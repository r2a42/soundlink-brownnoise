# Buffer sizing and streaming cadence for a small-buffer source into Kalimba port 3

> **This is an archival research document from the original (larger, private) project repository.** Some of its internal links point at files not included in this public export; where one doesn't resolve, that's why. The repository's own current, self-contained write-ups are listed in README.md's "Repository layout" section.

**2026-10-04.** Task: size the buffer and pick the clock for a VM-generated audio source
feeding `TransformAdpcmDecode -> StreamKalimbaSink(3)`, the path probe104 proved carries
audio. Four questions, answered in the brief's order.

**Headline, in one paragraph.** The length convention is confirmed and the arithmetic is
`duration_ms = n/4` for an `n`-word block at 8 kHz. A source **cannot** be rewound or
re-read — there is no trap for it, and while a transform holds the source every
introspection call is documented to return zero — but that does not matter, because the
firmware's own answer is *rebuild the source, keep the buffer*, and it does this in two
separate places. The clock must be a **repeating `MessageSendLater`**: `MESSAGE_MORE_SPACE`
is structurally useless on a transform-fed sink (the sink is connected, so there is no
space to report), `MESSAGE_STREAM_DISCONNECT` arrives only after the gap has begun, and
polling `SourceSize` returns zero by documentation. The recommended design is
**`malloc(133)` into the one 138-word pool block — 128 bytes of ADPCM = 32 ms — rebuilt
every 28 ms**, with `0x1072` sent exactly once and `SourceClose` called on every tick.

---

## 1. The length convention: confirmed, with a third independent proof

> `StreamRegionSource(ptr, n)` takes **`n` 16-bit words** of backing store and delivers
> **`n` bytes**, one byte per word, from the **low 8 bits** of each word. *(proven)*

The project already believed this from probe104 and from `sink_avrcp.c`. Here is the
disassembly that settles it outright, `fn_06c61` (`0x6c61 .. 0x6cf9`, 152 words, 10
callers) — the AVRCP passthrough request builder:

    0x06c89:  AL = len + 2
    0x06c8b:  buf = malloc(len + 2)          <-- malloc takes WORDS
    0x06c99:  X = buf
    0x06c9b:  clc +0 ; asr #0x8              ; AH = op >> 8
    0x06c9d:  st AH,@(0,X)                   <-- buf[0] = HIGH byte, one whole word
    0x06ca3:  and AL,#0xff                   ; AL = op & 0xff
    0x06ca5:  st AL,@(1,X)                   <-- buf[1] = LOW byte, the NEXT word
    0x06cad:  memcpy(buf + 2, payload, len)  (fn_39468)
    0x06cb7:  AH = len + 2
    0x06cbb:  src = StreamRegionSource(buf, len + 2)

A two-byte protocol header occupies **two words**, each carrying one byte in its low 8
bits, and the length handed to `StreamRegionSource` is the same `len + 2` that was handed
to `malloc`. Words == bytes, and the byte is the low half.

Two corroborations, both already in the tree:

- `fn_1edf9` at `0x1ee1b` reassembles a big-endian 16-bit file field as
  `(p[0] & 0xff) << 8 | (p[1] & 0xff)` from a `SourceMap` pointer — same convention on the
  read side. The matching ADK source is `voice_prompt_file.c:50-52`:
  `prompt->playback_rate = ((uint16)rx_array[10] << 8) | rx_array[11];`
- probe104 on hardware: `n = 17000` gave "about 4 seconds" at 8 kHz.
  `17000 x 2 / 8000 = 4.25 s`. *(proven, arithmetically exact)*

### ADPCM density, and why this convention favours ADPCM 4:1

`TransformAdpcmDecode` is IMA ADPCM, 4 bits per sample, so one byte is two samples.
Combined with one-byte-per-word:

| payload format | bits/sample | samples per **word** of VM RAM |
|---|---|---|
| IMA ADPCM via `TransformAdpcmDecode` | 4 | **2.0** |
| 16-bit PCM via `StreamConnect` / `StreamMove` | 16 | 0.5 |

**ADPCM gets 4x more audio per word of a pmalloc block than raw PCM does.** On a unit whose
largest reachable block is 138 words that is the difference between 32 ms and 8 ms. This is
the single strongest argument for keeping the ADPCM transform in the design.

### Duration table at 8000 Hz

`samples = 2n`, `duration_ms = 2n/8000 x 1000 = n/4`.

