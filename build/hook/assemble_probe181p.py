#!/usr/bin/env python3
"""probe181p: probe181 + POLL 200 ms. ONE change: the poll period in REARM, 1000 -> 200 (J-T11, 2026-10-12; built
offline, NOT flashed).

(docs/deep/firmware-study-2026-10-12/T11-product-build-and-press-pages.md section 3.1 is the full press page and
the reading ladder; docs/deep/strategy-2026-10-12/STRATEGY.md J-C6 / J-D4 / row 181p; T03 section 6.3 for the
number.  Flash it ONLY after probes 179, 180 AND 181 (with its 4-minute pulse run) have been pressed on the
speaker and their results recorded in docs/field-log.md: like 180 and 181 this image LOOPS WITHOUT AN END OF ITS
OWN, and its STOP is MessageCancelFirst, which has never run on hardware at the time of writing.)

## THE CHANGE (one immediate, two words in the image)

  probe181 armed its poll with `ld AL,#1000` in REARM.  probe181p arms it with `ld AL,#200`.  An immediate of
  1000 and one of 200 both need a prefix word plus the load (ca.imm_words), so the cave is still 174 words,
  0x3E21D..0x3E3E6, all in the const window, none in the region, and the layout is identical.  The build asserts
  against build/hook/probe181_words.json that exactly two words differ: 0x3E382 0x0400 -> 0x0100 and 0x3E383
  0xE814 -> 0xC814.  Everything else is probe181's byte for byte: the hook (0x00e46, operand bytes 04 d4 d5),
  STOP (MessageCancelFirst first), the busy read, GATE 0x1072(8000, b = 2) kept on every rebuild (J-C17: no skip
  until 181p has read c), POLL_ID 0x12, the stand-in material rphrases_us (10,486 bytes), and the spoken ids.
  This file is assemble_probe181.py with POLL_MS = 200, this docstring and the delta assertion.

## WHY 200 ms (T03 section 6, model; every parameter below is assumed, none measured)

  The 1000 ms proving seam is about 386 ms whatever the lead L is (the chunk is 2621.5 ms, the tick grid is
  1000 ms).  At 200 ms the model puts the seam at the purge-made silence c - h1072 (20 ms at the default rebuild
  latency c = 21 ms, 3 ms at a low-c bracket) for any lead L from about 25 to 225 ms, a pure splice of 16-32 ms
  of cut tail above L about 245 ms, and a 200 ms tick-limited gap below L about 25 ms.  So the gap the owner hears
  READS c, not L (T03 6.2).  13 busy reads per chunk (probe181: 2).  50 ms would reach the 55-tick mark of probes
  150/151 inside chunk 2 and is the LAST step, not the first (J-C6, 03 M2).

## WHAT THE MODEL SAYS THE SPEAKER SHOULD DO (cavesim world, zero VM latency; build/hook/gate_probe181p.py)

  chunk 2622 ms; the first tick at or after the free edge is the next multiple of 200 ms from the (re)arm, so
  chunks start at 0, 2800, 5600 ms, ... (period 2.8 s, 21.4 a minute), silence 178 ms, ONE poll pending, nothing
  spoken.  With a lead L above 22 ms the tick at 2600 ms already finds the port free: period 2.6 s (23 a minute),
  and the 0x1072 + rebuild land inside the audible tail (cavesim rules R1 + R4, the ACCEPTED hazard rows of
  probes 179-181, now the NORMAL case at every seam).  What the speaker does with that is the question.

## THE PRESS PLAN (speaker volume DOWN; laptop connected; music PLAYING; no call application open; USB UNPLUGGED
## after the readback; Bluetooth button in reach; a stopwatch; a phone recording the speaker if possible)

  1. centre LONG = START.  Listen 60 s by the stopwatch.  Per seam write: silence (none / a tick or click about
     20 ms / a short gap about 0.2 s / longer), a click or a level step, and the time of any larger dropout.
     Count the pulses in the 60 s (21 = 2.8 s period, 23 = 2.6 s period; the chunk length is not measured, the
     owner's ear put the first chunk at about 14 percent longer than the arithmetic, verify V5).  Compare chunk 1
     with chunks 2 and 3.
  2. Keep listening to 4 minutes in all (about 86 chunks, 1,150 busy reads): any 0x24 / 0x25 inside it is a
     per-chunk or per-tick limit (13 ticks a chunk puts the 55-tick mark of probes 150/151 in chunk 5).
  3. centre LONG inside the BODY of a chunk (1 s after one starts) = STOP.  The chunk in flight plays out (at
     most 2.6 s), then SILENCE and nothing spoken.  Wait 10 s.  No button of any kind during chunks.
  4. centre LONG = START again, 30 s, centre LONG in a chunk body = STOP.  Stop here.

## OUTCOME TABLE (spoken ids as probes 180/181: 0x10, 0x21, 0x22, 0x1B, 0x24, 0x25, 0x3E; 0x26 is NOT spoken; the
## SUCCESS of a loop image is acoustic by design, a spoken id at a seam or at a STOP would be a SPEAK while our
## chain holds port 3 (CLAUDE.md rule 4).  Do not carry a table between probes: read this one.)

  heard at the seam (long run, purge kept, 8 kHz stand-in; T03 reading ladder)
  a silence of about 0.2 s at every seam, pulse 2.8 s (21 a minute)
                              -> the lead L is under about 25 ms: the rebuild waits for the next tick after the
                                 audible end.  The gap is the poll wait.  Next: 100 ms (one immediate; it fits
                                 one word, so the cave shrinks by one word and the layout is rebuilt and
                                 re-gated), threshold L 12 ms.
  a very short gap (about 5-40 ms, may sound like a click) at every seam, pulse 2.6 s (23 a minute)
                              -> L is between about 25 and 225 ms and the number is c = the rebuild latency
                                 (about 20 ms: default bracket; about 3 ms: low-c bracket).  If c - h1072 is 10 ms
                                 or less the J-D4 target (gap 10 ms or less, or a pure splice) is met with the
                                 purge kept; if it is above, the skip-re-arm image (J-C17) is the next candidate.
  no silence, a splice (a click from a few ms of cut tail), pulse 2.6 s
                              -> L is above about 245 ms (the model's 32 ms splice).  J-D4 met.
  mostly seamless with a LARGER dropout (about 0.15-0.2 s) every 10-60 s
                              -> the sliding regime near a threshold; the period of the large dropout measures
                                 a_busy (T03 6.2 item 3).  Write down the times of three of them.
  chunk 1 longer or lower than the rest
                              -> as probe181: the stock leaves a rate other than 8000 for the first chunk.
  every seam is a click or a level or pitch jump, or the sound changes character, or grows loud
                              -> a rebuild into a still-draining DSP is NOT harmless here.  Kill switches at once
                                 (below); do not repeat; the next step is a slower poll, not a faster one.
  loops; STOP in a chunk body ends it at the end of that chunk; silence; the 2nd START works
                              -> MessageCancelFirst works from a cave at the 200 ms rate (probes 180/181 answered
                                 it at slower rates).
  keeps looping after STOP    -> the cancel did not find the message: press STOP once more inside a chunk body;
                                 a press in a gap then STARTs a second chain (doubled seams): kill switch.
  a START press does nothing, every time
                              -> MessageCancelFirst returned TRUE with nothing pending (every press reads STOP).
  "call ended" 0x21 while music plays
                              -> the DSP went away at a seam; the loop is over, nothing is pending.
  "bluetooth off" 0x3E on START -> no .kap loaded: music is not playing.
  "and" 0x10 at a seam or START -> StreamKalimbaSink(3) returned 0.
  0x22 / 0x1B / 0x24 / 0x25 at a seam or START
                              -> FileFind dir / FileFind file / StreamFileSource / TransformAdpcmDecode or
                                 TransformStart refused; port free; nothing re-armed.  Note the time: inside 14 s
                                 (chunk 5, 55 ticks) it is the tick-count fault of probes 150/151; later it is a
                                 per-chunk limit.
  "ended" 0x26 heard          -> the WRONG image is on the speaker (probe179).
  a RESTART at any poll or press -> the busy read, MessageCancelFirst or the rebuild into a draining DSP: note the
                                 time since START and whether it was at a seam.
  1 chunk then silence, no id -> the tick was not delivered at this rate, or the read stays busy forever.
  KILL SWITCHES if STOP fails, in this order: (1) Bluetooth long press (the pairing teardown ends our chain; the
  next poll speaks 0x21; re-pair afterwards); (2) pause the music only if probe179 press B said the unload beats
  the poll; (3) POWER off with USB unplugged (about 20 s).  Recovery order: docs/FLASH-PROTOCOL.md "Recovery".

## SIMULATED (tools/cavesim.py world model, offline; the model is not the firmware)

  build/hook/gate_probe181p.py: probe181's 31 scenarios with every expectation re-derived for the 200 ms grid,
  plus the grid scenarios, STOP either side of the free edge and the 10/30/200 ms lead cases (37 scenarios in all).
  Rules R1-R6 report no violation except the accepted/inherited cases.  The model has no 0x1072 purge, no lead
  unless --tail-ms is given, and zero VM latency: tools/seammodel.py prices the seam with assumed parameters.
"""

