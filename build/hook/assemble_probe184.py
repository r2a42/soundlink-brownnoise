#!/usr/bin/env python3
"""probe184: the ONE at-scale partition-2 write -- the brown-noise ROFS (T08, 2026-10-12; built offline, NOT flashed). [ROUND-3 NOTE: corrections to this docstring are in the comment block at the end of the file]

Needs the owner's explicit go-ahead (J-D2, second approval) and a recorded probe184a that found the file
(outcome 0x12 or 0x35).  Flash NOTHING until docs/FLASH-PROTOCOL.md is met in full.  This file is the
design record of probe184; assemble_probe184a.py runs the SAME cave builder (this file) with a tiny
payload and a longer verdict, so the two cannot drift apart.  Companion files: narrow184_lib.py (payload,
ROFS, staging), gate_probe184.py (the world-model gate), docs/deep/firmware-study-2026-10-12/T08-184a-184-assemblers.md.

## VARIANTS (round 3, B02, 2026-10-12; narrow184_lib.PROBES is the table; outputs of probe184 / probe184a are unchanged)

  probe184_58k   58,700 B payload (seed 63, sha256 a488348b...ffa17), 2,106 periods, start 1,320: spares the region-A header,
                 the E6 array and the region-B tail (V03).   probe184a_58k  the tiny 184a staged from period 1,320.
  probe184_90k   90,004 B payload (T07 flat_22s), 3,224 periods, start 202: the J-D3 long alternative, every id garbled.
  Each has a one-line wrapper assemble_<name>.py (the preflight/caveguard gates read its REDIRECT_EDITS literal) and its
  own words/dfu/cmd files.  Comparison, hashes and gate output: docs/deep/round3-2026-10-12/B02-payload-staging-final-size.md.

## WHAT IT DOES (one press, centre LONG press = event 0x4004, hook 0x00e46, swallowed)

  1. FileFind(1, "NowSpeakTTS", 11) (pool copy), FileFind(dir, "data_us", 7) (carried), StreamFileSource.
  2. SKIPN: 1,270 x ADVANCE (SourceSize >= 64, SourceDrop 64) -- the start-period skip.  The span
     staged into data_us begins at period 1,270 (byte 81,280), not at period 0.
  3. LOOK, BEFORE ANY ERASE: SourceMap, and elements 18..21 must be "fsr_" (the ROFS magic).  A packed
     map, a wrong offset, a window that cannot be walked, or a stock data_us all stop here with p2 untouched.
  4. *** StreamPartitionOverwriteSink(1, 2) *** -- the p2 erase.
  5. 2,156 x GATHER: SourceMap, SinkMap+SinkClaim(28) via Bose's fn_12e1a, memmove 28 elements from map+18,
     SinkFlush(28), ADVANCE.  (28 BYTES a period: see narrow184_lib.py "the unit rule".)
  6. FINISH: SourceClose, PartitionSetMessageDigest(sink, 3 = SKIP, 0, 0), SinkClose.
  7. VERDICT: PartitionGetInfo(1, 2, STATE): 0 = VALID.  One spoken id.

## THE STAGING (FIRST = 9, the corrected rule; and a TAIL start so the ids survive)

  FIRST = 9: data_us words 9..22 of every 32-word period are fully writable (payload-184.md section 0), i.e.
  bytes 18..45 of every 64-byte period.  The ROFS goes into 28 bytes of each period from START_PERIOD = 1270
  on: 2,156 periods, data_us bytes 81,280..219,264 (ends 8 bytes before fsedit's compensation slack at
  219,272).  The header (words 0..38) is untouched.  tools/promptmap.py (unit model, header spared): all 57
  speech ids have NO staged word in their read set at this start (table in the T08 note); at start period 1
  (the STRATEGY text) none does.  The model leaves region A and the E6 array unknown (promptmap section 8.3),
  so this is a better bet than the head, not a proof.  python build/hook/assemble_probe184.py --start-period 1
  builds the head variant under the infix _sp1 (outputs never overwrite the default files).

## FILES AND HASHES (python build/hook/assemble_probe184.py --build; deterministic, rebuilt twice identical)

  payload   tools/brownnoise.py --rate 8000 --bytes 60100 --gen fft --loop --peak 0.985 --seed 63
            = T07 flat_15s, 15.025 s at 8000 Hz, sha256 ea70bed4021a0fa6f33ca3696633f2314485d6e7cea4f11a61ef05f22ef3ad13
  ROFS      60,368 B (/brown.adpcm flags 0x00 + the official 11-byte /ext_version), 2,156 periods, 0 pad bytes,
            sha256 96d0f672c04aaa1db768ff9c9a0dd7c918eb6e0e58d0a5071028703f3e4e580e
  cave      296 words: 155 in the const window (0x3E21D.. , the hook target is the first word), 141 in the
            code region (0x2331e.. , of them the 14 stub words that make the dead functions return 0)
            probe184_words.json sha256 e618367af7a49ba1f748b710d9fe9a3416215234f7dc5940735cf1e2e55000f4
  image     probe184_brown.dfu sha256 916e301badc9a0caa0dac56ce41d873bec1aa7ea5b3e469d5c015a80f8581e58
            60,537 bytes differ from the official 3.0.3, all inside the fs area: 59,989 staged data_us bytes
            (of 60,368 staged), 515 cave bytes (of 592), 3 redirect bytes, 12 XOR-balance flips, 18
            digest-compensation flips.
  edits     3 redirect bytes (hook 0x00e46 -> 0x3E21D: 0x706bd=04 0x706bf=d4 0x706c1=d5), the cave words as
            area bytes 0x6EA30 + 2 * word, and the staged bytes at area byte 600 + 64 * (1270 + p) + 18 + j
            (p = 0..2155, j = 0..27).  60,963 edits cannot go on one command line; the image is built through
            fsedit.build() in-process (as probe141 was); probe184_cmd.txt holds the rebuild command.

## OWNER GATES (each answered before the flash; none is pre-ticked)

  J-D2 the p2 route with the corrected risk text: ONE clean erase proven (probe140), geometry unmeasured, no p2
       readback, a 2,156-iteration loop never run, a staged data_us on the speaker until a stock one is flashed.
       Recommended yes ONLY if probe184a answered 0x12 or 0x35.
  J-D3 length: 15.025 s (this file) or 22.5 s (90,004 B: 3,224 periods, no tail start fits, every id garbled).
  J-D14 material: the recommended flat recipe (T07); the crest-3.0 alternative is a different payload sha and
       must be chosen BEFORE this flash (a content change after the erase costs another erase).

## THE PRESS (volume at the usual level, laptop connected, music PAUSED, USB unplugged after the readback)

  Centre LONG press ONCE, then wait for ONE spoken id.  The press takes seconds (the erase) and then 2,156
  flushes: DO NOT pull power, press nothing else.  A second press repeats the erase.  Write the time from the
  press to the id.  Then write the owner's words into docs/field-log.md before building anything else.

## OUTCOME TABLE (spoken ids; none is a stock prompt in this context, none is used by probes 139-143, 179-185 or 187)

  0x12 "voice prompts on"         VALID: the ROFS is on p2.  Flash the stock-data_us image next (185a, or the
                                  read-only census as image B) -- that is where the file is looked for.
  0x15 "auto off enabled"         closed but STATE != VALID, or PartitionGetInfo refused: not confirmed.
  0x14 "auto off disabled"        the write did not complete: the sink would not open, or a trap refused during
                                  the gather (SourceMap / claim / flush / the window), or the digest was refused.
                                  The sink was closed; p2 is INCOMPLETE.  Do not repeat the press unchanged.
  0x36 "select a bose speaker .." BEFORE the erase: elements 18..21 are not "fsr_" (packed map, other offset,
                                  or the stock data_us is on the speaker).
  0x37 "select the bose headphones .." BEFORE the erase: SourceSize < 64 or SourceMap 0 (the 1,270-step walk).
  0x38 "select the bose product .." BEFORE the erase: FileFind / StreamFileSource refused.
  silence or garbled speech       the staged span is hit after all.  Wait 60 s.  Then flash a stock-data_us
                                  image; if p2 was written it stays written (the recovery that is proven:
                                  flash #17, 2026-10-06).
  (the three "select ..." sentences differ by one noun; 0x14 / 0x15 differ by dis- / en-.)

## NOT KNOWN (the press answers them)

  SourceMap packing on a FILE source from a cave (one byte per word: proven for the stock readers, never run
  here), the window width and whether SourceDrop refills synchronously over 81 KB + 138 KB, SinkClaim/Flush
  units and the slack of a fresh p2 sink, flash time per 28-byte flush, any VM watchdog over ~3,400 steps,
  and whether the firmware puts a RAW_SERIAL partition into the union file system at all.

## GATES RUN (offline)

  assemble: decode-verify OK; cavesim probe90 control AL = 0x000e; build/hook/gate_probe184.py probe184:
  21 scenarios, 0 failed (every path; the bytes written to p2 equal the ROFS); tools/preflight.py probe184:
  OK (296 cave words and 3 redirect bytes in the image); tools/caveguard.py: SAFE.  No frame is larger than
  enterl -8; the hook sits at 54 of 316 stack words (tools/stackdepth.py 0xe46).  BUILT, NOT FLASHED.
"""

