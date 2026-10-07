#!/bin/bash
# Build the MACRO and Sophie machines for the Model:Cycles (ColdFire MCF5441x).
# Needs: m68k-linux-gnu-gcc and binutils (Debian/Ubuntu: apt install gcc-m68k-linux-gnu binutils-m68k-linux-gnu),
# or set CROSS=m68k-elf- .
# Output: build/macro.{elf,bin,sym} and build/sophie.{elf,bin,sym}, linked at 0x43000000.
set -e
cd "$(dirname "$0")"
CROSS=${CROSS:-m68k-linux-gnu-}
CFLAGS="-mcpu=54418 -O2 -ffreestanding -fno-builtin -nostdlib -fno-pic -fno-pie -fno-common \
        -ffunction-sections -fdata-sections -fomit-frame-pointer -Wall"
P=machines/macro
S=machines/sophie
D1=$P/third_party/digi1_mods
DS=$S/third_party/digisophie
mkdir -p build

${CROSS}gcc $CFLAGS -I$D1 -c $P/macro_cycles.c -o build/macro_cycles.o
${CROSS}gcc $CFLAGS -I$D1 -c $D1/macro.c -o build/macro.o
${CROSS}gcc $CFLAGS -I$D1 -c $D1/mono.c -o build/mono.o
${CROSS}ld -T $P/link.ld --gc-sections --no-warn-rwx-segments -o build/macro.elf \
    build/macro_cycles.o build/macro.o build/mono.o

${CROSS}gcc $CFLAGS -I$DS -c $S/sophie_cycles.c -o build/sophie_cycles.o
${CROSS}gcc $CFLAGS -I$DS -c $DS/sophie.c -o build/sophie.o
${CROSS}ld -T $S/link.ld --gc-sections --no-warn-rwx-segments -o build/sophie.elf \
    build/sophie_cycles.o build/sophie.o build/mono.o

for m in macro sophie; do
    ${CROSS}nm -n build/$m.elf > build/$m.sym
    ${CROSS}objcopy -O binary build/$m.elf build/$m.bin
    if [ -n "$(${CROSS}nm -u build/$m.elf)" ]; then echo "undefined symbols in $m"; exit 1; fi
    echo "$m: $(${CROSS}size -A build/$m.elf | awk '/\.text/{t=$2} /\.rodata/{r=$2} /\.bss/{b=$2} END{print t" bytes of code, "r" of tables, "b" of state (6 voices)"}')"
done
