Purpose: the one-page hub for HOW this project changes the speaker and learns from it: the flash protocol and every gate, the probe lifecycle with exact commands, the offline gates, press plans and spoken ids, how results are logged, the cavesim world model, and a recipe for building probe N+1 from probe N.

> **Note on references (public export):** this file cites files from the original private research repository that are not included here; each such path is marked "(not in this export)" at its first mention, and all of them are listed in `docs/NOT-IN-EXPORT.md`. The claims they support are summarised in the text; the cited originals are not needed to rebuild or flash anything.

Status / last verified: 2026-10-10 (offline gate outputs quoted below were re-run on this date; nothing here touched the device; the owner is away and the speaker is NOT connected, so no flash and no USB command may be run until the owner says it is back).

Read next: docs/FLASH-PROTOCOL.md (the authoritative gate text), then docs/topics/cave-and-hooks.md for the code-side limits.

> **This is an archival research document from the original (larger, private) project repository.** Some of its internal links point at files not included in this public export; where one doesn't resolve, that's why. The repository's own current, self-contained write-ups are listed in README.md's "Repository layout" section.

Confidence marks: **proven** (command output, address or owner press quoted in the source), **well-supported**, **hypothesis**, **unknown**. Negatives are results. Where two sources disagree the newer one wins; section 4 lists the known cases.

Terms. A "probe" is one built DFU image carrying one cave (a small code patch) plus one hook; it is numbered (probe178 is on the speaker). "Press" means the owner presses a button and reports what he hears. "FLASHED" is `build/hook/FLASHED`, the single source of truth for what is on the speaker. "Unit 2" is the only speaker; unit 1 was lost on 2026-10-04.

---

## 1. Summary

The project learns by experiment: build one image, prove it offline, flash it, read the image back off the device, ask the owner for one press under conditions written down first, record his words, and only then build the next image. Everything in this hub exists because that loop was once run without its gates.

On 2026-10-04 eleven flashes and nine presses ran in 92 minutes with zero readbacks, output sent to /dev/null, background jobs and fixed sleeps. Unit 1 then stopped enumerating on USB in any mode and was lost. About 95 earlier cycles had followed the gates and lost nothing. The gates are now written down (`docs/FLASH-PROTOCOL.md`), automated where possible (`tools/flash_probe.py`, `tools/preflight.py`, `tools/caveguard.py`), and restated as a checklist for the first day back (`docs/RETURN-CHECKLIST.md` (not in this export)).

Offline gates catch a bad build before a press is spent: assembler decode-verify, the cavesim control (probe90) and every path of the new probe, `--build`, preflight, caveguard, and stack headroom for a new hook site. A simulator pass proves the cave is well-formed, not that the firmware agrees: the readback proves the image, the press proves the behaviour.

The flash itself is one foreground sequence with an expected line at every step (`enter-dfu`, poll for 4022, `download` with its "Waiting ... for firmware to manifest" line, `leave-dfu -f` with no errXXX, poll for 40fe, `info -f`). Then `build/hook/FLASHED` is written at once, and the readback must show 0 of 975,168 filesystem bytes differ and every cave word present. No readback means no next flash.

A press plan states, before the press, what is connected, what is playing, which button and gesture, and a table of outcomes in which every path (success included) has a distinct spoken prompt id that cannot be confused with a stock prompt. The owner's words go into `docs/field-log.md` (not in this export) verbatim before anything else is built.

---

## 2. KEY FACTS

Paths are relative to the repo root. "Recomputed" or "ran 2026-10-10" means the output was reproduced offline on that date.

### 2a. The flash protocol and its gates

