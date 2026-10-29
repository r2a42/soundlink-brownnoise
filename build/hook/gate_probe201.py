#!/usr/bin/env python3
"""Offline world-model gate for probe201 (F1: a READ-ONLY file-source diagnostic ON THE STAGED data_us) -- 2026-10-15.
NOT independently reviewed. NO device, no flash tool: pure emulation.

Runs the real words (build/hook/probe201_words.json, written by assemble_probe201.py) through tools/cavesim.py's clocked world model.
The file the cave opens is the STAGED data_us of probe198b (build/payload/r3/data_us_r3_staged), or the STOCK one in the "not served" rows. Every row's expected id sequence comes from an INDEPENDENT reference
model written here (ref_ids): the diagnostic's decision procedure re-stated in Python over the stock bytes and the row's world parameters
(element layout, live or snapshot map, window, drop advance, map shift / failure), not read off the cave. Hard-coded cross-checks pin
the reference model on the key rows. FRAME rows run tools/framecheck.py and cavesim's static hazard scan (V11 D1).

    python build/hook/assemble_probe201.py                     # first (writes probe200_words.json)
    python build/hook/gate_probe201.py [--part I/N] [--list] [--words PATH]
    --words PATH  runs a mutated copy of the words: the gate must FAIL there (mutation rows)
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
US0 = open(os.path.join(ROOT, 'firmware', 'bose', 'extracted', 'internal_fs', 'data_us'), 'rb').read()
sys.path.insert(0, os.path.join(ROOT, 'build', 'hook'))
import narrow184_lib as L      # noqa: E402
ORACLE = open(os.path.join(ROOT, 'build', 'payload', 'r3', 'brown_8000_58968_s63.adpcm'), 'rb').read()
STG = L.stage(ORACLE, 1320)['new_us']
STAGED_REL = 'build/payload/r3/data_us_r3_staged'
_sp = os.path.join(ROOT, STAGED_REL)
if not (os.path.exists(_sp) and open(_sp, 'rb').read() == STG):         # never rewrite an identical file (parallel parts read it)
    with open(_sp, 'wb') as _f:
        _f.write(STG)
assert len(US0) == 219528 and len(STG) == 219528
sys.path.insert(0, os.path.join(ROOT, 'tools'))

WIN = 3072
START_PERIOD = 1320
BIT1, BIT0 = 0x30, 0x3B


# ------------------------------------------------------------------ the reference model (independent of the cave's code)
WA, WB, WC = 64 * 1319, 64 * 1320, 64 * 1320 + 14
SCAN_N = 40


class W:
    """one row's world parameters: window, default leading elements, alignment rules (M, R, N), junk, whether the staged bytes are served, map failure"""
    def __init__(self, window=WIN, lead=0, rules=(), junk=False, served=True, failpos=None):
        self.window, self.lead, self.rules, self.junk, self.served, self.failpos = window, lead, tuple(rules), junk, served, failpos
        self.file = STG if served else US0

    def size(self, pos):
        return min(len(US0) - pos, self.window)

    def lead_at(self, pos):
        for m, r, n in self.rules:
            if pos % m == r:
                return n
        return self.lead

    def elements(self, pos):
        data = self.file[pos:pos + self.size(pos)]
        body = [(0x5A00 | b) if self.junk else b for b in data]
        return [0xDD] * self.lead_at(pos) + body

    def mapok(self, pos):
        return not (self.failpos is not None and pos >= self.failpos)


def at(el, i):
    return el[i] if i < len(el) else 0


def scan(el, row):
    mask, s0, s1 = row
    for j in range(SCAN_N):
        if (at(el, j) & mask) == s0 and (at(el, j + 1) & mask) == s1:
            return j
    return None


GA = (US0[WA + 18], US0[WA + 19])
ROW_A, ROW_ARAW, ROW_P, ROW_S = (0xFF, GA[0], GA[1]), (0xFFFF, GA[0], GA[1]), (0xFF, 0x77, 0x7F), (0xFF, 0x6A, 0x00)


