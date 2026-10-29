#!/usr/bin/env python3
"""Offline world-model gate for probe203 (H1: a READ-ONLY diagnostic ON THE STAGED data_us -- are the staged bytes served, and where) -- 2026-10-15.
PREPARATION ONLY: the window starts in build/hook/params_probe204.py are PLACEHOLDERS until the probe202 numbers are filled in; not flash-cleared; no independent review.
NO device, no flash tool: pure emulation.

Runs the real words (build/hook/probe204_words.json, written by assemble_probe204.py) through tools/cavesim.py's clocked world model. The file the cave opens is the
STAGED data_us (build/payload/r3/data_us_r3_staged), the STOCK one, or a generated VARIANT (build/payload/r3/data_us_h1_*, new files) in the rows that need a map the
staged file cannot produce (payload moved, payload and stock pair both present). Every row's expected id sequence comes from an INDEPENDENT reference model (ref_ids): the
window start, the map (leading elements as a function of the window alignment and of the history), the three gram searches and the class (0..5) restated in Python over
the file bytes, then the class bits and their parity. Hard-coded cross-checks pin the reference model on the key rows. FRAME rows run tools/framecheck.py and cavesim's
static hazard scan.

    python build/hook/assemble_probe204.py                     # first (writes probe204_words.json)
    python build/hook/gate_probe203.py [--part I/N] [--list] [--words PATH] [--first]
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
US0 = open(os.path.join(ROOT, 'firmware', 'bose', 'extracted', 'internal_fs', 'data_us'), 'rb').read()
sys.path.insert(0, os.path.join(ROOT, 'build', 'hook'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import narrow184_lib as L      # noqa: E402
import params_probe204 as PRM  # noqa: E402
ORACLE = open(os.path.join(ROOT, 'build', 'payload', 'r3', 'brown_8000_58968_s63.adpcm'), 'rb').read()
STG = L.stage(ORACLE, 1320)['new_us']
assert len(US0) == 219528 and len(STG) == 219528

WIN = 3072
SCAN_N = 100
BIT1, BIT0 = 0x30, 0x3B
WINDOWS_FULL = list(PRM.WINDOWS)
WINDOWS = [(w[0], w[1]) for w in WINDOWS_FULL]
NW = len(WINDOWS)
NT = 2 + 4 * NW
NOPAIR = bytes(PRM.NOPAIR)
assert all(x == 0 for n, x in WINDOWS), 'aligned windows only (the extra drop was cut from the cave)'


def _pairs(w):
    """(control, second, third) byte pairs of a window: control and second from the STAGED file, third from the STOCK file (NOPAIR if None)"""
    n, x, cp, sp, tp = w
    return bytes(STG[cp:cp + 2]), bytes(STG[sp:sp + 2]), (NOPAIR if tp is None else bytes(US0[tp:tp + 2]))


GRAMS = [_pairs(w) for w in WINDOWS_FULL]
D = WINDOWS_FULL[0][3] - WINDOWS_FULL[0][2]
assert all(w[3] - w[2] == D for w in WINDOWS_FULL)
LAST = WINDOWS_FULL[-1]                      # the window that carries the staged (payload) position
PAYSP = LAST[3]                              # file position of the second pair of the last window (84,498 for the filled-in constants)
PAY = bytes(STG[PAYSP:PAYSP + 2])
STK = bytes(US0[PAYSP:PAYSP + 2])
# hard-coded cross-check of the filled-in constants (stock bytes and the payload start); a changed block needs these edited deliberately
if [tuple(w) for w in WINDOWS_FULL] == [(10, 0, 649, 653, None), (1319, 0, 84425, 84429, None), (1320, 0, 84494, 84498, 84498)]:
    assert PAY == bytes([0x77, 0x7F]) and STK == bytes([0x6A, 0x00]), (PAY, STK)
    assert GRAMS[2][0] == bytes([0x69, 0x00]) and D == 4 and NOPAIR == bytes([0x80, 0xED])
    assert [g[0].hex() for g in GRAMS] == [US0[649:651].hex(), US0[84425:84427].hex(), '6900']


def _variant(name, edits=(), base=None, zero_from=None, zero_all=False):
    """a generated VARIANT of the staged file (new files; never rewritten when identical)"""
    data = bytearray(STG if base is None else base)
    if zero_all:
        data = bytearray(len(data))
    if zero_from is not None:
        data[zero_from:] = bytes(len(data) - zero_from)
    for pos, vals in edits:
        data[pos:pos + len(vals)] = bytes(vals)
    rel = 'build/payload/r3/data_us_i1_' + name
    p = os.path.join(ROOT, rel)
    if not (os.path.exists(p) and open(p, 'rb').read() == bytes(data)):
        with open(p, 'wb') as f:
            f.write(data)
    return rel, bytes(data)


STAGED_REL = 'build/payload/r3/data_us_r3_staged'
_sp = os.path.join(ROOT, STAGED_REL)
if not (os.path.exists(_sp) and open(_sp, 'rb').read() == STG):
    with open(_sp, 'wb') as _f:
        _f.write(STG)
V1_REL, V1 = _variant('v1_neither', [(PAYSP, [0x55, 0x55])])                                        # neither payload nor stock pair at the payload position
V4_REL, V4 = _variant('v4_moved', [(PAYSP, [0x55, 0x55]), (PAYSP + 6, list(PAY))])                  # payload gram 6 bytes later, stock pair gone
V5_REL, V5 = _variant('v5_both', [(PAYSP, list(STK)), (PAYSP + 6, list(PAY))])                      # stock pair at the position AND the payload 6 later
V6_REL, V6 = _variant('v6_nearmiss', [(PAYSP, [STK[0] | 1, STK[1] | 1])])                           # a near miss of the stock pair
VZ_REL, VZ = _variant('vz_zeros', zero_all=True)                                                    # the staged file serves zeros everywhere
VZ80_REL, VZ80 = _variant('vz80_late_zeros', zero_from=80000)                                       # zeros from byte 80,000 on
VZS_REL, VZS = _variant('vzs_span_zeros', zero_from=64 * 1320)                                      # zeros from the start of the staged span on
VP_REL, VP = _variant('vp_nopair', [(WINDOWS_FULL[0][3], [0x55, 0x55]), (WINDOWS_FULL[0][3] + 40, list(NOPAIR)),
                                     (WINDOWS_FULL[1][3], [0x55, 0x55]), (WINDOWS_FULL[1][3] + 40, list(NOPAIR))])   # W1, W2: second pair destroyed, the impossible pair planted
VST_REL, VST = _variant('vst_stock', base=US0)                                                      # the STOCK file (staged bytes not served)


# ---- probe204: the DISPLACEMENT variants (J0-displacement-model.md): the stock file with the payload cells landing d bytes EARLIER than built
_PAYBYTES = bytes(STG[64 * (1320 + _j // 28) + 18 + _j % 28] for _j in range(58968))


def _displaced(d):
    data = bytearray(US0)
    for _j, _b in enumerate(_PAYBYTES):
        _pos = 64 * (1320 + _j // 28) + 18 + _j % 28 - d
        if 0 <= _pos < len(data):
            data[_pos] = _b
    return _variant('vd%d_displaced' % d, base=bytes(data))


VD0_REL, VD0 = _displaced(0)
VD30_REL, VD30 = _displaced(30)
VD64_REL, VD64 = _displaced(64)
VD128_REL, VD128 = _displaced(128)


# ------------------------------------------------------------------ the reference model (independent of the cave's code)
class W:
    """one row's world: file bytes, window, default leading elements, alignment rules (M, R, N), history rules, junk, map failure, drop advance"""
    def __init__(self, file=STG, window=WIN, lead=0, rules=(), last=(), ndrop=(), junk=False, failpos=None, adv=None):
        self.file, self.window, self.lead, self.rules, self.last, self.ndrop = file, window, lead, tuple(rules), tuple(last), tuple(ndrop)
        self.junk, self.failpos, self.adv = junk, failpos, adv

    def size(self, pos):
        return min(len(US0) - pos, self.window)

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
        data = self.file[pos:pos + self.size(pos)]
        return [0xDD] * self.lead_at(pos, nd, lastsz) + [(0x5A00 | b) if self.junk else b for b in data]

    def mapok(self, pos):
        return not (self.failpos is not None and pos >= self.failpos)

    def drop(self, pos, n=64):
        return min(pos + (n if self.adv is None else self.adv), len(US0))


