#!/usr/bin/env python3
"""probe197: step R2 of route M1 (docs/deep/material-2026-10-13/M1-graw.md section 6.2, row R2): a TINY p2 WRITE of a
pattern the cave COMPUTES, then a READ-BACK through the 0xD3 raw source with a FULL SourceDrop walk, byte by byte.

(Built offline on 2026-10-14. The owner authorised building and flashing R2 following the documented procedure; the
parent session flashes with tools/flash_probe.py. Base: probe196's proven engine (hook 0x00e46, TaskData, MessageSendLater
ticks, SPEAK, the 0xD3 synthesised stub, MessageCancelFirst as STOP) plus probe140's write idiom and probe188's guard and
consume lever. Note, gates, press page: docs/deep/material-2026-10-13/R2-probe197.md. NO independent review yet.)

## WHAT IT DOES (ONE press, TWO ticks; this is the first p2 ERASE and WRITE since probe140)
  PRESS (centre LONG, event 0x4004): MessageCancelFirst(task, 0x12 and 0x13): any TRUE = a run is pending = STOP (silent).
         Else arm tick 0x12 in PRESS_DELAY. The event is swallowed AND CONSUMED (the probe188 lever, six words: the caller's
         indicate flag := 0, bit 15 of its flag word set). The lever runs at the press, BEFORE any flash operation.
  TICK 0x12 (TW):  sinkState guard ({3, 13}; else 0x3C and the chain ends) -> t0 = VmGetClock -> sink =
         StreamPartitionOverwriteSink(1, 2) (THE ERASE of all of p2, VM parked until done) -> WLOOP: 100 periods of
         SinkMap, SinkClaim(28), 28 computed bytes, SinkFlush(28) -> t1 = VmGetClock -> PartitionSetMessageDigest(SKIP)
         -> SinkClose (the header commits here) -> ONE spoken id (below), then arms tick 0x13 STAGE_MS later.
  TICK 0x13 (TV):  r = PartitionGetRawSerialSource(1, 2) through the proven 0xD3 stub; then a full walk: SourceSize,
         SourceMap, compare every element with the computed pattern, SourceDrop(size), until 2800 bytes were checked.
         The source closes itself when it is exhausted; every other exit calls SourceClose. ONE spoken id.

## THE PATTERN: byte k (k = 0 .. 2799) is 1 + (k mod 224). 224 = 8 x 28, so the ramp wraps exactly at a period edge; values
## 1 .. 224 (never 0, never 0xFF = erased flash); a byte misplaced by any distance that is not a multiple of 224 is visible
## (a 128-octet ring shift, a 126/127 prime shift, a 28-byte period shift, an off-by-one).

## SPOKEN IDS (docs/request-id-catalog.md). Sets are DISJOINT per tick. 0x27 keeps its probe196 meaning (0xD3 handle 0).
##   guard refused   0x3C "adjust left airbud"      sinkState not 3/13 at the tick; nothing written, chain ends
##   TW open refused 0x3A "heart rate not detected" StreamPartitionOverwriteSink returned 0; nothing written, chain ends
##   TW write failed 0x19 "call from"               a SinkMap/SinkClaim/SinkFlush failed in the loop, or the digest call
##                                                  was FALSE; the sink was still closed (header = what was flushed)
##   TW written, erase+write time <1 s  0x26 "ended"; 1 to 5 s 0x3E "bluetooth off"; over 5 s 0x11 "bluetooth device
##                                                  list cleared - ready to connect another device"
##   TV handle 0     0x27 "battery 10%"             0xD3 refused
##   TV verified     0x33 "battery high"            all 2800 bytes equal the pattern
##   TV mismatch     0x30 "battery 100%"            first wrong byte at position < 126 (inside the prime)
##                   0x3F (stereo-mode sentence)    first wrong byte at position >= 126 (a refill / the ring-end wrap)
##                   0x18 "to select a different language press a volume button"  the wrong element is wider than 0xFF
##   TV short        0x36 "select a bose speaker..." the source ended (SourceSize 0 or SourceMap 0) before 2800 bytes
"""

import os, re, sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

_PROBE = re.match(r'assemble_(probe[0-9a-z]+)\.py$',
                  os.path.basename(os.path.abspath(__file__))).group(1)

