#!/usr/bin/env python3
"""probe184 payload: a minimal partition-2 ROFS holding ONE narrow (flags 0x00) brown-noise file,
its offline verification, and its staging plan into data_us blind windows.  OFFLINE ONLY.

Replaces, for probe184, build/payload/make_payload.py (which emits a flags-0x40 /brown.kap and
asserts it) and build/payload/stage_payload.py (whose window constants are 2 words off, see
"STAGING" below).  Neither old file is edited or overwritten: every output goes to
build/payload/narrow184/.

    python build/payload/make_narrow_payload.py                    # build + verify + plan
    python build/payload/make_narrow_payload.py --no-ext-version   # strictly ONE file in the ROFS
    python build/payload/make_narrow_payload.py --name b           # a shorter FileFind name
    python build/payload/make_narrow_payload.py --scratch DIR      # where the fsedit dry-run
                                                                   # and the cavesim mocks work
    python build/payload/make_narrow_payload.py --no-dry-run --no-world   # skip the slow steps

What it does (every step prints its evidence; any failed check exits 1):
  1. ADPCM  tools/brownnoise.py --rate 8000 --bytes 30000 --loop --peak 0.5 (generated if absent).
            Round 3 (B02, 2026-10-12): --bytes N / --gen / --seed / --expect-sha make the length a
            parameter (default 30000 = the output of 2026-10-10, byte-identical).  The T07 recipes:
              python build/payload/make_narrow_payload.py --bytes 60100 --gen fft --seed 63 --peak 0.985 \
                  --expect-sha ea70bed4021a0fa6f33ca3696633f2314485d6e7cea4f11a61ef05f22ef3ad13 --out SCRATCH
              python build/payload/make_narrow_payload.py --bytes 90004 --gen fft --seed 16 --peak 0.985 \
                  --expect-sha 1006c1687304b5364956622a766fd40cf9445152bfac557332a2f290fe51c36f --out SCRATCH
            NOTE: stage_plan here is the 2026-10-10 PACKED-WORD layout (14 little-endian words of the ROFS
            per 32-word period; see "STAGING" below and old_stage_misalignment()).  The built probe184 /
            probe184a images use the byte-per-word layout of build/hook/narrow184_lib.py (28 BYTES per
            period, unit rule), which is length-agnostic and carries the pinned recipes.  This file's
            ROFS builder and verifier are shared by both.  The "loop factorisation" line printed by
            stage_plan is the superseded imm8 OUTER x INNER design (informational; the built 184 uses
            one counter, so the only length constraint is start + periods <= 3,426).
  2. ROFS   csrfspack's own Fs.build() (the packer the old make_payload.py used), fresh tree:
            /               dir (flags 0x80)
              brown.adpcm   flags 0x00  <- the payload, FILE_INDEX 2
              ext_version   flags 0x00  <- the official 11-byte file (the updater's `v2` query)
            children sorted by name IGNORING CASE, as in BOTH official images (dirs first, then
            files, each group sorted).  The 128-byte RSA signature and 4-byte digest are the
            OFFICIAL ext image's and are STALE for this content (accepted: the write goes out
            under PartitionSetMessageDigest(3 = SKIP), proven by probe140).
  3. CHECK  re-parses the ROFS with an independent parser that follows tools/csr/dumpfs.py's
            arithmetic, cross-checks it against dumpfs.parse_fs itself and csrfspack.Fs, confirms
            the file is listed with flags 0x00 and the exact bytes, round-trips the packer, and
            runs a MIRROR of FileFind (adk/root/tools/include/firmware/file.h: relative to a
            start index, leading/trailing separators ignored, FILE_NONE = 0) and of
            StreamFileSource's acceptance rule (stream.h:312-318: narrow files only).  The mirror
            is validated against the two official images first.
  4. STAGE  the plan into data_us (rule below), the fsedit edit list, an in-memory replay of the
            cave's gather (read the 14 payload words per period through the source map) that must
            reproduce the ROFS byte for byte, and an fsedit dry-run that stops BEFORE any image is
            assembled (blind check, in-file-data check, XOR balance, digest oracle in a scratch
            dir, compensation solve, RSA-block invariant).
  5. WORLD  tools/cavesim_world.py's file model loaded with the file the ROFS parse yields,
            through the mock185b 'p2find' cave (FileFind(1, "<name>", n) from the root).

STAGING (the corrected rule; derived, then checked against the official image):
  data_us byte 0 sits at fs-AREA byte 600 (= 140 for 'iFel' + 2 * 230 words).  fsedit's blind
  rule is on content offset c = area - 136: bytes with 34 <= c % 64 <= 62.  A data_us word i
  (bytes 600+2i, 601+2i) is fully writable iff both bytes are blind: i % 32 in [9..22] = 14
  words per 32-word period (64 bytes).  stage_payload.py used 596+2i (a 4-byte slip: its "460"
  is a body offset from 'iFel' but it added 136, the header size to the DIGEST), which puts the
  same bytes 2 words early; it also set FIRST = 11.  Both are kept out of this file.
"""
import argparse
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'csr'))

