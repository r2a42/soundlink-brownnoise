#!/usr/bin/env python3
"""Offline world-model gate for probe199s (D1: the READ-ONLY file-source diagnostic on the STOCK data_us) -- 2026-10-14.
NOT independently reviewed. NO device, no flash tool: pure emulation.

Runs the real words (build/hook/probe199s_words.json, written by assemble_probe199s.py) through tools/cavesim.py's clocked world
model. The file the cave opens is the STOCK data_us (the world's default, firmware/bose/extracted/internal_fs/data_us). Every row's
expected id sequence comes from an INDEPENDENT reference model written here (ref_ids): the diagnostic's decision tree re-stated in
Python over the stock bytes and the row's world parameters (window, element layout, drop advance, map shift / failure), not read off
the cave. Hard-coded cross-checks pin the reference model on the key rows.

    python build/hook/assemble_probe199s.py                     # first (writes probe199s_words.json)
    python build/hook/gate_probe199s.py [--part I/N] [--list] [--words PATH]
    --words PATH  runs a mutated copy of the words: the gate must FAIL there (mutation rows)
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
US = open(os.path.join(ROOT, 'firmware', 'bose', 'extracted', 'internal_fs', 'data_us'), 'rb').read()
assert len(US) == 219528

# ------------------------------------------------------------------ the reference model (independent of the cave's code)
WIN = 3072                       # SourceSize of a file source = min(bytes left, 0xC00) (stack 0x55a97)
CHECKPOINTS = (1, 100, 1000, 1320)
IDS = dict(guard=0x3C, nosrc=0x17,
           clean=0x12, junk=0x13, packed=0x14, other=0x15, nomap=0x16,
           ok=0x30, f1320=0x2E, f1000=0x2C, f100=0x2A, f1=0x28,
           exact=0x3E, over=0x3D, under=0x39, stuck=0x24, w0=0x1B)


class W:
    """one row's world parameters"""
    def __init__(self, window=WIN, layout='byte', adv=None, shift=None, failpos=None):
        self.window, self.layout, self.adv, self.shift, self.failpos = window, layout, adv, shift, failpos

    def size(self, pos):
        return min(len(US) - pos, self.window)

    def elements(self, pos):
        start = pos
        if self.shift and pos >= self.shift[0]:
            start = max(0, pos + self.shift[1])
        data = US[start:start + self.size(pos)]
        if self.layout == 'byte':
            return list(data)
        if self.layout == 'junk':
            return [0x5A00 | b for b in data]
        if self.layout == 'le':
            return [data[i] | (data[i + 1] << 8) for i in range(0, len(data) - 1, 2)]
        if self.layout == 'be':
            return [(data[i] << 8) | data[i + 1] for i in range(0, len(data) - 1, 2)]
        raise ValueError(self.layout)

    def mapok(self, pos):
        return not (self.failpos is not None and pos >= self.failpos)

    def drop(self, pos):
        return min(pos + (64 if self.adv is None else self.adv), len(US))


def ref_t1(w):
    if not w.mapok(0):
        return IDS['nomap']
    e = w.elements(0)
    e0, e2 = e[0], e[2]
    if e0 == 2:
        return IDS['clean'] if e2 == 0 else IDS['packed'] if e2 == 9 else IDS['other']
    return IDS['junk'] if (e0 & 0xFF) == 2 else IDS['other']


def ref_t2(w):
    pos, done = 0, 0
    for k, cp in enumerate(CHECKPOINTS):
        ok = True
        for _ in range(cp - done):
            if w.size(pos) < 64:
                ok = False
                break
            pos = w.drop(pos)
        done = cp
        if ok and w.mapok(pos):
            e = w.elements(pos)
            ok = (e[0] & 0xFF) == US[64 * cp] and (e[18] & 0xFF) == US[64 * cp + 18]
        else:
            ok = False
        if not ok:
            return [IDS['f1'], IDS['f100'], IDS['f1000'], IDS['f1320']][k]
    return IDS['ok']


def ref_t3(w):
    pos, n = 0, 0
    cap = 3383 + 117
    while True:
        s = w.size(pos)
        if s != WIN:
            break
        if n == cap:
            return IDS['stuck']
        pos = w.drop(pos)
        n += 1
    if n == 0:
        return IDS['w0']
    if s == len(US) - 64 * 3383:
        return IDS['exact']
    return IDS['over'] if s < len(US) - 64 * 3383 else IDS['under']


