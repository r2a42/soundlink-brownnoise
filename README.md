# Brown noise, on your own Bose SoundLink Micro, by software only

> **Independent hobby project.** Not affiliated with, endorsed by, or supported by Bose or Qualcomm. Flashing a modified firmware voids any warranty and can permanently destroy the speaker (this project lost one unit that way; see below).

**The goal of this repository is for you to be able to build your own brown-noise machine out of your own Bose SoundLink Micro speaker** — no soldering, no opening the case, no hardware modification of any kind. Everything here is a *software* patch delivered the same way Bose's own firmware updates are: over USB, through the speaker's own update mechanism.

Press and hold the centre (voice-assistant) button: instead of calling the phone assistant, the speaker plays loud, sustained brown noise until you press it again. That is the design, and it is what the cave code does on every button event this project can see. **The long press by hand and a physical power-off while the noise plays have been tested on a real unit** (see "what's not yet confirmed," below, for the gaps that remain).

This started as one person's project to stop buying a $30 white-noise machine and use a speaker already on hand instead. It took about a month and more than 400 experimental firmware builds ("probes") to get there, and the repository keeps the research trail, not just the result, because the trail is the part most worth reusing on a different device.

## Is this for you?

If you own one of these speakers and are comfortable following a precise, somewhat fussy procedure with a USB cable, yes. If a step feels risky or unclear, stop and re-read — the gates exist because skipping them cost this project's first unit permanently (see "the risk," below).

If you have a *different* CSR8670/BlueCore ("gordon")-based Bluetooth speaker, most of the technique generalizes (see `docs/dsp-generator-route.md` section 8 and `docs/ring-buffer-fix.md` section 8) but the specific addresses in this repository are for this exact product and firmware version and will not apply as-is.

## The risk, stated plainly

Flashing firmware can **permanently brick the speaker**. This project lost its first unit this way, after skipping its own verification steps under time pressure (`docs/POST-MORTEM-2026-10-04.md`). The gates in `docs/FLASH-PROTOCOL.md` — flash in the foreground, read every line of output, verify the device reports success, read the whole image back and compare it byte-for-byte before doing anything else — exist because of that loss, and no unit has been lost since (though the one remaining unit has wedged and needed the documented recovery procedure more than once — `docs/FLASH-PROTOCOL.md` "Recovery" is not hypothetical). **Follow the gates exactly, every time, with no exceptions**, and keep the stock firmware download on hand so you can always recover to a known-good state.

This also uses a documented gap in the device's own firmware-signature check (below) rather than any cryptographic weakness or private key. It only lets you edit specific byte ranges of a filesystem the device has *already* validly signed (such as the official firmware download) — it cannot forge a signature for arbitrary new content, and the technique only ever starts from Bose's own signed image.

## What's here, in two parts

### Part 1 — the current method: a noise generator running inside the speaker's own DSP

The speaker has a second, smaller processor (a Kalimba DSP) dedicated to audio. Rather than storing a recorded noise sample and playing it back, the current version writes a small noise-generating routine (a 67-word chain of digital filters, `build/dsp/noisegen425.asm`) directly into that DSP's own running program memory and hooks it into its audio timer — so the DSP makes the noise itself, continuously, with no loop to ever notice, no stored audio file, and nothing added to the signed filesystem beyond a tiny hook. One flash, starting from an unmodified stock firmware download, installs it (`probe427`, release v0.2.0).

**How it sounds, and how that was decided.** The sound was tuned by ear against the author's own direct recording of the brown-noise source, in several rounds of "draw the target curve, approve it, flash it, listen"; the verdict on the final one was "perfect". Recordings made through the speaker with a laptop microphone array turned out to be a poor target (the array's noise suppression moves the bass by 5-7 dB between sessions). The whole story, including the target curve and the lessons, is in `docs/ear-tuned-eq.md`.

**Volume.** The volume ladder has 12 levels. The top level is about 4.6 dB lower than in the first release, because the old top was judged about 4.5 dB too loud and started to distort. The generator applies no output clamp (`build/dsp/noisegen425.asm`), and this speaker can still get loud and harsh enough to be uncomfortable — a design error in an earlier, unrelated probe once produced sustained "very loud harsh noise" that needed several button presses and a few USB unplug/replug cycles to stop (`docs/PROBE-CATALOG.md`, probe173). **Start at a low volume step, well away from your head, the first time you try it**, the same way you would with any new audio source.

