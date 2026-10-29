#!/usr/bin/env python3
"""cavesim_world_fast: tools/cavesim_world.py with ONE change, derived from the live file at import time (CM, 2026-10-22).

The world model's SourceMap handler (World.src_map) stores the mapped window into the VM's RAM ONE ELEMENT AT A TIME through VM.wr (up to 4,096
elements per call, 2,106 calls per writer-gate run: ~8.6 million Python-level calls, the dominant cost of every writer-gate scenario). This
module replaces exactly those store loops by one bulk store of the same words into the same RAM bytes when (and only when) that is provably the
same thing:
  - VM.trace_mem is False (no memory log to feed),
  - the destination range lies wholly below the const window and above address 0 (no special register 0xFFE0..0xFFE4, no read-only const cell,
    no address wrap),
  - the VM's wr is either the class method or cavesim's caller-frame guard whose protected addresses are outside the destination range,
  - the host is little-endian.
Otherwise the original element loop runs. The element list itself is built identically ([0xDD]*lead + the window bytes, the unpacked-map rule), only
with C-speed list(bytes) instead of a per-element comprehension when no --src-hibyte / --src-hijunk is set.
Like xapemu_fast, the module is built from the stock source by replacing text anchors that must each occur exactly once; otherwise ImportError.
"""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_PATH = os.path.join(HERE, 'cavesim_world.py')

A1_OLD = "            els = [0xDD] * lead + [(b << 8) if hib else (b | junk) for b in data]\n"
A1_NEW = "            els = [0xDD] * lead + ([b << 8 for b in data] if hib else (list(data) if not junk else [b | junk for b in data]))\n"
A2_OLD = ("            for i, v in enumerate(els[:cap]):\n"
          "                self.vm.wr(SRC_MAP_BASE + i, v)\n"
          "            return SRC_MAP_BASE\n")
A2_NEW = ("            _bulk_wr(self.vm, SRC_MAP_BASE, els[:cap])\n"
          "            return SRC_MAP_BASE\n")
A3_OLD = ("        for i, v in enumerate(words):\n"
          "            self.vm.wr(SRC_MAP_BASE + i, v)\n"
          "        return SRC_MAP_BASE\n")
A3_NEW = ("        _bulk_wr(self.vm, SRC_MAP_BASE, words)\n"
          "        return SRC_MAP_BASE\n")

HELPER = '''
def _bulk_wr(vm, base, vals):
    """Store vals at base, base+1, ... exactly as `for i, v in enumerate(vals): vm.wr(base + i, v)` would (see tools/cavesim_world_fast.py)."""
    import sys as _sys
    from array import array as _array
    if isinstance(vals, (bytes, bytearray)):
        vals = list(vals)
    n = len(vals)
    ok = (n > 0 and _sys.byteorder == 'little' and not vm.trace_mem and 0 < base and base + n <= vm.CONST_BASE)
    if ok and 'wr' in vm.__dict__:                       # an instance-level wr: only cavesim's caller-frame guard is understood
        w = vm.wr
        d = getattr(w, '__defaults__', None)
        ret = d[1] if (getattr(w, '__name__', '') == '_guarded_wr' and d and len(d) >= 2) else None
        if ret is None or any(base <= a < base + n for a in ret):
            ok = False
    if ok:
        try:
            raw = _array('H', [v & 0xFFFF for v in vals] if max(vals) > 0xFFFF else vals).tobytes()
        except (OverflowError, TypeError):
            ok = False
    if ok:
        vm.ram[2 * base:2 * base + 2 * n] = raw
        return
    for i, v in enumerate(vals):
        vm.wr(base + i, v)
'''


def _load():
    src = open(SRC_PATH, encoding='utf-8').read()
    for old in (A1_OLD, A2_OLD, A3_OLD):
        if src.count(old) != 1:
            raise ImportError('cavesim_world_fast: an anchor of tools/cavesim_world.py was not found exactly once; refusing to patch')
    new = src.replace(A1_OLD, A1_NEW).replace(A2_OLD, A2_NEW).replace(A3_OLD, A3_NEW) + '\n' + HELPER
    mod = types.ModuleType('cavesim_world')
    mod.__file__ = SRC_PATH
    sys.modules['cavesim_world'] = mod
    try:
        exec(compile(new, SRC_PATH, 'exec'), mod.__dict__)
    except BaseException:
        sys.modules.pop('cavesim_world', None)
        raise
    return mod


cavesim_world = _load()
