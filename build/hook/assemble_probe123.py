#!/usr/bin/env python3
"""probe123: can port 3 be CLAIMED and written? probe114's question, on a hook that reports.

probe122 answered the memory question definitively: **`malloc(320)` returned 0** ("lost"),
so the 318-word pool block is taken as well as the 642 that probes 111-121 all asked for.
`probe103`'s `malloc(512)` had already returned 0. **The heap is the wall.**

But probe122 also proved, in the same press, that **`KalimbaSendMessage(0x1072, 8000)`
succeeded and `StreamKalimbaSink(3)` succeeded** -- so with the laptop connected and music
paused, a DSP is loaded and port 3 exists and is armed. Only memory was missing.

So stop allocating. `fn_12e1a` -- Bose's own `SinkMap` + `SinkClaim` helper, 29 words, 13
callers in its USB and upgrade paths -- claims space **inside the sink's own buffer** and
returns a pointer, or 0 if the claim is refused. That needs no heap at all, and it feeds
**16-bit PCM**, so it uses `noise_fill`, the leaky integrator with a one-pole high-pass
that is kalsim-verified and was bit-exact on this hardware in probe81 -- a better spectrum
than the ADPCM random walk.

## Why this is not just probe114 reflashed

probe114 asks exactly this question and was pressed on 2026-10-04: **beep and LED flash,
alternating with LED-only, and no spoken id at all.** That pattern is the stock
voice-assistant start/stop toggle, which means the centre long press *did* emit `0x4004`
and *did* reach `0x107be`. The hook fired. probe114 simply could not report, because it is
the **only** probe that calls `0xDF7F` directly from a button handler -- the thing that
crashed probe30. It did not crash here, but it did not speak either.

Every probe that has ever reported successfully used one of two mechanisms: the **AL trick**
at `0xAE0` (leave the id in `AL`, the stock prompt call speaks it -- probes 89, 99, 100,
104, 122) or a **message handler** calling `0xDF7F` (probe99). probe123 uses the first.

So: same question, moved to `0xAE0` with the prompt left stock. `0xAE0` is also where
probe122 proved the port is live, and the Bluetooth long press is a trigger with seven
confirmed fires now.

## The probe

    KalimbaSendMessage(0x1072, 8000, 0, 0, 0)    arm the port-3 reader
    ksink = StreamKalimbaSink(3)
    ptr   = fn_12e1a(ksink, 256)                 SinkMap + SinkClaim, 0 if refused
    ptr == 0 -> AL = 0x12 "voice prompts on"     the claim was REFUSED
    else        noise_fill(ptr, 254, state)      16-bit PCM, two words of frame state
                SinkFlush(ksink, 256)
                AL = 0x13 "voice prompts off"    the claim was HONOURED

254 words at 8 kHz is ~32 ms, so the audio is incidental: **the spoken id is the result.**

**LAPTOP CONNECTED, MUSIC PAUSED. Long-press the BLUETOOTH button.**

    "voice prompts off"  -> **the port is directly writable.** Sustained brown noise then
                            needs no heap: claim, write, flush, on a timer. No source, no
                            transform, nothing to leak, and the better generator.
    "english"            -> the claim was refused on an armed port 3. Then the heap is the
                            only route and the next step is sizing down from 320 through
                            the 138, 100 and 94-word pools.
    "disconnected"       -> KalimbaSendMessage FALSE: no .kap, so not actually connected.
    "voice prompts on"   -> StreamKalimbaSink(3) returned 0 (no port 3).
    nothing              -> 0xAE0 did not fire, contradicting probe122 an hour earlier.
"""

import sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca
import liftfn
import liftfn

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

CAVE = 0x3E21D         # fixed by the hook's prefix fold at 0xAE0 (do not move)
# 0xae3 := bra +1 only. 0xAE4..0xAE6 (the prompt call) stays STOCK this time.
REDIRECT_EDITS = [("0x6fff1", "0x04"), ("0x6fff3", "0xd7"), ("0x6fff5", "0x3b"),
                  ("0x6fff6", "0xe0"), ("0x6fff7", "0x01")]
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

# No lifted generator: the const pool supplies the nibbles.

# Band 0 holds the entry jump and the 2-word TaskData; the code proper starts in
# band 1, because the hook's prefix fold pins the entry address and cannot be
# retargeted (docs/cave-frame.md, docs/message-task-abi.md).
# No handler, so no TaskData and no entry jump: the hook's target is the first
# instruction, exactly as in the probes before 97.
CODE_AT = CAVE
assert blind(CODE_AT) and in_run(CODE_AT), hex(CODE_AT)

