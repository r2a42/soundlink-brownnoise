#!/usr/bin/env python3
"""Disassemble stack_prog.bin -- the Bluetooth stack firmware, 751,112 bytes.

Why this exists: `build/analysis/full-disasm.txt` covers **vm.app only**. The stack is 45%
of every DFU image and had never been disassembled, so any claim about stack-side code was
unverifiable -- by me or by a consulting agent. That gap became load-bearing on 2026-10-05:
the trail from probe130's corrupted const word `0x8280` runs `fn_0aaa1` -> `fn_27bab` ->
`fn_395dd(task 0x705)`, and the task installed at `0x705` registers through
`MessageBlueStackTask`, i.e. into the stack.

`tools/disasm.py` cannot be pointed at it: it parses vm.app's 0x18-word header to find the
code length, and a raw stack image has no such header.

**Byte order is determined empirically.** An unknown-opcode rate does NOT discriminate --
the XAP decoder names essentially every byte, so both orders score 0.00% unnamed. What does
discriminate is structure: real code has one `enterl` per function with a matching
`leavel`, and a plausible `bsr` density.

Measured 2026-10-05:

    little-endian   enterl 6613 | leavel 6527 | rts  566 | bsr 21060
    big-endian      enterl 3445 | leavel 3161 | rts 1105 | bsr   327

Little-endian: 6,613 functions with epilogues matching to 1%, against the "~7,000
functions" in `docs/NEXT-UNIT-CHECKLIST.md`. Big-endian's 327 `bsr` is an implausible call
density for 375k words. Little-endian it is.

Two corrections this established:
  * **"CSR - bc7" is NOT in stack_prog.bin.** It is in `stack_const.bin` at byte 3720 (and
    in the DFU at 756076). The docs attributed it to stack_prog.bin.
  * Addresses here are **word indices from file start**. Whether the stack's own code base
    is 0 is NOT established, so these must never be equated with vm.app addresses -- it is
    a separate address space.

Usage:
    python tools/stackdisasm.py --probe     # byte-order and sanity report, writes nothing
    python tools/stackdisasm.py             # write build/analysis/stack-disasm.txt
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'xapvm'))
import xapvm

STACK = os.path.join(ROOT, 'firmware/bose/extracted/stack_prog.bin')
CONST = os.path.join(ROOT, 'firmware/bose/extracted/stack_const.bin')
OUT = os.path.join(ROOT, 'build/analysis/stack-disasm.txt')


def words(little=True):
    d = open(STACK, 'rb').read()
    if little:
        return [d[i] | (d[i + 1] << 8) for i in range(0, len(d) - 1, 2)]
    return [(d[i] << 8) | d[i + 1] for i in range(0, len(d) - 1, 2)]


def census(ws):
    op = [w & 0xFF for w in ws]
    return {'enterl': op.count(0x0B), 'leavel': op.count(0x0F),
            'rts': op.count(0xE2), 'bsr': op.count(0x9C)}


def probe():
    print('stack_prog.bin: %d bytes = %d words' % (os.path.getsize(STACK),
                                                   os.path.getsize(STACK) // 2))
    print('\nByte order by STRUCTURE (an unknown-opcode rate cannot tell them apart:')
    print('the decoder names every byte, so both orders score 0.00% unnamed):')
    best = None
    for little in (True, False):
        c = census(words(little))
        print('  %-13s enterl %6d | leavel %6d | rts %6d | bsr %6d'
              % ('little-endian' if little else 'big-endian',
                 c['enterl'], c['leavel'], c['rts'], c['bsr']))
        score = c['enterl'] + c['bsr'] - abs(c['enterl'] - c['leavel'])
        if best is None or score > best[1]:
            best = (little, score, c)
    little, _, c = best
    print('\n-> %s-endian: %d functions, epilogues matching to %.1f%%, %d calls.'
          % ('little' if little else 'big', c['enterl'],
             100.0 * c['leavel'] / max(1, c['enterl']), c['bsr']))
    print('   docs/NEXT-UNIT-CHECKLIST.md records "~7,000 functions" -- consistent.')
    d = open(STACK, 'rb').read()
    k = open(CONST, 'rb').read() if os.path.exists(CONST) else b''
    print('\n"CSR - bc7": stack_prog.bin %d, stack_const.bin %d'
          % (d.find(b'CSR - bc7'), k.find(b'CSR - bc7')))
    print('   (the docs put it in stack_prog.bin; it is in stack_const.bin)')
    print('\nAddresses are WORD INDICES FROM FILE START. The stack\'s own code base is')
    print('NOT established, so never equate these with vm.app addresses.')
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--probe', action='store_true', help='report only, write nothing')
    ap.add_argument('--big', action='store_true', help='force big-endian')
    a = ap.parse_args()
    if a.probe:
        probe()
        return 0
    ws = words(not a.big)
    ins = list(xapvm.decode(ws))
    c = census(ws)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('# Disassembly of stack_prog.bin (the Bluetooth stack firmware).\n')
        f.write('# %d words, %d instructions, %s-endian word order chosen by structural\n'
                % (len(ws), len(ins), 'big' if a.big else 'little'))
        f.write('# opcode census: %d enterl, %d leavel, %d bsr '
                '(tools/stackdisasm.py --probe).\n' % (c['enterl'], c['leavel'], c['bsr']))
        f.write('#\n')
        f.write('# SEPARATE ADDRESS SPACE from vm.app. Addresses below are WORD INDICES\n')
        f.write('# FROM FILE START; the stack\'s own code base is NOT established. Never\n')
        f.write('# equate an address here with a vm.app address.\n')
        f.write('# Trap/function names are NOT recoverable here: no trap table was found.\n\n')
        # decode() yields (addr, opcode, value, length) -- NOT objects. The address comes
        # from the tuple, not from enumerate(): prefix folding means one instruction can
        # span several words, so the two diverge.
        for a, op, v, ln in ins:
            raw = ' '.join('%04x' % ws[a + k] for k in range(ln) if a + k < len(ws))
            f.write('  %#08x: %-18s %s\n' % (a, raw, xapvm.mnemonic(op, v)))
    print('wrote %s' % OUT)
    print('  %d instructions, %d functions by enterl count' % (len(ins), c['enterl']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