OUT = os.path.join(HERE, 'narrow184')
OFFICIAL_EXT = os.path.join(ROOT, 'firmware/bose/extracted/ext_flash.bin')
OFFICIAL_DFU = os.path.join(ROOT, 'firmware/bose/minnow_3.0.3/Minnow_3.0.3_stack_plus_app.dfu')
DATA_US_FILE = os.path.join(ROOT, 'firmware/bose/extracted/internal_fs/data_us')

PERIOD = 32                  # data_us words per blind period (64 bytes)
DEFAULT_BYTES = 30000        # the 2026-10-10 plan payload; any length 28 P - 268 (P periods) is accepted since round 3
FAILED = []


def rel(p):
    return os.path.relpath(p, ROOT).replace(os.sep, '/')


def sha(b):
    return hashlib.sha256(b).hexdigest()


def check(cond, msg):
    print('  [%s] %s' % ('ok' if cond else 'FAIL', msg))
    if not cond:
        FAILED.append(msg)
    return cond


def pdp(x):
    return ((x >> 16) & 0xFFFF) | ((x & 0xFFFF) << 16)


# ---------------------------------------------------------------- csrfspack (runs main() at import)
def load_fspack():
    code = open(os.path.join(ROOT, 'tools', 'csr', 'csrfspack.py'), encoding='utf-8').read()
    g = {'__name__': 'csrfspack_mod'}
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):          # it prints its usage text on import
        try:
            exec(compile(code, 'csrfspack.py', 'exec'), g)
        except SystemExit:
            pass
    return g['Fs']


# ---------------------------------------------------------------- the independent ROFS parser
def parse_rofs(d, start):
    """Same arithmetic as tools/csr/dumpfs.py:parse_fs, returning entries (no files written).
    d[start:start+8] == b'fsr_dfu1'.  Entry i has FILE_INDEX i + 1."""
    assert d[start:start + 8] == b'fsr_dfu1'
    m = start + 8 + 128 + 4
    assert d[m:m + 4] == b'iFel'
    siw = pdp(struct.unpack_from('<I', d, m + 4)[0])
    nfiles = struct.unpack_from('<H', d, m + 8)[0]
    ents = []
    for n in range(nfiles):
        fno, doff, sz = [pdp(x) for x in struct.unpack_from('<III', d, m + 10 + 12 * n)]
        noff, flags = fno & 0xFFFFFF, fno >> 24
        name = ''
        if noff:
            p = m + noff * 2
            ln = struct.unpack_from('<H', d, p)[0]
            name = d[p + 2:p + 2 + ln * 2].decode('utf-16-le')
        e = dict(idx=n, findex=n + 1, flags=flags, isdir=bool(flags & 0x80), name=name,
                 doff=doff, size=sz, noff=noff)
        if not e['isdir']:
            e['data'] = bytes(d[m + doff * 2:m + doff * 2 + sz])
        ents.append(e)
    return dict(m=m, siw=siw, ents=ents)


# ---------------------------------------------------------------- FileFind / StreamFileSource mirror
FILE_NONE, FILE_ROOT = 0, 1


def file_find(ents, start, name, length=None):
    """adk .../firmware/file.h: 'index of a named file or directory, relative to the starting
    directory ... name possibly including a path ... leading and trailing directory separators
    are ignored ... FILE_NONE if no such item'.  Children of directory e are FILE_INDEX
    e.doff .. e.doff + e.size - 1 (csrfspack: 'data_off = first child index + 1' in 0-based
    terms = the first child's 1-based FILE_INDEX)."""
    if length is not None:
        name = name[:length]
    parts = [p for p in name.strip('/').split('/') if p]
    cur = start
    if not parts:
        return cur
    for part in parts:
        if not 1 <= cur <= len(ents):
            return FILE_NONE
        e = ents[cur - 1]
        if not e['isdir']:
            return FILE_NONE
        nxt = FILE_NONE
        for fi in range(e['doff'], e['doff'] + e['size']):
            if 1 <= fi <= len(ents) and ents[fi - 1]['name'] == part:
                nxt = fi
                break
        if nxt == FILE_NONE:
            return FILE_NONE
        cur = nxt
    return cur


def file_type(ents, fi):
    if not 1 <= fi <= len(ents):
        return 'error'
    e = ents[fi - 1]
    if e['isdir']:
        return 'directory'
    return 'narrow' if e['flags'] == 0x00 else 'wide'     # 0x40 = code/wide (every .kap)


