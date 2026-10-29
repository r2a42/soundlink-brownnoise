#!/usr/bin/env python3
"""Offline world-model gate for probe184a and probe184 (T08) and, since round 3 (B02), their variants
(narrow184_lib.PROBES: probe184a_58k, probe184_58k, probe184_90k).

    python build/hook/assemble_probe184a.py && python build/hook/gate_probe184.py probe184a
    python build/hook/assemble_probe184.py  && python build/hook/gate_probe184.py probe184
    python build/hook/gate_probe184.py probe184_58k       # or probe184a_58k, probe184_90k

Runs the real words (build/hook/probe184a_words.json / probe184_words.json) through tools/cavesim.py's
clocked world model, one scripted scenario per line, each checked with the simulator's own --expect
plus checks this gate adds.  Exit 0 = every scenario holds.

TWO DEPARTURES FROM THE STOCK WORLD MODEL, both done here (tools/cavesim*.py are not edited):

  1. SourceMap delivers ONE BYTE PER 16-BIT WORD.  tools/cavesim_world.py packs two file bytes per
     word (`--src-endian le|be`), which is the packing probe141 and the 2026-10-10 184 plan assumed.
     Every stock reader treats the map as one byte per word (narrow184_lib.py, the unit rule), so
     this gate replaces World.src_map with the unpacked form (capped at 4,096 elements; the cave
     only indexes elements < 64).  `--packed` runs the whole battery with the old packing: the cave
     must then stop at MISMATCH before it touches p2 (that is the point of its pre-erase look).
  2. The bytes the cave writes to p2 are CAPTURED (a wrapper on memmove while the p2 sink is open),
     so a scenario can check them against the ROFS byte for byte.  The stock model only counts
     claims, flushes and bytes.

The staged data_us (the file the cave opens) is the EDITED data_us of narrow184_lib.stage(), written
to a temp file and given to the world with --fs-add NowSpeakTTS/data_us=@file, so the gather runs
over exactly the bytes the built DFU carries.

What it cannot cover: whether the firmware agrees (SourceMap packing, window size, SourceDrop
semantics, SinkClaim/flush units, the VM watchdog over a 3,400-iteration loop, flash write time).
Those are the questions of the press, not of this gate.
"""
import contextlib
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'xapvm'))
sys.path.insert(0, HERE)
os.chdir(ROOT)
import narrow184_lib as L          # noqa: E402
import cavesim                     # noqa: E402
import cavesim_world as cw         # noqa: E402

PACKED = '--packed' in sys.argv
CAP = []                           # bytes memmoved while the p2 sink was open, one entry per call
LAST = {}                          # the last World instance
LIMIT = {'n': None, 'calls': 0}    # SourceSize returns 0 after this many calls (None: never)
SRC_CAP = 4096


def src_map_bytes(self, s):
    """SourceMap, one byte per 16-bit word (the device convention; see the module docstring)."""
    n = self.src_size(s)
    data = s['data'][s['pos']:s['pos'] + n][:SRC_CAP]
    for i, b in enumerate(data):
        self.vm.wr(cw.SRC_MAP_BASE + i, b)
    return cw.SRC_MAP_BASE


_orig_init = cw.World.__init__
_orig_install = cw.World.install
_orig_map = cw.World.src_map


def _init(self, *a, **k):
    _orig_init(self, *a, **k)
    LAST['w'] = self


def _install(self):
    _orig_install(self)
    t = self.trapnums['memmove']
    base = self.vm.STUB_RET[t]

    def mm(trap, ahal, a2, base=base):
        r = base(trap, ahal, a2) if callable(base) else base
        dst, n = ahal & 0xFFFF, (a2 >> 16) & 0xFFFF
        if self.p2['open'] and not self.p2['closed']:
            CAP.append(bytes(self.vm.rd((dst + k) & 0xFFFF) & 0xFF for k in range(n)))
        return r
    self.vm.STUB_RET[t] = mm
    t2 = self.trapnums['SourceSize']
    base2 = self.vm.STUB_RET[t2]

    def ss(trap, ahal, a2, base=base2):       # SourceSize answers 0 after LIMIT['n'] calls (a window that dries up)
        LIMIT['calls'] += 1
        if LIMIT['n'] is not None and LIMIT['calls'] > LIMIT['n']:
            return (0, 0)
        return base(trap, ahal, a2) if callable(base) else base
    self.vm.STUB_RET[t2] = ss


cw.World.__init__ = _init
cw.World.install = _install


