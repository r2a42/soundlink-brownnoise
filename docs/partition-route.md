# The runtime partition write: not closed, not safe yet, and one probe decides it

> **Note on references (public export):** this file cites files from the original private research repository that are not included here; each such path is marked "(not in this export)" at its first mention, and all of them are listed in `docs/NOT-IN-EXPORT.md`. The claims they support are summarised in the text; the cited originals are not needed to rebuild or flash anything.

> **This is an archival research document from the original (larger, private) project repository.** Some of its internal links point at files not included in this public export; where one doesn't resolve, that's why. The repository's own current, self-contained write-ups are listed in README.md's "Repository layout" section.

> **2026-10-28 banner:** the partition-2 route (staged data_us bytes written to p2 by a writer image) delivered the recorded noise from probe318 to probe367 and is now RETIRED for the product (probe380 generates the noise in the DSP). Partition 2 factory content is the 12 language packs (FACTS F325); `docs/deep/material-2026-10-27/CV-restore-language-packs.md` (not in this export) studies restoring them. The run-time partition write itself (`StreamPartitionOverwriteSink`) is proven by probe140 and by the writers; the findings may be useful to other projects.

**2026-10-02.** This is the only route to **clean, infinite, refill-free brown noise with
no paired device** — write our own DSP app to flash at runtime and `KalimbaLoad` it. We
already have the app: `fw/build/csr8670/brown_noise_kalimba.kap` (not in this export), 4,094 bytes,
kalsim-verified at −5.9 dB/octave, never clips.

It is also the only route in this project whose failure mode is worse than a recoverable
wedge. **Verdict: no-go as a direct attempt; go for one write-free probe first.**

## CORRECTION: the partition map this project had was never grounded

Earlier analysis in this session asserted a three-partition layout — 0: 4,096,000 B
filesystem, 1: 307,200 B filesystem, 2: 2,048,000 B RAW_SERIAL — read from "a 64-octet
table inside `vm.app` at file byte 0x7A83E". **That does not hold up, and I checked it
myself rather than trusting either agent that disagreed about it:**

- The words at file byte `0x7A83E` are `0048 00b5 00f1 005f 0000 0000 0000 0003 …` —
  not a partition table.
- **None of the three sizes appears anywhere in `vm.app`** as a 32-bit word pair, in
  either byte order. Zero hits for 4,096,000, 307,200 and 2,048,000.
- A whole-image scan of `Partition*`/`StreamPartition*` call sites finds no
  partition-geometry table at all. On CSR8670 the map lives in the SQIF/curator config,
  not in the VM app, which is consistent with its absence.

**What the disassembly does prove:** the only partition the running firmware is ever seen
to touch is **partition 0**. Boot mounts it at `0x0a340`
(`PartitionMountFilesystem(SERIAL_FLASH, 0, LOWER_PRIORITY)`, guarded by
`BootGetMode != 2`); the diagnostic handler `fn_1192x` also uses 0; and Bose's DFU writer
takes its partition number *from the incoming DFU header* (`0x18809`) with one hardcoded
`StreamPartitionOverwriteSink(SERIAL_FLASH, 0)` at `0x18828`.

> So "partition 1 is unused" is **unverified**, and whether partition 1 even exists is
> unverified. I told the owner otherwise; that was wrong. Nothing has ever read this
> device's live flash layout.

## CORRECTION, 2026-10-06: partition **2** exists, and the app writes it

The paragraph above is superseded in one respect. "Nothing has ever read this device's
live flash layout" still stands — no `PartitionGetInfo` has ever run. But the claim that
**partition 0 is the only partition the firmware touches is wrong**, and the evidence was
sitting in `build/analysis/full-disasm.txt` (not in this export) the whole time.

`fn_187e7` (called from `0x186b1`) takes an **image-type code** as its argument and maps it
to a partition number before writing:

```
0x187f7  ld AL,@(0,Y) ; cmp AL,#1 ; beq  -> 0x187fd
0x187fa  ld AL,@(0,Y) ; cmp AL,#2 ; bne  -> 0x187ff
0x187fd  ld AL,#0                          type 1 or 2 -> partition 0
0x187ff  ld AL,@(0,Y) ; cmp AL,#4 ; bne  -> 0x18804
0x18802  ld AL,#2                          type 4      -> partition 2
0x18803  st AL,@(2,Y)
0x18804  ld AL,@(2,Y) ; cmp AL,#0xffff ; beq -> 0x18817    anything else: refuse
0x18807  ld AL,#1 ; ld AH,@(2,Y) ; bsr -> StreamPartitionOverwriteSink
```

`AL=1` is the device (`PARTITION_SERIAL_FLASH = 1`, `partition_if.h:32`) and `AH` is the
partition, confirmed against `fn_18819`'s hardcoded `ld AL,#1 ; ld AH,#0` for partition 0.

So the live map, read off Bose's own code rather than guessed:

| partition | written by | holds |
|---|---|---|
| 0 | image types 1 and 2 | the main filesystem (`vm.app`, the `.kap`s, `data_us`) |
| **2** | **image type 4** | **almost certainly the external language filesystem** |

The second row is an inference from the mapping plus elimination — type 4 is the only other
accepted type and the ext filesystem is the only other filesystem Bose ships — so it is
**not yet hardware-confirmed**. It is grounded in code, not in a size coincidence, which is
more than the retracted three-partition table ever had.

## The external filesystem is real, parses with our tools, and IS mounted

`firmware/bose/index.xml` (not in this export) lists a second image for device `0x4022` that this project had
only ever treated as dissection material:

```
IMAGE Minnow_3.0.3_ext_signed.xuv   SUBID=1  TARGET=1  LENGTH=16727488  CRC=0xEB198EC7
```

