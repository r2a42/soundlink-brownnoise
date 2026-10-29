#!/usr/bin/env python3
"""Offline gate for probe216 (the READ-ONLY volume readout: the decoder instance field M[0x72f] + 11, spoken again and again). Pure emulation (tools/cavesim.py, the clocked world); no device.
    python build/hook/assemble_probe216.py      # first (writes probe216_words.json)
    python build/hook/gate_probe216.py
Every row greps the simulator report with regular expressions (a leading ! means: must NOT match). The master value -720 (0xFD30 = 64816 unsigned) reads 6 4 8 1 6, check 5."""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
WORDS = os.path.join(HERE, 'probe216_words.json')
BASE = ['--entry', '0x3E21D', '--caller-frame', '23', '--world', '--music', 'playing', '--steps', '400000000']
PTR = ['--mem', '72f=1000', '--mem', '100b=fd30']
NOWRITE = [r'!OverwriteSink', r'!SinkMap', r'!SinkClaim', r'!SinkFlush', r'!PartitionSetMessageDigest', r'!SinkClose', r'!TransformStart', r'!KalimbaSendMessage']

SCEN = [
    ('event 0x4758 at 0: the readout starts 12 s later (cue 0x12 at 14000), speaks 64816 as 6 4 8 1 6, check 5, separator, then repeats by itself (second cue at 44000)',
     BASE + ['--press', '0:4758', '--horizon', '60000'] + PTR,
     [r'spoken: 0x12@14000, 0x2d@17500, 0x2b@21000, 0x2f@24500, 0x28@28000, 0x2d@31500, 0x2c@35000, 0x13@38500, 0x12@44000', r'presses: 0 swallowed, 1 replayed', r'!violat'] + NOWRITE),
    ('the value changes at 40000 ms (-720 to -512 = 65024 = 6 5 0 2 4, check 7): the next reading speaks the new value',
     BASE + ['--press', '0:4758', '--mem-at', '40000:100b=fe00', '--horizon', '70000'] + PTR,
     [r'0x12@44000, 0x2d@47500, 0x2c@51000, 0x27@54500, 0x29@58000, 0x2b@61500, 0x2e@65000, 0x13@68500', r'!violat'] + NOWRITE),
    ('the decoder pointer goes to zero at 40000 ms (the DSP unloaded): the next cycle says 0x3B once at 42000 and the loop ends (nothing pending)',
     BASE + ['--press', '0:4758', '--mem-at', '40000:72f=0', '--horizon', '90000'] + PTR,
     [r'0x13@38500, 0x3b@42000\s*$|0x13@38500, 0x3b@42000\n', r'cave messages still pending: 0'] + NOWRITE),
    ('no decoder pointer at the start: 0x3B at 12000, nothing armed',
     BASE + ['--press', '0:4758', '--horizon', '40000'], [r'spoken: 0x3b@12000', r'cave messages still pending: 0'] + NOWRITE),
    ('two events 0x4758 at 0 and 3000 ms: ONE start (debounced) at 15000 (cue at 17000)',
     BASE + ['--press', '0:4758', '--press', '3000:4758', '--horizon', '30000'] + PTR, [r'spoken: 0x12@17000', r'presses: 0 swallowed, 2 replayed'] + NOWRITE),
    ('the centre long press starts the readout (cue at 2000) and a second press at 20000 stops it (silent, nothing pending)',
     BASE + ['--press', '0:4004', '--press', '20000:4004', '--horizon', '60000'] + PTR, [r'spoken: 0x12@2000, 0x2d@5500', r'presses: 2 swallowed, 0 replayed', r'cave messages still pending: 0'] + NOWRITE),
    ('other events (0x4742, 0x4003, 0x400d) are replayed and arm nothing',
     BASE + ['--press', '0:4742', '--press', '50:4003', '--press', '100:400d', '--horizon', '30000'] + PTR, [r'spoken: \(nothing\)', r'presses: 0 swallowed, 3 replayed', r'cave messages still pending: 0'] + NOWRITE),
    ('the lever: no store reaches the caller saved return address',
     BASE + ['--press', '0:4758', '--horizon', '40000'] + PTR, [r'caller-frame guard: stores to 0x0915, 0x0916 stop the run', r'!STOPPED']),
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
