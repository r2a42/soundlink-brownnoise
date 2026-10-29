#!/usr/bin/env python3
"""probe145: THE REFILL LOOP -- sustained brown noise. probe134's proven one-shot
chain plus the timer, the handler and the rebuild cycle of
docs/deep/buffer-cadence.md sections 4b/4c. The deliverable press.

## What plays

The generator is a hand-written XAP rewrite of the zero-net block generator that
probe134 played (loud: -10 dBFS in-band, 88-96% of energy above 150 Hz, 0.00% clip
across eight seeds). 49 words inside RETFILL, which is what pays for the whole
refill machinery: probe113 needed 231 words and never fit; RESUME-HERE named
exactly this lever.

## THE PAIR-SHIFT RULE that reshaped the generator (found re-verifying Opus's
## 54-word version in OUR emulator -- it would have been wrong on hardware)

xapemu models `asl`/`asr` (0xA0/0xA4) as shifts of the **32-bit AH:AL pair**, and
the lifted compiler output of nib_fill confirms it: `0009 01A4` is `lsr #1` (the
0x0009 word selects logical), `04A0` is `asl #4`, and the compiler zeroes AH before
every right shift. Opus's generator kept its loop counter IN AH and shifted AL
alone -- on the chip every shift would have pulled counter bits into the sample.
Rebuilt here: the counter lives in frame slot 3, one `ld AH,#0` before the loop,
and AH stays 0 throughout because no shifted value overflows (r <= 0x88, so
r<<4 <= 0x880). Everything else is the probe134 lineage verbatim: the six priming
bytes 80 FF FF FF FF F7, nibble order high-first, q0/q1/q2 = 0x30^r / 0xCB^A^t /
0x84^t2^t with t = (r&0x80)>>4 and t2 = (r&0x08)<<4. The 2-word prefixed forms
(and #0x88/#0x80/#0xB400, xor #0x84/#0xCB) match the lifted words byte for byte.

## Structure (189 of 197 writable words)

  CAVE      entry jump (bra ARM)
  CAVE+1,2  the TaskData {0x0003, handler} -- flashed const the message loop only
            ever READS; data address 0xBA3C (docs/message-task-abi.md section 5)

  ARM (the hook, enterl -8):
    BSR 0xE06D                                  stock back-call FIRST
    KalimbaSendMessage(0x1072, 2000, 0, 0, 0)   THE GATE *IS* THE ARM (sent once):
       FALSE = no DSP loaded = bail with nothing allocated. At boot the hook fires
       during audio init BEFORE the DSP is up (probe141's harm evidence), so this
       is the boot-safe gate; on the press probe134 proved it returns TRUE here.
    buf = malloc(129)                           the single 138-word pool block
    buf[2] = StreamKalimbaSink(3)               port-3 handle (constant for the run)
    buf[0] = 0x4CE1                             LFSR seed (0 would stick: x=(x>>1)^0)
    BSR RETFILL                                 fill + source + transform + start
                                                + the first timer beat, on success

  HANDLER (message loop every 110 ms; Task in AL -- ignored, buf in AH):
    enterl -3 ; BSR RETICK ; leavel -3          buf rides in AH; RETICK stores it
                                                as its first act

  RETICK (enterl -8; buf saved to slot 2):
    ksink = buf[2]
    t = TransformFromSink(ksink)                Bose's own teardown order (fn_31e6f,
    if t { TransformStop(t); TransformDisconnect(t) }   which itself takes a Bose
                                                INSTANCE pointer, not a sink -- so
                                                the sequence is replayed, not called)
    StreamDisconnect(0, ksink)                  UNCONDITIONAL (rule 4, probe106)
    SourceClose(buf[1])                         rule 3 -- the probe105/106 leak;
                                                unconditional because a tick only
                                                ever follows a successful rebuild,
                                                the sole writer of buf[1]
    bra RETFILLBODY                             tail jump: RETICK's frame IS the
                                                frame RETFILLBODY expects (-8), so
                                                RETFILL's leavel returns to the
                                                HANDLER directly

  RETFILL (enterl -8; buf -> slot 2) / RETFILLBODY (frame already up):
    seed = buf[0]; X = buf+3; GEN inlined       6 priming + 40 zero-net blocks = 126 B
    buf[0] = final x                            the walk CONTINUES across refills
    src = StreamRegionSource(buf+3, 126)        one byte per word, low 8 bits
    buf[1] = src                                stored BEFORE the transform calls:
                                                every failure path below stops the
                                                loop, so it is never closed twice
    t = TransformAdpcmDecode(src, buf[2])       probe104's proven recipe
    TransformStart(t)                           on FALSE: SourceClose(src), die
    MessageSendLater(0xBA3C, buf, 0, 110)       rule 5: re-arm here and ONLY here

Buffer: buf[0] = LFSR state, buf[1] = source to close next tick, buf[2] = ksink,
buf[3..128] = 126 sample bytes. malloc(129) lands in the 138 pool
(docs/cave-heap.md). RATE = 2000 Hz (probe134's loud rate; 126 B = 252 samples =
126 ms), period 110 ms = 87% duty -- one missed tick survivable
(docs/deep/buffer-cadence.md 3e/3f).

## Deviations from section 4b, and why

* No `free` on failure paths: a failed arm leaks the one 138 block once and the
  press is over (no timer, no repeat). It also makes a second press a silent
  no-op -- the block is already held -- which is the desired idempotence.
* No `MessageSinkTask(ksink, 0)`: section 4b does not include it and the budget
  does not either. Risk: the prompt's task 0xbd4e stays registered on port 3 and
  sees MESSAGE_STREAM_DISCONNECT when our transform drains. Probes 105/106 ran
  36 refills/s under exactly that condition and died of the SOURCE leak, not of
  the registration.
* The arm never tears down or closes (it enters RETFILL directly): section 4b's
  own arm sequence has no teardown, and buf[1] is raw malloc memory at that point.
* RETICK's `SourceClose` is unconditional (probe113 dropped the same guard): the
  guarantee is structural, not a runtime check.

## What the press does (laptop connected, music PAUSED, long-press the BLUETOOTH
## button -- probe134's conditions)

  SUSTAINED BROWN NOISE until power-off   SUCCESS -- the deliverable. Power off is
                                          the stop button. A second press is a
                                          silent no-op (the 138 block is held).
  one ~1/8 s burst then silence           the arm worked, the loop did not: the
                                          timer never fired OR the first tick
                                          failed (the sim says the tick sequence
                                          itself is right; a silence here is the
                                          message-dispatch assumption failing).
  silence                                 the 0x1072 gate bailed (no DSP: wrong
                                          press conditions) or an arm-stage call
                                          failed. The sim covers each stage.
  noise at POWER-ON (no press)            the gate passed at boot: the DSP was
                                          already up when the hook fired. Benign
                                          (RAM-only, power-cycle clears it) but
                                          report it -- it falsifies the boot
                                          -timing assumption.
  reboot/loop at boot                     STOP and report; that is probe105/106
                                          territory.

NO flash writes anywhere; every side effect is RAM state. But the press starts an
UNSTOPPABLE loop (only power-off stops it) and the hook still auto-fires at boot --
owner go-ahead per the standing rule.

## Verification (build/hook/verify_probe145.py -- ALL CHECKS PASS)

* Arm: trap order KALMSG -> malloc -> KSINK -> RSRC -> ADPCM -> TSTART -> MSGLATER;
  the 126 bytes BYTE-EXACT against the CONSULT8 Python reference; x -> 0x8b96.
* Ticks 2..4: full teardown + close + refill + re-arm, each fill BYTE-EXACT with
  the LFSR CONTINUING (0x8b96 -> 0xafae -> 0x55a3 -> 0x648c).
* Nine failure paths (gate/malloc/ksink/RSRC/ADPCM/TSTART on both paths): every
  one leavel-s out, none re-arms.
* preflight/caveguard: 190 cave words, 0 outside the proven window, all branch
  forms attested in Bose firmware. decode-verify: all branches OK, boundaries OK.

Two encoding bugs the sim caught before a flash could have: RETFILL entered
against the CALLER's frame (RSRC got buf=3 -- the frame-establishing enterl was
on the wrong side of the entry label), and `ld AH,@(2,X)` was encoded 0x0213
(mode 3 = @(n,Y)) instead of 0x0212 -- the ADPCM call was receiving buf where
ksink belonged.

BUILT, NOT FLASHED. sha256 6169a28562368aea514fca99c2ab87555e00b9b6a549b85d24028348cd48a33b.
"""

