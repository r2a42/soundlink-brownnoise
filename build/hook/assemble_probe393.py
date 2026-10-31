#!/usr/bin/env python3
"""probe393 = probe391 (fixed press-free writer: guard before the present check, ONE fixed 45 s tick, DROPBT = Bluetooth drop + stock-idle gate before the write) + MUTEBOOT (owner request 2026-10-29: "I do still want the bluetooth disconnect change"; hardware 14:41-14:58: with the DROPBT writer a device connected at boot still left the writer phrase unheard, the drop at the 45 s tick is too late). the 48 kHz payload g10 writer (the real writer, ids 0x24 written / 0x16 present).
WHY: in the WRITER image the stock "Connected to <spelled name>" prompt at boot uses voice-data letters that the staged payload overwrote; it wedges the speech path and the output stays muted, so the writer phrase is never heard with a device connected. With nothing connected the stock speaks nothing wrong and the phrases are strong and clear (rms 950-1400).
WHAT (WRITER_MUTEBOOT=1, build/hook/assemble_probe320.py; new EXT block MBEV, message id 0x18): the first event after boot arms a 60 s boot-mute message; EVERY event (AUTOARM -> MBEV) that finds it pending clears bit 13 of @0x570 (the stock voice-prompt enable, RAM only, only when set: SILENTDROP mechanism) and re-sends it 60 s ahead, so the stock speaks nothing at boot (no battery prompt, no Connected-to, no ready-to-connect, hence no wedge). DBFC (after the drop and the stock-idle gate, BEFORE the writer speaks) cancels the boot mute and puts the bit back (SILRST); the 35 s restore message does it again and turns the scans on; if the boot mute ever expires (60 s after the last event, the tick never got through) DBX restores the bit.
RISKS: the stock is silent for the first ~45 s after power-on (no battery prompt) in this image; if the user had voice prompts OFF the restore turns the bit on in RAM until the next boot; the stock may re-load @0x570 between events (not seen); a device that reconnects between the drop and the write is not dropped again.
PRESS PLAN (hands-free, unit 2): python tools/bug_repro_run.py TAG TOTAL "STEPS" --addr <laptop-bluetooth-address> --out <dir> [--no-bt] [--norestart] [--noconnect]. Present case (p2 already holds this payload): DFU restart, pw 1 at +22 s, laptop connected; EXPECT: no speech during the first ~45 s, the laptop link dropped about 45 s after the boot event, then ONE strong phrase (rms about 1000) a few seconds after the drop. Write case (p2 holds the OTHER payload, flash straight after the other writer, --norestart, pw 1 at +5 s): the same, phrase 0x24 Switching call, then the loop product confirms p2. Nothing connected: same but without the drop. Decode: python -I <scratchpad>/segs.py <wav> 0 TOTAL; only events of 0.5 s or longer and rms above about 600 count as a word.
"""
import os
os.environ.setdefault("EXTSEEDS", "3000")
os.environ.setdefault("WRITER_DEBOUNCE_MS", "0"); os.environ.setdefault("WRITER_FIXED_MS", "45000"); os.environ.setdefault("WRITER_DROPBT", "1"); os.environ.setdefault("WRITER_MUTEBOOT", "1")
os.environ.setdefault("WRITER_ID_WRITTEN", "0x24")
os.environ.setdefault("WRITER_ID_PRESENT", "0x16")
os.environ.setdefault("WRITER_PAYLOAD_FILE", "build/payload/g10/brown_48000_58968_seamfix160_f480_b.adpcm")
os.environ.setdefault("WRITER_PAYLOAD_SHA", "6ea4564a776320feb0146840db0a15dc1367f52e7cef52b0144e28e7e8f95c36")
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast): the same as assemble_probe320.py
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assemble_probe320.py"), encoding="utf-8").read(), __file__, "exec"))
