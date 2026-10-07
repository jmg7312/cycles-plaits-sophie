# MACRO and Sophie machines for the Elektron Model:Cycles

Two extra synth machines for the Model:Cycles (OS 1.13), twelve engines in all: **MACRO**, the eight
engines of digi1_mods' machine of that name (ported from Plaits), and **SOPHIE**, with its four models.
They run inside the Cycles' own voice loop next to the stock FM machines.

> **Status: beta, emulation only. This has NOT been flashed to or tested on a real Model:Cycles.**
> A tool now makes a flashable firmware with the two machines in the machine list (see
> [Beta firmware](#beta-firmware)); it is for testers who know how to restore their unit.
> Everything below was measured in emulation: [Modded-Cycles](https://github.com/18nelli18/Modded-Cycles)'
> bench (`tools/emu/mcengine.py`), which runs the real OS 1.13 voice loop from your own OS file, and the
> OS's own functions run one at a time.
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

The MACRO adapter calls `macro_render()` on **a stack of its own** (4 096 bytes, `machines/macro/private_stack.S`).
The Cycles' audio interrupt does not switch stacks: it runs on the stack of whatever task it interrupted, the
smallest of which is 2 048 bytes, and the stock machines use about 250 bytes of it. `macro_render()` needs up
to 1 700. On its own stack it uses 1 556 bytes at most in our runs, and the adapter stays at 248 bytes on the
task's stack, the level of the stock machines (emulation; the figures on the OS's stacks come from reading
the OS, not from hardware).

**The machine list:** `tools/make_firmware.py` adds the two machines to the OS's machine list (names, knob
descriptors, MACHINES screen) and writes a firmware file, from your own official OS file. It follows the
method Modded-Cycles uses for its Syntakt engines, which was tested on hardware; our implementation of it
was not. See [Beta firmware](#beta-firmware).

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

## Beta firmware

> **Read this whole section before flashing anything.**
> - **Not tested on hardware.** Nobody has flashed this yet. It may not boot, it may freeze, it may sound
>   wrong. If it does not boot you will have to restore the official OS yourself.
> - **Restoring needs a MIDI interface and a cable.** The recovery path is the STARTUP MENU: hold **FUNC**
>   while powering on, then choose **OS UPGRADE**. It listens on **MIDI IN only, not USB**. So you need a
>   MIDI interface wired to the Cycles' MIDI IN (3.5 mm TRS, or the DIN adapter), and software that sends a
>   `.syx` through it. **Try it BEFORE flashing the beta**: enter the STARTUP MENU, send the *official*
>   `model-cycles_OS1.13.syx` that way and see it through. If you cannot do that, do not flash the beta.
> - **Back up your projects** with Elektron Transfer first.
> - **Do not combine** this firmware with Modded-Cycles or Model-TG, and do not load into it projects made
>   with their added machines: every mod numbers its machines its own way.
> - **Before going back to the official OS**, put every track of your projects that uses MACRO or SOPHIE
>   back on a stock machine and save. The official OS reads outside a table for a track left on a machine
>   past CHORD; on a unit with Modded-Cycles' machines this froze the unit when MACHINES was pressed
>   (its notes/20). If it happens anyway: STARTUP MENU, EMPTY RESET clears the active project.
> - Flashing a modified OS is at your own risk and may void your warranty.

### Make the file

You need Python 3 (nothing else) and your own official `model-cycles_OS1.13.syx` from elektron.se. No
compiler: the machines' code is in `prebuilt/`.

```sh
python3 tools/make_firmware.py model-cycles_OS1.13.syx -o cycles_macro_sophie_beta.syx
```

It accepts only the official OS 1.13 file (sha256 `44fe5862...640c`), checks the file it wrote, and prints its
sha256. With the `prebuilt/` of this commit the result is 948 512 bytes, sha256
`84d792e242c21754bdd9613d14f8688f039b36cc985085cf9773ddee0547c0d7`. If yours differs, do not flash it, and
say so in your report. `--list` prints the 113 changes made to the OS, each with its reason. Nothing of
Elektron's is in this repository or in the tool: the OS comes from your file.

Send the file with Elektron Transfer, like an official OS (about 7 % longer). Then follow
**[docs/BETA-TEST.md](docs/BETA-TEST.md)**: what to check first, the load tests, what to write down, how to
restore.

### What it does

- The official OS 1.13, plus **MACRO** as machine 7 and **SOPHIE** as machine 8, after KICK, SNARE, METAL,
  PERC, TONE and CHORD on the MACHINES screen. Nothing else is added or changed: no other engine, no audio
  routing, no new screen.
- Choosing one sets its knobs to defaults: MACRO COLOR 4 (WSHAPE), SOPHIE COLOR 16 (FUSE), SHAPE, SWEEP and
  CONTOUR 64, DECAY 80. Turning a knob shows its name: Macro Engine, Macro Harmonic, Macro Timbre, Macro
  Morph; Sophie Model, Sophie Metal, Sophie Sweep, Sophie Color.
- Both show CHORD's picture: the OS has six pictures and none was added.
- Machine locks, CC 70 (machine, values 6 and 7) and CCs 16 to 19 go through the same tables as for the stock
  machines. A sound stores its knob values by knob, not by machine, so the project format does not change.
- 65 524 bytes of payload (code, tables, state) are appended to the OS and copied at boot to `0x43000000`,
  free memory above the OS's own. 113 places of the OS are changed, 406 bytes in all.

### What was checked, and what was not

`test/test_firmware.py` makes the firmware, reads the `.syx` back and runs the OS's own code on it in
emulation, next to the stock OS (44 checks, all passing):

- the file: message checksums, content checksum, HMAC trailer; the three other sections identical; every
  byte of the OS that differs is one of the 113 listed changes;
- boot: the bootstrap's own unpacker rebuilds the OS as built; the boot hook installs the payload and
  nothing else moves (SRAM, the rest of the image, the memory around the payload);
- the tables the OS builds at boot and every lookup by machine, knob, CC or descriptor: identical to stock
  for the six stock machines;
- MACHINES screen (names, 8 position marks inside the screen), the wheel up and down, the real
  machine-change code writing the defaults, back to a stock machine, the main screen's knobs;
- sound: the six stock machines **sample for sample** as on the stock OS (172 800 samples, and six tracks
  at once); the 12 engines through machine numbers 7 and 8, in tune; machine locks between stock and added
  machines; stack use.

**Not checked, because it cannot be emulated:** the unit booting as a whole; the screen as you see it (only
the drawing calls are intercepted: whether "SOPHIE" fits is taken from Model-TG, which shows 6- and
7-letter names there); real CPU time and audio dropouts; saving and loading a project or a preset on the
internal storage; MIDI in and out; the LFO on the new knobs; USB audio; anything that happens after hours of
use. That is what the beta test is for.

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

**Size**: MACRO 38 kB of code, 7.6 kB of tables, 1.7 kB of state for six voices and 4 kB of private stack.
Sophie 4.5 kB of code, 2.6 kB of tables, 0.6 kB of state. The code runs at `0x43000000`, the free SDRAM above
the OS's BSS that Modded-Cycles uses for its payload. Nothing is placed in the fast internal SRAM.

## Build

```sh
sudo apt install gcc-m68k-linux-gnu binutils-m68k-linux-gnu     # Debian / Ubuntu / WSL
./build.sh
```

Output: `build/macro.{elf,bin,sym}` and `build/sophie.{elf,bin,sym}` (each machine alone, for
`test/play_machines.py`), and the firmware payload, `build/payload.{elf,bin,sym}` and `build/stub.bin`: both
machines and the machine-list code of `firmware/` linked together. `tools/make_firmware.py --payload build`
uses it instead of `prebuilt/`; `./build.sh --prebuilt` refreshes `prebuilt/`. Another compiler version
gives another binary, so another firmware sha256. `CROSS=m68k-elf- ./build.sh` uses another toolchain
prefix. Flags: `-mcpu=54418 -O2 -ffreestanding -nostdlib`, as Modded-Cycles builds its
own C machines.

## Test

You need a checkout of Modded-Cycles (for its bench) and your own official `model-cycles_OS1.13.syx`.
No firmware is included here.

The firmware, from the `.syx` the tool writes (see [Beta firmware](#beta-firmware)):

```sh
pip install numpy unicorn
python3 test/test_firmware.py --modded ../Modded-Cycles --cycles model-cycles_OS1.13.syx --fast
```

The machines alone, without the machine list (no firmware is written):

```sh
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
machines/macro/private_stack.S       calls macro_render() on a stack of its own
machines/macro/link.ld
machines/macro/third_party/digi1_mods/    macro.c, mono.c and their headers, unmodified (MIT)
machines/sophie/sophie_cycles.c      the Sophie adapter
machines/sophie/link.ld
machines/sophie/third_party/digisophie/   sophie.c and its headers, unmodified (MIT)
firmware/                            the machine list: boot hook, tables, replaced OS accessors
prebuilt/                            the firmware payload as built by build.sh (our code and the MIT code only)
tools/make_firmware.py               official OS file -> beta firmware file
tools/mtlib/                         the OS file format, from elektron-model-tweaks (MIT)
build.sh
test/test_firmware.py                the firmware, checked in emulation from the file the tool writes
test/play_machines.py                the machines alone
test/stress_engine_switch.py         MACRO with an engine switch on every trig
docs/BETA-TEST.md                    for beta testers
docs/MODEL-CYCLES-NOTES.md           notes on the OS for loader and firmware authors
THIRD_PARTY.md
```

`mono.c` is there for one function, `mono_pitch_inc()` (pitch to phase step); the linker drops the rest.

## Licence

The adapters, scripts and documentation of this repository: MIT, see [LICENSE](LICENSE).
The third-party code keeps its own licences: see [THIRD_PARTY.md](THIRD_PARTY.md).
