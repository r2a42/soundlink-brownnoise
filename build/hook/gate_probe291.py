#!/usr/bin/env python3
"""Offline world-model gate for probe291 (R3 rebuilt for the probe200 result: the file-source map is shifted by ONE element) -- 2026-10-14.
NOT independently reviewed. The world model keeps the staged data_us and adds `--map-lead 1` (element j holds window byte j - 1); every row of probe198 rev 2 is kept
under that model, with new rows for the look (pass and refuse), the window boundaries and the frame rule.
PREPARATION ONLY. Not flash-cleared. NO device, no flash tool: pure emulation.

Runs the real words (build/hook/probe198_words.json, written by assemble_probe198.py) through tools/cavesim.py's clocked world
model. The file the cave opens is the EDITED data_us of narrow184_lib.stage(payload, 1320), written to
build/payload/g3/data_us_g2p0_staged (a generated file) and given to the world with --fs-add NowSpeakTTS/data_us=@file, one byte per
map element (--src-unpacked, the unit rule F207). Every healthy row checks that the flush stream the p2 sink COMMITTED
(--p2-capture) equals an INDEPENDENT oracle: the payload file bytes, read directly from build/payload/r3/ (sha256 pinned below).

    python build/hook/assemble_probe208.py                     # first (writes probe208_words.json)
    python build/hook/gate_probe208.py [--part I/N] [--list] [--words PATH]
    --words PATH  runs a mutated copy of the words: the gate must FAIL there (mutation rows)
"""
import hashlib
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
PAYLOAD_PATH = os.path.join(ROOT, 'build', 'payload', 'g3', 'brown_8000_58968_music_g2p0.adpcm')
PAYLOAD_SHA = '0f3cf48668d9f1e9d1f76270fc81a724ae9713ab6fb7534d9d18f26f6ed85ce1'
STAGED_REL = 'build/payload/g3/data_us_g2p0_staged'
START_PERIOD = 1320

ORACLE = open(PAYLOAD_PATH, 'rb').read()
assert hashlib.sha256(ORACLE).hexdigest() == PAYLOAD_SHA and len(ORACLE) == 58968, 'the payload file is not the pinned one'

sys.path.append(os.path.join(ROOT, 'build', 'hook'))
import narrow184_lib as L      # noqa: E402
_swp = bytearray(ORACLE)
for _k in range(0, len(_swp), 2):
    _swp[_k], _swp[_k + 1] = _swp[_k + 1], _swp[_k]
_stg = L.stage(bytes(_swp), START_PERIOD)                       # probe208: the payload staged with every adjacent pair swapped
_built = _stg['new_us']


def _served(built, lo=84480):
    """the file the SPEAKER serves for a staged image (probe206/207, owner exact matches): from byte 84,480 on an ODD file offset serves the byte built two positions later"""
    d = bytearray(built)
    for _o in range(lo, len(built) - 2):
        if _o % 2 == 1:
            d[_o] = built[_o + 2]
    return bytes(d)


_stg = dict(_stg)
_stg['new_us'] = _served(_built)                                  # the world serves the lane-swapped view of the staged image
_sp = os.path.join(ROOT, STAGED_REL)
if not (os.path.exists(_sp) and open(_sp, 'rb').read() == _stg['new_us']):      # never rewrite an identical file (parallel parts read it)
    with open(_sp, 'wb') as _f:
        _f.write(_stg['new_us'])

E = ['--entry', '0x3E21D']
PRESS = ['--press', '0:4004']
LEVER = ['--caller-frame', '23']
STATE = ['--mem', '59e=d']
STAGED = ['--fs-add', 'NowSpeakTTS/data_us=@' + STAGED_REL, '--src-unpacked', '--map-lead', '1']      # probe200: element j = window byte j - 1
BASE = E + PRESS + STATE + LEVER + ['--raw-from-sink', '--steps', '8000000', '--horizon', '60000']
H = BASE + STAGED                       # the healthy base: the staged data_us

SCEN = []


def S(group, name, args, expects, regex=(), **extra):
    SCEN.append((group, name, args, list(expects), list(regex), extra))


OKRUN = ['spoken=30', 'violations=0', 'pending=0', 'swallowed=1', 'replayed=0', 'flushes=2106', 'p2closed=True']
UNTOUCHED = ['flushes=0', 'p2closed=False', 'pending=0', 'violations=0']
NOERASE = r'!OverwriteSink'
FILES_CLOSED = r'file sources: 1 opened, 0 never closed'

