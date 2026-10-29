#!/usr/bin/env python3
"""probe158: RELOAD THE DSP. The teardown is not avoidable, so stop avoiding it
and undo it.

## probe157 ANSWERED THE QUESTION THAT HAD BEEN OPEN SINCE probe104

Owner: **"7 seconds of noise and then 'bluetooth off'."** That id is the
gate-returned-FALSE branch, and `KalimbaSendMessage` returns TRUE only if a
`.kap` is loaded. So, measured rather than inferred:

**THE DSP IS GONE ABOUT SEVEN SECONDS AFTER THE PRESS.**

Which explains, at last, a number five unrelated architectures all produced:

  probe104   4.25 s   const-pool region source (by design)
  probe145   ~9 s     refill loop + per-tick SourceClose
  probe146   6-7 s    close removed
  probe147   ~6 s     rate-matched
  probe149   ~6 s     + ids
  probe150   ~6 s     + the transform id split
  probe151   ~6 s     + an explicit TransformDisconnect
  probe155   7 s      ONE source, ONE transform, nothing repeating
  probe157   7 s      + "bluetooth off": THE DSP IS GONE

Ten probes of pool arithmetic were explaining a number that had nothing to do
with pools. probe155 should have been the clue -- one source, one transform, no
possible accumulation, same seven seconds -- and probe157's single bool made it
unambiguous.

## WHY THE OBVIOUS FIX IS NOT AVAILABLE

The hook at 0x0AE0 fires on the enter-pairing path, and the cave runs the stock
back-call `fn_0e06d` first (probe77's rule). The tempting next move is to skip
that back-call so the speaker never enters pairing. **It would not work, and the
disassembly says so plainly: `fn_0e06d` is called from THIRTY-ONE sites**
(0x4e3, 0xae0, 0xd00, 0xd9e, 0xdad, 0x118b, ... 0x18cd8) **and it range-checks
its argument against 0x35, 0x2a, 0x51 and 0x3ec -- prompt ids.** It is the prompt
dispatcher, not the pairing action. Skipping it would silence a prompt and change
nothing about A2DP. The teardown happens upstream of this hook, in the event
handling that leads to it, and no edit inside the cave can prevent it.

So the teardown is a fact of this trigger. **This probe stops fighting it and
undoes it instead.**

## THE ONE CHANGE: WHEN THE GATE SAYS THE DSP IS GONE, LOAD IT BACK

probe157 already reads the gate on every rebuild and speaks when it is FALSE.
probe158 keeps that bool but acts on it:

    gate 0x1072 -> TRUE   the DSP is alive; carry on as probe157 does
                -> FALSE  **reload it**:
                            idx = FileFind(FILE_ROOT, 0xbd75, 27)
                            KalimbaLoad(idx)
                            gate 0x1072 again
                          and if that now says TRUE, build and keep playing

Every piece is proven or stock:

  * **`KalimbaLoad` from a cave is hardware-proven clean** -- that is probe93's
    whole result.
  * **`0xbd75` is the firmware's OWN const-pool copy of
    "sbc_decoder/sbc_decoder.kap"**, 27 chars, established by probe154 and
    verified again here at build time by searching `code` for the characters. No
    carried string, so no band-split hazard.
  * **The sequence is the stock firmware's.** `fn_22f6f` at `0x22f79`-`0x22f90`
    does `ld AL,#1` (FILE_ROOT) ; `ld AH,<name ptr>` ; `bsr FileFind` ; **`bsr
    KalimbaLoad` with the index straight through in AL** ; `cmp AL,#0` ; and
    later `ld AL,#3` ; `bsr StreamKalimbaSink`. Nothing sits between the FileFind
    and the KalimbaLoad, and port 3 is what the loaded DSP is addressed by
    afterwards. probe158 copies that order exactly.

If this works the loop becomes self-healing: pairing takes the decoder down,
the next tick notices, reloads it, re-arms the port and carries on. Seven-second
chunks, indefinitely, through a teardown that happens on every press.

## WHAT COULD STILL GO WRONG, NAMED IN ADVANCE

The honest uncertainty is whether a cave-driven `KalimbaLoad` of `sbc_decoder`
yields a port 3 that accepts a transform, or whether the DSP also needs
configuration the stock A2DP path normally supplies. probe96 wedged on
`KalimbaSendMessage(0x7000)`, so this probe sends nothing to the DSP except the
`0x1072` it already sends. If the reload loads but the port stays unusable, the
ids below say which step gave up, and the answer is still progress: it would mean
the deliverable needs its own DSP rather than Bose's.

## The press (laptop connected, music PAUSED, long-press the BLUETOOTH button)

**TIME IT.** Expect a seam every seven seconds -- that is a chunk boundary, and
now possibly a DSP reload as well.

  NOISE GOING ON PAST ~15 s        the reload works and the loop is SELF-HEALING.
                                   Keep timing; minutes means the deliverable is
                                   in reach. Power off to stop it.
  noise ~7 s, then "bluetooth      the DSP is gone AND UNRECOVERABLE: FileFind
  off" (0x3E)                      found no sbc_decoder.kap, or KalimbaLoad
                                   refused it. Same sound probe157 used for
                                   "gone", now meaning "gone and we could not get
                                   it back" -- the escalation is in the log.
  noise ~7 s, then "and" (0x10)    the reload was ACCEPTED but left no usable
                                   port 3 (StreamKalimbaSink returned 0). That
                                   would mean a cave-driven KalimbaLoad is not
                                   equivalent to the stock A2DP load, and the
                                   deliverable needs its own DSP rather than
                                   Bose'"'"'s. This is the most informative failure.
  noise ~7 s, then "call with"     the DSP is alive (gate TRUE) and the port
  (0x25)                           re-armed, but the transform was refused --
                                   with the sink disconnected first that points
                                   at allocation. Count the cycles.
  noise ~7 s, then "switching      StreamFileSource refused: a pool is dry.
  call" (0x24)
  noise ~7 s, then "conference     FileFind lost NowSpeakTTS, or data_us inside
  call" (0x22) / "call from        it, on a rebuild.
  unknown" (0x1B)
  noise ~7 s then SILENCE          the timer never fired.
  silence from the start           the gate bailed at the ARM: no DSP up, so the
                                   press conditions were not met.

## What is NOT changed

The hook, the redirects, the two-level FileFind onto the narrow
`NowSpeakTTS/data_us`, both path strings (one item each, asserted contiguous and
read back off the device), the corrected prefixed-pointer fold, the
`StreamDisconnect` that frees the sink, the 7500 ms re-arm, the flashed const
TaskData at data 0xBA3C, and the ARM's silent boot-safe bail.

BUILT, NOT FLASHED until the owner says so.
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
RATE     = 2000          # the tone rate every audio probe has used
SDISC    = ca.STUB['StreamDisconnect']
MSGLATER = ca.STUB['MessageSendLater']
KALLOAD  = ca.STUB['KalimbaLoad']
KAPPATH  = 'sbc_decoder/sbc_decoder.kap'   # the FIRMWARE'S own const-pool
                         #   copy; probe154 established it and the build
                         #   below re-finds it, so no carried string and
                         #   therefore no band-split hazard
TASK_ADDR = 0xBA3C       # const_addr(CAVE+1): the TaskData lives at
                         #   CAVE+1, CAVE+2, exactly as probes 145-151
                         #   had it -- the dispatch path those probes
                         #   proved on hardware
DELAY_MS = 9500          # just PAST the measured ~7 s chunk. probe156
                         #   fired at 5000 to keep the port from going
                         #   dry, but the rebuild now re-arms it with
                         #   0x1072, so the only thing left to avoid is
                         #   re-gating mid-stream -- which DOES purge
                         #   live audio (codec_tones.asm:507-513)
OVERSINK = ca.STUB['StreamPartitionOverwriteSink']
SETDIGEST = ca.STUB['PartitionSetMessageDigest']
SINKCLOSE = ca.STUB['SinkClose']
SINKFLUSH = ca.STUB['SinkFlush']
MEMMOVE = ca.STUB['memmove']
FN12E1A = 0x12E1A                       # Bose's SinkMap+SinkClaim helper (stock)
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

# ---- two SHORT carried strings, each emitted as ONE item so the layout cannot
# split it, and each asserted contiguous after layout. The cave's blind bands
# measure 14, 9 and 3 words, so "NowSpeakTTS/data_us" (20 words with its NUL)
# CANNOT fit in one band -- hence the two-level walk. file.h:18-28 supports it:
# FileFind takes the directory to start from, and FILE_ROOT is 1.
DIRNAME, FILENAME = "NowSpeakTTS", "data_us"

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
# ------------------------------------------------------------------- the ARM
# The ARM gates FIRST and bails SILENTLY on FALSE -- the boot-safety rule, since
# this hook auto-fires at power-on when no DSP is up and the speaker must not
# announce anything uninvited. RETICK gates AGAIN (see there), which at arm time
# is a harmless second send into a buffer with nothing in it yet; the difference
# is that RETICK SPEAKS when the gate fails, and the ARM does not.
LBL("ARM")
W(0xF80B)                       # enterl -8
BSR(BACK)                       # the stock back-call FIRST, probe77's order
BSR("GATE")                     # KalimbaSendMessage(0x1072, 2000, 0,0,0)
W(0x0084); BR(0xF4, "AOUT")     # FALSE -> no DSP -> SILENT bail, no id at all
BSR("RETICK")                   # build the first chunk and arm the timer
LBL("AOUT")
W(0xF80F)                       # leavel -8

# --------------------------------------------------------------- the HANDLER
# Runs in the main VM message loop, reached through the flashed const TaskData
# at CAVE+1/CAVE+2 -- the dispatch path probes 145, 146 and 147 all proved on
# hardware. Everything happens inside RETICK, in ITS frame.
LBL("HANDLER")
W(0xF60B)                       # enterl -3 (saves the return; no slots needed)
BSR("RETICK")
W(0xF60F)                       # leavel -3

# ------------------------------------------------------------------- RETICK
# The whole build, with NO saved state: it re-derives the sink and both file
# indices every time, so the ARM and the HANDLER can share it verbatim.
LBL("RETICK")
W(0xF80B)                       # enterl -8

# ---- *** THE PROBE157 CHANGE *** re-arm the port, and ask the DSP if it is
# still there. codec_tones.asm:252-260 disarms the port after ~30 ms of empty --
# which happens in every seam between chunks -- and :514-516 makes a fresh
# 0x1072 the ONLY thing that re-arms it. probe156 left this out and so would
# have fed a port nobody drains. Re-sending mid-stream is what hurt probes
# 105/106 (36 times a second); at a chunk boundary there is nothing to purge.
# AND the return value is the cheapest discriminator this project has had:
# KalimbaSendMessage is TRUE only if a .kap is loaded, so FALSE here means the
# DSP has gone -- which is the standing explanation for why FIVE unrelated
# architectures all died at ~6-9 s, probe155 included, where only one source and
# one transform ever existed and no pool could have been exhausted.
BSR("GATE")                     # KalimbaSendMessage(0x1072, 2000, 0,0,0)
W(0x0084); BR(0xF0, "HAVEDSP")  # TRUE -> the DSP is alive, carry straight on

# ---- *** THE PROBE158 CHANGE *** the gate says the DSP is GONE, so LOAD IT
# BACK. probe157 measured this condition; this probe undoes it. The sequence is
# the stock firmware's own, fn_22f6f at 0x22f79-0x22f80: FILE_ROOT in AL, the
# name pointer in AH, the length in @(0,Y), FileFind, and then KalimbaLoad with
# the index straight through in AL with nothing in between. KalimbaLoad from a
# cave is probe93's proven result, and the path is the firmware's own const-pool
# copy, so there is no carried string to be split across a blind band.
W(*ca.imm_words(len(KAPPATH), 0x14))    # ld AL,#27     the length in WORDS
W(0x0027)                       # st AL,@(0,Y)  arg3 FIRST
W(0x0114)                       # ld AL,#1      arg1 = FILE_ROOT
W(*_KAP_AH)                     # ld AH,#<pool addr of the .kap path>
BSR(FILEFIND)
W(0x0084); BR(0xF4, "RELOADBAD")    # FILE_NONE -> cannot even try
BSR(KALLOAD)                    # AL carries the index, exactly as the stock site
W(0x0084); BR(0xF4, "RELOADBAD")    # FALSE -> the load was refused

# ---- RE-ARM after the reload. This is REQUIRED, not redundant: the stock
# builder fn_22f6f takes StreamKalimbaSink(3) only AFTER its KalimbaLoad
# (0x22f7e -> 0x22f8f), so port 3 does not pre-exist the load, and the 0x1072
# that armed the OLD port died with it. An earlier draft of this probe cut this
# block for budget and would have rebuilt into an unarmed port.
BSR("GATE")                     # KalimbaSendMessage(0x1072, 2000, 0,0,0)
W(0x0084); BR(0xF4, "STILLDEAD")    # loaded, but the port will not arm

LBL("HAVEDSP")
# ---- ksink = StreamKalimbaSink(3)
ca.call1(W, BSR, KSINK, al=('imm', 3))
W(0x0227)                       # st AL,@(2,Y)  ksink
W(0x0084); BR(0xF4, "NOSINK")

# ---- StreamDisconnect(0, ksink): free the sink for a NEW transform. Not for
# memory -- probes 151/153 proved the VM cannot reclaim the transform or the
# source -- but for CONNECTIVITY: a second TransformAdpcmDecode on a sink that
# still has one attached would be refused. Harmless on the first pass, when
# nothing is attached yet, and the refill loop made this call 55 times a press.
W(0x0014)                       # ld AL,#0      source = none
W(0x0213)                       # ld AH,@(2,Y)  ksink
BSR(SDISC)

# ---- dir = FileFind(FILE_ROOT, "NowSpeakTTS", 11). Length into @(0,Y) FIRST.
W(*ca.imm_words(len(DIRNAME), 0x14))    # ld AL,#11
W(0x0027)                       # st AL,@(0,Y)  arg3 = length in words
W(0x0114)                       # ld AL,#1      arg1 = FILE_ROOT
LBL("SETAHDIR")
W(0x0000, 0x0010)               # ld AH,#<data addr of STRDIR>  (patched below)
BSR(FILEFIND)
W(0x0084); BR(0xF4, "NODIR")
W(0x0327)                       # st AL,@(3,Y)  dir index

# ---- file = FileFind(dir, "data_us", 7)
W(*ca.imm_words(len(FILENAME), 0x14))   # ld AL,#7
W(0x0027)                       # st AL,@(0,Y)
W(0x0317)                       # ld AL,@(3,Y)  arg1 = the DIRECTORY index
LBL("SETAHFILE")
W(0x0000, 0x0010)               # ld AH,#<data addr of STRFILE> (patched below)
BSR(FILEFIND)
W(0x0084); BR(0xF4, "NOFILE")

# ---- src = StreamFileSource(file); the index is already in AL.
BSR(FILESRC)
W(0x0084); BR(0xF4, "NOSRC")

# ---- t = TransformAdpcmDecode(src, ksink); TransformStart(t)
W(0x0213)                       # ld AH,@(2,Y)  ksink (AL still holds src)
BSR(ADPCM)
W(0x0084); BR(0xF4, "NOPLAY")
BSR(TSTART)                     # AL carries the transform
W(0x0084); BR(0xF4, "NOPLAY")

# ---- and ask again in DELAY_MS. MessageSendLater(cave_task, id, 0, delay):
# message slot0, delay HIGH slot1, delay LOW slot2 (message-task-abi.md §1).
W(0x0014); W(0x0027)            # message id = 0       slot0
W(0x0127)                       # (AL still 0) delay high = 0   slot1
W(*ca.imm_words(DELAY_MS, 0x14))    # ld AL,#5000
W(0x0227)                       # st AL,@(2,Y)  delay low (ksink is dead now)
W(0x0010)                       # ld AH,#0      the MessageId, set EXPLICITLY:
                                #   without this it would be whatever
                                #   TransformStart happened to leave in AH. The
                                #   handler does not need an id (it re-derives
                                #   everything), but passing a stale register
                                #   into a firmware trap is not something to
                                #   leave to chance.
W(*ca.imm_words(TASK_ADDR, 0x14))   # ld AL,#0xBA3C  arg1 = the cave's TaskData
BSR(MSGLATER)
W(0xF80F)                       # leavel -8 -- the chunk is playing, the timer
                                #   is set, and nothing else is held

LBL("STILLDEAD")
W(0x1414)                       # ld AL,#0x14 "auto off disabled" -- the .kap
BR(0xE0, "SAY")                 #   RELOADED but the port still will not arm: a
                                #   cave-driven KalimbaLoad is not equivalent to
                                #   the stock A2DP load, and the deliverable
                                #   needs its own DSP rather than Bose's
LBL("RELOADBAD")
W(0x3E14)                       # ld AL,#0x3E "bluetooth off" -- the SAME id
BR(0xE0, "SAY")                 #   probe157 used for "the DSP is gone", kept
                                #   deliberately: there it meant gone, here it
                                #   means gone AND unrecoverable (FileFind found
                                #   no sbc_decoder.kap, or KalimbaLoad refused
                                #   it). One sound, one escalating meaning, and
                                #   the field log carries the distinction.
LBL("NOPLAY")
W(0x2514)                       # ld AL,#0x25 "call with"
BR(0xE0, "SAY")
LBL("NOSRC")
W(0x2414)                       # ld AL,#0x24 "switching call"
BR(0xE0, "SAY")
LBL("NOFILE")
W(0x1B14)                       # ld AL,#0x1B "call from unknown"
BR(0xE0, "SAY")
LBL("NODIR")
W(0x2214)                       # ld AL,#0x22 "conference call"
BR(0xE0, "SAY")
LBL("NOSINK")
W(0x1014)                       # ld AL,#0x10 "and"
LBL("SAY")                      # ...and fall through into the shared speech
BSR(SPEAK)                      # probe99's direct idiom, hardware-proven
W(0xF80F)                       # leavel -8, and NO re-arm: the loop stops here

# ---- GATE: KalimbaSendMessage(0x1072 SET_TONE_RATE, 2000, 0, 0, 0) -> bool in AL.
# Factored out because probe158 needs it THREE times -- the ARM's boot-safe
# check, the per-tick DSP-health test, and the re-arm after a reload -- and three
# inline copies cost 30 words against a 197-word ceiling. Its own frame holds the
# three zero stack args, which is where KalimbaSendMessage reads them from.
LBL("GATE")
W(0xF80B)                       # enterl -8
W(0x0014)                       # ld AL,#0
W(0x0027); W(0x0127); W(0x0227) # b = c = d = 0        slots 0..2
W(*ca.imm_words(RATE, 0x10))    # ld AH,#2000
W(*ca.imm_words(0x1072, 0x14))  # ld AL,#0x1072
BSR(KALMSG)
W(0xF80F)                       # leavel -8, and AL carries the bool out

# ---- the two path strings, AFTER the final leavel so their char words are
# never executed. EACH IS ONE ITEM, so the layout must place it whole, and the
# assembler asserts contiguity afterwards.
LBL("STRDIR")
W(*([ord(c) for c in DIRNAME] + [0]))
LBL("STRFILE")
W(*([ord(c) for c in FILENAME] + [0]))

# ---- layout (proven machinery, verbatim from probe137/139/140) ----
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

# ---- patch the two FileFind string pointers, and PROVE each string is
# contiguous. probe141 had neither: its pointer fold was wrong whenever the low
# byte was >= 0x80 (XAP folds sext8(prefix)*256 + sext8(operand), so such a low
# byte is NEGATIVE and borrows from the high byte), and a carried string got
# split across blind bands with no check that it had not.
CONST_ORIGIN = 236514
def _str_ptr(label, text, setah):
    base = label_addr[label]
    words = [ord(c) for c in text] + [0]
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
_str_ptr('STRDIR', DIRNAME, 'SETAHDIR')
_str_ptr('STRFILE', FILENAME, 'SETAHFILE')

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
assert seen.get(CAVE) == CODE_AT, (hex(CAVE), hex(CODE_AT), seen.get(CAVE))
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
