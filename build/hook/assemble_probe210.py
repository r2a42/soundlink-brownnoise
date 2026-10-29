#!/usr/bin/env python3
"""probe195: an UNBOUNDED loop with a STOP. Delayed start, 50 ms seam polls, constant poll id 0x12, MessageCancelFirst on the press.

(Built offline on 2026-10-13, owner home. Standing owner instruction: "prepare the next probe and flash when
ready, following the documented procedure." Flashed ONLY by tools/flash_probe.py with every FLASH-PROTOCOL
gate. Base: probe194 (gapless seams proven) with probe180's STOP design.)

## WHY (probe194 press, owner words: "3 chunks, no discernable gap but I can hear the seam. all the same level.
## ended after the 3rd chunk.") The gap is closed; the loop must now run until the owner stops it.

## THE IMAGE
  PRESS (centre long, event 0x4004), in this order:
    MessageCancelFirst(task, 0x12): TRUE -> a poll was pending, i.e. the loop is RUNNING (or the first tick is
      pending): this press is a STOP. Nothing else is touched, nothing is spoken (port 3 is ours). The chunk in
      flight plays out (at most 2.6 s) and then there is silence, because the poll that would rebuild it is gone.
    FALSE -> a START: StreamKalimbaSink(3) + READ-ONLY TransformFromSink; busy -> nothing; free ->
      MessageSendLater(task, 0x12, 0, 1000 ms). The press itself is silent (the stock beep still plays).
  TICK (HANDLER), id 0x12 always: sink read; busy -> re-arm 0x12 in 50 ms; free -> GATE = 0x1072 (8000 Hz,
    b = 2) + the shift poke (proven in probe192-194; FALSE = the DSP is gone -> 0x21 "call ended", the loop
    ends), then BUILD and re-arm 0x12 in 2450 ms. FOREVER: no counter, no "ended".
  Every message this cave sends carries the id 0x12 that the STOP cancels (probe180's rule).
  Refusal ids as probe194 (0x10 0x22 0x1B 0x24 0x25; 0x21 when the DSP is gone). Each of them ENDS the loop with
  a spoken id (nothing is re-armed), which is also how any hidden limit would show (probes 150/151 saw object
  creation refused after about 55 ticks: unresolved; the file source of every chunk is never closed).

## NOT OBSERVED before this probe: MessageCancelFirst called from a cave on a cave message (probe180's
## hypothesis, never flashed); an unbounded run. FAILURE MODES by the header: FALSE for a pending message = the
## STOP press falls into the START ladder, where the busy port makes it do nothing (the loop does not stop);
## TRUE with nothing pending = the START presses do nothing. Neither touches port 3.

## THE PRESS PAGE (owner present; speaker volume DOWN; laptop connected; music PLAYING; USB UNPLUGGED after the
## readback so that POWER can force the speaker off). Centre LONG presses, in this order (the PD-02 exception
## for a silent-success image: START, STOP, START, STOP; wait for the stated events between them):
  1 START: beep, ~1 s silence, then chunk after chunk with no gap. Let it run about 30 s (about 11 chunks).
  2 STOP: press ONCE at any moment. Expect: the chunk in flight finishes, then SILENCE (music only).
  3 wait 5 s of silence, START again (the same as 1; a loop that restarts proves the STOP left no state).
  4 STOP again at any moment in the next 10 s.
    loops, STOP stops, START restarts, STOP stops  -> success
    STOP does nothing (the loop continues)         -> MessageCancelFirst found nothing; use a kill switch
    the loop stops by itself with a spoken id      -> a limit: say WHICH id and how many seconds (0x10, 0x22,
                                                      0x1B, 0x24, 0x25, 0x21), this is the leak/limit result
    a gap or a different level after many chunks   -> say when
    a RESTART / buzz / silence at the start        -> note when, do not press again
Kill switches (in order): STOP (the thing under test); Bluetooth long press (tears down A2DP and the DSP);
PAUSE the music (the DSP unloads, the next tick ends the loop with 0x10 or 0x21); POWER off with USB unplugged.
"""

