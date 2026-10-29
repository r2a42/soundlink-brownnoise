#!/usr/bin/env python3
"""probe188 (PBd, the DIAGNOSTIC product build) and, through assemble_probe189.py, probe189 (PB, the SILENT product build).
B01, round 3, 2026-10-12; built and gated offline, NOT flashed (build/hook/FLASHED still says probe178).

The full press pages, id tables, word counts, hashes and the exact edit commands are in
docs/deep/round3-2026-10-12/B01-product-build-probes.md; read it before an owner-present session.  The spec is
T11 section 5, R05 section 5 and V04 (PB/PBd review) of the same round.  This file is the builder and the record
of the design in the code comments.

## WHAT IT IS (probe181p's loop with five changes; everything else is probe181p byte for byte in behaviour)

  1. THE GUARD, FIRST.  Both entries (the button press ARM and the poll tick HANDLER) run ONE copy of it (R05 5.4, the
     merged entry; two copies do not fit): sinkState (@0x59e, `ld AL,@0x59e` = 0x0600 0x9E15) must be 13 or 3, and
     @0x72f (the A2DP plugin instance) must be non-zero, BEFORE StreamKalimbaSink(3) (create-if-absent) is called.
     STOP is still first: MessageCancelFirst(cave task, POLL_ID) runs before the guard, so a press ends a running
     loop in ANY state.
  2. THE CONSUME LEVER (CONSUME, owner decision): after ARM, TRIG stores 0 into the caller's indicate flag and sets
     bit 15 of its flag word (cave slots 21/22 = fn_00846 locals 13/14), so fn_01749 skips its whole switch: no
     assistant request, no stock beep, no short-press conversion.  Six words.  NEVER RUN ON HARDWARE.
  3. THE MERGED ENTRY changes one behaviour: a START while port 3 is busy is a DEFERRED start (the poll waits for the
     port) instead of a no-op; a second press cancels it (STOP first).
  4. THE ID PLACEMENT (rule 4).  A guard refusal never calls SPEAK: ARM returns the id in AL, TRIG speaks it (a button
     press, no poll pending) and the message loop ignores it (a tick: a silent end).  The refusals after the busy read
     (the table below) speak from the frame as in 179-181p.  Every normal exit of ARM sets AL := 0.
  5. THE TAIL.  Every spoken id lives in the last group of items (QSTATE QPLUG NOSINK NODIR NOFILE NOSRC NOPLAY GONE SAY).
     probe189 (PB) is this image with those nine entry points each reduced to one `leavel -8` and every other tail word
     dropped; nothing before the tail changes by a bit (asserted at build time; PBEDIT below).

  Unchanged from probe181p: the hook (0x00e46, operand bytes 04 d4 d5), POLL_ID 0x12, POLL_MS 200, the 0x1072 resend
  (rate 8000, word b = TONE_B = 2) on EVERY rebuild, BUILD (FileFind tts / rphrases_us, 10,486 bytes, the stand-in
  material), no TransformStop, no StreamDisconnect, no PS write, no partition write.

## WORDS AND HASHES (python build/hook/assemble_probe188.py --build ; python build/hook/assemble_probe189.py --build)

  probe188  180 words 0x3E21D..0x3E3E1, all in the const window, none in the code region;
            words sha256 b5e055e80de4979640c71ade4dc052650f58482befdc5655b9b76a685f1d4c00
            dfu   sha256 e0523156fb0685545093567ab946edf877637f881c9801db8e7b2d04633abd2f
  probe189  165 words (180 - 15 tail words), same span start, no bsr to SPEAK;
            words sha256 f6d647dd1513cd0b4e26aaca57c1884b6c15cc216c6092e6c8530943056ad125
            dfu   sha256 21e8d9eeb11e3bb2dbb787e6fad0a590b9f55880038fb67943c95463eb928eb8
  (fsedit/dfubuild flakes about one build in four on identical input, "final digest mismatch" or "no fs area": rerun;
  the results are deterministic once built.)

## SPOKEN IDS OF PBd (probe189 speaks none of them).  Success is ACOUSTIC (loop, STOP).  Do not carry another probe's table.

  after a guard refusal at a BUTTON PRESS (TRIG speaks it; a tick that fails the guard ends silently):
    0x27 + sinkState      sinkState not 3 or 13: 0x27 limbo, 0x28 connectable, 0x29 discoverable (state 2), 0x2B..0x2D
                          outgoing / incoming / active call, 0x2E test mode, 0x2F..0x33 call variants, 0x35 low battery,
                          0x36 aux, 0x37 factory reset, 0x38 language select, 0x39 manual connect, 0x3B reman, 0x3C ship
                          mode, 0x3D USB, 0x3A and 0x3E states 19 and 23 (unnamed).  0x2A (state 3) and 0x34 (state 13)
                          cannot occur.  These are the stock BATTERY and pairing sentences: a battery sentence right after
                          a press is the report, one without a press is the stock.
    0x23 "conference call failed"   sinkState 3 or 13 but @0x72f == 0 (a stock prompt or a call has the DSP)
  after the busy read said the port is free (as 179-181p; the SAME id at START and at a seam rebuild):
    0x10 "and"                      StreamKalimbaSink(3) returned 0
    0x22 "conference call"          the directory FileFind refused
    0x1B "call from unknown"        the file FileFind refused
    0x24 "switching call"           StreamFileSource refused
    0x25 "call with"                TransformAdpcmDecode OR TransformStart refused (one id for both)
    0x21 "call ended"               GATE (0x1072) returned FALSE: no .kap loaded: the DSP went away at a seam, or a START
                                    with the music not playing (probe181p said 0x3E for that START; one id now)
  silence after START with no id    the cancel returned TRUE with nothing pending (every press reads STOP), or the press
                                    was not a 0x4004 in this state (the button table delivers it in states 2, 3, 13 only)

## GATE 5 / GATE 6 (stated, NOT resolved; see the note): the success of a loop is acoustic; ids are shared between START
## and a rebuild and between the two Transform refusals; PB speaks nothing; the press scripts need several presses.

## KILL SWITCHES as 180/181p: Bluetooth long press (ends our chain at the DSP teardown), pause the music only if the
## unload beats the poll, POWER off with USB unplugged (about 20 s).  docs/FLASH-PROTOCOL.md "Recovery" otherwise.

## GATES RUN (offline, all 2026-10-12): decode-verify OK; cavesim probe90 AL = 0x000e; tools/preflight.py probe188
## probe189 OK; tools/caveguard.py SAFE; tools/stackdepth.py 0xE46 --frame 8 FITS (no frame larger than enterl -8);
## build/hook/gate_probe188.py probe188 and probe189: 80 scenarios each, 0 failed (probe189 also compared with probe188
## summary by summary); three mutations of the words are caught; builds are byte-identical on rebuild.
"""

