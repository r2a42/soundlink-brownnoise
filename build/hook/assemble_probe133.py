#!/usr/bin/env python3
"""probe133: probe132 with the ASSEMBLER's branch encoding fixed. No logic change.

probe131 (gate via `ble`) and probe132 (gate via `bne`) both crashed on the long press with
an uncut boot prompt. Two different encodings, one crash -- so the opcode was never the
issue. The real fault was in our own toolchain.

## Multi-word branches were targeted ONE WORD SHORT, for the project's whole history

An independent boundary census over Bose's 191,224 instructions — asking which rule lands
on a decoded instruction boundary, rather than asking the disassembler to confirm itself:

    2-word branches (2103):   a+v     886  (42.1%)      a+ln-1+v  2103  (100.0%)
    3-word bsr      (7473):   a+v    5788  (77.5%)      a+ln-1+v  7473  (100.0%)

**The displacement is relative to the LAST word of the instruction.** The assembler already
did this for `bsr` and used `tgt - a` for branches.

An earlier check of mine appeared to confirm `a+v` across all 2,102 multi-word branches.
That test was **circular**: it compared the disassembler's printed target against `a+v`,
and the disassembler computes that target with `a+v`. It could only ever agree.

## What it did on hardware

probe132's gate bail intended `0x3e320` and landed one word later:

    0x3e320: f80f   leavel -8     <- intended: the clean return
    0x3e321: 01e0   bra +1        <- where it actually went
    0x3e322: 0000   nop
    0x3e323: fe0b   enterl -2     <- nib_fill's prologue

So the bail fell **into the generator**, entered with `AL = sinkState` as its buffer
pointer, wrote 126 bytes through a bogus address and returned through a frame nobody
pushed. "Crash, no wedge" exactly.

And the bail was always taken: `0x00ac2` calls `fn_0d500`
(`stateManagerEnterConnDiscoverableState`), which ends `ld AL,#2 ; bsr fn_0d441` →
`st AL,@0x59e`, so **`sinkState` is 2 when the hook runs**, not 3 or 13. probe131's
`cmp AL,#2 ; ble` and probe132's `cmp AL,#3 ; bne` therefore both branch.

## Why ~130 probes survived it

Only a **taken** multi-word branch is affected. probe77 and probe104 contain none;
probe129's three 2-word `beq`s are failure paths that never fired (the fix decrements their
operands too, which is why rebuilding probe129 no longer matches its proven image — its
artifacts were restored rather than overwritten). probe131's gate was **the first taken
multi-word branch in the project's history.**

Nothing caught it because the assembler, `decode-verify` and `tools/xapemu.py` all shared
the one wrong rule, so all three agreed and `cavesim` showed the gate working on every path.
The emulator even documented the rule as "validated on probe3 and probe5" — both of which
use **one-word** branches, where `ln-1 == 0` and the two rules coincide.

## What changed in this probe

Nothing in the cave's logic. `assemble_probe*.py` now encodes 2- and 3-word branches as
`tgt - (a + sz - 1)`, chooses the size with the same measure, and `decode-verify` and the
emulator check with `a + ln - 1 + v`. probe133 is probe132 re-emitted correctly.

## And a correction to carry forward

**"The gate is boot-safe" was a vacuous claim.** `docs/deep/hook-gates.md` already
establishes that gates 2 and 3 at `0x0AE0` need a connected slot and a live A2DP streaming
latch, so the cave cannot execute at power-on with nothing connected. The uncut prompt was
a **null result**, not evidence the gate works — and probe121/130's boot crashes were the
far-run corruption, already attributed elsewhere.

Because `sinkState` is **2** at this hook, any gate demanding {3, 13} will always bail here.
The sinkState gate belongs to a future centre-button hook, not this one.

**Play music, PAUSE it, then LONG-PRESS the BLUETOOTH button.**

    short quiet "shh"  -> the branch fix is right AND the state is 3+ after all, so the
                          gate passed. Both the toolchain fix and the gate are good.
    silence            -> the fix works and the bail now lands on `leavel` as intended,
                          confirming sinkState == 2 at this hook. The gate must then be
                          dropped here, not widened.
    crash again        -> the branch rule is not the whole story; stop and re-analyse.
"""

import io, os, re, sys, json, subprocess
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

# --- output paths are derived from THIS FILE'S OWN NAME, never hardcoded -------------
# Every probe assembler is made by copying its predecessor, and three times now the copy
# kept the predecessor's hardcoded output paths and silently overwrote the artifacts of
# the image sitting ON THE DEVICE: probe129_words.json twice, probe134_words.json once
# (restored from build/hook/snapshots/ and re-verified against the device readback both
# times). A words.json is the only record of what a flashed image contains, so losing it
# costs the readback check its reference.
_PROBE = re.match(r'assemble_(probe[0-9a-z]+)\.py$',
                  os.path.basename(os.path.abspath(__file__))).group(1)

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
# PRIME is read out of the C rather than restated here, so this assert validates what was
# actually compiled. probe128's version hardcoded 9 and would have kept passing after the
# generator changed -- a check that cannot fail is worse than no check.
_c = io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          '..', 'noiseprobe', 'noise.c'), encoding='utf-8').read()
PRIME = int(re.search(r'#define\s+PRIME\s+(\d+)', _c).group(1))
_cn = int(re.search(r'#define\s+NWORDS\s+(\d+)', _c).group(1))
assert _cn == NWORDS, 'noise.c has NWORDS=%d but this assembler expects %d' % (_cn, NWORDS)
assert (NWORDS - PRIME) % 3 == 0, 'the cycle unrolls three words at a time'
print('generator: PRIME=%d, NWORDS=%d (read from noise.c)' % (PRIME, NWORDS))
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