import os, re, sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

_PROBE = re.match(r'assemble_(probe[0-9a-z]+)\.py$',
                  os.path.basename(os.path.abspath(__file__))).group(1)

# Declared for tools/caveguard.attest_trap_stubs (it parses these two module-level literals with ast).
SYNTH_TRAPS = [0xD3]       # PartitionGetRawSerialSource: no stub in vm.app (proven to dispatch by probes 196 and 197)
SYNTH_CONTROLS = []

CAVE = 0x3E21D
def LD_X_Y(n): return (n << 8) | 0x1B     # ld X,@(n,Y)
def LD_AL_X(n): return (n << 8) | 0x16    # ld AL,@(n,X)
# probe172: the hook moves to 0x00e46 (`bsr fn_189fb`, 3-word bsr, operand bytes 01 7c b3
# at area bytes 0x706bd/0x706bf/0x706c1); the opcode byte 0x9c and the low bytes stay.
# 0x0AE0 is NOT edited: the Bluetooth long press is stock again. The values are asserted
# below against the bsr3 encoding of CAVE from 0x00e46.
HOOK = 0x00E46
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
AREA0 = 0x6EA30
CONST_BASE = 0x7400                     # data addr of code word 236514 (0x39BE2)

BACK = 0xE06D
SPEAK = 0xDF7F
FILEFIND = ca.STUB['FileFind']
FILESRC = ca.STUB['StreamFileSource']
SOURCEMAP = ca.STUB['SourceMap']
SOURCECLOSE = ca.STUB['SourceClose']
SINKSLACK = ca.STUB['SinkSlack']
KALMSG   = ca.STUB['KalimbaSendMessage']
KSINK    = ca.STUB['StreamKalimbaSink']
ADPCM    = ca.STUB['TransformAdpcmDecode']
TSTART   = ca.STUB['TransformStart']
RATE     = 8000          # probe190: THE ONE CHANGE (probe179 sent 2000). 0x1072 word a.
SDISC    = ca.STUB['StreamDisconnect']
MSGLATER = ca.STUB['MessageSendLater']
KALLOAD  = ca.STUB['KalimbaLoad']
KALTASK  = ca.STUB['MessageKalimbaTask']   # 0x1cd: route DSP messages to a task
KALPOFF  = ca.STUB['KalimbaPowerOff']      # 0x1be: the teardown's own call (0x317d9)
KALLONG  = ca.STUB['KalimbaSendLongMessage']  # 0x1c8 (probe168)
KAPPATH  = 'sbc_decoder/sbc_decoder.kap'   # the FIRMWARE'S own const-pool
                         #   copy; probe154 established it and the build
                         #   below re-finds it, so no carried string and
                         #   therefore no band-split hazard
TASK_ADDR = 0xBA3C       # const_addr(CAVE+1): the TaskData lives at
                         #   CAVE+1, CAVE+2, exactly as probes 145-151
                         #   had it -- the dispatch path those probes
                         #   proved on hardware
POLL_MS = 1000           # probe179: the poll period for PROVING (DESIGN: floor 50 ms; 1000 ms
                         #   keeps the gap between chunks audible and the load on the loop low)
CHAIN = 4                # the press arms BUILD with slot 4 = CHAIN, so the first tick carries
                         #   id CHAIN - 1 = 3: chunks 2 and 3 are rebuilt at ids 3 and 2, id 1 ends
