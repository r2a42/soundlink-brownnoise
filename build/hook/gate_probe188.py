#!/usr/bin/env python3
"""Offline world-model gate for probe188 (PBd, diagnostic) and probe189 (PB, silent) -- B01, 2026-10-12.

Runs the real words (build/hook/probe188_words.json / probe189_words.json, written by assemble_probe188.py and
assemble_probe189.py) through tools/cavesim.py's clocked world model, one scripted scenario per entry, each checked
with the simulator's own --expect plus regular expressions on its output.  Exit 0 = every scenario holds.

    python build/hook/assemble_probe188.py ; python build/hook/assemble_probe189.py     # first
    python build/hook/gate_probe188.py probe188 [--part I/N] [--workers N] [--list]
    python build/hook/gate_probe188.py probe189 [--part I/N] [--workers N] [--list]
    options: --group LOOP,GUARD,... (subset)   --words PATH (run a mutated copy of the words: the gate must FAIL)

EVERY scenario presets the healthy speaker state (--mem 59e=d --mem 72f=3400: sinkState 13, an A2DP plugin
instance), because without it every run is a GUARD EXIT and the STOP / pending / loop rows would pass vacuously
(the model's data memory is zero).  Row G1 is the negative control: no preset, nothing may start.
For probe189 every scenario is ALSO run on probe188 and the two world summaries must be identical apart from the
spoken-ids line and the port-3-rules line (PB is PBd with the ids replaced by leavel; same chunks, same starts, same
pending messages); probe189 never speaks.

Groups: LOOP (the 181p loop and STOP rows, re-derived), GUARD (the 0..31 sinkState sweep, @0x72f, E5 with its
unguarded control, the residual rule-4 row), REFUSE (every id of the table, on START and on a rebuild), LEVER (the
consume lever through --caller-frame 23), SEAM (181p's lead and rate rows), POISON (MessageSendLater, KalimbaSendMessage
and SPEAK return non-zero junk: AL at the exit of ARM must be 0 or TRIG would speak it).
The model has zero VM latency, no purge and no lead unless --tail-ms is given (see gate_probe181p.py).
"""
import concurrent.futures as cf
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
E = ['--entry', '0x3E21D']
START = ['--press', '0:4004']
HEALTHY = ['--mem', '59e=d', '--mem', '72f=3400']


def mem(**kw):
    out = []
    for k, v in kw.items():
        out += ['--mem', '%s=%s' % (k[1:], v)]          # _59e='d' -> --mem 59e=d
    return out


POISON = ("import sys; sys.path.insert(0, 'tools'); sys.path.insert(0, 'tools/xapvm'); import cavesim as c; "
          "c.DEFAULT_RETURNS['MessageSendLater'] = 0x1234; c.DEFAULT_RETURNS['KalimbaSendMessage'] = 7; "
          "o = c.build\n"
          "def b(*a, **k):\n"
          "    r = o(*a, **k); vm = r[0] if isinstance(r, tuple) else r\n"
          "    vm.FUNC_RET[c.SPEAK_ADDR] = (0, 0x7777); return r\n"
          "c.build = b; sys.argv = ['cavesim.py'] + sys.argv[1:]; c.main()\n")

SCEN = []      # (group, name, sim args (after probe name), expects fn(pbd)->list, regex list, extra dict)


def S(group, name, args, expects, regex=(), **extra):
    SCEN.append((group, name, args, expects, list(regex), extra))


def sp(pbd_ids):
    """the spoken= expectation: PBd speaks pbd_ids (list of hex strings), PB nothing"""
    return lambda pbd: 'spoken=' + (','.join(pbd_ids) if pbd else '')


def E_(base, spoken, rules_pbd=None):
    """expectation builder: base list + the spoken key (+ a rules/violations override for PBd)"""
    def f(pbd):
        out = list(base) + [spoken(pbd)]
        if rules_pbd is not None and pbd:
            out += list(rules_pbd)
        elif 'violations=0' not in base and rules_pbd is not None:
            out += ['violations=0']
        return out
    return f


NONE = sp([])
H = HEALTHY
LP = ['looping=yes', 'violations=0', 'pending=1']

