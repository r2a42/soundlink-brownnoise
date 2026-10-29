#!/usr/bin/env python3
"""probe262 = ladder rung 5v with the FULL stock bring-up (0x1002 master/ratio payload, 0x10a0, 0x1001, 0x1070, 0x1071) before GO, so that the cold loudness matches the Bluetooth product (probe261 cold: rms 3700, warm product: rms 590) (see build/hook/ladder_ext.py)."""
STAGE = 5
VARIANT = 'v'
ALLFILL = True
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast); ladder_core.py defines the same values
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
import os
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder_core.py"), encoding="utf-8").read(), __file__, "exec"))
