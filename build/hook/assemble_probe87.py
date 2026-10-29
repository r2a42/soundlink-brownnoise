#!/usr/bin/env python3
"""probe87: brown noise straight to the CODEC. No DSP, no music, no phone.

Found while researching 2026-10-01: **Bose has a DSP-less tone path and this
project had been ignoring it.** `0x1C17F` plays a tone and branches on whether
the DSP is available:

    0x1c192  ld X,@0x6c4 ; ld AH,@(1,X) ; asr #8 ; and AH,#1   ; "use DSP" flag
    0x1c199  beq +9                                  ; clear -> the CODEC path
    0x1c19a  ld AL,@(4,Y) ; st AL,@(0,Y)              ; channel = 0
    0x1c19c  ld AL,#0x3 ; ld AH,#0x0                  ; CODEC, instance 0
    0x1c19e  bsr StreamAudioSink                      ; <- STRAIGHT TO THE DAC
    0x1c1a1  bra +5
    0x1c1a2  ld AL,#0x3 ; bsr StreamKalimbaSink       ; set -> port 3 instead
    0x1c1a6  st AL,@(4,Y)                             ; either sink
    0x1c1a8  bsr StreamRingtoneSource
    0x1c1af  bsr 0x1C751                              ; = StreamConnect+PanicNull

So the firmware connects a **source directly to `StreamAudioSink`** when no DSP
is up. That is also the ADK's documented idiom (`ringtone_if.h`), and it means
**standalone audio does not need `KalimbaLoad` at all.**

## Why probe63 is not the counter-example it looked like

probe63 did `StreamAudioSink(3, 0, 2)`, configured the rate, and crashed on
`StreamConnect`. It used only frame slots 0-4, so `docs/cave-frame.md` does not
explain it. But **channel 2 is `AUDIO_CHANNEL_A_AND_B`** -- "the stereo CODEC in
mono-mode" (`app/audio/audio_if.h`) -- while **Bose's own direct path asks for
channel 0, `AUDIO_CHANNEL_A`**. Of 33 `StreamAudioSink` sites, 27 use hardware 3
instance 0; the channel is the part that varies at runtime.

The channel is therefore the prime suspect for probe63's crash, and it has never
been varied.

## This probe

    sink = StreamAudioSink(CODEC=3, 0, AUDIO_CHANNEL_A=0)   <- the change
           SinkConfigure(sink, STREAM_CODEC_OUTPUT_RATE, 2000)
    buf  = malloc(512)                                      proven, probe82
    buf[0..1] = {0xACE1, 0}
           noise_fill(buf+2, 510, buf)                      proven, probe81
    src  = StreamRegionSource(buf+2, 510)                   proven, probe62
    t    = StreamConnect(src, sink)                         the question

Rate 2000 makes 510 samples last **255 ms**: the tone rate is a free parameter,
since the ADK reads `playback_rate` out of a prompt file header rather than an
enum, and 255 ms of brown noise is long enough to recognise.

**The prompt call is deleted**, so nothing can take the DAC back. That costs the
spoken ids, but all three outcomes stay distinguishable by ear, because a crash
restarts the speaker audibly:

    brown noise  -> **the deliverable, standalone.** No DSP, no music, no phone.
                    What remains is only duration.
    silence      -> the codec sink accepts a region source and plays nothing.
    a crash      -> connecting to the codec sink is fatal regardless of channel.
                    probe86 (a RINGTONE source to the same sink, which is Bose's
                    exact code path) then separates "this sink" from "this
                    source type".

**No music needed. Nothing need be connected.**
"""

import sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca
import liftfn

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

CAVE = 0x3E21D         # fixed by the hook's prefix fold at 0xAE0 (do not move)
# 0xae3 := bra +1 only. 0xAE4..0xAE6 (the prompt call) stays STOCK this time.
REDIRECT_EDITS = [("0x6fff1", "0x04"), ("0x6fff3", "0xd7"), ("0x6fff5", "0x3b"),
                  ("0x6fff6", "0xe0"), ("0x6fff7", "0x01"),   # 0xae3 := bra +1
                  # 0xae4..0xae6 := three nops -- delete the prompt player so
                  # nothing can take the DAC back from us.
                  ("0x6fff8", "0x00"), ("0x6fff9", "0x00"),
                  ("0x6fffa", "0x00"), ("0x6fffb", "0x00"),
                  ("0x6fffc", "0x00"), ("0x6fffd", "0x00")]
AREA0 = 0x6EA30
NSAMP = 128

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

# ---- the generator, lifted from the linked image ----
LIFT = liftfn.lift('build/noiseprobe/noiseprobe', 'noise_fill')
assert not LIFT['problems'], LIFT['problems']
print('lifted noise_fill: %d words, %d items, %d labels'
      % (LIFT['size'], len(LIFT['items']),
         sum(1 for it in LIFT['items'] if it[0] == 'label')))

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))

BACK = 0xE06D          # the call the hook at 0xae0 displaced

W(0xF00B)                       # enterl -16  (slots 0..13 usable, 14/15 = link)
BSR(BACK)                       # stock back-call (proven by probe37)

