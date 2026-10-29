#!/usr/bin/env python3
"""Which const-pool zero runs are SAFE to put a cave in?

probe130 crashed the speaker on boot. Every one of its 234 cave words was zero in the
official image and inside a DFU blind window -- the two conditions the probe assemblers
check -- and it still corrupted live data, because **zero does not mean unread**. A
zero-filled gap inside a live table passes both checks and is still read at runtime.

The specific kill: probe130 wrote const data 0x827B..0xC307; `fn_0aaa1` at code 0x0aaa5
does `ld AL,#0x8280`, and `fn_27bab` then ships two words from there as a message payload.
Those two words had become opcode bytes.

`docs/cave-budget.md:58-61` warned about exactly this ("'never loaded' means never loaded
by an immediate address... any region taken from here must..."), but the assembler's rule
was never taught it. This tool is that rule, so it can be asserted instead of remembered.

Usage:
    python tools/caveguard.py                 # audit every zero run in the const pool
    python tools/caveguard.py probe130        # check one probe's words
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'xapvm'))

CODE_WORDS = 236514
CONST_A = 0x39BE2
CONST_BASE = 0x7400
DISASM = os.path.join(ROOT, 'build/analysis/full-disasm.txt')
# The window the long-proven probes used, and the budget docs/cave-budget.md records.
SAFE_WINDOW = (0x3E200, 0x3E400)

# The SECOND region class (2026-10-08, docs/deep/code-region-plan.md): dead CODE in the
# AVRCP-browse block, listed EXPLICITLY function by function -- not a rule, not a range to
# grow. SAFE_WINDOW above is unchanged. Each entry: function start -> (end, stub address,
# stub words). A probe may write a word here only if (a) it lies inside one of these
# functions, (b) both of its bytes are DFU-writable (tools/disasm.py blind_byte), and (c)
# the probe ALSO writes that function's stub, exactly, so that if the static analysis were
# wrong and the function were called, it returns 0 instead of running cave code:
#   writable entry:            0014 00e2 = ld AL,#0 ; rts            (as stock fn_323ca)
#   first writable after enterl: 0014 leavel -N, with the function's own N.
# fn_2346c is deliberately ABSENT: its first writable word is 17 words into stock code and a
# `beq` before it bypasses any stub there, so a safe exit is not provable.
# 2026-10-16 (owner: "expand the cave by enough to have comfortable working room"): fn_233f0
# and fn_23632 are ADDED with a stub placed at the first writable FULL instruction word (not
# the operand word that opens the writable run), where every path through the stock prologue
# must pass (docs/deep/material-2026-10-13/J26-cave-expansion.md): fn_233f0 at 0x233fe
# (the `bne` after `cmp AH,#0xff`; the `beq` at 0x233fa lands on 0x233ff = the stub's
# `leavel`), fn_23632 at 0x2363e (the `bne` after `cmp AL,#0xc00`; the `beq` at 0x23638
# jumps straight to the stock exit 0x23665). Both stubs are `ld AL,#0 ; leavel -N`.
CODE_REGION = {
    0x2331e: (0x23344, 0x2331e, (0x0014, 0x00E2)),   # AvrcpBrowseSetPlayerRequest
    0x23344: (0x2337C, 0x23344, (0x0014, 0x00E2)),   # AvrcpBrowseChangePathRequest
    0x2337C: (0x233F0, 0x2337D, (0x0014, 0xF50F)),   # (unnamed), enterl -11 at entry
    0x2349C: (0x234FD, 0x2349D, (0x0014, 0xFA0F)),   # AvrcpBrowseSearchRequest, enterl -6
    0x234FD: (0x23543, 0x234FD, (0x0014, 0x00E2)),   # AvrcpBrowseSetPlayerResponse
    0x23543: (0x23565, 0x23543, (0x0014, 0x00E2)),   # AvrcpBrowseChangePathResponse
    0x23565: (0x235A9, 0x23565, (0x0014, 0x00E2)),   # AvrcpBrowseGetItemAttributesResponse
    0x233F0: (0x2346C, 0x233FE, (0x0014, 0xF90F)),   # (unnamed), enterl -7; stub at +14 (see above)
    0x23632: (0x23666, 0x2363E, (0x0014, 0xFA0F)),   # (unnamed), enterl -6; stub at +12 (see above)
    # 2026-10-17 (owner: noise with no Bluetooth device needs a DSP loader, which needs room; the owner approved
    # expanding via more dead code on 2026-10-16): twelve more dead functions from the 2026-10-08 survey
    # (survivors4.json, zero bsr/branch/TaskData/switch references, re-checked by build/analysis/space3/recheck*.py:
    # no outside branch or bsr, no immediate equal to a low16 of an address inside). Each stub sits on the first
    # writable full instruction after `enterl -N` with NO branch between the entry and it (checked by script,
    # build/analysis/space3/screen.py), so every path through the stock prologue passes it: `ld AL,#0 ; leavel -N`.
    # docs/deep/material-2026-10-13/J27-cave-expansion-2.md.
    0x1DDA4: (0x1DE0F, 0x1DDA5, (0x0014, 0xF10F)),   # fn_1dda4, 49 writable, enterl -15; stub at +1
    0x375B8: (0x37601, 0x375BD, (0x0014, 0xF80F)),   # fn_375b8, 32 writable, enterl -8; stub at +5
    0x2CE02: (0x2CE45, 0x2CE03, (0x0014, 0xF60F)),   # fn_2ce02, 31 writable, enterl -10; stub at +1
    0x3685A: (0x3688C, 0x3685D, (0x0014, 0xFA0F)),   # fn_3685a, 28 writable, enterl -6; stub at +3
    0xE5AB: (0xE5EC, 0xE5BD, (0x0014, 0xFE0F)),   # fn_e5ab, 28 writable, enterl -2; stub at +18
    0x12E37: (0x12E66, 0x12E3D, (0x0014, 0xF90F)),   # fn_12e37, 23 writable, enterl -7; stub at +6
    0x163BC: (0x163E4, 0x163BD, (0x0014, 0xFE0F)),   # fn_163bc, 21 writable, enterl -2; stub at +1
    0x2F5C4: (0x2F5E9, 0x2F5C5, (0x0014, 0xF90F)),   # fn_2f5c4, 19 writable, enterl -7; stub at +1
    0x210A7: (0x210D9, 0x210A8, (0x0014, 0xF20F)),   # fn_210a7, 18 writable, enterl -14; stub at +1
    0x275A8: (0x275D1, 0x275A9, (0x0014, 0xF30F)),   # fn_275a8, 17 writable, enterl -13; stub at +1
    0x23D5D: (0x23D7F, 0x23D5E, (0x0014, 0xF60F)),   # fn_23d5d, 16 writable, enterl -10; stub at +1
    0x27982: (0x279A3, 0x27983, (0x0014, 0xF80F)),   # fn_27982, 15 writable, enterl -8; stub at +1
    # 2026-10-17, second batch (probe236; same method, build/analysis/space3/recheck3.py and recheck4.py: no outside
    # branch or bsr, no look-alike immediate; not yet confirmed inert on hardware on their own, probe235 covered the first twelve):
    0x38D79: (0x38D8E, 0x38D7E, (0x0014, 0xFA0F)),   # fn_38d79, 14 writable, enterl -6; stub at +5
    0x36D58: (0x36D6B, 0x36D5D, (0x0014, 0xFA0F)),   # fn_36d58, 14 writable, enterl -6; stub at +5
    0x25C14: (0x25C2B, 0x25C1D, (0x0014, 0xFB0F)),   # fn_25c14, 14 writable, enterl -5; stub at +9
    0x23E99: (0x23EB2, 0x23E9D, (0x0014, 0xFB0F)),   # fn_23e99, 14 writable, enterl -5; stub at +4
    0x22B7D: (0x22B90, 0x22B7E, (0x0014, 0xFB0F)),   # fn_22b7d, 14 writable, enterl -5; stub at +1
    0xDC92: (0xDCAD, 0xDC9D, (0x0014, 0xFE0F)),   # fn_dc92, 14 writable, enterl -2; stub at +11
    0x360E6: (0x36105, 0x360E7, (0x0014, 0xF70F)),   # fn_360e6, 13 writable, enterl -9; stub at +1
    0x27BF0: (0x27C0A, 0x27BFD, (0x0014, 0xF50F)),   # fn_27bf0, 13 writable, enterl -11; stub at +13
    0x4BC3: (0x4BE3, 0x4BC4, (0x0014, 0xFE0F)),   # fn_4bc3, 14 writable, enterl -2; stub at +1
    0x437C: (0x438E, 0x437D, (0x0014, 0xFA0F)),   # fn_437c, 14 writable, enterl -6; stub at +1
    0x27613: (0x2762A, 0x2761D, (0x0014, 0xF70F)),   # fn_27613, 13 writable, enterl -9; stub at +10
    0x35B1F: (0x35B36, 0x35B20, (0x0014, 0xFA0F)),   # fn_35b1f, 12 writable, enterl -6; stub at +1
    0x3531F: (0x35334, 0x35320, (0x0014, 0xFC0F)),   # fn_3531f, 12 writable, enterl -4; stub at +1
    0x22BD2: (0x22BE9, 0x22BDD, (0x0014, 0xF90F)),   # fn_22bd2, 12 writable, enterl -7; stub at +11
    0x22B36: (0x22B49, 0x22B3D, (0x0014, 0xFB0F)),   # fn_22b36, 12 writable, enterl -5; stub at +7    # fn_12f4f (rejected in J26 for a single stub): TWO stubs cover every path: the fall-through after `beq +3` at 0x12f5c reaches 0x12f5d, the taken branch lands on 0x12f5f.
    # Stub words 0x12f5d..0x12f60 = [ld AL,#0 ; leavel -12] twice (entry A runs the first pair, entry B the second). 68 writable words; no outside reference (J26 / recheck.py).
    0x12F4F: (0x12FE9, 0x12F5D, (0x0014, 0xF40F, 0x0014, 0xF40F)),   # fn_12f4f, 68 writable, enterl -12
    # third batch (batch3.py: provable stub, no outside refs; fn_27b33 left out: its brxl bound was flagged in space-survey.md):
    0x6E5D: (0x6E69, 0x6E5E, (0x0014, 0xFE0F)),   # fn_6e5d, 12 writable, enterl -2; stub at +1
    0x37780: (0x37790, 0x37781, (0x0014, 0xFC0F)),   # fn_37780, 11 writable, enterl -4; stub at +1
    0x2BE60: (0x2BE73, 0x2BE61, (0x0014, 0xF70F)),   # fn_2be60, 11 writable, enterl -9; stub at +1
    0x12660: (0x1266F, 0x12661, (0x0014, 0xFD0F)),   # fn_12660, 11 writable, enterl -3; stub at +1
    0x170C1: (0x170D7, 0x170C2, (0x0014, 0xFD0F)),   # fn_170c1, 10 writable, enterl -3; stub at +1
    0x38EFB: (0x38F06, 0x38EFD, (0x0014, 0xFD0F)),   # fn_38efb, 9 writable, enterl -3; stub at +2
    0x23DC2: (0x23DDD, 0x23DC3, (0x0014, 0xF70F)),   # fn_23dc2, 9 writable, enterl -9; stub at +1
    0x1293D: (0x12946, 0x1293E, (0x0014, 0xFC0F)),   # fn_1293d, 9 writable, enterl -4; stub at +1
    0x27AE3: (0x27AFD, 0x27AE4, (0x0014, 0xF40F)),   # fn_27ae3, 8 writable, enterl -12; stub at +1
    0x25C03: (0x25C14, 0x25C04, (0x0014, 0xFB0F)),   # fn_25c03, 8 writable, enterl -5; stub at +1
    0xDA63: (0xDA73, 0xDA64, (0x0014, 0xFD0F)),   # fn_da63, 8 writable, enterl -3; stub at +1
    # 2026-10-18 fourth batch (probe276 confirms them inert on their own): six functions the 2026-10-17 re-check had dropped on the rule 'an immediate equals a low16 of an address inside'.
    # build/analysis/space3/recheck5.py lists every such immediate with its context: each is a data-space operand, not a code pointer (a compare with a message id 0x110a, an and-mask 0xf307, string pointers 0x8ea0/0x8dc5.. loaded
    # for a debug-string call, a const-table index 0x9cc9, a sample-rate select 0x2b11), so none can enter the function. No outside bsr/branch/TaskData/switch reference (survivors4.json). Stubs from screen.py (no branch before the stub).
    0x210D9: (0x2110B, 0x210DF, (0x0014, 0xF30F)),   # fn_210d9, 28 writable, enterl -13; stub at +6
    0x8E9D: (0x8ECB, 0x8E9E, (0x0014, 0xE70F)),   # fn_8e9d, 28 writable, enterl -25; stub at +1
    0x2F2FF: (0x2F334, 0x2F300, (0x0014, 0xFC0F)),   # fn_2f2ff, 26 writable, enterl -4; stub at +1
    0x9CC0: (0x9CF1, 0x9CC1, (0x0014, 0xFA0F)),   # fn_9cc0, 25 writable, enterl -6; stub at +1
    0x38DC4: (0x38DF3, 0x38DC5, (0x0014, 0xFB0F)),   # fn_38dc4, 21 writable, enterl -5; stub at +1
    0x32B05: (0x32B2C, 0x32B06, (0x0014, 0xFB0F)),   # fn_32b05, 20 writable, enterl -5; stub at +1
    # fifth batch (2026-10-18; recheck5.py contexts: debug-string pointers / a table index; the look-alikes fn_35b5f, fn_35bda, fn_127dd and fn_128dc store a TaskData-shaped record and stay excluded):
    0x2BF58: (0x2BF6B, 0x2BF5E, (0x0014, 0xF70F)),   # fn_2bf58, 14 writable, enterl -9; stub at +6
    0x8D10: (0x8D2F, 0x8D1E, (0x0014, 0xF90F)),   # fn_8d10, 14 writable, enterl -7; stub at +14
    0x2FE4: (0x3002, 0x2FE5, (0x0014, 0xFC0F)),   # fn_2fe4, 12 writable, enterl -4; stub at +1
    0x176D9: (0x176E7, 0x176DD, (0x0014, 0xFE0F)),   # fn_176d9, 10 writable, enterl -2; stub at +4
    0x38E7F: (0x38E88, 0x38E80, (0x0014, 0xFE0F)),   # fn_38e7f, 9 writable, enterl -2; stub at +1
}

# 2026-10-19 (AY, docs/deep/material-2026-10-19/AY-dead-pool-extension.md): the AY pool, a SEPARATE dict so that the 59 entries above
# (and every wrapper that derives its fill from them) behave exactly as before. A probe opts in with AYBATCH = 'A' (ladder_core.py).
# Entry shape differs from CODE_REGION on one point (L1b F1): the words [function start, stub) stay STOCK (the enterl and the
# prologue that the stub's `leavel -N` closes); the fill starts after the stub words. check() asserts this for these entries.
# Not yet confirmed inert on hardware: batch A is the stub-only probe297.
CODE_REGION_AY = {
    # batch A (AY section 6)
    0x38A24: (0x38A90, 0x38A25, (0x0014, 0xF70F)),   # fn_38a24, enterl -9, stub at +1 (I2S plugin CsrSetVolumeI2SDevice_SSM2518, only caller fn_387c6)
    0x1DF56: (0x1DFAB, 0x1DF5D, (0x0014, 0xF70F)),   # fn_1df56, enterl -9, stub at +7 (engine A, only caller fn_1dda4)
    0x12EE8: (0x12F34, 0x12EE9, (0x0014, 0xFA0F)),   # fn_12ee8, enterl -6, stub at +1 (only caller fn_12f4f)
    # batch B (AY section 3.2; hand-cleared; stub-only image probe324, NOT yet confirmed inert on hardware)
    0x384F6: (0x385AA, 0x384FD, (0x0014, 0xF90F)),   # fn_384f6, enterl -7, stub at +7 (I2S plugin StreamAudioSink/SinkConfigure, 0 callers)
    0x1EE80: (0x1EF5C, 0x1EE81, (0x0014, 0xEB0F)),   # fn_1ee80, enterl -21, stub at +1 (second phrase reader, 0 callers)
    0x2CD5B: (0x2CDB1, 0x2CD5D, (0x0014, 0xF50F)),   # fn_2cd5b, enterl -11, stub at +2 (hfp_min_cfm, 0 callers)
    # batch C (owner approval 2026-10-28, AskUserQuestion "Batches C + D"; AY section 3.3 and 5: fn_2fde2, second-order proof rated well-supported; stub-only inertness image probe381, NOT yet confirmed inert on hardware)
    0x2FDE2: (0x2FF84, 0x2FDE3, (0x0014, 0xF00F)),   # fn_2fde2, enterl -16, stub at +1 (418 words, only caller fn_2fdd1, a TaskData handler named by 17 const triples that nothing ever dispatches)
    # batch D (owner approval 2026-10-28; AY section 3.4: 16 small rule-A dead functions, 0 unresolved hits; stub-only inertness image probe381, NOT yet confirmed inert on hardware)
    0x38474: (0x384B5, 0x3847F, (0x0014, 0xF80F)),   # fn_38474, enterl -8 (I2S plugin, 0 callers)
    0x384B5: (0x384E9, 0x384BD, (0x0014, 0xFA0F)),   # fn_384b5, enterl -6 (I2S plugin, 0 callers)
    0x387C6: (0x387FF, 0x387C7, (0x0014, 0xFC0F)),   # fn_387c6, enterl -4 (callers fn_384b5, fn_384e9, both dead roots)
    0x37808: (0x37842, 0x37809, (0x0014, 0xF90F)),   # fn_37808, enterl -7 (obexPutReq, caller fn_3759a root)
    0x20A48: (0x20A78, 0x20A49, (0x0014, 0xF40F)),   # fn_20a48, enterl -12 (GattReliableWriteExecuteRequest, caller fn_211d5 root)
    0x211D5: (0x211FF, 0x211DE, (0x0014, 0xF50F)),   # fn_211d5, enterl -11 (root, 0 callers)
    0x20616: (0x20654, 0x2061D, (0x0014, 0xEC0F)),   # fn_20616, enterl -20 (GattReadLongCharacteristicValueRequest, caller fn_210a7 in CODE_REGION)
    0x2777C: (0x27794, 0x2777D, (0x0014, 0xF80F)),   # fn_2777c, enterl -8 (ConnectionDmBleSetAdvertiseEnable, caller fn_0747c root)
    0xE58B:  (0xE5AB,  0xE59D,  (0x0014, 0xFE0F)),   # fn_0e58b, enterl -2 (root, 0 callers)
    0x2C716: (0x2C737, 0x2C71D, (0x0014, 0xF00F)),   # fn_2c716, enterl -16 (ConnectionRfcommPortNegRequest, root)
    0x2F9B9: (0x2F9CB, 0x2F9BD, (0x0014, 0xFB0F)),   # fn_2f9b9, enterl -5 (callers fn_2f9cb, fn_2f9d0, roots)
    0x1FB3B: (0x1FB58, 0x1FB3F, (0x0014, 0xFD0F)),   # fn_1fb3b, enterl -3 (callers fn_1fdec, fn_1fe32, roots)
    0x2FC5C: (0x2FC6B, 0x2FC5F, (0x0014, 0xFE0F)),   # fn_2fc5c, enterl -2 (amp chain 0x701b..0x701e, caller fn_2fd5e root)
    0x378DE: (0x378F9, 0x378DF, (0x0014, 0xFA0F)),   # fn_378de, enterl -6 (obexDeleteReq, caller fn_375b8 in CODE_REGION)
    0x2BE19: (0x2BE2C, 0x2BE1F, (0x0014, 0xF70F)),   # fn_2be19, enterl -9 (caller fn_08d10 in CODE_REGION)
    0x1DEDD: (0x1DEE9, 0x1DEDE, (0x0014, 0xFE0F)),   # fn_1dedd, enterl -2 (engine A, caller fn_1de74 child of fn_1dda4)
}
AY_BATCHES = {'A': (0x38A24, 0x1DF56, 0x12EE8), 'B': (0x384F6, 0x1EE80, 0x2CD5B),
              'AB': (0x38A24, 0x1DF56, 0x12EE8, 0x384F6, 0x1EE80, 0x2CD5B),
              'C': (0x2FDE2,), 'D': (0x38474, 0x384B5, 0x387C6, 0x37808, 0x20A48, 0x211D5, 0x20616, 0x2777C, 0xE58B, 0x2C716, 0x2F9B9, 0x1FB3B, 0x2FC5C, 0x378DE, 0x2BE19, 0x1DEDD),
              'ABCD': (0x38A24, 0x1DF56, 0x12EE8, 0x384F6, 0x1EE80, 0x2CD5B) + (0x2FDE2,) + (0x38474, 0x384B5, 0x387C6, 0x37808, 0x20A48, 0x211D5, 0x20616, 0x2777C, 0xE58B, 0x2C716, 0x2F9B9, 0x1FB3B, 0x2FC5C, 0x378DE, 0x2BE19, 0x1DEDD),
              'CD': (0x2FDE2,) + (0x38474, 0x384B5, 0x387C6, 0x37808, 0x20A48, 0x211D5, 0x20616, 0x2777C, 0xE58B, 0x2C716, 0x2F9B9, 0x1FB3B, 0x2FC5C, 0x378DE, 0x2BE19, 0x1DEDD)}      # AB: batch B confirmed inert by ear on probe324 (owner 2026-10-24: consistent level, no odd behaviour); code may now be placed there


def region_entry(f):
    """(end, stub address, stub words) of a function start in CODE_REGION or CODE_REGION_AY."""
    return CODE_REGION[f] if f in CODE_REGION else CODE_REGION_AY[f]


def region_fn(a):
    for f, (end, _, _) in CODE_REGION.items():
        if f <= a < end:
            return f
    for f, (end, _, _) in CODE_REGION_AY.items():
        if f <= a < end:
            return f
    return None


def region_writable(a):
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import disasm
    return (disasm.blind_byte(disasm.AREA0 + 2 * a)
            and disasm.blind_byte(disasm.AREA0 + 2 * a + 1))


def const_addr(a):
    return CONST_BASE + (a - CODE_WORDS)


def word_of(data_addr):
    return CODE_WORDS + (data_addr - CONST_BASE)


def zero_runs(code, lo, hi, minlen):
    runs, i = [], lo
    while i < hi:
        if code[i] == 0:
            j = i
            while j < hi and code[j] == 0:
                j += 1
            if j - i >= minlen:
                runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


def immediate_loads():
    """Every immediate value an instruction loads, with the site that loads it.

    Only immediates that fall inside the const data window can be pointers into it. A load
    is evidence the region is live even if the pool entry itself is zero.
    """
    pat = re.compile(r'^\s*(0x[0-9a-f]+):.*#(0x[0-9a-f]{4})\b')
    hits = {}
    with open(DISASM, encoding='utf-8', errors='replace') as f:
        for line in f:
            m = pat.match(line)
            if not m:
                continue
            v = int(m.group(2), 16)
            if CONST_BASE <= v <= 0xD39A:
                hits.setdefault(v, []).append(int(m.group(1), 16))
    return hits


def audit(reach=64):
    """Report every zero run and whether anything points into it.

    `reach` is how far past a loaded pointer a record is assumed to extend: a load of a
    base address makes the words after it live too, which is the indexed/computed case
    docs/cave-budget.md warns cannot be seen directly.
    """
    import xapvm
    code = xapvm.load_words(
        os.path.join(ROOT, 'firmware/bose/extracted/internal_fs/vm.app'))[0x18:]
    loads = immediate_loads()
    runs = zero_runs(code, CONST_A, CONST_A + 24475, 16)
    print('%d zero runs of >=16 words in the const pool\n' % len(runs))
    print('%-22s %-20s %6s  %s' % ('code words', 'data addrs', 'words', 'verdict'))
    safe_total = 0
    rows = []
    for a, b in runs:
        d0, d1 = const_addr(a), const_addr(b - 1)
        direct = [v for v in loads if d0 <= v <= d1]
        near = [v for v in loads if d0 - reach <= v < d0]
        in_safe = SAFE_WINDOW[0] <= a and b <= SAFE_WINDOW[1]
        # The WINDOW is the decisive test, because it is empirical: ~40 flashes have
        # written these runs without incident, including probe129 hours ago. The read scan
        # is advisory only -- it has known false positives, since a 16-bit immediate that
        # happens to land in 0x7400..0xD39A may be an ordinary number rather than a
        # pointer. probe129 wrote into two runs this scan calls "read" and was fine.
        note = ('%d direct load(s)' % len(direct) if direct
                else 'pointer within %d below' % reach if near else 'no loads seen')
        if in_safe:
            verdict = 'SAFE - proven window   [%s]' % note
            safe_total += b - a
        else:
            verdict = 'OUTSIDE proven window -> DO NOT USE   [%s]' % note
        rows.append((a, b, d0, d1, verdict, direct))
        print('%-22s %-20s %6d  %s'
              % ('0x%05x..0x%05x' % (a, b), '0x%04X..0x%04X' % (d0, d1), b - a, verdict))
        for v in direct[:3]:
            print('%44s loaded at %s' % ('', ', '.join('0x%05x' % s for s in loads[v][:3])))
    print('\nwords in runs marked SAFE: %d' % safe_total)
    print('docs/cave-budget.md records 197 WRITABLE words in the proven window')
    print('(writable = 29 bytes of every 64 are DFU-editable, so < words above)')
    return rows


def check(probe):
    """Fail if any of a probe's cave words sits in a run something reads."""
    import xapvm
    code = xapvm.load_words(
        os.path.join(ROOT, 'firmware/bose/extracted/internal_fs/vm.app'))[0x18:]
    loads = immediate_loads()
    w = sorted(int(k, 16) for k in
               json.load(open(os.path.join(ROOT, 'build/hook/%s_words.json' % probe))))
    bad = []
    for a in w:
        d = const_addr(a)
        for v in loads:
            if v <= d <= v + 64:
                bad.append((a, d, v, loads[v][0]))
                break
    words = {int(k, 16): v & 0xFFFF for k, v in
             json.load(open(os.path.join(ROOT, 'build/hook/%s_words.json' % probe))).items()}
    region = [a for a in w if region_fn(a) is not None]
    bad = [x for x in bad if region_fn(x[0]) is None]      # pointer proximity: const only
    outside = [a for a in w if not (SAFE_WINDOW[0] <= a < SAFE_WINDOW[1])
               and region_fn(a) is None]
    unwritable = [a for a in region if not region_writable(a)]
    nostub = []
    for f in sorted({region_fn(a) for a in region}):
        _, sa, sw = region_entry(f)
        if tuple(words.get(sa + k) for k in range(len(sw))) != sw:
            nostub.append(f)
    # AY entries only: the words [start, stub) must be absent or stock (L1b F1: the enterl the stub's leavel closes must run)
    ayfn = sorted({region_fn(a) for a in region} & set(CODE_REGION_AY))
    ay_prologue = []
    for f in ayfn:
        for a in range(f, CODE_REGION_AY[f][1]):
            if a in words and words[a] != code[a]:
                ay_prologue.append(a)
    win = [a for a in w if SAFE_WINDOW[0] <= a < SAFE_WINDOW[1]]
    print('%s: %d words: %d in the const window, %d in the code region'
          % (probe, len(w), len(win), len(region)))
    if win:
        print('  const window data 0x%04X..0x%04X'
              % (const_addr(min(win)), const_addr(max(win))))
    print('  words outside the proven window 0x%05X..0x%05X AND outside CODE_REGION: %d'
          % (SAFE_WINDOW[0], SAFE_WINDOW[1], len(outside)))
    if region:
        print('  code-region words not DFU-writable: %d' % len(unwritable))
        print('  code-region functions written WITHOUT their exact stub: %s'
              % ([hex(f) for f in nostub] or 'none'))
    if ayfn:
        print('  AY-pool functions %s: prologue words [start, stub) changed from stock: %d'
              % ([hex(f) for f in ayfn], len(ay_prologue)))
    print('  words within 64 of a loaded pointer: %d' % len(bad))
    for a, d, v, site in bad[:8]:
        print('     a=0x%05x data 0x%04X <- pointer 0x%04X loaded at 0x%05x' % (a, d, v, site))
    # Outside-the-window is the decisive failure; the pointer proximity count is
    # advisory and is printed for evidence, not used as the verdict.
    ok = not outside and not unwritable and not nostub and not ay_prologue
    print('  %s' % ('SAFE -- every word inside the proven window or the listed, stubbed '
                    'code region' if ok
                    else 'UNSAFE -- DO NOT FLASH (outside %d, unwritable %d, unstubbed %d)'
                         % (len(outside), len(unwritable), len(nostub))))
    return ok


