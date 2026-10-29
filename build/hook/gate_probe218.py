#!/usr/bin/env python3
"""Offline gate for probe218 (the DSP-without-a-stream experiment: a fabricated AUDIO_PLUGIN_CONNECT to the stock decoder plugin 0xCBCF, then reports, then DISCONNECT). Pure emulation (tools/cavesim.py, the clocked world); no device. The stock plugin is NOT simulated: the model only records that the messages were sent.
    python build/hook/assemble_probe218.py      # first (writes probe218_words.json)
    python build/hook/gate_probe218.py"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
WORDS = os.path.join(HERE, 'probe218_words.json')
BASE = ['--entry', '0x3E21D', '--caller-frame', '23', '--world', '--music', 'playing', '--steps', '400000000', '--audio-busy']
NOWRITE = [r'!OverwriteSink', r'!SinkMap', r'!SinkClaim', r'!SinkFlush', r'!PartitionSetMessageDigest', r'!SinkClose', r'!TransformStart']
SCEN = [
    ('event 0x4753 at 0: AUTO at 10000: ONE CONNECT (0x7000 to 0xcbcf) after a malloc of 13 words, ticks at 14000 .. 31500, ONE DISCONNECT (0x7001) at 24500; spoken 0x27 (no instance in the model), 0x29 (busy zero), 0x2c (gate TRUE), 0x13 (clean)',
     BASE + ['--press', '0:4753', '--horizon', '40000'],
     [r'PanicUnlessMalloc +AL=0x000d', r'MessageSendLater +AL=0xcbcf AH=0x7000', r'MessageSendLater +AL=0xcbcf AH=0x7001', r'spoken: 0x27@14000, 0x29@17500, 0x2c@21000, 0x13@28000',
      r'presses: 0 swallowed, 1 replayed', r'cave messages still pending: 0', r'!violat'] + NOWRITE),
    ('the plugin holds the busy word (0xcbcf): reported busy nonzero (0x2a) and unclean (0x12), then the cleanup clears it (SetAudioBusy(0) at the last tick)',
     BASE + ['--busy-init', 'cbcf', '--press', '0:4753', '--horizon', '40000'],
     [r'spoken: 0x27@14000, 0x2a@17500, 0x2c@21000, 0x12@28000', r'audio busy: now 0x0000; SetAudioBusy calls: 0@31500', r'cave messages still pending: 0'] + NOWRITE),
    ('another owner holds the busy word (0x1234): reported nonzero, NEVER cleared by the cave',
     BASE + ['--busy-init', '1234', '--press', '0:4753', '--horizon', '40000'],
     [r'spoken: 0x27@14000, 0x2a@17500, 0x2c@21000, 0x12@28000', r'audio busy: now 0x1234; SetAudioBusy calls: none', r'cave messages still pending: 0'] + NOWRITE),
    ('a decoder instance already exists (@0x72f nonzero: a stream is up): refused at once, 0x3B at 10000, NOTHING sent to the plugin',
     BASE + ['--mem', '72f=1000', '--press', '0:4753', '--horizon', '40000'],
     [r'spoken: 0x3b@10000$|spoken: 0x3b@10000\n', r'!AH=0x7000', r'!AH=0x7001', r'cave messages still pending: 0'] + NOWRITE),
    ('other events (0x4742, 0x4715, 0x4003, 0x4004) are replayed and arm nothing',
     BASE + ['--press', '0:4742', '--press', '50:4715', '--press', '90:4003', '--press', '120:4004', '--horizon', '30000'],
     [r'spoken: \(nothing\)', r'presses: 0 swallowed, 4 replayed', r'cave messages still pending: 0', r'!AH=0x7000'] + NOWRITE),
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
