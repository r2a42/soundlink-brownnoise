#!/usr/bin/env python3
"""probe346 = the probe322 press-free WRITER (spoken 0x24 after a real write, 0x16 when p2 already holds it) with the SEAM-FIXED payload g10 build/payload/g10/brown_48000_58968_seamfix160_f480_b.adpcm (sha256 6ea4564a776320feb0146840db0a15dc1367f52e7cef52b0144e28e7e8f95c36, first 4 bytes f7 ff 72 6b): the g8 payload whose last 480 samples before the speaker's early cut point (160 samples before the end) fade to zero and whose last 160 samples are zero (tools/seamfix.py); the first nibble changed 7 -> 15 (0x77 -> 0xF7: same ADPCM index delta, only a constant -22 LSB offset; the 7 -> 6 change of probe344 shifted the whole step path and was WRONG) so that the writer's first-four-bytes check differs from the g9 payload now in p2 and the write happens without a test writer first. Gate: WRITER_PAYLOAD_FILE=build/payload/g10/brown_48000_58968_seamfix160_f480_b.adpcm WRITER_PAYLOAD_SHA=6ea4564a776320feb0146840db0a15dc1367f52e7cef52b0144e28e7e8f95c36 WRITER_ID_WRITTEN_HEX=24 WRITER_ID_PRESENT_HEX=16 WRITER_WORDS=probe346 python build/hook/gate_probe320.py"""
import os
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast): the same as assemble_probe320.py
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
os.environ.setdefault("WRITER_ID_WRITTEN", "0x24")
os.environ.setdefault("WRITER_ID_PRESENT", "0x16")
os.environ.setdefault("WRITER_PAYLOAD_FILE", "build/payload/g10/brown_48000_58968_seamfix160_f480_b.adpcm")
os.environ.setdefault("WRITER_PAYLOAD_SHA", "6ea4564a776320feb0146840db0a15dc1367f52e7cef52b0144e28e7e8f95c36")
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assemble_probe320.py"), encoding="utf-8").read(), __file__, "exec"))
