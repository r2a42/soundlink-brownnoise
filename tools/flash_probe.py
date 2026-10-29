#!/usr/bin/env python3
"""flash_probe: docs/FLASH-PROTOCOL.md steps 3 and 4 as ONE foreground process.

Why (owner, 2026-10-08): the assistant's turns can be interrupted between tool calls. A
flash run as separate commands could then stop half-way (in DFU mode, or flashed but with
FLASHED not updated and no readback) with nobody reading the output. This script makes the
sequence a single call that runs every gate itself and STOPS at the first unexpected line.

It does nothing the protocol does not already require, in the same order:
  0. preconditions: image + words + assembler exist, tools/preflight.py passes, the device
     lists as 05a7:40fe (normal mode). Refuses to start from DFU mode.
  1. enter-dfu; expect "may take a few seconds". Poll `list` by ELAPSED time (60 s) for 4022.
  2. download --force IMAGE (timeout 900 s); expect "Waiting ... for firmware to manifest".
  3. leave-dfu -f; STOP if the output contains errXXX.
  4. poll `list` (60 s) for 40fe; `info -f` must show "Main 3.0.3.6546".
  5. write build/hook/FLASHED NOW (verified=PENDING), before anything else.
  6. readback: tools/csr/dfu_upload.py (timeout 900 s), then the protocol's marker-aligned
     comparison: require 0 of 975,168 filesystem bytes differ and 0 words wrong.
  7. poll for 40fe, info -f again, and write verified= into FLASHED, verbatim numbers.

Never: background, /dev/null, fixed sleeps in place of polling, exit-code judgement. Every
command and its full output are printed AND appended to build/hook/<probe>_flash.log.

Usage:  python tools/flash_probe.py probeNNN [--dry-run]
"""
import datetime, hashlib, json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
DFU = os.path.join('tools', 'bose-dfu', 'bose-dfu.exe')
FLASHED = os.path.join('build', 'hook', 'FLASHED')
FS, AREA0 = 975168, 0x6EA30
FW = 'Main 3.0.3.6546'

probe = sys.argv[1]
dry = '--dry-run' in sys.argv
image = 'build/hook/%s_brown.dfu' % probe
words_json = 'build/hook/%s_words.json' % probe
readback = 'build/hook/%s_readback.dfu' % probe
LOG = open('build/hook/%s_flash.log' % probe, 'a', encoding='utf-8')


def say(s):
    line = '[%s] %s' % (datetime.datetime.now().strftime('%H:%M:%S'), s)
    print(line, flush=True)
    LOG.write(line + '\n'); LOG.flush()


def stop(why):
    say('STOP: ' + why)
    say('Device state is whatever the last step above left. See FLASH-PROTOCOL Recovery.')
    sys.exit(2)


def run(args, timeout):
    say('$ ' + ' '.join(args))
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or '') + (e.stderr or '')
        for ln in str(out).splitlines():
            say('  | ' + ln)
        stop('timed out after %d s' % timeout)
    out = (r.stdout or '') + (r.stderr or '')
    for ln in out.splitlines():
        say('  | ' + ln)
    say('  (exit %d -- recorded, not used as the verdict)' % r.returncode)
    return out


def poll(pid, seconds):
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        out = run([DFU, 'list'], 30)
        if '05a7:%s' % pid in out:
            say('  -> %s at t=%.0f s' % (pid, time.monotonic() - t0))
            return True
        t = time.monotonic()
        while time.monotonic() - t < 1.0:     # pace the poll, not a fixed wait for state
            pass
    return False


def flashed_update(fields, note=None):
    lines = open(FLASHED, encoding='utf-8').read().splitlines()
    head = [l for l in lines if l.startswith('#')]
    kv, order = {}, []
    for l in lines:
        if not l.startswith('#') and '=' in l and not l.startswith(' '):
            k, v = l.split('=', 1)
            if k in ('unit', 'status', 'probe', 'image', 'sha256', 'firmware', 'flashed',
                     'cycle', 'verified'):
                kv[k] = v; order.append(k)
    kv.update(fields)
    keys = ['unit', 'status', 'probe', 'image', 'sha256', 'firmware', 'flashed', 'cycle',
            'verified']
    body = head + ['%s=%s' % (k, kv[k]) for k in keys if k in kv]
    if note is None:                      # keep the existing note= block verbatim
        i = next((j for j, l in enumerate(lines) if l.startswith('note=')), None)
        if i is not None:
            body += [''] + lines[i:]
    else:
        body += ['', 'note=' + note]
    open(FLASHED, 'w', encoding='utf-8').write('\n'.join(body) + '\n')
    say('FLASHED updated: ' + ', '.join('%s=%s' % (k, fields[k]) for k in fields))


