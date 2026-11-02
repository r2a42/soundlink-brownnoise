# Hook sites: the whole image, disassembled, and a better place to stand

> **Note on references (public export):** this file cites files from the original private research repository that are not included here; each such path is marked "(not in this export)" at its first mention, and all of them are listed in `docs/NOT-IN-EXPORT.md`. The claims they support are summarised in the text; the cited originals are not needed to rebuild or flash anything.

**2026-10-02.** Written after probes 103-108 were built on a hook site nobody had
read. `tools/disasm.py` now decodes the entire image in one pass.

## What exists now

    python tools/disasm.py              # all three artifacts
    python tools/disasm.py --fn 0x846   # one function
    python tools/disasm.py --hooks      # just the redirectable-site report

| artifact | contents |
|---|---|
| `build/analysis/full-disasm.txt` (not in this export) | 11.7 MB: **191,358 instructions over all 236,514 code words**, grouped into **5,676 functions**, every branch/call target resolved, **151 trap stubs named from the BlueLab 7.3 table** |
| `build/analysis/xref.json` (not in this export) | callers per function; readers and writers per global (**329** globals) |
| `build/analysis/hook-sites.txt` (not in this export) | **8,282 redirectable call/branch sites** |

The 7.4 trap names in `build/analysis/functions/*.lst` are wrong
(`docs/trap-numbering.md` (not in this export)); this supersedes them.

**A site is "redirectable" when every operand byte of the instruction falls inside a
DFU blind window**, so its target can be rewritten without disturbing a byte the RSA
signature covers. That is the property that made `0x0AE0` the original hook. There are
8,281 others.

## Why the old hook kept not running

Independently reproduced by `tools/disasm.py --fn 0x846`:

    0x00acd: 0c17        ld AL,@(12,Y)      <- the incoming event id
    0x00ace: 4000 0384   cmp AL,#0x4003     <- EventUsrEnterPairing
    0x00ad0: 0300 44f0   bne +836  -> 0x00e14

> **The cave at `0x0AE0` only ever ran on EventUsrEnterPairing.** The trigger was
> never "long-press the Bluetooth button"; it was "long-press while that press means
> enter pairing". A second long-press, with the speaker already in pairing mode,
> produces a different event and some other handler speaks id `0x00`
> "ready to connect" -- which is exactly what the owner reported, twice, and what
> probe82 saw a week earlier.

`cmp AL,#0x4003` at `0x00ace` is **not** blind, so the test cannot be retargeted. The
site is intrinsically single-event. `bose-firmware-anatomy.md` §7 claimed that exiting
with `X = 0xAED` + `rts` makes "every long-press reach the cave"; that is **false** --
the decision happens upstream of `0x0AE0`, on the previous press.

## The better site: 0x10823, the button-event dispatch

`fn_1061b` (entry `0x1061b`, `enterl -22`, sole caller `0xf77e`) is the 193-case
button dispatcher that turns a physical press plus state into a `0x40xx` message.
Its general dispatch tail:

    0x1081e: 0014        ld AL,#0x0
    0x1081f: 0027        st AL,@(0,Y)        message = 0
    0x10820: 0500 1214   ld AL,#0x512        task
    0x10822: 1313        ld AH,@(19,Y)       THE COMPUTED EVENT ID
    0x10823: 0300 8e00 b89c  bsr -> fn_395dd      [BLIND: all 3 operand bytes]

Hooking `0x10823` gives what `0x0AE0` never could:

