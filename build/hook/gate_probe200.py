#!/usr/bin/env python3
"""Offline world-model gate for probe200 (E1: the ELEMENT CENSUS, a READ-ONLY diagnostic on the STOCK data_us) -- 2026-10-14.
NOT independently reviewed. NO device, no flash tool: pure emulation.

Runs the real words (build/hook/probe200_words.json, written by assemble_probe200.py) through tools/cavesim.py's clocked world model.
The file the cave opens is the STOCK data_us (the world's default). Every row's expected id sequence comes from an INDEPENDENT reference
model written here (ref_ids): the census's decision procedure re-stated in Python over the stock bytes and the row's world parameters
(element layout, live or snapshot map, window, drop advance, map shift / failure), not read off the cave. Hard-coded cross-checks pin
the reference model on the key rows. FRAME rows run tools/framecheck.py and cavesim's static hazard scan (V11 D1).

    python build/hook/assemble_probe200.py                     # first (writes probe200_words.json)
    python build/hook/gate_probe200.py [--part I/N] [--list] [--words PATH]
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
sys.path.insert(0, os.path.join(ROOT, 'tools'))

WIN = 3072
START_PERIOD = 1320
NONE_ID, START_ID, END_ID = 0x31, 0x12, 0x13


# ------------------------------------------------------------------ the reference model (independent of the cave's code)
class W:
    """one row's world parameters"""
    def __init__(self, window=WIN, layout='byte', live=False, adv=None, shift=None, failpos=None):
        self.window, self.layout, self.live, self.adv, self.shift, self.failpos = window, layout, live, adv, shift, failpos

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
        if self.layout == 'hibyte':
            return [b << 8 for b in data]
        if self.layout == 'le16':
            return [data[i] | (data[i + 1] << 8) for i in range(0, len(data) - 1, 2)]
        if self.layout == 'be16':
            return [(data[i] << 8) | data[i + 1] for i in range(0, len(data) - 1, 2)]
        raise ValueError(self.layout)

    def mapok(self, pos):
        return not (self.failpos is not None and pos >= self.failpos)

    def drop(self, pos, n=64):
        return min(pos + (n if self.adv is None else self.adv), len(US))


def at(el, i):
    return el[i] if i < len(el) else 0                  # past the end of the map: data memory the model leaves at zero


def rows(w0):
    """the three (mask, s0) rows of a window that starts at file byte w0: the element at w0 + 4"""
    b0, b1 = US[w0 + 4], US[w0 + 5]
    return [(0x00FF, b0), (0xFFFF, b0 << 8 | b1), (0xFF00, b0 << 8)]


def scan(el, row):
    for j in range(10):
        if (at(el, j) & row[0]) == row[1]:
            return j
    return None


def classify(el, w0):
    for f, row in enumerate(rows(w0), 1):
        j = scan(el, row)
        if j is not None:
            return f, j
    return 4, None


def census0(w):
    """stock style: SourceMap at position 0 (p0), SourceDrop(4), classify the elements p0 shows after the drop"""
    if not w.mapok(0):
        return None
    el0 = w.elements(0)
    pos = w.drop(0, 4)
    el = w.elements(pos) if w.live else el0
    return classify(el, 4)


def ref_ids(w):
    ids = [START_ID]
    c = census0(w)
    ids.append(NONE_ID if c is None or c[0] == 4 else 0x27 + c[0] - 1)                      # FAM0
    ids.append(NONE_ID if c is None or c[0] == 4 else 0x27 + c[1])                          # IDX0
    # EXT
    if not w.mapok(0):
        ids.append(NONE_ID)
    else:
        el = w.elements(0)
        v = (1 if at(el, 3071) == US[3071] else 0) + (2 if at(el, 1535) == (US[3070] << 8 | US[3071]) else 0)
        ids.append(0x27 + v)
    # IDX1320
    if c is None or c[0] == 4:
        ids.append(NONE_ID)
    else:
        pos = w.drop(0, 4)
        ok = True
        for _ in range(START_PERIOD):
            if w.size(pos) < 64:
                ok = False
                break
            pos = w.drop(pos)
        if not ok:
            ids.append(NONE_ID)
        else:
            pos = w.drop(pos, 10)
            if not w.mapok(pos):
                ids.append(NONE_ID)
            else:
                j = scan(w.elements(pos), rows(64 * START_PERIOD + 14)[c[0] - 1])
                ids.append(NONE_ID if j is None else 0x27 + j)
    ids.append(END_ID)
    return ids