import os, re, sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

_PROBE = re.match(r'assemble_(probe[0-9a-z]+)\.py$',
                  os.path.basename(os.path.abspath(__file__))).group(1)

CAVE = 0x3E21D
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
SINKSLACK = ca.STUB['SinkSlack']
KALMSG   = ca.STUB['KalimbaSendMessage']
KSINK    = ca.STUB['StreamKalimbaSink']
ADPCM    = ca.STUB['TransformAdpcmDecode']
TSTART   = ca.STUB['TransformStart']
RATE     = 8000          # inherited from probe181 (unchanged here). 0x1072 word a. Every audio probe so far sent 2000; 8000 is the
                         #   DSP's own default tone rate and the rate the brown material is authored at
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
POLL_MS = 200            # probe181p: THE ONE CHANGE (probe181 had 1000). The poll period; 200 ms is the T03/J-C6
                         #   first step (13 busy reads per 2.62 s chunk; DESIGN floor 50 ms, R5 floor in cavesim)
POLL_ID = 0x0012         # probe180: the ONE MessageId this cave ever sends to its TaskData; the
                         #   press cancels exactly this id (STOP) and every REARM sends exactly it.
                         #   A message id, not a request id: it is never spoken.
assert 1 <= POLL_ID <= 127          # ld AH,#POLL_ID is one word (ca.imm_words, opcode 0x10)
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
DIR_DATA, _DIR_AH = _pool_ah("tts")   # probe177: "tts" from the pool (0x3e40f; DIRNAME is set below)

