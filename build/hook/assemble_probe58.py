#!/usr/bin/env python3
"""probe58: brown noise through a Source -- the route the ADK actually supports.

probe58 writes PCM straight into StreamAudioSink. Nothing in the ADK or in
Bose's firmware ever does that (docs/bose-audio-path.md §2): every
SinkClaim/SinkMap/SinkFlush in the ADK is on a Bluetooth pipe, and the
documented way to make a sound is to connect a **Source** to the audio
sink. This probe does it the documented way.

    dac = StreamAudioSink(CODEC=3, INSTANCE_0=0, CHANNEL_A_AND_B=2)
    SinkConfigure(dac, STREAM_CODEC_OUTPUT_RATE = 0x301, 8000)
    buf = malloc(1024)  or malloc(128) if that fails
    n samples of brown noise generated into buf:
        x   = (x>>1) ^ (-(x&1) & 0xB400)      16-bit Galois LFSR
        acc = acc - (acc>>8)                  leak, to bound the walk
        acc = acc + ((int16)x >> 4)           integrate: white -> brown
        *p++ = acc
    src = StreamRegionSource(buf, n)
    StreamConnect(src, dac)
    SinkConfigure(dac, STREAM_AUDIO_MUTE_ENABLE = 0x700, 0)   -- Bose un-mutes
    SinkConfigure(dac, STREAM_CODEC_OUTPUT_GAIN = 0x303, 15)      AFTER connect

Why each piece is believed to work:

- **StreamRegionSource (0x152)** makes a Source out of any memory block.
  Bose calls it 19 times, including at 0x06BEB with a pointer of 0x7F6E,
  which is inside its own constant-pool window -- so streaming from
  arbitrary memory is something this firmware already does.
- **malloc (0x026)** is called 81 times by Bose, with constant sizes up to
  134 words. 1024 is a step beyond anything it asks for, so there is a
  fallback to 128; whichever succeeds sets the region length.
- **The un-mute after StreamConnect** is Bose's own order at 0x1E42D.
- Unlike probe58, the cave hands the samples to the stream subsystem and
  returns. The audio continues after the button handler has finished,
  which is what we actually want.

**The bails speak** (docs/bose-audio-path.md §7). Each failure path returns
a different request id, so one button press says out loud where it stopped:

    sink null      -> 0x06  "lost"
    malloc failed  -> 0x08  "disconnected"
    source null    -> 0x0A  "connecting"
    connect failed -> 0x0C  "connection lost"
    reached the end-> 0x04  "connected"

So the reading is: noise then "connected" = it works. Silence then
"connected" = every call succeeded but nothing came out. Anything else
names its own failure.

**The gain is 15 because 15 is 0 dB.** The ADK's gain_utils library gives
the mapping: GainDbToDacGain(v) = CODEC_STEPS + v/DB_TO_DAC, with
CODEC_STEPS = 15 and DB_TO_DAC = 3 dB. So DAC gain 15 is unity and each
step is 3 dB -- the 0..22 range spans -45 dB to +21 dB. probes 56-57 used
12 and described it as "of 0..22" as though that were mid-scale. It is
**9 dB down**, and with this waveform at -14 dBFS the output would have
been around -23 dB: quiet enough that a working probe could be mistaken
for a silent one. 15 is the loudest setting that cannot clip, since the
waveform peaks at -3.2 dBFS.

The generator was tuned offline in tools/cavesim.py rather than guessed.
Without the leak the integrator is an unbounded random walk: it wraps 16
bits after about 40,000 samples and every wrap is a full-scale click.
`acc -= acc>>8` with a >>4 step holds it to +-22785 over 400,000 samples
(50 s at 8 kHz) with zero discontinuities, at -14 dBFS, and the measured
slope is -7.9/-6.1/-5.1 dB per octave across the band -- brown noise. The
emulator's output matches a Python model of the algorithm exactly.

Known leak (the other kind): the block is never freed, and the header says that is the
caller's job. Each press leaks up to 2 KB, so after enough presses malloc
will start failing -- which will announce itself as "disconnected". A
power cycle clears it.
"""
import sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

TONE = 0x4946
CAVE = 0x3E21D
REDIRECT_EDITS = [("0x6fff1", "0x04"), ("0x6fff3", "0xd7"), ("0x6fff5", "0x3b"),
                  ("0x6fff6", "0xe0"), ("0x6fff7", "0x01")]   # 0xae3 := bra +1 (word 0x01e0, no-op)
AREA0 = 0x6EA30

