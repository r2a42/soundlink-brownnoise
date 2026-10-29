#!/usr/bin/env python3
"""probe102: continuous brown noise. Refill on a timer, at the rate that works.

probe101 was **silent**. Against probe77 -- a long clean tone under identical
conditions -- exactly two things differed:

| | probe77 (tone heard) | probe101 (silent) |
|---|---|---|
| source | `StreamRingtoneSource` | `StreamRegionSource` |
| `SET_TONE_RATE` | **8000** | **1000** |

The rate was the stated suspect, and 1000 Hz is far outside anything the ADK ever
asks for (8000, 16000, 44100, 48000); it would need 16:1 upsampling. But testing the
rate alone puts 64 ms back on the table, and the owner has twice been asked to judge
64 ms and twice rightly could not.

**So fix the rate and the duration together, with machinery that is already proven.**

## The refill loop

probe99 proved `MessageSendLater` + a `TaskData` in const padding + a handler running
from `MessageLoop` all work; probe100 proved the **MessageId survives into the
handler**. A data pointer on this chip is 16 bits -- exactly the width of a MessageId
-- so **the buffer pointer travels as the message id**, which solves the problem that
a cave has nowhere safe to keep a global:

    cave      buf = malloc(512) ; seed ; noise_fill ; SET_TONE_RATE 8000
              ksink3 ; StreamRegionSource ; StreamConnect
              MessageSendLater(task, buf, 0, 60 ms)

    handler(AH = buf):
              noise_fill(buf+2, 510, buf)      continues the sequence, does not restart
              ksink3 ; StreamRegionSource ; StreamConnect
              MessageSendLater(task, buf, 0, 60 ms)      re-arm, same pointer

510 samples at 8000 Hz is 64 ms, so a refill every 60 ms keeps it continuous. **The
re-arm is unconditional**, so it runs for as long as the speaker leaves it alone --
which for a sleep sound is the desired behaviour, not a bug. probe100's counter is
not needed here, and its bug (failure paths skipping the re-arm) cannot recur because
there are no failure bails: the prompt call is deleted, so a spoken id would be
inaudible anyway, and every call in this chain is already proven on hardware.

**And the refills are genuinely continuous, not a loop.** The generator carries its
LFSR and integrator through the state pointer in `buf[0..1]`, so each refill continues
the sequence -- verified earlier: a second refill shares **0 of 128** samples with the
first. A 64 ms buffer replayed unchanged would buzz at 15.6 Hz; this does not.

## Conditions

**Phone CONNECTED, music PAUSED** -- probe77 proved that keeps the A2DP decoder
loaded, which is what makes port 3 a free mixing input and keeps the firmware owning
the DAC.

    continuous noise -> **the deliverable.** Brown noise, generated in a cave, on a
                        button press, for as long as it is left running.
    a brief hiss then nothing -> the first buffer played and the refill did not.
                        The timer works (probe99), so suspect the handler's own
                        re-arm.
    a rough buzz     -> refills are happening but not continuously -- the 60 ms
                        interval is wrong against the real consumption rate.
    silence          -> the rate was not the difference either, and the remaining
                        suspect is `StreamRegionSource` itself on the tone port,
                        where `StreamRingtoneSource` works. That would be worth
                        knowing precisely.
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
                  ("0x6fff6", "0xe0"), ("0x6fff7", "0x01"),   # 0xae3 := bra +1
                  # 0xae4..0xae6 := three nops. probe82 left the prompt call stock
                  # and its .kap reload destroyed the connection, so probe82 could
                  # never have been heard. Nothing may take the path back now.
                  ("0x6fff8", "0x00"), ("0x6fff9", "0x00"),
                  ("0x6fffa", "0x00"), ("0x6fffb", "0x00"),
                  ("0x6fffc", "0x00"), ("0x6fffd", "0x00")]
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

# Band 0 holds the entry jump and the 2-word TaskData; the code proper starts in
# band 1, because the hook's prefix fold pins the entry address and cannot be
# retargeted (docs/cave-frame.md, docs/message-task-abi.md).
BAND0 = [CAVE + k for k in range(14)]
assert all(blind(a) and in_run(a) for a in BAND0)
CODE_AT = next_blind(BAND0[-1] + 1)
assert CODE_AT == CAVE + 32, hex(CODE_AT)

TASK_AT = CAVE + 1
TASK_PTR = ca.const_addr(TASK_AT)
REFILL_MS = 60

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))

BACK = 0xE06D          # the call the hook at 0xae0 displaced

W(0xF00B)                       # enterl -16  (slots 0..13 usable, 14/15 = link)
BSR(BACK)                       # stock back-call (proven by probe37)

ca.call1(W, BSR, ca.STUB['malloc'], al=('imm', 512))
W(0x0A27)                       # st AL,@(10,Y)  buf
W(0x0084); BR(0xF4, "EXIT")

W(0x0A1B)                       # ld X,@(10,Y)
ca.load_al(W, ('imm', 0xACE1)); W(0x0026)      # buf[0] = LFSR seed
ca.load_al(W, ('imm', 0));      W(0x0126)      # buf[1] = integrator seed
W(0x0A17); W(0x0234); W(0x0B27) # samples = buf + 2 -> slot 11

BSR("FILL")                     # noise_fill + connect, shared with the handler

# Hand the buffer pointer to the handler AS THE MESSAGE ID: a data pointer is 16
# bits, exactly a MessageId's width, and probe100 proved the id arrives intact.
ca.calln(W, BSR, ca.STUB['MessageSendLater'],
         al=('imm', TASK_PTR), ah=('slot', 10),
         stack=[('imm', 0), ('long', REFILL_MS)], stage='AL')
LBL("EXIT")
W(0xF00F)                       # leavel -16
BR(0xE0, "DONE")

# ---- the handler: refill, reconnect, re-arm. Entered with AH = buf.
LBL("HANDLER")
W(0xF00B)                       # enterl -16
W(0x0A23)                       # st AH,@(10,Y)  buf (the MessageId)
W(0x0A17); W(0x0234); W(0x0B27) # samples = buf + 2 -> slot 11
BSR("FILL")
ca.calln(W, BSR, ca.STUB['MessageSendLater'],
         al=('imm', TASK_PTR), ah=('slot', 10),
         stack=[('imm', 0), ('long', REFILL_MS)], stage='AL')
W(0xF00F)                       # leavel -16
BR(0xE0, "DONE")

# ---- FILL(slot10 = buf, slot11 = samples): regenerate and reconnect.
# Shared by the cave and the handler so the generator is lifted only once.
LBL("FILL")
W(0xF00B)                       # enterl -16
W(0x1A17); W(0x0A27)            # ld AL,@(26,Y) -> st AL,@(10,Y)   caller's slot 10
W(0x1B17); W(0x0B27)            # ld AL,@(27,Y) -> st AL,@(11,Y)   caller's slot 11

ca.calln(W, BSR, "NOISE", al=('slot', 11), ah=('imm', 510),
         stack=[('slot', 10)], stage='AL')

ca.calln(W, BSR, ca.STUB['KalimbaSendMessage'],
         al=('imm', 0x1072), ah=('imm', 8000),       # the rate probe77 proved
         stack=[('imm', 0), ('imm', 0), ('imm', 0)], stage='AL')

ca.call1(W, BSR, ca.STUB['StreamKalimbaSink'], al=('imm', 3))
W(0x0C27)                       # st AL,@(12,Y)  ksink3
W(0x0084); BR(0xF4, "FEXIT")
ca.call2(W, BSR, ca.STUB['StreamRegionSource'], al=('slot', 11), ah=('imm', 510))
W(0x0D27)                       # st AL,@(13,Y)  src
W(0x0084); BR(0xF4, "FEXIT")
ca.call2(W, BSR, ca.STUB['StreamConnect'], al=('slot', 13), ah=('slot', 12))
LBL("FEXIT")
W(0xF00F)                       # leavel -16
BR(0xE0, "DONE")

W(0x0000)                       # padding past the +-128 bsr encoding gap
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

# entry jump over the TaskData, then the TaskData itself once layout is known
entry_v = CODE_AT - CAVE
assert -128 <= entry_v <= 127
assert CAVE not in out and TASK_AT not in out and TASK_AT + 1 not in out
out[CAVE] = ((entry_v & 0xFF) << 8) | 0xE0
HANDLER_AT = label_addr["HANDLER"]
for k, v in enumerate(ca.taskdata_words(HANDLER_AT)):
    out[TASK_AT + k] = v
print("handler a=%#x, TaskData a=%#x -> data %#06x = %s"
      % (HANDLER_AT, TASK_AT, TASK_PTR,
         ' '.join('%04x' % w for w in ca.taskdata_words(HANDLER_AT))))

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