# The const pool, as a byte stream. const_addr maps code-word `a` to the data
# window; the pool begins immediately after the code, so its first word is at
# 0x7400 exactly. 17000 words = 34000 ADPCM samples = 4.25 s at 8000 Hz,
# measured offline at -0.9 dBFS with no quiet run over 17 samples.
LIFT = liftfn.lift('build/noiseprobe/noiseprobe', 'noise_fill')
assert not LIFT['problems'], LIFT['problems']
print('lifted noise_fill: %d words (the kalsim-verified leaky integrator)' % LIFT['size'])
CLAIM = 0x12E1A         # fn_12e1a(AL=sink, AH=count) -> pointer, or 0 if refused
NCLAIM = 256            # words to claim
NSAMP = 254             # leaving two frame slots for the generator state
NWORDS = 318            # matches the recompiled generator and the 318-word pmalloc block
POOL_PTR = 0x7400
POOL_LEN = 17000
assert POOL_PTR == ca.const_addr(236514), hex(ca.const_addr(236514))
# Stay inside the part of the const window PROVEN mapped at runtime: probes 99,
# 100 and 102 had the firmware read a TaskData as data at 0xBA3C, which is 17,980
# words past 0x7400. The section almost certainly runs to 0xD39A, but reading off
# the end of a mapped region is a way to wedge the VM for nothing.
assert POOL_PTR + POOL_LEN <= 0xBA3C, hex(POOL_PTR + POOL_LEN)

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))

BACK = 0xE06D          # the call the hook at 0xae0 displaced

W(0xF00B)                       # enterl -16  (slots 0..13 usable, 14/15 = link)
BSR(BACK)                       # stock back-call (proven by probe37)

# Arm the port-3 reader: codec_tones.asm:516 sets $aux_input_stream_available = 1
# inside this handler. 8000 Hz is the rate probe77 proved audible.
ca.calln(W, BSR, ca.STUB['KalimbaSendMessage'],
         al=('imm', 0x1072), ah=('imm', 8000),
         stack=[('imm', 0), ('imm', 0), ('imm', 0)], stage='AL')
W(0x0084); BR(0xF4, "R08")

ca.call1(W, BSR, ca.STUB['StreamKalimbaSink'], al=('imm', 3))
W(0x0A27)                       # st AL,@(10,Y)  ksink3
W(0x0084); BR(0xF4, "R12")

# THE MEASUREMENT. No heap: fn_12e1a claims space inside the sink's own buffer and
# returns a pointer, or 0 when SinkClaim gives 0xFFFF. probe122 proved malloc is the wall
# and that this port is live, so this is the question that decides the architecture.
ca.call2(W, BSR, CLAIM, al=('slot', 10), ah=('imm', NCLAIM))
W(0x0D27)                       # st AL,@(13,Y)  ptr
W(0x0084); BR(0xF4, "R16")      # 0 -> claim REFUSED -> its OWN id, 0x16 "english".
# NOT R12: that is probe104's StreamKalimbaSink bail, and letting both land on 0x12 would
# make "no port 3" and "claim refused" indistinguishable -- the one distinction this
# probe exists to draw.

# 16-bit PCM straight into the port. noise_fill is the leaky integrator with a one-pole
# high-pass, kalsim-verified and bit-exact on this hardware in probe81. Its two words of
# state live in frame slots 8 and 9, addressed with Bose's own idiom from 0x107f3.
W(0xE415)                       # ld AL,@0xffe4   AL = Y
W(0x0834)                       # add AL,#8       -> &slot 8
W(0x0727)                       # st AL,@(7,Y)
W(0x0014); W(0x0827); W(0x0927) # slots 8,9 = 0   (noise_fill seeds itself)
ca.calln(W, BSR, "NOISE", al=('slot', 13), ah=('imm', NSAMP),
         stack=[('slot', 7)], stage='AL')

ca.call2(W, BSR, ca.STUB['SinkFlush'], al=('slot', 10), ah=('imm', NCLAIM))
W(0x1314)                       # ld AL,#0x13 "voice prompts off" -- claim HONOURED

BR(0xE0, "EXIT")                # AL already holds 0x13 from the claim path
LBL("R06"); W(0x0614); BR(0xE0, "EXIT")   # 0x06 unused here (no malloc), kept harmless
LBL("R08"); W(0x0814); BR(0xE0, "EXIT")    # 0x08  "disconnected"
LBL("R12"); W(0x1214); BR(0xE0, "EXIT")    # 0x12  "voice prompts on" -- no port 3
LBL("R16"); W(0x1614); BR(0xE0, "EXIT")    # 0x16  "english" -- CLAIM REFUSED
LBL("R01"); W(0x0114); BR(0xE0, "EXIT")    # 0x01  "connecting to"
LBL("R0A"); W(0x0A14)                      # 0x0A  "connecting"
LBL("EXIT")
W(0xF00F)                       # leavel -16

W(0x0000); W(0x0000); W(0x0000); W(0x0000)                       # padding past the +-128 bsr encoding gap
LBL("NOISE")
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
        # Branches use the SAME last-word rule as bsr. Verified independently against
        # Bose's 2103 multi-word branches: a+ln-1+v lands on an instruction boundary
        # 100% of the time, a+v only 42% (chance).
        elif op in (0x20, 0x24, 0x28, 0x2C, 0xE0, 0xE4, 0xE8, 0xEC,
                    0xF0, 0xF4, 0xF8, 0xFC): seen[a] = (a + ln - 1 + v) & 0x3FFFF
for a, (tgt, kind) in intended.items():
    assert seen.get(a) == (tgt & 0x3FFFF), (hex(a), kind, hex(tgt), seen.get(a))
assert CODE_AT == CAVE   # no entry jump to verify in this probe
for i, item in enumerate(prog):
    if item[0] != "label":
        assert addrs[i] in dstarts, (hex(addrs[i]), "boundary")
print("decode-verify: all branches OK, boundaries OK")

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe123_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe123_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe123_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe123_cmd.txt")
