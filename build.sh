#!/bin/bash
# Build the MACRO and Sophie machines for the Model:Cycles (ColdFire MCF5441x).
# Needs: m68k-linux-gnu-gcc and binutils (Debian/Ubuntu: apt install gcc-m68k-linux-gnu binutils-m68k-linux-gnu),
# or set CROSS=m68k-elf- .
# Output: build/macro.{elf,bin,sym} and build/sophie.{elf,bin,sym}, each linked alone at 0x43000000 (for
# test/play_machines.py), and the firmware payload, see the end of this file.
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

# The firmware payload (tools/make_firmware.py): both machines and the machine-list code linked together at
# 0x43000000, and the boot hook. Output: build/payload.{elf,bin,sym} and build/stub.bin.
F=firmware
${CROSS}gcc $CFLAGS -I$F -c $F/machine_list.c -o build/machine_list.o
${CROSS}gcc -mcpu=54418 -I$F -c $F/hooks.S -o build/hooks.o
${CROSS}ld -T $F/link.ld --gc-sections --no-warn-rwx-segments -o build/payload.elf \
    build/hooks.o build/machine_list.o build/macro_cycles.o build/macro.o \
    build/sophie_cycles.o build/sophie.o build/mono.o
if [ -n "$(${CROSS}nm -u build/payload.elf)" ]; then echo "undefined symbols in payload"; exit 1; fi
${CROSS}nm -n build/payload.elf > build/payload.sym
${CROSS}objcopy -O binary -j .text -j .rodata -j .data -j .tables build/payload.elf build/payload.bin
${CROSS}objcopy -O binary -j .stub build/payload.elf build/stub.bin
echo "payload: $(stat -c %s build/payload.bin) bytes in the file, $(${CROSS}size -A build/payload.elf | awk '/\.bss/{print $2}') of state; boot hook $(stat -c %s build/stub.bin) bytes"
# ./build.sh --prebuilt also refreshes prebuilt/, the copy make_firmware.py uses by default.
if [ "$1" = "--prebuilt" ]; then
    cp build/payload.bin build/stub.bin build/payload.sym prebuilt/
    (cd prebuilt && sha256sum payload.bin stub.bin payload.sym > SHA256SUMS)
    echo "prebuilt/ refreshed"
fi
