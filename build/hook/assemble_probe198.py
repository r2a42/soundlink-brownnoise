#!/usr/bin/env python3
"""probe198: step R3 of route M1 (docs/deep/material-2026-10-13/M1-graw.md section 6.2, row R3): the AT-SCALE p2 write of the
brown-noise payload, staged in data_us. PREPARATION ONLY: not flash-cleared, no independent review, owner decision pending.
Note, gates, press page draft: docs/deep/material-2026-10-13/R3-probe198.md.

## WHAT IT DOES (built on probe197's engine: hook 0x00e46, guard {3,13}, consume lever, ticks, ids, the 0xD3 stub)
  PRESS (centre LONG): STOP if a tick is pending, else arm TW; the lever consumes the event (as probe197).
  TICK 0x12 (TW):  sinkState guard -> open data_us (FileFind NowSpeakTTS, FileFind data_us, StreamFileSource) -> PREP: skip
         START_PERIOD x SourceDrop(64) to the staged span, then the PRE-ERASE LOOK (the first 4 staged bytes must equal the
         payload's: a stock data_us has other bytes there and the image refuses BEFORE the erase) -> StreamPartitionOverwriteSink
         (THE ERASE of all of p2) -> GLOOP: 2,106 periods of SourceMap / SinkMap / SinkClaim(28, offset bounded) / memmove(28,
         from map element 18) / SinkFlush(28) / SourceDrop(64) -> SourceClose -> digest SKIP -> SinkClose -> ONE spoken id.
         V09 D1: GLOOP reads VmGetClock once per period and ABORTS (code 6, sink closed, digest SKIP, id 0x12) when more than
         15,000 ms have passed, or more than 1,000 ms after the first 100 periods (a flash slower than 10 ms per program).
  (NO read-back tick in this variant: the cave cannot hold it, see the note section 5; the write result is the
   one spoken id and the read-back is the first job of the next image.)

## THE PAYLOAD: 58,968 bytes of IMA ADPCM = 28 x 2,106 (raw, no ROFS wrapper), tools/brownnoise.py --rate 8000 --bytes 58968 --gen fft
## --loop --peak 0.985 --seed 63 (sha256 in the note). Staged at data_us period 1,320 (bytes 18..45 of each 64): it spares the
## region-A header, the E6 array and the region-B tail; only region A's body is rewritten. 14.742 s per chunk at 8 kHz.
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

STAGE_TW, STAGE_TV = 0x12, 0x13
PRESS_DELAY = 2000
STAGE_MS = 10000
SINKSTATE = 0x59E

# ---- the payload and its staging (pinned recipe; regenerated and checked at build time)
PAYLOAD_BYTES = 58968
PAYLOAD_SEED = 63
PAYLOAD_PEAK = 0.985
PAYLOAD_SHA = '1dc9dac050481af1bf398e3f99a82c2bbf605b821c2fee9b7b4bad8328afb968'
CHUNK = 28
PERIODS = PAYLOAD_BYTES // CHUNK          # 2106
assert PERIODS * CHUNK == PAYLOAD_BYTES
START_PERIOD = 1320                       # the first start that spares the region-A header (narrow184_lib.header_a_hits)
PERIOD = 64
MAPOFF = 18                               # map elements 18..45 of each 64-byte data_us period (narrow184_lib: FIRST_WORD 9)
DIRNAME, FILENAME = "NowSpeakTTS", "data_us"

# ---- spoken ids (docs/request-id-catalog.md). Disjoint per tick.
ID_GUARD, ID_OPENFAIL, ID_WFAIL, ID_WRITTEN = 0x3C, 0x3A, 0x19, 0x26      # as probe197 (0x26: written and closed, no timing)
ID_NOSRC, ID_NOWIN, ID_NOLOOK = 0x17, 0x28, 0x3B                          # before the erase: nothing was changed (V09 D3: ids HEARD on this unit)
ID_ABORT = 0x12                                                           # V09 D1: the time limit stopped the write; sink closed, short valid p2
ABORT_MS = 15000         # V09 D1: no healthy run takes this long (R2: 100 flushes + erase < 1 s; estimate 2 to 9 s for 2,106)
EARLY_PERIODS = 100      # after this many periods ...
EARLY_MS = 1000          # ... more than this many ms means a flash slower than 10 ms per page program (a tick of 21 s or more)
ID_H0, ID_PRIME_OK, ID_PRIME_BAD, ID_PRIME_SHORT = 0x27, 0x33, 0x30, 0x36   # TV (the proven 0xD3 read)

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
CMP0 = 0x0084                              # cmp AL,#0
BEQ, BNE, BCS, BCC, BRA = 0xF4, 0xF0, 0xFC, 0xF8, 0xE0

# ---- the payload, regenerated and checked against its pinned sha256 at build time (a changed generator fails loudly)
def _payload():
    import tempfile
    _cache = os.path.join('build', 'payload', 'r3', 'brown_8000_58968_s63.adpcm')
    if os.path.exists(_cache):                       # a cached copy is used ONLY if its sha256 is the pinned one
        _d = open(_cache, 'rb').read()
        if hashlib.sha256(_d).hexdigest() == PAYLOAD_SHA and len(_d) == PAYLOAD_BYTES:
            return _d
    with tempfile.TemporaryDirectory(prefix='r3_adpcm_') as td:
        out = os.path.join(td, 'p.adpcm')
        r = subprocess.run([sys.executable, os.path.join('tools', 'brownnoise.py'), '--rate', '8000', '--bytes', str(PAYLOAD_BYTES),
                            '--gen', 'fft', '--loop', '--peak', str(PAYLOAD_PEAK), '--seed', str(PAYLOAD_SEED), '--out', out],
                           capture_output=True, text=True, timeout=900)
        if r.returncode:
            raise SystemExit('brownnoise.py failed:\n' + r.stderr[-600:])
        data = open(out, 'rb').read()
    if hashlib.sha256(data).hexdigest() != PAYLOAD_SHA or len(data) != PAYLOAD_BYTES:
        raise SystemExit('payload sha256 %s != pinned %s' % (hashlib.sha256(data).hexdigest(), PAYLOAD_SHA))
    return data
PAYLOAD = _payload()
FIRST4 = list(PAYLOAD[:4])
print('payload %d bytes sha256 %s, first 4 bytes %s' % (len(PAYLOAD), PAYLOAD_SHA[:16], ' '.join('%02x' % b for b in FIRST4)))
# ---- the staging into data_us (narrow184_lib.stage: every edit byte blind and in file data, none twice, the span ends before
# fsedit's compensation slack, and a byte-per-element replay of the cave's gather over the EDITED data_us equals the payload)
sys.path.insert(0, 'build/hook')
import narrow184_lib as L
STG = L.stage(PAYLOAD, START_PERIOD)
assert STG['periods'] == PERIODS and STG['span'][1] <= L.DATA_US_SLACK
assert L.header_a_hits(PAYLOAD_BYTES, START_PERIOD) == 0, 'the staged span touches the region-A header'
print('staging: start period %d, data_us bytes %d..%d, %d edits (%d differ from stock); region-A header words hit: 0'
      % (START_PERIOD, STG['span'][0], STG['span'][1], len(STG['edits']), STG['changed']))

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

# --------------------------------------------------------------- the HANDLER (probe197's, two stages)
LBL("HANDLER")
W(0xF80B)
W(ST_AH_Y(4))
W(*CMPI_AH(STAGE_TW)); BR(BEQ, "DO_TW")
W(0xF80F)
LBL("DO_TW")
BSR("TW")                       # AL = the id to speak, AH = the next stage (0 = the chain ends)
W(ST_AL_Y(5))
W(ST_AH_Y(3))
BR(BRA, "FIN")
LBL("FIN")
W(LD_AL_Y(5))
BSR(SPEAK)
W(LD_AL_Y(3)); W(CMP0); BR(BEQ, "FEND")
W(*LDI_AL(STAGE_MS)); W(ST_AL_Y(4))
BR(BRA, "SENDLATER")
LBL("FEND")
W(0xF80F)

LBL("ARM")
W(0xF80B)
ca.call2(W, BSR, CANCELFIRST, al=('imm', TASK_ADDR), ah=('imm', STAGE_TW))
W(CMP0); BR(BNE, "STOP")
W(*LDI_AL(STAGE_TW)); W(ST_AL_Y(3))
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

# ---------------------------------------------------------------------- TW: guard, open data_us, skip + look, erase, gather+write, close
# Frame slots: 2 sink, 3 source, 4 digest result, 5 the loop status / the id kept across SourceClose.
# Returns AL = the id to speak, AH = the next stage (STAGE_TV after a close, 0 when nothing was erased and the chain ends).
LBL("TW")
W(0xF80B)
W(*ca.imm_words(SINKSTATE, 0x15))
W(*CMPI_AL(13)); BR(BEQ, "TW_GOK")
W(*CMPI_AL(3)); BR(BNE, "TW_REFUSE")
LBL("TW_GOK")
BSR("OPENSRC")                  # AL = the data_us source, 0 = refused
W(ST_AL_Y(3))
W(CMP0); BR(BEQ, "TW_NOSRC")
BSR("PREP")                     # AL = 0 ready, else THE ID TO SPEAK (ID_NOWIN: the window offered < 64 bytes; ID_NOLOOK: the marker is absent)
W(CMP0); BR(BNE, "TW_ENDSRC")   # nothing was erased: close the source, speak, the chain ends
ca.call2(W, BSR, OVERSINK, al=('imm', 1), ah=('imm', 2))     # *** THE ERASE of all of p2 *** (the VM parks until done)
W(ST_AL_Y(2))
W(CMP0); BR(BEQ, "TW_OPENFAIL")
W(LD_AL_Y(3)); W(LD_AH_Y(2))
BSR("GLOOP")                    # AL = 0 or the failing step
W(ST_AL_Y(5))
ca.call1(W, BSR, SOURCECLOSE, al=('slot', 3))      # the source is closed on every path after the erase
ca.calln(W, BSR, SETDIGEST, al=('slot', 2), ah=('imm', 3), stack=[('imm', 0), ('imm', 0)], stage='AL')
W(ST_AL_Y(4))
ca.call1(W, BSR, SINKCLOSE, al=('slot', 2))
W(LD_AL_Y(5)); W(*CMPI_AL(6)); BR(BEQ, "TW_ABORT")     # V09 D1: the time limit stopped the write (the sink IS closed)
W(LD_AL_Y(5)); W(CMP0); BR(BNE, "TW_FAIL")
W(LD_AL_Y(4)); W(CMP0); BR(BEQ, "TW_FAIL")
W(0x0010); W(*LDI_AL(ID_WRITTEN)); W(0xF80F)
LBL("TW_ABORT")
W(0x0010); W(*LDI_AL(ID_ABORT)); W(0xF80F)
LBL("TW_FAIL")
W(0x0010); W(*LDI_AL(ID_WFAIL)); W(0xF80F)
LBL("TW_OPENFAIL")
W(*LDI_AL(ID_OPENFAIL))
LBL("TW_ENDSRC")                # AL = the id; nothing was erased; close the source, the chain ends
W(ST_AL_Y(5))
ca.call1(W, BSR, SOURCECLOSE, al=('slot', 3))
W(0x0010); W(LD_AL_Y(5)); W(0xF80F)
LBL("TW_NOSRC")
W(0x0010); W(*LDI_AL(ID_NOSRC)); W(0xF80F)
LBL("TW_REFUSE")
W(0x0010); W(*LDI_AL(ID_GUARD)); W(0xF80F)

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

# ---------------------------------------------------------------------- PREP: skip START_PERIOD periods, then the pre-erase look
# AL = source. Slots: 2 source, 3 periods left. Returns 0 ready / the id to speak (window < 64 / marker absent).
LBL("PREP")
W(0xF80B)
W(ST_AL_Y(2))
W(*LDI_AL(START_PERIOD)); W(ST_AL_Y(3))
LBL("PR_SKIP")
ca.call1(W, BSR, SOURCESIZE, al=('slot', 2))
W(*CMPI_AL(PERIOD)); BR(BCS, "PR_NOWIN")        # offered < 64
ca.call2(W, BSR, SOURCEDROP, al=('slot', 2), ah=('imm', PERIOD))
W(LD_AL_Y(3)); W(0xFF34); W(ST_AL_Y(3))
W(CMP0); BR(BNE, "PR_SKIP")
ca.call1(W, BSR, SOURCEMAP, al=('slot', 2))
W(CMP0); BR(BEQ, "PR_NOLOOK")
W(0x0127); W(0x011B)            # st AL,@(1,Y) ; ld X,@(1,Y)   (no trap in between)
for _k, _b in enumerate(FIRST4):
    W(((MAPOFF + _k) << 8) | 0x16); W(*CMPI_AL(_b)); BR(BNE, "PR_NOLOOK")
W(0x0014); W(0xF80F)
LBL("PR_NOWIN")
W(*LDI_AL(ID_NOWIN)); W(0xF80F)
LBL("PR_NOLOOK")
W(*LDI_AL(ID_NOLOOK)); W(0xF80F)

# ---------------------------------------------------------------------- GLOOP: 2,106 periods, gather + write
# AL = source, AH = sink. Returns 0 or 1 (SourceMap) / 2 (SinkMap) / 3 (SinkClaim, incl. offset >= 21) / 4 (SinkFlush) / 5 (window < 64)
# / 6 (V09 D1: the TIME LIMIT: elapsed > 15,000 ms at any period, or > 1,000 ms when 100 periods are done).
# Slots: 2 source, 3 sink, 4 periods left, 5 source pointer (map + 18), 6 sink map then destination, 7 clock (low word) at the
# loop start, 1 the elapsed time between two traps only. Frame -10. The clock is read ONCE per period (VmGetClock, 16 bits: the
# tick is bounded far below 65 s, so the modular difference is exact).
LBL("GLOOP")
W(0xF60B)                       # enterl -10
W(ST_AL_Y(2)); W(ST_AH_Y(3))
W(*LDI_AL(PERIODS)); W(ST_AL_Y(4))
BSR(VMCLOCK); W(ST_AL_Y(7))        # t0 (low word; AH = the high word is not needed)
LBL("GL_TOP")
BSR(VMCLOCK); W(0x0757); W(ST_AL_Y(1))                   # sub AL,@(7,Y): elapsed ms; kept in slot 1 until the next trap
W(*CMPI_AL(ABORT_MS)); BR(BCC, "GL_F6")                  # >= 15,000 ms: abort
W(LD_AL_Y(4)); W(*CMPI_AL(PERIODS - EARLY_PERIODS)); BR(BNE, "GL_GO")
W(LD_AL_Y(1)); W(*CMPI_AL(EARLY_MS)); BR(BCC, "GL_F6")  # 100 periods done and >= 1,000 ms: abort
LBL("GL_GO")
ca.call1(W, BSR, SOURCEMAP, al=('slot', 2))
W(CMP0); BR(BEQ, "GL_F1")
W((MAPOFF << 8) | 0x34); W(ST_AL_Y(5))                  # add AL,#18
ca.call1(W, BSR, SINKMAP, al=('slot', 3))
W(CMP0); BR(BEQ, "GL_F1")
W(ST_AL_Y(6))
ca.call2(W, BSR, SINKCLAIM, al=('slot', 3), ah=('imm', CHUNK))
W(0xFF84); BR(BEQ, "GL_F1")                             # 0xFFFF
W(*CMPI_AL(21)); BR(BCC, "GL_F1")                       # V07 D2: offset >= 21 refused
W(0x0637); W(ST_AL_Y(6))                                # add AL,@(6,Y) ; destination
W(*LDI_AL(CHUNK)); W(0x0027)                            # @(0,Y) = 28
W(LD_AH_Y(5)); W(LD_AL_Y(6))
BSR(MEMMOVE)
ca.call2(W, BSR, SINKFLUSH, al=('slot', 3), ah=('imm', CHUNK))
W(CMP0); BR(BEQ, "GL_F1")
ca.call1(W, BSR, SOURCESIZE, al=('slot', 2))
W(*CMPI_AL(PERIOD)); BR(BCS, "GL_F1")
ca.call2(W, BSR, SOURCEDROP, al=('slot', 2), ah=('imm', PERIOD))
W(LD_AL_Y(4)); W(0xFF34); W(ST_AL_Y(4))
W(CMP0); BR(BNE, "GL_TOP")
W(0x0014); W(0xF60F)
for _n in (1, 6):
    LBL("GL_F%d" % _n)
    W(((_n) << 8) | 0x14); W(0xF60F)

# ---- where the dead-code region starts: a function is never split between the window and the region (the
# only cross-area form Bose uses is `bsr`; a 3-word conditional branch is refused below), so the region marker goes
# BEFORE a whole function. Everything from REGION_AT on is cold code entered only by `bsr`.
REGION_AT = 'OPENSRC'             # window: TRIG, stub, HANDLER, ARM, SENDLATER, TW; region: WLOOP, TV
_k = [i for i, it in enumerate(prog) if it[0] == "label" and it[1] == REGION_AT][0]
prog.insert(_k, ("region",))

# ---- informational: estimated words per function (bsr to a stock address = 3 words, to a label = 2, br = 1)
_cur, _sizes = None, {}
for _it in prog:
    if _it[0] == "label" and _it[1] in ("TRIG", "STUB_D3", "HANDLER", "ARM", "SENDLATER", "TW", "OPENSRC", "PREP", "GLOOP", "TV"):
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
    words = [ord(c) for c in text] + ([0] if nul else [])
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
# probe172: the stubs ride along ONLY when cave code is in the region; this image puts
# nothing there, so the seven dead functions stay byte-for-byte stock.
if any(caveguard.region_fn(_a) is not None for _a in out):
    for _a, _v in REGION_STUBS.items():
        assert _a not in out, hex(_a)
        out[_a] = _v
for _lbl in ("HANDLER", "STRFILE"):   # probe179: the handler's FIRST instruction stays in the window; probe196: so do both stubs
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
    "# %d cave/redirect byte edits + %d staged data_us byte edits go through fsedit.build() in-process\n"
    "# (too many for one --edit command line); output %s\n"
    % (_PROBE, len(_cave_edits), len(STG['edits']), _dfu))
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
    _edits += STG['edits']
    assert len({o for o, _ in _edits}) == len(_edits), 'an area byte is edited twice (cave vs payload)'
    _fsc["build"](_edits, _dfu)
    # independent check of the BUILT image: replay the cave's gather over the data_us bytes in the DFU itself
    _d = open(_dfu, 'rb').read()
    _ia = _d.find(b'fsr_dfu1')
    _us = _d[_ia + STG['area0']:_ia + STG['area0'] + 219528]
    _got = bytearray()
    for _p in range(PERIODS):
        _b = PERIOD * (START_PERIOD + _p) + MAPOFF
        _got += _us[_b:_b + CHUNK]
    assert bytes(_got) == PAYLOAD, 'DFU gather replay != the payload'
    print('built %s: gather replay over the DFU = the payload (%d bytes), sha256 %s'
          % (_dfu, len(PAYLOAD), hashlib.sha256(_d).hexdigest()))
else:
    print("edit lists ready (%d cave/redirect byte edits, %d staged data_us byte edits); "
          "run with --build to assemble %s" % (len(_cave_edits), len(STG['edits']), _dfu))
