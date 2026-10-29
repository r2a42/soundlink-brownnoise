#!/usr/bin/env python3
"""probe269 = ladder rung 5v (PRODUCT TEST 3: probe261's self-healing product handler with the MINIMAL bring-up and the constant stock DAC gain of probe268) (see build/hook/ladder_ext.py)."""
STAGE = 5
VARIANT = 'v'
ALLFILL = True
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast); ladder_core.py defines the same values
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
import os
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder_core.py"), encoding="utf-8").read(), __file__, "exec"))