import os, re, sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

_PROBE = re.match(r'assemble_(probe[0-9a-z]+)\.py$',
                  os.path.basename(os.path.abspath(__file__))).group(1)

CAVE = 0x3E21D
REDIRECT_EDITS = [("0x6fff1", "0x04"), ("0x6fff3", "0xd7"), ("0x6fff5", "0x3b"),
                  ("0x6fff6", "0xe0"), ("0x6fff7", "0x01"),
                  ("0x6fff8", "0x00"), ("0x6fff9", "0x00"),
                  ("0x6fffa", "0x00"), ("0x6fffb", "0x00"),
                  ("0x6fffc", "0x00"), ("0x6fffd", "0x00")]
AREA0 = 0x6EA30
CONST_BASE = 0x7400

BACK = 0xE06D
SPEAK = 0xDF7F
MALLOC = ca.STUB['malloc']
KALMSG = ca.STUB['KalimbaSendMessage']
KSINK = ca.STUB['StreamKalimbaSink']
RSRC = ca.STUB['StreamRegionSource']
ADPCM = ca.STUB['TransformAdpcmDecode']
TSTART = ca.STUB['TransformStart']
TFS = ca.STUB['TransformFromSink']
TSTOP = ca.STUB['TransformStop']
TDISC = ca.STUB['TransformDisconnect']
SDISC = ca.STUB['StreamDisconnect']
SRCLOSE = ca.STUB['SourceClose']
MSGLATER = ca.STUB['MessageSendLater']

