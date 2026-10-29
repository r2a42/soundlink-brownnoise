#!/usr/bin/env python3
"""probe114: can the tone port be written DIRECTLY, with nothing to leak?

**Built, not flashed.** Unlike probes 111 and 113 this one can be tested **with the laptop
connected and music paused** — probe77/104 conditions — so it does not wait on probe112's
standalone answer. It tests the architecture, not the pairing question.

## Why this is the architecture worth having

Every audio design in this project so far builds a `StreamRegionSource` and a
`TransformAdpcmDecode` per buffer, and **that is what crashed probes 105 and 106**:
`TransformDisconnect` does not free the attached source, so an un-drained source leaked
every cycle until Bose's own allocations hit `PanicNull` (`docs/cave-heap.md`). probe113
fixes it by copying Bose's five-call teardown — but the objects are still created and
destroyed 7 times a second.

Writing the port directly allocates **nothing**: claim space, write samples, flush. No
source, no transform, no `malloc`, nothing to close, nothing to leak, and no teardown to
get wrong. It would also feed **16-bit PCM**, so it can use
`build/noiseprobe/noise.c:noise_fill` — the leaky-integrator generator with a one-pole
high-pass, **kalsim-verified at -5.89/-6.02/-5.89 dB per octave and bit-exact on this
hardware in probe81** — instead of the ADPCM random walk, which has no leak and therefore
needs priming tricks and still drifts toward the rail.

So if this works it is better on every axis: better spectrum, no leak, less code.

## The primitive, which turns out to already exist

probe103 tried this and never got there — it died at `malloc(512)` before reaching the
sink, and the calling convention for `SinkClaim`/`SinkMap` was going to be guessed. It does
not need guessing. Profiling every function by the traps it calls
(`build/analysis/fn-profiles.txt`) turned up **`fn_12e1a`, 29 words, 13 callers**:

    fn_12e1a(AL = sink, AH = count) -> pointer, or 0        enterl -6
        base = SinkMap(sink)
        off  = SinkClaim(sink, count)
        if off == 0xFFFF: return 0          claim refused
        ptr = base + off
        fn_39480(ptr, 0, count)             memset to zero
        return ptr

Bose's own "claim space in a sink and give me a pointer", `bsr`-able with two register
arguments. It uses it from the USB and upgrade paths (`0xd395`, `0xd3bd`, `0x179xx`-
`0x189xx`), **never on a Kalimba port** — which is precisely the open question.

## Why the old negative result does not settle it

`docs/field-log.md` has probes 64-66 concluding Kalimba sinks report no slack. Those
queried the **codec** sink (64) and ports **0 and 4-7** (65, 66) — never port 3 — and none
of them sent `0x1072` first, which is what sets `$aux_input_stream_available` and arms the
port-3 reader (`codec_tones.asm:516`). `0x1072` was not discovered until much later. And
`sink.h:46-47`'s warning that an "operator sink stream always returns 0xFFFF" is a
Kymera-era concept; this is the old frame-sync Kalimba, so a port here is not an operator.

## The probe

    arm      KalimbaSendMessage(0x1072, 8000, 0, 0, 0)   word b = 0, the louder shift
    ksink    StreamKalimbaSink(3)
    ptr      fn_12e1a(ksink, 256)                        claim 256 and map it
    ptr == 0 -> "voice prompts on"      the claim was REFUSED; direct write is dead
    else     noise_fill(ptr, 254, state in the frame)    true brown noise, PCM
             SinkFlush(ksink, 256)
             -> "voice prompts off"     the claim was HONOURED

`noise_fill` needs two words of carried state and there is no `malloc` here, so the state
lives in the cave's own frame — addressed with Bose's own idiom from `0x107f3`,
`ld AL,@0xffe4 ; add AL,#n`, which forms the address of frame slot n.

256 words is 32 ms at 8 kHz, so the audio is incidental; **the spoken id is the result.**

**Laptop CONNECTED, music PAUSED. Press the CENTRE button once.**

    "voice prompts off"
        -> **the port can be written directly.** Build the leak-free architecture: claim,
           write, flush, on a timer. No sources, no transforms, and true brown noise from
           the verified generator. This supersedes probes 111 and 113.
    "voice prompts on"
        -> the claim was refused on an ARMED port 3, which finally settles what probes
           64-66 only suggested. The ADPCM transform route stands, and probe113 is the way.
    "mobile device not found"  -> StreamKalimbaSink(3) returned 0.
    "disconnected"             -> KalimbaSendMessage FALSE: no .kap, so not connected.
    "english"                  -> the hook fired but this button emits another event.
    a crash                    -> claiming an armed Kalimba port is actively unsafe, which
                                  is worth knowing cheaply and is recoverable.
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
LIFT = liftfn.lift('build/noiseprobe/noiseprobe', 'noise_fill')
assert not LIFT['problems'], LIFT['problems']
print('lifted noise_fill: %d words (the kalsim-verified leaky integrator)' % LIFT['size'])

# Band 0 holds the entry jump and the 2-word TaskData; the code proper starts in
# band 1, because the hook's prefix fold pins the entry address and cannot be
# retargeted (docs/cave-frame.md, docs/message-task-abi.md).
# No handler, so no TaskData and no entry jump.
CODE_AT = CAVE
assert blind(CODE_AT) and in_run(CODE_AT), hex(CODE_AT)

TASK_AT = CAVE + 1
TASK_PTR = ca.const_addr(TASK_AT)
TONE_RATE = 8000        # the rate probe77 and probe104 both proved
SPEAK = 0xDF7F          # the prompt engine: id in AL, nothing in X, and it returns
CLAIM = 0x12E1A         # fn_12e1a(AL=sink, AH=count) -> pointer, or 0 if refused
NCLAIM = 256            # words to claim; 32 ms at 8 kHz, so the id is the real result
NSAMP = 254             # leaving two frame slots' worth of generator state
# No TaskData and no handler: everything happens in the button handler, so there is no
# timer, nothing scheduled, and nothing that can outlive the press.

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))


W(0xF00B)                       # enterl -16  (slots 0..13 usable, 14/15 = link)
W(0x0A23)                       # st AH,@(10,Y)  the event id we were called with

W(*ca.imm_words(VA_EVENT, 0x80))   # cmp AH,#0x4004
BR(0xF0, "OTHER")

# Arm the port-3 reader. codec_tones.asm:516 sets $aux_input_stream_available = 1 here,
# which is what probes 64-66 never did. Word b = 0 selects shift 7, the louder of Bose's
# two (docs/kalimba-disasm.md).
ca.calln(W, BSR, ca.STUB['KalimbaSendMessage'],
         al=('imm', 0x1072), ah=('imm', TONE_RATE),
         stack=[('imm', 0), ('imm', 0), ('imm', 0)], stage='AL')
W(0x0084); BR(0xF4, "NODSP")

ca.call1(W, BSR, ca.STUB['StreamKalimbaSink'], al=('imm', 3))
W(0x0B27)                       # st AL,@(11,Y)  ksink
W(0x0084); BR(0xF4, "NOSINK")

# THE MEASUREMENT. Bose's own claim-and-map helper; 0 means SinkClaim returned 0xFFFF.
ca.call2(W, BSR, CLAIM, al=('slot', 11), ah=('imm', NCLAIM))
W(0x0C27)                       # st AL,@(12,Y)  ptr
W(0x0084); BR(0xF4, "NOCLAIM")

# The claim was honoured. Fill it with real brown noise: noise_fill is a leaky integrator
# with a one-pole high-pass, kalsim-verified at -5.9 dB/octave and bit-exact on hardware
# in probe81. Its two words of carried state live in frame slots 8 and 9, addressed with
# Bose's own idiom from 0x107f3.
# The LFSR state MUST be non-zero: x = (x>>1) ^ (-(x&1) & 0xB400) maps 0 to 0, so a
# zero seed produces silence forever. Caught by checking the generated PCM against the
# model rather than assuming -- both agreed, and both were zero.
ca.load_al(W, ('imm', 0xACE1)); W(0x0827)      # slot 8 = LFSR seed
W(0x0014); W(0x0927)                           # slot 9 = integrator = 0
W(0xE415)                       # ld AL,@0xffe4   AL = Y
W(0x0834)                       # add AL,#8       -> &slot 8
W(0x0D27)                       # st AL,@(13,Y)
ca.calln(W, BSR, "NOISE", al=('slot', 12), ah=('imm', NSAMP),
         stack=[('slot', 13)], stage='AL')

ca.call2(W, BSR, ca.STUB['SinkFlush'], al=('slot', 11), ah=('imm', NCLAIM))

W(0x1314); BSR(SPEAK)           # 0x13 "voice prompts off" = THE CLAIM WAS HONOURED
BR(0xE0, "PASS")
LBL("NOCLAIM"); W(0x1214); BSR(SPEAK); BR(0xE0, "PASS")  # 0x12 "voice prompts on"
LBL("NOSINK");  W(0x0914); BSR(SPEAK); BR(0xE0, "PASS")  # 0x09 "mobile device not found"
LBL("NODSP");   W(0x0814); BSR(SPEAK); BR(0xE0, "PASS")  # 0x08 "disconnected"
LBL("OTHER");   W(0x1614); BSR(SPEAK)                    # 0x16 "english"

# ---- replay the displaced call, or the centre button stops working.
LBL("PASS")
W(0x0014); W(0x0027)            # ld AL,#0 ; st AL,@(0,Y)   message = 0
ca.load_al(W, ('imm', 0x512))
W(0x0A13)                       # ld AH,@(10,Y)
BSR(SEND)
W(0xF00F)                       # leavel -16, which returns

W(0x0000) ; W(0x0000)                       # padding past the +-128 bsr encoding gap
LBL("NOISE")
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
assert CODE_AT == CAVE   # no entry jump in this probe
for i, item in enumerate(prog):
    if item[0] != "label":
        assert addrs[i] in dstarts, (hex(addrs[i]), "boundary")
print("decode-verify: all branches OK, boundaries OK")

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe114_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe114_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe114_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe114_cmd.txt")