import os, re, sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

# assemble_probe189.py runs THIS file through runpy with ENGINE_VARIANT = "probe189" (the silent product build PB);
# run directly it is probe188 (PBd, the diagnostic build: the same cave with its ids spoken).
_PROBE = globals().get('ENGINE_VARIANT') or re.match(r'assemble_(probe[0-9a-z]+)\.py$',
                  os.path.basename(os.path.abspath(__file__))).group(1)
assert _PROBE in ('probe188', 'probe189'), _PROBE
SILENT = (_PROBE == 'probe189')         # PB: the mechanical edit "every id stub becomes leavel" (see PBEDIT below)
CONSUME = True                          # R05 5.3: the 6-word consume-the-0x4004-event lever in TRIG (owner decision N-L)
REPORT_AT_START = True                  # PBd only: a START refused by the guard speaks the reason (TRIG speaks it; design choice, B01 note 3)

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
POLL_MS = 200            # the poll period of probe181p (the T03/J-C6 first step; 13 busy reads per 2.62 s chunk). PB must use the
                         #   smallest period that 181p proved clean: 1000 (probe181) or 200 -- change HERE and rebuild (new hashes)
TONE_B = 2               # 0x1072 word b: 2 = NO_EXTRA_GAIN, shift 4, 18 dB quieter -- the ONE level the owner heard as quiet (probe178).
                         #   J-D16's b = 0 belongs to the 0.9-peak brown payload at 185a, NOT to this stand-in (rphrases_us at b = 0 was
                         #   heard as very abrasive and loud). Change HERE and rebuild (new hashes).
