#!/usr/bin/env python3
"""probe17: catalog sweep v5 — ZERO structural delta from stock.
Cave: beep + id=(ctr+0x35)&0x3F -> dispatcher frame slot 10 (zero
accesses in the whole dispatcher fn) + counter++. Post-flow: STOCK
except ONE word: 0xae3 ld AL,#0x35 -> ld AL,@(10,Y). No globals except
0x518 (counter). Wedge theories addressed: no 0x50c write, no post-flow
rewrite, LED/0x56b block untouched, single stock-site request.

Root-cause chain from tonight's field data + ISA re-check:
  1. rts pops the INTERNAL return stack (0x4946 nests 4 bsrs w/o saving X),
     so the old X=0xaed exit was a no-op: every cave returned to 0xae3 and
     the stock post-flow (0xdf7f(0x35) + LED) always ran. Siri always
     fired; alternation = stock VA start/cancel.
  2. The cave's EXTRA 0xdf7f request (15b/15c) is the delta vs stock that
     wedges the VA session after press 1 (cave beep heard once, never
     again: subsequent start-presses fail the 0x9157/0x565 guards).

probe16 design:
  - Cave (0xae0 redirect, unchanged mechanism): beep (0x4946, "cave ran"),
    id = (@0x518 + 0x35) & 0x3F -> global 0x50c (verified free: one boot
    write, zero reads), counter++ (wrap 0x40). rts -> 0xae3 (stock flow).
  - Post-flow rewrite (ALL blind bytes, 0xae3-0xae7):
      ld AL,@0x50c ; bsr 0xdf7f ; bra 0xaed
    = the STOCK request site now plays OUR counter id. One request per
    start-press, stock session semantics, no extra request.
  - First id = 0x35 (the stock sound) => press 1 behaves exactly like
    stock (healthy session), then 0x36..0x3F, 0x00..0x34.
  - Gate force dropped (stock handles it at the stock site).
"""
import sys, json, subprocess

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

REQ = 0xDF7F
TONE = 0x4946
CAVE = 0x3E21D
CTR = 0x518
IDG = 0x50C
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

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))

# ---------------- CAVE (clone + slot10 CONST + patch only) ----------
W(0xF80B)                       # enterl -8
W(0x0014)                       # ld AL,#0
BSR(TONE)                       # beep
LDI36 = (0x36 << 8) | 0x14      # ld AL,#0x36
W(LDI36)
W(0x1227)                       # st AL,@(18,Y)  (= dispatcher slot 10)
W(0x083C)                       # add Y,#8
W(0x00E2)                       # rts

POSTFLOW = [(0xae3, [0x0A17])]   # ld AL,@(10,Y)

# ---- layout (cave: proven band machinery; postflow: fixed addresses) ----
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

def sext8(b): return b - 256 if b & 0x80 else b
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
print("cave: all writes blind + in-run")

# post-flow fixed words
pf = {}
for a, val in POSTFLOW:
    for k, val2 in enumerate(val):
        pf[a+k] = val2
for a in pf:
    assert blind(a), (hex(a), "postflow word not blind")
    assert a not in out
out.update(pf)
print(f"post-flow rewrite: {len(pf)} words at {' '.join(hex(a) for a in sorted(pf))}")

patched = list(code)
for cw, val in out.items(): patched[cw] = val & 0xFFFF

# verify: cave branches + postflow fold
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
        elif op in (0xE0, 0xF0, 0xF4, 0xF8, 0xFC): seen[a] = (a + v) & 0x3FFFF
for a, (tgt, kind) in intended.items():
    assert seen.get(a) == (tgt & 0x3FFFF), (hex(a), kind, hex(tgt), seen.get(a))

for i, item in enumerate(prog):
    if item[0] != "label":
        assert addrs[i] in dstarts, (hex(addrs[i]), "boundary")
print("decode-verify: cave branches, postflow bsr->0xdf7f, boundaries OK")

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe18b_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe18b_redirect.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe18b_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe18b_cmd.txt")
