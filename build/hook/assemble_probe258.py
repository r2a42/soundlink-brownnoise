#!/usr/bin/env python3
"""probe258 = ladder rung 5s (J33: read PIO5/PIO12, send the stock amp-on message 0x7023 to task 0x72c 3 s after GO, read again) (see build/hook/ladder_ext.py)."""
STAGE = 5
VARIANT = 's'
ALLFILL = True
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast); ladder_core.py defines the same values
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
import os
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder_core.py"), encoding="utf-8").read(), __file__, "exec"))
