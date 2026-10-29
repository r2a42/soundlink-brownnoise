#!/usr/bin/env python3
"""probe298 = probe296 behaviour plus EVGUARD (docs/deep/material-2026-10-19/AU-stale-dac-design.md section 5, with the extra @0x72e call-plugin test): at the top of EVTX the stale @0x6d1 bit 15 is cleared when the audio-busy word is 0, @0x72f == 0, @0x72e == 0 and StreamKalimbaSink(3) == 0. The new code is placed in the AY batch A dead-pool functions (fn_38a24, fn_1df56, fn_12ee8; AYPOOL = True makes ladder_ext add their writable runs as bands), which probe297 must confirm inert first. Details: BC-probe298-evguard.md. Built offline 2026-10-19; NOT flashed."""
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
