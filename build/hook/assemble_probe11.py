#!/usr/bin/env python3
"""Assemble the probe11 cave (band-wise across blind windows)."""
import sys
sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

SRS, SCFG, SSFS, UR, TONE = 0x162, 0x11A, 0x12A, 0x05E, 0x4946
FLAG, FEED, SEED = 0x808, 0x809, 0x810
CAVE = 0x3E21D

w = xapvm.load_words("firmware/bose/extracted/internal_fs/vm.app")
code = w[0x18:]
C0 = (0x6e974 + 0x34) % 64
def blind(cw): return 34 <= (2*cw + C0) % 64 <= 60   # both bytes must be writable
def next_blind(pc):
    while not blind(pc) or not in_run(pc): pc += 1
    return pc
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
print("zero runs:", [(hex(a), hex(b), b-a) for a, b in _runs])
def in_run(cw): return any(a <= cw < b for a, b in _runs)

# ---- program: entries (kind, payload); 'w' payload = ATOMIC word list ----
prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BNE(lbl): prog.append(("bne", lbl))
def BRA(lbl): prog.append(("bra", lbl))
def LBL(n): prog.append(("label", n))

W(0xFA0B)                       # enterl -6
W(0x0800, 0x0815)               # ld AL,@FLAG
W(0x0134)                       # xor AL,#1
W(0x0800, 0x0825)               # st AL,@FLAG
W(0x0527)                       # st AL,@(5,Y)
W(0x0184)                       # cmp AL,#1
BNE("SKIPOP")
W(0x0014)                       # ld AL,#0
BSR(TONE)                       # beep
BSR("BODY")                     # start rumble
LBL("SKIPOP")
W(0x0B00, 0xED14)               # ld AL,#0xaed
W(0xE119)                       # ld X,AL
W(0x063C)                       # add Y,#6
W(0x00E2)                       # rts
LBL("BODY")
W(0x1014, 0x0227)               # ld AL,#16 ; st counter
W(0x0800, 0x1014, 0x0327)       # ld AL,#SEED ; st ptr
LBL("LOOP")
W(0x031B)                       # ld X,@(3,Y)
BSR(UR)                         # UtilRandom
W(0x0027)                       # st rand
W(0x0010, 0x0009)               # AH=0 ; clc
W(0x0FC4, 0x2134)               # and 15 ; add 33
W(0x07A0)                       # asl 7 (pair)
W(0x0123)                       # st pitchhi
W(0x0017, 0x0010, 0x0009, 0x02A4)
W(0x0FC4, 0x0834)               # (rand>>2)&15 + 8
W(0x01B7)                       # or pitchhi -> note
W(0x031B, 0x0026)               # ld X ; st note @(0,X)
W(0x0138, 0x032B)               # X++ ; st ptr
W(0x0217, 0xFF34, 0x0227)       # counter--
W(0x0084)                       # cmp 0
BNE("LOOP")
W(0x031B)                       # ld X,@(3,Y)  (ptr = past last note)
W(0x0100, 0x8000, 0x0014)       # ld AL,#0x8000 (SEQ_END)
W(0x0026)                       # st AL,@(0,X)
W(0x0800, 0x1014, 0x0327)       # ptr = SEED
BSR(SRS)                        # src = StreamRingtoneSource(SEED)
W(0x0427, 0x0184)               # st src @(4,Y) ; cmp 0
BNE("HAVE")
W(0x00E2)                       # rts (no source)
LBL("HAVE")
W(0x0300, 0x0B10)               # ld AH,#0x30b
W(0x0417)                       # ld AL,src
BSR(SCFG)                       # StreamConfigure(0x30b, src)
W(0x0010, 0x0417)               # AH=0 ; AL=src
BSR(SSFS)                       # feed = StreamSinkFromSource(src)
W(0x0800, 0x0825)               # st AL,@FEED
W(0x00E2)                       # rts

# ---- layout: fixed-point with atomic entries ----
SIZE = {"w": None, "bsr": 3, "bne": 2, "bra": 2, "label": 0}
bsr_size, br_size = {}, {}

