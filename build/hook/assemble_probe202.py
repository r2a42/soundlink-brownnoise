#!/usr/bin/env python3
"""probe202: G1, the ALIGNMENT CENSUS: a READ-ONLY diagnostic of where SourceMap shows the file bytes, for several window starts, built on the
STOCK data_us. 2026-10-15. NOT independently reviewed.
Why: probe201 (staged data_us) found no gram in elements 0..39 at the 64-aligned windows 84,416 and 84,480 and none at the unaligned 84,494, while
probe200 (stock) found the stock gram at element 5 (shift +1) at the unaligned starts 4 and 84,494. This image measures, per window start, the
element index j (0..99) where a known two-byte gram of the STOCK file appears, as decimal digit prompts, with a check digit per start.
It WRITES NOTHING (no sink, no partition call, no erase). Ticks STAGE_MS apart: START 0x12, then per start three prompts (hi digit, lo digit,
check = (hi + lo) mod 10) as "battery (v+1)x10 %" (v = percent / 10 - 1), then END 0x13. Note: docs/deep/material-2026-10-13/G1-probe202.md.
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
ID_NOMAP = 0x16                                                        # SourceMap returned 0 (the guard and an open refusal are silent)
ID_START, ID_END = 0x12, 0x13                                             # framing: "voice prompts on" ... "voice prompts off"
SCAN_N = 100                                                              # gram search: element j = 0..99
GRAM_E = 11                                                               # the gram is the stock bytes at window start + 11
OLD_ROW = 6                                                              # the row whose map is taken BEFORE the drops (99 = none)

# ---- the STOCK data_us, read at build time: every gram comes from the file itself
_US = open('firmware/bose/extracted/internal_fs/data_us', 'rb').read()
assert len(_US) == 219528 and _US[:16] == bytes.fromhex('0200000009000000d0a4463f9600b900')
# (drops of 64, one extra drop, old-pointer row, window start). The window start is 64 n + x.
ROWDEF_ALL = [
    (1, 0, False, 64),                  # 0  aligned, small            (probe199s T2: first checkpoint)
    (10, 0, False, 640),                # 1  aligned, ten drops of 64
    (0, 640, False, 640),               # 2  the same start by ONE drop of 640 (history)
    (10, 1, False, 641),                # 3  aligned + 1
    (10, 32, False, 672),               # 4  aligned + 32
    (1320, 0, False, 84480),            # 5  aligned, large            (probe198b's window)
    (1320, 14, False, 84494),           # 6  aligned + 14              (probe200 k4: stock gram at element 5)
    (1320, 0, True, 84480),             # 7  as 5 but the map is taken at position 0 and read through the OLD pointer (probe200 k2 form)
]
NR = 7
ROWDEF = [ROWDEF_ALL[i] for i in [0, 1, 2, 3, 5, 6, 7]]
for _n, _x, _old, _P in ROWDEF:
    assert _P == 64 * _n + _x or (_old and _P == 64 * _n + _x) or True
    assert 64 * _n + _x == _P, (_n, _x, _P)
GRAMS = []
for _n, _x, _old, _P in ROWDEF:
    _g = _US[_P + GRAM_E:_P + GRAM_E + 2]
    assert _g[0] != _g[1] and not any(_US[_i:_i + 2] == _g for _i in range(max(0, _P - 95), _P + GRAM_E)), (_P, _g.hex())   # no earlier occurrence: the first match is the true one for any lead up to 95
    GRAMS.append((_g[0], _g[1]))
NT = 3 * NR + 2                                                           # START + 3 per row + END
STAGE_FIRST, STAGE_LAST = 0x12, 0x12 + NT - 1
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


# ---- the start-state rows, ONE item each in the const window (the cave READS them): [drops of 64, one extra drop + 1 (1 = none), gram byte 0, gram byte 1]
# followed by an rts that is never reached (a data word with a zero low byte folds into the next word, so the terminator is in the same item),
# and the row pointer table PT (data addresses of the rows, patched after the layout).
LBL("PT")
W(*[0x0101 + i for i in range(NR)], 0x00E2)
for _i, (_n, _x, _old, _P) in enumerate(ROWDEF):
    LBL("ROW%d" % _i)
    W(_n, _x + 1, GRAMS[_i][0], GRAMS[_i][1], 0x00E2)

# --------------------------------------------------------------- the HANDLER (one tick per stage; probe199s's)
# AL = task, AH = the MessageId = the STAGE (0x12..0x18). Frame -8: 2 = the file source, 3 = next stage (0 = none),
# 4 = the stage id (then the delay), 5 = the stage index / the id to speak.
LBL("HANDLER")
W(0xF80B)
W(ST_AH_Y(4))
W(LD_AL_Y(4)); W(0xEE34); W(ST_AL_Y(5))        # add AL,#-18 : the stage index k
W(*CMPI_AL(STAGE_LAST - STAGE_FIRST + 1)); BR(BCC, "H_OUT")   # k >= 6 (unsigned, so also an id below 0x12): not ours
W(*ca.imm_words(SINKSTATE, 0x15))              # ld AL,@0x59e   the guard, re-read at EVERY tick (probe197's, unchanged)
W(*CMPI_AL(13)); BR(BEQ, "H_GOK")
W(*CMPI_AL(3)); BR(BNE, "H_OUT")                              # refused: silent
LBL("H_GOK")
BSR("OPENSRC")                                 # AL = the data_us source, 0 = refused
W(ST_AL_Y(2)); W(CMP0); BR(BEQ, "H_OUT")
W(LD_AH_Y(5)); W(LD_AL_Y(2)); BSR("TICK")      # TICK(AL = source, AH = k) -> AL = the id
W(ST_AL_Y(5))
ca.call1(W, BSR, SOURCECLOSE, al=('slot', 2))
W(LD_AL_Y(4)); W(0x0134); W(ST_AL_Y(3))        # next stage = this stage + 1
W(*CMPI_AL(STAGE_LAST + 1)); BR(BNE, "FIN")
W(0x0014); W(ST_AL_Y(3))                       # the chain ends here
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

# ---------------------------------------------------------------------- SCAN: AL = map pointer, AH = a gram pointer [g0, g1]
# Looks for two consecutive elements e[j], e[j+1] with (e & 0xFF) == g0, g1, j = 0..SCAN_N-1. Returns AL = the first j, or SCAN_N (= none).
# Reads only elements 0..SCAN_N of the map. Slots: 2 pointer (advanced), 3 gram pointer, 4 j. Frame -10.
LBL("SCAN")
W(0xF60B)
W(ST_AL_Y(2)); W(ST_AH_Y(3))
W(0x0014); W(ST_AL_Y(4))
LBL("SC_J")
for _e in (0, 1):
    W(LD_X_Y(2)); W(LD_AL_X(_e)); W(*MASK_AL); W(LD_X_Y(3)); W((_e << 8) | 0x86); BR(BNE, "SC_NEXT")     # ld AL,@(e,X) ; and AL,#0xFF ; cmp AL,@(e,X')
W(LD_AL_Y(4)); W(0xF60F)
LBL("SC_NEXT")
W(LD_AL_Y(2)); W(0x0134); W(ST_AL_Y(2))
W(LD_AL_Y(4)); W(0x0134); W(ST_AL_Y(4)); W(*CMPI_AL(SCAN_N)); BR(BNE, "SC_J")
W(*LDI_AL(SCAN_N)); W(0xF60F)

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


# ---------------------------------------------------------------------- TICK: AL = source, AH = tick index k (0..NT-1); returns AL = the id to speak
# k 0 = START (0x12), k NT-1 = END (0x13). Else kk = k - 1 = 3 r + q: row r (ROWDEF), q 0 = hi digit of j, 1 = lo digit, 2 = check = (hi + lo) mod 10.
# j = the first element index where the gram of the row's start is found (0..SCAN_N-1), or SCAN_N = none (value 10, id 0x31).
# The start: n x SourceDrop(64) (no SourceSize check: every start is far from the end of the 219,528-byte file), one SourceDrop(x) if x != 0, then a FRESH SourceMap (or, for an OLD row, the map taken BEFORE the drops).
# Slots (frame -12): 2 source, 3 k / kk / q, 4 r, 5 PT pointer / row pointer, 6 n, 7 map pointer, 8 j / lo, 9 temporary / hi.
LBL("TICK")
W(0xF40B)
W(ST_AL_Y(2)); W(ST_AH_Y(3))
W(LD_AL_Y(3)); W(CMP0); BR(BNE, "TK_K1")
W(*LDI_AL(ID_START)); W(0xF40F)
LBL("TK_K1")
W(*CMPI_AL(NT - 1)); BR(BNE, "TK_K2")
W(*LDI_AL(ID_END)); W(0xF40F)
LBL("TK_K2")
W(0xFF34); W(ST_AL_Y(3))                                 # kk = k - 1
W(0x0014); W(ST_AL_Y(4))                                 # r = 0
LBL("RQ")
W(LD_AL_Y(3)); W(*CMPI_AL(3)); BR(BCS, "RQ_DONE")        # kk < 3: q = kk
W(0xFD34); W(ST_AL_Y(3))
W(LD_AL_Y(4)); W(0x0134); W(ST_AL_Y(4)); BR(BRA, "RQ")
LBL("RQ_DONE")
LBL("SETAHPT")
W(0x0000, 0x0010)               # ld AH,#<data addr of PT> (patched below)
W(ST_AH_Y(5))
W(LD_AL_Y(5)); W((4 << 8) | 0x37); W(ST_AL_Y(5))         # PT + r
W(LD_X_Y(5)); W(LD_AL_X(0)); W(ST_AL_Y(5))               # the row pointer
W(LD_X_Y(5)); W(LD_AL_X(0)); W(ST_AL_Y(6))               # n
W(LD_AL_Y(4)); W(*CMPI_AL(OLD_ROW)); BR(BNE, "TK_DR")  #OLD
ca.call1(W, BSR, SOURCEMAP, al=('slot', 2)); W(CMP0); BR(BNE, "TK_MO"); W(*LDI_AL(ID_NOMAP)); W(0xF40F)  #OLD
LBL("TK_MO")  #OLD
W(ST_AL_Y(7))  #OLD an OLD row: the map BEFORE the drops
LBL("TK_DR")
W(LD_AL_Y(6)); W(CMP0); BR(BEQ, "TK_XD")
LBL("DR_TOP")
ca.call2(W, BSR, SOURCEDROP, al=('slot', 2), ah=('imm', PERIOD))
W(LD_AL_Y(6)); W(0xFF34); W(ST_AL_Y(6)); W(CMP0); BR(BNE, "DR_TOP")
LBL("TK_XD")
W(LD_X_Y(5)); W(LD_AL_X(1)); W(0xFF34); W(CMP0); BR(BEQ, "TK_MAP"); W(ST_AL_Y(9))      # the extra drop is stored +1 (no stray 0x0E word in the cave)
ca.call2(W, BSR, SOURCEDROP, al=('slot', 2), ah=('slot', 9))
LBL("TK_MAP")
W(LD_AL_Y(4)); W(*CMPI_AL(OLD_ROW)); BR(BEQ, "TK_SC")  #OLD
ca.call1(W, BSR, SOURCEMAP, al=('slot', 2)); W(CMP0); BR(BNE, "TK_MF"); W(*LDI_AL(ID_NOMAP)); W(0xF40F)     # a FRESH map at the window start
LBL("TK_MF")
W(ST_AL_Y(7))
LBL("TK_SC")
W(LD_AL_Y(5)); W(0x0234); W(ST_AL_Y(9)); W(LD_AH_Y(9)); W(LD_AL_Y(7)); BSR("SCAN")
W(ST_AL_Y(8))
W(*CMPI_AL(SCAN_N)); BR(BEQ, "TK_NONE")
W(0x0014); W(ST_AL_Y(9))                                 # hi = 0
LBL("DV")
W(LD_AL_Y(8)); W(*CMPI_AL(10)); BR(BCS, "DV_DONE")
W(0xF634); W(ST_AL_Y(8)); W(LD_AL_Y(9)); W(0x0134); W(ST_AL_Y(9)); BR(BRA, "DV")
LBL("DV_DONE")
W(LD_AL_Y(3)); W(CMP0); BR(BEQ, "V_HI")
W(*CMPI_AL(1)); BR(BEQ, "V_LO")
W(LD_AL_Y(9)); W((8 << 8) | 0x37); W(*CMPI_AL(10)); BR(BCS, "TK_OUT")      # q 2: (hi + lo) mod 10
W(0xF634); BR(BRA, "TK_OUT")
LBL("V_HI")
W(LD_AL_Y(9)); BR(BRA, "TK_OUT")
LBL("V_LO")
W(LD_AL_Y(8)); BR(BRA, "TK_OUT")
LBL("TK_NONE")
W(*LDI_AL(10))                                           # none -> value 10 -> id 0x31
LBL("TK_OUT")
W(0x2734); W(0xF40F)                                     # add AL,#0x27 ; leavel -12



# ---- where the dead-code region starts: a function is never split between the window and the region (the
# only cross-area form Bose uses is `bsr`; a 3-word conditional branch is refused below), so the region marker goes
# BEFORE a whole function. Everything from REGION_AT on is cold code entered only by `bsr`.
REGION_AT = 'SCAN'                # window: TRIG, string, two tables, HANDLER, ARM, SENDLATER, OPENSRC; region: EXT, SCAN, TICK (found by a layout search)
_k = [i for i, it in enumerate(prog) if it[0] == "label" and it[1] == REGION_AT][0]
prog.insert(_k, ("region",))

# ---- informational: estimated words per function (bsr to a stock address = 3 words, to a label = 2, br = 1)
_cur, _sizes = None, {}
for _it in prog:
    if _it[0] == "label" and _it[1] in ("TRIG", "HANDLER", "ARM", "SENDLATER", "OPENSRC", "SCAN", "TICK"):
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
def _data_addr(base):
    return (CONST_BASE + (base - CONST_ORIGIN)) & 0xFFFF
for _i, (_n, _x, _old, _P) in enumerate(ROWDEF):
    _b = label_addr["ROW%d" % _i]
    assert [out.get(_b + _k) for _k in range(4)] == [_n, _x + 1, GRAMS[_i][0], GRAMS[_i][1]], ('row %d is not contiguous' % _i)
    out[label_addr["PT"] + _i] = _data_addr(_b)
_str_ptr('PT', [_data_addr(label_addr["ROW%d" % _i]) for _i in range(NR)], 'SETAHPT', nul=False)
# probe172: the stubs ride along ONLY when cave code is in the region; this image puts
# nothing there, so the seven dead functions stay byte-for-byte stock.
if any(caveguard.region_fn(_a) is not None for _a in out):
    for _a, _v in REGION_STUBS.items():
        assert _a not in out, hex(_a)
        out[_a] = _v
for _lbl in ["HANDLER", "STRFILE", "PT"] + ["ROW%d" % _i for _i in range(NR)]:   # probe179: the handler's FIRST instruction stays in the window; probe196: so do both stubs
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
