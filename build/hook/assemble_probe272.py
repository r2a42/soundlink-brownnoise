#!/usr/bin/env python3
"""probe272 = ladder rung 5v (PRODUCT TEST 5: SPEAKX now also catches 0x10 'and' (DSP gone, seen on the unit), 0x25 and 0x3B (loop failures with a DSP loaded -> ENSURE); the 25-minute no-device run repeated) (see build/hook/ladder_ext.py)."""
STAGE = 5
VARIANT = 'v'
ALLFILL = True
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast); ladder_core.py defines the same values
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
import os
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder_core.py"), encoding="utf-8").read(), __file__, "exec"))
