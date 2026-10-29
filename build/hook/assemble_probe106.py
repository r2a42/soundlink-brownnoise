#!/usr/bin/env python3
"""probe106: probe105's three defects fixed. A toggle, not a pile of chains.

probe105 on hardware: press 1 spoke "connected to" (all five calls succeeded) and
made **no sound**; press 2 spoke "voice prompts on" (a call returned 0); press 3
**crashed and rebooted** (recovered on its own, no wedge).

A review of the emitted assembly found the cave itself mechanically correct --
frame, slot usage, trap argument order, cmp-before-branch, `leavel` semantics,
reentrancy and stack depth all check out. Every defect was design-level, and there
are exactly three.

## 1. Nothing stopped a second chain -- this is press 2 and press 3

The cave ran unconditionally on every press, and the re-arm is unconditional, so
each press started a timer chain that could never be stopped. On press 2:

    StreamKalimbaSink(3)        OK -- a Kalimba sink handle is a lookup, not an
                                     allocation, so it is handed out even when busy
    StreamRegionSource(B+2,126) OK
    TransformAdpcmDecode(...)   **0** -- chain A's transform still holds sink 3
                                     (stream.h:117: zero if already connected)

which is the reported "voice prompts on" exactly. And that refusal is itself a new
hardware fact: **an ADPCM transform persists and keeps the sink after its region
source has drained.** Had it self-disposed, sink 3 would have been free and press 2
would have spoken 0x0E.

The crash follows. `stream.h:213-219` -- a region source "only exists while the data
is being read", destroyed on drain. Chain B's sources are never drained, because its
transform never exists, and nothing calls `SourceClose`. So chain B leaked a firmware
stream object **every 28 ms, about 36 a second**, from press 2 onward. Our own
allocations fail gracefully; Bose's go through `PanicNull`, and press 3 triggers a
prompt, which allocates. Hence: crash, reboot, recovery.

**Fix:** `MessageFlushTask(task)` (stub 0x06E) flushes every message queued for a
task and returns how many -- so the cave can kill an old chain *without knowing its
MessageId*, and can tell whether one was running. That makes this a **toggle**:

    press 1  no chain pending  -> start one, speak "connected to"
    press 2  a chain pending   -> kill it, tear down the transform, speak
                                  "voice prompts off"

## 2. `buf[1]` held a destroyed transform handle

probe105 kept the live transform in `buf[1]` but only ever rewrote it on full
success, so every `RBAD` exit left a handle to a transform that no longer existed,
and the next refill called `TransformDisconnect` on it. `transform.h:52-53` says the
handle "can no longer be used" after a disconnect and promises nothing about reuse.
If the firmware recycles handle ids -- table-indexed handles usually do -- that call
tears down whoever inherited the id: a prompt, or the A2DP stream when music
resumes. probe105's own docstring predicted the window ("the prompt's .kap reload
will break a refill or two"), which is exactly when Bose creates its prompt
transform.

**Fix:** stop tracking it. `TransformFromSink(StreamKalimbaSink(3))` (stub 0x14A,
`transform.h:84-90`: "zero if no transform or connection is active") returns
whatever actually holds the port. That can never be stale, it lets a new press take
the port over from an old chain, and it frees `buf[1]`.

## 3. 0x1072 on every refill purged the audio -- this is the silence

`codec_tones.asm:495-520`, the SET_TONE_RATE handler, recomputes the copy timer,
reconfigures the mixer, and then:

    // purge tone buffers, safeguard to make sure left and
    // right channels are synchronised
    r0 = M[&$tone_in_left_cbuffer_struc + $cbuffer.WRITE_ADDR_FIELD];
    M[&$tone_in_left_cbuffer_struc + $cbuffer.READ_ADDR_FIELD] = r0;

`TONE_BUFFER_SIZE` is 256 samples (`codec_decoder.h:107`) and the copy timer runs
every 8 ms. probe105 sent 0x1072 **36 times a second**, discarding the whole tone
buffer each time. probe104 sent it once and was plainly audible; probe105 sent it
constantly and was silent.

The flag it sets, `$aux_input_stream_available`, is cleared by the DSP only after
`$PCM_END_DETECTION_TIME_OUT` = 30000 us of inactivity (`codec_tones.asm:248-271`),
so while data keeps arriving it never needs re-sending.

**Fix:** send 0x1072 only when `TransformFromSink` found nothing -- the first fill,
and any refill after a .kap reload killed our transform. Healthy refills skip it.

## 4. And the gain flag was wrong

Both of Bose's paths pass `NO_EXTRA_GAIN` (`audio_plugin_if.h:194` = 0x2):
`voice_prompts_dsp_if.c:594` and `:604`. probe105 passed 0, and `codec_tones.asm`
turns that into a **3-bit left shift**:

    r0 = 3;  Null = r2 AND 2;  if NZ r0 = 0;  r0 = r0 + 8;

i.e. shift 11 instead of 8 -- **+18 dB**. Our content is -13 dBFS by measurement, so
that saturates at +5 dBFS. probe105's docstring claimed the +18 dB usefully raised
the level; it would have clipped it. Word b is now 2, matching Bose, and -13 dBFS is
the delivered level.

## The shape

    cave      n = MessageFlushTask(task)
              n != 0  -> kill the transform on port 3, speak "voice prompts off"
              n == 0  -> buf = malloc(128) ; buf[0] = LFSR seed
                         tmpl_fill(buf+2) ; FILL ; speak FILL's id

    handler(AH = buf):  FILL

    FILL      MessageSendLater(task, buf, 0, 28 ms)        re-arm first
              ksink = StreamKalimbaSink(3)
              t = TransformFromSink(ksink)
              t  -> TransformDisconnect(t)                 never a stale handle
              !t -> KalimbaSendMessage(0x1072, 8000, NO_EXTRA_GAIN, 0, 0)
              nib_fill(buf+2, buf)                         signs only
              t = TransformAdpcmDecode(StreamRegionSource(buf+2, 126), ksink)
              TransformStart(t)

The noise shaping is unchanged from probe105 and still measures **-13.1 dBFS, 0.00%
clipped, -6.00 dB/octave** (brown is -6), refill artifact 16 dB down, verified
against the bytes the device actually holds.

One leak remains and is deliberate: a stopped chain's 128-word buffer cannot be
found, so each on/off cycle loses 128 words of VM heap. That is bounded by the
owner's patience rather than by a timer, and a reboot clears it.

**Phone CONNECTED, music PAUSED** -- still a crutch, and the next probe removes it:
`audio_output_connect.c:620` runs `TransformStart(TransformAdpcmDecode(source,
audio_sink))` into a real DAC sink with no DSP and no .kap at all, which is how the
ADK plays ADPCM prompts when nothing else is loaded.

    continuous brown noise, and a second press stops it
        -> **the deliverable.** Expect the prompt to punch one hole in it as the
           .kap reloads; the 0x1072 path above is what recovers from that.
    a low throb under the noise
        -> the 31.7 Hz refill rate. It measures 16 dB down; a bigger buffer lowers
           it, and malloc(256) is worth trying once 128 is proven.
    "connected to" and still silence
        -> the purge was not the whole story. Next: TransformPollTraffic (stub
           0x142) on the live transform, which answers "did any byte move" without
           depending on ears.
    "voice prompts off" on the FIRST press
        -> a chain from probe105 survived the reboot, or MessageFlushTask counts
           something unexpected. Press again.
    "voice prompts on" -> a call still returned 0. With one chain only, the sink
                          cannot be busy, so suspect KalimbaSendMessage, i.e. no
                          .kap loaded, i.e. the phone is not actually connected.
    "lost"             -> malloc(128) returned 0, now plausible as leaked heap from
                          probe105's presses. A power cycle clears it.
"""

import sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca
import liftfn

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

CAVE = 0x3E21D         # fixed by the hook's prefix fold at 0xAE0 (do not move)
# 0xae3 := bra +1 only. 0xAE4..0xAE6 (the prompt call) stays STOCK this time.
REDIRECT_EDITS = [("0x6fff1", "0x04"), ("0x6fff3", "0xd7"), ("0x6fff5", "0x3b"),
                  ("0x6fff6", "0xe0"), ("0x6fff7", "0x01")]
# 0xAE4..0xAE6 left STOCK. probes 76-102 deleted the prompt call to stop its .kap
# reload stealing the tone port, and paid for it with six presses the owner could
# not interpret. Here the refill timer re-creates the transform every 110 ms, so
# the prompt costs at most one gap -- and buys a spoken id that names the failing
# call.
AREA0 = 0x6EA30
NSAMP = 128

w = xapvm.load_words("firmware/bose/extracted/internal_fs/vm.app")
code = w[0x18:]
C0 = (0x6e974 + 0x34) % 64
def blind(cw): return 34 <= (2*cw + C0) % 64 <= 60
CONST_A = 0x39BE2                      # const pool start, in `a` space
CONST_N = w[7]
# SCAN WINDOW NARROWED 2026-10-05. This used to sweep the WHOLE const pool with a 16-word
# threshold, advertising "262 writable words". probe130 used 234 of them and CRASHED THE
# SPEAKER ON BOOT: 55 words landed outside the hardware-proven window, 9 of them in the run
# 0x3aa51..0x3aa67 whose data address 0x8280 is loaded by fn_0aaa1 at 0x0aaa5 and shipped as
# a message payload. Being zero in the official image and inside a DFU blind window -- the
# only two things this scan checked -- is NOT sufficient. ZERO DOES NOT MEAN UNREAD.
# docs/cave-budget.md has recorded the real budget, 197 words in 0x3E200..0x3E400, since
# 2026-09-30. tools/caveguard.py enforces it and tools/preflight.py calls it.
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

