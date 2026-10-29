#!/usr/bin/env python3
"""callsites: what arguments Bose passes to a given trap.

Reports call sites under the ABI that was verified by compiling and
linking probe apps (docs/trap-abi.md, docs/message-task-abi.md):

    arg1 -> AL, arg2 -> AH, args 3..n -> @(0,Y), @(1,Y), ...
    a 32-bit argument takes two slots, HIGH word first
    return <- AL

`tools/xapvm.args()` predates that and tracks the older, wrong model
(32-bit arg1 in AH:AL, arg2 in the slots); its numbers must not be read as
argument 1 and argument 2. This module exists so nobody has to.

Values are constant-tracked backwards over a short window and reported
only when they are provably constant at the call. Anything loaded from
memory, computed, or crossing a branch is reported as None -- never
guessed. That is the whole point: three wrong conclusions in this project
came from reading call sites optimistically.

    python tools/callsites.py StreamAudioSink SinkConfigure
    python tools/callsites.py --list
"""
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, 'firmware/bose/extracted/internal_fs/vm.app')
HDR_WORDS = 24
WINDOW = 12            # instructions of backward context to track

AH, AL, X, Y = 0, 1, 2, 3
_BRANCH_OPS = {0xE0, 0xF0, 0xF4, 0xF8, 0x9C}


def sext8(b):
    return b - 256 if b & 0x80 else b


def load_words(path):
    d = open(path, 'rb').read()
    return [struct.unpack_from('<H', d, i)[0] for i in range(0, len(d) & ~1, 2)]


def decode(code):
    """Yield (a, opcode, folded_value, n_words) in the project's `a` space."""
    i, n = HDR_WORDS, len(code)
    while i < n:
        start, v, k = i, 0, 0
        while i < n and (code[i] & 0xFF) == 0x00 and code[i] != 0x0000 and k < 3:
            v = (v + sext8(code[i] >> 8)) << 8
            i += 1
            k += 1
        if i >= n:
            return
        w = code[i]
        i += 1
        yield start - HDR_WORDS, w & 0xFF, v + sext8(w >> 8), i - start


def find_stubs(ins):
    stubs = {}
    ins = list(ins)
    for k in range(len(ins) - 2):
        a, op, v, _ = ins[k]
        if op == 0x0B and v == -3 and ins[k + 1][1] == 0x18:
            nxt = ins[k + 2]
            if nxt[1] == 0x00 and k + 3 < len(ins):
                nxt = ins[k + 3]
            if nxt[1] == 0xE0:
                stubs[a] = ins[k + 1][2] & 0xFFFF
    return stubs


def track(prev):
    """Constant-track AL, AH and the outgoing @(n,Y) slots.

    Returns (al, ah, slots) where each is a value or None. None means
    'not provably constant here', not 'zero'.
    """
    reg = {AH: None, AL: None}
    slots = {}
    for a, op, v, ln in prev:
        hi, r, mode = op >> 4, (op >> 2) & 3, op & 3
        if op in _BRANCH_OPS:                    # control flow joins: know nothing
            reg = {AH: None, AL: None}
            slots = {}
        elif op in (0x0B, 0x0F):                 # enterl/leavel: function boundary
            # Anything before an `enterl` belongs to a DIFFERENT function, so
            # AL and AH hold incoming arguments, not constants we can read.
            # Not clearing them here is how "Bose passes negative Kalimba
            # ports" got into the project: the 0xFFFB at 0x1CAA3 is the tail
            # of the function BEFORE the one that calls the trap at 0x1CAA6.
            reg = {AH: None, AL: None}
            slots = {}
        elif hi == 0x8 or op in (0x9B,):         # cmp/tst: flags only
            pass
        elif hi == 0x1:                          # ld
            if r in reg:
                reg[r] = (v & 0xFFFF) if mode == 0 else None
            elif r == Y:
                slots = {}
        elif hi == 0xC and mode == 0:            # and reg,#imm
            if r in reg:
                reg[r] = None if reg[r] is None else (reg[r] & v & 0xFFFF)
        elif hi == 0x2 and mode == 3:            # st reg,@(n,Y)
            slots[v] = reg.get(r) if r in reg else None
        elif hi == 0x2 and mode in (1, 2):       # st to memory: registers intact
            pass
        else:                                    # anything else: assume it wrote
            if r in reg:
                reg[r] = None
            elif r == Y:
                slots = {}
    return reg[AL], reg[AH], slots


def call_sites(ins, stubs, stub_addr):
    ins = list(ins)
    for k, (a, op, v, ln) in enumerate(ins):
        if op != 0x9C:
            continue
        if a + ln - 1 + v != stub_addr:
            continue
        yield a, track(ins[max(0, k - WINDOW):k])


def _fmt(v):
    return 'None' if v is None else '%#06x' % v


def main(argv):
    names = json.load(open(os.path.join(ROOT, 'tools/bose-stubs.json')))
    if not argv or argv[0] == '--list':
        for n in sorted(names):
            print('%-34s 0x%03X' % (n, names[n]))
        return
    code = load_words(APP)
    ins = list(decode(code))
    stubs = find_stubs(ins)
    for name in argv:
        if name not in names:
            print('%s: not a stub in this image' % name)
            continue
        addr = names[name]
        print('\n== %s  (stub 0x%03X, trap 0x%02X) ==' % (name, addr, stubs.get(addr, -1)))
        print('%-10s %-10s %-10s %s' % ('site', 'arg1(AL)', 'arg2(AH)', 'stack slots'))
        n = 0
        for a, (al, ah, slots) in call_sites(ins, stubs, addr):
            s = ' '.join('@%d=%s' % (k, _fmt(slots[k])) for k in sorted(slots))
            print('0x%-8X %-10s %-10s %s' % (a, _fmt(al), _fmt(ah), s or '-'))
            n += 1
        print('%d call sites' % n)


if __name__ == '__main__':
    main(sys.argv[1:])
