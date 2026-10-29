#!/usr/bin/env python3
"""probe189: PB, the SILENT product build (B01, 2026-10-12; built offline, NOT flashed).

This is probe188 (PBd, the diagnostic build) with the mechanical edit "every spoken id becomes a plain leavel":
the nine tail entry points QSTATE QPLUG NOSINK NODIR NOFILE NOSRC NOPLAY GONE SAY are each one `leavel -8` and every
other word of the tail (and every connector inside it) is dropped.  Every word before the tail is bit-identical to
probe188's, and the build asserts it, asserts that no decoded bsr in the image targets SPEAK (0xDF7F), and asserts
that no cave word lies in the code region.  Read assemble_probe188.py (docstring, outcome and id tables) and
docs/deep/round3-2026-10-12/B01-product-build-probes.md first; run assemble_probe188.py BEFORE this file (the
equivalence check reads build/hook/probe188_words.json).

    python build/hook/assemble_probe188.py [--build]
    python build/hook/assemble_probe189.py [--build]
"""
import os, runpy
# preflight.redirect_edits() reads this literal from THIS file; the engine asserts it equals the bsr3 from the hook
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assemble_probe188.py"),
               run_name="__main__", init_globals={"ENGINE_VARIANT": "probe189"})
