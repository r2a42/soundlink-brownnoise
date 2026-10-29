#!/usr/bin/env python3
"""probe69: is it the arithmetic, or the write through malloc'd memory?

probe69 crashed, which was not expected: its only addition to probe67 was a
loop of pure arithmetic, no traps, no 32-bit carry arithmetic, no branch after
a call, and `tools/cavesim.py` reproduces its output against a Python model
sample for sample.

But the loop does do one thing nothing has ever done on this hardware:

    ld X,@(5,Y)        ; X = p, a pointer into the malloc'd block
    st AH,@(0,X)       ; *p = acc   <-- a WRITE THROUGH THAT POINTER

`malloc` returning non-null (probe61) and `StreamRegionSource` accepting the
block (probe62) both prove the *handle* is good. Neither proves the cave may
**write** there. The VM is an `-mpu` build -- memory-protected -- and the
hardware bug the compiler works around, B-96516, is an **MPU** bug
(`docs/adk-compiler.md`). A cave writing outside whatever region the MPU
grants it is exactly the shape of fault that would kill the firmware.

So this probe keeps the loop bit-for-bit and changes **only where it stores**:

    st AH,@(0,X)   ->   st AH,@(1,Y)

i.e. the same 128 iterations of the same arithmetic, writing to a **stack
slot** in the cave's own frame instead of through the heap pointer. Nothing
else differs from probe69.

    survives ("connected to") -> the arithmetic is fine and **writing through
                                 the malloc'd pointer is what faults**. That is
                                 an MPU finding, and it closes the last route:
                                 we can allocate memory and hand it to the
                                 stream subsystem but we cannot put samples in
                                 it, so a cave cannot generate audio at all.
    crashes                   -> the loop itself faults, and the suspects are
                                 the two opcodes no cave has ever executed:
                                 the 0x0009 shift modifier and `nadd` (0x0074).
                                 Bisect by removing the leak, then the LFSR.
"""
import sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca

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

W(0xF80B)                       # enterl -8
BSR(BACK)                       # stock back-call (proven by probe37)

# All proven: probe61, probe62, probe65.
ca.call1(W, BSR, ca.STUB['malloc'], al=('imm',128))
W(0x0327)                       # st AL,@(3,Y)  buf
W(0x0084); BR(0xF4, "NOMEM")
# The single new thing: fill that buffer with brown noise before wrapping it
# in a Source. Pure arithmetic -- no traps, no 32-bit carry arithmetic, and no
# conditional branch straight after a call, so neither hardware hazard applies.
W(0x0317); W(0x0527)            # p = buf
ca.load_al(W, ('imm',0xACE1)); W(0x0627)   # x   = 0xACE1
ca.load_al(W, ('imm',0));      W(0x0727)   # acc = 0
ca.load_al(W, ('imm',128));    W(0x0027)   # count = 128
LBL("LOOP")
W(0x0713)                       # ld AH,@(7,Y)   acc
W(0x08A4)                       # asr #8         acc>>8, sign-preserving
W(0x0717)                       # ld AL,@(7,Y)   acc
W(0xE055)                       # sub AL,@$XAP_AH   acc - (acc>>8)
W(0x0727)                       # st AL,@(7,Y)   the leak
W(0x0613)                       # ld AH,@(6,Y)   x
W(0x0009); W(0x01A4)            # lsr #1         x>>1, logical
W(0x0617)                       # ld AL,@(6,Y)
W(0x01C4)                       # and AL,#1
W(0x0074)                       # nadd AL,#0     -(x&1)
W(0xB400, 0x00C4)               # and AL,#0xb400
W(0xE1D1)                       # xor AH,@$XAP_AL   the LFSR step
W(0x0623)                       # st AH,@(6,Y)   x = new
W(0x04A4)                       # asr #4         (int16)x >> 4
W(0x0733)                       # add AH,@(7,Y)  acc += step
W(0x0723)                       # st AH,@(7,Y)
W(0x0123)                       # st AH,@(1,Y)   THE ONLY CHANGE: a stack slot,
                                #                not *p through the heap pointer
W(0x0517); W(0x0134); W(0x0527) # p++
W(0x0017); W(0xFF34); W(0x0027) # count--
W(0x0084)                       # cmp AL,#0
BR(0xF0, "LOOP")                # bne

ca.call2(W, BSR, ca.STUB['StreamRegionSource'], al=('slot',3), ah=('imm',128))
W(0x0427)                       # st AL,@(4,Y)  src
W(0x0084); BR(0xF4, "NULLSRC")
ca.call1(W, BSR, ca.STUB['StreamKalimbaSink'], al=('imm',0))
W(0x0227)                       # st AL,@(2,Y)  ksink
W(0x0084); BR(0xF4, "NULLSINK")

# The single new thing: the same StreamConnect, pointed at a DSP port
# instead of the codec sink probe63 died on.                [2-arg ABI]
ca.call2(W, BSR, ca.STUB['StreamConnect'], al=('slot',4), ah=('slot',2))
W(0x0084); BR(0xF4, "NOCONN")
W(0x0E14); BR(0xE0, "EXIT")     # ld AL,#0x0E  "connected to"
LBL("NOCONN");   W(0x0C14); BR(0xE0, "EXIT")   # ld AL,#0x0C  "connection lost"
LBL("NULLSRC");  W(0x0A14); BR(0xE0, "EXIT")   # ld AL,#0x0A  "connecting"
LBL("NOMEM");    W(0x0814); BR(0xE0, "EXIT")   # ld AL,#0x08  "disconnected"
LBL("NULLSINK"); W(0x0614)                     # ld AL,#0x06  "lost"
LBL("EXIT")
W(0xF80F)                       # leavel -8

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

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe69_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe69_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe69_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe69_cmd.txt")
