#!/usr/bin/env python3
"""Offline gate for probe212 (the READ-ONLY event-map beacon). Pure emulation (tools/cavesim.py, the clocked world); no device.
    python build/hook/assemble_probe212.py      # first (writes probe212_words.json)
    python build/hook/gate_probe212.py
Every row greps the simulator report with regular expressions (a leading ! means: must NOT match)."""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
WORDS = os.path.join(HERE, 'probe212_words.json')
BASE = ['--entry', '0x3E21D', '--caller-frame', '23', '--world', '--music', 'playing', '--steps', '400000000']
NOWRITE = [r'!OverwriteSink', r'!SinkMap', r'!SinkClaim', r'!SinkFlush', r'!PartitionSetMessageDigest', r'!SinkClose', r'!TransformStart', r'!KalimbaSendMessage']

SCEN = [
    ('events 0x4715 at 0 ms and 0x4753 at 100 ms: prompts 0x27 at 2000 and 0x29 at 10100, both events replayed, nothing pending',
     BASE + ['--press', '0:4715', '--press', '100:4753', '--horizon', '30000'],
     [r'spoken: 0x27@2000, 0x29@10100', r'presses: 0 swallowed, 2 replayed', r'cave messages still pending: 0', r'!violat'] + NOWRITE),
    ('all eight events at once: prompts 0x27..0x2e in order at 2000 + 4000 * index',
     BASE + sum([['--press', '0:%X' % e] for e in (0x4715, 0x472D, 0x4753, 0x4742, 0x4754, 0x4716, 0x4743, 0x477C)], []) + ['--horizon', '60000'],
     [r'spoken: 0x27@2000, 0x28@6000, 0x29@10000, 0x2a@14000, 0x2b@18000, 0x2c@22000, 0x2d@26000, 0x2e@30000', r'presses: 0 swallowed, 8 replayed', r'cave messages still pending: 0'] + NOWRITE),
    ('the centre long press 0x4004 and an unlisted event 0x4003 are replayed to the stock, nothing spoken',
     BASE + ['--press', '0:4004', '--press', '50:4003', '--horizon', '20000'], [r'spoken: \(nothing\)', r'presses: 0 swallowed, 2 replayed', r'cave messages still pending: 0'] + NOWRITE),
    ('the lever: no store reaches the caller saved return address', BASE + ['--press', '0:4715', '--horizon', '30000'], [r'caller-frame guard: stores to 0x0915, 0x0916 stop the run', r'!STOPPED']),
]


def run(args, regex):
    r = subprocess.run([sys.executable, 'tools/cavesim.py', WORDS] + args, cwd=ROOT, capture_output=True, text=True, timeout=1800)
    out = r.stdout + r.stderr
    bad = []
    if r.returncode not in (0, 1):
        bad.append('exit code %d' % r.returncode)
    for rx in regex:
        neg = rx.startswith('!')
        pat = rx[1:] if neg else rx
        if (re.search(pat, out) is not None) == neg:
            bad.append(('must NOT match: ' if neg else 'missing: ') + pat)
    return bad, out


def main():
    fails = 0
    for i, (name, args, regex) in enumerate(SCEN):
        bad, out = run(args, regex)
        print('%s %2d %s' % ('FAIL' if bad else 'ok  ', i, name), flush=True)
        for b in bad:
            print('      -> %s' % b)
        if bad:
            fails += 1
            print('\n'.join('      | ' + ln[:200] for ln in out.splitlines()[-12:]))
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import framecheck
    fnd = framecheck.check(framecheck.load(WORDS))
    print('%s %2d tools/framecheck.py: no store into the top two slots of any function frame' % ('FAIL' if fnd else 'ok  ', len(SCEN)))
    fails += 1 if fnd else 0
    print('\n%d scenario(s) run, %d failed' % (len(SCEN) + 1, fails))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