| fact | confidence | source |
|---|---|---|
| The gates, in order: (1) offline build and verify; (1b) cave inside the proven window; (2) stack headroom if the hook is new; (3) flash in the foreground, every line read; update FLASHED; (4) read the image back; (5) one press, conditions and outcome ids written first; (6) record the result, then stop. If a step cannot be completed the next flash does not happen. | proven | `docs/FLASH-PROTOCOL.md` |
| Unit 1 was lost on 2026-10-04 after eleven flashes and nine presses in 92 minutes with zero readbacks; the unit then did not enumerate in any mode. `PSKEY_USB_VM_CONTROL = 1`, so a dead VM application means no USB and no host-side recovery. | proven (the sequence); the single cause is NOT established (the probe127 cave also put 21 words outside the window) | `docs/POST-MORTEM-2026-10-04.md`; `docs/field-log.md:8241` |
| FORBIDDEN in a flash: `run_in_background`, redirecting any step to /dev/null, a fixed `sleep` instead of polling, a `timeout` under 600 s on `download`, judging by an exit code, queueing probes. | proven | `docs/FLASH-PROTOCOL.md` step 3 "Forbidden" |
| Poll `list` for PID 4022 (DFU) and later 40fe (normal) by ELAPSED time (tens of seconds), never by iteration count. A 12-iteration loop finished in about 1 s on 2026-10-05 and reported 40fe every time. A second `enter-dfu` is not a safe retry. | proven | `docs/FLASH-PROTOCOL.md` step 3 warning |
| Expected lines: `enter-dfu` -> "Note that device may take a few seconds to change mode"; `download --force` -> "Waiting NN.NNNs, as requested by device, for firmware to manifest" (45.867 s on 2026-10-02 and again on probe172); `leave-dfu -f` -> no `errXXX` (FAIL on errFIRMWARE); `info -f` -> "Current firmware: Main 3.0.3.6546". `-f` is required on `download` and `leave-dfu` for this device. | proven | `docs/FLASH-PROTOCOL.md` step 3; `docs/field-log.md:12907` (probe172 flash) |
| `build/hook/FLASHED` is updated IMMEDIATELY after the flash (`probe=`, `image=`, `sha256=`, `flashed=`, `cycle=`, `verified=PENDING`) and `verified=` is filled at the readback. `tools/docaudit.py` checks the docs against it; a stale FLASHED makes the audit enforce falsehoods. | proven | `docs/FLASH-PROTOCOL.md` step 3; `tools/flash_probe.py` `flashed_update()` |
| Readback: `python tools/csr/dfu_upload.py build/hook/probeNNN_readback.dfu`, foreground, `timeout 900`. It enters DFU itself and always tries to leave. Require 0 of 975,168 filesystem bytes differ AND all N cave words present AND the redirect bytes. A plain `cmp` is meaningless: the readback differs in length from the flashed file and `fsr_dfu1` sits at a different offset (0xbfc00 vs 0xbff4c in the validated pair), so align on the `fsr_dfu1` marker in both files. | proven | `docs/FLASH-PROTOCOL.md` step 4 (validated on the probe77 pair); `tools/flash_probe.py` |
| NO READBACK = NO NEXT FLASH. If readback fails or is unavailable, fix the readback path before flashing again. | proven (the loss) | `docs/FLASH-PROTOCOL.md` step 4; `docs/POST-MORTEM-2026-10-04.md` "Hard gates" |
| `tools/flash_probe.py probeNNN` runs steps 3 and 4 as ONE foreground process: preconditions (image, words, assembler exist; preflight passes; device lists as 05a7:40fe, refuses from 4022), `enter-dfu`, 60 s elapsed-time poll for 4022, `download --force` (timeout 900), `leave-dfu -f`, 60 s poll for 40fe, `info -f`, FLASHED written, readback (timeout 900), marker-aligned compare, `verified=` written. It stops at the first unexpected line and logs to `probeNNN_flash.log` in build/hook/. `--dry-run` stops before `enter-dfu` but still needs the device attached. | proven | `tools/flash_probe.py` docstring and body |
| The runner exists because assistant turns can be interrupted between tool calls (owner, 2026-10-08), leaving a half-done flash with nobody reading. Run it in the foreground, alone, never behind a heredoc or any other command. | proven | `tools/flash_probe.py` docstring; `docs/FLASH-PROTOCOL.md` |
| probe178 was flash cycle 57 on unit 2 (`cycle=57 on unit 2`), flashed by `tools/flash_probe.py` with readback verified 124/124 words and 0 of 975,168 bytes differing. | proven | `build/hook/FLASHED` |
| Recovery order (corrected 2026-10-08): (1) `bose-dfu list` (40fe = the app still runs, USB recovery is possible); (2) `bose-dfu info -f` and `python tools/csr/tap_sweep.py vr` (either answering = command layer alive); (3) `enter-dfu` will NOT work if the message loop is stuck, one attempt only; (4) POWER + VOICE-ASSISTANT ~10 s did NOT work from a wedge (it worked once, from errFIRMWARE); (5) what works: UNPLUG USB, hold POWER alone ~20 s, plug USB, press POWER; (6) a cold boot is clean, so flash stock at once and press nothing; (7) last resort: let the battery go flat; no USB at all = SPI only (no dongle owned). | proven | `docs/FLASH-PROTOCOL.md` "Recovery"; `docs/field-log.md:11717` and `:11804` |
| `bose-dfu info -f` (not `list`) is the liveness test: `list` needs only USB descriptors and reports a wedged device as healthy. | proven | `docs/roadmap.md` (not in this export); `docs/FLASH-PROTOCOL.md` |
| Cave-code safety rules: never call a trap on an object of unknown state (prefer read-only interrogation); never run a teardown against an object that may not exist; prove hook reachability from the BUTTON; gate on `KalimbaSendMessage(0x1072)` returning TRUE (FALSE at power-on because no DSP is loaded, so a cold boot bails silently). | proven | `docs/FLASH-PROTOCOL.md` "Safety rules for cave code" |
| The owner holds STANDING permission to flash; the gates are what make that safe. No other permission is implied. | proven (owner statement) | memory csr8670-flash-protocol |
| OFFLINE PERIOD from 2026-10-10: no flash and no device command (`tools/flash_probe.py`, `tools/bose-dfu/*`, `tools/csr/dfu_upload.py`, `tools/csr/tap_sweep.py`) until the owner says the speaker is back. Probes may be assembled, simulated and preflighted. | proven (standing instruction) | memory csr8670-offline-period-2026-10-10; `docs/RESUME-HERE.md` (not in this export) banner |

### 2b. The offline gates (ran 2026-10-10 unless noted)

