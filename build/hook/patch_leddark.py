#!/usr/bin/env python3
"""Adds LEDDARK to build/hook/ladder_ext.py (probe357, owner 2026-10-27: 'I would like the bluetooth pairing light to stop blinking since the primary use case is sleep noise').
LEDDARK: at the press ON (mode ON) the cave calls the stock fn_19092 with AL = 0 once: it applies the default LED words and every light (battery, pairing) goes dark until the next stock
power-on (hardware: console 'ld 3' alone darkened all lights, they stayed dark through noise stop/start and a USB replug; a power cycle restored them)."""
p = "build/hook/ladder_ext.py"
s = open(p, encoding="utf-8").read()
assert "LEDDARK" not in s
anchor = "    if G.get('STALL'):\n        # ---- probe334 STALL INSTRUMENT."
assert s.count(anchor) == 1
block = '''    if G.get('LEDDARK'):
        # ---- LEDDARK: AL = the mode (1 ON, 0 OFF), preserved. ON: the stock LED routine fn_19092(0) once (every light dark until the next stock power-on)
        BLK(); LBL("LEDDARK")
        W(0xF80B); W(0x0327)
        W(0x0084); BR(0xF4, "LD_X")
        W(0x0014); BSR(0x19092)
        LBL("LD_X")
        W(0x0317); W(0xF80F)
'''
s = s.replace(anchor, block + anchor, 1)
anchor3 = "        if G.get('DEEPSLEEP'): BSR(\"DSLEEP\")"
assert s.count(anchor3) == 1
s = s.replace(anchor3, "        if G.get('LEDDARK'): BSR(\"LEDDARK\")                                    # probe357: AL = the mode, preserved\n" + anchor3, 1)
open(p, "w", encoding="utf-8").write(s)
print("patched LEDDARK")
