# XAP2 instruction encodings, taken from the compiler

**2026-09-30.** Not inferred, not guessed. The ADK assembler writes the
same program twice — `<out>.xap` in mnemonics and `<out>.app` as linked
words — so lining the two up names every encoding the compiler can emit.
`tools/opcodes.py` does the lining up; `build/opprobe/` is a C program
written to make the compiler emit as wide a spread of instructions as
possible.

**Every row below comes from an alignment the linker's own map confirms**:
a function's pairing is only trusted when the words consumed equal the
`size=` the map reports for it. Twelve functions passed that test, and
across them **no opcode maps to more than one mnemonic** — which is the
evidence that the alignment is right rather than merely plausible.

Regenerate with:

```sh
python tools/opcodes.py build/opprobe/opprobe
```

## Coverage: 100% of the speaker's code

Decoding all **191,358 instructions** in Bose's `vm.app` and checking each
opcode against this table plus the structural rule below: **every one is
named.** Nothing in the image decodes to an unknown opcode.

That was not true when this file was first written — 20 opcodes and 1.47%
of instructions were unnamed. Each turned out to be an unverified
*addressing mode* of a family whose `@abs` form was already verified, so
`build/opprobe/more.c` was written to make the compiler emit them: shifts
and multiplies by a local and through a pointer, `tst` on a local, `nadd`
on a local. The rule then closed the gap rather than being assumed into
it.

## The structure

A word is `operand8 << 8 | opcode8`. A leading run of words whose opcode
byte is `0x00` (and which are not the word `0x0000` itself) is a **signed
prefix chain**: each operand is sign-extended and folded
`v = (v + sext8(a)) << 8`, with the final word's operand added at the end.

For the `ld`/`st`/arithmetic families the opcode decomposes as
`hi<<4 | reg<<2 | mode`, with `reg` = 0 AH, 1 AL, 2 X, 3 Y and `mode` =
0 `#imm`, 1 `@abs`, 2 `@(n,X)`, 3 `@(n,Y)`.

The families that work on the **AH:AL pair** rather than a named register
use the same low two bits for the mode, and bits 2-3 to pick the
operation:

| base | operation | verified modes |
|---|---|---|
| `0x90` | `smult` | `#imm` 0x90, `@abs` 0x91, `@(n,X)` 0x92 |
| `0x94` | `sdiv` (`udiv` with the modifier) | `#imm` 0x94, `@abs` 0x95, `@(n,X)` 0x96 |
| `0x98` | `tst` | `@abs` 0x99, `@(n,X)` 0x9A |
| `0xA0` | `asl` | `#imm` 0xA0, `@abs` 0xA1, `@(n,X)` 0xA2 |
| `0xA4` | `asr` (`lsr` with the modifier) | `#imm` 0xA4, `@abs` 0xA5 |

The `@(n,Y)` members (0x93, 0x97, 0x9B, 0xA3, 0xA7) appear in Bose's image
but the compiler never emitted them for us — GCC loads a local into a
register first. They are named by the rule, not by direct observation, and
that is the one place this table extrapolates.

`0x2n` is shared: modes 1-3 are `st`, and the four mode-0 slots (`0x20`,
`0x24`, `0x28`, `0x2C`) hold branches instead, since storing to an
immediate has no meaning.

## `0x0009` is a modifier, not `clc`

The single most consequential correction here. The project recorded
`0x0009` as `clc` "which precedes `asr` for a logical shift". It is
really a **modifier word that selects the unsigned form of the
instruction that follows**:

| signed form | unsigned form |
|---|---|
| `asr #1` = `01A4` | `lsr #1` = **`0009 01A4`** |
| `asr @m` = `nnA5` | `lsr @m` = **`0009 nnA5`** |
| `sdiv @m` = `nn95` | `udiv @m` = **`0009 nn95`** |
| — | `udiv #n` = **`0009 nn94`** |

Anything that decodes `0x0009` as a standalone instruction will be one
word out of step from that point on, and will then mis-decode everything
after it. This is worth stating plainly because it is exactly what made
`tools/xapemu.py` model the brown-noise integrator as a monotonic ramp.

## The table