# ------------------------------------------------------------------ LOOP
S('LOOP', 'START, loop 3: a 4th chunk starts, one poll pending, silent; starts 0 2800 5600, silences 178',
  START + ['--loop', '3'] + H, E_(LP + ['swallowed=1', 'replayed=0'], NONE),
  [r'#2 start +2800 ms', r'#3 start +5600 ms', r'next start\): 178, 178, 178$'])
S('LOOP', 'START, STOP at 4.5 s (chunk 2), START at 30 s, STOP at 43.5 s: 2 + 5 chunks at the 2.8 s period',
  START + ['--press', '4500:4004', '--press', '30000:4004', '--press', '43500:4004', '--horizon', '70000'] + H,
  E_(['chunks=7', 'ended=7', 'violations=0', 'pending=0', 'swallowed=4', 'replayed=0'], NONE))
S('LOOP', 'STOP in the gap (2.7 s; the poll is still pending): it cancels',
  START + ['--press', '2700:4004', '--horizon', '40000'] + H,
  E_(['chunks=1', 'ended=1', 'violations=0', 'pending=0'], NONE))
S('LOOP', 'STOP while chunk 1 plays (1.5 s)',
  START + ['--press', '1500:4004', '--horizon', '40000'] + H,
  E_(['chunks=1', 'ended=1', 'violations=0', 'pending=0'], NONE))
S('LOOP', 'long run: START, STOP at 50.5 s: 19 chunks, one poll at a time, nothing spoken',
  START + ['--press', '50500:4004', '--horizon', '100000', '--events', '3000'] + H,
  E_(['chunks=19', 'ended=19', 'violations=0', 'pending=0'], NONE))
S('LOOP', 'a modelled pending poll + one press: that press is a STOP, no chunk is built',
  ['--pending', '12@1000', '--press', '0:4004', '--once'] + H,
  E_(['chunks=0', 'violations=0', 'pending=0', 'swallowed=1'], NONE))
S('LOOP', 'a non-0x4004 event is replayed to the stock, nothing else happens',
  ['--press', '0:4003', '--once'] + H,
  E_(['chunks=0', 'violations=0', 'pending=0', 'replayed=1', 'swallowed=0'], NONE))
S('LOOP', 'STOP then START inside the draining chunk (1.5 s, 2.0 s): the second press is a DEFERRED start, the noise goes on (R05 E34)',
  START + ['--press', '1500:4004', '--press', '2000:4004', '--horizon', '20000'] + H,
  E_(['chunks=8', 'violations=0', 'pending=1', 'swallowed=3'], NONE), [r'#2 start +2800 ms'])
S('LOOP', 'START while a foreign tone holds port 3 (0..3 s): a deferred start, the first chunk at 3.0 s, no stacked transform',
  START + ['--foreign-tone', '0:3000', '--horizon', '12000'] + H,
  E_(['violations=0', 'pending=1'], NONE), [r'#1 start +3000 ms'])
S('LOOP', 'STOP in a BAD state: a poll is pending, sinkState 5 (call): the press is still a STOP (STOP is first)',
  ['--pending', '12@1000', '--press', '0:4004', '--once'] + mem(_59e='5', _72f='3400'),
  E_(['chunks=0', 'violations=0', 'pending=0', 'swallowed=1'], NONE))
S('LOOP', 'STOP with no plugin instance (@0x72f = 0): a poll is pending, the press is still a STOP',
  ['--pending', '12@1000', '--press', '0:4004', '--once'] + mem(_59e='d', _72f='0'),
  E_(['chunks=0', 'violations=0', 'pending=0', 'swallowed=1'], NONE))
S('LOOP', 'music PAUSED (unload 100 ms): chunk 1, then 0x21 at the first seam, no re-arm',
  START + ['--music', 'paused', '--unload-ms', '100', '--horizon', '60000'] + H,
  E_(['chunks=1', 'violations=0', 'pending=0', 'dsp=unloaded'], sp(['21'])))
