#!/usr/bin/env python3
"""probe275 = TEST build of probe274's product plus power-off OFF, mute, yield to a streaming phone, 4-s watchdog (variant v: the connect event 0x4753 stands in for the press) -- was: probe274 = the product (variant P, probe270) plus two owner-report fixes of 2026-10-18, NO new cave words:
  G4 (boot wait): the button-table row 26 (centre DOUBLE in state 9, event 0x4012; the only centre row whose seven words are all DFU-writable) becomes
      centre LONG press (type 2) in states {1 Connectable, 18 ManualConnect} -> event 0x4004, so the press works from power-on, before the stock prompt
      "mobile device not found - ready to connect" (docs/deep/material-2026-10-18/K2-boot-state-trigger.md R1). Five blind bytes at code words 0x3D344, 0x3D345, 0x3D347, 0x3D348.
      Lost: the centre double press while a three-way call is on hold. Row 38 (states 2, 3, 13) is untouched, so no press is sent twice.
  G1 (level): the default level is 0 (-6 dB: shift 2) and the cold start's DAC gain index is 12 (-9 dB, +6 dB): the cold noise is unchanged, the warm (Bluetooth) noise is 6 dB quieter.
Press plan: docs/field-log.md, entry probe274."""
import os
os.environ.setdefault("SPAN", "80000"); os.environ.setdefault("CAPF", "0.7")
NEWFEAT = True
STAGE = 5
VARIANT = 'v'
ALLFILL = True
PROBE_DEFLEV = 0
PROBE_GAIN_N = 12
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast); the first three are the hook (ladder_core.py asserts them), the rest are the button-table row 26 bytes
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5"), ("0xe90b8", "0x02"), ("0xe90ba", "0x04"), ("0xe90be", "0x04"), ("0xe90c0", "0x02"), ("0xe90c1", "0x00")]
import os
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder_core.py"), encoding="utf-8").read(), __file__, "exec"))
