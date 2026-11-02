# Release notes

## v0.2.1 (2026-11-02)

Shipped patches are now exactly three: `probe393` (writer), `probe427` (the single-flash DSP product, nickname "Brownie") and `probe428` (the loop product with the power-off fix). Changes since v0.2.0:

- The `probe387` loop patch is removed: it keeps a power-on delay of up to 16 s after a power-off that `probe428` fixes. (The v0.2.0 tag still contains it.)
- `probe428` was tested by the author on one unit (a summary verdict; no per-case log was kept) and is no longer described as offline-only. Not tested: a phone connecting while the noise plays, and the loop and writer on a second unit.
- `probe427` was flashed and read back on four units.
- `tools/install_from_stock.py --two-image` now defaults to the loop `probe428`.
- Documentation fixes: README disclaimer, patch output paths, stale references to the superseded patches, clean-room note (it rebuilds the first release's probe380), probe catalog rows for 393 and 428.

## v0.2.0 (2026-10-31)

Three changes to the product, new patches for the older recorded-noise route, and a patch generator. All patches apply to the official stock firmware `Minnow_3.0.3_stack_plus_app.dfu` (sha256 `5ae3bc9655af1b80eb78ebe3610eb58473edd715c885f8cdffc3f1b66be4659e`, firmware 3.0.3.6546) with `build/patches/apply_patch.py`.

### Patches

| file (`build/patches/`) | image | output sha256 | status |
|---|---|---|---|
| `probe427_product_from_stock_3.0.3.6546.patch.json` | probe427, the DSP-generator product | `d3de3e67030c599f0ffa780bed0944c2b0521a422ee19a1421cd04adcc5919fc` | flashed and read back on four units; sound, volume and power-off tested by hand on one |
| `probe393_writer_from_stock_3.0.3.6546.patch.json` | probe393, the payload writer (partition-2 write, highest risk) | `3cc7bc9228048d58783f6b5783776e69212a4baff1010b359080529ce0be6593` | real writes verified on one unit with the loop product |
| `probe428_loop_from_stock_3.0.3.6546.patch.json` | probe428, probe387 plus PWRREL2 | `327a1bc579cc422459f37293b7316e9dbf723c88f1cadc9fdf2a1f9719fc7013` | hardware-tested on unit 2 by the owner (full press plan, owner's word; no per-case detail recorded); fixes the 16 s power-on delay after a power-off; see `docs/deep/probe428-loop-2026-10-31.md` |

`apply_patch.py` prints "matches the recorded, verified image" for every patch whose output hash matches the one in the patch file. That check proves the bytes are the ones the build produced; it is not itself a test on a speaker (probe428's hardware test is noted in the table above).

### What changed in the product (probe380 to probe427)

1. **Sound.** A new 67-word generator (`build/dsp/noisegen425.asm`) tuned by ear to a direct recording of the source (`docs/ear-tuned-eq.md`).
2. **Volume.** The ladder is capped at 12 levels; the top is about 4.6 dB lower than before. The old top was judged about 4.5 dB too loud and starting to distort. The default level is 6.
3. **Power-off with noise playing (PWRREL).** Fixed a bug: after powering off while the noise played, a power-on within about 16 s looked like nothing happened (the next press then powered it off again). The cave held the audio path "busy" for 16 s after power-off, and the stock firmware delays all prompts, including the power-on announcement, while it is set. The cave now releases the hold on the power-off event itself.
4. Connected-device start fix (STARTWAIT, SILENTDROP, NOREWR), from the first export's follow-up work: when a phone or laptop is connected, a long press no longer collides with the stock spelled-name prompt.

### The loop images

- **Writer: probe346 replaced by probe393.** The writer now mutes stock prompts from the first boot event, drops Bluetooth at its tick and guards before the present-check, so the partition-2 write runs the same with or without a connected device. Without these, a staged payload broke the stock spelled-name prompt and the output stayed muted with a device connected.
- **Loop: probe367 replaced by probe428.** It carries the connected-device start fix and PWRREL2, a power-off release that is safe for the loop: the loop's 16 s hold exists so the stock does not start its power-on speech while a payload transform still holds the DSP, so the release is made only when no transform is running (`docs/deep/probe428-loop-2026-10-31.md`). The intermediate loop probe387 is no longer shipped.
- The volume cap was **not** applied to the loop: the loop's default level is 10 and its top is already about as loud as the generator's accepted level 11; capping it at 12 levels would leave one step above the default.

### Tooling

- New `build/patches/make_patch.py`: builds a patch from a stock file and an image, and checks its own output. It reproduces the first release's probe380 patch exactly.
- `tools/install_from_stock.py` defaults: product probe427, writer probe393, loop probe428.
- `build/hook/ladder_core.py` and `build/hook/ladder_ext.py` updated; every older image still rebuilds identically (the new behaviour is behind opt-in flags).

### Known limits

- `tools/flash_probe.py` handles one unit per `build/hook/FLASHED` and overwrites `<probe>_readback.dfu`; copy readbacks away between units.
- `tools/framecheck.py` reports two findings on probe427 that are a false attribution (`docs/CURRENT-STATE.md` section 4).
- Untested: a phone connecting while the noise plays; the loop and writer on a second unit; probe428 on a second unit.

## v0.1.0 (2026-10-29)

The first export: the probe380 DSP-generator product and the probe346 writer and probe367 loop of the older route (now under `build/patches/superseded/`).