import os, re, sys, json, subprocess
sys.path.insert(0, 'tools')
import caveasm as ca

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm"); sys.path.insert(0, "build/hook")
import xapvm
import narrow184_lib as L

# assemble_probe184a.py runs this file through runpy with ENGINE_VARIANT set, so the two probes
# share ONE cave builder (and cannot drift apart); the file name decides otherwise.
_PROBE = globals().get('ENGINE_VARIANT') or re.match(
    r'assemble_(probe[0-9a-z]+)\.py$', os.path.basename(os.path.abspath(__file__))).group(1)
# round 3 (B02): the table of images is narrow184_lib.PROBES (name -> variant, default start, ids_survive);
# probe184a / probe184 are the two built 2026-10-12 and their output is unchanged.
assert _PROBE in L.PROBES, _PROBE
IS_A = L.PROBES[_PROBE]['a']
VKEY = L.PROBES[_PROBE]['vkey']

CAVE = 0x3E21D
# probe172's hook, unchanged since: 0x00e46 `bsr fn_189fb` (3-word bsr, operand bytes 01 7c b3 at
# area bytes 0x706bd/0x706bf/0x706c1) becomes `bsr CAVE`; asserted below against the bsr3 encoding.
HOOK = 0x00E46
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
AREA0 = 0x6EA30
CONST_BASE = 0x7400                     # data addr of code word 236514 (0x39BE2)

SPEAK = 0xDF7F                          # probe99's direct idiom `ld AL,#id ; bsr 0xDF7F`
FN189FB = 0x189FB                       # the call at 0x00e46: MessageSend(0xa5ce, 1, {1, event})
FN12E1A = 0x12E1A                       # Bose's SinkMap + SinkClaim(n) + zero-fill helper (stock)
FILEFIND = ca.STUB['FileFind']
FILESRC = ca.STUB['StreamFileSource']
SOURCEMAP = ca.STUB['SourceMap']
SOURCESIZE = ca.STUB['SourceSize']
SOURCEDROP = ca.STUB['SourceDrop']
SOURCECLOSE = ca.STUB['SourceClose']
OVERSINK = ca.STUB['StreamPartitionOverwriteSink']
SETDIGEST = ca.STUB['PartitionSetMessageDigest']
SINKCLOSE = ca.STUB['SinkClose']
SINKFLUSH = ca.STUB['SinkFlush']
MEMMOVE = ca.STUB['memmove']
GETINFO = ca.STUB['PartitionGetInfo']
MOUNT = ca.STUB['PartitionMountFilesystem']

# ---- the geometry (BYTES; narrow184_lib.py explains why a period is 28 bytes, not 14 words)
PERIOD = L.PERIOD_BYTES       # 64: one blind period of data_us = one SourceDrop
FIRST = L.FIRST_WORD          # 9 (NOT 11: payload-184.md section 0, RETURN-CHECKLIST 4.4): data_us words 9..22
MAPOFF = L.FIRST_BYTE         # 18 = 2 * FIRST: map element of the first payload byte of a period (one byte per word)
CHUNK = L.CHUNK               # 28: claim = memmove = flush
DEFAULT_SP = L.PROBES[_PROBE]['sp']   # 1270 = tail staging: the last start whose 60,368-byte span ends before the slack
START_PERIOD = DEFAULT_SP
if '--start-period' in sys.argv:
    START_PERIOD = int(sys.argv[sys.argv.index('--start-period') + 1])