ID_PLUG = 0x23           # PBd only: "conference call failed" = a button press with no A2DP plugin instance (@0x72f == 0)
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
# probe188/189 (R05 5.3, owner decision N-L): after ARM the swallowed event is also CONSUMED -- the caller's indicate
# flag (13,Y) := 0 and bit 15 of its flag word (14,Y) set (cave slots 21 and 22, fn_00846 being `enterl -23` and the
# cave `enterl -8`), so fn_01749 skips its whole switch: no assistant request, no stock beep, no short-press
# conversion.  Six words, a stock shape (0x00e25-0x00e27), NEVER RUN ON HARDWARE (first cave store into a caller
# frame).  CONSUME = False drops it (a different image, different hashes).
LBL("TRIG")
W(0xF80B)                       # enterl -8
W(0x0027)                       # st AL,@(0,Y)  the event id
W(*ca.imm_words(0x4004, 0x84))  # cmp AL,#0x4004
BR(0xF0, "PASS")                # bne -> not ours: replay
BSR("ARM")                      # start a chunk, or stop the running one.  AL = 0, or (a guard refusal) the id to speak
W(0x0127)                       # st AL,@(1,Y)  keep it across the lever
if CONSUME:
    W(0x0014)                       # ld AL,#0
    W((21 << 8) | 0x27)             # st AL,@(21,Y)  caller (13,Y): the indicate flag := 0
    W((22 << 8) | 0x17)             # ld AL,@(22,Y)  caller (14,Y): its flag word
    W(*ca.imm_words(0x8000, 0xB4))  # or AL,#0x8000  bit 15 = "consumed" (0x00853 is the attested form)
    W((22 << 8) | 0x27)             # st AL,@(22,Y)
W(0x0117)                       # ld AL,@(1,Y)
W(0x0084); BR(0xF0, "SAY")      # bne -> a guard refusal asks for an id: SAY speaks it and leaves (same frame size)
W(0xF80F)                       # leavel -8: the voice-dial event is swallowed
LBL("PASS")
W(0x0017)                       # ld AL,@(0,Y)  the event back in AL
BSR(FN189FB)                    # the stock call, replayed (0x00e49 reloads AL after it)
W(0xF80F)                       # leavel -8

# ---- the carried path string, ONE item so the layout places it whole (asserted below).
LBL("STRFILE")
W(*[ord(c) for c in FILENAME])  # "rphrases_us", no NUL: FileFind takes the length (11)

# --------------------------------------------------------------- the HANDLER
# Dispatched through the TaskData at CAVE+1/CAVE+2 by the poll the press (and every rebuild) arms. AL = task, AH =
# the MessageId (always POLL_ID; NOT read).  It shares HBODY with ARM (R05 5.4: the merged entry, the only layout
# that fits {3,13} + the plugin test + the lever): slot 3 of the frame carries WHO CAME IN, 1 = the poll tick,
# 0 = a button press.  The first instruction is in the const window (asserted below).
LBL("HANDLER")
W(0xF80B)                       # enterl -8
BR(0xE0, "HBODY")

# ---------------------------------------------------------------------- ARM
# ONE chain per START.  STOP FIRST (reachable in every state, before any guard or sink read):
#   MessageCancelFirst(cave task, POLL_ID)    TRUE -> STOP: the loop was running, it is stopped, nothing else is touched
#   FALSE -> START: HBODY (the guard, the sink, the busy read, GATE, BUILD).
# Return value (read by TRIG, ignored by the message loop): AL = 0, or the id of a GUARD refusal for TRIG to speak.
LBL("ARM")
W(0xF80B)                       # enterl -8
ca.call2(W, BSR, CANCELFIRST, al=('imm', TASK_ADDR), ah=('imm', POLL_ID))
W(0x0084); BR(0xF0, "STOP")     # bne -> TRUE: a poll was pending: STOP. Nothing else is touched