RATE = 2000
NBYTES = 126             # 6 priming + 40 x 3 zero-net blocks
BUF_WORDS = 129          # 3 state + 126 sample bytes -> the 138 pool
SEED = 0x4CE1
REFILL_MS = 110          # 126 ms of audio per fill; 87% duty
TASK_ID = None           # the MessageId IS buf (the handler reads AH as buf)
DIAG_ID = 0x1F           # "muted": a tick's rebuild failed
TASK_ADDR = 0xBA3C       # const_addr(CAVE+1) -- the TaskData lives at CAVE+1, CAVE+2

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
def in_run(cw): return any(a <= cw < b for a, b in _runs)

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

# CAVE = entry jump. CAVE+1, CAVE+2 = the TaskData {hwrd, lwrd} of the handler,
# flashed data the message loop only ever READS (docs/message-task-abi.md section 5).
# The handler's address is known only after layout, so the low word is patched then.
# Code proper starts at CAVE+3; execution never falls into the TaskData because the
# entry jump skips it and every function exits by leavel/rts.
TASK_AT = CAVE + 1
CODE_AT = CAVE + 3
assert blind(TASK_AT) and in_run(TASK_AT) and blind(CODE_AT) and in_run(CODE_AT)
assert ca.const_addr(TASK_AT) == TASK_ADDR, (hex(ca.const_addr(TASK_AT)),)

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))

# ------------------------------------------------------------------- the ARM
LBL("ARM")                      # the hook's entry jump at CAVE targets this label
W(0xF80B)                       # enterl -8
BSR(BACK)                       # stock back-call first, probe77's proven order

