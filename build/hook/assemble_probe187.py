#!/usr/bin/env python3
"""probe187: the READ-ONLY volume census (T06c). It reads, it speaks ONE prompt id, it writes nothing. [ROUND-3 NOTE: corrections to this docstring are in the comment block at the end of the file]

## What it is for (docs/deep/firmware-study-2026-10-12/T06-volume-path.md, "Census specification")

The stock volume step ends in a 0x1002 message whose TONE word is fn_0dece(0). T06 predicts, from the
stock 3.0.3 PS defaults, that the tone word is a FIXED -2242 (-37.4 dB) at every volume step, so the
tone mix ratio (and our port-3 noise) does not follow the volume buttons, and that the DAC is held at
a fixed gain (gain type "digital"). Nothing was heard or read from the unit. This image reads the
unit's own live values once and says what it found, with one spoken id:

    @0x6d0            audio-output config pointer      (0 -> nothing to read)
    @0x72f            A2DP plugin instance (DECODER)   (0 -> DSP not loaded / not the A2DP plugin)
    @(14,@0x6d0)      gain type of the main group      0 hardware, 1 digital, 2 hybrid
    @(10,@0x72f)      volume group word                2 = all groups (the stock default)
    @(11,@0x72f)      last master dB/60 the stock stored
    @(12,@0x72f)      last tone  dB/60 the stock stored
    @0x528 & 0x1000   the "tones at a fixed volume" flag (PS USR6 word 0, bit 12)

It calls NOTHING but the prompt engine (SPEAK, the idiom of probes 99 and 172-178). No port, no
timer, no message, no trap, no store outside its own stack frame (the assembler asserts this from the
decoded words, below). Every event except the centre long press 0x4004 is replayed to the stock
(fn_189fb), exactly as probe178 does; 0x4004 is swallowed and runs the census.

## THE DECISION (the reference, T06 "Decision"; the id table below deviates from T06 ONLY in the ids)

    @0x6d0 == 0 or @0x72f == 0            -> NULL guard
    gain type 0 / 2 / other                -> HARDWARE / HYBRID / INVALID guards
    gain type 1 (digital, the prediction):
        a = 0 if tone in -2300..-2200 (the predicted fixed -2242), else 1 if tone == master, else 2
        b = tones-fixed flag (@0x528 bit 12)
        c = 0 if group == 2 else 1
        idx = a + 3b + 6c        (0..11)

## THE SPOKEN IDS (T06c note has the full table with the question each answers)

  battery 10..100 %  0x27..0x30 = idx 0..9 (the stock speaks one of them at power-on, never during a press)
  0x2A battery 40%   idx 3 = a0 b1 c0 = THE FULL PREDICTION (digital, tone fixed, group = all)
  0x2B battery 50%   idx 4 AND idx 10 (a1 b1: flag set but the tone equals the master; c not told)
  0x3D noise cancellation only   idx 11 (a2 b1 c1: the PS differs from the DFU default, group not 2)
  guards (never spoken by the stock on this speaker, promptmap.md section 6):
  0x39 heart rate detected       @0x6d0 or @0x72f is 0     (press while music is PLAYING)
  0x3A heart rate not detected   gain type 0 hardware      (the DAC follows the step: digital reading WRONG)
  0x3B adjust airbuds            gain type 2 hybrid
  0x3C adjust left airbud        gain type invalid (3 or more)
  0x31..0x34 are NEVER spoken here (stock low/full/high/medium battery prompts, never observed: hypothesis).

## THE PRESS (one flash, one press; the full script is in T06c)

Laptop connected, music PLAYING, the power-on announcement finished. Speaker volume: from the bottom,
volume-UP 3 to 5 times (not mute, not step 1, not near step 62), wait 5 s. CENTRE long press ONCE, then
listen for ONE prompt and write it down. A beep with it is the stock assistant toggle, not an outcome.
No further presses (a later centre short press may be converted to 0x4004 and re-run the census).
"""

import os, re, sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

_PROBE = re.match(r'assemble_(probe[0-9a-z]+)\.py$',
                  os.path.basename(os.path.abspath(__file__))).group(1)

CAVE = 0x3E21D
# probe172, proven on hardware: the hook is at 0x00e46 (`bsr fn_189fb`, 3-word bsr, operand bytes
# 01 7c b3 at area bytes 0x706bd/0x706bf/0x706c1); the opcode byte 0x9c and the low bytes stay.
# 0x0AE0 is NOT edited. The values are asserted below against the bsr3 encoding of CAVE from 0x00e46.
HOOK = 0x00E46
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
AREA0 = 0x6EA30
CONST_BASE = 0x7400                     # data addr of code word 236514 (0x39BE2)

