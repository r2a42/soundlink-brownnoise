Purpose: one hub for everything about the speaker's voice-prompt system and about WHERE brown-noise material can come from (files, ADPCM, loop seams, rate, partition 2), with routes to the detailed notes.

StreamFileSource streams only narrow files (flags 0x00): data_us and rphrases_us. See FACTS F112.

Status / last verified: 2026-10-10. Checked today on this machine: `tools/csr/dumpfs.py` on the official 3.0.3 image (file flags), `tools/adpcm.py --selftest`, `tools/brownnoise.py --selftest`, `tools/promptmap.py --selftest` (44 checks), the stream.h quote. Nothing in this file was pressed on the speaker today; the speaker has probe178 and is not connected.

Read next: `docs/topics/hardware-and-firmware.md` (device and cave), then the routing list in section 7 for the exact question you have.

> **This is an archival research document from the original (larger, private) project repository.** Some of its internal links point at files not included in this public export; where one doesn't resolve, that's why. The repository's own current, self-contained write-ups are listed in README.md's "Repository layout" section.

Confidence marks: **proven** (address, instruction, command output or press quoted), **well-supported** (proven pieces plus one stated inference), **hypothesis**. Negatives are results. Where sources disagree the newer one wins, and section 5 lists the known retractions.

---

## 1. Summary (one page)

The goal is loud, sustained brown noise on the speaker by software only, played through the speaker's own loud, volume-aware audio engine. Two questions decide it: what bytes to play (the MATERIAL), and how the cave gets them into the audio path.

**The prompt system.** Every spoken sound is a numbered request id (0x00-0x3F, 64 ids). The VM app asks the engine to speak id N; the engine reads entry N+1 of `tts/rphrases_us` (a phoneme script, 10,486 bytes) and sends the phonemes to a separate DSP app, `NowSpeakTTS.kap`, which synthesises speech from a voice database, `NowSpeakTTS/data_us` (219,528 bytes). All 64 ids are owner-verified by ear: 57 are speech, 7 are empty stubs, none is a tone or a sound that could loop. So the prompt system can never make noise itself.

**Why this matters twice.** First, the ids are the project's only feedback channel from the speaker: a cave "speaks" an id to report which branch it took (section 3.4). Second, the two files behind the prompts are the only streamable files on the device.

**The material chain that works today.** `FileFind` the file, `StreamFileSource` it (works only on "narrow" files, flags 0x00), `TransformAdpcmDecode` it into Kalimba port 3, `TransformStart`. The firmware pumps it with no further VM work. Proven on hardware with `data_us` (probe155) and with `rphrases_us` (probes 177 and 178). The decoder treats ANY bytes as 4-bit ADPCM, so the prompt files decode to harsh, heavily clipped noise: a stand-in, never the deliverable.

**The deliverable needs chosen bytes.** The generator and encoder exist and are verified offline (`tools/brownnoise.py`, `tools/adpcm.py`; the encoder matches the ADK's own tool byte for byte). The only open problem is a place to put them:

- The signed-DFU write path gives only 29 of every 64 bytes, never a run longer than 29. Chosen bytes interleaved with Bose's bytes decode as a roar. Closed.
- No `.kap`, no `vm.app` byte, no dead-code word can serve as a stream source. Closed.
- The one dense write channel that keeps the cave is the partition-2 overwrite (`StreamPartitionOverwriteSink(1,2)`), carrying a self-authored read-only filesystem whose file is narrow. The payload is built and verified offline (30,268-byte image, 7.5 s of 8 kHz noise). It is NOT approved or flashed.

**Partition 2 is unproven at three links**: a write above 16 bytes (only 16 bytes ever committed), whether p2 is visible to `FileFind` at all, and whether `PartitionMountFilesystem` can ever succeed on a RAW_SERIAL-typed partition (it returned FALSE twice). It also needs a data_us staging that garbles every spoken prompt while it is on the speaker, and an erase whose worst case is not excluded by measurement. The owner has not answered the decisions that gate it (RETURN-CHECKLIST section 5, D1, D2, D10-D13).

**Loop seams and rate.** Each chunk is a fresh transform that starts from predictor 0, so a seam is clean only if the file ends near zero; the generator rotates the loop to a zero crossing and the offline seam test says inaudible in principle (not heard). The first chunk after we start pressing played at about 8 kHz and later chunks at the rate we send; the cause is unknown, so 8000 Hz material is a bet that probe181 tests.

**Standing owner constraints**: software only, no SPI, no opening the speaker; the owner's ear judges the sound; never assume the driver cannot reproduce brown noise (the owner's streamed brown noise sounds excellent on it).

---

## 2. KEY FACTS

### 2.1 Prompts and ids

| fact | confidence | source |
|---|---|---|
| There are 64 request ids, 0x00-0x3F, all identified by the owner by ear (probe38 sweep, anchored by "english" = 0x16 and "ready to connect another device" = 0x35, 31 presses apart, consistent). | proven | `docs/request-id-catalog.md`; `docs/field-log.md:1125` |
| 57 ids speak; 7 are empty stubs (0x02 0x03 0x05 0x07 0x0f 0x1a 0x1d). No id is a tone, chime or drone, so nothing sustained exists in the id space. | proven (ear + stub match) | `docs/deep/offline-2026-10-10/promptmap.md` section 1.3; catalog "What this tells us" |
| The 0x00-0x3F prompt ids are a different space from the 0x4xxx sink events, and from the 0x3e9-0x3f2 request-API phrase family. | proven (catalog note) / well-supported (3e9 family) | catalog header; `docs/sink-events.md`; `docs/bose-firmware-anatomy.md` section 18 |
| Request id N reads `rphrases_us` table entry N+1. The lookup is in code (`fn_1ee80`, 0x1ee80); the 7 empty ids land exactly on the 7 stub entries. | proven (lookup, 7 matches); well-supported (all ids) | promptmap.md section 1.3 |
| Two catalog ids do not follow N+1: 0x0b (long stereo-pairing sentence = entry 65) and 0x11 (chain of entries 18 + 54). | hypothesis | promptmap.md section 1.4 |
| `rphrases_us` is the NowSpeakTTS phoneme script: word 0 = 147 entries, then per-phrase payloads (unit bytes 1..43, 0xff = word break, prosody bytes). It is NOT an (offset, length) directory into `data_us`. | proven | promptmap.md section 1; `python tools/promptmap.py --selftest` (44 checks, re-run today) |
| `data_us` is a two-region voice database (header, 15-entry region-B header E0..E14, phoneme table, unit groups, frame store, region A of 135,144 bytes whose role is undecoded). It is not PCM. | proven (parse); region A role unknown | promptmap.md section 2 |
| The speech DSP (`NowSpeakTTS.kap`) reads `data_us` itself from flash; the VM reads only single header words. E2 (header word) is the phoneme-table base the DSP adds for every unit. | well-supported | promptmap.md section 3 |
| A cave speaks an id by calling the VM request API, `BSR 0xDF7F` with the id in AL (gate: `@0x570` bit 13, else the request is dropped silently). | proven (hardware, used in every probe since probe99) | `build/hook/assemble_probe178.py:61,351`; `docs/bose-firmware-anatomy.md` section 3 |
| While our transform holds port 3, a SPEAK is silent at best (probe173: "no voice prompts" while our transforms held the port). | proven (observation); mechanism well-supported | `docs/field-log.md:13002` item 3 |

