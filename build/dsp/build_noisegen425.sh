#!/bin/bash
# build_noisegen425.sh: noisegen425.asm -> kas -> klink -> kobjcopy -> compact -> build/dsp/noisegen425.bin (probe425; same steps as build_noisegen2.sh without the generator script)
set -e
cd "$(dirname "$0")/../.."
T=adk/root/tools/bin
W=$(mktemp -d); cp build/dsp/noisegen425.asm build/dsp/gen.link $W/
( cd $W && "$OLDPWD/$T/kas.exe" -DGORDON -DKAL_ARCH3 -DKALASM3 -g -mchip=gordon noisegen425.asm -o n425.o && "$OLDPWD/$T/klink.exe" -o n425.elf -Tgen.link n425.o && "$OLDPWD/$T/kobjcopy.exe" -O binary n425.elf n425_raw.bin )
cp $W/n425.o build/dsp/noisegen425.o; cp $W/n425.elf build/dsp/noisegen425.elf; cp $W/n425_raw.bin build/dsp/noisegen425_raw.bin
python build/dsp/compact.py noisegen425_raw.bin noisegen425.bin | head -1
