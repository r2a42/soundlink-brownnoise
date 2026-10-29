# VM trap ABI — verified by compiler, not inference

> **CORRECTION, 2026-09-30 (later): every stub ADDRESS in this file's
> table below is wrong.** The names were taken from BlueLab 7.4's trap
> table; the speaker's image is BlueLab 7.3, and 173 traps are numbered
> differently. The argument conventions in this file are unaffected —
> they came from compiling and linking, not from the name table. Use
> `docs/trap-stub-table.md` / `tools/bose-stubs.json` for addresses and
> read `docs/trap-numbering.md` for what this invalidates.

> **Continued in `docs/message-task-abi.md`** (2026-09-30, a second probe
> app): the same method extended to four arguments, to *incoming* arguments
> in a callback, to the layout of a `TaskData`, and to where the constant
> pool lives in the data address space. The complete 151-entry stub table
> is in `docs/trap-stub-table.md` and `tools/bose-stubs.json`.

**2026-09-30.** Established by compiling and **linking** a probe app with
the ADK (`build/convprobe/`), then disassembling the resulting `vm.app`.
Each call used a distinctive magic constant so it is identifiable in the
output. This supersedes every earlier convention claim in this project,
including two of my own that were wrong.

## The rules

| form | arg 1 | arg 2 | arg 3 | return |
|---|---|---|---|---|
| 1-argument trap | **AL** | — | — | **AL** |
| 2-argument trap | **AL** | **AH** | — | **AL** |
| 3-argument trap | **AL** | **AH** | **`@(0,Y)`** | **AL** |
| 3-arg with 32-bit arg3 | **AL** | **AH** | `@(0,Y)`=high, `@(1,Y)`=low | **AL** |

Verified emissions:

```
StreamAudioSink(CODEC=3, INSTANCE_0=0, CHANNEL_A=0)      3 args
    ld AH,#0x0 ; st AH,@(0,Y)      arg3
    ld AL,#0x3                     arg1   (AH already 0 = arg2)
    bsr <stub> ; st AL,@0x500      return in AL

SinkConfigure(dac, 0x3111, 0x4222)                        3 args, 32-bit value
    ld AH,#0x4222 ; st AH,@(1,Y)   arg3 low
    ld AH,#0x0    ; st AH,@(0,Y)   arg3 high
    ld AH,#0x3111                  arg2   (AL still holds the sink = arg1)
    bsr <stub>

SinkClaim(dac, 0x5333)     ld AL,@dac ; ld AH,#0x5333 ; bsr     2 args
SinkFlush(dac, 0x6444)     ld AL,@dac ; ld AH,#0x6444 ; bsr     2 args
SinkMap(dac)               ld AL,@dac ; bsr                     1 arg
StreamKalimbaSink(0x7555)  ld AL,#0x7555 ; bsr                  1 arg
StreamSinkFromSource(src)  ld AL,@src ; bsr                     1 arg
StreamConnect(src, sink)   ld AL,@src ; ld AH,@sink ; bsr        2 args
StreamConfigure(k, v)      ld AL,#k ; ld AH,#v ; bsr             2 args
```

## Verified trap numbers and Bose stub addresses

| trap | name | Bose stub |
|---|---|---|
| 0x07 | PanicNull | 0x42 |
| 0x40 | SinkClaim | 0xDE |
| 0x41 | SinkMap | 0xE2 |
| 0x42 | SinkFlush | 0xE6 |
| 0x4B | StreamConnect | 0x106 |
| 0x50 | ~~StreamConfigure~~ **SinkConfigure** | **0x11A** |
| 0x52 | ~~SinkConfigure~~ **StreamSinkFromSource** | 0x122 |
| 0x53 | ~~StreamSourceFromSink~~ **SourceClose** | 0x126 |
| 0x54 | ~~StreamSinkFromSource~~ **SinkClose** | 0x12A |
| 0x6E | ~~StreamAudioSink~~ **StreamScoSink** | 0x16A (real StreamAudioSink: **0x162**) |
| 0x89 | ~~StreamKalimbaSink~~ **KalimbaPowerOff** | 0x1BE (real StreamKalimbaSink: **0x1B4**) |
| 0x8A | ~~KalimbaLoad~~ **KalimbaSendMessage** | **0x1C3** |
| 0x8C | ~~KalimbaSendMessage~~ **MessageKalimbaTask** | 0x1CD |

