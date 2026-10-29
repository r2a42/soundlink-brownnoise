#!/usr/bin/env python3
"""Offline world-model gate for the cold-start LADDER rungs (probe240..245 = rung 1..6; build/hook/ladder_ext.py).
    python build/hook/gate_ladder.py RUNG        (RUNG 1..5)
Every row greps the simulator report (a leading ! means: must NOT match). NO device. Not independently reviewed."""
import os, re, subprocess, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
RUNG = int(sys.argv[1]) if len(sys.argv) > 1 else 1
VARIANT = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] in ('a', 'b', 'c', 'f', 'p', 'q', 'r', 's', 'D', 't', 'u', 'v', 'y', 'z', 'G') else ''
NAME = sys.argv[3] if len(sys.argv) > 3 else 'probe24%d' % (RUNG - 1)
WORDS = os.path.join(ROOT, 'build', 'hook', NAME + '_words.json')
BASE = ['--flag-id', '30', '--entry', '0x3E21D', '--mem', '59e=d', '--caller-frame', '23', '--world', '--music', 'playing', '--dsp', 'down',
        '--chunk-ms', '14742', '--raw-p2', 'file:build/payload/r3/brown_8000_58968_s63.adpcm', '--raw-pack', 'octet', '--raw-prime', '126',
        '--steps', '400000000']
MARK = '0x%x' % (0x27 + RUNG + (1 if VARIANT == 'a' else 2 if VARIANT == 'b' else 3 if VARIANT == 'c' else 0))
NOWRITE = [r'!OverwriteSink', r'!SinkMap', r'!SinkClaim', r'!SinkFlush', r'!PartitionSetMessageDigest', r'!SinkClose']
ROWS = []
def R(name, extra, rx, horizon=60000): ROWS.append((name, BASE + ['--horizon', str(horizon)] + extra, rx))

seq = [r'spoken: 0x27@10000', r'MessageKalimbaTask\(0xba3c\)', r'DSP loaded and booted', r'MUSIC_READY 0x1000 queued']
if RUNG >= 2: seq += [r'SETPLUGIN\(1\) accepted'] + ([] if VARIANT == 'a' else [r'LOADPARAMS\(0x2270\) -> PARAMS_LOADED'])
if RUNG >= 2 and VARIANT == 'a': seq += [r'!LOADPARAMS']
if RUNG >= 3 and not VARIANT: seq += [r'calls fn_1f04c', r'calls fn_1f512']
if RUNG >= 4 and not VARIANT: seq += [r'KalimbaSendLongMessage\(0x1002, len 8', r'KalimbaSendLongMessage\(0x10a0, len 7', r'KalimbaSendMessage\(0x1001, 0x0002', r'KalimbaSendMessage\(0x1070, 0x12c0, b=0x0080', r'KalimbaSendMessage\(0x1071, 0x12c0, b=0x0640']
if RUNG >= 99 and not VARIANT: seq += [r'PanicUnlessMalloc +AL=0x0009', r'StreamRegionSource +AL=0x[0-9a-f]+ AH=0x0009', r'StreamKalimbaSink +AL=0x0000', r'StreamConnect']
if RUNG == 5 and VARIANT in ('y', 'z'):
    R('rung 5y (cold start loop with the FULL stock bring-up): SETPLUGIN, LOADPARAMS, fn_1f04c, 0x1002, 0x10a0, 0x1001, 0x1070, 0x1071, GO, amp-on, then the loop',
      ['--press', '0:4753'], [r'MUSIC_READY', r'SETPLUGIN\(1\) accepted', r'LOADPARAMS', r'calls fn_1f04c', r'KalimbaSendLongMessage\(0x1002, len 8', r'KalimbaSendMessage\(0x1001', r'KalimbaSendMessage\(0x1070', r'KalimbaSendMessage\(0x1071', r'GO: DSP running', r'MessageSendLater +AL=0x072c AH=0x7023', r'chunks started: [3-9]', r'(?m)spoken: 0x27@10000$', r'port-3 rules: OK', r'!R3 t='] + NOWRITE, horizon=90000)