def cls(j, off):
    return 0 if j is None else 1 if j == off else 2 if j == off + 1 else 3


def ref_bits(w):
    """the 8 data bits A1 A0 B1 B0 C1 C0 S H"""
    ok = all(w.size(64 * i) >= 64 for i in range(1319))          # the drop loop's SourceSize >= 64 test
    el = {}
    for name, pos in (('A', WA), ('B', WB), ('C', WC)):
        el[name] = w.elements(pos) if ok and w.mapok(pos) else None
    a, b, c = el['A'], el['B'], el['C']
    ja = scan(a, ROW_A) if a is not None else None
    jh = scan(a, ROW_ARAW) if a is not None else None
    jb = scan(b, ROW_P) if b is not None else None
    js = scan(b, ROW_S) if b is not None else None
    jc = scan(c, ROW_P) if c is not None else None
    ca_, cb_, cc_ = cls(ja, 18), cls(jb, 18), cls(jc, 4)
    return [ca_ >> 1, ca_ & 1, cb_ >> 1, cb_ & 1, cc_ >> 1, cc_ & 1, 1 if js is not None else 0, 1 if jh is not None else 0]


def ref_ids(w):
    return [BIT1 if x else BIT0 for x in [1, 0] + ref_bits(w)]


# ------------------------------------------------------------------ the rows
E = ['--entry', '0x3E21D']
PRESS = ['--press', '0:4004']
LEVER = ['--caller-frame', '23']
STATE = ['--mem', '59e=d']
STEPS = ['--steps', '40000000', '--horizon', '130000']
BASE = E + PRESS + STATE + LEVER + STEPS
FSADD = ['--fs-add', 'NowSpeakTTS/data_us=@' + STAGED_REL, '--src-unpacked']
STAGED = FSADD + ['--src-window', str(WIN)]
STOCK = ['--src-unpacked', '--src-window', str(WIN)]
H = BASE + STAGED

SCEN = []


def S(group, name, args, expects, regex=(), **extra):
    SCEN.append((group, name, args, list(expects), list(regex), extra))


def spoken(ids):
    return 'spoken=' + ','.join('%02x' % i for i in ids)


UNTOUCHED = ['flushes=0', 'p2closed=False', 'violations=0']
NOWRITE = [r'!OverwriteSink', r'!SinkMap', r'!SinkClaim', r'!SinkFlush', r'!PartitionSetMessageDigest', r'!SinkClose', r'!SYNTHESISED TRAP STUB']
CLOSED = r'file sources: 10 opened, 0 never closed'


def BITS(bits):
    return [BIT1 if x else BIT0 for x in [1, 0] + list(bits)]


def world_row(group, name, extra, w, base=None, cross=None, regex=()):
    ids = ref_ids(w)
    if cross is not None:
        assert ids == BITS(cross), (name, [hex(i) for i in ids])           # the reference model, pinned
    S(group, name, (base or H) + extra, [spoken(ids), 'violations=0', 'pending=0'] + UNTOUCHED[:2], list(NOWRITE) + [CLOSED] + list(regex))


# bits: A1 A0 B1 B0 C1 C0 S H
world_row('NOMINAL', 'shift +1 everywhere, clean high bytes (the probe200 reading): A=2 B=2 C=2 S=0 H=1', ['--map-lead', '1'], W(lead=1),
          cross=[1, 0, 1, 0, 1, 0, 0, 1], regex=[r'spoken: 0x30@2000', r'port-3 rules: OK', r'!TransformStart'])
world_row('NOMINAL', 'no shift at all: A=1 B=1 C=1', [], W(lead=0), cross=[0, 1, 0, 1, 0, 1, 0, 1])
world_row('NOMINAL', 'shift +1 at the unaligned window, 0 at the 64-aligned ones (alignment-dependent): A=1 B=1 C=2',
          ['--map-lead', '1', '--map-lead-rule', '64:0:0'], W(lead=1, rules=[(64, 0, 0)]), cross=[0, 1, 0, 1, 1, 0, 0, 1])
