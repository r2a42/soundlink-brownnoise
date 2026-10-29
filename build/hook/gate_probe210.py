#!/usr/bin/env python3
"""Offline world-model gate for probe210 (probe210: probe209 plus audio-busy HOLD/RELEASE and STOP restore pokes) -- 2026-10-15. NOT independently reviewed.
NO device, no flash tool: pure emulation (tools/cavesim.py, the clocked world). The raw source is fed the real payload (--raw-p2 file:build/payload/r3/brown_8000_58968_s63.adpcm,
whose sha256 is pinned below) and the chunk is 2 x 58,968 / 8,000 = 14,742 ms. Every row greps the simulator's report with regular expressions (a leading ! means: must NOT match).
    python build/hook/assemble_probe210.py                     # first (writes probe210_words.json)
    python build/hook/gate_probe210.py [--list] [--words PATH]
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

BASE = ['--entry', '0x3E21D', '--press', '0:4004', '--mem', '59e=d', '--caller-frame', '23', '--world', '--music', 'playing',
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


def chunks(n_started, n_ended=None):
    return [r'chunks started: %d, ended: %d' % (n_started, n_started if n_ended is None else n_ended)]


# ------------------------------------------------------------------ NOMINAL
S('NOMINAL', 'a press: the delayed start at 1000 ms, then chunk after chunk 14,742 ms long with only a few ms between them (5 chunks in 60 s), nothing spoken',
  [], [r'#1 start +1000 ms.*14742 ms', r'#2 start +1575\d ms', r'#3 start +3050\d ms', r'#4 start +4525\d ms', r'chunks started: 5, ended: 4', r'spoken: \(nothing\)',
       r'silence between chunks \(ms, audible end -> next start\): 8, 8, 8, 8', r'port-3 rules: OK', r'raw partition sources \(trap 0xD3\): 5 call', r'!violat'] + NOWRITE)
S('NOMINAL', 'every rebuild sends 0x1072 (8000 Hz, b = 2) and the level poke: the chunks are all 8000 Hz, quiet level b=0x2',
  [], [r'8000 Hz  b=0x2 quiet'] + [r'#%d start' % i for i in range(1, 5)])
S('NOMINAL', 'a longer run: 90 s = 7 chunks, still no gap, no spoken id',
  [], chunks(7, 6) + [r'spoken: \(nothing\)', r'port-3 rules: OK'], horizon=100000)
S('NOMINAL', 'the lever: no store reaches the caller\'s saved return address', [], [r'caller-frame guard: stores to 0x0915, 0x0916 stop the run', r'!STOPPED'])
S('NOMINAL', 'the raw source is opened through the synthesised 0xD3 stub once per chunk', [], [r'synthesised-stub calls \{211: 5\}', r'SYNTHESISED TRAP STUB at 0x[0-9A-Fa-f]+: trap 0xD3'])

# ------------------------------------------------------------------ STOP / START
S('STOP', 'a second press at 20000 ms (chunk 2 playing): STOP: that chunk plays out (to 30,492 ms), then silence, nothing re-armed, nothing spoken',
  ['--press', '20000:4004'], [r'chunks started: 2, ended: 2', r'spoken: \(nothing\)', r'cave messages still pending: 0', r'presses: 2 swallowed'] + NOWRITE, horizon=80000)
S('STOP', 'STOP at 5000 ms (chunk 1 playing) then START at 25000 ms: the loop restarts and runs again (chunks 1, 2 and then 3 more)',
  ['--press', '5000:4004', '--press', '25000:4004'], [r'chunks started: 6, ended: 5', r'#1 start +1000 ms', r'#2 start +26000 ms', r'spoken: \(nothing\)', r'presses: 3 swallowed', r'pending: 1'], horizon=95000)
S('STOP', 'a press during the 1000 ms delay (before the first chunk): STOP, no chunk ever starts',
  ['--press', '500:4004'], [r'chunks started: 0, ended: 0', r'spoken: \(nothing\)', r'!raw partition sources \(trap 0xD3\): [1-9]'], horizon=30000)

# ------------------------------------------------------------------ the pre-start check and the refusals (each speaks one id, starts nothing, leaves no source open)
S('CHECK', 'the first source byte is wrong (a stale or garbage stream): the check refuses, 0x3B "adjust airbuds", NO chunk, the source is closed',
  ['--raw-p2', 'file:' + V0], [r'spoken: 0x3b@1000', r'chunks started: 0', NOLEAK], horizon=20000)
S('CHECK', 'the fourth source byte is wrong: the same refusal (all four bytes are checked)',
  ['--raw-p2', 'file:' + V3], [r'spoken: 0x3b@1000', r'chunks started: 0', NOLEAK], horizon=20000)
S('CHECK', 'the raw source is stale from byte 1 on (a wrong byte after the checked four is NOT detected by design): the loop runs',
  ['--raw-p2', 'file:' + V1000], [r'chunks started: [1-9]', r'spoken: \(nothing\)'], horizon=20000)
S('CHECK', 'SourceMap on the raw source returns 0: 0x3B, no chunk, the source is closed',
  ['--raw-map-zero'], [r'spoken: 0x3b@1000', r'chunks started: 0', NOLEAK], horizon=20000)
S('REFUSE', '0xD3 returns 0 (p2 erased or not readable: no raw source): 0x24 "switching call", no chunk, nothing to close',
  ['--raw-p2', 'none'], [r'spoken: 0x24@1000', r'chunks started: 0'], horizon=20000)

# ------------------------------------------------------------------ the DSP going away, limits
S('DSP', 'the DSP is gone BEFORE the first tick (unloaded at 500 ms): the first tick says 0x21 "call ended", no chunk is built',
  ['--unload-at', '500'], [r'spoken: 0x21@1000', r'chunks started: 0', NOLEAK], horizon=20000)
S('DSP', 'the DSP unloads at 20000 ms (pause the music mid-run): the loop ends at the next seam with 0x21; port 3 is free when it speaks',
  ['--unload-at', '20000'], [r'spoken: 0x21@', r'port-3 rules: OK'], horizon=60000)
S('DSP', 'a Bluetooth long press tears everything down at 20000 ms: the running chunk ends cleanly, no further chunk, no violation',
  ['--bt-teardown-at', '20000'], [r'port-3 rules: OK', r'!VIOLATION'], horizon=60000)

# ------------------------------------------------------------------ probe210 additions: audio-busy HOLD / RELEASE and the STOP restore pokes
AB = ['--audio-busy', '--mem', '72b=1']
S('HOLD', 'music PAUSED at 20000 ms with the audio-busy model: our hold (task 0xba3c) parks the plugin disconnect, the loop keeps running (5 chunks in 60 s), nothing spoken',
  AB + ['--pause-at', '20000'], [r'PARKED on the audio-busy word \(0xba3c\)', r'chunks started: 5, ended: 4', r'spoken: \(nothing\)', r'audio busy: now 0xba3c', r'port-3 rules: OK'])
S('HOLD', 'without the struct pointer (72b = 0) no hold is taken (the stock rule is untouched): same as probe209, the pause ends the loop with 0x21',
  ['--audio-busy', '--pause-at', '20000'], [r'chunks started: 2, ended: 2', r'spoken: 0x21@', r'audio busy: now 0x0000; SetAudioBusy calls: 0@'], horizon=60000)
S('HOLD', 'the DSP unloads at 20000 ms: the loop ends with 0x21 and OUR hold is released first (busy back to 0)',
  AB + ['--unload-at', '20000'], [r'spoken: 0x21@', r'audio busy: now 0x0000', r'port-3 rules: OK'], horizon=60000)
S('HOLD', 'STOP at 20000 ms: the chunk plays out, the restore pokes follow, busy is cleared at the chunk end, no pending message, nothing spoken',
  AB + ['--press', '20000:4004'], [r'chunks started: 2, ended: 2', r'spoken: \(nothing\)', r'audio busy: now 0x0000', r'cave messages still pending: 0', r'port-3 rules: OK'], horizon=60000)
S('HOLD', 'the hold does not break the nominal loop: 5 chunks, 8 ms seams, no 0x1072 while busy (R1)',
  AB, [r'chunks started: 5, ended: 4', r'silence between chunks \(ms, audible end -> next start\): 8, 8, 8, 8', r'port-3 rules: OK', r'!violat'], horizon=60000)

# ------------------------------------------------------------------ frame rules (V11 D1)
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
    words = os.path.join(ROOT, 'build', 'hook', 'probe210_words.json')
    if '--words' in argv:
        words = argv[argv.index('--words') + 1]
    fails = ran = 0
    for i, (g, name, args, regex) in enumerate(SCEN):
        bad, out = run_scen(words, args, regex)
        ran += 1
        print('%s %2d %-7s %s' % ('FAIL' if bad else 'ok  ', i, g, name), flush=True)
        for b in bad:
            print('      -> %s' % b)
        if bad:
            fails += 1
            print('\n'.join('      | ' + ln[:200] for ln in out.splitlines()[-16:]), flush=True)
    for j, (g, name, kind) in enumerate(FRAME):
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
