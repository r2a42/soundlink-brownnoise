"""probe101: BROWN NOISE into port 3, under the conditions that now work.

probe77, reflashed and retested: **a long clean tone with the phone CONNECTED and
music PAUSED** (2026-10-01, owner). That settles the shape of the whole thing:

* the **A2DP decoder stays loaded while A2DP is merely connected and idle**;
* so **port 3 is free** -- for the decoder it is a spare tone-mixing input, unlike
  the voice-prompt plugin where port 3 *is* the prompt;
* the **firmware** owns the DSP and has it wired to the DAC, so we never touch it;
* and with no music playing there is nothing to mask the result.

**The deliverable is therefore: phone connected, press the button.** No music, no
DSP ownership, no DAC rewiring -- none of the things that wedged probes 91-97.

## This probe swaps the ringtone for the real thing

Every piece has already been proven on hardware, separately:

    buf  = malloc(512)                     probe82 -- 512 words is the heap ceiling
    buf[0..1] = {0xACE1, 0}                the carried generator state
           noise_fill(buf+2, 510, buf)     probe81 -- bit-exact on the speaker
           KalimbaSendMessage(0x1072, 1000, 0, 0, 0)
    ksink3 = StreamKalimbaSink(3)          probe75/77
    src    = StreamRegionSource(buf+2,510) probe62
    t      = StreamConnect(src, ksink3)    probe75/77

This is probe82's cave with **two changes, both only about being audible**:

1. **The prompt call is deleted.** probe82 left it stock, so its `.kap` reload
   destroyed the connection -- probe82 could never have been heard, as recorded at
   the time.
2. **The tone rate is 1000 Hz, not 8000.** 510 samples at 8 kHz is 64 ms, which the
   owner has twice been asked to judge and twice could not -- rightly. At 1000 Hz the
   same buffer lasts **510 ms**, and brown noise band-limited to 500 Hz is still
   entirely brown noise: its energy is concentrated at the bottom anyway. The rate is
   a free parameter (the ADK reads `playback_rate` out of a prompt file header).

Half a second of real brown noise is unmistakable and is not a judgement call.

## What remains after this, honestly

**Sustain.** 510 samples is 510 ms at this rate, so a continuous sound needs the
buffer refilled -- and the machinery for that is now *proven*, not theoretical:
probe99 showed `MessageSendLater` + a `TaskData` in const padding + a handler running
from `MessageLoop` all work, and probe100 showed the MessageId can carry state across
wakeups. The generator already carries its LFSR and integrator through a state
pointer, so successive refills are continuous rather than repeating: a second refill
shares **0 of 128** samples with the first.

**No music needed -- but the phone must be CONNECTED.** Pause the music.

    half a second of noise -> **brown noise, from a cave, on a button press.** Then
                              sustain is the only thing between this and the goal.
    a tone-like buzz       -> the rate was clamped and the buffer is playing faster
                              than declared; still a success for the path.
    silence                -> every call is proven individually, so suspect the rate:
                              1000 Hz may be refused where 8000 is not.
"""

import sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca
import liftfn

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm


# --- output paths are derived from THIS FILE'S OWN NAME, never hardcoded -------------
# Every probe assembler is made by copying its predecessor, and three times now the copy
# kept the predecessor's hardcoded output paths and silently overwrote the artifacts of
# the image sitting ON THE DEVICE: probe129_words.json twice, probe134_words.json once
# (restored from build/hook/snapshots/ and re-verified against the device readback both
# times). A words.json is the only record of what a flashed image contains, so losing it
# costs the readback check its reference.
_PROBE = re.match(r'assemble_(probe\d+)\.py$',
                  os.path.basename(os.path.abspath(__file__))).group(1)