# ---------------------------------------------------------------------------------------
# ATTESTATION: does every instruction FORM we emit actually appear in Bose's firmware?
#
# probe131 crashed on hardware while passing decode-verify, cavesim and every other gate.
# Its gate emitted a **two-word `ble`** (prefix + 0x28). Counting all 191,224 instructions
# of vm.app: every conditional branch has an attested two-word form EXCEPT `ble`, which
# Bose uses 68 times and never prefixes. If 0x28 does not accept a prefix on this core, the
# hardware ignores the prefix word and executes `ble -5` -- a backward jump into the cave
# prologue, which is exactly "crash but no wedge".
#
# Neither the assembler nor the emulator could catch it: they share one opcode table, so
# both folded the prefix and both agreed. Only Bose's own usage falsifies it. Hence this
# check, which compares each emitted (opcode, length) against the firmware's own census.
# ---------------------------------------------------------------------------------------

BRANCH_OPS = {0x20: 'bgt', 0x24: 'bge', 0x28: 'ble', 0x2C: 'bcz',
              0xF0: 'bne', 0xF4: 'beq', 0xF8: 'bcc', 0xFC: 'bcs',
              0xE0: 'bra', 0x9C: 'bsr',
              0xE1: 'bra@',   # J-T12/J-T3: the indirect jump that ends the trap tail (Bose: once, 0x295)
              0x0E: 'ldXH'}   # round 3: `ld XH,@(n,Y)`, the 4th tail word. Not a branch; it joins this census because
                              # it is another form Bose uses (0x294, and 0x3960f in decoded data) and a cave must
                              # not invent a 2-word spelling of it (attest counts it on cave words only)