# ------------------------------------------------------------------ NOMINAL
S('NOMINAL', 'healthy base: 0x30 at 2000; 2106 flushes, 58968 bytes = the payload (oracle); the file source closed',
  H, OKRUN, [r'spoken: 0x30@2000', r'SinkClose\(p2 sink\): 2106 flushes, 58968 bytes, digest type 3 -> VALID', FILES_CLOSED],
  capture=True)
S('NOMINAL', 'sinkState 3 is accepted', E + PRESS + ['--mem', '59e=3'] + LEVER + ['--raw-from-sink', '--steps', '8000000',
                                                                                  '--horizon', '60000'] + STAGED,
  OKRUN, capture=True)
S('NOMINAL', 'SinkClaim returns offset 20 (the largest legal): the stores go to map + 20, the capture is still the payload',
  H + ['--claim-offset', '20'], OKRUN, capture=True)
S('NOMINAL', 'a file window of 128 bytes (SourceSize 128): the same stream', H + ['--src-window', '128'], OKRUN, capture=True)
S('NOMINAL', 'a file window of exactly 64 bytes (the minimum the cave accepts)', H + ['--src-window', '64'], OKRUN, capture=True)
S('NOMINAL', 'the lever: no store reaches the caller\'s saved return address', H, OKRUN,
  [r'caller-frame guard: stores to 0x0915, 0x0916 stop the run', r'!STOPPED'])

# ------------------------------------------------------------------ GUARD (sinkState): nothing opened, erased or written
for st in ('0', '1', '2', '5', '6', 'a', 'c', 'e', '10', '16'):
    S('GUARD', 'sinkState 0x%s: 0x3C only, no file opened, nothing erased or written, the chain ends' % st,
      E + PRESS + ['--mem', '59e=' + st] + LEVER + ['--raw-from-sink', '--steps', '8000000', '--horizon', '60000'] + STAGED,
      ['spoken=3c'] + UNTOUCHED, [NOERASE, r'!FileFind'])
S('GUARD', 'no sinkState preset: refused', E + PRESS + LEVER + ['--raw-from-sink', '--steps', '8000000', '--horizon', '60000'] + STAGED,
  ['spoken=3c'] + UNTOUCHED, [NOERASE, r'!FileFind'])
S('GUARD', 'sinkState changes to 2 at 1000 ms (before the tick): the TICK refuses', H + ['--mem-at', '1000:59e=2'],
  ['spoken=3c'] + UNTOUCHED, [NOERASE, r'!FileFind'])

# ------------------------------------------------------------------ BEFORE THE ERASE: every refusal leaves p2 untouched
S('PRE', 'FileFind refuses (the first lookup): 0x17, nothing erased', H + ['--fail', 'FileFind'],
  ['spoken=17'] + UNTOUCHED, [NOERASE])
S('PRE', 'FileFind refuses the SECOND lookup (data_us): 0x17', H + ['--fail-after', 'FileFind=2'], ['spoken=17'] + UNTOUCHED, [NOERASE])
S('PRE', 'StreamFileSource refuses: 0x17', H + ['--fail', 'StreamFileSource'], ['spoken=17'] + UNTOUCHED, [NOERASE])
S('PRE', 'the window offers 63 bytes (< 64) during the skip: 0x28, the source is closed, nothing erased',
  H + ['--src-window', '63'], ['spoken=28'] + UNTOUCHED, [NOERASE, FILES_CLOSED])
S('PRE', 'SourceMap returns 0 at the look: 0x3B, source closed, nothing erased', H + ['--fail', 'SourceMap'],
  ['spoken=3b'] + UNTOUCHED, [NOERASE, FILES_CLOSED])
S('PRE', 'the STOCK data_us (image without the staging): the look fails, 0x3B, nothing erased', BASE + ['--src-unpacked'],
  ['spoken=3b'] + UNTOUCHED, [NOERASE, FILES_CLOSED])
S('PRE', 'packed map (two bytes per element): the look fails, 0x3B, nothing erased', BASE + STAGED[:2] + ['--src-endian', 'le'],
  ['spoken=3b'] + UNTOUCHED, [NOERASE])

