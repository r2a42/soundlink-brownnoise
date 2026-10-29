#!/usr/bin/env python3
"""Offline gate for probe187, the READ-ONLY volume census (docs/deep/firmware-study-2026-10-12/T06c-volume-census-probe.md).

Runs the REAL probe187 words (build/hook/probe187_words.json, written by assemble_probe187.py) through
tools/xapemu.py via tools/cavesim.py's build(), in-process, with every memory access traced.  No
tool is modified.  Exit 0 = every check holds.

    python build/hook/assemble_probe187.py        # first: writes probe187_words.json
    python build/hook/gate_probe187.py

What it proves (model level; the speaker is not involved):
  G1  the reference: T06's decision (the verbatim signed-compare reference, "Census specification") mapped
      through the documented id table equals what the cave speaks, for EVERY point of a grid that includes
      the four boundaries -2300/-2301/-2200/-2199, tone == master at several levels, precedence, every
      gain type, every group word, every flag word, and the two null guards (about 3,500 states);
  G2  T06's own scenario table (cavesim rows) gives the expected id, row by row;
  G3  exactly one prompt id is spoken per 0x4004 press and nothing else is called (the trap list is empty
      but for the SPEAK back-call); the id is never in FORBIDDEN_IDS (empty stubs, stock battery
      low/full/high/medium); the set of ids spoken over the grid equals the documented table;
  G4  READ-ONLY, dynamically: on every 0x4004 run the only writes are inside the cave's own two stack
      frames, and the only data reads are @0x6d0, @0x72f, @0x528, the three DECODER fields and the gain
      type (the assembler asserts the same statically from the decoded words);
  G5  the null guards read nothing through a null pointer (no @(n,0) read);
  G6  every other event is replayed to the stock: one MessageSendLater(0xa5ce, AH=1), nothing spoken, no
      census read.

What it cannot show: what the speaker holds in those RAM words (that is the press), whether SPEAK of an id
above 0x38 behaves like the others (it is the same engine call; the ids were heard in the probe38 sweep),
or the signed-ness of the unit's real values beyond the arithmetic here.
"""
import os
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'xapvm'))
import cavesim as cs                                           # noqa: E402

WORDS = os.environ.get('PROBE187_WORDS') or os.path.join(ROOT, 'build', 'hook', 'probe187_words.json')   # env: mutation tests
ENTRY = 0x3E21D
D, Q = 0x3400, 0x3500            # the plugin instance and the audio-output config (clear of frame 0x0900,
                                 #   heap 0x2000 and the world model's MSGBUF 0x3000)
G_ID, G_GRP, G_MASTER, G_TONE, G_FLAG = Q + 14, D + 10, D + 11, D + 12, 0x528

# ---- the id table (must equal ID_* in assemble_probe187.py)
T06_TO_MINE = {0x23: 0x39, 0x24: 0x3A, 0x25: 0x3B, 0x26: 0x3C,
               **{i: i for i in range(0x27, 0x31)},
               0x33: 0x2B, 0x34: 0x3D}
FORBIDDEN = {0x02, 0x03, 0x05, 0x07, 0x0F, 0x1A, 0x1D, 0x31, 0x32, 0x33, 0x34}
DOCUMENTED = {0x27, 0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x2F, 0x30, 0x39, 0x3A, 0x3B, 0x3C, 0x3D}


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def t06_ref(s):
    """T06 'Decision', verbatim (signed compares). Returns T06's own id."""
    if s['p6d0'] == 0 or s['p72f'] == 0:
        return 0x23
    gt = s['gt']
    if gt == 0:
        return 0x24
    if gt == 2:
        return 0x25
    if gt != 1:
        return 0x26
    tone, master = s16(s['tone']), s16(s['master'])
    a = 0 if -2300 <= tone <= -2200 else (1 if tone == master else 2)
    b = (s['flag'] >> 12) & 1
    c = 0 if s['group'] == 2 else 1
    idx = a + 3 * b + 6 * c
    return 0x27 + idx if idx <= 9 else 0x33 + (idx - 10)


