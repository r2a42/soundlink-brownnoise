#!/usr/bin/env python3
"""probe254 = ladder rung 5m (TTS-style output wiring: Kalimba port 6 -> ONE codec sink StreamAudioSink(3,0,channel 2), no fn_1f04c) (see build/hook/ladder_ext.py)."""
STAGE = 5
VARIANT = 'm'
ALLFILL = True
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast); ladder_core.py defines the same values
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
import os
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder_core.py"), encoding="utf-8").read(), __file__, "exec"))
