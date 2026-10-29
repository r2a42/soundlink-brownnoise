#!/usr/bin/env python3
"""verify_probe148: the completion-driven refill loop, end to end, in cavesim.

The architecture under test:
  ARM: gate, malloc(113), TaskData{3,handler} in buf[0..1], seed/flag/ksink,
       MessageSinkTask(buf), watchdog MessageSendLater(buf,0x41,0,127), REFILL.
  0x8026 completion -> flag set -> REFILL (no teardown, no timer).
  0x41 watchdog -> flag set? exit : speak 0x1F.

cavesim's stubs return 0 for MessageSinkTask (falsy!) -- the ARM has no success
check by design, so the arm run proceeds regardless; the completion path is
driven MANUALLY here (the sim has no message queue: we enter the handler the
way the VM would, Task in AL = buf, id in AH).
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'xapvm'))
import cavesim                                                  # noqa: E402

SEED = 0x7F
NBYTES, NBLOCKS = 108, 34
BUF = cavesim.HEAP
CAVE = 0x3E21D
WORDS = json.load(open(os.path.join(ROOT, 'build/hook/probe148_words.json')))


def reference_from(seed, blocks):
    x = seed & 0xFFFF
    out = [0x0080, 0x00FF, 0x00FF, 0x00FF, 0x00FF, 0x00F7]
    for _ in range(blocks):
        x = (x >> 1) ^ ((0 - (x & 1)) & 0xB400)
        r = x & 0x88
        t = r >> 4
        out.append((0x30 ^ r) & 0xFF)
        out.append((0xCB ^ (r & 0x80) ^ t) & 0xFF)
        out.append((0x84 ^ ((r << 4) & 0xFFFF) ^ t) & 0xFF)
    return out, x


def buf_bytes(vm):
    return [vm.rd(BUF + 5 + i) & 0xFF for i in range(NBYTES)]


def check_fill(vm, expect_bytes, expect_x, tag):
    got = buf_bytes(vm)
    assert got == expect_bytes, (
        '%s: bytes differ at %s' %
        (tag, [i for i in range(NBYTES) if got[i] != expect_bytes[i]][:4]))
    assert vm.rd(BUF + 2) == expect_x, (
        '%s: buf[2] = %#06x, reference x = %#06x' % (tag, vm.rd(BUF + 2), expect_x))
    print('  %s: %d bytes BYTE-EXACT; x -> %#06x' % (tag, NBYTES, expect_x))


HANDLER = None
stubs_inv = {}


def run_arm(fail=()):
    vm, state, stubs, trapnums = cavesim.build(
        os.path.join(ROOT, 'build/hook/probe148_words.json'), fail=set(fail))
    stubs_inv.update({v: k for k, v in trapnums.items()})
    vm.Y = cavesim.FRAME
    why, pc = vm.run(CAVE)
    return vm, why


def run_handler(vm, ah):
    vm.traps = []
    vm.AH = ah
    vm.AL = BUF                         # the Task pointer IS buf
    vm.Y = cavesim.FRAME
    why, pc = vm.run(HANDLER)
    assert why == 'leavel', (hex(ah), why, pc)


print('1. ARM')
vm, why = run_arm()
assert why == 'leavel', why
names = [stubs_inv.get(t, 'trap_%02x' % t) for t, _, _ in vm.traps]
assert names == ['KalimbaSendMessage', 'malloc', 'StreamKalimbaSink',
                 'MessageSinkTask', 'MessageSendLater', 'StreamRegionSource',
                 'TransformAdpcmDecode', 'TransformStart'], names
print('  traps: %s' % ' '.join(names))
assert vm.rd(BUF) == 3, 'buf[0] should hold hi(HANDLER)=3'
assert vm.rd(BUF + 4) == 0x55C0, 'buf[4] should hold ksink'
assert vm.rd(BUF + 3) == 0, 'buf[3] flag starts 0'
print('  TaskData buf[0..1] = %04x %04x; flag=0; ksink stored' %
      (vm.rd(BUF), vm.rd(BUF + 1)))
ref, x = reference_from(SEED, NBLOCKS)
check_fill(vm, ref, x, 'fill#1')

HANDLER = 0x30000 | vm.rd(BUF + 1)      # the TaskData the arm built, read back
assert vm.rd(BUF) == 3 and (HANDLER >> 16) == 0x3, (hex(HANDLER),)
print('  handler at %#x (read from the runtime TaskData)' % HANDLER)

print('2. THREE 0x8026 COMPLETIONS (no teardown, no timer, walk continues)')
TICK = ['StreamRegionSource', 'TransformAdpcmDecode', 'TransformStart']
for k in range(2, 5):
    run_handler(vm, 0x8026)
    names = [stubs_inv.get(t, 'trap_%02x' % t) for t, _, _ in vm.traps]
    assert names == TICK, (k, names)
    ref, x = reference_from(x, NBLOCKS)
    check_fill(vm, ref, x, 'fill#%d' % k)
    assert vm.rd(BUF + 3) != 0, 'flag should be set'
print('  flag stays set; no SourceClose/TransformFromSink/MessageSendLater anywhere')

print('3. WATCHDOG')
run_handler(vm, 0x41)                   # flag set: silent exit
assert not vm.calls_seen, 'watchdog must be silent after completions'
print('  after completions: silent, no traps')
vm, why = run_arm()                     # fresh arm: flag 0
run_handler(vm, 0x41)
spoken = [v & 0xFFFF for a, v in vm.calls_seen if a == cavesim.SPEAK_ADDR]
assert spoken == [0x1F], (hex(vm.calls_seen and vm.calls_seen[0][0] or 0), spoken)
print('  before any completion: speaks 0x1F (muted)')

print('4. FAILURE PATHS (the arm)')
for fail, n_traps, note in [
        ('KalimbaSendMessage', 1, 'gate bails: no DSP'),
        ('malloc', 2, 'pool exhausted'),
        ('StreamKalimbaSink', 3, 'no port-3 sink'),
        ('StreamRegionSource', 6, 'rebuild fails after the watchdog arm'),
        ('TransformAdpcmDecode', 8, 'close the fresh source, no completion'),
        ('TransformStart', 9, 'close the fresh source, no completion')]:
    vm, why = run_arm(fail=(fail,))
    names = [stubs_inv.get(t, 'trap_%02x' % t) for t, _, _ in vm.traps]
    assert why == 'leavel', (fail, why)
    assert len(names) == n_traps, (fail, names)
    assert 'MessageSendLater' in names or n_traps <= 3, (fail, names)
    print('  arm --fail %-22s -> %d traps (%s)' % (fail, n_traps, note))

print('\nALL SIM CHECKS PASS')
