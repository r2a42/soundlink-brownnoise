# The brown-noise DSP app already exists. The blocker is delivery.

> **Note on references (public export):** this file cites files from the original private research repository that are not included here; each such path is marked "(not in this export)" at its first mention, and all of them are listed in `docs/NOT-IN-EXPORT.md`. The claims they support are summarised in the text; the cited originals are not needed to rebuild or flash anything.

> **2026-10-28 banner:** the conclusion below that DSP code can only be delivered by a runtime partition write is superseded. The DSP's program memory is writable at run time through its PM window (DM 0x020000/0x030000 + PM address after DM[0xFE65] := 1), which needs no filesystem edit and no partition write; a DSP-side noise generator runs on the speaker (probe380). See `docs/dsp-generator-route.md` and FACTS F316-F321. The statements about the signed filesystem (a `.kap` cannot be authored through the blind windows) remain true.

> ## UPDATE, 2026-10-08: DELIVERY IS SOLVED. LIFETIME IS THE BLOCKER, AND IT IS THE DSP.
>
> **Audio works.** probe155 produced loud noise on hardware with no repeating part at all:
> `FileFind(FILE_ROOT,"NowSpeakTTS",11)` → `FileFind(dir,"data_us",7)` →
> `StreamFileSource` → `TransformAdpcmDecode` → `TransformStart` into port 3. One source, one
> transform, no timer, no teardown, no `malloc`. Two file facts made it work, both now
> established: `StreamFileSource` returns 0 for anything that is **not a NARROW file**
> (`stream.h:300`), and the only two narrow files in the image are `NowSpeakTTS/data_us`
> (219,528 B, flags 0x00) and `tts/rphrases_us` (10,486 B) — every `.kap` and `vm.app` are
> flags 0x40 "code" and are not streamable. `dumpfs.py` prints the flag byte.
>
> **What stops it is the DSP, not the data.** probe157 measured
> `KalimbaSendMessage(0x1072)` returning FALSE ~7 s after the press: `sbc_decoder` is gone,
> because the press enters pairing and `fn_0d500` (called at `0x00ac2`, before the hook) tears
> A2DP down. See `docs/deep/hook-gates.md` (not in this export).
>
> **The direct port write is parked.** probe152's census found `SinkSlack` on port 3 reports no
> usable room, and Bose never claims, maps or flushes an audio sink anywhere in this firmware.
>
> **And reloading the DSP from the cave WEDGED THE DEVICE.** probe158 added, on a FALSE gate,
> `FileFind(FILE_ROOT, 0xbd75, 27)` → `KalimbaLoad(idx)` → re-gate → rebuild. Owner: "noise for
> 5 seconds and then it wedged. I can't reboot it." Recovery needed a flash back to stock
> (cycle 35) and the ordered procedure in `docs/FLASH-PROTOCOL.md`. `KalimbaLoad` from a cave
> is clean in isolation (probe93), so the suspect is reloading `sbc_decoder` **underneath a
> live A2DP teardown**. **Do not reintroduce a cave-driven `KalimbaLoad` on this hook without
> explaining that wedge first.**

**2026-10-01.** Research that reframes the whole project.

## 1. A verified brown-noise generator for this exact chip was built a week ago