S('LOOP', 'DSP down at START: 0x21 (probe181p said 0x3E here), nothing built, nothing armed',
  START + ['--dsp', 'down', '--once'] + H,
  E_(['chunks=0', 'violations=0', 'pending=0', 'dsp=unloaded'], sp(['21'])))
S('LOOP', 'Bluetooth long press at 1.5 s: chunk cut, the next poll speaks 0x21 and arms nothing; a later START: 0x21 again',
  START + ['--bt-teardown-at', '1500', '--press', '20000:4004', '--horizon', '40000'] + H,
  E_(['chunks=1', 'violations=0', 'pending=0'], sp(['21', '21'])))

# ------------------------------------------------------------------ GUARD
S('GUARD', 'G1 NEGATIVE CONTROL: START with the model default memory (sinkState 0, no plugin): nothing starts; PBd reports state 0 = 0x27',
  START + ['--once'],
  E_(['chunks=0', 'violations=0', 'pending=0'], sp(['27'])))
for v in range(0, 32):
    if v in (3, 13):
        S('GUARD', 'sweep sinkState=%d: the loop runs (3 chunks + a 4th, one poll pending, silent)' % v,
          START + ['--loop', '3'] + mem(_59e='%x' % v, _72f='3400'),
          E_(LP, NONE))
    else:
        S('GUARD', 'sweep sinkState=%d: START is refused, nothing built, nothing pending; PBd speaks 0x%02x, PB nothing' % (v, 0x27 + v),
          START + ['--once'] + mem(_59e='%x' % v, _72f='3400'),
          E_(['chunks=0', 'violations=0', 'pending=0'], sp(['%02x' % (0x27 + v)])))
S('GUARD', 'sinkState 13 but @0x72f = 0 (no A2DP plugin instance): START refused; PBd speaks 0x23',
  START + ['--once'] + mem(_59e='d', _72f='0'),
  E_(['chunks=0', 'violations=0', 'pending=0'], sp(['23'])))
S('GUARD', 'E5: state 13 -> 6 and a foreign DSP at 3.5 s: the loop ends at the NEXT TICK, silently, no W1 (PBd too: a tick never speaks)',
  START + ['--mem-at', '3500:59e=6', '--wrong-dsp', '3500:3000', '--horizon', '20000'] + H,
  E_(['chunks=2', 'ended=2', 'violations=0', 'pending=0'], NONE))
S('GUARD', 'E5 control: the UNGUARDED probe181p under the same scenario shows the W1 violations (the row can fail)',
  START + ['--mem-at', '3500:59e=6', '--wrong-dsp', '3500:3000', '--horizon', '20000'] + H,
  lambda pbd: ['violations=4'], [r'W1 t=3600'], probe='probe181p', skip_equiv=True)
S('GUARD', 'the plugin instance freed at 3.5 s (a stock prompt / call swap): the loop ends at the next tick, silently',
  START + ['--mem-at', '3500:72f=0', '--horizon', '20000'] + H,
  E_(['chunks=2', 'ended=2', 'violations=0', 'pending=0'], NONE))
S('GUARD', 'a call starts at 3.5 s (state 6) and the owner presses at 6.0 s (chunk 2 has ended): a START in a bad state, PBd reports 0x2d',
  START + ['--mem-at', '3500:59e=6', '--press', '6000:4004', '--horizon', '20000'] + H,
  E_(['chunks=2', 'ended=2', 'violations=0', 'pending=0'], sp(['2d'])))
S('GUARD', 'RESIDUAL (rule 4): START, STOP at 1.5 s, state 6 at 1.6 s, START at 2.0 s while chunk 1 still drains: PBd SPEAKS under port 3 (R3); PB is silent',
  START + ['--press', '1500:4004', '--mem-at', '1600:59e=6', '--press', '2000:4004', '--horizon', '20000'] + H,
  E_(['chunks=1', 'ended=1', 'pending=0'], sp(['2d']), rules_pbd=['violations=1', 'rules=R3']))

# ------------------------------------------------------------------ REFUSE
S('REFUSE', 'START: StreamKalimbaSink -> 0: 0x10 "and"',
  START + ['--fail', 'StreamKalimbaSink', '--once'] + H, E_(['chunks=0', 'violations=0', 'pending=0'], sp(['10'])))
