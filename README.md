# Plaits and Sophie machines for the Elektron Model:Cycles

Twelve extra synth machines for the Model:Cycles (OS 1.13): the eight engines of **Plaits** and the four
models of **Sophie**, running inside the Cycles' own voice loop next to the stock FM machines.

> **Status: emulation only. This has NOT been flashed to or tested on a real Model:Cycles.**
> Everything below was measured in [Modded-Cycles](https://github.com/18nelli18/Modded-Cycles)' emulation
> bench (`tools/emu/mcengine.py`), which runs the real OS 1.13 voice loop from your own OS file.
> Unofficial; not affiliated with, endorsed by or supported by Elektron.

## What this is, and what it is not

The synthesis code is not ours. People already ported Plaits and Sophie to this CPU (ColdFire MCF5441x,
no FPU) for the Digitakt mk1:

- **Plaits**: `macro.c` from [digi1_mods](https://github.com/gdeo607/digi1_mods) (MIT), a fixed-point port
  of [Plaits](https://github.com/pichenettes/eurorack) by Emilie Gillet (MIT).
- **Sophie**: `sophie.c` from [digisophie](https://github.com/soejrd/digisophie) (MIT), a fixed-point
  adaptation of [Sophie for Schwung](https://github.com/mestela/schwung-sophie) by Matt Estela (MIT).

Both are copied here **unmodified** (`machines/*/third_party/`, with their licences), so the build needs
nothing else.

What this repository adds is the **adapter** between that code and the Model:Cycles machine contract
(`update(pmod, voice, params)` once per 32-sample block, then `render(out, voice)`), two short C files:

- `machines/plaits/plaits_cycles.c`
- `machines/sophie/sophie_cycles.c`

They read the track's knobs, compute the pitch the way the stock pitch code does (note + PITCH + FINE
TUNE), call the engine, and then run the **stock** amp envelope, VCA and PUNCH stage, set up as the stock
TONE machine sets them up. So DECAY, PUNCH and GATE behave as on any stock machine.

**What is missing:** adding the machines to the OS's machine list (names, knob descriptors, MACHINES
screen). That is what Modded-Cycles' generator does for its Syntakt engines; this code is meant to be
plugged into it. Nothing here builds a flashable firmware.

## The machines

One machine per engine. The engine does not take a knob; to change engine per step, use a machine lock.

| Menu name | Engine | Plaits engine |
|---|---|---|
| `PL_WSHAP` | WSHAPE | waveshaping oscillator |
| `PL_2OPFM` | 2OP FM | two-operator FM |
| `PL_NOISE` | NOISE | filtered clocked noise |
| `PL_PARTC` | PARTCL | particle noise |
| `PL_BDRUM` | BDRUM | bass drum |
| `PL_SNARE` | SNARE | snare drum |
| `PL_HIHAT` | HIHAT | hi-hat |
| `PL_GRAIN` | GRAIN | granular formant oscillator |
| `SO_FUSE` | FUSE | Sophie model 0 |
| `SO_BOOM` | BOOM | Sophie model 1 |
| `SO_PIPE` | PIPE | Sophie model 2 |
| `SO_SHARD` | SHARD | Sophie model 3 |

The names are a proposal: a two-letter prefix per family (`PL_`, `SO_`; `SK_` would suit the Syntakt
engines) and five letters. **Whether eight characters fit the MACHINES screen has not been checked**; five
are known to fit.

### Knobs

| Knob | Plaits machines | Sophie machines |
|---|---|---|
| PITCH | pitch (as stock) | pitch (as stock) |
| DECAY | amp decay (stock envelope) | amp decay (stock envelope) |
| COLOR | **AUX**: 0-55 Plaits' OUT, 72-127 its AUX output, 56-71 crossfade | **COLOR** |
| SHAPE | **HARMONICS** | **METAL** |
| SWEEP | **TIMBRE** | **SWEEP** (bipolar, 64 = centre) |
| CONTOUR | **MORPH** | **FBK** (feedback) |
| PUNCH, GATE | as stock | as stock |

Not mapped yet for Sophie: **FOLD** (its wavefolder) is off and velocity is fixed at 127. The plan for FOLD
is a second layer on the SHAPE knob, hold PRESET MENU and turn SHAPE, the way Model-TG puts Attack on DECAY.

## Measurements (emulation)

Note 60, default knobs (Plaits: HARMONICS/TIMBRE/MORPH 64; Sophie: 64/64/64, FBK 32), DECAY 80.

**Cost**: instructions per 32-sample block for one voice, counted in the emulated voice loop (the loop
alone, with no voice, is 1610). It is an instruction count, not a time on hardware.

| Stock machine | | Plaits | | Sophie | |
|---|---|---|---|---|---|
| TONE | 5291 | PL_WSHAP | 5316 | SO_FUSE | 5285 |
| PERC | 6079 | PL_NOISE | 5363 | SO_PIPE | 5486 |
| METAL | 6431 | PL_2OPFM | 5436 | SO_BOOM | 5638 |
| SNARE | 7157 | PL_SNARE | 6786 | SO_SHARD | 6153 |
| KICK | 7416 | PL_GRAIN | 7401 | | |
| CHORD | 8294 | PL_HIHAT | 7629 | | |
| | | PL_BDRUM | 8160 | | |
| | | PL_PARTC | 9166 | | |

**Level**: peak after the stock amp chain, as a fraction of full scale. Stock machines 0.076-0.212;
Plaits machines 0.044-0.125; Sophie machines 0.055-0.068.

**Pitch**: note 60 plays 262-264 Hz (expected 261.6; the measurement is to the nearest sample period).
PITCH +12 gives 522 Hz, -12 gives 131 Hz; FINE TUNE +32 is one semitone.

**Size**: Plaits 38 kB of code, 7.6 kB of tables, 1.7 kB of state for six voices. Sophie 4.5 kB of code,
2.6 kB of tables, 0.6 kB of state. Both modules are linked at `0x43000000`, the free SDRAM above the OS's
BSS that Modded-Cycles uses for its payload.

## Build

```sh
sudo apt install gcc-m68k-linux-gnu binutils-m68k-linux-gnu     # Debian / Ubuntu / WSL
./build.sh
```

Output: `build/plaits.{elf,bin,sym}` and `build/sophie.{elf,bin,sym}`. `CROSS=m68k-elf- ./build.sh` uses
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
module is loaded at `0x43000000`. For each machine the test plays a 0.5 s note, writes
`out/<machine>.wav`, and checks that it sounds, that no memory access went astray, and (for the pitched
ones) that the note is in tune. `--cost` adds the instruction counts above. The `.wav` files are normalised,
so they do not show the level; the printed peak does.

With a stock Unicorn the bench emulates the EMAC in Python and is slow: about a minute per machine.
`--fast` is for a Unicorn built with [digiemu](https://github.com/irpina/digiemu)'s patches
(`tools/install-patched-unicorn.sh` there): the EMAC then runs natively, the output is bit-identical, and
the whole test takes a few seconds.

One thing the bench needed: its Python EMAC does not know `move.l ACCext01,Dn`, which the Plaits port uses
to save and restore the EMAC state around its own use. The test adds it at run time; `mcengine.py` and
`emac.py` are not modified.

## Layout

```
machines/plaits/plaits_cycles.c      the Plaits adapter
machines/plaits/link.ld
machines/plaits/third_party/digi1_mods/   macro.c, mono.c and their headers, unmodified (MIT)
machines/sophie/sophie_cycles.c      the Sophie adapter
machines/sophie/link.ld
machines/sophie/third_party/digisophie/   sophie.c and its headers, unmodified (MIT)
build.sh
test/play_machines.py
THIRD_PARTY.md
```

`mono.c` is there for one function, `mono_pitch_inc()` (pitch to phase step); the linker drops the rest.

## Licence

The adapters, scripts and documentation of this repository: MIT, see [LICENSE](LICENSE).
The third-party code keeps its own licences: see [THIRD_PARTY.md](THIRD_PARTY.md).