def bose_census(code):
    """How many times Bose uses each (opcode, word length) in its own code."""
    import xapvm
    cen = {}
    for a, op, v, ln in xapvm.decode(code[:CODE_WORDS]):
        if op in BRANCH_OPS:
            cen[(op, ln)] = cen.get((op, ln), 0) + 1
    return cen


def attest(probe):
    """Fail if the cave emits an instruction form Bose's firmware never uses."""
    import xapvm
    code = xapvm.load_words(
        os.path.join(ROOT, 'firmware/bose/extracted/internal_fs/vm.app'))[0x18:]
    cen = bose_census(code)
    w = {int(k, 16): v & 0xFFFF for k, v in
         json.load(open(os.path.join(ROOT, 'build/hook/%s_words.json' % probe))).items()}
    patched = list(code)
    for a, v in w.items():
        patched[a] = v
    lo, hi = min(w), max(w)
    bad, used = [], {}
    for a, op, v, ln in xapvm.decode(patched, fold_zero=False):
        # [lo, hi] spans every stock word BETWEEN cave clusters (FS-C55: for a cave in both the
        # code region and the const window it counts stock branches in between). That window is kept
        # for the older forms so their printed counts and verdicts are unchanged; the new `ld XH`
        # form (28 historical probes would otherwise fail on decoded const data) is counted on
        # CAVE words only.
        if lo <= a <= hi and op in BRANCH_OPS and (op != 0x0E or a in w):
            n = cen.get((op, ln), 0)
            used[(op, ln)] = used.get((op, ln), 0) + 1
            if n == 0:
                bad.append((a, op, ln))
    print('%s: branch forms emitted in the cave' % probe)
    for (op, ln), k in sorted(used.items()):
        n = cen.get((op, ln), 0)
        print('   %-4s %d-word  x%-3d  Bose uses this form %5d time(s)%s'
              % (BRANCH_OPS[op], ln, k, n, '   <-- UNATTESTED' if n == 0 else ''))
    for a, op, ln in bad:
        print('   FAIL a=0x%05x emits a %d-word %s, which Bose NEVER does'
              % (a, ln, BRANCH_OPS[op]))
    print('   %s' % ('all emitted forms are attested in Bose firmware' if not bad
                     else 'UNATTESTED FORM -- do not flash'))
    return not bad

