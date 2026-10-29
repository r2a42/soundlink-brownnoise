#!/usr/bin/env python3
"""probe184a: the tiny VALID ROFS write -- does partition-2 content reach the union filesystem?  (T08, 2026-10-12; [ROUND-3 NOTE: corrections to this docstring are in the comment block at the end of the file]
built offline, NOT flashed.)

STRATEGY.md section 4.1 "184a" (J-C3: verify.md V11 fix 3 wins over D11): ONE press, ONE erase of p2, a 2,800-byte
ROFS holding /brown.adpcm (flags 0x00, 2,532 bytes of the T07 recipe) and the official 11-byte /ext_version, then
the question the large write cannot ask first: FileFind from the ROOT -- found?  If not, mount p2 (1, 2, 1) and
look again.  It is the same cave as probe184 (assemble_probe184.py is the builder; this file only names the
variant), with 100 periods instead of 2,156 and the verdict branch of 184a:

  1. FileFind NowSpeakTTS / data_us, StreamFileSource.   2. SKIPN: 1,270 x (SourceSize >= 64, SourceDrop 64).
  3. LOOK before the erase: elements 18..21 of the map = "fsr_" else stop (p2 untouched).
  4. *** StreamPartitionOverwriteSink(1, 2) ***.   5. 100 x GATHER (claim 28, memmove 28 from map+18, flush 28,
  drop 64).   6. SourceClose, digest SKIP, SinkClose.   7. GetInfo STATE; FileFind(1, "brown.adpcm", 11); else
  PartitionMountFilesystem(1, 2, 1) and FileFind again.  ONE spoken id.

It also rehearses what probe184 will need, BEFORE its big erase: the 1,270-step walk over 81 KB of the file
source (a window that dries up speaks 0x37 with p2 untouched), the packing of SourceMap on a file source (0x38
with p2 untouched), and 100 claim/flush periods on a fresh p2 sink.  The same start period (1,270) is used in
both probes, so the first 100 periods of 184's span are exactly the span 184a stages.  (V03, round 3: that does NOT
carry an audibility result from 184a to 184 -- 184 stages 2,056 more periods, 29,505 words of region A against 721 --
and both images rewrite 12 of the 30 region-A header words; assemble_probe184a_58k.py / assemble_probe184_58k.py
start at period 1,320 and rewrite none.)

## THE STAGING AND THE IDS

  FIRST = 9 (data_us words 9..22 = bytes 18..45 of each 64-byte period), START_PERIOD = 1270: the staged span is
  data_us bytes 81,280..87,680 (E6-array tail, region-B tail, the start of region A).  The unit model of
  tools/promptmap.py says all 57 speech ids survive that span (start period 1: none), header untouched.  Model only.
  The ids below are speaking ids that the stock does not say with a laptop connected and the music paused and
  that no other probe table uses.

## FILES AND HASHES (python build/hook/assemble_probe184a.py --build; deterministic, rebuilt twice identical)

  payload   tools/brownnoise.py --rate 8000 --bytes 2532 --gen fft --loop --peak 0.985 --seed 63
            sha256 c14fee1747b246059b7db43edf61b28b945dcf8df781685aa28a91fe0f0f729b  (2532 = 28 x 100 - 268)
  ROFS      2,800 B, 100 periods, 0 pad bytes, sha256 0b49d7fe432e90d8febb03e3b9f7912dcf8dd331a83f68e686528330527ac960
  cave      341 words: 166 in the const window, 175 in the code region (14 of them the stub words)
            probe184a_words.json sha256 23776c54e3d8f6f07e932faf0ba4a94401a736d9aa6b2c353de8422fb8779ec0
  image     probe184a_brown.dfu sha256 ecd8ec6a7a2e0cc463ae48b59ac3198175ff9ec005426a27a5eae9bf74243b5b
            3,401 bytes differ from the official 3.0.3, all inside the fs area: 2,780 staged data_us bytes (of 2,800),
            595 cave bytes (of 682), 3 redirect bytes, 11 XOR-balance flips, 12 digest-compensation flips.
  edits     the redirect bytes 0x706bd=04 0x706bf=d4 0x706c1=d5; the cave words at area byte 0x6EA30 + 2 * word;
            the staged bytes at area byte 600 + 64 * (1270 + p) + 18 + j (p = 0..99, j = 0..27): 3,485 edits in all,
            more than one command line holds, so fsedit.build() is called in-process; probe184a_cmd.txt holds the rebuild.

## OWNER GATES AND ORDER (STRATEGY J-D2: yes to 184a alone, after 182 and 181p are recorded)

  182 (read-only window census) first if the owner wants the window answered without an erase -- but the pre-erase
  stops of this image (0x36 0x37 0x38) are the same census for the 81 KB walk and the packing, with p2 untouched.
  A second erase of p2 (the first clean one was probe140), geometry unmeasured, a 100-iteration loop never run, a
  staged data_us on the speaker until a stock one is flashed.  Press ONCE.

## THE PRESS (volume at the usual level, laptop connected, music PAUSED, USB unplugged after the readback)

  Centre LONG press once.  Wait for ONE spoken id (the erase takes seconds).  Do not pull power; press nothing else.
  Write the time from the press to the id.  Write the owner's words into docs/field-log.md before building anything.

## OUTCOME TABLE (no id is a stock prompt in this context; none is in a table of probes 139-143, 179-185, 187)

  0x12 "voice prompts on"          VALID, found FROM THE ROOT with no mount: p2 is in the union file system by itself.
                                   The large write is worth its first run; then ask J-D2 for 184.
  0x35 "ready to connect another device"  VALID, found only after the cave mounted p2: the union needs the mount
                                   (185a needs the 185b form).  Same decision as above.
  0x0b "press the bluetooth and volume down ... second bose device"  VALID, mount accepted, file STILL missing: either
                                   the bytes on p2 are not a valid ROFS (sink units) or p2 is not a member.  STOP
                                   before the large erase.
  0x3f "... to enter stereo mode"  PartitionMountFilesystem returned FALSE (RAW_SERIAL refusal reading): STOP; ranks 5
                                   and 6 of the strategy.
  0x15 "auto off enabled"          closed but STATE != VALID, or PartitionGetInfo refused: not confirmed.
  0x14 "auto off disabled"         the write did not complete: the p2 sink would not open, or a trap refused during
                                   the gather (SourceMap / claim / flush / window), or the digest was refused (the sink
                                   was closed; p2 INCOMPLETE).  Do not repeat the press unchanged.
  0x36 "select a bose speaker .."  BEFORE the erase: "fsr_" not at elements 18..21 (packed map / other offset / stock data_us).
  0x37 "select the bose headphones .." BEFORE the erase: SourceSize < 64 or SourceMap 0 during the walk.
  0x38 "select the bose product .." BEFORE the erase: FileFind / StreamFileSource refused.
  silence or garbled                the staged span is hit after all: wait 60 s, flash a stock-data_us image (the
                                   read-only partition census) -- p2 stays written.
  (0x36 0x37 0x38 differ by one noun; 0x14 / 0x15 by dis- / en-; 0x0b / 0x3f by their last words.)

## GATES RUN (offline)

  assemble: decode-verify OK; cavesim probe90 control AL = 0x000e; build/hook/gate_probe184.py probe184a: 24
  scenarios, 0 failed (every outcome above; the bytes written to p2 equal the ROFS; every opened source closed);
  tools/preflight.py probe184a OK; tools/caveguard.py SAFE.  No frame larger than enterl -8.  BUILT, NOT FLASHED.
"""
import os, runpy
# preflight.redirect_edits() reads this literal from THIS file; the engine asserts it equals the bsr3 from the hook
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assemble_probe184.py"),
               run_name="__main__", init_globals={"ENGINE_VARIANT": "probe184a"})

# ROUND-3 NOTE (2026-10-12, curator; comments only - the words and DFU hashes are unchanged).
# R02: the tiny valid ROFS cannot be mounted while p2 is table type 3 (the mount tests type 1), so this test can only report NOMOUNT/MISSING as designed
# (owner decision PD-20). V03: at start 1,270 the span rewrites 12 of 30 region-A header words; STATE VALID proves the commit only; a speech
# test must be added to the press page. The 1,320-start twin is probe184a_58k. See docs/deep/round3-2026-10-12/README.md (R3-C011, R3-C100, R3-C101).
