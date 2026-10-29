# fw/ — an earlier, abandoned route, kept only for provenance

Everything under `fw/` is this project's own original code, MIT-licensed (`LICENSE`), from a route tried before this project's software-only scope was settled: a from-scratch brown-noise firmware built on CSR's own *unsigned* stack for this chip, meant to replace Bose's application entirely. Installing it would need a hardware SPI burn — out of scope for everything else in this repository, and never attempted.

`fw/csr8670/` is kept because `build/dsp/noisegen.asm` (the generator actually used today, delivered over USB with no hardware access, see `docs/dsp-generator-route.md`) reuses the same noise arithmetic (the LCG constants) first verified here, in isolation, in the Kalimba DSP simulator. See `fw/csr8670/README.md` for what was and wasn't verified, and why this particular route was abandoned.
