#!/usr/bin/env python3
"""cavesim: run a cave in the emulator before flashing it.

Every probe so far has been tested by flashing it and asking the owner to
press a button -- a cycle that costs a reflash and a human. Most of what
can go wrong (a branch to the wrong label, a slot clobbered by a later
call, a loop that never terminates, a bail path that falls through) is
visible without any of that.

This loads a probe's generated words into the speaker's own `vm.app`,
stubs the firmware traps with plausible return values, runs the cave in
`tools/xapemu.py`, and reports the trap sequence, the exit value in AL,
and any buffer the cave filled.

    python tools/cavesim.py probe58
    python tools/cavesim.py probe58 --fail malloc     # force a bail path
    python tools/cavesim.py probe161 --dsp up --teardown
        # model the DSP handshake: after the entry run, deliver DSP replies
        # (MESSAGE_FROM_KALIMBA) and timer ticks to the cave's handler; --teardown
        # unloads the DSP before each tick. Validated: probe160 speaks 0x14, as on
        # hardware (2026-10-08). See install_dsp() for what the model assumes.

    # B2 (2026-10-10), the clocked world -- tools/cavesim_world.py, every flag opt-in, every
    # run above byte-identical (tools/cavesim_regress.py). Full list with examples:
    # docs/deep/offline-2026-10-10/cavesim-changes.md
    python tools/cavesim.py probe178 --entry 0x3E21D --loop 3 --press-gap 5000 --brief
        # three start-only press cycles on a virtual ms clock: chunk length from file size and
        # rate, the port-3 rules R1..R6 checked at every trap, --expect for assertions
    python tools/cavesim.py probe177 --entry 0x3E21D --music paused --press 0:4004 --press 8000:4004
        # the owner's probe177 result 1: press 2 speaks 0x3E (the DSP unloaded after the tone)
    python tools/cavesim_selftest.py        # mock 179/180/182/185b caves through the model

    # J-T3 (2026-10-12), failure worlds and the cave-carried trap stub (docs/deep/firmware-study-
    # 2026-10-12/T03-cavesim-and-seam-model.md); every flag opt-in, every run above byte-identical:
    python tools/cavesim.py probe181 --entry 0x3E21D --press 0:4004 --press 2800:4004 --cancel never
        # STOP failure world: the second press forks a second chain (R6 x56 in 30 s)
    python tools/cavesim.py probe181 --entry 0x3E21D --press 0:4004 --wrong-dsp 4000:3000
        # a prompt/call DSP replaces sbc_decoder: the gate reads TRUE, the rebuild lands there (W1)
    python tools/cavesim.py probe181 --entry 0x3E21D --press 0:4004 --mid-chunk-1072 4000:0
        # the stock sends 0x1072(8000, b=0) mid-chunk: purge cut + a +18 dB HEARING HAZARD
    python tools/cavesim.py <cave using a synthesised trap stub>   # prints SYNTHESISED TRAP STUB lines
    python tools/seammodel.py check        # the seam timing model (gap/splice vs P, L, c, D)

    # round 3 (2026-10-12, docs/deep/round3-2026-10-12/T14-tool-owner-round3.md): a cave branch into the
    # stock trap tail is a HAZARD and a STOP; --staged models FIRST = 9 / one byte per element (the old
    # layout is --staged-legacy); --src-unpacked / --p2-capture FILE / --size-dries-after N make the
    # 184 rehearsal need no monkeypatch; --caller-frame K checks a store into the caller's frame:
    python tools/cavesim.py probe181 --entry 0x3E21D --frame 13=1 --frame 14=0 --show 90D:2 --caller-frame 23

What it does NOT tell you: whether the firmware likes the calls. The stubs
always succeed unless told otherwise, and `asr` is modelled as a logical
shift, so a generated waveform's exact samples are indicative, not exact.
It answers "is this cave well-formed", not "will the speaker make a noise".
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'xapvm'))
import xapemu                                                  # noqa: E402
import caveguard                                               # noqa: E402  (J-T3: trap-stub recogniser)

APP = os.path.join(ROOT, 'firmware/bose/extracted/internal_fs/vm.app')
BACK_CALL = 0xE06D          # the Bose call the hook at 0xae0 displaced
HEAP = 0x2000               # where the fake malloc hands out memory
MODELLED_SEPARATELY = frozenset({'malloc', 'PartitionGetInfo', 'memmove', 'SourceMap',
                                 'fn_1f04c'})   # honour --fail via a closure, not a constant
FRAME = 0x0900              # synthetic Y for the cave's frame
SRCMAP = 0x4000             # probe141: where --staged preloads the mapped source
CLAIM = 0x9000              # probe141: where the modelled fn_12e1a claims to map
# 0x9000..0xFFFE = 28,670 words: fits the full 16,520-word payload without the
# wrap that would overwrite the cave's own frame at 0x8F8 (sim-only concern)
# (must NOT overlap the staged source: 0x4000 + 16,520 words = 0x8078)

# J-T12 / J-T3: traps that exist in the stack but have NO stub in Bose's vm.app (tools/bose-stubs.json
# has 151 entries and none of these). They can only be called through a cave-synthesised stub
# (caveguard.synth_stub_words), and their modelled return must still be installed (the loop in
# build() skips names that have no vm.app stub).
NO_VM_STUB = frozenset({'PartitionGetRawSerialSource'})

# Plausible, distinguishable return values. AL is the return register.
DEFAULT_RETURNS = {
    'StreamAudioSink':     0x51C0,
    'StreamAudioSource':   0x52C0,
    'StreamRingtoneSource': 0x53C0,
    'StreamFileSource':    0x54C0,
    'StreamKalimbaSink':   0x55C0,
    'StreamSourceFromSink': 0x56C0,
    'StreamSinkFromSource': 0x57C0,
    'StreamRegionSource':  0x58C0,
    'StreamConnect':       0x59C0,
    'SinkConfigure':       1,
    'SourceConfigure':     1,
    'StreamConfigure':     1,
    'SinkFlush':           1,
    'SinkSlack':           0x0100,
    'SinkClaim':           0x0000,     # offset 0 into the mapped buffer
    'SinkMap':             HEAP,
    'MessageSendLater':    0,
    'MessageSinkTask':     0,
    'FileFind':            1,          # FILE_INDEX; FILE_NONE is 0, FILE_ROOT 1
    'VmDeepSleepEnable':   1,          # returns the PREVIOUS setting
    'KalimbaSendMessage':  1,          # bool: TRUE only if a .kap is loaded
    'KalimbaLoad':         1,
    'StreamDisconnect':    1,
    'StreamConnectDispose': 0x5AC0,
    'TransformFromSink':   0x5BC0,
    'TransformFromSource': 0x5CC0,
    # The ADPCM route (probe103). TransformAdpcmDecode returns a Transform, and
    # TransformStart/Stop/Disconnect take one; distinct values so a simulated run
    # shows whether the cave passed the transform or accidentally re-passed the
    # source it was built from.
    'TransformAdpcmDecode': 0x5EC0,   # not 0x5DC0: that collides with probe104's length
    'TransformStart':      1,
    'TransformStop':       1,
    'TransformDisconnect': 0,
    'TransformPollTraffic': 1,
    # probe106: MessageFlushTask returns how many messages it flushed, so 0 means
    # no chain was pending, i.e. this press is a START. TransformFromSink returns
    # whatever holds the port; 0 means idle, which is the first-fill path.
    'MessageFlushTask':    0,
    'TransformConfigure':  1,
    # probe140 (pattern write): the overwrite sink returns a handle; the digest
    # call returns TRUE for md_type=3 (SKIP). --fail-able like everything else.
    'StreamPartitionOverwriteSink': 0x61C0,
    'PartitionSetMessageDigest':    1,
    'SinkClose':           1,
    # probe141 (staged write): FileFind returns a fake index; StreamFileSource a
    # fake source; SourceMap returns SRCMAP, where --staged preloads the payload
    # words. memmove is modelled separately (it really copies through vm.rd/wr).
    'FileFind':            0x5DF0,
    'StreamFileSource':    0x5FC0,
    'PartitionMountFilesystem': 1,
    'SourceMap':           0,          # closure below: returns SRCMAP
    # J-T12: PartitionGetRawSerialSource(device, partition) -> Source (a handle, 0 = failure).
    # INTERFACE MODEL ONLY: the source's size and bytes are not modelled (T12 section 6, S3).
    'PartitionGetRawSerialSource': 0x62C0,
}


def load_tables():
    stubs = json.load(open(os.path.join(ROOT, 'tools/bose-stubs.json')))
    names = json.load(open(os.path.join(ROOT, 'tools/traps-bluelab73.json')))
    return stubs, names


SPEAK_ADDR = 0xDF7F     # the prompt engine: id in AL, nothing in X, and it returns


def build(words_json, fail=(), pmap=None, dac_guard=False):
    """Patch a probe's words into vm.app and return a configured VM."""
    stubs, trapnums = load_tables()
    words = xapemu.load_vm_app(APP)
    patch = {int(k, 16): v & 0xFFFF for k, v in json.load(open(words_json)).items()}
    vm = xapemu.VM(words, trace_mem=False)
    code = list(vm.code)
    for a, v in patch.items():
        code[a] = v
    vm.code = code
    # D1 (probe199s): the cave's own data words (a table the code READS through a pointer) live in the const pool and
    # are visible in DATA space at 0x7400 + (a - 236514) on the device; xapemu.VM.rd serves that range from vm.const,
    # a separate copy of the ORIGINAL pool, so a patched word read as data came back as the stock (zero) word.
    # Mirror the patch into vm.const. (Code is fetched from vm.code and is unaffected.)
    _cw = 236514
    vm.const = list(vm.const)
    for a, v in patch.items():
        if a >= _cw and a - _cw < len(vm.const):
            vm.const[a - _cw] = v
    # The cave sits inside a const-pool zero run, so its words must be decoded
    # unfolded or the entry is not an instruction start. See xapemu.VM.run.
    # one span per address cluster (a gap of > 256 words starts a new cluster)
    spans, cur = [], None
    for a in sorted(patch):
        if cur and a - cur[1] <= 256: cur[1] = a
        else: cur = [a, a]; spans.append(cur)
    vm.nofold = [tuple(x) for x in spans]

    # J-T3 (T12 spec S1-S3): trap stubs the CAVE carries (`enterl -3 ; ld X,#n ; <tail>`).
    # The folded decode in xapemu cannot see them, so each is registered as a FUNC_RET
    # short-circuit at its address: reached by `bsr`, it reads the arguments from the caller's
    # frame at call time (exactly what the stock-stub interception does), records the trap and
    # returns to the caller with Y untouched. For a legacy cave synth is {} and nothing changes.
    synth = caveguard.find_cave_stubs(vm.code, vm.nofold)
    state_synth = synth

    # Every probe on the 0x107be hook reports its result by calling the prompt
    # engine at 0xDF7F directly (id in AL), instead of probe90's trick of leaving
    # the id in AL for the stock code at 0xAE0 to speak. The emulator ran the real
    # engine and returned, so those runs were valid but THE ID WAS NEVER REPORTED
    # -- the one thing the owner actually hears. Short-circuit it and record it.
    vm.FUNC_RET[SPEAK_ADDR] = (0, 0)   # FUNC_RET values are (AH, AL) pairs

    # malloc hands out a bump-allocated block so the cave has somewhere real
    # to write; a name in `fail` returns 0 instead, to exercise a bail path.
    state = {'brk': HEAP}

    def malloc(trap, ahal, a2):
        size = ahal & 0xFFFF
        if 'malloc' in fail:
            return (0, 0)
        p = state['brk']
        state['brk'] += size
        state.setdefault('blocks', []).append((p, size))
        return (0, p)

    for name, val in DEFAULT_RETURNS.items():
        if name not in stubs and name not in NO_VM_STUB:
            continue
        t = trapnums.get(name)
        if t is None:
            continue
        vm.STUB_RET[t] = (0, 0) if name in fail else (0, val)
    if 'malloc' in trapnums:
        vm.STUB_RET[trapnums['malloc']] = malloc

    def make_synth_stub(n):
        def synth_stub(pc, pair, _):
            vm.calls_seen.pop()               # a trap, not a "back-call" (xapemu logged it)
            a2 = (vm.rd(vm.Y & 0xFFFF) << 16) | vm.rd((vm.Y + 1) & 0xFFFF)
            vm.traps.append((n, pair, a2))
            ret = vm.STUB_RET.get(n)          # late lookup: the world model wraps STUB_RET
            if ret is None:
                return (vm.AH, vm.AL)
            return ret(n, pair, a2) if callable(ret) else ret
        return synth_stub
    for a_, (n_, _kind, _ln) in synth.items():
        vm.FUNC_RET[a_] = make_synth_stub(n_)
    state['synth'] = state_synth

    # probe139: PartitionGetInfo(device=AL, partition=AH, key=@(0,Y),
    # uint32* out=@(1,Y)) -> bool, value written THROUGH the pointer. Bose's own
    # call sites (0x1192a, 0x182d1: `ld AL,@0xffe4 ; add AL,#n ; st AL,@(1,Y)`,
    # then read the result from slots n:n+1 as AH:AL) put the LOW half at ptr+1.
    # Keys per adk partition_if.h: IS_MOUNTED=0, SIZE=1, TYPE=2, STATE=3,
    # SECTOR_SIZE=4; types UNUSED=0, FILESYSTEM=1, PS=2, RAW_SERIAL=3,
    # RANDOM_ACCESS=4. `pmap` is the SIMULATED map (partition -> TYPE), not a
    # claim about the device: the whole point of probe139 is that the live map
    # has never been read. Default is the map the static analysis predicts
    # (0 = main filesystem, 2 = ext language filesystem); --pmap overrides it so
    # every outcome branch of the census can be exercised without a flash.
    if pmap is None:
        pmap = {0: 1, 2: 1}
    else:
        pmap = {int(k): v for k, v in pmap.items()}   # JSON keys are strings

    def partition_getinfo(trap, ahal, a2):
        if 'PartitionGetInfo' in fail:
            return (0, 0)
        part = (ahal >> 16) & 0xFFFF
        key, ptr = (a2 >> 16) & 0xFFFF, a2 & 0xFFFF
        if part not in pmap:
            return (0, 0)
        st_val = 0
        if part == 2 and state.get('p2_overwritten'):
            st_val = 1 if 'PartitionSetMessageDigest' in fail else 0
        val = {0: 1, 1: 0x4000 * part, 2: pmap[part], 3: st_val, 4: 0x1000}.get(key, 0)
        vm.wr(ptr, 0)                       # high half
        vm.wr((ptr + 1) & 0xFFFF, val)      # low half
        return (0, 1)

    if 'PartitionGetInfo' in trapnums:
        vm.STUB_RET[trapnums['PartitionGetInfo']] = partition_getinfo

    # probe141: the file-source gather. SourceMap returns SRCMAP (words preloaded
    # from --staged); memmove(dst=AL, src=AH, len=@(0,Y)) copies for real, so a
    # simulated gather is checkable byte-for-byte at CLAIM. fn_12e1a (Bose's
    # SinkMap+SinkClaim helper, stock code at 0x12e1a) short-circuits to CLAIM.
    # The mapped source AND the claim buffer are loader/sink-internal, NOT VM
    # RAM: model both as virtual dicts. Emulated RAM cannot hold 37.7 K source
    # words + 16.5 K claim words around the read-only const window (0x7400-
    # 0xD39A) -- staged words silently vanished into it in the first run.
    state['claimbuf'] = {}
    state['claim_base'] = CLAIM
    state['srcbuf'] = {}

    def source_map(trap, ahal, a2):
        if 'SourceMap' in fail:
            return (0, 0)
        return (0, SRCMAP)

    if 'SourceMap' in trapnums:
        vm.STUB_RET[trapnums['SourceMap']] = source_map

    def rd_src(a):
        return state['srcbuf'].get(a, vm.rd(a & 0xFFFF))

    def memmove(trap, ahal, a2):
        dst, src = ahal & 0xFFFF, (ahal >> 16) & 0xFFFF
        n = (a2 >> 16) & 0xFFFF
        if 'memmove' in fail:
            return (0, 0)
        base = state.get('claim_dst')
        if dst == base:                    # the outstanding claim: sink-internal buf
            for k in range(n):
                state['claimbuf'][(dst + k) & 0xFFFF] = rd_src((src + k) & 0xFFFF)
            state['claim_dst'] = None
        else:
            for k in range(n):
                vm.wr((dst + k) & 0xFFFF, rd_src((src + k) & 0xFFFF))
        return (0, dst)

    if 'memmove' in trapnums:
        vm.STUB_RET[trapnums['memmove']] = memmove
    if 'StreamPartitionOverwriteSink' in trapnums:
        _base = vm.STUB_RET[trapnums['StreamPartitionOverwriteSink']]
        def overwrite_sink(trap, ahal, a2):
            part = (ahal >> 16) & 0xFFFF
            if part == 2 and not ('StreamPartitionOverwriteSink' in fail):
                state['p2_overwritten'] = True
            return _base if not callable(_base) else _base(trap, ahal, a2)
        vm.STUB_RET[trapnums['StreamPartitionOverwriteSink']] = overwrite_sink
    vm.FUNC_RET[BACK_CALL] = (0, 0)
    # probe162: fn_1f04c(&params), the stock audio_output connect (DAC rewire), modelled
    # as a bool; `--fail fn_1f04c` exercises the refusal path. The params it reads are
    # checked by the caller's verify, not here.
    def fn1f04c(pc, ahal, _):
        ptr = ahal & 0xFFFF
        state.setdefault('dac_params', []).append(tuple(vm.rd(ptr + k) for k in range(3)))
        if 'fn_1f04c' in fail: return (0, 0)
        if dac_guard:      # --dac-guard (probe295): the real guard at 0x1f051..0x1f056: bit 15 of @0x6d1 ("DAC connected") set -> return 0 with no work; success sets it (0x1f098..0x1f09c)
            if vm.rd(0x6D1) & 0x8000:
                state['dac_refused'] = state.get('dac_refused', 0) + 1
                return (0, 0)
            vm.wr(0x6D1, vm.rd(0x6D1) | 0x8000)
        vm.chain_alive = True      # BH (--chain-model): the DAC link chain of fn_1f04c exists (a recorded attribute; no behaviour of any existing option reads it)
        return (0, 1)
    vm.FUNC_RET[0x1F04C] = fn1f04c
    # probe323 (2026-10-24): the four stock Bluetooth scan wrappers (docs/deep/material-2026-10-19/BK-lifted-connlib.md 4.3), modelled as recorded calls that keep the state bits @0x564
    # bit 10 (page scan on) and bit 11 (inquiry scan on) exactly as the real code does (0x0c7f2: |= 0x400; 0x0c80e: &= ~0x400; 0x0c82a: |= 0x800; 0x0c86d: &= ~0x800). The scan-enable value each would send is recorded
    # in state['scan_calls'] as (wrapper, scan_enable): page ON = 3 if bit 11 else 2; page OFF = 1 if bit 11 else 0; inquiry ON = 3 if bit 10 else 1; inquiry OFF = 2 if bit 10 else 0 (read BEFORE the bit changes, as the code does).
    def _scan(name, set_mask, clear_mask, val):
        def f(pc, ahal, _):
            w = vm.rd(0x564)
            state.setdefault('scan_calls', []).append((name, val(w)))
            vm.wr(0x564, (w | set_mask) & ~clear_mask & 0xFFFF)
            return (0, 0)
        return f
    vm.FUNC_RET[0x0C7F2] = _scan('page_on', 0x400, 0, lambda w: 3 if w & 0x800 else 2)
    vm.FUNC_RET[0x0C80E] = _scan('page_off', 0, 0x400, lambda w: 1 if w & 0x800 else 0)
    vm.FUNC_RET[0x0C82A] = _scan('inq_on', 0x800, 0, lambda w: 3 if w & 0x400 else 1)
    vm.FUNC_RET[0x0C86D] = _scan('inq_off', 0, 0x800, lambda w: 2 if w & 0x400 else 0)
    # probe328 (2026-10-24): fn_09157 = number of connected devices (modelled: 1 when the sink state @0x59e is 3 or more, else 0); fn_09445(flag) = the stock's drop-every-link helper, recorded as ('drop_all', flag) and followed by the
    # effect of the stock's disconnect tail: sink state 1 (Connectable) and page scan on (bit 10 of @0x564, fn_0d481 -> fn_0c7f2), applied at once (the real tail comes later; the product's watchdog scans off again)
    vm.FUNC_RET[0x09157] = lambda pc, ahal, _: (0, 1 if vm.rd(0x59E) >= 3 else 0)
    def _drop_all(pc, ahal, _):
        state.setdefault('scan_calls', []).append(('drop_all', ahal & 0xFFFF))
        vm.wr(0x59E, 1)
        vm.wr(0x564, vm.rd(0x564) | 0x400)
        return (0, 0)
    vm.FUNC_RET[0x09445] = _drop_all
    vm.WATCH.update((0x1F5BF, 0x22A89))      # probe296: the cold DAC gain (fn_22a89(n) -> fn_1f5bf(0, gain)) is recorded, not modelled
    # probe167: fn_23229(volume, flag), the stock prompt-volume setter (fn_1f47a x2 ->
    # KalimbaSendLongMessage 0x1002/0x101b -> fn_1f589 x2). Void. Modelled as a recorded
    # call because its real code reads the audio_output config @0x6d0, which this
    # simulator leaves 0, and would Panic.
    vm.FUNC_RET[0x23229] = (0, 0)
    # probe171: fn_1f4e1(output, gain_60ths_dB), the audio_output per-output hardware-gain
    # setter (fn_1f371 = StreamAudioSink, fn_1f3e9 = dB -> DAC gain, SinkConfigure 0x303 under
    # PanicNull). Void. Recorded, for the same reason as fn_23229: it reads @0x6d0.
    vm.FUNC_RET[0x1F4E1] = (0, 0)
    # probe171: fn_1f512(group, gain) = fn_1f4e1 for each output of the group (0: outputs
    # 0..4; caller slot 0 = 0 -> no per-output trims). Void, recorded likewise.
    vm.FUNC_RET[0x1F512] = (0, 0)
    # 2026-10-18: fn_1f12b, the stock audio_output DISCONNECT (undoes fn_1f04c; every stock teardown calls it). Void, recorded (probe279: the cave undoes its own DAC connection on an OFF).
    def fn1f12b(pc, ahal, _):
        vm.chain_alive = False     # BH: the cave's own DAC disconnect destroys the chain
        if dac_guard: vm.wr(0x6D1, vm.rd(0x6D1) & 0x7FFF)      # --dac-guard: the clear at 0x1f163..0x1f168
        return (0, 0)
    vm.FUNC_RET[0x1F12B] = fn1f12b if dac_guard else (0, 0)
    # J-T3 (T06 E15/E20, the volume Variant B): fn_1f47a(group AL, master AH, tone @(0,Y),
    # &blk @(1,Y)) copies the tone VERBATIM into blk[2] (proven, 0x1f487), and Panics when
    # @0x6d0 (the audio_output config) is 0, group >= 2 or blk == 0 (proven, 0x1f47e-0x1f485,
    # 0x1f4b6): the model raises the same stop so a cave that forgets `--mem 6d0=...` or passes a
    # bad group is caught. Digital-arm model: blk[1] := master; blk[0] (fn_1f3e9 of the config
    # word) is NOT modelled (unknown gain type, T06 census). Void.
    def fn1f47a(pc, pair, _):
        group, master = pair & 0xFFFF, (pair >> 16) & 0xFFFF
        tone, blk = vm.rd(vm.Y & 0xFFFF), vm.rd((vm.Y + 1) & 0xFFFF)
        if vm.rd(0x6D0) == 0 or group >= 2 or blk == 0:
            raise RuntimeError('fn_1f47a would Panic (T06 E15): @0x6d0=%#06x group=%d blk=%#06x '
                               '(preset --mem 6d0=<config>, group 0 or 1, blk != 0)'
                               % (vm.rd(0x6D0), group, blk))
        vm.wr((blk + 2) & 0xFFFF, tone)
        vm.wr((blk + 1) & 0xFFFF, master)
        state.setdefault('gain_blocks', []).append((group, master, tone, blk))
        return (0, 0)
    vm.FUNC_RET[0x1F47A] = fn1f47a
    vm.Y = FRAME
    return vm, state, stubs, trapnums


