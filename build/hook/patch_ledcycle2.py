#!/usr/bin/env python3
"""Splits the LEDTICK block of ladder_ext.py into LEDTICK + LEDACT (the cave clusters are small; probe356 found no cluster for the whole block)."""
p = "build/hook/ladder_ext.py"
s = open(p, encoding="utf-8").read()
a = s.index("        for _v, _leds in ((1, (0,)), (2, (1,)), (3, (2,)), (4, (0, 1, 2))):\n            W(0x0517)")
b = s.index("        LBL(\"LT_NX\")\n")
old = s[a:b]
new = '''        W(0x0517); BSR("LEDACT")                                                  # the variant's action (its own block)
'''
s = s[:a] + new + s[b:]
# the LEDACT block goes before LEDTICK
anchor = "        # ---- LEDTICK: AL = the id 0x1000 | (v << 4) | t. slots: 3 id, 4 t, 5 v\n"
assert s.count(anchor) == 1
act = '''        # ---- LEDACT: AL = the variant v: 0 nothing, 1-3 one LED off, 4 LEDs 0-2 off, 5 the stock ids cancelled
        BLK(); LBL("LEDACT")
        W(0xF80B); W(0x0327)
        for _v, _leds in ((1, (0,)), (2, (1,)), (3, (2,)), (4, (0, 1, 2))):
            W(0x0317); W(*imm(_v, 0x84)); BR(0xF0, "LA_V%d" % _v)
            for _led in _leds:
                W(0x0014); W(0x0027); W(0x0010); W(*imm(_led, 0x14)); BSR(LEDC)  # LedConfigure(led, LED_ENABLE, 0)
            BR(0xE0, "LA_X")
            LBL("LA_V%d" % _v)
        W(0x0317); W(*imm(5, 0x84)); BR(0xF0, "LA_X")
        BSR("CSTOCK")
        LBL("LA_X")
        W(0xF80F)
'''
s = s.replace(anchor, act + anchor, 1)
open(p, "w", encoding="utf-8").write(s)
print("split done; removed", len(old), "chars from LEDTICK")
