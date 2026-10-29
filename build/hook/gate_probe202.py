#!/usr/bin/env python3
"""Offline world-model gate for probe202 (G1: the ALIGNMENT CENSUS, a READ-ONLY diagnostic on the STOCK data_us) -- 2026-10-15.
NOT independently reviewed. NO device, no flash tool: pure emulation.

Runs the real words (build/hook/probe202_words.json, written by assemble_probe202.py) through tools/cavesim.py's clocked world model.
The file the cave opens is the STOCK data_us (the world's default). Every row's expected id sequence comes from an INDEPENDENT reference
model written here (ref_ids): the decision procedure re-stated in Python over the stock bytes and the row's world parameters (leading
elements as a function of the window start and of the history, live or snapshot map, window, drop advance, map failure), not read off
the cave. Hard-coded cross-checks pin the reference model on the key rows. FRAME rows run tools/framecheck.py and cavesim's static
hazard scan.

    python build/hook/assemble_probe202.py                     # first (writes probe202_words.json)
    python build/hook/gate_probe202.py [--part I/N] [--list] [--words PATH]
    --words PATH  runs a mutated copy of the words: the gate must FAIL there (mutation rows)
    --first       stop at the first failing row (used for the mutated copies)
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
SCAN_N = 100
GRAM_E = 11
NONE_ID, NOMAP_ID, START_ID, END_ID = 0x31, 0x16, 0x12, 0x13
# (drops of 64, one extra drop, old-pointer row): the same table as the assembler's ROWDEF (rows 0, 1, 2, 3, 5, 6, 7 of its list)
ROWS = [(1, 0, False), (10, 0, False), (0, 640, False), (10, 1, False), (1320, 0, False), (1320, 14, False), (1320, 0, True)]
NT = 3 * len(ROWS) + 2
# hard-coded cross-check of the grams (stock bytes at start + 11), so the gate does not trust its own table:
assert [US[64 * n + x + GRAM_E:64 * n + x + GRAM_E + 2].hex() for n, x, o in ROWS] == ['0020', '1544', '1544', '4415', '000b', '006c', '000b']


# ------------------------------------------------------------------ the reference model (independent of the cave's code)
class W:
    """one row's world parameters"""
    def __init__(self, window=WIN, lead=0, rules=(), last=(), ndrop=(), live=False, adv=None, shift=None, failpos=None, junk=0, hibyte=False):
        self.window, self.lead, self.rules, self.last, self.ndrop = window, lead, list(rules), list(last), list(ndrop)
        self.live, self.adv, self.shift, self.failpos, self.junk, self.hibyte = live, adv, shift, failpos, junk, hibyte

    def size(self, pos):
        return min(len(US) - pos, self.window)

    def lead_at(self, pos, nd, lastsz):
        lead = self.lead
        for m, r, n in self.rules:
            if pos % m == r:
                lead = n
                break
        for s, n in self.last:
            if lastsz == s:
                lead = n
                break
        for c, n in self.ndrop:
            if nd >= c:
                lead = n
                break
        return lead

    def elements(self, pos, nd, lastsz):
        start = pos
        if self.shift and pos >= self.shift[0]:
            start = max(0, pos + self.shift[1])
        data = US[start:start + self.size(pos)]
        if self.hibyte:
            return [0xDD] * self.lead_at(pos, nd, lastsz) + [b << 8 for b in data]
        return [0xDD] * self.lead_at(pos, nd, lastsz) + [b | self.junk for b in data]

    def mapok(self, pos):
        return not (self.failpos is not None and pos >= self.failpos)

    def drop(self, pos, n=64):
        return min(pos + (n if self.adv is None else self.adv), len(US))


def at(el, i):
    return el[i] if i < len(el) else 0                  # past the end of the map: data memory the model leaves at zero


def gram_of(n, x):
    p = 64 * n + x
    return US[p + GRAM_E], US[p + GRAM_E + 1]


def scan(el, g):
    for j in range(SCAN_N):
        if (at(el, j) & 0xFF) == g[0] and (at(el, j + 1) & 0xFF) == g[1]:
            return j
    return None