# Declared for tools/caveguard.attest_trap_stubs (it parses these two module-level literals with ast).
SYNTH_TRAPS = [0xD3]       # PartitionGetRawSerialSource: no stub in vm.app (proven to dispatch by probe196)
SYNTH_CONTROLS = []        # no control stub in R2 (probe196 proved 0xCE and 0xD3)

CAVE = 0x3E21D
# probe172: the hook moves to 0x00e46 (`bsr fn_189fb`, 3-word bsr, operand bytes 01 7c b3
# at area bytes 0x706bd/0x706bf/0x706c1); the opcode byte 0x9c and the low bytes stay.
HOOK = 0x00E46
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
AREA0 = 0x6EA30
CONST_BASE = 0x7400                     # data addr of code word 236514 (0x39BE2)

BACK = 0xE06D
SPEAK = 0xDF7F
OVERSINK = ca.STUB['StreamPartitionOverwriteSink']
SINKMAP = ca.STUB['SinkMap']
SINKCLAIM = ca.STUB['SinkClaim']
SINKFLUSH = ca.STUB['SinkFlush']
SETDIGEST = ca.STUB['PartitionSetMessageDigest']
SINKCLOSE = ca.STUB['SinkClose']
VMCLOCK = ca.STUB['VmGetClock']
SOURCESIZE = ca.STUB['SourceSize']
SOURCEMAP = ca.STUB['SourceMap']
SOURCEDROP = ca.STUB['SourceDrop']
SOURCECLOSE = ca.STUB['SourceClose']
MSGLATER = ca.STUB['MessageSendLater']
CANCELFIRST = ca.STUB['MessageCancelFirst']
TASK_ADDR = 0xBA3C       # const_addr(CAVE+1): the TaskData lives at CAVE+1, CAVE+2, exactly as probes 145-196

STAGE_TW, STAGE_TV = 0x12, 0x13
PRESS_DELAY = 2000       # press -> TW (probe196)
STAGE_MS = 10000         # TW -> TV: a long prompt (up to ~7 s) plus the A2DP reload must be over (V05 H1)
PERIODS = 100            # 100 x 28 = 2800 bytes
PERIOD_BYTES = 28
TOTAL_BYTES = PERIODS * PERIOD_BYTES
WRAP = 225               # the ramp value after 224 is 225 -> wraps to 1
EARLY_R = TOTAL_BYTES - 126          # R (bytes remaining) above this = position < 126
SINKSTATE = 0x59E        # sinkState, a plain RAM word (probe131-133, 142-144 read it; F194: 3 Connected, 13 A2dpStreaming)

# ---- spoken ids
ID_GUARD, ID_OPENFAIL, ID_WFAIL = 0x3C, 0x3A, 0x19
ID_FAST, ID_MID, ID_SLOW = 0x26, 0x3E, 0x11   # V07 D3: 0x26 "ended" and 0x3E "bluetooth off" were HEARD on this unit (probes 190-194, 177); 0x11 has not been
ID_H0, ID_VERIFIED, ID_MIS_EARLY, ID_MIS_LATE, ID_WIDE, ID_SHORT = 0x27, 0x33, 0x30, 0x3F, 0x18, 0x36
FAST_MS, MID_MS = 1000, 5000

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

FN189FB = 0x189FB                       # the call at 0x00e46: MessageSend(0xa5ce, 1, {1, event})
prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))
def REGION(): prog.append(("region",))

# ---- one-word forms used below (opcode = hi<<4 | reg<<2 | mode; reg 0 AH 1 AL 2 X 3 Y; mode 0 #, 1 @abs, 2 @(n,X), 3 @(n,Y))
def LD_AL_Y(n): return (n << 8) | 0x17     # ld AL,@(n,Y)
def ST_AL_Y(n): return (n << 8) | 0x27     # st AL,@(n,Y)
def LD_AH_Y(n): return (n << 8) | 0x13     # ld AH,@(n,Y)
def ST_AH_Y(n): return (n << 8) | 0x23     # st AH,@(n,Y)
def LD_AL_X(n): return (n << 8) | 0x16     # ld AL,@(n,X)
def OR_AL_X(n): return (n << 8) | 0xB6     # or AL,@(n,X)   (Bose: 63 uses)
def LDI_AL(v): return ca.imm_words(v, 0x14)    # ld AL,#v
def CMPI_AL(v): return ca.imm_words(v, 0x84)   # cmp AL,#v
def CMPI_AH(v): return ca.imm_words(v, 0x80)   # cmp AH,#v
CMP0 = 0x0084                              # cmp AL,#0
BEQ, BNE, BCS, BCC, BRA = 0xF4, 0xF0, 0xFC, 0xF8, 0xE0

