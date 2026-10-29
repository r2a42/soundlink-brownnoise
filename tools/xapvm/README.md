# xapvm: reading CSR VM application images

`xapvm.py` reads `vm.app` files (magic `BIGvmApp`, 24-word header, then
code, then constants), in either the linker's text form or the packed
little-endian binary form found in a DFU filesystem. It decodes just
enough XAP2 to find firmware trap calls and constant arguments.

```sh
python xapvm.py <vm.app>                         # every Pio* trap call, constant args
python -c "import xapvm; xapvm.listing('<vm.app>', 0x1460, 0x1500)"   # partial disassembly
```

## How the encoding was learned

No XAP disassembler ships with the ADK. Encodings were read off our own
probe programs (`adk/work/probe`), compiled with the ADK's
`xap-local-xap-gcc`, linked with its `ld`, and compared to the `.s`
output and the linker map. Every probe call site and argument decodes
correctly.

| Fact | Evidence |
|---|---|
| word = operand8<<8 \| opcode8 | all probe instructions |
| opcode 0x00 is a prefix; every operand byte is sign-extended and summed at its position | `5600 7814` = ld AL,#0x5678; `AC00 CD10` = ld AH,#0xABCD; far `bsr` in Bose's app: 3522 stub hits with this rule, 0 without |
| low 2 bits = mode (#, @abs, @(n,X), @(n,Y)); bits 2-3 = reg (AH, AL, X, Y); high nibble 1 ld, 2 st, 8 cmp, C and | probe2 |
| 0x9C bsr rel (target = last word + operand), 0xE0 bra, 0xF4 beq, 0x0B enterl, 0x0F leavel | probe, probe2 |
| the word 0x0000 is not a prefix; it decodes as its own one-word instruction | the stub at 0x20e (`FD0B 0100 9F18 0000 7FE0`) |
| 32-bit arg 1 in AH:AL, arg 2 at @(0,Y) high / @(1,Y) low | probe |
| trap stub `FD0B [prefix] nn18 [0000] [prefix] xxE0` (enterl -3; ld X,#nn; bra) with nn = trap number | linker map of probe |

`traps.json` (272 entries) is the trap-number table extracted from the
ADK's `vmbuilder.exe`. It was checked against the five traps in the
probe map. Bose's `vm.app` has 151 stubs; every one maps to a named
sink-app trap, with no trap number repeated. (An earlier matcher that did
not require the `bra` also counted 16 ordinary functions, giving 167
"stubs" with duplicate `free`/`malloc` and one unknown number.)

Unknown opcodes print as `?xx`. `a0`-`a7` look like shifts and `f0`/`f8`
like conditional branches, but these are unconfirmed.

`args()` tracks AH/AL and `st AH/AL,@(n,Y)` over the 8 instructions
before each call. Non-immediate loads, `and`, `a0`-`a7`, `bsr` and `bra`
invalidate what they may overwrite; `enterl`/`leavel`/writes to Y drop
the stack slots. `(window has other ops)` marks a reported constant that
an unmodelled opcode came after and might have changed.

## Full opcode table (2026-09-27, probe3/probe4/probe5 — validated)

Probes built with `xap-local-xap-gcc` (needs `-I<libdir>` for
`native_if.inc` + a local copy of `assisted-crt0.o`/`native_if.inc`;
see `adk/work/probe/`). Every entry below is verified against `.s`
ground truth and, where noted, executed correctly in `tools/xapemu.py`.

| opcode | instruction | notes |
|---|---|---|
| 0x1n | ld reg,<#imm,@abs,@(n,X),@(n,Y) | n = op&3 mode; reg = op>>2 &3: AH,AL,X,Y |
| 0x2n | st reg,... | same modes |
| 0x3n | add | `e035` = add AL,@AH |
| 0x5n | sub | |
| 0x8n | cmp | C=1 iff reg<val (borrow), Z=1 iff equal |
| 0xBn | or | |
| 0xCn | and | |
| 0xDn | xor | `ffd4` = xor AL,#-1 (not) |
| 0x74 | neg | |
| 0x91 | mul | 16x16 -> AH:AL |
| 0xA0 | asl #n | shifts the 32-bit AH:AL pair (`10a0 0ea4` = *4) |
| 0xA4 | asr #n | logical if CLC (0x0009) precedes, else arithmetic |
| 0xA1/0xA5 | asl/asr @count-reg | count in UXL (`e3a1`, `e3a5`) |
| 0xE2 | rts | |
| 0x0B | enterl v | Y += v (frame alloc; v<0) |
| 0x0F | leavel v | Y -= v AND returns (framed functions end in leavel) |
| 0x0E | TRAP | common dispatcher at 0x291: st X,@(0,Y); trap fires with number at (0,Y) |
| 0x9C | bsr rel | target = word_after + operand (2-word) |
| 0xF0 | bne | target = branch_word_addr + operand (1-word, NO +1!) |
| 0xF4 | beq | |
| 0xF8 | bcc | C==0 |
| 0xFC | bcs | C==1 |
| 0x20 | bgt | signed > |
| 0x24 | bge | signed >= |
| 0x28 | ble | signed <= |
| 0x2C | bls | unsigned <= (C or Z) |
| 0xE4 | blt | signed < |
| 0x9B | tst @(v,Y) | |
| 0x9A | tst @(v,X) | Z from memory at X+v (vm.app, inferred from % print) |
| 0x90 | (byte extend?) | vm.app f593/f5b1 only; value flows unchanged |

**Branch target bias**: 1-word branches use `target = branch_addr + sext8(v)`
(probe3 `f_c_bit` beq/bra, probe5 `f_bitloop` beq/bra/bcz all match; the
after-instruction bias misroutes and loops forever). `bsr` (2-word) uses
`target = word_after_instruction + sext8(v)`.

**vm.app segment map** (header words, probe3-calibrated): [4]=0x18 code
start, [6]=code words (0x9be2), [7]=const words (0x5f9b), [8]=global
words (0x240), [18]=code+const end (0xfb95); image continues to 0x3fb95
(a third segment — the string literals live there). Data addressing is
flat image-word indexing (`ld AL,@0x8bd9` reads image word 0x8bd9).

**Remaining unknowns**: 0x99/0x9A exact family semantics, 0xE8 (seen in
vm.app `f5e8`), P1/straps segment addressing, emulator needs app-init
context (globals/heap) to run the button dispatch standalone.

## Address-space model (2026-09-27, session 4 — calibrated with probe6)

probe6 (`adk/work/probe/probe6.*`) places const tables at known data
addresses (`$_masktab`=0x7401, `$_bigtab`=0x7407, `$_fmt`=0x740d) and
embeds recognizable content (1111 2222..., "CALIBSTRING"). Result:

- CONST window base = 0x7400 (probe convention, version word at 0x7400).
  file_pos = (0x18 + hdr[6]) + (data_addr - 0x7400). Verified byte-exact
  (bigtab word order: 32-bit values stored lo word first).
- hdr[6] = code words, hdr[7] = const words, hdr[8] = global words,
  hdr[18] = end of the LOADED image. For Bose's vm.app the file is
  0x3fb95 words but the loaded image ends at 0xfb95; the remaining
  0x30000-word tail contains MORE CODE (coherent functions with valid
  trap stubs at e.g. 0x395e7) plus rodata/strings ("chstatus %d
  wakeFromShip", UTF-16 UI strings "ANR/Bass/Alerts") -> vm.app uses
  BANKED code/const space (hdr[5]=3 in Bose's build = bank count?).
  The 17-bit bsr displacements (multi-prefix folding) are REAL and
  reach the tail; do NOT truncate them.
- XAP .LARGE model: X and Y are 32-bit (UX:XL, UY:YL); `@(n,X)` spans
  banks via UX. Bose's table walks (base 0x8175 etc.) depend on the
  bank register set by callers — the flat const mapping reads the
  WRONG data for them. This is the open piece of the memory model.
- bsr in xapemu had an off-by-one (fixed): target = a + ln - 1 + v,
  validated end-to-end through probe5's main -> f_bytesearch with
  seeded globals (idx_out = 4 and 3 exactly).

## Button config data (found, not yet fully decoded)

- The sink button config lives in PS keys (PSKEY_USR10 = 0x0294 =
  the "pskey user 10" translation table per sink_buttons.c) — Bose's
  USR10 (51 words) is in the official DFU's signed app-PS area and is
  readable: `05041e00 05051e00 9600a700 bb00c200 c900d000 05041e00
  8550f100 7c01c702`. USR18 (0x029c) = the logical<->physical
  translation pairs (identity 0..15 in Bose's build). The ADK module
  def (adk/root/apps/sink/module_configurations/sink_button_module_def.xml)
  gives the field layouts (event_config_type = pio_mask16 + vreg:1 +
  chg:1 + state:14 + event:8 + type:8; timing enums 0..13; button
  translation pairs). Decode USR10 + the events USR key against these.
- The runtime event table (code-index ~0x3d28d, tail): 7-word-ish
  entries {0x4000/0x0004, type, action(0x40xx event id OR 0x67xx
  data ptr), 0x00ff, w4, w5, 0} — the 0x67xx pointers are RAM
  addresses of runtime structures; 0x00ff recurring (PIO mask hi?).
- The PIO-change handler walks SIX 4-word entries at data 0x8175
  (types 6/7 = RISING/FALLING) — six logical inputs = six buttons.
  Reading it correctly needs the bank mechanism above.
