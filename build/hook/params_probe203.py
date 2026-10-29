"""probe203 PARAMETER BLOCK -- FILLED IN 2026-10-15 from the probe202 result (shift +1 at EVERY start on the stock file; no alignment dependence).
Read by build/hook/assemble_probe203.py and build/hook/gate_probe203.py. Note: docs/deep/material-2026-10-13/I1-probe203.md (supersedes the template of H1-prep-203-198c.md).
(The H1 template block is kept in build/hook/h1_templates/params_probe203_template.py.)

WINDOWS : 1..3 windows, each (drops of 64, one extra drop, CTL_POS, SECOND_POS, THIRD_POS): window start = 64 * drops + extra; CTL_POS = file position of the
          CONTROL pair; SECOND_POS = CTL_POS + 4 (the "second" pair, read from the STAGED file: stock bytes outside the span, payload bytes inside it);
          THIRD_POS = file position of a STOCK pair (read from the stock file) that must NOT be there if the file is staged (inside the span), or None (an
          impossible pair, NOPAIR, is searched: the class 2 / 5 then cannot occur). The two-byte pairs are searched in elements 0..99 of ONE fresh map, masked & 0xFF.
Class per window (see the note): 0 control not found; 1 control only; 2 control + THIRD found, SECOND not; 3 SECOND exactly 4 elements after the control; 4 SECOND found elsewhere; 5 SECOND and THIRD both found.
"""
WINDOWS = [
    (10, 0, 649, 653, None),                       # W1: window 640, stock bytes EARLY in the file (the staged file is identical to stock there)
    (1319, 0, 84425, 84429, None),                 # W2: window 84,416, stock bytes just BEFORE the staged span (probe201 A found nothing here)
    (1320, 0, 84494, 84498, 84498),                # W3: window 84,480 (probe198b's look window): the payload pair 77 7f at 84,498 and the STOCK pair 6a 00 at the same place
]
NOPAIR = (0x80, 0xED)                              # a two-byte pair that occurs nowhere in the stock or the staged file
