#!/usr/bin/env python3
"""probe139: the partition census -- a WRITE-FREE PartitionGetInfo sweep.

docs/partition-route.md names this "the only thing to do next" on the partition
route: a cave that calls PartitionGetInfo(SERIAL_FLASH, n, TYPE, &out) and
NOTHING ELSE -- no sink, no write, no mount, no load. Read-only interrogation,
the FLASH-PROTOCOL safety preference, and the go/no-go for the whole route:

  the live partition map has NEVER been read on hardware. The static case
  (fn_187e7: image type 1/2 -> partition 0, type 4 -> partition 2; the ext
  .xuv parses as a bare fsr_dfu1 filesystem; vm.app reads ext_version/NowSpeakTTS)
  says partition 2 holds the ext language filesystem, but that is inference from
  Bose's code, not a hardware fact. The census turns the inference into a datum
  with zero brick risk: PartitionGetInfo cannot write anything.

ABI (verified against TWO stock call sites, 0x1192a-0x1192f and 0x182d1-0x182d6):

  AL      device, 1 = PARTITION_SERIAL_FLASH (partition_if.h:32)
  AH      partition number (0x182d4 masks it `and AH,#3` -> 0..3 meaningful)
  @(0,Y)  key: IS_MOUNTED=0, SIZE=1, TYPE=2, STATE=3, SECTOR_SIZE=4
  @(1,Y)  uint32* out, formed with Bose's own idiom
          `ld AL,@0xffe4 ; add AL,#n ; st AL,@(1,Y)` = &slot n
  ->      bool in AL; value written through the pointer. The stock sites read
          slots n:n+1 as AH:AL, so the LOW half is at ptr+1 -- this cave reads
          slot 5 for an out pointer of &slot4.

OUTCOME TABLE (press: laptop connected, music paused, LONG-PRESS the BLUETOOTH
button -- probe134/137's proven trigger; hook and redirects are byte-identical
to probe137's). EVERY path has a distinct id; none is 0x00/0x09/0x35, and none
is a prompt this state produces by itself:

  battery 10%         partition 1 TYPE=UNUSED -- the safest possible write target
  battery 20%         partition 2 TYPE=UNUSED -- ext-fs inference wrong; p2 free
  battery 30%         partition 3 TYPE=UNUSED
  battery 40%         partition 4 TYPE=UNUSED
  battery 50%         none of 1..4 unused; partition 2 = FILESYSTEM -- the
                      EXPECTED live map (p0 main fs + p2 ext fs). The overwrite-
                      partition-2 plan is confirmed as grounded.
  battery 60%         none unused; partition 2 = PS
  battery 70%         none unused; partition 2 = RAW_SERIAL
  battery 80%          none unused; partition 2 = RANDOM_ACCESS
  auto off disabled   none unused; partition 2 ABSENT or TYPE unrecognizable --
                      the ext-fs inference is unsupported; stop and rethink
  conference call     CONTROL FAILED: GetInfo(SERIAL_FLASH, 0, TYPE) returned
  failed              FALSE or TYPE != FILESYSTEM. Partition 0 demonstrably holds
                      the main fs, so this means the ABI model above is wrong --
                      the rest of the sweep's data would be garbage. Stop.

DESIGN NOTES:

* Partition 0 is queried FIRST as a control: we know its answer (FILESYSTEM,
  mounted at boot, 0x0a340). A trap this project has never called gets one
  self-check before its data is believed.
* The sweep reports the FIRST n in 1..4 with TYPE == UNUSED, per the doc's
  compression ("the go/no-go in one press"). If none is unused -- the expected
  outcome -- the cave re-queries partition 2 and speaks its TYPE, because that
  single value is what decides whether the overwrite-p2 plan stands.
* One id per press. 0xAE0 is one-shot per streaming session (probe123), so
  speaking a sequence would spend presses; the id lattice above fits in one.
* NOTHING is written. No sink trap, no digest, no mount, no KalimbaLoad. The
  next step after a go outcome is the pattern-write probe (open sink on the
  reported partition, write a known pattern, digest SKIP, close, re-read STATE)
  -- separately, with its own go-ahead.
* Reporting is `ld AL,#id ; bsr 0xDF7F` -- probe99's direct-call idiom, with
  hardware behind it (probe99 spoke two ids from the cave this way).
* The stock back-call `bsr 0xE06D` runs FIRST (probe77's proven order) and the
  redirects are byte-identical to probe137's: 0xAE0 -> cave, 0xae3 := bra +1,
  0xae4..0xae6 nopped so the stock 0x35 cannot confuse the census id.

CAVE COST: ~90 words of the 197-word window, no generator, no malloc, no timer.
`enterl -8` at this hook is hardware-proven (probes 122/128/129/132/133/134/137).

SIMULATION: cavesim models PartitionGetInfo (added with this probe) from a
configurable map, `--pmap '{"0":1,"2":1}'` default = the predicted live map.
Every outcome branch is exercised below; see the run sheet.

THIS PROBE IS BUILT, NOT FLASHED. probe137 is on the device awaiting its press
(malloc(254)); the owner decides whether to press it first or overwrite it with
this census. Either order is safe; probe137 rebuilds identically.
"""