| n (words = bytes) | samples | duration @ 8 kHz | rebuild rate if period = duration | pool on THIS unit |
|---|---|---|---|---|
| 64  | 128  | **16.0 ms** | 62.5 Hz | PMALLOC_EXTRA only (5 blocks) — reachability unproven |
| 94  | 188  | **23.5 ms** | 42.6 Hz | APP 2 blocks (+ EXTRA 2) |
| 100 | 200  | **25.0 ms** | 40.0 Hz | APP **4 blocks** (3 + 1) |
| 128 | 256  | **32.0 ms** | 31.3 Hz | lands in the APP 138 block |
| 138 | 276  | **34.5 ms** | 29.0 Hz | APP **1 block** |
| 160 | 320  | **40.0 ms** | 25.0 Hz | PMALLOC_EXTRA only (2 blocks) |
| 318 | 636  | **79.5 ms** | 12.6 Hz | APP 1 block — **held: it is the app stack arena** |
| 642 | 1284 | **160.5 ms** | 6.2 Hz | APP 1 block — unavailable with music paused (probe103) |

Two caveats on this table, both honest:

1. **A per-stream ADPCM header, if the transform consumes one, is not accounted for.** IMA
   ADPCM in WAV carries a 4-byte block header (predictor16 + index8 + reserved8). Nothing
   in `transform.h`, `voice_prompts_dsp_if.c` or the disassembly says whether CSR's
   transform expects one. probe104's `n = 17000` cannot distinguish: 4 bytes out of 17,000
   is 0.05%. At `n = 128` it would be 3% — 8 samples, 1 ms. So **treat the durations as
   upper bounds accurate to about 1 ms.** *(negative: not established either way)*
2. **`malloc` reachability of PMALLOC_EXTRA is not established on this unit.** `docs/cave-heap.md`
   derives the app pool list from `PSKEY_PMALLOC_APP` and every observed `malloc` result
   (128 reliable; 254, 320, 512, 1024 refused) is explained by that list alone. Sizes that
   exist *only* in `PSKEY_PMALLOC_EXTRA` — 64 and 160 — have never been requested.
   **Treat 64 and 160 as untested, not as available.** *(negative)*

---

## 2. Can one source be reused? No — and it does not matter

### 2a. There is no rewind. Four independent negatives.

- **No such trap exists.** `docs/trap-stub-table.md` lists all 151 stubs in this `vm.app`;
  `source.h` lists the whole `Source` API: `SourceSize`, `SourceSizeHeader`, `SourceMap`,
  `SourceMapHeader`, `SourceDrop`, `SourceBoundary`, `SourceIsValid`, `SourceConfigure`,
  `SourceClose`, `SourceSynchronise`. **There is no Seek, Rewind, or Reset.** *(proven)*
- **`SourceDrop` only moves forward.** "Discards the indicated number of bytes from the
  **front** of the source." Negative amounts are not expressible — `amount` is `uint16`.
  The firmware's only idiomatic use is the `SourceEmpty` macro, drain-to-zero; `fn_2504a`
  at `0x250c6`-`0x250cc` is exactly that:

      0x250c6:  AL = @(11,Y)                 ; the source
      0x250c7:  bsr SourceSize
      0x250ca:  AH = @0xffe1                 ; AH = returned size  (SourceDrop arg2)
      0x250cb:  AL = @(11,Y)                 ; AL = source         (arg1)
      0x250cc:  bsr SourceDrop               ; = SourceEmpty(src)

  That is `#define SourceEmpty(s) SourceDrop(_x, SourceSize(_x))` from `source.h:16`,
  compiled. It throws data away; it cannot bring data back. *(proven)*
- **`SourceConfigure` has no position key.** The full `vm_stream_config_key` list
  (`app/vm/vm_if.h`, mirrored in `app/stream/stream_if.h:136-161`) is
  `VM_SOURCE_SCO_RATEMATCH_ENABLE 0x0`, `VM_SOURCE_FREQUENCY 0x1`, `VM_SOURCE_MESSAGES 0x2`,
  `VM_SOURCE_SCO_METADATA_ENABLE 0x3`, `VM_SINK_MESSAGES 0x4`, four USB keys `0x5-0x8`,
  `VM_SINK_SCO_SET_FRAME_LENGTH 0x9`, `STREAM_SOURCE_NOTIFY_WHEN_DRAINED 0xA`,
  `STREAM_DSP_DISABLE_METADATA 0xB`, then hardware keys from `0x0100` up. **Nothing
  addresses read position or length.** *(proven)*
- **The length is fixed at creation.** `StreamRegionSource(const uint8 *data, uint16 length)`
  takes the length once; no call re-supplies it.

### 2b. While a transform holds it, the source is opaque to the VM

Every relevant trap carries the same note, and it is not a footnote — it is the governing
rule for this design:

| call | `source.h` / `stream.h` says, when the stream is connected to another stream |
|---|---|
| `SourceSize` | "will return zero" |
| `SourceMap` | "will return zero" |
| `SourceBoundary` | "will return zero" |
| `SourceDrop` | "will fail" |
| `StreamMove` | "will return zero" |
| `SinkSlack` / `SinkClaim` / `SinkMap` | "will return zero" |
| `SinkFlush` | "will return FALSE" |

A `TransformStart`ed transform *is* a connection. So once the transform is running:
**`SourceSize` cannot tell you how much is left, `SourceMap` cannot give you a pointer, and
`SinkSlack` cannot tell you how much room the port has.** *(proven from the headers; the
same wording appears on all nine traps)*

