#!/usr/bin/env python3
"""probe181: probe180 + RATE 8000. ONE change: the tone rate in the 0x1072 message, 2000 -> 8000.

(docs/deep/offline-2026-10-10/DESIGN.md section 3, "probe181"; built offline, NOT flashed.
Flash it ONLY after probe179 AND probe180 have been pressed on the speaker and their results
recorded: like probe180 this image LOOPS WITHOUT AN END OF ITS OWN, and its STOP is
MessageCancelFirst, which has never run on hardware.)

## THE CHANGE (one immediate, two words in the image)

  probe180 sent KalimbaSendMessage(0x1072, a = 2000, b = 2, 0, 0) in GATE, before every chunk.
  probe181 sends a = 8000 (RATE below). Nothing else differs: this assembler is
  assemble_probe180.py with RATE = 8000 and this docstring, and it asserts at build time
  that, against build/hook/probe180_words.json, exactly the two words of GATE's
  `ld AH,#imm` differ (0x0800 -> 0x1F00 and 0xD010 -> 0x4010; the immediate is a prefix word
  plus the load, and 8000 needs the same two words as 2000, so the cave is still 174 words,
  0x3E21D..0x3E3E6, all in the const window, none in the region; handler first instruction
  0x3E268). Handler, ARM (MessageCancelFirst first), BUILD, REARM, POLL_ID 0x12, POLL_MS 1000,
  word b = 2, the spoken ids, the hook and the redirect bytes: byte for byte probe180's.
  The material is still rphrases_us (10,486 bytes), the stand-in. Why 8000 (DESIGN section 8
  item 6, README F-list, dsp-keepalive-rate B): the brown material is authored at 8000 Hz and
  probe185a will be pressed at 8000, so the rate must be proven in the loop BEFORE the material
  changes; and the first chunk after the stock's last tone has been heard at about 7-8 kHz
  whatever was sent (probe177), so with a = 8000 the first chunk and the later ones should
  agree even though the CAUSE of that first-chunk behaviour is still open.

## THE BASE (read assemble_probe180.py's docstring for the full account)
  START  = centre long press with no poll pending: BUILD (FileFind x2, StreamFileSource,
           TransformAdpcmDecode -> port 3, TransformStart), arm MessageSendLater(0xBA3C, 0x12,
           0, 1000 ms).
  POLL   = every 1000 ms: StreamKalimbaSink(3) + READ-ONLY TransformFromSink; busy -> re-arm 0x12
           and nothing else; free -> GATE 0x1072(8000, b = 2) (FALSE -> 0x21), then BUILD and
           re-arm 0x12. The loop has no end of its own.
  STOP   = centre long press while the poll is pending: MessageCancelFirst(0xBA3C, 0x12) TRUE ->
           leavel; nothing touches port 3; nothing is spoken; the chunk in flight plays out.
  No Stop / Disconnect / StreamDisconnect anywhere; no 0x1072 on a busy port.

## TIMING AT 8000 Hz (re-derived; arithmetic = well-supported, model = the same arithmetic)
  chunk length = bytes x 2 samples / rate = 10,486 x 2 / 8000 = 2.6215 s (2622 ms)
                 (the same arithmetic gives 10.486 s at 2000 Hz, probe180's chunk)
  The poll grid is 1000 ms from each (re)arm. Chunk 1 starts at the press (t = 0): ticks at 1 s and
  2 s read BUSY (re-arm), the tick at 3 s reads FREE (the chunk ended at 2.62 s) and rebuilds.
  So every chunk is 2.62 s of sound then 378 ms of silence (ceil(2.6215) x 1 s - 2.6215 s),
  period 3.000 s, 2 busy reads + 1 rebuild per chunk, 20 chunks and 20 seams a minute.
  Compare probe180's 2000 Hz chunks: 10.49 s, seam 514 ms, period 11 s, 10 busy reads + 1 rebuild per chunk,
  5.5 chunks a minute. Consequences (arithmetic):
    - STOP latency <= 2.62 s (180: <= 10.5 s); a press in the 378 ms gap stops at once.
    - 1,200 rebuilds an hour, 3.7 times probe180's 327: the per-chunk source leak (F6, the
      cave never closes its StreamFileSource) binds 3.7 times sooner. A spoken 0x24/0x25 after
      MANY seams is the leak; the seam count sizes it. (An 8 h sleep with the final 7.5 s
      material is ~3,800 rebuilds; with this stand-in it would be 9,600.)
    - 12.6 % of the time is silence (378 ms in 3 s): the pumping cadence is the first thing the
      owner hears. POLL_MS is deliberately unchanged (E3 changes it later, one immediate).
    - The model has zero VM latency; on the speaker each tick arrives some tens of ms late (a
      hypothesis on the amount), and each re-arm starts from the handler, not the grid, so the
      measured period is 3.0 s plus up to ~3 x that latency and the seam is a little over 378 ms.
      A seam that is NOT constant (0.4 s sometimes, 1.4 s sometimes) means the chunk lengths
      are not constant: see the outcome table.

## WHAT THE OWNER SHOULD HEAR (prediction; the cave cannot check it)
  A steady pulse: 2.6 s of the stand-in noise (rphrases_us decoded as ADPCM: a harsh,
  buzzy rush, the "abrasive" stand-in of probe174, at the quiet level b = 2), 0.4 s of silence,
  and again, about 20 times a minute, with NO difference between the first chunk and the others.
  Against probe180: there chunk 1 was ~3 s at about 8 kHz and every later chunk was 10.5 s,
  four times slower and two octaves lower. In 181 EVERY chunk should sound like probe180's
  FIRST chunk (same pitch, same ~2.6 s), including the first. Brown noise it is not (the
  material is a stand-in); only rate, length and pulse are under test.

## NOT OBSERVED before this probe (this probe is the experiment)
  - everything probe180 inherits: a tick delivered from the 0x00e46 hook, the busy read on a
    running transform, ids on this hook, MessageCancelFirst from a cave (all hypothesis; see
    assemble_probe180.py). Do not flash 181 until 179 and 180 have answered them.
  - the rate: whether 0x1072 a = 8000 plays every chunk at 8000 Hz, and the real stock rate
    that chunk 1 meets. Hypotheses, none separable offline: the first chunk plays at what the
    stock left in the DSP ("late latch", the model's default, observed n=2 as "chunk 1 about 4x
    faster"); the resampler caches the rate (struck, the sites re-read it live); something
    else. A result of "all chunks equal" fits ALL of them (8000 = the stock's rate = the sent
    rate), so it makes the question moot for the material but does not answer it.
  - the free-before-audible-end seam is EXPECTED, not a fault (stack-transform.md, well-
    supported, never seen on the speaker); at 2.6 s chunks it recurs three times as often,
    so a cut tail would be three times as audible. Judge the seam by ear, not as an error.

## THE PRESS PLAN (speaker volume DOWN; laptop connected; music PLAYING; USB UNPLUGGED after
## the readback so that POWER can force the speaker off; Bluetooth button within reach;
## a stopwatch)

  1. centre LONG press = START. Let it loop 60 s by the stopwatch; COUNT the pulses (expect 20,
     each 2.6 s on / 0.4 s off) and LISTEN to chunk 1 against chunk 2 and 3 (same pitch, same
     length?). Write down any chunk that is longer or lower than the rest, and when.
  2. centre LONG press = STOP. The chunk in flight finishes (<= 2.6 s), then SILENCE and
     NOTHING spoken. Wait 10 s.
  3. centre LONG press = START again; loop 30 s (10 pulses); is the FIRST chunk of this second
     session the same as the rest? (A START while a stopped chunk is still sounding does
     nothing: wait for silence.)
  4. centre LONG press = STOP. Stop here.
  Optional, no flash (the cheap extras of DESIGN section 8 item 6): once, trigger a stock tone
  immediately before the START (any prompt or button beep the speaker makes on its own, for
  example a short press of a volume button if it beeps) and listen to whether chunk 1 of THAT
  session differs: this separates "the first chunk after the stock's last tone" from "the
  first chunk of any session". Say which stock tone you used.

## OUTCOME TABLE (spoken ids from docs/request-id-catalog.md; the SAME ids as probe180 - 0x10,
## 0x21, 0x22, 0x1B, 0x24, 0x25, 0x3E - none collides with a prompt the speaker says by itself
## with music playing and a laptop connected; 0x26 is NOT spoken in this image. Do not carry
## a table between probes: read this one.)

  every chunk the same pitch and ~2.6 s, 3.0 s pulse, ~20 a minute, STOP stops it, START again
  works, the first chunk of the 2nd session is the same
                              -> the rate is consistent at 8000 from chunk 1; the first-chunk
                                 quirk is moot for the 8000 material. The loop, STOP and the
                                 rate are done. (MessageCancelFirst: see probe180's rows.)
  chunk 1 is longer / lower than the rest (about 3 s, "slower"), chunks 2+ ~2.6 s
                              -> the first chunk after the stock's tone is NOT played at 8000:
                                 the stock leaves a different rate (the model's --stock-rate 7000
                                 predicts 2996 ms and a 4 ms seam, or ~1 s if that tick lands
                                 first). Consistent with the late-latch reading. The loop is
                                 unharmed. Next: E4 (re-send 0x1072 once after TransformStart)
                                 becomes worth a press, ONE change, or accept a different
                                 chunk 1 (only the first chunk of a session differs).
  chunk 1 equals the rest in the first session but the first chunk after a stock tone / a
  second session differs
                              -> the latch is tied to the stock's last tone: same remedy.
  all chunks the same but NOT ~2.6 s (for example every chunk ~5 s, or ~10.5 s again)
                              -> 0x1072's word a is not read as Hz the way the arithmetic
                                 assumes (probes 128-134 are unreconciled counter-evidence), or
                                 the rate is not applied; or the WRONG image is on the speaker
                                 (probe180 would give chunk 1 ~3 s then 10.5 s: check the
                                 readback). Stopwatch the pulse period: it is the chunk length
                                 rounded up to whole seconds.
  loops; STOP ends it at the end of the chunk in flight; silence; the 2nd START works
                              -> MessageCancelFirst works from a cave (probe180's question,
                                 answered again here at a 4x shorter latency)
  keeps looping after STOP    -> the cancel did not find the message: press STOP once more; a
                                 press that lands in a GAP then STARTs a second chain (two polls
                                 pending, doubled seams: kill switch). Next step is
                                 MessageFlushTask(0xBA3C) (stub 0x6e), ONE change, in a later probe.
  a START press does nothing (no noise, no id), every time
                              -> MessageCancelFirst returned TRUE with nothing pending: every
                                 press reads as a STOP (probe180's second failure row)
  "call ended" 0x21 while music plays
                              -> the DSP went away at a seam; the loop is over, nothing is
                                 pending, the next press is a START (probe179 press B)
  "bluetooth off" 0x3E on START
                              -> no .kap loaded (nothing streaming): music is not playing
  "and" 0x10 at a seam or on START
                              -> StreamKalimbaSink(3) returned 0
  0x22 / 0x1B / 0x24 / 0x25 at a seam or on START
                              -> FileFind dir / FileFind file / StreamFileSource /
                                 TransformAdpcmDecode or TransformStart refused; port free;
                                 nothing re-armed. After MANY seams a 0x24 or 0x25 means a
                                 per-chunk leak binds (3.7x sooner than in probe180)
  "ended" 0x26 heard          -> the WRONG image is on the speaker (probe179)
  a RESTART at any poll or press
                              -> the busy read (as in 179) or MessageCancelFirst (as in 180)
                                 is the crasher; 0x1072 at 8000 is the least likely suspect
                                 (it is the same message as before with a different word) -
                                 but it is also a NEW value to the DSP: if 180 was clean and
                                 181 restarts at a seam, suspect the rate first
  loud runaway / change of character
                              -> a logic error touched a busy port (NOT expected): Bluetooth
                                 long press, then POWER off
  1 chunk then silence, no id -> as 179: the tick was never delivered from this hook, or the
                                 read stays busy forever (179/180 have already answered this)
  KILL SWITCHES if STOP fails, in this order: (1) Bluetooth long press (the pairing teardown
  ends our running transform; the next poll reads the gate FALSE, speaks 0x21 and re-arms
  nothing; re-pair afterwards); (2) pause the music, only if probe179 press B said the unload
  beats the poll; (3) POWER off with USB unplugged (~20 s).

## SIMULATED (tools/cavesim.py world model, offline; the model is not the firmware)
build/hook/gate_probe181.py: probe180's 25 scenarios (with the chunk-count expectations
re-derived for the 3.0 s period) plus 6 rate/latch scenarios: stock rate 8000 (default),
--latch immediate, --stock-rate 7000 (chunk 1 at 7000 Hz / 2996 ms, seam 4 ms), --stock-rate
4000 (chunk 1 5243 ms, seam 757 ms), 7000 + immediate, and two sessions with the DSP unloaded
and reloaded (the second session's chunk 1 plays at the stock rate again). Rules R1-R6 report
no violation except the same three accepted/inherited cases as probe180. MessageCancelFirst is
modelled as header semantics (hypothesis); the latch is modelled as the field-log observed it
(late, n=2); the model cannot say what the real DSP does with 8000.
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
RATE     = 8000          # probe181: THE ONE CHANGE. 0x1072 word a. Every audio probe so far sent 2000; 8000 is the
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
POLL_MS = 1000           # probe179: the poll period for PROVING (DESIGN: floor 50 ms; 1000 ms
                         #   keeps the gap between chunks audible and the load on the loop low)
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
# probe181 (as 180): dispatched through the TaskData at CAVE+1/CAVE+2 by the 1 s poll the press (and
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
W(*ca.imm_words(POLL_MS, 0x14))     # ld AL,#1000
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
W(*ca.imm_words(RATE, 0x10))    # ld AH,#8000  (probe181; was 2000)
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

# probe181: the ONE change, asserted. Against probe180's cave (if its words file is present) exactly
# the two words of GATE's `ld AH,#RATE` may differ: the cave is probe180 + a rate immediate.
_P180 = "build/hook/probe180_words.json"
if os.path.exists(_P180):
    _old = {int(k, 16): v & 0xFFFF for k, v in json.load(open(_P180)).items()}
    _diff = sorted(x for x in set(_old) | set(out)
                   if (_old.get(x) is None) != (out.get(x) is None)
                   or (_old.get(x) is not None and _old[x] != (out[x] & 0xFFFF)))
    _g = label_addr["GATE"]
    assert _diff == [_g, _g + 1], ("probe181 must differ from probe180 in GATE's ld AH,#RATE only",
                                   [hex(x) for x in _diff])
    print("vs probe180: %d words differ, %s = GATE's ld AH,#%d (%s -> %s)"
          % (len(_diff), [hex(x) for x in _diff], RATE,
             ' '.join('%04x' % _old[x] for x in _diff),
             ' '.join('%04x' % (out[x] & 0xFFFF) for x in _diff)))
else:
    print("vs probe180: probe180_words.json not present, delta not asserted")
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