| fact | confidence | source |
|---|---|---|
| Control: `python tools/cavesim.py probe90` ends `ended: leavel at 0x3E31E   AL = 0x000e`. Run it EVERY time; if it drifts, nothing else means anything. | proven (ran) | `docs/RETURN-CHECKLIST.md` row 0.4; `docs/FLASH-PROTOCOL.md` step 1 |
| `python tools/caveguard.py probe178` printed `SAFE -- every word inside the proven window or the listed, stubbed code region` and `all emitted forms are attested in Bose firmware`; the "words within 64 of a loaded pointer" lines are advisory. | proven (ran) | `tools/caveguard.py` |
| `python tools/stackdepth.py 0xE46 --frame 8` -> `headroom at that point: 316 - 54 = **262 words**`, `a cave frame of 8 words: FITS (254 words would remain)`. | proven (ran) | `tools/stackdepth.py`; `docs/RETURN-CHECKLIST.md` row 0.17 |
| `python tools/cavesim_regress.py` -> `169 cases: 169 identical, 0 differ, 0 missing golden`. The goldens (`build/analysis/cavesim-golden/`, 169 files) are git-ignored, so a fresh checkout reports 169 missing. | proven (ran) | `tools/cavesim_regress.py`; `docs/deep/offline-2026-10-10/README.md` (not in this export) F9 |
| `python tools/cavesim_selftest.py` -> `23 cases, 0 failed` (four MOCK caves in the shape of probes 179, 180, 182 and 185b). They are not probes. | proven (ran) | `tools/cavesim_selftest.py`; `docs/deep/offline-2026-10-10/cavesim-changes.md` (not in this export) section 4 |
| `python tools/adpcm.py --selftest` passes, including a byte-exact match of the vendor `.prm` (3,400 bytes). | proven (ran) | `tools/adpcm.py` |
| `python tools/docaudit.py` -> `46 fact checks, 0 broken references, 0 failing overall` and `device: probe178 -- PROBE`. It reads FLASHED and the docs it knows; it does NOT read `docs/deep/offline-2026-10-10/`. | proven (ran) | `tools/docaudit.py` |
| `tools/preflight.py probeNNN` checks the built FILE: same length as the official image, `fsr_dfu1` at the same offset, every cave word at `0x6EA30 + 2a`, every redirect byte, every differing byte explained as cave, redirect or digest compensation; then runs caveguard (window, region stubs, branch-form attestation). It never touches the device and is not a readback. | proven | `tools/preflight.py` docstring |
| `python tools/preflight.py -h` is NOT a help flag; `-h` is read as a probe name and prints `-h        SKIP  missing -h_brown.dfu`, and the run STILL ends with `all checked probes pass pre-flight`. A SKIP (missing image or words file) is therefore not a failure to preflight itself: read the per-probe line, never only the last line. | proven (ran) | `tools/preflight.py` `check()` returns None on a missing file; `docs/RETURN-CHECKLIST.md` notes |
| Per-probe scenario gates exist for the loop probes: `python build/hook/gate_probe180.py` (25 scenarios) and `gate_probe181.py` (31 scenarios), each driving cavesim's world model with `--expect`. | well-supported (counts from the checklist, not re-run here) | `docs/RETURN-CHECKLIST.md` row 0.20; `build/hook/gate_probe180.py` |

### 2c. Press plans, spoken ids, logging

| fact | confidence | source |
|---|---|---|
| The cave reports an outcome by SPEAKING a prompt id (it leaves the id in AL and calls the prompt engine, fn_0df7f / the `SPEAK` label). The owner reports what he heard, so the heard prompt is the result channel. | proven | `build/hook/assemble_probe179.py`; `docs/request-id-catalog.md` (not in this export) |
| Two id spaces: prompt ids 0x00-0x3F index the speaker's sound corpus (all 64 owner-confirmed); the 0x4xxx values are ADK sink events (`docs/sink-events.md`). Never mix them. | proven | `docs/request-id-catalog.md` banner |
| Every path gets its own id, success included. Silence is allowed only where the build intends it (a busy press does nothing) and is then a stated row. The id table belongs to ONE probe; do not carry it to another (the same prompt means different things in different probes). | proven | `docs/FLASH-PROTOCOL.md` step 5; `docs/deep/offline-2026-10-10/README.md` F8; `docs/RETURN-CHECKLIST.md` section 2.2 |
| No id may collide with a stock prompt used in that state: 0x09 "mobile device not found", 0x00 "ready to connect", 0x3E "bluetooth off" (also the stock Bluetooth-off prompt), and 0x21 0x22 0x24 0x25 0x1B (call prompts, ambiguous if a call application is open on the laptop). | proven | `docs/POST-MORTEM-2026-10-04.md` (probe123 reused 0x09); `docs/deep/offline-2026-10-10/README.md` F8 |
| The current id vocabulary (probes 178 and 179): 0x3E no DSP loaded; 0x22 `FileFind(tts)` refused; 0x1B `FileFind(rphrases_us)` refused; 0x10 `StreamKalimbaSink(3)` returned 0; 0x24 `StreamFileSource` refused; 0x25 `TransformAdpcmDecode` or `TransformStart` refused; probe179 adds 0x26 "ended" (success) and 0x21 "call ended" (gate FALSE at a seam). | proven (assemblers); meanings of the stock words from the catalog | `docs/RETURN-CHECKLIST.md` sections 1.1 and 2.2 |
| The press plan lives in the assembler docstring and is copied into the field-log "built" entry. It states: speaker volume, what is connected, what is playing (music PLAYING or paused; the DSP must be up), the button and gesture (centre long press, 1.5 s or more), the wait between presses (5 s after the sound stops), and the outcome table ("heard X means Y, next Z"). | proven | `build/hook/assemble_probe179.py` docstring; `docs/field-log.md:13417` |
| Kill switches are printed on every press page, in order: the loop ends by itself (179 only); centre long press = STOP (180 on, hypothesis); Bluetooth long press; pause the music; POWER off with USB unplugged. USB is UNPLUGGED after the readback so that POWER can force the speaker off. | proven (list); status per switch in the source | `docs/RETURN-CHECKLIST.md` section 3 |
| `docs/field-log.md` is APPEND-ONLY evidence, read by `tools/docaudit.py`: owner words quoted verbatim first, interpretation separate, corrections in LATER entries, never edits. Its header defines the classes field observation / binary artifact / log claim. | proven | `docs/field-log.md` lines 1-24 |
| Per-probe entries use these headings: `# probeNNN -- built DATE: <one-line change>` (written BEFORE the flash, with the press plan and the offline gate outputs); `# probeNNN -- flash #K on unit 2, DATE (tools/flash_probe.py)` (key lines quoted and the "AWAITING THE PRESS" conditions); `# probeNNN -- RESULT (DATE, owner, <conditions>): "<words>"` (verbatim, then numbered readings). | proven | `docs/field-log.md:12867`, `:12907`, `:12923`, `:13417` |
| Write the owner's words into the field log BEFORE building anything else. The press results of probes 114, 121, 122, 125 and 126 were never logged and had to be recovered from a transcript. | proven | `docs/FLASH-PROTOCOL.md` step 6; `docs/POST-MORTEM-2026-10-04.md` |
| Run `python tools/docaudit.py` after any doc or FLASHED change; `docs/RESUME-HERE.md`'s banner changes only by ADDING lines (FLASHED stays authoritative). | proven | `docs/RETURN-CHECKLIST.md` section 2.5 |