# ---- HBODY: the state guard FIRST (before StreamKalimbaSink(3), which is create-if-absent), then the 181p body.
#   sinkState (@0x59e, a plain RAM word, R05 E1/E2) must be 13 (A2dpStreaming) or 3 (Connected);
#   @0x72f (the A2DP plugin instance, freed during a stock prompt swap and a call) must be non-zero.
LBL("HBODY")
W(*ca.imm_words(0x59E, 0x15))   # ld AL,@0x59e   (0x0600 0x9e15, the form probes 131-133 and 142-144 ran)
W(*ca.imm_words(13, 0x84)); BR(0xF4, "GOK")      # cmp AL,#13 ; beq
W(*ca.imm_words(3, 0x84)); BR(0xF0, "QSTATE")    # cmp AL,#3 ; bne -> not a streaming-capable state
LBL("GOK")
W(*ca.imm_words(0x72F, 0x99)); BR(0xF4, "QPLUG") # tst @0x72f ; beq -> no A2DP plugin (prompt swap, call)
ca.call1(W, BSR, KSINK, al=('imm', 3))
W(0x0227)                       # st AL,@(2,Y)  ksink
W(0x0084); BR(0xF4, "NOSINK")   # 0 -> "and": the loop ends here, nothing re-armed
BSR(TFROMSINK)                  # READ-ONLY. AL = the transform on port 3, or 0
W(0x0084); BR(0xF4, "HFREE")    # 0 -> the port is free
# ---- REARM: MessageSendLater(cave task, POLL_ID, 0, POLL_MS) -- probe173's form verbatim.
LBL("REARM")                    # also the busy exit: re-arm the SAME id and touch nothing else (a START here = a DEFERRED start)
W(0x0014); W(0x0027)            # message = 0          slot0
W(0x0127)                       # (AL still 0) delay high = 0   slot1
W(*ca.imm_words(POLL_MS, 0x14))     # ld AL,#200
W(0x0227)                       # st AL,@(2,Y)  delay low (ksink is dead now)
W(*ca.imm_words(POLL_ID, 0x10)) # ld AH,#POLL_ID  the MessageId (constant)
W(*ca.imm_words(TASK_ADDR, 0x14))   # ld AL,#0xBA3C  the cave's TaskData
BSR(MSGLATER)                   # ... and FALL into STOP: the chunk plays, the poll is set, AL := 0 (MessageSendLater's result is not 0)

# ---- STOP: the cancel found the poll: the loop is stopped.  The chunk in flight plays out.  NO teardown, ever
# (probes 174/175 crashed stopping a running transform; rule 4).  Every normal exit of ARM comes through here with
# AL := 0 ("nothing to say" to TRIG).
LBL("STOP")
W(0x0014)                       # ld AL,#0
W(0xF80F)                       # leavel -8

LBL("HFREE")
BSR("GATE")                     # 0x1072(8000, b = TONE_B): TRUE iff a .kap is loaded
W(0x0084); BR(0xF4, "GONE")     # FALSE -> the DSP went away (or never was): nothing re-armed
# ---- BUILD: needs slot 2 = ksink; falls out into REARM.
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
BR(0xE0, "REARM")               # BUILD done: arm the next poll

# ---- GATE: KalimbaSendMessage(0x1072 SET_TONE_RATE, 8000, TONE_B, 0, 0) -> bool in AL, through KSEND's own frame
# (probe161's form).  Sent on EVERY rebuild (the skeptics: a skip-re-arm is J-C17, not proven).  TONE_B = 2 is the
# one level the owner has heard as quiet (probe178 "Quieter on Both"): NO_EXTRA_GAIN, cbops.shift 4 instead of 7,
# 18 dB quieter.  b = 0 is the J-D16 level of the 0.9-peak brown payload at 185a, NOT of this stand-in.
LBL("GATE")
W(*ca.imm_words(RATE, 0x10))    # ld AH,#8000
W(*ca.imm_words(0x1072, 0x14))  # ld AL,#0x1072   ...and fall into KSEND
LBL("KSEND")
W(0xF80B)                       # enterl -8
W(0x0327)                       # st AL,@(3,Y)  the message id
W(*ca.imm_words(TONE_B, 0x14))  # ld AL,#TONE_B
W(0x0027)                       # st AL,@(0,Y)  b           slot 0
W(0x0014)                       # ld AL,#0
W(0x0127); W(0x0227)            # c = d = 0                  slots 1..2
W(0x0317)                       # ld AL,@(3,Y)
BSR(KALMSG)
W(0xF80F)                       # leavel -8, and AL carries the bool out

