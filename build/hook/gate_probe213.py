#!/usr/bin/env python3
"""Offline gate for probe213 (the connect-triggered READ-ONLY census). Pure emulation (tools/cavesim.py, the clocked world); no device.
    python build/hook/assemble_probe213.py      # first (writes probe213_words.json)
    python build/hook/gate_probe213.py
The census content must equal probe211b's (same structure, same ids in the same order, the same speech); only the start (20 s after the last
connect event) and the spacing (3500 ms instead of 4000 ms) differ. probe211b_words.json must exist (python build/hook/assemble_probe211b.py)."""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
W213 = os.path.join(HERE, 'probe213_words.json')
W211B = os.path.join(HERE, 'probe211b_words.json')
BASE = ['--entry', '0x3E21D', '--caller-frame', '23', '--world', '--music', 'playing', '--steps', '400000000']
STRUCT = ['--mem', '72b=1000', '--mem', '1000=ba3c', '--mem', '100b=5', '--mem', '100d=ac44', '--mem', '1017=2']
NOWRITE = [r'!OverwriteSink', r'!SinkMap', r'!SinkClaim', r'!SinkFlush', r'!PartitionSetMessageDigest', r'!SinkClose', r'!TransformStart', r'!KalimbaSendMessage']
SKIP_MS = 200


def sim(words, args):
    r = subprocess.run([sys.executable, 'tools/cavesim.py', words] + args, cwd=ROOT, capture_output=True, text=True, timeout=1800)
    return r.returncode, r.stdout + r.stderr


def spoken(out):
    m = re.search(r'^spoken: (.*)$', out, re.M)
    if not m or m.group(1).strip() == '(nothing)':
        return []
    return [(int(a, 16), int(b)) for a, b in re.findall(r'0x([0-9a-f]+)@(\d+)', m.group(1))]


def check(name, bad):
    print('%s %s' % ('FAIL' if bad else 'ok  ', name), flush=True)
    for b in bad:
        print('      -> %s' % b)
    return 1 if bad else 0


def grep(out, regex):
    bad = []
    for rx in regex:
        neg = rx.startswith('!')
        pat = rx[1:] if neg else rx
        if (re.search(pat, out) is not None) == neg:
            bad.append(('must NOT match: ' if neg else 'missing: ') + pat)
    return bad


def main():
    fails = 0
    # 1. equivalence with probe211b
    rc1, o1 = sim(W213, BASE + ['--press', '0:4742', '--press', '3000:4753', '--press', '6000:4715', '--horizon', '500000'] + STRUCT)
    rc2, o2 = sim(W211B, BASE + ['--press', '0:4004', '--horizon', '500000'] + STRUCT)
    a, b = spoken(o1), spoken(o2)
    bad = []
    if not a:
        bad.append('probe213 spoke nothing')
    if [i for i, _ in a] != [i for i, _ in b]:
        bad.append('id sequence differs from probe211b (%d vs %d prompts)' % (len(a), len(b)))
    if a and a[0] != (0x12, 28000):
        bad.append('start cue is %r, expected 0x12 at 28000 (6000 + 20000 + 2000)' % (a[0],))
    gaps = [a[k + 1][1] - a[k][1] for k in range(len(a) - 1)]
    if gaps and min(gaps) < SKIP_MS:
        bad.append('a gap below %d ms' % SKIP_MS)
    if any(g not in (3500, SKIP_MS, 3500 + SKIP_MS) and g < 3500 for g in gaps):
        bad.append('unexpected gaps %r' % sorted(set(gaps)))
    bad += grep(o1, [r'presses: 0 swallowed, 3 replayed', r'cave messages still pending: 0', r'!violat'] + NOWRITE)
    fails += check('connect events 0x4742 (0 ms), 0x4753 (3 s), 0x4715 (6 s): the census starts at 28000 and speaks exactly probe211b\'s sequence (%d prompts, %d ms to the end)' % (len(a), a[-1][1] if a else 0), bad)
    # 2. a connect event while a census runs aborts it
    rc, o = sim(W213, BASE + ['--press', '0:4742', '--press', '25000:4715', '--horizon', '200000'] + STRUCT)
    s = spoken(o)
    bad = []
    if not s or s[0] != (0x12, 22000):
        bad.append('first cue %r, expected 0x12 at 22000' % (s[:1],))
    if s and s[-1][1] > 45000:
        bad.append('spoke after the abort at 45000: %r' % (s[-1],))
    if len(s) < 5:
        bad.append('too few prompts before the abort')
    bad += grep(o, [r'presses: 0 swallowed, 2 replayed', r'cave messages still pending: 0', r'!violat'] + NOWRITE)
    fails += check('a connect event during a census aborts it silently (nothing pending afterwards)', bad)
    # 3. the manual press still starts the census and a second press stops it
    rc, o = sim(W213, BASE + ['--press', '0:4004', '--press', '20000:4004', '--horizon', '100000'] + STRUCT)
    s = spoken(o)
    bad = []
    if not s or s[0] != (0x12, 2000):
        bad.append('manual start cue %r' % (s[:1],))
    if s and s[-1][1] > 20000:
        bad.append('spoke after the stop press: %r' % (s[-1],))
    bad += grep(o, [r'presses: 2 swallowed, 0 replayed', r'cave messages still pending: 0'] + NOWRITE)
    fails += check('the centre long press still starts (cue at 2000) and stops the census, event swallowed', bad)
    # 4. no structure pointer
    rc, o = sim(W213, BASE + ['--press', '0:4742', '--horizon', '60000'])
    bad = grep(o, [r'spoken: 0x3b@20000\b', r'presses: 0 swallowed, 1 replayed', r'cave messages still pending: 0'] + NOWRITE)
    fails += check('no structure pointer: 0x3B at 20000 (the debounced start), nothing armed', bad)
    # 5. other events replayed
    rc, o = sim(W213, ['--entry', '0x3E21D', '--caller-frame', '23', '--world', '--press', '0:4003', '--press', '100:4716', '--horizon', '30000'])
    bad = grep(o, [r'spoken: \(nothing\)', r'presses: 0 swallowed, 2 replayed', r'cave messages still pending: 0'])
    fails += check('other events (0x4003, 0x4716) are replayed to the stock, nothing spoken, nothing armed', bad)
    # 6. the lever
    rc, o = sim(W213, BASE + ['--press', '0:4742', '--horizon', '40000'] + STRUCT)
    bad = grep(o, [r'caller-frame guard: stores to 0x0915, 0x0916 stop the run', r'!STOPPED'])
    fails += check('the lever: no store reaches the caller saved return address', bad)
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import framecheck
    fnd = framecheck.check(framecheck.load(W213))
    fails += check('tools/framecheck.py: no store into the top two slots of any function frame', ['%s' % (f,) for f in fnd] if fnd else [])
    print('\n7 scenario(s) run, %d failed' % fails)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
