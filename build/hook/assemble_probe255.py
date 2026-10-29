#!/usr/bin/env python3
"""probe255 = ladder rung 5p (output-content probe: port 6 is read BEFORE the DAC is connected, then the DAC is connected late) (see build/hook/ladder_ext.py)."""
STAGE = 5
VARIANT = 'p'
ALLFILL = True
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast); ladder_core.py defines the same values
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
import os
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder_core.py"), encoding="utf-8").read(), __file__, "exec"))