_SUFFIX = '' if START_PERIOD == DEFAULT_SP else '_sp%d' % START_PERIOD
if _SUFFIX:
    print('NOTE: --start-period %d is a VARIANT run: every output file gets the infix %s'
          % (START_PERIOD, _SUFFIX))
NAME = L.NAME

# ---- the payload and its staging (pinned recipes; failures here stop the build)
ADPCM = L.adpcm(VKEY)
ROFS, _ROFS_LOG = L.rofs(ADPCM)
STG = L.stage(ROFS, START_PERIOD)
PERIODS = STG['periods']
print('payload %s: %d B (sha256 %s)' % (VKEY, len(ADPCM), L.sha(ADPCM)))
print('ROFS: %d B (sha256 %s), %d periods x %d B = %d B written to p2 (%d pad bytes)'
      % (len(ROFS), L.sha(ROFS), PERIODS, CHUNK, PERIODS * CHUNK, PERIODS * CHUNK - len(ROFS)))
print('staging: start period %d, data_us bytes %d..%d, %d edits (%d differ from stock)'
      % (START_PERIOD, STG['span'][0], STG['span'][1], len(STG['edits']), STG['changed']))
assert 0 < PERIODS < 0x7FFF and 0 < START_PERIOD < 0x7FFF
assert START_PERIOD + PERIODS <= L.SLACK_PERIODS, 'start + periods exceeds %d (fsedit compensation slack)' % L.SLACK_PERIODS
# the order of the code-region blocks (see p3): the one order of the 120 tried first that assembles both probes
REGION_ORDER = ['GATHER', 'ADVANCE', 'SKIPN', 'FINISH', 'VERDICT']

# ---- the spoken ids (docs: T08 section "id tables").  NINE outcome classes, nine ids.  Rules: (a) the id
# speaks (not one of the 7 empty stubs); (b) it survives the staging in tools/promptmap.py's model at
# START_PERIOD (all 57 do at the tail start; none at start period 1); (c) the stock says it only when the
# owner performs a pairing / toggle gesture (promptmap section 6: 0x12 0x14 0x15 0x35-0x38 and the two
# "second bose device" sentences 0x0b 0x3f), never with a laptop connected, the music paused and nothing
# touched; (d) it appears in no table of probes 139-143, 179-183, the 185 mocks or probe187 (whose guards
# take the never-spoken 0x39-0x3d and the battery ids).  The classes that call for the SAME next step
# share an id (a refused trap after the erase was requested: 0x14; closed but not VALID or unreadable:
# 0x15), because the ids are too few to give each its own.  The three "select a bose ..." sentences
# differ by one noun (speaker / headphones / product): they are the three stops BEFORE the erase.
ID_OK, ID_STATE2, ID_STATE3, ID_STATE4 = 0x12, 0x35, 0x0B, 0x3F
ID_WRITEFAIL, ID_NOTVALID = 0x14, 0x15
ID_MISMATCH, ID_NOWIN, ID_NOOPEN = 0x36, 0x37, 0x38
ID = dict(
    NOOPEN=ID_NOOPEN,        # "select the bose product ..."  FileFind / StreamFileSource refused (before the erase)
    NOWIN=ID_NOWIN,          # "select the bose headphones .." SourceSize < 64 / SourceMap 0 (before the erase)
    MISMATCH=ID_MISMATCH,    # "select a bose speaker .."     "fsr_" not at map elements 18..21 (before the erase)
    EOPEN=ID_WRITEFAIL,      # "auto off disabled"            the p2 sink would not open ...
    GATHER=ID_WRITEFAIL,     #                                ... or a trap refused during the gather ...
    DIGEST=ID_WRITEFAIL,     #                                ... or PartitionSetMessageDigest refused
    INCOMPLETE=ID_NOTVALID,  # "auto off enabled"             closed, but STATE != VALID ...
    GETINFO=ID_NOTVALID,     #                                ... or PartitionGetInfo refused
)
if IS_A:
    ID.update(F_ROOT=ID_OK,      # "voice prompts on"          VALID, file found FROM THE ROOT (p2 is in the union)
              F_MOUNT=ID_STATE2, # "ready to connect another device"  VALID, found only after the cave mounted p2
              MISSING=ID_STATE3, # "press the bluetooth and volume down ... second bose device"  VALID, mount ok, file missing
              NOMOUNT=ID_STATE4) # "... to enter stereo mode"   PartitionMountFilesystem returned FALSE
else:
    ID.update(VALID=ID_OK)       # "voice prompts on"          VALID: the ROFS is on p2
assert len(set(ID.values())) == (9 if IS_A else 6), 'outcome classes and ids disagree: %r' % ID
_EMPTY = {0x02, 0x03, 0x05, 0x07, 0x0F, 0x1A, 0x1D}
_STOCK_CTX = {0x00, 0x01, 0x04, 0x06, 0x08, 0x09, 0x0A, 0x0C, 0x0D, 0x0E, 0x16, 0x17, 0x18, 0x19,
              0x1B, 0x1C, 0x1E, 0x1F, 0x20}                           # connect / call / language
_OTHER_PROBES = ({0x10, 0x13, 0x1B, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x2A, 0x2B, 0x3E}   # 179-181, 185 mocks
                 | set(range(0x27, 0x35)) | set(range(0x39, 0x3E)))                           # 140-143, 182, 183, 187
assert not set(ID.values()) & (_EMPTY | _STOCK_CTX | _OTHER_PROBES), 'an id collides with the stock or another probe'
_surv, _hdr, _per = L.promptmap_survivors(len(ROFS), START_PERIOD)
_missing = [hex(i) for i in sorted(set(ID.values())) if i not in _surv]
print('promptmap (model): header words hit %d, %d of 57 speech ids survive the staged span; table ids not surviving: %s'
      % (_hdr, len(_surv), _missing or 'none'))
# V03 (round 3): the id model covers the 57 read sets and the region-B header ONLY. What else the span rewrites:
for _n, _h, _t in L.data_us_exposure(len(ROFS), START_PERIOD):
    print('   exposure (model): %-28s %6d of %6d words staged' % (_n, _h, _t))
_hdra = L.header_a_hits(len(ROFS), START_PERIOD)
if _hdra:
    print('   WARNING (V03): %d of the 30 region-A header words are staged; the TTS DSP copies that header at every '
          'speech-session init, so "the ids are audible" is a hypothesis for this image' % _hdra)
if _missing and not _SUFFIX and L.PROBES[_PROBE]['ids_survive']:
    raise SystemExit('an outcome id does not survive the staging in the model: %s' % _missing)

