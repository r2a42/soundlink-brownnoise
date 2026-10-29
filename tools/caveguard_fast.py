#!/usr/bin/env python3
"""caveguard_fast: memoise the two whole-image static checks cavesim runs at every start (CM, 2026-10-22).

caveguard.stray_tail_ops(code, spans, stubs) and caveguard.tail_branches(code, spans) each decode the ~230,000-word image (unfolded) and filter by the cave
spans: ~1.3 s of every simulator process, repeated for each of the hundreds of scenarios of a gate although the answer depends only on the code words,
the spans and (for the first) the synthesised-stub table. Both are pure functions of those arguments. The wrapped functions below return the
stored result of an earlier identical call, keyed by sha256(code words | repr(spans) | repr(stubs) | function name | sha256 of caveguard.py and xapvm.py),
in memory and (GATE_TABLE_CACHE=<dir>) on disk. A miss runs the ORIGINAL function and stores its result unchanged.
"""
import array
import hashlib
import os
import pickle

HERE = os.path.dirname(os.path.abspath(__file__))
STATS = {'hits': 0, 'misses': 0}
_MEM = {}


def _src_sha():
    h = hashlib.sha256()
    for p in (os.path.join(HERE, 'caveguard.py'), os.path.join(HERE, 'xapvm', 'xapvm.py')):
        h.update(open(p, 'rb').read())
    return h.hexdigest()


def install(caveguard):
    base = _src_sha()
    cdir = os.environ.get('GATE_TABLE_CACHE')

    def wrap(name):
        orig = getattr(caveguard, name)

        def f(*args):
            code = args[0]
            key = hashlib.sha256((base + '|' + name + '|' + hashlib.sha256(array.array('H', code).tobytes()).hexdigest() + '|' +
                                  '|'.join(repr(a) for a in args[1:])).encode()).hexdigest()
            if key in _MEM:
                STATS['hits'] += 1
                return list(_MEM[key])
            path = os.path.join(cdir, key[:32] + '.cg.pkl') if cdir else None
            if path and os.path.exists(path):
                try:
                    _MEM[key] = pickle.load(open(path, 'rb'))
                    STATS['hits'] += 1
                    return list(_MEM[key])
                except Exception:
                    pass
            STATS['misses'] += 1
            r = orig(*args)
            _MEM[key] = list(r)
            if path:
                try:
                    os.makedirs(cdir, exist_ok=True)
                    tmp = path + '.%d.tmp' % os.getpid()
                    pickle.dump(_MEM[key], open(tmp, 'wb'))
                    os.replace(tmp, path)
                except OSError:
                    pass
            return r
        f.__wrapped__ = orig
        setattr(caveguard, name, f)
    for n in ('stray_tail_ops', 'tail_branches'):
        wrap(n)
