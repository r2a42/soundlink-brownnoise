#!/usr/bin/env python3
"""virtual_press: press the speaker's centre LONG button (or a volume key) from the laptop over USB, through the real firmware.

WHAT THIS ACTUALLY IS: a thin client for a diagnostic/test interface Bose already
built into the stock firmware of every unit of this product -- it was there before
this project touched the speaker, and using it does not flash, patch, or modify the
device in any way. This script does not add, unlock-in-the-sense-of-create, or alter
any capability of the device; it only sends the same USB HID bytes a host already
could, to an interface that was always listening, the way any other USB client
sending it feature reports would. Nothing here depends on, or results from, the cave
patch or the signed-filesystem technique used elsewhere in this project -- a completely
stock, unflashed speaker responds to this the same way.

NOTE ON WHAT THAT INTERFACE OPENS: step 1 below sends that native console's own
documented-in-the-firmware unlock verb. Any owner of a unit of this product who
already has USB access to it (the same physical access this entire project requires
for everything else) can compute this unlock code for THEIR OWN unit from THEIR OWN
unit's own serial number, which is itself readable from the device before unlocking
anything (`bose-dfu info -f`). This is a vendor diagnostic-console unlock, not a
signing key or a cryptographic break, and it grants no capability beyond what physical
USB access to your own unit already implies (DFU flashing already lets you rewrite the
device; this additionally lets you inject console commands, button/volume events and
DSP memory reads/writes at runtime without a flash). It is unit-specific by
construction: no serial number is stored anywhere in this repository, and this code
cannot unlock a different unit than the one physically connected when it runs.

How (all proven on hardware 2026-10-27):
  1. TAP verb `db 96 <code>` (HID Feature report 2) unlocks the text console; the code is 0xCB9A XOR the 4-character
     groups of the unit's system serial (PS user key 0x35), which `bose-dfu info -f` prints as "HW serial". The unlock lasts
     until the USB cable is replugged (a power cycle over USB does not clear it).
  2. HID Feature report 6 (62 data bytes) carries one text line, here `kp <n>`: the console's key-press command. n is a
     DECIMAL number; the emulator-verified map (tools/xapemu.py on the real vm.app) was built for this project and is not
     separately documented in this export. Only the three numbers below are allowed by this tool: 196 -> event 0x4004
     (centre LONG; acts only in sinkStates 1, 2, 3, 13, otherwise nothing is sent), 176 -> 0x400D (volume up), 160 ->
     0x400E (volume down).
  Other kp numbers include power-off (33 -> 0x4003) and factory-reset-class ids: NEVER add them here without the owner.

Usage:  python tools/csr/virtual_press.py press        # centre long press (ON when OFF, OFF when ON)
        python tools/csr/virtual_press.py ledoff | ledrestore   # LED test mode with every LED off / back to the normal LED logic (EXPERIMENTAL)
        python tools/csr/virtual_press.py ledcfg <0-3> <0|1>   # EXPERIMENTAL: LedConfigure(led, LED_ENABLE, v) through the console `hd`
        python tools/csr/virtual_press.py volup | voldown
        python tools/csr/virtual_press.py code         # print whether the code could be computed (never prints the code)
Power on/off of the speaker itself: python tools/csr/tap_sweep.py "pw 1" / "pw 0" (a read error after pw is normal).
The code is unit-keyed: it is computed at run time from `info -f`, never stored in the repository."""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tap_sweep  # noqa: E402

DFU = os.path.join(HERE, "..", "bose-dfu", "bose-dfu.exe")
ALLOWED = {"press": "kp 196", "volup": "kp 176", "voldown": "kp 160", "ledoff": "ld 0 0", "ledrestore": "ld 3"}   # ledoff/ledrestore: the LED test command `ld` of the stock console (fn_108f7 -> fn_19054 / fn_19092; docs/deep/material-2026-10-27/CR-tap-power-keys.md section 10)


def unlock_code(serial):
    acc = 0xCB9A
    for g in range(0, len(serial), 4):
        chunk = serial[g:g + 4]
        w = 0
        for c in chunk:
            try:
                d = int(c, 16)
            except ValueError:
                d = 0xF
            w = (w << 4) | d
        if len(chunk) < 4:
            w <<= 2 * (4 - len(chunk))
        acc ^= w & 0xFFFF
    return "%04X" % acc


def hw_serial():
    out = subprocess.run([DFU, "info", "-f"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if line.startswith("HW serial"):
            return line.split(":", 1)[1].strip()
    return None


def report6(text):
    h, pid = tap_sweep.open_tap()
    if not h:
        return "<no device>"
    try:
        return h.send_feature_report(bytes([6]) + text.encode() + b"\x00" * (63 - 1 - len(text)))
    finally:
        h.close()


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "ledcfg" and sys.argv[2] in ("0", "1", "2", "3") and sys.argv[3] in ("0", "1"):
        # EXPERIMENTAL: console `hd <led> 0 <v>` = LedConfigure(led, LED_ENABLE, v) (fn_11ffe 3-argument form, decode 2026-10-27). The 0- and 1-argument forms of `hd` do other things (KalimbaPowerOff!) and are NOT reachable from here.
        sn = hw_serial()
        tap_sweep.one("db 96 " + unlock_code(sn))
        time.sleep(0.3)
        line = "hd %s 0 %s" % (sys.argv[2], sys.argv[3])
        print("sent %s: report 6 returned %s" % (line, report6(line + chr(13))))
        return
    if len(sys.argv) == 3 and sys.argv[1] == "peek" and sys.argv[2] in "01234" and len(sys.argv[2]) == 1:
        # probe362 only: console `ev <id>` with one of five SAFE ids (the default arm of the stock fn_01749 switch) = a read-only DSP PEEK:
        # 0 -> 0x4015 DM 0x2A75, 1 -> 0x402C DM 0x2AAC, 2 -> 0x402D DM 0x0300, 3 -> 0x402E DM 0x29E6, 4 -> 0x4033 DM 0x03FE.
        # NEVER send 0x4021 (BootSetMode 7: the speaker drops to USB 4005) or 0x4022 (LoaderModeEnter) (field log 2026-10-28).
        sn = hw_serial()
        tap_sweep.one("db 96 " + unlock_code(sn))
        time.sleep(0.3)
        line = "ev %d" % (0x4015, 0x402C, 0x402D, 0x402E, 0x4033)[int(sys.argv[2])]
        print("sent %s: report 6 returned %s" % (line, report6(line + chr(13))))
        return
    if len(sys.argv) != 2 or sys.argv[1] not in list(ALLOWED) + ["code"]:
        sys.exit(__doc__)
    sn = hw_serial()
    if not sn:
        sys.exit("no HW serial from bose-dfu info -f (speaker not in normal mode?)")
    code = unlock_code(sn)
    if sys.argv[1] == "code":
        print("code computed from a %d-character serial (not printed)" % len(sn))
        return
    tap_sweep.one("db 96 " + code)      # a read error is normal; a wrong code is silently ignored
    time.sleep(0.3)
    print("sent %s: report 6 returned %s" % (ALLOWED[sys.argv[1]], report6(ALLOWED[sys.argv[1]] + "\r")))


if __name__ == "__main__":
    main()
