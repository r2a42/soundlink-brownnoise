"""probe205 PARAMETER BLOCK -- the WIDE displacement test and a second look at the W2 anomaly (2026-10-15), derived from params_probe204.py.
probe204 (owner: 10 0011 0000 0011 = classes 1 0 1) REJECTED a displacement of the payload cells of about 64 bytes. Fitting all 11 staged-file observations (docs/deep/material-2026-10-13/J0-displace.py,
fit2 variant) leaves d = 127..130 (two periods) and 191..192 (three periods) explaining 10 of 11; the one never explained is the control pair 00 2e at 84,425 (probe203 W2, probe204 W2).
GRAM_D = 98 and SCAN_N = 127 in this image: the second pair lies 98 bytes after the control (the code compares jp - jc with an immediate) and the search covers elements 0..126, so the payload pair can be seen on either side of the control.
WINDOWS : each (drops of 64, extra (0), CTL_POS, SECOND_POS, THIRD_POS None). Search: elements 0..99 of ONE fresh map, masked, lead +1.
  W1 window 84,352 (1,318 drops): control 03 00 at 84,402, second = the PAYLOAD pair 77 c6 (bytes 2,3 as built at 84,500):  d = 0 -> 1? no: window covers 84,351..84,550 so the pair at 84,498 IS inside: d = 0 -> 3;  payload begins in 84,351..84,550 (d in -52..147) -> 4 (or 3 at d = 0).
  W2 window 84,416 (1,319 drops): control 84,462 (stock, unstaged, offset 46 of period 1,319, a DIFFERENT control than 00 2e), second pair 84,586 (outside the window): class 1 if the control is seen, class 0 if the anomaly extends to this control too.
  W3 window 84,288 (1,317 drops): control 84,374, second = the PAYLOAD pair:  payload begins in 84,287..84,386 (d in 112..211) -> 4;  else 1.
"""
SCAN_N = 127                                       # the pair search covers elements 0..126 (probe204: 0..99; 127 is the largest one-word immediate)
WINDOWS = [
    (1318, 0, 84402, 84500, None),                 # W1: window 84,352; control 03 00 at 84,402 (offset 50 of period 1,318: stock, uncovered by cells for d = 0, 30, 64, 128, 192); second = the PAYLOAD pair 77 c6 (bytes 2,3) at 84,500
    (1319, 0, 84462, 84560, None),                 # W2: window 84,416; control 61 00 at 84,462 (offset 46 of period 1,319, NOT 00 2e); second = a stock pair at 84,560 (+98)
    (1317, 0, 84402, 84500, None),                 # W3: window 84,288; same control and second pair
]
NOPAIR = (0x80, 0xED)