def hazards(patch, stubs=None, caller_frame=None):
    """Static checks a cave must pass before it is worth simulating.

    **add/sub -> addc/subc adjacency.** The ADK compiles with
    `-mworkaround-b96516`, whose own help string reads "Use NOPs to avoid
    MPU hardware bug B-96516". The only thing the flag changes is to insert
    a `nop` between an `add`/`sub` and the `addc`/`subc` that follows it. Bose's own image obeys
    it: 106 of its 108 addc/subc are immediately preceded by a nop, and
    the two that are not have other instructions between them and their
    add. Hand-written cave code gets no such help from a compiler, and the
    bug would be invisible in this emulator -- which computes the carry
    correctly -- while being wrong on the speaker.
    """
    words = {int(k, 16): v & 0xFFFF for k, v in patch.items()}
    # J-T3: a cave-synthesised trap stub has its own `enterl -3` frame (slot 0 = the trap
    # number, slots 1-2 = the saved return address, written by enterl itself). Its words must
    # not set the frame the REST of the cave is judged against, and are not judged. With no
    # stub this is a no-op, so every pre-existing run is byte-identical.
    if stubs:
        skip = {a + k for a, (_n, _kd, ln) in stubs.items() for k in range(ln)}
        words = {a: w for a, w in words.items() if a not in skip}
    lo, hi = min(words), max(words)
    seq, a = [], lo
    while a <= hi:
        if a not in words:
            a += 1
            continue
        n = 1
        while (words.get(a + n - 1, 0) & 0xFF) == 0x00 and words.get(a + n - 1) and n < 4:
            if a + n not in words:
                break
            n += 1
        seq.append((a, words[a + n - 1] & 0xFF, n))
        a += n
    branches = {0x20, 0x24, 0x28, 0x2C, 0xE4, 0xE8, 0xEC, 0xF0, 0xF4, 0xF8, 0xFC}
    out = []
    # **`enterl -k` reserves the TOP TWO slots for the saved return address.**
    # Usable slots are 0 .. k-3; storing to @(k-2,Y) or @(k-1,Y) overwrites the
    # 2-word code-relative return address, and the cave dies on `leavel`.
    #
    # Derived from Bose's own code generation: of 3,446 functions with an
    # `enterl -k` and a store to @(n,Y) with n<k, **3,208 leave exactly the top
    # two slots alone** and none violates the rule (the 3 apparent exceptions
    # decode const-pool data as instructions). It also explains why the
    # compiler gives a leaf `enterl -2` and then puts its local at @(-1,Y):
    # with k=2 there are no usable positive slots at all.
    #
    # This cost probes 68, 69, 72, 73, 78, 79 and 80 -- seven crashes and six
    # owner presses spent bisecting a generator that was never at fault.
    frame = None
    for a in sorted(words):
        if (words[a] & 0xFF) == 0x0B:               # enterl
            op = words[a] >> 8
            frame = op - 256 if op & 0x80 else op
            frame = -frame if frame < 0 else frame
            break
    if frame and frame >= 2:
        bad = sorted({(v >> 8) for v in words.values()
                      if (v & 0xFF) in (0x27, 0x23, 0x2B)
                      and frame - 2 <= (v >> 8) < frame})
        for slot in bad:
            out.append('frame slot %d is part of the saved return address of '
                       '`enterl -%d` (usable slots are 0..%d) -- storing to it '
                       'destroys the return path'
                       % (slot, frame, frame - 3))
    if caller_frame and frame:
        # R05 (E15, E17): the callee's incoming argument / the caller's slot j is cave slot frame+j,
        # and the caller's own saved return address sits at its slots K-2, K-1. A store at a literal
        # slot >= the cave frame is a write INTO THE CALLER'S FRAME.
        for slot in sorted({(v >> 8) for v in words.values() if (v & 0xFF) in (0x27, 0x23, 0x2B)
                            and (v >> 8) >= frame}):
            j = slot - frame
            if j in (caller_frame - 2, caller_frame - 1):
                out.append('cave slot %d is caller slot %d, part of the CALLER\'s saved return address '
                           '(its `enterl -%d` slots %d and %d): storing to it destroys the return path'
                           % (slot, j, caller_frame, caller_frame - 2, caller_frame - 1))
            else:
                out.append('NOTE cave slot %d writes caller slot %d (an attested form only for '
                           'incoming-argument slots, R05 E16; the caller\'s local at slot %d is %s)'
                           % (slot, j, j, 'inside its frame' if j < caller_frame - 2
                              else 'beyond its frame'))
    for k in range(1, len(seq)):
        addr, op, _ = seq[k]
        prev_addr, prev_op, prev_n = seq[k - 1]
        if (op >> 4) in (0x4, 0x6) and (prev_op >> 4) in (0x3, 0x5):
            out.append('0x%05X: %s immediately follows %s at 0x%05X -- the '
                       'MPU needs a nop between them (bug B-96516)'
                       % (addr, 'addc' if (op >> 4) == 4 else 'subc',
                          'add' if (prev_op >> 4) == 3 else 'sub', prev_addr))
        # The compiler's -mleave-sets-flags says `leave` and `rts` SET FLAGS,
        # so a conditional branch straight after a call is reading whatever
        # the callee's return left -- which this emulator does not model, and
        # which a trap's behaviour is anyway not documented for. Always `cmp`
        # the returned value first.
        if op in branches and prev_op in (0x9C, 0x9E):
            out.append('0x%05X: conditional branch straight after the call at '
                       '0x%05X -- leave/rts set flags, so cmp the result first'
                       % (addr, prev_addr))
    return out