Measured 2026-10-06:

- CRC-32 of the **ASCII text** is `0xEB198EC7` and its length is `16727488` — both match
  `index.xml` exactly, so the `.xuv` text is the unit of HTTP transfer.
- Converted, it is **2,090,936 bytes** and begins `fsr_dfu1` — a **bare** read-only
  filesystem with no `CSR-dfu2` container, no stack, no PS areas. Header is the 8-byte id
  plus the 128-byte RSA signature; **there is no partition or target field in the file.**
- `tools/csr/dumpfs.py` walks it cleanly: 25 files, all foreign-language prompt data
  (`NowSpeakTTS/data_fr`, `tts/rphrases_ru`, …) plus an 11-byte `ext_version`. Nothing in it
  is needed to boot, and nothing in it is needed to work in English.
- **`vm.app` references its contents.** Searching the one-char-per-16-bit-word encoding
  (`docs/const-strings.md` (not in this export)) finds `ext_version` at `0x78a56`, plus `NowSpeakTTS`, `tts/`,
  `data_` and `rphrases`. The app reads this filesystem, so **the ext partition is mounted
  into the union filesystem.**

That last point retires **blocker #2** of this document. The cave does not have to author a
ROFS and mount it: Bose already mounts one, in a format `tools/csr/csrfspack.py` already
writes, holding files nothing depends on. `FileFind` searches the union, so a `.kap` placed
in the ext filesystem is visible to `KalimbaLoad` exactly like `sbc_decoder.kap`.

## But the delivery channel is NOT the boot loader

The obvious probe — hand the ext image to `bose-dfu download` or `dfu_download.py` — is
aimed at the wrong receiver, and would have been a wasted flash:

- **AN093 knows nothing about this.** CSR's DFU spec documents only the `CSR-dfu2`
  container; the Boot Loader "validates the header on receipt" and that header is the
  container's File Header Area. A bare `fsr_dfu1` has none. `TARGET`/`SUBID` are Bose's own
  index conventions, not CSR DFU features, and the DFU protocol carries no target field.
- **`dfu_download.py` refuses the file anyway**: it calls `parse_suffix()` unconditionally
  and exits with "no 'DFU' signature in suffix". The ext image ends at its `iFel`
  filesystem trailer with no DFU suffix, so the tool would have to be changed to send it —
  a change that should not be made until the receiver is known.
- **The writer is the running app, fed over USB.** `fn_18819` pairs
  `StreamPartitionOverwriteSink(SERIAL_FLASH, 0)` with `StreamUsbEndPointSink(2)` and
  `StreamSourceFromSink`, i.e. partition writes are driven from a USB endpoint **in normal
  mode by `vm.app`** — not from the boot loader in DFU mode. The ext image is installed
  through the application's own updater channel.

So the honest status of ext-filesystem delivery is: **the target is right, the payload
format is one we can already write, the mount already exists — and the channel is the
app's updater protocol, which this project has not yet driven.**

## What genuinely favours the route