w = xapvm.load_words("firmware/bose/extracted/internal_fs/vm.app")
code = w[0x18:]

# ---- probe162: "NowSpeakTTS" from the firmware's const pool (no NUL needed: FileFind
# takes the length). Pick the first copy whose prefixed ld AH folds back.
def _pool_ah(text):
    p = [ord(c) for c in text]
    for i in range(236514, len(code) - len(p)):
        if list(code[i:i + len(p)]) != p: continue
        d = (CONST_BASE + (i - 236514)) & 0xFFFF
        lo8 = d & 0xFF; hi8 = ((d >> 8) + (1 if lo8 >= 0x80 else 0)) & 0xFF
        sx = lambda b: b - 256 if b >= 0x80 else b
        if 0x7400 <= d <= 0xD39A and 1 <= hi8 and (sx(hi8) * 256 + sx(lo8)) & 0xFFFF == d:
            return d, ((hi8 << 8), (lo8 << 8) | 0x10)
    raise AssertionError('no usable pool copy of %r' % text)

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
# ---- probe162: the CONFIRMED code region (probe161s, 2026-10-08; tools/caveguard.py
# CODE_REGION). Its writable runs, minus each function's stub, become extra bands AFTER
# the const window's, so code spills into them only when the window is full. Code only:
# strings and the TaskData must stay in the window (asserted after layout).
import caveguard
REGION_STUBS = {}
_REGION_BANDS = []
for _f, (_end, _sa, _sw) in sorted(caveguard.CODE_REGION.items()):
    for _k, _v in enumerate(_sw):
        REGION_STUBS[_sa + _k] = _v
    _a = _f
    while _a < _end:
        if caveguard.region_writable(_a) and _a not in REGION_STUBS:
            _b = _a
            while _b < _end and caveguard.region_writable(_b) and _b not in REGION_STUBS:
                _b += 1
            # probe164: never start a band inside an original instruction. If the word
            # before is a prefix (low byte 0), leave this word original so that
            # instruction stays whole and the linear decode is unambiguous.
            _s = _a
            while _s < _b and (code[_s - 1] & 0xFF) == 0 and (_s - 1) not in REGION_STUBS:
                _s += 1
            if _s < _b:
                _REGION_BANDS.append((_s, _b))
            _a = _b
        else:
            _a += 1
REGION_WORDS = {a for x, y in _REGION_BANDS for a in range(x, y)}
def in_run(cw): return any(a <= cw < b for a, b in _runs) or cw in REGION_WORDS

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
_BANDS += _REGION_BANDS
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

# CAVE is the hook target and holds the first instruction: there is no TaskData and no handler in
# this image (nothing is ever sent to the cave later), so the entry jump of probes 145-181 is not needed.
CODE_AT = CAVE
assert blind(CODE_AT) and in_run(CODE_AT)

DIR_DATA, _DIR_AH = _pool_ah("NowSpeakTTS")   # "NowSpeakTTS" from the firmware's own pool (FileFind takes the length)
DIRNAME, FILENAME = "NowSpeakTTS", "data_us"  # data_us is carried (the pool never holds it as one run)

prog = []
def W(*words): prog.append(("w", list(words)))
def BSR(t): prog.append(("bsr", t))
def BR(op, l): prog.append(("br", op, l))
def LBL(n): prog.append(("label", n))
def REGION(): prog.append(("region",))
def LDAL(v): W(*ca.imm_words(v, 0x14))
def LDAH(v): W(*ca.imm_words(v, 0x10))
def CMPAL(v): W(*ca.imm_words(v, 0x84))
def STAL(n): W((n << 8) | 0x27)             # st AL,@(n,Y)
def LDALS(n): W((n << 8) | 0x17)            # ld AL,@(n,Y)
def CMP0(): W(0x0084)                       # cmp AL,#0

# slots of TRIG's frame (enterl -8, slots 0..5 only, as probe141): 0 = the event, then FileFind
# length / digest args; 1 = source, 2 = sink, 3 = mapped pointer, 4 = counter, 5 = the id kept
# across SinkClose.
S_SRC, S_SINK, S_PTR, S_CNT = 1, 2, 3, 4

# ------------------------------------------------------------------ the TRIGGER (probe172, proven)
# entered from 0x00e46 in fn_00846 with AL = the event. 0x4004 = a CENTRE LONG PRESS: WRITE inline,
# one spoken id, event swallowed. Every other event: fn_189fb replayed with AL restored, the
# stock call. The window holds TRIG, the write sequence, the exits, PASS and the strings; SKIPN,
# GATHER (one period), ADVANCE, FINISH and VERDICT (and FIND) are code-region subroutines reached
# by bsr only (a cave may not branch into the region: that would need a 3-word bra, which Bose
# never emits).  The strings and every branch target stay in the proven window.
LBL("TRIG")
W(0xF80B)                       # enterl -8
STAL(0)                         # st AL,@(0,Y)  the event id
CMPAL(0x4004)
BR(0xF0, "PASS")                # bne -> not ours: replay

# ---- 1. FileFind(1, "NowSpeakTTS", 11), FileFind(dir, "data_us", 7)  (probes 177-181's two-level walk)
LDAL(len(DIRNAME)); STAL(0)     # arg3 = length
W(0x0114)                       # ld AL,#1  FILE_ROOT
W(*_DIR_AH)                     # ld AH,#<pool copy of "NowSpeakTTS">
BSR(FILEFIND)
CMP0(); BR(0xF4, "NOOPEN")
LDAH(len(FILENAME)); W(0x0023)  # ld AH,#7 ; st AH,@(0,Y)  arg3 (AL = the directory still)
LBL("SETAHFILE")
W(0x0000, 0x0010)               # ld AH,#<data addr of STRFILE> (patched below)
BSR(FILEFIND)
CMP0(); BR(0xF4, "NOOPEN")
BSR(FILESRC)                    # src = StreamFileSource(file)
STAL(S_SRC)
CMP0(); BR(0xF4, "NOOPEN")

# ---- 2. skip to the staged span (region subroutine SKIPN: START_PERIOD x ADVANCE = SourceSize >= 64,
# SourceDrop 64).  SKIPN and FINISH return 0 = fine, else the id to speak; a refusal is a spoken
# stop BEFORE the erase.
LDALS(S_SRC)
LDAH(START_PERIOD)
BSR("SKIPN")
CMP0(); BR(0xF0, "ENDSRC")

