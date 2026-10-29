Purpose: one-page orientation on the DFU container, Bose's signature scheme, which
bytes can actually be changed, and the recovery path, with routes into every doc that
has detail.

Status / last verified: 2026-10-10.

Read next: docs/FLASH-PROTOCOL.md for the mandatory gates before any flash, then
docs/topics/hardware-and-firmware.md for what the writable bytes are used for.

Confidence marks: **proven** (address, instruction, command output, or quoted press),
**well-supported** (one traced inference beyond a proven fact), **hypothesis**.
`docs/dfu-signature-scheme.md` is the final-state derivation of everything summarized
here; it has been trimmed to its established conclusions (the original, much longer
session-by-session research log -- which contained several corrected false starts along
the way -- is not reproduced in this export).

---

## 1. Summary (what is established)

Bose signs the internal filesystem with 1024-bit RSA, exponent e=3, no padding, over a
non-standard hash: eight interleaved MD5 chains fed from the filesystem body, each
block of which is read only 34 bytes deep by the hashing code. That last fact is the
whole opening: 30 of every 64 bytes in the signed filesystem never enter the hash, so
they can be changed freely and the signature stays valid -- no cryptographic forgery is
needed. A companion 32-bit digest field and the container's own XOR redundancy check
also have to be kept consistent, and this project's tool (`tools/fsedit.py`) automates
both the chosen edit and the compensating fixups. This has been proven on hardware with
arbitrary chosen content (probe8, probe9), and it is the actual, currently-used write
channel for everything this project ships. Two other write surfaces were tried and are
closed: the stack area and the unsigned PS areas are both rejected by the loader for a
reason that is not visible anywhere in the plain image (not a CRC, not the known hash).
A third surface -- writing a running application's own flash partition at runtime -- is
real (Bose's own code does it) but is parked: it is the only route in this project
whose failure mode is an unrecoverable brick, and only a tiny write has ever been
proven to commit. DFU recovery back to stock firmware is proven and routine.

Ranges, so they are not read as a conflict: byte rule 34..62; word rule 34..60 (a word needs both bytes blind; the cave assembler uses the word rule); the hash itself never reads 34..63 (30 bytes of every 64), and `tools/fsedit.py` is one byte tighter at 34..62 (29 bytes of every 64) as a safety margin. See `docs/GLOSSARY.md` ("blind window" entry). One-line proven statement: `docs/FACTS.md` F015 and F050. Primary source: `docs/dfu-signature-scheme.md` sections 1-2.

## 2. Key facts

| fact | confidence | source |
|---|---|---|
| Verification the device performs is raw RSA, e=3, no padding: `multiprec_expFP(block,3,...)`, from CSR's own BlueSuite source | proven | docs/dfu-signature-scheme.md section 1 |
| The signed block is 8 independent, interleaved standard-MD5 chains (IV-initialized), chunk k of the fed stream going to chain k mod 8 | proven, validated bit-exact against hashlib.md5 and against dfusign on tiny/tiny2/ext test files | docs/dfu-signature-scheme.md section 1 |
| The compress step reads only bytes 0..33 of each 64-byte block (message words M[0..15] as LE dwords at 16-bit stride); bytes 34..63 never enter the hash | proven -- this is the project's actual write channel | docs/dfu-signature-scheme.md section 1 |
| Hashed span = digest(4B) + filesystem body, minus the area's final word; feed = every complete 64-byte block; empty tail -> no finalize block | proven, canonical rule, now in tools/csrhash.py | docs/dfu-signature-scheme.md section 1 |
| Bose's signing modulus n (1024-bit) is recovered and verified against all 7 shipped Minnow releases: `S^3 mod n == B` for every release | proven | docs/dfu-signature-scheme.md section 1; reproduce with tools/recover_modulus.py |
| 29 of 64 bytes per block are writable ("blind"); no contiguous run over 29 bytes exists anywhere signed | proven | docs/dfu-signature-scheme.md section 2; docs/cave-budget.md "What is not available" |
| A second, separate 32-bit digest field is GF(2)-linear (CRC-family) on valid bodies; `dfubuild`'s checksum reproduces the shipped digest exactly and recomputes it on edits | proven | docs/dfu-signature-scheme.md section 1 |
| `tools/fsedit.py` automates: (1) chosen edits in blind bytes, (2) an XOR balance pass, (3) a GF(2) solve for digest-compensation flips, (4) full verify (digest byte-identical, RSA block invariant, XOR 0, csrverify) | proven | docs/dfu-signature-scheme.md section 2 |
| Arbitrary chosen content was flashed and accepted: probe8 (16 one-bit flips, accepted, readback confirmed), probe9 (43-byte diff incl. 18 chosen bytes, accepted, readback byte-identical) | proven on hardware | docs/dfu-signature-scheme.md section 2 |
| The stack area (`CSRbcfw1`) has only a CRC-32, no RSA signature; a CRC-fixed edit (probe1) was still rejected (`errFILE`) -- the loader checks a reference not visible anywhere in the plain image | proven, cause unknown | docs/dfu-signature-scheme.md section 3 |
| Unsigned PS areas (sps: 90 stack keys, aps: 54 app keys), CRC-32 only, no signature/digest field; a CRC-fixed PS edit (probe6, a one-byte product-string change) was also rejected at the manifest stage (`errFILE`), same as the stack | proven, closes this door | docs/dfu-signature-scheme.md section 3 |
| A likely (not device-proven) explanation: CSR's own `dfukeyinsert`/`dfusign` tools put the vendor's public key into the loader at build time, and the loader checks the stack's signature against that embedded key -- a check USB DFU, which never replaces the loader itself, cannot route around | hypothesis, research-grade | - |
| Partition 0 (internal filesystem) is the only target the boot-mode DFU protocol (AN093 / `CSR-dfu2` container) can write; a runtime write to partition 2 uses `StreamPartitionOverwriteSink` with digest mode SKIP=3, driven by the *running application* over a normal-mode USB endpoint, not the boot loader | proven (mechanism) | docs/partition-route.md "The live map..." and "But the delivery channel..." |
| A 16-byte runtime partition write was proven to commit (`PartitionSetMessageDigest`); a full-size write was never attempted; this is the project's one unbounded-brick-risk route, not recommended without a full understanding of the risk | proven (16B) / untested (full size) | docs/partition-route.md "What makes it unsafe" |
| DFU recovery to stock 3.0.3 is proven: after a rejected probe, `bose-dfu download -f -p 4022` of the official image followed by `leave-dfu` restores Main 3.0.3.6546 | proven | docs/FLASH-PROTOCOL.md "Recovery" |
| A wedged-but-still-enumerating device (40fe) needs USB unplugged, POWER held ~20s, then USB replugged and POWER pressed again; the POWER+VOICE-ASSISTANT combo does NOT recover this state (only errFIRMWARE) | proven, corrected 2026-10-08 | docs/FLASH-PROTOCOL.md "Recovery" steps 4-5 |
| If the VM app itself dies, there is no USB at all (`PSKEY_USB_VM_CONTROL=1`) and no software recovery exists; only CSR SPI hardware recovery remains | proven | docs/FLASH-PROTOCOL.md "No USB at all" |
| Unit 1 was permanently lost 2026-10-04 after skipping the flash-protocol gates (11 flashes, 9 presses, 92 minutes, zero readbacks); the single cause is not established (the cave-outside-window pattern of probes 121, 127, 130 may be the real reason) | the loss proven; the cause well-supported at best | docs/POST-MORTEM-2026-10-04.md |

## 3. How it works, in layers

1. **Container layer.** The DFU file is CSR's standard `CSR-dfu2` container (per AN093),
   carrying a File Header Area plus one or more area images. On this device the areas
   are `CSRbcfw1` (native Bluetooth stack), `CSR-Rdfu1`/`CSR-Rdfu2` (loader-recognized
   area ids), and the filesystem area whose own internal format id is `fsr_dfu1`. The
   boot loader validates the container header on receipt; a bare `fsr_dfu1` filesystem
   with no `CSR-dfu2` wrapper (like the external-language image) is not something the
   loader protocol accepts at all (docs/partition-route.md "But the delivery channel").

2. **Filesystem signature layer.** Inside the filesystem area, Bose's own signing tool
   (`dfusign`) computes a 128-byte block from `digest(4B) + filesystem body` (minus the
   area's final word), fed in 64-byte chunks to 8 interleaved standard-MD5 chains
   (chain = chunk index mod 8), each chunk's hash input truncated to its first 34 bytes.
   That 128-byte block is signed with raw RSA (`B^d mod n`, e=3 on verify), and the
   signature words are stored reversed in the file. The device verifies by recomputing
   the same block from the content it receives and checking `S^3 mod n == B`. Because
   the hash ignores bytes 34..63 of every block, those bytes ("blind bytes") can hold
   any content without breaking the signature.

3. **Digest-compensation layer.** A separate 32-bit digest field (GF(2)-linear /
   CRC-family, Bose's own un-identified-but-linear algorithm) must also match, or the
   loader's "vendor-specific verification" fails even with a valid RSA block (this is
   what rejected an early blind-edit-only probe, probe2). `tools/fsedit.py` measures
   the digest's linear contribution at pool positions and solves a small GF(2) system
   to find compensating blind-byte flips that restore the digest exactly, alongside a
   separate pass that keeps the body's 16-bit XOR redundancy at zero (`dfubuild` silently
   drops any filesystem whose body XOR is nonzero).

4. **PS and stack layer (closed doors).** The stack area and the unsigned PS areas
   (`sps`, `aps`) carry only a CRC-32 each -- no RSA signature, no digest field -- yet a
   CRC-fixed edit to either was rejected by the loader with `errFILE` at the manifest
   stage. The reference the loader checks against is not a plain CRC or the 8-chain
   hash visible anywhere in the plain image; it is most likely the stack's own
   signature verified against a vendor public key embedded in the loader at build time
   (a mechanism this project cannot reach over USB DFU, since the loader itself is
   never part of any DFU payload).

5. **Runtime partition-write layer (parked, high-risk).** Separately from the DFU boot
   loader, the running VM application has code (`fn_18819` / `fn_187e7`) that writes a
   chosen flash partition from a normal-mode USB endpoint, using
   `StreamPartitionOverwriteSink` with digest mode `SKIP=3`. This is how Bose delivers
   the external-language filesystem to partition 2 in production. The mechanism and
   every needed trap stub are proven to exist; only a 16-byte write has actually been
   committed in this project. A misaligned full-size write could in principle reach the
   partition map or a loader-adjacent sector -- the one failure mode worse than a
   recoverable wedge -- so do not attempt a full-size write without understanding that risk.

6. **Recovery layer.** The boot loader always accepts a validly signed official image,
   so any rejected or bad probe can be undone by downloading the stock 3.0.3 DFU and
   leaving DFU mode -- proven multiple times, including after the stack-probe rejection
   and after probe6. The harder case is a wedge where the application half-runs: there,
   recovery is a physical USB-unplug + power-cycle sequence (docs/FLASH-PROTOCOL.md),
   not a software command, because a stuck message loop services neither HID commands
   nor the expected button combo.

## 4. One retraction worth keeping (what the first guess got wrong)

**"Cube-root forgery" was the first guess, and it is wrong.** The signed block is a
full-width hash with no attacker-steerable bytes in the naive sense, so forging a
signature via a bare RSA weakness (e=3 with no padding, over attacker-chosen bytes)
does not apply here. The real opening is the hash's own blind window (section 1
above), not a weakness in RSA itself -- no cryptographic break of any kind is
involved or needed. The original research log that found this (and several other,
less consequential false starts along the way) is not reproduced in this export;
only the final, verified conclusions are, in `docs/dfu-signature-scheme.md`.