POLL_ID = 0x0012         # probe195: the ONE MessageId this cave ever sends to its TaskData (the STOP cancels it)
CANCELFIRST = ca.STUB['MessageCancelFirst']   # 0x66: cancel the first pending message of (task, id)
PRESS_DELAY = 1000       # press -> first tick (as probe193)
FIRST_POLL = 14500       # probe209: build -> first poll; the chunk is 2 x 58,968 / 8,000 = 14,742 ms (probe194 used 2450 for the 2,622 ms chunk: 172 ms early)
POLL_SHORT = 50          # probe194: busy -> re-arm (the project floor, rule R5)
SKIP_GATE_ID = 2         # probe194: the tick with this id rebuilds WITHOUT 0x1072 and the poke
OVERSINK = ca.STUB['StreamPartitionOverwriteSink']
SETDIGEST = ca.STUB['PartitionSetMessageDigest']
SINKCLOSE = ca.STUB['SinkClose']
SINKFLUSH = ca.STUB['SinkFlush']
MEMMOVE = ca.STUB['memmove']
FN12E1A = 0x12E1A
FN1F12B = 0x1F12B                       # AudioOutputDisconnect (stock prompt teardown, fn_231b3)
FN1F04C = 0x1F04C                       # audio_output connect (docs/deep/dsp-output-wiring.md)                       # Bose's SinkMap+SinkClaim helper (stock)
MEMMOVE = ca.STUB['memmove']

PERIOD = 32
FIRST = 11
PER_PERIOD = 14
PERIODS = 1180
INNER = 59                              # 20 x 59 = 1180
OUTER = 20
CHUNK_BYTES = PER_PERIOD * 2            # 28

w = xapvm.load_words("firmware/bose/extracted/internal_fs/vm.app")
code = w[0x18:]
# ---- the .kap path lives in the FIRMWARE'S const pool: find it and address it
_kp = [ord(c) for c in KAPPATH]
_kh = [i for i in range(len(code) - len(_kp))
       if code[i] == _kp[0] and list(code[i:i + len(_kp)]) == _kp]
assert _kh, 'the .kap path %r is NOT in vm.app\'s const pool' % KAPPATH
KAP_CODE = _kh[0]
KAP_DATA = (CONST_BASE + (KAP_CODE - 236514)) & 0xFFFF
assert 0x7400 <= KAP_DATA <= 0xD39A, (hex(KAP_CODE), hex(KAP_DATA))
_klo = KAP_DATA & 0xFF
_khi = ((KAP_DATA >> 8) + (1 if _klo >= 0x80 else 0)) & 0xFF
_ksx = lambda b: b - 256 if b >= 0x80 else b
assert (_ksx(_khi) * 256 + _ksx(_klo)) & 0xFFFF == KAP_DATA, (
    'the prefixed ld AH for the .kap path does not fold back: %#06x'
    % ((_ksx(_khi) * 256 + _ksx(_klo)) & 0xFFFF))
_KAP_AH = ((_khi << 8) | 0x00, (_klo << 8) | 0x10)
print('DSP reload path %r: pool copy at code %#x -> data %#06x (ld AH %04x %04x), '
      '%d words' % (KAPPATH, KAP_CODE, KAP_DATA, _KAP_AH[0], _KAP_AH[1], len(KAPPATH)))

# ---- probe162: "NowSpeakTTS" from the firmware's const pool (no NUL needed: FileFind
# takes the length). Pick the first copy whose prefixed ld AH folds back.
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

