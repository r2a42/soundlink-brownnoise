#!/usr/bin/env python3
"""probe295 = probe285 (the product: NEWFEAT, DSPGUARD, IDGUARD) plus the four fixes of docs/deep/material-2026-10-19/AH-cave-review.md section 6: F2 CLEARDAC (clear the stale @0x6d1 bit 15 before the cold fn_1f04c DAC connect), F1 CONSUME (the probe197 consume lever on the stock 0x4004 path: no beep, no park, no 0x4018), F3 FAILOFF (PL_DAC / PL_ID / GG_BAD switch the mode OFF and speak 0x3D / 0x3C), F4 CANCELALL (OFFLOOP with the library MessageCancelAll 0x395e7). Details, words, gates, press page, rollback: docs/deep/material-2026-10-19/AJ-probe295-fix.md. Built offline 2026-10-19; NOT flashed."""
import os
os.environ.setdefault("SPAN", "80000"); os.environ.setdefault("CAPF", "0.7"); os.environ.setdefault("RANDASSIGN", "1"); os.environ.setdefault("SEEDS", "3000")   # RANDASSIGN: the cluster choice is randomised per layout seed (as probe288); the first seed that places is 1336
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
PROBE_DEFLEV = 0
PROBE_GAIN_N = 12
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast); the first three are the hook (ladder_core.py asserts them), the rest are the button-table row 26 bytes
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5"), ("0xe90b8", "0x02"), ("0xe90ba", "0x04"), ("0xe90be", "0x04"), ("0xe90c0", "0x02"), ("0xe90c1", "0x00")]
import os
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder_core.py"), encoding="utf-8").read(), __file__, "exec"))