`fw/csr8670/brown_noise.asm` — 243 lines of Kalimba assembly for gordon: a 24-bit LCG
(constants `-4508331`, `17`, seed `21845`, the same as the ADK's `$math.rand`), a leaky
integrator (leak 1/512, input 1/64), a one-pole high-pass near 119 Hz, both clamped to
±0.5, producing 256-sample blocks into two cbuffers feeding DAC ports 0 and 1 on a
1.5 ms timer.

Built: `fw/build/csr8670/brown_noise_kalimba.kap` (not in this export) — **2,047 records = 4,094 bytes of
payload.**

Verified in `kalsim_csr8670.exe` (`fw/csr8670/README.md`):

- **−5.89 / −6.02 / −5.89 dB per octave** at 400→800→1600→3200 Hz — textbook brown;
- −26.3 dBFS RMS, peak −13.2 dBFS over 20 s, never clamping;
- **all 3,577,332 captured samples (74.5 s) bit-exact** against a Python model.

It was built on 2026-09-24 for the *whole-firmware-replacement* route and shelved when
the owner chose software-only. **The hard part of this project was finished before the
software-only work began.**

## 2. The `.kap` format is settled, and ours is interchangeable with Bose's

`elf2kap` emits ASCII records of exactly 16 bytes (`@%06X   %04X\r\n`); the device's
filesystem holds **the same values as a flat little-endian 16-bit word array.**

Verified directly: the device's `NowSpeakTTS.kap` begins `0a00 0001 4000 0000`, i.e.
words `000a 0100 0040 0000` — byte-identical to the first four records of our built
`brown_noise_kalimba.kap`. All five images share the same **201-word `elf2kap -b`
gordon bootstrap prefix**; big-endian gives a 0-word match, so byte order is settled.

Size is not a constraint: 4,094 bytes is 6% of `sbc_decoder.kap` (69,994 bytes).

## 3. Port 3 wants exactly what we can produce

`$TONE_IN_PORT = ($cbuffer.READ_PORT_MASK | $cbuffer.FORCE_PCM_AUDIO) + 3` = `0x946003`
(`adk/root/kalimba/apps/a2dp_sink/codec_decoder.h:195`,
`adk/root/src/kalimba/core/cbuffer_defines.h:45,85-87`): **little-endian,
sign-extended, saturating, plain 16-bit PCM, no framing**, resampled DSP-side from
whatever rate `0x1072` declared. Mono is a plain stream; stereo is L/R interleaved on
the single port.

> **CORRECTION, 2026-10-02.** The gain claim below is wrong for this speaker.
> Bose's binary adds **+4**, not the ADK's +8, so the tone shift is **7** (word b
> bit 1 clear) or **4** (set) -- both BELOW the unity 16->24-bit alignment of 8.
> There is no +18 dB boost and nothing saturates; passing word b = 0 is simply the
> louder of the two by 18 dB. See `docs/kalimba-disasm.md` (not in this export).

`0x1072`'s word a is **plain Hz, not Hz/10** (unlike `0x1070`/`0x1071`, which divide by
`DSP_RESAMPLING_RATE_COEFFICIENT`), and bit 1 of word b selects a **+18 dB** tone shift
(`codec_tones.asm:476-502`). Setting `$aux_input_stream_available = 1` at
`codec_tones.asm:516` is what actually arms the port-3 reader.

## 4. The DSP cannot be told to generate noise

`sbc_decoder`'s entire registered message set is `0x1070/0x1071/0x1072` plus the
`music_example` table (`music_example_system.asm:425-467`) — mode, config, EQ, volume,
mute, I2S, ANC, SPI. **Nothing synthesises.** A sweep of the a2dp_sink app and every
Kalimba library for `tone_gen|sine_gen|oscillator|noise_gen|white_noise|loopback|
TEST_MODE|…` returns zero hits, and `SETMODE` offers only `STANDBY/PASSTHRU/FULLPROC`.

Four generators exist in the ADK but none is reachable in Bose's image:

| generator | where | why unreachable |
|---|---|---|
| DTMF dual-sine, message **0x7150** | `src/kalimba/dtmf/dtmf.asm`, prebuilt `gordon/dtmf.a` | **no shipped ADK app links `dtmf`** |
| `$math.vector_rand` — LCG white noise, fills a buffer | `src/kalimba/math/rand.asm:93-120` | `math` is linked but `--gc-sections` drops the unused symbol |
| gain-controlled comfort noise | `src/kalimba/codec/stream_decode.asm:785-889` | a2dp_sink uses `$codec.av_decode`, off this path; `COMFORT_NOISE_GAIN` exists only for `voice_prompt_sbc` and is 0 |
| `$M.AEC_500.comfort_noise_generator`, **colour 0 = BROWN** | only inside `gordon/cvc_modules.pa`, no source; `a2dp_low_latency_1mic/send_proc.asm:874` | needs CVC frame/FFT scaffolding a2dp_sink has not got |

