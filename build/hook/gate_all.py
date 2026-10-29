#!/usr/bin/env python3
"""gate_all: the whole offline gate of one product image in ONE command (CM, 2026-10-22; docs/deep/material-2026-10-19/CM-gate-streamlining.md).

    python build/hook/gate_all.py probe310 --poll-floor 10                 # FULL = the flash gate (all stages, both chunk models)
    python build/hook/gate_all.py probe310 --poll-floor 10 --mode quick    # QUICK = changed-row subset. NOT A FLASH GATE (exit code 10 on pass)
    python build/hook/gate_all.py probe310 --poll-floor 10 --slow --jobs 4 # reference path: original tools/cavesim.py, no cache

Stages (FULL; every one must pass; nothing is dropped relative to docs/deep/material-2026-10-19/BZ section 5 / CK section 5):
  control    python tools/cavesim.py probe90                        expect AL = 0x000e
  preflight  python tools/preflight.py PROBE                        expect the image check line + "pass pre-flight"
  framecheck python tools/framecheck.py PROBE                       expect 0 stores into the top two frame slots
  product    build/hook/gate_product.py PROBE, once per chunk model (default 4914 and 14742,4914), EVERY scenario
  stock      build/hook/gate_stock_world.py PROBE (GATE_CHUNK_MS=4914), every scenario
  xpair      the cross-pair: the other 24 kHz payload in p2: scenario 64 must FAIL with exactly "missing: chunks started: 12," (the pair rule),
             and scenario 73's silence expectations must hold with that payload in p2
  writer     the writer gate whose pinned payload is the one this image pairs with (gate_probe304/306/308.py), all scenarios
The gate scripts themselves are run UNCHANGED through build/hook/gate_runner.py (fast simulator path + optional raw-result cache); their verdict
logic is the original. This tool only schedules (one scenario per task, longest first, N-2 workers), collects and reports.
Exit codes: 0 FULL pass; 1 any failure; 10 QUICK subset passed (not a gate).
"""
import argparse
import concurrent.futures as cf
import glob
import json
import os
import re
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
CM = os.path.join(ROOT, 'docs', 'deep', 'material-2026-10-19', 'cm-coverage')
RUNNER = os.path.join(HERE, 'gate_runner.py')
import tempfile
CACHE_ROOT = os.environ.get('GATE_CACHE_ROOT') or os.path.join(tempfile.gettempdir(), 'csr8670_gate_cache')      # outside the repository: the pickles are ~15 MB each
PY = sys.executable
_env_lock = threading.Lock()


# ----------------------------------------------------------------------------------------------------------------- loading
def wrapper_text(probe):
    try:
        return open(os.path.join(HERE, 'assemble_%s.py' % probe), encoding='utf-8').read()
    except OSError:
        return ''


def load_sc(probe, env):
    """The scenario list of gate_product.py for this probe under this environment: the gate's own source executed up to its run loop."""
    path = os.path.join(HERE, 'gate_product.py')
    src = open(path, encoding='utf-8').read()
    cut = src.index('\nfails = 0\n')
    with _env_lock:
        saved = {k: os.environ.get(k) for k in env}
        old_argv = sys.argv
        try:
            for k, v in env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            sys.argv = [path, probe]
            g = {'__file__': path, '__name__': 'gate_product_load'}
            exec(compile(src[:cut], path, 'exec'), g)
            return g['SC']
        finally:
            sys.argv = old_argv
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def payload_by_first4():
    out = {}
    for f in sorted(glob.glob(os.path.join(ROOT, 'build', 'payload', 'g*', 'brown_24000_58968_*.adpcm'))):
        out[open(f, 'rb').read(4).hex()] = os.path.relpath(f, ROOT).replace('\\', '/')
    return out


def detect_p2(probe):
    m = re.search(r'PAYLOAD_FIRST4\s*=\s*\(([^)]*)\)', wrapper_text(probe))
    if not m:
        return None
    key = ''.join('%02x' % int(x, 16) for x in m.group(1).split(','))
    return payload_by_first4().get(key)


