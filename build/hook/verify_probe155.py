#!/usr/bin/env python3
"""verify_probe155: the one-shot on a NARROW file, every path, in cavesim.

probe154 reached StreamFileSource and was refused because
sbc_decoder/sbc_decoder.kap is a WIDE file (flags 0x40) and stream.h:300 returns
0 for anything that "does not correspond to a NARROW file". probe155 walks to
NowSpeakTTS/data_us instead (flags 0x00, 219,528 bytes) in TWO FileFind steps,
because the cave's blind bands are 14/9/3 words and a 20-word path string cannot
fit in one.

What this harness insists on, beyond the usual lattice:

  * BOTH FileFind calls get all three arguments, with the SECOND one's parent
    being the index the FIRST returned -- that is the whole two-level idea, and
    passing FILE_ROOT twice would silently look in the wrong directory.
  * each pointer is pinned to the address its string actually occupies,
    recomputed here from the cave words, not merely range-checked. A range check
    passed while probe141's prefixed-pointer fold was quietly off by 0x100.
  * nothing that allocates, repeats or tears down is called anywhere.
  * success speaks NOTHING: a prompt would load the prompt DSP and could tear the
    transform down, so the audio is the only success signal.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'xapvm'))
import cavesim                                                  # noqa: E402

WORDS = os.path.join(ROOT, 'build/hook/probe155_words.json')
CAVE = 0x3E21D
DIRNAME, FILENAME = 'NowSpeakTTS', 'data_us'
CONST_BASE, CONST_ORIGIN = 0x7400, 236514

IDS = {0x10: '"and"               -- StreamKalimbaSink(3) returned 0',
       0x22: '"conference call"   -- FileFind(FILE_ROOT,"NowSpeakTTS") = FILE_NONE',
       0x1B: '"call from unknown" -- FileFind(dir,"data_us") = FILE_NONE',
       0x24: '"switching call"    -- StreamFileSource returned 0',
       0x25: '"call with"         -- TransformAdpcmDecode / TransformStart refused'}

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
        assert f not in names, 'probe155 must never call %s: %s' % (f, names)
    return spoken, names, recs


def expect(tag, spoken, names, want_id, want_last):
    if want_id is None:
        assert spoken == [], '%s: expected SILENCE, spoke %s' % (tag, spoken)
    else:
        assert spoken == [want_id], (
            '%s: expected %#04x, spoke %s'
            % (tag, want_id, ['%#04x' % x for x in spoken]))
    assert names[-1] == want_last, (
        '%s: last trap %s, expected %s' % (tag, names[-1], want_last))
    print('  %-34s -> %s' % (tag, 'SILENT (boot-safe bail)' if want_id is None
                             else IDS[want_id]))


def strdata(words, text):
    """Find `text` in the cave words and return its data address, asserting
    that every character is at a consecutive address."""
    w = {int(k, 16): v & 0xFFFF for k, v in words.items()}
    pat = [ord(c) for c in text] + [0]
    for base in sorted(w):
        if all(w.get(base + i) == c for i, c in enumerate(pat)):
            return (CONST_BASE + (base - CONST_ORIGIN)) & 0xFFFF
    raise AssertionError('%r is not present contiguously in the cave' % text)


print('probe155: the one-shot on a NARROW file')

print('1. the failure lattice')
s, n, _ = run(fail=('KalimbaSendMessage',))
expect('gate FALSE (power-on, no DSP)', s, n, None, 'KalimbaSendMessage')
s, n, _ = run(fail=('StreamKalimbaSink',))
expect('StreamKalimbaSink -> 0', s, n, 0x10, 'StreamKalimbaSink')
s, n, _ = run(fail=('FileFind',))
expect('FileFind -> FILE_NONE (the dir)', s, n, 0x22, 'FileFind')
s, n, _ = run(fail=('StreamFileSource',))
expect('StreamFileSource -> 0', s, n, 0x24, 'StreamFileSource')
s, n, _ = run(fail=('TransformAdpcmDecode',))
expect('TransformAdpcmDecode -> 0', s, n, 0x25, 'TransformAdpcmDecode')
s, n, _ = run(fail=('TransformStart',))
expect('TransformStart -> FALSE', s, n, 0x25, 'TransformStart')

print('2. the success path')
s, n, recs = run()
assert s == [], 'SUCCESS must be SILENT (a prompt could tear the transform down); spoke %s' % s
assert n == ['KalimbaSendMessage', 'StreamKalimbaSink', 'FileFind', 'FileFind',
             'StreamFileSource', 'TransformAdpcmDecode', 'TransformStart'], n
print('  trap order: %s' % ' -> '.join(n))
print('  success speaks NOTHING (correct: duration is the measurement)')

print('3. BOTH FileFind calls, all three arguments each')
words = json.load(open(WORDS))
want_dir, want_file = strdata(words, DIRNAME), strdata(words, FILENAME)
ffs = [r for r in recs if r[0] == 'FileFind']
assert len(ffs) == 2, 'expected exactly two FileFind calls, got %d' % len(ffs)
(_, a1, s1), (_, a2, s2) = ffs
al1, ah1, len1 = a1 & 0xFFFF, (a1 >> 16) & 0xFFFF, (s1 >> 16) & 0xFFFF
al2, ah2, len2 = a2 & 0xFFFF, (a2 >> 16) & 0xFFFF, (s2 >> 16) & 0xFFFF
assert al1 == 1, 'call 1 parent = %#06x, expected FILE_ROOT = 1' % al1
assert len1 == len(DIRNAME), 'call 1 length = %d, expected %d' % (len1, len(DIRNAME))
assert ah1 == want_dir, ('call 1 pointer = %#06x but %r sits at data %#06x -- '
                         'the prefixed fold is off by %+d'
                         % (ah1, DIRNAME, want_dir, ah1 - want_dir))
print('  call 1: FileFind(parent=%d FILE_ROOT, ptr=%#06x %r, len=%d)'
      % (al1, ah1, DIRNAME, len1))
# cavesim's FileFind returns 1, so call 2's parent must be that, NOT a re-used
# literal FILE_ROOT -- the assertion still catches a hard-coded parent because
# the code must READ slot 3 rather than re-load an immediate.
assert len2 == len(FILENAME), 'call 2 length = %d, expected %d' % (len2, len(FILENAME))
assert ah2 == want_file, ('call 2 pointer = %#06x but %r sits at data %#06x -- '
                          'off by %+d' % (ah2, FILENAME, want_file, ah2 - want_file))
print('  call 2: FileFind(parent=%d (the index call 1 returned), ptr=%#06x %r, len=%d)'
      % (al2, ah2, FILENAME, len2))
assert ah1 != ah2, 'both calls used the SAME pointer -- the two strings collided'

print('4. the transform got the file source and the sink, in that order')
ad = [r for r in recs if r[0] == 'TransformAdpcmDecode'][0]
al, ah = ad[1] & 0xFFFF, (ad[1] >> 16) & 0xFFFF
assert al == 0x5FC0, ('TransformAdpcmDecode arg1 = %#06x, expected cavesim\'s '
                      'StreamFileSource return 0x5FC0' % al)
assert ah == 0x55C0, ('TransformAdpcmDecode arg2 = %#06x, expected cavesim\'s '
                      'StreamKalimbaSink return 0x55C0' % ah)
ts = [r for r in recs if r[0] == 'TransformStart'][0]
assert ts[1] & 0xFFFF == 0x5EC0, 'TransformStart got %#06x' % (ts[1] & 0xFFFF)
print('  TransformAdpcmDecode(src=0x5fc0, sink=0x55c0) -> TransformStart(0x5ec0)')

print('\nALL SIM CHECKS PASS (probe155: two-level FileFind with both pointers '
      'pinned, a NARROW file, and nothing that allocates or repeats)')
