#!/usr/bin/env python3
"""Adds PEEKCEN to build/hook/ladder_ext.py (probe359, owner 2026-10-27 "Yes go ahead": the READ-ONLY DSP PEEK census for the 48 kHz buffer question, docs/deep/material-2026-10-27/CU-dsp-peek-census.md).
Host-driven: the console `ev <20480+k>` (event 0x5000+k, k = 0..7) makes EVTX call PCGO, which sends KalimbaSendMessage(0x7AB2 PEEK, address k) to the running DSP. The reply (MESSAGE_FROM_KALIMBA, id 0x7AB2, words 1 and 3 = the low 16 bits of M[a] and M[a+1])
reaches PCREPLY, which schedules 12 octal digits (low digit first, 6 per word, 4.5 s apart from +12 s) as the census digit messages 0x900+d (SPEAKD speaks battery (d+1)*10 percent). Nothing is written to the DSP."""
p = "build/hook/ladder_ext.py"
s = open(p, encoding="utf-8").read()
assert "PEEKCEN" not in s
# 1. blocks
anchor = "    if G.get('STALL'):\n        # ---- probe334 STALL INSTRUMENT."
assert s.count(anchor) == 1
block = '''    if G.get('PEEKCEN'):
        ADDRS = (0x2A73, 0x2A75, 0x2A77, 0x2AAC, 0x0300, 0x03FE, 0x29E6, 0x28FE)
        # ---- PCGO: AL = the event 0x5000 + k: PEEK (0x7AB2) of DM[ADDRS[k]] (words: address low, address high 0)
        BLK(); LBL("PCGO")
        W(0xF80B); W(0x0327)
        W(0x0014); W(0x0027); W(0x0127); W(0x0227)
        for _k, _a in enumerate(ADDRS):
            W(0x0317); W(*imm(0x5000 + _k, 0x84)); BR(0xF0, "PG_%d" % (_k + 1))
            W(*imm(_a, 0x10)); BR(0xE0, "PG_S")
            LBL("PG_%d" % (_k + 1))
        LBL("PG_S")
        W(*imm(0x7AB2, 0x14)); BSR(KALMSG)
        W(0xF80F)
        # ---- PCWORD: AL = a 16-bit value, AH = the first delay (ms): six octal digits, low first, as the digit messages 0x900 + d through SDG; AL = the next delay
        BLK(); LBL("PCWORD")
        W(0xF80B); W(0x0427); W(0x0323)
        W(*imm(6, 0x14)); W(0x0527)
        LBL("PW_L")
        W(0x0417); W(0x07C4); W(*imm(0x900, 0x34)); BSR("SDG")
        W(0x0417); W(0x0009); W(0x03A4); W(0x0427)
        W(0x0517); W(*imm(0xFFFF, 0x34)); W(0x0527); W(0x0084); BR(0xF0, "PW_L")
        W(0x0317)
        W(0xF80F)
        # ---- PCREPLY: X = the message of the 0x7AB2 reply (X is untouched on entry): words 1 and 3 are spoken
        BLK(); LBL("PCREPLY")
        W(0xF80B)
        W(0x0316); W(0x0627)
        W(0x0116)
        W(*imm(12000, 0x10)); BSR("PCWORD")
        W(0x0327); W(0x0313); W(0x0617); BSR("PCWORD")
        W(0xF80F)
'''
s = s.replace(anchor, block + anchor, 1)
# 2. EVTX hook
a2 = "    BLK(); LBL(\"EVTX\")\n    W(0xF80B); W(0x0327)\n"
assert s.count(a2) == 1
s = s.replace(a2, a2 + '''    if G.get('PEEKCEN'):
        W(*imm(0x5000, 0x84)); BR(0xFC, "EV_Q")                                    # probe359: events 0x5000..0x5007 (console `ev 20480+k`) = a PEEK of address k (swallowed: the stock never sees them)
        W(*imm(0x5008, 0x84)); BR(0xF8, "EV_Q")
        BSR("PCGO"); W(0xF80F)
        LBL("EV_Q")
        W(0x0317)
''', 1)
# 3. census handler also for PEEKCEN
a3 = "    if G.get('CENSUS'):\n        # probe288: the census digit messages"
assert s.count(a3) == 1
s = s.replace(a3, "    if G.get('CENSUS') or G.get('PEEKCEN'):\n        # probe288: the census digit messages", 1)
# 4. the reply
a4 = "    W(0x101B); W(0x0016)                 # ld X,@(16,Y) the Message ; ld AL,@(0,X) the DSP message id\n"
assert s.count(a4) == 1
s = s.replace(a4, a4 + '''    if G.get('PEEKCEN'):
        W(*imm(0x7AB2, 0x84)); BR(0xF0, "XH_P")                                    # probe359: the PEEK reply (X still = the message)
        BSR("PCREPLY"); W(0xF80F)
        LBL("XH_P")
''', 1)
open(p, "w", encoding="utf-8").write(s)
print("patched PEEKCEN")
