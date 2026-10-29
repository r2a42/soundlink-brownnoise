#!/usr/bin/env python3
"""probe321 = the probe320 press-free WRITER with the OTHER pinned payload (the compensated 48 kHz payload of writer probe314, sha256 b0a30146...). A hardware TEST image for the write path:
a speaker whose p2 holds the probe320 payload (first 4 bytes 77 ff 72 6b) must WRITE this one on boot (first 4 bytes 77 7f f8 09 differ) and speak 0x30; flashing probe320 afterwards must write the
other payload back. Everything else is assemble_probe320.py (the same cave, gate: WRITER_PAYLOAD_FILE=... WRITER_PAYLOAD_SHA=... WRITER_WORDS=probe321 python build/hook/gate_probe320.py)."""
import os
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast): the same as assemble_probe320.py
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
os.environ.setdefault("WRITER_PAYLOAD_FILE", "build/payload/g7/brown_48000_58968_comp.adpcm")
os.environ.setdefault("WRITER_PAYLOAD_SHA", "b0a3014643b512d315075b0c169fcfb04e815299e7f751eacf3fc987def91b87")
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assemble_probe320.py"), encoding="utf-8").read(), __file__, "exec"))
