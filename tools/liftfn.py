#!/usr/bin/env python3
"""liftfn: lift a compiled leaf function out of a linked .app into cave items.

Probes 68, 69, 72 and 73 all crashed because the brown-noise generator was
**transcribed by hand** from compiler output. Six owner presses eliminated the
loop, the connectors, the write target and the leak, and left one of seven
hand-copied instructions as the fault. The lesson in `docs/roadmap.md` Step 2
is not "find the bad opcode" but "stop copying opcodes".

This does the copying. Given a linked `.app` plus its `.map` and `.sym`, it
decodes one function and emits the layout items a cave assembler consumes:

    ('w', [words])        a straight-line instruction, verbatim
    ('br', opcode, lbl)   a relative branch, as a LABEL
    ('label', name)       a branch target

Branches become labels because the cave's own layout splits code across
blind-window bands and inserts connector jumps, so every internal offset has
to be recomputed by the assembler. Emitting the raw branch words -- which is
what hand-transcription did -- bakes in offsets that the banding then
invalidates. probe71 proved the banding machinery is sound; this makes the
lifted code use it.

    python tools/liftfn.py build/noiseprobe/noiseprobe noise_fill
    python tools/liftfn.py build/noiseprobe/noiseprobe noise_fill --json out.json

What it refuses to lift, because a cave cannot host it:

  * any `bsr` -- the function must be a leaf; a call would need its callee
    lifted too, and the callee may not be position-independent;
  * any branch leaving the function;
  * any `@abs` operand below 0xFF00 -- that is a global, and globals live at
    fixed data addresses this firmware has not got. Addresses at or above
    0xFF00 are the XAP's own registers ($XAP_UXL and friends) and are fine.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'xapvm'))
import xapvm                                                   # noqa: E402

# Relative-branch opcodes (docs/xap-opcodes.md). 0xE0 is `bra`; the rest are
# conditional. Their target is the branch word's own address plus the fold.
BRANCHES = {0x20: 'bgt', 0x24: 'bge', 0x28: 'ble', 0x2C: 'bcz',
            0xE0: 'bra', 0xE4: 'blt', 0xE8: 'bpl', 0xEC: 'bmi',
            0xF0: 'bne', 0xF4: 'beq', 0xF8: 'bcc', 0xFC: 'bcs'}
CALLS = {0x9C: 'bsr', 0x9E: 'bsr ,X'}
# Instruction families whose low two opcode bits are the addressing mode.
MODED_HI = {0x1, 0x2, 0x3, 0x4, 0x5, 0x6, 0x7, 0x8, 0xB, 0xC, 0xD}
MODED_SHIFT = {0xA0, 0xA4, 0x90, 0x94, 0x98}
MODE_ABS = 1
REG_SAFE_FROM = 0xFF00          # at/above this an @abs operand is a register


def load_code(stem):
    """Code words of a linked probe .app, indexed by code-word address.

    A freshly linked `.app` is not laid out like Bose's `vm.app`: its `@ADDR`
    lines start at 0x8001 rather than 0, so `xapvm.load_words` rejects it as a
    gapped image. `tools/libmatch.py` already solved this -- the code base is
    `min(address) + 0x18`, past the 0x18-word header. Same arithmetic here.
    """
    words = {}
    with open(stem + '.app', encoding='latin1') as f:
        for line in f:
            m = re.match(r'@([0-9A-Fa-f]+)\s+([0-9A-Fa-f]{1,4})', line)
            if m:
                words[int(m.group(1), 16)] = int(m.group(2), 16)
    if not words:
        raise SystemExit('liftfn: no @address lines in %s.app' % stem)
    base = min(words) + 0x18
    return [words.get(base + i, 0) for i in range(max(words) - base + 1)]


def read_symbols(stem):
    """{name: word address} from the linker's .sym (addresses are hex)."""
    out = {}
    with open(stem + '.sym', encoding='latin1') as f:
        for line in f:
            m = re.match(r'^(\$?[\w.?$]+),\s*([0-9a-fA-F]+)\s*$', line.strip())
            if m:
                out[m.group(1)] = int(m.group(2), 16)
    return out


def read_sizes(stem):
    """{name: size in words} from the linker's .map (sizes are DECIMAL).

    Worth stating because the two files disagree on base: `.sym` prints
    addresses in hex and `.map` prints `address=`/`size=` in decimal. Both
    were cross-checked against each other on noise_fill (0x3B == 59, and
    0x3B + 41 - 1 == 0x63 == ?LBE_noise_fill).
    """
    out = {}
    with open(stem + '.map', encoding='latin1') as f:
        for line in f:
            m = re.match(r'^(\$?[\w.?$]+)\s+address=(\d+)\s+size=(\d+)', line.strip())
            if m:
                out[m.group(1)] = (int(m.group(2)), int(m.group(3)))
    return out


