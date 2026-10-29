#!/usr/bin/env python3
"""promptmap: spoken request id -> rphrases_us payload -> data_us bytes, and what a staged payload garbles.

Offline only (reads firmware/bose/extracted/internal_fs/{rphrases_us,data_us} and the catalog; touches no
device).  Written for README F5 (probe 184 stages its payload INTO data_us).  Findings, with the evidence
each rests on (full write-up: docs/deep/offline-2026-10-10/promptmap.md):

1. THE PREMISE IS WRONG.  rphrases_us is NOT an (offset, length) directory of data_us chunks (that was the
   withdrawn PCM reading).  It is the phoneme script of the NowSpeakTTS engine: a count word + 147 u16 word offsets, then
   one payload per phrase = [count word 0x80NN][NN unit bytes][pad][NN prosody bytes][NN more if the 0x4000
   / 0x8000 flag bits are set].  Unit bytes are phoneme codes 1..43 plus 0xff (word break).  The VM reads it
   in fn_1ee80 (0x1ee80): word idx+1 of the table is the payload offset, so REQUEST ID N == table entry
   N+1 (proven by the code and by the 7 empty ids landing exactly on the 7 empty stubs).  There is no
   data_us (offset, length) per id; the DSP (NowSpeakTTS.kap) reads data_us itself, per unit.

2. data_us IS A TWO-REGION VOICE DATABASE.  File header: word 0 = 2 regions, then region base words
   (idx0 = 9, idx1 = 0xa4d0).  Region B (units) starts at word 9 = byte 18 and carries a 15-entry header
   E0..E14 of 32-bit (hi,lo) word pairs; E2 = 268 is the phoneme-table offset, E4 x E5 = 80 x 52 is the
   E6 array.  The DSP copies these 15 entries into DM at init (call 0x1605, r1 = 15) and indexes the
   phoneme table with them (0xde8: r0 = unit*2 + M[0xff3ff3]).  Table entry for unit u is at byte 18 + E2 +
   2u (physical entry u-1).  Each entry points at a GROUP of 5 records (flag|count word 0x8005); a record
   lists 27-word frame pointers (relative to byte 18); a 5-byte descriptor row precedes each group.
   Region A (bytes 0x149a0..EOF, 64 percent of the file) is a second structure, not decoded here.

3. THE STAGED WINDOW STARTS INSIDE THE REGION-B HEADER.  stage_payload.py NUMBERS the window i % 32 in
   11..24 ('old'), but the fsedit edits it emits (and the committed build/hook/probe141_brown.dfu) land on
   words 9..22 ('corrected', payload-184.md section 0; the selftest reads the DFU).  Both cover the header
   entries including E2, the phoneme-table base the DSP uses for every unit; the physical one overwrites
   E0..E6.  So no unit-based prompt can be certified untouched at ANY payload size.

Model limits (hypothesis): which bytes the DSP actually reads per unit (all of the group span and all 27
words of each frame are assumed read: an over-approximation), and that region A / the E6 array are read
for some prompts (unknown, reported separately as UNKNOWN, never as "untouched").

Usage:
    python tools/promptmap.py --selftest
    python tools/promptmap.py --table                 # id -> rphrases range, units, data_us exposure
    python tools/promptmap.py --id 0x27 [--bytes 30268 --layout corrected]
    python tools/promptmap.py --regions               # data_us region map
    python tools/promptmap.py --footprint 8192 16384 30000 65242 [--layout old|corrected]
    python tools/promptmap.py --untouched 8192 16384 30000 65242 [--layout old|corrected]
    python tools/promptmap.py --summary 8192 16384 30000 65242   # ids hit, share of each id's read set overwritten
    python tools/promptmap.py --hits 8192 16384 30000 65242      # per-id staged words inside its read set
    python tools/promptmap.py --header-after                     # region-B header E0..E14 after the real 141 / 184 payload
    python tools/promptmap.py --relocate 30268 65242             # where could the payload go instead (model)
    python tools/promptmap.py --stock                 # ids the stock speaks by itself
    python tools/promptmap.py --json FILE
"""
import argparse
import json
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FS = os.path.join(ROOT, 'firmware', 'bose', 'extracted', 'internal_fs')
ALT = os.path.join(ROOT, 'build', 'fsedit', 't', 'official', 'fs_000bff4c')
CATALOG = os.path.join(ROOT, 'docs', 'request-id-catalog.md')
STAGE_PY = os.path.join(ROOT, 'build', 'payload', 'stage_payload.py')

RPH_SIZE = 10486
DATA_SIZE = 219528
DATA_AREA_BYTE0 = 600        # data_us byte 0 at fs-area byte 600 (payload-184.md section 0, re-verified)
BLIND_LO, BLIND_HI = 34, 62  # tools/fsedit.py blind(): content offset = area byte - 136, bytes 34..62 of 64
PER_PERIOD = 14
PERIOD_WORDS = 32
FRAME_WORDS = 27             # stride of every frame-pointer list in data_us (parse-proven)
B_BASE = 18                  # region B base byte (file header idx0 = 9 words)
SILENCE_UNITS = (32, 33)     # region A header E6/E7 = 32/33; leading unit of 132 of 132 phrases


def _read(name, sub):
    for base in (FS, ALT):
        p = os.path.join(base, *sub)
        if os.path.exists(p):
            return open(p, 'rb').read()
    raise SystemExit('missing %s (looked in %s and %s)' % (name, FS, ALT))


def load_rphrases():
    return _read('rphrases_us', ('rphrases_us',) if os.path.exists(os.path.join(FS, 'rphrases_us'))
                 else ('tts', 'rphrases_us'))


def load_data_us():
    return _read('data_us', ('data_us',) if os.path.exists(os.path.join(FS, 'data_us'))
                 else ('NowSpeakTTS', 'data_us'))


