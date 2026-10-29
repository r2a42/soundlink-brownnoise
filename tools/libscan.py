#!/usr/bin/env python3
"""libscan: match EVERY ADK library function against Bose's image.

`tools/libmatch.py` finds library functions by linking a probe first, so it
only ever sees what that probe pulled in. This skips the linker entirely.

The ADK's `.a` libraries are gzip-compressed `.xap` **assembler text**, so
every function in all 153 of them can be read directly. Converting a
function's mnemonics to opcodes with the verified table
(`docs/xap-opcodes.md`) gives the same relocation-proof signature
`libmatch` uses, without needing the function to be reachable from any
program we can write.

    python tools/libscan.py                 # every library
    python tools/libscan.py gain audio      # only libraries matching a name
    python tools/libscan.py --min 14        # stricter length floor

A match means Bose's image contains that function's exact opcode sequence.
A miss means nothing: Bose may not use it, or its source may differ between
BlueLab 7.3 (the speaker) and 7.4 (these libraries).
"""
import argparse
import glob
import gzip
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIBDIR = os.path.join(ROOT, 'adk/root/tools/lib/BlueLab-7.4-Release/assisted')
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import libmatch                                                # noqa: E402

REG = {'ah': 0, 'al': 1, 'x': 2, 'y': 3}
HI = {'ld': 0x1, 'st': 0x2, 'add': 0x3, 'addc': 0x4, 'sub': 0x5,
      'subc': 0x6, 'nadd': 0x7, 'cmp': 0x8, 'or': 0xB, 'and': 0xC, 'xor': 0xD}
PAIR = {'asl': 0xA0, 'lsl': (0x09, 0xA0), 'asr': 0xA4, 'lsr': (0x09, 0xA4),
        'smult': 0x90, 'umult': (0x09, 0x90),
        'sdiv': 0x94, 'udiv': (0x09, 0x94), 'tst': 0x98}
FIXED = {'nop': 0x00, 'brxl': 0x09, 'enterl': 0x0B, 'leavel': 0x0F,
         'rts': 0xE2, 'bgt': 0x20, 'bge': 0x24, 'ble': 0x28, 'bcz': 0x2C,
         'blt': 0xE4, 'bpl': 0xE8, 'bmi': 0xEC, 'bne': 0xF0, 'beq': 0xF4,
         'bcc': 0xF8, 'bcs': 0xFC}


def mode_of(operand):
    """0 #imm, 1 @abs, 2 @(n,X), 3 @(n,Y) -- from the operand text alone."""
    o = operand.strip()
    if o.startswith('#'):
        return 0
    if o.startswith('@('):
        return 3 if o.rstrip(')').endswith(('Y', 'y')) else 2
    if o.startswith('@'):
        return 1
    return None


def encode(line):
    """One assembler line -> [opcodes], or None if it cannot be encoded."""
    parts = line.split(None, 1)
    mn = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ''
    if mn in FIXED:
        return [FIXED[mn]]
    if mn == 'bra':
        return [0xE1 if rest.startswith('@') else 0xE0]
    if mn == 'bsr':
        return [0x9E if rest.endswith(',X') or rest.endswith(',x') else 0x9C]
    if mn in PAIR:
        m = mode_of(rest)
        if m is None:
            return None
        base = PAIR[mn]
        if isinstance(base, tuple):
            return [base[0], base[1] | m]
        return [base | m]
    if mn in HI:
        if ',' not in rest:
            return None
        reg, operand = rest.split(',', 1)
        r = REG.get(reg.strip().lower())
        m = mode_of(operand)
        if r is None or m is None:
            return None
        return [(HI[mn] << 4) | (r << 2) | m]
    return None


