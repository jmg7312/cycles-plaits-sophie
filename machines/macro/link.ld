/* MACRO machines: code, tables and state in one piece at 0x43000000 (free SDRAM above the OS's BSS,
 * the address Modded-Cycles uses for its payload). For the emulation test; the final placement is up to
 * the firmware builder. */
ENTRY(macro_cycles_render)
SECTIONS
{
  . = 0x43000000;
  _start = .;
  .text   : { KEEP(*(.text.macro_cycles_render)) KEEP(*(.text.macro_cycles_update_*)) *(.text*) }
  . = ALIGN(4);
  _code_end = .;
  .rodata : { *(.rodata*) }
  . = ALIGN(4);
  .data   : { *(.data*) }
  . = ALIGN(4);
  _bss_start = .;
  .bss    : { *(.bss*) *(COMMON) }
  . = ALIGN(4);
  _end = .;
  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
