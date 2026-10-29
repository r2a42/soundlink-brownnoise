#!/usr/bin/env python3
"""docaudit: re-derive the documentation's load-bearing numbers and check them.

The docs are full of addresses and counts that a future session will act on
without re-deriving. Several were written before the trap-table correction,
and at least one doc has already been found asserting something no longer
true. This recomputes each fact from the artifacts and checks that the text
still says it.

    python tools/docaudit.py            # report
    python tools/docaudit.py -v         # show every check, not just failures

A check is (label, computed value, the file that should say it, the exact
text that should appear). Anything that cannot be recomputed from an
artifact -- an owner observation, a judgement, a plan -- is deliberately not
here; this is for facts a machine can settle.


NOTE (this public export): this tool was written for, and hard-codes paths into, the original private research repository (CLAUDE.md, docs/RESUME-HERE.md, docs/field-log.md, and others not included here). It will not run cleanly against this export; it is kept for provenance, not as a tool this export expects you to run."""
import argparse
import json
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, 'firmware/bose/extracted/internal_fs/vm.app')
HDR = 24


def sext8(b):
    return b - 256 if b & 0x80 else b


def words(path=APP):
    d = open(path, 'rb').read()
    return [struct.unpack_from('<H', d, i)[0] for i in range(0, len(d) & ~1, 2)]


def decode(w, lo, hi):
    i = HDR + lo
    end = HDR + hi
    while i < end:
        s, v, k = i, 0, 0
        while i < end and (w[i] & 0xFF) == 0x00 and w[i] != 0 and k < 3:
            v = (v + sext8(w[i] >> 8)) << 8
            i += 1
            k += 1
        if i >= end:
            return
        x = w[i]
        i += 1
        yield s - HDR, i - s, x & 0xFF, (v + sext8(x >> 8)) & 0xFFFF, w[i - 1]


