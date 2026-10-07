#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check the beta firmware in emulation, starting from the .syx file that tools/make_firmware.py writes.

    python3 test/test_firmware.py --modded PATH/TO/Modded-Cycles --cycles model-cycles_OS1.13.syx [--fast]
                                  [--payload DIR] [--keep OUT.syx]

It makes the firmware (as a user would), reads the file back, and runs the real code of the OS on it, the
stock OS next to it for comparison:

  file      checksums, HMAC trailer, the other sections untouched, every changed byte of the OS accounted for
  boot      the bootstrap's own unpacker reads the packed OS; the boot hook installs the payload
  tables    the tables the OS builds at boot; every lookup by machine, knob, CC or descriptor
  screens   MACHINES screen, wheel, machine change with its default values, main-screen knobs
  sound     the six stock machines sample for sample; MACRO and SOPHIE through their own machine numbers
  projects  what a sound saved with machine 7 or 8 does, here and on the stock OS

This is emulation, function by function: there is no emulator of the whole Model:Cycles. It proves what it
lists and nothing else. NOTHING here has run on hardware.

The bench is Modded-Cycles' tools/emu/mcengine.py (voice loop), imported from your checkout; the way of
running OS functions one at a time with their surroundings intercepted, and which functions to run, follow
its tests (test_sdvintage_7th.py, test_syntakt_machines.py). The code here is our own.