def at(el, i):
    return el[i] if i < len(el) else 0


def scan(el, g):
    for j in range(SCAN_N):
        if (at(el, j) & 0xFF) == g[0] and (at(el, j + 1) & 0xFF) == g[1]:
            return j
    return None


def window_class(w, i):
    n, x = WINDOWS[i]
    pos, nd, last = 0, 0, None
    for _ in range(n):
        pos = w.drop(pos)
        nd += 1
        last = 64
    if not w.mapok(pos):
        return 0
    el = w.elements(pos, nd, last)
    c3, s3, t3 = GRAMS[i]
    jc, jp, js = scan(el, c3), scan(el, s3), scan(el, t3)
    if jc is None:
        return 0
    if jp is not None:
        return 3 if jp - jc == D else 4
    return 2 if js is not None else 1


def class_bits(c):
    par = 1 if c in (1, 2, 4) else 0                   # the classes 0..4 with an odd number of one bits
    return [(c >> 2) & 1, (c >> 1) & 1, c & 1, par]


def ref_ids(w):
    bits = [1, 0]
    for i in range(NW):
        bits += class_bits(window_class(w, i))
    return [BIT1 if b else BIT0 for b in bits]


def ids_of_classes(classes):
    bits = [1, 0]
    for c in classes:
        bits += class_bits(c)
    return [BIT1 if b else BIT0 for b in bits]


