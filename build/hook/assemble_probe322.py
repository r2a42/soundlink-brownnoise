#!/usr/bin/env python3
"""probe322 = the probe320 press-free WRITER (right payload, sha256 8cc5b91f..., first 4 bytes 77 ff 72 6b) with DISTINCT spoken ids (owner, 2026-10-23: "pick a different prompt so it's not so confusing ... say something distinct so we know it worked"):
success after a real write = 0x24 "switching call" (owner choice D, 2026-10-23: the long 0x11 phrase was also confusing on the first boot); p2 already held the payload (nothing erased) = 0x16 "english" (one short word). The first choice, 0x20 "unmuted" / 0x1f "muted", was rejected by the owner as too alike. The failure ids are unchanged (0x12 time limit, 0x19 write failed, 0x3A, 0x17, 0x28, 0x3B).
The stock boot says "battery 100%"; the writer no longer does. Everything else is assemble_probe320.py. Gate: WRITER_ID_WRITTEN_HEX=24 WRITER_ID_PRESENT_HEX=16 WRITER_WORDS=probe322 python build/hook/gate_probe320.py"""
import os
# literals read by tools/preflight.py and tools/caveguard.py (they parse this file with ast): the same as assemble_probe320.py
SYNTH_TRAPS = [0xD3]
SYNTH_CONTROLS = []
REDIRECT_EDITS = [("0x706bd", "0x04"), ("0x706bf", "0xd4"), ("0x706c1", "0xd5")]
os.environ.setdefault("WRITER_ID_WRITTEN", "0x24")
os.environ.setdefault("WRITER_ID_PRESENT", "0x16")
exec(compile(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assemble_probe320.py"), encoding="utf-8").read(), __file__, "exec"))