# ======================================================================= THE TAIL (every spoken id lives here)
# PBd speaks, PB does not: PB is this image with the nine tail entry points (QSTATE QPLUG NOSINK NODIR NOFILE NOSRC
# NOPLAY GONE SAY) each reduced to ONE `leavel -8` and every other tail word dropped (the mechanical edit, applied
# to the finished word list below, PBEDIT).  Nothing before this label is touched by the edit.
# Who may speak (rule 4: never SPEAK while OUR transform holds port 3):
#   - NOSINK NODIR NOFILE NOSRC NOPLAY GONE: reached only AFTER the busy read said free (as 179-181p).
#   - QSTATE QPLUG: reached BEFORE the sink is read (it is create-if-absent), so they never call SPEAK: they return the id
#     in AL.  A button press came through TRIG, which speaks it (no poll is pending: the cancel said FALSE; by the press
#     page no chunk is draining).  A poll tick came through the message loop, which ignores AL: a silent end.
LBL("TAIL")
LBL("QSTATE")
if REPORT_AT_START:
    W(*ca.imm_words(0x59E, 0x15))   # ld AL,@0x59e : the state report, id = 0x27 + sinkState
    W(*ca.imm_words(0x27, 0x34))    # add AL,#0x27
W(0xF80F)                       # leavel -8: ARM hands the id to TRIG (a tick ignores AL: silent)
LBL("QPLUG")
if REPORT_AT_START:
    W(*ca.imm_words(ID_PLUG, 0x14)) # 0x23 "conference call failed": the A2DP plugin instance is absent
W(0xF80F)
LBL("NOSINK")
W(0x1014)                       # ld AL,#0x10 "and": StreamKalimbaSink(3) returned 0
BR(0xE0, "SAY")
LBL("NODIR")
W(0x2214)                       # ld AL,#0x22 "conference call": the directory is gone
BR(0xE0, "SAY")
LBL("NOFILE")
W(0x1B14)                       # ld AL,#0x1B "call from unknown": the file is gone
BR(0xE0, "SAY")
LBL("NOSRC")
W(0x2414)                       # ld AL,#0x24 "switching call": StreamFileSource refused
BR(0xE0, "SAY")
LBL("NOPLAY")
W(0x2514)                       # ld AL,#0x25 "call with": the transform was refused
BR(0xE0, "SAY")
LBL("GONE")
W(0x2114)                       # ld AL,#0x21 "call ended": GATE FALSE = no .kap (the DSP went away at a seam, or a START
                                #   with the music not playing: probe181p said 0x3E there; one id now). FALL into SAY
LBL("SAY")
BSR(SPEAK)                      # probe99's direct idiom, hardware-proven
BR(0xE0, "STOP")                # and out through STOP (AL := 0)

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
    extra_owner = {}
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
            extra_owner[addr] = i
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

# ---- PBEDIT: probe189 (PB) is probe188 (PBd) with every tail entry point reduced to ONE `leavel -8` and every other
# tail word (and every connector inside the tail) dropped.  Nothing before the TAIL label changes by a bit, because
# the layout is sequential and the tail is the LAST group of items; the check below asserts it word by word.
TAIL_IDX = next(i for i, it in enumerate(prog) if it[0] == "label" and it[1] == "TAIL")
TAIL_FIRST = next(i for i in range(TAIL_IDX, len(prog)) if prog[i][0] not in ("label", "region"))
STUBS = ["QSTATE", "QPLUG", "NOSINK", "NODIR", "NOFILE", "NOSRC", "NOPLAY", "GONE", "SAY"]
tail_words = set()
for i, item in enumerate(prog):
    if i < TAIL_FIRST or item[0] in ("label", "region"): continue
    n = len(item[1]) if item[0] == "w" else bsr_size[i] if item[0] == "bsr" else br_size[i]
    tail_words |= set(range(addrs[i], addrs[i] + n))
