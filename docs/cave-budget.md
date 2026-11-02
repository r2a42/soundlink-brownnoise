# How much cave space there is

> **Note on references (public export):** this file cites files from the original private research repository that are not included here; each such path is marked "(not in this export)" at its first mention, and all of them are listed in `docs/NOT-IN-EXPORT.md`. The claims they support are summarised in the text; the cited originals are not needed to rebuild or flash anything.

**2026-09-30.** Measured, because probe58 turned out to be using most of
it and the next design needs to know.

## The budget today: about 197 words

A cave has to live in the constant pool (it is flash, it is executable via
`bsr`, and it is data-addressable at 0x7400 — `docs/message-task-abi.md`),
in regions Bose does not use, and only 29 bytes of every 64 are writable
at all.

> **2026-10-04: this 197-word figure is the SAFE one, and it is now enforced.** The probe
> assemblers were at some point widened to scan the whole const pool with a 16-word
> threshold, advertising **262** writable words. probe130 used 234 of them and **crashed
> the speaker on boot**: 55 words landed in zero gaps inside live tables, one of which
> (`0x8280`) is loaded by `fn_0aaa1` at `0x0aaa5` and shipped as a message payload. Caution
> #1 below had warned of exactly this and was never wired into the assembler. It is now:
> `tools/caveguard.py`, called from `tools/preflight.py`.

The probe assemblers scan `0x3E200..0x3E400` for zero runs of 40+ words.
That window holds three:

| run | words | **writable** |
|---|---|---|
| `0x3E211..0x3E2A0` | 143 | 59 |
| `0x3E2BA..0x3E356` | 156 | 70 |
| `0x3E362..0x3E400` | 158 | 68 |
| | | **197** |

The layout machinery stitches them together with `bra` connectors, which
is why probe58's 143 words span `0x3E21D..0x3E384` across all three.

> **probe58 uses 143 of the 197. There are ~54 words spare.**

Enough for a sustain probe — a const `TaskData` is 2 words, a
`MessageSendLater` call about 12, and a handler that reuses the existing
generator perhaps 30 more — but not enough to be careless with.

## The next 65 words are free

Four more zero runs sit outside the scanned window:

| run | words | writable |
|---|---|---|
| `0x3DF6F..0x3DF9E` | 47 | 15 |
| `0x3DF9F..0x3DFCE` | 47 | 26 |
| `0x3EAD2..0x3EAF2` | 32 | 14 |
| `0x3AA51..0x3AA67` | 22 | 10 |

> ## ⚠ THIS PARAGRAPH CAUSED A CRASH. The four runs above are NOT free.
>
> It used to read: *"Widening the assemblers' scan window picks these up for free. **262
> writable words** exist in zero runs of 16+ words across the whole image."* The scan was
> duly widened, and on **2026-10-04 probe130 used 234 of those words and crashed the
> speaker on boot** ("battery one hundr—" then reboot, repeating).
>
> **The runs above are read at runtime.** `tools/caveguard.py` audits each one:
>
>     0x3AA51..0x3AA67   data 0x826F..0x8284   22 w   THREE load sites: 0x0aa30, 0x0aaa5, 0x0aafa
>     0x3DF6F..0x3DF9E   data 0xB78D..0xB7BB   47 w   no immediate loads seen -- still unproven
>     0x3DF9F..0x3DFCE   data 0xB7BD..0xB7EB   47 w   no immediate loads seen -- still unproven
>     0x3EAD2..0x3EAF2   data 0xC2F0..0xC30F   32 w   a loaded pointer sits just below it
>
> `0x3AA51` is the confirmed kill: `fn_0aaa1` at `0x0aaa5` does `ld AL,#0x8280`, and
> `fn_27bab` ships two words from there as a message payload with id `0x66`, from
> connection-manager code that runs as a device connects — concurrent with the battery
> prompt, which is exactly where the crash landed.
>
> **Every one of those words is zero in the official image and inside a DFU blind window**,
> which are the only two things the assembler checked. **Zero does not mean unread**: a
> zero-filled gap *inside a live table* satisfies both and is still read. Caution #1 in the
> next section says precisely this about the string reserve; it was never connected to
> these runs.
>
> **The budget is 197 words, in `0x3E200..0x3E400` only.** `tools/caveguard.py` enforces it
> and `tools/preflight.py` calls it, so a probe outside the window cannot reach a flash. If
> a design does not fit 197 words, **shrink the design, not the rule.**
>
> Also note a dangerous coincidence: **262 is simultaneously the stack headroom at `0xAE0`**
> (316 declared − 54 words of call path). Two unrelated budgets, the same number — and
> `docs/POST-MORTEM-2026-10-04.md` records probe127 being lost partly to *"a 262-word figure
> measured at `0xAE0` weeks earlier"*, i.e. the stack one. When quoting 262, always say
> which.

