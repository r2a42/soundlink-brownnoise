#!/usr/bin/env python3
"""probe111: brown noise with NOTHING paired, by taking port 3 from the prompt.

**Built and verified but deliberately NOT flashed** -- probe110 must be pressed first,
because if no DSP loads standalone this probe has nothing to inject into.

## What changed from every previous audio probe: no 0x1072

Reading `NowSpeakTTS.kap` directly (`docs/kalimba-disasm.md`) settles something the
project had only ever assumed. The two DSPs register completely different message sets:

| image | registrar | registered ids |
|---|---|---|
| `sbc_decoder` | `0x349c` | `0x1002`, **`0x1070`/`0x1071`/`0x1072`**, `0x1078`, `0x7010`, `0x7157`, `0x7158`, `0x8019` |
| `NowSpeakTTS` | `0x1802`/`0x350` | **`0x7000`**, `0x8000`, `0x8006`-`0x8009` |

**The prompt DSP handles no `0x10xx` message at all** -- no rate control, no tone-port
arming. Confirmed twice over: by the registration scan, and by searching its whole
disassembly for the immediates `0x1070`-`0x1080`, which finds nothing where
`sbc_decoder` finds six.

So the `0x1072` / `$aux_input_stream_available` machinery this project has leaned on for
twenty probes **exists only in the A2DP decoder**, and sending it to the prompt DSP is a
no-op. This probe does not send it.

What the prompt DSP *does* do is decode whatever arrives on port 3 -- that is its entire
purpose, and `fn_22f6f` is Bose feeding it exactly that way:
`TransformAdpcmDecode -> StreamKalimbaSink(3)`. So the move is to **take the port away
from the prompt and put our own transform on it.**

    cave      buf = malloc(641)            the single 642-word pmalloc block
              buf[0] = LFSR seed
              nib_fill(buf+2, buf)         template + signs, 639 words of brown ADPCM
              MessageSendLater(task, buf, 0, 400 ms)        buf rides as the MessageId
              bsr 0xdf7f(0x0E)             ask the FIRMWARE to load a prompt DSP
              replay fn_395dd              so the centre button still works

    handler   ksink = StreamKalimbaSink(3)
              t = TransformFromSink(ksink)
              t -> TransformStop(t) ; TransformDisconnect(t)
              StreamDisconnect(0, ksink)       <-- TAKE THE PORT FROM THE PROMPT
              MessageSinkTask(ksink, 0)        <-- and its messages with it
              TransformStart(TransformAdpcmDecode(
                  StreamRegionSource(buf+2, 639), ksink))

The teardown is `fn_31e6f`'s order exactly, including the `StreamDisconnect` that sits
outside its "a transform was found" guard. The first build of this probe disconnected a
running transform and left the prompt's task registered on the port; see
`docs/field-log.md` under the probe111 review finding.

The prompt gets cut off mid-word. That is not a side effect to apologise for -- it is the
clearest possible signal that the port changed hands.

## Level and duration

639 words = 1278 nibbles = **1278 samples = 160 ms** at the 8 kHz the prompt engine runs
at. Five times probe105's 31.5 ms, which the owner twice could not judge.

The priming is **9 words, not 12**. A longer buffer lets the unleaked random walk wander
further, and at 1278 samples a prime of 12 reaches the rail: measured over four seeds,
-10.1 dBFS with 0.55% clipped and peak 32768. Prime 9 gives **-19.8 dBFS, 0.00% clipped,
peak 12762.** Measured, not assumed.

## Why this cannot crash the way 105 and 106 did

One `malloc`, one transform, **one** timer firing once with no re-arm. Nothing is rebuilt,
so there is no un-closed `StreamRegionSource` to leak -- which `docs/cave-heap.md`
identifies as the actual cause of those reboots (`TransformDisconnect` does not free the
attached source; Bose's own teardown adds `StreamDisconnect` and `SourceClose`).

And the cave never loads, starts or wires a DSP. The firmware does all of it, which is the
division of labour that probes 75, 77 and 104 all survived and that probes 96 and 97 died
of ignoring.

**NOTHING PAIRED. Press the CENTRE / voice-assistant button once.**

    "connected t-" cut off, then ~160 ms of low rushing noise
        -> **brown noise, standalone, software only.** Then it is only sustain, and
           sustain means a refill that calls SourceClose every cycle.
    the prompt plays through untouched, no noise
        -> the port was not taken. TransformFromSink found nothing, or the prompt does
           not use port 3 on this unit after all.
    prompt cut off, then silence
        -> the port WAS taken and our transform did not play. That is a clean result:
           the difference from probe104 is only which DSP is loaded.
    "mobile device not found" / "connecting to" / "connecting"
        -> StreamKalimbaSink / StreamRegionSource, TransformAdpcmDecode, or
           TransformStart returned 0, named in that order.
    "lost"
        -> malloc(641) failed; the 642-word block was already taken. Retry after a power
           cycle, or fall back to 128 words and 31 ms.
"""

import sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca
import liftfn

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

CAVE = 0x3E21D         # fixed by the hook's prefix fold at 0xAE0 (do not move)
# 0xae3 := bra +1 only. 0xAE4..0xAE6 (the prompt call) stays STOCK this time.
# Redirect the CENTRE-BUTTON send at 0x107be (fn_1061b case 181, button code 0xC5,
# event 0x4004) to the cave. Stock words there are `0300 8e00 1d9c`; reaching 0x3E21D
# needs v = 186973 = aa 0x03, bb 0xda, cc 0x5d, so only two bytes actually change. All
# three operand bytes are inside blind windows. 0x0AE0/0x0AE3 are left STOCK -- the old
# pairing-only hook is retired (docs/hook-sites.md).
REDIRECT_EDITS = [("0x8f9ad", "0x03"), ("0x8f9af", "0xda"), ("0x8f9b1", "0x5d")]
VA_EVENT = 0x4004
SEND = 0x395DD          # fn_395dd(task=AL, id=AH, message=@(0,Y)); reads CALLER's slot 0
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
assert not LIFT['problems'], LIFT['problems']
print('lifted nib_fill %d words (template + signs merged)' % LIFT['size'])

# Band 0 holds the entry jump and the 2-word TaskData; the code proper starts in
# band 1, because the hook's prefix fold pins the entry address and cannot be
# retargeted (docs/cave-frame.md, docs/message-task-abi.md).
BAND0 = [CAVE + k for k in range(3)]       # entry jump + the 2-word TaskData
assert all(blind(a) and in_run(a) for a in BAND0)
CODE_AT = CAVE + 3                        # no longer skips the rest of band 0
assert blind(CODE_AT) and in_run(CODE_AT), hex(CODE_AT)

TASK_AT = CAVE + 1
TASK_PTR = ca.const_addr(TASK_AT)
DELAY_MS = 400          # inside the prompt, after its loader has run
NWORDS = 639            # 9 priming words + 630 = 3 x 210; 1278 samples = 160 ms at 8 kHz
assert (NWORDS - 9) % 3 == 0, 'tmpl_fill unrolls the cycle three words at a time'
SPEAK = 0xDF7F          # the prompt engine: id in AL, nothing in X, and it returns
# No TONE_RATE and no 0x1072: NowSpeakTTS registers no 0x10xx handler at all
# (docs/kalimba-disasm.md), so the rate message would be a no-op on the prompt DSP.

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))


W(0xF00B)                       # enterl -16  (slots 0..13 usable, 14/15 = link)
W(0x0A23)                       # st AH,@(10,Y)  the event id we were called with

W(*ca.imm_words(VA_EVENT, 0x80))   # cmp AH,#0x4004
BR(0xF0, "PASS")

ca.call1(W, BSR, ca.STUB['malloc'], al=('imm', NWORDS + 2))
W(0x0B27)                       # st AL,@(11,Y)  buf  (slot 10 holds the event id)
W(0x0084); BR(0xF4, "NOMEM")

W(0x0B1B)                       # ld X,@(11,Y)
W(0x0014); W(0x0026)            # buf[0] = 0, nib_fill's first-call sentinel
W(0x0B17); W(0x0234); W(0x0C27) # samples = buf + 2 -> slot 12

# One call: lays the template down (first time) and sets the sign bits.
ca.call2(W, BSR, "NIBS", al=('slot', 12), ah=('slot', 11))

# Hand buf to the handler as the MessageId -- a data pointer is 16 bits, exactly a
# MessageId's width, and probe100 proved the id arrives intact.
ca.calln(W, BSR, ca.STUB['MessageSendLater'],
         al=('imm', TASK_PTR), ah=('slot', 11),
         stack=[('imm', 0), ('long', DELAY_MS)], stage='AL')

W(0x0E14)                       # ld AL,#0x0E  "connected to"
BSR(SPEAK)                      # ask the FIRMWARE for a prompt, so IT loads the DSP
BR(0xE0, "PASS")
LBL("NOMEM")
W(0x0614)                       # ld AL,#0x06  "lost"
BSR(SPEAK)

# ---- replay the displaced call, or the centre button stops working.
LBL("PASS")
W(0x0014); W(0x0027)            # ld AL,#0 ; st AL,@(0,Y)   message = 0
ca.load_al(W, ('imm', 0x512))   # task
W(0x0A13)                       # ld AH,@(10,Y)             the original event id
BSR(SEND)
W(0xF00F)                       # leavel -16, which returns

