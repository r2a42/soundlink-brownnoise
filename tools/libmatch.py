#!/usr/bin/env python3
"""libmatch: name Bose's functions by matching compiled ADK library code.

Bose's `vm.app` is a custom application, but it is linked against the same
ADK libraries we have. Any library function it uses is compiled from the
same source by the same compiler, so its **opcode sequence** appears in the
image verbatim -- only the operands differ, because branch offsets and data
addresses get relocated.

So: link a probe app that references library functions, take each
function's opcode sequence from the result, and search the speaker's image
for it. A hit names a Bose function outright.

    python tools/libmatch.py build/sustainprobe/sustainprobe
    python tools/libmatch.py build/convprobe/convprobe --min 8

Matching is on opcode bytes only, which is what makes it relocation-proof.
The cost is false positives on short functions, so `--min` sets a floor and
the report shows how distinctive each match is.

This was proved by hand first: `MessageLoop` was found in Bose's image at
a = 0x395F8 by comparing it instruction-for-instruction with our own linked
copy (docs/message-task-abi.md §3).
"""
import argparse
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, 'firmware/bose/extracted/internal_fs/vm.app')
HDR = 24


def sext8(b):
    return b - 256 if b & 0x80 else b


def bose_opcodes():
    """(opcode list, per-instruction address list) over the image's code."""
    d = open(APP, 'rb').read()
    w = [struct.unpack_from('<H', d, i)[0] for i in range(0, len(d) & ~1, 2)]
    code = (w[5] << 16) | w[6]
    ops, addrs, i = [], [], HDR
    while i < HDR + code:
        s, k = i, 0
        while i < HDR + code and (w[i] & 0xFF) == 0x00 and w[i] != 0 and k < 3:
            i += 1
            k += 1
        if i >= HDR + code:
            break
        ops.append(w[i] & 0xFF)
        addrs.append(s - HDR)
        i += 1
    return ops, addrs


def probe_functions(prefix, min_len):
    """{name: [opcodes]} for each function in a linked probe app."""
    words = {}
    for ln in open(prefix + '.app'):
        m = re.match(r'@([0-9A-Fa-f]{6})\s+([0-9A-Fa-f]{4})', ln)
        if m:
            words[int(m.group(1), 16)] = int(m.group(2), 16)
    base = min(words) + HDR
    sizes = {}
    for ln in open(prefix + '.map'):
        m = re.match(r'(\S+)\s+address=(\d+)\s+size=(\d+)', ln.strip())
        if m:
            sizes[m.group(1)] = (int(m.group(2)), int(m.group(3)))
    out = {}
    for name, (a, n) in sizes.items():
        ops, i, end = [], base + a, base + a + n
        while i < end:
            k = 0
            while i < end and (words.get(i, 0) & 0xFF) == 0x00 and words.get(i) and k < 3:
                i += 1
                k += 1
            if i >= end:
                break
            ops.append(words[i] & 0xFF)
            i += 1
        if len(ops) >= min_len:
            out[name] = ops
    return out


def find(hay, needle):
    hits, start = [], 0
    n = len(needle)
    while True:
        try:
            k = hay.index(needle[0], start)
        except ValueError:
            return hits
        if hay[k:k + n] == needle:
            hits.append(k)
        start = k + 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('prefix', help='linked probe app without extension')
    ap.add_argument('--min', type=int, default=10,
                    help='minimum instructions for a function to be matched')
    args = ap.parse_args()

    ops, addrs = bose_opcodes()
    fns = probe_functions(args.prefix, args.min)
    print('# %d functions of >=%d instructions in %s' %
          (len(fns), args.min, os.path.basename(args.prefix)))
    print('# searching %d instructions of Bose code\n' % len(ops))
    named = 0
    for name in sorted(fns, key=lambda n: -len(fns[n])):
        hits = find(ops, fns[name])
        if not hits:
            continue
        named += 1
        where = ', '.join('0x%05X' % addrs[h] for h in hits[:4])
        print('%-32s %3d instructions  ->  %s%s'
              % (name, len(fns[name]), where,
                 ' (+%d more)' % (len(hits) - 4) if len(hits) > 4 else ''))
    print('\n%d of %d matched' % (named, len(fns)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
