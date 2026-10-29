#!/usr/bin/env python3
"""probe142: THE PLAY PROBE -- mount partition 2, load /brown.kap, wire the DAC.

The last gate. probe141's staged write put the brown-noise filesystem on p2
(unconfirmed on device -- this probe is also its verification: FileFind answers
whether /brown.kap is really there). EVERY side effect here is runtime-only:
a mount (RAM state, gone at reboot), a DSP load (RAM), a stream connect (RAM).
NOTHING writes flash. With the boot-safe gate, a power-on auto-fire bails
silently in a handful of words.

THE GATE (new, hard requirement after probe141's harm event): read sinkState
(@0x59e, fn_0d475's value) and require 3 (deviceConnected) or 13 (0x0d,
deviceA2DPStreaming) BEFORE ANYTHING. At power-on the speaker auto-enters
pairing (sinkState 1), the 0xAE0 hook fires (probe121 precedent) -- and this
cave exits SILENTLY instead of mounting, loading and making noise uninvited.
probe141 had NO gate and rewrote p2 at every power-on; that omission is the
device-harm incident.

THE CHAIN (probe95's proven recipe, plus the mount and our file):

  PartitionMountFilesystem(SERIAL_FLASH=1, 2, LOWER_PRIORITY=1)  via slot 0
  FileFind(1, "brown.kap", 9)          -- 3-arg form: arg3 = length in WORDS
  VmDeepSleepEnable(0)                 -- bracket the load (0x1E3FE/0x1E408 idiom)
  KalimbaLoad(f)                       -- probe93-proven clean from a cave
  (deep-sleep restore skipped: our DSP is self-timed and stays loaded)
  StreamAudioSink(3, 0, 2)             -- CODEC, instance 0, channel 2 (probe95)
  SinkConfigure(dac, 0x0301, 16000)    -- probe95's exact config
  StreamKalimbaSink(0)                 -- port 0 of OUR loaded DSP
  StreamSourceFromSink(ksink)
  StreamConnect(ksrc, dac)             -- probe95-proven survivable alone
  -> the kap is self-timed: the noise starts here and SUSTAINS.

OUTCOME TABLE (press = laptop connected, music PAUSED, Bluetooth long-press,
FIRST press):

  SUSTAINED BROWN NOISE   SUCCESS -- the deliverable. Plays until power-off
                          (nothing tears the DSP down; a second press repeats).
  battery 30%             PartitionMountFilesystem returned FALSE (p2 fs broken?
                          probe141's write failed? -- the write probe re-runs)
  battery 40%             FileFind found /brown.kap nowhere (fs content wrong)
  battery 50%             KalimbaLoad returned FALSE (DSP load refused)
  battery 60%             StreamAudioSink 0 / StreamKalimbaSink 0 /
                          StreamSourceFromSink 0 (wiring handles failed)
  battery 90%             StreamConnect returned 0 (DAC wire refused)
  silence                 the gate bailed (wrong state -- press conditions not
                          met) OR the connect silently succeeded with no
                          audible output (kap/DAC rate mismatch). Distinguish
                          by the trap log and by retrying with music PLAYING.

NO flash writes. enterl -8 at this hook is hardware-proven. Redirects identical
to 137/139/140/141's. The path string lives after the final leavel (the
string-executes-as-opcodes lesson from probe141).

BUILT, NOT FLASHED. Runtime side effects only, but the press changes what the
speaker DOES -- owner go-ahead per the standing rule.
"""

import os, re, sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

_PROBE = re.match(r'assemble_(probe[0-9a-z]+)\.py$',
                  os.path.basename(os.path.abspath(__file__))).group(1)

CAVE = 0x3E21D
REDIRECT_EDITS = [("0x6fff1", "0x04"), ("0x6fff3", "0xd7"), ("0x6fff5", "0x3b"),
                  ("0x6fff6", "0xe0"), ("0x6fff7", "0x01"),
                  ("0x6fff8", "0x00"), ("0x6fff9", "0x00"),
                  ("0x6fffa", "0x00"), ("0x6fffb", "0x00"),
                  ("0x6fffc", "0x00"), ("0x6fffd", "0x00")]
AREA0 = 0x6EA30
CONST_BASE = 0x7400                     # data addr of code word 236514 (0x39BE2)

BACK = 0xE06D
SPEAK = 0xDF7F
MOUNT = ca.STUB['PartitionMountFilesystem']
FILEFIND = ca.STUB['FileFind']
DESLEEP = ca.STUB['VmDeepSleepEnable']
KLOAD = ca.STUB['KalimbaLoad']
AUDIOSINK = ca.STUB['StreamAudioSink']
SINKCONF = ca.STUB['SinkConfigure']
KSINK = ca.STUB['StreamKalimbaSink']
SRCFROM = ca.STUB['StreamSourceFromSink']
CONNECT = ca.STUB['StreamConnect']

