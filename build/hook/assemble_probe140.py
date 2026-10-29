#!/usr/bin/env python3
"""probe140: the pattern write -- can this cave commit bytes to partition 2?

docs/partition-route.md's second gate, authorized by probe139's census (pressed
2026-10-06, "battery 70%": control passed, no partition 1..4 unused, partition 2
EXISTS with TYPE = RAW_SERIAL). The full attempt (our own ROFS + KalimbaLoad) is
only a bounded risk after a real write round-trips. This probe writes the
smallest meaningful thing and reports one id:

  1. GetInfo(SERIAL_FLASH, 2, STATE, &4)   -- control: the census proved this works
  2. StreamPartitionOverwriteSink(1, 2)    -- *** THIS ERASES PARTITION 2 ***
     (the ext language packs die here; restorable from Minnow_3.0.3_ext_signed.xuv,
     whose genuine RSA signature lets a restoral write pass md_type=1 on-device)
  3. SinkMap + SinkClaim(16)               -- fn_12e1a's stock idiom, inline, with
                                              the guards fn_12e1a lacks (0-checks)
  4. write 8 words at map+0: 'f','s','r','_','d','f','u','1' as 4 LE words
     (7366 5F72 6466 3175) + 0001 0002 0003 0004. The marker is for any future
     raw read of p2 (dfu_upload reads only the main fs area). This is NOT a
     mountable filesystem -- p2 fails to parse until restored, the accepted cost
     (nothing in ext is boot-critical).
  5. SinkFlush(sink, 16)
  6. PartitionSetMessageDigest(sink, 3=SKIP, 0, 0) -- Bose's own SKIP mode
  7. SinkClose -- the first word commits only here (partition.h:44-46)
  8. GetInfo(2, STATE) again               -- the verdict

OUTCOME TABLE (press = probe134/137/139's proven trigger; laptop connected, music
PAUSED, Bluetooth long-press, FIRST press; the press may take a while -- erasing
~2 MB of SQIF happens inside step 2; DO NOT pull power during the press):

  battery 10%         SUCCESS: pattern written, digest SKIP, closed, and
                      partition-2 STATE == VALID. The whole route is GO.
  battery 20%         closed but STATE == INCOMPLETE -- the failsafe fired
                      (first word not committed). Unexpected with SKIP; report.
  battery 30%         StreamPartitionOverwriteSink returned FALSE (open failed)
  battery 40%         SinkMap 0 / SinkClaim 0xffff / claim offset != 0
  battery 50%         SinkFlush returned FALSE
  battery 60%         PartitionSetMessageDigest returned FALSE -- SinkClose was
                      still run; expect INCOMPLETE, fails safe
  conference call failed   the pre-read GetInfo contradicted the census -- stop

NOT done here: no mount, no FileFind, no KalimbaLoad, nothing that touches
partition 0 or the loader. The erase is the only destructive act, it is bounded
to partition 2 by the same trap Bose's own updater aims at p2 (fn_187e7 type 4),
and the recovery path (POWER+VA hardware DFU, probe137 reflash, or an official
update) covers every branch of this tree.

CAVE COST: ~140 of 197 words. enterl -8 at this hook is hardware-proven.
Redirects byte-identical to probe137/139's. Reporting is probe99's
`ld AL,#id ; bsr 0xDF7F` direct idiom; ids are the battery family (distinct,
none collides with 0x00/0x09/0x35, and the owner has just used this family).

BUILT, NOT FLASHED. This probe writes flash -- it needs the owner's explicit
go-ahead per docs/partition-route.md and the owner's standing rule.
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

BACK = 0xE06D
SPEAK = 0xDF7F
GETINFO = ca.STUB['PartitionGetInfo']
OVERSINK = ca.STUB['StreamPartitionOverwriteSink']
SINKMAP = ca.STUB['SinkMap']
SINKCLAIM = ca.STUB['SinkClaim']
SINKFLUSH = ca.STUB['SinkFlush']
SETDIGEST = ca.STUB['PartitionSetMessageDigest']
SINKCLOSE = ca.STUB['SinkClose']

KEY_STATE = 3
DEV_SQIF = 1
P2 = 2
PATTERN = [0x7366, 0x5F72, 0x6466, 0x3175, 0x0001, 0x0002, 0x0003, 0x0004]
PAT_BYTES = len(PATTERN) * 2          # 16

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

def getinfo_prep(key):
    """@(0,Y)=key, @(1,Y)=&slot4 (Bose's e415 idiom); out low half lands in slot 5."""
    assert 0 <= key <= 0x7f
    W(0x0200 | (key << 8) | 0x14)   # ld AL,#key
    W(0x0027)                       # st AL,@(0,Y)
    W(0xE415)                       # ld AL,@0xffe4 (Y mirror)
    W(0x0434)                       # add AL,#4
    W(0x0127)                       # st AL,@(1,Y)

W(0xF80B)                       # enterl -8 (slots 0..5 usable)
BSR(BACK)                       # stock back-call first, probe77's proven order

# ---- 1. control: GetInfo(p2, STATE) -- the census proved this exact query
getinfo_prep(KEY_STATE)
W(0x0114)                       # ld AL,#1
W(0x0210)                       # ld AH,#2
BSR(GETINFO)
W(0x0084); BR(0xF4, "CTRLFAIL") # FALSE -> contradicts the census; stop

# ---- 2. *** THE ERASE *** open the overwrite sink on partition 2
ca.call2(W, BSR, OVERSINK, al=('imm', DEV_SQIF), ah=('imm', P2))
W(0x0227)                       # st AL,@(2,Y)  sink
W(0x0084); BR(0xF4, "EOPEN")    # FALSE -> open failed (no sink to close)

# ---- 3. map + claim (fn_12e1a's idiom, guards strengthened)
ca.call1(W, BSR, SINKMAP, al=('slot', 2))
W(0x0327)                       # st AL,@(3,Y)  map
W(0x0084); BR(0xF4, "MAPBAD")   # cmp AL,#0 ; beq -> map returned 0: failure
ca.call2(W, BSR, SINKCLAIM, al=('slot', 2), ah=('imm', PAT_BYTES))
W(0xFF84)                       # cmp AL,#0xffff (operand -1), fn_12e1a's guard
BR(0xF4, "MAPBAD")              # beq -> claim returned 0xffff: failure
W(0x0084); BR(0xF0, "MAPBAD")   # cmp AL,#0 ; bne -> unexpected nonzero offset

# ---- 4. the pattern, via @(n,X), X = map
W(0x031B)                       # ld X,@(3,Y)
for i, val in enumerate(PATTERN):
    if 0 <= val <= 0x7f:
        W(0x0200 | (val << 8) | 0x14)       # ld AL,#val          (1 word)
    else:
        hi, lo = (val >> 8) & 0xFF, val & 0xFF
        assert hi != 0 and 1 <= hi <= 0x7f, hex(val)   # prefix byte: nonzero, sign-safe
        W((hi << 8) | 0x00, (lo << 8) | 0x14)  # ONE 2-word item: prefix + ld AL,#lo
        # fold = sext8(hi)<<8 + sext8(lo) = val (both bytes <= 0x7f here: unsigned-safe)
    W(0x0000 | (i << 8) | 0x26)             # st AL,@(i,X): op (2<<4)|(1<<2)|2 = 0x26
    # 0x2B would be st X,@(n,Y) -- storing the map pointer into frame slots!

# ---- 5. flush
ca.call2(W, BSR, SINKFLUSH, al=('slot', 2), ah=('imm', PAT_BYTES))
W(0x0084); BR(0xF4, "FLUSHFAIL")

# ---- 6. digest SKIP (md_type=3, data=NULL, len=0)
ca.calln(W, BSR, SETDIGEST, al=('slot', 2), ah=('imm', 3),
         stack=[('imm', 0), ('imm', 0)], stage='AL')
W(0x0084); BR(0xF4, "DIGESTFAIL")

# ---- 7. close -- the first word commits here
ca.call1(W, BSR, SINKCLOSE, al=('slot', 2))

# ---- 8. verdict: re-read STATE
getinfo_prep(KEY_STATE)
W(0x0114)
W(0x0210)
BSR(GETINFO)
W(0x0084); BR(0xF4, "CTRLFAIL")
W(0x0517)                       # ld AL,@(5,Y)  STATE low half
W(0x0084); BR(0xF4, "SUCCESS")  # cmp AL,#0 ; beq -> STATE == VALID
W(0x2814)                       # "battery 20%"  INCOMPLETE / INVALID
BSR(SPEAK)
BR(0xE0, "OUT")
LBL("SUCCESS")
W(0x2714)                       # "battery 10%"  SUCCESS
BSR(SPEAK)
BR(0xE0, "OUT")

# ---- failure tails with an OPEN sink: close, then speak
LBL("MAPBAD")
W(0x2A14)                       # "battery 40%"
W(0x0027)                       # st AL,@(0,Y)  (id stash; key phase is over)
BR(0xE0, "CLOSESPK")
LBL("FLUSHFAIL")
W(0x2B14)                       # "battery 50%"
W(0x0027)
BR(0xE0, "CLOSESPK")
LBL("DIGESTFAIL")
W(0x2C14)                       # "battery 60%"
W(0x0027)
BR(0xE0, "CLOSESPK")
LBL("CLOSESPK")
ca.call1(W, BSR, SINKCLOSE, al=('slot', 2))
W(0x0017)                       # ld AL,@(0,Y)
BSR(SPEAK)
BR(0xE0, "OUT")

LBL("EOPEN")                    # open failed: no sink, nothing to close
W(0x2914)                       # "battery 30%"
BSR(SPEAK)
BR(0xE0, "OUT")

LBL("CTRLFAIL")                 # no sink (pre-read) or post-close contradiction
W(0x2314)                       # "conference call failed"
BSR(SPEAK)
BR(0xE0, "OUT")

LBL("OUT")
W(0xF80F)                       # leavel -8, which returns

# ---- layout (proven machinery, verbatim from probe137/139) ----
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
        if addrs[i] not in dstarts:
            print("BOUNDARY FAIL at", hex(addrs[i]), "item:", item)
            for a in range(addrs[i]-8, addrs[i]+8):
                print("   %07x: %04x %s" % (a, patched[a],
                      "START" if a in dstarts else ""))
            raise SystemExit(1)
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
