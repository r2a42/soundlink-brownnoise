#!/usr/bin/env python3
"""probe72: drop the leak. It holds the one encoding never seen from a compiler.

The eliminations, one press each:

    68  generation loop, writing through the malloc'd pointer      crash
    69  same loop, storing to a stack slot instead                 crash
        -> not the heap write; the MPU theory was wrong
    70  trivial countdown, 5-word body, no connector inside        WORKS
        -> backward branches in a cave are fine
    71  probe70's loop padded to a 65-word body with 36 non-blind
        words, so connectors are certainly inside it               WORKS
        -> connectors inside loops are fine too

So the fault is the generator's **arithmetic**, and one part of it stands out.
Every opcode in the LFSR half was read directly out of the compiler's own
`noise_fill` output (`build/convprobe/noise.s`): `0009 01A4` = `lsr #1`,
`01C4` = `and AL,#1`, `0074` = `nadd AL,#0`, `B400 00C4` = `and AL,#0xB400`,
`E1D1` = `xor AH,@$XAP_AL`, `nnA4` = `asr #n`.

The **leak** was added later by this project and never appeared in compiler
output:

    ld AH,@(7,Y)  ;  asr #8  ;  ld AL,@(7,Y)  ;  sub AL,@$XAP_AH  ;  st AL,@(7,Y)
                                                 ^^^^ 0xE055

`0xE055` is the only encoding in the loop derived from the structural rule
rather than observed. Asking the compiler for `acc - ((int16)acc >> 8)` gives
`ld X,@acc ; ld AH,@$XAP_UXL ; asr #8 ; sub X,@$XAP_AH` -- it puts the
accumulator in **X** and subtracts into X, never using the AL form.

This probe removes the five leak words and changes nothing else.

**And it may make a sound.** Without the leak the integrator is an unbounded
random walk, but it only wraps after about 40,000 samples, and this buffer is
128 -- so 128 valid brown-noise samples are still generated
(`docs/gain.md` for why the level is what it is).

    noise, then "connected to" -> the leak was the fault AND our samples reach
                                 the DSP. Re-add the leak using the compiler's
                                 X-register form.
    "connected to" alone       -> the leak was the fault; the DSP ignores port 0.
    a crash                    -> the LFSR half faults despite every opcode in
                                 it coming from compiler output. Bisect again:
                                 remove the `xor`, then the `nadd`.
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
# (the leak is removed: five words, incl. the unverified 0xE055)
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
W(0x051B)                       # ld X,@(5,Y)    p
W(0x0022)                       # st AH,@(0,X)   *p = acc
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

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe72_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe72_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe72_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe72_cmd.txt")