# ---- two SHORT carried strings, each emitted as ONE item so the layout cannot
# split it, and each asserted contiguous after layout. The cave's blind bands
# measure 14, 9 and 3 words, so "NowSpeakTTS/data_us" (20 words with its NUL)
# CANNOT fit in one band -- hence the two-level walk. file.h:18-28 supports it:
# FileFind takes the directory to start from, and FILE_ROOT is 1.
DIRNAME, FILENAME = "tts", "rphrases_us"   # probe177: tts/rphrases_us (10,486 bytes, ~10 s)

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
CANCELFIRST = ca.STUB['MessageCancelFirst']   # 0x66: cancel the first pending message of (task, id)
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

# ---- the carried path string, ONE item so the layout places it whole (asserted below).
LBL("STRFILE")
W(*[ord(c) for c in FILENAME])  # "data_us", no NUL: FileFind takes the length (7)

# --------------------------------------------------------------- the HANDLER
# probe181p (as 181/180): dispatched through the TaskData at CAVE+1/CAVE+2 by the 200 ms poll the press (and
# every rebuild) arms. AL = task, AH = the MessageId (always POLL_ID; NOT read: REARM sends the
# immediate, so no mis-delivered id can make a poll the STOP cannot cancel). The first
# instruction is in the const window (asserted below); everything after it may spill. The
# handler shares BUILD's frame (enterl -8) and enters BUILD with slot 2 = ksink, exactly the
# state the press leaves.
LBL("HANDLER")
W(0xF80B)                       # enterl -8
ca.call1(W, BSR, KSINK, al=('imm', 3))
W(0x0227)                       # st AL,@(2,Y)  ksink
W(0x0084); BR(0xF4, "NOSINK")   # 0 -> 0x10 "and": the loop ends here, nothing re-armed
BSR(TFROMSINK)                  # READ-ONLY. AL = ksink still (st and cmp leave it)
W(0x0084); BR(0xF4, "HFREE")    # 0 -> the port is free
# ---- busy: the chunk still holds port 3. Re-arm the SAME id and touch nothing else.
BR(0xE0, "REARM")
LBL("HFREE")
BSR("GATE")                     # 0x1072(8000, b = 2): TRUE iff a .kap is loaded
W(0x0084); BR(0xF4, "GONE")     # FALSE -> the DSP went away at the seam: 0x21, no re-arm
BR(0xE0, "BUILD")               # rebuild; BUILD re-arms POLL_ID, forever (probe180: no ENDED)
LBL("GONE")
W(0x2114)                       # ld AL,#0x21 "call ended": distinct from START's 0x3E
BR(0xE0, "SAY")

