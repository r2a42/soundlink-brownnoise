#!/usr/bin/env python3
"""probe14: PCM LOUDNESS PROBE via StreamAudioSink (codec raw sink).
press-ON: beep, StreamAudioSink(hw=CODEC) -> sink, write one chunk of
full-scale square-wave PCM (±16000, sign flips every 8 samples), arm the
0x4003 timer with the PCM sink as msg. timer: claim 64 words -> if ok,
write 64 more samples, flush, re-arm (backpressure-adaptive pacing).
press-OFF: CancelFirst (codec sink stays reserved until reboot — probe!).
Answers ONE question: is the raw codec PCM path LOUD? (tone path isn't).

Architecture (MessageSendLater/CancelFirst ABI decoded this session:
  raw trap 0x62: @(0,Y)=msg_lo @(1,Y)=msg_hi @(2,Y)=delay, AL=task, AH=id
  raw trap 0x66: AL=task, AH=id
  app task TaskData = global 0x512 (button manager sends 0x4003 to it;
  msg value at that site = 0). Dispatcher envelope: id=@(12,Y),
  msg_lo=@(13,Y), msg_hi=@(14,Y) -> cave (entered via 0xae0 bsr, frame
  -8) reads id=@(20,Y), msg_lo=@(21,Y), msg_hi=@(22,Y).

  THE SINK RIDES IN THE TIMER MESSAGE: no RAM storage anywhere.
   PRESS (msg_lo==0): toggle 0x56b bit11.
     ON : TONE(0x4946) beep, AH:AL = feed sink; FEED_CTRL [VOL 0xA0FF,
          TIMBRE 0xB002 saw, TEMPO 0x90F0]; FEED 2 notes; arm timer
          MessageSendLater(0x512, 0x4003, msg=sink, delay=250).
     OFF: MessageCancelFirst(0x512, 0x4003); stream starves.
   TIMER (msg_lo!=0 = the sink): FEED 2 notes into msg sink; re-arm with
     same sink. Claim-fail = backpressure OR dead stream -> still re-arm;
     the loop ends only via OFF-press (CancelFirst).
  Exit always X=0xaed (post-flow skipped; gate stays open).

Notes 0x1408/0x1688/0x1A08/0x1C18 = MIDI 40/45/52/57 = 82/110/165/220 Hz
quavers (probe12's 55-98 Hz were perceptually ~25 dB down; saw + vol 255
+ higher band fixes the "super soft" field report).
"""
import sys, json, subprocess

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

TONE = 0x4946
CAVE = 0x3E21D
SENDLATER, CANCELFIRST = 0x62, 0x66
CLAIM, MAP, FLUSH = 0x0DE, 0x0E2, 0x0E6
ASINK = 0x16A                                  # StreamAudioSink (trap 110)
APP_TASK = 0x512
VA_ID = 0x4003
TICK_MS = 250
NOTES = (0x1408, 0x1688, 0x1A08, 0x1C18)      # feed rotates 2 at a time? no: fixed pair per call
FEED_NOTES = (0x1408, 0x1A08)                 # 82.4 / 164.8 Hz quavers per tick
CTRL_WORDS = (0xA0FF, 0xB002, 0x90F0)         # VOLUME 255, TIMBRE saw, TEMPO 240
REDIRECT_EDITS = [("0x6fff1", "0x04"), ("0x6fff3", "0xd7"), ("0x6fff5", "0x3b")]
AREA0 = 0x6EA30          # area byte of code word 0, low byte (LE words)

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
print("zero runs:", [(hex(a), hex(b), b-a) for a, b in _runs])
def in_run(cw): return any(a <= cw < b for a, b in _runs)
def next_blind(pc):
    while not blind(pc) or not in_run(pc):
        pc += 1
        assert pc < 0x3E3F8, "cave exceeds the zero-run region"
    return pc

def bsr2_encodable(v):
    # one prefix + bsr word: v = aa*256 + sext(bb), aa != 0
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


stubs, _ = xapvm.find_stubs(code)
tt = xapvm.trap_table()
found = {tt.get(n): a for a, n in stubs.items()}
assert found.get("SinkClaim") == CLAIM and found.get("SinkMap") == MAP
assert found.get("SinkFlush") == FLUSH
assert found.get("MessageSendLater") == SENDLATER
assert found.get("MessageCancelFirst") == CANCELFIRST
print("stubs verified")

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))       # op: 0xE0 bra, 0xF0 bne, 0xF4 beq
def LBL(n): prog.append(("label", n))
def LDI_AL(v):
    if -128 <= v <= 127:
        W(((v & 0xFF) << 8) | 0x14)
    else:
        h = (v + 128) >> 8
        b = v - (h << 8)
        assert -128 <= b <= 127
        W((h & 0xFF) << 8, ((b & 0xFF) << 8) | 0x14)
