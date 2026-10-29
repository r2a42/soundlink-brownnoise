#!/usr/bin/env python3
"""probe95: StreamConnect(ksrc, dac) -- one call, the prime wedge suspect.

probe94 said **"connected to"** (2026-10-01, owner): every handle obtained,
`StreamSourceFromSink` included -- the only trap in the DSP recipe that had never
been called from a cave -- and no wedge.

So the elimination now reads:

    probe93   load sbc_decoder.kap                              clean
    probe94   + StreamAudioSink, SinkConfigure, StreamKalimbaSink,
                StreamSourceFromSink  (handles only, no state change)   clean
    probe91   + StreamConnect(ksrc,dac) + gain + unmute + 0x7000        WEDGE

**One change here: `StreamConnect(ksrc, dac)`.** Everything around it is known
good, so this is a genuine single-call test of the suspect that has been top of the
list since the incident -- the call that takes the DAC away from Bose's own audio
manager and points it at the DSP we loaded.

Gain, unmute and the `0x7000` "go" message stay out. If this is clean, probe96 adds
`0x7000` alone and the wedge is cornered either way.

## No sound is expected

The decoder has not been told to run, and nothing is feeding its tone port. This
probe is about the wedge and about whether the DSP's output can legally reach the
DAC from cave context -- not about audio.

`enterl -16`, slots 10-12, unchanged. **No music, nothing connected.** Prompt call
stock, so every path speaks.

    "connected to"   -> **the connect is survivable and returns a transform.** The
                        DSP's output is wired to the DAC by us. Then 0x7000 is the
                        only remaining wedge suspect, and probe96 adds it alone.
    "connected"      -> StreamConnect returned 0: refused, cleanly, no fault. Also
                        informative -- the route needs something else first.
    anything earlier -> a probe94 regression; the ids are unchanged.
    **a wedge**      -> **StreamConnect(ksrc, dac) is what wedged probe91.**
                        Rewiring the DAC behind the audio manager's back is not a
                        free action, and the DSP-to-DAC route needs the firmware's
                        cooperation rather than our own wiring. Recovery is not
                        characterised -- allow it time, and tell me what was done
                        rather than assuming a procedure.
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

# ---- THE CHANGE: obtain the handles the DSP-to-DAC wiring needs, and STOP.
# Nothing below alters any state: three handle fetches and a rate on a sink that
# nothing is connected to. StreamConnect and KalimbaSendMessage(0x7000) are the
# two remaining wedge suspects and are deliberately NOT here.
ca.call3(W, BSR, ca.STUB['StreamAudioSink'],
         al=('imm', 3), ah=('imm', 0), arg3=('imm', 2))   # channel 2, as the DSP path uses
W(0x0A27)                       # st AL,@(10,Y)  dac -- reuses f, now consumed
W(0x0084); BR(0xF4, "NODAC")
ca.call3_long(W, BSR, ca.STUB['SinkConfigure'],
              al=('slot', 10), ah=('imm', 0x0301), arg3_32=16000)

ca.call1(W, BSR, ca.STUB['StreamKalimbaSink'], al=('imm', 0))
W(0x0B27)                       # st AL,@(11,Y)  ksink0 -- reuses old
W(0x0084); BR(0xF4, "NOKSINK")

# The only trap in the whole DSP recipe never called from a cave.
ca.call1(W, BSR, ca.STUB['StreamSourceFromSink'], al=('slot', 11))
W(0x0C27)                       # st AL,@(12,Y)  ksrc -- reuses ok
W(0x0084); BR(0xF4, "NOKSRC")

# ---- THE ONE CHANGE: wire the DSP's output to the DAC. Nothing else is
# added -- no gain, no unmute, no KalimbaSendMessage(0x7000).
ca.call2(W, BSR, ca.STUB['StreamConnect'], al=('slot', 12), ah=('slot', 10))
W(0x0084); BR(0xF4, "NOCONN")

W(0x0E14); BR(0xE0, "EXIT")     # ld AL,#0x0E  "connected to"
LBL("NOCONN");   W(0x0414); BR(0xE0, "EXIT")   # 0x04  "connected"
LBL("NOKSRC");   W(0x0C14); BR(0xE0, "EXIT")   # 0x0C  "connection lost"
LBL("NOKSINK");  W(0x0114); BR(0xE0, "EXIT")   # 0x01  "connecting to"
LBL("NODAC");    W(0x0014); BR(0xE0, "EXIT")   # 0x00  "ready to connect"
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

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe95_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe95_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe95_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe95_cmd.txt")
