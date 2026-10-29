"""probe147: THE REFILL LOOP, RATE-MATCHED -- probe146's press (6-7 s, same
quality) refuted the double-free theory and pinned the real killer: the
production/consumption MISMATCH. This probe matches the rate exactly. The
press narrative and the full diagnosis chain live in the field log, 2026-10-06.

## THE REAL KILLER: 2291 samples/s into a 2000 samples/s drain

probe145/146 delivered 252 samples every 110 ms = 2291 samples/s. The DSP
consumes the 2000 Hz tone at exactly 2000 samples/s (set_tone_rate_from_vm:
copy period 16 ms mono at 2000 Hz; the mix pulls the resample buffer at the
tone rate). Pull-driven delivery self-balances -- so the surplus had nowhere
to go but the port: it backpressured at capacity (~0.9 s in), and EVERY tick's
source then stalled ~32 bytes short of drained. An undrained source object is
not self-reclaiming (drained ones are -- stream.h), and probe146 (no close,
per the double-free diagnosis) leaked one per tick until the ~60-block source
pool died at a FIXED count: the reproducible ~6-7 s stop. probe145's per-tick
close attempted the same free -- its ~9 s was the same death, within the
owner's estimate error. The lifetime barely moving between probes (and moving
the WRONG way for the double-free theory) is what broke it: the DSP side is
identical in both, so a DSP-disarm death could not shift; only a VM-side
per-tick mechanism could.

## THE FIX: produce exactly what is consumed

216 samples (108 bytes) every 108 ms = 2000.000 samples/s. The fill is
accepted whole by the near-empty port (216 <= its 256 capacity), the source
drains within milliseconds, self-reclaims, nothing is closed, nothing leaks,
and the pipe never starves. Constants only: NBYTES 108 (34 blocks), buf
malloc(111), delay 108 ms -- the cave structure is probe146's, 190 words
(incl. the new 0x1F failure speech below).

Remaining known limitation (NOT addressed here -- one variable per press):
a message-loop tick late by >~32 ms starves the port into the DSP's two-empty-
check disarm (16 ms cadence at this rate, 30 ms timeout). That death is
RANDOM-timed (jitter), unlike the fixed-count deaths diagnosed above -- if
probe147 dies at a random time, that is the survivor, and the fix (SinkSlack
gate + a single 0x1072 re-arm) is probe148. The occasional DROPS = the same
jitter one empty check deep; survivable, audible as a momentary gap.

## The 0x1F failure speech (8 of the 13 spare words)

If a rebuild ever fails (RSRC 0 = allocation refused -- the pool suspect;
ADPCM/TStart FALSE), the tick speaks 0x1F "muted" once from the message loop
and stops. Silence after noise = the DSP-disarm path; "muted" = the VM path,
named. The arm path shares RETFILL, so an arm-side rebuild failure also
speaks. The boot gate still bails before any of this at power-on.

## The press (laptop connected, music PAUSED, long-press the BLUETOOTH button)

  NOISE RUNS MINUTES+                  the rate match holds; the leak is dead.
                                       Let it run. (Jitter-disarm may still end
                                       it randomly -- note the time.)
  stops at ~7-9 s again, then "muted"  the VM pool is still failing; the speech
                                       names the rebuild stage.
  stops at ~7-9 s again, silent        a fixed-time DSP-side event; deep dig.
  stops at a RANDOM time, silent       the jitter-disarm survivor -> probe148.
  drops (momentary gaps)               expected occasionally; note frequency.
  "modem" quality                      unchanged by design -- shaping is the
                                       probe AFTER sustain holds.

BUILT, NOT FLASHED -- owner go-ahead gates every flash.
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
CONST_BASE = 0x7400

BACK = 0xE06D
SPEAK = 0xDF7F
MALLOC = ca.STUB['malloc']
KALMSG = ca.STUB['KalimbaSendMessage']
KSINK = ca.STUB['StreamKalimbaSink']
RSRC = ca.STUB['StreamRegionSource']
ADPCM = ca.STUB['TransformAdpcmDecode']
TSTART = ca.STUB['TransformStart']
TFS = ca.STUB['TransformFromSink']
TSTOP = ca.STUB['TransformStop']
TDISC = ca.STUB['TransformDisconnect']
SDISC = ca.STUB['StreamDisconnect']
SRCLOSE = ca.STUB['SourceClose']
MSGLATER = ca.STUB['MessageSendLater']
MSKTASK = ca.STUB['MessageSinkTask']

RATE = 2000
NBYTES = 108             # 6 priming + 34 x 3 zero-net blocks = 216 samples
                         #   = 108 ms of audio at 2000 Hz
BUF_WORDS = 111          # 3 state + 108 sample bytes -> the 138 pool
SEED = 0x7F           # any nonzero state is on the same maximal LFSR cycle;
                         # 1-word immediate (0x4CE1 cost a prefix word)
WATCHDOG_ID = 0x41       # our own one-shot startup-check id: small on purpose
                         #   (1-word immediates); only the port's stream
                         #   machinery and our own timer send to this task
WATCHDOG_MS = 127        # if no completion arrived by then, speak 0x1F (1-word imm)
COMPLETION = 0x8026      # MESSAGE_STREAM_DISCONNECT: the transform's self-dispose
# (probe147's rate-match constant REFILL_MS is retired by probe148:)
REFILL_MS_UNUSED = 108
                         #   the 2000 Hz tone at exactly 2000 samples/s, so the
                         #   fill MUST be 216 samples per 108 ms -- 100% duty,
                         #   exact balance. probe145/146 delivered 252/110 ms =
                         #   2291/s: the port backpressured, every tick's source
                         #   stalled ~32 bytes short of drained, and one undrained
                         #   source object leaked per tick until the pool died at
                         #   a FIXED count -- the reproducible ~7-9 s stop (146's
                         #   no-close made it strictly worse; the header reading
                         #   that justified dropping the close was right about
                         #   drained sources but the sources never drained).
                         #   Rate-matched, each fill is accepted whole by the
                         #   empty port (216 <= 256), the source drains within
                         #   ms, self-reclaims, and nothing leaks.
DIAG_ID = 0x1F           # "muted": no completion arrived / a rebuild failed

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

# CAVE = entry jump. CAVE+1, CAVE+2 = the TaskData {hwrd, lwrd} of the handler,
# flashed data the message loop only ever READS (docs/message-task-abi.md section 5).
# The handler's address is known only after layout, so the low word is patched then.
# Code proper starts at CAVE+3; execution never falls into the TaskData because the
# entry jump skips it and every function exits by leavel/rts.
# NO const TaskData: the completion message carries the sink's id, not our buf,
# so the handler needs a RAM TaskData whose third word holds buf (probe116's
# malloc'd pattern, finally flashed). Code starts right after the entry jump.
CODE_AT = CAVE + 1
assert blind(CODE_AT) and in_run(CODE_AT)

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))

BACK = 0xE06D

# ------------------------------------------------------------------- the ARM
LBL("ARM")                      # the hook's entry jump at CAVE targets this label
W(0xF80B)                       # enterl -8
BSR(BACK)                       # stock back-call first, probe77's proven order

# GATE *IS* THE ARM: 0x1072 once, at 2000 Hz, words b/c/d = 0 (probe134 verbatim).
W(0x0014)                       # ld AL,#0
W(0x0027); W(0x0127); W(0x0227) # b = c = d = 0         slots 0..2
W(*ca.imm_words(RATE, 0x10))    # ld AH,#2000   arg2 = rate
W(*ca.imm_words(0x1072, 0x14))  # ld AL,#0x1072 arg1 = MESSAGE_SET_TONE_RATE
BSR(KALMSG)
W(0x0084); BR(0xF4, "OUT")      # FALSE = no DSP = boot-safe silent bail

# buf = malloc(113): buf[0] LFSR, buf[1] completion flag, buf[2] ksink,
# buf[3..110] the 108 sample bytes, buf[111..112] the RAM TaskData
# {hi,lo handler} -- the task pointer is buf+111, one add from buf.
ca.call1(W, BSR, MALLOC, al=('imm', 113))
W(0x0427)                       # st AL,@(4,Y)  buf
W(0x0084); BR(0xF4, "OUT")      # pool exhausted: silent no-op

W(0x041B)                       # ld X,@(4,Y)   X = buf
W(0x7F14)                       # ld AL,#0x7F   the seed
W(0x0026)                       # st AL,@(0,X)  buf[0] = seed
W(0x0014)                       # ld AL,#0
W(0x0126)                       # st AL,@(1,X)  buf[1] = 0 (no completion yet)

# ksink = StreamKalimbaSink(3) -> buf[2]
ca.call1(W, BSR, KSINK, al=('imm', 3))
W(0x0084); BR(0xF4, "OUT")
W(0x041B)                       # ld X,@(4,Y)   (X is the link register)
W(0x0226)                       # st AL,@(2,X)  buf[2] = ksink

# the RAM TaskData at buf[111..112]: {3, lo(HANDLER)} -- hi is always 3 for a
# cave at 0x3Exxxx; lo is patched after layout (HLO_IDX)
W(0x0314)                       # ld AL,#3
W(0x6F26)                       # st AL,@(0x6F,X)  buf[111] = hi(HANDLER)
HLO_IDX = len(prog)
W(*ca.imm_words(0xE200, 0x14))  # ld AL,#lo(HANDLER) -- PATCHED after layout
W(0x7026)                       # st AL,@(0x70,X)  buf[112] = lo(HANDLER)

# task = buf + 111, parked in slot 3 (the gate's dead staging slot) -- BOTH
# remaining calls need it.
W(0x0417); W(0x6F34); W(0x0327) # ld AL,@(4,Y); add AL,#0x6F; st AL,@(3,Y)

# OWN the port's task registration (the probe113-vetted idiom): completions
# (0x8026) and any port stream messages now come to OUR TaskData.
W(0x0216)                       # ld AL,@(2,X)  ksink   (X = buf still)
W(0x0313)                       # ld AH,@(3,Y)  task
BSR(MSKTASK)                    # (no success check: if this fails, no completion
                                #   ever comes and the watchdog speaks "muted")

# WATCHDOG: MessageSendLater(task, 0x41, 0, 127) -- if no completion arrives
# within 127 ms of the first fill, the handler says so. ABI: arg1 task -> AL,
# arg2 id -> AH, message -> slot0, delay HIGH -> slot1, delay LOW -> slot2.
W(0x0014)                       # ld AL,#0
W(0x0027); W(0x0127)            # message = 0   slot0; delay HIGH = 0   slot1
W(0x7F14); W(0x0227)            # ld AL,#127; st AL,@(2,Y)  delay LOW = 127
W(0x4110)                       # ld AH,#0x41   arg2 = our watchdog id
W(0x0317)                       # ld AL,@(3,Y)  arg1 = task
BSR(MSGLATER)

# first fill + build; the 0x8026 completion drives everything after this
W(0x0417)                       # ld AL,@(4,Y)  buf
BSR("REFILL")

LBL("OUT")
W(0xF80F)                       # leavel -8

# ---------------------------------------------------------------- the HANDLER
# Runs in the main VM message loop. Task in AL (= buf+111, so buf = AL-111),
# id in AH. AH survives every load below.
LBL("HANDLER")
W(0xF50B)                       # enterl -5  (slots 0..2 usable)
W(*ca.imm_words(0xFFE3, 0x14))  # ld AL,@0xffe3  (the X mirror: AL = task)
W(0x9134)                       # add AL,#0x91 (-111)  -> buf
W(0x0227)                       # st AL,@(2,Y)  slot2 = buf
W(0x021B)                       # ld X,@(2,Y)   X = buf
W(*ca.imm_words(COMPLETION, 0x80))  # cmp AH,#0x8026
BR(0xF4, "ISCOMP")
W(0x4180)                       # cmp AH,#0x41  (our watchdog id, 1 word)
BR(0xF4, "ISWDOG")
BR(0xE0, "HEXIT")               # port stream messages (0x8022/0x8021): ignore

LBL("ISWDOG")                   # the one-shot startup check, 127 ms in:
W(0x019A)                       # tst @(1,X)    the completion flag (Bose's own
                                #   tst @(v,X) form, fn_31e6f's 0x029a)
BR(0xF0, "HEXIT")               # bne: flag nonzero = completions seen, exit
BSR("SAY8")                     # "muted": NO completion in 127 ms -- the
                                #   0x8026-to-a-cave-task assumption failed

LBL("ISCOMP")                   # the previous transform COMPLETED (self-disposed:
                                #   its source fully drained -- nothing to clean);
                                #   placed last so it FALLS THROUGH into HEXIT
W(0x0126)                       # st AL,@(1,X)  buf[1] = buf (nonzero: the flag
                                #   only needs to read back as seen)
W(0x0217)                       # ld AL,@(2,Y)  buf -> REFILL's arg
BSR("REFILL")                   # fill + source + transform + start (NO timer:
                                #   the NEXT completion is the next clock)
LBL("HEXIT")
W(0xF50F)                       # leavel -5

# ------------------------------------------------------------------- REFILL
# fill + source + transform + start. buf arrives in AL. NO teardown (the
# previous transform completed and disposed ITSELF -- never destroyed mid-stall,
# so nothing leaks), NO timer (the completion message is the clock). A failed
# rebuild speaks 0x1F and the chain ends: no completion will ever follow.
LBL("REFILL")
W(0xF80B)                       # enterl -8
W(0x0227)                       # st AL,@(2,Y)  buf
W(0x021B)                       # ld X,@(2,Y)
W(0x0016)                       # ld AL,@(0,X)  LFSR state
W(0x0127)                       # st AL,@(1,Y)  -> the generator's seed slot
W(0x0338)                       # add X,#3      write pointer = buf+3

# ---- GEN, inlined: 6 priming bytes + 34 zero-net blocks (108 bytes = 216
# samples; fills the empty port whole). Pair shifts: AH zeroed once here, no
# overflow possible (r <= 0x88 -> r<<4 <= 0x880). Counter in slot 3.
W(0x8014)                       # ld AL,#0x80
W(0x0026)                       # st AL,@(0,X)   prime[0]
W(0x7FD4)                       # xor AL,#0x7F -> 0xFF
W(0x0126); W(0x0226); W(0x0326); W(0x0426)   # prime[1..4] = 0xFF
W(0x08D4)                       # xor AL,#0x08 -> 0xF7
W(0x0526)                       # prime[5]
W(0x0638)                       # add X,#6      past the priming
W(0x0010)                       # ld AH,#0      the pair-shift zero
W(0x2214)                       # ld AL,#34     block counter
W(0x0327)                       # st AL,@(3,Y)
LBL("GENLOOP")
W(0x0117)                       # ld AL,@(1,Y)  x
W(0x01C4)                       # and AL,#1
W(0x0074)                       # neg AL        0/0xFFFF
W(0xB400, 0x00C4)               # and AL,#0xB400  (2-word prefixed)
W(0x0427)                       # st AL,@(4,Y)  mask
W(0x0117)                       # ld AL,@(1,Y)  x again (slot1 still holds it)
W(0x01A4)                       # asr #1        pair shift, AH=0 -> logical
W(0x04D7)                       # xor AL,@(4,Y) ^= mask
W(0x0127)                       # st AL,@(1,Y)  new x
W(0x0100, 0x88C4)               # and AL,#0x88    r
W(0x0027)                       # st AL,@(0,Y)  slot0 = r
W(0x30D4)                       # xor AL,#0x30
W(0x0026)                       # st AL,@(0,X)  out0
W(0x0017)                       # ld AL,@(0,Y)  r
W(0x04A4)                       # asr #4        r>>4, bit3 = r's bit7
W(0x08C4)                       # and AL,#0x08  t
W(0x0527)                       # st AL,@(5,Y)
W(0x0017)                       # ld AL,@(0,Y)  r
W(0x04A0)                       # asl #4        bit3 -> bit7 (no overflow)
W(0x0100, 0x80C4)               # and AL,#0x80  t2
W(0x05D7)                       # xor AL,@(5,Y) t2 ^ t
W(0x0100, 0x84D4)               # xor AL,#0x84  (prefixed)
W(0x0226)                       # st AL,@(2,X)  out2
W(0x0517)                       # ld AL,@(5,Y)  t
W(0x04A0)                       # asl #4        A = t<<4 = r & 0x80
W(0x05D7)                       # xor AL,@(5,Y) A ^ t
W(0x0100, 0xCBD4)               # xor AL,#0xCB  (prefixed)
W(0x0126)                       # st AL,@(1,X)  out1
W(0x0338)                       # add X,#3
W(0x0317)                       # ld AL,@(3,Y)  counter
W(0xFF34)                       # add AL,#0xFF  -1 (sets Z)
W(0x0327)                       # st AL,@(3,Y)
BR(0xF0, "GENLOOP")             # bne while counter != 0

# ---- source + transform + start
W(0x021B)                       # ld X,@(2,Y)   X is the link register: reload
W(0x0117)                       # ld AL,@(1,Y)  final x
W(0x0026)                       # st AL,@(0,X)  buf[0] = x (the walk continues)
W(0x0217)                       # ld AL,@(2,Y)
W(0x0334)                       # add AL,#3     buf+3
W(0x6C10)                       # ld AH,#108    the 216-sample fill
BSR(RSRC)
W(0x0084); BR(0xF4, "RBFAIL")
W(0x0327)                       # st AL,@(3,Y)  src (frame slot)
W(0x021B)                       # ld X,@(2,Y)
W(0x0212)                       # ld AH,@(2,X)  ksink (mode 2 = @(n,X): 0x12)
BSR(ADPCM)
W(0x0427)                       # st AL,@(4,Y)  t
W(0x0084); BR(0xF4, "RBFAILSRC")
W(0x0417)                       # ld AL,@(4,Y)
BSR(TSTART)
W(0x0084); BR(0xF4, "RBFAILSRC")
W(0xF80F)                       # leavel -8
LBL("RBFAILSRC")
W(0x0317)                       # ld AL,@(3,Y)  the FRESH src: created but never
BSR(SRCLOSE)                    #   pumped, so the close is mandatory (probe105)
BSR("SAY8")                     # "muted": the rebuild failed here
W(0xF80F)                       # leavel -8
LBL("RBFAIL")
BSR("SAY8")                     # "muted"  (RSRC returned 0: the pool)
W(0xF80F)                       # leavel -8

LBL("SAY8")                     # shared "muted": one far call, three sites
W(0x1F14)                       # ld AL,#0x1F
BSR(SPEAK)
W(0x00E2)                       # rts

# ---- layout (proven machinery, verbatim from probe144: tightened reservation,
# ---- lazy next_blind, connector branches, last-word displacements) ----
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
            if nb_probe is None:
                _tot = sum(len(p[1]) if p[0]=='w' else 3 for p in prog if p[0]!='label')
                raise AssertionError('IT%d exhausted at %d/%d; static item words=%d, bands=%d, conn so far=%d' % (iteration, i, len(prog), _tot, len(_BANDS), len(extra)))
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

# ---- the entry jump, then patch lo(HANDLER) into the ARM's TaskData build ----
entry_v = label_addr["ARM"] - CAVE
assert -128 <= entry_v <= 127
assert CAVE not in out, 'the entry jump word is already occupied'
out[CAVE] = ((entry_v & 0xFF) << 8) | 0xE0
HANDLER_AT = label_addr["HANDLER"]
assert (HANDLER_AT >> 16) == 3, hex(HANDLER_AT)
_hlo = ca.imm_words(HANDLER_AT & 0xFFFF, 0x14)
assert len(_hlo) == 2, _hlo
_ha = addrs[HLO_IDX]
for k, v in enumerate(_hlo):
    out[_ha + k] = v
print("handler a=%#x -> t[1] built at runtime: hi=0003 (hardcoded), lo=%04x "
      "(imm patched at %#x)" % (HANDLER_AT, HANDLER_AT & 0xFFFF, _ha))

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
assert seen.get(CAVE) == label_addr["ARM"], (hex(CAVE), hex(label_addr["ARM"]), seen.get(CAVE))
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
