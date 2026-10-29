#!/usr/bin/env python3
"""probe261 = ladder rung 5v (PRODUCT TEST 2: as 5u, one emulated press only when the mode is OFF; an SLC disconnect with the mode ON arms ENSURE, which restarts the noise 4 s later) (see build/hook/ladder_ext.py)."""
STAGE = 5
VARIANT = 'v'
ALLFILL = True
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast); ladder_core.py defines the same values
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
import os
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder_core.py"), encoding="utf-8").read(), __file__, "exec"))
