#!/usr/bin/env python3
"""probe93: probe85 with ONE WORD changed -- the .kap it loads.

The owner's instruction: *change only one thing after the last firmware that did
not wedge.*

**Strictly, that firmware is probe90, not probe85**, and the owner was right to
question it. The record: probes 86, 88, 89 and 90 were all pressed and all
survived; 91 is the only one that wedged.

    probe86   silence, no crash          codec route
    probe88   silent                     codec route
    probe89   "connected to", no tone    codec route
    probe90   silence, no crash          codec route   <- last non-wedging firmware
    probe91   WEDGE                      DSP route

But **probe90 is on the direct-to-codec route, and that route is closed**: probe89
showed every call in it succeeds, probe90 showed it still makes no sound with
nothing able to steal the DAC. One change from probe90 would be one change along a
path already measured as inert.

So the baseline here is **probe85 -- the last non-wedging firmware on the DSP
route**, which is the route still open. It loads a `.kap` from a cave with no music
playing and speaks an id, and it is on the speaker now. That choice is a judgement,
not what the instruction literally said, and it is stated here so it can be
overruled: a one-change-from-probe90 probe is buildable, it just tests a dead
route.

**The one change is the filename argument to `FileFind`:**

    probe85:  FileFind(FILE_ROOT, 0xB3D2, 27)   'NowSpeakTTS/NowSpeakTTS.kap'
    probe93:  FileFind(FILE_ROOT, 0xBD75, 27)   'sbc_decoder/sbc_decoder.kap'

Both strings are **27 characters**, so even the length argument is untouched. Every
other word of the cave is identical.

## Why this is the right single change

Two reasons, and they coincide.

**It is on the critical path.** probe75/77 made sound with `sbc_decoder.kap`
loaded -- by A2DP, not by us -- and it is the *decoder* that mixes
`TONE_VP_MIXING_DSP_PORT`. probe85 loaded `NowSpeakTTS.kap`, which may not mix
port 3 at all. Nothing downstream is worth building until the right `.kap` is
known to load.

**It bisects the wedge.** probe91 was load-the-decoder **plus** rewire the DAC
**plus** `KalimbaSendMessage(0x7000)`, and it wedged the VM application. probe85
was load-the-TTS-kap and was fine. Those differ in three ways at once. This
isolates the first: **if loading `sbc_decoder.kap` alone wedges the speaker, the
load is the problem and the wiring is innocent.** If it is fine, the wiring is
next, one call at a time.

Nothing about the probe91 incident is settled -- see `docs/field-log.md`; two
causal claims from it have already been retracted, and probe85-vs-probe91 is one
press each. This probe is the cheapest way to turn that into a measurement.

## The chain, unchanged from probe85 apart from that word

    f   = FileFind(FILE_ROOT, 0xBD75, 27)      <- the only change
    old = VmDeepSleepEnable(0)
    ok  = KalimbaLoad(f)
          VmDeepSleepEnable(old)
    ok2 = KalimbaSendMessage(0x1072, 2000, 0, 0, 0)

`KalimbaSendMessage` is still the measurement: it only succeeds with a `.kap`
loaded. `enterl -16`, slots 10-12, well inside the 262 words of headroom
`tools/stackdepth.py` reports at this hook.

**No music, nothing connected.** Prompt call stock, so every path speaks.

    "connected to"   -> **`sbc_decoder.kap` loads from a cave and the DSP
                        answers.** The right .kap is ours on demand, and the
                        wiring becomes the next single change.
    "connecting"     -> it loaded but SET_TONE_RATE was refused -- the decoder may
                        need configuring before it accepts messages.
    "disconnected"   -> KalimbaLoad refused the decoder, where it accepted the TTS
                        .kap. A real difference between the two, cleanly located.
    "lost"           -> FileFind did not find it, which would be surprising: the
                        name is Bose's own const string and 27 chars like the other.
    a wedge          -> **loading the decoder is what wedged probe91**, and the
                        wiring is innocent. Recovery: see docs/field-log.md; the
                        procedure is not characterised, so allow it time.
"""

import sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca

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


prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))

BACK = 0xE06D          # the call the hook at 0xae0 displaced

W(0xF00B)                       # enterl -16  (slots 0..13 usable, 14/15 = link)
BSR(BACK)                       # stock back-call (proven by probe37)

# THE ONE CHANGE: 0xBD75 'sbc_decoder/sbc_decoder.kap' instead of 0xB3D2
# 'NowSpeakTTS/NowSpeakTTS.kap'. Both are 27 chars, so arg3 is untouched too.
ca.call3(W, BSR, ca.STUB['FileFind'],
         al=('imm', 1), ah=('imm', 0xBD75), arg3=('imm', 27))
W(0x0A27)                       # st AL,@(10,Y)  f
W(0x0084); BR(0xF4, "NOFILE")

# VmDeepSleepEnable(0) brackets the load, exactly as 0x1E3FE/0x1E408 do.
ca.call1(W, BSR, ca.STUB['VmDeepSleepEnable'], al=('imm', 0))
W(0x0B27)                       # st AL,@(11,Y)  old

ca.call1(W, BSR, ca.STUB['KalimbaLoad'], al=('slot', 10))
W(0x0C27)                       # st AL,@(12,Y)  ok

ca.call1(W, BSR, ca.STUB['VmDeepSleepEnable'], al=('slot', 11))

W(0x0C17)                       # ld AL,@(12,Y)
W(0x0084); BR(0xF4, "NOLOAD")

# The measurement: this can only succeed if a .kap is loaded, and probe75 showed
# it returns FALSE with no music. TRUE here means the cave owns the DSP.
ca.calln(W, BSR, ca.STUB['KalimbaSendMessage'],
         al=('imm', 0x1072), ah=('imm', 2000),
         stack=[('imm', 0), ('imm', 0), ('imm', 0)], stage='AL')
W(0x0084); BR(0xF4, "NODSP")

W(0x0E14); BR(0xE0, "EXIT")     # ld AL,#0x0E  "connected to"
LBL("NODSP");    W(0x0A14); BR(0xE0, "EXIT")   # 0x0A  "connecting"
LBL("NOLOAD");   W(0x0814); BR(0xE0, "EXIT")   # 0x08  "disconnected"
LBL("NOFILE");   W(0x0614)                     # 0x06  "lost"
LBL("EXIT")
W(0xF00F)                       # leavel -16

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

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe93_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe93_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe93_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe93_cmd.txt")
