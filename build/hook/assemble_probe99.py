"""probe99: give the handler a voice. Did the timer fire at all?

probe98: **"connected to" and nothing** (2026-10-01, owner). The cave spoke, so
`MessageSendLater` was reached -- but the handler is silent by construction, so that
result cannot distinguish:

* the timer never fired (bad `TaskData`, `MessageSendLater` refused, message never
  delivered), from
* the handler ran and a call failed, from
* the handler ran, connected, and nothing mixed.

Three very different problems, one indistinguishable silence. That is the same trap
probes 86/88/90 fell into on the codec route, and it is avoidable here.

## The change: the handler reports through the prompt player

`0xDF7F` is Bose's prompt player -- `enterl -7`, request id in AL, passes it to
`0xDF01` -- and this project has been using it indirectly since probe37, because the
hook returns into it. A cave can simply **call it**, exactly as it calls the stock
back-call `0xE06D`. So the handler now ends with `ld AL,#id ; bsr 0xDF7F` and names
its own outcome:

    reached the handler, all three calls fine   -> 0x16  "english"
    StreamKalimbaSink(3) returned 0             -> 0x12  "voice prompts on"
    StreamRingtoneSource returned 0             -> 0x09  "mobile device not found"
    StreamConnect refused                       -> 0x13  "voice prompts off"

"english" is unmistakable and unlike anything the cave itself says.

**This costs the tone, and that is the point.** The handler's own prompt reloads the
`.kap` and will destroy the connection it just made -- so probe99 is not trying to
make a sound. It is establishing whether the timer and the handler work at all,
which probe98 left unknown.

## Reading it

    "connected to" ... "english"
        -> **the timer fired, the handler ran, and all three calls succeeded.**
           Everything mechanical works and the remaining problem is purely
           acoustic: either 300 ms is the wrong moment, or the prompt's .kap does
           not mix port 3. probe100 then drops the handler's voice and sweeps the
           delay.
    "connected to" ... "voice prompts on" / "mobile device not found" /
    "voice prompts off"
        -> the handler ran and that call failed, named exactly.
    "connected to" and still nothing
        -> **the handler never ran.** The timer is the problem, not the audio: the
           TaskData, the message id, or MessageSendLater itself. The TaskData reads
           back correctly on the device (`0003 e265` for a handler at 0x3E265), so
           the next suspect would be the delivery rather than the pointer.
    a wedge
        -> calling the prompt player from a message handler is unsafe. Recovery:
           **hold POWER + VOICE ASSISTANT ~10 s.**

**No music, nothing connected.**
"""
import sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca

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


# ---- the ringtone, from app/ringtone/ringtone_if.h and ringtone_notes.h ----
# Values cross-checked by running the ADK's own preprocessor over the macros
# (xap-local-xap-gcc -E), not by reading the header by eye.
SEQ_CONTROL = 0x8000
def TEMPO(t):   return SEQ_CONTROL | (1 << 12) | t      # crotchets/min
def VOLUME(v):  return SEQ_CONTROL | (2 << 12) | v      # 8-bit
def TIMBRE(t):  return SEQ_CONTROL | (3 << 12) | t      # 1 = square
def DECAY(d):   return SEQ_CONTROL | (4 << 12) | d      # /16 fixed point
END = SEQ_CONTROL | (0 << 12)
def NOTE(pitch, length):  return (pitch << 7) | length  # pitch = MIDI number
A4, REST = 57, 127                                      # A4 = 220 Hz
SEMIBREVE, CROTCHET = 1, 4                              # length is a DIVISOR

# 7 semibreves at 60 crotchets/min = 7 * 4 s = 28 s, max volume, square wave,
# decay 0xFF (15.9) so each note holds its level instead of dying away.
# Untied, so every note restarts at full volume -- seven chances to be heard.
# 5 semibreves rather than probe77's 7: band 0 is 14 words and the 2-word
# TaskData has to live there too. 5 x 4 s = 20 seconds instead of 28.
NOTES = ([TEMPO(60), DECAY(0xFF), VOLUME(0xFF), TIMBRE(1)]
         + [NOTE(A4, SEMIBREVE)] * 5
         + [NOTE(REST, CROTCHET), END])
assert NOTES[:4] == [0x903C, 0xC0FF, 0xA0FF, 0xB001], [hex(v) for v in NOTES]
assert NOTES[4] == 0x1C81 and NOTES[-2:] == [0x3F84, 0x8000]
assert len(NOTES) == 11, len(NOTES)

