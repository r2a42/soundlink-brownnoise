#!/usr/bin/env python3
"""gate_runner: run ANY existing gate script (gate_product.py, gate_stock_world.py, gate_probe30x.py ...) UNCHANGED, with its simulator calls
routed through the fast path (CM, 2026-10-22).

    python build/hook/gate_runner.py build/hook/gate_product.py probe310       # env GATE_* exactly as for the gate script itself

What it does, and nothing else: the gate scripts launch `python tools/cavesim.py ARGS` with subprocess.run and then judge the captured
text. This wrapper replaces subprocess.run for exactly those calls so that each

  1. (GATE_FAST != 0)  runs tools/cavesim_fast.py instead of tools/cavesim.py (cached decode tables; byte-identical output, proof in
     docs/deep/material-2026-10-19/CM-gate-streamlining.md section 4);
  2. (GATE_RESULT_CACHE=<dir>)  first looks for a stored RAW result (stdout, stderr, return code, p2-capture bytes) under a key made of
     the full argument list, the sha256 of every file the arguments name (words json, payload, staged file ...), the sha256 of the
     simulator sources and data tables, and GATE_FAST. The gate script then judges the raw text exactly as before, so an edited
     regex or scenario list can never be answered from a stale verdict; only the simulator run is skipped;
  3. (GATE_TIMING_LOG=<file>)  appends one JSON line per simulator call: wall seconds, cache hit, return code, argv tail.

GATE_FAST=0 runs the original tools/cavesim.py with no cache (the slow reference path used by the equivalence tests).
The gate script's own source is executed unmodified (runpy), including its sys.exit code.
"""
import base64
import hashlib
import json
import os
import runpy
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
FAST = os.environ.get('GATE_FAST', '1') != '0'
CACHE = os.environ.get('GATE_RESULT_CACHE') if FAST else None
TLOG = os.environ.get('GATE_TIMING_LOG')
_real_run = subprocess.run
_fcache = {}