def ref_ids(w):
    return [ref_t1(w), ref_t2(w), ref_t3(w)]


# ------------------------------------------------------------------ the rows
E = ['--entry', '0x3E21D']
PRESS = ['--press', '0:4004']
LEVER = ['--caller-frame', '23']
STATE = ['--mem', '59e=d']
SRC = ['--src-window', str(WIN), '--src-unpacked']
BASE = E + PRESS + STATE + LEVER + ['--steps', '30000000', '--horizon', '60000']
H = BASE + SRC

SCEN = []


def S(group, name, args, expects, regex=(), **extra):
    SCEN.append((group, name, args, list(expects), list(regex), extra))


def spoken(ids):
    return 'spoken=' + ','.join('%02x' % i for i in ids)


UNTOUCHED = ['flushes=0', 'p2closed=False', 'pending=0', 'violations=0']
NOWRITE = [r'!OverwriteSink', r'!SinkMap', r'!SinkClaim', r'!SinkFlush', r'!PartitionSetMessageDigest', r'!SinkClose', r'!SYNTHESISED TRAP STUB']
CLOSED = r'file sources: 3 opened, 0 never closed'


def world_row(group, name, extra_args, w, regex=(), closed=True, cross=None, base=None):
    ids = ref_ids(w)
    if cross is not None:
        assert ids == cross, (name, [hex(i) for i in ids], [hex(i) for i in cross])        # the reference model, pinned
    exp = [spoken(ids), 'violations=0', 'pending=0'] + UNTOUCHED[:2]
    rx = list(NOWRITE) + list(regex)
    if closed and IDS['over'] not in ids:
        rx.append(CLOSED)
    S(group, name, (base or H) + extra_args, exp, rx)


# ------------------------------------------------------------------ NOMINAL
world_row('NOMINAL', 'healthy base (stock data_us, window 0xC00, one byte per element): 12, 30, 3e (clean layout, all four checkpoints, exact tail)',
          [], W(), cross=[0x12, 0x30, 0x3E], regex=[r'spoken: 0x12@2000', r'port-3 rules: OK', r'!TransformStart'])
world_row('NOMINAL', 'sinkState 3 is accepted at every tick', [], W(), cross=[0x12, 0x30, 0x3E],
          base=E + PRESS + ['--mem', '59e=3'] + LEVER + ['--steps', '30000000', '--horizon', '60000'] + SRC)
S('NOMINAL', 'the lever: no store reaches the caller\'s saved return address', H, [spoken([0x12, 0x30, 0x3E])],
  [r'caller-frame guard: stores to 0x0915, 0x0916 stop the run', r'!STOPPED'])
S('NOMINAL', 'the order of the traps in tick 1: FileFind FileFind S.FileSource SourceMap SourceClose MessageSendLater SPEAK; nothing of the write side',
  H, [spoken([0x12, 0x30, 0x3E])],
  [r'timer message, MessageId 0x0012 -> FileFind FileFind S\.FileSource SourceMap SourceClose MessageSendLater SPEAK 0x12', r'!SYNTHESISED TRAP STUB'])

# ------------------------------------------------------------------ GUARD (sinkState): nothing opened
for st in ('0', '1', '2', '5', '6', 'a', 'c', 'e', '10', '16'):
    S('GUARD', 'sinkState 0x%s: 0x3C only, no file opened, the chain ends' % st,
      E + PRESS + ['--mem', '59e=' + st] + LEVER + ['--steps', '30000000', '--horizon', '60000'] + SRC,
      [spoken([0x3C])] + UNTOUCHED, [r'!FileFind', r'!StreamFileSource'])
S('GUARD', 'no sinkState preset: refused', E + PRESS + LEVER + ['--steps', '30000000', '--horizon', '60000'] + SRC,
  [spoken([0x3C])] + UNTOUCHED, [r'!FileFind'])
S('GUARD', 'sinkState changes to 2 at 5000 ms (after tick 1, before tick 2): 12 then 3c, the chain ends',
  H + ['--mem-at', '5000:59e=2'], [spoken([0x12, 0x3C])] + UNTOUCHED, [r'file sources: 1 opened, 0 never closed'])
