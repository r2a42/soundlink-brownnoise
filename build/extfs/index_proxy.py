#!/usr/bin/env python3
"""Learn the Bose Updater's LOOKUP and INDEX URLs by proxying its own traffic.

HOST-SIDE ONLY. This never touches the speaker: no DFU, no partition write, no
update endpoint. It restarts the updater and asks it to start a session, which is
what makes it fetch its lookup/index files.

DIFFERENCE FROM index_sniff.py
  index_sniff.py answered every request with 502, so it learned at most the request
  line and left the updater in a failed state ("Failed to download lookup file: 99").
  This one FORWARDS: plain HTTP is relayed upstream and the response body saved, and
  CONNECT is tunnelled blind. So the updater succeeds exactly as it would without us,
  and we learn

    * the full absolute URL of each plain-HTTP fetch, and its body, or
    * `CONNECT host:443`, which proves the fetch is HTTPS and names the host while
      leaving the path invisible (no MITM, no CA installed -- a separate decision).

PROXY SETTING
  HKCU\\...\\Internet Settings is per-user and is what Qt's QNetworkAccessManager
  reads via WinINET. Admin is not needed for it and the hosts file is not touched.
  ProxyEnable/ProxyServer/ProxyOverride are saved first, restored in a finally block,
  and re-read and printed afterwards so a failed restore cannot pass silently.
"""
import json, os, re, select, socket, subprocess, sys, threading, time

PORT = 8899
KEY = r'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
EXE = r'C:\Program Files (x86)\Bose Updater\BOSEUPDATER.EXE'
LOG = os.path.join(os.environ.get('TEMP', '.'), 'BoseUpdater.log')
HERE = os.path.dirname(os.path.abspath(__file__))
CAP = os.path.join(HERE, 'capture')

events = []        # one dict per proxied connection
lock = threading.Lock()


def log(kind, **kw):
    kw['kind'] = kind
    kw['t'] = round(time.time(), 3)
    with lock:
        events.append(kw)
    print('  %-10s %s' % (kind, kw.get('detail', '')), flush=True)


# ------------------------------------------------------------------ registry

def ps(script):
    r = subprocess.run(['powershell', '-NoProfile', '-Command', script],
                       capture_output=True, text=True)
    return (r.stdout or '').strip(), (r.stderr or '').strip()


def read_proxy():
    out, _ = ps("$p = Get-ItemProperty '%s'; [pscustomobject]@{"
                "enable=$p.ProxyEnable; server=$p.ProxyServer; "
                "override=$p.ProxyOverride} | ConvertTo-Json -Compress" % KEY)
    try:
        return json.loads(out)
    except Exception:
        return {'enable': None, 'server': None, 'override': None}


def write_proxy(state):
    """state values of None or '' mean 'remove the value'."""
    cmds = []
    if state.get('enable') is None:
        cmds.append("Remove-ItemProperty '%s' -Name ProxyEnable "
                    "-ErrorAction SilentlyContinue" % KEY)
    else:
        cmds.append("Set-ItemProperty '%s' -Name ProxyEnable -Value %d -Type DWord"
                    % (KEY, int(state['enable'])))
    for name, reg in (('server', 'ProxyServer'), ('override', 'ProxyOverride')):
        v = state.get(name)
        if v in (None, ''):
            cmds.append("Remove-ItemProperty '%s' -Name %s "
                        "-ErrorAction SilentlyContinue" % (KEY, reg))
        else:
            cmds.append("Set-ItemProperty '%s' -Name %s -Value '%s'" % (KEY, reg, v))
    ps('; '.join(cmds))


# --------------------------------------------------------------------- proxy

def read_head(sock):
    data = b''
    while b'\r\n\r\n' not in data and len(data) < 65536:
        try:
            c = sock.recv(4096)
        except (socket.timeout, OSError):
            break
        if not c:
            break
        data += c
    return data