PATH = "brown.kap"
PATH_LEN = len(PATH)                   # 9 -- FileFind arg3, length in WORDS

w = xapvm.load_words("firmware/bose/extracted/internal_fs/vm.app")
code = w[0x18:]
C0 = (0x6e974 + 0x34) % 64
def blind(cw): return 34 <= (2*cw + C0) % 64 <= 60
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

_ORDER = []
for a, b in _runs:
    if a <= CAVE < b: _ORDER.append((CAVE, b))
for a, b in _runs:
    if a > CAVE: _ORDER.append((a, b))
for a, b in _runs:
    if b <= CAVE: _ORDER.append((a, b))
assert _ORDER and _ORDER[0][0] == CAVE
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
    if pc in _BEND:
        k = _BEND[pc] + 1
        assert k < len(_BANDS), ('cave exhausted: %d writable words is not enough'
                                 % sum(y - x for x, y in _BANDS))
        return _BANDS[k][0]
    for x, y in _BANDS:
        if x <= pc < y:
            return pc
    raise AssertionError('next_blind off the map at %#x' % pc)

BAND0 = [CAVE]
assert all(blind(a) and in_run(a) for a in BAND0)
CODE_AT = CAVE + 1
assert blind(CODE_AT) and in_run(CODE_AT), hex(CODE_AT)

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))

W(0xF80B)                       # enterl -8 (slots 0..5 usable)
BSR(BACK)                       # stock back-call first, probe77's proven order

# ---- THE GATE: sinkState (@0x59e) must be 3 or 13. Anything else (boot
# auto-pairing = 1, idle = 0) exits SILENTLY -- no id, no side effect.
W(0x0600, 0x9E15)               # ld AL,@0x59e   (prefix + ld AL,abs: fold =
                                #   6*256 + sext8(0x9e=-98) = 1438 = 0x59e)
W(0x0384)                       # cmp AL,#3
BR(0xF4, "GO")                  # beq -> connected
W(0x0D84)                       # cmp AL,#0x0d
BR(0xF4, "GO")                  # beq -> a2dp streaming
BR(0xE0, "OUT")                 # else: silent bail

# ---- mount partition 2 at LOWER priority
LBL("GO")
ca.call3(W, BSR, MOUNT, al=('imm', 1), ah=('imm', 2), arg3=('imm', 1))
W(0x0084); BR(0xF4, "NOMOUNT")  # FALSE -> mount refused

# ---- FileFind(1, "brown.kap", 9): arg3 staged first, then the patched
# string pointer, then AL -- hand-emitted, AH before AL.
W(0x0914)                       # ld AL,#9
W(0x0027)                       # st AL,@(0,Y)  arg3 = length in words
W(0x0114)                       # ld AL,#1
LBL("SETAH")                    # prefixed ld AH,#<string data addr>, patched
W(0x0000, 0x0010)
BSR(FILEFIND)
W(0x0084); BR(0xF4, "NOFILE")   # 0 -> /brown.kap not found
W(0x0227)                       # st AL,@(2,Y)  f

# ---- load the DSP (VmDeepSleepEnable bracket, 0x1E3FE/0x1E408 idiom)
ca.call1(W, BSR, DESLEEP, al=('imm', 0))
ca.call1(W, BSR, KLOAD, al=('slot', 2))
W(0x0327)                       # st AL,@(3,Y)  ok
W(0x0084); BR(0xF4, "NOLOAD")   # FALSE -> DSP load refused

# ---- the DAC wire (probe95's exact chain, minus nothing)
PAD_DAC = 1                       # swept: breaks the band-edge size oscillation
for _ in range(PAD_DAC):
    W(0x0000)
ca.call3(W, BSR, AUDIOSINK, al=('imm', 3), ah=('imm', 0), arg3=('imm', 2))
W(0x0227)                       # st AL,@(2,Y)  dac -- f is consumed after load
W(0x0084); BR(0xF4, "NODAC")
ca.call3_long(W, BSR, SINKCONF, al=('slot', 2), ah=('imm', 0x0301), arg3_32=16000)
ca.call1(W, BSR, KSINK, al=('imm', 0))
W(0x0327)                       # st AL,@(3,Y)  ksink
W(0x0084); BR(0xF4, "NOKSINK")
ca.call1(W, BSR, SRCFROM, al=('slot', 3))
W(0x0327)                       # st AL,@(3,Y)  ksrc
W(0x0084); BR(0xF4, "NOKSRC")

