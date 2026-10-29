#!/usr/bin/env python3
"""Offline STOCK-WORLD gate (BF, 2026-10-19): what a stock TTS prompt and a stock tone do to the cave's DAC link, on the images probe285 / 295 / 296 / 298.
    python build/hook/gate_stock_world.py [probe285 probe295 probe296 probe298 ...]     (default: those four)
Uses the opt-in cavesim stock-world events --tone-at / --tts-at (tools/cavesim_world.py, docs/deep/material-2026-10-19/BF-stock-world-model.md).
The expectations depend on the features the image's wrapper declares (CLEARDAC = F2, EVGUARD = probe298). NO device. The model is a reading of the lifts
(AQ), not a measurement: a REBOOT here means "the lifted code path PanicNulls", see BF section 4 for the limits."""
import os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
NAMES = sys.argv[1:] or ['probe285', 'probe295', 'probe296', 'probe298']
BASE = ['--flag-id', '30', '--entry', '0x3E21D', '--mem', '59e=d', '--caller-frame', '23', '--world', '--music', 'playing', '--dsp', 'down',
        '--chunk-ms', os.environ.get('GATE_CHUNK_MS', '14742'), '--raw-p2', 'file:' + os.environ.get('GATE_P2', 'build/payload/r3/brown_8000_58968_s63.adpcm'), '--raw-pack', 'octet', '--raw-prime', '126',
        '--steps', '900000000', '--allow', 'R6', '--dac-guard', '--ksink-after-unload', 'zero', '--audio-busy', '--show', '6d1:1']
BASE = BASE + (['--poll-floor', os.environ['GATE_POLL_FLOOR']] if os.environ.get('GATE_POLL_FLOOR') else [])   # probe309: the busy re-poll is 10 ms; rule R5's floor (default 50) is lowered for THIS image only and the value is stated in BY-smooth-loop.md
# BH (probe299): the stack-true chain model (cavesim --chain-model) replaces the counterfactual pair `--ksink-after-unload zero`; selected per image by EVGCHAIN in its wrapper. Old images keep BASE byte for byte.
BASE_CHAIN = [a for a in BASE]
_i = BASE_CHAIN.index('--ksink-after-unload'); BASE_CHAIN[_i:_i + 2] = ['--chain-model']
TFS0, TFS1 = r'TransformFromSource -> 0 \(--chain-model: the DAC link chain is gone\)', r'TransformFromSource -> handle \(--chain-model: the DAC link chain is alive\)'
STOP = ['--press', '0:4004', '--press', '30000:4004']           # cold ON, then the stop press at 30 s (the cave arms the hold release for 46 s)
REBOOT = r'stock world: outcome REBOOT at %d ms'
NOREB = r'stock world: outcome no reboot'
F_SET, F_CLR = r'data @0x06D1\.\.\+1: 8000', r'data @0x06D1\.\.\+1: 0000'