def functions(path):
    """{name: [opcodes]} for every function in a .a archive or a .s file.

    Compiler `-S` output is accepted as well as a library, and is exactly as
    good a signature source: with the ADK's own flags, the assembly `-S`
    emits is **opcode-identical** to what the linker produces. Verified on
    build/opprobe/more.c -- 46 opcodes from -S, the same 46 from the linked
    image. (The ABI mix-up recorded in docs/vm-trap-calling-convention.md
    was never about `-S`; it was about compiling without `-mal-first`.)
    """
    if path.endswith('.s'):
        text = open(path, encoding='latin1').read()
    else:
        text = gzip.open(path, 'rb').read().decode('latin1')
    out, name, ops, bad = {}, None, [], False
    for raw in text.split('\n'):
        line = raw.rstrip('\r')
        if not line.strip():
            continue
        if line.startswith((';', '^')):
            continue
        if not line[0].isspace():
            lbl = line.split(':')[0].strip()
            if not lbl.startswith('$_'):
                continue          # ?LBB_/?L local labels sit INSIDE a function
            if name and ops and not bad:
                out[name] = ops
            name, ops, bad = lbl, [], False
            continue
        tok = line.split()
        if not tok:
            continue
        if tok[0].upper() in ('MODULE', 'ENDMOD', '.LARGE', '.ENHANCED',
                              '.CODE', '.SEG', 'DS', 'DC', 'dc', 'ORG',
                              'EQU', 'DEQU', 'CEQU', '.ALL', 'INCLUDE',
                              '.PACK', 'GLOBAL', 'END'):
            continue
        e = encode(line.strip())
        if e is None:
            bad = True
        elif not bad:
            ops.extend(e)
    if name and ops and not bad:
        out[name] = ops
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('filter', nargs='*', help='only libraries whose name matches')
    ap.add_argument('--min', type=int, default=12)
    ap.add_argument('--asm', metavar='DIR',
                    help='scan compiler -S output from DIR/*.s instead of the libraries')
    args = ap.parse_args()

    ops, addrs = libmatch.bose_opcodes()
    # Searching 191k opcodes for each of thousands of needles is far too slow
    # in Python. Both haystack and needle are byte values, so hand the search
    # to bytes.find, which runs at C speed.
    hay = bytes(ops)
    if args.asm:
        libs = sorted(glob.glob(os.path.join(args.asm, '*.s')))
    else:
        libs = sorted(glob.glob(os.path.join(LIBDIR, '*.a')))
    if args.filter:
        libs = [p for p in libs if any(f in os.path.basename(p) for f in args.filter)]
    total = scanned = 0
    hits = []
    for p in libs:
        try:
            fns = functions(p)
        except Exception:
            continue
        base = os.path.basename(p)
        lib = base[:-2] if base.endswith('.s') else base[3:-2]
        for name, seq in fns.items():
            if len(seq) < args.min:
                continue
            scanned += 1
            needle = bytes(seq)
            k, count, first = hay.find(needle), 0, None
            while k != -1:
                if first is None:
                    first = k
                count += 1
                k = hay.find(needle, k + 1)
            if first is not None:
                hits.append((len(seq), name, lib, addrs[first], count))
        total += 1
    hits.sort(reverse=True)
    at = {a: i for i, a in enumerate(addrs)}
    seen, rows = set(), []
    for n, name, lib, addr, count in hits:
        if addr in seen:
            continue
        seen.add(addr)
        rows.append((addr, name[2:], lib, n, count, ops[at[addr]] == 0x0B))

    # Quality signal, reported rather than assumed: a coincidental opcode run
    # would almost always land in the MIDDLE of a function. One that starts on
    # an `enterl` is a function entry, which is what a real match looks like.
    on_entry = sum(1 for r in rows if r[5])
    strict = [r for r in rows if r[5] and r[3] >= 25]
    print('# scanned %d libraries, %d functions of >=%d instructions'
          % (total, scanned, args.min))
    print('# %d distinct addresses matched' % len(rows))
    print('# %d of them (%.0f%%) begin at an `enterl`, i.e. a real function entry'
          % (on_entry, 100.0 * on_entry / max(1, len(rows))))
    print('# %d are high confidence: >=25 instructions AND on an entry\n' % len(strict))
    print('%-9s %-42s %-24s %-6s %s'
          % ('address', 'function', 'library', 'insns', 'entry'))
    for addr, name, lib, n, count, entry in rows:
        print('0x%05X  %-42s %-24s %-6d %s%s'
              % (addr, name, lib, n, 'yes' if entry else 'NO',
                 '  (%d sites)' % count if count > 1 else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