# GATE *IS* THE ARM: 0x1072 once, at 2000 Hz, words b/c/d = 0 (probe134 verbatim).
# Hand-staged: one ld AL,#0 feeds all three zero stack args (st never touches AL).
W(0x0014)                       # ld AL,#0
W(0x0027); W(0x0127); W(0x0227) # b = c = d = 0         slots 0..2
W(*ca.imm_words(RATE, 0x10))    # ld AH,#2000   arg2 = rate
W(*ca.imm_words(0x1072, 0x14))  # ld AL,#0x1072 arg1 = MESSAGE_SET_TONE_RATE
BSR(KALMSG)
W(0x0084); BR(0xF4, "OUT")      # FALSE = no DSP = boot-safe silent bail

ca.call1(W, BSR, MALLOC, al=('imm', BUF_WORDS))
W(0x0427)                       # st AL,@(4,Y)  buf (slot4: above the stack args)
W(0x0084); BR(0xF4, "OUT")      # pool exhausted: silent no-op

ca.call1(W, BSR, KSINK, al=('imm', 3))
W(0x0084); BR(0xF4, "OUT")      # no port-3 sink: silent no-op (block leaks once)
W(0x041B)                       # ld X,@(4,Y)
W(0x0226)                       # st AL,@(2,X)  buf[2] = ksink
W(*ca.imm_words(SEED, 0x14))    # ld AL,#0x4CE1 (prefixed: greedy digits 0x4D/0xE1)
W(0x0026)                       # st AL,@(0,X)  buf[0] = seed (0 would stick)
                                # (buf[1] needs no init: the handler only runs if
                                #   the rebuild below stored a real src there)
W(0x0417)                       # ld AL,@(4,Y)
BSR("RETFILL")                  # fill, wire, start, arm the timer on success

LBL("OUT")                      # failure falls through here too: same leavel
W(0xF80F)                       # leavel -8

# --------------------------------------------------------------- the HANDLER
# Runs in the main VM message loop (docs/message-task-abi.md section 6: safer than
# the button handler). Task in AL (ignored -- the TaskData is read-only const),
# buf in AH (the MessageId). enterl -3: one usable slot, which is all it needs --
# everything else happens inside RETICK, in ITS frame.
LBL("HANDLER")
W(0xF60B)                       # enterl -3 (saves the return; no slots needed)
BSR("RETICK")                   # teardown, close, refill, rebuild, re-arm.
                                #   buf rides in AH: RETICK's first act is to
                                #   store it, and the Task in AL is ignored
W(0xF60F)                       # leavel -3

# ------------------------------------------------------------------- RETICK
# The tick's teardown half: Bose's order (fn_31e6f's, minus the instance
# bookkeeping we do not have), then the close of the previous source, then the
# fill+build+timer half in its own frame. buf arrives in AL. The HANDLER
# (6 words) calls RETICK with the MessageId; the ARM calls RETFILL directly.
# GEN and TIMER are INLINED in RETFILL. GEN clobbers frame slots 0/1/3/4/5 and
# zeroes AH (the pair-shift zero); buf lives in slot 2, the one slot it does not
# touch. TIMER's stack args (slots 0-2) land on dead slots: buf (slot 2) is read
# into AH before the delay's low word overwrites it.
LBL("RETICK")
W(0xF80B)                       # enterl -8
W(0x0223)                       # st AH,@(2,Y)  buf (id in AH from the handler)
W(0x021B)                       # ld X,@(2,Y)
W(0x0216)                       # ld AL,@(2,X)  ksink
W(0x0527)                       # st AL,@(5,Y)
BSR(TFS)                        # TransformFromSink(ksink) -- fn_31e6f's order:
W(0x0427)                       # st AL,@(4,Y)  t
W(0x0084); BR(0xF4, "NOTRANS")
BSR(TSTOP)                      # TransformStop(t): arg1 is already in AL
W(0x0417); BSR(TDISC)           # TransformDisconnect(t)
LBL("NOTRANS")
W(0x0014)                       # ld AL,#0      source arg = 0
W(0x0513)                       # ld AH,@(5,Y)  ksink
BSR(SDISC)                      # StreamDisconnect(0, ksink) -- UNCONDITIONAL
W(0x021B)                       # ld X,@(2,Y)
W(0x0116)                       # ld AL,@(1,X)  previous source -- ALWAYS valid:
                                #   a tick only ever follows a successful rebuild,
                                #   its only writer (probe113's dropped guard,
                                #   now airtight)
