#!/usr/bin/env python3
"""probe135: probe134 with the buffer raised to the historically proven size.

ONE variable: NWORDS 126 -> 639, so malloc(128) -> malloc(641) and the region length
0x7e -> 0x27f. The rate stays at 2000 Hz, the generator's four block templates are
unchanged, and the chain is otherwise byte-for-byte probe134 -- which the owner reported
as "louder noise" on 2026-10-05.

Duration: 639 bytes = 1278 samples at 2000 Hz = 639 ms, 5.07x probe134's 126 ms.

*** DO NOT FLASH AS BUILT. The malloc size is unsupported. ***

I wrote here that "malloc(641) is proven -- probes 105/106/113 ran it". That was FALSE and
I did not check it before writing it down. What the record actually says:

  - probes 105 and 106 WERE flashed, but both used NWORDS = 126 / malloc(128)
    (assemble_probe105.py:242, assemble_probe106.py:271).
  - probes 111 and 113 are the NWORDS = 639 / malloc(641) ones, and the field log heads
    both sections "BUILT AND VERIFIED, NOT FLASHED" (docs/field-log.md:5676, :5750). The
    malloc(641) "verification" at :6023 is cavesim, not hardware.
  - assemble_probe105.py:89 -- malloc(128) was chosen "rather than probe103's 512, which
    returned 0". A 512-word request is KNOWN TO HAVE FAILED on this device.
  - probe128's confirmed-on-hardware list contains only "malloc(128) is granted".

So: largest confirmed grant 128 words, 512 known to fail, and 641 > 512. This image would
very probably get malloc -> 0, bail to the single leavel and play silence. That is SAFE --
it cannot crash on this path -- but it would waste one of the owner's presses, which are
the scarcest resource in this project.

Kept, not deleted, because the 639-word payload itself is measured and sound (RMS -9.2
dBFS, 90.7% above 150 Hz, 0.00% clipped, final index exactly 80, predictor excursion only
-14246..+17656 against a +/-32768 rail, over 211 blocks). The zero-net property scales;
only the heap request is unsupported. Reuse this file once a grant above 128 is proven.

Was originally derived from probe134 by copying its assembler, which hardcodes its own
output paths; all three were retargeted to probe135 so the image currently ON THE DEVICE
cannot be overwritten. probe129_words.json was silently destroyed twice this way.


ONE variable from probe129, which has played audio **twice** on this unit. No gate: the
sinkState gate is proven useless at `0xAE0` (`fn_0d500` has exactly one `leavel`, no `rts`,
and ends `ld AL,#2 ; bsr fn_0d441` -> `st AL,@0x59e`, so the state is unconditionally 2
there and any gate on {3,13} always bails). Keeping it would guarantee silence.

## The generator: zero-net blocks, no predictor tracking at all

Five cheap schemes were measured and rejected because **randomness in a pure accumulator
drifts, and correcting the drift needs the accumulated value** -- which is why exact
tracking kept winning at 122 words. That conclusion was right about those five schemes and
wrong as a general claim.

The escape is to make the drift **structurally impossible** rather than corrected. In a
3-word block with magnitudes (3,0,4,3,0,4) the step index cycles 80 -> 79 -> 78 -> 80, so
the six diffs are six fixed constants with the second three equal to the first three. If
the signs of nibbles 3-5 are the **negation** of nibbles 0-2, the block's net displacement
is **exactly zero for any random bits**: the predictor returns to its start every six
samples. No drift, no tracker, and no clipping for any seed, by construction.

Three free bits per block give eight patterns; restricting to the four with small block
means is what lifts the >150 Hz fraction from ~60% to ~90%:

    x = lfsr(x) ; r = x & 0x88 ; t = r >> 4
    q[0] = 0x30 ^ r                     signs (s0, s1)
    q[1] = 0xCB ^ (r & 0x80) ^ t        signs (~s0, ~s0)
    q[2] = 0x84 ^ (r << 4) ^ t          signs (~s1, s0)

Priming is `80 FF FF FF FF F7`, which lands the index on exactly 80 with the predictor at
+1705. The old five-`0xF7` priming left it at **+8945**, wasting 7.2k of headroom for
nothing.

## Measured, not estimated

    design                              words  frame   in-band dBFS   >150Hz   clip
    free walk (probe129, shipped)          56   -2     -41.9           0.2%    0.00%
    exact tracker (did not fit)           122   -8     -14.1..-13.6   84-94%   0.00%
    THIS: zero-net blocks                  84   -3     -10.0..-9.6    88-96%   0.00%

**+4 dB louder in-band than the tracker, 38 words smaller, 5 frame slots shallower**, and
~32 dB above what probe129 actually put in the audible band. Eight seeds, 0.00% clipping on
every one -- the seed fragility that made probe129's level luck is gone, because the bound
is structural.

Fit: 84 + the unstripped 84-word chain = **168 of the 182 cap**, so the six dead failure-id
loads do not even need removing yet.

## Nibble order is now SETTLED: high nibble first

This had been an open unknown the project worked around. A known waveform was encoded with
the ADK's own `voice_prompt_tool.exe` and decoded both ways: RMS error **1217 high-first vs
10606 low-first** on an 8746-RMS input. Prompts from that tool play through
`TransformAdpcmDecode` on CSR firmware, so the firmware's decoder must agree with it.

Related correction: the tracker's claimed "order-agnostic at K=1200" was **seed luck** --
low-first clips up to 1.98% across seeds, 0.00% only for `0xACE1`. This design is not
order-agnostic either (low-first up to 1.59%), which is exactly why the measurement above
mattered.

## Still a loudness diagnostic, not brown noise

Roughly a 333 Hz-centred buzz-noise, tonality 7.6-11.2 dB peak-to-mean above 150 Hz against
the tracker's 6.6-10.3 and white noise's ~6.5 -- the same category as the tracker, slightly
more tonal. Shaping toward brown comes after loudness is demonstrated.

**Play music, PAUSE it, then LONG-PRESS the BLUETOOTH button.**

    a clearly AUDIBLE ~1/8 second burst, much louder than before -> loudness solved; next
                                                                    is sustain, then shaping
    quiet like probe129  -> the in-band model does not transfer to this driver, and the
                            whole >150 Hz premise needs rethinking
    silence              -> the chain broke; probe129 proved it works, so suspect the
                            generator
    crash                -> stop; the frame is shallower than probe129's total, so this
                            would be unexplained
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

NWORDS = 639            # *** UNPROVEN SIZE -- SEE THE WARNING IN THE DOCSTRING ***
                        # malloc(641) has NEVER been granted on this hardware. The largest
                        # CONFIRMED grant is 128 words; malloc(512) RETURNED 0 on probe103.
RATE   = 2000           # Hz. UNCHANGED from probe134, so duration is the only variable:
                        # 639 bytes = 1278 samples = 639 ms here, 5.07x probe134's 126 ms.
                        # (639 words at 8 kHz was only 160 ms, which is why the rate stays
                        # at 2000 -- the low rate is what buys duration from a small buffer.)
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
# NWORDS is defined ONCE, near the top, as 639. probe125 inherited a SECOND `NWORDS = 639`
# assignment at this point which executed later and silently restored malloc(641) -- the
# exact bug probe125 existed to fix. Verified again for probe128 by grepping the generated
# file for every NWORDS assignment before building.
# PRIME is read out of the C rather than restated here, so this assert validates what was
# actually compiled. probe128's version hardcoded 9 and would have kept passing after the
# generator changed -- a check that cannot fail is worse than no check.
# Cross-check the C against what this assembler assumes, reading the real file rather
# than restating constants. The generator changed shape: there is no PRIME any more (the
# priming is six literal bytes), and the structure is 3-word zero-net blocks, so the
# requirement is that the payload after priming divides into whole blocks.
_c = io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          '..', 'noiseprobe', 'noise.c'), encoding='utf-8').read()
_cn = int(re.search(r'#define\s+NWORDS\s+(\d+)', _c).group(1))
assert _cn == NWORDS, 'noise.c has NWORDS=%d but this assembler expects %d' % (_cn, NWORDS)
assert 'q[0] = (uint16)(0x30 ^ r)' in _c,     'noise.c is not the zero-net block generator this probe expects'
assert (NWORDS - 6) % 3 == 0, 'six priming words then whole 3-word blocks'
print('generator: zero-net blocks, NWORDS=%d, %d blocks (read from noise.c)'
      % (_cn, (_cn - 6) // 3))
# buf[0] LFSR state, buf[1] live SOURCE, samples from buf+2. The live transform is NOT
# stored: the teardown finds it with TransformFromSink, which is the whole reason to use
# that trap (a cached handle goes stale, as probe105's did). Keeping the SOURCE is what
# lets SourceClose run -- the call whose absence leaked a stream object every 28 ms in
# probes 105 and 106.
SPEAK = 0xDF7F          # the prompt engine: id in AL, nothing in X, and it returns
# No TONE_RATE and no 0x1072: NowSpeakTTS registers no 0x10xx handler at all
# (docs/kalimba-disasm.md), so the rate message would be a no-op on the prompt DSP.

# NOTE: the six failure-id loads were removed to pay for the larger generator. They were
# dead weight -- the prompt call at 0xae4..0xae6 is nopped so no id is ever spoken, and
# nothing downstream reads AL (the stock return point 0x00ae3 is `ld AL,#0x35`). Removing
# them is safe because `ld` preserves the flags from `cmp`: proven on hardware by probes
# 60/64/65/122, each of which spoke exactly the id of the bail it reached, which is only
# possible if Z survived the intervening `ld`. probe77 runs the same way, with no ids.

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
W(0x0084); BR(0xF4, "OUT")        # 0x08 FALSE = no .kap loaded

# ---- 2. take Bose's own tone port (proven: probe65, probe74, probe122)
ca.call1(W, BSR, ca.STUB['StreamKalimbaSink'], al=('imm', 3))
W(0x0227)                       # st AL,@(2,Y)  ksink
W(0x0084); BR(0xF4, "OUT")        # 0x12 no sink

# ---- 3. NWORDS payload bytes plus two state words. 641 total.
ca.call1(W, BSR, ca.STUB['malloc'], al=('imm', NWORDS + 2))
W(0x0327)                       # st AL,@(3,Y)  buf
W(0x0084); BR(0xF4, "OUT")        # 0x06 pool exhausted

# ---- 4. zero the state words and derive the payload pointer.
# malloc'd memory is not guaranteed zero and buf[0] == 0 is nib_fill's first-call
# sentinel, so the caller zeroes it rather than seeding a constant.
W(0x031B)                       # ld X,@(3,Y)
W(0x0014); W(0x0026); W(0x0126) # buf[0] = 0 (sentinel), buf[1] = 0
W(0x0317); W(0x0234); W(0x0427) # samples = buf + 2 -> slot 4

# ---- 5. generate the nibbles. kalsim-verified and bit-exact in probe81; measured at
# probe134 measured NWORDS = 126 at -9.3 dBFS, 0.00% clipped, index held at exactly 80,
# and the owner reported "louder noise" on 2026-10-05. Raising NWORDS does not change the
# spectrum: every 3-word block is drawn from the same four templates and is individually
# zero-net, so 211 blocks behave exactly as 40 did. Only the duration changes.
ca.call2(W, BSR, "NIBS", al=('slot', 4), ah=('slot', 3))

# ---- 6. a Source over the generated bytes. One byte per 16-bit word, low 8 bits,
# so NWORDS words carry NWORDS bytes = 2*NWORDS ADPCM samples.
ca.call2(W, BSR, ca.STUB['StreamRegionSource'],
         al=('slot', 4), ah=('imm', NWORDS))
W(0x0527)                       # st AL,@(5,Y)  src
W(0x0084); BR(0xF4, "OUT")        # 0x01 no source

# ---- 7. Bose's own recipe, proven to carry audio in probe104.
ca.call2(W, BSR, ca.STUB['TransformAdpcmDecode'], al=('slot', 5), ah=('slot', 2))
W(0x0427)                       # st AL,@(4,Y)  t   (samples is finished with)
W(0x0084); BR(0xF4, "CLOSESRC")   # 0x0A no transform

# ---- 8. go.
ca.call1(W, BSR, ca.STUB['TransformStart'], al=('slot', 4))
W(0x0084); BR(0xF4, "CLOSESRC")   # 0x16 would not start
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
        # Probe for the next band LAZILY, and treat "there is no next band" as needing no
        # connector reservation. Computing it eagerly made the LAST band throw even when
        # the item fitted and no handoff was required -- which rejected layouts that were
        # perfectly valid (probe113 needs 231 of the 262 writable words and was refused).
        try:
            nb_probe = next_blind(band_end)
            cs = 1 if -128 <= nb_probe - addr <= 127 else 2
        except AssertionError:
            nb_probe, cs = None, 0
        # Writable words in this band are [band_start, band_end). The item occupies
        # [addr, addr+sz); if it falls through, a connector occupies [addr+sz, addr+sz+cs).
        # So the requirement is exactly `addr + sz + cs <= band_end` for a falling-through
        # item and `addr + sz <= band_end` for a terminating one.
        #
        # The old test was `addr + (sz+1) > band_end - cs`, which reserved a spare word AND
        # the connector -- double-counting -- and also reserved a connector after `rts`,
        # `leavel` and `bra`, which never fall through. Both errors are conservative, so no
        # previously built probe was ever laid out unsafely; they only stranded words. The
        # log showed exactly "1 word left unused" at each of 14 band handoffs, and probe134
        # (162 raw words) was refused from a 197-word cave because of it.
        #
        # Safe to tighten: line 533's `assert not [a for a in out if not blind(a) or not
        # in_run(a)]` re-checks EVERY emitted word against the blind map independently of
        # this arithmetic, and caveguard re-checks the window against Bose's firmware.
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