def stream_file_source_accepts(ents, fi):
    """stream.h:312-318: 'return 0 if index is FILE_NONE, or does not correspond to a narrow file'."""
    return fi != FILE_NONE and file_type(ents, fi) == 'narrow'


# ---------------------------------------------------------------- 1. the ADPCM
def get_adpcm(path, peak, regenerate, nbytes=DEFAULT_BYTES, gen=None, seed=None):
    n = nbytes
    if regenerate or not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cmd = [sys.executable, os.path.join(ROOT, 'tools', 'brownnoise.py'), '--rate', '8000',
               '--bytes', str(n), '--loop', '--peak', str(peak), '--out', path]
        if gen is not None:                     # round 3 (B02): the T07 recipes use --gen fft --seed N
            cmd[cmd.index('--out'):cmd.index('--out')] = ['--gen', gen]
        if seed is not None:
            cmd[cmd.index('--out'):cmd.index('--out')] = ['--seed', str(seed)]
        print('  generating:', ' '.join(os.path.relpath(c, ROOT) if os.path.isabs(c) else c
                                         for c in cmd[1:]))
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=600)
        print('\n'.join('    ' + l for l in r.stdout.splitlines()))
        if r.returncode:
            raise SystemExit('brownnoise.py failed:\n' + r.stderr)
    return open(path, 'rb').read()


# ---------------------------------------------------------------- 2. build the ROFS
def build_rofs(Fs, adpcm, name, with_ext_version):
    official = Fs(open(OFFICIAL_EXT, 'rb').read())
    ver = next(e for e in official.entries if e['name'] == 'ext_version')
    files = [(name, adpcm)]
    if with_ext_version:
        files.append(('ext_version', ver['data']))
    files.sort(key=lambda t: t[0].lower())               # name order IGNORING CASE, as the official images
    fs = official                                        # keeps signature / digest (STALE, accepted)
    ents = [dict(i=0, flags=0x80, noff=0, name='', doff=2, size=len(files), isdir=True)]
    for k, (nm, data) in enumerate(files, start=1):
        # noff / doff are ORDER placeholders: Fs.build() re-derives the real word offsets
        ents.append(dict(i=k, flags=0x00, noff=k, name=nm, doff=k, size=len(data), isdir=False,
                         data=data))
    fs.entries = ents
    fs.siw = 0               # smaller than the layout -> Fs.build() takes its 'we outgrew the
    #                          original' branch: 6 slack words, even total (the official images'
    #                          size_in_words are both even)
    out = fs.build()
    return out, ver['data']


