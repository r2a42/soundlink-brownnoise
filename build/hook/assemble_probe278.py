#!/usr/bin/env python3
"""probe278 = TEST build (variant v, the connect event 0x4753 stands in for the press) of the probe277 product logic with the L1a hardening (OFFALL cancels every pending message and poll, stage-B and auto-start mode guards, refused load = OFF + one prompt, audio-busy guard in ENSURE, MUTE only with a DSP on port 3) and the fifth batch of dead functions."""
import os
os.environ.setdefault("SPAN", "80000"); os.environ.setdefault("CAPF", "0.7")
NEWFEAT = True
STAGE = 5
VARIANT = 'v'
ALLFILL = True
PROBE_DEFLEV = 0
PROBE_GAIN_N = 12
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast); the first three are the hook (ladder_core.py asserts them), the rest are the button-table row 26 bytes
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5"), ("0xe90b8", "0x02"), ("0xe90ba", "0x04"), ("0xe90be", "0x04"), ("0xe90c0", "0x02"), ("0xe90c1", "0x00")]
import os
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder_core.py"), encoding="utf-8").read(), __file__, "exec"))