# ---------------------------------------------------------------------------------------
# SYNTHESISED TRAP STUBS (J-T12 spec, implemented here by J-T3, 2026-10-12): a cave calling a
# trap that has NO stub in vm.app.
#
# A stock stub is `enterl -3 ; ld X,#n ; bra 0x291`. Reaching 0x291 from the cave would need a
# 3-word `bra`, which Bose NEVER emits (census: bra 1-word 6968, 2-word 1230, 3-word 0), so the
# cave carries the five tail words itself: `enterl -3 ; ld X,#n ; st X,@(0,Y) ; ld X,@0xfffc ;
# st X,@(-1,Y) ; ld XH,@(-1,Y) ; bra @0xfffd`. The tail is the ADK's own common_trap_code
# (proven, T12 section 2). NEVER RUN ON HARDWARE: every such stub is declared by the probe
# (`SYNTH_TRAPS = [..]` / `SYNTH_CONTROLS = [..]` in its assembler) and listed by
# attest_trap_stubs. Whether the speaker accepts the tail executed from the cave is a
# hypothesis; whether the stack dispatcher reaches trap n is T01/T12 well-supported (bound 0xE2).
#
# The recogniser lives HERE (not in tools/xapvm/xapvm.py as the T12 diff had it) because J-T3
# owns this file; cavesim.py imports it from here. Corrections owed to xapemu are in T03.
# ---------------------------------------------------------------------------------------

