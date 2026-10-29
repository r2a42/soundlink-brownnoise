#!/usr/bin/env python3
"""caveasm: emit VM trap calls with the VERIFIED ABI.

Every wrong-argument bug in this project (probes 39-47, 53) came from
hand-writing trap call sequences. This module generates them instead, from
the convention established by compiling and linking probe apps with the
ADK and disassembling the result (build/convprobe, build/sustainprobe).

ABI, verified -- docs/trap-abi.md and docs/message-task-abi.md:

    arg1        -> AL
    arg2        -> AH
    args 3..n   -> @(0,Y), @(1,Y), ... in order
    a 32-bit argument takes two consecutive slots, HIGH word first
    return      <- AL, always

A callback is the mirror image: it receives arg1 in AL, arg2 in AH, and
arg3 at @(n,Y) after its own `enterl #n`.

Usage with the existing cave assemblers, which expose W() and BSR():

    import caveasm as ca
    ca.call2(W, BSR, ca.STUB['SinkClaim'], al=('slot',2), ah=('imm',32))
    ca.send_later(W, BSR, ca.const_addr(TASK_A), 0xDF01, delay_ms=20)

Arguments are ('imm', value) or ('slot', n) meaning @(n,Y); a stack
argument may also be ('long', value32).
"""

import json
import os

# --- Bose vm.app geometry (from its 24-word header; docs/message-task-abi.md)
HDR_WORDS = 24             # `a` space = file word index - HDR_WORDS
CODE_WORDS = 236514        # code occupies a = 0 .. CODE_WORDS-1
CONST_WORDS = 24475        # const occupies a = CODE_WORDS .. +CONST_WORDS-1
CONST_DATA_BASE = 0x7400   # where the constant pool is mapped in data space
GLOBALS_DATA_BASE = 0x0500

# Useful firmware constants, from the ADK headers
D_IMMEDIATE = 0xFFFFFFFF            # message.h: (Delay)-1
MESSAGE_MORE_DATA = 0x8021          # app/message/system_message.h
MESSAGE_MORE_SPACE = 0x8022
VM_SOURCE_MESSAGES = 0x0002         # app/stream/stream_if.h
VM_SINK_MESSAGES = 0x0004
VM_MESSAGES_ALL, VM_MESSAGES_SOME, VM_MESSAGES_NONE = 0, 1, 2
STREAM_CODEC_OUTPUT_RATE = 0x0301
STREAM_CODEC_OUTPUT_GAIN = 0x0303   # range 0..22


def const_addr(a):
    """Data-space address of a const-region word at project address `a`.

    The cave lives in const zero-padding, and const is mapped into the data
    address space at 0x7400 -- so anything the cave needs to be *pointed
    at* (a TaskData, a table) can simply be flashed beside it.
    """
    if not CODE_WORDS <= a < CODE_WORDS + CONST_WORDS:
        raise ValueError('a=%#x is not in the const region' % a)
    return CONST_DATA_BASE + (a - CODE_WORDS)


def taskdata_words(a_handler):
    """The two words of a TaskData pointing at a cave handler at `a_handler`.

    A TaskData is { hwrd(handler), lwrd(handler) } -- the handler's
    code-relative word address as a 32-bit pair, high word first.
    """
    return [(a_handler >> 16) & 0xFFFF, a_handler & 0xFFFF]