# ---- two SHORT carried strings, each emitted as ONE item so the layout cannot
# split it, and each asserted contiguous after layout. The cave's blind bands
# measure 14, 9 and 3 words, so "NowSpeakTTS/data_us" (20 words with its NUL)
# CANNOT fit in one band -- hence the two-level walk. file.h:18-28 supports it:
# FileFind takes the directory to start from, and FILE_ROOT is 1.
GETBUSY, SETBUSY = 0x2F9F2, 0x2F9FB   # stock GetAudioBusy / SetAudioBusy(task): the word AudioBusyPtr() (fn_2f9f7) points at; the plugin disconnect is sent conditionally on it (audio.c)
RID1, RID2, RID3 = 0x13, 0x14, 0x15   # the level-restore ticks after a STOP: poke only, no 0x1072 (no purge); +300 ms, +1000 ms, +2500 ms
RD1, RD2, RD3 = 300, 700, 1500        # delays: STOP -> 0x13, 0x13 -> 0x14, 0x14 -> 0x15
ID_NOPRIME = 0x3B   # "adjust airbuds" (heard): the first four bytes of the raw source are not the payload's `77 7f 77 c6`: nothing started, the source closed
FIRST4 = (0x77, 0x7F, 0x77, 0xC6)   # build/payload/r3/brown_8000_58968_s63.adpcm bytes 0..3 (asserted below)

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
TFROMSINK = ca.STUB['TransformFromSink']
TSTOP     = ca.STUB['TransformStop']
TDISC     = ca.STUB['TransformDisconnect']
prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))
def REGION(): prog.append(("region",))   # unused in probe174: everything fits the window
# ------------------------------------------------------------------ the TRIGGER
# probe172, proven on hardware: entered from 0x00e46 in fn_00846 (enterl -23) with AL = the
# event. 0x4004 = a CENTRE LONG PRESS while connected -> ARM, event swallowed. Every other
# event: fn_189fb replayed with AL restored, the stock call.
LBL("TRIG")
W(0xF80B)                       # enterl -8
W(0x0027)                       # st AL,@(0,Y)  the event id
W(*ca.imm_words(0x4004, 0x84))  # cmp AL,#0x4004
BR(0xF0, "PASS")                # bne -> not ours: replay
BSR("ARM")                      # start a chunk, or stop the running one
W(0xF80F)                       # leavel -8: the voice-dial event is swallowed
LBL("PASS")
W(0x0017)                       # ld AL,@(0,Y)  the event back in AL
BSR(FN189FB)                    # the stock call, replayed (0x00e49 reloads AL after it)
W(0xF80F)                       # leavel -8

# ---- the SYNTHESISED stub for trap 0xD3 (probe196 words, proven to dispatch on the speaker): ONE item, ends in 0xE1
LBL("STUB_D3")
W(*ca.synth_stub_words(0xD3))

# --------------------------------------------------------------- the HANDLER
# probe179: dispatched through the TaskData at CAVE+1/CAVE+2 by the 1 s poll the press (and
# every rebuild) arms. AL = task, AH = the MessageId = the chain counter (3, 2, 1). Every
# trap below clobbers AH, so it is saved in frame slot 4 at once and read back from there.
# The first instruction is in the const window (asserted below); everything after it may
# spill. The handler shares BUILD's frame (enterl -8) and enters BUILD with slot 4 = id and
# slot 2 = ksink, exactly the state the press leaves.
LBL("HANDLER")
W(0xF80B)                       # enterl -8
W(0x0423)                       # st AH,@(4,Y)  the MessageId
W(0x0417)                       # ld AL,@(4,Y)
W(*ca.imm_words(POLL_ID, 0x84)); BR(0xF4, "HNORM")   # cmp AL,#0x12 ; beq -> the loop's poll
BSR("HREST")                    # any other id (0x13..0x15): a level-restore tick after a STOP (AL = the id)
W(0xF80F)                       # leavel -8
LBL("HNORM")
ca.call1(W, BSR, KSINK, al=('imm', 3))
W(0x0227)                       # st AL,@(2,Y)  ksink
W(0x0084); BR(0xF4, "NOSINK")   # 0 -> 0x10 "and": the loop ends here, nothing re-armed
BSR(TFROMSINK)                  # READ-ONLY. AL = ksink still (st and cmp leave it)
W(0x0084); BR(0xF4, "HFREE")    # 0 -> the port is free
# ---- busy: the chunk still holds port 3. Re-arm id POLL_ID in 50 ms and touch nothing else.
W(*ca.imm_words(POLL_SHORT, 0x14)); W(0x0327)    # delay -> slot 3
BR(0xE0, "REARM")
LBL("HFREE")
BSR("GATE")                     # 0x1072(8000, b = 2) + poke: TRUE iff a .kap is loaded
W(0x0084); BR(0xF4, "GONE")     # FALSE -> the DSP went away at the seam: 0x21, no re-arm
BR(0xE0, "BUILD")               # rebuild; BUILD re-arms POLL_ID
LBL("GONE")
W(0x2114)                       # ld AL,#0x21 "call ended": distinct from START's 0x3E
BR(0xE0, "SAY")