This kills the three obvious "clever" designs in one stroke: you cannot poll progress, you
cannot top the source up, and you cannot measure the port.

### 2c. The backing buffer *can* be rewritten — but it buys nothing

`stream.h:191-207` is explicit that there is no copy:

> "...in order to efficiently transfer the data without having to copy it. It is important
> that the memory being treated as a source **persists long enough** for the stream
> operation to complete... the memory block being treated as a source **is not freed** by
> the stream subsystem... It remains the caller's responsibility to manage the memory."

So the region source is a window on VM data space, and writing to that memory while the
transform runs is physically legal — it is an ordinary store, not a stream call. But:

- you cannot know the read position (2b), so every write is blind and races the consumer;
- and rewriting **cannot extend the source past `n` bytes.** After `n` bytes the source is
  spent and the transform ends, whatever is in memory.

> **Answer to Q2: a `StreamRegionSource` cannot be rewound, re-read, or extended. In-place
> rewriting of the backing buffer is possible but gains nothing, because the source still
> dies at `n` bytes and the VM cannot see the read pointer.** *(proven)*

### 2d. The firmware's own answer: rebuild the source, keep the buffer

This is the useful half of Q2, and the image contains **two** fully decoded instances of
the pattern.

**Pattern A — a fresh source per chunk, inside a tight loop, never closed.**
`fn_14a19` (`0x14a19 .. 0x14b05`, 236 words, called from `0x1483f`) is a VM-driven push of
a memory region into a sink, and its inner loop is exactly the shape this task is asking
about:

    0x14a64:  loop:  AL = @0x5d2                      ; the destination sink
    0x14a66:         bsr SinkSlack
    0x14a69:         and AL,#0xfffe                   ; round slack down to even
    0x14a6b:         beq -> 0x14ac6                   ; no room: set stalled, leave loop
    0x14a6c:         n = @(19,Y)                      ; bytes remaining
    0x14a6e:         cmp AH,@0xffe1 ; bcz +2
    0x14a70:         n = slack                        ; n = min(remaining, slack)
    0x14a71:         ptr = @(21,Y) + desc[2] + 4      ; running byte offset into the buffer
    0x14a76:         src = StreamRegionSource(ptr, n) <-- A NEW SOURCE, EVERY CHUNK
    0x14a84:         StreamMove(@0x5d2, src, n)
    0x14a91:         SinkFlush(@0x5d2, n)
    0x14a96:         @(19,Y) -= n                     ; remaining
    0x14a99:         @(21,Y) += n                     ; offset  <-- the BUFFER is reused
    0x14acb:         if remaining == 0 -> done
    0x14ace:         if !stalled -> bra -106 -> 0x14a64

  One persistent buffer, a throwaway `StreamRegionSource` per chunk, and **no `SourceClose`
  anywhere** — because `StreamMove` drains each source completely and `stream.h:199-203`'s
  "the source only exists while the data is being read" reclaims it. *(proven)*

**Pattern B — a fresh source per fill, explicitly closed.**
`fn_06c61` creates it (quoted in §1) and the twins `fn_06aa7` (`0x6aa7 .. 0x6ad9`, 50
words) and `fn_05deb` (`0x5deb .. 0x5e0b`, 32 words) tear it down. `fn_06aa7`:

    0x06ab8:  tst @(45,X)            ; is a buffer still live?
    0x06ab9:  beq -> 0x06acf
    0x06abb:  fn_23f11(inst[19])     ; cancel the outstanding request
    0x06ac1:  AL = inst[45]
    0x06ac2:  bsr free               <-- free the BUFFER
    0x06ac7:  AL = inst[47]
    0x06ac8:  bsr SourceClose        <-- close the REGION SOURCE
    0x06ace:  inst[45] = 0
    0x06ad3:  inst[21] = 0           ; clear the busy flag
    0x06ad7:  inst[23] = 0

  `free` the buffer **and** `SourceClose` the source, as two separate obligations.
  *(proven)*

> **The firmware never reuses a region source and never rewinds one. It rebuilds the source
> object — which is cheap and, when fully drained, free — and reuses the buffer. That is the
> design to copy.** `docs/cave-heap.md` already records the cost of getting this wrong:
> probes 105 and 106 rebuilt the transform 36 times a second and never called
> `SourceClose`, and because they refilled early the source had not drained either, so
> nothing reclaimed it. One leaked stream object per cycle exhausted the pool until **Bose's**
> allocations hit `PanicNull`.

---

## 3. The clock: a repeating `MessageSendLater`, and nothing else works

### 3a. `MESSAGE_MORE_SPACE` (0x8022) — a real mechanism in this build, structurally useless here