# ------------------------------------------------------------------ the TRIGGER
# probe172, proven on hardware: entered from 0x00e46 in fn_00846 (enterl -23) with AL = the event. 0x4004 = a CENTRE LONG
# PRESS -> ARM, event swallowed. Every other event: fn_189fb replayed with AL restored, the stock call.
# THE CONSUME LEVER (probe188/189, R05 5.3; PLAN-v2 PD-11, F301): after ARM the swallowed event is also CONSUMED -- the caller's
# indicate flag (13,Y) := 0 and bit 15 of its flag word (14,Y) set (cave slots 21 and 22, fn_00846 being `enterl -23` and the
# cave `enterl -8`), so fn_01749 skips its whole switch: no assistant request, no stock beep, no short-press conversion, no
# stored 0x4004 replay. Six words, a stock shape (0x00e25-0x00e27). NEVER RUN ON HARDWARE (the first cave store into a caller
# frame). It runs at the PRESS, 2 s BEFORE the first flash operation: a failure of the lever cannot touch p2.
LBL("TRIG")
W(0xF80B)                       # enterl -8
W(0x0027)                       # st AL,@(0,Y)  the event id
W(*ca.imm_words(0x4004, 0x84))  # cmp AL,#0x4004
BR(BNE, "PASS")                 # bne -> not ours: replay
BSR("ARM")                      # arm the write tick, or stop the pending one
W(0x0014)                       # ld AL,#0
W((21 << 8) | 0x27)             # st AL,@(21,Y)  caller (13,Y): the indicate flag := 0
W((22 << 8) | 0x17)             # ld AL,@(22,Y)  caller (14,Y): its flag word
W(*ca.imm_words(0x8000, 0xB4))  # or AL,#0x8000  bit 15 = "consumed"
W((22 << 8) | 0x27)             # st AL,@(22,Y)
W(0xF80F)                       # leavel -8: the voice-dial event is swallowed
LBL("PASS")
W(0x0017)                       # ld AL,@(0,Y)  the event back in AL
BSR(FN189FB)                    # the stock call, replayed (0x00e49 reloads AL after it)
W(0xF80F)                       # leavel -8

# ---- the SYNTHESISED stub for trap 0xD3 (probe196 words, proven to dispatch on the speaker): ONE item, ends in 0xE1
LBL("STUB_D3")
W(*ca.synth_stub_words(0xD3))

# --------------------------------------------------------------- the HANDLER (probe196's, two stages)
# AL = task, AH = the MessageId = the stage (0x12 write, 0x13 verify). Slots: 3 = next stage (0 = none), 4 = stage id / delay,
# 5 = the id to speak.
LBL("HANDLER")
W(0xF80B)                       # enterl -8
W(ST_AH_Y(4))                   # st AH,@(4,Y)  the stage id
W(*CMPI_AH(STAGE_TW)); BR(BEQ, "DO_TW")
W(*CMPI_AH(STAGE_TV)); BR(BEQ, "DO_TV")
W(0xF80F)                       # an id that is not ours: nothing
LBL("DO_TW")
BSR("TW")                       # AL = the id to speak, AH = the next stage (0 = the chain ends)
W(ST_AL_Y(5))
W(ST_AH_Y(3))
BR(BRA, "FIN")
LBL("DO_TV")
W(0x0014); W(ST_AL_Y(3))        # next = 0: the chain ends after the verify
BSR("TV")                       # AL = the id to speak
W(ST_AL_Y(5))
LBL("FIN")                      # speak slot 5, then arm slot 3 (if any) STAGE_MS later
W(LD_AL_Y(5))
BSR(SPEAK)                      # probe99's direct idiom, hardware-proven; no transform of ours exists in this image
W(LD_AL_Y(3)); W(CMP0); BR(BEQ, "FEND")
W(*LDI_AL(STAGE_MS)); W(ST_AL_Y(4))
BR(BRA, "SENDLATER")
LBL("FEND")
W(0xF80F)                       # leavel -8