# ------------------------------------------------------------------ OPEN of the p2 sink
S('OPEN', 'StreamPartitionOverwriteSink returns 0: 0x3A, source closed, nothing written',
  H + ['--fail', 'StreamPartitionOverwriteSink'], ['spoken=3a', 'flushes=0', 'p2closed=False', 'pending=0', 'violations=0'],
  [FILES_CLOSED, r'!SinkMap'])

# ------------------------------------------------------------------ THE LOOP
S('LOOP', 'SinkMap returns 0 in period 1: 0x19; the sink and the source are closed; nothing committed',
  H + ['--fail', 'SinkMap'], ['spoken=19', 'flushes=0', 'p2closed=True', 'pending=0', 'violations=0'], [FILES_CLOSED])
S('LOOP', 'SinkClaim fails (0xFFFF) in period 1: 0x19', H + ['--claim-fail-at', '1'], ['spoken=19', 'flushes=0', 'p2closed=True'], [FILES_CLOSED])
S('LOOP', 'SinkClaim fails in period 1000: 0x19, 999 periods committed, closed', H + ['--claim-fail-at', '1000'],
  ['spoken=19', 'flushes=999', 'p2closed=True', 'violations=0'], [FILES_CLOSED])
for off in (21, 40, 0x7FFF):
    S('LOOP', 'SinkClaim returns offset %d (>= 21): refused before any store through the pointer: 0x19, nothing committed' % off,
      H + ['--claim-offset', str(off)], ['spoken=19', 'flushes=0', 'p2closed=True', 'violations=0'])
S('LOOP', 'SinkFlush returns 0 in period 1: 0x19, nothing committed', H + ['--flush-fail-at', '1'],
  ['spoken=19', 'flushes=0', 'p2closed=True'])
S('LOOP', 'SinkFlush returns 0 in period 1000: 0x19, 999 periods committed, closed', H + ['--flush-fail-at', '1000'],
  ['spoken=19', 'flushes=999', 'p2closed=True'], [FILES_CLOSED])
S('LOOP', 'SinkFlush returns 0 in the LAST period: 0x19, 2105 committed', H + ['--flush-fail-at', '2106'],
  ['spoken=19', 'flushes=2105', 'p2closed=True'])
S('LOOP', 'SourceMap fails from its 500th call on (mid-gather): 0x19, closed', H + ['--fail-after', 'SourceMap=500'],
  ['spoken=19', 'p2closed=True', 'violations=0'], [FILES_CLOSED])
S('LOOP', 'SourceSize reads 0 from its 2000th call on (the gather asks for the window): 0x19, closed',
  H + ['--size-dries-after', '2000'], ['spoken=19', 'p2closed=True', 'violations=0'], [FILES_CLOSED])
S('LOOP', 'the digest call returns FALSE: 0x19, the sink is still closed', H + ['--fail', 'PartitionSetMessageDigest'],
  ['spoken=19', 'flushes=2106', 'p2closed=True'], [FILES_CLOSED])

# ------------------------------------------------------------------ V09 D1: the clock bound on the single write tick
SK = r'SinkClose\(p2 sink\): \d+ flushes, \d+ bytes, digest type 3 -> VALID'
HEALTHY_T = ['spoken=30', 'violations=0', 'pending=0', 'flushes=2106', 'p2closed=True']
S('TIME', 'healthy but slow: 4 ms per flush (8.4 s), erase 300 ms: no abort, the payload is identical (oracle)',
  H + ['--flush-ms', '4', '--erase-ms', '300'], HEALTHY_T, [r'spoken: 0x30', FILES_CLOSED], capture=True)
S('TIME', 'the slowest healthy flash: 6 ms per flush (12.6 s; 100 periods in 600 ms): no abort, the payload is identical',
  H + ['--flush-ms', '6', '--erase-ms', '300'], HEALTHY_T, [r'spoken: 0x30'], capture=True)
S('TIME', 'a very slow ERASE (20 s) does not count: the clock starts after the sink is open; no abort, oracle identical',
  H + ['--flush-ms', '2', '--erase-ms', '20000'], HEALTHY_T, [r'spoken: 0x30'], capture=True)
