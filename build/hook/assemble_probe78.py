#!/usr/bin/env python3
"""probe78: real brown noise, with the generator COMPILED instead of copied.

probe77 result: **a long tone** (2026-09-30, owner) -- low, "think car horn",
and no tone at all without music playing. So:

  * the `.kap` reload WAS the thief, and deleting the prompt call fixed it;
  * loud, sustained, software-generated sound on a button press works;
  * and the owner's verdict is the right one: a ringtone is a car horn, not
    brown noise. Every ringtone timbre is periodic by construction.

The sound now has to come from the generator, which is the one thing that has
never run. Probes 68, 69, 72 and 73 crashed on it, and six presses narrowed the
fault to one of seven instructions **transcribed by hand** from compiler output.

So this probe does not try to fix those seven instructions. It replaces the
whole method: `tools/liftfn.py` compiles `build/noiseprobe/noise.c`, links it,
and lifts `noise_fill` out of the linked image **as data**, turning every
internal branch into a label so the cave's band layout can recompute it.

And the lifted code is **nothing like the transcription**. The compiler keeps
`acc` and the pointer in the XAP scratch registers `@0xFFF8`, `@0xFFF9` and
`@0xFFFA`, and only `x` in the frame at `@(-1,Y)`; the hand-written version put
all four in frame slots. That is a structural difference, not a one-opcode
difference, which is consistent with six presses failing to find a single bad
instruction.

**Clobbering 0xFFF8..0xFFFA is safe here**, and the reason is the compiler's
own convention: those are caller-saved scratch, so anything live across a call
is already spilled -- and the cave is installed *at a call site*
(`0xAE0 bsr 0xE06D`), so the surrounding function had already spilled before
we got control. Bose's own code uses them the same way (`0x1E3C7 st AH,@0xFFF8`
at a function entry).

    buf   = malloc(128)                    proven, probe61
    noise_fill(buf, 128)                   THE LIFTED GENERATOR -- new
    KalimbaSendMessage(0x1072, 8000, …)    proven, probe75
    ksink = StreamKalimbaSink(3)           proven, probe75
    src   = StreamRegionSource(buf, 128)   proven, probe62
    t     = StreamConnect(src, ksink)      proven, probe75

**The prompt call at 0xAE4 is deliberately left INTACT.** 128 words is 16 ms at
8 kHz, which is a tick, not something to judge by ear -- so this probe is a
crash test for the generator and wants its spoken diagnosis back. If it says
"connected to", the generator runs on hardware for the first time and probe79
can delete the prompt again and listen.

    "connected to"    -> every call succeeded AND THE GENERATOR RAN.
    "lost"            -> malloc(128) failed (it never has).
    "disconnected"    -> KalimbaSendMessage FALSE: no music was playing.
    "ready to connect"-> StreamKalimbaSink(3) returned 0 (it never has).
    "connecting"      -> StreamRegionSource returned 0.
    "connection lost" -> StreamConnect refused.
    a crash           -> the generator still faults, and the fault is NOT
                         transcription. That would be worth knowing.

Sustain is a separate problem and is not addressed here: 16 ms needs refilling,
`docs/roadmap.md` Step 3.
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
                  ("0x6fff6", "0xe0"), ("0x6fff7", "0x01")]
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

W(0xF80B)                       # enterl -8
BSR(BACK)                       # stock back-call (proven by probe37)

# 130 words: buf[0..1] is the generator's carried state, buf[2..129] the samples.
ca.call1(W, BSR, ca.STUB['malloc'], al=('imm', NSAMP + 2))
W(0x0627)                       # st AL,@(6,Y)  buf
W(0x0084); BR(0xF4, "NOMEM")

# Seed the state: buf[0] = 0xACE1 (the LFSR), buf[1] = 0 (the integrator).
W(0x061B)                       # ld X,@(6,Y)
ca.load_al(W, ('imm', 0xACE1))
W(0x0026)                       # st AL,@(0,X)
ca.load_al(W, ('imm', 0))
W(0x0126)                       # st AL,@(1,X)

W(0x0617)                       # ld AL,@(6,Y)
W(0x0234)                       # add AL,#2
W(0x0727)                       # st AL,@(7,Y)  samples = buf + 2

# The new thing: noise_fill(samples, NSAMP, buf). Three arguments, so arg3
# goes in our @(0,Y) -- which is the callee's @(2,Y), and the lifted code
# reads it from exactly there.
ca.calln(W, BSR, "NOISE", al=('slot', 7), ah=('imm', NSAMP),
         stack=[('slot', 6)], stage='AL')

# Proven in probe75, all three.
ca.calln(W, BSR, ca.STUB['KalimbaSendMessage'],
         al=('imm', 0x1072), ah=('imm', 8000),
         stack=[('imm', 0), ('imm', 0), ('imm', 0)], stage='AL')
W(0x0084); BR(0xF4, "NODSP")

ca.call1(W, BSR, ca.STUB['StreamKalimbaSink'], al=('imm', 3))
W(0x0527)                       # st AL,@(5,Y)  ksink
W(0x0084); BR(0xF4, "NULLSINK")

ca.call2(W, BSR, ca.STUB['StreamRegionSource'], al=('slot', 7), ah=('imm', NSAMP))
W(0x0427)                       # st AL,@(4,Y)  src
W(0x0084); BR(0xF4, "NULLSRC")

ca.call2(W, BSR, ca.STUB['StreamConnect'], al=('slot', 4), ah=('slot', 5))
W(0x0084); BR(0xF4, "NOCONN")
W(0x0E14); BR(0xE0, "EXIT")     # ld AL,#0x0E  "connected to"
LBL("NOCONN");   W(0x0C14); BR(0xE0, "EXIT")   # 0x0C  "connection lost"
LBL("NULLSRC");  W(0x0A14); BR(0xE0, "EXIT")   # 0x0A  "connecting"
LBL("NODSP");    W(0x0814); BR(0xE0, "EXIT")   # 0x08  "disconnected"
LBL("NULLSINK"); W(0x0014); BR(0xE0, "EXIT")   # 0x00  "ready to connect"
LBL("NOMEM");    W(0x0614); BR(0xE0, "EXIT")   # 0x06  "lost"
LBL("EXIT")
W(0xF80F)                       # leavel -8
BR(0xE0, "DONE")                # jump over the lifted function

# The lifted generator, verbatim words with its branches as labels. It carries
# its own `enterl -2`/`leavel -2`, so its frame is self-consistent.
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

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe78_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe78_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe78_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe78_cmd.txt")