# --------------------------------------------------------------------------------------------------
# rphrases_us
# --------------------------------------------------------------------------------------------------
class Rphrases:
    """147-word offset table, then payloads.  Entry k (k = request id + 1) -> word offset of payload k."""

    def __init__(self, raw):
        if len(raw) != RPH_SIZE:
            raise SystemExit('rphrases_us is %d bytes, expected %d' % (len(raw), RPH_SIZE))
        self.raw = raw
        self.w = struct.unpack('<%dH' % (len(raw) // 2), raw)
        self.count = self.w[0]                   # 147 entries; word 0 is the count (VM guard: idx < word 0)
        self.n = self.count + 1                  # table words = count word + 147 entries; payloads start here
        self.table = self.w[:self.n]             # table[k], k = 1..147, is the word offset of payload k
        self.nwords = len(self.w)

    def payload_layout(self, off):
        """Return dict for the payload at word offset `off` (layout read from fn_1ee80 0x1ee80..0x1ef5b)."""
        w = self.w
        hdr = w[off]
        n = hdr & 0x3fff
        f4 = bool(hdr & 0x4000)
        f8 = bool(hdr & 0x8000)
        h = (n + 1) >> 1
        u0 = off + 1
        b0 = off + 1 + ((n + 2) >> 1)            # one pad word after the units when n is even
        c0 = b0 + h
        d0 = c0 + (h if f4 else 0)
        end = d0 + (h if f8 else 0)
        byte = lambda base, i: self.raw[2 * (base + (i >> 1)) + (i & 1)]
        return dict(off=off, kind='payload', hdr=hdr, n=n, f4=f4, f8=f8, size=end - off,
                    units=bytes(byte(u0, i) for i in range(n)),
                    prosody=bytes(byte(b0, i) for i in range(n)),
                    arrays=dict(units=(u0, h), prosody=(b0, h), c=(c0, h if f4 else 0), d=(d0, h if f8 else 0)))

    def entries(self):
        """Distinct non-null payloads sorted by offset, each with its word size."""
        offs = sorted(set(o for o in self.table[1:] if o))
        return [self.payload_layout(o) for o in offs]

    def record_for_entry(self, k):
        o = self.table[k]
        return self.payload_layout(o) if o else None

    def id_range(self, rid):
        """Byte (offset, length) of the rphrases_us payload spoken for request id `rid` (0..146)."""
        if not 0 <= rid < self.count:
            return None
        rec = self.record_for_entry(rid + 1)
        if rec is None:
            return None
        return 2 * rec['off'], 2 * rec['size']


def load_catalog():
    cat = {}
    for line in open(CATALOG, encoding='utf-8'):
        m = re.match(r'\| `0x([0-9a-f]{2})` \| (.*) \|\s*$', line)
        if m:
            cat[int(m.group(1), 16)] = m.group(2).replace('*', '').strip()
    return cat


# --------------------------------------------------------------------------------------------------
# data_us
# --------------------------------------------------------------------------------------------------
class DataUs:
    def __init__(self, raw):
        if len(raw) != DATA_SIZE:
            raise SystemExit('data_us is %d bytes, expected %d' % (len(raw), DATA_SIZE))
        self.raw = raw
        self.w = struct.unpack('<%dH' % (len(raw) // 2), raw)
        w = self.w
        self.nregions = w[0]
        self.region_words = [(w[1 + 2 * i] << 16) | w[2 + 2 * i] for i in range(2)]   # B, A (idx0, idx1)
        assert self.region_words[0] * 2 == B_BASE, 'region B is not at byte 18'
        self.a_base = self.region_words[1] * 2                                       # byte 0x149a0
        self.E = self.entries(self.region_words[0])
        self.AE = self.entries(self.region_words[1])
        self.table_byte0 = B_BASE + self.E[2] + 2                                    # unit 1 -> byte 0x120
        self.t = [w[(self.table_byte0 // 2) + p] for p in range(44)]                # physical entries
        self.groups = [self.parse_group(p) for p in range(43)]

    def entries(self, base_word):
        w = self.w
        return [(w[base_word + 2 * k] << 16) | w[base_word + 2 * k + 1] for k in range(15)]

    def word(self, byte):
        return self.w[byte // 2]

    def parse_group(self, p):
        """Group p (unit p+1): leading descriptor word, 0x8005 flag|count, records, frame pointer lists."""
        w = self.w
        lead_b = B_BASE + self.t[p]                      # leading word (the previous group's trailing pointer)
        lead = w[lead_b // 2]
        end_b = B_BASE + self.t[p + 1]
        i = lead_b // 2 + 1
        g = dict(p=p, unit=p + 1, lead_byte=lead_b, lead=lead, end_byte=end_b, records=[], ptrs=[], tiny=False)
        if w[i] != 0x8005:
            # tiny alias group (silence units): [0x0001][shared silence frame pointer]
            g['tiny'] = True
            g['ptrs'] = [w[i + 1]]
            g['records'].append((i * 2, 0, 1, [w[i + 1]]))
            return g
        g['nrec'] = w[i] & 0xff
        i += 1
        last = None
        while i < end_b // 2:
            h = w[i]
            ni, no = h >> 8, h & 0xff
            if ni > 16 or no > 12 or i + 1 + 2 * ni + no > end_b // 2:
                break
            offs = list(w[i + 1 + 2 * ni:i + 1 + 2 * ni + no])
            ok = all(offs[k + 1] - offs[k] == FRAME_WORDS for k in range(len(offs) - 1))
            if not ok or (last is not None and offs and offs[0] - last != FRAME_WORDS):
                break
            g['records'].append((i * 2, ni, no, offs))
            g['ptrs'] += offs
            if offs:
                last = offs[-1]
            i += 1 + 2 * ni + no
        g['body_end'] = i * 2
        return g

    def frame_bytes(self, ptr):
        a = B_BASE + 2 * ptr
        return a, a + 2 * FRAME_WORDS

    def row_bytes(self, g):
        a = B_BASE + g['lead']
        return a, a + 5

    @property
    def frame_store(self):
        lo = min(p for g in self.groups for p in g['ptrs'])
        hi = max(p for g in self.groups for p in g['ptrs']) + FRAME_WORDS
        return B_BASE + 2 * lo, B_BASE + 2 * hi

    def regions(self):
        """Ordered byte regions of data_us (label, start, end, evidence)."""
        fs_lo, fs_hi = self.frame_store
        e6 = B_BASE + self.E[6]
        e7 = B_BASE + self.E[7]
        r = [
            ('file header (region count + 2 base words + junk)', 0, B_BASE, 'proven (parse)'),
            ('region-B header E0..E14', B_BASE, B_BASE + 60, 'proven (15 x 32-bit hi,lo; DSP copies at init)'),
            ('region-B head data (undecoded, E14 = 32)', B_BASE + 60, self.table_byte0 - 2, 'unknown role'),
            ('phoneme table (44 x u16 at 0x120)', self.table_byte0 - 2 + 2, B_BASE + self.t[0], 'proven'),
            ('unit groups 0..42 (records + leading descriptor)', B_BASE + self.t[0], self.groups[42]['body_end'],
             'proven (parse)'),
            ('descriptor rows (5 bytes each)', self.groups[42]['body_end'], fs_lo, 'well-supported'),
            ('frame store (27-word frames)', fs_lo, fs_hi, 'proven (pointers tile it)'),
            ('E6 array (E4 x E5 = 80 x 52 B)', e6, e7, 'proven (E7-E6 == 80*52)'),
            ('region-B tail (E7..E0 gap, undecoded)', e7, self.a_base, 'unknown role'),
            ('region A (second structure, undecoded)', self.a_base, DATA_SIZE, 'unknown role; header E0 = len-1'),
        ]
        return r


# --------------------------------------------------------------------------------------------------
# staging geometry
# --------------------------------------------------------------------------------------------------
def blind_word(i):
    """Is data_us word i fully writable?  fsedit: content offset c = area - 136, blind iff 34 <= c%64 <= 62."""
    for byte in (DATA_AREA_BYTE0 + 2 * i, DATA_AREA_BYTE0 + 2 * i + 1):
        c = byte - 136
        if not (BLIND_LO <= c % 64 <= BLIND_HI):
            return False
    return True


def derived_window():
    return [i for i in range(PERIOD_WORDS) if blind_word(i)]


def old_stage_constants():
    """FIRST/LAST/PERIOD as written in build/payload/stage_payload.py (read as text; never imported)."""
    src = open(STAGE_PY, encoding='utf-8').read()
    first_last = re.search(r'^FIRST, LAST = (\d+), (\d+)', src, re.M)
    period = re.search(r'^PERIOD = (\d+)', src, re.M)
    return int(first_last.group(1)), int(first_last.group(2)), int(period.group(1))


def layout_first(layout):
    if layout == 'old':
        return old_stage_constants()[0]
    if layout == 'corrected':
        win = derived_window()
        return win[0]
    raise SystemExit('layout must be old or corrected')


def staged_words(n_bytes, layout='corrected', start_period=0):
    """Sorted data_us word indices overwritten when n_bytes of payload are staged (padding included)."""
    first = layout_first(layout)
    words = -(-n_bytes // 2)
    periods = -(-words // PER_PERIOD)
    out = []
    for p in range(start_period, start_period + periods):
        for k in range(PER_PERIOD):
            out.append(PERIOD_WORDS * p + first + k)
    return periods, out


class Staged:
    """Prefix-sum membership over data_us words for a staged word list."""

    def __init__(self, words):
        self.flags = bytearray(DATA_SIZE // 2 + 1)
        for i in words:
            if 0 <= i < DATA_SIZE // 2:
                self.flags[i] = 1
        self.pre = [0]
        for f in self.flags:
            self.pre.append(self.pre[-1] + f)

    def hits_bytes(self, a, b):
        """Number of staged words overlapping byte interval [a, b)."""
        wa, wb = max(0, a // 2), min(DATA_SIZE // 2, (b + 1) // 2)
        if wb <= wa:
            return 0
        return self.pre[wb] - self.pre[wa]


# --------------------------------------------------------------------------------------------------
# exposure of a phrase
# --------------------------------------------------------------------------------------------------
def unit_exposure(du, u):
    """Byte intervals read for unit u (1..43), labelled.  Over-approximation: whole group span, whole frames."""
    if not 1 <= u <= 43:
        return None
    g = du.groups[u - 1]
    iv = [('table entry', du.table_byte0 + 2 * (u - 1), du.table_byte0 + 2 * (u - 1) + 2),
          ('group span', g['lead_byte'], g['end_byte'] if g['p'] < 42 else g['body_end']),
          ('descriptor row', *du.row_bytes(g))]
    for p in sorted(set(g['ptrs'])):
        iv.append(('frame', *du.frame_bytes(p)))
    return iv


def phrase_units(rec):
    return sorted(set(b for b in rec['units'] if b != 0xff))


def phrase_exposure(du, rec):
    """Dict label -> list of intervals for the units of rec, plus the global header (always read at init)."""
    ex = {'header': [('region-B header E0..E14', B_BASE, B_BASE + 60), ('file header', 0, B_BASE)]}
    ex['units'] = []
    for u in phrase_units(rec):
        ex['units'] += unit_exposure(du, u)
    return ex


def count_hits(staged, ivs):
    return sum(staged.hits_bytes(a, b) for (_l, a, b) in ivs)


# --------------------------------------------------------------------------------------------------
# what the stock speaks by itself (evidence tagged)
# --------------------------------------------------------------------------------------------------
STOCK = [
    # (ids, when, evidence)
    ('0x27-0x30 (battery 10..100%)', 'at every power-on, one of them (owner: "battery 100%" at power-on, '
     'field-log probe118/121 table); the level is the charge', 'observed (owner)'),
    ('0x09 mobile device not found + 0x00 ready to connect', 'power-on with nothing paired/connected (owner: '
     '"mobile device not found - ready to connect" on power-on, probe118)', 'observed (owner)'),
    ('0x00 ready to connect', 'centre/pairing long press with nothing connected (owner, probe117/118/123)',
     'observed (owner)'),
    ('0x16 english / 0x17 / 0x18', 'language gesture; also heard as the first of two prompts on a centre long '
     'press after music (owner, probe123)', 'observed (owner, with cave in image)'),
    ('0x0e connected to / 0x04 connected', 'a phone/laptop connects (name appended by the VM)',
     'hypothesis (catalog wording; probe67 heard 0x0e only from the cave)'),
    ('0x08 / 0x0d disconnected, 0x06 lost, 0x0c connection lost', 'link drop or out of range',
     'hypothesis (catalog wording)'),
    ('0x31 battery low please charge now, 0x32 battery full, 0x33 battery high, 0x34 battery medium',
     'low-battery warning / charge state', 'hypothesis (catalog wording; never observed by the project)'),
    ('0x12 / 0x13 voice prompts on/off, 0x14 / 0x15 auto off disabled/enabled', 'user toggle gestures',
     'hypothesis (catalog wording)'),
    ('0x11 list cleared + 0x35 ready to connect another device, 0x36-0x38 select a bose ...',
     'clearing the pairing list / second-device pairing', 'hypothesis (catalog wording)'),
    ('0x3e bluetooth off', 'Bluetooth-off gesture (README F8)', 'well-supported (README F8; probe177 heard an '
     'unexplained beep after it)'),
    ('0x19 0x1b 0x1c 0x1e 0x1f 0x20 0x21-0x26', 'HFP call events (a call on the laptop, Teams etc.)',
     'hypothesis (catalog wording; README F8 residual)'),
    ('0x39-0x3d heart rate / airbuds / noise cancellation', 'never: other Bose products (cross-product corpus)',
     'well-supported (catalog "What this tells us" 2)'),
]


# --------------------------------------------------------------------------------------------------
# reports
# --------------------------------------------------------------------------------------------------
# Request id -> rphrases entry.  Proven rule: entry = id + 1 (fn_1ee80 reads table word idx+1).  Two catalog
# ids do not follow it (hypothesis, from decoding the unit strings against the owner-verified wording):
#   0x0b  entry 12 is the unit string of "connected"; the sentence the owner heard for 0x0b ("press the
#         bluetooth and volume down buttons simultaneously on a second bose device") is entry 65 (id 64).
#   0x11  entry 18 is "bluetooth device list cleared"; the owner heard it followed by "ready to connect another
#         device", which is entry 54 (id 0x35): assumed chained by the VM.
PHRASE_MAP = {0x0b: (65,), 0x11: (18, 54)}


def id_entries(rid):
    return PHRASE_MAP.get(rid, (rid + 1,))


def id_rows(rp, du, cat):
    rows = []
    for rid in range(64):
        ents = id_entries(rid)
        recs = [rp.record_for_entry(k) for k in ents]
        rngs = [(2 * r['off'], 2 * r['size']) for r in recs]
        units_all = b''
        for r in recs:
            units_all += (bytes([255]) if units_all else b'') + r['units']
        rec = dict(recs[0], units=units_all) if len(recs) > 1 else recs[0]
        rows.append(dict(id=rid, text=cat.get(rid, ''), phrase=ents[0], entries=ents, rec=rec, recs=recs,
                         ranges=rngs, rph_off=rngs[0][0], rph_len=sum(l for _o, l in rngs),
                         units=phrase_units(rec), n_units=len(units_all),
                         empty=bool(len(recs) == 1 and recs[0]['units'] == bytes([255])),
                         remapped=ents != (rid + 1,)))
    return rows


def span_union(ivs):
    ivs = sorted((a, b) for (_l, a, b) in ivs)
    out = []
    for a, b in ivs:
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def verdicts(rp, du, cat, n_bytes, layout):
    periods, words = staged_words(n_bytes, layout)
    st = Staged(words)
    hdr_hits = st.hits_bytes(B_BASE, B_BASE + 60)
    e2_hit = st.hits_bytes(B_BASE + 4 * 2, B_BASE + 4 * 2 + 4)
    res = []
    for r in id_rows(rp, du, cat):
        if r['empty'] or not r['units']:
            res.append(dict(r, hits=0, strict='silent-stub', units_only='silent-stub', nbytes=0))
            continue
        ex = phrase_exposure(du, r['rec'])
        hits = count_hits(st, ex['units'])
        merged = span_union(ex['units'])
        res.append(dict(r, hits=hits, nbytes=sum(b - a for a, b in merged), nint=len(merged),
                        strict='TOUCHED (header E-entries overwritten)' if hdr_hits else
                        ('TOUCHED' if hits else 'untouched'),
                        units_only='TOUCHED' if hits else 'untouched'))
    return dict(n_bytes=n_bytes, layout=layout, periods=periods, span=64 * periods, staged_words=len(words),
                header_hits=hdr_hits, e2_hit=e2_hit, rows=res, staged=st)


def print_regions(du):
    print('data_us region map (bytes; B-relative pointers are byte 18 + value)')
    print('  region B base 18 (word 9); region A base %#x (word %#x)' % (du.a_base, du.region_words[1]))
    print('  region-B header E0..E14: ' + ' '.join('%#x' % e for e in du.E))
    print('  region-A header E0..E14: ' + ' '.join('%#x' % e for e in du.AE))
    for lab, a, b, ev in du.regions():
        print('  %#08x..%#08x %8d B  %-52s %s' % (a, b, b - a, lab, ev))


def print_table(rp, du, cat):
    print('%-5s %-6s %7s %5s %4s  %-34s %s' % ('id', 'entry', 'rph_off', 'len', 'N', 'text', 'units (phoneme codes)'))
    for r in id_rows(rp, du, cat):
        u = ' '.join('%d' % x for x in r['rec']['units'] if x != 0xff)
        ent = '+'.join(str(e) for e in r['entries']) + ('*' if r['remapped'] else '')
        print('0x%02x  %-6s %7d %5d %4d  %-34s %s' % (r['id'], ent, r['rph_off'], r['rph_len'],
                                                      r['n_units'], r['text'][:34], u[:60]))
    print('* = entry differs from the proven id+1 rule (hypothesis, PHRASE_MAP in promptmap.py)')


def print_footprint(rp, du, cat, sizes, layouts):
    for layout in layouts:
        print('layout %s (window words i %% 32 in %d..%d)' % (layout, layout_first(layout), layout_first(layout) + 13))
        for n in sizes:
            v = verdicts(rp, du, cat, n, layout)
            print('  payload %6d B: %5d periods, %6d staged words, span 0..%d B (%.1f %% of file); header E-words hit: %d'
                  % (n, v['periods'], v['staged_words'], v['span'], 100.0 * v['span'] / DATA_SIZE, v['header_hits']))
            for lab, a, b, _ev in du.regions():
                h = v['staged'].hits_bytes(a, b)
                tot = (b - a) // 2
                print('      %-52s %6d/%-6d words overwritten (%5.1f %%)' % (lab, h, tot, 100.0 * h / max(1, tot)))


def print_untouched(rp, du, cat, sizes, layouts):
    for layout in layouts:
        for n in sizes:
            v = verdicts(rp, du, cat, n, layout)
            nonempty = [r for r in v['rows'] if r['strict'] not in ('silent-stub',)]
            strict_ok = [r for r in nonempty if r['strict'] == 'untouched']
            unit_ok = [r for r in nonempty if r['units_only'] == 'untouched']
            print('layout %-9s payload %6d B: header E-words overwritten=%d  strict-untouched ids=%d of %d '
                  'speech ids; units-only-untouched=%d' % (layout, n, v['header_hits'], len(strict_ok),
                                                          len(nonempty), len(unit_ok)))
            if unit_ok:
                print('    units-only untouched (only meaningful if the header were spared): ' +
                      ' '.join('0x%02x' % r['id'] for r in unit_ok))
            silent = [r['id'] for r in v['rows'] if r['strict'] == 'silent-stub']
            print('    empty/silent ids (nothing spoken, so nothing to garble, useless as outcome ids): ' +
                  ' '.join('0x%02x' % i for i in silent))


def print_summary(rp, du, cat, sizes, layouts):
    print('%-9s %8s %7s %9s %6s %-11s %s' % ('layout', 'payload', 'periods', 'span B', 'hdr w', 'ids hit', "share of an id's read set overwritten (min / median / max)"))
    for layout in layouts:
        for n in sizes:
            v = verdicts(rp, du, cat, n, layout)
            speech = [r for r in v['rows'] if r['strict'] != 'silent-stub']
            fr = []
            for r in speech:
                ex = phrase_exposure(du, r['rec'])
                mw = sum((b - a + 1) // 2 for a, b in span_union(ex['units']))
                fr.append(100.0 * r['hits'] / max(1, mw))
            fr.sort()
            hit = sum(1 for r in speech if r['hits'])
            print('%-9s %8d %7d %9d %6d %2d of %-5d %.1f / %.1f / %.1f %%' % (
                layout, n, v['periods'], v['span'], v['header_hits'], hit, len(speech), fr[0], fr[len(fr) // 2], fr[-1]))


def print_hits(rp, du, cat, sizes, layout, ids=None):
    vs = [verdicts(rp, du, cat, n, layout) for n in sizes]
    print("staged words that fall in each id's read set (layout %s); read set = model over-approximation" % layout)
    print('%-5s %-32s %5s %8s  %s' % ('id', 'text', 'units', 'read B', '  '.join('%8d' % n for n in sizes)))
    for i, r in enumerate(vs[0]['rows']):
        if ids is not None and r['id'] not in ids:
            continue
        if r['strict'] == 'silent-stub':
            print('0x%02x  %-32s %5s %8s  silent stub (nothing spoken)' % (r['id'], r['text'][:32], '-', '-'))
            continue
        print('0x%02x  %-32s %5d %8d  %s' % (r['id'], r['text'][:32], len(r['units']), r['nbytes'],
                                           '  '.join('%8d' % v['rows'][i]['hits'] for v in vs)))


def print_id(rp, du, cat, rid, n_bytes, layout):
    v = verdicts(rp, du, cat, n_bytes, layout)
    r = v['rows'][rid]
    print('id 0x%02x "%s"' % (rid, r['text']))
    print('  rphrases_us entry %d: payload bytes %d..%d (%d B)  N=%d flags=%s' % (
        r['phrase'], r['rph_off'], r['rph_off'] + r['rph_len'], r['rph_len'], r['n_units'],
        ''.join(f for f, on in (('4', r['rec']['f4']), ('8', r['rec']['f8'])) if on) or '-'))
    print('  units: ' + ' '.join('%d' % b if b != 0xff else '|' for b in r['rec']['units']))
    if not r['units']:
        print('  no unit: nothing is spoken')
        return
    ex = phrase_exposure(du, r['rec'])
    merged = span_union(ex['units'])
    print('  data_us read set (model): %d intervals, %d B for the %d units %s' % (
        len(merged), sum(b - a for a, b in merged), len(r['units']), r['units']))
    print('  staged %d B (%s): %d staged words fall in that set; header E-words overwritten: %d -> %s' % (
        n_bytes, layout, r['hits'], v['header_hits'], r['strict']))


# --------------------------------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------------------------------
STAGE_WORDS = {'probe141': os.path.join(ROOT, 'build', 'payload', 'staged_words.json'),
               'probe184': os.path.join(ROOT, 'build', 'payload', 'narrow184', 'narrow_staged_words.json')}


def apply_staging(du, payload_words, layout, start_period=0):
    """Return data_us words (list) after the payload word stream is written into the blind windows."""
    w = list(du.w)
    first = layout_first(layout)
    for idx, val in enumerate(payload_words):
        p, k = divmod(idx, PER_PERIOD)
        w[PERIOD_WORDS * (p + start_period) + first + k] = val
    return w


def header_after(du, which, layout='corrected'):
    """E0..E14 and the phoneme-table address the DSP would compute after a real payload stream is staged.
    Physical positions: both probe141's committed DFU and 184's plan write words 9..22 (fsedit area bytes)."""
    path = STAGE_WORDS[which]
    if not os.path.exists(path):
        return None
    payload = json.load(open(path))
    w = apply_staging(du, payload, layout)
    ent = [(w[9 + 2 * k] << 16) | w[10 + 2 * k] for k in range(15)]
    return dict(which=which, words=len(payload), E=ent, table_unit1=B_BASE + ent[2] + 2,
                inside=B_BASE + ent[2] + 2 < DATA_SIZE)


def print_header_after(du):
    print('region-B header E0..E14 as the DSP reads it (copy at init, call 0x1605 r1=15):')
    print('  stock                 ' + ' '.join('%#x' % e for e in du.E))
    for which in ('probe141', 'probe184'):
        h = header_after(du, which)
        if h is None:
            print('  %-9s staged word file %s missing' % (which, STAGE_WORDS[which]))
            continue
        print('  %-9s (%5d words) ' % (which, h['words']) + ' '.join('%#x' % e for e in h['E']))
        print('            unit 1 table entry would be read at byte %#x (%s the %d-byte file); stock %#x' % (
            h['table_unit1'], 'inside' if h['inside'] else 'OUTSIDE', DATA_SIZE, du.table_byte0))


def relocate(rp, du, cat, n_bytes, layout):
    """Where could n_bytes be staged so that the unit model reports every speech id untouched?"""
    nw = -(-n_bytes // 2)
    per = -(-nw // PER_PERIOD)
    cands = [('head (stock layout)', 0),
             ('frame store start %#x' % du.frame_store[0], du.frame_store[0]),
             ('frame store end / E6 array %#x' % du.frame_store[1], du.frame_store[1]),
             ('end of E6 array %#x' % (B_BASE + du.E[7]), B_BASE + du.E[7]),
             ('region A start %#x' % du.a_base, du.a_base),
             ('tail: last %d B before the compensation slack (%#x)' % (64 * per, 0x35888),
              (0x35888 // 64 - per) * 64)]
    print('layout %s, payload %d B = %d periods = %d B of data_us' % (layout, n_bytes, per, 64 * per))
    for lab, start in cands:
        sp = -(-start // 64) if not lab.startswith('tail') else start // 64
        _p, words = staged_words(n_bytes, layout, start_period=sp)
        end_b = 2 * (words[-1] + 1)
        st = Staged(words)
        hdr = st.hits_bytes(0, B_BASE + 60)
        rows = verdicts_with(rp, du, cat, st)
        speech = [r for r in rows if r['units']]
        okc = sum(1 for r in speech if r['hits'] == 0)
        regs = [(l, st.hits_bytes(a, b)) for l, a, b, _e in du.regions() if st.hits_bytes(a, b)]
        print('  start %-52s bytes %#08x..%#08x: header hits %d, ids with no unit-exposure hit %d of %d' % (
            lab, 64 * sp, end_b, hdr, okc, len(speech)))
        print('      regions overwritten: ' + (', '.join('%s %d w' % (l.split(' (')[0], h) for l, h in regs) or 'none'))
        if end_b > 0x35888:
            print('      !! reaches the compensation slack (fsedit SLACK_RANGE) at %#x' % 0x35888)


def verdicts_with(rp, du, cat, st):
    rows = []
    for r in id_rows(rp, du, cat):
        if not r['units']:
            rows.append(dict(r, hits=0))
            continue
        ex = phrase_exposure(du, r['rec'])
        rows.append(dict(r, hits=count_hits(st, ex['units'])))
    return rows


def selftest():
    ok = True
    n_chk = [0]

    def check(cond, msg):
        n_chk[0] += 1
        if not cond:
            print('[FAIL] ' + msg)
            return False
        print('[ok]   ' + msg)
        return True

    rp = Rphrases(load_rphrases())
    du = DataUs(load_data_us())
    cat = load_catalog()

    # ---- rphrases_us ------------------------------------------------------------------------
    ok &= check(len(rp.raw) == RPH_SIZE and rp.nwords == 5243, 'rphrases_us is %d bytes = %d words' %
                (len(rp.raw), rp.nwords))
    ok &= check(rp.count == 147 and rp.n == 148 and len(rp.table) == 148,
                'word 0 = 147 = number of entries; table = count word + 147 entries = %d words' % rp.n)
    ok &= check(rp.table[1] == rp.n, 'entry 1 = word %d: the first payload starts right after the table' % rp.table[1])
    nulls = [k for k in range(1, rp.n) if rp.table[k] == 0]
    ok &= check(nulls == [81, 134], 'only entries 81 and 134 are null (ids 80 and 133, outside the catalog): %s' % nulls)
    ents = rp.entries()
    offs = [e['off'] for e in ents]
    ok &= check(offs == sorted(set(offs)) and len(offs) == 145, '%d distinct payload offsets, strictly increasing' %
                len(offs))
    ok &= check([k for k in range(1, rp.n) if rp.table[k]] == sorted(
        (k for k in range(1, rp.n) if rp.table[k]), key=lambda k: rp.table[k]),
        'entry order == payload order (no entry points backwards)')
    gaps_ok = True
    covered = rp.n
    for i, e in enumerate(ents):
        nxt = ents[i + 1]['off'] if i + 1 < len(ents) else rp.nwords
        if e['off'] + e['size'] != nxt:
            gaps_ok = False
            print('   gap/overlap at word %d: size %d next %d' % (e['off'], e['size'], nxt))
        covered += e['size']
    ok &= check(gaps_ok, 'computed payload sizes tile the file with no gap and no overlap (layout proof for all %d '
                'payloads, flags 0x4000/0x8000 included)' % len(ents))
    ok &= check(covered == rp.nwords and 2 * covered == RPH_SIZE,
                'table (%d words) + payloads cover %d words = all %d bytes' % (rp.n, covered, 2 * covered))
    ok &= check(ents[0]['off'] == rp.n, 'payloads start right after the table')
    rng = [rp.id_range(i) for i in range(64)]
    ok &= check(all(r is not None for r in rng), 'every catalog id 0..63 has a payload (entry id+1)')
    mono = all(rng[i][0] + rng[i][1] <= rng[i + 1][0] for i in range(63))
    ok &= check(mono, 'ids 0..63: byte ranges monotonic and non-overlapping (0x%x..0x%x)' %
                (rng[0][0], rng[63][0] + rng[63][1]))
    allr = [(i, rp.id_range(i)) for i in range(147) if rp.id_range(i)]
    ok &= check(all(allr[i][1][0] + allr[i][1][1] <= allr[i + 1][1][0] for i in range(len(allr) - 1)),
                'all %d non-null ids 0..146: ranges monotonic and non-overlapping' % len(allr))
    ok &= check(len(cat) == 64, 'catalog has 64 ids')
    stubs = [i for i in range(64) if rp.record_for_entry(i + 1)['units'] == bytes([255])]
    empties = sorted(i for i, t in cat.items() if t.startswith('(empty'))
    ok &= check(stubs == empties, 'the %d owner-verified empty ids %s are exactly the stub payloads (id+1 mapping)' %
                (len(empties), ' '.join('0x%02x' % i for i in empties)))
    seen = set()
    for e in ents:
        seen |= set(e['units'])
    ok &= check(seen <= set(range(1, 44)) | {0xff}, 'unit alphabet = %d..%d + 0xff (word break)' %
                (min(seen - {0xff}), max(seen - {0xff})))

    # ---- staging geometry -------------------------------------------------------------------
    win = derived_window()
    ok &= check(win == list(range(9, 23)), 'fsedit blind rule on data_us (area byte 600 + 2i) gives words '
                'i %% 32 in %d..%d (14 of 32)' % (win[0], win[-1]))
    o_first, o_last, o_per = old_stage_constants()
    ok &= check((o_first, o_last, o_per) == (11, 24, 32), 'stage_payload.py uses FIRST,LAST,PERIOD = %d,%d,%d '
                '(two words late versus the rule: payload-184.md section 0)' % (o_first, o_last, o_per))
    per, words = staged_words(30268, 'corrected')
    ok &= check(per == 1081 and 64 * per == 69184, 'corrected layout, 30,268 B ROFS: %d periods, span %d B '
                '(payload-184.md section 3: 1,081 periods, 69,184 B)' % (per, 64 * per))
    ok &= check(all(blind_word(i) for i in words), 'every staged word of the corrected layout is fully blind')

    # ---- data_us structure ------------------------------------------------------------------
    ok &= check(du.nregions == 2 and du.region_words == [9, 0xa4d0], 'file header: 2 regions at words 9 and 0xa4d0')
    ok &= check(du.E[2] == 268 and du.table_byte0 == 0x120, 'E2 = 268 puts the phoneme table at byte 0x120')
    ok &= check(du.t == sorted(du.t) and len(set(du.t)) == 44, 'phoneme table: 44 strictly increasing entries')
    spans = [(g['lead_byte'], g['end_byte']) for g in du.groups]
    ok &= check(all(spans[i][1] == spans[i + 1][0] for i in range(42)), '43 group spans tile bytes %#x..%#x with no '
                'gap' % (spans[0][0], spans[-1][1]))
    full = [g for g in du.groups if not g['tiny']]
    ok &= check(len(full) == 41 and [g['p'] for g in du.groups if g['tiny']] == [31, 32],
                '41 real groups + 2 tiny alias groups (physical 31, 32)')
    ok &= check(all(g['nrec'] == 5 and len(g['records']) == 5 for g in full), 'every real group has exactly 5 records '
                '(flag|count word 0x8005), all parsed')
    store = {}
    clash = False
    for g in full:
        for p in g['ptrs']:
            if p in store:
                clash = True
            store[p] = g['p']
    sil = [g['ptrs'][0] for g in du.groups if g['tiny']]
    ok &= check(len(set(sil)) == 1, 'both tiny alias groups share one silence frame pointer %#x' % sil[0])
    pts = sorted(store)
    ok &= check(not clash and sil[0] not in store and len(pts) == 1267, '41 real groups: 1267 distinct frame pointers, '
                'none shared with the silence frame')
    pts = sorted(list(store) + [sil[0]])
    ok &= check(all(pts[i + 1] - pts[i] == FRAME_WORDS for i in range(len(pts) - 1)),
                'silence frame + all real frames stride exactly 27 with no gap: %d frames, words %#x..%#x' %
                (len(pts), pts[0], pts[-1]))
    fs_lo, fs_hi = du.frame_store
    ok &= check(fs_hi == B_BASE + du.E[6], 'frame store ends at byte %#x == 18 + E6 (independent cross-check)' % fs_hi)
    ok &= check(du.E[7] - du.E[6] == du.E[4] * du.E[5], 'E7 - E6 = %d = E4 x E5 = %d x %d (the E6 array)' %
                (du.E[7] - du.E[6], du.E[4], du.E[5]))
    ok &= check(du.a_base + du.AE[0] + 1 == DATA_SIZE, 'region A header E0 = %d: region A runs to the last byte' %
                du.AE[0])
    ok &= check((du.AE[6], du.AE[7]) == SILENCE_UNITS and all(
        [g['p'] for g in du.groups if g['tiny']] == [u - 1 for u in SILENCE_UNITS] for _ in [0]),
        'silence units 32,33 (region A E6,E7) are the two tiny alias groups (unit u -> physical group u-1)')
    first_units = [e['units'][0] for e in ents if e['kind'] == 'payload' and len(e['units']) > 1]
    ok &= check(set(first_units) <= set(SILENCE_UNITS), 'the first unit of %d of %d multi-unit phrases is a silence '
                'unit (32 or 33)' % (sum(1 for u in first_units if u in SILENCE_UNITS), len(first_units)))
    rows = [du.row_bytes(g) for g in du.groups]
    lo_r, hi_r = min(a for a, _ in rows), max(b for _, b in rows)
    ok &= check(lo_r >= du.groups[42]['body_end'] and hi_r <= fs_lo,
                'descriptor rows lie in %#x..%#x just before the frame store' % (lo_r, hi_r))

    # ---- the committed probe141 image really carries the damaged header ------------------------
    dfu = os.path.join(ROOT, 'build', 'hook', 'probe141_brown.dfu')
    if os.path.exists(dfu) and os.path.exists(STAGE_WORDS['probe141']):
        b = open(dfu, 'rb').read()
        o = 0xBFF4C + DATA_AREA_BYTE0
        head_ok = b[o:o + 18] == du.raw[:18]
        words141 = json.load(open(STAGE_WORDS['probe141']))
        got = struct.unpack('<14H', b[o + 18:o + 18 + 28])
        ok &= check(head_ok and list(got) == words141[:14],
                    'build/hook/probe141_brown.dfu: data_us words 9..22 = first 14 staged words %s (E2 = %#x): the '
                    'image that killed all audio on 2026-10-06 had the header overwritten' % (
                        ' '.join('%04x' % x for x in got[:3]) + '...', (got[4] << 16) | got[5]))
    else:
        print('[skip] build/hook/probe141_brown.dfu or staged_words.json missing: image check skipped')

    # ---- exposure sanity --------------------------------------------------------------------
    r0 = id_rows(rp, du, cat)[0]
    ex = phrase_exposure(du, r0['rec'])
    ok &= check(sum(b - a for a, b in span_union(ex['units'])) > 0, 'id 0x00 exposure is non-empty')
    for n in (8192, 16384, 30000, 65242):
        for layout in ('old', 'corrected'):
            v = verdicts(rp, du, cat, n, layout)
            if not check(v['header_hits'] > 0 and v['e2_hit'] > 0 and
                         all(r['strict'] != 'untouched' for r in v['rows']),
                         'payload %d (%s): header + E2 overwritten, no speech id is certifiably untouched' %
                         (n, layout)):
                ok = False
    print('%d checks, %s' % (n_chk[0], 'ALL PASSED' if ok else 'FAILURES'))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--table', action='store_true')
    ap.add_argument('--regions', action='store_true')
    ap.add_argument('--stock', action='store_true')
    ap.add_argument('--id', type=lambda s: int(s, 0))
    ap.add_argument('--bytes', type=int, default=30268)
    ap.add_argument('--layout', choices=('old', 'corrected', 'both'), default='both')
    ap.add_argument('--footprint', type=int, nargs='*')
    ap.add_argument('--untouched', type=int, nargs='*')
    ap.add_argument('--header-after', action='store_true')
    ap.add_argument('--summary', type=int, nargs='*')
    ap.add_argument('--hits', type=int, nargs='*')
    ap.add_argument('--relocate', type=int, nargs='*')
    ap.add_argument('--json')
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    rp = Rphrases(load_rphrases())
    du = DataUs(load_data_us())
    cat = load_catalog()
    layouts = ('old', 'corrected') if a.layout == 'both' else (a.layout,)
    if a.table or not any((a.regions, a.stock, a.id is not None, a.footprint, a.untouched, a.json, a.header_after,
                           a.relocate, a.summary, a.hits)):
        print_table(rp, du, cat)
    if a.regions:
        print_regions(du)
    if a.stock:
        for ids, when, ev in STOCK:
            print('%-60s | %s | %s' % (ids, when, ev))
    if a.id is not None:
        print_id(rp, du, cat, a.id, a.bytes, 'corrected' if a.layout == 'both' else a.layout)
    if a.footprint:
        print_footprint(rp, du, cat, a.footprint, layouts)
    if a.untouched:
        print_untouched(rp, du, cat, a.untouched, layouts)
    if a.hits:
        print_hits(rp, du, cat, a.hits, 'corrected' if a.layout == 'both' else a.layout)
    if a.summary:
        print_summary(rp, du, cat, a.summary, layouts)
    if a.header_after:
        print_header_after(du)
    if a.relocate:
        for n in a.relocate:
            for layout in layouts:
                relocate(rp, du, cat, n, layout)
    if a.json:
        out = []
        for r in id_rows(rp, du, cat):
            rs = [] if not r['units'] else [list(x) for x in span_union(phrase_exposure(du, r['rec'])['units'])]
            out.append(dict(id=r['id'], text=r['text'], entries=list(r['entries']), remapped_hypothesis=r['remapped'],
                            rphrases_ranges=[list(x) for x in r['ranges']], n_units=r['n_units'],
                            units=r['units'], physical_groups=[u - 1 for u in r['units']],
                            dataus_read_set_model=rs, dataus_read_bytes=sum(y - x for x, y in rs)))
        json.dump(dict(note='rphrases_ranges are exact byte (offset, length) in rphrases_us; dataus_read_set_model is '
                            'an over-approximation of what the DSP reads from data_us (there is no per-id chunk)',
                       ids=out, regions=[(l, a_, b_, e) for l, a_, b_, e in du.regions()]),
                  open(a.json, 'w'), indent=1)


if __name__ == '__main__':
    main()
