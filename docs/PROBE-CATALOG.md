# Probe catalogue (per-probe rows for 1-181; section 13 covers 182-381 by era, more coarsely)

Purpose: one row per probe and per experiment image, so a reader can find what any probe changed, what it asked, what the owner heard, and where the evidence lives.
Status / last verified: 2026-10-10. Rows were written from the field-log digests (timeline-A/B/C) and the file map, then re-checked against the primary text of docs/field-log.md, the probe run logs in firmware/bose/probe/ and the assembler docstrings in build/hook/. Section 10 lists the rows that were re-checked and the mismatches that were fixed. Round 3 (2026-10-12): section 12 at the end adds probes 181q100, 181q50, 188, 189, 184_58k, 184a_58k and 184_90k (built offline, NOT flashed) and the verifier verdicts on the section 11 images (12.1); the rows of 181p, 184a, 184 and 187 carry a bracketed round-3 note.
Read next: docs/RESUME-HERE.md (banner = current state), docs/RETURN-CHECKLIST.md (first day back), docs/deep/offline-2026-10-10/README.md (probes 179-186), docs/FLASH-PROTOCOL.md (before any flash).

> **This is an archival index from the original (larger, private) project repository**, kept here for provenance and detail. Many of its internal links (`docs/RESUME-HERE.md`, `docs/RETURN-CHECKLIST.md`, `docs/field-log.md`, `firmware/bose/probe/`, and others) point at files that are not included in this public export. `docs/CURRENT-STATE.md`, `docs/dsp-generator-route.md`, and `docs/ring-buffer-fix.md` are this export's own current, self-contained write-ups and are not affected.

Scope. This file is an index, not the evidence. The evidence is docs/field-log.md (append-only, owner words verbatim), the readbacks and DFUs in build/hook/, and the run logs in firmware/bose/probe/. When this file and the field log disagree, the field log wins and the later entry wins over the earlier one. What is on the speaker right now is whatever build/hook/FLASHED says (2026-10-10: probe178 on unit 2).

## 1. How to read this catalogue

### 1.1 Columns

| Column | Meaning |
|---|---|
| probe | Probe number as the project names it. A letter suffix is a variant of the same number (11b, 11c, 15b, 18a..c, 161s). Rows without a number are named experiments. |
| date / unit | Date in 2026 (MM-DD) and which speaker it ran on: u1 = unit 1 (lost 2026-10-04 20:23), u2 = unit 2 (from 2026-10-04). From probe139 the log numbers each unit-2 flash ("#14"); earlier unit-2 flashes are not numbered. |
| what it changed | The one-line delta from the previous image or from stock. "cave" = the code at word address 0x3E21D in the vm.app constant window; "hook" = the redirect that calls it. |
| question | What the probe was built to find out. |
| press result | The owner's report, shortened, in quotes when verbatim. "Spoken id" outcomes (for example "lost", "connected to") are the probes' own diagnostics: the cave makes the stock voice-prompt engine say a known phrase; see docs/request-id-catalog.md. |
| verdict | One of the five words defined in 1.2, with a short qualifier when needed. |
| key lesson | What the project learned. Confidence marks: proven = quoted press, readback, address or command output; well-supported = disassembly, ADK source or simulation, never pressed; hypothesis = stated as such. Negatives are results. |
| log | Line number in docs/field-log.md of the entry heading (L123) and, after a slash or comma, the result entry. Probes 1-21 and 138 have no field-log entry; the source is named instead. |
| artefacts | Which files exist; see 1.3. |

### 1.2 Verdict words

| Verdict | Meaning |
|---|---|
| PROVEN-POSITIVE | The probe showed what it was built to show, and a press, readback or command output proves it. |
| NEGATIVE | The probe ran and showed the idea fails or crashes. A negative is a result and often fixed a later design. |
| INCONCLUSIVE | It ran, but the result was ambiguous, confounded, or answered a different question. |
| RETIRED | Superseded before a useful press, pulled, flashed but never pressed, or made void by a later correction (the "void" cases say so). |
| NOT-FLASHED | Built or designed, never put on a speaker. |

### 1.3 Artefact notation (paths are relative to the repository root)

| Token | File |
|---|---|
| asm | build/hook/assemble_probeNN.py. The docstring is the best design note for the probe, and sometimes carries the press result. |
| words | build/hook/probeNN_words.json, the cave words as built. |
| cmd | build/hook/probeNN_cmd.txt, the fsedit command line that builds the image. |
| dfu | build/hook/probeNN_brown.dfu, the built image. `dfu:name` = a differently named image in build/hook/ (probes 23-54 use descriptive names). |
| rb | the hardware readback of what was flashed: build/hook/probeNN_readback.dfu or readback_probeNN.bin. `rb:name` = another readback name (unit-2 or re-press readbacks). These files hold Bluetooth link keys and serials: list them, never open them. |
| log | build/hook/probeNN_flash.log, the flash transcript written by tools/flash_probe.py (probe161 onward). |
| verify, gate, smoke | per-probe check scripts in build/hook/ (verify_probeNN.py, gate_probeNN.py, smoke_probeNN.py). |
| snap | a copy of the DFU, words and hash in build/hook/snapshots/ (probes 134-137), taken BEFORE the flash (L9359); a snapshot is not proof of a flash. |
| Q:name | the image is quarantined in RADIOACTIVE_DO_NOT_FLASH/build_hook/ (probes 10-22). |
| fw:name | file under firmware/bose/probe/ (probes 1-9 have no build/hook files). |
| pre-image | build/hook/pre_probeNN.bin, a readback taken before the flash. |

### 1.4 Cautions

- The absence of a readback file does not prove a probe was not flashed. Readbacks were skipped on 2026-10-02 to 2026-10-04 (probes 103-127), which is part of how unit 1 was lost; see docs/POST-MORTEM-2026-10-04.md.
- The presence of a DFU does not prove it was flashed. Use the field-log entry heading ("flashed" / "BUILT, NOT FLASHED").
- "Centre button" error: probes 10-24 were pressed on the centre button, but the hook at 0xAE0 only runs on a Bluetooth-button hold (event 0x4003). Every result of probes 10-24 is void for the cave question (field log L453, retraction). Results of probes 10-21 were never entered in the field log at all (the log starts at probe22); what is known of them comes from the run logs in firmware/bose/probe/ and from assembler docstrings, which the project itself marks as an unverified narrative.
- Trap numbers before 2026-09-30 are wrong: the speaker's vm.app is BlueLab 7.3 and 173 of 257 trap names differ from the numbers first used (field log L2161, docs/trap-numbering.md). Probes 46, 47 and 52-56 called other traps than their names say.
- Before 2026-10-05 any multi-word branch target quoted from the project's disassembler is one word short (L8974); and "262 writable cave words" is wrong, the proven window is 197 words (L8196).
- Press counts are small (often n = 1 or 2). "Ear-timed" durations are estimates.

### 1.5 How to zero in on one probe

1. Find the row here; note the log line.
2. `sed -n 'START,+70p' docs/field-log.md` shows the entry (setup first, owner words and analysis after). Later corrections to the same probe may sit further down: `grep -n "probeNN" docs/field-log.md`.
3. Read the docstring at the top of build/hook/assemble_probeNN.py for the design and the outcome table written before the press.
4. For the cave bytes, read build/hook/probeNN_words.json; for the image identity, hash the dfu and compare with RADIOACTIVE_DO_NOT_FLASH/MANIFEST.sha256 or build/hook/FLASHED (current only).
5. For topic questions (heap, hooks, ADPCM, frames) use the topic docs named in "Read next" of docs/PROJECT-LAYOUT.md rather than reading the probes in order.

### 1.6 Find probes by topic

| Topic | Probes (see the rows) | Topic doc |
|---|---|---|
| DFU signature, which areas are writable | 1-9, A1, B1 | docs/dfu-signature-scheme.md |
| Finding the hook; Bluetooth hold versus centre button | 10-29, 110-127, 172 | docs/hook-sites.md, docs/centre-button-hook.md, docs/deep/hook-gates.md, docs/deep/centre-long-press.md |
| Choosing the voice prompt (the id lever) and the 64-id catalogue | 31-38 | docs/request-id-catalog.md |
| Trap ABI and trap numbering | 40-47, 59-66 | docs/trap-abi.md, docs/trap-numbering.md |
| Cave frame rules, crashes of 68-80 | 68-81 | docs/cave-frame.md |
| Cave size and window | 130 (and the audit at L8241) | docs/cave-budget.md |
| First sustained tone | 74-77 | docs/bose-audio-path.md |
| Owning the DSP or the codec, the wedges | 85-97, 158-171 | docs/dsp-noise-route.md, docs/deep/dsp-output-wiring.md |
| Timers and message tasks | 98-100, 145-153 | docs/message-task-abi.md |
| ADPCM generation, loudness | 104-106, 128-134 | docs/deep/offline-2026-10-10/adpcm-format.md |
| Heap and memory | 61, 82, 103, 122, 136, 137 | docs/cave-heap.md |
| Partition 2 and file sources | 138-144, 154, 155 | docs/partition-route.md |
| The pairing teardown (why 7 s) | 157 (and 104-155) | docs/deep/hook-gates.md (addendum), docs/dsp-noise-route.md (update 2026-10-08) |
| Centre long press, chunk per press, level | 172-181 | docs/deep/offline-2026-10-10/README.md, DESIGN.md |
| Safety incidents and recovery | 91, 96, 97, 127, 130, 141, 158, 162, 173-175 | docs/FLASH-PROTOCOL.md, docs/POST-MORTEM-2026-10-04.md |

## 2. The eras

| Era | Probes | Dates (2026) | Unit | What it was about | How it ended |
|---|---|---|---|---|---|
| E0 USB-DFU signature probes | 1-9 (+A1, A1r, B1) | 09-24 to 09-27 | u1 | Which DFU areas the loader checks (stack, PS, signed fs). | Unsigned PS keys are writable; the signed fs is writable in blind windows with a digest collision (probe8, probe9). |
| E1 First hooks, wrong button | 10-24 | 09-27 to 09-29 | u1 | Splice code into vm.app, find a hook, make noise. | All pressed on the centre button; results void (L453). |
| E2 The right button and the id lever | 25-38 | 09-29 | u1 | Find the live hook; make our code choose the voice prompt. | Hook at 0xAE0 = Bluetooth hold; first working cave (29); lever complete (37); 64-id catalogue. |
| E3 Injection on wrong trap numbers; speech lever | 39-58 | 09-29 to 09-30 | u1 | Reach the DAC or a Kalimba port from the cave; edit phrase payloads. | Trap numbers found wrong (L2161); "route closed" withdrawn; speech route closed by owner decision. |
| E4 Correct traps, bisect, frame bug | 59-81 | 09-30 to 10-01 | u1 | One trap call per flash; a generator that crashed. | Port 3 reachable; tone sustained (77); seven crashes explained by cave frame slots 6/7 (80, 81). |
| E5 Own the DSP / codec route, wedge | 82-97 | 10-01 | u1 | Run without music; drive the DAC from the cave. | Cave can load a .kap (85); owning the DAC with data flowing wedges the VM (96, 97). |
| E6 Timers and ADPCM discovered | 98-106 | 10-01 to 10-02 | u1 | Firmware owns the DSP; the cave only feeds port 3 on a timer. | ADPCM transform over a region source carries audio (104); refill loops crash (105, 106). |
| E7 Hook search, heap wall, unit 1 lost | 107-127 | 10-02 to 10-04 | u1 | A hook that fires standalone; a leak-free refill; more memory. | No better hook found; malloc above 138 words refused; probe127 wedged unit 1 for good. |
| E8 Unit 2: generated noise and the gates | 128-137 | 10-04 to 10-05 | u2 | First generated audio; make it loud; branch bug. | probe134 "louder noise"; window and displacement rules found; heap route closed (137). |
| E9 Partition route and refill loops | 138-158 | 10-05 to 10-07 | u2 | A mountable .kap in partition 2; a timer-driven refill loop. | Partition write works but the mount refuses; every loop dies at 6-9 s (pairing teardown, 157). |
| E10 DSP reload and wedge bisect | 159-171 | 10-08 | u2 | Reload the DSP ourselves and drive it. | Reload and config are clean; the second chunk stays inaudible; line parked. |
| E11 Centre long press, chunk, level | 172-178 | 10-08 to 10-10 | u2 | Pivot to the centre-long-press hook; one chunk per press. | Sustain past 7 s (174); start-only cycle works press after press (177); level knob is ours (178). |
| E12 Offline | 179-181 built; 182-186 designed | 10-10 | none | Poll loop, STOP, rate; payload and ROFS. | Built and simulated, NOT flashed. |

## 3. The 15 most important probes

1. **probe8 (09-27, u1).** The first modified signed filesystem was accepted and booted: 16 one-bit flips in data_us blind windows plus a GF(2) digest collision, and the readback shows the flips. It opened the only software route: bytes 34..62 of every 64-byte block are writable, and tools/fsedit.py then wrote arbitrary content (probe9).
2. **probe27 (09-29, u1).** Suppressing the one request at 0xAE3 removed "ready to connect another device": id 0x35 is that prompt and the 0xAE0/0xAE3 block runs on a Bluetooth-button hold (event 0x4003), not a voice-assistant hold. It voided probes 10-24, which had all been pressed on the wrong (centre) button (L394, L436, L453).
3. **probe29 (09-29, u1).** The first working cave: `enterl -3; bsr 0xe06d; leavel -3` at 0x3E21D runs on a Bluetooth long press and returns cleanly, so hook, cave and return mechanism are sound. probe28's crash was therefore in its payload, and "the cave executes" was proven by that crash (L541, L600).
4. **probe37 (09-29, u1).** The lever is complete: the cave leaves `bra +1` at 0xAE3, sets the prompt id in AL after the back-call, and the stock code issues the request. Our code now chooses what the loud, volume-controlled engine says, touching no RAM below 0x80 (L1091).
5. **probe59 (09-30, u1).** After the trap table was found to be BlueLab 7.3, `StreamAudioSink(CODEC,0,2)` at stub 0x162 was the first trap call that did real work from a cave ("Voice prompts on"). It confirmed the corrected numbering and the three-argument ABI on hardware and started the single-call bisect (L2487).
6. **probe77 (09-30, u1; confirmed 10-01, 10-04 on u1 and u2).** With the prompt call at 0xAE4 deleted, a ringtone connected to Kalimba port 3 gave "a LONG TONE": the prompt engine's KalimbaLoad of NowSpeakTTS had been evicting the tone. It is the known-good control: it has passed three times on two units with a phone connected and music paused (L3669, L5318, L7724).
7. **probe81 (10-01, u1).** `enterl -16` instead of `enterl -8` made the lifted brown-noise generator work on the speaker (first sample 0xFE27 bit-exact). The cave frame rule (slots k-2 and k-1 hold the saved return address) explains seven earlier crashes (68, 69, 72, 73, 78, 79, 80) (L3943, L4007).
8. **probe97 (10-01, u1; with probe96).** A source on the tone port without any 0x7000 start message wedged the VM exactly as probe96's start message did. The fatal act is taking the DAC from Bose's audio manager while data flows, which kills the "own the DSP" architecture. Holding POWER + VOICE ASSISTANT recovered that wedge, but it did not recover the 2026-10-08 wedge (L11821), so the standing recovery order in docs/FLASH-PROTOCOL.md applies (L4989, L5030, L4956).
9. **probe104 (10-01/02, u1).** `TransformStart(TransformAdpcmDecode(StreamRegionSource(ptr,len), StreamKalimbaSink(3)))` over const words carried audio ("maybe .25 second burst of static"). It is Bose's own voice-prompt recipe and the foundation of every generator since (L5533, L5546).
10. **probe127 (10-04, u1).** A hook three frames deep with `enterl -16` wedged the speaker at power-on and unit 1 never enumerated on USB again. Eleven flashes and nine presses in 92 minutes with zero readbacks led to docs/FLASH-PROTOCOL.md; the single cause remains unestablished (L7537, L8286).
11. **probe130 (10-04, u2).** A 234-word cave, 55 words outside the proven window, crashed on boot ("battery one hundr.." then reboot). The first account (L8153) blamed zero words inside live const tables, but L8500 excluded that by controls (probes 117/118 corrupted the same words without crashing); the cause is unnamed (frame depth is the leading candidate, unproven). The proven cave is 197 words in 0x3E200..0x3E400, enforced by tools/caveguard.py as policy (L8153, L8500).
12. **probe134 (10-05, u2).** Nibble signs arranged so each 3-byte ADPCM block nets zero gave "louder noise" (in-band -41.9 to -9.3 dBFS). It is the first loud generated audio and the generator every later probe reuses; it still lasted only 126 ms (L9373).
13. **probe157 (10-07, u2).** "7 seconds of noise and then 'bluetooth off'": the DSP is gone about 7 s after a press on the 0xAE0 hook because the pairing teardown (fn_0d500, 0x00ac2) runs first. This explains why five unrelated designs (probes 104-171) all died at 6-9 s (L11554, L11670).
14. **probe172 (10-08, u2).** Hooking the centre long press at 0x00e46 (event 0x4004) spoke the stock prompt and nothing else: the trigger works, the event is swallowed, no pairing is entered and the stock DSP stays up. It removed the 7 s cut-off (L12923).
15. **probe177 (10-09, u2; with 174 and 178).** One chunk of the narrow file tts/rphrases_us through port 3 plays loud and ends by itself, press after press with music playing. probe174 had shown sustain past 7 s, and probe178 (on the speaker now) showed the level knob is ours: 0x1072 word b = 2 is "Quieter on Both" (L13315, L13394).

Also worth knowing: probe91 (first wedge, L4513), probe141 (device harm, L10119), probes 131-133 (branch displacement root cause, L8974), probes 173-175 (runaway and teardown crash, L13002, L13177), probe135/136/137 (heap wall, L9405).

## 4. The catalogue

Dates are 2026. All rows are unit 1 until probe127. Column order: probe | date, unit | what it changed | question | press result | verdict | key lesson | log | artefacts.

### 4.0 Era E0: USB-DFU signature probes 1-9 (no cave, no hook)

These probes have no files in build/hook/. Images and write-ups are in firmware/bose/probe/ (`fw:`), run transcripts are probe1_run.log and probe_run2..10 in the same folder, and the mechanism is explained in docs/dfu-signature-scheme.md. Result matrix: probe_run2_2026-09-26.log and probe_run4_2026-09-26.log.

