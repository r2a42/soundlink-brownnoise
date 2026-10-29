#!/usr/bin/env python3
"""probe305 = the PRODUCT for the 24 kHz noise (docs/deep/material-2026-10-19/BW-24k-pair.md): probe303 with RATE 24000 (the 0x1072 tone-rate word), PAYLOAD_FIRST4 for build/payload/g4/brown_24000_58968_ns.adpcm (pair with the writer probe304), FIRST_POLL 4600 (the 24 kHz chunk is 2 x 58,968 / 24,000 = 4,914 ms) and RELEASE_MS 16000 unchanged (still above the 14,742 ms an 8 kHz-played first chunk would last). Everything else is probe303 (which was probe302 with the ORIGINAL payload check; probe302 was probe301 + G5ZAP). Built offline 2026-10-20; NOT flashed."""
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
PAYLOAD_FIRST4 = (0x77, 0x77, 0x67, 0x5A)
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
