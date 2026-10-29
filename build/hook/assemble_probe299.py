#!/usr/bin/env python3
"""probe299 = probe298 with the EVGUARD DSP test corrected (docs/deep/material-2026-10-19/BH-probe299-evguard-fixed.md): the fourth condition is no longer StreamKalimbaSink(3) == 0 (never true, BG section 12) but TransformFromSource(StreamSourceFromSink(StreamKalimbaSink(5))) == 0, i.e. the DAC link chain made by fn_1f04c is gone (disposed by a stock KalimbaLoad/KalimbaPowerOff). Clear @0x6d1 bit 15 iff the audio-busy word is 0, @0x72f == 0, @0x72e == 0 and that chain does not exist. Placed in the AY batch A pool; probe297 must be confirmed inert first. Built offline 2026-10-19; NOT flashed."""
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
