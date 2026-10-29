#!/usr/bin/env python3
"""probe152: THE PORT-SINK CENSUS -- write-free, allocation-free, and it decides
whether the only architecture that CANNOT leak is available at all.

## WHY THE LOOP REPAIRS ARE OVER

Hardware record of the refill loop, every line a press:

  probe145  per-tick SourceClose present     ~9 s  = ~82 ticks
  probe146  that SourceClose removed         ~6 s  = ~55 ticks
  probe149  + ids                            ~6 s, 0x3D, 0x3B SILENT
            -> StreamRegionSource NEVER fails
  probe150  + split the transform id          ~6 s, 0x3D, 0x39 SILENT
            -> TransformAdpcmDecode RETURNS 0: creation refused
  probe151  stored the transform handle and called TransformStop +
            TransformDisconnect on it EXPLICITLY every tick, replacing the
            TransformFromSink lookup that returned 0 every tick
                                             ~6 s, 0x3D, **UNCHANGED**

probe151 is the decisive negative. Invoking `TransformDisconnect` -- the trap
`transform.h:45-55` documents as "Disconnect and destroy a transform" -- on the
handle `TransformAdpcmDecode` itself returned, every single tick, reclaimed
NOTHING. The tick count did not move.

So the tally is: no frees = 55 ticks. Explicit transform destruction = 55 ticks.
`SourceClose` = 82 ticks. **The only lever that has ever moved the number is
SourceClose, and the best it buys is 9 seconds.** The target is hours.

The structural reading: ANY per-tick allocation against a fixed pool, with
imperfect reclamation, dies at a fixed tick count. The fix is not a better free.
It is to stop allocating.

## THE ARCHITECTURE THAT CANNOT LEAK, AND THE ONE QUESTION IT RESTS ON

Write PCM straight into the Kalimba port sink:

    SinkSlack(ksink)            how much room is there
    SinkClaim(ksink, n)         reserve n bytes IN THE PORT'S OWN BUFFER
    SinkMap(ksink)              a pointer to it
    ...generate samples directly into that memory...
    SinkFlush(ksink, n)         commit

No region source. No transform. No `malloc` for audio at all -- the samples go
into the sink's own buffer, so **the per-tick allocation count is zero** and the
failure mode this project has spent five presses on cannot occur. As a bonus it
retires the ADPCM zero-net-block structure that makes the current output a
333 Hz carrier with four waveform states -- the "modem" tonality.

It rests on one unverified assumption: **are `SinkClaim`/`SinkMap` usable on a
Kalimba/MMU port sink?** `docs/dsp-noise-route.md` calls this the single most
load-bearing untested idea in the route, `docs/firmware-map.md:154` calls it
"still the open question", and every stock `SinkClaim`/`SinkMap` call site in the
firmware is a BT or USB pipe -- none in the Kalimba cluster. probe140 proved the
idiom works from a cave on a PARTITION sink; a port sink has never been asked.

**And `sink.h:46-47` says how it could die outright: "If the sink is an operator
sink stream then it always returns 0xFFFF, irrespective of whether [it] is valid
or not."** If port 3 registers as an operator sink, the architecture is dead on
arrival. BlueCore port sinks predate the operator framework, so it may instead be
a real claimable MMU buffer. This probe settles it for near-zero risk.

## THE THREE DOCUMENTED TRAPS THIS PROBE IS BUILT AROUND

  1. **`sink.h:44` -- `SinkClaim` returns ZERO if the sink stream is connected.**
     So **0 is a REFUSAL SENTINEL, not "granted at offset 0"**. An earlier draft
     of this probe read 0 as success; that is exactly the inverted guard that
     makes `fn_12e1a` (`full-disasm.txt:64838-64854`) memset `size` words from
     data address ~0 on a connected sink -- the wild write that cost probe123
     (`POST-MORTEM-2026-10-04.md:82`). Here BOTH 0 and 0xFFFF are refusals, and
     they get DIFFERENT ids because they mean different things: 0xFFFF points at
     the operator-sink clause (architecture dead), 0 at a connection (possibly
     addressable).
  2. **`sink.h:48-49` -- `SinkClaim` "will block VM application if there are not
     sufficient buffer memory resources."** A claim can HANG the press. So
     `SinkSlack` is the gate: the claim is only attempted once the port has
     admitted to at least as much room as we ask for, and we ask for FOUR BYTES.
  3. **`sink.h:24` / `:66` -- `SinkSlack` and `SinkMap` also return 0 on a
     connected sink**, so a zero from either is "unusable", never a value.

`SinkSlack` is read-only and cannot scribble, which is why it goes first
(`docs/deep/buffer-cadence.md:535-540` recommends exactly that). The map pointer
is stored for the record and **never dereferenced**, because this probe writes
nothing at all.

## WHAT IT DOES, AND WHAT IT CANNOT DO

    1. the 0x1072 gate, exactly as the loop uses it -- boot-safe silent bail
       when no DSP is up, and it leaves the tone port armed as the loop would
    2. ksink = StreamKalimbaSink(3)
    3. SinkSlack(ksink)      -- a question; also the gate against trap 2
    4. SinkClaim(ksink, 4)   -- the real question, four bytes
    5. SinkMap(ksink)        -- confirmation only
    6. speak ONE id saying how far it got
    7. **NO SinkFlush.** Nothing is committed, nothing reaches the audio path,
       no sample is ever presented to the DSP.

NO malloc. NO transform. NO source. NO timer, so no loop and nothing to stop.
NO flash writes. The only state touched is a four-byte reservation in a port
buffer that is never committed and is gone at power-off.

## THE OUTCOME LATTICE (battery family -- probe139's proven census channel)

  battery 10%   StreamKalimbaSink(3) returned 0 -- no port sink even with a DSP
                up. That contradicts five probes that got one; re-press.
  battery 20%   SinkSlack unusable: 0xFFFF, or less than the 4 bytes we need
                (which covers 0, i.e. invalid or connected). The port admits no
                writable room -> direct write is DEAD, and the loop is all we
                have.
  battery 40%   SinkClaim returned 0xFFFF -> the `sink.h:46-47` operator-sink
                clause. Direct write is DEAD ON ARRIVAL, definitively.
  battery 30%   SinkClaim returned 0 -> the CONNECTED sentinel, a different
                failure: the port is claimable in principle but something holds
                it. Worth attacking.
  battery 80%   claim granted a real offset but SinkMap returned 0 --
                contradictory, and the fn_12e1a hazard case, caught by its guard.
  battery 90%   **FULL SUCCESS: slack >= 4, claim granted a REAL offset, map
                non-zero.** The direct port write is available, and probe153 is
                the real thing: generate PCM into the claimed space, flush, and
                refill with ZERO allocations per tick.

0x2B/0x2C (50/60%) are skipped -- the catalog's first pass read them EMPTY and no
probe has exercised them. 0x2D (70%) is skipped: it was probe139's census answer
and reusing it would muddy that record. 0x30 (100%) is skipped because the
speaker says it by itself at power-on. 0x3B/0x3D/0x39/0x1F belong to the loop
probes and stay out of this lattice.

## ONE ID, AT THE END, DELIBERATELY

A two-id scheme was considered and rejected: speaking loads the prompt DSP, and
doing that BEFORE the census would change the very port state being measured.
The single id is spoken only after every query has run.

## The press (laptop connected, music PAUSED, long-press the BLUETOOTH button)

There is no audio in this probe. Exactly one spoken prompt, or silence if the
gate bailed because no DSP was up. Nothing to stop, nothing to time.

## What is NOT changed

The hook, the redirects (byte-identical to the family), the 0x1072 gate and its
2000 Hz rate, and the const-window discipline. Nothing of the refill loop is
present: probe152 shares no code with it beyond the gate and the entry.

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
# Byte-identical to probe134/136/137's redirects: the 0xAE0 bsr -> 0x3E21D,
# 0xae3 := bra +1, and the stock prompt call at 0xae4..0xae6 nopped so the only
# id the owner hears is the census result. All bytes are inside blind windows.
REDIRECT_EDITS = [("0x6fff1", "0x04"), ("0x6fff3", "0xd7"), ("0x6fff5", "0x3b"),
                  ("0x6fff6", "0xe0"), ("0x6fff7", "0x01"),
                  ("0x6fff8", "0x00"), ("0x6fff9", "0x00"),
                  ("0x6fffa", "0x00"), ("0x6fffb", "0x00"),
                  ("0x6fffc", "0x00"), ("0x6fffd", "0x00")]
AREA0 = 0x6EA30

BACK = 0xE06D           # the call the hook displaced: run it first, always
SPEAK = 0xDF7F          # prompt engine: id in AL, nothing in X, returns
KALMSG    = ca.STUB['KalimbaSendMessage']
KSINK     = ca.STUB['StreamKalimbaSink']
SINKSLACK = ca.STUB['SinkSlack']
SINKCLAIM = ca.STUB['SinkClaim']
SINKMAP   = ca.STUB['SinkMap']
RATE        = 2000       # the loop's tone rate: same port state
CLAIM_BYTES = 4          # TINY on purpose: sink.h:48-49 says a
                         #   claim BLOCKS the VM when buffer memory
                         #   is short, so SinkSlack gates it and we
                         #   ask for the smallest useful amount

# ids: docs/request-id-catalog.md (owner-verified 2026-09-29, all 64 anchored)
ID_P1_UNUSED, ID_SWEEP_BASE = None, 0x26     # sweep speaks n + 0x26 -> 0x27..0x2a
ID_P2_TYPE_BASE = 0x2a                       # none-path speaks TYPE + 0x2a -> 0x2b..0x2e
ID_P2_ABSENT = 0x14                          # "auto off disabled"
ID_CTRLFAIL = 0x23                           # "conference call failed"
KEY_TYPE = 2                                 # partition_info_key PARTITION_INFO_TYPE
DEV_SQIF = 1                                 # partition_filesystem_devices SERIAL_FLASH
MAX_PART = 4                                 # sweep 1..4 (0x182d4's `and AH,#3` says 0..3)

w = xapvm.load_words("firmware/bose/extracted/internal_fs/vm.app")
code = w[0x18:]
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
CODE_AT = CAVE + 1
assert blind(CODE_AT) and in_run(CODE_AT), hex(CODE_AT)

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))
# ---------------------------------------------------------------- the CENSUS
# One pass, six possible spoken ids, and NOT ONE WRITE. Guard order is
# SinkSlack -> SinkClaim -> SinkMap: Slack is read-only so it cannot scribble
# and it gates the blocking clause, and the map pointer is never dereferenced.
W(0xF80B)                       # enterl -8 (slots 0..5 usable, 6/7 = link)
BSR(BACK)                       # the stock back-call FIRST, probe77's order

# ---- the gate: KalimbaSendMessage(0x1072 SET_TONE_RATE, 2000, 0, 0, 0).
# Identical to the refill loop's, for two reasons: it is the project's boot-safe
# discipline (FALSE = no DSP = the power-on auto-fire bails in silence), and it
# leaves the tone port in the SAME armed state the loop would, so the census
# measures the port the loop would actually use.
W(0x0014)                       # ld AL,#0
W(0x0027); W(0x0127); W(0x0227) # b = c = d = 0        slots 0..2
W(*ca.imm_words(RATE, 0x10))    # ld AH,#2000
W(*ca.imm_words(0x1072, 0x14))  # ld AL,#0x1072
BSR(KALMSG)
W(0x0084); BR(0xF4, "OUT")      # FALSE -> no DSP -> SILENT bail, no id at all

# ---- ksink = StreamKalimbaSink(3)
ca.call1(W, BSR, KSINK, al=('imm', 3))
W(0x0227)                       # st AL,@(2,Y)  ksink
W(0x0084); BR(0xF4, "NOSINK")   # 0 -> no port sink even with a DSP up

# ---- SinkSlack(ksink). Read-only (sink.h:17-25), so it is safe to ask first,
# and it is the GATE against sink.h:48-49 -- a claim larger than the available
# buffer memory BLOCKS the VM, i.e. hangs the press.
ca.call1(W, BSR, SINKSLACK, al=('slot', 2))
W(0xFF84); BR(0xF4, "SLACKBAD")  # cmp AL,#0xffff ; beq -> invalid
W(0x0484); BR(0xFC, "SLACKBAD")  # cmp AL,#4 ; bcs -> AL < 4 (XAP carry: C=1 on
                                 #   borrow, so bcs = "less than"). This also
                                 #   catches 0, which sink.h:24 gives for a
                                 #   connected or invalid sink. Only past this
                                 #   point has the port admitted room for 4.

# ---- SinkClaim(ksink, 4) -- THE QUESTION. sink.h:32 gives the offset on
# success, 0xFFFF on refusal, and sink.h:44 gives ZERO on a CONNECTED sink.
# Zero is therefore a REFUSAL, not an offset: reading it as "offset 0" is the
# inverted guard that makes fn_12e1a memset from address ~0.
ca.call2(W, BSR, SINKCLAIM, al=('slot', 2), ah=('imm', CLAIM_BYTES))
W(0xFF84); BR(0xF4, "CLAIMFFFF") # 0xffff -> the operator-sink clause: DEAD
W(0x0084); BR(0xF4, "CLAIMZERO") # 0      -> the connected sentinel: refused

# ---- SinkMap(ksink) -- confirmation only. The pointer is stored for the record
# and NEVER DEREFERENCED: this probe writes nothing.
ca.call1(W, BSR, SINKMAP, al=('slot', 2))
W(0x0327)                       # st AL,@(3,Y)  map
W(0x0084); BR(0xF4, "MAPBAD")   # 0 -> contradictory, and the hazard case

# ---- full success: slack >= 4, claim granted a REAL offset, map non-zero
W(0x2F14)                       # ld AL,#0x2F "battery 90%" -- THE GO SIGNAL
BR(0xE0, "SAY")
LBL("MAPBAD")
W(0x2E14)                       # ld AL,#0x2E "battery 80%" -- claim OK, map 0
BR(0xE0, "SAY")
LBL("CLAIMFFFF")
W(0x2A14)                       # ld AL,#0x2A "battery 40%" -- 0xFFFF: operator
BR(0xE0, "SAY")                 #   sink, direct write dead on arrival
LBL("CLAIMZERO")
W(0x2914)                       # ld AL,#0x29 "battery 30%" -- 0: connected
BR(0xE0, "SAY")
LBL("SLACKBAD")
W(0x2814)                       # ld AL,#0x28 "battery 20%" -- no writable room
BR(0xE0, "SAY")
LBL("NOSINK")
W(0x2714)                       # ld AL,#0x27 "battery 10%" -- no port sink
LBL("SAY")                      # ...and fall through into the shared speech
BSR(SPEAK)                      # probe99's direct idiom, hardware-proven
LBL("OUT")                      # the gate's silent bail lands here too
W(0xF80F)                       # leavel -8

# ---- layout (proven machinery, probes 67-77, verbatim from probe137) ----
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
            if bsr_size.get(i, 2) != want: bsr_size[i] = want; ok = False
        else:
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
            # last-word relative -- the probe131/132 lesson, proven by census
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
