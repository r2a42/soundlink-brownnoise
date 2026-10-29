#!/bin/sh
# Run brown_noise_kalimba.kap in the ADK's CSR8670 DSP simulator for a
# fixed wall-clock time, capture both DAC ports, and compare them with the
# bit-exact model. Needs ./build.sh first. Kalsim sends the VM "go"
# message itself. Usage: ./sim.sh [seconds, default 20]
set -e
here=$(cd "$(dirname "$0")" && pwd)
out="$here/../build/csr8670"
kalsim="$here/../../adk/root/tools/kalsim/kalsim_csr8670.exe"
rm -f "$out"/sim_left.raw "$out"/sim_right.raw
# kalsim runs until killed, so timeout's 124 is the normal exit. Anything
# else means it failed or quit early.
status=0
timeout "${1:-20}" "$kalsim" -n -q -e -m --deny-external \
    -o 0 "$(cygpath -w "$out/sim_left.raw")" r=768000 \
    -o 1 "$(cygpath -w "$out/sim_right.raw")" r=768000 \
    "$(cygpath -w "$out/brown_noise_kalimba.kap")" || status=$?
if [ "$status" -ne 124 ]; then
    echo "kalsim exited with $status before the time limit" >&2
    exit 1
fi
python "$here/model.py" --compare "$out/sim_left.raw" "$out/sim_right.raw"
