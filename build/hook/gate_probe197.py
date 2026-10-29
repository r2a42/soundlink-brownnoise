#!/usr/bin/env python3
"""Offline world-model gate for probe197 (step R2: the tiny p2 write + the full read-back) -- 2026-10-14.

Runs the real words (build/hook/probe197_words.json, written by assemble_probe197.py) through tools/cavesim.py's clocked
world model with the R2 additions of the same date (a partition-sink model that CAPTURES what is committed, a raw source
built from those bytes with SourceDrop and self-closing at exhaustion, failure injection, a clock), one scripted scenario per
entry, each checked with the simulator's own --expect plus regular expressions on its output ('!' prefix = must NOT match).
Exit 0 = every scenario holds.  NO device, no flash tool: pure emulation.

    python build/hook/assemble_probe197.py                       # first (writes probe197_words.json)
    python build/hook/gate_probe197.py [--part I/N] [--list] [--words PATH]
    --words PATH  runs a mutated copy of the words: the gate must FAIL there (mutation rows)

THE HEALTHY BASE: one centre-long press at t = 0 with the caller-frame guard of the consume lever (--caller-frame 23: a store
to fn_00846's saved return address STOPS the run), sinkState 13 preset, the p2 sink model, a raw source built from what the
sink committed.  Ticks fall at 2000 (TW: erase + write + close) and 12000 (TV: read back) ms.  Expected: 0x26 (written, under
1 s) then 0x33 (all 2800 bytes verified), 100 flushes, 2800 bytes committed, equal to the INDEPENDENT oracle in this file
(byte k = 1 + k mod 224), one raw source opened and self-closed, SourceDrop used, no violation.
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
E = ['--entry', '0x3E21D']
PRESS = ['--press', '0:4004']
LEVER = ['--caller-frame', '23']
STATE = ['--mem', '59e=d']
H = E + PRESS + STATE + LEVER + ['--raw-from-sink', '--horizon', '60000']      # the healthy base
ORACLE = bytes(1 + (k % 224) for k in range(2800))                              # the independent pattern oracle

SCEN = []       # (group, name, args (after the probe name), expects (--expect list), regex list, extra)


def S(group, name, args, expects, regex=(), **extra):
    SCEN.append((group, name, args, list(expects), list(regex), extra))


OKRUN = ['spoken=26,33', 'violations=0', 'pending=0', 'swallowed=1', 'replayed=0', 'flushes=100', 'p2closed=True',
         'rawopen=1', 'rawexhausted=1', 'rawclosed=1']
NOWRITE = ['flushes=0', 'p2closed=False', 'rawopen=0', 'rawcalls=0', 'pending=0', 'violations=0']
NOERASE = r'!OverwriteSink'          # the trap list must not contain the erase/open call

# ------------------------------------------------------------------ NOMINAL
S('NOMINAL', 'healthy base: 0x26 at 2000, 0x33 at 12000; 100 flushes, 2800 bytes = the oracle; one raw source, self-closed',
  H, OKRUN, [r'spoken: 0x26@2000, 0x33@12000', r'SinkClose\(p2 sink\): 100 flushes, 2800 bytes, digest type 3 -> VALID'], capture=True)
S('NOMINAL', 'sinkState 3 (connected, music paused) is accepted', E + PRESS + ['--mem', '59e=3'] + LEVER + ['--raw-from-sink', '--horizon', '60000'],
  OKRUN, capture=True)
S('NOMINAL', 'SourceSize window 127 (the other predicted capacity)', H + ['--raw-prime', '127'], OKRUN)
S('NOMINAL', 'SourceSize window 64 (a smaller ring): the full walk still verifies', H + ['--raw-prime', '64'], OKRUN)
S('NOMINAL', 'SourceSize window 100', H + ['--raw-prime', '100'], OKRUN)
S('NOMINAL', 'the lever: no store reaches the caller\'s saved return address (--caller-frame 23 would STOP the run)', H, OKRUN,
  [r'caller-frame guard: stores to 0x0915, 0x0916 stop the run', r'!STOPPED'])

# ------------------------------------------------------------------ GUARD (sinkState): nothing may be erased or written
for st in ('0', '1', '2', '5', '6', 'a', 'c', 'e', '10', '16'):          # hex values of sinkState
    S('GUARD', 'sinkState 0x%s: 0x3C only, nothing erased, nothing written, the chain ends' % st,
      E + PRESS + ['--mem', '59e=' + st] + LEVER + ['--raw-from-sink', '--horizon', '60000'],
      ['spoken=3c'] + NOWRITE, [NOERASE])
S('GUARD', 'no sinkState preset (the model\'s RAM is 0): refused', E + PRESS + LEVER + ['--raw-from-sink', '--horizon', '60000'],
  ['spoken=3c'] + NOWRITE, [NOERASE])
S('GUARD', 'sinkState changes to 2 at 1000 ms, before the tick: the TICK refuses (the guard is read at the write)',
  H + ['--mem-at', '1000:59e=2'], ['spoken=3c'] + NOWRITE, [NOERASE])
S('GUARD', 'sinkState flips between 13 and 3 during the run: no effect (the guard is read once)',
  H + ['--mem-at', '5000:59e=3'], OKRUN)

# ------------------------------------------------------------------ OPEN / WRITE failures (the sink is closed afterwards)
S('OPEN', 'StreamPartitionOverwriteSink returns 0: 0x3A only, nothing written, the chain ends (no verify of the OLD p2)',
  H + ['--fail', 'StreamPartitionOverwriteSink'], ['spoken=3a', 'flushes=0', 'p2closed=False', 'rawopen=0', 'rawcalls=0',
                                                    'pending=0', 'violations=0'], [r'!SinkMap', r'!SinkClose'])
S('WRITE', 'SinkMap returns 0 in period 1: 0x19, sink CLOSED, nothing committed -> TV: handle 0 (0x27)',
  H + ['--fail', 'SinkMap'], ['spoken=19,27', 'flushes=0', 'p2closed=True', 'rawopen=0', 'violations=0', 'pending=0'])
S('WRITE', 'SinkClaim fails (0xFFFF) in period 1: 0x19 then 0x27', H + ['--claim-fail-at', '1'],
  ['spoken=19,27', 'flushes=0', 'p2closed=True', 'violations=0', 'pending=0'])
S('WRITE', 'SinkClaim fails in period 50: 0x19, 49 periods committed (1372 bytes), closed -> TV: SHORT 0x36',
  H + ['--claim-fail-at', '50', '--allow', 'R8'], ['spoken=19,36', 'flushes=49', 'p2closed=True', 'violations=0', 'pending=0'])
S('WRITE', 'SinkFlush returns 0 in period 50: 0x19, 49 periods committed, closed -> TV: SHORT 0x36',
  H + ['--flush-fail-at', '50', '--allow', 'R8'], ['spoken=19,36', 'flushes=49', 'p2closed=True', 'violations=0', 'pending=0'])
S('WRITE', 'SinkFlush returns 0 in period 1: 0x19, nothing committed -> TV: handle 0',
  H + ['--flush-fail-at', '1'], ['spoken=19,27', 'flushes=0', 'p2closed=True', 'pending=0', 'violations=0'])
S('WRITE', 'SinkFlush returns 0 in period 100 (the last): 0x19, 99 periods committed -> TV: SHORT',
  H + ['--flush-fail-at', '100', '--allow', 'R8'], ['spoken=19,36', 'flushes=99', 'p2closed=True', 'pending=0'])
S('WRITE', 'the digest call returns FALSE: 0x19, the sink is still CLOSED; the model builds no header -> TV: handle 0',
  H + ['--fail', 'PartitionSetMessageDigest'], ['spoken=19,27', 'flushes=100', 'p2closed=True', 'rawopen=0', 'pending=0'])

# ------------------------------------------------------------------ CLAIM OFFSET (V07 D2): the one computed-pointer store is bounded
for off in (1, 10, 20):
    S('OFFSET', 'SinkClaim returns offset %d (<= 20): accepted, the stores go to map + %d, the capture is the oracle' % (off, off),
      H + ['--claim-offset', str(off)], OKRUN, capture=True)
for off in (21, 40, 256, 0x7FFF):
    S('OFFSET', 'SinkClaim returns offset %d (>= 21): REFUSED, no store through the pointer, 0x19 then the verify finds nothing (0x27)' % off,
      H + ['--claim-offset', str(off)], ['spoken=19,27', 'flushes=0', 'p2closed=True', 'rawopen=0', 'violations=0', 'pending=0'])

# ------------------------------------------------------------------ STOPWATCH buckets (erase+write time, VmGetClock)
for ms, ident in ((0, '26'), (999, '26'), (1000, '3e'), (4999, '3e'), (5000, '11'), (30000, '11'), (65000, '11')):
    S('CLOCK', 'erase %d ms (flushes 0 ms): bucket id 0x%s' % (ms, ident), H + ['--erase-ms', str(ms)],
      ['spoken=%s,33' % ident, 'flushes=100', 'violations=0'])
S('CLOCK', '100 flushes x 12 ms = 1200 ms: 0x3E', H + ['--flush-ms', '12'], ['spoken=3e,33'])
S('CLOCK', '100 flushes x 60 ms = 6000 ms: 0x11', H + ['--flush-ms', '60'], ['spoken=11,33'])
S('CLOCK', 'the 16-bit clock rolls over INSIDE a fast run: read as the slow id (documented 1-in-60 false slow)',
  H + ['--clock-base', '63400', '--erase-ms', '500'], ['spoken=11,33'])
S('CLOCK', 'the clock sits at 65000 at t0 and the run is fast with NO rollover: 0x26',
  H + ['--clock-base', '63000', '--erase-ms', '100'], ['spoken=26,33'])

# ------------------------------------------------------------------ VERIFY (TV): handle 0, mismatch classes, short
S('VERIFY', '0xD3 returns 0 although the write closed well: 0x27', H + ['--raw-refuse'],
  ['spoken=26,27', 'rawopen=0', 'flushes=100', 'violations=0', 'pending=0'])
for pos, ident, what in ((0, '30', 'the first byte'), (1, '30', 'byte 1'), (27, '30', 'the last byte of period 1'),
                         (28, '30', 'the first byte of period 2'), (100, '30', 'byte 100'), (125, '30', 'byte 125 (last of the prime)'),
                         (126, '3f', 'byte 126 (first after the prime)'), (127, '3f', 'byte 127'), (252, '3f', 'byte 252'),
                         (1000, '3f', 'byte 1000'), (2799, '3f', 'the last byte')):
    S('VERIFY', 'one wrong byte at %d (%s): id 0x%s, the source is CLOSED by the cave' % (pos, what, ident),
      H + ['--raw-corrupt', str(pos)], ['spoken=26,%s' % ident, 'rawopen=1', 'rawclosed=1', 'rawexhausted=0', 'violations=0', 'pending=0'])
S('VERIFY', 'a ring-end wrap bug (byte p reads byte p-128 from 126 on): first wrong byte at 128 -> 0x3F',
  H + ['--raw-wrapbug', '128'], ['spoken=26,3f', 'rawclosed=1', 'rawexhausted=0', 'violations=0'])
S('VERIFY', 'a wrap bug of 27 bytes: first wrong byte at 126 -> 0x3F', H + ['--raw-wrapbug', '27'],
  ['spoken=26,3f', 'violations=0'])
S('VERIFY', 'packed little-endian elements: the first element is wider than 0xFF -> 0x18', H + ['--raw-pack', 'le'],
  ['spoken=26,18', 'rawclosed=1', 'violations=0'])
S('VERIFY', 'packed big-endian elements -> 0x18', H + ['--raw-pack', 'be'], ['spoken=26,18', 'violations=0'])
for n in (0, 1, 126, 127, 1000, 2799):
    if n == 0:
        continue
    S('VERIFY', 'the stream is %d bytes (SHORT of 2800): 0x36; the drained source is not closed again' % n,
      H + ['--raw-truncate', str(n), '--allow', 'R8'], ['spoken=26,36', 'pending=0', 'rawexhausted=1'])
S('VERIFY', 'SourceMap returns 0 on a live source: 0x36 AND the source is closed', H + ['--raw-map-zero'],
  ['spoken=26,36', 'rawclosed=1', 'rawexhausted=0', 'violations=0'])
S('VERIFY', 'the window reports 0 (--raw-prime 0): 0x36, the live source is not touched again (a model leak warning only)',
  H + ['--raw-prime', '0'], ['spoken=26,36', 'violations=0'])
S('VERIFY', 'the stream is 2800 bytes long but the model\'s drops are honoured: exactly 2800 bytes are checked (R reaches 0 '
            'with the source self-closed and untouched)', H, OKRUN)

# ------------------------------------------------------------------ PRESS handling
S('PRESS', 'a second press at 1000 ms (TW pending): STOP, nothing erased, nothing written',
  H + ['--press', '1000:4004'], ['spoken=', 'swallowed=2'] + NOWRITE, [NOERASE])
S('PRESS', 'a second press at 5000 ms (TV pending until 12000): STOP, the write stands, the verify never runs',
  H + ['--press', '5000:4004'], ['spoken=26', 'swallowed=2', 'flushes=100', 'p2closed=True', 'rawcalls=0', 'pending=0', 'violations=0'])
S('PRESS', 'a second press at 40000 ms (the run is over): a SECOND full run (200 flushes)',
  E + PRESS + STATE + LEVER + ['--raw-from-sink', '--horizon', '100000', '--press', '40000:4004'],
  ['spoken=26,33,26,33', 'swallowed=2', 'flushes=200', 'rawopen=2', 'rawexhausted=2', 'pending=0', 'violations=0'])
S('PRESS', 'a non-0x4004 event is replayed to the stock, nothing else happens',
  E + ['--press', '0:4003', '--once'] + STATE + LEVER + ['--raw-from-sink'],
  ['spoken=', 'replayed=1', 'swallowed=0'] + NOWRITE, [NOERASE])
S('PRESS', 'an id that is not a stage (0x77) delivered to the handler: nothing happens',
  E + ['--pending', '77@1000', '--horizon', '10000'] + STATE + ['--raw-from-sink'], ['spoken='] + NOWRITE, [NOERASE])
S('PRESS', '--cancel never (a STOP finds nothing): a second press during the gap starts a second chain; the run still ends',
  H + ['--cancel', 'never', '--press', '5000:4004', '--horizon', '100000'], ['rawopen=2'], extra_ok_violations=True)

# ------------------------------------------------------------------ STUBS / TRAP LIST
S('STUBS', 'one synthesised stub (0xD3, 8 words) is named; no SinkSlack/PartitionGetInfo control; the trap list has no '
           'SourceClose in the verified path', H, OKRUN,
  [r'SYNTHESISED TRAP STUB at 0x3E[0-9A-F]+: trap 0xD3 PartitionGetRawSerialSource, inline tail, 8 words',
   r'!trap 0xCE', r'!SourceClose'])
S('STUBS', 'rule R3 (no SPEAK while port 3 is ours) is silent: R2 builds no transform', H, ['violations=0'],
  [r'port-3 rules: OK', r'!TransformAdpcmDecode', r'!TransformStart', r'!TransformStop'])
S('STUBS', 'the erase/open call happens exactly once per run and AFTER the guard', H, OKRUN,
  [r'(?s)VmGetClock S\.PartitionOverwriteSink SinkMap'])


def run_one(words, scen):
    group, name, args, expects, regex, extra = scen
    cap = None
    cmd = [sys.executable, 'tools/cavesim.py', words] + args + ['--brief']
    if extra.get('capture'):
        fd, cap = tempfile.mkstemp(suffix='.p2cap')
        os.close(fd)
        cmd += ['--p2-capture', cap]
    for e in expects:
        cmd += ['--expect', e]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=900)
    out = r.stdout + r.stderr
    bad = []
    if r.returncode != 0 and not extra.get('extra_ok_violations'):
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
    if 'STOPPED' in out and '!STOPPED' not in regex or 'Traceback' in out:
        bad.append('STOPPED/Traceback in the output')
    if cap is not None:
        data = open(cap, 'rb').read()
        os.unlink(cap)
        if data != ORACLE:
            bad.append('p2 capture (%d bytes) differs from the independent oracle (2800 bytes, byte k = 1 + k mod 224)' % len(data))
    return bad, out


def main():
    argv = sys.argv[1:]
    if '--list' in argv:
        for i, s in enumerate(SCEN):
            print('%2d %-8s %s' % (i, s[0], s[1]))
        return 0
    words = 'probe197'
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