# ---------------------------------------------------------------------- ARM
# ONE chain per press, and nothing is ever done to a port that is busy. Unchanged from
# probe178 up to the gate; then slot 4 = CHAIN and the shared BUILD runs.
#   ksink = StreamKalimbaSink(3)                 0 -> 0x10 "and"
#   t = TransformFromSink(ksink)   READ-ONLY     nonzero -> STOP: this press does nothing
#   GATE 0x1072 (TRUE iff a .kap is loaded)      FALSE -> 0x3E "bluetooth off"
#   BUILD -> FileFind, FileFind, StreamFileSource, TransformAdpcmDecode -> port 3,
#   TransformStart, MessageSendLater(task, id - 1, 0, POLL_MS), return.
LBL("ARM")
W(0xF80B)                       # enterl -8
ca.call2(W, BSR, CANCELFIRST, al=('imm', TASK_ADDR), ah=('imm', POLL_ID))
W(0x0084); BR(0xF0, "STOP")     # bne -> TRUE: a poll was pending: STOP. Nothing else is touched
ca.call1(W, BSR, KSINK, al=('imm', 3))
W(0x0227)                       # st AL,@(2,Y)  ksink
W(0x0084); BR(0xF4, "NOSINK")
BSR(TFROMSINK)                  # TransformFromSink(ksink): AL = the transform, or 0
W(0x0327)                       # st AL,@(3,Y)  t
W(0x0084); BR(0xF0, "STOP")     # bne -> port 3 is busy: this press does nothing
W(*ca.imm_words(PRESS_DELAY, 0x14)); W(0x0327)   # delay -> slot 3
BR(0xE0, "REARM")               # the press only arms the timer; the tick builds chunk 1
# ---- BUILD: shared by the press and the handler. Needs slot 2 = ksink, slot 4 = id.
LBL("BUILD")
ca.call2(W, BSR, "STUB_D3", al=('imm', 1), ah=('imm', 2))   # src = PartitionGetRawSerialSource(1, 2) through the proven 0xD3 stub; 0 = refused
W(0x0084); BR(0xF4, "NOSRC")
W(0x0527)                       # st AL,@(5,Y)  src
ca.call1(W, BSR, SOURCEMAP, al=('slot', 5))   # the pre-start check: SourceMap(src) -> the first bytes are the payload's
W(0x0084); BR(0xF4, "NOPRIME")
W(0x0127)                       # st AL,@(1,Y)  the map pointer (slot 1: no trap until the compares are done)
W(LD_X_Y(1))
for _k, _b in enumerate(FIRST4):
    W(LD_AL_X(_k)); W(*ca.imm_words(_b, 0x84)); BR(0xF0, "NOPRIME")   # ld AL,@(k,X) ; cmp AL,#byte ; bne -> mismatch
W(0x0517)                       # ld AL,@(5,Y)  src
W(0x0213)                       # ld AH,@(2,Y)  ksink
BSR(ADPCM)                      # t = TransformAdpcmDecode(src, ksink)
W(0x0084); BR(0xF4, "NOPLAY")
BSR(TSTART)                     # TransformStart(t)
W(0x0084); BR(0xF4, "NOPLAY")
W(*ca.imm_words(FIRST_POLL, 0x14)); W(0x0327)    # delay -> slot 3 (probe194: 2450 ms after a build)
# ---- REARM: MessageSendLater(cave task, slot 5, 0, POLL_MS) -- probe173's form verbatim:
# message slot 0, delay HIGH slot 1, delay LOW slot 2 (message-task-abi.md 1).
LBL("REARM")
W(0x0014); W(0x0027)            # message = 0          slot0
W(0x0127)                       # (AL still 0) delay high = 0   slot1
W(0x0317)                       # ld AL,@(3,Y)  the delay (probe194: set by the caller)
W(0x0227)                       # st AL,@(2,Y)  delay low (ksink is dead now)
W(*ca.imm_words(POLL_ID, 0x10))     # ld AH,#POLL_ID  the MessageId (always the one the STOP cancels)
W(*ca.imm_words(TASK_ADDR, 0x14))   # ld AL,#0xBA3C  the cave's TaskData
BSR(MSGLATER)
W(0xF80F)                       # leavel -8: the chunk plays, the poll is set