# ------------------------------------------------------------------ the rows
E = ['--entry', '0x3E21D']
PRESS = ['--press', '0:4004']
LEVER = ['--caller-frame', '23']
STATE = ['--mem', '59e=d']
STEPS = ['--steps', '80000000', '--horizon', '140000']
BASE = E + PRESS + STATE + LEVER + STEPS


def fs(rel):
    return ['--fs-add', 'NowSpeakTTS/data_us=@' + rel, '--src-unpacked', '--src-window', str(WIN)]


STAGED = fs(STAGED_REL)
H = BASE + STAGED

SCEN = []


def S(group, name, args, expects, regex=(), **extra):
    SCEN.append((group, name, args, list(expects), list(regex), extra))


def spoken(ids):
    return 'spoken=' + ','.join('%02x' % i for i in ids)


UNTOUCHED = ['flushes=0', 'p2closed=False', 'violations=0']
NOWRITE = [r'!OverwriteSink', r'!SinkMap', r'!SinkClaim', r'!SinkFlush', r'!PartitionSetMessageDigest', r'!SinkClose', r'!SYNTHESISED TRAP STUB']
CLOSED = r'file sources: %d opened, 0 never closed' % NT


def world_row(group, name, extra, w, base=None, cross=None, regex=()):
    ids = ref_ids(w)
    if cross is not None:
        assert ids == ids_of_classes(cross), (name, [hex(i) for i in ids], cross)           # the reference model, pinned
    S(group, name, (base or H) + extra, [spoken(ids), 'violations=0', 'pending=0'] + UNTOUCHED[:2], list(NOWRITE) + [CLOSED] + list(regex))


# classes: 0 control not found, 1 control only, 2 control + stock (third) pair, 3 second pair at control + D, 4 second pair elsewhere
# the cross-checks below are valid for the FILLED-IN windows (W1 640 stock early, W2 84,416 stock before the span, W3 84,480 staged); other window lists skip them
PH = [tuple(w) for w in WINDOWS_FULL] == [(10, 0, 649, 653, None), (1319, 0, 84425, 84429, None), (1320, 0, 84494, 84498, 84498)]


def X(cross):
    return cross if PH else None


NS = ['--src-unpacked', '--src-window', str(WIN)]
world_row('NOMINAL', 'E0 (everything as expected): staged file served, lead 1 at every start: W1 W2 W3 class 3 3 3 (bits 0 1 1 0 each)', ['--map-lead', '1'], W(lead=1), cross=X([3, 3, 3]),
          regex=[r'spoken: 0x30@2000', r'port-3 rules: OK', r'!TransformStart'])
world_row('NOMINAL', 'lead 0 everywhere: the classes do not depend on the lead (contiguity): 3 3 3', [], W(lead=0), cross=X([3, 3, 3]))
world_row('NOMINAL', 'lead 5 everywhere: 3 3 3', ['--map-lead', '5'], W(lead=5), cross=X([3, 3, 3]))
world_row('NOMINAL', 'lead 88: controls at elements 96 / 97 / 102: W1 W2 control found, second pair outside: class 1, W3 control outside: 0', ['--map-lead', '88'], W(lead=88), cross=X([1, 1, 0]))
world_row('NOMINAL', 'lead 90 at the 64-aligned starts (all three windows are aligned): controls at 98 / 99 / 104: classes 1 1 0', ['--map-lead', '1', '--map-lead-rule', '64:0:90'],
          W(lead=1, rules=[(64, 0, 90)]), cross=X([1, 1, 0]))
