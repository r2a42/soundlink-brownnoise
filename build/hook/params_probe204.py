"""probe204 PARAMETER BLOCK -- the DISPLACEMENT test (2026-10-15), derived from build/hook/params_probe203.py.
Read by build/hook/assemble_probe204.py and build/hook/gate_probe204.py. Note: docs/deep/material-2026-10-13/J0-displacement-model.md (the model) and J1-probe204.md.

Question: are the STAGED payload cells displaced in the file the speaker serves (the model fits d = 63..66 bytes, about one 64-byte period earlier)?
WINDOWS : each (drops of 64, one extra drop (must be 0), CTL_POS, SECOND_POS, THIRD_POS): window start = 64 * drops; CTL_POS = file position of the CONTROL pair (a stock,
          UNSTAGED pair, taken from the built file); SECOND_POS = CTL_POS + 4 (the same distance in every window); THIRD_POS None (an impossible pair is searched).
Class per window (the probe203 classes): 0 control not found; 1 control found, second pair not found; 3 second pair exactly 4 elements after the control; 4 second pair found elsewhere.
Expected (both pairs are searched in elements 0..99 of ONE fresh map, masked, lead +1):
  W1 window 84,416, control 84,494 (stock), second = the PAYLOAD pair 77 7f at 84,498 (staged):  d = 0 -> 3;  d = 64 (payload begins at 84,434) -> 4;  d >= 128 or none -> 1.
  W2 window 84,416, control 84,425 (stock), second = stock 84,429: a repeat of probe203 W2 (it heard class 0): d = 0 -> 3.  (is the W2 anomaly reproducible?)
  W3 window 84,480, control 84,558 (stock), second = the payload pair at 84,562 (staged, payload bytes 28,29): d = 0 -> 3;  d = 64 (they land at 84,498) -> 4;  d >= 128 -> 1.
"""
WINDOWS = [
    (1319, 0, 84494, 84498, None),                 # W1
    (1319, 0, 84425, 84429, None),                 # W2 (repeat of probe203 W2)
    (1320, 0, 84558, 84562, None),                 # W3
]
NOPAIR = (0x80, 0xED)                              # a two-byte pair that occurs nowhere in the stock or the staged file