The mechanism works. `vm_if.h:76-89` says the default is `VM_MESSAGES_ALL` (= 0), so a sink
with a registered task gets MORE_SPACE without any `SinkConfigure`; `VM_MESSAGES_SOME` = 1,
`VM_MESSAGES_NONE` = 2, set with `SinkConfigure(sink, VM_SINK_MESSAGES = 0x0004, v)`.
Seven handlers in the image compare against `0x8022`:

| site | context |
|---|---|
| `0x18538` | USB audio: `0x8022` **acted on** (`-> 0x18568`), `0x8021` acted on, pumps via `fn_188ea` = `fn_12e1a` + `SinkFlush` on endpoint `0x81` |
| `0x22d7d` | voice prompts, port 3: `0x8022` -> `0x22d89`, which is `leavel`. **Does nothing.** |
| `0x2575e`, `0x2da8b`, `0x34c9c`, `0x35f92`, `0x361b4` | other protocol sinks |

So MORE_SPACE is live and usable on this firmware — on sinks the VM writes itself. It is
useless for our case for a structural reason, not an empirical one: **MORE_SPACE reports
space on a sink the VM can write, and our sink is connected to the transform, so
`SinkSlack` returns 0 and there is nothing to write (§2b).** The firmware's own port-3 code
agrees by treating `0x8022` as noise at `0x22d7f`.

The one thing worth saying in its favour: the empty arm at `0x22d7f` sits **first** in
`fn_22d7c`'s comparison chain, ahead of `0x8026`, which is where a compiler puts the most
frequent case. That is weak evidence that `0x8022` does fire on a transform-fed port-3
sink — i.e. the message arrives, it just carries no actionable information.
*(well-supported, not proven)*

### 3b. `MESSAGE_MORE_DATA` (0x8021) — wrong direction

A *source* event: "more data has arrived at a Source" (`system_message.h:98`,
`SYSTEM_MESSAGE_BASE_ + 33`). Our region source is VM memory, not a producer; nothing
arrives at it. Controlled by `VM_SOURCE_MESSAGES = 0x0002`. **Irrelevant.** *(negative)*

### 3c. Polling `SourceSize` — dead by documentation

`source.h:21-28`: "This call will return zero if the source stream is connected to another
stream." A running transform is such a connection. **`SourceSize` on our source returns 0
from the moment `TransformStart` succeeds until the transform is gone, so it cannot
distinguish "finished" from "running".** Recording this as a negative because it is the
most attractive-looking of the three options in the brief. *(proven from the header)*

Related negative: `STREAM_SOURCE_NOTIFY_WHEN_DRAINED` (`SourceConfigure` key `0x000A`)
sounds like the answer but is not — it "will generate **HQ event** when the stream buffer
has been drained", a host-queue event, not a VM message. *(well-supported)*

### 3d. `MESSAGE_STREAM_DISCONNECT` (0x8026) — correct, but too late

This is the event the firmware actually uses: `fn_22d7c` at `0x22d80` -> `fn_23183` ->
`fn_231c8`, end-of-prompt teardown. It fires when the transform tears down, i.e. **after**
the source has drained — after the gap has started. Fine as a safety re-arm; useless as the
primary clock, which must fire *before* the buffer runs out.

### 3e. What the DSP does if you are late — the two deadlines

This is the number that actually constrains the period, and it comes out of the Kalimba
source rather than the VM image.

| constant | value | file |
|---|---|---|
| `TONE_BUFFER_SIZE` | **256** samples ("for 8khz input and 16ms interrupt period") | `codec_decoder.h:107` |
| resample cbuffer | `TONE_BUFFER_SIZE * 6` = 1536 | `codec_tones.asm:29` |
| `TMR_PERIOD_TONE_COPY` | **8000** us ("8msec tone timer handler period"), scaled by `8000/rate` | `codec_decoder.h:105`, `codec_tones.asm:478-480` |
| `$PCM_END_DETECTION_TIME_OUT` | **30000** us = **30 ms** | `codec_decoder.h:166` |
| `PLAY_BACK_FINISHED_MSG` | `0x1080` | `codec_decoder.h:160` |

`$detect_end_of_aux_stream` (`codec_tones.asm`, called from `$tone_copy_handler` on every
copy tick) does this:

    r3 = M[$aux_input_stream_available];  if Z return      ; port not armed
    r0 = amount of data in $tone_in_left_resample_cbuffer_struc
    ... first-data latch on bit 1 ...
    input_has_received:
       r1 = M[$no_tone_timer] + M[$tmr_period_tone_copy]
       Null = r0 ; if NZ r1 = 0                            ; any data at all resets it
       M[$no_tone_timer] = r1
       Null = r1 - $PCM_END_DETECTION_TIME_OUT ; if NEG return
       send PLAY_BACK_FINISHED_MSG (0x1080) to the VM
       M[$aux_input_stream_available] = 0                  <-- THE PORT IS DISARMED

So there are two deadlines, and they are far apart:

- **The audible deadline.** The pipe holds up to 256 samples = **32 ms** at 8 kHz (plus
  whatever sits in the 1536-word resample buffer). Run past it and the listener hears a
  dropout.
