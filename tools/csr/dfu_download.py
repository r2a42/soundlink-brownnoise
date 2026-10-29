#!/usr/bin/env python3
"""Write a DFU image to a Bose device over USB HID.

THIS WRITES TO THE DEVICE. Read the safety notes before using it.

    python dfu_download.py --dry-run             image.dfu
    python dfu_download.py --expect-sha256 <hex> image.dfu --i-mean-it

Framing is taken from tchebb/bose-dfu src/protocol.rs, which derived it from
USB captures of Bose's official updater:

    SET_FEATURE report 1:
      [0] report id = 1
      [1] 0x01  = DFU_DNLOAD
      [2:4] block number, u16 LE
      [4:6] payload length, u16 LE
      [6:]  payload, up to 1017 bytes
    GET_FEATURE report 2 (GET_STATUS) returns:
      [0] report id  [1] status  [2:5] poll timeout u24 LE  [5] state

The 16-byte DFU suffix is NOT sent -- AN093: the host "sends the contents of
the file to the device, with the exception of the DFU Suffix Area", and
bose-dfu does exactly that. Transfer ends with an empty block; the device
then manifests and should land in dfuIDLE.

SAFETY
  * --i-mean-it is required to send anything.
  * --expect-sha256 is required with --i-mean-it: the file's hash must match
    or nothing is sent. This exists so you cannot fat-finger the wrong image.
  * The transfer ABORTS the moment GET_STATUS reports anything but OK.
  * AN093 warns that persistent-store areas are written BEFORE any checksum
    or signature is verified, and that bad PS keys can leave a device that no
    further DFU can recover. Code areas are safer: the loader withholds each
    area's first word until the whole area verifies. Prefer images with no PS
    areas for anything experimental.
  * Recovery for anything short of a device that stops enumerating is the
    official Bose Updater reinstalling stock firmware.
"""
import argparse, hashlib, sys, time

try:
    import hid
except ImportError:
    sys.exit("pip install hidapi")

VID = 0x05A7
NORMAL_PID = 0x40FE
DFU_PID = 0x4022
USAGE_PAGE = 0xFF00
RID_UPLOAD_DOWNLOAD = 1
RID_GETSTATUS = 2
RID_STATECMD = 3
DFU_DNLOAD = 0x01
XFER_DATA_SIZE = 1017
SUFFIX_LEN = 16
ENTER_DFU = [1, 0xB0, 0x07]
EXIT_DFU = 0xFF

STATES = {0: "appIDLE", 1: "appDETACH", 2: "dfuIDLE", 3: "dfuDNLOAD_SYNC",
          4: "dfuDNBUSY", 5: "dfuDNLOAD_IDLE", 6: "dfuMANIFEST_SYNC",
          7: "dfuMANIFEST", 8: "dfuMANIFEST_WAIT_RESET", 9: "dfuUPLOAD_IDLE",
          10: "dfuERROR"}
STATUS = {0x00: "OK", 0x01: "errTARGET", 0x02: "errFILE", 0x03: "errWRITE",
          0x04: "errERASE", 0x05: "errCHECK_ERASED", 0x06: "errPROG",
          0x07: "errVERIFY", 0x08: "errADDRESS", 0x09: "errNOTDONE",
          0x0a: "errFIRMWARE", 0x0b: "errVENDOR", 0x0c: "errUSBR",
          0x0d: "errPOR", 0x0e: "errUNKNOWN", 0x0f: "errSTALLEDPKT"}


def enumerate_pid(pid):
    return [d for d in hid.enumerate(VID, 0)
            if d['product_id'] == pid and d.get('usage_page') == USAGE_PAGE]


def wait_for(pid, timeout=25):
    for _ in range(timeout):
        time.sleep(1)
        got = enumerate_pid(pid)
        if got:
            return got
    return []


def get_status(h):
    r = bytes(h.get_feature_report(RID_GETSTATUS, 1 + 6))
    if r and r[0] == RID_GETSTATUS:
        r = r[1:]
    status = r[0]
    poll = int.from_bytes(r[1:4], 'little')
    state = r[4]
    return status, poll, state


def describe(status, poll, state):
    return "status=%s poll=%dms state=%s" % (
        STATUS.get(status, hex(status)), poll, STATES.get(state, state))