# Band order: the rest of CAVE's own run, then every later run, then the runs
# before CAVE. Layout must begin at CAVE because that is what the hook branches to.
_ORDER = []
for a, b in _runs:
    if a <= CAVE < b: _ORDER.append((CAVE, b))
for a, b in _runs:
    # Only runs a 1-word connector can reach from the end of the previous band.
    # The three runs around the cave qualify (gaps of 26 and 12 words). 0x3EAD2
    # is 1746 words past 0x3E400 and does not, so it stays out until the layout
    # can reserve a wider branch for the hop.
    if a > CAVE:
        _ORDER.append((a, b))
for a, b in _runs:
    if b <= CAVE:
        _ORDER.append((a, b))
assert _ORDER and _ORDER[0][0] == CAVE, 'CAVE is not inside a zero run'
# Maximal runs of consecutive writable words, in band order. The layout walks
# this list; a connector branch carries control from the end of one band to the
# start of the next, wherever in the pool that is.
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
    """Band-order successor: if pc is one past a filled band, the next band's
    first word; if pc is inside a band, pc itself."""
    if pc in _BEND:
        k = _BEND[pc] + 1
        assert k < len(_BANDS), 'cave exhausted: %d writable words is not enough'             % sum(y - x for x, y in _BANDS)
        return _BANDS[k][0]
    for x, y in _BANDS:
        if x <= pc < y:
            return pc
    raise AssertionError('next_blind off the map at %#x' % pc)

# ---- the generator, lifted from the linked image ----
LIFT = liftfn.lift('build/noiseprobe/noiseprobe', 'nib_fill')
LIFT2 = liftfn.lift('build/noiseprobe/noiseprobe', 'tmpl_fill')
assert not LIFT['problems'], LIFT['problems']
assert not LIFT2['problems'], LIFT2['problems']
print('lifted nib_fill %d words, tmpl_fill %d words'
      % (LIFT['size'], LIFT2['size']))

# Band 0 holds the entry jump and the 2-word TaskData; the code proper starts in
# band 1, because the hook's prefix fold pins the entry address and cannot be
# retargeted (docs/cave-frame.md, docs/message-task-abi.md).
BAND0 = [CAVE + k for k in range(3)]       # entry jump + the 2-word TaskData
assert all(blind(a) and in_run(a) for a in BAND0)
CODE_AT = CAVE + 3                        # no longer skips the rest of band 0
assert blind(CODE_AT) and in_run(CODE_AT), hex(CODE_AT)

TASK_AT = CAVE + 1
TASK_PTR = ca.const_addr(TASK_AT)
# 126 words = 252 nibbles = 252 samples = 31.5 ms at 8000 Hz. malloc(128) is
# exactly 2 header words (LFSR state, live transform) plus those 126.

# --- output paths are derived from THIS FILE'S OWN NAME, never hardcoded -------------
# Every probe assembler is made by copying its predecessor, and three times now the copy
# kept the predecessor's hardcoded output paths and silently overwrote the artifacts of
# the image sitting ON THE DEVICE: probe129_words.json twice, probe134_words.json once
# (restored from build/hook/snapshots/ and re-verified against the device readback both
# times). A words.json is the only record of what a flashed image contains, so losing it
# costs the readback check its reference.
_PROBE = re.match(r'assemble_(probe\d+)\.py$',
                  os.path.basename(os.path.abspath(__file__))).group(1)

NWORDS = 126
assert (NWORDS - 12) % 3 == 0, 'tmpl_fill unrolls the cycle three words at a time'
REFILL_MS = 28

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))

BACK = 0xE06D          # the call the hook at 0xae0 displaced

W(0xF00B)                       # enterl -16  (slots 0..13 usable, 14/15 = link)
BSR(BACK)                       # stock back-call (proven by probe37)

