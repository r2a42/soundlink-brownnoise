# Messages, tasks, and where a cave's Task can live

> **Note on references (public export):** this file cites files from the original private research repository that are not included here; each such path is marked "(not in this export)" at its first mention, and all of them are listed in `docs/NOT-IN-EXPORT.md`. The claims they support are summarised in the text; the cited originals are not needed to rebuild or flash anything.

> **This is an archival research document from the original (larger, private) project repository.** Some of its internal links point at files not included in this public export; where one doesn't resolve, that's why. The repository's own current, self-contained write-ups are listed in README.md's "Repository layout" section.

**2026-09-30.** Established the project's own way: compile **and link** a
probe app with the ADK (`build/sustainprobe/`), read the generated `.xap`
and the linked image, and cross-check every conclusion against the
speaker's own `vm.app`. Nothing here is inferred from call sites.

This answers the question the sustain problem was blocked on: *can a cave
keep audio running after the button handler returns?* The infrastructure
answer is **yes**, and it needs no RAM allocation.

## 1. The argument convention generalises to four arguments

`docs/trap-abi.md` established 1-3 arguments. `MessageSendLater` has four,
and the compiler's emission shows the rule is uniform:

```c
MessageSendLater(&g_task, 0xA111, 0, 0xB222);
```
```
ld AL,#0       ; st AL,@(0,Y)      arg3  message
ld AL,#0xB222  ; st AL,@(2,Y)      arg4  delay, LOW word
ld AL,#0       ; st AL,@(1,Y)      arg4  delay, HIGH word
ld AL,#(_g_task)                   arg1
ld AH,#0xA111                      arg2
bsr $_MessageSendLater
```

> **arg1 -> AL, arg2 -> AH, args 3..n -> `@(0,Y)`, `@(1,Y)`, ... in order.
> A 32-bit argument occupies two consecutive slots, HIGH word first.
> Return in AL.**

`SinkConfigure`'s `@(0,Y)`=high / `@(1,Y)`=low is the same rule, not a
special case: its 32-bit value is simply the first stack argument.

## 2. The callback convention is the mirror image

```c
static void handler(Task t, MessageId id, Message m) { ... }
```
```
_handler:
    enterl #2
    ld X,@(2,Y)            ; arg3  Message      <- caller's slot 0
    st AL,@$_g_seen_task   ; arg1  Task
    st AH,@$_g_seen_id     ; arg2  MessageId
```

> **A handler receives Task in AL, MessageId in AH, and Message at
> `@(n,Y)` after its own `enterl #n`** -- the caller's slot 0, shifted by
> the frame it just opened.

## 3. A `TaskData` is two words: the handler's code-relative address

```
_g_task:  DS 2
    .SEG INITC
    dc hwrd(_handler)
    dc lwrd(_handler)
```

In the linked image those two const words are `0x0000 0x0042`, and
`_handler`'s symbol address is `0x0042`. So:

> **`TaskData = { hwrd(a_handler), lwrd(a_handler) }`, a 32-bit
> code-relative word address, high word first.**

"Code-relative" is **exactly the project's `a` space**: symbol address =
file word index - 24 (the header). Verified twice over -- our probe's
symbols line up that way, and every stub address in `docs/trap-abi.md`
(PanicNull 0x42, SinkClaim 0xDE, StreamConnect 0x106, ...) reproduces as
`file_index - 24` when the speaker's `vm.app` is rescanned.

`MessageLoop` dispatches by adding the running PC to that value, so the
stored number is position-independent and needs no load-base fixup from
us. The mechanism is worth stating because it names a register:
`bsr +1` captures the return address, `add X,@(-2,Y)` adds the stored
low word, and the high half comes from `@0xFFE2`. **X is the link
register** — the ADK's `$XAP_UXH`/`$XAP_UXL` are its two halves, and
`$XAP_UY` is simply Y; the "U" is CSR's name for the user register
file, not a separate register. The consequence for cave code is
concrete: **X does not survive a `bsr`**, so a pointer held in X must
be reloaded after every call. The speaker runs the stock library `MessageLoop`; its dispatch
signature (`ld AH,@(0,X) ; ld AL,@(1,X) ; st AH,@(-1,Y) ; st AL,@(-2,Y)`)
occurs **exactly once** in Bose's `vm.app`, at `a = 0x39603`.

## 4. The constant pool is directly readable as data, at 0x7400

From the ADK's own `crt0`:

```
.PACK {INIT, VAR, VAREND}, {H'500,  H'900}     globals
.PACK {CONST, INITC},      {H'7400, H'D400}    constants
```

Confirmed in the linked probe: a `static const TaskData` was passed as
`ld AL,#0x7401`, a `const uint16[]` was read with `ld AL,@(0x7403,X)`, and
RAM globals sat at `0x503`.. -- exactly `0x7400 + const_offset` and
`0x500 + global_index`.

For the speaker's `vm.app` (header says code = 236514 words, const =
24475):

| region | `a` range | data address |
|---|---|---|
| code | 0 .. 236513 | not data-addressable |
| const | 236514 .. 260988 | `0x7400 + (a - 236514)`, ending 0xD39A |

Two independent checks that this mapping is real: the const segment is
24475 words against a hard cap of 24576 (`0xD400-0x7400`) -- a 101-word
margin, far too snug to be coincidence -- and 522 of Bose's absolute data
references land inside the window.

**The cave at `a = 0x3E21D` is in the const region, at data address
`0xBA3B`.**

## 5. Consequence: a cave can own a Task

The cave already lives in const zero-padding. Const is flash, so it is
permanent, and const is data-addressable, so a `Task` pointer to it is an
ordinary pointer. Therefore:

> Reserve two words of the cave's padding at `a_task`. Write
> `{hwrd(a_handler), lwrd(a_handler)}` into them **at build time**, as
> ordinary flashed data. Pass `0x7400 + (a_task - 236514)` wherever a
> `Task` is wanted.

No RAM allocation, no `malloc`, no scribbling on Bose's globals, and
nothing to re-establish after a power cycle. `tools/caveasm.py` has
`const_addr()` and `taskdata_words()` for this.

The handler itself is an ordinary cave function: `enterl #n` ... `leavel
#n`, reading `id` from AH.

## 5a. Bose's own code confirms the callback convention

The handler Bose registers with `MessagePioTask` (its only call site,
0x7E7E) lives at **0x7F1A**, and the registration builds the TaskData
exactly as described above: `ld AH,#0` / `ld AL,#0x7f1a` then
`st AH,@(0,X)` / `st AL,@(1,X)`. The handler then dispatches on **AH**
against `0x8023` (`MESSAGE_PIO_CHANGED`), `0x8024` and `0x802D`, and
reads its Message from `@(13,Y)` after `enterl -13`.

That is the incoming convention — id in AH, message at `@(n,Y)` after
`enterl #n` — observed in the speaker's own firmware rather than only
in a probe we compiled. A cave handler can be written against it with
confidence.

## 6. Two sustain mechanisms, both now reachable

**A -- timer.** `MessageSendLater(task, id, 0, delay_ms)`; the handler
refills the sink and re-arms. Delay is in milliseconds
(`D_SEC(s) = s*1000`); `D_IMMEDIATE` is `(Delay)-1`, and that is exactly
what the library's `MessageSend` passes -- it is a wrapper, not a trap:

```
$_MessageSend:  ld X,@(5,Y) ; st X,@(0,Y)
                ld X,#-1 ; st X,@(2,Y) ; st X,@(1,Y)
                bsr $_MessageSendLater
```

**B -- sink-driven, the ADK-native one.** `MessageStreamTaskFromSink(dac,
task)` registers the task; the firmware then sends `MESSAGE_MORE_SPACE`
(**0x8022**) whenever the DAC has room, and `SinkSlack(dac)` says how
much. Frequency is set with `SinkConfigure(dac, VM_SINK_MESSAGES=0x0004,
VM_MESSAGES_ALL=0)`. This is self-clocking and cannot drift.

B is the right long-term answer; A is easier to interpret on a first
flash, because it fires exactly once and tells us the dispatch works.

Either way the handler runs from the **main VM message loop**, which is a
far safer context than the current cave -- that one runs inside a button
handler, which is where every request-API crash (probes 30/34/35) came
from.

## 7. Stub addresses this added

Full table in `docs/trap-stub-table.md` (not in this export) (all 151), machine-readable in
`tools/bose-stubs.json`. All of these are below trap 0x4D, where
BlueLab 7.3 and 7.4 agree, so they survived the naming correction in
`docs/trap-numbering.md` (not in this export) unchanged — unlike the audio path.

The ones that matter here:

| trap | name | stub `a` |
|---|---|---|
| 0x10 | `MessageSendLater` | **0x062** |
| 0x11 | `MessageCancelFirst` | 0x066 |
| 0x12 | `MessageWait` | 0x287 |
| 0x14 | `MessageFree` | 0x28A |
| 0x3D | `MessageSinkTask` | **0x0D2** |
| 0x3E | `MessageSinkGetTask` | 0x0D6 |
| 0x3F | `SinkSlack` | **0x0DA** |
| 0x22 | `VmGetClock` | 0x096 |
| 0x6C | `StreamAudioSink` | **0x162** |
| 0x86 | `StreamFileSource` | 0x1AF |

`MessageSend`, `MessageCancelAll` and `MessageLoop` are **library
functions, not traps** -- do not look for stubs for them.

`VmSoftwareWdKick` (trap 0xD4) has **no stub in Bose's image**, so the
VM cannot disable or re-arm the software watchdog. An earlier draft of
this file listed one at 0x267; that was the 7.4 mis-naming, and 0x267
is really `TransformRtpEncode`.

## 8. What this does not establish

Nothing here has been run on the speaker. It says the mechanism exists and
gives its exact shape; it does not say the DAC produces sound, which is
still what probe56 is waiting to answer. If probe56 is silent, none of
this rescues it -- a sustained silence is still silence.

## The sink-driven clock and the `buf`-in-MessageId trick are incompatible (2026-10-02)

Approach B above — `MessageStreamTaskFromSink(sink, task)`, then refill on
`MESSAGE_MORE_SPACE` (`0x8022`) — is still the right long-term answer. But it cannot be
bolted onto probes 111 and 113 as they stand, and the reason is worth writing down before
someone tries.

Both probes carry the heap buffer **in the MessageId field**: `MessageSendLater(task, buf,
0, delay)`, so their handler reads `AH` as `buf`. A handler gets Task in `AL` and
MessageId in `AH` (see above), and `MessageSinkTask` controls the task for the **whole
stream**, delivering both `MESSAGE_MORE_SPACE` and `MESSAGE_MORE_DATA` (`message.h:46-49`).
So registering our own task on the sink would hand that handler a small real MessageId
where it expects a heap pointer, and it would build a `StreamRegionSource` and a transform
over whatever lies at that address, once per message — the probe 105/106 leak, recreated.

**So approach B requires giving up the MessageId trick first.** `buf` would have to live
somewhere the handler can read independently — the cave's own `TaskData`, or a const-pool
word — leaving `AH` free to carry a real id, and the handler would dispatch on it:
`0x8022` means refill, our own timer id means first-fill. That is the shape of the next
refill probe, not an edit to an existing one.

Until then, probes 111 and 113 use `MessageSinkTask(ksink, 0)`, which takes the
registration **away from the prompt** (`fn_22f6f` leaves its own task `0xbd4e` on port 3)
without routing anything into ours. See `docs/field-log.md` (not in this export).

## The firmware's own third option: `MessageSendConditionally` on a busy flag

`fn_06c61` (152 words, 10 callers) is Bose's "hand this chunk to a region source, or defer
it if one is still live" helper, and it clocks itself with neither a timer nor a sink
message:

    busy = &inst[21]                       # inst = @0x546 + instance
    if *busy == 0:                          # 0x06c85, the branch test
        src = StreamRegionSource(inst[45], len + 2)
        inst[47] = src
        *busy = 1                           # 0x06cc5
        fn_23f17(inst[19], 9, {0, 0, 0x7e, size, src})
    else:
        m = PanicUnlessMalloc(len + 4)      # copy the payload into a message
        ... memcpy via fn_39468 ...
        MessageSendConditionally(0x512, 0x5e52, m, busy)   # 0x06cf5

`MessageSendConditionally(Task, MessageId, Message, const uint16 *c)` delivers the message
when **`*c` becomes zero** (`message.h:149`). So the firmware serialises region sources
behind a single busy word rather than polling or timing.

For this project the catch is that **nothing in the stream layer clears that word** — the
code that retires the chunk does. A cave would have to clear its own flag, which buys
nothing a timer does not. It is recorded because it explains the `0x512` / `0x5e52` pair
seen elsewhere, and because the `inst[21]` busy flag is the thing to watch if a future
probe wants to interleave with the firmware's own region sources rather than displace them.

**Do not read the `len + 2` here as our probes' `buf + 2`.** Theirs is a two-word header
inside the region; ours is two words of generator state *before* the region starts. Same
constant, unrelated reasons.