SPEAK = 0xDF7F                          # the prompt engine: id in AL (probe99's idiom)
TASK_ADDR = 0xBA3C       # const_addr(CAVE+1): the TaskData lives at CAVE+1, CAVE+2, exactly as
                         #   probes 145-178 had it -- the dispatch path those probes proved
FN189FB = 0x189FB        # the call at 0x00e46: MessageSend(0xa5ce, 1, {1, event})

# ---- the id table (T06c); ONE place, used by the code and asserted by gate_probe187.py
ID_NULL, ID_HW, ID_HYB, ID_INV = 0x39, 0x3A, 0x3B, 0x3C
ID_BATT0 = 0x27                         # idx 0..9 -> 0x27..0x30
ID_IDX10 = 0x2B                         # idx 10 merges into idx 4
ID_IDX11 = 0x3D                         # idx 11
FORBIDDEN_IDS = {0x02, 0x03, 0x05, 0x07, 0x0F, 0x1A, 0x1D,     # empty stubs: silence looks like "nothing happened"
                 0x31, 0x32, 0x33, 0x34}                       # stock low/full/high/medium battery (never observed)

w = xapvm.load_words("firmware/bose/extracted/internal_fs/vm.app")
code = w[0x18:]

C0 = (0x6e974 + 0x34) % 64
def blind(cw): return 34 <= (2*cw + C0) % 64 <= 60
SCAN_LO, SCAN_HI, MIN_RUN = 0x3E200, 0x3E400, 40
_runs = []
_i = SCAN_LO
while _i < SCAN_HI:
    if code[_i] == 0:
        j = _i
        while j < SCAN_HI and code[j] == 0: j += 1
        if j - _i >= MIN_RUN: _runs.append((_i, j))
        _i = j
    else:
        _i += 1
# ---- probe162: the CONFIRMED code region (probe161s, 2026-10-08; tools/caveguard.py
# CODE_REGION). Its writable runs, minus each function's stub, become extra bands AFTER
# the const window's, so code spills into them only when the window is full. Code only:
# strings and the TaskData must stay in the window (asserted after layout).
import caveguard
REGION_STUBS = {}
_REGION_BANDS = []
for _f, (_end, _sa, _sw) in sorted(caveguard.CODE_REGION.items()):
    for _k, _v in enumerate(_sw):
        REGION_STUBS[_sa + _k] = _v
    _a = _f
    while _a < _end:
        if caveguard.region_writable(_a) and _a not in REGION_STUBS:
            _b = _a
            while _b < _end and caveguard.region_writable(_b) and _b not in REGION_STUBS:
                _b += 1
            # probe164: never start a band inside an original instruction. If the word
            # before is a prefix (low byte 0), leave this word original so that
            # instruction stays whole and the linear decode is unambiguous.
            _s = _a
            while _s < _b and (code[_s - 1] & 0xFF) == 0 and (_s - 1) not in REGION_STUBS:
                _s += 1
            if _s < _b:
                _REGION_BANDS.append((_s, _b))
            _a = _b
        else:
            _a += 1
REGION_WORDS = {a for x, y in _REGION_BANDS for a in range(x, y)}
def in_run(cw): return any(a <= cw < b for a, b in _runs) or cw in REGION_WORDS

_ORDER = []
for a, b in _runs:
    if a <= CAVE < b: _ORDER.append((CAVE, b))
for a, b in _runs:
    if a > CAVE: _ORDER.append((a, b))
for a, b in _runs:
    if b <= CAVE: _ORDER.append((a, b))
assert _ORDER and _ORDER[0][0] == CAVE
_BANDS = []
for lo, hi in _ORDER:
    _a = lo
    while _a < hi:
        if blind(_a):
            _b = _a
            while _b < hi and blind(_b): _b += 1
            _BANDS.append((_a, _b)); _a = _b
        else:
            _a += 1
_BANDS += _REGION_BANDS
_BEND = {b: k for k, (a, b) in enumerate(_BANDS)}
assert _BANDS[0][0] == CAVE, hex(_BANDS[0][0])
print('cave budget: %d runs, %d bands, %d writable words'
      % (len(_runs), len(_BANDS), sum(b - a for a, b in _BANDS)))

def next_blind(pc):
    if pc in _BEND:
        k = _BEND[pc] + 1
        assert k < len(_BANDS), ('cave exhausted: %d writable words is not enough'
                                 % sum(y - x for x, y in _BANDS))
        return _BANDS[k][0]
    for x, y in _BANDS:
        if x <= pc < y:
            return pc
    raise AssertionError('next_blind off the map at %#x' % pc)

