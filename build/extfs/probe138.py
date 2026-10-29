#!/usr/bin/env python3
"""probe138 -- prove the Bose Updater's updateUsingEndpointUrl channel.

THIS CAN WRITE THE SPEAKER'S EXTERNAL FLASH PARTITION. Read docs/partition-route.md
and docs/FLASH-PROTOCOL.md first.

WHAT THIS IS
  The external language filesystem (`Minnow_3.0.3_ext_signed.xuv`, a bare `fsr_dfu1`)
  is NOT installed by the boot loader -- AN093 knows only the CSR-dfu2 container, the
  file has no DFU suffix and no partition field, and `vm.app`'s own writer pairs
  StreamPartitionOverwriteSink with StreamUsbEndPointSink, i.e. the RUNNING APP does
  the partition write, fed over USB in normal mode.

  The channel that drives it is the Bose Updater desktop app's local HTTP API:

      updateUsingEndpointUrl?deviceID=&url=&version=&fileCrc=&fileSize=

  recovered verbatim from the btu.bose.com SPA bundle
  (`/prod/iot-btu-fe-core/assets/index-*.js`, `updateNaOTAUsingURL`). `url` is a
  PARAMETER, so the file is ours to choose. This script serves it from 127.0.0.1.

WHY THIS PROBE IS SAFE TO RUN FIRST
  * The payload is Bose's own unmodified signed 3.0.3 ext image.
  * It contains no stack, no PS areas and no English prompts -- 25 files of
    foreign-language prompt data. Nothing in it is needed to boot or to work in en-us.
  * This unit reports `v2` = "Ext 1.1.3-6164" against main 3.0.3.6546, so installing
    the matching 3.0.3 ext pack is a legitimate upgrade, not just an experiment.
  * Recovery is the same file, re-servable, plus Bose's own updater.

VERIFICATION, and why it is not dfu_upload.py
  `tools/csr/dfu_upload.py` reads the DFU-uploadable container only. It CANNOT see the
  external partition, so FLASH-PROTOCOL step 4 does not apply verbatim here. The
  equivalent on this route is the TAP console, which reads the ext partition directly:

      v2  external flash version   "Ext 1.1.3-6164"  ->  expect "Ext 3.0.3-6546"
      la  installed languages
      vr  main firmware version    must NOT change
      lc  current locale

  Both are read-only verbs from the swept table and are checked before and after.

Usage
  python build/extfs/probe138.py                      # dry run: no write
  python build/extfs/probe138.py --i-mean-it --expect-sha256 <hex>
"""
import argparse, functools, hashlib, http.server, json, os, socket, subprocess
import sys, threading, time, urllib.parse, urllib.request, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
IMAGE = os.path.join(ROOT, 'firmware', 'bose', 'minnow_3.0.3',
                     'Minnow_3.0.3_ext_signed.xuv')

# index.xml, device 0x4022, RELEASE 3.0.3.6546, the SUBID=1 TARGET=1 image.
EXPECT_LEN = 16727488
EXPECT_CRC = 0xEB198EC7
VERSION = '3.0.3.6546'
CRC_PARAM = '0X%08X' % EXPECT_CRC          # index.xml's own spelling

BASE = 'http://127.0.0.1:49312/updater'
BROWSER_UA = 'Mozilla/5.0'                 # longer/encoded UAs crash the updater
ORIGIN = 'https://btu.bose.com'
EXE = r'C:\Program Files (x86)\Bose Updater\BOSEUPDATER.EXE'

TAP_BEFORE_AFTER = ['vr', 'v2', 'lc', 'la']


# ---------------------------------------------------------------- updater API

def nonce():
    return 'T%012x' % (int(time.time() * 1000) & 0xFFFFFFFFFFFF)