world_row('NOMINAL', 'lead 64 at the aligned starts: 3 3 3', ['--map-lead', '1', '--map-lead-rule', '64:0:64'], W(lead=1, rules=[(64, 0, 64)]), cross=X([3, 3, 3]))
world_row('NOMINAL', 'history: lead 1, but 30 after 1,000 drop calls (W2 and W3 only): 3 3 3', ['--map-lead', '1', '--map-lead-ndrop', '1000:30'],
          W(lead=1, ndrop=[(1000, 30)]), cross=X([3, 3, 3]))
world_row('NOMINAL', 'history: lead 1, but 85 after 1,000 drop calls (W2: control at 94 and second at 98 found, class 3; W3: control at 99, second outside, class 1): 3 3 1', ['--map-lead', '1', '--map-lead-ndrop', '1000:85'],
          W(lead=1, ndrop=[(1000, 85)]), cross=X([3, 3, 1]))
world_row('NOMINAL', 'junk 0x5A in every high byte (the search is masked): 3 3 3', ['--map-lead', '1', '--src-hijunk'], W(lead=1, junk=True), cross=X([3, 3, 3]))
world_row('NOMINAL', 'the staged file serves ZEROS everywhere: classes 0 0 0 (bits all 0)', ['--map-lead', '1'], W(file=VZ, lead=1), base=BASE + fs(VZ_REL), cross=X([0, 0, 0]))
world_row('NOMINAL', 'zeros from byte 80,000 on (W1 fine, W2 and W3 dead): classes 3 0 0', ['--map-lead', '1'], W(file=VZ80, lead=1), base=BASE + fs(VZ80_REL), cross=X([3, 0, 0]))
world_row('NOMINAL', 'zeros from the staged span on (W1 and W2 fine, W3 dead): classes 3 3 0', ['--map-lead', '1'], W(file=VZS, lead=1), base=BASE + fs(VZS_REL), cross=X([3, 3, 0]))
world_row('NOMINAL', 'the STOCK file is served at the payload position (staged bytes not served): classes 3 3 2 (bits 0 1 0 1 at W3)', ['--map-lead', '1'], W(file=US0, lead=1),
          base=BASE + NS, cross=X([3, 3, 2]))
world_row('NOMINAL', 'variant 7 (W1 and W2: the second pair destroyed and the NOPAIR pair planted 40 bytes on): classes 2 2 3', ['--map-lead', '1'], W(file=VP, lead=1), base=BASE + fs(VP_REL), cross=X([2, 2, 3]))
world_row('NOMINAL', 'variant 1 (neither payload nor stock pair at the payload position): classes 3 3 1', ['--map-lead', '1'], W(file=V1, lead=1), base=BASE + fs(V1_REL), cross=X([3, 3, 1]))
world_row('NOMINAL', 'variant 6 (a near miss of the stock pair, low bits set): classes 3 3 1', ['--map-lead', '1'], W(file=V6, lead=1), base=BASE + fs(V6_REL), cross=X([3, 3, 1]))
world_row('NOMINAL', 'variant 4 (the payload pair 6 bytes later, the stock pair gone): classes 3 3 4', ['--map-lead', '1'], W(file=V4, lead=1), base=BASE + fs(V4_REL), cross=X([3, 3, 4]))
world_row('NOMINAL', 'variant 5 (the stock pair at the position AND the payload pair 6 later): the payload wins: classes 3 3 4', ['--map-lead', '1'], W(file=V5, lead=1), base=BASE + fs(V5_REL), cross=X([3, 3, 4]))
PH4 = [tuple(w) for w in WINDOWS_FULL] == [(1319, 0, 84494, 84498, None), (1319, 0, 84425, 84429, None), (1320, 0, 84558, 84562, None)]
if PH4:
    world_row('NOMINAL', 'probe204 d=0 (the cells exactly where built): W1 W2 W3 classes 3 3 3', ['--map-lead', '1'], W(file=VD0, lead=1), base=BASE + fs(VD0_REL), cross=[3, 3, 3])
    world_row('NOMINAL', 'probe204 d=64 (the cells one period EARLIER): the payload pair of W1 at 84,434 and of W3 at 84,498, both before their controls: classes 4 3 4', ['--map-lead', '1'], W(file=VD64, lead=1), base=BASE + fs(VD64_REL), cross=[4, 3, 4])
    world_row('NOMINAL', 'probe204 d=128 (two periods earlier): the payload pairs fall outside the windows: classes 1 3 1', ['--map-lead', '1'], W(file=VD128, lead=1), base=BASE + fs(VD128_REL), cross=[1, 3, 1])
    world_row('NOMINAL', 'probe204 d=30 (a partial displacement): classes follow the reference model', ['--map-lead', '1'], W(file=VD30, lead=1), base=BASE + fs(VD30_REL))
