"""probe198c PARAMETER BLOCK -- the ONLY file to edit when the probe202 numbers arrive (2026-10-15).
PREPARATION ONLY: the values below are PLACEHOLDERS (marked PLACEHOLDER); nothing built from them is flash-cleared.
Read by build/hook/assemble_probe198c.py and build/hook/gate_probe198c.py. Fill-in procedure: docs/deep/material-2026-10-13/H1-prep-203-198c.md section 4.

START_EXTRA : bytes dropped ONCE, after the 1,320 x SourceDrop(64) skip and before the first look/gather map. The gather window then starts at
              64 * 1320 + START_EXTRA (and every later period at +64): 0 = 64-aligned windows, 14 = probe200's unaligned control start (14 mod 64).
              Allowed 0..18 (the staged bytes of a period are file bytes 18..45; a start beyond 18 would put byte 0 of the payload before the window).
MAP_SHIFT   : the lead of the map at THAT alignment, from probe202 (element j holds window byte j - MAP_SHIFT). probe200 measured +1 at the
              UNALIGNED starts 4 and 84,494 (stock file; well-supported); the aligned value is unknown until probe202 (PLACEHOLDER).
The element of payload byte 0 in each window is ELEM0 = 18 - START_EXTRA + MAP_SHIFT (the look reads ELEM0..ELEM0+3, the gather ELEM0..ELEM0+27).
"""
START_EXTRA = 14     # PLACEHOLDER: probe200's unaligned control start (the only alignment with a measured lead)
MAP_SHIFT = 1        # PLACEHOLDER: probe200's lead at the unaligned starts (stock file)
# The world models the gate uses for the alignment ("other alignment" = the one this image does NOT use). PLACEHOLDER values: change with the probe202 numbers.
OTHER_ALIGNMENT_SHIFT = 5     # PLACEHOLDER: the lead the world gives to the alignment this image does not use (any value; it must not matter)
