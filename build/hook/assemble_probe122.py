#!/usr/bin/env python3
"""probe122: brown noise through probe104's five proven calls. One change: the data.

**probe104 produced audio** -- laptop connected, music paused, Bluetooth long-press. Five
calls, no state, nothing to clean up. probe122 keeps all five and replaces Bose's const
pool with a generated brown-noise buffer.

## What 2026-10-04 established

probe77 reflashed and **the tone played**, so the cave, the `0xAE0` hook, the long-press
and the flashing procedure are all alive. probes 117/118 made no sound and probe121
crashed. Three errors in them, all now fixed here:

1. **Wrong conditions.** Port 3 belongs to `sbc_decoder`, which A2DP loads. 117/118 were
   tested with nothing connected -- no decoder, no port.
2. **probe117 depended on the prompt call probe77 deliberately deletes** (it reloads the
   `.kap` and steals the tone port).
3. **They omitted `KalimbaSendMessage(0x1072, 8000)`**, which arms the port-3 reader.
   Dropped because the *prompt* DSP has no `0x10xx` handler -- true and irrelevant once
   `sbc_decoder` is what is loaded. probe104 sends it and works.

probe121 **crashed at power-on**: with nothing connected the speaker auto-enters pairing,
firing `0x4003`, and its teardown then ran against a port that was not there. probe77 and
probe104 survive the same power-on fire because they only connect a source.

## So probe122 drops everything unproven

**No teardown. No `MessageSinkTask`. No refill timer.** Exactly probe104's five calls.

## Two structural findings that forced the design

- **The cave cannot hold the data.** `StreamRegionSource` needs a contiguous region, and
  the blind-window geometry gives only ~14 consecutive writable words in every 32. A
  cave-resident buffer longer than ~3 ms is impossible. probe104 worked *because* it
  pointed at Bose's own contiguous const pool.
- **The const pool cannot be the data either.** Searching all 24,475 words for a 2-second
  window that decodes as ADPCM without clipping found **0 of 33** -- every stretch rails
  the IMA index. That is why probe104 gave "loud rough static" and not noise.

So contiguous **writable** memory is unavoidable, which means `malloc`. `probe103`'s
`malloc(512)` returned 0, so the size matters: the VM heap is ten fixed pools and the
**642-word block is a single one** that probes 111-121 all asked for. probe122 asks for
**320**, targeting the **318-word** pool block, and the generator was recompiled to
`NWORDS = 318` to match -- re-measured at **0.00% clipped, -4.95 dB/octave**, identical in
character to 639.

The cost is duration: 318 bytes = 636 samples = **80 ms** at the proven 8000 Hz. A short
whoosh, not a sleep sound. It is a proof that *generated brown noise* reaches the speaker,
after which duration is the only problem left instead of one of four.

**LAPTOP CONNECTED, MUSIC PAUSED. Long-press the Bluetooth button.**

    a brief rushing whoosh (~80 ms)  -> **brown noise reaches the speaker.**
    "lost"            -> malloc(320) returned 0; the 318 pool block is taken too.
    "disconnected"    -> KalimbaSendMessage FALSE: no .kap, not actually connected.
    "voice prompts on"-> StreamKalimbaSink(3) returned 0.
    other spoken id   -> the named call returned 0.
    nothing           -> all calls succeeded and the transform moved nothing.
"""

import sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca
import liftfn
import liftfn

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

CAVE = 0x3E21D         # fixed by the hook's prefix fold at 0xAE0 (do not move)
# 0xae3 := bra +1 only. 0xAE4..0xAE6 (the prompt call) stays STOCK this time.
REDIRECT_EDITS = [("0x6fff1", "0x04"), ("0x6fff3", "0xd7"), ("0x6fff5", "0x3b"),
                  ("0x6fff6", "0xe0"), ("0x6fff7", "0x01")]
# 0xAE4..0xAE6 left STOCK. probes 76-102 deleted the prompt call to stop its .kap
# reload stealing the tone port, and paid for it with six presses the owner could
# not interpret. Here the refill timer re-creates the transform every 110 ms, so
# the prompt costs at most one gap -- and buys a spoken id that names the failing
# call.
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

# No lifted generator: the const pool supplies the nibbles.

# Band 0 holds the entry jump and the 2-word TaskData; the code proper starts in
# band 1, because the hook's prefix fold pins the entry address and cannot be
# retargeted (docs/cave-frame.md, docs/message-task-abi.md).
# No handler, so no TaskData and no entry jump: the hook's target is the first
# instruction, exactly as in the probes before 97.
CODE_AT = CAVE
assert blind(CODE_AT) and in_run(CODE_AT), hex(CODE_AT)

# The const pool, as a byte stream. const_addr maps code-word `a` to the data
# window; the pool begins immediately after the code, so its first word is at
# 0x7400 exactly. 17000 words = 34000 ADPCM samples = 4.25 s at 8000 Hz,
# measured offline at -0.9 dBFS with no quiet run over 17 samples.
LIFT = liftfn.lift('build/noiseprobe/noiseprobe', 'nib_fill')
assert not LIFT['problems'], LIFT['problems']
print('lifted nib_fill: %d words' % LIFT['size'])
NWORDS = 318            # matches the recompiled generator and the 318-word pmalloc block
POOL_PTR = 0x7400
POOL_LEN = 17000
assert POOL_PTR == ca.const_addr(236514), hex(ca.const_addr(236514))
# Stay inside the part of the const window PROVEN mapped at runtime: probes 99,
# 100 and 102 had the firmware read a TaskData as data at 0xBA3C, which is 17,980
# words past 0x7400. The section almost certainly runs to 0xD39A, but reading off
# the end of a mapped region is a way to wedge the VM for nothing.
assert POOL_PTR + POOL_LEN <= 0xBA3C, hex(POOL_PTR + POOL_LEN)

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))

