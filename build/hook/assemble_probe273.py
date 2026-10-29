#!/usr/bin/env python3
"""probe273 = ladder rung 5W (= the product with the 10-s WATCHDOG, and a spoken test code when the watchdog intervenes: 1 = no DSP found, 2 = DSP loaded but no poll pending (dead loop)); the no-device run repeated) (see build/hook/ladder_ext.py)."""
import os
os.environ.setdefault("SPAN", "38000")   # the placer needs the wider cluster span for this image
STAGE = 5
VARIANT = 'W'
ALLFILL = True
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast); ladder_core.py defines the same values
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
import os
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder_core.py"), encoding="utf-8").read(), __file__, "exec"))