def parse_suffix(data):
    if len(data) < SUFFIX_LEN:
        raise SystemExit("file too short to hold a DFU suffix")
    s = bytearray(data[-SUFFIX_LEN:])
    s.reverse()                       # the whole suffix is byte-swapped
    if bytes(s[5:8]) != b'DFU':
        raise SystemExit("no 'DFU' signature in suffix -- not a DFU file")
    return dict(crc=int.from_bytes(s[0:4], 'big'),
                suffix_len=s[4],
                bcd_dfu=int.from_bytes(s[8:10], 'big'),
                vid=int.from_bytes(s[10:12], 'big'),
                pid=int.from_bytes(s[12:14], 'big'),
                rel=int.from_bytes(s[14:16], 'big'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('image')
    ap.add_argument('--dry-run', action='store_true',
                    help='do everything except send; no device writes')
    ap.add_argument('--i-mean-it', action='store_true',
                    help='actually write to the device')
    ap.add_argument('--expect-sha256', metavar='HEX',
                    help='refuse to send unless the image hashes to this')
    args = ap.parse_args()

    data = open(args.image, 'rb').read()
    digest = hashlib.sha256(data).hexdigest()
    suf = parse_suffix(data)
    payload_len = len(data) - suf['suffix_len']
    nblocks = (payload_len + XFER_DATA_SIZE - 1) // XFER_DATA_SIZE

    print("image      : %s" % args.image)
    print("size       : %d bytes" % len(data))
    print("sha256     : %s" % digest)
    print("suffix     : vid=%#06x pid=%#06x release=%#06x bcdDFU=%#06x len=%d"
          % (suf['vid'], suf['pid'], suf['rel'], suf['bcd_dfu'], suf['suffix_len']))
    print("payload    : %d bytes -> %d data blocks + 1 empty terminator"
          % (payload_len, nblocks))

    if suf['vid'] != VID:
        print("\n*** suffix vendor id %#06x is not Bose (%#06x). Refusing."
              % (suf['vid'], VID))
        return 1
    if suf['pid'] not in (DFU_PID, 0xFFFF):
        print("\n*** suffix product id %#06x is not this device's DFU pid %#06x."
              % (suf['pid'], DFU_PID))
        return 1

    if args.expect_sha256 and digest.lower() != args.expect_sha256.lower():
        print("\n*** sha256 mismatch. Expected %s. Refusing to send."
              % args.expect_sha256)
        return 1

    if args.dry_run:
        print("\nDRY RUN -- nothing sent. Device untouched.")
        devs = enumerate_pid(NORMAL_PID) or enumerate_pid(DFU_PID)
        print("device currently visible: %s"
              % (", ".join(hex(d['product_id']) for d in devs) or "<none>"))
        return 0

    if not args.i_mean_it:
        print("\nRefusing to write without --i-mean-it.")
        return 1
    if not args.expect_sha256:
        print("\n--i-mean-it also requires --expect-sha256.")
        return 1

    # ---- get the device into DFU mode ----
    devs = enumerate_pid(DFU_PID)
    if not devs:
        norm = enumerate_pid(NORMAL_PID)
        if not norm:
            print("no Bose device found")
            return 1
        print("\nentering DFU mode...")
        h = hid.device(); h.open_path(norm[0]['path'])
        h.send_feature_report(bytes(ENTER_DFU))
        h.close()
        devs = wait_for(DFU_PID)
        if not devs:
            print("device did not re-enumerate as %#06x" % DFU_PID)
            return 1
    print("device in DFU mode (%#06x)" % DFU_PID)

    h = hid.device()
    h.open_path(devs[0]['path'])
    rc = 0
    try:
        st = get_status(h)
        print("status before: %s" % describe(*st))
        if st[0] != 0:
            print("*** device is not in an OK state; refusing to write")
            return 1

        print("\nwriting %d blocks..." % nblocks)
        prev_poll = 0
        block = 0
        sent = 0
        while True:
            chunk = data[sent:sent + XFER_DATA_SIZE]
            if sent >= payload_len:
                chunk = b''
            elif sent + len(chunk) > payload_len:
                chunk = data[sent:payload_len]
            rep = bytes([RID_UPLOAD_DOWNLOAD, DFU_DNLOAD]) \
                + (block & 0xFFFF).to_bytes(2, 'little') \
                + len(chunk).to_bytes(2, 'little') + chunk
            h.send_feature_report(rep)
            if not chunk:
                if prev_poll:
                    print("  final block sent; waiting %d ms to manifest" % prev_poll)
                    time.sleep(prev_poll / 1000.0)
            status, poll, state = get_status(h)
            prev_poll = poll
            if status != 0:
                print("\n*** ABORT at block %d: %s"
                      % (block, describe(status, poll, state)))
                rc = 1
                break
            if not chunk:
                print("  done: %s" % describe(status, poll, state))
                if state != 2:
                    print("  (expected dfuIDLE)")
                break
            if state != 5:
                print("\n*** unexpected state at block %d: %s"
                      % (block, describe(status, poll, state)))
                rc = 1
                break
            sent += len(chunk)
            block = (block + 1) & 0xFFFF
            if block % 256 == 0:
                print("  ... %d / %d bytes" % (sent, payload_len))
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
        back = wait_for(NORMAL_PID, 20)
        print("  back as: %s"
              % (", ".join(hex(d['product_id']) for d in back) or "<nothing yet>"))
    return rc


sys.exit(main())