CAVE = 0x3E21D         # fixed by the hook's prefix fold at 0xAE0 (do not move)
# 0xae3 := bra +1 only. 0xAE4..0xAE6 (the prompt call) stays STOCK this time.
REDIRECT_EDITS = [("0x6fff1", "0x04"), ("0x6fff3", "0xd7"), ("0x6fff5", "0x3b"),
                  ("0x6fff6", "0xe0"), ("0x6fff7", "0x01"),   # 0xae3 := bra +1
                  # 0xae4..0xae6 := three nops. probe82 left the prompt call stock
                  # and its .kap reload destroyed the connection, so probe82 could
                  # never have been heard. Nothing may take the path back now.
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

# Heap ladder: take the biggest block the VM will give. Slot 12 = sample count,
# slot 13 = the request id that reports which size won.
ca.call1(W, BSR, ca.STUB['malloc'], al=('imm', 512))
W(0x0A27)                       # st AL,@(10,Y)
W(0x0084); BR(0xF0, "GOT512")
ca.call1(W, BSR, ca.STUB['malloc'], al=('imm', 256))
W(0x0A27)
W(0x0084); BR(0xF0, "GOT256")
ca.call1(W, BSR, ca.STUB['malloc'], al=('imm', 128))
W(0x0A27)
W(0x0084); BR(0xF4, "NOMEM")
ca.load_al(W, ('imm', 126)); W(0x0C27)          # 128 - 2 state words
ca.load_al(W, ('imm', 0x01)); W(0x0D27)         # "connecting to"
BR(0xE0, "HAVE")
LBL("GOT256")
ca.load_al(W, ('imm', 254)); W(0x0C27)
ca.load_al(W, ('imm', 0x04)); W(0x0D27)         # "connected"
BR(0xE0, "HAVE")
LBL("GOT512")
ca.load_al(W, ('imm', 510)); W(0x0C27)
ca.load_al(W, ('imm', 0x0E)); W(0x0D27)         # "connected to"
LBL("HAVE")

# Seed the carried state in buf[0..1], then samples = buf + 2.
W(0x0A1B)                       # ld X,@(10,Y)
ca.load_al(W, ('imm', 0xACE1))
W(0x0026)                       # st AL,@(0,X)
ca.load_al(W, ('imm', 0))
W(0x0126)                       # st AL,@(1,X)
W(0x0A17)                       # ld AL,@(10,Y)
W(0x0234)                       # add AL,#2
W(0x0B27)                       # st AL,@(11,Y)  samples

ca.calln(W, BSR, "NOISE", al=('slot', 11), ah=('slot', 12),
         stack=[('slot', 10)], stage='AL')

ca.calln(W, BSR, ca.STUB['KalimbaSendMessage'],
         al=('imm', 0x1072), ah=('imm', 1000),   # 510 samples = 510 ms, not 64
         stack=[('imm', 0), ('imm', 0), ('imm', 0)], stage='AL')
W(0x0084); BR(0xF4, "NOSTREAM")

ca.call1(W, BSR, ca.STUB['StreamKalimbaSink'], al=('imm', 3))
W(0x0527)                       # st AL,@(5,Y)  ksink
W(0x0084); BR(0xF4, "NOSTREAM")

ca.call2(W, BSR, ca.STUB['StreamRegionSource'], al=('slot', 11), ah=('slot', 12))
W(0x0427)                       # st AL,@(4,Y)  src
W(0x0084); BR(0xF4, "NOSTREAM")

ca.call2(W, BSR, ca.STUB['StreamConnect'], al=('slot', 4), ah=('slot', 5))
W(0x0084); BR(0xF4, "NOSTREAM")

W(0x0D17); BR(0xE0, "EXIT")     # ld AL,@(13,Y)  which malloc size won
LBL("NOSTREAM"); W(0x0814); BR(0xE0, "EXIT")   # 0x08  "disconnected"
LBL("NOMEM");    W(0x0614)                     # 0x06  "lost"
LBL("EXIT")
W(0xF00F)                       # leavel -16

BR(0xE0, "DONE")                # jump over the lifted function
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
    assert seen.get(a) == (tgt & 0x3FFFF), (hex(a), kind, hex(tgt), seen.get(a))
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