# ---------------------------------------------------------------- 3. verify the ROFS
def verify_rofs(Fs, out, adpcm, name, with_ext_version, ver_data):
    print('\n== 3. ROFS checks')
    import dumpfs
    # --- the mirror is validated on the two OFFICIAL images first
    off_ext = parse_rofs(open(OFFICIAL_EXT, 'rb').read(), 0)['ents']
    dfu = open(OFFICIAL_DFU, 'rb').read()
    off_main = parse_rofs(dfu, dfu.find(b'fsr_dfu1'))['ents']
    nst = file_find(off_main, FILE_ROOT, 'NowSpeakTTS', 11)
    du = file_find(off_main, nst, 'data_us', 7)
    check(nst != 0 and du != 0 and du == file_find(off_main, FILE_ROOT, 'NowSpeakTTS/data_us')
          == file_find(off_main, FILE_ROOT, '/NowSpeakTTS/data_us/'),
          'mirror on the official main fs: FileFind(1,"NowSpeakTTS",11)=%d then (dir,"data_us",7)=%d, '
          'same as the path form with and without separators' % (nst, du))
    check(stream_file_source_accepts(off_main, du)
          and stream_file_source_accepts(off_main, file_find(off_main, FILE_ROOT, 'tts/rphrases_us'))
          and not stream_file_source_accepts(off_main, file_find(off_main, FILE_ROOT, 'vm.app'))
          and not stream_file_source_accepts(off_main, nst),
          'mirror on the official main fs: data_us and rphrases_us (flags 0x00) accepted; '
          'vm.app (0x40) and a directory refused')
    check(file_find(off_main, FILE_ROOT, 'NoSuchFile') == 0
          and file_find(off_ext, FILE_ROOT, 'ext_version') != 0,
          'mirror: FILE_NONE for a missing name; ext_version found in the official ext image')
    for label, ents in (('main fs', off_main), ('ext image', off_ext)):
        ok = True
        for e in ents:
            if e['isdir']:
                kids = ents[e['doff'] - 1:e['doff'] - 1 + e['size']]
                dirs = [k['name'] for k in kids if k['isdir']]
                fls = [k['name'] for k in kids if not k['isdir']]
                ok &= (dirs + fls == [k['name'] for k in kids]) \
                    and dirs == sorted(dirs, key=str.lower) and fls == sorted(fls, key=str.lower)
        check(ok, 'official %s: every directory lists dirs first, then files, each sorted by '
              'name IGNORING CASE (NowSpeakTTS.kap sits after data_us) -- the order this builder '
              'reproduces' % label)

    # --- structure
    check(out[:8] == b'fsr_dfu1' and out[0x8C:0x90] == b'iFel', "magic 'fsr_dfu1' ... 'iFel' at 0x8C")
    P = parse_rofs(out, 0)
    ents = P['ents']
    siw = P['siw']
    check(len(out) == 0x8C + siw * 2, 'length %d = 140 + size_in_words %d * 2' % (len(out), siw))
    check(siw % 2 == 0, 'size_in_words %d is even (both official images are even; the old '
          'brown_fs.bin was 16437, odd)' % siw)
    trailer = out[-8:]
    check(pdp(struct.unpack_from('<I', trailer, 0)[0]) == siw and trailer[4:] == b'iFel',
          "trailer = size_in_words copy + 'iFel'")
    x = 0
    for i in range(0x8C, len(out), 2):
        x ^= struct.unpack_from('<H', out, i)[0]
    check(x == 0, '16-bit XOR over the body = 0x%04X' % x)
    check(out[8:0x88] == Fs(open(OFFICIAL_EXT, 'rb').read()).signature
          and out[0x88:0x8C] == Fs(open(OFFICIAL_EXT, 'rb').read()).digest,
          'signature + digest are the official ext image copies (STALE for this content, by design)')

    # --- the tree
    want = 3 if with_ext_version else 2
    check(len(ents) == want and ents[0]['isdir'] and ents[0]['flags'] == 0x80,
          '%d entries: root dir (0x80) + %d file(s)' % (len(ents), want - 1))
    files = [e for e in ents if not e['isdir']]
    kids = ents[ents[0]['doff'] - 1:ents[0]['doff'] - 1 + ents[0]['size']]
    check([k['name'] for k in kids] == sorted((k['name'] for k in kids), key=str.lower)
          and len(kids) == want - 1,
          'root children %s in case-insensitive name order' % [k['name'] for k in kids])
    nar = [e for e in files if e['name'] == name]
    check(len(nar) == 1 and nar[0]['flags'] == 0x00,
          'listed: %r flags=0x%02X size=%d' % (name, nar[0]['flags'], nar[0]['size']))
    check(nar[0]['data'] == adpcm and nar[0]['size'] == len(adpcm),
          'file bytes == the ADPCM exactly (%d bytes, sha256 %s)' % (len(adpcm), sha(nar[0]['data'])))
    check(all(e['flags'] == 0x00 for e in files), 'every file in the image is narrow (flags 0x00)')
    if with_ext_version:
        ev = next(e for e in files if e['name'] == 'ext_version')
        check(ev['data'] == ver_data, 'ext_version == the official 11 bytes %r' % ver_data)
    for e in files:
        check(e['doff'] % 2 == 0, 'data of %r starts on a dword boundary (word %d)' % (e['name'], e['doff']))

    # --- dumpfs.parse_fs (the actual tool) agrees entry for entry
    tmp = tempfile.mkdtemp(prefix='narrow_dumpfs_')
    try:
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            dents = dumpfs.parse_fs(out, 0, tmp)
        listing = buf.getvalue().strip().splitlines()
        same = [(d['flags'], d['name'], d['doff'], d['size']) for d in dents] == \
               [(e['flags'], e['name'], e['doff'], e['size']) for e in ents]
        check(same, 'dumpfs.parse_fs returns the same table as the independent parser')
        got = open(os.path.join(tmp, name), 'rb').read()
        check(got == adpcm, 'dumpfs.parse_fs extracted %r: %d bytes, identical' % (name, len(got)))
        for l in listing:
            print('      dumpfs: ' + l.strip().replace(tmp, '<tmp>'))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- csrfspack agrees, and the packer round-trips
    fp = Fs(out)
    paths = fp.paths()
    check(paths['/' + name]['flags'] == 0x00 and paths['/' + name]['data'] == adpcm,
          'csrfspack.Fs(...).paths() lists /%s flags=0x00 with the exact bytes' % name)
    check(Fs(out).build() == out, 'csrfspack round trip: BYTE-IDENTICAL')

    # --- FileFind / StreamFileSource mirror on the payload ROFS
    print('  FileFind mirror (FILE_INDEX = table position + 1; FILE_ROOT = %d):' % FILE_ROOT)
    fi = file_find(ents, FILE_ROOT, name, len(name))
    check(fi != 0 and ents[fi - 1]['name'] == name,
          'FileFind(FILE_ROOT, %r, %d) = %d' % (name, len(name), fi))
    check(file_type(ents, fi) == 'narrow' and stream_file_source_accepts(ents, fi),
          'FileType = narrow; StreamFileSource(%d) would accept (flags 0x00)' % fi)
    check(file_find(ents, FILE_ROOT, '/' + name + '/') == fi, 'leading/trailing separators ignored')
    for bad in (name[:-1], name + 'x', 'tts/' + name):
        check(file_find(ents, FILE_ROOT, bad) == 0, 'FileFind(%r) = FILE_NONE' % bad)
    print('      (case rule NOT asserted: the official siblings sort ignoring case, so the firmware '
          'may compare ignoring case; the name used is the same lower-case string on both sides)')
    return ents, fi


