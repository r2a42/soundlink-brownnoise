#!/usr/bin/env python3
"""Pre-flight: verify a built probe DFU actually contains what the assembler intended.

Every probe so far has been verified two ways -- in the emulator before flashing, and by
readback after. **Nothing checked the built DFU itself**, between those two steps. This
closes that gap, offline, before a button press is spent.

For each probe it confirms:

  1. the DFU is the same length as the official image and the `fsr_dfu1` filesystem area
     sits at the same offset (so area offsets are directly comparable);
  2. **every cave word is present at its own address**, read back out of the DFU;
  3. every redirect (hook) byte holds the intended value;
  4. every differing byte is accounted for as cave, redirect, or digest compensation --
     an unexplained difference means something is wrong. (Round 3, V03: this used to be
     informational for the bytes that were neither cave nor redirect -- the line printed
     "compensation/other N" and passed whatever N was, so for the staged 184a/184 images it
     counted 2,800 / 60,000 staged payload bytes as "compensation". Those bytes are now
     classified: compensation = inside fsedit's SLACK_RANGE (the last 256 bytes of data_us),
     staged payload cells = data_us file bytes 18..45 of a 64-byte period (the FIRST = 9, 28-byte
     layout of build/hook/narrow184_lib.py), anything else FAILS. The classification is
     structural; the exact staged VALUES are checked by the image's own gate and DFU replay.)

Area byte offsets map to DFU offsets as `dfu = fsr_dfu1_offset + area_offset`, and a cave
word at project address `a` lives at area offset `AREA0 + 2*a` (AREA0 = 0x6EA30), low byte
first. That mapping is NOT the raw DFU offset -- getting it wrong makes the check pass
vacuously, so step 2 is what gives the result its force.

Usage:  python tools/preflight.py probe117 [probe118 ...]
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OFFICIAL = os.path.join(ROOT, 'firmware/bose/minnow_3.0.3',
                        'Minnow_3.0.3_stack_plus_app.dfu')
AREA0 = 0x6EA30


def redirect_edits(probe):
    """Pull REDIRECT_EDITS out of the probe's assembler, including any appends."""
    path = os.path.join(ROOT, 'build/hook/assemble_%s.py' % probe)
    src = open(path, encoding='utf-8').read()
    pairs = []
    m = re.search(r'REDIRECT_EDITS\s*=\s*\[(.*?)\]', src, re.S)
    if m:
        pairs += re.findall(r'\(\s*"(0x[0-9a-fA-F]+)"\s*,\s*"(0x[0-9a-fA-F]+)"\s*\)',
                            m.group(1))
    pairs += re.findall(
        r'REDIRECT_EDITS\.append\(\(\s*"(0x[0-9a-fA-F]+)"\s*,\s*"(0x[0-9a-fA-F]+)"\s*\)\)',
        src)
    return [(int(a, 16), int(v, 16)) for a, v in pairs]