def facts():
    """Recompute everything the docs assert. Returns {label: value}."""
    w = words()
    code = (w[5] << 16) | w[6]
    const = w[7]
    f = {
        'code words': code,
        'const words': const,
        'header words': w[4],
        'const window end': 0x7400 + const - 1,
        'const cap margin': 0xD400 - 0x7400 - const,
        'cave data addr': 0x7400 + (0x3E21D - code),
        'vm version stamp': w[12],
    }
    ins = list(decode(w, 0, code))
    f['instructions'] = len(ins)

    # stubs
    stubs = json.load(open(os.path.join(ROOT, 'tools/bose-stubs.json')))
    f['stub count'] = len(stubs)
    for n in ('StreamAudioSink', 'SinkConfigure', 'StreamKalimbaSink',
              'KalimbaSendMessage', 'MessageSendLater', 'SinkClaim', 'SinkMap',
              'SinkFlush', 'SinkSlack', 'PanicNull', 'StreamConnect',
              'StreamRegionSource', 'malloc', 'MessageSinkTask',
              'StreamFileSource', 'StreamRingtoneSource', 'VmGetClock'):
        f['stub ' + n] = stubs[n]

    # nops and the B-96516 pattern
    nops = [k for k, (a, n, op, v, raw) in enumerate(ins) if raw == 0x0000 and n == 1]
    f['standalone nops'] = len(nops)
    add_addc = sum(1 for k in nops
                   if k + 1 < len(ins) and (ins[k + 1][2] >> 4) == 0x4
                   and (ins[k - 1][2] >> 4) == 0x3)
    sub_subc = sum(1 for k in nops
                   if k + 1 < len(ins) and (ins[k + 1][2] >> 4) == 0x6
                   and (ins[k - 1][2] >> 4) == 0x5)
    f['add-nop-addc'] = add_addc
    f['sub-nop-subc'] = sub_subc
    f['other nops'] = len(nops) - add_addc - sub_subc
    carry = [k for k, (a, n, op, v, raw) in enumerate(ins) if (op >> 4) in (0x4, 0x6)]
    f['addc/subc total'] = len(carry)
    f['addc/subc with nop'] = sum(1 for k in carry
                                  if ins[k - 1][4] == 0x0000 and ins[k - 1][1] == 1)

    # brxl / switches
    f['brxl count'] = sum(1 for a, n, op, v, raw in ins if op == 0x09 and raw == 0xFE09)
    f['modifier 0x0009 count'] = sum(1 for a, n, op, v, raw in ins
                                     if op == 0x09 and raw == 0x0009)

    # const strings
    cs = HDR + code
    strs, i = [], 0
    while i < const:
        if 0x20 <= w[cs + i] <= 0x7E:
            j = i
            while j < const and 0x20 <= w[cs + j] <= 0x7E:
                j += 1
            if j - i >= 4:
                strs.append((0x7400 + i, j - i))
            i = j
        else:
            i += 1
    f['const strings'] = len(strs)
    f['const string chars'] = sum(n for _, n in strs)
    f['const text pct'] = round(100.0 * f['const string chars'] / const)
    addrs = {a for a, _ in strs}
    loaded = {v for a, n, op, v, raw in ins if (op >> 4) == 1 and (op & 3) == 0 and v in addrs}
    f['strings loaded'] = len(loaded)
    f['strings never loaded'] = len(strs) - len(loaded)

    # the dead repeat flag
    f['refs to 0x5B0'] = sum(1 for a, n, op, v, raw in ins
                             if v == 0x5B0 and ((op & 3) == 1 and (op >> 4) in (1, 2, 8)
                                                or op == 0x99))

    # cave budget: zero runs inside the assemblers' scan window
    C0 = (0x6e974 + 0x34) % 64
    blind = lambda cw: 34 <= (2 * cw + C0) % 64 <= 60
    runs, i = [], 0x3E200
    while i < 0x3E400:
        if w[HDR + i] == 0:
            j = i
            while j < 0x3E400 and w[HDR + j] == 0:
                j += 1
            if j - i >= 40:
                runs.append((i, j, sum(1 for x in range(i, j) if blind(x))))
            i = j
        else:
            i += 1
    f['scan-window runs'] = len(runs)
    f['scan-window writable'] = sum(r[2] for r in runs)

    # trap tables
    t73 = json.load(open(os.path.join(ROOT, 'tools/traps-bluelab73.json')))
    t74 = json.load(open(os.path.join(ROOT, 'tools/traps-bluelab74.json')))
    f['traps 7.3.1'] = len(t73)
    f['traps 7.4'] = len(t74)
    f['renumbered traps'] = sum(1 for n in set(t73) & set(t74) if t73[n] != t74[n])

    # whatever is actually on the speaker, per the single source of truth
    flashed = {}
    for ln in open(os.path.join(ROOT, 'build/hook/FLASHED')):
        if '=' in ln and not ln.startswith('#'):
            k, v = ln.split('=', 1)
            flashed[k.strip()] = v.strip()
    f['flashed probe'] = flashed['probe']
    f['flashed status'] = flashed.get('status', 'ON DEVICE')
    f['flashed firmware'] = flashed.get('firmware', '')
    f['flashed image exists'] = os.path.exists(os.path.join(ROOT, flashed['image']))
    if not f['flashed status'].startswith('STOCK'):
        pw = json.load(open(os.path.join(
            ROOT, 'build/hook/%s_words.json' % flashed['probe'])))
        f['flashed words'] = len(pw)
        f['flashed first'] = min(int(k, 16) for k in pw)
        f['flashed last'] = max(int(k, 16) for k in pw)

    # re-run the library matcher so its documented addresses stay honest
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import libmatch
    ops, addrs = libmatch.bose_opcodes()
    for prefix, name, key in (
            ('build/libprobe/libprobe', '$_VolumeConvertStepsToDB', 'lib VolumeConvertStepsToDB'),
            ('build/sustainprobe/sustainprobe', '$_MessageCancelAll', 'lib MessageCancelAll')):
        fns = libmatch.probe_functions(os.path.join(ROOT, prefix), 6)
        hits = libmatch.find(ops, fns[name])
        f[key] = addrs[hits[0]] if hits else None

    # the whole-library scan's headline numbers, from the saved artifact
    art = os.path.join(ROOT, 'build/analysis/named-functions.txt')
    head = open(art, encoding='utf-8', errors='replace').read(400)
    f['libscan matched'] = int(re.search(r'# (\d+) distinct addresses', head).group(1))
    f['libscan on entry'] = int(re.search(r'# (\d+) of them', head).group(1))
    f['libscan strict'] = int(re.search(r'# (\d+) are high confidence', head).group(1))

    art2 = os.path.join(ROOT, 'build/analysis/named-app-functions.txt')
    h2 = open(art2, encoding='utf-8', errors='replace').read(400)
    f['sinkscan matched'] = int(re.search(r'# (\d+) distinct addresses', h2).group(1))
    f['sinkscan on entry'] = int(re.search(r'# (\d+) of them', h2).group(1))

    # sink events: how many 0x4xxx values Bose uses, and how many are named
    ev = open(os.path.join(ROOT, 'build/analysis/sink-events.txt'),
              encoding='utf-8', errors='replace').read()
    m = re.search(r'# (\d+) distinct values used, (\d+) named', ev)
    f['events used'], f['events named'] = int(m.group(1)), int(m.group(2))
    return f