S('NOMINAL', 'sinkState 3 is accepted at every tick', E + PRESS + ['--mem', '59e=3'] + LEVER + STEPS + STAGED + ['--map-lead', '1'],
  [spoken(ref_ids(W(lead=1))), 'violations=0', 'pending=0'] + UNTOUCHED[:2], NOWRITE)
S('NOMINAL', 'the lever: no store reaches the caller\'s saved return address', H + ['--map-lead', '1'], [spoken(ref_ids(W(lead=1)))],
  [r'caller-frame guard: stores to 0x0915, 0x0916 stop the run', r'!STOPPED'])
S('NOMINAL', 'the trap order of tick 0 (the sync, no map): FileFind FileFind S.FileSource SourceClose MessageSendLater SPEAK 0x30', H + ['--map-lead', '1'],
  [spoken(ref_ids(W(lead=1)))], [r'timer message, MessageId 0x0012 -> FileFind FileFind S\.FileSource SourceClose MessageSendLater SPEAK 0x30'])
for _i in range(NW):
    _bit0 = class_bits(window_class(W(lead=1), _i))[0]
    S('NOMINAL', 'the trap order of the first tick of window %d: %d SourceDrop(64), one SourceMap, SourceClose, SPEAK' % (_i, WINDOWS[_i][0]), H + ['--map-lead', '1'],
      [spoken(ref_ids(W(lead=1)))], [r'timer message, MessageId 0x%04x -> FileFind FileFind S\.FileSource (SourceDrop ){%d}SourceMap SourceClose MessageSendLater SPEAK 0x%02x'
                                    % (0x12 + 2 + 4 * _i, WINDOWS[_i][0], BIT1 if _bit0 else BIT0)])

# ------------------------------------------------------------------ failures, drops
world_row('FAIL', 'SourceMap returns 0 from the start: class 0 everywhere (bits 0 0 0 0)', ['--map-lead', '1', '--map-fail-pos', '0'], W(lead=1, failpos=0), cross=X([0, 0, 0]))
world_row('FAIL', 'SourceMap returns 0 from byte 84,000 on: W1 fine, W2 and W3 class 0', ['--map-lead', '1', '--map-fail-pos', '84000'], W(lead=1, failpos=84000),
          cross=X([3, 0, 0]))
world_row('FAIL', 'SourceMap returns 0 from byte 84,450 on: only W3 (84,480) is class 0', ['--map-lead', '1', '--map-fail-pos', '84450'], W(lead=1, failpos=84450), cross=X([3, 3, 0]))
world_row('DROP', 'every SourceDrop advances 32 bytes: the starts land elsewhere; the model follows the file bytes', ['--map-lead', '1', '--drop-adv', '32'], W(lead=1, adv=32))
world_row('DROP', 'every SourceDrop advances 128 bytes', ['--map-lead', '1', '--drop-adv', '128'], W(lead=1, adv=128))

# ------------------------------------------------------------------ GUARD: nothing opened, silent
for st in ('0', '1', '2', '5', '6', 'a', 'c', 'e', '10', '16'):
    S('GUARD', 'sinkState 0x%s: SILENT, no file opened, the chain ends' % st, E + PRESS + ['--mem', '59e=' + st] + LEVER + STEPS + STAGED,
      ['spoken='] + UNTOUCHED, [r'!FileFind', r'!StreamFileSource', r'!SPEAK 0x'])