def row_value(w, n, x, old):
    """the first index j of the gram (an int), None = not found, 'nomap' = SourceMap returned 0"""
    g = gram_of(n, x)
    pos, nd, last = 0, 0, None
    el0 = None
    if old:
        if not w.mapok(pos):
            return 'nomap'
        el0 = w.elements(pos, nd, last)
    for _ in range(n):
        pos = w.drop(pos)
        nd += 1
        last = 64
    if x:
        pos = w.drop(pos, x)
        nd += 1
        last = x
    if old:
        el = w.elements(pos, nd, last) if w.live else el0
    else:
        if not w.mapok(pos):
            return 'nomap'
        el = w.elements(pos, nd, last)
    return scan(el, g)


def row_ids(v):
    if v == 'nomap':
        return [NOMAP_ID] * 3
    if v is None:
        return [NONE_ID] * 3
    hi, lo = v // 10, v % 10
    return [0x27 + hi, 0x27 + lo, 0x27 + (hi + lo) % 10]


def ref_ids(w):
    ids = [START_ID]
    for n, x, old in ROWS:
        ids += row_ids(row_value(w, n, x, old))
    return ids + [END_ID]


# ------------------------------------------------------------------ the rows
E = ['--entry', '0x3E21D']
PRESS = ['--press', '0:4004']
LEVER = ['--caller-frame', '23']
STATE = ['--mem', '59e=d']
STEPS = ['--steps', '300000000', '--horizon', '260000']
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
CLOSED = r'file sources: %d opened, 0 never closed' % NT


def world_row(group, name, extra_args, w, regex=(), cross=None, base=None):
    ids = ref_ids(w)
    if cross is not None:
        assert ids == cross, (name, [hex(i) for i in ids], [hex(i) for i in cross])        # the reference model, pinned
    S(group, name, (base or H) + extra_args, [spoken(ids), 'violations=0', 'pending=0'] + UNTOUCHED[:2], list(NOWRITE) + [CLOSED] + list(regex))


def tri(j):
    hi, lo = j // 10, j % 10
    return [0x27 + hi, 0x27 + lo, 0x27 + (hi + lo) % 10]


NONE3 = [0x31] * 3
NOMAP3 = [0x16] * 3

# ------------------------------------------------------------------ NOMINAL: the hypotheses about the alignment rule
# ids: 0x12 START, per row (P64, P640 by ten drops, P640 by one drop of 640, P641, P84480, P84494, P84480 through the OLD pointer):
# hi digit, lo digit, check (hi + lo) mod 10, each as "battery (v+1) x 10 %" (0x27 + v); 0x31 = none, 0x16 = SourceMap 0; 0x13 END.
# j = GRAM_E (11) + lead.
world_row('NOMINAL', 'H0: lead 1 at every start (probe200: +1 at the unaligned starts), snapshot old row: j = 12 (0x28 0x29 0x2a), the old row none', ['--map-lead', '1'], W(lead=1),
          cross=[0x12] + tri(12) * 6 + NONE3 + [0x13], regex=[r'spoken: 0x12@2000', r'port-3 rules: OK', r'!TransformStart'])
world_row('NOMINAL', 'H1: lead 0 everywhere: j = 11', [], W(lead=0), cross=[0x12] + tri(11) * 6 + NONE3 + [0x13])
world_row('NOMINAL', 'H2: lead 1 unaligned, lead 64 at the 64-aligned starts (j = 75): rows 0, 1, 2, 4 aligned; rows 3, 5 unaligned', ['--map-lead', '1', '--map-lead-rule', '64:0:64'],
          W(lead=1, rules=[(64, 0, 64)]), cross=[0x12] + tri(75) * 3 + tri(12) + tri(75) + tri(12) + NONE3 + [0x13])
world_row('NOMINAL', 'H3: lead 1 unaligned, lead 22 aligned (j = 33; just outside probe201 window of 40 at E = 18)', ['--map-lead', '1', '--map-lead-rule', '64:0:22'],
          W(lead=1, rules=[(64, 0, 22)]), cross=[0x12] + tri(33) * 3 + tri(12) + tri(33) + tri(12) + NONE3 + [0x13])