S('TIME', 'the 32-bit clock crosses a 16-bit boundary mid-write (base 0xFFF0): the 16-bit difference stays exact; no abort',
  H + ['--flush-ms', '4', '--clock-base', '65520'], HEALTHY_T, [r'spoken: 0x30'], capture=True)
S('TIME', 'the 32-bit clock crosses 0xFFFFFFFF mid-write: no abort', H + ['--flush-ms', '4', '--clock-base', '4294960000'],
  HEALTHY_T, [r'spoken: 0x30'], capture=True)
S('TIME', 'ABORT (cap): 8 ms per flush (100 periods in 800 ms passes the early check; 16.8 s in all): stops at 15 s, short valid p2, '
          '0x12, source and sink closed, digest SKIP',
  H + ['--flush-ms', '8'], ['spoken=12', 'violations=0', 'pending=0', 'p2closed=True'], [SK, FILES_CLOSED, r'!spoken: 0x30'])
S('TIME', 'ABORT (early check): 11 ms per flush (1.1 s for 100 periods): stops after 100 periods, 0x12, closed, digest SKIP',
  H + ['--flush-ms', '11'], ['spoken=12', 'flushes=100', 'violations=0', 'pending=0', 'p2closed=True'], [SK, FILES_CLOSED])
S('TIME', 'ABORT (early check, boundary): 10 ms per flush (exactly 1,000 ms for 100 periods): stops (the limit is inclusive)',
  H + ['--flush-ms', '10'], ['spoken=12', 'flushes=100', 'p2closed=True'], [SK, FILES_CLOSED])
S('TIME', 'ABORT (cap, pathological): 1000 ms per flush: stops at 15 s after 15 flushes, 0x12, closed',
  H + ['--flush-ms', '1000'], ['spoken=12', 'flushes=15', 'violations=0', 'pending=0', 'p2closed=True'], [SK, FILES_CLOSED])
S('TIME', 'ABORT across a 16-bit clock boundary (base 0xFFF0, 11 ms): still stops after 100 periods',
  H + ['--flush-ms', '11', '--clock-base', '65520'], ['spoken=12', 'flushes=100', 'p2closed=True'], [SK])
S('TIME', 'ABORT leaves the chain ended: a second press afterwards starts a new, healthy run (no residue)',
  BASE[:-2] + ['--horizon', '100000', '--press', '40000:4004'] + STAGED + ['--flush-ms', '11'],
  ['spoken=12,12', 'swallowed=2', 'flushes=200', 'pending=0', 'violations=0'], [SK])

# ------------------------------------------------------------------ probe291: THE SHIFT (look pass / refuse, window boundaries)
LEAD0 = [a for a in STAGED if a not in ('--map-lead', '1')]          # the old world: element j = window byte j
LEAD2 = LEAD0 + ['--map-lead', '2']
S('SHIFT', 'look PASSES with the shift of one (elements 19..22 = 77 7f 77 c6): the base row, already NOMINAL; here with the exact trap order up to the erase',
  H, OKRUN, [r'FileFind FileFind S\.FileSource SourceSize SourceDrop.*SourceMap S\.PartitionOverwriteSink'], capture=True)
S('SHIFT', 'look REFUSES (0x3B) in the OLD world (no shift: element 19 is 7f, not 77): nothing erased, source closed',
  BASE + LEAD0, ['spoken=3b'] + UNTOUCHED, [NOERASE, FILES_CLOSED])
S('SHIFT', 'look REFUSES (0x3B) when the map is shifted by TWO (element 19 is the byte before the payload): nothing erased',
  BASE + LEAD2, ['spoken=3b'] + UNTOUCHED, [NOERASE, FILES_CLOSED])
S('SHIFT', 'a map with the shift of one but a window of exactly 64 bytes (elements 1..64): every flush reads elements 19..46: written, capture = payload',
  H + ['--src-window', '64'], OKRUN, capture=True)
S('SHIFT', 'the same with the map TRUNCATED to SourceSize elements in all (the last window byte is not mapped): elements 19..46 are far from the end: written',
  H + ['--src-window', '64', '--map-trunc'], OKRUN, capture=True)
S('SHIFT', 'window 128 with the shift: written, capture = payload', H + ['--src-window', '128'], OKRUN, capture=True)
S('SHIFT', 'window 47 (< 64): the skip refuses before the erase (0x28), the last flush would have needed element 46 of a 47-byte window',
  H + ['--src-window', '47'], ['spoken=28'] + UNTOUCHED, [NOERASE, FILES_CLOSED])