# ---- the DSP handshake (--dsp), offline plan item 6, 2026-10-08 -------------------------
# A model of sbc_decoder's side of the conversation, from what is established in
# docs/field-log.md and the PM-flash overlay (tools/kapdisasm.py): it boots on KalimbaLoad
# and sends MUSIC_READY 0x1000 to whichever task owns the Kalimba mailbox; SETPLUGIN 0x1020
# (code 1/5/8) then LOADPARAMS 0x1012 is answered with PARAMS_LOADED 0x1015 (the PS reads in
# between are serviced by the firmware, not the VM); GO 0x7000 without SETPLUGIN halts it in
# $error (probe96). KalimbaSendMessage is TRUE only while a .kap is loaded. A MODEL: it
# checks that a cave's half of the protocol is well-formed, not that the DSP agrees.
CONST_DATA_BASE, CODE_WORDS = 0x7400, 236514
DSP_MSG = 0x8024            # MESSAGE_FROM_KALIMBA
MSGBUF = 0x3000             # where a delivered Message's words are placed


def install_dsp(vm, trapnums, up, fail=(), refuse=()):
    dsp = {'loaded': up, 'plugin': None, 'go': False, 'halted': False, 'task': None,
           'queue': [], 'log': []}
    vm.chain_alive = bool(up)      # BH (--chain-model): a stock DSP that is up has its own DAC chain; a cold start has none

    def note(s):
        dsp['log'].append(s)

    def kload(trap, ahal, a2):
        if 'KalimbaLoad' in fail:
            note('KalimbaLoad refused (--fail)')
            return (0, 0)
        if (ahal & 0xFFFF) == 0:
            note('KalimbaLoad(FILE_NONE) refused')
            return (0, 0)
        dsp.update(loaded=True, plugin=None, go=False, halted=False)
        vm.chain_alive = False     # BH: a successful KalimbaLoad disposes every transform chain (BG 0.1 item 3)
        note('DSP loaded and booted')
        if dsp['task'] is not None:
            dsp['queue'].append(('dsp', 0x1000))
            note('  -> MUSIC_READY 0x1000 queued to the cave task')
        else:
            note('  -> MUSIC_READY 0x1000 goes to a STOCK task (mailbox not ours)')
        return (0, 1)

    def ktask(trap, ahal, a2):
        dsp['task'] = ahal & 0xFFFF
        note('MessageKalimbaTask(%#06x): the mailbox is ours' % dsp['task'])
        return (0, 0)

    def kpoff(trap, ahal, a2):
        dsp.update(loaded=False, plugin=None, go=False)
        vm.chain_alive = False     # BH: KalimbaPowerOff disposes every chain
        dsp['queue'] = [e for e in dsp['queue'] if e[0] != 'dsp']
        note('KalimbaPowerOff: DSP off')
        return (0, 0)

    def ksend(trap, ahal, a2):
        mid, arg = ahal & 0xFFFF, (ahal >> 16) & 0xFFFF
        if not dsp['loaded']:
            note('KalimbaSendMessage(%#06x) -> FALSE (no .kap loaded)' % mid)
            return (0, 0)
        if dsp['halted']:
            note('KalimbaSendMessage(%#06x) into a HALTED DSP' % mid)
        if mid in refuse and dsp['plugin'] is not None:
            note('KalimbaSendMessage(%#06x) -> FALSE (--dsp-refuse, configured DSP)' % mid)
            return (0, 0)
        if mid == 0x1020:
            ok = arg in (1, 5, 8)
            dsp['plugin'] = arg if ok else None
            note('SETPLUGIN(%d) %s' % (arg, 'accepted' if ok else 'REJECTED (not 1/5/8)'))
        elif mid == 0x1012:
            if dsp['plugin'] is not None:
                dsp['queue'].append(('dsp', 0x1015))
                note('LOADPARAMS(%#06x) -> PARAMS_LOADED 0x1015 queued' % arg)
            else:
                note('LOADPARAMS before SETPLUGIN: no PARAMS_LOADED')
        elif mid == 0x7000:
            if dsp['plugin'] is None:
                dsp['halted'] = True
                note('GO without SETPLUGIN: DSP HALTS in $error (probe96)')
            else:
                dsp['go'] = True
                note('GO: DSP running')
        else:
            note('KalimbaSendMessage(%#06x, %#06x, b=%#06x, c=%#06x) -> TRUE'
                 % (mid, arg, (a2 >> 16) & 0xFFFF, a2 & 0xFFFF))   # probe166: b/c shown
            if mid == 0x7AB3:   # probe296: the POKE messages; the 4th argument (stack slot 2 = value hi) carries the tone mix ratio byte
                note('POKE message: addr %#06x, value hi (stack slot 2) = %#06x' % (arg, vm.rd((vm.Y + 2) & 0xFFFF) & 0xFFFF))
        return (0, 1)

    def ksendlong(trap, ahal, a2):
        # probe168: KalimbaSendLongMessage(id AL, len AH, ptr @(0,Y)); logs the payload.
        mid, n, ptr = ahal & 0xFFFF, (ahal >> 16) & 0xFFFF, (a2 >> 16) & 0xFFFF
        if not dsp['loaded']:
            note('KalimbaSendLongMessage(%#06x) -> FALSE (no .kap loaded)' % mid)
            return (0, 0)
        if mid in refuse and dsp['plugin'] is not None:
            note('KalimbaSendLongMessage(%#06x) -> FALSE (--dsp-refuse, configured DSP)' % mid)
            return (0, 0)
        def rd(a):   # const addresses (>= 0x7400) live in the code image, as in handler_of
            return (vm.code[CODE_WORDS + (a - CONST_DATA_BASE)] if a >= CONST_DATA_BASE
                    else vm.rd(a)) & 0xFFFF
        note('KalimbaSendLongMessage(%#06x, len %d, @%#06x = [%s]) -> TRUE'
             % (mid, n, ptr, ' '.join('%04x' % rd(ptr + k) for k in range(n))))
        return (0, 1)

    for name, fn in (('KalimbaLoad', kload), ('MessageKalimbaTask', ktask),
                     ('KalimbaPowerOff', kpoff), ('KalimbaSendMessage', ksend),
                     ('KalimbaSendLongMessage', ksendlong)):
        if name in trapnums:
            vm.STUB_RET[trapnums[name]] = fn
    return dsp


