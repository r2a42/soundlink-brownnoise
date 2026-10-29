# Topic hub: the audio path and the DSP (A2DP, sbc_decoder, port 3, tone path, lifetime)

Purpose: one place to learn how sound gets out of the Bose SoundLink Micro, how our brown-noise chunk gets into that path, and which statements about it are proven, doubtful or retracted.

StreamFileSource streams only narrow files (flags 0x00): data_us and rphrases_us. See FACTS F112.

Status / last verified: 2026-10-10 (offline; the speaker holds probe178 and is not connected; nothing here was pressed after 2026-10-10 morning).

Read next: `docs/dsp-generator-route.md` and `docs/ring-buffer-fix.md` for this export's own current write-ups of the audio path in practice. (This page cites some deeper offline research-note folders not included in this public export; where a citation doesn't resolve, those two files are the up-to-date account.)

Confidence marks: proven (an address, instruction, command output or quoted press), well-supported (one stated inference beyond a proven fact), hypothesis, unknown. "Proven (static, not pressed)" means the instruction text says so but nothing was observed on the speaker.

---

## 1. Summary (one page)

**The stock path.** A phone or laptop streams A2DP. The BlueCore firmware strips the RTP header with a transform and feeds SBC frames into Kalimba (DSP) sink port 0. The DSP image `sbc_decoder.kap` decodes SBC, runs the music processing, mixes in any tone or prompt that arrives on DSP read port 3, and writes PCM to DSP write ports 5 and 6. The VM wired those two ports to DAC channels A and B. The VM never touches PCM; it only loads the DSP, wires streams and sends messages.

**Our path.** We do not make sound ourselves. From a small VM program (the "cave") we build a chain `FileFind -> StreamFileSource -> TransformAdpcmDecode -> StreamKalimbaSink(3) -> TransformStart` after telling the DSP the tone rate with message `0x1072`. The firmware decodes 4-bit IMA ADPCM bytes from a file in the flash filesystem and pushes the samples into port 3. The DSP resamples them to 48 kHz and mixes them into the music output. This is the only proven way to get arbitrary-content audio out of this speaker.

**What is proven on hardware.** A centre long press while A2DP is connected reaches our hook (`0x00e46`), starts one chunk through port 3, and the chunk plays loud for as long as the file lasts, with the stock DSP alive (probes 172, 174, 175, 177, 178). With music playing, the next press after a chunk ends builds a second chunk (n=2). The `0x1072` word b selects a quiet level or a loud level 18 dB apart (probe178). The pairing-teardown "7 second" ceiling of probes 104-171 was the Bluetooth-button hook, not the audio path.

**What is not proven.** Looping (never pressed beyond two chunks), the busy read of a running transform, sustain with music paused (the DSP unloads), the first-chunk rate anomaly, what level does when the volume buttons move, and whether real brown-noise material sounds right through this path. Probes 179-181 (poll loop, STOP, rate 8000) are built and gated offline, not flashed.

**What is closed.** Reloading the DSP from the cave (probes 162-171: every stock message accepted, DAC silent). Writing PCM into the DAC sink. A region or ringtone source connected straight to the port without a transform. Any `.kap` of ours (cannot be written into the signed image). Asking the DSP to synthesise noise (it has no generator). Stopping a running chunk with the stock teardown (probes 174/175 restarted the speaker; the cause is now known, section 4.3).

**Hard rules that come from this topic** (section 5.2): compute chunk durations from file size and rate; read `TransformFromSink(StreamKalimbaSink(3))` before touching port 3 and do nothing if nonzero; never `TransformStop` a node you got from `TransformFromSink`; never SPEAK while our transform holds port 3; never re-arm on a timer without a detected end.

---

## 2. KEY FACTS

### 2.1 Wiring and what plays

| # | fact | confidence | source |
|---|---|---|---|
| 1 | On this speaker the stock connects DSP write port 5 to DAC channel A and write port 6 to DAC channel B (hardware type CODEC 3, instance 0), muted at connect then unmuted, via `fn_1f04c`. The A2DP teardown `fn_31734` calls `fn_1f12b` (AudioOutputDisconnect), which closes both DAC sinks. | proven (decode) | `docs/deep/dsp-output-wiring.md` "Answer in one paragraph", "The teardown undoes it" |
| 2 | The DSP side agrees: sbc_decoder's output chain checks write ports `0x800011`/`0x800012` (ports 5 and 6); the tone buffer drains only through that output chain. | proven (decode) | `docs/field-log.md:11959` item 5 (read from the PM-flash overlay) |
| 3 | The A2DP input end (RTP decode transform into Kalimba sink 0, codec chosen by `fn_315bb`) was identified by matching `fn_31af3` to the ADK `MusicConnectAudio`. | well-supported | `docs/deep/dsp-output-wiring.md` table "How fn_31af3 maps"; `docs/firmware-map.md` "The seven DSP-load sites" |
| 4 | Of the four DSPs on the device only `sbc_decoder.kap` registers the `0x1070`-`0x1080` tone family; `NowSpeakTTS`, `soundClearNb`, `soundClearWb` have none of those immediates. A computed id would not show in an immediate scan. | well-supported (strong) | `docs/kalimba-disasm.md` "The decisive negative" and the method caveat after "Correction: no 0x10xx at all" |
| 5 | `sbc_decoder` is loaded only by the A2DP media-connect machine (`fn_315e7` at `0x316ce`, driven by `fn_30ddd`), which needs a real media stream. No standalone (no phone) DSP with a tone port exists. | proven (decode) | `docs/firmware-map.md` "The seven DSP-load sites" |
| 6 | Kalimba port 3 is the port the firmware mixes tones and voice prompts into (`TONE_VP_MIXING_DSP_PORT`); port 0 is the decoder's own input. Bose's own tone recipe is at `0x31A7C`: `KalimbaSendMessage(0x1072, 8000)`, `StreamKalimbaSink(3)`, `MessageSinkTask`, `StreamRingtoneSource`, connect. | proven (decode + ADK header) | `docs/bose-audio-path.md` section 8 |
| 7 | The working chain is `KalimbaSendMessage(0x1072)` -> `FileFind` x2 -> `StreamFileSource` -> `TransformAdpcmDecode(src, StreamKalimbaSink(3))` -> `TransformStart`. First produced by probe155 (data_us) and used unchanged through 174-178 (rphrases_us in 177/178). | proven (press) | `docs/dsp-noise-route.md` update banner; `docs/field-log.md:13286`, `docs/field-log.md:13394`; `build/hook/assemble_probe178.py` |
| 8 | `StreamFileSource` returns 0 for any file that is not NARROW. Only `NowSpeakTTS/data_us` (219,528 B) and `tts/rphrases_us` (10,486 B) are narrow; every `.kap` and `vm.app` is flags `0x40`. | proven (header + own `dumpfs` run) | `docs/deep/offline-2026-10-10/verify.md` section V2; `docs/deep/offline-2026-10-10/material-slots.md` section 0 |
| 9 | A transform is mandatory. A region or ringtone source connected straight to the tone port was silent (probes 101/102); the same bytes through `TransformAdpcmDecode` were loud (probe104). Writing PCM into an audio sink has no precedent in the ADK or Bose and is closed. | proven (press) | `docs/field-log.md:5546`; `docs/bose-audio-path.md` correction banner and section 2 |

### 2.2 Messages, rate, level

