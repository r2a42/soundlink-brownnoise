#!/bin/sh
# Compile the ADK 4.3.1 sink app to assembly, for tools/libscan.py --asm.
#
# The sink app needs 14 generated config headers, and generating them needs
# -hw/-sw BuildVariant names that exist in the module XML. The pair below is
# the speaker configuration; a wrong pair fails with
#   ExPatternArraySizeMismatch: Is "0" instead of "22"
# and passing all 45 module definitions instead of the 14 the makefile uses
# fails with KeyError: 'VREF'.
#
#   sh tools/gen-sink-asm.sh <output-dir>
set -e
OUT=${1:?usage: [HW=.. SW=..] gen-sink-asm.sh <output-dir>}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
A=$ROOT/adk/4.3.1/app/apps/sink
B=$ROOT/adk/4.3.1/bluelab73/app/tools
M=$A/module_configurations

MODULES="sink_a2dp sink_hfp_data sink_pio sink_private_data sink_button \
sink_inquiry sink_multi_channel sink_device_id sink_dut sink_volume \
sink_audio_routing sink_audio_prompts sink_tones sink_led"
DEFS=""
for m in $MODULES; do
    f=$M/$m'_module_def.xml'; [ -f "$f" ] || f=$M/$m'_def.xml'
    DEFS="$DEFS $f"
done

(cd "$A" && "$ROOT/adk/4.3.1/app/tools/bin/config_build.exe" -s BLUECORE \
    -g ./global_config.xml -ocd config_definition -o ./ $DEFS \
    -psk 6-49,150-199 -pm ./pskey_map.xml \
    -hw "${HW:-CE446}" -sw "${SW:-Speaker_with_TWS}" -l ./config_build.log)

mkdir -p "$OUT"
LIBINC=""
for d in "$ROOT"/adk/4.3.1/app/src/lib/*/; do LIBINC="$LIBINC -I$d"; done
ok=0
for f in "$A"/*.c; do
    n=$(basename "$f" .c)
    if "$B/bin/xap-local-xap-gcc-3.3.3" \
        -B"$B/lib/gcc-lib/xap-local-xap-assisted/3.3.3" \
        -mpu -mleaf-optim -mno-function-sizeof -mworkaround-b96516 -O -S \
        -I"$A" -I"$B/include/firmware" -I"$B/include/standard" $LIBINC \
        "$f" -o "$OUT/$n.s" 2>/dev/null; then ok=$((ok+1)); else rm -f "$OUT/$n.s"; fi
done
echo "compiled $ok of $(ls "$A"/*.c | wc -l) sink-app files into $OUT"