def handler_of(vm, task):
    """The handler address held in a const TaskData {hwrd, lwrd} at data address `task`."""
    c = CODE_WORDS + (task - CONST_DATA_BASE)
    return ((vm.code[c] << 16) | vm.code[c + 1]) & 0x3FFFF


def run_report(vm, names, title):
    print('\n== %s' % title)
    for t, ahal, a2 in vm.traps:
        print('  %-24s AL=%#06x AH=%#06x' % (names.get(t, 'trap_%02x' % t),
                                             ahal & 0xFFFF, ahal >> 16))
    for a, v in getattr(vm, 'watched', []):
        g = (v >> 16) & 0xFFFF
        print('  watched fn_%05x  AL=%#06x AH=%#06x%s' % (a, v & 0xFFFF, g, ('  (gain %d/60 dB)' % (g - 0x10000 if g & 0x8000 else g)) if a == 0x1F5BF else ''))
    for a, v in vm.calls_seen:
        if a == SPEAK_ADDR:
            print('  SPEAKS 0x%02X' % (v & 0xFFFF))
        else:
            print('  calls fn_%05x  AL=%#06x AH=%#06x' % (a, v & 0xFFFF, (v >> 16) & 0xFFFF))


def dsp_session(vm, dsp, names, trapnums, args, vm_state=None):
    vm_state = vm_state if vm_state is not None else {}
    """Deliver DSP and timer messages to the cave's handler until the queue is empty."""
    timers = []
    def collect():
        for t, ahal, a2 in vm.traps:
            if names.get(t) == 'MessageSendLater':
                timers.append((ahal & 0xFFFF, (ahal >> 16) & 0xFFFF))
        for line in dsp['log']:
            print('    dsp: %s' % line)
        dsp['log'] = []
    collect()
    shown = [0]
    for n in range(args.events):
        if dsp['queue']:
            kind, mid = dsp['queue'].pop(0)
            task = dsp['task']
            vm.AH, vm.AL = DSP_MSG, task
            for k, v in enumerate((mid, 0, 0, 0, 0)):
                vm.wr(MSGBUF + k, v)
            title = 'event %d: MESSAGE_FROM_KALIMBA msg[0]=%#06x' % (n + 1, mid)
        elif timers:
            task, mid = timers.pop(0)
            if args.teardown and dsp['loaded'] and not dsp.get('torn'):
                dsp.update(loaded=False, plugin=None, go=False, torn=True)
                print('\n  (--teardown: the A2DP teardown unloads the DSP before this tick)')
            vm.AH, vm.AL = mid, task
            title = 'event %d: timer, MessageId %#06x' % (n + 1, mid)
        else:
            print('\nqueue empty after %d event(s); DSP %s%s' % (
                n, 'loaded' if dsp['loaded'] else 'off',
                ', HALTED' if dsp['halted'] else (', running' if dsp['go'] else '')))
            return 0
        h = handler_of(vm, task)
        vm.Y = FRAME
        vm.wr(FRAME, MSGBUF)              # the Message, read as @(n,Y) after enterl -n
        try:
            why, pc = vm.run(h, max_steps=args.steps)
        except RuntimeError as e:
            print('STOPPED in %s: %s' % (title, e))
            return 1
        run_report(vm, names, '%s -> handler 0x%05X, ended %s at 0x%05X'
                   % (title, h, why, pc))
        sc = vm_state.get('scan_calls', [])
        if sc: print('  scan calls so far: %s' % ' '.join('%s=%d' % c for c in sc))
        dp = vm_state.get('dac_params', [])
        for prm in dp[shown[0]:]:
            print('  fn_1f04c params at call time: {%s}' % ', '.join('%#06x' % x for x in prm))
        shown[0] = len(dp)
        collect()
    print('\nevent limit (%d) reached' % args.events)
    return 0