# Kill any chain an earlier press left running. MessageFlushTask returns how many
# messages it flushed (message.h:127), which is the only way a cave can learn that
# a chain exists without knowing the MessageId it was armed with.
ca.call1(W, BSR, ca.STUB['MessageFlushTask'], al=('imm', TASK_PTR))
W(0x0084); BR(0xF0, "STOP")     # bne: something was pending -> this press stops it

ca.call1(W, BSR, ca.STUB['malloc'], al=('imm', NWORDS + 2))
W(0x0A27)                       # st AL,@(10,Y)  buf
W(0x0084); BR(0xF4, "NOMEM")

W(0x0A1B)                       # ld X,@(10,Y)
ca.load_al(W, ('imm', 0xACE1)); W(0x0026)      # buf[0] = LFSR state
W(0x0A17); W(0x0234); W(0x0B27) # samples = buf + 2 -> slot 11

# The magnitude template, written ONCE: twelve 0x44 priming words lift the IMA step
# index to ~47, then 0x11/0x41/0x14 repeating holds it there. Refills touch only the
# sign bits, which is what keeps nib_fill small.
ca.call1(W, BSR, "TMPL", al=('slot', 11))

BSR("FILL")                     # generates, connects, re-arms, returns the id in AL
BR(0xE0, "SPEAK")

# ---- a second press stops the chain. The timer is already flushed; all that is
# left is to take our transform off port 3 so the firmware has it back.
LBL("STOP")
ca.call1(W, BSR, ca.STUB['StreamKalimbaSink'], al=('imm', 3))
W(0x0C27)                       # st AL,@(12,Y)  ksink3
W(0x0084); BR(0xF4, "SAYOFF")
ca.call1(W, BSR, ca.STUB['TransformFromSink'], al=('slot', 12))
W(0x0927)                       # st AL,@(9,Y)   whatever holds the port, or 0
W(0x0084); BR(0xF4, "SAYOFF")
ca.call1(W, BSR, ca.STUB['TransformDisconnect'], al=('slot', 9))
LBL("SAYOFF"); W(0x1314); BR(0xE0, "SPEAK")    # 0x13  "voice prompts off"
LBL("NOMEM");  W(0x0614)                       # 0x06  "lost"
LBL("SPEAK")
W(0xF00F)                       # leavel -16, which returns

# ---- the handler, entered from MessageLoop with AH = buf. It cannot speak, so it
# ignores FILL's status; FILL re-arms the timer itself.
LBL("HANDLER")
W(0xF00B)                       # enterl -16
W(0x0A23)                       # st AH,@(10,Y)  buf (the MessageId)
BSR("FILL")
W(0xF00F)                       # leavel -16, which returns

# ---- FILL(caller slot10 = buf) -> AL = the prompt id. Re-arms the timer.
LBL("FILL")
W(0xF00B)                       # enterl -16
W(0x1A17); W(0x0A27)            # ld AL,@(26,Y) -> st AL,@(10,Y)   caller's slot 10
W(0x0234); W(0x0B27)            # samples = buf + 2 -> slot 11

# Re-arm BEFORE anything can bail, so the chain survives a .kap reload and nothing
# has to preserve AL across the call.
ca.calln(W, BSR, ca.STUB['MessageSendLater'],
         al=('imm', TASK_PTR), ah=('slot', 10),
         stack=[('imm', 0), ('long', REFILL_MS)], stage='AL')

ca.call1(W, BSR, ca.STUB['StreamKalimbaSink'], al=('imm', 3))
W(0x0C27)                       # st AL,@(12,Y)  ksink3
W(0x0084); BR(0xF4, "RBAD")

# Ask the PORT what holds it, rather than trusting a handle we stored last time.
# probe105 kept it in buf[1] and left it stale on every bail path.
ca.call1(W, BSR, ca.STUB['TransformFromSink'], al=('slot', 12))
W(0x0927)                       # st AL,@(9,Y)
W(0x0084); BR(0xF4, "ARMRATE")  # nothing there: first fill, or a .kap reload
ca.call1(W, BSR, ca.STUB['TransformDisconnect'], al=('slot', 9))
BR(0xE0, "HAVERATE")

# Only sent when the port is idle. codec_tones.asm:509-516 PURGES the 256-sample
# tone buffer on every 0x1072, so sending it per refill (probe105) threw the audio
# away. Word b = NO_EXTRA_GAIN, which Bose always sets: clearing it selects an
# extra 3-bit shift (+18 dB) and saturates our -13 dBFS content.
LBL("ARMRATE")
ca.calln(W, BSR, ca.STUB['KalimbaSendMessage'],
         al=('imm', 0x1072), ah=('imm', 8000),
         stack=[('imm', 2), ('imm', 0), ('imm', 0)], stage='AL')
