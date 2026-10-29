#!/usr/bin/env python3
"""verify_probe152: the port-sink census, every branch, in cavesim.

probe152 asks whether a Kalimba port sink can be claimed, and writes NOTHING.
The whole probe is its outcome lattice, so this harness drives each of the six
spoken ids plus the silent boot bail by overriding exactly one trap return at a
time, and asserts three things every run:

  * the id spoken is the right one for that trap configuration;
  * SinkFlush is NEVER called -- nothing may ever be committed;
  * no trap after the bail point is called, i.e. the probe really does stop.

The claim lattice is the part worth being pedantic about. sink.h:32 gives the
offset on success and 0xFFFF on refusal, and sink.h:44 gives ZERO on a connected
sink -- so ZERO IS A REFUSAL, not "offset 0". cavesim's DEFAULT_RETURNS models
SinkClaim as 0 (probe140's partition-sink assumption, where offset 0 was the
expected success), which under probe152's correct reading is the CONNECTED
sentinel. That disagreement is the point of the explicit cases below.
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'xapvm'))
import cavesim                                                  # noqa: E402

WORDS = os.path.join(ROOT, 'build/hook/probe152_words.json')
CAVE = 0x3E21D

IDS = {0x27: 'battery 10% -- StreamKalimbaSink returned 0',
       0x28: 'battery 20% -- SinkSlack unusable (0xFFFF or < 4)',
       0x29: 'battery 30% -- SinkClaim returned 0: the CONNECTED sentinel',
       0x2A: 'battery 40% -- SinkClaim returned 0xFFFF: operator sink, DEAD',
       0x2E: 'battery 80% -- claim OK but SinkMap returned 0',
       0x2F: 'battery 90% -- FULL SUCCESS: the direct port write is available'}


def run(returns=None, fail=()):
    """One census pass. `returns` overrides individual trap returns as AL."""
    vm, state, stubs, trapnums = cavesim.build(WORDS, fail=set(fail))
    for name, al in (returns or {}).items():
        vm.STUB_RET[trapnums[name]] = (0, al)
    vm.Y = cavesim.FRAME
    why, pc = vm.run(CAVE)
    assert why == 'leavel', (why, hex(pc))
    names = [stubs.get(t, 'trap_%02x' % t) if isinstance(stubs, dict) else t
             for t, _, _ in vm.traps]
    inv = {v: k for k, v in trapnums.items()}
    names = [inv.get(t, 'trap_%02x' % t) for t, _, _ in vm.traps]
    spoken = [v & 0xFFFF for a, v in vm.calls_seen if a == cavesim.SPEAK_ADDR]
    assert 'SinkFlush' not in names, 'probe152 must NEVER flush: %s' % names
    return spoken, names


def expect(tag, spoken, names, want_id, want_last):
    if want_id is None:
        assert spoken == [], '%s: expected SILENCE, spoke %s' % (tag, spoken)
    else:
        assert spoken == [want_id], (
            '%s: expected %#04x (%s), spoke %s'
            % (tag, want_id, IDS[want_id], ['%#04x' % x for x in spoken]))
    assert names[-1] == want_last, (
        '%s: last trap %s, expected %s (the probe must STOP there)'
        % (tag, names[-1], want_last))
    label = 'SILENT (boot-safe bail)' if want_id is None else IDS[want_id]
    print('  %-34s -> %s' % (tag, label))


print('probe152 census lattice')

# 1. no DSP: the gate refuses and the cave must say NOTHING at all.
s, n = run(fail=('KalimbaSendMessage',))
expect('gate FALSE (power-on, no DSP)', s, n, None, 'KalimbaSendMessage')

# 2. a DSP is up but there is no port-3 sink.
s, n = run(fail=('StreamKalimbaSink',))
expect('StreamKalimbaSink -> 0', s, n, 0x27, 'StreamKalimbaSink')

# 3. slack refuses outright, and slack below the 4 bytes we intend to claim.
s, n = run({'SinkSlack': 0xFFFF})
expect('SinkSlack -> 0xFFFF', s, n, 0x28, 'SinkSlack')
s, n = run({'SinkSlack': 0})
expect('SinkSlack -> 0 (connected)', s, n, 0x28, 'SinkSlack')
s, n = run({'SinkSlack': 3})
expect('SinkSlack -> 3 (below the claim)', s, n, 0x28, 'SinkSlack')
s, n = run({'SinkSlack': 4})
assert n[-1] != 'SinkSlack', 'slack == 4 must PASS the gate, got %s' % n
print('  %-34s -> passes the gate (boundary)' % 'SinkSlack -> 4 (exactly enough)')

# 4. the claim lattice: both refusal sentinels, each with its own id.
s, n = run({'SinkSlack': 0x100, 'SinkClaim': 0xFFFF})
expect('SinkClaim -> 0xFFFF (operator)', s, n, 0x2A, 'SinkClaim')
s, n = run({'SinkSlack': 0x100, 'SinkClaim': 0})
expect('SinkClaim -> 0 (connected)', s, n, 0x29, 'SinkClaim')

# 5. a real offset, then the map.
s, n = run({'SinkSlack': 0x100, 'SinkClaim': 8, 'SinkMap': 0})
expect('claim 8, SinkMap -> 0', s, n, 0x2E, 'SinkMap')
s, n = run({'SinkSlack': 0x100, 'SinkClaim': 8, 'SinkMap': 0x2000})
expect('claim 8, SinkMap -> 0x2000', s, n, 0x2F, 'SinkMap')

# 6. the whole point: no write path exists at all.
_, n = run({'SinkSlack': 0x100, 'SinkClaim': 8, 'SinkMap': 0x2000})
for forbidden in ('SinkFlush', 'malloc', 'StreamRegionSource',
                  'TransformAdpcmDecode', 'TransformStart', 'MessageSendLater'):
    assert forbidden not in n, 'probe152 must not call %s: %s' % (forbidden, n)
print('  %-34s -> no flush, no malloc, no transform, no timer'
      % 'the success path, fully')

print('\nALL SIM CHECKS PASS (probe152: 6 ids + the silent bail, and NOTHING is '
      'ever written or committed)')
