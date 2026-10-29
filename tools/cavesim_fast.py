#!/usr/bin/env python3
"""cavesim_fast: run tools/cavesim.py unchanged, with three result-identical speed-ups (CM, 2026-10-22):
    python tools/cavesim_fast.py <exactly the arguments of tools/cavesim.py>
  1. tools/xapemu_fast.py        the decode tables of xapemu.VM.run are built once per image, not once per simulated event
  2. tools/cavesim_world_fast.py the SourceMap window is stored into RAM in bulk when that is provably the same as the element loop
  3. tools/caveguard_fast.py     the two whole-image static checks at start-up are memoised
Output (stdout, stderr, exit code, --p2-capture file) is byte-identical to tools/cavesim.py; proof and the evidence tables:
docs/deep/material-2026-10-19/CM-gate-streamlining.md section 4. If an anchor in a stock source no longer matches, the affected patch is skipped
with one stderr line (slower, still correct)."""
import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import xapemu_fast  # noqa: F401,E402  (registers itself as `xapemu`)
try:
    import cavesim_world_fast  # noqa: F401,E402  (registers itself as `cavesim_world`)
except ImportError as _e:
    sys.stderr.write('cavesim_fast: world patch not applied (%s); running the stock cavesim_world\n' % _e)
try:
    import caveguard
    import caveguard_fast
    caveguard_fast.install(caveguard)
except Exception as _e:
    sys.stderr.write('cavesim_fast: caveguard memo not applied (%s)\n' % _e)
sys.argv[0] = os.path.join(HERE, 'cavesim.py')
runpy.run_path(sys.argv[0], run_name='__main__')
