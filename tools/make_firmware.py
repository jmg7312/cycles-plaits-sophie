#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Make a Model:Cycles firmware file with the Plaits and Sophie machines added to the machine list.

    python3 tools/make_firmware.py model-cycles_OS1.13.syx -o cycles_plaits_sophie_beta.syx

It reads YOUR official Model:Cycles OS 1.13 file (nothing else is accepted), adds the two machines after the
six stock ones, and writes a .syx to send with Elektron Transfer. No Elektron code is distributed with this
tool: everything of the OS comes from your file.

BETA. NOT TESTED ON HARDWARE. Read "Beta firmware" in README.md and docs/BETA-TEST.md before flashing.

Options:
    --payload DIR   take payload.bin, stub.bin and payload.sym from DIR (default: prebuilt/; build/ after
                    ./build.sh)
    --list          print every change made to the OS, with its reason
    --report FILE   write the list of changes and the layout as JSON (used by test/test_firmware.py)

Pure Python 3, standard library only. The file format code is tools/mtlib, from elektron-model-tweaks by
drumkilla (MIT). What is changed in the OS and why: Modded-Cycles' notes 17 to 20 (18nelli18), see
docs/MODEL-CYCLES-NOTES.md, section 5.
"""
import argparse
import hashlib
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mtlib import aplib, container                      # noqa: E402
from mtlib.syx import unwrap, wrap, BYTES_PER_MSG       # noqa: E402

# ---- the only firmware accepted ---------------------------------------------------------------------------
SYX_SHA256 = '44fe586269631a0ca7da25a3383fc6733c314809505fc3cc52f1e0ed9800640c'
MAIN_SHA256 = 'cc99d4f0175d34d1e91d046e6ec85a5e8ab58ab9edbb3c24406acd48cb99ee98'
BASE = 0x40000400                   # load address of the main OS (section 3)
IMAGE_LEN = 0x1a9d40                # its unpacked length
STAGE = 0x40200000                  # the bootstrap puts the packed OS here: the unpacked one must end below

# ---- the machines -----------------------------------------------------------------------------------------
# name: on the MACHINES screen, written like the stock ones (Kick, Snare...), 7 letters at most.
# knobs: COLOR, SHAPE, SWEEP, CONTOUR as (long name, short name, default). The screen shows the long name
# when a knob is turned, one word per line, words of 8 letters at most.
MACHINES = (
    dict(name='Plaits', update='macro_cycles_update', render='macro_cycles_render', decay=80,
         knobs=(('Plaits Engine', 'ENGN', 4), ('Plaits Harmonic', 'HARM', 64), ('Plaits Timbre', 'TIMB', 64),
                ('Plaits Morph', 'MRPH', 64))),
    dict(name='Sophie', update='sophie_cycles_update', render='sophie_cycles_render', decay=80,
         knobs=(('Sophie Model', 'MODL', 16), ('Sophie Metal', 'METL', 64), ('Sophie Sweep', 'SWEP', 64),
                ('Sophie Color', 'COLR', 64))),
)
STOCK, ADDED = 6, len(MACHINES)
NMACH = STOCK + ADDED               # 8
TOP = NMACH - 1                     # the highest machine number, 7

# ---- OS 1.13 (docs/MODEL-CYCLES-NOTES.md) -----------------------------------------------------------------
DESC, NDESC, DSIZE = 0x4010dce0, 76, 0x38       # parameter descriptors
NDESC_NEW = NDESC + 5 * ADDED                   # 86
SNARE_DESC, ALG_DESC = 51, 41                   # SNARE's five descriptors (our model); "Algorithm" = the machine
ROWS, CCROWS = 0x40a79418, 0x40a7ada4           # per-machine rows built at boot (6 x 32 bytes each)
NAMES = 0x401177e4                              # 6 machine names
RENDER_TAB, UPDATE_TAB, ENGINE_MAP = 0x40118610, 0x40118628, 0x40118640
BOOT_CLEAR = 0x400004b2                         # clears the BSS; its first 8 bytes become the boot hook
CAVE, CAVE_LEN = 0x4016cae8, 1024               # an all-0xFF sprite mask, freed for the boot hook's code
CAVE_PTR, SHARED_MASK, SHARED_LEN = 0x400b1106, 0x40154ae4, 1040   # its only user; an identical, larger mask
BSS_END = 0x423380b0                            # end of what the OS clears at boot
# Where the accessors of the descriptor table bound the index: "moveq #76" / "moveq #75" (Modded-Cycles'
# list, tools/gen_sdvintage_7th.py; 0x4005a50a, replaced whole here, is left out).
BOUNDS = (
    0x4000a93e, 0x4000a95e, 0x4000a984, 0x4000aa52, 0x4000b208, 0x4000b22a, 0x4000b3e4, 0x4000b476,
    0x4000b51a, 0x4000b65a, 0x4000b6ec, 0x4000b788, 0x4000b946, 0x4001d5e2, 0x4001d8ee, 0x4001d90e,
    0x4001e026, 0x4001f326, 0x40022a7c, 0x40022afe, 0x40029e78, 0x40029e98, 0x4002b430, 0x40046d5c,
    0x4004e31e, 0x4004e3ba, 0x4005a368, 0x4005a4e8, 0x4005a52c, 0x4005a556, 0x4005a582, 0x4005a5cc,
    0x4005a5fe, 0x4005a628, 0x4005a65c, 0x4005a76a, 0x4005a7aa, 0x4005a7d0, 0x4005a7f8, 0x4005a81a,
    0x4005a83c, 0x4005a85e,
)
# Opcodes that may come before a 32-bit address we move: lea abs.l,An / pea abs.l / move.l #,Dn /
# move.l abs.l,d0 / addi.l #,d0 / addi.l #,d1.
REF_OPCODES = {0x41f9, 0x43f9, 0x45f9, 0x47f9, 0x49f9, 0x4bf9, 0x4df9, 0x4879, 0x2c3c, 0x2039, 0x0680, 0x0681}


def die(msg):
    print('ERROR: ' + msg, file=sys.stderr)
    sys.exit(1)


def be32(x):
    return struct.pack('>I', x & 0xffffffff)


def sha(b):
    return hashlib.sha256(b).hexdigest()


# ---- reading the official file ----------------------------------------------------------------------------
def read_official(path):
    raw = open(path, 'rb').read()
    if sha(raw) != SYX_SHA256:
        die('%s is not the official Model:Cycles OS 1.13 file (model-cycles_OS1.13.syx, 890 016 bytes,\n'
            '       sha256 %s).\n       Nothing was written.' % (os.path.basename(path), SYX_SHA256))
    stream, info = unwrap(raw)
    cont = container.parse(stream)
    sec = {s['id']: s for s in cont['sections']}
    body = lambda s: cont['blob'][s['off']:s['off'] + s['size']]
    main, ops = aplib.depack(body(sec[3]))
    if sha(main) != MAIN_SHA256 or len(main) != IMAGE_LEN or sec[3]['attr'] != BASE:
        die('unexpected main OS inside the file')
    plain = []
    for s in cont['sections']:
        try:
            plain.append(aplib.depack(body(s))[0])
        except (ValueError, IndexError):
            plain.append(body(s))
    return dict(raw=raw, info=info, cont=cont, main=main, ops=ops, plain=plain)


# ---- our code ---------------------------------------------------------------------------------------------
def read_payload(folder):
    names = ('payload.bin', 'stub.bin', 'payload.sym')
    for n in names:
        if not os.path.isfile(os.path.join(folder, n)):
            die('%s not found in %s (run ./build.sh, or use the prebuilt/ folder of the repository)' % (n, folder))
    blob, stub, symtext = (open(os.path.join(folder, n), 'rb').read() for n in names)
    sums = os.path.join(folder, 'SHA256SUMS')
    if os.path.isfile(sums):
        want = dict(reversed(l.split()) for l in open(sums) if l.strip())
        for n, b in zip(names, (blob, stub, symtext)):
            if want.get(n) != sha(b):
                die('%s does not match %s' % (n, sums))
    sym = {}
    for line in symtext.decode('ascii').splitlines():
        a, _, n = line.split()
        sym[n] = int(a, 16)
    sym['ml_rows'] = sym['ml_rows_area'] + 32           # one empty row before the rows (machine_list.c)
    return blob, stub, sym


def build_payload(blob, sym, img):
    """The payload as the boot hook installs it: code, constants, the tables filled in, then zeros."""
    start, end = sym['_start'], sym['_end']
    u32 = lambda va: struct.unpack_from('>I', img, va - BASE)[0]
    if (sym['_payload_longs'] * 4 != end - start or sym['_payload_src'] != BASE + IMAGE_LEN
            or sym['ml_boot'] != CAVE or sym['_bss_start'] - start != len(blob) or start < BSS_END):
        die('payload symbols do not fit this tool')
    pay = bytearray(blob) + bytes(end - start - len(blob))

    def put(name, data, room):
        if len(data) > room:
            die('%s: %d bytes for %d' % (name, len(data), room))
        o = sym[name] - start
        pay[o:o + len(data)] = data

    # our names
    strings, where = bytearray(), {}
    for s in [m['name'] for m in MACHINES] + [k[i] for m in MACHINES for k in m['knobs'] for i in (0, 1)]:
        if s not in where:
            where[s] = sym['ml_strings'] + len(strings)
            strings += s.encode('ascii') + b'\0'
    put('ml_strings', strings, sym['_bss_start'] - sym['ml_strings'])
    # machine names and the two function tables: the six stock entries from the OS, then ours
    for name, src, ours in (('ml_names', NAMES, [where[m['name']] for m in MACHINES]),
                            ('ml_update', UPDATE_TAB, [sym[m['update']] for m in MACHINES]),
                            ('ml_render', RENDER_TAB, [sym[m['render']] for m in MACHINES])):
        put(name, b''.join(be32(u32(src + 4 * i)) for i in range(STOCK)) + b''.join(be32(x) for x in ours), 4 * NMACH)
    # descriptors: the OS's 76, with "Algorithm" going up to our last machine, then five per added machine
    # modelled on SNARE's (same slots, range, CCs 16-19, flags): four knobs and an Amp Decay
    table = bytearray(img[DESC - BASE:DESC - BASE + NDESC * DSIZE])
    amax = ALG_DESC * DSIZE + 0x0c
    if table[amax:amax + 4] != be32(5 << 8):
        die('unexpected "Algorithm" descriptor')
    table[amax:amax + 4] = be32(TOP << 8)
    snare = lambda k: bytearray(img[DESC - BASE + (SNARE_DESC + k) * DSIZE:][:DSIZE])
    for m in MACHINES:
        if not (m['name'].isalpha() and m['name'].isascii() and len(m['name']) <= 7):
            die('machine name %s' % m['name'])
        for k, (long_, short, default) in enumerate(m['knobs']):
            if max(len(w) for w in long_.split(' ')) > 8 or not 0 <= default <= 127:
                die('knob %s' % long_)
            e = snare(k)
            if e[0:4] != be32(1) or e[4:8] != be32(0x0b + k):
                die('unexpected SNARE descriptor')
            e[0x00:0x04] = be32(6)              # "belongs to one machine"; which one: ml_owner (machine_list.c)
            e[0x10:0x14] = be32(default << 8)
            e[0x2c:0x30] = be32(where[long_])
            e[0x34:0x38] = be32(where[short])
            table += e
        e = snare(4)                            # Amp Decay with this machine's default
        if e[0:4] != be32(7) or e[4:8] != be32(0x12):
            die('unexpected Amp Decay descriptor')
        e[0x10:0x14] = be32(m['decay'] << 8)
        table += e
    put('ml_desc', table, NDESC_NEW * DSIZE)
    return bytes(pay)


# ---- the changes to the OS --------------------------------------------------------------------------------
def patches(img, stub, sym):
    """[(address, expected bytes, new bytes, group, reason)]"""
    out = []
    at = lambda va, n: bytes(img[va - BASE:va - BASE + n])

    def w(va, old, new, group, why):
        old, new = (bytes.fromhex(x) if isinstance(x, str) else bytes(x) for x in (old, new))
        if len(old) != len(new):
            die('patch %#x: lengths' % va)
        if at(va, len(old)) != old:
            die('patch %#x: found %s, expected %s' % (va, at(va, len(old)).hex(), old.hex()))
        out.append((va, old, new, group, why))

    jmp = lambda name: b'\x4e\xf9' + be32(sym[name])

    # boot
    if len(stub) > CAVE_LEN or at(CAVE, CAVE_LEN) != b'\xff' * CAVE_LEN or at(SHARED_MASK, SHARED_LEN) != b'\xff' * SHARED_LEN:
        die('unexpected sprite masks')
    w(CAVE, b'\xff' * len(stub), stub, 'boot', 'boot hook code, in a sprite mask that is all 0xFF')
    w(CAVE_PTR, be32(CAVE), be32(SHARED_MASK), 'boot', 'that sprite now reads an identical all-0xFF mask')
    w(BOOT_CLEAR, '4feffff048d700f0', jmp('ml_boot') + b'\x4e\x71', 'boot',
      'BSS clear: jump to the boot hook, which copies the payload to %#x first' % sym['_start'])

    # tables that had to grow: every 32-bit reference to the old one now points at ours
    moved = ((DESC, 'ml_desc', 0, 34, 'parameter descriptors, 76 -> %d' % NDESC_NEW),
             (DESC + 8, 'ml_desc', 8, 1, 'parameter descriptors (field +8)'),
             (DESC + 0x20, 'ml_desc', 0x20, 2, 'parameter descriptors (field +0x20)'),
             (ROWS, 'ml_rows', 0, 5, 'machine/knob rows, 6 -> %d machines' % NMACH),
             (CCROWS, 'ml_ccrows', 0, 2, 'machine/CC rows, 6 -> %d machines' % NMACH),
             (NAMES, 'ml_names', 0, 1, 'machine names (MACHINES screen)'),
             (UPDATE_TAB, 'ml_update', 0, 1, 'voice loop: update functions'),
             (RENDER_TAB, 'ml_render', 0, 1, 'voice loop: render functions'))
    for old, name, off, count, why in moved:
        refs, i = [], img.find(be32(old))
        while i >= 0:
            if i % 2 == 0:
                refs.append(BASE + i)
            i = img.find(be32(old), i + 1)
        if len(refs) != count:
            die('%d references to %#x, expected %d' % (len(refs), old, count))
        for va in refs:
            if struct.unpack('>H', at(va - 2, 2))[0] not in REF_OPCODES:
                die('reference to %#x at %#x: unexpected instruction' % (old, va))
            w(va, be32(old), be32(sym[name] + off), 'tables', why)

    # the descriptor count in the table's accessors
    for va in BOUNDS:
        op, n = at(va, 2)
        if op & 0xf1 != 0x70 or n not in (75, 76):
            die('%#x is not moveq #75 / #76' % va)
        w(va, bytes((op, n)), bytes((op, n + 5 * ADDED)), 'descriptor count', 'moveq #%d -> #%d' % (n, n + 5 * ADDED))

    # the machine count
    t = '%02x' % TOP
    for va, old, new, why in (
            (0x400a7dba, '7205', '72' + t, 'voice loop: highest machine at a trig'),
            (0x400a7df4, '7005', '70' + t, 'voice loop: highest machine that is rendered'),
            (ENGINE_MAP + 6, '0000', '0607', 'voice loop: machines 6 and 7 use entries 6 and 7 of the tables'),
            (0x4005a2b8, '487800c0', '4878%04x' % (32 * NMACH), 'table builder: clear %d rows' % NMACH),
            (0x4005a572, '7205', '7206', 'a descriptor belongs to one machine if its field is <= 6'),
            (0x4005a6a6, '7205', '72' + t, 'machine, knob -> descriptor: highest machine'),
            (0x4005a8f6, 'b4806522143c0007', '74' + t + 'b48065204e71',
             'track, machine, CC -> descriptor: highest machine (same test, the 7 loaded before it)'),
            (0x400147a4, '7005', '70' + t, "setting a track's machine: highest machine"),
            (0x400148aa, '7205', '72' + t, 'MACHINES wheel: highest machine (compare)'),
            (0x400148b2, '7005', '70' + t, 'MACHINES wheel: highest machine (value)'),
            (0x400a25e0, '7005', '70' + t, 'MACHINES screen: highest machine with a name'),
            (0x400a26a2, '7850', '7849', 'MACHINES screen: position marks start 7 pixels to the left'),
            (0x400a26e8, '7006', '70%02x' % NMACH, 'MACHINES screen: %d position marks' % NMACH)):
        w(va, old, new, 'machine count', why)

    # functions and instructions replaced by ours
    for va, old, name, why in (
            (0x4004df40, '704c222f0004', 'ml_state_at_entry', "descriptor -> state object: ours use SNARE's"),
            (0x4004dfa2, '704c222f0004', 'ml_state_connect_entry', 'same, the variant that connects'),
            (0x4004df5c, '7206202f0004', 'ml_record_at_entry', 'record number -> per-machine record: two more'),
            (0x4004df76, '7205202f0004', 'ml_record_of_entry', 'machine -> per-machine record: two more'),
            (0x4005a50a, '724c202f0004', 'ml_desc_machine_entry', 'descriptor -> its machine'),
            (0x4005a340, '7005b085643e', 'ml_builder_row', "table builder: our descriptors go in their machine's row"),
            (0x400a2638, 'eb8c48780001', 'ml_icon_index', 'MACHINES screen: picture number (ours show CHORD\'s)')):
        w(va, old, jmp(name), 'detours', why)
    w(0x4001e8da, '202f0020226a0068', b'\x4e\xb9' + be32(sym['ml_knob_vec']) + b'\x4e\x71', 'detours',
      'main screen, knob -> descriptor: record numbers for our machines')

    out.sort()
    for a, b in zip(out, out[1:]):
        if a[0] + len(a[1]) > b[0]:
            die('patches overlap at %#x' % b[0])
    return out


# ---- packing ----------------------------------------------------------------------------------------------
def pack_grown(data, ops, dirty, old_len):
    """aPLib stream for data: the original stream re-emitted for data[:old_len] (mtlib's method: an op that
    reads or writes a changed byte becomes literals), then data[old_len:] packed here with a plain greedy
    search for matches of 4 bytes or more inside the added part."""
    w = aplib._Writer()
    last = 1
    for kind, pos, off, n in ops:
        if kind == aplib.LITERAL:
            w.literal(data[pos])
        elif dirty.find(1, pos, pos + n) >= 0 or dirty.find(1, pos - off, pos - off + n) >= 0:
            for k in range(pos, pos + n):
                w.literal(data[k])
        else:
            w.match(off, n, last)
            last = off
    seen, i, end = {}, old_len, len(data)
    while i < end:
        key = data[i:i + 4]
        j = seen.get(key) if len(key) == 4 else None
        n = 0
        if j is not None:
            n = 4
            while i + n < end and n < 0x4000 and data[j + n] == data[i + n]:
                n += 1
        if n:
            w.match(i - j, n, last)
            last = i - j
        else:
            w.literal(data[i])
            n = 1
        for k in range(i, min(i + n, end - 3)):
            seen[data[k:k + 4]] = k
        i += n
    w.end()
    body = w.o
    body[0:4] = (len(body) - aplib.SECT_HDR).to_bytes(4, 'big')
    body[4:8] = (sum(body[aplib.SECT_HDR:]) & 0xffffffff).to_bytes(4, 'big')
    return bytes(body)


def make(fw, new_main, dirty):
    packed = pack_grown(new_main, fw['ops'], dirty, IMAGE_LEN)
    if aplib.depack(packed)[0] != new_main:
        die('internal: the packed OS does not unpack to itself')
    cont = fw['cont']
    blob = cont['blob']
    key = container.find_key(fw['plain'], blob[:-container.DIGEST_LEN], blob[-container.DIGEST_LEN:])
    if key is None:
        die('could not derive the trailer key from the official file')
    new_blob = container.rebuild(cont, {3: packed}, key)
    return wrap(container.build_stream(new_blob, BYTES_PER_MSG), fw['info']['product'], fw['info']['start_seq'])


def check(syx, fw, new_main):
    """Read the finished file back from scratch and check everything that can be checked."""
    stream, info = unwrap(syx)                              # every message checksum
    cont = container.parse(stream)
    blob = cont['blob']
    ok = info['product'] == fw['info']['product'] and cont['version'] == fw['cont']['version']
    ok &= int.from_bytes(stream[0:4], 'big') == len(blob)
    ok &= int.from_bytes(stream[4:8], 'big') == container.content_checksum(blob)
    old = {s['id']: s for s in fw['cont']['sections']}
    plain = []
    for s in cont['sections']:
        body = blob[s['off']:s['off'] + s['size']]
        o = old[s['id']]
        ok &= s['attr'] == o['attr']
        if s['id'] == 3:
            ok &= int.from_bytes(body[0:4], 'big') == len(body) - 8
            ok &= int.from_bytes(body[4:8], 'big') == sum(body[8:]) & 0xffffffff
            ok &= aplib.depack(body)[0] == new_main
            plain.append(new_main)
        else:
            ok &= body == fw['cont']['blob'][o['off']:o['off'] + o['size']]
            plain.append(fw['plain'][o['index']])
    ok &= container.find_key(plain, blob[:-container.DIGEST_LEN], blob[-container.DIGEST_LEN:]) is not None
    return bool(ok)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('official', help='your official model-cycles_OS1.13.syx')
    ap.add_argument('-o', '--output', default='cycles_plaits_sophie_beta.syx')
    ap.add_argument('--payload', default=os.path.join(HERE, '..', 'prebuilt'))
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--report')
    args = ap.parse_args()

    fw = read_official(args.official)
    img = fw['main']
    blob, stub, sym = read_payload(args.payload)
    payload = build_payload(blob, sym, img)
    writes = patches(img, stub, sym)

    new = bytearray(img)
    dirty = bytearray(len(img))
    for va, old, data, _, _ in writes:
        new[va - BASE:va - BASE + len(data)] = data
        dirty[va - BASE:va - BASE + len(data)] = b'\x01' * len(data)
    new_main = bytes(new) + payload
    if BASE + len(new_main) > STAGE:
        die('the OS would end at %#x, past %#x' % (BASE + len(new_main), STAGE))

    syx = make(fw, new_main, dirty)
    if not check(syx, fw, new_main):
        die('the finished file failed its checks. Nothing was written.')
    open(args.output, 'wb').write(syx)

    if args.list:
        group, order = None, ['boot', 'tables', 'descriptor count', 'machine count', 'detours']
        for va, old, data, g, why in sorted(writes, key=lambda w: (order.index(w[3]), w[0])):
            if g != group:
                group = g
                print('\n  %s (%d)' % (g, sum(1 for w in writes if w[3] == g)))
            show = lambda b: b.hex() if len(b) <= 8 else '%s... (%d bytes)' % (b[:4].hex(), len(b))
            print('    %08x  %-18s -> %-26s %s' % (va, show(old), show(data), why))
        print()
    if args.report:
        json.dump(dict(
            official_sha256=SYX_SHA256, main_os_sha256=sha(new_main), syx_sha256=sha(syx),
            image_len=IMAGE_LEN, payload_at=sym['_start'], payload_len=len(payload), payload_file_len=len(blob),
            payload_sha256=sha(payload), symbols={k: v for k, v in sym.items()},
            machines=[dict(m, index=STOCK + i, knobs=[list(k) for k in m['knobs']]) for i, m in enumerate(MACHINES)],
            writes=[dict(at=va, old=old.hex(), new=data.hex(), group=g, why=why) for va, old, data, g, why in writes],
        ), open(args.report, 'w'), indent=1)

    changed = sum(len(w[1]) for w in writes)
    print('Model:Cycles OS 1.13 + %s' % ', '.join('%s (machine %d)' % (m['name'], STOCK + 1 + i) for i, m in enumerate(MACHINES)))
    print('  %d changes in the OS (%d bytes), payload %d bytes at %#x, OS now ends at %#x'
          % (len(writes), changed, len(payload), sym['_start'], BASE + len(new_main)))
    print('  file checked: message checksums, content checksum, section sum, HMAC trailer, OS unpacks as built')
    print('  main OS sha256 %s' % sha(new_main))
    print('  wrote %s (%d bytes)' % (args.output, len(syx)))
    print('  sha256 %s' % sha(syx))
    print('BETA, NOT TESTED ON HARDWARE: read docs/BETA-TEST.md before flashing.')


if __name__ == '__main__':
    main()
