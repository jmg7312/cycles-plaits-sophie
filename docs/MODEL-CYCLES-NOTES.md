# Model:Cycles OS 1.13: notes for a mod loader

What we know about the Model:Cycles that a loader such as [elekloader](https://github.com/irpina/elekloader)
would need in order to support it: the OS file, a draft of the device profile, the memory map, the audio
engine and its machines, the UI and MIDI entry points, and what the existing mods already occupy.

No Elektron code is reproduced here: only addresses, sizes, hashes and descriptions. All addresses are
virtual addresses of **OS 1.13**.

## Where each fact comes from

Every fact carries one of these tags. Nothing here has been confirmed by us on hardware.

| Tag | Meaning |
|---|---|
| **[M]** | Measured or read by us in the stock `model-cycles_OS1.13.syx` (unpacked main OS, disassembled with `m68k-linux-gnu-objdump -m m68k:cfv4e`, or run in emulation). |
| **[MC]** | From [Modded-Cycles](https://github.com/18nelli18/Modded-Cycles)' notes (`notes/`), whose author tested on hardware. Note number given. |
| **[TG]** | From [Model-TG](https://github.com/TinyGregAudio/Model-TG)'s `docs/INTERNALS.md` ("each verified on hardware"). |
| **[DK]** | From [elektron-model-tweaks](https://github.com/drumkilla/elektron-model-tweaks)' `mtlib` (the file format code). |
| **[MAN]** | Elektron's Model:Cycles User Manual, OS 1.13. |

Where two sources agree it is said. Where we only have one, treat it as that source's claim.

---

## 1. The OS file

### Stock releases

| | Model:Cycles 1.13 | Model:Samples 1.13 |
|---|---|---|
| `.syx` sha256 | `44fe586269631a0ca7da25a3383fc6733c314809505fc3cc52f1e0ed9800640c` | `e11859b68deb7e5e3fe86ab32581212093849c4be5d3950add011eac398a2ce8` |
| `.syx` size | 890 016 | 849 568 |
| main OS (section id 3) sha256, unpacked | `cc99d4f0175d34d1e91d046e6ec85a5e8ab58ab9edbb3c24406acd48cb99ee98` | `a351392c62ec1c6c3324a807baf46934690d54edfc76029a4b4882541cad1ab2` |
| main OS length, unpacked | 1 744 192 | 1 733 184 |

[M] for the Cycles; the Samples' hashes are [DK] (`tweaks/model-samples_OS1.13/device.json`) and its sizes [M].

### SysEx transport [DK], checked [M]

- Messages `F0 00 20 3C <product> 00 ...`; one start message, N data messages of exactly 128 bytes, one end
  message. Cycles 1.13: 6 953 data messages.
- Product byte: `0x11` Model:Cycles, `0x0F` Model:Samples. Device byte in the start/end messages: `0x0C`
  Cycles, `0x0A` Samples.
- Payload: 7-bit packing, MSB first (8 SysEx bytes carry 7 data bytes); 116 packed bytes = 101 plain bytes
  per message.
- Per-message checksum: `(C0 - sum(msg[i] ^ mask[i] for i in 8..125)) & 0x7F` with `mask[i] = (V - i) & 0x3F`.
  Cycles: `V = 0x3A`, `C0 = 0x22`. Samples: `V = 0x3C`, `C0 = 0x1E`.

### Container [DK], checked [M]

- Stream = `[u32 container length][u32 content checksum]` then the container.
- Container magic `ELE3`; version field `00381.13` (product code `0038`, version `1.13`); section count at
  `+0x1C`; section table at `+0x20`, 16 bytes per entry: id, offset, size, attr.
- Content checksum: sum over big-endian words of `(index + 1) XOR word`. Not a CRC.
- Sections of the Cycles 1.13 file, in table order:

| id | stored | unpacked | attr | what |
|---|---|---|---|---|
| 5 | 15 | 15 | `00000000` | build date, `210525 16:37:28` |
| 2 | 15 536 | 26 602 | `04000000` | ColdFire code (bootstrap / updater) |
| 3 | 654 704 | 1 744 192 | `40000400` | **main OS**; attr = its load address |
| 4 | 31 752 | 31 752 | `80000400` | ColdFire code, stored unpacked; attr = its load address |

- Compressed sections: an 8-byte header `[u32 stream length][u32 byte sum of the stream]`, then an aPLib
  variant (interlaced Elias-gamma bit stream; offset bias 767). `mtlib/aplib.py` decodes and re-encodes it.
- **Trailer: HMAC-SHA256** over the container, 32 bytes at the end. The key is not stored: it is derived
  from material inside the unpacked firmware, a printable string `s` followed by a 32-byte constant `c`,
  sitting right after the 8-byte anchor `BE F9 A3 F7 C6 71 78 F2` (the tail of the firmware's own SHA-256
  table): `key = sha256(s) XOR sha256(reverse(s)) XOR c`. `mtlib/container.py` finds it and accepts it only
  when it reproduces the stored digest. We ran this on the stock file: the key is found and the digest
  matches.
- Only section 3 needs to change for a mod. The Model tools carry sections 2 and 4 over byte for byte.

## 2. Draft of an elekloader device profile

Field names are those of `docs/DEVICES.md`. "?" means we do not know.

| field | Model:Cycles | source |
|---|---|---|
| `releases` | the hashes and length above | [M] |
| `sysex_id` | `0x11` (product byte); device byte `0x0C` | [DK] [M] |
| `main_section`, `main_load` | id 3, `0x40000400` | [M] (section attr) |
| `stage` | the bootstrap reads the section to `0x40200000`, then unpacks it in place to `0x40000400`. Bootstrap loader `0x80000850`, its aPLib depacker `0x800006bc` (section 2) | [MC] note 17 §6 |
| `flash_at`, `flash_limit` | ? | |
| `trailer` | `'hmac'` | [DK] [M] |
| `hmac_key_from` | derived as described above: anchor, string, constant inside the unpacked firmware | [DK] |
| `isa` | ColdFire. CPU read on the chip: **MCF54415CMJ250** (V4m core, MMU, EMAC, **no FPU**). Audio code uses the EMAC with `MACSR = 0xA0` (signed fractional, saturating) | [MC] note 21; [M] |
| `areas` | see "Free memory" below | [MC] |
| `recovery` | hold **FUNC** at power-on for the STARTUP MENU, then `4 ... OS UPGRADE`. **It listens on MIDI IN only, not USB**: a USB-MIDI interface wired to the Cycles' MIDI IN is needed to come back from a build that does not boot | [MAN]; [MC] notes 6, 12 |
| `container`, `version_len` | `'ele3'`; version field 8 characters (`00381.13`) | [M] |
| `protected` | ? Model-TG documents one hard rule, see "Constraints" below | [TG] |
| `blob_max` | the unpacked main OS must end below `0x40200000`: **2 096 128 bytes at most**. Stock is 1 744 192, so **351 936 bytes** for everything appended, all mods together | [MC] note 17 §7 |
| `toolchain` | `m68k-linux-gnu-gcc -mcpu=54418 -O2 -ffreestanding -nostdlib` (Modded-Cycles); GNU as for ColdFire (Model-TG) | [MC] [TG] |

The Model:Samples is the same board family and the same container; its main OS loads at the same address
[M]. We have not looked into its code.

## 3. Memory map

| range | what | source |
|---|---|---|
| `0x40000000`-`0x400003FF` | before the image; the vector table is here (the sequencer's handler is written to `0x400001E4`) | [M] |
| `0x40000400`-`0x401AA140` | the stock main OS image | [M] |
| `0x4019B590`-`0x401AA140` | load-time data, copied to the internal SRAM at boot and then reused as scratch: `0x4019B590..0x401A2A50` to `0x80000000`, `0x401A2A50..0x401AA140` to `0x80008000` | [MC] (`mcengine.py`), [TG]; checked [M]: the sine table at `0x8000EEE4` is at image `0x401A9934` |
| `0x4019B590`-`0x423380B0` | BSS, cleared at boot by `0x400004B2` (about 35 MB, voice states included) | [MC] note 17 §3; [TG] |
| above `0x423380B0` | no OS code references any address here up to the stack | [MC] note 17 §3 |
| `0x40000000`-`0x47FFFFFF` | covered by the data cache as the stock OS sets it up (ACR0) | [MC] note 17 §3; [TG] |
| `0x80000000`-`0x8000FFFF` | 64 kB internal SRAM: audio buffers, wavetables, per-block parameter state | [M] |
| 128 MB SDRAM in all | | [MC] note 17 §3 |

### Free memory, and who already uses it

- **`0x43000000`**: Modded-Cycles' payload, run on hardware. Its boot hook replaces the first 8 bytes of
  `0x400004B2` and copies the payload, appended at the end of the image (`0x401AA140`), to `0x43000000`
  before the BSS (which contains it) is cleared. [MC] note 17 §3.
- **`0x46700000`**: where Modded-Cycles puts its payload when combined with Model-TG. [MC] note 31.
- **`0x401AB750`** onwards (code from `0x401ABA40`): Model-TG's blob, in filesystem cache blocks it retires.
  [TG]
- **Sprite masks**: `0xFF` runs inside the image that are sprite masks which can be freed (the sprite then
  reads a shared mask). Modded-Cycles uses two of 1 024 bytes, at `0x4016CAE8` and `0x4018A788`, for small
  hooks. [MC] note 14 §5.
- Model-TG also uses a 64 MiB sample region and the cache setup above `0x4C000000`. [TG]

### Constraints [TG]

- Nothing of a mod may live between `0x4019B590` and `0x401AB750`: that is the firmware's own load-time data
  and scratch, including a 16 kB buffer at `0x401A7750..0x401AB750` the filesystem relies on being zero.
- The boot clear must still cover `0x4019B590..0x423380B0`, skipping only the mod's own code.

## 4. The audio engine

- One voice per track, six tracks; 32-sample blocks at 48 kHz (1 500 blocks a second). [M]
- **Voice loop: `0x400A7D4A`**`(out, params, trig_mask, release_mask)`. It sets `MACSR = 0xA0` on entry
  (`0x400A7D5A`) and `0x20` on exit (`0x400A7E5C`). [MC] note 14; checked [M]
- Voice state: 6 x `0x31C` bytes from **`0x42308828`**. Voice reset: `0x400A7AB8`. [MC]; checked [M]
- Track output buffers: `0x80001858 + track * 128` (32 x int32). Main mix `0x40056610` sums them into the
  interleaved stereo bus at `0x8000B990`. [TG]; the first is the bench's `TRACK_BASE` [MC]
- The sequencer is an interrupt handler, `0x40054C1E`, installed by `0x40055D56`. [M]
- The audio function called by the interrupt each block: `0x4005979E` (call site `0x40059382`). [MC]
  (`gen_syntakt_engines.py`)

### Machines

- A machine is two functions, taken from two tables of six pointers indexed by the machine number
  (0 KICK, 1 SNARE, 2 METAL, 3 PERC, 4 TONE, 5 CHORD):
  **render table `0x40118610`**, **update table `0x40118628`**. [M]; same in [MC] note 14

| # | machine | render | update |
|---|---|---|---|
| 0 | KICK | `0x400AA3C4` | `0x400AA08C` |
| 1 | SNARE | `0x400AB6E8` | `0x400AB3B0` |
| 2 | METAL | `0x400AA712` | `0x400AA49C` |
| 3 | PERC | `0x400AACC2` | `0x400AA998` |
| 4 | TONE | `0x400AA930` | `0x400AA7B8` |
| 5 | CHORD | `0x400AB24C` | `0x400AAE88` |

- Dispatch: `0x400A7DFE`..`0x400A7E24` in the voice loop. A byte table at `0x40118640`
  (`00 01 02 03 04 05 00 00`) maps the machine number to the table entry. [M] [MC] note 18 §2
- **Contract** [MC] note 14, used as is by our machines in emulation:
  - `update(pmod, v, p)`: once per block, before render. `pmod` = the trig's note, semitones << 16; `v` =
    the voice state; `p` = the track's parameters, 8.8 words.
  - `render(out, v)`: writes 32 int32 samples.
  - `v + 0x38 != 0` on the block where a note starts.
- Track parameter words at `p`: `+0x14` PITCH, `+0x16` COLOR, `+0x18` SHAPE, `+0x1A` SWEEP, `+0x1C` CONTOUR,
  `+0x1E` PUNCH, `+0x22` FINE TUNE, `+0x24` DECAY. A parameter with slot `s` is at `p + 2 * s` (machine
  `0x09`, pitch `0x0A`, color `0x0B`, shape `0x0C`, sweep `0x0D`, contour `0x0E`, punch `0x0F`, gate `0x10`,
  fine tune `0x11`, decay `0x12`). [MC]; the five knob offsets checked [M] in TONE's update
- A track has 33 parameter words in all (k = 0..32, a 66-byte mirror); the stock OS uses k = 0..22. Model-TG
  takes k = 23 (Attack), 24 and 25 (Filter, Resonance), 26 and 27 (its Sampler's state). A sound record is
  100 bytes with 32 slots at `+28..+91`. [TG]

### Stock DSP blocks a machine can call [M]

Read in the disassembly; the first three are the ones our machines call in emulation.

| address | what |
|---|---|
| `0x400A9252` `(v)` | amp envelope: linear attack, hold while gated (GATE), exponential decay from `v + 592` |
| `0x400A9430` `(buf, v)` | VCA for that envelope (level `v + 560`, ramped over the block) |
| `0x400A967A` `(buf, v)` | PUNCH stage |
| `0x400A9120` `(v)` | the four operators' envelopes: delay, attack, decay to a level |
| `0x400A8204`, `0x400A835E` `(op, v)` | phase-modulated wavetable operator, two modulation inputs (48 kHz; 96 kHz variant) |
| `0x400A8ADC`, `0x400A8FC2` `(op, v)` | self-feedback operator (48 kHz; 96 kHz variant) |
| `0x400A8722` `(op, v)` | CHORD's operator: the same with a crossfade between two wavetables |
| `0x400A9884` `(a, b, out, idx, v)` | two-input mixer with a ramped gain per input |
| `0x400A9A32` | three-input mixer (CHORD) |
| `0x400A9CF6`, `0x400A9D4E` | first-order filters (coefficients b0, b1, a1) |
| `0x400A9EBE` | second-order filter (b0, b1, b2, a1, a2) |
| `0x400A9F58` | 2x decimator (TONE) |
| `0x400A91EA` `(v)` | attack/decay envelope used for pitch (KICK, SNARE, PERC) or filter cutoff (CHORD) |
| `0x400A9CA8` `(table, value)` | 128-point table lookup with linear interpolation: every knob curve goes through it |
| `0x400A7E6C`, `0x400A7F66` | operator frequencies from the note (exp table `0x40118A4C`) |

An operator is 120 bytes at `v + n * 120` (n = 0..3): ratio `+80` (`0x04000000` = 1.0), level envelope
`+84..+96`, phase `+108`, phase step `+112`, level `+116`/`+120`, modulation depths `+132`/`+136`, the two
modulation input pointers `+148`/`+152`, wavetable pointer `+168`, the two output pointers `+192` (after the
level) and `+196` (before it). Wavetables are 257 x int32.

## 5. Adding a machine to the list

Modded-Cycles does it for its Syntakt engines and documents every place that depends on the number of
machines: **[MC] note 18** (a 7th machine, 116 writes, six attempts on hardware) and notes 19 and 20 (more
machines). Since the beta firmware, this repository does it too, for Plaits and Sophie, with its own code
(`firmware/`, `tools/make_firmware.py`): section 5.1 lists what it changes. In short, what has to change:

- the voice loop: two bounds (`0x400A7DBA`, `0x400A7DF4`), the byte table `0x40118640`, and the two function
  tables, which are contiguous and have to be relocated to grow;
- the "Algorithm" parameter (descriptor 41, `0x4010E5D8`): its maximum decides what can be selected
  everywhere (menu, machine locks, CC 70);
- the parameter descriptor table **`0x4010DCE0`** (76 entries of `0x38` bytes): each machine has its own
  COLOR/SHAPE/SWEEP/CONTOUR entries (long name, short name, default) and an Amp Decay; it cannot grow in
  place;
- the lookup tables built at boot from the descriptors by `0x4005A274` (per-machine rows for knobs and CCs);
- the MACHINES screen (drawn from `0x400A25E0`): a bound, the table of six name pointers `0x401177E4`, the
  icons (two arrays of six sprite descriptors);
- setting a track's machine: `0x4001477E`, and the wheel `0x4001488A`, both bounded at 5;
- the per-machine records (seven of 76 bytes at `0x40A71540`).

**A limit on the number of machines.** In Modded-Cycles' method every added machine gets five descriptors
of its own (four knobs and an Amp Decay). The accessors of the descriptor table bound the index with
`moveq #75` / `moveq #76` at 43 sites (`BOUNDS` in its `tools/gen_sdvintage_7th.py`), and `moveq` takes a
signed 8-bit value: 127 descriptors at most, so (127 - 76) / 5 = **10 added machines in all, every mod
together**. Its generator sets its own limit at 6. Going further means machines sharing descriptors, or
rewriting those sites. This is our reading of its generator, not something we tried. It is why the two
machines of this repository hold several engines each, picked by a knob.

The screen shows the **long name** of a knob when it is turned, split at spaces, one word per line; words
up to 8 letters fit. A 5-letter machine name is known to fit the MACHINES screen. [MC] note 18 §10

### 5.1 What the beta firmware changes (machines 6 and 7, 113 places, 406 bytes)

`python3 tools/make_firmware.py OFFICIAL.syx --list` prints every one with its address and bytes. All of it
[MC] notes 17 to 20 unless marked **ours**; checked in emulation by `test/test_firmware.py` [M], not on
hardware.

| what | where | why |
|---|---|---|
| boot hook (3) | first 8 bytes of `0x400004B2` become a jump; its code (38 bytes) in the sprite mask `0x4016CAE8`, whose sprite (`0x400B1106`) now reads the identical mask `0x40154AE4` | copy the payload from the end of the image (`0x401AA140`) to `0x43000000` before the BSS, which contains it, is cleared. The copy includes the payload's state as zeros |
| descriptor table (37) | every reference to `0x4010DCE0` (34), `+8` (1), `+0x20` (2) | the table cannot grow in place: a copy with 10 more entries lives in the payload. Entries 76-79 and 81-84 are the knobs of Plaits and Sophie, 80 and 85 their Amp Decay, all modelled on SNARE's (same slots, range, CCs 16-19, flags). "Algorithm" (41) goes up to 7 in the copy: that is what makes the machines selectable (menu, machine locks, CC 70) |
| descriptor count (42) | the `moveq #76` / `#75` of the table's accessors | 86 / 85 |
| rows built at boot (7 + 1) | references to `0x40A79418` (5) and `0x40A7ADA4` (2); size cleared at `0x4005A2B8` | machine/knob and machine/CC rows for 8 machines, in the payload. **Ours:** an empty row before and eight after, because the Amp Decay lookup (`0x4005A6B6`) does not check the machine |
| machine count (11) | `0x400A7DBA`, `0x400A7DF4`, bytes 6-7 of `0x40118640`, `0x4005A6A6`, `0x400147A4`, `0x400148AA`, `0x400148B2`, `0x400A25E0`, `0x400A26A2`, `0x400A26E8`, and `0x4005A8F6` | highest machine 5 -> 7 in the voice loop, the knob lookup, the machine setter, the wheel, the MACHINES screen (8 marks starting 7 pixels further left), the CC lookup. **Ours:** the CC lookup is patched in place (the same compare, with the 7 loaded before it) instead of through a detour |
| function tables, names (3) | `0x400A7D6C`, `0x400A7E16`, `0x400A2614` | update, render and name tables with 8 entries, in the payload |
| "belongs to one machine" (1 + 2) | `0x4005A572`; `0x4005A340` and `0x4005A50A` replaced | a descriptor's machine field cannot say 7 (7 means every machine): ours carry 6, and two pieces of our code say which machine each belongs to |
| state objects (2) | `0x4004DF40`, `0x4004DFA2` replaced | one state object per descriptor, 76 of them built at boot: ours use SNARE's |
| per-machine records (2 + 1) | `0x4004DF5C`, `0x4004DF76` replaced; `0x4001E8DA` | two more records, built on first use from SNARE's; a machine that does not exist gets KICK's instead of a read before the table |
| MACHINES screen picture (1) | `0x400A2638` | six pictures only. **Ours:** Plaits and Sophie show CHORD's, which is what the OS's other screens already show for a machine above CHORD, so those are left alone |

The four replaced accessors keep `a0` and `a1` (**ours**): the stock ones are leaves that change `d0` and
`d1` only, and callers compiled with them may rely on it.

For a loader, this is the natural shared resource: one owner of the machine list that machine mods register
with (what `digichain` and `core_machines` do on the Digitakt mk1). Today three independent mods patch
these same sites: Model-TG (its Sampler is machine 6), Modded-Cycles (Syntakt engines from 6, or from 7 next
to Model-TG) and this repository would be a fourth.

## 6. UI and MIDI entry points

All [TG] unless tagged otherwise.

- **Keys**: the key-code accessor every consumer calls is `0x4007240C`. Codes: FUNC 1, TRACK 2, PATTERN 3,
  RETRIG 4, PRESET 5 (the key labelled PRESET MENU, called [MACHINES] in the manual), PUNCH 6, RECORD 9,
  RETURN 12, SETTINGS 13, PAGE 15, trig keys 16-31, DATA press 32. Event flags at `+16`: bit 0 down, bit 3
  repeat, bit 4 click, bit 5 long press.
- **Knobs**: index at event `+12`: DATA 1, the twelve parameter knobs 2-13. Clicks with acceleration:
  `0x4006F73A(event, slow, fast)`.
- **Screen**: text `0x40071A04`, rectangles `0x40070DEA`; y runs from the bottom.
- **Notes**: core note-on `0x4008171E(track, note, velocity, 0x40, 0, -1, -1)`, note-off
  `0x4008145E(track, note, 0x40)`.
- **Pattern data**: a track's step data is a 722-byte block; step flags word at `+2 * step` (bit 0 = trig);
  per-step signed bytes, -1 = track default: velocity `+128`, length `+192`, trig note `+580`, sound lock
  `+644`. Parameter locks: set `0x4001646A(track, step, slot, value)`, clear `0x400164B0`, get `0x4001591E`.
- From our own reading [M], same block: micro timing `+256` (-23..+23), retrig settings `+320`, `+384`,
  `+448`, trig condition `+516`. Trig conditions are evaluated by `0x400913F0`.
- **Trig builder** `0x400548CE(track, pattern, sounds, step, flag, out)`, called by the sequencer once per
  step and track (`0x400551A6`) and by `0x40055AF4`.
- **MIDI out** [M]: note on `0x4008273C(channel, note, velocity)`, note off `0x400827A8`, CC
  `0x40082800(channel, cc, value)`, NRPN `0x40082848`; all go through `0x400826B0(length, bytes, port)`.
  USB packetiser (handles SysEx): `0x40003396(length, bytes)`. The MIDI out task is `0x4008A0BA`; it reads
  16-byte messages from the queue at `0x40FCB2EC` (posted with `0x40001FBA`).
- **Small files** on the internal storage: open `0x4007BC5E(path, mode, fh)`, read `0x4007BAAA`, write
  `0x4007BB0A`, close `0x4007BC1C`. Task context only.

## 7. Emulation

- There is no full-device emulator for the Models. digiemu boots the Digitakt mk1 and Digitone mk1 only.
- **Voice loop bench**: Modded-Cycles' `tools/emu/mcengine.py` runs `0x400A7D4A` on the real main OS with
  Unicorn. Stock Unicorn gets the EMAC wrong in signed fractional mode, so the bench emulates every EMAC
  instruction in Python: correct, about 100 times slower than real time. [MC] note 14 §4
- With Unicorn 2.1.4 built with **digiemu's six patches** and the CPU model `UC_CPU_M68K_CFV4E`, the Python
  EMAC can be switched off: the six stock machines then render **bit-identical** `.wav` files, 3 to 5 times
  faster than real time. With the model `UC_CPU_M68K_ANY` the same build renders wrong audio. [M]
- Modded-Cycles also has tests that run UI code paths (the MACHINES screen, the knob handler, the machine
  change) function by function with intercepted drawing. [MC] note 18 §8

## 8. Existing mods to coexist with

| mod | where it lives | what it touches that a loader would arbitrate |
|---|---|---|
| [elektron-model-tweaks](https://github.com/drumkilla/elektron-model-tweaks) | byte patches in section 3 | latching mute, trig preview, browser scroll, 16-channel USB audio |
| [Model-TG](https://github.com/TinyGregAudio/Model-TG) | blob at `0x401AB750`, boot hook | machine 6 (Sampler), the voice loop dispatch, the key accessor, extra parameters on PRESET + knob, the sound record |
| [Modded-Cycles](https://github.com/18nelli18/Modded-Cycles) | payload at `0x43000000` (or `0x46700000`), boot hook on `0x400004B2`, sprite masks | machines 6+ (Syntakt engines), the machine list and descriptors, a load governor in the voice loop, USB audio |
| this repository (beta firmware) | payload at `0x43000000`, boot hook on `0x400004B2`, the sprite mask `0x4016CAE8` | machines 6 and 7 (Plaits, Sophie), the machine list and descriptors (section 5.1). Not to be combined with the two above |

## 9. What we do not know

- `flash_at` / `flash_limit`, and anything else about the bootstrap beyond what [MC] note 17 says.
- Whether the Model:Samples' addresses differ from the Cycles' (very likely: its main OS is another build).
- How much stack the audio interrupt really leaves to a machine. From reading the OS (not measured on
  hardware): the interrupt does not switch stacks, the smallest task stack is 2 048 bytes, and the stock
  machines use about 250 bytes below the voice loop [M]. Our Plaits adapter therefore runs its engine on a
  stack of its own.
- Real CPU time of anything: all our costs are instruction counts in emulation.
- Whether an 8-character machine name fits the MACHINES screen. Model-TG shows 6- and 7-character names
  there, file names included [TG]; we rely on that for "Plaits" and "Sophie", which were not measured.
- Whether a project saved with machine 7 or 8 reloads as saved. [MC] note 20 reports a track that kept its
  added machine's number across a reflash, so the number is stored as it is.