### 2d. The cavesim world model

| fact | confidence | source |
|---|---|---|
| `tools/cavesim.py` loads a probe's `_words.json` into the speaker's own vm.app, stubs the traps, and runs the cave in `tools/xapemu.py`. It reports the trap sequence, the exit value in AL, the spoken ids ("prompt ids spoken, in order") and any buffer the cave filled. It answers "is this cave well-formed", not "will the speaker make a noise". | proven | `tools/cavesim.py` docstring |
| Since 2026-10-10 it has an opt-in "world": a millisecond clock, a message queue (`MessageSendLater`, `MessageCancelFirst`, `MessageFlushTask`), port 3 and the ADPCM chunk on it, the DSP end-of-tone report, the paused-music unload, the rate latch and level word, a small file system with partition-2 rules, `SourceSize`/`SourceMap`/`SourceDrop`/`SourceClose`, partition census keys, and a rule checker R1-R6. Every legacy invocation prints byte-identical output (the 169-case battery). | proven (the battery) | `docs/deep/offline-2026-10-10/cavesim-changes.md` |
| Rules R1-R6 (checked at every trap): R1 `0x1072` while port 3 is busy; R2 TransformStop/Disconnect/StreamDisconnect on a running transform; R3 SPEAK while port 3 is busy; R4 a second transform while one holds the port; R5 `MessageSendLater` below 50 ms; R6 two cave messages pending. R1 is a conservative design rule, not a proven hazard on its own; R2 comes from two crashes (probes 174, 175) whose call was never bisected; R6 is a convention. | proven (the rules exist); basis per rule in the source | `docs/deep/offline-2026-10-10/cavesim-changes.md` section 3 |
| The model's parameters are written from the record, not measured by the simulator: chunk length (2 samples per byte, rate from the latch), rate latch (first chunk after a DSP load plays at 8 kHz, later chunks at the sent rate), level word (`b & 2` selects cbops shift 4 vs 7), free edge (port reads free at source EOF, before the audible end), paused unload (default 100 ms, a guess), timer delivery (not yet observed on the 0x00E46 hook), `MessageCancelFirst` (header semantics, hypothesis). | status per row in the source | `docs/deep/offline-2026-10-10/cavesim-changes.md` section 3 table |
| The model reproduced the owner's probe177/178 durations (2,622 ms then 10,486 ms), the probe177 paused-music `0x3E`, probe173's R1/R2/R4 pattern and probe175's R2. It does NOT reproduce a firmware Panic: it flags the call, it does not know what the firmware does with it. Ran 2026-10-10: `python tools/cavesim.py probe178 --entry 0x3E21D --loop 3 --press-gap 5000 --brief` printed chunks of 2622 ms and 10486 ms, `port-3 rules: OK`. | proven (reproduction); limits stated | `docs/deep/offline-2026-10-10/cavesim-changes.md` section 5; ran |
| `asr` is modelled as a logical shift, stub returns are plausible values, and the assembler and emulator share one opcode table (`tools/xapvm/xapvm.py`), so a wrong encoding can pass both. Time inside a handler is zero. | proven | `tools/cavesim.py` docstring; `docs/deep/offline-2026-10-10/cavesim-changes.md` section 8; `tools/caveguard.py` |
| A clean simulated run does not rule out a phase-dependent hazard: with the port reading free 400 ms early the run is clean only because no 1 s poll lands in that window; with 900 ms it lands and R1 + R4 fire. | proven (the model) | `docs/deep/offline-2026-10-10/cavesim-changes.md` section 4 |

### 2e. Reading the record