BSR(SRCLOSE)                    # rule 3 -- the call probes 105/106 omitted
BR(0xE0, "RETFILLBODY")         # TAIL JUMP into the fill+build+timer half.
                                #   RETICK's frame (-8) IS the frame the body
                                #   expects: buf is already in slot 2 (st AH
                                #   above), and RETFILL's own leavel -8 pops
                                #   THIS frame and returns to the HANDLER.

# ---- RETFILL(buf=AL): the fill+build+timer half, ITS OWN FUNCTION with its own
# frame -- the ARM enters here directly (first beat: nothing of ours is connected
# yet, so no teardown and no close; buf[1] is raw malloc memory), and RETICK's
# tail jumps into its body with the frame already established. GEN and TIMER are
# inlined. GEN clobbers frame slots 0/1/3/4/5 and zeroes AH (the pair-shift
# zero); buf lives in slot 2, the one slot it does not touch. TIMER's stack args
# (slots 0-2) land on dead slots: buf (slot 2) is read into AH before the delay's
# low word overwrites it.
LBL("RETFILL")
W(0xF80B)                       # enterl -8
W(0x0227)                       # st AL,@(2,Y)  buf
LBL("RETFILLBODY")
W(0x021B)                       # ld X,@(2,Y)
W(0x0016)                       # ld AL,@(0,X)  LFSR state
W(0x0127)                       # st AL,@(1,Y)  -> the generator's seed slot
W(0x0338)                       # add X,#3      write pointer = buf+3

# ---- GEN, inlined: 6 priming bytes + 40 zero-net blocks. asr/asl shift the
# 32-bit AH:AL pair, so AH is zeroed once here and nothing in the loop
# overflows into it (r <= 0x88 -> r<<4 <= 0x880). Counter in slot 3.
W(0x8014)                       # ld AL,#0x80
W(0x0026)                       # st AL,@(0,X)   prime[0]
W(0x7FD4)                       # xor AL,#0x7F -> 0xFF
W(0x0126); W(0x0226); W(0x0326); W(0x0426)   # prime[1..4] = 0xFF
W(0x08D4)                       # xor AL,#0x08 -> 0xF7
W(0x0526)                       # prime[5]
W(0x0638)                       # add X,#6      past the priming
W(0x0010)                       # ld AH,#0      the pair-shift zero
W(0x2814)                       # ld AL,#40     block counter
W(0x0327)                       # st AL,@(3,Y)
LBL("GENLOOP")
W(0x0117)                       # ld AL,@(1,Y)  x
W(0x01C4)                       # and AL,#1
W(0x0074)                       # neg AL        0/0xFFFF
W(0xB400, 0x00C4)               # and AL,#0xB400  (2-word prefixed, like the lift)
W(0x0427)                       # st AL,@(4,Y)  mask
W(0x0117)                       # ld AL,@(1,Y)  x again (slot1 still holds it)
W(0x01A4)                       # asr #1        pair shift, AH=0 -> logical
W(0x04D7)                       # xor AL,@(4,Y) ^= mask
W(0x0127)                       # st AL,@(1,Y)  new x
W(0x0100, 0x88C4)               # and AL,#0x88    r
W(0x0027)                       # st AL,@(0,Y)  slot0 = r
W(0x30D4)                       # xor AL,#0x30
W(0x0026)                       # st AL,@(0,X)  out0
W(0x0017)                       # ld AL,@(0,Y)  r
W(0x04A4)                       # asr #4        r>>4, bit3 = r's bit7
W(0x08C4)                       # and AL,#0x08  t
W(0x0527)                       # st AL,@(5,Y)
W(0x0017)                       # ld AL,@(0,Y)  r
W(0x04A0)                       # asl #4        bit3 -> bit7 (no overflow: r<=0x88)
W(0x0100, 0x80C4)               # and AL,#0x80  t2
W(0x05D7)                       # xor AL,@(5,Y) t2 ^ t
W(0x0100, 0x84D4)               # xor AL,#0x84  (prefixed: lift line 65)
W(0x0226)                       # st AL,@(2,X)  out2
W(0x0517)                       # ld AL,@(5,Y)  t
W(0x04A0)                       # asl #4        A = t<<4 = r & 0x80
W(0x05D7)                       # xor AL,@(5,Y) A ^ t
W(0x0100, 0xCBD4)               # xor AL,#0xCB  (prefixed: lift line 60)
W(0x0126)                       # st AL,@(1,X)  out1
W(0x0338)                       # add X,#3
W(0x0317)                       # ld AL,@(3,Y)  counter
W(0xFF34)                       # add AL,#0xFF  -1 (sets Z)
W(0x0327)                       # st AL,@(3,Y)
BR(0xF0, "GENLOOP")             # bne while counter != 0