import os, re, sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm

_PROBE = re.match(r'assemble_(probe[0-9a-z]+)\.py$',
                  os.path.basename(os.path.abspath(__file__))).group(1)

CAVE = 0x3E21D
# Byte-identical to probe134/136/137's redirects: the 0xAE0 bsr -> 0x3E21D,
# 0xae3 := bra +1, and the stock prompt call at 0xae4..0xae6 nopped so the only
# id the owner hears is the census result. All bytes are inside blind windows.
REDIRECT_EDITS = [("0x6fff1", "0x04"), ("0x6fff3", "0xd7"), ("0x6fff5", "0x3b"),
                  ("0x6fff6", "0xe0"), ("0x6fff7", "0x01"),
                  ("0x6fff8", "0x00"), ("0x6fff9", "0x00"),
                  ("0x6fffa", "0x00"), ("0x6fffb", "0x00"),
                  ("0x6fffc", "0x00"), ("0x6fffd", "0x00")]
AREA0 = 0x6EA30

BACK = 0xE06D           # the call the hook displaced: run it first, always
SPEAK = 0xDF7F          # prompt engine: id in AL, nothing in X, returns
GETINFO = ca.STUB['PartitionGetInfo']

# ids: docs/request-id-catalog.md (owner-verified 2026-09-29, all 64 anchored)
ID_P1_UNUSED, ID_SWEEP_BASE = None, 0x26     # sweep speaks n + 0x26 -> 0x27..0x2a
ID_P2_TYPE_BASE = 0x2a                       # none-path speaks TYPE + 0x2a -> 0x2b..0x2e
ID_P2_ABSENT = 0x14                          # "auto off disabled"
ID_CTRLFAIL = 0x23                           # "conference call failed"
KEY_TYPE = 2                                 # partition_info_key PARTITION_INFO_TYPE
DEV_SQIF = 1                                 # partition_filesystem_devices SERIAL_FLASH
MAX_PART = 4                                 # sweep 1..4 (0x182d4's `and AH,#3` says 0..3)

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

def set_key_ptr():
    # @(0,Y) = key (TYPE), @(1,Y) = &slot4 -- Bose's own frame-pointer idiom
    # (stock 0x1192a/0x182d1: `e415 ld AL,@0xffe4`, the Y-REGISTER MIRROR at
    # data address 0xFFE4; 0xFFE0 is the AH mirror and gives garbage here).
    # The out uint32 lands in slots 4:5, low half at 5.
    W(0x0214)                       # ld AL,#2      (PARTITION_INFO_TYPE)
    W(0x0027)                       # st AL,@(0,Y)
    W(0xE415)                       # ld AL,@0xffe4 (= Y, the frame base)
    W(0x0434)                       # add AL,#4
    W(0x0127)                       # st AL,@(1,Y)