BAND0 = [CAVE + k for k in range(14)]
assert all(blind(a) and in_run(a) for a in BAND0)
NOTES_AT = CAVE + 1
CODE_AT = next_blind(BAND0[-1] + 1)
assert CODE_AT == CAVE + 32, hex(CODE_AT)
NOTES_PTR = ca.const_addr(NOTES_AT)
TASK_AT = NOTES_AT + len(NOTES)          # 2 words, still inside band 0
assert TASK_AT + 1 <= BAND0[-1], 'TaskData does not fit in band 0'
TASK_PTR = ca.const_addr(TASK_AT)
WAKE_ID = 0x0001                         # our own message id; any value works
DELAY_MS = 300                           # mid-prompt, while the DSP path is up

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))

BACK = 0xE06D          # the call the hook at 0xae0 displaced

W(0xF00B)                       # enterl -16  (slots 0..13 usable, 14/15 = link)
BSR(BACK)                       # stock back-call (proven by probe37)

# Schedule ourselves. MessageSendLater(task, id, message=0, delay) -- the 4-arg
# form, with the delay as a 32-bit value, high word first. First use in this
# project of machinery docs/message-task-abi.md derived long ago.
ca.send_later(W, BSR, TASK_PTR, WAKE_ID, delay_ms=DELAY_MS)

# Then ask the firmware for a prompt. THIS is what brings the audio path up:
# it loads a .kap, wires it to the DAC and starts it -- all the things probes
# 95-97 proved we must not do ourselves.
W(0x0E14)                       # ld AL,#0x0E  "connected to"
W(0xF00F)                       # leavel -16
BR(0xE0, "DONE")                # jump over the handler

# ---- the handler, entered from MessageLoop ~300 ms later.
# Callback ABI: Task in AL, MessageId in AH, Message at @(n,Y). We need none of
# them. By now the firmware owns a running DSP wired to the DAC, so all we do is
# add a source to its tone port -- probe75/77's configuration exactly.
LBL("HANDLER")
W(0xF00B)                       # enterl -16

ca.call1(W, BSR, ca.STUB['StreamKalimbaSink'], al=('imm', 3))
W(0x0A27)                       # st AL,@(10,Y)  ksink3
W(0x0084); BR(0xF4, "HNOKS3")

ca.call1(W, BSR, ca.STUB['StreamRingtoneSource'], al=('imm', NOTES_PTR))
W(0x0B27)                       # st AL,@(11,Y)  src
W(0x0084); BR(0xF4, "HNORT")

ca.call2(W, BSR, ca.STUB['StreamConnect'], al=('slot', 11), ah=('slot', 10))
W(0x0084); BR(0xF4, "HNOCONN")

# ---- THE CHANGE: the handler names its own outcome through Bose's prompt player
# at 0xDF7F (enterl -7, request id in AL). This costs the tone -- the prompt
# reloads the .kap -- which is accepted: probe98 could not tell "never ran" from
# "ran and failed", and that is the question.
W(0x1614); BSR(0xDF7F)          # 0x16 "english" -- everything worked
BR(0xE0, "HEXIT")
LBL("HNOKS3");   W(0x1214); BSR(0xDF7F); BR(0xE0, "HEXIT")   # 0x12 voice prompts on
LBL("HNORT");    W(0x0914); BSR(0xDF7F); BR(0xE0, "HEXIT")   # 0x09 mobile device not found
LBL("HNOCONN");  W(0x1314); BSR(0xDF7F)                      # 0x13 voice prompts off
LBL("HEXIT")
W(0xF00F)                       # leavel -16
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

# The entry jump over the data, and the data. `bra` leaves X -- the link
# register the hook's `bsr` just set -- untouched, so the cave can still return.
assert CAVE not in out and not any(NOTES_AT + k in out for k in range(len(NOTES)))
entry_v = CODE_AT - CAVE
assert -128 <= entry_v <= 127
out[CAVE] = ((entry_v & 0xFF) << 8) | 0xE0
for k, v in enumerate(NOTES):
    out[NOTES_AT + k] = v
# The TaskData can only be written after layout, because it holds the handler's
# own address: { hwrd(a), lwrd(a) }, high word first (docs/message-task-abi.md).
HANDLER_AT = label_addr["HANDLER"]
for k, v in enumerate(ca.taskdata_words(HANDLER_AT)):
    assert TASK_AT + k not in out
    out[TASK_AT + k] = v
print("handler at a=%#x, TaskData at a=%#x -> data %#06x = %s"
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
        elif op in (0xE0, 0xF0, 0xF4, 0xF8): seen[a] = (a + v) & 0x3FFFF
for a, (tgt, kind) in intended.items():
    assert seen.get(a) == (tgt & 0x3FFFF), (hex(a), kind, hex(tgt), seen.get(a))
assert seen.get(CAVE) == CODE_AT, (hex(CAVE), seen.get(CAVE))
for i, item in enumerate(prog):
    if item[0] != "label":
        assert addrs[i] in dstarts, (hex(addrs[i]), "boundary")
print("decode-verify: all branches OK, boundaries OK")

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe99_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe99_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe99_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe99_cmd.txt")