w = xapvm.load_words("firmware/bose/extracted/internal_fs/vm.app")
code = w[0x18:]
C0 = (0x6e974 + 0x34) % 64
def blind(cw): return 34 <= (2*cw + C0) % 64 <= 60
_runs = []
_i = 0x3E200
while _i < 0x3E400:
    if code[_i] == 0:
        j = _i
        while j < 0x3E400 and code[j] == 0: j += 1
        if j - _i >= 40: _runs.append((_i, j))
        _i = j
    else:
        _i += 1
def in_run(cw): return any(a <= cw < b for a, b in _runs)
def next_blind(pc):
    while not blind(pc) or not in_run(pc):
        pc += 1
        assert pc < 0x3E3F8, "cave exceeds zero-run region"
    return pc
stubs, _ = xapvm.find_stubs(code)
tt = xapvm.trap_table()
assert tt.get(stubs[TONE]) == "StreamRingtoneSource" if TONE in stubs else True  # 0x4946 is a real function, not a stub

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))

BACK = 0xE06D          # the call the hook at 0xae0 displaced

W(0xF80B)                       # enterl -8
BSR(BACK)                       # stock back-call (proven)

# dac = StreamAudioSink(CODEC, INSTANCE_0, CHANNEL_A_AND_B)   [3-arg ABI]
ca.call3(W, BSR, ca.STUB['StreamAudioSink'], al=('imm',3), ah=('imm',0), arg3=('imm',2))
W(0x0227)                       # st AL,@(2,Y)  dac
W(0x0084); BR(0xF4, "BAIL_SINK")
# SinkConfigure(dac, STREAM_CODEC_OUTPUT_RATE, 8000)
ca.call3_long(W, BSR, ca.STUB['SinkConfigure'], al=('slot',2), ah=('imm',0x301), arg3_32=8000)

# buf = malloc(1024), falling back to malloc(128)             [1-arg ABI]
ca.call1(W, BSR, ca.STUB['malloc'], al=('imm',1024))
W(0x0327)                       # st AL,@(3,Y)  buf
ca.load_al(W, ('imm',1024)); W(0x0127)          # n = 1024
W(0x0317)                       # ld AL,@(3,Y)
W(0x0084); BR(0xF0, "GEN")      # got the big block
ca.call1(W, BSR, ca.STUB['malloc'], al=('imm',128))
W(0x0327)                       # st AL,@(3,Y)  buf
ca.load_al(W, ('imm',128)); W(0x0127)           # n = 128
W(0x0317)                       # ld AL,@(3,Y)
W(0x0084); BR(0xF4, "BAIL_MALLOC")
LBL("GEN")

# p = buf ; x = 0xACE1 ; acc = 0 ; count = n
W(0x0317); W(0x0527)            # p = buf
ca.load_al(W, ('imm',0xACE1)); W(0x0627)
ca.load_al(W, ('imm',0));      W(0x0727)
W(0x0117); W(0x0027)            # count = n
LBL("LOOP")
# leaky integrator: acc -= acc>>8. Without it the random walk is unbounded
# and wraps 16 bits after ~40k samples, which is a loud click. With it the
# walk is bounded forever (400k samples: +-22785, 0 discontinuities) and the
# spectrum still falls at about -6 dB/octave. Verified in tools/cavesim.py.
W(0x0713)                       # ld AH,@(7,Y)   acc
W(0x08A4)                       # asr #8         arithmetic, sign-preserving
W(0x0717)                       # ld AL,@(7,Y)   acc
W(0xE055)                       # sub AL,@$XAP_AH   acc - (acc>>8)
W(0x0727)                       # st AL,@(7,Y)
W(0x0613)                       # ld AH,@(6,Y)   x
W(0x0009)                       # clc
W(0x01A4)                       # asr #1         x>>1
W(0x0617)                       # ld AL,@(6,Y)
W(0x01C4)                       # and AL,#1
W(0x0074)                       # neg            -(x&1)
W(0xB400, 0x00C4)               # and AL,#0xb400
W(0xE1D1)                       # xor AH,AL      LFSR step
W(0x0623)                       # st AH,@(6,Y)   x = new
W(0x04A4)                       # asr #4  (>>4 with the leak: -14 dBFS)
W(0x0733)                       # add AH,@(7,Y)  acc += x>>6
W(0x0723)                       # st AH,@(7,Y)
W(0x051B)                       # ld X,@(5,Y)    p
W(0x0022)                       # st AH,@(0,X)   *p = acc
W(0x0517); W(0x0134); W(0x0527) # p++
W(0x0017); W(0xFF34); W(0x0027) # count--
W(0x0084)                       # cmp AL,#0
BR(0xF0, "LOOP")                # bne

