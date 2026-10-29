#!/usr/bin/env python3
"""probe115: CANCELLED 2026-10-02 -- DO NOT FLASH. Settled without a press.

**The device is configured for AUDIO_CHANNEL_A, not A_AND_B.** `PSKEY_USR40` in this
unit's own readback is `0000 0000 0023 0001 0000 ...`; the single live descriptor is at
index 2, and `fn_0b2c0` takes the channel from **bit 4**, which is clear. `fn_1f3c6` maps
that to `AUDIO_CHANNEL_A` (0), `fn_0b29a`/`fn_1f398` give `AUDIO_HARDWARE_CODEC` (3), and
`fn_0b2bb`/`fn_1f3b2` give `AUDIO_INSTANCE_0` (0).

That is character for character what probes 86, 88, 89 and 90 called, and they were
silent with every call returning success. **The channel was the last unexplained
parameter and it is now eliminated**, so this probe would have tested a configuration the
device does not use. Kept for the record; it must not take a button press.
See `docs/field-log.md` and `docs/codec-sink-inert.md`.

---- original rationale, now superseded ----

probe115: the one untried cell in the codec matrix -- AUDIO_CHANNEL_A_AND_B.

**Built, not flashed.** Tested with **NOTHING CONNECTED and no music** -- which is how
probes 86, 88, 89 and 90 were all tested (`docs/field-log.md:4218`, `:4254`, `:4422`).
The first draft of this probe said "laptop connected, music paused", copied from
probe77/104. That would have been a mistake: this probe's entire value is being a
ONE-VARIABLE change from probe90, so running it under different conditions would add a
second variable and void the comparison. It also needs no DSP, no prompt and no port 3,
so there is no structural reason for anything to be connected.

## Why this probe exists, and why the one it replaces was cancelled

`docs/codec-sink-inert.md` originally queued a probe to test whether probe86's
`StreamConnect` had been silently **refused** (`stream.h:111`). Reading this project's
own matrix (`docs/field-log.md:4425`) refutes that before a press is spent:

| probe | rate | gain | unmute | channel | result |
|---|---|---|---|---|---|
| 63 | yes | - | - | **2** | **crash** (region source) |
| 86 | - | - | - | 0 | silence |
| 88 | - | yes | yes | 0 | silence |
| 89 | yes | yes | yes | 0 | **"connected to"** -- every call returns success |
| 90 | yes | yes | yes | 0 | silence |

probe89 spoke an id reachable only after `StreamConnect` returned non-zero, so the
connect was **not** refused; and 88/89/90 set rate, gain and mute. Those four
explanations are all dead.

**What the matrix never varies is the channel.** Every silent probe passed
`AUDIO_CHANNEL_A = 0`. That was a deliberate choice, not an oversight: probe63 used
channel **2** and crashed, so probe86 moved to 0 and called the channel "the prime
suspect" (`assemble_probe86.py:28-34`). But probe63 also fed a **region source**, and
`docs/field-log.md:4365` already flagged the confound -- Bose's working DSP path uses
channel **2** with a *Kalimba* source, so channel 2 is not fatal in itself.

So **channel 2 with a ringtone source** is the single untried cell.

## And the firmware says channel 0 alone is wrong

`fn_1c475` (290 words) is the image's most complete VM-side codec open. Every one of
its three branches either opens A *and* B and **`SinkSynchronise`s them**, or opens a
single sink as `AUDIO_CHANNEL_B` (1) or `AUDIO_CHANNEL_A_AND_B` (2), or `Panic()`s.
`AUDIO_CHANNEL_A = 0` is never a standalone sink **on that path** -- only ever half of a
synchronised pair. It is NOT true of the firmware as a whole: `fn_1f371` + `fn_1f3c6`
open channel A standalone from a config table at `@0x6d0`, so the original and stronger
form of this argument is refuted (`docs/codec-sink-inert.md`). What survives is that the
channel is the only parameter probes 86-90 never varied, and that `A_AND_B` is the
documented mono configuration for a one-speaker device. `audio_if.h:86` calls `A_AND_B` *"obtaining the stereo CODEC in
mono-mode"*, which is exactly what a one-speaker SoundLink Micro wants.
See `docs/codec-sink-inert.md`.

## The probe: probe90, with 2 where it had 0

Byte-for-byte probe90's call chain -- same rate, same gain, same unmute, same 13-word
ringtone, same failure ids -- so a difference in outcome is attributable to the channel
and nothing else.

    sink = StreamAudioSink(CODEC=3, INSTANCE_0=0, AUDIO_CHANNEL_A_AND_B=2)   <-- was 0
    StreamDisconnect(0, sink)                   fn_1c751's own first act
    SinkConfigure(sink, STREAM_CODEC_OUTPUT_RATE  = 0x301, 8000)
    SinkConfigure(sink, STREAM_CODEC_OUTPUT_GAIN  = 0x303, 15)
    SinkConfigure(sink, STREAM_AUDIO_MUTE_ENABLE  = 0x700, 0)
    src  = StreamRingtoneSource(const notes)    proven, probe74/77/90
    StreamConnect(src, sink)

Two things differ from probe90 and both are forced:

1. **The hook.** probe90 sat at `0xAE0`, which `0x00ace` gates to `cmp AL,#0x4003`
   (EventUsrEnterPairing). This sits at `0x107be`, the **centre button**, ungated.
2. **Success speaks nothing, and does not replay the displaced send.** probe89 proved
   the chain succeeds on channel 0 and then *spoke* -- and the prompt engine loads a
   `.kap` that rewires the DAC, which is why probe90 deleted the prompt to get a clean
   listen. Here a success leaves the connection alone: no prompt, and event `0x4004`
   is swallowed so the stock voice-assistant handler cannot displace it either.
   Every failure path still speaks its id and still replays the send.

The ringtone is 7 semibreves at 60 crotchets/min. Under the **corrected** duration law
(`60000/(T*L)` ms, not the `240000/(T*L)` this project had wrong until probe77 was
re-read) that is **1 s per note, about 7 s total** -- not the 28 s probe90's own
comment claims. Short, but 220 Hz square at full volume is unmistakable.

**NOTHING CONNECTED, no music. Press the CENTRE button once.**

    a ~7 s tone      -> **the channel was the answer.** The codec sink is not inert; it
                        was being opened in a configuration the firmware never uses.
                        Direct-to-DAC is alive: swap the ringtone for StreamRegionSource
                        over generated noise and that is brown noise with no DSP at all.
    silence          -> the channel is eliminated too, and with rate, gain, mute and
                        refused-connect already dead the direct codec route is finished
                        on the evidence. The ADPCM-into-port-3 route (probe113) is the
                        only live one, and probe114 decides its shape.
    "lost"             -> StreamAudioSink refused channel 2.
    "disconnected"     -> SinkConfigure rate failed.
    "ready to connect" -> SinkConfigure gain failed.
    "connecting to"    -> SinkConfigure unmute failed.
    "connecting"       -> StreamRingtoneSource returned 0.
    "connection lost"  -> StreamConnect refused on channel 2.
    "english"          -> the hook fired but this button emits another event.
    a crash          -> channel 2 is fatal with a ringtone source too, which makes
                        probe63's crash about the channel after all. Recoverable.
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

# ---- the ringtone, from app/ringtone/ringtone_if.h and ringtone_notes.h ----
# Lifted VERBATIM from assemble_probe90.py so that the note array is not a second
# variable. Values were cross-checked there by running the ADK's own preprocessor
# over the macros (xap-local-xap-gcc -E), not by reading the header by eye.
SEQ_CONTROL = 0x8000
def TEMPO(t):   return SEQ_CONTROL | (1 << 12) | t      # crotchets/min
def VOLUME(v):  return SEQ_CONTROL | (2 << 12) | v      # 8-bit
def TIMBRE(t):  return SEQ_CONTROL | (3 << 12) | t      # 1 = square
def DECAY(d):   return SEQ_CONTROL | (4 << 12) | d      # /16 fixed point
END = SEQ_CONTROL | (0 << 12)
def NOTE(pitch, length):  return (pitch << 7) | length  # pitch = MIDI number
A4, REST = 57, 127                                      # A4 = 220 Hz
SEMIBREVE, CROTCHET = 1, 4                              # length is a DIVISOR

# 7 semibreves at 60 crotchets/min. probe90 called this 28 s using the 240000/(T*L)
# law this project had wrong; the corrected law is 60000/(T*L) ms, so a semibreve here
# is 1 s and the whole thing is about 7 s. Max volume, square wave, decay 0xFF (15.9)
# so each note holds its level instead of dying away. Untied, so every note restarts
# at full volume -- seven chances to be heard.
NOTES = ([TEMPO(60), DECAY(0xFF), VOLUME(0xFF), TIMBRE(1)]
         + [NOTE(A4, SEMIBREVE)] * 7
         + [NOTE(REST, CROTCHET), END])
assert NOTES[:4] == [0x903C, 0xC0FF, 0xA0FF, 0xB001], [hex(v) for v in NOTES]
assert NOTES[4] == 0x1C81 and NOTES[-2:] == [0x3F84, 0x8000]
assert len(NOTES) == 13, len(NOTES)

# Band 0 holds the entry jump and the 2-word TaskData; the code proper starts in
# band 1, because the hook's prefix fold pins the entry address and cannot be
# retargeted (docs/cave-frame.md, docs/message-task-abi.md).
# Band 0 holds the entry jump over the note array; the code proper starts in band 1,
# because the hook's prefix fold pins the entry address and cannot be retargeted.
BAND0 = [CAVE + k for k in range(1 + len(NOTES))]
assert all(blind(a) and in_run(a) for a in BAND0)
NOTES_AT = CAVE + 1
CODE_AT = next_blind(BAND0[-1] + 1)
assert blind(CODE_AT) and in_run(CODE_AT), hex(CODE_AT)
NOTES_PTR = ca.const_addr(NOTES_AT)

SPEAK = 0xDF7F          # the prompt engine: id in AL, nothing in X, and it returns
RATE = 8000             # probe90's value, unchanged
GAIN = 15               # STREAM_CODEC_OUTPUT_GAIN, 0 dB; probe90's value
CHANNEL = 2             # AUDIO_CHANNEL_A_AND_B -- **THE ONE CHANGE FROM probe90**
# No TaskData and no handler: everything happens in the button handler, so there is
# no timer, nothing scheduled, and nothing that can outlive the press.

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))


W(0xF00B)                       # enterl -16  (slots 0..13 usable, 14/15 = link)
W(0x0A23)                       # st AH,@(10,Y)  the event id we were called with

W(*ca.imm_words(VA_EVENT, 0x80))   # cmp AH,#0x4004
BR(0xF0, "OTHER")

# AUDIO_HARDWARE_CODEC=3, AUDIO_INSTANCE_0=0, AUDIO_CHANNEL_A_AND_B=2.
# probe90 passed 0 here and was silent; nothing else in this chain differs.
ca.call3(W, BSR, ca.STUB['StreamAudioSink'],
         al=('imm', 3), ah=('imm', 0), arg3=('imm', CHANNEL))
W(0x0B27)                       # st AL,@(11,Y)  sink
W(0x0084); BR(0xF4, "NOSINK")

# fn_1c751's own first act before connecting anything to a codec sink is to tear down
# whatever holds it (two StreamDisconnect calls, fn_1c773 at 0x1c773). Harmless if
# nothing does, and it costs two words. Not expected to be the fix -- probe89 proved
# the connect succeeds without it -- but there is no reason to keep omitting it.
ca.call2(W, BSR, ca.STUB['StreamDisconnect'], al=('imm', 0), ah=('slot', 11))

# A codec with no configured rate has no clock. Bose sets this at 0x1E41D, and
# fn_1c475 sets it on every one of its branches, before connecting.
ca.call3_long(W, BSR, ca.STUB['SinkConfigure'],
              al=('slot', 11), ah=('imm', 0x0301), arg3_32=RATE)
W(0x0084); BR(0xF4, "NORATE")

ca.call3_long(W, BSR, ca.STUB['SinkConfigure'],
              al=('slot', 11), ah=('imm', 0x0303), arg3_32=GAIN)
W(0x0084); BR(0xF4, "NOGAIN")

ca.call3_long(W, BSR, ca.STUB['SinkConfigure'],
              al=('slot', 11), ah=('imm', 0x0700), arg3_32=0)      # unmute
W(0x0084); BR(0xF4, "NOUNMUTE")

ca.call1(W, BSR, ca.STUB['StreamRingtoneSource'], al=('imm', NOTES_PTR))
W(0x0C27)                       # st AL,@(12,Y)  src
W(0x0084); BR(0xF4, "NOSRC")

ca.call2(W, BSR, ca.STUB['StreamConnect'], al=('slot', 12), ah=('slot', 11))
W(0x0084); BR(0xF4, "NOCONN")

# SUCCESS. Say NOTHING -- the prompt engine would load a .kap and rewire the DAC --
# and do NOT replay the displaced send, so the stock voice-assistant handler cannot
# displace it either. Just leave, and let the tone play.
BR(0xE0, "DONE")

LBL("NOCONN");   W(0x0C14); BSR(SPEAK); BR(0xE0, "PASS")  # 0x0C "connection lost"
LBL("NOSRC");    W(0x0A14); BSR(SPEAK); BR(0xE0, "PASS")  # 0x0A "connecting"
LBL("NOUNMUTE"); W(0x0114); BSR(SPEAK); BR(0xE0, "PASS")  # 0x01 "connecting to"
LBL("NOGAIN");   W(0x0014); BSR(SPEAK); BR(0xE0, "PASS")  # 0x00 "ready to connect"
LBL("NORATE");   W(0x0814); BSR(SPEAK); BR(0xE0, "PASS")  # 0x08 "disconnected"
LBL("NOSINK");   W(0x0614); BSR(SPEAK); BR(0xE0, "PASS")  # 0x06 "lost"
LBL("OTHER");    W(0x1614); BSR(SPEAK)                    # 0x16 "english"

# ---- replay the displaced call on every path EXCEPT success.
LBL("PASS")
W(0x0014); W(0x0027)            # ld AL,#0 ; st AL,@(0,Y)   message = 0
ca.load_al(W, ('imm', 0x512))
W(0x0A13)                       # ld AH,@(10,Y)
BSR(SEND)
LBL("DONE")
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

# The entry jump over the data, and the data. `bra` leaves X -- the link register the
# hook's `bsr` just set -- untouched, so the cave can still return.
assert CAVE not in out and not any(NOTES_AT + k in out for k in range(len(NOTES)))
_ev = CODE_AT - CAVE
assert -128 <= _ev <= 127, _ev
out[CAVE] = ((_ev & 0xFF) << 8) | 0xE0
for _k, _v in enumerate(NOTES):
    out[NOTES_AT + _k] = _v
print("notes at a=%#x -> data %#06x, %d words; code from %#x"
      % (NOTES_AT, NOTES_PTR, len(NOTES), CODE_AT))

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

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe115_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe115_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe115_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe115_cmd.txt")