- **The signature bypass is real and Bose uses it.** `partition_if.h:60` defines
  `PARTITION_MESSAGE_DIGEST_SKIP = 3` = "do not perform verification", and Bose's own
  writer calls `md_type=3` at `0x18754` and `0x1894f`. A cave can commit a self-authored
  partition with no signature and no CRC. (It bypasses only the *partition* digest — not
  the loader's protection list.)
- **`partition.h:44-46` confirms the first-word rule**: a partition's first word is held
  in RAM until the stream closes, then verified against the digest. Without
  `PartitionSetMessageDigest` it is never committed and the partition stays
  `PARTITION_STATE_INCOMPLETE`. So a forgotten digest fails *safe*.
- **`KalimbaLoad` from a cave is proven clean on hardware** (probe93), as is wiring the
  DSP output to the DAC (probe95). Only `KalimbaSendMessage(0x7000)` wedged (probe96) —
  and **our app needs no `0x7000`**, because we wrote it and it self-times.
- **The payload can be assembled.** The blind window gives 29 editable bytes in every 64,
  so no 64 contiguous chosen bytes exist — but the cave does not need contiguous *source*
  bytes. It copies each block's 29 blind bytes into the partition sink, and the partition
  content comes out dense. 4,094 bytes needs ⌈4094/29⌉ = **142 source blocks = 9,088 B**
  of `data_us`'s 219,528 (45% writable, and the `fsedit` channel is proven on hardware).
- Every trap needed has a stub: `StreamPartitionOverwriteSink`(599), `MessageSinkTask`(210),
  `SinkSlack`(218), `SinkClaim`(222), `SinkMap`(226), `SinkFlush`(230),
  `PartitionSetMessageDigest`(611), `SinkClose`(298), `PartitionGetInfo`(607),
  `PartitionMountFilesystem`(603), `FileFind`(426), `KalimbaLoad`(441).

## What makes it unsafe today

1. **`StreamPartitionOverwriteSink` erases the whole target partition on open**, and
   erases shared sectors of neighbours if the partition is not sector-aligned
   (`stream.h:390-416`). With the live map unknown, the blast radius is unknown.
2. **The cave must write a whole filesystem, not a file.** `KalimbaLoad(FILE_INDEX)` needs
   an index from `FileFind`, which searches the *mounted* union filesystem, and
   `PartitionMountFilesystem` parses a CSR read-only-filesystem structure. A raw `.kap` in
   a partition is invisible. So the payload is a complete ROFS image wrapping the `.kap`
   (~5-6 KB, raising the gather to ~180-210 source blocks), built offline.
3. **The VM cannot read partition bytes back** — there is no raw-partition-source stub in
   `tools/bose-stubs.json`. Verification is limited to `PartitionGetInfo` STATE/SIZE.
4. **Cave budget.** Gather+write (~60-120 words) plus mount+FileFind+KalimbaLoad (~40-60)
   against 262 words total, 64 already used. Tightest cave attempted, little margin.

## Recovery, and the one mode that is not bounded

`POWER + VOICE-ASSISTANT ~10 s` recovered this device from `errFIRMWARE` caused by a
partially-written image, so it survives corruption of the app and filesystem layer — i.e. it
works when the **boot loader** is what is running.

> **CORRECTION, 2026-10-08.** This paragraph used to call it "a hardware DFU entry that works
> with the VM app completely dead", and that claim is not supported. When probe158 wedged
> unit 2 — application still running and enumerating `40fe`, but servicing no HID — the combo
> **did not work**: the LED went out and nothing else happened. A wedged-but-running
> application is not the same state as `errFIRMWARE`, and the combo may well be serviced by
> the application's own button handler. What recovered the wedge was **unplugging USB and
> holding POWER alone for ~20 s**, because with USB attached the chip stays powered and a
> power-off cannot take effect. The ordered procedure is in `docs/FLASH-PROTOCOL.md`'s
> Recovery section.

| failure | lands in | recoverable? |
|---|---|---|
| wrong but valid unused partition erased | that partition gone, FS0 intact | yes |
| aliases partition 0 | live filesystem erased | yes — precedent exists |
| interrupted write | partition INCOMPLETE, FS0 intact | yes |
| digest omitted or bad | INCOMPLETE, nothing committed | yes, fails safe |
| **misaligned write reaching the partition map or a loader-adjacent sector** | loader may not find itself | **unbounded — the one case we cannot rule out** |

## The only thing to do next: a write-free census

A cave that calls **`PartitionGetInfo(SERIAL_FLASH, n, key, &value)` and nothing else** —
no open, no write, no mount, no load. Reads only, zero brick risk. It answers the whole
go/no-go:

- does any partition `n > 0` exist, and is any `TYPE == PARTITION_TYPE_UNUSED`? If none,
  **the route is dead and we stop, with the speaker untouched**;
- `SIZE` says whether a 5-6 KB ROFS fits;
- `SECTOR_SIZE` and the offsets bear on the shared-sector risk, which is the only
  plausibly-unrecoverable mode;
- `IS_MOUNTED` confirms whether 0 is the only mount.

Reporting is the constraint: ~60 values against a spoken channel of maybe ten
distinguishable prompts. The useful compression is to speak **the first `n > 0` whose
TYPE is UNUSED**, or a distinct id for "none", which is the go/no-go in one press. The
address of a result slot can be formed with Bose's own idiom, seen at `0x107f3`:
`ld AL,@0xffe4 ; add AL,#n ; st AL,@(k,Y)`.

Gated on that passing: open the sink on that partition, write a small known pattern, set
the digest to SKIP, close, and re-read STATE — **no mount, no `KalimbaLoad`.** Only after
both steps is the full attempt a bounded risk.

**Ordering.** This is behind probe110 and probe111, which are recoverable-wedge-only and
go straight at the deliverable. The partition route is worth de-risking, not rushing, and
I will not write to flash without the owner's explicit go-ahead.

## probe138, 2026-10-06: the updater's custom-URL channel is CLOUD-ONLY. Nothing written.

Ran `build/extfs/probe138.py` with `--i-mean-it`. **The updater refused the request and the
speaker was never written.** The device still holds probe137 and ext 1.1.3.

The endpoint signature was recovered verbatim from the btu.bose.com SPA bundle
(`/prod/iot-btu-fe-core/assets/index-ClUMmefc.js`, function `updateNaOTAUsingURL`):

```
updateUsingEndpointUrl?deviceID=&url=&version=&fileCrc=&fileSize=
```

`url` is a parameter, which is why this looked like a custom-file channel. **It is not, for
this device.** Measured:

| call | status | meaning |
|---|---|---|
| `startUpdaterSession`, `isUpdaterReady` | 0 | session fine |
| `getCurrentDevicesConnected?pids=-1` | 0 | device found (GUID). Omitting `pids` gives `-1005` |
| `getCurrentDeviceInformation` | 0 | `internalVersion 3.0.3.6546`, `externalVersion 1.1.3.6164`, `isLatestVersion false`, **`useCloud "0"`** |
| `getAvailableVersions` | 0 | `["3.0.3.6546"]` — the product IS in the updater's index |
| `getUpdateProgress` | 0 | `state idle` |
| **`getGuid`** | **-1007** | `guid: ""` |
| **`updateUsingEndpointUrl`** | **-1007** | refused; nothing logged, nothing written |

The error table, from the same bundle: `-1003 INVALID_FUNCTION`, `-1004 INVALID_PARAMETER`,
`-1005 MISSING_PARAMETER`, **`-1007 NO_DEVICE`**, `-1008 DEVICE_COMM_FAILURE`.

So this is not a malformed request — dedicated codes exist for that. It is device
*resolution* failing, and `getGuid` fails the same way with an empty guid. The SPA's
`UpdateButton` computes `et = a.useCloud == "0"` and reaches `updateNaOTAUsingURL` only via
the `getServiceDiscovery` → `getNaOtaUpdate` cloud path. **`updateUsingEndpointUrl` is the
NA-OTA (cloud) route; this product reports `useCloud = 0` and has no cloud GUID, so it is
not eligible.** In Advanced mode the SPA instead calls
`updateToSpecificVersion(deviceID, version)`.

**This confirms the README's original claim** that the updater offers only official-image
endpoints for this device, and corrects my reading that a URL parameter opens a custom-file
path. `updateToLatest` / `updateToSpecificVersion` pick the file from Bose's own index.

### What probe138 did establish, at zero risk

1. **The ext partition is a legitimate delivery target.** It parses with
   `tools/csr/dumpfs.py`, holds 25 files of foreign-language prompt data and nothing
   boot-critical, and **`vm.app` reads it** (`ext_version`, `NowSpeakTTS`, `tts/`, `data_`
   in the one-char-per-word encoding) — so it is mounted into the union filesystem that
   `FileFind` searches. The 29-of-64 blind-window cap that closes the signed-DFU channel
   does **not** apply to a partition written outside DFU.
2. **A software-readable verification channel for that partition exists**, which
   `dfu_upload.py` cannot provide: TAP `v2` = external flash version, `la` = installed
   languages, with `vr` as the control. Read before and after, **no button press needed.**
   Measured on unit 2: `vr` Main 3.0.3.6546, `v2` **Ext 1.1.3-6164**, `lc` en-us, `la` 13
   languages. The updater's own record agrees (`externalVersion 1.1.3.6164`).
3. **This unit's ext partition is a version behind its firmware**, and 3.0.3.6546 is offered.

### Where that leaves delivery

- **`updateToSpecificVersion("3.0.3.6546")`** would exercise the official write path, but it
  installs the official bundle — which includes the main `.dfu` and so **wipes the cave**
  (recoverable: reflash probe137). It buys a channel proof and no custom content.
- **Redirecting the updater's index host** to serve our own `index.xml` + images would reuse
  the sanctioned path with content we choose. The updater logs `DOWNLOADING INDEX FILE` but
  the URL is not in the log and not in any binary (Qt resources are zlib-compressed), so
  this needs traffic observation to locate. Not yet actionable.
- **A cave-driven `StreamPartitionOverwriteSink(SERIAL_FLASH, 2)`** is now better grounded
  than when this document was written: partition 2 is confirmed in Bose's own code, its
  contents are non-critical, and `v2`/`la` verify the result without a press.
- **The app's own USB update receiver** (`fn_18819`, `StreamUsbEndPointSink(2)`) is an
  unmapped protocol distinct from the boot loader's that `bose-dfu` speaks.

## probe139, 2026-10-06: the write-free census is BUILT — not flashed

`build/hook/assemble_probe139.py` → `probe139_brown.dfu` (sha256 `d93a8728…`), 90 cave
words inside `0x3E21D..0x3E306`, redirects byte-identical to probe137's. It calls
**PartitionGetInfo and nothing else**: partition 0 as a self-check (we know it is
FILESYSTEM), then a sweep of 1..4 for the first `TYPE == UNUSED`, then — if none —
partition 2's TYPE, which is the datum that decides whether the overwrite-p2 plan is
grounded. One spoken id per press, from the owner-verified catalog:

| heard | meaning |
|---|---|
| battery 10/20/30/40% | partition 1/2/3/4 TYPE=UNUSED |
| battery 50% | none unused; **partition 2 = FILESYSTEM — the expected live map** |
| battery 60/70/80% | none unused; partition 2 = PS / RAW_SERIAL / RANDOM_ACCESS |
| auto off disabled | none unused; partition 2 absent or TYPE unrecognized — stop |
| conference call failed | CONTROL FAILED: the part-0 query contradicted a known answer; data invalid |

ABI taken from two stock call sites (0x1192a, 0x182d1): `AL`=device 1, `AH`=partition,
`@(0,Y)`=key (TYPE=2), `@(1,Y)`=uint32* out via `ld AL,@0xffe4 ; add AL,#n` — the **Y
register mirror** at 0xFFE4 (0xFFE0 is the AH mirror; using it gave garbage until
caught in simulation). Low half of the out value sits at ptr+1.

Verified before build: all 11 outcome branches simulated in cavesim (PartitionGetInfo
modelled from a `--pmap` map, default the predicted `{"0":1,"2":1}`), control probe90
still `AL = 0x0E`, preflight + caveguard pass (all branch forms attested in Bose
firmware). Two toolchain defects found and fixed on the way:

1. **xapemu read/wrote negative @abs operands unmasked** — `ld AL,@0xffe4` is a signed
   −28 that must wrap to 0xFFE4; unmasked it read the end of the RAM buffer. Never
   exercised before, because no earlier probe used the frame-pointer idiom.
2. **XAP2 carry polarity recorded** (it matters for every future sweep): `cmp` sets
   C=1 on borrow, so **bcc = taken when AL ≥ val and bcs = taken when AL < val** —
   the opposite of ARM/x86. Confirmed against fn_0e06d's own dispatch ladder.

Sequencing: probe137's answer landed first — pressed 2026-10-05, the word **"lost"**
(malloc(254) refused with music paused), closing the one-shot heap route and making the
partition route the live path to sustain. probe139 was flashed over it 2026-10-06 (flash #14
on unit 2) and readback-verified: 0 of 975,168 filesystem bytes differ, 90/90 cave words,
11/11 redirect bytes. **Awaiting its press.**

## The index-host redirect, 2026-10-06: tried, and blocked at the transport

The one remaining sanctioned-path variant — intercepting the updater's lookup/index
fetch so it downloads OUR index.xml listing OUR ext image — was followed this morning
with host-side-only tooling (no DFU, no write, no update endpoint called):

- `build/extfs/index_sniff.py` — per-user WinINET proxy (HKCU, no admin), answered
  everything 502. Learned only that requests happen; left the updater failed.
- `build/extfs/index_proxy.py` — same proxy mechanism but FORWARDING: plain HTTP is
  relayed and captured, CONNECT is tunnelled blind, settings saved/restored in a
  `finally`. Restarted the updater and called `startUpdaterSession` — the call that
  pulls lookup + index.

**Result (`build/extfs/capture/transcript.json` (not in this export)): every updater fetch is HTTPS.**
`worldwide.bose.com:443` and `bose-downloads.s3.amazonaws.com:443` via CONNECT —
hosts visible, paths and bodies not. No plain HTTP anywhere.

So serving our own index requires MITM with a CA the updater trusts — a separate and
much larger decision (certificate installation, and the index/image signatures would
then have to pass whatever the updater or device checks). **The updater route is
parked there.** What remains actionable on this route is unchanged: the cave-driven
`StreamPartitionOverwriteSink(SERIAL_FLASH, 2)` behind the probe139 census, and the
unmapped fn_18819 USB protocol.

## The updater/index route: verdict — dead for custom content; the real finding is better

Follow-up disassembly of the device's app-mode update receiver (2026-10-06, same session as
the index-proxy run). The receiver is `fn_18634` (state machine, called from the endpoint-2
task handler `fn_185c3`), with responses on endpoint **0x81** (`fn_188ea`) and commands on
endpoint **0x02**. Three walls now stand between the updater-index idea and custom content:

1. **Transport.** All updater fetches are HTTPS (measured, §above): substitution needs a
   trusted CA on the host — invasive, and unproven that the updater trusts user-store CAs.
2. **The index carries no integrity controls.** `index.xml` IMAGE entries have only
   CRC/LENGTH/TARGET/SUBID/NOFORCE — no digest-mode or signature field. The digest mode is
   chosen by the UPDATER per image kind, so a substituted index cannot relax verification.
3. **The device verifies signed images on write.** For a type-4 (ext) write the receiver's
   digest phase reads a code from its state word (`@0x69c` bits 8–10): **1 = APP_SIGNATURE**
   → `fn_18896` copies the signature **from the incoming USB stream** and
   `PartitionSetMessageDigest(sink, 1, sig, len)` makes the device check
   `S³ mod n == recompute(content)` itself. We cannot produce a valid signature for
   self-authored content, and the 29/64 blind-window cap makes feed-evasion worthless for
   sustained audio. A MITM'd custom ext image is rejected on write.

**The real finding — the digest mode is HOST-CONTROLLED and SKIP is one of the options.**
The state machine accepts codes 1 (APP_SIGNATURE), 2 (CRC, 2-word CRC also from the stream),
and **3 = SKIP, no verification at all** (`0x18754`: `md_type=3` with null data/len). Bose's
own type-0 path already uses it: `fn_187e7` routes image type 0 to `fn_18908`, which writes
via `StreamReformatSerialFlashSink(SERIAL_FLASH)` and closes with `md_type=3`. Types 1/2 →
partition 0, type 4 → partition 2 via `StreamPartitionOverwriteSink`; unknown types are
refused (`0xffff` check). So the true "direct write" is not the updater at all — it is a
custom host that speaks the app-mode USB protocol and sends digest code 3. No updater, no
TLS, no index, no signature, no cave words.

