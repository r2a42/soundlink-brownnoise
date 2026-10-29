#!/usr/bin/env python3
"""Offline gate for probe219 (the invalid-handle micro-test). Pure emulation (tools/cavesim.py, the clocked world); no device. The stock plugin is NOT simulated: the model only records that the messages were sent.
    python build/hook/assemble_probe219.py      # first (writes probe219_words.json)
    python build/hook/gate_probe219.py"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
WORDS = os.path.join(HERE, 'probe219_words.json')
BASE = ['--entry', '0x3E21D', '--caller-frame', '23', '--world', '--music', 'playing', '--steps', '400000000', '--audio-busy']
NOWRITE = [r'!OverwriteSink', r'!SinkMap', r'!SinkClaim', r'!SinkFlush', r'!PartitionSetMessageDigest', r'!SinkClose', r'!TransformStart']
SCEN = [
    ('event 0x4753 at 0: AUTO at 10000, ticks 11000 .. 25000 in 3500 steps: the markers 0x28 .. 0x2c, in order, ONE invalid-id message (0x7019) to 0xcbcf, StreamSourceFromSink(0), StreamDisconnect(0,0), then the USB endpoint 2 pair; nothing pending afterwards',
     BASE + ['--press', '0:4753', '--horizon', '40000'],
     [r'spoken: 0x28@11000, 0x29@14500, 0x2a@18000, 0x2b@21500, 0x2c@25000', r'MessageSendLater +AL=0xcbcf AH=0x7019', r'!AH=0x7000', r'!AH=0x7001',
      r'StreamSourceFromSink +AL=0x0000', r'StreamDisconnect +AL=0x0000 AH=0x0000', r'StreamUsbEndPointSink +AL=0x0002',
      r'presses: 0 swallowed, 1 replayed', r'cave messages still pending: 0', r'!violat'] + NOWRITE),
    ('other events (0x4742, 0x4715, 0x4003, 0x4004) are replayed and arm nothing',
     BASE + ['--press', '0:4742', '--press', '50:4715', '--press', '90:4003', '--press', '120:4004', '--horizon', '30000'],
     [r'spoken: \(nothing\)', r'presses: 0 swallowed, 4 replayed', r'cave messages still pending: 0', r'!AH=0x7019'] + NOWRITE),
    ('the lever: no store reaches the caller saved return address',
     BASE + ['--press', '0:4753', '--horizon', '40000'], [r'caller-frame guard: stores to 0x0915, 0x0916 stop the run', r'!STOPPED']),
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