| opcode | mnemonic | example | source |
|---|---|---|---|
| `0x00` | `nop` | `0000` | `nop` |
| `0x0B` | `enterl #n` | `FD0B` | frame open, Y += operand |
| `0x0E` | `ld XH,@(n,Y)` | `FF0E` | high half of the 32-bit X |
| `0x0F` | `leavel #n` | `FE0F` | frame close and return |
| `0x10`-`0x1B` | `ld reg,<ea>` | `0500 0015` | `ld AL,@$_g_u` |
| `0x1A` | `ld X,@(table,X)` | `7400 011A` | jump-table fetch |
| `0x20` | `bgt` | `0520` | |
| `0x21`-`0x2B` | `st reg,<ea>` | `F821` | `st AH,@H'fff8` |
| `0x24` | `bge` | `0524` | |
| `0x28` | `ble` | `0528` | |
| `0x2C` | `bcz` | `052C` | |
| `0x35`,`0x38`,`0x39` | `add reg,<ea>` | `E139` | `add X,@$XAP_AL` |
| `0x41`,`0x49` | `addc reg,<ea>` | `0500 0E41` | 32-bit add, high word |
| `0x55` | `sub reg,<ea>` | `0500 0F55` | |
| `0x61` | `subc reg,<ea>` | `0500 0E61` | 32-bit subtract, high word |
| `0x70`,`0x74` | **`nadd reg,<ea>`** | `0070` | `reg = val - reg`; with `#0` it negates |
| `0x80`-`0x88` | `cmp reg,<ea>` | `0788` | `cmp X,#H'0007` |
| `0x91` | `smult @m` | `0500 0191` | signed multiply into AH:AL |
| `0x95` | `sdiv @m` | `0500 0B95` | signed divide of AH:AL |
| `0x99` | `tst @abs` | `0500 0A99` | |
| `0x9A` | `tst @(n,X)` | `029A` | |
| `0x9B` | `tst @(n,Y)` | `109B` | |
| `0x9C` | `bsr rel` | `019C` | target = last word + fold |
| `0x9E` | `bsr rel,X` | `FE00 679E` | indexed call — function pointers |
| `0xA0` | `asl #n` | `01A0` | on the AH:AL pair |
| `0xA1` | `asl @m` | `F8A1` | |
| `0xA4` | `asr #n` | `01A4` | **arithmetic**, sign-preserving |
| `0xA5` | `asr @m` | `0500 0BA5` | |
| `0xB0`,`0xB4` | `or reg,<ea>` | `01B0` | |
| `0xC4` | `and reg,<ea>` | `00C4` | |
| `0xD4` | `xor reg,<ea>` | `FF00 00D4` | `0xE1D1` = `xor AH,@$XAP_AL` |
| `0xE0` | `bra rel` | `04E0` | target = the branch word + fold |
| `0xE1` | `bra @m` | `FDE1` | indirect |
| `0xE2` | `rts` | `00E2` | |
| `0xE4` | `blt` | `05E4` | |
| `0xE8` | `bpl` | `05E8` | |
| `0xEC` | `bmi` | `05EC` | |
| `0xF0` | `bne` | `05F0` | |
| `0xF4` | `beq` | `02F4` | |
| `0xF8` | `bcc` | `05F8` | |
| `0xFC` | `bcs` | `05FC` | |
| `0009 nn94` | `udiv #n` | `0009 0394` | |
| `0009 nn95` | `udiv @m` | `0009 0500 0195` | |
| `0009 nnA4` | `lsr #n` | `0009 01A4` | |
| `0009 nnA5` | `lsr @m` | `0009 F8A5` | |

The memory-mapped register file, from the ADK's own `crt0`:

```
$XAP_AH  EQU H'ffe0      $XAP_UXH EQU H'ffe2      $XAP_UY  EQU H'ffe4
$XAP_AL  EQU H'ffe1      $XAP_UXL EQU H'ffe3
```

so `E139` is genuinely `add X,AL` and `E1D1` genuinely `xor AH,AL`.

## A silicon hazard the compiler hides: `add` then `addc`

The ADK compiles everything with `-mworkaround-b96516`. Diffing the
compiler's output with and without that flag, across four real source
files, the **only** thing it changes is this:

```
    add  AL,@$_g_m+1
    nop                  <-- inserted by -mworkaround-b96516
    addc AH,@$_g_m
    ...
    sub  AL,@$_g_m+1
    nop                  <-- and here
    subc AH,@$_g_m
```

> **An `addc`/`subc` must not immediately follow the `add`/`sub` whose
> carry it consumes.** The silicon needs at least one instruction in
> between, and the compiler uses `nop`.

Bose's image obeys it. Of its **108** `addc`/`subc` instructions, **106
are immediately preceded by a `nop`**, and all 106 form
`add/sub -> nop -> addc/subc` triples. The two that are not have other
instructions separating them from their `add` — in `MessageLoop`, an
`st` and an `ld` do the job.

This matters because cave code is hand-written and gets no such help, and
because the bug is **invisible in the emulator**, which computes the carry
correctly. `tools/cavesim.py` now checks for it statically on every probe
and prints `HAZARD` if it finds one. No probe this project has built is
affected — none of them does 32-bit arithmetic — but the check fires
correctly on a synthetic case, which is the only reason to trust a check
that has never fired in anger.

