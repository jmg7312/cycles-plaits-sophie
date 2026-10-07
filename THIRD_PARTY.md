# Third-party code

Copied unmodified (line endings normalised to LF), each with its licence file next to it.

## digi1_mods: the MACRO engines

- Files: `machines/macro/third_party/digi1_mods/` (`macro.c`, `macro.h`, `macro_tables.h`, `mono.c`,
  `mono.h`, `mono_tables.h`), from `mods/digimono/`.
- Source: <https://github.com/gdeo607/digi1_mods>, commit `c86c7f1ee8524dd9835d60b6d74a4777f806f07b`.
- Licence: MIT, Copyright (c) 2026 the digi1_mods authors (`LICENSE` in that folder).
- `macro.c` restates Plaits (<https://github.com/pichenettes/eurorack>, `plaits/dsp`) in fixed point:
  Copyright 2016 Emilie Gillet, MIT. The licence text is at the top of `macro.c` and `macro_tables.h`.
  Plaits is a Mutable Instruments product; this is an unofficial use of its published code, not affiliated
  with or endorsed by Mutable Instruments. The machine is called Plaits on the Model:Cycles' screen, after
  the code it carries (it was MACRO, digi1_mods' name, in the first versions of this repository).

## digisophie: Sophie for Digitakt

- Files: `machines/sophie/third_party/digisophie/` (`sophie.c`, `sophie.h`, `sophie_sin_table.inc`).
- Source: <https://github.com/soejrd/digisophie>, commit `961c39cec699e8f8940391634aaba9fad7120792`.
- Licence: MIT, Copyright (c) 2026 Matt Estela, Copyright (c) 2026 digisophie contributors (`LICENSE` in
  that folder).
- `sophie.c` is a fixed-point adaptation of Sophie for Schwung by Matt Estela
  (<https://github.com/mestela/schwung-sophie>), MIT.

## elektron-model-tweaks: the OS file format

- Files: `tools/mtlib/` (`aplib.py`, `container.py`, `syx.py`), used by `tools/make_firmware.py` and
  `test/test_firmware.py`.
- Source: <https://github.com/drumkilla/elektron-model-tweaks>, commit
  `7a240e6f59eae4baa70aa44e51a920a89c1806d7`.
- Licence: MIT, Copyright (c) 2026 drumkilla (`tools/mtlib/LICENSE`).

## Method, not code

- **Modded-Cycles** (<https://github.com/18nelli18/Modded-Cycles>, no licence file): how to add a machine to
  the Model:Cycles' list comes from its notes 17 to 20 and from reading its generators and tests: the boot
  hook and where the payload goes, the list of places that depend on the number of machines or of
  descriptors, which OS functions to run in emulation and what to intercept around them. That work was
  tested on hardware by its author. None of its code is in this repository: `firmware/`,
  `tools/make_firmware.py` and `test/test_firmware.py` are written from those facts (addresses, structures,
  expected bytes), and `docs/MODEL-CYCLES-NOTES.md` section 5.1 says where ours differs.
- **Model-TG** (<https://github.com/TinyGregAudio/Model-TG>, MIT): facts from its `docs/INTERNALS.md`, and
  the idea of a mod that builds its own firmware from the user's official file. No code taken.
- The few OS instructions that a hook replaces are done again by the hook (in the boot hook, the table
  builder detour, the MACHINES screen detour and the knob detour): that much of the OS's behaviour is restated
  in our assembly.

## Not included, used by the test

- Modded-Cycles (<https://github.com/18nelli18/Modded-Cycles>): its emulation bench
  `tools/emu/mcengine.py` (and, for `play_machines.py` and `stress_engine_switch.py`, its copy of
  `tools/mtlib`). The tests import them from your own checkout.
- No Elektron firmware or code is included: not in the sources, not in `prebuilt/` (our code and the MIT
  code above, compiled). The tool and the tests read your own official OS file.