S('GUARD', 'no sinkState preset: silent', E + PRESS + LEVER + STEPS + STAGED, ['spoken='] + UNTOUCHED, [r'!FileFind'])
S('GUARD', 'sinkState changes to 2 at 5000 ms (after tick 0, before tick 1): 30 only, the chain ends',
  H + ['--map-lead', '1', '--mem-at', '5000:59e=2'], [spoken([BIT1])] + UNTOUCHED, [r'file sources: 1 opened, 0 never closed'])
S('GUARD', 'sinkState changes to 2 at 30000 ms (after tick 3): the first three ticks only',
  H + ['--map-lead', '1', '--mem-at', '30000:59e=2'], [spoken(ref_ids(W(lead=1))[:4])] + UNTOUCHED, [r'file sources: 4 opened, 0 never closed'])

# ------------------------------------------------------------------ OPEN refusals (silent)
S('OPEN', 'FileFind refuses (first lookup): silent', H + ['--fail', 'FileFind'], ['spoken='] + UNTOUCHED, [r'!StreamFileSource'])
S('OPEN', 'FileFind refuses the SECOND lookup (data_us): silent', H + ['--fail-after', 'FileFind=2'], ['spoken='] + UNTOUCHED)
S('OPEN', 'StreamFileSource refuses: silent', H + ['--fail', 'StreamFileSource'], ['spoken='] + UNTOUCHED)

# ------------------------------------------------------------------ PRESS handling
S('PRESS', 'a second press at 1000 ms (tick 0 pending): STOP, nothing opened', H + ['--press', '1000:4004'], ['spoken=', 'swallowed=2'] + UNTOUCHED, [r'!FileFind'])
S('PRESS', 'a second press at 8000 ms (tick 1 pending): STOP after the first id', H + ['--press', '8000:4004'],
  [spoken([BIT1]), 'swallowed=2'] + UNTOUCHED, [r'file sources: 1 opened, 0 never closed'])
S('PRESS', 'a second press in the middle of the run (tick 7 pending): STOP, the rest never spoken', H + ['--map-lead', '1', '--press', '60000:4004'],
  [spoken(ref_ids(W(lead=1))[:7]), 'swallowed=2'] + UNTOUCHED)
S('PRESS', 'a second press during the LAST tick: STOP, the last prompt never spoken', H + ['--map-lead', '1', '--press', '%d:4004' % (2000 + 9000 * (NT - 2) + 4000)],
  [spoken(ref_ids(W(lead=1))[:-1]), 'swallowed=2'] + UNTOUCHED)
S('PRESS', 'a second press after the run (%d s): a SECOND full run' % (2 + 9 * (NT - 1)), BASE[:-2] + ['--horizon', '%d' % (2 * (2000 + 9000 * NT) + 60000), '--press', '%d:4004' % (2000 + 9000 * (NT - 1) + 20000)] + STAGED + ['--map-lead', '1'],
  [spoken(ref_ids(W(lead=1)) * 2), 'swallowed=2'] + UNTOUCHED, [CLOSED.replace('%d opened' % NT, '%d opened' % (2 * NT))])
S('PRESS', 'a non-0x4004 event is replayed to the stock, nothing else happens', E + ['--press', '0:4003', '--once'] + STATE + LEVER + STAGED,
  ['spoken=', 'replayed=1', 'swallowed=0'] + UNTOUCHED, [r'!FileFind'])
S('PRESS', 'an id that is not a stage (0x77) delivered to the handler: nothing happens', E + ['--pending', '77@1000', '--horizon', '10000'] + STATE + STAGED,
  ['spoken='] + UNTOUCHED, [r'!FileFind'])
S('PRESS', 'an id just above the last stage (0x%02x) delivered to the handler: nothing happens' % (0x12 + NT), E + ['--pending', '%x@1000' % (0x12 + NT), '--horizon', '10000'] + STATE + STAGED,
  ['spoken='] + UNTOUCHED, [r'!FileFind'])
S('STUBS', 'no synthesised stub, no sink, no partition call, no transform, R3 silent', H + ['--map-lead', '1'], [spoken(ref_ids(W(lead=1)))],
  NOWRITE + [r'port-3 rules: OK', r'!TransformAdpcmDecode', r'!TransformStart', r'!TransformStop', r'!PartitionGetRawSerialSource'])

# ------------------------------------------------------------------ FRAME
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
    words = 'probe204'
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
            if '--first' in argv:
                break
    print('\n%d scenario(s) run, %d failed' % (ran, fails))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