## 5. Open questions

- The exact algorithm Bose's loader uses to reject stack/PS edits is unidentified. It
  is not any CRC variant or the 8-chain MD5 hash tried against the plain image. The
  leading hypothesis (an embedded vendor public key checked against a signed stack
  area) is unproven on this device. Source: docs/dfu-signature-scheme.md section 3.
- Whether Bose's own updater (vs. this project's tools) would behave any differently
  against the stack/PS doors is unknown -- only this project's probes have been tried.
- Whether a full-size (tens of KB) runtime partition-2 write actually commits safely,
  and what exactly happens if it is misaligned, is untested. Source: docs/partition-
  route.md "What makes it unsafe"; this is the single highest-risk open question in
  the project.
- Whether a collision or preimage attack against the 8-chain MD5 mode is feasible was
  examined only as a fallback once the blind-byte route proved sufficient; the
  assessment was never finished because it became unnecessary, and nothing published
  here depends on it. Source: docs/dfu-signature-scheme.md section 3.

## 6. Detailed knowledge (routing)

| doc | read it for | when |
|---|---|---|
| docs/dfu-signature-scheme.md | the final-state derivation of the signature scheme, the modulus recovery, and the blind-byte/digest-compensation mechanism | understanding the signing scheme in full |
| docs/cave-budget.md | the writable-word budget inside the filesystem's blind windows, as consumed by cave code specifically | sizing cave code against the write budget |
| docs/partition-route.md | the partition map, the external filesystem, the runtime partition-write mechanism and its risk | anything about partition 2 or a non-filesystem write |
| docs/FLASH-PROTOCOL.md | the mandatory gates for every flash (foreground, poll, readback, log) and the proven recovery procedure | before and during every flash, no exceptions |
| docs/POST-MORTEM-2026-10-04.md | exactly how unit 1 was lost, and the PS-key fact (`PSKEY_USB_VM_CONTROL=1`) that made it unrecoverable | before touching anything that could stop the VM app from running |
| docs/topics/hardware-and-firmware.md | what the writable bytes and the cave are actually used for | once the write mechanism itself is understood |

This is an archival research document; a few deeper research-folder citations that
appeared in the original (larger, private) project repository's copy of this page --
pointing at offline/strategy/firmware-study working notes not included in this public
export -- have been removed rather than left dangling. The table above, and
`docs/dfu-signature-scheme.md`, are this export's complete, self-contained account of
the signing mechanism.