- **The fatal deadline.** **30 ms of continuous emptiness** after that and the DSP clears
  `$aux_input_stream_available`, sends `0x1080`, and **stops reading port 3 entirely**. Only
  another `0x1072` re-arms it (`set_tone_rate_from_vm` sets the flag back to 1), and that
  `0x1072` also purges the tone buffers — `codec_tones.asm:507-513`, the bug that silenced
  probes 105 and 106.

> **A design tolerates one missed tick and not two.** With a 32 ms buffer and a 28 ms
> period: one missed tick leaves the pipe dry for ~24 ms — audible, survivable. Two missed
> ticks leave it dry for ~52 ms > 30 ms — the port disarms and the cave goes permanently
> silent with no way to notice. *(well-supported: arithmetic over the two cited constants)*

### 3f. Verdict and the period table

> **Answer to Q3: a repeating `MessageSendLater(cave_task, id, 0, period_ms)` is the only
> clock a small cave can use reliably.** It is the only one of the four options that can
> fire *before* the source drains, which is the entire requirement. Delay is in
> milliseconds with 1 ms resolution; the handler runs from the main VM message loop, which
> `docs/message-task-abi.md` §6 already notes is a far safer context than a button handler.
> `0x8026` and `MESSAGE_FROM_KALIMBA`/`0x1080` are worth knowing as failure signals but
> cannot drive the stream.

Period = about **85%** of the buffer duration: enough margin to absorb message-loop jitter,
little enough waste that the generator is not run for nothing.

| n | duration | **recommended period** | tick rate | verdict |
|---|---|---|---|---|
| 64  | 16.0 ms | 13 ms | 77 Hz | **reject** — 13 ms is inside message-loop jitter, and the pool is unproven |
| 94  | 23.5 ms | 20 ms | 50 Hz | workable, tight |
| 100 | 25.0 ms | 21 ms | 48 Hz | **good fallback** — four blocks, most redundant size on the unit |
| 128 | 32.0 ms | **28 ms** | 36 Hz | **recommended** — proven allocatable, and the period probes 105/106 already ran |
| 160 | 40.0 ms | 34 ms | 29 Hz | best numbers, but EXTRA-pool only and untested |
| 318 | 79.5 ms | 66 ms | 15 Hz | block is the app stack arena — **not available** |
| 642 | 160.5 ms | 136 ms | 7 Hz | one block, unavailable with music paused |

Note the inversion in the artefact column: because the ADPCM decoder restarts at
predictor 0 / index 0 on every new transform, the tick rate shows up as a periodic
discontinuity *at the tick frequency*. 36 Hz lands as a low buzz; 7 Hz would land as an
audible flutter. **For artefact placement, smaller and faster is better** — the opposite of
the usual buffering instinct. See §4c.

---

## 4. Recommended design

### 4a. Allocation: one 138-word block, requested as `malloc(133)`, allocated once and never freed

`malloc(133)` lands in the single 138-word `PSKEY_PMALLOC_APP` block — the largest size this
unit has ever been observed to grant (`docs/cave-heap.md`: 128 reliable across probes 61,
81, 105, 106; 254/320/512/1024 all refused). Layout:

| words | use |
|---|---|
| `buf[0 .. 127]` | 128 ADPCM bytes, one per word, low 8 bits = **32.0 ms** of audio |
| `buf[128]` | `ksink`, the port-3 sink handle |
| `buf[129]` | `prev_src`, the source to close next tick |
| `buf[130]` | PRNG state |
| `buf[131]` | generator-side ADPCM predictor |
| `buf[132]` | generator-side ADPCM step index |

