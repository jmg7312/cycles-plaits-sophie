# Third-party code

Copied unmodified (line endings normalised to LF), each with its licence file next to it.

## digi1_mods: the fixed-point port of Plaits

- Files: `machines/plaits/third_party/digi1_mods/` (`macro.c`, `macro.h`, `macro_tables.h`, `mono.c`,
  `mono.h`, `mono_tables.h`), from `mods/digimono/`.
- Source: <https://github.com/gdeo607/digi1_mods>, commit `c86c7f1ee8524dd9835d60b6d74a4777f806f07b`.
- Licence: MIT, Copyright (c) 2026 the digi1_mods authors (`LICENSE` in that folder).
- `macro.c` restates Plaits (<https://github.com/pichenettes/eurorack>, `plaits/dsp`) in fixed point:
  Copyright 2016 Emilie Gillet, MIT. The licence text is at the top of `macro.c` and `macro_tables.h`.
  Plaits is a Mutable Instruments product; this is an unofficial use of its published code.

## digisophie: Sophie for Digitakt

- Files: `machines/sophie/third_party/digisophie/` (`sophie.c`, `sophie.h`, `sophie_sin_table.inc`).
- Source: <https://github.com/soejrd/digisophie>, commit `961c39cec699e8f8940391634aaba9fad7120792`.
- Licence: MIT, Copyright (c) 2026 Matt Estela, Copyright (c) 2026 digisophie contributors (`LICENSE` in
  that folder).
- `sophie.c` is a fixed-point adaptation of Sophie for Schwung by Matt Estela
  (<https://github.com/mestela/schwung-sophie>), MIT.

## Not included, used by the test

- Modded-Cycles (<https://github.com/18nelli18/Modded-Cycles>): its emulation bench
  `tools/emu/mcengine.py` and its `tools/mtlib`. The test imports them from your own checkout.
- No Elektron firmware or code is included. The test reads your own official OS file.
