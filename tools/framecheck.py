#!/usr/bin/env python3
"""framecheck: PER-FUNCTION saved-return-address check for a cave's words (offline, touches nothing).

`enterl -k` reserves the TOP TWO slots of its frame (k-2 and k-1) for the saved return address; a store to @(k-2,Y) or @(k-1,Y)
of that function's own frame destroys the return path (probes 68..80; probe199s rev 1, V11 D1). cavesim.py's HAZARD check judges
the whole image against the FIRST `enterl` it finds, which misses the mistake in any later function and flags correct code in a
function with a bigger frame. This check tracks the frame of each function (a function starts at an `enterl`, in address order,
window and region separately) and reports every store `st AL|AH|X,@(n,Y)` with k-2 <= n < k.

Data blocks (the carried file name, a table) are skipped: a block of words that ends in `rts` (0x00E2) and is preceded by a
terminator (leavel / bra / rts) is data. Stores at n >= k (the consume lever writes the CALLER's frame) and at negative n are not
frame-top stores and are not reported.

    python tools/framecheck.py probe199s [probe197 ...]        exit 1 if any finding
    import framecheck; framecheck.check(words_dict) -> list of (addr, k, n, op)
"""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
STORES = {0x27: 'st AL', 0x23: 'st AH', 0x2B: 'st X'}
TERMINATORS = {0x0F, 0xE0, 0xE2, 0xE1}


def data_addrs(words):
    """addresses of the DATA blocks (a carried string, a table): words that end in `rts` (0x00E2) after a terminator."""
    data = set()
    for a in sorted(words):
        if words[a] == 0x00E2:                         # rts: ends a data block (functions end in leavel / bra)
            b = a - 1
            blk = []
            while b in words and (words[b] & 0xFF) not in TERMINATORS:
                blk.append(b)
                b -= 1
            data.update(blk)
    return data


def check(words):
    """words: {address: word}. Returns [(address, frame k, slot n, text)]."""
    addrs = sorted(words)
    data = data_addrs(words)
    out = []
    frame = None
    prev = None
    for a in addrs:
        w = words[a]
        if prev is not None and a != prev + 1:        # a gap: another band / area; the frame stays (a function spans bands)
            pass
        prev = a
        if a in data:
            continue
        lo = w & 0xFF
        if lo == 0x0B:                                 # enterl -k
            op = w >> 8
            k = (256 - op) if op & 0x80 else -op
            frame = k if k > 0 else None
            continue
        if frame and lo in STORES:
            n = w >> 8
            if frame - 2 <= n < frame:
                out.append((a, frame, n, '%s,@(%d,Y)' % (STORES[lo], n)))
    return out


def load(name):
    path = name if name.endswith('.json') else os.path.join(ROOT, 'build', 'hook', '%s_words.json' % name)
    return {int(k, 16): v & 0xFFFF for k, v in json.load(open(path)).items()}


def main(argv):
    bad = 0
    for name in argv or []:
        f = check(load(name))
        print('%s: %d store(s) into the top two slots of a frame' % (name, len(f)))
        for a, k, n, t in f:
            print('   0x%05x  %s  inside enterl -%d (slots %d and %d are the saved return address)' % (a, t, k, k - 2, k - 1))
        bad += len(f)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