def run(probe, args, expects, mapmode=None, size_calls=None):
    """One cavesim world run in-process.  Returns (rc, stdout text, world).  mapmode: None = the
    battery default (bytes, or packed with --packed), 'packed' = the stock model's two bytes per word."""
    cw.World.src_map = (_orig_map if (mapmode == 'packed' or PACKED) else src_map_bytes)
    del CAP[:]
    LAST.clear()
    LIMIT['n'], LIMIT['calls'] = size_calls, 0
    argv = ['cavesim.py', probe, '--entry', '0x3E21D'] + args
    for e in expects:
        argv += ['--expect', e]
    old = sys.argv
    sys.argv = argv
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = cavesim.main()
    finally:
        sys.argv = old
    return rc, buf.getvalue(), LAST.get('w')


def main():
    probe = (sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else 'probe184a')
    assert probe in L.PROBES, (probe, sorted(L.PROBES))      # round 3 (B02): the variants of narrow184_lib.PROBES
    is_a = L.PROBES[probe]['a']
    vkey = L.PROBES[probe]['vkey']
    sp = L.PROBES[probe]['sp']
    adpcm = L.adpcm(vkey)
    rofs, _ = L.rofs(adpcm)
    stg = L.stage(rofs, sp)
    periods = stg['periods']
    tmp = tempfile.mkdtemp(prefix='gate184_')
    staged = os.path.join(tmp, 'data_us_staged.bin')
    open(staged, 'wb').write(stg['new_us'])
    stock = os.path.join(tmp, 'data_us_stock.bin')
    open(stock, 'wb').write(open(L.DATA_US_FILE, 'rb').read())
    p2file = os.path.join(tmp, 'brown.adpcm')
    open(p2file, 'wb').write(adpcm)
    def rel(p):      # cavesim_world splits --fs-add values at the first ':' (a Windows drive letter breaks it)
        return os.path.relpath(p, ROOT).replace(os.sep, '/')
    STAGED = ['--fs-add', 'NowSpeakTTS/data_us=@' + rel(staged)]
    P2FILE = ['--fs-add', 'brown.adpcm=@' + rel(p2file) + ':p2']
    # the emulator's default step cap (200,000) is too small for 1,270 skip steps + 2,156 periods
    START = ['--press', '0:4004', '--once', '--steps', '6000000']
    # the id table of assemble_probe184.py (nine classes; the world prints ids in lower-case hex without padding)
    ID = dict(NOOPEN='38', NOWIN='37', MISMATCH='36', EOPEN='14', GATHER='14', DIGEST='14',
              INCOMPLETE='15', GETINFO='15')
    if is_a:
        ID.update(F_ROOT='12', F_MOUNT='35', MISSING='b', NOMOUNT='3f')
    else:
        ID.update(VALID='12')

    def ex(*kv):
        return list(kv)

    quiet = ['violations=0', 'chunks=0', 'pending=0']
    ok_id = ID['F_ROOT'] if is_a else ID['VALID']
    cases = []   # (name, args, expects, check(world, out) -> list of failure strings)

    def content_ok(w, out):
        bad = []
        got = b''.join(CAP)
        if got != stg['padded']:
            bad.append('p2 content: %d bytes captured, %s the ROFS (%d bytes)'
                       % (len(got), 'differ from' if len(got) == len(stg['padded']) else 'length differs from',
                          len(stg['padded'])))
        if w.p2['flushes'] != periods or w.p2['bytes'] != periods * 28 or w.p2['claims'] != periods:
            bad.append('p2 flush bookkeeping: %d flushes %d bytes %d claims (want %d / %d / %d)'
                       % (w.p2['flushes'], w.p2['bytes'], w.p2['claims'], periods, periods * 28, periods))
        if not (w.p2['erased'] and w.p2['closed'] and w.p2['digest'] == 3):
            bad.append('p2 sink: erased=%s closed=%s digest=%s' % (w.p2['erased'], w.p2['closed'], w.p2['digest']))
        return bad

    def untouched(w, out):
        bad = []
        if w.p2['erased'] or w.p2['open'] or CAP:
            bad.append('p2 was touched before a stop that must come BEFORE the erase '
                       '(erased=%s open=%s memmoves=%d)' % (w.p2['erased'], w.p2['open'], len(CAP)))
        return bad

    def erased_not_valid(w, out):
        bad = []
        if not w.p2['erased']:
            bad.append('expected the erase to have been issued')
        return bad

    if is_a:
        cases += [
            ('HAPPY, firmware puts p2 in the union at once: root FileFind finds it -> F_ROOT',
             STAGED + P2FILE + START + ['--p2-automount'], ex(*quiet, 'spoken=' + ID['F_ROOT'], 'swallowed=1', 'replayed=0'),
             content_ok),
            ('HAPPY, only the cave mount shows it: root miss, mount, found -> F_MOUNT',
             STAGED + P2FILE + START, ex(*quiet, 'spoken=' + ID['F_MOUNT']), content_ok),
            ('written but not visible even after the mount (file absent from the model) -> MISSING',
             STAGED + START, ex(*quiet, 'spoken=' + ID['MISSING']), content_ok),
            ('mount refused (RAW_SERIAL type reading) -> NOMOUNT',
             STAGED + P2FILE + START + ['--fail', 'PartitionMountFilesystem'],
             ex(*quiet, 'spoken=' + ID['NOMOUNT']), content_ok),
        ]
    else:
        cases += [
            ('HAPPY: the ROFS is gathered, committed, STATE VALID -> VALID',
             STAGED + START, ex(*quiet, 'spoken=' + ID['VALID'], 'swallowed=1', 'replayed=0'), content_ok),
        ]
    cases += [
        ('closed but STATE != VALID (--pinfo 2:3=1) -> INCOMPLETE',
         STAGED + START + ['--pinfo', '2:3=1'], ex(*quiet, 'spoken=' + ID['INCOMPLETE']), content_ok),
        ('GetInfo refuses after the close -> GETINFO',
         STAGED + START + ['--fail', 'PartitionGetInfo'], ex(*quiet, 'spoken=' + ID['GETINFO']), content_ok),
        # ---- stops BEFORE the erase
        ('FileFind refused on the directory -> NOOPEN, p2 untouched',
         STAGED + START + ['--fail', 'FileFind'], ex(*quiet, 'spoken=' + ID['NOOPEN']), untouched),
        ('FileFind refused on data_us (2nd call) -> NOOPEN, p2 untouched',
         STAGED + START + ['--fail-after', 'FileFind=2'], ex(*quiet, 'spoken=' + ID['NOOPEN']), untouched),
        ('StreamFileSource refused -> NOOPEN, p2 untouched',
         STAGED + START + ['--fail', 'StreamFileSource'], ex(*quiet, 'spoken=' + ID['NOOPEN']), untouched),
        ('the source window is 32 bytes (< 64): the first ADVANCE refuses -> NOWIN, p2 untouched',
         STAGED + START + ['--src-window', '32'], ex(*quiet, 'spoken=' + ID['NOWIN']), untouched),
        ('SourceMap returns 0 at the look before the erase -> NOWIN, p2 untouched',
         STAGED + START + ['--fail', 'SourceMap'], ex(*quiet, 'spoken=' + ID['NOWIN']), untouched),
        ('the stock data_us (nothing staged) -> MISMATCH at map+18, p2 untouched',
         START, ex(*quiet, 'spoken=' + ID['MISMATCH']), untouched),
        # ---- failures AFTER the erase (the sink is closed first)
        ('the p2 sink would not open -> EOPEN',
         STAGED + START + ['--fail', 'StreamPartitionOverwriteSink'], ex(*quiet, 'spoken=' + ID['EOPEN']),
         lambda w, o: []),
        ('SinkFlush refuses on the 50th period -> GATHER, sink closed (INCOMPLETE p2)',
         STAGED + START + ['--fail-after', 'SinkFlush=50'], ex(*quiet, 'spoken=' + ID['GATHER']),
         lambda w, o: ([] if w.p2['closed'] and w.p2['flushes'] == 50 else
                        ['sink not closed / flushes=%d (want 50: 49 good + the refused one)' % w.p2['flushes']])),
        ('SinkMap returns 0 (claim pointer 0) -> GATHER on the first period',
         STAGED + START + ['--fail', 'SinkMap'], ex(*quiet, 'spoken=' + ID['GATHER']),
         lambda w, o: ([] if w.p2['closed'] and w.p2['flushes'] == 0 else ['sink not closed / flushes=%d' % w.p2['flushes']])),
        ('SourceMap refuses mid-loop (5th call = the 4th period) -> GATHER',
         STAGED + START + ['--fail-after', 'SourceMap=5'], ex(*quiet, 'spoken=' + ID['GATHER']),
         lambda w, o: ([] if w.p2['closed'] and w.p2['flushes'] == 3 else ['flushes=%d (want 3)' % w.p2['flushes']])),
        ('the window dries up mid-gather (SourceSize answers 0 from the 12th period on) -> GATHER, sink closed',
         STAGED + START, (ex(*quiet, 'spoken=' + ID['GATHER']), sp + 11),
         lambda w, o: ([] if w.p2['closed'] and w.p2['flushes'] == 12 else
                        ['closed=%s flushes=%d (want 12)' % (w.p2['closed'], w.p2['flushes'])])),
        ('PartitionSetMessageDigest refuses -> DIGEST, sink closed',
         STAGED + START + ['--fail', 'PartitionSetMessageDigest'], ex(*quiet, 'spoken=' + ID['DIGEST']),
         lambda w, o: ([] if w.p2['closed'] and w.p2['flushes'] == periods else ['closed=%s flushes=%d' % (w.p2['closed'], w.p2['flushes'])])),
        ('the source window is exactly 64 bytes: still enough for every ADVANCE -> same result as the happy path',
         STAGED + START + ['--src-window', '64'] + (P2FILE + ['--p2-automount'] if is_a else []),
         ex(*quiet, 'spoken=' + ok_id), content_ok),
        ('the source window is 4,096 bytes -> same result as the happy path',
         STAGED + START + ['--src-window', '4096'] + (P2FILE + ['--p2-automount'] if is_a else []),
         ex(*quiet, 'spoken=' + ok_id), content_ok),
        ('the source window is 63 bytes (< 64) -> NOWIN, p2 untouched',
         STAGED + START + ['--src-window', '63'], ex(*quiet, 'spoken=' + ID['NOWIN']), untouched),
        ('SourceMap packs two bytes per word, little endian (the 2026-10-10 model): MISMATCH, p2 untouched',
         (STAGED + START + ['--src-endian', 'le'], 'packed'), ex(*quiet, 'spoken=' + ID['MISMATCH']), untouched),
        ('SourceMap packs two bytes per word, big endian: MISMATCH, p2 untouched',
         (STAGED + START + ['--src-endian', 'be'], 'packed'), ex(*quiet, 'spoken=' + ID['MISMATCH']), untouched),
        # ---- not our event
        ('a non-0x4004 event is replayed to the stock, nothing else happens',
         ['--press', '0:4003', '--once', '--steps', '6000000'] + STAGED, ex(*quiet, 'spoken=', 'replayed=1', 'swallowed=0'), untouched),
    ]

    bad = 0
    for name, args, expects, check in cases:
        mapmode, size_calls = None, None
        if isinstance(args, tuple):             # (args, 'packed'): the stock model's SourceMap packing
            args, mapmode = args
        if isinstance(expects, tuple):          # (expects, n): SourceSize answers 0 after n calls
            expects, size_calls = expects
        rc, out, w = run(probe, args, expects, mapmode, size_calls)
        got = [l for l in out.splitlines() if l.startswith('expect ')]
        okk = rc == 0 and len(got) == len(expects) and all(l.endswith('PASS') for l in got)
        extra = []
        if okk and w is not None:
            extra = check(w, out)
            open_src = [x['path'] for x in w.sources.values() if not x['closed']]
            if open_src:
                extra.append('file source(s) left open: %s' % open_src)
            okk = not extra
        print('%-4s %s' % ('PASS' if okk else 'FAIL', name))
        if not okk:
            bad += 1
            print('     args: ' + ' '.join(args))
            for l in got:
                if not l.endswith('PASS'):
                    print('     ' + l)
            for e in extra:
                print('     ' + e)
            if rc and not got:
                print((out)[-900:])
    # ---- round 3 (B02): the same happy path through cavesim's NATIVE world options (T14: --src-unpacked,
    # --p2-capture), in a fresh process, with no monkeypatch of this file in play.  Independent of the battery above.
    if not PACKED:
        import subprocess
        capf = os.path.join(tmp, 'p2_capture.bin')
        cmd = [sys.executable, os.path.join(ROOT, 'tools', 'cavesim.py'), probe, '--entry', '0x3E21D',
               '--fs-add', 'NowSpeakTTS/data_us=@' + rel(staged), '--src-unpacked', '--p2-capture', capf,
               '--press', '0:4004', '--once', '--steps', '6000000',
               '--expect', 'spoken=' + ok_id, '--expect', 'violations=0'] + (
                   ['--fs-add', 'brown.adpcm=@' + rel(p2file) + ':p2', '--p2-automount'] if is_a else [])
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=900)
        passes = [l for l in r.stdout.splitlines() if l.startswith('expect ')]
        cap_ok = os.path.exists(capf) and open(capf, 'rb').read() == stg['padded']
        okk = r.returncode == 0 and len(passes) == 2 and all(l.endswith('PASS') for l in passes) and cap_ok
        print('%-4s %s' % ('PASS' if okk else 'FAIL',
                           'NATIVE cross-check (cavesim --src-unpacked --p2-capture, no monkeypatch): happy path, '
                           'capture == the padded ROFS (%d bytes)' % len(stg['padded'])))
        if not okk:
            bad += 1
            print('     rc=%s capture_ok=%s' % (r.returncode, cap_ok))
            print((r.stdout + r.stderr)[-900:])
        total = len(cases) + 1
    else:
        total = len(cases)
    print('%d scenarios, %d failed%s' % (total, bad, ' (--packed: expect failures)' if PACKED else ''))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
