#!/usr/bin/env python3
"""Stress the MACRO machine with an engine switch on every trig, in the emulated Model:Cycles voice loop.

Background: on the Digitakt mk1, heavy parameter-locking of MACRO's engine knob is reported to freeze the
unit. This test looks for what could do that on the Cycles: a block that never ends, a memory access gone
astray, or a block whose cost jumps when the engine changes.

Every trig picks a random engine, random HARMONICS / TIMBRE / MORPH, a random note and a random gap to the
next trig (1 to 6 blocks, so notes are cut short). For every block it counts the instructions executed and
keeps the worst note-start block per (previous engine -> new engine).

    python3 test/stress_engine_switch.py --modded PATH/TO/Modded-Cycles --cycles model-cycles_OS1.13.syx \
        [--trigs 2000] [--seed 1] [--fast]

--fast as in play_machines.py (a Unicorn with digiemu's patches). Counting instructions is slow either way.
"""
import argparse
import os
import random
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
BUILD = os.path.join(HERE, '..', 'build')
DST = 0x43000000
RENDER_TAB, UPDATE_TAB = 0x40118610, 0x40118628
SLOT = 1
ENGINES = ['WSHAPE', '2OP FM', 'NOISE', 'PARTCL', 'BDRUM', 'SNARE', 'HIHAT', 'GRAIN']
BLOCK_LIMIT = 2_000_000                     # instructions; a normal block is under 12 000


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--modded', required=True)
    ap.add_argument('--cycles', required=True)
    ap.add_argument('--trigs', type=int, default=2000)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--fast', action='store_true')
    args = ap.parse_args()

    sys.path.insert(0, os.path.join(args.modded, 'tools'))
    from mtlib import aplib, container
    from mtlib.syx import unwrap
    stream, _ = unwrap(open(args.cycles, 'rb').read())
    c = container.parse(stream)
    s3 = {s['id']: s for s in c['sections']}[3]
    img0 = aplib.depack(c['blob'][s3['off']:s3['off'] + s3['size']])[0]

    sys.path.insert(0, os.path.join(args.modded, 'tools', 'emu'))
    import numpy as np
    import emac
    import mcengine
    from unicorn import UC_HOOK_CODE
    from unicorn import m68k_const as mk

    if args.fast:
        emac.EMAC.install = lambda self, instrs: 0
        mcengine._emac_instrs = lambda main_os, ranges: {}
        mcengine._emac_payload = lambda payload, dst=mcengine.PAYLOAD_DST: {}
        mcengine.mk.UC_CPU_M68K_ANY = mcengine.mk.UC_CPU_M68K_CFV4E
    else:
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

    sym = {}
    for line in open(os.path.join(BUILD, 'macro.sym')):
        a, _, n = line.split()
        sym[n] = int(a, 16)
    blob = open(os.path.join(BUILD, 'macro.bin'), 'rb').read()
    blob += bytes(sym['_end'] - DST - len(blob))
    img = bytearray(img0)
    struct.pack_into('>I', img, RENDER_TAB + 4 * SLOT - mcengine.BASE, sym['macro_cycles_render'])
    struct.pack_into('>I', img, UPDATE_TAB + 4 * SLOT - mcengine.BASE, sym['macro_cycles_update'])
    mcengine.PAYLOAD_CODE = ((DST, sym['_code_end']),)
    mcengine.SRAM_CODE = (DST + 0x10000000, 0, 0)
    eng = mcengine.Engine(bytes(img), payload=(DST, blob))
    eng.solo(0)
    eng.set(0, machine=SLOT, decay=100, punch=0)

    count = [0]

    def tick(uc, addr, size, ud):
        count[0] += 1
        if count[0] > BLOCK_LIMIT:
            uc.emu_stop()
    eng.uc.hook_add(UC_HOOK_CODE, tick)

    # A note starts in the block AFTER the one where the trig is asked for: the voice loop hands the trig to
    # the machine one block late (v + 0x38), and the machine reads the engine knob then. So the cost of a
    # switch is the cost of that block, and the engine switched to is the one the knob shows in that block.
    rnd = random.Random(args.seed)
    worst = {}                               # (previous engine, new engine) -> (instructions, knobs)
    worst_any = (0, None)
    hung, total_blocks, peak = [], 0, 0.0
    sounding = None                          # the engine of the note that last started
    asked = False                            # a trig was asked for in the previous block
    for t in range(args.trigs):
        e = rnd.randrange(8)
        knobs = dict(color=8 * e + rnd.randrange(8), shape=rnd.randrange(128), sweep=rnd.randrange(128),
                     contour=rnd.randrange(128), note=rnd.randrange(24, 97))
        eng.set(0, **knobs)
        for b in range(rnd.randrange(1, 7)):
            if b:                            # knobs keep moving between trigs too
                eng.set(0, shape=rnd.randrange(128), sweep=rnd.randrange(128), contour=rnd.randrange(128))
            count[0] = 0
            x = eng.block(1 if b == 0 else 0)[0]
            total_blocks += 1
            n = count[0]
            peak = max(peak, float(np.max(np.abs(x))) / 2**31)
            if n > BLOCK_LIMIT or eng.unmapped:
                hung.append((t, b, sounding, e, n, knobs, list(eng.unmapped[:3])))
                break
            if n > worst_any[0]:
                worst_any = (n, (t, b, sounding, e, knobs))
            if asked:                        # this block starts a note, on engine e
                if n > worst.get((sounding, e), (0,))[0]:
                    worst[(sounding, e)] = (n, knobs)
                sounding = e
            asked = b == 0
        if hung:
            break

    print('%d trigs, %d blocks, seed %d; peak output %.3f of full scale' % (t + 1, total_blocks, args.seed, peak))
    if hung:
        t, b, p, e, n, knobs, um = hung[0]
        print('FAILED at trig %d, block %d after it: %s -> %s, %d instructions, knobs %s, unmapped %s'
              % (t, b, ENGINES[p] if p is not None else '-', ENGINES[e], n, knobs,
                 ['pc %08x addr %08x' % u for u in um]))
        sys.exit(1)
    n, (t, b, p, e, knobs) = worst_any
    print('worst block: %d instructions (trig %d, block %d after it, sounding %s, knob on %s, %s)'
          % (n, t, b, ENGINES[p] if p is not None else '-', ENGINES[e], knobs))
    print('\nworst note-start block, instructions, by engine switched to (rows: from, columns: to):')
    print('%-7s' % '' + ''.join('%8s' % x[:7] for x in ENGINES))
    for p in range(8):
        print('%-7s' % ENGINES[p][:7] + ''.join('%8d' % worst.get((p, e), (0,))[0] for e in range(8)))
    print('\nno block ran away, no stray memory access')


main()
