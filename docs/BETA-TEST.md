# Beta test: MACRO and SOPHIE on the Model:Cycles

For testers. This firmware has **never run on a real Model:Cycles**. Everything known about it comes from
emulation (see the README, "What was checked, and what was not"). You are the first to try it. Expect
anything, including a unit that does not start until you restore it.

Please report on GitHub (an issue on this repository), whatever the result. "It boots and the six stock
machines sound normal" is already worth a report.

## 1. Before flashing

1. Your unit runs **OS 1.13**, and is not running Modded-Cycles or Model-TG.
2. You have the official `model-cycles_OS1.13.syx` (elektron.se). It is your way back. Keep it at hand.
3. **You have tried the recovery path, with the official file, before anything else.** Power off, hold
   **FUNC**, power on: the STARTUP MENU appears. Choose **OS UPGRADE**. In that menu the unit listens on
   **MIDI IN only**, not USB: connect a MIDI interface's output to the Cycles' MIDI IN (3.5 mm TRS, or the DIN
   adapter) and send the official `.syx` with a SysEx tool, slowly. Modded-Cycles' notes report 6 to 7
   minutes, and a transfer that stalls when sent too fast (power off, start again, slower). We have not
   done this ourselves. If you cannot complete it with the official file, **stop here**.
4. Your projects are backed up with Elektron Transfer.
5. You made the file yourself with `tools/make_firmware.py`, from your own official file, and its sha256 is
   the one given in the README for this commit. Note the commit and the sha256: put them in your report.
6. Stable power. Do not touch the unit while it writes the flash.

Flash with Elektron Transfer over USB, like an official OS.

## 2. First checks

Stop at the first thing that looks wrong, write it down, and restore (section 5).

1. **It boots.** The usual start screen, then the usual project.
2. **Nothing changed for the stock machines.** Play a project you know. KICK, SNARE, METAL, PERC, TONE and
   CHORD sound as before; their knobs show the usual names.
3. **MACHINES screen.** Press MACHINES and turn the wheel: eight machines, **MACRO** and **SOPHIE** after
   Chord. Eight position marks, all on the screen. MACRO and SOPHIE show CHORD's picture (expected). Does
   "SOPHIE" fit? The wheel stops at SOPHIE going up and at Kick going down.
4. **MACRO sounds.** Put a track on MACRO. Its knobs go to COLOR 4, SHAPE 64, SWEEP 64, CONTOUR 64,
   DECAY 80. Play the pad: a pitched tone (WSHAPE). Turn COLOR slowly from 0 to 127 and play: the engine
   changes every 8 values, WSHAPE, 2OP FM, NOISE, PARTCL, BDRUM, SNARE, HIHAT, then GRAIN from 56 up. Each
   of the eight sounds.
5. **SOPHIE sounds.** Same on SOPHIE: COLOR 16 at first; the model changes every 32 values, FUSE, BOOM,
   PIPE, SHARD. Each of the four sounds.
6. **Knob names.** Turning COLOR, SHAPE, SWEEP, CONTOUR on MACRO shows Macro Engine, Macro Harmonic, Macro
   Timbre, Macro Morph; on SOPHIE, Sophie Model, Sophie Metal, Sophie Sweep, Sophie Color. Anything cut off?
7. **The common knobs.** On both: PITCH transposes in semitones, DECAY sets the length, PUNCH and GATE act
   as on a stock machine, VOLUME+DIST, the sends and PAN work.
8. **Back to a stock machine.** Put the track back on TONE: TONE's usual default values and sound.
9. **A pattern.** Sequence MACRO and SOPHIE on two tracks, with a parameter lock of COLOR on a few steps and
   a machine lock (a step on another machine). Play it.
10. **Save and reload.** Save the project, power off, power on. The tracks are still on MACRO and SOPHIE,
    with their knob values, and play the same. Save a preset from a MACRO track and load it on another.
11. If you use them: CC 70 (machine) with values 6 and 7, CCs 16 to 19 on a MACRO track, the LFO with COLOR
    or SHAPE as destination.

## 3. Load tests

This is the main unknown. Emulation counts instructions, not time: nobody knows yet how much of the
processor these machines take on the real unit. On the Digitakt, the MACRO engines are reported to overload
when used on every track.

Work up step by step. At each step listen for crackles, missing notes, a late or sluggish screen, knobs
that answer slowly.

1. One track of MACRO, 16 steps, each engine in turn.
2. Two tracks of MACRO.
3. Four tracks.
4. Six tracks of MACRO.
5. Six tracks, all with a trig **on the same step** (step 1, then every step).
6. One track with a **parameter lock of COLOR on every step**, a different engine each step. Then two
   tracks, then six.
7. The engines counted as heaviest in emulation: **PARTCL** (COLOR 24 to 31) and **BDRUM** (32 to 39). Six
   tracks of PARTCL, all on the same steps, fast tempo, short DECAY, then long DECAY.
8. Six tracks of SOPHIE.
9. MACRO and SOPHIE mixed with stock machines, and the delay and reverb sends open.
10. Leave a loaded pattern playing for 15 minutes.

## 4. What to write down

1. Commit of this repository and sha256 of the file you flashed.
2. Which step of sections 2 and 3 you reached.
3. For any problem: **what** (crackle, missing notes, wrong sound, slow screen, freeze, reboot), **when**
   (which pattern, how many tracks, which machines and engines, tempo), and whether it comes back when you
   do the same again.
4. A freeze: what you pressed just before. Does the unit start again after a power cycle? With the same
   project?
5. How the levels of MACRO and SOPHIE compare with the stock machines.
6. Anything on the screen that overlaps or is cut off. A photo helps.

## 5. Restoring the official OS

1. If the unit works: **first put every track that uses MACRO or SOPHIE back on a stock machine, in every
   project you want to keep, and save.** The official OS does not know machines 7 and 8: a track left on one
   plays CHORD, and its screens read outside a table. With Modded-Cycles' machines this froze the unit when
   MACHINES was pressed.
2. Then send the official `model-cycles_OS1.13.syx` with Elektron Transfer, as for any OS update.
3. If the unit does not start, or freezes too early for that: STARTUP MENU (hold **FUNC** while powering
   on), **OS UPGRADE**, and send the official file through **MIDI IN**, as you tried in section 1.
4. If the official OS then freezes on a project that still has a track on MACRO or SOPHIE: STARTUP MENU,
   **EMPTY RESET**. It clears the active project (the manual, section 13); the unit starts on an empty one.
   Your other projects are still stored. Do not work on the official OS in a project that still has such a
   track: restore your backup, or flash the beta again to put the tracks back on stock machines.