def detect_writer(p2):
    """The writer gate whose pinned PAYLOAD_PATH is this payload."""
    if not p2:
        return None
    base = os.path.basename(p2)
    for f in sorted(glob.glob(os.path.join(HERE, 'gate_probe3*.py'))):
        t = open(f, encoding='utf-8').read()
        m = re.search(r"PAYLOAD_PATH = os\.path\.join\(ROOT, 'build', 'payload', '(g\d+)', '([^']+)'\)", t)
        if m and (m.group(1) + '/' + m.group(2)) == p2.split('payload/')[-1] and base == m.group(2):
            return os.path.basename(f)
    return None


# ----------------------------------------------------------------------------------------------------------------- tasks
class Task:
    def __init__(self, stage, name, cmd, env, est, parse, quick=True):
        self.stage, self.name, self.cmd, self.env, self.est, self.parse, self.quick = stage, name, cmd, env, est, parse, quick
        self.fn = None
        self.ok = None
        self.detail = []
        self.wall = 0.0
        self.sims = []          # per simulator call records from the runner's timing log
        self.log = None


def parse_gate_lines(out, expect):
    """product / stock / writer output: every 'ok'/'xfail' line counts as a pass, 'FAIL' fails; expect = the number of result lines needed."""
    lines = out.splitlines()
    res = [ln for ln in lines if re.match(r'(ok  |FAIL|xfail|skip) ', ln)]
    bad = [ln for ln in lines if ln.startswith('FAIL')]
    detail = []
    for k, ln in enumerate(lines):
        if ln.startswith('FAIL'):
            detail.append(ln[:240])
            j = k + 1
            while j < len(lines) and lines[j].startswith('      '):
                detail.append(lines[j][:240]); j += 1
    ok = (not bad) and (expect is None or len(res) == expect)
    if not bad and expect is not None and len(res) != expect:
        detail.append('expected %d result line(s), saw %d' % (expect, len(res)))
    return ok, detail


def run_cmd(task, rundir):
    if task.fn is not None:
        t0 = time.time()
        task.ok, task.detail, task.sims = task.fn(task)
        task.wall = time.time() - t0
        return task
    env = dict(os.environ)
    env.update(task.env)
    task.log = os.path.join(rundir, 'timing-%s.jsonl' % re.sub(r'[^A-Za-z0-9_.-]+', '_', task.stage + '-' + task.name))
    env['GATE_TIMING_LOG'] = task.log
    t0 = time.time()
    r = subprocess.run(task.cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=14400)
    task.wall = time.time() - t0
    out = r.stdout + r.stderr
    task.ok, task.detail = task.parse(out, r.returncode)
    try:
        for ln in open(task.log, encoding='utf-8'):
            task.sims.append(json.loads(ln))
    except OSError:
        pass
    return task