| fact | confidence | source |
|---|---|---|
| Trust order: `build/hook/FLASHED` over any prose about the speaker; `docs/RETURN-CHECKLIST.md` section 6 over `DESIGN.md` until DESIGN is edited; `verify.md` and `stack-transform.md` over the first-pass research notes and the offline README; inside one file a later dated correction over earlier text. | proven (the project's rule) | `docs/INDEX.md` (not in this export) section 1a |
| Verification (V0-V11) downgraded or corrected most of the first-pass "PROVEN" labels in DESIGN. Nothing seen only in a stack-image reading is "proven on hardware" until a press. | proven | `docs/deep/offline-2026-10-10/verify.md` (not in this export); `docs/RETURN-CHECKLIST.md` header |
| A static reading of the stack image (`build/analysis/stack-disasm.txt` (not in this export)) found why probes 174/175 crashed: `TransformFromSink` returns the downstream node, which carries flag 0x40, and `TransformStop` on it calls `Panic(0x4030)` at 0x1d74f. Never pressed alone. The free-before-audible-end seam is defined behaviour, not a fault. | well-supported (instruction text; no press) | `docs/deep/offline-2026-10-10/stack-transform.md` (not in this export) verdicts; `docs/field-log.md` (last entry) |

---

## 3. How it works

### 3.1 The probe lifecycle (exact commands)

Replace NNN with the probe number. All commands run from the repo root. Steps 1-8 need no device. Step 10 onward touches the speaker and is forbidden during the offline period.

| # | step | command or action | expected |
|---|---|---|---|
| 1 | write the assembler | copy the nearest assembler to `assemble_probeNNN.py` in build/hook/ (see section 3.8); edit its docstring FIRST: the one change, the press plan, the outcome table with a distinct id per path | the docstring is the spec |
| 2 | assemble and decode-verify | `python build/hook/assemble_probe<NNN>.py` | `decode-verify: all branches OK, boundaries OK`; a line `cave spans 0x3e21d..0x..., N words`; it also rewrites `probeNNN_words.json` and `probeNNN_cmd.txt` |
| 3 | the control, every time | `python tools/cavesim.py probe90` | `ended: leavel at 0x3E31E   AL = 0x000e` |
| 4 | every path of the new probe | `python tools/cavesim.py probeNNN --entry 0x3e21d --al 0x4004` (busy path, default); then `--fail TransformFromSink` (the full START); then one run per refusal (`--fail StreamKalimbaSink`, `--fail FileFind`, `--fail-after FileFind=2`, `--fail StreamFileSource`, `--fail TransformAdpcmDecode`, `--fail TransformStart`, `--fail KalimbaSendMessage`); `--dsp up` / `--dsp down`; `--teardown`; `--events N`; a non-hook event with `--al 0x4003 --once --expect replayed=1` | the line `prompt ids spoken, in order: 0xNN` gives each path's id; confirm each against the outcome table. For a loop probe add the world model: `--loop N --settle-ms MS --brief --expect chunks=N --expect violations=0` |
| 5 | regression batteries (when cavesim or shared cave code changed) | `python tools/cavesim_regress.py`; `python tools/cavesim_selftest.py`; `python tools/adpcm.py --selftest`; for loop probes `python build/hook/gate_probeNNN.py` | `169 cases: 169 identical`; `23 cases, 0 failed`; scenario counts |
| 6 | build the image | `python build/hook/assemble_probe<NNN>.py --build` (runs `tools/fsedit.py`, timeout 1200 s); then `sha256sum build/hook/probeNNN_brown.dfu` | no "fsedit failed". It rewrites the TRACKED scratch files `build/fsedit/probe.dfu` (not in this export) and `build/fsedit/x/04_fs0.bin` (not in this export). The build is reproducible |
| 7 | preflight and caveguard | `python tools/preflight.py probeNNN`; `python tools/caveguard.py probeNNN` | `OK    all N cave words and 3 redirect bytes verified in the image`; `all checked probes pass pre-flight`; `SAFE`; all branch forms attested |
| 8 | stack headroom, if the hook site is new or the frame exceeds `enterl -8` | `python tools/stackdepth.py <site> --frame N` | for 0x00E46: headroom 262, 8-word frame FITS |
| 9 | log the build | append `# probeNNN -- built DATE: <one-line change>` to `docs/field-log.md`: the change, the press plan, the gate outputs, the sha256 | written BEFORE the flash. Write the text with the Write tool to a scratch file, then `cat >> docs/field-log.md` |
| 10 | pre-device dry run | `python tools/flash_probe.py probeNNN --dry-run` | `preconditions OK; next cycle=K on unit 2`, `DRY RUN: stopping before enter-dfu`. Needs the device attached. NOT during the offline period |
| 11 | flash, foreground | `python tools/flash_probe.py probeNNN` (or the manual lines of FLASH-PROTOCOL step 3, then its Python comparison recipe) | every line read; the runner stops at the first unexpected line |
| 12 | check | FLASHED shows `verified=readback ... 0 of 975168 filesystem bytes differ; N/N words correct`; `list` shows 40fe; `info -f` shows `Main 3.0.3.6546` | anything else: STOP, no press |
| 13 | log the flash | append `# probeNNN -- flash #K on unit 2, DATE (tools/flash_probe.py)` quoting the key lines and the "AWAITING THE PRESS" conditions | |
| 14 | the press | ONE press under the written conditions; USB unplugged after the readback | |
| 15 | record the result | append `# probeNNN -- RESULT (DATE, owner, <conditions>): "<words>"` with the owner's words verbatim, then numbered readings and where the line stands. Negatives are results | BEFORE building anything else |
| 16 | audit | `python tools/docaudit.py` | `0 broken references, 0 failing overall`; add pointer lines to the `docs/RESUME-HERE.md` banner when told |
| 17 | commit (only when asked) | the repo is LOCAL-ONLY (no remote); untracked `probeNNN_readback.dfu` files stay as evidence and are never edited | |

### 3.2 The flash, line by line

    ./tools/bose-dfu/bose-dfu.exe enter-dfu          # "Note that device may take a few seconds to change mode"
    ./tools/bose-dfu/bose-dfu.exe list               # POLL until a line has 4022
    ./tools/bose-dfu/bose-dfu.exe download --force build/hook/probeNNN_brown.dfu
                                                     # "Waiting NN.NNNs, as requested by device, for firmware to manifest"
    ./tools/bose-dfu/bose-dfu.exe leave-dfu -f       # no errXXX anywhere in the output
    ./tools/bose-dfu/bose-dfu.exe list               # POLL until a line has 40fe
    ./tools/bose-dfu/bose-dfu.exe info -f            # "Current firmware: Main 3.0.3.6546"
    (write build/hook/FLASHED NOW, verified=PENDING)
    python tools/csr/dfu_upload.py build/hook/probeNNN_readback.dfu     # foreground, timeout 900

The last fatal session and the last good cycle used the SAME image (probe114). They differed at every line above: polling vs `sleep 5`, reading the "Waiting" line vs `>/dev/null`, checking `leave-dfu` vs `>/dev/null`, polling 40fe then `info` vs `list`/`info`, a foreground readback vs none, FLASHED updated vs never, foreground vs `run_in_background` (`docs/FLASH-PROTOCOL.md` side-by-side table).

### 3.3 The readback comparison

    FS, AREA0 = 975168, 0x6EA30
    rb = open('build/hook/probeNNN_readback.dfu','rb').read()
    fl = open('build/hook/probeNNN_brown.dfu','rb').read()
    ir, ifl = rb.find(b'fsr_dfu1'), fl.find(b'fsr_dfu1')
    d = sum(1 for i in range(FS) if rb[ir+i] != fl[ifl+i])          # require 0
    bad = [k for k, v in words.items()                              # require none
           if (rb[ir+AREA0+2*int(k,16)] | rb[ir+AREA0+2*int(k,16)+1] << 8) != (v & 0xffff)]

(The full script is in `docs/FLASH-PROTOCOL.md` step 4; `tools/flash_probe.py` implements it.) The 2026-10-02 cycle compared extracted files and printed 974,538 instead of 975,168; either is valid, record which. A readback of probe178 kept at `build/hook/probe178_readback.dfu` (not in this export) is evidence and contains the unit's private data: do not open it as text.

### 3.4 Press plans

The plan is written before the flash and has this shape (compare the docstring of `build/hook/assemble_probe179.py` and `docs/RETURN-CHECKLIST.md` section 2.2):

1. Conditions: what is connected (laptop over Bluetooth), what is playing, speaker volume, which button and gesture, how long to wait between presses, whether USB is unplugged.
2. A table: heard X / means Y / spoken id / next action. Every path of the cave has a row, success included.
3. A row for "a restart or crash" and one for "a loud runaway", each pointing at the kill switches.
4. A model prediction when cavesim can give one (chunk starts, gaps, the closing id).
5. A reading rule for ambiguous silence (what two causes the cave cannot tell apart).

The owner is asked to report: which probe, which button, exactly what was heard, duration, cut-off prompts. "Nothing happened" is a result.

### 3.5 Zero-flash experiments

Some questions cost a press but no flash, because the speaker already runs an image that exercises them (step 0 of the return checklist uses probe178 to test the busy read, ten consecutive presses, the settling press and the paused-unload timing). They are gates too: a restart in the busy-read press vetoes flashing probe179. The conditions, the owner decision that makes them knowing, and the verdict table are in `docs/RETURN-CHECKLIST.md` section 1.

### 3.6 How results are recorded (the chain)

1. The owner's words go into `docs/field-log.md` verbatim (RESULT entry).
2. FLASHED gets `verified=` with the readback numbers verbatim.
3. A short banner line goes into `docs/RESUME-HERE.md` (added, never rewritten).
4. Standing lessons go into the memory notes (`MEMORY.md` index): the cave window, the flash protocol, the port-3 chunk rules.
5. `python tools/docaudit.py` re-derives the numbers the docs assert and must pass.

### 3.7 cavesim: how to use the world model

    python tools/cavesim.py probe178 --entry 0x3E21D --loop 3 --press-gap 5000 --brief
    python tools/cavesim.py probe177 --entry 0x3E21D --music paused --press 0:4004 --press 8000:4004 --brief --expect spoken=3e
    python tools/cavesim.py probe179 --entry 0x3E21D --loop 3 --settle-ms 5000 --brief --expect chunks=3 --expect spoken=26 --expect violations=0 --expect pending=0
    python tools/cavesim.py probe179 --entry 0x3E21D --loop 3 --music paused --expect spoken=21
    python tools/cavesim.py probe179 --entry 0x3E21D --loop 3 --tail-ms 900          # expect R1, R3, R4 (the phase-dependent hazard)
    python tools/cavesim.py probe179 --entry 0x3E21D --al 0x4003 --once --expect replayed=1

Flags worth knowing (full list: `python tools/cavesim.py -h`; semantics: `docs/deep/offline-2026-10-10/cavesim-changes.md` section 2): `--loop N`, `--press MS:EVENT`, `--press-gap MS`, `--pending ID[@MS]`, `--music playing|paused`, `--unload-ms`, `--bt-teardown-at MS`, `--stock-prompt MS:DUR`, `--latch late|immediate`, `--free-edge eof|audible`, `--tail-ms`, `--fs-add`, `--pinfo`, `--expect KEY=VAL` (keys: chunks ended spoken violations rules pending swallowed replayed dsp looping), `--strict`, `--allow RULE`, `--enter handler --id HEX`, `--fail TRAP`, `--fail-after TRAP=N`, `--dsp up|down`, `--teardown`.

Reading its output: the `prompt ids spoken, in order:` line is the path's id; `port-3 rules: OK` means no R1-R6 hit; the chunk table gives starts, rates, lengths and the silence between chunks. A `--fail TransformFromSink` in a world run means "the read returns 0 even while the chunk is audible" (the hazard), not "the port is free"; for the old meaning use a world run with no chunk playing (`--once`).

To change cavesim itself: record goldens only from a cavesim you trust (`python tools/cavesim_regress.py --record`), and re-run the battery after every change (`tools/cavesim_regress.py` lists the 169 cases; it covers probe90 and probes 172-178 on 23 paths each plus probes 139, 140, 160, 161, 165, 168).

### 3.8 Recipe: build probe N+1 from probe N

Use the newest assembler whose design you are extending (today `build/hook/assemble_probe179.py`, or 180/181 which are built on it; probe178 is what is on the speaker). The smallest real example is 177 -> 178: one constant changed (`0x1072` word b from 0 to 2); `diff assemble_probe177.py assemble_probe178.py` is 89 lines, mostly docstring.

1. Preconditions. The previous probe's RESULT is in the field log, FLASHED shows its verified readback, and you can state the ONE change and the question it answers. If the previous probe is only built (179 today), N+1 is built on it for the offline plan; it is still not flashed before its predecessor's result is recorded.
2. Copy. `cp build/hook/assemble_probeN.py build/hook/assemble_probeM.py` (M = N+1). The script derives its probe name from its own file name (regex `assemble_(probe[0-9a-z]+)\.py`), so `probeM_words.json`, `probeM_cmd.txt` and `probeM_brown.dfu` are named automatically.
3. Rewrite the docstring first: the one change, why, the press plan, the outcome table. Give every new path a distinct id from the vocabulary in section 2c and check each against the stock-prompt collisions.
4. Make the one change. Keep `CAVE = 0x3E21D`, `HOOK = 0x00E46`, `REDIRECT_EDITS` and the encoding assert, the stub dictionary (`ca.STUB[...]`), the layout machinery (bands, connectors, region stubs) and the decode-verify block unchanged. Use `tools/caveasm.py` helpers (`ca.call1/2/3`, `ca.send_later`, `ca.imm_words`) rather than hand-writing trap sequences. Keep the frame at `enterl -8` and slots 0..5; save AH at handler entry; keep strings whole and in the window.
5. Run steps 2-5 of section 3.1. Exercise every path including each `--fail`. For a new trap or a new state, add a world-model scenario (see `build/hook/gate_probe180.py` as the pattern: a list of (description, flags, expectations) cases).
6. If the change touched shared code (layout, a helper) or cavesim, run `cavesim_regress.py` and `cavesim_selftest.py`.
7. Build (step 6), preflight and caveguard (step 7), stack headroom if the site or frame is new (step 8). Check the word count against 197 (window) and the region rule; if over, shrink the design.
8. Log the build in the field log (step 9), including the sha256, then stop. Flashing waits for the owner and for every gate of FLASH-PROTOCOL.

Things that bite: the assembler rewrites `probeM_words.json` and `probeM_cmd.txt` even without `--build`; `--build` dirties two tracked scratch files in `build/fsedit/`; a new probe is not in the regression battery until you add it; the `FIRST = 11` constant in the 179-181 assemblers (inherited from the probe141 staging code) is wrong for a staging window: `docs/deep/offline-2026-10-10/payload-184.md` (not in this export) says 9, and `docs/INDEX.md` section 1b lists it as a stale claim.

### 3.9 Why the protocol is shaped this way (the three lessons)

1. Verify the image where it matters: preflight proves the FILE, the readback proves the DEVICE. The field log records 35 readback verifications before the fatal session, which did none.
2. A tool that shares assumptions with what it checks proves nothing about those assumptions: the assembler and emulator share an opcode table, the assembler's own "zero and blind" test was the only placement check until probe130, and the 262-word stack figure was measured at a different site. Look for a check that does not share them (Bose's own usage, a readback, a press).
3. A working result is the signal to slow down, not to speed up: six images went out in the 67 minutes after probe77's tone played.

