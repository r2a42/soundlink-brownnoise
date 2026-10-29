#!/usr/bin/env python3
"""probe300 = probe299 + a READ-ONLY G5 report (docs/deep/material-2026-10-19/BN-probe300-g5-diag.md). On the yield path only (a stream start 0x4758 while the noise runs, the EVTX yield turns it OFF) it speaks ONE digit D 36 s later (= 20 s after the yield release at +16 s): D = blk[24] + 5 * (@0x73e bit 6, BDSP "ready" = the VM unmute ran), as battery (D+1)*10 percent, only when the mode is OFF. No stock call, no write: it changes no audio behaviour. Words only in the AY batch A pool and the leftover fill of the twelve confirmed functions, plus the HANDLER bsr retarget. A two-digit version (G5TWO in ladder_ext.py) does not fit batch A. Built offline 2026-10-19; NOT flashed."""
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
G5DIAG = True
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
