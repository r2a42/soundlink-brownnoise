#!/usr/bin/env python3
"""probe329 = probe328 with the busy poll back at 10 ms (PAYLOAD_BUSY_POLL 10, PAYLOAD_FIRST_POLL 2423 = the 2,457 ms chunk minus 34 ms as probe315; owner 2026-10-24: "could we move from 6ms down to 10ms and see if the processor is just overwhelmed?" - the occasional click remains). Original docstring: probe328 = probe327 (fine ladder, silent bottom) plus BLUETOOTH OFF while the noise plays (owner 2026-10-24: more clicks with a device connected; he never wants music and noise together): at the centre long press ON and every 10 s while ON, SCANSYNC drops every connected device with the stock helper fn_09445(1) (when fn_09157 reports one) and turns page and inquiry scan off; at OFF it turns them back on when nothing is connected. Original docstring: probe327 = probe326 with a SILENT level 0 and three quiet levels below the old bottom: 15 levels (ids 0x40..0x4E): shift = level/4 (base 0), ratio = 30 + 7 * (level % 4), level 0 sends ratio 0; default level 10 (= the old default gain). Owner 2026-10-24: volume did not go to zero at level 0. Original docstring: probe326 = probe324 (batch B inert stubs) with the FINE ladder: 11 levels of 1.5 dB (owner 2026-10-24: smaller volume steps), default level 6 (= the old level 3). PROBE_FINE: shift = base 1 + level/4, ratio byte = 30 + 7 * (level % 4) = 30, 37, 44, 51: the same total gain as the old 3 dB ladder at every second level (old level L = new level 2L). Original docstring: probe318 = probe316 (48 kHz, 6 ms busy poll) with the first-four-bytes check of the bass-calm payload written by writer probe317 (FIRST4 77 FF 72 6B). Original docstring: probe316 = probe315 with a 6 ms busy poll (PAYLOAD_BUSY_POLL 6, PAYLOAD_FIRST_POLL 2448 = the 2,457 ms chunk minus 9 ms as probe311; owner order 2026-10-22 after the 48 kHz seam was audible only sometimes; the cavesim rule R5 floor is lowered to 6 for THIS image only, GATE_POLL_FLOOR=6). Original docstring: probe315 = probe313 at 48 kHz (PAYLOAD_RATE 48000, PAYLOAD_FIRST_POLL 2423 = the 2,457 ms chunk minus 34 ms as the 24 kHz pair, FIRST4 77 FF 72 6B of the 48 kHz payload written by writer probe314; owner order 2026-10-22: full-rate version). Original docstring: probe313 = probe312 plus TIMERS (cancel the stock TM3 link-lost and TM2 idle power-off timers on every rebuild; owner timed the 300 s power-off 2026-10-22). Original docstring: probe312 = probe310 with NOPURGE (docs/deep/material-2026-10-19/CN-no-purge-probe312.md; CL-fable-review.md R1). PRODUCT ONLY: payload and every constant as probe310 (PAYLOAD_FIRST_POLL 4880, PAYLOAD_BUSY_POLL 10, RATE 24000, RELEASE_MS 16000, FIRST4 77 FF 7A 37, the compensated 24 kHz payload written by writer probe306). One change: the rebuild after a chunk end sends NO 0x1072 (the tone-buffer purge) while the LIGHT-OK flag (message id 0x2A) is pending: it pokes the level and holds the audio-busy word, nothing else. The first rebuild after a start, after an OFF, and every 60 s (FG timer, id 0x2B) it sends the full gate as probes 300-310 did, which heals a rate/level change by a stock 0x1072. The cavesim rule R5 floor is lowered to 10 for THIS image's gates only (GATE_POLL_FLOOR=10; owner approval 2026-10-21 for probe310, carried here); no other gate is changed. Built offline 2026-10-22; NOT flashed."""
import os
os.environ.setdefault("SPAN", "80000"); os.environ.setdefault("CAPF", "0.7"); os.environ.setdefault("RANDASSIGN", "1"); os.environ.setdefault("SEEDS", "60000")   # as probe296 (layout seed 1336)
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
AYBATCH = 'AB'
AYPOOL = True
EVGUARD = True
EVGCHAIN = True
G5ZAP = True
NOPURGE = True
TIMERS = True
PAYLOAD_RATE = 48000
PAYLOAD_FIRST_POLL = 2423
PAYLOAD_BUSY_POLL = 10
PAYLOAD_RELEASE_MS = 16000
PAYLOAD_FIRST4 = (0x77, 0xFF, 0x72, 0x6B)
PROBE_DEFLEV = 10
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
