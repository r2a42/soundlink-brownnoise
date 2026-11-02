# The VM heap is ten fixed pools, and the largest is 642 words

> **Note on references (public export):** this file cites files from the original private research repository that are not included here; each such path is marked "(not in this export)" at its first mention, and all of them are listed in `docs/NOT-IN-EXPORT.md`. The claims they support are summarised in the text; the cited originals are not needed to rebuild or flash anything.

> ## CORRECTION, 2026-10-08: THIS DOCUMENT IS SOUND, AND IT WAS APPLIED TO THE WRONG PROBLEM
>
> Everything below about the pools is still accurate. **But the pool arithmetic here was used
> to explain the ~6-9 second death of the port-3 audio loop across probes 145, 146, 147, 149,
> 150, 151 and 153, and that was wrong.** probe157 measured the real cause:
> `KalimbaSendMessage(0x1072)` returns FALSE about seven seconds after the press, i.e. **the
> DSP is gone.** Entering pairing tears down A2DP and takes `sbc_decoder` with it, and the
> teardown runs in `fn_0d500` — called at `0x00ac2`, two instructions *before* the 0x0AE0 hook
> — so the cave cannot prevent it.
>
> The clue that should have ended it sooner: **probe155 allocated exactly one source and one
> transform, nothing repeating, and still stopped at seven seconds.** No pool could have been
> exhausted. When five unrelated architectures produce the same number, the number belongs to
> something none of them changed.
>
> Two measured facts from that arc belong here, because they bound what this document's advice
> can achieve: **`TransformDisconnect` on a stored transform handle reclaimed nothing**
> (probe151, ~55 ticks unchanged), and **`SourceClose` on a region source returns FALSE** --
> `source.h:124-126`, "some sources ... have a lifetime defined by other means, and cannot be
> closed using this call" (probe153, measured on the first tick). **The VM cannot explicitly
> reclaim either object in that chain.** Use this document for sizing `malloc`, not for
> explaining audio that stops.

**2026-10-02.** Settled statically, after three probes guessed at `malloc` sizes and
two firmwares crashed from a leak this explains.

## The pools

`PSKEY_PMALLOC_APP` (0x215F) in `firmware/bose/minnow_3.0.3/Minnow_3.0.3_stack_plus_app.dfu` (not in this export)
defines the VM app pools as *(element size in words x count)*:

    4x27   16x68   32x13   46x4   94x2   100x3   100x1   138x1   318x1   642x1

= 3,482 words, plus a BASE pool of 4,280 and an EXTRA pool including 64x5, 94x2, 160x2.
`malloc(n)` rounds up to the smallest **free** pool whose element size is >= n
(`pskeys.txt:12787`: "n_elements each of size el_size in 16-bit words").

## What that predicts, and what it explains

| request | pool it needs | observed |
|---|---|---|
| 1024 | none exists | probe61: refused, no fault |
| 512 | the single **642** | probe82 OK with music playing; probe103 returned 0 with music paused |
| 254 | **318**, else 642 | probe107 |
| 128 | **138**, else 318/642 | probes 61, 81, 105, 106: reliable |

The 318-word block is almost certainly the app stack arena -- `vm.app` header[09] is
316 words (`docs/message-task-abi.md`, `tools/stackdepth.py`) -- so in practice the
only large transient block is **one** 642.

> **A cave gets at most one allocation above 138 words, and only if nothing else
> holds the 642 block.** Anything bigger than 642 words cannot be allocated at all.

`VmGetAvailableAllocations` cannot measure this: `vm.h:23-34` says it returns "the
number of free slots", and Bose uses it at `0x1E087` as `cmp AL,#2` before loading a
DSP -- a block *count*, not a size.

## The leak that crashed probe105 and probe106

**`TransformDisconnect` does not free the attached source.** Bose's own teardown is
four calls in order (`vm.app` 0x31E6F-0x31E90 and 0x31F49-0x31F65):

    TransformFromSink -> TransformStop -> TransformDisconnect -> StreamDisconnect

and the voice-prompt plugin pairs it with an explicit close
(`adk/root/src/lib/csr_voice_prompts_plugin/csr_voice_prompts.c:238-243`):

    if (SourceIsValid(source)) { StreamDisconnect(source, NULL); SourceClose(source); }

`voice_prompt_file.c:44,60` closes every region/file source it finishes with. The
only auto-disposing path is `StreamConnectAndDispose` (`stream.h:608-629`), which is
not what `TransformAdpcmDecode` + `TransformStart` uses.

probes 105 and 106 rebuilt the transform every 28 ms and never called `SourceClose`.
Because they refilled *early* by design -- 28 ms against 31.5 ms of buffered audio --
the region source had not drained either, so `stream.h:199-203`'s "only exists while
the data is being read" never reclaimed it. **One source stream leaked per cycle, 36
a second.** Our own allocations then fail gracefully, but Bose's go through
`PanicNull`, and a prompt allocates -- hence press 3 crashing and rebooting.

> Any refill design must call **`SourceClose` on the previous source every cycle**,
> and should let the source drain before tearing the transform down.

## Bose's canonical teardown, decoded (2026-10-02)

`fn_31e6f` (34 words, called from `0x317d7`) is the firmware's own transform teardown, and
it is the recipe any refill design must copy. Fully decoded:

    t = TransformFromSink(sink)        sink read from the plugin struct at @(2,X)
    if t:
        TransformStop(t)               <-- probes 105/106 omitted
        TransformDisconnect(t)
    StreamDisconnect(0, sink)          <-- UNCONDITIONAL, AL=0 (no source), AH=sink
    struct[2] = 0                      <-- zero the stored handle

Three details that matter, each one a thing probe105 or probe106 got wrong:

1. **`TransformStop` precedes `TransformDisconnect`.** Both probes called only
   `TransformDisconnect`.
2. **`StreamDisconnect(0, sink)` is called even when no transform was found** — it breaks
   any stream pairing left on the sink. Neither probe called it at all.
3. **The stored handle is zeroed immediately after.** probe105 cached a transform in
   `buf[1]` and only rewrote it on full success, so every bail path left a handle to a
   destroyed transform that the next refill would disconnect — potentially whatever
   inherited that id.

`SourceClose` is not in this function; it lives in the voice-prompt plugin's
`DisconnectAndCloseSource` (`csr_voice_prompts.c:238-243`), which pairs
`StreamDisconnect(source, NULL)` with `SourceClose(source)`. A refill design needs both
halves: this teardown for the sink side, and `SourceClose` for the region source it
created, because `TransformDisconnect` does not free it.

All five traps are callable: `TransformFromSink` 0x14a, `TransformStop` 0x13a,
`TransformDisconnect` 0x13e, `StreamDisconnect` 0x10e, `SourceClose` 0x126.