### 2.2 Filesystem and streamable files

| fact | confidence | source |
|---|---|---|
| Internal fs (3.0.3) has 7 live files: `vm.app`, `NowSpeakTTS/data_us`, `NowSpeakTTS/NowSpeakTTS.kap`, `sbc_decoder/sbc_decoder.kap`, `soundClearNb/soundClearNb.kap`, `soundClearWb/soundClearWb.kap`, `tts/rphrases_us`. | proven (dumpfs re-run today) | `python tools/csr/dumpfs.py firmware/bose/minnow_3.0.3/Minnow_3.0.3_stack_plus_app.dfu OUTDIR` |
| Flags: `data_us` 0x00 and `rphrases_us` 0x00 (narrow). Every `.kap` and `vm.app` is 0x40 (code). | proven (dumpfs output today) | same; `docs/deep/offline-2026-10-10/material-slots.md` section 0 |
| `StreamFileSource` returns 0 for any file that is not narrow, so exactly two files can be a stream payload. | proven (header quote) | `adk/root/tools/include/firmware/stream.h:312-318` |
| The file directory matters: `FileFind(dir "NowSpeakTTS", "data_us")` and `FileFind(dir "tts", "rphrases_us")`. probe176 used the wrong directory and got FILE_NONE (0x1B). | proven (press) | `docs/field-log.md:13244` |
| No inter-file slack exists; files are adjacent. | proven | `docs/content-control-analysis.md` section 2 |
| The external fs (`ext_flash.bin`, own signature) holds `ext_version` (11 bytes) and 12 language packs `data_XX` / `rphrases_XX` (bp fr ge it jp kr mc ms nl po ru sv; largest `data_ru` 255,390 bytes). Flags are reported 0x00. | proven (names, sizes: file listing); flags well-supported | `firmware/bose/extracted/ext_fs/` (names and sizes); material-slots.md section 2(A) |
| The language packs are NOT on the speaker now: the partition-2 erase of probes 140/141 removed them, and a stock reflash leaves p2 alone. What p2 holds now is unknown. | well-supported | material-slots.md section 2(A); `docs/RETURN-CHECKLIST.md` section 4.3 |

### 2.3 ADPCM and tools