S('SHIFT', 'the stock data_us with the shift: refused (0x3B)', BASE + ['--src-unpacked', '--map-lead', '1'], ['spoken=3b'] + UNTOUCHED, [NOERASE])

# ------------------------------------------------------------------ probe208: the PAIR-SWAP (probe206/207): the staging must be pre-swapped, the served view is lane-swapped
_plain_rel = 'build/payload/g3/data_us_g2p0_plain_served'
_plain = _served(L.stage(ORACLE, START_PERIOD)['new_us'])           # the OLD staging (probe291: not pre-swapped) as the speaker would serve it
_pp = os.path.join(ROOT, _plain_rel)
if not (os.path.exists(_pp) and open(_pp, 'rb').read() == _plain):
    with open(_pp, 'wb') as _f:
        _f.write(_plain)
_nosw_rel = 'build/payload/g3/data_us_g2p0_swapped_noserved'
_pp2 = os.path.join(ROOT, _nosw_rel)
if not (os.path.exists(_pp2) and open(_pp2, 'rb').read() == _built):
    with open(_pp2, 'wb') as _f:
        _f.write(_built)
S('SWAP', 'the OLD (unswapped) staging served through the lane swap, as probe291 had it: the look REFUSES (0x3B), nothing erased',
  BASE + ['--fs-add', 'NowSpeakTTS/data_us=@' + _plain_rel, '--src-unpacked', '--map-lead', '1'], ['spoken=3b'] + UNTOUCHED, [NOERASE, FILES_CLOSED])
S('SWAP', 'the pair-swapped staging served WITHOUT a lane swap (a world where the speaker did not swap): the look REFUSES (0x3B), nothing erased',
  BASE + ['--fs-add', 'NowSpeakTTS/data_us=@' + _nosw_rel, '--src-unpacked', '--map-lead', '1'], ['spoken=3b'] + UNTOUCHED, [NOERASE, FILES_CLOSED])

# ------------------------------------------------------------------ FRAME (V11 D1)
S('FRAME', 'tools/framecheck.py: no store into the top two slots of any function frame (per function)', [], [], [], frame='fc')
S('FRAME', 'cavesim static hazards: none except the whole-image frame line (framecheck answers it per function) and data blocks', [], [], [], frame='hz')

# ------------------------------------------------------------------ PRESS handling
S('PRESS', 'a second press at 1000 ms (TW pending): STOP, nothing opened, nothing erased',
  H + ['--press', '1000:4004'], ['spoken=', 'swallowed=2'] + UNTOUCHED, [NOERASE, r'!FileFind'])
S('PRESS', 'a second press at 40000 ms (the run is over): a SECOND full run (4212 flushes), same oracle per run',
  BASE[:-2] + ['--horizon', '100000', '--press', '40000:4004'] + STAGED,
  ['spoken=30,30', 'swallowed=2', 'flushes=4212', 'pending=0', 'violations=0'])
S('PRESS', 'a non-0x4004 event is replayed to the stock, nothing else happens',
  E + ['--press', '0:4003', '--once'] + STATE + LEVER + ['--raw-from-sink'] + STAGED,
  ['spoken=', 'replayed=1', 'swallowed=0'] + UNTOUCHED, [NOERASE, r'!FileFind'])
S('PRESS', 'an id that is not a stage (0x77) delivered to the handler: nothing happens',
  E + ['--pending', '77@1000', '--horizon', '10000'] + STATE + ['--raw-from-sink'] + STAGED,
  ['spoken='] + UNTOUCHED, [NOERASE, r'!FileFind'])
S('PRESS', 'the cave never touches 0xD3 or a raw source in this variant (no read-back tick)', H, OKRUN + ['rawcalls=0'],
  [r'!raw partition sources'])

# ------------------------------------------------------------------ STUBS / TRAP LIST
S('STUBS', 'NO synthesised trap stub is carried (0xD3 is not called in this variant); rule R3 silent; no transform',
  H, OKRUN, [r'!SYNTHESISED TRAP STUB', r'port-3 rules: OK', r'!TransformAdpcmDecode', r'!TransformStart', r'!TransformStop'])