# ---------------------------------------------------------------------- ARM (the press)
# MessageCancelFirst(task, 0x12) and (task, 0x13): TRUE = a tick is pending = a run is under way: this press is a STOP, nothing
# else is touched (silent). Else arm TW. (probe195's STOP, once per stage id.) NO guard here: the guard is read in TW, at the
# moment of the write (a press-time reading would be stale 2 s later).
LBL("ARM")
W(0xF80B)                       # enterl -8
ca.call2(W, BSR, CANCELFIRST, al=('imm', TASK_ADDR), ah=('imm', STAGE_TW))
W(CMP0); BR(BNE, "STOP")
ca.call2(W, BSR, CANCELFIRST, al=('imm', TASK_ADDR), ah=('imm', STAGE_TV))
W(CMP0); BR(BNE, "STOP")
W(*LDI_AL(STAGE_TW)); W(ST_AL_Y(3))      # message id = TW
W(*LDI_AL(PRESS_DELAY)); W(ST_AL_Y(4))   # delay
BR(BRA, "SENDLATER")
LBL("STOP")
W(0xF80F)                       # leavel -8

# ---- SENDLATER: MessageSendLater(cave task, slot 3, 0, slot 4 ms) -- probe196's, verbatim.
LBL("SENDLATER")
W(0x0014); W(0x0027)            # message = 0          slot0
W(0x0127)                       # (AL still 0) delay high = 0   slot1
W(LD_AL_Y(4))                   # the delay
W(0x0227)                       # st AL,@(2,Y)  delay low
W(LD_AH_Y(3))                   # ld AH,@(3,Y)  the MessageId (the next stage)
W(*ca.imm_words(TASK_ADDR, 0x14))   # ld AL,#0xBA3C  the cave's TaskData
BSR(MSGLATER)
W(0xF80F)                       # leavel -8: the next tick is set

# ---------------------------------------------------------------------- TW: guard, erase, write, close
# Frame slots: 2 sink; 3 t0 hi, then (after t1) the success id; 4 t0 lo, then the digest result; 5 the loop result.
# Returns AL = the id to speak, AH = the next stage (STAGE_TV, or 0 when nothing was written and the chain ends).
LBL("TW")
W(0xF80B)                       # enterl -8
W(*ca.imm_words(SINKSTATE, 0x15))   # ld AL,@0x59e  (the form probes 131-133 and 142-144 ran)
W(*CMPI_AL(13)); BR(BEQ, "TW_GOK")
W(*CMPI_AL(3)); BR(BNE, "TW_REFUSE")
LBL("TW_GOK")
BSR(VMCLOCK)                    # t0: AH:AL = the 32-bit ms clock (stock callers store AH, AL)
W(ST_AH_Y(3)); W(ST_AL_Y(4))
ca.call2(W, BSR, OVERSINK, al=('imm', 1), ah=('imm', 2))     # *** THE ERASE of all of p2 *** (the VM parks until done)
W(ST_AL_Y(2))                   # sink
W(CMP0); BR(BEQ, "TW_OPENFAIL")
W(LD_AL_Y(2))
BSR("WLOOP")                    # AL = 0 or the failing step
W(ST_AL_Y(5))
BSR(VMCLOCK)                    # t1 (AH:AL)
W(0x0383)                       # cmp AH,@(3,Y)   high words equal? (else >= 65 s or a rollover: the slow id)
BR(BNE, "TW_SLOW")
W(0x0457)                       # sub AL,@(4,Y)   elapsed ms (16 bits)
W(*CMPI_AL(FAST_MS)); BR(BCS, "TW_FAST")        # AL < 1000 (unsigned)
W(*CMPI_AL(MID_MS)); BR(BCS, "TW_MID")          # AL < 5000
LBL("TW_SLOW")
W(*LDI_AL(ID_SLOW)); BR(BRA, "TW_STASH")
LBL("TW_MID")
W(*LDI_AL(ID_MID)); BR(BRA, "TW_STASH")
LBL("TW_FAST")
W(*LDI_AL(ID_FAST))
LBL("TW_STASH")
W(ST_AL_Y(3))                   # the success id
# partition digest SKIP (md_type 3, data NULL, len 0), then the close: the header commits here. ALWAYS, even after a failed
# loop: an open sink would make the 0xD3 builder refuse (a live partition sink) and the next press reopen it.
ca.calln(W, BSR, SETDIGEST, al=('slot', 2), ah=('imm', 3), stack=[('imm', 0), ('imm', 0)], stage='AL')
W(ST_AL_Y(4))                   # the digest result
ca.call1(W, BSR, SINKCLOSE, al=('slot', 2))
W(LD_AL_Y(5)); W(CMP0); BR(BNE, "TW_FAIL")      # the loop failed
W(LD_AL_Y(4)); W(CMP0); BR(BEQ, "TW_FAIL")      # the digest call returned FALSE
W(*ca.imm_words(STAGE_TV, 0x10))                # ld AH,#STAGE_TV
W(LD_AL_Y(3)); W(0xF80F)                        # AL = the success id; leavel -8
LBL("TW_FAIL")
W(*ca.imm_words(STAGE_TV, 0x10)); W(*LDI_AL(ID_WFAIL)); W(0xF80F)
LBL("TW_OPENFAIL")
W(0x0010); W(*LDI_AL(ID_OPENFAIL)); W(0xF80F)
LBL("TW_REFUSE")
W(0x0010); W(*LDI_AL(ID_GUARD)); W(0xF80F)

