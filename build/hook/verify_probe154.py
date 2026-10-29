#!/usr/bin/env python3
"""verify_probe154: the one-shot long play, every path, in cavesim.

probe154 has no timer, no teardown and no malloc: one file source, one
transform, and the port pulls until the data runs out. So the things worth
asserting are (a) that the chain is built in the right order with the right
arguments, (b) that NOTHING repeating or allocating is present, and (c) that
each refusal speaks its own id and stops.

The argument check on FileFind matters most. It takes THREE arguments --
index, pointer, length in words (probe144's form) -- and probe141 passed only
two, which is one reason its FileFind was never shown to work. Here the harness
reads the trap's recorded AL, AH and @(0,Y) and insists on 1, the patched
string address, and 27.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'xapvm'))
import cavesim                                                  # noqa: E402

WORDS = os.path.join(ROOT, 'build/hook/probe154_words.json')
CAVE = 0x3E21D
PATHLEN = 27

IDS = {0x10: '"and"        -- StreamKalimbaSink(3) returned 0',
       0x16: '"english"    -- FileFind found nothing',
       0x26: '"ended"      -- StreamFileSource returned 0',
       0x1E: '"call ignored" -- TransformAdpcmDecode returned 0',
       0x18: '"to select a different language..." -- TransformStart FALSE'}

# nothing in this probe may allocate, repeat, or tear anything down
FORBIDDEN = ('malloc', 'MessageSendLater', 'MessageSinkTask', 'SourceClose',
             'TransformStop', 'TransformDisconnect', 'TransformFromSink',
             'StreamDisconnect', 'StreamRegionSource', 'SinkClaim', 'SinkFlush',
             'StreamPartitionOverwriteSink')


def run(fail=(), returns=None):
    vm, state, stubs, trapnums = cavesim.build(WORDS, fail=set(fail))
    for name, al in (returns or {}).items():
        vm.STUB_RET[trapnums[name]] = (0, al)
    vm.Y = cavesim.FRAME
    why, pc = vm.run(CAVE)
    assert why == 'leavel', (why, hex(pc))
    inv = {v: k for k, v in trapnums.items()}
    names = [inv.get(t, 'trap_%02x' % t) for t, _, _ in vm.traps]
    recs = [(inv.get(t, 'trap_%02x' % t), ahal, a2) for t, ahal, a2 in vm.traps]
    spoken = [v & 0xFFFF for a, v in vm.calls_seen if a == cavesim.SPEAK_ADDR]
    for f in FORBIDDEN:
        assert f not in names, 'probe154 must never call %s: %s' % (f, names)
    return spoken, names, recs


def expect(tag, spoken, names, want_id, want_last):
    if want_id is None:
        assert spoken == [], '%s: expected SILENCE, spoke %s' % (tag, spoken)
    else:
        assert spoken == [want_id], (
            '%s: expected %#04x, spoke %s' % (tag, want_id,
                                              ['%#04x' % x for x in spoken]))
    assert names[-1] == want_last, (
        '%s: last trap %s, expected %s' % (tag, names[-1], want_last))
    print('  %-36s -> %s' % (tag, 'SILENT (boot-safe bail)' if want_id is None
                             else IDS[want_id]))


print('probe154: the one-shot long play')

print('1. the failure lattice')
s, n, _ = run(fail=('KalimbaSendMessage',))
expect('gate FALSE (power-on, no DSP)', s, n, None, 'KalimbaSendMessage')
s, n, _ = run(fail=('StreamKalimbaSink',))
expect('StreamKalimbaSink -> 0', s, n, 0x10, 'StreamKalimbaSink')
s, n, _ = run(fail=('FileFind',))
expect('FileFind -> 0 (FILE_NONE)', s, n, 0x16, 'FileFind')
s, n, _ = run(fail=('StreamFileSource',))
expect('StreamFileSource -> 0', s, n, 0x26, 'StreamFileSource')
s, n, _ = run(fail=('TransformAdpcmDecode',))
expect('TransformAdpcmDecode -> 0', s, n, 0x1E, 'TransformAdpcmDecode')
s, n, _ = run(fail=('TransformStart',))
expect('TransformStart -> FALSE', s, n, 0x18, 'TransformStart')

print('2. the success path')
s, n, recs = run()
assert s == [], 'SUCCESS must be SILENT -- the audio is the signal, and a prompt here could tear the transform down. Spoke %s' % s
assert n == ['KalimbaSendMessage', 'StreamKalimbaSink', 'FileFind',
             'StreamFileSource', 'TransformAdpcmDecode', 'TransformStart'], n
print('  trap order: %s' % ' -> '.join(n))
print('  success speaks NOTHING (correct: duration is the measurement)')

print('3. FileFind got all THREE arguments')
ff = [r for r in recs if r[0] == 'FileFind'][0]
_, ahal, a2 = ff
al, ah, s0 = ahal & 0xFFFF, (ahal >> 16) & 0xFFFF, (a2 >> 16) & 0xFFFF
strdata = json.load(open(os.path.join(ROOT, 'build/hook/probe154_words.json')))
assert al == 1, 'FileFind arg1 (index) = %#06x, expected 1 = FILE_ROOT' % al
assert s0 == PATHLEN, (
    'FileFind arg3 (@(0,Y), length in WORDS) = %d, expected %d -- probe141 '
    'omitted this argument entirely' % (s0, PATHLEN))
assert 0x7400 <= ah <= 0xD39A, (
    'FileFind arg2 (pointer) = %#06x, which is outside the const window '
    '0x7400..0xD39A, so the patched string address is wrong' % ah)
# Pin it EXACTLY. A window check alone passed while the prefixed-immediate fold
# was silently delivering a pointer 0x100 too low (the probe141 bug probe154
# found), so recompute the intended address independently: locate the path in
# vm.app's OWN const pool, exactly as the assembler does.
sys.path.insert(0, os.path.join(ROOT, 'tools', 'xapvm'))
import xapvm                                                     # noqa: E402
_w = xapvm.load_words(os.path.join(ROOT,
        'firmware/bose/extracted/internal_fs/vm.app'))
_code = _w[0x18:]
_pat = [ord(c) for c in 'sbc_decoder/sbc_decoder.kap']
_hits = [i for i in range(len(_code) - len(_pat))
         if _code[i] == _pat[0] and list(_code[i:i + len(_pat)]) == _pat]
assert _hits, 'the path is not in the const pool'
_want = (0x7400 + (_hits[0] - 236514)) & 0xFFFF
assert ah == _want, (
    'FileFind pointer = %#06x but the pool string sits at data %#06x -- the '
    'prefixed ld AH fold is wrong by %+d' % (ah, _want, ah - _want))
print('  pointer pinned to the FIRMWARE pool copy at data %#06x (not a carried '
      'string: a 28-word string gets SPLIT across blind bands)' % _want)
print('  FileFind(index=%d, ptr=%#06x in the const window, len=%d words)'
      % (al, ah, s0))

print('4. the transform got the source and the sink, in that order')
ad = [r for r in recs if r[0] == 'TransformAdpcmDecode'][0]
al, ah = ad[1] & 0xFFFF, (ad[1] >> 16) & 0xFFFF
assert al == 0x5FC0, ('TransformAdpcmDecode arg1 = %#06x, expected cavesim\'s '
                      'StreamFileSource return 0x5FC0 (cavesim defines it twice; the later probe141 override wins)' % al)
assert ah == 0x55C0, ('TransformAdpcmDecode arg2 = %#06x, expected cavesim\'s '
                      'StreamKalimbaSink return 0x55C0' % ah)
ts = [r for r in recs if r[0] == 'TransformStart'][0]
assert ts[1] & 0xFFFF == 0x5EC0, (
    'TransformStart got %#06x, expected the transform 0x5EC0' % (ts[1] & 0xFFFF))
print('  TransformAdpcmDecode(src=%#06x, sink=%#06x) -> TransformStart(%#06x)'
      % (0x5FC0, 0x55C0, 0x5EC0))

print('\nALL SIM CHECKS PASS (probe154: one source, one transform, nothing that '
      'allocates or repeats, and FileFind gets all three arguments)')