**RE roadmap for that protocol** (all static so far, zero device writes): message framing on
ep 0x02/0x81; the `@0x69c` state-word layout (families 0x2000–0xe000, digest code in bits
8–10, entered from the 0x8000 family); image-type codes (0 reformat, 1/2 → p0, 4 → p2); how a
transfer session is armed; and what `fn_18525(0xa5c6)` / `fn_188ea`'s 3-word responses carry.
The cleanest ground truth would be a passive USB capture of the official updater performing
an **official ext-only** update — sanctioned, ext-only, main fs untouched — but that needs
USB capture tooling and eyes on the device; deferred until the owner is home.

Until then the actionable path is unchanged: probe139 (census, on device) → pattern-write
probe → cave-driven `StreamPartitionOverwriteSink(SERIAL_FLASH, 2)`.

## probe140, 2026-10-06: the pattern-write is BUILT — not flashed, awaiting owner go-ahead

Census result first (pressed 2026-10-06, **"battery 70%"** = id 0x2d): the control passed
(part 0 = FILESYSTEM), **no partition 1..4 is UNUSED, and partition 2 EXISTS with
TYPE = RAW_SERIAL** — the first hardware reading of the live partition map. TYPE is a
property of the SQIF map, not the content, so the ext fs living in a RAW_SERIAL partition is
consistent; the overwrite-p2 plan stands on a hardware-confirmed target.

`build/hook/probe140_brown.dfu` (not in this export) (sha256 `4bebac28…`, 155 cave words in
`0x3E21D..0x3E3A2`, redirects identical to 137/139) is the second gate:

1. GetInfo(p2, STATE) — control
2. **StreamPartitionOverwriteSink(1, 2) — erases partition 2** (ext language packs die;
   restorable from `Minnow_3.0.3_ext_signed.xuv`, whose genuine RSA signature lets a
   restoral write pass md_type=1 on-device)
3. SinkMap + SinkClaim(16) — fn_12e1a's idiom, inline, guards strengthened
4. write 8 words: `fsr_dfu1` as 4 LE words + 0001..0004 (a raw-read marker, not an fs)
5. SinkFlush(16); 6. PartitionSetMessageDigest(sink, 3=SKIP, 0, 0); 7. SinkClose
8. GetInfo(p2, STATE) — the verdict

One spoken id: **battery 10% = STATE VALID, route GO**; 20% = INCOMPLETE (failsafe fired);
30/40/50/60% = open/map-claim/flush/digest failures; "conference call failed" = control.
The press may take a while (~2 MB erase inside step 2) — do not pull power mid-press.