def LD16(v):                                    # ld AL,#v (never emits 0x0000)
    if -128 <= v <= 127:
        W(((v & 0xFF) << 8) | 0x14)
    else:
        h = (v + 0x80) >> 8
        assert h != 0, "prefix word would be the banned 0x0000"
        b = v - (h << 8)
        assert -128 <= b <= 127
        W((h & 0xFF) << 8, ((b & 0xFF) << 8) | 0x14)

def STASH16(slot):                              # st AL->slot, st AH->slot+1
    W(((slot & 0xFF) << 8) | 0x27, (((slot+1) & 0xFF) << 8) | 0x23)
def RELOAD16(slot):                             # AH=slot+1, AL=slot
    W((((slot+1) & 0xFF) << 8) | 0x13, ((slot & 0xFF) << 8) | 0x17)

# ---------------- FEED(mode): sink in caller slots 2,3; mode in slot 4 ------
# mode 0 = 2 notes, mode 1 = 3 control words. Claim 4 / flush 4 words.
# Claim-fail (backpressure) or null map: still flush + return AL=1.
def emit_FEED():
    """PCM-FEED: sink in caller slots 2,3. claim(64) -> map -> write 64
    samples (±16000 square, flip every 8) -> flush(64). AL=1 fed, 0=full."""
    LBL("FEED")
    W(0xFA0B)                                   # enterl -6
    LD16(64); W(0x0027)                         # claim size 64
    W(0x0014, 0x0127)
    RELOAD16(8)
    BSR(CLAIM)
    W(0x0427)
    W(0xFF84)
    BR(0xF4, "FEED_FULL")                       # == -1 -> buffer full
    W(0x0417, 0x0027)                           # map(sink, offset)
    W(0x0014, 0x0127)
    RELOAD16(8)
    BSR(MAP)
    W(0x0527)
    W(0x0084)
    BR(0xF4, "FEED_FULL")                       # null map
    W(0x051B)                                   # X = map lo
    W(0x0417)                                   # AL = offset
    W(0xE139)                                   # X = map + offset
    LD16(16000); W(0x0227)                      # sample = +16000 -> @(2,Y)
    LD16(8); W(0x0527)                          # outer counter = 8 -> @(5,Y)
    LBL("FEED_OUT")
    LD16(8); W(0x0427)                          # inner counter = 8 -> @(4,Y)
    LBL("FEED_IN")
    W(0x0217)                                   # ld AL,@(2,Y)  (sample)
    W(0x0026)                                   # st @(0,X)
    W(0x0138)                                   # X++
    W(0x0417)                                   # inner--
    W(0xFF34)
    W(0x0427)
    W(0x0084)
    BR(0xF0, "FEED_IN")
    W(0x0217)                                   # sample
    W(0x0174)                                   # neg AL (0x74: AL = -AL)
    W(0x0227)                                   # store back
    W(0x0517)                                   # outer--
    W(0xFF34)
    W(0x0527)
    W(0x0084)
    BR(0xF0, "FEED_OUT")
    LBL("FEED_FULL")
    LD16(64); W(0x0027)                         # flush(sink, 64)
    W(0x0014, 0x0127)
    RELOAD16(8)
    BSR(FLUSH)
    W(0x0114)
    W(0x063C, 0x00E2)

# ---------------- REARM(): sink in caller slots 2,3 -> timer message -------
def emit_REARM():
    LBL("REARM")
    W(0xFC0B)                                   # enterl -4
    W(0x0617, 0x0027)                           # ld AL,@(6,Y) -> @(0,Y)  (sink lo)
    W(0x0717, 0x0127)                           # ld AL,@(7,Y) -> @(1,Y)  (sink hi)
    LDI_AL(TICK_MS); W(0x0227)                  # delay -> @(2,Y)
    LD16(APP_TASK)                              # AL = 0x512
    W(0x4000, 0x0310)                           # AH = 0x4003
    BSR(SENDLATER)
    W(0x043C, 0x00E2)                           # add Y,#4 ; rts