S('GUARD', 'sinkState changes to 2 at 20000 ms (after tick 2, before tick 3): 12, 30, 3c',
  H + ['--mem-at', '20000:59e=2'], [spoken([0x12, 0x30, 0x3C])] + UNTOUCHED, [r'file sources: 2 opened, 0 never closed'])

# ------------------------------------------------------------------ OPEN refusals (tick 1 only; the chain ends)
S('OPEN', 'FileFind refuses (first lookup): 0x17, the chain ends', H + ['--fail', 'FileFind'], [spoken([0x17])] + UNTOUCHED, [r'!StreamFileSource'])
S('OPEN', 'FileFind refuses the SECOND lookup (data_us): 0x17', H + ['--fail-after', 'FileFind=2'], [spoken([0x17])] + UNTOUCHED)
S('OPEN', 'StreamFileSource refuses: 0x17', H + ['--fail', 'StreamFileSource'], [spoken([0x17])] + UNTOUCHED)

# ------------------------------------------------------------------ T1: the element layout at the file start
world_row('T1', 'junk in the high byte of every element: T1 13 (junk), T2 passes (masked), T3 exact', ['--src-hijunk'], W(layout='junk'),
          cross=[0x13, 0x30, 0x3E])
world_row('T1', 'two bytes per element, little endian: T1 14 (packed); T2 reads element 18 = bytes 36/37 and fails at checkpoint 1',
          ['--src-window', str(WIN), '--src-endian', 'le'], W(layout='le'), cross=[0x14, 0x28, 0x3E],
          base=E + PRESS + STATE + LEVER + ['--steps', '30000000', '--horizon', '60000'])
world_row('T1', 'two bytes per element, big endian: T1 15 (other: e0 = 0x0200)',
          ['--src-window', str(WIN), '--src-endian', 'be'], W(layout='be'), cross=[0x15, 0x28, 0x3E],
          base=E + PRESS + STATE + LEVER + ['--steps', '30000000', '--horizon', '60000'])
world_row('T1', 'SourceMap returns 0 at the file start (position 0): T1 16, T2 fails at checkpoint 1, T3 does not use the map',
          ['--map-fail-pos', '0'], W(failpos=0), cross=[0x16, 0x28, 0x3E])
world_row('T1', 'the map is shifted by 7 bytes from the start: T1 15 (other)', ['--map-shift-from', '0:7'], W(shift=(0, 7)))
world_row('T1', 'the map shows 0x5A in the high byte AND the file window is 0xC00: still T1 13', ['--src-hijunk'], W(layout='junk'))

# ------------------------------------------------------------------ T2: the checkpoints
world_row('T2', 'a map shift of 9 from position 64 on: checkpoint 1 fails (0x28)', ['--map-shift-from', '64:9'], W(shift=(64, 9)),
          cross=[0x12, 0x28, 0x3E])
world_row('T2', 'a map shift of 5 from position 6400 on: checkpoints 1 passes, 100 fails (0x2A)', ['--map-shift-from', '6400:5'],
          W(shift=(6400, 5)), cross=[0x12, 0x2A, 0x3E])
world_row('T2', 'a map shift of 5 from position 64000 on: checkpoint 1000 fails (0x2C)', ['--map-shift-from', '64000:5'],
          W(shift=(64000, 5)), cross=[0x12, 0x2C, 0x3E])
world_row('T2', 'a map shift of 5 from position 84480 on: only checkpoint 1320 fails (0x2E): the probe198 look position',
          ['--map-shift-from', '84480:5'], W(shift=(84480, 5)), cross=[0x12, 0x2E, 0x3E])
world_row('T2', 'a map shift of -3 from position 84480 on (map behind): checkpoint 1320 fails', ['--map-shift-from', '84480:-3'],
          W(shift=(84480, -3)), cross=[0x12, 0x2E, 0x3E])
world_row('T2', 'SourceMap returns 0 from position 6400 on: checkpoint 100 fails (0x2A)', ['--map-fail-pos', '6400'], W(failpos=6400),
          cross=[0x12, 0x2A, 0x3E])
world_row('T2', 'SourceMap returns 0 from position 84480 on: checkpoint 1320 fails (0x2E)', ['--map-fail-pos', '84480'], W(failpos=84480),
          cross=[0x12, 0x2E, 0x3E])
