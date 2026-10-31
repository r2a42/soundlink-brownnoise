"""ladder_ext: the EXTENSION of the probe235 cave for the cold-start LADDER (probes 240..): new code placed ONLY in the twelve dead functions
that probe235 confirmed inert on hardware (2026-10-17), leaving every word of probe234's cave unchanged except two 3-word bsr operands
(TRIG -> EVENTS, HANDLER -> AUTOSTART), which are retargeted to thin wrappers that call the old routines unchanged.

    apply(G, STAGE)   G = the namespace of the (patched) probe235 assembler, STAGE = rung number 1..6

Rungs (each adds ONE step; every rung ends with a battery-percentage prompt as the diagnostic, id 0x27 + k = battery 10k percent):
  all : connect event 0x4753 (the laptop connects, nothing streams) -> 10 s later marker 0x27 ("battery 10%": the stage trigger was reached)
        -> 6 s later: MessageKalimbaTask(ours), FileFind, KalimbaLoad (refused -> 0x3E "bluetooth off")
  1   : DSP MUSIC_READY (0x1000) -> KalimbaPowerOff, speak 0x28 (battery 20%)
  2   : + SETPLUGIN(1) + LOADPARAMS, PARAMS_LOADED (0x1015) -> KalimbaPowerOff, speak 0x29 (30%)
  3   : + fn_1f04c DAC connect + DAC gain, then teardown (KalimbaPowerOff + fn_1f12b), speak 0x2A (40%)
  4   : + 0x1002, 0x10a0, 0x1001, 0x1070, 0x1071, teardown, speak 0x2B (50%)
  5   : + the silent SBC frame into port 0, teardown, speak 0x2C (60%)
  6   : + 0x1072 + poke + hold + GO and the first noise poll (no teardown, nothing spoken): the noise should start
Failure ids: 0x3E load refused, 0x1F DAC connect refused, 0x24 a DSP message refused, 0x3A the frame could not be fed.
"""
import sys, os, os

CONFIRMED12 = (0x1DDA4, 0x375B8, 0x2CE02, 0x3685A, 0xE5AB, 0x12E37, 0x163BC, 0x2F5C4, 0x210A7, 0x275A8, 0x23D5D, 0x27982)
COLD_ID = 0x2E
REL2_ID = 0x14                     # the cold-owned flag (a pending delayed message, kept alive by WATCH)
FLAG_MS = 20000
DG_ID = 0x50                   # probe300 (BN): the read-only G5 report digit (a timer message to the cave task; not a poll id 0x40..0x45)
DG_MS = 36000                  # 20 s after the yield release (the release is 16 s after the yield)
WATCH_MS = 4000                    # the watchdog period
GAIN_N = 10                        # the cold start's hardware volume index (0..15, 3 dB per step, 15 = 0 dB); 10 = -15 dB
STG_A, STG_B = 0x0025, 0x0026          # MessageIds of the two stage timers (unused by the old cave: AUTO 0x20, REL 0x13, MODE 0x30, polls 0x40..)
SBC_LEN = 9


class Prog:
    def __init__(self): self.items = []
    def W(self, *w): self.items.append(("w", list(w)))
    def BSR(self, t): self.items.append(("bsr", t))
    def BR(self, op, l): self.items.append(("br", op, l))
    def LBL(self, n): self.items.append(("label", n))
    def BLK(self): self.items.append(("blk",))


def build_xprog(G):
    """TABLEX (probe405, opt-in): the handler complex that ladder_core emitted into XPROG (HANDLER .. SAY, REARM) becomes the EXT block HX, and ARM becomes the EXT block ARMX
    (ARM's tail jump to REARM is replaced by a private copy of REARM's body, so the two blocks are independent and each can be pinned far from its call site). Main labels (POKE, AUTOSTART, SPEAKR, RSEND ...)
    are called by their placed addresses. Instruction content is identical to the window code of probe402."""
    X = list(G['XPROG'])
    L = G['label_addr']
    own = {it[1] for it in X if it[0] == "label"}
    assert not (G.get('VMREAD') or G.get('G5DIAG')), 'TABLEX: the handler AUTOSTART call goes straight to EXTH'
    def conv(it):
        if it[0] == "bsr" and it[1] == "AUTOSTART": return ("bsr", "EXTH")        # the old handler bsr to AUTOSTART was a retargeted 3-word operand (-> EXTH); EXTH is an EXT block now called directly
        if it[0] == "bsr" and isinstance(it[1], str) and it[1] not in own: return ("bsr", L[it[1]])
        if it[0] == "br": assert it[2] in own, it
        return it
    X = [conv(it) for it in X]
    ia = X.index(("label", "ARMX"))
    ib = [k for k, it in enumerate(X) if it[0] == "label" and k > ia][0]            # the label after ARM's items (NOPLAY)
    arm = X[ia:ib]
    hx = X[:ia] + X[ib:]
    ir = hx.index(("label", "REARM"))
    ie = [k for k in range(ir + 1, len(hx)) if hx[k] == ("w", [0xF80F])][0]
    rearm_body = hx[ir + 1:ie + 1]                                                    # REARM's body incl. its leavel -8
    assert arm[-1] == ("br", 0xE0, "REARM"), arm[-1]
    arm = arm[:-1] + rearm_body
    assert not any(it[0] == "br" and it[2] == "REARM" for it in arm)
    return [("blk",)] + hx + [("blk",)] + arm


def build_scan(G):
    """probe323: SCANSYNC, placed FIRST in the AY pool (it calls only stock addresses) so that the product's main layout, which was packed with no room to spare, only gains two 3-word call sites.
    AL = the noise mode (1 ON, 0 OFF), preserved. ON: if @0x564 bit 10 or 11 (page / inquiry scan on) is set -> the stock page-scan-off and inquiry-scan-off wrappers (nothing is sent when both are clear).
    OFF: sink state below 3 (limbo, connectable, discoverable): page scan on (fn_0c7f2) and inquiry scan on (fn_0c82a); any other state nothing (a connected speaker keeps the stock's scans off)."""
    P = Prog()
    W, BSR, BR, LBL, BLK = P.W, P.BSR, P.BR, P.LBL, P.BLK
    imm = G['ca'].imm_words
    BLK(); LBL("SCANSYNC")                                                        # the dispatcher: AL = the mode, preserved
    W(0xFC0B)                                                                     # enterl -4
    W(0x0127)                                                                     # st AL,@(1,Y)
    W(0x0084); BR(0xF4, "SY_R")
    BSR("SCANOFF"); BR(0xE0, "SY_X")
    LBL("SY_R")
    BSR("SCANRST")
    LBL("SY_X")
    W(0x0117)                                                                     # ld AL,@(1,Y)  the mode back
    W(0xFC0F)
    BLK(); LBL("SCANOFF")
    W(0xFE0B)
    if G.get('BTDROP'):
        # probe328: any device connected (the stock's own test, fn_09157 = number of connected devices) -> the stock's drop-everything helper fn_09445(1) (fn_0ccd4 both HFP links, fn_04162(1) the A2DP links, fn_0d358): the call the Bluetooth key and the 10 s reset use
        BSR(0x09157); W(0x0084); BR(0xF4, "SO_S")
        W(0x0114); BSR(0x09445)
        LBL("SO_S")
    if G.get('CANCEL670B'):
        # probe333: the stock "ready to connect" reminder (fn_0d500 sends 0x670b to task 0x512 in 500 ms; its handler at 0x0292a re-sends it every 60 s = 0xea60 ms): cancel the pending one (MessageCancelFirst; the handler's own fn_395e7 loops the same trap) on every SCANOFF (the press ON and each 4-s watchdog tick)
        W(*imm(0x670B, 0x10)); W(*imm(0x512, 0x14)); BSR(G['CANCELFIRST'])
    W(*imm(0x564, 0x15)); W(*imm(0x0C00, 0xC4)); W(0x0084); BR(0xF4, "SO_X")      # both scan bits clear: nothing to send
    BSR(0x0C80E); BSR(0x0C86D)                                                    # page scan off, inquiry scan off (scan-enable 0)
    LBL("SO_X")
    W(0xFE0F)
    BLK(); LBL("SCANRST")                                                         # sinkState 0, 1 or 2 (not connected): the stock scans back on (a repeat of an ON is harmless)
    W(0xFE0B)
    W(*imm(0x59E, 0x15)); W(*imm(3, 0x84)); BR(0xF8, "SR_X")                      # sinkState >= 3 (connected, streaming, call, ...): nothing
    BSR(0x0C7F2); BSR(0x0C82A)                                                    # page scan on, inquiry scan on
    LBL("SR_X")
    W(0xFE0F)
    return P.items


