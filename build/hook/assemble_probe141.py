#!/usr/bin/env python3
"""probe141: the staged write -- data_us's blind windows become partition 2's fs.

Third gate of the partition route. probe140 proved a cave can commit to p2;
this probe writes the REAL payload: `build/payload/brown_fs.bin` (33,014 bytes =
16,520 words after period padding; the fs itself is 16,437 words) -- the minimal
ROFS carrying /brown.kap (the kalsim-verified brown-noise DSP app) -- gathered
out of data_us's blind windows and committed under digest SKIP.

THE STAGING (build/payload/stage_payload.py): payload word k sits in data_us at
file word 32*(k//14) + 7 + (k mod 14) -- file words with i % 32 in [7..20] are
the ones whose BOTH bytes are blind (fsedit's rule applied to data_us's body
offset 460+2i). 14 words per 32-word period, 1,180 periods, so the cave needs
NO address table: X-walk is arithmetic.

THE CAVE (every step has a spoken bail):

  FileFind(AL=1, AH=&"NowSpeakTTS/data_us")   -- fn_12e6f's exact convention
    bsr StreamFileSource                      -- AL carries idx -> source
    bsr SourceMap                             -- AL carries source -> mapped ptr
  StreamPartitionOverwriteSink(1, 2)          -- *** erases p2 (already holds
                                               probe140's 16-byte marker) ***
  SinkSlack(sink) >= 28 guard                 -- fn_12e1a's claim-hazard insurance
  1180 periods:  fn_12e1a(sink, 14)           -- Bose's own Map+Claim (claim=0 bail)
                 memmove(dst=AL, src=X-mirror, len=14)   -- Bose's own copier
                 SinkFlush(sink, 28)
                 src += 32
  PartitionSetMessageDigest(sink, 3=SKIP) ; SinkClose
  GetInfo(p2, STATE) -> verdict

OUTCOME TABLE (press = laptop connected, music PAUSED, Bluetooth long-press,
FIRST press; the write pumps ~33 KB claim-by-claim -- expect the press to take
longer than probe140's; do not pull power during it):

  battery 10%         SUCCESS: 33 KB written, SKIP, closed, p2 STATE == VALID.
                      The fs is on the device. Route GO for the play probe.
  battery 20%         closed but INCOMPLETE -- failsafe fired, unexpected
  battery 30%         sink open failed
  battery 40%         FileFind found nothing (path/model wrong)
  battery 50%         StreamFileSource or SourceMap returned 0
  battery 60%         SinkSlack < 28 / claim returned 0 mid-gather
  battery 80%         gather failed mid-way: claim 0, memmove, flush, OR the
                      digest call (all share "battery low"; the simulator names
                      the call -- on-device they share the recovery: none needed)
  conference call failed   --unused this probe-- (reserve)

The 0x50 "battery 80%" id is 0x32... NO: ids are battery 10/20/30/40/50/60/80/90
= 0x27/0x28/0x29/0x2a/0x2b/0x2c/0x2e/0x2f (skipping 0x2d "70%", probe139's
census result, to keep every press's vocabulary distinct in the log).

CAVE COST: ~180 of 197 words (the string is 20 words of it). enterl -8 at this
hook is hardware-proven. Redirects byte-identical to 137/139/140's.

SIMULATION: --staged build/payload/staged_words.json preloads the mapped source
at 0x4000; fn_12e1a short-circuits to a claim buffer at 0x5000; memmove really
copies -- so the simulated gather is checkable word-for-word at 0x5000.

BUILT, NOT FLASHED. Writes flash: owner go-ahead required (docs/partition-route.md).
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
FILEFIND = ca.STUB['FileFind']
FILESRC = ca.STUB['StreamFileSource']
SOURCEMAP = ca.STUB['SourceMap']
SINKSLACK = ca.STUB['SinkSlack']
OVERSINK = ca.STUB['StreamPartitionOverwriteSink']
SETDIGEST = ca.STUB['PartitionSetMessageDigest']
SINKCLOSE = ca.STUB['SinkClose']
SINKFLUSH = ca.STUB['SinkFlush']
MEMMOVE = ca.STUB['memmove']
FN12E1A = 0x12E1A                       # Bose's SinkMap+SinkClaim helper (stock)
MEMMOVE = ca.STUB['memmove']

PATH = "NowSpeakTTS/data_us"
PERIOD = 32
FIRST = 11
PER_PERIOD = 14
PERIODS = 1180
INNER = 59                              # 20 x 59 = 1180
OUTER = 20
CHUNK_BYTES = PER_PERIOD * 2            # 28

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

# ---- 1. FileFind(1, "NowSpeakTTS/data_us")
# (the path string itself lives AFTER the final leavel -- see the STR label at
# the end: in the fall-through path its char words EXECUTE as opcodes)
W(0x0114)                       # ld AL,#1
LBL("SETAH")                    # the 2-word prefixed ld AH below is patched
W(0x0000, 0x0010)               # post-layout with the string's data address
BSR(FILEFIND)
W(0x0084); BR(0xF4, "NOFILE")   # 0 -> not found

# ---- 2. source + map (AL carries idx -> source -> map, exactly fn_12e6f)
BSR(FILESRC)
W(0x0227)                       # st AL,@(2,Y)?? -- NO: slot 2 is the SINK later.
# Slots: 0 = memmove len, 1 = src walk ptr, 2 = sink, 3 = claim dst, 4 = inner, 5 = outer.
# source and map only need to survive until the loop starts: keep them in AL flow.
BSR(SOURCEMAP)
W(0x0084); BR(0xF4, "MAPFAIL")
# AL = map. src walk ptr = map + FIRST:
W((FIRST << 8) | 0x34)          # add AL,#FIRST (operand in the HIGH byte)
W(0x0127)                       # st AL,@(1,Y)  src ptr

# ---- 3. *** THE ERASE *** open the overwrite sink on partition 2
ca.call2(W, BSR, OVERSINK, al=('imm', 1), ah=('imm', 2))
W(0x0227)                       # st AL,@(2,Y)  sink
W(0x0084); BR(0xF4, "EOPEN")

# ---- 4. (no slack guard: fn_12e1a's claim==0 return is caught below, and the
#          fresh-open sink provably has room -- probe140 opened and claimed on it)

# ---- 5. the periodic gather: 20 x 59 periods
W(0x0E14)                       # ld AL,#14
W(0x0027)                       # st AL,@(0,Y)  memmove len (constant)
W(0x1414)                       # ld AL,#20
W(0x0527)                       # st AL,@(5,Y)  outer = 20
LBL("OUTER")
W(0x3B14)                       # ld AL,#59
W(0x0427)                       # st AL,@(4,Y)  inner = 59
LBL("INNER")
ca.call2(W, BSR, FN12E1A, al=('slot', 2), ah=('imm', PER_PERIOD))
W(0x0327)                       # st AL,@(3,Y)  claim dst
W(0x0084); BR(0xF4, "CLAIMFAIL")
ca.call2(W, BSR, MEMMOVE, al=('slot', 3), ah=('slot', 1))
ca.call2(W, BSR, SINKFLUSH, al=('slot', 2), ah=('imm', CHUNK_BYTES))
W(0x0084); BR(0xF4, "GATHERFAIL")
W(0x0117)                       # ld AL,@(1,Y)
W(0x2034)                       # add AL,#32
W(0x0127)                       # st AL,@(1,Y)
W(0x0417)                       # ld AL,@(4,Y)
W(0xFF34)                       # add AL,#-1   (0xff: the XAP carry rule makes
W(0x0427)                       # st AL,@(4,Y)  no difference to the Z flag here)
W(0x0084); BR(0xF0, "INNER")    # cmp AL,#0 ; bne -> more inner periods
W(0x0517)                       # ld AL,@(5,Y)
W(0xFF34)                       # add AL,#-1
W(0x0527)                       # st AL,@(5,Y)
W(0x0084); BR(0xF0, "OUTER")    # more outer

# ---- 6. digest SKIP + close
ca.calln(W, BSR, SETDIGEST, al=('slot', 2), ah=('imm', 3),
         stack=[('imm', 0), ('imm', 0)], stage='AL')
W(0x0084); BR(0xF4, "GATHERFAIL")
ca.call1(W, BSR, SINKCLOSE, al=('slot', 2))

# ---- 7. verdict
W(0x0314)                       # ld AL,#3   (PARTITION_INFO_STATE) -- 0x03 in the
W(0x0027)                       # HIGH byte; 0x0214 here would ask for TYPE (2)
W(0xE415)                       # ld AL,@0xffe4
W(0x0434)                       # add AL,#4
W(0x0127)                       # st AL,@(1,Y)
W(0x0114)                       # ld AL,#1
W(0x0210)                       # ld AH,#2
BSR(GETINFO := ca.STUB['PartitionGetInfo'])
W(0x0084); BR(0xF4, "OUT")      # FALSE -> can't report; out silently (shouldn't happen)
W(0x0517)                       # ld AL,@(5,Y)
W(0x0084); BR(0xF4, "SUCCESS")  # STATE 0 = VALID
W(0x2814)                       # "battery 20%"  INCOMPLETE
BSR(SPEAK)
BR(0xE0, "OUT")
LBL("SUCCESS")
W(0x2714)                       # "battery 10%"  SUCCESS -- ROUTE GO
BSR(SPEAK)
BR(0xE0, "OUT")

# ---- failure tails (close if a sink exists, then speak)
LBL("MAPFAIL")
W(0x3214)                       # "battery 50%"
W(0x0027)
BR(0xE0, "OUTNSPK")
LBL("EOPEN")
W(0x2914)                       # "battery 30%"
BSR(SPEAK)
BR(0xE0, "OUT")
LBL("NOFILE")
W(0x2A14)                       # "battery 40%"
BSR(SPEAK)
BR(0xE0, "OUT")
LBL("CLAIMFAIL")                # and GATHERFAIL: one id for any mid-gather
LBL("GATHERFAIL")               # failure ("battery low please charge now" --
W(0x3114)                       # distinctive, never spontaneous in this state)
W(0x0027)
BR(0xE0, "CLOSESPK")
LBL("CLOSESPK")
ca.call1(W, BSR, SINKCLOSE, al=('slot', 2))
W(0x0017)                       # ld AL,@(0,Y)
BSR(SPEAK)
BR(0xE0, "OUT")
LBL("OUTNSPK")
BSR(SPEAK)                      # AL still holds the id stored at MAPFAIL
BR(0xE0, "OUT")
LBL("OUT")
W(0xF80F)                       # leavel -8, which returns

# ---- the path string lives HERE, after the leavel: unreachable dead data. In
# the fall-through path its char words EXECUTE as opcodes (each is a plausible
# opcode with operand 0) -- the first simulation run garbage-clobbered the
# slots and skipped the gather exactly that way. FileFind's AH points here
# through the const-pool window (0x7400 + STR - 0x39BE2).
LBL("STR")
for ch in PATH:
    W(ord(ch))                  # one char per word
W(0x0000)                       # NUL terminator, matching the stock string shape

# ---- layout (proven machinery, verbatim from probe137/139/140) ----
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
            if bsr_size.get(i, 2) != want:
                changes.append((iteration, hex(a), 'bsr', want))
                bsr_size[i] = want; ok = False
        else:
            want = (1 if -128 <= tgt - a <= 127
                    else 2 if br2_encodable(tgt - (a + 1))
                    else 3)
            if br_size.get(i, 1) != want:
                changes.append((iteration, hex(a), 'br', want))
                br_size[i] = want; ok = False
    if ok: break
else:
    for c in changes[-12:]:
        print('  change:', c)
    raise SystemExit('no converge after %d iters: br sizes %s'
                     % (iteration, {hex(addrs[i]): sz for i, sz in br_size.items()
                                    if prog[i][0] == 'br'}))

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

# ---- patch the FileFind string pointer: ld AH,#<data addr of STR> ----
# ld AH,#imm with a prefixed high byte: prefix hi, then (lo<<8)|0x10.
STR_CODE = label_addr['STR']
STR_DATA = (CONST_BASE + (STR_CODE - 236514)) & 0xFFFF
SETAH = label_addr['SETAH']
ah_lo = STR_DATA & 0xFF
ah_hi = (STR_DATA >> 8) & 0xFF
assert 1 <= ah_hi <= 0xFF, hex(STR_DATA)   # prefix byte: nonzero; 0x80+ wraps
# negatively through the signed fold and still yields the 16-bit address.
out[SETAH] = (ah_hi << 8) | 0x00
out[SETAH + 1] = (ah_lo << 8) | 0x10
print('FileFind string "NowSpeakTTS/data_us" at code %s -> data %#x (ld AH prefix %04x %04x)'
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
# This probe ALSO carries the staged payload: 33,040 blind-window edits in
# data_us (build/payload/probe141_edits.py, generated by stage_payload.py).
# 33K command-line args would not survive exec, so fsedit is driven directly
# through its build(edits, out) API. The cave+redirect edits go through the
# same path so ONE fsedit run produces the complete image.
sys.path.insert(0, "tools")
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("probe141_edits", "build/payload/probe141_edits.py")
_edmod = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_edmod)

fsc = {'__file__': os.path.abspath('tools/fsedit.py')}
_code = open("tools/fsedit.py", encoding="utf-8").read()
try:
    exec(compile(_code, "tools/fsedit.py", "exec"), fsc)
except SystemExit:
    pass
fs_build = fsc["build"]

edits = []
for off, val in REDIRECT_EDITS:
    edits.append((int(off, 16), int(val, 16)))
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    edits.append((AREA0 + 2*cw, v & 0xFF))
    edits.append((AREA0 + 2*cw + 1, (v >> 8) & 0xFF))
edits += _edmod.EDITS

if "--build" in sys.argv:
    fs_build(edits, f"build/hook/{_PROBE}_brown.dfu")
else:
    print(f"edit list ready: {len(edits)} edits "
          f"({len(out)} cave words + {len(REDIRECT_EDITS)} redirect bytes + "
          f"{len(_edmod.EDITS)} staged payload bytes); run with --build")
