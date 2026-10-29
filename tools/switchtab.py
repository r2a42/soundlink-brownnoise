#!/usr/bin/env python3
"""switchtab: find and resolve the speaker's switch statements.

The compiler renders a dense `switch` as

    cmp  <reg>,#N          ; N = number of table entries
    bcc  <default>         ; unsigned: index >= N takes the default
    ld   X,@$XAP_AL        ; index into X
    ld   X,@(JTBASE,X)     ; JTBASE is a DATA address in the const window
    brxl                   ; jump to (address after brxl) + X

so a table entry is an offset from the instruction following `brxl`. The
table lives in the constant pool, which is mapped into data space at
0x7400 (docs/message-task-abi.md), and `brxl` is the word 0xFE09
(docs/xap-opcodes.md).

Verified end to end against the compiler's own output: `f_switch` in
build/opprobe has cases 0..3 and 9, and its table reads
`0000 0003 0006 0009 000F x5 000C` -- the five 0x000F entries being the
default, exactly as the C source says.

    python tools/switchtab.py            # every switch in the image
    python tools/switchtab.py 0x846      # the ones inside one function
"""
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, 'firmware/bose/extracted/internal_fs/vm.app')
HDR = 24
CONST_DATA_BASE = 0x7400
BRXL = 0xFE09
OP_LD_X_IDX = 0x1A          # ld X,@(n,X)


def sext8(b):
    return b - 256 if b & 0x80 else b


def load():
    d = open(APP, 'rb').read()
    w = [struct.unpack_from('<H', d, i)[0] for i in range(0, len(d) & ~1, 2)]
    code_words = (w[5] << 16) | w[6]
    const_start = HDR + code_words          # file index of const word 0
    return w, code_words, const_start


def decode(w, lo=0, hi=None):
    """Yield (a, nwords, opcode, folded) over the project's `a` space."""
    i, n = HDR + lo, len(w) if hi is None else HDR + hi
    while i < n:
        s, v, k = i, 0, 0
        while i < n and (w[i] & 0xFF) == 0x00 and w[i] != 0 and k < 3:
            v = (v + sext8(w[i] >> 8)) << 8
            i += 1
            k += 1
        if i >= n:
            return
        x = w[i]
        i += 1
        yield s - HDR, i - s, x & 0xFF, v + sext8(x >> 8)


def find(w, code_words, const_start, lo=0, hi=None):
    """Yield (brxl_addr, jt_data_addr, bound, entries) for each switch."""
    ins = list(decode(w, lo, hi))
    for k in range(2, len(ins)):
        a, n, op, v = ins[k]
        if op != 0x09 or v != -2:                       # brxl
            continue
        pa, pn, pop, pv = ins[k - 1]
        if pop != OP_LD_X_IDX:                          # ld X,@(JT,X)
            continue
        jt = pv & 0xFFFF
        bound = None
        for j in range(k - 2, max(0, k - 8), -1):       # the cmp that bounds it
            if (ins[j][2] >> 4) == 0x8 and (ins[j][2] & 3) == 0:
                bound = ins[j][3] & 0xFFFF
                break
        base = a + n                                    # entries are offsets from here
        idx = const_start + (jt - CONST_DATA_BASE)
        entries = []
        for e in range(bound or 16):
            if not 0 <= idx + e < len(w):
                break
            entries.append((e, (base + w[idx + e]) & 0x3FFFF))
        yield a, jt, bound, base, entries


def main():
    w, code_words, const_start = load()
    lo = hi = None
    if len(sys.argv) > 1:
        lo = int(sys.argv[1], 0)
        hi = lo + (int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x400)
    found = list(find(w, code_words, const_start, lo or 0, hi))
    print('%d switch statements%s' % (len(found),
          '' if lo is None else ' in 0x%X..0x%X' % (lo, hi)))
    for a, jt, bound, base, entries in found:
        tgts = {}
        for e, t in entries:
            tgts.setdefault(t, []).append(e)
        dflt = max(tgts, key=lambda t: len(tgts[t])) if tgts else None
        print('\nbrxl at 0x%05X   table @data 0x%04X   %s cases' % (a, jt, bound))
        for t in sorted(tgts):
            cases = tgts[t]
            tag = '  (default)' if t == dflt and len(cases) > 1 else ''
            rng = ','.join(str(c) for c in cases) if len(cases) <= 8 else \
                '%d..%d (%d)' % (min(cases), max(cases), len(cases))
            print('    case %-18s -> 0x%05X%s' % (rng, t, tag))
    return 0


if __name__ == '__main__':
    sys.exit(main())