**Behaviour tested by hand on a physical unit:** long press starts the noise; the physical power button powers it off while the noise plays, and a power-on right afterwards behaves like stock (this was a bug in the first release: the cave kept the audio path marked busy for 16 s after power-off, which delayed the stock power-on announcement, and an early power-on looked like nothing happened); a 5-minute run and an overnight run went well. Lights are intentionally darkened while the noise plays, and the stock idle power-off behaviour is restored once the noise is stopped. Read `docs/dsp-generator-route.md` for how the generator works and `docs/CURRENT-STATE.md` for what each result rests on.

**What's not yet confirmed (`docs/CURRENT-STATE.md` section 4):** a phone *connecting* (as opposed to disconnecting) while the noise is already playing; idle power-off and the lights after that case; multi-hour recorded soak; and the loop and writer images of Part 2 on a second unit; and a first flash onto a factory-fresh unit through `tools/install_from_stock.py` (the author's flashes were done with `tools/flash_probe.py` on units already running earlier probes). None of these are known problems — they're simply untested, which is a different thing from verified, and you may be the first person testing them.

### Part 2 — the earlier method: a recorded, looped noise file through the stock tone path

Before the DSP generator, this project reached the same goal a different way: encoding a brown-noise recording as ADPCM, writing it into the one writable slot a locked speaker's filesystem format allows for streamable audio (normally used for voice prompts), and playing it on a loop through the speaker's existing tone-mixing path — the same mechanism it already uses for "connected," "battery low," and other spoken prompts. This needed two firmware flashes rather than one: a one-time "writer" image that erases and rewrites the speaker's second flash partition at runtime to stage the payload (by this project's own risk assessment, the single highest-risk operation here — its failure mode is not a recoverable wedge but an unrecoverable brick, see `docs/partition-route.md`), and the looping "product" image that plays it. It also hit an audible-clicks problem at full quality that turned out to be a DSP ring-buffer size limit, fixed by three data writes that enlarge the buffer.

