#!/usr/bin/env python3
"""xapemu: a small XAP2 interpreter for tracing Bose vm.app functions.

Decodes with xapvm (91.7% opcode coverage; unknowns raise). Runs a
function with a synthetic frame, logs every memory EA read/written and
register state. Purpose: settle effective addresses the static reader
cannot (table walks), and later serve as the offline test bench for
cave code.

Semantics (from probe3/probe4 ground truth):
  - registers AH, AL, X, Y (16-bit); C, Z flags
  - word = operand8<<8 | opcode8, prefix chaining per xapvm.decode
  - mode 0 #imm, 1 @abs, 2 @(n,X), 3 @(n,Y); @(0xffe0..ffe4) = AH,AL,UX?,UY
  - asl/asr #n operate on the 32-bit AH:AL pair (probe4: asl#16;asr#14 = *4)
  - mul = 16x16 -> AH:AL
  - branches rel8: target = addr_after + operand
"""
import os, sys, struct

# relative to this file, not to one machine (J-T12 S2a; the old absolute path made a copy of tools/
# import the original's xapvm, which hid a scratch edit of xapvm from every scratch-tree test)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "xapvm"))
import xapvm


class VM:
    CONST_BASE = 0x7400                 # platform-fixed const window (.PACK in every probe)

    nofold = None      # (lo, hi) cave span to decode with fold_zero=False

    def __init__(self, words, trace_mem=True):
        """words = the FULL vm.app file (header at 0).

        Header layout (confirmed against our own linked probe apps and the
        speaker's image, docs/message-task-abi.md):
            words[4]      header size in words (24)
            words[5:7]    code size, 32-bit, HIGH word first
            words[7]      const size
        Code starts after the header and is indexed in the project's `a`
        space; const follows it and is mapped into DATA space at 0x7400.

        The previous version read the code size from words[6] alone and
        ended const at words[18]. That is harmless for a small app but
        wrong for the speaker's, whose code is 0x39BE2 words -- it put the
        const window tens of thousands of words off, so a cave reading its
        own constants would have seen garbage.
        """
        self.file = words
        code_words = (words[5] << 16) | words[6]
        const_start = words[4] + code_words
        self.const = words[const_start:const_start + words[7]]
        self.code = words[words[4]:]
        self.ram = bytearray(0x10000 * 2)    # data RAM (globals, stack, frames)
        self.AH = self.AL = self.X = self.Y = 0
        self.XH = 0                    # high half of the 32-bit X, at 0xFFE2
        self.C = self.Z = 0
        self.lastA = self.lastB = 0    # last cmp operands (for signed branches)
        self.unsigned_form = False     # set by the 0x0009 word, consumed by the next op
        self.N = 0                     # sign of the last result, for bpl/bmi
        self.trace_mem = trace_mem
        self.log = []
        # trapnum -> (AH, AL) or callable(trapnum, AH:AL, a2) -> (AH, AL):
        # injected return values when the emulator hits a trap stub, so a
        # cave's callers see plausible sinks/offsets without real firmware.
        self.STUB_RET = {}
        # code address -> (AH, AL) or callable(addr, AH:AL, a2): the same
        # thing for ORDINARY functions, so a cave's back-call into Bose's
        # own code can be short-circuited instead of executed.
        self.FUNC_RET = {}
        self.WATCH = set()                    # probe296: entry addresses that are only RECORDED (watched), the code still runs
        self.watched = []

    def rd(self, wa):
        # Mode-1 (abs) operands are SIGNED 8-bit sign-extended to 16 bits: the
        # word `e015` is `ld AL,@0xffe4` (sext8(0xe4) = -28 -> 0xFFE4), which is
        # how Bose's own code reads the frame-base register mirror (0x1192a,
        # 0x182d1). Unmasked, the negative wa misses the 0xFFE4 checks and
        # struct.unpack_from treats it as an offset from the END of ram -- found
        # by probe139, the first probe to use the idiom (2026-10-06).
        wa &= 0xFFFF
        if wa == 0xFFE0: return self.AH        # special register file
        if wa == 0xFFE1: return self.AL
        if wa == 0xFFE2: return self.XH
        if wa == 0xFFE3: return self.X
        if wa == 0xFFE4: return self.Y
        if self.CONST_BASE <= wa < self.CONST_BASE + len(self.const):
            v = self.const[wa - self.CONST_BASE]
            if self.trace_mem:
                self.log.append(("R", wa, v))
            return v
        v = struct.unpack_from("<H", self.ram, 2 * wa)[0]
        if self.trace_mem:
            self.log.append(("R", wa, v))
        return v

    def wr(self, wa, v):
        wa &= 0xFFFF                       # see the note in rd(): signed operands
        if wa == 0xFFE0: self.AH = v & 0xFFFF
        elif wa == 0xFFE1: self.AL = v & 0xFFFF
        elif wa == 0xFFE4: self.Y = v & 0xFFFF
        elif self.CONST_BASE <= wa < self.CONST_BASE + len(self.const):
            pass                               # const is read-only
        else:
            struct.pack_into("<H", self.ram, 2 * wa, v & 0xFFFF)
            if self.trace_mem:
                self.log.append(("W", wa, v & 0xFFFF))

    def ea(self, mode, v):
        if mode == 0:
            return None                        # immediate
        if mode == 1:
            return v & 0xFFFF                  # absolute (prefix-summed)
        if mode == 2:
            return (self.X + v) & 0xFFFF
        return (self.Y + v) & 0xFFFF

    def pair(self):
        return (self.AH << 16) | self.AL

    def setpair(self, p):
        self.AH = (p >> 16) & 0xFFFF
        self.AL = p & 0xFFFF

    def run(self, start, max_steps=200000):
        # `0x0000` IS a prefix word, so decode() folds zero runs into the
        # instruction that follows them -- which is right for real code and
        # wrong for a cave, because a cave lives INSIDE a const-pool zero run
        # and its entry word therefore stops being an instruction start. That
        # regression made every probe report "no instruction at <entry>",
        # probe90 included, after the fold was introduced.
        #
        # Fix: index real code folded, then overlay an unfolded decode for the
        # cave's own address span only (self.nofold, set by the caller). The
        # cave's assembler verifies itself the same way, with fold_zero=False.
        ins = {}
        for a, op, v, ln in xapvm.decode(self.code):
            ins[a] = (op, v, ln)
        if self.nofold:
            # one (lo, hi) span, or a list of spans (probe162: a cave in two clusters,
            # const window + code region; decoding everything between them unfolded
            # would corrupt the stock code in between)
            spans = self.nofold if isinstance(self.nofold, list) else [self.nofold]
            for a, op, v, ln in xapvm.decode(self.code, fold_zero=False):
                if any(lo <= a <= hi for lo, hi in spans):
                    ins[a] = (op, v, ln)
        stubs, _ = xapvm.find_stubs(self.code)
        self.traps = []                       # (trapnum, AH:AL, a2) recorded at stub calls
        self.calls_seen = []                  # (addr, AH:AL) for FUNC_RET short-circuits
        pc = start
        steps = 0
        calls = []
        while steps < max_steps:
            steps += 1
            if pc not in ins:
                raise RuntimeError(f"no instruction at {pc:#x}")
            op, v, ln = ins[pc]
            nxt = pc + ln
            hi, reg, mode = op >> 4, (op >> 2) & 3, op & 3
            R = ("AH", "AL", "X", "Y")
            if pc in self.WATCH and calls:
                self.watched.append((pc, self.pair()))
            if pc in self.FUNC_RET and calls:
                ret = self.FUNC_RET[pc]
                self.calls_seen.append((pc, self.pair()))
                self.AH, self.AL = (ret(pc, self.pair(), None) if callable(ret) else ret)
                self.AH &= 0xFFFF; self.AL &= 0xFFFF
                pc = calls.pop()
                continue
            if pc in stubs:
                # firmware trap: record and return (args: AH:AL, @(0,Y):@(1,Y))
                a2 = None
                s0 = self.rd((self.Y + 0) & 0xFFFF)
                s1 = self.rd((self.Y + 1) & 0xFFFF)
                a2 = (s0 << 16) | s1
                self.traps.append((stubs[pc], self.pair(), a2))
                ret = self.STUB_RET.get(stubs[pc])
                if ret is not None:
                    self.AH, self.AL = (ret(stubs[pc], self.pair(), a2) if callable(ret)
                                        else ret)
                    self.AH &= 0xFFFF; self.AL &= 0xFFFF
                if calls:
                    pc = calls.pop()
                    continue
                return "trap", pc
            if op in (0x0E, 0xE1):
                # The last two words of the common trap tail 0x291..0x295 (`ld XH,@(-1,Y)` and
                # `bra @0xFFFD`, J-T12 section 2). The STOCK stubs never get here: `find_stubs`
                # recognises them and the `pc in stubs` branch above short-circuits the call; a
                # CAVE-carried stub is short-circuited by cavesim (FUNC_RET at its entry). So
                # reaching one of these opcodes means control entered a tail in a way no stub
                # recognises: a stray copy of the tail, a near-copy, or a branch into 0x291
                # (V01 D1: a cave `bsr 0x291` used to be run as the pseudo-trap `trap_e245` and
                # passed every gate). Before round 3 this was a pseudo-TRAP that recorded whatever
                # was at @(0,Y) and returned, which turned each of those into a quiet success. On
                # hardware the tail jumps through the firmware's trap-handler cells with X holding
                # a link, not a trap number, so the model stops.
                raise RuntimeError("trap tail word %#04x (%s) executed at %#x outside a recognised "
                                   "trap stub: control entered the common trap tail without a "
                                   "canonical stub (a stray tail, a near-copy, or a branch to "
                                   "0x291; tools/caveguard.py attest_trap_stubs)"
                                   % (op, "ld XH,@(n,Y)" if op == 0x0E else "bra @abs", pc))
            if op == 0x9A:                     # tst @(v,X): Z from memory at X+v
                t = self.rd((self.X + v) & 0xFFFF)
                self.Z = 1 if t == 0 else 0
                self.N = 1 if t & 0x8000 else 0    # 2026-10-19 (AE section 14): N too, like 0x98/0x99/0x9B
                pc = nxt
                continue
            if op == 0x9C:                     # bsr: push return, jump
                # X IS the link register. Bose's own code proves it: the
                # library MessageLoop does `bsr +1` purely to capture the
                # return address, then `add X,@(-2,Y)`, and reads the high
                # half from 0xFFE2. The ADK calls the pair $XAP_UXH/$XAP_UXL,
                # but 0xFFE3 reads back as X and 0xFFE4 as Y -- the "U" is
                # CSR's name for the user register file, not a separate
                # register. Consequence for caves: **X does not survive a
                # bsr**, so a pointer held in X must be reloaded after every
                # call. Ours all do.
                self.X = nxt & 0xFFFF
                calls.append(nxt)
                pc = (pc + ln - 1 + v) & 0x3FFFF  # target = a + ln-1 + v (validated rule; 18-bit)
                continue
            if op == 0xE2:                     # rts: pop return (top-level -> done)
                if not calls:
                    return "rts", pc
                pc = calls.pop()
                continue
            if op in (0xF0, 0xF4, 0xF8, 0xFC, 0x20, 0x24, 0x28, 0x2C,
                      0xE0, 0xE4, 0xE8, 0xEC):
                # Branch target is relative to the LAST word of the instruction, the same
                # rule as bsr above -- NOT the branch word's own address.
                #
                # The old rule (`pc + v`) was "validated on probe3 f_c_bit and probe5
                # f_bitloop: beq/bra/bcz", but those are all ONE-WORD branches, where
                # ln-1 == 0 and the two rules coincide. For multi-word branches they
                # differ by one word, and an independent boundary census over Bose's
                # 191,224 instructions settles it:
                #
                #     2-word branches (2103):  pc+v  886 (42%)   pc+ln-1+v  2103 (100%)
                #     3-word bsr      (7473):  pc+v 5788 (78%)   pc+ln-1+v  7473 (100%)
                #
                # This mattered: the assembler shared the wrong rule, so every multi-word
                # branch it emitted was targeted one word short, and probe131/132's gate
                # bail landed on `bra +1` -> the generator's `enterl -2` instead of on
                # `leavel -8`. Emulator and assembler agreeing is not validation when they
                # share the assumption.
                tgt = (pc + ln - 1 + v) & 0x3FFFF   # 18-bit code space (cave at 0x3Exxx)
                taken = True
                sa, sb = self.lastA, self.lastB
                if op == 0xF0: taken = self.Z == 0
                elif op == 0xF4: taken = self.Z == 1
                elif op == 0xF8: taken = self.C == 0
                elif op == 0xFC: taken = self.C == 1
                elif op == 0x20: taken = (sa > sb) if sa & 0x8000 == sb & 0x8000 else (sb & 0x8000 != 0)
                elif op == 0x24: taken = (sa >= sb) if sa & 0x8000 == sb & 0x8000 else (sb & 0x8000 != 0)
                elif op == 0x28: taken = (sa <= sb) if sa & 0x8000 == sb & 0x8000 else (sa & 0x8000 != 0)
                elif op == 0x2C: taken = self.C == 1 or self.Z == 1
                elif op == 0xE4: taken = (sa < sb) if sa & 0x8000 == sb & 0x8000 else (sa & 0x8000 != 0)
                elif op == 0xE8: taken = self.N == 0      # bpl
                elif op == 0xEC: taken = self.N == 1      # bmi
                pc = tgt if taken else nxt
                continue
            # (opcode 0x0E, `ld XH,@(n,Y)`, used to have a second branch here. It was dead behind the
            # pseudo-TRAP above and used mode 2, @(n,X), where the opcode is @(n,Y); both are gone.)
            if op in (0x0B, 0x0F):             # enterl/leavel move Y; leavel RETURNS
                if op == 0x0B:
                    self.Y = (self.Y + v) & 0xFFFF
                    pc = nxt
                else:
                    self.Y = (self.Y - v) & 0xFFFF
                    if calls:
                        pc = calls.pop()
                    else:
                        return "leavel", pc
                continue
            if op in (0x98, 0x99, 0x9B):       # tst #imm / tst @abs / tst @(v,Y)
                # 0x98 tst #imm added 2026-10-19 (AE section 12): Z/N from the immediate itself.
                if op == 0x98:
                    t = v & 0xFFFF
                else:
                    t = self.rd((v & 0xFFFF) if op == 0x99 else (self.Y + v) & 0xFFFF)
                self.Z = 1 if t == 0 else 0
                self.N = 1 if t & 0x8000 else 0
                pc = nxt
                continue
            if op in (0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7):  # pair shifts on AH:AL (0xA3/0xA7: count in @(v,Y), added 2026-10-17 for fn_01623/fn_0160e; 0xA2/0xA6: count in @(v,X), added 2026-10-19, AE section 11)
                # 0xA4/0xA5 shift right. They are ARITHMETIC: the ADK
                # assembler renders `asr #6` as the single word 0x06A4 and
                # `lsr #1` as the PAIR 0x0009 0x01A4 -- so the 0x09 word is
                # what makes a right shift logical, and a bare nnA4 keeps
                # the sign. (An earlier version shifted logically always,
                # which turned the brown-noise integrator into a monotonic
                # ramp: every (int16)x>>6 came out non-negative.)
                p = self.pair()
                if op in (0xA2, 0xA3, 0xA6, 0xA7):
                    n = self.rd(self.ea(mode, v)) & 0x1F     # @(v,X) for 0xA2/0xA6, @(v,Y) for 0xA3/0xA7
                    # NOTE: the 5-bit mask is a convention; silicon behaviour for a count >= 32 is UNKNOWN (BJ section 8.1). Do not change without proof.
                elif op in (0xA1, 0xA5):
                    n = self.rd(self.ea(mode, v)) & 0x1F
                else:
                    n = v & 0x3F
                if op in (0xA0, 0xA1, 0xA2, 0xA3):
                    p = (p << n) & 0xFFFFFFFF
                elif self.unsigned_form:
                    p = p >> n
                else:
                    p = ((p - 0x100000000) if p & 0x80000000 else p) >> n
                    p &= 0xFFFFFFFF
                self.unsigned_form = False
                self.setpair(p)
                pc = nxt
                continue
            if op in (0x90, 0x91, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97):  # smult / sdiv, or umult / udiv after 0x0009
                # mul = 0x90 #imm, 0x91 @abs, 0x92 @(n,X), 0x93 @(n,Y) (docs/xap-opcodes.md, hi=9
                # family). 0x90 used to be skipped as a "byte-extend quirk" at vm.app f593/f5b1; those
                # two sites are `mul #3 ; ld X,@0xffe1`, a real x3 table-offset multiply (2026-10-19,
                # tools/README.md, docs/deep/material-2026-10-19/AE-xapemu-mul-fix.md).
                # div = 0x94 #imm, 0x95 @abs, 0x96 @(n,X), 0x97 @(n,Y) (same mode rule; 2026-10-19,
                # AE section 9). AH:AL / operand: quotient -> AL, remainder -> AH (proven at vm.app
                # 0x01186: `div @(5,Y) ; st AH,@0x511` is (x+1) mod N, and 0x0eff0 `div @(7,Y) ;
                # st AL,@(6,Y)` takes the quotient). Signed form truncates toward zero, remainder
                # takes the sign of the numerator.
                if op in (0x90, 0x94):
                    val = v & 0xFFFF
                elif op in (0x91, 0x95):
                    val = self.rd(self.ea(1, v))
                else:
                    val = self.rd(self.ea(op & 3, v))
                if op < 0x94:                              # multiply -> AH:AL
                    a, b = self.AL, val
                    if not self.unsigned_form:
                        a = a - 0x10000 if a & 0x8000 else a
                        b = b - 0x10000 if b & 0x8000 else b
                    self.setpair((a * b) & 0xFFFFFFFF)
                else:                                      # divide AH:AL by val
                    num, den = self.pair(), val
                    if not self.unsigned_form:
                        num = num - 0x100000000 if num & 0x80000000 else num
                        den = den - 0x10000 if den & 0x8000 else den
                    if den == 0:
                        raise RuntimeError("divide by zero at %#x" % pc)
                    q = abs(num) // abs(den)
                    r = abs(num) % abs(den)
                    if (num < 0) != (den < 0):
                        q = -q
                    if num < 0:
                        r = -r
                    self.AL = q & 0xFFFF       # quotient in AL, remainder in AH
                    self.AH = r & 0xFFFF       # (the compiler reads AL then AH)
                self.unsigned_form = False
                pc = nxt
                continue
            if hi == 0x7:                      # nadd reg,<ea> : reg = val - reg
                # Verified from the compiler (tools/opcodes.py): 0x70 is
                # `nadd AH,#imm` and 0x74 `nadd AL,#imm`. The project used to
                # call 0x74 `neg`, which is only the imm==0 case.
                a = self.ea(mode, v)
                val = (v & 0xFFFF) if mode == 0 else self.rd(a)
                cur = {"AH": self.AH, "AL": self.AL, "X": self.X, "Y": self.Y}[R[reg]]
                r = (val - cur) & 0xFFFF
                self.lastA, self.lastB = r, val
                self.Z = 1 if r == 0 else 0
                self.N = 1 if r & 0x8000 else 0
                # 2026-10-19 (AE section 14): C is the carry-out of val + ~cur + 1, i.e. 1 iff val >= cur
                # (no borrow). Forced for imm 0 by the 32-bit negate idiom at 0x39abf
                # (`neg AL ; xor AH,#-1 ; adc AH,#0`); polarity for imm != 0 is unproven (no site reads it).
                self.C = 1 if val >= cur else 0
                if R[reg] == "AH": self.AH = r
                elif R[reg] == "AL": self.AL = r
                elif R[reg] == "X": self.X = r
                else: self.Y = r
                pc = nxt
                continue
            if op == 0x09 and v == -2:         # brxl: indexed branch (switch)
                # `ld X,@(table,X) ; brxl` is how the compiler jumps through a
                # switch table. The table entries are offsets from the
                # instruction AFTER the brxl, so the target is nxt + X.
                pc = (nxt + self.X) & 0x3FFFF
                continue
            if op == 0x09 and v == 0:          # unsigned-form modifier
                # Not `clc`. It is a modifier word that selects the unsigned
                # variant of the instruction that follows: `asr` -> `lsr`,
                # `sdiv` -> `udiv`. Confirmed by aligning the ADK assembler's
                # mnemonics against the linked words (tools/opcodes.py).
                self.C = 0
                self.unsigned_form = True
                pc = nxt
                continue
            if hi in (0x1, 0x2, 0x3, 0x4, 0x5, 0x6, 0x8, 0xB, 0xC, 0xD):
                a = self.ea(mode, v)
                if hi == 0x1:                  # ld
                    val = (v & 0xFFFF) if mode == 0 else self.rd(a)
                    if R[reg] == "AH": self.AH = val
                    elif R[reg] == "AL": self.AL = val
                    elif R[reg] == "X": self.X = val
                    else: self.Y = val
                elif hi == 0x2:                # st
                    val = {"AH": self.AH, "AL": self.AL, "X": self.X, "Y": self.Y}[R[reg]]
                    if a is not None:
                        self.wr(a, val)
                elif hi == 0x8:                # cmp: C=1 iff cur<val (borrow), Z=1 iff equal
                    val = (v & 0xFFFF) if mode == 0 else self.rd(a)
                    cur = {"AH": self.AH, "AL": self.AL, "X": self.X, "Y": self.Y}[R[reg]]
                    self.lastA, self.lastB = cur, val
                    self.C = 1 if cur < val else 0
                    self.Z = 1 if cur == val else 0
                    self.N = 1 if (cur - val) & 0x8000 else 0
                else:                          # add/sub/or/and/xor
                    val = (v & 0xFFFF) if mode == 0 else self.rd(a)
                    cur2 = {"AH": self.AH, "AL": self.AL, "X": self.X, "Y": self.Y}[R[reg]]
                    if hi == 0x3: r = (cur2 + val) & 0xFFFF; self.C = 1 if cur2 + val > 0xFFFF else 0
                    elif hi == 0x4:                      # addc: the high half of a 32-bit add
                        t = cur2 + val + self.C
                        r = t & 0xFFFF; self.C = 1 if t > 0xFFFF else 0
                    elif hi == 0x6:                      # subc: the high half of a 32-bit subtract
                        t = cur2 - val - self.C
                        r = t & 0xFFFF; self.C = 1 if t < 0 else 0
                    elif hi == 0x5: r = (cur2 - val) & 0xFFFF; self.C = 1 if cur2 < val else 0
                    elif hi == 0xB: r = cur2 | val
                    elif hi == 0xC: r = cur2 & val
                    else: r = cur2 ^ val
                    self.lastA, self.lastB = r, val
                    self.Z = 1 if r == 0 else 0
                    self.N = 1 if r & 0x8000 else 0
                    if R[reg] == "AH": self.AH = r
                    elif R[reg] == "AL": self.AL = r
                    elif R[reg] == "X": self.X = r
                    else: self.Y = r
                pc = nxt
                continue
            if op == 0x00:
                # A word of 0x0000 is `nop`: opcode 0x00 with a ZERO operand, so
                # it is not a prefix (a prefix needs a non-zero operand byte).
                # Hardware agrees -- probe77 deleted the prompt call at 0xAE4 by
                # writing three 0x0000 words and the cave ran. Caves also use one
                # as padding when a `bsr` slot is too wide for its distance.
                pc = nxt
                continue
            raise RuntimeError(f"unmodelled opcode {op:#04x} at {pc:#x} (word {self.code[pc]:#06x})")


def load_vm_app(path):
    return xapvm.load_words(path)      # FULL file; VM slices code/const itself


if __name__ == "__main__":
    code = load_vm_app(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    "firmware", "bose", "extracted", "internal_fs", "vm.app"))
    vm = VM(code)
    # synthetic frame for the function at 0x7e1a (enterl -6: Y -= 6)
    vm.Y = 0x800
    vm.AH, vm.AL = 0x0000, 0x0010     # pretend PIO state changed, bit 4
    try:
        end = vm.run(0x7e1a, max_steps=300)
        print("ended:", end, "AH:AL =", hex(vm.pair()))
    except RuntimeError as e:
        print("stopped:", e)
    for row in vm.log[:80]:
        print(row)