# ---- THE GATE. docs/deep/buffer-cadence.md section 4d; six words.
# The cave runs at cold power-on (auto-pairing fires 0xAE0, and the battery prompt means a
# .kap is loaded so 0x1072 returns TRUE), which is when probes 121 and 130 crashed. Require
# a connected device before touching anything.
#
# INLINED, not called: fn_0d475 is only `ld AL,@0x59e ; rts`, so inlining saves a 3-word
# far bsr and adds NO call frame -- which matters because stack depth is the leading
# hypothesis for probe130, and a gate that deepened the stack would defeat itself.
#
# @0x59e has ONE writer in the image (0x0d460 in fn_0d441). At power-on it is 0 deviceLimbo
# or 1 deviceConnectable; only 3 and 13 are accepted, so an uninitialised zero bails too.
# Four words, ONE branch, no new label. Two branches plus a label made the layout
# engine oscillate without converging (it packs code into 14-word bands, and the extra
# label could not be placed stably), so the test is expressed as a single comparison.
#
# sink_states.h: 0 deviceLimbo, 1 deviceConnectable, 2 deviceConnDiscoverable,
#                3 deviceConnected, ... 13 deviceA2DPStreaming
# States 0/1/2 are exactly the pre-connection states the speaker is in at power-on; every
# state from 3 up implies a connection. So `<= 2 -> bail` is the gate, and anything that
# slips through still has to pass KalimbaSendMessage returning TRUE, which is the second,
# independent test section 4d asks for.
# ONE item, not two: `0x0600 0x9e15` is a single prefixed instruction, and emitting it as
# two items let the layout engine place a band connector between the prefix and its
# opcode, which decode-verify caught as a boundary error. W(a, b) keeps them adjacent.
W(0x0600, 0x9e15)               # ld AL,@0x59e   sinkState (encoding copied from 0x0d475)
# cmp AL,#3 ; bcc  -- NOT cmp AL,#2 ; ble. A two-word `ble` appears ZERO times in the
# 191,224 instructions of vm.app, and probe131 emitted one (OUT is 250 words away, so the
# branch needs two words). If 0x28 does not take a prefix, the hardware ignores the 0x0100
# and runs `ble -5`, jumping backwards into the prologue -- which is probe131's crash.
# `cmp AL,#imm ; bcc` is attested 905 times (74 of them two-word), same meaning here:
# bcc is unsigned less-than, so AL < 3 bails on 0/1/2 exactly as AL <= 2 did.
# EQUALITY, not an inequality. Two reasons.
#
# 1. `cmp AL,#3 ; bcc` turned out INVERTED in the emulator: states 0/1/2 ran the chain and
#    3/13 bailed, i.e. bcc here means ">=", not "<". I could flip to bcs -- but the carry
#    polarity comes from the SAME shared opcode table that hid probe131's bug, so trusting
#    it to be right in one direction and wrong in the other is exactly the mistake twice.
# 2. `bne` is unambiguous (not-equal is not-equal), and it is the second most attested
#    two-word form in the firmware: 187 uses.
#
# `cmp AL,#3 ; bne OUT` bails unless sinkState == 3 deviceConnected. At power-on the state
# is 0/1/2, all != 3, so the cave stays inert at boot -- which is what probe131 proved
# matters. If the real state during the press is 13 deviceA2DPStreaming rather than 3, this
# bails and we get SILENCE, not a crash: a safe failure that tells us the state, and the
# gate can be widened next build.
W(0x0384)                       # cmp AL,#3
BR(0xF0, "OUT")                 # bne -> bail unless deviceConnected

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
# NWORDS = 126 as -23.0 dBFS, 0.00% clipped, step index held at 36 (tools/noisespec.py).
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

for iteration in range(200):   # 24 was not enough once the gate added two branches
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
    if iteration > 190:
        # Diagnose the oscillation instead of just failing: print the items whose encoded
        # size is still flipping, with the displacement that is driving it.
        print('iter %d still unstable:' % iteration)
        for i, item in enumerate(prog):
            if item[0] not in ("bsr", "br"): continue
            lbl = item[2] if item[0] == "br" else item[1]
            tgt = label_addr[lbl] if isinstance(lbl, str) else lbl
            print('   item %3d %-4s -> %-10s a=0x%05x tgt=0x%05x v=%+6d size=%s'
                  % (i, item[0], lbl if isinstance(lbl, str) else hex(lbl),
                     addrs[i], tgt, tgt - addrs[i],
                     (bsr_size if item[0] == 'bsr' else br_size).get(i)))
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
