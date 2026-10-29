#!/usr/bin/env python3
"""narrow184_lib: the payload, ROFS and data_us staging shared by assemble_probe184a.py,
assemble_probe184.py and gate_probe184.py.  OFFLINE ONLY: reads firmware/bose and tools/, writes
nothing into the repository (the payload generator writes to a temp dir).

Why a library: the two assemblers build the SAME cave and differ in the payload and the verdict
branch, and build/payload/make_narrow_payload.py (the 2026-10-10 builder) could stage ONLY a
30,000-byte file (`stage_plan` looked for `size == 30000`, T07 E19; parametrised in round 3, B02,
default output byte-identical, see B02-payload-staging-final-size.md).  Its ROFS builder, its
independent ROFS parser and its verifier are length-agnostic and are imported from there
unchanged; the staging arithmetic (the same rule, restated for any length and any start period) is
here, because make_narrow_payload.stage_plan stages the superseded packed-word layout (14 words per
period) while the images stage 28 BYTES per period.
Round 3 (B02) adds the variants '184-90k' and '184-58k' and the table PROBES (name -> variant, start).

THE UNIT RULE (T08, the correction this file encodes).  Every stock reader of SourceMap in vm.app
treats the mapped window as ONE BYTE PER 16-BIT WORD (fn_1edf9 0x1ee1b reads a big-endian 16-bit
value as (p[0] & 0xff) << 8 | (p[1] & 0xff); the USB receiver fn_185c3 tests p[0] == 3 as the HID
report id; docs/deep/prompt-audio-pump.md calls it proven; StreamRegionSource, its sibling, was
seen delivering one byte per word on hardware, FACTS N012), and every stock writer of a partition
sink counts SinkClaim / memmove / SinkFlush in BYTES (fn_18908: claim n, memmove n elements of a
one-byte-per-word table, flush n; fn_188ea: a 3-byte HID reply, claim 3, flush 3).  probe141 and
the 2026-10-10 184 plan claimed 14 and flushed 28 and read the map as packed little-endian words:
inconsistent in either model.  Here a period is 28 BYTES: the cave reads map elements 18..45 of
each 64-byte data_us period, claims 28, memmoves 28 elements, flushes 28.
"""
import contextlib
import hashlib
import importlib.util
import io
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'csr'))

OFFICIAL_DFU = os.path.join(ROOT, 'firmware/bose/minnow_3.0.3/Minnow_3.0.3_stack_plus_app.dfu')
DATA_US_FILE = os.path.join(ROOT, 'firmware/bose/extracted/internal_fs/data_us')

PERIOD_BYTES = 64            # one blind period of data_us (fsedit: content bytes 34..62 of 64)
FIRST_WORD = 9               # data_us words 9..22 are fully writable in every 32-word period (payload-184.md section 0)
FIRST_BYTE = 2 * FIRST_WORD  # = 18: bytes 18..45 of each 64-byte period
CHUNK = 28                   # payload bytes per period
DATA_US_SLACK = 219272       # fsedit SLACK_RANGE start inside data_us (body 0x35A54): last 256 B
NAME = 'brown.adpcm'

# ---- the pinned payload recipes (T07 section 5.7; the 184a file is a short slice-size of the same recipe)
VARIANTS = {
    '184': dict(bytes=60100, seed=63, peak=0.985,
                sha='ea70bed4021a0fa6f33ca3696633f2314485d6e7cea4f11a61ef05f22ef3ad13',
                why='T07 flat_15s: 15.025 s at 8000 Hz, 2,156 periods'),
    # ---- round 3 (B02, 2026-10-12): the J-D3 long alternative and the A-header-sparing alternative ----
    '184-90k': dict(bytes=90004, seed=16, peak=0.985,
                    sha='1006c1687304b5364956622a766fd40cf9445152bfac557332a2f290fe51c36f',
                    why='T07 flat_22s: 22.501 s at 8000 Hz, 3,224 periods; no start spares any id (every id garbled)'),
    '184-58k': dict(bytes=58700, seed=63, peak=0.985,
                    sha='a488348bceea2b88fa35512fe4e304de3546b631fc4f62628eb9a599239ffa17',
                    why='B02: the same recipe as flat_15s at 58,700 B = 28 x 2,106 - 268 (14.675 s), the LONGEST payload whose '
                        'span (start 1,320..3,426) spares the region-A header, the E6 array and the region-B tail; '
                        'NOT in T07 and not read by V02: its numbers are B02 section 3 (rms -11.51 dBFS, decoded peak 32,121, '
                        '0 clipped, seam step 927 = 0.23 x p99)'),
    '184a': dict(bytes=2532, seed=63, peak=0.985,
                 sha='c14fee1747b246059b7db43edf61b28b945dcf8df781685aa28a91fe0f0f729b',
                 why='the same recipe at 2,532 bytes: 28 x 100 - 268, so the ROFS is 100 periods'),
}


def sha(b):
    return hashlib.sha256(b).hexdigest()


