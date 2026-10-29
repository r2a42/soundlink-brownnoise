#!/usr/bin/env python3
"""Offline world-model gate for probe181p (the 200 ms seam image; J-T11, 2026-10-12).

Runs the real probe181p words (build/hook/probe181p_words.json, written by
assemble_probe181p.py) through tools/cavesim.py's clocked world model, one scripted scenario
per line, and checks each with the simulator's own --expect.  Exit 0 = every scenario holds.

    python build/hook/assemble_probe181p.py       # first: writes probe181p_words.json
    python build/hook/gate_probe181p.py

probe181p = probe181 with POLL_MS 1000 -> 200 (one immediate, two words).  The 31 probe181 scenarios are
re-run with every expectation re-derived for the 200 ms tick grid: chunk 2622 ms, the first tick at or after
the free edge is the next multiple of 200 ms from the (re)arm, so the zero-latency model gives a start gap of
2800 ms and a 178 ms silence (the 1000 ms image gave 3000 ms and 378 ms).  Press times are not on a tick or a
chunk boundary.  Added scenarios (SEAM_CASES): the grid itself, STOP either side of the free edge, and the
lead cases.

What it covers and what it cannot cover: exactly as gate_probe181.py.  The model has zero VM latency and no
0x1072 purge and no lead L unless --tail-ms is given, so it cannot say what the speaker will play at a seam.
That is the question the press asks (tools/seammodel.py prices it with assumed parameters).
"""
import subprocess, sys, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIM = [sys.executable, os.path.join('tools', 'cavesim.py'), 'probe181p', '--entry', '0x3E21D']
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
    ('START, STOP at 4.5 s (chunk 2 playing), START at 30 s, STOP at 43.5 s (chunk 5 of the 2nd run '
     'playing): DESIGN press plan; 2 + 5 chunks at the 2.8 s period',
     START + ['--press', '4500:4004', '--press', '30000:4004', '--press', '43500:4004',
              '--horizon', '70000'],
     ['chunks=7', 'ended=7', 'spoken=', 'violations=0', 'pending=0', 'swallowed=4', 'replayed=0']),
    ('STOP inside the gap between chunk 1 and 2 (2.7 s; chunk 1 ends 2622 ms, the rebuild tick is at 2.8 s): '
     'the poll is still pending, so it cancels',
     START + ['--press', '2700:4004', '--horizon', '40000'],
     ['chunks=1', 'ended=1', 'spoken=', 'violations=0', 'pending=0']),
    ('STOP while chunk 1 is playing (1.5 s)',
     START + ['--press', '1500:4004', '--horizon', '40000'],
     ['chunks=1', 'ended=1', 'spoken=', 'violations=0', 'pending=0']),
    ('long run: START, STOP at 50.5 s: 19 chunks (starts at 0, 2.8, ... 50.4 s), one poll at a time, '
     'nothing spoken',
     START + ['--press', '50500:4004', '--horizon', '100000', '--events', '3000'],
     ['chunks=19', 'ended=19', 'spoken=', 'violations=0', 'pending=0']),
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
    ('rebuild: directory FileFind refused (3rd call): 0x22 at the first seam (2.8 s)',
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
     'start gaps 2800, silences 178 ms, STOP at 13.5 s ends it',
     START + H5,
     ['chunks=5', 'ended=5', 'spoken=', 'violations=0', 'pending=0'],
     [r'#1 start +0 ms .* 8000 Hz .* 2622 ms', r'#5 start +11200 ms .* 8000 Hz .* 2622 ms',
      r'start gaps \(ms\): 2800, 2800, 2800, 2800$', r'next start\): 178, 178, 178, 178$']),
    ('RATE: --latch immediate: identical (8000 sent, 8000 played from chunk 1)',
     START + H5 + ['--latch', 'immediate'],
     ['chunks=5', 'ended=5', 'spoken=', 'violations=0', 'pending=0'],
     [r'#1 start +0 ms .* 8000 Hz .* 2622 ms', r'next start\): 178, 178, 178, 178$']),
    ('RATE: the stock leaves 7000 (late latch): chunk 1 plays at 7000 Hz / 2996 ms (the "about 3 s" '
     'heard in probe177), seam 1 is 4 ms (tick at 3.0 s), chunks 2+ at 8000 Hz / 2622 ms',
     START + H5 + ['--stock-rate', '7000'],
     ['chunks=5', 'ended=5', 'spoken=', 'violations=0', 'pending=0'],
     [r'#1 start +0 ms .* 7000 Hz .* 2996 ms', r'#2 start +3000 ms .* 8000 Hz .* 2622 ms',
      r'next start\): 4, 178, 178, 178$']),
    ('RATE: the stock leaves 4000 (late latch): chunk 1 5243 ms, first free tick at 5.4 s, seam 157 ms, '
     'then 2800 ms period',
     START + ['--press', '13500:4004', '--horizon', '30000', '--stock-rate', '4000'],
     ['chunks=4', 'ended=4', 'spoken=', 'violations=0', 'pending=0'],
     [r'#1 start +0 ms .* 4000 Hz .* 5243 ms', r'#2 start +5400 ms .* 8000 Hz .* 2622 ms',
      r'next start\): 157, 178, 178$']),
    ('RATE: --stock-rate 7000 --latch immediate: the sent 8000 is honoured from chunk 1',
     START + H5 + ['--stock-rate', '7000', '--latch', 'immediate'],
     ['chunks=5', 'ended=5', 'spoken=', 'violations=0', 'pending=0'],
     [r'#1 start +0 ms .* 8000 Hz .* 2622 ms', r'next start\): 178, 178, 178, 178$']),
    ('RATE: two sessions, DSP unloaded at 8 s and reloaded at 10 s (stock 7000 again): the 2nd '
     'session starts again with a 7000 Hz / 2996 ms chunk, then 8000 Hz',
     START + ['--press', '4000:4004', '--unload-at', '8000', '--music-resume-at', '10000',
              '--press', '15000:4004', '--press', '19000:4004', '--horizon', '40000',
              '--stock-rate', '7000'],
     ['chunks=4', 'ended=4', 'spoken=', 'violations=0', 'pending=0', 'dsp=loaded'],
     [r'#3 start +15000 ms .* 7000 Hz .* 2996 ms', r'#4 start +18000 ms .* 8000 Hz .* 2622 ms']),
]

