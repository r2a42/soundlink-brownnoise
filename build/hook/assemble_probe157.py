#!/usr/bin/env python3
"""probe157: RE-ARM THE PORT, AND ASK THE DSP IF IT IS STILL THERE.

probe156 was built, flashed and then SUPERSEDED WITHOUT A PRESS, because a review
found a defect that would have made it fail even in the benign case. This probe
is probe156 with that defect fixed and one bool added -- and that bool is the
cheapest discriminator this project has had in ten probes.

## probe155's RESULT, AND THE PATTERN NOBODY HAD LINED UP

probe155: **"noise. fairly loud. 7 seconds. no voice prompt after noise."** The
whole chain worked. Now put that next to every other port-3 result:

  probe104   4.25 s   (by design -- a 17 KB const-pool region)
  probe145   ~9 s     refill loop, per-tick SourceClose
  probe146   6-7 s    same, close removed
  probe147   ~6 s     rate-matched
  probe149   ~6 s     + ids
  probe150   ~6 s     + the transform id split
  probe151   ~6 s     + an explicit TransformDisconnect
  probe155   7 s      ONE source, ONE transform, no timer, no teardown

**Five unrelated architectures, one death time.** And probe155 is the one that
breaks the leak explanation: it allocates exactly one source and one transform,
so accumulation CANNOT be why it stopped at seven seconds. Ten probes of pool
arithmetic were explaining a number that something else was setting.

The candidate that fits every row: the hook at 0x0AE0 fires only on
`EventUsrEnterPairing` (`docs/deep/hook-gates.md:16-24`), and the cave runs the
stock back-call `fn_0e06d` first -- so **every successful press really does put
the speaker into pairing**, which tears down A2DP and takes the `sbc_decoder`
DSP down with it. probe77's own docstring guessed at this years of probes ago:
"something else evicts the DSP -- most likely pairing tearing down A2DP, which
reloads the decoder". Once the DSP is gone, port 3 is gone, and no VM-side
cleverness brings it back.

That is a hypothesis, not a fact. **This probe makes it answer for itself.**

## THE DEFECT IN probe156, AND WHY IT COULD NOT HAVE WORKED

probe156 deliberately left the `0x1072` gate OUT of the rebuild, reasoning that
re-sending it purges the tone cbuffer (`codec_tones.asm:507-513`) -- the
probe105/106 bug. That reasoning was wrong in this context, for two reasons:

  * probes 105/106 were hurt because they re-sent `0x1072` **36 times a second,
    mid-stream**. At end-of-stream there is nothing left in the buffer to purge.
  * `codec_tones.asm:252-260` and `:514-516`: once the DSP's end-of-tone detector
    has disarmed the port -- which it does after ~30 ms of empty, i.e. in every
    seam between chunks -- **only a fresh `0x1072` re-arms it.**

So probe156 would have rebuilt the transform and fed it into a port nobody
drains. It could not have sustained even with a healthy DSP and a perfect timer.
It was flashed (cycle 32) and is superseded here with no press spent on it.

## THE TWO CHANGES

**1. The gate moves INTO the rebuild, so every cycle re-arms the port.** The ARM
still gates first and bails SILENTLY on FALSE -- that is the boot-safety rule,
because the hook auto-fires at power-on when no DSP is up and the speaker must
not announce anything uninvited. RETICK then gates again, which at arm time is a
harmless second send into a buffer that has nothing in it yet.

**2. RETICK READS THE GATE'S RETURN, and speaks if it is FALSE.** This is the
whole point. `KalimbaSendMessage` returns TRUE only if a `.kap` is loaded. So on
a rebuild:

    gate TRUE   the DSP is alive; the port is re-armed; carry on
    gate FALSE  **the DSP IS GONE** -- say so

One bool, spoken as **0x3E "bluetooth off"**, settles a pattern that has survived
ten probes. If it fires, the diagnosis is no longer a hypothesis and the
conclusion is structural: the deliverable cannot live on a hook that enters
pairing, and the next work is finding a trigger that does not.

**And the timer moves to 7500 ms**, from probe156's 5000. probe156 re-armed
*before* the chunk ended, specifically to keep the port from going dry -- but with
the gate now re-arming the port that is no longer necessary, and re-gating
mid-stream is the one thing that genuinely does purge audio. Firing just after
the measured ~7 s costs a short seam and avoids cutting a live chunk.

## The press (laptop connected, music PAUSED, long-press the BLUETOOTH button)

**TIME IT, and listen for a prompt after the noise stops.**

  NOISE IN ~7 s CHUNKS, GOING ON     the re-arm works. Keep timing: minutes means
                                     sustain is solved. A short seam every seven
                                     seconds is expected and is the chunk
                                     boundary.
  noise ~7 s, then "bluetooth off"   **THE DSP IS GONE.** Hypothesis confirmed:
  (0x3E)                             entering pairing takes the decoder down, and
                                     that -- not any pool -- is what has been
                                     setting every death time since probe104.
                                     The hook has to move off EnterPairing.
  noise ~7 s, then "call with"       the DSP is alive and the port re-armed, but
  (0x25)                             the transform was refused -- with the sink
                                     disconnected first that points at
                                     allocation. Count the cycles.
  noise ~7 s, then "switching        StreamFileSource refused: a pool is dry.
  call" (0x24)
  noise ~7 s, then "conference       FileFind lost the directory, or
  call" (0x22) / "call from          "data_us" inside it, on a rebuild.
  unknown" (0x1B)
  noise ~7 s, then "and" (0x10)      StreamKalimbaSink(3) returned 0 on a rebuild
                                     while the gate still said the DSP was there.
  noise ~7 s then SILENCE, no        the timer never fired at all. That is the
  prompt of any kind                 one remaining mechanism this probe cannot
                                     see, and it would point back at the message
                                     dispatch rather than the audio path.
  silence from the start             the 0x1072 gate bailed at the ARM: no DSP up,
                                     so the press conditions were not met.

## What is NOT changed

The hook, the redirects, the two-level FileFind onto the narrow
`NowSpeakTTS/data_us`, both path strings (each one item, asserted contiguous, and
read back off the device on probe155), the corrected prefixed-pointer fold, the
`StreamDisconnect` that frees the sink for a new transform, the flashed const
TaskData at data 0xBA3C whose dispatch probes 145-147 proved, and the rest of the
id lattice.

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
TASK_ADDR = 0xBA3C       # const_addr(CAVE+1): the TaskData lives at
                         #   CAVE+1, CAVE+2, exactly as probes 145-151
                         #   had it -- the dispatch path those probes
                         #   proved on hardware
DELAY_MS = 7500          # just PAST the measured ~7 s chunk. probe156
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
W(0x0014)                       # ld AL,#0
W(0x0027); W(0x0127); W(0x0227) # b = c = d = 0        slots 0..2
W(*ca.imm_words(RATE, 0x10))    # ld AH,#2000
W(*ca.imm_words(0x1072, 0x14))  # ld AL,#0x1072
BSR(KALMSG)
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
W(0x0014)                       # ld AL,#0
W(0x0027); W(0x0127); W(0x0227) # b = c = d = 0        slots 0..2
W(*ca.imm_words(RATE, 0x10))    # ld AH,#2000
W(*ca.imm_words(0x1072, 0x14))  # ld AL,#0x1072
BSR(KALMSG)
W(0x0084); BR(0xF4, "NODSP")    # FALSE -> THE DSP IS GONE. Say so.

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

LBL("NODSP")
W(0x3E14)                       # ld AL,#0x3E "bluetooth off" -- THE DSP IS GONE
BR(0xE0, "SAY")
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