def show_words(vm, specs):
    """--show ADDR[:N]: print cave state words after the run (B2)."""
    for spec in specs:
        a, _, n = spec.partition(':')
        a, n = int(a, 16), int(n or '1', 0)
        print('data @0x%04X..+%d: %s' % (a, n, ' '.join('%04x' % vm.rd(a + k) for k in range(n))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('probe', help='probe name, e.g. probe58')
    ap.add_argument('--dac-guard', action='store_true',
                    help='model the fn_1f04c guard on @0x6d1 bit 15 (refuse while set, set on success) and the fn_1f12b clear (probe295 gate); off: fn_1f04c always succeeds')
    ap.add_argument('--fail', action='append', default=[],
                    help='trap name that should return 0 (repeatable)')
    ap.add_argument('--steps', type=int, default=200000)
    ap.add_argument('--entry', help='hex entry address; needed since probe105, '
                                    'whose cave spans runs below the hook target '
                                    'so the lowest word is no longer the entry')
    # Every probe since probe109 gates on the event id the hook passed in AH
    # (`cmp AH,#0x4004`). With no way to set it, those probes entered with AH=0,
    # failed their own gate and simulated only the OTHER branch -- so the audio
    # chain they exist to check was never executed here. These set the entry
    # registers the way the hook site does.
    ap.add_argument('--ah', help='hex AH on entry (e.g. 4004, the event id)')
    ap.add_argument('--al', help='hex AL on entry')
    ap.add_argument('--mem', action='append', default=[], metavar='ADDR=VAL',
                    help='preset a data word before entry, e.g. --mem 59e=3. Needed for '
                         'GATED probes: probe131 reads sinkState at @0x59e, which defaults '
                         'to 0 here, so without this only the bail path is exercised.')
    ap.add_argument('--staged', help='the payload preloaded at 0x%04X as the mapped data_us source. '
                                     'Round 3 (T08/T14): ONE BYTE PER ELEMENT, FIRST = 9, i.e. payload '
                                     'byte k sits at map element 64*(k//28) + 18 + k%%%%28 (28 bytes of '
                                     'every 64-byte period, the layout narrow184_lib.stage writes). '
                                     'FILE = a JSON list of byte values, or any other file read as raw '
                                     'bytes. Capped at 20,480 elements (%d periods): a longer payload '
                                     'needs the world model (--fs-add NowSpeakTTS/data_us=@FILE '
                                     '--src-unpacked). --staged-legacy restores the 2026-10 layout.'
                                     % (SRCMAP, (CLAIM - SRCMAP) // 64))
    ap.add_argument('--staged-legacy', action='store_true',
                    help='with --staged: the pre-round-3 layout, a JSON list of 16-bit WORDS, 14 per '
                         '32-word period starting at word 11 (probe141, FIRST = 11; known wrong: '
                         'payload-184.md section 0)')
    ap.add_argument('--pmap', help='probe139 only: JSON partition->TYPE map the simulated '
                                   'PartitionGetInfo answers from, e.g. \'{"0":1,"2":0}\'. '
                                   'Default {"0":1,"2":1} (main + ext filesystems).')
    ap.add_argument('--dsp-refuse', action='append', default=[], metavar='ID',
                    help='with --dsp: KalimbaSendMessage(ID) returns FALSE once the DSP is '
                         'configured (after an accepted SETPLUGIN), e.g. 7000 for GO. '
                         'Exercises a bail on the reloaded DSP without failing the gate '
                         'sends before it (probe164)')
    ap.add_argument('--dsp', choices=('up', 'down'),
                    help='model the DSP handshake (state at entry: up = a .kap is loaded); '
                         'then deliver DSP and timer messages to the cave handler')
    ap.add_argument('--teardown', action='store_true',
                    help='with --dsp: unload the DSP before the FIRST timer tick only (the '
                         '~7 s A2DP teardown that probes 157-161 run into; it happens once)')
    ap.add_argument('--events', type=int, default=None,
                    help='with --dsp: max deliveries (default 10; 400 in the clocked world)')
    ap.add_argument('--fail-after', action='append', default=[], metavar='TRAP=N',
                    help='with --dsp: TRAP returns 0 from its Nth call on (e.g. '
                         'TransformAdpcmDecode=2 fails only the build on our own DSP)')
    ap.add_argument('--dump', action='store_true',
                    help='print every word of each malloc block, not just 12')
    ap.add_argument('--caller-frame', metavar='K',
                    help='the hook CALLER is a function with `enterl -K` (fn_00846 = 23): a store at '
                         'cave slot s >= the cave frame lands in the caller slot s - frame. A store into '
                         'the caller saved return address (slots K-2, K-1) is a HAZARD and stops the run '
                         '(R05: the consume lever at 21/22 is right, 29/30 would crash)')
    # ---- B2 (2026-10-10): the clocked world, see tools/cavesim_world.py and
    # docs/deep/offline-2026-10-10/cavesim-changes.md. All opt-in; none changes an old run.
    g = ap.add_argument_group('world model (offline workflow B2)')
    g.add_argument('--world', action='store_true',
                   help='install the world model (port 3, rules, fs, messages, clock) and run '
                        'the clocked session; implied by every flag in this group except '
                        '--enter/--task/--frame/--x/--y/--show/--id')
    g.add_argument('--loop', type=int, metavar='N',
                   help='run until N chunks have ended, let a bounded cave finish '
                        '(--settle-ms), stop if chunk N+1 starts (an unbounded cave)')
    g.add_argument('--press', action='append', default=[], metavar='MS:EVENT',
                   help='a button event delivered to the entry at MS ms, e.g. 0:4004 '
                        '(repeatable; default one press of --al, else 4004, at t=0)')
    g.add_argument('--press-gap', type=int, metavar='MS',
                   help='start-only caves: press again MS ms after each chunk ends when the '
                        'cave has nothing pending (probe178: 5000)')
    g.add_argument('--pending', action='append', default=[], metavar='ID[@MS]',
                   help='a cave message already pending at start (hex id, due at MS, default '
                        '1000): MessageCancelFirst finds it; delivered unless cancelled')
    g.add_argument('--flag-id', metavar='ID', help='world (opt-in, probe232+): the hex MessageId of a long-lived MODE FLAG message the cave keeps pending by design; '
                   'rule R6 and the "still pending" line ignore messages with this id (reported on their own line)')
    g.add_argument('--once', action='store_true', help='world: run only the events at t=0')
    g.add_argument('--horizon', type=int, default=600000, help='world: end of time, ms')
    g.add_argument('--settle-ms', type=int, default=3000,
                   help='with --loop: how long after chunk N ends a bounded cave may still act')
    g.add_argument('--poll-floor', type=int, default=50,
                   help='rule R5: MessageSendLater to the cave below this many ms is a violation')
    g.add_argument('--stock-rate', type=int, default=8000,
                   help='the rate the stock leaves in the DSP (probe177 R2: first chunk ~8 kHz)')
    g.add_argument('--latch', choices=('late', 'immediate'), default='late',
                   help='late: a sent 0x1072 rate applies from the NEXT chunk (observed, n=2); '
                        'immediate: from the chunk it precedes')
    g.add_argument('--free-edge', choices=('eof', 'audible'), default='eof',
                   help='when firmware frees port 3: at source EOF or at the audible end '
                        '(unknown offline: verify.md V1)')
    g.add_argument('--tail-ms', type=int, default=0,
                   help='audible end minus source EOF (the DSP draining the tone); with '
                        '--free-edge eof the port reads free this long while audible (V2 hazard)')
    g.add_argument('--tone-end-ms', type=int, default=30,
                   help='DSP end-of-tone 0x1080 this long after the audible end (V6: ~30 ms)')
    g.add_argument('--music', choices=('playing', 'paused'), default='playing',
                   help='paused: the DSP unloads --unload-ms after each tone end (probe177 R1)')
    g.add_argument('--unload-ms', type=int, default=100,
                   help='paused-music unload latency after the tone end (unmeasured, V6)')
    g.add_argument('--chunk-ms', help='chunk durations, comma list (last repeats), or auto '
                                      '(file bytes x 2 samples / rate)')
    g.add_argument('--stock-prompt', action='append', default=[], metavar='MS:DUR',
                   help='a stock prompt holds port 3 from MS for DUR ms (TransformFromSink '
                        'reads a foreign handle)')
    g.add_argument('--bt-teardown-at', type=int, metavar='MS',
                   help='Bluetooth long press at MS: the running chunk ends cleanly, the DSP '
                        'unloads, pending cave messages are not flushed (model of fn_0d500)')
    g.add_argument('--unload-at', type=int, metavar='MS', help='the DSP unloads at MS')
    g.add_argument('--music-resume-at', type=int, metavar='MS',
                   help='the stock reloads the DSP at MS (rate latch back to the stock rate)')
    g.add_argument('--fs-add', action='append', default=[], metavar='PATH=SIZE|@FILE[:VIS]',
                   help='add a file; VIS = root (default) | p2 | never. p2 files are visible '
                        'once p2 is written+closed with digest SKIP (or --p2-preloaded) AND '
                        '(--p2-automount or the cave mounted p2)')
    g.add_argument('--src-window', type=int, metavar='BYTES',
                   help='SourceSize returns at most this many bytes (default: the whole '
                        'remaining file, capped at 0xFFFF as a uint16)')
    g.add_argument('--src-endian', choices=('le', 'be'), default='le',
                   help='byte packing of SourceMap words (unknown offline; probe182 settles it)')
    g.add_argument('--src-unpacked', action='store_true',
                   help='world: SourceMap maps ONE BYTE PER 16-BIT ELEMENT (the device convention, T08: '
                        'fn_1edf9, fn_185c3; StreamRegionSource was seen so, FACTS N012) instead of two '
                        'bytes per word; window semantics unchanged')
    g.add_argument('--drop-adv', type=int, default=None, metavar='N',
                   help='D1 (probe199s): every SourceDrop advances the file source by exactly N bytes whatever it was asked '
                        '(default: the bytes asked); the position is clamped to the file size')
    g.add_argument('--map-shift-from', metavar='POS:SHIFT',
                   help='D1: from file position POS on, SourceMap presents the bytes starting at position + SHIFT (SHIFT may be negative)')
    g.add_argument('--map-fail-pos', type=int, default=None, metavar='POS',
                   help='D1: SourceMap on a file source returns 0 once the position is POS or more')
    g.add_argument('--map-lead', type=int, default=0, metavar='N',
                   help='R3b (probe198b): with --src-unpacked the map has N leading elements (value 0xDD) BEFORE the window bytes, '
                        'so element j holds window byte j - N (probe200: N = 1)')
    g.add_argument('--map-lead-rule', action='append', default=[], metavar='M:R:N',
                   help='F1 (probe201): when the window start position % M == R the map has N leading elements (first matching rule wins; '
                        'otherwise --map-lead): an alignment-dependent shift')
    g.add_argument('--map-lead-last', action='append', default=[], metavar='S:N',
                   help='G1 (probe202): history dependence: when the LAST SourceDrop on the source asked for S bytes the map has N leading elements '
                        '(applied after --map-lead-rule; first match wins)')
    g.add_argument('--map-lead-ndrop', action='append', default=[], metavar='C:N',
                   help='G1 (probe202): history dependence: when the source has seen C or more SourceDrop calls the map has N leading elements '
                        '(applied after --map-lead-last)')
    g.add_argument('--map-trunc', action='store_true',
                   help='R3b: with --map-lead the map has SourceSize elements in all (the last N window bytes are not mapped)')
    g.add_argument('--src-hibyte', action='store_true',
                   help='E1 (probe200): with --src-unpacked every element holds its byte in the HIGH byte (b << 8)')
    g.add_argument('--map-live', action='store_true',
                   help='E1: the memory a SourceMap pointer addresses follows later SourceDrops of that source (a live window); '
                        'default: a snapshot taken at the SourceMap call')
    g.add_argument('--src-hijunk', action='store_true',
                   help='D1: with --src-unpacked every element carries 0x5A in its high byte (a map with junk above the byte)')
    g.add_argument('--src-cap', type=int, default=4096, metavar='N',
                   help='with --src-unpacked: at most N elements are mapped (default 4096; RAM below '
                        'the const window)')
    g.add_argument('--p2-capture', metavar='FILE',
                   help='world: write the bytes the cave flushes to the p2 sink (the payload it sends '
                        'to the partition, read from the claim buffer at each SinkFlush) to FILE, '
                        'and print their count and sha256')
    g.add_argument('--size-dries-after', type=int, metavar='N',
                   help='world: SourceSize answers 0 from its (N+1)th call on (a window that dries up '
                        'mid-gather)')
    g.add_argument('--size-value-at', action='append', default=[], metavar='N:V',
                   help='H1 (probe198c gate): SourceSize answers V (instead of the real window) at its Nth call only (a window of exactly 63 mid-gather)')
    g.add_argument('--pinfo', action='append', default=[], metavar='PART:KEY=VAL',
                   help='PartitionGetInfo override; keys 0 IS_MOUNTED 1 SIZE 2 TYPE 3 STATE '
                        '4 SECTOR_SIZE')
    # R1 / probe196 (2026-10-13): the read-only census world. Every flag opt-in; absent, every run is unchanged.
    g.add_argument('--raw-p2', metavar='SPEC',
                   help='PartitionGetRawSerialSource(1, 2) world model (trap 0xD3; docs/deep/material-2026-10-13/'
                        'M1-graw.md D3): none (handle 0) | zero:N | incr:N (octets 0,1,2.. mod 256) | '
                        'hex:HEXOCTETS | staged141 (the probe141 gather as octets: build/payload/staged_words.json '
                        'words 2.., low octet first). A handle is returned only for device 1, partition 2')
    g.add_argument('--raw-pack', choices=('octet', 'le', 'be'), default='octet',
                   help='SourceMap element layout of the raw source: one octet per element (F207), or two '
                        'octets per element little/big-endian (hypotheses, not facts)')
    g.add_argument('--raw-prime', type=int, default=126, metavar='N',
                   help='the raw source window: SourceSize = min(N, remaining) (M1-graw B2: 126 or 127)')
    g.add_argument('--raw-map-zero', action='store_true', help='SourceMap on the raw source returns 0')
    g.add_argument('--synth-skew', type=int, default=0, metavar='N',
                   help='the cave-SYNTHESISED SinkSlack stub (trap 0x3F) returns N more than the stock one '
                        '(the control-mismatch world)')
    g.add_argument('--synth-noop', action='store_true',
                   help='every cave-SYNTHESISED stub returns at once WITHOUT running its trap (a mis-dispatch that '
                        'comes back: AL, AH and memory untouched)')
    # R2 / probe197 (2026-10-14): the p2 write + read-back world. Every flag opt-in.
    g.add_argument('--raw-from-sink', action='store_true',
                   help='0xD3 returns a source over the bytes the p2 partition sink COMMITTED (flushed) in this run, '
                        'once it was closed with digest SKIP (3); SourceDrop is allowed and the source closes itself '
                        'when exhausted (rule R8: any later call on it is a violation)')
    g.add_argument('--raw-corrupt', metavar='POS[:XOR]', help='flip (XOR, default 0x55) the stream byte at POS')
    g.add_argument('--raw-truncate', type=int, metavar='N', help='the stream is cut to N bytes')
    g.add_argument('--raw-wrapbug', type=int, metavar='K',
                   help='ring-end wrap bug: from stream position 126 on, byte p reads byte p-K')
    g.add_argument('--raw-refuse', action='store_true', help='0xD3 returns 0 even after a good close')
    g.add_argument('--claim-fail-at', action='append', type=int, default=[], metavar='N',
                   help='the Nth SinkClaim (1-based) returns 0xFFFF')
    g.add_argument('--claim-offset', type=int, default=None, metavar='N',
                   help='every SinkClaim on the p2 sink returns offset N (default 0): the cave must add it to SinkMap '
                        '(V07 D2); the capture honours it')
    g.add_argument('--flush-fail-at', action='append', type=int, default=[], metavar='N',
                   help='the Nth SinkFlush (1-based) returns 0 and commits nothing')
    g.add_argument('--erase-ms', type=int, default=0, metavar='MS', help='VmGetClock advances MS across the sink open')
    g.add_argument('--flush-ms', type=int, default=0, metavar='MS', help='VmGetClock advances MS per committed flush')
    g.add_argument('--clock-base', type=int, default=5000, metavar='MS', help='VmGetClock value at t = 0 (32 bit)')
    g.add_argument('--getinfo-fail-at', action='append', type=int, default=[], metavar='N',
                   help='the Nth PartitionGetInfo call (1-based) returns FALSE')
    g.add_argument('--slack', type=int, default=None, metavar='N', help='SinkSlack returns N (default 0x100)')
    g.add_argument('--p2-mounted', type=int, choices=(0, 1),
                   help='IS_MOUNTED(2) before any cave mount (default: the legacy answer, 1)')
    g.add_argument('--p2-automount', action='store_true',
                   help='firmware puts p2 in the union file system by itself')
    g.add_argument('--p2-preloaded', action='store_true',
                   help='the p2 files already exist (a later session, after the erase)')
    g.add_argument('--expect', action='append', default=[], metavar='KEY=VAL',
                   help='assert a result (chunks ended spoken violations rules pending '
                        'swallowed replayed dsp looping); exit 1 on a mismatch')
    g.add_argument('--strict', action='store_true', help='exit 2 on any rule violation')
    g.add_argument('--allow', action='append', default=[], metavar='RULE',
                   help='waive a port-3 rule on purpose (R1..R6), e.g. --allow R1 for the DESIGN '
                        'E4 experiment; waived hits are listed, not counted')
    g.add_argument('--brief', action='store_true',
                   help='world: one line per cave run (trap names, spoken ids, !! rule hits) '
                        'instead of the full trap listing')
    # ---- J-T3 (2026-10-12): failure worlds; every flag defaults to falsy and turns the world on
    g.add_argument('--cancel', choices=('never', 'always'), default=None,
                   help='world: MessageCancelFirst returns FALSE every time (never finds the '
                        'message) or TRUE every time (nothing removed): the STOP failure worlds')
    g.add_argument('--ksink-after-unload', choices=('zero',), default=None,
                   help='world: StreamKalimbaSink(3) returns 0 while no DSP is loaded (the '
                        'counterfactual to probe177 R1, where it stayed nonzero)')
    g.add_argument('--wrong-dsp', action='append', default=[], metavar='MS:DUR',
                   help='world: a TTS-prompt or call DSP replaces sbc_decoder for DUR ms; the '
                        'gate still reads TRUE; rule W1 flags 0x1072 / a rebuild into it')
    g.add_argument('--mid-chunk-1072', action='append', default=[], metavar='MS[:b]',
                   help='world: the STOCK sends 0x1072(8000, b) at MS (default b=0): purge cut, '
                        'level switch (b&2 clear = +18 dB), stale ksink task; not a cave call')
    g.add_argument('--audio-busy', action='store_true',
                   help='probe210 (2026-10-15): model the stock audio-busy word (fn_2f9f2 get, fn_2f9fb set; an opt-in FUNC_RET model), the '
                        '--pause-at disconnect that PARKS while busy is set, and the 0x1080 end-of-tone that clears busy (fn_31ab7); with it no 0x1080 is '
                        'delivered while another chunk is already running (the DSP buffer is refilled: no 30 ms of silence)')
    g.add_argument('--busy-init', default=None, metavar='HEX',
                   help='probe218 (2026-10-16): the audio-busy word starts at this value instead of 0 (needs --audio-busy)')
    g.add_argument('--pause-at', type=int, default=None, metavar='MS',
                   help='probe210: the music is PAUSED at MS: the stock sends the plugin disconnect, conditional on the audio-busy word (needs --audio-busy); '
                        'the DSP unloads --unload-ms after busy is zero')
    g.add_argument('--foreign-tone', action='append', default=[], metavar='MS:DUR',
                   help='world: a stock tone disposes our chain at MS and holds port 3 for DUR ms')
    g.add_argument('--voice-field', action='store_true',
                   help='world: model the stock assistant toggle: every 0x4004 reaching the stock '
                        'arm flips a field (enable/disable request), and while it is set a centre '
                        'SHORT press (--short-id) is converted to 0x4004 (T04 E7/C10)')
    g.add_argument('--short-id', default='4045', help='hex event id of the centre SHORT press for '
                   '--voice-field (default 4045, 02-loop-forever E2)')
    g.add_argument('--field-at', action='append', default=[], metavar='MS:0|1',
                   help='world: an HFP status message sets (1) or clears (0) the voice field')
    g.add_argument('--msg-at', action='append', default=[], metavar='MS:ID',
                   help='deliver a plain MessageSend message with id ID (hex) to the cave task at MS (a STOCK message sent to the busy owner, e.g. 0x7008, probe285)')
    g.add_argument('--dspmsg-at', action='append', default=[], metavar='MS:ID',
                   help='deliver a MESSAGE_FROM_KALIMBA with msg[0]=ID (hex) to the cave handler at MS (a STOCK tone or prompt on our DSP, probe284)')
    g.add_argument('--tone-at', action='append', default=[], metavar='MS',
                   help='BF stock world (opt-in, implies --audio-busy): a stock tone (fn_0de40 -> prompt plugin 0xBD4E) is requested at MS; parked while the audio-busy word is non-zero; '
                        'served: @0x6d1 bit 15 set -> PanicNull at 0x230be = modelled REBOOT (the run stops), clear -> connects, busy 0xBD4E for --tone-ms, then ends (bit 15 cleared)')
    g.add_argument('--tts-at', action='append', default=[], metavar='MS',
                   help='BF stock world (opt-in, implies --audio-busy): a stock TTS prompt is requested at MS; parked while busy; served: busy 0xB195, our DSP and chains torn down '
                        '(StreamKalimbaSink(3) -> 0), @0x6d1 bit 15 left as it is, for --tts-ms')
    g.add_argument('--chain-model', action='store_true',
                   help='BH (opt-in): the stack-true Kalimba model of docs/deep/material-2026-10-19/BG-lifted-stack-audio.md section 12 REPLACES the --ksink-after-unload counterfactual: '
                        'StreamKalimbaSink(p) is never 0, and TransformFromSource(...) is nonzero iff the DAC link chain is alive (made by fn_1f04c, a stock DSP that is up; destroyed by '
                        'fn_1f12b, a KalimbaLoad, a KalimbaPowerOff, a DSP unload, a stock TTS). --chain-at MS:0|1 sets it by hand')
    g.add_argument('--chain-at', action='append', default=[], metavar='MS:0|1', help='BH: with --chain-model, set the DAC link chain dead (0) or alive (1) at MS')
    g.add_argument('--tone-ms', type=int, default=400, metavar='MS', help='BF: how long a served stock tone holds the busy word (default 400)')
    g.add_argument('--tts-ms', type=int, default=3000, metavar='MS', help='BF: how long a served stock TTS prompt holds the busy word (default 3000)')
    g.add_argument('--clock-jump', action='append', default=[], metavar='MS:EXTRA',
                   help='probe334: from world time MS on, VmGetClock reads EXTRA ms more (a model of a processor stall: the next timer message is delivered EXTRA ms late as seen by the cave)')
    g.add_argument('--mem-at', action='append', default=[], metavar='MS:ADDR=VAL',
                   help='world: write RAM at MS (hex ADDR=VAL), e.g. 3000:59e=6 for a sinkState '
                        'change (ADK sink_states.h: 3 connected, 5 incoming call, 6 active call '
                        'SCO, 13 A2DP streaming)')
    g.add_argument('--enter', choices=('hook', 'handler'), default='hook',
                   help='handler: enter the cave TaskData handler directly (a second entry) '
                        'with AL = the task and AH = --id (single-run mode)')
    g.add_argument('--id', help='hex MessageId for --enter handler')
    g.add_argument('--task', help='hex TaskData data address (default: cave word + 1)')
    g.add_argument('--frame', action='append', default=[], metavar='SLOT=VAL',
                   help='preset a caller-frame word at Y+SLOT (SLOT may be negative) before entry')
    g.add_argument('--x', help='hex X on entry')
    g.add_argument('--y', help='hex Y on entry (default 0x%04X)' % FRAME)
    g.add_argument('--show', action='append', default=[], metavar='ADDR[:N]',
                   help='print N data words at ADDR after the run (cave state words)')
    args = ap.parse_args()
    if args.tone_at or args.tts_at:
        args.audio_busy = True               # BF: the stock world parks on the audio-busy word
    world_flags = (args.tone_at or args.tts_at or args.world or args.loop or args.press or args.press_gap or args.pending
                   or args.once or args.stock_prompt or args.bt_teardown_at is not None
                   or args.unload_at is not None or args.music_resume_at is not None
                   or args.fs_add or args.src_window or args.pinfo or args.expect
                   or args.raw_p2 is not None or args.synth_skew or args.getinfo_fail_at
                   or args.slack is not None or args.synth_noop or args.raw_from_sink or args.claim_fail_at
                   or args.flush_fail_at or args.erase_ms or args.flush_ms or args.claim_offset is not None
                   or args.p2_mounted is not None or args.p2_automount or args.p2_preloaded
                   or args.chunk_ms or args.music == 'paused' or args.tail_ms or args.brief
                   or args.allow or args.cancel or args.ksink_after_unload or args.wrong_dsp
                   or args.mid_chunk_1072 or args.foreign_tone or args.mem_at or args.dspmsg_at or args.msg_at
                   or args.voice_field or args.field_at or args.src_unpacked or args.p2_capture
                   or args.size_dries_after is not None or args.size_value_at or args.drop_adv is not None or args.map_shift_from
                   or args.map_fail_pos is not None or args.src_hijunk or args.src_hibyte or args.map_live or args.map_lead or args.map_trunc or args.map_lead_rule or args.map_lead_last or args.map_lead_ndrop)
    if args.events is None:
        args.events = 400 if world_flags else 10
    if world_flags and not args.dsp:
        args.dsp = 'up'          # the loop needs a DSP model; --dsp down still wins

    probe_path = args.probe if args.probe.endswith('.json') else None
    words_json = probe_path or os.path.join(ROOT, 'build/hook/%s_words.json' % args.probe)
    patch = json.load(open(words_json))
    cave = int(args.entry, 16) if args.entry else min(int(k, 16) for k in patch)
    pmap = json.loads(args.pmap) if args.pmap else None
    vm, state, stubs, trapnums = build(words_json, fail=set(args.fail), pmap=pmap, dac_guard=args.dac_guard)
    if args.staged:
        if args.staged_legacy:
            sw = json.load(open(args.staged))
            for k, v in enumerate(sw):
                fw = 32 * (k // 14) + 11 + (k % 14)  # the staging layout (probe141)
                state['srcbuf'][(SRCMAP + fw) & 0xFFFF] = v & 0xFFFF
            print('staged %d words behind SourceMap (0x%04X, periodic layout)' % (len(sw), SRCMAP))
        else:
            if args.staged.lower().endswith('.json'):
                sw = [int(x) & 0xFF for x in json.load(open(args.staged))]
            else:
                sw = list(open(args.staged, 'rb').read())
            last = 64 * ((len(sw) - 1) // 28) + 18 + ((len(sw) - 1) % 28) if sw else 0
            if last >= CLAIM - SRCMAP:
                print('--staged: %d bytes need map elements up to %d but the flat window holds %d; use '
                      'the world model (--fs-add NowSpeakTTS/data_us=@FILE --src-unpacked) or '
                      '--staged-legacy' % (len(sw), last, CLAIM - SRCMAP))
                return 2
            for k, v in enumerate(sw):
                e = 64 * (k // 28) + 18 + (k % 28)       # FIRST = 9 words = byte 18 of the period
                state['srcbuf'][(SRCMAP + e) & 0xFFFF] = v
            print('staged %d bytes behind SourceMap (0x%04X): one byte per element, 28 of every 64 '
                  '(elements 18..45), %d periods' % (len(sw), SRCMAP, -(-len(sw) // 28)))
        # the claim helper: Bose's fn_12e1a, short-circuited -- the claimed
        # window ADVANCES so the virtual claim buffer accumulates the payload
        def fn12e1a_short(trap, ahal, a2):
            n = (ahal >> 16) & 0xFFFF
            p = state['claim_base'] & 0xFFFF
            state['claim_base'] = (p + n) & 0xFFFF
            state['claim_dst'] = p            # outstanding claim, consumed by memmove
            return (0, p)
        vm.FUNC_RET[0x12E1A] = fn12e1a_short
    names = {v: k for k, v in trapnums.items()}
    for spec in args.fail_after:
        tname, _, n = spec.partition('=')
        base = vm.STUB_RET.get(trapnums[tname]); cnt = {'n': 0}
        def late(trap, ahal, a2, base=base, cnt=cnt, n=int(n)):
            cnt['n'] += 1
            if cnt['n'] >= n:
                return (0, 0)
            return base(trap, ahal, a2) if callable(base) else base
        vm.STUB_RET[trapnums[tname]] = late
    dsp = install_dsp(vm, trapnums, args.dsp == 'up', set(args.fail),
                      {int(x, 16) for x in args.dsp_refuse}) if args.dsp else None

    print('%s: %d words, cave at 0x%05X' % (args.probe, len(patch), cave))
    synth = state.get('synth') or {}
    for a_, (n_, kind_, ln_) in sorted(synth.items()):
        print('  SYNTHESISED TRAP STUB at 0x%05X: trap 0x%02X %s, %s tail, %d words'
              % (a_, n_, names.get(n_, '?'), kind_, ln_))
        if n_ > caveguard.SYNTH_MAX_TRAP:
            print('  HAZARD  trap 0x%02X is above the stack dispatcher bound 0x%X (T01/T12): the '
                  'call faults on hardware; the model returns as for any trap' % (
                      n_, caveguard.SYNTH_MAX_TRAP))
        if n_ in caveguard.UNIMPLEMENTED_TRAPS:
            print('  HAZARD  trap 0x%02X is an UNIMPLEMENTED slot of the stack trap table ((M,A) = (0,0), '
                  'T01 C2): the dispatcher takes the fault path on hardware; the model returns as for '
                  'any trap' % n_)
    for a_, op_ in caveguard.stray_tail_ops(vm.code, vm.nofold, synth):
        print('  HAZARD  opcode 0x%02X (%s) at 0x%05X outside a recognised trap stub: the '
              'emulator STOPS if it runs it (round 3: it used to mis-run it as a pseudo-TRAP), and '
              'the tail is a form never run from a cave'
              % (op_, 'ld XH,@(n,Y)' if op_ == 0x0E else 'bra @abs', a_))
    for a_, op_, t_ in caveguard.tail_branches(vm.code, vm.nofold):
        print('  HAZARD  %s at 0x%05X targets the stock trap tail 0x%03X: control would enter the tail '
              'with a link in X (a code address, not a trap number) -- above the dispatcher bound 0x%X, '
              'a VM fault on hardware (V01 D1); the emulator stops if it runs it'
              % ('bsr' if op_ == 0x9C else 'bra' if op_ == 0xE0 else 'branch', a_, t_,
                 caveguard.SYNTH_MAX_TRAP))
    for h in hazards(patch, synth, int(args.caller_frame, 0) if args.caller_frame else None):
        print('  %s' % h if h.startswith('NOTE') else '  HAZARD  %s' % h)
    # A trap with no entry in DEFAULT_RETURNS is a silent hole: `--fail` cannot
    # reach it, and the cave reads whatever AL happened to hold rather than a
    # modelled return. probe75 hit exactly that with KalimbaSendMessage, and
    # the run looked fine. Report it instead.
    for name in args.fail:
        # MODELLED_SEPARATELY are traps whose return is a closure rather than a
        # DEFAULT_RETURNS constant, so they honour --fail without appearing in that
        # table. Checking only DEFAULT_RETURNS warned that `--fail malloc` had been
        # ignored when it had in fact been applied -- a false alarm that invites
        # someone to discard a perfectly good bail test.
        if name not in DEFAULT_RETURNS and name not in MODELLED_SEPARATELY:
            print('  WARNING --fail %s has no modelled return; it was ignored'
                  % name)
    if args.fail:
        print('forced failures: %s' % ', '.join(args.fail))
    if args.ah:
        vm.AH = int(args.ah, 16)
        print('entry AH = 0x%04X' % vm.AH)
    if args.al:
        vm.AL = int(args.al, 16)
        print('entry AL = 0x%04X' % vm.AL)
    for spec in args.mem:
        a, _, v = spec.partition('=')
        vm.wr(int(a, 16), int(v, 16) & 0xFFFF)
        print('preset @0x%04X = 0x%04X' % (int(a, 16), int(v, 16) & 0xFFFF))
    for spec in args.frame:                 # B2: caller-frame state at the entry
        a, _, v = spec.partition('=')
        vm.wr((FRAME + int(a, 0)) & 0xFFFF, int(v, 16) & 0xFFFF)
        print('preset frame @(%d,Y) = 0x%04X' % (int(a, 0), int(v, 16) & 0xFFFF))
    if args.x:
        vm.X = int(args.x, 16)
        print('entry X = 0x%04X' % vm.X)
    if args.y:
        vm.Y = int(args.y, 16)
        print('entry Y = 0x%04X' % vm.Y)
    if args.caller_frame:
        # R05: the CALLER's saved return address is at its slots K-2 and K-1, i.e. data addresses
        # entry-Y + K-2 and K-1. A cave store there destroys the return path; the model stops.
        _k = int(args.caller_frame, 0)
        _ret = {(vm.Y + _k - 2) & 0xFFFF, (vm.Y + _k - 1) & 0xFFFF}
        _wr0 = vm.wr
        _y0 = vm.Y

        def _guarded_wr(wa, v, _wr0=_wr0, _ret=_ret, _k=_k, _y0=_y0):
            if (wa & 0xFFFF) in _ret:
                raise RuntimeError('store to %#06x = the CALLER\'s saved return address (caller '
                                   '`enterl -%d`, slot %d): the hook would return into the weeds'
                                   % (wa & 0xFFFF, _k, (wa & 0xFFFF) - _y0))
            _wr0(wa, v)
        vm.wr = _guarded_wr
        print('caller-frame guard: stores to %s stop the run (caller enterl -%d)'
              % (', '.join('%#06x' % x for x in sorted(_ret)), _k))
    # B2: the cave's TaskData is the two words after its ENTRY word (CAVE+1, CAVE+2), as in
    # every probe since 145 (so pass --entry for a cave that spans a lower region); its data address is what MessageSendLater / MessageKalimbaTask take
    task_addr = (int(args.task, 16) if args.task else
                 (CONST_DATA_BASE + (cave + 1 - CODE_WORDS)) & 0xFFFF)
    if world_flags:
        import cavesim_world
        me = sys.modules[__name__]
        w = cavesim_world.World(me, vm, trapnums, names, args, state, dsp)
        w.task = task_addr
        w.install()
        h = handler_of(vm, task_addr)
        handler = h if h in {int(k, 16) for k in patch} else None
        print('world model on: cave task %#06x -> handler %s; DSP %s; %s'
              % (task_addr, '0x%05X' % h if handler else 'none (%#x is not a cave word)' % h,
                 'loaded' if dsp['loaded'] else 'down', 'once' if args.once else 'clocked'))
        rc = w.run(cave, int(args.al, 16) if args.al else 0x4004, handler)
        w.summary()
        rc = w.check_expect() or rc
        show_words(vm, args.show)
        if rc == 0 and args.strict and w.violations:
            return 2
        return rc
    if args.enter == 'handler':
        h = handler_of(vm, task_addr)
        vm.AL, vm.AH = task_addr, int(args.id or '0', 16)
        vm.wr(FRAME, MSGBUF)
        cave = h
        print('second entry: handler 0x%05X, AL = task %#06x, AH = id %#06x' % (h, vm.AL, vm.AH))
    try:
        why, pc = vm.run(cave, max_steps=args.steps)
    except RuntimeError as e:
        print('STOPPED: %s' % e)
        return 1

    if vm.calls_seen:
        print('')
        print('prompt ids spoken, in order:')
        for _a, _v in vm.calls_seen:
            if _a == SPEAK_ADDR:
                print('  0x%02X  spoken by the prompt engine' % (_v & 0xFFFF))

    print('\ntrap calls, in order:')
    for t, ahal, a2 in vm.traps:
        print('  %-24s AL=%#06x AH=%#06x  @(0,Y)=%#06x @(1,Y)=%#06x'
              % (names.get(t, 'trap_%02x' % t), ahal & 0xFFFF, ahal >> 16,
                 (a2 >> 16) & 0xFFFF, a2 & 0xFFFF))
    for a, ahal in vm.calls_seen:
        print('  (back-call 0x%05X)' % a)

    print('\nended: %s at 0x%05X   AL = %#06x' % (why, pc, vm.AL))
    for p, size in state.get('blocks', []):
        shown = size if args.dump else min(size, 12)
        vals = [vm.rd(p + i) for i in range(shown)]
        if args.dump:
            # Full dump, so the bytes the REAL lifted generator produced can be decoded
            # and compared against tools/noisespec.py's independent model. Two
            # implementations agreeing is what makes a quoted spectrum trustworthy.
            print('buffer 0x%04X..+%d, all %d words:' % (p, size, size))
            for i in range(0, shown, 16):
                print('  +%-4d %s' % (i, ' '.join('%04x' % v for v in vals[i:i + 16])))
        else:
            print('buffer 0x%04X..+%d: %s%s'
                  % (p, size, ' '.join('%04x' % v for v in vals),
                     ' ...' if size > 12 else ''))
        nz = sum(1 for i in range(size) if vm.rd(p + i))
        print('  %d of %d words non-zero' % (nz, size))
    if dsp is not None:
        rc = dsp_session(vm, dsp, names, trapnums, args, state)
        show_words(vm, args.show)
        return rc
    show_words(vm, args.show)
    return 0


if __name__ == '__main__':
    sys.exit(main())
