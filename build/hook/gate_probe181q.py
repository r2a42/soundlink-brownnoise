#!/usr/bin/env python3
"""Offline world-model gate for the poll variants of probe181p: probe181q100 (POLL_MS 100) and probe181q50
(POLL_MS 50).  Also runs on probe181p itself (POLL_MS 200) as a check of this file's own arithmetic: the generated
P = 200 scenario set passes on 181p's words.  It is NOT gate_probe181p.py: press times, one session gap and the
paused-music unload time differ (below), so a pass here is not a rerun of that gate.
(B3, round 3, 2026-10-12; built offline, NOT flashed.)

    python build/hook/assemble_probe181q100.py   # first: writes probe181q100_words.json (and --build the dfu)
    python build/hook/gate_probe181q.py probe181q100 [-j 8] [--only TEXT] [--list]
    python build/hook/gate_probe181q.py probe181q50  -j 8
    python build/hook/gate_probe181q.py probe181p    -j 8      # P = 200: the generator run on 181p's own words (a check)

Runs the real words of the named image (build/hook/<name>_words.json) through tools/cavesim.py's clocked world
model, one scripted scenario per line, each checked with the simulator's own --expect (plus regular expressions on
the world summary for the rate and seam tables).  Exit 0 = every scenario holds.  Scenarios are independent
processes, so -j N runs them in parallel (gate_probe181p took 520 s serially at P = 200; at P = 50 there are four
times as many ticks to simulate, which is why this gate takes -j and why the Bash tool's 600 s cap is not a limit).

What the expectations are: gate_probe181p's, re-derived from the tick grid.  With the zero-latency model:
  D  = 2622 ms (10,486 bytes x 2 samples / 8000 Hz, rounded as cavesim prints it)
  S  = ceil(D / P) * P     the start-to-start period (the first tick at or after the free edge, ticks every P ms
                           from the (re)arm): 2800 (P 200), 2700 (P 100), 2650 (P 50)
  SIL = S - D              the silence between chunks: 178, 78, 28 ms
Two things differ from gate_probe181p besides the numbers:
  1. Press times are moved OFF every tick grid.  181p's times (1500, 2500, 4500, 13500, 30000, 50500 ...) are
     multiples of 100 and 50, so at P = 100 or 50 the press and a tick would tie in the model (the order of a press
     and a tick at the same millisecond is not a property of the speaker).  The times used here end in 17, and
     the gap between the second START and the second STOP is 13,370 ms (43,500 - 30,000 = 13,500 is 5 x 2,700 and
     would tie with a chunk start at P = 100).  The paused-music case moves its DSP unload time so that it still
     precedes the first free tick (100 ms for P = 200, 38 ms for P = 100); at P = 50 the first free tick (2650 ms)
     comes BEFORE the modelled 0x1080 (2652 ms), so chunk 2 is built and the 0x21 comes at the second seam.
  2. The event cap (--events, default 400 in the clocked world) is raised to 20000, because a 50 ms poll makes 53
     cave runs per chunk.
What it covers and what it cannot cover: exactly as gate_probe181p.py.  The model has zero VM latency, no 0x1072
purge and no lead L unless --tail-ms is given, so it cannot say what the speaker will play at a seam; that is the
question of the press (tools/seammodel.py prices it with assumed parameters; B03 note).  Because the model has no
a_busy, its hazard threshold is 22 ms for P = 200, 100 and 50 alike (2622 mod 100 = 22, and 2600 is a tick of
every grid); the seam model, which counts a_busy per busy read, puts the thresholds at about 25, 12 and 37 ms.
"""
import argparse, math, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
POLLS = {'probe181p': 200, 'probe181q100': 100, 'probe181q50': 50}
D = 2622
EV = ['--events', '20000']
T_ODD = 17          # added to every press time so that no press ties with a tick or a chunk start


def exp(*kv):
    out = []
    for k in kv:
        out += ['--expect', k]
    return out


