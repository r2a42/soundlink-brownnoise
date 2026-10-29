#!/usr/bin/env python3
"""probe161s: the CODE-REGION CONFIRMATION probe. probe161, byte for byte, plus the region.

docs/deep/code-region-plan.md. Behaviour-neutral by construction:

  * probe161's 189 cave words and 11 redirect bytes are copied VERBATIM from
    build/hook/probe161_words.json and probe161's REDIRECT_EDITS (asserted below);
    probe161 is what is on the speaker now, readback-verified, and pressed.
  * In each of the 7 functions listed in tools/caveguard.py CODE_REGION, the first
    writable boundary gets Bose's own immediate return (ld AL,#0 ; rts, or ld AL,#0 ;
    leavel -N after a one-word enterl), and EVERY other writable word of those 7
    functions gets the same stub pair as fill. Nothing branches to the region; the fill
    exists to exercise the write at the scale probe162 will use, and the readback checks
    every word.

Not touched: anything else. No USB/DFU path: none of the 7 functions reaches or is reached
from any function calling a USB, BootSetMode/GetMode, Loader* or PsStore/PsFlood trap
(checked 2026-10-08), and fsedit's digest compensation lands in the same data_us slack
range every probe since 11b has used.

THE CHECKS (laptop NOT connected to start):
  1. power on, nothing connected: the stock start-up ("battery ...", "ready to connect").
     A crash or reboot loop = the region writes are not inert -> recovery, flash stock.
  2. connect the laptop, play music ~1 minute, pause/resume, change volume. Anything
     abnormal -> stop, flash stock.
  3. the probe161 press (laptop connected, music PAUSED, long-press BLUETOOTH): expect
     probe161's own result, noise then "voice prompts on" (0x12).
Build:  python build/hook/assemble_probe161s.py [--build]
"""
import json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
sys.path.insert(0, 'tools'); sys.path.insert(0, 'tools/xapvm')
import caveguard, disasm, xapvm

_PROBE = 'probe161s'
AREA0 = 0x6EA30

# probe161's redirect bytes, VERBATIM (preflight.py reads this literal).
REDIRECT_EDITS = [("0x6fff1", "0x04"), ("0x6fff3", "0xd7"), ("0x6fff5", "0x3b"),
                  ("0x6fff6", "0xe0"), ("0x6fff7", "0x01"),
                  ("0x6fff8", "0x00"), ("0x6fff9", "0x00"),
                  ("0x6fffa", "0x00"), ("0x6fffb", "0x00"),
                  ("0x6fffc", "0x00"), ("0x6fffd", "0x00")]
_src161 = open('build/hook/assemble_probe161.py', encoding='utf-8').read()
_m = re.search(r'REDIRECT_EDITS\s*=\s*\[(.*?)\]', _src161, re.S)
assert [tuple(p) for p in re.findall(r'\(\s*"(0x[0-9a-fA-F]+)"\s*,\s*"(0x[0-9a-fA-F]+)"\s*\)',
                                        _m.group(1))] == REDIRECT_EDITS, 'redirect != probe161'

cave = {int(k, 16): v & 0xFFFF for k, v in
        json.load(open('build/hook/probe161_words.json')).items()}
assert len(cave) == 189, len(cave)
assert all(caveguard.SAFE_WINDOW[0] <= a < caveguard.SAFE_WINDOW[1] for a in cave)

writable = lambda a: (disasm.blind_byte(AREA0 + 2 * a) and disasm.blind_byte(AREA0 + 2 * a + 1))
region = {}
for f, (end, sa, sw) in sorted(caveguard.CODE_REGION.items()):
    assert all(writable(sa + k) for k in range(len(sw))), ('stub not writable', hex(f))
    for k, v in enumerate(sw):
        region[sa + k] = v
    # fill: every other writable word of the function, stub pair repeated, phase from
    # the start of each writable run
    a = f
    while a < end:
        if writable(a) and a not in region:
            run = a
            while a < end and writable(a) and a not in region:
                region[a] = (0x0014, 0x00E2)[(a - run) % 2]
                a += 1
        else:
            a += 1
assert not set(region) & set(cave)
assert all(caveguard.region_fn(a) is not None and writable(a) for a in region)

# decode-verify the stubs in the patched image: each function must now start with
# (enterl ; ) ld AL,#0 ; rts|leavel at an instruction boundary.
code, _ = disasm.load()
patched = list(code)
for a, v in region.items():
    patched[a] = v
for f, (end, sa, sw) in sorted(caveguard.CODE_REGION.items()):
    seq = [(a + f, op, v) for a, op, v, ln in xapvm.decode(patched[f:f + 4], fold_zero=False)]
    want = ([(f, 0x14, 0), (f + 1, 0xE2, 0)] if sa == f else
            [(f, 0x0B, None), (f + 1, 0x14, 0), (f + 2, 0x0F, None)])
    for (wa, wop, wv), (a, op, v) in zip(want, seq):
        assert a == wa and op == wop and (wv is None or v == wv), (hex(f), seq[:3])
    if sa != f:   # leavel must undo this function's own enterl: the decoder gives both
                  # the same operand (enterl adds it to Y, leavel subtracts it; xapemu)
        assert seq[0][2] == seq[2][2], (hex(f), seq[:3])
    print('  fn_%05x  stub OK: %s' % (f, ' ; '.join('%02x/%d' % (op, v) for _, op, v in seq[:3])))

print('%s: %d cave words (probe161, verbatim) + %d code-region words in %d functions'
      % (_PROBE, len(cave), len(region), len(caveguard.CODE_REGION)))
out = dict(cave); out.update(region)
json.dump({hex(a): v for a, v in sorted(out.items())},
          open('build/hook/%s_words.json' % _PROBE, 'w'), indent=0)

edits = list(REDIRECT_EDITS)
for cw in sorted(out):
    v = out[cw]
    edits.append((hex(AREA0 + 2 * cw), hex(v & 0xFF)))
    edits.append((hex(AREA0 + 2 * cw + 1), hex(v >> 8)))
cmd = [sys.executable, 'tools/fsedit.py', '--out', 'build/hook/%s_brown.dfu' % _PROBE]
for off, val in edits:
    cmd += ['--edit', '%s=%s' % (off, val)]
open('build/hook/%s_cmd.txt' % _PROBE, 'w').write(' '.join(cmd) + '\n')
if '--build' in sys.argv:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr); raise SystemExit('fsedit failed')
else:
    print('edit list ready (%d bytes) -> %s_cmd.txt' % (len(edits), _PROBE))
