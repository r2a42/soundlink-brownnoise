#!/usr/bin/env python3
"""probe184_58k: probe184 with the 58,700-byte payload staged from period 1,320 (spares the region-A header)  (B02, round 3, 2026-10-12; built offline, NOT flashed.)

Payload: tools/brownnoise.py --rate 8000 --bytes 58700 --gen fft --loop --peak 0.985 --seed 63
(sha256 a488348bceea2b88fa35512fe4e304de3546b631fc4f62628eb9a599239ffa17); ROFS 58,968 B = 2,106 periods, 0 pad;
span data_us bytes 84,480..219,264 = 3,426 - 2,106 = 1,320 is the only start that fits.  Unlike probe184 (start 1,270)
the span holds no word of the E6 array, the region-B tail or the 30-word region-A header (V03 finding 1).  14.675 s
instead of 15.025 s.  Same press, same ids, same outcome table as probe184.

This file only names the variant; the cave is built by assemble_probe184.py (the shared engine), with the payload,
start period and verdict branch taken from narrow184_lib.PROBES['probe184_58k'].  Build: python build/hook/assemble_probe184_58k.py --build
Outputs: build/hook/probe184_58k_words.json, probe184_58k_brown.dfu, probe184_58k_cmd.txt.  The default probe184 / probe184a
images are untouched.  Hashes, gates and the full comparison: docs/deep/round3-2026-10-12/B02-payload-staging-final-size.md.
"""
import os, runpy
# preflight.redirect_edits() reads this literal from THIS file; the engine asserts it equals the bsr3 from the hook
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assemble_probe184.py"),
               run_name="__main__", init_globals={"ENGINE_VARIANT": "probe184_58k"})