def check(probe):
    dfu = os.path.join(ROOT, 'build/hook/%s_brown.dfu' % probe)
    wj = os.path.join(ROOT, 'build/hook/%s_words.json' % probe)
    for p in (dfu, wj):
        if not os.path.exists(p):
            print('%-9s SKIP  missing %s' % (probe, os.path.basename(p)))
            return None
    off = open(OFFICIAL, 'rb').read()
    new = open(dfu, 'rb').read()
    ia_o, ia_n = off.find(b'fsr_dfu1'), new.find(b'fsr_dfu1')
    words = {int(k, 16): v & 0xFFFF for k, v in json.load(open(wj)).items()}
    red = redirect_edits(probe)

    problems = []
    if len(off) != len(new):
        problems.append('length %d != official %d' % (len(new), len(off)))
    if ia_o != ia_n or ia_n < 0:
        problems.append('fsr_dfu1 at 0x%x, official 0x%x' % (ia_n, ia_o))

    bad_words = []
    for a, want in sorted(words.items()):
        b = ia_n + AREA0 + 2 * a
        got = new[b] | (new[b + 1] << 8)
        if got != want:
            bad_words.append((a, want, got))
    bad_red = []
    for aoff, want in red:
        got = new[ia_n + aoff]
        if got != want:
            bad_red.append((aoff, want, got))

    # probe130 passed every check in this file and still crashed the speaker on boot: all
    # 234 of its cave words were zero in the official image and inside a DFU blind window,
    # but 55 of them lay OUTSIDE the hardware-proven const window and landed in zero gaps
    # inside live tables. Zero does not mean unread. caveguard enforces the window.
    import caveguard
    window_ok = caveguard.check(probe)
    # probe131 passed every other gate and crashed: it emitted a 2-word `ble`, a form
    # Bose never uses. The assembler and emulator share one opcode table so both agreed.
    attested = caveguard.attest(probe)
    # J-T12 / J-T3: a cave that calls a trap with no stub in vm.app carries its own stub (the
    # five tail words). Every such stub must be canonical, declared in the assembler and listed.
    synth_ok = caveguard.attest_trap_stubs(probe)

    diff = {i for i in range(min(len(off), len(new))) if off[i] != new[i]}
    cave_b = set()
    for a in words:
        cave_b.add(ia_n + AREA0 + 2 * a)
        cave_b.add(ia_n + AREA0 + 2 * a + 1)
    red_b = {ia_n + a for a, _ in red}
    unexplained = diff - cave_b - red_b
    # V03: split the unexplained bytes. body byte = area byte - 140 (fsedit.in_file_data); data_us
    # byte 0 is at area byte 600 and the file is 219,528 bytes (promptmap.DATA_AREA_BYTE0/DATA_SIZE).
    try:
        import fsedit
        slack_lo, slack_hi = fsedit.SLACK_RANGE
    except Exception:                                  # the proven constants, if fsedit will not import
        slack_lo, slack_hi = 0x35A54, 0x35B54
    comp_b = {i for i in unexplained if slack_lo <= i - ia_n - 140 < slack_hi}
    staged_b = {i for i in unexplained - comp_b
                if 600 <= i - ia_n < 600 + 219528 and 18 <= (i - ia_n - 600) % 64 < 46}
    other_b = unexplained - comp_b - staged_b

    print('%-9s %d words, %d redirect bytes, %d bytes differ from official'
          % (probe, len(words), len(red), len(diff)))
    print('          cave %d  redirect %d  compensation/other %d'
          % (len(diff & cave_b), len(diff & red_b), len(unexplained)))
    if staged_b or other_b:
        print('          of those: data_us slack (compensation) %d, staged payload cells %d, '
              'UNEXPLAINED %d' % (len(comp_b), len(staged_b), len(other_b)))
    if bad_words:
        problems.append('%d cave words wrong, first: a=0x%05x want 0x%04x got 0x%04x'
                        % ((len(bad_words),) + bad_words[0]))
    if bad_red:
        problems.append('%d redirect bytes wrong, first: area 0x%05x want 0x%02x got 0x%02x'
                        % ((len(bad_red),) + bad_red[0]))
    if other_b:
        problems.append('%d differing bytes are neither cave, redirect, data_us slack compensation '
                        'nor staged payload cells, first at area byte 0x%x'
                        % (len(other_b), min(other_b) - ia_n))
    if not attested:
        problems.append('emits an instruction form that appears NOWHERE in Bose firmware '
                        '(see caveguard attest) -- this is what crashed probe131')
    if not synth_ok:
        problems.append('a synthesised trap stub is not canonical / not declared / not '
                        'listed, or a stray 0x0E/0xE1 is in the cave '
                        '(see caveguard attest_trap_stubs)')
    if not window_ok:
        problems.append('cave words outside the hardware-proven const window '
                        '(see caveguard) -- this is what crashed probe130 on boot')
    if problems:
        for p in problems:
            print('          FAIL  %s' % p)
        return False
    print('          OK    all %d cave words and %d redirect bytes verified in the image'
          % (len(words), len(red)))
    return True


if __name__ == '__main__':
    names = sys.argv[1:] or ['probe114', 'probe117', 'probe118', 'probe119']
    results = [check(n) for n in names]
    bad = [n for n, r in zip(names, results) if r is False]
    print()
    print('FAILED: %s' % ', '.join(bad) if bad else 'all checked probes pass pre-flight')
    sys.exit(1 if bad else 0)
