#!/usr/bin/env python3
"""Offline world-model gate for probe236 (probe220 plus volume steps on events 0x400D/0x400E, a hold release on a manual stop and on the A2DP disconnect event 0x4716) -- 2026-10-16. NOT independently reviewed.
NO device, no flash tool: pure emulation (tools/cavesim.py, the clocked world). The raw source is fed the real payload (--raw-p2 file:build/payload/r3/brown_8000_58968_s63.adpcm,
whose sha256 is pinned below) and the chunk is 2 x 58,968 / 8,000 = 14,742 ms. Every row greps the simulator's report with regular expressions (a leading ! means: must NOT match).
    python build/hook/assemble_probe236.py                     # first (writes probe236_words.json)
    python build/hook/gate_probe236.py [--list] [--words PATH]
"""
import hashlib
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
PAYLOAD_REL = 'build/payload/r3/brown_8000_58968_s63.adpcm'
PAYLOAD_SHA = '1dc9dac050481af1bf398e3f99a82c2bbf605b821c2fee9b7b4bad8328afb968'
P = open(os.path.join(ROOT, PAYLOAD_REL), 'rb').read()
assert hashlib.sha256(P).hexdigest() == PAYLOAD_SHA and len(P) == 58968
CHUNK_MS = 2 * len(P) * 1000 // 8000          # 14,742 ms
assert CHUNK_MS == 14742
assert tuple(P[:4]) == (0x77, 0x7F, 0x77, 0xC6)

BASE = ['--entry', '0x3E21D', '--mem', '59e=d', '--caller-frame', '23', '--world', '--music', 'playing',
        '--chunk-ms', str(CHUNK_MS), '--raw-p2', 'file:' + PAYLOAD_REL, '--raw-pack', 'octet', '--raw-prime', '126', '--steps', '400000000']
def _variant(name, pos):
    """a copy of the payload with the byte at POS flipped (XOR 0x55), written once under build/payload/r3/"""
    d = bytearray(P)
    d[pos] ^= 0x55
    rel = 'build/payload/r3/payload_r4_' + name
    ap = os.path.join(ROOT, rel)
    if not (os.path.exists(ap) and open(ap, 'rb').read() == bytes(d)):
        with open(ap, 'wb') as f:
            f.write(d)
    return rel


V0, V3, V1000 = _variant('corrupt0', 0), _variant('corrupt3', 3), _variant('corrupt1000', 1000)
NOLEAK = r'![1-9][0-9]* never closed'
NOWRITE = [r'!OverwriteSink', r'!SinkMap', r'!SinkClaim', r'!SinkFlush', r'!PartitionSetMessageDigest', r'!SinkClose']

SCEN = []


def S(group, name, extra, regex, horizon=60000):
    SCEN.append((group, name, BASE + ['--horizon', str(horizon)] + extra, list(regex)))


def M(group, name, extra, regex, horizon=60000):
    """the manual (centre long press at 0 ms) rows inherited from probe209: unchanged engine"""
    S(group, name, ['--press', '0:4004'] + extra, regex, horizon)


def chunks(n_started, n_ended=None):
    return [r'chunks started: %d, ended: %d' % (n_started, n_started if n_ended is None else n_ended)]


# ------------------------------------------------------------------ probe236 (LEAN): the cold start of the cave's own DSP
OK_SEQ = [r'MessageKalimbaTask +AL=0xba3c', r'FileFind +AL=0x0001 AH=0xbd75', r'KalimbaLoad', r'SETPLUGIN\(1\) accepted', r'LOADPARAMS\(0x2270\) -> PARAMS_LOADED',
          r'KalimbaSendLongMessage\(0x1002, len 8', r'KalimbaSendLongMessage\(0x10a0, len 7, @0x[0-9a-f]+ = \[0001 0001 0001 0001 0001 0001 0001\]', r'KalimbaSendMessage\(0x1001, 0x0002',
          r'KalimbaSendMessage\(0x1070, 0x12c0, b=0x0080', r'KalimbaSendMessage\(0x1071, 0x12c0, b=0x0640', r'StreamRegionSource +AL=0x[0-9a-f]+ AH=0x0009', r'StreamKalimbaSink +AL=0x0000',
          r'StreamConnect', r'KalimbaSendMessage\(0x7ab3, 0x28f6, b=0x0000, c=0x0000\) -> TRUE', r'GO: DSP running']
S('COLD', 'long press with NO DSP (nothing ever connected): load, MUSIC_READY, SETPLUGIN+LOADPARAMS, PARAMS_LOADED, DAC, volume, types, mode, rates, ONE silent SBC frame into port 0, tone rate + poke, GO; the first chunk 1500 ms later; nothing spoken',
  ['--dsp', 'down', '--press', '0:4004'], OK_SEQ + [r'#1 start +1500 ms.*14742 ms', r'chunks started: 3, ended: 2', r'spoken: \(nothing\)', r'port-3 rules: OK', r'!violat', r'DSP: loaded'] + NOWRITE, horizon=40000)
S('COLD', 'the order inside the bring-up: GO is the LAST message before the poll; the frame is connected before the tone rate and GO',
  ['--dsp', 'down', '--press', '0:4004'], [r'(?s)StreamRegionSource.*StreamConnect.*KalimbaSendMessage\(0x1072, 0x1f40, b=0x0002.*GO: DSP running'], horizon=3000)
S('COLD', 'KalimbaLoad refused: 0x3E "bluetooth off" is spoken, no chunk',
  ['--dsp', 'down', '--fail', 'KalimbaLoad', '--press', '0:4004'], [r'spoken: 0x3e', r'chunks started: 0'], horizon=20000)
