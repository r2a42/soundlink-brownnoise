#!/usr/bin/env python3
"""verify_probe160: the BARE reload, with the cave owning the Kalimba mailbox.

probe158 wedged the VM on its first reload tick. The disassembly (2026-10-08)
says the stock handler cannot be the mechanism: the A2DP teardown fn_31734
registers a NULL Kalimba task (0x317dc-0x317dd) and frees its instance, so the
reloaded DSP's first message went to nobody. What is left is everything
probe158 did AFTER KalimbaLoad in that same tick -- 0x1072, StreamKalimbaSink,
the transform, a possible SPEAK -- or the bare load itself on top of the
previous chunk's stale port-3 objects.

probe160 bisects that: on a FALSE gate it does MessageKalimbaTask(ours),
FileFind, KalimbaLoad -- and STOPS. The DSP's own unsolicited MUSIC_READY
(0x1000, sbc_decoder PM 0x24d) is the observation: it arrives in the handler
as MESSAGE_FROM_KALIMBA, which powers the DSP off and speaks 0x14.

This harness must show:

  * a FALSE tick is EXACTLY gate -> MessageKalimbaTask(ours) -> FileFind ->
    KalimbaLoad, silent, with no re-arm, no re-gate, no sink, no transform;
  * FileFind / KalimbaLoad refused -> 0x3E, no re-arm;
  * MESSAGE_FROM_KALIMBA with msg[0] == 0x1000 -> KalimbaPowerOff, then 0x14;
    with any other msg[0] (0x8000, the DSP's second boot message, included)
    -> 0x10 (a different id) and NO power-off -- probe159's second power-off
    on the 0x8000 is exactly the defect that withdrew it;
  * every other MessageId (0x802A, 0x8022, 1) runs NOTHING;
  * the healthy tick (id 0) is probe157/158's build, unchanged, and never
    takes the mailbox; its failures all speak the single id 0x25.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'xapvm'))
import cavesim                                                  # noqa: E402
import caveasm as ca                                            # noqa: E402

WORDS = os.path.join(ROOT, 'build/hook/probe160_words.json')
CAVE = 0x3E21D
TASK_ADDR, DELAY_MS, KAPLEN = 0xBA3C, 9500, 27
MSG_FROM_KALIMBA, MSG_FROM_KALIMBA_LONG = 0x8024, 0x802A   # 0x8000 + 36 / + 42
MUSIC_READY = 0x1000
KAPIDX = 0x5DF0                      # cavesim's fake FileFind index
MSGBUF = 0x2800                      # where the test plants a DSP message

HEALTHY = ['KalimbaSendMessage', 'StreamKalimbaSink', 'StreamDisconnect',
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


def arm(vm):
    vm.Y = cavesim.FRAME
    assert vm.run(CAVE)[0] == 'leavel'


def tick(vm, inv, msg_id=0, msg0=None):
    vm.traps = []; vm.calls_seen.clear()
    if msg0 is not None:                 # plant a Message and point slot 0 at it
        vm.wr(MSGBUF, msg0)
        vm.wr(cavesim.FRAME + 0, MSGBUF)
    vm.AH = msg_id; vm.AL = TASK_ADDR; vm.Y = cavesim.FRAME
    why, pc = vm.run(handler)
    assert why == 'leavel', (why, hex(pc))
    names = [inv.get(t, 'trap_%02x' % t) for t, _, _ in vm.traps]
    recs = [(inv.get(t, 'trap_%02x' % t), a, b) for t, a, b in vm.traps]
    spoken = [v & 0xFFFF for a, v in vm.calls_seen if a == cavesim.SPEAK_ADDR]
    return names, recs, spoken


print('probe160: the bare reload, mailbox owned')

print('1. a HEALTHY tick (id 0) is the probe157/158 build, unchanged')
vm, inv = mk()
arm(vm)
n, r, sp = tick(vm, inv)
assert n == HEALTHY, n
assert sp == [], sp
print('  %s' % ' -> '.join(n))
for fail in ('StreamKalimbaSink', 'FileFind', 'StreamFileSource',
             'TransformAdpcmDecode', 'TransformStart'):
    vm, inv = mk(fail=[fail])
    arm(vm)
    n, r, sp = tick(vm, inv)
    assert sp == [0x25], ('--fail %s spoke %s, expected the single id 0x25' % (fail, sp))
    assert 'MessageSendLater' not in n and 'KalimbaLoad' not in n, (fail, n)
print('  every healthy-build failure -> 0x25 "call with", no re-arm, no reload')

print('2. THE CASE THAT MATTERS: gate FALSE -> own mailbox -> FileFind -> KalimbaLoad -> STOP')
vm, inv = mk(gate_seq=[1, 1, 0])
arm(vm)
n, r, sp = tick(vm, inv)
assert sp == [], 'the reload tick must be SILENT, spoke %s' % sp
assert n == ['KalimbaSendMessage', 'MessageKalimbaTask', 'FileFind', 'KalimbaLoad'], n
print('  %s   (and nothing else)' % ' -> '.join(n))
mk_ = [x for x in r if x[0] == 'MessageKalimbaTask'][0]
assert mk_[1] & 0xFFFF == TASK_ADDR, hex(mk_[1] & 0xFFFF)
ff = [x for x in r if x[0] == 'FileFind'][0]
al, ah, a2 = ff[1] & 0xFFFF, (ff[1] >> 16) & 0xFFFF, (ff[2] >> 16) & 0xFFFF
assert al == 1 and a2 == KAPLEN and 0x7400 <= ah <= 0xD39A, (hex(al), hex(ah), a2)
kl = [x for x in r if x[0] == 'KalimbaLoad'][0]
assert kl[1] & 0xFFFF == KAPIDX, hex(kl[1] & 0xFFFF)
print('  MessageKalimbaTask(%#06x) ; FileFind(FILE_ROOT, %#06x, %d) -> KalimbaLoad(%#06x)'
      % (mk_[1] & 0xFFFF, ah, a2, kl[1] & 0xFFFF))
for bad in ('MessageSendLater', 'StreamKalimbaSink', 'TransformAdpcmDecode',
            'StreamDisconnect'):
    assert bad not in n, bad
assert n.count('KalimbaSendMessage') == 1, 'no re-gate after the load: %s' % n
print('  no re-arm, no re-gate, no sink, no transform after the load')

print('3. reload IMPOSSIBLE -> 0x3E, no re-arm')
for fail in ('FileFind', 'KalimbaLoad'):
    vm, inv = mk(gate_seq=[1, 1, 0], fail=[fail])
    arm(vm)
    n, r, sp = tick(vm, inv)
    assert sp == [0x3E], ('--fail %s spoke %s' % (fail, sp))
    assert 'MessageSendLater' not in n, n
    print('  --fail %-12s -> 0x3E "bluetooth off", no re-arm' % fail)

print('4. MESSAGE_FROM_KALIMBA at the handler')
vm, inv = mk()
arm(vm)
n, r, sp = tick(vm, inv, msg_id=MSG_FROM_KALIMBA, msg0=MUSIC_READY)
assert n == ['KalimbaPowerOff'], n
assert sp == [0x14], sp
print('  msg[0] = 0x1000 MUSIC_READY -> KalimbaPowerOff -> 0x14 "auto off disabled"')
for other in (0x8000, 0x7070):
    vm, inv = mk()
    arm(vm)
    n, r, sp = tick(vm, inv, msg_id=MSG_FROM_KALIMBA, msg0=other)
    assert n == [], 'msg[0]=%#06x must NOT power off or run any trap: %s' % (other, n)
    assert sp == [0x10], sp
    print('  msg[0] = %#06x -> NO trap -> 0x10 "and"' % other)
print('  (0x14 and 0x10 are DIFFERENT sounds; both prove the VM survived the load)')

print('5. every other MessageId runs NOTHING')
for mid in (MSG_FROM_KALIMBA_LONG, 0x8022, 0x0001, 0x7016):
    vm, inv = mk()
    arm(vm)
    n, r, sp = tick(vm, inv, msg_id=mid, msg0=MUSIC_READY)
    assert n == [] and sp == [], (hex(mid), n, sp)
    print('  MessageId %#06x -> no trap, no id' % mid)

print('6. the timer constant and the handler frame')
want = list(ca.imm_words(DELAY_MS, 0x14)) + [0x0227]
w = {int(k, 16): v & 0xFFFF for k, v in words.items()}
hit = [a for a in sorted(w) if all(w.get(a + i) == v for i, v in enumerate(want))]
assert hit, 'no `ld AL,#%d ; st AL,@(2,Y)`' % DELAY_MS
assert w[handler & 0x3FFFF] == 0xF60B, 'handler must open enterl -10 (Message at @(10,Y))'
print('  delay %d ms at %#x; handler at %#x opens enterl -10 and reads @(10,Y)'
      % (DELAY_MS, hit[0], handler & 0x3FFFF))

print('\nALL SIM CHECKS PASS (probe160: a FALSE tick owns the mailbox, loads the '
      "DSP and stops; the DSP's MUSIC_READY is answered with KalimbaPowerOff and "
      'a spoken id; nothing else runs anything)')
