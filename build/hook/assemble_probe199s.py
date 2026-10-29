#!/usr/bin/env python3
"""probe199s: D1, a READ-ONLY diagnostic of the FILE-SOURCE read side, built on the STOCK data_us (no staging). 2026-10-14.
NOT independently reviewed. Why: probe198 (R3) spoke 0x3B ("adjust airbuds") = the pre-erase look failed, nothing erased; the build and the
readback were right, so the cave READS the staged data_us wrongly (or the file source serves other bytes). The staged region A also broke
spelled speech, so spoken ids are unreliable while the staged data_us is installed: this image carries the STOCK data_us (every id reliable, speech
restored) and tests the read side against the stock bytes, including the very position probe198 looked at (period 1,320, element 18 = 6a 00 0d 00).
Note, gates, press page, outcome table: docs/deep/material-2026-10-13/D1-probe199.md.

## WHAT IT DOES: it writes NOTHING (no sink, no partition call, no erase). Three ticks, one spoken id each, STAGE_MS apart.
  PRESS (centre LONG): STOP if a tick is pending, else arm T1 (probe196's ARM, probe197's lever).
  every tick: sinkState guard {3,13}; open NowSpeakTTS/data_us (OPENSRC); the test; SourceClose; ONE id; arm the next tick.
  T1 (0x12) layout of SourceMap's elements at the FILE START (header bytes 02 00 00 00 09 00 00 00).
  T2 (0x13) four checkpoints: after 1, 100, 1000 and 1320 x SourceDrop(64), element 0 and 18 against the stock bytes (the last is probe198's look position).
  T3 (0x14) the tail walk: SourceDrop(64) while SourceSize == 0xC00; the first SourceSize below 0xC00 is the exact number of bytes left.
"""

import os, re, sys, json, subprocess, hashlib
sys.path.insert(0, 'tools')
import caveasm as ca

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

_PROBE = re.match(r'assemble_(probe[0-9a-z]+)\.py$',
                  os.path.basename(os.path.abspath(__file__))).group(1)

SYNTH_TRAPS = []           # no synthesised stub in this variant (0xD3 is not called)
SYNTH_CONTROLS = []

CAVE = 0x3E21D
HOOK = 0x00E46
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
AREA0 = 0x6EA30
CONST_BASE = 0x7400

BACK = 0xE06D
SPEAK = 0xDF7F
OVERSINK = ca.STUB['StreamPartitionOverwriteSink']
SINKMAP = ca.STUB['SinkMap']
SINKCLAIM = ca.STUB['SinkClaim']
SINKFLUSH = ca.STUB['SinkFlush']
SETDIGEST = ca.STUB['PartitionSetMessageDigest']
SINKCLOSE = ca.STUB['SinkClose']
MEMMOVE = ca.STUB['memmove']
VMCLOCK = ca.STUB['VmGetClock']
FILEFIND = ca.STUB['FileFind']
FILESRC = ca.STUB['StreamFileSource']
SOURCESIZE = ca.STUB['SourceSize']
SOURCEMAP = ca.STUB['SourceMap']
SOURCEDROP = ca.STUB['SourceDrop']
SOURCECLOSE = ca.STUB['SourceClose']
MSGLATER = ca.STUB['MessageSendLater']
CANCELFIRST = ca.STUB['MessageCancelFirst']
TASK_ADDR = 0xBA3C

PRESS_DELAY = 2000
SINKSTATE = 0x59E

# ---- geometry (no payload in this image: the data_us on the speaker is the STOCK file)
START_PERIOD = 1320                       # the first start that spares the region-A header (narrow184_lib.header_a_hits)
PERIOD = 64
MAPOFF = 18                               # the element probe198 looked at (period 1,320 element 18)
DIRNAME, FILENAME = "NowSpeakTTS", "data_us"

