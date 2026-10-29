#!/usr/bin/env python3
"""probe288 = probe285 plus CENSUS (read-only diagnostic for the 'later long presses do nothing' failure): an idle centre long press that finds residue (mode flag, Kalimba sink, our busy hold, DAC link) speaks two digit prompts and changes nothing; a clean idle press and every ON-path press behave as probe285. Dropped for room (cave full): the stream-start yield (NOYIELD), LEAN, the 10-s watchdog (NOWATCH), DSPGUARD; OFFLOOP shrinks OFFALL. Kept: IDGUARD, SPEAKX."""
import os
os.environ.setdefault("SPAN", "80000"); os.environ.setdefault("CAPF", "0.7"); os.environ.setdefault("RANDASSIGN", "1")   # RANDASSIGN: probe288 randomises the cluster choice per layout seed (ladder_ext.place_once)
NEWFEAT = True
IDGUARD = True
CENSUS = True
NOYIELD = True
LEAN = True
NOWATCH = True
OFFLOOP = True
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