def build_program(G, STAGE, VARIANT=''):
    EAMP = VARIANT in ('E', 'F')      # 'E' = 'D' (volume-word diagnostic) plus the amp-on message right after GO; 'F' = 'E' with CONSTANT values instead of the RAM reads (bisect)
    NOREAD = (VARIANT == 'F')
    if EAMP: VARIANT = 'D'
    DIAG = (VARIANT == 'W')           # 'W' = 'v' plus a spoken code when the watchdog has to intervene (test only)
    if DIAG: VARIANT = 'v'
    FINAL = (VARIANT == 'P')          # 'P' = the PRODUCT: 'v' without the hands-free test emulation (no connect-event press, no stage A)
    if FINAL: VARIANT = 'v'
    NEWF = bool(G.get('NEWFEAT'))     # probe275+: power-off OFF, mute, yield to a streaming phone, 4-s watchdog (off: probe274's logic and layout exactly)
    WMS = WATCH_MS if NEWF else 10000
    P = Prog()
    ca = G['ca']
    TRIMSW = bool(G.get('TRIMSW'))    # opt-in (2026-10-30, docs/deep/layout-engine-2026-10-30.md): drop the explicit swallows of the COLD (0x2E) and NOREWR (0x24) flag messages; IDGUARD already ends every id that is not REL/MODE/AUTO, so the swallow is redundant (well-supported by reading, NOT yet run on hardware)
    if TRIMSW: assert G.get('IDGUARD') and VARIANT == 'v' and not ({0x2E, 0x24} & {G['REL_ID'], G['MODE_ID'], G['AUTO_ID']}), 'TRIMSW needs IDGUARD'
    W, BSR, BR, LBL, BLK = P.W, P.BSR, P.BR, P.LBL, P.BLK
    imm = ca.imm_words
    TASK_ADDR = G['TASK_ADDR']
    KALMSG, KALTASK, KALLOAD, KALPOFF = G['KALMSG'], G['KALTASK'], G['KALLOAD'], G['KALPOFF']
    FILEFIND, KALLONG, KSINK = G['FILEFIND'], G['KALLONG'], G['KSINK']
    SPEAK, CANCELFIRST = G['SPEAK'], G['CANCELFIRST']
    FN1F04C, FN1F12B = 0x1F04C, 0x1F12B
    RGNSRC, SCONN, PMALLOC = ca.STUB['StreamRegionSource'], ca.STUB['StreamConnect'], ca.STUB['PanicUnlessMalloc']
    LEVEL_ID = G['LEVEL_BASE'] + G.get('DEFLEV_EXT', G['DEFLEV'])
    L = G['label_addr']
    MARK = 0x27 + STAGE + (1 if VARIANT == 'a' else 2 if VARIANT == 'b' else 3 if VARIANT == 'c' else 0)
    _unused_mark = 0x27 + STAGE                          # this rung's success marker: battery 10*(STAGE+1) percent
    sys.path.insert(0, 'docs/deep/material-2026-10-13/c-sbc')
    import sbclib
    SBC = list(sbclib.build_cover(SBC_LEN))

    # ---- EVTX: TRIG calls this instead of EVENTS (AL = the event)
    BLK(); LBL("EVTX")
    W(0xF80B); W(0x0327)
    if G.get('PEEKCEN'):
        BSR("PCGO"); W(0x0084); BR(0xF4, "EV_Q")                                    # probe362: PCGO answers 1 for one of the five trigger events (stock default-arm ids, see PCIDS) = a PEEK was sent; else 0
        W(0x0317); W(0xF80F)
        LBL("EV_Q")
        W(0x0317)
    if G.get('BOOTSTART'):
        # probe342 (DIAGNOSTIC, owner 2026-10-27: unattended tests): 0x4001 EventUsrPowerOn, mode OFF: arm ONE press-equivalent BOOT_MS later (id 0x31; EXTH calls MODETOGX if the mode is still OFF). The 0x4001 itself goes on to the stock EVENTS below.
        W(*imm(0x4001, 0x84)); BR(0xF0, "EV_B")
        BSR(L['PEEKMODE']); W(0x0084); BR(0xF0, "EV_B")
        W(*imm(0x31, 0x14)); W(*imm(G.get('BOOT_MS', 25000), 0x10)); BSR(L['RSEND'])
        LBL("EV_B")
        W(0x0317)
    if VARIANT == 'w':
        # WARM reference: a silent stream start (event 0x4758) loads the STOCK DSP; start the noise loop 5 s later and read the same port quantities
        W(*imm(0x4758, 0x84)); BR(0xF0, "EV_X")
        W(*imm(LEVEL_ID, 0x14)); W(*imm(5000, 0x10)); BSR(L['RSEND'])
        W(*imm(0x28, 0x14)); W(*imm(15500, 0x10)); BSR(L['RSEND'])
        W(*imm(0x29, 0x14)); W(*imm(21000, 0x10)); BSR(L['RSEND'])
        BR(0xE0, "EV_X")
    if VARIANT == 'v':
        W(*imm(0x4716, 0x84)); BR(0xF0, "EV_4")                    # SLC disconnected: the old EVENTS stops the loop; if the mode is ON, ENSURE brings the noise back 4 s later
        BSR(L['PEEKMODE']); W(0x0084); BR(0xF4, "EV_X")
        W(*imm(0x2C, 0x14)); W(*imm(4000, 0x10)); BSR(L['RSEND'])
        BR(0xE0, "EV_X")
        LBL("EV_4")
        if NEWF:
          # probe275: 0x4002 EventUsrPowerOff with the mode ON = a press of OFF (mute at once, hold released later); 0x4758 stream start while the DSP is OURS (cold-owned flag 0x2E) = YIELD to the phone: OFF, so the stock decoder can load and music plays
          W(0x0317); W(*imm(0x4002, 0x84)); BR(0xF0, "EV_5")
          BSR(L['PEEKMODE']); W(0x0084); BR(0xF4, "EV_P" if (G.get('PWRREL') or G.get('PWRREL2')) else "EV_X")
          BSR("MODETOGX")
          if G.get('PWRREL2'):
              # probe428 (the payload LOOP product's form of PWRREL; docs/deep/probe428-loop-2026-10-31.md): in the loop a chunk (an ADPCM transform on Kalimba port 3) is usually in flight at the
              # power-off and the 16 s hold exists to keep the stock away from the DSP until it has ended (rule 4: never speak / never let the stock reload the DSP while our transform holds port 3).
              # So the release goes through RELFREE: SetAudioBusy(0) (RELEASE0, only if the word is our task) ONLY when port 3 has no transform (StreamKalimbaSink(3) = 0 = no DSP, or
              # TransformFromSink(ksink) = 0 = free); a chunk still in flight keeps the hold, and its free edge (0x8026 in EXTH, XF_R below) releases it then. The REL timer (16 s) stays as the backstop.
              assert G.get('FREEEDGE') and not G.get('GEN') and not G.get('PWRREL'), 'PWRREL2 is the loop product form: needs FREEEDGE, no GEN, not together with PWRREL'
              LBL("EV_P"); BSR("RELFREE")
          elif G.get('PWRREL'):
              # probe427 (owner 2026-10-30: after a power-off with the noise playing, two more presses were needed to power on; docs/deep/poweroff-with-noise-2026-10-30.md):
              # a power-off (0x4002) releases OUR audio-busy hold AT ONCE (RELEASE0: SetAudioBusy(0) only if the word is our task), mode ON (after the OFF above) or OFF (a power-off
              # inside the 16 s after a press-OFF). The lean generator has no chunk in flight, so nothing needs the hold after an OFF; the stock power-off and the next power-on
              # announcement are MessageSendConditionally on that word and were parked for up to 16 s (REL). The REL timer still fires and finds the word not ours: no-op.
              LBL("EV_P"); BSR(L['RELEASE0'])
          BR(0xE0, "EV_X")
          LBL("EV_5")
          if not G.get('NOYIELD'):      # probe286 (diagnostic build) drops the stream-start yield to make room for the DIAG6 speech
              W(0x0317); W(*imm(0x4758, 0x84)); BR(0xF0, "EV_6")
              BSR(L['PEEKMODE']); W(0x0084); BR(0xF4, "EV_X")
              W(*imm(COLD_ID, 0x14)); BSR("PEEKF"); W(0x0084); BR(0xF4, "EV_X")
              BSR("MODETOGX"); BR(0xE0, "EV_X")
          LBL("EV_6")
    if VARIANT == 'v' and not FINAL:
        # TEST EMULATION of the centre long press for the hands-free runs: the connect event 0x4753 presses ONCE (only when the mode is OFF)
        W(*imm(0x4753, 0x84)); BR(0xF0, "EV_X")
        BSR(L['PEEKMODE']); W(0x0084); BR(0xF0, "EV_X")
        BSR("MODETOGX")
    elif not FINAL:
        W(*imm(0x4753, 0x84)); BR(0xF0, "EV_X")
        W(*imm(STG_A, 0x10)); W(*imm(TASK_ADDR, 0x14)); BSR(CANCELFIRST)     # debounce
        W(*imm(10000, 0x10)); W(*imm(STG_A, 0x14)); BSR(L['RSEND'])          # old RSEND: MessageSendLater(cave task, AL, 0, AH)
    LBL("EV_X")
    W(0x0317); BSR(L['EVENTS'])
    W(0xF80F)

    if G.get('CSTOCK'):
        # ---- CSTOCK (probe335 DIAGNOSTIC): MessageCancelAll(0x512, id) for every id from CSTOCK_HI down to CSTOCK_LO (fn_395e7 loops MessageCancelFirst until none is left). 0x512 is the stock application task (every stock periodic chain of the survey sends to it). AL is preserved.
        BLK(); LBL("CSTOCK")
        W(0xFC0B)                                                                 # enterl -4 (slots 0 and 1 are free)
        W(0x0027)                                                                 # st AL,@(0,Y)  the mode
        W(*imm(G['CSTOCK_HI'], 0x14)); W(0x0127)                                  # id = HI -> slot 1
        LBL("CS_L")
        W(0x0113); W(*imm(0x512, 0x14)); BSR(0x395E7)                             # ld AH,@(1,Y) ; ld AL,#0x512 ; MessageCancelAll(task, id)
        W(0x0117); W(*imm(0xFFFF, 0x34)); W(0x0127)                               # id - 1
        W(*imm(G['CSTOCK_LO'], 0x84)); BR(0xF8, "CS_L")                           # while id >= LO
        W(0x0017)                                                                 # ld AL,@(0,Y)  the mode back
        W(0xFC0F)
    if G.get('LEDCYCLE'):
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
        # ---- LEDACT: AL = the variant v: 0 nothing, 1-3 one LED off, 4 LEDs 0-2 off, 5 the stock ids cancelled
        BLK(); LBL("LEDACT")
        W(0xF80B); W(0x0327)
        for _v, _leds in ((1, (0,)), (2, (1,)), (3, (2,)), (4, (0, 1, 2))):
            W(0x0317); W(*imm(_v, 0x84)); BR(0xF0, "LA_V%d" % _v)
            for _led in _leds:
                W(0x0014); W(0x0027); W(0x0010); W(*imm(_led, 0x14)); BSR(LEDC)  # LedConfigure(led, LED_ENABLE, 0)
            BR(0xE0, "LA_X")
            LBL("LA_V%d" % _v)
        LBL("LA_X")
        W(0xF80F)
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
        LBL("LT_NB")
        W(0x0517); BSR("LEDACT")                                                  # the variant's action (its own block)
        LBL("LT_NX")
        W(0x0417); W(*imm(1, 0x34)); W(0x0427)                                    # t += 1
        W(*imm(6, 0x84)); BR(0xF0, "LT_SD")
        W(0x0014); W(0x0427)                                                      # t = 6 -> 0 and the next variant
        W(0x0517); W(*imm(1, 0x34)); W(0x0527)
        W(*imm(5, 0x84)); BR(0xF0, "LT_SD")
        W(0x0014); W(0x0527)                                                      # v = 5 -> 0
        LBL("LT_SD")
        W(0x0517); W(0x04A0); W(0x0437); W(*imm(0x1000, 0x34))                    # id' = 0x1000 + (v << 4) + t
        W(*imm(5000, 0x10)); BSR(L['RSEND'])
        W(0xF80F)
    if G.get('LEDDARK'):
        # ---- LEDDARK: AL = the mode (1 ON, 0 OFF), preserved. ON: the stock LED routine fn_19092(0) once (every light dark until the next stock power-on)
        BLK(); LBL("LEDDARK")
        W(0xF80B); W(0x0327)
        W(0x0084); BR(0xF4, "LD_X")
        W(0x0014); BSR(0x19092)
        LBL("LD_X")
        W(0x0317); W(0xF80F)
    if G.get('PEEKCEN'):
        # probe362 (2026-10-28): the trigger ids are NOT 0x4020+k any more: the fn_01749 switch maps 0x4021 to BootSetMode(7) (the speaker drops to USB 4005) and 0x4022 to LoaderModeEnter. These five ids are the DEFAULT arm of
        # that switch (switchtab.py 0x1749, case = id - 0x4001, target 0x23e2) and are not compared anywhere in the fn_00846 ladder: nothing in the stock acts on them.
        PCIDS = ((0x402D, 0x2A00, 0x02, None), (0x402E, 0x0300, 0x00, None), (0x4033, 0x8367, 0x00, None))   # probe378 (trimmed): HI first word, state, hook readback; 0x4015 = LOADER, 0x402C = HOOK
        # ---- PCGO: AL = an event. A trigger id: PEEK (0x7AB2) of its DM cell (words: address low, address high 0), AL = 1; any other id: AL = 0
        BLK(); LBL("PCGO")
        W(0xF80B); W(0x0327)
        W(0x0014); W(0x0027); W(0x0127); W(0x0227)
        if G.get('GENLOAD'):
            W(0x0317); W(*imm(0x4015, 0x84)); BR(0xF0, "PG_L1")                      # probe378 LOADER: start the PM load (message 0x1100 in 20 ms)
            W(*imm(0x1100, 0x14)); W(*imm(20, 0x10)); BSR(L['RSEND']); W(0x0114); W(0xF80F)
            LBL("PG_L1")
            W(0x0317); W(*imm(0x402C, 0x84)); BR(0xF0, "PG_L2")                      # probe378 HOOK: stop the stock refill (M[0x28ea] = M[0x28fe] = 0), then ONE write M[0x8367] := 0x2A00
            for _ha, _hv in ((0x28EA, 0), (0x28FE, 0), (0x8367, 0x2A00)):
                W(*imm(_hv, 0x14)); W(0x0127); W(*imm(_ha, 0x10)); W(*imm(0x7AB3, 0x14)); BSR(KALMSG)
            W(0x0114); W(0xF80F)
            LBL("PG_L2")
        for _k, (_id, _a, _h, _pv) in enumerate(PCIDS):
            W(0x0317); W(*imm(_id, 0x84)); BR(0xF0, "PG_%d" % (_k + 1))
            W(*imm(_h, 0x14)); W(0x0027)
            if _pv is not None:
                W(*imm(_pv, 0x14)); W(0x0127)
                W(*imm(_a, 0x10)); BR(0xE0, "PG_P")
            else:
                W(*imm(_a, 0x10)); BR(0xE0, "PG_S")
            LBL("PG_%d" % (_k + 1))
        W(0x0014); W(0xF80F)
        LBL("PG_P")
        W(*imm(0x7AB3, 0x14)); BSR(KALMSG)                                        # probe369: the POKE (no readout)
        W(0x0114); W(0xF80F)
        LBL("PG_S")
        W(*imm(0x7AB2, 0x14)); BSR(KALMSG)
        if G.get('PCMARK'): W(*imm(0x909, 0x14)); W(*imm(15000, 0x10)); BSR(L['RSEND'])
        W(0x0114); W(0xF80F)
        if G.get('GENLOAD'):
            # ---- GENLOAD (probe378; owner go 2026-10-28; fable review in the field log): write build/dsp/noisegen.bin (60 DSP program words linked at PM 0x2A00) into DSP program memory through the PM window.
            #      GLDM (message ids 0x1100..): 0x1100 = POKE M[0xFE65] := 1 (PM_WIN_ENABLE); 0x1101 + j = chunk j (6 PM words), 30 ms apart. No hook here (a separate event does that, after a PEEK verification).
            #      GLDPUT: AL = hi16, AH = lo16 of one PM word; the PM address lives in the CALLER's slot 3 (the PSDG pattern, caller slot 3 = @(11,Y)); POKEs LO half (window 3) then HI half (window 2); increments the address.
            _bin = open('build/dsp/noisegen.bin', 'rb').read()
            _words = [((_bin[i] << 8) | _bin[i + 1], (_bin[i + 2] << 8) | _bin[i + 3]) for i in range(0, len(_bin), 4)]      # (hi16, lo16), big-endian file
            import os as _os
            _words = _words[:int(_os.environ.get('GEN_WORDS', len(_words)))]                                       # capacity test only
            _CH = 6
            _chunks = [_words[i:i + _CH] for i in range(0, len(_words), _CH)]
            BLK(); LBL("GLDPUT")
            W(0xF80B)
            W(0x0427); W(0x0523)                                  # st AL,@4 (hi16) ; st AH,@5 (lo16)
            W(0x0014); W(0x0227)                                  # slot 2 (w4) = 0
            W(*imm(3, 0x14)); W(0x0027)                           # slot 0 (w2) = 3 : PMWIN_LO
            W(0x0517); W(0x0127)                                  # slot 1 (w3) = lo16
            W(0x0B13)                                             # ld AH,@(11,Y) : the PM address (caller slot 3)
            W(*imm(0x7AB3, 0x14)); BSR(KALMSG)
            W(*imm(2, 0x14)); W(0x0027)                           # slot 0 = 2 : PMWIN_HI
            W(0x0417); W(0x0127)                                  # slot 1 = hi16
            W(0x0B13)
            W(*imm(0x7AB3, 0x14)); BSR(KALMSG)
            W(0x0B17); W(*imm(1, 0x34)); W(0x0B27)               # caller slot 3 += 1
            W(0xF80F)
            for _j, _ch in enumerate(_chunks):
                BLK(); LBL("GLC%d" % _j)                          # AL = the PM address of the chunk's first word
                W(0xF80B); W(0x0327)
                for _hi, _lo in _ch:
                    W(*imm(_hi, 0x14)); W(*imm(_lo, 0x10)); BSR("GLDPUT")
                W(0xF80F)
            BLK(); LBL("GLDM")                                    # AL = the message id
            W(0xF80B); W(0x0327)
            W(*imm(0x1100, 0x84)); BR(0xF0, "GM_1")
            W(0x0014); W(0x0027); W(0x0227); W(*imm(1, 0x14)); W(0x0127); W(*imm(0xFE65, 0x10)); W(*imm(0x7AB3, 0x14)); BSR(KALMSG)
            W(*imm(0x1101, 0x14)); W(*imm(30, 0x10)); BSR(L['RSEND']); W(0xF80F)
            LBL("GM_1")
            for _j in range(len(_chunks)):
                W(0x0317); W(*imm(0x1101 + _j, 0x84)); BR(0xF0, "GM_n%d" % (_j + 1))
                W(*imm(0x2A00 + _CH * _j, 0x14)); BSR("GLC%d" % _j)
                if _j + 1 < len(_chunks):
                    W(*imm(0x1102 + _j, 0x14)); W(*imm(30, 0x10)); BSR(L['RSEND'])
                W(0xF80F)
                LBL("GM_n%d" % (_j + 1))
            W(0xF80F)
        # ---- PCWORD: AL = a 16-bit value, AH = the first delay (ms): six octal digits, low first, as the digit messages 0x900 + d through SDG; AL = the next delay
        BLK(); LBL("PCWORD")
        W(0xF80B); W(0x0427); W(0x0323)
        W(*imm(6, 0x14)); W(0x0527)
        W(0x0014); W(0x0227)                                  # slot 2: the digit sum = 0 (probe362 CHECK DIGIT, owner 2026-10-28)
        LBL("PW_L")
        W(0x0417); W(0x07C4); W(0x0237); W(0x0227)            # sum += digit (add AL,@(2,Y))
        W(0x0417); W(0x07C4); W(*imm(0x900, 0x34)); BSR("PSDG")
        W(0x0417); W(0x0009); W(0x03A4); W(0x0427)
        W(0x0517); W(*imm(0xFFFF, 0x34)); W(0x0527); W(0x0084); BR(0xF0, "PW_L")
        W(0x0217); W(0x07C4); W(*imm(0x900, 0x34)); BSR("PSDG")   # the 7th digit = (sum of the six digits) mod 8
        W(0x0317)
        W(0xF80F)
        BLK(); LBL("PSDG")                                    # AL = a digit message id; sent after the CALLER's slot-3 delay, which then advances by 3.5 s (16-bit delays: 14 digits must end before 65.5 s)
        W(0xF80B); W(0x0327)
        W(0x0B13); W(0x0317); BSR(L['RSEND'])
        W(0x0B17); W(*imm(3500, 0x34)); W(0x0B27)
        W(0xF80F)
        # ---- PCREPLY: X = the message of the 0x7AB2 reply (X is untouched on entry): word 1 (M[a], low 16 bits) is spoken
        BLK(); LBL("PCREPLY")
        W(0xF80B); W(0x0327); W(0x031B)                                           # st AL,@(3,Y) the Message ; ld X,@(3,Y)
        W(0x0116)
        W(*imm(9000, 0x10)); BSR("PCWORD")                                   # probe363: ONE word per ev (7 sends); probe362 sent 14 and the speaker reset at the reply
        W(0xF80F)
    if G.get('STALL'):
        # ---- probe334 STALL INSTRUMENT. A tick chain of messages with id = (k << 8) | (clock & 0xFF), k = 0x10..0x7F (0x1000 = the first, sent by BUILD): each tick reads VmGetClock (low word) and compares it with the clock the id carries; a tick that arrives
        #      STALL_THR ms or more later than its STALL_D ms delay means the cooperative scheduler did not run for that long (the stream copy that feeds the 5.3 ms port-3 buffer starves after about 3-5 ms). A late tick = a MARKER: the tone is muted (MUTE) and the level poll is
        #      re-sent 150 ms ahead (the busy path's POKE restores the ratio), so the recording shows a silent gap at exactly that moment. The chain ends after k = 0x7F (about 1 s of the chunk) and BUILD starts it again. No state is kept outside the message ids.
        D, THR = G.get('STALL_D', 8), G.get('STALL_THR', 5)
        VMCLOCK = ca.STUB['VmGetClock']
        BLK(); LBL("STALLTICK")                                                   # AL = the MessageId (>= 0x1000)
        W(0xF80B)
        W(0x0327)                                                                 # st AL,@(3,Y)  id
        BSR(VMCLOCK); W(0x0427)                                                   # now (low word) -> slot 4
        W(0x0317); W(0x08A4); W(*imm(0xFF, 0xC4)); W(0x0527)                      # k = (id >> 8) & 0xFF -> slot 5
        W(*imm(0x10, 0x84)); BR(0xF4, "ST_N")                                     # k = 0x10: the first tick of a chunk carries no clock: nothing to compare
        W(0x0317); W(*imm(0xFF, 0xC4)); W(0x0327)                                 # t0 = id & 0xFF -> slot 3 (the id is no longer needed)
        W(0x0417); W(0x0357); W(*imm(16 - D, 0x34)); W(*imm(0xFF, 0xC4))          # v = (now - t0 - D + 16) & 0xFF
        W(*imm((-(16 + THR)) & 0xFFFF, 0x34)); W(*imm(112 - THR, 0x84)); BR(0xF8, "ST_N")   # v - (16 + THR) unsigned < 112 - THR : a stall (late by THR ms up to 112 ms); else normal
        if not G.get('STALL_QUIET'):                                              # probe336: QUIET = the tick chain only, no marker (no mute, no re-poll)
            BSR(L['CANCELANY']); W(0x0084); BR(0xF4, "ST_N")                          # no level poll pending (the mode is OFF): no marker
            W(*imm(G['LEVEL_BASE'] - 1, 0x34)); W(0x0327)                             # the level poll id -> slot 3
            BSR("MUTE")
            W(0x0317); W(*imm(150, 0x10)); BSR(L['RSEND'])                            # the poll back in 150 ms: busy -> the poke restores the ratio
        LBL("ST_N")
        if G.get('TRAFFIC'):
            # probe340: the pipeline test. From k = 0x14 on, every tick asks the stack whether OUR transform moved data since the last tick (TransformPollTraffic; FALSE = the worker or the DSP did not move a byte for one tick interval).
            #   FALSE = a B event: the tone is muted and the level poll re-sent 400 ms ahead (a 400 ms dip; the VM-late A event above makes a 150 ms dip), so a recording tells the two apart by the length of the gap.
            W(0x0517); W(*imm(0x14, 0x84)); BR(0xFC, "ST_S")                          # k < 0x14: the chunk has only just started
            W(*imm(3, 0x14)); BSR(G['KSINK']); W(0x0084); BR(0xF4, "ST_S")           # no Kalimba sink: nothing to test
            BSR(ca.STUB['TransformFromSink']); W(0x0084); BR(0xF4, "ST_S")           # no transform on port 3
            BSR(ca.STUB['TransformPollTraffic']); W(0x0084); BR(0xF0, "ST_S")        # TRUE: data moved
            BSR(L['CANCELANY']); W(0x0084); BR(0xF4, "ST_S")                         # no level poll pending (the mode is OFF): no marker
            W(*imm(G['LEVEL_BASE'] - 1, 0x34)); W(0x0327)
            BSR("MUTE")
            W(0x0317); W(*imm(400, 0x10)); BSR(L['RSEND'])
            LBL("ST_S")
        W(0x0517); W(*imm(1, 0x34)); W(*imm(0x80, 0x84)); BR(0xF8, "ST_X")        # k + 1 >= 0x80: the chain ends
        W(0x08A0); W(0x0327)                                                      # (k + 1) << 8 -> slot 3
        W(0x0417); W(*imm(0xFF, 0xC4)); W(0x0337)                                 # (now & 0xFF) + ((k + 1) << 8)
        W(*imm(D, 0x10)); BSR(L['RSEND'])
        LBL("ST_X")
        W(0xF80F)
    # ---- EXTH: HANDLER calls this instead of AUTOSTART (AL = a MessageId that is not a poll)
    BLK(); LBL("EXTH")
    W(0xF80B); W(0x0327)
    if not FINAL and VARIANT != 'v':
        W(*imm(STG_A, 0x84)); BR(0xF0, "XH_1")
        BSR("STAGE_A"); W(0xF80F)
    LBL("XH_1")
    W(*imm(STG_B, 0x84)); BR(0xF0, "XH_2")
    BSR("STAGE_B"); W(0xF80F)
    LBL("XH_2")
    if G.get('STALL'):
        W(*imm(0x1000, 0x84)); BR(0xFC, "XS_1")                                   # a stall-chain tick (probe334): ids below 0x1000 go on
        W(*imm(0x8000, 0x84)); BR(0xF8, "XS_1")                                   # and the system ids from 0x8000 (MESSAGE_FROM_KALIMBA = 0x8024 reaches this handler: the first simulation of the instrument caught it as a tick)
        BSR("STALLTICK"); W(0xF80F)
        LBL("XS_1")
    if G.get('CENSUS') or G.get('PEEKCEN'):
        # probe288: the census digit messages (ids 0x900..0x94F, sent by CENSUSX) go to SPEAKD (battery (digit+1)*10 percent); anything else goes on
        W(*imm(0x900, 0x84)); BR(0xFC, "XC_1")
        W(*imm(0x950, 0x84)); BR(0xF8, "XC_1")
        W(0x0317); W(0x0FC4); W(*imm(0x27, 0x34)); BSR(L['SPEAKR']); W(0xF80F)       # id & 0x0F + 0x27 = battery (digit+1)*10 percent, through SPEAKR (releases OUR hold first)
        LBL("XC_1")
    if G.get('GENLOAD') or G.get('GEN'):
        W(*imm(0x1100, 0x84)); BR(0xFC, "XG_1")                                   # probe378/380: the PM loader messages 0x1100 .. 0x110F
        W(*imm(0x1110, 0x84)); BR(0xF8, "XG_1")
        W(0x0317); BSR("GLDM"); W(0xF80F)
        LBL("XG_1")
    if VARIANT in ('f', 'k', 'w', 'p', 'q', 'r', 's', 'D'):
        if VARIANT in ('f', 'w', 'p', 'q', 'r', 's', 'D'):
            W(*imm(0x28, 0x84)); BR(0xF0, "XD_0")
            BSR("DIAGA"); W(0xF80F)
            LBL("XD_0")
            if VARIANT not in ('p', 'q', 'r'):
                W(*imm(0x29, 0x84)); BR(0xF0, "XD_2")
                BSR("DIAGB"); W(0xF80F)
                LBL("XD_2")
        W(*imm(0x900, 0x84)); BR(0xFC, "XD_1")                     # id < 0x900: not a digit message
        W(*imm(0x950, 0x84)); BR(0xF8, "XD_1")                     # id >= 0x950: no
        W(0x0317); BSR("SPEAKD"); W(0xF80F)
        LBL("XD_1")
    if VARIANT == 'v':
        if NEWF and not TRIMSW:
            W(*imm(COLD_ID, 0x84)); BR(0xF0, "XU_0")                 # the cold-owned flag message expired (not re-armed): swallow it
            W(0xF80F)
            LBL("XU_0")
        W(*imm(0x2C, 0x84)); BR(0xF0, "XU_2")
        BSR("ENSURE")
        W(0xF80F)
        LBL("XU_2")
        if G.get('STARTWAIT'):
            W(*imm(0x2F, 0x84)); BR(0xF0, "XU_5")                                # probe384: the 40 s closer: ENSURE with AL = 0x2F (no gate)
            BSR("ENSURE")
            W(0xF80F)
            LBL("XU_5")
        if G.get('NOREWR') and not TRIMSW:
            W(*imm(0x24, 0x84)); BR(0xF0, "XU_7")                                # probe388: the GENF flag message expired: swallow it
            W(0xF80F)
            LBL("XU_7")
        if G.get('SILENTDROP'):
            W(*imm(0x32, 0x84)); BR(0xF0, "XU_6")                                # probe386/387: the prompt-enable restore (8 s after the press)
            BSR("SILRST")
            W(0xF80F)
            LBL("XU_6")
        if not G.get('NOWATCH'):
            W(*imm(0x2D, 0x84)); BR(0xF0, "XU_4")
            BSR("WATCH")
            W(0xF80F)
            LBL("XU_4")
    if VARIANT == 'u':
        W(*imm(0x2A, 0x84)); BR(0xF0, "XU_1")                       # test press 2 (toggle OFF), then arm test press 3 45 s later
        BSR("MODETOGX")
        W(*imm(0x2B, 0x14)); W(*imm(45000, 0x10)); BSR(L['RSEND'])
        W(0xF80F)
        LBL("XU_1")
        W(*imm(0x2B, 0x84)); BR(0xF0, "XU_2")                       # test press 3 (toggle ON again: the warm path)
        BSR("MODETOGX")
        W(0xF80F)
        LBL("XU_2")
    if G.get('BOOTSTART'):
        W(*imm(0x31, 0x84)); BR(0xF0, "XB_1")                                     # probe342: the boot-start timer fired: press once if the mode is still OFF
        BSR(L['PEEKMODE']); W(0x0084); BR(0xF0, "XB_X")
        BSR("MODETOGX")
        LBL("XB_X"); W(0xF80F)
        LBL("XB_1")
    if G.get('LEDCYCLE'):
        W(*imm(0x1000, 0x84)); BR(0xFC, "XL_1")                                   # ids 0x1000..0x105F are the LED-variant ticks
        W(*imm(0x1060, 0x84)); BR(0xF8, "XL_1")
        BSR("LEDTICK"); W(0xF80F)
        LBL("XL_1")
    if G.get('FREEEDGE'):
        W(*imm(0x8026, 0x84)); BR(0xF0, "XF_1")                                   # probe337: MESSAGE_STREAM_DISCONNECT = the free edge of our chunk: the pending level poll is brought forward to 1 ms from now
        BSR(L['CANCELANY']); W(0x0084); BR(0xF4, "XF_R" if G.get('PWRREL2') else "XF_X")     # AL = level + 1, or 0 (no poll pending: the mode is OFF): nothing (PWRREL2: the release check below)
        W(*imm(G['LEVEL_BASE'] - 1, 0x34)); W(*imm(G.get('FREEDELAY', 1), 0x10)); BSR(L['RSEND'])
        if G.get('PWRREL2'):
            # probe428: the free edge of the LAST chunk (no poll pending) with the mode OFF (a press-OFF or a power-off happened): release our audio-busy hold now, not 16 s after the OFF,
            # provided port 3 really is free (RELFREE reads TransformFromSink first). Mode ON (STARTWAIT waiting, or a restart pending): nothing changes.
            W(0xF80F)
            LBL("XF_R")
            BSR(L['PEEKMODE']); W(0x0084); BR(0xF0, "XF_X")
            BSR("RELFREE")
        LBL("XF_X"); W(0xF80F)
        LBL("XF_1")
    W(*imm(0x8024, 0x84)); BR(0xF0, "XH_3")
    W(0x121B if G.get('TABLEX') else 0x101B); W(0x0016)                 # ld X,@(16,Y) the Message ; ld AL,@(0,X) the DSP message id.  TABLEX (probe405): the window trampoline's 2-slot frame sits between the handler frame and the scheduler's: @(18,Y)
    if G.get('PEEKCEN'):
        W(*imm(0x7AB2, 0x84)); BR(0xF0, "XH_P")                                    # probe359: the PEEK reply (X still = the message)
        W(0x1017); BSR("PCREPLY"); W(0xF80F)                                       # probe364: the message POINTER goes in AL (as the stock fn_38bb1 takes it); PCREPLY reloads X from its frame
        LBL("XH_P")
    BSR("DSPMSG"); W(0xF80F)
    LBL("XH_3")
    W(*imm(0x8000, 0x84)); BR(0xF8, "XH_X")
    if VARIANT in ('q', 'r'):
        W(0x0317); BSR("IDLOG")
    if NEWF:
        if G.get('DACREL3'):
            # probe287: the delayed hold release (REL_ID, 16 s after any OFF, after the last chunk) undoes OUR DAC connection first when the cold-owned flag (kept pending 20 s after the OFF, not cancelled by OFFALL) says the DSP is ours; the stock plugin's fn_1f04c returns 0 on our connection and fn_31d3f PanicNulls (agent O)
            W(0x0317); W(*imm(G['REL_ID'], 0x84)); BR(0xF0, "XH_R3")
            W(*imm(COLD_ID, 0x14)); BSR("PEEKF"); W(0x0084); BR(0xF4, "XH_R3")
            BSR(FN1F12B)
            LBL("XH_R3")
        if G.get('DACREL2'):
            W(0x0317); W(*imm(REL2_ID, 0x84)); BR(0xF0, "XH_R2")
            BSR(FN1F12B); BSR(L['RELEASE0'])                                    # the last chunk has ended (16 s): undo OUR DAC connection, then release the audio-busy hold
            W(0xF80F)
            LBL("XH_R2")
        if G.get('IDGUARD'):
            # probe285: AUTOSTART treats EVERY other id as an auto-start (cancel the poll, arm a first poll in 1 s = the noise restarts). A stock message that reaches our task (0x7008 from the stock AudioDisconnect during the power-off, sent to the busy owner = us) must be ignored; only our own ids (hold release, mode flag, auto-start) go on
            W(0x0317); W(*imm(G['REL_ID'], 0x84)); BR(0xF4, "XH_A")
            W(0x0317); W(*imm(G['MODE_ID'], 0x84)); BR(0xF4, "XH_A")
            W(0x0317); W(*imm(G['AUTO_ID'], 0x84)); BR(0xF4, "XH_G")
            W(0xF80F)
            LBL("XH_G")
        W(0x0317); W(*imm(G['AUTO_ID'], 0x84)); BR(0xF0, "XH_A")             # the delayed auto-start (0x20) must not arm a poll when the mode is OFF (L1a F1a)
        BSR(L['PEEKMODE']); W(0x0084); BR(0xF4, "XH_X")
        LBL("XH_A")
    W(0x0317); BSR(L['AUTOSTART'])
    LBL("XH_X")
    W(0xF80F)

    # ---- STAGE_A: marker 0x27, then arm stage B
    if not FINAL and VARIANT != 'v':
        BLK(); LBL("STAGE_A")
        W(0xF80B)
        if VARIANT == 'v':
            # PRODUCT TEST 2: the connect event stands in for ONE press, only when the mode is OFF (later connects must not toggle it)
            BSR(L['PEEKMODE']); W(0x0084); BR(0xF0, "SA_X")
            BSR("MODETOGX")
            LBL("SA_X")
            W(0xF80F)
        if VARIANT == 'u':
            # PRODUCT TEST: the connect event stands in for the centre long press (hands-free). The real trigger is TRIG -> MODETOGX.
            BSR("MODETOGX")
            W(*imm(0x2A, 0x14)); W(*imm(50000, 0x10)); BSR(L['RSEND'])
            W(0xF80F)
        if VARIANT != 'v':
          W(*imm(0x27, 0x14)); BSR(SPEAK)
        if VARIANT == 'k':
            # CALIBRATION: speak digits 1..9 (battery 20%..100%) 4.5 s apart through the digit chain, so the recogniser-free decoder has a template of every digit
            W(0x0114); W(0x0327); W(*imm(4500, 0x14)); W(0x0427)           # k = 1 (slot 3) ; delay = 4500 (slot 4)
            LBL("CAL_L")
            W(0x0317); W(*imm(0x900, 0x34)); W(0x0413); BSR(L['RSEND'])      # RSEND(id = 0x900 + k, delay)
            W(0x0417); W(*imm(4500, 0x34)); W(0x0427)
            W(0x0317); W(0x0134); W(0x0327); W(*imm(10, 0x84)); BR(0xFC, "CAL_L")
        elif VARIANT != 'v':
            W(*imm(6000, 0x10)); W(*imm(STG_B, 0x14)); BSR(L['RSEND'])
        W(0xF80F)

    # ---- STAGE_B: MessageKalimbaTask(ours), FileFind, KalimbaLoad
    BLK(); LBL("STAGE_B")
    W(0xF80B)
    if NEWF:
        BSR(L['PEEKMODE']); W(0x0084); BR(0xF0, "SB_ON")                    # the mode went OFF while this load was pending: no KalimbaLoad (L1a F1b/c)
        W(0xF80F)
        LBL("SB_ON")
    W(*imm(TASK_ADDR, 0x14)); BSR(KALTASK)
    W(*imm(len(G['KAPPATH']), 0x14)); W(0x0027)
    W(0x0114); W(*G['_KAP_AH']); BSR(FILEFIND)
    W(0x0084); BR(0xF4, "SB_BAD")
    BSR(KALLOAD)
    W(0x0084); BR(0xF4, "SB_BAD")
    W(0xF80F)
    LBL("SB_BAD")
    if NEWF:
        BSR("MODETOGX")                                                     # a refused load: the mode goes OFF (no endless retries, L1a F4) and the "bluetooth off" id is spoken once
        W(0x3E14); BSR(L['SPEAKR'])
    else:
        W(0x3E14); BSR(SPEAK)
    W(0xF80F)

    # ---- DSPMSG: AL = the DSP's message id
    BLK(); LBL("DSPMSG")
    W(0xF80B)
    if NEWF and G.get('DSPGUARD'):
        W(0x0327)                                                           # probe284: the mode is OFF (a stop press or the power-off already ran): a DSP message is the STOCK's (its beep, its power-off tone), not ours; ignore it
        BSR(L['PEEKMODE']); W(0x0084); BR(0xF4, "DM_X")
        W(0x0317)
    W(*imm(0x1000, 0x84)); BR(0xF0, "DM_P")
    if STAGE == 1:
        BSR("TEARM")
    else:
        W(0x0110); W(*imm(0x1020, 0x14)); BSR("PSEND")                      # SETPLUGIN(1)
        if VARIANT == 'a':
            BSR("TEARM")                                                    # 2a: SETPLUGIN only, then the marker
        else:
            W(*imm(0x2270, 0x10)); W(*imm(0x1012, 0x14)); BSR("PSEND")      # LOADPARAMS
            if VARIANT == 'b': BSR("TEARM")                                 # 2b: tear down at once, do not wait for 0x1015
    W(0xF80F)
    LBL("DM_P")
    W(*imm(0x1015, 0x84)); BR(0xF0, "DM_X")
    if STAGE >= 2:
        BSR("POSTLOAD")
    LBL("DM_X")
    W(0xF80F)

    # ---- TEARM: the rung's end: teardown + the rung's marker.   TEARID: AL = a failure id: teardown + speak it
    if not (STAGE >= 5 and VARIANT in ('t', 'u', 'v', 'y', 'z', 'G')):
      BLK(); LBL("TEARM")
      W(0xF80B)
      if STAGE == 1: BSR(KALPOFF)           # rung 1 only: NEVER power off a DSP whose parameters are loaded (probe241 stalled the cold speaker)
      if STAGE >= 3: BSR(FN1F12B)           # undo our DAC connect; the prompt engine then loads NowSpeakTTS over the DSP (probe161's path)
      W(*imm(MARK, 0x14)); BSR(SPEAK)
      W(0xF80F)
    if VARIANT != 'v':
      BLK(); LBL("TEARID")
      W(0xF80B); W(0x0027)
      BSR(FN1F12B)
      W(0x0017); BSR(SPEAK)
      W(0xF80F)

    # ---- PSEND: KalimbaSendMessage(AL, AH, 0, 0, 0)
    BLK(); LBL("PSEND")
    W(0xF80B); W(0x0327); W(0x0014); W(0x0027); W(0x0127); W(0x0227); W(0x0317)
    BSR(KALMSG)
    W(0xF80F)

    if STAGE >= 2:
        # ---- POSTLOAD (PARAMS_LOADED)
        BLK(); LBL("POSTLOAD")
        W(0xF80B)
        if VARIANT in ('u', 'v'):
            BSR(L['PEEKMODE']); W(0x0084); BR(0xF0, "PL_ON")   # mode OFF (toggled off while the DSP loaded): do not bring the noise up
            W(0xF80F)
            LBL("PL_ON")
        if STAGE == 2 and VARIANT == 'c':
            W(*imm(MARK, 0x14)); BSR(SPEAK)                  # 2c: speak at once on PARAMS_LOADED, no PowerOff (probe161's path)
            W(0xF80F)
        elif STAGE == 2:
            BSR("TEARM")
            W(0xF80F)
        else:
            if VARIANT == 'm':
                # TTS-STYLE OUTPUT (the wiring of the stock prompt engine fn_1e3c5, which is proven audible from the cold speaker): ONE combined codec sink
                # StreamAudioSink(type 3, instance 0, channel 2), rate 48000, the DSP's WRITE PORT 6 connected straight to it, unmuted. No fn_1f04c, no SinkSynchronise, no hardware-gain call.
                W(*imm(2, 0x14)); W(0x0027)                    # slot 0 = channel 2
                W(*imm(3, 0x14)); W(0x0010); BSR(ca.STUB['StreamAudioSink'])
                W(0x0084); BR(0xF4, "PL_DAC")
                W(0x0427)                                      # st AL,@(4,Y) the sink
                W(0x0014); W(0x0027); W(*imm(0xBB80, 0x14)); W(0x0127)        # SinkConfigure(sink, 0x301, 0:48000)
                W(0x0417); W(*imm(0x301, 0x10)); BSR(ca.STUB['SinkConfigure'])
                W(*imm(6, 0x14)); BSR(KSINK); BSR(ca.STUB['StreamSourceFromSink'])
                W(0x0413); BSR(SCONN)                          # StreamConnect(source of Kalimba port 6, the sink)
                W(0x0084); BR(0xF4, "PL_DAC")
                W(0x0014); W(0x0127); W(0x0027); W(0x0417); W(*imm(0x700, 0x10)); BSR(ca.STUB['SinkConfigure'])      # unmute
            elif VARIANT not in ('p', 'q', 'r'):
                if G.get('CLEARDAC'):
                    # probe295 (AH F2): a cold load of OUR DSP means no valid DAC connection exists, but the stock TTS engine closes the codec sinks and powers the DSP off WITHOUT clearing @0x6d1 bit 15 ("DAC connected"); fn_1f04c then returns 0 at its guard (0x1f051) and the start is silent. Clear the stale bit (the same three instructions as fn_1f12b 0x1f172..0x1f176, with 0x7fff)
                    W(*imm(0x6D1, 0x15)); W(*imm(0x7FFF, 0xC4)); W(*imm(0x6D1, 0x25))
                W(0x0014); W(0x0327); W(0x0527)                  # params = {0, 0xbb80, 0}
                W(*imm(0xBB80, 0x14)); W(0x0427)
                W(0xE415); W(0x0334)
                BSR(FN1F04C)
                W(0x0084); BR(0xF4, "PL_DAC")
                if VARIANT == 'z':
                    # the stock plugin's own gain: volume = high byte of (11,@0x72e) (fn_303c3-0x303d5), gain = fn_22a89(volume) in 1/60 dB, applied by fn_1f5bf(0, gain)
                    W(0x0700, 0x2E19); W(0x0B12); W(0x0009); W(0x08A4); W(0xE015); BSR(0x22A89); W(0xE111); W(0x0014); BSR(0x1F5BF)
                elif VARIANT in ('G', 'u', 'v'):
                    # CONSTANT stock gain: volume index GAIN_N (0..15; gain = (3*n-45) dB via fn_22a89) applied by the stock wrapper fn_1f5bf(0, gain)
                    W(*imm(G.get('PROBE_GAIN_N', GAIN_N), 0x14)); BSR(0x22A89); W(0xE111); W(0x0014); BSR(0x1F5BF)
                else:
                    W(0x0014); W(0x0027); W(0x0010); BSR(0x1F512)    # DAC hardware gain 0 dB
            if STAGE == 3:
                BSR("TEARM")
                W(0xF80F)
            else:
                if VARIANT not in ('f', 'm', 'p', 'q', 'r', 's', 'D', 't', 'u', 'v', 'G'):                 # 5f/5m/5p: the MINIMAL bring-up of J29 (SETPLUGIN, LOADPARAMS, DAC connect, 0x1072, GO): no 0x1002/0x10a0/0x1001/0x1070/0x1071
                    BSR("BRINGUP")                            # AL = 0 or an id
                    W(0x0084); BR(0xF0, "PL_ID")
                if STAGE == 4:
                    BSR("TEARM")
                    W(0xF80F)
                else:
                    # rung 5 (J29: the DSP needs no SBC frame): 0x1072 + pokes + hold, GO, the old noise loop's first poll; running: no teardown, nothing spoken
                    BSR("GOGO")
                    W(0x0084); BR(0xF0, "PL_ID")
                    W(0xF80F)
            LBL("PL_ID")
            if VARIANT == 'v' and G.get('FAILOFF'):
                # probe295 (AH F3): every post-load failure of the product switches the mode OFF (OFFALL: cancel the chains, mute, arm the release) and speaks a distinct id through SPEAKR (it releases OUR hold first): 0x3C "adjust left airbud" = GATE/GO/bring-up refused, 0x3D "noise cancellation only" = DAC connect refused. Neither is a stock prompt of this speaker (earbud/headphone prompts) and neither is intercepted by SPEAKX
                W(*imm(0x3C, 0x14)); BR(0xE0, "PL_F")
                LBL("PL_DAC")
                W(*imm(0x3D, 0x14))
                LBL("PL_F")
                W(0x0527)                                        # st AL,@(5,Y): the id (slots 6,7 hold the return address)
                BSR("MODETOGX")
                W(0x0517); BSR(L['SPEAKR'])
                W(0xF80F)
            else:
                if VARIANT != 'v': BSR("TEARID")
                W(0xF80F)
                LBL("PL_DAC")
                if VARIANT != 'v': W(0x1F14); BSR("TEARID")
                W(0xF80F)

    if STAGE >= 4 and VARIANT not in ('f', 'm', 'p', 'q', 'r', 's', 'D', 't', 'u', 'v', 'G'):
        # ---- SENDLONGS: payloads on the stack (slots 1..10 of a -14 frame): 0x1002 (8 words from slot 1, unchecked) and 0x10a0 (7 words from slot 4, checked). AL = the 0x10a0 result
        BLK(); LBL("SENDLONGS")
        W(0xF20B)
        W(*imm(0x000F, 0x14)); W(0x0127)
        W(*imm(0xFD30, 0x14)); W(0x0227)
        W(0x0014); W(0x0327)
        W(0x0114)
        for k in range(4, 11): W((k << 8) | 0x27)
        W(0xE415); W(0x0134); W(0x0027); W(0x0810); W(*imm(0x1002, 0x14)); BSR(KALLONG)
        if VARIANT != 'v': W(0xE415); W(0x0434); W(0x0027); W(0x0710); W(*imm(0x10A0, 0x14)); BSR(KALLONG)       # v: 0x10a0 is not registered in the Bose DSP (J29: ACKed and dropped): not sent
        W(0xF20F)
        # ---- BRINGUP: SENDLONGS + SETMODE + 0x1070 + 0x1071. AL = 0 or 0x24
        BLK(); LBL("BRINGUP")
        W(0xF80B)
        BSR("SENDLONGS")
        W(0x0084); BR(0xF4, "BU_BAD")
        W(0x0210); W(*imm(0x1001, 0x14)); BSR("PSEND")
        W(0x0084); BR(0xF4, "BU_BAD")
        if VARIANT != 'v':
            W(*imm(0x80, 0x14)); W(0x0027); W(0x0014); W(0x0127); W(0x0227)
            W(*imm(4800, 0x10)); W(*imm(0x1070, 0x14)); BSR(KALMSG)
            W(0x0084); BR(0xF4, "BU_BAD")
            W(*imm(0x640, 0x14)); W(0x0027)
            W(*imm(4800, 0x10)); W(*imm(0x1071, 0x14)); BSR(KALMSG)
            W(0x0084); BR(0xF4, "BU_BAD")
        W(0x0014)
        W(0xF80F)
        LBL("BU_BAD")
        W(0x2414)
        W(0xF80F)

    if STAGE >= 99:      # the silent-SBC-frame feed is NOT needed (J29): kept only as documentation of the abandoned rung
        # ---- MKSBC: AL = StreamRegionSource over a malloc'd silent SBC frame, or 0
        BLK(); LBL("MKSBC")
        W(0xF80B)
        W(*imm(SBC_LEN, 0x14)); BSR(PMALLOC)
        W(0x0527); W(0x051B)
        W(0x0014)
        for k, b in enumerate(SBC):
            if b == 0: W((k << 8) | 0x26)
        for k, b in enumerate(SBC):
            if b != 0: W(*imm(b, 0x14)); W((k << 8) | 0x26)
        W(0x0517); W(*imm(SBC_LEN, 0x10)); BSR(RGNSRC)
        W(0xF80F)
        # ---- FEED: connect the silent frame to Kalimba sink 0. AL = 0 or 0x3A
        BLK(); LBL("FEED")
        W(0xF80B)
        BSR("MKSBC")
        W(0x0084); BR(0xF4, "FD_BAD")
        W(0x0527)
        ca.call1(W, BSR, KSINK, al=('imm', 0))
        W(0x0084); BR(0xF4, "FD_BAD")
        W(0x0127); W(0x0517); W(0x0113); BSR(SCONN)
        W(0x0084); BR(0xF4, "FD_BAD")
        W(0x0014)
        W(0xF80F)
        LBL("FD_BAD")
        W(0x3A14)
        W(0xF80F)

    if G.get('RING512'):
        # ---- RING512 (probe366, owner go 2026-10-28; fable consultant, field log): the tone ring structure DM[0x2A73] = {size, rd, wr} {0x100, 0x100, 0x100} becomes {0x200, 0x200, 0x200}: ring 512 at base 0x200 (a size-aligned block; ring 1 there is unused in the mono path).
        #      Called after GATE (0x1072 purge: the ring is empty) and before GO. ORDER: wr, rd, then size (never the size first: with size 0x200 and pointers at 0x1xx the block would be 0x000-0x1FF and the copy would overwrite DM[0x00..0xFF]).
        #      KalimbaSendMessage 0x7AB3 POKE: AH = address low, slot 0 = address high, slot 1 = value low, slot 2 = value high. Returns AL = 0. No check of the replies (the DSP answers 0x7AB3 with status 0: ignored by the cave handler's unknown-id path).
        BLK(); LBL("RING512")
        W(0xF80B)
        for _a in (0x2A75, 0x2A74, 0x2A73):
            W(0x0014); W(0x0027); W(0x0227); W(*imm(0x200, 0x14)); W(0x0127)
            W(*imm(_a, 0x10)); W(*imm(0x7AB3, 0x14)); BSR(KALMSG)
        W(0x0014)
        W(0xF80F)
    if STAGE >= 5:
        # ---- GOGO: 0x1072 + poke + hold (old GATE), GO, and the first poll of the old noise loop. AL = 0 or 0x24
        BLK(); LBL("GOGO")
        W(0xF80B)
        W(*imm(LEVEL_ID, 0x14)); W(0x0427)                    # slot 4 = the level's MessageId (GATE's poke reads it)
        BSR(L['GATE'])
        W(0x0084); BR(0xF4, "GG_BAD")
        if G.get('RING512'): BSR("RING512")                                                   # probe366: the tone ring 512 samples at base 0x200 (empty, before GO)
        W(0x0010); W(*imm(0x7000, 0x14)); BSR("PSEND")
        W(0x0084); BR(0xF4, "GG_BAD")
        if NEWF: BSR(L['CANCELANY'])                                                      # the poll armed by the press (ARM) must not become a second chain (L1a F3)
        W(*imm(LEVEL_ID, 0x14)); W(*imm(1500, 0x10)); BSR(L['RSEND'])
        if G.get('GEN'): W(*imm(0x1100, 0x14)); W(*imm(50, 0x10)); BSR(L['RSEND'])      # probe380: the generator loader (UNHOOK, enable, PM words, HOOK) starts 20 ms after GO
        if VARIANT == 'f':
            W(*imm(0x28, 0x14)); W(*imm(12000, 0x10)); BSR(L['RSEND'])                    # DIAGA 12 s after GO (the chunk started 1.5 s after GO: chunk + 10.5 s)
            W(*imm(0x29, 0x14)); W(*imm(17500, 0x10)); BSR(L['RSEND'])                    # DIAGB 17.5 s after GO (chunk + 16 s)
        if VARIANT in ('t', 'u', 'v', 'y', 'z', 'G') or EAMP:
            BSR("AMPON")                                                                    # J33/probe258: the stock amp-on message right after GO; the noise loop then runs on
        if VARIANT == 'D':
            W(*imm(0x28, 0x14)); W(*imm(3000, 0x10)); BSR(L['RSEND'])                      # DIAGA 3 s after GO: stop the loop poll, read three candidate volume variables, speak them in octal after the chunk
        if VARIANT == 's':
            W(*imm(0x28, 0x14)); W(*imm(3000, 0x10)); BSR(L['RSEND'])                      # DIAGA 3 s after GO: read PIO5/PIO12, stop the loop, send the stock amp-on message
            W(*imm(0x29, 0x14)); W(*imm(8000, 0x10)); BSR(L['RSEND'])                      # DIAGB 8 s after GO: read them again
        if VARIANT in ('p', 'q', 'r'):
            W(*imm(0x28, 0x14)); W(*imm(4000, 0x10)); BSR(L['RSEND'])                      # DIAGA 4 s after GO
        W(0x0014)
        W(0xF80F)
        LBL("GG_BAD")
        W(0x2414)
        W(0xF80F)
    if VARIANT in ('f', 'w', 'p', 'q', 'r', 's', 'D'):
        # ---- DIAGNOSTIC (rung 5f cold / 5w warm): two snapshots of the Kalimba port quantities, each as three single-digit battery prompts (id 0x27 + digit)
        #   class(v) = 0 if v == 0, 1 if v < 16, 2 if v < 128, else 3
        #   d1 = port 6 (the DSP's DAC-B output): 0 no sink handle, 1 no source behind it, else 2 + class(SourceSize)   -> 2 = nothing waiting, 5 = >= 128 bytes waiting
        #   d2 = Kalimba sink 3 (tone input): 0 no handle, else 1 + class(SinkSlack)                                  -> 1 = FULL (no free room), 4 = >= 128 free
        #   d3 = transform on port 3: 0 no sink, 1 none, 2 present
        SRCSZ, SLACK, TFROM = ca.STUB['SourceSize'], ca.STUB['SinkSlack'], ca.STUB['TransformFromSink']
        SRCFROM = ca.STUB['StreamSourceFromSink']
        BLK(); LBL("CLASS")                                   # AL = value -> AL = 0..3
        W(0x0084); BR(0xF4, "CL_X")
        W(*imm(16, 0x84)); BR(0xFC, "CL_1")
        W(*imm(128, 0x84)); BR(0xFC, "CL_2")
        W(*imm(3, 0x14))
        W(0x00E2)
        LBL("CL_2")
        W(*imm(2, 0x14))
        W(0x00E2)
        LBL("CL_1")
        W(*imm(1, 0x14))
        LBL("CL_X")
        W(0x00E2)
        if VARIANT not in ('p', 'q', 'r', 's', 'D'):
            BLK(); LBL("RDSIZE")                                  # AL = Kalimba port -> 0 no sink handle, 1 no source behind it, else 2 + class(SourceSize)
            W(0xFE0B)
            BSR(KSINK); W(0x0084); BR(0xF4, "RS_0")
            BSR(SRCFROM); W(0x0084); BR(0xF4, "RS_1")
            BSR(SRCSZ); BSR("CLASS"); W(*imm(2, 0x34))
            W(0xFE0F)
            LBL("RS_1")
            W(0x0114)
            W(0xFE0F)
            LBL("RS_0")
            W(0x0014)
            W(0xFE0F)
        BLK(); LBL("SDG")                                     # AL = a digit message id; sends it after the CALLER's slot-3 delay and advances that delay by 4.5 s
        W(0xF80B); W(0x0327)
        W(0x0B13); W(0x0317); BSR(L['RSEND'])                 # ld AH,@(11,Y) (caller slot 3) ; ld AL,@(3,Y) ; RSEND
        W(0x0B17); W(*imm(4500, 0x34)); W(0x0B27)             # caller slot 3 += 4500
        W(0xF80F)
        if VARIANT not in ('p', 'q', 'r', 's', 'D'):
            BLK(); LBL("READ3")                                   # AL = delay (ms) of the first digit; reads d1 d2 d3 and schedules their prompts 4.5 s apart (ids 0x900 + 16*j + digit)
            W(0xF80B); W(0x0327)                                  # slot 3 = delay
            W(*imm(6, 0x14)); BSR("RDSIZE"); W(*imm(0x900, 0x34)); BSR("SDG")
            W(*imm(3, 0x14)); BSR(KSINK); W(0x0084); BR(0xF4, "R3_S0")
            W(0x0427); BSR(SLACK); BSR("CLASS"); W(*imm(1, 0x34))
            BR(0xE0, "R3_S")
            LBL("R3_S0")
            W(0x0014)
            LBL("R3_S")
            W(*imm(0x910, 0x34)); BSR("SDG")
            W(*imm(3, 0x14)); BSR(KSINK); W(0x0084); BR(0xF4, "R3_T0")
            BSR(TFROM); W(0x0084); BR(0xF4, "R3_T1")
            W(0x0114)
            LBL("R3_T1")
            W(*imm(1, 0x34))
            LBL("R3_T0")
            W(*imm(0x920, 0x34)); BSR("SDG")
            W(*imm(1, 0x14)); BSR("DACCON"); W(*imm(0x930, 0x34)); BSR("SDG")      # d4: DAC B (output 1)
            W(0x0014); BSR("DACCON"); W(*imm(0x940, 0x34)); BSR("SDG")             # d5: DAC A (output 0)
            W(0xF80F)
            BLK(); LBL("DACCON")                                  # AL = output index (0 DAC A, 1 DAC B) -> 0 no sink, 1 sink with NO source feeding it, 2 connected
            W(0xFE0B)
            BSR(0x1F371); W(0x0084); BR(0xF4, "DC_0")             # fn_1f371: the stock helper that returns the DAC sink of an output
            BSR(SRCFROM); W(0x0084); BR(0xF4, "DC_1")
            W(0x0214)
            W(0xFE0F)
            LBL("DC_1")
            W(0x0114)
            W(0xFE0F)
            LBL("DC_0")
            W(0x0014)
            W(0xFE0F)
            BLK(); LBL("DIAGA")                                   # in flight (chunk + 10.5 s): stop the loop (never speak while our transform holds port 3), read, speak from +7.5 s
            W(0xF80B)
            BSR(L['CANCELANY'])
            W(*imm(7500, 0x14)); BSR("READ3")
            W(0xF80F)
            BLK(); LBL("DIAGB")                                   # after the chunk should have ended (chunk + 16 s): read, speak from +25.5 s (after DIAGA's five)
            W(0xF80B)
            W(*imm(25500, 0x14)); BSR("READ3")
            W(0xF80F)
        if VARIANT in ('p', 'q', 'r'):
            # ---- OUTPUT-CONTENT PROBE (rung 5p): the DAC is connected only AFTER the read, so port 6 is not drained while we look at it.
            #   CONTENT(mode): AL = 0 no source / no data, 1 fewer than 64 bytes waiting, else 2 + class(number of the first 32 elements that differ from the reference); mode 0 reference = 0, mode 1 reference = the first element
            if VARIANT in ('p', 'r'):
                SRCMAP = ca.STUB['SourceMap']
                BLK(); LBL("CONTENT")
                W(0xF40B); W(0x0327)
                W(*imm(6, 0x14)); BSR(KSINK); W(0x0084); BR(0xF4, "CT_0")
                BSR(SRCFROM); W(0x0084); BR(0xF4, "CT_0")
                W(0x0427)
                BSR(SRCSZ); W(*imm(64, 0x84)); BR(0xFC, "CT_1")
                W(0x0417); BSR(SRCMAP); W(0x0084); BR(0xF4, "CT_0")
                W(0x0527)
                W(0x0014); W(0x0627); W(0x0827)
                W(0x0014); W(0x0727)
                LBL("CT_L")
                W(0x051B); W(0x0016); W(0x0787); BR(0xF4, "CT_S")
                W(0x0617); W(0x0134); W(0x0627)
                LBL("CT_S")
                W(0x0517); W(0x0134); W(0x0527)
                W(0x0817); W(0x0134); W(0x0827); W(*imm(32, 0x84)); BR(0xFC, "CT_L")
                W(0x0617); BSR("CLASS"); W(*imm(2, 0x34)); BR(0xE0, "CT_X")
                LBL("CT_1")
                W(0x0114); BR(0xE0, "CT_X")
                LBL("CT_0")
                W(0x0014)
                LBL("CT_X")
                W(0xF40F)
                BLK(); LBL("READP")                               # AL = delay of the first digit: schedules d1 = port 6 SourceSize class, d2 = CONTENT(0), d3 = CONTENT(1), d4 = transform on port 3
                W(0xF80B); W(0x0327)
                W(0x0014); BSR("CONTENT"); W(*imm(0x900, 0x34)); BSR("SDG")
                W(0xF80F)
            BLK(); LBL("DACLATE")                             # the DAC connect of POSTLOAD, run late (frame -8, parameter block in slots 3..5)
            W(0xF80B)
            W(0x0014); W(0x0327); W(0x0527)
            W(*imm(0xBB80, 0x14)); W(0x0427)
            W(0xE415); W(0x0334)
            BSR(FN1F04C)
            W(0x0084); BR(0xF4, "DL_X")
            W(0x0014); W(0x0027); W(0x0010); BSR(0x1F512)
            LBL("DL_X")
            W(0xF80F)
            BLK(); LBL("DIAGA")                               # GO + 4 s: stop the loop, read port 6 BEFORE the DAC drains it, then connect the DAC and speak 21 s later (the chunk has ended by then)
            W(0xF80B)
            BSR(L['CANCELANY'])
            if VARIANT in ('p', 'r'):
                W(*imm(21000, 0x14)); BSR("READP")
            else:
                W(*imm(0x900, 0x14)); W(*imm(21000, 0x10)); BSR(L['RSEND'])       # q: one fixed prompt (battery 10%) 21 s later
            BSR("DACLATE")
            W(0xF80F)
            if VARIANT in ('q', 'r'):
                BLK(); LBL("IDLOG")                           # AL = a MessageId that reached AUTOSTART: speak it as five octal digits (low first) from +35 s, 4.5 s apart
                W(0xF80B); W(0x0427)
                W(*imm(35000, 0x14)); W(0x0327)
                for _k in range(3):
                    W(0x0417); W(0x07C4); W(*imm(0x900, 0x34)); BSR("SDG")
                    W(0x0417); W(0x0009); W(0x03A4); W(0x0427)
                W(0xF80F)
    if VARIANT in ('u', 'v') and not DIAG and not G.get('NOSPEAKX'):
        # ---- SPEAKX: SPEAKR's bsr to the stock speak function is retargeted here. The old poll says 0x21 "call ended" and stops the loop when the DSP has VANISHED (probe269 long run: the stock unloaded it about 13.7 minutes after
        #      the Bluetooth link went away). In the product that is a restart, not a prompt: arm stage B (the cold bring-up) in 1.5 s instead of speaking 0x21. Every other id goes to the stock speak function unchanged.
        BLK(); LBL("SPEAKX")
        W(0xFE0B)
        W(*imm(0x10, 0x84)); BR(0xF4, "SX_C")           # 0x10 "and": StreamKalimbaSink(3) = 0, the DSP is GONE (seen on the unit)
        W(*imm(0x21, 0x84)); BR(0xF4, "SX_C")           # 0x21 "call ended": GATE false
        W(*imm(0x25, 0x84)); BR(0xF4, "SX_C")           # 0x25 "call with": the transform was refused
        W(*imm(0x3B, 0x84)); BR(0xF0, "SX_S")           # 0x3B "adjust airbuds": the payload check failed; anything else is spoken
        LBL("SX_C")
        W(*imm(0x2C, 0x14)); W(*imm(1500, 0x10)); BSR(L['RSEND'])      # every exit of the old loop is a restart request: ENSURE in 1.5 s (cold bring-up if the DSP is gone, else amp-on and a new poll)
        W(0xFE0F)
        LBL("SX_S")
        BSR(SPEAK)
        W(0xFE0F)
    if VARIANT in ('u', 'v'):
        # ---- MODETOGX: the product's centre-long-press handler (TRIG's bsr to MODETOG is retargeted here). The old MODETOG toggles the mode flag (ON arms a first poll); then:
        #      mode ON and no DSP loaded (GATE FALSE): cancel that poll and start the COLD bring-up (stage B 1.5 s later); mode ON and a DSP loaded: send the amp-on message (idempotent).
        if G.get('DEEPSLEEP'):
            BLK(); LBL("DSLEEP")                                                # AL = mode: VmDeepSleepEnable(mode == 0), AL preserved
            W(0xFC0B); W(0x0027)
            W(0x0084); BR(0xF4, "DS_1")
            W(0x0014); BR(0xE0, "DS_C")
            LBL("DS_1"); W(0x0114)
            LBL("DS_C"); BSR(ca.STUB['VmDeepSleepEnable'])
            W(0x0017); W(0xFC0F)
        BLK(); LBL("MODETOGX")
        W(0xF80B)
        if G.get('CENSUS'):
            BSR("CENSUSX"); W(0x0084); BR(0xF4, "MX_N")                       # probe288: an idle press that finds residue speaks the census and changes NOTHING (no toggle, no start)
            W(0xF80F)
            LBL("MX_N")
        if G.get('DACREL2'): W(*imm(REL2_ID, 0x10)); W(*imm(TASK_ADDR, 0x14)); BSR(CANCELFIRST)
        W(*imm(0x13, 0x10)); W(*imm(TASK_ADDR, 0x14)); BSR(CANCELFIRST)        # a delayed hold release armed by an earlier OFF (REL_ID) must not fire under a new loop (rule R6); an OFF below arms it again
        BSR(L['MODETOG'])
        BSR(L['PEEKMODE'])
        if G.get('LEDCYCLE'): BSR("LEDSTART")                                  # probe356: AL = the mode, preserved
        if G.get('LEDDARK'): BSR("LEDDARK")                                    # probe357: AL = the mode, preserved
        if G.get('DEEPSLEEP'): BSR("DSLEEP")                                     # probe339: AL = the mode (1 ON, 0 OFF), preserved: VmDeepSleepEnable(0) while the noise plays, (1) at the OFF
        if G.get('CSTOCK'): BSR("CSTOCK")                                        # probe335: cancel the stock message ids CSTOCK_LO..CSTOCK_HI of task 0x512 (AL, the mode, is preserved)
        if G.get('SILENTDROP'): BSR("SILMUTE")                                  # probe386/387: AL = the mode, preserved: ON -> the stock prompt-enable bit is cleared for 8 s so that the press-initiated disconnect announcement stays silent
        if G.get('SCAN'): BSR(G['SCAN_ADDR']['SCANSYNC'])                       # probe323: AL = the mode (1 ON, 0 OFF), preserved: ON -> Bluetooth scans off; OFF -> the stock scans back on (state 1: page; state 2: page + inquiry)
        W(0x0084); BR(0xF4, "MX_O" if NEWF else "MX_X")
        if G.get('DIAG6'):
            # probe286 DIAGNOSTIC (start press only), through the existing SPEAK: id 0x27 = no Kalimba sink on port 3 (no DSP resident, the cold path), id 0x29 = a Kalimba sink exists (a DSP is resident: the warm path)
            W(*imm(3, 0x14)); BSR(KSINK); W(0x0084); W(*imm(0x27, 0x14)); BR(0xF4, "DG_3")
            W(0x0214); W(*imm(0x29, 0x14))
            LBL("DG_3")
            BSR(SPEAK)
        if VARIANT == 'v' and not G.get('NOWATCH'):
            W(*imm(0x2D, 0x10)); W(*imm(TASK_ADDR, 0x14)); BSR(CANCELFIRST)    # the watchdog chain (WATCH_MS) is armed once per ON
            W(*imm(0x2D, 0x14)); W(*imm(WMS, 0x10)); BSR(L['RSEND'])
        if G.get('STARTWAIT'): BSR("SWGATE"); W(0x0084); BR(0xF4, "MX_G"); BSR(L['CANCELANY']); LBL("MX_G")      # probe384: the stock owns the DSP: the first poll (a level POKE into it) is cancelled; the ENSURE that passes the gate re-creates the poll (its EN_D path)
        W(*imm(0x2C, 0x14)); W(*imm(500, 0x10)); BSR(L['RSEND'])             # ENSURE in 0.5 s: no DSP -> the cold bring-up; a DSP loaded -> amp-on (the old poll armed by MODETOG plays)
        if G.get('STARTWAIT'): W(*imm(0x2F, 0x14)); W(*imm(40000, 0x10)); BSR(L['RSEND'])       # probe384: the closer: 40 s after the press ENSURE runs with the gate skipped
        if NEWF:
            BR(0xE0, "MX_X")
            LBL("MX_O")
            BSR("OFFALL")                                                      # OFF (press, power-off or yield): everything pending is cancelled, the tone is muted at once (L1a F1, F3, F8)
            if G.get('TMREARM'): BSR(0x12ABB)                                  # probe358: the stock per-sinkState timer manager fn_12abb re-arms the idle power-off timers that TIMERS cancelled
        LBL("MX_X")
        W(0xF80F)
    if VARIANT == 'v':
        # ---- ENSURE: "make the noise run if the mode is ON" (armed 4 s after an SLC disconnect). Mode OFF: nothing. A DSP is loaded (GATE TRUE): cancel the pending hold release, amp-on, restart the poll like the old auto-start.
        #      No DSP (GATE FALSE): the cold bring-up again (stage B in 1.5 s).
        BLK(); LBL("ENSURE")                                                    # AL = 0: called by the WATCHDOG (a busy port means the loop is healthy: nothing to do); AL != 0: a restart request (0x2C): a busy port is retried every second
        W(0xF80B); W(0x0327)
        BSR(L['PEEKMODE'])
        W(0x0084); BR(0xF4, "EN_X")
        if NEWF and not G.get('LEAN'):
            BSR(G['GETBUSY']); W(0x0084); BR(0xF4, "EN_B")                   # a stock prompt or tone owns the audio-busy word: leave the DSP alone, look again (L1a F5)
            W(*imm(TASK_ADDR, 0x84)); BR(0xF0, "EN_R")
            LBL("EN_B")
        if G.get('STARTWAIT'):
            # probe384: never PM-write / poke into a DSP the STOCK owns (blk[24] != 0 or sinkState >= 3): look again in 1 s (the 0x2F closer, armed by the press, forces the start after 40 s)
            W(0x0317); W(*imm(0x2F, 0x84)); BR(0xF4, "EN_F")
            BSR("SWGATE"); W(0x0084); BR(0xF0, "EN_R")
            LBL("EN_F")
            W(*imm(0x2F, 0x10)); W(*imm(TASK_ADDR, 0x14)); BSR(CANCELFIRST)
        W(*imm(3, 0x14)); BSR(KSINK); W(0x0084); BR(0xF4, "EN_C")                 # StreamKalimbaSink(3) = 0: no DSP
        if not G.get('GEN'):
            BSR(ca.STUB['TransformFromSink']); W(0x0084); BR(0xF0, "EN_R")             # a chunk still on port 3: look again in 1 s (rule R1: no 0x1072 / SPEAK / reload while it plays)
        W(*imm(LEVEL_ID, 0x14)); W(0x0427); BSR(L['GATE']); W(0x0084); BR(0xF0, "EN_W")   # GATE (slot 4 = the level id): TRUE iff a .kap is loaded
        LBL("EN_C")
        if DIAG: W(*imm(0x27, 0x14)); BSR(L['SPEAKR'])                       # test code 1 (battery 10%): the watchdog found NO DSP
        W(*imm(STG_B, 0x10)); W(*imm(TASK_ADDR, 0x14)); BSR(CANCELFIRST)      # at most ONE stage-B request pending
        W(*imm(STG_B, 0x14)); W(*imm(1500, 0x10)); BSR(L['RSEND'])
        if NEWF:
            W(*imm(COLD_ID, 0x10)); W(*imm(TASK_ADDR, 0x14)); BSR(CANCELFIRST)    # the DSP will be OURS: the cold-owned flag (re-armed by WATCH)
            W(*imm(COLD_ID, 0x14)); W(*imm(FLAG_MS, 0x10)); BSR(L['RSEND'])
        LBL("EN_X")
        W(0xF80F)
        LBL("EN_R")
        W(0x0317); W(0x0084); BR(0xF4, "EN_X")                                 # the watchdog (AL = 0): a chunk on port 3 = healthy, done
        W(*imm(0x2C, 0x14)); W(*imm(500 if G.get('SILENTDROP') else 1000, 0x10)); BSR(L['RSEND'])
        W(0xF80F)
        LBL("EN_W")
        BSR("ENSURE2")
        W(0xF80F)
        BLK(); LBL("ENSURE2")                                                  # (split off ENSURE so that the blocks fit the small clusters of the cave)
        W(0xF80B)
        W(*imm(0x13, 0x10)); W(*imm(TASK_ADDR, 0x14)); BSR(CANCELFIRST)        # REL_ID: the release armed by the disconnect's STOPT must not drop our hold under the restarted loop
        BSR(L['CANCELANY'])                                                    # a DSP is loaded and port 3 is free: is the poll chain alive?
        W(0x0084); BR(0xF4, "EN_D")
        W(*imm(G['LEVEL_BASE'] - 1, 0x34)); W(*imm(50, 0x10)); BSR(L['RSEND'])      # alive (between two chunks or just armed by the press): put the poll back
        BSR("AMPON")                                                           # and make sure the amplifier is on (idempotent: the stock checks fn_0f215)
        if G.get('NOREWR'):
            W(*imm(0x24, 0x10)); W(*imm(TASK_ADDR, 0x14)); BSR(CANCELFIRST); W(0x0084); BR(0xF4, "EN_J")      # probe388: GENF pending = the generator was written moments ago (the redundant ENSURE of the 0x4716 event): put it back and do not rewrite
            W(*imm(0x24, 0x14)); W(*imm(8000, 0x10)); BSR(L['RSEND']); BR(0xE0, "EN_K")
            LBL("EN_J")
        if G.get('GEN'): W(*imm(0x1100, 0x14)); W(*imm(50, 0x10)); BSR(L['RSEND'])      # probe380: (re)write and hook the generator (UNHOOK first)
        if G.get('NOREWR'): LBL("EN_K")
        W(0xF80F)
        LBL("EN_D")
        if DIAG: W(*imm(0x28, 0x14)); BSR(L['SPEAKR'])                       # test code 2 (battery 20%): DSP loaded, port free, NO poll pending = the loop was dead
        BSR("AMPON")
        if G.get('GEN'): W(*imm(0x1100, 0x14)); W(*imm(50, 0x10)); BSR(L['RSEND'])
        W(*imm(0x20, 0x14)); BSR(L['AUTOSTART'])
        W(0xF80F)
        if G.get('SILENTDROP'):
            # probe386/387: the stock speak core fn_0df01 returns at once when bit 13 of @0x570 (voice prompts on) is clear (0x0df06..0x0df0c). The press-initiated drop makes the stock say '<name> disconnected':
            # clear that bit just before the drop (only when it is set: a user who turned prompts off is left alone) and put it back 8 s later (id 0x32). RAM only: the stock saves the setting to PS only from its own prompts-toggle.
            BLK(); LBL("SILMUTE")                                              # AL = the mode (1 ON): preserved (enterl -4: slots 0 and 1 are ours, 2 and 3 the saved return address)
            W(0xFC0B); W(0x0027)
            W(0x0084); BR(0xF4, "SM_X")                                        # mode OFF: nothing
            W(*imm(0x570, 0x15)); W(*imm(0x2000, 0xC4)); W(0x0084); BR(0xF4, "SM_X")      # prompts already off: nothing, and no restore
            W(*imm(0x570, 0x15)); W(*imm(0xDFFF, 0xC4)); W(*imm(0x570, 0x25))
            W(*imm(0x32, 0x10)); W(*imm(TASK_ADDR, 0x14)); BSR(CANCELFIRST)    # at most one restore pending
            W(*imm(0x32, 0x14)); W(*imm(8000, 0x10)); BSR(L['RSEND'])
            LBL("SM_X")
            W(0x0017); W(0xFC0F)
            BLK(); LBL("SILRST")
            W(0xFE0B)
            W(*imm(0x570, 0x15)); W(*imm(0x2000, 0xB4)); W(*imm(0x570, 0x25))   # or AL,#0x2000
            W(0xFE0F)
        if G.get('STARTWAIT'):
            BLK(); LBL("SWGATE")                                               # probe384: AL = 1 = WAIT (sinkState >= 3, or the stock plugin owns a DSP: blk[24] != 0), else 0; read only
            W(0xFE0B)
            W(*imm(0x59E, 0x15)); W(*imm(3, 0x84)); BR(0xF8, "SW_W")
            W(*imm(0x72B, 0x19)); W(0x1816); W(0x0084); BR(0xF4, "SW_X")
            LBL("SW_W"); W(0x0114)
            LBL("SW_X")
            W(0xFE0F)
        # ---- WATCH: the product's watchdog, every 10 s while the mode is ON (armed by MODETOGX): re-arm itself, then the ENSURE check (any cause that stops the loop is healed within ~10 s)
        if not G.get('NOWATCH'):
          BLK(); LBL("WATCH")
          W(0xF80B)
          BSR(L['PEEKMODE'])
          W(0x0084); BR(0xF4, "WT_X")
          if G.get('CSTOCK'): BSR("CSTOCK")                                      # probe335: again every watchdog tick (a stock chain that re-armed itself is cancelled again)
          if G.get('SCAN'): BSR(G['SCAN_ADDR']['SCANSYNC'])                       # probe323: AL = 1 (mode ON): the stock turned a scan back on (link loss, disconnect)? off again; sends nothing when both bits are clear
          W(*imm(0x2D, 0x14)); W(*imm(WMS, 0x10)); BSR(L['RSEND'])
          if NEWF: W(*imm(COLD_ID, 0x14)); BSR("PEEKF")                           # keep the cold-owned flag alive while it is set
          if not G.get('GEN'): W(0x0014); BSR("ENSURE")                           # AL = 0: watchdog mode (GEN: the heartbeat poll is the liveness check)
          LBL("WT_X")
          W(0xF80F)
    if VARIANT == 'v' and NEWF:
        # ---- OFFALL (L1a F1/F3/F8): the one OFF routine. Cancel the delayed stage-B load (0x26), the auto-start (0x20), the watchdog (0x2D), the restart check (0x2C) and the cold-owned flag (0x2E);
        #      cancel EVERY pending poll (a loop at CANCELANY); always arm the delayed release of our audio-busy hold; mute the tone.
        BLK(); LBL("OFFALL")
        W(0xF80B)
        if G.get('DACREL2'):
            # probe287 (agent O: fn_1f04c returns 0 when OUR DAC connection is still up and the stock plugin then PanicNulls = a reboot): when the DSP is OURS (cold-owned flag pending) remember it; the release 16 s later (after the last chunk) then also undoes the DAC connection (REL2_ID), never at the OFF itself (probe279 ran fn_1f12b at the OFF and wedged on the stop and power-off)
            W(*imm(COLD_ID, 0x14)); BSR("PEEKF"); W(0x0327)
        if G.get('DACREL'):
            # probe279 (K3 hypothesis 2): when the DSP is OURS (cold-owned flag pending) undo OUR DAC connection (fn_1f04c) the way every stock teardown does (fn_1f12b), so the stock A2DP connect can claim the DAC
            W(*imm(COLD_ID, 0x14)); BSR("PEEKF"); W(0x0084); BR(0xF4, "OA_N")
            BSR(FN1F12B)
            LBL("OA_N")
        if G.get('OFFLOOP'):
            # one loop cancels every cave message id 0x20..0x2E (auto-start 0x20, stage B 0x26, restart check 0x2C, watchdog 0x2D, cold flag 0x2E; the others are unused in the product): 12 words instead of 35
            W(*imm(0x20, 0x14)); W(0x0427)
            LBL("OA_C")
            W(0x0413 if G.get('CANCELALL') else 0x0412); W(*imm(TASK_ADDR, 0x14)); BSR(0x395E7 if G.get('CANCELALL') else CANCELFIRST)      # probe295 (AH F4/I6): CANCELALL = the library MessageCancelAll(AL = task, AH = id), a loop of CancelFirst: a duplicate chain of an id does not survive an OFF. ALSO FIXES a latent defect of the OFFLOOP of probes 287/288 (kept byte-for-byte for them): 0x0412 is `ld AH,@(4,X)` (X = the link register = a code address), not `ld AH,@(4,Y)` = 0x0413, so their loop cancelled garbage ids (cavesim: 0, then 0x76 x14), not 0x20..0x2E
            W(0x0417); W(*imm(1, 0x34)); W(0x0427); W(*imm(0x2E if G.get('DACREL3') else (0x30 if G.get('STARTWAIT') else 0x2F), 0x84)); BR(0xFC, "OA_C")
        else:
          for _id in ((STG_B, G['AUTO_ID'], 0x2D, 0x2C) if G.get('DACREL3') else (STG_B, G['AUTO_ID'], 0x2D, 0x2C, COLD_ID)):
            W(*imm(_id, 0x10)); W(*imm(TASK_ADDR, 0x14)); BSR(CANCELFIRST)
        LBL("OA_L")
        BSR(L['CANCELANY']); W(0x0084); BR(0xF0, "OA_L")
        W(*imm(G['REL_ID'], 0x10)); W(*imm(TASK_ADDR, 0x14)); BSR(CANCELFIRST)
        if G.get('DACREL2'):
            W(*imm(REL2_ID, 0x10)); W(*imm(TASK_ADDR, 0x14)); BSR(CANCELFIRST)
            W(0x0317); W(0x0084); BR(0xF4, "OA_1")
            W(*imm(REL2_ID, 0x14)); BR(0xE0, "OA_R")
            LBL("OA_1")
            W(*imm(G['REL_ID'], 0x14))
            LBL("OA_R")
            W(*imm(G['RELEASE_MS'], 0x10)); BSR(L['RSEND'])
        else:
            W(*imm(G['REL_ID'], 0x14)); W(*imm(G['RELEASE_MS'], 0x10)); BSR(L['RSEND'])
        BSR("MUTE")
        W(0xF80F)
        # ---- MUTE: tone mix ratio M[0x28f6] := 0 (KalimbaSendMessage 0x7AB3): the tone is silent at once, the music path is untouched; the next poll's POKE restores the ratio
        BLK(); LBL("MUTE")
        W(0xF80B)
        W(*imm(3, 0x14)); BSR(KSINK); W(0x0084); BR(0xF4, "MU_X")                 # no Kalimba sink on port 3: no DSP of ours to write into (L1a F5)
        W(0x0014); W(0x0027); W(0x0127); W(0x0227)
        W(*imm(0x28F6, 0x10)); W(*imm(0x7AB3, 0x14)); BSR(KALMSG)
        if G.get('GEN'): W(*imm(0x16C3, 0x14)); BSR("HOOKP")                       # probe380: the stock tone-copy handler back (M[0x8367] := 0x16C3) at every OFF/MUTE
        LBL("MU_X")
        W(0xF80F)
        if G.get('PWRREL2'):
            # ---- RELFREE (probe428): release OUR audio-busy hold only when port 3 has no transform. StreamKalimbaSink(3) = 0 (no DSP: nothing of ours can be in flight) or
            #      TransformFromSink(ksink) = 0 (the port is free: the same read-only test the handler makes before every rebuild) -> RELEASE0 (SetAudioBusy(0) iff the word is our task).
            #      A transform on the port (ours in flight, or a stock tone's): nothing; the REL timer releases 16 s after the OFF as before. Read-only traps and one conditional write; no message, no DSP write.
            BLK(); LBL("RELFREE")
            W(0xFE0B)                                                                 # enterl -2 (no local slot: nothing is stored)
            W(*imm(3, 0x14)); BSR(KSINK); W(0x0084); BR(0xF4, "RF_R")                 # ksink = StreamKalimbaSink(3); 0 -> release
            BSR(ca.STUB['TransformFromSink']); W(0x0084); BR(0xF0, "RF_X")           # AL = ksink still (cmp leaves it); a transform holds the port -> keep the hold
            LBL("RF_R")
            BSR(L['RELEASE0'])
            LBL("RF_X")
            W(0xFE0F)
        # ---- PEEKF: AL = a flag message id; AL = 1 if it is pending (put back at once for FLAG_MS), else 0
        if not (G.get('NOYIELD') and G.get('NOWATCH') and not (G.get('DACREL') or G.get('DACREL2') or G.get('DACREL3'))):      # probe288 (CENSUS) reads the cold flag destructively and needs no PEEKF
          BLK(); LBL("PEEKF")
          W(0xF80B); W(0x0327)
          W(0x0313); W(*imm(TASK_ADDR, 0x14)); BSR(CANCELFIRST)
          W(0x0084); BR(0xF4, "PF_X")
          W(0x0317); W(*imm(FLAG_MS, 0x10)); BSR(L['RSEND'])
          W(0x0114)
          LBL("PF_X")
          W(0xF80F)
    if G.get('CENSUS'):
        # ---- ADDIF: AL = a value, AH = a weight; the CALLER's slot 3 (the accumulator) += weight when AL != 0
        BLK(); LBL("ADDIF")
        W(0xFC0B); W(0x0023)                                                # enterl -4: slots 0,1 are free, 2,3 the return address
        W(0x0084); BR(0xF4, "AI_X")
        W(0x0717); W(0x0037); W(0x0727)                                     # ld AL,@(4+3,Y) ; add AL,@(0,Y) ; st AL,@(4+3,Y)
        LBL("AI_X")
        W(0xFC0F)
        # ---- CENSUSX (probe288, read-only): AL = 1 if the census was taken, else 0. No census while a transform holds port 3 (CLAUDE.md rule 4), and none on a CLEAN idle state (no mode flag, cold flag, Kalimba
        #      sink, busy hold or DAC link): that press is the normal cold start. Otherwise two digit messages (0x900 + d1, d2) are scheduled 1.5 / 6 s later (SPEAKD speaks battery (d+1)*10 percent).
        #      d1 = SINK (the cold-owned flag is NOT read: OFFALL always cancels it and, without WATCH, it lives only 20 s after a cold start; the mode is always OFF when a census is spoken) ; d2 = BUSY (1 = the busy word is OUR task, else 0) + 2*DAC (@0x6d1 bit 15) 
        BLK(); LBL("CENSUSX")
        W(0xF80B)
        BSR(L['PEEKMODE']); W(0x0084); BR(0xF0, "CN_NO")                     # the mode is ON (running, or just started): the normal path (a stop press is never turned into a census)
        W(*imm(3, 0x14)); BSR(KSINK); W(0x0084); BR(0xF4, "CN_A")
        BSR(ca.STUB['TransformFromSink']); W(0x0084); BR(0xF0, "CN_NO")      # a transform on port 3: nothing is spoken, the normal path runs
        LBL("CN_A")
        BSR("CENSUSY")
        LBL("CN_X")
        W(0xF80F)
        LBL("CN_NO")
        W(0x0014); BR(0xE0, "CN_X")
        BLK(); LBL("CENSUSY")
        W(0xF80B)
        BSR("DIG1"); W(0x0427)
        BSR("DIG2"); W(0x0527)
        W(0x0417); W(0x0537)                                                # d1 + d2 == 0: a clean state, the press is a normal start
        W(0x0084); BR(0xF4, "CN_NO2")
        for _s, _d in ((4, 1500), (5, 6000)):
            W((_s << 8) | 0x17); W(*imm(0x900, 0x34)); W(*imm(_d, 0x10)); BSR(L['RSEND'])
        W(0x0114)
        W(0xF80F)
        LBL("CN_NO2")
        W(0x0014)
        W(0xF80F)
        BLK(); LBL("DIG1")
        W(0xF80B)
        W(*imm(3, 0x14)); BSR(KSINK); W(0x0084); BR(0xF4, "D1_X")           # d1 = 1 if StreamKalimbaSink(3) != 0 (a DSP is resident)
        W(0x0114)
        LBL("D1_X")
        W(0xF80F)
        BLK(); LBL("DIG2")
        W(0xF80B)
        W(0x0014); W(0x0327)
        BSR(G['GETBUSY']); W(*imm(TASK_ADDR, 0x84)); BR(0xF0, "CN_B")
        W(0x0114); W(*imm(1, 0x10)); BSR("ADDIF")                           # the audio-busy word is OUR task (the cave's hold): +1
        LBL("CN_B")
        W(*imm(0x6D1, 0x15)); W(*imm(0x8000, 0xC4)); W(*imm(2, 0x10)); BSR("ADDIF")
        W(0x0317)
        W(0xF80F)
    if G.get('GEN'):
        # ---- GEN LOADER (probe380; owner go 2026-10-28; fable design): the DSP-side brown-noise generator build/dsp/noisegen.bin (linked at PM 0x2A00) is written into DSP program memory through the PM window at every
        #      noise start, then hooked into the tone-copy timer (M[0x8367] := 0x2A00, the 16-bit sign-extended form of DM2 0xFF8367). The program is a DATA TABLE in eight whole window bands (see ladder_core GEN_TABLE_AT):
        #      slot j holds 7 PM words as (hi16, lo16) pairs; slot j lives 0x20 words after slot j-1 (the 3-word band at slot 3 is not a slot), so chunk c uses slot j = c + (c >= 3).
        #      Messages to the cave task: 0x1100 = UNHOOK (M[0x8367] := 0x16C3) + PM_WIN_ENABLE (M[0xFE65] := 1); 0x1101 = UNHOOK again; 0x1102 + c = chunk c (7 PM words); 0x1102 + NCH = HOOK; 0x1103 + NCH = HOOK again
        #      (covers a race with the timer reschedule store). One id per 50 ms (the project poll floor, rule R5); every id checks that the mode is still ON.
        NCH_T = 7                                              # chunks served from the data table (7 PM words each)
        if G.get('TABLEX'): NCH_T = (G['GEN_NW'] + 6) // 7     # probe405: the table has 11 slots; chunks 0..NCH_T-1 are served from it (slot j = c + (c >= 3) + (c >= 8))
        _GX = G.get('GEN_EXTRA') or ()
        NCHX = (len(_GX) + 6) // 7                             # probe395 (NOISEGEN2): extra chunks of 7 PM words loaded straight from cave immediates
        NCH = NCH_T + NCHX
        assert 0x1103 + NCH < 0x1110
        _base_data = ca.const_addr(G['GEN_TABLE_AT'][0])
        assert 0x7400 <= _base_data <= 0xD39A - 0x20 * (13 if G.get('TABLEX') else 8), hex(_base_data)
        if G.get('TABLEX'): assert not G.get('GEN_EXTRA') and NCH_T <= 7 + len(G['GEN_TABLE_AT']) - 7 and NCHX == 0 and G['GEN_NW'] <= 7 * len(G['GEN_TABLE_AT'])
        BLK(); LBL("GLDPUT")                                  # AL = hi16, AH = lo16 of one PM word; the PM address is the CALLER's slot 3 (caller slot 3 = @(11,Y)); LO half (window 3) then HI half (window 2); address += 1
        W(0xF80B)
        W(0x0427); W(0x0523)
        W(0x0014); W(0x0227)
        W(*imm(3, 0x14)); W(0x0027)
        W(0x0517); W(0x0127)
        W(0x0B13)
        W(*imm(0x7AB3, 0x14)); BSR(KALMSG)
        W(*imm(2, 0x14)); W(0x0027)
        W(0x0417); W(0x0127)
        W(0x0B13)
        W(*imm(0x7AB3, 0x14)); BSR(KALMSG)
        W(0x0B17); W(*imm(1, 0x34)); W(0x0B27)
        W(0xF80F)
        BLK(); LBL("GLRUN")                                   # AL = chunk c: 7 PM words from slot j = c + (c >= 3) to PM 0x2A00 + 7 c
        W(0xF80B)
        W(0x0427)                                             # slot 4 = c
        W(0x03A0); W(0x0457)                                  # asl #3 ; sub AL,@(4,Y) : 7 c
        W(*imm(0x2A00, 0x34)); W(0x0327)                      # slot 3 = the PM address of the chunk's first word (GLDPUT's caller slot 3)
        W(0x0417); W(*imm(3, 0x84)); BR(0xFC, "GR_A")
        W(*imm(1, 0x34))                                      # c >= 3: slot j = c + 1
        LBL("GR_A")
        if G.get('TABLEX'):
            W(*imm(9, 0x84)); BR(0xFC, "GR_B"); W(*imm(1, 0x34))      # j >= 9 (c >= 8): skip the 9-word band (slot 9 at 0x3E35D+..): slot j = c + 2
            LBL("GR_B")
        W(0x05A0); W(*imm(_base_data, 0x34)); W(0x0527)       # asl #5 ; add the data pointer of slot 0 ; slot 5 = the pointer
        W(*imm(7, 0x14)); W(0x0427)                           # slot 4 = the word counter
        LBL("GR_L")
        W(0x051B); W(0x0016); W(0x0112)                       # ld X,@(5,Y) ; ld AL,@(0,X) hi16 ; ld AH,@(1,X) lo16
        BSR("GLDPUT")
        W(0x0517); W(*imm(2, 0x34)); W(0x0527)               # pointer += 2
        W(0x0417); W(*imm(0xFFFF, 0x34)); W(0x0427)           # counter -= 1
        W(0x0084); BR(0xF0, "GR_L")
        W(0xF80F)
        _GLXV = os.environ.get('GLX_VARIANT', 'direct') if NCHX else ''
        if NCHX and _GLXV == 'direct':
            for _k in range(NCHX):
                BLK(); LBL("GLX%d" % _k)                      # PM words 7*(7+k) .. +6 of the generator from immediates: slot 3 = the PM address, then (AL = hi16, AH = lo16, GLDPUT) per word
                W(0xF80B)
                W(*imm(0x2A00 + 7 * (NCH_T + _k), 0x14)); W(0x0327)
                for _hi, _lo in _GX[7 * _k:7 * _k + 7]:
                    W(*imm(_hi, 0x14)); W(*imm(_lo, 0x10)); BSR("GLDPUT")
                W(0xF80F)
        elif NCHX:
            _SPLIT = ((0, 4), (4, 7)) if _GLXV == 'split' else ((0, 7),)
            BLK(); LBL("GLRUNX")                              # AL = chunk c >= 7: dispatch to the straight-line blocks GLX(c - 7) (a / b)
            W(0xF80B)
            W(0x0427)                                         # slot 4 = c
            for _k in range(NCHX):
                W(0x0417); W(*imm(NCH_T + _k, 0x84)); BR(0xF0, "GX_%d" % (_k + 1))
                for _nm in "ab"[:len(_SPLIT)]: BSR("GLX%d%s" % (_k, _nm))
                BR(0xE0, "GX_END")
                LBL("GX_%d" % (_k + 1))
            LBL("GX_END")
            W(0xF80F)
            for _k in range(NCHX):
                for _nm, (_i0, _i1) in zip("ab", _SPLIT):
                    BLK(); LBL("GLX%d%s" % (_k, _nm))
                    W(0xF80B)
                    W(*imm(0x2A00 + 7 * (NCH_T + _k) + _i0, 0x14)); W(0x0327)
                    for _hi, _lo in _GX[7 * _k + _i0:min(7 * _k + _i1, len(_GX))]:
                        W(*imm(_hi, 0x14)); W(*imm(_lo, 0x10)); BSR("GLDPUT")
                    W(0xF80F)
        BLK(); LBL("HOOKP")                                   # AL = the value: POKE M[0x8367] := AL (the tone-copy timer handler pointer)
        W(0xF80B)
        W(0x0127)
        W(0x0014); W(0x0027); W(0x0227)
        W(*imm(0x8367, 0x10)); W(*imm(0x7AB3, 0x14)); BSR(KALMSG)
        W(0xF80F)
        BLK(); LBL("GLDM")                                    # AL = the message id 0x1100 ..
        W(0xF80B); W(0x0327)
        BSR(L['PEEKMODE']); W(0x0084); BR(0xF0, "GM_ON")
        W(0xF80F)                                             # the mode went OFF: the chain ends here
        LBL("GM_ON")
        W(0x0317); W(*imm(0x1100, 0x84)); BR(0xF0, "GM_1")
        if G.get('NOREWR'):
            W(*imm(0x24, 0x10)); W(*imm(TASK_ADDR, 0x14)); BSR(CANCELFIRST)        # probe388: GENF, 'a generator write is fresh': at most one pending
            W(*imm(0x24, 0x14)); W(*imm(8000, 0x10)); BSR(L['RSEND'])
        W(0x0014); W(0x0027); W(0x0227); W(*imm(1, 0x14)); W(0x0127); W(*imm(0xFE65, 0x10)); W(*imm(0x7AB3, 0x14)); BSR(KALMSG)       # PM_WIN_ENABLE := 1
        W(*imm(0x16C3, 0x14)); BSR("HOOKP"); BR(0xE0, "GM_N")
        LBL("GM_1")
        W(0x0317); W(*imm(0x1101, 0x84)); BR(0xF0, "GM_2")
        W(*imm(0x16C3, 0x14)); BSR("HOOKP"); BR(0xE0, "GM_N")
        LBL("GM_2")
        W(*imm(0x1102 + NCH, 0x84)); BR(0xFC, "GM_C")         # id < 0x1102 + NCH : a chunk
        W(*imm(0x1102 + NCH, 0x84)); BR(0xF4, "GM_H1")        # = : the first HOOK
        W(*imm(0x2A00, 0x14)); BSR("HOOKP"); BSR("AMPON"); W(0xF80F)       # > : the second HOOK (and the amp-on message again: the stock 0x1080 handling may switch the amplifier off after GO) ends the chain
        LBL("GM_H1")
        W(*imm(0x2A00, 0x14)); BSR("HOOKP"); BR(0xE0, "GM_N")
        LBL("GM_C")
        W(*imm((-0x1102) & 0xFFFF, 0x34))                    # AL = id - 0x1102 = c
        if NCHX:
            W(*imm(NCH_T, 0x84)); BR(0xFC, "GM_T")           # c < 7: a chunk of the data table
            if _GLXV == 'direct':
                for _k in range(NCHX):                       # c >= 7: a chunk from cave immediates (probe395), direct dispatch (AL = c is intact until the call)
                    W(*imm(NCH_T + _k, 0x84)); BR(0xF0, "GX_%d" % (_k + 1))
                    BSR("GLX%d" % _k); BR(0xE0, "GM_N")
                    LBL("GX_%d" % (_k + 1))
                BR(0xE0, "GM_N")
            else:
                BSR("GLRUNX"); BR(0xE0, "GM_N")              # c >= 7: the dispatch block
            LBL("GM_T")
        BSR("GLRUN")
        LBL("GM_N")
        W(0x0317); W(*imm(1, 0x34)); W(*imm(50, 0x10)); BSR(L['RSEND'])
        W(0xF80F)
    if VARIANT in ('s', 't', 'u', 'v', 'y', 'z', 'G') or EAMP:
        BLK(); LBL("AMPON")                                   # MessageSend(task 0x72c, 0x7023, NULL) through the stock wrapper fn_395dd (payload at the caller's slot 0)
        W(0xFC0B)
        W(0x0014); W(0x0027)
        W(*imm(0x7023, 0x10)); W(*imm(0x72C, 0x14)); BSR(0x395DD)
        W(0xFC0F)
    if VARIANT == 'D':
        # ---- DIAGNOSTIC D: which RAM word holds the speaker's volume? OCT3(AL = value, AH = delay) schedules 3 octal digits (low first, battery (d+1)*10 %), returns AL = the next delay
        BLK(); LBL("OCT3")
        W(0xF80B); W(0x0427); W(0x0323)
        for _k in range(3):
            W(0x0417); W(0x07C4); W(*imm(0x900, 0x34)); BSR("SDG")
            W(0x0417); W(0x0009); W(0x03A4); W(0x0427)
        W(0x0317)
        W(0xF80F)
        BLK(); LBL("VOLD")                                    # AL = delay of the first digit: A = high byte of (11,@0x72e), B = (8,@0x6fd), C = @0x536
        W(0xF80B); W(0x0527)
        if NOREAD:
            W(*imm(0o123, 0x14)); W(0x0513); BSR("OCT3"); W(0x0527)
            W(*imm(0o456, 0x14)); W(0x0513); BSR("OCT3"); W(0x0527)
            W(*imm(0o701, 0x14)); W(0x0513); BSR("OCT3"); W(0x0527)
        else:
            W(0x0700, 0x2E19); W(0x0B12); W(0x0009); W(0x08A4); W(0xE015); W(0x0513); BSR("OCT3"); W(0x0527)
            W(0x0700, 0xFD19); W(0x0816); W(0x0513); BSR("OCT3"); W(0x0527)
            W(0x0500, 0x3615); W(0x0513); BSR("OCT3"); W(0x0527)
        W(0xF80F)
        BLK(); LBL("DIAGA")
        W(0xF80B)
        BSR(L['CANCELANY'])
        W(*imm(19000, 0x14)); BSR("VOLD")
        W(0xF80F)
        BLK(); LBL("DIAGB")
        W(0xF80B)
        W(0xF80F)
    if VARIANT == 's':
        # ---- J33 (agent report, 2026-10-17): the stock audio library switches the amplifier ON before a cold prompt (0x7024 -> 0x7023 on task 0x72c -> 0x6f00 to the app 0x512 -> fn_0f1df: PIO5 low, PIO12 mode 5)
        #      and OFF 100 ms after the prompt ends (0x7020 -> 0x6f01 -> fn_0f206: PIO5 high). The cave never asks again. 5s: read the two pins, send 0x7023 to 0x72c, read again.
        #      digit d = 2*PIO5 + PIO12 (fn_01623 = stock PioGet of one pin): 2 = PIO5 high, PIO12 low (off), 1 = PIO5 low, PIO12 high (on)
        BLK(); LBL("PIOD")                                    # AL = delay (ms): schedules ONE digit prompt d after the delay
        W(0xF80B); W(0x0327)
        W(*imm(12, 0x14)); BSR(0x1623); W(0x0427)
        W(*imm(5, 0x14)); BSR(0x1623); W(0x0084); BR(0xF4, "PD_0")
        W(0x0417); W(0x0234); W(0x0427)
        LBL("PD_0")
        W(0x0417); W(*imm(0x900, 0x34)); W(0x0313); BSR(L['RSEND'])
        W(0xF80F)
        BLK(); LBL("DIAGA")                                   # GO + 3 s: read, stop the loop poll (the running chunk plays on), amp-on message; the digit is spoken 19 s later (the chunk has ended)
        W(0xF80B)
        W(*imm(19000, 0x14)); BSR("PIOD")
        BSR(L['CANCELANY'])
        BSR("AMPON")
        W(0xF80F)
        BLK(); LBL("DIAGB")                                   # GO + 8 s: read again, spoken at GO + 26.5 s
        W(0xF80B)
        W(*imm(18500, 0x14)); BSR("PIOD")
        W(0xF80F)
    if VARIANT in ('f', 'k', 'w', 'p', 'q', 'r', 's', 'D'):
        BLK(); LBL("SPEAKD")                                  # AL = 0x900 + 16*j + digit -> speak battery (digit+1)*10 percent
        W(0xF80B)
        W(0x00C4 | (0x0F << 8)); W(*imm(0x27, 0x34)); BSR(L['SPEAKR'])      # and AL,#0x0F ; add AL,#0x27 ; speak through the old SPEAKR: it first releases OUR audio-busy hold (GATE set it), without which the stock prompt engine parks the prompt
        W(0xF80F)
    return P.items


