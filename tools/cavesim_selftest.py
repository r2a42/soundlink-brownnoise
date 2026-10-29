#!/usr/bin/env python3
"""cavesim_selftest: exercise cavesim's world model end to end with MOCK caves.

The real probe179..186 are assembled by other agents; this builds two small stand-ins in the
shape DESIGN.md section 3 specifies, by reusing build/hook/assemble_probe178.py's proven layout
machinery (its program section is replaced, everything else is verbatim), and drives them
through `tools/cavesim.py --loop ... --expect ...`.  A MOCK is not a probe: nothing here is
flashed, nothing is written under build/hook/ (words go to a temp dir), and the mocks are not
claimed to be the final probes.  They prove that the simulator can express, and the rules can
judge, the mechanisms the design needs:

  mock179  BOUNDED poll loop: after TransformStart, MessageSendLater(task, 3, 0, 1000 ms);
           the handler re-arms while TransformFromSink is busy, rebuilds on a free port with
           id-1, speaks 0x26 at id 1, speaks 0x21 when the gate is FALSE (DSP gone).
  mock180  UNBOUNDED poll loop with a constant id 0x12 and a STOP: a centre long press first
           calls MessageCancelFirst(task, 0x12): TRUE = STOP (nothing else), FALSE = START.

J-T3 (2026-10-12) adds an EXTENSION battery after the original 23 cases (the original block still
prints its own "23 cases, 0 failed" line first):

  mockguard  mock180 plus the sinkState guard 02-loop-forever R1 proposes: the poll handler reads
             @0x59e inline (`ld AL,@0x59e`, the encoding probe131 used) and continues only for
             connected (3) or A2DP streaming (13); any other state returns silently without
             re-arming. Driven over the whole ADK sinkState enum (adk/root/apps/sink/sink_states.h).
             The REAL probe180/181 handlers never read @0x59e (T03 section 4), so the same
             `--mem 59e=` scenarios on probe181 behave identically for every value: the hole.
  synth      a main function that calls trap 0xD3 through a cave-carried inline-tail stub
             (T12), plus a stub-below-main layout, a stray tail, and caveguard.attest_trap_stubs
             on all of them. Built in memory and written to the temp dir.
  failure worlds on the real probe181 words: --cancel, --ksink-after-unload, --wrong-dsp,
             --mid-chunk-1072, --foreign-tone, --mem-at.

Round 3 (2026-10-12, T14) adds, still in the extension battery: a cave `bsr`/`bra` into the stock trap
tail (V01 D1, brick), stubs for unimplemented trap slots (V01 D2), near-copies of the tail and the
window-end / dispatcher-bound pairs (V01 D8), declaration parsing (V01 D7), the R05 consume lever (the
store into the caller's frame, with and without --caller-frame), the sinkState sweep 16..31 and the new
184-rehearsal world options (--src-unpacked, --size-dries-after).

    python tools/cavesim_selftest.py            # build both mocks, run the whole suite
    python tools/cavesim_selftest.py --keep DIR # also leave the word files in DIR

Exit 0 only when every expectation passes.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'build', 'hook', 'assemble_probe178.py')
BEGIN = '# ------------------------------------------------------------------ the TRIGGER'
END = '# ---- layout (proven machinery'

PROG = r'''
POLL_MS = 1000
BOUNDED = %(bounded)s
GUARD = %(guard)s                  # J-T3: the sinkState guard (only the 'guard' mock)
POLL_ID = 0x12                     # unbounded mock: the constant id
TONE_B = 2
LBL("TRIG")
W(0xF80B)                          # enterl -8
W(0x0027)                          # st AL,@(0,Y)  the event id
W(*ca.imm_words(0x4004, 0x84))     # cmp AL,#0x4004
BR(0xF0, "PASS")
BSR("ARM")
W(0xF80F)
LBL("PASS")
W(0x0017)
BSR(FN189FB)
W(0xF80F)

LBL("STRFILE")
W(*[ord(c) for c in FILENAME])

# ---------------------------------------------------------------- the poll handler
# entry: AL = task, AH = the MessageId.  AH is clobbered by every call, so the id is saved at
# once in slot 3 and reloaded (verify.md V7).
LBL("HANDLER")
W(0xF80B)                          # enterl -8
W(0x0323)                          # st AH,@(3,Y)   the id
if GUARD:
    W(*ca.imm_words(0x59E, 0x15))      # ld AL,@0x59e   sinkState, inline (probe131's encoding)
    W(*ca.imm_words(3, 0x84)); BR(0xF4, "GOK")      # cmp AL,#3  (connected) ; beq
    W(*ca.imm_words(13, 0x84)); BR(0xF0, "GOUT")    # cmp AL,#13 (A2DP streaming) ; bne -> out
    LBL("GOK")
ca.call1(W, BSR, KSINK, al=('imm', 3))
W(0x0227)                          # st AL,@(2,Y)   ksink
W(0x0084); BR(0xF4, "HNOSINK")
BSR(TFROMSINK)
W(0x0084); BR(0xF0, "HREARM")      # busy: wait another poll
if BOUNDED:
    W(0x0317)                      # ld AL,@(3,Y)
    W(0x0184); BR(0xF4, "HENDED")  # id 1: the count is spent
W(0x0217)                          # ld AL,@(2,Y)  ksink
BSR("BUILD")
W(0x0084); BR(0xF0, "HFAIL")
W(0x0313)                          # ld AH,@(3,Y)
if BOUNDED:
    W(0x0150)                      # sub AH,#1
BSR("ARMPOLL")
W(0xF80F)
LBL("HREARM")
W(0x0313)                          # ld AH,@(3,Y)
BSR("ARMPOLL")
W(0xF80F)
if GUARD:
    LBL("GOUT")
    W(0xF80F)                      # silent exit: no speech, no re-arm
LBL("HENDED")
W(0x2614)                          # ld AL,#0x26 "ended"
BSR(SPEAK)
W(0xF80F)
LBL("HNOSINK")
W(0x1014)                          # 0x10
BSR(SPEAK)
W(0xF80F)
LBL("HFAIL")
W(*ca.imm_words(0x3E, 0x84))       # cmp AL,#0x3E  (BUILD's "no DSP")
BR(0xF0, "HSAY")
W(0x2114)                          # ld AL,#0x21 "call ended": the DSP went away at a seam
LBL("HSAY")
BSR(SPEAK)
W(0xF80F)

# ---------------------------------------------------------------- ARM (the press)
LBL("ARM")
W(0xF80B)
if not BOUNDED:
    W(*ca.imm_words(POLL_ID, 0x10))     # ld AH,#0x12
    W(*ca.imm_words(TASK_ADDR, 0x14))   # ld AL,#task
    BSR(CANCELFIRST)
    W(0x0084); BR(0xF0, "STOPPED")      # TRUE: a poll was pending -> STOP, nothing else
ca.call1(W, BSR, KSINK, al=('imm', 3))
W(0x0227)
W(0x0084); BR(0xF4, "ANOSINK")
BSR(TFROMSINK)
W(0x0084); BR(0xF0, "STOPPED")          # busy: do nothing
W(0x0217)                               # ld AL,@(2,Y)
BSR("BUILD")
W(0x0084); BR(0xF0, "AFAIL")
if BOUNDED:
    W(0x0310)                           # ld AH,#3
else:
    W(*ca.imm_words(POLL_ID, 0x10))     # ld AH,#0x12
BSR("ARMPOLL")
LBL("STOPPED")
W(0xF80F)
LBL("ANOSINK")
W(0x1014)
BSR(SPEAK)
W(0xF80F)
LBL("AFAIL")
BSR(SPEAK)                              # AL = BUILD's id (0x3E on the start path)
W(0xF80F)

# ---------------------------------------------------------------- ARMPOLL(AH = id)
LBL("ARMPOLL")
W(0xF80B)
W(0x0014); W(0x0027)                    # message = 0       slot 0
W(0x0127)                               # delay high = 0    slot 1
W(*ca.imm_words(POLL_MS, 0x14))
W(0x0227)                               # delay low         slot 2
W(*ca.imm_words(TASK_ADDR, 0x14))       # ld AL,#task
BSR(MSGLATER)
W(0xF80F)

# ---------------------------------------------------------------- BUILD(AL = ksink) -> AL = 0 or a failure id
# The window holds the entry, string, TaskData, handler, ARM and ARMPOLL; BUILD and GATE spill
# into the dead-code region (reached only by bsr: a 3-word branch across is refused).
REGION()
LBL("BUILD")
W(0xF80B)
W(0x0227)                               # st AL,@(2,Y)  ksink
BSR("GATE")
W(0x0084); BR(0xF4, "BNODSP")
W(*ca.imm_words(len(DIRNAME), 0x14))
W(0x0027)
W(0x0114)                               # ld AL,#1  FILE_ROOT
W(*_DIR_AH)
BSR(FILEFIND)
W(0x0084); BR(0xF4, "BNODIR")
W(*ca.imm_words(len(FILENAME), 0x10))
W(0x0023)
LBL("SETAHFILE")
W(0x0000, 0x0010)
BSR(FILEFIND)
W(0x0084); BR(0xF4, "BNOFILE")
BSR(FILESRC)
W(0x0084); BR(0xF4, "BNOSRC")
W(0x0213)                               # ld AH,@(2,Y)
BSR(ADPCM)
W(0x0084); BR(0xF4, "BNOPLAY")
BSR(TSTART)
W(0x0084); BR(0xF4, "BNOPLAY")
W(0x0014)                               # ld AL,#0  success
W(0xF80F)
LBL("BNODIR")
W(0x2214); W(0xF80F)
LBL("BNOFILE")
W(0x1B14); W(0xF80F)
LBL("BNOSRC")
W(0x2414); W(0xF80F)
LBL("BNOPLAY")
W(0x2514); W(0xF80F)
LBL("BNODSP")
W(0x3E14); W(0xF80F)

LBL("GATE")
W(*ca.imm_words(RATE, 0x10))
W(*ca.imm_words(0x1072, 0x14))
LBL("KSEND")
W(0xF80B)
W(0x0327)
W(*ca.imm_words(TONE_B, 0x14))
W(0x0027)
W(0x0014)
W(0x0127); W(0x0227)
W(0x0317)
BSR(KALMSG)
W(0xF80F)

'''


# mock182: the READ-ONLY file-source window census (DESIGN.md probe182). id = 0x27 + head_ok
# + 2 * (the window advanced after SourceDrop(n)); 0x23 = a trap refused.  The map is read with
# memmove into the frame (the idiom probe141 uses for pointers); words are little-endian
# unless --src-endian be.
PROG_CENSUS = r'''
DIR_DATA, _DIR_AH = _pool_ah("NowSpeakTTS")
DIRNAME, FILENAME = "NowSpeakTTS", "data_us"
TFROMSINK = ca.STUB["TransformFromSink"]
SRCSIZE, SRCDROP = ca.STUB["SourceSize"], ca.STUB["SourceDrop"]
SRCMAP, SRCCLOSE = ca.STUB["SourceMap"], ca.STUB["SourceClose"]
LBL("TRIG")
W(0xF80B)
W(0x0027)
W(*ca.imm_words(0x4004, 0x84))
BR(0xF0, "PASS")
BSR("ARM")
W(0xF80F)
LBL("PASS")
W(0x0017)
BSR(FN189FB)
W(0xF80F)
LBL("STRFILE")
W(*[ord(c) for c in FILENAME])
LBL("HANDLER")
W(0xF80B)
W(0xF80F)
LBL("ARM")
W(0xF80B)
W(*ca.imm_words(len(DIRNAME), 0x14)); W(0x0027)
W(0x0114)
W(*_DIR_AH)
BSR(FILEFIND)
W(0x0084); BR(0xF4, "FAIL")
W(*ca.imm_words(len(FILENAME), 0x10)); W(0x0023)
LBL("SETAHFILE")
W(0x0000, 0x0010)
BSR(FILEFIND)
W(0x0084); BR(0xF4, "FAIL")
BSR(FILESRC)
W(0x0084); BR(0xF4, "FAIL")
W(0x0127)                       # st AL,@(1,Y)  src
BSR(SRCSIZE)
W(0x0227)                       # st AL,@(2,Y)  n
W(0x0117)
BSR(SRCMAP)
W(0x0084); BR(0xF4, "FAIL")
W(0x0327)                       # st AL,@(3,Y)  map
W(0x0314); W(0x0027)            # @(0,Y) = 3 words
W(0x0313)                       # ld AH,@(3,Y)  src = map
W(0xE415); W(0x0334)            # ld AL,@0xffe4 ; add AL,#3  dst = Y+3 (slots 3..5)
BSR(MEMMOVE)
W(0x0317); W(*ca.imm_words(2, 0x84)); BR(0xF0, "BADHEAD")
W(0x0417); W(0x0084); BR(0xF0, "BADHEAD")
W(0x0517); W(*ca.imm_words(9, 0x84)); BR(0xF0, "BADHEAD")
W(0x2814); W(0x0027)            # id 0x28: head matches
BR(0xE0, "DROP")
LBL("BADHEAD")
W(0x2714); W(0x0027)            # id 0x27: head mismatch
LBL("DROP")
W(0x0117); W(0x0213)            # AL = src, AH = n
BSR(SRCDROP)
W(0x0117)
BSR(SRCSIZE)
W(0x0084); BR(0xF4, "CLOSE")
W(0x0017); W(0x0234); W(0x0027) # id += 2: the window advanced
LBL("CLOSE")
W(0x0117)
BSR(SRCCLOSE)
W(0x0017)
BSR(SPEAK)
W(0xF80F)
LBL("FAIL")
W(0x2314)
BSR(SPEAK)
W(0xF80F)
'''


# mock185b: FileFind(1, "brown.adpcm", 11) from the root; on FILE_NONE mount p2 (1, 2, LOWER)
# and look again.  0x2A found from the root, 0x2B found after the mount, 0x13 still missing.
PROG_P2FIND = r'''
DIRNAME, FILENAME = "", "brown.adpcm"
TFROMSINK = ca.STUB["TransformFromSink"]
MOUNT = ca.STUB["PartitionMountFilesystem"]
LBL("TRIG")
W(0xF80B)
W(0x0027)
W(*ca.imm_words(0x4004, 0x84))
BR(0xF0, "PASS")
BSR("ARM")
W(0xF80F)
LBL("PASS")
W(0x0017)
BSR(FN189FB)
W(0xF80F)
LBL("STRFILE")
W(*[ord(c) for c in FILENAME])
LBL("HANDLER")
W(0xF80B)
W(0xF80F)
LBL("ARM")
W(0xF80B)
BSR("FIND")
W(0x0084); BR(0xF0, "FOUND1")
ca.call3(W, BSR, MOUNT, al=('imm', 1), ah=('imm', 2), arg3=('imm', 1))
W(0x0084); BR(0xF4, "NONE")
BSR("FIND")
W(0x0084); BR(0xF0, "FOUND2")
LBL("NONE")
W(0x1314)
BSR(SPEAK)
W(0xF80F)
LBL("FOUND1")
W(0x2A14)
BSR(SPEAK)
W(0xF80F)
LBL("FOUND2")
W(0x2B14)
BSR(SPEAK)
W(0xF80F)
LBL("FIND")
W(0xF80B)
W(*ca.imm_words(len(FILENAME), 0x14)); W(0x0027)
W(0x0114)
LBL("SETAHFILE")
W(0x0000, 0x0010)
BSR(FILEFIND)
W(0xF80F)
'''


def build(mode, outpath):
    src = open(SRC, encoding='utf-8').read()
    a, b = src.index(BEGIN), src.index(END)
    prog = (PROG_CENSUS if mode == 'census' else PROG_P2FIND if mode == 'p2find' else
            PROG % {'bounded': 'True' if mode == 'bounded' else 'False',
                    'guard': 'True' if mode == 'guard' else 'False'})
    prog = prog.replace('CANCELFIRST', "ca.STUB['MessageCancelFirst']")
    src = src[:a] + 'TFROMSINK = ca.STUB["TransformFromSink"]\n' + prog + '\n' + src[b:]
    old = 'open(f"build/hook/{_PROBE}_words.json", "w")'
    assert old in src
    src = src.replace(old, 'open(%r, "w")' % outpath)
    old = 'open(f"build/hook/{_PROBE}_cmd.txt", "w").write(" ".join(cmd) + "\\n")'
    assert old in src
    src = src.replace(old, 'pass')
    ns = {'__file__': os.path.join(ROOT, 'build', 'hook', 'assemble_probe999.py'),
          '__name__': 'mock_assembler'}
    old_argv, old_cwd, old_out = sys.argv, os.getcwd(), sys.stdout
    try:
        os.chdir(ROOT)
        sys.argv = ['assemble_probe999.py']
        sys.stdout = open(os.devnull, 'w')
        exec(compile(src, 'mock_%s' % mode, 'exec'), ns)
    finally:
        sys.stdout.close() if sys.stdout is not old_out else None
        sys.stdout, sys.argv = old_out, old_argv
        os.chdir(old_cwd)
    return len(ns['out'])


CASES = [
    # (name, mock, cavesim args, expectations)
    ('179 bounded, music playing: 3 chunks, 0x26, nothing pending, no rule broken',
     'bounded', ['--loop', '3', '--settle-ms', '5000'],
     ['chunks=3', 'ended=3', 'spoken=26', 'violations=0', 'pending=0', 'looping=no']),
    ('179 bounded, --loop 2 cap: chunk 3 starts after the cap (the loop does not stop itself early)',
     'bounded', ['--loop', '2', '--settle-ms', '5000'],
     ['chunks=3', 'looping=yes', 'violations=0']),
    ('179 press B, music PAUSED, unload 100 ms after the tone end: 0x21 at the first seam',
     'bounded', ['--loop', '3', '--music', 'paused', '--unload-ms', '100', '--settle-ms', '5000'],
     ['chunks=1', 'spoken=21', 'dsp=unloaded', 'violations=0', 'pending=0']),
    ('179 paused, unload 5000 ms (the slow-unload reading): the poll beats it, 3 chunks, 0x26',
     'bounded', ['--loop', '3', '--music', 'paused', '--unload-ms', '60000', '--settle-ms', '5000'],
     ['chunks=3', 'spoken=26', 'violations=0']),
    ('179 latch: chunk 1 at the stock rate, chunks 2-3 at 2000 Hz (summary shows it)',
     'bounded', ['--loop', '3', '--settle-ms', '5000'], ['chunks=3']),
    ('179 V2 hazard, 400 ms tail: the port reads free 400 ms before the audible end but no poll '
     'lands in that window (phase-dependent) -> clean',
     'bounded', ['--loop', '3', '--tail-ms', '400', '--settle-ms', '5000'],
     ['chunks=3', 'violations=0']),
    ('179 V2 hazard, 900 ms tail: the 2 s poll lands inside it -> R1, R4 (rebuild while audible), R3 (0x26 spoken over the tail)',
     'bounded', ['--loop', '3', '--tail-ms', '900', '--settle-ms', '5000'],
     ['rules=R1,R3,R4']),   # R3: the final 0x26 is also spoken while chunk 3 is still audible
    ('179 forced-free read (TransformFromSink returns 0 on a live chunk, --fail): R1 + R4, and R3 for the 0x26',
     'bounded', ['--loop', '3', '--fail', 'TransformFromSink', '--settle-ms', '5000'],
     ['rules=R1,R3,R4']),
    ('179 DSP unloaded before the press: START speaks 0x3E, nothing armed',
     'bounded', ['--loop', '3', '--dsp', 'down'], ['chunks=0', 'spoken=3e', 'pending=0']),
    ('179 Bluetooth long press at 1500 ms: chunk cut, DSP gone, the pending poll speaks 0x21',
     'bounded', ['--loop', '3', '--bt-teardown-at', '1500', '--settle-ms', '8000'],
     ['spoken=21', 'violations=0']),
    ('180 unbounded: START, STOP at 4500 ms (chunk 2 is playing: chunk 1 is only 2.6 s) cancels the poll; chunk 2 plays out; silence',
     'unbounded', ['--press', '0:4004', '--press', '4500:4004', '--horizon', '60000'],
     ['chunks=2', 'ended=2', 'spoken=', 'pending=0', 'violations=0']),
    ('180 unbounded: START, STOP, 15 s, START again: the cancel left a clean queue',
     'unbounded', ['--press', '0:4004', '--press', '4500:4004', '--press', '30000:4004',
                   '--press', '40000:4004', '--horizon', '70000'],
     ['chunks=3', 'ended=3', 'pending=0', 'violations=0']),
    ('180 unbounded with --loop 3: a chunk 4 starts, so looping=yes (no end of its own)',
     'unbounded', ['--loop', '3'], ['looping=yes', 'violations=0']),
    ('180 a press on an event other than 0x4004 is replayed to the stock, nothing armed',
     'unbounded', ['--press', '0:400d', '--once'],
     ['replayed=1', 'swallowed=0', 'chunks=0']),
    ('182 census, whole-file window (uint16 cap): head matches, window advances -> 0x2a',
     'census', ['--once'], ['spoken=2a', 'violations=0', 'chunks=0']),
    ('182 census, 4 KB window: same id (the gather geometry is window-agnostic)',
     'census', ['--once', '--src-window', '4096'], ['spoken=2a']),
    ('182 census, a 100-byte file: the drop empties the window -> 0x28 (no advance)',
     'census', ['--once', '--fs-add', 'NowSpeakTTS/data_us=100'], ['spoken=28']),
    ('182 census, big-endian packing: the head check fails -> 0x29',
     'census', ['--once', '--src-endian', 'be'], ['spoken=29']),
    ('182 census with FileFind refused (--fail): 0x23, no port, no write',
     'census', ['--once', '--fail', 'FileFind'], ['spoken=23', 'chunks=0']),
    ('185 p2find, nothing written to p2: the name is missing after the mount too -> 0x13',
     'p2find', ['--once', '--fs-add', 'brown.adpcm=30000:p2'], ['spoken=13']),
    ('185 p2find, p2 written, firmware does NOT automount: root miss, cave mount, found -> 0x2b',
     'p2find', ['--once', '--p2-preloaded', '--fs-add', 'brown.adpcm=30000:p2'], ['spoken=2b']),
    ('185 p2find, p2 written and automounted: found from the root -> 0x2a (185a)',
     'p2find', ['--once', '--p2-preloaded', '--p2-automount', '--fs-add', 'brown.adpcm=30000:p2'],
     ['spoken=2a']),
    ('185 p2find, mount refused (RAW_SERIAL reading): still missing -> 0x13',
     'p2find', ['--once', '--p2-preloaded', '--fail', 'PartitionMountFilesystem',
                '--fs-add', 'brown.adpcm=30000:p2'], ['spoken=13']),
]


# ----------------------------------------------------------------------------------------------
# J-T3 extension battery. Kept apart from CASES so the original block (and its "23 cases" line)
# is unchanged.
# ----------------------------------------------------------------------------------------------

def sink_states():
    """The ADK sinkState enum (sink_states.h:38-40 region) -> [(value, name)]."""
    import re
    path = os.path.join(ROOT, 'adk', 'root', 'apps', 'sink', 'sink_states.h')
    src = open(path, encoding='utf-8', errors='replace').read()
    body = src[src.index('typedef enum'):src.index('sinkState;')]
    body = re.sub(r'/\*.*?\*/', '', body, flags=re.S)
    names = re.findall(r'\b(device\w+|SINK_NUM_STATES)\b', body)
    return [(i, n) for i, n in enumerate(names) if n != 'SINK_NUM_STATES']


def _far3(op, a, target):
    """The shortest relative bsr (op 0x9C) or bra (0xE0) at address `a` reaching `target`
    (target = a + ln - 1 + v; 1, 2 or 3 words; the name is from the first user, the 3-word form)."""
    v = target - a
    if -128 <= v <= 127:
        return [((v & 0xFF) << 8) | op]
    v = target - (a + 1)
    for aa in range(-128, 128):
        cc = v - aa * 256
        if aa and -128 <= cc <= 127:
            return [(aa & 0xFF) << 8, ((cc & 0xFF) << 8) | op]
    v = target - (a + 2)
    for aa in range(-128, 128):
        for bb in range(-128, 128):
            cc = v - aa * 65536 - bb * 256
            if aa and bb and -128 <= cc <= 127:
                return [(aa & 0xFF) << 8, (bb & 0xFF) << 8, ((cc & 0xFF) << 8) | op]
    raise ValueError('cannot encode a branch %#x -> %#x' % (a, target))


NEAR = {'near_cell': (4, 0xFB19),     # ld X,@0xFFFB instead of @0xFFFC (a different firmware cell)
        'near_bra': (7, 0xFCE1),      # bra @0xFFFC instead of @0xFFFD
        'near_store': (5, 0xFE2B)}    # st X,@(-2,Y) instead of @(-1,Y)


def build_synth(outpath, trap=0xD3, mode='ok'):
    """The T12 mock: main = `enterl -8 ; ld AH,#2 ; ld AL,#1 ; bsr stub ; st AL,@(2,Y) ;
    leavel -8` at 0x3E21D and a cave-carried stub for `trap` (generated by
    caveguard.synth_stub_words, never hand-written). Modes: ok (stub above main at 0x3E240),
    below (stub at 0x3E21D, main at 0x3E240), stray (the five tail words only, no stub)."""
    import json
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import caveguard
    w = {}
    if mode == 'ok':
        main = [0xF80B, 0x0210, 0x0114, 0x209C, 0x0227, 0xF80F]
        for i, v in enumerate(main):
            w[0x3E21D + i] = v
        for i, v in enumerate(caveguard.synth_stub_words(trap)):
            w[0x3E240 + i] = v
    elif mode == 'below':
        for i, v in enumerate(caveguard.synth_stub_words(trap)):
            w[0x3E21D + i] = v
        m0 = 0x3E240
        rel = 0x3E21D - (m0 + 3)
        main = [0xF80B, 0x0210, 0x0114, ((rel & 0xFF) << 8) | 0x9C, 0x0227, 0xF80F]
        for i, v in enumerate(main):
            w[m0 + i] = v
    elif mode == 'farbra':             # the form T12 rejects: a 3-word `bra` to 0x291
        main = [0xF80B, 0x0210, 0x0114, 0x209C, 0x0227, 0xF80F]
        for i, v in enumerate(main):
            w[0x3E21D + i] = v
        import caveasm
        head = [caveguard.ENTERL_3] + caveasm.imm_words(trap, 0x18)
        a_bra = 0x3E240 + len(head)
        v = caveguard.COMMON_TAIL_A - (a_bra + 2)          # target = a + ln - 1 + v, ln = 3
        for aa in range(-128, 128):
            for bb in range(-128, 128):
                cc = v - aa * 65536 - bb * 256
                if aa and bb and -128 <= cc <= 127:
                    head += [(aa & 0xFF) << 8, (bb & 0xFF) << 8, ((cc & 0xFF) << 8) | 0xE0]
                    break
            else:
                continue
            break
        for i, x in enumerate(head):
            w[0x3E240 + i] = x
    elif mode == 'stray':
        main = [0xF80B, 0x0210, 0x0114, 0x209C, 0x0227, 0xF80F]
        for i, v in enumerate(main):
            w[0x3E21D + i] = v
        for i, v in enumerate(caveguard.COMMON_TAIL):
            w[0x3E240 + i] = v
    elif mode in ('bsrtail', 'bratail'):
        # V01 D1 (brick): a cave `bsr` / `bra` straight into the stock trap tail. 0x291 is the first tail
        # word (st X,@(0,Y)); 0x293 the third. bsr puts the link in X; the tail stores X as the trap id.
        op, tgt = (0x9C, 0x291) if mode == 'bsrtail' else (0xE0, 0x293)
        main = [0xF80B, 0x0210, 0x0114] + _far3(op, 0x3E220, tgt)
        main += [0x0227, 0xF80F] if mode == 'bsrtail' else []
        for i, v in enumerate(main):
            w[0x3E21D + i] = v
    elif mode in NEAR:
        # V01 D8: a near-copy of the tail (one word changed): neither a canonical stub nor the five tail
        # words. The main function is the 'ok' one, the stub sits at 0x3E240.
        main = [0xF80B, 0x0210, 0x0114, 0x209C, 0x0227, 0xF80F]
        for i, v in enumerate(main):
            w[0x3E21D + i] = v
        stub = caveguard.synth_stub_words(trap)
        idx, val = NEAR[mode]
        stub[idx] = val
        for i, v in enumerate(stub):
            w[0x3E240 + i] = v
    elif mode in ('winend', 'winover'):
        # V01 D8: the window-end pair. A canonical 8-word stub ending exactly at 0x3E400 passes; one
        # word further fails ('outside the proven window').
        at = 0x3E3F8 if mode == 'winend' else 0x3E3F9
        main = [0xF80B, 0x0210, 0x0114] + _far3(0x9C, 0x3E220, at) + [0x0227, 0xF80F]
        for i, v in enumerate(main):
            w[0x3E21D + i] = v
        for i, v in enumerate(caveguard.synth_stub_words(trap)):
            w[at + i] = v
    json.dump({'%X' % k: v for k, v in sorted(w.items())}, open(outpath, 'w'))
    return len(w)


def build_gain(outpath, group=0, master=0xFC18, tone=0xF73E):
    """Variant-B mock (T06): a cave that builds a gain block with the stock fn_1f47a:
    fn_1f47a(group AL, master AH, tone @(0,Y), &blk @(1,Y)) with blk = 0x2100, then returns
    blk[2] (the tone, copied verbatim) in AL. A 3-word bsr (the stock function is far)."""
    import json
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import caveasm as ca
    words = [0xF80B]
    words += ca.imm_words(tone, 0x14) + [0x0027]
    words += ca.imm_words(0x2100, 0x14) + [0x0127]
    words += ca.imm_words(master, 0x10)
    words += ca.imm_words(group, 0x14)
    a = 0x3E21D + len(words)
    v = 0x1F47A - (a + 2)                      # target = a + ln - 1 + v for the 3-word bsr
    for aa in range(-128, 128):
        for bb in range(-128, 128):
            cc = v - aa * 65536 - bb * 256
            if aa and bb and -128 <= cc <= 127:
                words += [(aa & 0xFF) << 8, (bb & 0xFF) << 8, ((cc & 0xFF) << 8) | 0x9C]
                break
        else:
            continue
        break
    words += ca.imm_words(0x2102, 0x15) + [0xF80F]
    json.dump({'%X' % (0x3E21D + i): w for i, w in enumerate(words)}, open(outpath, 'w'))
    return len(words)


def build_consume(outpath, slots=(21, 22)):
    """R05 E18 (the 6-word consume lever, T04 2I): in the hook, for a 0x4004 event store 0 into the
    caller's indicate-flag slot and set bit 15 of the caller's flag word:
        ld AL,#0 ; st AL,@(a,Y) ; ld AL,@(b,Y) ; or AL,#0x8000 ; st AL,@(b,Y)
    in a cave `enterl -8` frame. fn_00846 is `enterl -23`: its locals (13,Y), (14,Y) are cave slots
    21 and 22 (R05 E17); slots 29 and 30 would be ITS saved return address (the variant 'bad')."""
    import json
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import caveasm as ca
    a, b = slots
    cons = [0x0014, (a << 8) | 0x27, (b << 8) | 0x17] + ca.imm_words(0x8000, 0xB4) + [(b << 8) | 0x27]
    words = [0xF80B, 0x0027] + ca.imm_words(0x4004, 0x84) + [((len(cons) + 1) << 8) | 0xF0] + cons + [0xF80F]
    json.dump({'%X' % (0x3E21D + i): x for i, x in enumerate(words)}, open(outpath, 'w'))
    return len(words), len(cons)


def build_staged(outpath):
    """Round 3: a cave that reads two 28-byte periods of the staged map the way the 184 gather does,
    memmove(dst, SRCMAP + 18, 28) then memmove(dst + 28, SRCMAP + 64 + 18, 28), so `--staged FILE`
    (one byte per element, FIRST = 9) can be checked byte for byte with --show 2800:56."""
    import json
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import caveasm as ca
    mm = ca.STUB['memmove']
    words = [0xF80B]
    for dst, src in ((0x2800, 0x4000 + 18), (0x281C, 0x4000 + 64 + 18)):
        words += [0x1C14, 0x0027] + ca.imm_words(src, 0x10) + ca.imm_words(dst, 0x14)
        words += _far3(0x9C, 0x3E21D + len(words), mm)
    words += [0xF80F]
    json.dump({'%X' % (0x3E21D + i): x for i, x in enumerate(words)}, open(outpath, 'w'))
    return len(words)


# (title, words, entry, cavesim args, expectations, must-contain substrings, must-not-contain[, rc])
S181 = ['--press', '0:4004', '--brief']
EXT = [
    ('--cancel never on probe181, second press at 2800 (in the gap): a SECOND chain forks '
     '(02 section 5: 56 R6 in 30 s, 2 pending)',
     'probe181', '0x3E21D', S181 + ['--press', '2800:4004', '--horizon', '30000', '--cancel', 'never'],
     ['rules=R6', 'violations=56', 'pending=2'], ['MessageCancelFirst(0xba3c, 0x12) -> FALSE (--cancel never'], []),
    ('--cancel never, second press at 1500 (inside a chunk): harmless, one chain, nothing forks',
     'probe181', '0x3E21D', S181 + ['--press', '1500:4004', '--horizon', '30000', '--cancel', 'never'],
     ['violations=0', 'pending=1'], [], []),
    ('--cancel always: the very first press reads "a poll is pending" -> STOP, no chunk is ever built',
     'probe181', '0x3E21D', S181 + ['--press', '2800:4004', '--cancel', 'always'],
     ['chunks=0', 'pending=0', 'spoken=', 'violations=0'], ['--cancel always: nothing removed'], []),
    ('baseline for the next case: music PAUSED, DSP unloads 100 ms after the tone end: 0x21',
     'probe181', '0x3E21D', S181 + ['--music', 'paused', '--unload-ms', '100', '--horizon', '20000'],
     ['spoken=21', 'dsp=unloaded', 'pending=0'], [], []),
    ('--ksink-after-unload zero: the same press ends on the no-sink id 0x10, not 0x21',
     'probe181', '0x3E21D', S181 + ['--music', 'paused', '--unload-ms', '100', '--horizon', '20000',
                                    '--ksink-after-unload', 'zero'],
     ['spoken=10', 'dsp=unloaded', 'pending=0'], [], []),
    ('--wrong-dsp 4000:3000 on probe181: the gate reads TRUE, the cave rebuilds into the wrong DSP -> W1',
     'probe181', '0x3E21D', S181 + ['--wrong-dsp', '4000:3000', '--horizon', '14000'],
     ['rules=W1', 'cut=1', 'spoken='], ['WRONG DSP resident for 3000 ms',
                                      'sbc_decoder reloaded by the stock'], []),
    ('--mid-chunk-1072 4000 (b=0) on probe181: purge cut + quiet->loud hazard, and R1 stays SILENT (not a cave call)',
     'probe181', '0x3E21D', S181 + ['--mid-chunk-1072', '4000:0', '--horizon', '9000'],
     ['hazards=1', 'violations=0'], ['HEARING HAZARD: chunk 2', 'purged by the stock 0x1072'], []),
    ('--mid-chunk-1072 4000:2 (the stock keeps b=2): purge cut but no level hazard',
     'probe181', '0x3E21D', S181 + ['--mid-chunk-1072', '4000:2', '--horizon', '9000'],
     ['hazards=0', 'violations=0'], ['purged by the stock 0x1072'], ['HEARING HAZARD']),
    ('--foreign-tone 4000:2000: our chain is disposed, the poll reads the foreign handle and rebuilds after',
     'probe181', '0x3E21D', S181 + ['--foreign-tone', '4000:2000', '--horizon', '9000'],
     ['cut=1', 'violations=0', 'spoken='], ['STOCK TONE (fn_1c17f) disposes our chain'], []),
    ('THE HOLE: probe181 under --mem 59e=6 (active call SCO) still loops (its handler never reads 59e)',
     'probe181', '0x3E21D', ['--press', '0:4004', '--brief', '--loop', '3', '--mem', '59e=6'],
     ['looping=yes', 'violations=0'], [], []),
    ('THE HOLE: probe181 under --mem 59e=0 (limbo) loops the same',
     'probe181', '0x3E21D', ['--press', '0:4004', '--brief', '--loop', '3', '--mem', '59e=0'],
     ['looping=yes', 'violations=0'], [], []),
    ('E5 on the REAL probe181: a call state at 3500 ms plus a wrong DSP: it rebuilds into it (W1) and speaks nothing',
     'probe181', '0x3E21D', S181 + ['--mem', '59e=d', '--mem-at', '3500:59e=6', '--wrong-dsp', '3500:3000',
                                    '--horizon', '14000'],
     ['rules=W1'], ['RAM @0x059e := 0x0006'], []),
    ('--voice-field: START (field 0 -> 1, an enable request), then a centre SHORT press 4045 at 5000 is '
     'converted to 0x4004 by the stock: the cave sees it, STOPs, the stock sends a disable',
     'probe181', '0x3E21D', S181 + ['--press', '5000:4045', '--voice-field', '--horizon', '20000'],
     ['converted=1', 'field=0', 'pending=0', 'swallowed=2', 'replayed=0'],
     ['voice-recognition enable request', 'voice-recognition disable request'], []),
    ('same presses WITHOUT --voice-field: the short press is replayed to the stock (play/pause) and the '
     'poll keeps running',
     'probe181', '0x3E21D', S181 + ['--press', '5000:4045', '--horizon', '20000'],
     ['converted=0', 'replayed=1', 'pending=1'], [], ['voice-recognition']),
    ('--voice-field with an HFP message clearing the field at 2000 (T04 M4): the short press is NOT converted',
     'probe181', '0x3E21D', S181 + ['--press', '5000:4045', '--voice-field', '--field-at', '2000:0',
                                    '--horizon', '20000'],
     ['converted=0', 'replayed=1', 'pending=1', 'field=0'], ['CLEARS the voice-recognition field'], []),
    ('--voice-field parity: three long presses 0, 20 s, 40 s toggle the field 1,0,1 (odd = enabled)',
     'probe181', '0x3E21D', ['--press', '0:4004', '--press', '20000:4004', '--press', '40000:4004',
                             '--brief', '--voice-field', '--horizon', '60000'],
     ['field=1', 'converted=0'], ['enable@0, disable@20000, enable@40000'], []),
]


def guard_cases():
    cases = []
    for v, name in sink_states():
        passes = v in (3, 13)
        cases.append(('guard mock, sinkState %d (%s): %s' % (
            v, name, 'the loop runs' if passes else 'silent exit at the first poll, nothing pending'),
            'guard', '0x3E21D',
            ['--press', '0:4004', '--brief', '--loop', '3', '--mem', '59e=%x' % v],
            ['looping=yes', 'violations=0'] if passes
            else ['chunks=1', 'looping=no', 'pending=0', 'spoken=', 'violations=0'], [], []))
    # V04 / R05 E33: the real unit's states go beyond the 16 ADK values (Bose adds 15 Aux, 16 FactoryReset,
    # 17 LanguageSelect, 18 ManualConnect, 20 Reman, 21 ShipMode, 22 USB; the setter drops >= 0x18). The
    # {3,13} guard must exit silently for ALL of them.
    for v in range(16, 32):
        cases.append(('guard mock, sinkState %d (beyond the ADK enum; F194 / R05 E1): silent exit at '
                      'the first poll, nothing pending' % v,
                      'guard', '0x3E21D',
                      ['--press', '0:4004', '--brief', '--loop', '3', '--mem', '59e=%x' % v],
                      ['chunks=1', 'looping=no', 'pending=0', 'spoken=', 'violations=0'], [], []))
    cases.append(('guard mock + E5: streaming (13), then a call (6) and a wrong DSP at 3500 ms: the guard '
                  'exits at the next poll, no W1, nothing spoken, nothing pending',
                  'guard', '0x3E21D',
                  ['--press', '0:4004', '--brief', '--mem', '59e=d', '--mem-at', '3500:59e=6',
                   '--wrong-dsp', '3500:3000', '--horizon', '14000'],
                  ['violations=0', 'spoken=', 'pending=0', 'cut=1'], [], []))
    return cases


def gain_cases():
    return [
        ('Variant B mock: fn_1f47a without the audio_output config preset stops like the firmware '
         '(Panic when @0x6d0 == 0)',
         'gain', '0x3E21D', [], [], ['STOPPED: fn_1f47a would Panic (T06 E15)'], [], 1),
        ('Variant B mock with --mem 6d0=3100: the stock call is recorded and blk[2] = the tone verbatim',
         'gain', '0x3E21D', ['--mem', '6d0=3100'], [],
         ['(back-call 0x1F47A)', 'AL = 0xf73e'], ['STOPPED']),
        ('Variant B mock with group 2 (out of range): stops, as the firmware Panics',
         'gain_g2', '0x3E21D', ['--mem', '6d0=3100'], [], ['STOPPED: fn_1f47a would Panic (T06 E15)'],
         [], 1),
    ]


def synth_cases():
    return [
        ('T12 synth: a main calling trap 0xD3 through a cave-carried inline-tail stub (stub above main): '
         'the stub is named, the trap is recorded, AL = the modelled source',
         'synth_ok', '0x3E21D', [],
         [], ['SYNTHESISED TRAP STUB at 0x3E240: trap 0xD3 PartitionGetRawSerialSource, inline tail, 8 words',
              'PartitionGetRawSerialSource AL=0x0001 AH=0x0002', 'ended: leavel at 0x3E222   AL = 0x62c0'],
         ['HAZARD', 'WARNING']),
        ('T12 synth with --fail PartitionGetRawSerialSource: AL = 0 and no "no modelled return" warning',
         'synth_ok', '0x3E21D', ['--fail', 'PartitionGetRawSerialSource'],
         [], ['AL = 0x0000'], ['HAZARD', 'WARNING']),
        ('T12 synth, stub BELOW main: no frame HAZARD (the stub words are not judged)',
         'synth_below', '0x3E240', [],
         [], ['SYNTHESISED TRAP STUB at 0x3E21D', 'AL = 0x62c0'], ['HAZARD']),
        ('T12 synth through the world: the press line names the trap, port-3 rules OK',
         'synth_ok', '0x3E21D', ['--world', '--once', '--brief'],
         ['violations=0'], ['PartitionGetRawSerialSource'], []),
        ('T12 far-bra stub (3-word bra to 0x291, the form Bose never emits): the model still recognises it '
     '(bra tail) rather than mis-running it',
     'synth_farbra', '0x3E21D', [], [],
     ['SYNTHESISED TRAP STUB at 0x3E240: trap 0xD3 PartitionGetRawSerialSource, bra tail, 6 words',
      'AL = 0x62c0'], []),
    ('T12 synth of trap 0x100 (StreamPipePair): the model prints the dispatcher-bound HAZARD',
         'synth_h100', '0x3E21D', [], [],
         ['HAZARD  trap 0x100 is above the stack dispatcher bound 0xE2'], []),
    ('T12 stray tail (five words, no stub): HAZARD printed and the run STOPS at the 0x0E (round 3: it used '
         'to be mis-run as a pseudo-TRAP and accepted)',
         'synth_stray', '0x3E21D', [],
         [], ['HAZARD  opcode 0x0E (ld XH,@(n,Y)) at 0x3E243 outside a recognised trap stub',
              'STOPPED: trap tail word 0x0e (ld XH,@(n,Y)) executed at 0x3e243'], [], 1),
        ('V01 D1 (brick): a cave `bsr` straight into the stock trap tail 0x291: HAZARD, and the run STOPS '
         '(it used to run as the pseudo-trap trap_e245 with no warning)',
         'synth_bsrtail', '0x3E21D', [],
         [], ['HAZARD  bsr at 0x3E220 targets the stock trap tail 0x291',
              'STOPPED: trap tail word 0x0e (ld XH,@(n,Y)) executed at 0x294'], [], 1),
        ('V01 D1: a cave `bra` into the middle of the tail (0x293): HAZARD, and the run STOPS',
         'synth_bratail', '0x3E21D', [],
         [], ['HAZARD  bra at 0x3E220 targets the stock trap tail 0x293', 'STOPPED: trap tail word 0x0e'],
         [], 1),
        ('V01 D2: a synthesised stub for the UNIMPLEMENTED slot 0xDA: HAZARD printed (the model still returns)',
         'synth_unimpl', '0x3E21D', [],
         [], ['SYNTHESISED TRAP STUB at 0x3E240: trap 0xDA', 'HAZARD  trap 0xDA is an UNIMPLEMENTED slot'], []),
    ]


def consume_cases():
    """R05 E18 / E33: the consume lever through the model, and --caller-frame."""
    FR = ['--frame', '13=1', '--frame', '14=0', '--show', '90D:2']
    return [
        ('R05 consume lever, event 0x4004: the caller indicate flag := 0 and bit 15 of its flag word set '
         '(@0x90D..0x90E = 0000 8000)', 'consume', '0x3E21D', FR, [],
         ['data @0x090D..+2: 0000 8000'], ['HAZARD', 'STOPPED']),
        ('R05 consume lever, a centre SHORT event 0x4045: the two slots stay 0001 0000',
         'consume', '0x3E21D', FR + ['--al', '4045'], [], ['data @0x090D..+2: 0001 0000'], ['STOPPED']),
        ('R05 consume lever with --caller-frame 23 (fn_00846): slots 21/22 are caller slots 13/14, a NOTE and '
         'no stop', 'consume', '0x3E21D', FR + ['--caller-frame', '23'], [],
         ['caller-frame guard', 'NOTE cave slot 21 writes caller slot 13', 'data @0x090D..+2: 0000 8000'],
         ['HAZARD', 'STOPPED']),
        ('R05 skeptic: the same lever at slots 29/30 is fn_00846\'s saved return address: HAZARD and the run '
         'STOPS (without --caller-frame nothing notices)', 'consume_bad', '0x3E21D',
         FR + ['--caller-frame', '23'], [],
         ['HAZARD  cave slot 29 is caller slot 21', 'STOPPED: store to 0x0915 = the CALLER'], [], 1),
        ('R05 skeptic: slots 29/30 without --caller-frame run to the end (the hole the option closes)',
         'consume_bad', '0x3E21D', FR, [], ['ended: leavel'], ['HAZARD', 'STOPPED']),
    ]


def census_cases():
    """T08 follow-up 1: the 184-rehearsal world options on the read-only census mock."""
    return [
        ('--size-dries-after 1: the second SourceSize answers 0 (a window that dries up) -> no advance, 0x28',
         'census', '0x3E21D', ['--once', '--size-dries-after', '1', '--expect', 'spoken=28'],
         [], ['forced: --size-dries-after 1'], []),
        ('--src-unpacked: SourceMap maps one byte per element, so the 3-word packed head check fails (and the '
         'window still advances) -> 0x29, as for the big-endian packing',
         'census', '0x3E21D', ['--once', '--src-unpacked', '--expect', 'spoken=29'], [], [], []),
    ]


def run_ext(tmp):
    """Run the extension battery; returns the number of failures."""
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import caveguard
    words = {}
    for mode in ('guard', 'census'):
        words[mode] = os.path.join(tmp, 'mock_%s_words.json' % mode)
        n = build(mode, words[mode])
        print('built mock %-9s %3d words -> %s' % (mode, n, words[mode]))
    for key, slots in (('consume', (21, 22)), ('consume_bad', (29, 30))):
        words[key] = os.path.join(tmp, 'mock_%s_words.json' % key)
        n, _c = build_consume(words[key], slots)
        print('built mock %-9s %3d words -> %s' % (key, n, words[key]))
    words['gain'] = os.path.join(tmp, 'mock_gain_words.json')
    build_gain(words['gain'])
    words['gain_g2'] = os.path.join(tmp, 'mock_gain_g2_words.json')
    build_gain(words['gain_g2'], group=2)
    for key, mode, trap in (('synth_ok', 'ok', 0xD3), ('synth_below', 'below', 0xD3),
                            ('synth_stray', 'stray', 0xD3), ('synth_farbra', 'farbra', 0xD3),
                            ('synth_h100', 'ok', 0x100),
                            ('synth_c4a', 'ok', 0x4A),
                            ('synth_bsrtail', 'bsrtail', 0xD3), ('synth_bratail', 'bratail', 0xD3),
                            ('synth_near_cell', 'near_cell', 0xD3), ('synth_near_bra', 'near_bra', 0xD3),
                            ('synth_near_store', 'near_store', 0xD3),
                            ('synth_winend', 'winend', 0xD3), ('synth_winover', 'winover', 0xD3),
                            ('synth_unimpl', 'ok', 0xDA), ('synth_e2', 'ok', 0xE2),
                            ('synth_e3', 'ok', 0xE3)):
        words[key] = os.path.join(tmp, 'mock_%s_words.json' % key)
        n = build_synth(words[key], trap, mode)
    bad = total = 0
    for case in EXT + guard_cases() + gain_cases() + synth_cases() + consume_cases() + census_cases():
        title, wk, entry, args, expect, must, mustnot = case[:7]
        want_rc = case[7] if len(case) > 7 else 0
        total += 1
        probe = words.get(wk, wk)
        cmd = [sys.executable, os.path.join(ROOT, 'tools', 'cavesim.py'), probe, '--entry', entry]
        if not wk.startswith(('synth', 'gain')):
            cmd += ['--al', '4004']
        cmd += args
        for e in expect:
            cmd += ['--expect', e]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=600)
        out = r.stdout + r.stderr
        miss = [m for m in must if m not in out]
        extra = [m for m in mustnot if m in out]
        ok = r.returncode == want_rc and not miss and not extra
        print('%s  %s' % ('PASS' if ok else 'FAIL', title))
        if not ok:
            bad += 1
            print('    ' + ' '.join(cmd[2:]))
            for m in miss:
                print('    missing text: %r' % m)
            for m in extra:
                print('    unexpected text: %r' % m)
            for line in out.splitlines():
                if line.startswith(('expect', 'STOPPED', 'Traceback', '  File')) or 'Error' in line \
                        or line.startswith('port-3 rules'):
                    print('    ' + line)
    # caveguard.attest_trap_stubs on the synth mocks (in-process, words_path in the temp dir)
    gates = [
        ('caveguard: the 0xD3 stub declared in SYNTH_TRAPS passes', 'synth_ok', [0xD3], [], True),
        ('caveguard: the same stub NOT declared fails ("not declared")', 'synth_ok', [], [], False),
        ('caveguard: the stub listed as a SYNTH_CONTROL (Bose has no stub for 0xD3) fails', 'synth_ok',
         [], [0xD3], False),
        ('caveguard: a declared trap with no stub in the cave fails', 'synth_ok', [0xD3, 0x20], [], False),
        ('caveguard: a far-bra stub fails ("only the inline tail is allowed")', 'synth_farbra',
         [0xD3], [], False),
        ('caveguard: a stub for 0x100 (above the dispatcher bound 0xE2) fails', 'synth_h100',
         [0x100], [], False),
        ('caveguard: a stub for 0x4A (Bose has one) fails as a SYNTH_TRAP', 'synth_c4a', [0x4A], [], False),
        ('caveguard: a stub for 0x4A passes as a SYNTH_CONTROL', 'synth_c4a', [], [0x4A], True),
        ('caveguard: five tail words with no stub fail (stray tail, stray 0x0E/0xE1)', 'synth_stray',
         [], [], False),
        # ---- round 3 (V01 D1, D2, D8)
        ('V01 D1 (brick): a cave `bsr` into the stock trap tail 0x291 FAILS (it passed before)',
         'synth_bsrtail', [], [], False),
        ('V01 D1: a cave `bra` into the tail (0x293) FAILS', 'synth_bratail', [], [], False),
        ('V01 D2: a declared stub for the UNIMPLEMENTED slot 0xDA FAILS', 'synth_unimpl', [0xDA], [], False),
        ('V01 D2: ... and as a SYNTH_CONTROL it fails too (no stock stub, unimplemented)', 'synth_unimpl',
         [], [0xDA], False),
        ('V01 D8: a near-copy of the tail, cell 0xFFFB instead of 0xFFFC, FAILS', 'synth_near_cell',
         [0xD3], [], False),
        ('V01 D8: a near-copy, `bra @0xFFFC`, FAILS', 'synth_near_bra', [0xD3], [], False),
        ('V01 D8: a near-copy, `st X,@(-2,Y)`, FAILS', 'synth_near_store', [0xD3], [], False),
        ('V01 D8: a canonical stub ending exactly at 0x3E400 passes', 'synth_winend', [0xD3], [], True),
        ('V01 D8: the same stub one word further (ends at 0x3E401) FAILS ("outside the proven window")',
         'synth_winover', [0xD3], [], False),
        ('V01 D8: a stub for 0xE2 (the dispatcher bound, Bose has a stock stub) passes as a SYNTH_CONTROL',
         'synth_e2', [], [0xE2], True),
        ('V01 D8: a stub for 0xE3 (one above the bound) FAILS', 'synth_e3', [0xE3], [], False),
    ]
    for title, wk, decl, ctl, want in gates:
        total += 1
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            got = caveguard.attest_trap_stubs('probeX', declared=decl, controls=ctl,
                                              words_path=words[wk])
        ok = (got == want)
        print('%s  %s' % ('PASS' if ok else 'FAIL', title))
        if not ok:
            bad += 1
            print(buf.getvalue())
    # V01 D7: synth_declared parses the assembler with ast (was: regex + digit scraping)
    import tempfile as _tf
    probe_dir = os.path.join(ROOT, 'build', 'hook')
    for title, text, name, want in (
            ('V01 D7: a "]" inside a comment no longer truncates the list',
             'SYNTH_TRAPS = [0xD3,  # note: ] bracket in a comment\n               0x3F]\n', 'SYNTH_TRAPS',
             [0xD3, 0x3F]),
            ('V01 D7: a tuple is read (it was dropped)', 'SYNTH_CONTROLS = (0x3F,)\n', 'SYNTH_CONTROLS', [0x3F]),
            ('V01 D7: a commented-out assignment and a missing name read as empty',
             '# SYNTH_TRAPS = [0x11]\nX = 1\n', 'SYNTH_TRAPS', []),
            ('V01 D7: an expression that is not a literal is refused, not guessed',
             'SYNTH_TRAPS = [0xD3] + OTHER\n', 'SYNTH_TRAPS', ValueError)):
        total += 1
        with _tf.TemporaryDirectory() as td:
            fn = os.path.join(td, 'assemble_mock.py')
            open(fn, 'w').write(text)
            try:
                got = caveguard.synth_declared('mock', name, path=fn)
            except ValueError as e:
                got = ValueError
        ok = (got == want)
        print('%s  %s' % ('PASS' if ok else 'FAIL', title))
        if not ok:
            bad += 1
            print('    got %r want %r' % (got, want))
    # round 3: `--staged FILE` is ONE BYTE PER ELEMENT with FIRST = 9 (28 of every 64 elements, from
    # element 18); `--staged-legacy` keeps the 14-words-per-32 / +11 layout for probe141
    total += 1
    sp = os.path.join(tmp, 'mock_staged_words.json')
    build_staged(sp)
    payload = bytes((i * 7 + 3) & 0xFF for i in range(56))
    pp = os.path.join(tmp, 'payload.bin')
    open(pp, 'wb').write(payload)
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'cavesim.py'), sp, '--entry', '0x3E21D',
                        '--staged', pp, '--show', '2800:56'], capture_output=True, text=True, cwd=ROOT,
                       timeout=600)
    want = 'data @0x2800..+56: ' + ' '.join('%04x' % b for b in payload)
    ok = r.returncode == 0 and want in r.stdout and 'staged 56 bytes behind SourceMap' in r.stdout
    print('%s  --staged (round 3): two 28-byte periods read at map elements 18..45 and 82..109 come back '
          'byte for byte' % ('PASS' if ok else 'FAIL'))
    if not ok:
        bad += 1
        print(r.stdout[-600:])
    total += 1
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'cavesim.py'), 'probe141', '--staged',
                        os.path.join(ROOT, 'build', 'payload', 'staged_words.json'), '--staged-legacy'],
                       capture_output=True, text=True, cwd=ROOT, timeout=600)
    ok = r.returncode == 0 and 'staged 16520 words behind SourceMap (0x4000, periodic layout)' in r.stdout
    print('%s  --staged-legacy: the 2026-10 word layout still loads for probe141' % ('PASS' if ok else 'FAIL'))
    if not ok:
        bad += 1
        print(r.stdout[-600:])
    # --p2-capture sees a direct-store payload (probe140's 16-byte pattern) as well as memmoved ones
    total += 1
    cap = os.path.join(tmp, 'cap140.bin')
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'cavesim.py'), 'probe140', '--entry',
                        '0x3E21D', '--world', '--once', '--p2-capture', cap], capture_output=True,
                       text=True, cwd=ROOT, timeout=600)
    got = open(cap, 'rb').read() if os.path.exists(cap) else b''
    ok = (r.returncode == 0 and len(got) == 16 and got[:4] == b'frfu'
          and 'p2 capture: 1 flushes, 16 bytes' in r.stdout)
    print('%s  --p2-capture: probe140\'s 16 pattern bytes ("frfu...") are captured at the flush'
          % ('PASS' if ok else 'FAIL'))
    if not ok:
        bad += 1
        print(r.stdout[-600:])
    print('%d extension cases, %d failed' % (total, bad))
    return bad


def xapemu_mul_cases():
    """tools/xapemu.py multiply (2026-10-19): 0x90 #imm, 0x91 @abs, 0x92 @(n,X), 0x93 @(n,Y), all
    signed 16x16 -> AH:AL. Before this, 0x90 was skipped as a 'byte-extend quirk' and 0x92 stopped
    the emulator. The stock sites the quirk was invented for (vm.app 0xf593/0xf5b1, `mul #3`) are
    a real x3 and are checked against the real vm.app."""
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import xapemu

    def mk(code):
        w = [0] * 24
        w[4] = 24
        w[6] = len(code)
        return xapemu.VM(w + code)

    def poke(vm, wa, val):
        vm.ram[2 * wa:2 * wa + 2] = (val & 0xFFFF).to_bytes(2, 'little')

    bad = 0
    total = 0

    def check(title, got, want):
        nonlocal bad, total
        total += 1
        ok = got == want
        print('%s  xapemu mul: %s' % ('PASS' if ok else 'FAIL', title))
        if not ok:
            bad += 1
            print('    got %s want %s' % (got, want))

    vm = mk([0x0514, 0x0390, 0x00E2])                 # ld AL,#5 ; mul #3 ; rts
    vm.run(0)
    check('mul #3 (5*3)', (vm.AH, vm.AL), (0, 15))
    vm = mk([0xFE14, 0x0390, 0x00E2])                 # AL = -2
    vm.run(0)
    check('mul #3 signed (-2*3 = 0xFFFFFFFA)', (vm.AH, vm.AL), (0xFFFF, 0xFFFA))
    vm = mk([0x0514, 0x0191, 0x00E2])                 # mul @0x01
    poke(vm, 1, 7)
    vm.run(0)
    check('mul @abs (5*7), 0x91 unchanged', (vm.AH, vm.AL), (0, 35))
    vm = mk([0x0514, 0x0192, 0x00E2])                 # mul @(1,X)
    vm.X = 0x100
    poke(vm, 0x101, 7)
    vm.run(0)
    check('mul @(1,X) (5*7), was "unmodelled opcode 0x92"', (vm.AH, vm.AL), (0, 35))
    vm = mk([0x0514, 0x0293, 0x00E2])                 # mul @(2,Y)
    vm.Y = 0x200
    poke(vm, 0x202, -3)
    vm.run(0)
    check('mul @(2,Y) signed (5*-3 = 0xFFFFFFF1)', (vm.AH, vm.AL), (0xFFFF, 0xFFF1))
    vm = mk([0x0514, 0x0009, 0x0192, 0x00E2])         # clc form: unsigned
    vm.X = 0x100
    poke(vm, 0x101, 0xFFFF)
    vm.unsigned_form = False
    vm.run(0)
    check('mul @(1,X) after 0x0009 stays defined (no stop)', vm.AH is not None, True)
    fw = os.path.join(ROOT, 'firmware', 'bose', 'extracted', 'internal_fs', 'vm.app')
    if os.path.exists(fw):
        for site in (0xF592, 0xF5B0):                 # ld AL,@(-1,Y) ; mul #3 ; ld X,@0xffe1
            vm = xapemu.VM(xapemu.load_vm_app(fw))
            vm.Y = 0x800
            poke(vm, 0x7FF, 7)
            vm.run(site, max_steps=3)
            check('vm.app %#x: mul #3 gives X = 21 (table offset x3)' % site,
                  (vm.AL, vm.X), (21, 21))
    print('%d xapemu mul cases, %d failed' % (total, bad))
    return bad


def xapemu_div_cases():
    """tools/xapemu.py divide (2026-10-19): 0x94 #imm, 0x95 @abs, 0x96 @(n,X), 0x97 @(n,Y); AH:AL
    divided by the operand, quotient in AL, remainder in AH; signed (truncating toward zero,
    remainder takes the numerator's sign) or, after 0x0009, unsigned. Real call sites: fn_22a98
    (div @(6,X), curve numbers of S section 3.1) and fn_0dece, fn_22a89, fn_1f3e9 (div #imm)."""
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import xapemu

    def mk(code):
        w = [0] * 24
        w[4] = 24
        w[6] = len(code)
        return xapemu.VM(w + code)

    def poke(vm, wa, val):
        vm.ram[2 * wa:2 * wa + 2] = (val & 0xFFFF).to_bytes(2, 'little')

    bad = 0
    total = 0

    def check(title, got, want):
        nonlocal bad, total
        total += 1
        ok = got == want
        print('%s  xapemu div: %s' % ('PASS' if ok else 'FAIL', title))
        if not ok:
            bad += 1
            print('    got %s want %s' % (got, want))

    # unsigned (0x0009 first): AH:AL = 100, / 7 -> q 14 (AL), r 2 (AH)
    vm = mk([0x0010, 0x6414, 0x0009, 0x0794, 0x00E2])
    vm.run(0)
    check('udiv #7 (100 / 7 = 14 r 2)', (vm.AH, vm.AL), (2, 14))
    # registers set directly: 32-bit numerators
    vm = mk([0x0009, 0x1094, 0x00E2])
    vm.AH, vm.AL = 1, 0x2345
    vm.run(0)
    check('udiv #16 (0x12345 / 16 = 0x1234 r 5)', (vm.AH, vm.AL), (5, 0x1234))
    vm = mk([0x0794, 0x00E2])
    vm.AH, vm.AL = 0xFFFF, 0xFF9C                       # -100
    vm.run(0)
    check('sdiv #7 (-100 / 7 = -14 r -2, truncating)', (vm.AH, vm.AL), (0xFFFE, 0xFFF2))
    vm = mk([0x0794, 0x00E2])
    vm.AH, vm.AL = 0, 100
    vm.run(0)
    check('sdiv #7 (100 / 7 = 14 r 2)', (vm.AH, vm.AL), (2, 14))
    vm = mk([0x6414, 0x0010, 0x0009, 0x0195, 0x00E2])   # ld AL,#100 ; ld AH,#0 ; udiv @1
    poke(vm, 1, 7)
    vm.run(0)
    check('udiv @abs 0x95 (100 / 7)', (vm.AH, vm.AL), (2, 14))
    vm = mk([0x6414, 0x0010, 0x0009, 0x0296, 0x00E2])   # udiv @(2,X)
    vm.X = 0x100
    poke(vm, 0x102, 9)
    vm.run(0)
    check('udiv @(2,X) 0x96 (100 / 9 = 11 r 1), was "unmodelled opcode 0x96"', (vm.AH, vm.AL), (1, 11))
    vm = mk([0x6414, 0x0010, 0x0009, 0x0397, 0x00E2])   # udiv @(3,Y)
    vm.Y = 0x200
    poke(vm, 0x203, 9)
    vm.run(0)
    check('udiv @(3,Y) 0x97 (100 / 9)', (vm.AH, vm.AL), (1, 11))
    vm = mk([0x6414, 0x0010, 0x0296, 0x00E2])           # signed @(2,X), operand -9
    vm.X = 0x100
    poke(vm, 0x102, -9)
    vm.run(0)
    check('sdiv @(2,X) 100 / -9 = -11 r 1', (vm.AH, vm.AL), (1, 0xFFF5))
    vm = mk([0x6414, 0x0010, 0x0009, 0x0195, 0x00E2])
    poke(vm, 1, 0)
    try:
        vm.run(0)
        check('divide by zero raises', False, True)
    except RuntimeError:
        check('divide by zero raises', True, True)
    fw = os.path.join(ROOT, 'firmware', 'bose', 'extracted', 'internal_fs', 'vm.app')
    if os.path.exists(fw):
        def fresh():
            vm = xapemu.VM(xapemu.load_vm_app(fw))
            stubs, _ = xapemu.xapvm.find_stubs(vm.code)
            vm.STUB_RET[stubs[0x4A]] = (0, 0x900)          # PanicUnlessMalloc -> heap block
            vm.Y = 0x800
            return vm
        curve = [100, 1, 1, -99, -99, 0, -99]              # S section 3.1, USR12 group 0
        # by-hand values of S section 3.1 (conv(step) in 1/60 dB)
        for step, want in ((98, -60), (80, -1151), (62, -2242), (50, -2969), (2, -5879), (99, 0)):
            vm = fresh()
            for i, w in enumerate(curve):
                poke(vm, 0x700 + i, w)
            vm.AH, vm.AL = 0x700, step
            r = vm.run(0x22A98)
            got = vm.AL - 0x10000 if vm.AL & 0x8000 else vm.AL
            check('fn_22a98 step %d = %d (div @(6,X) at 0x22ae8/0x22b00)' % (step, want),
                  (r[0], got), ('leavel', want))
        vm = fresh()                                       # fn_0dece(0) with fn_0ddcf stubbed to 10
        vm.FUNC_RET[0x0DDCF] = (0, 10)
        poke(vm, 0x51B, 0x600)                             # fn_0dece: ptr = 7 * AL + @0x51b
        for i, w in enumerate(curve):
            poke(vm, 0x600 + i, w)
        vm.AL = 0
        r = vm.run(0x0DECE)
        got = vm.AL - 0x10000 if vm.AL & 0x8000 else vm.AL
        check('fn_0dece(0) = -2242 (10 * 100 >> 4 = 62 steps through the curve)', (r[0], got),
              ('leavel', -2242))
        for n, want in ((0, -2700), (10, -900), (12, -540), (15, 0)):   # div #0xf
            vm = fresh()
            vm.AL = n
            r = vm.run(0x22A89)
            got = vm.AL - 0x10000 if vm.AL & 0x8000 else vm.AL
            check('fn_22a89(%d) = %d (div #0xf)' % (n, want), (r[0], got), ('leavel', want))
        for g, want in ((0, 15), (-540, 12), (-900, 10), (-2700, 0), (-179, 15), (-181, 14)):
            vm = fresh()                                   # fn_1f3e9: signed div #0xb4 (truncating)
            vm.AL = g & 0xFFFF
            r = vm.run(0x1F3E9)
            check('fn_1f3e9(%d) = %d (signed div #0xb4)' % (g, want), (r[0], vm.X), ('leavel', want))
    print('%d xapemu div cases, %d failed' % (total, bad))
    return bad


def xapemu_shift_cases():
    """tools/xapemu.py (2026-10-19, AE section 11/12): pair shifts by a count held in memory,
    0xA2 asl @(n,X) and 0xA6 asr @(n,X) (the (n,Y) forms 0xA3/0xA7 and @abs 0xA1/0xA5 already
    existed), and 0x98 tst #imm. Real sites: vm.app 0x614c (`ld AL,#1 ; asl @(0,X)`, set-bit idiom),
    fn_16ea1 (0x16ea4 asl @(2,X)) and the tst #imm at 0xf008."""
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import xapemu

    def mk(code):
        w = [0] * 24
        w[4] = 24
        w[6] = len(code)
        return xapemu.VM(w + code)

    def poke(vm, wa, val):
        vm.ram[2 * wa:2 * wa + 2] = (val & 0xFFFF).to_bytes(2, 'little')

    bad = 0
    total = 0

    def check(title, got, want):
        nonlocal bad, total
        total += 1
        ok = got == want
        print('%s  xapemu shift/tst: %s' % ('PASS' if ok else 'FAIL', title))
        if not ok:
            bad += 1
            print('    got %s want %s' % (got, want))

    vm = mk([0x0114, 0x02A2, 0x00E2]); vm.X = 0x100; poke(vm, 0x102, 5); vm.run(0)
    check('asl @(2,X) 0xA2: 1 << 5', (vm.AH, vm.AL), (0, 32))
    vm = mk([0x0114, 0x02A2, 0x00E2]); vm.X = 0x100; poke(vm, 0x102, 20); vm.run(0)
    check('asl @(2,X) 0xA2: 1 << 20 carries into AH', (vm.AH, vm.AL), (0x10, 0))
    vm = mk([0x0114, 0x02A3, 0x00E2]); vm.Y = 0x100; poke(vm, 0x102, 5); vm.run(0)
    check('asl @(2,Y) 0xA3 (existing): 1 << 5', (vm.AH, vm.AL), (0, 32))
    vm = mk([0x03A6, 0x00E2]); vm.X = 0x100; poke(vm, 0x103, 3); vm.AH, vm.AL = 0xFFFF, 0xFFC0; vm.run(0)
    check('asr @(3,X) 0xA6 arithmetic: -64 >> 3 = -8', (vm.AH, vm.AL), (0xFFFF, 0xFFF8))
    vm = mk([0x0009, 0x03A6, 0x00E2]); vm.X = 0x100; poke(vm, 0x103, 4); vm.AH, vm.AL = 0x8000, 0
    vm.run(0)
    check('lsr @(3,X) (0x0009 0xA6) logical: 0x80000000 >> 4', (vm.AH, vm.AL), (0x0800, 0))
    vm = mk([0x03A6, 0x00E2]); vm.X = 0x100; poke(vm, 0x103, 4); vm.AH, vm.AL = 0x8000, 0
    vm.run(0)
    check('asr @(3,X) 0xA6 keeps the sign: 0x80000000 >> 4', (vm.AH, vm.AL), (0xF800, 0))
    vm = mk([0x0198, 0x02F4, 0x0114, 0x00E2]); vm.run(0)
    check('tst #1 0x98: Z = 0, beq not taken (falls to ld AL,#1)', (vm.Z, vm.AL), (0, 1))
    vm = mk([0x0098, 0x02F4, 0x0114, 0x00E2]); vm.run(0)
    check('tst #0 0x98: Z = 1, beq taken (AL untouched)', (vm.Z, vm.AL), (1, 0))
    vm = mk([0xFF98, 0x00E2]); vm.run(0)
    check('tst #-1 0x98: N = 1, Z = 0', (vm.N, vm.Z), (1, 0))
    fw = os.path.join(ROOT, 'firmware', 'bose', 'extracted', 'internal_fs', 'vm.app')
    if os.path.exists(fw):
        vm = xapemu.VM(xapemu.load_vm_app(fw)); vm.Y = 0x800; vm.X = 0x300 - 0; poke(vm, 0x300, 9)
        vm.AL = 1
        vm.run(0x614C, max_steps=1)
        check('vm.app 0x614c: AL=1 ; asl @(0,X) with @X = 9 gives 0x200', (vm.AH, vm.AL), (0, 0x200))
        vm = xapemu.VM(xapemu.load_vm_app(fw)); vm.Y = 0x800; vm.AL = 0x300; poke(vm, 0x302, 3)
        vm.run(0x16EA1, max_steps=7)                   # .. asl @(2,X) ; asl #16 ; asr #16 ; div #5
        check('vm.app fn_16ea1: (1 << 3) / 5 = 1 r 3', (vm.AH, vm.AL), (3, 1))
        vm = xapemu.VM(xapemu.load_vm_app(fw)); vm.Y = 0x800
        r = vm.run(0xF008, max_steps=2)
        check('vm.app 0xf008 tst #1 ; beq: not taken, pc at the bsr 0xf00a',
              (vm.Z, vm.calls_seen == []), (0, True))
    print('%d xapemu shift/tst cases, %d failed' % (total, bad))
    return bad


def xapemu_flag_cases():
    """tools/xapemu.py (2026-10-19, AE section 14): `tst @(n,X)` 0x9A sets N as well as Z (seven
    `tst ; bpl/bmi` sites in vm.app: 0x22571 0x31e30 0x39682 0x396ef 0x39773 0x39863 0x39a25), and
    `nadd` (0x70..0x7F, `neg` = nadd AL,#0) sets C = 1 iff val >= reg (the 32-bit negate idiom
    `neg AL ; xor AH,#-1 ; adc AH,#0` at vm.app 0x39abf)."""
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import xapemu

    def mk(code):
        w = [0] * 24
        w[4] = 24
        w[6] = len(code)
        return xapemu.VM(w + code)

    def poke(vm, wa, val):
        vm.ram[2 * wa:2 * wa + 2] = (val & 0xFFFF).to_bytes(2, 'little')

    bad = 0
    total = 0

    def check(title, got, want):
        nonlocal bad, total
        total += 1
        ok = got == want
        print('%s  xapemu flags: %s' % ('PASS' if ok else 'FAIL', title))
        if not ok:
            bad += 1
            print('    got %s want %s' % (got, want))

    for val, want in ((0x8000, (0, 1)), (0xFFFF, (0, 1)), (0x7FFF, (0, 0)), (0, (1, 0))):
        vm = mk([0x019A, 0x00E2]); vm.X = 0x100; poke(vm, 0x101, val); vm.N = 1 - want[1]; vm.Z = 1 - want[0]
        vm.run(0)
        check('tst @(1,X) 0x9A of %#06x: (Z, N)' % val, (vm.Z, vm.N), want)
    fw = os.path.join(ROOT, 'firmware', 'bose', 'extracted', 'internal_fs', 'vm.app')
    SITE_N = {0x22571: 2, 0x31E30: 1, 0x39682: 1, 0x396EF: 1, 0x39773: 1, 0x39863: 1, 0x39A25: 0}  # operand n of each tst @(n,X), from the decode
    for a in SITE_N:
        if not os.path.exists(fw):
            break
        for val, nwant in ((0x8000, 1), (0x0003, 0)):
            vm = xapemu.VM(xapemu.load_vm_app(fw)); vm.Y = 0x800; vm.N = 1 - nwant
            n = SITE_N[a]
            vm.X = 0x300 - n; poke(vm, 0x300, val)
            vm.run(a, max_steps=1)
            check('vm.app %#x tst @(n,X) of %#06x leaves N = %d' % (a, val, nwant), vm.N, nwant)
    for al, ah, want_c, want in ((0, 1, 1, (0x0000, 0xFFFF)), (5, 0, 0, (0xFFFB, 0xFFFF)),
                                 (0, 0, 1, (0, 0)), (0x8000, 0, 0, (0x8000, 0xFFFF))):
        vm = mk([0x0074, 0xFFD0, 0x0040, 0x00E2]); vm.AL, vm.AH = al, ah; vm.run(0)
        check('neg AL ; xor AH,#-1 ; adc AH,#0 of %#x:%04x = %#010x' % (ah, al, (want[1] << 16) | want[0]),
              (vm.AL, vm.AH), want)
    vm = mk([0x0074, 0x00E2]); vm.AL = 0; vm.C = 0; vm.run(0)
    check('nadd AL,#0 with AL = 0: C = 1', vm.C, 1)
    vm = mk([0x0074, 0x00E2]); vm.AL = 7; vm.C = 1; vm.run(0)
    check('nadd AL,#0 with AL = 7: C = 0', (vm.C, vm.N, vm.AL), (0, 1, 0xFFF9))
    if os.path.exists(fw):
        for ah, al, want in ((1, 0, 0xFFFF0000), (0, 5, 0xFFFFFFFB), (0x8000, 0, 0x80000000)):
            vm = xapemu.VM(xapemu.load_vm_app(fw)); vm.Y = 0x800; vm.AH, vm.AL = ah, al
            vm.run(0x39ABF, max_steps=3)               # neg AL ; xor AH,#-1 ; adc AH,#0
            check('vm.app 0x39abf negate idiom of %#x:%04x' % (ah, al), (vm.AH << 16) | vm.AL, want)
    print('%d xapemu flag cases, %d failed' % (total, bad))
    return bad


def main():
    keep = None
    if '--keep' in sys.argv:
        keep = sys.argv[sys.argv.index('--keep') + 1]
        os.makedirs(keep, exist_ok=True)
    tmp = keep or tempfile.mkdtemp(prefix='cavesim_mocks_')
    words = {}
    for mode in ('bounded', 'unbounded', 'census', 'p2find'):
        words[mode] = os.path.join(tmp, 'mock_%s_words.json' % mode)
        n = build(mode, words[mode])
        print('built mock %-9s %3d words -> %s' % (mode, n, words[mode]))
    bad = 0
    for title, mode, args, expect in CASES:
        cmd = [sys.executable, os.path.join(ROOT, 'tools', 'cavesim.py'), words[mode],
               '--entry', '0x3E21D', '--al', '4004'] + args
        for e in expect:
            cmd += ['--expect', e]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=600)
        ok = r.returncode == 0
        print('%s  %s' % ('PASS' if ok else 'FAIL', title))
        if not ok:
            bad += 1
            print('    ' + ' '.join(cmd[2:]))
            for line in (r.stdout + r.stderr).splitlines():
                if line.startswith(('expect', 'STOPPED', 'Traceback', '  File', '    model: !!')) \
                        or 'Error' in line or line.startswith('port-3 rules'):
                    print('    ' + line)
    print('%d cases, %d failed' % (len(CASES), bad))
    print()
    bad_ext = run_ext(tmp)
    print()
    bad_mul = xapemu_mul_cases()
    print()
    bad_div = xapemu_div_cases()
    print()
    bad_shift = xapemu_shift_cases()
    print()
    bad_flag = xapemu_flag_cases()
    return 1 if bad or bad_ext or bad_mul or bad_div or bad_shift or bad_flag else 0


if __name__ == '__main__':
    sys.exit(main())