# ---- spoken ids (docs/request-id-catalog.md). Disjoint per tick. The data_us is STOCK, so every id is reliable.
STAGE_FIRST, STAGE_LAST = 0x12, 0x14
ID_GUARD, ID_NOSRC = 0x3C, 0x17                                           # as probe197/198: state guard / file open refused
ID_L_CLEAN, ID_L_JUNK, ID_L_PACKED, ID_L_OTHER, ID_L_NOMAP = 0x12, 0x13, 0x14, 0x15, 0x16          # T1
ID_W_OK, ID_W_F1320, ID_W_F1000, ID_W_F100, ID_W_F1 = 0x30, 0x2E, 0x2C, 0x2A, 0x28               # T2 (battery level = how far the walk got)
ID_T_EXACT, ID_T_OVER, ID_T_UNDER, ID_T_STUCK, ID_T_W0 = 0x3E, 0x3D, 0x39, 0x24, 0x1B             # T3 (the tail walk)

# ---- the STOCK data_us, read at build time: the expected bytes of every test come from the file itself
_US = open('firmware/bose/extracted/internal_fs/data_us', 'rb').read()
assert len(_US) == 219528 and _US[:8] == bytes([2, 0, 0, 0, 9, 0, 0, 0])
XORK = 0x15A                                   # table words are value ^ XORK (no zero low byte)
WALK_ROWS = []                                 # (skip count, element 0, element 18) for periods 1, 100, 1000, 1320 (cumulative)
_prev = 0
for _p in (1, 100, 1000, START_PERIOD):
    WALK_ROWS.append((_p - _prev, _US[64 * _p], _US[64 * _p + 18]))
    _prev = _p