# ----------------------------------------------------------------------------------------------------------------- plan
def build_plan(a):
    probe = a.probe
    wrap = wrapper_text(probe)
    if not os.path.exists(os.path.join(HERE, probe + '_words.json')):
        sys.exit('no build/hook/%s_words.json: build the image first (assemble_%s.py --build)' % (probe, probe))
    p2 = a.p2 or detect_p2(probe) or 'build/payload/r3/brown_8000_58968_s63.adpcm'
    floor = a.poll_floor
    m = re.search(r'PAYLOAD_BUSY_POLL\s*=\s*(\d+)', wrap)
    if m and int(m.group(1)) < 50 and floor is None:
        sys.exit('%s declares PAYLOAD_BUSY_POLL = %s (< the rule R5 floor 50): pass --poll-floor N explicitly (the lowered floor needs the owner\'s approval and is stated in the image\'s doc)' % (probe, m.group(1)))
    models = [x.strip() for x in a.models.split(';') if x.strip()]
    base_env = {'GATE_P2': p2}
    if floor is not None:
        base_env['GATE_POLL_FLOOR'] = str(floor)
    if a.slow:
        base_env['GATE_FAST'] = '0'
    elif not a.no_cache:
        base_env['GATE_RESULT_CACHE'] = a.cache_dir
    hist = {}
    try:
        hist = json.load(open(os.path.join(CM, 'history.json')))
    except (OSError, ValueError):
        pass
    tasks = []

    def est(key, default):
        return hist.get(key, default)

    quick = a.mode == 'quick'
    sel = set(x for x in a.ids.split(',') if x) if a.ids else None
    changed = None
    if quick and not sel:
        since = a.quick_since or previous_probe(probe)
        changed = changed_rows(probe, since, dict(base_env, GATE_CHUNK_MS=models[0]))
    # control / preflight / framecheck
    t = Task('control', 'probe90', None, base_env, 3, None)
    t.fn = control_fn
    tasks.append(t)
    tasks.append(Task('preflight', probe, [PY, os.path.join(ROOT, 'tools', 'preflight.py'), probe], {}, 4,
                      lambda out, rc: (bool(re.search(r'OK\s+all \d+ cave words and \d+ redirect bytes verified', out) and 'all checked probes pass pre-flight' in out),
                                       [ln for ln in out.splitlines() if re.search(r'FAIL|MISMATCH|problem|WRONG|ERROR', ln)][:6])))
    tasks.append(Task('framecheck', probe, [PY, os.path.join(ROOT, 'tools', 'framecheck.py'), probe], {}, 1,
                      lambda out, rc: (re.search(r': 0 store\(s\) into the top two slots of a frame', out) is not None, out.splitlines()[-3:])))
    # product, per chunk model, per scenario
    nsc = {}
    for mdl in models:
        env = dict(base_env, GATE_CHUNK_MS=mdl)
        sc = load_sc(probe, env)
        ids = {}
        for n, args, rx in sc:
            ids.setdefault(n.split()[0], []).append(int(args[args.index('--horizon') + 1]))
        nsc[mdl] = len(sc)
        for sid, hs in ids.items():
            if sel is not None and sid not in sel:
                continue
            if changed is not None and sid not in changed:
                continue
            if changed is not None and mdl != models[0] and sid not in SLOW_MODEL_ROWS:
                continue
            key = 'product|%s|%s|%s' % (probe, mdl, sid)
            t = Task('product', 'm%s/%s' % (mdl, sid), [PY, RUNNER, os.path.join(HERE, 'gate_product.py'), probe], dict(env, GATE_ONLY=sid),
                     est(key, sum(hs) / 5000.0), None)
            n_expected = len(hs)
            t.parse = (lambda n_expected: lambda out, rc: parse_gate_lines(out, n_expected))(n_expected)
            t.key = key
            tasks.append(t)
    full_only = not quick
    if full_only or sel is not None:
        if sel is None:
            # stock world (every scenario; GATE_JOBS threads inside)
            env = dict(base_env, GATE_CHUNK_MS=a.models.split(';')[0].split(',')[-1], GATE_JOBS='3')
            key = 'stock|%s' % probe
            t = Task('stock', probe, [PY, RUNNER, os.path.join(HERE, 'gate_stock_world.py'), probe], env, est(key, 60), lambda out, rc: parse_gate_lines(out, None))
            t.key = key
            tasks.append(t)
            # cross-pair
            if 'PAYLOAD_RATE = 24000' in wrap or 'PAYLOAD_RATE = 48000' in wrap:
                others = [v for k, v in sorted(payload_by_first4().items()) if v != p2]
                other = a.cross_p2 or (others[-1] if others else None)
                if other:
                    env = dict(base_env, GATE_P2=other, GATE_CHUNK_MS=('2457' if 'PAYLOAD_RATE = 48000' in wrap else '4914'))   # probe315: the 48 kHz pair's all-full-rate chunk model
                    xs = load_sc(probe, env)
                    s64 = [s for s in xs if s[0].split()[0] == '64'][0]
                    s73 = [s for s in xs if s[0].split()[0] == '73'][0]
                    tasks.append(make_xpair(probe, env, other, s64, s73))
            # writer
            wr = a.writer or detect_writer(p2)
            if wr:
                nparts = max(2, min(8, a.jobs))
                for i in range(nparts):
                    key = 'writer|%s|%d/%d' % (wr, i + 1, nparts)
                    t = Task('writer', '%s %d/%d' % (wr, i + 1, nparts), [PY, RUNNER, os.path.join(HERE, wr), '--part', '%d/%d' % (i + 1, nparts)], {k: v for k, v in base_env.items() if k != 'GATE_P2'},
                             est(key, 90), lambda out, rc: parse_gate_lines(out, None))
                    t.key = key
                    tasks.append(t)
            else:
                print('NOTE: no writer gate found for payload %s (use --writer gate_probeNNN.py)' % p2)
    return tasks, nsc, p2, floor, models