Verified before build: all reachable outcome paths simulated (new cavesim models for
StreamPartitionOverwriteSink / PartitionSetMessageDigest / SinkClose, with stateful
post-write STATE); control probe90 AL=0x0E; preflight + caveguard pass (155 words, all
branch forms attested). The simulator caught three real bugs before any flash: branch
polarity inversions on the map-0 check, the claim guard, and the final STATE==VALID test;
the boundary checker caught a 2-word prefixed `ld` emitted as two separate layout items;
and the store encoding was `st X,@(n,Y)` (0x2B — stores the map pointer into frame slots)
where `st AL,@(n,X)` (0x26) was meant. All fixed and re-verified.

**HOLDING FOR OWNER GO-AHEAD** — this probe writes flash (the p2 erase is the point).

## Safety analysis for probe140 (owner question: "can this brick the USB interface?")

Asked before authorizing the flash. The honest answer, recorded here as the reference:

**What the write CANNOT address.** `StreamPartitionOverwriteSink(1, 2)` selects a data
partition BY NUMBER through the stack's SQIF map. The USB interface lives in three places,
none of which is a partition in that map: the VM app's USB configuration (partition 0 fs +
PS keys — `PSKEY_USB_VM_CONTROL=1` means the app enumerates in normal mode), the stack
firmware (the two `CSRbcfw1` areas, written only through the DFU-container path with its
own header validation), and the boot loader / hardware-DFU entry (factory-immutable — it
never ships in any DFU, per the signature-scheme analysis). A partition number cannot
select any of them. The only adjacent casualty class is partition 0, via sector overlap at
the erase boundary.

**The empirical anchor.** This exact erase has already run on THIS unit: the official
3.0.3 upgrade (2026-10-04) shipped the ext image per `index.xml`, so Bose's updater erased
and rewrote partition 2 with this same trap, and the device survived — it is the unit in
hand. Every SoundLink Micro that ever took a language-pack update did this erase. [CORRECTION 2026-10-12: not supported. Unit 2 took only the stack_plus_app image and read Ext 1.1.3-6164 afterwards, so Bose's updater never erased p2 here; one clean erase is proven (probe140). `docs/FACTS.md` F149, FS-C36.]

**The residual, named precisely.** Partition 2's geometry (start offset, SIZE, sector
size) has never been read — `PartitionGetInfo` exposes SIZE/SECTOR_SIZE but not the start,
and the map itself is in a curator config sector we hold no dump of (verified: not in the
main DFU file). The erase rounds to sector boundaries; if the map had p2 misaligned against
the main image's tail, the rounding could clip the main fs's last sector. The counter: that
would corrupt the main filesystem on every official ext update, which a shipping product
cannot do. This is inference from Bose's practice, not a measurement — hence not "100%".

**Failsafe behavior.** The first-word rule (`partition.h:44-46`): content commits only at
SinkClose after the digest step; an interrupted or crashing write leaves STATE=INCOMPLETE
with nothing committed — a state the API models as normal. Hardware DFU (POWER+VA, proven
on unit 1) reflashes the main image with the app dead. The one tail recovery does NOT
cover: if a wiped p2 caused a boot panic, a main-DFU reflash would not touch p2 and the
app-mode restoral needs the app running; SPI is the only then-remaining route. A boot panic
is judged unlikely (INVALID/INCOMPLETE are modeled states; English needs no ext files) but
is not excluded by a measurement.

**Related finding for the FULL attempt (not probe140):** `sqif_app_validate_if.h` shows the
firmware validates executable filesystems in SQIF at boot; a FAIL stops the VM/DSP and
resets. If application security is enabled on this product, a self-authored .kap in a
restored/rewritten ext fs could fail that validation. Nothing for probe140 to hit (a
pattern is not an fs; no .kap is found or validated), but the full attempt must study this
before KalimbaLoad-ing self-authored code.

## The payload is BUILT — brown_fs.bin (2026-10-06), verified offline