| probe | date, unit | what it changed | question | press result | verdict | key lesson | log | artefacts |
|---|---|---|---|---|---|---|---|---|
| probe1 | 09-24 u1 | Stack const words 0x40..0x43 FFFF FFFF FFFF FFFF -> FFFE 0000 0000 FFFE (14 bytes); stack and file CRCs fixed (tools/make_stack_probe.py) | Is the unsigned stack area checked only by CRC? | No press (download only): errFILE after the 45.9 s manifest wait. Official 3.0.3 re-downloaded, leave-dfu restored Main 3.0.3.6546. | NEGATIVE | A CRC-valid stack patch is rejected by the loader; the check and its reference are unknown. Say "rejected once, cause unknown", not "USB route closed" (proven; memory note csr8670-unsigned-stack-area). Recovery by official reflash proven. | none (pre-log); firmware/bose/probe/probe1_run.log:6-15 | fw:Minnow_3.0.3_stack_probe1.dfu fw:Minnow_3.0.3_stack_probe1.txt fw:probe1_run.log |
| probe2 | 09-26 u1 | Two bit flips in fs dword padding (fs offsets 0x4b032, 0x6c07a); body XOR kept 0; RSA signature stale | Is the fs signature enforced over padding? | errVERIFY after the manifest wait; the device drifted to errFIRMWARE; official restore proven, readback = baseline. | NEGATIVE | The loader programs the image first and fails at the verify stage, so a rejected download can write flash; recoverable by an official reflash (proven, three times that day). | none; probe_run2_2026-09-26.log | fw:probe2_fs_pad.dfu fw:probe2_fs_pad.txt |
| probe3 | 09-26 u1 | One data byte in /tts/rphrases_us (fs offset 0x6d108, 0x91 -> 0x6e), fs repacked with csrfspack, XOR 0, signature stale | Do file-data edits behave like padding edits? | errVERIFY, same shape as probe2 | NEGATIVE | Padding and file data behave alike; the fsr_dfu1 signature is enforced at the verify stage over the whole body (proven). | none; probe_run2_2026-09-26.log | fw:probe3_fs_xorfix.dfu fw:probe3_fs_xorfix.txt |
| probe4 | 09-26 u1 | Official image plus one inert key 0x2290 (value 0000) in the unsigned ps[0] area (16 bytes vs 8), CRC fixed | Can PS keys be injected over USB? | ACCEPTED, manifest clean, booted normally; the PS store grew from 82 to 83 keys. | PROVEN-POSITIVE | Unsigned PS key injection works end to end (proven by readback). | none; probe_run2_2026-09-26.log | fw:probe4_ps_unsigned.dfu fw:probe4_ps_unsigned.txt |
| probe5 | 09-26 u1 | ps[0] delete record (action 0) for key 0x2290 | Clean-up that doubles as a delete test | ACCEPTED; readback identical to the session baseline | PROVEN-POSITIVE | Delete records work (proven). | none; probe_run2_2026-09-26.log | fw:probe5_ps_delete.dfu |
| A1 | 09-26 u1 | Keys 0x007d (USB bcdDevice, also in the signed sps) = 0x0002 and 0x225b (hardware serial, not in sps/aps) = "ZZZZ..." via ps[0] | Do unsigned keys override keys the signed stack-PS also carries? | ACCEPTED. Key 0x225b took (bose-dfu info printed it); 0x007d did not take. | PROVEN-POSITIVE (partial) | The signed stack-PS is applied after ps[0] and silently overwrites shared keys; the unsigned channel controls only identity, pairing and state keys (proven). | none; probe_run3_2026-09-26.log | fw:A1_ps_precedence.dfu |
| A1r | 09-26 u1 | Restore of the original serial through ps[0] (original words kept in private/original_serial_225b.bin) | Undo A1 | ACCEPTED; readback identical to baseline | PROVEN-POSITIVE | Injected keys can be restored (proven). | none; probe_run3_2026-09-26.log | fw:A1_restore_serial.dfu |
| B1 | 09-26 u1 | Cross-version stack splice (stack of 2.6.0 on 3.0.3) | Does the errFILE check depend on the stack version? | Offline only, never downloaded (the run log says "no download needed"). | NOT-FLASHED | Stacks of 1.0.6, 2.6.0 and 3.0.3 are byte-identical, so a cross-version swap tests nothing; only a cross-product splice could, and it was not run (needs an owner decision). | none; probe_run3_2026-09-26.log | fw:B1_stack_260_on_303.dfu |
| probe6 | 09-26 u1 | One byte inside sps key 0x02c2 (product string "Bose" -> "Rose"), sps CRC-32 fixed | Are the official PS areas (sps/aps) checked only by CRC? | errFILE at the manifest stage, nothing programmed; official restore OK. | NEGATIVE | sps/aps are cross-checked at the manifest stage with the same mechanism as the stack (proven); mechanism unknown. Only two doors left: unsigned ps[0] and the fs digest. | none; probe_run4_2026-09-26.log | fw:probe6_ps_name.dfu fw:probe6_ps_name.txt |
| probe7 | unknown u1 | Image named fs_blind (blind-window fs edit) | unknown | Not in any run log, README or field log; result unknown. | INCONCLUSIVE | Unknown. probe_run5 (09-27) opens with probe8 as the first accepted blind-window edit. Extracted partitions are in build/probe7/. | none | fw:probe7_fs_blind.dfu |
| probe8 | 09-27 u1 | 16 one-bit flips in data_us blind windows (bytes 34..62 of 64-byte blocks) plus a GF(2) digest-collision set; Bose signature untouched | Is a blind-window edit accepted when the digest is made to collide? | ACCEPTED, manifest clean, booted normally; readback shows all 16 flips. | PROVEN-POSITIVE | Every loader check can be satisfied by a modified fs: about 30 of every 64 body bytes are writable if XOR parity and the digest are compensated (proven). | none; probe_run5_2026-09-27.log; docs/dfu-signature-scheme.md addendum 5 | fw:probe8_fs_digestcollide.dfu fw:probe8_fs_digestcollide.txt |
| probe9 | 09-27 u1 | 18 chosen ASCII bytes ("ZCODE-OPEN-FW-2026") in data_us at body 0x2001e plus 7 XOR-balance and 18 digest flips (43 bytes) via tools/fsedit.py | Can arbitrary chosen content be written? | ACCEPTED, booted, readback byte-identical to the built image. | PROVEN-POSITIVE | tools/fsedit.py writes any bytes into blind windows (proven). dfubuild silently drops a body whose XOR is not 0. The compensation flips landed in data_us (the TTS database) and silently killed voice prompts, noticed only at probe11 (well-supported: diagnosed in probe_run9; relocating the flips to the data_us tail in probe11b restored prompts). | none; probe_run6_2026-09-27.log | fw:probe9_demo_marker.dfu fw:probe9_demo_marker.txt |

### 4.1 Era E1: first hooks, all pressed on the wrong button (probes 10-24)

Unit 1. Only the run logs in firmware/bose/probe/ (probe_run7..10) and the assembler docstrings describe probes 10-21; none has a field-log entry. Dates marked (built) are the file times of the quarantined DFUs in RADIOACTIVE_DO_NOT_FLASH/build_hook/; the flash dates of probes 12-21 are not recorded anywhere I found. The project itself rates their field results as an unverified narrative (opus_task/CONSULT3_DATA_FOR_OPUS.md line 58, CONSULT4_TASK.md line 252). Probes 22-24 are the first field-log entries (L25 onward).