# ---- 3. look BEFORE the erase: the first staged period must show "fsr_" at map elements 18..21
# (one byte per word; the ROFS starts with the bytes 66 73 72 5f 64 66 75 31 = "fsr_dfu1").  Packed words, a different offset, or a stock data_us
# all stop here, with p2 untouched.
LDALS(S_SRC)
BSR(SOURCEMAP)
CMP0(); BR(0xF4, "NOWIN")
STAL(S_PTR)
W((S_PTR << 8) | 0x1B)          # ld X,@(3,Y)
for _k, _ch in enumerate("fsr_"):
    W(((MAPOFF + _k) << 8) | 0x16)      # ld AL,@(18+k,X)
    CMPAL(ord(_ch))
    BR(0xF0, "MISMATCH")

# ---- 4. *** THE ERASE *** open the overwrite sink on partition 2 (device 1, partition 2)
ca.call2(W, BSR, OVERSINK, al=('imm', 1), ah=('imm', 2))
STAL(S_SINK)
CMP0(); BR(0xF4, "EOPEN")

# ---- 5. the gather: PERIODS x GATHER(src, sink)
LDAL(PERIODS); STAL(S_CNT)
LBL("LOOP")
LDALS(S_SRC)
W((S_SINK << 8) | 0x13)         # ld AH,@(2,Y)
BSR("GATHER")
CMP0(); BR(0xF4, "GFAIL")
LDALS(S_CNT); W(0xFF34); STAL(S_CNT)    # counter -= 1
CMP0(); BR(0xF0, "LOOP")

# ---- 6. FINISH (region): close the source (Bose closes its own file sources, fn_1edf9 0x1ee26),
# digest SKIP, close the sink (the first word commits only at the close, partition.h:44-46)
LDALS(S_SRC)
W((S_SINK << 8) | 0x13)         # ld AH,@(2,Y)
BSR("FINISH")
CMP0(); BR(0xF0, "SAY")         # nonzero = the id (digest refused; the sink is closed already)

# ---- 7. the verdict (region subroutine): AL = the id
BSR("VERDICT")
BR(0xE0, "SAY")

# ---- failure exits. A gather failure closes the source and the sink (p2 stays INCOMPLETE, the
# fail-safe); the exits before the erase close the source only; NOOPEN has none.
LBL("GFAIL")
LDAL(ID['GATHER']); STAL(5)     # keep the id across the calls below
LDALS(S_SRC)
BSR(SOURCECLOSE)
ca.call1(W, BSR, SINKCLOSE, al=('slot', S_SINK))
LDALS(5)
BR(0xE0, "SAY")
LBL("NOWIN")
LDAL(ID['NOWIN'])
BR(0xE0, "ENDSRC")
LBL("MISMATCH")
LDAL(ID['MISMATCH'])
BR(0xE0, "ENDSRC")
LBL("EOPEN")
LDAL(ID['EOPEN'])
LBL("ENDSRC")
STAL(5)                         # keep the id across SourceClose
LDALS(S_SRC)
BSR(SOURCECLOSE)
LDALS(5)
BR(0xE0, "SAY")
LBL("NOOPEN")
LDAL(ID['NOOPEN'])
LBL("SAY")
BSR(SPEAK)                      # probe99's direct idiom, hardware-proven; port 3 is not ours here
W(0xF80F)                       # leavel -8: the centre long press is swallowed

LBL("PASS")
W(0x0017)                       # ld AL,@(0,Y)  the event back in AL
BSR(FN189FB)                    # the stock call, replayed (0x00e49 reloads AL after it)
W(0xF80F)                       # leavel -8

# ---- carried strings, each ONE item so the layout places it whole (asserted below); they follow
# a terminator and nothing falls into them
LBL("STRFILE")
W(*[ord(c) for c in FILENAME])
if IS_A:
    LBL("STRNAME")
    W(*[ord(c) for c in NAME])
W(0x00E2)                       # rts: a terminator so the region entry below is legal (never reached)

REGION()                        # everything below is reached only by bsr, from the window

# The code-region blocks. The layout engine needs a connector of 1-2 words at the end of every band,
# so the ORDER of the blocks decides whether a build is possible at all (a band that ends one word short
# of a 2-word connector is refused); REGION_ORDER is the order that assembles for this variant.
def _blk_SKIPN():
    # ================================================================== SKIPN (region)
    # AL = source, AH = n.  n x ADVANCE.  0 = done, else ID['NOWIN'] (the window offered < 64 bytes)
    LBL("SKIPN")
    W(0xFC0B)                       # enterl -4
    STAL(1); W(0x0223)              # slot 1 = source, slot 2 = n
    LBL("SKL")
    LDALS(1)
    BSR("ADVANCE")
    CMP0(); BR(0xF4, "SKF")
    LDALS(2); W(0xFF34); STAL(2)    # n -= 1
    CMP0(); BR(0xF0, "SKL")
    W(0x0014)                       # ld AL,#0
    W(0xFC0F)                       # leavel -4
    LBL("SKF")
    LDAL(ID['NOWIN'])
    W(0xFC0F)                       # leavel -4

def _blk_FINISH():
    # ================================================================== FINISH (region)
    # AL = source, AH = sink.  Close the source, digest SKIP, close the sink.  0 = done, else ID['DIGEST']
    # (the sink is closed either way)
    LBL("FINISH")
    W(0xFC0B)                       # enterl -4
    W(0x0323)                       # st AH,@(3,Y)  sink
    BSR(SOURCECLOSE)                # AL = the source still
    ca.calln(W, BSR, SETDIGEST, al=('slot', 3), ah=('imm', 3),
             stack=[('imm', 0), ('imm', 0)], stage='AL')
    STAL(2)                         # keep the digest result across SinkClose
    ca.call1(W, BSR, SINKCLOSE, al=('slot', 3))
    LDALS(2)
    CMP0(); BR(0xF4, "FINBAD")
    W(0x0014)                       # ld AL,#0
    W(0xFC0F)                       # leavel -4
    LBL("FINBAD")
    LDAL(ID['DIGEST'])
    W(0xFC0F)                       # leavel -4

