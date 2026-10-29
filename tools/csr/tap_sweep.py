#!/usr/bin/env python3
"""Sweep the TAP verbs recovered from vm.app's table C (0x79ac0, 18 entries).

Sends each verb BARE (no arguments). Re-opens the HID handle per command so a
stall on an unsupported verb cannot poison the next one.
Only verbs passed on the command line are sent -- nothing is hardcoded to run.
"""
import sys, time
import hid

VID = 0x05A7
USAGE_PAGE = 0xFF00
TAP = 2
RESP = 126

def open_tap():
    for d in hid.enumerate(VID, 0):
        if d.get("usage_page") == USAGE_PAGE:
            h = hid.device(); h.open_path(d["path"]); h.set_nonblocking(0)
            return h, d["product_id"]
    return None, None

def one(cmd):
    h, pid = open_tap()
    if not h: return "<no device>"
    try:
        if pid != 0x40FE:
            return f"<device in PID 0x{pid:04x}, not normal mode>"
        try:
            h.send_feature_report(bytes([TAP]) + cmd.encode() + b"\x00")
        except Exception as e:
            return f"<send failed: {e}>"
        time.sleep(0.08)
        try:
            r = h.get_feature_report(TAP, 1 + RESP)
        except Exception as e:
            return f"<STALL/read error: {e}>"
        if not r: return "<empty>"
        b = bytes(r)
        if b and b[0] == TAP: b = b[1:]
        txt = b.split(b"\x00", 1)[0]
        if not txt: return "<null response>"
        return txt.decode("utf-8", "replace")
    finally:
        try: h.close()
        except Exception: pass

if __name__ == "__main__":
    verbs = sys.argv[1:]
    if not verbs: sys.exit("usage: tapsweep.py <verb> [verb...]")
    for v in verbs:
        r = one(v)
        print(f"  {v:>4} -> {r}")
        time.sleep(0.25)