SLOW_MODEL_ROWS = {'1', '5', '8', '9', '10', '17', '27', '35', '44', '50', '64', '65', '66', '67', '68', '69', '70', '71', '72', '73', '74', '75', '76', '77', '78', '79', '80', '81', '82', '83', '84'}


def previous_probe(probe):
    n = int(re.sub(r'\D', '', probe))
    cands = sorted(int(re.search(r'assemble_probe(\d+)\.py$', f).group(1)) for f in glob.glob(os.path.join(HERE, 'assemble_probe*.py'))
                   if re.search(r'assemble_probe(\d+)\.py$', f))
    prev = [c for c in cands if c < n and os.path.exists(os.path.join(HERE, 'probe%d_words.json' % c))]
    return 'probe%d' % prev[-1] if prev else None


def changed_rows(probe, since, env):
    """Rows (ids) that are new or whose definition (arguments, expectations, horizon) differs from the previous image's: the impact subset."""
    def norm(args):         # --events N is a model budget (BASE differs between images for that alone), not a row definition
        a = list(args)
        while '--events' in a:
            k = a.index('--events'); del a[k:k + 2]
        return a
    cur = load_sc(probe, env)
    old = {}
    if since:
        for n, args, rx in load_sc(since, env):
            old[n.split()[0]] = (norm(args), rx)
    ids = set()
    for n, args, rx in cur:
        sid = n.split()[0]
        if sid not in old or old[sid] != (norm(args), rx):
            ids.add(sid)
    ids |= {'1', '64'}              # the lifecycle row and the chunk-rhythm row always run
    return ids


def sim_inproc(args, tag):
    """One simulator call through gate_runner.run (fast path, result cache, as in every other task)."""
    import gate_runner
    t0 = time.time()
    r = gate_runner.run([PY, 'tools/cavesim.py'] + args, cwd=ROOT, capture_output=True, text=True)
    return r.stdout + r.stderr, {'t': round(time.time() - t0, 3), 'hit': os.environ.get('GATE_RESULT_CACHE') is not None and False, 'tag': tag}


def judge(out, rx):
    bad = []
    for p in rx:
        neg = p.startswith('!')
        pat = p[1:] if neg else p
        if (re.search(pat, out) is not None) == neg:
            bad.append(('present: ' if neg else 'missing: ') + pat)
    if 'STOPPED' in out:
        bad.append('STOPPED in the simulator')
    return bad


def control_fn(task):
    out, rec = sim_inproc(['probe90'], 'control')
    ok = re.search(r'ended: .* AL = 0x000e', out) is not None
    return ok, [] if ok else ['control probe90: AL != 0x000e'], [rec]


