#!/usr/bin/env python3
"""probe127: the same audio design, on a hook that is downstream of every gate.

probe126 produced **nothing but a double LED flash** on a volume-up short press. With
success now announced, that is unambiguous: **the hook did not fire.**

## Why 0x10823 was still the wrong hook

`fn_1061b` dispatches on its **second argument**, `@(8,Y)`:

    0x10626: ld AL,@(8,Y) ; cmp AL,#0x1 ; bne -> 0x107c1     mode 1: the jump table
    0x107c2: ld AL,@(8,Y) ; cmp AL,#0x2 ; bne -> 0x1082a     mode 2: the fn_105b2 lookup

`0x107be` lives on the **mode 1** path and `0x10823` on the **mode 2** path. So
"`0x10823` is the dispatcher's common exit, reached by any button in any state" was wrong
-- it is the common exit *of mode 2 only*, and a volume short press evidently does not
arrive in mode 2. That is the third hook in a row chosen on an incomplete reading of its
reachability, and the pattern is mine to own: I kept picking sites by what they looked
like locally instead of proving the path from the button to the site.

## The hook that cannot be gated out

`fn_189fb` is 13 words and is called from `0x812`, `0xe46` and `0x11fe7`. **`0xe46` is
`fn_00846`'s epilogue**, and `fn_00846` is the task-`0x512` handler that every `0x40xx`
user event passes through -- its `0x4008` and `0x400d` cases both land on `0x00e27`, which
branches to that epilogue. So `fn_189fb` sees **every** user event the app processes,
regardless of dispatcher mode, `sinkState`, or the A2DP-streaming latch.

Its send is at **`0x18a04`**, a 3-word `bsr` with **all operand bytes blind**:

    0x189fb: enterl -8
    0x189fc: ld AH,#0x1          ; message id 1
    0x189fe: st AL,@(2,Y)        ; <-- THE EVENT, parked in the frame
    0x189ff: ld AL,@0xffe4 ; add AL,#2 ; st AL,@(0,Y)   ; message = &event
    0x18a02: ld AL,#0xa5ce       ; the event-queue task
    0x18a04: bsr fn_395dd        ; <-- OUR HOOK.  v = 153623, bytes 02 58 17
                                 ;     fs 0x9fe39 / 0x9fe3b / 0x9fe3d, all blind

The event is readable at `@(2,Y)` on arrival, which is how the cave gates on it.

## Frame handling, which is the one delicate part

`fn_395dd` reads its **caller's** slot 0 for the message, so after our `enterl` the replay
would read *our* slot 0. The cave therefore captures `Y + 2` (the message pointer) into a
register **before** its own `enterl`, parks it, and restores it to slot 0 immediately
before replaying `fn_395dd(AL = 0xa5ce, AH = 1)`. Nothing downstream can tell the
difference.

Everything else is probe126 unchanged: gate on `0x400d`, `KalimbaSendMessage(0x1072,
8000)` to arm port 3, `malloc(317)` sized to the 318-word pool block, no teardown, and
every outcome -- success included -- spoken through the message handler.

**Play music, pause it, then SHORT-PRESS VOLUME UP.**

    "voice prompts off"  -> all six calls succeeded, malloc(317) included.
    "lost"               -> malloc(317) returned 0; the heap is closed.
    "disconnected"       -> no .kap loaded; play music first.
    "voice prompts on"   -> StreamKalimbaSink(3) returned 0.
    "connecting to" / "connecting" / "english" -> region / ADPCM / start returned 0.
    nothing at all       -> even fn_189fb did not fire, which would mean the volume press
                            produces no 0x40xx event through fn_00846 at all.
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
REDIRECT_EDITS = [("0x9fe39", "0x02"), ("0x9fe3b", "0x58"), ("0x9fe3d", "0x17")]
SEND = 0x395DD          # fn_395dd(task=AL, id=AH, message=@(0,Y)); reads CALLER's slot 0
EVENT = 0x400D          # EventUsrMainOutVolumeUp: table entry 14, B_SHORT,
                        # state mask 0x00c0fffe -- fires in any state, repeatably
NWORDS = 315            # matches the recompiled generator; malloc(317) fits the 318 pool
REPORT_MS = 300
QTASK = 0xA5CE          # the event-queue task fn_189fb posts to         # delay before a failure id is spoken from message context
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
BAND0 = [CAVE + k for k in range(3)]       # entry jump + the 2-word TaskData
assert all(blind(a) and in_run(a) for a in BAND0)
CODE_AT = CAVE + 3                        # no longer skips the rest of band 0
assert blind(CODE_AT) and in_run(CODE_AT), hex(CODE_AT)

TASK_AT = CAVE + 1
TASK_PTR = ca.const_addr(TASK_AT)
DELAY_MS = 400          # inside the prompt, after its loader has run
# NWORDS is defined near the top as 315. The inherited `NWORDS = 639` line was removed
# here: it executed LATER and silently restored malloc(641), the exact failure probe125
# exists to fix. Caught by reading the generated file before flashing.
assert (NWORDS - 9) % 3 == 0, 'tmpl_fill unrolls the cycle three words at a time'
REFILL_MS = 140         # against 160 ms of data: ~7 cycles/s, not probes 105/106's 36
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


# Y still belongs to fn_189fb here, and @(2,Y) holds the event. Capture the message
# pointer (Y + 2) into X BEFORE our own enterl, because fn_395dd reads its CALLER's slot 0
# and after enterl that is ours, not fn_189fb's.
W(0xE415)                       # ld AL,@0xffe4   AL = Y (fn_189fb's frame)
W(0x0234)                       # add AL,#2       -> &event, the message pointer
W(0xE119)                       # ld X,@0xffe1    X = AL

W(0xF00B)                       # enterl -16  (slots 0..13 usable, 14/15 = link)
W(0x062B)                       # st X,@(6,Y)    the message pointer, for the replay
W(0x061B); W(0x0016)            # ld X,@(6,Y) ; ld AL,@(0,X)   AL = the event id
W(0x0A27)                       # st AL,@(10,Y)  the event

W(*ca.imm_words(EVENT, 0x84))   # cmp AL,#0x400d
BR(0xF0, "PASS")

# Arm the port-3 reader. probe122 proved this succeeds with sbc_decoder loaded; probes
# 113-121 omitted it on the reasoning that the PROMPT dsp has no 0x10xx handler, which is
# true and irrelevant once A2DP's decoder is what is up. Word b = 0 selects shift 7.
ca.calln(W, BSR, ca.STUB['KalimbaSendMessage'],
         al=('imm', 0x1072), ah=('imm', 8000),
         stack=[('imm', 0), ('imm', 0), ('imm', 0)], stage='AL')
W(0x0084); W(0x0814); BR(0xF4, "REPORT")     # 0x08 "disconnected"

ca.call1(W, BSR, ca.STUB['StreamKalimbaSink'], al=('imm', 3))
W(0x0B27)                       # st AL,@(11,Y)  ksink
W(0x0084); W(0x1214); BR(0xF4, "REPORT")     # 0x12 "voice prompts on"

# 317, NOT 320. 320 exceeds the 318-word pool block and so demands the single 642, which
# is taken -- that two-word overshoot is the most likely cause of probe122's "lost".
ca.call1(W, BSR, ca.STUB['malloc'], al=('imm', NWORDS + 2))
W(0x0C27)                       # st AL,@(12,Y)  buf
W(0x0084); W(0x0614); BR(0xF4, "REPORT")     # 0x06 "lost"
W(0x0C1B)                       # ld X,@(12,Y)
W(0x0014); W(0x0026); W(0x0126) # buf[0] = 0 (nib_fill sentinel), buf[1] = 0
W(0x0C17); W(0x0234); W(0x0D27) # samples = buf + 2 -> slot 13
ca.call2(W, BSR, "NIBS", al=('slot', 13), ah=('slot', 12))

ca.call2(W, BSR, ca.STUB['StreamRegionSource'],
         al=('slot', 13), ah=('imm', NWORDS))
W(0x0927)                       # st AL,@(9,Y)   src
W(0x0084); W(0x0114); BR(0xF4, "REPORT")     # 0x01 "connecting to"

ca.call2(W, BSR, ca.STUB['TransformAdpcmDecode'], al=('slot', 9), ah=('slot', 11))
W(0x0927)                       # st AL,@(9,Y)   t
W(0x0084); W(0x0A14); BR(0xF4, "REPORT")     # 0x0A "connecting"

ca.call1(W, BSR, ca.STUB['TransformStart'], al=('slot', 9))
W(0x0084); W(0x1614); BR(0xF4, "REPORT")     # 0x16 "english"

# SUCCESS NOW SPEAKS. probe125 stayed silent on success, which made "nothing at all"
# ambiguous between (a) the hook never fired and (b) all six calls worked and 79 ms at
# -21 dBFS was simply too quiet and brief to notice. That ambiguity wasted a press, so
# the win case gets its own id. The handler speaks 300 ms later, by which time the 79 ms
# of audio is long finished, so the prompt cannot mask it.
W(0x1314); BR(0xE0, "REPORT")   # 0x13 "voice prompts off" = ALL SIX CALLS SUCCEEDED

# ---- a failure id reaches the owner through a MESSAGE handler, which is the only
# mechanism that has ever worked (probe99). AL holds the id on arrival here.
LBL("REPORT")
# AL holds the failure id. MessageSendLater wants task in AL and id in AH, so park the id
# first. Then fall through to PASS so the displaced send is still replayed.
W(0x0827)                       # st AL,@(8,Y)   the id
ca.calln(W, BSR, ca.STUB['MessageSendLater'],
         al=('imm', TASK_PTR), ah=('slot', 8),
         stack=[('imm', 0), ('long', REPORT_MS)], stage='AL')

LBL("PASS")
# Replay exactly what fn_189fb was about to do: fn_395dd(task = 0xa5ce, id = 1,
# message = &event). Slot 0 must hold the ORIGINAL message pointer, which ca.call* will
# have overwritten, so it is restored from slot 6 here.
W(0x0617); W(0x0027)            # ld AL,@(6,Y) ; st AL,@(0,Y)   message = &event
ca.load_al(W, ('imm', QTASK))
W(0x0110)                       # ld AH,#0x1      the message id fn_189fb uses
BSR(SEND)
W(0xF00F)                       # leavel -16, which returns
BR(0xE0, "DONE")

# ---- the handler: speak whatever id it was sent. Task in AL, MessageId in AH.
LBL("HANDLER")
W(0xF00B)                       # enterl -16
W(0xE015)                       # ld AL,@0xffe0   AL = AH = the id
BSR(SPEAK)
W(0xF00F)                       # leavel -16
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

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe127_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe127_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe127_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe127_cmd.txt")
