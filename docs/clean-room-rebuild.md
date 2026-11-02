# Clean-room reproducibility test

See also `docs/payload-build.md` for rebuilding the writer (probe393) and the loop (probe428), including their noise sample.

Purpose: a from-scratch rebuild of the first release's product, probe380 (the DSP-generator route, `docs/dsp-generator-route.md`), done with only this repository and publicly downloadable files, to answer "could someone other than the original author actually follow this." No device was touched; this is a build-only test.

**If you just want the result and not the from-scratch rebuild**, read `build/patches/` instead (also summarized in the README's "Reproducing this yourself" section): it ships the already-computed byte-diff between the stock firmware and this image, and a small dependency-free script that applies and verifies it — no vendor toolchain needed. Everything below is the harder, from-scratch path that produced that patch in the first place.

## Result: hash match, with one real caveat

Rebuilding the DSP-generator image from this repository, with only publicly downloadable Bose firmware plus the inputs listed below, produced an output byte-for-byte identical (same sha256) to the image this project actually flashed and verified on its own speaker. **The build is reproducible from this repository alone, given the inputs below** — but see "the one real friction point" further down: one of those inputs (the vendor ADK) is not, itself, something an arbitrary member of the public can simply download, which a later, fully isolated retest (cloning nothing but this public repo, with no access to any of the original project's local files) specifically checked and confirmed. Steps 1-3 below reproduced perfectly in that isolated retest; step 4 is the gate.

## What you need to bring, step by step

1. **This repository** (`build/`, `tools/`, `docs/`).
2. **Stock firmware for your exact product and version** (this project's target: application firmware `3.0.3.6546`), downloaded directly from Bose's own update distribution for this product. The download requires no account and no credentials. Bose's updater finds a device's firmware this way, and so can you:
   - Bose serves a small XML index per device, keyed by the device's USB identity. For this product (USB PID `0x4022`, "SoundLink Micro"), the index is at `https://downloads.bose.com/ced/minnow/index.xml` ("minnow" is this product's internal codename).
   - That index lists the current release (`REVISION="3.0.3.6546"`) and the image filename; the actual file is at `https://downloads.bose.com/ced/minnow/Minnow_3.0.3_stack_plus_app.dfu`.
   - A different Bose product has a different codename and index path; if you're adapting this project to a different speaker, that's where to start looking (and note that none of the rest of this project's specific addresses would carry over to a different product regardless).

   Place the downloaded file at `firmware/bose/minnow_3.0.3/Minnow_3.0.3_stack_plus_app.dfu` (the path this repository's scripts expect; adjust the scripts if you keep it elsewhere). **Confirm its sha256 is exactly**
   ```
   5ae3bc9655af1b80eb78ebe3610eb58473edd715c885f8cdffc3f1b66be4659e
   ```
   **before using it** — a different firmware version will need re-derived addresses throughout this project, not just a different file.
3. **Extract the firmware's internal files** from that stock DFU:
   ```
   python tools/csrdfu.py extract firmware/bose/minnow_3.0.3/Minnow_3.0.3_stack_plus_app.dfu firmware/bose/extracted/
   ```
   This writes each internal file under `firmware/bose/extracted/fs_<offset>/` (the directory name is the byte offset inside the DFU where that filesystem was found — it varies by firmware build, which is why it isn't hardcoded). Find the one that contains `vm.app` and `data_us` (the internal, not the external/language, filesystem) and either rename it or copy its contents to `firmware/bose/extracted/internal_fs/` — the path `caveguard.py`, `cavesim.py`, and `preflight.py` expect. None of these extracted files are shipped in this repository, only the public stock file they come from.
4. **The CSR/Qualcomm ADK toolchain** (`docs/toolchain.md`): the DSP assembler/linker/packer and the vendor's own filesystem-build tool. This is vendor tooling this repository cannot redistribute; see `docs/toolchain.md` for exactly which pieces are used and why two ADK versions are needed, and `build/dsp/gen.link.README.md` for the one small linker-script change the DSP generator build needs. The exact command line for turning `build/dsp/noisegen.asm` into the binary `build/dsp/compact.py` consumes (`kas` with `gen.link`, then `klink`, then `kobjcopy -O binary`) is recorded in `tools/README.md`'s entry for `build/dsp/compact.py`.
5. **No device-specific or unit-specific value is needed anywhere in the build.** No serial number, no Bluetooth link key, no per-device configuration key, and no private signing key. The build uses only the generic stock firmware (the same download anyone with this product can get) and the generic edit list in this repository. The signed-filesystem step does not need Bose's private key or any per-unit secret — see `docs/dfu-signature-scheme.md` for why: the technique edits only byte ranges the device's own verification never reads, so the stock image's own original signature stays valid unchanged.

**Verify your own rebuild** of the first release's product (probe380) by comparing
```
sha256sum build/hook/probe380_brown.dfu
```
against
```
25690ba49684a62781a8d2bdcf9db8386589f15d9fbd42fa4f8ed6b9c2b67c4a
```
A match means your rebuild is bit-for-bit the same image this project actually flashed and read back from its own speaker.

## The one real friction point

The CSR/Qualcomm ADK and its binary toolchain (the DSP assembler/linker, the vendor's own firmware-packing tool, and their supporting libraries) is specialized vendor tooling, and it is **not a simple public download**: a separate, fully isolated reproduction attempt (a fresh clone of this repository, no access to any of the original project's own files, using only this repo and the public internet) specifically researched this and found Qualcomm's self-serve developer portal does not surface it for this chip family, that it is described as gated behind a BlueLab developer license agreement, and that the only places it was found to surface publicly were informal file-sharing (a forum offer to privately share a copy, a possibly-paywalled third-party site) — not a legitimate distribution channel, and not something this project used, recommends, or depended on to reach its own result. **If you don't already have ADK access through an existing CSR8670/BlueCore vendor relationship, treat step 4 below as the one part of this path you likely cannot complete**, and use `build/patches/` instead (steps 1-3 below are identical either way, and that isolated test confirmed they work exactly as documented).

## What this test did not cover

- **Flashing a second, independent unit.** This test rebuilds the image offline and compares hashes; it does not exercise the physical flashing procedure on hardware other than the project's own unit, which this test did not cover (the finished product was separately flashed and read back on four units).
- **Every rollback image.** Only the first release's DSP-generator product (probe380) was rebuilt this way; the current product, probe427, is built the same way from `build/dsp/noisegen425.asm` with `build/hook/assemble_probe427.py` and should hash to `d3de3e67030c599f0ffa780bed0944c2b0521a422ee19a1421cd04adcc5919fc`; the earlier recorded-noise product (`docs/ring-buffer-fix.md`) was not separately re-verified by this specific test, though it uses the same signed-filesystem mechanism.

## The follow-up isolated test

A second attempt deliberately started with nothing but a fresh clone of this public repository (no local files from the original project at all) plus the public internet, specifically to check whether an actual stranger could do this, not just whether the original author's own machine could. It independently found the exact same stock-firmware download URL pattern, confirmed the same sha256, ran the extraction step exactly as documented, and then stopped at the DSP-binary build step for lack of the vendor ADK — exactly where the first test's own hedge said a reader might. That dependency's real-world availability is now the finding written into "the one real friction point" above, and is the reason `build/patches/` exists.

## No violations

This test used no USB or device access, opened no private data, and made no changes to this repository's own files — it ran entirely in an isolated working copy, with the one downloaded file kept in its own directory, separate from the build's working directory, per the general safety practice for untrusted downloads.
