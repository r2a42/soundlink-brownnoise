#!/usr/bin/env python3
"""Slims LEDCYCLE: five variants (0 baseline, 1-3 one LED off, 4 LEDs 0-2 off), no CSTOCK variant, no level re-poll at the boundary."""
p = "build/hook/ladder_ext.py"
s = open(p, encoding="utf-8").read()
old1 = '''        W(0x0317); W(*imm(5, 0x84)); BR(0xF0, "LA_X")
        BSR("CSTOCK")
        LBL("LA_X")'''
assert old1 in s
s = s.replace(old1, '        LBL("LA_X")', 1)
old2 = '''        BSR(L['CANCELANY']); W(0x0084); BR(0xF4, "LT_NB")                         # and the level poll put back 400 ms ahead
        W(*imm(G['LEVEL_BASE'] - 1, 0x34)); W(*imm(400, 0x10)); BSR(L['RSEND'])
'''
assert old2 in s
s = s.replace(old2, "", 1)
old3 = '''        W(0x0517); W(*imm(1, 0x34)); W(0x0527)
        W(*imm(6, 0x84)); BR(0xF0, "LT_SD")
        W(0x0014); W(0x0527)                                                      # v = 6 -> 0'''
assert old3 in s
s = s.replace(old3, '''        W(0x0517); W(*imm(1, 0x34)); W(0x0527)
        W(*imm(5, 0x84)); BR(0xF0, "LT_SD")
        W(0x0014); W(0x0527)                                                      # v = 5 -> 0''', 1)
open(p, "w", encoding="utf-8").write(s)
print("slimmed")