# ---- STOP: port 3 is busy on a PRESS: do NOTHING (probe176). probes 174/175 crashed stopping
# a running transform from here.
LBL("STOP")
BSR("STOPR")                    # arm the level-restore chain (region): the stock STOP-press reaction raised the level
W(0xF80F)                       # leavel -8

LBL("NOSINK")
W(0x1014)                       # ld AL,#0x10 "and": StreamKalimbaSink(3) returned 0
BR(0xE0, "SAY")
LBL("NOSRC")
W(0x2414)                       # ld AL,#0x24 "switching call": PartitionGetRawSerialSource (0xD3) returned 0
BR(0xE0, "SAY")
LBL("NOPRIME")
ca.call1(W, BSR, SOURCECLOSE, al=('slot', 5))
W(*ca.imm_words(ID_NOPRIME, 0x14))   # ld AL,#0x3B "adjust airbuds": nothing was started
BR(0xE0, "SAY")
LBL("NOPLAY")
W(0x2514)                       # ld AL,#0x25 "call with": the transform was refused
BR(0xE0, "SAY")
LBL("NODSP")
W(0x3E14)                       # ld AL,#0x3E "bluetooth off": no .kap loaded -- and FALL
                                #   into SAY, the next item
LBL("SAY")
BSR("SPEAKR")                   # probe210: release OUR audio-busy hold, then SPEAK AL (region wrapper)                      # probe99's direct idiom, hardware-proven; port 3 is free on
                                #   every path that reaches here
W(0xF80F)                       # leavel -8

# ---- probe193: the COLD part goes into the dead-code region (owner approved 2026-10-13). The window
# above ends with SAY's leavel (a terminator), as the region entry requires.
REGION()
TONE_B = 2
POKE_SHIFT = 5       # probe193: cbops.shift for the mono tone copy (4 = quiet, 7 = loud; 6 dB per step)
POKE_ADDR = 0x29E6      # M[0x29e6] = the mono tone-copy shift cell the 0x1072 handler writes (T02 E5/E23)
# ---- GATE: KalimbaSendMessage(0x1072 SET_TONE_RATE, 8000, TONE_B, 0, 0) -> bool in AL, through
# KSEND's own frame, then (if TRUE) the shift POKE KalimbaSendMessage(0x7AB3, M[0x29e6] := POKE_SHIFT).
LBL("GATE")
W(*ca.imm_words(RATE, 0x10))    # ld AH,#8000
W(*ca.imm_words(0x1072, 0x14))  # ld AL,#0x1072   ...and fall into KSEND
LBL("KSEND")
W(0xF80B)                       # enterl -8
W(0x0327)                       # st AL,@(3,Y)  the message id
W(*ca.imm_words(TONE_B, 0x14))  # ld AL,#2
W(0x0027)                       # st AL,@(0,Y)  b = 2        slot 0
W(0x0014)                       # ld AL,#0
W(0x0127); W(0x0227)            # c = d = 0                  slots 1..2
W(0x0317)                       # ld AL,@(3,Y)
BSR(KALMSG)
# ---- probe191: after a TRUE 0x1072, poke the mono tone-copy shift (M[0x29e6] := POKE_SHIFT) with
# KalimbaSendMessage(0x7AB3, addr lo = 0x29e6 | addr hi = 0, value lo = POKE_SHIFT, value hi = 0).
W(0x0084); BR(0xF4, "KDONE")    # cmp AL,#0 / beq: the 0x1072 was refused -> return FALSE as it was
W(0x0014)                       # ld AL,#0
W(0x0027)                       # st AL,@(0,Y)  addr hi = 0  slot 0
W(0x0227)                       # st AL,@(2,Y)  value hi = 0 slot 2
W(*ca.imm_words(POKE_SHIFT, 0x14))  # ld AL,#POKE_SHIFT
W(0x0127)                       # st AL,@(1,Y)  value lo     slot 1
W(*ca.imm_words(POKE_ADDR, 0x10))   # ld AH,#0x29e6  addr lo
W(*ca.imm_words(0x7AB3, 0x14))  # ld AL,#0x7AB3
BSR(KALMSG)                     # the poke; its result is ignored
BSR("HOLD")                     # probe210: SetAudioBusy(our task) when nothing holds it: a PAUSE then cannot release the plugin disconnect
W(0x0114)                       # ld AL,#1       TRUE: the tone message was accepted
LBL("KDONE")
W(0xF80F)