def _load_stubs():
    """Trap name -> Bose stub address, all 151 (tools/gen-stub-table.py).

    Names come from BlueLab 7.3.1's trap table, which is the one the
    speaker's image uses. Reading it with BlueLab 7.4's table -- which the
    project did until 2026-09-30 -- mis-names 173 traps and is what made
    probes 46, 47 and 52-56 call the wrong ones (docs/trap-numbering.md).
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'bose-stubs.json')
    with open(path) as f:
        return json.load(f)


STUB = _load_stubs()
STUB['MessageStreamTaskFromSink'] = STUB['MessageSinkTask']   # ADK 4.4 name

# ---- the cave-carried trap stub (J-T12 spec S4, applied by the round-3 tool owner, 2026-10-12) ----
# A trap that has NO stub in vm.app (151 stubs; the stack implements ~66 more) can only be called
# through a stub the CAVE carries: a stock stub is `enterl -3 ; ld X,#n ; bra 0x291`, and from the
# cave `bra 0x291` would be a 3-word bra (253,836 words away) which Bose never emits, so the cave
# carries the five tail words itself (the ADK's own common_trap_code, T12 section 2). NEVER RUN ON
# HARDWARE. The stub is GENERATED here, never hand-written (the project's lesson); the recogniser
# and the gate are in tools/caveguard.py, the model in tools/cavesim.py.
COMMON_TAIL_A = 0x291                                      # the stock tail, vm.app code words 0x291..0x295
COMMON_TAIL = (0x002B, 0xFC19, 0xFF2B, 0xFF0E, 0xFDE1)     # st X,@(0,Y); ld X,@0xFFFC; st X,@(-1,Y); ld XH,@(-1,Y); bra @0xFFFD
ENTERL_3 = 0xFD0B                                          # SHARED_TRAP_HANDLER_STACK_USAGE = 3 (native_if.inc:51)
# traps that exist in the stack but have no vm.app stub; name -> number. Deliberately NOT in
# bose-stubs.json (the 151 real stubs) and NOT in STUB: a name here is reachable only through
# synth_stub_words.
SYNTH_TRAP = {'PartitionGetRawSerialSource': 0xD3}


def synth_stub_words(trap):
    """`enterl -3 ; ld X,#trap ; <tail>`: a stock stub with its `bra 0x291` replaced by the tail
    itself. Emit as ONE W(*words) item (so no writable-band boundary splits it), then BSR(label) to
    call it like a stock stub. 0xD3 -> FD0B 0100 D318 002B FC19 FF2B FF0E FDE1 (8 words); 0x3F ->
    FD0B 3F18 002B FC19 FF2B FF0E FDE1 (7 words)."""
    return [ENTERL_3] + imm_words(trap, 0x18) + list(COMMON_TAIL)


# Opcodes that END a straight-line run in a cave: rts 0xE2, leavel 0x0F, and (J-T12 S7) `bra @abs`
# 0xE1, the last word of a synthesised stub. An assembler's layout engine must not reserve a
# connector word after an item that ends in one of these; every assembler carries its own copy of
# needs_follow() (assemble_probe178 and later: `(item[1][-1] & 0xFF) not in (0xE2, 0x0F)`), which
# ignores 0xE1 and so wastes a word after a stub. A new assembler that carries a stub should call
# this instead.
TERMINATOR_OPS = (0xE2, 0x0F, 0xE1)


def needs_follow(item):
    """Layout helper shared by the probe assemblers: does `item` fall through into the next one?
    item = ("region",) | ("bsr", label) | ("br", opcode, label) | ("words", [..]). A bsr always
    returns to the next word; a conditional br may; an unconditional `bra` (0xE0) and a run ending
    in rts / leavel / bra @abs do not."""
    k = item[0]
    if k == "region":
        return False
    if k == "bsr":
        return True
    if k == "br":
        return item[1] != 0xE0
    return (item[1][-1] & 0xFF) not in TERMINATOR_OPS

OP_LD_AL_IMM, OP_LD_AH_IMM = 0x14, 0x10
OP_LD_AL_SLOT, OP_ST_AL_SLOT = 0x17, 0x27
OP_LD_AH_SLOT, OP_ST_AH_SLOT = 0x13, 0x23


def _sext8(b):
    return b - 256 if b & 0x80 else b


def fold(prefixes, final):
    """The decoder's signed prefix chain (docs/xap-opcodes.md)."""
    v = 0
    for a in prefixes:
        v = (v + _sext8(a)) << 8
    return v + _sext8(final)


