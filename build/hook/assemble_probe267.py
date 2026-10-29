#!/usr/bin/env python3
"""probe267 = ladder rung 5F (= 5E with CONSTANT octal values 123, 456, 701 instead of the three RAM reads: bisects whether the reads or the nine delayed prompts killed the audio of 5D/5E) (see build/hook/ladder_ext.py)."""
STAGE = 5
VARIANT = 'F'
ALLFILL = True
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast); ladder_core.py defines the same values
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
import os
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder_core.py"), encoding="utf-8").read(), __file__, "exec"))
