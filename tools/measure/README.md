# tools/measure: the hands-free measurement kit (added 2026-10-28)

Purpose: the scripts that turned the speaker into a self-measuring test rig: record the laptop microphone while timed console commands run, then analyse level, spectrum and glitches, and decode spoken census words.
Status: copied from the session scratchpad on 2026-10-28 and cleaned (no stored unlock code, no session paths). Run everything from the repo root. DEVICE ACCESS only for `voltest.py`.

| script | what it does |
|---|---|
| `voltest.py` | records `measure_out/NAME.wav` (16 kHz mono) while sending timed `pw1`, `db`, `kp 196`, `ev N` lines over the TAP/console channel |
| `rms.py FILE.wav` | prints the rms of every 3 s window (is the noise on, steady, silent?) |
| `wav_spec.py A.wav B.wav T0 T1` | compares the spectrum of two recordings (octave-band means relative to 1 kHz, same time window) |
| `glitch.py A.wav B.wav T0 T1` | counts 10 ms blocks whose 3-12 kHz energy exceeds 8x the median (clicks, seam bursts) for two recordings |
| `slots3.py FILE.wav T_EV` | decodes a spoken census word (seven battery-percent prompts, 3.5 s apart from T_EV + 9 s) with faster-whisper, refuses silent slots, checks the 7th (check) digit |
| `gen_model.py`, `gen_tune.py` | bit-exact 24-bit Python model of `build/dsp/noisegen.asm` and the shelf-tuning search against a payload spectrum |

Setup for `slots3.py`: a Python venv with `faster-whisper` and `numpy` (the model `small.en`). Run scripts that import numpy with `python -I` from outside any folder that contains a stray `dis.py`. Method and lessons: `docs/dsp-generator-route.md` sections 6 and 7.
