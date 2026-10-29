#!/usr/bin/env python3
"""xapemu_fast: tools/xapemu.py with ONE change, derived from the live file at import time (CM, 2026-10-22).

The only difference from tools/xapemu.py is how VM.run obtains its two lookup tables:

    ins   = {addr: (op, v, ln)}   the folded decode of the whole code, overlaid with the unfolded decode of the cave spans
    stubs = {addr: trap}          xapvm.find_stubs(code)

The stock VM.run rebuilds both from scratch on EVERY call (three full decodes of the ~230,000-word image, ~5 s) and cavesim calls
VM.run once per simulated event (a press, a timer, a DSP reply: hundreds to 12,000 times per scenario). This module computes the
tables once per (code content, nofold spans, xapvm source) and reuses them. The interpreter body below the table setup is
the stock source text, unchanged (this module builds itself by replacing exactly the setup block of the stock source and
refuses to load if the block is not found, so a later edit to xapemu.py can never be silently bypassed).

Soundness: `ins` and `stubs` are only READ by the interpreter loop (it never assigns ins[...] or stubs[...]). They are functions of
(vm.code, vm.nofold, xapvm.decode, xapvm.find_stubs) only. The cache key is the sha256 of the code words + the repr of nofold +
the sha256 of tools/xapvm/xapvm.py. Within one process the key is computed once per code list object (identity); an atexit
check re-hashes the code and FAILS the process (exit code 97) if the list was mutated after the tables were built.
GATE_FAST_VERIFY=1 re-hashes on every call instead (slow; used by the equivalence tests).
Disk cache (optional, GATE_TABLE_CACHE=<dir>): the tables pickled under their key, so a fresh process skips the ~8 s build.

Use: `import xapemu_fast` BEFORE `import xapemu` registers it as the module `xapemu` (tools/cavesim_fast.py does this).
"""
import atexit
import hashlib
import os
import pickle
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_PATH = os.path.join(HERE, 'xapemu.py')

_SETUP_BEGIN = "        ins = {}\n        for a, op, v, ln in xapvm.decode(self.code):\n"
_SETUP_END = "        stubs, _ = xapvm.find_stubs(self.code)\n"

STATS = {'builds': 0, 'mem_hits': 0, 'disk_hits': 0, 'disk_writes': 0}
_MEM = {}          # key -> (ins, stubs)
_BY_ID = {}        # id(code list) -> (code list, key, digest)  (the list object is held so the id cannot be reused)


def _xapvm_sha():
    return hashlib.sha256(open(os.path.join(HERE, 'xapvm', 'xapvm.py'), 'rb').read()).hexdigest()


def _digest(code):
    import array
    return hashlib.sha256(array.array('H', code).tobytes()).hexdigest()


def _spans_repr(nofold):
    if not nofold:
        return 'none'
    spans = nofold if isinstance(nofold, list) else [nofold]
    return repr([tuple(x) for x in spans])


def _tables(vm, xapvm):
    code = vm.code
    spans = _spans_repr(vm.nofold)
    verify = os.environ.get('GATE_FAST_VERIFY') == '1'
    ent = _BY_ID.get(id(code))
    if ent is not None and ent[0] is code and not verify and ent[3] == spans:
        return _MEM[ent[1]]
    dg = _digest(code)
    key = hashlib.sha256((dg + '|' + spans + '|' + _xapvm_sha()).encode()).hexdigest()
    if ent is not None and ent[0] is code and ent[2] != dg:
        raise RuntimeError('xapemu_fast: vm.code was mutated after the decode tables were built')
    _BY_ID[id(code)] = (code, key, dg, spans)
    if key in _MEM:
        STATS['mem_hits'] += 1
        return _MEM[key]
    cdir = os.environ.get('GATE_TABLE_CACHE')
    path = os.path.join(cdir, key[:32] + '.pkl') if cdir else None
    if path and os.path.exists(path):
        try:
            with open(path, 'rb') as f:
                tabs = pickle.load(f)
            _MEM[key] = tabs
            STATS['disk_hits'] += 1
            return tabs
        except Exception:
            pass
    # ---- the stock computation, verbatim (xapemu.VM.run) ----
    ins = {}
    for a, op, v, ln in xapvm.decode(code):
        ins[a] = (op, v, ln)
    if vm.nofold:
        sp = vm.nofold if isinstance(vm.nofold, list) else [vm.nofold]
        for a, op, v, ln in xapvm.decode(code, fold_zero=False):
            if any(lo <= a <= hi for lo, hi in sp):
                ins[a] = (op, v, ln)
    stubs, _ = xapvm.find_stubs(code)
    # ---------------------------------------------------------
    STATS['builds'] += 1
    _MEM[key] = (ins, stubs)
    if path:
        try:
            os.makedirs(cdir, exist_ok=True)
            tmp = path + '.%d.tmp' % os.getpid()
            with open(tmp, 'wb') as f:
                pickle.dump((ins, stubs), f, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, path)
            STATS['disk_writes'] += 1
        except Exception:
            pass
    return _MEM[key]


def _exit_check():
    for code, key, dg, _sp in list(_BY_ID.values()):
        if _digest(code) != dg:
            sys.stderr.write('xapemu_fast: vm.code changed after the tables were built; results are NOT valid\n')
            os._exit(97)


def _load():
    src = open(SRC_PATH, encoding='utf-8').read()
    i = src.find(_SETUP_BEGIN)
    j = src.find(_SETUP_END)
    if i < 0 or j < i or src.count(_SETUP_BEGIN) != 1 or src.count(_SETUP_END) != 1:
        raise ImportError('xapemu_fast: the table-setup block of tools/xapemu.py was not found exactly once; refusing to patch')
    j += len(_SETUP_END)
    new = src[:i] + "        ins, stubs = _fast_tables(self, xapvm)\n" + src[j:]
    mod = types.ModuleType('xapemu')
    mod.__file__ = SRC_PATH
    mod._fast_tables = _tables
    sys.modules['xapemu'] = mod
    exec(compile(new, SRC_PATH, 'exec'), mod.__dict__)
    return mod


if 'xapemu' in sys.modules and not getattr(sys.modules['xapemu'], '_fast_tables', None):
    raise ImportError('xapemu_fast must be imported before xapemu')
xapemu = _load()
atexit.register(_exit_check)