S('STUBS', 'order of traps in the write tick: FileFind x2, FileSource, the skip, ONE SourceMap (the look), THEN the erase, then '
           'the loop (VmGetClock first, then per period: VmGetClock SourceMap SinkMap SinkClaim memmove SinkFlush SourceSize SourceDrop), SourceClose, digest, SinkClose, SPEAK',
  H, OKRUN, [r'(?s)FileFind FileFind S\.FileSource SourceSize SourceDrop.*?SourceSize SourceDrop SourceMap S\.PartitionOverwriteSink '
             r'VmGetClock VmGetClock SourceMap SinkMap SinkClaim memmove SinkFlush SourceSize SourceDrop VmGetClock SourceMap.*SourceClose '
             r'PartitionSetMessageDigest SinkClose SPEAK'])


sys.path.insert(0, os.path.join(ROOT, 'tools'))


def run_frame(words, kind):
    import framecheck
    bad = []
    if kind == 'fc':
        fnd = framecheck.check(framecheck.load(words))
        for a, k, n, txt in fnd:
            bad.append('0x%05x %s inside enterl -%d: slot %d is part of the saved return address' % (a, txt, k, n))
        return bad, 'framecheck: %d finding(s)' % len(fnd)
    cmd = [sys.executable, 'tools/cavesim.py', words] + E + ['--brief']
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)
    out = r.stdout + r.stderr
    data = framecheck.data_addrs(framecheck.load(words))
    for ln in out.splitlines():
        if ln.strip().startswith('HAZARD') and 'frame slot' not in ln:
            m = re.match(r'\s*HAZARD\s+0x([0-9A-Fa-f]+)', ln)
            if m and int(m.group(1), 16) in data:
                continue
            bad.append(ln.strip()[:200])
    return bad, out


def run_one(words, scen):
    group, name, args, expects, regex, extra = scen
    if extra.get('frame'):
        return run_frame(words, extra['frame'])
    cap = None
    cmd = [sys.executable, 'tools/cavesim.py', words] + args + ['--brief']
    if extra.get('capture'):
        fd, cap = tempfile.mkstemp(suffix='.p2cap')
        os.close(fd)
        cmd += ['--p2-capture', cap]
    for e in expects:
        cmd += ['--expect', e]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=1800)
    out = r.stdout + r.stderr
    bad = []
    if r.returncode != 0:
        bad.append('exit code %d' % r.returncode)
    for ln in out.splitlines():
        if (ln.startswith('expect ') and ln.rstrip().endswith('FAIL')) or ' FAIL (have' in ln:
            bad.append(ln.strip())
    for rx in regex:
        if rx.startswith('!'):
            if re.search(rx[1:], out):
                bad.append('must not match /%s/' % rx[1:])
        elif not re.search(rx, out):
            bad.append('missing /%s/' % rx)
    if ('STOPPED' in out and '!STOPPED' not in regex) or 'Traceback' in out:
        bad.append('STOPPED/Traceback in the output')
    if cap is not None:
        data = open(cap, 'rb').read()
        os.unlink(cap)
        if data != ORACLE:
            bad.append('p2 capture (%d bytes, sha256 %s) differs from the independent oracle (%d bytes, sha256 %s)'
                       % (len(data), hashlib.sha256(data).hexdigest()[:16], len(ORACLE), PAYLOAD_SHA[:16]))
    return bad, out


def main():
    argv = sys.argv[1:]
    if '--list' in argv:
        for i, s in enumerate(SCEN):
            print('%2d %-8s %s' % (i, s[0], s[1]))
        return 0
    words = 'probe291'
    if '--words' in argv:
        words = argv[argv.index('--words') + 1]
    part = (0, 1)
    if '--part' in argv:
        a, b = argv[argv.index('--part') + 1].split('/')
        part = (int(a) - 1, int(b))
    fails = ran = 0
    for i, s in enumerate(SCEN):
        if i % part[1] != part[0]:
            continue
        bad, out = run_one(words, s)
        ran += 1
        print('%s %2d %-7s %s' % ('FAIL' if bad else 'ok  ', i, s[0], s[1]))
        for b in bad:
            print('      -> %s' % b)
        if bad:
            fails += 1
            print('\n'.join('      | ' + ln[:200] for ln in out.splitlines()[-14:]))
    print('\n%d scenario(s) run, %d failed' % (ran, fails))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
