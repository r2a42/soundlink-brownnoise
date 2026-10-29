#!/usr/bin/env python3
"""probe257 = ladder rung 5r (= probe255's port-6 read and late DAC connect, PLUS the AUTOSTART id logger of probe256: a reproduction of 255) (see build/hook/ladder_ext.py)."""
STAGE = 5
VARIANT = 'r'
ALLFILL = True
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast); ladder_core.py defines the same values
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
import os
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder_core.py"), encoding="utf-8").read(), __file__, "exec"))