BAND0 = [CAVE]
assert all(blind(a) and in_run(a) for a in BAND0)
# CAVE = the entry jump; CAVE+1, CAVE+2 = the handler's const TaskData; code
# proper starts at CAVE+3. Execution never falls into the TaskData because the
# entry jump skips it and every function exits by leavel.
TASK_AT = CAVE + 1
CODE_AT = CAVE + 3
assert blind(TASK_AT) and in_run(TASK_AT) and blind(CODE_AT) and in_run(CODE_AT)
assert ca.const_addr(TASK_AT) == TASK_ADDR, (hex(ca.const_addr(TASK_AT)),)


prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))
def REGION(): prog.append(("region",))   # unused: everything fits the window (asserted below)

# Opcodes used below (all attested in Bose code, docs/xap-opcodes.md; the branch forms are
# re-attested by tools/preflight.py):  tst @abs 0x99, ld X,@abs 0x19, ld AL,@abs 0x15,
# ld AL,@(n,X) 0x16, ld AL,@(n,Y) 0x17, st AL,@(n,Y) 0x27, cmp AL,#imm 0x84, cmp AL,@(n,Y) 0x87,
# add AL,#imm 0x34, and AL,#imm 0xC4, bne 0xF0, beq 0xF4, bcc 0xF8, bcs 0xFC, bra 0xE0.
# NO signed branch (blt/bge/...), NO multiply, NO shift, NO store except @(n,Y) inside the frame.
OP_TST_ABS, OP_LD_X_ABS, OP_LD_AL_ABS = 0x99, 0x19, 0x15
OP_LD_AL_XREL, OP_ADD_AL_IMM, OP_AND_AL_IMM, OP_CMP_AL_IMM = 0x16, 0x34, 0xC4, 0x84
BNE, BEQ, BCC, BCS, BRA = 0xF0, 0xF4, 0xF8, 0xFC, 0xE0

# ------------------------------------------------------------------ the TRIGGER
# probe172, proven on hardware: entered from 0x00e46 in fn_00846 (enterl -23) with AL = the event.
# 0x4004 = a CENTRE LONG PRESS while connected -> the census, event swallowed. Every other event:
# fn_189fb replayed with AL restored, the stock call (probe178's TRIG, word for word).
LBL("TRIG")
W(0xF80B)                       # enterl -8
W(0x0027)                       # st AL,@(0,Y)  the event id
W(*ca.imm_words(0x4004, 0x84))  # cmp AL,#0x4004
BR(BNE, "PASS")                 # not ours: replay
BSR("CENSUS")                   # read, speak one id
W(0xF80F)                       # leavel -8: the voice-dial event is swallowed
LBL("PASS")
W(0x0017)                       # ld AL,@(0,Y)  the event back in AL
BSR(FN189FB)                    # the stock call, replayed
W(0xF80F)                       # leavel -8

# --------------------------------------------------------------- the HANDLER
# Never dispatched: this image sends no message to its task. The TaskData at CAVE+1/CAVE+2 still
# has to point at a handler for the layout machinery (as probe174-178).
LBL("HANDLER")
W(0xF80B)                       # enterl -8
W(0xF80F)                       # leavel -8

# -------------------------------------------------------------------- CENSUS
# enterl -8: usable slots 0..5 (docs/cave-frame.md: the top two hold the return address).
#   slot 0 master, 1 group, 2 tone, 3 the id being built.   X is reloaded from RAM when needed
#   (nothing between the loads calls anything, so X survives).
LBL("CENSUS")
W(0xF80B)                       # enterl -8
W(*ca.imm_words(0x6D0, OP_TST_ABS)); BR(BEQ, "NULLID")   # tst @0x6d0: audio-output config
W(*ca.imm_words(0x72F, OP_TST_ABS)); BR(BEQ, "NULLID")   # tst @0x72f: the A2DP plugin instance
W(*ca.imm_words(0x6D0, OP_LD_X_ABS))                     # ld X,@0x6d0
W(0x0E00 | OP_LD_AL_XREL)       # ld AL,@(14,X)  gain type of the main group (fn_1f47a reads it so)
W(*ca.imm_words(1, OP_CMP_AL_IMM)); BR(BEQ, "DIG")       # 1 = digital: the prediction
W(*ca.imm_words(0, OP_CMP_AL_IMM)); BR(BEQ, "HWID")      # 0 = hardware
W(*ca.imm_words(2, OP_CMP_AL_IMM)); BR(BEQ, "HYBID")     # 2 = hybrid
W(*ca.imm_words(ID_INV, 0x14))  # ld AL,#invalid-type id ...
BR(BRA, "SAY")
LBL("HWID")
W(*ca.imm_words(ID_HW, 0x14)); BR(BRA, "SAY")
LBL("HYBID")
W(*ca.imm_words(ID_HYB, 0x14)); BR(BRA, "SAY")
LBL("NULLID")
W(*ca.imm_words(ID_NULL, 0x14)); BR(BRA, "SAY")

