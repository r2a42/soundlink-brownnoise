#!/usr/bin/env python3
"""Assemble the probe11c cave: toggle + beep + FEED-SINK experiment.

Program (all stubs verified): toggle global 0x56b bit11 (safe app flag,
no longer set by anything since the post-flow is skipped); ON:
  0x4946(0) = beep + returns the ringtone stream's FEED SINK in AH:AL;
  SinkClaim(feed,16) -> SinkMap -> write [TEMPO 0x93C0, 15x note 0x0C08
  (pitch 24 = 32.7 Hz, quaver)] -> SinkFlush.  If the feed accepts note
  words, the speaker plays a LOW PULSING after the beep.
Exit: frame restore + rts -> 0xae3 -> [patched bra] -> 0xaed (Siri path
skipped).
"""
import sys
sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

TONE, CLAIM, MAP, FLUSH = 0x4946, 0x0DE, 0x0E2, 0x0E6   # code addrs
CAVE = 0x3E21D

w = xapvm.load_words("firmware/bose/extracted/internal_fs/vm.app")
code = w[0x18:]
C0 = (0x6e974 + 0x34) % 64
def blind(cw): return 34 <= (2*cw + C0) % 64 <= 60   # both bytes writable
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
def next_blind(pc):
    while not blind(pc) or not in_run(pc): pc += 1
    return pc

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BNE(lbl): prog.append(("bne", lbl))
def BRA(lbl): prog.append(("bra", lbl))
def LBL(n): prog.append(("label", n))

W(0xF80B)                        # enterl -8
W(0x0500, 0x6B15)                # ld AL,@0x56b
W(0x0800, 0x00D4)                # xor AL,#0x0800   (toggle bit 11)
W(0x0500, 0x6B25)                # st AL,@0x56b
W(0x0800, 0x00C4)                # and AL,#0x0800
W(0x0084)                        # cmp AL,#0
BNE("ON")
BRA("RET")
LBL("ON")
BSR("BODY")
LBL("RET")
W(0x083C)                        # add Y,#8
W(0x00E2)                        # rts -> 0xae3 -> patched bra -> 0xaed
LBL("BODY")
W(0x0014)                        # ld AL,#0
BSR(TONE)                        # beep + feed sink in AH:AL
W(0x0223)                        # st AH,@(2,Y)   sink hi
W(0x0327)                        # st AL,@(3,Y)   sink lo
# SinkClaim(sink, 16)
W(0x1014, 0x0027)                # ld AL,#16 ; st @(0,Y)
W(0x0014, 0x0127)                # ld AL,#0 ; st @(1,Y)
W(0x0213, 0x0317)                # ld AH,@(2,Y) ; ld AL,@(3,Y)
BSR(CLAIM)                       # offset -> AL
W(0x0427)                        # st offset @(4,Y)
# SinkMap(sink, offset)
W(0x0417, 0x0027)                # ld AL,@(4,Y) ; st @(0,Y)
W(0x0014, 0x0127)                # ld AL,#0 ; st @(1,Y)
W(0x0213, 0x0317)                # reload sink
BSR(MAP)                         # ptr -> AH:AL
W(0x0523)                        # st AH,@(5,Y)
W(0x0627)                        # st AL,@(6,Y)
W(0x0084)                        # cmp AL,#0
BNE("W0")
BRA("DONE")                      # null map -> bail
LBL("W0")
W(0x061B)                        # ld X,@(6,Y)
W(0x9400, 0xC014)                # ld AL,#0x93C0 (prefix 0x94 compensates sext(-0x40))
W(0x0026)                        # st AL,@(0,X)
W(0x0138)                        # add X,#1
W(0x062B)                        # st X,@(6,Y)
W(0x0F14, 0x0727)                # ld AL,#15 ; counter @(7,Y)
LBL("WLOOP")
W(0x061B)                        # ld X,@(6,Y)
W(0x0C00, 0x0814)                # ld AL,#0x0C08 (pitch 24, quaver)
W(0x0026)                        # st AL,@(0,X)
W(0x0138)                        # add X,#1
W(0x062B)                        # st X,@(6,Y)
W(0x0717)                        # ld AL,@(7,Y)
W(0xFF34)                        # add AL,#-1
W(0x0727)                        # st AL,@(7,Y)
W(0x0084)                        # cmp AL,#0
BNE("WLOOP")
# SinkFlush(sink, 16)
W(0x1014, 0x0027)                # ld AL,#16 ; st @(0,Y)
W(0x0014, 0x0127)                # ld AL,#0 ; st @(1,Y)
W(0x0213, 0x0317)                # reload sink
BSR(FLUSH)
LBL("DONE")
W(0x00E2)                        # rts

# ---- layout: fixed-point with atomic entries (proven machinery) ----
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
        sz = bsr_size.get(i, 3) if kind == "bsr" else br_size.get(i, 1) if kind in ("bne", "bra") else len(arg)
        band_end = addr
        while blind(band_end) and in_run(band_end): band_end += 1
        limit = band_end - 1
        if addr + sz > limit:
            nb = next_blind(band_end)
            # connector goes RIGHT AFTER the last placed word: no 0x0000 holes
            # (0x0000's runtime semantics are unverified - never execute it)
            assert blind(addr) and in_run(addr), (hex(addr), "connector slot not blind")
            extra[addr] = nb
            addr = nb
            continue
        if kind == "bsr" and i not in bsr_size: bsr_size[i] = 3
        if kind in ("bne", "bra") and i not in br_size: br_size[i] = 1
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
            near = -128 <= target - a <= 127
            want = 1 if near else 2
            if br_size.get(i, 1) != want: br_size[i] = want; ok = False
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
# patch the bra at 0xae3 into the patched copy too, then decode-verify both zones
patched[0xAE3] = 0x0AE0          # bra +0x0A -> 0xAED (skip Siri post-flow)
names = {0x4946: "play-tone/feedsink", 0x0DE: "SinkClaim", 0x0E2: "SinkMap", 0x0E6: "SinkFlush"}
for a, op, v, ln in xapvm.decode(patched, fold_zero=False):
    if lo <= a <= hi or a in (0xAE0, 0xAE3):
        m = xapvm.mnemonic(op, v)
        tgt = None
        if op == 0x9C: tgt = (a+ln-1+v) & 0x3FFFF
        elif op in (0xE0, 0xF0): tgt = (a+v) & 0x3FFFF
        if tgt is not None: m += f" -> {tgt:#x}" + (f" ({names[tgt]})" if tgt in names else "")
        print(f"  {a:#x}: {' '.join(f'{patched[i]:04x}' for i in range(a, a+ln))} {m}")

import json
json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe11c_words.json", "w"), indent=0)
print("saved build/hook/probe11c_words.json")