for iteration in range(8):
    addr = CAVE
    addrs = [0]*len(prog)
    extra = {}
    i = 0
    while i < len(prog):
        kind, arg = prog[i]
        if kind == "label":
            addrs[i] = addr; i += 1; continue
        sz = bsr_size.get(i, 3) if kind == "bsr" else br_size.get(i, 2) if kind == "bne" else br_size.get(i, 1) if kind == "bra" else len(arg)
        band_end = addr
        while blind(band_end) and in_run(band_end): band_end += 1
        limit = band_end - 1
        if addr + sz > limit:
            nb = next_blind(band_end)
            extra[limit] = nb
            addr = nb
            continue
        if kind == "bsr" and i not in bsr_size: bsr_size[i] = 3
        if kind == "bne" and i not in br_size: br_size[i] = 2
        if kind == "bra" and i not in br_size: br_size[i] = 1
        addrs[i] = addr
        addr += sz
        i += 1
    label_addr = {}
    for i, (k, arg) in enumerate(prog):
        if k != "label": continue
        j = i + 1
        while j < len(prog) and (prog[j][0] == "label" or addrs[j] < 0): j += 1
        label_addr[arg] = addrs[j] if j < len(prog) else addrs[-1]
    ok = True
    for i, (kind, arg) in enumerate(prog):
        a = addrs[i]
        if a < 0 or kind in ("w", "label"): continue
        target = label_addr[arg] if isinstance(arg, str) else arg
        if kind == "bsr":
            near = -126 <= target - a <= 126
            want = 1 if near else 3
            if bsr_size.get(i, 3) != want: bsr_size[i] = want; ok = False
        else:
            op = 0xF0 if kind == "bne" else 0xE0
            v2 = target - (a + 2)
            near = -128 <= v2 <= 127
            want = 1 if near else 2
            if br_size.get(i, 2) != want: br_size[i] = want; ok = False
    if ok: break
else:
    raise SystemExit("did not converge")

out = {}
for i, (kind, arg) in enumerate(prog):
    a = addrs[i]
    if kind == "label": continue
    if kind == "w":
        for k, val in enumerate(arg):
            assert a + k not in out, (hex(a+k), "collision")
            out[a+k] = val
    elif kind == "bsr":
        tgt = label_addr[arg] if isinstance(arg, str) else arg
        if bsr_size[i] == 1:
            v = tgt - a
            assert -126 <= v <= 126
            out[a] = ((v & 0xFF) << 8) | 0x9C
        else:
            v = tgt - (a + 2)
            done = False
            for aa in range(-128, 128):
                if aa == 0: continue
                for bb in range(-128, 128):
                    if bb == 0: continue
                    cc = v - aa * 65536 - bb * 256
                    if -128 <= cc <= 127:
                        out[a] = aa << 8; out[a+1] = bb << 8; out[a+2] = (cc << 8) | 0x9C
                        done = True; break
                if done: break
            assert done
    else:
        op = 0xF0 if kind == "bne" else 0xE0
        target = label_addr[arg]
        if br_size[i] == 1:
            v = target - a
            assert -128 <= v <= 127
            out[a] = ((v & 0xFF) << 8) | op
        else:
            v = target - (a + 2)
            aa = 1 if v > 0 else -2
            bb = v - aa * 256
            assert -128 <= bb <= 127
            out[a] = aa << 8; out[a+1] = (bb << 8) | op

for ca, nb in extra.items():
    v = nb - ca
    assert -128 <= v <= 127
    assert ca not in out, (hex(ca), "connector collision")
    out[ca] = ((v & 0xFF) << 8) | 0xE0

lo, hi = min(out), max(out)
print(f"cave spans {lo:#x}..{hi:#x}, {len(out)} words (iters {iteration+1})")
bad = [a for a in out if not blind(a) or not in_run(a)]
assert not bad, [hex(a) for a in bad]
print("all writes blind + in-run")

patched = list(code)
for cw, val in out.items(): patched[cw] = val
for a, op, v, ln in xapvm.decode(patched, fold_zero=False):
    if a < lo or a > hi: continue
    m = xapvm.mnemonic(op, v)
    tgt = None
    if op == 0x9C: tgt = (a+ln-1+v) & 0x3FFFF
    elif op in (0xE0, 0xF0): tgt = (a+v) & 0x3FFFF
    if tgt is not None: m += f" -> {tgt:#x}"
    print(f"  {a:#x}: {' '.join(f'{patched[i]:04x}' for i in range(a, a+ln))} {m}")

import json
json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe11_words.json", "w"), indent=0)
print("saved build/hook/probe11_words.json")