BACK = 0xE06D          # the call the hook at 0xae0 displaced

W(0xF00B)                       # enterl -16  (slots 0..13 usable, 14/15 = link)
BSR(BACK)                       # stock back-call (proven by probe37)

# Arm the port-3 reader: codec_tones.asm:516 sets $aux_input_stream_available = 1
# inside this handler. 8000 Hz is the rate probe77 proved audible.
ca.calln(W, BSR, ca.STUB['KalimbaSendMessage'],
         al=('imm', 0x1072), ah=('imm', 8000),
         stack=[('imm', 0), ('imm', 0), ('imm', 0)], stage='AL')
W(0x0084); BR(0xF4, "R08")

ca.call1(W, BSR, ca.STUB['StreamKalimbaSink'], al=('imm', 3))
W(0x0A27)                       # st AL,@(10,Y)  ksink3
W(0x0084); BR(0xF4, "R12")

# A generated brown-noise buffer. The cave cannot hold it (blind windows give only
# ~14 contiguous words) and no stretch of const pool decodes without clipping, so this
# needs real RAM. 320 targets the 318-word pool block, not the single 642 that probes
# 111-121 asked for and that probe103 showed can be unavailable.
ca.call1(W, BSR, ca.STUB['malloc'], al=('imm', NWORDS + 2))
W(0x0D27)                       # st AL,@(13,Y)  buf
W(0x0084); BR(0xF4, "R06")
W(0x0D1B)                       # ld X,@(13,Y)
W(0x0014); W(0x0026); W(0x0126) # buf[0] = 0 (nib_fill sentinel), buf[1] = 0
W(0x0D17); W(0x0234); W(0x0C27) # samples = buf + 2 -> slot 12
ca.call2(W, BSR, "NIBS", al=('slot', 12), ah=('slot', 13))

ca.call2(W, BSR, ca.STUB['StreamRegionSource'],
         al=('slot', 12), ah=('imm', NWORDS))
W(0x0B27)                       # st AL,@(11,Y)  src
W(0x0084); BR(0xF4, "R12")

# Bose's own two call sites, 0x22F9B and 0x23083: arg1 = source, arg2 = sink.
ca.call2(W, BSR, ca.STUB['TransformAdpcmDecode'], al=('slot', 11), ah=('slot', 10))
W(0x0C27)                       # st AL,@(12,Y)  t
W(0x0084); BR(0xF4, "R01")

# transform.h:25-28: a StreamConnect transform starts implicitly and must NOT be
# started; a TransformAdpcmDecode one must be.
ca.call1(W, BSR, ca.STUB['TransformStart'], al=('slot', 12))
W(0x0084); BR(0xF4, "R0A")

W(0x0E14); BR(0xE0, "EXIT")     # ld AL,#0x0E  "connected to" = every call OK
LBL("R06"); W(0x0614); BR(0xE0, "EXIT")   # 0x06 "lost" -- malloc failed
LBL("R08"); W(0x0814); BR(0xE0, "EXIT")    # 0x08  "disconnected"
LBL("R12"); W(0x1214); BR(0xE0, "EXIT")    # 0x12  "voice prompts on"
LBL("R01"); W(0x0114); BR(0xE0, "EXIT")    # 0x01  "connecting to"
LBL("R0A"); W(0x0A14)                      # 0x0A  "connecting"
LBL("EXIT")
W(0xF00F)                       # leavel -16

W(0x0000); W(0x0000); W(0x0000); W(0x0000)                       # padding past the +-128 bsr encoding gap
LBL("NIBS")
for it in LIFT['items']:
    if it[0] == 'w':
        W(*it[1])
    elif it[0] == 'br':
        BR(it[1], it[2])
    else:
        LBL(it[1])

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
    addr = CODE_AT
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
        # Branches use the SAME last-word rule as bsr. Verified independently against
        # Bose's 2103 multi-word branches: a+ln-1+v lands on an instruction boundary
        # 100% of the time, a+v only 42% (chance).
        elif op in (0x20, 0x24, 0x28, 0x2C, 0xE0, 0xE4, 0xE8, 0xEC,
                    0xF0, 0xF4, 0xF8, 0xFC): seen[a] = (a + ln - 1 + v) & 0x3FFFF
for a, (tgt, kind) in intended.items():
    assert seen.get(a) == (tgt & 0x3FFFF), (hex(a), kind, hex(tgt), seen.get(a))
assert CODE_AT == CAVE   # no entry jump to verify in this probe
for i, item in enumerate(prog):
    if item[0] != "label":
        assert addrs[i] in dstarts, (hex(addrs[i]), "boundary")
print("decode-verify: all branches OK, boundaries OK")

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe122_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe122_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe122_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe122_cmd.txt")
