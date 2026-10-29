#!/usr/bin/env python3
"""probe155: THE NARROW FILE -- probe154 was one trap from playing, and the header
said exactly why it stopped.

## WHAT probe154 PROVED, AND WHAT IT TRIPPED OVER

Pressed twice, both times id 0x26 "ended". The chain got this far:

    KalimbaSendMessage(0x1072, 2000)   PASSED
    ksink = StreamKalimbaSink(3)       PASSED
    idx = FileFind(1, 0xbd75, 27)      **PASSED -- nonzero**
    src = StreamFileSource(idx)        **RETURNED 0**

So `FileFind` works. The three-argument form is right, the const-pool pointer is
right, and the two bugs probe154 fixed in probe141's machinery (the prefixed
pointer fold, and a carried string split across blind bands) were real and are
now behind us.

`StreamFileSource` is documented in one line, `stream.h:300`:

    @return 0 if index is #FILE_NONE, or does not correspond to a NARROW file.

and `file_if.h` distinguishes `FILE_TYPE_NARROW_FILE` (8-bit wide) from
`FILE_TYPE_WIDE_FILE` (16-bit wide). probe154 opened
`sbc_decoder/sbc_decoder.kap` -- Kalimba code, which is a WIDE file. **It was
never streamable.** Not a directory, not a lock, not a path problem: the wrong
file width.

## THE FILESYSTEM, DUMPED, WHICH SETTLES BOTH QUESTIONS AT ONCE

`tools/csr/dumpfs.py` on the stock image prints the flag byte per file:

    NowSpeakTTS/data_us              219,528 B   flags=0x00   entropy 7.32
    NowSpeakTTS/NowSpeakTTS.kap       31,076 B   flags=0x40
    sbc_decoder/sbc_decoder.kap       69,994 B   flags=0x40   <- probe154's file
    soundClearNb/soundClearNb.kap     56,186 B   flags=0x40
    soundClearWb/soundClearWb.kap     65,242 B   flags=0x40
    tts/rphrases_us                   10,486 B   flags=0x00   entropy 6.08
    vm.app                           522,026 B   flags=0x40

Flag 0x40 is "code" (probe144 established that: it matches every `.kap`), and
every 0x40 file is exactly the kind `StreamFileSource` refuses. **The only two
narrow files in the image are `NowSpeakTTS/data_us` and `tts/rphrases_us`,** and
the big one is 219,528 bytes with an entropy of 7.32 -- very nearly random,
which is the best thing that could be said about a noise source.

**A CORRECTION TO probe154's OWN NOTES.** probe154 claimed that because
`"NowSpeakTTS/data_us"` is absent from vm.app's const pool, probe141's path
"was never grounded". That was wrong, and the dump above is why: the path is
EXACTLY right. The firmware simply builds that name at runtime instead of
storing it as a literal. probe141's `FileFind` failed on the pointer fold and the
split string, not on the path. The two bugs stand; the slur on the path does not.

## THE ONE CHANGE: A TWO-LEVEL LOOKUP, AND A NARROW FILE

`file.h:18-28` says `FileFind(start, name, length)` finds "a named file or
directory, relative to the starting directory", and `start` "is commonly
FILE_ROOT". It accepts a path, but probe155 cannot hand it one, for a reason
that is now measured rather than guessed:

**the cave's blind bands are 14, 9 and 3 words wide.** A carried
`"NowSpeakTTS/data_us"` needs 20 words and therefore CANNOT fit in any single
band -- it would be split exactly as probe154's 28-word string was. So the path
is walked in two steps, with two short strings that each fit:

    dir  = FileFind(FILE_ROOT, "NowSpeakTTS", 11)    12 words with its NUL
    file = FileFind(dir,       "data_us",      7)     8 words with its NUL
    src  = StreamFileSource(file)                     a NARROW file: streamable
    TransformAdpcmDecode(src, ksink) ; TransformStart(t)

Each string is emitted as ONE multi-word item so the layout machinery must place
it whole, and the assembler ASSERTS afterwards that every character landed at
consecutive addresses. That assertion is the thing probe141 never had.

At the 2000 Hz tone rate, 219,528 bytes read as 4-bit ADPCM is ~439,000 samples:
**about three and a half minutes from a single allocation**, against the refill
loop's six seconds. No timer, no teardown, no `malloc`, no refill -- nothing in
this probe repeats, so nothing in it can leak.

`FileType` would have made a nice extra check and is deliberately NOT called: it
is absent from this project's verified stub table, the dump above already answers
the width question offline, and a probe about to play audio is no place to
introduce a trap number nobody has confirmed.

## WHAT IT WILL SOUND LIKE

`data_us` is the prompt corpus, and it is raw 16-bit PCM rather than ADPCM. Read
as 4-bit ADPCM nibbles at entropy 7.32, it should come out as noise rather than
speech. It will not be BROWN noise -- there is no spectral shaping here, and none
is intended yet.

**Judge this press by its DURATION, not its timbre.** If it runs for minutes,
sustain is solved architecturally and the remaining work is shaping.

## THE OUTCOME LATTICE

Four ids, from the call family -- no call is active during the press, so none of
them can be self-emitted, and their openings are deliberately unalike:

  SOUND, and it RUNS           SUCCESS. No success id on purpose: speaking loads
                               the prompt DSP and could tear the transform down.
                               The audio is the signal; the only number that
                               matters is HOW LONG. Power off to stop it.
  "conference call"    (0x22)  FileFind(FILE_ROOT, "NowSpeakTTS") returned
                               FILE_NONE -- the directory itself is not there.
  "call from unknown"  (0x1B)  the directory resolved but "data_us" inside it did
                               not. The two-level walk is wrong, or the name is.
  "switching call"     (0x24)  StreamFileSource returned 0 on a file the dump
                               says is NARROW. That would contradict
                               stream.h:300 and would be a genuine surprise.
  "call with"          (0x25)  TransformAdpcmDecode or TransformStart refused.
                               Note that probe154 never reached these, so this
                               would be their first real test on a file source.
  silence, no speech           the 0x1072 gate bailed (no DSP up), or the chain
                               completed and produced nothing audible. Re-press
                               with the laptop connected and music paused.

## What is NOT changed

The hook, the redirects (byte-identical to the family), the 0x1072 gate at
2000 Hz, `StreamKalimbaSink(3)`, the boot-safe silent bail, the corrected
prefixed-pointer fold, and the one-shot shape: one source, one transform, nothing
that allocates or repeats.

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

PERIOD = 32
FIRST = 11
PER_PERIOD = 14
PERIODS = 1180
INNER = 59                              # 20 x 59 = 1180
OUTER = 20
CHUNK_BYTES = PER_PERIOD * 2            # 28

w = xapvm.load_words("firmware/bose/extracted/internal_fs/vm.app")
code = w[0x18:]
# ---- two SHORT carried strings, each emitted as ONE item so the layout cannot
# split it, and each asserted contiguous after layout. The cave's blind bands
# measure 14, 9 and 3 words, so "NowSpeakTTS/data_us" (20 words with its NUL)
# CANNOT fit in one band -- hence the two-level walk. file.h:18-28 supports it:
# FileFind takes the directory to start from, and FILE_ROOT is 1.
DIRNAME, FILENAME = "NowSpeakTTS", "data_us"

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
# ------------------------------------------------- the ONE-SHOT, NARROW FILE
# One source over a 219,528-byte NARROW file, one transform, and the port pulls
# until the data runs out. No timer, no teardown, no malloc, no refill.
W(0xF80B)                       # enterl -8 (slots 0..5 usable, 6/7 = link)
BSR(BACK)                       # the stock back-call FIRST, probe77's order

# ---- the gate, unchanged: FALSE means no DSP, i.e. the power-on auto-fire.
W(0x0014)                       # ld AL,#0
W(0x0027); W(0x0127); W(0x0227) # b = c = d = 0        slots 0..2
W(*ca.imm_words(RATE, 0x10))    # ld AH,#2000
W(*ca.imm_words(0x1072, 0x14))  # ld AL,#0x1072
BSR(KALMSG)
W(0x0084); BR(0xF4, "OUT")      # SILENT bail, no id at all

# ---- ksink = StreamKalimbaSink(3)
ca.call1(W, BSR, KSINK, al=('imm', 3))
W(0x0227)                       # st AL,@(2,Y)  ksink
W(0x0084); BR(0xF4, "NOSINK")

# ---- dir = FileFind(FILE_ROOT, "NowSpeakTTS", 11).  Length into @(0,Y) FIRST:
# the ld AL that follows would otherwise clobber it (probe144's ordering).
W(*ca.imm_words(len(DIRNAME), 0x14))    # ld AL,#11
W(0x0027)                       # st AL,@(0,Y)  arg3 = length in words
W(0x0114)                       # ld AL,#1      arg1 = FILE_ROOT
LBL("SETAHDIR")
W(0x0000, 0x0010)               # ld AH,#<data addr of STRDIR>  (patched below)
BSR(FILEFIND)
W(0x0084); BR(0xF4, "NODIR")    # FILE_NONE -> no NowSpeakTTS directory
W(0x0327)                       # st AL,@(3,Y)  dir index

# ---- file = FileFind(dir, "data_us", 7)
W(*ca.imm_words(len(FILENAME), 0x14))   # ld AL,#7
W(0x0027)                       # st AL,@(0,Y)
W(0x0317)                       # ld AL,@(3,Y)  arg1 = the DIRECTORY index
LBL("SETAHFILE")
W(0x0000, 0x0010)               # ld AH,#<data addr of STRFILE> (patched below)
BSR(FILEFIND)
W(0x0084); BR(0xF4, "NOFILE")   # FILE_NONE -> no data_us inside it

# ---- src = StreamFileSource(file). AL already carries the index.
# stream.h:300 returns 0 for anything that is not a NARROW file; the dump says
# this one has flags 0x00, so it is narrow and this should now succeed.
BSR(FILESRC)
W(0x0084); BR(0xF4, "NOSRC")

# ---- t = TransformAdpcmDecode(src, ksink); TransformStart(t)
W(0x0213)                       # ld AH,@(2,Y)  ksink (AL still holds src)
BSR(ADPCM)
W(0x0084); BR(0xF4, "NOPLAY")
BSR(TSTART)                     # AL carries the transform
W(0x0084); BR(0xF4, "NOPLAY")

# ---- SUCCESS. Silent on purpose: a prompt here loads the prompt DSP and could
# tear the transform down. The audio is the signal, and DURATION is the result.
BR(0xE0, "OUT")

LBL("NOPLAY")
W(0x2514)                       # ld AL,#0x25 "call with"
BR(0xE0, "SAY")
LBL("NOSRC")
W(0x2414)                       # ld AL,#0x24 "switching call"
BR(0xE0, "SAY")
LBL("NOFILE")
W(0x1B14)                       # ld AL,#0x1B "call from unknown"
BR(0xE0, "SAY")
LBL("NODIR")
W(0x2214)                       # ld AL,#0x22 "conference call"
BR(0xE0, "SAY")
LBL("NOSINK")
W(0x1014)                       # ld AL,#0x10 "and" -- a fragment the stock
                                #   firmware never speaks alone
LBL("SAY")                      # ...and fall through into the shared speech
BSR(SPEAK)                      # probe99's direct idiom, hardware-proven
LBL("OUT")                      # the gate bail and SUCCESS both land here
W(0xF80F)                       # leavel -8

# ---- the two path strings, AFTER the final leavel so their char words are
# never executed. EACH IS ONE ITEM: the layout machinery places a multi-word
# item whole or moves it to the next band, which is what guarantees the
# contiguity FileFind needs. Asserted after layout as well.
LBL("STRDIR")
W(*([ord(c) for c in DIRNAME] + [0]))
LBL("STRFILE")
W(*([ord(c) for c in FILENAME] + [0]))

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

# ---- patch the two FileFind string pointers, and PROVE each string is
# contiguous. probe141 had neither: its pointer fold was wrong whenever the low
# byte was >= 0x80 (XAP folds sext8(prefix)*256 + sext8(operand), so such a low
# byte is NEGATIVE and borrows from the high byte), and a carried string got
# split across blind bands with no check that it had not.
CONST_ORIGIN = 236514
def _str_ptr(label, text, setah):
    base = label_addr[label]
    words = [ord(c) for c in text] + [0]
    for k, expect in enumerate(words):
        got = out.get(base + k)
        assert got == expect, (
            'string %r is NOT contiguous: word %d at %#x is %r, expected %r -- '
            'the layout split it across blind bands'
            % (text, k, base + k, got, expect))
    data = (CONST_BASE + (base - CONST_ORIGIN)) & 0xFFFF
    assert 0x7400 <= data <= 0xD39A, (text, hex(data))
    lo8 = data & 0xFF
    hi8 = ((data >> 8) + (1 if lo8 >= 0x80 else 0)) & 0xFF
    sx = lambda b: b - 256 if b >= 0x80 else b
    assert (sx(hi8) * 256 + sx(lo8)) & 0xFFFF == data, (
        'prefixed ld AH does not fold back for %r: hi=%02x lo=%02x -> %#06x, '
        'want %#06x' % (text, hi8, lo8, (sx(hi8)*256 + sx(lo8)) & 0xFFFF, data))
    assert 1 <= hi8 <= 0xFF, hex(data)
    a = label_addr[setah]
    out[a] = (hi8 << 8) | 0x00
    out[a + 1] = (lo8 << 8) | 0x10
    print('  %-12r %2d words, contiguous at code %#x -> data %#06x '
          '(ld AH %04x %04x)' % (text, len(words), base, data, out[a], out[a+1]))

print('FileFind strings:')
_str_ptr('STRDIR', DIRNAME, 'SETAHDIR')
_str_ptr('STRFILE', FILENAME, 'SETAHFILE')

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
