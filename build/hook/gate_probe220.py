#!/usr/bin/env python3
"""Offline world-model gate for probe220 (probe215 plus the audio-busy hold of probe210: the noise survives the end of the laptop stream; a TEST-ONLY stop on the event 0x4753) -- 2026-10-16. NOT independently reviewed.
NO device, no flash tool: pure emulation (tools/cavesim.py, the clocked world). The raw source is fed the real payload (--raw-p2 file:build/payload/r3/brown_8000_58968_s63.adpcm,
whose sha256 is pinned below) and the chunk is 2 x 58,968 / 8,000 = 14,742 ms. Every row greps the simulator's report with regular expressions (a leading ! means: must NOT match).
    python build/hook/assemble_probe220.py                     # first (writes probe220_words.json)
    python build/hook/gate_probe220.py [--list] [--words PATH]
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


# ------------------------------------------------------------------ probe220: the hands-free auto-start on 0x4758 (a music stream started)
AUTO_NOTE = [r'spoken: \(nothing\)', r'port-3 rules: OK', r'!violat'] + NOWRITE
S('AUTO', 'event 0x4758 at 0 ms: the debounced start at 4000 ms, the first chunk at 5000 ms, then chunk after chunk with 8 ms seams (4 chunks in 60 s), nothing spoken, the event is replayed',
  ['--press', '0:4758'], [r'#1 start +5000 ms.*14742 ms', r'#2 start +1975\d ms', r'#3 start +3450\d ms', r'chunks started: 4, ended: 3',
                          r'silence between chunks \(ms, audible end -> next start\): 8, 8, 8', r'presses: 0 swallowed, 1 replayed'] + AUTO_NOTE)
S('AUTO', 'two events 0x4758 at 0 and 1500 ms: ONE start (debounced), the first chunk at 6500 ms',
  ['--press', '0:4758', '--press', '1500:4758'], [r'#1 start +6500 ms', r'chunks started: 4, ended: 3', r'presses: 0 swallowed, 2 replayed'] + AUTO_NOTE)
S('AUTO', 'a second 0x4758 at 30000 ms while the loop runs: the poll is put back, no second chain, seams stay 8 ms (the only R6 line is the pending auto-start message itself)',
  ['--press', '0:4758', '--press', '30000:4758'], [r'chunks started: 6, ended: 5', r'silence between chunks \(ms, audible end -> next start\): 8, 8, 8, 8, 8',
                                                      r'R6 t=30000 ms: a cave message is already pending \(0x12\)', r'spoken: \(nothing\)', r'!violat'] + NOWRITE, horizon=80000)
S('AUTO', 'other connect-time events (0x4742, 0x4753) and 0x4003 start nothing and are replayed',
  ['--press', '0:4742', '--press', '50:4753', '--press', '100:4003'], [r'chunks started: 0', r'spoken: \(nothing\)', r'presses: 0 swallowed, 3 replayed', r'cave messages still pending: 0'] + NOWRITE, horizon=30000)
S('AUTO', 'the DSP is gone when the auto-start fires (unloaded at 100 ms): the first tick says 0x21 "call ended", no chunk, nothing re-armed',
  ['--press', '0:4758', '--unload-at', '100'], [r'spoken: 0x21@5000', r'chunks started: 0', NOLEAK], horizon=30000)
S('AUTO', 'music PAUSED at 20000 ms (the DSP unloads), resumed at 40000 ms with a new 0x4758 at 40500 ms: the loop ends with 0x21 at the next seam (34500) and restarts by itself (chunk 3 at 45500)',
  ['--press', '0:4758', '--unload-at', '20000', '--music-resume-at', '40000', '--press', '40500:4758'], [r'spoken: 0x21@34500', r'#3 start +45500 ms', r'port-3 rules: OK', r'!violat'] + NOWRITE, horizon=75000)
S('AUTO', 'a Bluetooth teardown at 20000 ms: the running chunk ends cleanly, no further chunk, no violation',
  ['--press', '0:4758', '--bt-teardown-at', '20000'], [r'port-3 rules: OK', r'!VIOLATION'], horizon=60000)
S('AUTO', 'a manual STOP (long press) at 25000 ms during the auto-started loop: that chunk plays out, then silence, nothing pending',
  ['--press', '0:4758', '--press', '25000:4004'], [r'chunks started: 2, ended: 2', r'spoken: \(nothing\)', r'cave messages still pending: 0', r'presses: 1 swallowed, 1 replayed'] + NOWRITE, horizon=80000)

# ------------------------------------------------------------------ probe220: the hold (the stream stops, the noise goes on) and the test-only stop
AB = ['--audio-busy', '--mem', '72b=1']
S('HOLD', 'the stream stops (PAUSE) at 20000 ms during an auto-started loop: our hold parks the plugin disconnect, the loop keeps running (5 chunks in 70 s), nothing spoken, the disconnect stays parked',
  AB + ['--press', '0:4758', '--pause-at', '20000'], [r'PARKED on the audio-busy word \(0xba3c\)', r'chunks started: 5, ended: 4', r'spoken: \(nothing\)', r'a disconnect is still PARKED', r'port-3 rules: OK'] + NOWRITE, horizon=70000)
S('HOLD', 'the test stop (event 0x4753) at 30000 ms while the loop runs: that chunk plays out (to 34500), the stock clears the busy word at the chunk end, nothing pending, nothing spoken',
  AB + ['--press', '0:4758', '--press', '30000:4753'], [r'chunks started: 2, ended: 2', r'SetAudioBusy calls: 47676@5000, 0@3452\d', r'audio busy: now 0x0000', r'spoken: \(nothing\)', r'cave messages still pending: 0', r'port-3 rules: OK'] + NOWRITE, horizon=80000)
S('HOLD', 'pause at 20000 ms THEN the test stop at 40000 ms: the loop ran on, then the parked disconnect is delivered at the chunk end and the DSP unloads, busy zero, nothing pending',
  AB + ['--press', '0:4758', '--pause-at', '20000', '--press', '40000:4753'], [r'the parked plugin disconnect is delivered', r'DSP UNLOADED \(parked disconnect\)', r'audio busy: now 0x0000', r'cave messages still pending: 0', r'spoken: \(nothing\)', r'port-3 rules: OK'] + NOWRITE, horizon=90000)
S('HOLD', 'the test stop event 0x4753 with NO loop running (the first connect): nothing happens, nothing armed, nothing pending',
  AB + ['--press', '0:4753'], [r'chunks started: 0', r'cave messages still pending: 0', r'spoken: \(nothing\)', r'SetAudioBusy calls: none'] + NOWRITE, horizon=40000)
S('HOLD', 'the DSP is gone when the auto-start ticks (unloaded at 100 ms) with the hold model: 0x21, our hold is released first, nothing held',
  AB + ['--press', '0:4758', '--unload-at', '100'], [r'spoken: 0x21@5000', r'audio busy: now 0x0000', r'chunks started: 0'] + NOWRITE, horizon=30000)

# ------------------------------------------------------------------ the manual rows inherited from probe209 (the engine is unchanged)
# ------------------------------------------------------------------ NOMINAL
M('NOMINAL', 'a press: the delayed start at 1000 ms, then chunk after chunk 14,742 ms long with only a few ms between them (5 chunks in 60 s), nothing spoken',
  [], [r'#1 start +1000 ms.*14742 ms', r'#2 start +1575\d ms', r'#3 start +3050\d ms', r'#4 start +4525\d ms', r'chunks started: 5, ended: 4', r'spoken: \(nothing\)',
       r'silence between chunks \(ms, audible end -> next start\): 8, 8, 8, 8', r'port-3 rules: OK', r'raw partition sources \(trap 0xD3\): 5 call', r'!violat'] + NOWRITE)
M('NOMINAL', 'every rebuild sends 0x1072 (8000 Hz, b = 2) and the level poke: the chunks are all 8000 Hz, quiet level b=0x2',
  [], [r'8000 Hz  b=0x2 quiet'] + [r'#%d start' % i for i in range(1, 5)])
M('NOMINAL', 'a longer run: 90 s = 7 chunks, still no gap, no spoken id',
  [], chunks(7, 6) + [r'spoken: \(nothing\)', r'port-3 rules: OK'], horizon=100000)
M('NOMINAL', 'the lever: no store reaches the caller\'s saved return address', [], [r'caller-frame guard: stores to 0x0915, 0x0916 stop the run', r'!STOPPED'])
M('NOMINAL', 'the raw source is opened through the synthesised 0xD3 stub once per chunk', [], [r'synthesised-stub calls \{211: 5\}', r'SYNTHESISED TRAP STUB at 0x[0-9A-Fa-f]+: trap 0xD3'])

# ------------------------------------------------------------------ STOP / START
M('STOP', 'a second press at 20000 ms (chunk 2 playing): STOP: that chunk plays out (to 30,492 ms), then silence, nothing re-armed, nothing spoken',
  ['--press', '20000:4004'], [r'chunks started: 2, ended: 2', r'spoken: \(nothing\)', r'cave messages still pending: 0', r'presses: 2 swallowed'] + NOWRITE, horizon=80000)
M('STOP', 'STOP at 5000 ms (chunk 1 playing) then START at 25000 ms: the loop restarts and runs again (chunks 1, 2 and then 3 more)',
  ['--press', '5000:4004', '--press', '25000:4004'], [r'chunks started: 6, ended: 5', r'#1 start +1000 ms', r'#2 start +26000 ms', r'spoken: \(nothing\)', r'presses: 3 swallowed', r'pending: 1'], horizon=95000)
M('STOP', 'a press during the 1000 ms delay (before the first chunk): STOP, no chunk ever starts',
  ['--press', '500:4004'], [r'chunks started: 0, ended: 0', r'spoken: \(nothing\)', r'!raw partition sources \(trap 0xD3\): [1-9]'], horizon=30000)

# ------------------------------------------------------------------ the pre-start check and the refusals (each speaks one id, starts nothing, leaves no source open)
M('CHECK', 'the first source byte is wrong (a stale or garbage stream): the check refuses, 0x3B "adjust airbuds", NO chunk, the source is closed',
  ['--raw-p2', 'file:' + V0], [r'spoken: 0x3b@1000', r'chunks started: 0', NOLEAK], horizon=20000)
M('CHECK', 'the fourth source byte is wrong: the same refusal (all four bytes are checked)',
  ['--raw-p2', 'file:' + V3], [r'spoken: 0x3b@1000', r'chunks started: 0', NOLEAK], horizon=20000)
M('CHECK', 'the raw source is stale from byte 1 on (a wrong byte after the checked four is NOT detected by design): the loop runs',
  ['--raw-p2', 'file:' + V1000], [r'chunks started: [1-9]', r'spoken: \(nothing\)'], horizon=20000)
M('CHECK', 'SourceMap on the raw source returns 0: 0x3B, no chunk, the source is closed',
  ['--raw-map-zero'], [r'spoken: 0x3b@1000', r'chunks started: 0', NOLEAK], horizon=20000)
M('REFUSE', '0xD3 returns 0 (p2 erased or not readable: no raw source): 0x24 "switching call", no chunk, nothing to close',
  ['--raw-p2', 'none'], [r'spoken: 0x24@1000', r'chunks started: 0'], horizon=20000)

# ------------------------------------------------------------------ the DSP going away, limits
M('DSP', 'the DSP is gone BEFORE the first tick (unloaded at 500 ms): the first tick says 0x21 "call ended", no chunk is built',
  ['--unload-at', '500'], [r'spoken: 0x21@1000', r'chunks started: 0', NOLEAK], horizon=20000)
M('DSP', 'the DSP unloads at 20000 ms (pause the music mid-run): the loop ends at the next seam with 0x21; port 3 is free when it speaks',
  ['--unload-at', '20000'], [r'spoken: 0x21@', r'port-3 rules: OK'], horizon=60000)
M('DSP', 'a Bluetooth long press tears everything down at 20000 ms: the running chunk ends cleanly, no further chunk, no violation',
  ['--bt-teardown-at', '20000'], [r'port-3 rules: OK', r'!VIOLATION'], horizon=60000)

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
    words = os.path.join(ROOT, 'build', 'hook', 'probe220_words.json')
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