def pump(a, b):
    try:
        while True:
            r, _, _ = select.select([a, b], [], [], 30)
            if not r:
                return
            for s in r:
                try:
                    d = s.recv(16384)
                except OSError:
                    return
                if not d:
                    return
                (b if s is a else a).sendall(d)
    except OSError:
        pass


def do_connect(client, head):
    target = head.split()[1].decode('latin1')
    host, _, port = target.partition(':')
    port = int(port or 443)
    log('CONNECT', detail='%s:%d  (HTTPS -- host only, path not visible)' % (host, port),
        host=host, port=port)
    try:
        up = socket.create_connection((host, port), timeout=15)
    except OSError as e:
        client.sendall(b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n')
        log('error', detail='upstream connect failed %s: %s' % (target, e))
        return
    client.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
    with up:
        pump(client, up)


def do_plain(client, head, body_extra):
    line = head.split(b'\r\n')[0].decode('latin1')
    parts = line.split()
    method, url = (parts + ['', ''])[:2]
    m = re.match(r'http://([^/:]+)(?::(\d+))?(/.*)?$', url, re.I)
    if not m:
        client.sendall(b'HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n')
        log('error', detail='not absolute-form: %s' % line)
        return
    host, port, path = m.group(1), int(m.group(2) or 80), m.group(3) or '/'
    log('HTTP', detail='%s %s' % (method, url), method=method, url=url)

    lines = head.split(b'\r\n')
    out = [method.encode() + b' ' + path.encode() + b' HTTP/1.1']
    for h in lines[1:]:
        if not h:
            break
        name = h.split(b':', 1)[0].lower()
        if name in (b'proxy-connection', b'connection', b'accept-encoding'):
            continue
        out.append(h)
    out += [b'Connection: close', b'', b'']
    req = b'\r\n'.join(out) + body_extra

    try:
        up = socket.create_connection((host, port), timeout=20)
    except OSError as e:
        client.sendall(b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n')
        log('error', detail='upstream connect failed %s: %s' % (host, e))
        return
    with up:
        up.settimeout(25)
        up.sendall(req)
        resp = b''
        while True:
            try:
                d = up.recv(32768)
            except (socket.timeout, OSError):
                break
            if not d:
                break
            resp += d
    if resp:
        try:
            client.sendall(resp)
        except OSError:
            pass
    status = resp.split(b'\r\n')[0].decode('latin1', 'replace') if resp else '<empty>'
    body = resp.split(b'\r\n\r\n', 1)[1] if b'\r\n\r\n' in resp else b''
    name = re.sub(r'[^A-Za-z0-9._-]', '_', url)[-120:]
    os.makedirs(CAP, exist_ok=True)
    p = os.path.join(CAP, name or 'body')
    with open(p, 'wb') as f:
        f.write(body)
    log('reply', detail='%s  %d body bytes -> %s'
        % (status, len(body), os.path.relpath(p, HERE)),
        url=url, status=status, bytes=len(body), path=p)


def handler(client):
    try:
        client.settimeout(10)
        head = read_head(client)
        if not head:
            return
        if head[:1] == b'\x16':
            log('tls-direct', detail='raw TLS to the proxy port: %s' % head[:8].hex())
            return
        first = head.split(b'\r\n')[0]
        body_extra = head.split(b'\r\n\r\n', 1)[1] if b'\r\n\r\n' in head else b''
        if first.upper().startswith(b'CONNECT'):
            do_connect(client, head)
        else:
            do_plain(client, head, body_extra)
    except Exception as e:
        log('error', detail='handler: %r' % (e,))
    finally:
        try:
            client.close()
        except OSError:
            pass


def serve(stop):
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('127.0.0.1', PORT))
    srv.listen(64)
    srv.settimeout(1)
    while not stop.is_set():
        try:
            c, _ = srv.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        threading.Thread(target=handler, args=(c,), daemon=True).start()
    srv.close()


# ------------------------------------------------------------------- updater

def updater_call(endpoint, **params):
    import urllib.parse, urllib.request
    params.setdefault('callback', 'BoseUpdater.remoteCallback')
    params.setdefault('token', 'T%012x' % (int(time.time() * 1000) & 0xFFFFFFFFFFFF))
    params.setdefault('userAgent', 'Mozilla/5.0')
    qs = '&'.join('%s=%s' % (k, urllib.parse.quote(str(v), safe='/.-_:'))
                  for k, v in params.items())
    url = 'http://127.0.0.1:49312/updater/%s?%s' % (endpoint, qs)
    req = urllib.request.Request(url, headers={'Origin': 'https://btu.bose.com',
                                               'Referer': 'https://btu.bose.com/'})
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # never self-proxy
    with op.open(req, timeout=25) as r:
        return r.read().decode('utf-8', 'replace').strip()


def wait_port(port, secs=40):
    for i in range(secs):
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=2):
                return i
        except OSError:
            time.sleep(1)
    return None