world_row('NOMINAL', 'shift +1 unaligned, +2 at the 64-aligned windows: A=3 B=3 C=2', ['--map-lead', '1', '--map-lead-rule', '64:0:2'],
          W(lead=1, rules=[(64, 0, 2)]), cross=[1, 1, 1, 1, 1, 0, 0, 1])
world_row('NOMINAL', 'the mirror: shift 0 unaligned, +1 at the aligned windows: A=2 B=2 C=1', ['--map-lead', '0', '--map-lead-rule', '64:0:1'],
          W(lead=0, rules=[(64, 0, 1)]), cross=[1, 0, 1, 0, 0, 1, 0, 1])
world_row('NOMINAL', 'shift +1 and junk 0x5A in every high byte: the masked search still finds A, B, C; H = 0 (raw search fails)',
          ['--map-lead', '1', '--src-hijunk'], W(lead=1, junk=True), cross=[1, 0, 1, 0, 1, 0, 0, 0])
world_row('NOMINAL', 'shift +3 (found elsewhere): A=3 B=3 C=3', ['--map-lead', '3'], W(lead=3), cross=[1, 1, 1, 1, 1, 1, 0, 1])
world_row('NOMINAL', 'the STOCK data_us is served instead of the staged one (shift +1): A=2, B=0 (payload absent), C=0, S=1',
          ['--map-lead', '1'], W(lead=1, served=False), base=BASE + STOCK, cross=[1, 0, 0, 0, 0, 0, 1, 1])
world_row('FAIL', 'SourceMap returns 0 from byte 84,480 on: A normal, B, C, S none', ['--map-lead', '1', '--map-fail-pos', '84480'], W(lead=1, failpos=84480),
          cross=[1, 0, 0, 0, 0, 0, 0, 1])
world_row('FAIL', 'SourceMap returns 0 from the start: everything none, H = 0', ['--map-lead', '1', '--map-fail-pos', '0'], W(lead=1, failpos=0), cross=[0] * 8)
world_row('WINDOW', 'SourceSize 63: the drop loop refuses at the first drop: everything none', ['--map-lead', '1', '--src-window', '63'], W(lead=1, window=63),
          base=BASE + FSADD, cross=[0] * 8)
world_row('WINDOW', 'SourceSize 128 (the tail drops of 64 and 78 fit): the map has 128 (+ lead) elements', ['--map-lead', '1', '--src-window', '128'],
          W(lead=1, window=128), base=BASE + FSADD)
S('NOMINAL', 'sinkState 3 is accepted at every tick', E + PRESS + ['--mem', '59e=3'] + LEVER + STEPS + STAGED + ['--map-lead', '1'],
  [spoken(ref_ids(W(lead=1))), 'violations=0', 'pending=0'] + UNTOUCHED[:2], NOWRITE)
S('NOMINAL', "the lever: no store reaches the caller's saved return address", H + ['--map-lead', '1'], [spoken(ref_ids(W(lead=1)))],
  [r'caller-frame guard: stores to 0x0915, 0x0916 stop the run', r'!STOPPED'])
S('NOMINAL', 'the trap order of tick 0 (sync): FileFind FileFind S.FileSource SourceClose MessageSendLater SPEAK 0x30 (no map)', H + ['--map-lead', '1'],
  [spoken(ref_ids(W(lead=1)))], [r'timer message, MessageId 0x0012 -> FileFind FileFind S\.FileSource SourceClose MessageSendLater SPEAK 0x30'])