def _blk_GATHER():
    # ================================================================== GATHER (region)
    # AL = source, AH = sink.  One period: map, claim 28, memmove 28 elements from map+18, flush 28, drop 64.
    # 1 = done, 0 = a trap refused (the caller closes the sink and speaks)
    LBL("GATHER")
    W(0xFC0B)                       # enterl -4
    STAL(1); W(0x0223)              # slot 1 = source, slot 2 = sink
    LDAL(CHUNK); STAL(0)            # slot 0 = memmove length (no later call here writes slot 0)
    LDALS(1)
    BSR(SOURCEMAP)
    CMP0(); BR(0xF4, "GFAILR")
    W((MAPOFF << 8) | 0x34)         # add AL,#18
    STAL(3)                         # slot 3 = source pointer
    ca.call2(W, BSR, FN12E1A, al=('slot', 2), ah=('imm', CHUNK))   # AL = claimed pointer, 0 on failure
    CMP0(); BR(0xF4, "GFAILR")
    W((3 << 8) | 0x13)              # ld AH,@(3,Y)  (AL = dst still)
    BSR(MEMMOVE)
    ca.call2(W, BSR, SINKFLUSH, al=('slot', 2), ah=('imm', CHUNK))
    CMP0(); BR(0xF4, "GFAILR")
    LDALS(1)
    BSR("ADVANCE")                  # AL = 1 / 0
    W(0xFC0F)                       # leavel -4
    LBL("GFAILR")
    W(0x0014)                       # ld AL,#0
    W(0xFC0F)                       # leavel -4

def _blk_ADVANCE():
    # ================================================================== ADVANCE (region)
    # AL = source.  1 = the window offered >= 64 bytes and 64 were dropped, 0 = it did not
    LBL("ADVANCE")
    W(0xFD0B)                       # enterl -3
    STAL(0)
    BSR(SOURCESIZE)
    W((PERIOD << 8) | 0x84)         # cmp AL,#64
    BR(0xF8, "ADVOK")               # bcc: unsigned >= 64
    W(0x0014)                       # ld AL,#0
    W(0xFD0F)                       # leavel -3
    LBL("ADVOK")
    LDALS(0)
    W((PERIOD << 8) | 0x10)         # ld AH,#64
    BSR(SOURCEDROP)
    W(0x0114)                       # ld AL,#1
    W(0xFD0F)                       # leavel -3

def _blk_VERDICT():
    # ================================================================== VERDICT (region)
    # GetInfo(SERIAL_FLASH, 2, STATE): 0 = VALID.  AL = the id to speak.
    LBL("VERDICT")
    W(0xFA0B)                       # enterl -6
    W(0x0314); STAL(0)              # slot 0 = key 3 (PARTITION_INFO_STATE)
    W(0xE415); W(0x0434); W(0x0127) # slot 1 = &slot4 (Y + 4): the uint32 lands in slots 4 (hi), 5 (lo)
    W(0x0114); W(0x0210)            # ld AL,#1 ; ld AH,#2
    BSR(GETINFO)
    CMP0(); BR(0xF4, "VGI")
    LDALS(5)
    CMP0(); BR(0xF0, "VINC")
    if IS_A:
        # visibility: FileFind(FILE_ROOT, "brown.adpcm", 11) from the root; else mount p2 (1, 2, 1) and look again
        BSR("FIND")
        CMP0(); BR(0xF0, "VFROOT")
        ca.call3(W, BSR, MOUNT, al=('imm', 1), ah=('imm', 2), arg3=('imm', 1))
        CMP0(); BR(0xF4, "VNOMOUNT")
        BSR("FIND")
        CMP0(); BR(0xF0, "VFMOUNT")
        LDAL(ID['MISSING'])
        BR(0xE0, "VOUT")
        LBL("VFROOT")
        LDAL(ID['F_ROOT'])
        BR(0xE0, "VOUT")
        LBL("VFMOUNT")
        LDAL(ID['F_MOUNT'])
        BR(0xE0, "VOUT")
        LBL("VNOMOUNT")
        LDAL(ID['NOMOUNT'])
        BR(0xE0, "VOUT")
    else:
        LDAL(ID['VALID'])
        BR(0xE0, "VOUT")
    LBL("VINC")
    LDAL(ID['INCOMPLETE'])
    BR(0xE0, "VOUT")
    LBL("VGI")
    LDAL(ID['GETINFO'])
    LBL("VOUT")
    W(0xFA0F)                       # leavel -6, AL carries the id out

    if IS_A:
        # ---- FIND: FileFind(FILE_ROOT, "brown.adpcm", 11) from the root; AL = FILE_INDEX or 0
        LBL("FIND")
        W(0xFE0B)                   # enterl -2
        LDAL(len(NAME)); STAL(0)
        W(0x0114)                   # ld AL,#1
        LBL("SETAHNAME")
        W(0x0000, 0x0010)           # ld AH,#<data addr of STRNAME> (patched below)
        BSR(FILEFIND)
        W(0xFE0F)                   # leavel -2

for _n in REGION_ORDER:
    globals()['_blk_' + _n]()

# ---- layout (proven machinery, verbatim from probe137/139/140) ----
bsr_size, br_size = {}, {}
label_addr = {}
changes = []
def needs_follow(item):
    k = item[0]
    if k == "region": return False
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
        if kind == "region":
            # no connector: nothing falls through into the region
            assert i > 0 and not needs_follow(prog[i - 1]), 'region entry must follow a terminator'
            addrs[i] = -1
            addr = _REGION_BANDS[0][0]; i += 1; continue
        if kind == "w": sz = len(prog[i][1])
        elif kind == "bsr": sz = bsr_size.get(i, 0)
        else: sz = br_size.get(i, 1)
        band_end = addr
        while blind(band_end) and in_run(band_end): band_end += 1
        try:
            nb_probe = next_blind(band_end)
            cs = (1 if -128 <= nb_probe - addr <= 127
                  else 2 if br2_encodable(nb_probe - (addr + 1)) else 3)
        except AssertionError:
            nb_probe, cs = None, 0
        need = sz + (cs if needs_follow(prog[i]) else 0)
        if addr + need > band_end:
            assert nb_probe is not None, (
                'cave exhausted: %d writable words is not enough (at %#x, item %d of %d; '
                '%d program words still unplaced, before connectors)'
                % (sum(y - x for x, y in _BANDS), addr, i, len(prog),
                   sum(len(prog[j][1]) if prog[j][0] == "w" else
                       bsr_size.get(j, 2) if prog[j][0] == "bsr" else br_size.get(j, 1)
                       for j in range(i, len(prog)) if prog[j][0] in ("w", "bsr", "br"))))
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
    if kind in ("label", "region"): continue
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
            raise SystemExit('REFUSED: a 3-word branch at %#x -> %s %#x -- Bose never emits it' % (a, item[2], tgt))