def make_xpair(probe, env, other, s64, s73):
    t = Task('xpair', os.path.basename(other), None, env, 20, None)
    words = os.path.join(HERE, probe + '_words.json')

    def fn(task):
        detail, recs = [], []
        # (a) the unchanged gate row 64 with the other payload in p2: it must FAIL on "chunks started: 12," (no chunk starts: the pair rule refuses the mismatched payload)
        e = dict(os.environ); e.update(env); e['GATE_ONLY'] = '64'
        t0 = time.time()
        r = subprocess.run([PY, RUNNER, os.path.join(HERE, 'gate_product.py'), probe], cwd=ROOT, env=e, capture_output=True, text=True, timeout=14400)
        recs.append({'t': round(time.time() - t0, 3), 'tag': 'xpair-64'})
        out = r.stdout + r.stderr
        failed = re.search(r'^FAIL 64 ', out, re.M) is not None
        miss = [ln.strip() for ln in out.splitlines() if ln.strip().startswith('-> ')]
        _xn = 'chunks started: 24,' if 'PAYLOAD_RATE = 48000' in wrapper_text(probe) else 'chunks started: 12,'   # probe315: 24 chunks in 60 s at 2,463 ms; the 24 kHz images start 12
        if not failed or not any(_xn in m for m in miss) or 'STOPPED' in out:
            detail.append('row 64 with the mismatched payload did not fail on "%s" as the pair rule requires: ' % _xn + ' | '.join(miss)[:300])
        # (b) the silence expectations of row 73 with the mismatched payload in p2
        args = list(s73[1]); k = args.index('--raw-p2'); args[k + 1] = 'file:' + other
        out2, rec = sim_inproc([words] + args, 'xpair-73')
        recs.append(rec)
        bad = judge(out2, s73[2])
        detail += ['silence check: ' + b for b in bad]
        return (not detail), detail, recs
    t.fn = fn
    return t