# src = StreamRegionSource(buf, n)                            [2-arg ABI]
ca.call2(W, BSR, ca.STUB['StreamRegionSource'], al=('slot',3), ah=('slot',1))
W(0x0427)                       # st AL,@(4,Y)  src
W(0x0084); BR(0xF4, "BAIL_SRC")
# StreamConnect(src, dac)                                     [2-arg ABI]
ca.call2(W, BSR, ca.STUB['StreamConnect'], al=('slot',4), ah=('slot',2))
W(0x0084); BR(0xF4, "BAIL_CONN")
# Bose un-mutes and sets the gain AFTER the connect (its own order, 0x1E42D)
ca.call3_long(W, BSR, ca.STUB['SinkConfigure'], al=('slot',2), ah=('imm',0x700), arg3_32=0)
ca.call3_long(W, BSR, ca.STUB['SinkConfigure'], al=('slot',2), ah=('imm',0x303), arg3_32=15)
W(0x0414); BR(0xE0, "EXIT")     # ld AL,#0x04  "connected"

LBL("BAIL_SINK");   W(0x0614); BR(0xE0, "EXIT")   # "lost"
LBL("BAIL_MALLOC"); W(0x0814); BR(0xE0, "EXIT")   # "disconnected"
LBL("BAIL_SRC");    W(0x0A14); BR(0xE0, "EXIT")   # "connecting"
LBL("BAIL_CONN");   W(0x0C14)                     # "connection lost"
LBL("EXIT")
W(0xF80F)                       # leavel -8

# ---- layout (proven machinery) ----
bsr_size, br_size = {}, {}
label_addr = {}
def needs_follow(item):
    k = item[0]
    if k == "bsr": return True
    if k == "br": return item[1] != 0xE0
    return (item[1][-1] & 0xFF) != 0xE2
def bsr2_encodable(v):
    for aa in range(max(-128, (v >> 8) - 2), min(128, (v >> 8) + 3)):
        if aa == 0: continue
        b = v - aa * 256
        if -128 <= b <= 127: return True
    return False
def bsr3_encodable(v):
    for aa in range(-128, 128):
        if aa == 0: continue
        for bb in range(-128, 128):
            if bb == 0: continue
            cc = v - aa*65536 - bb*256
            if -128 <= cc <= 127: return True
    return False

for iteration in range(12):
    addr = CAVE
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
        if addr + need > band_end:
            if addr >= band_end:
                addr = next_blind(band_end); continue
            nb = next_blind(band_end)
            assert blind(addr) and in_run(addr), (hex(addr), "connector slot not blind")
            extra[addr] = nb
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
            want = 1 if -128 <= tgt - a <= 127 else 2
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
        else:
            v = tgt - a
            aa = 1 if v > 0 else -2
            bb = v - aa * 256
            assert -128 <= bb <= 127
            out[a] = (aa & 0xFF) << 8; out[a+1] = ((bb & 0xFF) << 8) | op
for ca, nb in extra.items():
    v = nb - ca
    out[ca] = ((v & 0xFF) << 8) | 0xE0

lo, hi = min(out), max(out)
print(f"cave spans {lo:#x}..{hi:#x}, {len(out)} words (iters {iteration+1})")
assert not [a for a in out if not blind(a) or not in_run(a)]
patched = list(code)
for cw, val in out.items(): patched[cw] = val & 0xFFFF
intended, seen, dstarts = {}, {}, set()
for i, item in enumerate(prog):
    if item[0] in ("bsr", "br"):
        a = addrs[i]
        lbl = item[2] if item[0] == "br" else item[1]
        intended[a] = (label_addr[lbl] if isinstance(lbl, str) else lbl, item[0])
for a, op, v, ln in xapvm.decode(patched, fold_zero=False):
    dstarts.add(a)
    if lo <= a <= hi:
        if op == 0x9C: seen[a] = (a + ln - 1 + v) & 0x3FFFF
        elif op in (0xE0, 0xF0, 0xF4, 0xF8): seen[a] = (a + v) & 0x3FFFF
for a, (tgt, kind) in intended.items():
    assert seen.get(a) == (tgt & 0x3FFFF), (hex(a), kind, hex(tgt), seen.get(a))
for i, item in enumerate(prog):
    if item[0] != "label":
        assert addrs[i] in dstarts, (hex(addrs[i]), "boundary")
print("decode-verify: all branches OK, boundaries OK")

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe58_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe58_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe58_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe58_cmd.txt")