| # | fact | confidence | source |
|---|---|---|---|
| 10 | The `0x1072` handler (PM `0x1761`-`0x1788`) takes word a = tone rate in plain Hz (written to `M[0xff83f2]`), derives the copy-timer period `M[0x2aac]` as K / rate (doubled for mono), writes the shift (b bit 1 clear -> 7, set -> 4) into `M[0x29e6]` and `M[0x29cc]`, copies write pointers over read pointers (purging the tone buffers) and sets `M[0x2aa6] = 1` (port armed). | proven (decode) | `build/analysis/kalimba/sbc_decoder.disasm.txt` lines for `80001761`-`80001788`; `docs/deep/offline-2026-10-10/dsp-keepalive-rate.md` B1 |
| 11 | Bose's shift is 7 / 4, not the ADK's 11 / 8. Unity 16-to-24-bit alignment is 8, so both settings are below unity and b = 0 is the louder one by 3 bits. Nothing saturates. | proven (decode) | `docs/kalimba-disasm.md` "THE CORRECTION"; `docs/field-log.md:8063` |
| 12 | `0x29e6` is the shift field of the mono tone-copy cbops operator (DM init record at `0x29c7`, value 7 at boot). | proven (decode of the init data) | `docs/deep/offline-2026-10-10/verify.md` section V4 point 2 |
| 13 | probe178 (b = 2) was heard quieter than probe177 (b = 0) on both chunks (owner: "Quieter on Both"). | proven (press, ear, n=2) | `docs/field-log.md:13394` |
| 14 | The step is 18 dB at the cbops output (3 bits). The acoustic ratio was not measured and a limiter downstream is not excluded. Changing b between consecutive chunks has never been tried. | well-supported / unknown | `docs/deep/offline-2026-10-10/verify.md` section V4 (a), (b) |
| 15 | Loudness is independent of the volume buttons and the music volume. | hypothesis (one hedged ear report: "does not appear to be impacted") | `docs/field-log.md:13315` item 3; `docs/deep/offline-2026-10-10/verify.md` section V4 (c) |
| 16 | The `0x1002` main-volume handler (PM-flash `0x3468`) copies the 8-word block verbatim into DM `0x29a9`-`0x29b0`. No instruction addresses that block literally, so what the DSP does with the tone word is not shown offline. A plain `0x1002` long send from the cave is safe (probe168, TRUE, no crash) but its loudness effect was never heard. | proven (decode) for the copy; unknown for the effect | `docs/deep/offline-2026-10-10/controls.md` section 5; `docs/field-log.md:12596` |
| 17 | `0x1070` carries the DAC rate divided by 10; the handler multiplies by 10 into `M[0xff83f1]` (output rate 48000). | proven (decode) | `build/analysis/kalimba/sbc_decoder_flash0_slot2959.disasm.txt` lines `8000314a`-`8000314c`; `docs/deep/offline-2026-10-10/dsp-keepalive-rate.md` B4 |
| 18 | The tone resampler mixes when output rate >= 0.9 x input rate and ignores the tone otherwise, so input rates up to about 53 kHz are accepted. | well-supported (ADK `resample_header.h`, Bose handler read) | `docs/deep/offline-2026-10-10/dsp-keepalive-rate.md` B4 |
| 19 | `TransformAdpcmDecode` yields 2 samples per input byte (4-bit ADPCM). | well-supported (ear: 10,486 B -> ~3 s at 8 kHz and ~12 s at 2 kHz, both 14 % over prediction; probe104 17,000 B -> 4.25 s is arithmetic) | `docs/deep/offline-2026-10-10/verify.md` section V5 point 1; `docs/deep/buffer-cadence.md` confidence summary |
| 20 | The rate-consuming sites re-read the rate live: the tone mix operator compares the live input rate to its cache on every call and recomputes at once (PM `0x11b5`-`0x11d6`), and the copy timer re-reads `M[0x2aac]` every tick. | proven (decode) | `docs/deep/offline-2026-10-10/verify.md` section V5 point 4 |
| 21 | Observed: the first chunk of ours after we start pressing played about 4x faster than the second, near 8 kHz, although `0x1072` asked for 2000 on both. The cause is unknown (see traps 7.4). | observed (ear, n=2 first presses, n=1 second press) | `docs/field-log.md:13286`, `docs/field-log.md:13315`; `docs/deep/offline-2026-10-10/verify.md` section V5 |
| 22 | `KalimbaSendMessage` returns TRUE when a `.kap` is loaded, not when the DSP handled the message. FALSE therefore means "no DSP" and is the cave's DSP-gone gate. | proven (press: probe177 R1; ADK semantics) | `docs/kalimba-disasm.md` "consequence 2"; `docs/field-log.md:13286` |

### 2.3 Lifetime and end of chunk

| # | fact | confidence | source |
|---|---|---|---|
| 23 | The DSP sends `0x1080` (PLAY_BACK_FINISHED) after the tone input buffer has been empty for `$PCM_END_DETECTION_TIME_OUT = 30000` microseconds, accumulated in tick-period steps (tens of ms), then clears the armed flag and stops reading port 3. Only a new `0x1072` re-arms it. | proven (decode) | `build/analysis/kalimba/sbc_decoder.disasm.txt` lines `800017b8`-`800017c5`; `adk/root/kalimba/apps/a2dp_sink/codec_decoder.h:166`; `docs/deep/buffer-cadence.md` section 3e |
| 24 | The VM handles `0x1080` in `fn_31105` (`cmp #0x1080` at `0x3115e`, then `0x312e8 bsr fn_31ab7`); the same case exists in `fn_30940` and `fn_323cc`. The cave does not own the Kalimba task, so it never receives `0x1080`. | proven (decode) | `docs/deep/offline-2026-10-10/chunk-end.md` sections 2a-2c; `docs/deep/offline-2026-10-10/dsp-keepalive-rate.md` A2 |
| 25 | `fn_31ab7` (`0x31ab7`-`0x31ad1`) does `MessageSinkTask(StreamKalimbaSink(3), 0)` if the decoder context `@0x72f` is set; then only if bit 13 or 14 of `M[@0x72b+26]` is set it clears bit 14 and calls `fn_2f9fb(0)`, which zeroes the routing field `M[@0x72b+10]`. It makes NO `TransformStop`, `TransformDisconnect` or `StreamDisconnect` call and does NOT touch the audio-busy word `@(24,@0x72b)`. | proven (decode) | `docs/deep/offline-2026-10-10/verify.md` sections V1, V6 point 2 |
| 26 | The only stock `TransformStop`/`TransformDisconnect` callers are `fn_31e6f` (reached only from `0x317d7`, the A2DP-disconnect path) and `fn_31e91` (RTP encode). | proven (decode) | `docs/deep/offline-2026-10-10/verify.md` section V1 point 2 |
| 27 | With music PLAYING the DSP stayed loaded and a second chunk was built (probe177 R2: ~3 s then ~12 s; probe178: two quiet chunks). | proven (press, n=2 pairs) | `docs/field-log.md:13315`, `docs/field-log.md:13394` |
| 28 | With music PAUSED the DSP was gone when press 2 landed, 5 s or more (unmeasured) after a ~3 s chunk: `0x1072` returned FALSE, the cave spoke 0x3E "bluetooth off". | proven (press, n=1) | `docs/field-log.md:13286` |
| 29 | The unload chain is `0x1080` -> `fn_31ab7` zeroes `[10]` -> a parked disconnect message is released -> `fn_30ddd` case at `0x30e54` -> `fn_31734` -> `KalimbaPowerOff` at `0x317d9`. The decode is proven; which sender parked the disconnect and the meaning of the `[26]` bits 13/14 are not shown. | well-supported | `docs/deep/offline-2026-10-10/verify.md` section V6 point 2; `docs/deep/offline-2026-10-10/dsp-keepalive-rate.md` A3 |
| 30 | The paused-unload latency is UNMEASURED: probe177 (n=1) only shows the DSP was gone by press 2. Any figure under 1 s or near 8 s is an expectation or the press schedule, not data. The decoded chain contains no timer (a hypothesis-grade reason to expect a short delay), and a routing-delay timer of unknown length (`EventSysCheckAudioRouting` `0x4746`) is the doubt. The "~8 s" in older notes is the press schedule (3 s chunk + 5 s wait), not a latency. | unknown (any figure is an expectation, not data) | `docs/deep/offline-2026-10-10/verify.md` section V6 points 1, 3, 4 |
| 31 | Two readings of the paused unload were never separated: (a) tone end with A2DP paused releases the plugin disconnect, (b) a paused stream times out and the DSP goes regardless. Probes 174/175 ran past 7 s during a pause with the DSP alive, which leans to (a). | well-supported for (a) | `docs/field-log.md:13286` item 3; `docs/deep/offline-2026-10-10/verify.md` section V6 |

### 2.4 The transform in the stack image (all proven static, none pressed)

