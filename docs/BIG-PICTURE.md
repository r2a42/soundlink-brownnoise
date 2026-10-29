# Big picture: the whole CSR8670 / Bose SoundLink Micro project in ten minutes

Purpose: give a newcomer with no memory of this project the goal, the hardware, the hack end to end, the history, the exact current state and the next steps, with a link to the detail behind every statement.

Status / last verified: 2026-10-28 for sections 0 and 0a (rewritten); the sections below section 0a are the 2026-10-10 text and are history where they disagree: `docs/CURRENT-STATE.md` wins.

> **This is an archival research document from the original (larger, private) project repository.** It was written for that repository's own working notes and links into several files (`docs/RESUME-HERE.md`, `docs/RETURN-CHECKLIST.md`, `docs/INDEX.md`, and others) that are internal process notes not included in this public export. Where a link below doesn't resolve, that's why; `docs/CURRENT-STATE.md`, `docs/dsp-generator-route.md`, and `docs/ring-buffer-fix.md` are this export's own current, self-contained write-ups.

Read next: `docs/CURRENT-STATE.md`, then `docs/FLASH-PROTOCOL.md` before anything touches the device.

Confidence marks used here (the project convention): **proven** = an address, instruction, command output or owner press is quoted in the cited source; **well-supported** = one traced inference beyond a proven fact, or a static reading never seen on hardware; **hypothesis**; **unknown** = not established, the cited file would answer it. Negatives are results. Where sources disagree, the newer one wins, and `docs/deep/offline-2026-10-10/verify.md` and `stack-transform.md` beat older text.

---

## 0. The whole project in six lines (rewritten 2026-10-28)

1. Goal: loud, sustained brown noise on a Bose SoundLink Micro, installed over USB by the speaker's own update mechanism, software only. MET on unit 2 (probe380).
2. The only door is Bose's RSA-signed DFU. 30 of every 64 bytes of the signed filesystem are not covered by the signature (the actual tooling uses one byte less of margin: 29), so a few hundred words of our code can live inside the speaker's own `vm.app` (the "cave": a 197-word window plus an approved pool of otherwise-dead functions).
3. That code is called from a hooked button event and drives the speaker's DSP through its own messages.
4. What works today (probe380, flashed once from stock): a centre-button long press starts brown noise that the speaker's own DSP generates (no recording, no loop), within about 1-2 s; a second press stops it; 15 volume levels; lights dark while it plays; stock idle power-off restored; Bluetooth off while it plays.
5. How: the cave writes a 45-word routine into the DSP's program memory at every start (through the DSP's PM window) and hooks the DSP's tone-copy timer; `docs/dsp-generator-route.md`.
6. This project's first unit was permanently lost on 2026-10-04 by skipping the flash gates (`docs/POST-MORTEM-2026-10-04.md`); every result since is from the one remaining speaker, and every flash obeys `docs/FLASH-PROTOCOL.md` without exception. Open items (not yet tested): `docs/CURRENT-STATE.md` section 3.

### 0a. How we got here, in one paragraph

Recorded noise (a looped ADPCM payload staged in the voice file, then written to a flash partition by a writer image) worked from probe318 on but needed two flashes, cost most of the cave and left a 2.5 s loop seam and 48 kHz timeline steps; a 32 kHz native payload and then a 512-sample tone ring (three DSP pokes) cured the steps. A read-only DSP memory census (probes 361-365) proved the DSP's PEEK/POKE interface, found the ring and timer cells, and then the DSP's program-memory window (probes 368-377). That made it possible to run the generator in the DSP itself (probe380), which removed the payload, the writer, the loop and most of the cave.

Material rule in one line: StreamFileSource streams only narrow files (flags 0x00): data_us and rphrases_us (`docs/FACTS.md` F112); `.kap` and `vm.app` are flags 0x40 and are refused.

---

## 1. The goal and the owner's constraints

| constraint | statement | source | confidence |
|---|---|---|---|
| goal | brown noise on the Bose SoundLink Micro, installed over USB DFU, software only: an image any owner could flash with the speaker's own updater | memory `csr8670-software-only-goal`; `README.md` "Scope" | proven (owner statements) |
| no hardware route | no SPI, no soldering, no opening the case; decided 2026-09-25, because the owner wants it for sleep | same | proven |
| trigger | the CENTRE (voice-assistant / multifunction) button, stated 2026-09-30; the Bluetooth-hold hook that early probes used is for experiments only | same; `docs/field-log.md` probe41 entry | proven |
| loudness and sustain | loud, sustained; originally also "engine-routed so the volume buttons work". Today the tone path ignores the volume buttons (one hedged ear report, probe177) and the level knob is ours (probe178); whether the volume buttons should act on it is an open decision (D5 in `docs/RETURN-CHECKLIST.md` section 5) | `docs/RETURN-CHECKLIST.md` 1.6, 5 | well-supported |
| the speaker is not the limit | never assume the driver cannot reproduce brown noise or a frequency range. The reference is the owner's own Bluetooth-streamed brown noise, which sounds excellent on this speaker. When a probe sounds wrong, suspect our pipeline first. Only the owner's ear closes "can the speaker do X". The 2026-10-04 "redefine the goal" verdict was retracted on 2026-10-08 | memory `csr8670-speaker-not-the-limit`; `docs/field-log.md` line 12181 | proven (owner correction) |
| the owner's ear judges | wav previews of the generated material are decoder output only (before the DSP tone path, shift, resampler and mix); they screen, they do not decide | `docs/RETURN-CHECKLIST.md` end of section 6 | proven |
| flash discipline | every flash obeys the gates of `docs/FLASH-PROTOCOL.md`; the owner holds standing permission to flash and the gates are what make it safe | memory `csr8670-flash-protocol` | proven |
| offline period | from 2026-10-10 no flash and no device command until the owner says the speaker is back | memory `csr8670-offline-period-2026-10-10`; `docs/RESUME-HERE.md` banner | proven |
| private data | device readbacks contain Bluetooth link keys and serials and are never included in this export | - | proven |