import caveasm as _ca                                      # noqa: E402  (round 3: the stub words live in caveasm)
COMMON_TAIL_A = _ca.COMMON_TAIL_A                          # 0x291
COMMON_TAIL = _ca.COMMON_TAIL                              # (0x002B, 0xFC19, 0xFF2B, 0xFF0E, 0xFDE1)
ENTERL_3 = _ca.ENTERL_3                                    # 0xFD0B
SYNTH_MAX_TRAP = 0xE2    # the stack VM trap dispatcher faults above this (stack-disasm.txt:101480-101487, cmp X,#0xe2)
# Trap slots whose (M, A) pair is (0, 0) in the stack trap table: UNIMPLEMENTED (T01 C2, proven by
# tools/trapcat.py; the dispatcher's argument form 0 is the fault path, R02 E11). A stub for one of these
# passed the gate before round 3 (V01 D2: dispatcher behaviour on a (0,0) entry untraced).
UNIMPLEMENTED_TRAPS = frozenset({0x2C, 0x2F, 0x96, 0xAF, 0xC0, 0xC1, 0xCA, 0xD9, 0xDA, 0xDB})
# the relative branch / call opcodes whose target is a + ln - 1 + v (xapemu.py, validated on 2-word
# branches and 3-word bsr over Bose's whole image)
REL_BRANCH_OPS = frozenset({0x9C, 0xE0, 0xE4, 0xE8, 0xEC, 0xF0, 0xF4, 0xF8, 0xFC,
                            0x20, 0x24, 0x28, 0x2C})