# ------------------------------------------------------------------------------------------------ placement into the twelve functions
def ext_bands(G):
    code, caveguard = G['code'], G['caveguard']
    bands = []
    for f in sorted(G['_NEWFN']):
        if f in G.get('INERT_ONLY', ()): continue                      # confirmation image: stubs and fill only, no code placed there
        end, sa, sw = G['_NEWFN'][f]
        stubs = {sa + k for k in range(len(sw))}
        a = f
        while a < end:
            if caveguard.region_writable(a) and a not in stubs:
                b = a
                while b < end and caveguard.region_writable(b) and b not in stubs: b += 1
                s = a
                while s < b and (code[s - 1] & 0xFF) == 0 and (s - 1) not in stubs: s += 1
                if b - s >= 4: bands.append((s, b))   # bands under 4 words cost more in connectors than they hold
                a = b
            else:
                a += 1
    # the leftover words of the const window (everything the old cave did not use), as bands of their own cluster
    out = G['out']
    for (a, b) in G['_BANDS']:
        if not (G['SCAN_LO'] <= a < G['SCAN_HI']): continue
        x = a
        while x < b:
            if x in out: x += 1; continue
            y = x
            while y < b and y not in out: y += 1
            if y - x >= 4 and G['blind'](x) and G['in_run'](x): bands.append((x, y))
            x = y
    return bands


