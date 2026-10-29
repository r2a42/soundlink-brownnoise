#!/usr/bin/env python3
"""probe12 (v2, fixed): long-press -> beep + feed 16 rumble note words into
the tone stream's feed sink.  Tests the engine-v2 core unknown: does the
feed sink returned by 0x4946 accept note words and play them?

Fixes vs the 2026-09-27-night draft:
  1. SinkClaim failure now BRANCHES OUT (second beep + exit) instead of
     falling through with offset 0xFFFF (write corruption).
  2. enterl -8 (frame slots 0..7 all in frame; draft used -6 but wrote
     slot 7 - caller-frame corruption).
  3. Note counter uses slot 7 (draft decremented slot 2).
  4. Single SinkFlush (draft flushed twice with stale args).

Sizes are WORD-consistent with probe11c: SinkClaim 32, write 16 words
(TEMPO-free, seed seq 3's timbre/tempo already running), SinkFlush 16.
If the ABI is byte-based instead: claim 32B exact for 16 words, flush 16B
= half the burst - rumble length distinguishes the two.

Telemetry on device:
  beep + ~1.7 s low rumble  -> feed sink WORKS (engine v2 is go)
  beep, beep (no rumble)    -> SinkClaim failed
  beep only                 -> claim+map+flush ran, feed silently dropped
  nothing                   -> crash (recoverable, official restore proven)

Exit: X=0xaed, rts (skips the 0xae3 post-flow: VR flip never runs ->
every long-press reaches this cave; no 0xae3 patch needed).
"""
import sys, json, subprocess

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

TONE = 0x4946
CAVE = 0x3E21D
REDIRECT_EDITS = [("0x6fff1", "0x04"), ("0x6fff3", "0xd7"), ("0x6fff5", "0x3b")]
AREA0 = 0x6EA30          # area byte of code word 0, low byte (LE words)

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

stubs, _ = xapvm.find_stubs(code)
tt = xapvm.trap_table()
CLAIM = MAP = FLUSH = None
for a, num in stubs.items():
    if tt.get(num) == "SinkClaim": CLAIM = a
    if tt.get(num) == "SinkMap": MAP = a
    if tt.get(num) == "SinkFlush": FLUSH = a
assert (CLAIM, MAP, FLUSH) == (0x0DE, 0x0E2, 0x0E6), (CLAIM, MAP, FLUSH)
print("claim/map/flush stubs:", hex(CLAIM), hex(MAP), hex(FLUSH))

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BNE(l): prog.append(("bne", l))
def BRA(l): prog.append(("bra", l))
def LBL(n): prog.append(("label", n))
def LDI_AL(v):
    """ld AL,#v (signed imm8, one prefix word if needed). ONE atomic item:
    a standalone prefix-looking word (low byte 0) would absorb the next
    band connector into a 2-word branch with a garbage target."""
    if -128 <= v <= 127:
        W(((v & 0xFF) << 8) | 0x14)
    else:
        h = (v + 128) >> 8
        b = v - (h << 8)
        assert -128 <= b <= 127
        W((h & 0xFF) << 8, ((b & 0xFF) << 8) | 0x14)

RELOAD_SINK = (0x0213, 0x0317)     # ld AH,@(2,Y); ld AL,@(3,Y)

W(0xF80B)                          # enterl -8
W(0x0014)                          # ld AL,#0
BSR(TONE)                          # beep; AH:AL = feed sink
W(0x0223, 0x0327)                  # st AH,@(2,Y); st AL,@(3,Y)
# SinkClaim(feed, 32)
LDI_AL(32); W(0x0027)              # ld AL,#32 ; st @(0,Y)
W(0x0014, 0x0127)                  # ld AL,#0 ; st @(1,Y)
W(*RELOAD_SINK)
BSR(CLAIM)                         # offset -> AL (0xFFFF = fail)
W(0x0427)                          # st offset @(4,Y)
W(0xFF84)                          # cmp AL,#-1
BNE("HAVE")
W(0x0014)                          # claim failed: 2nd beep = telemetry
BSR(TONE)
BRA("EXIT")
LBL("HAVE")
# SinkMap(feed, offset)
W(0x0417, 0x0027)                  # ld AL,@(4,Y) ; st @(0,Y)
W(0x0014, 0x0127)                  # ld AL,#0 ; st @(1,Y)
W(*RELOAD_SINK)
BSR(MAP)                           # ptr -> AH:AL
W(0x0523, 0x0627)                  # st AH,@(5,Y); st AL,@(6,Y)
W(0x0084)                          # cmp AL,#0
BNE("W0")
BRA("EXIT")                        # null map -> bail
LBL("W0")
W(0x061B)                          # ld X,@(6,Y)    X = map
W(0x0417)                          # ld AL,@(4,Y)   AL = offset
W(0xE139)                          # add X,AL       X = map + offset
LDI_AL(16); W(0x0727)              # counter @(7,Y) = 16
LBL("NROUND")
for note in (0x1088, 0x1208, 0x1408, 0x1688):
    LDI_AL(note)                   # (pitch<<7)|8 : 55/65/82/98 Hz, quaver
    W(0x0026)                      # st AL,@(0,X)
    W(0x0138)                      # add X,#1