for cslot, (nb, cs) in extra.items():
    v = nb - cslot
    if cs == 1:
        assert -128 <= v <= 127, (hex(cslot), hex(nb), v)
        out[cslot] = ((v & 0xFF) << 8) | 0xE0
    elif cs == 3:
        raise SystemExit('REFUSED: a 3-word bra connector at %#x -- Bose never emits it' % cslot)
    elif False:
        assert cslot + 1 not in out and cslot + 2 not in out, hex(cslot)
        v = nb - (cslot + 2)
        done = False
        for aa in range(-128, 128):
            if aa == 0: continue
            for bb in range(-128, 128):
                if bb == 0: continue
                cc = v - aa*65536 - bb*256
                if -128 <= cc <= 127:
                    out[cslot] = (aa & 0xFF) << 8; out[cslot+1] = (bb & 0xFF) << 8
                    out[cslot+2] = ((cc & 0xFF) << 8) | 0xE0
                    done = True; break
            if done: break
        assert done, ('connector3', hex(cslot), hex(nb))
    else:
        assert cslot + 1 not in out, hex(cslot + 1)
        v = nb - (cslot + 1)             # probe165: a 2-word branch is relative to its
                                         #   SECOND word, as br2_encodable() sized it
        for aa in range(max(-128, (v >> 8) - 2), min(128, (v >> 8) + 3)):
            if aa == 0: continue
            bb = v - aa * 256
            if -128 <= bb <= 127:
                out[cslot] = (aa & 0xFF) << 8
                out[cslot + 1] = ((bb & 0xFF) << 8) | 0xE0
                break
        else:
            raise AssertionError(('connector', hex(cslot), hex(nb), v))


# ---- probe172: the redirect bytes must be the bsr3 from HOOK to CAVE (relative to the
# bsr's LAST word, as every 3-word bsr above is encoded)
_v = CAVE - (HOOK + 2)
_enc = None
for _aa in range(-128, 128):
    if _aa == 0: continue
    for _bb in range(-128, 128):
        if _bb == 0: continue
        _cc = _v - _aa * 65536 - _bb * 256
        if -128 <= _cc <= 127 and _cc != 0:
            _enc = (_aa & 0xFF, _bb & 0xFF, _cc & 0xFF); break
    if _enc: break
assert _enc, hex(_v)
_want = [("0x%x" % (AREA0 + 2 * (HOOK + k) + 1), "0x%02x" % _enc[k]) for k in range(3)]
assert REDIRECT_EDITS == _want, (REDIRECT_EDITS, _want)
print("hook: 0x%05x bsr -> CAVE 0x%05x, operand bytes %02x %02x %02x at %s"
      % (HOOK, CAVE, _enc[0], _enc[1], _enc[2], [a for a, _ in REDIRECT_EDITS]))
assert label_addr["TRIG"] == CAVE, hex(label_addr["TRIG"])

# probe162: the region's stubs ride along in EVERY image that uses the region, and the
# things the cave READS (strings) must be in the const window.
CONST_ORIGIN = 236514
def _str_ptr(label, text, setah, nul=True):
    base = label_addr[label]
    words = [ord(c) for c in text] + ([0] if nul else [])
    for k, expect in enumerate(words):
        got = out.get(base + k)
        assert got == expect, (
            'string %r is NOT contiguous: word %d at %#x is %r, expected %r -- '
            'the layout split it across blind bands'
            % (text, k, base + k, got, expect))
    assert caveguard.SAFE_WINDOW[0] <= base and base + len(words) <= caveguard.SAFE_WINDOW[1], (
        'string %r is outside the const window' % text)
    data = (CONST_BASE + (base - CONST_ORIGIN)) & 0xFFFF
    assert 0x7400 <= data <= 0xD39A, (text, hex(data))
    lo8 = data & 0xFF
    hi8 = ((data >> 8) + (1 if lo8 >= 0x80 else 0)) & 0xFF
    sx = lambda b: b - 256 if b >= 0x80 else b
    assert (sx(hi8) * 256 + sx(lo8)) & 0xFFFF == data, (
        'prefixed ld AH does not fold back for %r: hi=%02x lo=%02x -> %#06x, '
        'want %#06x' % (text, hi8, lo8, (sx(hi8)*256 + sx(lo8)) & 0xFFFF, data))
    assert 1 <= hi8 <= 0xFF, hex(data)
    a = label_addr[setah]
    out[a] = (hi8 << 8) | 0x00
    out[a + 1] = (lo8 << 8) | 0x10
    print('  %-12r %2d words, contiguous at code %#x -> data %#06x '
          '(ld AH %04x %04x)' % (text, len(words), base, data, out[a], out[a+1]))

print('FileFind strings:')
print('  %-12r from the firmware const pool at data %#06x (ld AH %04x %04x)'
      % (DIRNAME, DIR_DATA, _DIR_AH[0], _DIR_AH[1]))
_str_ptr('STRFILE', FILENAME, 'SETAHFILE', nul=False)
if IS_A:
    _str_ptr('STRNAME', NAME, 'SETAHNAME', nul=False)
# the stubs ride along ONLY when cave code is in the region
if any(caveguard.region_fn(_a) is not None for _a in out):
    for _a, _v in REGION_STUBS.items():
        assert _a not in out, hex(_a)
        out[_a] = _v
_nreg = sum(1 for a in out if caveguard.region_fn(a) is not None)
print('region: %d words used (%d of them stubs), const window: %d words, total %d'
      % (_nreg, len(REGION_STUBS) if _nreg else 0, len(out) - _nreg, len(out)))
lo, hi = min(out), max(out)
print(f"cave spans {lo:#x}..{hi:#x}, {len(out)} words (iters {iteration+1})")
assert not [a for a in out if not blind(a) or not (in_run(a) or a in REGION_STUBS)]
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
_forms = {}
for a, op, v, ln in xapvm.decode(patched, fold_zero=False):
    dstarts.add(a)
    if a in out and op in caveguard.BRANCH_OPS:
        _forms[(op, ln)] = _forms.get((op, ln), 0) + 1
    if lo <= a <= hi:
        if op == 0x9C: seen[a] = (a + ln - 1 + v) & 0x3FFFF

        elif op in (0x20, 0x24, 0x28, 0x2C, 0xE0, 0xE4, 0xE8, 0xEC,
                    0xF0, 0xF4, 0xF8, 0xFC): seen[a] = (a + ln - 1 + v) & 0x3FFFF
