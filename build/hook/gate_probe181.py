#!/usr/bin/env python3
"""Offline world-model gate for probe181 (docs/deep/offline-2026-10-10/DESIGN.md section 3).

Runs the real probe181 words (build/hook/probe181_words.json, written by
assemble_probe181.py) through tools/cavesim.py's clocked world model, one scripted scenario
per line, and checks each with the simulator's own --expect.  Exit 0 = every scenario holds.

    python build/hook/assemble_probe181.py        # first: writes probe181_words.json
    python build/hook/gate_probe181.py

probe181 = probe180 + 0x1072 word a 8000: the 25 probe180 scenarios are re-run with the chunk counts
re-derived for the 3.0 s period (2622 ms chunk + 378 ms seam), and RATE_CASES add the rate/latch
models (--stock-rate, --latch, --unload-at/--music-resume-at), matched on the world summary's
chunk table because cavesim has no --expect key for rates.

What it covers: START, the loop for N cycles, STOP while a chunk plays, STOP inside the gap
between two chunks, START again after a STOP, a long run, music paused (DSP unloads), DSP
down, Bluetooth teardown, each trap refused on the START and on a rebuild at a seam, a
replayed (non-0x4004) event, a modelled pending poll, and the two ACCEPTED hazard families
(DESIGN section 3 probe179 outcome rows: the port reads free while the tail is still audible
or TransformFromSink reads 0 on a live chunk -> R1 + R4, the probe173 pattern).  Everything
else must report violations=0 (rules R1-R6).

What it cannot cover: MessageCancelFirst is modelled as the header says (TRUE iff a message
with that task and id is pending, then removed).  What the real trap does from a cave is
hypothesis; the press settles it.  The two failure readings (cancel never finds the message;
cancel always TRUE) were run with a scratch copy of the world and are described in the
field-log entry, not here.
"""
import subprocess, sys, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIM = [sys.executable, os.path.join('tools', 'cavesim.py'), 'probe181', '--entry', '0x3E21D']
START = ['--press', '0:4004']


def exp(*kv):
    out = []
    for k in kv:
        out += ['--expect', k]
    return out


