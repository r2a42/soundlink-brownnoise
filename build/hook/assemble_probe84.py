#!/usr/bin/env python3
"""probe84: the same PCM test, long enough to be unmistakable.

probe83 (2026-10-01, owner): *"I'm not sure. Would it work only once? If I heard
anything it was very very short."*

Both halves of that are correct and both are answerable. **Yes, once per press**
-- one press fills one buffer and plays it once, and later presses do not reach
the cave at all because the first long-press puts the speaker into pairing, after
which the guard at 0x0ACD takes a different branch (seen in probe82). And **64 ms
is very very short** -- that is what 512 words at 8 kHz is. Asking anyone to
judge 64 ms was the wrong experiment, twice.

So this probe makes the sound 4x longer and keeps the pitch sensible, without
touching the chain that probe82 already verified end to end.

## Stretching it

The DSP's tone rate is a **free parameter**. In the ADK, `playback_rate` is read
straight out of a prompt file's header (`voice_prompt_file.c:52`,
`rx_array[10] << 8 | rx_array[11]`) and defaults to 8000 only when the file says
zero. It is an arbitrary 16-bit value the DSP resamples from, not an enum, so
there is no reason a lower rate should be refused.

    tone rate 8000 -> 512 samples = 64 ms      (probe83)
    tone rate 2000 -> 512 samples = 256 ms     (this probe)

`square_fill` now takes its half-period as an argument, so the pitch can follow
the rate without recompiling: **half = 2** gives a 4-sample period, which at a
2000 Hz tone rate is **500 Hz** -- a comfortable pitch for this speaker, at
-1.4 dBFS.

**The result is informative either way.** If the DSP honours 2000, that is 256 ms
of a loud 500 Hz square wave. If it clamps to 8000, it is 64 ms of 2000 Hz
instead -- a shorter, higher beep. Both are audible; only silence is not.

    buf   = malloc(512 | 256 | 128)
            square_fill(buf, n, 2)             lifted from C, 37 words
            KalimbaSendMessage(0x1072, 2000, 0, 0, 0)
    ksink = StreamKalimbaSink(3)
    src   = StreamRegionSource(buf, n)
    t     = StreamConnect(src, ksink)

Prompt call still deleted, so nothing reloads the `.kap` and there is no spoken
diagnosis. Needs music playing.

    a clear beep or buzz | **the DSP plays PCM we wrote.** Structure finished;
                         | only sustain remains, and that is the deliverable.
    silence              | the DSP will not consume a region source on port 3
                         | even though it consumes a firmware ringtone there.
                         | The next question becomes what the ringtone path does
                         | differently -- not how to lengthen our buffer again.
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
ca.calln(W, BSR, "SQUARE", al=('slot', 10), ah=('slot', 12),
         stack=[('imm', 2)], stage='AL')   # half-period 2 -> 500 Hz at 2 kHz

ca.calln(W, BSR, ca.STUB['KalimbaSendMessage'],
         al=('imm', 0x1072), ah=('imm', 2000),   # 4x longer than 8000
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
            # The 1-word form's fold is sext8(operand), so its true reach is
            # -128..127. The old -126..126 bound was over-conservative and
            # created FALSE unencodable gaps at +-127 -- probe84 hit one at
            # distance 127. decode-verify below re-decodes the patched image and
            # asserts every target, so widening this is self-checking.
            want = 1 if -128 <= v <= 127 else 2 if bsr2_encodable(v - 1) else 3 if bsr3_encodable(v - 2) else 0
            if want > bsr_size.get(i, 2): bsr_size[i] = want; ok = False
        else:
            want = 1 if -128 <= tgt - a <= 127 else 2
            if want > br_size.get(i, 1): br_size[i] = want; ok = False
    if ok: break
else:
    raise SystemExit("no converge")

out = {}
# When a bsr is emitted in the padded form, the bsr word is not at the item's
# own address; decode-verify has to look where the instruction actually starts.
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
                # A 2-word `bsr` cannot express a SHORT distance: both prefix
                # bytes must be non-zero, so its smallest magnitude is 129.
                # Branch relaxation only widens (to stop it oscillating), so a
                # slot sized at 2 can end up holding a distance the 2-word form
                # cannot reach. Pad with a `nop` and use the 1-word form -- the
                # bsr's last word is then a+1, so the fold is tgt-(a+1).
                v1 = tgt - (a + 1)
                assert -128 <= v1 <= 127, (hex(a), hex(tgt), v1)
                out[a] = 0x0000                      # nop (operand 0 = not a prefix)
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
                # Same fallback one size up: two `nop`s and a 1-word bsr.
                v1 = tgt - (a + 2)
                assert -128 <= v1 <= 127, (hex(a), hex(tgt), v1)
                out[a] = 0x0000
                out[a+1] = 0x0000
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
    at = bsr_at.get(a, a)
    assert seen.get(at) == (tgt & 0x3FFFF), (hex(a), kind, hex(tgt), seen.get(at))
for i, item in enumerate(prog):
    if item[0] != "label":
        assert addrs[i] in dstarts, (hex(addrs[i]), "boundary")
print("decode-verify: all branches OK, boundaries OK")

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe84_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe84_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe84_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe84_cmd.txt")