# ---------------------------------------------------------------------- ARM
# ONE chain per START, and nothing is ever done to a port that is busy. probe180 puts the STOP
# first: MessageCancelFirst(cave task, POLL_ID) TRUE = the loop is running = this press is a
# STOP (leavel; nothing touches port 3; nothing is spoken). FALSE = START, unchanged from
# probe179/178 from the sink check on; then the shared BUILD runs.
#   MessageCancelFirst(task, POLL_ID)            TRUE -> STOP
#   ksink = StreamKalimbaSink(3)                 0 -> 0x10 "and"
#   t = TransformFromSink(ksink)   READ-ONLY     nonzero -> STOP: this press does nothing
#   GATE 0x1072 (TRUE iff a .kap is loaded)      FALSE -> 0x3E "bluetooth off"
#   BUILD -> FileFind, FileFind, StreamFileSource, TransformAdpcmDecode -> port 3,
#   TransformStart, MessageSendLater(task, POLL_ID, 0, POLL_MS), return.
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
BSR("GATE")
W(0x0084); BR(0xF4, "NODSP")    # FALSE -> no .kap loaded (nothing streaming): 0x3E
# ---- BUILD: shared by the press and the handler. Needs slot 2 = ksink.
LBL("BUILD")
W(*ca.imm_words(len(DIRNAME), 0x14))    # ld AL,#3
W(0x0027)                       # st AL,@(0,Y)  arg3 = length in words
W(0x0114)                       # ld AL,#1      arg1 = FILE_ROOT
W(*_DIR_AH)                     # ld AH,#<pool copy of "tts">
BSR(FILEFIND)
W(0x0084); BR(0xF4, "NODIR")
W(*ca.imm_words(len(FILENAME), 0x10))   # ld AH,#11  (probe176: from the name)
W(0x0023)                       # st AH,@(0,Y)  arg3 = length in words
LBL("SETAHFILE")
W(0x0000, 0x0010)               # ld AH,#<data addr of STRFILE> (patched below)
BSR(FILEFIND)
W(0x0084); BR(0xF4, "NOFILE")
BSR(FILESRC)                    # src = StreamFileSource(file); the index is in AL
W(0x0084); BR(0xF4, "NOSRC")
W(0x0213)                       # ld AH,@(2,Y)  ksink (AL still holds src)
BSR(ADPCM)                      # t = TransformAdpcmDecode(src, ksink)
W(0x0084); BR(0xF4, "NOPLAY")
BSR(TSTART)                     # TransformStart(t)
W(0x0084); BR(0xF4, "NOPLAY")
# ---- REARM: MessageSendLater(cave task, POLL_ID, 0, POLL_MS) -- probe173's form verbatim:
# message slot 0, delay HIGH slot 1, delay LOW slot 2 (message-task-abi.md 1). The id is the
# immediate POLL_ID on every path (the next poll after any chunk, busy or rebuilt, is the one
# the STOP cancels).
LBL("REARM")
W(0x0014); W(0x0027)            # message = 0          slot0
W(0x0127)                       # (AL still 0) delay high = 0   slot1
W(*ca.imm_words(POLL_MS, 0x14))     # ld AL,#200   (probe181p; probe181 had 1000)
W(0x0227)                       # st AL,@(2,Y)  delay low (ksink is dead now)
W(*ca.imm_words(POLL_ID, 0x10)) # ld AH,#POLL_ID  the MessageId (constant)
W(*ca.imm_words(TASK_ADDR, 0x14))   # ld AL,#0xBA3C  the cave's TaskData
BSR(MSGLATER)
W(0xF80F)                       # leavel -8: the chunk plays, the poll is set

# ---- STOP: two ways in, one terminus, both do NOTHING to port 3. (1) the cancel found the poll:
# the loop was running and is now stopped. (2) port 3 is busy on a START press (probe176).
# probes 174/175 crashed stopping a running transform from here: no teardown, ever.
LBL("STOP")
W(0xF80F)                       # leavel -8