# ---- the handler, 400 ms later, mid-prompt. Entered with AH = buf.
LBL("HANDLER")
W(0xF00B)                       # enterl -16
W(0x0B23)                       # st AH,@(11,Y)  buf
W(0x0B17); W(0x0234); W(0x0C27) # samples = buf + 2 -> slot 12

ca.call1(W, BSR, ca.STUB['StreamKalimbaSink'], al=('imm', 3))
W(0x0D27)                       # st AL,@(13,Y)  ksink3
W(0x0084); BR(0xF4, "RBAD")

# TAKE THE PORT FROM THE PROMPT. Asking the port what holds it can never be a stale
# handle, which is what probe105 got wrong by caching one in buf[1].
ca.call1(W, BSR, ca.STUB['TransformFromSink'], al=('slot', 13))
W(0x0927)                       # st AL,@(9,Y)
W(0x0084); BR(0xF4, "NOTEAR")
# fn_31e6f, Bose's own teardown, is TransformFromSink -> TransformStop ->
# TransformDisconnect -> StreamDisconnect(0, sink), then it ZEROES the handle.
# The first version of this probe went straight from TransformFromSink to
# TransformDisconnect, stopping a running transform by disconnecting it, which
# the firmware never does anywhere in the image.
ca.call1(W, BSR, ca.STUB['TransformStop'], al=('slot', 9))
ca.call1(W, BSR, ca.STUB['TransformDisconnect'], al=('slot', 9))
LBL("NOTEAR")

# StreamDisconnect sits OUTSIDE the "a transform was found" guard in fn_31e6f
# (0x31e87), so it runs whether or not one was. It is also what makes the
# following connect legal at all: stream.h:111 says StreamConnect returns zero
# if the sink is already connected to another stream, which is how probe102's
# every refill after the first was refused.
ca.call2(W, BSR, ca.STUB['StreamDisconnect'], al=('imm', 0), ah=('slot', 13))

# Take the port's task registration away from the prompt. fn_22f6f finishes its
# port-3 wiring with MessageSinkTask(ksink, 0xbd4e) -- the prompt's own task --
# so without this the prompt's state machine keeps receiving MESSAGE_MORE_SPACE
# and MESSAGE_MORE_DATA for a port we are now feeding, and can tear it down from
# its own disconnect path.
#
# The task passed is ZERO, not our own TASK_PTR. This probe rides `buf` in the
# MessageId field (MessageSendLater(task, buf, ...)), so the handler reads AH as
# a heap pointer. Registering our task here would deliver real sink messages to
# the same handler with AH = a small MessageId, which it would treat as a buffer
# address, rebuilding a StreamRegionSource and a transform per message -- the
# exact leak that crashed probes 105 and 106. message.h:36 defines the return as
# the previous task or zero, so zero is the "no task" value.
ca.call2(W, BSR, ca.STUB['MessageSinkTask'], al=('slot', 13), ah=('imm', 0))

ca.call2(W, BSR, ca.STUB['StreamRegionSource'],
         al=('slot', 12), ah=('imm', NWORDS))
W(0x0A27)                       # st AL,@(10,Y)  src (the event id is done with)
W(0x0084); BR(0xF4, "RBAD")

# Bose's own two call sites, 0x22F9B and 0x23083: arg1 = source, arg2 = sink.
ca.call2(W, BSR, ca.STUB['TransformAdpcmDecode'], al=('slot', 10), ah=('slot', 13))
W(0x0927)                       # st AL,@(9,Y)   t
W(0x0084); BR(0xF4, "RADPCM")

ca.call1(W, BSR, ca.STUB['TransformStart'], al=('slot', 9))
W(0x0084); BR(0xF4, "RSTART")

BR(0xE0, "HEXIT")               # SUCCESS: say nothing, so the noise can be heard
LBL("RSTART"); W(0x0A14); BSR(SPEAK); BR(0xE0, "HEXIT")   # 0x0A "connecting"
LBL("RADPCM"); W(0x0114); BSR(SPEAK); BR(0xE0, "HEXIT")   # 0x01 "connecting to"
LBL("RBAD");   W(0x0914); BSR(SPEAK)                      # 0x09 "mobile device not found"
LBL("HEXIT")
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
        try:
            nb_probe = next_blind(band_end)
            cs = 1 if -128 <= nb_probe - addr <= 127 else 2
        except AssertionError:
            nb_probe, cs = None, 0
        if addr + need > band_end - cs:
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

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe111_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe111_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe111_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe111_cmd.txt")