def cdiv(a, b):
    return -(-a // b)


def build_cases(P):
    S = cdiv(D, P) * P
    SIL = S - D
    START = ['--press', '0:4004']

    def starts_before(T, t0=0):
        """chunks that started before a press at T (T not on the grid): t0 + k*S < T."""
        return cdiv(T - t0, S)

    def pat_list(vals, tail='$'):
        return r'\): ' + ', '.join(str(v) for v in vals) + tail

    # ---- 1. the loop and the STOP ------------------------------------------------------------------
    T1, T2 = 4500 + T_ODD, 30000 + T_ODD
    T3 = T2 + 13370      # 13370 is no multiple of 2800, 2700 or 2650 (43500 - 30000 = 13500 = 5 x 2700 would tie at P = 100)
    n_two = starts_before(T1) + starts_before(T3, T2)
    Tg = D + SIL // 2                 # inside the gap between chunk 1's audible end and the rebuild tick
    Tlong = 50500 + T_ODD
    n_long = starts_before(Tlong)
    # music PAUSED: the world unloads the DSP --unload-ms after the chunk's 0x1080 (audible end 2622 + 30 ms
    # tone-end).  181p: 100 ms, before its first free tick at 2800.  At 100 ms the first free tick is 2700, so the
    # unload must come sooner (18 ms); at 50 ms the first free tick (2650) is BEFORE the 0x1080 (2652): chunk 2 is
    # built before the DSP goes, and the 0x21 comes at the second seam.
    um = min(100, S - D - 30 - 10)
    if um < 5:
        um = 20
    n_pause = 1 if S > D + 30 + um else 2
    PAUSED_CASE = (
        'music PAUSED (unload %d ms after the 0x1080 at 2652): %s' % (
            um, 'chunk 1, then 0x21 "call ended" at the first seam (%d ms), no re-arm' % S if n_pause == 1 else
            'the first free tick (%d ms) is BEFORE the 0x1080, so chunk 2 is built; 0x21 at the second seam, no re-arm' % S),
        START + ['--music', 'paused', '--unload-ms', str(um), '--horizon', '60000'],
        ['chunks=%d' % n_pause, 'spoken=21', 'violations=0', 'pending=0', 'dsp=unloaded'])
    CASES = [
        ('START, loop 3 cycles: a 4th chunk starts (no end of its own), one poll pending, silent',
         START + ['--loop', '3'],
         ['looping=yes', 'violations=0', 'pending=1', 'spoken=', 'swallowed=1', 'replayed=0']),
        ('START, STOP at %.3f s, START at %.3f s, STOP at %.3f s: DESIGN press plan; %d chunks in all at the %.3f s '
         'period' % (T1 / 1000, T2 / 1000, T3 / 1000, n_two, S / 1000),
         START + ['--press', '%d:4004' % T1, '--press', '%d:4004' % T2, '--press', '%d:4004' % T3,
                  '--horizon', '70000'],
         ['chunks=%d' % n_two, 'ended=%d' % n_two, 'spoken=', 'violations=0', 'pending=0', 'swallowed=4',
          'replayed=0']),
        ('STOP inside the gap between chunk 1 and 2 (%d ms; chunk 1 ends 2622 ms, the rebuild tick is at %d ms): '
         'the poll is still pending, so it cancels' % (Tg, S),
         START + ['--press', '%d:4004' % Tg, '--horizon', '40000'],
         ['chunks=1', 'ended=1', 'spoken=', 'violations=0', 'pending=0']),
        ('STOP while chunk 1 is playing (1.517 s)',
         START + ['--press', '%d:4004' % (1500 + T_ODD), '--horizon', '40000'],
         ['chunks=1', 'ended=1', 'spoken=', 'violations=0', 'pending=0']),
        ('long run: START, STOP at %.3f s: %d chunks (starts at 0, %.2f, ... s), one poll at a time, nothing spoken'
         % (Tlong / 1000, n_long, S / 1000),
         START + ['--press', '%d:4004' % Tlong, '--horizon', '100000'],
         ['chunks=%d' % n_long, 'ended=%d' % n_long, 'spoken=', 'violations=0', 'pending=0']),
        ('a modelled pending poll + one press: that press is a STOP, no chunk is built',
         ['--pending', '12@1000', '--press', '0:4004', '--once'],
         ['chunks=0', 'spoken=', 'violations=0', 'pending=0', 'swallowed=1']),
        ('a non-0x4004 event is replayed to the stock, nothing else happens',
         ['--press', '0:4003', '--once'],
         ['chunks=0', 'spoken=', 'violations=0', 'pending=0', 'replayed=1', 'swallowed=0']),
        # ---- 2. the DSP goes away -------------------------------------------------------------------
        PAUSED_CASE,
        ('DSP down at START: 0x3E "bluetooth off", nothing built, nothing armed',
         START + ['--dsp', 'down', '--once'],
         ['chunks=0', 'spoken=3e', 'violations=0', 'pending=0', 'dsp=unloaded']),
        ('Bluetooth long press at %.3f s: chunk cut, the next poll speaks 0x21 and arms nothing' % (1.5 + T_ODD / 1000),
         START + ['--bt-teardown-at', str(1500 + T_ODD), '--horizon', '40000'],
         ['chunks=1', 'spoken=21', 'violations=0', 'pending=0', 'dsp=unloaded']),
        ('after that teardown a START press finds no DSP: 0x3E',
         START + ['--bt-teardown-at', str(1500 + T_ODD), '--press', '%d:4004' % (20000 + T_ODD), '--horizon', '60000'],
         ['chunks=1', 'spoken=21,3e', 'violations=0', 'pending=0']),
        # ---- 3. every refusal on START (port free, speaks, arms nothing) ----------------------------
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
        # ---- 4. the same refusals on a REBUILD at a seam (speaks the same id, re-arms nothing) ------
        ('rebuild: directory FileFind refused (3rd call): 0x22 at the first seam (%d ms)' % S,
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
        ('INHERITED from 179: StreamKalimbaSink -> 0 on the 3rd call (a poll inside chunk 1): 0x10, loop over; '
         'R3 only because the model still holds port 3 (on the machine a 0 sink = DSP gone)',
         START + ['--fail-after', 'StreamKalimbaSink=3', '--horizon', '60000'],
         ['chunks=1', 'ended=1', 'spoken=10', 'rules=R3', 'pending=0']),
        # ---- 5. ACCEPTED hazards (DESIGN probe179 outcome rows; the probe173 pattern) ---------------
        ('HAZARD (accepted): the port reads free 900 ms before the audible end -> R1 + R4 at the seam',
         START + ['--loop', '3', '--tail-ms', '900', '--free-edge', 'eof'],
         ['rules=R1,R4', 'looping=yes']),
        ('HAZARD (accepted): TransformFromSink reads 0 on a live chunk -> R1 + R4',
         START + ['--loop', '3', '--fail', 'TransformFromSink'],
         ['rules=R1,R4', 'looping=yes']),
    ]

    # ---- 6. RATE / LATCH models (probe181's own: --stock-rate, --latch).  Chunk length = 10,486 x 2 / rate.
    H5T = 13500 + T_ODD
    H5 = ['--press', '%d:4004' % H5T, '--horizon', '30000']
    n5 = starts_before(H5T)

    def sgaps(n, vals_first=None):
        v = ([vals_first] if vals_first is not None else []) + [S] * (n - 1 - (1 if vals_first is not None else 0))
        return v

    def gaps_pat(first, n):
        """start gaps S repeated: chunk 1 gap `first`, then S"""
        return pat_list([first] + [S] * (n - 2))

    def sil_pat(first, n):
        return pat_list([first] + [SIL] * (n - 2))

    RATE_CASES = [
        ('RATE: the stock leaves 8000 (default model, late latch): every chunk 8000 Hz / 2622 ms, start gaps %d, '
         'silences %d ms, STOP at %.3f s ends it' % (S, SIL, H5T / 1000),
         START + H5,
         ['chunks=%d' % n5, 'ended=%d' % n5, 'spoken=', 'violations=0', 'pending=0'],
         [r'#1 start +0 ms .* 8000 Hz .* 2622 ms', r'#%d start +%d ms .* 8000 Hz .* 2622 ms' % (n5, (n5 - 1) * S),
          r'start gaps \(ms\): ' + ', '.join([str(S)] * (n5 - 1)) + '$',
          r'next start\): ' + ', '.join([str(SIL)] * (n5 - 1)) + '$']),
        ('RATE: --latch immediate: identical (8000 sent, 8000 played from chunk 1)',
         START + H5 + ['--latch', 'immediate'],
         ['chunks=%d' % n5, 'ended=%d' % n5, 'spoken=', 'violations=0', 'pending=0'],
         [r'#1 start +0 ms .* 8000 Hz .* 2622 ms', r'next start\): ' + ', '.join([str(SIL)] * (n5 - 1)) + '$']),
    ]
    # stock leaves 7000: chunk 1 = 10486*2/7000 = 2996 ms; the first free tick is 3000 for P in {200, 100, 50}
    F7 = cdiv(2996, P) * P
    n7 = 1 + cdiv(H5T - F7, S)
    RATE_CASES.append(
        ('RATE: the stock leaves 7000 (late latch): chunk 1 plays at 7000 Hz / 2996 ms (the "about 3 s" heard in '
         'probe177), seam 1 is %d ms (tick at %d ms), chunks 2+ at 8000 Hz / 2622 ms' % (F7 - 2996, F7),
         START + H5 + ['--stock-rate', '7000'],
         ['chunks=%d' % n7, 'ended=%d' % n7, 'spoken=', 'violations=0', 'pending=0'],
         [r'#1 start +0 ms .* 7000 Hz .* 2996 ms', r'#2 start +%d ms .* 8000 Hz .* 2622 ms' % F7,
          r'next start\): ' + ', '.join([str(F7 - 2996)] + [str(SIL)] * (n7 - 2)) + '$']))
    # stock leaves 4000: chunk 1 = 5243 ms
    F4 = cdiv(5243, P) * P
    n4 = 1 + cdiv(H5T - F4, S)
    RATE_CASES.append(
        ('RATE: the stock leaves 4000 (late latch): chunk 1 5243 ms, first free tick at %d ms, seam %d ms, then a %d ms '
         'period' % (F4, F4 - 5243, S),
         START + H5 + ['--stock-rate', '4000'],
         ['chunks=%d' % n4, 'ended=%d' % n4, 'spoken=', 'violations=0', 'pending=0'],
         [r'#1 start +0 ms .* 4000 Hz .* 5243 ms', r'#2 start +%d ms .* 8000 Hz .* 2622 ms' % F4,
          r'next start\): ' + ', '.join([str(F4 - 5243)] + [str(SIL)] * (n4 - 2)) + '$']))
    RATE_CASES.append(
        ('RATE: --stock-rate 7000 --latch immediate: the sent 8000 is honoured from chunk 1',
         START + H5 + ['--stock-rate', '7000', '--latch', 'immediate'],
         ['chunks=%d' % n5, 'ended=%d' % n5, 'spoken=', 'violations=0', 'pending=0'],
         [r'#1 start +0 ms .* 8000 Hz .* 2622 ms', r'next start\): ' + ', '.join([str(SIL)] * (n5 - 1)) + '$']))
    p1, p2, p3 = 4000 + T_ODD, 15000 + T_ODD, 19000 + T_ODD
    RATE_CASES.append(
        ('RATE: two sessions, DSP unloaded at 8 s and reloaded at 10 s (stock 7000 again): the 2nd session starts '
         'again with a 7000 Hz / 2996 ms chunk, then 8000 Hz (the first free tick is %d ms after the press)' % F7,
         START + ['--press', str(p1) + ':4004', '--unload-at', '8000', '--music-resume-at', '10000',
                  '--press', str(p2) + ':4004', '--press', str(p3) + ':4004', '--horizon', '40000',
                  '--stock-rate', '7000'],
         ['chunks=4', 'ended=4', 'spoken=', 'violations=0', 'pending=0', 'dsp=loaded'],
         [r'#3 start +%d ms .* 7000 Hz .* 2996 ms' % p2, r'#4 start +%d ms .* 8000 Hz .* 2622 ms' % (p2 + F7)]))

    # ---- 7. this file's own scenarios: the tick grid itself, STOP either side of the free edge, lead cases
    def lead_case(L):
        tick = cdiv(D - L, P) * P          # the first tick at or after the free edge (EOF = D - L)
        hazard = tick < D
        keys = (['rules=R1,R4', 'looping=yes'] if hazard
                else ['looping=yes', 'violations=0', 'pending=1', 'spoken='])
        pats = []
        if hazard:
            pats = [r'start gaps \(ms\): %d, %d, %d$' % (tick, tick, tick),
                    r'next start\): %d, %d, %d$' % (tick - D, tick - D, tick - D)]
        else:
            pats = [r'start gaps \(ms\): %d, %d, %d$' % (tick, tick, tick),
                    r'next start\): %d, %d, %d$' % (tick - D, tick - D, tick - D)]
        return ('SEAM: a %d ms lead (--free-edge eof --tail-ms %d): EOF at %d, the first tick at or after it is %d ms: %s'
                % (L, L, D - L, tick,
                   'inside the audible tail by %d ms -> R1 + R4 (the accepted hazard) at EVERY seam' % (D - tick)
                   if hazard else 'after the audible end: no hazard rule fires'),
                START + ['--loop', '3', '--tail-ms', str(L), '--free-edge', 'eof'], keys, pats)

    Tb = 2500 + T_ODD     # last busy read before the free edge
    Ta = S + T_ODD                                 # just after the rebuild tick
    SEAM_CASES = [
        ('SEAM: 3 cycles: starts 0, %d, %d ms; silences %d ms; ONE poll pending; R5 (poll >= 50 ms) holds'
         % (S, 2 * S, SIL),
         START + ['--loop', '3'],
         ['looping=yes', 'violations=0', 'pending=1', 'spoken='],
         [r'#2 start +%d ms' % S, r'#3 start +%d ms' % (2 * S),
          r'next start\): %d, %d, %d$' % (SIL, SIL, SIL)]),
        ('SEAM: STOP at %.3f s (a busy read before the free edge): chunk 1 only, nothing pending' % (Tb / 1000),
         START + ['--press', '%d:4004' % Tb, '--horizon', '20000'],
         ['chunks=1', 'ended=1', 'spoken=', 'violations=0', 'pending=0']),
        ('SEAM: STOP at %.3f s (just after the rebuild tick at %d ms): chunk 2 is already playing, STOP cancels the '
         'poll, chunk 2 plays out' % (Ta / 1000, S),
         START + ['--press', '%d:4004' % Ta, '--horizon', '20000'],
         ['chunks=2', 'ended=2', 'spoken=', 'violations=0', 'pending=0']),
        lead_case(10),
        lead_case(30),
        lead_case(200),
    ]
    if P < 200:
        SEAM_CASES.append(lead_case(80))
        SEAM_CASES.append(lead_case(130))
    if P == 50:
        SEAM_CASES.append(lead_case(60))
    return CASES + RATE_CASES + SEAM_CASES


def run_case(name, argsl, expects, pats, simname):
    sim = [sys.executable, os.path.join('tools', 'cavesim.py'), simname, '--entry', '0x3E21D']
    cmd = sim + argsl + EV + exp(*expects)
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=3000)
    got = [l for l in r.stdout.splitlines() if l.startswith('expect ')]
    ok = r.returncode == 0 and len(got) == len(expects) and all(l.endswith('PASS') for l in got)
    msgs = []
    for pat in pats:
        if not re.search(pat, r.stdout, re.M):
            ok = False
            msgs.append('expect output %r FAIL' % pat)
    for l in got:
        if not l.endswith('PASS'):
            msgs.append(l)
    if not ok and r.returncode and not got:
        msgs.append((r.stdout + r.stderr)[-600:])
    return ok, name, ' '.join(cmd[2:]), msgs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('probe', choices=sorted(POLLS))
    ap.add_argument('-j', type=int, default=4, help='scenarios run in parallel')
    ap.add_argument('--only', default=None, help='run only scenarios whose name contains this text')
    ap.add_argument('--list', action='store_true')
    a = ap.parse_args()
    P = POLLS[a.probe]
    cases = build_cases(P)
    if a.only:
        cases = [c for c in cases if a.only in c[0]]
    if a.list:
        for c in cases:
            print(c[0])
            print('    ' + ' '.join(c[1] + EV + exp(*c[2])))
            for p in (c[3] if len(c) > 3 else []):
                print('    re: ' + p)
        return 0
    print('%s: P = %d ms, D = %d, S = %d, silence %d ms; %d scenarios, -j %d'
          % (a.probe, P, D, cdiv(D, P) * P, cdiv(D, P) * P - D, len(cases), a.j))
    bad = 0
    with ThreadPoolExecutor(max_workers=a.j) as ex:
        futs = [ex.submit(run_case, c[0], c[1], c[2], (c[3] if len(c) > 3 else []), a.probe) for c in cases]
        for f in futs:
            ok, name, cmd, msgs = f.result()
            print('%-4s %s' % ('PASS' if ok else 'FAIL', name), flush=True)
            if not ok:
                bad += 1
                print('     cmd: ' + cmd)
                for m in msgs:
                    print('     ' + m)
    print('%d scenarios, %d failed' % (len(cases), bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