def ext_bands_ay(G):
    """probe298: the writable runs of the AY dead functions (after their stub words), same band rule as ext_bands. Used ONLY for the EVGUARD wrapper block, so the probe296 layout stays untouched."""
    code, caveguard = G['code'], G['caveguard']
    bands = []
    for f in sorted(G['_AYFN']):
        end, sa, sw = G['_AYFN'][f]
        stubs = {sa + k for k in range(len(sw))}
        a = f
        while a < end:
            if caveguard.region_writable(a) and a not in stubs and a >= sa:
                b = a
                while b < end and caveguard.region_writable(b) and b not in stubs: b += 1
                s = a
                while s < b and (code[s - 1] & 0xFF) == 0 and (s - 1) not in stubs: s += 1
                if b - s >= 4: bands.append((s, b))
                a = b
            else:
                a += 1
    return bands


def build_evg(G, evtx_addr):
    """probe298 EVGUARD wrapper (AU section 5 with the call-plugin test of BC section 2): TRIG's `bsr EVENTS` (retargeted to EVTX in probe296) goes here instead. AL = the event.
    enterl -4 ; st AL,@(0,Y) ; [clear @0x6d1 bit 15 iff busy == 0 and @0x72f == 0 and @0x72e == 0 and StreamKalimbaSink(3) == 0] ; ld AL,@(0,Y) ; bsr EVTX ; leavel -4.
    Nothing but slot 0 of the own frame is written; X, AH and the flags are dead at both ends (TRIG replays the stock call with AL reloaded from its own slot 0)."""
    P = Prog()
    ca = G['ca']
    W, BSR, BR, LBL, BLK = P.W, P.BSR, P.BR, P.LBL, P.BLK
    imm = ca.imm_words
    BLK(); LBL("EVG")
    W(0xFC0B); W(0x0027)                                                 # enterl -4 ; st AL,@(0,Y)  the event
    if G.get('VMREAD'):
        W(0x0017); BSR(G['_VRGO']); W(0x0084); BR(0xF4, "VG_P")             # probe382: a read-out trigger id is consumed here, BEFORE EVGCHK can clear @0x6d1 bit 15 (AL = 1); any other id goes on
        W(0xFC0F)
        LBL("VG_P")
    BSR("EVGCHK")                                                       # the reconcile (own block: the AY bands are only 12-14 words each)
    if G.get('G5DIAG'):
        # probe300 (BN): arm the READ-ONLY G5 report on the yield path: a stream start (0x4758) while the mode is ON (EVTX turns it OFF below). One timer message DG_ID, DG_MS later. Nothing else is touched.
        Lm = G['label_addr']
        W(0x0017); W(*imm(0x4758, 0x84)); BR(0xF0, "EG_N")              # ld AL,@(0,Y) ; event == 0x4758 ?
        BSR(Lm['PEEKMODE']); W(0x0084); BR(0xF4, "EG_N")                 # the mode is OFF: nothing to report
        if G.get('G5COLD'):
            W(*imm(COLD_ID, 0x14)); BSR(G['_PEEKF']); W(0x0084); BR(0xF4, "EG_N")      # the cold-owned flag is gone (the DSP is a stock one, the noise does not yield): not the yield path. (EVTX asks the same.)
        if not G.get('G5NOSEND'): W(*imm(DG_ID, 0x14)); W(*imm(DG_MS, 0x10)); BSR(Lm['RSEND'])      # probe302: G5NOSEND drops the +36 s digit timer to make room for the G5ZAP clear
        if G.get('G5TWO'):
            W(*imm(DG_ID + 1, 0x14)); W(*imm(DG_MS + 6000, 0x10)); BSR(Lm['RSEND'])
        LBL("EG_N")
    if G.get('G5ZAP'):
        W(0x0017); BSR("EVGY")                                           # probe302 (BR section 5): the yield-time flag clear lives in its own block EVGY (AL = the event)
    W(0x0017); BSR(evtx_addr)                                            # the event back in AL, then the unchanged EVTX
    W(0xFC0F)
    if G.get('G5ZAP'):
        # EVGY: a stream start (0x4758) while the noise mode is ON (EVTX turns it OFF right after): clear the stale DAC flag @0x6d1 bit 15 NOW, before the stock prompt tears our DSP down at +16 s
        # (BR: the queued plugin load's fn_1f04c would refuse and PanicNull). Only when no stock A2DP plugin instance exists (@0x72f == 0).
        Lm = G['label_addr']
        BLK(); LBL("EVGY")
        W(0xFE0B)                                                        # enterl -2
        W(*imm(0x4758, 0x84)); BR(0xF0, "EG_N")                          # event == 0x4758 ?
        BSR(Lm['PEEKMODE']); W(0x0084); BR(0xF4, "EG_N")                 # the mode is OFF: nothing to do
        W(*imm(0x72F, 0x15)); W(0x0084); BR(0xF0, "EG_N")                # a stock A2DP instance exists: leave the bit alone
        BSR("EVGZAP")
        LBL("EG_N")
        W(0xFE0F)                                                        # leavel -2
    BLK(); LBL("EVGCHK")
    W(0xFE0B)                                                            # enterl -2
    BSR(G['GETBUSY']); W(0x0084); BR(0xF0, "EV_G")                       # busy != 0 -> skip
    W(*imm(0x72F, 0x15)); W(0x0084); BR(0xF0, "EV_G")                    # @0x72f != 0 (A2DP instance) -> skip
    W(*imm(0x72E, 0x15)); W(0x0084); BR(0xF0, "EV_G")                    # @0x72e != 0 (call/CVC instance) -> skip
    BSR("EVGCLR")
    LBL("EV_G")
    W(0xFE0F)                                                            # leavel -2
    if G.get('EVGCHAIN'):
        # probe299 (BH): the stack-true "the DAC link chain is gone" test. StreamKalimbaSink(5) is never 0 (BG 12), so the old port-3 test never fired; the
        # DAC link made by fn_1f04c is a chain whose root node has the SOURCE of Kalimba port 5 (BG 3.3), and KalimbaLoad/KalimbaPowerOff dispose it (BG 0.1 item 3).
        # TransformFromSource(StreamSourceFromSink(StreamKalimbaSink(5))) != 0 iff that chain exists. KSINK == 0 (pool dry) is no verdict: skip.
        BLK(); LBL("EVGCLR")
        W(0xFE0B)                                                        # enterl -2
        W(*imm(5, 0x14)); BSR(G['KSINK']); W(0x0084); BR(0xF4, "EV_C")   # no port object (pool dry) -> no verdict, skip
        BSR(ca.STUB['StreamSourceFromSink']); BSR(ca.STUB['TransformFromSource'])
        W(0x0084); BR(0xF0, "EV_C")                                      # the chain exists (the flag is TRUE) -> skip
        BSR("EVGZAP")
        LBL("EV_C")
        W(0xFE0F)                                                        # leavel -2
        BLK(); LBL("EVGZAP")
        W(0xFE0B)                                                        # enterl -2
        W(*imm(0x6D1, 0x15)); W(*imm(0x7FFF, 0xC4)); W(*imm(0x6D1, 0x25))    # the F2 clear, same words
        W(0xFE0F)                                                        # leavel -2
        return P.items
    BLK(); LBL("EVGCLR")
    W(0xFE0B)                                                            # enterl -2
    W(*imm(3, 0x14)); BSR(G['KSINK']); W(0x0084); BR(0xF0, "EV_C")       # a Kalimba sink on port 3 -> skip
    W(*imm(0x6D1, 0x15)); W(*imm(0x7FFF, 0xC4)); W(*imm(0x6D1, 0x25))    # the F2 clear, same words
    LBL("EV_C")
    W(0xFE0F)                                                            # leavel -2
    return P.items


