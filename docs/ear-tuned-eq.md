# How the sound and the volume cap were chosen (probes 412-427)

Purpose: record how the generator's sound was finally tuned, why recordings through the speaker could not be the target, what the target curve is, and how the volume ladder was capped. Read it if you want to retune the sound yourself.
Status / last verified: 2026-10-31. The author's ear was the final judge throughout.

## 1. Why not tune against a recording made through the speaker

The first target was a recording of a streamed brown-noise app played through the speaker and captured by a laptop microphone array. It was a poor target:

- The array applies stationary-noise suppression and speech enhancement. In the lab notebook the 60-250 Hz band differs by 5-7 dB between two sessions of the same speaker and room.
- The through-speaker curve had dips at 400 Hz and 1.6 kHz and bumps at 1 kHz and 2.5 kHz that are path effects (speaker, room, microphone, codec), not the source.
- Played back, the recordings sounded worse than the generator's own recordings ("these sound like trash"), because the capture chain is audibly lossy.

So the target became the **source itself**: a direct, 48 kHz stereo recording of the brown-noise app (30.6 s, about -26 dBFS rms). Its third-octave shape is flat from 63 to 125 Hz and then falls about 2.5-2.9 dB per octave up to 8 kHz, smooth, with no bumps or dips.

## 2. The target curve

The raw source curve is too bright through this speaker (the small driver and the room add their own lift), so the final target is a hybrid, built in four rounds of "draw it, approve it, flash it, listen":

1. follow the through-speaker measurement (the goal recording) up to 200 Hz, where it crosses -20 dB;
2. then use the source's slope, with a gentler corner than a straight join;
3. then lower everything from 250 Hz up by 4.5 dB (the listener found the first two flashes "still a bit bright").

Generator-response target (dB relative to the 100 Hz peak), probe425:

| Hz | 40 | 50 | 63 | 80 | 100 | 125 | 160 | 200 | 250 | 315 | 400 | 500 | 630 | 800 | 1k | 1.25k | 1.6k | 2k | 2.5k | 3.15k | 4k | 5k | 6.3k |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dB | -40.5 | -33.0 | -12.2 | -1.2 | 0 | -2.5 | -9.5 | -17.7 | -24.7 | -26.5 | -27.4 | -28.1 | -28.5 | -29.4 | -30.3 | -31.2 | -32.2 | -33.0 | -33.8 | -34.8 | -35.7 | -36.7 | -37.9 |

The low end below 60 Hz was left alone on purpose ("low end is fine").

## 3. The generator

`build/dsp/noisegen425.asm` (the Q15 coefficients and the per-sample equations are in the file header; build with `build/dsp/build_noisegen425.sh`, which needs the ADK tools): a linear-congruential sample source feeds a leaky integrator, two state-variable filters in series, and a separate band-pass filter on the white input; the output is a weighted sum of the filter outputs, shifted into the ring. 67 words of DSP program memory. Coefficient-only changes (no new instructions) were retuned with a private fitting script that is not part of this export, with these gates on every build: integer model equal to the DSP arithmetic, a 40-million-sample stability run, at least 10 dB of ring headroom at the top ladder rung, the control probe, preflight, framecheck, loadcheck. The final fit is within 0.42 dB rms of the target between 125 Hz and 6.3 kHz (largest miss 1.2 dB at 250 Hz). Level: 14.6 dB of headroom at the default.

## 4. The volume ladder and its cap

The ladder has 15 levels of 1.2-1.9 dB (mean 1.6 dB, uneven because the ring shift changes every fourth level). In a measured run of the generator the top level was the default plus 9.6 dB, with peaks within 0.1 dB of full scale on the recording microphone. The author judged that top about 4.5 dB too loud and starting to distort.

The cap changes one constant: `PROBE_NLEV` from 15 to 12, which makes the top level 11, about 4.6 dB lower than the old top. Only three cave words change (the `NLEV - 1` immediates in `ladder_core.py`). The default level is 6 (it was 8 before the retune, because the new sound is louder at the same ladder position).

## 5. Power-off with the noise playing

Symptom: power the speaker off while the noise plays, and a power-on right afterwards needs two more presses with a gap, instead of stock behaviour. Waiting about 30 seconds made it normal.

Cause: the cave marks the audio path as busy while the noise plays and left that flag set for 16 seconds after power-off. The stock firmware delays every prompt, including the "battery N%" announcement at power-on, while the flag is set, so an early power-on looked like nothing happened and the next press powered it off again.

Fix (`PWRREL`, 3 cave words): on the power-off event 0x4002 the cave releases its hold at once (it clears the audio-busy word only if the word is its own). The generator has nothing in flight after an OFF, so the 16-second hold has no purpose there. See `build/hook/ladder_ext.py`. The same hold in the older loop image protects a payload transform and is **not** changed the same way without a separate check (`docs/RELEASE-NOTES.md`).

## 6. Lessons

- Tune against the source, not against a recording made through the speaker and a consumer microphone array; judge the final result by ear.
- Do not fit a smooth curve through a measured path response: a cubic or quartic fit of the through-speaker curve scored 3.4-4.3 dB against the captures, and a refit through the path model blew up (+15 dB at 1.6 kHz).
- Draw the proposed curve first and get it approved before flashing; three rounds of redraws were cheaper than three extra flashes.