Both the *method* (streaming your own audio content into a signed, locked device's DSP mix, with no DSP code of your own) and the *ring-buffer fix* (which the DSP-generator route reuses) are complete and independently useful; read `docs/ring-buffer-fix.md`.

## How the signed-firmware check doesn't stop custom content

Bose signs the speaker's filesystem (1024-bit RSA, no padding) over a hash that, as implemented, only reads the first 34 bytes of every 64-byte chunk of content — the other 30 bytes of every 64 never enter the signature at all. A second, separate checksum also has to be kept consistent, which this project's tooling (`tools/fsedit.py`) automates by finding compensating edits with simple linear algebra. The result: roughly 45% of the bytes of an *already officially signed* filesystem can be changed freely, and the device still accepts it as validly signed — because, from the device's point of view, nothing it actually checks has changed. No private key, no forged signature, and no broken cryptography is involved. Full derivation: `docs/dfu-signature-scheme.md`; plain-language summary: `docs/topics/dfu-and-signing.md`.

## Reproducing this yourself

There are two ways to get from the stock firmware download to the exact image this project flashed, and both are independently verified to produce the identical, hash-checked result. No device-specific secret (serial number, Bluetooth key, or private signing key) is needed in either one; everything here was derived from, and works against, the publicly downloadable stock firmware.

**The easy way — no vendor toolchain needed.** `build/patches/` ships the literal, already-computed byte-level difference between the official stock firmware and the built image (a `.patch.json` file: a sparse list of byte offsets and new values — this project's own content only, never storing the original bytes it replaces (the whole-file hash check below is what guarantees the input is correct before any edit runs, not a per-edit copy of the old value)). `build/patches/apply_patch.py` is a small, dependency-free Python script that verifies your downloaded stock file is byte-identical to the one this patch was built against, applies the patch, and verifies the result's hash before writing it — refusing to proceed at every step if anything doesn't match exactly:

```
python build/patches/apply_patch.py build/patches/probe427_product_from_stock_3.0.3.6546.patch.json STOCK.dfu build/hook/probe427_brown.dfu
```

`build/patches/` ships one patch for the current (single-flash, DSP-generator) product, `probe427`, and two for the older (two-flash, recorded-noise) route of Part 2: the writer `probe393` and the loop product `probe428` (tested by the author on one unit; a summary verdict, no per-case log was kept). The earlier loop `probe387` is no longer shipped: it has the power-on-after-power-off delay of up to 16 s that `probe428` fixes. Run the same script once per patch, to separate output files. The first release's patches (`probe380`, `probe346`, `probe367`) are in `build/patches/superseded/`. **`probe393`, the writer, performs a runtime write to the speaker's second flash partition — this project's own single highest-risk operation, whose failure mode is an unrecoverable brick, not a recoverable wedge (see "the risk," above, and `docs/partition-route.md`).** The single-flash `probe427` path above does not have this risk; prefer it unless you specifically want to reproduce the older route:

```
python build/patches/apply_patch.py build/patches/probe393_writer_from_stock_3.0.3.6546.patch.json STOCK.dfu build/hook/probe393_brown.dfu
python build/patches/apply_patch.py build/patches/probe428_loop_from_stock_3.0.3.6546.patch.json STOCK.dfu build/hook/probe428_brown.dfu
```

Flash `build/hook/probe393_brown.dfu` first and wait for it to report a successful write; only then flash `build/hook/probe428_brown.dfu` — see `docs/ring-buffer-fix.md` section 9. Same stock file, same script, same per-step hash verification, for every patch. `build/patches/make_patch.py` builds a patch from your own rebuilt image.

This cannot produce any image other than the one it already describes — it's a fixed replay of a result this project already built, flashed, and read back from its own speaker, not a general-purpose tool. If you just want the result, this is the path; a fresh, from-scratch clone-and-rebuild of this repository (no local files from the original project, nothing but this repo and the public internet) confirmed the stock-firmware download and this replay step both work exactly as documented, including refusing cleanly on a corrupted or wrong input file.

A patch produced this way is ready to flash directly with `bose-dfu` by hand per `docs/FLASH-PROTOCOL.md`. If you instead want to use this project's own `tools/flash_probe.py`/`tools/install_from_stock.py` (which run the full gate sequence, including a byte-exact readback comparison, for you), those also need the matching `_words.json` file for each probe (already included in `build/hook/`) and the extracted stock firmware tree from `docs/clean-room-rebuild.md` step 3 — both are needed regardless of which path produced the `.dfu`.

**The full way — rebuild from source.** (Only the DSP product, probe427, can be rebuilt this way. The writer probe393 and the loop probe428 carry a noise sample that is not part of this export, so the shipped patches are the only route to them.) `docs/clean-room-rebuild.md` documents rebuilding the first release's DSP generator (probe380) and its signed edit list from scratch. The current product, probe427, is built the same way from `build/dsp/noisegen425.asm` with `build/hook/assemble_probe427.py`; use that to verify independently, or to change anything. This needs the CSR/Qualcomm ADK (`docs/toolchain.md`) — and the same from-scratch test found that this specific piece is **not** a simple public download: it's gated behind a Qualcomm/CSR vendor developer-license agreement, and the only avenues that turned up for getting it without one were informal file-sharing, which this project neither used nor recommends. If you already have ADK access (an existing CSR8670/BlueCore developer relationship), this path works end-to-end and is fully documented; if you don't, the patch above gets you the same verified result without it.

A copy of the physical speaker is needed either way, obviously, and patience with `docs/FLASH-PROTOCOL.md`.

## Requirements

`build/patches/apply_patch.py` needs nothing but Python 3 and its standard library — that's the whole point of it. Going further than that (the full rebuild, measurement, or disassembly tooling) needs a Windows machine and, depending on the tool, `numpy`/`scipy` (measurement and signal analysis), `hid` (talking to the speaker's HID interfaces directly), or `faster-whisper` (decoding spoken diagnostic output from a microphone recording) — there is no single `requirements.txt` because most readers will only ever need the first sentence of this paragraph. Check a given tool's own docstring or `tools/README.md` before assuming you need any of the rest.

## Repository layout

- `docs/` — the full technical reference this project accumulated: firmware architecture, the signed-DFU mechanism, the audio/DSP path, the flashing protocol and its gates, a catalog of the more than 400 experimental builds, and topic guides that index all of it. **Only a handful of these were rewritten for an outside reader**: this README, `docs/CURRENT-STATE.md`, `docs/dsp-generator-route.md`, `docs/ring-buffer-fix.md`, `docs/clean-room-rebuild.md`, `docs/dfu-signature-scheme.md`, `docs/topics/dfu-and-signing.md`, `docs/FLASH-PROTOCOL.md`, and `docs/toolchain.md` — start there. The rest (`docs/FACTS.md`, `docs/GLOSSARY.md`, `docs/PROBE-CATALOG.md`, `docs/BIG-PICTURE.md`, the remaining topic hubs, and everything under `docs/deep/`) is the project's own internal research record, carried over largely as-is: it refers to "the owner" (this project's author), cites AI coding-assistant sessions and consultants by name, and links into some internal process files and a lab notebook (`docs/field-log.md`) that aren't included in this export. Files marked archival say so at the top; where one isn't marked but a link doesn't resolve, that's why.
- `tools/` — the Python tooling: the firmware-patch assembler and simulator (`caveasm.py`, `cavesim*.py`), the signed-filesystem editor (`fsedit.py`) and its supporting DFU/filesystem parsers (`tools/csr/`), DSP and VM disassemblers (`kapdisasm.py`, `xapvm/`, `disasm.py`), and the measurement scripts used to verify results (`tools/measure/`).
- `build/dsp/` — the DSP noise generator's source (`noisegen.asm`) and the linker/packing scripts for it.
- `fw/` — an earlier, abandoned route (a from-scratch firmware replacement needing a hardware SPI burn, never attempted), kept only because the current generator reuses its noise arithmetic.
- `build/patches/` — the no-ADK-needed route: verified byte-diff patches from the official stock firmware to each product, and the script that applies and verifies them.
- `build/hook/`, `build/extfs/` — the application-CPU patch ("cave") assemblers for the experimental builds referenced throughout the docs, kept as a record of the project's actual history and as worked examples of the technique. `build/hook/` also holds many one-off sweep and debug scripts. Like most of `docs/` above, their docstrings are an unedited lab record, not rewritten for an outside reader. Two scripts in `build/extfs/` (`index_sniff.py`, `index_proxy.py`) temporarily change your Windows per-user proxy setting (no admin rights needed, and each restores it) to observe Bose's own updater traffic — read their docstrings before running either one; nothing else here changes anything outside this repository or the speaker.

