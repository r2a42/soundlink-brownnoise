#!/usr/bin/env python3
"""probe264 = ladder rung 5z (= 5y with the STOCK PLUGIN'S DAC GAIN: volume = high byte of (11,@0x72e), gain = fn_22a89(volume), fn_1f5bf(0, gain), instead of fn_1f512(0,0)) (see build/hook/ladder_ext.py)."""
STAGE = 5
VARIANT = 'z'
ALLFILL = True
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast); ladder_core.py defines the same values
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
import os
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder_core.py"), encoding="utf-8").read(), __file__, "exec"))