def _sext8(b):
    return b - 256 if b & 0x80 else b


def check_common_tail(code):
    """Fail loudly if the image's own words at 0x291..0x295 are not the known tail."""
    got = tuple(code[COMMON_TAIL_A:COMMON_TAIL_A + 5])
    if got != COMMON_TAIL:
        raise ValueError('words at 0x291..0x295 are %s, not the known trap tail'
                         % [hex(w) for w in got])


def _ld_x_imm(code, i):
    """`ld X,#n` starting at raw word i (prefix chain then opcode 0x18) -> (n, next index)."""
    v, j = 0, i
    while j - i < 3 and (code[j] & 0xFF) == 0 and code[j] != 0:
        v = (v + _sext8(code[j] >> 8)) << 8
        j += 1
    if (code[j] & 0xFF) != 0x18:
        return None
    return (v + _sext8(code[j] >> 8)) & 0xFFFF, j + 1


def find_cave_stubs(code, spans):
    """Trap stubs synthesised INSIDE cave spans -> {addr: (trap, kind, nwords)}.

    Raw-word pattern match (not a decode sweep, so a data word cannot shift the alignment).
    kind 'inline': enterl -3 ; ld X,#n ; the five tail words.
    kind 'bra'   : enterl -3 ; ld X,#n ; [0000] ; bra -> 0x291 (any length; the 3-word form is
                   unattested in Bose's code, so attest_trap_stubs rejects it, but the model
                   still recognises it rather than mis-running it)."""
    if isinstance(spans, tuple) and len(spans) == 2 and not isinstance(spans[0], (tuple, list)):
        spans = [spans]
    out = {}
    if not any(code[i] == ENTERL_3 for lo, hi in spans for i in range(lo, hi + 1)):
        return out                                   # cheap exit for every legacy cave
    check_common_tail(code)
    for lo, hi in spans:
        for i in range(lo, hi + 1):
            if code[i] != ENTERL_3:
                continue
            r = _ld_x_imm(code, i + 1)
            if r is None:
                continue
            n, j = r
            if tuple(code[j:j + 5]) == COMMON_TAIL:
                out[i] = (n, 'inline', j + 5 - i)
                continue
            k = j + 1 if code[j] == 0x0000 else j
            v, m = 0, k
            while m - k < 3 and (code[m] & 0xFF) == 0 and code[m] != 0:
                v = (v + _sext8(code[m] >> 8)) << 8
                m += 1
            if (code[m] & 0xFF) == 0xE0 and (m + v + _sext8(code[m] >> 8)) == COMMON_TAIL_A:
                out[i] = (n, 'bra', m + 1 - i)
    return out


