#!/usr/bin/env python3
"""probe184a_58k: probe184a staged from period 1,320 (the 184a that pairs with probe184_58k)  (B02, round 3, 2026-10-12; built offline, NOT flashed.)

Same 2,532-byte payload and 100 periods as probe184a, but the span is data_us bytes 84,480..90,880, which holds no word
of the E6 array, the region-B tail or the region-A header (V03: start period 1,320).  Pair it with probe184_58k, whose
first 100 periods are exactly this span.  Same press, same outcome table as probe184a.

This file only names the variant; the cave is built by assemble_probe184.py (the shared engine), with the payload,
start period and verdict branch taken from narrow184_lib.PROBES['probe184a_58k'].  Build: python build/hook/assemble_probe184a_58k.py --build
Outputs: build/hook/probe184a_58k_words.json, probe184a_58k_brown.dfu, probe184a_58k_cmd.txt.  The default probe184 / probe184a
images are untouched.  Hashes, gates and the full comparison: docs/deep/round3-2026-10-12/B02-payload-staging-final-size.md.
"""
import os, runpy
# preflight.redirect_edits() reads this literal from THIS file; the engine asserts it equals the bsr3 from the hook
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assemble_probe184.py"),
               run_name="__main__", init_globals={"ENGINE_VARIANT": "probe184a_58k"})
