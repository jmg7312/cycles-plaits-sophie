# MACRO and Sophie machines for the Elektron Model:Cycles

Two extra synth machines for the Model:Cycles (OS 1.13), twelve engines in all: **MACRO**, the eight
engines of digi1_mods' machine of that name (ported from Plaits), and **SOPHIE**, with its four models.
They run inside the Cycles' own voice loop next to the stock FM machines.

> **Status: emulation only. This has NOT been flashed to or tested on a real Model:Cycles.**
> Everything below was measured in [Modded-Cycles](https://github.com/18nelli18/Modded-Cycles)' emulation
> bench (`tools/emu/mcengine.py`), which runs the real OS 1.13 voice loop from your own OS file.
> Unofficial; not affiliated with, endorsed by or supported by Elektron.

## What this is, and what it is not

The synthesis code is not ours. It already exists for this CPU (ColdFire MCF5441x, no FPU), made for the
Digitakt mk1:

- **MACRO**: `macro.c` from [digi1_mods](https://github.com/gdeo607/digi1_mods) (MIT), engines ported to
  fixed point from [Plaits](https://github.com/pichenettes/eurorack) by Emilie Gillet (MIT). The machines
  keep the names digi1_mods gave them.
- **Sophie**: `sophie.c` from [digisophie](https://github.com/soejrd/digisophie) (MIT), a fixed-point
  adaptation of [Sophie for Schwung](https://github.com/mestela/schwung-sophie) by Matt Estela (MIT).

Both are copied here **unmodified** (`machines/*/third_party/`, with their licences), so the build needs
nothing else.

What this repository adds is the **adapter** between that code and the Model:Cycles machine contract
(`update(pmod, voice, params)` once per 32-sample block, then `render(out, voice)`), two short C files:

- `machines/macro/macro_cycles.c`
- `machines/sophie/sophie_cycles.c`

They read the track's knobs, compute the pitch the way the stock pitch code does (note + PITCH + FINE
TUNE), call the engine, and then run the **stock** amp envelope, VCA and PUNCH stage, set up as the stock
TONE machine sets them up. So DECAY, PUNCH and GATE behave as on any stock machine.

**What is missing:** adding the machines to the OS's machine list (names, knob descriptors, MACHINES
screen). Existing mods already do that for their own machines (Modded-Cycles for its Syntakt engines,
Model-TG for its Sampler); the same has to be done for these. Nothing here builds a flashable firmware,
and where this code should end up is an open question.

**For loader and firmware authors:** [docs/MODEL-CYCLES-NOTES.md](docs/MODEL-CYCLES-NOTES.md) gathers what
we know about the Model:Cycles OS 1.13 (file format, a draft device profile, memory map, the machine
tables and contract, UI and MIDI entry points, what existing mods occupy), each fact with its source.

## The machines

Two machines. In each, **the COLOR knob picks the engine**, so a parameter lock on COLOR changes the engine
per step. This follows digi1_mods' MACRO on the Digitakt, where the first machine knob does the same. The
reason is a limit of the OS: with the known method, about ten machines can be added in all, every mod
together (see [docs/MODEL-CYCLES-NOTES.md](docs/MODEL-CYCLES-NOTES.md), section 5), so a family of engines
shares one machine.

| Machine | COLOR value | Engine |
|---|---|---|
| MACRO | 0-7 | WSHAPE, waveshaping oscillator |
| | 8-15 | 2OP FM, two-operator FM |
| | 16-23 | NOISE, filtered clocked noise |
| | 24-31 | PARTCL, particle noise |
| | 32-39 | BDRUM, bass drum |
| | 40-47 | SNARE, snare drum |
| | 48-55 | HIHAT, hi-hat |
| | 56-127 | GRAIN, granular formant oscillator |
| SOPHIE | 0-31 | FUSE |
| | 32-63 | BOOM |
| | 64-95 | PIPE |
| | 96-127 | SHARD |

MACRO's zones are digi1_mods' (eight values per engine, the last engine filling the rest, so a saved value
keeps its engine when engines are added). The engine is read at each note start.

### Knobs

| Knob | MACRO | SOPHIE |
|---|---|---|
| PITCH | pitch (as stock) | pitch (as stock) |
| DECAY | amp decay (stock envelope) | amp decay (stock envelope) |
| COLOR | **ENGN**: the engine | **MODEL**: the model |
| SHAPE | **HARMONICS** | **METAL** |
| SWEEP | **TIMBRE** | **SWEEP** (bipolar, 64 = centre) |
| CONTOUR | **MORPH** | **COLOR** (Sophie's own: inharmonic character) |
| PUNCH, GATE | as stock | as stock |

Not mapped yet: MACRO's **AUX** output (the engines play their OUT); Sophie's **FBK** (fixed at 32), **FOLD**
(its wavefolder, off) and velocity (fixed at 127). The plan is a second layer on the knobs, hold PRESET MENU
and turn one, the way Model-TG puts Attack on DECAY.

## Measurements (emulation)

Note 60, default knobs (all at 64, COLOR in the middle of the engine's zone), DECAY 80. The cost table was
measured with one machine per engine, before the engines were grouped; the grouped machines run the same
engine code.

**Cost**: instructions per 32-sample block for one voice, counted in the emulated voice loop (the loop
alone, with no voice, is 1610). It is an instruction count, not a time on hardware.

| Stock machine | | MACRO | | Sophie | |
|---|---|---|---|---|---|
| TONE | 5291 | WSHAPE | 5343 | FUSE | 5579 |
| PERC | 6079 | NOISE | 5390 | PIPE | 5780 |
| METAL | 6431 | 2OP FM | 5463 | BOOM | 5932 |
| SNARE | 7157 | SNARE | 6813 | SHARD | 6447 |
| KICK | 7416 | GRAIN | 7428 | | |
| CHORD | 8294 | HIHAT | 7656 | | |
| | | BDRUM | 8187 | | |
| | | PARTCL | 9193 | | |

**Level**: peak after the stock amp chain, as a fraction of full scale. Stock machines 0.076-0.212;
MACRO machines 0.044-0.125; Sophie machines 0.055-0.068.

**Pitch**: note 60 plays 262-264 Hz (expected 261.6; the measurement is to the nearest sample period).
PITCH +12 gives 522 Hz, -12 gives 131 Hz; FINE TUNE +32 is one semitone.

**Size**: MACRO 38 kB of code, 7.6 kB of tables, 1.7 kB of state for six voices. Sophie 4.5 kB of code,
2.6 kB of tables, 0.6 kB of state. Both modules are linked at `0x43000000`, the free SDRAM above the OS's
BSS that Modded-Cycles uses for its payload.

## Build

```sh
sudo apt install gcc-m68k-linux-gnu binutils-m68k-linux-gnu     # Debian / Ubuntu / WSL
./build.sh
```

Output: `build/macro.{elf,bin,sym}` and `build/sophie.{elf,bin,sym}`. `CROSS=m68k-elf- ./build.sh` uses
another toolchain prefix. Flags: `-mcpu=54418 -O2 -ffreestanding -nostdlib`, as Modded-Cycles builds its
own C machines.

## Test

You need a checkout of Modded-Cycles (for its bench) and your own official `model-cycles_OS1.13.syx`.
No firmware is included here and none is written.

```sh
pip install numpy unicorn
python3 test/play_machines.py --modded ../Modded-Cycles --cycles model-cycles_OS1.13.syx
```

In the emulated memory only, each machine takes SNARE's place in the OS's two machine tables and the
module is loaded at `0x43000000`. For each of the twelve engines the test plays a 0.5 s note, writes
`out/<machine>-<engine>.wav`, and checks that it sounds, that no memory access went astray, and (for the pitched
ones) that the note is in tune. `--cost` adds the instruction counts above. The `.wav` files are normalised,
so they do not show the level; the printed peak does.

With a stock Unicorn the bench emulates the EMAC in Python and is slow: about a minute per machine.
`--fast` is for a Unicorn built with [digiemu](https://github.com/irpina/digiemu)'s patches
(`tools/install-patched-unicorn.sh` there): the EMAC then runs natively, the output is bit-identical, and
the whole test takes a few seconds.

One thing the bench needed: its Python EMAC does not know `move.l ACCext01,Dn`, which `macro.c` uses
to save and restore the EMAC state around its own use. The test adds it at run time; `mcengine.py` and
`emac.py` are not modified.

## Layout

```
machines/macro/macro_cycles.c        the MACRO adapter
machines/macro/link.ld
machines/macro/third_party/digi1_mods/    macro.c, mono.c and their headers, unmodified (MIT)
machines/sophie/sophie_cycles.c      the Sophie adapter
machines/sophie/link.ld
machines/sophie/third_party/digisophie/   sophie.c and its headers, unmodified (MIT)
build.sh
test/play_machines.py
docs/MODEL-CYCLES-NOTES.md           notes on the OS for loader and firmware authors
THIRD_PARTY.md
```

`mono.c` is there for one function, `mono_pitch_inc()` (pitch to phase step); the linker drops the rest.

## Licence

The adapters, scripts and documentation of this repository: MIT, see [LICENSE](LICENSE).
The third-party code keeps its own licences: see [THIRD_PARTY.md](THIRD_PARTY.md).
