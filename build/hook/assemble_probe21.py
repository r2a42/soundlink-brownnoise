#!/usr/bin/env python3
"""probe21: probe20 + LOUDNESS ATTACK.
probe20 field: connect WORKS (quiet hiss = our notes reaching the DSP!);
cutout = 0x4757 watchdog. Loudness levers stacked here:
  1. Stream control words: VOLUME 0xA0FF (255), TIMBRE 0xB002 (saw),
     TEMPO 0x90F0 prepended to the burst (probe20 fed bare notes).
  2. DSP gain message: KalimbaSendMessage(0x10a9 MUSIC_VOLUME_MSG_S,
     0, system, master, tone) with max fields — the standard gain msg
     the ADK setVolume() sends (Bose app may honor it).

probe19 showed raw writes into an unconnected Kalimba sink are silent —
no stream exists. This probe makes the real connection, combining the
two proven pieces:
  - StreamRingtoneSource(3) + StreamConfigure(0x30b) + StreamSinkFromSource
    = the tone generator (0x4946's exact sequence, field-proven audible)
  - StreamKalimbaSink(3) + StreamConnect(src, ksink)
    = the ADK's raw-PCM-into-engine pattern (port 3 = TONE_VP_MIXING)
Then feeds 32 note words (82/165 Hz quavers) into the source's feed sink.
If the connect works, the notes play through the DSP at ENGINE volume —
the cave exits to the stock chirp flow as usual (probe10-clone-proven).

Frame map (enterl -12; cave slot n = dispatcher slot n+8):
  0/1 ksink  2/3 src  4/5 feed  6/7 scratch  8 offset  9 counter  10 free
"""
import sys, json, subprocess

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

TONE = 0x4946          # not used; we replicate its sequence
RSRC, SCONFIG, SFROMS = 0x162, 0x11A, 0x12A
KSINK, SCONN = 0x1BE, 0x106
KMSEND = 0x1CD
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
W(0x0014)                       # ld AL,#0
BSR(TONE)                       # beep (cave-ran marker)
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
# ksink = StreamKalimbaSink(3)
W(0x0314, 0x0010)               # AL=3 ; AH=0
BSR(KSINK)
W(0x0023, 0x0127)               # ksink -> @(0,Y)/@(1,Y)
W(0x0084)
BR(0xF0, "CONN")                # nonzero -> connect
BR(0xE0, "EXIT")                # null ksink -> out
# StreamConnect(src, ksink): AH:AL = src, sink in @(0,Y):@(1,Y)
LBL("CONN")
W(0x0213, 0x0317)               # AH=src hi(@2), AL=src lo(@3) (un-swapped)
BSR(SCONN)
W(0x0084)
BR(0xF0, "FEED")                # connect TRUE≠0 -> feed (bne; beq was inverted)
# connect returned 0 -> treat as fail: second beep telemetry
W(0x0014)
BSR(TONE)
BR(0xE0, "EXIT")
# ---- FEED: claim 64, write 3 control words + 29 notes, flush 64 ----
LBL("FEED")
# ---- DSP gain: KalimbaSendMessage(0x10a9, 0, 0xffff, 0xffff, 0xffff) ----
# arg packing per 0x30010 site: AL = msg args ptr?? actually KalimbaSendMessage(id=AL?, ...) --
# trap 0x1cd convention (from 0x1c2fa caller): AL = first arg, AH = ??? copy pattern:
# 0x1c2ef: AL=0x6c4 ptr+4; AH=0x8024; 0x395e7(task=AL,id=AH) cancel; then AL=same; bsr 0x1cd
# => KalimbaSendMessage(AL=first_param, AH=id); params 2..5 in @(0..3,Y)? probe: id in AH.
W(0x0214, 0x0027)               # @(0,Y) = 2   (tone gain slot per ADK: msg id 0 = {system,master,tone})
W(0xFF14, 0x0127)               # ld AL,#-1 (=0xffff) ; @(1,Y) (0xFFFF bare = op 0xFF!)
W(0x1014, 0x0227)               # @(2,Y) = 0x10 (16 params? filler)
W(0x0014, 0x0327)               # @(3,Y) = 0
W(0x1100, 0xA910, 0x0014)       # ld AH,#0x10a9 (id) ; ld AL,#0 (param1)
BSR(KMSEND)
W(0x4014, 0x0027)               # claim size 64 -> @(0,Y)
W(0x0014, 0x0127)
W(0x0413, 0x0517)               # AH=hi@(4,Y), AL=lo@(5,Y) (un-swapped)               # AH:AL = feed
BSR(CLAIM)
W(0x0827)                       # offset -> @(8,Y)
W(0xFF84)
BR(0xF0, "MAPIT")               # bne: offset != -1 -> map (was inverted beq)
BR(0xE0, "EXIT")                # claim failed -> out
LBL("MAPIT")
W(0x0817, 0x0027)               # @(0,Y) = offset
W(0x0014, 0x0127)
W(0x0413, 0x0517)               # AH=hi@(4,Y), AL=lo@(5,Y) (un-swapped)               # feed
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
# control words first: VOLUME 255, TIMBRE saw, TEMPO 240
# (0xA0FF = prefix 0xA1 (-95<<8) + byte 0xFF (-1); 0xB102 = 0xB1<<8 + 2;
#  0x90F0 = 0x91<<8 + sext(0xF0)=-16)
# 0xA0FF = -0x5F01 signed16... as unsigned immediate: prefix a=0xA1(161): 161*256=41216; b=0xA0FF-41216=25471 no.
# imm must satisfy v = a*256 + sext(b): 0xA0FF as SIGNED = -24321: a=-96(0xA0): -24576; b=255(0xFF->-1)=-1: -24577 no;
# a=-95: -24320; b=-1: -24321 = sext16(-24321)=0xA0FF ✓. so prefix 0xA100, word 0xFF14.
W(0xA100, 0xFF14, 0x0026, 0x0138)   # VOLUME 255
W(0xB100, 0x0214, 0x0026, 0x0138)   # TIMBRE 0xB002: prefix 0xB1(177*256=45312); b=0x02-... 45312+2=45314=0xB102 ✓
W(0x9100, 0xF014, 0x0026, 0x0138)   # TEMPO 0x90F0: prefix 0x91(145*256=37120); b=0xF0=-16: 37104=0x90F0 ✓
LBL("NOTE")
W(0x1100, 0x8814)               # ld AL,#0x1088 (82 Hz quaver)
W(0x0026, 0x0138)               # st, X++
W(0x1500, 0x0814)               # ld AL,#0x1508
W(0x0026, 0x0138)
W(0x0A17, 0xFF34, 0x0A27)       # counter--
W(0x0084)
BR(0xF0, "NOTE")
W(0x4014, 0x0027)               # flush 64
W(0x0014, 0x0127)
W(0x0413, 0x0517)               # AH=hi@(4,Y), AL=lo@(5,Y) (un-swapped)
BSR(FLUSH)
LBL("EXIT")
W(0x0C3C)                       # add Y,#12
W(0x00E2)                       # rts -> stock 0xae3

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

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe21_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe21_loud.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe21_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe21_cmd.txt")