# ---- source + transform + start
W(0x021B)                       # ld X,@(2,Y)   X is the link register: reload
W(0x0117)                       # ld AL,@(1,Y)  final x
W(0x0026)                       # st AL,@(0,X)  buf[0] = x (the walk continues)
W(0x0217)                       # ld AL,@(2,Y)
W(0x0334)                       # add AL,#3     buf+3
W(0x7E10)                       # ld AH,#126
BSR(RSRC)
W(0x0084); BR(0xF4, "RBFAIL")   # 0: buf[1] still holds the previous (live) source
W(0x021B)                       # ld X,@(2,Y)
W(0x0126)                       # st AL,@(1,X)  buf[1] = src (failure paths below
                                #   never re-arm, so it is never closed twice)
W(0x0212)                       # ld AH,@(2,X)  ksink (mode 2 = @(n,X): 0x12)
BSR(ADPCM)
W(0x0427)                       # st AL,@(4,Y)  t (slot4 is free: the old t is dead)
W(0x0084); BR(0xF4, "RBFAILSRC")
W(0x0417)                       # ld AL,@(4,Y)
BSR(TSTART)
W(0x0084); BR(0xF4, "RBFAILSRC")

# ---- TIMER, inlined: MessageSendLater(cave_task, buf, 0, 110). message slot0,
# delay LOW slot2, HIGH slot1 (docs/message-task-abi.md section 1).
W(0x0213)                       # ld AH,@(2,Y)  arg2 = buf FIRST: slot2 is about
                                #   to be overwritten by the delay's low word
W(0x0014); W(0x0027)            # message = 0          slot0
W(0x0127)                       # (AL still 0) delay high = 0   slot1
W(0x6E14); W(0x0227)            # delay low = 110      slot2 (buf is dead now)
W(*ca.imm_words(TASK_ADDR, 0x14))   # ld AL,#0xBA3C  arg1 = the cave's TaskData
BSR(MSGLATER)
W(0xF80F)                       # leavel -8
LBL("RBFAILSRC")
W(0x021B)                       # ld X,@(2,Y)
W(0x0116)                       # ld AL,@(1,X)  the src stored above (never 0)
BSR(SRCLOSE)                    # a source nobody consumes is the probe105 leak
W(0xF80F)                       # leavel -8 (the return value has no reader:
                                #   both callers leavel on failure regardless)
LBL("RBFAIL")
W(0xF80F)                       # leavel -8

