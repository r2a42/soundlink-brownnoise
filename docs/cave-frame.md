# `enterl -k` reserves the top two frame slots

**2026-10-01.** Every cave in this project used `enterl -8` and treated all
eight frame slots as free. Two of them are not free: they hold the saved return
address. Writing them destroys the return path and the cave dies on `leavel`.

> **`enterl -k` reserves slots `k-2` and `k-1` for the 2-word code-relative
> saved return address. Usable slots are `0 .. k-3`.**

This cost **seven crashes and six owner presses**, and it was misdiagnosed twice
— first as a bad opcode in a hand-transcribed generator
(`docs/roadmap.md` Step 2), then as an unusable `malloc` pointer (probe80).

## Proof 1: every probe's slot usage against its outcome

| probes | frame slots stored to | result |
|---|---|---|
| 59-62, 64-67, 70, 71, 74-77 | **0..5 only** | **all survived** |
| 68, 69, 72, 73, 78, 79, 80 | **include 6 or 7** | **all crashed** |

Twenty probes. The only exception is **probe63**, which crashed for a separate
and already-established reason: `StreamConnect` to the codec sink, which Bose's
engine holds (`docs/bose-audio-path.md`).

Regenerate with the slot census in `tools/cavesim.py`'s `hazards()`.

## Proof 2: Bose's own code generation

Of **3,446** functions in `vm.app` that have an `enterl -k` and at least one
store to `@(n,Y)` with `n < k`:

```
   2 top slots untouched :  3208 functions
   3 top slots untouched :    64
   4 top slots untouched :    59
   5 top slots untouched :    56
```

**3,208 leave exactly the top two alone, and none violates the rule.** The three
apparent violations (0x39E08, 0x3DD5B, 0x3E016) are all at or above 0x39BE2 —
the constant pool — so they are data being decoded as instructions, not code.

## Proof 3: the compiler's own leaf functions

`build/noiseprobe/noise.c` compiles to a leaf with `enterl -2` whose only local
lives at **`@(-1,Y)`** — *below* the frame — and whose third argument is read at
`@(2,Y)`. With `k = 2` there are **no usable positive slots at all**, so the
compiler has nowhere else to put a local. That had looked like an oddity of the
lift; it is the rule showing through.

It is also consistent with the argument ABI (`docs/trap-abi.md`): a callee's
incoming argument `n` sits at `@(k + n, Y)` where `k` is the **callee's** frame
size, which is why Bose's caller at 0x1E09F writes `@(0,Y)..@(3,Y)` and the
callee with `enterl -13` reads `@(13,Y)..@(16,Y)`.

## The guard

`tools/cavesim.py` now reports this as a hazard, and it discriminates perfectly:

```
flagged:  probe68, 69, 72, 73, 78, 79, 80      (every unexplained crash)
clean:    probe59, 60, 61, 62, 63, 64, 65, 66, 67, 70, 71, 74, 75, 76, 77
```

Run `python tools/cavesim.py <probe>` before every flash. It would have caught
this the first time probe68 was built.

## What it invalidates

- **`docs/roadmap.md` Step 2 was aimed at the wrong target.** The generator was
  never broken by transcription, and no single opcode was ever at fault. The
  six-press bisect of probes 68-73 was measuring a frame bug.
- **probe80's reading was wrong too.** `malloc`'s pointer is not the problem;
  Bose's own `malloc` sites do exactly what probe80 did (`ld AL,#1`,
  `bsr 0x26`, `st AL,@(n,Y)`, `ld X,@(n,Y)`, `st AL,@(0,X)`), 81 of them.
- **`tools/liftfn.py` remains worth having** — compiling beats transcribing
  regardless, and it caught a 12 dB gain error and a re-seeding bug in
  simulation — but it did not fix, and was never going to fix, the crash.

## The rule for caves from here

Use `enterl -16`. It costs 8 more words of stack than `enterl -8`, gives slots
`0..13`, and leaves room for nested calls. Bose's own functions go to
`enterl -37` and beyond, so a 16-word frame is unremarkable.
