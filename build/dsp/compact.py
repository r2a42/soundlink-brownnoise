#!/usr/bin/env python3
"""compact.py: noisegen_raw.bin (kas/klink output, big-endian 32-bit PM words, linked at PM 0x2A00) -> noisegen.bin with every two-word ABSOLUTE branch (prefix word 0xFD000000 + an
e1f0 call / ddf0 jump / ddXX conditional jump / e5f0 do whose low 16 bits are the absolute target) rewritten as ONE word with the 16-bit RELATIVE operand the stock code uses
(proven forms: `e1 f0 fd a2` call at 0x16c9 -> 0x146b; `dd f0 03 cc` jump at 0x16cf -> 0x1a9b; `e5 f0 00 05` do at 0x1474 -> 0x1479; `dd 00 03 c5` conditional jump). The offset is relative to
the address of the instruction word itself. Targets inside the routine move with the compaction; external targets (0x1a27, 0x1a8d, 0x1a9b) stay.
Usage: python build/dsp/compact.py   (reads build/dsp/noisegen_raw.bin, writes build/dsp/noisegen.bin and prints the listing)."""
import os, sys

BASE = 0x2A00
here = os.path.dirname(os.path.abspath(__file__))
raw = open(os.path.join(here, "noisegen_raw.bin"), "rb").read()
words = [int.from_bytes(raw[i:i + 4], "big") for i in range(0, len(raw), 4)]
n = len(words)

# 1. find the prefixed absolute branches
OPS = {0xE1F0: "call", 0xDDF0: "jump", 0xE5F0: "do"}
def is_abs_branch(i):
    if i + 1 >= n or words[i] != 0xFD000000: return False
    op16 = words[i + 1] >> 16
    return op16 in OPS or (op16 >> 8) == 0xDD            # dd xx : a (conditional) jump
drop = set()
for i in range(n):
    if is_abs_branch(i): drop.add(i)                      # the prefix word goes away
newidx = {}                                              # old index -> new index
k = 0
for i in range(n):
    if i in drop: continue
    newidx[i] = k; k += 1
# a target that pointed at a dropped prefix would point at the instruction after it (never the case for these branches)
out = []
for i in range(n):
    if i in drop: continue
    w = words[i]
    if i > 0 and (i - 1) in drop:                         # the instruction of a prefixed pair: make it relative
        tgt = w & 0xFFFF                                  # absolute low16 (kas)
        if BASE <= tgt < BASE + n:                        # internal: move with the compaction
            tgt = BASE + newidx[tgt - BASE]
        here_addr = BASE + newidx[i]
        off = (tgt - here_addr) & 0xFFFF
        assert -32768 <= ((off ^ 0x8000) - 0x8000) <= 32767
        w = (w & 0xFFFF0000) | off
    out.append(w)
open(os.path.join(here, "noisegen.bin"), "wb").write(b"".join(x.to_bytes(4, "big") for x in out))
print("compact: %d -> %d PM words" % (n, len(out)))
for j, w in enumerate(out):
    print("%#06x: %08x" % (BASE + j, w))
