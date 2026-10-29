#!/usr/bin/env python3
"""probe54: write to the DAC -- with probe53's pointer bug fixed.

probe53 played id 0x00 ("ready to connect") instead of the 0x16 its EXIT
sets, which means the return value was corrupted. Cause found by decoding
the emitted cave:

    0x3e260: e139   add X,@0xffe1        <- NOT "add X,AL"

`W(0xE139)` was inherited from probe39 with the comment "X = map +
offset", but it actually adds the contents of **MMIO address 0xFFE1** to
X. So the write pointer became `base + <arbitrary>` and sixteen stores
landed somewhere unintended -- enough to corrupt the frame and the
returned id. probe53 taught nothing about the DAC; it only found a bug.

Two fixes:

  1. **Drop the offset arithmetic entirely.** Write at the mapped base.
     SinkClaim's offset is still requested (so the buffer is reserved) but
     not used as a displacement, removing the broken instruction.
  2. **Real amplitude.** probe53 wrote 0x0030 / 0xFFD0 -- about 0.1% of
     full scale, inaudible even if everything else had worked. Now
     +/-0x1000.

Also removes a stray `ld X,@(0,Y)` placeholder left in probe53.

  audible buzz -> the VM writes samples to the codec; brown noise is then
                  just an LFSR fill instead of a square wave.
  silence      -> sink opens, writes accepted, but Bose's DSP owns the
                  codec output.
  crash        -> SinkClaim/SinkMap convention is wrong.
"""
import sys, json, subprocess

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

TONE = 0x4946
CAVE = 0x3E21D
REDIRECT_EDITS = [("0x6fff1", "0x04"), ("0x6fff3", "0xd7"), ("0x6fff5", "0x3b"),
                  ("0x6fff6", "0xe0"), ("0x6fff7", "0x01")]   # 0xae3 := bra +1 (word 0x01e0, no-op)
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
assert tt.get(stubs[TONE]) == "StreamRingtoneSource" if TONE in stubs else True  # 0x4946 is a real function, not a stub

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))

BACK = 0xE06D          # the call the hook at 0xae0 displaced

DACSINK = 0x16A                 # StreamAudioSink stub (trap 0x6e)

W(0xFA0B)                       # enterl -6
BSR(BACK)                       # stock back-call FIRST (proven)
W(0x0014)                       # ld AL,#0
W(0x0027)                       # st AL,@(0,Y)   AUDIO_CHANNEL_A   (arg3)
W(0x0314)                       # ld AL,#3       AUDIO_HARDWARE_CODEC (arg1)
W(0x0010)                       # ld AH,#0       AUDIO_INSTANCE_0  (arg2)
BSR(DACSINK)                    # StreamAudioSink(...)   ** the one new thing **
W(0x0227)                       # st AL,@(2,Y)   the Sink (returned in AL)
W(0x0084)                       # cmp AL,#0
BR(0xF4, "EXIT")                # no sink -> bail
W(0x0217)                       # ld AL,@(2,Y)   dac
W(0x2010)                       # ld AH,#0x20    32 words
BSR(0x0DE)                      # SinkClaim (reserve the buffer)
W(0x0217)                       # ld AL,@(2,Y)
BSR(0x0E2)                      # SinkMap -> AL = base
W(0x0427)                       # st AL,@(4,Y)
W(0x041B)                       # ld X,@(4,Y)    write pointer = base
W(0x1000, 0x0014)               # ld AL,#0x1000  (+ swing)
W(0x0026)
W(0x0138)
W(0x0026)
W(0x0138)
W(0x0026)
W(0x0138)
W(0x0026)
W(0x0138)
W(0x0026)
W(0x0138)
W(0x0026)
W(0x0138)
W(0x0026)
W(0x0138)
W(0x0026)
W(0x0138)
W(0xF000, 0x0014)               # ld AL,#0xf000  (- swing)
W(0x0026)
W(0x0138)
W(0x0026)
W(0x0138)
W(0x0026)
W(0x0138)
W(0x0026)
W(0x0138)
W(0x0026)
W(0x0138)
W(0x0026)
W(0x0138)
W(0x0026)
W(0x0138)
W(0x0026)
W(0x0138)
W(0x0217)                       # ld AL,@(2,Y)
W(0x2010)                       # ld AH,#0x20
BSR(0x0E6)                      # SinkFlush
LBL("EXIT")
W(0x1614)                       # ld AL,#0x16   <- id left in the return register
W(0xFA0F)                       # leavel -6 -> returns to 0xae3 with AL = id

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

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe54_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe54_write.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe54_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe22_cmd.txt")