def imm_words(value, opcode):
    """Shortest word sequence loading `value` with `opcode`. Verified against
    the compiler: ld AH,#0x4222 -> [0x4200, 0x2210]."""
    v = value if value < 0x8000 else value - 0x10000     # treat as signed 16
    if -128 <= v <= 127:
        return [((v & 0xFF) << 8) | opcode]
    for a in range(-128, 128):
        if a == 0:
            continue
        b = v - a * 256
        if -128 <= b <= 127:
            return [(a & 0xFF) << 8, ((b & 0xFF) << 8) | opcode]
    for a in range(-128, 128):
        if a == 0:
            continue
        for b in range(-128, 128):
            if b == 0:
                continue
            c = v - a * 65536 - b * 256
            if -128 <= c <= 127:
                return [(a & 0xFF) << 8, (b & 0xFF) << 8,
                        ((c & 0xFF) << 8) | opcode]
    raise ValueError('cannot encode immediate %#x' % value)


def _load(W, spec, imm_op, slot_op):
    kind, val = spec
    if kind == 'imm':
        W(*imm_words(val, imm_op))
    elif kind == 'slot':
        W((val << 8) | slot_op)
    else:
        raise ValueError('bad operand spec %r' % (spec,))


def load_al(W, spec):
    _load(W, spec, OP_LD_AL_IMM, OP_LD_AL_SLOT)


def load_ah(W, spec):
    _load(W, spec, OP_LD_AH_IMM, OP_LD_AH_SLOT)


def store_al(W, slot):
    W((slot << 8) | OP_ST_AL_SLOT)


def store_ah(W, slot):
    W((slot << 8) | OP_ST_AH_SLOT)


def _stack_slots(stack):
    """Expand stack arguments into (slot, spec) pairs in EMISSION order.

    Verified against both probes' compiler output: each argument is stored
    in turn, and a 32-bit argument stores its LOW word (the higher slot)
    before its HIGH word (the lower slot).
    """
    out, i = [], 0
    for spec in stack:
        kind, val = spec
        if kind == 'long':
            out.append((i + 1, ('imm', val & 0xFFFF)))
            out.append((i, ('imm', (val >> 16) & 0xFFFF)))
            i += 2
        else:
            out.append((i, spec))
            i += 1
    return out


def calln(W, BSR, stub, al, ah=None, stack=(), stage='AH'):
    """A trap call with any number of arguments.

    al/ah are arg1/arg2; `stack` holds args 3.. as specs, where ('long', v)
    is a 32-bit value occupying two slots. `stage` picks the scratch
    register used to move stack arguments -- both 'AH' (the convprobe
    emission) and 'AL' (the sustainprobe emission) are verified compiler
    output. AL is loaded last, so staging through it is safe; a ('slot', n)
    argument is read after the stack slots are written, so do not pass one
    that the call's own stack arguments overwrite.
    """
    load = load_ah if stage == 'AH' else load_al
    store = store_ah if stage == 'AH' else store_al
    for slot, spec in _stack_slots(stack):
        load(W, spec)
        store(W, slot)
    if ah is not None:
        load_ah(W, ah)
    load_al(W, al)
    BSR(stub)


def call1(W, BSR, stub, al):
    """1-argument trap: arg -> AL. Return in AL."""
    calln(W, BSR, stub, al)


def call2(W, BSR, stub, al, ah):
    """2-argument trap: arg1 -> AL, arg2 -> AH. Return in AL."""
    calln(W, BSR, stub, al, ah)


def call3(W, BSR, stub, al, ah, arg3):
    """3-argument trap: arg1 -> AL, arg2 -> AH, arg3 -> @(0,Y)."""
    calln(W, BSR, stub, al, ah, [arg3])


def call3_long(W, BSR, stub, al, ah, arg3_32):
    """3-argument trap whose third argument is 32-bit:
    @(0,Y)=high, @(1,Y)=low. Matches the compiler's SinkConfigure."""
    calln(W, BSR, stub, al, ah, [('long', arg3_32)])