## The reserve: 1,318 words in unreferenced debug strings

The constant pool holds 729 printable strings (`docs/const-strings.md` (not in this export)).
Cross-referencing every immediate load in the code against them:

- **449 strings are loaded by at least one instruction.**
- **280 are never loaded by any instruction** — 3,001 words, of which
  **1,318 fall in writable blind windows.**

That is 6.7× the current budget. It is real space, but it is not free, and
two cautions decide whether it can be used:

1. **"Never loaded" means never loaded *by an immediate address*.** Some
   strings are table entries reached by computed addressing — the
   two-letter module tags (`ae ao av ba bd ...`) are plainly indexed, and
   each one would count as unreferenced. Any region taken from here must
   be checked for being part of a run of similar short entries, and
   preferably be long and isolated.
2. **The layout machinery requires zeros.** `in_run()` in every probe
   assembler tests for zero words. Placing code in a string region means
   teaching it that a region is usable because nothing *reads* it, not
   because it is blank — a change to machinery that currently has 39
   clean flash cycles behind it.

So: documented as available, not recommended until something needs it.
The order of preference is (1) the 54 words still free in the current
window, (2) widening the window for 65 more, (3) the string reserve.

## What is not available

- **Contiguous space.** Nowhere in the filesystem can 64 consecutive bytes
  be written; the longest writable run is 29 bytes followed by 35
  untouchable (`docs/content-control-analysis.md` (not in this export) §1). This is why a
  `.kap` cannot be installed and why PCM cannot be flashed as data.
- **RAM at build time.** Globals are Bose's. The cave gets RAM only by
  calling `malloc` at run time (stub 0x026, which Bose uses with sizes up
  to 134 words), or by keeping state in its own const words — which are
  read-only at run time.

# Addendum, 2026-10-01: the hard ceiling, measured across the whole image

Two capacity questions that had been assumed rather than measured.

## Total writable zero space in the const pool: **252 words**

Scanning the entire const pool (`a = 0x39BE2 .. 0x3FB7D`, 24,475 words) for zero
runs of 32 words or more:

| `a` range | words | blind/writable | data address |
|---|---|---|---|
| 0x3E362..0x3E400 | 158 | 68 | 0xBB80 |
| 0x3E2BA..0x3E356 | 156 | 70 | 0xBAD8 |
| 0x3E211..0x3E2A0 | 143 | 59 | 0xBA2F |
| 0x3DF9F..0x3DFCE | 47 | 26 | 0xB7BD |
| 0x3DF6F..0x3DF9E | 47 | 15 | 0xB78D |
| 0x3EAD2..0x3EAF2 | 32 | 14 | 0xC2F0 |
| **total** | **583** | **252** | |

The cave already uses the three large runs, which are the ~200 words every probe has
been squeezed into. **There is no large unused reserve** — the remaining three runs
add 55 blind words and are not contiguous with the rest.

## There are no zero runs in the code region at all

Scanning `a = 0 .. 0x39BE2` for zero runs of 40+ words: **zero runs found.** Bose's
code is dense, so the cave cannot be relocated somewhere roomier.

## Why this matters for the remaining routes

A `ringtone_note` array placed in a zero run could in principle be as long as the
*whole run* rather than just its blind words — the 18-of-32 unmodifiable words are
`0x0000`, which decodes as `RINGTONE_NOTE(C0, length 0)`, and whether that is benign
decides everything. But even in the best case the longest **contiguous** array is one
run: **158 words, of which 68 are ours.** Runs are separated by live const data, which
would decode as arbitrary notes and commands — and roughly one word in sixteen is an
`END` (any word matching `0x8xxx` with bits 12-14 clear), so playback through real data
would stop after ~16 words on average.

So the ringtone route is capacity-bound at a couple of seconds of chaotic sequence, not
minutes of anything. **Only a route that gets content out of the signed filesystem
entirely — a runtime partition write, or the DSP generating it — can produce sustained
noise.**
