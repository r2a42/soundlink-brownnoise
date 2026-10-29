#!/usr/bin/env python3
"""probe103: feed port 3 through TransformAdpcmDecode -- Bose's own recipe.

Two bugs were found in the region-source route, and both invalidate probes 82,
83, 84, 101 and 102.

## Bug 1: `StreamRegionSource` carries ONE BYTE per 16-bit word

Proven three independent ways:

* `sink_avrcp.c:111` declares `const uint8 avrcp_retrieve_media_attributes_basic[12]`
  and `:5108` passes `sizeof(...)` = 12. Bose's compiled copy is **12 whole words**
  at const 0x7F6E with length 0xC. So one `uint8` occupies one word and the length
  counts words.
* Bose's own `AvrcpPassthroughRequest` builder at 0x06C96-0x06CBB literally does
  `and AL,#0xff` before storing each byte in its own word, then calls
  `StreamRegionSource(buf, len+2)`.
* This compiler stores strings one character per word, and OBEX/PBAP hand
  `(string, strlen)` straight to the same trap (`docs/const-strings.md`).

`noise_fill` writes **16-bit** samples, one per word. So what actually reached the
DSP in every region-source probe was **the low byte of each sample** -- the top 8
bits discarded, and half the intended duration. probe83's +-28000 square became
0x60/0x20 byte pairs: a quiet, DC-offset buzz at twice the pitch. probe101's brown
noise became its own LSBs, which is **white**, with the brown tilt gone.

## Bug 2: probe102's refill could not reconnect

`stream.h:111` -- `StreamConnect` "will return zero if the source/sink stream is
connected to another stream." probe102 re-called `StreamKalimbaSink(3)` +
`StreamConnect` every 60 ms with no teardown. The ADK tears a tone down with
`StreamDisconnect` first (`csr_cvc_common_dsp_if.c:589`); probe102 never did.

> So `StreamRegionSource` was never shown to be a non-audio construct. Both
> negative results are explained by a unit error and a missing teardown, and
> `stream.h:191-195` says the opposite of the conclusion in so many words: a
> region source exists "to handle data ... using functions that expect a source,
> **e.g. StreamConnect()**".

## The fix is not to pack PCM better -- it is to send ADPCM

One byte per word is a crippling 0.5 samples/word for 16-bit PCM. For **IMA
ADPCM it is 2 samples per word -- 4x the density** -- and the ADK has a trap that
decodes it straight into this exact port. `voice_prompts_dsp_if.c:386-400`:

    Sink lSink = StreamKalimbaSink(TONE_VP_MIXING_DSP_PORT);        /* = 3 */
    PanicFalse(TransformStart(TransformAdpcmDecode(prompt_source, lSink)));

**That code is compiled into Bose's image twice**, at 0x22F9B and 0x23083, and the
second site is preceded by `KalimbaSendMessage(0x1072, rate)` then
`StreamKalimbaSink(3)` -- the order used below. Stub 0x156 is present.

And the decoder does the hard part for us. **IMA ADPCM is an accumulator**: each
nibble adds a signed step to the running output. Feeding it random signs therefore
integrates into a **random walk, which is brown noise by construction** -- a 1/f^2
spectrum with no filter on our side. `nib_fill` only has to produce nibbles.

    nibble = sign<<3 | magnitude
             sign       a fresh LFSR bit
             magnitude  forced into 4..7, so the decoder's step index climbs to
                        its ceiling and stays there -- i.e. loud

`build/noiseprobe/noise.c:nib_fill` is compiled by the ADK's own compiler and
lifted by `tools/liftfn.py` (70 words, a clean leaf). Verified in `tools/xapemu.py`
against a Python model: **0 mismatches in 64 words**, all words <= 0xFF so the
byte truncation is a no-op, all 128 nibbles magnitude 4..7, 73/128 signs set.

## Sustain, done the way the header says

    cave      buf = malloc(512)
              buf[0] = LFSR state   buf[1] = live transform handle
              FILL ; MessageSendLater(task, buf, 0, 110 ms) ; speak 0x0E

    handler(AH = buf):
              FILL ; MessageSendLater(task, buf, 0, 110 ms)      unconditional

    FILL      TransformDisconnect(buf[1])        <- the teardown probe102 lacked
              nib_fill(buf+2, 510, buf)          continues the LFSR, never restarts
              KalimbaSendMessage(0x1072, 8000)   the rate probe77 proved
              t = TransformAdpcmDecode(StreamRegionSource(buf+2, 510),
                                       StreamKalimbaSink(3))
              TransformStart(t) ; buf[1] = t

510 bytes = 1020 nibbles = **1020 samples = 127 ms at 8000 Hz**, refilled every
110 ms. The buffer pointer travels as the MessageId (probe100 proved it survives),
which is how a cave with nowhere to keep a global keeps state.

## This probe finally has a diagnosis channel

The prompt call is left **stock**, and `FILL` returns a bail id that the cave
speaks. So the owner's report names the failing call instead of being a judgement
about 127 ms of sound. The prompt will load `NowSpeakTTS.kap` and evict the
decoder as it did in probe75 -- but the refill timer re-creates the transform every
110 ms, so audio should resume once the prompt finishes.

**Phone CONNECTED, music PAUSED** -- probe77's proven conditions.

    "connected to" THEN sustained noise
        -> **the deliverable.** Brown noise by integration, software only.
    "connected to" and nothing
        -> all six calls succeeded and no audio came out. That is a real result:
           the transform exists but moves nothing, and `TransformPollTraffic`
           (stub 0x142) is then the next probe, not another guess.
    "disconnected"            -> KalimbaSendMessage FALSE: no .kap loaded, so the
                                 phone is not connected. Reconnect and retry.
    "voice prompts on"        -> StreamKalimbaSink(3) or StreamRegionSource
                                 returned 0. Both already succeeded in probe77
                                 and probe101, so one id covers the pair.
    "connecting to"           -> TransformAdpcmDecode returned 0. The trap is
                                 present but refused this source/sink pair.
    "connecting"              -> TransformStart returned FALSE.
    "lost"                    -> malloc(512) failed.
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

# ---- the generator, lifted from the linked image ----
LIFT = liftfn.lift('build/noiseprobe/noiseprobe', 'nib_fill')
assert not LIFT['problems'], LIFT['problems']
print('lifted nib_fill: %d words, %d items, %d labels'
      % (LIFT['size'], len(LIFT['items']),
         sum(1 for it in LIFT['items'] if it[0] == 'label')))

# Band 0 holds the entry jump and the 2-word TaskData; the code proper starts in
# band 1, because the hook's prefix fold pins the entry address and cannot be
# retargeted (docs/cave-frame.md, docs/message-task-abi.md).
BAND0 = [CAVE + k for k in range(3)]       # entry jump + the 2-word TaskData
assert all(blind(a) and in_run(a) for a in BAND0)
CODE_AT = CAVE + 3                        # no longer skips the rest of band 0
assert blind(CODE_AT) and in_run(CODE_AT), hex(CODE_AT)

TASK_AT = CAVE + 1
TASK_PTR = ca.const_addr(TASK_AT)
REFILL_MS = 110        # buffer holds 127 ms at 8000 Hz

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
W(0x0084); BR(0xF4, "NOMEM")

W(0x0A1B)                       # ld X,@(10,Y)
ca.load_al(W, ('imm', 0xACE1)); W(0x0026)      # buf[0] = LFSR state
ca.load_al(W, ('imm', 0));      W(0x0126)      # buf[1] = no live transform yet

BSR("FILL")                     # returns 0, or a bail id to speak
W(0x0084); BR(0xF0, "SPEAK")    # bne: FILL failed, AL already holds the id

# Hand the buffer pointer to the handler AS THE MESSAGE ID: a data pointer is 16
# bits, exactly a MessageId's width, and probe100 proved the id arrives intact.
ca.calln(W, BSR, ca.STUB['MessageSendLater'],
         al=('imm', TASK_PTR), ah=('slot', 10),
         stack=[('imm', 0), ('long', REFILL_MS)], stage='AL')
W(0x0E14)                       # ld AL,#0x0E  "connected to" = every call OK
BR(0xE0, "SPEAK")
LBL("NOMEM"); W(0x0614)         # 0x06  "lost"
LBL("SPEAK")
W(0xF00F)                       # leavel -16
BR(0xE0, "DONE")

# ---- the handler: tear down, refill, reconnect, re-arm. Entered with AH = buf.
# It runs from MessageLoop and cannot speak, so it ignores FILL's status.
LBL("HANDLER")
W(0xF00B)                       # enterl -16
W(0x0A23)                       # st AH,@(10,Y)  buf (the MessageId)
BSR("FILL")
ca.calln(W, BSR, ca.STUB['MessageSendLater'],
         al=('imm', TASK_PTR), ah=('slot', 10),
         stack=[('imm', 0), ('long', REFILL_MS)], stage='AL')
W(0xF00F)                       # leavel -16
BR(0xE0, "DONE")

# ---- FILL(caller slot10 = buf, slot11 = samples) -> AL = 0 or a bail id.
# Shared by the cave and the handler so the generator is lifted only once.
LBL("FILL")
W(0xF00B)                       # enterl -16
W(0x1A17); W(0x0A27)            # ld AL,@(26,Y) -> st AL,@(10,Y)   caller's slot 10
W(0x0234); W(0x0B27)            # samples = buf + 2 -> slot 11. buf[0] is the LFSR
                                # state, buf[1] the live transform handle.

# Tear the previous transform down first. probe102 omitted this and stream.h:111
# says every reconnect after the first was therefore refused.
W(0x0A1B)                       # ld X,@(10,Y)
W(0x0116)                       # ld AL,@(1,X)   buf[1] = live transform, or 0
W(0x0C27)                       # st AL,@(12,Y)
W(0x0084); BR(0xF4, "NOTEAR")
ca.call1(W, BSR, ca.STUB['TransformDisconnect'], al=('slot', 12))
LBL("NOTEAR")

# Regenerate the nibbles. The LFSR lives in buf[0], so each refill CONTINUES the
# sequence -- a replayed 127 ms buffer would buzz at 7.9 Hz; this does not.
ca.calln(W, BSR, "NIBS", al=('slot', 11), ah=('imm', 510),
         stack=[('slot', 10)], stage='AL')

# Arm the port-3 reader: codec_tones.asm:516 sets $aux_input_stream_available = 1
# inside this handler. 8000 Hz is the rate probe77 proved audible.
ca.calln(W, BSR, ca.STUB['KalimbaSendMessage'],
         al=('imm', 0x1072), ah=('imm', 8000),
         stack=[('imm', 0), ('imm', 0), ('imm', 0)], stage='AL')
W(0x0084); BR(0xF4, "R08")

ca.call1(W, BSR, ca.STUB['StreamKalimbaSink'], al=('imm', 3))
W(0x0C27)                       # st AL,@(12,Y)  ksink3
W(0x0084); BR(0xF4, "R12")

ca.call2(W, BSR, ca.STUB['StreamRegionSource'], al=('slot', 11), ah=('imm', 510))
W(0x0D27)                       # st AL,@(13,Y)  src -- 510 BYTES, one per word
W(0x0084); BR(0xF4, "R12")

# Bose's own two call sites, 0x22F9B and 0x23083: arg1 = source, arg2 = sink.
ca.call2(W, BSR, ca.STUB['TransformAdpcmDecode'], al=('slot', 13), ah=('slot', 12))
W(0x0927)                       # st AL,@(9,Y)   t
W(0x0084); BR(0xF4, "R01")

# transform.h:25-28: StreamConnect transforms start implicitly and must NOT be
# started; a TransformAdpcmDecode one must be.
ca.call1(W, BSR, ca.STUB['TransformStart'], al=('slot', 9))
W(0x0084); BR(0xF4, "R0A")

W(0x0A1B)                       # ld X,@(10,Y)
W(0x0917)                       # ld AL,@(9,Y)
W(0x0126)                       # st AL,@(1,X)   buf[1] = t, for the next teardown
W(0x0014); BR(0xE0, "FEXIT")    # ld AL,#0  success
LBL("R08"); W(0x0814); BR(0xE0, "FEXIT")   # 0x08  "disconnected"
LBL("R12"); W(0x1214); BR(0xE0, "FEXIT")   # 0x12  "voice prompts on"
LBL("R01"); W(0x0114); BR(0xE0, "FEXIT")   # 0x01  "connecting to"
LBL("R0A"); W(0x0A14)                      # 0x0A  "connecting"
LBL("FEXIT")
W(0xF00F)                       # leavel -16
BR(0xE0, "DONE")

W(0x0000)                       # padding past the +-128 bsr encoding gap
LBL("NIBS")
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
assert seen.get(CAVE) == CODE_AT, (hex(CAVE), hex(CODE_AT), seen.get(CAVE))
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
