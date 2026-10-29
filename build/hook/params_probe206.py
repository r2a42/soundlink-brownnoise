"""probe206 PARAMETER BLOCK -- the RAW READOUT of the staged data_us (2026-10-15), derived from params_probe205.py.
Question: what bytes does the file source SERVE at the first staged cells? probes 201..205 asked yes/no questions about pairs and were never able to see the value.
The owner's instruction (2026-10-15): "only the text to speech is garbled ... all the stock prompts are fine. Assume that unless proven otherwise": so the ten 'battery N%' prompts are
the digit channel again (value v = digit 0..9 spoken as id 0x27 + v = 'battery (v+1)x10 %'; digit 0 = 'battery 10%', digit 9 = 'battery 100%').
ROWS : (drops of 64, element index E). Each row = ONE served byte, read from ONE fresh SourceMap taken after the drops: (map[E] & 0xFF). With the lead +1 rule (probe202),
       element E holds file byte (64 * drops + E - 1).  Four prompts per row: hundreds, tens, units, check = (h + t + u) mod 10.
Window 84,480 (1,320 drops): E = 17 .. 24 = file bytes 84,496 .. 84,503: 84,496 and 84,497 are STOCK (unstaged), 84,498 .. 84,503 are the first six PAYLOAD bytes as built (77 7f 77 c6 bf 10).
"""
ROWS = [(1320, e) for e in range(17, 25)]
ITEM_PAD = 1
