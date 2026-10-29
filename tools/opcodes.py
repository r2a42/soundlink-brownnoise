#!/usr/bin/env python3
"""opcodes: derive the XAP2 opcode table from the ADK compiler's own output.

The assembler writes two things for the same program: `<out>.xap`, the
instruction stream in mnemonics, and `<out>.app`, the linked words. Line
them up function by function and every encoding the compiler can emit
names itself -- no guessing, no inference from call sites.

This is how the "unconfirmed" entries in tools/xapvm's table (the a0-a7
shifts, the f0/f8 branches) get settled, and how tools/xapemu's unmodelled
opcodes get found before they raise in the middle of a cave simulation.

    python tools/opcodes.py build/opprobe/opprobe     # prints the table
    python tools/opcodes.py build/opprobe/opprobe --gaps

Alignment is per function, anchored on the symbol table, so a mismatch in
one function cannot corrupt the rest.
"""
import argparse
import os
import re
import sys
from collections import defaultdict

DIRECTIVES = {
    'MODULE', 'ENDMOD', 'EQU', 'DEQU', 'CEQU', 'DS', 'DC', 'dc', 'ORG',
    'INCLUDE', '.SEG', '.CODE', '.CSEG', '.PACK', '.ENHANCED', '.LARGE',
    '.DATA', 'GLOBAL', 'EXTERN', 'END', '.ALL', '.STABS', '.STABN',
}


def sext8(b):
    return b - 256 if b & 0x80 else b


def read_app(path):
    """The linked words, keyed by file address, plus the code base."""
    words = {}
    for ln in open(path):
        m = re.match(r'@([0-9A-Fa-f]{6})\s+([0-9A-Fa-f]{4})', ln)
        if m:
            words[int(m.group(1), 16)] = int(m.group(2), 16)
    lo = min(words)
    hdr = [words[lo + i] for i in range(24)]
    return words, lo + 24, hdr            # symbol address 0 == lo+24


def read_map(path):
    """{symbol: size in words} -- the linker's own count, used to prove an
    alignment rather than assume it."""
    sizes = {}
    for ln in open(path):
        m = re.match(r'(\S+)\s+address=(\d+)\s+size=(\d+)', ln.strip())
        if m:
            sizes[m.group(1)] = int(m.group(3))
    return sizes


def read_sym(path):
    syms = {}
    for ln in open(path):
        # some entries carry a trailing marker, e.g. "$_f_bits, 00014e *"
        m = re.match(r'(\S+),\s+([0-9a-f]{6})', ln.strip())
        if m:
            syms[m.group(1)] = int(m.group(2), 16)
    return syms


def read_xap(path, syms):
    """{function label: [mnemonic lines]} in source order.

    Local labels (`?L5`, `?LBB_f`) do NOT start a new body -- they sit in
    the middle of a function, and treating them as boundaries chopped every
    function into fragments too short to align.
    """
    bodies, cur = defaultdict(list), None
    for raw in open(path):
        line = raw.rstrip('\n')
        if not line.strip() or line.lstrip().startswith(';'):
            continue
        if not line[0].isspace():                       # a label
            name = line.split(':')[0].strip()
            if name in syms:
                cur = name
            continue
        parts = line.split()
        if not parts or parts[0] in DIRECTIVES:
            continue
        if cur is not None:
            bodies[cur].append(' '.join(parts))
    return bodies


MODIFIER = 0x0009   # the exact WORD 0x0009 selects the unsigned form of the
                    # instruction that follows: `asr #1` is 01A4 but `lsr #1`
                    # is 0009 01A4, and `sdiv @m` is nn95 while `udiv @m` is
                    # 0009 nn95. It is not a standalone `clc`.
                    #
                    # Opcode 0x09 with a DIFFERENT operand is its own
                    # instruction: 0xFE09 is `brxl`, the indexed branch a
                    # switch statement jumps through. Bose's image has 2541 of
                    # the modifier and 318 `brxl`, and nothing else that
                    # survives a real decode.


