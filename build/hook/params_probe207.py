"""probe207 PARAMETER BLOCK -- does the PAIR-SWAP of the served staged cells (probe206) hold in later periods? (2026-10-15), derived from params_probe206.py.
probe206 (owner, 8 groups): the served stream at the first cell shows, with the +1 lead rule (element E ~ file offset E-1), EVEN offsets as built and ODD offsets as the byte built TWO positions later
(served[o] = built[o+2] for odd o). probe207 reads one byte at each of nine places to see whether that rule holds in later periods and at the end of the cell.
ROWS : (drops of 64, element index E). E even <=> an ODD file offset (the discriminating ones); E odd <=> an even offset (served as built).
  (1321, 19)  period 1321 offset 18 (even): expect 5            (1321, 20)  offset 19 (odd): swap rule 137 (as built 28; stock 0)
  (2000, 20)  period 2000 offset 19 (odd): swap rule 16 (as built 1; stock 134)    (2000, 46)  offset 45 (odd): swap rule 252 (as built 131; stock 199)
  (3425, 19)  period 3425 (the last staged) offset 18 (even): expect 2   (3425, 20)  offset 19 (odd): swap rule 194 (as built 21; stock 6)   (3425, 46)  offset 45 (odd): swap rule 29 (as built 115; stock 9)
  (1320, 45)  period 1320 offset 44 (even): expect 3            (1320, 46)  offset 45 (odd): swap rule 0 = built[47] (stock); as built would be 2 (the last payload byte of the cell)
"""
ROWS = [(1321, 19), (1321, 20), (2000, 20), (2000, 46), (3425, 19), (3425, 20), (3425, 46), (1320, 45), (1320, 46)]
ITEM_PAD = 1