LBL("DIG")
W(*ca.imm_words(0x72F, OP_LD_X_ABS))                     # ld X,@0x72f
W(0x0B00 | OP_LD_AL_XREL); W(0x0027)                     # ld AL,@(11,X) ; st AL,@(0,Y)  master
W(0x0A00 | OP_LD_AL_XREL); W(0x0127)                     # ld AL,@(10,X) ; st AL,@(1,Y)  group
W(0x0C00 | OP_LD_AL_XREL); W(0x0227)                     # ld AL,@(12,X) ; st AL,@(2,Y)  tone
W(*ca.imm_words(ID_BATT0, 0x14)); W(0x0327)              # ld AL,#0x27 ; st AL,@(3,Y)    id := idx 0
# ---- a: tone in -2300..-2200 -> +0 ; tone == master -> +1 ; else +2.
# (tone + 2300) as an UNSIGNED 16-bit number is <= 100 exactly for tone -2300..-2200: no signed branch.
W(0x0217)                       # ld AL,@(2,Y)  tone
W(*ca.imm_words(2300, OP_ADD_AL_IMM))
W(*ca.imm_words(101, OP_CMP_AL_IMM)); BR(BCS, "ADONE")   # AL < 101 : the predicted fixed tone, a = 0
W(0x0217)                       # ld AL,@(2,Y)  tone again
W(0x0087)                       # cmp AL,@(0,Y) master
BR(BEQ, "AONE")
W(0x0317)                       # ld AL,@(3,Y)
W(*ca.imm_words(2, OP_ADD_AL_IMM)); W(0x0327)            # +2 ; st AL,@(3,Y)    a = 2
BR(BRA, "ADONE")
LBL("AONE")
W(0x0317)                       # ld AL,@(3,Y)
W(*ca.imm_words(1, OP_ADD_AL_IMM)); W(0x0327)            # +1 ; st AL,@(3,Y)    a = 1
LBL("ADONE")
# ---- b: the tones-fixed flag, @0x528 bit 12 -> +3
W(*ca.imm_words(0x528, OP_LD_AL_ABS))                    # ld AL,@0x528
W(*ca.imm_words(0x1000, OP_AND_AL_IMM))                  # and AL,#0x1000
W(*ca.imm_words(0, OP_CMP_AL_IMM)); BR(BEQ, "BDONE")
W(0x0317)                       # ld AL,@(3,Y)
W(*ca.imm_words(3, OP_ADD_AL_IMM)); W(0x0327)            # +3 ; st AL,@(3,Y)
LBL("BDONE")
# ---- c: group word != 2 -> +6
W(0x0117)                       # ld AL,@(1,Y)  group
W(*ca.imm_words(2, OP_CMP_AL_IMM)); BR(BEQ, "CDONE")
W(0x0317)                       # ld AL,@(3,Y)
W(*ca.imm_words(6, OP_ADD_AL_IMM)); W(0x0327)            # +6 ; st AL,@(3,Y)
LBL("CDONE")
W(0x0317)                       # ld AL,@(3,Y)  id = 0x27 + idx
# ---- idx 10 and 11 would be 0x31 and 0x32 (stock battery low/full): map them to non-battery ids
W(*ca.imm_words(0x31, OP_CMP_AL_IMM)); BR(BCS, "SAY")    # AL < 0x31 : idx 0..9, speak as is
W(*ca.imm_words(0x32, OP_CMP_AL_IMM)); BR(BEQ, "IDX11")
W(*ca.imm_words(ID_IDX10, 0x14)); BR(BRA, "SAY")         # idx 10 -> 0x2B (merged with idx 4)
LBL("IDX11")
W(*ca.imm_words(ID_IDX11, 0x14))                         # idx 11 -> 0x3D, and FALL into SAY
LBL("SAY")
BSR(SPEAK)                      # probe99's direct idiom, hardware-proven; port 3 is untouched
W(0xF80F)                       # leavel -8

# ---- layout (proven machinery, verbatim from probe137/139/140) ----
bsr_size, br_size = {}, {}
label_addr = {}
changes = []
def needs_follow(item):
    k = item[0]
    if k == "region": return False
    if k == "bsr": return True
    if k == "br": return item[1] != 0xE0
    return (item[1][-1] & 0xFF) not in (0xE2, 0x0F)   # rts, leavel