# ---------------------------------------------------------------------- WLOOP: 100 periods of computed bytes
# AL = the sink. Returns AL = 0, or 1 (SinkMap returned 0), 2 (SinkClaim failed), 3 (SinkFlush returned 0).
# Slots: 2 sink; 3 periods left; 4 E = the next byte value (1 .. 224); 5 the mapped pointer (then free).
# One period = probe140's idiom, repeated: SinkMap(sink) -> map; SinkClaim(sink, 28) -> offset (0xFFFF = failure);
# X = map + offset; 28 stores `st AL,@(0,X)` with X stepped; SinkFlush(sink, 28). Units: F207 (well-supported): the sink counts
# BYTES and a map element holds one byte, so 28 stores for a 28-byte claim. The loop is bounded: 100 iterations.
LBL("WLOOP")
W(0xF80B)                       # enterl -8
W(ST_AL_Y(2))
W(*LDI_AL(PERIODS)); W(ST_AL_Y(3))
W(0x0114); W(ST_AL_Y(4))        # E := 1
LBL("WL_TOP")
ca.call1(W, BSR, SINKMAP, al=('slot', 2))
W(ST_AL_Y(5))
W(CMP0); BR(BEQ, "WL_FMAP")
ca.call2(W, BSR, SINKCLAIM, al=('slot', 2), ah=('imm', PERIOD_BYTES))
W(0xFF84); BR(BEQ, "WL_FCLAIM")  # cmp AL,#0xffff (probe140's guard)
W(*CMPI_AL(21)); BR(BCC, "WL_FCLAIM")   # V07 D2: a 28-byte claim in a 48-octet window starts at 20 at the latest: AL >= 21 = refuse
W(0x0537)                       # add AL,@(5,Y)   offset + map
W(ST_AL_Y(5))
W(0x051B)                       # ld X,@(5,Y)
W(LD_AL_Y(4))                   # AL = E
W(*ca.imm_words(PERIOD_BYTES, 0x10))    # ld AH,#28   the inner counter
LBL("WL_BYTE")
W(0x0026)                       # st AL,@(0,X)
W(0x0134)                       # add AL,#1
W(0x0138)                       # add X,#1
W(0xFF30)                       # add AH,#-1
W(0x0080); BR(BNE, "WL_BYTE")   # cmp AH,#0 ; bne
W(*CMPI_AL(WRAP)); BR(BNE, "WL_NOWRAP")
W(0x0114)                       # ld AL,#1
LBL("WL_NOWRAP")
W(ST_AL_Y(4))
ca.call2(W, BSR, SINKFLUSH, al=('slot', 2), ah=('imm', PERIOD_BYTES))
W(CMP0); BR(BEQ, "WL_FFLUSH")
W(LD_AL_Y(3)); W(0xFF34); W(ST_AL_Y(3))
W(CMP0); BR(BNE, "WL_TOP")
W(0x0014); W(0xF80F)            # ld AL,#0 ; leavel -8: all periods flushed
LBL("WL_FMAP")
W(0x0114); W(0xF80F)
LBL("WL_FCLAIM")
W(0x0214); W(0xF80F)
LBL("WL_FFLUSH")
W(0x0314); W(0xF80F)