def build_dg(G, exth_addr):
    """probe300 (BN): the READ-ONLY G5 report digit. DGW is HANDLER's bsr AUTOSTART target (frameless): the id DG_ID (armed by EVG on the yield path, DG_MS later) is handled here, every other id jumps to EXTH
    unchanged (EXTH then returns to HANDLER's caller itself). The digit D = blk[24] + 5*ready is spoken as battery (D+1)*10 percent = id 0x27+D, only when the mode is OFF (CLAUDE.md rule 4).
      blk[24]  = the stock plugin's DSP state (0 none, 1 loading, 2 loaded, 3 connected, 4 refused), read from the audio-manager block @0x72b
      ready    = @0x73e bit 6 = the BDSP shadow of the last source-mute write: set by 'ready' (index 46 := 0, the VM unmute), cleared by 'go sent'
    No stock call, no write."""
    P = Prog()
    ca = G['ca']
    W, BSR, BR, LBL, BLK = P.W, P.BSR, P.BR, P.LBL, P.BLK
    imm = ca.imm_words
    Lm = G['label_addr']
    BLK(); LBL("DGW")                                                    # frameless: AL = the id
    W(*imm(DG_ID, 0x84)); BR(0xF4, "DG_1")
    if G.get('G5TWO'):
        W(*imm(DG_ID + 1, 0x84)); BR(0xF4, "DG_1")
    BR(0xE0, exth_addr)                                                  # every other id: EXTH, unchanged
    LBL("DG_1")
    if G.get('G5TWO'):
        W(0xFC0B); W(0x0027)                                             # enterl -4 ; st AL,@(0,Y)
    else:
        W(0xFE0B)                                                        # enterl -2
    BSR(Lm['PEEKMODE']); W(0x0084); BR(0xF0, "DG_X")                     # the mode is ON (the noise was started again): silent
    if G.get('G5TWO'):
        W(0x0017); W(*imm(DG_ID + 1, 0x84)); BR(0xF4, "DG_2")
    W(*imm(0x73E, 0x15)); W(*imm(0x40, 0xC4)); BR(0xF4, "DG_Z")          # ld AL,@0x73e ; and AL,#0x40 ; beq : 'ready' has not run (AL = 0)
    W(*imm(5, 0x14))                                                     # ld AL,#5
    LBL("DG_Z")
    W(*imm(0x72B, 0x19)); W(0x1836)                                      # ld X,@0x72b ; add AL,@(24,X)  = + blk[24]
    if G.get('G5TWO'):
        BR(0xE0, "DG_S")
        LBL("DG_2")
        W(*imm(0x73E, 0x15)); W(*imm(0x10, 0xC4)); BR(0xF4, "DG_Y")
        W(*imm(1, 0x14))
        LBL("DG_Y")
        W(*imm(0x6D1, 0x99)); BR(0xE8, "DG_S")
        W(0x0234)
    LBL("DG_S")
    W(*imm(0x27, 0x34)); BSR(Lm['SPEAKR'])                               # add AL,#0x27 ; speak (releases OUR hold first, a no-op when the stock owns the audio-busy word)
    LBL("DG_X")
    W(0xFC0F if G.get('G5TWO') else 0xFE0F)                              # leavel : back to HANDLER (DG_ID needs no EXTH)
    return P.items