~~**Every stub address this project has used was correct.** All the
failures were argument conventions.~~ **Retracted 2026-09-30.** The
addresses came from the wrong BlueLab version's trap table; the audio
and Kalimba ones are all wrong. See `docs/trap-numbering.md`.

## `StreamKalimbaSource` is not a trap

The compiler renders `StreamKalimbaSource(x)` as
**`StreamSourceFromSink(StreamKalimbaSink(x))`** — two calls. So
`traps.json`'s label for 0x89 (`StreamKalimbaSink`) is **correct**, and my
earlier suspicion that it was mislabelled was wrong. Withdrawn.

## Consequence: probes 46 and 47 were the same call

Both put the port in `@(0,Y)` and `AL=3`. Under the real convention, the
port argument is **AL**, so both actually called
**`StreamKalimbaSink(3)`** — identical calls, which is exactly why they
produced identical crashes.

**Therefore Bose's negative port 0xFFFB has never been tested**, and the
conclusion recorded as "the VM audio-injection route is closed" rests on
two malformed probes. What is actually established is narrower:
**`StreamKalimbaSink(3)` crashes from cave context.** The route should be
re-opened as a question, with a correctly-encoded probe.

## Probes that were correctly encoded after all

`StreamAudioSink` in probes 52-54 used `AL=3, AH=0, @(0,Y)=channel`, which
matches the verified 3-argument form. probe54's `SinkClaim` (AL=sink,
AH=size), `SinkMap` (AL=sink) and `SinkFlush` (AL=sink, AH=size) are all
correct too. **probe54 is sound and its result will be meaningful.**

---

# Correction: my probe53 bug diagnosis was WRONG

I claimed `W(0xE139)` = `add X,@0xffe1` was a bug — "an MMIO read, not
`add X,AL`". The ADK's own listing settles it:

```
$XAP_AH  EQU H'ffe0
$XAP_AL  EQU H'ffe1
```

**0xFFE1 *is* AL.** The XAP exposes its registers as memory addresses, and
the compiler itself emits `xor AH,@$XAP_AL` and `add AL,@$XAP_AH` in
ordinary generated code. So `add X,@0xffe1` is exactly `add X,AL`,
probe39's original comment was correct, and probe53's pointer arithmetic
was fine.

**probe53's real failure cause is therefore unexplained**, and probe54 —
which "fixed" it by dropping the offset — removed something that was
never broken. Worse, dropping the offset is itself likely wrong: if
`SinkClaim` returns a non-zero offset, writing at the bare base writes to
the wrong place.

Remaining candidates for probe53: `SinkClaim` returning failure (0xFFFF),
making the write pointer `base-1`; or the sink being null and the bail
path behaving differently than intended.

**Third time I have blamed an inherited comment and been wrong about the
instruction.** The rule that actually works, now enforced by
`tools/caveasm.py`: generate sequences from verified ABI, never hand-write
them, and never diagnose an encoding without checking it against compiler
output.

# Verified XAP opcodes (from compiled brown-noise code)

> **Superseded 2026-09-30 by `docs/xap-opcodes.md`**, which derives the
> whole instruction set by aligning the ADK assembler's mnemonics
> against the linked words, with the linker's own function sizes as
> proof. Two rows below are wrong: `0x0009` is not `clc` but the
> unsigned-form modifier (it turns `asr` into `lsr` and `sdiv` into
> `udiv`), and `0x0074` is `nadd AL,#imm`, of which negation is only
> the `#0` case. The rest reproduce exactly.

| encoding | meaning |
|---|---|
| `0x0009` | `clc` (clear carry; precedes `asr` for a logical shift) |
| `nnA4` | `asr #n` — arithmetic shift right of AH |
| `0x0074` | `neg` |
| `nnC4` | `and AL,#n` |
| `0xE1D1` | `xor AH,@0xffe1` = **xor AH,AL** |
| `nn33` | `add AH,@(n,Y)` |
| `nn23` / `nn13` | `st/ld AH,@(n,Y)` |
| `0x0022` | `st AH,@(0,X)` |
| `nn17` / `nn27` | `ld/st AL,@(n,Y)` |
| `nn1B` | `ld X,@(n,Y)` |
| `0x0134` | `add AL,#1` |
| `0xE139` | `add X,@0xffe1` = **add X,AL** |

A 16-bit Galois LFSR plus integrator — brown noise — compiles to ~17
words, well within the cave budget.