--fast as in play_machines.py: a Unicorn built with digiemu's patches. Without it the sound part takes hours.
"""
import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from mtlib import aplib, container          # noqa: E402
from mtlib.syx import unwrap                # noqa: E402

BASE, IMAGE_LEN = 0x40000400, 0x1a9d40
BSS = (0x4019b590, 0x423380b0)
STOP, STACK = 0x90000100, 0x90020000        # STOP: its low byte must be 0 (see screen())
FAKE = 0x93000000                           # fake objects
NAMES = ['Kick', 'Snare', 'Metal', 'Perc', 'Tone', 'Chord']
FAILED = []


def check(ok, msg):
    print('  %s %s' % ('ok    ' if ok else 'FAILED', msg), flush=True)
    if not ok:
        FAILED.append(msg)
    return ok


def sha(b):
    return hashlib.sha256(b).hexdigest()


def be32(x):
    return struct.pack('>I', x & 0xffffffff)


# ---- running OS functions ---------------------------------------------------------------------------------
class Box:
    """OS image, its BSS, the payload, SRAM; functions are called one at a time, some of them intercepted."""

    def __init__(self, image, payload=b'', sram=None):
        uc = self.uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        uc.ctl_set_cpu_model(CPU)
        uc.mem_map(0x40000000, 0x02400000)
        uc.mem_write(BASE, bytes(image))
        uc.mem_map(0x43000000, 0x00100000)
        uc.mem_write(0x43000000, bytes(payload))
        uc.mem_map(0x80000000, 0x00020000)
        if sram:
            uc.mem_write(0x80000000, sram)
        uc.mem_map(0x90000000, 0x04000000)
        uc.mem_write(STOP, b'\x4e\x71\x4e\x71')
        self.bad, self.stubs, self.calls, self.hooked = [], {}, [], set()
        uc.hook_add(UC_HOOK_MEM_UNMAPPED, lambda u, a, addr, s, v, d: self.bad.append(addr) or False)

    def stub(self, addr, name=None, ret=0):
        """Intercept a function: note its arguments, return ret."""
        self.stubs[addr] = (name or '%#x' % addr, ret)
        if addr not in self.hooked:
            self.hooked.add(addr)
            self.uc.hook_add(UC_HOOK_CODE, self._stub, begin=addr, end=addr)

    def _stub(self, uc, addr, size, ud):
        if addr in self.stubs:
            name, ret = self.stubs[addr]
            sp = uc.reg_read(mk.UC_M68K_REG_A7)
            self.calls.append((name, struct.unpack('>8I', uc.mem_read(sp + 4, 32))))
            uc.reg_write(mk.UC_M68K_REG_D0, ret)
            uc.reg_write(mk.UC_M68K_REG_PC, struct.unpack('>I', uc.mem_read(sp, 4))[0])
            uc.reg_write(mk.UC_M68K_REG_A7, sp + 4)

    def rd(self, a, n):
        return bytes(self.uc.mem_read(a, n))

    def u32(self, a):
        return struct.unpack('>I', self.rd(a, 4))[0]

    def cstr(self, a):
        return self.rd(a, 32).split(b'\0')[0].decode('latin1')

    def run(self, pc, sp, regs=None, count=50_000_000):
        for r, v in (regs or {}).items():
            self.uc.reg_write(r, v & 0xffffffff)
        self.uc.reg_write(mk.UC_M68K_REG_A7, sp)
        try:
            self.uc.emu_start(pc, STOP, count=count)
        except UcError as e:
            self.bad.append(('error', str(e)))
        if self.uc.reg_read(mk.UC_M68K_REG_PC) != STOP:
            self.bad.append(('stopped at', self.uc.reg_read(mk.UC_M68K_REG_PC)))
        return self.uc.reg_read(mk.UC_M68K_REG_D0)

    def call(self, fn, *args, regs=None, count=50_000_000):
        sp = STACK - 0x1000
        self.uc.mem_write(sp, struct.pack('>%dI' % (1 + len(args)), STOP, *[a & 0xffffffff for a in args]))
        return self.run(fn, sp, regs, count)


def s32(x):
    return x - (1 << 32) if x & 0x80000000 else x


# ---- the file ---------------------------------------------------------------------------------------------
def read_syx(path):
    stream, info = unwrap(open(path, 'rb').read())           # raises on a bad message checksum
    cont = container.parse(stream)
    sec = {s['id']: dict(s, body=cont['blob'][s['off']:s['off'] + s['size']]) for s in cont['sections']}
    return stream, info, cont, sec


def file_checks(official, built, rep):
    print('file')
    s0, i0, c0, sec0 = read_syx(official)
    s1, i1, c1, sec1 = read_syx(built)
    check(i1['count'] * 101 == len(s1) and i1['product'] == i0['product'] and i1['start_seq'] == i0['start_seq'],
          'SysEx: %d messages (official: %d), every message checksum right, same product and sequence start'
          % (i1['count'], i0['count']))
    blob = c1['blob']
    check(int.from_bytes(s1[0:4], 'big') == len(blob) and int.from_bytes(s1[4:8], 'big') == container.content_checksum(blob)
          and c1['version'] == c0['version'] and [s['id'] for s in c1['sections']] == [s['id'] for s in c0['sections']],
          'container: length, content checksum, version %s, same sections in the same order' % c1['version'])
    same = all(sec1[i]['body'] == sec0[i]['body'] and sec1[i]['attr'] == sec0[i]['attr'] for i in (5, 2, 4))
    check(same and sec1[3]['attr'] == sec0[3]['attr'] == BASE, 'sections 5, 2 and 4 byte for byte as in the official file; load addresses unchanged')
    p3 = sec1[3]['body']
    check(int.from_bytes(p3[0:4], 'big') == len(p3) - 8 and int.from_bytes(p3[4:8], 'big') == sum(p3[8:]) & 0xffffffff,
          'section 3: stream length and byte sum')
    stock = aplib.depack(sec0[3]['body'])[0]
    new = aplib.depack(p3)[0]
    boot = aplib.depack(sec0[2]['body'])[0]
    plain = [new if s['id'] == 3 else boot if s['id'] == 2 else sec1[s['id']]['body'] for s in c1['sections']]
    key = container.find_key(plain, blob[:-32], blob[-32:])
    key0 = container.find_key([stock, boot], c0['blob'][:-32], c0['blob'][-32:])
    check(key is not None and key == key0, 'HMAC-SHA256 trailer right, with the key derived the same way as for the official file')
    check(sha(new) == rep['main_os_sha256'] and sha(open(built, 'rb').read()) == rep['syx_sha256'],
          'main OS %s..., file %s...' % (rep['main_os_sha256'][:16], rep['syx_sha256'][:16]))

    # every byte of the OS that differs from the official one must belong to a change the tool lists
    writes = [(w['at'], bytes.fromhex(w['old']), bytes.fromhex(w['new'])) for w in rep['writes']]
    listed = bytearray(IMAGE_LEN)
    ok = True
    for at, old, data in writes:
        o = at - BASE
        ok &= stock[o:o + len(old)] == old and new[o:o + len(data)] == data and not any(listed[o:o + len(data)])
        listed[o:o + len(data)] = b'\x01' * len(data)
    diff = [i for i in range(IMAGE_LEN) if stock[i] != new[i]]
    ok &= all(listed[i] for i in diff)
    groups = {}
    for w in rep['writes']:
        groups[w['group']] = groups.get(w['group'], 0) + 1
    check(ok, 'OS image: %d bytes differ from the official one, all inside the %d listed changes (%d bytes; %s)'
          % (len(diff), len(writes), sum(listed), ', '.join('%s %d' % kv for kv in groups.items())))
    check(len(new) == IMAGE_LEN + rep['payload_len'] and sha(new[IMAGE_LEN:]) == rep['payload_sha256']
          and BASE + len(new) <= 0x40200000,
          'payload: %d bytes appended, the OS ends at %#x (must stay below 0x40200000)' % (rep['payload_len'], BASE + len(new)))
    return stock, new, boot, p3, sec0[3]['body']


# ---- boot -------------------------------------------------------------------------------------------------
def bootstrap_unpack(boot, packed, want):
    """The bootstrap's own unpacker (0x800006bc in section 2, which runs at 0x800003fc) reads the packed OS
    from 0x40200000 and writes it to 0x40000400. It is the one that runs on the device, not mtlib."""
    uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
    uc.ctl_set_cpu_model(CPU)
    uc.mem_map(0x80000000, 0x20000)
    uc.mem_write(0x800003fc, boot)
    uc.mem_map(0x40000000, 0x00400000)
    uc.mem_write(0x40200000, packed)
    stop, sp = 0x8001f000, 0x8001e000
    uc.mem_write(stop, b'\x4e\x71\x4e\x71')
    uc.mem_write(sp, struct.pack('>III', stop, 0x40200000, BASE))
    uc.reg_write(mk.UC_M68K_REG_A7, sp)
    bad = []
    uc.hook_add(UC_HOOK_MEM_UNMAPPED, lambda u, a, addr, s, v, d: bad.append(addr) or False)
    try:
        uc.emu_start(0x800006bc, stop, count=600_000_000)
    except UcError as e:
        bad.append(str(e))
    return (bytes(uc.mem_read(BASE, len(want))) == want and not any(uc.mem_read(BASE + len(want), 256)) and not bad
            and uc.reg_read(mk.UC_M68K_REG_D0) == len(want))


def boot(image, pay_at, pay_len):
    """What the OS does first (0x4000052c): initialise the SRAM (0x4000045c), clear the BSS (0x400004b2).
    Memory above the BSS is filled with a mark first, to see exactly what gets written there."""
    b = Box(image[:IMAGE_LEN])
    b.uc.mem_write(BASE, bytes(image))                      # with what the bootstrap unpacked after the OS
    b.uc.mem_write(BSS[1], b'\xa5' * (0x42400000 - BSS[1]))
    b.uc.mem_write(0x43000000, b'\xa5' * 0x100000)
    b.uc.mem_write(0x40a00000, b'\x5a' * 0x1000)            # and something in the BSS, to see it cleared
    marks = {mk.UC_M68K_REG_D4: 0x44444444, mk.UC_M68K_REG_D5: 0x55555555, mk.UC_M68K_REG_D6: 0x66666666,
             mk.UC_M68K_REG_D7: 0x77777777, mk.UC_M68K_REG_A2: 0xa2a2a2a2}
    b.call(0x4000045c, regs=marks)
    b.call(0x400004b2, count=200_000_000)
    kept = all(b.uc.reg_read(r) == v for r, v in marks.items()) and b.uc.reg_read(mk.UC_M68K_REG_A7) == STACK - 0x1000 + 4
    return b, kept


def boot_checks(stock, new, bootsec, packed, rep):
    print('boot')
    check(bootstrap_unpack(bootsec, packed, new),
          "the bootstrap's own unpacker turns the packed OS (%d bytes) back into the OS as built (%d bytes)" % (len(packed), len(new)))
    at, n = rep['payload_at'], rep['payload_len']
    a, kept_a = boot(stock, at, n)
    b, kept_b = boot(new, at, n)
    check(not a.bad and not b.bad and kept_a and kept_b, 'SRAM initialisation and BSS clear run to their end, stock and modified; registers and stack as stock')
    payload = b.rd(at, n)
    check(payload == new[IMAGE_LEN:], 'boot hook: the payload is at %#x, identical to the %d bytes appended to the OS' % (at, n))
    file_len, sym = rep['payload_file_len'], rep['symbols']
    check(not any(payload[sym['_bss_start'] - at:]) and sym['_end'] - at == n,
          'its state (%d bytes from %#x) is zero' % (n - file_len, sym['_bss_start']))
    around = b.rd(at + n, 0x100000 - n) == b'\xa5' * (0x100000 - n) and b.rd(BSS[1], 0x1000) == b'\xa5' * 0x1000
    check(around and a.rd(0x43000000, 0x100000) == b'\xa5' * 0x100000,
          'nothing else is written above the BSS (stock writes nothing there at all)')
    code = (BASE, BSS[0])
    check(b.rd(*[code[0], code[1] - code[0]]) == new[:code[1] - BASE] and a.rd(code[0], code[1] - code[0]) == stock[:code[1] - BASE],
          'the OS image below the BSS is not modified by the boot')
    zero = lambda x: not any(x.rd(BSS[0], 0x100000)) and not any(x.rd(0x40a00000, 0x1000)) and not any(x.rd(BSS[1] - 0x1000, 0x1000))
    check(zero(a) and zero(b) and not any(b.rd(BASE + IMAGE_LEN, n)), 'the BSS is cleared, the appended copy of the payload with it')
    sram = b.rd(0x80000000, 0x10000)
    check(sram == a.rd(0x80000000, 0x10000), 'the internal SRAM is exactly as the stock boot leaves it')
    return payload, sram


# ---- tables and lookups -----------------------------------------------------------------------------------
BSS_TABLES = (0x40a79200, 0x40a7b000)       # everything the builder 0x4005a274 writes
ROWS, CCROWS, ROW_COUNT = 0x40a79418, 0x40a7ada4, 0x40a79260
DESC = 0x4010dce0


def tables(a, b, rep):
    print('tables built at boot, lookups')
    sym, machines = rep['symbols'], rep['machines']
    first = {m['index']: 76 + 5 * i for i, m in enumerate(machines)}
    a.call(0x4005a274)
    b.call(0x4005a274)
    check(not a.bad and not b.bad, 'table builder (0x4005a274) runs to its end')
    lo, hi = BSS_TABLES
    sa, sb = a.rd(lo, hi - lo), bytearray(b.rd(lo, hi - lo))
    rows_a, cc_a = sa[ROWS - lo:][:192], sa[CCROWS - lo:][:192]
    rows_b, cc_b = b.rd(sym['ml_rows'], 256), b.rd(sym['ml_ccrows'], 256)
    counts = (a.u32(ROW_COUNT), b.u32(ROW_COUNT))
    sb[ROWS - lo:ROWS - lo + 192] = rows_a                  # the old rows stay empty in the modified OS
    sb[CCROWS - lo:CCROWS - lo + 192] = cc_a
    sb[ROW_COUNT - lo:ROW_COUNT - lo + 4] = sa[ROW_COUNT - lo:][:4]
    check(counts == (6, 8), 'rows: stock %d machines, modified %d' % counts)
    check(bytes(sb) == sa, 'every other table the builder fills is identical to stock')
    check(rows_b[:192] == rows_a and cc_b[:192] == cc_a, 'rows of machines 1-6 identical to stock')
    snare_r, snare_c = struct.unpack('>8I', rows_a[32:64]), struct.unpack('>8I', cc_a[32:64])
    ok = True
    for m, f in first.items():
        r, c = struct.unpack('>8I', rows_b[32 * m:][:32]), struct.unpack('>8I', cc_b[32 * m:][:32])
        ok &= r == tuple(f + x - 51 if 51 <= x <= 55 else x for x in snare_r)
        ok &= c == tuple(f + x - 51 if 51 <= x <= 54 else x for x in snare_c)
        print('         machine %d: Amp Decay and knob descriptors %s, CC 16-19 -> %s' % (m + 1, list(r[:6]), list(c[:4])))
    check(ok, "rows of machines 7 and 8: SNARE's, with their own descriptors")

    # machine, knob slot -> descriptor
    diff, outside = set(), []
    for m in range(-1, 17):
        for slot in range(34):
            x, y = a.call(0x4005a692, slot, m), b.call(0x4005a692, slot, m)
            if slot == 0x12 and not 0 <= m < 8:             # the OS does not check the machine here: stock reads
                outside.append(y)                           # outside its rows, ours reads an empty row
            elif x != y:
                diff.add((m, slot, y))
    want = {(m, 0x0b + k, f + k) for m, f in first.items() for k in range(4)} | {(m, 0x12, f + 4) for m, f in first.items()}
    check(diff == want and not any(outside),
          'machine, knob -> descriptor (0x4005a692), machines -1..16 x 34 slots: as stock except the %d answers for machines 7 and 8;\n'
          '         Amp Decay of a machine that does not exist: 0, the "Error" descriptor (stock reads outside its table)' % len(diff))
    if diff != want:
        print('         unexpected: %s; missing: %s' % (sorted(diff - want), sorted(want - diff)))
    # descriptor -> "belongs to one machine" and -> its machine
    spec = [(a.call(0x4005a556, d), b.call(0x4005a556, d)) for d in range(100)]
    ok = all(x == y for x, y in spec[:76]) and all(y == spec[0][0] for x, y in spec[86:])
    ok &= [s32(y) != 0 for x, y in spec[76:86]] == [True] * 4 + [False] + [True] * 4 + [False]
    mach = [(s32(a.call(0x4005a50a, d)), s32(b.call(0x4005a50a, d))) for d in range(100)]
    ok &= all(x == y for x, y in mach[:76]) and all(y == mach[0][0] for x, y in mach[86:])
    ok &= [y for x, y in mach[76:86]] == [6, 6, 6, 6, 7, 7, 7, 7, 7, 7]
    check(ok, 'descriptor -> belongs to one machine (0x4005a556), -> which (0x4005a50a): 0-75 as stock, 76-85 -> %s, past the end as stock'
          % [y for x, y in mach[76:86]])
    # track, machine, CC -> descriptor
    diff = set()
    for t in range(8):
        for m in range(10):
            for cc in range(128):
                x, y = a.call(0x4005a8ce, t, m, cc), b.call(0x4005a8ce, t, m, cc)
                if x != y:
                    diff.add((t, m, cc, y))
    want = {(t, m, 16 + k, f + k) for t in range(6) for m, f in first.items() for k in range(4)}
    check(diff == want and not a.bad and not b.bad,
          'track, machine, CC -> descriptor (0x4005a8ce), 8 x 10 x 128: as stock except CC 16-19 on machines 7 and 8 (%d answers)' % len(diff))

    # the descriptors themselves, through the OS's accessors
    def desc(x, d):
        x.call(0x4005a65a, d, regs={mk.UC_M68K_REG_A0: FAKE})
        rng = struct.unpack('>3i', x.rd(FAKE, 12))
        return (x.call(0x4005a4e8, d), x.cstr(x.call(0x4000b22a, 0, d)), x.cstr(x.call(0x4000b208, 0, d))) + tuple(v >> 8 for v in rng)
    da, db = [desc(a, d) for d in range(100)], [desc(b, d) for d in range(100)]
    alg = 41
    ok = all(da[d] == db[d] for d in range(76) if d != alg) and all(db[d] == db[0] for d in range(86, 100))
    ok &= da[alg][:4] == db[alg][:4] and (da[alg][4], db[alg][4]) == (5, 7) and da[alg][5] == db[alg][5]
    for m in machines:
        f = first[m['index']]
        for k, (long_, short, default) in enumerate(m['knobs']):
            ok &= db[f + k] == (0x0b + k, long_, short, 0, 127, default)
        ok &= db[f + 4] == (0x12, 'Amp Decay', 'DEC', 0, 127, m['decay'])
        print('         machine %d %-6s: %s, Amp Decay %d' % (m['index'] + 1, m['name'],
              ', '.join('%s/%s %d' % tuple(k) for k in m['knobs']), m['decay']))
    check(ok, 'descriptors read through the OS accessors: 0-75 as stock, except that "Algorithm" (the machine) now goes to 7; 76-85 ours')
    # descriptor -> state object, with the registers the stock functions leave alone
    keep = {mk.UC_M68K_REG_A0: 0xa0a0a0a0, mk.UC_M68K_REG_A1: 0xa1a1a1a1}
    st, kept = [], True
    for d in range(100):
        st.append((a.call(0x4004df40, d), b.call(0x4004df40, d, regs=keep)))
        kept &= all(b.uc.reg_read(r) == v for r, v in keep.items())
    ok = all(x == y for x, y in st[:76]) and all(st[d][1] == st[51 + (d - 76) % 5][0] for d in range(76, 86))
    ok &= all(y == st[0][0] for x, y in st[86:])
    for x in (a, b):
        x.stub(0x400ddf60, 'connect')
    for d in (0, 30, 75, 76, 80, 81, 85, 86, 99):
        a.calls, b.calls = [], []
        twin = d if d < 76 else 51 + (d - 76) % 5 if d < 86 else 0
        ok &= a.call(0x4004dfa2, twin, 0x1234) == b.call(0x4004dfa2, d, 0x1234) == 0x40a71500
        ok &= [c[1][:3] for c in a.calls] == [c[1][:3] for c in b.calls] and len(b.calls) == 1
    for x in (a, b):
        del x.stubs[0x400ddf60]
    check(ok and kept, "descriptor -> state object (0x4004df40, 0x4004dfa2): 0-75 as stock, 76-85 -> SNARE's; a0 and a1 untouched")


# ---- per-machine records, screens -------------------------------------------------------------------------
REC, REC_LEN, REP = 0x40a71540, 76, FAKE + 0x100000


def fill_records(x):
    """The seven per-machine records as the OS builds them at boot (0x400e0fc6...): two C++ strings ("GROO",
    sharing one representation with a reference count), then the 17 descriptors of the machine's page."""
    x.uc.mem_write(REP, struct.pack('>iii', 4, 4, 0) + b'GROO\0')
    for i in range(7):
        ids = [0] * 17
        if i:
            f = 46 + 5 * (i - 1)
            ids = [42, f + 4, f, f + 1, f + 2, f + 3, 26, 27, 29, 25, 23, 22, 39, 37, 40, 38, 9]
        x.uc.mem_write(REC + REC_LEN * i, struct.pack('>II17i', REP + 12, REP + 12, *ids))