def scenarios(wrap):
    ev = 'EVGUARD = True' in wrap
    ch = 'EVGCHAIN = True' in wrap
    base = BASE_CHAIN if ch else BASE
    if 'STALL = True' in wrap: base = base + ['--events', '60000']      # probe334: the stall instrument's 8-ms tick chain (about 110 ticks per chunk) needs a larger model event budget; no rule changes
    f2 = 'CLEARDAC = True' in wrap
    S = []
    def add(name, extra, rx, horizon): S.append((name, base + ['--horizon', str(horizon)] + extra, rx))
    # R1: the finding-4 case. A stock TTS after the stop (parked behind the hold, served at the release), a volume press at 55 s, a stock tone at 60 s.
    for tts, label in (('35000', 'TTS parked behind the hold at +5 s, served at the release (46 s)'), ('46500', 'TTS requested just after the release (+16.5 s)')):
        add('R1 stop press, %s, volume press 0x400D at +25 s, stock tone at +30 s: %s' % (label, 'probe298 does NOT reboot (EVGUARD cleared the stale bit at the press)' if ev else 'REBOOT (bit 15 stale)'),
            STOP + ['--tts-at', tts, '--press', '55000:400D', '--tone-at', '60000'],
            ([r'PARKED' if tts == '35000' else r'STOCK TTS served', NOREB, r'STOCK TONE served \(AQ 4\.4\): @0x6d1 bit 15 clear -> connects', r'STOCK TONE ends', F_CLR, r'!REBOOT'] + ([TFS0] if ch else []) if ev else [r'PARKED' if tts == '35000' else r'STOCK TTS served', REBOOT % 60000, r'!stock world: outcome no reboot']), 90000)
    # R1c: the same without any event between the TTS and the tone (a timer-driven tone): EVGUARD has nothing to hook onto (BC 4, AU 7.2)
    add('R1c stop press, TTS served at the release, a stock tone at +30 s with NO event in between (timer-driven tone): REBOOT on every image, EVGUARD included',
        STOP + ['--tts-at', '35000', '--tone-at', '60000'], [REBOOT % 60000, F_SET], 90000)
    # R2: a tone parked behind the hold (branch B without F1, or another stock tone): the bit is VALID (DSP resident), so nobody covers it
    add('R2 a stock tone requested at +10 s (parked behind the hold), released at 46 s while our DSP and DAC link are still up: REBOOT at the release on every image',
        STOP + ['--tone-at', '40000'], [REBOOT % 46000, r'!STOCK TONE served[^\n]*connects'], 60000)
    # R3: a TTS alone never reboots
    add('R3 stop press, one TTS served at the release, nothing else: no reboot, DSP gone, the flag is left stale',
        STOP + ['--tts-at', '35000'], [NOREB, F_SET, r'DSP: unloaded'], 70000)
    # R4: F2, the start press after a TTS
    if f2:
        add('R4 (F2) stop press, TTS at +16.5 s, START press at 100 s: the noise starts again (the stale bit is cleared before the DAC connect)',
            STOP + ['--tts-at', '46500', '--press', '100000:4004'],
            [NOREB, r'(?s)GO: DSP running.*GO: DSP running', r'(?s)calls fn_1f04c.*calls fn_1f04c', r'mode flag \(id 0x30\) pending: yes', r'chunks started: (?:[5-9]|[1-9][0-9])'], 160000)
    else:
        add('R4 (no F2) stop press, TTS at +16.5 s, START press at 100 s: the DAC connect is refused silently by the stale bit (one GO only, zombie mode)',
            STOP + ['--tts-at', '46500', '--press', '100000:4004'],
            [NOREB, r'(?s)calls fn_1f04c.*calls fn_1f04c', r'(?s)\A(?!.*GO: DSP running.*GO: DSP running)', r'mode flag \(id 0x30\) pending: yes'], 160000)
    if ev:
        # R5: probe298 only: after the repair the stock tone plays and ends cleanly, and a START press afterwards still works
        add('R5 (probe298) stop, TTS, volume press, tone (connects, ends, bit cleared), START press at 100 s: the noise starts again',
            STOP + ['--tts-at', '46500', '--press', '55000:400D', '--tone-at', '60000', '--press', '100000:4004'],
            [NOREB, r'STOCK TONE ends', r'(?s)GO: DSP running.*GO: DSP running', r'mode flag \(id 0x30\) pending: yes', r'chunks started: (?:[5-9]|[1-9][0-9])'], 160000)
    # R6: control, a tone with our DSP resident and no TTS: the bit is valid, every image reboots (EVGUARD correctly does not clear it)
    add('R6 control: stop press, NO TTS, a volume press then a stock tone at +30 s (E2: DSP resident, bit valid): REBOOT on every image (EVGUARD refuses to lie)',
        STOP + ['--press', '55000:400D', '--tone-at', '60000'], [REBOOT % 60000, F_SET] + ([TFS1] if ch else []), 90000)
    if ch:
        # R7 (probe299): the chain is ALIVE and the flag valid after a TTS: a stock DSP/chain was rebuilt (--chain-at 50000:1) before the volume press: NOT cleared, the tone then reboots (honest: the flag is valid, the model has no way to refuse a connect over a live chain)
        add('R7 (probe299) stop press, TTS, then a stock chain comes alive (--chain-at 50000:1), volume press, tone: the flag is VALID, EVGUARD does not clear it (REBOOT as in R6)',
            STOP + ['--tts-at', '35000', '--chain-at', '50000:1', '--press', '55000:400D', '--tone-at', '60000'], [REBOOT % 60000, F_SET, TFS1], 90000)
        # R8 (probe299): TTS, volume press, tone, then a SECOND TTS and a second volume press and tone: the repair repeats
        add('R8 (probe299) the repair repeats: TTS, press, tone (ok), second TTS, press, tone (ok): no reboot',
            STOP + ['--tts-at', '35000', '--press', '55000:400D', '--tone-at', '60000', '--tts-at', '70000', '--press', '80000:400D', '--tone-at', '85000'],
            [NOREB, r'STOCK TONE ends', F_CLR, r'!REBOOT'], 120000)
    return S


def run_one(job):
    name, label, args, rx = job
    r = subprocess.run([sys.executable, 'tools/cavesim.py', os.path.join(ROOT, 'build', 'hook', name + '_words.json')] + args, cwd=ROOT, capture_output=True, text=True, timeout=3600)
    out = r.stdout + r.stderr
    bad = []
    for p in rx:
        neg = p.startswith('!')
        pat = p[1:] if neg else p
        if (re.search(pat, out) is not None) == neg: bad.append(('present: ' if neg else 'missing: ') + pat)
    if 'STOPPED' in out: bad.append('STOPPED in the simulator')
    outcome = re.search(r'stock world: outcome ([^;]*)', out)
    return name, label, bad, (outcome.group(1) if outcome else '?')


jobs = []
for n in NAMES:
    wrap = ''
    try: wrap = open(os.path.join(ROOT, 'build', 'hook', 'assemble_' + n + '.py'), encoding='utf-8').read()
    except OSError: pass
    for label, args, rx in scenarios(wrap): jobs.append((n, label, args, rx))
fails = 0
with ThreadPoolExecutor(max_workers=int(os.environ.get('GATE_JOBS', '4'))) as ex:
    for name, label, bad, outcome in ex.map(run_one, jobs):
        print(('FAIL ' if bad else 'ok   ') + '[%s] %s   => %s' % (name, label, outcome))
        for b in bad: print('      -> ' + b)
        fails += bool(bad)
print('%d scenario(s), %d failed' % (len(jobs), fails))
sys.exit(1 if fails else 0)
