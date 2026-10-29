#!/usr/bin/env python3
"""probe109: the standalone gate. One press, one question, no audio needed.

A plan rebuilt from the full disassembly (`docs/hook-sites.md`,
`build/analysis/full-disasm.txt`) says every remaining route runs through one
unproven fact, and that nothing else is worth testing until it is settled:

> **Does the firmware load a DSP -- making Kalimba port 3 live -- with no device
> paired at all?**

If yes, the owner's standing requirement ("standalone, NO OTHER DEVICES") is
satisfiable and the rest is engineering. If no, the only standalone option left is a
runtime partition write, which is the one route in this project whose brick risk is
worse than a recoverable wedge.

## Why it is not already answered

probe82 ran standalone and spoke **"disconnected"**, which is `KalimbaSendMessage`
returning FALSE -- no `.kap` loaded. That looks like a no, but it is not: probe82
called `KalimbaSendMessage` from the **button handler**, before any prompt had played.
The prompt is what loads the DSP, and it only starts after the cave returns. probe82
measured the wrong moment.

`voice_prompts_dsp_if.c:85-118` says a **compressed** prompt takes `playStandalone`,
which loads a DSP. Bose's prompts are compressed -- they are decoded by
`NowSpeakTTS.kap`, which is why a prompt reload stole the tone port in probe75. And
the disassembly shows the loader path `fn_1c2c9` / `fn_1e3c5`
(`FileFind -> VmDeepSleepEnable -> KalimbaLoad -> MessageKalimbaTask ->
KalimbaSendMessage(0x7000)`) **contains no Bluetooth dependency anywhere**. So the
capability exists; what has never been checked on hardware is whether it fires with
nothing paired.

## The probe

    cave      MessageSendLater(task, 1, 0, 600 ms)
              return prompt id 0x0E       -> the firmware loads the prompt DSP and
                                             speaks "connected to"

    handler   KalimbaSendMessage(0x1072, 8000, NO_EXTRA_GAIN, 0, 0)
              TRUE  -> bsr 0xdf7f(0x13)   "voice prompts off"
              FALSE -> bsr 0xdf7f(0x08)   "disconnected"

That is the whole thing: **no malloc, no generator, no transform, no region source,
no refill.** Nothing here can leak, and nothing can wedge a DAC, because the cave
never touches one. 600 ms puts the handler inside the prompt, by which time the
loader has run.

## The new capability this uses

`0xdf7f` -- the prompt engine -- is directly `bsr`-able: **id in AL, nothing required
in X, and it returns** (it does its own `enterl -7`; 13 callers; `docs/hook-sites.md`).
Every probe so far could only report from the button handler, by leaving an id in AL
for the stock call at `0x0AE4`. A timer handler had no voice at all, which is why
probes 98-106 had to infer what their handlers did. **This is the first probe whose
handler speaks for itself**, and if it works every future handler can be diagnosed
directly.

## The trigger, and why it is reliable in exactly this case

The hook at `0x0AE0` sits behind `cmp AL,#0x4003` at `0x00ace`, so it runs only on
EventUsrEnterPairing (`docs/hook-sites.md`). That has been the cause of several dead
presses -- but it is *most* reliable standalone: **with nothing connected, a long
press of the Bluetooth button unambiguously means "enter pairing"**, which is exactly
event 0x4003. The requirement that makes this probe interesting is the same one that
makes its trigger dependable.

**NOTHING PAIRED. Disconnect the computer's Bluetooth entirely, then long-press the
Bluetooth button once.**

    "connected to" then "voice prompts off"
        -> **the gate opens.** A DSP loads with nothing paired, so port 3 is live
           standalone and the brown-noise route needs no paired device. Next probe
           puts the ADPCM transform on that port.
    "connected to" then "disconnected"
        -> no DSP is loaded even while a prompt plays. The prompt path uses
           `VoicePromptsNoDspPlay` straight to the DAC, port 3 never exists
           standalone, and the only standalone route left is the partition write --
           which I would not attempt without asking first.
    "connected to" and nothing else
        -> the handler ran but `bsr 0xdf7f` did not speak. That is a real result too:
           it means a handler cannot use the prompt engine, and every future handler
           has to report some other way.
    "ready to connect" or silence
        -> the cave did not run; the press was not EventUsrEnterPairing. Make sure
           nothing is paired and the speaker is not already in pairing mode.
    a crash or reboot
        -> `bsr 0xdf7f` from a MessageLoop handler is not safe. Worth knowing cheaply,
           and recoverable.
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
CONST_A = 0x39BE2                      # const pool start, in `a` space
CONST_N = w[7]
# SCAN WINDOW NARROWED 2026-10-05. This used to sweep the WHOLE const pool with a 16-word
# threshold, advertising "262 writable words". probe130 used 234 of them and CRASHED THE
# SPEAKER ON BOOT: 55 words landed outside the hardware-proven window, 9 of them in the run
# 0x3aa51..0x3aa67 whose data address 0x8280 is loaded by fn_0aaa1 at 0x0aaa5 and shipped as
# a message payload. Being zero in the official image and inside a DFU blind window -- the
# only two things this scan checked -- is NOT sufficient. ZERO DOES NOT MEAN UNREAD.
# docs/cave-budget.md has recorded the real budget, 197 words in 0x3E200..0x3E400, since
# 2026-09-30. tools/caveguard.py enforces it and tools/preflight.py calls it.
SCAN_LO, SCAN_HI, MIN_RUN = 0x3E200, 0x3E400, 40
_runs = []
_i = SCAN_LO
while _i < SCAN_HI:
    if code[_i] == 0:
        j = _i
        while j < SCAN_HI and code[j] == 0: j += 1
        if j - _i >= MIN_RUN: _runs.append((_i, j))
        _i = j
    else:
        _i += 1
def in_run(cw): return any(a <= cw < b for a, b in _runs)

# Band order: the rest of CAVE's own run, then every later run, then the runs
# before CAVE. Layout must begin at CAVE because that is what the hook branches to.
_ORDER = []
for a, b in _runs:
    if a <= CAVE < b: _ORDER.append((CAVE, b))
for a, b in _runs:
    # Only runs a 1-word connector can reach from the end of the previous band.
    # The three runs around the cave qualify (gaps of 26 and 12 words). 0x3EAD2
    # is 1746 words past 0x3E400 and does not, so it stays out until the layout
    # can reserve a wider branch for the hop.
    if a > CAVE:
        _ORDER.append((a, b))
for a, b in _runs:
    if b <= CAVE:
        _ORDER.append((a, b))
assert _ORDER and _ORDER[0][0] == CAVE, 'CAVE is not inside a zero run'
# Maximal runs of consecutive writable words, in band order. The layout walks
# this list; a connector branch carries control from the end of one band to the
# start of the next, wherever in the pool that is.
_BANDS = []
for lo, hi in _ORDER:
    _a = lo
    while _a < hi:
        if blind(_a):
            _b = _a
            while _b < hi and blind(_b): _b += 1
            _BANDS.append((_a, _b)); _a = _b
        else:
            _a += 1
_BEND = {b: k for k, (a, b) in enumerate(_BANDS)}
assert _BANDS[0][0] == CAVE, hex(_BANDS[0][0])
print('cave budget: %d runs, %d bands, %d writable words'
      % (len(_runs), len(_BANDS), sum(b - a for a, b in _BANDS)))

def next_blind(pc):
    """Band-order successor: if pc is one past a filled band, the next band's
    first word; if pc is inside a band, pc itself."""
    if pc in _BEND:
        k = _BEND[pc] + 1
        assert k < len(_BANDS), 'cave exhausted: %d writable words is not enough'             % sum(y - x for x, y in _BANDS)
        return _BANDS[k][0]
    for x, y in _BANDS:
        if x <= pc < y:
            return pc
    raise AssertionError('next_blind off the map at %#x' % pc)

# ---- the generator, lifted from the linked image ----
# No generators: this probe makes no sound, it asks one question.

# Band 0 holds the entry jump and the 2-word TaskData; the code proper starts in
# band 1, because the hook's prefix fold pins the entry address and cannot be
# retargeted (docs/cave-frame.md, docs/message-task-abi.md).
BAND0 = [CAVE + k for k in range(3)]       # entry jump + the 2-word TaskData
assert all(blind(a) and in_run(a) for a in BAND0)
CODE_AT = CAVE + 3                        # no longer skips the rest of band 0
assert blind(CODE_AT) and in_run(CODE_AT), hex(CODE_AT)

TASK_AT = CAVE + 1
TASK_PTR = ca.const_addr(TASK_AT)
DELAY_MS = 600          # inside the prompt, after its loader has run
TONE_RATE = 8000        # the rate probe77 and probe104 both proved
NO_EXTRA_GAIN = 2       # audio_plugin_if.h:194; Bose sets it on every path
SPEAK = 0xDF7F          # the prompt engine: id in AL, nothing in X, and it returns

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))

BACK = 0xE06D          # the call the hook at 0xae0 displaced

W(0xF00B)                       # enterl -16  (slots 0..13 usable, 14/15 = link)
BSR(BACK)                       # stock back-call (proven by probe37)

# Schedule the question, then ask the FIRMWARE to load a DSP by requesting a prompt.
# We never load or wire anything ourselves -- that is what wedged probes 96 and 97.
ca.calln(W, BSR, ca.STUB['MessageSendLater'],
         al=('imm', TASK_PTR), ah=('imm', 1),
         stack=[('imm', 0), ('long', DELAY_MS)], stage='AL')
W(0x0E14)                       # ld AL,#0x0E  "connected to"
W(0xF00F)                       # leavel -16, which returns

# ---- the handler, 600 ms later, mid-prompt. THE MEASUREMENT.
LBL("HANDLER")
W(0xF00B)                       # enterl -16

# KalimbaSendMessage returns FALSE when no .kap is loaded. If it is TRUE here, with
# nothing paired, then the prompt brought a DSP up and port 3 exists standalone.
ca.calln(W, BSR, ca.STUB['KalimbaSendMessage'],
         al=('imm', 0x1072), ah=('imm', TONE_RATE),
         stack=[('imm', NO_EXTRA_GAIN), ('imm', 0), ('imm', 0)], stage='AL')
W(0x0084); BR(0xF4, "NODSP")

W(0x1314)                       # ld AL,#0x13  "voice prompts off" = a DSP IS loaded
BSR(SPEAK)                      # first use of the prompt engine from a handler
BR(0xE0, "HEXIT")
LBL("NODSP")
W(0x0814)                       # ld AL,#0x08  "disconnected" = no DSP
BSR(SPEAK)
LBL("HEXIT")
W(0xF00F)                       # leavel -16, which returns

# ---- layout (proven machinery, probes 67-77) ----
bsr_size, br_size = {}, {}
label_addr = {}
def needs_follow(item):
    k = item[0]
    if k == "bsr": return True
    if k == "br": return item[1] != 0xE0
    return (item[1][-1] & 0xFF) not in (0xE2, 0x0F)   # rts, leavel
def bsr2_encodable(v):
    for aa in range(max(-128, (v >> 8) - 2), min(128, (v >> 8) + 3)):
        if aa == 0: continue
        b = v - aa * 256
        if -128 <= b <= 127: return True
    return False
def br2_encodable(v):
    for aa in range(max(-128, (v >> 8) - 2), min(128, (v >> 8) + 3)):
        if aa == 0: continue
        if -128 <= v - aa * 256 <= 127: return True
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
        nb_probe = next_blind(band_end)
        cs = 1 if -128 <= nb_probe - addr <= 127 else 2
        if addr + need > band_end - (cs - 1):
            if addr >= band_end:
                addr = next_blind(band_end); continue
            nb = nb_probe
            assert blind(addr) and in_run(addr), (hex(addr), "connector slot not blind")
            assert addr + cs <= band_end, (
                'no room for a %d-word connector at %#x (band ends %#x)'
                % (cs, addr, band_end))
            extra[addr] = (nb, cs)
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
            # Each candidate size is tested with ITS OWN last-word displacement,
            # because that is what will actually be encoded.
            want = (1 if -128 <= tgt - a <= 127
                    else 2 if br2_encodable(tgt - (a + 1))
                    else 3)
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
        elif br_size[i] == 2:
            # Displacement is relative to the LAST word of the instruction, exactly as
            # for bsr. Using `tgt - a` here targeted every multi-word branch ONE WORD
            # SHORT and is what crashed probe131/132: proven by an independent boundary
            # census of Bose's 2103 multi-word branches (a+ln-1+v: 100%, a+v: 42%).
            v = tgt - (a + 1)
            for aa in range(max(-128, (v >> 8) - 2), min(128, (v >> 8) + 3)):
                if aa == 0: continue
                bb = v - aa * 256
                if -128 <= bb <= 127:
                    out[a] = (aa & 0xFF) << 8
                    out[a+1] = ((bb & 0xFF) << 8) | op
                    break
            else:
                raise AssertionError(('br2', hex(a), hex(tgt)))
        else:
            v = tgt - (a + 2)          # last-word relative, as for bsr
            done = False
            for aa in range(-128, 128):
                if aa == 0: continue
                for bb in range(-128, 128):
                    if bb == 0: continue
                    cc = v - aa * 65536 - bb * 256
                    if -128 <= cc <= 127:
                        out[a] = (aa & 0xFF) << 8; out[a+1] = (bb & 0xFF) << 8
                        out[a+2] = ((cc & 0xFF) << 8) | op
                        done = True; break
                if done: break
            assert done, ('br3', hex(a), hex(tgt))
for cslot, (nb, cs) in extra.items():
    v = nb - cslot
    if cs == 1:
        assert -128 <= v <= 127, (hex(cslot), hex(nb), v)
        out[cslot] = ((v & 0xFF) << 8) | 0xE0
    else:
        assert cslot + 1 not in out, hex(cslot + 1)
        for aa in range(max(-128, (v >> 8) - 2), min(128, (v >> 8) + 3)):
            if aa == 0: continue
            bb = v - aa * 256
            if -128 <= bb <= 127:
                out[cslot] = (aa & 0xFF) << 8
                out[cslot + 1] = ((bb & 0xFF) << 8) | 0xE0
                break
        else:
            raise AssertionError(('connector', hex(cslot), hex(nb), v))

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
for cslot, (nb, cs) in extra.items():
    intended[cslot] = (nb, 'connector')
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
