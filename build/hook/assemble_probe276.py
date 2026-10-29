#!/usr/bin/env python3
"""probe276 = probe274 (the product, button row, level offset) with SIX new dead functions given stubs and fill only (fn_210d9 fn_8e9d fn_2f2ff fn_9cc0 fn_38dc4 fn_32b05): the confirmation that they are inert. The cave logic is probe274 exactly; nothing is placed in them."""
STAGE = 5
VARIANT = 'P'
ALLFILL = True
INERT_ONLY = (0x210D9, 0x8E9D, 0x2F2FF, 0x9CC0, 0x38DC4, 0x32B05)
PROBE_DEFLEV = 0
PROBE_GAIN_N = 12
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast); the first three are the hook (ladder_core.py asserts them), the rest are the button-table row 26 bytes
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5"), ("0xe90b8", "0x02"), ("0xe90ba", "0x04"), ("0xe90be", "0x04"), ("0xe90c0", "0x02"), ("0xe90c1", "0x00")]
import os
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder_core.py"), encoding="utf-8").read(), __file__, "exec"))