Putting the state *inside the block* matters: it means the cave needs **no writable RAM of
its own**, which it does not have — the cave lives in the const pool, which is flash.
`docs/message-task-abi.md` establishes that the block pointer can ride in the MessageId
(`MessageSendLater(task, buf, 0, delay)`; the data pointer on this chip is 16 bits, exactly
a MessageId's width, and probe100 proved the id survives). That document also warns the
trick is incompatible with registering a sink task — **which is fine here, because §3a
established that we do not want one.** The two constraints resolve each other.

The block is never freed. A cave has no shutdown path, and a 138-word permanent reservation
is the honest price of this route.

### 4b. The sequence

Arm once, from the hook. **Every failure is a quiet return — no `Panic*` trap appears
anywhere, and the timer is armed only if the whole chain succeeded.**

    ; ---- arm (runs on the hook) ----
    st = fn_0d475()                              ; 3 words: ld AL,@0x59e ; rts
    if (st != 3 && st != 0x0d) return            ; deviceConnected / deviceA2DPStreaming
                                                 ; anything else => no A2DP DSP => no-op
    buf = malloc(133)                            ; trap 0x00, stub 0x026
    if (!buf) return                             ; pool exhausted: silent no-op
    init_state(buf); fill(buf, 128)              ; brown-noise nibble generator

    if (!KalimbaSendMessage(0x1072, 8000, 0, 0, 0))   ; stub 0x1C3; word b = 0
        { free(buf); return }                    ; FALSE => no DSP loaded. The second
                                                 ; half of the state check.
    ksink = StreamKalimbaSink(3)                 ; stub 0x1B4
    if (!ksink) { free(buf); return }
    buf[128] = ksink

    src = StreamRegionSource(buf, 128)           ; stub 0x152
    if (!src) { free(buf); return }
    t = TransformAdpcmDecode(src, ksink)         ; stub 0x156
    if (!t || !TransformStart(t))                ; stub 0x136
        { SourceClose(src); free(buf); return }  ; stub 0x126
    buf[129] = src
    MessageSendLater(cave_task, buf, 0, 28)      ; stub 0x062

    ; ---- every 28 ms; handler gets Task in AL, buf in AH ----
    on tick(buf):
        ksink = buf[128]
        ; teardown in Bose's own order, fn_31e6f (0x31E6F-0x31E90)
        t = TransformFromSink(ksink)             ; stub 0x14A
        if (t) { TransformStop(t)                ; stub 0x13A
                 TransformDisconnect(t) }        ; stub 0x13E
        StreamDisconnect(0, ksink)               ; stub 0x10E -- UNCONDITIONAL
        SourceClose(buf[129]); buf[129] = 0      ; stub 0x126 -- the probe105/106 leak
        ; refill and restart.  NO 0x1072 HERE.
        fill(buf, 128)
        src = StreamRegionSource(buf, 128)
        t = TransformAdpcmDecode(src, ksink)
        if (t && TransformStart(t)) buf[129] = src
        else                       { SourceClose(src); return }   ; DSP gone: STOP, do not re-arm
        MessageSendLater(cave_task, buf, 0, 28)  ; re-arm on the success path

Objects, explicitly: **buffer reused forever; source and transform rebuilt every tick and
both torn down every tick.** That is Pattern B from §2d, run at 36 Hz.

### 4c. Seven rules, each one a recorded past failure

1. **Send `0x1072` exactly once, at arm time, never in the tick.** Its handler purges the
   256-sample tone cbuffer (`codec_tones.asm:507-513`); probes 105/106 sent it per refill
   and threw away their own audio before the DSP's copy timer could take it. The order
   `0x1072` **before** `StreamKalimbaSink(3)` is the firmware's order (`fn_23016`:
   `0x2306e` then `0x23075`) and exists for the same reason.
2. **Pass word b = 0** (`cbops.shift 7`) rather than 2 (`shift 4`, 18 dB quieter). But note
   the counter-evidence honestly: probe105 passed 0 and the project recorded "+18 dB
   saturates" against -13 dBFS content. **So b = 0 requires the generator's peak scaled
   down by ~18 dB**; if it clips, b = 2 is the retreat.
3. **`SourceClose` the previous source on every tick.** `TransformDisconnect` does not free
   it (`docs/cave-heap.md`), and refilling early means the source has not drained, so
   nothing else reclaims it either. One leak per tick at 36 Hz is what crashed probes 105
   and 106 — through *Bose's* `PanicNull`, not ours.
4. **Full four-call teardown**, `TransformFromSink -> TransformStop -> TransformDisconnect
   -> StreamDisconnect(0, sink)`, with the `StreamDisconnect` unconditional. probe106
   proved an ADPCM transform keeps holding the sink after its source drains.
5. **Re-arm the timer on the success path only, and return without re-arming on any
   failure.** probe100's bug was failure paths skipping the re-arm; the opposite bug — a
   timer that keeps ticking after the DSP is evicted — spins the pool at 36 Hz for nothing.
6. **No `Panic`, `PanicNull`, `PanicFalse` or `PanicUnlessMalloc` on any path.** The ADK's
   own code at `0x23022` and `voice_prompts_dsp_if.c:310` uses `PanicFalse`; a cave must
   not, because a cave's failure must be silence, not a reboot.
7. **Do not call `fn_12e1a` on port 3 again.** See the warning in §5.

### 4d. The state check, spelled out

The brief's two signals are both correct, and they test different things, so use both:

- **`fn_0d475()` == 3 or 0x0d.** `fn_0d475` (`0xd475 .. 0xd478`) is three words —
  `ld AL,@0x59e ; rts` — with **220 callers** (counted from `tools/disasm.py --fn 0x0d475`).
  `@0x59e` is the app's main state word, and enumerating `sink_states.h`'s `sink_state`
  from `deviceLimbo = 0` gives `3 = deviceConnected` and `13 = 0x0d = deviceA2DPStreaming`
  (`adk/root/apps/sink/sink_states.h:54`). Every `0xCx` button case in the dispatcher gates
  on exactly these two values. This tests *whether a phone is attached at all* — and
  probe104 worked at "connected, music paused", so `deviceConnected` must be accepted, not
  just `deviceA2DPStreaming`.
