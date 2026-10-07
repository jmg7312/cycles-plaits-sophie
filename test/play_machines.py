#!/usr/bin/env python3
"""Play the Plaits and Sophie machines in the real Model:Cycles voice loop, emulated.

It uses Modded-Cycles' own bench, tools/emu/mcengine.py, unmodified. In the emulated memory only, each
machine takes SNARE's place in the OS's two machine tables (render 0x40118614, update 0x4011862c) and the
module is loaded at 0x43000000. No firmware file is written, and nothing here contains Elektron code: the
MAIN OS is read from YOUR official model-cycles_OS1.13.syx.

    python3 test/play_machines.py --modded PATH/TO/Modded-Cycles --cycles model-cycles_OS1.13.syx [--cost] [--fast]

For each of the 12 engines (Plaits' eight, Sophie's four models; the COLOR knob picks one): a 0.5 s note
(note 60, default knobs) written to out/<machine>-<engine>.wav, its peak level, and for the pitched ones the
measured frequency.

--cost  also counts the instructions per 32-sample block for one voice, for every machine here and for the
        six stock machines (slow).
--fast  for a Unicorn built with digiemu's patches (github.com/irpina/digiemu, patches/): it runs the EMAC
        natively, so the bench's Python EMAC is switched off and the CPU model is CFV4E. About 500 times
        faster, bit-identical output. Do not use it with a stock Unicorn: the EMAC would be wrong.

Needs: numpy, unicorn, and m68k-linux-gnu-objdump on the PATH (the bench uses it, unless --fast).
"""
import argparse
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, '..', 'build')
DST = 0x43000000
RENDER_TAB, UPDATE_TAB = 0x40118610, 0x40118628
SLOT = 1                                    # SNARE's index in the machine tables
IDLE_LOOP = None

PLAITS_ENGINES = [('WSHAPE', 'wshape'), ('2OP FM', '2opfm'), ('NOISE', 'noise'), ('PARTCL', 'partcl'),
          ('BDRUM', 'bdrum'), ('SNARE', 'snare'), ('HIHAT', 'hihat'), ('GRAIN', 'grain')]
SOPHIE_ENGINES = ['fuse', 'boom', 'pipe', 'shard']
PITCHED = {'WSHAPE', '2OP FM', 'GRAIN'}


def main_os(modded, syx):
    """The decompressed MAIN OS (section 3) of the official .syx, with Modded-Cycles' mtlib."""
    sys.path.insert(0, os.path.join(modded, 'tools'))
    from mtlib import aplib, container
    from mtlib.syx import unwrap
    stream, _ = unwrap(open(syx, 'rb').read())
    c = container.parse(stream)
    s3 = {s['id']: s for s in c['sections']}[3]
    return aplib.depack(c['blob'][s3['off']:s3['off'] + s3['size']])[0]


def load(name):
    sym = {}
    for line in open(os.path.join(BUILD, name + '.sym')):
        a, _, n = line.split()
        sym[n] = int(a, 16)
    blob = open(os.path.join(BUILD, name + '.bin'), 'rb').read()
    return sym, blob + bytes(sym['_end'] - DST - len(blob))


