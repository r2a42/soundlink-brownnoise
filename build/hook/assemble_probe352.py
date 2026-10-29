#!/usr/bin/env python3
"""probe352 = the probe322 press-free WRITER (spoken 0x24 after a real write, 0x16 when p2 already holds it) with the NATIVE 32 kHz payload build/payload/g8/brown_32000_58968_lfd10L.adpcm (sha256 563ef73602cfb33a087e7ee128bdd57688fc5e8cf8b7922753133dbe5ff8942c, first 4 bytes 7f f7 7f 16; made by docs/deep/material-2026-10-19/hx-coverage/mk48_lf.py 32000 with ROT=local DIP_DB=-10 DIP_HALF_MS=40 = the recipe of the 48 kHz payload lfd10L at 32 kHz; owner order 2026-10-27: iterate for clean noise; the lower rate removed the timeline steps in probe350). Gate: WRITER_PAYLOAD_FILE=build/payload/g8/brown_32000_58968_lfd10L.adpcm WRITER_PAYLOAD_SHA=563ef73602cfb33a087e7ee128bdd57688fc5e8cf8b7922753133dbe5ff8942c WRITER_ID_WRITTEN_HEX=24 WRITER_ID_PRESENT_HEX=16 WRITER_WORDS=probe352 python build/hook/gate_probe320.py"""
import os
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast): the same as assemble_probe320.py
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
os.environ.setdefault("WRITER_ID_WRITTEN", "0x24")
os.environ.setdefault("WRITER_ID_PRESENT", "0x16")
os.environ.setdefault("WRITER_PAYLOAD_FILE", "build/payload/g8/brown_32000_58968_lfd10L.adpcm")
os.environ.setdefault("WRITER_PAYLOAD_SHA", "563ef73602cfb33a087e7ee128bdd57688fc5e8cf8b7922753133dbe5ff8942c")
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assemble_probe320.py"), encoding="utf-8").read(), __file__, "exec"))