def bsr2_encodable(v):
    for aa in range(max(-128, (v >> 8) - 2), min(128, (v >> 8) + 3)):
        if aa == 0: continue
        b = v - aa * 256
        if -128 <= b <= 127: return True
    return False
def br2_encodable(v):
    for aa in range(max(-128, (v >> 8) - 2), min(128, (v >> 8) + 3)):
        if aa == 0: continue
        if -128 <= v - aa * 256 <= 127: return True
    return False
def bsr3_encodable(v):
    for aa in range(-128, 128):
        if aa == 0: continue
        for bb in range(-128, 128):
            if bb == 0: continue
            cc = v - aa*65536 - bb*256
            if -128 <= cc <= 127: return True
    return False

for iteration in range(200):
    addr = CODE_AT
    addrs = [0]*len(prog)
    extra = {}
    i = 0
    while i < len(prog):
        kind = prog[i][0]
        if kind == "label":
            addrs[i] = addr; i += 1; continue
        if kind == "region":
            # no connector: nothing falls through into the region
            assert i > 0 and not needs_follow(prog[i - 1]), 'region entry must follow a terminator'
            addrs[i] = -1
            addr = _REGION_BANDS[0][0]; i += 1; continue
        if kind == "w": sz = len(prog[i][1])
        elif kind == "bsr": sz = bsr_size.get(i, 0)
        else: sz = br_size.get(i, 1)
        band_end = addr
        while blind(band_end) and in_run(band_end): band_end += 1
        try:
            nb_probe = next_blind(band_end)
            cs = (1 if -128 <= nb_probe - addr <= 127
                  else 2 if br2_encodable(nb_probe - (addr + 1)) else 3)
        except AssertionError:
            nb_probe, cs = None, 0
        need = sz + (cs if needs_follow(prog[i]) else 0)
        if addr + need > band_end:
            assert nb_probe is not None, (
                'cave exhausted: %d writable words is not enough (at %#x, item %d of %d; '
                '%d program words still unplaced, before connectors)'
                % (sum(y - x for x, y in _BANDS), addr, i, len(prog),
                   sum(len(prog[j][1]) if prog[j][0] == "w" else
                       bsr_size.get(j, 2) if prog[j][0] == "bsr" else br_size.get(j, 1)
                       for j in range(i, len(prog)) if prog[j][0] in ("w", "bsr", "br"))))
            if addr >= band_end:
                addr = next_blind(band_end); continue
            nb = nb_probe
            assert blind(addr) and in_run(addr), (hex(addr), "connector slot not blind")
            assert addr + cs <= band_end, (
                'no room for a %d-word connector at %#x (band ends %#x)'
                % (cs, addr, band_end))
            extra[addr] = (nb, cs)
            addr = nb
            continue
        if kind == "bsr" and i not in bsr_size: bsr_size[i] = 2
        if kind == "br" and i not in br_size: br_size[i] = 1
        addrs[i] = addr
        addr += sz
        i += 1
    label_addr = {}
    for i, item in enumerate(prog):
        if item[0] != "label": continue
        j = i + 1
        while j < len(prog) and (prog[j][0] == "label" or addrs[j] < 0): j += 1
        label_addr[item[1]] = addrs[j] if j < len(prog) else addrs[-1]
    ok = True
    for i, item in enumerate(prog):
        if item[0] not in ("bsr", "br"): continue
        a = addrs[i]
        lbl = item[2] if item[0] == "br" else item[1]
        tgt = label_addr[lbl] if isinstance(lbl, str) else lbl
        if item[0] == "bsr":
            v = tgt - a
            want = 1 if -126 <= v <= 126 else 2 if bsr2_encodable(v - 1) else 3 if bsr3_encodable(v - 2) else 0
            if bsr_size.get(i, 2) != want:
                changes.append((iteration, hex(a), 'bsr', want))
                bsr_size[i] = want; ok = False
        else:
            want = (1 if -128 <= tgt - a <= 127
                    else 2 if br2_encodable(tgt - (a + 1))
                    else 3)
            if br_size.get(i, 1) != want:
                changes.append((iteration, hex(a), 'br', want))
                br_size[i] = want; ok = False
    if ok: break
else:
    for c in changes[-12:]:
        print('  change:', c)
    raise SystemExit('no converge after %d iters: br sizes %s'
                     % (iteration, {hex(addrs[i]): sz for i, sz in br_size.items()
                                    if prog[i][0] == 'br'}))

