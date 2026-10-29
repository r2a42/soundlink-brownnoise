#!/usr/bin/env python3
"""probe310 = probe307 with a WINDOWED FAST POLL (docs/deep/material-2026-10-19/BZ-fast-poll-probe310.md). PRODUCT ONLY: the payload is probe307's (the compensated 24 kHz payload written by writer probe306; FIRST4 77 FF 7A 37), no writer press. Two constants differ from probe307: PAYLOAD_FIRST_POLL 4880 (was 4600: the first poll now lands 20 ms before the earliest observed free instant, about 4,900 ms after the build) and PAYLOAD_BUSY_POLL 10 (was the 50-ms POLL_SHORT: the BUSY re-poll only). RATE 24000 and RELEASE_MS 16000 as probe307. The cavesim rule R5 floor (default 50 ms) is lowered to 10 for THIS image's gates only (GATE_POLL_FLOOR=10; owner approval 2026-10-21); no other gate is changed. Built offline 2026-10-21; NOT flashed."""
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
PAYLOAD_FIRST_POLL = 4880
PAYLOAD_BUSY_POLL = 10
PAYLOAD_RELEASE_MS = 16000
PAYLOAD_FIRST4 = (0x77, 0xFF, 0x7A, 0x37)
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