world_row('T2', 'a shift of exactly one period (64) from position 84480: checkpoint 1320 fails', ['--map-shift-from', '84480:64'],
          W(shift=(84480, 64)), cross=[0x12, 0x2E, 0x3E])

# ------------------------------------------------------------------ SourceDrop advance
world_row('DROP', 'every SourceDrop advances 32 bytes (short): T2 fails at checkpoint 1, T3 STUCK (0x24: the 3,500-drop cap)',
          ['--drop-adv', '32'], W(adv=32), cross=[0x12, 0x28, 0x24])
world_row('DROP', 'every SourceDrop advances 128 bytes (long): T2 fails at 1, T3 OVER (0x3D); the source is NOT closed',
          ['--drop-adv', '128'], W(adv=128), cross=[0x12, 0x28, 0x3D])
world_row('DROP', 'every SourceDrop advances 63 bytes: T2 fails at 1, T3 UNDER (0x39)', ['--drop-adv', '63'], W(adv=63), cross=[0x12, 0x28, 0x39])
world_row('DROP', 'every SourceDrop advances 0 bytes: T2 fails at 1, T3 STUCK', ['--drop-adv', '0'], W(adv=0), cross=[0x12, 0x28, 0x24])
world_row('DROP', 'every SourceDrop advances 65 bytes: T3 OVER (0x3D)', ['--drop-adv', '65'], W(adv=65), cross=[0x12, 0x28, 0x3D])
world_row('DROP', 'every SourceDrop advances 64 bytes (explicit): the base result', ['--drop-adv', '64'], W(adv=64), cross=[0x12, 0x30, 0x3E])

# ------------------------------------------------------------------ the window
world_row('WINDOW', 'SourceSize is 2048 (not 0xC00): T3 reports W0 (0x1B), T2 still passes', ['--src-window', '2048'], W(window=2048),
          cross=[0x12, 0x30, 0x1B], base=E + PRESS + STATE + LEVER + ['--steps', '30000000', '--horizon', '60000', '--src-unpacked'])
world_row('WINDOW', 'SourceSize is 63 (< 64): the drop loop of T2 refuses at the first drop (0x28), T3 W0', ['--src-window', '63'], W(window=63),
          cross=[0x12, 0x28, 0x1B], base=E + PRESS + STATE + LEVER + ['--steps', '30000000', '--horizon', '60000', '--src-unpacked'])
world_row('WINDOW', 'SourceSize is 64 (the minimum the drops accept): T2 passes, T3 W0', ['--src-window', '64'], W(window=64),
          cross=[0x12, 0x30, 0x1B], base=E + PRESS + STATE + LEVER + ['--steps', '30000000', '--horizon', '60000', '--src-unpacked'])

# ------------------------------------------------------------------ PRESS handling
S('PRESS', 'a second press at 1000 ms (tick 1 pending): STOP, nothing opened', H + ['--press', '1000:4004'],
  ['spoken=', 'swallowed=2'] + UNTOUCHED, [r'!FileFind'])
S('PRESS', 'a second press at 8000 ms (tick 2 pending): STOP after the first id', H + ['--press', '8000:4004'],
  [spoken([0x12]), 'swallowed=2'] + UNTOUCHED, [r'file sources: 1 opened, 0 never closed'])
S('PRESS', 'a second press at 40000 ms (the run is over): a SECOND full run',
  BASE[:-2] + ['--horizon', '100000', '--press', '40000:4004'] + SRC,
  [spoken([0x12, 0x30, 0x3E, 0x12, 0x30, 0x3E]), 'swallowed=2'] + UNTOUCHED, [CLOSED.replace('3 opened', '6 opened')])
S('PRESS', 'a non-0x4004 event is replayed to the stock, nothing else happens',
  E + ['--press', '0:4003', '--once'] + STATE + LEVER + SRC, ['spoken=', 'replayed=1', 'swallowed=0'] + UNTOUCHED, [r'!FileFind'])
S('PRESS', 'an id that is not a stage (0x77) delivered to the handler: nothing happens',
  E + ['--pending', '77@1000', '--horizon', '10000'] + STATE + SRC, ['spoken='] + UNTOUCHED, [r'!FileFind'])

