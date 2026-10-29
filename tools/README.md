# tools/ -- every script that acts as a tool, by job

Purpose: one place that says what each tool is for, the exact command line, what it reads and writes, whether it is safe to run with no speaker attached, and which docs cite it.
Status / last verified: 2026-10-10 (command lines read from each tool's argparse or docstring; the checkers and self-tests listed in section 4 were RUN on 2026-10-10 and their output is quoted). Round 3 (2026-10-12): section 16 at the end lists the tools added or changed (trapcat, seammodel options, cavesim options, the new assemblers and gates).

> This is an archival research document; it links into some internal process files (`docs/RETURN-CHECKLIST.md`, `docs/PROJECT-LAYOUT.md`, `docs/INDEX.md`) not included in this public export.

Read next: `docs/FLASH-PROTOCOL.md` (the gates), `README.md` (this export's own repository layout).

Confidence marks follow the project convention: **proven** (a command, output or source line is quoted), **well-supported**, **hypothesis**. Where the older inventory or a docstring disagrees with the code, the code wins and the disagreement is listed in section 14.

## 0. Rules for anyone running a tool here

1. Run everything from the repo root: `python tools/<name>.py ...` (proven: the scripts compute `ROOT` from `__file__`; `tools/flash_probe.py` does `os.chdir(ROOT)`).
2. **DEVICE: do not run offline.** These touch USB. With no speaker attached, do not run them:
   `tools/flash_probe.py` (also with `--dry-run`, see 7.1), `tools/bose-dfu/bose-dfu.exe`, `tools/csr/dfu_upload.py`, `tools/csr/dfu_download.py`, `tools/csr/tap_sweep.py`.
   `tools/csr/analyse_dump.py` (not included in this export) opened a device dump (link keys, serials); it is not a tool this export ships or needs.
3. Never open a readback or dump (`*_readback.dfu`, `private/*.bin`): they hold Bluetooth link keys and serials. Listing names and sizes is fine.
4. Several tools overwrite TRACKED files. Before running them check the "Writes" line: `tools/gen-stub-table.py` (rewrites `tools/bose-stubs.json` and `docs/trap-stub-table.md`), `tools/cavesim_regress.py --record` (rewrites the golden files), the assemblers with `--build` (rewrite `build/fsedit/probe.dfu` and `build/fsedit/x/04_fs0.bin`, per `docs/RETURN-CHECKLIST.md` row 0.13).
5. Every script resolves its own root via `os.path.dirname(os.path.abspath(__file__))`, so the repo can be moved or cloned anywhere.
6. `tools/fsedit.py` and `tools/make_probe_variants.py` use the in-tree `tools/csr/`; there is no out-of-tree fallback in this export.
7. The foreground rules of `docs/FLASH-PROTOCOL.md` apply to any run longer than a few seconds that touches the device: foreground, poll by elapsed time, read every line.

## 1. One-screen map by job

| Job | Tool | Offline-safe | One line |
|---|---|---|---|
| Analyse a recording | `tools/recan.py FILE.wav [--from S --to S --win 2 --period 14.74]` | yes | per-window rms, 50 ms cv, spectral tilt (brown noise about -6 dB/oct), bursts, STEADY/BURSTY verdict, chunk-cadence autocorrelation (2026-10-17) |
| Assemble | `build/hook/assemble_probe*.py` | yes | one assembler per probe; `--build` writes the signed-compatible DFU via fsedit |
| Assemble | `tools/caveasm.py`, `tools/liftfn.py` | yes | libraries for trap-call sequences / lifting compiled leaf functions |
| Assemble | `tools/fsedit.py` | yes | the signed-DFU patcher (blind-byte edits, digest cancelled) |
| Simulate | `tools/cavesim.py` (+ `cavesim_world.py`, `xapemu.py`) | yes | run a probe's cave in the speaker's own vm.app with stubbed traps; clocked world model |
| Simulate | `build/hook/gate_probe180.py`, `gate_probe181.py` | yes | scripted world-model scenarios for probes 180 / 181 |
| Verify | `tools/preflight.py` | yes | the BUILT dfu contains what the assembler intended (not a readback) |
| Verify | `tools/caveguard.py` | yes | cave words inside 0x3E200..0x3E400 and branch forms attested |
| Verify | `tools/stackdepth.py` | yes | stack headroom at a hook address |
| Verify | `tools/csrdfu.py info`, `tools/csr/csrverify.py` | yes | checksum audit of a DFU container |
| Flash / readback | `tools/flash_probe.py` | **DEVICE** | FLASH-PROTOCOL steps 3-4 as one foreground process |
| Flash / readback | `tools/bose-dfu/bose-dfu.exe` | **DEVICE** | third-party HID DFU CLI (enter-dfu, list, download, leave-dfu, info) |
| Flash / readback | `tools/csr/dfu_upload.py` | **DEVICE** | read-only readback of the flash |
| Flash / readback | `tools/csr/tap_sweep.py`, `tools/csr/dfu_download.py` | **DEVICE** | recovery probe / spare writer |
| Extract / pack | `tools/csrdfu.py`, `tools/csr/csrpack.py`, `csrfspack.py`, `dumpfs.py`, `psdump.py` | yes | parse, list, extract, repack DFU containers and the iFel filesystem |
| Analyse firmware | `tools/disasm.py`, `callsites.py`, `switchtab.py`, `fnprofile.py`, `conststrings.py`, `promptmap.py`, `stackdisasm.py`, `kapdisasm.py` | yes | read-only static analysis of vm.app, the BT stack and the Kalimba images |
| Analyse firmware | `tools/libmatch.py`, `libscan.py`, `opcodes.py`, `extract-traps.py`, `gen-stub-table.py` | yes | name functions from ADK libraries; derive opcode and trap tables |
| Noise / ADPCM | `tools/adpcm.py`, `tools/brownnoise.py`, `tools/noisespec.py` | yes | the codec, the payload generator, the old generator's spectrum |
| Signing | `tools/csrhash.py`, `build/sign/*` | yes | how the fs signature hash works; nobody can sign for Bose |
| Docs checkers | `tools/docaudit.py`, `tools/doclinks.py` | yes | numbers-vs-docs audit; link and reference checker |
| Regression | `tools/cavesim_regress.py`, `tools/cavesim_selftest.py` | yes | byte-identical battery; mock-cave self-test |

## 2. The lifecycle of a probe, in order

Worked example in prose: probe178 is what `build/hook/FLASHED` says is on the speaker. Replace NNN by the probe number. Every command except step 5 is offline-safe (proven: none opens USB; read in source).

```
# 0 orient
cat build/hook/FLASHED                       # what is on the speaker (docaudit enforces the docs against it)
python tools/docaudit.py                     # expect: 46 fact checks, 0 broken references, 0 failing overall

# 1 assemble (writes build/hook/probeNNN_words.json and probeNNN_cmd.txt; no DFU yet)
python build/hook/assemble_probeNNN.py       # expect: decode-verify: all branches OK

# 2 simulate (the CONTROL first, every time)
python tools/cavesim.py probe90              # expect last line: ended: leavel at 0x3E31E   AL = 0x000e
python tools/cavesim.py probeNNN --entry 0x3E21D --al 4004 [--fail TRAPNAME] [--dsp up] [--teardown] ...
python build/hook/gate_probeNNN.py           # only probes 180, 181 have one
python tools/cavesim_regress.py              # only if tools/cavesim.py or cavesim_world.py changed

# 3 build the image (runs tools/fsedit.py with the edit list in probeNNN_cmd.txt; needs adk/root/tools/bin/dfubuild.exe)
python build/hook/assemble_probeNNN.py --build   # writes build/hook/probeNNN_brown.dfu

# 4 verify the built FILE (not the device)
python tools/preflight.py probeNNN           # also runs caveguard; expect: all checked probes pass pre-flight
python tools/caveguard.py probeNNN           # cave window + attested branch forms
python tools/stackdepth.py 0xHOOK [--frame N]   # only if the hook site is new; the address argument is REQUIRED

# 5 compare sha256sum of the image with the recorded hash (docs/RETURN-CHECKLIST.md row 0.14), then flash (DEVICE -- not offline)
python tools/flash_probe.py probeNNN         # DEVICE: steps 3-4 of the protocol in one foreground process

# 6 one press, then write the result into docs/field-log.md (append-only) and update build/hook/FLASHED notes
python tools/docaudit.py                     # must pass after any docs edit
python tools/doclinks.py                     # BROKEN must be 0 for files you touched
```

The manual alternative to step 5 is the command list in `docs/FLASH-PROTOCOL.md` step 3 and step 4 (`bose-dfu.exe enter-dfu`, `list`, `download --force`, `leave-dfu -f`, `list`, `info -f`, then `dfu_upload.py` and the marker-aligned compare). `flash_probe.py` does exactly those steps and stops at the first unexpected line (its docstring, lines 1-24).

## 3. Quick router: "I want to ..."

| I want to | Use | Section |
|---|---|---|
| know whether a built image is what I intended | `tools/preflight.py` | 4.1 |
| check my cave is inside the proven window | `tools/caveguard.py` | 4.2 |
| see how a cave behaves before a press | `tools/cavesim.py` | 5.1 |
| edit the signed filesystem | `tools/fsedit.py` | 6.1 |
| read a function in vm.app | `tools/disasm.py --fn 0x846` | 9.1 |
| find what arguments Bose passes to a trap | `tools/callsites.py NAME ...` | 9.2 |
| generate or check brown-noise payload bytes | `tools/brownnoise.py`, `tools/adpcm.py` | 10.2, 10.1 |
| check a DFU file's checksums | `tools/csrdfu.py info FILE` | 8.1 |
| list files inside a DFU's filesystem | `tools/csrdfu.py extract` or `tools/csr/csrfspack.py --list` | 8.1, 8.4 |
| know what a spoken prompt id does | `tools/promptmap.py --id N` | 9.4 |
| check docs agree with the facts | `tools/docaudit.py`, `tools/doclinks.py` | 4.4, 4.5 |

## 4. Verify and checker tools

Observed on 2026-10-10 on this machine (proven: output quoted):

| Checker | Command | Observed result | Run time |
|---|---|---|---|
| docaudit | `python tools/docaudit.py` | `device: probe178 -- PROBE` then `46 fact checks, 0 broken references, 0 failing overall` | short (not timed) |
| preflight | `python tools/preflight.py probe178` | `OK all 124 cave words and 3 redirect bytes verified in the image`, `all checked probes pass pre-flight` | short (not timed) |
| caveguard | `python tools/caveguard.py probe178` | `all emitted forms are attested in Bose firmware` | short (not timed) |
| stackdepth | `python tools/stackdepth.py 0xAE0 --frame 24` | `headroom at that point: 316 - 54 = **262 words**`, `a cave frame of 24 words: FITS (238 words would remain)` | short (not timed) |
| cavesim_regress | `python tools/cavesim_regress.py` | `169 cases: 169 identical, 0 differ, 0 missing golden` | about 1 min 50 s |
| cavesim_selftest | `python tools/cavesim_selftest.py` | ends `23 cases, 0 failed` | about 2 min |
| doclinks | `python tools/doclinks.py` | prints BROKEN lines and `SUMMARY files=.. BROKEN=..`; at the time of the run 4 BROKEN were reported in other agents' docs (see 4.5) | short (not timed) |
| doclinks self-test | `python tools/doclinks.py --selftest` | `selftest OK` | short (not timed) |
| adpcm self-test | `python tools/adpcm.py --selftest` | `selftest OK` | short (not timed) |
| brownnoise self-test | `python tools/brownnoise.py --selftest` | `brownnoise selftest: OK (brown round-trip SNR 23.0 dB)` | short (not timed) |
| promptmap self-test | `python tools/promptmap.py --selftest` | `44 checks, ALL PASSED` | short (not timed) |

### 4.1 tools/preflight.py -- is the built DFU what the assembler intended?

- Purpose: verify the BUILT dfu, offline, between the emulator and the readback. Confirms same length as the official image, `fsr_dfu1` at the same offset, every cave word at its own address, every redirect byte, and that every differing byte is explained as cave, redirect or digest compensation (docstring lines 1-22).
- Run: `python tools/preflight.py probe178 [probe179 ...]`. With NO argument it checks the stale default list `probe114 probe117 probe118 probe119` (`tools/preflight.py` line 125), so always pass the probe name.
- In: `build/hook/probe*_brown.dfu`, `build/hook/probe*_words.json`, `build/hook/assemble_probe*.py` (it parses `REDIRECT_EDITS` out of the assembler source by regex), `firmware/bose/minnow_3.0.3/Minnow_3.0.3_stack_plus_app.dfu`. Out: stdout only. Calls `caveguard.check` and `caveguard.attest` (lines 84-89).
- Offline-safe: yes. It is NOT a readback and never touches the speaker.
- Gotcha: cave word at project address `a` lives at fs-area offset `0x6EA30 + 2*a`, low byte first; a wrong mapping would pass vacuously, which is why step 2 of its checks gives the result its force (docstring).
- Cited by: `docs/FLASH-PROTOCOL.md`, `docs/POST-MORTEM-2026-10-04.md`, `docs/NEXT-UNIT-CHECKLIST.md`, `docs/RETURN-CHECKLIST.md`, `docs/PROJECT-LAYOUT.md`, `docs/cave-budget.md`; run by `tools/flash_probe.py` as a precondition.

### 4.2 tools/caveguard.py -- cave window and branch forms

- Purpose: (a) with no argument, audit every zero run of 16 or more words in the const pool; (b) with a probe name, check every cave word lies in `0x3E200..0x3E400` and that every emitted branch form is attested in Bose firmware (`attest`; "UNATTESTED FORM -- do not flash").
- Run: `python tools/caveguard.py` (audit; prints 7 zero runs and a verdict per run) or `python tools/caveguard.py probe178 [probe179 ...]`. Exit 0 only if both checks pass (lines 273-277).
- In: `build/hook/probe*_words.json`, `firmware/bose/extracted/internal_fs/vm.app`, `build/analysis/full-disasm.txt` (generated by `tools/disasm.py`). Out: stdout.
- Offline-safe: yes.
- Gotchas: born from probe130, which crashed the speaker on boot: "zero does not mean unread" (docstring). The window `0x3E200..0x3E400` (about 197 words) is a hard rule in the owner's memory notes. A second region class (dead code in the AVRCP-browse block) is listed function by function in the file's comments (lines 37-50); it is not a rule to extend.
- Cited by: `docs/FLASH-PROTOCOL.md` step 1b, `docs/cave-budget.md`, `docs/deep/code-region-plan.md`, `docs/deep/space-survey.md`, `docs/RESUME-HERE.md`, `docs/RETURN-CHECKLIST.md`.

### 4.3 tools/stackdepth.py -- stack headroom at a hook

- Purpose: walk the call graph backwards from a hook address summing `enterl` frames; the stack size is vm.app header word [09] (316 words for Bose, proven by the run above).
- Run: `python tools/stackdepth.py 0xAE0 [--frame 24]`. The `addr` argument is **required**: running it with no argument fails with `error: the following arguments are required: addr` (proven). `docs/FLASH-PROTOCOL.md` step 2 shows the bare command; that line is out of date.
- In: `firmware/bose/extracted/internal_fs/vm.app`. Out: stdout.
- Offline-safe: yes.
- Gotchas: follows direct `bsr` edges only, so the number is a LOWER bound on depth and an UPPER bound on headroom; measure the site you hook, not a nearby one (probe127 used a figure from a shallower site).
- Cited by: `docs/FLASH-PROTOCOL.md`, `docs/roadmap.md` rule 0, `docs/cave-heap.md`, `docs/POST-MORTEM-2026-10-04.md`, `docs/deep/offline-2026-10-10/DESIGN.md`.

### 4.4 tools/docaudit.py -- recompute the load-bearing numbers and check the docs say them

- Purpose: re-derive facts from artifacts and check that named docs still contain the exact text; also reports broken backtick paths in `docs/*.md` and `README.md`.
- Run: `python tools/docaudit.py [-v|--verbose]`. Exit 1 on any failure.
- In: `build/hook/FLASHED`, `docs/RESUME-HERE.md`, `docs/field-log.md`, other docs, `vm.app`. Out: stdout.
- Offline-safe: yes.
- Gotchas: the check set is chosen from `status=` in `build/hook/FLASHED` (device / LOST / STOCK); a stale FLASHED makes it enforce falsehoods. It looks for exact strings in `docs/RESUME-HERE.md` (for example `**probe178** (`build/hook/probe178_brown.dfu`)`), so edit that file only by adding lines and re-run. `docs/field-log.md` is append-only evidence it reads. Do not move or rename docs.
- Cited by: `docs/FLASH-PROTOCOL.md`, `docs/PROJECT-LAYOUT.md`, `docs/NEXT-UNIT-CHECKLIST.md`, `docs/RETURN-CHECKLIST.md`, `docs/roadmap.md`.

### 4.5 tools/doclinks.py -- offline link and reference checker (new 2026-10-10)

- Purpose: scan `docs/**/*.md`, `README.md`, `tools/README.md`, `build/README.md`, `CLAUDE.md` (those present) for markdown links, backtick repo paths (optional `:NNN` and `#anchor`) and `field-log.md:NNN` line references; fenced code blocks are skipped.
- Run: `python tools/doclinks.py [--strict] [--list-orphans [--direct]] [--json] [--root DIR] [--selftest]`. Exit 1 only if BROKEN > 0; `--strict` also fails on NOTE, ANCHOR-MISSING and LINE-OUT-OF-RANGE. `--list-orphans` lists docs not reachable from `docs/INDEX.md` (or from `README.md` and `docs/RESUME-HERE.md` before the index exists).
- Finding classes: BROKEN (missing target), ANCHOR-MISSING, LINE-OUT-OF-RANGE (field-log line beyond its length), NOTE (missing target under a git-ignored generated prefix such as `build/analysis/`, `adk/`, `firmware/bose/extracted/`, `BT STUFF/`, `repo/`).
- Offline-safe: yes; standard library only; targets that leave the repo are not checked and never opened (line 205).
- Gotcha: a backtick path containing a placeholder such as NNN is treated as a real path and reported BROKEN; write `*` instead (globs are skipped) or use a fenced block. Paths in backticks are repo-root relative, so ADK-relative paths are reported BROKEN too. At the time of the first run (2026-10-10, 66 files) it reported 4 BROKEN, all in other docs: docs/toolchain.md lines 54 and 56 (ADK-relative paths that tools/docaudit.py whitelists), adpcm-format.md line 279 in docs/deep/offline-2026-10-10/ (an ADK-relative SampleAudioPrompts path), and write-constraint.md line 202 in the same folder (names docs/AGENT-BRIEF.md; the file is docs/deep/AGENT-BRIEF.md). The count changes as docs change; re-run it.
- Cited by: not yet cited by any doc (its own header names `docs/INDEX.md` as read-next).

### 4.6 Related container checks

`python tools/csrdfu.py info FILE.dfu` and `python tools/csr/csrverify.py FILE.dfu` verify every checksum of a DFU container; see 8.1 and 8.3.

## 5. Simulate

### 5.1 tools/cavesim.py -- run a cave in the emulator before flashing

- Purpose: load a probe's generated words into the speaker's own `vm.app`, stub the traps with plausible return values, run the cave in `tools/xapemu.py`, report the trap sequence, exit AL, spoken prompt ids and buffers. It answers "is this cave well-formed", not "will the speaker make a noise" (docstring).
- Run, common forms (all read from `argparse` at lines 541-674):
  - `python tools/cavesim.py probe90` -- the CONTROL; expect `ended: leavel at 0x3E31E   AL = 0x000e` (proven in `docs/RETURN-CHECKLIST.md` row 0.4 and by the regression battery).
  - `python tools/cavesim.py probe178 --entry 0x3E21D --al 4004` -- the default busy path; `--entry` is needed since probe105; `--ah EVENT` / `--al EVENT` set the registers the hook passes (every probe since 109 gates on the event id 0x4004).
  - `--fail TRAP` (repeatable) makes a trap return 0; `--fail-after TRAP=N` fails from the Nth call; `--mem ADDR=VAL` presets a data word; `--steps N` caps steps.
  - DSP handshake: `--dsp up|down`, `--teardown`, `--events N`, `--dsp-refuse ID`.
  - Probe-specific: `--staged JSON` (probe141), `--pmap JSON` (probe139), `--dump`.
  - World model (opt-in, clocked, B2): `--loop N`, `--press MS:EVENT`, `--press-gap MS`, `--pending ID[@MS]`, `--once`, `--horizon`, `--settle-ms`, `--poll-floor`, `--stock-rate`, `--latch late|immediate`, `--free-edge eof|audible`, `--tail-ms`, `--tone-end-ms`, `--music playing|paused`, `--unload-ms`, `--chunk-ms`, `--stock-prompt MS:DUR`, `--bt-teardown-at`, `--unload-at`, `--music-resume-at`, `--fs-add PATH=SIZE|@FILE[:VIS]`, `--src-window`, `--src-endian le|be`, `--pinfo PART:KEY=VAL`, `--p2-mounted`, `--p2-automount`, `--p2-preloaded`, `--expect KEY=VAL` (exit 1 on mismatch), `--strict` (exit 2 on a rule violation), `--allow RULE`, `--brief`, `--enter hook|handler`, `--id`, `--task`, `--frame SLOT=VAL`, `--x`, `--y`, `--show ADDR[:N]`.
  - Example (probe178, three press cycles on a virtual clock): `python tools/cavesim.py probe178 --entry 0x3E21D --loop 3 --press-gap 5000 --brief` (docstring).
- In: `build/hook/probe*_words.json` (or any path ending `.json` as the probe argument), `vm.app`. Out: stdout only.
- Offline-safe: yes.
- Gotchas: every stub and every world-model line is a MODEL, not a measurement; real trap behaviour stays "hypothesis" until a press. Exercise every path including each `--fail` bail and confirm the spoken id of each (`docs/FLASH-PROTOCOL.md` step 1). Any change to `cavesim.py` or `cavesim_world.py` must pass `tools/cavesim_regress.py` (169 cases byte-identical). Assumption table: `docs/deep/offline-2026-10-10/cavesim-changes.md`.
- Cited by: `docs/FLASH-PROTOCOL.md`, `docs/NEXT-UNIT-CHECKLIST.md`, `docs/RESUME-HERE.md`, `docs/RETURN-CHECKLIST.md`, `docs/roadmap.md`, `docs/cave-frame.md`, `docs/adk-compiler.md`, `docs/xap-opcodes.md`, `docs/deep/offline-2026-10-10/` (README, DESIGN, cavesim-changes, payload-184, design-risk).

### 5.2 tools/cavesim_world.py -- the clocked world model

- Purpose: virtual ms clock, event queue, MessageSendLater, port-3 chunks, rules R1-R6, file system and partition models behind `--world/--loop/--press`. Imported by `cavesim.py` only when a world flag is given.
- Run: not run directly (library). In/out: none of its own.
- Offline-safe: yes. Gotcha: every line is a MODEL; see the assumption table in `docs/deep/offline-2026-10-10/cavesim-changes.md`.
- Cited by: `docs/PROJECT-LAYOUT.md`, `docs/RESUME-HERE.md`, `docs/deep/offline-2026-10-10/cavesim-changes.md`, `README.md` and `payload-184.md` in that folder.

### 5.3 tools/xapemu.py -- the XAP2 interpreter

- Purpose: interpreter under `cavesim.py`; logs memory effective addresses and registers; unknown opcodes raise.
- Run: library (`import xapemu`). Its `__main__` runs a hard-coded demo of the function at 0x7e1a using an absolute repo path (lines 408-416); do not rely on it.
- Offline-safe: yes. Gotcha: the docstring's "91.7% opcode coverage" is an older figure (hypothesis that it is stale); `tools/opcodes.py --gaps` lists opcodes it does not model.
- Cited by: `docs/RESUME-HERE.md`, `docs/adk-compiler.md`, `docs/xap-opcodes.md`, `docs/deep/offline-2026-10-10/cavesim-changes.md`.
- 2026-10-19 multiply fix: opcodes `0x90` `mul #imm`, `0x91` `mul @abs`, `0x92` `mul @(n,X)`, `0x93` `mul @(n,Y)` are now all modelled (signed 16x16 into AH:AL; unsigned after `0x0009`). `0x90` used to be skipped as a "byte-extend quirk" and `0x92` stopped the run ("unmodelled opcode 0x92"); the two sites named for the quirk, vm.app `0xf593`/`0xf5b1`, are `mul #3 ; ld X,@0xffe1`, a real table-offset multiply. Emulations of functions that use `mul` (`fn_22a89`, `fn_07d5d`, `fn_0f58c`, `fn_08674`, `fn_061e0`) made before this date are suspect. Self-tests: `xapemu_mul_cases()` in `tools/cavesim_selftest.py`; report `docs/deep/material-2026-10-19/AE-xapemu-mul-fix.md`.
- 2026-10-19 divide: `0x94` #imm, `0x95` @abs, `0x96` @(n,X), `0x97` @(n,Y) are all modelled (AH:AL / operand, quotient in AL, remainder in AH, signed truncating, unsigned after `0x0009`); `0x96` used to stop the run ("unmodelled opcode 0x96", `fn_22a98`). Self-tests: `xapemu_div_cases()` in `tools/cavesim_selftest.py` (26 cases, incl. `fn_22a98`, `fn_0dece`, `fn_22a89`, `fn_1f3e9` on the real vm.app); AE section 9.
- 2026-10-19 shifts and `tst #imm`: `0xA2` `asl @(n,X)` (12 sites in vm.app) and `0xA6` `asr @(n,X)` (0 sites) are now modelled (count = memory word & 0x1F, same as `0xA1/0xA3/0xA5/0xA7`), and `0x98` `tst #imm` (5 sites: Z from the immediate). `0x9E` `bsr rel,X` (1 site, message loop 0x39611) is still unmodelled because its semantics are unproven. Census tool: `python tools/xapemu_opscan.py` (lists opcode classes in vm.app code that the emulator raises on; exit 1 while `0x9E` remains). Self-tests: `xapemu_shift_cases()` (12 cases); AE sections 11-13.
- 2026-10-19 flags: `tst @(n,X)` (0x9A) now sets N as well as Z (7 `bpl`/`bmi` sites in vm.app, 4 in the printf core), and `nadd`/`neg` (hi nibble 7) now sets C = 1 iff val >= reg (the 32-bit negate idiom at 0x39abf proves it for `neg`). Pair-shift counts are STILL masked to 5 bits: silicon behaviour at 32 is unknown, do not change without proof. Self-tests: `xapemu_flag_cases()` (27 cases); AE section 14; BJ section 6.

### 5.4 tools/cavesim_regress.py -- byte-identical regression battery

- Purpose: the rule when cavesim grows is that the probe90 control and every probe172..178 run print exactly the same bytes. This runs 169 cases and diffs against `build/analysis/cavesim-golden/`.
- Run: `python tools/cavesim_regress.py` (diff; exit 1 on any difference), `python tools/cavesim_regress.py --list` (prints the 169 cases), `python tools/cavesim_regress.py --record` (overwrites the golden files: do this ONLY from a trusted cavesim, e.g. HEAD).
- Offline-safe: yes (without `--record`). Observed: `169 cases: 169 identical, 0 differ, 0 missing golden` in about 1 min 50 s.
- Gotcha: the golden files were recorded from the cavesim of commit 34d9c45 (before B2).
- Cited by: `docs/PROJECT-LAYOUT.md`, `docs/RESUME-HERE.md`, `docs/RETURN-CHECKLIST.md`, `docs/deep/offline-2026-10-10/` (README, cavesim-changes, REVIEW-part2).

### 5.5 tools/cavesim_selftest.py -- mock caves through the world model

- Purpose: builds MOCK probes from `build/hook/assemble_probe178.py`'s layout machinery (program section replaced) and drives them through `cavesim.py --loop ... --expect`.
- Run: `python tools/cavesim_selftest.py [--keep DIR]` (words go to a temp dir unless `--keep`). Exit 0 only when every expectation passes. Observed: `23 cases, 0 failed`, about 2 minutes.
- Offline-safe: yes; writes nothing under `build/hook/`.
- Gotcha: the docstring names two mocks (mock179, mock180); the file defines four (mock179, mock180, mock182, mock185b), and the run prints PASS lines for 182 and 185 cases too (proven). Mocks are not probes and are never flashed.
- Cited by: `docs/PROJECT-LAYOUT.md`, `docs/RETURN-CHECKLIST.md`, `docs/deep/offline-2026-10-10/` (README, cavesim-changes, REVIEW-part2).

### 5.6 build/hook/gate_probe180.py, gate_probe181.py -- per-probe world-model gates

- Purpose: scripted scenarios (start, loop, stop mid-chunk, DSP down, BT teardown, each trap refused, hazard families) through `cavesim.py --expect`. Exit 0 = every scenario holds.
- Run: `python build/hook/assemble_probe180.py` first (writes the words), then `python build/hook/gate_probe180.py`; same for 181.
- Offline-safe: yes. Gotcha: cannot cover the real `MessageCancelFirst` behaviour from a cave; the press settles it. Probes 180 and 181 are not yet flashed.
- Cited by: `docs/RETURN-CHECKLIST.md`, `docs/deep/offline-2026-10-10/REVIEW-part2.md`.

### 5.7 build/hook/verify_probe145..161.py, smoke_probe12/13.py -- legacy

Older per-probe emulator checks superseded by `cavesim.py`; cited only in the field log. Do not treat them as current gates.

## 6. Assemble and build

### 6.1 tools/fsedit.py -- the signed-DFU patcher

- Purpose: write bytes into the "blind" positions (bytes 34..62 of each 64-byte content block) of the signed filesystem, rebalance the body XOR, cancel the 32-bit digest by a GF(2) solve, keep Bose's RSA signature valid. Proven end to end 2026-09-27 (probe8: accepted, booted, persisted); mechanism in `docs/dfu-signature-scheme.md`.
- Run: `python tools/fsedit.py --edit AREA_BYTE_OFFSET=HEX [--edit ...] --out OUT.dfu` or `python tools/fsedit.py --demo --out OUT.dfu`. Offsets are within the fs area (the fs body starts at area byte 140, 0x8C); both the offset and the value are parsed with `int(x, 0)`, so write the value with a `0x` prefix (`--edit 0x706bd=0x04`, as in `build/hook/probe178_cmd.txt`; a bare `5a` would fail). `--out` is required.
- In: `firmware/bose/minnow_3.0.3/Minnow_3.0.3_stack_plus_app.dfu`; needs `adk/root/tools/bin/dfubuild.exe` (the digest oracle; part of the vendor ADK, NOT included in this export -- see `docs/toolchain.md` and `build/patches/` for a no-ADK alternative), `tools/csr/csrpack.py` and `csrverify.py`, and the compensation pool `build/hook/slack_pool.json` (line 51; the original data_us pool is `build/sign/dfutest/L_pool.json`). Out: the patched DFU; scratch in `build/fsedit/`.
- Offline-safe: yes. Flashing is a separate manual step.
- Gotchas: edits outside blind bytes, in the table/names/trailer, or with odd flip parity are refused. Compensation flips land in the last 256 bytes of data_us ("tolerated, not structurally safe"; re-test voice prompts after any flash that lands them, comment at lines 52-63). `build/fsedit/probe.dfu` and `build/fsedit/x/04_fs0.bin` are tracked scratch files that every build rewrites.
- Cited by: `docs/dfu-signature-scheme.md`, `docs/PROJECT-LAYOUT.md`, `docs/RESUME-HERE.md`, `docs/content-control-analysis.md`, `docs/next-probe-v2-idswap.md`, `docs/adk-tools.md`, `docs/deep/offline-2026-10-10/` (design-risk, material-slots, verify, write-constraint).

### 6.2 build/hook/assemble_probe*.py -- one assembler per probe (168 files)

- Purpose: lays out the cave words, redirect bytes and design/press table (the docstring is the probe's design). Without `--build` it writes `build/hook/probe*_words.json` and `probeNNN_cmd.txt` (the fsedit command) and prints `edit list ready (...)`. With `--build` it runs the fsedit command (timeout 1200 s) and writes `build/hook/probe*_brown.dfu`. The only flag read is `--build` (`sys.argv`, proven for probes 179 and 181).
- Run: `python build/hook/assemble_probe178.py` (expect `decode-verify: all branches OK`) then `python build/hook/assemble_probe178.py --build`.
- Offline-safe: yes. Gotchas: cave words must stay in 0x3E200..0x3E400; hand-written trap sequences caused probes 39-47 and 53 to fail (use `tools/caveasm.py`). Only the assembler of the probe about to be flashed is a live gate. Probes 179, 180, 181 are built and gated offline and NOT flashed.
- Cited by: `docs/FLASH-PROTOCOL.md` step 1, every probe entry in `docs/RESUME-HERE.md`.

### 6.3 tools/caveasm.py -- trap-call emitter (library)

- Purpose: emit VM trap-call sequences with the verified ABI: arg1 in AL, arg2 in AH, args 3..n at `@(0,Y)`.., a 32-bit argument takes two slots high word first, return in AL (docstring; `docs/trap-abi.md`, `docs/message-task-abi.md`).
- Run: `import caveasm as ca` inside an assembler (exposes `call2`, `send_later`, `const_addr`, `imm_words`, `STUB`). No CLI.
- Offline-safe: yes. Gotcha: "every wrong-argument bug in probes 39-47, 53 came from hand-writing trap sequences".
- Cited by: `docs/trap-abi.md`, `docs/message-task-abi.md`, `README.md`.

### 6.4 tools/liftfn.py -- lift a compiled leaf function into cave items

- Purpose: decode one function from a linked `.app` with its `.map` and `.sym` and emit layout items (`('w', ..)`, `('br', op, label)`, `('label', n)`) so the cave assembler recomputes branches after banding. Written because probes 68, 69, 72, 73 crashed on hand-transcribed opcodes.
- Run: `python tools/liftfn.py build/noiseprobe/noiseprobe noise_fill [--json out.json]`.
- Offline-safe: yes. Gotcha: refuses `bsr` (leaf functions only) and anything a cave cannot host. Used for the probe ~68-130 generators; later generators are hand assembly (`build/payload/gen_test.py`).
- Cited by: `docs/cave-frame.md`, `docs/roadmap.md`.

### 6.5 tools/make_probe_variants.py and tools/make_stack_probe.py -- legacy, images meant to be rejected

- `python tools/make_probe_variants.py [--out-dir DIR] [--force]` builds `probe2_fs_pad.dfu`, `probe3_fs_xorfix.dfu`, `probe4_ps_unsigned.dfu` into `firmware/bose/probe/` (git-ignored) to map where the loader checks (2026-09 signature mapping; result in `docs/dfu-signature-scheme.md`).
- `python tools/make_stack_probe.py [--out PATH] [--force]` builds the Route A2 probe (a harmless change in the unsigned stack area, CRCs recomputed) to `firmware/bose/probe/Minnow_3.0.3_stack_probe1.dfu`. It was rejected on 2026-09-24 with errFILE, cause unknown (memory note "Unsigned stack area").
- Offline-safe: yes (the stack-probe docstring: "Only reads and writes files. Never opens the USB device."). **Never flash their outputs** without the owner's go-ahead.
- Cited by: `docs/PROJECT-LAYOUT.md`, `README.md`, `docs/device-support.md`.

## 7. Flash and readback (all touch USB: DEVICE, do not run offline)

### 7.1 tools/flash_probe.py -- FLASH-PROTOCOL steps 3 and 4 as one foreground process

- Purpose: a single call that runs every gate itself and STOPS at the first unexpected line. Steps (docstring lines 1-24): preconditions (image, words, assembler exist; `tools/preflight.py` passes; `bose-dfu list` shows `05a7:40fe`, refuses to start from DFU mode); `enter-dfu`; poll `list` by ELAPSED 60 s for 4022; `download --force` (900 s); `leave-dfu -f` (STOP on any errXXX); poll for 40fe; `info -f` must show `Main 3.0.3.6546`; write `build/hook/FLASHED` with `verified=PENDING` first; readback via `tools/csr/dfu_upload.py` (900 s) and the marker-aligned compare (require 0 of 975,168 filesystem bytes differ and 0 words wrong); poll again, `info -f`, write `verified=` verbatim.
- Run: `python tools/flash_probe.py probeNNN [--dry-run]` -- **DEVICE: do not run offline.** The only options are the probe name and `--dry-run` (`sys.argv` at lines 35-36).
- In: `build/hook/probe*_brown.dfu`, `probeNNN_words.json`, `assemble_probeNNN.py`. Out: `build/hook/FLASHED`, `build/hook/probe*_readback.dfu` (contains link keys: never open), `build/hook/probe*_flash.log` (appended; opened at import, so even a dry run creates or extends it).
- **`--dry-run` is not device-free**: the preconditions run `bose-dfu.exe list` (USB enumeration) before the dry-run exit (lines 109-128, proven by reading). Do not use it as an offline check; use `tools/preflight.py` instead.
- Gotchas: never background it, never redirect to `/dev/null`, no fixed sleeps. Exit code 2 means it STOPPED with the device in whatever state the last step left; read the Recovery section of `docs/FLASH-PROTOCOL.md`. It hard-codes `FS = 975168` and `AREA0 = 0x6EA30`. `docs/FLASH-PROTOCOL.md` never names it (it documents the manual commands); the doc and the script are consistent (csrdfu extract gives 974,538 bytes, the marker-aligned recipe 975,168; both valid, record which).
- Introduced 2026-10-08. Cited by: `docs/RETURN-CHECKLIST.md`, `docs/deep/offline-2026-10-10/` (DESIGN, README, REVIEW-part2); many field-log entries.

### 7.2 tools/bose-dfu/bose-dfu.exe -- third-party HID DFU CLI

- Purpose: tchebb/bose-dfu, a Rust CLI. Subcommands used by the protocol: `enter-dfu`, `list`, `download --force FILE`, `leave-dfu -f`, `info -f` (`docs/FLASH-PROTOCOL.md` step 3). 1,456,640 bytes, dated 2026-09-22.
- Run: only as the protocol's step 3 prescribes, or via `flash_probe.py`. **DEVICE: do not run offline** (not even `list`; it enumerates USB).
- Gotchas: `-f` is required on `download` and `leave-dfu` for this device ("untested or ambiguous-mode device"). A second `enter-dfu` is not a safe retry. `HidDfuCmd backup` does not work here (length zero, `docs/toolchain.md`). Never judge success from an exit code; read the line the protocol says to expect.

### 7.3 tools/csr/dfu_upload.py -- read-only readback

- Purpose: read the flash image off a Bose device in DFU mode (PID 0x4022); enters DFU itself if the device is in normal mode (0x40fe); always tries to leave DFU on exit, including on error.
- Run: `python tools/csr/dfu_upload.py build/hook/probe*_readback.dfu` (one positional argument, the output file; foreground with `timeout 900`) -- **DEVICE: do not run offline**.
- In: the device. Out: the file (about 1.76 MB; contains link keys and serials: never open). Needs the `hid` module. MAX_BYTES is 8 MiB.
- Cited by: `docs/FLASH-PROTOCOL.md` step 4, `docs/POST-MORTEM-2026-10-04.md`, `docs/NEXT-UNIT-CHECKLIST.md`, `docs/RETURN-CHECKLIST.md`, `docs/PROJECT-LAYOUT.md`, `docs/partition-route.md`, `docs/toolchain.md`. Skipping its step cost unit 1 (2026-10-04).

### 7.3b tools/csr/virtual_press.py -- the virtual centre press (DEVICE, 2026-10-27)

`python tools/csr/virtual_press.py press | volup | voldown | code`: computes the unit-keyed unlock code from `bose-dfu info -f`, sends TAP `db 96 <code>` and one `kp` line in HID Feature report 6 (only kp 196 = centre LONG 0x4004, 176 = volume up, 160 = volume down are allowed). Power on/off of the speaker: `tap_sweep.py "pw 1"` / `"pw 0"`. Proven on hardware, with the dangers listed: `docs/deep/material-2026-10-27/CR-tap-power-keys.md` sections 3 and 8.

This talks to a diagnostic/test console Bose already built into the stock firmware -- it predates this project and works the same way on a completely unflashed speaker. Using it does not flash, patch, or modify the device; it is a USB HID client sending bytes to an interface that was always there, not a capability this project added or unlocked in the sense of creating.

### 7.3c tools/click_detect.py -- glitch finder for microphone recordings of the looped noise (2026-10-27)

`python -I tools/click_detect.py rec.wav --skip 40 [--json out.json]`: aligns every loop to the payload, builds the empirical template of the recording and reports the SEAM gap per loop, timeline STEPs (3-4 ms insertions), unique BURST events and the SEAM HF energy. Gain independent; start recordings in silence and start the noise inside them. Workflow, validation and baseline: `docs/deep/material-2026-10-27/CS-click-detection-workflow.md`.

### 7.3d tools/seamfix.py -- make an ADPCM noise payload survive the speaker's early chunk cut (2026-10-27)

`python -I tools/seamfix.py IN.adpcm OUT.adpcm [--cut 160] [--fade 480]`: the speaker cuts every chunk about 160 samples before its end (measured by click_detect.py: SEAM gap -3.3 ms), so the loop joins sample N-160 to a decoder restarted at (0,0). seamfix fades the last audible part to zero before the cut point and zeroes everything after, same length, same first bytes. Background and the first test: `docs/deep/material-2026-10-27/CS-click-detection-workflow.md` section 6.

### 7.4 tools/csr/tap_sweep.py -- TAP verbs (diagnostic)

- Purpose: sends bare TAP verbs (HID usage page 0xFF00) taken from vm.app's table C (18 entries). Only verbs given on the command line are sent; the handle is re-opened per command.
- Run: `python tools/csr/tap_sweep.py vr` -- **DEVICE**. `vr` is the recovery probe of `docs/FLASH-PROTOCOL.md` Recovery step 2.
- Gotcha: an unsupported verb can stall.
- Cited by: `docs/FLASH-PROTOCOL.md`, `docs/RETURN-CHECKLIST.md`.

### 7.5 tools/csr/dfu_download.py -- independent writer (spare)

- Purpose: writes a DFU image over HID using the framing from bose-dfu. `python tools/csr/dfu_download.py --dry-run IMAGE` and `python tools/csr/dfu_download.py --expect-sha256 HEX IMAGE --i-mean-it`. Aborts on the first non-OK status.
- **DEVICE** even with `--dry-run`: the dry run enumerates HID devices to print what is visible (lines 154-156). The loop uses `bose-dfu.exe`; do not use this instead without a documented reason.
- Cited by: `docs/partition-route.md`, `README.md`.

## 8. Extract and pack: images, containers, filesystems, persistent store

### 8.1 tools/csrdfu.py -- container parser and extractor (current)

- Purpose: parse CSR-dfu2 files and `fsr_dfu1` filesystem images. `python tools/csrdfu.py info FILE.dfu` prints ok/BAD per check and exits 1 if anything is BAD (observed on the stock image: `file crc ok`, `suffix signature ok crc ok`). `python tools/csrdfu.py extract FILE.dfu|ext.xuv|ext.bin OUTDIR` keeps the filesystem tree under `fs_<offset>/`.
- Offline-safe: yes. Cited by: `docs/FLASH-PROTOCOL.md`, `docs/RESUME-HERE.md`, `README.md`.
- Gotcha: not the same file as `tools/csr/csrdfu.py` (section 13).

### 8.2 tools/csr/csrpack.py -- clean-room DFU container writer

- `python tools/csr/csrpack.py --roundtrip FILE.dfu` (must be byte-identical), `--extract FILE.dfu OUTDIR/`, `--rebuild FILE.dfu OUTDIR/ NEW.dfu`.
- Recomputes stack CRC, three PS CRCs, fs XOR, file_crc and suffix CRC; copies RSA signatures through unchanged. Gotcha: it cannot make signatures and the device DOES verify them (a 6-byte change gave errFIRMWARE, 2026-09-20). Used by `tools/fsedit.py`. Cited by `docs/device-support.md`, `README.md`.

### 8.3 tools/csr/csrverify.py

`python tools/csr/csrverify.py FILE.dfu` checks every checksum against its stored value (CRC is `zlib.crc32 ^ 0xFFFFFFFF`). Prerequisite of `fsedit.py`. Cited by `README.md`.

### 8.4 tools/csr/csrfspack.py -- clean-room packer for the iFel filesystem

`python tools/csr/csrfspack.py --roundtrip FS.bin`, `--list FS.bin`, `--replace FS.bin /PATH NEWFILE OUT.bin`. Also imported for `Fs.build()` by `build/payload/` scripts. Gotcha: its docstring calls the digest field "unidentified"; that is older text, `tools/fsedit.py` later solved the compensation (section 6.1). Cited by `docs/device-support.md`, `docs/partition-route.md`, `docs/deep/offline-2026-10-10/` (design-mvp, material-slots).

### 8.5 tools/csr/dumpfs.py, csrfs.py, psdump.py, dspdump.py, xuv2bin.py

| Tool | Command | Purpose | Notes |
|---|---|---|---|
| `tools/csr/dumpfs.py` | `python tools/csr/dumpfs.py FILE.dfu [OUTDIR]` | dump the VM filesystem from a DFU or raw `fsr_dfu1`, entropy per file | `parse_fs` is imported by `build/payload/make_narrow_payload.py` to cross-check its own parser; cited by `docs/dsp-noise-route.md`, `docs/partition-route.md`, `payload-184.md`, `verify.md` |
| `tools/csr/csrfs.py` | `python tools/csr/csrfs.py FILE [OUTDIR]` | list / extract the filesystem from a container or bare blob | overlaps `csrdfu.py extract`; `README.md` only |
| `tools/csr/psdump.py` | `python tools/csr/psdump.py FILE.dfu` | dump every Persistent Store record with PSKEY names from `tools/csr/pskeys_gordon.json` | "never guess PSKEY numbers from memory"; `README.md` |
| `tools/pskeys.py` | `python tools/pskeys.py FILE.dfu pskeys.txt` | list PS keys with names from an ADK `pskeys.txt` | overlaps psdump; `docs/NEXT-UNIT-CHECKLIST.md`, `docs/deep/AGENT-BRIEF.md` |
| `tools/csr/dspdump.py` | `python tools/csr/dspdump.py FILE.dfu [--json out.json]` | extract PSKEY_DSP9..26 parameter blocks | coefficient layout NOT established (docstring); no doc cites it |
| `tools/csr/xuv2bin.py` | `python tools/csr/xuv2bin.py in.xuv out.bin` | `@addr word` text to little-endian binary (no docstring) | no doc cites it |

All are offline-safe; none of them opens USB.

## 9. Analyse firmware (read-only static analysis)

### 9.1 tools/disasm.py -- whole-image vm.app disassembly (primary reading tool)

- Purpose: decode all 236,514 code words with BlueLab 7.3 trap names, a cross-reference index, and the hook-site search (every 3-word bsr/bra whose operand bytes lie in DFU blind windows).
- Run: `python tools/disasm.py` (all three outputs), `python tools/disasm.py --fn 0x846` (one function to stdout), `python tools/disasm.py --hooks` (hook-site report only).
- Out: `build/analysis/full-disasm.txt`, `build/analysis/xref.json`, `build/analysis/hook-sites.txt` (git-ignored, generated; about 11.7 MB). `tools/caveguard.py` reads `full-disasm.txt`.
- Offline-safe: yes. Cited by: `docs/firmware-map.md`, `docs/hook-sites.md`, `docs/PROJECT-LAYOUT.md`, `docs/RESUME-HERE.md`, `docs/deep/` (AGENT-BRIEF, buffer-cadence, centre-long-press, code-region-plan), `docs/deep/offline-2026-10-10/` (chunk-end, controls, stack-transform, verify).

### 9.2 tools/callsites.py -- constant-tracked trap arguments

`python tools/callsites.py StreamAudioSink SinkConfigure` and `python tools/callsites.py --list`. Uses the verified ABI (arg1 AL, arg2 AH, rest at `@(n,Y)`); reports None rather than guess. Use it instead of `tools/xapvm/xapvm.py`'s `args()`, which uses the old wrong ABI. Cited by `docs/content-control-analysis.md`.

### 9.3 tools/switchtab.py, fnprofile.py, conststrings.py

| Tool | Command | Purpose | Cited by |
|---|---|---|---|
| `tools/switchtab.py` | `python tools/switchtab.py [ADDR [LEN]]` | find and resolve `cmp/bcc/brxl` jump tables | `docs/centre-button-hook.md`, `docs/xap-opcodes.md`, `docs/deep/prompt-audio-pump.md`, `docs/deep/space-survey.md` |
| `tools/fnprofile.py` | `python tools/fnprofile.py` | classify functions by reachable trap stubs; rank unnamed ones by callers (hard-coded repo path) | `docs/PROJECT-LAYOUT.md`, `docs/RESUME-HERE.md` |
| `tools/conststrings.py` | `python tools/conststrings.py [REGEX ...] > build/analysis/const-strings.txt` | debug strings from the const pool (one char per 16-bit word; address = what `ld AL,#addr` uses) | `docs/const-strings.md`, `docs/deep/AGENT-BRIEF.md` |

### 9.4 tools/promptmap.py -- spoken request id to rphrases_us payload to data_us bytes

- Purpose: finding (docstring, with evidence in `docs/deep/offline-2026-10-10/promptmap.md`): `rphrases_us` is the NowSpeakTTS phoneme script, not a `data_us` directory; request id N is table entry N+1 (read in `fn_1ee80`); `data_us` is a two-region voice database; a staged payload overwrites the region-B header including E2, so no unit-based prompt can be certified untouched.
- Run: `python tools/promptmap.py --selftest`, `--table`, `--regions`, `--stock`, `--id 0x27 [--bytes 30268] [--layout old|corrected|both]`, `--footprint N [N ...]`, `--untouched`, `--relocate`, `--summary`, `--hits`, `--header-after`, `--json PATH`.
- Offline-safe: yes (reads the extracted `rphrases_us` and `data_us`). Observed: selftest `44 checks, ALL PASSED`. Model limits (which bytes the DSP actually reads per unit) are hypothesis.
- Cited by: `docs/RETURN-CHECKLIST.md`, `docs/deep/offline-2026-10-10/` (promptmap, REVIEW-part2).

### 9.5 tools/stackdisasm.py and tools/kapdisasm.py

- `python tools/stackdisasm.py [--probe] [--big]`: disassemble the Bluetooth stack `firmware/bose/extracted/stack_prog.bin` (751,112 bytes) to `build/analysis/stack-disasm.txt`; `--probe` reports without writing; little-endian was chosen by `enterl`/`leavel` structure (6613 vs 3445 enterl). Addresses are word indices from file start and are NOT vm.app addresses. Cited by `docs/NEXT-UNIT-CHECKLIST.md`, `docs/deep/offline-2026-10-10/` (README, stack-transform).
- `python tools/kapdisasm.py [IMAGE] [--out DIR]`: `IMAGE` is one of `sbc_decoder`, `NowSpeakTTS`, `soundClearNb`, `soundClearWb` (a name, not a file path; no argument = all four), read from `firmware/bose/extracted/internal_fs`. Needs `adk/root/tools/bin/kobjdump.exe` (present). Writes to `build/analysis/kalimba/`. Cited by `docs/kalimba-disasm.md`, `docs/firmware-map.md`, `docs/PROJECT-LAYOUT.md`, `docs/RESUME-HERE.md`.

### 9.6 Library and table derivation (mostly one-shots)

| Tool | Command | Purpose | Notes |
|---|---|---|---|
| `tools/libmatch.py` | `python tools/libmatch.py build/sustainprobe/sustainprobe [--min 8]` | name Bose functions by matching opcode sequences of a linked ADK probe | short matches can be false positives; `docs/library-matching.md`, `docs/firmware-map.md` |
| `tools/libscan.py` | `python tools/libscan.py [FILTER ...] [--min 14] [--asm DIR]` | same over all 153 ADK `.a` libraries without linking | a miss means nothing; `docs/library-matching.md` |
| `tools/gen-sink-asm.sh` | `sh tools/gen-sink-asm.sh OUTDIR` (env `HW=`, `SW=`) | compile the ADK 4.3.1 sink app to assembly for `libscan --asm` | wrong hw/sw pair fails with `ExPatternArraySizeMismatch`; `docs/library-matching.md` |
| `tools/opcodes.py` | `python tools/opcodes.py build/opprobe/opprobe [--gaps]` | derive the XAP2 opcode table from compiler `.xap` vs `.app` | `--gaps` = opcodes `xapemu` does not model; `docs/xap-opcodes.md` |
| `tools/extract-traps.py` | `python tools/extract-traps.py VMBUILDER.exe [out.json]` | extract the trap table from an ADK `vmbuilder.exe` | one-shot, done; produced `tools/traps-bluelab73.json` and `traps-bluelab74.json`; `docs/trap-numbering.md`, `docs/toolchain.md` |
| `tools/gen-stub-table.py` | `python tools/gen-stub-table.py` | regenerate `tools/bose-stubs.json` and `docs/trap-stub-table.md` | **overwrites two tracked files**; must use the 7.3 table (the 7.4 table made probes 46, 47, 52-56 call wrong traps) |

Data: `tools/traps-bluelab73.json` is the correct trap table for this speaker (VM version 0x3200); do not use `traps-bluelab74.json` for Bose images. `tools/bose-stubs.json` is the stub table.

### 9.7 tools/xapvm/ -- the vm.app reader (basis of most tools)

- `python tools/xapvm/xapvm.py VM.APP` prints every trap stub and constant arguments (`usage: python xapvm.py <vm.app>`). `tools/xapvm/README.md` documents the opcode encoding and the 2026-09-27 table. It reads `tools/traps-bluelab73.json` (line 100).
- `tools/xapvm/analyze.py` is legacy: function discovery and per-function listings into `build/analysis/functions/`; its names came from the superseded 7.4 trap table, so do not trust its trap names (use `tools/disasm.py`).
- Gotcha: `xapvm.args()` uses the OLD wrong ABI; use `tools/callsites.py`. The README's mention of a `traps.json` of 272 entries is stale: no file of that name exists under tools/.
- Cited by: `docs/xap-opcodes.md`, `docs/trap-numbering.md`, `docs/bose-firmware-anatomy.md`, `docs/dfu-signature-scheme.md`, `docs/deep/AGENT-BRIEF.md`.

## 10. Noise and ADPCM generation

### 10.1 tools/adpcm.py -- the codec

- Purpose: IMA ADPCM in the exact dialect of the ADK `voice_prompt_tool` and `TransformAdpcmDecode`: no headers, high nibble first, state starts (0,0). The encoder reproduces the ADK tool's output byte for byte (2000/2000, 3000/3000, 5001 samples, and 33,504/33,504 bytes on 16 vendor prompt files; docstring, `docs/deep/offline-2026-10-10/adpcm-format.md`). The textbook quantiser agrees on only 65% of bytes and is NOT this dialect.
- Run: `python tools/adpcm.py --selftest`; `python tools/adpcm.py encode in.pcm out.adpcm [--prm]`; `python tools/adpcm.py decode in.adpcm out.pcm|out.wav [--rate N]`. The input of `encode` is **raw little-endian int16 PCM**, not a WAV (docstring lines 40-44). `--prm` pads to an even length like the ADK tool.
- Offline-safe: yes; pure Python, no numpy. Observed: `selftest OK`.
- Cited by: `docs/PROJECT-LAYOUT.md`, `docs/RESUME-HERE.md`, `docs/RETURN-CHECKLIST.md`, `docs/deep/offline-2026-10-10/` (adpcm-format, DESIGN, design-mvp, design-risk, verify, README, REVIEW-part2).

### 10.2 tools/brownnoise.py -- brown-noise payload generator

- Purpose: Gaussian noise through a leaky integrator, optional 2nd-order high-pass, optional loopable crossfade, normalised, encoded with `adpcm.py` from state (0,0); writes the payload, a `.wav` preview of the decoded payload, and a report (level, clipping, octave slope, round-trip SNR, loop-seam step, onset). `--interleave PERIOD:LO-HI --stock random|zeros|file:PATH[:OFFSET]` models the DFU blind-window interleave and reports NAIVE vs AWARE encodings.
- Run (from the docstring, lines 21-30):
  `python tools/brownnoise.py --rate 8000 --bytes 219528 --loop --out build/noise/brown_8000_219528.bin`
  `python tools/brownnoise.py --rate 2000 --seconds 20 --out build/brownnoise/brown_2000.adpcm`
  `python tools/brownnoise.py --rate 2000 --seconds 10 --interleave 64:34-62 --stock random`
  `python tools/brownnoise.py --seam-test build/noise/brown_8000_219528.bin --rate 8000`
  `python tools/brownnoise.py --selftest`
  Options with defaults (code, lines 394-396): `--rate 2000`, `--seconds 20`, `--peak 0.5`, `--leak 10`, `--hp 20`, `--xfade 50`, `--seed 1`, `--out`, `--wav`, `--also-rate`, `--bytes N` (exact payload size, 2 samples per byte; overrides `--seconds`), `--pattern-name`, flag `--loop`.
- Offline-safe: yes. Observed selftest: `brownnoise selftest: OK (brown round-trip SNR 23.0 dB)`.
- Gotchas: it never claims how the speaker sounds; the owner's ear judges. Exact slot sizes for `--bytes`: rphrases_us 10,486; soundClearWb.kap 65,242; data_us 219,528 (docstring).
- Cited by: `docs/PROJECT-LAYOUT.md`, `docs/RESUME-HERE.md`, `docs/deep/offline-2026-10-10/` (adpcm-format, design-mvp, design-risk, DESIGN, payload-184, README).

### 10.3 tools/noisespec.py and the one-off generator analyses

| Tool | Command | Purpose | Notes |
|---|---|---|---|
| `tools/noisespec.py` | `python tools/noisespec.py [NWORDS ...]` (default `639 636`) | spectrum of the OLD on-device `nib_fill` generator; defines `ima_decode` reused by the analysers below | needs numpy (`import numpy as np`); `docs/NEXT-UNIT-CHECKLIST.md`, `docs/PROJECT-LAYOUT.md` |
| `tools/primesweep.py` | `python tools/primesweep.py` | priming count vs loudness for a single pass at NWORDS=126 | legacy, pre-probe134; hard-coded repo path; no doc cites it |
| `tools/bandcheck.py` | `python tools/bandcheck.py` | energy by band, PRIME 9 vs 12 | legacy; hard-coded path; no doc cites it |
| `tools/boundtest.py` | `python tools/boundtest.py` | bounded-walk principle vs rate | legacy; hard-coded path; field log only |
| `tools/cheaptrack.py` | `python tools/cheaptrack.py` | cheap predictor trackers vs exact | legacy; hard-coded path; field log only |
| `tools/fsspec.py`, `tools/kapspec.py` | `python tools/fsspec.py`, `python tools/kapspec.py` | how files / `.kap` binaries sound through `TransformAdpcmDecode` (clipping, step index, slope) | legacy, uncited; hard-coded paths; kapspec carries a stale scratchpad note |

Findings from these one-offs are in the field log, not in the scripts.

### 10.4 build/payload/ -- payload builders for the material probes

| Tool | Command | Purpose | Status |
|---|---|---|---|
| `build/payload/make_narrow_payload.py` | `python build/payload/make_narrow_payload.py [--name N] [--no-ext-version] [--scratch DIR] [--no-dry-run] [--no-world] [--regenerate] [--peak P] [--adpcm FILE] [--start-period N] [--out DIR] [--no-edits-module]` | probe184 payload: a minimal partition-2 ROFS with ONE narrow (flags 0x00) brown-noise file, offline verification, staging plan into `data_us` blind windows; outputs only to `build/payload/narrow184/`; any failed check exits 1 | current; see `docs/deep/offline-2026-10-10/payload-184.md` |
| `build/payload/make_payload.py` | `python build/payload/make_payload.py` | earlier ROFS wrapping a flags-0x40 `brown.kap`; output `build/payload/brown_fs.bin` | legacy; signature and digest are the official ext image's and STALE by design |
| `build/payload/stage_payload.py` | `python build/payload/stage_payload.py` | stage `brown_fs.bin` into `data_us` blind windows and emit the probe141 kit | legacy; its window constants are 2 words off (per the `make_narrow_payload.py` docstring) |
| `build/payload/probe141_edits.py` | imported | generated data: 33,040 `(area_byte, value)` edits for probe141 | legacy data |
| `build/payload/gen_test.py` | `python build/payload/gen_test.py` | hand-written 48-word XAP brown-noise generator verified bit-exact in cavesim | no doc cites it; the generator that made the word budget fit |
| `build/payload/opus_gen.py` | `python3 build/payload/opus_gen.py` | 54-word generator plus mini emulator from an external consult | legacy; its own header says verify in YOUR cavesim; do not flash its words |

All offline-safe. `build/hook/make_opus_task.py` (assembles `opus_task/ANALYSIS_TASK.md`) is legacy.

## 11. Signing (what was learned; nothing here can sign for Bose)

No private key for Bose exists in the project. The method is "blind-byte editing" (`tools/fsedit.py`), never re-signing. Evidence trail: `docs/dfu-signature-scheme.md`.

- `tools/csrhash.py`: reimplementation of the fs signature hash (8-chain MD5 variant, RSA e=3), validated against CSR's `dfusign.exe`. `python tools/csrhash.py AREA` prints the 128-byte block; `python tools/csrhash.py --block AREA` prints only the block; `python tools/csrhash.py AREA --verify SIGNED_AREA` reports the signature size. The docstring also lists `--sig` and `--S` options that `main()` does not implement (lines 148-180). Imported by `tools/fsedit.py` (`fs_block`). Cited by `docs/dfu-signature-scheme.md`, `docs/deep/offline-2026-10-10/` (verify, write-constraint).
- `tools/recover_modulus.py`: legacy GCD recovery of the signing modulus; superseded by `build/sign/recover_bose_modulus.py` (result `build/sign/bose_n.txt`: 1024-bit n with S^3 mod n equal to the hash block for all 7 releases, 2026-09-26). Public data; there is still no private exponent. Cited only by itself.
- `build/sign/`: legacy evidence of the 2026-09-24..27 reverse engineering: patched copies of `dfusign.exe` (`dfusign_*.exe`, third-party code: do not run), `patch_logger*.py`, `run_logger2.py`, 21 `dbg*.py` debugger scripts (they spawn processes), `digest_candidates.py`, `recover_diag.py`, `sweep_compare.py`, `validate_finalize.py`, test inputs (`*.xuv`, `*.fs`), `dfutest/`, `pf_test/`. Several hard-code the repo path. `build/sign/dfutest/L_pool.json` is the compensation pool `fsedit.py` uses. Do not rerun; do not move.

## 12. Third-party and reference material

| Path | What | Notes |
|---|---|---|
| `tools/bose-dfu/bose-dfu.exe` | tchebb/bose-dfu binary (NOT included in this export; obtain from the upstream `tchebb/bose-dfu` project) | DEVICE; section 7.2 |
| `tools/innoextract/` | Inno Setup unpacker (NOT included in this export; a separately licensed third-party tool, used only to unpack the vendor ADK installers) | third-party; not run in this session |
| `tools/csr-dfu-parser-ref/` | `CSRDFU.bt` (010 Editor template), `unpack_dfu_fs.1sc`, README, LICENSE | reference for the DFU format |
| `tools/csr/AN093.txt`, `AN093-csr-dfu-spec.pdf` (NOT included in this export; CSR's own spec document carries its own non-disclosure notice -- see NOTICE), `pskeys_gordon.json` (included) | CSR DFU spec and PSKEY name table | read by `psdump.py` |
| `tools/traps-bluelab73.json`, `traps-bluelab74.json`, `bose-stubs.json` | trap tables | 7.3 is the correct one |

## 13. Legacy and dead-by-path tools (kept as evidence)

| Tool | Why it is legacy |
|---|---|

| `tools/csr/fschk.py` | 15-line fs-XOR check on two deleted scratchpad files; candidate for deletion |
| `tools/csr/csrdfu.py` | older exploratory container parser with an entropy report; superseded by `tools/csrdfu.py` |
| `tools/csr/csrfs.py` | overlaps `tools/csrdfu.py extract` and `tools/csr/dumpfs.py` |
| `tools/xapvm/analyze.py` | superseded by `tools/disasm.py`; 7.4 trap names |
| `tools/recover_modulus.py` | superseded; see section 11 |
| `build/hook/verify_probe145..161.py`, `smoke_probe12/13.py`, `_p16dbg.py`, `make_opus_task.py` | superseded by cavesim; field-log only |

## 14. Discrepancies found while writing this file (code beats docs; newer beats older)

| # | Statement elsewhere | What the code shows (proven by reading or running) |
|---|---|---|
| 1 | `docs/FLASH-PROTOCOL.md` step 2: `python tools/stackdepth.py` gives the declared stack size | the `addr` argument is required; the bare command exits with an argparse error |
| 2 | `docs/FLASH-PROTOCOL.md` documents only manual flash commands | `tools/flash_probe.py` (introduced 2026-10-08, used for probe178's flash) runs them; the protocol file never names it |
| 3 | earlier inventory: `flash_probe.py --dry-run` is a safe check | it runs `bose-dfu.exe list` first (USB enumeration) |
| 4 | earlier inventory: `adpcm.py encode in.wav out.bin` | `encode` takes raw little-endian int16 PCM, not a WAV |
| 5 | earlier inventory: `kapdisasm.py <file.kap>` | the argument is an image NAME (`sbc_decoder`, `NowSpeakTTS`, `soundClearNb`, `soundClearWb`) |
| 6 | earlier inventory: `fsedit.py` needed an out-of-tree tool | it uses the in-tree `tools/csr/` only in this export |
| 7 | earlier inventory: `tools/doclinks.py` purpose unknown | it is the offline link checker (section 4.5) |
| 8 | `tools/cavesim_selftest.py` docstring: two mocks | the file defines four mocks and the run executes 23 cases |
| 9 | `tools/preflight.py` default (no argument) | checks probes 114, 117, 118, 119; always pass a probe name |
| 10 | `tools/csr/csrfspack.py` docstring: digest "unidentified" | solved later by `tools/csrhash.py` and `tools/fsedit.py` (digest cancelled by a GF(2) solve); the docstring is older |
| 11 | `tools/xapvm/README.md` mentions a `traps.json` of 272 entries | the code reads `tools/traps-bluelab73.json`; no file named traps.json exists under tools/ |
| 12 | `tools/csrhash.py` docstring lists `--sig` and `--S` | `main()` implements `--block` and `--verify` only |
| 13 | `tools/xapemu.py` docstring: 91.7% opcode coverage | likely an older figure; cavesim runs have since been executed with unknown opcodes raising (hypothesis; `tools/opcodes.py --gaps` gives the current gaps) |
| 14 | the earlier inventory said `tools/innoextract/` has no binary | `innoextract.exe` and `ie.zip` are present |

Unknown (point at the file that would answer): whether `tools/csr/dspdump.py`, `xuv2bin.py` and `tools/primesweep.py` family are still wanted (no doc or script cites them; the field log may, `docs/field-log.md`).

## 15. Additions 2026-10-12 (firmware study; offline-safe unless stated)

Appended at the end so that no cited line moved. Evidence and numbers: `docs/deep/firmware-study-2026-10-12/` (T03, T07, T08, T11, T12) and `docs/FACTS.md` section 9.

| Tool | Command and what it does | Reads / writes | Notes |
|---|---|---|---|
| `tools/seammodel.py` (new) | `python tools/seammodel.py {seam,table,align,ladder,sens,check} ...`: gap and splice at the chunk seam versus poll period P, lead L and rebuild latency c, tick-phase alignment of the payload length. `python tools/seammodel.py check` prints 15 PASS and "seammodel self-check: OK". | reads nothing; prints | MODEL only; c, L, a_busy are unmeasured (FACTS F221). Options of `seam`: `--P --L --size --rate --h --h1072 --s0 --a-busy --a-build --F --purge {always,never} --chunks` |
| `tools/cavesim.py` (changed) | New opt-in world flags: `--cancel {never,always}`, `--ksink-after-unload zero`, `--wrong-dsp MS:DUR` (rule W1), `--mid-chunk-1072 MS[:b]`, `--foreign-tone MS:DUR`, `--mem-at MS:ADDR=VAL`, `--voice-field` with `--short-id` and `--field-at MS:0|1`; a recorded `fn_1f47a` call that Panics like the firmware; a cave-carried trap stub (`SYNTHESISED TRAP STUB ... inline tail`) with FUNC_RET interception. All default falsy: legacy runs are byte-identical. | as before | FACTS F220. A stray 0x0E/0xE1 tail is reported as a HAZARD (not STOPPED); xapemu is untouched |
| `tools/cavesim_regress.py` (changed) | Second battery of 33 extension cases and a new `--record-new` mode that writes only goldens that are missing. Expected output: `169 cases: 169 identical` and `33 extension cases: 33 identical`. | goldens in `build/analysis/cavesim-golden/` | the 33 new goldens are in a git-ignored directory (`git add -f` if wanted). The command takes minutes and ignores `--help` (it runs the battery) |
| `tools/cavesim_selftest.py` (changed) | 23 original cases, then 52 extension cases (failure worlds, guard sweep over 16 ADK sinkState values, trap-stub gate cases). Expected: `23 cases, 0 failed` and `52 extension cases, 0 failed`. | - | the sweep does not cover Bose state values 16-22 (FACTS F194) |
| `tools/caveguard.py` (changed) | Adds `attest_trap_stubs`, `find_cave_stubs`, `stray_tail_ops`, `synth_stub_words`; prints `probeNNN: synthesised trap stubs: N` and `trap stubs: none, or every one canonical and declared`; FAILS (exit 1) on a non-canonical, undeclared, out-of-window, above-0xE2 or stray 0x0E/0xE1 tail. `tools/preflight.py` calls it and prints the same two lines per probe. | - | FACTS F167. Gate holes listed in T12 skeptic (`ld XH` not in BRANCH_OPS; near-copy tail) |
| `tools/brownnoise.py` (changed) | New options `--gen {integrator,fft}` (default integrator, byte-identical, sha `f832c4d6...` pinned by `--selftest`), `--lp`, `--shelf-db`, `--shelf-hz`, `--tilt`, `--crest-sigma K`, `--crest-iters`, `--rot-cands`, `--ref-table WAV` (octave table of a reference wav against ideal brown). The report now also prints the sha256 and a "vs ideal" octave line. Recommended recipe: `python tools/brownnoise.py --rate 8000 --bytes 60100 --gen fft --loop --peak 0.985 --seed 63`. | writes the payload and a decoded wav only where `--out` says | FACTS F202-F206. Supersedes the option list at 10.2 (which stays correct for the old options) |
| `build/payload/payload_study.py` (new) | `python build/payload/payload_study.py [--selftest] [--section analytic|generators|peaks|seeds|loop|variants|lengths|final|previews|all] [--seeds N]`: the numbers behind the T07 payload decision, with sha256 pins. | writes previews only with `--section previews` (to `build/payload/previews/`) | model output; scipy is not needed |
| `build/hook/assemble_probe181p.py`, `gate_probe181p.py` (new) | probe181 with POLL_MS 200; gate = 37 scenarios (about 9 minutes). | `--build` writes `probe181p_*` | NOT flashed |
| `build/hook/assemble_probe184a.py`, `assemble_probe184.py`, `narrow184_lib.py`, `gate_probe184.py` (new) | 184a = tiny valid ROFS, 184 = the T07 file; `assemble_probe184a.py` runs the 184 engine via runpy with its own docstring and press page; `narrow184_lib.py` stages any length and start period (byte-per-word replay); `gate_probe184.py probe184a|probe184` runs 24 / 21 world-model scenarios with an unpacked SourceMap patch and compares the p2 bytes written with the ROFS. | `--build` writes `probe184*_words.json`, `_cmd.txt` (a rebuild note, the edits exceed one command line) and `_brown.dfu` | NOT flashed; `make_narrow_payload.py` still stages only 30,000 B |
| `build/hook/assemble_probe187.py`, `gate_probe187.py` (new) | the read-only volume census; the assembler prints a READ-ONLY PROOF (86 instructions on a whitelist, 9 stores all into its own frame); the gate checks 4,567 census states, 22 scenario rows, 9 replay events and 23 world rows (34 s with the memoised instruction table). | `--build` writes `probe187_*` | NOT flashed |
| `tools/xapemu.py` (unchanged, two findings) | Line 20 imports xapvm from a hard-coded absolute path at module level (not only in the demo, correcting line 17 and 193 above); `VM.run()` rebuilds a roughly 215,000-entry instruction table on every call (about 0.12 s): bulk gates must memoise it. | - | owner: also the 0x0E pseudo-TRAP (lines 179-186) and dead branch (:248) per T12 |


## 16. Additions 2026-10-12, round 3 (offline-safe unless stated)

Appended at the end so that no cited line moved. Evidence: `docs/deep/round3-2026-10-12/` (R02, T14, V01, B01, B02, B03) and `docs/FACTS.md` section 10. The command lines below were read from each tool's `--help` or argparse on 2026-10-12. Run assemblers and gates from the repository root (`python build/hook/assemble_probeNNN.py`); run from `build/hook/` they cannot find `caveasm`.

| Tool | Command and what it does | Reads / writes | Notes |
|---|---|---|---|
| `tools/trapcat.py` (new) | `python tools/trapcat.py [--catalogue] [--forms] [--classes] [--checks] [--trap 0xD3] [--selftest]`: re-derives the trap catalogue from the stack image: 227 slots, the 20 real argument forms (form 0 is the fault entry), the 18 stream-object classes, and the pinned checks (210/7/10, 211/5/1/10, 217 distinct shims, banks 214/3). `--checks` prints "ALL OK"; `--selftest` asserts the pinned facts. | reads `firmware/bose/extracted/stack_*.bin` and `tools/bose-stubs.json`; prints | FACTS F238, F239; R02. The facts it prints are what `caveguard.UNIMPLEMENTED_TRAPS` encodes (not enforced by a test). |
| `tools/seammodel.py` (changed by T14, V01) | Subcommands now `{seam,table,align,ladder,sens,dscan,check}`. New: `dscan` (reading versus the chunk length D, `--d-ms-list`), `--reengage` and `--mixer-off` (the 7 ms mixer re-engagement of an empty port; `--reengage 0` reproduces the old tables), `--L-samples` on `table` (grid points of the lead L in samples, "grid points, not bounds"), a header that says D is assumed unless `--d-ms` is passed, longer horizons so a slow slide is not reported clean. | reads nothing; prints | MODEL only; D, h, s0, a_busy, L and the 7 ms are unmeasured (FACTS F284). Most `check` lines are identities of the code with its closed forms. |
| `tools/cavesim.py` (changed by T14) | New options: `--caller-frame K` (the hook caller is a function with `enterl -K`; static and runtime guard for stores into the caller frame, used by the consume-lever row), `--staged FILE` now models FIRST = 9 with one byte per element (28 of every 64 from element 18) and `--staged-legacy` keeps the word layout, world options `--src-unpacked`, `--src-cap N`, `--p2-capture FILE` (write the bytes the cave flushes to the p2 sink) and `--size-dries-after N`; a cave bsr/bra into the trap tail `0x291..0x295` prints a HAZARD and stops. Together they reproduce the 184a/184 gate scenario with no monkeypatch (the capture equals the padded ROFS). | as before | FACTS F280, F283; T14. Not modelled: a 0xD3 raw source, PEEK/POKE. |
| `tools/caveguard.py` / `tools/preflight.py` (changed by T14) | `attest_trap_stubs` now refuses a stub for any of the ten unimplemented slots and any bsr/bra into `0x291..0x295` (`tail_branches`); `caveguard probeNNN ...` now checks every probe named (it used to stop at the first failure) and prints a MANUAL GATE line: stack headroom for an image with a synthesised stub is a manual gate. Preflight step 4 classifies each differing byte (cave / redirect / data_us slack / staged cells / UNEXPLAINED = FAIL). | - | `python tools/caveguard.py` has no `--help` (a bare flag is read as a probe name). |
| `tools/cavesim_regress.py`, `tools/cavesim_selftest.py` (changed by T14) | Expected output now: `169 cases: 169 identical` and `45 extension cases: 45 identical`; `23 cases, 0 failed` and `96 extension cases, 0 failed`. | goldens in `build/analysis/cavesim-golden/` | the 45 `ext_*.txt` goldens (and `ext_synth_stray.round2.txt`) are in a git-ignored directory; whether to `git add -f` them is an owner question (`docs/CLEANUP-LOG.md`). |
| `tools/caveasm.py`, `tools/xapemu.py`, `tools/xapvm/xapvm.py` (changed by T14) | `caveasm.synth_stub_words`, `COMMON_TAIL`, `needs_follow` (a shared helper; the assemblers still carry their own); `xapemu` imports xapvm by a relative path and no longer models opcodes `0x0E` / `0xE1` as a pseudo-TRAP; `xapvm` prints mnemonics for them. | - | `build/analysis/*-disasm.txt` still show the old mnemonics until regenerated. |
| `build/payload/make_narrow_payload.py` (changed by B02) | `python build/payload/make_narrow_payload.py [--bytes N] [--adpcm FILE] [--gen G] [--seed S] [--expect-sha SHA] [--peak P] [--regenerate] [--name NAME] [--start-period N] [--out FILE] [--scratch DIR] [--no-dry-run] [--no-world] [--no-edits-module]`; the default (30,000 B) output is byte-identical to before. The T07 recipes are `--bytes 60100` and `--bytes 90004`. | writes under `build/payload/` | the built 184/184a images never used the old 30,000 B stage_plan (they stage through `narrow184_lib.py`). |
| `build/hook/narrow184_lib.py` (changed by B02, T14) | Adds `first_clean_start`, `data_us_exposure` and `header_a_hits` (how many region-A header words, E6-array words and region-B-tail words a staged span rewrites); `python build/hook/narrow184_lib.py` prints the exposure table. | reads the official data_us | FACTS F293; V03. The assemblers' id gates only warn on header hits. |
| `build/hook/assemble_probe181q100.py`, `assemble_probe181q50.py`, `gate_probe181q.py` (new, B03) | 181p with POLL_MS 100 / 50 (one immediate; 172 words). `python build/hook/gate_probe181q.py [-j J] [--only TEXT] [--list] {probe181p,probe181q100,probe181q50}` runs 37 / 39 / 40 scenarios in parallel (minutes each at -j 6; not a rerun of `gate_probe181p.py`). | `--build` on the assemblers writes `probe181q*_words.json`, `_cmd.txt`, `_brown.dfu` | NOT flashed; builder-checked only (FACTS F289). |
| `build/hook/assemble_probe188.py`, `assemble_probe189.py`, `gate_probe188.py` (new, B01) | PBd (180 words) and PB (165 words; the assembler asserts it equals PBd outside the tail). `python build/hook/gate_probe188.py [probe188\|probe189] [--part I/N] [--group A,B] [--words FILE] [--workers N] [--list]` runs 80 world-model scenarios (6 workers by default; it ignores `--help` and starts the default run). | `--build` writes `probe188_*`, `probe189_*` | NOT flashed; builder-checked only (FACTS F286, F287). fsedit/dfubuild flakes about one build in four on identical input; rerun gives a byte-identical image (F285). |
| `build/hook/assemble_probe184_58k.py`, `assemble_probe184a_58k.py`, `assemble_probe184_90k.py` (new, B02) | Thin wrappers that run `assemble_probe184.py` / `assemble_probe184a.py` with the 58,700 B payload at start 1,320 or the 90,004 B payload at start 202. `gate_probe184.py probe184a\|probe184\|probe184a_58k\|probe184_58k\|probe184_90k` (it ignores `--help`) now also cross-checks with `cavesim --src-unpacked --p2-capture`. | `--build` writes `probe184*_58k_*` / `probe184_90k_*` | NOT flashed; the 184 family cannot succeed as designed (R02, FACTS F235). |
| `tools/fsedit.py` (unchanged, finding) | It uses the fixed work directory `build/fsedit/probe.fs`: two builds at once collide ("dfubuild produced no fs area" or "final digest mismatch") and write no DFU. Build one image at a time; a per-process work dir is a tool-owner request. | - | FACTS F285; B02. |

- `tools/install_from_stock.py [--dry-run]` -- written 2026-10-18 for the two-image install (writer probe208, one centre press, product probe279) through flash_probe.py; dry-run only at the time. Superseded by the 2026-10-28 single-flash default below.


## 13. Additions 2026-10-28

- `tools/measure/` (new): the hands-free measurement kit: `voltest.py` (record the microphone while sending timed console commands), `rms.py`, `wav_spec.py`, `glitch.py`, `slots3.py` (decode a spoken census word with a check digit), `gen_model.py` and `gen_tune.py` (model and tuning of the DSP generator). See `tools/measure/README.md`.
- `build/dsp/compact.py` (new): rewrites the five two-word absolute branches of the linked DSP generator as the stock one-word relative forms and writes `build/dsp/noisegen.bin`. The assembly chain is `kas` (`adk/root/tools/bin`, flags `-DGORDON -DKAL_ARCH3 -DKALASM3 -g -mchip=gordon`), `klink` with `build/dsp/gen.link`, `kobjcopy -O binary`, then `compact.py`. See `docs/dsp-generator-route.md`.
- `tools/csr/virtual_press.py`: the `peek <0-7>` subcommand sends a SAFE census event (never 0x4021/0x4022; see `docs/dsp-generator-route.md` section 7); the census builds (probes 361-377) map event ids to DSP cells in `build/hook/ladder_ext.py` (PCIDS).
- `tools/install_from_stock.py [probe380]` (now also the bare, no-argument default): the one-flash install of the lean product (no writer). The older two-image mode (writer + product) now needs an explicit `--two-image` flag; see `docs/ring-buffer-fix.md`.
- `tools/caveguard.py`: `CODE_REGION_AY` now holds AY batches A-D (23 functions); `AY_BATCHES` has 'A', 'B', 'C', 'D', 'AB', 'CD', 'ABCD'.
- Manual stock reflash (not scripted): the sequence of `docs/FLASH-PROTOCOL.md` with `firmware/bose/minnow_3.0.3/Minnow_3.0.3_stack_plus_app.dfu`, then `tools/csr/dfu_upload.py` and a comparison of the filesystem area (0 of 975,168 bytes must differ).
