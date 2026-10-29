#!/usr/bin/env python3
"""probe107: one transform, one shot, no timer. Does our ADPCM sound brown?

probe105 and probe106 both behaved inconsistently press to press and both crashed
and rebooted the speaker. Both refilled a 128-word buffer every 28 ms, tearing down
and rebuilding the ADPCM transform **36 times a second**. probe104, which built
**one** transform and no timer at all, worked first time and never misbehaved.

So this probe goes back to probe104's architecture and removes everything that has
ever crashed: no `MessageSendLater`, no handler, no `TaskData`, no refill, no
toggle, no `MessageFlushTask`. One `malloc`, one transform, one shot.

It asks exactly one question: **does the brown-noise ADPCM we generate actually
sound like brown noise?** Nothing in it can answer "and does it sustain", and that
is deliberate -- sustain is the thing that has been crashing, and there is no point
making it sustain a sound we have never confirmed.

## Why the refill architecture probably crashes

Recorded here because it is the next thing to fix, not fixed here. `stream.h:213-219`
says a region source "only exists while the data is being read" and is destroyed on
drain. probe105/106 refilled EARLY by design -- every 28 ms against 31.5 ms of audio
-- so the source had **not** drained when `TransformDisconnect` was called. If
disconnecting a transform does not destroy an undrained source, every refill leaked
one, 36 times a second, and the crash is the firmware's own allocations failing
through `PanicNull`. A Fable agent is checking that and whether `SourceClose` is the
missing call.

## What changed, and why each one

| | probe106 | probe107 |
|---|---|---|
| buffer | malloc(128), 126 words | **malloc(256), 252 words** |
| 0x1072 rate | 8000 Hz | **2000 Hz** |
| duration | 31.5 ms per refill | **252 ms, once** |
| refill | every 28 ms, forever | **none** |
| timer, handler, TaskData | yes | **none** |

The duration is the point. 31.5 ms is not judgeable -- the owner has twice been
asked to judge something that short and twice rightly could not. 252 words at 2000 Hz
is 504 samples = **252 ms**, eight times longer, from a single transform.

2000 Hz is the one extrapolation here: only 8000 is proven on hardware (probe77,
probe104). It is safe on the two constraints I can check. `codec_tones.asm:478-487`
sets the DSP's tone-copy period to `(TMR_PERIOD_TONE_COPY/4) * 8000 / rate` = 16 ms
at 2000 Hz, comfortably inside the `$PCM_END_DETECTION_TIME_OUT` of 30 ms
(`codec_decoder.h:166`) that would otherwise make the DSP declare playback finished;
and the resample buffer is `TONE_BUFFER_SIZE * 6` = 1536 words
(`codec_tones.asm:29`). Brown noise band-limited to 1 kHz is a deep rumble, which for
a sleep sound is the right end of the spectrum anyway.

## The shaping, measured

Unchanged in design from probe105/106, re-measured for a single 252-word shot over
four seeds: **-12.3 dBFS, 0.00% clipped**, IMA step index pinned at 46/47/48 for the
whole buffer. Twelve 0x44 priming words lift the index there; `0x11 0x41 0x14`
repeating holds it, because `(-1-1) + (+2-1) + (-1+2) = 0`. The same design measured
**-6.06 dB/octave** against brown's -6 over a one-second record; a 252 ms record fits
shallower (-4.5) purely because 504 samples give too few FFT bins below 100 Hz.

Word b of `0x1072` is `NO_EXTRA_GAIN` (2), as both of Bose's own paths set it
(`voice_prompts_dsp_if.c:594,604`). probe105 passed 0, which selects an extra 3-bit
shift in `codec_tones.asm:505-509` -- **+18 dB** -- and would have saturated this
content at +5 dBFS.

## The one mechanism kept beyond probe104

`TransformFromSink(StreamKalimbaSink(3))` then `TransformDisconnect`, before building
ours. Without it the SECOND press fails: probe106's press 2 proved an ADPCM transform
keeps holding the sink after its source drains, so the port must be cleared or
`TransformAdpcmDecode` returns 0. This is what makes presses repeatable.

## Known cost, accepted

Each press leaks its 256-word buffer: nothing can find it again to `free` it, because
a cave has no persistent variable. That is about four to six presses before
`malloc` starts failing, which is why **this probe wants a power cycle first** and
why it is a one-shot test rather than something to live with.

**Phone CONNECTED, music PAUSED, and POWER-CYCLE FIRST.**

    a ~250 ms low rumble or whoosh
        -> **the shaping is right.** Brown noise, software only. Everything left is
           sustain, and sustain gets built on the architecture the Fable agent
           recommends rather than on another refill loop.
    a click, a tick, or a short hiss
        -> audio reaches the port but the shaping is wrong. The level and spectrum
           are measured offline, so suspect the 2000 Hz rate or the gain flag, both
           of which changed here.
    "connected to" and silence
        -> 252 ms at 2000 Hz is not getting through although every call succeeded.
           That points at the rate; the next probe would go back to 8000 Hz and
           accept 63 ms, with TransformPollTraffic (stub 0x142) as the real answer.
    "disconnected" -> KalimbaSendMessage FALSE. Either no .kap is loaded, i.e. the
                      phone is not actually connected, or the DSP rejected 2000 Hz.
    "voice prompts on" -> StreamRegionSource, TransformAdpcmDecode or TransformStart
                      returned 0. After a power cycle with one press, the sink
                      cannot be busy, so this would be new.
    "lost"         -> malloc(256) returned 0 even after a power cycle.
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
# No handler, so no TaskData and no entry jump: the hook's target is the first
# instruction, as it was before probe97.
CODE_AT = CAVE
assert blind(CODE_AT) and in_run(CODE_AT), hex(CODE_AT)

TASK_AT = CAVE + 1
TASK_PTR = ca.const_addr(TASK_AT)
# 126 words = 252 nibbles = 252 samples = 31.5 ms at 8000 Hz. malloc(128) is
# exactly 2 header words (LFSR state, live transform) plus those 126.
# 252 words = 504 nibbles = 504 samples = 252 ms at the 2000 Hz declared below.
# malloc(254) is 2 header words (LFSR state, spare) plus those 252.

# --- output paths are derived from THIS FILE'S OWN NAME, never hardcoded -------------
# Every probe assembler is made by copying its predecessor, and three times now the copy
# kept the predecessor's hardcoded output paths and silently overwrote the artifacts of
# the image sitting ON THE DEVICE: probe129_words.json twice, probe134_words.json once
# (restored from build/hook/snapshots/ and re-verified against the device readback both
# times). A words.json is the only record of what a flashed image contains, so losing it
# costs the readback check its reference.
_PROBE = re.match(r'assemble_(probe\d+)\.py$',
                  os.path.basename(os.path.abspath(__file__))).group(1)

NWORDS = 252
assert (NWORDS - 12) % 3 == 0, 'tmpl_fill unrolls the cycle three words at a time'
TONE_RATE = 2000
NO_EXTRA_GAIN = 2       # audio_plugin_if.h:194; Bose sets it on every path

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
W(0x0A17); W(0x0234); W(0x0B27) # samples = buf + 2 -> slot 11

# The magnitude template: twelve 0x44 priming words lift the IMA step index to ~47,
# then 0x11/0x41/0x14 repeating holds it there because the deltas sum to zero.
ca.call1(W, BSR, "TMPL", al=('slot', 11))
# Then the sign bits, which are what make it a random walk, i.e. brown.
ca.call2(W, BSR, "NIBS", al=('slot', 11), ah=('slot', 10))

ca.call1(W, BSR, ca.STUB['StreamKalimbaSink'], al=('imm', 3))
W(0x0C27)                       # st AL,@(12,Y)  ksink3
W(0x0084); BR(0xF4, "RBAD")

# Clear the port first. probe106's press 2 proved an ADPCM transform keeps holding
# the sink after its region source has drained, so without this the second press
# gets 0 from TransformAdpcmDecode. Asking the PORT what holds it can never be a
# stale handle, which is what probe105 got wrong.
ca.call1(W, BSR, ca.STUB['TransformFromSink'], al=('slot', 12))
W(0x0927)                       # st AL,@(9,Y)
W(0x0084); BR(0xF4, "NOTEAR")
ca.call1(W, BSR, ca.STUB['TransformDisconnect'], al=('slot', 9))
LBL("NOTEAR")

# Arm the port-3 reader, ONCE. codec_tones.asm:509-516 purges the 256-sample tone
# buffer on every 0x1072, which is why probe105/106 sending it per refill threw the
# audio away. Word b = NO_EXTRA_GAIN, as Bose always sets: clearing it selects an
# extra 3-bit shift (+18 dB) and would saturate this content.
ca.calln(W, BSR, ca.STUB['KalimbaSendMessage'],
         al=('imm', 0x1072), ah=('imm', TONE_RATE),
         stack=[('imm', NO_EXTRA_GAIN), ('imm', 0), ('imm', 0)], stage='AL')
W(0x0084); BR(0xF4, "NODSP")

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

W(0x0E14); BR(0xE0, "SPEAK")    # ld AL,#0x0E  "connected to" = every call OK
LBL("NODSP"); W(0x0814); BR(0xE0, "SPEAK")   # 0x08  "disconnected"
LBL("RBAD");  W(0x1214); BR(0xE0, "SPEAK")   # 0x12  "voice prompts on"
LBL("NOMEM"); W(0x0614)                      # 0x06  "lost"
LBL("SPEAK")
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
assert CODE_AT == CAVE   # no entry jump to verify in this probe
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