# ---- 0. preconditions --------------------------------------------------------------
say('==== flash_probe %s %s' % (probe, '(DRY RUN)' if dry else ''))
for p in (image, words_json, 'build/hook/assemble_%s.py' % probe):
    if not os.path.exists(p):
        stop('missing ' + p)
sha = hashlib.sha256(open(image, 'rb').read()).hexdigest()
say('image %s sha256 %s' % (image, sha))
pf = run([sys.executable, 'tools/preflight.py', probe], 600)
if 'all checked probes pass pre-flight' not in pf:
    stop('preflight did not pass')
out = run([DFU, 'list'], 30)
if '05a7:4022' in out:
    stop('device is ALREADY in DFU mode; not starting from an unknown state')
if '05a7:40fe' not in out:
    stop('device not listed in normal mode (40fe)')
prev = open(FLASHED, encoding='utf-8').read()
m = re.search(r'^cycle=(\d+) on unit (\d+)', prev, re.M)
cycle = 'cycle=%d on unit %s' % (int(m.group(1)) + 1, m.group(2)) if m else 'cycle=?'
say('preconditions OK; next %s' % cycle)
if dry:
    say('DRY RUN: stopping before enter-dfu. Nothing was sent to the device.')
    sys.exit(0)

# ---- 1-4. flash --------------------------------------------------------------------
out = run([DFU, 'enter-dfu'], 60)
if 'may take a few seconds' not in out:
    stop('enter-dfu did not print the expected note (do NOT retry enter-dfu blindly)')
if not poll('4022', 60):
    stop('no 4022 within 60 s of elapsed polling')
out = run([DFU, 'download', '--force', image], 900)
if not re.search(r'Waiting [0-9.]+s, as requested by device, for firmware to manifest', out):
    stop('download did not print "Waiting ... for firmware to manifest": write NOT confirmed')
out = run([DFU, 'leave-dfu', '-f'], 120)
if re.search(r'\berr[A-Z]+', out):
    stop('leave-dfu reported an error: ' + re.search(r'\berr[A-Z]+', out).group(0))
if not poll('40fe', 60):
    stop('no 40fe within 60 s after leave-dfu')
out = run([DFU, 'info', '-f'], 60)
if FW not in out:
    stop('info -f did not show "%s"' % FW)
now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M local')
flashed_update({'status': 'PROBE', 'probe': probe, 'image': image, 'sha256': sha,
                'firmware': '3.0.3.6546', 'flashed': now,
                'cycle': cycle.split('=', 1)[1], 'verified': 'PENDING'},
               note='%s, flashed by tools/flash_probe.py (transcript build/hook/%s_flash.log). '
                    'Press plan: the docstring of build/hook/assemble_%s.py. Previous: %s.'
                    % (probe, probe, probe,
                       (lambda m: m.group(1) if m else 'none')(re.search(r'^probe=(\S+)', prev, re.M))))

# ---- 6-7. readback -----------------------------------------------------------------
t0 = time.monotonic()
run([sys.executable, 'tools/csr/dfu_upload.py', readback], 900)
say('readback took %.0f s' % (time.monotonic() - t0))
if not os.path.exists(readback):
    stop('no readback file: NO NEXT FLASH until the readback path works')
rb, fl = open(readback, 'rb').read(), open(image, 'rb').read()
ir, ifl = rb.find(b'fsr_dfu1'), fl.find(b'fsr_dfu1')
if ir < 0 or ifl < 0 or len(rb) < ir + FS:
    stop('readback has no complete fsr_dfu1 area (%d bytes)' % len(rb))
d = sum(1 for i in range(FS) if rb[ir + i] != fl[ifl + i])
W = json.load(open(words_json))
bad = [k for k, v in W.items()
       if (rb[ir + AREA0 + 2 * int(k, 16)] | rb[ir + AREA0 + 2 * int(k, 16) + 1] << 8)
       != (v & 0xffff)]
say('%d of %d filesystem bytes differ' % (d, FS))
say('cave words: %d total, %d wrong' % (len(W), len(bad)))
if not poll('40fe', 60):
    stop('device not back at 40fe after readback')
out = run([DFU, 'info', '-f'], 60)
if FW not in out:
    stop('info -f after readback did not show "%s"' % FW)
verdict = ('readback %d bytes (%.0f s, foreground, tools/flash_probe.py); %d of %d filesystem '
           'bytes differ; %d/%d words correct; readback kept at %s'
           % (len(rb), time.monotonic() - t0, d, FS, len(W) - len(bad), len(W), readback))
if d or bad:
    flashed_update({'verified': 'FAILED: ' + verdict})
    stop('readback MISMATCH -- do not press; investigate')
flashed_update({'verified': verdict})
say('DONE: flashed and verified. Next: the press plan, then log the result.')
