#!/usr/bin/env python3
"""conststrings: pull the debug strings out of the speaker's constant pool.

Bose's vm.app stores strings **one character per 16-bit word**, not packed,
so an ordinary `strings` pass over the binary sees nothing. They live in
the constant pool, which starts after the code and is mapped into data
space at 0x7400 (docs/message-task-abi.md) -- so a string's address here
is exactly what the code loads with `ld AL,#<addr>`.

    python tools/conststrings.py                 > build/analysis/const-strings.txt
    python tools/conststrings.py voice assist    # only matching strings
"""
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, 'firmware/bose/extracted/internal_fs/vm.app')
MIN_LEN = 4


def strings(path=APP, min_len=MIN_LEN):
    d = open(path, 'rb').read()
    w = [struct.unpack_from('<H', d, i)[0] for i in range(0, len(d) & ~1, 2)]
    hdr = 24
    const_start = hdr + ((w[5] << 16) | w[6])
    const_len = w[7]
    out, i = [], 0
    while i < const_len:
        if 0x20 <= w[const_start + i] <= 0x7E:
            j = i
            while j < const_len and 0x20 <= w[const_start + j] <= 0x7E:
                j += 1
            if j - i >= min_len:
                out.append((0x7400 + i,
                            ''.join(chr(w[const_start + k]) for k in range(i, j))))
            i = j
        else:
            i += 1
    return out


def main():
    pats = [re.compile(p, re.I) for p in sys.argv[1:]]
    rows = strings()
    if pats:
        rows = [r for r in rows if any(p.search(r[1]) for p in pats)]
    for a, s in rows:
        print('0x%04X  %s' % (a, s))
    print('# %d strings' % len(rows), file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