| # | fact | confidence | source |
|---|---|---|---|
| 32 | `TransformAdpcmDecode(file, ksink)` builds TWO nodes: A (ADPCM worker, root, flags 0) and B (copy node, flag `0x40` "downstream of another node"). It returns A; `TransformFromSink(ksink)` finds B. That it takes this path rests on one branch reading (`bcz` as unsigned <=); every other reading would make the call fail, which it does not. | proven (static) for the structure; well-supported for the path | `docs/deep/offline-2026-10-10/stack-transform.md` section 2 |
| 33 | `TransformStop` on a node with flag `0x40` calls `Panic(0x4030)` at stack word `0x1d74f`. The cave's `t = TransformFromSink(ksink); TransformStop(t)` therefore panics: this is the best reading of the cause of the speaker restarts in probes 174 and 175 (the restarts are proven by press, n=2). | Panic decode proven (static); as the crash cause well-supported, not yet pressed | `docs/deep/offline-2026-10-10/stack-transform.md` section 8; `build/analysis/stack-disasm.txt` lines 96387-96394 (`0x01d748`-`0x01d751`) |
| 34 | When the last byte of the file is consumed the file source closes itself (`SourceDrop` -> size 0 -> auto-close flag `0x80`, set at `0x55aca`), which disposes the whole chain synchronously inside the decoder's last run, frees the intermediate buffer, and posts `MESSAGE_STREAM_DISCONNECT` (`0x8026`) only to tasks that are registered. The Kalimba port-3 object is not freed. No VM code is involved. | proven (static, not pressed) | `docs/deep/offline-2026-10-10/stack-transform.md` section 4 |
| 35 | `TransformFromSink(ksink)` is a pure list walk (no flag tested). It is nonzero from creation until the final `SourceDrop`, then 0, while the DSP and port still hold samples. The poll sees "free" BEFORE the audible end, by design. How early is unknown. | proven (static) for the read; unknown for the lead | `docs/deep/offline-2026-10-10/stack-transform.md` sections 5, 10 |
| 36 | A second `TransformAdpcmDecode` on a source or sink that already has a transform returns 0. Stacked transforms on one port cannot exist. | proven (static) | `docs/deep/offline-2026-10-10/stack-transform.md` section 6 item 3b |
| 37 | The decoder state is two words in the node (predictor, index), written back each run and lost with the node. A new node is zero-filled, so every chunk starts at predictor 0, index 0 (the zero-fill count was not traced). | proven (persistence); well-supported (start value 0,0) | `docs/deep/offline-2026-10-10/stack-transform.md` section 3 |
| 38 | No busy-port read of a RUNNING transform has ever been observed on hardware. The citations "busy presses in 176-178" do not exist; 174/175 are the only presses that could have done it and they crashed for the static reason in row 33. | proven negative | `docs/deep/offline-2026-10-10/verify.md` section V2 (busy-read) |

### 2.5 Material and the speaker

| # | fact | confidence | source |
|---|---|---|---|
| 39 | The device decodes IMA ADPCM (CWI dialect), 4 bits per sample, no header, high nibble first, standard step and index tables. | proven (nibble order and tables, static); well-supported (start state) | `docs/deep/offline-2026-10-10/adpcm-format.md` section 1; `docs/deep/offline-2026-10-10/stack-transform.md` section 3 |
| 40 | `data_us` and `rphrases_us` are the NowSpeakTTS corpus, not ADPCM and not noise. Played as ADPCM they decode 43-62 % railed per 40 KB window (36 % for rphrases_us), about -1.6 dBFS RMS, spectrum falling about 3.5 dB per octave (pink-ish, not rising). Arbitrary bytes are NOT brown by construction. | measured offline (tools/adpcm.py) | `docs/deep/offline-2026-10-10/verify.md` section V10; `docs/deep/offline-2026-10-10/adpcm-format.md` section 1 negatives |
| 41 | Durations by arithmetic only (never timed): `data_us` 54.9 s at 8 kHz and 219.5 s at 2 kHz; `rphrases_us` 2.6 s at 8 kHz and 10.5 s at 2 kHz. | well-supported | `docs/deep/offline-2026-10-10/verify.md` section V10 |
| 42 | The IMA decoder is a leak-free accumulator, so a free random walk drifts to DC at any rate. Quiet probe129 was that, not the 2 kHz rate. A bounded walk made probe134 "louder noise". | proven (offline measurement; press for 134) | `docs/field-log.md:8078`; `docs/field-log.md:9373` |
| 43 | The owner's Bluetooth-streamed brown noise "sounds excellent" on this speaker. The 2026-10-04 inference that the driver does not radiate below 150 Hz was never measured and is withdrawn. | proven (owner quote) | `docs/field-log.md:12181`; memory note `csr8670-speaker-not-the-limit` |
| 44 | No brown-noise payload has been played through the tone path. Hardware noise so far is 126 ms bounded-walk bursts (probes 128-134) and the prompt corpus as a stand-in (173-178). The wav previews are decoder output before the DSP shift, resampler and mix. | proven negative | `docs/deep/offline-2026-10-10/README.md` section 4C, F12; `docs/deep/offline-2026-10-10/adpcm-format.md` section 5 |

### 2.6 History facts the next agent will trip on

| # | fact | confidence | source |
|---|---|---|---|
| 45 | Every port-3 result from probe104 to probe171 ended near 6-9 s. probe157 measured why: ~7 s after a Bluetooth long press `KalimbaSendMessage(0x1072)` returns FALSE (DSP gone). | proven (press, n=1) for the measurement | `docs/field-log.md:11670` |
| 46 | The cause is the pairing entry: the hook at `0x00ae0` sits two instructions after `fn_0d500` (`0x00ac2`), the connection-library disconnect plus page/inquiry scan, which drops A2DP asynchronously and takes `sbc_decoder` down. The centre-button hook has no such teardown and chunks ran past 7 s on the first press (174, 175). | well-supported | `docs/deep/hook-gates.md` addendum; `docs/field-log.md:11697`; `docs/field-log.md:13112` |
| 47 | Cave-driven DSP reload (probes 158-171) was accepted at every step and stayed silent: `KalimbaLoad` of `sbc_decoder`, our task owning the Kalimba mailbox, the stock `0x1000 -> 0x1020 + 0x1012 -> 0x1015` handshake, `fn_1f04c` DAC connect, `0x1002`, `0x1001`, `0x1070`, `0x1071`, `0x10a0`, `0x1072`, GO `0x7000`, DAC hardware gain 0 dB, then a port-3 stream. | proven (press, ten probes) | `docs/field-log.md:12076`-`docs/field-log.md:12866` |
| 48 | GO sent to a DSP that has not had SETPLUGIN halts the DSP in `$error`, which explains the probe96 wedge on the DSP side. The VM-side half (a send that waits for an ACK freezing the loop) is a hypothesis. | proven (DSP side) | `docs/field-log.md:11959` item 2 |

---

## 3. How it works

### 3.1 The stock path in one diagram

    phone / laptop --A2DP--> BlueCore stack --RTP transform--> Kalimba sink port 0
                                                                   |
                                                                   v
                                  sbc_decoder.kap (SBC decode, music_example processing)
                                       ^ port 3: tone / prompt input, mixed here
                                       v
                          DSP write ports 5 and 6 --> DAC channel A, channel B

The VM side of connecting an output is one library call, `fn_1f04c(&params)` with `{rate_hi, rate_lo, flags}`; the stock prompt builder uses `{0x0000, 0xbb80, 0x0000}` (48,000 Hz). The connect configures each DAC sink's rate (`SinkConfigure 0x301`), leaves the hardware gain at DAC step 0 (-45 dB) and the sink muted, then pass 2 connects and clears the mute flag. Stock raises the gain afterwards through `fn_1f589 -> fn_1f512 -> fn_1f4e1` (`docs/deep/dsp-output-wiring.md`, `docs/field-log.md:12783`).

Bose's DSP load recipe for the A2DP case is `FileFind -> VmDeepSleepEnable(0) -> KalimbaLoad -> ... -> GO`. Do not confuse it with `docs/bose-audio-path.md` section 1, which disassembles the NowSpeakTTS prompt-DSP loader `fn_1e3c5` (DSP output port 0 -> DAC, 16 kHz); that is a different DSP and a different wiring (`docs/kalimba-disasm.md` correction of 2026-10-05).

Bring-up order the stock uses for sbc_decoder (from decode of `fn_31d3f` and the DSP boot code): the DSP boots, sends `0x1000` (MUSIC_READY) then `0x8000`, and waits for GO. The VM answers `0x1020` (SETPLUGIN, variant 1 = SBC) and `0x1012` (LOADPARAMS), the DSP replies `0x1015` (PARAMS_LOADED), then the VM does the DAC connect, `0x1002` volume, `0x1001` SetMode (FULLPROC = 2), `0x1070`/`0x1071` rates, `0x10a0` output types, `0x1072` for tones, and `0x7000` GO (`docs/field-log.md:11959`, `docs/field-log.md:12756`, `docs/deep/dsp-output-wiring.md`).

