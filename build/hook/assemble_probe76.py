#!/usr/bin/env python3
"""probe76: stop the voice prompt from stealing the tone port.

**probe75 made the speaker play our tone** (2026-09-30, owner, verified twice):
a brief 220 Hz square wave, then "connected to". And the pair of presses
settled the precondition exactly:

    no music playing  -> "disconnected"   (KalimbaSendMessage FALSE, no .kap)
    music playing     -> TONE, then "connected to"

So the audio path is open end to end. The DSP is loaded while A2DP is active,
it accepts `MESSAGE_SET_TONE_RATE`, and it mixes a ringtone we flashed into our
own cave padding out through the speaker. That is the project's core question
answered: software only, our own sound, on a button press.

## Why it was brief, and this is readable straight off the hook

The prompt played *cleanly straight after the tone*, so the DSP was available
the whole time -- the tone was not cut off by the DSP going away. It stopped
when the prompt started. Disassembling the hook site shows why:

    0x0acd  ld AL,@(12,Y)        ; the sink event
    0x0ace  cmp AL,#0x4003       ; EventUsrEnterPairing
    0x0ad0  bne +836
    0x0ae0  bsr 0xe06d           <== the call our cave replaced
    0x0ae3  ld AL,#0x35          <== REDIRECT_EDITS makes this a no-op, so our
                                     cave's AL survives into the next call
    0x0ae4  bsr 0xdf7f           <== the prompt player: plays request id AL

**Every cave so far has ended by asking the firmware to play a voice prompt**,
and the voice-prompt path takes Kalimba port 3 for itself -- it is the same
`TONE_VP_MIXING_DSP_PORT`. It disconnects whatever is there and connects its
own source, destroying our transform. The reporting channel this project has
relied on for 40 probes is in direct competition with the thing being built.

## The one change

`docs/request-id-catalog.md` has **seven owner-verified silent ids**: 0x02,
0x03, 0x05, 0x07, 0x0F, 0x1A and 0x1D played nothing at all during probe38's
sweep of the whole corpus. So the success path asks for an empty prompt and
every bail path keeps its spoken one. The diagnostic channel survives for
exactly the cases that still need it.

    success -> id 0x02, silent.  Everything else unchanged from probe75.

    a full ~28 s tone, no speech | the prompt was the thief. Loud, sustained,
                                 | software-generated sound on a button press.
    a brief tone, no speech      | something else truncates it -- most likely
                                 | pairing tearing down A2DP and with it the
                                 | DSP. The answer is then our own KalimbaLoad.
    a brief tone, then speech    | an "empty" id still drives the prompt engine
                                 | into port 3. Nop out 0xAE4 instead.
    "disconnected"               | no music was playing; press again with music.

Still requires music playing, because only then is a .kap loaded. Making the
sound standalone means loading one ourselves -- `KalimbaLoad` (stub 0x1B9),
following Bose's recipe at 0x1E3E8. That is the next architecture, not this
probe.
"""

import sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

CAVE = 0x3E21D         # fixed by the hook's prefix fold at 0xAE0 (do not move)
REDIRECT_EDITS = [("0x6fff1", "0x04"), ("0x6fff3", "0xd7"), ("0x6fff5", "0x3b"),
                  ("0x6fff6", "0xe0"), ("0x6fff7", "0x01")]   # 0xae3 := bra +1
AREA0 = 0x6EA30

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
NOTES = ([TEMPO(60), DECAY(0xFF), VOLUME(0xFF), TIMBRE(1)]
         + [NOTE(A4, SEMIBREVE)] * 7
         + [NOTE(REST, CROTCHET), END])
assert NOTES[:4] == [0x903C, 0xC0FF, 0xA0FF, 0xB001], [hex(v) for v in NOTES]
assert NOTES[4] == 0x1C81 and NOTES[-2:] == [0x3F84, 0x8000]
assert len(NOTES) == 13, len(NOTES)

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

# Band 0 (14 blind words from CAVE) holds a jump over the data plus the notes;
# the code proper starts in band 1. The hook's target address is fixed, so the
# data cannot simply go first -- hence the jump.
BAND0 = [CAVE + k for k in range(14)]
assert all(blind(a) and in_run(a) for a in BAND0)
NOTES_AT = CAVE + 1
CODE_AT = next_blind(BAND0[-1] + 1)
assert CODE_AT == CAVE + 32, hex(CODE_AT)
NOTES_PTR = ca.const_addr(NOTES_AT)

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))

BACK = 0xE06D          # the call the hook at 0xae0 displaced

W(0xF80B)                       # enterl -8
BSR(BACK)                       # stock back-call (proven by probe37)

# The one new trap: a Source over 13 const words in our own cave.
# The one new call: tell the .kap a mono 8 kHz tone is coming. Arguments
# 3..5 go in @(0,Y)..@(2,Y) and are all zero, which is MONO_PROMPT without
# NO_EXTRA_GAIN -- i.e. extra gain on, the loudest of the documented options.
# Staged through AL, which is the emission Bose's own code at 0x31A86 uses.
ca.calln(W, BSR, ca.STUB['KalimbaSendMessage'],
         al=('imm', 0x1072), ah=('imm', 8000),
         stack=[('imm', 0), ('imm', 0), ('imm', 0)], stage='AL')
W(0x0084); BR(0xF4, "NODSP")    # returns bool: FALSE means no .kap is loaded

# Proven call (probe65, probe74), at Bose's own tone port.
ca.call1(W, BSR, ca.STUB['StreamKalimbaSink'], al=('imm', 3))
W(0x0527)                       # st AL,@(5,Y)  ksink
W(0x0084); BR(0xF4, "NULLSINK")

# Proven by probe74: a const pointer into the cave is an acceptable Source.
ca.call1(W, BSR, ca.STUB['StreamRingtoneSource'], al=('imm', NOTES_PTR))
W(0x0427)                       # st AL,@(4,Y)  src
W(0x0084); BR(0xF4, "NULLSRC")

ca.call2(W, BSR, ca.STUB['StreamConnect'], al=('slot', 4), ah=('slot', 5))
W(0x0084); BR(0xF4, "NOCONN")
W(0x0214); BR(0xE0, "EXIT")     # ld AL,#0x02  SILENT: do not take port 3
LBL("NOCONN");   W(0x0C14); BR(0xE0, "EXIT")   # ld AL,#0x0C  "connection lost"
LBL("NULLSRC");  W(0x0A14); BR(0xE0, "EXIT")   # ld AL,#0x0A  "connecting"
LBL("NODSP");    W(0x0814); BR(0xE0, "EXIT")   # ld AL,#0x08  "disconnected"
LBL("NULLSINK"); W(0x0614)                     # ld AL,#0x06  "lost"
LBL("EXIT")
W(0xF80F)                       # leavel -8

# ---- layout (proven machinery, probes 67-73) ----
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

lo, hi = min(out), max(out)
print("notes at a=%#x -> data %#06x, %d words; code from %#x"
      % (NOTES_AT, NOTES_PTR, len(NOTES), CODE_AT))
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
print("decode-verify: entry jump OK, all branches OK, boundaries OK")

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe76_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe76_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe76_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe76_cmd.txt")