S('REFUSE', 'START: directory FileFind refused: 0x22',
  START + ['--fail', 'FileFind', '--once'] + H, E_(['chunks=0', 'violations=0', 'pending=0'], sp(['22'])))
S('REFUSE', 'START: file FileFind refused (2nd call): 0x1B',
  START + ['--fail-after', 'FileFind=2', '--once'] + H, E_(['chunks=0', 'violations=0', 'pending=0'], sp(['1b'])))
S('REFUSE', 'START: StreamFileSource refused: 0x24',
  START + ['--fail', 'StreamFileSource', '--once'] + H, E_(['chunks=0', 'violations=0', 'pending=0'], sp(['24'])))
S('REFUSE', 'START: TransformAdpcmDecode refused: 0x25',
  START + ['--fail', 'TransformAdpcmDecode', '--once'] + H, E_(['chunks=0', 'violations=0', 'pending=0'], sp(['25'])))
S('REFUSE', 'START: TransformStart refused: 0x25',
  START + ['--fail', 'TransformStart', '--once'] + H, E_(['chunks=0', 'violations=0', 'pending=0'], sp(['25'])))
S('REFUSE', 'rebuild: directory FileFind refused (3rd call): 0x22 at the first seam',
  START + ['--fail-after', 'FileFind=3', '--horizon', '60000'] + H,
  E_(['chunks=1', 'ended=1', 'violations=0', 'pending=0'], sp(['22'])))
S('REFUSE', 'rebuild: file FileFind refused (4th call): 0x1B',
  START + ['--fail-after', 'FileFind=4', '--horizon', '60000'] + H,
  E_(['chunks=1', 'ended=1', 'violations=0', 'pending=0'], sp(['1b'])))
S('REFUSE', 'rebuild: StreamFileSource refused (2nd call): 0x24',
  START + ['--fail-after', 'StreamFileSource=2', '--horizon', '60000'] + H,
  E_(['chunks=1', 'ended=1', 'violations=0', 'pending=0'], sp(['24'])))
S('REFUSE', 'rebuild: TransformAdpcmDecode refused (2nd call): 0x25',
  START + ['--fail-after', 'TransformAdpcmDecode=2', '--horizon', '60000'] + H,
  E_(['chunks=1', 'ended=1', 'violations=0', 'pending=0'], sp(['25'])))
S('REFUSE', 'rebuild: TransformStart refused (2nd call): 0x25',
  START + ['--fail-after', 'TransformStart=2', '--horizon', '60000'] + H,
  E_(['chunks=1', 'ended=1', 'violations=0', 'pending=0'], sp(['25'])))
S('REFUSE', 'INHERITED: StreamKalimbaSink -> 0 on the 3rd call (a poll inside chunk 1): 0x10, loop over (R3 only because the model still holds port 3)',
  START + ['--fail-after', 'StreamKalimbaSink=3', '--horizon', '60000'] + H,
  E_(['chunks=1', 'ended=1', 'pending=0'], sp(['10']), rules_pbd=['rules=R3']),
  )

# ------------------------------------------------------------------ LEVER (the consume lever, R05 5.3)
LV = ['--frame', '13=1', '--frame', '14=0', '--show', '90D:2', '--caller-frame', '23']
S('LEVER', 'START, event 0x4004: the caller indicate flag := 0, bit 15 of its flag word set (@0x90D..0x90E = 0000 8000); no HAZARD, no stop',
  START + ['--once'] + LV + H, E_(['chunks=1', 'violations=0'], NONE),
  [r'data @0x090D\.\.\+2: 0000 8000', r'NOTE cave slot 21 writes caller slot 13', r'NOTE cave slot 22 writes caller slot 14'])
S('LEVER', 'STOP (a poll pending), event 0x4004: the same two words',
  ['--pending', '12@1000', '--press', '0:4004', '--once'] + LV + H, E_(['chunks=0', 'violations=0', 'pending=0'], NONE),
  [r'data @0x090D\.\.\+2: 0000 8000'])