def expected(s):
    return T06_TO_MINE[t06_ref(s)]


vm, STATE, STUBS, TRAPNUMS = cs.build(WORDS)
# xapemu.VM.run() re-decodes the whole 236,514-word image on every call (about 0.12 s). Nothing outside the
# cave, the trap stubs, fn_189fb (the replayed stock call) and the SPEAK short-circuit can execute here, so
# for the bulk grid the decoded instruction table is restricted to those windows. The restriction is
# checked: before the grid, every distinct run shape is executed BOTH ways and the results compared.
import xapvm                                                   # noqa: E402
_decode, _find_stubs, _memo = xapvm.decode, xapvm.find_stubs, {}
RESTRICT = False
WINDOWS = [(0, 0x400), (0x18800, 0x18C00), (0xDF00, 0xE000), (0x39500, 0x39600)]


def _cached_decode(code, fold_zero=True):
    k = ('d', id(code), fold_zero)
    if k not in _memo:
        _memo[k] = list(_decode(code, fold_zero))
    if RESTRICT and fold_zero:
        k2 = ('r', id(code))
        if k2 not in _memo:
            _memo[k2] = [t for t in _memo[k] if any(lo <= t[0] < hi for lo, hi in WINDOWS)]
        return iter(_memo[k2])
    if RESTRICT and not fold_zero:                 # the unfolded table is only used for the cave's own span
        k3 = ('u', id(code))
        if k3 not in _memo:
            _memo[k3] = [t for t in _memo[k] if t[0] >= 0x3E000]
        return iter(_memo[k3])
    return iter(_memo[k])


def _cached_find_stubs(code):
    k = ('s', id(code))
    if k not in _memo:
        _memo[k] = _find_stubs(code)
    return _memo[k]


xapvm.decode, xapvm.find_stubs = _cached_decode, _cached_find_stubs
RAM0 = bytes(vm.ram)
FRAME = cs.FRAME


def run(event, s=None):
    """One run of the cave at the hook entry. Returns a dict."""
    vm.ram[:] = RAM0
    vm.trace_mem = True
    vm.log = []
    vm.AH = vm.AL = event
    vm.X = 0
    vm.Y = FRAME
    vm.C = vm.Z = vm.N = 0
    if s is not None:
        vm.wr(0x6D0, Q if s['p6d0'] else 0)
        vm.wr(0x72F, D if s['p72f'] else 0)
        vm.wr(G_ID, s['gt'])
        vm.wr(G_GRP, s['group'])
        vm.wr(G_MASTER, s['master'])
        vm.wr(G_TONE, s['tone'])
        vm.wr(G_FLAG, s['flag'])
        vm.log = []
    why, pc = vm.run(ENTRY, max_steps=2000)
    spoken = [v & 0xFFFF for a, v in vm.calls_seen if a == cs.SPEAK_ADDR]
    writes = [wa for k, wa, v in vm.log if k == 'W']
    reads = [wa for k, wa, v in vm.log if k == 'R']
    return {'why': why, 'spoken': spoken, 'traps': list(vm.traps), 'writes': writes, 'reads': reads,
            'calls': list(vm.calls_seen)}


fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)
        print('  FAIL', msg)


def state(gt=1, tone=0xF73E, master=0xE3E0, flag=0x9094, group=2, p6d0=1, p72f=1):
    return dict(gt=gt, tone=tone, master=master, flag=flag, group=group, p6d0=p6d0, p72f=p72f)


FRAME_LO, FRAME_HI = FRAME - 16, FRAME
READ_OK = {0x6D0, 0x72F, 0x528, G_ID, G_GRP, G_MASTER, G_TONE}