def frequency(x, np):
    y = np.asarray(x[2400:2400 + 8192], dtype=float)
    y = y - y.mean()
    ac = np.correlate(y, y, 'full')[len(y) - 1:]
    lo, hi = 48000 // 2500, 48000 // 30
    return 48000.0 / (lo + int(np.argmax(ac[lo:hi])))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--modded', required=True, help='a checkout of github.com/18nelli18/Modded-Cycles')
    ap.add_argument('--cycles', required=True, help='the official model-cycles_OS1.13.syx')
    ap.add_argument('--out', default=os.path.join(HERE, '..', 'out'))
    ap.add_argument('--cost', action='store_true')
    ap.add_argument('--fast', action='store_true')
    args = ap.parse_args()

    img0 = main_os(args.modded, args.cycles)
    sys.path.insert(0, os.path.join(args.modded, 'tools', 'emu'))
    import numpy as np
    import emac
    import mcengine
    from unicorn import m68k_const as mk

    if args.fast:
        emac.EMAC.install = lambda self, instrs: 0
        mcengine._emac_instrs = lambda main_os, ranges: {}
        mcengine._emac_payload = lambda payload, dst=mcengine.PAYLOAD_DST: {}
        mcengine.mk.UC_CPU_M68K_ANY = mcengine.mk.UC_CPU_M68K_CFV4E
    else:
        # The bench's Python EMAC does not know "move.l ACCext01 <-> Dn", which macro.c uses to save
        # and restore the EMAC around its own use. Added here, not in the bench: the value is kept as is.
        slow = emac.EMAC._slow

        def _slow(self, uc, addr):
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

    def engine(blob, sym, update, render):
        img = bytearray(img0)
        struct.pack_into('>I', img, RENDER_TAB + 4 * SLOT - mcengine.BASE, render)
        struct.pack_into('>I', img, UPDATE_TAB + 4 * SLOT - mcengine.BASE, update)
        mcengine.PAYLOAD_CODE = ((DST, sym['_code_end']),)
        mcengine.SRAM_CODE = (DST + 0x10000000, 0, 0)       # no second code area
        eng = mcengine.Engine(bytes(img), payload=(DST, blob))
        eng.solo(0)
        return eng

    cases = []
    psym, pblob = load('macro')
    for n, (label, fn) in enumerate(PLAITS_ENGINES):          # COLOR picks the engine, in zones of 8
        cases.append(('Plaits', label, pblob, psym, psym['macro_cycles_update'], psym['macro_cycles_render'],
                      dict(color=8 * n + 4, shape=64, sweep=64, contour=64, decay=80)))
    ssym, sblob = load('sophie')
    for n, m in enumerate(SOPHIE_ENGINES):                   # COLOR picks the model, in zones of 32
        cases.append(('Sophie', m.upper(), sblob, ssym, ssym['sophie_cycles_update'], ssym['sophie_cycles_render'],
                      dict(color=32 * n + 16, shape=64, sweep=64, contour=64, decay=80)))

    os.makedirs(args.out, exist_ok=True)
    failed = 0
    print('%-7s %-7s  %6s  %9s  %s' % ('machine', 'engine', 'peak', 'frequency', 'emulation'))
    for name, tag, blob, sym, up, re, knobs in cases:
        eng = engine(blob, sym, up, re)
        eng.set(0, machine=SLOT, note=60, punch=0, **knobs)
        t0 = time.time()
        x = eng.render(750, trig_at=(0,), track=0)
        dt = time.time() - t0
        peak = float(np.max(np.abs(x))) / 2**31
        f = frequency(x, np) if tag in PITCHED else None
        ok = peak > 0.01 and not eng.unmapped and (f is None or abs(f / 261.63 - 1) < 0.015)
        failed += not ok
        mcengine.wav(os.path.join(args.out, (name + '-' + tag.replace(' ', '') + '.wav').lower()), x)
        print('%-7s %-7s  %6.3f  %9s  %.2f s%s' % (name, tag, peak, ('%.1f Hz' % f) if f else '-', dt,
                                                 '' if ok else '   <-- FAILED (unmapped accesses: %d)' % len(eng.unmapped)))

    if args.cost:
        def cost(make):
            eng = make()
            eng.render(4, trig_at=(0,), track=0)
            eng.count_instructions()
            eng.render(20, trig_at=(), track=0)
            return eng.instructions / 20

        def stock(m):
            eng = mcengine.Engine(img0)
            eng.machine_defaults(0, m)
            eng.set(0, note=60)
            eng.solo(0)
            return eng

        def silent():
            eng = mcengine.Engine(img0)
            for t in range(6):
                eng.uc.mem_write(mcengine.VOICE0 + t * mcengine.VSTRIDE, struct.pack('>I', 6))
            return eng
        idle = cost(silent)
        print('\ninstructions per 32-sample block, one voice (the voice loop alone: %.0f)' % idle)
        for nm, m in mcengine.MACH.items():
            print('  stock %-8s %6.0f' % (nm, cost(lambda m=m: stock(m)) - idle))
        for name, tag, blob, sym, up, re, knobs in cases:
            def make(blob=blob, sym=sym, up=up, re=re, knobs=knobs):
                eng = engine(blob, sym, up, re)
                eng.set(0, machine=SLOT, note=60, punch=0, **knobs)
                return eng
            print('  %-14s %6.0f' % (name + ' ' + tag, cost(make) - idle))

    print('\n%d machine runs, %d failed; .wav files in %s' % (len(cases), failed, os.path.abspath(args.out)))
    sys.exit(1 if failed else 0)


main()