Sending `0x7150` as a probe costs nothing, but expect no effect.

## 5. Delivery: the *signed-filesystem* routes are closed, with numbers

> **CORRECTION, 2026-10-02.** This section used to be titled "both filesystem routes
> are closed" and the project has been treating `.kap` delivery as settled. That
> overstates it. Authoring or caving a `.kap` **inside the signed filesystem** is
> genuinely closed, by the arithmetic below. But a **runtime partition write**
> (`StreamPartitionOverwriteSink` -> `PartitionMountFilesystem` -> `FileFind` ->
> `KalimbaLoad`) bypasses DFU signing altogether, every trap it needs has a stub,
> and it has never been attempted. Its honest status is **"unproven, and the only
> route in this project with a brick risk worse than a recoverable wedge"** -- not
> "closed". It is also the only route to clean, infinite, refill-free brown noise
> with no paired device, because the DSP would generate it itself.


`KalimbaLoad(FILE_INDEX)` can only open a file already in the read-only filesystem. Our
only write channel is the blind window: **29 arbitrary bytes in every 64**, the other 35
fixed by Bose's signature.

### Authoring a whole `.kap` through the windows is arithmetically impossible

For each existing `.kap`, counting only the bytes we *cannot* change, and trying all 64
possible block alignments to find the best case:

| target | bytes already matching | best alignment | **unchangeable bytes still wrong** |
|---|---|---|---|
| `NowSpeakTTS.kap` | 1,619 / 4,094 (39.5%) | 62 | **1,333** |
| `soundClearWb.kap` | 1,113 / 4,094 (27.2%) | 0 | 1,608 |
| `sbc_decoder.kap` | 1,085 / 4,094 (26.5%) | 2 | 1,606 |
| `soundClearNb.kap` | 1,009 / 4,094 (24.6%) | 10 | 1,668 |

The best case still needs **1,333 bytes changed that cannot be changed.** The 39.5%
agreement for `NowSpeakTTS` is mostly the shared 402-byte bootstrap plus chance.

### Caving an existing `.kap` is capacity-starved

Zero runs of 16+ words, which is the only space a DSP cave could use:

| image | words | zero runs | total zero words |
|---|---|---|---|
| `sbc_decoder.kap` | 34,997 | 3 (39, 39, 16 words) | **94** (0.3%) |
| `NowSpeakTTS.kap` | 15,538 | 0 | **0** |
| `soundClearNb.kap` | 28,093 | 0 | **0** |
| `soundClearWb.kap` | 32,621 | 0 | **0** |

At 45% writable that is a handful of *file* words per run, and gordon instructions are
wider than one file word. Nowhere near enough for a generator plus buffer handling.

> **So delivery cannot come through the signed filesystem.** The remaining candidate is
> a **runtime partition write** — `StreamPartitionOverwriteSink` (0x257) /
> `StreamReformatSerialFlashSink` (0x273) — writing the 4,094-byte `.kap` and then
> `KalimbaLoad`ing it.

## 6. The build toolchain is already working in this project

`kas.exe` (kalasm3, *not* `kalasm`), `klink.exe`, `kar.exe`, `elf2kap.exe` (`-b` for
bootstrap), `kalsim_csr8670.exe`. Gordon flags: `-DGORDON -DKAL_ARCH3 -DKALASM3
-mchip=gordon`. **144 gordon `.a` archives were built locally** into
`adk/root/kalimba/lib_sets/sdk/gordon/` (logged in `adk/kalimba-libs.log`), including
every library `sbc_decoder.xip` needs — plus `dtmf.a`.

Full DSP source is present: applications in `adk/root/kalimba/apps/` (including
`a2dp_sink` and `voice_prompt_sbc`, the latter almost certainly the template for Bose's
`NowSpeakTTS.kap`), libraries in `adk/root/src/kalimba/`. `adk/root/` is ADK **4.4**,
`adk/4.3.1/app/` is 4.3, and the DSP app sources are byte-identical between them apart
from a version string.