---

## 4. Traps and retractions

| what was believed | what is true | where it was corrected |
|---|---|---|
| `preflight.py` closes the gap between the emulator and the readback. | It checks the built file only. | `docs/POST-MORTEM-2026-10-04.md`; `docs/FLASH-PROTOCOL.md` |
| The readback tool does not exist. | `tools/csr/dfu_upload.py` has been in-tree since 2026-10-04; it was looked for at a guessed path. | `docs/FLASH-PROTOCOL.md` step 4 |
| The POWER + VOICE-ASSISTANT combo recovers a wedge. | It did not on 2026-10-08; unplug USB and hold POWER ~20 s. `docs/RUN-SHEET.md` (not in this export) still carries the old text. | `docs/FLASH-PROTOCOL.md` "Recovery" |
| `bose-dfu list` showing 40fe means the device is fine. | It needs only USB descriptors. Use `info -f`. | `docs/roadmap.md` |
| The window of 262 words is available. | 197. probe130 crashed. | `docs/cave-budget.md`; `docs/topics/cave-and-hooks.md` |
| The port-3 chunk lasts about 7 s. | About 219 s (219,528 bytes at 2000 Hz); every 7 s was the pairing teardown. Compute durations from file size x rate. | memory csr8670-port3-chunk-rules; `docs/field-log.md` probe173 |
| Re-gate or disconnect a running transform from a timer. | probe173 ran away loud and needed a power cycle. Never touch a busy port; never speak while the cave holds port 3; no timer re-arm until a chunk's end is detected. | memory csr8670-port3-chunk-rules |
| The stock teardown order ends a chunk safely from the cave. | It restarted the speaker twice (probes 174, 175). Static cause: `TransformStop` on the downstream node Panics. The stop path is retired. | `docs/deep/offline-2026-10-10/stack-transform.md` |
| "Busy presses in probes 176-178 did nothing and nothing crashed." | No press in 176-178 ever hit a running transform. The busy read on a running chunk is UNTESTED on hardware. | `docs/deep/offline-2026-10-10/verify.md` V2/V3 |
| The gap between chunks is about 1 s. | It is `ceil(D/POLL) x POLL - D`: 378 ms and 514 ms in the model, anywhere in 0..POLL_MS in general. | `docs/deep/offline-2026-10-10/cavesim-changes.md` section 6 |
| A free-before-audible-end read is a fault (the probe173 pattern); require two consecutive free reads. | It is defined behaviour; the mitigation is dropped. | `docs/deep/offline-2026-10-10/stack-transform.md` section 9; `docs/RETURN-CHECKLIST.md` section 6 |
| A pass of `docaudit` means the docs are consistent. | It does not read `docs/deep/offline-2026-10-10/`. | `docs/deep/offline-2026-10-10/README.md` section 0 |
| `docs/probe-test-sheet.md` (not in this export) is the current test protocol. | Only its catalog-sweep protocol is valid; the tests A-C and the press log are blank templates. | `docs/request-id-catalog.md` holds the finished catalog |
| `docs/RUN-SHEET.md` is the flash procedure. | It is a 2026-10-04 button-session page; its probe117-119 steps are history and its bose-dfu forms predate the `-f` rule. | `docs/FLASH-PROTOCOL.md` |
| `docs/NEXT-UNIT-CHECKLIST.md` (not in this export) is a live to-do list. | It was written on 2026-10-04 for the replacement speaker, which is now unit 2 and in service. Its rule that the first flash on a new unit is stock, read back and diffed, still stands for any further unit. | `docs/POST-MORTEM-2026-10-04.md` "Hard gates" |