# ------------------------------------------------------------------ GUARD / OPEN: silent
for st in ('0', '2', '5', 'a', '10'):
    S('GUARD', 'sinkState 0x%s: SILENT, no file opened, the chain ends' % st, E + PRESS + ['--mem', '59e=' + st] + LEVER + STEPS + STAGED,
      ['spoken='] + UNTOUCHED, [r'!FileFind', r'!StreamFileSource'])
S('GUARD', 'no sinkState preset: silent', E + PRESS + LEVER + STEPS + STAGED, ['spoken='] + UNTOUCHED, [r'!FileFind'])
S('GUARD', 'sinkState changes to 2 at 30000 ms: the first four ticks speak (1 0 and A1 A0), the rest is silent',
  H + ['--map-lead', '1', '--mem-at', '30000:59e=2'], [spoken(ref_ids(W(lead=1))[:4])] + UNTOUCHED, [r'file sources: 4 opened, 0 never closed'])
S('OPEN', 'FileFind refuses (first lookup): silent', H + ['--fail', 'FileFind'], ['spoken='] + UNTOUCHED, [r'!StreamFileSource'])
S('OPEN', 'FileFind refuses the SECOND lookup: silent', H + ['--fail-after', 'FileFind=2'], ['spoken='] + UNTOUCHED)
S('OPEN', 'StreamFileSource refuses: silent', H + ['--fail', 'StreamFileSource'], ['spoken='] + UNTOUCHED)

# ------------------------------------------------------------------ PRESS
S('PRESS', 'a second press at 1000 ms (tick 0 pending): STOP, nothing opened', H + ['--press', '1000:4004'], ['spoken=', 'swallowed=2'] + UNTOUCHED, [r'!FileFind'])
S('PRESS', 'a second press at 8000 ms (tick 1 pending): STOP after the first prompt', H + ['--press', '8000:4004'], [spoken([BIT1]), 'swallowed=2'] + UNTOUCHED,
  [r'file sources: 1 opened, 0 never closed'])
S('PRESS', 'a non-0x4004 event is replayed to the stock, nothing else happens', E + ['--press', '0:4003', '--once'] + STATE + LEVER + STAGED,
  ['spoken=', 'replayed=1', 'swallowed=0'] + UNTOUCHED, [r'!FileFind'])
S('PRESS', 'an id that is not a stage (0x77) delivered to the handler: nothing happens', E + ['--pending', '77@1000', '--horizon', '10000'] + STATE + STAGED,
  ['spoken='] + UNTOUCHED, [r'!FileFind'])
S('STUBS', 'no synthesised stub, no sink, no partition call, no transform, R3 silent', H + ['--map-lead', '1'], [spoken(ref_ids(W(lead=1)))],
  NOWRITE + [r'port-3 rules: OK', r'!TransformAdpcmDecode', r'!TransformStart', r'!TransformStop', r'!PartitionGetRawSerialSource'])
S('FRAME', 'tools/framecheck.py: no store into the top two slots of any function frame (per function)', [], [], [], frame='fc')
S('FRAME', 'cavesim static hazards: none except the whole-image frame line (framecheck answers it per function) and data blocks', [], [], [], frame='hz')


def run_frame(words, kind):
    import framecheck
    bad = []
    if kind == 'fc':
        fnd = framecheck.check(framecheck.load(words))
        for a, k, n, txt in fnd:
            bad.append('0x%05x %s inside enterl -%d: slot %d is part of the saved return address' % (a, txt, k, n))
        return bad, 'framecheck: %d finding(s)' % len(fnd)
    cmd = [sys.executable, 'tools/cavesim.py', words] + E + ['--brief']
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)
    out = r.stdout + r.stderr
    data = framecheck.data_addrs(framecheck.load(words))
    for ln in out.splitlines():
        if ln.strip().startswith('HAZARD') and 'frame slot' not in ln:
            m = re.match(r'\s*HAZARD\s+0x([0-9A-Fa-f]+)', ln)
            if m and int(m.group(1), 16) in data:
                continue
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
    words = 'probe201'
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
