#!/usr/bin/env python3
"""probe116: does MESSAGE_MORE_SPACE arrive on a Kalimba port at all?

**No audio. One spoken answer, three seconds after the press.** This probe makes no
sound on purpose: it asks the single question that the whole sink-driven refill
architecture rests on, and that question can be answered without a generator.

## Why this is not the full refill probe

The full design was built first and **does not fit the cave**: it needed
**291 words against the 262 writable ones**, 29 short, measured by the assembler rather
than estimated (`cave exhausted: ... 29 more words of program remain unplaced`). The
57-word lifted `nib_fill` is the largest single block in it, so the control logic cannot
be trimmed far enough -- dropping both the `SourceSize` gate and the `SinkConfigure`
would recover about 12.

Closing the remaining gap means either shrinking the generator or recompiling it with
`NWORDS = 636` so the TaskData and the sample buffer fit in **one** 642-word pmalloc
block (`2 + 2 + 636 = 640`), which would remove the second `malloc`, its bail and the
handler's `buf` load -- about 14 words. Both touch the one piece of this project that is
kalsim-verified and bit-exact on hardware, so neither belongs in a blind trim. **It is
also not worth doing until the mechanism is known to work**, which is this probe.

## What had to be corrected to get here

**The const pool is not writable, so `buf` cannot be persisted there.** The plan for this
probe said to store it in the cave's `TaskData` or a const-pool word. The cave *is* the
const pool (DATA `0x7400`-`0xD39A`, 24475 words) -- the flash region `tools/fsedit.py`
patches with RSA digest compensation. Measured, not assumed: across all 236,514 words of
code Bose performs **0 stores** into that window against **11,281 loads**. That is
precisely why probes 111 and 113 ride `buf` in the MessageId field.

**The way out is a malloc'd TaskData**, which this probe keeps. A handler receives
**Task in `AL`** and MessageId in `AH` (`docs/message-task-abi.md:49`), and a `TaskData`
is only `{hi(handler), lo(handler)}` -- two words the VM reads and never writes. So the
task can live in RAM, `AL` becomes a writable pointer, and `AH` is free to carry a real
MessageId. The handler address is patched into an immediate once layout converges.

**`SinkSlack` would answer the wrong question.** The plan said to size refills with it.
`fn_24085` (15 words, 13 callers) shows what it is for:

    fn_24085(AL = sink, AH = x, arg3 = threshold):
        if SinkSlack(sink) < threshold: return 0      # 0x2408b, cmp then bcz
        return fn_237d1(sink, x)

a gate on "has the sink room for the N words I am about to write **myself**" -- probe114's
claim-write-flush route. A `TransformAdpcmDecode` pulls as the DSP consumes, so the refill
size is not ours to choose. The full design therefore gates on `SourceSize(buf[1])`
instead: has the current source drained? That is recorded for when it is built.

## The probe

    cave      t = malloc(3) ; t[0..1] = &handler ; t[2] = 0      the arrival flag
              MessageSendLater(t, 0x4100, 0, 400 ms)             our own setup id
              speak 0x0E                                          the FIRMWARE loads a DSP
              replay fn_395dd

    handler   (AL = t, AH = id)
              ksink = StreamKalimbaSink(3)                        once, before dispatch
              id == 0x4100 -> MessageSinkTask(ksink, t)            take the port's task
                              SinkConfigure(ksink, VM_SINK_MESSAGES, VM_MESSAGES_SOME)
                              MessageSendLater(t, 0x4101, 0, 3000 ms)   the verdict timer
              id == 0x8022 -> t[2] = 1      MESSAGE_MORE_SPACE ARRIVED. Say nothing yet.
              id == 0x4101 -> speak 0x13 if t[2] else 0x12
              else         -> return                              ignores MORE_DATA

`VM_MESSAGES_SOME` (`vm_if.h:87`) sends at most one message at a time, so even if the port
is noisy this cannot queue messages into the heap the way probes 105 and 106 did.

Nothing is connected to the port and no source is built, which is deliberate:
`MESSAGE_MORE_SPACE` means *the sink has room*, so it should fire on a ready, empty port.
If it only fires once something is streaming, that shows up as the negative below and is
worth knowing for the same price.

**NOTHING PAIRED. Press the CENTRE / voice-assistant button once, then wait 3 seconds.**

    "connected to", then "voice prompts off"
        -> **MESSAGE_MORE_SPACE arrives on a Kalimba port.** The sink-driven clock is
           viable, and the full refill probe is worth the generator rework needed to fit
           it in 262 words.
    "connected to", then "voice prompts on"
        -> the task registered and the sink configured, but no MORE_SPACE in 3 s. The
           sink-driven clock is dead on this port and **probe113's 140 ms timer is the
           only refill route** -- which is already built, signed and queued.
    "connected to" and then nothing at all
        -> the verdict timer never fired, so the message loop is not dispatching to a
           malloc'd TaskData. That would invalidate the malloc'd-task idea itself, which
           is worth catching before the full design is built on it.
    "lost"      -> StreamKalimbaSink(3) returned 0.
    "ready to connect" -> SinkConfigure refused VM_SINK_MESSAGES on this sink.
    "disconnected"     -> malloc failed.
    "english"   -> the hook fired but this button emits another event.
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
# No generator and no buffer: this probe makes no sound, it asks one question. Dropping
# the 57-word lifted nib_fill is most of what makes it fit.

# Band 0 holds the entry jump and the 2-word TaskData; the code proper starts in
# band 1, because the hook's prefix fold pins the entry address and cannot be
# retargeted (docs/cave-frame.md, docs/message-task-abi.md).
# Band 0 holds ONLY the entry jump now: the TaskData is malloc'd, because the const
# pool this cave lives in is read-only at runtime (0 stores against 11,281 loads in the
# whole image). The code proper starts in band 1, since the hook's prefix fold pins the
# entry address and cannot be retargeted.
BAND0 = [CAVE]
assert all(blind(a) and in_run(a) for a in BAND0)
CODE_AT = CAVE + 1
assert blind(CODE_AT) and in_run(CODE_AT), hex(CODE_AT)

FIRSTFILL = 0x4100      # our own first-fill id; only this cave ever sends it
MORE_SPACE = 0x8022     # SYSTEM_MESSAGE_BASE_ + 34, system_message.h:107
VM_SINK_MESSAGES = 0x0004          # stream_if.h:145
VM_MESSAGES_SOME = 1               # vm_if.h:87 -- at most one outstanding, self-throttling
DELAY_MS = 400          # inside the prompt, after its loader has run
VERDICT = 0x4101        # our own verdict id, fired 3 s after setup
VERDICT_MS = 3000
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


W(0xF00B)                       # enterl -16  (slots 0..13 usable, 14/15 = link)
W(0x0A23)                       # st AH,@(10,Y)  the event id we were called with

W(*ca.imm_words(VA_EVENT, 0x80))   # cmp AH,#0x4004
BR(0xF0, "PASS")

# The TaskData, in RAM, because the const pool this cave lives in is read-only at runtime.
# t[2] is the arrival flag MORE_SPACE sets and the verdict timer reads.
ca.call1(W, BSR, ca.STUB['malloc'], al=('imm', 3))
W(0x0C27)                       # st AL,@(12,Y)  t
W(0x0084); BR(0xF4, "NOMEM")
W(0x0C1B)                       # ld X,@(12,Y)
W(0x0314); W(0x0026)            # t[0] = 3 = hi(HANDLER_AT), fixed for a cave in 0x3Exxx
HLO_IDX = len(prog)
W(*ca.imm_words(0xE200, 0x14))  # ld AL,#lo(HANDLER_AT) -- PATCHED after layout
W(0x0126)                       # t[1] = lo(HANDLER_AT)
W(0x0014); W(0x0226)            # t[2] = 0   no MORE_SPACE seen yet

ca.calln(W, BSR, ca.STUB['MessageSendLater'],
         al=('slot', 12), ah=('imm', FIRSTFILL),
         stack=[('imm', 0), ('long', DELAY_MS)], stage='AL')

W(0x0E14)                       # ld AL,#0x0E  "connected to"
BSR(SPEAK)                      # ask the FIRMWARE for a prompt, so IT loads the DSP
BR(0xE0, "PASS")
LBL("NOMEM")
W(0x0814); BSR(SPEAK)           # 0x08 "disconnected" -- malloc failed

LBL("PASS")
W(0x0014); W(0x0027)            # ld AL,#0 ; st AL,@(0,Y)   message = 0
ca.load_al(W, ('imm', 0x512))
W(0x0A13)                       # ld AH,@(10,Y)
BSR(SEND)
W(0xF00F)                       # leavel -16, which returns

# ---- the handler. AL = t (our malloc'd TaskData), AH = a REAL MessageId.
LBL("HANDLER")
W(0xF00B)                       # enterl -16
W(0x0A27)                       # st AL,@(10,Y)  t
W(0x0923)                       # st AH,@(9,Y)   id

# The port handle, once, before the dispatch. It runs on messages we ignore, which is
# harmless: StreamKalimbaSink is a handle lookup, not an allocation.
ca.call1(W, BSR, ca.STUB['StreamKalimbaSink'], al=('imm', 3))
W(0x0D27)                       # st AL,@(13,Y)  ksink
W(0x0084); BR(0xF4, "NOSINK")

W(0x0913)                       # ld AH,@(9,Y)   reload the id; the call clobbered AH
W(*ca.imm_words(FIRSTFILL, 0x80))   # cmp AH,#0x4100
BR(0xF4, "SETUP")
W(*ca.imm_words(MORE_SPACE, 0x80))  # cmp AH,#0x8022
BR(0xF4, "ARRIVED")
W(*ca.imm_words(VERDICT, 0x80))     # cmp AH,#0x4101
BR(0xF0, "HEXIT")               # not ours: MESSAGE_MORE_DATA and everything else

# ---- the verdict, 3 s after setup.
W(0x0A1B)                       # ld X,@(10,Y)
W(0x029A)                       # tst @(2,X)     the arrival flag
BR(0xF4, "NEVER")
W(0x1314); BSR(SPEAK)           # 0x13 "voice prompts off" -- MORE_SPACE DID ARRIVE
BR(0xE0, "HEXIT")
LBL("NEVER")
W(0x1214); BSR(SPEAK)           # 0x12 "voice prompts on"  -- it never did
BR(0xE0, "HEXIT")

# ---- MESSAGE_MORE_SPACE. Record it and say nothing: with VM_MESSAGES_SOME it can still
# repeat, and speaking here would reload the DSP and confuse the verdict.
LBL("ARRIVED")
W(0x0A1B)                       # ld X,@(10,Y)
W(0x0114); W(0x0226)            # t[2] = 1
BR(0xE0, "HEXIT")

# ---- setup: take the port's task from the prompt and point it at US. fn_22f6f leaves
# its own task 0xbd4e on port 3. Safe here, unlike in probes 111 and 113, precisely
# because AH is no longer carrying a heap pointer.
LBL("SETUP")
ca.call2(W, BSR, ca.STUB['MessageSinkTask'], al=('slot', 13), ah=('slot', 10))
ca.call3_long(W, BSR, ca.STUB['SinkConfigure'],
              al=('slot', 13), ah=('imm', VM_SINK_MESSAGES), arg3_32=VM_MESSAGES_SOME)
W(0x0084); BR(0xF4, "NOCFG")
ca.calln(W, BSR, ca.STUB['MessageSendLater'],
         al=('slot', 10), ah=('imm', VERDICT),
         stack=[('imm', 0), ('long', VERDICT_MS)], stage='AL')
BR(0xE0, "HEXIT")

LBL("NOCFG");  W(0x0014); BSR(SPEAK); BR(0xE0, "HEXIT")  # 0x00 "ready to connect"
LBL("NOSINK"); W(0x0614); BSR(SPEAK)                     # 0x06 "lost"
LBL("HEXIT")
W(0xF00F)                       # leavel -16, which returns
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
            if nb_probe is None:
                # Quantify the shortfall rather than just refusing: sum the sizes of the
                # items that could not be placed, so the budget negative is a number.
                _left = 0
                for _j in range(i, len(prog)):
                    _k = prog[_j][0]
                    if _k == "label":
                        continue
                    if _k == "w":
                        _left += len(prog[_j][1])
                    elif _k == "bsr":
                        _left += bsr_size.get(_j, 0)
                    else:
                        _left += br_size.get(_j, 1)
                raise AssertionError(
                    'cave exhausted: %d writable words is not enough; %d more words of '
                    'program remain unplaced at item %d of %d'
                    % (sum(y - x for x, y in _BANDS), _left, i, len(prog)))
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

# entry jump, then patch the handler address into the immediate that builds the
# malloc'd TaskData at runtime. The value is only known after layout; the encoding width
# is not, by construction -- hi is always 3 for a cave in 0x3Exxx, and lo is always in
# 0xE2xx-0xEAxx, whose high byte is non-zero, so imm_words always returns two words.
entry_v = CODE_AT - CAVE
assert -128 <= entry_v <= 127
assert CAVE not in out
out[CAVE] = ((entry_v & 0xFF) << 8) | 0xE0
HANDLER_AT = label_addr["HANDLER"]
assert (HANDLER_AT >> 16) == 3, hex(HANDLER_AT)
_hlo = ca.imm_words(HANDLER_AT & 0xFFFF, 0x14)
assert len(_hlo) == 2, _hlo
_ha = addrs[HLO_IDX]
for k, v in enumerate(_hlo):
    out[_ha + k] = v
print("handler a=%#x -> TaskData built at runtime: hi=0003 lo=%04x (imm patched at %#x)"
      % (HANDLER_AT, HANDLER_AT & 0xFFFF, _ha))

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

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe116_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe116_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe116_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe116_cmd.txt")
