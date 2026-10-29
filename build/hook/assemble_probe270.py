#!/usr/bin/env python3
"""probe270 = THE PRODUCT (variant P): the centre long press starts the noise on a cold speaker (no Bluetooth device needed) or on a loaded DSP; self-healing after a Bluetooth disconnect; no test emulation (a connect event does NOT start the noise) (see build/hook/ladder_ext.py)."""
STAGE = 5
VARIANT = 'P'
ALLFILL = True
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast); ladder_core.py defines the same values
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
import os
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder_core.py"), encoding="utf-8").read(), __file__, "exec"))