world_row('NOMINAL', 'H4: lead 1 unaligned, lead 90 aligned (j = 101, out of the 100-element search): aligned rows none', ['--map-lead', '1', '--map-lead-rule', '64:0:90'],
          W(lead=1, rules=[(64, 0, 90)]), cross=[0x12] + NONE3 * 3 + tri(12) + NONE3 + tri(12) + NONE3 + [0x13])
world_row('NOMINAL', 'H5: lead 0 aligned, lead 1 unaligned: j = 11 aligned, 12 unaligned', ['--map-lead', '1', '--map-lead-rule', '64:0:0'],
          W(lead=1, rules=[(64, 0, 0)]), cross=[0x12] + tri(11) * 3 + tri(12) + tri(11) + tri(12) + NONE3 + [0x13])
world_row('NOMINAL', 'H6: lead = the residue class of the start: 641 -> 7, 84494 -> 3, aligned -> 0', ['--map-lead', '0', '--map-lead-rule', '64:1:7', '--map-lead-rule', '64:14:3'],
          W(lead=0, rules=[(64, 1, 7), (64, 14, 3)]), cross=[0x12] + tri(11) * 3 + tri(18) + tri(11) + tri(14) + NONE3 + [0x13])
world_row('NOMINAL', 'H7 (history): lead 1, but 40 after a LAST drop of 640 (one big drop): row 2 j = 51, the others 12', ['--map-lead', '1', '--map-lead-last', '640:40'],
          W(lead=1, last=[(640, 40)]), cross=[0x12] + tri(12) * 2 + tri(51) + tri(12) * 3 + NONE3 + [0x13])
world_row('NOMINAL', 'H8 (history): lead 1, 30 after 1000 or more drop calls: rows 4, 5 j = 41', ['--map-lead', '1', '--map-lead-ndrop', '1000:30'],
          W(lead=1, ndrop=[(1000, 30)]), cross=[0x12] + tri(12) * 4 + tri(41) * 2 + NONE3 + [0x13])
world_row('NOMINAL', 'H9: a LIVE window (old pointer follows the position), lead 1: the old row j = 12', ['--map-lead', '1', '--map-live'], W(lead=1, live=True),
          cross=[0x12] + tri(12) * 7 + [0x13])
world_row('NOMINAL', 'H10: live window, lead 1 unaligned / 64 aligned: the old row (aligned 84,480) j = 75', ['--map-lead', '1', '--map-live', '--map-lead-rule', '64:0:64'],
          W(lead=1, live=True, rules=[(64, 0, 64)]), cross=[0x12] + tri(75) * 3 + tri(12) + tri(75) + tri(12) + tri(75) + [0x13])
world_row('NOMINAL', 'H11: lead 5 at every start: j = 16', ['--map-lead', '5'], W(lead=5), cross=[0x12] + tri(16) * 6 + NONE3 + [0x13])
world_row('NOMINAL', 'H12: lead 88 at every start: j = 99, the LAST element searched (hi 9, lo 9, check 8)', ['--map-lead', '88'], W(lead=88), cross=[0x12] + tri(99) * 6 + NONE3 + [0x13])
world_row('NOMINAL', 'H13: lead 89 at every start: j = 100, one past the search: none', ['--map-lead', '89'], W(lead=89), cross=[0x12] + NONE3 * 7 + [0x13])
world_row('NOMINAL', 'BYTE with junk 0x5A in every high byte: still found (the compare is masked): j = 12', ['--map-lead', '1', '--src-hijunk'], W(lead=1, junk=0x5A00),
          cross=[0x12] + tri(12) * 6 + NONE3 + [0x13])
world_row('NOMINAL', 'each byte in the HIGH byte of its element (masked low byte 0): the model decides (mostly none)', ['--map-lead', '1', '--src-hibyte'],
          W(lead=1, hibyte=True))
S('NOMINAL', 'sinkState 3 is accepted at every tick', E + PRESS + ['--mem', '59e=3'] + LEVER + STEPS + SRC + ['--map-lead', '1'],
  [spoken(ref_ids(W(lead=1))), 'violations=0', 'pending=0'] + UNTOUCHED[:2], NOWRITE)
