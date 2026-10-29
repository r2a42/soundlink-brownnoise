#!/bin/sh
# Build the brown-noise app for CSR8670 (gordon) with the ADK in ../../adk/root
# (see ../../docs/toolchain.md). Output: ../build/csr8670/
#   image/                  filesystem contents (vm.app, brown_noise_kalimba/*.kap)
#   merge.xpv, merge.xdv    full flash image: CSR unsigned gordon stack + filesystem
#   brown_noise.psr         boot PIO state to apply by hand (README.md)
# Extra VM defines, e.g.: EXTRA_DEFS="-DAMP_ENABLE_PIO=<n>" ./build.sh
# (<n> is still unknown for this speaker; see README.md before using it)
set -e
here=$(cd "$(dirname "$0")" && pwd)
R=$(cd "$here/../../adk/root" && pwd)
out="$here/../build/csr8670"
export PATH="$R/tools/bin:$PATH"
make="$R/tools/bin/make.exe -R BLUELAB=$R/tools HARDWARE=gordon FLASHSIZE=16384"

# Start clean: sim captures of an older .kap are stale after a rebuild.
rm -rf "$out" && mkdir -p "$out"
cp "$here"/*.asm "$here"/*.c "$here"/*.mak "$here"/*.psr "$out"/
cd "$out"
$make -f brown_noise_kalimba.mak build
$make -f brown_noise.mak EXTRA_DEFS="$EXTRA_DEFS" build
ls -l merge.xpv merge.xdv brown_noise.psr image/vm.app image/brown_noise_kalimba/brown_noise_kalimba.kap