out = {}
for i, item in enumerate(prog):
    kind = item[0]
    a = addrs[i]
    if kind in ("label", "region"): continue
    if kind == "w":
        for k, val in enumerate(item[1]):
            assert a + k not in out
            out[a+k] = val
    elif kind == "bsr":
        tgt = label_addr[item[1]] if isinstance(item[1], str) else item[1]
        szb = bsr_size[i]
        assert szb in (1, 2, 3), (hex(a), item[1])
        if szb == 1:
            v = tgt - a
            out[a] = ((v & 0xFF) << 8) | 0x9C
        elif szb == 2:
            v = tgt - (a + 1)
            for aa in range(max(-128, (v >> 8) - 2), min(128, (v >> 8) + 3)):
                if aa == 0: continue
                b = v - aa * 256
                if -128 <= b <= 127:
                    out[a] = (aa & 0xFF) << 8
                    out[a+1] = ((b & 0xFF) << 8) | 0x9C
                    break
            else:
                raise AssertionError((hex(a), hex(tgt)))
        else:
            v = tgt - (a + 2)
            done = False
            for aa in range(-128, 128):
                if aa == 0: continue
                for bb in range(-128, 128):
                    if bb == 0: continue
                    cc = v - aa*65536 - bb*256
                    if -128 <= cc <= 127:
                        out[a] = (aa & 0xFF) << 8; out[a+1] = (bb & 0xFF) << 8
                        out[a+2] = ((cc & 0xFF) << 8) | 0x9C
                        done = True; break
                if done: break
            assert done
    else:
        op = item[1]
        tgt = label_addr[item[2]]
        if br_size[i] == 1:
            v = tgt - a
            out[a] = ((v & 0xFF) << 8) | op
        elif br_size[i] == 2:
            v = tgt - (a + 1)
            for aa in range(max(-128, (v >> 8) - 2), min(128, (v >> 8) + 3)):
                if aa == 0: continue
                bb = v - aa * 256
                if -128 <= bb <= 127:
                    out[a] = (aa & 0xFF) << 8
                    out[a+1] = ((bb & 0xFF) << 8) | op
                    break
            else:
                raise AssertionError(('br2', hex(a), hex(tgt)))
        else:
            v = tgt - (a + 2)
            done = False
            for aa in range(-128, 128):
                if aa == 0: continue
                for bb in range(-128, 128):
                    if bb == 0: continue
                    cc = v - aa*65536 - bb*256
                    if -128 <= cc <= 127:
                        out[a] = (aa & 0xFF) << 8; out[a+1] = (bb & 0xFF) << 8
                        out[a+2] = ((cc & 0xFF) << 8) | op
                        done = True; break
                if done: break
            assert done, ('br3', hex(a), hex(tgt))
            raise SystemExit('REFUSED: a 3-word branch at %#x -> %s %#x -- Bose never emits it' % (a, item[2], tgt))
for cslot, (nb, cs) in extra.items():
    v = nb - cslot
    if cs == 1:
        assert -128 <= v <= 127, (hex(cslot), hex(nb), v)
        out[cslot] = ((v & 0xFF) << 8) | 0xE0
    elif cs == 3:
        raise SystemExit('REFUSED: a 3-word bra connector at %#x -- Bose never emits it' % cslot)
    elif False:
        assert cslot + 1 not in out and cslot + 2 not in out, hex(cslot)
        v = nb - (cslot + 2)
        done = False
        for aa in range(-128, 128):
            if aa == 0: continue
            for bb in range(-128, 128):
                if bb == 0: continue
                cc = v - aa*65536 - bb*256
                if -128 <= cc <= 127:
                    out[cslot] = (aa & 0xFF) << 8; out[cslot+1] = (bb & 0xFF) << 8
                    out[cslot+2] = ((cc & 0xFF) << 8) | 0xE0
                    done = True; break
            if done: break
        assert done, ('connector3', hex(cslot), hex(nb))
    else:
        assert cslot + 1 not in out, hex(cslot + 1)
        v = nb - (cslot + 1)             # probe165: a 2-word branch is relative to its
                                         #   SECOND word, as br2_encodable() sized it
        for aa in range(max(-128, (v >> 8) - 2), min(128, (v >> 8) + 3)):
            if aa == 0: continue
            bb = v - aa * 256
            if -128 <= bb <= 127:
                out[cslot] = (aa & 0xFF) << 8
                out[cslot + 1] = ((bb & 0xFF) << 8) | 0xE0
                break
        else:
            raise AssertionError(('connector', hex(cslot), hex(nb), v))

# ---- probe172: the redirect bytes must be the bsr3 from HOOK to CAVE (relative to the
# bsr's LAST word, as every 3-word bsr above is encoded)
_v = CAVE - (HOOK + 2)
_enc = None
for _aa in range(-128, 128):
    if _aa == 0: continue
    for _bb in range(-128, 128):
        if _bb == 0: continue
        _cc = _v - _aa * 65536 - _bb * 256
        if -128 <= _cc <= 127 and _cc != 0:
            _enc = (_aa & 0xFF, _bb & 0xFF, _cc & 0xFF); break
    if _enc: break
