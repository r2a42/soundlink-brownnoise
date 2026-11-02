# Rebuilding the writer (probe393) and the loop (probe428) from source

Purpose: the writer and the loop carry a 58,968-byte noise sample (the "payload"). This page says where it comes from and how to regenerate it byte for byte, so that probe393 and probe428 can be rebuilt from source like probe427.
Status / last verified: 2026-11-02. Regeneration run in this repository: every step below printed `ok` and the result was byte-identical to the shipped file. The three assemblers were run from a copy of this tree and their word lists were identical to the shipped `build/hook/probe393_words.json`, `probe427_words.json` and `probe428_words.json`.
Read next: `docs/clean-room-rebuild.md` (the other prerequisites), `docs/ring-buffer-fix.md`.

## What the payload is

`build/payload/g10/brown_48000_58968_seamfix160_f480_b.adpcm`: 58,968 bytes of IMA ADPCM (the dialect `tools/adpcm.py` implements), one 2.457 s loop of 48 kHz noise. It is synthetic: seeded Gaussian noise, shaped to a brown spectrum with a bass bell (+11 dB at 90 Hz) and a mid dip (-4 dB at 2.2 kHz), soft-limited, and encoded. No recording is involved. sha256 `6ea4564a776320feb0146840db0a15dc1367f52e7cef52b0144e28e7e8f95c36`.

## Regenerating it

```
python build/payload/build_payload.py --check    # instant: the shipped file has the pinned hash
python build/payload/build_payload.py            # about 3-4 minutes: regenerate and compare
```

Needs Python 3 with numpy and scipy; no vendor files and no device. The script runs `build/payload/gen/hx-coverage/mk48_lf.py` (which writes an intermediate into `build/payload/g8/`, git-ignored) and then three small steps, printing `ok` or `FAIL` after each, with a sha256 pinned at every stage:

| step | what | pinned sha256 (start) |
|---|---|---|
| 1 | `mk48_lf.py 48000` with `ROT=local DIP_DB=-10 DIP_HALF_MS=40`: seeded (seed 63), a rotation of the circular signal chosen so the loop join costs least in the bass, head offset so the first four bytes are cheap to compare | `8cc5b91f` |
| 2 | replace the last 47 bytes with the stored tail, so the decoder ends in state (0, 0) and the file loops exactly | `d233cbf0` |
| 3 | first byte `0x77` to `0xF7` (first nibble 7 to 15: same step-index delta, only the sign, a constant -22 LSB offset) so the first four bytes are `f7 ff 72 6b` | not pinned separately |
| 4 | `tools/seamfix.py` (cut 160, fade 480): fade to zero ahead of the speaker's early chunk cut | `6ea4564a` |

**One honest limit.** Step 2's tail was found by an offline dynamic-programming re-encode of the last 96 samples; the script that did it was not kept. Its result is stored as a 47-byte constant in `build/payload/build_payload.py`, and the script checks the properties that matter: only the last 41 bytes change, and the decoder ends in state (0, 0). Everything else is generated from the seed. Another encoder could produce a different, equally valid tail; it would not match the shipped hash.

## Rebuilding the images

The assemblers read the payload from `build/payload/g10/` (writer) and need the same prerequisites as probe427: the extracted stock firmware tree and the vendor ADK's SBC sources (`sbclib.py` reads `adk/4.4/app/src/kalimba/sbc/`), see `docs/clean-room-rebuild.md`. Then, from the repository root:

```
python build/hook/assemble_probe393.py     # writer: 957 cave words, plus 58,968 staged payload bytes
python build/hook/assemble_probe428.py     # loop: 2,106 cave words
python build/hook/assemble_probe427.py     # product: 2,108 cave words
```

Each writes `build/hook/probeNNN_words.json`; compare it with the shipped file. Add `--build` (needs the vendor packing tool from the ADK) to assemble the signed image, then check its sha256 against `docs/RELEASE-NOTES.md`. The `--build` step was not re-run for this page; the shipped patches (`build/patches/`) were built from these same inputs and apply to the stock file with the recorded hashes.

## Files

- `build/payload/build_payload.py`: the driver above.
- `build/payload/gen/hx-coverage/mk48_lf.py`, `build/payload/gen/bu-coverage/{mkcomp,mkloops,nsenc}.py`: the generator and its helpers, as used for the shipped payload. Two small edits for this export: the old analysis-scratch path in `mkcomp.py` is now an environment variable, and `mk48_lf.py` skips a final comparison with an older payload that is not part of this export.
- `build/payload/make_narrow_payload.py`: the partition-2 filesystem builder and staging plan the writer assembler loads.
- `tools/adpcm.py`, `tools/brownnoise.py`, `tools/seamfix.py`: the codec, the noise generator and the loop-end fix.
- `docs/deep/material-2026-10-13/c-sbc/sbclib.py`: needed by the loop and product assemblers (it reads the ADK).
