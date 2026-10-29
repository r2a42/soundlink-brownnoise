#!/usr/bin/env python3
"""voltest.py: record the laptop microphone while sending timed TAP / console commands to the speaker (DEVICE ACCESS).

Usage (from the repo root):
  python -I tools/measure/voltest.py NAME SECONDS "t:cmd,t:cmd,..."
  NAME     output file stem; the recording is written to measure_out/NAME.wav (16 kHz mono, tools/mic_rec.ps1)
  SECONDS  recording length
  cmd      pw1 | pw0 | db (unlock; the code is computed from `bose-dfu info -f`, never stored) | any console line, e.g. "kp 196" (centre long press), "kp 176"/"kp 160" (volume up/down), "ev 16405"
Example (noise on at 90 s, off at 150 s):  python -I tools/measure/voltest.py run1 190 "0:pw1,88:db,90:kp 196,150:kp 196"
Notes: the unlock lasts until the USB cable is replugged; a read error after pw/db is normal. Never send ev 16417 (0x4021) or ev 16418 (0x4022): see docs/dsp-generator-route.md section 7.
Check afterwards that the speaker did not reset: the 40fe node's DEVPKEY_Device_LastArrivalDate must not have moved."""
import os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools", "csr"))
import tap_sweep      # noqa: E402
import virtual_press  # noqa: E402

name, sec, steps = sys.argv[1], int(sys.argv[2]), sys.argv[3]
os.makedirs(os.path.join(ROOT, "measure_out"), exist_ok=True)
out = os.path.join(ROOT, "measure_out", name + ".wav")
serial = virtual_press.hw_serial()
code = virtual_press.unlock_code(serial) if serial else None


def rep6(text):
    h, pid = tap_sweep.open_tap()
    if not h:
        return "<no device>"
    try:
        return h.send_feature_report(bytes([6]) + text.encode() + b"\x00" * (63 - 1 - len(text)))
    finally:
        h.close()


rec = subprocess.Popen(["powershell", "-File", os.path.join(ROOT, "tools", "mic_rec.ps1"), "-Seconds", str(sec), "-Out", out],
                       stdout=subprocess.PIPE, text=True)
t0 = time.time()


def at(t):
    while time.time() - t0 < t:
        time.sleep(0.05)


for item in steps.split(","):
    t, cmd = item.split(":", 1)
    at(float(t))
    if cmd == "pw1":
        r = tap_sweep.one("pw 1")
    elif cmd == "pw0":
        r = tap_sweep.one("pw 0")
    elif cmd == "db":
        r = tap_sweep.one("db 96 " + code) if code else "<no serial>"
    else:
        r = rep6(cmd + "\r")
    print("%.1f %s -> %s" % (time.time() - t0, cmd, r), flush=True)
print(rec.communicate()[0])