| probe | date, unit | what it changed | question | press result | verdict | key lesson | log | artefacts |
|---|---|---|---|---|---|---|---|---|
| probe10 | 09-27 u1 | Hook 0xae0: `bsr 0xe06d` -> `bsr 0x3e21d`; 11-word cave (`ld AL,#0; bsr 0x4946` beep; `ld X,#0xae3; rts`); 34 bytes diff | Does our code execute inside Bose's vm.app? | ACCEPTED, booted, readback fs byte-identical. No press result recorded (owner unattended at flash time). | INCONCLUSIVE | First custom code on the speaker (proven: accepted and booted). The X=0xae3 exit was a no-op because rts pops the internal return stack (docstring of probe16, unverified). | none; probe_run7_2026-09-27.log | rb:post_probe10.bin pre-image Q:probe10_va_hook.dfu |
| probe10clone | 09-28 (built) u1 | Rebuild of the probe10 hook on later tooling; the assembler file carries probe17's docstring (header mismatch) | Probably a control for the stock chirp flow ("probe10-clone-proven", docstring of probe20; hypothesis) | None recorded | RETIRED | Purpose not documented. | none | asm words cmd Q:probe10clone.dfu |
| probe11 | 09-27 u1 | 87-word cave: toggle RAM flag 0x808, beep via 0x4946, 16 random ringtone notes at RAM 0x810 (StreamRingtoneSource, StreamConfigure 0x30b, StreamSinkFromSource); 160 bytes diff | Do RAM note arrays play; is the toggle stable? | Owner (probe_run9): long press = LED flash only; no beep, no rumble, voice prompts dead, pairing invisible to the phone. Speaker reverted to stock. | NEGATIVE | Two build defects: the 0xae0 redirect was left out of the edit list (cave orphaned), and the compensation flips in data_us corrupted the TTS prompt database, which killed prompts and, most likely, pairing (symptom proven; mechanism well-supported). Affects probes 8-11. | none; probe_run8_2026-09-27.log, probe_run9_2026-09-27.log | asm words rb:post_probe11.bin pre-image Q:probe11_rumble.dfu |
| probe11b | 09-27 u1 | probe11 with the redirect included and compensation moved to the data_us tail | Do prompts and pairing survive? | Owner confirmed prompts, pairing and Bluetooth working (probe_run10). | INCONCLUSIVE | Tail flips at 0x359D2..0x35B22 are empirically safe. The run log's "slack" measurement was a hex slip: data_us really ends at 0x35B44. | none; probe_run10_2026-09-28.log | rb:post_probe11b.bin pre-image Q:probe11b_rumble.dfu |
| probe11c | 09-28 u1 | Cave v3: toggle bit 11 of global 0x56b; 0x4946 beep, its return value as feed sink; SinkClaim/SinkMap/write 15 low notes/SinkFlush; `bra` at 0xae3 to 0xaed to skip the Siri call; 160 bytes diff | Does the feed sink accept note words, and can the Siri call be skipped? | Owner (centre button): prompts speak, pairing OK, LED flashes, "SIRI STILL FIRES", press 1 beep, press 2 none, alternating. | RETIRED (void: wrong button) | The run log's reading (feed-sink route dead, 0x4003 downstream of the real event) was built on wrong-button presses and the field log voids the "Siri still fires" claim (L453). The alternation is the stock session toggle. | L453 (retraction); probe_run10_2026-09-28.log | asm words rb:post_probe11c.bin pre-image Q:probe11c_dbg.dfu Q:probe11c_rumble.dfu |
| probe12 | 09-27 (draft built), 09-28 (run log) u1 | Feed-sink cave: SinkMap, SinkClaim(128), 32 rumble notes, SinkFlush(64); 69 words | Does the feed sink returned by 0x4946 play notes? | Never flashed at the time: self-verification showed three bsr targets encode wrong (MAP, CLAIM, TONE). | NOT-FLASHED | Do not flash until every bsr target in the BUILT file is decoded and compared with the intent (later formalised as decode-verify). A "v2, fixed" assembler exists; whether it was flashed is unknown. | none; probe_run10_2026-09-28.log | asm words cmd smoke Q:probe12_rumble.dfu |
| probe13 | 09-27 (built) u1 | "Engine v3": press-hold toggles an indefinite low-noise mode; MessageSendLater timer carries the feed sink in the message, MessageCancelFirst on the second press | Self-timed sustain on the feed sink | No verified result. docs/bose-firmware-anatomy.md says the VOLUME/TIMBRE control words changed nothing audibly, which comes from the unverified narrative. | RETIRED (unverified) | The timer-in-message idea reappears in probes 98-100; flashed status unverifiable. | none | asm words cmd smoke Q:probe13_engine.dfu |
| probe14 | 09-28 (built) u1 | PCM loudness probe: write a +-16000 square burst into "StreamAudioSink" (really stub 0x16A = StreamScoSink) with a timer; 64-word claim | Is the raw codec PCM path loud? | "Silent" (unverified narrative) | RETIRED (void) | It never opened the DAC: 0x16A is StreamScoSink on BlueLab 7.3. The conclusion "the DSP owns the codec, all audio must go through the engine" was withdrawn 2026-09-30 (docs/bose-firmware-anatomy.md section 6; well-supported). | L1968 (cross-reference) | asm words cmd Q:probe14_pcm.dfu |
| probe15 | 09-28 (built) u1 | Catalogue sweep: force gate 0x570 bit 13, call 0xdf7f with id = (@0x503+1) & 0x3F | Which request ids exist and what do they play? | No verified result | RETIRED | Found that 0xdf7f(id) is Bose's audio-request API (docs/bose-firmware-anatomy.md). The catalogue was finished by probes 28-38 (docs/request-id-catalog.md). | none | asm words cmd Q:probe15_catalog.dfu |
| probe15b | 09-28 (built) u1 | Sweep v2: counter moved to global 0x518, gate bit saved and restored; 46-word cave, 99 bytes diff | Same, without derailing the counter | Flashed (readback flash_readback_probe15b.bin matches the image). The narrative says the session wedged after press 1 (unverified; probe16 docstring). | RETIRED (void) | Press results void (wrong button). The readback is one of four that proved accepted-and-programmed byte for byte (README 2026-09-29). | none | asm words cmd rb:flash_readback_probe15b.bin Q:probe15b_catalog.dfu |
| probe15c | 09-28 (built) u1 | Sweep v3 with telemetry | Same | None recorded | RETIRED | Image quarantined; no result. | none | asm words cmd Q:probe15c_catalog.dfu |
| probe16 | 09-28 (built) u1 | Sweep v4: request moved to the stock site; rewrote post-flow 0xae3-0xae8 | Does a stock-site request avoid the "wedge"? | None recorded | RETIRED | Header (unverified): the extra 0xdf7f in 15b/15c was thought to be what wedged the session; later work shows the real constraint is the cave frame (L4007). | none | asm words cmd Q:probe16_sweep.dfu |
| probe17 | 09-28 (built) u1 | Sweep v5: zero structural delta, one word changed (`ld AL,@(10,Y)` at 0xae3), counter at 0x518 | Same | None recorded | RETIRED | See probe16. | none | asm words cmd Q:probe17_sweep.dfu |
| probe17b | 09-28 (built) u1 | Variant "sweep0" of probe17 | Same | None recorded | RETIRED | See probe16. | none | asm words cmd Q:probe17b_sweep0.dfu |
| probe18a | 09-28 (built) u1 | Image probe18a_counter (assembler file carries probe17's docstring) | Intent per docs: content control by repointing a dead fs file record or an rphrases_us directory entry ("probe18 lever", docs/bose-firmware-anatomy.md section 15) | None recorded | RETIRED | Not documented beyond file names. | none | asm words cmd Q:probe18a_counter.dfu |
| probe18b | 09-28 (built) u1 | Image probe18b_redirect | Same | Flashed (readback_18b.bin matches the image, README). No result recorded. | RETIRED | Same. | none | asm words cmd rb:readback_18b.bin Q:probe18b_redirect.dfu |
| probe18c | 09-28 (built) u1 | Image probe18c_const5 | Same | None recorded | RETIRED | Same. | none | asm words cmd Q:probe18c_const5.dfu |
| probe19 | 09-28 (built) u1 | PCM port scan: per press, StreamKalimbaSink(port N-1), claim/map/write 64-word square burst/flush | Which Kalimba port is live? | Raw writes into an unconnected Kalimba sink were silent (docstring of probe20, unverified) | RETIRED (void) | Pressed on the wrong button with wrong trap numbers. | none | asm words cmd Q:probe19_pcmscan.dfu |
| probe20 | 09-28 (built) u1 | Tone source (StreamRingtoneSource, StreamConfigure 0x30b) connected to Kalimba port 3, 32 note words | Does a tone source reach the DSP port? | Docstring of probe21: "connect WORKS (quiet hiss = our notes reaching the DSP!)", cutout by the 0x4757 watchdog (unverified) | RETIRED (void) | Passed the bogus configure key 0x300B (L1356); docs/content-control-analysis.md lines 215-220 doubt it ever ran. | L1356 (cross-reference) | asm words cmd Q:probe20_connect.dfu |
| probe21 | 09-28 (built) u1 | probe20 plus a loudness attack (control words 0xA0FF/0xB002/0x90F0, KalimbaSendMessage 0x10a9) | Can the tone be made loud? | Unverified | RETIRED (void) | Stale-CRC defect noted against it (docs/next-probe-v2-idswap.md line 106). | none | asm words cmd Q:probe21_loud.dfu |
| probe22 | 09-29 u1 | Hook 0xae0 -> cave 0x3E21D, 13 words: `enterl -8`, tone 0x4946, write 0x1234 to abs 0xcb34 and read back (second tone if equal), @0x536 = (ctr++ & 0xF) << 11, return to stock 0xae3 | Does the cave run; is the 0xcb__ region writable? | "I tried probe 22 and the behavior is just as normal. beep then flash, second press flash only, 3rd press beep and flash, fourth press flash only and repeat." (centre button) | PROVEN-POSITIVE (boots and runs); cave execution INCONCLUSIVE | Build, accept, boot, run is proven end to end. Two readings (cave ran silently / cave never ran) were not separated. Corrects opus_task/CORRECTION_TO_CONSULT2.md s3 (its "cave beeps every press" was the stock chirp). | L25 | asm words cmd rb Q:probe22_scan.dfu |
| probe23 | 09-29 u1 | Id swap 0x35 -> 0x16 at 0xae3 (1 byte) plus 21 compensation bytes in the data_us tail | Does the swapped id change the long-press sound? | "every other long press beeps. they all flash. no different. voice prompts work fine." (centre button) | RETIRED (void: wrong button) | Compensation bytes in the data_us tail (body 0x35A60-0x35AF2) are harmless (precedent, not structure). The alternation is the stock toggle. | L117, L157 | cmd dfu:probe23_idswap.dfu rb |
| probe24 | 09-29 u1 | Cave head `bra +0` (infinite loop), trigger-gated | If the cave runs it must hang | "nothing changed" (centre button) | RETIRED (void; conclusion retracted) | "The cave never executes" was withdrawn at L453: the owner had pressed the centre button. | L208, L240, L453 | cmd dfu:probe24_halt.dfu rb |

### 4.2 Era E2: the right button and the id lever (probes 25-38)

All 09-29, u1. From here every press is a Bluetooth long press unless stated.

| probe | date, unit | what it changed | question | press result | verdict | key lesson | log | artefacts |
|---|---|---|---|---|---|---|---|---|
| probe25 | 09-29 u1 | Stock plus 10 bytes: `bra` over `ld AL,#id` at five 0xdf7f sites (0x5C5, 0xAE3, 0xD25, 0xE0BE, 0xE0C9) | Which prompt site is live? | "Seems normal with one possible exception. When I have one device connected and hold down bluetooth button, I don't get a voice prompt to connect the second device." | INCONCLUSIVE (candidate) | Needed a stock control (next row). | L261, L296 | cmd dfu:probe25_silence.dfu rb |
| stock control | 09-29 u1 | Official Minnow_3.0.3_stack_plus_app.dfu reflashed (sha256 5ae3bc96...4659e), readback 0 bytes differ | Does stock say "ready to connect another device" with one device connected? | "stock says "ready to connect another device" with one device connected and a long press of the bluetooth button" | PROVEN-POSITIVE | CONFIRMED: code edits reach executed code; the mapping file_offset(a) = 0x12E97C + 2a and fs_offset(a) = 0x6EA30 + 2a are right (proven). | L313, L337, L342 | rb:readback_stock_control.bin |
| probe26 | 09-29 u1 | One byte: id 0x17 -> 0x1b at word 0xE0BE | Is 0xE0BE the site? | "same behavior. "ready to connect another device"" | NEGATIVE | 0xE0BE is not the site. | L364, L383 | cmd dfu:probe26_site.dfu rb |
| probe27 | 09-29 u1 | `bra +4` at 0xAE3 (suppress the id-0x35 request), hook at 0xAE0 stock | Is the 0xAE0/0xAE3 block the Bluetooth-hold path? | "prompt gone" | PROVEN-POSITIVE | Id 0x35 = "ready to connect another device"; the block runs on a Bluetooth-button hold (event 0x4003), not a voice-assistant hold (proven). Voids probes 10-24. | L394, L432, L436, L453 | cmd dfu:probe27_ae3.dfu rb |
| probe28 | 09-29 u1 | First live cave: `enterl -3`, counter @0x520, `bsr 0xdf7f(id)` then `bsr 0xe06d` (order inverted vs stock) | Does the cave run on a Bluetooth hold? | "the first long press appears to crash and reboot the device. second led from left flashes briefly, then the 5 right most leds light up then go dark. then it boots normally when I press power" | PROVEN-POSITIVE (cave executes) | THE CAVE EXECUTES; a crash is a positive result here. Crash cause unattributed until probe80. | L480, L534, L541 | asm words cmd dfu:probe28_sweep.dfu rb |
| probe29 | 09-29 u1 | Passthrough cave `enterl -3; bsr 0xe06d; leavel -3` | Is the machinery sound without a payload? | ""Ready to connect another device" plays, no crash" | PROVEN-POSITIVE | First working cave; probe28's fault was its payload (proven). | L567, L596, L600 | asm words cmd dfu:probe29_passthru.dfu rb |
| probe30 | 09-29 u1 | probe29 plus `ld AL,#0x35; bsr 0xdf7f` inside the cave (stock order) | Can the cave issue the request itself? | "crash" | NEGATIVE | Call order is not the cause. The first hypothesis (frame depth) was only partly right; the real cause was found at probe80. | L612, L656 | asm words cmd dfu:probe30_const.dfu rb |
| probe31 | 09-29 u1 | One byte: `ld AL,#0x35` -> `#0x16` at 0xAE3, no cave | Does the stock-site call path honour another id? | "long press says "english". verified 2x." | PROVEN-POSITIVE | Id 0x16 = "English"; the stock-site path works (proven). | L692, L721 | cmd dfu:probe31_idonly.dfu rb |
| probe32 | 09-29 u1 | `bra` trampoline at 0xAE3 into the cave, which calls `bsr 0xdf7f` at stock frame depth; id from @0x503; new 3-word long-branch encoder | Can a trampoline carry the request? | "Same sound every press "connecting to"" | INCONCLUSIVE | Trampoline runs, no crash, but the stock TTS was truncated (an unmapped id preempted it). | L743, L797, L801 | asm words cmd dfu:probe32_tramp.dfu rb |
| probe33 | 09-29 u1 | probe32 with the counter moved to @0x520 | Is the id actually changing? | "Same sound every press "connecting to"" | INCONCLUSIVE | Identical to probe32: the id sweep via @0x503 fails because stock overwrites it. | L819, L853 | asm words cmd dfu:probe33_sweep.dfu rb |
| probe34 | 09-29 u1 | Trampoline requesting the known-good id 0x16 | Is the trampoline the variable? | "that crashed . and for the record "connecting to" would normally be followed by a tts description of the device" | NEGATIVE | A real-prompt id via the trampoline crashes. | L867, L890 | asm words cmd dfu:probe34_const.dfu rb |
| probe35 | 09-29 u1 | Trampoline carrying the stock id 0x35 (functionally identical to stock) | Does stock behaviour survive the trampoline? | "crash." | NEGATIVE | A trampoline cannot carry a real prompt request; frame depth was necessary, not sufficient. Speaker restored to stock after. | L920, L941 | asm words cmd dfu:probe35_stockid.dfu rb |
| probe36 | 09-29 u1 | `ld AL,@0x70` at 0xAE3; cave stores 0x16 to @0x70 then `bsr 0xe06d` | Can the cave pick the id through a global? | "crash" | NEGATIVE | Absolute addresses below 0x80 are VM internals, not free globals (proven by crash). | L977, L1032 | asm words cmd dfu:probe36_idglobal.dfu rb |
| probe37 | 09-29 u1 | 0xAE3 = `bra +1` no-op; cave `enterl -3; bsr 0xe06d; ld AL,#0x16; leavel -3` | Can the cave choose the id while stock issues the request? | ""english"" | PROVEN-POSITIVE | THE LEVER IS COMPLETE: our code chooses what the loud engine path plays, touching no RAM. Three constraints: stock makes the deep call, the id is in AL after the back-call, no RAM below 0x80. | L1056, L1087, L1091 | asm words cmd dfu:probe37_alcarry.dfu rb |
| probe38 | 09-29 u1 | Counter @0x520 supplies AL, ids 0..63 in one flash | Can all 64 ids be swept in one flash? | "it's cycling between prompts but the power cycle doesn't reset it to 1 so I'm not sure of the order" | PROVEN-POSITIVE | Sweep works; VM RAM persists across a Bose "power off" (a sleep state). Anchor counts on "English" 0x16 and "Ready..." 0x35. The 64-id catalogue was finished by later sweeps (docs/request-id-catalog.md). | L1125, L1168 | asm words cmd dfu:probe38_sweep.dfu rb |

### 4.3 Era E3: injection on wrong trap numbers, speech lever, DAC attempts (probes 39-58)

| probe | date, unit | what it changed | question | press result | verdict | key lesson | log | artefacts |
|---|---|---|---|---|---|---|---|---|
| probe39 | 09-29 u1 | 115-word cave: nine trap calls aimed at Bose's Kalimba port 0xfffb, `leavel -12`, connector hops | Can we inject into Bose's own port? | "crash" | INCONCLUSIVE | Uninformative: too many changes at once (methodology failure recorded; rule "one change per flash"). | L1196, L1241 | asm words cmd dfu:probe39_negport.dfu rb |
| probe40 | 09-30 u1 | probe37 plus one trap, StreamKalimbaSink(0xfffb) | Is a trap call from a cave safe? | ""english"" | PROVEN-POSITIVE | A trap call from a cave is safe (proven). Which stub was called is suspect under the later trap-numbering finding (L2161). | L1258, L1282 | asm words cmd dfu:probe40_ksink.dfu rb |
| probe41 | 09-30 u1 | probe40 plus StreamRingtoneSource | Is the ringtone-source call safe? | ""english" and this isn't an urgent priority but remember that its the voice assistant center button that we want to use as the trigger, not the bluetooth button" | INCONCLUSIVE | Safe, but the call took a null tune (mis-numbered trap). PRODUCT REQUIREMENT recorded: trigger = the centre (voice-assistant) button. | L1297, L1326, L1334 | asm words cmd dfu:probe41_rsrc.dfu rb |
| probe42 | 09-30 u1 | probe41 plus StreamConfigure with the "corrected" key 0x30B | Does StreamConfigure work from a cave? | "crash" | NEGATIVE | The inherited W(0x3000,0x0B10) folds to 0x300B, not 0x30B (proven by decode); the corrected key was not sufficient (argument and trap-number errors, L1550, L2161). | L1353, L1390 | asm words cmd dfu:probe42_sconfig.dfu rb |
| probe43 | 09-30 u1 | Mirror 0x4946's frame discipline: `enterl -6`, null-source bail, arg slots zeroed | Does frame discipline fix the configure crash? | ""English"" | INCONCLUSIVE | Passed, "right by luck" per L1620. | L1409, L1446 | asm words cmd dfu:probe43_frame.dfu rb |
| probe44 | 09-30 u1 | probe43 plus StreamSinkFromSource (0x12a), omits 0x42 | Next call in Bose's tone setup | "crash" | NEGATIVE | 0x42 = PanicNull; `enterl -6` functions reference slots up to @(37,Y); led to "ask the compiler" (L1538). | L1469, L1497 | asm words cmd dfu:probe44_feed.dfu rb |
| probe45 | 09-30 u1 | Call Bose's own 0x4946 from the cave: `enterl -6; bsr 0xe06d; ld AL,#0; bsr 0x4946; ld AL,#0x16; leavel -6` | Does Bose's tone setup run from a cave? | ""English"" | PROVEN-POSITIVE | Bose's tone setup is safe from a cave; stub convention (one-arg stream trap: arg in @(0,Y), AL=3, AH=0, result in AL) settled from compiled ADK code, refined at L2161/L2487. | L1570, L1612, L1620 | asm words cmd dfu:probe45_call4946.dfu rb |
| probe46 | 09-30 u1 | "StreamKalimbaSink(0xfffb) encoded correctly" | Retry probe40's call with the new convention | "crash" | RETIRED (void) | Stub 0x1BE is KalimbaPowerOff, not StreamKalimbaSink (0x1B4): L2161. | L1638, L1663 | asm words cmd dfu:probe46_port.dfu rb |
| probe47 | 09-30 u1 | "Port 3" in place of 0xfffb (again KalimbaPowerOff) | Is port 3 reachable? | "crash" | RETIRED (void) | Declared "THE VM AUDIO-INJECTION ROUTE IS CLOSED" (L1695); WITHDRAWN at L2161 and refuted by probes 65-75. | L1673, L1691, L1695 | asm words cmd dfu:probe47_port3.dfu rb |
| probe48 | 09-30 u1 | 52 of 147 rphrases_us count words (0x80NN) set to 255 units | Is the unit-count word a content lever? | "long and garbled confirmed. sounds like slow motion speech." | PROVEN-POSITIVE | The unit-count word works as a lever (proven). Speech route later closed by owner decision. | L1747, L1782 | cmd dfu:probe48_longphrase.dfu rb |
| probe49 | 09-30 u1 | 232 editable bytes after phrase 1 randomised (seed 20260930) | What do the parameter bytes do? | "some slow motion, but with speed changes and pitch changes. some empty quiet. some bizarre sounds." | PROVEN-POSITIVE | Phrase payload format decoded: N unit indices + ceil(N/2) param words + 2 trailer words, 9 of 9 phrases. | L1803, L1823 | cmd dfu:probe49_randunits.dfu rb |
| probe50 | 09-30 u1 | Constant 0x80 fill in the parameter bytes (311 bytes differ) | Is there a clean speed control? | "It still sounds like the normal voice prompts but at 20% of the normal playback speed." | PROVEN-POSITIVE | Clean speed control: level sets speed, spread sets variation. | L1857, L1874 | cmd dfu:probe50_constfill.dfu rb |
| probe51 | 09-30 u1 | Random parameters 0x00-0x3F (319 bytes differ) | Does a very low band approach a rumble? | Flashed (readback exists), never pressed. Owner: "This is academically interesting but I want to figure out real brown noise." | RETIRED | Speech route closed by decision. | L1899 | cmd dfu:probe51_lowband.dfu rb |
| probe52 | 09-30 u1 | probe37 plus a trap believed to be StreamAudioSink (really StreamScoSink, stub 0x16A) | Can the DAC be opened from a cave? | ""English"" | INCONCLUSIVE (void) | Nothing about the DAC was tested (L2161); almost certainly returned 0 (L2487). | L1930, L1970 | asm words cmd dfu:probe52_dac.dfu rb |
| probe53 | 09-30 u1 | SinkClaim/SinkMap/write 16 words/SinkFlush on the wrong sink | Can a waveform be written to the DAC? | "Long press = "ready to connect"" (id 0 = corrupted return value) | INCONCLUSIVE (void) | First blamed on `add X,@0xffe1`; probe55 says that word is right ($XAP_AL = 0xffe1). The real defect was the wrong trap names. | L1980, L2014 | asm words cmd dfu:probe53_write.dfu rb |
| probe54 | 09-30 u1 | probe53 with the SinkClaim offset dropped and real amplitude +-0x1000 | Retry the write | Flashed, never pressed (superseded by probe55). | RETIRED | Its premise was wrong: the dropped instruction was never broken. | L2043 | asm words cmd dfu:probe54_write.dfu rb |
| probe55 | 09-30 u1 | Real Galois-LFSR brown noise (0xB400 plus integrator) written to the DAC, built with tools/caveasm.py | Does brown noise reach the DAC? | Flashed while the owner was away; never pressed. | RETIRED (dead: wrong traps) | Called StreamScoSink and friends (L2161). | L2065 | asm words cmd dfu rb |
| probe56 | 09-30 u1 | probe55 plus SinkConfigure rate/gain | Same with the codec configured | Flashed, never pressed | RETIRED (dead: wrong traps) | As probe55. | L2108 | asm words cmd dfu rb |
| probe57 | 09-30 u1 | First probe with the right traps (StreamAudioSink 0x162, SinkConfigure 0x11A, SinkSlack 0x0DA, SinkClaim 0x0DE, SinkMap 0x0E2, SinkFlush 0x0E6), direct PCM write, 119 words | Does a direct PCM write reach the DAC? | Flashed, superseded untested by probe58. | RETIRED | No ADK precedent for writing PCM into an audio sink; retiring it untested was later called a mistake, and the direct-write route was closed by measurement (probe64). | L2190 (and L3004 ff) | asm words cmd dfu |
| probe58 | 09-30 u1 | Source route: malloc buffer, LFSR fill, StreamRegionSource, StreamConnect to the DAC; 143 words, speaking bail ids. Rev 2 (second flash): gain 12 -> 15 (15 = 0 dB, 3 dB/step) | Does a connected region source play on the DAC? | "Crashed on long press" | NEGATIVE | Broke the one-variable-per-flash rule (six calls); cause found by the probe59-63 bisect: StreamConnect to the codec sink. First use of tools/cavesim.py. | L2263, L2380, L2425 | asm words cmd dfu |

### 4.4 Era E4: correct traps, single-call bisect, the frame bug (probes 59-81)

All u1. Spoken ids are the cave's diagnostics: 0x12 "Voice prompts on", 0x13 "voice prompts off", 0x15 "auto off enabled", 0x04 "connected", 0x06 "lost", 0x0E "connected to", 0x08 "disconnected" (docs/request-id-catalog.md).

| probe | date, unit | what it changed | question | press result | verdict | key lesson | log | artefacts |
|---|---|---|---|---|---|---|---|---|
| probe59 | 09-30 u1 | `StreamAudioSink(CODEC=3, INSTANCE_0=0, CHANNEL_A_AND_B=2)` only (stub 0x162); 19 words; success speaks 0x12 | Does a corrected-table trap call work from a cave? | "Voice prompts on" | PROVEN-POSITIVE | First real trap call to do work; the corrected trap table and the 3-argument ABI are confirmed on hardware (proven). | L2459, L2487 | asm words cmd dfu |
| probe60 | 09-30 u1 | + `SinkConfigure(sink, OUTPUT_RATE, 8000)`; 35 words | Is the configure call accepted? | "voice prompts off" (0x13, success) | PROVEN-POSITIVE | SinkConfigure returned true. | L2517, L2543 | asm words cmd dfu |
| probe61 | 09-30 u1 | + `malloc(1024)` then `malloc(128)`; 50 words | Is malloc safe, and how big? | "auto off enabled" (0x15) | PROVEN-POSITIVE | malloc(1024) is null, malloc(128) succeeds; probe58's buffer was only 128 words = 16 ms at 8 kHz. | L2577, L2603 | asm words cmd dfu |
| probe62 | 09-30 u1 | + `StreamRegionSource(buf,128)`; 54 words | Is a region source obtainable? | "connected" (0x04) | PROVEN-POSITIVE | Non-null source. | L2637, L2658 | asm words cmd dfu |
| probe63 | 09-30 u1 | + `StreamConnect(src, codec sink)`; 65 words | Is the connect the crash in probe58? | "crash" | NEGATIVE | StreamConnect to the codec sink kills the firmware; bisect finished. Later refined: probe86 shows the crash depended on channel and source type. | L2682, L2723 | asm words cmd dfu |
| probe64 | 09-30 u1 | `SinkSlack` on the codec sink; 44 words | Can the codec sink be written directly? | "lost" (slack 0) | NEGATIVE | Codec sink already owned and connected by Bose; direct write closed. The reading was softened at L2950: zero slack may be what every audio endpoint reports. | L2769, L2794 | asm words cmd dfu |
| probe65 | 09-30 u1 | `StreamKalimbaSink(0)` + SinkSlack; 29 words | Does a Kalimba sink have room? | "lost" | NEGATIVE | First true StreamKalimbaSink call (0x1B4): non-null sink, slack 0. | L2836, L2870 | asm words cmd dfu |
| probe66 | 09-30 u1 | Ports 7, 6, 5, 4; 71 words | Does any other port have room? | "lost" | NEGATIVE | Every audio sink reports zero slack: endpoints, not writable (observation proven, interpretation hypothesis). | L2903, L2944 | asm words cmd dfu |
| probe67 | 09-30 u1 | `StreamConnect(src, Kalimba sink 0)`; 47 words | Is a connect to a Kalimba sink survivable? | First flash attempt failed (errFIRMWARE incident); second attempt "connected to" (0x0E) | PROVEN-POSITIVE | StreamConnect to a Kalimba sink is survivable and returns a non-null transform. Incident: enter-dfu OK, then hidapi errors on download; errFIRMWARE after replug; recovered by reflashing probe66 (0 of 975,168 differ). errFIRMWARE is not a brick; never chain build + flash + leave-dfu (L3035). | L2972, L3004, L3073 | asm words cmd dfu |
| probe68 | 09-30 u1 | Generator loop (90 words) + StreamConnect | Does the LFSR brown generator run in the cave? | "crash" | NEGATIVE | First hypothesis: MPU or heap write (wrong; see probe80). | L3138, L3182 | asm words cmd dfu |
| probe69 | 09-30 u1 | probe68 storing to a stack slot instead of the heap | Is it the heap write? | "crash" | NEGATIVE | Not the heap write. Census: every working cave was straight-line. | L3206, L3226 | asm words cmd dfu |
| probe70 | 09-30 u1 | Trivial countdown loop; 58 words | Do backward branches work? | "connected to" | PROVEN-POSITIVE | Backward branches work. | L3258, L3279 | asm words cmd dfu |
| probe71 | 09-30 u1 | 65-word loop body spanning connectors; 82 words | Do connector hops inside loops work? | "connected to" | PROVEN-POSITIVE | Connectors inside loops are fine. | L3296, L3317 | asm words cmd dfu |
| probe72 | 09-30 u1 | Generator minus the leak words; 85 words | Is the leak the fatal part? | "crash" | NEGATIVE | Not the leak. | L3348, L3368 | asm words cmd dfu |
| probe73 | 09-30 u1 | Arithmetic run once, straight-line, no loop; 74 words | Which instruction is fatal? | "crash" | NEGATIVE | One of seven instructions seemed fatal; bisect stopped deliberately. The real cause (frame slots) came at probe80. | L3390, L3416 | asm words cmd dfu |
| probe74 | 09-30 u1 | `StreamRingtoneSource(0xBA3C)` (13 const notes in cave padding) to `StreamKalimbaSink(3)` with the DSP off; 50 words | Does a const array stream into port 3? | "connected to", no sound | INCONCLUSIVE | A const pointer is a valid stream source. "No sound" was explained by probe75: no .kap is loaded when idle. | L3462, L3532 | asm words cmd dfu rb |
| probe75 | 09-30 u1 | + `KalimbaSendMessage(0x1072 SET_TONE_RATE)`; 70 words; pressed twice | Does the DSP play the tone? | Idle: "disconnected". Music playing: "a brief TONE, then "connected to"" | PROVEN-POSITIVE | First sound the project authored. A .kap is loaded only while A2DP is active or a prompt plays; stub 0x1C3 = KalimbaSendMessage confirmed. Corrects the port-0 / port-3 "DSP ignores" readings of probes 67/74. | L3543 | asm words cmd dfu rb |
| probe76 | 09-30 u1 | Success id 0x02 (silent) | Is prompt audio what cuts the tone? | "a brief tone, no speech" | NEGATIVE | A silent id does not preserve the tone: KalimbaLoad of NowSpeakTTS.kap happens before any check. | L3640, L3663 | asm words cmd dfu rb |
| probe77 | 09-30 u1 (re-pressed 10-01 u1, 10-04 u1, 10-04 u2) | Three `nop` over the prompt call `bsr 0xdf7f` at 0xAE4..0xAE6 (reporting channel lost on purpose); ringtone to port 3; 70 words | Does removing the prompt's KalimbaLoad let the tone sustain? | "long tone, low, maybe 600Hz. think car horn, not brown noise. no music playing = no tone". Later with phone connected and music PAUSED: "a long clean tone"; 10-04 u1 "tone plays"; u2 "long clean tone". | PROVEN-POSITIVE | The control probe. The prompt's KalimbaLoad was the thief. Loud, sustained, software-authored sound on a button press works with a phone connected. Pitch about 2x design (DSP at 16 kHz vs declared 8000). A ringtone is periodic: a diagnostic, not the deliverable. | L3669, L3740, L5318, L7664, L7724 | asm words cmd dfu rb:probe77_readback.dfu,probe77_restore_readback.dfu,probe77_unit2_readback.dfu |
| probe78 | 09-30 u1 | Compiled generator lifted by tools/liftfn.py, malloc(130), nested `enterl -2`; 142 words | Does a compiler-built generator run? | "crash" | NEGATIVE | Broke the one-change rule (five changes). Transcription, single opcode, emulator error all ruled out; every crasher wrote through a pointer (coincidence). | L3758, L3833 | asm words cmd dfu rb |
| probe79 | 09-30 u1 | malloc(8), pointer round trip, one generator sample, no streams; `enterl -8`; 104 words | Is a pointer write the fault? | "crash, no spoken word" | NEGATIVE | Pointer writes and clobbering X are ordinary in Bose code (1,514 sites). | L3867, L3893 | asm words cmd dfu rb |
| probe80 | 09-30 u1 | malloc(8) + read + write through the pointer only; 27 words | Isolate the crash | "crash" | NEGATIVE | Real cause (docs/cave-frame.md): `enterl -k` reserves slots k-2 and k-1 for the 2-word saved return address; a store to slot 6 or 7 of `enterl -8` crashes (proven by a 20-probe correlation, Bose codegen and hardware). Overturns the generator, leak, MPU, pointer hypotheses of probes 68-79. | L3916, L3943 | asm words cmd dfu rb |
| probe81 | 10-01 u1 | Same test as probe79 with `enterl -16`; 103 words | Is the frame the whole problem? | "connected to" | PROVEN-POSITIVE | The frame rule was it; the generator was always correct (first sample 0xFE27 bit-exact on the speaker). | L3976, L4007 | asm words cmd dfu rb |

### 4.5 Era E5: running without music, the codec route, the wedge (probes 82-97)

All 10-01, u1.

| probe | date, unit | what it changed | question | press result | verdict | key lesson | log | artefacts |
|---|---|---|---|---|---|---|---|---|
| probe82 | 10-01 u1 | Call chain: malloc 512/256/128, noise to port 3, prompt stock; 166 words | Does generated noise reach port 3? | No music: "disconnected". Music, first press: "connected to". Later presses: stock "ready to connect". No hiss. | INCONCLUSIVE | Tested the call chain, not the audio. "Heap ceiling 512" was later undermined (probably 256 misheard, L9758). First long press enters pairing; later presses take a branch at 0x0ACD that never reaches the cave. | L4020, L4065 | asm words cmd dfu rb |
| probe83 | 10-01 u1 | 400 Hz square wave, 64 ms, prompt deleted; 127 words | Can the cave make a tone without the prompt? | "I'm not sure. Would it work only once? If I heard anything it was very very short." | INCONCLUSIVE | Owner constraint: no more tests with music playing, which forces the standalone-DSP architecture. Fixed branch-relaxation oscillation and +-128-word bsr bugs in the cave assembler. | L4086, L4126 | asm words cmd dfu rb |
| probe84 | 10-01 u1 | 256 ms square at a 2 kHz tone rate | Longer tone | Flashed (cycle 67), superseded untested by probe85 | RETIRED | Still needed music. Three more assembler bugs listed at L4158-4175. | L4147 | asm words cmd dfu |
| probe85 | 10-01 u1 | Cave loads the DSP itself: `FileFind(1,0xB3D2,27)` (NowSpeakTTS.kap), `VmDeepSleepEnable(0)`, `KalimbaLoad`, `KalimbaSendMessage(0x1072,2000)`; 60 words | Can the cave load a .kap without music? | "connected to" with no music | PROVEN-POSITIVE | The cave owns the DSP load and the DSP answers; music dependency broken. Reflashed as the safe baseline at cycle 75 after probe92 was pulled. | L4176, L4216 | asm words cmd dfu rb |
| probe86 | 10-01 u1 | DSP-less tone path: `StreamAudioSink(3,0,0)`, `StreamRingtoneSource(0xBA3C)`, `StreamConnect`; prompt deleted; 44 words | Does Bose's DSP-less tone path reach the codec? | "silence, no crash" | NEGATIVE | Retires the probe63 claim "StreamConnect to the codec sink is FATAL" (channel and source type differed). Later (L5864) disassembly found probe86's "bare StreamConnect" call is a function that does two StreamDisconnects first. | L4236, L4274 | asm words cmd dfu rb |
| probe87 | 10-01 u1 | Region source (generated noise) on codec channel 0, no DSP, per its docstring | Separate source type from channel in probe86's silence | None recorded; image built, superseded by probe88; no field-log section | RETIRED | Planned at L4260/L4286 only. Flash status unknown. | L4260 (mention) | asm words cmd dfu |
| probe88 | 10-01 u1 | probe86 plus codec gain 15 on both channels and unmute (copied from 0x1E4D4, 0x1E433); 89 words | Was the DAC gain unset? | "silent" | NEGATIVE | Not the gain either. | L4308 | asm words cmd dfu rb |
| probe89 | 10-01 u1 | + rate 8000, spoken ids, prompt stock; 102 words | Is every codec-sink call survivable? | "connected to", no tone | INCONCLUSIVE | Every call on the codec sink succeeds, but the stock prompt steals the DAC, so the pre-registered rule "no tone => abandon codec route" was wrong. | L4347, L4383 | asm words cmd dfu rb |
| probe90 | 10-01 u1 | probe89 with the prompt deleted | Does the codec route make sound alone? | "silence, no crash" | NEGATIVE | Codec route declared closed (accepts a source, configures, unmutes, yields a transform, no sound). Settled as unactionable at L6266 and L6563 (no VM-reachable codec power control; device uses channel A). Control for cavesim from L5915. | L4413 | asm words cmd dfu rb |
| probe91 | 10-01 u1 | Open-coded DSP route with sbc_decoder.kap (0xBD75): load, sinks, connect, start; `enterl -24`; 154 words, 12 calls | Run the DSP ourselves | "nothing, and I mean nothing. it booted and connected but none of the buttons do anything at all." | NEGATIVE | The VM app wedged (bose-dfu info times out, list still shows the device). Claimed causes both retracted: stack overflow (stack headroom 262, L4659) and "30 s hold cures it". bose-dfu info is the liveness test. | L4447, L4513, L4659 | asm words cmd dfu rb |
| probe92 | 10-01 u1 | probe91 with `enterl -16` | Test the frame theory | Flashed (cycle 74), pulled before any press; probe85 reflashed | RETIRED | Stack theory wrong: header word [09] = stack size 316, depth at the hook 54, headroom 262 (tools/stackdepth.py). One wedge is not a diagnosis. | L4633, L4659 | asm words cmd dfu rb |
| probe93 | 10-01 u1 | probe85 with the sbc_decoder.kap name (2 words differ); cycle 76 | Does loading the decoder wedge? | "connected to", no music | PROVEN-POSITIVE | sbc_decoder.kap loads from a cave and the DSP answers; loading alone is clean. | L4741, L4792 | asm words cmd dfu rb |
| probe94 | 10-01 u1 | + StreamAudioSink(3,0,2), SinkConfigure(OUTPUT_RATE 16000), StreamKalimbaSink(0), StreamSourceFromSink; 106 words | Are all handles obtainable? | "connected to" | PROVEN-POSITIVE | Every handle is obtainable, including the one never-called trap. | L4806, L4841 | asm words cmd dfu rb |
| probe95 | 10-01 u1 | + `StreamConnect(ksrc, dac)`; 116 words | Is wiring the DSP output to the DAC survivable? | "connected to" | PROVEN-POSITIVE | Connect is survivable and returns a transform, but only because nothing was flowing (see probe97). | L4856, L4884 | asm words cmd dfu rb |
| probe96 | 10-01 u1 | + `KalimbaSendMessage(0x7000)` (start); 134 words | Last element of probe91's bisect | WEDGE | NEGATIVE | First read as "0x7000 is the culprit"; reframed by probe97. Recovery as recorded at L4956 (n=1): 8 min wait no; unplug + 30 s power hold no; hold POWER + VOICE ASSISTANT ~10 s => DFU 05a7:4022. Not reliable: it did not recover the 2026-10-08 wedge (L11821) and L11804 says the one earlier success was an errFIRMWARE case; see FACTS.md X008 and section 5. The standing recovery is unplug USB, hold POWER ~20 s, replug, press POWER. | L4891, L4937, L4956 | asm words cmd dfu rb |
| probe97 | 10-01 u1 | probe95 + a source on tone port 3 (`StreamKalimbaSink(3)`, `StreamRingtoneSource`, `StreamConnect`), no 0x7000 anywhere; 163 words | Is the start message the culprit? | WEDGE | NEGATIVE | It is the DAC, not the start message: taking the DAC from Bose's audio manager and letting data flow is fatal (well-supported; mechanism hypothesis). The "own the DSP" architecture is dead; the firmware must keep the DSP and the cave must only feed port 3. | L4989, L5030 | asm words cmd dfu rb |

### 4.6 Era E6: timers and the ADPCM discovery (probes 98-106)

u1, 10-01 to 10-02.

| probe | date, unit | what it changed | question | press result | verdict | key lesson | log | artefacts |
|---|---|---|---|---|---|---|---|---|
| probe98 | 10-01 u1 | Inverted design: firmware owns the path (cave returns prompt id 0x0E); a `MessageSendLater` timer (300 ms, TaskData 0003 e265 in const padding) injects into port 3 from a handler; 60 words | Can a timer handler feed port 3? | "connected to" and nothing | INCONCLUSIVE | Ambiguous because the handler had no voice (the same trap as probes 86/88/90). | L5096, L5159 | asm words cmd dfu rb |
| probe99 | 10-01 u1 | + the handler speaks via `bsr 0xDF7F` (0x16 "english" on success); 84 words | Does the handler run? | "connected to" ... "english" | PROVEN-POSITIVE | MessageSendLater + const-padding TaskData + callback ABI deliver and run a handler about 300 ms later; all three handler calls succeed. Problem is "when": the prompt connects its own source to port 3 (ADK voice_prompts_dsp_if.c:398). | L5173, L5210 | asm words cmd dfu rb |
| probe100 | 10-01 u1 | Handler re-arms itself, 12 attempts 300 ms to 2.5 s; 100 words | Is there a window when port 3 is free? | "voice prompts off" (0x13: connect refused) | NEGATIVE | The prompt plugin uses port 3 itself while the A2DP decoder leaves it free, so the prompt-driven design (98-100) cannot work in principle. Author bug (failure bails skipped the re-arm); decode-verify knew only 4 of 12 branch opcodes (fixed). | L5242, L5282 | asm words cmd dfu rb |
| probe101 | 10-01 u1 | malloc(512), noise_fill, `0x1072` rate 1000, `StreamRegionSource` straight to port 3; 166 words (phone connected, music paused) | Brown noise through the probe77 path | "silence" | NEGATIVE | Causes later retracted (see probe102 and probe104). | L5352, L5400 | asm words cmd dfu rb |
| probe102 | 10-01 u1 | Timer refill every 60 ms, buffer pointer carried as MessageId, rate 8000, region source; 172 words | Does a refilled region source play? | "silence" | RETIRED (conclusion retracted) | Concluded "StreamRegionSource is not an audio source" and closed the PCM-in-RAM route; RETRACTED at L5554: the port needs an ADPCM transform, a region source delivers one byte per 16-bit word, and the probe reconnected without StreamDisconnect. Probes 82, 83, 84, 101, 102 are invalidated. | L5415, L5476, L5554 | asm words cmd dfu rb |
| probe103 | 10-01 u1 | malloc(512) + brown ADPCM, 28 ms refill | Brown ADPCM through the transform | "lost" | NEGATIVE | malloc(512) returned 0 on the first call, so nothing after it ran. | L5533 | asm words cmd dfu |
| probe104 | 10-01/02 u1 | No malloc: `TransformAdpcmDecode` over 17,000 const words, one transform, no timer; 64 words | Does the ADPCM transform carry audio? | "maybe .25 second burst of static then immediately "connected to"" | PROVEN-POSITIVE | `TransformStart(TransformAdpcmDecode(StreamRegionSource(ptr,len), StreamKalimbaSink(3)))` carries audio: Bose's own recipe (sites 0x22F9B, 0x23083). The foundation of every generator since. | L5533, L5546 | asm words cmd dfu |
| probe105 | 10-02 u1 | Brown shaping, `malloc(128)`, 28 ms refill, no toggle | Refill loop with ADPCM | Press 1 "connected to" and no audio; press 2 "voice prompts on"; press 3 crashed and rebooted | NEGATIVE | Un-closed sources leak the common pmalloc pool; 0x1072 purges the tone buffer each refill, so press 1 was silent (disassembly, well-supported). | L5533, L5567, L5579 | asm words cmd dfu |
| probe106 | 10-02 u1 | 105 + `MessageFlushTask` toggle + `TransformFromSink` teardown + `0x1072` only when idle | Fix the leak with a teardown | Inconsistent across presses; crashed and rebooted; later crashing at rest | NEGATIVE | A transform keeps holding its sink after the source drains; TransformDisconnect does not free the source (disassembly). | L5533, L5567 | asm words cmd dfu |

### 4.7 Era E7: hook search, heap wall, unit 1 lost (probes 107-127)

u1. Dates 10-02 for builds; presses of 117-127 on 10-04. The 2026-10-04 flash table with timestamps is at L7420.

| probe | date, unit | what it changed | question | press result | verdict | key lesson | log | artefacts |
|---|---|---|---|---|---|---|---|---|
| probe107 | 10-02 u1 | One-shot `malloc(254)` ADPCM, 2000 Hz, 252 ms; clears port 3 first; 162 words; flashed cycle 91 with 0x1072 word b = 2 (18 dB quiet) | Does our brown ADPCM sound brown? | "ready to connect" (recorded only in the assemble_probe108.py docstring) | INCONCLUSIVE | Stock behaviour: with no phone connected a long press never reaches the hook at 0xAE0, so the cave never ran and no malloc happened. malloc(254) stayed unresolved until probe137 ("lost"). | L5600; assemble_probe108.py docstring | asm words cmd dfu |
| probe108 | 10-02 u1 | probe107 plus one read-only `SinkSlack(StreamKalimbaSink(3))` while armed and idle | Does an armed port 3 report writable room (direct-write design)? | Flashed at the same quiet setting; no result recorded. L5633 says three presses gave stock "ready to connect" (probably 107-109; hypothesis) | INCONCLUSIVE | The probe64-66 "zero slack" negatives never sent 0x1072 first, so they did not test an armed port. | L5674 (mention) | asm words cmd dfu |
| probe109 | 10-02 u1 | "Standalone gate" on hook 0xAE0: `MessageSendLater(600 ms)`, prompt id 0x0E; handler `KalimbaSendMessage(0x1072, 8000)` TRUE -> 0x13, FALSE -> 0x08 | Does the firmware load a DSP with nothing paired? | No result recorded (see probe108 note) | INCONCLUSIVE | Hook 0xAE0 only runs on EventUsrEnterPairing with a device slot connected; the hook was moved next. | L5657 (mention), L5633 | asm words cmd dfu |
| probe110 | 10-02 u1 | Hook moved to 0x107be (centre-button case 181, code 0xC5, event 0x4004; 2 operand bytes; 0xAE0 stock for the first time since probe10); replays fn_395dd; same question as 109; 64 words; flashed cycle 93 | Same, on a hook that "always fires" | No result recorded (L6525) | INCONCLUSIVE | The 0x107be hook was later found state-gated and was never confirmed to fire (L6686, L7505). | L5628, L6525 | asm words cmd dfu |
| probe111 | 10-02 u1 | Steal port 3 from the prompt DSP; 200 words (later 218); built | Does our ADPCM play on the prompt DSP's port 3? | Not flashed | NOT-FLASHED | Dropped as a strict subset of probe113 (L6186). Premise (prompt DSP on port 3) withdrawn at L8703. | L5676, L6186 | asm words cmd dfu |
| probe112 | 10-02 u1 | probe110 plus an else-branch speaking 0x16 "english"; 69 words; flashed cycle 94 | Same, with the "hook did not fire" ambiguity removed | No result recorded; dropped before a press | RETIRED | It could not answer its own question: KalimbaSendMessage TRUE means a .kap is loaded, not that the port is armed (L6191). | L5724, L6191 | asm words cmd dfu |
| probe113 | 10-02 u1 | Sustained brown noise: Bose's full 4-call teardown + SourceClose, 140 ms refill; 233 words; built | Leak-free sustain | Not flashed | NOT-FLASHED | Two assembler bugs found; the 639-word malloc never fit the proven heap. A "malloc(641) is PROVEN" header claim was later shown false (L9405). | L5750, L9902 | asm words cmd dfu |
| probe114 | 10-02 u1 (flashed cycle 95), reflashed 10-04 u1 | Write port 3 directly with `fn_12e1a` (SinkMap + SinkClaim), 16-bit PCM `noise_fill`; hook 0x107be; 154 words | Is port 3 writable directly? | 10-02, nothing connected: "Pressed center button with nothing connected. Nothing happened." 10-04, laptop connected, music paused, centre long press: "first long press = beep and LED flash; second long press = LED flash; and then it repeats that pattern"; no spoken id | INCONCLUSIVE | 10-02 test condition was invalid. Hook 0x107be never confirmed to fire. fn_12e1a on a connected sink returns 0 and memsets 256 words from data address 0 (L7332); that call is unsafe. | L5807, L6495, L7449 | asm words cmd dfu |
| probe115 | 10-02 u1 | `AUDIO_CHANNEL_A_AND_B` variant of probe90 on hook 0x107be; 141 words | Does channel A_AND_B make the codec route audible? | Not flashed | NOT-FLASHED | Dead without a press: the device opens `StreamAudioSink(3, 0, CHANNEL_A=0)` (PSKEY_USR40), so A_AND_B is not used (proven from the key). | L5857, L6266 | asm words cmd dfu |
| probe116 | 10-02 u1 | Sink-driven clock: does MESSAGE_MORE_SPACE arrive on a Kalimba port; no audio, one spoken answer; 145 words (the full design needed 291) | Can the sink clock the refill? | Not flashed | NOT-FLASHED | MORE_SPACE is useless as a clock on a transform-fed sink (L7390). The "262-word ceiling" it was measured against was wrong (197). | L6066 | asm words cmd dfu |
| probe117 | 10-02 built; 10-04 u1 | probe113 brown noise on hook 0xAE0; 220 words | Sustained brown noise on a proven hook | "ready to connect" (pairing long press, nothing connected): "this is just the stock behavior. It entered pairing mode and looked for a device trying to connect. I didn't hear anything else." | INCONCLUSIVE | Wrong conditions: the 0xAE0 hook needs a connected device and an A2DP-streaming latch (one-shot per session, L7229). | L6631, L7420 table | asm words cmd dfu |
| probe118 | 10-02 built; 10-04 u1 | probe113 audio on hook 0x10823 with an EventUsr-family gate; 225 words | Does 0x10823 fire standalone? | Wrong gesture (pairing, not the volume press): power-on "battery 100%" ... "mobile device not found - ready to connect", then "ready to connect" after each long press; owner twice: "That's not it. This is the stock behavior with no device connected. Nothing custom is happening." | NEGATIVE | The cave fired at power-on and reported its own bail id 0x09 ("mobile device not found", docstring of probe120); 0x10823 is mode-2 only (refuted on hardware, L7497). | L6767, L7420 table | asm words cmd dfu |
| probe119 | 10-02 u1 | probe118 cave plus one table byte (button-table entry 35 state mask 0x20 -> 0x22) | Does one byte make the centre button work in state 1? | Not flashed | NOT-FLASHED | Side effect of delivering EventUsrAnswer in state 1 was never resolved (L7062). | L6981, L7062 | asm words cmd dfu |
| probe120 | 10-02 u1 | probe118 gated on EventUsrEnterPairing alone; 223 words; built | Avoid the power-on fire | Never flashed | NOT-FLASHED | No result exists (L7455). No brown.dfu is in build/hook. | L7455 | asm words cmd |
| probe121 | 10-04 u1 | probe113 continuous brown noise in probe77's configuration (laptop connected, music paused), prompt call nopped; 220 words (power-on test) | Does the known-good configuration sustain noise? | Power-on: "battery 100%" and then it crashes but isn't wedged: "that happens when I power on. power on is always the first step." | NEGATIVE | The cave runs at cold power-on. The crash cause went through three accounts (port 3 teardown L7533, a prompt id L8327, neither L8529); newest: unexplained. Outside the proven window (L8241). | L7447, L8327, L8529 | asm words cmd dfu |
| probe122 | 10-04 u1 | probe104's five proven calls, generated brown buffer in place of the const pool, `malloc(320)` | Memory for a generated buffer? | "lost" | NEGATIVE | `malloc(320)` returned 0 while `0x1072` TRUE and `StreamKalimbaSink(3)` succeeded: port 3 can be armed; the heap is the wall (pools 138 reliable, 318 held, 642 held). | L7448, L7464 | asm words cmd dfu |
| probe123 | 10-04 u1 | Claim and write port 3 via `fn_12e1a` on a hook that reports | Probe114's question with spoken ids | Power up, play music, pause, long press: "english" on the first long press, "ready to connect" on the second; flaky, sometimes two "english"; without music = "ready to connect" | INCONCLUSIVE | The spoken id is void: the claim call memsets 256 words from data address 0 (L7332). Its gate behaviour independently confirms the 0xAE0 one-shot analysis (L7470). | L7450, L7332, L7470 | asm words cmd dfu |
| probe124 | none | No probe 124 exists (no files, no log mention) | n/a | n/a | RETIRED | Number skipped. | none | none |
| probe125 | 10-04 u1 | Brown noise on a volume short-press trigger (hook 0x10823); silent on success; 79 ms at -21 dBFS; 188 words | Does the volume press fire the cave? | "nothing at all" | INCONCLUSIVE | Silent on success, so it could not tell a dead hook from an inaudible burst (design fault). | L7451, L7526 | asm words cmd dfu |
| probe126 | 10-04 u1 | probe125 with success speaking 0x13; 189 words | Same, unambiguous | "nothing except a double LED flash" | NEGATIVE | The hook did not fire. 0x10823 is not a standalone hook. | L7452, L7527 | asm words cmd dfu |
| probe127 | 10-04 u1 (20:18) | probe126's audio design (gate on event 0x400d, `malloc(317)`, no teardown) on hook 0x18a04 inside fn_189fb, which sees every user event; three frames deep, `enterl -16`; 196 words | Standalone trigger that cannot be gated out | Power-on: wedged, second LED from the left flashing; afterwards no USB in any mode. UNIT 1 LOST at 20:23. | NEGATIVE (fatal) | Cause unestablished: stack overflow from `enterl -16` three frames deep (post-mortem) or live-const corruption, or neither (L8286). Eleven flashes, nine presses, 92 minutes, zero readbacks: docs/FLASH-PROTOCOL.md exists because of this. | L7453, L7537, L8286 | asm words cmd dfu |

### 4.8 Era E8: unit 2, generated noise and the gates (probes 128-137)

Unit 2 (flash numbers are not logged before probe139). Hook 0xAE0 (Bluetooth long press, a connected device and music paused unless stated).

| probe | date, unit | what it changed | question | press result | verdict | key lesson | log | artefacts |
|---|---|---|---|---|---|---|---|---|
| probe128 | 10-04 u2 | Generated ADPCM, `malloc(128)`, 126 bytes, rate 2000, PRIME 9; 154 words | Does self-generated audio play? | "~1/8 second of noise / a short 'shh'. very quiet." | PROVEN-POSITIVE | First self-generated audio; the predicted 126 ms matched; a non-8000 rate (2000 Hz) works. Region source: n words in, n bytes out (low 8 bits), two samples per byte. | L7833 | asm words cmd dfu rb:probe128_unit2_readback.dfu |
| probe129 | 10-04 u2; re-pressed 10-05 | Same burst with PRIME 9 -> 12 (one cave word, +10.7 dB content); 153 words | Is it louder? | "it was lower frequency but not louder." Re-press 10-05 (n = 2): "long press = short quiet shhhhh" | INCONCLUSIVE | First diagnosis (the 2000 Hz rate pushes energy below the driver) was withdrawn at L8078: a leak-free IMA accumulator drifts to DC at any rate. The chain is reliable (n = 2). | L7917, L8003, L8819, L8860 | asm words cmd dfu rb:probe129_repress_readback.dfu,probe129_unit2_readback.dfu |
| probe130 | 10-04 u2 | Bounded generator, `enterl -8`; 234 words, 55 outside the proven window | Does a bounded walk give a loud band? | Power-up: "we get 'battery one hundr....' and it gets cut off and reboots. crash on boot." Not bricked. | NEGATIVE | Zero words inside live const tables are still read at runtime; the cave is 197 words in 0x3E200..0x3E400. tools/caveguard.py written. Cause of the boot crash: window widening is the accepted account, frame depth is the alternative; unestablished (L8500). | L8153, L8241 | asm words cmd dfu rb:probe130_unit2_readback.dfu |
| probe131 | 10-05 u2 | probe129 + inlined gate `cmp AL,#2 ; ble OUT` (keep the cave off at boot); 159 words | Does a sinkState gate keep boot safe and the press working? | "battery 100% plays uncut" at power-on; "long press bluetooth crash but no wedge." | NEGATIVE | Boot-safe gate, crashing press. Interim theories withdrawn; real cause found at L8974: multi-word branch displacement is relative to the last word. | L8639, L8773 | asm words cmd dfu rb:probe131_unit2_readback.dfu |
| probe132 | 10-05 u2 | 131 with the gate `cmp AL,#3 ; bne OUT` (an attested encoding) | Is the two-word `ble` the culprit? | "uncut prompt + crash" | NEGATIVE | The encoding theory is withdrawn: a two-word `ble` exists nowhere in Bose's firmware but the crash persisted. | L8866, L8927 | asm words cmd dfu rb:probe132_unit2_readback.dfu |
| probe133 | 10-05 u2 | Same logic as 132 with the assembler's branch displacement fixed; 159 words | Does the corrected rule `target = a + ln - 1 + v` hold on hardware? | "silence" (the predicted pass) | PROVEN-POSITIVE | Branch rule validated on hardware; sinkState is unconditionally 2 at the 0xAE0 hook, so a gate for {3, 13} can never pass there. | L9058, L9089 | asm words cmd dfu rb:probe133_unit2_readback.dfu |
| probe134 | 10-05 u2 | Zero-net ADPCM generator at 2000 Hz (each 3-byte block nets zero), 175 words, no gate | Is bounded, zero-net noise loud? | "louder noise." | PROVEN-POSITIVE | THE PASS: in-band RMS -41.9 -> -9.3 dBFS, 88.1 percent of energy above 150 Hz. Still 126 ms. | L9213, L9373 | asm words cmd dfu rb snap |
| probe135 | 10-05 u2 | `malloc(641)`, 639-word payload (RMS -9.2 dBFS, 0.00 percent clipped); built | Longer burst | Not flashed; image renamed probe135_brown.dfu.UNPROVEN_MALLOC_DO_NOT_FLASH | NOT-FLASHED | The header claim "malloc(641) is PROVEN" was false (probes 105/106 used malloc(128); 111/113 were never flashed; 103's malloc(512) returned 0). A simulated result must never look like a hardware result in the record. Note: build/hook/snapshots/ holds probe135 `.flashed` copies although the log says it was never flashed; snapshots are taken before a flash (L9359), so the log wins. | L9405, L9411 | asm words cmd dfu:probe135_brown.dfu.UNPROVEN_MALLOC_DO_NOT_FLASH snap |
| probe136 | 10-05 u2 | `malloc(641)` with music PLAYING (642-word pool); 187 words; speaks 0x06 on refusal | Is the 642 pool allocatable during playback? | "lost" | NEGATIVE | The 642 pool is refused even in playback; contradicts probe82's apparent 512 success. A spoken id per failure path turns a negative into a fact. | L9463, L9644 | asm words cmd dfu rb snap |
| probe137 | 10-05 u2 | `malloc(254)` (252 ms), music paused (318 pool); 187 words | Is the 318 cell allocatable? | "lost" | NEGATIVE | One-shot heap route closed: the 318 pool is not allocatable (the stack arena, header word [09] = 316); only the 138 pool is. The refill loop is the only route. | L9730, L9867 | asm words cmd dfu rb snap |

### 4.9 Era E9: partition route and refill loops (probes 138-158)

Unit 2, flashes #14 to #34 (flash #17 was a stock recovery, #35 another). Probes 139-144 trigger on the Bluetooth long press (hook 0xAE0). Probes 145-158 use the same hook.

| probe | date, unit | what it changed | question | press result | verdict | key lesson | log | artefacts |
|---|---|---|---|---|---|---|---|---|
| probe138 | 10-06 u2 (no flash) | Not a cave: build/extfs/probe138.py asks the Bose Updater's local HTTP API `updateUsingEndpointUrl` to install a custom file on the ext partition | Is there a custom-URL install channel? | The updater refused: -1007 NO_DEVICE; nothing written; the speaker still held probe137 | NEGATIVE | `updateUsingEndpointUrl` is the cloud (NA-OTA) route; this product reports `useCloud = 0` (proven by the API replies). The ext partition parses (25 files of foreign prompt data) and vm.app reads it. | no field-log entry; docs/partition-route.md:215 | build/extfs/probe138.py (+ index_proxy.py, index_sniff.py) |
| probe139 | 10-06 u2 #14 | `PartitionGetInfo` census, part-0 control | Which partitions exist? | "battery 70%" (0x2d) | PROVEN-POSITIVE | No partition 1..4 is UNUSED; partition 2 exists with TYPE = 3 RAW_SERIAL. The control passed, so the ABI model is hardware-validated. XAP2: `bcc` is taken when AL >= val. | L9984, L10008 | asm words cmd dfu rb |
| probe140 | 10-06 u2 #15 | Overwrite partition 2, write an 8-word fsr_dfu1-marked pattern, digest SKIP, close | Does a runtime partition write work? | "battery 10%" (0x27) = pattern committed, STATE VALID | PROVEN-POSITIVE | The partition write works from a cave (16 bytes only ever committed; "dense" write unproven). The 2 MB erase wiped the ext language packs; restorability is disputed (L10074 says restorable from Minnow_3.0.3_ext_signed.xuv, L10325/L10390 say unrecoverable from our side; later text wins). | L10040, L10058 | asm words cmd dfu rb |
| probe141 | 10-06 u2 #16 | Staged 33,040 payload bytes in data_us blind windows and wrote them to partition 2 (about 33 KB) from the cave | Can a mountable .kap be written to p2? | Press outcome never established. DEVICE HARM: total audio output loss (no prompts, no music; Bluetooth, AVRCP, LEDs, chirp fine). Stock flash #17 restored everything. | NEGATIVE | Hypothesis (strong): the 0xAE0 hook also fires at power-on and the cave ran a multi-second erase plus write during audio init. Amendment L13679: the staged p2 content was a shifted stream, never a valid ROFS. Rule: a boot-safe gate before any side effect. | L10099, L10119, L10148, L13679 | asm words cmd dfu rb |
| probe142 | 10-06 u2 #18 | Play probe: mount p2, FileFind /brown.kap, KalimbaLoad, wire the DAC; gated on sinkState in {3, 13}; 148 words | Does the p2 file play? | Two silent presses | NEGATIVE | The gate can never pass: sinkState at the hook is 2 (and racy). | L10180, L10202, L10342 | asm words cmd dfu rb |
| probe143 | 10-06 u2 #19 | State-report diagnostic (spoken id = 0x27 + sinkState), then the unconditional chain | What is sinkState at the hook, and does the mount work? | "battery 30%" (state 2) then "voice prompts on" (mount returned FALSE) | NEGATIVE | State 2 at the hook (an earlier decode wrongly read it as 3, corrected inline); `PartitionMountFilesystem(1,2,LOWER)` returns FALSE. | L10217, L10237 | asm words cmd dfu rb |
| probe144 | 10-06 u2 #20 | FileFind unmounted first, then mount | Is the file visible without a mount? | "battery 30%" then "voice prompts on" again | NEGATIVE | File not visible, mount FALSE: partition route PARKED. Two indistinguishable causes: garbage written (the stream was shifted, L13686) or RAW_SERIAL refuses a mount. | L10260, L10279, L10353 | asm words cmd dfu rb |
| probe145 | 10-06 u2 #21 | Refill loop: 126 bytes every 110 ms via MessageSendLater, full teardown each tick; 54-word hand-assembled generator | Can a timer-driven loop sustain? | "Major progress but not there yet. There is noise playing. I wouldn't call it brown noise. Its almost like a modem that was dropped several octaves. It lasted for about 9 seconds and then stopped." | PROVEN-POSITIVE | First time a cave-owned TaskData dispatches from the main message loop and a teardown survives about 80 cycles (proven). The double-free diagnosis was refuted next; the 9 s number belongs to the pairing teardown (L11554). | L10450, L10524 | asm words cmd dfu rb verify |
| probe146 | 10-06 u2 #22 | probe145 without the per-tick SourceClose | Is the close the problem? | "Slightly shorter I think, maybe 6-7 seconds. Same quality of noise." | NEGATIVE | The double-free theory is dead. The 9 vs 6 s difference was ear-timing noise (L11296). | L10605, L10621 | asm words cmd dfu rb verify |
| probe147 | 10-06 u2 #23 | Rate-matched refill (216 samples per 108 ms); spoken 0x1F "muted" on failure | Does exact rate matching help? | "First time it had a brief sub 1 second burst of noise, then 5-6 seconds of silence and then 'muted'." | NEGATIVE | Exact rate match drains the pipe to empty and the DSP's end-of-tone detector disarms port 3 (codec_tones.asm reading, not pressed). The "pool dies at 5-6 s" part was superseded by L11554. | L10661, L10675 | asm words cmd dfu rb verify |
| probe148 | 10-07 u2 #24 | Completion-driven refill (MessageSinkTask 0x8026) with RAM TaskData and a 127 ms watchdog | Can the sink drive the loop? | One short blip of noise, then silence; nothing spoken | INCONCLUSIVE | Changed two variables and removed stage speech; the log says it yielded no attributable fact (L10755). | L10722, L10737 | asm words cmd dfu rb verify |
| probe149 | 10-07 u2 #25 | probe146 plus two spoken ids (0x3B after RegionSource, 0x3D after the transform) | Which stage fails at about 6 s? | About 6 s of noise, then 0x3D "noise cancellation only" | INCONCLUSIVE | Source allocation never fails (0x3B silent); the merged id left create vs start open. | L10763, L10830 | asm words cmd dfu rb verify |
| probe150 | 10-07 u2 #26 | Split 0x3D into create (0x3D) and start (0x39) | Create or start? | ~6 s of noise then 0x3D | NEGATIVE | `TransformAdpcmDecode` returned 0 (creation refused); the port was not refusing. | L10881, L10939 | asm words cmd dfu rb verify |
| probe151 | 10-07 u2 #27 | Store the transform handle; Stop + Disconnect it each tick | Does explicit teardown of the stored handle free the pool? | ~6 s of noise then 0x3D, unchanged | NEGATIVE | Decisive negative of the loop line (L11053 ledger). | L10953, L11042 | asm words cmd dfu rb verify |
| probe152 | 10-07 u2 #28 | Port-sink census: SinkSlack, SinkClaim(4), SinkMap, no flush | Can port 3 be written directly? | "battery 20%" | NEGATIVE | SinkSlack unusable; direct port write unproven, not disproven (long shot). | L11069, L11148 | asm words cmd dfu rb verify |
| probe153 | 10-07 u2 #29 | `StreamDisconnect(src, ksink)` both sides, then SourceClose with its bool read | Does SourceClose reclaim a region source? | 0x3A "heart rate not detected" within a second | NEGATIVE | SourceClose on a region source returns FALSE (source.h:124-126); the loop line is closed (L11282). | L11193, L11268 | asm words cmd dfu rb verify |
| probe154 | 10-07 u2 #30 | One-shot play of sbc_decoder.kap via FileFind + StreamFileSource | Can a file be streamed as audio? | "I think it said 'ended'", then on the second press "it definitely said 'ended'" | NEGATIVE | FileFind works from a cave (first ever, 3-argument form). StreamFileSource accepts only NARROW files (stream.h:300); .kap is WIDE. Only data_us and rphrases_us are narrow. Two probe141 machinery bugs found by the simulator. | L11302, L11396 | asm words cmd dfu rb verify |
| probe155 | 10-07 u2 #31 | FileFind NowSpeakTTS then data_us, StreamFileSource, ADPCM transform, one source | Does a file source give sustained audio with nothing repeating? | "noise. fairly loud. 7 seconds. no voice prompt after noise." | PROVEN-POSITIVE | First sustained generated audio. The 7 s limit was explained next entry: the pairing teardown. | L11457, L11535, L11554 | asm words cmd dfu rb verify |
| probe156 | 10-07 u2 #32 | State-free rebuild on a 5 s timer, no gate | Rebuild without state | Flashed and superseded without a press | RETIRED | It would not re-arm: the DSP disarms port 3 after about 30 ms empty at every seam and only a fresh 0x1072 re-arms. | L11590 | asm words cmd dfu verify |
| probe157 | 10-07 u2 #33 | Gate inside the rebuild; speak 0x3E if the gate returns FALSE; 7.5 s timer | Is the DSP still loaded at 7 s? | "7 seconds of noise and then "bluetooth off"" | PROVEN-POSITIVE | The DSP is gone about 7 s after the press: pairing teardown (fn_0d500 at 0x00ac2) runs before the 0xAE0 hook. The 6-9 s endings of probes 145-157 are attributed to it (the DSP being gone at 7 s is proven by the bool; the fn_0d500 attribution and its extension to 145-156 are well-supported; probe104's 4.25 s was by design; probes 160-171 failed differently). Skipping the back-call cannot help. | L11612, L11670, L11697 | asm words cmd dfu rb verify |
| probe158 | 10-07 u2 #34 | On gate FALSE: FileFind + KalimbaLoad + re-arm; 9.5 s timer | Can the cave reload the DSP and continue? | "noise for 5 seconds and then it wedged. I can't reboot it." | NEGATIVE | Recovery needed flash #35: POWER + VOICE-ASSISTANT did not work from this wedge; unplug USB, hold POWER about 20 s, replug, press POWER did (FLASH-PROTOCOL.md "Recovery"). | L11717, L11798, L11804 | asm words cmd dfu rb verify |

### 4.10 Era E10: DSP reload and the wedge bisect (probes 159-171)

All 10-08, u2. Trigger: Bluetooth long press, laptop connected, music paused.

| probe | date, unit | what it changed | question | press result | verdict | key lesson | log | artefacts |
|---|---|---|---|---|---|---|---|---|
| probe159 | 10-08 u2 #36 | Bare reload, cave owns the DSP mailbox | Can the cave reload and own the DSP? | Flashed and superseded without a press | RETIRED | It would have powered the DSP off on every message. Stock loader sends nothing after KalimbaLoad; all configuration happens on MUSIC_READY 0x1000 and PARAMS_LOADED 0x1015. docs/kalimba-disasm.md "sbc_decoder has no 0x7000/GO" is wrong (L11966). | L11861, L11951 | asm words cmd dfu rb verify |
| probe160 | 10-08 u2 #37 | Bare reload, KalimbaPowerOff only on 0x1000; speaks 0x14 | Is a bare reload clean? | "noise ~7 s, then ~3 s later 'auto off disabled'" | PROVEN-POSITIVE | The bare reload is clean; hypothesis H1 dead. | L12012, L12054 | asm words cmd dfu rb verify |
| probe161 | 10-08 u2 #38 | Answer MUSIC_READY with SETPLUGIN(1) + LOADPARAMS(0x2270); speak 0x12 on PARAMS_LOADED | Does the reloaded DSP accept the stock configuration? | "approximately two seconds of noise, approximately 5 seconds of silence, and then "voice prompts on"" | PROVEN-POSITIVE | PARAMS_LOADED came back; cavesim predicted it. | L12076, L12135 | asm words cmd dfu rb verify |
| probe161s | 10-08 u2 #39 | probe161 plus 221 words in 7 stubbed AVRCP-browse functions (code region) | Is the code region usable for cave code? | "noise for a while, then silence, then "voice prompts on""; checks "1 is normal", "2 all things worked." | PROVEN-POSITIVE | The 221 code-region words and 7 stubs are inert at boot, in normal use and through the DSP reload; usable from probe162 (verify.md V8: not refuted, two citations weak). | L12162, L12198, L12208 | asm words cmd dfu rb log |
| probe162 | 10-08 u2 #40 | DAC rewire + 0x1072 + GO + chunk build + 9.5 s tick on PARAMS_LOADED | Does the reloaded DSP play our chunk? | "noise for a slow 9 count then silence"; then a WEDGE; recovered by flash #41 | NEGATIVE | The wedge was the 9.5 s re-tick (bisect inference, L12423). First build failed preflight (3-word bra, L12219). | L12217, L12254, L12268 | asm words cmd dfu rb log |
| probe163 | 10-08 u2 #42 | Rewire alone, then teardown; speaks 0x20 | Step 1 of the wedge bisect | "9 count of noise then "unmuted"" | PROVEN-POSITIVE | The DAC rewire is clean. | L12287, L12317 | asm words cmd dfu rb log |
| probe164 | 10-08 u2 #43 | Rewire + 0x1072 + GO, then teardown; speaks 0x15 | Step 2 | "9 count of noise, silence, then "auto off enabled"" | PROVEN-POSITIVE | 0x1072 and GO are clean. | L12329, L12368 | asm words cmd dfu rb log |
| probe165 | 10-08 u2 #44 | Chunk build on the running DSP, no re-tick; speaks 0x16 | Step 3 | "noise, silence, then "english"" | INCONCLUSIVE | The build is clean but the second noise was inaudible; probe162's wedge is the re-tick. | L12380, L12416 | asm words cmd dfu rb log |
| probe166 | 10-08 u2 #45 | + stock sample-rate messages 0x1070/0x1071 at 4800 before GO; 0x22 | Is a missing rate message the silence? | "noise, silence, "conference call", no second noise." | NEGATIVE | Rates accepted, still inaudible. | L12429, L12475 | asm words cmd dfu rb log |
| probe167 | 10-08 u2 #46 | + the stock DSP volume (fn_23229); 0x1E | Is volume the silence? | "noise, silence, speaker restarts." | NEGATIVE | A Panic in the fn_23229 chain (cold boot clean). | L12486, L12536 | asm words cmd dfu rb log |
| probe168 | 10-08 u2 #47 | probe166 + one plain 0x1002 volume message; 0x3D | Same with a safe message | "noise, silence, "noise cancellation only", no second noise." | NEGATIVE | Volume accepted, still inaudible. | L12551, L12596 | asm words cmd dfu rb log |
| probe169 | 10-08 u2 #48 | + output-device-type message 0x10a0; 0x39 | Last pre-GO message | "noise, silence, "heart rate detected", no second noise" | NEGATIVE | Accepted, still inaudible. | L12609, L12679 | asm words cmd dfu rb log |
| probe170 | 10-08 u2 #49 | + SetMode 0x1001 FULLPROC; 0x3A | Last pre-GO message | "noise, silence, "heart rate not detected", no second noise." | NEGATIVE | Accepted, still inaudible. | L12703, L12756 | asm words cmd dfu rb log |
| probe171 | 10-08 u2 #50 | + DAC hardware gain (fn_1f512), which the connect leaves at -45 dB; 0x3C | Is the gain the silence? | "noise, silence, "adjust left airbud", no second noise." | NEGATIVE | Gain set, still inaudible. Prime remaining suspect: no codec input after the teardown (hypothesis from ADK source, L12849). The pivot to a hook without the pairing teardown removed the need. | L12783, L12836, L12845 | asm words cmd dfu rb log |

### 4.11 Era E11: centre long press, one chunk per press, the level knob (probes 172-178)

Unit 2. Hook 0x00e46 (centre long press, event 0x4004), stock 0xAE0 untouched.

| probe | date, unit | what it changed | question | press result | verdict | key lesson | log | artefacts |
|---|---|---|---|---|---|---|---|---|
| probe172 | 10-08 u2 #51 | Trigger-only: hook 0x00e46 (operand bytes 01 7c b3 -> 04 d4 d5), 21 words, speaks 0x17 | Does a centre long press reach a hook that does not enter pairing? | "to select english press and hold the multifunction button" and nothing else | PROVEN-POSITIVE | The trigger works and the event is swallowed with no pairing teardown. verify.md V0: "swallowed cleanly" is overstated and "0x4004 only in states 2/3/13" is false; boot safety well-supported. | L12867, L12923 | asm words cmd dfu rb log |
| probe173 | 10-08 u2 #52 | Port-3 chunk loop on the centre hook, 9.5 s tick, 5 chunks | Does a loop sustain on the new hook? | "noise, then differeent noise that played forever, way more than 45 seconds. I pushed lots of button sto get it to stop eventually. no voice prompts. I also had to plug and unplug a few times to get the device to stop making very loud harsh noise." | NEGATIVE | A design error (re-arm during a running chunk); rules at L13037 (memory note csr8670-port3-chunk-rules). verify.md V3: the attribution to a 0x1072 re-send is unestablished; cause of "harsh" unknown. | L12944, L13002 | asm words cmd dfu rb log |
| probe174 | 10-08 flash, 10-09 press u2 #53 | One chunk per press, busy check first; a second press STOPs via Stop/Disconnect/StreamDisconnect and speaks | Sustain past 7 s; can the stop work? | "First press long noise. Terrible quality, very abrasive and loud, kept going well past 7 seconds. Second press crash. Speaker is ok and booted after crash." | PROVEN-POSITIVE (sustain); NEGATIVE (stop) | Sustain proven on this hook (the 7 s cut-off was the pairing teardown). Crash cause found statically: TransformFromSink returns the downstream node (flag 0x40) and TransformStop on it Panics 0x4030 (L13688; well-supported, never pressed). | L13051, L13112, L13688 | asm words cmd dfu rb log |
| probe175 | 10-09 u2 #54 | Same with a SILENT stop | Is it the spoken id that crashes? | Same: long noise, second press crash | NEGATIVE | The teardown itself crashes from the cave; transform-teardown STOP retired. verify.md V3: "which call" not bisected; "Panic" is an inference from a restart. | L13142, L13177 | asm words cmd dfu rb log |
| probe176 | 10-09 u2 #55 | A short chunk of rphrases_us (10,486 bytes) that ends by itself; a busy press does nothing | Does the stock clean up port 3 when the DSP reports end of tone? | "call from unknown" (0x1B) on press 1 | NEGATIVE | `FileFind(NowSpeakTTS, "rphrases_us")` returned FILE_NONE; the file lives under tts/. Amendment L13704: rphrases_us is a phoneme script, not a chunk directory. | L13203, L13244 | asm words cmd dfu rb log |
| probe177 | 10-09 u2 #56 | probe176 with the right directory (`tts/rphrases_us`) | Does a self-ending chunk cycle press after press? | Result 1 (music paused): "first press 3 seconds of noise that stops on its own / second press "bluetooth off" and a beep / speaker works fine". Result 2 (music playing): "first Centre long press -> ~3 s of loud noise over the music, stops by itself. / second Centre long press -> ~12 s of noise over the music lower pitch, same volume, stops by itself. / noise does not appear to be impacted by music volume or volume buttons. always loud." | PROVEN-POSITIVE | The start-only cycle works press after press (n = 2; "press after press" for N > 2 unproven, verify.md V1). With music paused the stock unloads the DSP after the tone (press 2 "bluetooth off", n = 1). The first chunk ran at about 8 kHz speed, the second at 2 kHz; the rate latch is not understood (verify.md V5). data_us = about 55 s at 8 kHz or 220 s at 2 kHz. | L13250, L13286, L13315 | asm words cmd dfu rb log |
| probe178 | 10-09 flash, 10-10 press u2 #57 | probe177 with `0x1072` word b = 2 | Is the level ours? | "Quieter on Both." | PROVEN-POSITIVE | Word b = 2 is honoured at once, on both presses (the first and the second chunk; n = 2); the rate is the odd one out and its cause is unknown (verify.md V5). The level knob is ours (b = 0 loud, b = 2 quiet). The "18 dB" is arithmetic, not measured (verify.md V4). ON THE SPEAKER NOW (build/hook/FLASHED). | L13350, L13394 | asm words cmd dfu rb log |

### 4.12 Era E12: built and gated offline, never flashed (probes 179-181)

Offline, 2026-10-10, owner away. Plans and outcome tables: docs/deep/offline-2026-10-10/DESIGN.md; first-day script: docs/RETURN-CHECKLIST.md.

| probe | date, unit | what it changed | question | press result | verdict | key lesson | log | artefacts |
|---|---|---|---|---|---|---|---|---|
| probe179 | 10-10 none | probe178 plus a bounded poll loop (3 chunks, then speaks 0x26 "ended"), no STOP; sha256 a31e2fe8...cd276 | Does a tick delivered from the 0x00e46 hook run; does the busy read work; does the DSP stay up between chunks? | NOT-FLASHED | NOT-FLASHED | Unproven by design (L13463-13467). Zero-flash Step 0 on probe178 comes first (RETURN-CHECKLIST). | L13417 | asm words cmd dfu |
| probe180 | 10-10 none | Unbounded loop with a constant poll id 0x12 and a MessageCancelFirst-first STOP; sha256 f4130846...b3ba | Does MessageCancelFirst work as a STOP from a cave? | NOT-FLASHED | NOT-FLASHED | 25 world-model scenarios pass; MessageCancelFirst has never run on hardware. Docstring wording "fault" corrected by the amendment at L13694. | L13490, L13694 | asm words cmd dfu gate |
| probe181 | 10-10 none | probe180 with 0x1072 rate a = 8000; sha256 d76bef1d...bd53 | What does a = 8000 do to the first-chunk rate quirk? | NOT-FLASHED | NOT-FLASHED | Predicts 2.62 s chunks and 0.4 s seams. The rate-quirk conclusion is a bet probe181 settles (verify.md V5). Flash only after 179 and 180 are recorded. | L13570 | asm words cmd dfu gate |

## 5. Other flashes (not probe numbers)

These images are also on the evidence trail. Flash numbers (#N) are unit 2; unit 1 cycles are not numbered here.

| when | unit | image | what / why | result | log |
|---|---|---|---|---|---|
| 09-24 | u1 | official Minnow_3.0.3 | Restore after probe1 | OK; Main 3.0.3.6546 | firmware/bose/probe/probe1_run.log:19-33 |
| 09-26 | u1 | official 3.0.3 (x3) | Restores after probes 2, 3, 6; each readback byte-identical to baseline | OK | probe_run2, probe_run4 |
| 09-27 night | u1 | official 3.0.3 | Revert after probe11 (prompts dead); fs readback 0 diffs vs official | OK | probe_run9_2026-09-27.log |
| 09-29 | u1 | official 3.0.3 ("stock control") | Control for probe25 | PROVEN-POSITIVE (see 4.2) | L313 |
| 10-01 | u1 | probe85 reflash | Safe baseline after probe92 was pulled (cycle 75, readback 0 of 975,168 differ, 60 cave words) | OK | L4684 |
| 10-01 | u1 | probe77 reflash | Phone connected, music PAUSED: a long clean tone; shows the A2DP decoder stays loaded while connected and idle | PROVEN-POSITIVE | L5318 |
| 10-04 | u1 | official 3.0.3 | Stock baseline at 19:06 between probe118 and probe77, offered by the owner to "verify that 100%" | OK | L7420 table |
| 10-04 | u1 | probe77 reflash | Control still passes on this firmware: "tone plays" | PROVEN-POSITIVE | L7420 table |
| 10-04 | u2 | stock 1.1.3.6165 -> 3.0.3.6546 | Unit 2 bring-up; readback gate proven both directions; the unit's fs header reads as erased flash (factory image never went through DFU, hypothesis). Stack byte-identical between 1.1.3 and 3.0.3. | OK | L7577 |
| 10-04 | u2 | probe77 | Control on unit 2 | "long clean tone" (3 for 3 across two units) | L7664, L7724 |
| 10-05 | u2 | probe129 reflash | Re-flash for attribution, zero new code | "long press = short quiet shhhhh" | L8819, L8860 |
| 10-06 | u2 | stock #17 | Recovery after probe141's total audio loss; partition 2 still held probe141's content (the stock DFU does not cover p2) | Speaker normal (verify.md V11: "self-authored fs tolerated" not backed, content was not a valid fs) | L10148 |
| 10-08 | u2 | stock #35 | Recovery after probe158's wedge | OK; standing recovery order recorded | L11804, L11849 |
| 10-08 | u2 | stock #41 | Recovery after probe162's wedge (unplug, hold POWER ~20 s, replug, press POWER); transcript build/hook/stock_recovery_20261008b_flash.log and readback stock_recovery_20261008b_readback.dfu (the other two stock_recovery*_readback.dfu files in build/hook probably belong to #17 and #35; hypothesis) | OK; 0 of 975,168 fs bytes differ from official | L12268, L12274 |

Quarantined images that are not probes: RADIOACTIVE_DO_NOT_FLASH/build_hook/roundtrip.dfu (sha256 equals the official stock image, an identity round trip), rt_mine.dfu (same hash as probe11c_rumble.dfu), claude_probe22__SHA256_6194....dfu (a probe22 build from the unverified earlier narrative; not the probe22 the owner pressed, which is probe22_scan.dfu, built 09-29 06:54), and the fsedit/dfusign test images under build_fsedit, build_fsedit_t and build_sign. RADIOACTIVE_DO_NOT_FLASH/MANIFEST.sha256 holds every hash. Never flash anything from that folder.

## 6. Designed, not built (probes 182-186)

Specified in docs/deep/offline-2026-10-10/DESIGN.md (line numbers are in that file). None has an assembler. (2026-10-12: probe184 now has one; see section 11.)

| probe | what it would do | gate |
|---|---|---|
| probe182 | READ-ONLY census of the file-source window; no port, no write (DESIGN.md:245) | none beyond the normal flash gates |
| probe183 | Optional READ-ONLY partition-2 census, `PartitionGetInfo` only (DESIGN.md:260) | optional |
| probe184 | The one p2 write: the brown ROFS, FIRST = 9 (DESIGN.md:269; docs/deep/offline-2026-10-10/payload-184.md) | OWNER GO-AHEAD REQUIRED: one erase of the only unit; misaligned-erase brick risk not excluded (RETURN-CHECKLIST D1: no for now) |
| probe185a / 185b | The loop pointed at our file (one change: the carried name); 185b is the mount fallback (DESIGN.md:291, 301) | after 184 |
| probe186 | Level from the volume buttons (DESIGN.md:310) | after the loop |

## 7. Lineage: which probe descends from which

Read each line left to right; "x" marks a dead end or a void result, "(n)" a note under the line. Every arrow is "built on the result or code of". Evidence for each step is in the row of the later probe.

### 7.1 The trigger and the prompt lever (hook at 0xAE0)

    22 -> 23x -> 24x          wrong button; void
    25 -> stock control -> 26 -> 27      the live site found; Bluetooth hold identified
    27 -> 28 (cave executes, payload crashes) -> 29 (first working cave)
    29 -> 30x (request from inside the cave crashes) -> 31 (id change at the stock site works)
    31 -> 32 -> 33 -> 34x -> 35x (trampoline cannot carry a real request) -> 36x (global 0x70)
    36x -> 37 (id in AL, stock makes the deep call: THE LEVER) -> 38 (64-id sweep) -> catalogue
    37 -> 40 -> 41 -> 42x -> 43 -> 44x -> 45 (Bose's own 0x4946 runs from a cave)

### 7.2 Trap calls and the audio route

    39x (nine calls at once) -> 40 (one trap) -> 41 -> 42x -> 43 -> 44x -> 45
    45 -> 46x -> 47x   (void: KalimbaPowerOff) -> trap-numbering finding (L2161)
    52x -> 53x -> 54 -> 55 -> 56 -> 57 -> 58x  (wrong traps, then too many calls)
    58x -> 59 -> 60 -> 61 -> 62 -> 63x (StreamConnect to the codec sink) -> 64x -> 65x -> 66x
    63x -> 67 (StreamConnect to a Kalimba sink survives) -> 74 (ringtone to port 3) -> 75 (tone with music)
    75 -> 76x (silent id) -> 77 (prompt call deleted: the long tone)
    77 -> 85 (cave loads the DSP itself) -> 93 -> 94 -> 95 -> 96x/97x (DAC takeover wedges)
    77 -> 98 -> 99 -> 100x (timers; the prompt owns port 3) -> 101x -> 102 (retracted) -> 103x -> 104 (ADPCM carries audio)
    104 -> 105x -> 106x (refill leaks) -> 107..127 (heap wall, hook search) -> 128 (first generated audio)

### 7.3 The generator and the cave rules

    55/58 (LFSR) -> 68x -> 69x -> 70 -> 71 -> 72x -> 73x -> 78x -> 79x -> 80x -> 81 (frame slots k-2, k-1 reserved)
    81 -> 82 -> 83 (square waves; heap and music problems) -> 101/102 (noise_fill into a region source, retracted)
    104 -> 122x (malloc(320) = 0) -> 128 (126 bytes, PRIME 9) -> 129 (PRIME 12: quiet; IMA accumulator) -> 130x (bounded walk; boot crash, window)
    130x -> 131x -> 132x -> 133 (branch displacement rule) -> 134 (zero-net blocks: loud) -> 135 (not flashed) -> 136x -> 137x (heap closed)
    134 -> 145 (refill loop) ... -> 155 (file source) -> 177 (self-ending chunk)

### 7.4 The long chain to the current state

    172 -> 173x -> 174 -> 175x -> 176x -> 177 -> 178 -> 179 -> 180 -> 181

| step | what changed | why |
|---|---|---|
| 172 | Hook moved to the centre long press at 0x00e46; cave only speaks | The 0xAE0 hook runs behind the pairing teardown that kills the DSP at about 7 s (probe157). |
| 173 | First port-3 chunk loop on the new hook, 9.5 s tick, 5 chunks | Test sustain; failed as a runaway (re-arm during a running chunk). |
| 174 | One chunk per press, busy check first, second press STOPs | Remove the loop; sustain past 7 s worked, the stop press crashed. |
| 175 | Silent stop | Bisect the crash: the teardown itself panics (TransformStop on the downstream node). |
| 176 | Short self-ending chunk from rphrases_us, no stop path | Drop the STOP entirely; the file lookup used the wrong directory. |
| 177 | Directory fixed (tts/rphrases_us) | The start-only cycle works press after press; rate quirk and "always loud" observed. |
| 178 | 0x1072 word b = 2 | The level knob is ours ("Quieter on Both"). On the speaker now. |
| 179 | Bounded poll loop (3 chunks, then "ended"), no STOP | Learn whether ticks arrive from this hook, whether the busy read works, how the DSP behaves between chunks. NOT flashed. |
| 180 | Unbounded loop, constant poll id, MessageCancelFirst-first STOP | A usable stop without touching the transform. NOT flashed. |
| 181 | 0x1072 rate a = 8000 | Settle the first-chunk rate quirk. NOT flashed. |

### 7.5 Other lines

    Hook sites: 0xAE0 (10-109, 117, 121-123, 128-171) -> 0x107be (110, 112, 114, 115) -> 0x10823 (118, 120, 125, 126)
                -> 0x18a04 inside fn_189fb, three frames deep (127; unit 1 lost) -> back to 0xAE0 (128) -> 0x00e46 (172-181)
    Refill loops: 105 -> 106 -> 145 -> 146 -> 147 -> 148 -> 149 -> 150 -> 151 -> 152 -> 153 (SourceClose FALSE; loop line closed)
                -> 154 -> 155 (file source) -> 156 -> 157 (the 7 s is the pairing teardown) -> 158x
    DSP reload (stock load order): 85 -> 93 -> 157 -> 158x -> 159 -> 160 -> 161 -> 161s -> 162x -> 163 -> 164 -> 165 -> 166x .. 171x (inaudible; parked at 172)
    Partition 2: 138 (updater: no) -> 139 -> 140 -> 141x (device harm) -> stock #17 -> 142x -> 143x -> 144x -> parked -> 183/184 designed
    Speech lever: 48 -> 49 -> 50 -> 51 (closed by owner decision)
    Safety incidents: 91 (wedge) -> 96/97 (wedge) -> 127 (unit 1 lost) -> 130 (boot crash) -> 141 (audio loss) -> 158, 162 (wedges) -> 173 (runaway) -> 174/175 (stop crash)
    Signature work: 1 -> 2 -> 3 -> 4 -> 5 -> A1 -> A1r -> 6 -> 8 -> 9 -> 10

## 8. Probes that were never flashed (or never pressed)

### 8.1 Built, never flashed

| probe | why not | log |
|---|---|---|
| B1 | Cross-version stack swap is vacuous (stacks identical); offline only | probe_run3_2026-09-26.log |
| probe12 | Self-verification found three wrong bsr targets (run log, 09-28); a "v2, fixed" assembler exists, flash status unknown | probe_run10_2026-09-28.log |
| probe111 | Subset of probe113; premise withdrawn | L6186, L9902 |
| probe113 | Dropped; malloc(641) never fit | L5750, L9902 |
| probe115 | Dead without a press: the device opens channel A | L6266 |
| probe116 | MORE_SPACE is useless as a clock | L6066, L7390 |
| probe119 | Side effect of the table byte unresolved | L7062 |
| probe120 | Superseded; no brown.dfu | L7455 |
| probe135 | malloc(641) unproven; quarantined | L9405 |
| probe179, probe180, probe181 | Offline, owner away (2026-10-10); flash after Step 0 and in order | L13417, L13490, L13570 |

Designed only (no assembler): probes 182, 183, 184, 185a, 185b, 186 (section 6). Update 2026-10-12: probe184 and probe184a now have assemblers (built offline, NOT flashed) and probes 181p and 187 are new: section 11.

### 8.2 Flashed, never pressed (or no result recorded)

| probe | note | log |
|---|---|---|
| probe51 | Owner redirected away from the speech route | L1899 |
| probes 54, 55, 56, 57 | Superseded while the owner was away; 55 and 56 had wrong traps | L2043-L2190 |
| probe84 | Superseded by probe85 | L4147 |
| probe87 | Image exists; no section; superseded by 88 (flash status unknown) | L4260 |
| probe92 | Pulled: stack theory wrong | L4659 |
| probes 108, 109, 110, 112 | Flashed 10-02; no recorded result (107-109 probably stock "ready to connect") | L5633, L6525 |
| probe141 | Pressed, but the press outcome was never established (device harm) | L10119 |
| probe156, probe159 | Flashed and superseded without a press | L11590, L11951 |

### 8.3 Unknown

probe7 (image only), probes 10clone, 13, 14, 15, 15c, 16, 17, 17b, 18a, 18c, 19, 20, 21 (images and assemblers exist; flashed status and results are not in any verified record), and probe124 (the number was never used).

## 9. Unit 1 versus unit 2

| | unit 1 | unit 2 |
|---|---|---|
| Role | Probes 1-127 | Probes 128-178 |
| Dates | 2026-09-24 to 2026-10-04 20:23 | from 2026-10-04 |
| Firmware | Bose 3.0.3.6546 from the first dump | arrived on stock 1.1.3.6165, upgraded to 3.0.3.6546 on 2026-10-04 (L7577) |
| End state | LOST at probe127: no USB enumeration in any mode (PSKEY_USB_VM_CONTROL = 1, so a dead app means no USB); cause not established | alive; probe178 on it (build/hook/FLASHED, cycle 57 on unit 2) |
| Shared facts | Stack byte-identical between releases; PSKEY_PMALLOC_APP, PMALLOC_EXTRA, USR40 and USB_VM_CONTROL identical on both units (L7605-7611); the control probe77 passes on both | |
| Differences | The earliest dump had the fs header | The fs header reads as erased flash (factory image never went through DFU; hypothesis); ext partition 1.1.3 |
| Evidence | build/hook/readback_probe*.bin (22-56), probe*_readback.dfu | build/hook/probe*_unit2_readback.dfu (77, 128-133), probe*_readback.dfu (134 onward), probe*_flash.log (161 onward) |

Rules that follow from the loss: docs/FLASH-PROTOCOL.md (foreground, read every line, readback before the next flash, update FLASHED first); docs/POST-MORTEM-2026-10-04.md; memory note csr8670-flash-protocol.

## 10. Verification record, disagreements and gaps

### 10.1 What was checked, and how

| Check | Result |
|---|---|
| Coverage | Every probe number 1 to 181 has a row (18 as 18a, 18b, 18c; 124 as "never existed"; 182-186 in section 6); plus the variants 10clone, 11b, 11c, 15b, 15c, 17b, 161s and the route probes A1, A1r, B1. |
| Cited line numbers | 339 field-log line citations in the log column were compared with docs/field-log.md by script: 324 sit at or within a few lines of an entry that names the probe; the other 15 point at retraction, summary or amendment entries that cover several probes (L453, L3004, L4659, L5533, L5567, L5633, L5674, L6525, L7420, L7537, L10353, L11554, L11697, L11804, L13688) and were read by hand. |
| Quoted owner words | 130 quoted strings in the "press result" column were machine-compared (whitespace, case and quote style normalised) with docs/field-log.md, the probe run logs and the assembler docstrings: 126 are verbatim; the other 4 are artefacts of nested quotation marks in the table cell, checked by eye (probe20 is verbatim from the docstring of assemble_probe21.py). Paraphrases that had been put in quotation marks were reworded. |
| Cave word counts | The "N words" figures in the "what changed" column were compared with the field-log entry (or with L8250-8256, the audit list); the exceptions (probes 10, 11, 53, 77, 78, 93 and 113) were checked against run logs and the later entry that restates them. |
| Rows read against the primary text | About 90 rows were read against the field-log text itself, not the digest: probes 22-54 (all, from the verbatim result blocks), 57, 59, 63, 67, 77, 81, 85, 91, 96, 97, 103-110, 112, 114, 117, 118, 121, 123, 125-135, 139-147, 149, 154, 155, 157, 158, 160, 161, 161s, 173, 174, 177, 178, plus the stock control. |
| Artefact column | Generated from directory listings of build/hook, firmware/bose/probe and RADIOACTIVE_DO_NOT_FLASH/build_hook at build time; no file was opened. |
| Repository tools | `python tools/doclinks.py` reports no finding for this file; `python tools/docaudit.py` passes (46 checks, 0 failing). |

### 10.2 Mismatches found and fixed (the digests timeline-A/B/C and the file map were wrong or incomplete)

| # | What the digest said | What the primary source says | Row |
|---|---|---|---|
| 1 | probe138 has "no section"; number unused | probe138 is build/extfs/probe138.py, run on 2026-10-06: the Bose Updater refused the custom-URL request (-1007 NO_DEVICE) and nothing was written. It is described in docs/partition-route.md:215, not in the field log. | probe138 |
| 2 | probe87 was "never built" | build/hook has assemble_probe87.py, words, cmd and a 1,761,440-byte DFU; there is no press, no log section and no readback, so it was built and superseded; whether it was flashed is unknown. | probe87 |
| 3 | Results of probes 107, 108, 109 unknown (timeline-B O11) | The docstring of build/hook/assemble_probe108.py records probe107's press: "ready to connect" (stock; the cave never ran because no phone was connected). L5633 adds that three presses gave stock "ready to connect"; 108 and 109 are probably two of them (hypothesis). | probes 107-109 |
| 4 | probe104 quoted as "maybe .25 s burst of static" | Verbatim: "maybe .25 second burst of static then immediately 'connected to'" (L5542). | probe104 |
| 5 | probe146 quoted as "Slightly shorter, maybe 6-7 seconds." | Verbatim at L10621: "Slightly shorter I think, maybe 6-7 seconds. Same quality of noise." | probe146 |
| 6 | probe127 "hooked three frames deep" with no site | The docstring names the hook: 0x18a04 inside fn_189fb (sees every user event), gated on event 0x400d, malloc(317), `enterl -16`. | probe127 |
| 7 | probes 125 and 126 hook not stated | Both used 0x10823, the mode-2 exit (probe125 docstring line 35; refuted on hardware, L7497, and in the docstring of probe127). | probes 125-126 |
| 8 | probes 51, 54, 55, 56 "untested" | Readbacks readback_probe51/54/55/56.bin exist and the entries say "Thirty-second / thirty-fifth ... accept-and-program cycle": they were flashed and never pressed. | probes 51-56 |
| 9 | Dates of probes 12-21 not given | No dated record. The file times of the quarantined DFUs give the build dates (09-27 20:13 for probe12 to 09-28 21:43 for probe21); the flash dates are unknown. | probes 12-21 |
| 10 | probe142 result line given as the entry line | The heading is L10180 (flash); the "two silent presses" are stated at L10202 and L10342. | probe142 |
| 11 | probe96's recovery (POWER + VOICE ASSISTANT) presented as the recovery | Superseded: it did not recover the 2026-10-08 wedge (L11821); the standing order is in docs/FLASH-PROTOCOL.md "Recovery". | probes 96, 158 |
| 12 | The file map (inventory-build.md) says build/hook/snapshots/ copies are "written by flash_probe at flash time" | No tool in tools/ writes them; L9359 says they were snapshotted by hand before the flash, and probe135 has one although it was never flashed. | probes 134-137 |
| 13 | The file map lists probe51/54/55/56 readbacks without saying what they prove | They prove the images were flashed (section 8.2); the entries say they were never pressed. | probes 51-56 |

### 10.3 Disagreements between sources that remain (the newer entry wins; stated here so nobody has to rediscover them)

| Topic | Disagreement | Which is newer or better |
|---|---|---|
| Cave size | 262 words (assemblers 2026-10-02 to 10-05), 197 words (proven window), 182 usable code words after 15 connectors | 197 and 182 (L8196, L9131); every earlier "fits/does not fit" statement used 262. |
| probe130 boot crash | Live-table corruption from 55 words outside the window (L8153, L9907) versus frame depth 62/70/80 (L8500) | Unestablished (L8500-8586); the window rule stands regardless (cave-window memory note). |
| probe121 crash | Port 3 teardown (L7533), a prompt id (L8327), neither (L8529) | Newest: unexplained. |
| Unit 1 loss | Stack overflow from `enterl -16` (post-mortem) versus live-const corruption versus neither | Unestablished (L8286). |
| Heap | probe82 "512 words" versus probe103's `malloc(512) = 0` | probe82's number was probably 256 misheard (L9758); the proven grant is 128 words. |
| Ext language packs after probe140 | Restorable from Minnow_3.0.3_ext_signed.xuv (L10074) versus unrecoverable from our side (L10325, L10390) | Later text (L10390) wins; owner decision. |
| Wedge recovery | POWER + VOICE ASSISTANT is app-independent (L4956) versus not (L11821) | Later: use the standing order in docs/FLASH-PROTOCOL.md. |
| Hook 0x107be | "Ungated" (L6527) versus state-gated (L6686) versus never confirmed to fire (L7505) | Newest: never confirmed to fire. |
| probe135 | The log says never flashed; build/hook/snapshots/ holds probe135 `.flashed` copies | The log wins (L9405); snapshots are taken before a flash (L9359). |
| Trap names before 2026-09-30 | See L2161 | Later table (docs/trap-numbering.md). |
| Press count claims "press after press" | n = 2 observed (probe177 result 2, probe178), RESUME-HERE banner says "press after press" | verify.md V1: n = 2, N > 2 unproven. |

### 10.4 Gaps (unknown, with the file that would answer)

| Question | Where an answer might be |
|---|---|
| Result of probe7 and whether it was flashed | Nothing recorded; firmware/bose/probe/probe7_fs_blind.dfu and build/probe7/ only. Ask the owner. |
| Flash status and results of probes 12-21 (except 15b and 18b, which were flashed) | opus_task/CONSULT*_TASK.md and docs/bose-firmware-anatomy.md carry only the unverified narrative. |
| Results of probes 108, 109, 110, 112 | Not in the log (L6525); the owner may remember. |
| What flashes #1 to #13 on unit 2 were | Probably the bring-up, probes 77, 128-134, 136, 137 and a recovery; the log numbers flashes only from #14 (probe139). |
| Whether probe87 was ever flashed | No evidence either way. |
| Why readbacks are absent for probes 57-73, 84, 87 and 103-127 | Unknown; for 103-127 see docs/POST-MORTEM-2026-10-04.md. |
| Which stock-recovery readback file belongs to which recovery flash | build/hook/stock_recovery*_readback.dfu; only the "b" pair (flash #41) is documented (L12274). |


## 11. Built and gated offline 2026-10-12, never flashed (probes 181p, 184a, 184, 187)

Offline, owner away. Built by the firmware study (`docs/deep/firmware-study-2026-10-12/README.md` section 4 has the hashes; the notes T06c, T08 and T11 have the cave listings, id tables and press pages). `build/hook/FLASHED` still names probe178. None of these may be flashed before the owner is present, every FLASH-PROTOCOL gate applies, and each is one flash, one press, one recorded result.

| probe | date, unit | what it changed | question | press result | verdict | key lesson | log | artefacts |
|---|---|---|---|---|---|---|---|---|
| probe181p | 10-12 none | probe181 with REARM `ld AL,#1000` -> `ld AL,#200` (exactly two words differ, 0x3E382 and 0x3E383); 174 words; words sha256 d057e1f3...9a63, dfu sha256 757fc413...d89c | What is the rebuild latency c, and is the seam audible at a 200 ms poll? | NOT-FLASHED | NOT-FLASHED | If the lead exceeds about 22 ms the 0x1072 and the rebuild land inside the audible tail at EVERY seam (a rare accepted hazard in 179-181 becomes the normal case: owner decision T11-N2); the heard gap reads c (model). The 100 ms and 50 ms images are separate builds (172 words, 59 differ). No sinkState guard. [Round 3 2026-10-12: V04 fix-first on the press page, words reproduce; see 12.1] | none | asm words cmd dfu gate (`gate_probe181p.py`, 37 scenarios) |
| probe184a | 10-12 none | Tiny valid ROFS (2,800 B, 100 periods) written to p2 by the 184 cave; tail start 1,270; pre-erase look for "fsr_" at map elements 18..21; then FileFind and PartitionMountFilesystem(1,2,1); 341 words; words sha256 23776c54...9ec0, dfu sha256 ecd8ec6a...3b5b | Does a valid ROFS in p2 reach the union file system (found / found after mount / missing)? | NOT-FLASHED | NOT-FLASHED | OWNER GO-AHEAD REQUIRED (one erase of the only unit). Counts BYTES (claim 28, flush 28, FIRST = 9), not the words of the 2026-10-10 spec. After the press press NO centre button until the image is replaced: a centre SHORT press is predicted to be converted into 0x4004 and would repeat the erase (T11 E11). The protocol readback never covers p2. No sinkState guard. ids 0x12 0x35 0x0b 0x3f 0x14 0x15 0x36 0x37 0x38 (one per outcome class). [Round 3 2026-10-12: V03 fix-first; R02: the file route cannot mount p2 (type 3), cannot succeed as designed; see 12.1] | none | asm words cmd dfu gate (`gate_probe184.py`, 24 scenarios), `narrow184_lib.py` |
| probe184 | 10-12 none | The at-scale p2 write of the T07 flat 15 s file (60,368-byte ROFS, 2,156 periods); 296 words; words sha256 e618367a...00f4, dfu sha256 916e301b...1e58 | Is the 15 s brown file visible and playable from p2? | NOT-FLASHED | NOT-FLASHED | Only after 184a found the file (owner decision J-D2). Same press-no-centre-button rule as 184a. The crest-reduction variant of the payload must be chosen before the erase (cannot be traded afterwards). [Round 3 2026-10-12: V03 fix-first; R02: cannot succeed as designed; 58k and 90k variants exist; see 12.1] | none | asm words cmd dfu gate (21 scenarios) |
| probe187 | 10-12 none | Read-only volume census: reads `@0x6d0`, `@0x72f`, `@0x528`, `@(14,@0x6d0)`, `@(10..12,@0x72f)` and speaks one id (0x2A = the full prediction); 104 words; words sha256 aca96db8...4ae0, dfu sha256 0bd22034...9fe6c | Does the stock tone word stay fixed at -2242 (the buttons do not move the noise), and is the DAC gain type digital? | NOT-FLASHED | NOT-FLASHED | Writes only its own stack frame; calls only SPEAK and the stock replay. Ids 0x39-0x3D (guards, rare outcomes) are stock prompts never spoken on this speaker, chosen for that reason; wording is an owner decision. Single-press script in T06c. [Round 3 2026-10-12: V04 fix-first on the press script and ids; R04: the press does not settle the DAC question; see 12.1] | none | asm words cmd dfu gate (`gate_probe187.py`, 4,567 states) |

Status of the designed-only list (section 6): probe184 now has an assembler (above); probe182, probe183 (see decision J-D17), probe185a/b and probe186 do not. The pipe census that STRATEGY.md rank 1 proposed was never designed and is closed (T01: trap 0x100 is not dispatched).


## 12. Built and gated offline in round 3 (2026-10-12), never flashed (probes 181q100, 181q50, 188, 189, 184_58k, 184a_58k, 184_90k) and the verifier verdicts on section 11

Offline, owner away. Built by round 3 (`docs/deep/round3-2026-10-12/README.md`; builders B01, B02, B03). `build/hook/FLASHED` still names probe178. None of these may be flashed before the owner is present; every FLASH-PROTOCOL gate applies; one flash, one press, one recorded result. "Builder gate only" means no independent verifier read the image: the gates are the builder's own (decode-verify, preflight, caveguard, stackdepth, `cavesim probe90` AL = 0x0e, a world-model gate). Full sha256 values below were recomputed with `sha256sum` on the files on 2026-10-12 and equal the notes' values.

| probe | date, unit | what it changed | question | press result | verdict | key lesson | log | artefacts |
|---|---|---|---|---|---|---|---|---|
| probe181q100 | 10-12 none | probe181p with POLL_MS 100 (REARM's `ld AL,#100`, a one-word immediate, so the layout re-flows: 172 words, 59 addresses differ, one immediate differs at source level); words sha256 4644c4ac27e8e33a5ec2f46a03b3e184c7d0683508f7d5922052bd338f03683b, dfu sha256 63f32941e271bd89ae2495bd93d2d6938f2c1f63dd4ef35de789145bddf8af24 | Does a 100 ms poll narrow the seam threshold (model: 110 ms below L 18.5 ms, 27 ms above)? | NOT-FLASHED | NOT-FLASHED | Builder gate only (B03). `gate_probe181q.py` 39 scenarios, 0 failed. Same ids as 181p, so it cannot be told from 181/181p by an id (V04); 0x25 covers two refusals. Shortest timer run on unit 2 so far is 108 ms (F291). Every threshold is conditional on the unmeasured chunk length D (time ten pulse onsets on 181p first). Decide only after the 181p result. | none | asm words cmd dfu gate (B03) |
| probe181q50 | 10-12 none | probe181p with POLL_MS 50 (172 words); words sha256 089f38b96e71dc8bf30a78ce10173fb4b846156d612bf4d325fd99be16a896a2, dfu sha256 a9f3f0810756700305d9b13d4b1f51f78e28520c1ce9f68fd6aff28c9de2802d | Does a 50 ms poll make the seam a pure splice, and does a timed pulse count measure D? | NOT-FLASHED | NOT-FLASHED | Builder gate only (B03). `gate_probe181q.py` 40 scenarios, 0 failed. A first-ever 50 ms timer on unit 2 (owner decision PD-08). Model: the first free tick (2650 ms) falls in the 0x1072/0x1080 window, so chunk 2 is built before 0x1080 of chunk 1 (hardware effect unknown). Best model cell is 16 ms; no poll reaches J-D4 inside R03's lead bounds with the purge kept. | none | asm words cmd dfu gate (B03) |
| probe188 (PBd) | 10-12 none | Product-build diagnostic on the 181p loop: merged-entry guard (sinkState 13 or 3, then `tst @0x72f`) before `StreamKalimbaSink(3)`, STOP first by MessageCancelFirst, `0x1072` (8000, b = 2) on every rebuild, POLL 200, 6-word consume lever in TRIG, deferred start when port 3 is busy, guard-refusal ids spoken by TRIG only; 180 words `0x3E21D..0x3E3E1`; words sha256 b5e055e80de4979640c71ade4dc052650f58482befdc5655b9b76a685f1d4c00, dfu sha256 e0523156fb0685545093567ab946edf877637f881c9801db8e7b2d04633abd2f | Does the guard pass in a healthy stream (first ground truth of sinkState 3/13 at the centre hook) and does the consume lever work? | NOT-FLASHED | NOT-FLASHED | Builder gate only (B01). `gate_probe188.py` 80 scenarios, 0 failed (mutations caught). Uses the speech stand-in material (rphrases_us chunk), so it is plumbing for goals 2 and 4, not goals 1/3. Valid only for POLL_MS 200; hashes provisional until the 181p result (PD-16). The consume lever is a never-run form (first cave store into a caller frame, not attested in Bose code). Gate 5/6 exception needed (PD-02). | none | asm words cmd dfu gate (B01) |
| probe189 (PB) | 10-12 none | PBd with nine tail entry points reduced to `leavel -8` and 15 tail words dropped (silent ends); 165 words; words sha256 f6d647dd1513cd0b4e26aaca57c1884b6c15cc216c6092e6c8530943056ad125, dfu sha256 21e8d9eeb11e3bb2dbb787e6fad0a590b9f55880038fb67943c95463eb928eb8 | The stand-in product: looping stand-in noise on the centre long press, silent. | NOT-FLASHED | NOT-FLASHED | Builder gate only (B01); 80 scenarios, 0 failed, compared with PBd summary by summary. PB follows PBd (PD-10). Fallback only if the p2 raw route is blocked (PLAN-v2). Limits: loops until a prompt or a pause, silent ends outside states 3/13, recurring stock tones +18 dB (V04). | none | asm words cmd dfu gate (B01) |
| probe184_58k | 10-12 none | probe184 with the 58,700 B payload at tail start period 1,320 (ROFS 58,968 B, 2,106 periods); 296 words; words sha256 d06f4414768aa513c6f78a4ab89ff8efbe26b41691013fca7c13ebe14b4dce04, dfu sha256 222dbad8d45d445dec2512c06d25f6854774ad99846ce86cc39a85ef135fa798 | The at-scale p2 write that spares the region-A header, the E6 array and the region-B tail (14.675 s, 0.35 s shorter). | NOT-FLASHED | NOT-FLASHED | Builder gate only (B02); `gate_probe184.py` 22 scenarios, 0 failed. The 58,700 B payload (sha256 a488348bceea2b88fa35512fe4e304de3546b631fc4f62628eb9a599239ffa17) is new and NOT independently verified (V02 covered the 60,100 B file). All 184-family images fail by design while p2 is table type 3 (R02: the mount needs type 1): owner decision PD-20. | none | asm words cmd dfu gate (B02) |
| probe184a_58k | 10-12 none | probe184a with the matching start 1,320 (2,106-period span, tiny ROFS 2,800 B as 184a); 341 words; words sha256 5d576aae87a25d747f7e99a8b39710eab4c3c20535fc56cbcb3cea1c6b033d6d, dfu sha256 35b2bb270aad2d174e98217e06ab32b2d7677313bd8f4849a15d122ee149a69d | The tiny-ROFS write test with a span that spares the speech structures. | NOT-FLASHED | NOT-FLASHED | Builder gate only (B02); 25 scenarios, 0 failed. Cannot succeed as designed (R02 mount refusal); a raw-payload image replaces it (PLAN-v2 G-RAW). | none | asm words cmd dfu gate (B02) |
| probe184_90k | 10-12 none | probe184 with a 90,004 B payload at start period 202 (ROFS 90,272 B, 3,224 periods); 296 words; words sha256 5b6dffac2ce06cfde926d67b4493b82fd78ffc4143ff2ab48931c1fe0f416719, dfu sha256 cbf5e12ad4a480fd31ede19c12cb3ec49e01c9619fc66ad47537dedd95efcab2 | The 22.5 s alternative; model: all 57 speech ids garbled, 94.0 percent of data_us rewritten. | NOT-FLASHED | NOT-FLASHED | Builder gate only (B02); 22 scenarios, 0 failed. Shown to build, not recommended. | none | asm words cmd dfu gate (B02) |

### 12.1 Verifier verdicts on the section 11 images (round 3)

| probe | verdict | what the verifier requires before any flash decision | note |
|---|---|---|---|
| probe181p | V04: fix-first (words and gate reproduce; the PRESS PAGE needs edits) | Add the missing outcome row (START silent because port 3 is busy at ARM's `TransformFromSink`), state the shared ids and the four-press script as the gate 5/6 exception, ask for the stopwatch time of chunk 2 (the 20 ms / 200 ms rungs hold only near D = 2621.5 ms), name both times of the 55-tick mark. Words differ from 181 in exactly 0x3E382 and 0x3E383 (reproduced); 179, 180, 181 hashes unchanged. | `docs/deep/round3-2026-10-12/V04-verify-187-181p-pb-spec.md` |
| probe187 | V04: fix-first (words, gates and hashes reproduce; read-only in the cave; SPEAK itself swaps the DSP) | Press script step 2 contradicts itself (use volume DOWN about 6 presses, never to the bottom); add "USB unplugged after the readback"; mark outcome ids 0x2D, 0x2E, 0x2F, 0x30, 0x3D "not expected"; the 0x2A row is never spoken (DECODER+10 is never written); the press reads the VM-side gain type only and does not settle the DAC question (R04): add the two free owner readings. | V04, R04 |
| probe184a | V03: fix-first | Both 1,270-start images rewrite 12 of 30 region-A header words (the TTS DSP reads that header): "57 of 57 ids survive" is a hypothesis; STATE VALID proves the commit only; the 184a-to-184 inference is invalid; press page: laptop connected (state 3 or 13), power-cycle after the id, no HFP connect; CLAUDE.md rule 3 vs the code-region words (PD-27). B02 built the 1,320-start variants. R02 then shows the file route cannot mount p2 (type 3). | `docs/deep/round3-2026-10-12/V03-verify-184a-184.md`, R02 |
| probe184 | V03: fix-first (same as 184a); the 60,100 B payload itself is V02: safe-to-flash-offline-evidence (not a flash clearance) | As 184a, plus an 81 KB walk (184a) and a further 138 KB gather (184) with no stock precedent; consider a ROFS of at most 2,106 periods. | V03, V02 |


## 13. Probes 182-381 by era (added 2026-10-28; per-probe rows were not written for these; the evidence is the "# probeNNN" entries of `docs/field-log.md`, which you can list with `grep -n "^# probe" docs/field-log.md`)

Flash numbers after about #217 in the field log are approximate (some entries reuse a number). The era rows below are summaries written from the field-log headings and the project memory notes: check the named entries before relying on a detail.

| probes | dates | what they established | result |
|---|---|---|---|
| 182-196 | 10-13/14 | narrow payload, staged `data_us`, the level knob (0x1072 word b), the first audible chunks; 24 kHz and 48 kHz payload decoding | the tone path plays recorded material; volume steps work |
| 197-225 | 10-14 to 10-16 | CONSUME of the stock 0x4004 path, hands-free loop with the laptop microphone, cold DSP load of `sbc_decoder`, amp-on message, Bluetooth events reaching the hook | brown noise from a speaker with no Bluetooth audio stream |
| 226-242 | 10-16/17 | level machinery, the twelve new dead functions (probe235 stub-only), ladder rungs | cave expanded to about 1,340 words |
| 243-287 | 10-17 to 10-19 | the product (MODETOGX, OFFALL, ENSURE, WATCH, SPEAKX), NEWFEAT power-off/mute/yield, DAC release experiments | the stable product (probe285 stop, power-off) |
| 288-300 | 10-19/20 | read-only state census, EVGUARD, the stale DAC flag, the G5 guard | probe300 rollback learned |
| 301-322 | 10-20 to 10-23 | payload writers (24 kHz, compensated), 48 kHz pair, NOPURGE, TIMERS (stock idle off cancelled), press-free writer | "for all intents and purposes perfect" at probe318 |
| 323-337 | 10-24/25 | SCAN/BTDROP (Bluetooth off while playing), fine 15-level ladder, click hunt: poll period, free-edge message, stall instrument | clicks traced to the loop seam |
| 338-358 | 10-25 to 10-27 | no-poll watchdog, boot-start (test aid), native 32 kHz payload (no steps), LEDDARK (lights dark), TMREARM (idle power-off restored) | probe358 meets the owner's flow |
| 359-365 | 10-28 | the DSP census: PEEK path, safe ids, check digit, the stale-X fix; ring and cell values | DSP internals mapped |
| 366-367 | 10-28 | 512-sample tone ring at 48 kHz | 0 timeline steps; boot-start removed in 367 |
| 368-379 | 10-28 | PM_WIN_ENABLE, PM window read/write proven, address forms, DM2 timer struct | the DSP's program memory is writable |
| 380 | 10-28 | the lean generator product (GEN), one flash from stock | measured within 2.4 dB of the recorded noise |
| 381 | 10-28 | inert stubs of AY batches C and D | hands-free check passed |
| 382-383 | 10-29 | read-only spoken-readout diagnostics (events 0x4070-0x4077) | not products |
| 384-388 | 10-29 | the connected-device start fix: STARTWAIT, CANCEL670B, SILENTDROP (387 loop, 388 generator), NOREWR | product matrix passed |
| 389-394 | 10-29 | payload writer revisions; 393 final (guard first, fixed 45 s tick, DROPBT, MUTEBOOT) | shipped as the writer in v0.2.0 |
| 395-420 | 10-29 to 10-30 | generator EQ experiments (stacked state-variable sections, wider loader table, recording-fit tuning) | tuning against a through-speaker recording abandoned, see `docs/ear-tuned-eq.md` |
| 421-422 | 10-30 | +3 dB / +5 dB tilt probes from 630 Hz | 421 "pretty good" |
| 423-425 | 10-30 | generator fitted to the source recording, then to the hybrid curve (v1-v3) | 425 "perfect" |
| 426 | 10-30 | probe425 + volume ladder capped at 12 levels | not flashed alone |
| 427 | 10-30 | probe426 + PWRREL (power-off releases the audio-busy hold at once) | shipped as the product in v0.2.0 |