def call(endpoint, **params):
    params.setdefault('callback', 'BoseUpdater.remoteCallback')
    params.setdefault('token', nonce())
    qs = '&'.join('%s=%s' % (k, urllib.parse.quote(str(v), safe='/.-_:'))
                  for k, v in params.items())
    url = '%s/%s?%s' % (BASE, endpoint, qs)
    req = urllib.request.Request(url, headers={'Origin': ORIGIN,
                                               'Referer': ORIGIN + '/'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode('utf-8', 'replace').strip()
    except Exception as e:
        return '<%s: %s>' % (type(e).__name__, e), None
    if body.startswith('BoseUpdater.remoteCallback'):
        i, j = body.find('('), body.rfind(')')
        if i != -1 and j > i:
            body = body[i + 1:j]
    try:
        args = json.loads('[' + body + ']')
    except Exception:
        return body, None
    payload = next((a for a in args if isinstance(a, (dict, list))), None)
    status = next((a for a in reversed(args) if isinstance(a, int)), None)
    return payload, status


def alive():
    """Plain TCP. Hitting an endpoint kicks off the lookup download, which
    races startUpdaterSession and dumps core."""
    try:
        with socket.create_connection(('127.0.0.1', 49312), timeout=2):
            return True
    except OSError:
        return False


def ensure_updater():
    if alive():
        return True
    if not os.path.exists(EXE):
        print('Bose Updater not installed at %s' % EXE)
        return False
    print('starting Bose Updater (must be via PowerShell Start-Process)...')
    subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Start-Process '%s'" % EXE], capture_output=True)
    for _ in range(25):
        time.sleep(1)
        if alive():
            print('  port open; settling 5 s before first request')
            time.sleep(5)
            return True
    print('  did not come up.')
    return False


def updater_session():
    p, s = call('startUpdaterSession', userAgent=BROWSER_UA)
    print('  startUpdaterSession: status=%s' % s)
    for _ in range(40):
        p, s = call('isUpdaterReady')
        val = (p or {}).get('updaterReady') if isinstance(p, dict) else None
        if s == 0 and str(val).strip().lower() == 'true':
            print('  isUpdaterReady: true')
            return True
        if not alive():
            print('  *** updater died while waiting for ready')
            return False
        time.sleep(1)
    print('  *** never became ready (needs its lookup file, and a device)')
    return False


def device_id():
    """The updater enumerates asynchronously after reporting ready, so a single
    call races it and returns an empty list. Poll. `pids=-1` is required: without
    it the endpoint answers status=-1005."""
    def harvest(o, ids):
        if isinstance(o, dict):
            for k, v in o.items():
                if k.lower() in ('deviceid', 'device_id', 'id') and \
                        isinstance(v, (str, int)):
                    ids.append(str(v))
                else:
                    harvest(v, ids)
        elif isinstance(o, list):
            for x in o:
                harvest(x, ids)

    for i in range(30):
        p, s = call('getCurrentDevicesConnected', pids='-1')
        ids = []
        harvest(p, ids)
        ids = list(dict.fromkeys(ids))
        if ids:
            print('  getCurrentDevicesConnected: status=%s ids=%s (after %ds)'
                  % (s, ids, i))
            return ids[0]
        if not alive():
            print('  *** updater died during enumeration')
            return None
        time.sleep(1)
    print('  getCurrentDevicesConnected: no device after 30 s')
    return None


# ------------------------------------------------------------------- TAP read

def tap(verb):
    """One read-only TAP verb via an external TAP prober script.

    Not included in this export: bose_probe.py is a separate, unpublished
    tool. Supply your own at BOSE_PROBE_PY (environment variable) if you
    want this function to work; otherwise this probe script is reference
    material only.
    """
    exe = os.environ.get('BOSE_PROBE_PY', '')
    try:
        out = subprocess.run([sys.executable, exe, '--tap', verb],
                             capture_output=True, text=True, timeout=90).stdout
    except Exception as e:
        return '<%s>' % e
    lines = [l.strip() for l in out.splitlines() if l.strip().startswith('->')]
    return lines[-1][2:].strip().strip("'") if lines else '<no reply>'


def tap_snapshot(label):
    print('\n--- TAP %s ---' % label)
    got = {}
    for v in TAP_BEFORE_AFTER:
        got[v] = tap(v)
        print('  %-3s %s' % (v, got[v]))
    return got


# --------------------------------------------------------------- file serving

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *a):
        print('  [http] ' + fmt % a)


def serve(directory):
    h = functools.partial(Handler, directory=directory)
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


# -------------------------------------------------------------------- the run

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', default=IMAGE)
    ap.add_argument('--i-mean-it', action='store_true',
                    help='actually send the update request')
    ap.add_argument('--expect-sha256', metavar='HEX',
                    help='required with --i-mean-it')
    args = ap.parse_args()

    data = open(args.image, 'rb').read()
    sha = hashlib.sha256(data).hexdigest()
    crc = zlib.crc32(data) & 0xffffffff

    print('=== probe138: updateUsingEndpointUrl channel test ===')
    print('image   : %s' % args.image)
    print('size    : %d bytes %s' % (len(data),
          'OK' if len(data) == EXPECT_LEN else 'MISMATCH vs index.xml'))
    print('crc32   : 0x%08X %s' % (crc,
          'OK' if crc == EXPECT_CRC else 'MISMATCH vs index.xml'))
    print('sha256  : %s' % sha)
    print('header  : %s' % data[:16].decode('latin1').replace('\r', '\\r').replace('\n', '\\n'))

    if len(data) != EXPECT_LEN or crc != EXPECT_CRC:
        print('\n*** image does not match index.xml. Refusing.')
        return 1
    if args.i_mean_it and not args.expect_sha256:
        print('\n*** --i-mean-it requires --expect-sha256.')
        return 1
    if args.expect_sha256 and sha.lower() != args.expect_sha256.lower():
        print('\n*** sha256 mismatch. Refusing.')
        return 1

    before = tap_snapshot('before')
    if before.get('v2', '').startswith('<'):
        print('\n*** TAP baseline failed; no verification channel. Refusing.')
        return 1

    srv, port = serve(os.path.dirname(os.path.abspath(args.image)))
    url = 'http://127.0.0.1:%d/%s' % (port, os.path.basename(args.image))
    print('\nserving image at %s' % url)

    # Prove our own server actually delivers the exact bytes before involving
    # the updater at all.
    with urllib.request.urlopen(url, timeout=30) as r:
        got = r.read()
    print('self-fetch: %d bytes, sha256 %s, %s' % (
        len(got), hashlib.sha256(got).hexdigest(),
        'IDENTICAL' if got == data else '*** DIFFERS'))
    if got != data:
        return 1

    if not ensure_updater():
        return 1
    print('\nupdater session:')
    if not updater_session():
        return 1
    did = device_id()
    if not did:
        print('\n*** no device id; is the speaker plugged in and awake?')
        return 1

    p, s = call('getCurrentDeviceInformation', deviceID=did)
    print('  getCurrentDeviceInformation: status=%s' % s)
    if isinstance(p, dict):
        # The serial is device-unique; this project keeps serials in private/.
        shown_info = {k: ('<redacted>' if k.lower() in ('serial', 'serialnumber')
                          else v) for k, v in p.items()}
        print(json.dumps(shown_info, indent=2)[:1200])

    params = dict(deviceID=did, url=url, version=VERSION,
                  fileCrc=CRC_PARAM, fileSize=str(len(data)))
    shown = '%s/updateUsingEndpointUrl?%s' % (
        BASE, '&'.join('%s=%s' % kv for kv in params.items()))
    print('\nrequest that %s be sent:\n  %s'
          % ('WILL' if args.i_mean_it else 'WOULD', shown))

    if not args.i_mean_it:
        print('\nDRY RUN -- nothing sent. Device untouched.')
        print('The speaker was only READ (TAP v2/vr/lc/la) and the image was')
        print('only served to this script itself.')
        return 0

    p, s = call('updateUsingEndpointUrl', **params)
    print('\nupdateUsingEndpointUrl: status=%s payload=%s' % (s, p))
    if s != 0:
        print('*** the updater refused the request. Nothing was written.')
        srv.shutdown()
        return 1

    print('\npolling getUpdateProgress (foreground, no background tasks)...')
    last = None
    for _ in range(180):   # 360 s; must finish inside one foreground call,
                           # because the HTTP server dies with this process
        p, s = call('getUpdateProgress', deviceID=did)
        if p != last:
            print('  %s' % json.dumps(p) if isinstance(p, (dict, list)) else '  %s' % p)
            last = p
        txt = json.dumps(p).lower() if isinstance(p, (dict, list)) else str(p).lower()
        if any(k in txt for k in ('complete', 'finish', 'success', 'error', 'fail')):
            break
        if not alive():
            print('  *** updater died mid-update')
            break
        time.sleep(2)
    srv.shutdown()

    print('\nletting the device settle before reading it back...')
    time.sleep(15)
    after = tap_snapshot('after')

    print('\n=== result ===')
    for v in TAP_BEFORE_AFTER:
        flag = 'CHANGED' if before.get(v) != after.get(v) else 'same'
        print('  %-3s %-9s %r -> %r' % (v, flag, before.get(v), after.get(v)))
    print('\nPASS criteria: v2 becomes "Ext 3.0.3-6546" and vr is UNCHANGED.')
    print('Record the outcome in docs/field-log.md and build/hook/FLASHED before')
    print('building anything else.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
