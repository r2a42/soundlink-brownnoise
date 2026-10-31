#!/usr/bin/env python3
"""probe428 = probe387 (the payload LOOP product: 48 kHz ADPCM loop from partition 2, STARTWAIT, CANCEL670B, SILENTDROP) + PWRREL2 (the loop's form of probe427's power-off fix; +27 program words; the cave word COUNT stays 2106 because EXT code is placed over fill words that are counted anyway). Owner 2026-10-31 ("1 yes": rebuild the loop with the cap and the power-off fix). Built OFFLINE, NOT flashed; design, evidence and the owner's test plan: docs/deep/probe428-loop-2026-10-31.md.
WHAT (build/hook/ladder_ext.py, flag PWRREL2; every other image rebuilds byte-identical: probe387 and probe427 words checked):
 (1) the power-off event 0x4002 (EVTX, mode ON: after the OFF path MODETOGX; mode OFF: directly) calls RELFREE instead of probe427's unconditional RELEASE0: StreamKalimbaSink(3) = 0 (no DSP) or TransformFromSink(ksink) = 0 (port 3 free) -> RELEASE0 (SetAudioBusy(0) only if the word is our task 0xBA3C); a transform still on port 3 (a chunk in flight, or a stock tone) -> nothing, the REL timer (16 s) stays as the backstop. probe427's RELEASE0 is NOT safe here: in the loop a 2.46 s chunk is in flight at almost every power-off, and the hold is what keeps a parked stock prompt (the power-on announcement = a TTS KalimbaLoad over our DSP) away from a DSP that our transform still feeds (CLAUDE.md rule 4, FACTS N033).
 (2) the free edge of the LAST chunk (MESSAGE_STREAM_DISCONNECT 0x8026 in EXTH, FREEEDGE; no poll pending) with the mode OFF (PEEKMODE = 0: a press-OFF or a power-off happened) also calls RELFREE: the hold drops when the chunk has ended (at most about 2.5 s after the OFF) instead of 16 s later. Mode ON (STARTWAIT waiting, a restart pending): unchanged.
 VOLUME CAP: NOT applied (PROBE_NLEV stays 15, PROBE_DEFLEV 10). The ladder code (POKE) is the same as the generator's, so PROBE_NLEV 12 would lower the loop's top by the same 4.74 dB (model; 4.6 dB measured on probe402); but the loop's default is level 10 (the generator's is 6) and its top (level 14) was heard by the owner on probe312/probe327 as "not uncomfortable" / "reached as before", while the generator's level 14 was "4.5 dB too loud": the payload is the quieter source at the same ladder level (about 6 dB by the defaults; probe380 at level 10 measured +1.1 dB over the loop at level 10). With NLEV 12 the loop would keep ONE step above its default. The doc has the table; a cap is a one-line change (PROBE_NLEV) if the owner's ear wants one.
EXPECTED on hardware (unit 2 only: the loop needs the 48 kHz payload in partition 2; units 3/4 hold factory language packs): as probe387 for the press, the noise and the volume; NEW: a POWER press while the noise plays stops it within 1 s and a POWER press 3 s later powers on normally ("battery N%" within about 2-3 s; before: silent until 16 s after the power-off, "two more presses with a gap"); after a centre press-OFF the stock prompts are free as soon as the last chunk ends (about 2.5 s) instead of 16 s.
RISKS: (1) the 0x8026 free edge is the firmware's dispose message for our chunk's stream (proven on hardware since probe337 as the poll trigger); RELFREE re-reads TransformFromSink before writing, so a late edge keeps the hold; (2) a power-off inside the first chunk after a stock tone (rate latch: that chunk may run at 8 kHz for 14.7 s) keeps the hold until the chunk's free edge or REL; (3) the EXT layout moved (seeded search): all words re-gated on the new image.
PRESS PLAN (owner, unit 2, after the flash and the readback under docs/FLASH-PROTOCOL.md; rollback probe387 c0e3efc8..., then probe427 (generator)): (1) centre long press, listen 30 s: noise within 2-5 s, steady, lights dark; (2) POWER press while the noise plays, then ONE POWER press within 3 s: PASS = noise stops within 1 s, then "battery N%" within about 3 s and the LED bar; FAIL = silence for 5 s (hands off 40 s, note the time of any late prompt); (3) control: POWER off / on with no noise; (4) centre ON, centre OFF, POWER off within 5 s, POWER on within 3 s: normal power-on; (5) centre ON, POWER off, wait 30 s, POWER on: normal; (6) 5 min run, volume up to the top (level 14, as before) and down, a phone connecting while the noise plays, OFF, later an idle power-off. Spoken ids: none new (the cave speaks nothing on these paths).
Base: probe387 (probe385 + SILENTDROP): the 48 kHz payload loop product (on unit 2 2026-10-29, four hands-free cases passed)."""
import os
os.environ.setdefault("SPAN", "80000"); os.environ.setdefault("CAPF", "0.7"); os.environ.setdefault("RANDASSIGN", "1"); os.environ.setdefault("SEEDS", "60000")   # as probe387 / probe296
NEWFEAT = True
DSPGUARD = True
IDGUARD = True
CONSUME = True
CLEARDAC = True
FAILOFF = True
OFFLOOP = True
CANCELALL = True
STAGE = 5
VARIANT = 'P'
ALLFILL = True
AYBATCH = 'ABCD'
AYPOOL = True
EVGUARD = True
EVGCHAIN = True
G5ZAP = True
NOPURGE = True
TIMERS = True
STARTWAIT = True
SILENTDROP = True
CANCEL670B = True
PWRREL2 = True
PAYLOAD_RATE = 48000
NOFILLER = True
LEDDARK = True
TMREARM = True
RING512 = True
PAYLOAD_FIRST_POLL = 5000
PAYLOAD_BUSY_POLL = 9
PAYLOAD_RELEASE_MS = 16000
PAYLOAD_FIRST4 = (0xF7, 0xFF, 0x72, 0x6B)
PROBE_DEFLEV = 10
PROBE_NOBUSYPOKE = True
FREEEDGE = True
PROBE_FINE_ZERO = True
PROBE_FINE = True
PROBE_NLEV = 15
PROBE_SHIFT_BASE = 0
PROBE_FINE_R0 = 30
SCAN = True
BTDROP = True
AYMAIN = True
PROBE_GAIN_N = 15
PROBE_RATIO_EVEN = 0x0F
PROBE_RATIO_ODD = 0x15
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast); the first three are the hook (ladder_core.py asserts them), the rest are the button-table row 26 bytes
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5"), ("0xe90b8", "0x02"), ("0xe90ba", "0x04"), ("0xe90be", "0x04"), ("0xe90c0", "0x02"), ("0xe90c1", "0x00")]
import os
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder_core.py"), encoding="utf-8").read(), __file__, "exec"))