# The one structural change from probe63: AUDIO_CHANNEL_A (0), not A_AND_B (2).
ca.call3(W, BSR, ca.STUB['StreamAudioSink'],
         al=('imm', 3), ah=('imm', 0), arg3=('imm', 0))
W(0x0A27)                       # st AL,@(10,Y)  sink
W(0x0084); BR(0xF4, "EXIT")

# 510 samples at 2000 Hz = 255 ms. 3-arg trap, 32-bit value (proven probe60).
ca.call3_long(W, BSR, ca.STUB['SinkConfigure'],
              al=('slot', 10), ah=('imm', 0x0301), arg3_32=2000)

ca.call1(W, BSR, ca.STUB['malloc'], al=('imm', 512))
W(0x0B27)                       # st AL,@(11,Y)  buf
W(0x0084); BR(0xF4, "EXIT")

W(0x0B1B)                       # ld X,@(11,Y)
ca.load_al(W, ('imm', 0xACE1))
W(0x0026)                       # st AL,@(0,X)   seed the LFSR
ca.load_al(W, ('imm', 0))
W(0x0126)                       # st AL,@(1,X)   seed the integrator
W(0x0B17)                       # ld AL,@(11,Y)
W(0x0234)                       # add AL,#2
W(0x0C27)                       # st AL,@(12,Y)  samples = buf + 2

ca.calln(W, BSR, "NOISE", al=('slot', 12), ah=('imm', 510),
         stack=[('slot', 11)], stage='AL')

ca.call2(W, BSR, ca.STUB['StreamRegionSource'], al=('slot', 12), ah=('imm', 510))
W(0x0D27)                       # st AL,@(13,Y)  src
W(0x0084); BR(0xF4, "EXIT")

ca.call2(W, BSR, ca.STUB['StreamConnect'], al=('slot', 13), ah=('slot', 10))
LBL("EXIT")
W(0xF00F)                       # leavel -16

BR(0xE0, "DONE")                # jump over the lifted function
W(0x0000)                       # padding past the +-128 bsr encoding gap
LBL("NOISE")
for it in LIFT['items']:
    if it[0] == 'w':
        W(*it[1])
    elif it[0] == 'br':
        BR(it[1], it[2])
    else:
        LBL(it[1])
LBL("DONE")

# ---- layout (proven machinery, probes 67-77) ----
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

for iteration in range(24):
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
            # The 1-word fold is sext8(operand), so its reach is -128..127; the
            # old -126..126 bound created FALSE gaps. Relaxation only WIDENS,
            # because letting a branch shrink again made the layout oscillate.
            want = 1 if -128 <= v <= 127 else 2 if bsr2_encodable(v - 1) else 3 if bsr3_encodable(v - 2) else 0
            if want > bsr_size.get(i, 2): bsr_size[i] = want; ok = False
        else:
            want = 1 if -128 <= tgt - a <= 127 else 2
            if want > br_size.get(i, 1): br_size[i] = want; ok = False
    if ok: break
else:
    raise SystemExit("no converge")

out = {}
# A padded bsr does not start at its item's address; decode-verify needs to know.
bsr_at = {}
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
                # A 2-word bsr cannot express a SHORT distance: both prefix
                # bytes must be non-zero, so its smallest magnitude is 129.
                # Pad with a nop and use the 1-word form.
                v1 = tgt - (a + 1)
                assert -128 <= v1 <= 127, (hex(a), hex(tgt), v1)
                out[a] = 0x0000
                out[a+1] = ((v1 & 0xFF) << 8) | 0x9C
                bsr_at[a] = a + 1
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
            if not done:
                v1 = tgt - (a + 2)
                assert -128 <= v1 <= 127, (hex(a), hex(tgt), v1)
                out[a] = 0x0000; out[a+1] = 0x0000
                out[a+2] = ((v1 & 0xFF) << 8) | 0x9C
                bsr_at[a] = a + 2
                done = True
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
            if not -128 <= bb <= 127:
                # Same gap as the 2-word bsr: a prefix byte cannot be zero, so a
                # 2-word conditional branch cannot express a SHORT distance.
                # Pad with a nop and use the 1-word form at a+1.
                v1 = tgt - (a + 1)
                assert -128 <= v1 <= 127, (hex(a), hex(tgt), v1)
                out[a] = 0x0000
                out[a+1] = ((v1 & 0xFF) << 8) | op
                bsr_at[a] = a + 1
            else:
                out[a] = (aa & 0xFF) << 8; out[a+1] = ((bb & 0xFF) << 8) | op
for cslot, nb in extra.items():
    v = nb - cslot
    out[cslot] = ((v & 0xFF) << 8) | 0xE0

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
    at = bsr_at.get(a, a)
    assert seen.get(at) == (tgt & 0x3FFFF), (hex(a), kind, hex(tgt), seen.get(at))
for i, item in enumerate(prog):
    if item[0] != "label":
        assert addrs[i] in dstarts, (hex(addrs[i]), "boundary")
print("decode-verify: all branches OK, boundaries OK")

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe87_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe87_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe87_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe87_cmd.txt")