tail_conn = {c for c, o in extra_owner.items() if o > TAIL_FIRST}
PBD_OUT = dict(out)                     # the diagnostic image's full word list (for the equivalence check)
PBD_TAIL = sorted(tail_words | tail_conn | {c + 1 for c in tail_conn if extra[c][1] == 2})
if SILENT:
    for a in tail_words:
        del out[a]
    for c in tail_conn:
        del out[c]
        if extra[c][1] == 2: del out[c + 1]
    extra = {c: v for c, v in extra.items() if c not in tail_conn}
    for l in STUBS:
        assert label_addr[l] not in out, (l, hex(label_addr[l]))
        out[label_addr[l]] = 0xF80F
    assert len({label_addr[l] for l in STUBS}) == len(STUBS)

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
    if SILENT and i >= TAIL_FIRST: continue      # PB: the tail items are gone (PBEDIT); the stubs are checked below
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
    if SILENT and i >= TAIL_FIRST: continue
    if item[0] not in ("label", "region"):
        assert addrs[i] in dstarts, (hex(addrs[i]), "boundary")
if SILENT:
    for l in STUBS:
        assert label_addr[l] in dstarts and patched[label_addr[l]] == 0xF80F, l
print("decode-verify: all branches OK, boundaries OK")

# ---- equivalence and structure checks (round 3, B01)
assert _nreg == 0, "rule 3 is literal: no cave word in the code region (shrink the design instead)"
if SILENT:
    assert not any(it[0] == "bsr" and (it[1] == SPEAK) for it in prog[:TAIL_FIRST]), "a SPEAK before the tail"
    _words188 = "build/hook/probe188_words.json"
    if os.path.exists(_words188):
        _p188 = {int(k, 16): v & 0xFFFF for k, v in json.load(open(_words188)).items()}
        _keep = {a: v for a, v in _p188.items() if a not in PBD_TAIL}
        _pb_non_stub = {a: v for a, v in out.items() if a not in {label_addr[l] for l in STUBS}}
        assert _pb_non_stub == _keep, "PB differs from PBd outside the tail"
        assert set(out) - set(_p188) == set(), "PB has a word PBd lacks"
        assert all(out[label_addr[l]] == 0xF80F for l in STUBS)
        print("vs probe188 (PBd): %d words (PBd %d); identical outside the tail; %d tail entry points are one "
              "leavel each; %d tail words dropped" % (len(out), len(_p188), len(STUBS), len(_p188) - len(out) + len(STUBS)))
        print("   PBd words differing from PB only at: %s" % ', '.join(l + '=' + hex(label_addr[l]) for l in STUBS))
    else:
        print("vs probe188: probe188_words.json not present, equivalence not asserted (run assemble_probe188.py first)")
    # no cave word may call SPEAK (0xDF7F): decode every bsr in the final image
    for a, op, v, ln in xapvm.decode(patched, fold_zero=False):
        if lo <= a <= hi and op == 0x9C:
            assert ((a + ln - 1 + v) & 0x3FFFF) != SPEAK, "PB calls SPEAK at %#x" % a
    print("PB: no bsr to SPEAK 0x%X in the image" % SPEAK)
else:
    print("PBd: %d words, tail %d words (the part probe189 drops)" % (len(out), len(PBD_TAIL)))
_P181P = "build/hook/probe181p_words.json"
if os.path.exists(_P181P):
    _o = {int(k, 16): v & 0xFFFF for k, v in json.load(open(_P181P)).items()}
    print("for scale: probe181p %d words; this image %d words (%+d)" % (len(_o), len(out), len(out) - len(_o)))
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
if "--labels" in sys.argv:
    for _l, _a in sorted(label_addr.items(), key=lambda kv: kv[1]):
        print("  %-10s %#x" % (_l, _a))
