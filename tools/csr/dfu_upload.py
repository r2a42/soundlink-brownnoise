#!/usr/bin/env python3
"""Read-only DFU upload from a Bose device already in DFU mode (PID 0x4022).

Writes nothing to the device. Always attempts to leave DFU mode on the way
out, including on error or interrupt.
"""
import hid, sys, time

VID = 0x05A7
RID_UPLOAD = 1
RID_GETSTATUS = 2
RID_STATECMD = 3
HDR = 5
XFER = 1017
EXIT_DFU = 0xFF
MAX_BYTES = 8 * 1024 * 1024

STATES = {0: "appIDLE", 1: "appDETACH", 2: "dfuIDLE", 3: "dfuDNLOAD_SYNC",
          4: "dfuDNBUSY", 5: "dfuDNLOAD_IDLE", 6: "dfuMANIFEST_SYNC",
          7: "dfuMANIFEST", 8: "dfuMANIFEST_WAIT_RESET", 9: "dfuUPLOAD_IDLE",
          10: "dfuERROR"}
STATUS = {0x00: "OK", 0x01: "errTARGET", 0x02: "errFILE", 0x03: "errWRITE",
          0x04: "errERASE", 0x05: "errCHECK_ERASED", 0x06: "errPROG",
          0x07: "errVERIFY", 0x08: "errADDRESS", 0x09: "errNOTDONE",
          0x0a: "errFIRMWARE", 0x0b: "errVENDOR", 0x0c: "errUSBR",
          0x0d: "errPOR", 0x0e: "errUNKNOWN", 0x0f: "errSTALLEDPKT"}

out = sys.argv[1]

ENTER_DFU = [1, 0xB0, 0x07]


def find(pid):
    return [d for d in hid.enumerate(VID, 0)
            if d['product_id'] == pid and d.get('usage_page') == 0xFF00]


devs = find(0x4022)
if not devs:
    norm = find(0x40FE)
    if not norm:
        sys.exit("No Bose device found.")
    print("device is in normal mode; entering DFU...")
    t = hid.device(); t.open_path(norm[0]['path'])
    t.send_feature_report(bytes(ENTER_DFU))
    t.close()
    # re-enumeration takes well over 3 s on the Micro; poll for it
    for _ in range(25):
        time.sleep(1)
        devs = find(0x4022)
        if devs:
            break
    if not devs:
        sys.exit("device did not re-enumerate as PID 0x4022")

h = hid.device()
h.open_path(devs[0]['path'])
print("opened DFU device, path=%s" % devs[0]['path'])


def state():
    try:
        r = bytes(h.get_feature_report(RID_STATECMD, 2))
        v = r[1] if len(r) > 1 and r[0] == RID_STATECMD else r[0]
        return v, STATES.get(v, hex(v))
    except Exception as e:
        return None, "<%s>" % e


def status():
    try:
        r = bytes(h.get_feature_report(RID_GETSTATUS, 7))
        if r and r[0] == RID_GETSTATUS:
            r = r[1:]
        return "status=%s state=%s" % (STATUS.get(r[0], hex(r[0])),
                                       STATES.get(r[4], r[4]))
    except Exception as e:
        return "<%s>" % e


total = 0
try:
    print("state before: %s" % (state()[1],))
    print("status before: %s" % status())
    print("\nuploading...")
    with open(out, 'wb') as f:
        blocks = 0
        while total < MAX_BYTES:
            try:
                rep = h.get_feature_report(RID_UPLOAD, 1 + HDR + XFER)
            except Exception as e:
                print("  read failed after %d bytes: %s" % (total, e))
                break
            if not rep:
                print("  empty report after %d bytes" % total)
                break
            b = bytes(rep)
            if b[0] == RID_UPLOAD:
                b = b[1:]
            if len(b) < HDR:
                print("  short header after %d bytes" % total)
                break
            n = int.from_bytes(b[0:2], 'little')
            if blocks == 0:
                print("  first header: len=%d extra=%s" % (n, b[2:5].hex(' ')))
            if n > XFER:
                print("  implausible block length %d; stopping" % n)
                break
            f.write(b[HDR:HDR + n])
            total += n
            blocks += 1
            if blocks % 256 == 0:
                print("  ... %d bytes (%d blocks)" % (total, blocks))
            if n != XFER:
                print("  short block (%d) = end of image" % n)
                break
    print("\nuploaded %d bytes to %s" % (total, out))
    print("status after: %s" % status())
finally:
    print("\nleaving DFU mode...")
    try:
        h.send_feature_report(bytes([RID_STATECMD, EXIT_DFU]))
        print("  exit sent")
    except Exception as e:
        print("  exit failed (%s) -- power-cycle the speaker" % e)
    try:
        h.close()
    except Exception:
        pass
    time.sleep(5)
    back = hid.enumerate(VID, 0)
    print("  now enumerating as: %s"
          % ", ".join(hex(d['product_id']) for d in back) or "<nothing>")

# Completeness check, added 2026-10-04 (csr8670 project). On unit 2 the first readback
# silently lost one whole 1017-byte block (block 379) and still ended with a normal-looking
# "short block = end of image". The CSR-dfu2 header declares the file length at bytes
# 10..13, so compare against it. A short readback must never be mistaken for a good one.
with open(out, 'rb') as f:
    head = f.read(16)
if head[:8] == b'CSR-dfu2' and len(head) >= 14:
    declared = int.from_bytes(head[10:14], 'little')
    if declared == total:
        print("\ncomplete: %d bytes, matching the header's declared length" % total)
    else:
        print("\n!!! INCOMPLETE READBACK: got %d bytes, header declares %d (%+d)."
              % (total, declared, total - declared))
        print("!!! Do not use this file. Read back again.")
        sys.exit(2)
else:
    print("\n!!! output does not start with a CSR-dfu2 header; cannot check completeness")
    sys.exit(2)
