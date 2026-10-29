# Current state (2026-10-28): the lean DSP-generator product is on the speaker

Purpose: the one page to read first to know where the project stands today, what is installed, what was measured, what is still open and which older statements this page supersedes.
Status / last verified: 2026-10-28 (evening). Evidence for every line was originally in `docs/field-log.md`, the project's append-only lab notebook, which is not included in this public export (it is a dense internal log, not written for an outside reader); `build/hook/FLASHED` is the authority for what is on the speaker.
Read next: `docs/dsp-generator-route.md` (how the generator works), `docs/FLASH-PROTOCOL.md` (before any flash).
Marks: **proven** = a command output or recording quoted in the project's lab notebook; **well-supported**; **hypothesis**.

## 1. What is on the speaker (proven)

Unit 2 (the only speaker) runs **probe380** (`build/hook/probe380_brown.dfu`, built by `python build/hook/assemble_probe380.py --build`): the LEAN GENERATOR product. It was installed by ONE flash from official stock firmware 3.0.3.6546 (the stock image was flashed first and read back: 0 of 975,168 filesystem bytes differ; then probe380: 0 differ, all 2,116 cave words correct).

The brown noise is **generated inside the speaker's DSP**. A 45-word routine (`build/dsp/noisegen.asm`, assembled with the ADK tools, post-processed by `build/dsp/compact.py`) is written into the DSP's program memory through its PM window every time the noise starts, and hooked into the DSP's tone-copy timer. There is no recorded noise, no payload partition, no writer image and no loop seam. Details: `docs/dsp-generator-route.md`.

Behaviour (hands-free tests with the laptop microphone and the virtual long press `tools/csr/virtual_press.py press`):

| item | result |
|---|---|
| start | noise within about 1-2 s of the centre long press; no auto-start at boot |
| spectrum vs the approved 48 kHz recorded noise (probe367's own self-generated payload, `tools/brownnoise.py`, not a third-party recording; same mic, relative to 1 kHz) | within +-2.4 dB in every band 30 Hz - 8 kHz; level +1.1 dB |
| stability | 9 minutes: rms sd 0.0013; 0 glitch blocks (the recorded loop showed about 2,000 seam bursts) |
| OFF/ON | three cycles, cold and warm path, noise back within about 2 s |
| volume | 15 fine levels (1.5 dB steps, level 0 silent); four steps down = -7.8 dB, four up = back |
| resets | none in any session (USB LastArrivalDate unchanged) |
| install | stock -> probe380 in one flash; the stock prompts (voice data) are intact |

Also kept from the earlier product (probe367/358): lights dark at noise start until the next stock power-on (LEDDARK), stock idle power-off restored after OFF (TMREARM), stock link-lost/idle timers cancelled while the noise plays (TIMERS), Bluetooth off while the noise plays (SCAN/BTDROP), noise survives Bluetooth disconnects (ENSURE), 48 kHz DAC.

## 2. Rollback and other images

- probe367: the previous product (48 kHz recorded noise, tone ring enlarged to 512 samples by three DSP pokes). Needs the payload in partition 2 (this unit still holds it) or the writer probe346.
- probe358: the 32 kHz native recorded product (needs the writer probe354's payload).
- probe381: probe367 plus inert stubs in 17 more dead functions (batches C and D of the approved dead-function pool, added 2026-10-28). It only proves those functions are unused; probe380 uses them for code.
- Stock: `firmware/bose/minnow_3.0.3/Minnow_3.0.3_stack_plus_app.dfu`, flashed by the manual sequence of `docs/FLASH-PROTOCOL.md` (it does not touch partition 2).
- `python tools/install_from_stock.py probe380` (or with no argument at all, since `probe380` is the default) is the one-flash install (a real run from a factory-state unit has not been done on a second unit).

## 3. Open items (not yet tested)

A physical long press by hand (only the virtual/scripted long press has been tested); a phone connecting (as opposed to disconnecting) while the noise plays; stock prompts and a physical power-off while the noise plays (the USB-console "power off" key does not stop the noise, as on probe367); idle power-off specifically after the connect-while-playing case; the lights specifically after that case; an ear check of the 17 newly used dead functions (only an automated hands-free test was done); the first run on a second, factory-state unit.

## 4. Statements this page supersedes

- "Delivery of DSP code cannot come through the signed filesystem, the only route is a partition write" (`docs/dsp-noise-route.md`): the filesystem route is still closed, but the DSP's own program memory is writable at run time through its PM window (proven 2026-10-28), which needs no partition write.
- "PM cannot be written through POKE": refuted on hardware (probes 375-377).
- "The cave is full": still true for the recorded-noise product; the lean product frees about 300 words, and 17 more dead functions (batches C, D of the approved dead-function pool) were approved.

## 5. New rules learned

- Never send console events 0x4021 (BootSetMode 7: the speaker drops to USB 4005; only a USB replug cures it) or 0x4022 (loader mode). Safe test ids are the stock event switch's default arm (0x4015, 0x402C-0x402E, 0x4033, 0x4070-0x4077).
- After every console event read the 40fe node's `DEVPKEY_Device_LastArrivalDate`: a reset moves it; "still lists 40fe" proves nothing.
- Spoken data readouts carry a check digit (7th digit = sum of the six octal digits mod 8) and the decoder refuses silent slots.
- Keep offline gates short: one reduced world run (ON at 0 s, OFF at 12 s, horizon 20 s), not a full product-gate run.

## 6. Timeline of the eras leading here

2026-10-10 to 10-13 offline study and cave expansion; 10-13 to 10-17 recorded-noise material, DSP cold load, hands-free loop; 10-17 to 10-19 cold-start product, volume ladder, census; 10-20 to 10-24 payload writers, 24/48 kHz, fine ladder, click hunt; 10-25 to 10-27 free-edge/poll experiments, native 32 kHz payload, boot-start, light-dark, idle power-off; 2026-10-28 the DSP read/write census (probes 361-365), the 48 kHz ring fix (366-367, `docs/ring-buffer-fix.md`), the program-memory window (368-377), the lean generator (380, `docs/dsp-generator-route.md`), the stock reflash and the single flash. `docs/PROBE-CATALOG.md` section 13 summarises probes 182-381 by era; it cites the project's internal lab notebook (`docs/field-log.md`) for detail, which is not included in this export.