CHECKS = [
    # (fact key, file, template using {v}; {v:X} for hex)
    ('code words', 'docs/message-task-abi.md', 'code = {v} words'),
    ('const words', 'docs/message-task-abi.md', 'const =\n24475'),
    ('const window end', 'docs/message-task-abi.md', 'ending 0x{v:X}'),
    ('const cap margin', 'docs/message-task-abi.md', 'a {v}-word\nmargin'),
    ('cave data addr', 'docs/message-task-abi.md', 'data address\n`0x{v:X}`'),
    ('stub StreamAudioSink', 'docs/trap-numbering.md', '| `StreamAudioSink` | **0x{v:03X}** |'),
    ('stub SinkConfigure', 'docs/trap-numbering.md', '| `SinkConfigure` | **0x{v:03X}** |'),
    ('stub StreamKalimbaSink', 'docs/trap-numbering.md', '| `StreamKalimbaSink` | **0x{v:03X}** |'),
    ('stub KalimbaSendMessage', 'docs/trap-numbering.md', '| `KalimbaSendMessage` | **0x{v:03X}** |'),
    ('stub MessageSendLater', 'docs/message-task-abi.md', '| `MessageSendLater` | **0x{v:03X}** |'),
    ('stub SinkSlack', 'docs/message-task-abi.md', '| `SinkSlack` | **0x{v:03X}** |'),
    ('stub StreamRegionSource', 'docs/bose-audio-path.md', 'stub 0x{v:03X}'),
    ('stub malloc', 'docs/bose-audio-path.md', 'stub **0x{v:03X}**'),
    ('traps 7.3.1', 'docs/trap-numbering.md', '| BlueLab 7.3.1 | {v} |'),
    ('traps 7.4', 'docs/trap-numbering.md', '| BlueLab 7.4 | {v} |'),
    ('renumbered traps', 'docs/trap-numbering.md', '**{v} of the 257'),
    ('stub count', 'docs/trap-stub-table.md', 'All {v} trap stubs'),
    ('instructions', 'docs/xap-opcodes.md', '**{v:,} instructions**'),
    ('standalone nops', 'docs/adk-compiler.md', '**113 standalone `nop` instructions**'),
    ('add-nop-addc', 'docs/adk-compiler.md', '| `add` then `addc` | {v} |'),
    ('sub-nop-subc', 'docs/adk-compiler.md', '| `sub` then `subc` | {v} |'),
    ('other nops', 'docs/adk-compiler.md', '| anything else | {v} |'),
    ('addc/subc total', 'docs/adk-compiler.md', "image's {v}"),
    ('brxl count', 'docs/xap-opcodes.md', '{v} of the second'),
    ('modifier 0x0009 count', 'docs/xap-opcodes.md', '{v} of the first'),
    ('const strings', 'docs/const-strings.md', '**{v} printable strings**'),
    ('const string chars', 'docs/const-strings.md', '{v:,} characters'),
    ('strings loaded', 'docs/cave-budget.md', '**{v} strings are loaded'),
    ('strings never loaded', 'docs/cave-budget.md', '**{v} are never loaded'),
    ('const text pct', 'docs/const-strings.md', '{v}% of the 24,475-word'),
    ('refs to 0x5B0', 'docs/const-strings.md', 'exactly two references'),
    ('scan-window writable', 'docs/cave-budget.md', '| | | **{v}** |'),
    # (the checks on what is flashed live in DEVICE_CHECKS / LOST_CHECKS below)
    # library matches: these are addresses a future session may act on
    ('lib VolumeConvertStepsToDB', 'docs/library-matching.md', '| **0x{v:05X}** | `VolumeConvertStepsToDB` | 118 |'),
    ('lib MessageCancelAll', 'docs/library-matching.md', '| 0x{v:05X} | `MessageCancelAll` | 15 |'),
    ('libscan matched', 'docs/library-matching.md', '# {v} distinct addresses matched'),
    ('libscan on entry', 'docs/library-matching.md', '# {v} of them (99%)'),
    ('libscan strict', 'docs/library-matching.md', '# {v} are high confidence'),
    ('sinkscan matched', 'docs/library-matching.md', '# {v} distinct addresses matched'),
    ('sinkscan on entry', 'docs/library-matching.md', '# {v} of them (100%)'),
    ('events used', 'docs/sink-events.md', '**Bose uses {v} distinct values'),
    ('events named', 'docs/sink-events.md', 'and {v} of them have an'),
]


