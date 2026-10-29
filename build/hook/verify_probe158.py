#!/usr/bin/env python3
"""verify_probe158: the DSP reload, in cavesim.

probe157 measured the thing that had been setting every death time since
probe104: seven seconds after the press, KalimbaSendMessage(0x1072) returns
FALSE, i.e. THE DSP IS GONE. Entering pairing takes it down, and that happens in
fn_0d500 at 0x00ac2 -- two instructions BEFORE this hook -- so the cave cannot
prevent it. probe158 undoes it instead: on a FALSE gate, reload
sbc_decoder.kap, re-arm, and carry on.

The cases that matter here are the ones no earlier harness could express:

  * a FALSE gate on a tick must trigger a RELOAD -- FileFind then KalimbaLoad --
    and not simply bail;
  * KalimbaLoad must receive the index FileFind returned, with the .kap FileFind
    using the firmware's own pool pointer and a length of 27;
  * after a successful reload the gate must be SENT AGAIN, because the stock
    builder takes StreamKalimbaSink(3) only after its KalimbaLoad (0x22f7e ->
    0x22f8f), so port 3 does not pre-exist the load and the old arming died with
    the old port;
  * reload-impossible and reload-but-will-not-arm must be DIFFERENT ids;
  * and a healthy tick must still never reload.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'xapvm'))
import cavesim                                                  # noqa: E402
import caveasm as ca                                            # noqa: E402

WORDS = os.path.join(ROOT, 'build/hook/probe158_words.json')
CAVE = 0x3E21D
TASK_ADDR, DELAY_MS, KAPLEN = 0xBA3C, 9500, 27
KSINK_H = 0x55C0                     # cavesim's StreamKalimbaSink return
# cavesim overrides FileFind to a 'fake index' of 0x5DF0 (the probe141 entry
# in DEFAULT_RETURNS), so that -- not 1 -- is the index KalimbaLoad must get.
KAPIDX = 0x5DF0

HEALTHY = ['KalimbaSendMessage', 'StreamKalimbaSink', 'StreamDisconnect',
           'FileFind', 'FileFind', 'StreamFileSource', 'TransformAdpcmDecode',
           'TransformStart', 'MessageSendLater']
words = json.load(open(WORDS))
handler = 0x30000 | (words['0x3e21f'] & 0xFFFF)


def mk(gate_seq=None):
    """gate_seq: list of AL values for successive KalimbaSendMessage calls."""
    vm, state, stubs, trapnums = cavesim.build(WORDS)
    inv = {v: k for k, v in trapnums.items()}
    if gate_seq is not None:
        box = {'i': 0}
        def gate(trap, ahal, a2):
            i = box['i']; box['i'] += 1
            return (0, gate_seq[i] if i < len(gate_seq) else gate_seq[-1])
        vm.STUB_RET[trapnums['KalimbaSendMessage']] = gate
    return vm, inv


def arm(vm):
    vm.Y = cavesim.FRAME
    assert vm.run(CAVE)[0] == 'leavel'


def tick(vm, inv):
    vm.traps = []; vm.calls_seen.clear()
    vm.AH = 0; vm.AL = TASK_ADDR; vm.Y = cavesim.FRAME
    why, pc = vm.run(handler)
    assert why == 'leavel', (why, hex(pc))
    names = [inv.get(t, 'trap_%02x' % t) for t, _, _ in vm.traps]
    recs = [(inv.get(t, 'trap_%02x' % t), a, b) for t, a, b in vm.traps]
    spoken = [v & 0xFFFF for a, v in vm.calls_seen if a == cavesim.SPEAK_ADDR]
    return names, recs, spoken


print('probe158: the DSP reload')

print('1. a HEALTHY tick still never reloads')
vm, inv = mk()
arm(vm)
n, r, sp = tick(vm, inv)
assert n == HEALTHY, n
assert 'KalimbaLoad' not in n, 'a healthy tick must not reload: %s' % n
assert sp == [], 'a healthy tick must be silent, spoke %s' % sp
print('  %s' % ' -> '.join(n))

print('2. THE CASE THAT MATTERS: gate FALSE -> reload -> re-arm -> build')
# gate: TRUE at the arm (x2: the ARM's own check and RETICK's), then FALSE on the
# tick (the DSP has gone), then TRUE for the post-reload re-arm.
vm, inv = mk(gate_seq=[1, 1, 0, 1, 1])
arm(vm)
n, r, sp = tick(vm, inv)
assert sp == [], 'a successful reload must stay SILENT, spoke %s' % ['%#04x' % x for x in sp]
assert n == ['KalimbaSendMessage',          # the gate: FALSE, the DSP is gone
             'FileFind', 'KalimbaLoad',     # the reload
             'KalimbaSendMessage',          # re-arm: port 3 is new
             'StreamKalimbaSink', 'StreamDisconnect', 'FileFind', 'FileFind',
             'StreamFileSource', 'TransformAdpcmDecode', 'TransformStart',
             'MessageSendLater'], n
print('  %s' % ' -> '.join(n))
ff = [x for x in r if x[0] == 'FileFind'][0]
al, ah, a2 = ff[1] & 0xFFFF, (ff[1] >> 16) & 0xFFFF, (ff[2] >> 16) & 0xFFFF
assert al == 1, '.kap FileFind parent = %#06x, expected FILE_ROOT' % al
assert a2 == KAPLEN, '.kap FileFind length = %d, expected %d' % (a2, KAPLEN)
assert 0x7400 <= ah <= 0xD39A, '.kap pointer %#06x outside the const window' % ah
kl = [x for x in r if x[0] == 'KalimbaLoad'][0]
assert kl[1] & 0xFFFF == KAPIDX, (
    'KalimbaLoad got %#06x, expected the index FileFind returned (%#06x) -- the '
    'stock site passes it straight through in AL with nothing in between'
    % (kl[1] & 0xFFFF, KAPIDX))
print('  FileFind(FILE_ROOT, ptr=%#06x, len=%d) -> KalimbaLoad(idx=%#06x)'
      % (ah, a2, kl[1] & 0xFFFF))
assert n.index('KalimbaSendMessage', 1) < n.index('StreamKalimbaSink'), (
    'the re-arm must come BEFORE StreamKalimbaSink: port 3 does not pre-exist '
    'the load')
print('  the re-arm precedes StreamKalimbaSink, as the stock order requires')

print('3. reload IMPOSSIBLE -> 0x3E, and it does NOT re-arm')
for fail in ('FileFind', 'KalimbaLoad'):
    vm, state, stubs, tn = cavesim.build(WORDS, fail={fail})
    inv = {v: k for k, v in tn.items()}
    box = {'i': 0}
    seq = [1, 1, 0]
    def gate(trap, ahal, a2, _b=box, _s=seq):
        i = _b['i']; _b['i'] += 1
        return (0, _s[i] if i < len(_s) else 0)
    vm.STUB_RET[tn['KalimbaSendMessage']] = gate
    arm(vm)
    n, r, sp = tick(vm, inv)
    assert sp == [0x3E], ('--fail %s: expected 0x3E "bluetooth off", spoke %s'
                          % (fail, ['%#04x' % x for x in sp]))
    assert 'MessageSendLater' not in n, '--fail %s re-armed: %s' % (fail, n)
    print('  --fail %-12s -> 0x3E "bluetooth off" (gone AND unrecoverable), no re-arm'
          % fail)

print('4. reloaded but the port WILL NOT ARM -> 0x14, a different id')
vm, inv = mk(gate_seq=[1, 1, 0, 0])      # gate fails again after the reload
arm(vm)
n, r, sp = tick(vm, inv)
assert sp == [0x14], ('expected 0x14 "auto off disabled", spoke %s'
                      % ['%#04x' % x for x in sp])
assert 'KalimbaLoad' in n, 'it must have tried the reload first: %s' % n
assert 'StreamKalimbaSink' not in n, 'it must stop before building: %s' % n
assert 'MessageSendLater' not in n, 'it must not re-arm: %s' % n
print('  reload accepted, gate still FALSE -> 0x14, stopped before building')
print('  (0x3E and 0x14 are DIFFERENT sounds for two different failures)')

print('5. the re-arm delay is past the async teardown')
want = list(ca.imm_words(DELAY_MS, 0x14)) + [0x0227]
w = {int(k, 16): v & 0xFFFF for k, v in words.items()}
hit = [a for a in sorted(w) if all(w.get(a + i) == v for i, v in enumerate(want))]
assert hit, 'the cave does not contain `ld AL,#%d ; st AL,@(2,Y)`' % DELAY_MS
print('  `ld AL,#%d ; st AL,@(2,Y)` at %#x -- past the ~7 s chunk AND past '
      'fn_0d500\'s async teardown' % (DELAY_MS, hit[0]))

print('\nALL SIM CHECKS PASS (probe158: a FALSE gate reloads the DSP, re-arms '
      'before taking the port, and the two reload failures speak different ids)')