assert all((v ^ XORK) & 0xFF for r in WALK_ROWS for v in r)
assert WALK_ROWS[-1][2] == 0x6A and _US[64 * START_PERIOD + 18:64 * START_PERIOD + 22] == bytes([0x6A, 0, 0x0D, 0])   # probe198's look position, stock
TAIL_N = -(-(len(_US) - 0xC00 + 1) // PERIOD)  # first n with 64 n > size - 0xC00
TAIL_S = len(_US) - PERIOD * TAIL_N
TAIL_CAP = TAIL_N + 117
assert (TAIL_N, TAIL_S) == (3383, 3016) and TAIL_S < 0xC00 <= len(_US) - PERIOD * (TAIL_N - 1)
STAGE_MS = 9000                                # tick -> next tick (a stock prompt is a DSP swap; >= 8000 as probe196)
w = xapvm.load_words("firmware/bose/extracted/internal_fs/vm.app")
code = w[0x18:]

# ---- "NowSpeakTTS" from the firmware's const pool (probe162's _pool_ah): the first copy whose prefixed ld AH folds back
def _pool_ah(text):
    p = [ord(c) for c in text]
    for i in range(236514, len(code) - len(p)):
        if list(code[i:i + len(p)]) != p: continue
        d = (CONST_BASE + (i - 236514)) & 0xFFFF
        lo8 = d & 0xFF; hi8 = ((d >> 8) + (1 if lo8 >= 0x80 else 0)) & 0xFF
        sx = lambda b: b - 256 if b >= 0x80 else b
        if 0x7400 <= d <= 0xD39A and 1 <= hi8 and (sx(hi8) * 256 + sx(lo8)) & 0xFFFF == d:
            return d, ((hi8 << 8), (lo8 << 8) | 0x10)
    raise AssertionError('no usable pool copy of %r' % text)
DIR_DATA, _DIR_AH = _pool_ah(DIRNAME)

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
def LD_X_Y(n): return (n << 8) | 0x1B     # ld X,@(n,Y)
def LD_AH_X(n): return (n << 8) | 0x12    # ld AH,@(n,X)
MASK_AL = ca.imm_words(0xFF, 0xC4)         # and AL,#0xFF
XORAL_K = ca.imm_words(XORK, 0xD4)         # xor AL,#0x15A
XORAH_K = ca.imm_words(XORK, 0xD0)         # xor AH,#0x15A
CMP0 = 0x0084                              # cmp AL,#0
BEQ, BNE, BCS, BCC, BRA = 0xF4, 0xF0, 0xFC, 0xF8, 0xE0

STG = None                                     # no staging: the data_us in the image is the stock file

# ------------------------------------------------------------------ the TRIGGER (probe197's, verbatim: the lever included)
LBL("TRIG")
W(0xF80B)                       # enterl -8
W(0x0027)                       # st AL,@(0,Y)  the event id
W(*ca.imm_words(0x4004, 0x84))  # cmp AL,#0x4004
BR(BNE, "PASS")                 # bne -> not ours: replay
BSR("ARM")                      # arm the write tick, or stop the pending one
W(0x0014)                       # ld AL,#0
W((21 << 8) | 0x27)             # st AL,@(21,Y)  caller (13,Y): the indicate flag := 0     (THE CONSUME LEVER, unproven)
W((22 << 8) | 0x17)             # ld AL,@(22,Y)  caller (14,Y): its flag word
W(*ca.imm_words(0x8000, 0xB4))  # or AL,#0x8000  bit 15 = "consumed"
W((22 << 8) | 0x27)             # st AL,@(22,Y)
W(0xF80F)                       # leavel -8: the voice-dial event is swallowed
LBL("PASS")
W(0x0017)                       # ld AL,@(0,Y)  the event back in AL
BSR(FN189FB)                    # the stock call, replayed
W(0xF80F)                       # leavel -8


# ---- the carried file name, ONE item in the const window (the cave READS it), followed by a terminator
LBL("STRFILE")
W(*[ord(c) for c in FILENAME])  # "data_us", no NUL: FileFind takes the length (7)
W(0x00E2)                       # rts: never reached; nothing falls into the string

# ---- the checkpoint table, ONE item in the const window (read through a pointer by WALK): per checkpoint
# [skip count, element 0, element 18]. Every word is stored as value ^ 0x15A so that no word has a zero low byte (the
# decoder would fold such a word into the next instruction as a prefix, and a data word is not an instruction);
# WALK undoes it with `xor #0x15A`. The expected bytes are the STOCK data_us bytes at the checkpoint (read from the file at build time).
LBL("WTAB")
W(*[v ^ XORK for row in WALK_ROWS for v in row])
W(0x00E2)                       # rts: never reached

# --------------------------------------------------------------- the HANDLER (one tick per stage; probe196's dispatch)
# AL = task, AH = the MessageId = the STAGE (0x12..0x14). Frame -8: 2 = the file source, 3 = next stage (0 = none),
# 4 = the stage id (then the delay), 5 = the id to speak.
LBL("HANDLER")
W(0xF80B)
W(ST_AH_Y(4))
W(*CMPI_AH(STAGE_FIRST)); BR(BCS, "H_OUT")      # an id below 0x12 (unsigned): not ours
W(*CMPI_AH(STAGE_LAST + 1)); BR(BCC, "H_OUT")   # an id above 0x14: not ours
W(*ca.imm_words(SINKSTATE, 0x15))              # ld AL,@0x59e   the guard, re-read at EVERY tick (probe197's, unchanged)
W(*CMPI_AL(13)); BR(BEQ, "H_GOK")
W(*CMPI_AL(3)); BR(BNE, "H_REFUSE")
LBL("H_GOK")
BSR("OPENSRC")                                 # AL = the data_us source, 0 = refused
W(ST_AL_Y(2)); W(CMP0); BR(BEQ, "H_NOSRC")
W(LD_AL_Y(4)); W(*CMPI_AL(STAGE_FIRST)); BR(BEQ, "H_D1")
W(*CMPI_AL(STAGE_FIRST + 1)); BR(BEQ, "H_D2")
W(LD_AL_Y(2)); BSR("TAIL"); BR(BRA, "H_DONE")
LBL("H_D1")
W(LD_AL_Y(2)); BSR("T1"); BR(BRA, "H_DONE")
LBL("H_D2")
W(LD_AL_Y(2)); BSR("WALK")
LBL("H_DONE")
W(ST_AL_Y(5))                                  # the id to speak
W(*CMPI_AL(ID_T_OVER)); BR(BEQ, "H_NOCLOSE")   # the over-advance outcome: the source may have closed itself at the file end
ca.call1(W, BSR, SOURCECLOSE, al=('slot', 2))
LBL("H_NOCLOSE")
W(LD_AL_Y(4)); W(0x0134); W(ST_AL_Y(3))        # next stage = this stage + 1
W(*CMPI_AL(STAGE_LAST + 1)); BR(BNE, "FIN")
LBL("H_END")
W(0x0014); W(ST_AL_Y(3))                       # the chain ends here
BR(BRA, "FIN")
LBL("H_NOSRC")
W(*LDI_AL(ID_NOSRC)); W(ST_AL_Y(5)); BR(BRA, "H_END")
LBL("H_REFUSE")
W(*LDI_AL(ID_GUARD)); W(ST_AL_Y(5)); BR(BRA, "H_END")
LBL("FIN")                      # speak slot 5, then arm slot 3 (if any) STAGE_MS later
W(LD_AL_Y(5))
BSR(SPEAK)
W(LD_AL_Y(3)); W(CMP0); BR(BEQ, "FEND")
W(*LDI_AL(STAGE_MS)); W(ST_AL_Y(4))
BR(BRA, "SENDLATER")
LBL("FEND")
LBL("H_OUT")
W(0xF80F)                       # leavel -8

# ---------------------------------------------------------------------- ARM (the press; probe196's)
# MessageCancelFirst(task, id) for each stage id: TRUE = that stage's tick was pending, i.e. the run is going: this press is a
# STOP, nothing else is touched (silent). Else arm T1.
LBL("ARM")
W(0xF80B)
W(*LDI_AL(STAGE_FIRST)); W(ST_AL_Y(2))
LBL("ARM_LOOP")
ca.call2(W, BSR, CANCELFIRST, al=('imm', TASK_ADDR), ah=('slot', 2))
W(CMP0); BR(BNE, "STOP")
W(LD_AL_Y(2)); W(0x0134); W(ST_AL_Y(2))
W(*CMPI_AL(STAGE_LAST + 1)); BR(BNE, "ARM_LOOP")
W(*LDI_AL(STAGE_FIRST)); W(ST_AL_Y(3))
W(*LDI_AL(PRESS_DELAY)); W(ST_AL_Y(4))
BR(BRA, "SENDLATER")
LBL("STOP")
W(0xF80F)

LBL("SENDLATER")
W(0x0014); W(0x0027)
W(0x0127)
W(LD_AL_Y(4))
W(0x0227)
W(LD_AH_Y(3))
W(*ca.imm_words(TASK_ADDR, 0x14))
BSR(MSGLATER)
W(0xF80F)

# ---------------------------------------------------------------------- OPENSRC: FileFind x2 + StreamFileSource (probe195's BUILD, verbatim)
LBL("OPENSRC")
W(0xF80B)
W(*ca.imm_words(len(DIRNAME), 0x14))
W(0x0027)                       # st AL,@(0,Y)  arg3 = length
W(0x0114)                       # ld AL,#1      FILE_ROOT
W(*_DIR_AH)                     # ld AH,#<pool copy of "NowSpeakTTS">
BSR(FILEFIND)
W(CMP0); BR(BEQ, "OS_FAIL")
W(*ca.imm_words(len(FILENAME), 0x10))
W(0x0023)                       # st AH,@(0,Y)  arg3 = length
LBL("SETAHFILE")
W(0x0000, 0x0010)               # ld AH,#<data addr of STRFILE> (patched below)
BSR(FILEFIND)
W(CMP0); BR(BEQ, "OS_FAIL")
BSR(FILESRC)                    # AL = the source (0 = refused)
W(0xF80F)
LBL("OS_FAIL")
W(0x0014); W(0xF80F)

# ---------------------------------------------------------------------- T1: the map's element layout at the FILE START
# AL = source. The stock header is 02 00 00 00 09 00 00 00 (bytes). Slots: 2 source, 3 e0, 4 e2.
# CLEAN  : e0 == 2 and e2 == 0 (one byte per element, nothing in the high byte: the unit rule F207)
# PACKED : e0 == 2 and e2 == 9 (two bytes per element, little endian)
# JUNK   : e0 & 0xFF == 2 but e0 != 2 (a high byte is not zero)
# NOMAP  : SourceMap returned 0       OTHER : none of those (a big-endian packed map, e0 == 0x200, lands here; so does a shifted map)
LBL("T1")
W(0xF80B)
W(ST_AL_Y(2))
ca.call1(W, BSR, SOURCEMAP, al=('slot', 2))
W(CMP0); BR(BEQ, "T1_NOMAP")
W(0x0127); W(0x011B)            # st AL,@(1,Y) ; ld X,@(1,Y)   (no trap in between)
W(LD_AL_X(0)); W(ST_AL_Y(3))
W(LD_AL_X(2)); W(ST_AL_Y(4))
W(LD_AL_Y(3)); W(*CMPI_AL(2)); BR(BNE, "T1_NE0")
W(LD_AL_Y(4)); W(CMP0); BR(BEQ, "T1_CLEAN")
W(*CMPI_AL(9)); BR(BEQ, "T1_PACKED")
LBL("T1_OTHER")
W(*LDI_AL(ID_L_OTHER)); W(0xF80F)
LBL("T1_NE0")
W(*MASK_AL); W(*CMPI_AL(2)); BR(BNE, "T1_OTHER")   # AL = e0: the low byte is the header's, the high byte is not zero
W(*LDI_AL(ID_L_JUNK)); W(0xF80F)
LBL("T1_CLEAN")
W(*LDI_AL(ID_L_CLEAN)); W(0xF80F)
LBL("T1_PACKED")
W(*LDI_AL(ID_L_PACKED)); W(0xF80F)
LBL("T1_NOMAP")
W(*LDI_AL(ID_L_NOMAP)); W(0xF80F)

# ---------------------------------------------------------------------- WALK: four checkpoints (periods 1, 100, 1000, 1320)
# AL = source. For each row of WTAB: SourceDrop(64) `skip` times (probe198's skip loop), SourceMap, then element 0 and element 18, each & 0xFF,
# must equal the stock bytes (the last checkpoint IS the byte probe198 looked at: period 1,320, element 18 = 6a). Returns the id of the FIRST failing checkpoint (a failed drop loop or SourceMap 0 counts as failing), or ID_W_OK.
# Slots: 2 source, 3 table pointer, 4 checkpoints left, 5 map pointer, 6 the skip count, then the masked element.
LBL("WALK")
W(0xF60B)                       # enterl -10: slots 6 and 7 are USABLE (V11 D1: in enterl -8 they were the saved return address)
W(ST_AL_Y(2))
LBL("SETAHTAB")
W(0x0000, 0x0010)               # ld AH,#<data addr of WTAB> (patched below)
W(ST_AH_Y(3))
W(*LDI_AL(len(WALK_ROWS))); W(ST_AL_Y(4))
LBL("WK_NEXT")
W(LD_X_Y(3)); W(LD_AL_X(0)); W(*XORAL_K); W(ST_AL_Y(6))      # the skip count of this row (decoded)
LBL("WK_DROP")                  # probe198's skip loop, verbatim: SourceSize >= 64, SourceDrop(64), count times
ca.call1(W, BSR, SOURCESIZE, al=('slot', 2))
W(*CMPI_AL(PERIOD)); BR(BCS, "WK_FAIL")
ca.call2(W, BSR, SOURCEDROP, al=('slot', 2), ah=('imm', PERIOD))
W(LD_AL_Y(6)); W(0xFF34); W(ST_AL_Y(6))
W(CMP0); BR(BNE, "WK_DROP")
ca.call1(W, BSR, SOURCEMAP, al=('slot', 2))
W(CMP0); BR(BEQ, "WK_FAIL")
W(ST_AL_Y(5))
W(LD_X_Y(5)); W(LD_AL_X(0)); W(*MASK_AL); W(ST_AL_Y(6))
W(LD_X_Y(3)); W(LD_AL_X(1)); W(*XORAL_K); W(0x0687); BR(BNE, "WK_FAIL")      # cmp AL,@(6,Y)
W(LD_X_Y(5)); W(LD_AL_X(18)); W(*MASK_AL); W(ST_AL_Y(6))
W(LD_X_Y(3)); W(LD_AL_X(2)); W(*XORAL_K); W(0x0687); BR(BNE, "WK_FAIL")
W(LD_AL_Y(3)); W(0x0334); W(ST_AL_Y(3))         # next row
W(LD_AL_Y(4)); W(0xFF34); W(ST_AL_Y(4)); W(CMP0); BR(BNE, "WK_NEXT")
W(*LDI_AL(ID_W_OK)); W(0xF60F)
LBL("WK_FAIL")                  # slot 4 = c = checkpoints left (4 = the first failed ... 1 = the last): id = 0x30 - 2 c = 0x28, 0x2A, 0x2C, 0x2E
W(LD_AL_Y(4)); W(0x0437); W(ST_AL_Y(6))                    # add AL,@(4,Y) ; st AL,@(6,Y)   2 c
W(*LDI_AL(ID_W_OK)); W(0x0657); W(0xF60F)                  # ld AL,#0x30 ; sub AL,@(6,Y) ; leavel

# ---------------------------------------------------------------------- TAIL: how far do TAIL_N drops of 64 really go?
# AL = source. SourceSize of a file source is min(bytes left, 0xC00) (stack 0x55a97, proven). SourceDrop(64) while SourceSize == 0xC00,
# counting n; the loop ends at the first SourceSize below 0xC00, which then IS the exact number of bytes left. With exact drops of
# 64 that is n = TAIL_N and S = TAIL_S. Slots: 2 source, 3 n, 4 S. The loop is capped at TAIL_CAP drops.
LBL("TAIL")
W(0xF80B)
W(ST_AL_Y(2))
W(0x0014); W(ST_AL_Y(3))
LBL("TL_TOP")
ca.call1(W, BSR, SOURCESIZE, al=('slot', 2))
W(ST_AL_Y(4))
W(*CMPI_AL(0xC00)); BR(BNE, "TL_EXIT")
W(LD_AL_Y(3)); W(*CMPI_AL(TAIL_CAP)); BR(BEQ, "TL_STUCK")
ca.call2(W, BSR, SOURCEDROP, al=('slot', 2), ah=('imm', PERIOD))
W(LD_AL_Y(3)); W(0x0134); W(ST_AL_Y(3))
BR(BRA, "TL_TOP")
LBL("TL_EXIT")
W(LD_AL_Y(3)); W(CMP0); BR(BEQ, "TL_W0")
W(LD_AL_Y(4)); W(*CMPI_AL(TAIL_S)); BR(BEQ, "TL_AT")        # S == 3,016: exactly TAIL_N x 64 bytes were dropped
BR(BCS, "TL_OVER")                                          # S < 3,016: more than that was dropped
W(*LDI_AL(ID_T_UNDER)); W(0xF80F)
LBL("TL_OVER")
W(*LDI_AL(ID_T_OVER)); W(0xF80F)
LBL("TL_AT")
W(*LDI_AL(ID_T_EXACT)); W(0xF80F)
LBL("TL_STUCK")
W(*LDI_AL(ID_T_STUCK)); W(0xF80F)
LBL("TL_W0")
W(*LDI_AL(ID_T_W0)); W(0xF80F)


# ---- where the dead-code region starts: a function is never split between the window and the region (the
# only cross-area form Bose uses is `bsr`; a 3-word conditional branch is refused below), so the region marker goes
# BEFORE a whole function. Everything from REGION_AT on is cold code entered only by `bsr`.
REGION_AT = 'OPENSRC'             # window: TRIG, string, table, HANDLER, ARM, SENDLATER; region: OPENSRC, T1, WALK, TAIL (found by a permutation search)
_k = [i for i, it in enumerate(prog) if it[0] == "label" and it[1] == REGION_AT][0]
prog.insert(_k, ("region",))

# ---- informational: estimated words per function (bsr to a stock address = 3 words, to a label = 2, br = 1)
_cur, _sizes = None, {}
for _it in prog:
    if _it[0] == "label" and _it[1] in ("TRIG", "HANDLER", "ARM", "SENDLATER", "OPENSRC", "T1", "WALK", "TAIL"):
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



CONST_ORIGIN = 236514
def _str_ptr(label, text, setah, nul=True):
    base = label_addr[label]
    words = ([ord(c) for c in text] if isinstance(text, str) else list(text)) + ([0] if nul else [])
    for k, expect in enumerate(words):
        got = out.get(base + k)
        assert got == expect, ('string %r is NOT contiguous: word %d at %#x is %r, expected %r' % (text, k, base + k, got, expect))
    data = (CONST_BASE + (base - CONST_ORIGIN)) & 0xFFFF
    assert 0x7400 <= data <= 0xD39A, (text, hex(data))
    lo8 = data & 0xFF
    hi8 = ((data >> 8) + (1 if lo8 >= 0x80 else 0)) & 0xFF
    sx = lambda b: b - 256 if b >= 0x80 else b
    assert (sx(hi8) * 256 + sx(lo8)) & 0xFFFF == data, ('prefixed ld AH does not fold back for %r' % text)
    assert 1 <= hi8 <= 0xFF, hex(data)
    a = label_addr[setah]
    out[a] = (hi8 << 8) | 0x00
    out[a + 1] = (lo8 << 8) | 0x10
    print('  %-12r %2d words, contiguous at code %#x -> data %#06x (ld AH %04x %04x)' % (text, len(words), base, data, out[a], out[a+1]))
print('FileFind strings:')
print('  %-14r from the firmware const pool at data %#06x (ld AH %04x %04x)' % (DIRNAME, DIR_DATA, _DIR_AH[0], _DIR_AH[1]))
_str_ptr('STRFILE', FILENAME, 'SETAHFILE', nul=False)
_str_ptr('WTAB', [v ^ XORK for r in WALK_ROWS for v in r], 'SETAHTAB', nul=False)
# probe172: the stubs ride along ONLY when cave code is in the region; this image puts
# nothing there, so the seven dead functions stay byte-for-byte stock.
if any(caveguard.region_fn(_a) is not None for _a in out):
    for _a, _v in REGION_STUBS.items():
        assert _a not in out, hex(_a)
        out[_a] = _v
for _lbl in ("HANDLER", "STRFILE", "WTAB"):   # probe179: the handler's FIRST instruction stays in the window; probe196: so do both stubs
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
_cave_edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    _cave_edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    _cave_edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
_dfu = f"build/hook/{_PROBE}_brown.dfu"
# The staged payload is 58,968 area-byte edits in data_us (28 bytes of every 64): far more than one command line holds
# (Windows: 32,767 characters), so the image is built through fsedit.build() in-process, exactly as probe184 was.
# probe198_cmd.txt records the command that rebuilds it.
open(f"build/hook/{_PROBE}_cmd.txt", "w").write(
    "python build/hook/assemble_%s.py --build\n"
    "# %d cave/redirect byte edits (no staging: the data_us stays the stock file) go through fsedit.build() in-process; output %s\n"
    % (_PROBE, len(_cave_edits), _dfu))
print("wrote build/hook/%s_words.json (%d words) and %s_cmd.txt" % (_PROBE, len(out), _PROBE))

if "--build" in sys.argv:
    sys.path.insert(0, "tools")
    _fsc = {'__file__': os.path.abspath('tools/fsedit.py')}
    try:
        exec(compile(open("tools/fsedit.py", encoding="utf-8").read(), "tools/fsedit.py", "exec"), _fsc)
    except SystemExit:
        pass
    _edits = [(int(o, 16), int(v, 16)) for o, v in REDIRECT_EDITS]
    for cw in sorted(out):
        v = out[cw] & 0xFFFF
        _edits.append((AREA0 + 2*cw, v & 0xFF))
        _edits.append((AREA0 + 2*cw + 1, (v >> 8) & 0xFF))
    assert len({o for o, _ in _edits}) == len(_edits), 'an area byte is edited twice (cave vs payload)'
    _fsc["build"](_edits, _dfu)
    _d = open(_dfu, 'rb').read()
    print('built %s: stock data_us, cave only, sha256 %s' % (_dfu, hashlib.sha256(_d).hexdigest()))
else:
    print("edit lists ready (%d cave/redirect byte edits, no staging); "
          "run with --build to assemble %s" % (len(_cave_edits), _dfu))