- **`KalimbaSendMessage(0x1072, ...)` returning FALSE.** This tests *whether a DSP is
  actually loaded right now*, which the state word does not. Bail on FALSE.

With no device connected, the first check short-circuits before any allocation, and the
cave is a pure no-op costing one load and two compares. That satisfies the brief's
requirement.

### 4e. Expected audible result

**Proven:** sound. `TransformStart(TransformAdpcmDecode(StreamRegionSource(ptr, n),
StreamKalimbaSink(3)))` carried audio in probe104.

**Well-supported:** continuous broadband noise, mixed into the main chain at `cbops.shift 7`,
for as long as the timer runs and no voice prompt intervenes.

**Hypothesis, and the honest weak point:** the spectrum is brown/red-weighted because IMA
ADPCM reconstructs by accumulating signed deltas with an adaptive step — a clamped random
walk integrator. But the decoder restarts at predictor 0, step index 0 on **every** new
transform, i.e. 36 times a second. If the generated random walk has drifted away from zero
by the end of a buffer, the next buffer begins by jumping back toward zero: a **36 Hz click
train superimposed on the noise.** Two mitigations, both cheap and both untested:

- **Shape each buffer's walk to start and end near zero.** The decoder's predictor is a
  deterministic function of the nibbles, so the cave can run the same IMA step in the
  generator (that is what `buf[131]`/`buf[132]` are for) and bias the last few nibbles to
  bring the running sum home. This removes the step at the seam at the cost of a slight
  high-pass tilt at 36 Hz — which for a sleep sound is harmless.
- **Keep the tick fast.** 36 Hz is a low buzz; the 7 Hz a 642-word block would give is an
  audible flutter. §3f's inversion.

### 4f. The alternative that removes the cadence entirely — **DEAD ON CONTENT (2026-10-04)**

> **Measured, not argued: every file on the device clips 36-54% of its samples through
> `TransformAdpcmDecode`, and so does every window of the 2 MB `ext_flash.bin`.**
> `sbc_decoder.kap` clips **41.08%** with the step index railed (mean 73.5 of 88) at
> **-1.9 dBFS**. The mechanism is structural: high-entropy binary drives IMA ADPCM's
> adaptive step index to its ceiling, where the predictor rails. The full table is in
> `docs/field-log.md` under "The file-source route is DEAD ON CONTENT".
>
> So this section's advice — *"try the file source first"* — is **withdrawn**. It was
> right that the machinery is far lighter; it was wrong that the content would serve. A
> sleep sound cannot be 41% clipped. **Shaped audio must be generated**, which is what the
> rest of this document designs. The 17.5 s/pass and no-`malloc` properties were real and
> are simply unreachable with flash content.



For completeness, because it dominates this design on object churn and is already written
up: `docs/deep/prompt-audio-pump.md` establishes that `FileFind(1, 0xBD75, 27)` +
`StreamFileSource` over `sbc_decoder/sbc_decoder.kap` (69,994 bytes) gives **17.5 s per
pass with no `malloc` at all** — one rebuild every 17.5 s instead of 36 per second, and no
138-word permanent reservation. Its cost is that the content is arbitrary flash bytes,
which cannot be shaped, gain-staged, or made seamless. **If the goal is "loud sustained
brown noise with as little machinery as possible", try the file source first; the design
above is what you need only if the noise has to be *generated*.**

---

## 5. Warning: `fn_12e1a` is unsafe on a connected sink, and its `0` is ambiguous

`fn_12e1a` (`0x12e1a .. 0x12e37`, 29 words, 13 callers) decodes as:

    0x12e1d:  p = SinkMap(sink)
    0x12e23:  c = SinkClaim(sink, size)
    0x12e26:  if (c == 0xffff) return 0                   ; documented claim failure
    0x12e2c:  p += c
    0x12e32:  memset(p, 0, size)                          (fn_39480)
    0x12e35:  return p

`sink.h:36-52` says `SinkClaim` returns `0xFFFF` on failure **but returns zero if the sink
is connected to another stream**, and `SinkMap` likewise returns zero when connected. So on
a *connected* sink the `0xffff` test does not fire: `p = 0`, `c = 0`, and the function
**memsets `size` words starting at data address 0** before returning 0.

Consequences for reading the probe result:

- `fn_12e1a` returning 0 on port 3 means **either** the claim was genuinely declined
  (`0xffff`, harmless) **or** the sink was connected at that moment (and low data space was
  scribbled). The two are indistinguishable from the return value alone. Which one happened
  depends on whether a transform was live on port 3 when the probe ran — **this is the
  single highest-value thing to re-check in the probe's source.**
- `fn_12e1a` demonstrably works on an unconnected sink: `fn_188ea` (`0x188ea .. 0x18908`)
  uses it to write 3 bytes to USB endpoint `0x81` and then `SinkFlush`es them. So the helper
  is not broken; the port-3 result is about port 3 or about connectedness.