for a, (tgt, kind) in intended.items():
    assert seen.get(a) == (tgt & 0x3FFFF), (hex(a), kind, hex(tgt), seen.get(a))
for i, item in enumerate(prog):
    if item[0] not in ("label", "region"):
        assert addrs[i] in dstarts, (hex(addrs[i]), "boundary")
print("decode-verify: all branches OK, boundaries OK")
# caveguard.attest() walks every instruction between the lowest and highest cave word, which for a cave
# that also uses the code region is most of vm.app: its table then counts STOCK branches. This is the
# same census applied to the instructions that START at a cave word only.
_cen = caveguard.bose_census(code)
print('branch forms of the cave itself (instruction starts at cave words), against the Bose census:')
for (_op, _ln), _k in sorted(_forms.items()):
    print('   %-4s %d-word  x%-3d  Bose uses this form %5d time(s)%s'
          % (caveguard.BRANCH_OPS[_op], _ln, _k, _cen.get((_op, _ln), 0),
             '   <-- UNATTESTED' if _cen.get((_op, _ln), 0) == 0 else ''))
assert all(_cen.get(k, 0) > 0 for k in _forms), 'the cave emits a branch form Bose never does'

# ---- the frame budget: the deepest frame chain this cave adds under the hook (words)
print('frames: TRIG -8 -> GATHER -4 -> fn_12e1a -6 -> fn_39480 -4 -> fn_39468 + trap stub -3 is the deepest static chain '
      '(about 8+4+6+4+3 = 25 words, plus whatever fn_39468 adds); TRIG -> VERDICT -6 -> FIND -2 -> stub -3 = 19. No frame is larger '
      'than -8, so no new stack measurement is owed (rule 2 gate 1); tools/stackdepth.py 0xe46 puts the hook at 54 of 316 words')

# ---- outputs
_wp = f"build/hook/{_PROBE}{_SUFFIX}_words.json"
json.dump({hex(a): v for a, v in out.items()}, open(_wp, "w"), indent=0)
_cave_edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw] & 0xFFFF
    _cave_edits.append((hex(AREA0 + 2*cw), hex(v & 0xFF)))
    _cave_edits.append((hex(AREA0 + 2*cw + 1), hex(v >> 8)))
_dfu = f"build/hook/{_PROBE}{_SUFFIX}_brown.dfu"
# The staged payload is tens of thousands of area-byte edits in data_us (28 bytes of every 64): far more
# than one command line holds (Windows: 32,767 characters), so the image is built through
# fsedit.build() in-process, exactly as probe141 was. probeNNN_cmd.txt records the command that
# rebuilds it.
open(f"build/hook/{_PROBE}{_SUFFIX}_cmd.txt", "w").write(
    "python build/hook/assemble_%s.py%s --build\n"
    "# %d cave/redirect byte edits + %d staged data_us byte edits go through fsedit.build() in-process\n"
    "# (too many for one --edit command line); output %s\n"
    % (_PROBE, (' --start-period %d' % START_PERIOD) if _SUFFIX else '', len(_cave_edits),
       len(STG['edits']), _dfu))
print("wrote %s (%d words) and %s_cmd.txt" % (_wp, len(out), _PROBE + _SUFFIX))

if "--build" in sys.argv:
    sys.path.insert(0, "tools")
    _fsc = {'__file__': os.path.abspath('tools/fsedit.py')}
    try:
        exec(compile(open("tools/fsedit.py", encoding="utf-8").read(), "tools/fsedit.py", "exec"), _fsc)
    except SystemExit:
        pass
    _edits = [(int(o, 16), int(v, 16)) for o, v in REDIRECT_EDITS]
    for cw in sorted(out):
        v = out[cw] & 0xFFFF
        _edits.append((AREA0 + 2*cw, v & 0xFF))
        _edits.append((AREA0 + 2*cw + 1, (v >> 8) & 0xFF))
    _edits += STG['edits']
    assert len({o for o, _ in _edits}) == len(_edits), 'an area byte is edited twice (cave vs payload)'
    _fsc["build"](_edits, _dfu)
    # independent check of the BUILT image: replay the cave's gather over the data_us bytes in the
    # DFU itself (not over the in-memory edit list) and compare with the bytes the cave will write
    _d = open(_dfu, 'rb').read()
    _ia = _d.find(b'fsr_dfu1')
    _us = _d[_ia + STG['area0']:_ia + STG['area0'] + 219528]
    _got = bytearray()
    for _p in range(PERIODS):
        _b = PERIOD * (START_PERIOD + _p) + MAPOFF
        _got += _us[_b:_b + CHUNK]
    assert bytes(_got) == STG['padded'], 'DFU gather replay != the ROFS'
    print('built %s: gather replay over the DFU = the ROFS (%d bytes + %d pad), sha256 %s'
          % (_dfu, len(ROFS), len(STG['padded']) - len(ROFS), L.sha(_d)))
else:
    print("edit lists ready (%d cave/redirect byte edits, %d staged data_us byte edits); "
          "run with --build to assemble %s" % (len(_cave_edits), len(STG['edits']), _dfu))

# ROUND-3 NOTE (2026-10-12, curator; comments only - the words and DFU hashes are unchanged).
# The docstring above predates four round-3 results:
#  - R02: PartitionMountFilesystem refuses table type != 1 and p2 is type 3, so the 'file found' outcomes cannot occur as designed
#    (owner decision PD-20: retire the file route for the raw route). The premise 'a recorded 184a that found the file' cannot be met.
#  - V03: at start 1,270 this image rewrites 12 of the 30 region-A header words of data_us (the TTS DSP reads that header), plus 42 E6-array
#    words and 637 region-B-tail words; 'all 57 ids survive' is a hypothesis with a counter-indication. STATE VALID proves only the digest-SKIP
#    commit, not the content; no p2 readback exists. An 81 KB skip and a 138 KB gather have no stock precedent.
#  - B02: the 58k variant (start 1,320) spares those structures; the 90k variant garbles every id.
#  - the outcome ids 0x35, 0x12, 0x14, 0x15 were used with other meanings by older probes (none is pending).
# Register: docs/deep/round3-2026-10-12/README.md section 4 (R3-C011, R3-C100, R3-C101, R3-C102, R3-C104, R3-C105).