# ------------------------------------------------------------------ the rows
E = ['--entry', '0x3E21D']
PRESS = ['--press', '0:4004']
LEVER = ['--caller-frame', '23']
STATE = ['--mem', '59e=d']
STEPS = ['--steps', '30000000', '--horizon', '70000']
BASE = E + PRESS + STATE + LEVER + STEPS
SRC = ['--src-window', str(WIN), '--src-unpacked']
H = BASE + SRC

SCEN = []


def S(group, name, args, expects, regex=(), **extra):
    SCEN.append((group, name, args, list(expects), list(regex), extra))


def spoken(ids):
    return 'spoken=' + ','.join('%02x' % i for i in ids)


UNTOUCHED = ['flushes=0', 'p2closed=False', 'pending=0', 'violations=0']
NOWRITE = [r'!OverwriteSink', r'!SinkMap', r'!SinkClaim', r'!SinkFlush', r'!PartitionSetMessageDigest', r'!SinkClose', r'!SYNTHESISED TRAP STUB']
CLOSED = r'file sources: 6 opened, 0 never closed'


def world_row(group, name, extra_args, w, regex=(), cross=None, base=None):
    ids = ref_ids(w)
    if cross is not None:
        assert ids == cross, (name, [hex(i) for i in ids], [hex(i) for i in cross])        # the reference model, pinned
    S(group, name, (base or H) + extra_args, [spoken(ids), 'violations=0', 'pending=0'] + UNTOUCHED[:2], list(NOWRITE) + [CLOSED] + list(regex))


# ------------------------------------------------------------------ NOMINAL: the hypotheses about the layout
# ids: 0x12 START, FAM0 (family - 1 as "battery (n+1) x 10 %"), IDX0 (j), EXT (bits), IDX1320 (j), 0x13 END; 0x31 = none
world_row('NOMINAL', 'BYTE layout, snapshot map: FAM0 0x27 (BYTE), IDX0 j = 8 (0x2F), EXT 0x28 (bit 0), IDX1320 j = 4 (0x2B)', [], W(),
          cross=[0x12, 0x27, 0x2F, 0x28, 0x2B, 0x13], regex=[r'spoken: 0x12@2000', r'port-3 rules: OK', r'!TransformStart'])
world_row('NOMINAL', 'BYTE layout, live window: IDX0 j = 4 (0x2B)', ['--map-live'], W(live=True), cross=[0x12, 0x27, 0x2B, 0x28, 0x2B, 0x13])
world_row('NOMINAL', 'BE16 (two bytes per element, first byte high), snapshot: FAM0 0x28, IDX0 j = 4, EXT 0x29 (bit 1), IDX1320 j = 2',
          ['--src-window', str(WIN), '--src-endian', 'be'], W(layout='be16'), cross=[0x12, 0x28, 0x2B, 0x29, 0x29, 0x13],
          base=BASE)
world_row('NOMINAL', 'BE16, live window: IDX0 j = 2', ['--src-window', str(WIN), '--src-endian', 'be', '--map-live'], W(layout='be16', live=True),
          cross=[0x12, 0x28, 0x29, 0x29, 0x29, 0x13], base=BASE)
world_row('NOMINAL', 'BYTE-HIGH (each byte in the high byte of its element), live: FAM0 0x29', ['--src-hibyte', '--map-live'],
          W(layout='hibyte', live=True), cross=[0x12, 0x29, 0x2B, 0x27, 0x2B, 0x13])
