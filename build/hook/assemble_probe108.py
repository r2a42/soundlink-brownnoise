#!/usr/bin/env python3
"""probe108: probe107's one-shot brown noise, plus the SinkSlack measurement.

probe107 was flashed and the owner's press reported **"ready to connect"** -- which is
not one of its four ids ("connected to", "disconnected", "voice prompts on", "lost").
It is stock firmware behaviour, so the cave never ran: with no phone connected a
long-press takes a different path and never reaches the hook at 0xAE0. No `malloc`
happened, so nothing leaked and nothing was learned.

Rather than spend the owner's next press on the same single question, this probe adds
**one read-only trap call** that settles the architecture for everything after it.

## The measurement

`SinkSlack(StreamKalimbaSink(3))`, called while the port is **armed and idle**.

This project concluded in probes 64-66 (`docs/field-log.md:2769-2960`) that Kalimba
sinks report zero slack, and abandoned direct writing on that basis. Those probes are
invalid for this question on two counts: probe64 queried the **codec** sink, probes
65/66 queried ports **0 and 4-7, never 3**, and none of them sent `0x1072` first --
which is the call that sets `$aux_input_stream_available = 1` and arms the port-3
reader (`codec_tones.asm:516`). `0x1072` was not discovered until much later. An
unarmed port reporting no space says nothing about an armed one.

`sink.h:46-47` warns that "if the sink is an operator sink stream then it always
returns 0xFFFF" from `SinkClaim`. That is a Kymera/Audio-Subsystem concept; this is
the old frame-sync Kalimba app, so a port here is not an operator and the constant
return does not apply. Port 3 is backed by an MMU window whose page is 64 words
(`cbuffer_defines.h`, `CBUFFER_MMU_PAGE_SIZE`).

**Why it matters more than anything else outstanding.** Every crash in probes 105 and
106 traces to one thing: `TransformDisconnect` does not free the attached source, so
rebuilding the transform leaked a stream object per cycle until Bose's own allocations
hit `PanicNull` (`docs/cave-heap.md`). A direct-write architecture -- arm the port
once, then `SinkClaim`/`SinkMap`/write PCM/`SinkFlush` on a timer -- allocates
**nothing at all**: no transform, no region source, no `malloc`, nothing to leak and
nothing to close. It would also feed raw 16-bit PCM, so it could use
`build/noiseprobe/noise.c:noise_fill`, the leaky-integrator brown generator this
project already proved bit-exact on hardware in probe81.

The call is placed after the port is cleared and armed, and before our own transform
is built, because `sink.h:41,63,81` say each of these calls fails on a sink that is
"connected to another stream".

## Everything else is probe107 unchanged

One `malloc`, one transform, one shot, 252 words at 2000 Hz = **252 ms**. No timer, no
handler, no `TaskData`, no refill, no toggle -- none of the machinery that crashed.
Decoded from the bytes the device actually holds: **-8.6 dBFS, 0.00% clipped, peak
21001**; the design measures -6.06 dB/octave against brown's -6 over a longer record.

The spoken id now carries the slack answer instead of a plain "everything worked",
since reaching it at all means every call succeeded:

    "voice prompts off"  -> slack was NON-ZERO. The armed port offers claimable space;
                            probes 64-66 were measuring the wrong thing. Build the
                            direct-write architecture -- the leak-free deliverable.
    "voice prompts on"   -> slack was ZERO. Direct write is genuinely dead, and the
                            answer is probe104's shape refilled only after the source
                            drains, with SourceClose on the old source every cycle.

Either way the 252 ms of noise plays first, as probe104's did before its prompt
("maybe .25 second burst of static and then immediately 'connected to'"), so this one
press answers both questions.

**POWER-CYCLE, WAIT FOR THE PHONE TO RECONNECT, CONFIRM IT IS CONNECTED (play a
second of music and pause it), THEN LONG-PRESS ONCE.**

    a ~1/4 second low rumble, then "voice prompts off"
        -> the shaping is right AND direct write is available. Best case.
    a ~1/4 second low rumble, then "voice prompts on"
        -> the shaping is right; sustain goes via drain-driven refill + SourceClose.
    no sound, then either of those two
        -> every call succeeded and nothing came out. The rate (2000 Hz, unproven --
           only 8000 is) is the first suspect, then TransformPollTraffic.
    "disconnected" -> KalimbaSendMessage FALSE: no .kap loaded, so the phone is not
                      actually connected, or the DSP rejected 2000 Hz.
    "ready to connect" or anything not listed
        -> the cave did not run again; the press did not reach the hook.
    "lost"         -> malloc(254) returned 0. Expected on a SECOND press without a
                      power cycle: it needs the single 642-word pmalloc block and a
                      cave cannot free it (docs/cave-heap.md).
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

# THE MEASUREMENT. The port is now armed (0x1072 just set
# $aux_input_stream_available) and idle (our transform is not built yet, and any old
# one was just disconnected), which is the state probes 64-66 never tested.
ca.call1(W, BSR, ca.STUB['SinkSlack'], al=('slot', 12))
W(0x0827)                       # st AL,@(8,Y)  slack, reported in the spoken id

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

# Reaching here means every call succeeded, so the id carries the slack answer.
W(0x0817)                       # ld AL,@(8,Y)   the slack we measured
W(0x0084); BR(0xF4, "NOSLACK")
W(0x1314); BR(0xE0, "SPEAK")    # 0x13  "voice prompts off" = slack was NON-ZERO
LBL("NOSLACK")
W(0x1214); BR(0xE0, "SPEAK")    # 0x12  "voice prompts on"  = slack was ZERO
LBL("NODSP"); W(0x0814); BR(0xE0, "SPEAK")   # 0x08  "disconnected"
LBL("RBAD");  W(0x0914); BR(0xE0, "SPEAK")   # 0x09  "mobile device not found"
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