### 3.2 Kalimba message ids that matter

Direction: VM->DSP unless marked. "TRUE" in the last column means only that a send returned TRUE (a `.kap` was loaded), not that the DSP handled it.

| id | name (ADK header) | role here | status |
|---|---|---|---|
| `0x1000` | MUSIC_READY (DSP->VM) | DSP boot done, waiting for configuration | proven; probe161 answered it from the cave |
| `0x1001` | MUSIC_SETMODE | system mode; 2 = FULLPROC. In the ADK, LOADPARAMS forces STANDBY and only SetMode raises it (ADK reading, not checked in Bose's image) | handler registered (`docs/field-log.md:11959` item 1); probe170 send returned TRUE |
| `0x1002` | MUSIC_VOLUME (ADK: deprecated) | Bose sends the 8-word block `{system, master, tone, trim x5}` as a long message; the handler copies it to DM `0x29a9`-`0x29b0` | decode proven; effect unknown; probe168 TRUE, no crash |
| `0x1012` / `0x1015` | LOADPARAMS / PARAMS_LOADED (DSP->VM) | parameter load handshake | proven (probe161: "voice prompts on" = `0x1015` reached our task) |
| `0x1020` | SETPLUGIN | accepts variants 1, 5, 8; without it GO halts the DSP | proven (DSP side) |
| `0x1070` | DAC sample rate (rate / 10) | handler multiplies by 10 into `M[0xff83f1]` | decode proven |
| `0x1071` | codec sample rate | registered; sent by `fn_313f0` with `0x1070` | probe166 TRUE |
| `0x1072` | tone rate and config | word a = Hz, word b bit 0 stereo, bit 1 NO_EXTRA_GAIN; arms and purges port 3 | decode and press proven (section 2.2) |
| `0x1078` | Bose extra | stores four words to DM `0x2A00`-`0x2A03`, a parameter store; never used by us | decode proven |
| `0x1080` | PLAY_BACK_FINISHED (DSP->VM) | end of tone input (section 2.3); a second send site exists on the SBC-decode path (`0x3132` in the flash overlay) | decode proven |
| `0x10a0` | SET_OUTPUT_DEV_TYPE (ADK: deprecated) | Bose sends a 7-word long message from `fn_3143c` | probe169 TRUE; whether Bose's DSP handles it is not shown |
| `0x7000` | GO | releases `$message.send_ready_wait_for_go` (PM-flash `0x34a7`) | decode proven; early GO wedges (row 48) |
| `0x8024` | MESSAGE_FROM_KALIMBA (stack->VM wrapper) | how DSP messages arrive at the VM handler | proven |
| `0x8021` / `0x8022` / `0x8026` / `0x8029` | MORE_DATA / MORE_SPACE / STREAM_DISCONNECT / SOURCE_EMPTY | stack messages to a registered sink or source task | static; the cave registers none |

### 3.3 The tone path in the DSP

1. `0x1072` arms the reader: stores the rate and the copy period, sets the shift, purges the tone cbuffers, sets `$aux_input_stream_available`.
2. A copy timer (8 ms scaled by 8000 / rate, doubled for mono) moves up to `TONE_BUFFER_SIZE` = 256 samples from port 3 into a resample cbuffer (1536 words). 256 samples is 32 ms at 8 kHz and 128 ms at 2 kHz (`docs/deep/buffer-cadence.md` section 3e).
3. The cbops tone operator shifts the samples (7 or 4), upsamples to the 48 kHz output rate and mixes them into the music output chain. The mix runs inside the output copy chain, which only runs when the music decoder has produced a frame (ADK structure, see 4.2).
4. `$detect_end_of_aux_stream` runs each tick; after 30,000 us of empty input it sends `0x1080` and disarms.
5. Two deadlines follow from this: a feeder tolerates one missed tick, not two. This is what killed rate-matched probe147 within a second, the one genuine DSP-side disarm in the 6-9 s era (`docs/field-log.md:10675`).

### 3.4 Level

Three independent stages, in order of how much of each we control.

| stage | what it is | who sets it | status |
|---|---|---|---|
| tone shift | `0x1072` word b: shift 7 (loud) or 4 (quiet), 18 dB apart at the cbops output | the cave, per chunk | proven, press-confirmed (probe178) |
| tone mix weight | ADK: written by the main-volume handler from the tone word of `0x1002`; Bose copies the block verbatim and the conversion is not located | the stock, on volume changes | unknown |
| DAC hardware gain | `SinkConfigure(dac, 0x303, n)`, n = 0..22, 15 = 0 dB, 3 dB per step (`docs/gain.md`) | the stock after connect; our cave never sets it on the stock DSP | well-supported |

What the volume buttons do to the noise is unknown (row 15). Do not describe the level as independent of them in anything that reaches the owner.

### 3.5 DSP lifetime, playing versus paused

- Music playing: the sink app keeps the A2DP source routed, so no disconnect is ever queued; the `0x1080` from our chunk's end is harmless and the DSP stays (n=2).
- Music paused: the sink app has already decided to drop the idle source but the disconnect was parked while the tone played; `0x1080` releases it and `KalimbaPowerOff` unloads the DSP (n=1, mechanism well-supported, latency unmeasured).
- Nothing connected: no `sbc_decoder`, so no port 3 mixing. The cave cannot load it usefully (section 4.2).
- Keep-alive options, ranked in `docs/deep/offline-2026-10-10/dsp-keepalive-rate.md` Part A: (1) require music playing (zero code, the v1 plan); (2) never let port 3 idle 30,000 us, either one long source or a re-arm inside the window; (3) cancel the routing timer (fragile); (4) forge the stream state (dangerous); (5) reload from the cave (closed). Its option-2 reasoning predates the microsecond correction: with `0x1080` firing tens of ms after the source ends and no timer in the unload chain, a 1 s poll is expected to LOSE the race when paused (`docs/deep/offline-2026-10-10/verify.md` section V6 point 4). Paused-phone operation is expected NOT to work in v1.

### 3.6 End of chunk and the stock cleanup

There are three different "ends", in this order for a file source:

1. Source EOF: the last byte leaves the file, the firmware disposes the transform chain, `TransformFromSink(ksink)` reads 0 (row 35).
2. Audible end: the port-3 buffer (32 ms at 8 kHz), whatever sits in the intermediate buffer (unknown whether it is delivered or dropped at dispose) and the DSP cbuffer drain.
3. DSP `0x1080`: tens of ms after the input is empty; the stock runs `fn_31ab7` (row 25), which does no transform teardown.

So the stock does not "free port 3 on tone end"; the firmware freed it at source EOF. Older notes that say the `0x1080` handler frees port 3 are retracted (7.2). The cave's chosen end signal is therefore a read-only poll of `TransformFromSink` from its own timer (`docs/deep/offline-2026-10-10/chunk-end.md` section 4, as modified by `docs/deep/offline-2026-10-10/stack-transform.md` section 9, which drops the "two consecutive free reads" mitigation because the first free read is already true).

An event route exists: `MessageSinkTask(ksink, our task)` makes the stack deliver `0x8026` exactly at the free edge. Its cautions (the handler must filter ids, `0x8022` also arrives, the stock clears the task in `fn_31ab7`) are in `docs/deep/offline-2026-10-10/stack-transform.md` section 9. It was tried once: probe148 (2026-10-07, malloc'd TaskData plus a 127 ms watchdog) gave "a short blip of noise, then silence" and the log itself calls the result ambiguous by construction, because two variables changed and the per-stage speech was removed (`docs/field-log.md:10722`-`docs/field-log.md:10762`). It neither confirms nor refutes event delivery.

### 3.7 The unreachable noise sources

The DSP cannot be told to generate noise: sbc_decoder registers no synthesiser, the ADK generators (DTMF `0x7150`, `$math.vector_rand`, comfort noise, CVC colour-0 brown) are unlinked, gc'd or need scaffolding Bose's app lacks (`docs/dsp-noise-route.md` section 4; `docs/kalimba-disasm.md` "Nothing synthesises"). A brown-noise `.kap` exists in the tree (`fw/csr8670/brown_noise.asm`, 4,094 bytes, kalsim-verified) but cannot be delivered through the signed filesystem (1,333 or more unchangeable bytes would have to change; `docs/dsp-noise-route.md` section 5). The only delivery route left is the parked partition-2 write (`docs/partition-route.md`, owner go-ahead required). Material must therefore be fed as bytes through the ADPCM transform.

---

## 4. Deeper explanations of the contested parts

### 4.1 The 7-second era and how it was explained

Probe104 (2026-10-02) showed that `TransformStart(TransformAdpcmDecode(StreamRegionSource(...), StreamKalimbaSink(3)))` carries audio (`docs/field-log.md:5546`). Its 0.25 s cut-off was first read as the prompt reloading NowSpeakTTS and evicting the decoder. From probe145 (2026-10-06) every architecture died at 6-9 s and the explanations changed three times:

| period | explanation | outcome |
|---|---|---|
| 145-146 | double free, then "the real killer": a 2291 samples/s feed against a 2000 samples/s drain stalls the port, an undrained source leaks one object per tick, and the pool dies at a fixed count (~55 ticks) | `docs/field-log.md:10621`-`docs/field-log.md:10660`; later partly contradicted, see 4.4 |
| 147 | rate matching drained the port to empty, the DSP's 30 ms end-detect disarmed it in under a second | real DSP-side disarm (row 23), but not the 6-9 s ceiling |
| 148-156 | completion-driven refill (148), instrumented loops (149-151), census (152-153), a single source and transform (155) | probe155 played 7 s with one source, one transform, no timer: accumulation cannot be the cause (`docs/field-log.md:11457`-`docs/field-log.md:11590`) |
| 157 | one added bool: the gate return after 7 s spoke 0x3E, so the DSP itself was gone | `docs/field-log.md:11670`: "Ten probes of pool arithmetic were explaining a number that had nothing to do with pools" |

Cause (well-supported): the Bluetooth long press enters pairing, and `fn_0d500` at `0x00ac2` runs before the hook, dropping A2DP and unloading the DSP (`docs/deep/hook-gates.md` addendum, `docs/field-log.md:11697`). Not skipping the stock back-call, because `fn_0e06d` is only the prompt dispatcher. The fix was a different hook: the centre long press arrives as event `0x4004` at `0x00e46` with no teardown (probe172, `docs/field-log.md:12923`), and the first press then played past 7 s (probes 174, 175). Probe173, on that hook, exposed the other half: a `data_us` chunk lasts the whole file, ~219 s at 2 kHz, not 7 s (`docs/field-log.md:13002`).

Where the "7 s" survives wrongly: probe173's 9.5 s timer, memory notes written before 2026-10-08, and `docs/deep/offline-2026-10-10/dsp-keepalive-rate.md` before its errata. Treat any 6-9 s figure measured on the Bluetooth hook as the teardown, never as a chunk length.

### 4.2 The reload line (probes 158-171) and why it stayed silent

Goal: a cave that does not need the phone's DSP. Sequence of results:

| probes | what was added | result |
|---|---|---|
| 93, 95 (older) | `KalimbaLoad(sbc_decoder)`; plus DAC wiring | clean (`docs/firmware-map.md` "What actually wedges") |
| 96, 97 | 96: GO from the cave; 97: a source on the tone port (on top of 95) | both wedged. For 96 the DSP side is explained: GO without SETPLUGIN halts the DSP in `$error` (row 48). 97 has no separate explanation on record |
| 158 | reload on a FALSE gate, then rebuild | "noise for 5 seconds and then it wedged"; recovery needed a stock flash (`docs/field-log.md:11717`-`docs/field-log.md:11860`) |
| 159, 160 | own the Kalimba mailbox, load, power off | clean; the DSP booted and sent `0x1000` to our task (`docs/field-log.md:12054`) |
| 161 | answer `0x1000` with SETPLUGIN + LOADPARAMS | `0x1015` came back; "voice prompts on" (`docs/field-log.md:12135`) |
| 162 | DAC rewire + `0x1072` + GO + chunk build + 9.5 s re-tick | wedge (`docs/field-log.md:12254`) |
| 163, 164, 165 | bisect: rewire alone clean; `0x1072` + GO clean; chunk build clean but INAUDIBLE | the wedge was the 9.5 s re-tick (`docs/field-log.md:12317`, `docs/field-log.md:12368`, `docs/field-log.md:12416`) |
| 166-170 | `0x1070`/`0x1071`, `0x1002` (167 restarted: panic in `fn_23229`'s chain), `0x10a0`, `0x1001` | every send TRUE, DAC silent |
| 171 | DAC hardware gain set to 0 dB (the connect leaves it at -45 dB) | still silent (`docs/field-log.md:12836`) |

Why silent (well-supported, not proven): the only remaining difference from the audible stock-loaded DSP is codec input. In the ADK `a2dp_sink` source the music frame loop runs only when the decoder has produced samples (`codec_decoder.asm:938`-`967`), the output copy draws from a silence chain until `$first_packet_received` (`$M.adjust_initial_latency`, `codec_decoder.asm:2587`), and that chain does not carry the tone-mix operators, so nothing reaches ports 5 and 6. The argument uses the ADK source structure, not Bose's binary, and no press isolated it. Feeding SBC into port 0 from the cave (~10 KB/s continuous) is out of scope. The line is closed; the pivot was to stop entering pairing (`docs/field-log.md:12867`). `docs/dsp-noise-route.md` banner warns against reintroducing a cave `KalimbaLoad` on the Bluetooth hook; the later bisect shows the 158 wedge was probably the re-tick, but it was never isolated at 158 itself (unknown).

### 4.3 The 174/175 crash, narrowed

Observed: probes 174 and 175 (same, with SPEAK removed) restarted the speaker on press 2 (the STOP path: `TransformFromSink`, `TransformStop`, `TransformDisconnect`, `StreamDisconnect(0, ksink)`). Earlier notes said "which of the three was not bisected". The stack image answers it: `TransformFromSink` returns the downstream node B (flag `0x40`) and `TransformStop(B)` panics at `0x1d74f` (row 33). `TransformDisconnect(B)` walks up to the root and is code-level safe; `StreamDisconnect(0, ksink)` disposes the chain on that sink and nothing else and is code-level safe; the stock's `fn_31e6f` pattern is safe where the sink-side node is a root (its RTP encode chain) but not for our two-node chain looked up from the sink. Static reading, not pressed. Probe151 ran the same trio on an inactive transform without a crash, which fits.

### 4.4 Contradictions that are still open

- `docs/field-log.md:10858`-`docs/field-log.md:10975` (probes 150/151): "an inactive transform is unfindable, not freed" and "SourceClose was forcing the reclamation", with the speaker refusing creation after ~55 ticks. `docs/deep/offline-2026-10-10/stack-transform.md` section 11 shows by code that a drained source is closed by the stack, the chain is freed, and `SourceClose` on a source that still has a transform is a no-op, which predicts no pile-up. One of the two is wrong; the image cannot say which. Do not cite "unfindable, not freed".
- How a stock prompt reaches the speaker while `sbc_decoder` is loaded. `docs/field-log.md:13012` and `docs/deep/offline-2026-10-10/controls.md` section 6 say prompts on a live sbc_decoder are mixed through port 3 (well-supported: probe172's SPEAK worked with port 3 free, probe173 heard no prompt with port 3 held). `docs/deep/prompt-audio-pump.md` and `docs/kalimba-disasm.md` (correction of 2026-10-05) say the ADK voice-prompt plugin that feeds port 3 is dead on this device (its files are absent) and the live prompt engine is NowSpeakTTS on port 0. The two are not reconciled; the safe rule (never SPEAK while our transform holds port 3) is correct under both.

### 4.5 Why the rate and the level were hard to pin

Rate and level look alike from outside and behave differently. Level (word b) is written into the cbops struct on every `0x1072` and was heard at once on the first chunk (probe178, row 13). Rate (word a) is written just as immediately and every rate-reading site re-reads it live (row 20), yet the first chunk played near 8 kHz (row 21). So the anomaly is not in any site the offline reading found. Candidates (all unverified): the `0x1072` handler running relative to the stock's own tone start, the stock re-sending its own rate when port 3 starts, a drain or priming effect. Counter-evidence nobody has reconciled: probes 128-134 were each a single first press with a = 2000 sent before the transform and the owner heard ~126 ms, as 2000 Hz predicts (8 kHz would be 31 ms). The decision to author material at 8000 Hz and send a = 8000 stands, but as a bet that probe181 tests with a stopwatch, not as a consequence of a proven rule.

---

## 5. Port-3 rules, and why each exists

### 5.1 The probes behind them

| probe | date | what it did | result |
|---|---|---|---|
| 173 | 2026-10-08 | first chunk loop on the centre hook; a 9.5 s timer whose ticks re-sent `0x1072`, called `StreamDisconnect(0, ksink)` without `TransformStop`, attached a new transform (four ticks, tick 5 was to speak 0x18) | "noise, then different noise that played forever, way more than 45 seconds ... had to plug and unplug a few times ... very loud harsh noise"; no prompt (`docs/field-log.md:13002`) |
| 174 | 2026-10-08/09 | one `data_us` chunk per press; press 2 STOP = trio + SPEAK 0x17 | press 1 sustained past 7 s ("terrible quality, very abrasive and loud"), press 2 restarted the speaker (`docs/field-log.md:13112`) |
| 175 | 2026-10-09 | same, SPEAK removed | same crash (`docs/field-log.md:13177`) |

What 173 proved and what it did not: the runaway is a press result (proven, n=1). That the 9.5 s tick caused it is well-supported, not proven: no tick on the `0x00e46` hook was ever observed, the owner pressed many buttons, and the prompt that would have marked tick 5 could not have been heard with port 3 held (`docs/deep/offline-2026-10-10/verify.md` section V7). The bundle (0x1072 re-send, StreamDisconnect without Stop, a second attach, a SPEAK) was never separated. The stack image adds that the "five 219 s stacked transforms" wording is wrong: a second `TransformAdpcmDecode` on a busy sink returns 0, so it was one long chain plus leaked sources (`docs/deep/offline-2026-10-10/stack-transform.md` section 8).

### 5.2 The rules, each with its reason and its current status

| rule | original reason (probe) | narrowed or corrected reason | status |
|---|---|---|---|
| 1. Compute chunk duration from file size and rate; never from a figure measured under the Bluetooth hook | 173: carried "7 s" into a 9.5 s timer; the chunk was ~219 s | the 7 s was the pairing teardown (4.1); `data_us` 54.9 s at 8 kHz, 219.5 s at 2 kHz, arithmetic only | in force |
| 2. Before touching port 3, read `TransformFromSink(StreamKalimbaSink(3))`; nonzero means busy, do nothing | 173: attached over a running transform | the read is a static pure list walk; a busy read has never been observed (row 38). It reads 0 from source EOF, before the audible end (row 35), so "free" does not mean "silent" | in force; step 0 on return is the first hardware test of it |
| 3. Never send `0x1072` to, or disconnect, a port with a running transform | 173 (bundled) | the handler only writes rate, period and shift and purges ~256 samples; "a 0x1072 re-send runs away" is hypothesis-against (probes 105/106 re-sent it 36 times a second and got silence). DESIGN experiment E4 deliberately re-sends it once right after `TransformStart` | rule kept as a guard; not proven as a cause (`docs/deep/offline-2026-10-10/verify.md` section V3 point 4) |
| 4. End a chunk only by letting it end. If a stop is ever needed, the stock order `TransformStop, TransformDisconnect, StreamDisconnect(0, ksink)` is NOT safe on a handle from `TransformFromSink` | 173/174/175: the stock order was copied from `fn_31e6f` | `TransformStop` on node B panics (row 33). Memory note `csr8670-port3-chunk-rules` and `docs/field-log.md:13037` still say "end a transform only the stock way"; read them with this correction. Candidate, never pressed, needs owner go-ahead: `StreamKalimbaSink(3)` then `StreamDisconnect(0, ksink)` alone | no loop image calls Stop, Disconnect or StreamDisconnect |
| 5. No timer re-arm until a chunk end is detected, not assumed | 173: tick landed mid-chunk | the poll design re-arms only on a free read (`docs/deep/offline-2026-10-10/DESIGN.md` section 3); tick delivery on `0x00e46` is itself unobserved (V7) | in force; probe179 is the first test |
| 6. Never SPEAK while our transform holds port 3 | 173: no prompt heard; 174: crash with SPEAK in the stop path | prompts on a live sbc_decoder are mixed through port 3 (well-supported, inference; see 4.4) | in force; speak only on paths where the port is free by construction |
| 7. A press on a busy port does nothing | 174-178 design | the busy branch (`LBL("STOP")` in `build/hook/assemble_probe178.py`) has never executed on hardware (V2) | in force; step 0 tests it |

---

## 6. What is known about the speaker reproducing brown noise

Known:

- The reference is the owner's Bluetooth-streamed brown noise, which sounds excellent on this speaker (`docs/field-log.md:12181`, memory note `csr8670-speaker-not-the-limit`). The judge is the owner's ear.
- A2DP music and our tone chunk leave through the same DSP output chain and DAC. The driver, the amplifier and the DAC are therefore the same for both; what differs is everything upstream (rate, ADPCM, shift, mix, gain).
- Bounded-walk generated noise at 2 kHz was heard as "louder noise" (probe134, `docs/field-log.md:9373`) and the harsh `data_us` and `rphrases_us` material as loud and abrasive. Both prove the path produces loud sound, not that it produces brown noise.

Limits that are ours, not the speaker's (all well-supported unless marked):

- The tone input rate: 8 kHz gives 4 kHz of bandwidth, 2 kHz gives 1 kHz, 16 kHz would give 8 kHz; the tone resampler accepts up to ~53 kHz (row 18). Brown noise is -6 dB per octave, so a few kHz of bandwidth is ample on paper; this is arithmetic, not a listening result.
- 4-bit ADPCM quantisation (SNR 23-30 dB in the decoded previews, `docs/deep/offline-2026-10-10/adpcm-format.md` section 5) and a decoder that restarts at predictor 0, index 0 on every chunk (seam artefact if the file's last sample is not near 0; `tools/brownnoise.py --loop` crossfades for this).
- Level: the cbops shift and an unknown tone weight and DAC gain (3.4).
- Unknown: whether the music chain applies EQ, bass management or a limiter to the tone mix (the `music_example` processing); not shown offline.

Retracted, do not repeat:

- "This driver does not radiate below 150 Hz, so redefine brown noise" (`docs/field-log.md:8747` goal verdicts, 2026-10-04). It was inferred from one probe (probe129) and withdrawn by the owner's correction (`docs/field-log.md:12181`). probe129's quietness was the unbounded IMA walk drifting to DC (`docs/field-log.md:8078`), not a driver limit.
- "The 2000 Hz rate killed the spectrum" (probe129 diagnosis, wrong per `docs/field-log.md:8078`; also repeated in the stale B4 of `docs/deep/offline-2026-10-10/dsp-keepalive-rate.md`). The rate changes where the spectrum sits, not its shape; the real case against 2000 Hz is bandwidth, and that is decided by ear.

Nothing yet tells us how a real brown payload sounds through this path. Candidate files exist: `build/noise/` (slot-sized payloads and wav previews at 2000 and 8000 Hz) and `build/brownnoise/` (20 s and 10 s files, peak 0.9 variants). Previews are decoder output before the DSP; they are screening, not judgement (`docs/deep/offline-2026-10-10/README.md` section 4C).

---

## 7. Traps and retractions

Check this table before trusting any older document in this area.

| # | stale or wrong claim | where it still appears | correct reading | source |
|---|---|---|---|---|
| 7.1 | "The `0x1080` handler frees port 3" | `docs/deep/offline-2026-10-10/chunk-end.md` sections 1, 2d (errata banner on top) | `fn_31ab7` makes no teardown call; firmware disposes the chain at source EOF | `docs/deep/offline-2026-10-10/verify.md` V1; `docs/deep/offline-2026-10-10/stack-transform.md` section 4 |
| 7.2 | `fn_31ab7` "clears the audio-busy word `@(24,@0x72b)`" | `docs/deep/offline-2026-10-10/dsp-keepalive-rate.md` A2/A3, digest-style summaries | it zeroes the routing field `M[@0x72b+10]` (only if bit 13 or 14 of `[26]` is set); it never touches `@(24,@0x72b)` | `docs/deep/offline-2026-10-10/verify.md` V6 point 2 |
| 7.3 | "DSP unloads ~8 s after the tone"; "30,000 copy-ticks" | `docs/deep/offline-2026-10-10/dsp-keepalive-rate.md`, `docs/deep/offline-2026-10-10/design-risk.md`, `docs/deep/offline-2026-10-10/controls.md` | 30,000 is microseconds (~30 ms); the 8 s is the press schedule; latency unmeasured, expected well under 1 s | `docs/deep/offline-2026-10-10/verify.md` V6 |
| 7.4 | "First chunk after a DSP load plays at the DSP's 8 kHz default, cached in the resampler" | `docs/RESUME-HERE.md` banner, `docs/deep/offline-2026-10-10/dsp-keepalive-rate.md` B2 | observed after the stock's last tone (n=2/n=1, ear); the DSP had been loaded since the music started; the resampler re-reads live; cause unknown; probes 128-134 contradict | `docs/deep/offline-2026-10-10/verify.md` V5 |
| 7.5 | "Loudness is independent of the volume buttons and music volume" | `docs/RESUME-HERE.md` banner, `docs/field-log.md:13315` | one hedged ear report; hypothesis | `docs/deep/offline-2026-10-10/verify.md` V4 (c) |
| 7.6 | "b = 2 is 18 dB quieter" stated as measured | several notes | 3 bits at the cbops output; acoustic ratio not measured | `docs/deep/offline-2026-10-10/verify.md` V4 (a) |
| 7.7 | "word b = 0 selects +18 dB and saturates" (ADK base +8) | probe105/107/108 docstrings, `docs/field-log.md:5579` | Bose base is +4: b = 0 is shift 7, nothing saturates, b = 2 is the quiet one | `docs/kalimba-disasm.md` "THE CORRECTION"; `docs/field-log.md:8063` |
| 7.8 | "TransformAdpcmDecode output is brown by construction" | `docs/deep/offline-2026-10-10/material-slots.md` and similar | a leak-free accumulator drifts to DC; arbitrary bytes decode pink-ish (-3.5 dB/oct) and ~50 % railed; brown needs a purpose-built payload | `docs/deep/offline-2026-10-10/verify.md` V10; `docs/field-log.md:8078` |
| 7.9 | "Spectrum rising toward treble, the opposite of brown" for the prompt corpus | `docs/deep/offline-2026-10-10/design-mvp.md` | falling ~3.5 dB/oct; harshness is ~50 % clipping | `docs/deep/offline-2026-10-10/verify.md` V10 |
| 7.10 | malloc + generate PCM + `StreamRegionSource` + `StreamConnect` is "the deliverable route" | `docs/bose-audio-path.md` section 6 (correction banner on top) | dead: probes 101/102 silent; only a source through a transform works | `docs/bose-audio-path.md` banner; `docs/field-log.md:5546` |
| 7.11 | "SourceClose was forcing the transform reclamation"; "inactive transform unfindable, not freed" | `docs/field-log.md:10858`-`docs/field-log.md:10975` | `SourceClose` on a source with a live transform is a no-op; drained chains are freed; contradiction open (4.4) | `docs/deep/offline-2026-10-10/stack-transform.md` sections 6, 11 |
| 7.12 | "port 3 -> sbc_decoder -> port 0 -> DAC" | `docs/field-log.md:8747` goal table | sbc_decoder outputs on write ports 5 and 6 to DAC A and B; port 0 is the input (and NowSpeakTTS's output) | `docs/deep/dsp-output-wiring.md` |
| 7.13 | "Busy presses in 176-178 did nothing and nothing crashed" | `docs/deep/offline-2026-10-10/design-risk.md` lines 22, 137, 594 | no such press exists; the busy branch never ran | `docs/deep/offline-2026-10-10/verify.md` V2 (busy-read); `docs/deep/offline-2026-10-10/DESIGN.md` section 8 item 3 |
| 7.14 | "TransformStop/Disconnect/StreamDisconnect Panics (174, 175)" as three equal suspects, and "a 0x1072 re-send runs away" | `docs/deep/offline-2026-10-10/design-risk.md` | only `TransformStop` on node B panics (static); the re-send claim is hypothesis-against | `docs/deep/offline-2026-10-10/stack-transform.md` section 8; `docs/deep/offline-2026-10-10/verify.md` V3 |
| 7.15 | "Five stacked 219 s transforms" (probe173) | `docs/field-log.md:13012` area, memory notes | stacking is impossible; one long chain plus leaked sources | `docs/deep/offline-2026-10-10/stack-transform.md` section 8 |
| 7.16 | A 6-9 s "chunk length" or pool-death explanation for probes 104-155 | `docs/field-log.md:10631`, older roadmap text | the Bluetooth-hook pairing teardown (4.1); probe147's sub-second death was a genuine disarm | `docs/field-log.md:11670` |
| 7.17 | "Redefine goal 4: the driver does not radiate below 150 Hz" | `docs/field-log.md:8747` | withdrawn 2026-10-08; only the owner's ear closes it | `docs/field-log.md:12181` |
| 7.18 | "The ADPCM decoder lives in `stack_prog.bin` which this project does not open" | `docs/deep/AGENT-BRIEF.md` line 19, older adpcm notes | it was disassembled (`build/analysis/stack-disasm.txt`); addresses there are stack word indices, runtime address = file word index + 10 plus a bank | `docs/deep/offline-2026-10-10/stack-transform.md` section 1 |
| 7.19 | "`sbc_decoder` has no 0x7000/GO" and "no `0x10xx` in NowSpeakTTS" | `docs/kalimba-disasm.md` before its corrections | the `.kap` has a PM-flash overlay (`0x3000`+); immediate scans of the RAM PM only are unsafe | `docs/kalimba-disasm.md` correction of 2026-10-08; `docs/field-log.md:11959` |
| 7.20 | "On NowSpeakTTS port 3 is the prompt's own data path (`fn_22f6f`), so a cave can take port 3 from the prompt" (probe111 premise) | `docs/kalimba-disasm.md` before its correction of 2026-10-05 | `fn_22f6f` is the dead ADK voice-prompt plugin (its files are absent); the standalone prompt engine NowSpeakTTS loads via `fn_1e3c5`, outputs on port 0 and registers no `0x1072`; see also 4.4 | `docs/deep/prompt-audio-pump.md`; `docs/kalimba-disasm.md` |

Further caution: all stack-image addresses are word indices in a separate address space; never compare one with a vm.app address (`docs/deep/AGENT-BRIEF.md`).

---

## 8. Open questions (and what settles each)

| question | why it is open | what settles it |
|---|---|---|
| Does a busy read of a running transform (`StreamKalimbaSink(3)` + `TransformFromSink`) restart the speaker? | never observed (row 38); static reading says it is a pure list walk | step 0 on return: probe178 as installed, music playing, a second centre long press about 1 s into a chunk, again inside the ~12 s chunk and near its end (`docs/RETURN-CHECKLIST.md` section 1) |
| Does the cycle hold for N > 2 presses, and how soon after the audible end does the port read free? | only two consecutive chunks ever observed | ten consecutive presses, then presses at about 0, 2 and 5 s after the audible end (same checklist) |
| How large is the lead between the free edge and the audible end, and is the last part of the intermediate buffer dropped? | MMU buffer unit not decoded | stopwatch a chunk of known length at 2 kHz and 8 kHz against the spoken id of probe179 press A (`docs/deep/offline-2026-10-10/stack-transform.md` section 10) |
| Paused-unload latency, and whether it is tone-end or stream timeout | one press, schedule not latency (rows 28-31) | music paused, press, press again at under 1, 2, 3 and 5 s; noise = DSP up, "bluetooth off" = gone (`docs/deep/offline-2026-10-10/README.md` section 4A item 4) |
| Does a tick (`MessageSendLater`) arrive from the `0x00e46` hook, and do ids count down? | proven on the `0xAE0` hook only | probe179 press A (3 chunks, then 0x26) |
| Is the first-chunk rate anomaly a rule, and does 8000 Hz material make it invisible? | cause unknown, counter-evidence from probes 128-134 | probe181 with a stopwatch on each chunk, plus a = 4000 on three presses and a press on a fresh DSP versus right after a stock prompt (`docs/deep/offline-2026-10-10/verify.md` section V5) |
| Does the level follow the volume buttons or the music volume? Is 18 dB the acoustic step? Is a change of b between chunks honoured? | one hedged ear report; decode only | the three-volume press test and a phone dB meter at b = 0 and b = 2 (`docs/deep/offline-2026-10-10/verify.md` section V4) |
| What does the `0x1002` tone word or the DAC gain do to a port-3 chunk? | handler copy proven, readers not located | a plain `0x1002` long send with the stock master and tone -1200 before a chunk (`docs/deep/offline-2026-10-10/controls.md` section 5) |
| Is `ksink`'s task nonzero at a cave chunk end (would a stale task deliver `0x8026` to the stock handler)? | depends on the last `MessageSinkTask` | read-only `MessageSinkGetTask` in a new image (`docs/deep/offline-2026-10-10/stack-transform.md` section 10) |
| Does `StreamDisconnect(0, ksink)` alone stop a running chunk cleanly? | static only; two earlier crashes | an image on top of probe180, behind the owner's go-ahead |
| Is the probe150/151 "pile-up after ~55 ticks" or the stack image right? | contradiction (4.4) | cannot be settled offline; the rebuild-per-chunk design does not depend on it |
| How do stock prompts reach the speaker while sbc_decoder runs, and does a prompt collide with our chunk? | sources disagree (4.4); experiment E2 untested | DESIGN experiment E2 (hold POWER during a chunk) behind the owner's decision |
| How does a real brown payload sound through the tone path, and at which rate? | no brown payload has been played | the owner's ear on probe185-class images; previews in `build/noise/` are screening only |
| Why did the probe158 wedge happen? | bisect of 162 points at the re-tick, 158 itself was not isolated | no further work planned; the line is closed |

---

## 9. Detailed knowledge: where to go for what

| if you want ... | read |
|---|---|
| the newest, most precise account of transforms, EOF, `TransformFromSink`, the 174/175 panic, `MessageSendLater`/`CancelFirst` | `docs/deep/offline-2026-10-10/stack-transform.md` |
| the judged claim list and the plan from probe179 on | `docs/deep/offline-2026-10-10/DESIGN.md` section 8 (claims), section 3 (probe sequence) |
| which claims were downgraded, with the evidence (V0-V11) | `docs/deep/offline-2026-10-10/verify.md` |
| the first day back: steps, gates, decisions | `docs/RETURN-CHECKLIST.md`; `docs/deep/offline-2026-10-10/README.md` section 4 |
| the DSP end-of-tone signal and the `fn_31ab7` cleanup | `docs/deep/offline-2026-10-10/chunk-end.md` (history; read with V1/V6) |
| why the DSP unloads when paused, keep-alive options, the rate latch (history, errata on top) | `docs/deep/offline-2026-10-10/dsp-keepalive-rate.md` |
| the level knobs, events reaching the hook, spoken feedback | `docs/deep/offline-2026-10-10/controls.md` |
| the ADPCM dialect, the encoder, brown generator, previews, slot payloads | `docs/deep/offline-2026-10-10/adpcm-format.md`; `tools/adpcm.py`; `tools/brownnoise.py` |
| where payload bytes can live (narrow files, partition 2) | `docs/deep/offline-2026-10-10/material-slots.md`; `docs/deep/offline-2026-10-10/write-constraint.md` |
| the prompt-id to corpus map (request id N, phoneme script) | `docs/deep/offline-2026-10-10/promptmap.md`; `docs/request-id-catalog.md` |
| how the stock connects the DAC, which DSP ports, the fn_1f04c parameters | `docs/deep/dsp-output-wiring.md` |
| Bose's tone recipe, the route map, the corrections to the old "deliverable route" | `docs/bose-audio-path.md` |
| the brown-noise DSP app that exists, why delivery is closed, the partition route | `docs/dsp-noise-route.md`; `docs/partition-route.md` |
| the DSP images: messages registered, the PM-flash overlay, the 0x1072 gain correction | `docs/kalimba-disasm.md`; `tools/kapdisasm.py`; `build/analysis/kalimba/` |
| the DAC gain scale (15 = 0 dB, 3 dB per step) | `docs/gain.md`; `docs/library-matching.md` |
| tone buffer size, the two deadlines, cadence of a refill design | `docs/deep/buffer-cadence.md` |
| how the stock plays prompts through port 3 (and why that plugin is dead) | `docs/deep/prompt-audio-pump.md` |
| why the Bluetooth hook tears the DSP down; the centre-button hook | `docs/deep/hook-gates.md`; `docs/deep/centre-long-press.md`; `docs/centre-button-hook.md` |
| why the codec sink stayed silent (probes 86/88-90) | `docs/codec-sink-inert.md` |
| the heap, leaks, pool sizes (the probe105/106 crash) | `docs/cave-heap.md` |
| message tasks, TaskData, handler ABI | `docs/message-task-abi.md` |
| the raw evidence, in time order (use the line numbers above) | `docs/field-log.md` (append-only; do not edit) |
| the probe images themselves and their press plans | `build/hook/assemble_probe178.py` (proven chunk), `build/hook/assemble_probe179.py` to `build/hook/assemble_probe181.py` (built, not flashed), `build/hook/assemble_probe173.py` to `build/hook/assemble_probe175.py` (the rule-makers) |
| the cave simulator and its world model (clock, queue, port 3, rules R1-R6) | `docs/deep/offline-2026-10-10/cavesim-changes.md`; `tools/cavesim.py`; `tools/cavesim_world.py` |

Standing owner constraints that bear on this topic (auto-memory notes): software only, no SPI; the speaker is not assumed to be the limit; port-3 chunk rules; every flash passes the hard gates of `docs/FLASH-PROTOCOL.md`. Other topic hubs live in docs/topics/.

See also (strategy review 2026-10-12, offline, a recommendation; read the skeptic section of each note first): `docs/deep/strategy-2026-10-12/03-seamless-generator.md` (the audible seam of the chunk-rebuild loop; which buffer the 0x1072 purge cuts in the Bose binary is unknown, `docs/FACTS.md` F154) and `docs/deep/strategy-2026-10-12/05-volume-control.md` (the loudness chain end to end; swallowing 0x400d/0x400e does not gate the main switch, `docs/FACTS.md` F148).

See also (firmware study 2026-10-12, offline, static or model results; read the skeptic section of each note first; index `docs/deep/firmware-study-2026-10-12/README.md`, functions `docs/FUNCTION-CATALOG.md`): `T02-bose-sbc-decoder-tone-path.md` (the purge cuts the one 256-sample tone buffer, 255 usable; the mono copy period is 16 ms at 8 kHz; no EQ or limiter after the mix; `docs/FACTS.md` F168-F175), `T01-pipe-trap-0x100.md` (the stack dispatches no trap above 0xE2, so no pipe: F157, F162), `T04-stock-collisions-and-centre-button.md` (a stock TTS prompt is a DSP swap, a stock tone re-sends 0x1072 b=0: F176-F179, F188), `T06-volume-path.md` (the stock tone word is predicted fixed at -2242, so the buttons are predicted not to move the noise: F196-F201) and `T07-payload-study.md` (payload generator, peak and length: F202-F206).

## See also (round 3, 2026-10-12)

Added at the end so that no cited line moved. Round 3 is offline and static or model work; nothing was run on the speaker. Index and corrections register: `docs/deep/round3-2026-10-12/README.md`; the facts are in `docs/FACTS.md` section 10.

- `docs/deep/round3-2026-10-12/R03-stack-version-and-lead-L.md`: the BC-side buffer is one 512-octet MMU buffer (I), so the lead L at the seam is bounded (16-64 ms at 8 kHz); the stack is byte-identical in every stock release (FACTS F244-F249).
- `docs/deep/round3-2026-10-12/R04-dsp-volume-readers.md`: the DSP applies no music master gain and has no reader of the volume_and_limit objects; a cave `0x1002` is a DAC command; the buttons-versus-noise question is a three-way fork (F250-F258, Q048).
- `docs/deep/round3-2026-10-12/N02-dsp-noise-sources-and-shapers.md`: the DSP images hold three PRNG families but no demonstrated generator; the DM PEEK/POKE messages `0x7AB2`/`0x7AB3` (F271-F274, Q046).
- `docs/deep/round3-2026-10-12/N04-backup-deep-dive.md`: SBC frames fed to Kalimba port 0: the Bose frame decode, the port-0 takeover, what survives (F275-F278).
- `docs/deep/round3-2026-10-12/B03-181p-poll-variants.md`: the 100 ms and 50 ms poll variants of 181p and the seam predictions (all conditional on the unmeasured chunk length D, F284, F289-F291).

## See also (2026-10-28)

The DSP can be read and written from the VM (PEEK/POKE), its tone ring and timer are mapped (FACTS F311-F319), its program memory is writable through the PM window (F316) and a noise generator runs inside it (probe380, F320). Everything: `docs/dsp-generator-route.md`. Statements in this hub that the DSP cannot be modified, or that noise material must come from a file, are superseded.