assert _enc, hex(_v)
_want = [("0x%x" % (AREA0 + 2 * (HOOK + k) + 1), "0x%02x" % _enc[k]) for k in range(3)]
assert REDIRECT_EDITS == _want, (REDIRECT_EDITS, _want)
print("hook: 0x%05x bsr -> CAVE 0x%05x, operand bytes %02x %02x %02x at %s"
      % (HOOK, CAVE, _enc[0], _enc[1], _enc[2], [a for a, _ in REDIRECT_EDITS]))
entry_v = CODE_AT - CAVE
assert -128 <= entry_v <= 127
assert CAVE not in out, 'the entry jump word is already occupied'
out[CAVE] = ((entry_v & 0xFF) << 8) | 0xE0
HANDLER_AT = label_addr["HANDLER"]
assert TASK_AT not in out and TASK_AT + 1 not in out
for _k, _v in enumerate(ca.taskdata_words(HANDLER_AT)):
    out[TASK_AT + _k] = _v
print("handler a=%#x, TaskData a=%#x -> data %#06x = %s"
      % (HANDLER_AT, TASK_AT, TASK_ADDR,
         ' '.join('%04x' % x for x in ca.taskdata_words(HANDLER_AT))))

# probe172: the stubs ride along ONLY when cave code is in the region; this image puts nothing
# there (the cave fits the const window), so the seven dead functions stay byte-for-byte stock.
assert not any(caveguard.region_fn(_a) is not None for _a in out), 'cave code spilled into the code region'
assert caveguard.SAFE_WINDOW[0] <= TASK_AT < caveguard.SAFE_WINDOW[1]
_nreg = 0
print('region: %d words used, const window: %d words' % (_nreg, len(out)))
lo, hi = min(out), max(out)
print(f"cave spans {lo:#x}..{hi:#x}, {len(out)} words (iters {iteration+1})")
assert not [a for a in out if not blind(a) or not (in_run(a) or a in REGION_STUBS)]
patched = list(code)
for cw, val in out.items(): patched[cw] = val & 0xFFFF
intended, seen, dstarts = {}, {}, set()
for cslot, (nb, cs) in extra.items():
    intended[cslot] = (nb, 'connector')
for i, item in enumerate(prog):
    if item[0] in ("bsr", "br"):
        a = addrs[i]
        lbl = item[2] if item[0] == "br" else item[1]
        intended[a] = (label_addr[lbl] if isinstance(lbl, str) else lbl, item[0])
for a, op, v, ln in xapvm.decode(patched, fold_zero=False):
    dstarts.add(a)
    if lo <= a <= hi:
        if op == 0x9C: seen[a] = (a + ln - 1 + v) & 0x3FFFF

        elif op in (0x20, 0x24, 0x28, 0x2C, 0xE0, 0xE4, 0xE8, 0xEC,
                    0xF0, 0xF4, 0xF8, 0xFC): seen[a] = (a + ln - 1 + v) & 0x3FFFF
for a, (tgt, kind) in intended.items():
    assert seen.get(a) == (tgt & 0x3FFFF), (hex(a), kind, hex(tgt), seen.get(a))
assert seen.get(CAVE) == CODE_AT, (hex(CAVE), hex(CODE_AT), seen.get(CAVE))
for i, item in enumerate(prog):
    if item[0] not in ("label", "region"):
        assert addrs[i] in dstarts, (hex(addrs[i]), "boundary")
print("decode-verify: all branches OK, boundaries OK")

# ---- READ-ONLY PROOF, from the decoded words (fold_zero=False, as a cave must be read) ------------
# The census must write nothing but its own stack frame, call nothing but SPEAK (and the stock
# fn_189fb replay), and read nothing but the three data words and the four fields it is meant to
# read. Every instruction that STARTS at a cave address (except the two TaskData words, which are
# data) is checked against a whitelist. A failure here stops the build.
_OK_OPS = {0x00, 0x0B, 0x0F, 0x14, 0x15, 0x16, 0x17, 0x19, 0x27, 0x34, 0x84, 0x87, 0x99, 0xC4,
           0x9C, 0xE0, 0xF0, 0xF4, 0xF8, 0xFC}