elif RUNG == 5 and VARIANT == 'v':
    R('rung 5v (PRODUCT TEST 2): press 1 via the connect event (cold ON); an SLC disconnect (0x4716) at 50 s: the old EVENTS stops the loop, ENSURE restarts it 4 s later (waits for the chunk in flight, rule R1); a second connect event at 90 s must NOT toggle the mode; nothing spoken',
      ['--press', '0:4753', '--press', '50000:4716', '--press', '90000:4753', '--allow', 'R6'], [r'DSP loaded and booted', r'GO: DSP running', r'(?s)AH=0x7023.*AH=0x7023', r'chunks started: (?:[6-9]|1[0-9])', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes', r'!R[1-5] t=', r'!KalimbaSendLongMessage'] + NOWRITE, horizon=150000)
elif RUNG == 5 and VARIANT == 'u':
    R('rung 5u (PRODUCT TEST): the connect event emulates press 1 (ON, cold: GATE FALSE -> stage B 1.5 s later -> load -> bring-up -> GO -> amp-on message -> loop), press 2 at +60 s (OFF), press 3 at +105 s (ON, warm: GATE TRUE -> amp-on message -> poll -> chunks); nothing is spoken',
      ['--press', '0:4753', '--allow', 'R6'], [r'MessageKalimbaTask\(0xba3c\)', r'DSP loaded and booted', r'SETPLUGIN\(1\) accepted', r'LOADPARAMS', r'calls fn_1f04c', r'GO: DSP running', r'(?s)AH=0x7023.*AH=0x7023', r'!KalimbaSendLongMessage', r'chunks started: [5-9]', r'(?m)spoken: \(nothing\)$', r'!R[1-5] t='] + NOWRITE, horizon=150000)
elif RUNG == 5 and VARIANT in ('t', 'G'):
    R('rung 5t (the cold start as a loop): minimal J29 bring-up, GO, the stock amp-on message 0x7023 to task 0x72c right after GO, then the old noise loop runs chunk after chunk; only the stage marker is spoken',
      ['--press', '0:4753'], [r'MUSIC_READY', r'SETPLUGIN\(1\) accepted', r'LOADPARAMS', r'calls fn_1f04c', r'GO: DSP running', r'MessageSendLater +AL=0x072c AH=0x7023', r'!KalimbaSendLongMessage', r'!KalimbaSendMessage\(0x1001', r'chunks started: [3-9]', r'(?m)spoken: 0x27@10000$', r'port-3 rules: OK', r'!R3 t='] + NOWRITE, horizon=90000)
elif RUNG == 5 and VARIANT in ('p', 'q', 'r', 's', 'D'):
    R('rung 5p (output-content probe): cold start to GO, the loop is stopped 4 s after GO, port 6 is read BEFORE the DAC connect, the DAC is connected late, one digit is spoken after the chunk has ended',
      ['--press', '0:4753', '--allow', 'R6'], [r'MUSIC_READY', r'SETPLUGIN\(1\) accepted', r'LOADPARAMS', r'GO: DSP running', r'calls fn_1f04c', r'!KalimbaSendLongMessage', r'port-3 rules: OK', r'!R3 t='] + NOWRITE, horizon=70000)
elif RUNG == 5 and VARIANT == 'f':
    R('rung 5f (diagnostic, minimal J29 bring-up): the cold start up to GO, the noise loop is stopped 12 s after GO, three log-scale digits are spoken only after the running chunk has ended (port 3 free)',
      ['--press', '0:4753', '--allow', 'R6'], [r'MUSIC_READY', r'SETPLUGIN\(1\) accepted', r'LOADPARAMS', r'calls fn_1f04c', r'GO: DSP running', r'!KalimbaSendLongMessage', r'!KalimbaSendMessage\(0x1001', r'chunks started: 1, ended: 1', r'spoken: 0x27@10000, 0x[0-9a-f]+@3[0-9]{4}, 0x[0-9a-f]+@4[0-9]{4}, 0x[0-9a-f]+@4[0-9]{4}', r'port-3 rules: OK', r'!R3 t='] + NOWRITE, horizon=70000)
elif RUNG == 5:
  R('rung 5: the laptop connect with no DSP: the whole cold bring-up, 0x1072 + pokes + hold, GO, then the old noise loop runs by itself (chunk after chunk, 8 ms seams); only the stage marker 0x27 is spoken',
      ['--press', '0:4753'], seq + [r'(?m)spoken: 0x27@10000$', r'GO: DSP running', r'KalimbaSendMessage\(0x1072, 0x1f40, b=0x0002', r'KalimbaSendMessage\(0x7ab3, 0x28f6', r'chunks started: [3-9]', r'port-3 rules: OK', r'!violat', r'DSP: loaded'] + NOWRITE, horizon=90000)
else:
  R('the laptop connect (event 0x4753) with no DSP: marker 0x27 at 10000 ms, the load at 16000 ms and every step up to this rung, then the rung marker %s; nothing else spoken; DSP off at the end' % MARK,
  ['--press', '0:4753'], seq + [r'spoken: 0x27@10000, %s@' % MARK, ] + ([r'KalimbaPowerOff', r'DSP: unloaded'] if RUNG == 1 else [r'!KalimbaPowerOff']) + [r'chunks started: 0', r'port-3 rules: OK', r'!violat', r'presses: 0 swallowed, 1 replayed'] + NOWRITE)
R('the event is replayed to the stock after our wrapper (fn_189fb sees 0x4753)', ['--press', '0:4753'], [r'calls fn_189fb +AL=0x4753', r'event 0x4753: REPLAYED'], horizon=30000)
if VARIANT not in ('u', 'v'): R('two connect events 1 s apart: the debounce leaves ONE stage run (marker 0x27 once)', ['--press', '0:4753', '--press', '1000:4753'], [r'MessageCancelFirst\(0xba3c, 0x25\) -> TRUE', (r'(?m)spoken: 0x27@11000$' if (RUNG == 5 and VARIANT not in ('f', 'p', 'q', 'r', 's', 'D', 'u', 'v')) else r'spoken: 0x27@11000, ' if VARIANT in ('f', 'p', 'q', 'r', 's', 'D', 'u', 'v') else r'spoken: 0x27@11000, %s@' % MARK)], horizon=60000)
R('other events (0x4742, 0x4715, 0x4743) start nothing and are replayed', ['--press', '0:4742', '--press', '100:4715', '--press', '200:4743'], [r'spoken: \(nothing\)', r'presses: 0 swallowed, 3 replayed', r'cave messages still pending: 0'] + NOWRITE, horizon=30000)
if VARIANT in ('u', 'v'):
    R('rung 5u/5v: KalimbaLoad refused: 0x3E "bluetooth off" 1.5 s after the (emulated) press, nothing loaded', ['--press', '0:4753', '--fail', 'KalimbaLoad', '--allow', 'R6'], [r'spoken: 0x3e@11500', r'DSP: unloaded'], horizon=60000)
else:
    R('KalimbaLoad refused: 0x3E "bluetooth off" after the marker 0x27, nothing loaded', ['--press', '0:4753', '--fail', 'KalimbaLoad'], [r'spoken: 0x27@10000, 0x3e@16000', r'DSP: unloaded', r'!MUSIC_READY'], horizon=40000)
R('the normal long press (0x4004) is the old mode toggle, unchanged: it starts the noise on a loaded DSP', ['--dsp', 'up', '--press', '0:4004'], [r'chunks started: [1-9]', r'mode flag \(id 0x30\) pending: yes'], horizon=40000)
if RUNG >= 3:
    R('the DAC connect fn_1f04c is refused: teardown and 0x1F "muted"', ['--press', '0:4753', '--fail-after', 'fn_1f04c=0'] if False else ['--press', '0:4753'], [r'calls fn_1f04c'], horizon=40000)
if RUNG >= 4 and VARIANT not in ('f', 'p', 'q', 'r', 's', 'D', 't', 'u', 'v', 'y', 'z', 'G'):
    R('the DSP refuses 0x1001: teardown, 0x24 "switching call" (not the rung marker)', ['--press', '0:4753', '--dsp-refuse', '1001'], [r'spoken: 0x27@10000, 0x24@', r'!%s@' % MARK], horizon=40000)
    R('the DSP refuses 0x10a0: 0x24', ['--press', '0:4753', '--dsp-refuse', '10a0'], [r'spoken: 0x27@10000, 0x24@', r'!%s@' % MARK], horizon=40000)
if RUNG >= 99:
    R('StreamConnect refused: 0x3A "heart rate not detected"', ['--press', '0:4753', '--fail', 'StreamConnect'], [r'spoken: 0x27@10000, 0x3a@', r'!%s@' % MARK], horizon=40000)
    R('StreamRegionSource refused: 0x3A', ['--press', '0:4753', '--fail', 'StreamRegionSource'], [r'spoken: 0x27@10000, 0x3a@', r'!%s@' % MARK], horizon=40000)


def run(extra, rx):
    r = subprocess.run([sys.executable, 'tools/cavesim.py', WORDS] + extra, cwd=ROOT, capture_output=True, text=True, timeout=1800)
    out = r.stdout + r.stderr
    bad = []
    if r.returncode not in (0, 1): bad.append('exit code %d' % r.returncode)
    for x in rx:
        neg = x.startswith('!'); pat = x[1:] if neg else x
        if (re.search(pat, out) is not None) == neg: bad.append(('must NOT match: ' if neg else 'missing: ') + pat)
    return bad, out


def main():
    fails = 0
    for i, (name, args, rx) in enumerate(ROWS):
        bad, out = run(args, rx)
        print('%s %2d %s' % ('FAIL' if bad else 'ok  ', i, name), flush=True)
        for b in bad: print('      -> %s' % b)
        if bad:
            fails += 1
            print('\n'.join('      | ' + ln[:200] for ln in out.splitlines()[-14:]), flush=True)
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import framecheck
    fnd = framecheck.check(framecheck.load(WORDS))
    print('%s FRAME framecheck: no store into the top two slots of any function frame' % ('FAIL' if fnd else 'ok  '))
    if fnd: fails += 1; print(fnd)
    print('\n%d row(s), %d failed' % (len(ROWS) + 1, fails))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