def check_run_clean(r, label, null_guard=False):
    check(r['why'] == 'leavel', '%s: ended with %s, not leavel' % (label, r['why']))
    check(len(r['spoken']) == 1, '%s: spoke %s, expected exactly one id' % (label, r['spoken']))
    check(r['traps'] == [], '%s: trap list not empty: %s' % (label, r['traps']))
    check(len(r['calls']) == 1, '%s: back-calls %s' % (label, r['calls']))
    bad_w = [hex(a) for a in r['writes'] if not (FRAME_LO <= a < FRAME_HI)]
    check(not bad_w, '%s: write outside the cave frames: %s' % (label, bad_w))
    bad_r = sorted({hex(a) for a in r['reads'] if a not in READ_OK and not (FRAME_LO <= a < FRAME_HI)})
    check(not bad_r, '%s: unexpected data read: %s' % (label, bad_r))
    if null_guard:
        nulls = [hex(a) for a in r['reads'] if a < 0x100]
        check(not nulls, '%s: read through a null pointer: %s' % (label, nulls))
    for i in r['spoken']:
        check(i not in FORBIDDEN, '%s: spoke forbidden id %#04x' % (label, i))


# ---------------------------------------------------------------------------- G2: T06's scenario table
print('G2 T06 scenario table (presets D=%#06x Q=%#06x), expected = my id (T06 id)' % (D, Q))
ROWS = [
    ('null config',                           state(p6d0=0),                                   0x39, 0x23),
    ('null decoder',                          state(p72f=0),                                   0x39, 0x23),
    ('hardware gain type',                    state(gt=0),                                     0x3A, 0x24),
    ('hybrid gain type',                      state(gt=2),                                     0x3B, 0x25),
    ('invalid gain type 3',                   state(gt=3),                                     0x3C, 0x26),
    ('predicted (master mute)',               state(master=0xE3E0, tone=0xF73E),               0x2A, 0x2A),
    ('predicted, group 0',                    state(master=0xE3E0, tone=0xF73E, group=0),      0x30, 0x30),
    ('flag clear, tone -2242',                state(flag=0x0094, master=0xE3E0, tone=0xF73E),  0x27, 0x27),
    ('flag clear, tone -2242, group 0',       state(flag=0x0094, group=0),                     0x2D, 0x2D),
    ('tone follows master (-4310)',           state(flag=0x0094, master=0xEF2A, tone=0xEF2A),  0x28, 0x28),
    ('tone follows master, group 0',          state(flag=0x0094, master=0xEF2A, tone=0xEF2A, group=0), 0x2E, 0x2E),
    ('flag clear, other (tone -1)',           state(flag=0x0094, master=0xE3E0, tone=0xFFFF),  0x29, 0x29),
    ('flag clear, other, group 0',            state(flag=0x0094, master=0xE3E0, tone=0xFFFF, group=0), 0x2F, 0x2F),
    ('flag set, other (-1500)',               state(master=0xE3E0, tone=0xFA24),               0x2C, 0x2C),
    ('flag set, other (-1500), group 0',      state(master=0xE3E0, tone=0xFA24, group=0),      0x3D, 0x34),
    ('flag set, tone = master (-4310)',       state(master=0xEF2A, tone=0xEF2A),               0x2B, 0x2B),
    ('flag set, tone = master, group 0',      state(master=0xEF2A, tone=0xEF2A, group=0),      0x2B, 0x33),
    ('precedence (tone = master = -2242)',    state(master=0xF73E, tone=0xF73E),               0x2A, 0x2A),
    ('boundary -2300',                        state(tone=0xF704),                              0x2A, 0x2A),
    ('boundary -2301',                        state(tone=0xF703),                              0x2C, 0x2C),
    ('boundary -2200',                        state(tone=0xF768),                              0x2A, 0x2A),
    ('boundary -2199',                        state(tone=0xF769),                              0x2C, 0x2C),
]
for name, s, want_mine, want_t06 in ROWS:
    r = run(0x4004, s)
    got = r['spoken'][0] if r['spoken'] else None
    ref = t06_ref(s)
    print('  %-40s spoke %s  expected %#04x (T06 id %#04x, reference %#04x)'
          % (name, ('%#04x' % got) if got is not None else '-', want_mine, want_t06, ref))
    check(ref == want_t06, '%s: reference %#04x != T06 table %#04x' % (name, ref, want_t06))
    check(got == want_mine, '%s: spoke %s, expected %#04x' % (name, got, want_mine))
    check_run_clean(r, name, null_guard=(s['p6d0'] == 0 or s['p72f'] == 0))

