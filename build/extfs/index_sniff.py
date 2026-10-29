#!/usr/bin/env python3
"""Learn the URL and scheme of the Bose Updater's LOOKUP and INDEX files.

HOST-SIDE ONLY. This never touches the speaker. It does not write flash, does
not enter DFU, and does not call any update endpoint.

WHY A PROXY AND NOT THE HOSTS FILE
  The hosts file needs Administrator and we do not have it. Qt's
  QNetworkAccessManager resolves the Windows (WinINET) proxy, which lives in
  HKCU -- per-user, writable without elevation, and trivially restorable.

WHAT IT LEARNS
  * a plain `GET http://host/path` through a proxy carries the FULL absolute URL
  * an `CONNECT host:443` instead proves the fetch is HTTPS, which would mean a
    redirect needs a CA the updater trusts -- a much bigger step, not taken here

SAFETY
  The original ProxyEnable/ProxyServer values are saved first and restored in a
  finally block, and the script re-reads them afterwards and prints the result so
  a failed restore cannot pass silently.
"""
import json, os, re, socket, subprocess, sys, threading, time

PORT = 8899
KEY = r'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
EXE = r'C:\Program Files (x86)\Bose Updater\BOSEUPDATER.EXE'
LOG = os.path.join(os.environ.get('TEMP', '.'), 'BoseUpdater.log')

seen = []


def ps(script):
    r = subprocess.run(['powershell', '-NoProfile', '-Command', script],
                       capture_output=True, text=True)
    return (r.stdout or '').strip(), (r.stderr or '').strip()


def read_proxy():
    out, _ = ps("$p = Get-ItemProperty '%s'; "
                "[pscustomobject]@{enable=$p.ProxyEnable; server=$p.ProxyServer} "
                "| ConvertTo-Json -Compress" % KEY)
    try:
        return json.loads(out)
    except Exception:
        return {'enable': None, 'server': None}


def set_proxy(enable, server):
    cmd = ["Set-ItemProperty '%s' -Name ProxyEnable -Value %d -Type DWord" % (KEY, enable)]
    if server is None:
        cmd.append("Remove-ItemProperty '%s' -Name ProxyServer -ErrorAction SilentlyContinue" % KEY)
    else:
        cmd.append("Set-ItemProperty '%s' -Name ProxyServer -Value '%s'" % (KEY, server))
    ps('; '.join(cmd))


def handler(conn, addr):
    try:
        conn.settimeout(6)
        data = b''
        while len(data) < 2048:
            try:
                c = conn.recv(1024)
            except socket.timeout:
                break
            if not c:
                break
            data += c
            if b'\r\n\r\n' in data:
                break
        seen.append(data)
        head = data.split(b'\r\n')[0].decode('latin1', 'replace') if data else '<empty>'
        if data[:1] == b'\x16':
            print('  [direct TLS to this port] first bytes %s' % data[:8].hex())
        else:
            print('  %s' % head)
        # Answer so the client fails fast and cleanly rather than hanging.
        try:
            conn.sendall(b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n'
                         b'Connection: close\r\n\r\n')
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def serve(stop):
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('127.0.0.1', PORT))
    srv.listen(32)
    srv.settimeout(1)
    while not stop.is_set():
        try:
            c, a = srv.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        threading.Thread(target=handler, args=(c, a), daemon=True).start()
    srv.close()


def session_call():
    import urllib.request
    url = ('http://127.0.0.1:49312/updater/startUpdaterSession'
           '?userAgent=Mozilla/5.0&callback=BoseUpdater.remoteCallback&token=T%d'
           % int(time.time()))
    req = urllib.request.Request(url, headers={'Origin': 'https://btu.bose.com',
                                               'Referer': 'https://btu.bose.com/'})
    # Do NOT route our own loopback call through the proxy.
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open(req, timeout=20) as r:
        return r.read().decode('utf-8', 'replace').strip()


def wait_port(port, secs=30):
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
    print('listener up on 127.0.0.1:%d' % PORT)

    log_mark = os.path.getsize(LOG) if os.path.exists(LOG) else 0

    try:
        set_proxy(1, '127.0.0.1:%d' % PORT)
        now = read_proxy()
        print('proxy set to: %s' % now)
        if str(now.get('server')) != '127.0.0.1:%d' % PORT:
            print('*** proxy did not take; aborting')
            return 1

        print('\nrestarting updater so Qt picks the proxy up at startup...')
        ps("Get-Process BOSEUPDATER -ErrorAction SilentlyContinue | "
           "Stop-Process -Force -ErrorAction SilentlyContinue")
        time.sleep(2)
        ps("Start-Process '%s'" % EXE)
        t = wait_port(49312, 30)
        print('  updater port open after %ss' % t)
        if t is None:
            return 1
        time.sleep(5)

        print('\ntriggering startUpdaterSession (this is what pulls the lookup file)')
        print('  reply: %s' % session_call()[:120])
        print('\nwatching for outbound requests (25 s)...')
        time.sleep(25)
    finally:
        if saved.get('enable') is None:
            set_proxy(0, None)
        else:
            set_proxy(int(saved['enable'] or 0), saved.get('server'))
        back = read_proxy()
        print('\nproxy restored to: %s  %s' % (
            back, 'OK' if str(back) == str(saved) else '*** MISMATCH - CHECK MANUALLY'))
        stop.set()

    print('\n=== what the updater asked for ===')
    if not seen:
        print('nothing arrived. Qt may not honour the WinINET proxy here, or the')
        print('lookup file was cached. Updater log tail:')
        if os.path.exists(LOG):
            with open(LOG, errors='replace') as f:
                f.seek(log_mark)
                for l in f.read().splitlines()[-12:]:
                    print('  ' + l)
        return 2

    urls, connects = set(), set()
    for d in seen:
        txt = d.decode('latin1', 'replace')
        for m in re.finditer(r'^(GET|POST|HEAD)\s+(\S+)', txt, re.M):
            urls.add(m.group(2))
        for m in re.finditer(r'^CONNECT\s+(\S+)', txt, re.M):
            connects.add(m.group(1))
        h = re.search(r'^Host:\s*(\S+)', txt, re.M)
        if h and not urls:
            connects.add(h.group(1))
    for u in sorted(urls):
        print('  PLAIN HTTP  %s' % u)
    for c in sorted(connects):
        print('  CONNECT     %s   (HTTPS -- path not visible without MITM)' % c)
    return 0


if __name__ == '__main__':
    sys.exit(main())
