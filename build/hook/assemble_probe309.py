#!/usr/bin/env python3
"""probe309 = the PRODUCT for the smooth-loop pair (docs/deep/material-2026-10-19/BY-smooth-loop.md): probe307 with ONLY PAYLOAD_FIRST4 changed, (0x7F,0x16,0xC1,0x09), for build/payload/g6/brown_24000_58968_fade12.adpcm (the 12 ms raised-cosine faded payload; pair with the writer probe308). RATE 24000, FIRST_POLL 4600, the 50-ms busy re-poll and RELEASE_MS 16000 are exactly probe307's: a fine-poll variant was built and dropped (BY doc section 3: the end-detector delay, not the poll grid, dominates the join, and a 10-ms poll would need the cavesim R5 floor lowered). Built offline 2026-10-21; NOT flashed."""
import os
os.environ.setdefault("SPAN", "80000"); os.environ.setdefault("CAPF", "0.7"); os.environ.setdefault("RANDASSIGN", "1"); os.environ.setdefault("SEEDS", "3000")   # as probe296 (layout seed 1336)
NEWFEAT = True
DSPGUARD = True
IDGUARD = True
CONSUME = True
CLEARDAC = True
FAILOFF = True
OFFLOOP = True
CANCELALL = True
STAGE = 5
VARIANT = 'P'
ALLFILL = True
AYBATCH = 'A'
AYPOOL = True
EVGUARD = True
EVGCHAIN = True
G5ZAP = True
PAYLOAD_RATE = 24000
PAYLOAD_FIRST_POLL = 4600
PAYLOAD_RELEASE_MS = 16000
PAYLOAD_FIRST4 = (0x7F, 0x16, 0xC1, 0x09)
PROBE_DEFLEV = 0
PROBE_GAIN_N = 15
PROBE_RATIO_EVEN = 0x0F
PROBE_RATIO_ODD = 0x15
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast); the first three are the hook (ladder_core.py asserts them), the rest are the button-table row 26 bytes
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5"), ("0xe90b8", "0x02"), ("0xe90ba", "0x04"), ("0xe90be", "0x04"), ("0xe90c0", "0x02"), ("0xe90c1", "0x00")]
import os
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder_core.py"), encoding="utf-8").read(), __file__, "exec"))
