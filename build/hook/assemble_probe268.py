#!/usr/bin/env python3
"""probe268 = ladder rung 5G (= probe259's cold loop with a CONSTANT stock DAC gain: fn_22a89(10) = -15 dB via fn_1f5bf(0, gain), meant to match the Bluetooth product's level (rms ~590 vs 3700 unattenuated)) (see build/hook/ladder_ext.py)."""
STAGE = 5
VARIANT = 'G'
ALLFILL = True
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast); ladder_core.py defines the same values
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
import os
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder_core.py"), encoding="utf-8").read(), __file__, "exec"))