CASES = [
    # ---- the loop and the STOP -------------------------------------------------------------
    ('START, loop 3 cycles: a 4th chunk starts (no end of its own), one poll pending, silent',
     START + ['--loop', '3'],
     ['looping=yes', 'violations=0', 'pending=1', 'spoken=', 'swallowed=1', 'replayed=0']),
    ('START, STOP at 4.5 s (chunk 2 playing), START at 30 s, STOP at 44 s (chunk 5 of the 2nd run '
     'playing): DESIGN press plan; 2 + 5 chunks at the 3.0 s period',
     START + ['--press', '4500:4004', '--press', '30000:4004', '--press', '44000:4004',
              '--horizon', '70000'],
     ['chunks=7', 'ended=7', 'spoken=', 'violations=0', 'pending=0', 'swallowed=4', 'replayed=0']),
    ('STOP inside the gap between chunk 1 and 2 (2.8 s): the poll is still pending, so it cancels',
     START + ['--press', '2800:4004', '--horizon', '40000'],
     ['chunks=1', 'ended=1', 'spoken=', 'violations=0', 'pending=0']),
    ('STOP while chunk 1 is playing (1.5 s)',
     START + ['--press', '1500:4004', '--horizon', '40000'],
     ['chunks=1', 'ended=1', 'spoken=', 'violations=0', 'pending=0']),
    ('long run: START, STOP at 100.5 s: 34 chunks (starts at 0, 3, ... 99 s), one poll at a time, '
     'nothing spoken',
     START + ['--press', '100500:4004', '--horizon', '200000', '--events', '4000'],
     ['chunks=34', 'ended=34', 'spoken=', 'violations=0', 'pending=0']),
    ('a modelled pending poll + one press: that press is a STOP, no chunk is built',
     ['--pending', '12@1000', '--press', '0:4004', '--once'],
     ['chunks=0', 'spoken=', 'violations=0', 'pending=0', 'swallowed=1']),
    ('a non-0x4004 event is replayed to the stock, nothing else happens',
     ['--press', '0:4003', '--once'],
     ['chunks=0', 'spoken=', 'violations=0', 'pending=0', 'replayed=1', 'swallowed=0']),
    # ---- the DSP goes away -----------------------------------------------------------------
    ('music PAUSED (unload 100 ms): chunk 1, then 0x21 "call ended" at the first seam, no re-arm',
     START + ['--music', 'paused', '--unload-ms', '100', '--horizon', '60000'],
     ['chunks=1', 'spoken=21', 'violations=0', 'pending=0', 'dsp=unloaded']),
    ('DSP down at START: 0x3E "bluetooth off", nothing built, nothing armed',
     START + ['--dsp', 'down', '--once'],
     ['chunks=0', 'spoken=3e', 'violations=0', 'pending=0', 'dsp=unloaded']),
    ('Bluetooth long press at 1.5 s: chunk cut, the next poll speaks 0x21 and arms nothing',
     START + ['--bt-teardown-at', '1500', '--horizon', '40000'],
     ['chunks=1', 'spoken=21', 'violations=0', 'pending=0', 'dsp=unloaded']),
    ('after that teardown a START press finds no DSP: 0x3E',
     START + ['--bt-teardown-at', '1500', '--press', '20000:4004', '--horizon', '60000'],
     ['chunks=1', 'spoken=21,3e', 'violations=0', 'pending=0']),
    # ---- every refusal on START (port free, speaks, arms nothing) --------------------------
    ('START: StreamKalimbaSink -> 0: 0x10 "and"',
     START + ['--fail', 'StreamKalimbaSink', '--once'],
     ['chunks=0', 'spoken=10', 'violations=0', 'pending=0']),
    ('START: directory FileFind refused: 0x22',
     START + ['--fail', 'FileFind', '--once'],
     ['chunks=0', 'spoken=22', 'violations=0', 'pending=0']),
    ('START: file FileFind refused (2nd call): 0x1B',
     START + ['--fail-after', 'FileFind=2', '--once'],
     ['chunks=0', 'spoken=1b', 'violations=0', 'pending=0']),
    ('START: StreamFileSource refused: 0x24',
     START + ['--fail', 'StreamFileSource', '--once'],
     ['chunks=0', 'spoken=24', 'violations=0', 'pending=0']),
    ('START: TransformAdpcmDecode refused: 0x25',
     START + ['--fail', 'TransformAdpcmDecode', '--once'],
     ['chunks=0', 'spoken=25', 'violations=0', 'pending=0']),
    ('START: TransformStart refused: 0x25',
     START + ['--fail', 'TransformStart', '--once'],
     ['chunks=0', 'spoken=25', 'violations=0', 'pending=0']),
    # ---- the same refusals on a REBUILD at a seam (speaks the same id, re-arms nothing) ----
    ('rebuild: directory FileFind refused (3rd call): 0x22 at the first seam',
     START + ['--fail-after', 'FileFind=3', '--horizon', '60000'],
     ['chunks=1', 'ended=1', 'spoken=22', 'violations=0', 'pending=0']),
    ('rebuild: file FileFind refused (4th call): 0x1B',
     START + ['--fail-after', 'FileFind=4', '--horizon', '60000'],
     ['chunks=1', 'ended=1', 'spoken=1b', 'violations=0', 'pending=0']),
    ('rebuild: StreamFileSource refused (2nd call): 0x24',
     START + ['--fail-after', 'StreamFileSource=2', '--horizon', '60000'],
     ['chunks=1', 'ended=1', 'spoken=24', 'violations=0', 'pending=0']),
    ('rebuild: TransformAdpcmDecode refused (2nd call): 0x25',
     START + ['--fail-after', 'TransformAdpcmDecode=2', '--horizon', '60000'],
     ['chunks=1', 'ended=1', 'spoken=25', 'violations=0', 'pending=0']),
    ('rebuild: TransformStart refused (2nd call): 0x25',
     START + ['--fail-after', 'TransformStart=2', '--horizon', '60000'],
     ['chunks=1', 'ended=1', 'spoken=25', 'violations=0', 'pending=0']),
    ('INHERITED from 179: StreamKalimbaSink -> 0 on the 3rd call (a poll inside chunk 1): 0x10, '
     'loop over; R3 only because the model still holds port 3 (on the machine a 0 sink = DSP gone)',
     START + ['--fail-after', 'StreamKalimbaSink=3', '--horizon', '60000'],
     ['chunks=1', 'ended=1', 'spoken=10', 'rules=R3', 'pending=0']),
    # ---- ACCEPTED hazards (DESIGN probe179 outcome rows; the probe173 pattern) -------------
    ('HAZARD (accepted): the port reads free 900 ms before the audible end -> R1 + R4 at the seam',
     START + ['--loop', '3', '--tail-ms', '900', '--free-edge', 'eof'],
     ['rules=R1,R4', 'looping=yes']),
    ('HAZARD (accepted): TransformFromSink reads 0 on a live chunk -> R1 + R4',
     START + ['--loop', '3', '--fail', 'TransformFromSink'],
     ['rules=R1,R4', 'looping=yes']),
]