# ---------------------------------------------------------------------- TV: read back, full SourceDrop walk, compare every byte
# Slots: 2 source; 3 n (elements left in this window); 4 E = the expected byte; 5 R = bytes still to check. Slot 1 is used
# ONLY between two traps (the map pointer, then R at the window start), never across a trap. Returns AL = the id to speak.
LBL("TV")
W(0xF80B)                       # enterl -8
ca.call2(W, BSR, "STUB_D3", al=('imm', 1), ah=('imm', 2))
W(ST_AL_Y(2))
W(CMP0); BR(BEQ, "TV_H0")
W(*LDI_AL(TOTAL_BYTES)); W(ST_AL_Y(5))
W(0x0114); W(ST_AL_Y(4))        # E := 1
LBL("TV_WIN")
ca.call1(W, BSR, SOURCESIZE, al=('slot', 2))
W(CMP0); BR(BEQ, "TV_SHORT")
W(ST_AL_Y(3))                   # n
W(0x0587); BR(0x2C, "TV_NOCLAMP")   # cmp AL,@(5,Y) ; bcz (n <= R)
W(LD_AL_Y(5)); W(ST_AL_Y(3))    # n := R (never look past 2800 bytes)
LBL("TV_NOCLAMP")
ca.call1(W, BSR, SOURCEMAP, al=('slot', 2))
W(CMP0); BR(BEQ, "TV_MAP0")
W(0x0127)                       # st AL,@(1,Y)   the map pointer (no trap until it is in X)
W(0x011B)                       # ld X,@(1,Y)
W(LD_AL_Y(5)); W(0x0127)        # slot 1 := R at the window start
LBL("TV_CMP")
W(0x0016)                       # ld AL,@(0,X)   the element
W(0x0487); BR(BNE, "TV_MIS")    # cmp AL,@(4,Y) ; bne
W(LD_AL_Y(4)); W(0x0134)        # E + 1
W(*CMPI_AL(WRAP)); BR(BNE, "TV_E")
W(0x0114)                       # ld AL,#1
LBL("TV_E")
W(ST_AL_Y(4))
W(0x0138)                       # add X,#1
W(LD_AL_Y(5)); W(0xFF34); W(ST_AL_Y(5))      # R -= 1
W(LD_AL_Y(3)); W(0xFF34); W(ST_AL_Y(3))      # n -= 1
W(CMP0); BR(BNE, "TV_CMP")
W(0x0117); W(0x0557); W(ST_AL_Y(3))          # drop = (R at the window start) - R
ca.call2(W, BSR, SOURCEDROP, al=('slot', 2), ah=('slot', 3))
W(LD_AL_Y(5)); W(CMP0); BR(BNE, "TV_WIN")
W(*LDI_AL(ID_VERIFIED)); W(0xF80F)           # R = 0: the source closed itself; do NOT touch it again
LBL("TV_MIS")                   # AL = the wrong element
W(*CMPI_AL(0x100)); BR(BCC, "TV_WIDEID")     # AL >= 0x100 (unsigned)
W(LD_AL_Y(5)); W(*CMPI_AL(EARLY_R)); BR(0x2C, "TV_LATE")     # R <= 2674: position >= 126
W(*LDI_AL(ID_MIS_EARLY)); BR(BRA, "TV_CLOSE")
LBL("TV_LATE")
W(*LDI_AL(ID_MIS_LATE)); BR(BRA, "TV_CLOSE")
LBL("TV_WIDEID")
W(*LDI_AL(ID_WIDE)); BR(BRA, "TV_CLOSE")
LBL("TV_SHORT")                 # SourceSize returned 0 with bytes still due: the source ended (it closed ITSELF when drained,
W(*LDI_AL(ID_SHORT)); W(0xF80F) # so its handle may be dead): speak, and NEVER touch the handle again (no SourceClose)
LBL("TV_MAP0")                  # SourceMap returned 0 on a source that still reports bytes: close it, then the same id
W(*LDI_AL(ID_SHORT))
LBL("TV_CLOSE")                 # AL = the id; keep it across SourceClose (slot 4 is free now)
W(ST_AL_Y(4))
ca.call1(W, BSR, SOURCECLOSE, al=('slot', 2))
W(LD_AL_Y(4))
W(0xF80F)                       # leavel -8
LBL("TV_H0")
W(*LDI_AL(ID_H0)); W(0xF80F)    # no source exists: nothing to close