def decode(words, base, start, count):
    """Yield (addr, [raw words], opcode, folded operand) for `count`
    instructions, following the signed prefix chain and absorbing the
    0x0009 modifier into the instruction it modifies."""
    a = start

    def one():
        nonlocal a
        raw, v, k = [], 0, 0
        while (words.get(base + a, 0) & 0xFF) == 0x00 and words.get(base + a, 0) and k < 3:
            raw.append(words[base + a])
            v = (v + sext8(words[base + a] >> 8)) << 8
            a += 1
            k += 1
        w = words.get(base + a)
        if w is None:
            return None
        raw.append(w)
        a += 1
        return raw, w & 0xFF, v + sext8(w >> 8)

    for _ in range(count):
        got = one()
        if got is None:
            return
        raw, op, v = got
        if len(raw) == 1 and raw[0] == MODIFIER:
            nxt = one()
            if nxt is None:
                return
            raw = raw + nxt[0]
            op, v = nxt[1], nxt[2]
            op |= 0x100                    # mark it as the modified form
        yield a - len(raw), raw, op, v


def pair(prefix):
    words, base, hdr = read_app(prefix + '.app')
    syms = read_sym(prefix + '.sym')
    bodies = read_xap(prefix + '.xap', syms)
    sizes = read_map(prefix + '.map')
    table = defaultdict(set)              # opcode -> {mnemonic forms}
    examples = {}
    aligned = skipped = 0
    for label, lines in bodies.items():
        if label not in syms:
            skipped += 1
            continue
        got = list(decode(words, base, syms[label], len(lines)))
        # An alignment is only trusted when it consumes EXACTLY the number of
        # words the linker says the function occupies. Without this check a
        # single missed multi-word form silently shifts every later pairing
        # and the table fills with nonsense (one opcode, six mnemonics).
        used = sum(len(raw) for _, raw, _, _ in got)
        if len(got) != len(lines) or used != sizes.get(label):
            skipped += 1
            continue
        aligned += 1
        for (addr, raw, op, v), text in zip(got, lines):
            mn = text.split()[0].lower()
            table[op].add(mn)
            examples.setdefault((op, mn), (raw, text))
    return table, examples, aligned, skipped, len(bodies)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('prefix', help='path without extension, e.g. build/opprobe/opprobe')
    ap.add_argument('--gaps', action='store_true',
                    help='only show opcodes tools/xapemu does not model')
    args = ap.parse_args()

    table, examples, aligned, skipped, total = pair(args.prefix)
    print('# aligned %d of %d labels (%d skipped: no symbol, or length mismatch)'
          % (aligned, total, skipped))
    print('# %d distinct opcodes observed\n' % len(table))

    modelled = set(range(0x10, 0x20)) | set(range(0x20, 0x30)) | \
        set(range(0x30, 0x40)) | set(range(0x50, 0x60)) | set(range(0x80, 0x90)) | \
        set(range(0xB0, 0xC0)) | set(range(0xC0, 0xD0)) | set(range(0xD0, 0xE0)) | \
        {0x09, 0x0B, 0x0E, 0x0F, 0x20, 0x24, 0x28, 0x2C, 0x74, 0x90, 0x91,
         0x9A, 0x9B, 0x9C, 0xA0, 0xA1, 0xA4, 0xA5, 0xE0, 0xE2, 0xE4,
         0xF0, 0xF4, 0xF8, 0xFC}

    print('| opcode | mnemonic(s) | example words | example source |')
    print('|---|---|---|---|')
    for op in sorted(table):
        if args.gaps and op in modelled:
            continue
        mns = sorted(table[op])
        raw, text = examples[(op, mns[0])]
        print('| `%s` | %s | `%s` | `%s` |'
              % (('0x%02X'%op if op<0x100 else '0009+0x%02X'%(op&0xFF)), ', '.join('`%s`' % m for m in mns),
                 ' '.join('%04X' % w for w in raw), text))
    if args.gaps:
        unseen = sorted(set(table) - modelled)
        print('\n# %d opcodes the emulator does not model: %s'
              % (len(unseen), ', '.join('0x%02X' % o for o in unseen) or 'none'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
