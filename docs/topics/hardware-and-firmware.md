Purpose: one-page orientation on the CSR8670 / Bose SoundLink Micro hardware and

> **Note on references (public export):** this file cites files from the original private research repository that are not included here; each such path is marked "(not in this export)" at its first mention, and all of them are listed in `docs/NOT-IN-EXPORT.md`. The claims they support are summarised in the text; the cited originals are not needed to rebuild or flash anything.
firmware, with routes into every doc that has detail, so a new agent does not have to
read docs/field-log.md to understand the device.

Status / last verified: 2026-10-10.

Read next: docs/CURRENT-STATE.md for the current state of the speaker, then
docs/topics/dfu-and-signing.md for how any of this can be written to, then the
"detailed knowledge" list below for a specific subsystem.

> **This is an archival research document from the original (larger, private) project repository.** Some of its internal links point at files not included in this public export; where one doesn't resolve, that's why. The repository's own current, self-contained write-ups are listed in README.md's "Repository layout" section.

Confidence marks: **proven** (address, instruction, command output, or quoted press),
**well-supported** (one traced inference beyond a proven fact), **hypothesis**.
Where sources disagree, the newer source wins; this file says so inline. Anything under
docs/deep/offline-2026-10-10/ is itself superseded in places by that directory's own
verify.md and stack-transform.md -- follow the banners.

---

## 1. Summary (what is established)