| fact | confidence | source |
|---|---|---|
| The ADK encoder dialect is CWI/audioop IMA ADPCM: 4 bits per sample, no header, no framing, no length field, state starts (0,0), first sample in the HIGH nibble, standard 89-entry step table. | proven (tool side) | `docs/deep/offline-2026-10-10/adpcm-format.md` sections 1-3, 10 |
| `tools/adpcm.py` reproduces the ADK `voice_prompt_tool.exe` byte for byte on test signals (2,000/2,000; 3,000/3,000; 5,001-sample odd case) and 16 vendor `.prm` files (33,504/33,504 bytes on the 8 with a matching WAV). The textbook quantiser agrees on only 65 % of bytes: the dialect is the CWI coder. | proven | adpcm-format.md section 10; `python tools/adpcm.py --selftest` (OK today) |
| The device's own decoder (stack image, function at stack word 0x59cec) reads the high nibble first and uses the standard step/index tables; its state is two words in the transform node. | proven (instruction text, static) | `docs/deep/offline-2026-10-10/stack-transform.md` section 3 |
| A new transform starts from predictor 0, index 0 (node zero-filled; fill count not traced); nothing carries between chunks. | well-supported (start value); proven (no carry) | stack-transform.md section 3; REVIEW-part2.md X6 |
| `TransformAdpcmDecode` yields 2 samples per byte, 4 words of output per input byte. | well-supported (rate by ear and probe128's 126 ms); proven (word counts, static) | stack-transform.md section 3; `docs/field-log.md:7833`; verify.md V5 |
| `tools/brownnoise.py` makes loopable brown-noise payloads (leaky integrator, high-pass, equal-power crossfade, zero-crossing rotation, peak, encode from (0,0), decoded WAV preview). `--selftest` OK today (brown round-trip SNR 23.0 dB). | proven (offline tool) | `tools/brownnoise.py`; adpcm-format.md sections 4, 11 |
| Whether a designed brown stream sounds like the owner's streamed brown noise through this decoder and driver is not known; only the owner's ear can say. | unknown | RETURN-CHECKLIST section 6.1 |

### 2.4 The as-is corpus as material

| fact | confidence | source |
|---|---|---|
| Decoded as ADPCM, `data_us` is 43-62 % railed per 40 KB window, -1.6 dBFS rms, power spectrum falling about 3.5 dB per octave (pink-ish, flatter than brown). `rphrases_us` is 36 % railed, -2.4 dBFS. The harshness is best explained by clipping. | measured (offline model); firmware decoder well-supported to match | verify.md V10 |
| Heard on the speaker: probe155 "noise. fairly loud" (cut at about 7 s by the Bluetooth pairing teardown); probe174 "terrible quality, very abrasive and loud" (data_us at 2 kHz, word b = 0, so material and level are confounded). | proven (quotes) | `docs/field-log.md:11535`, `:13112`; verify.md V10 point 3 |
| Durations by arithmetic (2 samples per byte): `data_us` 54.9 s at 8 kHz, 219.5 s at 2 kHz; `rphrases_us` 2.62 s and 10.49 s. Heard for `rphrases_us`: about 3 s (first chunk) and about 12 s (second). A `data_us` chunk has never been timed. | proven (arithmetic); well-supported (match to ears) | verify.md V10; `docs/field-log.md:13315` |

### 2.5 Writing chosen bytes

| fact | confidence | source |
|---|---|---|
| A signed-DFU edit can change only bytes 34..62 of every 64-byte block of the filesystem: 29 bytes, then 35 untouchable, everywhere. | proven (code, probes 8 and 9 flashed and read back) | `tools/fsedit.py:97-101`; verify.md V2 |
| Interleaving our bytes with the stock bytes does not make noise: random or real stock bytes drive the ADPCM step index to 80..88 and play at about -5 dBFS with 20 %+ clipping, even with a state-aware encoder. Closed on content. | measured (offline) | adpcm-format.md sections 6, 9 |
| An all-zero stock region would be a sample-and-hold and would work roughly, but no zero-filled narrow region exists. | measured (zeros case); negative well-supported | adpcm-format.md section 6 point 2; DESIGN.md section 8 item 19 |
| The dead-code region (0x2331e..0x235a9, 207 writable words + 14 stubs) is code, not data-addressable, so it cannot be a `StreamRegionSource` payload. The const pool is data-addressable but offers only about 197 chosen bytes (about 0.05 s). | proven (address map); proven by arithmetic | `docs/message-task-abi.md` section 4; material-slots.md section 2(B); verify.md V2 |
| `.kap` files and `vm.app` are flags 0x40: not streamable, so sacrificing them gains nothing. | proven | material-slots.md section 2(A) |
| `SourceMap` on a file source returns one byte per 16-bit data word; `SourceSize` is uint16, so a >64 KB file is read through a window advanced by `SourceDrop`. | proven (decode of `fn_1ee3d`; header) | `docs/deep/prompt-audio-pump.md` section 3; DESIGN.md section 8 item 13 |

### 2.6 Partition 2

| fact | confidence | source |
|---|---|---|
| Bose's updater maps image type 4 to partition 2 (`fn_187e7`); p2 held the external language filesystem. Nothing else is known about its geometry (the map lives in curator config, never dumped). | proven (code); inference (language packs) | `docs/partition-route.md` section "CORRECTION, 2026-10-06" |
| p2 TYPE reads 3 (RAW_SERIAL) via `PartitionGetInfo` (probe139). | proven (press: "battery 70%") | verify.md V11 |
| `StreamPartitionOverwriteSink(1,2)` + digest SKIP + `SinkClose`, with an 8-word (16-byte) write, commits and reads STATE VALID (probe140). Every other claim about commits is retracted: no write above 16 bytes has an established result. | proven at 16 bytes; larger unproven | verify.md V11; DESIGN.md section 8 items 12a, 12c |
| The write is dense (no 29/64 cap), because the cave gathers the staged bytes from a file and flushes them contiguously. | well-supported (design); not established by any press | material-slots.md section 2(C); verify.md V11 point 1 |
| `StreamPartitionOverwriteSink` erases the whole target partition on open and, if misaligned, neighbouring sectors. A misaligned erase reaching a loader-adjacent sector is the one unbounded failure. Two clean erases are on record (Bose's updater, probe140). | proven (header); risk not excluded by measurement | `docs/partition-route.md` "What makes it unsafe today" and "Recovery" |
| `PartitionMountFilesystem(1,2,LOWER)` returned FALSE twice (probes 143, 144) and an unmounted `FileFind` found nothing. Cause open: (a) probe141's content was garbage, (b) a RAW_SERIAL partition refuses a filesystem mount. | proven (observation); cause open | verify.md V11; payload-184.md sections 0, 4 |
| probe141's staged gather started at data_us word 11 but the staging was at word 9, so its p2 content was ROFS words 2..13 plus 2 stock words per period: never a valid ROFS. This removes "the gather read what was staged" from the evidence of 143/144. | proven (arithmetic on the committed DFU); hardware effect hypothesis | `docs/deep/offline-2026-10-10/payload-184.md` section 0 |
| No VM code mounts p2: both `PartitionMountFilesystem` call sites (0x0a340, 0x1193f) use partition 0. There is no direct evidence that p2 content ever reaches the union filesystem. | proven (call sites); premise of probe185a unsupported | verify.md V11 "FALSE mount" and corollary |
| p2 cannot be read back by any known channel. | well-supported | `docs/partition-route.md` STATUS block |

### 2.7 Chunk, seam, rate, level

| fact | confidence | source |
|---|---|---|
| When a file source is fully consumed, the stack disposes the whole transform chain synchronously. `TransformFromSink(StreamKalimbaSink(3))` is then 0 while the DSP may still hold audible tail. So a poll sees "free" EARLY, by design. How early is unknown. | proven (static); lead unknown | stack-transform.md sections 4, 5 |
| `TransformStop` on the downstream node returns `Panic(0x4030)`: the best reading of the probe174/175 crash cause. Rule stays: no Stop/Disconnect in a loop image. | Panic decode proven (static); as the crash cause well-supported, not yet pressed | stack-transform.md section 8 |
| Seam test, reset case (fresh transform per chunk): seam step 2..183 against p99 sample steps of 1,939..4,684 for the six slot-sized payloads. Inaudible in principle; not heard. | measured (offline model) | adpcm-format.md section 11 |
| First chunk after we start pressing played at about 7-8 kHz (3 s for 2.62 s predicted); the next at our 2 kHz (about 12 s for 10.49 s predicted). n = 2 first presses, n = 1 second press, by ear. | observed | `docs/field-log.md:13315`; verify.md V5 |
| `0x1072` word a = rate in Hz, applied at once to the tone rate and copy-timer; word b bit 1 selects cbops shift 4 instead of 7: b = 2 is 18 dB quieter. Honoured on the very first and second chunk (probe178 "Quieter on Both"). | proven (decode + ear) | DESIGN.md section 8 item 5; `docs/field-log.md:13394`; `docs/kalimba-disasm.md` |
| Loudness did not track the volume buttons or music volume in one hedged ear report. | hypothesis | verify.md V4 |

---

## 3. How it works

### 3.1 The prompt pipeline (what happens when id N is requested)

1. Any VM code, including our cave, calls `fn_0xDF7F(id)`. It stores the id in `@0x503`, drops it silently unless `@0x570` bit 13 is set, builds a message and hands it to the audio engine gateway (`bose-firmware-anatomy.md` section 3).
2. The engine loads `NowSpeakTTS.kap` (`fn_1e3c5`: `VmDeepSleepEnable(0)`, `KalimbaLoad`, DAC at 16 kHz, DSP port 0 to DAC, GO) (`docs/deep/prompt-audio-pump.md`, "What actually speaks").
3. `fn_1ee80` reads `rphrases_us` entry N+1 and sends its phoneme units and prosody bytes to the DSP with `KalimbaSendLongMessage` id 0x6000 (promptmap.md section 1.1).
4. The DSP reads `data_us` per unit, using the 15 header entries it copied at init, and renders speech (promptmap.md section 3).

**Disagreement, recorded not resolved.** `prompt-audio-pump.md` (decode, 2026-10-04) says the live prompt uses no transform and not port 3: its output goes through DSP port 0 to the DAC. The probe173 analysis (`docs/field-log.md:13002`, 2026-10-08) says prompts are mixed through port 3 when `sbc_decoder` is live, an inference from hearing no prompt while our transforms held the port. The first is older and from code; the second is newer and from one observation. The rule "never SPEAK while our transform holds port 3" stands on the observation either way.

### 3.2 What is on the filesystem

| path | bytes | flags | streamable | role |
|---|---|---|---|---|
| `NowSpeakTTS/data_us` | 219,528 | 0x00 | yes | voice database (not PCM) |
| `tts/rphrases_us` | 10,486 | 0x00 | yes | phoneme script, 147 entries |
| `NowSpeakTTS/NowSpeakTTS.kap` | 31,076 | 0x40 | no | prompt DSP app |
| `sbc_decoder/sbc_decoder.kap` | 69,994 | 0x40 | no | A2DP music DSP; owns the tone port 3 we use |
| `soundClearNb/soundClearNb.kap` | 56,186 | 0x40 | no | hands-free call DSP, narrowband (well-supported) |
| `soundClearWb/soundClearWb.kap` | 65,242 | 0x40 | no | hands-free call DSP, wideband (well-supported) |
| `vm.app` | 522,026 | 0x40 | no | the VM application |

The tree directories matter: the flat `firmware/bose/extracted/internal_fs/` folder hides them; `python tools/csrdfu.py extract` or `tools/csr/dumpfs.py` shows the tree. Names are matched by `FileFind(dir, name, len)`; leading and trailing separators are ignored (header `file.h`); whether the compare is case sensitive is unknown (payload-184.md section 2).

A cave carries a file name as a string in its code: the blind bands are 14, 9 and 3 words wide, so a path like `NowSpeakTTS/data_us` (20 words) is split into two `FileFind` calls, and short names come from copies already in the firmware const pool (`docs/deep/stock-helpers.md`; material-slots.md section 2).

### 3.3 data_us and rphrases_us in one paragraph each

`rphrases_us` (10,486 bytes = 5,243 little-endian words): word 0 = 147; words 1..147 are entries giving the word offset of each phrase payload (entries 81 and 134 are 0); a payload is a header word (low 14 bits = unit count N; bits 0x4000/0x8000 = extra arrays), N unit bytes, a pad word if N is even, N prosody bytes and optional arrays. Entry 1 is "ready to connect" (id 0x00). The computed payload sizes tile the whole file (proven by selftest).

`data_us`: word 0 = 2 (regions), then region base words; region B (bytes 18..0x149a0) carries a 15-entry header `E0..E14`, a 44-entry phoneme table at 0x120, 43 unit groups, a 68,472-byte frame store and an 80 x 52-byte array; region A (0x149a0 to the end, 135,144 bytes, 64 % of the file) is a second structure nobody decoded. Run `python tools/promptmap.py --regions` for the map.

### 3.4 Spoken ids as probe outcome channels

The technique ("make the bails speak", `docs/bose-audio-path.md` section 7): a cave ends every branch by speaking a different catalog id, so one press reports which branch ran. FLASH-PROTOCOL step 5 requires a distinct id for every path including success, and no id that collides with a stock prompt in that state.

How it has been used:

| probe | ids used | meaning |
|---|---|---|
| 170, 171 | 0x3A "heart rate not detected", 0x3C "adjust left airbud" | success marks chosen because the stock never says them on this speaker (`docs/field-log.md:12756`, `:12836`) |
| 172 | 0x17 | spoken by the cave only on the centre long press (`docs/field-log.md:12923`) |
| 139, 140 | battery 70 % = TYPE 3; battery 10 % = STATE VALID | read the partition ABI (verify.md V11) |
| 143, 144 | battery 30 % (state report; sinkState = 2 in 143), then 0x12 "voice prompts on" = mount FALSE | `docs/partition-route.md` lines 573 and 597; verify.md V11 |
| 174-178 | failure ids 0x3E (no DSP / gate FALSE), 0x10 (no sink), 0x22 (directory), 0x1B (file), 0x24 (source), 0x25 (transform); success speaks NOTHING | SPEAK would collide with our own transform on port 3 (probe155 header; assemble_probe178.py:288) |
| 179-181 (built, not flashed) | 0x26 "ended" success, 0x21 gate FALSE, plus the failure set | RETURN-CHECKLIST section 2.2 (its own table) |
| 182-185 (specs only) | 0x27 + class battery ids; 0x1B / 0x2A / 0x2B / 0x13 | each probe carries its OWN table (`docs/deep/offline-2026-10-10/REVIEW-part2.md` section 5) |

**Collisions and ambiguities.** Every press page must carry its own id table; never reuse a table from another probe.

- Stock prompts the speaker says by itself: 0x09 "mobile device not found" and 0x00 "ready to connect" (FLASH-PROTOCOL step 5); the power-on battery announcement (0x27-0x30, observed); 0x31 "battery low" and 0x32 "battery full" on battery events; "english" 0x16 on the language gesture (promptmap.md section 6).
- 0x3E "bluetooth off" is also the stock's own Bluetooth-off prompt; probe177 heard an unexplained beep after it.
- The call family 0x21, 0x22, 0x24, 0x25, 0x1B is ambiguous if an HFP call (Teams on the laptop) is active during a press (`docs/deep/offline-2026-10-10/README.md`, F8).
- Battery-family ids mean different things in probes 182, 183 and 184, and 0x2A/0x2B mean "battery 40/50 %" in 182 but "found" in 185. 0x21 means "failure" in 179 press A and "expected" in press B.
- Two sound-alike pairs: 0x08 and 0x0d are both "disconnected", 0x19 and 0x1c are both "call from". Never use both in one plan.
- 0x25 merges two causes (decode refused, start refused) in probes 178-181: a lost bit, not a collision (REVIEW-part2.md O7).
- The 7 empty ids cannot be outcome ids; they speak nothing.
- In the staged probe184 image no spoken id is reliable (section 3.9), which is why the plan uses two images.

### 3.5 Streaming a file into the audio path

```
dir  = FileFind(FILE_ROOT, "NowSpeakTTS", 11)       ; or "tts" for rphrases_us
file = FileFind(dir, "data_us", 7)
src  = StreamFileSource(file)                        ; 0 unless the file is narrow
t    = TransformAdpcmDecode(src, StreamKalimbaSink(3))
TransformStart(t)                                    ; the firmware pumps it; the VM may return
```

Before this, the cave sends `KalimbaSendMessage(0x1072, rate_Hz, level)` (gate: TRUE only if a `.kap` is loaded, i.e. music is playing; purges the port's tone buffer, so never re-send it to a running port). Before touching port 3 the cave reads `TransformFromSink(StreamKalimbaSink(3))`: nonzero means busy, do nothing. Rules from the 2026-10-08 runaway: durations from size x rate, never from a teardown-era number; no timer re-arm until a chunk's end is detected; no Stop, Disconnect or StreamDisconnect on a running transform; no SPEAK while we hold the port (memory note `csr8670-port3-chunk-rules`; DESIGN.md section 8 item 4).

### 3.6 ADPCM format and the tools

Format: see the first row group of section 2.3. In practice a payload is a flat byte file; duration = bytes x 2 / rate; no header and no padding requirement is known on the device (the ADK tool pads `.prm` files to an even length; every payload here is even).

| tool or folder | what it does | run |
|---|---|---|
| `tools/adpcm.py` | encode/decode in the device dialect, `--prm` even padding, `--selftest` | `python tools/adpcm.py --selftest` |
| `tools/brownnoise.py` | brown-noise payload + WAV preview + report; `--bytes N` fills a slot exactly; `--seam-test`; `--interleave` models the closed blind-window route | `python tools/brownnoise.py --rate 8000 --bytes 30000 --loop` |
| `tools/promptmap.py` | id to phrase to data_us bytes; what a staged payload garbles | `python tools/promptmap.py --selftest` |
| `tools/csr/dumpfs.py`, `tools/csr/csrfspack.py` | read / build the `fsr_dfu1` filesystem (flags byte printed) | `--list`, `--roundtrip` |
| `build/payload/make_narrow_payload.py` | the probe184 ROFS with one narrow file, verified three ways, staging plan | `python build/payload/make_narrow_payload.py` |
| `build/brownnoise/` | example payloads at 2000 and 8000 Hz (`.adpcm`) with decoded `.wav` previews, interleave experiments `il_*` | listen to the WAVs |
| `build/noise/` | slot-sized payloads (10,486 / 65,242 / 219,528 bytes) at both rates, `*_at8000.wav` previews, `il_*` | same |
| `build/payload/narrow184/` | the exact probe184 payload and image (30,000-byte `brown_8000_30000.bin` = 7.50 s, `narrow_fs.bin` 30,268 bytes) | see payload-184.md |
| `build/pcm/` | earlier raw-PCM brown payloads (legacy PCM-injection route) | legacy |
| `build/payload/make_payload.py`, `stage_payload.py` | LEGACY probe141 builders; staging window is 2 words off (use 9..22, not 11..24) | do not use |

Previews are the decoder's output BEFORE the DSP tone path, shift, resampler and mix: screening, not judgement. The owner's ear decides (RETURN-CHECKLIST section 6.1 lists the files to listen to first).

### 3.7 Material options, ranked

| rank | material | how chosen bytes get there | length | status | verdict |
|---|---|---|---|---|---|
| 1 | self-authored narrow file on partition 2 | partition write (dense by design) | up to the partition; planned 30,000 bytes = 7.5 s at 8 kHz | payload built and verified offline; write, visibility and mount all unproven; NOT approved | the only route to designed, clean brown noise; blocked at the device |
| 2 | `data_us` as-is | none | about 55 s at 8 kHz, 220 s at 2 kHz (arithmetic) | chain proven (probe155) | works today but plays as harsh, clipped noise; a stand-in; a 220 s unstoppable chunk is worse than the 10 s `rphrases_us` |
| 3 | `rphrases_us` as-is | none | 2.62 s at 8 kHz, 10.49 s at 2 kHz | the probe177/178 stand-in on the speaker now | short, not chosen; fine for proving loops |
| closed | `data_us` chosen bytes via the blind window | signed DFU, 29 of 64 | 219 KB slot but chopped | route D | 29 bytes mine then 35 Bose's about 1,700 times: ruins brown noise; also kills boot and diagnostic prompts |
| closed | interleaved payload over stock bytes | same | same | measured | decodes as a -5 dBFS roar gated at 15.6 or 62.5 Hz |
| closed | any `.kap`, `vm.app`, dead-code region | - | - | flags 0x40 / not data-addressable | cannot be a stream source |
| closed | const pool as a region source | cave words | about 197 bytes (0.05 s) | - | too small to sustain |
| closed | ext `data_xx` | - | - | absent from the speaker (erased) and still needs a partition write to restore | no use |
| closed | in-cave generator refilled by timer | - | - | probes 105/106 leaked stream objects and crashed; the refill loops of 145-151 ended at the ~7 s pairing teardown | superseded by the file chain |
| parked | app-mode USB update to partition 0 | USB protocol (not reverse-engineered) | whole main fs | wipes the cave | parked, destructive |

Why the interleave was closed: the stock bytes between our 29-byte runs drive the ADPCM step index to its ceiling, and from there a short band of ours cannot bring it back; even the state-aware encoder only recovers our 45 % of the time against a loud roar for the other 55 % (adpcm-format.md sections 6 and 9).

### 3.8 Loop seam, chunk length and rate

**Seam.** The loop is a sequence of chunks. Each chunk is a fresh transform from state (0,0), so the sample step across a seam equals the last decoded sample of the file. `tools/brownnoise.py --loop` crossfades the tail into the head and rotates the file to start at its quietest zero crossing; the six slot-sized payloads show seams of 2..183 against typical steps of thousands (adpcm-format.md section 11). Other gaps are structural: the poll sees the free edge before the audible end (lead unknown), a 1 s poll grid adds 0 to 1 s of silence per chunk (RETURN-CHECKLIST D6), and the planned 7.5 s file would therefore pump audibly unless `POLL_MS` is cut; the ear decides.

**Durations.** bytes x 2 / rate: payload 30,000 bytes = 7.5 s at 8 kHz or 30 s at 2 kHz. A longer file means a longer stop latency, because the only safe stop is to let the chunk end.

**Rate.** `0x1072` word a sets the tone rate and takes effect at once. Observed: the first chunk plays at about 8 kHz whatever we send; later chunks follow us. The cause is unknown. The named mechanism "resampler cache" is struck: the rate sites in the DSP re-read the rate live. Probes 128-134 (first presses, rate 2000, heard about 126 ms, which fits 2 kHz not 8 kHz) are unreconciled counter-evidence. The plan authors at 8000 Hz and sends 8000 so that every chunk agrees; probe181 tests it with a stopwatch (pass: every chunk within about 14 % of 2.62 s and one pitch). Bandwidth is rate / 2, so 2 kHz material is 1 kHz-limited and gritty (23.5 dB SNR) but four times as long per byte; 8 kHz is 4 kHz-limited and cleaner (29.8 dB). This is a design trade, not a statement about the driver: never assume the speaker cannot reproduce low frequencies (owner correction 2026-10-08).

**Level.** Cut the material at peak 0.5 to 0.9 and set loudness with `0x1072` word b (0 loud, 2 about 18 dB quieter), not by making the material quiet.

### 3.9 The partition-2 route and its risks

Plan (DESIGN.md section 3, amended by RETURN-CHECKLIST sections 4.3 and 6):

1. Probe182: read-only census of the file-source window (does `SourceSize` limit the map, does `SourceDrop` advance it, SourceMap word packing).
2. Probe183: read-only p2 census (`IS_MOUNTED`, `STATE`, `SECTOR_SIZE`, plus `SIZE`); mandatory per verify.md V11 and decision D10 (recommended, unanswered).
3. Probe184: the ONE p2 write. Payload `build/payload/narrow184/narrow_fs.bin` (30,268 bytes: `/brown.adpcm` flags 0x00 + the official 11-byte `/ext_version`), staged into `data_us` words 9..22 of each 32-word period (1,081 periods = 23 x 47, data_us bytes 0..69,184 = 31.5 %), gathered by the cave and flushed 28 bytes at a time.
4. Probe185a: the loop pointed at `FileFind(1, "brown.adpcm", 11)` from the root, no mount; 185b adds `PartitionMountFilesystem(1,2,1)` on FILE_NONE. If it still fails and the cause is the RAW_SERIAL type, software is blocked (curator-config or SPI map edit, which the owner has ruled out): stop and say so.

Risks, named:

- **The erase.** One unbounded case: a misaligned erase reaching a loader-adjacent sector. Not excluded by measurement. Only one unit is left (unit 1 was lost 2026-10-04). Needs the owner's explicit go-ahead (D1).
- **Prompts garbled.** Staging overwrites `data_us` words 9..22, which are header entries E0..E6 including E2, the phoneme-table base. Under the read-set model all 57 speaking ids lose bytes at 8, 16, 30 and 65 KB. Expect garbled or silent prompts, possibly no audio, until a non-staged image is flashed. The 2026-10-06 total audio loss after probe141 has this as a second candidate cause beside the boot-time cave (hypothesis). Mitigation: the two-image plan (D12): a silent write press, then flash an image with stock `data_us` and read the result with working prompts. p2 keeps its content across a reflash (observed 2026-10-06).
- **First-of-kind run.** A 1,081-iteration claim/flush loop after a multi-second erase has never completed on hardware; VM watchdog behaviour is untested. Do not pull power during it.
- **Unknown geometry.** Whether `SourceMap` word i is file bytes 2i, 2i+1 (little-endian) and the real window size are exactly what probe182 settles; the gather assumes them.
- **Stale signature and digest** on the written fs; accepted as in probe140 (digest SKIP, proven at 16 bytes only).
- **The official updater** must not be run on p2 afterwards: it would restore p2 and erase the brown file (D3).

Alternatives if p2 stays blocked: USB protocol reverse engineering (also gives a p2 read-back; `docs/partition-route.md` STATUS) and a curator-config dump or map edit (needs SPI; out of scope by the owner's rule).

---

## 4. Open questions (and what settles each)

| question | status now | settled by |
|---|---|---|
| Does designed 8 kHz brown ADPCM sound like the owner's streamed brown noise through this decoder and driver? | unknown | probe185a; the owner's ear (previews first, section 3.6) |
| Is a chunk end seam audible at 7.5 s with a 1 s poll? | previews say inaudible; pump from the gap is likely | 185a, then `POLL_MS` experiments E3 |
| What is the file-source window and does `SourceDrop` advance it? | unknown (SourceSize is uint16) | probe182 |
| Is p2 in the union filesystem at all? Mounted at boot? | no direct evidence | probe183 (`IS_MOUNTED`) |
| Is the mount FALSE a bad gather or a type refusal? | both live | 184 + verify image, then 185a/b |
| Does a 30 KB p2 write commit and read STATE VALID? | never established (only 16 bytes) | 184 and the verify image |
| Why does the first chunk play at about 8 kHz? Does a = 8000 make it invisible? | cause unknown; a bet | probe181 with a stopwatch; optionally a = 4000 and a fresh-DSP press |
| What is a `data_us` chunk's real length at 2 kHz? | arithmetic only (about 220 s) | never worth a flash unless needed |
| What does region A of `data_us` do (does tail staging spare the prompts)? | undecoded | the fs-only head/tail test (promptmap.md section 8.3) |
| Do the staged header words really cause the 2026-10-06 audio loss? | hypothesis | the same fs-only press |
| Do prompts mix through port 3 or reach the DAC from the speech DSP's own port? | decode and observation disagree | a press with a prompt during a chunk (E2, deferred; worst case a recoverable reboot) |
| How much audio is lost when the chain is disposed at source EOF (the lead)? | unknown (buffer I size not resolved) | step 0 A1c/A2 and 179 press A |
| Does the device need an even byte count or any alignment? | no constraint known | a press with an odd-length payload; not worth a flash |
| Request ids 0x0b and 0x11: which entries do they use? | hypothesis | decode the id-to-entry step (not found) |

---

## 5. Traps and retractions

Do not carry these forward. The right column wins.

| claim you may meet | where it still appears | status | what wins |
|---|---|---|---|
| `data_us` is raw 16-bit PCM, 13.7 s at 8 kHz | `docs/content-control-analysis.md` sections 2 and 4; `docs/bose-firmware-anatomy.md` section 12 (banner corrects) | withdrawn | promptmap.md section 2: voice database, not PCM |
| `rphrases_us` is an (offset, length) directory into `data_us`; Route A "repoint a phrase" gives long babble | anatomy section 12; content-control section 3 | withdrawn | promptmap.md section 1: phoneme script; ids are entries N+1 |
| Catalog "anomalies": 0x2b and 0x2c read as empty | `docs/request-id-catalog.md` "What this tells us" point 4 | stale | only 7 ids are empty; catalog provenance paragraph; promptmap.md section 10 |
| `data_us` is about 60 s, or the decoder runs 3.5x fast | `docs/field-log.md:13286` result 1; material-slots.md rank 2 | retracted the next day | 2 samples per byte: 55 s at 8 kHz, 220 s at 2 kHz (verify.md V10) |
| A chunk is about 7 s | probes 104-171 era | the 7 s was the pairing teardown | size x rate (probe157; memory `csr8670-port3-chunk-rules`) |
| The as-is corpus has a "rising, bright" spectrum | design-mvp.md | withdrawn | falls about 3.5 dB per octave, 36-62 % railed; harshness is clipping (verify.md V10) |
| "PROVEN: dense p2 commit", "self-authored fs boot-tolerated", "the ext partition IS mounted" | material-slots.md rank 1; `docs/partition-route.md` banner and STATUS; field-log "What the day proved" | retracted | only 16 bytes proven; leftover bytes were tolerated, not a valid fs; no VM code mounts p2 (verify.md V11) |
| The 2026-10-06 mount FALSE is garbage from the gather | design-risk.md 3.2 | one of two live causes | type refusal (ADK `upgrade_fw_if.c:193-200`) is equally live |
| Staging window words 11..24 | `build/payload/stage_payload.py`, probe141, `tools/cavesim.py --staged`, probes 179-181 assemblers | wrong by 2 words | words 9..22, FIRST = 9 (payload-184.md section 0) |
| The nibble order is the one free parameter if the first p2 chunk roars | adpcm-format.md section 7, DESIGN.md | outdated | proven high nibble first on the device (stack-transform.md section 3); a roar would point at content or the write |
| The first chunk is slow because of a "resampler cache" | dsp-keepalive-rate.md B2 | struck | cause unknown; rate sites re-read live (verify.md V5) |
| Interleaving our bytes in the blind windows could carry noise | early route-D notes | closed | measured roar (adpcm-format.md sections 6, 9) |
| Sacrificing a `.kap` (soundClear, NowSpeakTTS) gives a payload slot | early file-slot ideas | moot | flags 0x40: `StreamFileSource` returns 0 |
| Language packs on p2 can be streamed | partition-route.md "ext fs IS mounted" | not present now | erased by probes 140/141 |
| The driver cannot radiate below 150 Hz, so the brown goal was redefined | field-log 2026-10-04 | refuted by the owner 2026-10-08 | the limits are in our path; the owner's ear judges |
| Spoken ids can report 184's result | design-mvp / DESIGN.md 184 id table | unreliable in the staged image | two-image plan (promptmap.md section 8.2) |
| `0x4xxx` and `0x00-0x3F` are the same "ids" | casual wording | different spaces | sink events vs prompt ids (catalog header) |
| probe104 ran about 12 s | material-slots.md | disputed | field-log table at `docs/field-log.md:11561`: 4.25 s by design (17 KB at 8 kHz) |

---

## 6. Rules this topic inherits (do not break)

- No flash, no `tools/flash_probe.py`, nothing over USB while the owner is away. The first flash on return takes every gate of `docs/FLASH-PROTOCOL.md`.
- Cave words stay in the 197-word window (`docs/cave-budget.md`; memory `csr8670-cave-window`).
- Probe 184 is neither approved nor built as an assembler; do not present it as planned work done.
- Do not open `private/` or any readback or dump (`*_readback.dfu`, `*.bin` dumps); they hold link keys.
- `docs/field-log.md` is append-only evidence.

---

## 7. Detailed knowledge: where to go for what

| question | read |
|---|---|
| The 64 prompt ids and wordings | `docs/request-id-catalog.md` |
| How ids map to phrases and to data_us; what staging garbles; the per-id table | `docs/deep/offline-2026-10-10/promptmap.md`; `python tools/promptmap.py --table` |
| How the request API and the audio engine are wired | `docs/bose-firmware-anatomy.md` sections 3, 9, 18 (check the banners) |
| What actually speaks, the dead stock prompt plugin, the file-source idiom | `docs/deep/prompt-audio-pump.md` |
| Which file can be a stream payload; the candidate survey and ranking | `docs/deep/offline-2026-10-10/material-slots.md` (read with verify.md V2, V10, V11) |
| The 29-of-64 blind window and what it rules out | `docs/content-control-analysis.md` section 1; `docs/deep/offline-2026-10-10/write-constraint.md`; `tools/fsedit.py` |
| ADPCM format, encoder proof, brown-noise numbers, seam test, interleave study | `docs/deep/offline-2026-10-10/adpcm-format.md` |
| The device's own decoder and transform lifecycle; why chunk ends read "free" early; why 174/175 crashed | `docs/deep/offline-2026-10-10/stack-transform.md` |
| Detecting the end of a chunk; the poll design | `docs/deep/offline-2026-10-10/chunk-end.md` |
| Keeping the DSP up; the rate latch (banner: parts stale) | `docs/deep/offline-2026-10-10/dsp-keepalive-rate.md` |
| Level control, stop and volume buttons | `docs/deep/offline-2026-10-10/controls.md`; `docs/kalimba-disasm.md`; `docs/gain.md` |
| The partition route in full, including the failed 2026-10-06 campaign | `docs/partition-route.md` (read its STATUS block with verify.md V11) |
| The probe184 payload and staging numbers | `docs/deep/offline-2026-10-10/payload-184.md`; `build/payload/make_narrow_payload.py` |
| The judged plan and the downgraded claims | `docs/deep/offline-2026-10-10/DESIGN.md` (sections 3, 8); `docs/deep/offline-2026-10-10/verify.md`; `docs/deep/offline-2026-10-10/README.md` (findings F1-F14) |
| The order of presses and flashes on return; owner decisions D0-D13 | `docs/RETURN-CHECKLIST.md` |
| Flash safety, readback, recovery | `docs/FLASH-PROTOCOL.md` |
| Why only 29 of 64 bytes are writable (the signature scheme) | `docs/topics/dfu-and-signing.md`; `docs/dfu-signature-scheme.md` |
| Audit of the offline plan (spoken-id audit, stale-doc list, open review items) | `docs/deep/offline-2026-10-10/REVIEW-part2.md` |
| Device, cave, hooks, DSP background | `docs/topics/hardware-and-firmware.md` |
| History of material attempts (probe104 region source, 105/106 refill, 128-134 generated noise, 141 staged write, 155 data_us, 173-178) | `docs/field-log.md:5546`, `:7833`, `:11457`, `:11535`, `:13002`, `:13112`, `:13315`, `:13394` |
| Trap stubs used on this route (FileFind, StreamFileSource, TransformAdpcmDecode, partition traps) | `docs/trap-stub-table.md` |
| String and const-pool tricks for file names | `docs/deep/stock-helpers.md`; `docs/const-strings.md` |

See also (strategy review 2026-10-12, offline, a recommendation; read the skeptic section of each note first): `docs/deep/strategy-2026-10-12/01-rich-material.md` (what 4-bit ADPCM does to a 1/f^2 spectrum, level headroom, rate and length; payload levels `docs/FACTS.md` F150 and F151) and `docs/deep/strategy-2026-10-12/06-red-team.md` (alternatives to the partition-2 file route, with `docs/deep/strategy-2026-10-12/STRATEGY.md` J-C1, J-C2 and J-C19).

See also (firmware study 2026-10-12, offline, static or model results; read the skeptic section of each note first; index `docs/deep/firmware-study-2026-10-12/README.md`, functions `docs/FUNCTION-CATALOG.md`): `T07-payload-study.md` (the integrator payload is +2.4 dB hot in the top octave; `tools/brownnoise.py --gen fft`; recommended file 60,100 B, seed 63, peak 0.985; previews in `build/payload/previews/`: `docs/FACTS.md` F202-F206) and `T08-184a-184-assemblers.md` (tail start 1,270 keeps all 57 speech ids in the model: F209).

## See also (round 3, 2026-10-12)

Added at the end so that no cited line moved. Round 3 is offline and static or model work; nothing was run on the speaker. Index and corrections register: `docs/deep/round3-2026-10-12/README.md`; the facts are in `docs/FACTS.md` section 10.

- `docs/deep/round3-2026-10-12/N01-inplace-hybrid-adpcm-stream.md`: streaming data_us in place with a hybrid ADPCM stream is dead for goals 1-3; the one 0.5 s pocket (F267-F270).
- `docs/deep/round3-2026-10-12/B02-payload-staging-final-size.md`: payload staging at the final size; the 58,700 B variant that spares the speech structures; header exposure (F292-F294).
- `docs/deep/round3-2026-10-12/V02-verify-payload.md`: independent decode of the 60,100 B payload (F295; not a flash clearance).
- `docs/deep/round3-2026-10-12/N02-dsp-noise-sources-and-shapers.md`: the rphrases_us blind geometry and the TTS synth chain (F273, F274); data_us is the NowSpeakTTS voice database (F279).

## See also (2026-10-28)

The product no longer plays recorded material: the noise is generated in the DSP (probe380), so the narrow-file/payload rules of this hub apply only to the retired recorded-noise products (probe318-367). The payload files remain in `build/payload/` as history.