S('NOMINAL', 'the lever: no store reaches the caller\'s saved return address', H + ['--map-lead', '1'], [spoken(ref_ids(W(lead=1)))],
  [r'caller-frame guard: stores to 0x0915, 0x0916 stop the run', r'!STOPPED'])
S('NOMINAL', 'the trap order of tick 0: FileFind FileFind S.FileSource SourceClose MessageSendLater SPEAK 0x12 (START needs no map)', H + ['--map-lead', '1'],
  [spoken(ref_ids(W(lead=1)))], [r'timer message, MessageId 0x0012 -> FileFind FileFind S\.FileSource SourceClose MessageSendLater SPEAK 0x12'])
S('NOMINAL', 'the trap order of a drop tick (row 0, tick 1): one SourceDrop then SourceMap then SourceClose then SPEAK', H + ['--map-lead', '1'],
  [spoken(ref_ids(W(lead=1)))], [r'timer message, MessageId 0x0013 -> FileFind FileFind S\.FileSource SourceDrop SourceMap SourceClose MessageSendLater SPEAK 0x28'])
S('NOMINAL', 'the old row opens the map BEFORE its drops (tick 19, id 0x25: SourceMap, then the 1,320 drops, then no second SourceMap)', H + ['--map-lead', '1'],
  [spoken(ref_ids(W(lead=1)))], [r'timer message, MessageId 0x0025 -> FileFind FileFind S\.FileSource SourceMap (SourceDrop ){1320}SourceClose MessageSendLater SPEAK 0x31'])

# ------------------------------------------------------------------ shifts, drops, failures
world_row('SHIFT', 'map shifted by -2 bytes from byte 84,480 on (the map starts 2 bytes early, element j holds byte j + 2): rows 4, 5 j = 10, lead 1 elsewhere',
          ['--map-lead', '1', '--map-shift-from', '84480:2'], W(lead=1, shift=(84480, 2)))
world_row('SHIFT', 'map starts 3 bytes LATE from 600 on (shift -3): rows 1-5 find the gram at j = 15 (+lead 1)', ['--map-lead', '1', '--map-shift-from', '600:-3'], W(lead=1, shift=(600, -3)))
world_row('FAIL', 'SourceMap returns 0 from the start: every fresh row 0x16 x 3, the old row (map at 0 refused too)', ['--map-lead', '1', '--map-fail-pos', '0'], W(lead=1, failpos=0),
          cross=[0x12] + NOMAP3 * 7 + [0x13])
world_row('FAIL', 'SourceMap returns 0 from byte 84,000 on: rows 4 and 5 (fresh) 0x16, the old row finds nothing (snapshot)', ['--map-lead', '1', '--map-fail-pos', '84000'], W(lead=1, failpos=84000),
          cross=[0x12] + tri(12) * 4 + NOMAP3 * 2 + NONE3 + [0x13])
world_row('DROP', 'every SourceDrop advances 32 bytes: the starts land elsewhere; the model follows the file bytes', ['--map-lead', '1', '--drop-adv', '32'], W(lead=1, adv=32))
world_row('DROP', 'every SourceDrop advances 128 bytes', ['--map-lead', '1', '--drop-adv', '128'], W(lead=1, adv=128))
world_row('DROP', 'every SourceDrop advances 65 bytes (one too many): the starts drift by one byte per drop', ['--map-lead', '1', '--drop-adv', '65'], W(lead=1, adv=65))

# ------------------------------------------------------------------ GUARD: nothing opened, the chain ends silently
for st in ('0', '1', '2', '5', '6', 'a', 'c', 'e', '10', '16'):
    S('GUARD', 'sinkState 0x%s: silent, no file opened, the chain ends' % st,
      E + PRESS + ['--mem', '59e=' + st] + LEVER + STEPS + SRC, ['spoken='] + UNTOUCHED, [r'!FileFind', r'!StreamFileSource', r'!SPEAK 0x'])
S('GUARD', 'no sinkState preset: silent', E + PRESS + LEVER + STEPS + SRC, ['spoken='] + UNTOUCHED, [r'!FileFind'])
S('GUARD', 'sinkState changes to 2 at 5000 ms (after tick 0, before tick 1): 12 only, the chain ends',
  H + ['--map-lead', '1', '--mem-at', '5000:59e=2'], [spoken([0x12])] + UNTOUCHED, [r'file sources: 1 opened, 0 never closed'])
