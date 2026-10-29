#!/usr/bin/env python3
"""One-off patcher: adds the LEDCYCLE diagnostic (probe356) to build/hook/ladder_ext.py.
LEDCYCLE: while the noise mode is ON, a tick chain (ids 0x1000 | (variant << 4) | sub, every 5 s, six ticks per variant = 30 s) tries six ways of
stopping the Bluetooth pairing light; at each variant boundary the tone is muted for 400 ms (an audible marker) and all LEDs are first enabled again.
  variant 0: nothing (the baseline blink)      variant 1: LedConfigure(0, LED_ENABLE, 0)   variant 2: LedConfigure(1, 0, 0)   variant 3: LedConfigure(2, 0, 0)
  variant 4: LEDs 0, 1 and 2 off               variant 5: the stock ids 0x6700..0x67FF of task 0x512 cancelled (CSTOCK) every tick
Owner observes the light (2026-10-27: 'I would also like the bluetooth pairing light to stop blinking')."""
import re

p = "build/hook/ladder_ext.py"
s = open(p, encoding="utf-8").read()
assert "LEDCYCLE" not in s

# 1. the blocks, placed right before the STALL instrument block
anchor = "    if G.get('STALL'):\n        # ---- probe334 STALL INSTRUMENT."
assert s.count(anchor) == 1
blocks = '''    if G.get('LEDCYCLE'):
        LEDC = ca.STUB['LedConfigure']
        # ---- LEDALL1: LedConfigure(led, LED_ENABLE, 1) for LEDs 0, 1, 2 (undo whatever a variant switched off)
        BLK(); LBL("LEDALL1")
        W(0xF80B)
        for _led in (0, 1, 2):
            W(*imm(1, 0x14)); W(0x0027); W(0x0010); W(*imm(_led, 0x14)); BSR(LEDC)
        W(0xF80F)
        # ---- LEDSTART: AL = the mode (1 ON, 0 OFF), preserved: ON starts the variant tick chain (id 0x1000, first tick 5 s ahead)
        BLK(); LBL("LEDSTART")
        W(0xF80B); W(0x0327)
        W(0x0084); BR(0xF4, "LS_X")
        W(*imm(0x1000, 0x14)); W(*imm(5000, 0x10)); BSR(L['RSEND'])
        LBL("LS_X")
        W(0x0317); W(0xF80F)
        # ---- LEDTICK: AL = the id 0x1000 | (v << 4) | t. slots: 3 id, 4 t, 5 v
        BLK(); LBL("LEDTICK")
        W(0xF80B); W(0x0327)
        BSR(L['PEEKMODE']); W(0x0084); BR(0xF0, "LT_ON")
        BSR("LEDALL1")                                                            # the mode is OFF: LEDs back on, the chain ends here
        W(0xF80F)
        LBL("LT_ON")
        W(0x0317); W(*imm(0xF, 0xC4)); W(0x0427)                                  # t = id & 0xF
        W(0x0317); W(0x04A4); W(*imm(0xF, 0xC4)); W(0x0527)                       # v = (id >> 4) & 0xF
        W(0x0417); W(0x0084); BR(0xF0, "LT_NB")                                   # t != 0: not a variant boundary
        BSR("LEDALL1")                                                            # boundary: every LED enabled again,
        BSR("MUTE")                                                               # the tone muted (an audible marker),
        BSR(L['CANCELANY']); W(0x0084); BR(0xF4, "LT_NB")                         # and the level poll put back 400 ms ahead
        W(*imm(G['LEVEL_BASE'] - 1, 0x34)); W(*imm(400, 0x10)); BSR(L['RSEND'])
        LBL("LT_NB")
        for _v, _leds in ((1, (0,)), (2, (1,)), (3, (2,)), (4, (0, 1, 2))):
            W(0x0517); W(*imm(_v, 0x84)); BR(0xF0, "LT_V%d" % _v)
            for _led in _leds:
                W(0x0014); W(0x0027); W(0x0010); W(*imm(_led, 0x14)); BSR(LEDC)  # LedConfigure(led, LED_ENABLE, 0)
            BR(0xE0, "LT_NX")
            LBL("LT_V%d" % _v)
        W(0x0517); W(*imm(5, 0x84)); BR(0xF0, "LT_NX")
        BSR("CSTOCK")                                                             # variant 5: the stock ids 0x6700..0x67FF
        LBL("LT_NX")
        W(0x0417); W(*imm(1, 0x34)); W(0x0427)                                    # t += 1
        W(*imm(6, 0x84)); BR(0xF0, "LT_SD")
        W(0x0014); W(0x0427)                                                      # t = 6 -> 0 and the next variant
        W(0x0517); W(*imm(1, 0x34)); W(0x0527)
        W(*imm(6, 0x84)); BR(0xF0, "LT_SD")
        W(0x0014); W(0x0527)                                                      # v = 6 -> 0
        LBL("LT_SD")
        W(0x0517); W(0x04A0); W(0x0437); W(*imm(0x1000, 0x34))                    # id' = 0x1000 + (v << 4) + t
        W(*imm(5000, 0x10)); BSR(L['RSEND'])
        W(0xF80F)
'''
s = s.replace(anchor, blocks + anchor, 1)

# 2. EXTH dispatch: before the FREEEDGE branch
anchor2 = "    if G.get('FREEEDGE'):\n        W(*imm(0x8026, 0x84)); BR(0xF0, \"XF_1\")"
assert s.count(anchor2) == 1
disp = '''    if G.get('LEDCYCLE'):
        W(*imm(0x1000, 0x84)); BR(0xFC, "XL_1")                                   # ids 0x1000..0x105F are the LED-variant ticks
        W(*imm(0x1060, 0x84)); BR(0xF8, "XL_1")
        BSR("LEDTICK"); W(0xF80F)
        LBL("XL_1")
'''
s = s.replace(anchor2, disp + anchor2, 1)

# 3. MODETOGX: start the chain after the mode is known
anchor3 = "        if G.get('DEEPSLEEP'): BSR(\"DSLEEP\")"
assert s.count(anchor3) == 1
s = s.replace(anchor3, "        if G.get('LEDCYCLE'): BSR(\"LEDSTART\")                                  # probe356: AL = the mode, preserved\n" + anchor3, 1)
open(p, "w", encoding="utf-8").write(s)
print("patched ladder_ext.py for LEDCYCLE")