`build/payload/make_payload.py` (not in this export) → **`brown_fs.bin`, 33,014 bytes / 16,507 sink words**:
a minimal ROFS built through csrfspack's own builder (format fidelity inherited, roundtrip
byte-identical) with a fresh 3-entry tree: root + `/ext_version` (the original 11-byte
version file, so `v2`/`la` queries stay sane) + **`/brown.kap` (32,752 B, flags 0x40 =
code, matching every .kap in the main fs)**. The kap is the kalsim-verified generator
(LCG white → leaky integrator → one-pole high-pass, self-timed 1.5 ms, both DAC ports) —
**size decision: kept the 32,752-byte verified build** over shrinking (the route doc's
"4,094 bytes" figure does not match anything on disk). Verified: roundtrip byte-identical,
tree + kap content byte-checked, 16-bit body XOR zero, siw = 16,437 (compact — the builder
otherwise pads to the source image's 2 MB; probe140 proved a short commit reports VALID).

**Honest correction to earlier restoral language:** the original ext packs are NOT
restorable from the cave — data_us can stage ~49 KB, never the 2 MB official image, and no
other 2 MB source exists in partition 0. Once our fs lands on p2, the packs are gone until
the app-mode USB protocol is reversed (then the official image can be re-sent) or SPI.
English is unaffected; nothing boot-critical is in ext.

## probe141 (write probe) — design settled, build next

Staging: the 16,507 payload words go into **data_us** blind windows — 2 payload bytes per
staged word (a staged word IS a payload word verbatim), at the file-word positions where
BOTH bytes are blind. fsedit's rule (`blind(area_byte) = 34 <= (area_byte-136) % 64 <= 62`)
applied to data_us (file word i = body byte 460+2i) gives **file words with i mod 32 in
[7..20] fully writable — 14 payload words per 32-word period**, ~1,180 periods, span
~75 KB of data_us's 219,528. The periodicity means the cave needs NO address table: a
walk of (period → 14 consecutive mapped words) covers everything.

Cave flow (~150-170 of 197 words): FileFind(data_us) → StreamFileSource → SourceMap →
open overwrite sink(1,2) → periodic gather loop (read staged word at base+32p+7+k, claim
28 B per period, store through map, flush) → digest SKIP → close → GetInfo STATE → speak.
New traps for the cave: FileFind(0x1aa), StreamFileSource(0x1b9), SourceMap/SourceSize/
SourceBoundary — models needed in cavesim; the file-source mapping semantics (whole-file
vs sliding window) are the design's main unknown and get spoken bails.

**Known tail (unchanged, now concrete):** the boot-time `sqif_app_validate` may check
executable SQIF filesystems. Our fs has a STALE signature (copied from the official image;
unforgeable). The free test is the power-cycle after the write press, BEFORE the play
press: normal boot = validator does not care about p2; boot-loop = the one state main-DFU
reflash does not fix (SPI territory). The play probe itself never needs a boot.

## probe141, 2026-10-06: the staged write is BUILT — not flashed, awaiting owner go-ahead

`build/hook/probe141_brown.dfu` (not in this export) (sha256 `39fd5dd9…`, 180 cave words in
`0x3E21D..0x3E3DF`, redirects identical to 137/139/140's) writes the REAL payload:
FileFind(`NowSpeakTTS/data_us`) → StreamFileSource → SourceMap → open the overwrite
sink(1,2) → 1,180 periods of {fn_12e1a claim 14 words → memmove from the mapped source →
SinkFlush 28 B} → digest SKIP → close → GetInfo STATE verdict. Outcome ids: battery 10%
= SUCCESS (route GO for the play probe); 20% = INCOMPLETE; 30/40/50% = open/notfound/
gather; 60% ("battery low") = any mid-gather failure (merged: the simulator names the
call, on-device they share the recovery); "conference call failed" = reserve.

The staged bytes ride in data_us at the periodic blind positions (file words i%32 in
[11..24], 14 payload words per 32-word period, 16,520 words over ~75 KB) — placed by
`build/payload/stage_payload.py` (not in this export), carried in the DFU by fsedit's blind+compensation
machinery (33,280 bytes differ from official, all blind-verified by fsedit itself).

Verification: all outcome paths simulated; **the gathered payload is byte-exact**
(16,520/16,520 words into the virtual claim buffer); control probe90 AL=0x0E; preflight
(all forms attested) + caveguard + docaudit pass. The simulation caught FOUR real bugs
before any flash: two branch-polarity inversions, a transposed immediate (`add AL,#1`
for `add AL,#7`), the FileFind path string sitting in the fall-through path (char words
EXECUTE as opcodes — relocated to dead space after the leavel), and the verdict key
asking for TYPE instead of STATE. Two sim-side fixes: xapemu masks negative @abs
operands; the source/claim buffers are virtual (they cannot fit in emulated RAM around
the const window — 37.7 K + 16.5 K words vs 0x7400–0xD39A read-only).

**HOLDING FOR OWNER GO-AHEAD** — writes flash (re-erases p2, which currently holds
probe140's 16-byte marker; no language packs remain to lose).

## probe142, 2026-10-06: THE PLAY PROBE — built, simulated, holding for owner go-ahead

`build/hook/probe142_brown.dfu` (not in this export) (sha256 `0131e17b…`, 148 cave words in
`0x3E21D..0x3E39F`, redirects identical to the family, NO data_us staging — 256 bytes
differ from official, all cave+redirect+compensation). The deliverable press:

  GATE (new, hard requirement): sinkState @0x59e must be 3 or 13 before ANYTHING —
  boot-fire bails SILENTLY (the probe141 harm event's design rule, enforced)
  PartitionMountFilesystem(1, 2, LOWER=1)      -- mount our fs (runtime, RAM-only)
  FileFind(1, "brown.kap", 9)                  -- also verifies probe141's write landed
  VmDeepSleepEnable(0); KalimbaLoad(f)         -- probe93-proven; check + spoken bail
  StreamAudioSink(3, 0, 2)                     -- CODEC ch2 (probe95)
  SinkConfigure(dac, 0x0301, 16000)            -- probe95's exact config
  StreamKalimbaSink(0) -> StreamSourceFromSink -> StreamConnect(ksrc, dac)
  -> the kap is self-timed: BROWN NOISE STARTS AND SUSTAINS

Outcomes: SUSTAINED NOISE = the deliverable (plays until power-off); battery
30/40/50/60/80/90% = mount / notfound / load / dac / ksink+ksrc / connect failed;
silence = gate bailed (press conditions not met) or silent connect — distinguish via
music-playing retry. Failure ids are the familiar battery family (30–90%, distinct).

Simulated: gate blocks silently without --mem; full chain completes with it (trap order
FileFind→DeepSleep→Load→AudioSink→SinkConfigure→KalimbaSink→SourceFromSink→Connect,
all args verified in the trace); every --fail speaks its id; control probe90 0x0E.
The sim exposed one missing check pre-flash (KalimbaLoad's return was never tested —
added with its spoken bail). probe95's precedent covers every trap in the chain:
StreamConnect ALONE was clean (the probe91 wedge was the 0x7000 + gain + unmute
combination, which our self-timed kap does not need).

**HOLDING FOR OWNER GO-AHEAD** — runtime side effects only, but the press makes the
speaker do the thing.

## probe144, 2026-10-06: the dual-path play — built, simulated, holding for go

probe143's press decoded: **sinkState at the hook = 2** (battery 30% = 0x27+2; the
percentage is not the state number) — the enter-pairing transition in flight — and
**PartitionMountFilesystem returned FALSE**. Two causes: (a) probe141's write produced
garbage on hardware, or (b) **p2 is already mounted by Bose's boot code** and
double-mounting returns FALSE — in which case /brown.kap is ALREADY in the union
filesystem and the mount was never needed.

`build/hook/probe144_brown.dfu` (not in this export) (sha256 `3079ea68…`, 159 cave words) tests both in one
press, runtime-only: FileFind(/brown.kap) FIRST (no mount) → if found, straight to
KalimbaLoad + the probe95 DAC wire (deliverable); only if absent, mount p2 and retry
FileFind. Every step speaks (state report first, then the phrase family: mount refused
= "voice prompts on", absent-after-mount = "voice prompts off", load = "auto off
disabled", DAC sink = "auto off enabled", DSP port = "muted", source = "unmuted",
connect = "call ended"). Simulated: all paths + control; preflight pass.

---

# STATUS (2026-10-06, end of campaign): PARKED — blocked at the mount

Campaign summary (all details above and in docs/field-log.md):

| press | probe | first id | outcome |
|---|---|---|---|
| #16-era | probe141 (staged write) | (audio already dead) | device harm: total audio loss; stock recovery |
| #19-era | probe143 (state report) | battery 30% | sinkState=2 at hook; mount FALSE |
| #20-era | probe144 (dual-path) | battery 30% | unmounted FileFind found nothing; mount FALSE |

PROVEN: cave-side partition writes (erase/commit/digest-SKIP, probe140 STATE=VALID);
the fs payload builds, stages, deploys and reads back byte-exact; our fs on p2 is
boot-tolerated. BLOCKED: the mount refuses (FALSE, reproducibly, any state) and the
file is not visible unmounted. Causes (a) garbage-on-hardware from unverified SourceMap
semantics vs (b) RAW_SERIAL-typed partitions refusing PartitionMountFilesystem —
indistinguishable without a p2 read-back channel (none exists: DFU serves only the
declared main area; TAP v2 is a version record; the curator config sector was never
dumped).

UNBLOCKING OPTIONS (for a future session, in cost order):
1. **USB protocol RE** (the roadmap earlier in this file): a custom host speaking the
   app-mode protocol could also READ p2 back (the receiver's inverse) — answers (a)/(b)
   and enables direct p2 writes without any cave.
2. **Curator-config dump**: the partition map sector would settle the geometry question.
   Needs the SPI dongle (hardware) or a map-revealing API.
3. **Accept (b) and change the payload target**: if RAW_SERIAL partitions refuse
   mounting, no unused FILESYSTEM partition exists (census) — the route would need a
   map edit (curator config, same as 2).

Meanwhile the REFILL-LOOP route (docs/deep/buffer-cadence.md + the field-log analysis)
is unblocked in-hand: its ~23-word shortfall is recoverable by hand-assembling the
generator, and every other piece is hardware-proven. RECOMMENDED next work.

## CORRECTION 2026-10-12 (firmware study; appended, the text above is unchanged)

1. The "empirical anchor" (the official 3.0.3 upgrade erased and rewrote partition 2 on THIS unit) is not supported: `docs/FACTS.md` F149, `docs/deep/strategy-2026-10-12/STRATEGY.md` (not in this export) J-C1, FS-C36.
2. The section "CORRECTION: the partition map this project had was never grounded" is itself corrected. The 64-byte constant at vm.app data 0xAC25 (file byte 0x7A83E) IS a three-entry partition table (count 3; {0x1000, 0x1F4000, type 1}, {0x1F5000, 0x25800, type 1}, {0x21B000, 0xFA000, type 3}); it stores one byte per word and the sizes are in 16-bit-word units, so it holds exactly the numbers retracted as X005 (4,096,000 B, 307,200 B, 2,048,000 B). It is the default layout written by the app's type-0 reformat; whether the live unit has it is unmeasured. `docs/FACTS.md` F216, X046, T09 skeptic item 10.
3. "Partition 2 is almost certainly the external language filesystem" is in tension with that table: p2 is RAW_SERIAL (probe139) and 2,048,000 B is smaller than the 2,090,936 B ext image. Mark it a hypothesis; FS-C34.
4. The update route statements about the app-mode USB receiver are refined by the T09 skeptic section (HID Output report 3, opcode 0..5; image type 0 is a one-byte whole-flash wipe; in family 0x2000 no write opcode is reachable): `docs/FACTS.md` F212-F215.

## Round-3 amendment (2026-10-12, curator)

Appended at the end so that line numbers cited elsewhere stay valid. Corrections from `docs/deep/round3-2026-10-12/` that concern this file; full register: `docs/deep/round3-2026-10-12/README.md` (not in this export) section 4. Grades follow the verifier sections of the round-3 notes. Nothing above this heading was edited except a pointer on the status or banner line.

- **R3-C011** (R02 + verification). Claim: RT-08, Q014, Q015, RETURN-CHECKLIST 184a/185a/185b and D1/D11, STRATEGY 4.1: p2 is reachable by FileFind after PartitionMountFilesystem; a failed mount may be garbage; 185b "if RAW_SERIAL refuses to mount, software is blocked". Correction: PartitionMountFilesystem (worker 0x112e9) calls the table-type test with key 1 (FILESYSTEM) at 0x01130d-0x01130e; p2 reads TYPE 3 (F120), so the mount returns FALSE for any content (well-supported; conditional on the partition table, which a type-0 reformat could rewrite, F213/F216, not planned). Q015 is answered (type refusal), F122 explained, 184a/185a/185b and the built 184 family cannot succeed as designed (owner decision PD-20 in PLAN-v2). The "trap with no stub" 0xD3 is the route, not the block.
