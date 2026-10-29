"""Minimal reader for CSR VM application images (vm.app, "BIGvmApp").

Decodes only what is needed to find firmware trap calls and the constant
arguments loaded before them. Encoding learned from xapasmcsr/ld output
on probe programs (see README.md):

  word = operand8 << 8 | opcode8
  opcode 0x00        prefix. Every operand byte, prefixes included, is
                     sign-extended and the bytes are summed at their
                     positions: 5600 7814 = 0x5678, AC00 CD10 = 0xABCD
                     The word 0x0000 is NOT treated as a prefix; it decodes
                     as its own one-word instruction (op 0x00, operand 0).
  0x14 ld AL,#imm    0x10 ld AH,#imm    0x18 ld X?,#imm (trap number in stubs)
  0x27 st AL,@(off,Y)  0x23 st AH,@(off,Y)  0x9C bsr rel    0xE0 bra rel
  trap stub:  FD0B  [prefix] nn18  [0000]  [prefix] xxE0
"""
import json
import os
import re
import struct

HERE = os.path.dirname(os.path.abspath(__file__))


def load_words(path):
    data = open(path, "rb").read()
    if data[:1] in (b"@", b"#"):
        mem = {}
        for line in data.decode(errors="replace").splitlines():
            m = re.match(r"@([0-9A-Fa-f]+)\s+([0-9A-Fa-f]{1,4})\b", line)
            if m:
                a = int(m.group(1), 16)
                if a in mem:
                    raise SystemExit(f"{path}: address {a:#x} appears twice")
                mem[a] = int(m.group(2), 16)
        missing = [a for a in range(max(mem, default=-1) + 1) if a not in mem]
        if missing:
            raise SystemExit(f"{path}: {len(missing)} words missing (first at {missing[0]:#x}); "
                             "refusing to compact a gapped image")
        words = [mem[a] for a in range(len(mem))]
    else:
        words = list(struct.unpack(f"<{len(data) // 2}H", data[:len(data) // 2 * 2]))
    if words[:4] != [0x4249, 0x4776, 0x6D41, 0x7070]:
        raise SystemExit(f"{path}: not a VM app")
    return words


def sext8(b):
    return b - 0x100 if b & 0x80 else b


def decode(code, fold_zero=True):
    """Yield (addr, opcode, value, length) with prefixes folded in.

    `fold_zero` selects what the word `0x0000` means, and both answers are needed:

    * **True** (default, for analysing Bose's code): it is a prefix carrying operand
      byte 0x00. Required for any chain with a zero middle byte -- see the comment in
      the loop below; 21 call targets were wrong without it.
    * **False** (for verifying a cave): it is a standalone no-op. A cave is written
      into the const pool's ZERO RUNS, so with folding enabled the thousands of
      leading zeros ahead of it absorb into its first instruction and that
      instruction's address stops being a decode boundary -- which is exactly what
      the probe assemblers' decode-verify checks. Inside a cave a `0x0000` is padding
      we emitted, never a prefix, so the simpler reading is the correct one there.
    """
    i = 0
    n = len(code)
    while i < n:
        start = i
        val = 0
        # `0x0000` IS a legitimate prefix -- one carrying operand byte 0x00 -- and
        # excluding it (as this loop used to, to treat it as a nop) broke any chain that
        # needed a zero middle byte. At 0x07b82 the words `0200 0000 c69c` are one 3-word
        # bsr to 0x27b4a; the old rule split off the prefixes and decoded `c69c` alone as
        # `bsr -58`, giving 0x7b4a -- a different function. 21 call targets were wrong.
        #
        # Folding it unconditionally is safe: standing alone it contributes nothing,
        # because (val + 0) << 8 leaves a zero accumulator at zero, so the following
        # instruction's value is unchanged and the only difference is that the nop is
        # absorbed into that instruction's length instead of being yielded separately.
        # That also matches the hardware, where probe77's three `0x0000` words behaved as
        # nops -- a prefix contributing zero is indistinguishable from one.
        while i < n and (code[i] & 0xFF) == 0x00 and (fold_zero or code[i] != 0x0000):
            val = (val + sext8(code[i] >> 8)) << 8
            i += 1
        if i >= n:
            break
        op = code[i] & 0xFF
        val += sext8(code[i] >> 8)
        i += 1
        yield start, op, val, i - start


# The speaker's vm.app is a BlueLab 7.3 image (VM version stamp 0x3200), and
# trap numbers are NOT stable between BlueLab versions -- 173 of the 257 names
# shared by 7.3.1 and 7.4 are numbered differently. Naming this image's stubs
# from the 7.4 table is what made probes 46/47 call KalimbaPowerOff and probes
# 52-56 call StreamScoSink. See docs/trap-numbering.md.
TRAPS = os.path.join(HERE, os.pardir, "traps-bluelab73.json")


def trap_table():
    """Trap number -> name, for the BlueLab version this image was built with."""
    return {v: k for k, v in json.load(open(TRAPS)).items()}


def _zero_word(code, ins):
    a, op, v, ln = ins
    return ln == 1 and code[a] == 0x0000


def find_stubs(code):
    """Map stub address -> trap number. A stub is enterl -3; ld X,#n; bra,
    with at most one 0x0000 word between the ld and the bra."""
    stubs = {}
    ins = list(decode(code))
    for k in range(len(ins) - 2):
        a, op, v, _ = ins[k]
        if op == 0x0B and v == -3 and ins[k + 1][1] == 0x18:
            nxt = ins[k + 2]
            if _zero_word(code, nxt) and k + 3 < len(ins):
                nxt = ins[k + 3]
            if nxt[1] == 0xE0:
                stubs[a] = ins[k + 1][2] & 0xFFFF
    return stubs, ins


def calls(ins, stubs):
    """Yield (call_addr, stub_addr, preceding instructions) for bsr to a stub."""
    for k, (a, op, v, ln) in enumerate(ins):
        if op == 0x9C:
            target = a + ln - 1 + v
            if target in stubs:
                yield a, target, ins[max(0, k - 8):k]


def args(prev):
    """Constant-track AL/AH and @(n,Y) stack stores over the instructions
    before a call. Returns (arg1, arg2, clean): args are None when not
    constant. Every modelled op that writes AL/AH/Y (non-immediate loads,
    and, shifts, calls, frame changes) invalidates what it overwrites.
    clean is False only if a reported constant was followed by an
    unmodelled opcode that might have changed it."""
    AH, AL, X, Y = 0, 1, 2, 3
    reg = {AH: None, AL: None}      # value -> (val16, doubt) or None
    stack = {}
    for a, op, v, ln in prev:
        hi, r, mode = op >> 4, (op >> 2) & 3, op & 3
        if op in (0x9C, 0xE0) or op in _BRANCHES:   # branches clobber; post-branch code is only reached by jump
            reg = {AH: None, AL: None}
            stack = {}
        elif op in (0xF0, 0xF4, 0x9B) or hi == 0x8:   # beq/bne/tst/cmp: flags only
            pass
        elif op in (0x0B, 0x0F):            # enterl/leavel move Y
            stack = {}
        elif hi in (0x1,):                  # ld
            if r in reg:
                reg[r] = (v & 0xFFFF, False) if mode == 0 else None
            elif r == Y:
                stack = {}
        elif hi == 0xC:                     # and
            if r in reg:
                reg[r] = (reg[r][0] & v & 0xFFFF, reg[r][1]) if mode == 0 and reg[r] else None
            elif r == Y:
                stack = {}
        elif hi in (0x3, 0x5, 0xB, 0xD):    # add/sub/or/xor: result unknown
            if r in reg:
                reg[r] = None
            elif r == Y:
                stack = {}
        elif hi == 0x2 and mode == 3:       # st reg,@(n,Y)
            stack[v] = reg.get(r)
        elif hi == 0x2 and mode == 2:       # st reg,@(n,X): may alias the frame
            stack = {k: s and (s[0], True) for k, s in stack.items()}
        elif hi == 0x2 and mode == 1:       # st reg,@abs: registers unchanged
            pass
        elif 0xA0 <= op <= 0xA7:            # shift-like, unconfirmed: assume AH:AL written
            reg = {AH: None, AL: None}
        else:                               # unmodelled: keep values, but mark them doubtful
            reg = {k: s and (s[0], True) for k, s in reg.items()}
            stack = {k: s and (s[0], True) for k, s in stack.items()}
    doubt = False
    a1 = a2 = None
    if reg[AH] and reg[AL]:
        a1 = reg[AH][0] << 16 | reg[AL][0]
        doubt |= reg[AH][1] or reg[AL][1]
    s0, s1 = stack.get(0), stack.get(1)
    if s0 and s1:
        a2 = s0[0] << 16 | s1[0]
        doubt |= s0[1] or s1[1]
    return a1, a2, not doubt


def pio_report(path):
    w = load_words(path)
    code = w[w[4]:]
    stubs, ins = find_stubs(code)
    t = trap_table()
    out = []
    for a, s, prev in calls(ins, stubs):
        name = t.get(stubs[s], hex(stubs[s]))
        if name.startswith("Pio"):
            a1, a2, clean = args(prev)
            out.append((a, name, a1, a2, clean))
    return stubs, out


# opcode families learned from probe3 (adk/work/probe/probe3.*, 2026-09-27;
# .s mnemonic <-> word alignment, all verified):
#   word = operand8<<8 | opcode8; opcode = op<<4 | reg<<2 | mode for the
#   _OPS families (mode: 0 #imm, 1 @abs, 2 @(n,X), 3 @(n,Y); reg AH,AL,X,Y).
#   add 0x3x (e035 = add AL,@$XAP_AH), sub 0x5x, or 0xBx, xor 0xDx.
#   Shifts (count in operand): asl = 0xA0 (01a0 = asl #1), asr = 0xA4
#   directly, lsr = 0x0009 (clc) then 0xA4; variable count: asl @ = 0xA1,
#   lsr/asr @ = 0xA5 with the count operand (e3a1 = asl @$XAP_UXL).
#   mul = 0x91 (16x16). neg = 0x74. rts = 0x00E2.
#   Branches (rel8, target = word after the instruction + operand):
#   bne F0, beq F4, bcc F8, bcs FC, bgt 0x20, bge 0x24, ble 0x28, bcz 0x2C
#   (the st-family mode-0 slots 0x2x double as signed branches).
_OPS = {0x1: "ld", 0x2: "st", 0x3: "add", 0x5: "sub", 0x8: "cmp", 0xB: "or",
        0xC: "and", 0xD: "xor"}
_REGS = ("AH", "AL", "X", "Y")
_SPECIAL = {0x9C: "bsr", 0xE0: "bra", 0xF0: "bne", 0xF4: "beq", 0x0B: "enterl",
            0x0F: "leavel", 0xE2: "rts", 0xF8: "bcc", 0xFC: "bcs", 0x20: "bgt",
            0x24: "bge", 0x28: "ble", 0x2C: "bcz", 0x74: "neg",
            0x09: "clc"}
# 0xE4/0xE8/0xEC are conditional branches whose exact condition is not established,
# but their flow is: each one sits inside a compare-ladder (`cmp ; b?? +n ; cmp`),
# and the probe assemblers have verified branch encodings across all twelve of these
# opcodes on hardware. They were missing here, so register-clobber tracking and
# `listing()` treated 127 real branches as opaque. See docs/firmware-map.md.
_BRANCHES = {0x9C, 0xE0, 0xE4, 0xE8, 0xEC, 0xF0, 0xF4, 0xF8, 0xFC,
             0x20, 0x24, 0x28, 0x2C}


def _h(v):
    """16-bit hex; negative values are shown two's-complement."""
    return f"{v & 0xFFFF:#x}"


def mnemonic(op, v):
    if op in _SPECIAL:
        return f"{_SPECIAL[op]} {v:+d}"
    # The two opcodes of the common trap tail at 0x294/0x295 (J-T12 section 2, proven from the ADK's
    # own common_trap_code source): `ld XH,@(n,Y)` and `bra @abs` (an indirect jump through the data
    # cell). They printed as `?0e -1` / `?e1 -3` before 2026-10-12; the text of an already generated
    # build/analysis/*-disasm.txt keeps the old spelling until it is regenerated. NOT added to
    # _BRANCHES: `bra @abs` has no relative target.
    if op == 0x0E:
        return f"ld XH,@({v},Y)"
    if op == 0xE1:
        return f"bra @{_h(v)}"
    if op == 0x9B:
        return f"tst @({v},Y)"
    if op == 0xA0:
        return f"asl #{v & 0xFFFF:#x}"
    if op == 0xA4:
        return f"asr #{v & 0xFFFF:#x}"
    if op in (0xA1, 0xA5):
        return f"{'asl' if op == 0xA1 else 'asr'} @{_h(v)}"
    if op == 0x91:
        hi, reg, mode = (op >> 4), (op >> 2) & 3, op & 3
        arg = (f"#{_h(v)}", f"@{_h(v)}", f"@({v},X)", f"@({v},Y)")[1]
        return f"mul {arg}"
    hi, reg, mode = op >> 4, (op >> 2) & 3, op & 3
    arg = (f"#{_h(v)}", f"@{_h(v)}", f"@({v},X)", f"@({v},Y)")[mode]
    if op == 0x00 and v == 0:
        return "nop"                       # hardware agrees: probe77 wrote three
    if hi == 0x9:
        # In this family `reg` picks the OPERATION and `mode` the addressing, which
        # is why only three of its sixteen slots were ever named. Established
        # empirically over the whole image (docs/firmware-map.md): 0x9A is followed
        # by a conditional branch at 1022 of 1029 sites and 0x99 at 425 of 430, so
        # both are `tst`; 0x90 is followed by stores of BOTH AH and AL, i.e. a
        # 32-bit result, so it is `mul`; 0x94/0x95/0x97 are preceded by `clc` at
        # 72-100% of sites and store a single word, so they are `div`.
        if reg == 3:
            return f"bsr {v:+d}"
        return f"{('mul', 'div', 'tst')[reg]} {arg}"
    if hi == 0xA:
        return f"{('asl', 'asr')[reg & 1]} {arg}"
    if hi in (0x4, 0x6):
        # Carry arithmetic, completing the set `3=add 4=adc 5=sub 6=sbc`. Established
        # over the whole image: hi=4 follows an `add` at 97 of 99 sites and hi=6 follows
        # a `sub` at 9 of 9 -- but ONLY once the `nop` that sits between the low-half and
        # high-half operations is skipped. A first attempt tested for an immediately
        # preceding `add`, found 0 of 99, and wrongly recorded the reading as refuted.
        return f"{('adc' if hi == 0x4 else 'sbc')} {_REGS[reg]},{arg}"
    if hi == 0x7:
        # 0x74 is documented as `neg`; the family extends by mode. Inferred, not proven:
        # these 28 sites follow a `ld` 60% of the time rather than showing a carry
        # pattern, so the operation is right but the semantics are not nailed down.
        return f"neg? {arg}"
    if op in (0xE4, 0xE8, 0xEC):
        return f"b?{op:02x} {v:+d}"         # conditional; exact condition unknown
    if hi in _OPS:
        return f"{_OPS[hi]} {_REGS[reg]},{arg}"
    return f"?{op:02x} {v}"


def listing(path, lo, hi):
    w = load_words(path)
    code = w[w[4]:]
    stubs, ins = find_stubs(code)
    t = trap_table()
    for a, op, v, ln in ins:
        if lo <= a < hi:
            m = mnemonic(op, v)
            if op == 0x9C:
                tgt = a + ln - 1 + v
                m += f"  -> {t.get(stubs[tgt], hex(stubs[tgt])) if tgt in stubs else hex(tgt)}"
            elif op in _BRANCHES:
                # Last-word rule, as for bsr above. See tools/disasm.py render().
                m += f"  -> {a + ln - 1 + v:#x}"
            print(f"{a:#07x}  {' '.join(f'{x:04X}' for x in code[a:a + ln]):15s} {m}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        raise SystemExit("usage: python xapvm.py <vm.app>")
    stubs, rows = pio_report(sys.argv[1])
    print(f"{len(stubs)} trap stubs")
    for a, name, a1, a2, clean in rows:
        f = lambda x: "?" if x is None else f"0x{x:08x}"
        print(f"{a:#08x} {name:22s} arg1={f(a1)} arg2={f(a2)}{'' if clean else '  (window has other ops)'}")