# What the docs must say about the device, per build/hook/FLASHED. Two regimes, because
# on 2026-10-04 these checks went on enforcing "probe114 ... readback-verified" in
# RESUME-HERE.md for eleven flashes after it stopped being true, and then for a unit that
# no longer enumerated. A check that pins stale text is worse than none.
DEVICE_CHECKS = [   # status absent or not LOST: a live, readback-verified image
    ('flashed words', 'docs/field-log.md', '{v} words at 0x3E21D'),
    ('flashed first', 'docs/RESUME-HERE.md', 'all {vv} cave words'),
    # the docs must name the probe that is actually on the device
    ('flashed probe', 'docs/RESUME-HERE.md', '**{v}** (`build/hook/{v}_brown.dfu`)'),
    ('flashed probe', 'docs/field-log.md', '# {v} '),
    ('flashed image exists', 'docs/RESUME-HERE.md', 'readback-verified'),
]
LOST_CHECKS = [     # status=LOST: the docs must say so, and name the last image
    ('flashed probe', 'docs/RESUME-HERE.md', 'with **{v}** on it'),
    ('flashed probe', 'docs/RESUME-HERE.md', '**Nothing \u2014 there is no speaker.**'),
    ('flashed probe', 'docs/field-log.md', '| **{v}** |'),
    ('flashed probe', 'docs/POST-MORTEM-2026-10-04.md', 'eleven flashes and nine presses'),
    ('flashed image exists', 'docs/NEXT-UNIT-CHECKLIST.md', 'Next unit'),
]

STOCK_CHECKS = [    # status=STOCK: official firmware, no cave on the device
    ('flashed firmware', 'docs/RESUME-HERE.md', 'stock **{v}**'),
    ('flashed firmware', 'docs/field-log.md', 'stock **{v}**'),
    ('flashed image exists', 'firmware/bose/unit2/README.md', 'readback path is proven'),
]


def broken_refs():
    """Paths the docs point at that do not exist.

    Link rot is silent and it wastes a future session's time. Only
    repo-relative paths in backticks are checked; a few ADK-relative ones
    inside docs/toolchain.md's "what is in it" section are skipped, since
    there the prefix is the ADK root rather than this repo.
    """
    import glob
    pat = re.compile(r'`((?:docs|tools|build|firmware|fw|opus_task)/[A-Za-z0-9_./-]+)`')
    skip = {'tools/bin/xap-local-xap-gcc', 'tools/include/firmware/',
            'firmware/assisted/unified/gordon/'}
    out = []
    files = sorted(glob.glob(os.path.join(ROOT, 'docs/*.md')))
    files.append(os.path.join(ROOT, 'README.md'))
    for p in files:
        if not os.path.exists(p):
            continue
        s = open(p, encoding='utf-8', errors='replace').read()
        for m in sorted(set(pat.findall(s))):
            t = m.rstrip('.')
            if t in skip or '*' in t:
                continue
            if not os.path.exists(os.path.join(ROOT, t)):
                out.append('%s -> %s'
                           % (os.path.relpath(p, ROOT).replace(os.sep, '/'), t))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args()
    f = facts()
    bad = 0
    st = f['flashed status']
    checks = CHECKS + (LOST_CHECKS if st.startswith('LOST') else
                       STOCK_CHECKS if st.startswith('STOCK') else DEVICE_CHECKS)
    print('device: %s -- %s' % (f['flashed probe'], f['flashed status'][:64]))
    for key, path, tmpl in checks:
        v = f[key]
        want = tmpl.format(v=v, vv=f.get('flashed words'))
        text = open(os.path.join(ROOT, path), encoding='utf-8', errors='replace').read()
        ok = want in text
        if not ok:
            bad += 1
        if args.verbose or not ok:
            print('%-4s %-26s %-32s %s' % ('ok' if ok else 'FAIL', key,
                                           path.replace('docs/', ''),
                                           'expected: %r' % want if not ok else v))
    refs = broken_refs()
    for r in refs:
        print('FAIL broken reference: %s' % r)
    bad += len(refs)
    print('\n%d fact checks, %d broken references, %d failing overall'
          % (len(checks), len(refs), bad))
    if args.verbose:
        print('\nall recomputed facts:')
        for k in sorted(f):
            print('  %-26s %s' % (k, f[k]))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
