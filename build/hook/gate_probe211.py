#!/usr/bin/env python3
"""Offline gate for probe211 (the READ-ONLY census of the stock audio connection record). Pure emulation (tools/cavesim.py, the clocked world); no device.
    python build/hook/assemble_probe211.py      # first (writes probe211_words.json)
    python build/hook/gate_probe211.py
Every row greps the simulator report with regular expressions (a leading ! means: must NOT match)."""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
WORDS = os.path.join(HERE, 'probe211_words.json')
BASE = ['--entry', '0x3E21D', '--caller-frame', '23', '--world', '--music', 'playing', '--steps', '400000000']
STRUCT = ['--mem', '72b=1000', '--mem', '1000=ba3c', '--mem', '100b=5', '--mem', '100d=ac44', '--mem', '1017=2']
NOWRITE = [r'!OverwriteSink', r'!SinkMap', r'!SinkClaim', r'!SinkFlush', r'!PartitionSetMessageDigest', r'!SinkClose', r'!TransformStart', r'!KalimbaSendMessage']

SCEN = [
    ('word 0x0ba3c = 47676 is spoken 4 7 6 7 6 (ids 0x2b 0x2e 0x2d 0x2e 0x2d), a separator, then the one-digit words 5 and 0, 44100 as 4 4 1 0 0, and the last word 2',
     BASE + ['--press', '0:4004', '--horizon', '400000'] + STRUCT,
     [r'spoken: 0x12@2000, 0x2b@6000, 0x2e@10000, 0x2d@14000, 0x2e@18000, 0x2d@22000, 0x13@26000, 0x2c@30800, 0x13@34800, 0x27@39600, 0x13@43600, '
      r'0x2b@47600, 0x2b@51600, 0x28@55600, 0x27@59600, 0x27@63600, 0x13@67600', r'0x29@151600, 0x13@155600$|0x29@151600, 0x13@155600\s', r'cave messages still pending: 0', r'!violat'] + NOWRITE),
    ('a second press at 20000 ms stops the census (silent); nothing pending afterwards',
     BASE + ['--press', '0:4004', '--press', '20000:4004', '--horizon', '100000'] + STRUCT,
     [r'spoken: 0x12@2000, 0x2b@6000, 0x2e@10000, 0x2d@14000, 0x2e@18000\s*$|spoken: 0x12@2000, 0x2b@6000, 0x2e@10000, 0x2d@14000, 0x2e@18000\n', r'cave messages still pending: 0'] + NOWRITE),
    ('no structure pointer (M[0x72b] = 0): 0x3B "adjust airbuds" at once, nothing armed',
     BASE + ['--press', '0:4004', '--horizon', '20000'], [r'spoken: 0x3b@0', r'cave messages still pending: 0'] + NOWRITE),
    ('any other event is replayed to the stock, nothing spoken',
     ['--entry', '0x3E21D', '--caller-frame', '23', '--world', '--press', '0:4003', '--horizon', '10000'], [r'spoken: \(nothing\)', r'presses: 0 swallowed, 1 replayed']),
    ('the lever: no store reaches the caller\'s saved return address', BASE + ['--press', '0:4004', '--horizon', '30000'] + STRUCT, [r'caller-frame guard: stores to 0x0915, 0x0916 stop the run', r'!STOPPED']),
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
