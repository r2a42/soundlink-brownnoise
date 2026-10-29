#!/usr/bin/env python3
"""probe163: BISECT THE probe162 WEDGE. Step 1 alone: the DAC rewire, then the stock teardown.

## probe162 SAID: one of {rewire, 0x1072, GO} (or what follows GO) wedges the VM

Owner, 2026-10-08: "noise for a slow 9 count then silence"; info -f and TAP dead with USB
up = the wedge. No prompt, so fn_1f04c did not return FALSE and no build failed.

## THE CHANGE: on PARAMS_LOADED, ONLY the rewire, then undo it exactly as stock does

  1. fn_1f04c(&{0, 0xbb80, 0}) via DACON (unchanged from probe162).
     FALSE -> power off, 0x1F "muted" (unchanged).
  2. TRUE -> the stock prompt-end teardown, in fn_231b3's order: KalimbaPowerOff, then
     fn_1f12b = AudioOutputDisconnect (result ignored). Disconnecting is REQUIRED before
     speaking: the prompt builder calls fn_1f04c under PanicNull (0x22fd0), and fn_1f04c
     refuses while the "connected" bit 0x6d1:15 is set.
  3. Speak 0x20 "unmuted". The loop stops (no timer is pending on this path).
  NO 0x1072, NO GO, NO chunk build after the rewire.

## THE PRESS (laptop connected, music PAUSED, long-press BLUETOOTH). TIME IT.

  noise, silence, then "unmuted" (0x20)    SUCCESS: the rewire is clean and so is its stock
                                           teardown. The wedge is in 0x1072 / GO / after GO.
  noise, silence, then "muted" (0x1F)      fn_1f04c refused (teardown did not run / no config)
  noise, then "bluetooth off" (0x3E)       the reload was refused (regression)
  noise, silence, then "voice prompts on"  IMPOSSIBLE in this image: a stale image -- tell me
  "call with" (0x25)                       a tick found the DSP alive and its build failed
  the speaker restarts (start-up sounds)   a PanicNull fired (fn_1f12b's SinkClose, or the
                                           prompt builder's own fn_1f04c): a crash, not a wedge
  noise, then silence that never ends      I check `bose-dfu info -f`: dead = fn_1f04c ITSELF
                                           wedges -> unplug USB, hold POWER ~20 s, reconnect,
                                           POWER, and I flash stock
  silence from the start                   the ARM gate bailed: conditions not met

No id collides with a stock prompt in this state (0x00/0x09 avoided; "unmuted" is spoken
by the stock firmware only on a mute toggle, which this press does not make).
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
KALTASK  = ca.STUB['MessageKalimbaTask']   # 0x1cd: route DSP messages to a task
KALPOFF  = ca.STUB['KalimbaPowerOff']      # 0x1be: the teardown's own call (0x317d9)
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
DIR_DATA, _DIR_AH = _pool_ah("NowSpeakTTS")

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
            _REGION_BANDS.append((_a, _b)); _a = _b
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

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))
def REGION(): prog.append(("region",))   # everything after it starts in the code region
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

# ---- the two path strings, right after the ARM's leavel (probe161: moved up
# from the end so the layout places them while 8+-word bands are still free --
# at the end, fragmentation left none). Their char words are never executed. EACH IS ONE ITEM, so the layout must place it whole, and the
# assembler asserts contiguity afterwards.
LBL("STRFILE")
W(*[ord(c) for c in FILENAME])  # probe162: no NUL -- FileFind takes the length (7)

# --------------------------------------------------------------- the HANDLER
# Runs in the main VM message loop, reached through the flashed const TaskData
# at CAVE+1/CAVE+2 -- the dispatch path probes 145, 146 and 147 all proved on
# hardware. Everything happens inside RETICK, in ITS frame.
LBL("HANDLER")
W(0xF80B)                       # enterl -8: the SAME frame as RETICK, so the
                                #   handler can tail-branch into RETICK's body and
                                #   share its power-off/speak tail. Slots 0..5
                                #   usable, 6-7 the return; the Message is @(8,Y).
# ---- dispatch on the MessageId (AH), the form Bose's PIO handler uses (0x07f1c):
#   0       our chunk timer                          -> RETICK
#   0x8024  MESSAGE_FROM_KALIMBA                     -> switch on msg[0]
#   else    (0x802A LONG, 0x8022, ...)               -> ignore
W(0x0080); BR(0xF4, "RETICKBODY")   # cmp AH,#0 ; beq -> RETICK past its enterl
W(*ca.imm_words(0x8024, 0x80)); BR(0xF0, "HOUT")   # cmp AH,#0x8024 ; bne HOUT
W(0x081B)                       # ld X,@(8,Y)   the Message
W(0x0016)                       # ld AL,@(0,X)  msg[0] = the DSP's message id
W(*ca.imm_words(0x1000, 0x84)); BR(0xF4, "READY")  # MUSIC_READY ?
W(*ca.imm_words(0x1015, 0x84)); BR(0xF0, "HOUT")   # PARAMS_LOADED ? else ignore
                                #   (0x8000 is DSP->FIRMWARE and never reaches us;
                                #   anything else is ignored SILENTLY -- a prompt
                                #   now would load NowSpeakTTS over a running DSP)

# ---- PARAMS_LOADED: the DSP accepted the stock configuration. Power off and
# speak -- the probe160 path, proven clean.
# ---- *** THE PROBE162 CHANGE *** probe161 heard "voice prompts on" here: the
# reloaded DSP accepted SETPLUGIN + LOADPARAMS from our task. Now finish the stock
# bring-up instead of powering off (docs/deep/dsp-output-wiring.md):
#  1. rewire the DAC. The A2DP teardown ran fn_1f12b = AudioOutputDisconnect, which
#     closed the DAC sinks and cleared "connected" (0x6d1 bit 15) but kept the config
#     (0x6d0). fn_1f04c(&params) is the stock audio_output connect: ports 5/6 -> DAC
#     A/B, rate, SinkSynchronise, unmute. params = {0, 0xbb80, 0} (48 kHz, plain
#     connect, no outputs disabled) exactly as the stock prompt builder passes at
#     0x22fc8-0x22fd0 -- and, like it, ON THE STACK: fn_1f20f WRITES the rate back
#     into params, so they must not live in const memory. Slots 3..5 (the handler
#     shares RETICK's enterl -8 frame; slots 6-7 are the return, Message at @(8,Y)).
#  2. GATE = 0x1072: arm the tone port before GO, the stock order (field log: 0x1072
#     before GO stores the config; port 3 is not read until after GO).
#  3. GO = KalimbaSendMessage(0x7000, 0). Safe now: GO without SETPLUGIN is what
#     halted the DSP in probe96, and SETPLUGIN was accepted.
#  4. HAVEDSP: build port 3 <- data_us via ADPCM and arm the 9.5 s timer, so the loop
#     carries on with our DSP, which no A2DP teardown owns.
BSR("DACON")                    # fn_1f04c(&{0, 0xbb80, 0}) -> bool (region subroutine)
W(0x0084); BR(0xF4, "DACBAD")   # FALSE: not torn down / no config -> 0x1F
# ---- *** THE PROBE163 CHANGE *** rewired: undo it the stock way, then speak.
# fn_231b3's order: KalimbaPowerOff, then fn_1f12b (AudioOutputDisconnect). The
# disconnect is required: the prompt builder's fn_1f04c is under PanicNull.
W(0x2014)                       # ld AL,#0x20 "unmuted"
W(0x0027)                       # st AL,@(0,Y)
BSR(KALPOFF)                    # KalimbaPowerOff
BSR(FN1F12B)                    # AudioOutputDisconnect; result ignored
W(0x0017)                       # ld AL,@(0,Y)  0x20
BR(0xE0, "SAY")                 # speak, leavel, no re-arm

# ---- MUSIC_READY: answer it exactly as the stock handler does at
# 0x3119b-0x311b2: KalimbaSendMessage(0x1020 SETPLUGIN, code, 0,0,0) with a
# Panic on FALSE (we speak instead), then KalimbaSendMessage(0x1012 LOADPARAMS,
# 0x2270, 0,0,0) with the result ignored. code = fn_30fc5(variant) = table
# @0xcce4[1] = 1 for the SBC plugin record {0003 0dcc 1000}; the DSP's SETPLUGIN
# handler (PM-flash 0x325a) accepts 1/5/8. No 0x1018 (stock sends it only when
# an instance field is set), no GO, no 0x1072, no port -- one step.
LBL("READY")
W(0x0110)                       # ld AH,#1      SETPLUGIN code: SBC
W(*ca.imm_words(0x1020, 0x14))  # ld AL,#0x1020
BSR("KSEND")
# (no FALSE check: the stock code Panics on it, but KalimbaSendMessage is FALSE
# only when no .kap is loaded, and this DSP spoke to us one message ago. A FALSE
# would surface as silence with the VM alive. Cut for budget.)
W(*ca.imm_words(0x2270, 0x10))  # ld AH,#0x2270 the PS-key base, verbatim
W(*ca.imm_words(0x1012, 0x14))  # ld AL,#0x1012 LOADPARAMS
BSR("KSEND")                    # result ignored, as at 0x311b2
# (A 3000 ms PARAMS_LOADED timeout was designed here and cut for budget: ~21
# words over the 197 ceiling. Silence is resolved from the laptop instead.)
BR(0xE0, "HOUT")                # the DSP stays up, configured, waiting for GO

LBL("HOUT")
W(0xF80F)                       # leavel -8

# ------------------------------------------------------------------- RETICK
# The whole build, with NO saved state: it re-derives the sink and both file
# indices every time, so the ARM and the HANDLER can share it verbatim.
LBL("RETICK")
W(0xF80B)                       # enterl -8
LBL("RETICKBODY")              # the handler enters here on its timer id

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
# ---- *** PROBE159 CHANGE 2 of 2 *** own the DSP's mailbox BEFORE loading it.
# probe158 loaded sbc_decoder with whatever Kalimba task the A2DP teardown had
# left registered, so the fresh DSP's first messages went to a stock handler
# whose context that teardown had just destroyed -- and the VM wedged at the
# first reload. MessageKalimbaTask(ours) is what the stock loader itself does
# first (fn_315e7: 0x316b9 MessageKalimbaTask, then 0x316ce KalimbaLoad), and
# the handler above drops everything that is not our timer id.
W(*ca.imm_words(TASK_ADDR, 0x14))   # ld AL,#0xBA3C  the cave's own TaskData
BSR(KALTASK)                    # MessageKalimbaTask(ours); old task returned, ignored
W(*ca.imm_words(len(KAPPATH), 0x14))    # ld AL,#27     the length in WORDS
W(0x0027)                       # st AL,@(0,Y)  arg3 FIRST
W(0x0114)                       # ld AL,#1      arg1 = FILE_ROOT
W(*_KAP_AH)                     # ld AH,#<pool addr of the .kap path>
BSR(FILEFIND)
W(0x0084); BR(0xF4, "RELOADBAD")    # FILE_NONE -> cannot even try
BSR(KALLOAD)                    # AL carries the index, exactly as the stock site
W(0x0084); BR(0xF4, "RELOADBAD")    # FALSE -> the load was refused
# ---- *** PROBE159: LOADED. NOW STOP. *** No 0x1072, no StreamKalimbaSink, no
# transform, no SPEAK, no re-arm -- every one of those was in probe158's tick
# after this exact point, and the VM wedged. The observation is the DSP's own
# first message: sbc_decoder sends MUSIC_READY (0x1000) unsolicited at PM 0x24d,
# and because the mailbox is ours it lands in HANDLER as MESSAGE_FROM_KALIMBA.
W(0xF80F)                       # leavel -8

LBL("HAVEDSP")
# ---- ksink = StreamKalimbaSink(3)
ca.call1(W, BSR, KSINK, al=('imm', 3))
W(0x0227)                       # st AL,@(2,Y)  ksink
W(0x0084); BR(0xF4, "BUILDBAD")

# ---- (probe161) StreamDisconnect(0, ksink) REMOVED for budget. It only mattered
# for a SECOND healthy build on the same sink, and none happens: every tick from
# probe157 on found the DSP gone (the ~7 s pairing teardown), so the only build
# that runs is the ARM's first one, on a fresh port.

# ---- dir = FileFind(FILE_ROOT, "NowSpeakTTS", 11). Length into @(0,Y) FIRST.
W(*ca.imm_words(len(DIRNAME), 0x14))    # ld AL,#11
W(0x0027)                       # st AL,@(0,Y)  arg3 = length in words
W(0x0114)                       # ld AL,#1      arg1 = FILE_ROOT
W(*_DIR_AH)                     # ld AH,#<pool copy of "NowSpeakTTS"> (probe162:
                                #   the firmware's own const-pool string, as for the
                                #   .kap path; docs/deep/stock-helpers.md option A)
BSR(FILEFIND)
W(0x0084); BR(0xF4, "BUILDBAD")
W(0x0327)                       # st AL,@(3,Y)  dir index

# ---- file = FileFind(dir, "data_us", 7)
W(*ca.imm_words(len(FILENAME), 0x14))   # ld AL,#7
W(0x0027)                       # st AL,@(0,Y)
W(0x0317)                       # ld AL,@(3,Y)  arg1 = the DIRECTORY index
LBL("SETAHFILE")
W(0x0000, 0x0010)               # ld AH,#<data addr of STRFILE> (patched below)
BSR(FILEFIND)
W(0x0084); BR(0xF4, "BUILDBAD")

# ---- src = StreamFileSource(file); the index is already in AL.
BSR(FILESRC)
W(0x0084); BR(0xF4, "BUILDBAD")  # (restored in probe162: the region has room)

# ---- t = TransformAdpcmDecode(src, ksink); TransformStart(t)
W(0x0213)                       # ld AH,@(2,Y)  ksink (AL still holds src)
BSR(ADPCM)
W(0x0084); BR(0xF4, "BUILDBAD")
BSR(TSTART)                     # AL carries the transform; result unchecked
                                #   (probe161, budget): nothing below uses it

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

LBL("BUILDBAD")
W(0x2514)                       # ld AL,#0x25 "call with" -- ONE id for every
                                #   failure in the healthy build (sink, dir, file,
                                #   source, transform, start). probes 155-158
                                #   never fired any of the five separate ids this
                                #   replaces; the budget went to the handler.
BR(0xE0, "SAY")                 # NOT into OFFSAY: no power-off on a build failure
LBL("RELOADBAD")
W(0x3E14)                       # ld AL,#0x3E "bluetooth off" -- the SAME id
BR(0xE0, "SAY")                 #   probe157 used for "the DSP is gone", kept
                                #   deliberately: there it meant gone, here it
                                #   means gone AND unrecoverable (FileFind found
                                #   no sbc_decoder.kap, or KalimbaLoad refused
                                #   it). One sound, one escalating meaning, and
                                #   the field log carries the distinction.
LBL("DACBAD")                   # (probe162) fn_1f04c refused: power off, then
W(0x1F14)                       #   ld AL,#0x1F "muted", and fall into OFFSAY
LBL("OFFSAY")                   # (handler only) power the DSP off FIRST, then
W(0x0027)                       #   speak -- the probe160 order, proven clean
BSR(KALPOFF)                    #   st AL,@(0,Y) ; KalimbaPowerOff ; ld AL,@(0,Y)
W(0x0017)
LBL("SAY")                      # ...and fall through into the shared speech
BSR(SPEAK)                      # probe99's direct idiom, hardware-proven
W(0xF80F)                       # leavel -8, and NO re-arm: the loop stops here

# ---- GATE: KalimbaSendMessage(0x1072 SET_TONE_RATE, 2000, 0, 0, 0) -> bool in AL.
# Factored out because probe158 needs it THREE times -- the ARM's boot-safe
# check, the per-tick DSP-health test, and the re-arm after a reload -- and three
# inline copies cost 30 words against a 197-word ceiling. Its own frame holds the
# three zero stack args, which is where KalimbaSendMessage reads them from.
# ---- probe162: GATE and KSEND live WHOLE in the code region, entered ONLY by bsr
# (3-word bsr: Bose uses it 7,473 times). The first layout fell through into the
# region by a 3-word bra, a form Bose never emits; preflight refused it.
REGION()
LBL("GATE")
W(*ca.imm_words(RATE, 0x10))    # ld AH,#2000
W(*ca.imm_words(0x1072, 0x14))  # ld AL,#0x1072   ...and fall into KSEND
# ---- KSEND: KalimbaSendMessage(AL, AH, 0, 0, 0) -> bool in AL. probe161 sends
# three different messages (the gate, SETPLUGIN, LOADPARAMS), so the zero-slot
# frame is shared. AH is untouched by the st/ld AL below.
LBL("KSEND")
W(0xF80B)                       # enterl -8
W(0x0327)                       # st AL,@(3,Y)  the message id
W(0x0014)                       # ld AL,#0
W(0x0027); W(0x0127); W(0x0227) # b = c = d = 0        slots 0..2
W(0x0317)                       # ld AL,@(3,Y)
BSR(KALMSG)
W(0xF80F)                       # leavel -8, and AL carries the bool out

# ---- DACON (probe162, in the region): fn_1f04c(&params) -> bool in AL. Its OWN
# enterl -8 frame holds params on the stack (fn_1f20f writes the rate back into
# them), slots 3..5 exactly as the inline version had them in the handler's frame.
LBL("DACON")
W(0xF80B)                       # enterl -8
W(0x0014)                       # ld AL,#0
W(0x0327)                       # st AL,@(3,Y)  params[0] rate high = 0
W(0x0527)                       # st AL,@(5,Y)  params[2] flags = 0
W(*ca.imm_words(0xBB80, 0x14))  # ld AL,#0xbb80  48,000
W(0x0427)                       # st AL,@(4,Y)  params[1] rate low
W(0xE415)                       # ld AL,@0xffe4  Y
W(0x0334)                       # add AL,#3     AL = &params (data address Y+3)
BSR(FN1F04C)                    # fn_1f04c(&params) -> bool
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

# probe162: the region's stubs ride along in EVERY image that uses the region, and the
# things the cave READS (string, TaskData) must be in the const window.
for _a, _v in REGION_STUBS.items():
    assert _a not in out, hex(_a)
    out[_a] = _v
for _lbl in ("STRFILE",):
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