| HidDfuCmd can back up the device. | It fails at 0% ("Device reports DFU length of zero"); readback uses `dfu_upload.py`. | `docs/FLASH-PROTOCOL.md` step 4 |

---

## 5. Open questions

| question | status | what would answer it |
|---|---|---|
| Does the busy read (`StreamKalimbaSink(3)` + `TransformFromSink` on a running chunk) crash? | untested; the only candidates (174, 175) crashed for a statically found other reason | step 0 of `docs/RETURN-CHECKLIST.md` (zero flash) |
| Is a poll tick delivered to the cave from the 0x00E46 hook? | well-supported, never observed | probe179 press A |
| How long before the audible end does the port read free (the "lead")? | unknown | step 0 "press 0, 2, 5 s after the end"; probe179 |
| How soon does the stock unload the DSP with music paused? | proven once (probe177); latency unmeasured | step 0 A4; probe179 press B |
| Is `MessageCancelFirst` from a cave a working STOP? | hypothesis (static list semantics only) | probe180 |
| Does a per-chunk leak accumulate over hours? | the stack reading says no leak on completed chunks; probe150/151 saw creation refused after ~55 ticks; the two disagree | a soak of about 500 chunks |
| Does the first chunk's 8 kHz / later 2 kHz rate behaviour have one cause? | unknown (three readings fit) | probe181 (rate 8000) |
| Are the cavesim defaults (unload 100 ms, 30 ms end-of-tone, free edge at EOF) right? | unknown | the presses above |
| Which of the offline probes will actually be flashed first on return, and in what order? | decided by the owner | `docs/RETURN-CHECKLIST.md` section 5 (decisions) |

