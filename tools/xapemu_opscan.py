#!/usr/bin/env python3
"""xapemu_opscan: which opcodes in the speaker's vm.app does tools/xapemu.py NOT model? (2026-10-19)

Decodes every instruction of vm.app with xapvm.decode (prefixes folded), counts each opcode byte,
then probes the emulator with a one-instruction synthetic program per opcode (and per special
operand for 0x09). An opcode is "unmodelled" iff the emulator raises 'unmodelled opcode'. Any other
outcome (a result, a branch to a missing address, a trap-tail refusal, a divide by zero) means the
dispatch has a branch for it. Offline only; reads firmware/bose/extracted/internal_fs/vm.app.

usage: python tools/xapemu_opscan.py [--sites]   (--sites lists the first addresses of each gap)
"""
import os, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import xapemu, xapvm

VMAPP = os.path.join(os.path.dirname(HERE), "firmware", "bose", "extracted", "internal_fs", "vm.app")


def probe(op, operand=1):
    w = [0] * 24
    w[4] = 24
    code = [((operand & 0xFF) << 8) | op, 0x00E2, 0x00E2]
    w[6] = len(code)
    vm = xapemu.VM(w + code)
    vm.X = vm.Y = 0x800
    try:
        vm.run(0, max_steps=10)
    except RuntimeError as e:
        return "unmodelled" if "unmodelled opcode" in str(e) else "handled (%s)" % str(e)[:40]
    except Exception as e:                                 # struct errors etc: still dispatched
        return "handled (%s)" % type(e).__name__
    return "handled"


def main():
    words = xapemu.load_vm_app(VMAPP)
    vm = xapemu.VM(words)
    cnt = collections.Counter()
    first = collections.defaultdict(list)
    ncode = (words[5] << 16) | words[6]          # code words; the const pool follows and is data
    for a, op, v, ln in xapvm.decode(vm.code):
        if a >= ncode:
            break
        key = op
        if op == 0x09:
            key = (0x09, "modifier" if v == 0 else "brxl" if v == -2 else "other v=%d" % v)
        cnt[key] += 1
        if len(first[key]) < 4:
            first[key].append(a)
    total = sum(cnt.values())
    gaps = []
    print("%d instructions, %d distinct opcode classes" % (total, len(cnt)))
    for key in sorted(cnt, key=lambda k: (k if isinstance(k, int) else k[0], str(k))):
        op = key if isinstance(key, int) else key[0]
        operand = 1
        if isinstance(key, tuple):
            operand = 0 if key[1] == "modifier" else 0xFE if key[1] == "brxl" else 1
        r = probe(op, operand)
        if r == "unmodelled":
            gaps.append(key)
            print("UNMODELLED  %-22s %6d sites  first %s" % (
                ("%#04x" % key) if isinstance(key, int) else "0x09 " + key[1], cnt[key],
                " ".join("%#x" % x for x in first[key])))
    if not gaps:
        print("no opcode class is unmodelled")
    print("%d unmodelled class(es), %d sites" % (len(gaps), sum(cnt[k] for k in gaps)))
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(main())
