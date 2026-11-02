Purpose: the one-page hub for the "cave" (our code inside the speaker's own vm.app) and the "hooks" that call it: where code may live, how it is laid out, what the stack and frame rules are, which instruction forms are safe, how a cave owns a message Task, how traps are called, and which hook sites work.

> **Note on references (public export):** this file cites files from the original private research repository that are not included here; each such path is marked "(not in this export)" at its first mention, and all of them are listed in `docs/NOT-IN-EXPORT.md`. The claims they support are summarised in the text; the cited originals are not needed to rebuild or flash anything.

Status / last verified: 2026-10-10 (limits, bands, branch census and stack depth were recomputed on this date by running the repo tools offline; no device was touched).

Read next: docs/FLASH-PROTOCOL.md (gates 1, 1b and 2 are the rules in this hub), then docs/topics/probing-method.md (how a cave is built, simulated and flashed).

> **This is an archival research document from the original (larger, private) project repository.** Some of its internal links point at files not included in this public export; where one doesn't resolve, that's why. The repository's own current, self-contained write-ups are listed in README.md's "Repository layout" section.

Confidence marks: **proven** (an address, instruction, command output or owner press is quoted in the source), **well-supported** (one traced inference beyond a proven fact, or a static reading never seen on hardware), **hypothesis**, **unknown** (the cited file would answer it). Negatives are results. When two sources disagree the newer one wins; section 4 lists the known disagreements.

Terms. "a" is the project's code-relative word address (file word index minus the 24-word header). The "const window" is a = 0x3E200..0x3E400. A "band" is a run of cave-writable words. A "hook" is a 3-word `bsr` in stock code whose target we rewrite to the cave. A "blind" byte is one the RSA signature does not cover (see docs/topics/dfu-and-signing.md).

---

## 1. Summary

We cannot add a file to the speaker. We can only change blind bytes inside Bose's signed filesystem, and 29 of every 64 bytes are blind (docs/deep/offline-2026-10-10/write-constraint.md section 0). The only code we run is therefore a "cave": a few hundred words written into blind bytes of vm.app itself, entered by rewriting one stock call (a hook).

Where the cave lives. The proven home is the const-pool zero padding at a = 0x3E200..0x3E400. It holds three zero runs, and 197 words of them are blind. That figure is a hard ceiling: probe130 used words outside this window and crashed the speaker on boot. A second, explicitly listed region of seven dead AVRCP-browse functions (a = 0x2331e..0x235a9) adds 207 usable code words plus 14 mandatory stub words; it is code-only and is entered only by `bsr`. Nothing else is approved.

Layout. Every probe assembler places the entry jump at a = 0x3E21D, a 2-word TaskData behind it (data address 0xBA3C) and the code after that, and stitches the 16 bands together with 1-word `bra` connectors. Strings and the TaskData must sit in the const window because the code region cannot be read as data.

How it runs. The hook calls the cave from inside a stock function. The cave opens a frame (`enterl -8` is the rule), uses slots 0..5 only, and calls Bose's own traps through the 151 stubs of the BlueLab 7.3 trap table. A cave can also own a message Task: the TaskData is two flashed const words holding the handler address, so `MessageSendLater(0xBA3C, id, 0, ms)` re-enters the cave from the main message loop. That is how a cave outlives the button handler.

Hooks. The Bluetooth-pairing hook at 0x00AE0 carried probes 77 to 171 and was reachable only on the `EventUsrEnterPairing` arm; the pairing teardown that runs two instructions earlier kills the DSP about 7 s later. The current hook is 0x00E46 (`bsr fn_189fb` inside `fn_00846`): a centre-button long press while a device is connected arrives there as event 0x4004. It was proven by probe172 and carries probes 172 to 181. Two other sites (0x107be, 0x10823) were refuted on hardware.

Safety gates. `tools/caveguard.py` enforces the window and the region stubs, and attests that every branch form emitted also occurs in Bose's own code. `tools/preflight.py` calls it, `tools/stackdepth.py` measures stack headroom at the hook site, and `tools/cavesim.py` runs the cave in an emulator. None of these replaces a readback or a press.

---

## 2. KEY FACTS

Source column: paths are relative to the repo root; "recomputed" means this hub's author re-ran the tool on 2026-10-10.

### 2a. Where code may live

| fact | confidence | source |
|---|---|---|
| The cave is limited to the const window a = 0x3E200..0x3E400. It contains three zero runs: 0x3E211..0x3E2A0 (143 words), 0x3E2BA..0x3E356 (156), 0x3E362..0x3E400 (158). | proven | `docs/cave-budget.md` "The budget today"; `tools/caveguard.py` `SAFE_WINDOW`; recomputed |
| The writable (blind) part of those runs is 197 words in 16 bands: thirteen bands of 14 words, one of 9 (0x3E362..0x3E36B) and two of 3 (0x3E29D..0x3E2A0 and 0x3E3FD..0x3E400). Bands recur every 32 words (64 bytes). | proven | recomputed with the assembler's own scan (runs of at least 40 zero words, then the `blind()` test); `docs/cave-budget.md` table sums to 197 |
| A word is writable when BOTH its bytes are blind: `34 <= (2*cw + C0) % 64 <= 60` with `C0 = (0x6e974 + 0x34) % 64 = 40`. The upper bound is 60, not 62, because a word needs two blind bytes. The byte-level rule in `tools/fsedit.py` is 34..62 of each 64-byte block of the filesystem body. | proven | `docs/deep/offline-2026-10-10/write-constraint.md` (not in this export) part (a); `build/hook/assemble_probe179.py` `blind()` |
| No contiguous writable run longer than 29 bytes exists anywhere in the signed image. | proven | `docs/deep/offline-2026-10-10/write-constraint.md` section 0; `docs/cave-budget.md` "What is not available" |
| The cave cannot be relocated to roomier space in the code area: scanning a = 0..0x39BE2 for zero runs of 40 or more words finds none. The whole const pool has 583 zero words in six runs of 32 or more, of which 252 are writable; only the three window runs are approved. | proven | `docs/cave-budget.md` addendum 2026-10-01 |
| NEVER widen the window. If a design does not fit 197 words, shrink the design. | proven (a crash) | `docs/field-log.md:8153` (not in this export) (probe130); `docs/FLASH-PROTOCOL.md` step 1b; memory csr8670-cave-window |
| The second approved place is `CODE_REGION` in `tools/caveguard.py`: seven dead AVRCP-browse functions between a = 0x2331e and 0x235a9 (fn_2331e, fn_23344, fn_2337c, fn_2349c, fn_234fd, fn_23543, fn_23565). 221 writable words, of which 14 are the stub words (2 per function), so 207 are usable. | proven (count) | `docs/deep/offline-2026-10-10/verify.md` (not in this export) V8 "Count"; `tools/caveguard.py` `CODE_REGION` |
| Every function of the region that a probe touches must carry its stub exactly: `0014 00e2` (`ld AL,#0 ; rts`) at a writable entry, or `0014 f50f` / `0014 fa0f` (`ld AL,#0 ; leavel -11 / -6`) at the first word after `enterl` in fn_2337c and fn_2349c. caveguard fails a probe that writes a region word without its stub. | proven | `tools/caveguard.py` `CODE_REGION`, `check()`; `docs/deep/code-region-plan.md` (not in this export) "The safety device" |
| The region executes cave code on hardware: probe163 ("9 count of noise then 'unmuted'") ran code at 0x2331e..0x23364; probes 165 and 171 ran to about 0x234e9 and 0x235a6 (path derived in cavesim and matched to the heard outcomes). The stubs themselves were never entered. | proven (163); well-supported (span to 0x235a6) | `docs/deep/offline-2026-10-10/verify.md` V8 |
| The region is code space, not data-addressable. Strings, the TaskData and anything the cave READS must stay in the const window. | proven | `docs/deep/offline-2026-10-10/verify.md` V8 last section; `docs/deep/offline-2026-10-10/material-slots.md` (not in this export) |
| The region is entered by `bsr` only. A window-to-region `bra` would need a 3-word branch, which the assembler refuses. The handler's first instruction must stay in the window. | proven (refusal); hypothesis (a region handler entry would also work) | `build/hook/assemble_probe179.py` "REFUSED" paths; `docs/deep/offline-2026-10-10/verify.md` V7 "Handler placement" |
| The old "291 writable words" for the region is a stale first-pass figure; 207 + 14 = 221 is right. | proven | `docs/deep/offline-2026-10-10/verify.md` V8 |

### 2b. What a zero word can be

| fact | confidence | source |
|---|---|---|
| Zero in the official image plus "inside a blind window" is NOT sufficient. Those are the two things the assembler once checked, and a zero-filled gap inside a live table satisfies both and is still read at run time. | proven | `docs/field-log.md:8153`; `tools/caveguard.py` module docstring |
| probe130 (234 words, 55 outside the window) crashed the speaker on boot ("battery one hundr..." then reboot). `fn_0aaa1` at 0x0aaa5 does `ld AL,#0x8280`; `fn_27bab` ships two words from there as a message payload (id 0x66). The run 0x3AA51..0x3AA67 has three load sites (0x0aa30, 0x0aaa5, 0x0aafa). | proven (disassembly); the link from that load to the crash is well-supported | `docs/field-log.md:8153`; `docs/cave-budget.md` warning box |
| The correlation is not clean: probe117 and probe121 wrote byte-identical values at 0x8280/0x8281 and only probe121 crashed. The 197-word rule rests on the empirical window (about 40 flashes), not on a proven mechanism. | proven (the counter-example) | `docs/field-log.md:8241` "Tree-wide audit after probe130" |
| 0x0000 is a valid XAP prefix word, so a zero run decodes as prefixes; use `fold_zero=False` when decoding inside const-pool zero runs. | well-supported | `docs/deep/AGENT-BRIEF.md` (not in this export) "XAP conventions" |
| The caveguard read-scan (immediate loads that point into a run) is advisory only: it has false positives, flagging runs probe129 used safely. The empirical window is the decisive test. | proven | `tools/caveguard.py` `audit()` comment; `docs/field-log.md:8153` |
| 262 is two unrelated numbers: the (wrong) widened scan advertised 262 writable words, and the stack headroom at 0xAE0 is 262 words (316 - 54). When quoting 262, say which. | proven | `docs/cave-budget.md` warning box |

### 2c. Layout, tools and the build chain

| fact | confidence | source |
|---|---|---|
| Entry point `CAVE = 0x3E21D` (data 0xBA3B). Word 0 is a 1-word `bra +3` over the TaskData; the TaskData is at CAVE+1, CAVE+2 (data 0xBA3C) as `{0x0003, lwrd(handler)}`; code starts at CAVE+3. | proven | `build/hook/assemble_probe179.py` (`TASK_AT`, `CODE_AT`, entry jump assert); `tools/caveasm.py` self-test `taskdata_words(0x3E21D) == [3, 0xE21D]` |
| A cave word at project address `a` lives at filesystem-area byte offset `0x6EA30 + 2a`, low byte first; the DFU file offset adds the offset of the `fsr_dfu1` marker. | proven | `tools/preflight.py` docstring |
| Build chain: `assemble_probeNNN.py` writes `probeNNN_words.json` and `probeNNN_cmd.txt` (an edit list for `tools/fsedit.py`), and with `--build` runs fsedit to produce `probeNNN_brown.dfu`. fsedit keeps the RSA block and the digest valid by compensation flips. | proven | `build/hook/assemble_probe179.py` tail; `docs/topics/dfu-and-signing.md` |
| The band layout is fixed by `blind()` plus zero-run scan; a branch between bands uses a 1-word `bra` connector placed in the band tail; a carried string is one item and is asserted contiguous (the longest band is 14 words, so "NowSpeakTTS/data_us" at 20 words cannot be carried and the two-level `tts` + `rphrases_us` walk is used). | proven | `build/hook/assemble_probe179.py` comments near `DIRNAME, FILENAME` and `_str_ptr` |
| `tools/caveasm.py` emits trap calls with the verified ABI (`call1/2/3`, `calln`, `send_later`, `imm_words`, `const_addr`, `taskdata_words`); its self-test pins sequences the ADK compiler emitted. | proven | `tools/caveasm.py` |
| The gates, in order: assembler decode-verify (every branch and instruction boundary re-decoded from the patched image), `cavesim` on the control and every path, `--build`, `caveguard` (window, region stubs, branch-form attestation), `preflight` (the built FILE contains the intended words and redirect bytes), `stackdepth` for a new site. | proven | `docs/FLASH-PROTOCOL.md` step 1, 1b, 2; `tools/preflight.py` |
| `preflight.py` verifies the file, never the device. It is not a readback. | proven | `docs/FLASH-PROTOCOL.md` step 1 note |

### 2d. Frame, stack and headroom

| fact | confidence | source |
|---|---|---|
| `enterl -k` reserves the top two frame slots (k-2 and k-1) for the 2-word saved return address. Usable slots are 0..k-3, so `enterl -8` gives slots 0..5. | proven | `docs/cave-frame.md`: 3,208 of 3,446 Bose functions leave exactly the top two slots alone and none violates it; 20 probes split on it (probes 68, 69, 72, 73, 78, 79, 80 stored to slot 6 or 7 and crashed; the one outlier, probe63, crashed for another reason) |
| A callee's incoming argument n sits at `@(k+n, Y)` where k is the callee's own frame size. A handler's third argument (Message) is therefore at `@(n,Y)` after its `enterl n`. | proven | `docs/cave-frame.md` Proof 3; `docs/message-task-abi.md` section 2 |
| X is the link register: it does not survive a `bsr`; reload any pointer held in X after every call. | proven | `docs/message-task-abi.md` section 3 |
| The VM stack is 316 words (`vm.app` header word 09). | proven | `tools/stackdepth.py` docstring; recomputed |
| At the 0x00E46 hook: deepest static `bsr` path is 54 words over 3 frames (fn_00846 `enterl -23`, fn_01749 `enterl -27`, fn_02684 `enterl -4`), headroom 262 words, an 8-word frame fits with 254 left. 0xAE0 is in the same function, so the figure is identical. | proven (output); the figure is a LOWER bound on depth | recomputed: `python tools/stackdepth.py 0xE46 --frame 8`; `docs/RETURN-CHECKLIST.md` (not in this export) row 0.17 |
| Rule: no cave frame larger than `enterl -8` at a site where headroom has not been measured for THAT site. A figure measured at one site says nothing about a deeper one. | proven (a loss) | `docs/FLASH-PROTOCOL.md` step 2; `docs/POST-MORTEM-2026-10-04.md` "Stack headroom not re-measured" |
| `stackdepth` follows direct `bsr` edges only. Switch-table dispatch, message handlers and recursion are not followed, so real depth can be larger. | proven | `tools/stackdepth.py` docstring |
| A cave gets RAM only by `malloc` at run time (pools up to 642 words, one such block) or by keeping state in its own const words, which are read-only. Build-time globals belong to Bose. | proven (pools from PSKEY); the "one big block" reading is well-supported | `docs/cave-budget.md` "What is not available"; `docs/cave-heap.md` |
| VM RAM survives a Bose power-off (it is a sleep state), so a corrupted stack survives ordinary power cycling. | well-supported | `docs/roadmap.md` (not in this export) rule 0; `docs/request-id-catalog.md` (not in this export) ("0x520 is not cleared on boot") |

### 2e. Instruction forms and branches

| fact | confidence | source |
|---|---|---|
| Branch operands are relative to the instruction's LAST word: `target = a + length - 1 + operand`. Multi-word operands are a signed prefix chain (each prefix word `aa00` adds sext(aa) and shifts left 8). | proven | `tools/caveasm.py` `fold`; `tools/stackdepth.py`; `docs/xap-opcodes.md` |
| Bose's own census of (branch opcode, word length), recomputed: bsr 1w 1,505 / 2w 11,359 / 3w 7,473; bra 1w 6,968 / 2w 1,230 / 3w none; beq 1w 7,543 / 2w 524; bne 1w 4,724 / 2w 187; bcc 1w 1,397 / 2w 106; bcs 1w 426 / 2w 33; bcz 1w 651 / 2w 16; bge 1w 44 / 2w 1; bgt 1w 63 / 2w 5; ble 1w 68 / 2w NONE. No conditional branch has a 3-word form. | proven | recomputed with `caveguard.bose_census`; `tools/caveguard.py` `attest()` |
| The assembler refuses a 3-word conditional branch, a 3-word `bra` connector and, by attestation, a 2-word `ble`. A 3-word `bsr` is allowed (it is how a hook reaches the cave). | proven | `build/hook/assemble_probe179.py` "REFUSED"; `tools/caveguard.py` |
| The assembler and the emulator share one opcode table (`tools/xapvm/xapvm.py`), so they can agree on a wrong encoding. Only Bose's own usage falsifies a form. That is the reason for the attestation gate. | proven | `docs/field-log.md` (probe131 section, "shared-table trap"); `tools/caveguard.py` attest comment |
| Carry polarity: after `cmp AL,#imm`, the emulator showed `bcc` branching on "greater or equal", not the "less than" the project had assumed. Caves use `beq` / `bne` where they can and do not rely on `bcc` / `bcs` polarity. | hypothesis (the table was shared with the emulator) | `docs/field-log.md` probe131 section ("A second error, caught before flashing") |
| `bcz` is "unsigned less-or-equal" in the stack code (a clamp), not "less than" as `docs/deep/AGENT-BRIEF.md` says. | well-supported | `docs/deep/offline-2026-10-10/stack-transform.md` (not in this export) section 1 item 6 |

### 2f. TaskData, messages and the trap interface

| fact | confidence | source |
|---|---|---|
| A TaskData is two words: `{hwrd(a_handler), lwrd(a_handler)}`, the handler's code-relative word address, high word first. For the cave handler this is `{0x0003, 0xE2xx}` at data 0xBA3C. | proven | `docs/message-task-abi.md` section 3; `tools/caveasm.py` |
| A handler is entered as `handler(Task in AL, MessageId in AH, Message at @(n,Y) after its own enterl n)`. Every trap clobbers AH, so a handler saves AH into a frame slot at once. | proven | `docs/message-task-abi.md` sections 2, 5a; `docs/deep/offline-2026-10-10/verify.md` V7 "Implementation note" |
| The one message loop is `fn_395f8`: `MessageWait` at 0x395fb, TaskData read at 0x39603/4, `fn_3960a` adds the stored word to the PC, handler called, `MessageFree` at 0x39616. Hook-independent. | proven (decode) | `docs/deep/offline-2026-10-10/verify.md` V7 point 1; `docs/message-task-abi.md` section 3 (the dispatch signature occurs once, at a = 0x39603) |
| `MessageSendLater(task, id, message, delay_ms)` to the cave's TaskData is delivered with the id in AH, many times, on the 0xAE0 hook (probes 99, 145-157, 165). On the 0x00E46 hook it has never been observed; probe179 is the first test. | proven (0xAE0); well-supported, not observed (0x00E46) | `docs/deep/offline-2026-10-10/verify.md` V7 |
| A 32-bit stack argument is two slots, HIGH word first. `D_IMMEDIATE` is `(Delay)-1`. `MessageSend`, `MessageCancelAll` and `MessageLoop` are library functions, not traps. | proven | `docs/message-task-abi.md` sections 1, 6, 7 |
| Trap ABI: arg1 in AL, arg2 in AH, args 3..n at `@(0,Y)`, `@(1,Y)`, ...; return in AL. | proven | `docs/trap-abi.md` "The rules"; `tools/caveasm.py` docstring |
| The speaker's vm.app is a BlueLab 7.3 image (VM version stamp 0x3200, `appquery --vminfo` says VM 19.0). Trap names must come from `tools/traps-bluelab73.json` / `tools/bose-stubs.json`, never from the ADK 4.4 (7.4) table: 173 of the 257 shared names differ. | proven | `docs/trap-numbering.md` (not in this export); memory csr8670-toolchain-status |
| There are 151 trap stubs. A stub is `enterl -3 ; ld X,#<trap> ; bra 0x291`: 4 words for traps below 0x80, 5 words (a prefix word before `ld X`) from 0x83 up. Example: TransformFromSink is trap 0x5d at a = 0x14a; FileFind is 0x83 at 0x1aa. | proven | recomputed: `python tools/disasm.py --fn 0x14a` and `--fn 0x1aa`; `docs/trap-stub-table.md` (not in this export) |
| `VmSoftwareWdKick` has no stub in Bose's image, so a cave cannot kick or disable the software watchdog. | proven | `docs/message-task-abi.md` section 7 |
| `docs/vm-trap-calling-convention.md` (not in this export) is retracted (it states the argument convention backwards). Use `docs/trap-abi.md`. | proven | that file's banner |

### 2g. Hook sites

| fact | confidence | source |
|---|---|---|
| A hook is a `bsr` whose three operand bytes are all blind. Only the three operand (high) bytes of the 3-word `bsr` are edited; the prefix words' zero low bytes and the opcode byte 0x9c stay. | proven | `build/hook/assemble_probe179.py` `REDIRECT_EDITS` and the encoding assert |
| 0x00E46 is `bsr fn_189fb` at the end of `fn_00846` (`enterl -23`); `ld AL,@(12,Y)` at 0x00e45 puts the event id in AL. Redirect bytes `01 7c b3` -> `04 d4 d5` at area bytes 0x706bd, 0x706bf, 0x706c1. | proven | `docs/field-log.md:12867` (probe172 built); `docs/deep/centre-long-press.md` (not in this export) "The hook" |
| 47 branches of `fn_00846` reach 0x00e45, so the hook sees most user events (the cave replays every event it does not own). | well-supported (a static count, not re-run) | `docs/deep/centre-long-press.md` "The hook" |
| A centre-button LONG press with a device connected reaches 0x00E46 as AL = 0x4004 (EventUsrInitateVoiceDial). The owner heard only the cave's own 0x17 and nothing else. Probes 173-178 repeated the trigger 12+ times. | proven (probe172) | `docs/field-log.md:12923`; `docs/deep/offline-2026-10-10/verify.md` V0 |
| The cave's job at 0x00E46: compare AL with 0x4004; match -> run the cave action and swallow the event; no match -> `ld AL,@(0,Y)` then `bsr fn_189fb` (the stock call replayed) and return. `fn_189fb` is `MessageSend(0xa5ce, 1, {1, event})` and takes AL only. | proven | `docs/field-log.md:12867`; `build/hook/assemble_probe179.py` TRIG |
| Swallowing at 0x00E46 withholds only `fn_189fb`. The `fn_01749` case-3 arm at 0x0194C still runs after the cave returns, so Bose's assistant bookkeeping for 0x4004 still happens. "Swallowed cleanly" is true only of the ADK voice-dial. | proven (call order); effect unknown | `docs/deep/offline-2026-10-10/verify.md` V0 R2 |
| 0x4004 is NOT emitted only in states 2/3/13: the centre short press (when `@0x568` bits 5-6 are non-zero), four `fn_01749` re-sends and the "kp" debug command also send it without a state test. Nothing found sends it at boot (not exhaustively traced). | proven (senders); well-supported (no boot sender) | `docs/deep/offline-2026-10-10/verify.md` V0 R1 |
| The 9-word table edit in `fn_07d5d` (0x7da2-0x7daa) that would make a centre long press emit 0x4004 with NOTHING connected was designed but never applied. A centre long press with nothing connected is untested. | proven (not applied); unknown (behaviour) | `docs/deep/centre-long-press.md`; `docs/field-log.md:12867` |
| 0x00AE0 is `bsr fn_0e06d` in the 0x4003 EventUsrEnterPairing arm. It fires only when `cmp AL,#0x4003` at 0x00ace passes AND `fn_09157 != 0` (a connected device slot) AND bit 7 of `@0x565` (A2DP streaming latch) is set. The press clears the latch, so it is one-shot per streaming session. Until probe172 it was the only hook with confirmed fires (`docs/hook-sites.md` lists probes 89, 90, 98, 99, 100 and 102; most of probes 128-171 also used it). | proven | `docs/deep/hook-gates.md` (not in this export) section 1-3; `docs/hook-sites.md` "Correction" |
| At 0xAE0 the device is already committed to pairing: `fn_0d500` at 0x00ac2 (two instructions earlier) tears down A2DP and the sbc_decoder DSP. About 7 s after the press `KalimbaSendMessage(0x1072)` returns FALSE (probe157). That is the ceiling on every port-3 result from probe104 to probe155. | proven | `docs/deep/hook-gates.md` addendum 2026-10-08; `docs/RESUME-HERE.md` (not in this export) banner |
| 0x107be (case 0xC5 -> 0x4004 in `fn_1061b`) and 0x10823 (the dispatcher's mode-2 exit) never fired from a real button. `fn_1061b`'s only caller is the "kp" text-command dispatcher, not the button path. | proven (probes 114, 126 silent) | `docs/deep/hook-gates.md` section 4; `docs/deep/centre-long-press.md` Summary |
| The redirect for every hook site `S` is `v = CAVE - (S + 2)`, encoded as a signed three-byte chain. For 0x00E46, v = 0x3D3D5 = bytes `04 d4 d5`. | proven | `build/hook/assemble_probe179.py` (asserts `REDIRECT_EDITS` equal the encoder's output) |

---

## 3. How it works

### 3.1 From a button press to cave code

1. The owner presses the centre button for 1.5 s or more with a Bluetooth source connected.
2. Bose's PIO handler (`fn_07f1a` -> `fn_080ad` -> `fn_07d5d`) matches button table entry 38 (centre, type 2 LONG, state mask 0x200c = states 2, 3, 13) and sends message 0x4004 to the main task 0x512 (`docs/deep/offline-2026-10-10/verify.md` V0).
3. `fn_00846`'s event ladder (`cmp AH,#0x4004` at 0x0087c) reaches 0x00e45, loads the event into AL and executes the hooked `bsr` at 0x00e46. The stock target was `fn_189fb`; now it is 0x3E21D.
4. At 0x3E21D the 1-word `bra` skips the TaskData and lands at the trigger: `enterl -8`, store AL in slot 0, compare with 0x4004, `bne PASS`. A match calls the cave action (`ARM`); anything else replays `fn_189fb` with AL restored and returns. (Structure shown in `build/hook/assemble_probe179.py`, label `TRIG`.)
5. The cave action calls traps through stubs: `StreamKalimbaSink`, `TransformFromSink`, `KalimbaSendMessage`, `FileFind`, `StreamFileSource`, `TransformAdpcmDecode`, `TransformStart`, `MessageSendLater`. The audio meaning of those calls is in `docs/topics/audio-path-and-dsp.md`.
6. A timer message returns to the cave through its TaskData: the main loop calls `handler(AL = task, AH = id)`.

### 3.2 Anatomy of an assembled cave

    0x3E21D   bra +3                      entry jump (1 word)
    0x3E21E   hwrd(handler)               TaskData word 0 (always 0x0003 here)
    0x3E21F   lwrd(handler)               TaskData word 1
    0x3E220.. trigger, handler, builder, strings (one item each)

The assemblers (`assemble_probeNNN.py` in build/hook/) keep a program as a list of `w` (raw words), `bsr`, `br` and `label` items. They size every branch to the shortest legal form, iterate until sizes converge, lay items into bands in order (const-window bands first, region bands after, code only), insert 1-word `bra` connectors where a band ends mid-code, then re-decode the patched image and assert that every branch target and every instruction start matches intent ("decode-verify: all branches OK, boundaries OK").

Hard-won constraints visible in that code:

- A carried string must fit one band (at most 14 words) and is asserted contiguous after layout.
- `FileFind` takes a length, so no NUL is needed; "tts" is borrowed from Bose's own const pool, and `sbc_decoder/sbc_decoder.kap` is found in the pool by a scan, so neither is carried.
- A prefixed `ld AH,#imm` for a pool pointer is asserted to fold back to the intended 16-bit value.
- The handler's first instruction and the TaskData stay in the window; later handler code may spill into the region.

### 3.3 The three layers of protection

1. Static, on the words: caveguard (window or region with stubs), attestation (every emitted branch form occurs in Bose code), preflight (the built DFU holds the words and redirect bytes, and every differing byte is cave, redirect or digest compensation).
2. Dynamic, in a model: `tools/cavesim.py` runs the cave in `tools/xapemu.py` with stubbed traps (and, since 2026-10-10, a clocked "world model" of port 3, the message queue and files; see docs/topics/probing-method.md section 3.7).
3. On hardware: readback after every flash (0 of 975,168 filesystem bytes differ, all cave words present), then one press.

No layer replaces another. The shared opcode table, the stub return values and the unobserved firmware behaviour are exactly what the first two layers cannot check.

### 3.4 Choosing a hook (how the project decided, and the rule that came out of it)

The rule: prove reachability from the BUTTON, not from local code. Three hooks in a row were chosen from the disassembly alone and two never fired. The record:

| site | what the site is | result |
|---|---|---|
| 0x00AE0 | `bsr fn_0e06d` in the pairing arm of `fn_00846` | works; gated by three conditions; tears down the DSP before the cave runs |
| 0x107be | send site in `fn_1061b`, reached via case 0xC5 | probe114: silent, centre long press, laptop connected |
| 0x10823 | common exit of `fn_1061b` mode 2 | probe126: silent on a volume press; `fn_1061b` is the "kp" debug path |
| 0x18a04 | inside `fn_189fb`, one frame deeper than 0x00e46 | probe127 (unit 1 was lost with it; cause not established) |
| 0x00E46 | `bsr fn_189fb`, end of `fn_00846` | works for a connected centre long press (probe172) |

(The probe-to-hook mapping comes from each assembler's `REDIRECT_EDITS`: area byte 0x6fff1 = 0xAE0, 0x8f9ad = 0x107be, 0x8fa77 = 0x10823, 0x9fe39 = 0x18a04, 0x706bd = 0x00e46. Probes 110-116 used 0x107be; 118-120, 125, 126 used 0x10823; 127 used 0x18a04; 172-181 use 0x00e46; the rest of the 77-171 series used 0xAE0.)

### 3.5 Timers, ticks and persistence

A cave keeps no state of its own between calls: its frame dies at `leavel` and its const words are read-only. What persists is (a) the pending message in Bose's message list (`MessageSendLater` nodes live in one list sorted by due time; `MessageCancelFirst(task, id)` removes the first node with that task and id: `docs/deep/offline-2026-10-10/stack-transform.md` verdict 6, a static reading never pressed) and (b) the transform and port state in the firmware. The message id is the only counter the loop designs carry. Each tick re-reads the world (`StreamKalimbaSink(3)`, `TransformFromSink`) rather than trusting remembered state. Rules for what a tick may do to port 3 are in memory csr8670-port3-chunk-rules and `docs/topics/audio-path-and-dsp.md`.

### 3.6 The trap stub table

`tools/gen-stub-table.py` finds every `enterl -3 ; ld X,#n ; bra 0x291` and writes `docs/trap-stub-table.md` and `tools/bose-stubs.json` (name -> stub `a`). `tools/caveasm.py` loads the JSON as `ca.STUB[...]`, so a cave writes `ca.STUB['FileFind']` and `bsr`s to that address. A few traps live elsewhere (`MessageWait` 0x287, `MessageFree` 0x28a, `VmPutChar` 0x296, `TestPerform_` 0x28d, which are not at the regular stride) and the table lists them as such. Names come from BlueLab 7.3.1 (`tools/extract-traps.py` -> `tools/traps-bluelab73.json`); the stub address is a fact of the image, the name is a mapping.

---

## 4. Traps and retractions

| what was believed | what is true | where it was corrected |
|---|---|---|
| "The cave can be 262 words; scan the whole const pool for zero runs of 16 or more." | 197 words in 0x3E200..0x3E400 only. probe130 crashed on boot. | `docs/cave-budget.md` warning box; `docs/field-log.md:8153` |
| "Zero in the official image and blind means unread." | Zero gaps inside live tables are read. | same |
| Only probe130 was affected by the widened scan. | A tree-wide audit found 22 of 116 assemblers (from about probe107) sweeping the whole pool; the log counts six of them flashed. Which of them caused unit 1's loss is not established. | `docs/field-log.md:8241` |
| "`enterl -8` gives eight free frame slots." | Two are the saved return address. Usable 0..5. Seven crashes and six presses were misread as an opcode bug and an unusable `malloc`. | `docs/cave-frame.md` |
| "`docs/cave-frame.md`: use `enterl -16`." | Superseded for flashing by the protocol rule: nothing above `enterl -8` at an unmeasured site. | `docs/FLASH-PROTOCOL.md` step 2 |
| "probe91 died of a deep frame (stack)." | That diagnosis was retracted; the app stayed non-responsive and recovery is uncharacterised. | `docs/roadmap.md` rule 0 |
| "A 2-word `ble` is what crashed probe131 and probe132." | Withdrawn: probe132, with an attested `bne`, still crashed. The attestation gate stays as a precaution; the absence of a form in Bose code is evidence, not proof, that hardware rejects it. | `docs/field-log.md` probe132 section |
| "Hooking 0x10823 (or 0x107be) fires on any button in any state." | Refuted on hardware; both sit in the "kp" debug path or behind a code the button manager never emits. `docs/hook-sites.md` still recommends 0x10823 in its body. | `docs/deep/hook-gates.md` section 4; `docs/INDEX.md` (not in this export) section 1b |
| "A Bluetooth long press always reaches the 0xAE0 cave." | Only a press that means enter-pairing, with a connected device slot and the A2DP latch set. | `docs/hook-sites.md` "Why the old hook kept not running" |
| "The 0xAE0 cave could be kept alive by skipping the stock back-call." | The teardown is `fn_0d500` at 0x00ac2, before the hook; no cave edit prevents it. | `docs/deep/hook-gates.md` addendum |
| "Pool arithmetic explains the ~7 s death of the port-3 loop." | The DSP is gone after the pairing teardown. `docs/cave-heap.md` is sound but was applied to the wrong problem. | `docs/cave-heap.md` banner |
| "0x4004 is emitted only in states 2/3/13; swallowing it is clean." | Other senders exist; the `fn_01749` arm still runs. | `docs/deep/offline-2026-10-10/verify.md` V0 |
| "The region has 291 writable words." | 207 usable + 14 stub = 221. | `docs/deep/offline-2026-10-10/verify.md` V8 |
| "The region was never exercised on hardware." | probes 163, 165, 171 ran code from it. | same |
| Traps named from ADK 4.4 / BlueLab 7.4. | Probes 46/47 called KalimbaPowerOff and 52-56 called StreamScoSink by mistake; use the 7.3 table. | `docs/trap-numbering.md` |
| `docs/vm-trap-calling-convention.md` (arg1 in AH). | Retracted; the right order is AL, AH, then stack slots. | that file's banner; `docs/trap-abi.md` |
| "Stack headroom is 262 words everywhere." | It is 262 at 0xAE0 and 0x00E46 (same function); probe127 sat deeper and the figure was reused. | `docs/POST-MORTEM-2026-10-04.md` |
| `fn_12e1a` is a safe sink mapper. | On a connected sink `SinkMap`/`SinkClaim` return 0 and it memsets `size` words from data address 0 (probe123). Never call a trap on an object of unknown state. | `docs/FLASH-PROTOCOL.md` "Safety rules for cave code" |

---

## 5. Open questions

| question | status | what would answer it |
|---|---|---|
| Is a `MessageSendLater` tick delivered to the cave handler when the hook is 0x00E46, with small ids 3, 2, 1? | well-supported, never observed | probe179 (built, NOT flashed); `docs/deep/offline-2026-10-10/verify.md` V7 |
| Is the real stack deeper than 54 words at 0x00E46 through the message loop? | unknown (static lower bound only) | no tool follows switch dispatch; a stack-fill measurement would need a device |
| Why exactly are the 197 window words safe? | unknown (empirical window, about 40 flashes) | a data-flow trace of every reader of data 0xBA2F..0xBC00; never widen in the meantime |
| Does a handler entered through a TaskData work when its first instruction is in the region? | hypothesis | an image that does so; do not try without a reason |
| Does an AVRCP browse from a phone ever call a region function? | well-supported no; the entry stubs make it return 0 | not exercised on hardware |
| What does a centre long press do with NOTHING connected? | unknown; the 9-word edit exists as a design | `docs/deep/centre-long-press.md`; a new image |
| Are `@0x568` bits 5-6 / `@0x564` bit 15 live on this unit? If so a centre short press may reach the cave | hypothesis, low-moderate | the "settling press" in `docs/RETURN-CHECKLIST.md` section 1.4 |
| What killed unit 1: the stack frame, the live-const corruption, or a truncated write? | not established | none possible; the unit is lost |
| Does the hardware accept a 2-word `ble` or a 3-word conditional branch? | unknown; the project avoids them | a dedicated probe; not worth a flash |
| Do the cavesim stubs match the firmware (busy read, free edge, unload latency, `MessageCancelFirst`)? | unknown | the zero-flash presses and probe179 in `docs/RETURN-CHECKLIST.md` |

---

## 6. Detailed knowledge (routing)

If you want the cave limits and the history of the 197-word figure: `docs/cave-budget.md`, then `docs/field-log.md:8153` (probe130) and `docs/field-log.md:8241` (the tree-wide audit), then `tools/caveguard.py` (the code that enforces it).

If you want the frame and ABI rules: `docs/cave-frame.md`, `docs/trap-abi.md`, `docs/message-task-abi.md`, `docs/xap-opcodes.md`, `tools/caveasm.py`. For XAP decoding gotchas: `docs/deep/AGENT-BRIEF.md` "XAP conventions" (its `bcz` note is corrected in `docs/deep/offline-2026-10-10/stack-transform.md` section 1).

If you want the trap table: `docs/trap-stub-table.md`, `tools/bose-stubs.json`, `tools/traps-bluelab73.json`, `docs/trap-numbering.md`, `tools/gen-stub-table.py`, `tools/extract-traps.py`.

If you want the hooks: `docs/deep/centre-long-press.md` (the current hook and the unapplied state-1 edit), `docs/deep/hook-gates.md` (why 0xAE0 is gated and refuted sites), `docs/hook-sites.md` (the disassembly method and the whole-image site list; its recommendation of 0x10823 is withdrawn), `docs/centre-button-hook.md` (not in this export), `docs/sink-events.md` (names of the 0x4xxx events), `docs/deep/offline-2026-10-10/verify.md` V0 (the 0x4004 senders).

If you want more code space: `docs/deep/space-survey.md` (not in this export) (264 dead functions, about 2,870 usable code words in the second pass), `docs/deep/code-region-plan.md` (the region and its stubs), `docs/deep/stock-helpers.md` (not in this export) (callable stock helpers that save cave words).

If you want stack headroom: run `python tools/stackdepth.py <site> --frame N`; `docs/FLASH-PROTOCOL.md` step 2; `docs/roadmap.md` rule 0; `docs/POST-MORTEM-2026-10-04.md`.

If you want the simulator: `tools/cavesim.py -h`, `docs/deep/offline-2026-10-10/cavesim-changes.md` (not in this export), `docs/topics/probing-method.md` section 3.7.

If you want to see a complete cave: `build/hook/assemble_probe179.py` (the newest template; its docstring is the press plan), `build/hook/assemble_probe172.py` (the 21-word trigger-only cave), `build/hook/assemble_probe161s.py` (the region fill image).

If you want the Bose firmware around the hooks: `docs/bose-firmware-anatomy.md` (not in this export), `docs/firmware-map.md` (not in this export) (84 functions named), `build/analysis/full-disasm.txt` (not in this export) (generated by `python tools/disasm.py`), `docs/topics/hardware-and-firmware.md`.

If you want the state of the line today: `build/hook/FLASHED`, then `docs/RESUME-HERE.md` lines 1-40, then `docs/RETURN-CHECKLIST.md`.

See also (strategy review 2026-10-12, offline, a recommendation; read the skeptic section of each note first): `docs/deep/strategy-2026-10-12/04-stock-behavior.md` (not in this export) (every change the hook and the cave make against stock; the stock-function sheet is unmeasured) and `docs/FACTS.md` F148 and F155.

See also (firmware study 2026-10-12, offline, static or model results; read the skeptic section of each note first; index `docs/deep/firmware-study-2026-10-12/README.md` (not in this export), functions `docs/FUNCTION-CATALOG.md` (not in this export)): `T12-trap-tail-stub.md` (calling a trap that has no vm.app stub through a synthesised stub; never run on hardware: F166, F167), `T03-cavesim-and-seam-model.md` (cavesim failure worlds, the sinkState guard hole in the images 177-181: F219-F221), `T04-stock-collisions-and-centre-button.md` (what the 0x4004 swallow does and does not remove: F181-F183) and `T11-product-build-and-press-pages.md` (PB specification, stock sheet and press pages; 181p, 184a, 184 and 187 are built offline and NOT flashed: `docs/PROBE-CATALOG.md` section 11).

## See also (round 3, 2026-10-12)

Added at the end so that no cited line moved. Round 3 is offline and static or model work; nothing was run on the speaker. Index and corrections register: `docs/deep/round3-2026-10-12/README.md` (not in this export); the facts are in `docs/FACTS.md` section 10.

- `docs/deep/round3-2026-10-12/R05-stock-follow-ups.md` (not in this export): sinkState is a plain RAM word a cave reads inline (`0x0600 0x9E15`); the 6-word consume lever for 0x4004; the merged-entry guard cost (F259-F266).
- `docs/deep/round3-2026-10-12/B01-product-build-probes.md` (not in this export): probes 188 (PBd) and 189 (PB) built offline, NOT flashed; layout-engine limits (F286-F288).
- `docs/deep/round3-2026-10-12/V01-verify-tools-and-seam-model.md` (not in this export): a cave bsr/bra into the trap tail passed every gate before T14 and is now refused (F280); the stack headroom of a stub image is a manual gate.
- `docs/deep/round3-2026-10-12/R02-raw-source-0xd3-and-trap-catalogue.md` (not in this export): the 8-word 0xD3 stub is the only way a cave reaches the raw partition source; never run on hardware (F233-F243). CLAUDE.md rule 3 versus the code-region words: owner decision PD-27.

## See also (2026-10-28)

The cave can carry data as well as code: a DSP program is stored as a table in whole window bands that the layout leaves out of its pool (F321). AY batches C and D (17 more dead functions) are approved and proven inert hands-free (probe381). Layout rules learned: 3-word `bsr` needs a far target, conditional branches cannot cross window/dead-function (F322, F329). Build flag `GEN` and the lean product: `docs/CURRENT-STATE.md`.
