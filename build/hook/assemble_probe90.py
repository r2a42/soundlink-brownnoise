#!/usr/bin/env python3
"""probe90: the one untested cell -- full enablement AND no prompt.

probe89 said **"connected to", no tone** (2026-10-01, owner). Every call
succeeded, `StreamConnect` included.

A decision rule had been written in advance: if probe89 reported success with no
tone, abandon the codec route. **That rule was wrong, and it is worth saying why
rather than following it.** It assumed the prompt was a neutral observer. It is
not: "connected to" being *spoken* means the firmware played audio through the
DAC microseconds after the cave returned, so the DAC and amplifier plainly work
at that instant -- and probes 75/76/77 established that the prompt engine's
`KalimbaLoad` **takes the audio path away from whatever holds it**, even for a
silent id. probe89's silence is therefore just as consistent with "the route
works and the prompt stole it" as with "the route is dead".

Laid out as a matrix, one cell has never been tried:

    probe  rate  gain  unmute  prompt    result
    86     -     -     -       deleted   silence
    88     -     yes   yes     deleted   silence
    89     yes   yes   yes     STOCK     "connected to", no tone
    90     yes   yes   yes     deleted   <- this probe

So probe90 is probe89 with **one change**: the prompt call at 0xAE4..0xAE6 becomes
three `nop`s again, so nothing can take the DAC back. Every call in it reported
success on hardware in probe89.

The ringtone array is probe77's, so a success is **28 seconds** -- no judging
short sounds. A crash is still obvious because the speaker restarts audibly.

**No music, nothing connected.**

    a long tone -> **standalone audio with no DSP at all.** Swap the ringtone for
                   StreamRegionSource over generated noise and it is brown noise.
    silence     -> now this means something, because probe89 proved every call in
                   the chain returns success. The codec sink accepts a source,
                   yields a transform, and produces no sound. Then the codec route
                   really is finished, and the DSP route is next: probe85 proved
                   the cave can load a .kap, and Bose's recipe at
                   0x1E40D-0x1E441 wires port 0 to the DAC and starts it.
"""

import sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

CAVE = 0x3E21D         # fixed by the hook's prefix fold at 0xAE0 (do not move)
REDIRECT_EDITS = [("0x6fff1", "0x04"), ("0x6fff3", "0xd7"), ("0x6fff5", "0x3b"),
                  ("0x6fff6", "0xe0"), ("0x6fff7", "0x01"),   # 0xae3 := bra +1
                  # 0xae4..0xae6 := three nops. probe89 proved every call in this
                  # chain succeeds, so the id has done its job; now nothing may
                  # take the DAC back.
                  ("0x6fff8", "0x00"), ("0x6fff9", "0x00"),
                  ("0x6fffa", "0x00"), ("0x6fffb", "0x00"),
                  ("0x6fffc", "0x00"), ("0x6fffd", "0x00")]
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

W(0xF00B)                       # enterl -16  (slots 0..13 usable, 14/15 = link)
BSR(BACK)                       # stock back-call (proven by probe37)

ca.call3(W, BSR, ca.STUB['StreamAudioSink'],
         al=('imm', 3), ah=('imm', 0), arg3=('imm', 0))
W(0x0A27)                       # st AL,@(10,Y)  sinkA
W(0x0084); BR(0xF4, "NOSINK")

# The step probe86 and probe88 both missed: a codec with no configured rate has
# no clock. Bose sets this at 0x1E41D before connecting.
ca.call3_long(W, BSR, ca.STUB['SinkConfigure'],
              al=('slot', 10), ah=('imm', 0x0301), arg3_32=8000)
W(0x0084); BR(0xF4, "NORATE")

ca.call3_long(W, BSR, ca.STUB['SinkConfigure'],
              al=('slot', 10), ah=('imm', 0x0303), arg3_32=15)      # gain, 0 dB
W(0x0084); BR(0xF4, "NOGAIN")

ca.call3_long(W, BSR, ca.STUB['SinkConfigure'],
              al=('slot', 10), ah=('imm', 0x0700), arg3_32=0)       # unmute
W(0x0084); BR(0xF4, "NOUNMUTE")

ca.call1(W, BSR, ca.STUB['StreamRingtoneSource'], al=('imm', NOTES_PTR))
W(0x0B27)                       # st AL,@(11,Y)  src
W(0x0084); BR(0xF4, "NOSRC")

ca.call2(W, BSR, ca.STUB['StreamConnect'], al=('slot', 11), ah=('slot', 10))
W(0x0084); BR(0xF4, "NOCONN")

W(0x0E14); BR(0xE0, "EXIT")     # 0x0E  "connected to"
LBL("NOCONN");   W(0x0C14); BR(0xE0, "EXIT")   # 0x0C  "connection lost"
LBL("NOSRC");    W(0x0A14); BR(0xE0, "EXIT")   # 0x0A  "connecting"
LBL("NOUNMUTE"); W(0x0114); BR(0xE0, "EXIT")   # 0x01  "connecting to"
LBL("NOGAIN");   W(0x0014); BR(0xE0, "EXIT")   # 0x00  "ready to connect"
LBL("NORATE");   W(0x0814); BR(0xE0, "EXIT")   # 0x08  "disconnected"
LBL("NOSINK");   W(0x0614)                     # 0x06  "lost"
LBL("EXIT")
W(0xF00F)                       # leavel -16

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

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe90_words.json", "w"), indent=0)
edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe90_brown.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe90_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> probe90_cmd.txt")