---

## 2. The hardware in a paragraph

The device on the USB port is not a dev board: it is a **Bose SoundLink Micro** (Bose codename "Minnow"), built around a **CSR8670 "gordon"** Bluetooth audio chip, running Bose firmware **3.0.3.6546** (stack build `gdn_16unified_fl_bt4.2_28a1_1601111356`) (**proven**, `README.md` "What is actually on the USB port"; memory `csr8670-project-device`). It enumerates as HID `05A7:40FE` in normal mode and as `05A7:4022` in DFU mode; there is no CSR USB-SPI programmer and no COM port, so Bose's HID-DFU (driven by `tools/bose-dfu/bose-dfu.exe`) is the only way in. The chip runs three layers: a native Bluetooth **stack** (`stack_prog.bin`, 751,112 bytes, CRC-only area), a **VM application** `vm.app` (522,026 bytes of XAP2 bytecode: the speaker's behaviour, buttons, prompts), and **Kalimba DSP** images (`sbc_decoder.kap` decodes A2DP and mixes tones and prompts; `NowSpeakTTS.kap` is the prompt engine; two `soundClear*.kap` handle calls) loaded on demand. The signed internal filesystem (`fsr_dfu1`, 975,168 bytes) holds `vm.app`, the four `.kap` files, and the prompt data `data_us` (219,528 bytes) and `rphrases_us` (10,486 bytes) (**proven**, `docs/firmware-map.md` section 13). External flash carries a second signed filesystem of 12 foreign-language prompt packs, and there is a runtime-writable partition 2 (TYPE 3 RAW_SERIAL; probe139) into which the project has committed 16 bytes (probe140); a 33 KB attempt (probe141) has no established outcome (`docs/partition-route.md`). Only **unit 2** exists now; unit 1 was lost on 2026-10-04 20:23. Full layer-by-layer digest: `docs/firmware-map.md`, `docs/bose-firmware-anatomy.md`, `docs/bose-audio-path.md`, `docs/kalimba-disasm.md`.

---

## 3. How the hack works, end to end

Each step is one sentence plus the place to read more.