world_row('NOMINAL', 'BYTE-HIGH, snapshot: IDX0 j = 8', ['--src-hibyte'], W(layout='hibyte'), cross=[0x12, 0x29, 0x2F, 0x27, 0x2B, 0x13])
world_row('NOMINAL', 'BYTE with junk 0x5A in every high byte: still family BYTE (masked)', ['--src-hijunk'], W(layout='junk'),
          cross=[0x12, 0x27, 0x2F, 0x27, 0x2B, 0x13])
world_row('NOMINAL', 'LE16 (little-endian packed) ALIASES to family BYTE (the low byte of a word is the first byte): FAM0 0x27 but IDX0 j = 4 (snapshot) and EXT 0x27 (no element 3071), IDX1320 j = 2',
          ['--src-window', str(WIN), '--src-endian', 'le'], W(layout='le16'), cross=[0x12, 0x27, 0x2B, 0x27, 0x29, 0x13], base=BASE)
S('NOMINAL', 'sinkState 3 is accepted at every tick', E + PRESS + ['--mem', '59e=3'] + LEVER + STEPS + SRC,
  [spoken(ref_ids(W())), 'violations=0', 'pending=0'] + UNTOUCHED[:2], NOWRITE)
S('NOMINAL', 'the lever: no store reaches the caller\'s saved return address', H, [spoken(ref_ids(W()))],
  [r'caller-frame guard: stores to 0x0915, 0x0916 stop the run', r'!STOPPED'])
S('NOMINAL', 'the trap order of tick 0: FileFind FileFind S.FileSource SourceClose MessageSendLater SPEAK 0x12 (START needs no map)', H,
  [spoken(ref_ids(W()))], [r'timer message, MessageId 0x0012 -> FileFind FileFind S\.FileSource SourceClose MessageSendLater SPEAK 0x12'])

# ------------------------------------------------------------------ shifts, window, drops, failures
world_row('SHIFT', 'BYTE map shifted by +2 from the start (the map starts at byte 2): IDX0 j = 6', ['--map-shift-from', '0:2'], W(shift=(0, 2)),
          cross=None)
world_row('SHIFT', 'BYTE map shifted by +3 from byte 84,480 on: IDX1320 j = 1 (0x28), the start is normal', ['--map-shift-from', '84480:3'],
          W(shift=(84480, 3)))
world_row('SHIFT', 'BYTE map shifted by -2 from byte 84,480 on: IDX1320 j = 6', ['--map-shift-from', '84480:-2'], W(shift=(84480, -2)))
world_row('SHIFT', 'BYTE map shifted by +60 from byte 84,480 on (out of the 10-element search): IDX1320 none', ['--map-shift-from', '84480:60'],
          W(shift=(84480, 60)))
world_row('FAIL', 'SourceMap returns 0 from the start: FAM0, IDX0, EXT, IDX1320 all none (0x31)', ['--map-fail-pos', '0'], W(failpos=0),
          cross=[0x12, 0x31, 0x31, 0x31, 0x31, 0x13])
world_row('FAIL', 'SourceMap returns 0 from byte 84,490 on: only IDX1320 is none', ['--map-fail-pos', '84490'], W(failpos=84490),
          cross=[0x12, 0x27, 0x2F, 0x28, 0x31, 0x13])
world_row('WINDOW', 'SourceSize 2048: the map has 2,048 elements, EXT reads 0 for element 3071 (bit 0 clear)', ['--src-window', '2048'],
          W(window=2048), base=BASE + ['--src-unpacked'])
world_row('WINDOW', 'SourceSize 64: the 1,320 drops still run (>= 64 each time)', ['--src-window', '64'], W(window=64), base=BASE + ['--src-unpacked'])
world_row('WINDOW', 'SourceSize 63: the drop loop of IDX1320 refuses (< 64): none', ['--src-window', '63'], W(window=63), base=BASE + ['--src-unpacked'])
world_row('DROP', 'every SourceDrop advances 32 bytes: the 1,320 drops land at a different place: IDX1320 none', ['--drop-adv', '32'], W(adv=32))
world_row('DROP', 'every SourceDrop advances 128 bytes: IDX1320 none', ['--drop-adv', '128'], W(adv=128))
world_row('DROP', 'every SourceDrop, the 4- and 10-byte ones too, advances 64 bytes: the census sees the wrong place', ['--drop-adv', '64'], W(adv=64))