LBL("NOSINK")
W(0x1014)                       # ld AL,#0x10 "and": StreamKalimbaSink(3) returned 0
BR(0xE0, "SAY")
LBL("NODIR")
W(0x2214)                       # ld AL,#0x22 "conference call": the directory is gone
BR(0xE0, "SAY")
LBL("NOFILE")
W(0x1B14)                       # ld AL,#0x1B "call from unknown": data_us is gone
BR(0xE0, "SAY")
LBL("NOSRC")
W(0x2414)                       # ld AL,#0x24 "switching call": StreamFileSource refused
BR(0xE0, "SAY")
LBL("NOPLAY")
W(0x2514)                       # ld AL,#0x25 "call with": the transform was refused
BR(0xE0, "SAY")
LBL("NODSP")
W(0x3E14)                       # ld AL,#0x3E "bluetooth off": no .kap loaded -- and FALL
                                #   into SAY, the next item
LBL("SAY")
BSR(SPEAK)                      # probe99's direct idiom, hardware-proven; port 3 is free on
                                #   every path that reaches here
W(0xF80F)                       # leavel -8

# ---- GATE: KalimbaSendMessage(0x1072 SET_TONE_RATE, 8000, TONE_B, 0, 0) -> bool in AL,
# through KSEND's own frame (probe161's form). probe178: word b = 2 = NO_EXTRA_GAIN ->
# cbops.shift 4 instead of 7, 18 dB quieter (docs/kalimba-disasm.md). That was 178's change.
TONE_B = 2
LBL("GATE")
W(*ca.imm_words(RATE, 0x10))    # ld AH,#8000  (probe181, unchanged)
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
W(0xF80F)                       # leavel -8, and AL carries the bool out

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

print('FileFind strings:')
print('  %-12r from the firmware const pool at data %#06x (ld AH %04x %04x)'
      % (DIRNAME, DIR_DATA, _DIR_AH[0], _DIR_AH[1]))
_str_ptr('STRFILE', FILENAME, 'SETAHFILE', nul=False)
# probe172: the stubs ride along ONLY when cave code is in the region; this image puts
# nothing there, so the seven dead functions stay byte-for-byte stock.
if any(caveguard.region_fn(_a) is not None for _a in out):
    for _a, _v in REGION_STUBS.items():
        assert _a not in out, hex(_a)
        out[_a] = _v
for _lbl in ("STRFILE", "HANDLER"):   # probe179: the handler's FIRST instruction stays in the window
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

# probe181p: the ONE change, asserted. Against probe181's cave (if its words file is present) exactly
# the two words of REARM's `ld AL,#POLL_MS` may differ (1000 -> 200: both need a prefix word plus the load, so
# the cave is still 174 words and the layout is unchanged).
_P181 = "build/hook/probe181_words.json"
if os.path.exists(_P181):
    _old = {int(k, 16): v & 0xFFFF for k, v in json.load(open(_P181)).items()}
    _diff = sorted(x for x in set(_old) | set(out)
                   if (_old.get(x) is None) != (out.get(x) is None)
                   or (_old.get(x) is not None and _old[x] != (out[x] & 0xFFFF)))
    _want_old = ca.imm_words(1000, 0x14)
    _want_new = ca.imm_words(POLL_MS, 0x14)
    assert len(_diff) == 2 and _diff[1] == _diff[0] + 1, (
        "probe181p must differ from probe181 in REARM's ld AL,#POLL_MS only", [hex(x) for x in _diff])
    assert [_old[x] for x in _diff] == _want_old and [out[x] & 0xFFFF for x in _diff] == _want_new, (
        [hex(_old[x]) for x in _diff], [hex(out[x] & 0xFFFF) for x in _diff])
    assert label_addr["REARM"] < _diff[0] <= label_addr["REARM"] + 8, (hex(_diff[0]), hex(label_addr["REARM"]))
    print("vs probe181: %d words differ, %s = REARM's ld AL,#%d (%s -> %s)"
          % (len(_diff), [hex(x) for x in _diff], POLL_MS,
             ' '.join('%04x' % _old[x] for x in _diff),
             ' '.join('%04x' % (out[x] & 0xFFFF) for x in _diff)))
else:
    print("vs probe181: probe181_words.json not present, delta not asserted")
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
