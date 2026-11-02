# Flash protocol — mandatory, from 2026-10-04

> **2026-10-28 addendum (the gates below are unchanged):** to return to official firmware use the manual sequence with `firmware/bose/minnow_3.0.3/Minnow_3.0.3_stack_plus_app.dfu` (steps: list, info -f, enter-dfu, poll 4022 by elapsed time, download --force with the 45.867 s manifest wait, leave-dfu -f, poll 40fe, info -f, write `build/hook/FLASHED` as STOCK, `tools/csr/dfu_upload.py` readback, 0 of 975,168 filesystem bytes must differ); the stock image does not touch partition 2. The lean product installs from stock with one `tools/flash_probe.py probe427`. After any console event read the 40fe node's LastArrivalDate (a reset moves it).

Written after a unit was lost to eleven unverified flashes (and nine presses) in one
92-minute session. See `docs/POST-MORTEM-2026-10-04.md`. These are gates, not
guidance: if a step cannot be completed, **the next flash does not happen**.

## The loop, per probe. No step is optional.

### 1. Build and verify offline

    python build/hook/assemble_probeNNN.py            # expect "decode-verify: all branches OK"
    python tools/cavesim.py probe90                   # the CONTROL, every time; expect AL = 0x0E
    python tools/cavesim.py probeNNN --entry 0x... [--ah EVENT]
    # exercise EVERY path, including each --fail bail, and confirm the spoken id of each
    python build/hook/assemble_probeNNN.py --build
    python tools/preflight.py probeNNN                # verifies the FILE, not the device

**`preflight.py` is not a readback.** It proves the built image contains what the
assembler intended. It never touches the speaker. Do not let it stand in for step 4.

### 1b. The cave must stay inside the proven const window

    python tools/caveguard.py probeNNN      # also run automatically by preflight

**Every cave word must lie inside `0x3E200..0x3E400`**, the ~197-word region about forty
flashes have written without incident. Being zero in the official image and inside a DFU
blind window is **not sufficient**: probe130 satisfied both and crashed the speaker on
boot, because 55 of its words sat in zero gaps **inside live tables**. *Zero does not mean
unread.* If a design does not fit 197 words, shrink the design — do not widen the window.

### 2. Stack headroom, if the hook is new

    python tools/stackdepth.py                        # declared stack size
    # then measure the deepest static path TO THIS HOOK SITE, not to a different one

Any cave with a frame larger than `enterl -8` at an unmeasured site is forbidden. probe127
used `enterl -16` three frames deep (`fn_00846` `-23` → `fn_189fb` `-8` → cave) on a
headroom figure measured at a shallower site weeks earlier.

### 3. Flash in the FOREGROUND, reading every line

Each line has an expected output. **If any line does not produce it, stop.** Do not run
the next line.

    ./tools/bose-dfu/bose-dfu.exe enter-dfu
    #   expect: "Note that device may take a few seconds to change mode"

    ./tools/bose-dfu/bose-dfu.exe list                  # POLL -- but see the warning below
    #   expect: a line containing 4022. Re-run until it appears. NEVER a fixed `sleep`.

**Count elapsed time, not iterations.** On 2026-10-05 a 12-iteration poll loop ran through all
twelve `list` calls in about a second -- far faster than the mode change -- and reported
`40fe` every time. The `enter-dfu` had in fact worked; the loop was simply faster than the
device. Stopping there was correct (never run `download` into a device still in normal mode),
but the right fix is a loop that keeps polling for **tens of seconds**, not one that gives up
after N fast iterations. A second `enter-dfu` is also NOT a safe retry: it errors with
"to use an untested or ambiguous-mode device, you must pass -f" once the device has already
begun switching, which is easy to misread as a failure to enter DFU.

    ./tools/bose-dfu/bose-dfu.exe download --force build/hook/probeNNN_brown.dfu
    #   expect: "Waiting NN.NNNs, as requested by device, for firmware to manifest"
    #   (45.867 s on 2026-10-02). This line is the positive signal that the write
    #   completed. No line = no confirmed write = stop.

    ./tools/bose-dfu/bose-dfu.exe leave-dfu -f
    #   FAIL if the output contains errFIRMWARE (or any errXXX). Quote the output.

    ./tools/bose-dfu/bose-dfu.exe list                  # POLL, up to ~25 tries
    #   expect: a line containing 40fe

    ./tools/bose-dfu/bose-dfu.exe info -f               # liveness: NOT `list`
    #   expect: "Current firmware: Main 3.0.3.6546"

**Then, before anything else, update `build/hook/FLASHED`**: `probe=`, `image=`,
`flashed=` with the time, and `verified=PENDING`. It is filled in at step 4. On 2026-10-04
this file said probe114 through eleven flashes and the loss of the unit; `tools/docaudit.py`
checks the docs against it, so a stale `FLASHED` makes the audit enforce falsehoods.

**Forbidden:** `run_in_background`, redirecting any step to `/dev/null`, a fixed `sleep` in
place of polling for the PID, a `timeout` under 600 s on `download`, or judging success
from an exit code. `-f` is required on `download` and `leave-dfu` for this device
("untested or ambiguous-mode device").