# ---- wire it: the kap is self-timed, so the noise starts HERE and sustains
ca.call2(W, BSR, CONNECT, al=('slot', 3), ah=('slot', 2))
W(0x0084); BR(0xF4, "NOCONN")

# ---- SUCCESS: the noise is the report -- silent exit, like probe134
BR(0xE0, "OUT")

# ---- failure tails (battery ids, familiar family, all distinct)
LBL("NOMOUNT")
W(0x2914)                       # "battery 30%"
BSR(SPEAK)
BR(0xE0, "OUT")
LBL("NOFILE")
W(0x2A14)                       # "battery 40%"
BSR(SPEAK)
BR(0xE0, "OUT")
LBL("NOLOAD")
W(0x2B14)                       # "battery 50%"
BSR(SPEAK)
BR(0xE0, "OUT")
LBL("NODAC")
W(0x2C14)                       # "battery 60%"
BSR(SPEAK)
BR(0xE0, "OUT")
LBL("NOKSINK")
W(0x2E14)                       # "battery 80%"
BSR(SPEAK)
BR(0xE0, "OUT")
LBL("NOKSRC")
W(0x2F14)                       # "battery 90%"
BSR(SPEAK)
BR(0xE0, "OUT")
LBL("NOCONN")
W(0x3114)                       # "battery low please charge now"
BSR(SPEAK)
BR(0xE0, "OUT")

W(0x0000)                       # pad: the gate's silent-bail bra otherwise lands
LBL("OUT")                      # on the +128 displacement with no 2- or 3-word form
W(0xF80F)                       # leavel -8, which returns

# ---- the path string: DEAD DATA after the leavel (probe141's lesson: in the
# fall-through path its char words EXECUTE as opcodes)
LBL("STR")
for ch in PATH:
    W(ord(ch))
W(0x0000)

# ---- layout (proven machinery, verbatim from probe137/139/140/141) ----
bsr_size, br_size = {}, {}
label_addr = {}
changes = []
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

for iteration in range(200):
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
        try:
            nb_probe = next_blind(band_end)
            cs = 1 if -128 <= nb_probe - addr <= 127 else 2
        except AssertionError:
            nb_probe, cs = None, 0
        need = sz + (cs if needs_follow(prog[i]) else 0)
        if addr + need > band_end:
            assert nb_probe is not None, (
                'cave exhausted: %d writable words is not enough'
                % sum(y - x for x, y in _BANDS))
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
            want = (1 if -128 <= tgt - a <= 127
                    else 2 if br2_encodable(tgt - (a + 1))
                    else 3)
            if br_size.get(i, 1) != want:
                changes.append((iteration, hex(a), prog[i][2],
                                'item#%d' % i, want))
                br_size[i] = want; ok = False
    if ok: break
else:
    for c in changes[-10:]:
        print('  change:', c)
    raise SystemExit('no converge: last-addresses br %s / bsr %s'
                     % ({hex(addrs[i]): sz for i, sz in br_size.items() if prog[i][0] == 'br'},
                        {hex(addrs[i]): sz for i, sz in bsr_size.items() if prog[i][0] == 'bsr'}))

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
            v = tgt - (a + 2)
            done = False
            for aa in range(-128, 128):
                if aa == 0: continue
                for bb in range(-128, 128):
                    if bb == 0: continue
                    cc = v - aa*65536 - bb*256
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

entry_v = CODE_AT - CAVE
assert -128 <= entry_v <= 127
assert CAVE not in out, 'the entry jump word is already occupied'
out[CAVE] = ((entry_v & 0xFF) << 8) | 0xE0
assert 'HANDLER' not in label_addr, 'a handler exists but no TaskData is emitted for it'

# ---- patch the FileFind string pointer (label BEFORE the 2-word item) ----
STR_CODE = label_addr['STR']
STR_DATA = (CONST_BASE + (STR_CODE - 236514)) & 0xFFFF
SETAH = label_addr['SETAH']
ah_lo = STR_DATA & 0xFF
ah_hi = (STR_DATA >> 8) & 0xFF
assert 1 <= ah_hi <= 0xFF, hex(STR_DATA)   # 0x80+ wraps negatively, same 16 bits
out[SETAH] = (ah_hi << 8) | 0x00
out[SETAH + 1] = (ah_lo << 8) | 0x10
print('FileFind string "brown.kap" at code %s -> data %#x (ld AH prefix %04x %04x)'
      % (hex(STR_CODE), STR_DATA, out[SETAH], out[SETAH+1]))

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
