#!/usr/bin/env python3
"""Offline world-model gate for probe196 (step R1, the read-only H2' census) -- 2026-10-13.

Runs the real words (build/hook/probe196_words.json, written by assemble_probe196.py) through tools/cavesim.py's
clocked world model (with the R1 raw-source / PartitionGetInfo / SinkSlack additions of the same date), one scripted
scenario per entry, each checked with the simulator's own --expect plus regular expressions on its output.
Exit 0 = every scenario holds.  NO device, no flash tool: pure emulation.

    python build/hook/assemble_probe196.py                       # first (writes probe196_words.json)
    python build/hook/gate_probe196.py [--part I/N] [--list] [--words PATH]
    --words PATH  runs a mutated copy of the words: the gate must FAIL there (mutation rows)

THE HEALTHY BASE: one centre-long press at t = 0, the DSP up (--dsp up is the world default), p2 TYPE 3, STATE 0
(VALID), SIZE 0xF9FFC (the F216 default p2 less its 4 header words), a raw source of 300 incrementing octets,
SinkSlack at its default.  Ticks fall at 2000 (T1), 10000 (T2A), 18000 (T2B), 26000 (T3) ms (STAGE_MS 8000).
Expected: the control 0x1F "muted", then 0x12, 0x3B, and the 0xD3 chain's 0x2D (octets, not zero, none > 0xFF).
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
E = ['--entry', '0x3E21D']
PRESS = ['--press', '0:4004']
PI = ['--pinfo', '2:2=3', '--pinfo', '2:3=0', '--pinfo', '2:1=0xF9FFC']
RAW = ['--raw-p2', 'incr:300']
H = E + PRESS + PI + RAW + ['--horizon', '60000']          # the healthy base (all world flags are opt-in)


def pinfo(**kw):
    """pinfo(type=3, state=0, size='0xF9FFC') -> --pinfo flags for partition 2 (keys 2, 3, 1)"""
    key = {'type': 2, 'state': 3, 'size': 1}
    out = []
    for k in ('type', 'state', 'size'):
        if k in kw:
            out += ['--pinfo', '2:%d=%s' % (key[k], kw[k])]
    return out


SCEN = []       # (group, name, args (after the probe name), expects (--expect list), regex list, extra)


def S(group, name, args, expects, regex=(), **extra):
    SCEN.append((group, name, args, list(expects), list(regex), extra))


NOMINAL = ['spoken=1f,12,3b,2d', 'violations=0', 'pending=0', 'swallowed=1', 'replayed=0',
           'rawopen=1', 'rawclosed=1', 'rawdrops=0']

# ------------------------------------------------------------------ NOMINAL
S('NOMINAL', 'healthy base: 1f 12 3b 2d at 2000 10000 18000 26000, one source opened and closed, no SourceDrop',
  H, NOMINAL, [r'spoken: 0x1f@2000, 0x12@10000, 0x3b@18000, 0x2d@26000', r'PartitionGetRawSerialSource'])
S('NOMINAL', 'TYPE 0 (unused): the control still passes (equal reads of 0 with a TRUE bool); T2A then says 0x16 and the chain ENDS',
  H + pinfo(type=0), ['spoken=1f,16', 'pending=0', 'rawopen=0', 'rawcalls=0', 'violations=0'])
S('NOMINAL', 'SOURCE SIZE 127 is accepted like 126', H + ['--raw-prime', '127'], NOMINAL)

# ------------------------------------------------------------------ T1: GATE and the control
S('T1', 'DSP down at the first tick: 0x21 only, the chain ends, no p2 query, no source',
  E + PRESS + PI + RAW + ['--dsp', 'down', '--horizon', '60000'],
  ['spoken=21', 'violations=0', 'pending=0', 'rawopen=0'], [r'spoken: 0x21@2000'])
S('T1', 'music paused: the DSP unloads at 500 ms (before the first tick), the gate reads FALSE -> 0x21 only',
  H + ['--unload-at', '500'], ['spoken=21', 'pending=0', 'rawopen=0'])
S('T1', 'the STOCK PartitionGetInfo call of the control returns FALSE (call 1) -> 0x1C only, chain ends',
  H + ['--getinfo-fail-at', '1'], ['spoken=1c', 'pending=0', 'rawopen=0'])
S('T1', 'the SYNTHESISED stub returns FALSE (call 2) -> 0x20 only, no 0xD3 call',
  H + ['--getinfo-fail-at', '2'], ['spoken=20', 'pending=0', 'rawopen=0', 'violations=0'])
S('T1', 'CONTROL MISMATCH (the synthesised stub writes TYPE+1) -> 0x20 only; no 0xD3 call',
  H + ['--synth-skew', '1'], ['spoken=20', 'pending=0', 'rawopen=0', 'violations=0'])
S('T1', 'V05 D2: a stub that RETURNS WITHOUT RUNNING THE TRAP (AL = 1 left from the argument load, sentinel untouched) '
        '-> 0x20, not 0x1F', H + ['--synth-noop'], ['spoken=20', 'pending=0', 'rawopen=0'])

# ------------------------------------------------------------------ T2A: TYPE and STATE
S('T2A', 'STATE 1 INCOMPLETE -> 0x13 (the chain CONTINUES: only 0x12, 0x13, 0x14 continue it)',
  H + pinfo(state=1), ['spoken=1f,13,3b,2d', 'pending=0'])
S('T2A', 'STATE 2 INVALID -> 0x14 (the chain CONTINUES to T2B and T3)', H + pinfo(state=2), ['spoken=1f,14,3b,2d', 'pending=0', 'rawcalls=1'])
S('T2A', 'V06 D1: STATE 9 (outside the enum) -> 0x15 and the chain ENDS: no T2B, no 0xD3 call (4 GetInfo calls only)',
  H + pinfo(state=9), ['spoken=1f,15', 'getinfo=4', 'pending=0', 'rawopen=0', 'rawcalls=0', 'violations=0'])
S('T2A', 'V06 D1: STATE 3 (just outside the enum) -> 0x15 and the chain ENDS', H + pinfo(state=3),
  ['spoken=1f,15', 'getinfo=4', 'pending=0', 'rawopen=0', 'rawcalls=0', 'violations=0'])
S('T2A', 'V06 D1: TYPE 1 (a filesystem) -> 0x16 "english" and the chain ENDS, STATE is not read (3 GetInfo calls)',
  H + pinfo(type=1), ['spoken=1f,16', 'getinfo=3', 'pending=0', 'rawopen=0', 'rawcalls=0', 'violations=0'])
S('T2A', 'V06 D1: TYPE 0 (unused) -> 0x16 and the chain ENDS', H + pinfo(type=0), ['spoken=1f,16', 'pending=0', 'rawopen=0', 'rawcalls=0', 'violations=0'])
S('T2A', 'V06 D1: TYPE 4 (random access) -> 0x16 and the chain ENDS', H + pinfo(type=4), ['spoken=1f,16', 'pending=0', 'rawopen=0', 'rawcalls=0', 'violations=0'])
S('T2A', 'V06 D1: PartitionGetInfo call 3 (T2A TYPE; calls 1 and 2 are the control) returns FALSE -> 0x1E and the chain ENDS',
  H + ['--getinfo-fail-at', '3'], ['spoken=1f,1e', 'getinfo=3', 'pending=0', 'rawopen=0', 'rawcalls=0', 'violations=0'])
S('T2A', 'V06 D1: PartitionGetInfo call 4 (STATE) returns FALSE -> 0x1E and the chain ENDS',
  H + ['--getinfo-fail-at', '4'], ['spoken=1f,1e', 'getinfo=4', 'pending=0', 'rawopen=0', 'rawcalls=0', 'violations=0'])

# ------------------------------------------------------------------ T2B: SIZE
S('T2B', 'SIZE 0xF9FFC (the default p2) -> 0x3B (this is the base)', H, ['spoken=1f,12,3b,2d'])
S('T2B', 'SIZE 0x7600 (the smallest "big enough") -> 0x3D', H + pinfo(size='0x7600'),
  ['spoken=1f,12,3d,2d'])
S('T2B', 'SIZE 0x75FF (one word below) -> 0x39', H + pinfo(size='0x75FF'), ['spoken=1f,12,39,2d'])
S('T2B', 'SIZE 0x7000 -> 0x39', H + pinfo(size='0x7000'), ['spoken=1f,12,39,2d'])
S('T2B', 'SIZE 0 -> 0x39', H + pinfo(size='0'), ['spoken=1f,12,39,2d'])
S('T2B', 'SIZE 0x20000 (high half 2) -> 0x3D', H + pinfo(size='0x20000'), ['spoken=1f,12,3d,2d'])
S('T2B', 'SIZE 0xF0000 (high half 0xF, low half 0) -> 0x3D, NOT the default id', H + pinfo(size='0xF0000'),
  ['spoken=1f,12,3d,2d'])
S('T2B', 'SIZE 0xFA000 (the default WITHOUT the header subtraction) -> 0x3D', H + pinfo(size='0xFA000'),
  ['spoken=1f,12,3d,2d'])
S('T2B', 'SIZE 0x4F9FFC (high half 0x4F, low half the default) -> 0x3D', H + pinfo(size='0x4F9FFC'),
  ['spoken=1f,12,3d,2d'])
S('T2B', 'PartitionGetInfo call 5 (SIZE) returns FALSE -> 0x23',
  H + ['--getinfo-fail-at', '5'], ['spoken=1f,12,23,2d', 'pending=0'])

# ------------------------------------------------------------------ T3: the 0xD3 chain
S('T3', 'raw source refused (handle 0): 0x27, no source to close',
  E + PRESS + PI + ['--raw-p2', 'none', '--horizon', '60000'],
  ['spoken=1f,12,3b,27', 'rawopen=0', 'rawclosed=0', 'violations=0', 'pending=0'])
S('T3', 'the stub returns 0 for a forced failure (--fail PartitionGetRawSerialSource): 0x27',
  H + ['--fail', 'PartitionGetRawSerialSource'], ['spoken=1f,12,3b,27', 'rawopen=0'])
S('T3', 'handle but SourceSize 0 -> 0x29 (odd) and the source is closed',
  H + ['--raw-prime', '0'], ['spoken=1f,12,3b,29', 'rawopen=1', 'rawclosed=1', 'rawdrops=0'])
S('T3', 'V05 D1: SourceSize 64 (a 64-octet buffer, or a short payload) -> its OWN id 0x28, closed, never mapped',
  H + ['--raw-prime', '64'], ['spoken=1f,12,3b,28', 'rawclosed=1', 'rawmaps=0'])
S('T3', 'V05 D1: a valid 16-byte payload (probe140 size): SourceSize 16 -> 0x28, NOT 0x29',
  E + PRESS + PI + ['--raw-p2', 'incr:16', '--horizon', '60000'], ['spoken=1f,12,3b,28', 'rawclosed=1', 'rawmaps=0'])
S('T3', 'V05 D1: SourceSize 125 (the largest short size) -> 0x28', H + ['--raw-prime', '125'],
  ['spoken=1f,12,3b,28', 'rawmaps=0'])
S('T3', 'V05 D1: SourceSize 1 -> 0x28', E + PRESS + PI + ['--raw-p2', 'incr:1', '--horizon', '60000'],
  ['spoken=1f,12,3b,28', 'rawmaps=0'])
S('T3', 'SourceSize 128 (more than 127) -> 0x29, closed, never mapped', H + ['--raw-prime', '128'],
  ['spoken=1f,12,3b,29', 'rawclosed=1', 'rawmaps=0'])
S('T3', 'SourceMap returns 0 -> 0x34 and the source is closed', H + ['--raw-map-zero'],
  ['spoken=1f,12,3b,34', 'rawclosed=1', 'rawdrops=0'])
S('T3', 'all-zero octets -> 0x2A', E + PRESS + PI + ['--raw-p2', 'zero:300', '--horizon', '60000'],
  ['spoken=1f,12,3b,2a', 'rawclosed=1'])
S('T3', 'octets with a 0xFF among them -> still NARROW 0x2D',
  E + PRESS + PI + ['--raw-p2', 'hex:00ff00ff00ff00ff' + '00' * 124, '--horizon', '60000'],
  ['spoken=1f,12,3b,2d'])
S('T3', 'the probe141 stream as octets (64 66 75 31 ...) -> 0x2F',
  E + PRESS + PI + ['--raw-p2', 'staged141', '--horizon', '60000'], ['spoken=1f,12,3b,2f', 'rawclosed=1'])
S('T3', 'the probe141 stream but only 3 octets right (64 66 75 30 ...) -> NARROW 0x2D, not 0x2F',
  E + PRESS + PI + ['--raw-p2', 'hex:64667530' + '11' * 124, '--horizon', '60000'], ['spoken=1f,12,3b,2d'])
S('T3', 'the probe141 stream but the FIRST octet wrong (65 66 75 31 ...) -> 0x2D',
  E + PRESS + PI + ['--raw-p2', 'hex:65667531' + '11' * 124, '--horizon', '60000'], ['spoken=1f,12,3b,2d'])
S('T3', 'packed elements (two octets per element, little-endian): some element > 0xFF -> WIDE 0x2E',
  H + ['--raw-pack', 'le'], ['spoken=1f,12,3b,2e', 'rawclosed=1'])
S('T3', 'packed elements, big-endian -> WIDE 0x2E', H + ['--raw-pack', 'be'], ['spoken=1f,12,3b,2e'])
S('T3', 'the probe141 stream, packed little-endian (0x6664 0x3175 ...) -> WIDE 0x2E (no packed match is built)',
  E + PRESS + PI + ['--raw-p2', 'staged141', '--raw-pack', 'le', '--horizon', '60000'], ['spoken=1f,12,3b,2e'])
S('T3', 'a non-zero element only at index 7 (the last one looked at) -> NARROW 0x2D, not ZERO',
  E + PRESS + PI + ['--raw-p2', 'hex:00000000000000' + '05' + '00' * 118, '--horizon', '60000'],
  ['spoken=1f,12,3b,2d'])
S('T3', 'a non-zero element only at index 8 (NOT looked at) -> ZERO 0x2A (the class is "first 8 elements")',
  E + PRESS + PI + ['--raw-p2', 'hex:0000000000000000' + '05' + '00' * 117, '--horizon', '60000'],
  ['spoken=1f,12,3b,2a'])
S('T3', 'p2 STATE not VALID with a raw source configured: the model still builds it (the model is not the firmware)',
  H + pinfo(state=2), ['spoken=1f,14,3b,2d'])

# ------------------------------------------------------------------ PRESS handling
S('PRESS', 'a second press at 3000 ms (T2A pending until 10000): STOP, T2A..T3 never run, nothing pending',
  H + ['--press', '3000:4004'], ['spoken=1f', 'pending=0', 'swallowed=2', 'rawopen=0', 'violations=0'])
S('PRESS', 'a second press at 500 ms (T1 pending): STOP, nothing is ever spoken',
  H + ['--press', '500:4004'], ['spoken=', 'pending=0', 'swallowed=2', 'rawopen=0'])
S('PRESS', 'a second press at 21000 ms (T3 pending until 26000): STOP, T3 never runs',
  H + ['--press', '21000:4004'], ['spoken=1f,12,3b', 'pending=0', 'rawopen=0'])
S('PRESS', 'a second press at 40000 ms (the census is over): a SECOND census runs',
  E + PRESS + PI + RAW + ['--horizon', '100000', '--press', '40000:4004'],
  ['spoken=1f,12,3b,2d,1f,12,3b,2d', 'pending=0', 'swallowed=2', 'rawopen=2', 'rawclosed=2', 'violations=0'])
S('PRESS', 'a non-0x4004 event is replayed to the stock, nothing else happens',
  E + ['--press', '0:4003', '--once'] + PI + RAW,
  ['spoken=', 'pending=0', 'replayed=1', 'swallowed=0', 'rawopen=0'])
S('PRESS', 'an id that is not a stage (0x77) delivered to the handler: nothing happens',
  E + ['--pending', '77@1000', '--horizon', '10000'] + PI + RAW, ['spoken=', 'pending=0', 'rawopen=0', 'violations=0'])
S('PRESS', 'cancel never finds a message (--cancel never): the chain runs regardless, a second press forks nothing '
           'dangerous (R6 may flag the duplicate chain)',
  H + ['--cancel', 'never', '--press', '3000:4004'], ['rawopen=2'], extra_ok_violations=True)

# ------------------------------------------------------------------ STUBS / WORLD HOLES
S('STUBS', 'the trap list names both synthesised stubs and the stock calls (control order: stock GetInfo, '
           'then the stub)', H, NOMINAL,
  [r'SYNTHESISED TRAP STUB at 0x3E241: trap 0xCE PartitionGetInfo, inline tail, 8 words',
   r'SYNTHESISED TRAP STUB at 0x3E25D: trap 0xD3 PartitionGetRawSerialSource, inline tail, 8 words'])
S('STUBS', 'SpeakID is called with port 3 never ours: rule R3 silent', H, ['violations=0'],
  [r'port-3 rules: OK'])


def run_one(words, scen):
    group, name, args, expects, regex, extra = scen
    cmd = [sys.executable, 'tools/cavesim.py', words] + args + ['--brief']
    for e in expects:
        cmd += ['--expect', e]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)
    out = r.stdout + r.stderr
    ok = (r.returncode == 0) or extra.get('extra_ok_violations') and r.returncode in (0, 1)
    bad = []
    if r.returncode != 0 and not extra.get('extra_ok_violations'):
        bad.append('exit code %d' % r.returncode)
    for ln in out.splitlines():
        if ln.startswith('expect ') and ln.rstrip().endswith('FAIL') or ' FAIL (have' in ln:
            bad.append(ln.strip())
    for rx in regex:
        if not re.search(rx, out):
            bad.append('missing /%s/' % rx)
    if 'STOPPED' in out or 'Traceback' in out:
        bad.append('STOPPED/Traceback in the output')
    return bad, out


def main():
    argv = sys.argv[1:]
    if '--list' in argv:
        for i, s in enumerate(SCEN):
            print('%2d %-8s %s' % (i, s[0], s[1]))
        return 0
    words = 'probe196'
    if '--words' in argv:
        words = argv[argv.index('--words') + 1]
    part = (0, 1)
    if '--part' in argv:
        a, b = argv[argv.index('--part') + 1].split('/')
        part = (int(a) - 1, int(b))
    fails = 0
    ran = 0
    for i, s in enumerate(SCEN):
        if i % part[1] != part[0]:
            continue
        bad, out = run_one(words, s)
        ran += 1
        print('%s %2d %-7s %s' % ('FAIL' if bad else 'ok  ', i, s[0], s[1]))
        for b in bad:
            print('      -> %s' % b)
        if bad:
            fails += 1
            print('\n'.join('      | ' + ln for ln in out.splitlines()[-25:]))
    print('\n%d scenario(s) run, %d failed' % (ran, fails))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