# ------------------------------------------------------------------ GUARD: nothing opened
for st in ('0', '1', '2', '5', '6', 'a', 'c', 'e', '10', '16'):
    S('GUARD', 'sinkState 0x%s: 0x3C only, no file opened, the chain ends' % st,
      E + PRESS + ['--mem', '59e=' + st] + LEVER + STEPS + SRC, [spoken([0x3C])] + UNTOUCHED, [r'!FileFind', r'!StreamFileSource'])
S('GUARD', 'no sinkState preset: refused', E + PRESS + LEVER + STEPS + SRC, [spoken([0x3C])] + UNTOUCHED, [r'!FileFind'])
S('GUARD', 'sinkState changes to 2 at 5000 ms (after tick 0, before tick 1): 12 then 3c, the chain ends',
  H + ['--mem-at', '5000:59e=2'], [spoken([0x12, 0x3C])] + UNTOUCHED, [r'file sources: 1 opened, 0 never closed'])
S('GUARD', 'sinkState changes to 2 at 25000 ms (after tick 2, before tick 3): 12, 27, 2f, 3c',
  H + ['--mem-at', '25000:59e=2'], [spoken([0x12, 0x27, 0x2F, 0x3C])] + UNTOUCHED, [r'file sources: 3 opened, 0 never closed'])

# ------------------------------------------------------------------ OPEN refusals
S('OPEN', 'FileFind refuses (first lookup): 0x17, the chain ends', H + ['--fail', 'FileFind'], [spoken([0x17])] + UNTOUCHED, [r'!StreamFileSource'])
S('OPEN', 'FileFind refuses the SECOND lookup (data_us): 0x17', H + ['--fail-after', 'FileFind=2'], [spoken([0x17])] + UNTOUCHED)
S('OPEN', 'StreamFileSource refuses: 0x17', H + ['--fail', 'StreamFileSource'], [spoken([0x17])] + UNTOUCHED)

# ------------------------------------------------------------------ PRESS handling
S('PRESS', 'a second press at 1000 ms (tick 0 pending): STOP, nothing opened', H + ['--press', '1000:4004'], ['spoken=', 'swallowed=2'] + UNTOUCHED, [r'!FileFind'])
S('PRESS', 'a second press at 8000 ms (tick 1 pending): STOP after the first id', H + ['--press', '8000:4004'],
  [spoken([0x12]), 'swallowed=2'] + UNTOUCHED, [r'file sources: 1 opened, 0 never closed'])
S('PRESS', 'a second press at 60000 ms (the run is over, 47 s): a SECOND full run', BASE[:-2] + ['--horizon', '120000', '--press', '60000:4004'] + SRC,
  [spoken(ref_ids(W()) * 2), 'swallowed=2'] + UNTOUCHED, [CLOSED.replace('6 opened', '12 opened')])
S('PRESS', 'a non-0x4004 event is replayed to the stock, nothing else happens',
  E + ['--press', '0:4003', '--once'] + STATE + LEVER + SRC, ['spoken=', 'replayed=1', 'swallowed=0'] + UNTOUCHED, [r'!FileFind'])
S('PRESS', 'an id that is not a stage (0x77) delivered to the handler: nothing happens',
  E + ['--pending', '77@1000', '--horizon', '10000'] + STATE + SRC, ['spoken='] + UNTOUCHED, [r'!FileFind'])
S('STUBS', 'no synthesised stub, no sink, no partition call, no transform, R3 silent', H, [spoken(ref_ids(W()))],
  NOWRITE + [r'port-3 rules: OK', r'!TransformAdpcmDecode', r'!TransformStart', r'!TransformStop', r'!PartitionGetRawSerialSource'])

# ------------------------------------------------------------------ FRAME (V11 D1): no store into the saved return address of any function
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
    words = 'probe200'
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