def send_later(W, BSR, task_addr, msg_id, delay_ms, message=0):
    """MessageSendLater(task, id, message, delay) -- the sustain timer.

    `task_addr` is a data-space address; for a cave's own TaskData use
    const_addr(a_task). Delay is in milliseconds; D_IMMEDIATE sends now.
    """
    calln(W, BSR, STUB['MessageSendLater'],
          al=('imm', task_addr), ah=('imm', msg_id),
          stack=[('imm', message), ('long', delay_ms)], stage='AL')


if __name__ == '__main__':
    # Self-test against sequences the ADK compiler actually emitted.
    out = []
    W = lambda *ws: out.extend(ws)
    BSR = lambda stub: out.append(('bsr', stub))

    assert imm_words(0x4222, OP_LD_AH_IMM) == [0x4200, 0x2210], 'ld AH,#0x4222'
    assert imm_words(0x3111, OP_LD_AH_IMM) == [0x3100, 0x1110], 'ld AH,#0x3111'
    assert imm_words(0x5333, OP_LD_AH_IMM) == [0x5300, 0x3310], 'ld AH,#0x5333'
    assert imm_words(0x7555, OP_LD_AL_IMM) == [0x7500, 0x5514], 'ld AL,#0x7555'
    assert imm_words(3, OP_LD_AL_IMM) == [0x0314], 'ld AL,#3'
    assert imm_words(0, OP_LD_AH_IMM) == [0x0010], 'ld AH,#0'
    assert imm_words(0xFFFB, OP_LD_AL_IMM) == [0xFB14], 'ld AL,#0xfffb (-5)'
    # sustainprobe immediates
    assert imm_words(0xB222, OP_LD_AL_IMM) == [0xB200, 0x2214], 'ld AL,#0xb222'
    assert imm_words(0x0500, OP_LD_AL_IMM) == [0x0500, 0x0014], 'ld AL,#0x500'
    assert imm_words(0x7401, OP_LD_AL_IMM) == [0x7400, 0x0114], 'ld AL,#0x7401'
    assert imm_words(0xA111, OP_LD_AH_IMM) == [0xA100, 0x1110], 'ld AH,#0xa111'

    del out[:]; store_ah(W, 0); assert out == [0x0023], 'st AH,@(0,Y)'
    del out[:]; store_al(W, 2); assert out == [0x0227], 'st AL,@(2,Y)'
    del out[:]; load_al(W, ('slot', 2)); assert out == [0x0217], 'ld AL,@(2,Y)'

    # convprobe: StreamAudioSink(CODEC=3, INSTANCE_0=0, CHANNEL_A=0)
    del out[:]; call3(W, BSR, STUB['StreamAudioSink'],
                      ('imm', 3), ('imm', 0), ('imm', 0))
    assert out == [0x0010, 0x0023, 0x0010, 0x0314,
                   ('bsr', 0x162)], out

    # convprobe: SinkConfigure(dac, 0x3111, 0x4222), sink held in a slot
    del out[:]; call3_long(W, BSR, STUB['SinkConfigure'],
                           ('slot', 1), ('imm', 0x3111), 0x4222)
    assert out == [0x4200, 0x2210, 0x0123,        # ld AH,#0x4222 ; st AH,@(1,Y)
                   0x0010, 0x0023,                # ld AH,#0      ; st AH,@(0,Y)
                   0x3100, 0x1110,                # ld AH,#0x3111
                   0x0117, ('bsr', 0x11A)], out   # ld AL,@(1,Y)

    # sustainprobe: MessageSendLater(&g_task=0x500, 0xA111, 0, 0xB222).
    # Identical to the compiler's emission except that we load AH before AL
    # and it loaded AL before AH -- free scheduling, since neither load
    # touches the other register. We always put AL last so that staging
    # stack arguments through AL can never clobber arg1.
    del out[:]; send_later(W, BSR, 0x0500, 0xA111, 0xB222)
    assert out == [0x0014, 0x0027,                # ld AL,#0      ; st AL,@(0,Y)
                   0xB200, 0x2214, 0x0227,        # ld AL,#0xb222 ; st AL,@(2,Y)
                   0x0014, 0x0127,                # ld AL,#0      ; st AL,@(1,Y)
                   0xA100, 0x1110,                # ld AH,#0xa111   arg2
                   0x0500, 0x0014,                # ld AL,#0x500    arg1
                   ('bsr', STUB['MessageSendLater'])], out

    # sustainprobe: the same call with the Task in the flash const pool
    del out[:]; send_later(W, BSR, 0x7401, 0xA999, 0xBAAA)
    assert out == [0x0014, 0x0027, 0xBB00, 0xAA14, 0x0227, 0x0014, 0x0127,
                   0xAA00, 0x9910, 0x7400, 0x0114,
                   ('bsr', STUB['MessageSendLater'])], out

    # sustainprobe: MessageStreamTaskFromSink(dac, &g_task), SinkSlack(dac)
    del out[:]; call2(W, BSR, STUB['MessageSinkTask'],
                      al=('slot', 3), ah=('imm', 0x0500))
    assert out == [0x0500, 0x0010, 0x0317, ('bsr', 0x0D2)], out
    del out[:]; call1(W, BSR, STUB['SinkSlack'], ('slot', 3))
    assert out == [0x0317, ('bsr', 0x0DA)], out

    # geometry and the stub table
    assert const_addr(0x3E21D) == 0xBA3B, 'cave data address'
    assert taskdata_words(0x3E21D) == [0x0003, 0xE21D], 'TaskData words'
    # BlueLab 7.3.1 numbering -- see docs/trap-numbering.md. The four on the
    # first line are the ones the project had WRONG until 2026-09-30.
    assert STUB['StreamAudioSink'] == 0x162 and STUB['SinkConfigure'] == 0x11A
    assert STUB['StreamKalimbaSink'] == 0x1B4 and STUB['KalimbaSendMessage'] == 0x1C3
    assert STUB['PanicNull'] == 0x042 and STUB['SinkClaim'] == 0x0DE
    assert STUB['MessageSendLater'] == 0x062 and STUB['SinkSlack'] == 0x0DA

    # J-T12 (S4): the synthesised trap stub, generated and pinned to T12 section 4's exact words
    assert synth_stub_words(0xD3) == [0xFD0B, 0x0100, 0xD318, 0x002B, 0xFC19, 0xFF2B, 0xFF0E, 0xFDE1],         'trap 0xD3 stub'
    assert synth_stub_words(0x3F) == [0xFD0B, 0x3F18, 0x002B, 0xFC19, 0xFF2B, 0xFF0E, 0xFDE1],         'control stub 0x3F'
    assert synth_stub_words(0x100) == [0xFD0B, 0x0100, 0x0018, 0x002B, 0xFC19, 0xFF2B, 0xFF0E,
                                       0xFDE1], 'stub 0x100 (built only to be refused)'
    assert 0xD3 not in STUB.values() and 'PartitionGetRawSerialSource' not in STUB
    assert SYNTH_TRAP['PartitionGetRawSerialSource'] == 0xD3
    # needs_follow: a stub (ends in bra @abs 0xE1) does not fall through; rts / leavel do not either
    assert not needs_follow(("w", synth_stub_words(0xD3)))
    assert not needs_follow(("w", [0xF80F])) and not needs_follow(("w", [0x00E2]))
    assert needs_follow(("w", [0x0027])) and needs_follow(("bsr", "X"))
    assert needs_follow(("br", 0xF0, "X")) and not needs_follow(("br", 0xE0, "X"))
    print('caveasm self-test: %d stubs, all encodings match compiler output'
          % len(STUB))