VR_IDS = (0x4070, 0x4071, 0x4072, 0x4073)                      # probe382 read-out triggers (stock fn_01749 switch default arm; NEVER 0x4021 / 0x4022)
VR_IDS_383 = (0x4070, 0x4071, 0x4072, 0x4073, 0x4074, 0x4075, 0x4076)   # probe383 (VMUNGATE): + 0x4074 blk[24], 0x4075 @0x73e, 0x4076 @0x72f (same safe default-arm family; NEVER 0x4021 / 0x4022)
VR_KICK = 0x4077                                               # probe382: sends the ENSURE request (id 0x2C), speaks nothing


def build_vr(G):
    """probe382 VMREAD (READ-ONLY diagnostic, docs/deep/bug-2026-10-29-connected-device-no-noise.md): spoken read-out of VM state for the 'device connected, no noise' bug.
    VRGO (called by EVG with AL = the event, BEFORE EVGCHK can clear @0x6d1 bit 15): AL = 1 if the event is a trigger (consumed, the stock never sees it), else 0.
      0x4070 FLAGS (1 mode ON, 2 StreamKalimbaSink(3) != 0, 8 a heartbeat poll is pending) | 0x4071 the audio-busy word | 0x4072 @0x6d1 | 0x4073 @0x59e (sinkState)
      0x4077 KICK: MessageSendLater(cave, 0x2C = ENSURE, 100 ms), nothing spoken.
    A value is spoken as 6 octal digits (low first) + the check digit (sum mod 8), 3.5 s apart from +9 s, through the census digit messages 0x900 + d (seven MessageSendLater, as probe363).
    Nothing is spoken (silent no-op) when the mode is ON and a DSP sink exists on port 3 (the noise may be running; the lean generator has no transform, CLAUDE.md rule 4).
    VRGO..VRSDG are MAIN-layout blocks (the AY pool is too fragmented for ~150 words); VRW (AY pool, with EVG) is HANDLER's bsr AUTOSTART target (frameless, as DGW): ids 0x900..0x94F are speak digits (battery (d+1)*10 percent through SPEAKR), every other id goes to EXTH unchanged."""
    P = Prog()
    ca = G['ca']
    W, BSR, BR, LBL, BLK = P.W, P.BSR, P.BR, P.LBL, P.BLK
    imm = ca.imm_words
    Lm = G['label_addr']
    KS = G['KSINK']
    BLK(); LBL("VRW")                                                     # FRAMELESS (EXTH reads HANDLER's frame at fixed offsets, as DGW): AL = the id; HANDLER's bsr AUTOSTART target
    W(*imm(0x900, 0x84)); BR(0xFC, "VW_N")
    W(*imm(0x950, 0x84)); BR(0xF8, "VW_N")
    W(0xFE0B)                                                             # enterl -2
    W(0x0FC4); W(*imm(0x27, 0x34)); BSR(Lm['SPEAKR'])                     # (id & 0x0F) + 0x27 = battery (digit+1)*10 percent, OUR hold released first
    W(0xFE0F)                                                             # leavel -2: back to HANDLER
    LBL("VW_N")
    BR(0xE0, "EXTH")                                                      # every other id: EXTH, unchanged (it returns to HANDLER's caller itself)
    BLK(); LBL("VRGO")
    W(0xF80B); W(0x0327)                                                  # enterl -8 ; st AL,@(3,Y) the event
    for _k, _id in enumerate(VR_IDS_383 if G.get('VMUNGATE') else VR_IDS):
        W(0x0317); W(*imm(_id, 0x84)); BR(0xF0, "VR_%d" % (_k + 1))
        if _k == 0: BSR("VRFLG")
        elif _k == 1: BSR(G['GETBUSY'])
        elif _k == 4: W(*imm(0x72B, 0x19)); W(0x1816)                      # probe383: ld X,@0x72b ; ld AL,@(24,X) = blk[24], the stock plugin DSP state (as DGW, read only)
        else: W(*imm((0x6D1, 0x59E, 0, 0x73E, 0x72F)[_k - 2], 0x15))
        BSR("VRSAY")
        W(0x0114); W(0xF80F)                                              # AL = 1: consumed
        LBL("VR_%d" % (_k + 1))
    W(0x0317); W(*imm(VR_KICK, 0x84)); BR(0xF0, "VR_X")
    W(*imm(0x2C, 0x14)); W(*imm(100, 0x10)); BSR(Lm['RSEND'])
    W(0x0114); W(0xF80F)
    LBL("VR_X")
    W(0x0014); W(0xF80F)                                                  # not a trigger: AL = 0
    BLK(); LBL("VRFLG")                                                   # AL = FLAGS
    W(0xF80B)
    W(0x0014); W(0x0527)                                                  # slot 5 = 0
    BSR(Lm['PEEKMODE']); W(0x0084); BR(0xF4, "VF_1")
    W(0x0517); W(*imm(1, 0x34)); W(0x0527)
    LBL("VF_1")
    W(*imm(3, 0x14)); BSR(KS); W(0x0084); BR(0xF4, "VF_3")
    W(0x0517); W(*imm(2, 0x34)); W(0x0527)
    LBL("VF_3")
    if G.get('VMUNGATE'):
        W(*imm(0x72E, 0x15)); W(0x0084); BR(0xF4, "VF_5")                  # probe383: bit 4 = @0x72e != 0 (EVGCHK's null test)
        W(0x0517); W(*imm(4, 0x34)); W(0x0527)
        LBL("VF_5")
    BSR(Lm['CANCELANY']); W(0x0084); BR(0xF4, "VF_4")                     # AL = level + 1 of the pending heartbeat poll, else 0 (the cancel is undone at once)
    W(*imm(G['LEVEL_BASE'] - 1, 0x34)); W(*imm(G.get('GEN_HB_MS', 4000), 0x10)); BSR(Lm['RSEND'])
    W(0x0517); W(*imm(8, 0x34)); W(0x0527)
    LBL("VF_4")
    W(0x0517)
    W(0xF80F)
    BLK(); LBL("VRSAY")                                                   # AL = the value: speak it unless the noise may be running
    W(0xF80B); W(0x0427)                                                  # slot 4 = the value
    if not G.get('VMUNGATE'):
        BSR(Lm['PEEKMODE']); W(0x0084); BR(0xF4, "VR_GO")                     # the mode is OFF: speakable
        W(*imm(3, 0x14)); BSR(KS); W(0x0084); BR(0xF0, "VR_NO")               # ON with a DSP sink: the noise may be running: silent no-op
    LBL("VR_GO")
    W(0x0417); W(*imm(9000, 0x10)); BSR("VRWORD")
    LBL("VR_NO")
    W(0xF80F)
    BLK(); LBL("VRWORD")                                                  # AL = a 16-bit value, AH = the first delay (ms): as PCWORD (probe362)
    W(0xF80B); W(0x0427); W(0x0323)
    W(*imm(6, 0x14)); W(0x0527)
    W(0x0014); W(0x0227)
    LBL("VW_L")
    W(0x0417); W(0x07C4); W(0x0237); W(0x0227)
    W(0x0417); W(0x07C4); W(*imm(0x900, 0x34)); BSR("VRSDG")
    W(0x0417); W(0x0009); W(0x03A4); W(0x0427)
    W(0x0517); W(*imm(0xFFFF, 0x34)); W(0x0527); W(0x0084); BR(0xF0, "VW_L")
    W(0x0217); W(0x07C4); W(*imm(0x900, 0x34)); BSR("VRSDG")
    W(0x0317)
    W(0xF80F)
    BLK(); LBL("VRSDG")
    W(0xF80B); W(0x0327)
    W(0x0B13); W(0x0317); BSR(Lm['RSEND'])
    W(0x0B17); W(*imm(3500, 0x34)); W(0x0B27)
    W(0xF80F)
    return P.items