# ---- probe210: the level-restore chain after a STOP (cold code, region). Messages 0x13 -> 0x14 -> 0x15, each a POKE of the tone-copy shift cell
# (the proven probe191 poke; NOT 0x1072: it would purge the tone buffer mid-chunk). The chunk in flight plays out at the quiet level again.
LBL("HREST")                    # AL = the MessageId
W(0xF80B)                       # enterl -8
W(0x0427)                       # st AL,@(4,Y)  id
BSR("POKE")
W(0x0417)                       # ld AL,@(4,Y)
W(*ca.imm_words(RID3, 0x84)); BR(0xF8, "HREST_X")     # cmp AL,#0x15 ; bcc -> id >= 0x15: the chain ends
W(*ca.imm_words(RD2, 0x10))     # ld AH,#700
W(0x0417); W(*ca.imm_words(RID2, 0x84)); BR(0xF0, "HR_SEND")   # ld AL,@(4,Y) ; cmp AL,#0x14 ; bne -> keep 700
W(*ca.imm_words(RD3, 0x10))     # ld AH,#1500 (the id was 0x14)
LBL("HR_SEND")
W(0x0417); W(0x0134)            # ld AL,@(4,Y) ; add AL,#1 : the next id
BSR("RSEND")
LBL("HREST_X")
W(0xF80F)                       # leavel -8

# RSEND: AL = the MessageId, AH = the delay in ms. MessageSendLater(cave task, id, 0, delay) in probe173's form (REARM's).
LBL("RSEND")
W(0xF80B)                       # enterl -8
W(0x0427)                       # st AL,@(4,Y)  id
W(0x0323)                       # st AH,@(3,Y)  delay
W(0x0014); W(0x0027)            # message = 0          slot0
W(0x0127)                       # delay high = 0       slot1
W(0x0317); W(0x0227)            # delay low            slot2
W(0x0413)                       # ld AH,@(4,Y)  the MessageId
W(*ca.imm_words(TASK_ADDR, 0x14))   # ld AL,#0xBA3C  the cave's TaskData
BSR(MSGLATER)
W(0xF80F)                       # leavel -8

# POKE: KalimbaSendMessage(0x7AB3, M[0x29e6] := POKE_SHIFT): the level poke alone (KSEND's second half, probe191-209)
LBL("POKE")
W(0xF80B)                       # enterl -8
W(0x0014)                       # ld AL,#0
W(0x0027)                       # st AL,@(0,Y)  addr hi = 0
W(0x0227)                       # st AL,@(2,Y)  value hi = 0
W(*ca.imm_words(POKE_SHIFT, 0x14))  # ld AL,#POKE_SHIFT
W(0x0127)                       # st AL,@(1,Y)  value lo
W(*ca.imm_words(POKE_ADDR, 0x10))   # ld AH,#0x29e6  addr lo
W(*ca.imm_words(0x7AB3, 0x14))  # ld AL,#0x7AB3
BSR(KALMSG)
W(0xF80F)                       # leavel -8

