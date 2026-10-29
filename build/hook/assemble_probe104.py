#!/usr/bin/env python3
"""probe104: ADPCM straight from Bose's const pool. No malloc, no timer.

probe103 said **"lost"** -- `malloc(512)` returned 0, the very first call, so
nothing downstream ran at all. probe82 did get 512 words, but **with music
playing**; paused is a different heap state, and 1 KB is simply not there.

Rather than guess a smaller size, this probe removes the allocation entirely.

## The const pool is already a large body of ADPCM nibbles

`StreamRegionSource` hands over the **low byte of each 16-bit word**
(see probe103's note), and Bose's const pool is **24,475 words** mapped into
data space at 0x7400 (`caveasm.const_addr`, the same window probe74 proved a
region pointer is accepted from). Its low bytes are arbitrary. For IMA ADPCM
that is not a problem -- it is the input format.

**Decoded offline before flashing** (`STEP`/`IDX` tables, standard IMA):

| window | duration @8 kHz | RMS | longest quiet run |
|---|---|---|---|
| **first 17,000 words (used here)** | **4.25 s** | **-0.9 dBFS** | 17 samples (2 ms) |
| whole pool, 24,475 words | 6.12 s | -1.1 dBFS | 17 samples |
| middle 6,000 words | 1.50 s | -1.4 dBFS | 25 samples |

The length stops at 17,000 words rather than using the whole pool because that is
how far the const window is *proven* mapped at runtime: probes 99, 100 and 102
had the firmware read a `TaskData` as data at 0xBA3C = 17,980 words past 0x7400.
Reading off the end of a mapped region is a way to wedge the VM for nothing.

Only 13.7% of low bytes are zero and no quiet run exceeds 25 samples, so there
is no silent stretch anywhere in it.

**This will be loud, harsh static, not brown noise.** Uniformly random nibble
magnitudes average `(-1-1-1-1+2+4+6+8)/8 = +2` on the IMA step index, so the
index rails to its ceiling and stays there: 22,953 of 34,000 samples clip
against +-32767. A railed random walk is a rough rasp, not a 1/f^2 spectrum.

**That is deliberate.** probe103 could not answer whether
`TransformAdpcmDecode` into port 3 makes any sound, because it died before the
transform was ever created. This probe answers exactly that question and
nothing else -- 4.25 seconds at full scale, with no allocation to fail, no
generator, no `TaskData`, no refill timer and no teardown. Every one of those
is a way to get silence for a reason that has nothing to do with the transform.

Shaping it into real brown noise is probe105's job, and it is a solved problem
once the path is known to carry audio: force the nibble magnitudes down so the
step index settles mid-scale instead of railing, which `nib_fill` already does
(it is built, lifted and verified bit-exact) and which needs only a `malloc`
size that actually succeeds.

## The whole cave

    KalimbaSendMessage(0x1072, 8000, 0, 0, 0)       arm the port-3 reader
    ksink3 = StreamKalimbaSink(3)
    src    = StreamRegionSource(0x7400, 17000)      Bose's const pool, as bytes
    t      = TransformAdpcmDecode(src, ksink3)      Bose's own recipe, 0x22F9B
    TransformStart(t)

Five calls, no state, nothing to clean up. The prompt call stays **stock**, so
every failure names itself.

**Phone CONNECTED, music PAUSED** -- probe77's proven conditions.

    four seconds of loud rough static (before or after "connected to")
        -> **the ADPCM path into port 3 carries audio.** Then probe105 shapes it
           into brown noise with a generator and a survivable malloc.
    "connected to" and nothing
        -> all five calls succeeded and the transform moved nothing. With malloc,
           timers and the generator all out of the picture, that is a clean
           negative about the transform itself, and `TransformPollTraffic`
           (stub 0x142) is the follow-up.
    "disconnected"  -> KalimbaSendMessage FALSE: no .kap loaded, so the phone is
                       not actually connected. Reconnect and retry.
    "voice prompts on"
                    -> StreamKalimbaSink(3) or StreamRegionSource returned 0.
                       The latter would most likely mean a length limit, since
                       17000 is far larger than any length the ADK ever passes.
    "connecting to" -> TransformAdpcmDecode returned 0: the trap exists but
                       refused this source/sink pair.
    "connecting"    -> TransformStart returned FALSE.
"""

import sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca
import liftfn

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm


# --- output paths are derived from THIS FILE'S OWN NAME, never hardcoded -------------
# Every probe assembler is made by copying its predecessor, and three times now the copy
# kept the predecessor's hardcoded output paths and silently overwrote the artifacts of
# the image sitting ON THE DEVICE: probe129_words.json twice, probe134_words.json once
# (restored from build/hook/snapshots/ and re-verified against the device readback both
# times). A words.json is the only record of what a flashed image contains, so losing it
# costs the readback check its reference.
_PROBE = re.match(r'assemble_(probe\d+)\.py$',
                  os.path.basename(os.path.abspath(__file__))).group(1)

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

# Bose's own const pool as the byte stream. No malloc: probe103 died here.
ca.call2(W, BSR, ca.STUB['StreamRegionSource'],
         al=('imm', POOL_PTR), ah=('imm', POOL_LEN))
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
LBL("R08"); W(0x0814); BR(0xE0, "EXIT")    # 0x08  "disconnected"
LBL("R12"); W(0x1214); BR(0xE0, "EXIT")    # 0x12  "voice prompts on"
LBL("R01"); W(0x0114); BR(0xE0, "EXIT")    # 0x01  "connecting to"
LBL("R0A"); W(0x0A14)                      # 0x0A  "connecting"
LBL("EXIT")
W(0xF00F)                       # leavel -16

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

json.dump({hex(a): v for a, v in out.items()}, open(f"build/hook/{_PROBE}_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", f"build/hook/{_PROBE}_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open(f"build/hook/{_PROBE}_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> {_PROBE}_cmd.txt")