def abs_operand(op, fold):
    """The absolute address an @abs instruction refers to, or None."""
    hi = op >> 4
    if hi in MODED_HI and (op & 3) == MODE_ABS:
        return fold & 0xFFFF
    if (op & ~3) in MODED_SHIFT and (op & 3) == MODE_ABS:
        return fold & 0xFFFF
    return None


def lift(stem, func):
    code = load_code(stem)
    syms = read_symbols(stem)
    sizes = read_sizes(stem)
    key = '$_' + func
    if key not in syms:
        raise SystemExit('liftfn: %s not in %s.sym' % (key, stem))
    if key not in sizes:
        raise SystemExit('liftfn: %s not in %s.map' % (key, stem))
    entry = syms[key]
    map_addr, size = sizes[key]
    if map_addr != entry:
        raise SystemExit('liftfn: .sym says %#x, .map says %d -- disagreement'
                         % (entry, map_addr))
    end = entry + size

    # Decode from the entry rather than from word 0: the entry is a known
    # instruction boundary, so this cannot inherit a misalignment from
    # whatever padding precedes the function.
    decoded = [(a + entry, op, v, ln)
               for a, op, v, ln in xapvm.decode(code[entry:end])]
    consumed = sum(ln for _, _, _, ln in decoded)
    if consumed != size:
        raise SystemExit('liftfn: decoded %d words, .map says %d -- the range '
                         'does not decode cleanly' % (consumed, size))

    starts = {a for a, _, _, _ in decoded}
    targets, problems, notes = {}, [], []
    for a, op, v, ln in decoded:
        if op in CALLS:
            problems.append('%#x: %s -- not a leaf function' % (a, CALLS[op]))
            continue
        if op in BRANCHES:
            t = (a + v) & 0x3FFFF
            if not (entry <= t < end):
                problems.append('%#x: %s leaves the function (-> %#x)'
                                % (a, BRANCHES[op], t))
            elif t not in starts:
                problems.append('%#x: %s targets %#x, not an instruction start'
                                % (a, BRANCHES[op], t))
            else:
                targets.setdefault(t, 'L%04x' % t)
            continue
        ab = abs_operand(op, v)
        if ab is not None:
            if ab < REG_SAFE_FROM:
                problems.append('%#x: @abs %#06x is a global; the function '
                                'must use only locals' % (a, ab))
            else:
                notes.append('%#x: @abs %#06x (an XAP register, fine)' % (a, ab))

    items = []
    for a, op, v, ln in decoded:
        if a in targets:
            items.append(['label', targets[a]])
        if op in BRANCHES:
            items.append(['br', op, targets[(a + v) & 0x3FFFF]])
        else:
            items.append(['w', [code[a + k] for k in range(ln)]])
    return {'func': func, 'entry': entry, 'size': size,
            'items': items, 'problems': problems, 'notes': notes,
            'decoded': decoded}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stem', help='linked image without extension, e.g. build/noiseprobe/noiseprobe')
    ap.add_argument('func', help='C function name, without the $_ prefix')
    ap.add_argument('--json', metavar='PATH', help='write the items here')
    args = ap.parse_args()

    r = lift(args.stem, args.func)
    print('%s: entry %#x, %d words, %d items'
          % (r['func'], r['entry'], r['size'], len(r['items'])))
    for n in r['notes']:
        print('  note    %s' % n)
    for p in r['problems']:
        print('  REFUSED %s' % p)
    print()
    labels = {it[1] for it in r['items'] if it[0] == 'label'}
    by_addr = {a: (op, v, ln) for a, op, v, ln in r['decoded']}
    for a, op, v, ln in r['decoded']:
        tag = ''
        if op in BRANCHES:
            tag = '   -> L%04x' % ((a + v) & 0x3FFFF)
        lbl = 'L%04x:' % a if ('L%04x' % a) in labels else ''
        print('  %-8s %#06x  %-22s%s' % (lbl, a, xapvm.mnemonic(op, v), tag))
    if r['problems']:
        return 1
    if args.json:
        json.dump({'func': r['func'], 'entry': r['entry'], 'size': r['size'],
                   'items': r['items']}, open(args.json, 'w'), indent=0)
        print('\nwrote %s' % args.json)
    return 0


if __name__ == '__main__':
    sys.exit(main())