The target is a real consumer product, a Bose SoundLink Micro ("Minnow"), built on a
CSR8670 "gordon" Bluetooth/audio chip, not a bare development board. It has no debug
port and no SPI programmer attached; the only way into it from software is Bose's own
USB HID-DFU updater, which is signed. The firmware is split into a VM application
(XAP2 bytecode, the "control plane": buttons, messages, streams) and four Kalimba DSP
images (the "audio plane": decoders and tone mixers), plus a large, never-disassembled
native Bluetooth stack binary. All of this has been read, mapped, and (for the VM app)
100% decoded, though only ~17% of its functions are named. A small amount of writable
space -- a "cave" of about 197 words living inside signed flash -- is the only place
this project's own code can live, reached by redirecting an existing call inside the VM
app. The cave can load and drive the stock DSPs and play stock audio files through
them; it cannot add new DSP code or new large audio data, because the filesystem's
write budget is capped at 29-of-every-64 bytes (see docs/topics/dfu-and-signing.md). As
of probe178 (flash #57 on this unit), the cave reliably intercepts a centre-button long
press and controls the output level of a looping noise-like audio chunk played through
the stock A2DP decoder DSP's tone-mixing port. The device is currently disconnected; no
further flash may happen until the owner returns (memory note
csr8670-offline-period-2026-10-10).

## 2. Key facts

| fact | confidence | source |
|---|---|---|
| Device is a Bose SoundLink Micro, chip CSR8670 "gordon", USB HID 05A7:40FE (app mode) / BT DFU PID 0x4022, stock firmware 3.0.3.6546 | proven | memory csr8670-project-device.md; docs/device-support.md:9 |
| No CSR USB-SPI programmer and no COM port exist on this unit; HID-DFU is the only software path in | proven | memory csr8670-project-device.md; docs/FLASH-PROTOCOL.md:224 |
| `PSKEY_USB_VM_CONTROL = 1`: the VM app drives USB enumeration, so a dead app means no USB and no software recovery | proven | docs/POST-MORTEM-2026-10-04.md:37; docs/FLASH-PROTOCOL.md:224 |
| Internal filesystem (partition 0) holds 7 files: `vm.app` (522,026 B), `data_us` (219,528 B), `rphrases_us` (10,486 B), and 4 `.kap` DSP images | proven | docs/firmware-map.md section "13. fs file table" (per inventory-docs.md row); docs/partition-route.md:65 |
| `vm.app` is XAP2 bytecode: 236,514 code words, 100% decoded, 5,663 function entries, 17.4% named | proven | docs/firmware-map.md section 1 |
| Call ABI: arg1 -> AL, arg2 -> AH, args 3+ at @(0,Y).., return in AL (arg1-first, "AL-first") | proven, compiled-and-linked | docs/trap-abi.md; retracts docs/vm-trap-calling-convention.md (RETRACTED banner) |
| Message handler receives Task in AL, MessageId in AH, Message arg at @(n,Y) | proven | docs/message-task-abi.md sections 1-5 |
| `enterl -k` reserves the TOP TWO frame slots (k-2, k-1) for the return address; only slots 0..k-3 are usable | proven | docs/cave-frame.md |
| VM heap is 10 fixed pmalloc pools (4,16,32,46,94,100,100,138,318,642 words); only one allocation above 138 words is possible | proven | docs/cave-heap.md |
| Partition 0 holds the main filesystem; partition 2 is written for "image type 4", almost certainly the external language filesystem (not yet hardware-confirmed by PartitionGetInfo) | proven (map) / well-supported (partition-2 content) | docs/partition-route.md lines ~37-71 ("CORRECTION, 2026-10-06") |
| External flash carries a second signed filesystem (`ext_flash.bin`, 2,090,936 B, format `fsr_dfu1`), 12 foreign-language prompt packs, mounted into the app's union filesystem | proven | docs/partition-route.md "The external filesystem is real..." section |
| The cave's only safe home is `0x3E200..0x3E400`, ~197 writable words across three zero runs (59+70+68); a wider 262-word scan crashed the speaker (probe130) because a zero word inside a live table is still read at runtime | proven, enforced by tools/caveguard.py | docs/cave-budget.md; memory csr8670-cave-window.md |
| Only `sbc_decoder.kap` (of the 4 DSPs) registers the `0x1070/0x1071/0x1072` tone-mixing message family; it needs a real A2DP media stream to load | proven | docs/firmware-map.md "The seven DSP-load sites"; docs/kalimba-disasm.md "All four DSPs, not two" |
| DAC gain: codec output gain register value 15 = 0 dB, 3 dB per step (not the "12 = midpoint" first assumed) | proven | docs/gain.md |
| Tone gain-shift on this binary is 7 (bit clear) / 4 (bit set), not the ADK's 11/8 -- word b=0 is 18 dB louder, never clipping | proven, corrects an earlier reading | docs/kalimba-disasm.md "THE CORRECTION"; docs/bose-audio-path.md section 8 |
| Current proven audio chain (probe177/178): FileFind(rphrases_us) -> StreamFileSource -> TransformAdpcmDecode -> StreamKalimbaSink(3) -> TransformStart | proven, n>=1 on hardware | docs/deep/offline-2026-10-10/material-slots.md section 0 |
| Bose's own canonical transform teardown is exactly 4 calls: TransformFromSink -> TransformStop -> TransformDisconnect -> StreamDisconnect(0, sink) | proven | docs/firmware-map.md "0x31E6F-0x31E90"; docs/cave-heap.md |
| Calling TransformStop on the DOWNSTREAM node of a live chain Panics (0x4030 at stack 0x1d74f) -- the best reading of the probe174/175 crash cause (not a heap leak) | Panic decode proven (stack-image study, newer); as the crash cause well-supported, not yet pressed | docs/deep/offline-2026-10-10/stack-transform.md section 0 |
| A data_us chunk through port 3 runs ~219 s (not ~7 s; the ~7 s figure came from a Bluetooth pairing teardown cutting playback short) | proven | memory csr8670-port3-chunk-rules.md; field-log probe157/173 |
| Centre long-press hook: fn_07f1a -> fn_080ad -> fn_07d5d, 9-word edit makes a centre long press send 0x4004 in every state; converges at 0x00e46 (`bsr fn_189fb`), all operand bytes blind | proven, current hook (probe172+) | docs/deep/centre-long-press.md |
| No contiguous run over 29 writable bytes exists anywhere in the signed image -- see docs/topics/dfu-and-signing.md for why | proven | docs/content-control-analysis.md section 1; docs/cave-budget.md "What is not available" |
| Nothing in the shipped firmware can synthesize noise on its own; all known generator code (dtmf.asm, vector_rand, CVC comfort-noise) is unreachable in this build | proven, closed route | docs/dsp-noise-route.md section 4 |

## 3. How it works, in layers

1. **Hardware / USB layer.** CSR8670 "gordon" chip inside a Bose SoundLink Micro. USB
   enumerates as HID 05A7:40FE in normal/app mode, and as Bluetooth DFU device 0x4022
   when the chip is told to enter its boot loader. There is no other USB personality and
   no exposed debug/SPI header on this unit. Recovery when the app is wedged but still
   enumerating is a cold power cycle done with USB unplugged (docs/FLASH-PROTOCOL.md
   "Recovery" section) -- plugging/unplugging matters because the chip stays powered
   over USB regardless of battery state.

2. **Flash / filesystem layer.** Two independent signed filesystems exist: the internal
   one (partition 0: `vm.app`, 4 `.kap` DSP images, `data_us` prompt audio, `rphrases_us`
   phoneme script) and an external one (`ext_flash.bin`, 12 foreign-language packs,
   mounted into the same union filesystem `vm.app` searches via `FileFind`). The boot
   loader's DFU protocol can only write the internal filesystem's container format;
   the external one is written by the running application over a different USB channel
   that is cloud-gated and currently unusable for this project (docs/partition-route.md
   "But the delivery channel..."). A possible, unproven, high-risk third route is a
   direct runtime write to partition 2 (see docs/topics/dfu-and-signing.md section 4).

3. **VM application layer (the control plane).** `vm.app` is XAP2 bytecode running on
   the chip's VM. It owns button/event dispatch, message routing between tasks, stream
   and transform wiring (connecting audio sources to sinks), and the prompt/TTS engine.
   It never touches raw PCM samples itself -- audio always flows through a `Source`
   object into a `Sink` object; the VM only wires that connection (docs/bose-audio-path.md
   sections 1-2). The project's own code (the "cave") is a small block of this same
   bytecode, redirected into by changing an existing call's operand bytes to point at
   cave code instead of Bose's own target -- never by widening the VM app's size, which
   the signed image does not allow.

4. **DSP layer (the audio plane).** Four Kalimba DSP images: `NowSpeakTTS.kap` (TTS/
   standalone prompt, port 0), `sbc_decoder.kap` (A2DP decode + tone/voice-prompt
   mixing, port 3, the only DSP with the spare tone-mixing port this project uses),
   `soundClearNb.kap` / `soundClearWb.kap` (call voice processing). The VM loads a DSP
   with `KalimbaLoad`, wires its ports with Stream calls, and sends it short control
   messages (`0x1070`/`0x1071`/`0x1072` for the tone/mixing family on `sbc_decoder`).
   The DSP produces or passes through samples; the VM never does.

5. **XAP2 execution model.** Bytecode word = `operand8<<8 | opcode8`. Register aliases
   live in data space: `@0xffe0`=AH, `@0xffe1`=AL, `@0xffe4`=Y (all read-only);
   `@0xfff8`-`@0xfffb` is writable scratch. `enterl -k` / stack-frame conventions and
   the trap-call ABI are documented in docs/xap-opcodes.md, docs/trap-abi.md and
   docs/message-task-abi.md. A `TaskData` (2 words, a position-independent code-relative
   address) can live permanently in flash, letting a cave own a `Task` with zero RAM.

6. **PS (persistent store) keys.** Per-unit configuration (`PSKEY_USR0..USR99`,
   `PSKEY_PMALLOC_APP`, `PSKEY_INITIAL_PIO_STATE`, `PSKEY_USB_VM_CONTROL`, etc.) is
   stored separately from the filesystem, has only a CRC-32 (no RSA signature), and one
   probe into it was still rejected by the loader for an unidentified reason (see
   docs/topics/dfu-and-signing.md section 5). `PSKEY_USB_VM_CONTROL=1` is the key fact
   that makes "no app = no USB = no recovery" true on these units.

## 4. Traps and retractions (what earlier text got wrong)

- **"Zero means unread" -- false.** A const-pool word that is zero in the official image
  and sits inside a DFU blind window is not automatically safe cave space: some such
  words sit inside live tables that are read at runtime by a computed/indexed load.
  probe130 used a widened 262-word scan and crashed the speaker on boot because 55 of
  those words were in that category. The safe, enforced window is 197 words in
  `0x3E200..0x3E400` only. Source: memory csr8670-cave-window.md; docs/cave-budget.md.
- **Trap numbers are not stable across BlueLab versions.** This device's `vm.app`
  stamps VM version 0x3200 = BlueLab 7.3; naming stubs from the ADK 4.4 / BlueLab 7.4
  table (173 of 257 shared names differ) silently mis-targeted stubs in several early
  probes (e.g. a call landed on `StreamScoSink` instead of `StreamAudioSink`). Source:
  docs/trap-numbering.md; memory csr8670-toolchain-status.md.
- **The arg-calling convention was recorded backwards once.**
  `docs/vm-trap-calling-convention.md` (not in this export) states AH-first and calls itself "settled"; it
  was compiled with `-S` only, missing `-mal-first`, and is explicitly retracted in
  favor of docs/trap-abi.md's AL-first convention (compiled-and-linked proof).
- **"Loading/wiring a DSP from the cave wedges the device" was too broad.** A one-call-
  at-a-time bisect showed `KalimbaLoad` alone and `StreamConnect` to the DAC alone are
  both clean; the wedge is in *starting* a DSP the firmware's own audio manager does
  not know about, or routing data through one unexpectedly. Source: docs/firmware-map.md
  "What actually wedges, precisely".
- **The tone gain-shift table was read from the wrong base (ADK's 11/8 instead of
  Bose's actual 7/4).** This made two flashed probes (107/108) 18 dB quieter than
  intended, under the mistaken belief that word b=0 saturates. Source:
  docs/kalimba-disasm.md "THE CORRECTION".
- **A data_us port-3 chunk's duration was generalized from a figure measured only
  under Bluetooth-pairing teardown (~7 s) instead of from file size / sample rate
  (~219 s).** Carrying the wrong figure into a re-arm timer caused probe173's loud,
  unstoppable runaway. Source: memory csr8670-port3-chunk-rules.md.
- **TransformStop on an active chain's downstream node was blamed on a heap leak;**
  the real, static cause (a firmware Panic on that specific call pattern) was only
  found in the later stack-image study. Source: docs/deep/offline-2026-10-10/
  stack-transform.md section 0, "new" row; this also reframes the file-source EOF
  behavior (disposing the transform chain synchronously) as normal, not a fault --
  correcting docs/deep/offline-2026-10-10/README.md/DESIGN.md's earlier framing.
- **An earlier three-partition, byte-counted flash layout table was never grounded**
  in the image (none of its sizes appear in `vm.app`) and is retracted in favor of the
  code-derived type->partition map. Source: docs/partition-route.md "CORRECTION" section.
- **"rphrases_us is an (offset, length) directory into data_us" is withdrawn.** It is
  the phoneme script of the NowSpeakTTS engine instead (request id N maps to table
  entry N+1). Source: docs/deep/offline-2026-10-10/promptmap.md section 0; supersedes
  docs/bose-firmware-anatomy.md section 12 (also marked withdrawn there).

## 5. Open questions

- Partition 2's content is inferred (external-language filesystem) from the type->
  partition mapping, not confirmed by a `PartitionGetInfo` read. Unknown until that
  call is made. Source: docs/partition-route.md.
- Whether a full-size (tens of KB) runtime partition-2 write actually commits safely
  is untested; only a 16-byte write has been proven to commit
  (`PartitionSetMessageDigest`). This is the project's one unbounded-brick-risk mode.
  Source: docs/partition-route.md "What makes it unsafe".
- Whether a periodic timer tick reliably arrives when armed from the current
  `0x00e46` hook has not been directly observed on hardware; it is well-supported by
  the mechanism (a const `TaskData`) but not confirmed by a quoted press. Source:
  docs/deep/offline-2026-10-10/DESIGN.md section 8 item 8.
- The ~1,318-word unreferenced debug-string reserve's safety for cave code is
  undetermined; "never loaded by an immediate address" does not rule out computed-
  address table entries. Source: docs/cave-budget.md "The reserve".
- What exactly caused unit 1's loss is not reduced to a single cause: the skipped
  readback gate is proven to have hidden the problem, but a second candidate cause
  (a probe placing words outside the safe cave window around the same time) is also
  recorded and neither is ruled out. Source: docs/POST-MORTEM-2026-10-04.md;
  field-log lines ~8286-8302.

## 6. Detailed knowledge (routing)

| doc | read it for | when |
|---|---|---|
| docs/RESUME-HERE.md (lines 1-40) | current state of the speaker, right now | always, first |
| docs/PROJECT-LAYOUT.md | every top-level directory and whether it is load-bearing | orienting in the repo |
| docs/firmware-map.md | coverage numbers, named functions, DSP-load sites, what wedges precisely | deciding if something is already understood |
| docs/xap-opcodes.md | XAP2 instruction encoding, the 0x0009 modifier, the 0x0000 signed-prefix rule | reading/writing raw bytecode |
| docs/trap-abi.md + docs/trap-stub-table.md | the real (AL-first) call ABI and every trap's address, by name | calling any stub trap |
| docs/trap-numbering.md | why trap numbers differ between BlueLab 7.3 and 7.4, and which table to use | naming any stub |
| docs/message-task-abi.md | message handler ABI, TaskData layout, where a cave's Task can live | writing a message handler or timer callback |
| docs/cave-frame.md | the enterl -k top-two-slots rule | writing any cave function with locals |
| docs/cave-heap.md | the 10 pmalloc pools and sizes; why malloc(254) is refused | anything that calls malloc |
| docs/cave-budget.md | exact cave window, writable word counts, what is NOT available | before writing cave code, every time |
| docs/deep/space-survey.md + docs/deep/code-region-plan.md | the dead-code cave-space reserve beyond the 197-word window | if 197 words run out |
| docs/bose-audio-path.md | Bose's own audio recipe (FileFind -> KalimbaLoad -> StreamConnect -> ...) | wiring any audio path |
| docs/kalimba-disasm.md | the four .kap DSPs, the tone gain-shift correction, the PM-flash overlay | anything DSP-side |
| docs/gain.md | DAC gain scale (15 = 0 dB, 3 dB/step) | setting loudness |
| docs/dsp-noise-route.md | why/how the DSP route to brown noise is blocked or open, dated history | understanding the noise-generation blocker |
| docs/deep/centre-long-press.md | the exact byte-level edit for the centre-button hook in use since probe172 | touching the button hook |
| docs/deep/hook-gates.md | why earlier hook candidates (0x10823, 0x107be, 0x0AE0) were tried and withdrawn | avoiding a known dead end |
| docs/partition-route.md | partition map, the external filesystem, the parked runtime-write route | anything about partition 2 or ext filesystem |
| docs/deep/offline-2026-10-10/stack-transform.md | the stack-firmware ADPCM transform/port-3 lifecycle; the probe174/175 crash cause | anything about transform teardown or Panic 0x4030 |
| docs/deep/offline-2026-10-10/promptmap.md | rphrases_us phoneme-script structure; which prompt ids survive a staged payload | anything about spoken-prompt feedback |
| docs/deep/offline-2026-10-10/material-slots.md | which files can carry a narrow (streamable) payload; the current proven audio chain | choosing where content lives |
| docs/deep/offline-2026-10-10/chunk-end.md | the 0x1080 end-of-chunk signal and why it is poll-only, not hookable | anything about detecting chunk end |
| docs/deep/offline-2026-10-10/dsp-keepalive-rate.md | why the DSP unloads with music paused; the rate-latch issue | anything about sustaining or re-arming the DSP |
| docs/deep/offline-2026-10-10/DESIGN.md section 8 | the single merged, judged claim list superseding the individual research notes above | resolving any contradiction between docs |
| docs/deep/offline-2026-10-10/verify.md | which claims were downgraded/corrected by adversarial review (V0-V11) | checking whether a claim still stands |
| memory notes (csr8670-*.md, see MEMORY.md index) | owner's standing constraints and hard-won lessons, outside docs/ | always, alongside this file |

See also (firmware study 2026-10-12, offline, static or model results; read the skeptic section of each note first; index `docs/deep/firmware-study-2026-10-12/README.md` (not in this export), functions `docs/FUNCTION-CATALOG.md` (not in this export)): `docs/FUNCTION-CATALOG.md` (every function the notes identified, by image and address), `T05-auto-power-off.md` (0x4707 is never armed and cannot power off; 0x4737 is the encryption refresh: F190-F194), `T01-pipe-trap-0x100.md` (the stack trap table and the 18 stream classes: F157-F165) and `docs/FACTS.md` section 9.

## See also (round 3, 2026-10-12)

Added at the end so that no cited line moved. Round 3 is offline and static or model work; nothing was run on the speaker. Index and corrections register: `docs/deep/round3-2026-10-12/README.md` (not in this export); the facts are in `docs/FACTS.md` section 10.

- `docs/FUNCTION-CATALOG.md`: sections 1b, 2b, 3b-3d, 5c and 6 add the round-3 rows (boot mode, PS key 0x39, raw source, MMU buffers, DSP volume chain, TTS and soundClear, sinkState).
- `docs/deep/round3-2026-10-12/R03-stack-version-and-lead-L.md` (not in this export): the stack image is the same bytes in every stock release; the sbc_decoder flash records 1-3 are data (F244, F247).
- `docs/deep/round3-2026-10-12/R02-raw-source-0xd3-and-trap-catalogue.md` (not in this export): `python tools/trapcat.py --checks` re-derives the trap catalogue (227 slots, 20 forms, 18 stream classes).

## See also (2026-10-28)

DSP memory map facts (PM RAM 0x0000-0x2BFF, overlay cache 0x2C00-0x2FFF, PM window, tone ring, timer struct): F313-F319 and `docs/dsp-generator-route.md` section 3. Partition 2 holds the foreign-language packs on a factory unit (F325). Console events 0x4021 and 0x4022 are dangerous (F309).
