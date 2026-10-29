#!/usr/bin/env python3
"""probe83: does the DSP play PCM we wrote? One question, right instrument.

probe82 (2026-10-01, owner): **"disconnected"** with no music, **"connected to"**
with music, then stock behaviour on later presses. Two facts from that:

  * **the heap gives 512 words.** probe61 had only shown 128 works and 1024 does
    not; 512 is the first size the ladder tried and it succeeded. At 8 kHz that
    is 64 ms, and it sets the refill interval for sustain.
  * later presses said "ready to connect" because the first long-press put the
    speaker *into* pairing, so the guard at 0x0ACD takes a different branch and
    the cave is never reached. Nothing wrong.

**And no hiss was heard -- but probe82 could not have produced one.** The id was
spoken, which means the prompt engine ran, which means `KalimbaLoad` replaced the
`.kap` (probe76 proved that happens even for a silent id) and destroyed our
transform. A 64 ms buffer needed 64 ms of life and never got it. probe82 tested
the call chain, not the audio.

## So: delete the prompt, and ask with a square wave

64 ms of brown noise is perceptually soft; 64 ms of a 400 Hz square wave at
-1.4 dBFS is unmistakable. Using noise here would risk a third "not sure", which
is the one outcome worth engineering against.

`square_fill` is written in C beside `noise_fill` and lifted the same way, so
nothing is hand-assembled: 10 samples at +28000, 10 at -28000, a 20-sample period
= **400 Hz at 8 kHz**. `tools/liftfn.py` reports 35 words, no globals, all
branches internal.

    buf   = malloc(512 | 256 | 128)        512 now known to work
            square_fill(buf, n)            NEW, lifted from C
            KalimbaSendMessage(0x1072, 8000, 0, 0, 0)
    ksink = StreamKalimbaSink(3)
    src   = StreamRegionSource(buf, n)
    t     = StreamConnect(src, ksink)

**The prompt call at 0xAE4..0xAE6 is deleted** (three `nop`s, proven in probe77),
so nothing reloads the `.kap` and the buffer gets its full 64 ms. That also means
**no spoken diagnosis** -- accepted, because probe82 just confirmed every call in
this chain end to end.

    a short beep / click | **the DSP plays PCM we wrote.** The structure is
                         | finished and only sustain remains.
    silence              | the DSP does not consume a region source on port 3,
                         | even though it consumes a firmware ringtone there.
                         | That is a real finding and changes the plan: the next
                         | question becomes what the ringtone path does
                         | differently, not how to make our buffer longer.
    a crash              | the square-wave fill faults where noise_fill did not.

Needs music playing, because the DSP is only loaded for A2DP.
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
                  # 0xae4..0xae6 := nop,nop,nop -- delete `bsr 0xdf7f`, the
                  # prompt player, so nothing reloads the .kap under our audio.
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
LIFT = liftfn.lift('build/noiseprobe/noiseprobe', 'square_fill')
assert not LIFT['problems'], LIFT['problems']
print('lifted square_fill: %d words, %d items, %d labels'
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

# Heap ladder. probe82 established 512 works; keep the fallbacks anyway.
ca.call1(W, BSR, ca.STUB['malloc'], al=('imm', 512))
W(0x0A27)                       # st AL,@(10,Y)  buf
W(0x0084); BR(0xF0, "GOT512")
ca.call1(W, BSR, ca.STUB['malloc'], al=('imm', 256))
W(0x0A27)
W(0x0084); BR(0xF0, "GOT256")
ca.call1(W, BSR, ca.STUB['malloc'], al=('imm', 128))
W(0x0A27)
W(0x0084); BR(0xF4, "NOMEM")
ca.load_al(W, ('imm', 128)); W(0x0C27)
BR(0xE0, "HAVE")
LBL("GOT256")
ca.load_al(W, ('imm', 256)); W(0x0C27)
BR(0xE0, "HAVE")
LBL("GOT512")
ca.load_al(W, ('imm', 512)); W(0x0C27)
LBL("HAVE")

# The one new thing: square_fill(buf, n), lifted from C. Two arguments only,
# so there is no carried state and nothing to seed.
ca.call2(W, BSR, "SQUARE", al=('slot', 10), ah=('slot', 12))

ca.calln(W, BSR, ca.STUB['KalimbaSendMessage'],
         al=('imm', 0x1072), ah=('imm', 8000),
         stack=[('imm', 0), ('imm', 0), ('imm', 0)], stage='AL')
W(0x0084); BR(0xF4, "EXIT")

ca.call1(W, BSR, ca.STUB['StreamKalimbaSink'], al=('imm', 3))
W(0x0527)                       # st AL,@(5,Y)  ksink
W(0x0084); BR(0xF4, "EXIT")

ca.call2(W, BSR, ca.STUB['StreamRegionSource'], al=('slot', 10), ah=('slot', 12))
W(0x0427)                       # st AL,@(4,Y)  src
W(0x0084); BR(0xF4, "EXIT")

ca.call2(W, BSR, ca.STUB['StreamConnect'], al=('slot', 4), ah=('slot', 5))
LBL("NOMEM")
LBL("EXIT")
W(0xF00F)                       # leavel -16

BR(0xE0, "DONE")                # jump over the lifted function
# One unreachable `nop` of padding. A `bsr` of exactly +-128 words cannot be
# encoded at all: the 1-word form reaches +-127, and a 2-word form needs a
# NON-ZERO prefix byte, so its smallest magnitude is 129. Shifting the callee
# one word past the gap is the cheapest fix, and this nop sits immediately
# after the `bra` above, so it never executes.
W(0x0000)
LBL("SQUARE")
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
        # Branch relaxation must only ever WIDEN. Letting a branch shrink again
        # makes the layout oscillate -- probe83's lifted square_fill has five
        # labels and did not converge in 24 passes until this was monotonic.
        if item[0] == "bsr":
            v = tgt - a
            want = 1 if -126 <= v <= 126 else 2 if bsr2_encodable(v - 1) else 3 if bsr3_encodable(v - 2) else 0
            if want > bsr_size.get(i, 2): bsr_size[i] = want; ok = False
        else:
            want = 1 if -128 <= tgt - a <= 127 else 2
            if want > br_size.get(i, 1): br_size[i] = want; ok = False
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

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe83_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe83_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe83_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe83_cmd.txt")