---

## 6. Detailed knowledge (routing)

If you want the protocol itself: `docs/FLASH-PROTOCOL.md` (gates, recovery), `docs/POST-MORTEM-2026-10-04.md` (why), `tools/flash_probe.py` (the automated runner), `tools/csr/dfu_upload.py` (readback), `tools/bose-dfu/` (the DFU client).

If you want the first day back: `docs/RETURN-CHECKLIST.md` (section 0 gates with expected output, section 1 step 0, section 2 the 179 flash and press page, section 3 kill switches, section 6 amendments that win over DESIGN), then `docs/deep/offline-2026-10-10/README.md` section 4 (owner list) and `DESIGN.md` section 3 (the probe sequence 179-186).

If you want to build a probe: `build/hook/assemble_probe179.py` (newest template, its docstring is a complete press plan), `build/hook/assemble_probe178.py` and `build/hook/assemble_probe172.py` (the proven shapes), `tools/caveasm.py`, `docs/topics/cave-and-hooks.md`, `tools/fsedit.py` (how an edit list becomes a DFU).

If you want the simulator: `tools/cavesim.py -h`, `docs/deep/offline-2026-10-10/cavesim-changes.md`, `tools/cavesim_world.py`, `tools/cavesim_regress.py`, `tools/cavesim_selftest.py`, `build/hook/gate_probe180.py`.

If you want what an id means: `docs/request-id-catalog.md` (the 64 prompt ids; note D11 below), `docs/sink-events.md` (the 0x4xxx events), `docs/deep/offline-2026-10-10/promptmap.md` (not in this export) (what survives a data_us staging).

If you want the record of any probe: `docs/field-log.md` (search `# probeNNN`), `probeNNN_flash.log` in build/hook/ (the flash transcript), `build/hook/FLASHED` (the current state), `docs/RESUME-HERE.md` lines 1-40 (the banner).

If you want checks that the docs are sound: `python tools/docaudit.py` (facts), `python tools/doclinks.py` (links and references).

If you want recovery after a bad press: `docs/FLASH-PROTOCOL.md` "Recovery", `docs/RESUME-HERE.md` lines 156-205, `docs/field-log.md:11717` (the probe158 wedge) and `:11804` (the recovery flash to stock).

Known inconsistency to remember: `docs/request-id-catalog.md` says all 64 ids are owner-confirmed speech yet lists 0x02 0x03 0x05 0x07 0x0f 0x1a 0x1d as "(empty)". Re-listen only if an id from that set matters.

See also (strategy review 2026-10-12, offline, a recommendation; read the skeptic section of each note first): `docs/deep/strategy-2026-10-12/STRATEGY.md` (not in this export) section 4 (a proposed reordering of the probe sequence and a product build, not adopted) and section 8 (offline tasks J-T1 to J-T13), and `docs/deep/strategy-2026-10-12/02-loop-forever.md` (not in this export) (the loop lifecycle audit that the 179-181 press pages test).

See also (firmware study 2026-10-12, offline, static or model results; read the skeptic section of each note first; index `docs/deep/firmware-study-2026-10-12/README.md` (not in this export), functions `docs/FUNCTION-CATALOG.md` (not in this export)): `T03-cavesim-and-seam-model.md` (the new world flags and `tools/seammodel.py`), `T06c-volume-census-probe.md` (the read-only census image probe187), `T11-product-build-and-press-pages.md` (press pages and outcome tables for 181p, 184a, 184; the gate-5 conflict for loop images is owner decision T11-N1) and `T08-184a-184-assemblers.md` (nine outcome ids, one per class).

## See also (round 3, 2026-10-12)

Added at the end so that no cited line moved. Round 3 is offline and static or model work; nothing was run on the speaker. Index and corrections register: `docs/deep/round3-2026-10-12/README.md` (not in this export); the facts are in `docs/FACTS.md` section 10.

- `docs/deep/round3-2026-10-12/PLAN-v2.md` (not in this export): the revised flash sequence, gates and the 32 owner decisions (a recommendation).
- `docs/deep/round3-2026-10-12/V04-verify-187-181p-pb-spec.md` (not in this export): press-page defects found by an independent verifier; gate 5/6 conflict for loop images (owner decision PD-02).
- `docs/deep/round3-2026-10-12/T14-tool-owner-round3.md` (not in this export): tool changes and their regression evidence; `docs/PROBE-CATALOG.md` section 12 lists every image built in round 3 with its verifier status (builder gate only unless stated).

## See also (2026-10-28)

Spoken read-outs with check digits (F327), the LastArrivalDate reset check (F328), safe console event ids (F310), short offline gates (one reduced world run), the measurement kit `tools/measure/`, and the lessons list of `docs/dsp-generator-route.md` section 7.