# ---- the images this library feeds (round 3, B02).  name -> variant key, default start period, whether the
# ids are expected to survive (False: the 90k span garbles every id by construction, so the assembler PRINTS the
# survivor count instead of refusing).  'a' = the 184a verdict branch (find the file), else the 184 verdict.
SLACK_PERIODS = DATA_US_SLACK // PERIOD_BYTES      # 3,426: start + periods must not exceed this
PROBES = {
    'probe184a':     dict(a=True,  vkey='184a',    sp=1270, ids_survive=True),
    'probe184':      dict(a=False, vkey='184',     sp=1270, ids_survive=True),
    'probe184a_58k': dict(a=True,  vkey='184a',    sp=1320, ids_survive=True),
    'probe184_58k':  dict(a=False, vkey='184-58k', sp=1320, ids_survive=True),
    'probe184_90k':  dict(a=False, vkey='184-90k', sp=202,  ids_survive=False),
}


def periods_for(rofs_len):
    """gather iterations (28 bytes each) for a ROFS of `rofs_len` bytes"""
    return -(-rofs_len // CHUNK)


def max_start(rofs_len):
    """the last start period whose span still ends before fsedit's compensation slack"""
    return SLACK_PERIODS - periods_for(rofs_len)


def _load_mnp():
    p = os.path.join(ROOT, 'build', 'payload', 'make_narrow_payload.py')
    spec = importlib.util.spec_from_file_location('make_narrow_payload', p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def adpcm(variant):
    """The pinned payload bytes, regenerated by tools/brownnoise.py into a temp dir and checked
    against the sha256 recorded in T07 (a changed generator fails here, loudly)."""
    v = VARIANTS[variant]
    with tempfile.TemporaryDirectory(prefix='narrow184_adpcm_') as td:
        out = os.path.join(td, 'p.bin')
        cmd = [sys.executable, os.path.join(ROOT, 'tools', 'brownnoise.py'), '--rate', '8000',
               '--bytes', str(v['bytes']), '--gen', 'fft', '--loop', '--peak', str(v['peak']),
               '--seed', str(v['seed']), '--out', out]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=900)
        if r.returncode:
            raise SystemExit('brownnoise.py failed:\n' + r.stderr[-800:])
        data = open(out, 'rb').read()
    if sha(data) != v['sha'] or len(data) != v['bytes']:
        raise SystemExit('payload %s: sha256 %s != pinned %s (the generator changed; re-pin from T07 '
                         'only after reading it)' % (variant, sha(data), v['sha']))
    return data


def rofs(adpcm_bytes, name=NAME, verbose=False):
    """The ROFS of /<name> (flags 0x00) + the official 11-byte /ext_version, built by
    make_narrow_payload.build_rofs and verified by its verify_rofs (three parsers + FileFind
    mirror).  Returns (bytes, log_text)."""
    m = _load_mnp()
    Fs = m.load_fspack()
    out, ver = m.build_rofs(Fs, adpcm_bytes, name, True)
    buf = io.StringIO()
    m.FAILED.clear()
    with contextlib.redirect_stdout(buf):
        m.verify_rofs(Fs, out, adpcm_bytes, name, True, ver)
    log = buf.getvalue()
    if verbose:
        print(log)
    if m.FAILED:
        raise SystemExit('ROFS verification failed: %s\n%s' % (m.FAILED, log))
    return out, log


def stage(rofs_bytes, start_period):
    """Stage `rofs_bytes` into data_us: payload byte j of period p goes to data_us byte
    64 * (start_period + p) + 18 + j (= area byte area0 + that).  Returns a dict:
        edits      [(area_byte, value)]  for fsedit.build
        new_us     the edited data_us (bytes)
        padded     the bytes the cave will write to p2 (rofs + 0xFF padding to whole periods)
        periods    P
        area0      area byte of data_us byte 0
    Checks (SystemExit on failure): every edit byte is blind and in file data, no byte edited
    twice, the staged span ends before fsedit's compensation slack, and a byte-per-word replay of
    the cave's gather over the EDITED data_us reproduces `padded` exactly."""
    import fsedit
    m = _load_mnp()
    dfu = open(OFFICIAL_DFU, 'rb').read()
    ia = dfu.find(b'fsr_dfu1')
    P0 = m.parse_rofs(dfu, ia)
    du = next(e for e in P0['ents'] if e['name'] == 'data_us')
    area0 = 140 + 2 * du['doff']
    us = open(DATA_US_FILE, 'rb').read()
    assert dfu[ia + area0:ia + area0 + len(us)] == us and du['size'] == len(us) == 219528
    data = bytes(rofs_bytes)
    periods = -(-len(data) // CHUNK)
    padded = data + b'\xff' * (periods * CHUNK - len(data))
    end = (start_period + periods) * PERIOD_BYTES
    if end > DATA_US_SLACK:
        raise SystemExit('staged span ends at data_us byte %d, past the compensation slack %d'
                         % (end, DATA_US_SLACK))
    edits = []
    for p in range(periods):
        for j in range(CHUNK):
            edits.append((area0 + PERIOD_BYTES * (start_period + p) + FIRST_BYTE + j,
                          padded[p * CHUNK + j]))
    offs = [o for o, _ in edits]
    if len(set(offs)) != len(offs):
        raise SystemExit('an area byte is edited twice')
    body = fsedit.load_body()
    for o, v in edits:
        if not fsedit.blind(o):
            raise SystemExit('area byte %d is not blind' % o)
        if not fsedit.in_file_data(o - 140, body)[0]:
            raise SystemExit('area byte %d is not in file data' % o)
        body[o - 140] = v
    new_us = bytes(body[2 * du['doff']:2 * du['doff'] + du['size']])
    # byte-per-word replay of the cave's gather over the edited file
    got = bytearray()
    for p in range(periods):
        base = PERIOD_BYTES * (start_period + p) + FIRST_BYTE
        got += new_us[base:base + CHUNK]
    if bytes(got) != padded:
        raise SystemExit('gather replay != padded ROFS')
    changed = sum(1 for o, v in edits if dfu[ia + o] != v)
    return dict(edits=edits, new_us=new_us, padded=padded, periods=periods, area0=area0,
                start_period=start_period, span=(start_period * PERIOD_BYTES, end),
                changed=changed, rofs_len=len(data))


def promptmap_survivors(nbytes_rofs, start_period):
    """Ids whose modelled data_us read set holds no staged word (tools/promptmap.py, header
    spared or not as the start period decides).  Returns (sorted ids, header words hit, periods).
    MODEL ONLY: region A / the E6 array are unknown (promptmap section 8.3)."""
    import promptmap as pm
    rp = pm.Rphrases(pm.load_rphrases())
    du = pm.DataUs(pm.load_data_us())
    cat = pm.load_catalog()
    periods, words = pm.staged_words(nbytes_rofs, 'corrected', start_period=start_period)
    st = pm.Staged(words)
    hdr = st.hits_bytes(pm.B_BASE, pm.B_BASE + 60)
    rows = pm.verdicts_with(rp, du, cat, st)
    ok = [r['id'] for r in rows if r['units'] and r['hits'] == 0]
    return sorted(ok), hdr, periods


# ---- round 3 (V03, 2026-10-12): what the staged span covers BESIDES the 57 speech ids' read sets ----
# promptmap_survivors() above is a model of the unit read sets of the 57 ids and of the region-B header
# only. V03 showed the staged span also rewrites 12 of the 30 words of the REGION-A header (data_us bytes
# 84,384..84,443; the TTS DSP copies it into DM at every speech-session init and reads E1 and E4 at once,
# NowSpeakTTS_pm.disasm.txt:5589-5598), the E6 array, the region-B tail and region A itself. "The ids
# are audible after the write" is therefore a HYPOTHESIS with a counter-indication, not a model result.
# The byte ranges below are V03's (v4.py); they are data_us byte offsets.
DATA_US_REGIONS = (('region-B header', 18, 78),
                   ('E6 array', 0x12e0e, 0x13e4e),
                   ('region-B tail', 0x13e4e, 0x149a0),
                   ('region-A header', 0x149a0, 0x149a0 + 60),
                   ('region A (after the header)', 0x149a0 + 60, 219528))


def data_us_exposure(nbytes_rofs, start_period):
    """[(region name, staged words, words in the region)] for a payload of `nbytes_rofs` staged from
    `start_period`, by the corrected FIRST = 9 layout. Words are 16-bit data_us words. MODEL ONLY
    (tools/promptmap.py Staged.hits_bytes); what the DSP does with a changed region-A header is unknown."""
    import promptmap as pm
    periods, words = pm.staged_words(nbytes_rofs, 'corrected', start_period=start_period)
    st = pm.Staged(words)
    return [(name, st.hits_bytes(a, b), (b - a) // 2) for name, a, b in DATA_US_REGIONS]


def header_a_hits(nbytes_rofs, start_period):
    """Staged words inside the 30-word region-A header (0 is what a clean span needs)."""
    return next(h for name, h, _n in data_us_exposure(nbytes_rofs, start_period)
                if name == 'region-A header')


def first_clean_start(rofs_len):
    """lowest start period at which the model says all 57 speech ids survive (None if none up to max_start)"""
    hi = max_start(rofs_len)
    if hi < 0 or len(promptmap_survivors(rofs_len, hi)[0]) < 57:
        return None
    lo = 0
    while lo < hi:                      # survivor count is monotone in the start (reads sit at low offsets)
        mid = (lo + hi) // 2
        if len(promptmap_survivors(rofs_len, mid)[0]) == 57:
            hi = mid
        else:
            lo = mid + 1
    return lo


if __name__ == '__main__':
    for pn, pv in PROBES.items():
        v, sp = pv['vkey'], pv['sp']
        a = adpcm(v)
        r, _log = rofs(a)
        s = stage(r, sp)
        print('%-14s' % pn, end=' ')
        print('%-8s payload %6d B  ROFS %6d B  periods %5d  span data_us %d..%d  edits %d (%d differ)  max start %d'
              % (v, len(a), len(r), s['periods'], s['span'][0], s['span'][1], len(s['edits']), s['changed'],
                 max_start(len(r))))
        for _name, _h, _n in data_us_exposure(len(r), sp):
            print('        %-28s %6d of %6d words staged' % (_name, _h, _n))
