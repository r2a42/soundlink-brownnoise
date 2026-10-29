#!/usr/bin/env python3
"""verify_probe156: the re-arm, in cavesim.

probe155 played loud noise for seven seconds from one source and one transform.
probe156 makes that build a state-free subroutine and re-runs it on a 5000 ms
timer, so the port never runs dry.

What this harness checks that no earlier one could:

  * the ARM runs the 0x1072 gate and then the build; the HANDLER runs the build
    WITHOUT the gate (re-gating purges the tone cbuffer -- the probe105/106 bug);
  * every pass calls StreamDisconnect(0, ksink) BEFORE TransformAdpcmDecode, so
    the sink is free for a new transform (connectivity, not memory: probes
    151/153 proved neither object can be reclaimed);
  * every successful pass arms MessageSendLater with the cave's FLASHED TaskData
    0xBA3C and a 5000 ms delay -- and every FAILING pass does NOT re-arm, so a
    broken rebuild stops instead of spinning;
  * the build is genuinely state-free: three consecutive ticks produce identical
    trap sequences, which is what lets the ARM and the HANDLER share it;
  * both path strings are still contiguous and both pointers still pinned.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'xapvm'))
import cavesim                                                  # noqa: E402

WORDS = os.path.join(ROOT, 'build/hook/probe156_words.json')
CAVE = 0x3E21D
DIRNAME, FILENAME = 'NowSpeakTTS', 'data_us'
CONST_BASE, CONST_ORIGIN = 0x7400, 236514
TASK_ADDR, DELAY_MS = 0xBA3C, 5000
KSINK_H = 0x55C0

IDS = {0x10: '"and"               -- StreamKalimbaSink(3) returned 0',
       0x22: '"conference call"   -- FileFind lost the NowSpeakTTS directory',
       0x1B: '"call from unknown" -- FileFind lost data_us',
       0x24: '"switching call"    -- StreamFileSource returned 0',
       0x25: '"call with"         -- TransformAdpcmDecode / TransformStart refused'}

BUILD = ['StreamKalimbaSink', 'StreamDisconnect', 'FileFind', 'FileFind',
         'StreamFileSource', 'TransformAdpcmDecode', 'TransformStart',
         'MessageSendLater']
FORBIDDEN = ('malloc', 'MessageSinkTask', 'SourceClose', 'TransformStop',
             'TransformDisconnect', 'TransformFromSink', 'StreamRegionSource',
             'SinkClaim', 'SinkFlush', 'StreamPartitionOverwriteSink')

words = json.load(open(WORDS))
handler = 0x30000 | (words['0x3e21f'] & 0xFFFF)   # low word of the const TaskData


def build(fail=()):
    vm, state, stubs, trapnums = cavesim.build(WORDS, fail=set(fail))
    return vm, trapnums, {v: k for k, v in trapnums.items()}


def digest(vm, inv):
    names = [inv.get(t, 'trap_%02x' % t) for t, _, _ in vm.traps]
    recs = [(inv.get(t, 'trap_%02x' % t), a, b) for t, a, b in vm.traps]
    spoken = [v & 0xFFFF for a, v in vm.calls_seen if a == cavesim.SPEAK_ADDR]
    for f in FORBIDDEN:
        assert f not in names, 'probe156 must never call %s: %s' % (f, names)
    return names, recs, spoken


def run_arm(fail=()):
    vm, tn, inv = build(fail)
    vm.Y = cavesim.FRAME
    why, pc = vm.run(CAVE)
    assert why == 'leavel', (why, hex(pc))
    return (vm, inv) + digest(vm, inv)


def run_tick(vm, inv):
    vm.traps = []
    vm.calls_seen.clear()
    vm.AH = 0
    vm.AL = TASK_ADDR
    vm.Y = cavesim.FRAME
    why, pc = vm.run(handler)
    assert why == 'leavel', (why, hex(pc))
    return digest(vm, inv)


def strdata(text):
    w = {int(k, 16): v & 0xFFFF for k, v in words.items()}
    pat = [ord(c) for c in text] + [0]
    for base in sorted(w):
        if all(w.get(base + i) == c for i, c in enumerate(pat)):
            return (CONST_BASE + (base - CONST_ORIGIN)) & 0xFFFF
    raise AssertionError('%r is not contiguous in the cave' % text)


print('probe156: the re-arm')

print('1. the ARM: gate ONCE, then the build')
vm, inv, names, recs, spoken = run_arm()
assert names == ['KalimbaSendMessage'] + BUILD, names
assert spoken == [], 'the healthy arm must be SILENT, spoke %s' % spoken
print('  %s' % ' -> '.join(names))

print('2. the HANDLER: the SAME build, and NO re-gate')
n1, r1, s1 = run_tick(vm, inv)
assert n1 == BUILD, n1
assert 'KalimbaSendMessage' not in n1, (
    'the handler must NOT re-run the 0x1072 gate: its handler purges the tone '
    'cbuffer (codec_tones.asm:507-513), which is the probe105/106 bug')
assert s1 == [], 'a healthy tick must be SILENT, spoke %s' % s1
print('  %s' % ' -> '.join(n1))
print('  the gate is absent from the tick, as it must be')

print('3. the build is STATE-FREE: three ticks, identical')
n2, _, _ = run_tick(vm, inv)
n3, _, _ = run_tick(vm, inv)
assert n1 == n2 == n3, (n1, n2, n3)
print('  tick 1 == tick 2 == tick 3 (%d traps each)' % len(n1))

print('4. StreamDisconnect frees the sink BEFORE the new transform')
order = [x[0] for x in r1]
assert order.index('StreamDisconnect') < order.index('TransformAdpcmDecode'), order
sd = [x for x in r1 if x[0] == 'StreamDisconnect'][0]
al, ah = sd[1] & 0xFFFF, (sd[1] >> 16) & 0xFFFF
assert al == 0, 'StreamDisconnect source arg = %#06x, expected 0' % al
assert ah == KSINK_H, ('StreamDisconnect sink arg = %#06x, expected the port '
                       'sink %#06x' % (ah, KSINK_H))
print('  StreamDisconnect(source=0, sink=%#06x), before TransformAdpcmDecode' % ah)

print('5. the re-arm: the FLASHED TaskData and a 5000 ms delay')
ml = [x for x in r1 if x[0] == 'MessageSendLater'][0]
al, ah, a2 = ml[1] & 0xFFFF, (ml[1] >> 16) & 0xFFFF, ml[2]
msg, dhi = (a2 >> 16) & 0xFFFF, a2 & 0xFFFF
# message-task-abi.md section 1: message -> @(0,Y), delay HIGH -> @(1,Y), delay
# LOW -> @(2,Y). xapemu's trap record captures only slots 0 and 1, and RETICK's
# own `enterl -8` moves Y, so the low half is not readable at a fixed offset --
# assert the CONSTANT statically instead: the emitted `ld AL,#5000` must be
# immediately followed by `st AL,@(2,Y)`.
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import caveasm as _ca                                            # noqa: E402
_want = list(_ca.imm_words(DELAY_MS, 0x14)) + [0x0227]
_w = {int(k, 16): v & 0xFFFF for k, v in words.items()}
_hit = [a for a in sorted(_w)
        if all(_w.get(a + i) == v for i, v in enumerate(_want))]
assert _hit, ('the cave does not contain `ld AL,#%d` followed by st AL,@(2,Y) '
              '-- the re-arm delay is not what this probe claims' % DELAY_MS)
assert al == TASK_ADDR, 'task = %#06x, expected the flashed TaskData %#06x' % (al, TASK_ADDR)
assert ah == 0, ('MessageId (AH) = %#06x, expected an explicit 0 -- a stale '
                 'register left by TransformStart would mean the cave passes '
                 'whatever happened to be in AH' % ah)
assert msg == 0, 'message word = %#06x, expected 0' % msg
assert dhi == 0, 'delay HIGH = %#06x, expected 0' % dhi
print('  MessageSendLater(task=%#06x, id=%#06x, msg=%d, delayhi=%d), and '
      '`ld AL,#%d ; st AL,@(2,Y)` at %#x' % (al, ah, msg, dhi, DELAY_MS, _hit[0]))

print('6. every failure path speaks, and NONE re-arms')
for fail, want in (('StreamKalimbaSink', 0x10), ('FileFind', 0x22),
                   ('StreamFileSource', 0x24), ('TransformAdpcmDecode', 0x25),
                   ('TransformStart', 0x25)):
    _, _, n, r, sp = run_arm(fail=(fail,))
    assert sp == [want], ('--fail %s: expected %#04x, spoke %s'
                          % (fail, want, ['%#04x' % x for x in sp]))
    assert 'MessageSendLater' not in n, (
        '--fail %s RE-ARMED after failing: %s' % (fail, n))
    print('  --fail %-22s -> %s, no re-arm' % (fail, IDS[want]))
_, _, n, _, sp = run_arm(fail=('KalimbaSendMessage',))
assert sp == [] and n == ['KalimbaSendMessage'], (n, sp)
print('  --fail %-22s -> SILENT boot-safe bail, no build at all'
      % 'KalimbaSendMessage')

print('7. both pointers still pinned to contiguous strings')
want_dir, want_file = strdata(DIRNAME), strdata(FILENAME)
ffs = [x for x in r1 if x[0] == 'FileFind']
assert len(ffs) == 2, len(ffs)
(_, a1, s1_), (_, a2_, s2_) = ffs
ah1, len1 = (a1 >> 16) & 0xFFFF, (s1_ >> 16) & 0xFFFF
ah2, len2 = (a2_ >> 16) & 0xFFFF, (s2_ >> 16) & 0xFFFF
assert (a1 & 0xFFFF) == 1, 'call 1 parent must be FILE_ROOT'
assert ah1 == want_dir and len1 == len(DIRNAME), (hex(ah1), len1)
assert ah2 == want_file and len2 == len(FILENAME), (hex(ah2), len2)
assert ah1 != ah2
print('  call 1 ptr=%#06x %r len=%d ; call 2 ptr=%#06x %r len=%d'
      % (ah1, DIRNAME, len1, ah2, FILENAME, len2))

print('\nALL SIM CHECKS PASS (probe156: a state-free build shared by the arm and '
      'the handler, the sink freed before each rebuild, and a 5000 ms re-arm '
      'only ever on success)')