## What this corrected

| was recorded as | actually |
|---|---|
| `0x0009` = `clc` | the unsigned-form modifier |
| `0x0074` = `neg` | `nadd AL,#imm`; negation is the `#0` case |
| `0xA0`-`0xA7` "look like shifts, unconfirmed" | confirmed: `asl`/`asr` by immediate and by memory |
| `0xF0`/`0xF8` "look like conditional branches, unconfirmed" | confirmed, with the full set `bgt bge ble blt bpl bmi bne beq bcc bcs bcz` |
| `0x91` = `mul AL,@EA` | `smult`, and `0x95` is `sdiv` |

## `brxl`, and how a switch statement is built

Opcode `0x09` is **not** always the modifier. The distinction is the
operand:

| word | meaning |
|---|---|
| `0x0009` | the unsigned-form modifier above |
| `0xFE09` | **`brxl`** — an indexed branch |

Bose's image has 2541 of the first and 318 of the second, and nothing else
at that opcode that survives a real decode. Anything that treats every
`nn09` as a modifier will swallow the instruction after each `brxl`.

A dense `switch` compiles to:

```
cmp  <reg>,#N            ; N entries
bcc  <default>           ; unsigned compare: index >= N falls out
ld   X,@$XAP_AL          ; the index
ld   X,@(JTBASE,X)       ; JTBASE is a DATA address in the const window
brxl                     ; jump to (address after brxl) + X
```

The table lives in the **constant pool**, and each entry is an offset from
the instruction immediately after `brxl`. Verified against the compiler:
`f_switch` in `build/opprobe` has cases 0-3 and 9, and its table reads
`0000 0003 0006 0009 000F 000F 000F 000F 000F 000C` — the five `000F`
entries being the default, exactly as the C source says.

`tools/switchtab.py` resolves them in the speaker's image. There are
**318 switch statements**, and it prints each one's cases and targets.

## What is still open

Two labels in the probe do not align, and neither affects ordinary code:
`$_abort` and `$common_trap_code` come from a shared module that has no
entry in the linker map, and `$_NativePauseForDebug`'s `.xap` body is not
contiguous.

## The `hi=9` family, and 127 branches that were invisible (2026-10-02)

`tools/xapvm/xapvm.py`'s `mnemonic()` could not name **2,395 instructions (35 distinct opcodes)** out
of 191,358. Resolving them took the whole image as the evidence base rather than
guesswork: for each unknown opcode, what precedes it, what follows it, and in what
proportion. That brought the residue to **160 instructions (18 opcodes), 99.92%
resolved**, with no change to `decode()` — the probe assemblers' decode-verify still
passes unaltered.

### `hi=9`: `reg` picks the OPERATION, not a register

Only three of its sixteen slots had ever been named (`0x91` mul, `0x9B` tst,
`0x9C` bsr), which is why the family looked arbitrary. It is regular once you read
`reg` as an opcode extension and `mode` as the addressing mode:

| reg | operation | slots |
|---|---|---|
| 0 | `mul` | `0x90` #imm, `0x91` @abs, `0x92` @(n,X), `0x93` @(n,Y) |
| 1 | `div` | `0x94`–`0x97` |
| 2 | `tst` | `0x98`–`0x9B` |
| 3 | `bsr` | `0x9C` rel8, `0x9E` long |

The evidence, measured over every site:

- **`0x9A` is followed by a conditional branch at 1,022 of 1,029 sites (99%)**, and is
  typically preceded by `ld X,…` — so it is `tst @(n,X)`. `0x99` likewise at 425 of
  430 (98%) → `tst @abs`. `0x98` at 5 of 5 (100%) → `tst #imm`.
- **`0x90` is followed by stores of BOTH `AH` and `AL`** — a 32-bit result — so it is
  `mul #imm`, consistent with the already-known `0x91`.
- **`0x94`/`0x95`/`0x97` are preceded by `clc` at 72%, 100% and 100% of sites** and
  store a single word, matching the project's existing `clc`-then-shift idiom for
  carry-sensitive ops → `div`.

### `hi=A`: `reg` picks asl/asr, `mode` the operand

`0xA0`/`0xA1`/`0xA4`/`0xA5` were known; the family simply extends to modes 2 and 3,
which resolved `0xA2`, `0xA3` (54 sites) and `0xA7` (42 sites).

### `0xE4`, `0xE8`, `0xEC` are conditional branches, and were missing from `_BRANCHES`

Each sits inside a compare-ladder — `cmp AL,#4 ; b?? +10 ; cmp AL,#9` — so its flow
is certain even though the exact condition is not established; they render as
`b?e4` / `b?e8` / `b?ec`. The probe assemblers had already verified branch encodings
across all twelve relative-branch opcodes on hardware, but **`xapvm._BRANCHES` listed
only ten**, so 127 real branches were treated as opaque by register-clobber tracking
and by `listing()`. Now included.

