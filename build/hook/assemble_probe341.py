#!/usr/bin/env python3
"""probe341 = the probe322 press-free WRITER (spoken 0x24 after a real write, 0x16 when p2 already holds it) with the SEAM-FIXED payload build/payload/g9/brown_48000_58968_periodic96.adpcm (sha256 d233cbf0628c2f57bd43b175995c33a79a12319fbdf2bc3bce89d3e7288dd60a, first 4 bytes 77 ff 72 6b): the g8 lfd10L payload with only its last 93 samples (about 2 ms) re-encoded by a DP so the ADPCM decoder ends in state (0,0), the state every rebuild restarts from (owner 2026-10-25: option 1, the seam fix). Because the first 4 bytes equal the g8 payload's, flash probe321 first (it writes the other payload), then this. Gate: WRITER_PAYLOAD_FILE=build/payload/g9/brown_48000_58968_periodic96.adpcm WRITER_PAYLOAD_SHA=d233cbf0628c2f57bd43b175995c33a79a12319fbdf2bc3bce89d3e7288dd60a WRITER_ID_WRITTEN_HEX=24 WRITER_ID_PRESENT_HEX=16 WRITER_WORDS=probe341 python build/hook/gate_probe320.py"""
import os
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast): the same as assemble_probe320.py
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
os.environ.setdefault("WRITER_ID_WRITTEN", "0x24")
os.environ.setdefault("WRITER_ID_PRESENT", "0x16")
os.environ.setdefault("WRITER_PAYLOAD_FILE", "build/payload/g9/brown_48000_58968_periodic96.adpcm")
os.environ.setdefault("WRITER_PAYLOAD_SHA", "d233cbf0628c2f57bd43b175995c33a79a12319fbdf2bc3bce89d3e7288dd60a")
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assemble_probe320.py"), encoding="utf-8").read(), __file__, "exec"))