- it runs for **every** button event that reaches this dispatch, with no event gate;
- the **event id is in AH** on entry (and in the caller's slot 19), so a cave can
  filter on it -- and can *report* it, which identifies every button/press
  combination including the centre button;
- the displaced call is `fn_395dd(task=AL, id=AH, message=@(0,Y))`, so a cave
  preserves stock behaviour by making that same call, exactly as the `0x0AE0` cave
  calls `0xE06D`.

The sibling at `0x107be` is also redirectable but sends a hardcoded id (`0x6760`), so
it is specific to one event. `0x1061e`, right after the prologue and before the
switch, is redirectable but only **2 words** -- it cannot reach the cave at
`0x3E21D`, 187,391 words away.

## Diagnosis without the stock post-flow

`0xdf7f` -- the prompt engine -- is directly `bsr`-able from a cave: **id in AL,
nothing required in X, and it returns** (it does its own `enterl -7`). So a cave at
any site can speak its own id. The `0x0AE0` caves spoke by letting the stock flow at
`0x0AE4` run, which also executed the post-flow (`0x503` write, `0x56b` bit 11); that
is no longer necessary.

## Other candidates worth knowing

| site | fires on | notes |
|---|---|---|
| `0x10823` | every button event via the general dispatch | **recommended**; event id in AH |
| `0x00ec9` | every message into the VA handler `fn_00ec2`, before any event test | centre/VA family; `enterl -11`, event id in AL then slot 3 |
| `0x00edd` | — | `cmp AL,#0x4002` with **blind operands**: the event test itself is editable here, unlike at `0x00ace` |
| `0x00ae4` | the stock prompt call | redirectable; a way to intercept prompts |
| `0xe1a` | the `0x4004` arm in `fn_00846` | dead `bra 0xe45`, but **1 word**, so unreachable to the cave |

## The button-event table, decoded (2026-10-02)

`fn_1061b` dispatches on `(button_code - 16)` through a 193-entry jump table at **data
`0x92E7`** (const word `0x3bac9`). The entries are 16-bit **offsets** from a base of
**`0x1063F`**, confirmed by the default: offset `0x1EA` -> `0x10829`, exactly the `bcc`
out-of-range target. **159 of the 193 go to that default, so only 34 cases are real.**

Note that the word at `0x1063F` (`0xfe09`) is the **computed jump** -- `PC = 0x1063F + X`
-- which `xapvm` renders as `clc -2`. Another decoder gap, and the one that hides every
switch dispatch in the image.

The events reachable from the table: `0x4003`, `0x4004`, `0x400d`, `0x400e`, `0x403c`,
`0x4045` (x2), `0x4047`, `0x4048`, `0x4089`, `0x408a`, `0x408f`, `0x4098`, and ten
`0x67xx`. Reproduce with the script in the session scratchpad, or re-derive from
`build/analysis/full-disasm.txt`.

### The two that matter

| button code | case | event | gated? | body |
|---|---|---|---|---|
| **`0x21`** | 17 | **`0x4003`** EventUsrEnterPairing | — | the only source of the one event the `0x0AE0` cave runs on |
| **`0xC5`** | 181 | **`0x4004`** EventUsrInitateVoiceDial | **no** | `0x107a9`, sends at **`0x107be`** |

    0x107a9:  ld AL,#0x0 ; st AL,@(0,Y)     message = 0
    0x107ab:  ld AL,#0x512                  task
    0x107ad:  ld AH,#0x4004                 the event
    0x107af:  bra -> 0x107be
    0x107be:  bsr -> fn_395dd               [BLIND: all 3 operand bytes writable]

> **`0x107be` is the hook this project should have been using.** It is a 3-word
> redirectable `bsr`, it fires on the centre/voice-assistant button **unconditionally**
> -- no `0x59e` state test anywhere on the path -- and the event id arrives in `AH`, so
> a cave can filter. Contrast `0x0AE0`, which is gated to a single event by a `cmp`
> whose operands are not blind and therefore cannot be retargeted.
>
> The displaced call is `fn_395dd(task=AL, id=AH, message=@(0,Y))`, so a cave preserves
> stock behaviour by replaying it -- with the message word written into **its own**
> slot 0, since `fn_395dd` reads the caller's frame.

`0x107be` is shared with one other path (`0x107b0`-`0x107bd`), which *is* state-gated:
it requires `0x59e` to be 3 or 0xd and emits `0x6760`. Filtering on `AH == 0x4004`
separates them.

### Why presses stopped reaching the cave

Case 17's path has no state test either, so **button code `0x21` always emits
`0x4003`**. The state dependence is therefore not in `fn_1061b` at all -- it is upstream,
in whatever assigns the *code* to a physical press (`fn_1061b`'s sole caller is
`0xf77e`, inside `fn_0f5f7`). That is the remaining piece, and it stops mattering once
the hook moves to `0x107be`.

## Correction (2026-10-02, after probe114's first press): ungated *given* `0xC5`

probe114 was pressed with **nothing connected** and produced **no sound at all**, though
every one of its paths speaks. The redirect is installed correctly — the bytes read back
from the device, `0300 da00 5d9c`, fold to the cave at `0x3E21D` — and prompts were left
stock, so the engine was available. The instruction at `0x107be` was simply not executed.

So this page's claim that the hook "fires on every centre-button press regardless of
pairing or connection state" is **wrong**, and was wrong in a specific way worth keeping.
What the disassembly shows is that once the dispatcher reaches **case 181, button code
`0xC5`**, no state is tested before the send. The gating lives **upstream**, in which
button *code* the button manager emits. `0x4004` is `EventUsrInitateVoiceDial` and voice
dial needs a phone, so with nothing connected a centre press plausibly never becomes
`0xC5`.

**Ungated given `0xC5` — not ungated given a press.**

Also worth recording: **no probe at `0x107be` has ever been confirmed to fire.** Every
owner-heard prompt in this project came from the old `0xAE0` hook (probes 89, 90, 98, 99,
100, 102). `0xAE0` is gated to `EventUsrEnterPairing` (`0x4003`) and so is reached by the
pairing button, but it is the only hook with confirmed fires and it is where the
`TaskData` + `MessageSendLater` + handler machinery was proven.

## The hook to use for a button that works with nothing connected: `0x10823`

Established 2026-10-02 after probe114's silent press. The keypress dispatcher `fn_1061b`
(confirmed by its own log string `"TAP: kp - 0x%02x"` at const `0x93C1`) has exactly **two**
`fn_395dd` send sites:

| site | event source | `sinkState`-gated | redirectable |
|---|---|---|---|
| `0x107be` | `bra`-in from the `0xCx` case bodies | **yes** | yes |
| **`0x10823`** | `AH = @(19,Y)`, the accumulated event | **no** | **yes — all 3 operand bytes blind** |

Every `0xCx` body starts with `fn_0d475()` — three words, `ld AL,@0x59e ; rts` — and bails
unless the result is **3 (`deviceConnected`)** or **13 (`deviceA2DPStreaming`)**. With
nothing connected the state is **1 (`deviceConnectable`)**, so those cases bail to
`0x1082b` and divert to `0x1083b`, reaching no send at all. Values resolved against
`adk/4.3.1/app/apps/sink/sink_states.h`.

`0x10823` is the dispatcher's **common exit**: it sends whatever event the keypress
resolved to, after the per-case checks have already passed, so it fires for any button that
produces an event in any state. Same call shape as `0x107be`
(`fn_395dd(task = 0x512, id = AH)`), so existing replay logic transfers unchanged.

**Redirect:** `v = 186872`, operand bytes **`03 da f8`** against the stock encoding.

Use `0x10823` when the trigger must work standalone; `0x107be` only when a device is
connected. `0xAE0` remains the one with six confirmed fires, gated to
`EventUsrEnterPairing`.