W(0x0717)                          # ld AL,@(7,Y)
W(0xFF34)                          # add AL,#-1
W(0x0727)
W(0x0084)
BNE("NROUND")
# SinkFlush(feed, 16)
LDI_AL(16); W(0x0027)
W(0x0014, 0x0127)
W(*RELOAD_SINK)
BSR(FLUSH)
LBL("EXIT")
W(0x0B00, 0xED14)                  # ld AL,#0xaed
W(0xE119)                          # ld X,AL
W(0x083C)                          # add Y,#8
W(0x00E2)                          # rts: pc <- X = 0xaed (post-flow skipped)

# ---- layout: fixed-point with atomic band connectors (proven) ----
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
    raise SystemExit("no converge")

def sext8(b): return b - 256 if b & 0x80 else b

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
                        out[a] = (aa & 0xFF) << 8; out[a+1] = (bb & 0xFF) << 8
                        out[a+2] = ((cc & 0xFF) << 8) | 0x9C
                        done = True; break
                if done: break
            assert done
    else:
        op = 0xF0 if kind == "bne" else 0xE0
        tgt = label_addr[arg]
        if br_size[i] == 1:
            v = tgt - a
            assert -128 <= v <= 127
            out[a] = ((v & 0xFF) << 8) | op
        else:
            # multi-word BRANCH folds from the instruction's own address
            # (unlike bsr, which folds from the last word): tgt = a + operand
            v = tgt - a
            aa = 1 if v > 0 else -2
            bb = v - aa * 256
            assert -128 <= bb <= 127
            out[a] = (aa & 0xFF) << 8; out[a+1] = ((bb & 0xFF) << 8) | op
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

# AUTHORITATIVE verify: xapvm.decode (the validated decoder) must fold every
# bsr/branch in the cave to its intended target.
intended = {}
for i, (kind, arg) in enumerate(prog):
    if kind not in ("bsr", "bne", "bra"): continue
    a = addrs[i]
    intended[a] = (label_addr[arg] if isinstance(arg, str) else arg, kind)
seen = {}
dstarts = set()
for a, op, v, ln in xapvm.decode(patched, fold_zero=False):
    dstarts.add(a)
    if lo <= a <= hi:
        if op == 0x9C: seen[a] = ((a + ln - 1 + v) & 0x3FFFF, "bsr")
        elif op in (0xE0, 0xF0): seen[a] = ((a + v) & 0x3FFFF, "bra/bne")
for a, (tgt, kind) in intended.items():
    got = seen.get(a)
    assert got and got[0] == (tgt & 0x3FFFF), (hex(a), kind, hex(tgt), got)
print(f"decode-verify: {len(intended)}/{len(intended)} branches fold to intended targets")

# every placed instruction must START a decoded instruction: a prefix-looking
# word (low byte 0) before a connector would absorb it (garbage target at
# runtime as well as in the decoder)
for i, (kind, arg) in enumerate(prog):
    if kind == "label": continue
    a = addrs[i]
    assert a in dstarts, (hex(a), kind, "not an instruction boundary in linear decode")
for ca in extra:
    assert ca in dstarts, (hex(ca), "connector not an instruction boundary")
print("decode boundaries: every placed word starts an instruction")

# belt-and-braces: unsigned fold check too
for i, (kind, arg) in enumerate(prog):
    if kind != "bsr": continue
    a = addrs[i]
    tgt = label_addr[arg] if isinstance(arg, str) else arg
    val = 0
    for cw in (out[a], out[a+1], out[a+2]):
        cw &= 0xFFFF
        h = cw >> 8
        if (cw & 0xFF) == 0 and cw != 0x0000:
            val = (val + sext8(h)) << 8
        else:
            val += sext8(h)
    real = (a + 2 + val) & 0x3FFFF
    assert real == (tgt & 0x3FFFF), (hex(a), hex(real), hex(tgt))
print("unsigned fold check: OK")

names = {TONE: "play-tone/feedsink", CLAIM: "SinkClaim", MAP: "SinkMap", FLUSH: "SinkFlush"}
for a, op, v, ln in xapvm.decode(patched, fold_zero=False):
    if lo <= a <= hi:
        m = xapvm.mnemonic(op, v)
        tgt = None
        if op == 0x9C: tgt = (a+ln-1+v) & 0x3FFFF
        elif op in (0xE0, 0xF0): tgt = (a+v) & 0x3FFFF
        if tgt is not None: m += f" -> {tgt:#x}" + (f" ({names[tgt]})" if tgt in names else "")
        print(f"  {a:#x}: {' '.join(f'{patched[i]:04x}' for i in range(a, a+ln))} {m}")

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe12_words.json", "w"), indent=0)
print("saved build/hook/probe12_words.json")

# ---- fsedit invocation (redirect + every cave byte) ----
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe12_rumble.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe12_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> build/hook/probe12_cmd.txt (run with --build)")
