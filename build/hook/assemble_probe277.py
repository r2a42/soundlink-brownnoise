#!/usr/bin/env python3
"""probe277 = THE PRODUCT (variant P) with the probe275 logic: power-off (0x4002) stops the noise, MUTE on every OFF, YIELD to a streaming phone when the DSP is ours (cold-owned flag), 4-s watchdog; plus probe274 button-table row 26 and the level offset."""
import os
os.environ.setdefault("SPAN", "80000"); os.environ.setdefault("CAPF", "0.8")
NEWFEAT = True
STAGE = 5
VARIANT = 'P'
ALLFILL = True
PROBE_DEFLEV = 0
PROBE_GAIN_N = 12
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast); the first three are the hook (ladder_core.py asserts them), the rest are the button-table row 26 bytes
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5"), ("0xe90b8", "0x02"), ("0xe90ba", "0x04"), ("0xe90be", "0x04"), ("0xe90c0", "0x02"), ("0xe90c1", "0x00")]
import os
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder_core.py"), encoding="utf-8").read(), __file__, "exec"))