# ---- layout (proven machinery, verbatim from probe144: tightened reservation,
# ---- lazy next_blind, connector branches, last-word displacements) ----
bsr_size, br_size = {}, {}
label_addr = {}
changes = []
def needs_follow(item):
    k = item[0]
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
        if kind == "w": sz = len(prog[i][1])
        elif kind == "bsr": sz = bsr_size.get(i, 0)
        else: sz = br_size.get(i, 1)
        band_end = addr
        while blind(band_end) and in_run(band_end): band_end += 1
        try:
            nb_probe = next_blind(band_end)
            cs = 1 if -128 <= nb_probe - addr <= 127 else 2
        except AssertionError:
            nb_probe, cs = None, 0
        need = sz + (cs if needs_follow(prog[i]) else 0)
        if addr + need > band_end:
            assert nb_probe is not None, (
                'cave exhausted: %d writable words is not enough'
                % sum(y - x for x, y in _BANDS))
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
            if bsr_size.get(i, 2) != want: bsr_size[i] = want; ok = False
        else:
            want = (1 if -128 <= tgt - a <= 127
                    else 2 if br2_encodable(tgt - (a + 1))
                    else 3)
            if br_size.get(i, 1) != want:
                changes.append((iteration, hex(a), prog[i][2],
                                'item#%d' % i, want))
                br_size[i] = want; ok = False
    if ok: break
else:
    for c in changes[-10:]:
        print('  change:', c)
    raise SystemExit('no converge: last-addresses br %s / bsr %s'
                     % ({hex(addrs[i]): sz for i, sz in br_size.items() if prog[i][0] == 'br'},
                        {hex(addrs[i]): sz for i, sz in bsr_size.items() if prog[i][0] == 'bsr'}))

out = {}
for i, item in enumerate(prog):
    kind = item[0]
    a = addrs[i]
    if kind == "label": continue
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
for cslot, (nb, cs) in extra.items():
    v = nb - cslot
    if cs == 1:
        assert -128 <= v <= 127, (hex(cslot), hex(nb), v)
        out[cslot] = ((v & 0xFF) << 8) | 0xE0
    else:
        assert cslot + 1 not in out, hex(cslot + 1)
        for aa in range(max(-128, (v >> 8) - 2), min(128, (v >> 8) + 3)):
            if aa == 0: continue
            bb = v - aa * 256
            if -128 <= bb <= 127:
                out[cslot] = (aa & 0xFF) << 8
                out[cslot + 1] = ((bb & 0xFF) << 8) | 0xE0
                break
        else:
            raise AssertionError(('connector', hex(cslot), hex(nb), v))

# ---- the entry jump and the TaskData ----
entry_v = label_addr["ARM"] - CAVE
assert -128 <= entry_v <= 127
assert CAVE not in out, 'the entry jump word is already occupied'
out[CAVE] = ((entry_v & 0xFF) << 8) | 0xE0
HANDLER_AT = label_addr["HANDLER"]
assert TASK_AT not in out and TASK_AT + 1 not in out
for k, v in enumerate(ca.taskdata_words(HANDLER_AT)):
    out[TASK_AT + k] = v
print("handler a=%#x, TaskData a=%#x -> data %#06x = %s"
      % (HANDLER_AT, TASK_AT, TASK_ADDR,
         ' '.join('%04x' % x for x in ca.taskdata_words(HANDLER_AT))))

lo, hi = min(out), max(out)
print(f"cave spans {lo:#x}..{hi:#x}, {len(out)} words (iters {iteration+1})")
assert not [a for a in out if not blind(a) or not in_run(a)]
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
assert seen.get(CAVE) == label_addr["ARM"], (hex(CAVE), hex(label_addr["ARM"]), seen.get(CAVE))
for i, item in enumerate(prog):
    if item[0] != "label":
        assert addrs[i] in dstarts, (hex(addrs[i]), "boundary")
print("decode-verify: all branches OK, boundaries OK")

json.dump({hex(a): v for a, v in out.items()}, open(f"build/hook/{_PROBE}_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", f"build/hook/{_PROBE}_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open(f"build/hook/{_PROBE}_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> {_PROBE}_cmd.txt")
