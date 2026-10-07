/* The firmware payload: both machines, the machine-list code and its tables, in one piece.
 *
 *   .stub     the boot hook. It is written into the OS image itself, in a freed sprite mask (1 024 bytes of
 *             0xFF at 0x4016cae8; Modded-Cycles' notes 14 and 17), because it runs before the payload is in
 *             place.
 *   the rest  the payload, appended to the OS image (0x401aa140, its end) and copied by the boot hook to
 *             0x43000000: free SDRAM above the OS's BSS, the address Modded-Cycles uses for its payload.
 *             The copy includes .bss, as zeros.
 */
ENTRY(ml_boot)
EXTERN(ml_rows_area ml_ccrows)            /* read and written by the OS only: keep them */
_payload_src = 0x401aa140;
SECTIONS
{
  .stub 0x4016cae8 : { KEEP(*(.stub)) }

  . = 0x43000000;
  _start = .;
  .text   : { KEEP(*(.text.hooks))
              KEEP(*(.text.macro_cycles_render)) KEEP(*(.text.macro_cycles_update))
              KEEP(*(.text.sophie_cycles_render)) KEEP(*(.text.sophie_cycles_update))
              *(.text*) }
  . = ALIGN(4);
  _code_end = .;
  .rodata : { *(.rodata*) }
  . = ALIGN(4);
  .data   : { *(.data*) }
  . = ALIGN(4);
  .tables : { KEEP(*(.tables)) }
  . = ALIGN(4);
  _bss_start = .;
  .bss    : { *(.bss*) *(COMMON) }
  . = ALIGN(4);
  _end = .;
  _payload_longs = (_end - _start) / 4;
  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