# ---------------- CAVE ------------------------------------------------------
# Placement order: HEAD (timer path) -> REARM -> FEED -> ON -> PRESS/OFF -> EXIT.
# bsr displacement is encodable only at +/-126 (1-word) or |v|>=~32.6k (3-word,
# used only for the low trap stubs) - so every cave-internal bsr must keep both
# caller and callee close; branch targets may be far (2-word form reaches ±32k).
# ---- HEAD: entered at 0x3E21D by the 0xae0 redirect ----
W(0xF80B)                                       # enterl -8
W(0x1517)                                       # ld AL,@(21,Y) = msg_lo
W(0x0084)                                       # cmp AL,#0
BR(0xF4, "PRESS")                               # == 0 -> real press (far, 2-word)
# ---- TIMER FIRE: msg = sink ----
W(0x0227)                                       # sink lo -> @(2,Y)
W(0x1613)                                       # ld AH,@(22,Y) = msg_hi
W(0x0323)                                       # sink hi -> @(3,Y)
W(0x0014, 0x0427)                               # mode 0 (notes)
BSR("FEED")                                     # close: FEED below
BSR("REARM")                                    # always re-arm
BR(0xE0, "EXIT")                                # far, 2-word

# ---- REARM(): sink in caller slots 2,3 ----
emit_REARM()

# ---- FEED(mode): sink in caller slots 2,3 ----
emit_FEED()

# ---- ON: beep + create codec sink + PCM + arm ----
LBL("ON")
W(0x0014)
BSR(TONE)                                       # beep (far stub); feedback only
W(0x0014, 0x0027)                               # @(0,Y) = 0
LD16(3); W(0x0127)                              # @(1,Y) = 3  (Bose arg pattern)
W(0x0310)                                       # AH = 0 (instance 0)
LD16(3)                                         # AL = 3 = AUDIO_HARDWARE_CODEC
BSR(ASINK)                                      # AL = pcm sink (far stub)
STASH16(2)                                      # -> @(2,Y)/@(3,Y)
W(0x0084)
BR(0xF4, "EXIT")                                # sink refused -> beep only
BSR("FEED")                                     # first PCM chunk now
BSR("REARM")
BR(0xE0, "EXIT")

# ---- PRESS path ----
LBL("PRESS")
W(0x0500, 0x6B15)                               # ld AL,@0x56b
W(0x0800, 0x00D4)                               # xor AL,#0x0800
W(0x0500, 0x6B25)                               # st AL,@0x56b
W(0x0800, 0x00C4)                               # and AL,#0x0800
W(0x0084)
BR(0xF0, "ON")                                  # ON is near-above: -small
# OFF: cancel pending timer
LD16(APP_TASK)
W(0x4000, 0x0310)
BSR(CANCELFIRST)                                # far stub
# ---- EXIT: skip post-flow ----
LBL("EXIT")
W(0x0B00, 0xED14)                               # ld AL,#0xaed
W(0xE119)                                       # ld X,AL
W(0x083C)                                       # add Y,#8
W(0x00E2)                                       # rts

# ---- layout: fixed-point with atomic band connectors ----
bsr_size, br_size = {}, {}
label_addr = {}
for iteration in range(12):
    addr = CAVE
    addrs = [0]*len(prog)
    extra = {}
    i = 0
    def needs_follow(item):
        # the word after this item must be placed: conditionals fall
        # through, and a bsr/thunk's callee RETURNS to a+ln (rarely taken
        # branches and rts/bra tails are the only true terminators)
        k = item[0]
        if k == "bsr": return True
        if k == "br": return item[1] != 0xE0
        return (item[1][-1] & 0xFF) != 0xE2
    while i < len(prog):
        kind = prog[i][0]
        if kind == "label":
            addrs[i] = addr; i += 1; continue
        if kind == "w": sz = len(prog[i][1])
        elif kind == "bsr": sz = bsr_size.get(i, 0)
        else: sz = br_size.get(i, 1)
        band_end = addr
        while blind(band_end) and in_run(band_end): band_end += 1
        limit = band_end - 1
        # fall-through-capable items need one more placeable slot behind
        # them (next item or connector) or the not-taken path hits frozen
        need = sz + 1 if needs_follow(prog[i]) else sz
        if addr + need > band_end:
            if addr >= band_end:
                # band exhausted with a terminal item (bra/rts) in the
                # last slot: nothing follows, relocate without a connector
                addr = next_blind(band_end)
                continue
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
            if -126 <= v <= 126: want = 1
            elif bsr2_encodable(v - 1): want = 2
            elif bsr3_encodable(v - 2): want = 3
            else: want = 0
            if bsr_size.get(i, 3) != want: bsr_size[i] = want; ok = False
        else:
            want = 1 if -128 <= tgt - a <= 127 else 2
            if br_size.get(i, 1) != want: br_size[i] = want; ok = False
    if ok: break
