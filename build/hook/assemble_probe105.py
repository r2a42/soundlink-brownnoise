#!/usr/bin/env python3
"""probe105: brown noise. Real brown noise, sustained, software only.

probe104 settled the load-bearing question: **`TransformAdpcmDecode` into Kalimba
port 3 carries audio.** The owner heard a burst of static, cut off at about
0.25 s by the "connected to" prompt loading `NowSpeakTTS.kap` and evicting the
decoder -- exactly probe75's behaviour, and exactly what probe104's docstring
predicted. Five calls, no allocation, no timer, 64 words.

Two things were wrong with it, and both are now fixed by design rather than guess.

## 1. Why probe104 was static and not brown

An IMA decoder is an accumulator, so a random **sign** sequence integrates into a
random walk -- which is brown noise, 1/f^2, by construction. The level is set
entirely by the step index, and IMA's index delta is -1 for magnitudes 0..3 and
+2/+4/+6/+8 for 4..7. Const-pool bytes are uniformly random, so their mean delta
is **+2.05 per nibble**: the index pins at its ceiling, every step is full scale,
and 62% of samples clip. A railed random walk is a rasp.

I searched the whole pool for a window that escapes this. The best of 68 windows
has mean delta +1.22 and a slope of -2.4 dB/octave. **No const window is brown**,
so the nibbles have to be generated.

## 2. The design, chosen by measurement

Magnitudes whose deltas sum to zero over a short cycle hold the index
**stationary**. The shortest word-aligned such cycle is three words -- `0x11`,
`0x41`, `0x14`, i.e. `(-1-1) + (+2-1) + (-1+2) = 0`. That cycle holds the index
wherever it starts, and it starts at 0 (= -51 dBFS), so twelve `0x44` priming
words lift it to ~47 first.

Decoded offline with the standard IMA tables over many consecutive refills:

| prime words | dBFS | clipped | dB/octave | index | refill artifact |
|---|---|---|---|---|---|
| 9 | -25.0 | 0.00% | -6.02 | 34/35/36 | -15.5 dB |
| **12 (used here)** | **-15.2** | **0.00%** | **-6.02** | **46/47/48** | **-15.3 dB** |
| 15 | -7.0 | 2.08% | -6.08 | 58/59/60 | -15.1 dB |
| 18 | -4.7 | 10.89% | -6.02 | 70/71/72 | -11.9 dB |

**-6.02 dB/octave against brown's -6, with nothing clipping**, and the index held
to within one step of 47 for the whole buffer. The DSP's own +18 dB (bit 1 of
`0x1072` word b is NO_EXTRA_GAIN, and passing 0 leaves it clear) lifts -15.2 dBFS
to roughly -4 dBFS of delivered level.

Two designs that looked good on paper were killed by the same measurements, and
both are worth recording: making each buffer's second half the sign-inverse of its
first half -- intended to force the walk back to zero so buffers join seamlessly --
*worsened* the refill artifact from -13.5 dB to -4.5 dB, because it imposes
deterministic structure at exactly the buffer rate. And cheap memoryless magnitude
selectors (`(x&7)<2 ? 4 : 1` and eight others) hit -5.97 dB/octave but also -4.5 dB
of artifact, because a non-zero mean delta makes the envelope ramp across every
buffer.

## 3. Why it fits in the cave

The magnitudes never change between refills -- only the signs do. So
`tmpl_fill` writes the magnitude template **once** (22 words) and the per-refill
`nib_fill` rewrites only bits 7 and 3 of each word (42 words):

    *p = (*p & 0x77) | sign_a << 7 | sign_b << 3

Both are compiled by the ADK's own compiler and lifted by `tools/liftfn.py`.
Folding the prime test and the three-way magnitude select out of the hot path and
unrolling the template's cycle took the pair from 86 words to 64 -- which matters,
because the whole const pool holds only 262 writable words
(`docs/cave-budget.md`).

## 4. The shape

    cave      buf = malloc(128)                  128 = 2 + 126 exactly
              buf[0] = LFSR state, buf[1] = live transform handle
              tmpl_fill(buf+2, 126)              ONCE: magnitudes never change
              FILL                               generates, connects and re-arms
              speak FILL's status

    handler(AH = buf):  FILL

    FILL      TransformDisconnect(buf[1])        the teardown probe102 lacked
              nib_fill(buf+2, 126, buf)          signs only; LFSR carries on
              KalimbaSendMessage(0x1072, 8000)   the rate probe77 proved
              t = TransformAdpcmDecode(StreamRegionSource(buf+2, 126),
                                       StreamKalimbaSink(3))
              TransformStart(t) ; buf[1] = t
              MessageSendLater(task, buf, 0, 28 ms)     unconditional re-arm

126 words = 252 nibbles = **252 samples = 31.5 ms** at 8000 Hz, refilled every
28 ms. `malloc(128)` rather than probe103's 512, which returned 0: the field log
records 128 succeeding where 8 once failed, and 512 only ever succeeded with music
playing. The buffer pointer travels as the MessageId (probe100 proved it
survives), which is how a cave with nowhere to keep a global keeps state.

The re-arm is **unconditional and unbounded** -- for a sleep sound that is the
desired behaviour, not a bug.

**Phone CONNECTED, music PAUSED.**

    continuous brown noise
        -> **the deliverable.** Software-only brown noise on a button press, for
           as long as it is left running. Expect the prompt to punch a hole in the
           first second as it reloads the decoder, then recovery.
    a low throb under the noise
        -> the 31.7 Hz refill artifact is audible after all. It is 15.3 dB down by
           measurement; a bigger buffer lowers the rate, and probe106 would try
           malloc(256) now that 128 is known to work.
    static rather than noise, or it clips
        -> the template is not reaching the decoder as intended. cavesim checks the
           template bytes against the Python model, so suspect the region length or
           the byte order rather than the arithmetic.
    "lost"  -> even malloc(128) returned 0.
    "voice prompts on"
            -> one of KalimbaSendMessage / StreamKalimbaSink / StreamRegionSource /
               TransformAdpcmDecode / TransformStart failed. All five succeeded in
               probe104, so this is a regression rather than a new unknown, and one
               id covers them to save cave words. A FALSE from KalimbaSendMessage
               is much the likeliest: it means no .kap is loaded, i.e. the phone is
               not actually connected.
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
    if a > CAVE and a - _ORDER[-1][1] <= 120:
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

ca.call1(W, BSR, ca.STUB['malloc'], al=('imm', NWORDS + 2))
W(0x0A27)                       # st AL,@(10,Y)  buf
W(0x0084); BR(0xF4, "NOMEM")

W(0x0A1B)                       # ld X,@(10,Y)
ca.load_al(W, ('imm', 0xACE1)); W(0x0026)      # buf[0] = LFSR state
ca.load_al(W, ('imm', 0));      W(0x0126)      # buf[1] = no live transform yet
W(0x0A17); W(0x0234); W(0x0B27) # samples = buf + 2 -> slot 11

# The magnitude template, written ONCE: twelve 0x44 priming words to lift the IMA
# step index to ~47, then 0x11/0x41/0x14 repeating to hold it there. Only the sign
# bits change per refill, which is what keeps nib_fill small.
ca.call1(W, BSR, "TMPL", al=('slot', 11))

BSR("FILL")                     # generates, connects, re-arms, and returns the
                                # prompt id in AL, so the cave just speaks it
BR(0xE0, "SPEAK")
LBL("NOMEM"); W(0x0614)         # 0x06  "lost"
LBL("SPEAK")
W(0xF00F)                       # leavel -16, which returns

# ---- the handler, entered from MessageLoop with AH = buf. It cannot speak, so it
# ignores FILL's status; FILL re-arms the timer itself.
LBL("HANDLER")
W(0xF00B)                       # enterl -16
W(0x0A23)                       # st AH,@(10,Y)  buf (the MessageId)
BSR("FILL")
W(0xF00F)                       # leavel -16, which returns

# ---- FILL(caller slot10 = buf) -> AL = 0 or a bail id. Re-arms the timer.
LBL("FILL")
W(0xF00B)                       # enterl -16
W(0x1A17); W(0x0A27)            # ld AL,@(26,Y) -> st AL,@(10,Y)   caller's slot 10
W(0x0234); W(0x0B27)            # samples = buf + 2 -> slot 11

# Re-arm BEFORE anything can bail, so the chain is self-healing and nothing has to
# preserve AL across the call. The prompt's .kap reload will break a refill or two;
# this is what lets the noise come back afterwards.
ca.calln(W, BSR, ca.STUB['MessageSendLater'],
         al=('imm', TASK_PTR), ah=('slot', 10),
         stack=[('imm', 0), ('long', REFILL_MS)], stage='AL')

# Tear the previous transform down first. probe102 omitted this and stream.h:111
# says every reconnect after the first was therefore refused.
W(0x0A1B)                       # ld X,@(10,Y)
W(0x0116)                       # ld AL,@(1,X)   buf[1] = live transform, or 0
W(0x0C27)                       # st AL,@(12,Y)
W(0x0084); BR(0xF4, "NOTEAR")
ca.call1(W, BSR, ca.STUB['TransformDisconnect'], al=('slot', 12))
LBL("NOTEAR")

# Refresh only the sign bits. The LFSR lives in buf[0], so each refill CONTINUES
# the sequence; a replayed 31.5 ms buffer would buzz at 31.7 Hz instead.
ca.call2(W, BSR, "NIBS", al=('slot', 11), ah=('slot', 10))

# Arm the port-3 reader: codec_tones.asm:516 sets $aux_input_stream_available = 1
# inside this handler. Word b = 0 leaves NO_EXTRA_GAIN clear, which is +18 dB.
ca.calln(W, BSR, ca.STUB['KalimbaSendMessage'],
         al=('imm', 0x1072), ah=('imm', 8000),
         stack=[('imm', 0), ('imm', 0), ('imm', 0)], stage='AL')
W(0x0084); BR(0xF4, "RBAD")

ca.call1(W, BSR, ca.STUB['StreamKalimbaSink'], al=('imm', 3))
W(0x0C27)                       # st AL,@(12,Y)  ksink3
W(0x0084); BR(0xF4, "RBAD")

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

W(0x0A1B)                       # ld X,@(10,Y)
W(0x0917)                       # ld AL,@(9,Y)
W(0x0126)                       # st AL,@(1,X)   buf[1] = t, for the next teardown
W(0x0E14); BR(0xE0, "FEXIT")    # ld AL,#0x0E  "connected to" = every call OK
LBL("RBAD"); W(0x1214)         # 0x12  "voice prompts on" -- covers all five calls
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
        if addr + need > band_end:
            if addr >= band_end:
                addr = next_blind(band_end); continue
            nb = next_blind(band_end)
            assert blind(addr) and in_run(addr), (hex(addr), "connector slot not blind")
            extra[addr] = nb
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
for cslot, nb in extra.items():
    v = nb - cslot
    assert -128 <= v <= 127, (
        'band connector 0x%05X -> 0x%05X is %d words, which does not fit the one '
        'word the layout reserves for it. Keep the band order to runs within '
        'reach, or widen the reservation.' % (cslot, nb, v))
    out[cslot] = ((v & 0xFF) << 8) | 0xE0

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
for cslot, nb in extra.items():
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