# ---------------------------------------------------------------- 4. staging
def blind(area):                       # fsedit.blind(), restated so the rule is visible here
    c = area - 136
    return 34 <= c % 64 <= 62


def stage_plan(rofs, start_period, pad_word=0xFFFF, payload_len=DEFAULT_BYTES, name='brown.adpcm'):
    import fsedit
    print('\n== 4. staging plan (data_us blind windows)')
    dfu = open(OFFICIAL_DFU, 'rb').read()
    ia = dfu.find(b'fsr_dfu1')
    P = parse_rofs(dfu, ia)
    du = next(e for e in P['ents'] if e['name'] == 'data_us')
    area0 = 140 + 2 * du['doff']
    us = open(DATA_US_FILE, 'rb').read()
    check(dfu[ia + area0:ia + area0 + len(us)] == us and du['size'] == len(us),
          'data_us byte 0 is at fs-area byte %d (140 + 2*%d), %d bytes, identical to '
          'firmware/bose/extracted/internal_fs/data_us' % (area0, du['doff'], len(us)))
    win = [i for i in range(PERIOD) if blind(area0 + 2 * i) and blind(area0 + 2 * i + 1)]
    check(win == list(range(win[0], win[0] + len(win))) and len(win) == 14,
          'fully-writable words per 32-word period: i %% 32 in [%d..%d] (%d words, 28 bytes of 64)'
          % (win[0], win[-1], len(win)))
    first, last, per = win[0], win[-1], len(win)
    word_area = [area0 + 2 * (PERIOD * 3 + first), area0 + 2 * (PERIOD * 3 + last) + 1]
    print('      e.g. period 3: area bytes %d..%d (content offsets %d..%d, mod 64 = %d..%d)'
          % (word_area[0], word_area[1], word_area[0] - 136, word_area[1] - 136,
             (word_area[0] - 136) % 64, (word_area[1] - 136) % 64))

    data = bytes(rofs) + (b'\x00' if len(rofs) % 2 else b'')
    words = [data[i] | (data[i + 1] << 8) for i in range(0, len(data), 2)]
    periods = -(-len(words) // per)
    pad = periods * per - len(words)
    words += [pad_word] * pad
    check(start_period + periods <= len(us) // 64, '%d periods (+ start %d) fit in data_us (%d)'
          % (periods, start_period, len(us) // 64))
    # round 3 (B02): fsedit's digest compensation owns data_us bytes 219,272.. (narrow184_lib.DATA_US_SLACK);
    # a staged span must end before them. Silent when it holds (the default output is unchanged).
    if (start_period + periods) * 64 > 219272:
        check(False, 'staged span ends at data_us byte %d, past the compensation slack 219272 '
              '(start + periods must be <= 3426)' % ((start_period + periods) * 64))
    staged = []                                      # (data_us word index, value)
    for p in range(periods):
        for k in range(per):
            staged.append((PERIOD * (start_period + p) + first + k, words[p * per + k]))
    edits = []
    for i, v in staged:
        a = area0 + 2 * i
        edits.append((a, v & 0xFF))
        edits.append((a + 1, (v >> 8) & 0xFF))
    check(len({o for o, _ in edits}) == len(edits), 'no area byte is edited twice')
    check(all(blind(o) for o, _ in edits), 'every edit byte is blind (content offset 34..62 of its block)')

    # --- the cave's gather, replayed in memory against the edited fs body
    body = fsedit.load_body()
    for o, v in edits:
        body[o - 140] = v
    new_us = bytes(body[2 * du['doff']:2 * du['doff'] + du['size']])
    ok_in = all(fsedit.in_file_data(o - 140, body)[0] for o, _ in edits)
    check(ok_in, 'fsedit.in_file_data: every edit lies in file data (not table / names / trailer)')
    gathered = []
    for p in range(periods):
        base = PERIOD * (start_period + p) + first
        for k in range(per):
            w = new_us[2 * (base + k)] | (new_us[2 * (base + k) + 1] << 8)
            gathered.append(w)
    gbytes = b''.join(struct.pack('<H', w) for w in gathered)
    check(gbytes[:len(data)] == data, 'cave gather replay (words %d..%d of each %d-word period of '
          'the EDITED data_us, little-endian) == the ROFS, %d bytes, identical'
          % (first, last, PERIOD, len(data)))
    check(gbytes[len(data):] == b'\xff\xff' * pad, 'the %d pad word(s) after the trailer read 0x%04X'
          % (pad, pad_word))
    G = parse_rofs(gbytes, 0)
    gf = next(e for e in G['ents'] if not e['isdir'] and e['size'] == payload_len and e['name'] == name)
    check(gf['flags'] == 0x00, 'the gathered stream parses as a ROFS with the narrow file intact')
    changed = sum(1 for o, v in edits if dfu[ia + o] != v)
    span = (start_period * 64, (start_period + periods) * 64)
    print('      periods              : %d (%d payload words + %d pad)' % (periods, len(data) // 2, pad))
    print('      staged words / bytes : %d / %d  (%d of those bytes differ from the stock bytes)'
          % (len(staged), len(edits), changed))
    print('      data_us bytes touched: %d..%d of %d (%.1f %% of the file are in the staged span)'
          % (span[0], span[1], len(us), 100.0 * (span[1] - span[0]) / len(us)))
    print('      source consumed      : %d x SourceDrop(src, 64) = %d bytes' % (periods, periods * 64))
    print('      p2 write size        : %d x SinkFlush(28) = %d bytes (%d words); the ROFS itself '
          'is %d bytes' % (periods, periods * 28, periods * 14, len(data)))
    facts = []
    for inner in range(255, 1, -1):
        if periods % inner == 0 and periods // inner <= 255:
            facts.append((periods // inner, inner))
    if facts:
        print('      loop factorisation  : exact OUTER x INNER = %s (imm8 counters)' % facts[:4])
    else:
        best = None
        for total in range(periods, periods + 40):
            for inner in range(255, 1, -1):
                if total % inner == 0 and total // inner <= 255:
                    best = (total, total // inner, inner)
                    break
            if best:
                break
        print('      loop factorisation  : %d is not a product of two imm8 counters; nearest '
              'padded total %d = %d x %d (adds %d periods of pad; each is 28 more bytes written '
              'to p2 and 64 more data_us bytes staged)' % ((periods,) + best + (best[0] - periods,)))
    return dict(area0=area0, first=first, last=last, per=per, periods=periods, pad=pad,
                words=words, edits=edits, staged=staged, start_period=start_period,
                bytes_written=periods * 28, changed=changed, span=span, du_size=len(us),
                data=data)


def old_stage_misalignment():
    """Evidence for the 2-word slip in build/payload/stage_payload.py, from the committed
    probe141 image (read only)."""
    print('\n== 4b. the old staging (stage_payload.py / probe141) against the corrected rule')
    p141 = os.path.join(ROOT, 'build/hook/probe141_brown.dfu')
    old = os.path.join(HERE, 'brown_fs.bin')
    if not (os.path.exists(p141) and os.path.exists(old)):
        print('  (probe141 image or brown_fs.bin absent: skipped)')
        return
    o = open(OFFICIAL_DFU, 'rb').read()
    p = open(p141, 'rb').read()
    io_, ip = o.find(b'fsr_dfu1'), p.find(b'fsr_dfu1')
    diff = [i for i in range(0, 0x8C + 487514 * 2) if o[io_ + i] != p[ip + i]]
    d0 = diff[0]
    fsb = open(old, 'rb').read()
    # the gather exactly as assemble_probe141.py does it: map = data_us words, start at word 11
    area0 = 600
    us = p[ip + area0:ip + area0 + 219528]
    per0 = us[2 * 11:2 * 11 + 28]
    print('  first edited area byte in probe141_brown.dfu          : %d  (data_us word %d)'
          % (d0, (d0 - area0) // 2))
    print('  probe141 cave FIRST (assemble_probe141.py:96)          : 11  (area byte %d)' % (area0 + 22))
    print('  ROFS bytes 0..27 (brown_fs.bin)                       : %s' % fsb[:28].hex())
    print('  what a gather at word 11 reads from that image          : %s' % per0.hex())
    print('  payload words the cave gets: ROFS words 2..13 then 2 STOCK words -> shifted by 4 bytes: %s'
          % ('YES' if per0[:24] == fsb[4:28] and per0[24:] != fsb[28:32] else 'no'))
    print('  (arithmetic on the committed image: proven.  Whether SourceMap\'s word i is file '
          'bytes 2i,2i+1 on the device is exactly what probe182 settles: hypothesis.)')


def fsedit_dry_run(edits, scratch):
    """fsedit.build() up to (not including) the csrpack image assembly, with its work dir
    redirected to a scratch folder.  Nothing under build/ is written."""
    print('\n== 4c. fsedit dry-run (no image assembled; work dir %s)' % scratch)
    import fsedit
    fsedit.WORK = scratch
    os.makedirs(scratch, exist_ok=True)
    try:
        body = fsedit.load_body()
        edit_bytes = set()
        for off, val in edits:
            fsedit.check(fsedit.blind(off), 'blind')
            ok, where = fsedit.in_file_data(off - 140, body)
            fsedit.check(ok, where)
            body[off - 140] = val
            edit_bytes.add(off - 140)
        pool = json.load(open(fsedit.POOL))
        words = fsedit.blind_pool_words(pool, body, edit_bytes)
        V = fsedit.body_xor(body)
        bal = []
        if V:
            bal = fsedit.flips_for_value(V, words, body, edit_bytes)
            for o, m in bal:
                body[o] ^= m
            used = {o // 2 for o, m in bal}
            words = [p for p in words if p not in used]
        print('      %d edit bytes accepted by fsedit.blind + in_file_data; XOR residue 0x%04X '
              '-> %d balance flips at pool words' % (len(edits), V, len(bal)))
        d_new = fsedit.oracle_digest(body)
        delta = fsedit.DIGEST_OFFICIAL ^ d_new
        comp = fsedit.solve_compensation(delta, pool, words) if delta else []
        for p in comp:
            off = p * 2
            fsedit.check(fsedit.blind(off + 140), 'comp word not blind')
            fsedit.check(off not in edit_bytes, 'comp word collides with a chosen edit')
            body[off] ^= 1
        print('      digest delta 0x%08X -> %d compensation one-bit flips (pool ranks fine)'
              % (delta, len(comp)))
        fsedit.check(fsedit.oracle_digest(body) == fsedit.DIGEST_OFFICIAL, 'final digest mismatch')
        official = fsedit.load_body()
        dg = struct.pack('<I', fsedit.DIGEST_OFFICIAL)
        fsedit.check(fsedit.fs_block(dg + bytes(body)) == fsedit.fs_block(dg + bytes(official)),
                     'RSA block changed')
        fsedit.check(fsedit.body_xor(body) == 0, 'body XOR broken')
        intact = all(body[o - 140] == v for o, v in edits)
        check(intact, 'after balance + compensation every staged byte still holds its payload value')
        check(True, 'digest byte-identical to the official 0x%08X, RSA block unchanged, body XOR 0 '
              '(everything fsedit.build() verifies before csrpack)' % fsedit.DIGEST_OFFICIAL)
        return dict(balance=len(bal), comp=len(comp), delta=delta)
    except SystemExit as e:
        check(False, 'fsedit dry-run stopped: %s' % e)
        return None


# ---------------------------------------------------------------- 5. cavesim world
def world_check(fbytes, name, scratch):
    print('\n== 5. cavesim_world file model (mock185b "p2find" cave, FileFind(1,%r,%d) from the root)'
          % (name, len(name)))
    import cavesim_selftest as st
    os.makedirs(scratch, exist_ok=True)
    words = os.path.join(scratch, 'mock_p2find_words.json')
    if name != 'brown.adpcm':
        print('  (mock p2find hard-codes "brown.adpcm"; skipped for name %r)' % name)
        return
    st.build('p2find', words)
    fpath = os.path.join(scratch, 'p2_file_from_rofs_parse.bin')
    open(fpath, 'wb').write(fbytes)
    cases = [
        ('p2 written + automount: found from the root', ['--p2-preloaded', '--p2-automount'], 'spoken=2a'),
        ('p2 written, no automount: root miss, cave mount, found', ['--p2-preloaded'], 'spoken=2b'),
        ('p2 not written: missing', [], 'spoken=13'),
    ]
    for title, extra, expect in cases:
        cmd = [sys.executable, os.path.join(ROOT, 'tools', 'cavesim.py'), words, '--entry', '0x3E21D',
               '--al', '4004', '--once', '--fs-add', '%s=@%s:p2' % (name, os.path.relpath(fpath, ROOT).replace(os.sep, '/'))] + extra + \
              ['--expect', expect, '--brief']
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=600)
        check(r.returncode == 0, '%s -> %s' % (title, expect))
        if r.returncode:
            print('\n'.join('      ' + l for l in (r.stdout + r.stderr).splitlines()[-8:]))
    print('      (the model gets the %d bytes the ROFS PARSE yielded for %r, file size %d)'
          % (len(fbytes), name, len(fbytes)))


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--bytes', type=int, default=DEFAULT_BYTES,
                    help='payload length in bytes (default 30000; the T07 recipes are 60100 and 90004)')
    ap.add_argument('--adpcm', default=None,
                    help='payload file (default narrow184/brown_8000_<bytes>.bin, generated if absent)')
    ap.add_argument('--gen', default=None, help='tools/brownnoise.py --gen (T07 recipes: fft); default: its default')
    ap.add_argument('--seed', type=int, default=None, help='tools/brownnoise.py --seed (T07: 63 for 60100, 16 for 90004)')
    ap.add_argument('--expect-sha', default=None, help='fail unless the payload has this sha256')
    ap.add_argument('--peak', type=float, default=0.5)
    ap.add_argument('--regenerate', action='store_true')
    ap.add_argument('--name', default='brown.adpcm', help='the file name FileFind will be given')
    ap.add_argument('--no-ext-version', action='store_true', help='strictly ONE file in the ROFS')
    ap.add_argument('--start-period', type=int, default=0, help='first data_us period staged')
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--scratch', default=None)
    ap.add_argument('--no-dry-run', action='store_true')
    ap.add_argument('--no-world', action='store_true')
    ap.add_argument('--no-edits-module', action='store_true')
    a = ap.parse_args()
    if a.adpcm is None:
        a.adpcm = os.path.join(OUT, 'brown_8000_%d.bin' % a.bytes)
    scratch = a.scratch or tempfile.mkdtemp(prefix='narrow184_')
    os.makedirs(a.out, exist_ok=True)
    tag = '' if not a.no_ext_version else '_only'

    print('== 1. ADPCM')
    adpcm = get_adpcm(a.adpcm, a.peak, a.regenerate, a.bytes, a.gen, a.seed)
    check(len(adpcm) == a.bytes, '%s: %d bytes = %.2f s at 8000 Hz (2 samples/byte)'
          % (os.path.relpath(a.adpcm, ROOT), len(adpcm), len(adpcm) * 2 / 8000.0))
    print('      sha256 %s' % sha(adpcm))
    if a.expect_sha:
        check(sha(adpcm) == a.expect_sha, 'payload sha256 equals the pinned %s' % a.expect_sha)

    print('\n== 2. ROFS')
    Fs = load_fspack()
    out, ver = build_rofs(Fs, adpcm, a.name, not a.no_ext_version)
    rofs_path = os.path.join(a.out, 'narrow_fs%s.bin' % tag)
    open(rofs_path, 'wb').write(out)
    print('  %s: %d bytes, sha256 %s' % (os.path.relpath(rofs_path, ROOT), len(out), sha(out)))

    ents, fi = verify_rofs(Fs, out, adpcm, a.name, not a.no_ext_version, ver)
    fbytes = next(e for e in ents if e['name'] == a.name)['data']

    plan = stage_plan(out, a.start_period, payload_len=len(adpcm), name=a.name)
    old_stage_misalignment()
    dry = None
    if not a.no_dry_run:
        dry = fsedit_dry_run(plan['edits'], os.path.join(scratch, 'fsedit'))
    if not a.no_world:
        world_check(fbytes, a.name, scratch)

    # ---- outputs for the assembler
    json.dump(plan['words'], open(os.path.join(a.out, 'narrow_staged_words%s.json' % tag), 'w'))
    if not a.no_edits_module:
        mp = os.path.join(a.out, 'narrow_edits%s.py' % tag)
        with open(mp, 'w', encoding='utf-8') as f:
            f.write('# generated by make_narrow_payload.py -- fsedit AREA-byte edits for the probe184\n'
                    '# staged payload.  %d edits, data_us words %d..%d of period %d.. (word i of data_us '
                    'is area bytes 600+2i, 601+2i).\n'
                    % (len(plan['edits']), plan['staged'][0][0], plan['staged'][-1][0],
                       plan['start_period']))
            f.write('EDITS = [\n')
            for o, v in plan['edits']:
                f.write('  (0x%x, 0x%x),\n' % (o, v))
            f.write(']\n')
    manifest = dict(
        adpcm=dict(path=rel(a.adpcm), bytes=len(adpcm), sha256=sha(adpcm),
                   rate=8000, seconds=len(adpcm) * 2 / 8000.0, peak=a.peak),
        rofs=dict(path=rel(rofs_path), bytes=len(out), sha256=sha(out),
                  name=a.name, file_index=fi, ext_version=not a.no_ext_version),
        staging=dict(area0=plan['area0'], first_word=plan['first'], last_word=plan['last'],
                     words_per_period=plan['per'], period_words=PERIOD, periods=plan['periods'],
                     pad_words=plan['pad'], start_period=plan['start_period'],
                     edit_bytes=len(plan['edits']), bytes_differing_from_stock=plan['changed'],
                     data_us_span=plan['span'], p2_write_bytes=plan['bytes_written'],
                     staged_words_sha256=sha(json.dumps(plan['words']).encode())),
        fsedit_dry_run=dry)
    json.dump(manifest, open(os.path.join(a.out, 'manifest%s.json' % tag), 'w'), indent=1)
    print('\nwrote', os.path.relpath(a.out, ROOT), sorted(os.listdir(a.out)))
    print('\n%s' % ('ALL CHECKS PASSED' if not FAILED else '*** %d CHECK(S) FAILED: %s' % (len(FAILED), FAILED)))
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
