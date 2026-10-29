#!/usr/bin/env python3
"""probe128: GENERATED brown noise, single pass, on the one hook that actually fires.

First probe whose payload is noise this project generated rather than bytes that happened
to be lying in flash. Three changes from probe126, each closing a recorded failure.

## 1. The hook moves to 0xAE0, the only one ever observed to fire

probe126 sat at `0x10823` and was silent, as probe118 had been. `fn_1061b` dispatches on
its SECOND argument `@(8,Y)`: `0x10626` tests it against 1 (the jump table, reaching
`0x107be`) and `0x107c2` tests it against 2 (the `fn_105b2` lookup, reaching `0x10823`).
So `0x10823` is the common exit of **mode 2 only**. `0x107be` is refuted too -- probe114
was pressed under its own documented conditions and spoke nothing.

`0xAE0` is the only hook with confirmed fires, and probe77 re-confirmed it on **unit 2**
hours ago with a long clean tone. It is `EventUsrEnterPairing`-gated by the firmware
itself at `0x00ace`, so the cave needs no event test of its own, and it is one-shot per
streaming session -- which is fine for a single-pass probe.

## 2. malloc(128), not malloc(317)

probe126 asked for 317, which needs the single 138-word pool block EXACTLY: 318 is the
held app stack arena and 642 is taken while music plays. That is a single point of failure
dressed up as reliable. **128 is the size this unit has granted reliably** (probes 61, 81,
105, 106) and can be served by the 138, 318 *or* 642 block. The generator was recompiled
at `NWORDS = 126` to fit it, and the lifted immediate was read back as `0x7e34`
(`add AL,#126`) to prove the rebuild took rather than assuming it.

## 3. The tone rate drops to 2000 Hz, which is what makes the burst audible

126 bytes is 252 ADPCM samples. At 8 kHz that is **31 ms** -- a tick, and probe125 already
wasted a press on audio too brief to identify. The rate is ours to choose: `0x1072` word a
is plain Hz, and the DSP's own resampler derives its ratio arithmetically
(`cbops_fir_resample.asm:385-420`, no supported-rate table), so a non-8000 rate costs
filter quality and nothing else. At **2000 Hz the same buffer is 126 ms**, four times
longer and unmistakable.

The floor is not arbitrary. `set_tone_rate_from_vm` (`codec_tones.asm:470-520`) computes

    tmr_period = 2 * (16,000,000 / rate)        ; mono doubles it

and `$detect_end_of_aux_stream` disarms the port once `no_tone_timer` reaches
`$PCM_END_DETECTION_TIME_OUT` = 30,000 us. So **any rate below ~1067 Hz disarms port 3 on
the first tick**. 2000 Hz gives a 16 ms period, a comfortable margin under 30 ms.

## Why every bail is silent, and why that is acceptable here

The three words at `0xae4..0xae6` are nopped, exactly as probe77 does, because the prompt
engine's **`.kap` reload** -- not its speech -- is what tears our transform down. probe76
proved that with a silent id: "a brief tone, no speech". So the prompt channel cannot
coexist with sustained audio, and the ids left in `AL` below are inaudible.

That is tolerable because **all six calls in the chain are already proven on this
hardware**: `0x1072` and `StreamKalimbaSink(3)` by probe122, `malloc(128)` by probes 61/81,
and `StreamRegionSource` -> `TransformAdpcmDecode` -> `TransformStart` by probe104. The
realistic failure is not a call returning 0, it is the audio being inaudible -- which a
spoken id would not diagnose anyway.

## No teardown, no timer, no second allocation

A single pass only. No `MessageSendLater`, no `TransformFromSink`/`TransformStop`
teardown, no refill. probe121 crashed at power-on tearing down a port 3 that did not
exist; probes 105/106 exhausted the pool by rebuilding 36 times a second without
`SourceClose`. Neither mechanism is present here. The one `SourceClose` is on the bail
path where a source exists but the transform did not start, so a failed arm leaks nothing.
The block is never freed -- 128 words is the honest price of one press.

## One latent quirk, recorded so it cannot bite later

On the two `CLOSESRC` bails, `SourceClose` returns into `AL` and overwrites the id that was
just loaded, so `AL` ends up holding a heap pointer. That is harmless **in this probe** --
the prompt call is nopped so no id is audible, and nothing downstream of `0xae3` reads
`AL`. But any future variant that un-nops the prompt to get spoken diagnostics MUST reload
the id after `SourceClose`, or those two paths will hand the prompt engine a pointer as a
request id. Left as-is deliberately: changing it buys no behaviour here and risks a new
bug in verified code.

## Verified offline before flashing

    decode-verify              all branches OK, boundaries OK; 154 words of 262
    cavesim probe90 (control)  AL = 0x0E, reproducing its recorded field result
    cavesim probe128           rate 0x07d0 = 2000, malloc 0x80 = 128, region len 0x7e = 126
    all six --fail paths       each bails to the back-call; malloc failure bails BEFORE the
                               generator runs; both transform failures call SourceClose
    generator cross-check      the bytes the real lifted XAP produced are BYTE-FOR-BYTE
                               identical to tools/noisespec.py's independent model, LFSR
                               state included (0xf40c), and decode to 0.00% clipped,
                               step index 2/33.9/36 against a rail of 88
    stack                      54 path + 8 cave + 2 generator = 64 of 316 words. probe77,
                               which ran on THIS unit today, is 62. probe127, which bricked
                               unit 1, was 80.

**Play music, PAUSE it, then LONG-PRESS the BLUETOOTH button.**

    ~126 ms of noise   -> generated audio works. The payload question is answered and the
                          remaining work is duration (refill) and quality (bandwidth).
    the stock prompt    -> the cave ran but the chain bailed; all ids are inaudible, so the
    only, or silence      next probe adds a distinguishable failure signal.
    nothing at all      -> 0xAE0 did not fire; stream music again, since it is one-shot
                          per streaming session.
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
# The 0x10823 hook: the keypress dispatcher's generic event send, NOT sinkState-gated.
# v = 186872 -> operand bytes 03 da f8. The fs byte mapping AREA0 + 2*cw + 1 was checked
# against probe114's known-good triple for 0x107be before these were computed.
REDIRECT_EDITS = [("0x6fff1", "0x04"), ("0x6fff3", "0xd7"), ("0x6fff5", "0x3b"),
                  ("0x6fff6", "0xe0"), ("0x6fff7", "0x01"),   # 0xae3 := bra +1
                  # 0xae4..0xae6 := nop,nop,nop -- delete `bsr 0xdf7f`, the prompt
                  # player, so nothing reloads the .kap under our noise (probe76/77).
                  ("0x6fff8", "0x00"), ("0x6fff9", "0x00"),
                  ("0x6fffa", "0x00"), ("0x6fffb", "0x00"),
                  ("0x6fffc", "0x00"), ("0x6fffd", "0x00")]
SEND = 0x395DD          # fn_395dd(task=AL, id=AH, message=@(0,Y)); reads CALLER's slot 0
EVENT = 0x400D          # EventUsrMainOutVolumeUp: table entry 14, B_SHORT,
                        # state mask 0x00c0fffe -- fires in any state, repeatably
NWORDS = 126            # recompiled generator; malloc(128) is the PROVEN-reliable size
RATE   = 2000           # Hz. 126 bytes = 252 samples = 126 ms here vs 31 ms at 8 kHz.
                        # Floor is ~1067 Hz: tmr_period = 2*(16e6/rate) must stay under
                        # $PCM_END_DETECTION_TIME_OUT = 30000 us or port 3 disarms at once.
REPORT_MS = 300         # delay before a failure id is spoken from message context
# No STAGE1_MS: the replayed event is what triggers the app's own prompt.
# No VA_EVENT: 0x00ace already gated this hook to EventUsrEnterPairing (0x4003).
# No SEND: the displaced call here is a bsr 0xE06D at the start, not a replay.
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
BAND0 = [CAVE]                            # entry jump only: no TaskData is needed,
assert all(blind(a) and in_run(a) for a in BAND0)   # because there is no message handler
CODE_AT = CAVE + 1
assert blind(CODE_AT) and in_run(CODE_AT), hex(CODE_AT)

# No TASK_AT / TASK_PTR / DELAY_MS: there is no message handler and no timer, and
# CAVE+1 is now the first code word rather than TaskData.
# NWORDS is defined ONCE, near the top, as 126. probe125 inherited a SECOND `NWORDS = 639`
# assignment at this point which executed later and silently restored malloc(641) -- the
# exact bug probe125 existed to fix. Verified again for probe128 by grepping the generated
# file for every NWORDS assignment before building.
assert (NWORDS - 9) % 3 == 0, 'tmpl_fill unrolls the cycle three words at a time'
# buf[0] LFSR state, buf[1] live SOURCE, samples from buf+2. The live transform is NOT
# stored: the teardown finds it with TransformFromSink, which is the whole reason to use
# that trap (a cached handle goes stale, as probe105's did). Keeping the SOURCE is what
# lets SourceClose run -- the call whose absence leaked a stream object every 28 ms in
# probes 105 and 106.
SPEAK = 0xDF7F          # the prompt engine: id in AL, nothing in X, and it returns
# No TONE_RATE and no 0x1072: NowSpeakTTS registers no 0x10xx handler at all
# (docs/kalimba-disasm.md), so the rate message would be a no-op on the prompt DSP.

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))


BACK = 0xE06D          # the call the hook at 0xae0 displaced (probe37, probe77)

W(0xF80B)                       # enterl -8  (slots 0..5 usable, 6/7 = link)
BSR(BACK)                       # stock back-call FIRST, probe77's proven order

# ---- 1. arm the port-3 reader at RATE Hz. Words 3..5 = 0 is MONO_PROMPT with extra
# gain on, the loudest documented option; word b = 0 also selects Bose's shift 7.
# Sent ONCE: its handler purges the 256-sample tone cbuffer, which is what destroyed
# probes 105/106's own audio by re-sending it 36 times a second.
ca.calln(W, BSR, ca.STUB['KalimbaSendMessage'],
         al=('imm', 0x1072), ah=('imm', RATE),
         stack=[('imm', 0), ('imm', 0), ('imm', 0)], stage='AL')
W(0x0084); W(0x0814); BR(0xF4, "OUT")        # 0x08 FALSE = no .kap loaded

# ---- 2. take Bose's own tone port (proven: probe65, probe74, probe122)
ca.call1(W, BSR, ca.STUB['StreamKalimbaSink'], al=('imm', 3))
W(0x0227)                       # st AL,@(2,Y)  ksink
W(0x0084); W(0x1214); BR(0xF4, "OUT")        # 0x12 no sink

# ---- 3. NWORDS payload bytes plus two state words. 128 total.
ca.call1(W, BSR, ca.STUB['malloc'], al=('imm', NWORDS + 2))
W(0x0327)                       # st AL,@(3,Y)  buf
W(0x0084); W(0x0614); BR(0xF4, "OUT")        # 0x06 pool exhausted

# ---- 4. zero the state words and derive the payload pointer.
# malloc'd memory is not guaranteed zero and buf[0] == 0 is nib_fill's first-call
# sentinel, so the caller zeroes it rather than seeding a constant.
W(0x031B)                       # ld X,@(3,Y)
W(0x0014); W(0x0026); W(0x0126) # buf[0] = 0 (sentinel), buf[1] = 0
W(0x0317); W(0x0234); W(0x0427) # samples = buf + 2 -> slot 4

# ---- 5. generate the nibbles. kalsim-verified and bit-exact in probe81; measured at
# NWORDS = 126 as -20.9 dBFS, 0.00% clipped, step index held at 36 (tools/noisespec.py).
# (CORRECTED: -23.0 was tools/noisespec.py's THREE-REFILL figure; the single-pass
# value this probe actually emits is -20.9 dBFS, peak 5100. Confirmed against the
# emulator's own bytes. probe129 raises PRIME to 12 for -10.2 dBFS.)
ca.call2(W, BSR, "NIBS", al=('slot', 4), ah=('slot', 3))

# ---- 6. a Source over the generated bytes. One byte per 16-bit word, low 8 bits,
# so NWORDS words carry NWORDS bytes = 2*NWORDS ADPCM samples.
ca.call2(W, BSR, ca.STUB['StreamRegionSource'],
         al=('slot', 4), ah=('imm', NWORDS))
W(0x0527)                       # st AL,@(5,Y)  src
W(0x0084); W(0x0114); BR(0xF4, "OUT")        # 0x01 no source

# ---- 7. Bose's own recipe, proven to carry audio in probe104.
ca.call2(W, BSR, ca.STUB['TransformAdpcmDecode'], al=('slot', 5), ah=('slot', 2))
W(0x0427)                       # st AL,@(4,Y)  t   (samples is finished with)
W(0x0084); W(0x0A14); BR(0xF4, "CLOSESRC")   # 0x0A no transform

# ---- 8. go.
ca.call1(W, BSR, ca.STUB['TransformStart'], al=('slot', 4))
W(0x0084); W(0x1614); BR(0xF4, "CLOSESRC")   # 0x16 would not start
W(0x0214); BR(0xE0, "OUT")                   # 0x02 SUCCESS -- the noise is the report

# A source exists but nothing consumes it: close it so a failed arm leaks nothing.
# TransformDisconnect would NOT free it (docs/cave-heap.md), which is the probe105 leak.
LBL("CLOSESRC")
ca.call1(W, BSR, ca.STUB['SourceClose'], al=('slot', 5))

LBL("OUT")
W(0xF80F)                       # leavel -8, which returns
BR(0xE0, "DONE")

LBL("DONE")

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
        # Probe for the next band LAZILY, and treat "there is no next band" as needing no
        # connector reservation. Computing it eagerly made the LAST band throw even when
        # the item fitted and no handoff was required -- which rejected layouts that were
        # perfectly valid (probe113 needs 231 of the 262 writable words and was refused).
        # The reservation is also `cs`, not `cs - 1`: the connector occupies cs words
        # starting at addr+need, so placing an item needs addr + need + cs <= band_end.
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

# The entry jump at CAVE, and nothing else in band 0.
# probe126 also parked a 2-word TaskData at CAVE+1 for its message handler. probe128 has
# NO handler -- it is a single pass with no timer -- so CODE_AT is CAVE+1 and those two
# words are now CODE. Writing TaskData here would overwrite the first instructions, which
# is why the inherited assert below is kept: it fires if anything ever claims them again.
entry_v = CODE_AT - CAVE
assert -128 <= entry_v <= 127
assert CAVE not in out, 'the entry jump word is already occupied'
out[CAVE] = ((entry_v & 0xFF) << 8) | 0xE0
assert 'HANDLER' not in label_addr, 'a handler exists but no TaskData is emitted for it'

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

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe128_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe128_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe128_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe128_cmd.txt")