S('LEVER', 'guard exit (sinkState 5), event 0x4004: still consumed (0000 8000); PBd speaks 0x2c from TRIG',
  START + ['--once'] + LV + mem(_59e='5', _72f='3400'), E_(['chunks=0', 'violations=0'], sp(['2c'])),
  [r'data @0x090D\.\.\+2: 0000 8000'])
S('LEVER', 'DSP down at START (0x21), event 0x4004: consumed',
  START + ['--dsp', 'down', '--once'] + LV + H, E_(['chunks=0', 'violations=0'], sp(['21'])),
  [r'data @0x090D\.\.\+2: 0000 8000'])
S('LEVER', 'a centre SHORT event 0x4045: replayed to the stock, the two slots stay 0001 0000',
  ['--press', '0:4045', '--once'] + LV + H, E_(['chunks=0', 'violations=0', 'replayed=1', 'swallowed=0'], NONE),
  [r'data @0x090D\.\.\+2: 0001 0000'])

# ------------------------------------------------------------------ SEAM (probe181p's lead and rate rows, guard preset)
S('SEAM', 'a 10 ms lead (--free-edge eof --tail-ms 10): no hazard rule fires',
  START + ['--loop', '3', '--tail-ms', '10', '--free-edge', 'eof'] + H, E_(LP, NONE))
S('SEAM', 'a 30 ms lead: the tick at 2.6 s reads FREE while 22 ms of tail are audible -> R1 + R4 at every seam (accepted hazard of 181p, T11-N2)',
  START + ['--loop', '3', '--tail-ms', '30', '--free-edge', 'eof'] + H, lambda pbd: ['rules=R1,R4', 'looping=yes', 'spoken=' if not pbd else 'spoken='],
  [r'start gaps \(ms\): 2600, 2600, 2600$', r'next start\): -22, -22, -22$'])
S('SEAM', 'a 200 ms lead: R1 + R4 (the lead is what seammodel.py prices)',
  START + ['--loop', '3', '--tail-ms', '200', '--free-edge', 'eof'] + H, lambda pbd: ['rules=R1,R4', 'looping=yes'])
S('SEAM', 'TransformFromSink reads 0 on a live chunk -> R1 + R4 (accepted)',
  START + ['--loop', '3', '--fail', 'TransformFromSink'] + H, lambda pbd: ['rules=R1,R4', 'looping=yes'])
S('SEAM', 'RATE: the stock leaves 8000: every chunk 8000 Hz / 2622 ms, STOP at 13.5 s ends it',
  START + ['--press', '13500:4004', '--horizon', '30000'] + H,
  E_(['chunks=5', 'ended=5', 'violations=0', 'pending=0'], NONE),
  [r'#1 start +0 ms .* 8000 Hz .* 2622 ms', r'start gaps \(ms\): 2800, 2800, 2800, 2800$'])
S('SEAM', 'RATE: the stock leaves 7000: chunk 1 plays at 7000 Hz / 2996 ms, seam 1 is 4 ms, then 8000 Hz',
  START + ['--press', '13500:4004', '--horizon', '30000', '--stock-rate', '7000'] + H,
  E_(['chunks=5', 'ended=5', 'violations=0', 'pending=0'], NONE),
  [r'#1 start +0 ms .* 7000 Hz .* 2996 ms', r'#2 start +3000 ms .* 8000 Hz .* 2622 ms', r'next start\): 4, 178, 178, 178$'])

# ------------------------------------------------------------------ POISON (junk non-zero returns)
S('POISON', 'MessageSendLater returns 0x1234, KalimbaSendMessage returns 7, SPEAK returns 0x7777: the START still says nothing (AL = 0 at the ARM exit)',
  START + ['--loop', '2'] + H, E_(['looping=yes', 'violations=0', 'pending=1'], NONE), [], poison=True, skip_equiv=True)
S('POISON', 'the same junk on a guard exit: exactly one id (0x2c), then silence (SPEAK returning junk is not re-spoken)',
  START + ['--once'] + mem(_59e='5', _72f='3400'), E_(['chunks=0', 'violations=0', 'pending=0'], sp(['2c'])), [],
  poison=True, skip_equiv=True)