def main():
    saved = read_proxy()
    print('saved proxy state: %s' % saved)
    stop = threading.Event()
    threading.Thread(target=serve, args=(stop,), daemon=True).start()
    print('forwarding proxy up on 127.0.0.1:%d' % PORT)
    mark = os.path.getsize(LOG) if os.path.exists(LOG) else 0

    try:
        write_proxy({'enable': 1, 'server': '127.0.0.1:%d' % PORT, 'override': '<local>'})
        now = read_proxy()
        print('proxy set to:      %s' % now)
        if str(now.get('server')) != '127.0.0.1:%d' % PORT:
            print('*** proxy did not take; aborting without touching anything else')
            return 1

        print('\nrestarting the updater (Qt reads the proxy at startup)...')
        ps("Get-Process BOSEUPDATER -ErrorAction SilentlyContinue | "
           "Stop-Process -Force -ErrorAction SilentlyContinue")
        time.sleep(2)
        ps("Start-Process '%s'" % EXE)
        t = wait_port(49312)
        print('  local API port open after %ss' % t)
        if t is None:
            return 1
        time.sleep(4)

        print('\nstartUpdaterSession (this is the call that pulls lookup + index):')
        try:
            print('  reply: %s' % updater_call('startUpdaterSession')[:160])
        except Exception as e:
            print('  call failed: %r' % (e,))
        print('\nwatching... (30 s)')
        time.sleep(30)
    finally:
        write_proxy(saved)
        back = read_proxy()
        ok = (str(back.get('enable')) == str(saved.get('enable'))
              and str(back.get('server')) == str(saved.get('server'))
              and str(back.get('override')) == str(saved.get('override')))
        print('\nproxy restored:    %s  %s'
              % (back, 'OK' if ok else '*** MISMATCH - CHECK MANUALLY'))
        stop.set()

    print('\n=== updater log, new lines ===')
    if os.path.exists(LOG):
        with open(LOG, errors='replace') as f:
            f.seek(mark)
            for l in f.read().splitlines():
                print('  ' + l)

    print('\n=== what the updater fetched ===')
    if not events:
        print('  nothing arrived through the proxy.')
    urls = [e for e in events if e['kind'] == 'HTTP']
    conns = [e for e in events if e['kind'] == 'CONNECT']
    for e in urls:
        print('  PLAIN HTTP  %s' % e['url'])
    for e in sorted({(c['host'], c['port']) for c in conns}):
        print('  CONNECT     %s:%d   (HTTPS, path not visible)' % e)
    os.makedirs(CAP, exist_ok=True)
    with open(os.path.join(CAP, 'transcript.json'), 'w') as f:
        json.dump(events, f, indent=1)
    print('\ntranscript: %s' % os.path.join(CAP, 'transcript.json'))
    return 0 if (urls or conns) else 2


if __name__ == '__main__':
    sys.exit(main())
