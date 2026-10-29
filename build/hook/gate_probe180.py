#!/usr/bin/env python3
"""Offline world-model gate for probe180 (docs/deep/offline-2026-10-10/DESIGN.md section 3).

Runs the real probe180 words (build/hook/probe180_words.json, written by
assemble_probe180.py) through tools/cavesim.py's clocked world model, one scripted scenario
per line, and checks each with the simulator's own --expect.  Exit 0 = every scenario holds.

    python build/hook/assemble_probe180.py        # first: writes probe180_words.json
    python build/hook/gate_probe180.py

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
import subprocess, sys, os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIM = [sys.executable, os.path.join('tools', 'cavesim.py'), 'probe180', '--entry', '0x3E21D']
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
    ('START, STOP at 4.5 s (chunk 2 playing), START at 30 s, STOP at 45 s: DESIGN press plan',
     START + ['--press', '4500:4004', '--press', '30000:4004', '--press', '45000:4004',
              '--horizon', '70000'],
     ['chunks=4', 'ended=4', 'spoken=', 'violations=0', 'pending=0', 'swallowed=4', 'replayed=0']),
    ('STOP inside the gap between chunk 1 and 2 (2.8 s): the poll is still pending, so it cancels',
     START + ['--press', '2800:4004', '--horizon', '40000'],
     ['chunks=1', 'ended=1', 'spoken=', 'violations=0', 'pending=0']),
    ('STOP while chunk 1 is playing (1.5 s)',
     START + ['--press', '1500:4004', '--horizon', '40000'],
     ['chunks=1', 'ended=1', 'spoken=', 'violations=0', 'pending=0']),
    ('long run: START, STOP at 100 s: 10 chunks, one poll at a time, nothing spoken',
     START + ['--press', '100000:4004', '--horizon', '200000', '--events', '2000'],
     ['chunks=10', 'ended=10', 'spoken=', 'violations=0', 'pending=0']),
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


def main():
    bad = 0
    for name, args, expects in CASES:
        cmd = SIM + args + exp(*expects)
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)
        got = [l for l in r.stdout.splitlines() if l.startswith('expect ')]
        ok = r.returncode == 0 and len(got) == len(expects) and all(l.endswith('PASS') for l in got)
        print('%-4s %s' % ('PASS' if ok else 'FAIL', name))
        if not ok:
            bad += 1
            print('     cmd: ' + ' '.join(cmd[2:]))
            for l in got:
                if not l.endswith('PASS'):
                    print('     ' + l)
            if r.returncode and not got:
                print((r.stdout + r.stderr)[-600:])
    print('%d scenarios, %d failed' % (len(CASES), bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
