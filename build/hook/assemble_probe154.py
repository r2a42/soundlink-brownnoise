#!/usr/bin/env python3
"""probe154: THE ONE-SHOT LONG PLAY -- stop refilling. One source, one transform,
and let the port pull for minutes instead of 110 milliseconds.

## WHAT SIX PRESSES ESTABLISHED, AND WHAT THEY ADD UP TO

  probe145/146  the refill loop plays real audio, and dies at a FIXED tick count
  probe149      0x3B silent -> StreamRegionSource NEVER fails
  probe150      0x3D, 0x39 silent -> TransformAdpcmDecode RETURNS 0: the
                transform cannot be CREATED, reproducibly, at ~55 ticks
  probe151      explicit TransformStop + TransformDisconnect on the stored
                handle: ~55 ticks, UNCHANGED. The documented destroyer
                reclaims nothing.
  probe153      StreamDisconnect(src, ksink) breaking BOTH sides first, then
                SourceClose(src) -> **FALSE, on the first tick.**

And `source.h:124-126` says why, in as many words:

    Some sources, such as RFCOMM connections or the USB hardware, have a
    lifetime defined by other means, and cannot be closed using this call.

A region source is one of those: `stream.h` has it existing "only while the data
is being read". **So the VM cannot explicitly reclaim EITHER object in this
chain** -- not the transform (probe151) and not the source (probe153). Every tick
allocates two things that only the firmware can take back, which is why the
death is at a fixed count and why five presses of teardown repair moved it by
nothing.

(It also undermines the one datum that drove four of those probes. probe145's
"~9 s" against probe146's "~6 s" was read as SourceClose helping. The close
never worked, so that difference was most likely ear-timing noise.)

## THE THING NOBODY QUESTIONED

126 bytes, refilled every 110 ms, is an **arbitrary choice**. It is also the only
reason the allocation count matters: at 9 allocations a second, any fixed budget
is gone in seconds.

Bose does not do that. Its own voice prompts run for SECONDS from ONE source and
ONE transform -- `fn_12e6f` does `FileFind` -> `StreamFileSource` and hands the
result straight to `TransformAdpcmDecode`. The transform is pull-driven by the
port's own consumption, so a large source feeds it for as long as the data lasts.

So: make the source big and the refill disappear.

    FileFind(1, "sbc_decoder/sbc_decoder.kap", 27)   69,994 bytes
    StreamFileSource(idx)                a source over ALL of it
    TransformAdpcmDecode(src, ksink)     ONE transform
    TransformStart(t)                    and nothing else, ever

At the 2000 Hz tone rate, 69,994 bytes read as 4-bit ADPCM is ~140,000 samples
-- **about seventy seconds from a single allocation.** Against six, that is an
eleven-fold change, and it needs no timer, no teardown, no `malloc` and no
refill. Nothing in this probe can leak because nothing in it repeats.

THE FILE CHOICE IS NOT ARBITRARY. The obvious candidate was `data_us`
(219,528 bytes, three times longer), and it was rejected on two findings:
`"NowSpeakTTS/data_us"` **does not appear in vm.app's const pool at all**, and
neither does `"data_us"` -- so probe141's path string was never grounded, and
probe141 is precisely the probe whose press outcome was never heard, so its
`FileFind` has never been shown to succeed. `"sbc_decoder/sbc_decoder.kap"` IS
in the pool, at code word 0x3e56f: the firmware itself names this file, so the
path is real. Seventy seconds is more than enough to settle the question.

`FileFind` also takes THREE arguments -- index, pointer, and length in words
(probe144's form). probe141 passed only two. That is corrected here.

## TWO BUGS IN probe141's FileFind MACHINERY, FOUND BUILDING THIS PROBE

probe154 started as probe141's file-source code with a new body, and the
simulator caught two defects in the inherited machinery. Both would have made
`FileFind` read the wrong memory, and probe141 is exactly the probe whose press
outcome was never heard -- so neither was ever visible.

  1. **THE POINTER FOLD.** probe141 patched its `ld AH,#<string address>` by
     splitting the address into (high byte, low byte) and asserting that a high
     byte >= 0x80 "wraps negatively through the signed fold and still yields the
     16-bit address". That holds only when the LOW byte is below 0x80. XAP folds
     a prefixed immediate as `sext8(prefix)*256 + sext8(operand)`, so a low byte
     >= 0x80 is NEGATIVE and borrows one from the high byte. For the address this
     probe first computed, 0xBAE6, probe141's arithmetic emits ba/e6, which folds
     to **0xB9E6 -- a pointer 0x100 too low.** Fixed, with a round-trip assertion
     so it cannot recur silently.
  2. **THE SPLIT STRING.** A carried path string is laid out by the same band
     packer as the code, and the cave's blind bands are only ~12-29 words wide
     with connector branches inserted at the seams. The 28-word string for this
     path was split: chars landed at 0x3e2c8 and 0x3e2c9, then the layout jumped
     onward. `FileFind` would have read garbage. probe141 carried a 20-word
     string through the same machinery, so it was very likely split too.

Both are retired at once by not carrying a string at all. The firmware already
has this exact path in its const pool, guaranteed contiguous, and the assembler
now FINDS it there at build time (one char per 16-bit word), which simultaneously
proves the path is real and yields the pointer: **code 0x3e557 -> data 0xbd75**.
That is also why `data_us` could not simply be substituted -- it has no pool
copy, so it would need a carried string and reintroduce defect 2.

## WHAT IT WILL SOUND LIKE, AND WHY THAT IS FINE

Noise, almost certainly -- and that is the happy case. `sbc_decoder.kap` is
Kalimba machine code, and reading machine code as 4-bit ADPCM is close to
reading random nibbles, which is what noise IS. It will not be *brown* noise;
there is no spectral shaping here. But a wrong decode is still noise, and noise
is the goal.

Worth recording for the next probe: `data_us` turns out to be **raw 16-bit PCM,
not ADPCM** (field log, 2026-10-06), so nothing in this project's audio chain was
ever feeding the decoder the format it expects. That makes "wrong decode" the
normal case rather than an accident.

**The measurement here is DURATION, not timbre.** If it runs for a minute,
sustain is solved architecturally, and what remains -- getting *shaped* noise
into a file-sized region -- is a quality problem with its own channel (`fsedit`
rewrites 29 of every 64 bytes of a file).

So: do not judge this press by how it sounds. Time it.

## WHY NOT THE OTHER ROUTES

The per-tick refill is capped by two objects the VM cannot free -- measured, not
inferred. The direct port write is parked: probe152 found `SinkSlack` reports no
usable room, and Bose never claims, maps or flushes an audio sink anywhere in
this firmware. The partition route died at the mount. This is the one remaining
direction that the firmware's own code demonstrates works.

## THE OUTCOME LATTICE

Five failure ids, chosen for maximum contrast -- three single words, one two-word
phrase, one long sentence. None is in the EMPTY set, none is 0x00/0x09/0x35, none
is in use by another probe, and none can be emitted by the speaker itself in this
state:

  (no sound, no speech)  the 0x1072 gate bailed: no DSP was up.
  "and"          (0x10)  StreamKalimbaSink(3) returned 0. A bare "and" is a
                         concatenation fragment the stock firmware never speaks
                         alone, which makes it an ideal diagnostic.
  "english"      (0x16)  FileFind found no "NowSpeakTTS/data_us".
  "ended"        (0x26)  StreamFileSource returned 0 -- the file exists but will
                         not open as a source.
  "call ignored" (0x1E)  TransformAdpcmDecode returned 0 at the very first
                         attempt, with nothing allocated beforehand. That would
                         mean creation refusal is NOT about accumulation at all.
  "to select a different language press a volume button" (0x18)
                         TransformStart returned FALSE.
  SOUND            ---   SUCCESS. There is no success id: the audio IS the
                         signal, and the only number that matters is how long it
                         lasts. Power off to stop it.

## What is NOT changed

The hook, the redirects (byte-identical to the family), the 0x1072 gate and its
2000 Hz rate, `StreamKalimbaSink(3)`, the boot-safe silent bail, and the
const-window discipline. The `FileFind` + `StreamFileSource` idiom and the
after-the-leavel path string are probe141's, which found and opened this exact
file on hardware.

NO flash writes. NO malloc. NO timer. NO teardown. One source, one transform.

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
REDIRECT_EDITS = [("0x6fff1", "0x04"), ("0x6fff3", "0xd7"), ("0x6fff5", "0x3b"),
                  ("0x6fff6", "0xe0"), ("0x6fff7", "0x01"),
                  ("0x6fff8", "0x00"), ("0x6fff9", "0x00"),
                  ("0x6fffa", "0x00"), ("0x6fffb", "0x00"),
                  ("0x6fffc", "0x00"), ("0x6fffd", "0x00")]
AREA0 = 0x6EA30
CONST_BASE = 0x7400                     # data addr of code word 236514 (0x39BE2)

BACK = 0xE06D
SPEAK = 0xDF7F
FILEFIND = ca.STUB['FileFind']
FILESRC = ca.STUB['StreamFileSource']
SOURCEMAP = ca.STUB['SourceMap']
SINKSLACK = ca.STUB['SinkSlack']
KALMSG   = ca.STUB['KalimbaSendMessage']
KSINK    = ca.STUB['StreamKalimbaSink']
ADPCM    = ca.STUB['TransformAdpcmDecode']
TSTART   = ca.STUB['TransformStart']
RATE     = 2000          # the tone rate every audio probe has used
OVERSINK = ca.STUB['StreamPartitionOverwriteSink']
SETDIGEST = ca.STUB['PartitionSetMessageDigest']
SINKCLOSE = ca.STUB['SinkClose']
SINKFLUSH = ca.STUB['SinkFlush']
MEMMOVE = ca.STUB['memmove']
FN12E1A = 0x12E1A                       # Bose's SinkMap+SinkClaim helper (stock)
MEMMOVE = ca.STUB['memmove']

PATH = "sbc_decoder/sbc_decoder.kap"   # a REAL firmware literal:
                                       #   present in vm.app's const
                                       #   pool at code 0x3e56f, which
                                       #   "NowSpeakTTS/data_us" is NOT.
                                       #   69,994 bytes.
PERIOD = 32
FIRST = 11
PER_PERIOD = 14
PERIODS = 1180
INNER = 59                              # 20 x 59 = 1180
OUTER = 20
CHUNK_BYTES = PER_PERIOD * 2            # 28

w = xapvm.load_words("firmware/bose/extracted/internal_fs/vm.app")
code = w[0x18:]
# ---- the path lives in the FIRMWARE'S const pool: find it and address it ----
# One char per 16-bit word (docs/const-strings.md). Searching `code` for the
# sequence proves the path is real AND gives a contiguous pointer for free.
_pat = [ord(c) for c in PATH]
_hits = [i for i in range(len(code) - len(_pat))
         if code[i] == _pat[0] and list(code[i:i + len(_pat)]) == _pat]
assert _hits, 'the path %r is NOT in vm.app\'s const pool' % PATH
PATH_CODE = _hits[0]
CONST_ORIGIN = 236514                       # code word mapped to CONST_BASE
PATH_DATA = (CONST_BASE + (PATH_CODE - CONST_ORIGIN)) & 0xFFFF
assert 0x7400 <= PATH_DATA <= 0xD39A, (
    'pool string at code %#x maps to data %#x, outside the const window'
    % (PATH_CODE, PATH_DATA))
# XAP folds a prefixed immediate as sext8(prefix)*256 + sext8(operand), so a low
# byte >= 0x80 is NEGATIVE and borrows 1 from the high byte. probe141 ignored
# that and emitted a pointer 0x100 too low whenever it happened.
_lo = PATH_DATA & 0xFF
_hi = ((PATH_DATA >> 8) + (1 if _lo >= 0x80 else 0)) & 0xFF
_sx = lambda b: b - 256 if b >= 0x80 else b
assert (_sx(_hi) * 256 + _sx(_lo)) & 0xFFFF == PATH_DATA, (
    'prefixed ld AH does not fold back: hi=%02x lo=%02x -> %#06x, want %#06x'
    % (_hi, _lo, (_sx(_hi) * 256 + _sx(_lo)) & 0xFFFF, PATH_DATA))
assert 1 <= _hi <= 0xFF, hex(PATH_DATA)
_AH_WORDS = ((_hi << 8) | 0x00, (_lo << 8) | 0x10)
print('FileFind path %r: FIRMWARE pool copy at code %#x -> data %#06x '
      '(ld AH prefix %04x %04x), %d words, NO carried string'
      % (PATH, PATH_CODE, PATH_DATA, _AH_WORDS[0], _AH_WORDS[1], len(PATH)))

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
# ------------------------------------------------- the ONE-SHOT LONG PLAY
# No timer, no teardown, no malloc, no refill. One source over a 219,528-byte
# file, one transform, and the port pulls from it until the data runs out.
W(0xF80B)                       # enterl -8 (slots 0..5 usable, 6/7 = link)
BSR(BACK)                       # the stock back-call FIRST, probe77's order

# ---- the gate: KalimbaSendMessage(0x1072 SET_TONE_RATE, 2000, 0, 0, 0).
# The same gate every audio probe has used: FALSE means no DSP, which is the
# power-on auto-fire case, and it bails in silence.
W(0x0014)                       # ld AL,#0
W(0x0027); W(0x0127); W(0x0227) # b = c = d = 0        slots 0..2
W(*ca.imm_words(RATE, 0x10))    # ld AH,#2000
W(*ca.imm_words(0x1072, 0x14))  # ld AL,#0x1072
BSR(KALMSG)
W(0x0084); BR(0xF4, "OUT")      # FALSE -> no DSP -> SILENT bail, no id at all

# ---- ksink = StreamKalimbaSink(3)
ca.call1(W, BSR, KSINK, al=('imm', 3))
W(0x0227)                       # st AL,@(2,Y)  ksink
W(0x0084); BR(0xF4, "NOSINK")

# ---- FileFind(1, "NowSpeakTTS/data_us") -- fn_12e6f's exact convention, and
# probe141 ran this on hardware. The path string lives AFTER the final leavel;
# the 2-word prefixed `ld AH` below is patched post-layout with its data address.
W(*ca.imm_words(len(PATH), 0x14))   # ld AL,#27  the length in WORDS
W(0x0027)                       # st AL,@(0,Y)  arg3 FIRST: the ld AL below
                                #   would otherwise clobber it
W(0x0114)                       # ld AL,#1      arg1 = FILE_ROOT
W(*_AH_WORDS)                   # ld AH,#<POOL addr of the path> -- see PATH_DATA
BSR(FILEFIND)                   # the THREE-arg form, probe144's idiom.
                                #   probe141 called this with only AL and AH and
                                #   its outcome was never heard, so the 2-arg
                                #   form has never been shown to work.
W(0x0084); BR(0xF4, "NOFILE")   # 0 = FILE_NONE -> not found

# ---- src = StreamFileSource(idx): AL carries the index straight through, as
# fn_12e6f does. This is a source over ALL 219,528 bytes -- the whole point.
BSR(FILESRC)
W(0x0084); BR(0xF4, "NOSRC")

# ---- t = TransformAdpcmDecode(src, ksink): AL = src, AH = sink.
W(0x0213)                       # ld AH,@(2,Y)  ksink (AL still holds src)
BSR(ADPCM)
W(0x0084); BR(0xF4, "NOADPCM")  # 0 on the FIRST EVER attempt would mean the
                                #   creation refusal is not about accumulation

# ---- TransformStart(t): AL carries the transform.
BSR(TSTART)
W(0x0084); BR(0xF4, "NOSTART")

# ---- SUCCESS. No id: the audio is the signal and DURATION is the measurement.
BR(0xE0, "OUT")                 # fall out and let it play. Nothing repeats, so
                                #   nothing can leak.

LBL("NOSTART")
W(0x1814)                       # ld AL,#0x18 "to select a different language..."
BR(0xE0, "SAY")
LBL("NOADPCM")
W(0x1E14)                       # ld AL,#0x1E "call ignored"
BR(0xE0, "SAY")
LBL("NOSRC")
W(0x2614)                       # ld AL,#0x26 "ended"
BR(0xE0, "SAY")
LBL("NOFILE")
W(0x1614)                       # ld AL,#0x16 "english"
BR(0xE0, "SAY")
LBL("NOSINK")
W(0x1014)                       # ld AL,#0x10 "and" -- a fragment the stock
                                #   firmware never speaks alone
LBL("SAY")                      # ...and fall through into the shared speech
BSR(SPEAK)                      # probe99's direct idiom, hardware-proven
LBL("OUT")                      # the gate's silent bail and SUCCESS land here
W(0xF80F)                       # leavel -8

# NO carried path string. See PATH_DATA above: probe154 points FileFind at the
# firmware's OWN copy of this path in the const pool, which is guaranteed
# contiguous. A carried 28-word string is NOT: the layout packs the cave into
# blind bands of ~12-29 words and inserts connector branches at the seams, and
# it split this very string across a band (chars at 0x3e2c8, 0x3e2c9, then a
# jump) -- FileFind would have read garbage. probe141 carried a 20-word string
# through the same machinery, so its FileFind was very likely reading a split
# string too, on top of the pointer-fold bug fixed below.

# ---- layout (proven machinery, verbatim from probe137/139/140) ----
bsr_size, br_size = {}, {}
label_addr = {}
changes = []
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

for iteration in range(200):
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
            if bsr_size.get(i, 2) != want:
                changes.append((iteration, hex(a), 'bsr', want))
                bsr_size[i] = want; ok = False
        else:
            want = (1 if -128 <= tgt - a <= 127
                    else 2 if br2_encodable(tgt - (a + 1))
                    else 3)
            if br_size.get(i, 1) != want:
                changes.append((iteration, hex(a), 'br', want))
                br_size[i] = want; ok = False
    if ok: break
else:
    for c in changes[-12:]:
        print('  change:', c)
    raise SystemExit('no converge after %d iters: br sizes %s'
                     % (iteration, {hex(addrs[i]): sz for i, sz in br_size.items()
                                    if prog[i][0] == 'br'}))

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
# probe154 carries NO staged payload. probe141's 33,040 blind-window edits in
# data_us are inherited from this file's ancestor and are deliberately REMOVED:
# they are not wanted here, that scale of write at boot time is what caused the
# 2026-10-06 device-harm event, and this probe READS the filesystem rather than
# writing it. Only the cave words and the 11 redirect bytes are edited.
cmd = [sys.executable, "tools/fsedit.py", "--out", f"build/hook/{_PROBE}_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open(f"build/hook/{_PROBE}_cmd.txt", "w").write(" ".join(cmd) + "\n")

if "--build" in sys.argv:
    import subprocess
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes: {len(out)} cave words + "
          f"{len(REDIRECT_EDITS)} redirect bytes, NO staged payload) "
          f"-> {_PROBE}_cmd.txt")