#### The last cycle that worked, and the fatal one, side by side

Both from the session transcript, and **the same image** — probe114:

| step | 2026-10-02 15:09, cycle 95: worked | 2026-10-04 19:32: the fatal session |
|---|---|---|
| wait for DFU | polled `list` until `4022` | `sleep 5` |
| `download` | output read: *"Waiting 45.867s ... for firmware to manifest"* | `>/dev/null` |
| `leave-dfu` | `case "$out" in *errFIRMWARE*) echo "!!! errFIRMWARE"` | `>/dev/null` |
| liveness | polled `list` for `40fe`, then `info` → *"Main 3.0.3.6546"* | `list`, `info` |
| readback | `timeout 900 python .../dfu_upload.py`, foreground | **none** |
| result | *"filesystem: 0 of 974538 bytes differ / cave words on the device: 154 of 154 correct / redirect at 0x107be: 0300 da00 5d9c"* | — |
| `FLASHED` | updated | **never updated** |
| how it ran | foreground | **`run_in_background`** |

Every row where they differ is a rule above.

### 4. READ THE IMAGE BACK OFF THE DEVICE. No exceptions.

    python tools/csr/dfu_upload.py build/hook/probeNNN_readback.dfu

**In-tree since 2026-10-04** — it used to live only in a separate tooling directory, and looking
for it at a guessed path is how step 4 came to be skipped. One positional argument, the
output file. It enters DFU itself if the device is in normal mode (PID `0x40fe` → `0x4022`)
and always tries to leave DFU on the way out, including on error.

Then compare against the flashed image and require:

- **0 of 975,168 filesystem bytes differ**, and
- **all N cave words present** at their own addresses.

**The comparison, exactly.** A readback is *not* the same length as the flashed file
(1,760,580 vs 1,761,440) and `fsr_dfu1` sits at a different offset in each
(`0xbfc00` vs `0xbff4c`), so a plain `cmp` is meaningless. Align on the marker in **both**
files and compare the 975,168-byte filesystem area:

```python
import json
FS, AREA0 = 975168, 0x6EA30
rb = open('build/hook/probeNNN_readback.dfu', 'rb').read()
fl = open('build/hook/probeNNN_brown.dfu', 'rb').read()
ir, ifl = rb.find(b'fsr_dfu1'), fl.find(b'fsr_dfu1')
d = sum(1 for i in range(FS) if rb[ir + i] != fl[ifl + i])
print('%d of %d filesystem bytes differ' % (d, FS))
bad = [k for k, v in json.load(open('build/hook/probeNNN_words.json')).items()
       if (rb[ir + AREA0 + 2 * int(k, 16)] |
           rb[ir + AREA0 + 2 * int(k, 16) + 1] << 8) != (v & 0xffff)]
print('cave words: %d total, %d wrong' % (len(json.load(
    open('build/hook/probeNNN_words.json'))), len(bad)))
```

Validated 2026-10-04 against the surviving `probe77_readback.dfu` / `probe77_brown.dfu`
pair, which reproduces that probe's recorded field line exactly: **0 of 975168 filesystem
bytes differ, 70 cave words, 0 wrong**. It also confirms the build is reproducible — a
probe77 rebuilt on 2026-10-04 is byte-identical in the fs area to the image read off the
device on 2026-09-30.

The vendor's own BlueSuite backup tool (`HidDfuCmd backup`, part of the BlueSuite toolkit
mentioned in `docs/toolchain.md`, not included in this export) does **not** work as a
readback path here — it fails at 0% with *"Device reports DFU length of zero"*. Use
`tools/csr/dfu_upload.py` above instead; it is this project's own, proven readback path.

Run the readback **in the foreground with `timeout 900`**, as the last working cycle did.
Then set `verified=` in `build/hook/FLASHED` to the two numbers, verbatim. (The 2026-10-02
cycle compared extracted filesystem files via `tools/csrdfu.py extract` and printed
**974,538**; the marker-aligned recipe above compares the whole area and prints
**975,168**, as 37 earlier verifications in the field log do. Either is valid; record which.)

**If readback fails or is unavailable, stop. Fix the readback path before flashing again.**
This is the step whose absence cost the first unit: it is the only check that detects a
partially-written image, and 35 prior cycles in the field log all performed it.

### 5. One press, conditions written down first

State before the press: what is connected, what is playing, which button, which gesture,
and the full outcome table with a **distinct** spoken id for every path **including
success**. No id may collide with a stock prompt used in that state — `0x09` "mobile device
not found" and `0x00` "ready to connect" are both things the speaker says by itself.

### 6. Record the result, then stop

Write the outcome — negatives included — into a log file of your own (this project's own
log, `docs/field-log.md`, is its append-only lab notebook and is not included in this
export; start your own, e.g. a local `field-log.md` you keep for your own unit) before
building anything else. **One flash, one press, one recorded result.** No queueing
probes, no "while that lands". Do not commit a log that quotes your unit's own serial or
other identifying output verbatim (see the note on `*_flash.log` in `.gitignore`).

