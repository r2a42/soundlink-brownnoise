#!/usr/bin/env python3
"""Offline world-model gate for probe206 (RAW READOUT of the served staged data_us as digit prompts) -- 2026-10-15. NOT independently reviewed.
NO device, no flash tool: pure emulation. Runs the real words (build/hook/probe206_words.json, written by assemble_probe206.py) through tools/cavesim.py's clocked world model.
Every row's expected id sequence comes from an INDEPENDENT reference model (ref_ids): for each row of build/hook/params_probe206.py the window start (n SourceDrop(64)), the map (lead
elements + the file bytes), the element E, v = element & 0xFF, its digits hundreds / tens / units / check = (h + t + u) mod 10, each spoken as 0x27 + d; START 0x12, END 0x13, SourceMap 0 -> 0x16.
    python build/hook/assemble_probe206.py                     # first (writes probe206_words.json)
    python build/hook/gate_probe206.py [--part I/N] [--list] [--words PATH] [--first]
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
import params_probe206 as PRM  # noqa: E402
ORACLE = open(os.path.join(ROOT, 'build', 'payload', 'r3', 'brown_8000_58968_s63.adpcm'), 'rb').read()
STG = L.stage(ORACLE, 1320)['new_us']
assert len(US0) == 219528 and len(STG) == 219528

WIN = 3072
ROWS = list(PRM.ROWS)
NW = len(ROWS)
NT = 2 + 4 * NW
START, END, NOMAP, DIG0 = 0x12, 0x13, 0x16, 0x27


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
VZ_REL, VZ = _variant('vz_zeros', zero_all=True)                                                    # the staged file serves zeros everywhere
VST_REL, VST = _variant('vst_stock', base=US0)                                                      # the STOCK file (staged bytes not served)
_PAYBYTES = bytes(STG[64 * (1320 + _j // 28) + 18 + _j % 28] for _j in range(58968))


def _displaced(d):
    data = bytearray(US0)
    for _j, _b in enumerate(_PAYBYTES):
        _pos = 64 * (1320 + _j // 28) + 18 + _j % 28 - d
        if 0 <= _pos < len(data):
            data[_pos] = _b
    return _variant('vd%d_displaced' % d, base=bytes(data))


VD64_REL, VD64 = _displaced(64)
VD128_REL, VD128 = _displaced(128)
# a file whose staged cells serve payload XOR 0x5A (a "something else" served at the cells)
_x = bytearray(STG)
for _j in range(58968):
    _x[64 * (1320 + _j // 28) + 18 + _j % 28] ^= 0x5A
VX_REL, VX = _variant('vx_xor5a', base=bytes(_x))


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


def digits_ids(v):
    h, t, u = v // 100, (v // 10) % 10, v % 10
    return [DIG0 + h, DIG0 + t, DIG0 + u, DIG0 + (h + t + u) % 10]


def row_ids(w, i):
    n, e = ROWS[i]
    pos, nd, last = 0, 0, None
    for _ in range(n):
        pos = w.drop(pos)
        nd += 1
        last = 64
    if not w.mapok(pos):
        return [NOMAP] * 4
    el = w.elements(pos, nd, last)
    return digits_ids(at(el, e) & 0xFF)


def ref_ids(w):
    ids = [START]
    for i in range(NW):
        ids += row_ids(w, i)
    return ids + [END]


# ------------------------------------------------------------------ the rows
E = ['--entry', '0x3E21D']
PRESS = ['--press', '0:4004']
LEVER = ['--caller-frame', '23']
STATE = ['--mem', '59e=d']
STEPS = ['--steps', '400000000', '--horizon', str(2000 + 9000 * NT + 30000)]
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


# the expected values by hand (file byte = 64 n + E - 1 with lead 1): stock 84,496 = %02x, 84,497 = %02x; the built (payload) bytes at 84,498.. = 77 7f 77 c6 bf 10 93 91
NS = ['--src-unpacked', '--src-window', str(WIN)]
world_row('NOMINAL', 'E0 (everything as expected): staged file served, lead 1: eight bytes read, each as four digit prompts', ['--map-lead', '1'], W(lead=1),
          regex=[r'spoken: 0x12@2000', r'port-3 rules: OK', r'!TransformStart'])
world_row('NOMINAL', 'lead 0: element E is file byte 64 n + E: shifted by one', [], W(lead=0))
world_row('NOMINAL', 'lead 5', ['--map-lead', '5'], W(lead=5))
world_row('NOMINAL', 'junk 0x5A in every high byte (the read is masked): the same digits as E0', ['--map-lead', '1', '--src-hijunk'], W(lead=1, junk=True))
world_row('NOMINAL', 'the staged file serves ZEROS everywhere: every byte 0 (digits 0 0 0 0 -> "battery 10%" x4 per row)', ['--map-lead', '1'], W(file=VZ, lead=1), base=BASE + fs(VZ_REL))
world_row('NOMINAL', 'the STOCK file is served (staged bytes not served)', ['--map-lead', '1'], W(file=US0, lead=1), base=BASE + NS)
world_row('NOMINAL', 'payload cells displaced by 64 bytes', ['--map-lead', '1'], W(file=VD64, lead=1), base=BASE + fs(VD64_REL))
world_row('NOMINAL', 'payload cells displaced by 128 bytes', ['--map-lead', '1'], W(file=VD128, lead=1), base=BASE + fs(VD128_REL))
world_row('NOMINAL', 'payload cells served XOR 0x5A', ['--map-lead', '1'], W(file=VX, lead=1), base=BASE + fs(VX_REL))
S('NOMINAL', 'sinkState 3 is accepted at every tick', E + PRESS + ['--mem', '59e=3'] + LEVER + STEPS + STAGED + ['--map-lead', '1'],
  [spoken(ref_ids(W(lead=1))), 'violations=0', 'pending=0'] + UNTOUCHED[:2], NOWRITE)
S('NOMINAL', 'the lever: no store reaches the caller\'s saved return address', H + ['--map-lead', '1'], [spoken(ref_ids(W(lead=1)))],
  [r'caller-frame guard: stores to 0x0915, 0x0916 stop the run', r'!STOPPED'])
S('NOMINAL', 'the trap order of tick 0 (the START, no map): FileFind FileFind S.FileSource SourceClose MessageSendLater SPEAK 0x12', H + ['--map-lead', '1'],
  [spoken(ref_ids(W(lead=1)))], [r'timer message, MessageId 0x0012 -> FileFind FileFind S\.FileSource SourceClose MessageSendLater SPEAK 0x12'])
for _i in range(NW):
    S('NOMINAL', 'the trap order of the first tick of row %d: %d SourceDrop(64), one SourceMap, SourceClose, SPEAK' % (_i, ROWS[_i][0]), H + ['--map-lead', '1'],
      [spoken(ref_ids(W(lead=1)))], [r'timer message, MessageId 0x%04x -> FileFind FileFind S\.FileSource (SourceDrop ){%d}SourceMap SourceClose MessageSendLater SPEAK 0x%02x'
                                    % (0x12 + 1 + 4 * _i, ROWS[_i][0], row_ids(W(lead=1), _i)[0])])

# ------------------------------------------------------------------ failures, drops
world_row('FAIL', 'SourceMap returns 0 from the start: every row speaks "english" (0x16) x4', ['--map-lead', '1', '--map-fail-pos', '0'], W(lead=1, failpos=0))
world_row('FAIL', 'SourceMap returns 0 from byte 84,000 on: W1 fine, W2 and W3 class 0', ['--map-lead', '1', '--map-fail-pos', '84000'], W(lead=1, failpos=84000))
world_row('FAIL', 'SourceMap returns 0 from byte 84,450 on: only W3 (84,480) is class 0', ['--map-lead', '1', '--map-fail-pos', '84450'], W(lead=1, failpos=84450))
world_row('DROP', 'every SourceDrop advances 32 bytes: the starts land elsewhere; the model follows the file bytes', ['--map-lead', '1', '--drop-adv', '32'], W(lead=1, adv=32))
world_row('DROP', 'every SourceDrop advances 128 bytes', ['--map-lead', '1', '--drop-adv', '128'], W(lead=1, adv=128))

# ------------------------------------------------------------------ GUARD: nothing opened, silent
for st in ('0', '1', '2', '5', '6', 'a', 'c', 'e', '10', '16'):
    S('GUARD', 'sinkState 0x%s: SILENT, no file opened, the chain ends' % st, E + PRESS + ['--mem', '59e=' + st] + LEVER + STEPS + STAGED,
      ['spoken='] + UNTOUCHED, [r'!FileFind', r'!StreamFileSource', r'!SPEAK 0x'])
S('GUARD', 'no sinkState preset: silent', E + PRESS + LEVER + STEPS + STAGED, ['spoken='] + UNTOUCHED, [r'!FileFind'])
S('GUARD', 'sinkState changes to 2 at 5000 ms (after tick 0, before tick 1): 30 only, the chain ends',
  H + ['--map-lead', '1', '--mem-at', '5000:59e=2'], [spoken([START])] + UNTOUCHED, [r'file sources: 1 opened, 0 never closed'])
S('GUARD', 'sinkState changes to 2 at 30000 ms (after tick 3): the first three ticks only',
  H + ['--map-lead', '1', '--mem-at', '30000:59e=2'], [spoken(ref_ids(W(lead=1))[:4])] + UNTOUCHED, [r'file sources: 4 opened, 0 never closed'])

# ------------------------------------------------------------------ OPEN refusals (silent)
S('OPEN', 'FileFind refuses (first lookup): silent', H + ['--fail', 'FileFind'], ['spoken='] + UNTOUCHED, [r'!StreamFileSource'])
S('OPEN', 'FileFind refuses the SECOND lookup (data_us): silent', H + ['--fail-after', 'FileFind=2'], ['spoken='] + UNTOUCHED)
S('OPEN', 'StreamFileSource refuses: silent', H + ['--fail', 'StreamFileSource'], ['spoken='] + UNTOUCHED)

# ------------------------------------------------------------------ PRESS handling
S('PRESS', 'a second press at 1000 ms (tick 0 pending): STOP, nothing opened', H + ['--press', '1000:4004'], ['spoken=', 'swallowed=2'] + UNTOUCHED, [r'!FileFind'])
S('PRESS', 'a second press at 8000 ms (tick 1 pending): STOP after the first id', H + ['--press', '8000:4004'],
  [spoken([START]), 'swallowed=2'] + UNTOUCHED, [r'file sources: 1 opened, 0 never closed'])
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
    words = 'probe206'
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