`0x0000` with a zero operand is `nop` (hardware agrees — probe77 wrote three).

### `hi=4` and `hi=6` are `adc` and `sbc` -- and how I briefly "refuted" that

`_OPS` holds `3=add` and `5=sub`, so `4=adc` / `6=sbc` was the obvious reading. My first
test looked for an `add` **immediately** before each `hi=4` site, found **0 of 99**, and I
recorded the reading as refuted. That was wrong, and the way it was wrong is worth
keeping: the compiler emits 32-bit arithmetic as

    add AL,#0xe7ff      low half
    nop                 <-- an intervening word
    adc AH,#0xffff      high half, with carry

so the predecessor is never adjacent. Skipping `nop`s, **`hi=4` follows an `add` at 97 of
99 sites and `hi=6` follows a `sub` at 9 of 9.** The families are `adc` and `sbc`, `reg`
and `mode` as usual, completing `3=add 4=adc 5=sub 6=sbc`.

The lesson is that a test can refute a correct hypothesis for an incidental reason. The
97%-follow-a-`hi=0`-word observation that looked like evidence for a prefix-splitting bug
was just the nop.

`hi=7` remains inferred rather than proven: `0x74` is documented as `neg` and the family
extends by mode, but its 28 sites follow a `ld` 60% of the time and show no carry pattern,
so they render as `neg?`.

**Residue: 24 instructions of 191,358 (0.013%), three opcodes** -- `0x00` with a nonzero
operand (21, stray prefix words), `0x0e` (2) and `0xe1` (1).

## `0x0000` is a prefix, not a nop — and 21 call targets were wrong (2026-10-02)

The last of the unresolved opcodes turned out to be a **decoding bug with consequences**,
not a missing instruction. `decode()` excluded the word `0x0000` from the prefix chain:

    while i < n and (code[i] & 0xFF) == 0x00 and code[i] != 0x0000:

But a prefix carrying operand byte `0x00` *is* the word `0x0000`, so any chain needing a
zero middle byte was cut in half. At `0x07b82` the words `0200 0000 c69c` are **one 3-word
`bsr`**:

| | target |
|---|---|
| correct, folding all three | `0x27b4a` |
| old rule: prefixes split off, `c69c` decoded alone as `bsr -58` | `0x7b4a` |

A different function entirely, and **21 sites were affected**. Folding `0x0000`
unconditionally is safe because standing alone it contributes nothing -- `(val + 0) << 8`
leaves a zero accumulator at zero -- so the following instruction's *value* is unchanged
and only its length differs. That also matches the hardware, where probe77's three `0x0000`
words behaved as nops: a prefix contributing zero is indistinguishable from one.

**Residue: 3 instructions of 191,224 (0.0016%)** -- `0x0e` x2 and `0xe1` x1, which are an
adjacent pair at `0x00294`/`0x00295` plus one more, immediately before an `enterl -3`, so
they are almost certainly a function-entry idiom rather than a gap.

Effects of the fix, all verified: **5,676 function entries -> 5,663** (spurious entries from
mis-decoded `bsr` targets removed), **8,282 redirectable sites -> 8,295** (3-word forms now
recognised), and `fn_00846`'s caller moves from `0x1778` to `0x177a` because the call
instruction genuinely starts two words earlier than thought. Every address this project
depends on is intact: the `cmp AL,#0x4003` gate at `0x00ace`, the hook site `0x10823`, and
the prologues of `fn_00846`, `fn_1061b`, `fn_0df7f`, `fn_12e1a`, `fn_00ec2`, `fn_31e6f`.

### `decode()` now takes `fold_zero`, and a cave needs it False

A cave is written into the const pool's **zero runs**, so with folding enabled the thousands
of leading zeros ahead of it absorb into its first instruction and that instruction's
address stops being a decode boundary -- which is exactly what the probe assemblers'
decode-verify asserts. Inside a cave a `0x0000` is padding we emitted, never a prefix, so
all 97 assemblers now call `xapvm.decode(patched, fold_zero=False)`. Analysis keeps the
default. Both readings are correct in their own domain, which is why the parameter exists
rather than one of them winning.

**Update 2026-10-12 (firmware study).** The residue opcodes counted above as 0x0e x2 and 0xe1 x1 are the common trap tail: 0x0E is `ld XH,@(n,Y)` and 0xE1 is `bra @abs` (ADK assisted-crt0 `common_trap_code`, words `002B FC19 FF2B FF0E FDE1` at 0x291..0x295), not a function-entry idiom. `docs/FACTS.md` F166, FS-C44.
