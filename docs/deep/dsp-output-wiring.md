# Stock DSP output wiring (2026-10-08, ANSWERED; offline plan item 2)

> **Note on references (public export):** this file cites files from the original private research repository that are not included here; each such path is marked "(not in this export)" at its first mention, and all of them are listed in `docs/NOT-IN-EXPORT.md`. The claims they support are summarised in the text; the cited originals are not needed to rebuild or flash anything.

> **This is an archival research document from the original (larger, private) project repository.** Some of its internal links point at files not included in this public export; where one doesn't resolve, that's why. The repository's own current, self-contained write-ups are listed in README.md's "Repository layout" section.

Read from `build/analysis/full-disasm.txt` (not in this export) and the ADK 4.4 source in `adk/root`; nothing
on the device.

## Answer in one paragraph

On this speaker the stock firmware connects **DSP write port 5 -> DAC channel A** and **DSP
write port 6 -> DAC channel B** (both `AUDIO_HARDWARE_CODEC`, instance 0), synchronised,
each at `STREAM_CODEC_OUTPUT_RATE` (0x301) = the params sample rate, then **unmutes each
sink** (`STREAM_AUDIO_MUTE_ENABLE` 0x700 = 0). It is all done by one stock library function,
**`fn_1f04c(&params)`** (the audio_output library's connect). **The A2DP teardown undoes
it**: `fn_31734` calls `fn_1f12b` = `AudioOutputDisconnect`, which closes every DAC sink.
So **a reloaded DSP has no path to the DAC until something calls `fn_1f04c` again**, and
the cheapest way for a cave to rewire is to make that same call, with the params the stock
prompt builder uses: `{0x0000, 0xbb80, 0x0000}` = 48,000 Hz, plain connect, no outputs
disabled.

## How fn_31af3 maps onto the ADK source

fn_31af3 is `MusicConnectAudio` (`csr_a2dp_decoder_common.c`), from an older ADK than 4.4,
so its callees are ordered differently. Matched by the messages each one sends:

| Bose | ADK | evidence |
|---|---|---|
| inline in fn_31af3 | `audioDecoderConnectInputSources` | the codec switch, `TransformRtp*Decode` into Kalimba sink 0 |
| **fn_31d3f** | `InitMultiChannelParams` + `AudioOutputConnect` + `dsp_resample_rate` | 0xbb80 (48 kHz, subwoofer case) or codec rate; `fn_1f04c(&params)` under PanicNull; stores rate/10 at `@(20,decoder)` |
| fn_323ca | back-channel/sub check | `ld AL,#0 ; rts`: always off |
| fn_31f8d | forwarding/relay sink | `KalimbaSource(0/1)` to `@(10,arg)`, not the DAC |
| fn_31a0d (+ fn_314bf, fn_31de1, fn_31e2c) | `CsrA2dpDecoderPluginSetMode` | 0x1001 MUSIC_SETMODE (twice in fn_31de1), 0x100e; **no stream calls** |
| fn_313f0 | `audioDecodeSendDspSampleRateMessages` | 0x1070 MUSIC_MANAGER_SAMPLE_RATE, 0x1071 CODEC_SAMPLE_RATE |
| fn_31349 | the 0x600 (wired input) variant | 0x1073/0x1074, ADC `StreamAudioSource(2,0/1)` keys 0x504/0x501 into Kalimba sinks 1/0 |
| fn_3143c | `audioDecodeSendDspMultiChannelMessages` | 0x10a0 output types (long message, 7 words), 0x10a1 I2S config if I2S |
| 0x31d27 | `audioDecodeEnableDsp` | 0x7000 GO |

`csrA2dpDecoderDspLoadedAndConfigured` also **sets the digital volume to MUTE before
connecting** and raises it later through `SetLevels`; see "still open".

## The audio_output connect, fn_1f04c(&params)

`params` is 3 words: `{rate_hi, rate_lo, flags}`; flags bits 7-8 pick the transform
(0 = `StreamConnect`, 1 = `TransformAdpcmDecode`, 2 = connect-and-dispose `fn_39626`), bits
9+ are a per-output disable mask.

1. Guards: config pointer `@0x6d0` non-zero, "connected" bit 15 of `@0x6d1` clear,
   rate non-zero. Otherwise it returns 0 without doing anything.
2. For output `i = 0..6`: if mapped (`fn_1f398(i) != -1`), the source is
   `StreamSourceFromSink(StreamKalimbaSink(fn_1f381(i)))`.
3. `fn_1f20f` (the ADK's `connect()`), pass 1: for each mapped output `fn_1f32c`
   configures the sink (DAC: `SinkConfigure(sink, 0x301, rate)`; 0x500 is SPDIF,
   `fn_383e3` is I2S) and calls `fn_1f5e6`; `SinkSynchronise` chains each sink to the last.
4. Pass 2: `fn_1f371(i)` = `StreamAudioSink(type, instance, channel)`, connect per the
   flags, then `SinkConfigure(sink, 0x700, 0)` (**unmute**).
5. Copies params to `0x6d2..0x6d4`, sets `0x6d1` bit 15 (connected).

`fn_1f381` (output -> DSP port, a 7-case switch at brxl 0x1f387):

| output | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| DSP port | **5** | **6** | 7 | 8 | 4 | 9 | 10 |

This differs from ADK 4.4 (`DSP_OUTPUT_PORT_PRI_LEFT` = 4); Bose's build is older.

## Which outputs this speaker maps (PSKEY_USR40)

`fn_0b476` reads PS key 0x28 (`PSKEY_USR40`, 12 words, readback `0000 0000 0023 0001 ...`),
`fn_0b426` walks raw words 0-2 and `fn_0b381` / `fn_0b39f` fill the 2-word-per-output
table that `@0x6d0` points at:

- Raw word 2 = `0x0023` is live (bit 0 set, role = bits 3:1 = **1**).
- `fn_0b2de`: role 1 -> **output 0** (role 2 -> 2, 3 -> 4, 4 -> 5). Channel from
  `fn_0b2c0` = bit 4 = 0 -> **A**.
- Bit 5 is set, so `fn_0b39f` adds a pair: `fn_0b2f6`: role 1 -> **output 1**, channel
  from `fn_0b2cf` = NOT bit 4 -> **B**.
- Hardware type CODEC (3), instance 0, per the extractor chain already in
  `docs/field-log.md` (not in this export) (2026-10-02).

So outputs 0 and 1 -> ports **5** and **6** -> DAC **A** and **B**. That agrees with the DSP
side: sbc_decoder's output chain checks write ports `0x800011`/`0x800012`, and the ADK's
`cbuffer_defines.h` gives CSR8670 12 ports with `WRITE_PORT_MASK = 0x80000C`, so those are
write ports 5 and 6.

**Correction to the 2026-10-02 reading** (field log, "Exactly one output is configured"):
there is one live *descriptor*, but bit 5 makes it a **stereo pair**, two outputs. The
device drives DAC A **and** B, synchronised. probes 86-90 opened channel A alone. That is
not shown to be why they were silent (the codec route stays closed), but "channel A alone"
is not what the stock firmware does.

## The teardown undoes it (fn_1f12b = AudioOutputDisconnect)

`fn_1f12b` (callers include the A2DP disconnect `fn_31734` at 0x3174e and the prompt
paths at 0x2319b/0x231c2): for each output, `fn_1f5e6`, `StreamDisconnect`, `SinkClose`;
then clears `0x6d1` bit 15 (connected) and bit 14 (I2S, via `fn_385fb`). It does **not**
touch `@0x6d0`, the config pointer. After it runs, `fn_1f04c`'s guards pass again.

## What this means for probe162 (the "voice prompts on" branch of probe161)

The DSP is reloaded *after* the A2DP teardown, so the DAC is disconnected when the cave
says GO. To hear anything, the cave must rewire before or at GO:

    KalimbaSendMessage(0x1072 ...)            as now (tone-port config)
    fn_1f04c(&params)  params = {0, 0xbb80, 0} in the const window (3 words, DATA)
    KalimbaSendMessage(0x7000 GO, 0,0,0,0)
    port-3 transform                          as now

Cost: about 3 code words for a far `bsr` to `fn_1f04c` (address in AL), plus 3 const
words for params. Hand-coding the same wiring (two `StreamAudioSink`, two
`SinkConfigure` rate, `SinkSynchronise`, two `StreamKalimbaSink` + `StreamSourceFromSink`,
two `StreamConnect`, two unmutes) would be 11 trap calls, roughly 50 words.

Precondition, checkable on the device only indirectly: `fn_1f04c` returns 0 (and the
stock caller would Panic) if `0x6d1` bit 15 is still set, i.e. if the teardown did not run.
The cave should test the return value and speak a distinct id on 0, not Panic.

## Still open

- **Rate.** The DAC rate must match what the DSP outputs. The prompt builder uses
  48,000; music uses the codec rate. Whether sbc_decoder without 0x1070/0x1071 runs its
  output at 48 kHz is unknown. Sending 0x1070 with 4800 (rate/10, as `fn_31d3f` stores
  it) before GO is the stock-consistent choice and costs one message.
- **Volume.** The plugin mutes digital volume before connecting and raises it through
  `CsrA2dpDecoderPluginSetLevels`. Which message Bose's build sends for that (0x1002 in
  older ADKs; 4.4 has `MUSIC_VOLUME_MSG_S` 0x10a9) is not yet found. If the reloaded DSP
  defaults to mute, the tone port may be silent even when wired. Next to read:
  `fn_1f5e6` (called per output in both connect and disconnect: likely the hardware gain)
  and the SetLevels path that calls `fn_1f589` (`AudioOutputGainSetHardware`).