S('POISON', 'the same junk on a STOP (a poll pending): silent',
  ['--pending', '12@1000', '--press', '0:4004', '--once'] + H, E_(['chunks=0', 'violations=0', 'pending=0'], NONE), [],
  poison=True, skip_equiv=True)
S('POISON', 'the same junk on a refusal at START (FileFind refused): exactly one id (0x22)',
  START + ['--fail', 'FileFind', '--once'] + H, E_(['chunks=0', 'violations=0', 'pending=0'], sp(['22'])), [],
  poison=True, skip_equiv=True)


# ------------------------------------------------------------------ runner
WORDS = {}      # --words PATH: run a MUTATED copy of the words of the probe under test (the gate must then FAIL)


def run_sim(probe, args, poison=False):
    probe = WORDS.get(probe, probe)
    if poison:
        cmd = [sys.executable, '-c', POISON, probe] + E + args
    else:
        cmd = [sys.executable, os.path.join('tools', 'cavesim.py'), probe] + E + ['--brief'] + args
    if poison:
        cmd += ['--brief']
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=900)
    return cmd, r


KEEP = re.compile(r'^(stopped:|chunks started|  #\d+ start|  chunk-to-chunk|  silence between|presses:|'
                  r'cave messages|DSP:|file sources)')


def summary(out):
    return [l for l in out.splitlines() if KEEP.match(l)]


def one(item, probe):
    group, name, args, expects, regex, extra = item
    pbd = (probe == 'probe188')
    prb = extra.get('probe') or probe
    exp = expects(pbd)
    cmd, r = run_sim(prb, args + [x for e in exp for x in ('--expect', e)], extra.get('poison', False))
    got = [l for l in r.stdout.splitlines() if l.startswith('expect ')]
    ok = r.returncode == 0 and len(got) == len(exp) and all(l.endswith('PASS') for l in got)
    notes = [l for l in got if not l.endswith('PASS')]
    for pat in regex:
        if not re.search(pat, r.stdout, re.M):
            ok = False
            notes.append('output %r FAIL' % pat)
    if not pbd and 'W1' in name and False:
        pass
    # PB: the world summary must equal PBd's
    if ok and probe == 'probe189' and not extra.get('skip_equiv') and not extra.get('probe'):
        _c2, r2 = run_sim('probe188', args)
        if summary(r.stdout) != summary(r2.stdout):
            ok = False
            notes.append('PB summary differs from PBd: %r' % (set(summary(r.stdout)) ^ set(summary(r2.stdout)),))
    if not ok and not notes:
        notes.append((r.stdout + r.stderr)[-500:])
    return group, name, ok, notes, cmd


def main():
    probe = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].startswith('probe') else 'probe188'
    assert probe in ('probe188', 'probe189'), probe
    items = list(enumerate(SCEN))
    part = [a for a in sys.argv if a.startswith('--part')]
    if '--part' in sys.argv:
        i, n = [int(x) for x in sys.argv[sys.argv.index('--part') + 1].split('/')]
        items = [(k, s) for k, s in items if k % n == i - 1]
    if '--words' in sys.argv:
        WORDS[probe] = sys.argv[sys.argv.index('--words') + 1]
    if '--group' in sys.argv:
        g = sys.argv[sys.argv.index('--group') + 1].split(',')
        items = [(k, s) for k, s in items if s[0] in g]
    if '--list' in sys.argv:
        for k, s in items:
            print('%3d %-7s %s' % (k, s[0], s[1]))
        print('%d scenarios' % len(items))
        return 0
    workers = int(sys.argv[sys.argv.index('--workers') + 1]) if '--workers' in sys.argv else 6
    results = []
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, s, probe) for _k, s in items]
        for f in futs:
            results.append(f.result())
    bad = 0
    for group, name, ok, notes, cmd in results:
        print('%-4s %-7s %s' % ('PASS' if ok else 'FAIL', group, name))
        if not ok:
            bad += 1
            print('     cmd: ' + ' '.join(cmd[2:] if cmd[1] != '-c' else cmd[3:]))
            for l in notes:
                print('     ' + l)
    print('%s: %d scenarios, %d failed' % (probe, len(results), bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