1. **Signed DFU.** The only install path is Bose's USB DFU, whose filesystem area carries a 1024-bit RSA signature (e=3, no padding) over a non-standard 8-chain MD5-variant hash; Bose's modulus was recovered and `S^3 mod n == block` holds on all seven shipped releases (**proven**). Read: `docs/dfu-signature-scheme.md` (Session 9 addendum).
2. **Blind window.** The hash's compress function reads only bytes 0..33 of each 64-byte block, so bytes 34..62 of every block (29 of every 64, 45.3 percent; `tools/fsedit.py` uses 34..62) can change without touching the signature, and `tools/fsedit.py` balances the loader's separate linear digest with a GF(2) solve (**proven**: probe8 and probe9 were accepted and read back byte-identical on 2026-09-27). Consequence: never more than 29 contiguous writable bytes, so no `.kap` and no raw PCM file can be installed. Read: `docs/dfu-signature-scheme.md` Sessions 9-10; `docs/deep/offline-2026-10-10/write-constraint.md` section 0.
3. **Cave in the VM app's const window.** Our code is written as 16-bit XAP2 words into the zero runs of `vm.app`'s constant pool where both bytes of each word are blind; the proven window is `0x3E200..0x3E400`, about 197 writable words, entry `0x3E21D`, and probe178 uses 124 of them (**proven**; a wider scan crashed the speaker on boot at probe130 because zero-looking gaps inside live tables are still read). Read: `docs/cave-budget.md`; memory `csr8670-cave-window`; `tools/caveguard.py`.
4. **Hook at `fn_00846` `0x00e46`.** A centre long press sends event `0x4004` which reaches `0x00e46: bsr fn_189fb`, a 3-word call whose 3 operand bytes are all blind, so three edited bytes redirect it to the cave; the cave speaks or acts on `AL == 0x4004` and replays the stock call for every other event (**proven** for the trigger, probe172; edit bytes `01 7c b3` -> `04 d4 d5`). Read: `docs/deep/centre-long-press.md`; `docs/field-log.md` "probe172"; `docs/hook-sites.md`.
5. **Traps.** The cave calls the firmware's VM traps through stubs found in the image, named from the speaker's BlueLab 7.3 table (not the ADK 4.4's 7.4 table), with the ABI arg1 -> AL, arg2 -> AH, arg3+ -> `@(0,Y)...`, result in AL (**proven**, compiled and linked). The chain probe178 runs is `StreamKalimbaSink(3)` and `TransformFromSink` (read-only port interrogation), `KalimbaSendMessage(0x1072)`, `FileFind` (twice), `StreamFileSource`, `TransformAdpcmDecode`, `TransformStart`. Read: `docs/trap-abi.md`; `docs/trap-numbering.md`; `docs/trap-stub-table.md`; `docs/message-task-abi.md`.
6. **Port 3 tone path in the `sbc_decoder` DSP.** Kalimba port 3 of `sbc_decoder.kap` is `TONE_VP_MIXING_DSP_PORT`, where the firmware mixes tones and voice prompts into the music; message `0x1072` arms it (word a = rate in Hz, bit 1 of word b selects the gain shift, 7 for b = 0 loud, 4 for b = 2 quiet), and a FALSE return from the send means no DSP is loaded (**proven**; decode plus probe178 "Quieter on Both"). Read: `docs/bose-audio-path.md` sections 3-8; `docs/kalimba-disasm.md`.
7. **Material.** `TransformAdpcmDecode` makes the stack decode the file's bytes as IMA ADPCM (high nibble first, 2 samples per byte) onto port 3; today the bytes are `tts/rphrases_us`, a stand-in that is about 36 percent clipped, not brown noise (**well-supported**; only `data_us` and `rphrases_us` are narrow files `StreamFileSource` accepts). Read: `docs/deep/offline-2026-10-10/adpcm-format.md`; `material-slots.md`; `verify.md` V10.
8. **Chunk end and the next press.** When the file source reaches its end the stack disposes the transform chain synchronously, the DSP reports the end of the tone (`0x1080`), and the next press finds the port free and builds a fresh chunk; this is why one press makes one chunk (**well-supported**: static reading, `stack-transform.md` verdicts 2-3; observed twice). Read: `docs/deep/offline-2026-10-10/stack-transform.md`; `chunk-end.md` (history, errata-bannered).
9. **DSP mixer to codec.** The DSP mixes the tone with the A2DP music and writes DSP ports 5/6 to DAC channels A/B through the stock output wiring, so the noise comes out of the same driver as the music; the VM never touches PCM (**proven**, disassembly). Read: `docs/deep/dsp-output-wiring.md`; `docs/bose-audio-path.md` sections 1-2.
10. **Because the DSP is loaded only while a Bluetooth source is connected, the first product needs a connected, playing device** (**proven** n=1 that a paused DSP is unloaded after a tone; standalone use is structurally blocked, probes 162-171). Read: `docs/deep/offline-2026-10-10/dsp-keepalive-rate.md` (errata-bannered), `verify.md` V6.

---

## 4. Diagrams

### 4.1 Audio path (what happens on a centre long press with music playing)

    laptop / phone ---- Bluetooth A2DP ---->  CSR8670 BT stack
                                                   |
                                                   v
                                      Kalimba DSP: sbc_decoder.kap
                                      port 0 = A2DP codec input (music)
                                                   |
    centre button                                  |
      -> fn_07d5d (button table 0xaaaa)            |
      -> event 0x4004 -> fn_00846 -> 0x00e46       |
      -> CAVE @ 0x3E21D (our code)                 |
           1. StreamKalimbaSink(3) + TransformFromSink
              (read-only: busy -> do nothing)      |
           2. KalimbaSendMessage(0x1072, rate, b) -+--> sets tone rate and level shift
           3. FileFind tts / rphrases_us           |
           4. StreamFileSource(file)               |
           5. TransformAdpcmDecode(src, port 3) ---+--> port 3 = TONE_VP_MIXING
           6. TransformStart                       |    (IMA ADPCM, 2 samples/byte)
                                                   v
                                      DSP mixer: music + tone
                                                   |
                                      write ports 5/6 -> DAC A/B -> amplifier -> driver

    music paused: the stock unloads the DSP after the tone ends (0x1072 then returns FALSE,
    the cave speaks "bluetooth off" = prompt id 0x3E).

### 4.2 Update path (how a probe gets onto the speaker)

    dev PC                                                      speaker (unit 2)
    ------                                                      ----------------
    build/hook/assemble_probeNNN.py  (caveasm; docstring = press plan + outcome table)
      -> tools/cavesim.py           (XAP2 emulator + world model; control probe90 first)
      -> tools/fsedit.py            (official 3.0.3 .dfu + cave words + 3 hook bytes,
                                     in blind bytes only; XOR balance; GF(2) digest fix;
                                     RSA block unchanged: pow(S,3,n) == block)
      -> build/hook/probeNNN_brown.dfu
      -> tools/preflight.py + tools/caveguard.py   (check the FILE; never a readback)
      -> tools/flash_probe.py       (FOREGROUND, gate-checked runner)
           bose-dfu enter-dfu ------------------------------>  05a7:4022 (DFU mode)
           bose-dfu download --force   "Waiting 45.867s ..."   loader verifies signature + digest
           bose-dfu leave-dfu -f  (no errXXX) -------------->  05a7:40fe, info -f = 3.0.3.6546
           tools/csr/dfu_upload.py  <------------------------  readback (1,760,814 bytes)
           compare: 0 of 975,168 fs bytes differ + every cave word present
      -> update build/hook/FLASHED (verified=...), then ONE press, then log the owner's words
         in docs/field-log.md before building anything else

---

## 5. The journey (eras, with the lesson of each)

Dates and probe numbers are the field log's own. Line numbers are in `docs/field-log.md` (append-only; later entries correct earlier ones, so read the amendments at its end, lines 13674 onward, before relying on an old entry).

1. **Static analysis and toolchain (from 2026-09-22).** The device is a signed Bose product, not a dev board; `vm.app` was decoded 100 percent (XAP2 bytecode); the ADK 4.4 was unpacked (not installed); a clean-room firmware in `fw/` builds but the stock updater has no slot for it (`README.md`, `docs/device-support.md`, `docs/xap-opcodes.md`). *Lesson: compile reference code to learn an ABI, never infer it from call sites.*
2. **The signature scheme cracked (2026-09-24 to 2026-09-27).** An unsigned-stack probe was rejected with `errFILE` on 2026-09-24 (cause unknown; recovery by reflashing official 3.0.3 proven); Bose's modulus was recovered and the compress found to read only bytes 0..33 of each block (2026-09-26); probe8 (16 bit flips plus a digest collision) was accepted on 2026-09-27 and `tools/fsedit.py` then wrote arbitrary chosen bytes (probe9). *Lesson: the blind window is the only door, and it is 29 bytes wide; say "stack probe rejected once, cause unknown", never "USB route closed".* (`docs/dfu-signature-scheme.md`; memory `csr8670-unsigned-stack-area`.)
3. **Early probes: a hook that was the wrong button (2026-09-29 to 2026-09-30, probes 22-47).** Probes 10-24 pressed the centre button but hooked the Bluetooth-hold block (`0x4003` at `0xAE0`); the owner's retraction is at line 453. Probe29 was the first cave to run and return cleanly (line 567) and probe37 proved the "id in AL" lever, where our code picks which stock prompt plays (line 1056). *Lesson: prove a hook from the button, not from local code reading.*
4. **Trap numbering and the tone (2026-09-30, probes 46-90).** The speaker's `vm.app` is BlueLab 7.3, so 173 of 257 trap numbers differ from the ADK 4.4's; probes 46/47 had called `KalimbaPowerOff` and the "audio-injection route closed" verdict was withdrawn (line 2161). The right ABI settled (probe59-67); probe77 produced the first software-authored sustained sound (a ringtone to port 3, "long tone ... car horn") (line 3669). `enterl -k` reserves its top two slots, which explained seven crashes (probes 68-81, `docs/cave-frame.md`). *Lesson: name traps from the device's own BlueLab version; a crash census beats theories.*
5. **The DSP wedge and the transform route (2026-10-01, probes 91-106).** Wiring a DAC route ourselves wedged the VM (probes 96, 97); the design inverted to "firmware owns the audio path, the cave injects into port 3"; probe104 proved `TransformAdpcmDecode` over a region source carries audio (line 5546), and refill loops (105/106) crashed (`docs/cave-heap.md`). *Lesson: one wedge is not a diagnosis; liveness is `bose-dfu info -f`, not `list`.*
6. **Unit 1 lost, 2026-10-04 20:23.** Eleven flashes and nine presses in 92 minutes with zero readbacks; the speaker stopped enumerating in any mode (`PSKEY_USB_VM_CONTROL = 1`, so a dead app means no USB). Whether a truncated write or a bad cave word killed it is undecided (`docs/POST-MORTEM-2026-10-04.md`, line 7537, line 8286). *Lesson: no readback means no next flash; a working result is the signal to slow down.*
7. **Unit 2 (from 2026-10-04) and the first loud noise.** The replacement arrived on stock 1.1.3, was brought to 3.0.3.6546 with the readback path proven both ways (line 7577), and `docs/FLASH-PROTOCOL.md` became the gate. Probe134 (2026-10-05) made generated audio loud: the IMA decoder is a leak-free accumulator, so a free random walk drifts to DC and only zero-net blocks stay audible (line 9213, 9373); heap ceiling kept every one-shot to about 126 ms. *Lesson: the cave must be gated by something boot-safe; the window of 197 words is a fact, not a suggestion (probe130).*
8. **The partition-2 route (2026-10-06, probes 139-144).** Partition 2 is TYPE 3 RAW_SERIAL; a 16-byte overwrite commits (probe140); a staged 33 KB write produced total audio loss (probe141, recovered by a stock flash; the leading explanation is that the cave fired at every power-on and hammered flash during audio init, a hypothesis, line 10119); the mount then returned FALSE (143, 144) and the route was parked (line 10353). Offline replay later showed probe141's gather was shifted by two words, so its p2 content was never a valid filesystem (line 13686). *Lesson: a negative from garbage input is not a negative about the mechanism.*
9. **File-source and prompt/TTS discoveries (2026-10-06 to 2026-10-07, probes 145-157).** Timer refill loops (145-153) all died at 6-9 s; probe154 learned `StreamFileSource` accepts only narrow files (`data_us`, `rphrases_us`); probe155 gave the first sustained, non-repeating generated sound; probe157 found why everything died near 7 s: the Bluetooth-hold hook runs after `fn_0d500` has torn down the pairing and the DSP (line 11670). *Lesson: when five unrelated designs stop at the same number, the number belongs to something none of them changed.*
10. **The DSP reload line (2026-10-07 to 2026-10-08, probes 158-171).** Reloading `sbc_decoder` from the cave worked (probe160 clean, probe161 answered `MUSIC_READY`), but after probe158's wedge and probe162's re-tick wedge, ten probes gave the reloaded DSP every stock message, the DAC wiring and the hardware gain and the DAC stayed silent (line 12845). Wedge recovery learned: unplug USB, hold POWER about 20 s (POWER + centre did not work). *Lesson: stop when the one remaining difference (codec input) is something the pairing teardown removes; remove the teardown instead.*
11. **The pivot: the centre-button hook (probe172, 2026-10-08).** Hooking `0x00e46` (event `0x4004`) while connected removes the pairing teardown: the owner heard only the cave's prompt, no pairing, and the stock DSP stayed up (line 12923). *Lesson: the product trigger and the fix for the 7-second wall were the same change.*
12. **Runaway, sustain and the crashing stop (probes 173-175, 2026-10-08 to 2026-10-09).** Probe173 ran away loud and harsh until power-cycled (its 9.5 s re-tick re-sent `0x1072`, disconnected a running transform and spoke; which of these caused the runaway was never separated, `verify.md` V3); probe174 sustained a chunk well past 7 s (a `data_us` chunk is about 55 s at 8 kHz, about 220 s at 2 kHz by arithmetic); its stop press, and probe175's silent stop, restarted the speaker (lines 13002, 13112, 13177). The offline stack study later found the likely cause: `TransformFromSink` returns the downstream node and `TransformStop` on it panics (`Panic(0x4030)`, well-supported, never pressed). *Lesson: compute chunk durations from file size and rate; never touch a busy port 3; the transform-teardown stop is retired.*
13. **The start-only cycle (probes 176-177, 2026-10-09).** After a directory slip (176), probe177 with `tts/rphrases_us` ended each chunk by itself and the next press built another: first chunk about 3 s, second about 12 s and lower; the stock unloads the DSP if the music is paused (lines 13286, 13315). *Lesson: the design that touches nothing dangerous (one chunk per press, no stop) is the one that worked.*
14. **The level (probe178, flashed 2026-10-09, result 2026-10-10).** Word b of `0x1072` set to 2 gave "Quieter on Both": the level knob is ours at once, only the rate is latched (line 13394). *Lesson: change one thing per flash; each ear result then names its cause.*
15. **The offline design (2026-10-10).** With the owner away, a multi-agent workflow produced a judged plan of six flashes (`docs/deep/offline-2026-10-10/DESIGN.md`), an ADPCM codec and a brown-noise generator, a cave world-model simulator, probes 179-181 built and gated but not flashed, a static reading of the stack image, eleven adversarial checks (most "proven" labels downgraded), and the return-day checklist. *Lesson: a static reading that never met the hardware is a plan, not a result; step 0 on the speaker comes before any new flash.*

---

## 6. Where we are

### 6.1 Proven for the deliverable (on the speaker, probe178)

| item | what is established | confidence and source |
|---|---|---|
| trigger | A centre LONG press (>= 1.5 s) with a device connected reaches `0x00e46` as `AL = 0x4004`; the cave runs; no pairing is entered; the Bluetooth long press is stock again. Repeated on probes 172-178 | proven (owner presses); "swallowed cleanly" and "emitted only in states 2/3/13" were downgraded: other senders of `0x4004` exist (`verify.md` V0). Boot safety is well-supported, not proven |
| one chunk per press | one press builds one noise chunk that ends by itself; 174 sustained well past 7 s on `data_us`; 177/178 chunks end on their own | proven (owner quotes, lines 13112, 13315) |
| start-only cycle | with music playing, a chunk ends, port 3 is free, the DSP stays loaded, and the next press builds a new chunk | proven for n = 2 (probe177 result 2, probe178); "press after press" for N > 2 is not proven (`verify.md` V1) |
| level | `0x1072` word b = 2 is quieter than b = 0 on the first and the second chunk ("Quieter on Both"); the handler writes shift 4 or 7 | proven by ear and decode; "18 dB" is arithmetic, not measured (`verify.md` V4) |
| rate quirk | the first chunk after a press plays about 4x faster than the second (about 3 s versus about 12 s for the same 10,486 bytes); our 2000 Hz rate shows from the second chunk | observed, n = 2, ear estimates; the cause is **unknown** (`verify.md` V5; probes 128-134 are unreconciled counter-evidence) |
| loudness | "always loud", independent of the volume buttons and the music volume | one hedged ear report only (probe177); a hypothesis until step 0 A5 |
| needs music | with music playing the DSP stays loaded; paused, the stock unloads it after the tone and the next press speaks 0x3E "bluetooth off" | proven n = 1; the delay is unmeasured (`verify.md` V6; the old "about 8 s" is wrong) |

### 6.2 Not proven

| item | state | what would settle it |
|---|---|---|
| material | no brown-noise file exists on the device; `rphrases_us` is a stand-in that decodes about 36 percent clipped. Payload and previews are built offline (`build/noise/`, `build/payload/narrow184/`) and have never played on the speaker | probe184 (the p2 write) then 185a, and the owner's ear |
| looping | designed (a read-only poll from a `MessageSendLater` tick); no tick was ever observed from the `0x00e46` hook, the busy read of a RUNNING transform was never observed, and the seam is 0-1 s per chunk by design | step 0 on probe178, then probe179 press A |
| stop | the transform-teardown stop crashed twice; `MessageCancelFirst` is a hypothesis that has never run from a cave; today the only stops are letting the chunk end, pausing the music, or the Bluetooth long press | probe180 |
| keep-alive with music paused | the stock unloads the DSP after the tone; a 1 s poll is expected to lose the race; v1 is specified as "music must be playing" | step 0 A4, probe179 press B |
| rate quirk cause | unknown; authoring at 8000 Hz and sending `a = 8000` is a bet | probe181 |
| partition-2 route | a 16-byte write commits; nothing above 16 bytes is proven; `PartitionMountFilesystem` returned FALSE on garbage content; misaligned-erase brick risk is not excluded by measurement; the only unit; needs the owner's explicit go-ahead | probes 182, 183, 184 and the verify image |
| nothing-connected use | the stock table gates the centre long press to connected states; a 9-word table edit that would lift this is designed (`docs/deep/centre-long-press.md`) but no assembler contains it, and the cave-loaded DSP is silent without codec input (162-171) | not planned for v1 |

---

## 7. The next steps, in order (from `docs/RETURN-CHECKLIST.md`)

No flash and no device command until the owner says the speaker is back. Every flash then takes every gate of `docs/FLASH-PROTOCOL.md`; one flash, one press, one recorded result.

| # | step | gate or decision | detail |
|---|---|---|---|
| 0 | Pre-flight on the dev machine, no device: docaudit, probe179 assemble, `cavesim probe90` control, every refusal path, preflight, caveguard, stackdepth, regression battery | all expected lines match, else STOP | RETURN-CHECKLIST section 0 |
| 1 | **Step 0: zero-flash presses on probe178.** A1 busy read (second press during a chunk), A2 ten consecutive presses and presses 0, 2, 5 s after the end, A3 settling press, A4 paused unload timing, A5 loudness against the volume buttons, optional A6, A7 | owner decision D0 (accepts that A1 runs the busy read no press has exercised); a restart or a 3 s-early rebuild means no 179 flash today | section 1 |
| 2 | **probe179**: bounded poll loop (3 chunks then 0x26 "ended"), press A with music playing, press B paused; `build/hook/probe179_brown.dfu`, sha256 `a31e2fe8...cd276`, 181 words | D4 (v1 needs a playing stream), D6 (a 0-1 s gap is acceptable) | section 2 |
| 3 | **probe180**: unbounded loop, STOP by `MessageCancelFirst`; 174 words, sha256 `f4130846...b3ba` | 179 recorded; G180 | section 4.1 |
| 4 | **probe181**: rate 8000 (two words differ from 180); 174 words, sha256 `d76bef1d...bd53` | 179 and 180 recorded; G181; soak (D8) | section 4.2 |
| 5 | **probe182**: read-only census of the file-source window; **183**: read-only partition-2 census (recommended mandatory, D10) | G182; D10 | section 4.3 |
| 6 | **probe184**: the ONE partition-2 write of the brown payload (30,000 bytes = 7.5 s at 8000 Hz), two-image sequence so spoken ids are not relied on in the staged image | explicit owner go-ahead (D1, D2, D3, D11-D13); the 184 assembler with FIRST = 9 and a rehearsal in the world model are not built | section 4.3-4.4; `payload-184.md`; `promptmap.md` |
| 7 | **probe185a/b**: the loop pointed at our file (185b is the mount fallback); this is the first image that can be brown noise, looping and stoppable | D5, D8; the owner's ear | section 4.3 |
| 8 | **probe186**: level from the volume buttons, one change; E3 poll interval down to 50-200 ms for the seam | D5 | section 4.3 |

Decisions the owner must tick (recommended defaults are pre-filled): `docs/RETURN-CHECKLIST.md` section 5. What is still settled only by a press: section 6.1 there. Previews to listen to first: end of section 6 there. **Strategy review 2026-10-12 (offline, a recommendation, nothing adopted):** `docs/deep/strategy-2026-10-12/STRATEGY.md` rates this sequence AT-RISK against the five goals (rich brown, loops until stopped, seamless, stock behaviour kept, volume control) and proposes reorderings in its section 4 (a seam image 181p and a tiny valid write 184a before the large partition-2 write, a product build, a volume design that replays 0x400d/0x400e) and owner decisions J-D1 to J-D17 in its section 7; index `docs/deep/strategy-2026-10-12/README.md`. Two caveats for v1: it needs a playing stream (a pause or drop ends the noise and nothing resumes), and a brown file on partition 2 would not survive an official updater run (hypothesis, never run); the swallow premise of step 8 (probe186) is refuted as worded (`docs/FACTS.md` F148). **Firmware study 2026-10-12 (offline, static and model results):** `docs/deep/firmware-study-2026-10-12/README.md` answers the offline tasks: the pipe/generator branch is closed (the stack refuses traps above 0xE2), the DSP tone path, stock collisions, auto-off (inert) and the volume path are traced, and 181p, 184a, 184 and 187 are built offline, NOT flashed; functions are in `docs/FUNCTION-CATALOG.md`, facts in `docs/FACTS.md` section 9. Caveat for the partition-2 idea: the default partition table found in vm.app has p2 as RAW_SERIAL with 2,048,000 B (word units), smaller than the 2,090,936 B ext image, so "merge ext and noise" has no home on the default layout (FACTS F216; the live layout is unmeasured).

---

## 8. Ten things a newcomer most often gets wrong

1. **"A port-3 chunk lasts about 7 seconds."** The 7 seconds measured in probes 104-171 was the Bluetooth hook's pairing teardown cutting the chunk off (probe157 proved the DSP gone); on the centre hook a `data_us` chunk is about 55 s at 8 kHz or about 220 s at 2 kHz by arithmetic (not yet timed). Compute durations from file size and rate. Probe173 ran away on the 7 s figure. (memory `csr8670-port3-chunk-rules`; `verify.md` V10; **proven** for the teardown.)
2. **"The centre button reaches the old hook, and the trigger works anywhere."** It does not: `0xAE0` is the Bluetooth pairing event (`0x4003`), one-shot per streaming session, and it runs after the teardown. The product trigger is the centre long press at `0x00e46`; the stock button table turns it into `0x4004` only in the connected states (other senders of `0x4004` exist), and the 9-word edit that would lift this exists only on paper (no assembler contains it). (`docs/deep/hook-gates.md`; `docs/deep/centre-long-press.md`; field-log probe172 entry; **proven** for 172, **well-supported** for the state gate.)
3. **"Zero in the official image plus a blind window means the word is free."** Probe130 crashed the speaker on boot with 55 words in zero gaps inside live tables. The window `0x3E200..0x3E400` is hard-enforced by `tools/caveguard.py`; shrink the design, never widen the window. (memory `csr8670-cave-window`; `docs/cave-budget.md`; **proven**.)
4. **"Trap numbers and the call ABI can be read from the ADK 4.4."** The speaker is BlueLab 7.3 (version stamp `0x3200`): 173 of 257 trap numbers differ, and a compile with `-S` but without `-mal-first` produced the opposite argument order. Name traps from `tools/traps-bluelab73.json`; ABI is arg1 -> AL. A cave `enterl -k` may only use slots 0..k-3. (`docs/trap-numbering.md`; `docs/trap-abi.md`; `docs/cave-frame.md`; **proven**.)
5. **"Stop the noise with TransformStop / TransformDisconnect / StreamDisconnect, or re-send `0x1072`."** The teardown trio restarted the speaker twice (probes 174, 175); the static cause is `TransformStop` on the downstream node (`Panic(0x4030)`, **well-supported**, never pressed). Also never speak while the cave's transform holds port 3 (prompts are mixed through port 3), never re-arm a timer on an assumed chunk end, and never touch a busy port. (`docs/deep/offline-2026-10-10/stack-transform.md`; memory `csr8670-port3-chunk-rules`.)
6. **"The speaker cannot do brown noise, so redefine the goal."** That verdict (2026-10-04, from one probe) was retracted; the owner's streamed brown noise sounds excellent. The limits are in our path (the ADPCM walk, the tone rate, the material). Suspect the pipeline first; the owner's ear decides. (memory `csr8670-speaker-not-the-limit`; field log line 12181.)
7. **"Noise can be written into a file in flash, or generated by walking ADPCM freely."** No contiguous run longer than 29 bytes is ours, only `data_us` and `rphrases_us` can be a file source, and the IMA decoder is a leak-free accumulator (a free walk drifts to DC and is quiet). The as-is files decode 36-62 percent clipped. A dense payload needs partition 2, which is parked and carries the one unbounded brick risk; and the staged `data_us` of probe184 garbles every spoken prompt, so no spoken id is trustworthy inside that image. (`write-constraint.md`; `material-slots.md`; `promptmap.md`; `verify.md` V10; field log line 9213.)
8. **"Older notes labelled PROVEN are proven."** `verify.md` downgraded most DESIGN labels: "busy presses in 176-178" never happened; the "about 8 s" DSP-unload delay is tens of milliseconds and unmeasured; "swallowed cleanly" is withdrawn; looping is proven only for n = 2; `rphrases_us` is a phoneme script, not a directory into `data_us`, and `data_us` is the NowSpeakTTS unit corpus, not raw PCM (the "RAW PCM" in `docs/bose-firmware-anatomy.md` section 12 is withdrawn). The research notes in `docs/deep/offline-2026-10-10/` carry errata banners; `DESIGN.md` section 8 and `RETURN-CHECKLIST.md` section 6 win. Nothing seen only in the stack-image reading is "proven on hardware" until a press.
9. **"Preflight green, simulator green, `list` shows 40fe: the flash is verified."** `tools/preflight.py` checks the file, never the device; the simulator is a model; `list` needs only USB descriptors and reports a wedged speaker as healthy. Only the readback (0 of 975,168 fs bytes differ, every cave word present) verifies a flash, and `bose-dfu info -f` is the liveness test. Unit 1 was lost after eleven flashes with none. (`docs/FLASH-PROTOCOL.md`; `docs/POST-MORTEM-2026-10-04.md`; **proven**.)
10. **"POWER plus the centre button recovers a wedge, and a lost unit can be rescued over USB."** POWER + centre did not work on a wedged app (2026-10-08); what worked was unplug USB, hold POWER about 20 s, replug, press POWER, flash stock and press nothing. With `PSKEY_USB_VM_CONTROL = 1` a dead app means no USB at all and no host recovery exists (SPI only, out of scope by the owner's decision). Do not overstate the 2026-09-24 stack probe as "USB route closed": it was rejected once, cause unknown. (`docs/FLASH-PROTOCOL.md` Recovery; memory `csr8670-unsigned-stack-area`; **proven**.)

Also recurrent: multi-word branch displacement is relative to the last word, so disassembler output before 2026-10-05 was one word short (field log line 8974); and the cause of the unit 1 loss is undecided, though both lessons (readback, cave window) hold.

---

## 9. Where to go for detail

| question | read |
|---|---|
| What is on the speaker right now? | `build/hook/FLASHED` (authoritative), then the `docs/RESUME-HERE.md` banner |
| What do I do before I touch the device? | `docs/FLASH-PROTOCOL.md`; `docs/RETURN-CHECKLIST.md` |
| What is where in the repo? | `docs/PROJECT-LAYOUT.md`; `docs/deep/offline-2026-10-10/README.md` (index of the offline work) |
| How did the first unit die, and how do I avoid it? | `docs/POST-MORTEM-2026-10-04.md`; `docs/NEXT-UNIT-CHECKLIST.md` |
| What exactly happened on a given probe? | `docs/field-log.md` (13,700 lines, append-only evidence; do not edit it). If no per-era digest with line numbers sits next to this file yet, grep the log for `# probeNNN` headings |
| Signature, blind window, digest, fsedit | `docs/dfu-signature-scheme.md`; `docs/deep/offline-2026-10-10/write-constraint.md` |
| Cave budget, frame rules, heap | `docs/cave-budget.md`; `docs/cave-frame.md`; `docs/cave-heap.md` |
| Hooks and buttons | `docs/hook-sites.md`; `docs/deep/hook-gates.md`; `docs/deep/centre-long-press.md`; `docs/centre-button-hook.md` |
| Traps, ABI, message tasks | `docs/trap-abi.md`; `docs/trap-numbering.md`; `docs/trap-stub-table.md`; `docs/message-task-abi.md`; `docs/xap-opcodes.md` |
| Audio path, DSP, tone port, gain | `docs/bose-audio-path.md`; `docs/kalimba-disasm.md`; `docs/deep/dsp-output-wiring.md`; `docs/gain.md`; `docs/dsp-noise-route.md` |
| The stack's ADPCM transform and port-3 lifecycle | `docs/deep/offline-2026-10-10/stack-transform.md` |
| Material, payloads, ADPCM format | `docs/deep/offline-2026-10-10/adpcm-format.md`; `material-slots.md`; `payload-184.md` |
| Prompts, TTS corpus, spoken ids | `docs/request-id-catalog.md`; `docs/deep/offline-2026-10-10/promptmap.md`; `docs/bose-firmware-anatomy.md` (section 12 partly withdrawn) |
| Partition 2 | `docs/partition-route.md`; `docs/deep/offline-2026-10-10/verify.md` V11 |
| The judged plan and which claims survived | `docs/deep/offline-2026-10-10/DESIGN.md` section 8; `verify.md` |
| Firmware map and named functions | `docs/firmware-map.md`; `docs/deep/AGENT-BRIEF.md` (note: its stack line is out of date; the stack's ADPCM code was read in the 2026-10-10 study) |
| Toolchain and building | `docs/toolchain.md`; `docs/adk-compiler.md`; `docs/adk-tools.md` |

## Round-3 amendment (2026-10-12, curator)

Appended at the end so that line numbers cited elsewhere stay valid. Corrections from `docs/deep/round3-2026-10-12/` that concern this file; full register: `docs/deep/round3-2026-10-12/README.md` section 4. Grades follow the verifier sections of the round-3 notes. Nothing above this heading was edited except a pointer on the status or banner line.

- **R3-C072** (N03 + N04). Claim: FACTS N018 and BIG-PICTURE section 8 item 7: no contiguous run longer than 29 bytes is ours, so no dense payload without p2; dsp-keepalive-rate.md Option 5: an SBC feed into port 0 is a heavy continuous feed. Correction: True for ADPCM. A self-synchronising format fits: an SBC 20-byte frame plus an 8-byte silent cover frame per 29-byte window (simulator: ADK arithmetic with Bose control flow, not the Bose binary). A file source connected with StreamConnect costs no per-byte VM work, but port 0 is held by the stock RTP chain whenever a DSP is loaded, so a takeover (StreamDisconnect(0, ksink0)) is needed and the phone music stays dead until the connection is cycled. Route C is "viable with named defects, not shown to work"; N03 and N04 had no skeptic pass.
- **R3-C124** (PLAN-v2). Claim: The "main route" (cave plus a partition-2 FILE) in STRATEGY, RETURN-CHECKLIST, BIG-PICTURE and INDEX. Correction: PLAN-v2 (docs/deep/round3-2026-10-12/PLAN-v2.md) supersedes the file route with the raw route (G-RAW gate first); it is a RECOMMENDATION pending owner decisions PD-01..PD-32. probe178 is still the only image on the speaker.