S('COLD', 'the DSP refuses 0x1001 (SETMODE): the teardown (KalimbaPowerOff, fn_1f12b) then 0x24 "switching call", no chunk',
  ['--dsp', 'down', '--dsp-refuse', '1001', '--press', '0:4004'], [r'KalimbaPowerOff', r'spoken: 0x24', r'chunks started: 0', r'DSP: unloaded'], horizon=20000)
S('COLD', 'the DSP refuses 0x10a0 (output types): teardown then 0x24, no chunk',
  ['--dsp', 'down', '--dsp-refuse', '10a0', '--press', '0:4004'], [r'KalimbaPowerOff', r'spoken: 0x24', r'chunks started: 0'], horizon=20000)
S('COLD', 'the DSP refuses 0x1072 before GO: teardown then 0x24, no chunk',
  ['--dsp', 'down', '--dsp-refuse', '1072', '--press', '0:4004'], [r'spoken: 0x24', r'chunks started: 0'], horizon=20000)
S('COLD', 'StreamConnect of the silent frame refused: teardown then 0x3A "heart rate not detected", no chunk',
  ['--dsp', 'down', '--fail', 'StreamConnect', '--press', '0:4004'], [r'KalimbaPowerOff', r'spoken: 0x3a', r'chunks started: 0'], horizon=20000)
S('COLD', 'StreamRegionSource refused: teardown then 0x3A, no chunk',
  ['--dsp', 'down', '--fail', 'StreamRegionSource', '--press', '0:4004'], [r'KalimbaPowerOff', r'spoken: 0x3a', r'chunks started: 0'], horizon=20000)
S('WARM', 'long press with the stock DSP already loaded (a stream): no load, no feed; the first chunk at 1000 ms; nothing spoken (the old press)',
  ['--dsp', 'up', '--press', '0:4004'], [r'!KalimbaLoad', r'!StreamRegionSource', r'#1 start +1000 ms', r'chunks started: 5, ended: 4', r'spoken: \(nothing\)', r'port-3 rules: OK'] + NOWRITE, horizon=60000)
S('GONE', 'the DSP unloads at 20000 ms (music paused): at the next seam the poll finds no DSP and the cave loads its OWN, brings it up and resumes the chunks',
  ['--dsp', 'up', '--press', '0:4004', '--unload-at', '20000'], [r'KalimbaLoad', r'GO: DSP running', r'spoken: \(nothing\)', r'chunks started: [3-9]'], horizon=75000)

FRAME = [('FRAME', 'tools/framecheck.py: no store into the top two slots of any function frame (per function)', 'fc'),
         ('FRAME', 'cavesim static hazards: none except the whole-image frame line (framecheck answers it per function) and data blocks', 'hz')]


def run_scen(words, args, regex):
    cmd = [sys.executable, 'tools/cavesim.py', words] + args
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=1800)
    out = r.stdout + r.stderr
    bad = []
    if r.returncode not in (0, 1):
        bad.append('exit code %d' % r.returncode)
    for rx in regex:
        neg = rx.startswith('!')
        pat = rx[1:] if neg else rx
        found = re.search(pat, out) is not None
        if found == neg:
            bad.append(('must NOT match: ' if neg else 'missing: ') + pat)
    return bad, out


def run_frame(words, kind):
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import framecheck
    if kind == 'fc':
        fnd = framecheck.check(framecheck.load(words))
        return ['0x%05x %s inside enterl -%d: slot %d is part of the saved return address' % (a, t, k, n) for a, k, n, t in fnd], ''
    r = subprocess.run([sys.executable, 'tools/cavesim.py', words, '--entry', '0x3E21D', '--brief'], cwd=ROOT, capture_output=True, text=True, timeout=600)
    data = framecheck.data_addrs(framecheck.load(words))
    bad = []
    for ln in (r.stdout + r.stderr).splitlines():
        if ln.strip().startswith('HAZARD') and 'frame slot' not in ln:
            m = re.match(r'\s*HAZARD\s+0x([0-9A-Fa-f]+)', ln)
            if m and int(m.group(1), 16) in data:
                continue
            bad.append(ln.strip()[:200])
    return bad, ''


def main():
    argv = sys.argv[1:]
    if '--list' in argv:
        for i, s in enumerate(SCEN):
            print('%2d %-8s %s' % (i, s[0], s[1]))
        return 0
    words = os.path.join(ROOT, 'build', 'hook', 'probe236_words.json')
    if '--words' in argv:
        words = argv[argv.index('--words') + 1]
    fails = ran = 0
    only = int(argv[argv.index('--only') + 1]) if '--only' in argv else None
    for i, (g, name, args, regex) in enumerate(SCEN):
        if only is not None and i != only: continue
        bad, out = run_scen(words, args, regex)
        ran += 1
        print('%s %2d %-7s %s' % ('FAIL' if bad else 'ok  ', i, g, name), flush=True)
        for b in bad:
            print('      -> %s' % b)
        if bad:
            fails += 1
            print('\n'.join('      | ' + ln[:200] for ln in out.splitlines()[-16:]), flush=True)
    for j, (g, name, kind) in enumerate(FRAME if only is None else []):
        bad, out = run_frame(words, kind)
        ran += 1
        print('%s %2d %-7s %s' % ('FAIL' if bad else 'ok  ', len(SCEN) + j, g, name), flush=True)
        for b in bad:
            print('      -> %s' % b)
        if bad:
            fails += 1
    print('\n%d scenario(s) run, %d failed' % (ran, fails))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