def leftover_bands(G, bands, used):
    """The words of the twelve functions' EXT bands that the main placement did not use, as runs of >= 4 words (same start rule as ext_bands: a run never starts right after a prefix-like word)."""
    code = G['code']
    out_ = []
    for (a, b) in bands:
        x = a
        while x < b:
            if x in used: x += 1; continue
            y = x
            while y < b and y not in used: y += 1
            s = x
            while s < y and ((used_val(G, used, s - 1)) & 0xFF) == 0: s += 1
            if y - s >= 4: out_.append((s, y))
            x = y
    return out_


def used_val(G, used, a):
    return used[a] if a in used else G['code'][a]


def _materialize(items, placed):
    addrs, lab, extra, br_size, bs_size, br_place, bs_place, clusters = placed
    new = {}
    for i, it in enumerate(items):
        a = addrs[i]
        if it[0] == "w":
            for k, v in enumerate(it[1]): new[a + k] = v
        elif it[0] == "bsr":
            t = lab[it[1]] if isinstance(it[1], str) else it[1]
            for k, v in enumerate(enc_bsr(a, t, bs_size[i])): new[a + k] = v
            for k in range(bs_size[i], bs_place[i]): new[a + k] = 0x01E0         # padding: bra +1 (a harmless no-op), keeps the placed size
        elif it[0] == "br":
            for k, v in enumerate(enc_br(a, lab[it[2]] if isinstance(it[2], str) else it[2], it[1], br_size[i])): new[a + k] = v
            for k in range(br_size[i], br_place[i]): new[a + k] = 0x01E0         # padding: bra +1
    for ca_, (nb, csz) in extra.items():
        for k, v in enumerate(enc_br(ca_, nb, 0xE0, csz)): new[ca_ + k] = v
    ei = {}
    for i, it in enumerate(items):
        if it[0] == "bsr": ei[addrs[i]] = (lab[it[1]] if isinstance(it[1], str) else it[1], 'ext bsr')
        elif it[0] == "br": ei[addrs[i]] = (lab[it[2]] if isinstance(it[2], str) else it[2], 'ext br')
    for ca_, (nb, csz) in extra.items(): ei[ca_] = (nb, 'ext connector')
    return new, ei


def enc_bsr3(a, tgt):
    v = tgt - (a + 2)
    for aa in range(-128, 128):
        if aa == 0: continue
        for bb in range(-128, 128):
            if bb == 0: continue
            cc = v - aa * 65536 - bb * 256
            if -128 <= cc <= 127:
                return [(aa & 0xFF) << 8, (bb & 0xFF) << 8, ((cc & 0xFF) << 8) | 0x9C]
    raise AssertionError((hex(a), hex(tgt)))


def enc_bsr(a, tgt, size):
    if size == 1:
        return [(((tgt - a) & 0xFF) << 8) | 0x9C]
    if size == 3:
        return enc_bsr3(a, tgt)
    v = tgt - (a + 1)
    for aa in range(max(-128, (v >> 8) - 2), min(128, (v >> 8) + 3)):
        if aa == 0: continue
        b = v - aa * 256
        if -128 <= b <= 127:
            return [(aa & 0xFF) << 8, ((b & 0xFF) << 8) | 0x9C]
    raise AssertionError(('bsr2', hex(a), hex(tgt)))


def enc_br(a, tgt, op, size):
    if size == 1:
        v = tgt - a
        assert -128 <= v <= 127
        return [((v & 0xFF) << 8) | op]
    v = tgt - (a + 1)
    for aa in range(max(-128, (v >> 8) - 2), min(128, (v >> 8) + 3)):
        if aa == 0: continue
        bb = v - aa * 256
        if -128 <= bb <= 127:
            return [(aa & 0xFF) << 8, ((bb & 0xFF) << 8) | op]
    raise AssertionError(('br2', hex(a), hex(tgt)))


def bsr3_ok(v):
    """closed form of the 3-word encoding v = aa*65536 + bb*256 + cc with aa, bb in [-128,127] and NONZERO, cc in [-128,127]"""
    cc = ((v + 128) % 256) - 128
    rem = (v - cc) // 256
    bb = ((rem + 128) % 256) - 128
    aa = (rem - bb) // 256
    return bb != 0 and aa != 0 and -128 <= aa <= 127


def bsr2_ok(v):
    return br2_ok(v)


def br2_ok(v):
    for aa in range(max(-128, (v >> 8) - 2), min(128, (v >> 8) + 3)):
        if aa == 0: continue
        if -128 <= v - aa * 256 <= 127: return True
    return False


TERMS = None
DBG_S = 44


def place_once(G, items, bands, seed, required=()):
    """Place the EXT program: each block whole inside ONE cluster of bands (branches stay in 2-word reach), bsr always 3 words (attested)."""
    ca = G['ca']
    term_ops = ca.TERMINATOR_OPS
    def needs_follow(it):
        if it[0] == "bsr": return True
        if it[0] == "br": return it[1] != 0xE0
        if it[0] == "w": return (it[1][-1] & 0xFF) not in term_ops
        return False
    SPAN = int(__import__("os").environ.get("SPAN", "30000"))
    clusters = []
    for b in sorted(bands):
        if clusters and b[1] - clusters[-1][0][0] <= SPAN: clusters[-1].append(b)
        else: clusters.append([b])
    # blocks
    starts = [i for i, it in enumerate(items) if it[0] == "blk"]
    blocks = [(s, starts[n + 1] if n + 1 < len(starts) else len(items)) for n, s in enumerate(starts)]
    def bsize(s, e):
        return sum(len(it[1]) if it[0] == "w" else 3 if it[0] == "bsr" else 2 if it[0] == "br" else 0 for it in items[s:e])
    import random
    rnd = random.Random(seed)
    import os
    if os.environ.get('BLOCKSIZES'): print('BLOCKSIZES', sorted(((bsize(*b), items[b[0] + 1][1]) for b in blocks), reverse=True), [sum(y - x for x, y in c) for c in clusters])
    cap = [sum(y - x for x, y in c) * float(__import__("os").environ.get("CAPF", "0.7")) for c in clusters]
    assign = {}
    for (s, e) in sorted(blocks, key=lambda b: -bsize(*b) * (1.0 if seed == 0 else rnd.uniform(0.8, 1.2))):
        best = max(range(len(cap)), key=(lambda c: cap[c] * rnd.uniform(0.4, 1.6)) if (seed > 0 and os.environ.get('RANDASSIGN')) else (lambda c: cap[c]))     # RANDASSIGN (probe288): diversify the cluster choice across seeds
        assign[s] = best; cap[best] -= bsize(s, e)
    _force = G.get('FORCE')                                                # probe300: {block label: start address of a band of the wanted cluster}; absent for every older image
    if _force:
        for (s, e) in blocks:
            nm = items[s + 1][1]
            if nm in _force:
                assign[s] = [ci for ci, cb_ in enumerate(clusters) if any(b_[0] == _force[nm] for b_ in cb_)][0]
    br_size = {i: 1 for i, it in enumerate(items) if it[0] == "br"}       # the size each branch NEEDS (encoding)
    bs_size = {i: 1 for i, it in enumerate(items) if it[0] == "bsr"}
    br_place = dict(br_size)                                               # the size it is PLACED with: only ever grows (a short branch in a longer slot is padded with `bra +1`), so the layout converges
    bs_place = dict(bs_size)
    bump = {}
    for iteration in range(60):
        addrs = [None] * len(items)
        extra = {}                     # connector address -> (target, size)
        ptr = {}
        failed = False
        for (s, e) in blocks:
            c = assign[s] + bump.get(s, 0)
            if c >= len(clusters): raise RuntimeError('ladder: no cluster has room for the block at item %d (%s, %d words)' % (s, items[s + 1][1], bsize(s, e)))
            cb = clusters[c]
            if c not in ptr: ptr[c] = [0, cb[0][0]]          # [band index, addr]
            bi, addr = ptr[c]
            # never start a block in the last 6 words of a band
            if cb[bi][1] - addr < 6 and bi + 1 < len(cb): bi += 1; addr = cb[bi][0]
            i = s + 1
            while i < e:
                it = items[i]
                if it[0] == "label":
                    addrs[i] = None; i += 1; continue
                sz = len(it[1]) if it[0] == "w" else bs_place[i] if it[0] == "bsr" else br_place[i]
                bend = cb[bi][1]
                nxt = cb[bi + 1][0] if bi + 1 < len(cb) else None
                # an item that falls through always keeps 2 words after it in its band, so a connector to the next band always fits
                reserve = 2 if needs_follow(it) and nxt is not None else 0
                if addr + sz + reserve <= bend or (nxt is None and addr + sz <= bend and not needs_follow(it)):
                    addrs[i] = addr; addr += sz; i += 1
                    continue
                if nxt is None:
                    bump[s] = bump.get(s, 0) + 1; failed = True; break
                # does not fit: connector right here (the previous item falls through) to the first LATER band that can hold this item
                tj = None
                for jj in range(bi + 1, len(cb)):
                    last = (jj + 1 >= len(cb))
                    need_w = sz + (2 if needs_follow(it) and not last else 0)
                    if cb[jj][1] - cb[jj][0] >= need_w and not (last and needs_follow(it)):
                        tj = jj; break
                if tj is None:
                    bump[s] = bump.get(s, 0) + 1; failed = True; break
                prevk = None
                for pj in range(i - 1, s, -1):
                    if items[pj][0] != "label": prevk = pj; break
                if prevk is not None and needs_follow(items[prevk]):
                    tgt_ = cb[tj][0]
                    csz = 1 if -128 <= tgt_ - addr <= 127 else 2
                    assert addr + csz <= bend, ('ladder: reserve failed', hex(addr), csz, hex(bend))
                    extra[addr] = (tgt_, csz)
                bi = tj; addr = cb[bi][0]
            if failed: break
            ptr[c] = [bi, addr]
        if failed: continue
        # labels
        lab = {}
        for i, it in enumerate(items):
            if it[0] != "label": continue
            j = i + 1
            while j < len(items) and (items[j][0] in ("label", "blk")): j += 1
            lab[it[1]] = addrs[j]
        # the two retargeted OLD 3-word bsr operands must be encodable at these distances
        for (ra, rname) in required:
            if not bsr3_ok(lab[rname] - (ra + 2)): raise RuntimeError('ladder: the old bsr at %#x cannot reach %s at %#x' % (ra, rname, lab[rname]))
        # branch sizes: each item NEEDS a size (encoding) but is PLACED with a size that only ever grows; a short form in a longer slot is padded with `bra +1`
        ok = True
        for i, it in enumerate(items):
            if it[0] == "bsr":
                t = lab[it[1]] if isinstance(it[1], str) else it[1]
                v = t - addrs[i]
                want = 1 if -126 <= v <= 126 else 2 if bsr2_ok(v - 1) else 3
                if want == 3 and not bsr3_ok(v - 2): raise RuntimeError('ladder: a 3-word bsr cannot encode distance %d' % v)
                bs_size[i] = want
                if want > bs_place[i]: bs_place[i] = want; ok = False
            elif it[0] == "br":
                _bt = lab[it[2]] if isinstance(it[2], str) else it[2]
                v = _bt - addrs[i]
                want = 1 if -128 <= v <= 127 else (2 if br2_ok(_bt - (addrs[i] + 1)) else 3)
                if want == 3: raise RuntimeError('ladder: a branch needs 3 words (blocks too far apart)')
                br_size[i] = want
                if want > br_place[i]: br_place[i] = want; ok = False
        if ok:
            # every falling-through item must be followed by its successor or by a connector
            for (s_, e_) in blocks:
                prev = None
                for i in range(s_ + 1, e_):
                    it = items[i]
                    if it[0] == "label": continue
                    if prev is not None and needs_follow(items[prev]):
                        psz = len(items[prev][1]) if items[prev][0] == "w" else bs_place[prev] if items[prev][0] == "bsr" else br_place[prev]
                        end = addrs[prev] + psz
                        if addrs[i] != end:
                            assert end in extra and extra[end][0] == addrs[i], ('ladder: missing connector after item', prev, items[prev], hex(addrs[prev]), 'next at', hex(addrs[i]))
                    prev = i
            return addrs, lab, extra, br_size, bs_size, br_place, bs_place, clusters
    raise RuntimeError('ladder: layout did not converge')




