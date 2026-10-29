#!/usr/bin/env python3
"""probe39: audio injection into BOSE'S OWN Kalimba port (0xfffb), on the
Bluetooth button, with the proven epilogue.

Rebuilt from probe20's recipe with three deliberate changes:

  1. **Port 0xfffb instead of 3.** StreamKalimbaSink's 8 call sites show
     Bose's loud prompt path passing NEGATIVE ports -- `ld AL,#0xfffc` /
     `#0xfffb` at 0x1CAA6, right beside the prompt DSP setup. probe19/20
     only ever scanned ports 0..7, so the ports Bose's own full-volume
     audio uses were never tried. 0xfffb encodes as the one-word
     immediate -5 (0xFB14).
  2. **`leavel -12` epilogue instead of `add Y,#12 ; rts`.** probe20's
     return was never verified; probe29 and probe37 proved enterl/leavel
     returns correctly from this cave. probe20's epilogue is a prime
     suspect for why that era's results were unreliable.
  3. **The opening 0x4946 "marker" call is removed.** It is inaudible
     (the 0x30b tone route bypasses the DSP), and it opens a ringtone
     source that competes with the one this cave then opens itself.

0xAE3 is left STOCK, so the ordinary prompt still plays after the cave
returns -- a free "the cave returned cleanly" witness.

Trap calls from a cave are safe (probe21 did them without crashing);
only calling the request API from a cave crashes (probes 30/34/35). This
cave calls traps only.

  loud tone  -> the negative port reaches the full-scale mix. The
                loudness problem is SOLVED and only the waveform remains.
  quiet tone -> injection works but is attenuated; the gain problem is
                real and lives inside a .kap.
  prompt only-> injection produced nothing; the connect chain failed.
  no prompt  -> the cave did not return; epilogue or frame problem.

NOTE: the fed words are ringtone NOTE words, not PCM -- the ringtone
source synthesises tones from them. This probe answers the LOUDNESS
question only; a PCM-capable source is a separate step.
"""
import sys, json, subprocess

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

TONE = 0x4946          # not used; we replicate its sequence
RSRC, SCONFIG, SFROMS = 0x162, 0x11A, 0x12A
KSINK, SCONN = 0x1BE, 0x106
CLAIM, MAP, FLUSH = 0x0DE, 0x0E2, 0xE6
CAVE = 0x3E21D
REDIRECT_EDITS = [("0x6fff1", "0x04"), ("0x6fff3", "0xd7"), ("0x6fff5", "0x3b")]
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
for a, n in ((RSRC, "StreamRingtoneSource"), (SCONFIG, "StreamConfigure"),
             (SFROMS, "StreamSinkFromSource"), (KSINK, "StreamKalimbaSink"),
             (SCONN, "StreamConnect"), (CLAIM, "SinkClaim"), (MAP, "SinkMap"),
             (FLUSH, "SinkFlush")):
    assert tt.get(stubs[a]) == n, (hex(a), tt.get(stubs[a]))
print("stubs verified")

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))

W(0xF40B)                       # enterl -12 (0xF4 = -12 signed; 0xEC would be -20!)
# src = StreamRingtoneSource(3) with @(0,Y)=2 (0x4946's exact packing)
W(0x0214, 0x0027)               # ld AL,#2 ; @(0,Y)
W(0x0314, 0x0010)               # ld AL,#3 ; AH=0
BSR(RSRC)
W(0x0223, 0x0327)               # src -> @(2,Y)/@(3,Y)
W(0x0084)
BR(0xF4, "EXIT")                # no source -> out
# StreamConfigure(0x30b, src)
W(0x0217)                       # AL = src lo
W(0x3000, 0x0B10)               # AH = 0x30b
BSR(SCONFIG)
# feed = StreamSinkFromSource(src)
W(0x0217)                       # AL = src lo
W(0x0010)                       # AH = 0
BSR(SFROMS)
W(0x0423, 0x0527)               # feed -> @(4,Y)/@(5,Y)
W(0x0084)
BR(0xF4, "EXIT")
# ksink = StreamKalimbaSink(0xfffb)  <- Bose's own loud-path port
W(0xFB14, 0x0010)               # AL=0xfffb (immediate -5) ; AH=0
BSR(KSINK)
W(0x0023, 0x0127)               # ksink -> @(0,Y)/@(1,Y)
W(0x0084)
BR(0xF0, "CONN")                # nonzero -> connect
BR(0xE0, "EXIT")                # null ksink -> out
# StreamConnect(src, ksink): AH:AL = src, sink in @(0,Y):@(1,Y)
LBL("CONN")
W(0x0217, 0x0313)               # AL=src lo, AH=src hi
BSR(SCONN)
W(0x0084)
BR(0xF0, "FEED")                # connect TRUE≠0 -> feed (bne; beq was inverted)
# connect returned 0 -> treat as fail: second beep telemetry
W(0x0014)
BSR(TONE)
BR(0xE0, "EXIT")
# ---- FEED: claim 64, write 32 notes, flush 64 ----
LBL("FEED")
W(0x4014, 0x0027)               # claim size 64 -> @(0,Y)
W(0x0014, 0x0127)
W(0x0417, 0x0513)               # AH:AL = feed
BSR(CLAIM)
W(0x0827)                       # offset -> @(8,Y)
W(0xFF84)
BR(0xF0, "MAPIT")               # bne: offset != -1 -> map (was inverted beq)
BR(0xE0, "EXIT")                # claim failed -> out
LBL("MAPIT")
W(0x0817, 0x0027)               # @(0,Y) = offset
W(0x0014, 0x0127)
W(0x0417, 0x0513)               # feed
BSR(MAP)
W(0x0927)                       # map lo -> @(9,Y)
W(0x0084)
BR(0xF0, "WRITE")               # nonzero -> write
BR(0xE0, "EXIT")                # null map -> out
LBL("WRITE")
W(0x091B)                       # X = map
W(0x0817)                       # AL = offset
W(0xE139)                       # X = map + offset
W(0x1014, 0x0A27)               # counter 16 -> @(10,Y)
LBL("NOTE")
W(0x1100, 0x8814)               # ld AL,#0x1088 (82 Hz quaver)
W(0x0026, 0x0138)               # st, X++
W(0x1500, 0x0814)               # ld AL,#0x1508 (42.5 Hz-ish quaver... keep pair)
W(0x0026, 0x0138)
W(0x0A17, 0xFF34, 0x0A27)       # counter--
W(0x0084)
BR(0xF0, "NOTE")
W(0x4014, 0x0027)               # flush 64
W(0x0014, 0x0127)
W(0x0417, 0x0513)
BSR(FLUSH)
LBL("EXIT")
W(0xF40F)                       # leavel -12  (proven epilogue: probe29/37)

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

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe39_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe39_negport.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe39_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe39_cmd.txt")
