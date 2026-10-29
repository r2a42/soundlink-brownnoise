#!/usr/bin/env python3
"""probe184_90k: probe184 with the 90,004-byte payload (J-D3 long alternative, 22.501 s)  (B02, round 3, 2026-10-12; built offline, NOT flashed.)

Payload: --bytes 90004 --gen fft --loop --peak 0.985 --seed 16 (T07 flat_22s, sha256
1006c1687304b5364956622a766fd40cf9445152bfac557332a2f290fe51c36f); ROFS 90,272 B = 3,224 periods, 0 pad; start 202
(the largest that fits: 3,426 - 3,224), span data_us bytes 12,928..219,264 = 94.0 percent of the file.  By the model NO
speech id survives any start (all 57 ids garbled), so the outcome ids are spoken from a damaged TTS: the pre-erase stops
(0x36 0x37 0x38) and the result id may be unintelligible.  Owner decision J-D3 only; not the recommendation.

This file only names the variant; the cave is built by assemble_probe184.py (the shared engine), with the payload,
start period and verdict branch taken from narrow184_lib.PROBES['probe184_90k'].  Build: python build/hook/assemble_probe184_90k.py --build
Outputs: build/hook/probe184_90k_words.json, probe184_90k_brown.dfu, probe184_90k_cmd.txt.  The default probe184 / probe184a
images are untouched.  Hashes, gates and the full comparison: docs/deep/round3-2026-10-12/B02-payload-staging-final-size.md.
"""
import os, runpy
# preflight.redirect_edits() reads this literal from THIS file; the engine asserts it equals the bsr3 from the hook
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assemble_probe184.py"),
               run_name="__main__", init_globals={"ENGINE_VARIANT": "probe184_90k"})