def place_once_fg(G, items, bands, seed, required=()):
    """FILLGAPS variant of place_once (opt-in, env FILLGAPS=1; 2026-10-30 layout-engine work, docs/deep/layout-engine-2026-10-30.md): every cluster keeps a list of free runs [lo, hi) that blocks consume from the LEFT, blocks are placed largest first, an item that does not fit moves to a free run chosen by a seeded policy (best fit / first fit / random fit) and EARLIER runs stay usable by later blocks (place_once abandons the rest of a band when an item jumps away). A failed block is retried in the other clusters (cyclic bump). Everything after the placement loop is the unchanged place_once code."""
    ca = G['ca']
    term_ops = ca.TERMINATOR_OPS
    def needs_follow(it):
        if it[0] == "bsr": return True
        if it[0] == "br": return it[1] != 0xE0
        if it[0] == "w": return (it[1][-1] & 0xFF) not in term_ops
        return False
    SPAN = int(__import__("os").environ.get("SPAN", "30000"))
    clusters = []
    for b in sorted(bands):
        if clusters and b[1] - clusters[-1][0][0] <= SPAN: clusters[-1].append(b)
        else: clusters.append([b])
    # blocks
    starts = [i for i, it in enumerate(items) if it[0] == "blk"]
    blocks = [(s, starts[n + 1] if n + 1 < len(starts) else len(items)) for n, s in enumerate(starts)]
    def bsize(s, e):
        return sum(len(it[1]) if it[0] == "w" else 3 if it[0] == "bsr" else 2 if it[0] == "br" else 0 for it in items[s:e])
    import random
    rnd = random.Random(seed)
    import os
    if os.environ.get('BLOCKSIZES'): print('BLOCKSIZES', sorted(((bsize(*b), items[b[0] + 1][1]) for b in blocks), reverse=True), [sum(y - x for x, y in c) for c in clusters])
    cap = [sum(y - x for x, y in c) * float(__import__("os").environ.get("CAPF", "0.7")) for c in clusters]
    assign = {}
    for (s, e) in sorted(blocks, key=lambda b: -bsize(*b) * (1.0 if seed == 0 else rnd.uniform(0.8, 1.2))):
        best = max(range(len(cap)), key=(lambda c: cap[c] * rnd.uniform(0.4, 1.6)) if (seed > 0 and os.environ.get('RANDASSIGN')) else (lambda c: cap[c]))     # RANDASSIGN (probe288): diversify the cluster choice across seeds
        assign[s] = best; cap[best] -= bsize(s, e)
    _force = G.get('FORCE')                                                # probe300: {block label: start address of a band of the wanted cluster}; absent for every older image
    if _force:
        for (s, e) in blocks:
            nm = items[s + 1][1]
            if nm in _force:
                assign[s] = [ci for ci, cb_ in enumerate(clusters) if any(b_[0] == _force[nm] for b_ in cb_)][0]
    if os.environ.get('REQPIN'):
        # REQPIN: the blocks a retargeted OLD 3-word bsr operand calls (required) must lie more than 65 k words from the call site: assign them to such a cluster up front (the seed picks among the eligible ones)
        for (ra_, rname_) in required:
            for (s, e) in blocks:
                if items[s + 1][1] == rname_:
                    elig = [ci for ci, cb_ in enumerate(clusters) if all(abs(b_[0] - ra_) > 70000 and abs(b_[1] - ra_) > 70000 for b_ in cb_) and cap[ci] >= bsize(s, e) * 0.3]
                    if elig: assign[s] = max(elig, key=lambda ci: cap[ci] * rnd.uniform(0.4, 1.6))
    br_size = {i: 1 for i, it in enumerate(items) if it[0] == "br"}       # the size each branch NEEDS (encoding)
    bs_size = {i: 1 for i, it in enumerate(items) if it[0] == "bsr"}
    br_place = dict(br_size)                                               # the size it is PLACED with: only ever grows (a short branch in a longer slot is padded with `bra +1`), so the layout converges
    bs_place = dict(bs_size)
    bump = {}
    order_ = sorted(blocks, key=lambda b: -bsize(*b))
    for iteration in range(60):
        addrs = [None] * len(items)
        extra = {}                     # connector address -> (target, size)
        failed = False
        free = [[[x, y] for (x, y) in cb] for cb in clusters]       # per cluster: free runs [lo, hi), consumed from the left
        for (s, e) in order_:
            c = (assign[s] + bump.get(s, 0)) % len(clusters)
            if bump.get(s, 0) >= len(clusters): raise RuntimeError('ladder: no cluster has room for the block at item %d (%s, %d words)' % (s, items[s + 1][1], bsize(s, e)))
            runs = free[c]
            brnd = random.Random(seed * 1000003 + s)       # same decisions in every iteration of this seed
            pol = brnd.random()
            cur = None
            prevk = None
            i = s + 1
            while i < e:
                it = items[i]
                if it[0] == "label":
                    addrs[i] = None; i += 1; continue
                sz = len(it[1]) if it[0] == "w" else bs_place[i] if it[0] == "bsr" else br_place[i]
                reserve = 2 if needs_follow(it) else 0
                if cur is not None and runs[cur][0] + sz + reserve <= runs[cur][1]:
                    addrs[i] = runs[cur][0]; runs[cur][0] += sz; prevk = i; i += 1
                    continue
                need = sz + reserve
                if cur is None: need = max(need, 6)            # never start a block in the last 6 words of a run
                cand = [k for k, r in enumerate(runs) if k != cur and r[1] - r[0] >= need]
                if not cand:
                    bump[s] = bump.get(s, 0) + 1; failed = True; break
                if pol < 0.6:
                    # tightest fit: the run whose room is used best by the longest prefix of the remaining items (fewest wasted words, so fewer connectors)
                    def _pfx(room):
                        tot = 0; j = i
                        while j < e:
                            itj = items[j]
                            if itj[0] == "label": j += 1; continue
                            szj = len(itj[1]) if itj[0] == "w" else bs_place[j] if itj[0] == "bsr" else br_place[j]
                            if tot + szj + (2 if needs_follow(itj) else 0) > room: break
                            tot += szj; j += 1
                        return tot, j >= e
                    def _score(k):
                        room = runs[k][1] - runs[k][0]
                        tot, fin = _pfx(room)
                        return (room - tot - (3 if fin else 0), -tot, k)
                    k = min(cand, key=_score)
                elif pol < 0.8: k = cand[0]                                                  # first fit
                else: k = brnd.choice(cand)                                                  # random fit
                if cur is not None and prevk is not None and needs_follow(items[prevk]):
                    tgt_ = runs[k][0]
                    addr_ = runs[cur][0]
                    csz = 1 if -128 <= tgt_ - addr_ <= 127 else 2
                    assert addr_ + csz <= runs[cur][1], ('ladder: reserve failed', hex(addr_), csz, hex(runs[cur][1]))
                    extra[addr_] = (tgt_, csz); runs[cur][0] += csz
                cur = k
            if failed: break
        if failed: continue
        # labels
        lab = {}
        for i, it in enumerate(items):
            if it[0] != "label": continue
            j = i + 1
            while j < len(items) and (items[j][0] in ("label", "blk")): j += 1
            lab[it[1]] = addrs[j]
        # the two retargeted OLD 3-word bsr operands must be encodable at these distances
        for (ra, rname) in required:
            if not bsr3_ok(lab[rname] - (ra + 2)): raise RuntimeError('ladder: the old bsr at %#x cannot reach %s at %#x' % (ra, rname, lab[rname]))
        # branch sizes: each item NEEDS a size (encoding) but is PLACED with a size that only ever grows; a short form in a longer slot is padded with `bra +1`
        ok = True
        for i, it in enumerate(items):
            if it[0] == "bsr":
                t = lab[it[1]] if isinstance(it[1], str) else it[1]
                v = t - addrs[i]
                want = 1 if -126 <= v <= 126 else 2 if bsr2_ok(v - 1) else 3
                if want == 3 and not bsr3_ok(v - 2): raise RuntimeError('ladder: a 3-word bsr cannot encode distance %d' % v)
                bs_size[i] = want
                if want > bs_place[i]: bs_place[i] = want; ok = False
            elif it[0] == "br":
                _bt = lab[it[2]] if isinstance(it[2], str) else it[2]
                v = _bt - addrs[i]
                want = 1 if -128 <= v <= 127 else (2 if br2_ok(_bt - (addrs[i] + 1)) else 3)
                if want == 3: raise RuntimeError('ladder: a branch needs 3 words (blocks too far apart)')
                br_size[i] = want
                if want > br_place[i]: br_place[i] = want; ok = False
        if ok:
            # every falling-through item must be followed by its successor or by a connector
            for (s_, e_) in blocks:
                prev = None
                for i in range(s_ + 1, e_):
                    it = items[i]
                    if it[0] == "label": continue
                    if prev is not None and needs_follow(items[prev]):
                        psz = len(items[prev][1]) if items[prev][0] == "w" else bs_place[prev] if items[prev][0] == "bsr" else br_place[prev]
                        end = addrs[prev] + psz
                        if addrs[i] != end:
                            assert end in extra and extra[end][0] == addrs[i], ('ladder: missing connector after item', prev, items[prev], hex(addrs[prev]), 'next at', hex(addrs[i]))
                    prev = i
            return addrs, lab, extra, br_size, bs_size, br_place, bs_place, clusters
    raise RuntimeError('ladder: layout did not converge')


def place(G, items, bands, required=()):
    last = None
    _fails = {}
    _s0 = int(__import__("os").environ.get("SEED0", "0"))      # probe323: a start offset so that parallel processes can search disjoint seed ranges (default 0 = unchanged)
    for seed in range(_s0, _s0 + int(__import__("os").environ.get("SEEDS", "400"))):
        try:
            r = (place_once_fg if os.environ.get('FILLGAPS') else place_once)(G, items, bands, seed, required)
            print('ladder: layout seed %d' % seed)
            return r
        except RuntimeError as e:
            last = e; _fails[str(e)[:60]] = _fails.get(str(e)[:60], 0) + 1
        except AssertionError as e:
            last = e; _fails[str(e)[:60]] = _fails.get(str(e)[:60], 0) + 1
    if os.environ.get('SEEDS'): print('ladder: failure kinds', sorted(_fails.items(), key=lambda kv: -kv[1])[:8])
    raise SystemExit('ladder: no layout in seeds (%s)' % last)


def apply(G, STAGE):
    ca, out, caveguard = G['ca'], G['out'], G['caveguard']
    code = G['code']
    _snew = {}; _sei = {}; _sbands = []
    if G.get('SCAN'):
        _sitems = build_scan(G)
        _sbands = ext_bands_ay(G)
        _env0 = {k: os.environ.get(k) for k in ('SPAN', 'CAPF', 'SEED0', 'SEEDS')}
        os.environ['SPAN'] = '30000'; os.environ['CAPF'] = '1.0'
        os.environ['SEED0'] = os.environ.get('SCANSEED', '9'); os.environ['SEEDS'] = '1'      # the SCAN layout is pinned (SCANSEED 9: SCANOFF 0x12efd, SCANON 0x1df5f; 11: SCANON 0x38a3d) because EVG must still fit in the AY words that are left (checked offline)
        try: _splaced = place(G, _sitems, _sbands, ())
        finally:
            for k, v in _env0.items():
                if v is None: os.environ.pop(k, None)
                else: os.environ[k] = v
        _snew, _sei = _materialize(_sitems, _splaced)
        G['SCAN_ADDR'] = {'SCANSYNC': _splaced[1]['SCANSYNC']}
        print('SCAN blocks placed in the AY pool: %s (%d words)' % ({k: hex(v) for k, v in G['SCAN_ADDR'].items()}, len(_snew)))
    items = build_program(G, STAGE, G.get('VARIANT', ''))
    if G.get('TABLEX'): items = items + build_xprog(G)       # probe405: the handler complex as EXT blocks HX and ARMX
    if G.get('VMREAD'): items = items + build_vr(G)     # probe382: the read-out blocks (VRGO .. VRSDG and the digit wrapper VRW) join the MAIN layout
    bands = ext_bands(G)
    _b0 = list(bands)
    if G.get('AYMAIN'):
        # probe328: the AY pool (batches A and B) beyond the pinned SCAN blocks is also available to the MAIN layout; EVG then takes what is left
        _ayb = ext_bands_ay(G)
        if _snew: _ayb = leftover_bands(G, _ayb, _snew)
        if G.get('GEN'):
            # probe380: the EVG wrapper (TRIG's 3-word bsr reaches only targets more than 65 k words away) needs a far cluster with room: keep fn_1ee80 (95 writable words) and fn_1df56 (42) out of the MAIN layout; EVG takes them
            _ayb = [b_ for b_ in _ayb if not (0x1EE80 <= b_[0] < 0x1EF5C or 0x1DF56 <= b_[0] < 0x1DFAB)]
        bands = bands + _ayb
    EVG = bool(G.get('EVGUARD'))      # probe298: the wrapper block EVG (placed ONLY in the AY pool) sits between TRIG and EVTX; the probe296 layout of every other block is untouched
    _req = []
    for _called, _name in (("EVENTS", "EVTX"), ("AUTOSTART", "EXTH")) + ((("MODETOG", "MODETOGX"),) if G.get('VARIANT') in ('u', 'v', 'P', 'W') else ()) + (((G['SPEAK'], "SPEAKX"),) if G.get('VARIANT') in ('u', 'v', 'P') and not G.get('NOSPEAKX') else ()):
        if G.get('TABLEX') and _called == "AUTOSTART": continue          # probe405: the only call site (the handler) moved into the EXT block HX, which calls EXTH directly
        if G.get('VMREAD') and _called == "AUTOSTART": _name = "VRW"          # probe382: HANDLER's bsr AUTOSTART goes to VRW (> 65 k words away), VRW calls EXTH
        if EVG and _called == "EVENTS": continue
        if G.get('G5DIAG') and _called == "AUTOSTART": continue          # probe300: HANDLER's bsr AUTOSTART goes to DGW (AY pool), which calls EXTH; checked in the pool placement below
        _idx = [i for i, it in enumerate(G['prog']) if it[0] == "bsr" and it[1] == _called]
        if _called == "EVENTS": _idx = [i for i in _idx if any(G['prog'][j] == ("label", "T_EV") for j in range(max(0, i - 3), i))]
        assert len(_idx) == 1, (_called, _idx)
        _req.append((G['addrs'][_idx[0]], _name))
    if G.get('TABLEX'):
        for _called, _name in (("GATE", "HX"), ("TRIG", "ARMX")):          # the window trampoline's bsr and MODETOG's ARM call: placeholders retargeted to the EXT blocks
            _idx = [i for i, it in enumerate(G['prog']) if it[0] == "bsr" and it[1] == _called]
            assert len(_idx) == 1, (_called, _idx)
            _req.append((G['addrs'][_idx[0]], _name))
    if G.get('GEN') and G.get('GEN_FORCE'):
        G['FORCE'] = dict(G['GEN_FORCE'])          # probe380: the four blocks the old 3-word bsr operands reach (EVTX, EXTH, MODETOGX, SPEAKX) must sit more than 65 k words from their call sites: pin them to the far clusters
    try: placed = place(G, items, bands, _req)
    finally:
        if G.get('GEN') and G.get('GEN_FORCE'): G.pop('FORCE', None)
    addrs, lab, extra, br_size, bs_size, br_place, bs_place, clusters = placed
    print('ladder rung %d: %d EXT items, bands %d (%d words), clusters %s' % (STAGE, len(items), len(bands), sum(b - a for a, b in bands),
          [('%#x' % c[0][0], sum(y - x for x, y in c)) for c in clusters]))
    new, ei = _materialize(items, placed)
    assert not (set(new) & set(_snew))
    new.update(_snew); ei.update(_sei)           # probe323: the SCAN words (empty unless SCAN)
    allbands = list(bands) + list(_sbands)
    if EVG:
        _ti = [i for i, it in enumerate(G['prog']) if it[0] == "bsr" and it[1] == "EVENTS" and any(G['prog'][j] == ("label", "T_EV") for j in range(max(0, i - 3), i))]
        assert len(_ti) == 1
        G['_PEEKF'] = lab.get('PEEKF')
        G['_VRGO'] = lab.get('VRGO')
        evitems = build_evg(G, lab['EVTX'])
        _evreq = [(G['addrs'][_ti[0]], "EVG")]
        aybands = ext_bands_ay(G)
        if _snew: aybands = leftover_bands(G, aybands, _snew)          # probe323: the AY words the SCAN blocks took are not available to EVG
        if G.get('AYMAIN'): aybands = leftover_bands(G, aybands, new)    # probe328: nor the AY words the main layout took
        if G.get('G5ZAP') and not G.get('G5DIAG'):
            _lbands = leftover_bands(G, _b0, new)          # probe302: the leftover fill of the twelve confirmed functions joins the AY pool (as probe300)
            print('G5ZAP leftover runs:', [(hex(a_), b_ - a_) for a_, b_ in _lbands])
            aybands = aybands + _lbands
        if G.get('G5DIAG'):
            # probe300 (BN): the read-only report blocks (EVG's arm, DGW) are placed TOGETHER with the EVG wrapper into the AY pool plus the leftover fill of the twelve confirmed functions (the main layout does not move)
            _ai = [i for i, it in enumerate(G['prog']) if it[0] == "bsr" and it[1] == "AUTOSTART"]
            assert len(_ai) == 1
            evitems = build_dg(G, lab['EXTH']) + evitems
            _evreq.append((G['addrs'][_ai[0]], "DGW"))
            _lbands = leftover_bands(G, _b0, new)
            print('G5 leftover runs in the twelve functions:', [(hex(a_), b_ - a_) for a_, b_ in _lbands])
            aybands = aybands + _lbands
        _env = {k: os.environ.get(k) for k in ('SPAN', 'CAPF')}
        os.environ['SPAN'] = '30000'; os.environ['CAPF'] = '1.0'          # the AY functions are far apart: one cluster per function (2-word branch reach), full capacity
        if G.get('G5DIAG'):
            # DGW is forced into the AY2 cluster (0x1df5f): its HANDLER bsr is a 3-word form that reaches only targets more than 65 k words away, the AY3 cluster (0x38a..) is too near
            G['FORCE'] = {'DGW': 0x1df5f}
        if G.get('GEN'): print('GEN EVG debug: %d ay bands, %d words, runs %s' % (len(aybands), sum(b - a for a, b in aybands), sorted((b - a for a, b in aybands), reverse=True)[:12]))
        try: placed2 = place(G, evitems, aybands, _evreq)
        finally:
            G.pop('FORCE', None)
            for k, v in _env.items():
                if v is None: os.environ.pop(k, None)
                else: os.environ[k] = v
        print('ladder EVG wrapper: %d items placed in the AY pool (%d bands, %d words)' % (len(evitems), len(aybands), sum(b - a for a, b in aybands)))
        new2, ei2 = _materialize(evitems, placed2)
        assert not (set(new) & set(new2))
        new.update(new2); ei.update(ei2); allbands += aybands
        lab = dict(lab); lab.update(placed2[1])
    # --- every EXT word must be in a band of the twelve functions (or the AY pool), a fill word before, and not a stub
    stubs = set()
    for f in G['_NEWFN']:
        end, sa, sw = G['_NEWFN'][f]
        stubs |= {sa + k for k in range(len(sw))}
    for f in G.get('_AYFN', {}):
        end, sa, sw = G['_AYFN'][f]
        stubs |= {sa + k for k in range(len(sw))}
    bandset = {x for a, b in allbands for x in range(a, b)}
    for a, v in new.items():
        assert a in bandset and a not in stubs and caveguard.region_writable(a), hex(a)
        assert a in out or (G['SCAN_LO'] <= a < G['SCAN_HI']), ('EXT word not over fill', hex(a))
        out[a] = v
    G['EXT_WORDS'] = dict(new)
    G['EXT_INTENDED'] = ei
    # --- retarget the old 3-word bsr operands
    prog, addrs_old, bsr_size = G['prog'], G['addrs'], G['bsr_size']
    def retarget(label_before, called, newlabel):
        idx = []
        for i, it in enumerate(prog):
            if it[0] == "bsr" and it[1] == called: idx.append(i)
        if label_before:
            idx = [i for i in idx if any(prog[j] == ("label", label_before) for j in range(max(0, i - 3), i))]
        assert len(idx) == 1, (called, idx)
        i = idx[0]
        a = addrs_old[i]
        assert bsr_size[i] == 3, ('the old bsr must be a 3-word form', called, bsr_size[i])
        words = enc_bsr3(a, lab[newlabel])
        for k, v in enumerate(words): out[a + k] = v
        print('  retarget bsr at %#x: %s -> %s (%#x)' % (a, called, newlabel, lab[newlabel]))
        G.setdefault('RETARGETS', {})[a] = lab[newlabel]
    retarget("T_EV", "EVENTS", "EVG" if EVG else "EVTX")
    if not G.get('TABLEX'): retarget(None, "AUTOSTART", "DGW" if G.get('G5DIAG') else "VRW" if G.get('VMREAD') else "EXTH")
    if G.get('TABLEX'):
        retarget(None, "GATE", "HX"); retarget(None, "TRIG", "ARMX")
    if G.get('VARIANT') in ('u', 'v', 'P', 'W'): retarget(None, "MODETOG", "MODETOGX")
    if G.get('VARIANT') in ('u', 'v', 'P') and not G.get('NOSPEAKX'): retarget(None, G['SPEAK'], "SPEAKX")
    G['EXT_LABELS'] = lab
