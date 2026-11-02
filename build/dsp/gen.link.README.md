# The linker script for the DSP generator: not shipped here

> **Note on references (public export):** this file cites files from the original private research repository that are not included here; each such path is marked "(not in this export)" at its first mention, and all of them are listed in `docs/NOT-IN-EXPORT.md`. The claims they support are summarised in the text; the cited originals are not needed to rebuild or flash anything.

`noisegen.asm` links against a linker script named `gen.link` (see the comment at the top of `noisegen.asm`), which must sit next to it in this directory to build. It is not included in this repository, because it is a one-line change to the ADK's own vendor linker script, and the ADK is not redistributed here (see `NOTICE`).

To produce it yourself:

1. Copy `adk/root/kalimba/architecture/gordon.link` from your own ADK 4.4 install to `build/dsp/gen.link` (not in this export).
2. Change exactly one line — the `PM_REGION` line near the top:

   ```
   region PM_REGION    0x000000   0x002BFF    CODE;
   ```

   becomes

   ```
   region PM_REGION    0x002A00   0x002BFF    CODE;
   ```

   This narrows the region the linker is allowed to place the generator's code in, to the specific free program-memory window this project found and used (`docs/dsp-generator-route.md` section 3). Nothing else in the file changes.
3. Build as normal (`docs/toolchain.md`).