# ---- where the dead-code region starts: a function is never split between the window and the region (the
# only cross-area form Bose uses is `bsr`; a 3-word conditional branch is refused below), so the region marker goes
# BEFORE a whole function. Everything from REGION_AT on is cold code entered only by `bsr`.
REGION_AT = 'WLOOP'             # window: TRIG, stub, HANDLER, ARM, SENDLATER, TW; region: WLOOP, TV
_k = [i for i, it in enumerate(prog) if it[0] == "label" and it[1] == REGION_AT][0]
prog.insert(_k, ("region",))

# ---- informational: estimated words per function (bsr to a stock address = 3 words, to a label = 2, br = 1)
_cur, _sizes = None, {}
for _it in prog:
    if _it[0] == "label" and _it[1] in ("TRIG", "STUB_D3", "HANDLER", "ARM", "SENDLATER", "TW", "WLOOP", "TV"):
        _cur = _it[1]; _sizes[_cur] = 0
    elif _cur and _it[0] == "w": _sizes[_cur] += len(_it[1])
    elif _cur and _it[0] == "bsr": _sizes[_cur] += 2 if isinstance(_it[1], str) else 3
    elif _cur and _it[0] == "br": _sizes[_cur] += 1
print('estimated words per function:', ', '.join('%s %d' % kv for kv in _sizes.items()), '(total %d)' % sum(_sizes.values()))

# ---- layout (proven machinery, verbatim from probe137/139/140) ----
bsr_size, br_size = {}, {}
label_addr = {}
changes = []
def needs_follow(item):
    k = item[0]
    if k == "region": return False
    if k == "bsr": return True
    if k == "br": return item[1] != 0xE0
    return (item[1][-1] & 0xFF) not in ca.TERMINATOR_OPS   # rts, leavel, bra @abs (a synthesised stub ends in 0xE1)
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
            # probe196: if the previous placed item is a terminator nothing falls into the leftover words, so no
            # connector is needed (the probe195 engine asserted when fewer than `cs` words were left). The leftover
            # words stay stock. Everything is still checked by decode-verify below.
            _j = i - 1
            while _j >= 0 and prog[_j][0] == "label": _j -= 1
            if _j >= 0 and not needs_follow(prog[_j]):
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


# probe172: the stubs ride along ONLY when cave code is in the region; this image puts
# nothing there, so the seven dead functions stay byte-for-byte stock.
if any(caveguard.region_fn(_a) is not None for _a in out):
    for _a, _v in REGION_STUBS.items():
        assert _a not in out, hex(_a)
        out[_a] = _v
for _lbl in ("HANDLER", "STUB_D3"):   # probe179: the handler's FIRST instruction stays in the window; probe196: so do both stubs
    assert caveguard.SAFE_WINDOW[0] <= label_addr[_lbl] < caveguard.SAFE_WINDOW[1], _lbl
assert caveguard.SAFE_WINDOW[0] <= TASK_AT < caveguard.SAFE_WINDOW[1]
_nreg = sum(1 for a in out if caveguard.region_fn(a) is not None)
print('region: %d words used (%d of them stubs), const window: %d words'
      % (_nreg, len(REGION_STUBS), len(out) - _nreg))
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