else:
    raise SystemExit("no converge")

def sext8(b): return b - 256 if b & 0x80 else b
out = {}
for i, item in enumerate(prog):
    kind = item[0]
    a = addrs[i]
    if kind == "label": continue
    if kind == "w":
        for k, val in enumerate(item[1]):
            assert a + k not in out, (hex(a+k), "collision")
            out[a+k] = val
    elif kind == "bsr":
        tgt = label_addr[item[1]] if isinstance(item[1], str) else item[1]
        szb = bsr_size[i]
        assert szb in (1, 2, 3), (hex(a), item[1], "bsr displacement unencodable in any form")
        if szb == 1:
            v = tgt - a
            out[a] = ((v & 0xFF) << 8) | 0x9C
        elif szb == 2:
            # prefix + bsr word: target = (a+1) + operand, operand = aa*256 + sext(b)
            v = tgt - (a + 1)
            for aa in range(max(-128, (v >> 8) - 2), min(128, (v >> 8) + 3)):
                if aa == 0: continue
                b = v - aa * 256
                if -128 <= b <= 127:
                    out[a] = (aa & 0xFF) << 8
                    out[a+1] = ((b & 0xFF) << 8) | 0x9C
                    break
            else:
                raise AssertionError((hex(a), hex(tgt), "bsr2"))
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
            assert done, (hex(a), hex(tgt), "bsr displacement unencodable")
    else:
        op = item[1]
        tgt = label_addr[item[2]]
        if br_size[i] == 1:
            v = tgt - a
            assert -128 <= v <= 127
            out[a] = ((v & 0xFF) << 8) | op
        else:
            v = tgt - a              # branches fold from instruction start
            aa = 1 if v > 0 else -2
            bb = v - aa*256
            assert -128 <= bb <= 127, (hex(a), hex(tgt))
            out[a] = (aa & 0xFF) << 8; out[a+1] = ((bb & 0xFF) << 8) | op
for ca, nb in extra.items():
    v = nb - ca
    assert -128 <= v <= 127
    assert ca not in out
    out[ca] = ((v & 0xFF) << 8) | 0xE0

lo, hi = min(out), max(out)
print(f"cave spans {lo:#x}..{hi:#x}, {len(out)} words (iters {iteration+1})")
bad = [a for a in out if not blind(a) or not in_run(a)]
assert not bad, [hex(a) for a in bad]
print("all writes blind + in-run")

patched = list(code)
for cw, val in out.items(): patched[cw] = val & 0xFFFF

intended, seen, dstarts = {}, {}, set()
for i, item in enumerate(prog):
    if item[0] in ("bsr", "br"):
        a = addrs[i]
        tgt = label_addr[item[1]] if isinstance(item[1], str) else item[1]
        if item[0] == "bsr": intended[a] = (tgt, "bsr")
        else: intended[a] = (label_addr[item[2]], "br")
for a, op, v, ln in xapvm.decode(patched, fold_zero=False):
    dstarts.add(a)
    if lo <= a <= hi:
        if op == 0x9C: seen[a] = ((a + ln - 1 + v) & 0x3FFFF, "bsr")
        elif op in (0xE0, 0xF0, 0xF4): seen[a] = ((a + v) & 0x3FFFF, "br")
for a, (tgt, kind) in intended.items():
    got = seen.get(a)
    assert got and got[0] == (tgt & 0x3FFFF), (hex(a), kind, hex(tgt), got)
print(f"decode-verify: {len(intended)}/{len(intended)} branches fold to intended targets")
for i, item in enumerate(prog):
    if item[0] == "label": continue
    assert addrs[i] in dstarts, (hex(addrs[i]), item[0], "not a decode boundary")
for ca in extra:
    assert ca in dstarts, (hex(ca), "connector not a decode boundary")
print("decode boundaries: OK")

json.dump({hex(a): v for a, v in out.items()}, open("build/hook/probe14_words.json", "w"), indent=0)
print("saved build/hook/probe14_words.json")

edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
cmd = [sys.executable, "tools/fsedit.py", "--out", "build/hook/probe14_pcm.dfu"]
for off, val in edits:
    cmd += ["--edit", f"{off}={val}"]
open("build/hook/probe14_cmd.txt", "w").write(" ".join(cmd) + "\n")
if "--build" in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit("fsedit failed")
else:
    print(f"edit list ready ({len(edits)} bytes) -> build/hook/probe14_cmd.txt")