def refs(x):
    return struct.unpack('>i', x.rd(REP + 8, 4))[0]


def fake_track(x, machine):
    """A track object for 0x4001477e and 0x4001488a: its methods are intercepted, method +40 gives its sound."""
    obj, vt, snd = FAKE + 0x200000, FAKE + 0x201000, FAKE + 0x202000
    x.uc.mem_write(obj, be32(vt))
    for k in range(16):
        x.uc.mem_write(vt + 4 * k, be32(FAKE + 0x203000 + 16 * k))
        x.stub(FAKE + 0x203000 + 16 * k, 'method+%d' % (4 * k), snd if 4 * k == 40 else 0)
    for fn in (0x400cf866, 0x4000eb90, 0x40013126, 0x40014072):
        x.stub(fn)
    x.uc.mem_write(snd, bytes(256))
    x.uc.mem_write(snd + 38, struct.pack('>H', (machine & 0xff) << 8))
    return obj, snd


def machine_of(x, snd):
    return struct.unpack('>b', x.rd(snd + 38, 1))[0]


def knobs_of(x, snd):
    return [struct.unpack('>h', x.rd(snd + 0x14 + 2 * s, 2))[0] >> 8 for s in (0x0b, 0x0c, 0x0d, 0x0e, 0x12)]


def screen(x, m):
    """Draw the MACHINES screen for machine m, from where the machine is known (0x400a25e0), with the drawing
    calls intercepted. The stack is filled with the address of STOP: any return ends the run, and the byte
    the code tests at 35(sp) is 0."""
    x.calls = []
    for fn, name in ((0x40071a04, 'text'), (0x40071da4, 'picture'), (0x40070c4e, 'mark'), (0x40070efc, 'full mark'),
                     (FAKE + 0x300000, 'a5'), (FAKE + 0x300010, 'a4')):
        x.stub(fn, name)
    x.uc.mem_write(0x40fe32cc, be32(FAKE + 0x400000))       # the two arrays of six pictures
    x.uc.mem_write(0x40fe384c, be32(FAKE + 0x500000))
    sp = STACK - 0x2000
    x.uc.mem_write(sp, be32(STOP) * 128)
    x.run(0x400a25e0, sp, {mk.UC_M68K_REG_D3: m, mk.UC_M68K_REG_D2: FAKE + 0x600000, mk.UC_M68K_REG_A2: FAKE + 0x601000,
                           mk.UC_M68K_REG_A5: FAKE + 0x300000, mk.UC_M68K_REG_A4: FAKE + 0x300010})
    text = [x.cstr(args[6]) for n, args in x.calls if n == 'text']
    pics = [((args[1] - FAKE) >> 20, ((args[1] - FAKE) & 0xfffff) // 28, args[2], args[3]) for n, args in x.calls if n == 'picture']
    marks = [(n == 'full mark', args[1], args[2], args[3], args[4]) for n, args in x.calls if 'mark' in n]
    return text, pics, marks


def screens(stock, new, payload, sram, rep):
    print('MACHINES screen, wheel, machine change, knobs')
    machines = rep['machines']
    names = NAMES + [m['name'] for m in machines]
    first = {m['index']: 76 + 5 * i for i, m in enumerate(machines)}
    a, b = Box(stock[:IMAGE_LEN], sram=sram), Box(new[:IMAGE_LEN], payload, sram)
    ok, chord_pics = True, screen(b, 5)[1]
    for m in range(10):
        ta, pa, ma = screen(a, m)
        tb, pb, mb = screen(b, m)
        ok &= not a.bad and not b.bad
        if m < 6:
            ok &= ta == tb == [NAMES[m]] and pa == pb and len(pa) == 2 and {p[1] for p in pb} == {m}
        elif m < 8:
            ok &= ta == ['Error'] and pa == [] and tb == [names[m]] and len(pb) == 2 and {p[1] for p in pb} == {5}
            ok &= [p[2:] for p in pb] == [p[2:] for p in chord_pics]
        else:
            ok &= ta == tb == ['Error'] and pa == pb == []
        ok &= len(ma) == 6 and len(mb) == 8 and [k[0] for k in mb] == [i == m for i in range(8)]
        ok &= [k[0] for k in ma] == [i == m for i in range(6)]
        ok &= all((k[2], k[4]) == (ma[0][2], ma[0][4]) and k[3] - k[1] == 4 for k in mb) and all(64 <= k[1] and k[3] <= 127 for k in mb)
        ok &= [k[3] for k in mb] == [73 + 7 * i for i in range(8)] and [k[3] for k in ma] == [80 + 7 * i for i in range(6)]
        if 6 <= m < 8:
            print('         machine %d: stock shows %s and no picture; modified shows "%s", picture %d (CHORD), mark %d of %d full'
                  % (m + 1, ta, tb[0], pb[0][1] + 1, m + 1, len(mb)))
    check(ok, 'MACHINES screen, machines 1-10: names and pictures of 1-6 as stock; 7 = "%s", 8 = "%s"; 8 marks, x %d to %d, in the right half; past 8: "Error", as stock past 6'
          % (names[6], names[7], mb[0][1], mb[-1][3]))

    # setting a track's machine
    got = {}
    for name, img, pl in (('stock', stock, b''), ('new', new, payload)):
        for m in range(10):
            x = Box(img[:IMAGE_LEN], pl, sram)
            obj, snd = fake_track(x, 1)
            x.call(0x4001477e, obj, m, 0, 0)
            got[name, m] = (machine_of(x, snd), bool(x.bad))
    ok = all(got['stock', m] == got['new', m] == (m, False) for m in range(6))
    ok &= all(got['stock', m] == (1, False) for m in range(6, 10)) and all(got['new', m] == (1, False) for m in (8, 9))
    ok &= got['new', 6] == (6, False) and got['new', 7] == (7, False)
    check(ok, "setting a track's machine (0x4001477e): 1-6 as stock, 7 and 8 accepted (stock refuses them), 9 and 10 refused")
    # the wheel, there and back
    seq = {}
    for name, img, pl in (('stock', stock, b''), ('new', new, payload)):
        x = Box(img[:IMAGE_LEN], pl, sram)
        obj, snd = fake_track(x, 0)
        out = []
        for step in [1] * 10 + [-1] * 10 + [3, 3, 3, -5, -5]:
            x.call(0x4001488a, obj, step, 0, 0)
            out.append(machine_of(x, snd) + 1)
        seq[name] = (out, bool(x.bad))

    def walk(top):
        m, out = 0, []
        for step in [1] * 10 + [-1] * 10 + [3, 3, 3, -5, -5]:
            m = max(0, min(top, m + step))
            out.append(m + 1)
        return out
    check(seq['stock'] == (walk(5), False) and seq['new'] == (walk(7), False),
          'wheel (0x4001488a), 10 clicks up, 10 down, then jumps: stock stops at 6 and 1, modified at 8 and 1\n'
          '         modified: %s' % ' '.join(map(str, seq['new'][0])))

    # per-machine records
    a, b = Box(stock[:IMAGE_LEN], sram=sram), Box(new[:IMAGE_LEN], payload, sram)
    for x in (a, b):
        fill_records(x)
    keep = {mk.UC_M68K_REG_A0: 0xa0a0a0a0, mk.UC_M68K_REG_A1: 0xa1a1a1a1}
    ok = all(a.call(0x4004df5c, i) == b.call(0x4004df5c, i, regs=keep) == REC + REC_LEN * i
             and b.uc.reg_read(mk.UC_M68K_REG_A1) == 0xa1a1a1a1 and b.uc.reg_read(mk.UC_M68K_REG_A0) == 0xa0a0a0a0 for i in range(7))
    ok &= all(a.call(0x4004df76, m) == b.call(0x4004df76, m, regs=keep) and b.uc.reg_read(mk.UC_M68K_REG_A1) == 0xa1a1a1a1 for m in range(6))
    before = refs(b)
    recs = {}
    for m, f in first.items():
        r1, r2 = b.call(0x4004df5c, m + 1), b.call(0x4004df76, m)
        raw = b.rd(r1, REC_LEN)
        ids = struct.unpack('>17i', raw[8:])
        ok &= r1 == r2 and rep['payload_at'] <= r1 < rep['payload_at'] + rep['payload_len'] and raw[:8] == be32(REP + 12) * 2
        ok &= ids == (42, f + 4, f, f + 1, f + 2, f + 3, 26, 27, 29, 25, 23, 22, 39, 37, 40, 38, 9)
        recs[m] = list(ids[:6])
    ok &= refs(b) == before + 2 * len(first)
    b.call(0x4004df5c, 7), b.call(0x4004df76, 7)
    ok &= refs(b) == before + 2 * len(first) and not b.bad
    check(ok, 'per-machine records (0x4004df5c, 0x4004df76): 0-6 as stock; machines 7 and 8 get their own, built once: %s' % recs)
    stock_before = a.call(0x4004df76, 6)
    ok = stock_before == REC - REC_LEN
    kick = REC + REC_LEN
    ok &= all(b.call(0x4004df76, m) == kick for m in (8, 9, 100, -1)) and all(b.call(0x4004df5c, i) == kick for i in (9, 10, 100, -1))
    check(ok and not b.bad, "a machine that does not exist (9, 10, 100, -1): KICK's record. The stock OS gives %#x, 76 bytes BEFORE its table, for any machine past CHORD" % stock_before)

    # does a descriptor apply to a track? (0x4000aa9a: the track's machine against the descriptor's)
    app = {}
    for name, img, pl in (('stock', stock, b''), ('new', new, payload)):
        x = Box(img[:IMAGE_LEN], pl, sram)
        obj, snd = fake_track(x, 0)
        this = FAKE + 0x700000
        x.uc.mem_write(this, be32(0) + be32(obj))
        for m in range(8):
            x.uc.mem_write(snd + 38, bytes([m]))
            app[name, m] = [x.call(0x4000aa9a, this, d) & 0xff != 0 for d in range(86)]
        app[name, 'bad'] = bool(x.bad)
    ok = all(app['stock', m][:76] == app['new', m][:76] for m in range(8)) and not app['new', 'bad']
    ok &= all(app['new', m][76:] == [first.get(m) is not None and first[m] <= d < first[m] + 4 or d in (80, 85) and app['new', m][55]
                                    for d in range(76, 86)] for m in range(8))
    ok &= not any(app['new', 6][46:50] + app['new', 6][51:55] + app['new', 7][51:55]) and all(app['new', 1][51:55])
    check(ok, 'descriptor applies to a track (0x4000aa9a), machines 1-8 x 86 descriptors: 0-75 as stock; the knobs of MACRO apply to machine 7 only, those of SOPHIE to machine 8 only')

    # the real machine change, through the MACHINES screen's handler (0x400a2712 -> 0x4001488a -> 0x4001477e ->
    # 0x40014072): the new machine's default values are written into the sound
    def turn(img, pl, start, steps):
        x = Box(img[:IMAGE_LEN], pl, sram)
        fill_records(x)
        obj, snd = fake_track(x, start)
        del x.stubs[0x40014072]
        this = FAKE + 0x700000
        x.uc.mem_write(this, bytes(256))
        for k in range(6):
            x.uc.mem_write(this + 0x70 + 4 * k, struct.pack('>i', -1))
        for fn, ret in ((0x400cf866, FAKE + 0x800000), (0x4000eb90, FAKE + 0x800000), (0x40012412, 0), (0x400cf9a8, FAKE + 0x800000),
                        (0x4006bdfe, 0), (0x4000eb9c, FAKE + 0x800000), (0x40009c1a, obj), (0x400f44c6, 0), (0x4001416c, 0)):
            x.stub(fn, ret=ret)
        out = []
        for step in steps:
            x.call(0x400a2712, this, step, 0, 0)
            out.append((machine_of(x, snd), knobs_of(x, snd)))
        return out, bool(x.bad)
    up, bad_up = turn(new, payload, 4, [1, 1, 1, 1])                # TONE -> CHORD -> MACRO -> SOPHIE -> stays
    down, bad_down = turn(new, payload, 7, [-1, -1, -1])            # SOPHIE -> MACRO -> CHORD -> TONE
    ref_up, bad_ref = turn(stock, b'', 4, [1, 1])                   # stock: TONE -> CHORD -> stays
    ref_down, bad_ref2 = turn(stock, b'', 5, [-1])                  # stock: CHORD -> TONE
    want = {m['index']: [k[2] for k in m['knobs']] + [m['decay']] for m in machines}
    ok = not (bad_up or bad_down or bad_ref or bad_ref2)
    ok &= up[0] == ref_up[0] and up[0][0] == 5 and up[1] == (6, want[6]) and up[2] == (7, want[7]) and up[3][0] == 7
    ok &= down[0] == (6, want[6]) and down[1] == ref_up[0] and down[2] == ref_down[0] and down[2][0] == 4
    check(ok, 'machine change with the real handler: CHORD -> %s %s -> %s %s (COLOR SHAPE SWEEP CONTOUR DECAY), stops there;\n'
          '         back: -> %s -> CHORD %s -> TONE %s, the values the stock OS writes for CHORD and TONE'
          % (names[6], up[1][1], names[7], up[2][1], names[6], down[1][1], down[2][1]))

    # main screen: knob -> descriptor
    res = {}
    for name, img, pl in (('stock', stock, b''), ('new', new, payload)):
        x = Box(img[:IMAGE_LEN], pl, sram)
        fill_records(x)
        x.uc.mem_write(REC - REC_LEN, struct.pack('>19I', *[0xa0000000 + 16 * k for k in range(19)]))  # what lies before the table: poison
        this, vec = FAKE + 0x700000, FAKE + 0x710000
        x.uc.mem_write(vec, struct.pack('>8i', 1, 2, 3, 4, 5, 6, 0, 0))
        x.uc.mem_write(this + 104, struct.pack('>III', vec, vec + 24, vec + 24))
        for m in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 100, -1):
            for fn, ret in ((0x4001e318, m), (0x400cf9a8, FAKE + 0x800000), (0x4006b736, 0)):
                x.stub(fn, ret=ret)
            res[name, m] = [x.call(0x4001e814, this, k, 0, 0) for k in range(2, 16)]
        res[name, 'bad'] = bool(x.bad)
    ok = all(res['stock', m] == res['new', m] for m in range(6)) and not res['new', 'bad']
    for m, f in first.items():
        ok &= res['new', m][:6] == [42, f + 4, f, f + 1, f + 2, f + 3] and res['new', m][6:] == res['new', 1][6:]
        ok &= res['stock', m][:6] == [0] * 6
    ok &= all(res['new', m] == res['new', 0] for m in (8, 9, 100, -1))
    check(ok, "main screen, knob -> descriptor (0x4001e814), knobs 2-15: machines 1-6 as stock; 7 -> %s, 8 -> %s (stock: nothing); a machine that does not exist -> KICK's"
          % (res['new', 6][:6], res['new', 7][:6]))


# ---- sound ------------------------------------------------------------------------------------------------
MACRO = ['WSHAPE', '2OP FM', 'NOISE', 'PARTCL', 'BDRUM', 'SNARE', 'HIHAT', 'GRAIN']
SOPHIE = ['FUSE', 'BOOM', 'PIPE', 'SHARD']
PITCHED = {'WSHAPE', '2OP FM', 'GRAIN'}


def frequency(x):
    y = np.asarray(x[2400:2400 + 8192], dtype=float)
    y = y - y.mean()
    ac = np.correlate(y, y, 'full')[len(y) - 1:]
    lo, hi = 48000 // 2500, 48000 // 30
    return 48000.0 / (lo + int(np.argmax(ac[lo:hi])))


def sound(stock, new, payload, rep, out_dir):
    print('sound')
    sym, at = rep['symbols'], rep['payload_at']
    mcengine.PAYLOAD_CODE = ((at, sym['_code_end']),)
    mcengine.SRAM_CODE = (at + 0x10000000, 0, 0)            # no second code area
    in_payload = [0]

    def engine(img, pl=None, only=None):
        eng = mcengine.Engine(bytes(img[:IMAGE_LEN]), payload=(at, pl) if pl else None)
        if only is not None:                                # the other voices: a machine number nothing renders
            for t in range(6):
                if t != only:
                    eng.uc.mem_write(mcengine.VOICE0 + t * mcengine.VSTRIDE, be32(99))
        return eng

    def defaults(m):                                        # the stock defaults, from the descriptors of the OS
        d = lambda i: struct.unpack_from('>I', stock, DESC - BASE + i * 0x38 + 0x10)[0] >> 8
        f = 46 + 5 * m
        return dict(color=d(f), shape=d(f + 1), sweep=d(f + 2), contour=d(f + 3), decay=d(f + 4))

    # the six stock machines, sample for sample
    cases = (('defaults', {}), ('note 48, PUNCH', dict(note=48, punch=1)), ('note 72, knobs moved', dict(note=72, color=100, shape=20, sweep=90, contour=110, decay=90, gate=1)))
    ok, total, quiet = True, 0, []
    for m in range(6):
        for cname, over in cases:
            kw = dict(defaults(m), machine=m, note=60, punch=0)
            kw.update(over)
            res = []
            for img, pl in ((stock, None), (new, payload)):
                eng = engine(img, pl, only=0)
                eng.set(0, **kw)
                res.append((eng.render(300, trig_at=(1,), track=0), list(eng.unmapped)))
            (x, ux), (y, uy) = res
            ok &= np.array_equal(x, y) and not ux and not uy
            total += len(x)
            if np.max(np.abs(x)) < 2**31 * 0.005:
                quiet.append((NAMES[m], cname))
    check(ok and not quiet, 'the six stock machines, 3 settings each, 0.2 s: every one of the %d samples identical to the stock OS' % total)
    # all six tracks at once, one stock machine each, retriggered: the whole mix of tracks identical
    res = []
    for img, pl in ((stock, None), (new, payload)):
        eng = engine(img, pl)
        for t in range(6):
            eng.set(t, **dict(defaults(t), machine=t, note=48 + 5 * t, punch=t & 1))
        ran = [0]
        if pl:
            eng.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u: ran.__setitem__(0, ran[0] + 1), begin=at, end=at + len(pl))
        blocks = [eng.block(0x3f if b % 40 == 1 else 0) for b in range(200)]
        res.append((np.concatenate(blocks, axis=1), list(eng.unmapped), ran[0]))
    check(np.array_equal(res[0][0], res[1][0]) and not res[1][1] and res[1][2] == 0 and np.all(np.max(np.abs(res[0][0]), axis=1) > 2**24),
          'six tracks, one stock machine each, retriggered: all six outputs identical to stock; not one instruction of the payload runs (%d)' % res[1][2])

    # MACRO and SOPHIE through their own machine numbers
    os.makedirs(out_dir, exist_ok=True)
    print('         %-7s %-7s %6s  %s' % ('machine', 'engine', 'peak', 'frequency'))
    ok = True
    for m in rep['machines']:
        engines = MACRO if m['name'] == 'MACRO' else SOPHIE
        zone = 128 // (16 if m['name'] == 'MACRO' else 4)
        for n, label in enumerate(engines):
            eng = engine(new, payload, only=0)
            eng.set(0, machine=m['index'], note=60, punch=0, color=zone * n + zone // 2, shape=64, sweep=64, contour=64, decay=80)
            x = eng.render(750, trig_at=(1,), track=0)
            peak = float(np.max(np.abs(x))) / 2**31
            f = frequency(x) if label in PITCHED else None
            good = peak > 0.01 and not eng.unmapped and (f is None or abs(f / 261.63 - 1) < 0.015)
            ok &= good
            mcengine.wav(os.path.join(out_dir, ('%s-%s.wav' % (m['name'], label.replace(' ', ''))).lower()), x)
            print('         %-7s %-7s %6.3f  %s%s' % (m['name'], label, peak, ('%.1f Hz' % f) if f else '-', '' if good else '   <-- FAILED'))
    check(ok, 'machines 7 (MACRO) and 8 (SOPHIE), chosen by their machine number: the 12 engines sound, note 60 at 261.6 Hz (within 1.5 %) for the pitched ones')
    # default knobs of each machine give a sound; PITCH and the other common knobs act
    ok = True
    for m in rep['machines']:
        kw = dict(zip(('color', 'shape', 'sweep', 'contour'), (k[2] for k in m['knobs'])), decay=m['decay'], machine=m['index'], note=60)
        eng = engine(new, payload, only=0)
        eng.set(0, **kw)
        x = eng.render(400, trig_at=(1,), track=0)
        eng = engine(new, payload, only=0)
        eng.set(0, **dict(kw, pitch=76))
        y = eng.render(400, trig_at=(1,), track=0)
        f0, f1 = frequency(x), frequency(y)
        ok &= np.max(np.abs(x)) > 2**31 * 0.01 and (m['name'] != 'MACRO' or abs(f1 / f0 - 2) < 0.03) and not eng.unmapped
        print('         %s at its default knobs: peak %.3f, %.1f Hz; PITCH +12: %.1f Hz' % (m['name'], np.max(np.abs(x)) / 2**31, f0, f1))
    check(ok, 'each added machine sounds at the default values of its knobs; PITCH +12 doubles the frequency (MACRO WSHAPE)')
    # machine locks on one track: stock and added machines in turn
    eng = engine(new, payload, only=0)
    order = [1, 6, 7, 4, 6, 0, 7, 5]
    kws = {m['index']: dict(zip(('color', 'shape', 'sweep', 'contour'), (k[2] for k in m['knobs'])), decay=m['decay']) for m in rep['machines']}

    def lock(e, blk):
        if blk % 80 == 0 and blk // 80 < len(order):
            m = order[blk // 80]
            e.set(0, machine=m, note=60, **(kws[m] if m in kws else defaults(m)))
    x = eng.render(80 * len(order), trig_at=tuple(80 * k + 1 for k in range(len(order))), track=0, on_block=lock)
    parts = [float(np.max(np.abs(x[32 * (80 * k + 3):32 * (80 * k + 80)]))) / 2**31 for k in range(len(order))]
    check(all(p > 0.01 for p in parts) and not eng.unmapped,
          'machine locks on one track, %s: every step sounds (peaks %s)' % (' '.join(str(m + 1) for m in order), ' '.join('%.2f' % p for p in parts)))
    # six tracks of added machines on the same step
    eng = engine(new, payload)
    for t in range(6):
        m = rep['machines'][t % 2]
        eng.set(t, machine=m['index'], note=48 + 3 * t, color=(24 + 8 * t) if t % 2 == 0 else 16 + 32 * (t // 2), shape=64, sweep=64, contour=64, decay=80)
    blocks = np.concatenate([eng.block(0x3f if b % 60 == 1 else 0) for b in range(180)], axis=1)
    check(np.all(np.max(np.abs(blocks), axis=1) > 2**31 * 0.01) and not eng.unmapped,
          'six tracks at once, MACRO and SOPHIE alternating, triggered on the same block: all six sound, no stray memory access')
    return engine, defaults


def projects(stock, new, payload, rep, engine, defaults):
    print('a sound saved with machine 7 or 8')
    print('         Loading a project or a preset from the internal storage cannot be emulated: the bench has no file')
    print('         system and no project loader. What a loaded sound holds is its machine number (parameter word 9) and')
    print('         its knob values, by knob and not by machine. What the code does with such a sound:')
    kw = dict(color=4, shape=64, sweep=64, contour=64, decay=80, note=60)
    res = {}
    for m in (5, 6, 7, 8, 100):
        for name, img, pl in (('stock', stock, None), ('new', new, payload)):
            eng = engine(img, pl, only=0)
            eng.set(0, machine=m, **(kw if m != 5 else dict(kw)))
            x = eng.render(200, trig_at=(1,), track=0)
            res[name, m] = (x, bool(eng.unmapped), struct.unpack('>I', eng.uc.mem_read(mcengine.VOICE0, 4))[0])
    ok = all(not res[k][1] for k in res)
    ok &= res['new', 6][2] == 6 and res['new', 7][2] == 7 and all(np.max(np.abs(res['new', m][0])) > 2**24 for m in (6, 7))
    check(ok, 'this firmware: machine numbers 7 and 8 in the sound play MACRO and SOPHIE at the next trig (voice loop)')
    ok = all(res['stock', m][2] == 5 and np.array_equal(res['stock', m][0], res['stock', 5][0]) for m in (6, 7, 8, 100))
    ok &= all(res['new', m][2] == 5 and np.array_equal(res['new', m][0], res['stock', 5][0]) for m in (8, 100))
    check(ok, 'official OS, sound with machine 7 or 8: the voice loop plays CHORD with the knob values of the sound, no stray access.\n'
          '         Same here for a machine number past 8. (Its screens are another matter: see the per-machine records above.)')


# ---- main -------------------------------------------------------------------------------------------------
def main():
    global Uc, UcError, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_MEM_UNMAPPED, UC_HOOK_CODE, mk, np, mcengine, CPU
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--modded', required=True, help='a checkout of github.com/18nelli18/Modded-Cycles')
    ap.add_argument('--cycles', required=True, help='the official model-cycles_OS1.13.syx')
    ap.add_argument('--payload', help='folder with payload.bin, stub.bin, payload.sym (default: prebuilt/)')
    ap.add_argument('--keep', help='keep the firmware file made for the test here')
    ap.add_argument('--out', default=os.path.join(ROOT, 'out', 'firmware'), help='.wav files of the added machines')
    ap.add_argument('--fast', action='store_true')
    args = ap.parse_args()

    sys.path.insert(0, os.path.join(args.modded, 'tools', 'emu'))
    import numpy as np
    import emac
    import mcengine
    from unicorn import Uc, UcError, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_MEM_UNMAPPED, UC_HOOK_CODE
    from unicorn import m68k_const as mk
    if args.fast:
        emac.EMAC.install = lambda self, instrs: 0
        mcengine._emac_instrs = lambda main_os, ranges: {}
        mcengine._emac_payload = lambda payload, dst=mcengine.PAYLOAD_DST: {}
        mcengine.mk.UC_CPU_M68K_ANY = mcengine.mk.UC_CPU_M68K_CFV4E
        CPU = mk.UC_CPU_M68K_CFV4E
    else:
        CPU = mk.UC_CPU_M68K_ANY
        slow = emac.EMAC._slow

        def _slow(self, uc, addr):                          # as in play_machines.py
            sz, mn, ops = self.ops[addr]
            if mn == 'movel' and 'accext' in ops:
                src, dst = [a.strip() for a in ops.split(',')]
                ext = self.__dict__.setdefault('ext', {})
                if src.startswith('%accext'):
                    self.w(dst, ext.get(src, 0))
                else:
                    ext[dst] = self.r(src)
                uc.reg_write(mk.UC_M68K_REG_PC, addr + sz)
                return
            return slow(self, uc, addr)
        emac.EMAC._slow = _slow

    with tempfile.TemporaryDirectory() as tmp:
        built, report = args.keep or os.path.join(tmp, 'beta.syx'), os.path.join(tmp, 'report.json')
        cmd = [sys.executable, os.path.join(ROOT, 'tools', 'make_firmware.py'), args.cycles, '-o', built, '--report', report]
        if args.payload:
            cmd += ['--payload', args.payload]
        print('making the firmware: ' + ' '.join(cmd[1:]))
        made = subprocess.run(cmd, capture_output=True, text=True)
        print(''.join('    ' + l + '\n' for l in made.stdout.splitlines()), end='')
        if made.returncode:
            print(made.stderr)
            sys.exit(1)
        rep = json.load(open(report))
        stock, new, bootsec, packed, _ = file_checks(args.cycles, built, rep)

    payload, sram = boot_checks(stock, new, bootsec, packed, rep)
    tables(Box(stock[:IMAGE_LEN], sram=sram), Box(new[:IMAGE_LEN], payload, sram), rep)
    screens(stock, new, payload, sram, rep)
    engine, defaults = sound(stock, new, payload, rep, args.out)
    projects(stock, new, payload, rep, engine, defaults)

    print('\n%s' % ('ALL CHECKS PASSED (in emulation; nothing here has run on hardware)' if not FAILED
                    else '%d CHECK(S) FAILED:\n  ' % len(FAILED) + '\n  '.join(FAILED)))
    sys.exit(1 if FAILED else 0)


if __name__ == '__main__':
    main()