# ---------------------------------------------------------------------------- restricted decode == full decode
print('restricted-decode equivalence (the bulk grid runs with the restricted table)')
_shapes = [(0x4004, state()), (0x4004, state(p6d0=0)), (0x4004, state(p72f=0)), (0x4004, state(gt=0)),
           (0x4004, state(gt=2)), (0x4004, state(gt=3)), (0x4004, state(tone=0xFFFF, flag=0x0094, group=0)),
           (0x4004, state(tone=0xEF2A, master=0xEF2A)), (0x4005, state()), (0x400D, state()), (0x674C, state())]
_full = [run(ev, s) for ev, s in _shapes]
RESTRICT = True
_part = [run(ev, s) for ev, s in _shapes]
for (ev, s), x, y in zip(_shapes, _full, _part):
    check(x == y, 'restricted decode differs from the full decode for event %#06x %s' % (ev, s))
print('  %d run shapes identical (spoken ids, trap lists, every read, every write)' % len(_shapes))

# ---------------------------------------------------------------------------- G1 + G3 + G4: the grid
print('G1 grid against the T06 reference')
tones = [0xF704, 0xF703, 0xF73E, 0xF768, 0xF769, 0xE3E0, 0xEF2A, 0x0000, 0xFFFF, 0x8000, 0x7FFF, 0xFFFE, 0xFA24, 0xF9FF]
masters = [0xE3E0, 0xEF2A, 0xF73E, 0xF704, 0x0000, 0x7FFF, 0xFFFF, 0x8000]
flags = [0x9094, 0x0094, 0x1000, 0xEFFF, 0xFFFF, 0x0000]
groups = [0, 1, 2, 3, 0xFFFF, 0x8002]
seen = {}
n = 0
for tone in tones:
    for master in masters + [tone]:
        for flag in flags:
            for group in groups:
                s = state(tone=tone, master=master, flag=flag, group=group)
                r = run(0x4004, s)
                n += 1
                got = r['spoken'][0] if r['spoken'] else None
                want = expected(s)
                if got != want:
                    check(False, 'grid %s: spoke %s, expected %#04x' % (s, got, want))
                    if len(fails) > 20:
                        raise SystemExit('too many failures')
                seen.setdefault(got, 0)
                seen[got] += 1
                check_run_clean(r, 'grid#%d' % n)       # EVERY run: one id, no trap, writes only in the frames, reads only the 7 addresses
print('  %d digital states' % n)
for gt in (0, 2, 3, 4, 0x8001, 0xFFFF, 0x0100):
    for p6d0 in (0, 1):
        for p72f in (0, 1):
            s = state(gt=gt, p6d0=p6d0, p72f=p72f)
            r = run(0x4004, s)
            n += 1
            got = r['spoken'][0] if r['spoken'] else None
            check(got == expected(s), 'gt-grid %s: spoke %s, expected %#04x' % (s, got, expected(s)))
            seen[got] = seen.get(got, 0) + 1
            check_run_clean(r, 'gt gt=%#x p6d0=%d p72f=%d' % (gt, p6d0, p72f),
                            null_guard=(p6d0 == 0 or p72f == 0))
# gain type 1 with a null guard (the guard comes first)
for p6d0, p72f in ((0, 0), (0, 1), (1, 0)):
    s = state(p6d0=p6d0, p72f=p72f)
    r = run(0x4004, s)
    n += 1
    check(r['spoken'] == [0x39], 'guard %s: spoke %s' % ((p6d0, p72f), r['spoken']))
    check_run_clean(r, 'guard %d/%d' % (p6d0, p72f), null_guard=True)
print('  %d states in total; ids spoken (count):' % n)
for i in sorted(k for k in seen if k is not None):
    print('    %#04x  x%d' % (i, seen[i]))