def _fhash(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    k = (path, st.st_mtime_ns, st.st_size)
    h = _fcache.get(k)
    if h is None:
        h = _fcache[k] = hashlib.sha256(open(path, 'rb').read()).hexdigest()
    return h


_SIMDEP = None


def _sim_fingerprint():
    """sha256 over every tools/*.py (and tools/xapvm/*.py), the two json tables, the vm.app, and a (size, mtime) fingerprint of the internal_fs the world serves files from."""
    global _SIMDEP
    if _SIMDEP is None:
        h = hashlib.sha256()
        files = []
        for d in ('tools', os.path.join('tools', 'xapvm')):
            full = os.path.join(ROOT, d)
            files += sorted(os.path.join(full, f) for f in os.listdir(full) if f.endswith('.py'))
        files += [os.path.join(ROOT, 'tools', 'bose-stubs.json'), os.path.join(ROOT, 'tools', 'traps-bluelab73.json'),
                  os.path.join(ROOT, 'build', 'payload', 'staged_words.json'), os.path.join(ROOT, 'firmware', 'bose', 'extracted', 'internal_fs', 'vm.app')]
        for f in files:
            h.update((os.path.relpath(f, ROOT) + ':' + str(_fhash(f))).encode())
        ifs = os.path.join(ROOT, 'firmware', 'bose', 'extracted', 'internal_fs')
        for dp, _dn, fn in sorted(os.walk(ifs)):
            for f in sorted(fn):
                st = os.stat(os.path.join(dp, f))
                h.update(('%s:%d:%d' % (os.path.join(dp, f), st.st_size, st.st_mtime_ns)).encode())
        _SIMDEP = h.hexdigest()
    return _SIMDEP


def _named_files(argv):
    """sha256 of every existing file an argument names: the token itself, text after '=', with a leading '@' / 'file:' and a trailing ':VIS' removed."""
    out = {}
    for t in argv:
        if not isinstance(t, str) or len(t) > 400:
            continue
        cands = {t, t.split('=', 1)[-1]}
        for c in list(cands):
            for p in ('@', 'file:'):
                if c.startswith(p):
                    cands.add(c[len(p):])
            if ':' in c:
                cands.add(c.rsplit(':', 1)[0])
        for c in cands:
            c2 = c[1:] if c.startswith('@') else c
            if c2.startswith('file:'):
                c2 = c2[5:]
            p = c2 if os.path.isabs(c2) else os.path.join(ROOT, c2)
            if os.path.isfile(p):
                out[c2] = _fhash(p)
    return out


def _key(argv, cap_idx):
    a = list(argv)
    if cap_idx is not None:
        a[cap_idx + 1] = '<CAP>'
    ident = {'argv': a, 'files': _named_files(a), 'sim': _sim_fingerprint(), 'fast': FAST,
             'v': 1, 'pyhash': os.environ.get('PYTHONHASHSEED', '')}
    return hashlib.sha256(json.dumps(ident, sort_keys=True).encode()).hexdigest()


def _is_sim_call(args):
    return (isinstance(args, (list, tuple)) and len(args) >= 3 and args[0] == sys.executable
            and isinstance(args[1], str) and args[1].replace('\\', '/').endswith('tools/cavesim.py'))


def _log(rec):
    if TLOG:
        try:
            with open(TLOG, 'a', encoding='utf-8') as f:
                f.write(json.dumps(rec) + '\n')
        except OSError:
            pass


def run(args, *a, **kw):
    if not _is_sim_call(args):
        return _real_run(args, *a, **kw)
    args = list(args)
    tail = args[2:]
    cap_idx = tail.index('--p2-capture') if '--p2-capture' in tail else None
    cap_path = tail[cap_idx + 1] if cap_idx is not None else None
    t0 = time.time()
    key = path = None
    if CACHE:
        key = _key(tail, cap_idx)
        path = os.path.join(CACHE, key[:2], key + '.json')
        if os.path.exists(path):
            try:
                rec = json.load(open(path, encoding='utf-8'))
                out, err = rec['stdout'], rec['stderr']
                if cap_path:
                    if rec.get('cap') is not None:
                        open(cap_path, 'wb').write(base64.b64decode(rec['cap']))
                    if rec.get('cap_path'):
                        out, err = out.replace(rec['cap_path'], cap_path), err.replace(rec['cap_path'], cap_path)
                _log({'t': round(time.time() - t0, 3), 'hit': True, 'rc': rec['rc'], 'argv': tail[:1] + tail[-24:], 'key': key[:12]})
                return subprocess.CompletedProcess(args, rec['rc'], out, err)
            except (OSError, ValueError, KeyError):
                pass
    if FAST:
        args[1] = os.path.join(ROOT, 'tools', 'cavesim_fast.py')
    r = _real_run(args, *a, **kw)
    dt = time.time() - t0
    _log({'t': round(dt, 3), 'hit': False, 'rc': r.returncode, 'argv': tail[:1] + tail[-24:], 'key': key[:12] if key else None, 'fast': FAST})
    if CACHE and isinstance(r.stdout, str):
        try:
            rec = {'rc': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr or '', 'argv': tail, 'wall': dt,
                   'cap': base64.b64encode(open(cap_path, 'rb').read()).decode() if cap_path and os.path.exists(cap_path) else None,
                   'cap_path': cap_path}
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + '.%d.tmp' % os.getpid()
            json.dump(rec, open(tmp, 'w', encoding='utf-8'))
            os.replace(tmp, path)
        except OSError:
            pass
    return r


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('usage: gate_runner.py <gate script> [args]')
    script = os.path.abspath(sys.argv[1])
    sys.argv = [script] + sys.argv[2:]
    subprocess.run = run
    if FAST and os.environ.get('GATE_TABLE_CACHE') is None:
        import tempfile
        os.environ['GATE_TABLE_CACHE'] = os.path.join(os.environ.get('GATE_CACHE_ROOT') or os.path.join(tempfile.gettempdir(), 'csr8670_gate_cache'), 'tables')
    sys.path.insert(0, os.path.dirname(script))
    runpy.run_path(script, run_name='__main__')