W(0x0084); BR(0xF4, "RBAD")
LBL("HAVERATE")

# Refresh only the sign bits. The LFSR lives in buf[0], so each refill CONTINUES the
# sequence; a replayed 31.5 ms buffer would buzz at 31.7 Hz instead.
ca.call2(W, BSR, "NIBS", al=('slot', 11), ah=('slot', 10))

ca.call2(W, BSR, ca.STUB['StreamRegionSource'],
         al=('slot', 11), ah=('imm', NWORDS))
W(0x0D27)                       # st AL,@(13,Y)  src -- NWORDS BYTES, one per word
W(0x0084); BR(0xF4, "RBAD")

# Bose's own two call sites, 0x22F9B and 0x23083: arg1 = source, arg2 = sink.
ca.call2(W, BSR, ca.STUB['TransformAdpcmDecode'], al=('slot', 13), ah=('slot', 12))
W(0x0927)                       # st AL,@(9,Y)   t
W(0x0084); BR(0xF4, "RBAD")

# transform.h:25-28: a StreamConnect transform starts implicitly and must NOT be
# started; a TransformAdpcmDecode one must be.
ca.call1(W, BSR, ca.STUB['TransformStart'], al=('slot', 9))
W(0x0084); BR(0xF4, "RBAD")

W(0x0E14); BR(0xE0, "FEXIT")    # ld AL,#0x0E  "connected to" = every call OK
LBL("RBAD"); W(0x1214)         # 0x12  "voice prompts on"
LBL("FEXIT")
W(0xF00F)                       # leavel -16, which returns

W(0x0000)                       # padding past the +-128 bsr encoding gap
LBL("NIBS")
for it in LIFT['items']:
    if it[0] == 'w':
        W(*it[1])
    elif it[0] == 'br':
        BR(it[1], it[2])
    else:
        LBL(it[1])
LBL("TMPL")
for it in LIFT2['items']:
    if it[0] == 'w':
        W(*it[1])
    elif it[0] == 'br':
        BR(it[1], it[2])
    else:
        LBL(it[1])

# ---- layout (proven machinery, probes 67-77) ----
bsr_size, br_size = {}, {}
label_addr = {}
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

for iteration in range(24):
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
        need = sz + 1 if needs_follow(prog[i]) else sz
        nb_probe = next_blind(band_end)
        cs = 1 if -128 <= nb_probe - addr <= 127 else 2
        if addr + need > band_end - (cs - 1):
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
            # Each candidate size is tested with ITS OWN last-word displacement,
            # because that is what will actually be encoded.
            want = (1 if -128 <= tgt - a <= 127
                    else 2 if br2_encodable(tgt - (a + 1))
                    else 3)
            if br_size.get(i, 1) != want: br_size[i] = want; ok = False
    if ok: break
else:
    raise SystemExit("no converge")

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
            # Displacement is relative to the LAST word of the instruction, exactly as
            # for bsr. Using `tgt - a` here targeted every multi-word branch ONE WORD
            # SHORT and is what crashed probe131/132: proven by an independent boundary
            # census of Bose's 2103 multi-word branches (a+ln-1+v: 100%, a+v: 42%).
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
            v = tgt - (a + 2)          # last-word relative, as for bsr
            done = False
            for aa in range(-128, 128):
                if aa == 0: continue
                for bb in range(-128, 128):
                    if bb == 0: continue
                    cc = v - aa * 65536 - bb * 256
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

# entry jump over the TaskData, then the TaskData itself once layout is known
entry_v = CODE_AT - CAVE
assert -128 <= entry_v <= 127
assert CAVE not in out and TASK_AT not in out and TASK_AT + 1 not in out
out[CAVE] = ((entry_v & 0xFF) << 8) | 0xE0
HANDLER_AT = label_addr["HANDLER"]
for k, v in enumerate(ca.taskdata_words(HANDLER_AT)):
    out[TASK_AT + k] = v
print("handler a=%#x, TaskData a=%#x -> data %#06x = %s"
      % (HANDLER_AT, TASK_AT, TASK_PTR,
         ' '.join('%04x' % w for w in ca.taskdata_words(HANDLER_AT))))

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
        # Branches use the SAME last-word rule as bsr. Verified independently against
        # Bose's 2103 multi-word branches: a+ln-1+v lands on an instruction boundary
        # 100% of the time, a+v only 42% (chance).
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