# HOLD: SetAudioBusy(TASK_ADDR) when the decoder plugin exists (@0x72b nonzero) and nothing else holds the word (a stock prompt or tone does).
LBL("HOLD")
W(0xFE0B)                       # enterl -2
W(0x0700, 0x2B99)               # tst @0x72b
BR(0xF4, "HOLD_X")
BSR(GETBUSY)                    # AL = the audio-busy word
W(0x0084); BR(0xF0, "HOLD_X")   # nonzero: leave it
W(*ca.imm_words(TASK_ADDR, 0x14))
BSR(SETBUSY)
LBL("HOLD_X")
W(0xFE0F)                       # leavel -2

# STOPR: arm the restore chain: MessageSendLater(task, 0x13, 300 ms)
LBL("STOPR")
W(0xFE0B)                       # enterl -2
W(*ca.imm_words(RID1, 0x14))    # ld AL,#0x13
W(*ca.imm_words(RD1, 0x10))     # ld AH,#300
BSR("RSEND")
W(0xFE0F)                       # leavel -2

# SPEAKR: AL = a spoken id. Release OUR hold (AL preserved), then SPEAK it.
LBL("SPEAKR")
W(0xFE0B)                       # enterl -2
BSR("RELEASE")
BSR(SPEAK)
W(0xFE0F)                       # leavel -2

# RELEASE: AL = a spoken id (preserved). SetAudioBusy(0) only if the word is OUR task (never clear a stock prompt's hold).
LBL("RELEASE")
W(0xFC0B)                       # enterl -4
W(0x0127)                       # st AL,@(1,Y)  the id
BSR(GETBUSY)
W(*ca.imm_words(TASK_ADDR, 0x84)); BR(0xF0, "REL_X")
W(0x0014)
BSR(SETBUSY)
LBL("REL_X")
W(0x0117)                       # ld AL,@(1,Y)
W(0xFC0F)                       # leavel -4                       # leavel -8, and AL carries the bool out

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

# probe162: the region's stubs ride along in EVERY image that uses the region, and the
# things the cave READS (string, TaskData) must be in the const window.
CONST_ORIGIN = 236514
def _str_ptr(label, text, setah, nul=True):
    base = label_addr[label]
    words = [ord(c) for c in text] + ([0] if nul else [])
    for k, expect in enumerate(words):
        got = out.get(base + k)
        assert got == expect, (
            'string %r is NOT contiguous: word %d at %#x is %r, expected %r -- '
            'the layout split it across blind bands'
            % (text, k, base + k, got, expect))
    data = (CONST_BASE + (base - CONST_ORIGIN)) & 0xFFFF
    assert 0x7400 <= data <= 0xD39A, (text, hex(data))
    lo8 = data & 0xFF
    hi8 = ((data >> 8) + (1 if lo8 >= 0x80 else 0)) & 0xFF
    sx = lambda b: b - 256 if b >= 0x80 else b
    assert (sx(hi8) * 256 + sx(lo8)) & 0xFFFF == data, (
        'prefixed ld AH does not fold back for %r: hi=%02x lo=%02x -> %#06x, '
        'want %#06x' % (text, hi8, lo8, (sx(hi8)*256 + sx(lo8)) & 0xFFFF, data))
    assert 1 <= hi8 <= 0xFF, hex(data)
    a = label_addr[setah]
    out[a] = (hi8 << 8) | 0x00
    out[a + 1] = (lo8 << 8) | 0x10
    print('  %-12r %2d words, contiguous at code %#x -> data %#06x '
          '(ld AH %04x %04x)' % (text, len(words), base, data, out[a], out[a+1]))

# probe172: the stubs ride along ONLY when cave code is in the region; this image puts
# nothing there, so the seven dead functions stay byte-for-byte stock.
if any(caveguard.region_fn(_a) is not None for _a in out):
    for _a, _v in REGION_STUBS.items():
        assert _a not in out, hex(_a)
        out[_a] = _v
for _lbl in ("STUB_D3", "HANDLER"):   # probe179: the handler's FIRST instruction stays in the window
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