# ------------------------------------------------------------------ STUBS / TRAP LIST
S('STUBS', 'no synthesised stub, no sink, no partition call, no transform, R3 silent', H, [spoken([0x12, 0x30, 0x3E])],
  NOWRITE + [r'port-3 rules: OK', r'!TransformAdpcmDecode', r'!TransformStart', r'!TransformStop', r'!PartitionGetRawSerialSource'])

# ------------------------------------------------------------------ FRAME (V11 D1): no store into the saved return address of any function
# V11: WALK stored to slot 6 of an `enterl -8` frame (slots 6 and 7 are the saved return address); the world model keeps locals as plain
# memory and cannot see it. These two rows fail on that class of mistake: (1) tools/framecheck.py, a per-function check of every
# st AL/AH/X @(n,Y) against the frame of the function it sits in; (2) cavesim's own static HAZARD lines: any HAZARD other than the
# whole-image "frame slot" line (which judges every function by the FIRST enterl and so flags correct code in a bigger frame) fails,
# and the "frame slot" line is accepted only because (1) is clean.
S('FRAME', 'tools/framecheck.py: no store into the top two slots of any function frame (per function)', [], [], [], frame='fc')
S('FRAME', 'cavesim static hazards: none except the whole-image frame line, which framecheck (above) answers per function', [], [], [], frame='hz')


sys.path.insert(0, os.path.join(ROOT, 'tools'))


def run_frame(words, kind):
    import framecheck
    bad, out = [], ''
    if kind == 'fc':
        fnd = framecheck.check(framecheck.load(words))
        for a, k, n, txt in fnd:
            bad.append('0x%05x %s inside enterl -%d: slot %d is part of the saved return address' % (a, txt, k, n))
        return bad, 'framecheck: %d finding(s)' % len(fnd)
    cmd = [sys.executable, 'tools/cavesim.py', words] + E + ['--brief']
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)
    out = r.stdout + r.stderr
    data = framecheck.data_addrs(framecheck.load(words))      # the carried string and the checkpoint table are DATA
    for ln in out.splitlines():
        if ln.strip().startswith('HAZARD') and 'frame slot' not in ln:
            m = re.match(r'\s*HAZARD\s+0x([0-9A-Fa-f]+)', ln)
            if m and int(m.group(1), 16) in data:
                continue                                          # the scan decodes data words as instructions
            bad.append(ln.strip()[:200])
    return bad, out


def run_one(words, scen):
    group, name, args, expects, regex, extra = scen
    if extra.get('frame'):
        return run_frame(words, extra['frame'])
    cmd = [sys.executable, 'tools/cavesim.py', words] + args + ['--brief']
    for e in expects:
        cmd += ['--expect', e]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=1800)
    out = r.stdout + r.stderr
    bad = []
    if r.returncode != 0:
        bad.append('exit code %d' % r.returncode)
    for ln in out.splitlines():
        if (ln.startswith('expect ') and ln.rstrip().endswith('FAIL')) or ' FAIL (have' in ln:
            bad.append(ln.strip())
    for rx in regex:
        if rx.startswith('!'):
            if re.search(rx[1:], out):
                bad.append('must not match /%s/' % rx[1:])
        elif not re.search(rx, out):
            bad.append('missing /%s/' % rx)
    if ('STOPPED' in out and '!STOPPED' not in regex) or 'Traceback' in out:
        bad.append('STOPPED/Traceback in the output')
    return bad, out


def main():
    argv = sys.argv[1:]
    if '--list' in argv:
        for i, s in enumerate(SCEN):
            print('%2d %-8s %s' % (i, s[0], s[1]))
        return 0
    words = 'probe199s'
    if '--words' in argv:
        words = argv[argv.index('--words') + 1]
    part = (0, 1)
    if '--part' in argv:
        a, b = argv[argv.index('--part') + 1].split('/')
        part = (int(a) - 1, int(b))
    fails = ran = 0
    for i, s in enumerate(SCEN):
        if i % part[1] != part[0]:
            continue
        bad, out = run_one(words, s)
        ran += 1
        print('%s %2d %-7s %s' % ('FAIL' if bad else 'ok  ', i, s[0], s[1]), flush=True)
        for b in bad:
            print('      -> %s' % b)
        if bad:
            fails += 1
            print('\n'.join('      | ' + ln[:200] for ln in out.splitlines()[-14:]), flush=True)
    print('\n%d scenario(s) run, %d failed' % (ran, fails))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