# ---- probe181p's own scenarios: the 200 ms grid itself (chunk 2622 ms, first tick at or after the free edge)
SEAM_CASES = [
    ('SEAM: 3 cycles: starts 0, 2800, 5600 ms; silences 178 ms; ONE poll pending; R5 (poll >= 50 ms) holds',
     START + ['--loop', '3'],
     ['looping=yes', 'violations=0', 'pending=1', 'spoken='],
     [r'#2 start +2800 ms', r'#3 start +5600 ms', r'next start\): 178, 178, 178$']),
    ('SEAM: STOP at 2.5 s (last busy read before the free edge): chunk 1 only, nothing pending',
     START + ['--press', '2500:4004', '--horizon', '20000'],
     ['chunks=1', 'ended=1', 'spoken=', 'violations=0', 'pending=0']),
    ('SEAM: STOP at 2.9 s (just after the rebuild tick at 2.8 s): chunk 2 is already playing, '
     'STOP cancels the poll, chunk 2 plays out',
     START + ['--press', '2900:4004', '--horizon', '20000'],
     ['chunks=2', 'ended=2', 'spoken=', 'violations=0', 'pending=0']),
    ('SEAM: a 10 ms lead (--free-edge eof --tail-ms 10): EOF at 2612, the tick at 2.6 s reads busy, the tick at '
     '2.8 s rebuilds after the audible end: no hazard rule fires',
     START + ['--loop', '3', '--tail-ms', '10', '--free-edge', 'eof'],
     ['looping=yes', 'violations=0', 'pending=1', 'spoken=']),
    ('SEAM: a 30 ms lead (--free-edge eof --tail-ms 30): EOF at 2592, the tick at 2.6 s reads FREE while 22 ms of '
     'tail are still audible -> R1 + R4 (the accepted hazard) at EVERY seam, start gaps 2600 ms: at P = 200 any '
     'lead above 22 ms makes the rebuild land in the tail',
     START + ['--loop', '3', '--tail-ms', '30', '--free-edge', 'eof'],
     ['rules=R1,R4', 'looping=yes'],
     [r'start gaps \(ms\): 2600, 2600, 2600$', r'next start\): -22, -22, -22$']),
    ('SEAM: a 200 ms lead (--free-edge eof --tail-ms 200): the tick at 2.8 s lands inside the audible tail '
     '-> R1 + R4 (the accepted probe173-pattern hazard; here it is the lead, priced by seammodel.py)',
     START + ['--loop', '3', '--tail-ms', '200', '--free-edge', 'eof'],
     ['rules=R1,R4', 'looping=yes']),
]


def main():
    bad = 0
    for case in CASES + RATE_CASES + SEAM_CASES:
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
    print('%d scenarios, %d failed' % (len(CASES) + len(RATE_CASES) + len(SEAM_CASES), bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