## Safety rules for cave code

- **Never call a trap on an object whose state is unknown.** Prefer read-only
  interrogation. `fn_12e1a` on a *connected* sink memsets `size` words from data address 0,
  because `SinkMap`/`SinkClaim` return 0 rather than `0xffff` and its guard does not fire.
  Use `SinkSlack` to ask about space.
- **Never run a teardown against an object that may not exist.** probe121 crashed at
  power-on tearing down a port 3 that was not there, because the speaker auto-enters
  pairing with nothing connected and that fired the hook.
- **Prove hook reachability from the button, not from the local code.** `fn_1061b`
  dispatches on `@(8,Y)`: mode 1 → the jump table and `0x107be`, mode 2 → the `fn_105b2`
  lookup and `0x10823`. `0xAE0` additionally needs `fn_09157 != 0` and bit 7 of `@0x565`
  (the A2DP-streaming latch), and gate 1 requires the press to *mean* enter-pairing, which
  clears that latch — so it is structurally one-shot.
- **Guard for the wrong state.** `fn_0d475` returns `@0x59e` (`sinkState`); require
  `{3, 0x0d}` and a TRUE from `KalimbaSendMessage` before touching the audio path. They
  test different things, so check both.

## Recovery

**Corrected 2026-10-08, after probe158 wedged unit 2 and the procedure below did not
work.** Follow these in order; do not skip to the button combo.

1. **`bose-dfu list` first.** `40fe` means the device still enumerates in normal mode, and
   because `PSKEY_USB_VM_CONTROL = 1` makes the VM application drive enumeration, that means
   **the application is still running and USB recovery is possible.** Nothing enumerating at
   all is the serious case (see below).
2. **`bose-dfu info -f`, and one TAP verb (`python tools/csr/tap_sweep.py vr`).** These are
   two independent command channels. If either answers, the command layer is alive and
   `enter-dfu` will work normally — go to step 3 of the flash loop.
   On a wedge both fail: `info -f` returns the USB serial (that comes from the descriptor,
   not the app) and then "USB transaction error while reading info field", and the TAP verb
   stalls. That means USB is up but **no HID request is being serviced** — the message loop
   is stuck.
3. **`enter-dfu` will NOT work in that state**, and this is expected: it is a HID command the
   *application* must act on. One attempt is harmless; do not retry it (a second attempt
   errors with "untested or ambiguous-mode device").
4. **Do NOT rely on `POWER` + `VOICE-ASSISTANT` (centre) ~10 s.** This file used to present
   that as the wedge recovery and it **did not work** on 2026-10-08: the LED went out and
   nothing else happened — still `40fe`, still no HID. The one recorded success for that
   combo was recovery from **`errFIRMWARE`**, where the application was *not* running and the
   boot loader was; a wedged-but-running application is a different state, and if the combo
   is serviced by the application's own button handler then a stuck application cannot act on
   it either. It costs nothing to try, but do not stop here when it fails.
5. **What actually works: UNPLUG USB, hold POWER alone ~20 s, plug USB back in, press
   POWER.** While USB is attached the chip has power regardless of the battery, so a
   power-off cannot take effect — which is exactly why the combo appeared to do nothing. Off
   USB power the forced power-off lands and the speaker cold-boots.
6. **A cold boot comes up clean**, provided the cave gates on something boot-safe (every cave
   since probe142 gates on `KalimbaSendMessage(0x1072)`, which returns FALSE at power-on
   because no DSP is loaded, so the cave bails silently). **Flash stock immediately and press
   nothing** — the wedge needs a press with the DSP up, so the clean boot is your only
   guaranteed-safe window.
7. Last resort if the battery is charged and POWER will not force off: **let the battery go
   flat.** Slow, but it is an unconditional cold boot.

- **No USB at all:** `PSKEY_USB_VM_CONTROL = 1` on these units, so the VM application
  drives enumeration. A dead application means no USB, and no software recovery exists from
  the host. The only route is CSR's hardware **SPI** debug transport (vendor BlueSuite
  tools such as `BlueFlash.exe`/`nvscmd.exe`, not included in this export and not used
  anywhere else in this project), which needs opening the case and a USB-SPI dongle on the
  board's SPI pads — the one thing this entire project's software-only scope rules out.
  Avoiding this state is the whole point of step 4.

## What you need on disk before step 3

- `tools/bose-dfu/bose-dfu.exe` (obtain separately; see `NOTICE`).
- `build/hook/probeNNN_brown.dfu` and `build/hook/probeNNN_words.json` (built in step 1).
- The official stock firmware, if this is a recovery flash or your first flash from factory
  state (`docs/clean-room-rebuild.md` says where to get it and its expected hash).
- `build/hook/FLASHED` (a starter copy ships in this repository; the script creates one if
  it's somehow missing).

See also (gate 5, "a distinct spoken id for every outcome, success included"): whether a
looping product image can fully satisfy this gate the same way a single-shot probe can is
an open question this project never fully settled; the text of the gate stands as written
regardless.