check(None not in seen, 'a run spoke nothing')
check(set(seen) == DOCUMENTED, 'ids spoken %s != documented %s' % (sorted(map(hex, seen)), sorted(map(hex, DOCUMENTED))))
check(not (set(seen) & FORBIDDEN), 'a forbidden id was spoken')
# the merge is exactly the documented one: the only many-to-one fold of T06 ids
inv = {}
for t, m in T06_TO_MINE.items():
    inv.setdefault(m, []).append(t)
check(sorted((hex(m), sorted(map(hex, ts))) for m, ts in inv.items() if len(ts) > 1) == [('0x2b', ['0x2b', '0x33'])],
      'merge set: %s' % {hex(m): ts for m, ts in inv.items() if len(ts) > 1})

# ---------------------------------------------------------------------------- G6: other events replayed
print('G6 events other than 0x4004 are replayed to the stock')
for ev in (0x4005, 0x400D, 0x400E, 0x674C, 0x4744, 0x4003, 0x4045, 0x0000, 0xFFFF):
    s = state()
    r = run(ev, s)
    t = r['traps']
    check(r['spoken'] == [], 'event %#06x spoke %s' % (ev, r['spoken']))
    check(r['why'] == 'leavel', 'event %#06x ended with %s' % (ev, r['why']))
    check(len(t) == 1 and (t[0][1] & 0xFFFF) == 0xA5CE and (t[0][1] >> 16) == 1,
          'event %#06x: trap list %s (expected one MessageSendLater AL=0xa5ce AH=1)' % (ev, t))
    census_reads = {a for a in r['reads'] if a in (0x6D0, 0x72F, 0x528, G_ID, G_GRP, G_MASTER, G_TONE)}
    check(not census_reads, 'event %#06x read census state: %s' % (ev, sorted(map(hex, census_reads))))
    print('  event %#06x: replayed, trap list = %d, spoken = none' % (ev, len(t)))

# ---------------------------------------------------------------------------- G7: the clocked world model
# tools/cavesim.py --world (rules R1-R6, the DSP and clock model) with the census state preset by --mem.
# The census touches no port, so every run must report violations=0, chunks=0, pending=0.
print('G7 clocked world model (tools/cavesim.py, --expect), one subprocess per row')
import subprocess
PRE = ['--mem', '72f=%x' % D, '--mem', '6d0=%x' % Q, '--mem', '%x=1' % G_ID, '--mem', '%x=2' % G_GRP,
       '--mem', '%x=e3e0' % G_MASTER, '--mem', '%x=f73e' % G_TONE, '--mem', '528=9094']


def pre(**kw):
    d = {'6d0': '%x' % Q, '72f': '%x' % D, '%x' % G_ID: '1', '%x' % G_GRP: '2', '%x' % G_MASTER: 'e3e0',
         '%x' % G_TONE: 'f73e', '528': '9094'}
    d.update({k: v for k, v in kw.items()})
    out = []
    for k, v in d.items():
        out += ['--mem', '%s=%s' % (k, v)]
    return out