W(0xF80B)                       # enterl -8 (slots 0..5 usable, 6/7 = link)
BSR(BACK)                       # stock back-call FIRST, probe77's proven order

# ---- control: GetInfo(SERIAL_FLASH, 0, TYPE, &4). We KNOW this answer
# (partition 0 = the main filesystem, mounted at boot 0x0a340). If it fails,
# everything the sweep would report is garbage -- say so and stop.
set_key_ptr()
W(0x0114)                       # ld AL,#1      (SERIAL_FLASH)
W(0x0010)                       # ld AH,#0      (partition 0)
BSR(GETINFO)
W(0x0084); BR(0xF4, "CTRLFAIL") # FALSE -> the ABI/map model is wrong
W(0x0517)                       # ld AL,@(5,Y)  (TYPE, low half at ptr+1)
W(0x0184); BR(0xF0, "CTRLFAIL") # cmp AL,#1 ; bne -- expect FILESYSTEM

# ---- sweep n = 1..4, first TYPE == UNUSED
W(0x0114)                       # ld AL,#1
W(0x0227)                       # st AL,@(2,Y)  n = 1
LBL("LOOP")
set_key_ptr()
W(0x0114)                       # ld AL,#1      (device)
W(0x0213)                       # ld AH,@(2,Y)  (partition = n)
BSR(GETINFO)
W(0x0084); BR(0xF4, "NEXT")     # FALSE -> no such partition, try the next
W(0x0517)                       # ld AL,@(5,Y)
W(0x0084); BR(0xF4, "FOUND")    # cmp AL,#0 ; beq -> TYPE == UNUSED
LBL("NEXT")
W(0x0217)                       # ld AL,@(2,Y)
W(0x0134)                       # add AL,#1
W(0x0227)                       # st AL,@(2,Y)
W(0x0584)                       # cmp AL,#5
BR(0xFC, "LOOP")                # bcs -> C=1 means AL<5 (XAP carry: set on
                                # borrow, proven by fn_0e06d's dispatch ladder
                                # and xapemu line "cmp: C=1 iff cur<val") -- loop
# sweep exhausted: none of 1..4 is UNUSED. Report partition 2's TYPE -- the one
# value that decides whether the overwrite-p2 plan is grounded. TYPE 1..4 maps
# linearly to ids 0x2b..0x2e; anything else (absent partition, or a TYPE the
# ADK enum does not define) is "unsupported" and says so.
set_key_ptr()
W(0x0114)                       # ld AL,#1
W(0x0210)                       # ld AH,#2      (partition 2)
BSR(GETINFO)
W(0x0084); BR(0xF4, "UNSUP")    # FALSE -> partition 2 does not exist
W(0x0517)                       # ld AL,@(5,Y)
W(0x0084); BR(0xF4, "UNSUP")    # TYPE == 0 would collide with sweep id 0x2a
W(0x0584); BR(0xF8, "UNSUP")    # cmp AL,#5 ; bcc -> C=0 means AL>=5: not in
                                # the enum (carry polarity as above)
W(0x2A34)                       # add AL,#0x2a  -> ids 0x2b..0x2e
BSR(SPEAK)
BR(0xE0, "OUT")
LBL("UNSUP")
W(0x1414)                       # ld AL,#0x14   "auto off disabled"
BSR(SPEAK)
BR(0xE0, "OUT")

LBL("FOUND")
W(0x0217)                       # ld AL,@(2,Y)  n
W(0x2634)                       # add AL,#0x26  -> ids 0x27..0x2a
BSR(SPEAK)
BR(0xE0, "OUT")

LBL("CTRLFAIL")
W(0x2314)                       # ld AL,#0x23   "conference call failed"
BSR(SPEAK)
BR(0xE0, "OUT")

LBL("OUT")
W(0xF80F)                       # leavel -8, which returns

# ---- layout (proven machinery, probes 67-77, verbatim from probe137) ----
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
            # last-word relative -- the probe131/132 lesson, proven by census
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