def tail_uses(code, spans):
    """Every address in the spans where the five tail words occur in a row."""
    if isinstance(spans, tuple) and len(spans) == 2 and not isinstance(spans[0], (tuple, list)):
        spans = [spans]
    return [i for lo, hi in spans for i in range(lo, hi + 1)
            if tuple(code[i:i + 5]) == COMMON_TAIL]


def stray_tail_ops(code, spans, stubs):
    """Skeptic M4 of T12: decoded INSTRUCTION STARTS with opcode 0x0E (`ld XH,@(n,Y)`) or 0xE1
    (`bra @abs`) inside the cave spans that are not the 0x0E/0xE1 words of a recognised
    canonical stub. A near-copy of the tail (the native cells 0xFFF4/5, one word changed) is
    neither a stub nor the five-word tail, but it still ends in an indirect jump. Returns a
    sorted list of (addr, opcode). The raw-word prefilter keeps legacy caves free of the
    whole-image decode."""
    import xapvm
    if isinstance(spans, tuple) and len(spans) == 2 and not isinstance(spans[0], (tuple, list)):
        spans = [spans]
    if not any((code[i] & 0xFF) in (0x0E, 0xE1) for lo, hi in spans for i in range(lo, hi + 1)):
        return []
    ok = set()
    for a, (_n, kind, ln) in stubs.items():
        if kind == 'inline':
            ok |= {a + ln - 2, a + ln - 1}           # the ld XH and the bra @ of the tail
    out = []
    for a, op, v, ln in xapvm.decode(code, fold_zero=False):
        if op in (0x0E, 0xE1) and any(lo <= a <= hi for lo, hi in spans) and a not in ok:
            out.append((a, op))
    return sorted(out)


def tail_branches(code, spans):
    """V01 D1 (severity: brick). Relative branches and calls INSIDE the cave spans whose target is
    one of the five tail words 0x291..0x295, as [(addr, opcode, target)]. A stock stub reaches the
    tail with `bra +1`; a cave `bsr` or `bra` to it is a form no gate used to look at (a 3-word bsr
    is Bose's commonest call form, 7,473 uses): `bsr` leaves the link in X, the tail stores X as the
    trap number, so the id is a code address far above the dispatcher bound 0xE2 and the trap faults
    (T01 E6, T12 skeptic M2: the VM-fault path can leave the application dead with no USB). Target =
    a + ln - 1 + v, the rule xapemu.py validated on every multi-word branch of vm.app."""
    import xapvm
    if isinstance(spans, tuple) and len(spans) == 2 and not isinstance(spans[0], (tuple, list)):
        spans = [spans]
    lo_t, hi_t = COMMON_TAIL_A, COMMON_TAIL_A + len(COMMON_TAIL) - 1
    out = []
    for a, op, v, ln in xapvm.decode(code, fold_zero=False):
        if op in REL_BRANCH_OPS and any(lo <= a <= hi for lo, hi in spans):
            t = (a + ln - 1 + v) & 0x3FFFF
            if lo_t <= t <= hi_t:
                out.append((a, op, t))
    return sorted(out)


def synth_stub_words(trap):
    """`enterl -3 ; ld X,#trap ; <tail>`: a stock stub with its `bra 0x291` replaced by the
    tail itself. Emit as ONE W(*words) item, then BSR(label) to call it like a stock stub.
    Generated, never hand-written (the project's own lesson). The generator is
    caveasm.synth_stub_words (round 3, T12 S4); this name stays for the callers of 2026-10-12."""
    return _ca.synth_stub_words(trap)


def synth_declared(probe, name='SYNTH_TRAPS', path=None):
    """SYNTH_TRAPS / SYNTH_CONTROLS = [..] from the probe's assembler (as
    preflight.redirect_edits reads REDIRECT_EDITS). SYNTH_TRAPS: traps with no stock stub.
    SYNTH_CONTROLS: traps that DO have a stock stub, synthesised on purpose as a control for
    the mechanism."""
    path = path or os.path.join(ROOT, 'build/hook/assemble_%s.py' % probe)
    if not os.path.exists(path):
        return []
    # V01 D7: parse the assembler with ast and literal_eval the module-level assignment. The old
    # non-greedy regex plus digit scraping lost numbers after a ']' inside a comment and dropped
    # tuples. Every failure mode failed closed, but a gate should say why: a value that is not a
    # literal list of ints raises ValueError (attest_trap_stubs turns that into a FAIL).
    import ast
    src = open(path, encoding='utf-8').read()
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        raise ValueError('%s does not parse: %s' % (os.path.basename(path), e))
    found = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name
                                                for t in node.targets):
            found = node
    if found is None:
        return []
    try:
        val = ast.literal_eval(found.value)
    except ValueError:
        raise ValueError('%s: %s is not a literal list of ints' % (os.path.basename(path), name))
    if not isinstance(val, (list, tuple)) or not all(isinstance(x, int) and not isinstance(x, bool)
                                                    for x in val):
        raise ValueError('%s: %s is not a literal list of ints' % (os.path.basename(path), name))
    return list(val)


