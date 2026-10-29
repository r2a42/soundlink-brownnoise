#!/usr/bin/env python3
"""disasm: a whole-image disassembly of Bose's vm.app, with correct trap names.

Why this exists. Until now the project had `build/analysis/functions/*.lst` --
5,396 per-function listings produced piecemeal, naming trap stubs from the
superseded BlueLab 7.4 table (`docs/trap-numbering.md`), with no whole-image view
and no cross-reference index. That is how probes 103-108 came to be built on a hook
site nobody had read: `0x0AE0` turns out to sit behind `cmp AL,#0x4003` at `0x0ACD`,
so the cave only ever ran on EventUsrEnterPairing, and five firmwares were spent
before anyone looked.

This decodes all 236,514 code words in one pass and writes:

    build/analysis/full-disasm.txt   every instruction, grouped into functions,
                                     with trap stubs named from the 7.3 table and
                                     every branch/call target resolved
    build/analysis/xref.json         callers/callees per function, and readers and
                                     writers per global address
    build/analysis/hook-sites.txt    the search this was really built for: every
                                     3-word bsr/bra whose operand bytes are ALL
                                     inside the DFU blind windows, i.e. every call
                                     site that can be redirected to a cave without
                                     disturbing a byte the RSA signature covers

Usage:
    python tools/disasm.py                 # all three outputs
    python tools/disasm.py --fn 0x846      # one function to stdout
    python tools/disasm.py --hooks         # just the hook-site report
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'xapvm'))
import xapvm                                                     # noqa: E402

APP = os.path.join(ROOT, 'firmware/bose/extracted/internal_fs/vm.app')
AREA0 = 0x6EA30             # file byte offset of code word 0 (the DFU edit area)
BSR = 0x9C
BRANCHES = (0x20, 0x24, 0x28, 0x2C, 0xE0, 0xE4, 0xE8, 0xEC, 0xF0, 0xF4, 0xF8, 0xFC)


def blind_byte(area_byte_off):
    """True if this file byte is inside a DFU blind window (fsedit.blind)."""
    c = area_byte_off - 136
    return c >= 0 and 34 <= (c % 64) <= 62


def operand_byte(a):
    """File offset of the operand (high) byte of code word `a`."""
    return AREA0 + 2 * a + 1


def load():
    w = xapvm.load_words(APP)
    hdr = w[:0x18]
    ncode = (hdr[5] << 16) | hdr[6]
    return w[0x18:0x18 + ncode], ncode


def build(code):
    """Decode once and return (instructions, stub->trapnum, function entries)."""
    ins = list(xapvm.decode(code))
    stubs, _ = xapvm.find_stubs(code)
    names = {num: nm for nm, num in
             json.load(open(os.path.join(ROOT, 'tools/traps-bluelab73.json'))).items()}
    stub_name = {}
    for addr, num in (stubs.items() if isinstance(stubs, dict) else stubs):
        stub_name[addr] = names.get(num, 'trap_%#x' % num)

    by_addr = {a: (op, v, ln) for a, op, v, ln in ins}
    entries, callers, callees = set(), {}, {}
    for a, op, v, ln in ins:
        if op == 0x0B:                       # enterl: a function prologue
            entries.add(a)
        elif op == BSR:
            tgt = (a + ln - 1 + v) & 0x3FFFF
            entries.add(tgt)
            callers.setdefault(tgt, set()).add(a)
            callees.setdefault(a, tgt)
    return ins, by_addr, stub_name, sorted(entries), callers, callees


def fn_of(entries, a):
    """The entry address of the function containing `a`."""
    lo, hi = 0, len(entries) - 1
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if entries[mid] <= a:
            best = entries[mid]; lo = mid + 1
        else:
            hi = mid - 1
    return best


def render(a, op, v, ln, code, stub_name, entries):
    words = ' '.join('%04x' % code[a + k] for k in range(ln))
    text = xapvm.mnemonic(op, v)
    note = ''
    if op == BSR:
        tgt = (a + ln - 1 + v) & 0x3FFFF
        nm = stub_name.get(tgt)
        note = '  -> %s' % (nm if nm else 'fn_%05x' % tgt)
    elif op in BRANCHES:
        # Branches use the SAME last-word rule as bsr (a+ln-1+v), proven by a boundary
        # census of Bose's 2103 multi-word branches: 100% land on an instruction boundary,
        # versus 42% for a+v. Printing `a+v` here is what produced the circular
        # "confirmation" of the wrong rule that crashed probe131 and probe132 -- I checked
        # the assembler against this annotation, and this annotation used the same rule.
        note = '  -> %#07x' % ((a + ln - 1 + v) & 0x3FFFF)
    flag = ''
    if ln >= 2 and all(blind_byte(operand_byte(a + k)) for k in range(ln)):
        flag = '   [BLIND: all %d operand bytes writable]' % ln
    return '  %#07x: %-18s %-22s%s%s' % (a, words, text, note, flag)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fn', help='disassemble one function, e.g. 0x846')
    ap.add_argument('--hooks', action='store_true', help='only the hook-site report')
    args = ap.parse_args()

    code, ncode = load()
    ins, by_addr, stub_name, entries, callers, callees = build(code)
    eset = set(entries)
    print('decoded %d instructions over %d code words; %d function entries, '
          '%d trap stubs' % (len(ins), ncode, len(entries), len(stub_name)),
          file=sys.stderr)

    if args.fn:
        want = int(args.fn, 16)
        start = want if want in eset else fn_of(entries, want)
        nxt = next((e for e in entries if e > start), ncode)
        print('function %#x .. %#x  (%d words)' % (start, nxt, nxt - start))
        print('called by: %s' % ', '.join('%#x' % c for c in sorted(callers.get(start, ()))) or 'nobody')
        for a, op, v, ln in ins:
            if start <= a < nxt:
                print(render(a, op, v, ln, code, stub_name, entries))
        return 0

    # ---- the hook-site report
    hooks = []
    for a, op, v, ln in ins:
        if ln < 2 or op not in (BSR,) + BRANCHES:
            continue
        if not all(blind_byte(operand_byte(a + k)) for k in range(ln)):
            continue
        # Both forms use the last-word rule; see render(). This value is written into
        # build/analysis/hook-sites.txt as a hook's 'current target', so getting it
        # wrong mis-describes every multi-word branch site in that report.
        tgt = (a + ln - 1 + v) & 0x3FFFF
        hooks.append((a, op, ln, tgt, fn_of(entries, a)))

    path = os.path.join(ROOT, 'build/analysis/hook-sites.txt')
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('# Redirectable call/branch sites: every operand byte is inside a DFU\n'
                '# blind window, so the target can be rewritten without touching a byte\n'
                '# the RSA signature covers. This is the property that made 0x0AE0 the\n'
                '# original hook; these are all the alternatives.\n#\n'
                '# addr      form  words  current target        enclosing fn\n')
        for a, op, ln, tgt, fn in hooks:
            nm = stub_name.get(tgt)
            f.write('%#07x  %-5s %d      %-20s  fn_%05x\n'
                    % (a, 'bsr' if op == BSR else 'br%02x' % op, ln,
                       nm if nm else '%#07x' % tgt, fn or 0))
    print('%d redirectable sites -> build/analysis/hook-sites.txt' % len(hooks),
          file=sys.stderr)
    if args.hooks:
        return 0

    # ---- the full disassembly
    path = os.path.join(ROOT, 'build/analysis/full-disasm.txt')
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('# Whole-image disassembly of vm.app, %d code words, %d instructions.\n'
                '# Trap stubs named from the BlueLab 7.3 table (docs/trap-numbering.md);\n'
                '# the 7.4 names in build/analysis/functions/*.lst are WRONG.\n'
                '# [BLIND] marks an instruction whose operand bytes are all DFU-writable.\n\n'
                % (ncode, len(ins)))
        cur = None
        for a, op, v, ln in ins:
            if a in eset and a != cur:
                cur = a
                nm = stub_name.get(a)
                f.write('\n%s fn_%05x%s\n' % ('=' * 8, a, '  [trap stub: %s]' % nm if nm else ''))
                cs = sorted(callers.get(a, ()))
                f.write('   called by: %s\n' % (', '.join('%#x' % c for c in cs) if cs else '(no bsr found)'))
            f.write(render(a, op, v, ln, code, stub_name, entries) + '\n')
    print('full disassembly -> build/analysis/full-disasm.txt', file=sys.stderr)

    # ---- xrefs: callers/callees, and global readers/writers
    # Classify a mode-1 (@abs) access as a read or a write by its opcode family.
    # Only `st` (hi=2) writes; the shifts (hi=A) read AND write; everything else that
    # takes a memory operand -- ld, add, sub, cmp, mul/div/tst, or, and, xor -- reads.
    # An earlier version of this treated hi=A and hi=E as writes, which made 168
    # globals look "written but never read" and sent me looking for a pointer-access
    # explanation that does not exist (it accounted for exactly one of them).
    globs = {}
    for a, op, v, ln in ins:
        if (op & 3) == 1 and 0 <= v <= 0xFFFF:       # mode 1 = @abs
            hi = op >> 4
            if hi == 0x2:
                rw = ('w',)
            elif hi == 0xA:
                rw = ('r', 'w')
            elif hi in (0x1, 0x3, 0x5, 0x8, 0x9, 0xB, 0xC, 0xD):
                rw = ('r',)
            else:
                continue                             # not a memory operand we trust
            g = globs.setdefault('%#06x' % v, {'r': [], 'w': []})
            for k in rw:
                g[k].append('%#x' % a)
    xref = {
        'functions': {'%#x' % e: {'callers': ['%#x' % c for c in sorted(callers.get(e, ()))],
                                  'stub': stub_name.get(e)} for e in entries},
        'globals': globs,
    }
    path = os.path.join(ROOT, 'build/analysis/xref.json')
    json.dump(xref, open(path, 'w'), indent=0)
    print('xrefs -> build/analysis/xref.json (%d globals)' % len(globs), file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