- **Use `SinkSlack(ksink)` instead.** It is read-only, it cannot scribble, and 0 vs non-zero
  answers the question cleanly. `SinkClaim`'s header also warns it "will block VM
  application if there are not sufficient buffer memory resources" — another reason to
  probe with `SinkSlack` first.

If `SinkSlack(ksink)` turns out to be non-zero on an *unconnected* port 3, then the
`fn_14a19` pattern (§2d) becomes available on the tone port — `SinkSlack` ->
`StreamRegionSource` -> `StreamMove` -> `SinkFlush`, self-clocking, no transform, no
`SourceClose`. It is worth testing, but note it would carry **16-bit PCM at 0.5 samples per
word** instead of ADPCM at 2.0 (§1), so a 128-word buffer would hold 8 ms rather than 32 ms
— a 4x worse cadence problem. **The transform is worth keeping even if the claim works.**

---

## Confidence summary

| claim | confidence |
|---|---|
| `StreamRegionSource(ptr, n)`: n words in, n bytes out, one byte per word, low 8 bits | **proven** — `fn_06c61` `0x06c99`/`0x06ca5` store high and low bytes to `buf[0]`/`buf[1]`, and `0x06cbb` passes `len+2` after `malloc(len+2)` |
| 2 samples per byte (IMA ADPCM, 4 bits/sample); duration_ms = n/4 at 8 kHz | **proven** — probe104's 17,000 -> 4.25 s is arithmetically exact |
| Durations accurate to ~1 ms; a possible <=4-byte stream header is unaccounted for | **negative** — not established either way |
| ADPCM is 4x denser per word of VM RAM than 16-bit PCM | **proven** (follows from the two preceding rows) |
| No trap can rewind or re-read a source; `SourceDrop` is forward-only; no position key in `SourceConfigure` | **proven** — full 151-stub table, full `source.h`, full `vm_stream_config_key` list |
| While a transform holds them, `SourceSize`/`Map`/`Drop`/`Boundary`, `StreamMove`, `SinkSlack`/`Claim`/`Map`/`Flush` all return 0 or fail | **proven** — identical note on all nine traps in `source.h`/`sink.h`/`stream.h` |
| Rewriting the backing buffer under a running transform is legal but useless | **well-supported** — `stream.h:191-207` (no copy) plus the previous two rows |
| The firmware's own answer is *rebuild the source, keep the buffer*, with explicit `free` + `SourceClose` | **proven** — `fn_14a19` `0x14a64`-`0x14ace` and `fn_06aa7` `0x06ab8`-`0x06ad3` |
| `MESSAGE_MORE_SPACE` is live in this build on VM-written sinks | **proven** — `0x18538` acts on it; `fn_188ea` pumps |
| `MESSAGE_MORE_SPACE` carries no actionable information on a transform-fed port-3 sink | **well-supported** — `SinkSlack` returns 0 when connected; `fn_22d7c` `0x22d7f` ignores it |
| `0x8022` does in fact arrive on a port-3 sink | **hypothesis** — inferred from the arm's position first in `fn_22d7c`'s chain |
| Polling `SourceSize` cannot work | **proven** — `source.h:21-28` |
| `STREAM_SOURCE_NOTIFY_WHEN_DRAINED` raises an HQ event, not a VM message | **well-supported** — `stream_if.h:158` |
| Port-3 pipe holds 256 samples = 32 ms @ 8 kHz | **proven** — `TONE_BUFFER_SIZE`, `codec_decoder.h:107` |
| The DSP disarms port 3 after 30 ms of continuous emptiness and sends `0x1080` | **proven** — `$detect_end_of_aux_stream`, `codec_decoder.h:166` |
| The design tolerates one missed tick, not two | **well-supported** — arithmetic over the two preceding rows |
| A repeating `MessageSendLater` is the only workable clock | **well-supported** — by elimination of the other three, each eliminated on cited text |
| `malloc(133)` -> the single 138-word block is the largest reliable allocation on this unit | **well-supported** — `docs/cave-heap.md` pool census + probes 61/81/105/106 vs 103/122 |
| 64-word and 160-word blocks exist only in PMALLOC_EXTRA and have never been requested | **negative** — reachability from the VM `malloc` trap unestablished |
| The 318 block is the app stack arena and is permanently held | **well-supported** — `vm.app` header[09] = 316 words |
| `fn_12e1a` on a *connected* sink memsets from data address 0 and returns 0 | **proven** — `0x12e1d`-`0x12e35` decoded against `sink.h:24`/`:43`/`:66` |
| Whether the port-3 `fn_12e1a -> 0` was a declined claim or a connected sink | **unresolved** — depends on probe state; highest-value re-check |
| The result is brown-weighted noise | **hypothesis** — clamped random-walk integrator |
| A 36 Hz click train from the per-transform predictor reset, removable by shaping each buffer to start and end near zero | **hypothesis** — mechanism is certain, audibility and the fix are not |
