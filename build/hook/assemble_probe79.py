#!/usr/bin/env python3
"""probe79: isolate the generator. No streams, no DSP, one sample.

probe78 crashed -- running code that `tools/liftfn.py` lifted verbatim from the
linked compiler output and that the emulator reproduced **bit-exactly against a
Python transcription of noise.c** (0 of 128 samples differ). So the
transcription theory is dead, and so is any theory about one bad opcode: the
compiled code uses the same opcode families as the seven hand-written suspects
of probes 68-73 (0x09, 0xA4, 0xC4, 0x74, 0xD1) and fails the same way.

The emulator is not hiding a semantic error either: `xapemu` raises on an
unmodelled opcode, so every instruction in the function was executed with real
semantics, and the result was right.

That leaves the environment, and probe78 changed several things at once -- which
broke this project's own first rule. It added a `malloc(130)` where every prior
probe used 128, a pointer written through `@(0,X)`, a nested `enterl -2` frame,
a 128-iteration loop, and a `StreamRegionSource` pointed into the middle of a
block rather than at its start.

So this probe removes everything that is not the generator. **No
KalimbaSendMessage, no StreamKalimbaSink, no StreamRegionSource, no
StreamConnect.** Just:

    buf = malloc(8)                        ; null -> "lost"
    buf[0] = 0x1234 ; check buf[0]         ; mismatch -> "disconnected"
    buf[0] = 0xACE1 ; buf[1] = 0           ; seed the generator state
    noise_fill(buf+2, 1, buf)              ; ONE sample, not 128
    check buf[2] != 0                      ; zero -> "connecting"
    "connected to"

Each outcome is a different fact, and the pointer round-trip is the one that
matters most, because **writing through a pointer is the primitive every
crashing probe shares and no working probe has ever used.** Probes 37, 59-62,
64-67, 70, 71 and 74-77 only ever called traps and wrote frame slots. Probes
68, 69, 72, 73 and 78 all wrote through a pointer. That correlation is perfect
across eighteen probes and has never been tested on its own.

    "connected to"    -> malloc, the pointer round-trip AND the generator all
                         work. probe78's fault is then the 128-iteration loop
                         or one of the four stream calls, and the next probe
                         adds them back one at a time.
    "disconnected"    -> **a cave cannot write through a pointer.** That is the
                         root cause of every crash since probe68, and it makes
                         the generator innocent. Next question becomes why --
                         MPU, or a bad pointer from malloc.
    "connecting"      -> the generator ran but wrote a zero sample. Should be
                         impossible; the first sample is 0xFE27.
    "lost"            -> malloc(8) failed, having never failed at 128.
    a crash           -> the generator faults on a SINGLE sample with no
                         streams anywhere near it. Then bisect inside the
                         compiled function, which liftfn can do mechanically by
                         lifting a prefix of it.
"""

import sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca
import liftfn

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

# ---- the generator, lifted from the linked image ----
LIFT = liftfn.lift('build/noiseprobe/noiseprobe', 'noise_fill')
assert not LIFT['problems'], LIFT['problems']
print('lifted noise_fill: %d words, %d items, %d labels'
      % (LIFT['size'], len(LIFT['items']),
         sum(1 for it in LIFT['items'] if it[0] == 'label')))

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))

BACK = 0xE06D          # the call the hook at 0xae0 displaced

W(0xF80B)                       # enterl -8
BSR(BACK)                       # stock back-call (proven by probe37)

ca.call1(W, BSR, ca.STUB['malloc'], al=('imm', 8))
W(0x0627)                       # st AL,@(6,Y)  buf
W(0x0084); BR(0xF4, "NOMEM")

# The primitive every crashing probe shares and no working probe has used:
# write a word through a pointer, then read it back and check it.
W(0x061B)                       # ld X,@(6,Y)
ca.load_al(W, ('imm', 0x1234))
W(0x0026)                       # st AL,@(0,X)
W(0x0012)                       # ld AH,@(0,X)
W(*ca.imm_words(0x1234, 0x80))  # cmp AH,#0x1234
BR(0xF0, "BADMEM")

# Seed the generator state in buf[0..1]. X still holds buf.
ca.load_al(W, ('imm', 0xACE1))
W(0x0026)                       # st AL,@(0,X)
ca.load_al(W, ('imm', 0))
W(0x0126)                       # st AL,@(1,X)

W(0x0617)                       # ld AL,@(6,Y)
W(0x0234)                       # add AL,#2
W(0x0727)                       # st AL,@(7,Y)  samples = buf + 2

# ONE sample. If the arithmetic faults, it faults here with nothing else live.
ca.calln(W, BSR, "NOISE", al=('slot', 7), ah=('imm', 1),
         stack=[('slot', 6)], stage='AL')

# The call clobbers X, so reload it before reading the sample back.
W(0x061B)                       # ld X,@(6,Y)
W(0x0212)                       # ld AH,@(2,X)
W(0x0080)                       # cmp AH,#0
BR(0xF4, "ZEROSAMP")

W(0x0E14); BR(0xE0, "EXIT")     # ld AL,#0x0E  "connected to"
LBL("ZEROSAMP"); W(0x0A14); BR(0xE0, "EXIT")   # 0x0A  "connecting"
LBL("BADMEM");   W(0x0814); BR(0xE0, "EXIT")   # 0x08  "disconnected"
LBL("NOMEM");    W(0x0614); BR(0xE0, "EXIT")   # 0x06  "lost"
LBL("EXIT")
W(0xF80F)                       # leavel -8
BR(0xE0, "DONE")                # jump over the lifted function

LBL("NOISE")
for it in LIFT['items']:
    if it[0] == 'w':
        W(*it[1])
    elif it[0] == 'br':
        BR(it[1], it[2])
    else:
        LBL(it[1])
LBL("DONE")

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

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe79_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe79_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe79_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe79_cmd.txt")