## Scope and intent

This is interoperability and personal-device research: modifying firmware on a speaker you own, for your own use, using only publicly available firmware and tools this project wrote itself. It does not forge any signature, use or expose any private key, or depend on a broken cryptographic primitive (see "How the signed-firmware check doesn't stop custom content," above) — the technique works because of a documented gap in an already-public verification process, applied only to a filesystem Bose has already validly signed. Nothing here was built to work against a device you don't own, and nothing here was disclosed to or coordinated with Bose before publication; treat it accordingly.

Separately, some development and testing tools here (`tools/csr/virtual_press.py`, `tools/csr/tap_sweep.py`) talk to a diagnostic/test console Bose already built into every unit's stock firmware — this project didn't create, add, or modify that interface in any way; it's a USB client sending commands to something that was already there, and it works identically against a completely unflashed speaker. Figuring out how to address it (the unlock-code formula, the command map) came from reading the firmware's own disassembly, the same way everything else in this repository's analysis did.

## License and third-party material

This project's own code and writing are licensed under Apache License 2.0 (`LICENSE`). See `NOTICE` for third-party components and what is deliberately *not* included (Bose's firmware and the vendor ADK toolchain — neither of which this project has the right to redistribute).

This repository does not include any Bose firmware image, any device readback, or any personal device identifier (serial number, Bluetooth address, or similar). Everything here was derived from, and operates on, the publicly downloadable official firmware for this product.