WORLD = [
    ('predicted: 0x2A, nothing else',          pre() + ['--press', '0:4004', '--once'],
     ['spoken=2a', 'violations=0', 'chunks=0', 'pending=0', 'swallowed=1', 'replayed=0']),
    ('hardware gain type: 0x3A',               pre(**{'%x' % G_ID: '0'}) + ['--press', '0:4004', '--once'],
     ['spoken=3a', 'violations=0', 'chunks=0', 'pending=0']),
    ('hybrid: 0x3B',                           pre(**{'%x' % G_ID: '2'}) + ['--press', '0:4004', '--once'],
     ['spoken=3b', 'violations=0', 'chunks=0', 'pending=0']),
    ('invalid type: 0x3C',                     pre(**{'%x' % G_ID: '3'}) + ['--press', '0:4004', '--once'],
     ['spoken=3c', 'violations=0', 'chunks=0', 'pending=0']),
    ('null decoder (DSP not loaded): 0x39',    pre(**{'72f': '0'}) + ['--press', '0:4004', '--once'],
     ['spoken=39', 'violations=0', 'chunks=0', 'pending=0']),
    ('PS differs, group 0: 0x3D',              pre(**{'%x' % G_TONE: 'fa24', '%x' % G_GRP: '0'}) + ['--press', '0:4004', '--once'],
     ['spoken=3d', 'violations=0', 'chunks=0', 'pending=0']),
    ('a later press re-runs the census (J-R4): 0x2A twice',
     pre() + ['--press', '0:4004', '--press', '9000:4004', '--horizon', '20000'],
     ['spoken=2a,2a', 'violations=0', 'chunks=0', 'pending=0', 'swallowed=2']),
    ('DSP model down: the census is RAM-only, still 0x2A',
     pre() + ['--dsp', 'down', '--press', '0:4004', '--once'],
     ['spoken=2a', 'violations=0', 'chunks=0', 'pending=0']),
    ('null config @0x6d0 = 0: 0x39',             pre(**{'6d0': '0'}) + ['--press', '0:4004', '--once'],
     ['spoken=39', 'violations=0', 'chunks=0', 'pending=0']),
] + [
    # one world row per digital id 0x27..0x30 and 0x2B/0x3D (a, b, c chosen to hit idx 0..11)
    ('digital idx %2d -> %#04x' % (idx, want),
     pre(**{'%x' % G_TONE: tone, '%x' % G_MASTER: master, '528': flag, '%x' % G_GRP: grp}) + ['--press', '0:4004', '--once'],
     ['spoken=%02x' % want, 'violations=0', 'chunks=0', 'pending=0'])
    for idx, want, tone, master, flag, grp in [
        (0, 0x27, 'f73e', 'e3e0', '0094', '2'), (1, 0x28, 'ef2a', 'ef2a', '0094', '2'),
        (2, 0x29, 'ffff', 'e3e0', '0094', '2'), (3, 0x2a, 'f73e', 'e3e0', '9094', '2'),
        (4, 0x2b, 'ef2a', 'ef2a', '9094', '2'), (5, 0x2c, 'fa24', 'e3e0', '9094', '2'),
        (6, 0x2d, 'f73e', 'e3e0', '0094', '0'), (7, 0x2e, 'ef2a', 'ef2a', '0094', '0'),
        (8, 0x2f, 'ffff', 'e3e0', '0094', '0'), (9, 0x30, 'f73e', 'e3e0', '9094', '0'),
        (10, 0x2b, 'ef2a', 'ef2a', '9094', '0'), (11, 0x3d, 'fa24', 'e3e0', '9094', '0')]
] + [
    ('a volume event 0x400d is replayed, nothing spoken',
     pre() + ['--press', '0:400d', '--once'],
     ['spoken=', 'violations=0', 'chunks=0', 'pending=0', 'replayed=1', 'swallowed=0']),
    ('a stray 0x4005 is replayed, nothing spoken',
     pre() + ['--press', '0:4005', '--once'],
     ['spoken=', 'violations=0', 'chunks=0', 'pending=0', 'replayed=1', 'swallowed=0']),
]
for name, args, exps in WORLD:
    cmd = [sys.executable, os.path.join(ROOT, 'tools', 'cavesim.py'), 'probe187', '--entry', '0x3E21D'] + args
    for e in exps:
        cmd += ['--expect', e]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    ok = r.returncode == 0 and 'FAIL' not in r.stdout and 'STOPPED' not in r.stdout
    print('  %-62s %s' % (name, 'ok' if ok else 'FAIL'))
    if not ok:
        check(False, 'world row %r: rc=%d  %s' % (name, r.returncode, r.stdout[-600:].replace(chr(10), ' | ')))

print()
if fails:
    print('GATE FAILED: %d failure(s)' % len(fails))
    sys.exit(1)
print('probe187 gate: %d census states + %d scenario rows + 9 replay events + %d world rows, 0 failed' % (n, len(ROWS), len(WORLD)))