# ----------------------------------------------------------------------------------------------------------------- report
def write_md(path, a, done, wall, nsim, nhit):
    with open(path, 'w', encoding='utf-8') as f:
        f.write('# gate_all %s %s: per-task timing\n\nwall %.0f s on %d workers; simulator calls %d, cache hits %d\n\n' % (a.probe, a.mode, wall, a.jobs, nsim, nhit))
        f.write('| stage | task | result | wall s | sims | hits |\n|---|---|---|---|---|---|\n')
        for t in sorted(done, key=lambda t: -t.wall):
            f.write('| %s | %s | %s | %.1f | %d | %d |\n' % (t.stage, t.name, 'ok' if t.ok else 'FAIL', t.wall, len(t.sims), sum(1 for s in t.sims if s.get('hit'))))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('probe')
    ap.add_argument('--mode', choices=('full', 'quick'), default='full')
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 4) - 2))
    ap.add_argument('--models', default='4914;14742,4914', help="GATE_CHUNK_MS values for the product gate, ';'-separated")
    ap.add_argument('--poll-floor', type=int, default=None, help='GATE_POLL_FLOOR (required for an image with PAYLOAD_BUSY_POLL < 50)')
    ap.add_argument('--p2', default=None, help='payload in p2 (default: the one whose first four bytes the image pins)')
    ap.add_argument('--cross-p2', default=None)
    ap.add_argument('--writer', default=None, help='writer gate script file name in build/hook (default: matched by payload)')
    ap.add_argument('--ids', default='', help='quick mode: explicit product row ids, e.g. 64,65')
    ap.add_argument('--quick-since', default=None, help='quick mode: the image whose gate rows are the baseline (default: previous probe number)')
    ap.add_argument('--slow', action='store_true', help='original tools/cavesim.py, no cache (reference path)')
    ap.add_argument('--no-cache', '--fresh', dest='no_cache', action='store_true', help='bypass the raw-result cache (every simulator call runs; use for the run whose transcript is logged)')
    ap.add_argument('--cache-dir', default=os.path.join(CACHE_ROOT, 'results'))
    ap.add_argument('--report', default=None)
    a = ap.parse_args()
    if a.mode == 'full' and a.ids:
        sys.exit('--ids is a quick-mode option (a full run is the whole gate)')
    if a.slow:
        os.environ['GATE_FAST'] = '0'
    elif not a.no_cache:
        os.environ['GATE_RESULT_CACHE'] = a.cache_dir
    os.environ.setdefault('GATE_TABLE_CACHE', os.path.join(CACHE_ROOT, 'tables'))
    sys.path.insert(0, HERE)
    t_start = time.time()
    tasks, nsc, p2, floor, models = build_plan(a)
    banner = ('FULL GATE (flash gate)' if a.mode == 'full' else 'QUICK SUBSET -- NOT A FLASH GATE')
    print('=' * 100)
    print('%s: %s   p2=%s   poll-floor=%s   chunk models=%s   workers=%d   %s' % (banner, a.probe, p2, floor if floor is not None else 'default 50', models, a.jobs,
                                                                               'SLOW REFERENCE PATH' if a.slow else ('result cache ' + ('off' if a.no_cache else 'on'))))
    print('=' * 100, flush=True)
    rundir = os.path.join(CM, 'runs', '%s-%s-%s' % (a.probe, a.mode, time.strftime('%Y%m%d-%H%M%S')))
    os.makedirs(rundir, exist_ok=True)
    tasks.sort(key=lambda t: -t.est)
    done = []
    with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futs = [ex.submit(run_cmd, t, rundir) for t in tasks]
        for f in cf.as_completed(futs):
            t = f.result()
            done.append(t)
            print('%s %-10s %-34s %6.1fs  sims=%d hits=%d' % ('ok  ' if t.ok else 'FAIL', t.stage, t.name, t.wall, len(t.sims), sum(1 for s in t.sims if s.get('hit'))), flush=True)
            for d in t.detail if not t.ok else []:
                print('      -> ' + d)
    # summary
    wall = time.time() - t_start
    fails = [t for t in done if not t.ok]
    print('\n' + '-' * 100)
    by = {}
    for t in done:
        s = by.setdefault(t.stage, [0, 0, 0.0])
        s[0] += 1; s[1] += 0 if t.ok else 1; s[2] += t.wall
    print('%-11s %6s %6s %10s' % ('stage', 'tasks', 'failed', 'task-secs'))
    for k, (n, f, w) in sorted(by.items()):
        print('%-11s %6d %6d %10.1f' % (k, n, f, w))
    nsim = sum(len(t.sims) for t in done); nhit = sum(1 for t in done for s in t.sims if s.get('hit'))
    print('simulator calls %d (cache hits %d); summed task time %.0f s; wall %.0f s on %d workers' % (nsim, nhit, sum(t.wall for t in done), wall, a.jobs))
    print('\nslowest tasks:')
    for t in sorted(done, key=lambda t: -t.wall)[:8]:
        print('  %7.1fs  %s %s' % (t.wall, t.stage, t.name))
    # history for ordering (real, non-cached walls only)
    try:
        hist = json.load(open(os.path.join(CM, 'history.json')))
    except (OSError, ValueError):
        hist = {}
    for t in done:
        k = getattr(t, 'key', None)
        if k and t.ok and not any(s.get('hit') for s in t.sims):
            hist[k] = round(t.wall, 1)
    json.dump(hist, open(os.path.join(CM, 'history.json'), 'w'), indent=0, sort_keys=True)
    rep = {'probe': a.probe, 'mode': a.mode, 'p2': p2, 'poll_floor': floor, 'models': models, 'wall_s': round(wall, 1), 'workers': a.jobs, 'slow': a.slow,
           'tasks': [{'stage': t.stage, 'name': t.name, 'ok': t.ok, 'wall_s': round(t.wall, 2), 'sims': len(t.sims), 'hits': sum(1 for s in t.sims if s.get('hit')),
                      'detail': t.detail} for t in sorted(done, key=lambda t: (t.stage, t.name))]}
    rp = a.report or os.path.join(rundir, 'report.json')
    json.dump(rep, open(rp, 'w'), indent=1)
    write_md(os.path.splitext(rp)[0] + '-timing.txt', a, done, wall, nsim, nhit)
    print('report: ' + os.path.relpath(rp, ROOT))
    if fails:
        print('\nRESULT: %d TASK(S) FAILED -- %s' % (len(fails), ', '.join('%s %s' % (t.stage, t.name) for t in fails[:12])))
        return 1
    if a.mode == 'quick':
        print('\nRESULT: quick subset passed. THIS IS NOT A FLASH GATE (run without --mode quick). exit code 10.')
        return 10
    print('\nRESULT: FULL GATE PASSED (%s)' % a.probe)
    return 0


if __name__ == '__main__':
    sys.exit(main())