## 7. Open questions

- **Whether Bose's `sbc_decoder.kap` registers any message beyond the ADK set**,
  including `0x7150`. A word scan of the image is weak evidence in both directions
  (49 of 256 `0x10xx` values and 17 of 256 `0x71xx` values occur by chance), so this
  needs a real Kalimba disassembly or an on-device probe.
- **Whether `SinkClaim`/`SinkMap`/`SinkFlush` work on an *unconnected*
  `StreamKalimbaSink(3)`.** `sink.h:43,66,88` document failure on a *connected* sink and
  say nothing about the unconnected case; no ADK code tries it. This is the single most
  load-bearing untested idea for a software-only path, and it is cheap to test.
- Whether a `dtmf`-augmented `sbc_decoder` would fit in gordon's 11,264 PM words.

## Round-3 amendment (2026-10-12, curator)

Appended at the end so that line numbers cited elsewhere stay valid. Corrections from `docs/deep/round3-2026-10-12/` that concern this file; full register: `docs/deep/round3-2026-10-12/README.md` (not in this export) section 4. Grades follow the verifier sections of the round-3 notes. Nothing above this heading was edited except a pointer on the status or banner line.

- **R3-C034** (R03). Claim: T02 follow-up 3 / E31 and N02:27: sbc_decoder has no EQ or biquad; flash records 1-3 may be code. Correction: Flash records 1-3 are DATA (record 1 = 292 bit-packed 24-bit defaults, record 2 = 110 values in 21 groups [-g,0,+g,a1,a2], record 3 = packed 24-bit tables). "No EQ code kernel found" stands; "no biquad" must be softened: biquad-shaped coefficient data exist (window 2, DM2 0xff3786/0xff3790) with the consumer unlocated.
- **R3-C065** (N02). Claim: docs/kalimba-disasm.md:106-109: no hidden noise generator; the ADK $math.rand fingerprint (-4508331) appears in none of the images. Correction: The fingerprint is ADK-4.4 specific. Three PRNG families exist: sbc_decoder dither LCG (13653, +17), NowSpeakTTS noise excitation (-6408327, +13), soundClear 48-bit vector LCG. None is an audible generator reachable by message (well-supported, static only).
- **R3-C066** (N02). Claim: kalimba-disasm.md:85-90,137-141, dsp-noise-route.md:87-90, firmware-map.md:361-365, stock-helpers.md: the registered message sets of the four DSP images; 0x1020, 0x7050, 0x7ab1 appear in no image. Correction: Incomplete: sbc_decoder registers 29 ids plus the masked block 0x7AB0..0x7ABF (0x7AB2 PEEK, 0x7AB3 POKE of a DM word at a 24-bit address, no filter; 0x1020 is SETPLUGIN); only 0x7050 is handled by no image. NowSpeakTTS: 0x6000-0x6003, 0x7000, 0x8001, 0x8007-0x8009. soundClear: 0x4000-0x4600, 0x8007, 0x8008 (+0x8001; Wb also 0x7010/0x7020/0x7021).
- **R3-C067** (N02 + verification). Claim: F097, N036, dsp-noise-route.md section 4, 03-seamless-generator G6: nothing synthesises noise, DSP generators unreachable, proven. Correction: Keep the conclusion, re-grade the basis to well-supported (static only; message sets were incomplete; TTS engine not assessed). Verifier: the "DSP has no write path to PM RAM, so POKE cannot change code" claim (E26) is a hypothesis and probably false (ADK DSP code writes PM RAM through the PM windows), which reopens route B as an untested long shot; the NowSpeakTTS op1 formula is well-supported, not proven (the recursion may be r5 x old output slot, not y[n-1]).
- **R3-C069** (N02). Claim: dsp-noise-route.md section 5: caving an existing .kap is capacity-starved. Correction: Data-word edits are a separate question: the NowSpeakTTS .kap has recursion-stage cells wholly inside blind windows (untested; loader validation of the .kap trailer unknown). Not available as a route.