S('GUARD', 'sinkState changes to 2 at 25000 ms (after tick 2, before tick 3): 12, 28, 29',
  H + ['--map-lead', '1', '--mem-at', '25000:59e=2'], [spoken([0x12, 0x28, 0x29])] + UNTOUCHED, [r'file sources: 3 opened, 0 never closed'])

# ------------------------------------------------------------------ OPEN refusals (silent)
S('OPEN', 'FileFind refuses (first lookup): silent, the chain ends', H + ['--fail', 'FileFind'], ['spoken='] + UNTOUCHED, [r'!StreamFileSource'])
S('OPEN', 'FileFind refuses the SECOND lookup (data_us): silent', H + ['--fail-after', 'FileFind=2'], ['spoken='] + UNTOUCHED)
S('OPEN', 'StreamFileSource refuses: silent', H + ['--fail', 'StreamFileSource'], ['spoken='] + UNTOUCHED)

# ------------------------------------------------------------------ PRESS handling
S('PRESS', 'a second press at 1000 ms (tick 0 pending): STOP, nothing opened', H + ['--press', '1000:4004'], ['spoken=', 'swallowed=2'] + UNTOUCHED, [r'!FileFind'])
S('PRESS', 'a second press at 8000 ms (tick 1 pending): STOP after the first id', H + ['--press', '8000:4004'],
  [spoken([0x12]), 'swallowed=2'] + UNTOUCHED, [r'file sources: 1 opened, 0 never closed'])
S('PRESS', 'a second press at 100000 ms (a tick pending in the middle of the run): STOP, the rest never spoken', H + ['--map-lead', '1', '--press', '100000:4004'],
  [spoken([0x12] + tri(12) * 3 + tri(12)[:1]), 'swallowed=2'] + UNTOUCHED)
S('PRESS', 'a second press at 195000 ms (the LAST tick, id 0x28, is pending): STOP, the END prompt is never spoken', H + ['--map-lead', '1', '--press', '195000:4004'],
  [spoken(ref_ids(W(lead=1))[:-1]), 'swallowed=2'] + UNTOUCHED, [r'file sources: %d opened, 0 never closed' % (NT - 1)])
S('PRESS', 'a second press at 230000 ms (the run is over, 200 s): a SECOND full run', BASE[:-2] + ['--horizon', '480000', '--press', '230000:4004'] + SRC + ['--map-lead', '1'],
  [spoken(ref_ids(W(lead=1)) * 2), 'swallowed=2'] + UNTOUCHED, [CLOSED.replace('%d opened' % NT, '%d opened' % (2 * NT))])
S('PRESS', 'a non-0x4004 event is replayed to the stock, nothing else happens',
  E + ['--press', '0:4003', '--once'] + STATE + LEVER + SRC, ['spoken=', 'replayed=1', 'swallowed=0'] + UNTOUCHED, [r'!FileFind'])
S('PRESS', 'an id that is not a stage (0x77) delivered to the handler: nothing happens',
  E + ['--pending', '77@1000', '--horizon', '10000'] + STATE + SRC, ['spoken='] + UNTOUCHED, [r'!FileFind'])
S('PRESS', 'an id just above the last stage (0x%02x) delivered to the handler: nothing happens' % (0x12 + NT),
  E + ['--pending', '%x@1000' % (0x12 + NT), '--horizon', '10000'] + STATE + SRC, ['spoken='] + UNTOUCHED, [r'!FileFind'])
S('STUBS', 'no synthesised stub, no sink, no partition call, no transform, R3 silent', H + ['--map-lead', '1'], [spoken(ref_ids(W(lead=1)))],
  NOWRITE + [r'port-3 rules: OK', r'!TransformAdpcmDecode', r'!TransformStart', r'!TransformStop', r'!PartitionGetRawSerialSource'])

# ------------------------------------------------------------------ FRAME: no store into the saved return address of any function
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
    words = 'probe202'
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