def cave_spans(addrs):
    """One span per address cluster (a gap of more than 256 words starts a new one), as
    cavesim.build does."""
    spans, cur = [], None
    for a in sorted(addrs):
        if cur and a - cur[1] <= 256:
            cur[1] = a
        else:
            cur = [a, a]
            spans.append(cur)
    return [tuple(x) for x in spans]


def attest_trap_stubs(probe, declared=None, controls=None, words_path=None):
    """Gate for synthesised trap stubs. With no stub in the cave it prints two lines and
    passes. `words_path` lets the selftest check a mock without placing it under build/hook/."""
    import xapvm
    code = xapvm.load_words(
        os.path.join(ROOT, 'firmware/bose/extracted/internal_fs/vm.app'))[0x18:]
    check_common_tail(code)                              # the stock tail is what we copy
    wp = words_path or os.path.join(ROOT, 'build/hook/%s_words.json' % probe)
    w = {int(k, 16): v & 0xFFFF for k, v in json.load(open(wp)).items()}
    patched = list(code)
    for a, v in w.items():
        patched[a] = v
    spans = cave_spans(w)
    stubs = find_cave_stubs(patched, spans)
    uses = tail_uses(patched, spans)
    stock = set(xapvm.find_stubs(code)[0].values())      # trap numbers Bose already stubs
    names = {v: k for k, v in json.load(open(os.path.join(ROOT, 'tools/traps-bluelab73.json'))).items()}
    bad = []
    try:
        declared = synth_declared(probe) if declared is None else declared
        controls = synth_declared(probe, 'SYNTH_CONTROLS') if controls is None else controls
    except ValueError as e:
        print('%s: synthesised trap stubs: declaration unreadable' % probe)
        print('   FAIL %s' % e)
        print('   TRAP STUB PROBLEM -- do not flash')
        return False
    import caveasm
    print('%s: synthesised trap stubs: %d' % (probe, len(stubs)))
    for a, (n, kind, ln) in sorted(stubs.items()):
        canon = [ENTERL_3] + caveasm.imm_words(n, 0x18) + list(COMMON_TAIL)
        got = [patched[a + k] for k in range(ln)]
        row = '   0x%05X trap 0x%02X %-28s %s, %d words' % (a, n, names.get(n, '?'), kind, ln)
        why = []
        if kind != 'inline':
            why.append('only the inline tail is allowed (a far bra is a form Bose never emits)')
        if got != canon:
            why.append('words differ from the canonical stub %s' % [hex(x) for x in canon])
        if n in stock and n not in controls:
            why.append('Bose already has a stub for this trap: call it instead '
                       '(or list it in SYNTH_CONTROLS)')
        if n not in stock and n in controls:
            why.append('listed in SYNTH_CONTROLS but Bose has no stub for it: use SYNTH_TRAPS')
        if n not in names:
            why.append('not a BlueLab 7.3.1 trap number')
        if n > SYNTH_MAX_TRAP:
            why.append('above the stack dispatcher bound 0x%X: the call faults' % SYNTH_MAX_TRAP)
        if n in UNIMPLEMENTED_TRAPS:
            why.append('trap slot is (0,0) in the stack trap table: unimplemented, the dispatcher '
                       'takes the fault path (T01 C2, R02 E11)')
        if n not in declared and n not in controls:
            why.append('not declared in the assembler (SYNTH_TRAPS)')
        if not (SAFE_WINDOW[0] <= a and a + ln <= SAFE_WINDOW[1]):
            why.append('outside the proven window')
        print(row + ('   <-- ' + '; '.join(why) if why else ''))
        bad += why
    inside = {a + ln - 5 for a, (_n, _k, ln) in stubs.items()}
    for u in uses:
        if u not in inside:
            print('   FAIL the five trap-tail words occur at 0x%05X outside a recognised stub' % u)
            bad.append('stray tail')
    for a, op in stray_tail_ops(patched, spans, stubs):
        print('   FAIL opcode 0x%02X (%s) at 0x%05X outside a canonical trap stub'
              % (op, 'ld XH,@(n,Y)' if op == 0x0E else 'bra @abs', a))
        bad.append('stray 0x0E/0xE1')
    for a, op, t in tail_branches(patched, spans):
        print('   FAIL %s at 0x%05X targets the stock trap tail 0x%03X: a stock stub reaches it with a '
              '1-word bra, a cave must carry the tail itself (synth_stub_words); bsr leaves the link in '
              'X, so the trap id would be above the dispatcher bound 0x%X (V01 D1)'
              % ('bsr' if op == 0x9C else 'bra' if op == 0xE0 else 'branch', a, t, SYNTH_MAX_TRAP))
        bad.append('branch into the trap tail')
    for n in list(declared) + list(controls):
        if n not in {n2 for n2, _k, _l in stubs.values()}:
            print('   FAIL SYNTH_TRAPS/SYNTH_CONTROLS declares 0x%02X but no stub for it is in the cave' % n)
            bad.append('declared but absent')
    if stubs:
        # V01 D12 (doc): no tool prices the stack a synthesised stub adds against FLASH-PROTOCOL
        # gate 1. Say so, where the owner signs the figure.
        print('   MANUAL GATE: each stub adds a 3-word frame plus 1 word below it plus the trap shim '
              '(enterl -2 for 0xD3) to the stack at its call site; price it into the gate-1 headroom '
              'figure (python tools/stackdepth.py <entry> --frame <n>) and write it on the press page')
        try:
            asm = os.path.join(ROOT, 'build/hook/assemble_%s.py' % probe)
            if os.path.exists(asm) and re.search(r'not in \(0xE2, 0x0F\)\)', open(asm, encoding='utf-8').read()):
                print('   NOTE the assembler needs_follow() ignores 0xE1 (T12 S7): it reserves a connector '
                      'word after each stub. Harmless (layout only); use caveasm.needs_follow to save the word.')
        except OSError:
            pass
    print('   %s' % ('trap stubs: none, or every one canonical and declared' if not bad
                     else 'TRAP STUB PROBLEM -- do not flash'))
    return not bad


if __name__ == '__main__':
    if len(sys.argv) > 1:
        # V01 D10: all(f(p) for p in argv) stopped at the first failing probe, so later probes were
        # neither checked nor printed. Run every probe, then combine.
        ok = True
        for f in (check, attest, attest_trap_stubs):
            results = [f(p) for p in sys.argv[1:]]
            ok = all(results) and ok
        sys.exit(0 if ok else 1)
    audit()
