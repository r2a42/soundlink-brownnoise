#!/usr/bin/env python3
"""probe427 = probe426 + PWRREL (the power-off event 0x4002 releases the cave's audio-busy hold at once, mode ON or OFF; +3 cave words; docs/deep/poweroff-with-noise-2026-10-30.md). Owner 2026-10-30 on probe425: "When I power off with noise playing, it takes two more presses (with a gap between them) to power back on normally." Everything else = probe426: probe425 sound (noisegen425.bin, 67 PM words) with PROBE_NLEV 12. Built OFFLINE, NOT flashed."""
import os
os.environ.setdefault("SPAN", "30000"); os.environ.setdefault("CAPF", "1.0"); os.environ.setdefault("RANDASSIGN", "1"); os.environ.setdefault("SEEDS", "60000"); os.environ.setdefault("FILLGAPS", "1"); os.environ.setdefault("REQPIN", "1")   # layout search is deterministic: the first placing seed per stage (9 / 875 / 0) is taken; a rebuild is byte-identical (see the docstring)
NEWFEAT = True
TABLEX = True
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
AYBATCH = 'ABCD'
AYPOOL = True
EVGUARD = True
EVGCHAIN = True
G5ZAP = True
NOPURGE = True
GEN = True
STARTWAIT = True
SILENTDROP = True
NOREWR = True
NOISEGEN_BIN = "build/dsp/noisegen425.bin"
CANCEL670B = True
TIMERS = True
PAYLOAD_RATE = 48000
LEDDARK = True
TMREARM = True
PAYLOAD_RELEASE_MS = 16000
PROBE_DEFLEV = 6
PROBE_FINE_ZERO = True
PROBE_FINE = True
PROBE_NLEV = 12
PWRREL = True
PROBE_SHIFT_BASE = 0
PROBE_FINE_R0 = 30
SCAN = True
BTDROP = True
AYMAIN = True
PROBE_GAIN_N = 15
PROBE_RATIO_EVEN = 0x0F
PROBE_RATIO_ODD = 0x15
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast); the first three are the hook (ladder_core.py asserts them), the rest are the button-table row 26 bytes
SYNTH_TRAPS = []
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5"), ("0xe90b8", "0x02"), ("0xe90ba", "0x04"), ("0xe90be", "0x04"), ("0xe90c0", "0x02"), ("0xe90c1", "0x00")]
import os
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder_core.py"), encoding="utf-8").read(), __file__, "exec"))
