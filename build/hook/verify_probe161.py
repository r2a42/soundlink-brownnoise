#!/usr/bin/env python3
"""verify_probe161: answer MUSIC_READY the way the stock handler does.

probe160's press ("noise ~7 s, then ~3 s later 'auto off disabled'") proved the
bare reload clean: our task owned the mailbox, sbc_decoder booted, MUSIC_READY
(0x1000) reached us, the VM survived. probe161 takes the next stock step and
nothing else: on 0x1000 it sends, verbatim from fn_31105 0x3119b-0x311b2,

    KalimbaSendMessage(0x1020 SETPLUGIN, 1, 0, 0, 0)     code 1 = SBC
    KalimbaSendMessage(0x1012 LOADPARAMS, 0x2270, 0, 0, 0)

and leaves the DSP up. When the DSP answers PARAMS_LOADED (0x1015), the handler
powers it off and speaks 0x12 "voice prompts on". Every other DSP message is
ignored SILENTLY (a prompt now would load NowSpeakTTS over a running DSP).

This harness must show:
  * ARM: probe160's first build minus StreamDisconnect; boot gate FALSE = silent;
  * a FALSE tick is exactly gate -> MessageKalimbaTask(ours) -> FileFind ->
    KalimbaLoad, silent, and nothing after;
  * 0x1000 -> exactly the two sends above, in order, with zero stack args, and
    NO power-off, NO speech, NO timer;
  * 0x1015 -> KalimbaPowerOff, then 0x12;
  * 0x8000 / 0x7070 / other MessageIds -> nothing at all;
  * reload refused -> 0x3E and build failures -> 0x25, both WITHOUT a power-off
    (the shared tail must not leak OFFSAY into them).
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'xapvm'))
import cavesim                                                  # noqa: E402
import caveasm as ca                                            # noqa: E402

WORDS = os.path.join(ROOT, 'build/hook/probe161_words.json')
CAVE = 0x3E21D
TASK_ADDR, DELAY_MS, KAPLEN = 0xBA3C, 9500, 27
MSG_FROM_KALIMBA, MSG_FROM_KALIMBA_LONG = 0x8024, 0x802A
KAPIDX = 0x5DF0
MSGBUF = 0x2800

FIRST_BUILD = ['KalimbaSendMessage', 'KalimbaSendMessage', 'StreamKalimbaSink',
               'FileFind', 'FileFind', 'StreamFileSource', 'TransformAdpcmDecode',
               'TransformStart', 'MessageSendLater']
words = json.load(open(WORDS))
handler = 0x30000 | (words['0x3e21f'] & 0xFFFF)


def mk(gate_seq=None, fail=()):
    vm, state, stubs, trapnums = cavesim.build(WORDS, fail=set(fail))
    inv = {v: k for k, v in trapnums.items()}
    if gate_seq is not None:
        box = {'i': 0}
        def gate(trap, ahal, a2):
            i = box['i']; box['i'] += 1
            return (0, gate_seq[i] if i < len(gate_seq) else gate_seq[-1])
        vm.STUB_RET[trapnums['KalimbaSendMessage']] = gate
    return vm, inv


def run_arm(vm, inv):
    vm.traps = []
    if hasattr(vm, 'calls_seen'):
        vm.calls_seen.clear()
    vm.Y = cavesim.FRAME
    assert vm.run(CAVE)[0] == 'leavel'
    return ([inv.get(t, 'trap_%02x' % t) for t, _, _ in vm.traps],
            [v & 0xFFFF for a, v in vm.calls_seen if a == cavesim.SPEAK_ADDR])


def tick(vm, inv, msg_id=0, msg0=None):
    vm.traps = []; vm.calls_seen.clear()
    if msg0 is not None:
        vm.wr(MSGBUF, msg0)
        vm.wr(cavesim.FRAME + 0, MSGBUF)
    vm.AH = msg_id; vm.AL = TASK_ADDR; vm.Y = cavesim.FRAME
    why, pc = vm.run(handler)
    assert why == 'leavel', (why, hex(pc))
    assert vm.Y == cavesim.FRAME, 'frame not balanced: Y=%#x' % vm.Y
    names = [inv.get(t, 'trap_%02x' % t) for t, _, _ in vm.traps]
    recs = [(inv.get(t, 'trap_%02x' % t), a, b) for t, a, b in vm.traps]
    spoken = [v & 0xFFFF for a, v in vm.calls_seen if a == cavesim.SPEAK_ADDR]
    return names, recs, spoken


print('probe161: answer MUSIC_READY with SETPLUGIN + LOADPARAMS')

print('1. the ARM')
vm, inv = mk()
n, sp = run_arm(vm, inv)
assert n == FIRST_BUILD and sp == [], (n, sp)
print('  %s' % ' -> '.join(n))
vm, inv = mk(fail=['KalimbaSendMessage'])
n, sp = run_arm(vm, inv)
assert n == ['KalimbaSendMessage'] and sp == [], (n, sp)
print('  boot (gate FALSE): KalimbaSendMessage only, silent bail')
for fail in ('StreamKalimbaSink', 'FileFind', 'StreamFileSource', 'TransformAdpcmDecode'):
    vm, inv = mk(gate_seq=[1], fail=[fail])
    n, sp = run_arm(vm, inv)
    assert sp == [0x25], (fail, sp)
    assert 'KalimbaPowerOff' not in n and 'MessageSendLater' not in n, (fail, n)
print('  every first-build failure -> 0x25, NO power-off, no re-arm')

print('2. a FALSE tick: own mailbox -> FileFind -> KalimbaLoad -> STOP')
vm, inv = mk(gate_seq=[1, 1, 0])
run_arm(vm, inv)
n, r, sp = tick(vm, inv)
assert n == ['KalimbaSendMessage', 'MessageKalimbaTask', 'FileFind', 'KalimbaLoad'], n
assert sp == [], sp
mk_ = [x for x in r if x[0] == 'MessageKalimbaTask'][0]
assert mk_[1] & 0xFFFF == TASK_ADDR
ff = [x for x in r if x[0] == 'FileFind'][0]
assert ff[1] & 0xFFFF == 1 and (ff[2] >> 16) & 0xFFFF == KAPLEN
assert 0x7400 <= (ff[1] >> 16) & 0xFFFF <= 0xD39A
kl = [x for x in r if x[0] == 'KalimbaLoad'][0]
assert kl[1] & 0xFFFF == KAPIDX
print('  %s, silent' % ' -> '.join(n))
for fail in ('FileFind', 'KalimbaLoad'):
    vm, inv = mk(gate_seq=[1, 1, 0], fail=[fail])
    run_arm(vm, inv)
    n, r, sp = tick(vm, inv)
    assert sp == [0x3E] and 'KalimbaPowerOff' not in n and 'MessageSendLater' not in n, (fail, n, sp)
    print('  --fail %-12s -> 0x3E, NO power-off, no re-arm' % fail)

print('3. MUSIC_READY (0x1000) -> SETPLUGIN(1) then LOADPARAMS(0x2270), and nothing else')
vm, inv = mk()
run_arm(vm, inv)
n, r, sp = tick(vm, inv, msg_id=MSG_FROM_KALIMBA, msg0=0x1000)
assert n == ['KalimbaSendMessage', 'KalimbaSendMessage'], n
assert sp == [], 'no speech while the DSP is up: %s' % sp
(_, a1, b1), (_, a2, b2) = r
assert a1 & 0xFFFF == 0x1020 and (a1 >> 16) & 0xFFFF == 1, hex(a1)
assert a2 & 0xFFFF == 0x1012 and (a2 >> 16) & 0xFFFF == 0x2270, hex(a2)
assert b1 == 0 and b2 == 0, 'stack args must be zero: %#x %#x' % (b1, b2)
print('  KalimbaSendMessage(0x1020, 1, 0,0,0) -> KalimbaSendMessage(0x1012, 0x2270, 0,0,0)')
print('  no power-off, no speech, no timer: the DSP stays up, waiting for GO')

print('4. PARAMS_LOADED (0x1015) -> KalimbaPowerOff -> 0x12 "voice prompts on"')
vm, inv = mk()
run_arm(vm, inv)
n, r, sp = tick(vm, inv, msg_id=MSG_FROM_KALIMBA, msg0=0x1015)
assert n == ['KalimbaPowerOff'] and sp == [0x12], (n, sp)
print('  KalimbaPowerOff -> 0x12')

print('5. everything else is ignored silently')
for msg0 in (0x8000, 0x7070, 0x1080, 0x0000):
    vm, inv = mk(); run_arm(vm, inv)
    n, r, sp = tick(vm, inv, msg_id=MSG_FROM_KALIMBA, msg0=msg0)
    assert n == [] and sp == [], (hex(msg0), n, sp)
    print('  MESSAGE_FROM_KALIMBA msg[0]=%#06x -> nothing' % msg0)
for mid in (MSG_FROM_KALIMBA_LONG, 0x8022, 0x0001, 0x7016):
    vm, inv = mk(); run_arm(vm, inv)
    n, r, sp = tick(vm, inv, msg_id=mid, msg0=0x1015)
    assert n == [] and sp == [], (hex(mid), n, sp)
    print('  MessageId %#06x -> nothing' % mid)

print('6. constants')
want = list(ca.imm_words(DELAY_MS, 0x14)) + [0x0227]
w = {int(k, 16): v & 0xFFFF for k, v in words.items()}
hit = [a for a in sorted(w) if all(w.get(a + i) == v for i, v in enumerate(want))]
assert hit, DELAY_MS
assert w[handler & 0x3FFFF] == 0xF80B, 'handler must open enterl -8'
print('  delay %d ms at %#x; handler at %#x opens enterl -8, Message at @(8,Y)'
      % (DELAY_MS, hit[0], handler & 0x3FFFF))

print('\nALL SIM CHECKS PASS (probe161: MUSIC_READY is answered with the stock '
      'SETPLUGIN + LOADPARAMS, PARAMS_LOADED powers off and speaks 0x12, '
      'nothing else runs anything)')