_ABS_OK = {0x528, 0x6D0, 0x72F}
_XREL_OK = {10, 11, 12, 14}
_YSLOT_MAX = 5                       # enterl -8: slots 0..5 usable (docs/cave-frame.md)
_stores, _abs, _xrel, _calls, _ninsn = [], set(), set(), set(), 0
_skip = {TASK_AT, TASK_AT + 1}
for _a, _op, _v, _ln in xapvm.decode(patched, fold_zero=False):
    if _a not in out or _a in _skip:
        continue
    _ninsn += 1
    assert _op in _OK_OPS, 'READ-ONLY PROOF: opcode %#04x at %#x is not on the whitelist' % (_op, _a)
    _hi, _mode = _op >> 4, _op & 3
    if _hi == 2 and _mode != 0:                          # a store
        assert _op == 0x27 and 0 <= _v <= _YSLOT_MAX, (
            'READ-ONLY PROOF: store %#04x @%d at %#x is not st AL,@(n<=5,Y)' % (_op, _v, _a))
        _stores.append((_a, _v))
    if _op in (0x15, 0x19, 0x99):                        # absolute reads
        _abs.add(_v & 0xFFFF)
    if _op == 0x16:
        _xrel.add(_v)
    if _op in (0x17, 0x87):
        assert 0 <= _v <= _YSLOT_MAX, ('frame slot out of range at %#x' % _a)
    if _op == 0x9C:
        _t = (_a + _ln - 1 + _v) & 0x3FFFF
        if not (lo <= _t <= hi):
            _calls.add(_t)
assert _abs == _ABS_OK, ('absolute reads %s != %s' % (sorted(map(hex, _abs)), sorted(map(hex, _ABS_OK))))
assert _xrel == _XREL_OK, ('X-relative reads %s != %s' % (sorted(_xrel), sorted(_XREL_OK)))
assert _calls == {SPEAK, FN189FB}, ('external calls %s' % sorted(map(hex, _calls)))
print('READ-ONLY PROOF: %d instructions, all on the whitelist; %d stores, every one st AL,@(n<=5,Y) '
      '(own frame); absolute reads %s; X-relative field reads %s; external calls %s'
      % (_ninsn, len(_stores), [hex(x) for x in sorted(_abs)], sorted(_xrel),
         [hex(x) for x in sorted(_calls)]))
# ---- the id table: nothing forbidden may be reachable as a literal id
_ids = set()
for _a, _op, _v, _ln in xapvm.decode(patched, fold_zero=False):
    if _a in out and _a not in _skip and _op == 0x14:
        _ids.add(_v & 0xFFFF)
assert not (_ids & FORBIDDEN_IDS), 'a forbidden prompt id is loaded as a literal: %s' % sorted(map(hex, _ids & FORBIDDEN_IDS))
print('literal ld AL,#imm values in the cave: %s' % [hex(x) for x in sorted(_ids)])

json.dump({hex(a): v for a, v in out.items()}, open(f"build/hook/{_PROBE}_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
# probe154 carries NO staged payload. probe141's 33,040 blind-window edits in
# data_us are inherited from this file's ancestor and are deliberately REMOVED:
# they are not wanted here, that scale of write at boot time is what caused the
# 2026-10-06 device-harm event, and this probe READS the filesystem rather than
# writing it. Only the cave words and the 11 redirect bytes are edited.
cmd = [sys.executable, "tools/fsedit.py", "--out", f"build/hook/{_PROBE}_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open(f"build/hook/{_PROBE}_cmd.txt", "w").write(" ".join(cmd) + "\n")

if "--build" in sys.argv:
    import subprocess
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes: {len(out)} cave words + "
          f"{len(REDIRECT_EDITS)} redirect bytes, NO staged payload) "
          f"-> {_PROBE}_cmd.txt")


# ROUND-3 NOTE (2026-10-12, curator; comments only - the words and DFU hashes are unchanged).
# R04 and V04 correct the INTERPRETATION text of the docstring above, not the words: (1) the press reads the VM-side gain type only and does not
# settle the DAC question (A hardware/hybrid versus P host-side versus U undecoded stage stay open; add two free owner readings: do the speaker
# buttons change the MUSIC loudness at all, and does the host slider move); (2) a 'digital' result means the buttons move nothing audible and is NOT
# 'DAC not the knob'; (3) DECODER+10 (the group word) is never written by fn_31815, so 0x2A (the full prediction) is never spoken; ids 0x2D, 0x2E,
# 0x2F, 0x30, 0x3D are not expected on a stock unit; (4) 0x3A/0x3B: hardware or hybrid means music and noise follow the buttons and a cave 0x1002 is
# a DAC command. The press script step 2 contradicts itself (use volume DOWN about 6 presses, never to the bottom) and needs the condition
# 'USB unplugged after the readback'. Register: docs/deep/round3-2026-10-12/README.md (R3-C043, R3-C049, R3-C110).