# ---- probe181's ONE change: 0x1072 word a = 8000.  The RATE / LATCH models (--stock-rate, --latch,
# --unload-at, --music-resume-at).  cavesim has no --expect key for rates or seams, so these cases
# also match the world summary's chunk table and silence line (regular expressions on stdout).
# Chunk length = 10,486 bytes x 2 samples / rate: 2622 ms at 8000, 2996 ms at 7000, 5243 ms at 4000.
# The tick grid is 1000 ms from the rebuild, so the seam after a 2622 ms chunk is 378 ms.
H5 = ['--press', '13500:4004', '--horizon', '30000']
RATE_CASES = [
    ('RATE: the stock leaves 8000 (default model, late latch): every chunk 8000 Hz / 2622 ms, '
     'start gaps 3000, silences 378 ms, STOP at 13.5 s ends it',
     START + H5,
     ['chunks=5', 'ended=5', 'spoken=', 'violations=0', 'pending=0'],
     [r'#1 start +0 ms .* 8000 Hz .* 2622 ms', r'#5 start +12000 ms .* 8000 Hz .* 2622 ms',
      r'start gaps \(ms\): 3000, 3000, 3000, 3000$', r'next start\): 378, 378, 378, 378$']),
    ('RATE: --latch immediate: identical (8000 sent, 8000 played from chunk 1)',
     START + H5 + ['--latch', 'immediate'],
     ['chunks=5', 'ended=5', 'spoken=', 'violations=0', 'pending=0'],
     [r'#1 start +0 ms .* 8000 Hz .* 2622 ms', r'next start\): 378, 378, 378, 378$']),
    ('RATE: the stock leaves 7000 (late latch): chunk 1 plays at 7000 Hz / 2996 ms (the "about 3 s" '
     'heard in probe177), seam 1 is 4 ms, chunks 2+ at 8000 Hz / 2622 ms',
     START + H5 + ['--stock-rate', '7000'],
     ['chunks=5', 'ended=5', 'spoken=', 'violations=0', 'pending=0'],
     [r'#1 start +0 ms .* 7000 Hz .* 2996 ms', r'#2 start +3000 ms .* 8000 Hz .* 2622 ms',
      r'next start\): 4, 378, 378, 378$']),
    ('RATE: the stock leaves 4000 (late latch): chunk 1 5243 ms, tick at 5 s still busy, seam 757 ms, '
     'then 3000 ms period',
     START + ['--press', '13500:4004', '--horizon', '30000', '--stock-rate', '4000'],
     ['chunks=4', 'ended=4', 'spoken=', 'violations=0', 'pending=0'],
     [r'#1 start +0 ms .* 4000 Hz .* 5243 ms', r'#2 start +6000 ms .* 8000 Hz .* 2622 ms',
      r'next start\): 757, 378, 378$']),
    ('RATE: --stock-rate 7000 --latch immediate: the sent 8000 is honoured from chunk 1',
     START + H5 + ['--stock-rate', '7000', '--latch', 'immediate'],
     ['chunks=5', 'ended=5', 'spoken=', 'violations=0', 'pending=0'],
     [r'#1 start +0 ms .* 8000 Hz .* 2622 ms', r'next start\): 378, 378, 378, 378$']),
    ('RATE: two sessions, DSP unloaded at 8 s and reloaded at 10 s (stock 7000 again): the 2nd '
     'session starts again with a 7000 Hz / 2996 ms chunk, then 8000 Hz',
     START + ['--press', '4000:4004', '--unload-at', '8000', '--music-resume-at', '10000',
              '--press', '15000:4004', '--press', '19000:4004', '--horizon', '40000',
              '--stock-rate', '7000'],
     ['chunks=4', 'ended=4', 'spoken=', 'violations=0', 'pending=0', 'dsp=loaded'],
     [r'#3 start +15000 ms .* 7000 Hz .* 2996 ms', r'#4 start +18000 ms .* 8000 Hz .* 2622 ms']),
]


def main():
    bad = 0
    for case in CASES + RATE_CASES:
        name, args, expects = case[:3]
        pats = case[3] if len(case) > 3 else []
        cmd = SIM + args + exp(*expects)
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)
        got = [l for l in r.stdout.splitlines() if l.startswith('expect ')]
        ok = r.returncode == 0 and len(got) == len(expects) and all(l.endswith('PASS') for l in got)
        for pat in pats:
            if not re.search(pat, r.stdout, re.M):
                ok = False
                got.append('expect output %r FAIL' % pat)
        print('%-4s %s' % ('PASS' if ok else 'FAIL', name))
        if not ok:
            bad += 1
            print('     cmd: ' + ' '.join(cmd[2:]))
            for l in got:
                if not l.endswith('PASS'):
                    print('     ' + l)
            if r.returncode and not got:
                print((r.stdout + r.stderr)[-600:])
    print('%d scenarios, %d failed' % (len(CASES) + len(RATE_CASES), bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
