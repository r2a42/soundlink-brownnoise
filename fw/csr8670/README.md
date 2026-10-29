# brown_noise: the generator as a real CSR8670 application

A brown-noise generator as a CSR8670 (gordon) VM + Kalimba DSP app, built with the ADK 4.4 toolchain (`../../docs/toolchain.md`). This is kept as provenance for `build/dsp/noisegen.asm`, which reuses the same LCG constants — it is a separate, earlier (2026-09-24) piece of work from a route this project tried before settling on the signed-DFU cave patch used everywhere else here: a *whole-firmware replacement* built on CSR's own unsigned stack, which needs a hardware SPI burn to install and was retired once the project's scope became software-only (no hardware access of any kind). It never ran on real hardware.

| File | Role |
|---|---|
| `brown_noise.asm` | Kalimba DSP: 24-bit LCG white source, leaky integrator (leak 1/512, input 1/64, clamp ±0.5), one-pole high-pass at ~119 Hz (clamp ±0.5), 256-sample blocks into two cbuffers, 1.5 ms timer copies them to the DAC ports. |
| `main.c` | VM app: drives PIO5 high first (Bose holds it high; board function unknown), loads the `.kap`, DAC A/B at 48 kHz, gain `DAC_GAIN` (default 10, checked against 0..22 at compile time), optional `AMP_ENABLE_PIO` (refuses 5; level set before direction), sends GO. No buttons, no power-off. |
| `brown_noise.psr` | Bose's boot PIO state (PS keys 0x03b5, 0x2591, from the official 3.0.3 DFU): PIO5 and 17 high from reset. |
| `*.mak` | Hand-written project makefiles (in place of xIDE's generated ones). The ADK's `flash`/`keys` targets are disabled. |
| `build.sh` | Builds into `../build/csr8670/` with `HARDWARE=gordon FLASHSIZE=16384`. Wipes that directory first, including old sim captures. |
| `model.py` | Bit-exact Python model of the DSP loop plus the octave-slope test; `--compare` checks simulator captures. |
| `sim.sh` | Runs the `.kap` in the ADK's `kalsim_csr8670`, captures both DAC ports, compares every captured sample with the model. Fails if kalsim exits before the time limit or captures nothing. |

## Build

```sh
./build.sh                                   # Git Bash; needs the ADK at ../../adk/root (docs/toolchain.md)
EXTRA_DEFS="-DAMP_ENABLE_PIO=<n>" ./build.sh # once the amp PIO is known
python model.py ../build/csr8670/model.wav   # check the arithmetic
./sim.sh 20                                  # run the real .kap in kalsim
```

Output (2026-09-24 build, after the high-pass and PIO5 changes):

| File | Size | What it is |
|---|---|---|
| `image/brown_noise_kalimba/brown_noise_kalimba.kap` | 32,752 B | DSP code |
| `image/vm.app` | 5,937 B | VM code, 273 code words |
| `merge.xpv` / `merge.xdv` | 6.4 MB / 0.8 MB | Full internal-flash image: CSR's `stack_unsigned` for gordon + a filesystem holding the two files above. **No PS keys.** |
| `brown_noise.psr` | 622 B | Copied from the source; see "Before it goes on hardware" |

`EXTRA_DEFS="-DAMP_ENABLE_PIO=5"` and an out-of-range `DAC_GAIN` stop the build with `#error`; `make ... flash` stops with an error.

## Verified

- Toolchain: both halves compile and link, `vmbuilder` merges them with the gordon stack.
- Arithmetic (`model.py`): −5.89 / −6.02 / −5.89 dB per octave at 400→800→1600→3200 Hz, −26.3 dBFS RMS, peak −13.2 dBFS over 20 s, never at a clamp. Below the ~119 Hz high-pass the spectrum is flat (band levels 30/60/120/240/480 Hz: 42.1 / 42.5 / 40.8 / 36.7 / 31.5 dB).
- **The built `.kap` in the CSR8670 DSP simulator** (`sim.sh 20`, 2026-09-24): all 3,577,332 captured samples (74.5 s simulated) are bit-exact with the model, left equals right, longest zero run 1 sample. The capture is kept only until the next `build.sh`.

## Not verified

- The VM half (`vm.app`) has not run: there is no VM simulator, and the simulator sends the DSP its "go" message itself.
- Real hardware timing and the DAC/amp path on the speaker.
- What PIO5 does. The data sheet rules out the chip's own power latch; it drives something on Bose's board. This project's scope never included opening the speaker, so only code analysis could hint at what.
- Nothing from this directory has ever been written to the speaker.

## Why this route was abandoned

`merge.xpv` replaces the entire internal flash, including Bose's own application — installing it needs a hardware SPI burn, which this project ruled out entirely (software-only scope). Over USB the only writable thing is a signed DFU container, and this route produces an unsigned image the stock loader will never accept. This directory is kept only as the provenance for the noise arithmetic reused in `build/dsp/noisegen.asm`, which does install over USB, using the signed-filesystem technique documented in `docs/dfu-signature-scheme.md`.

## Open: amplifier enable

Bose's app PS key 0x029a (sink `CONFIG_PIO`, ADK 3.x layout, 15 words, the size matches) has PowerOnPIO, DeviceAudioActivePIO and AudioMutePIO all unset (0xFF). `analog_input` is PIO 12. So the stock firmware does not enable the amp through the standard sink PIO block. This was never resolved, since it would have required opening the board; `AMP_ENABLE_PIO` is left undefined in the build and drives no PIO.
