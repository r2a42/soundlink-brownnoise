#!/usr/bin/env python3
"""Extract and word-dump the PSKEY_DSP* parameter blocks from a CSR-dfu2
container -- on the Bose Minnow image these hold BDSP's tuning.

    python dspdump.py Minnow_3.0.3.dfu [--json out.json]

What is established (see CLAUDE.md):
  * keys 0x2261-0x2272 are PSKEY_DSP9..DSP26, CSR's documented "User DSP
    configuration data" (PSKEY_DSP0 = 0x2258)
  * word 0 of every 42/52-word parameter block is a 13-bit additive
    checksum: w0 == sum(w[1:]) (mod 0x2000), verified on all 10 blocks.
    The top 3 bits are not part of the checksum.
  * word 1 low byte is a preset index, 0x10 / 0x20 / 0x30
  * DSP15/DSP16 are a different format: word 0 is the block's own PSKEY
    number and word 1 chains to the next (DSP16's is 0, end of chain)
  * DSP23 is a 16-point sqrt(2)-spaced frequency table, 11 Hz .. 2048 Hz

NOT established: the coefficient layout inside the blocks. It does NOT
match CSR's own PEQ parameter format (src/kalimba/audio_proc/peq.h:
num_stages, gain_exp, gain_mant, then 5*N coefficients b2,b1,b0,a2,a1,
then N scales) -- BDSP uses its own container. Values sit at exactly
+/-0x4000 (= +/-1.0 in Q14) often enough to suggest cascaded biquads with
unity/pass-through stages, but a 5-word grouping scored only 82% on a
pole-stability test where the right answer should score ~100%. Do not
assert a decode without better evidence.
"""
import sys, struct, json, os

NAREAS, SIGSZ = 16, 128


class R:
    def __init__(s, d, o=0): s.d, s.o = d, o
    def u16(s): v = struct.unpack_from('<H', s.d, s.o)[0]; s.o += 2; return v
    def u32(s): v = struct.unpack_from('<I', s.d, s.o)[0]; s.o += 4; return v
    def i64(s): v = struct.unpack_from('<q', s.d, s.o)[0]; s.o += 8; return v
    def u64(s): v = struct.unpack_from('<Q', s.d, s.o)[0]; s.o += 8; return v
    def raw(s, n): v = s.d[s.o:s.o + n]; s.o += n; return v


def app_ps_records(path):
    """Return the Application Persistent Store records of a CSR-dfu2 file."""
    d = open(path, 'rb').read()
    r = R(d)
    r.raw(8); r.u16(); r.u32(); r.u16(); r.raw(64)
    for _ in range(5):
        r.u32()
    desc_len = r.u32()
    ssd = []
    for _ in range(NAREAS):
        r.u64(); r.u64(); ssd.append(r.u32())
    asd = []
    for _ in range(NAREAS):
        r.u16(); r.i64(); asd.append(r.u32())
    psd = []
    for _ in range(NAREAS):
        r.u64(); L = r.u32(); spl = r.u32(); apl = r.u32()
        psd.append((L, spl, apl))
    for _ in range(NAREAS):
        r.u32(); r.u16(); r.u16(); r.u16(); r.u16(); r.u32()
    if desc_len:
        r.raw(desc_len)
    for L in ssd:
        if not L:
            continue
        r.raw(8); r.u32()
        pdl = r.u32(); cdl = r.u16(); r.u16()
        r.raw(pdl); r.raw(cdl)
    for L in asd:
        if not L:
            continue
        r.raw(r.u16())

    def parse_ps(expected):
        start = r.o
        r.u16(); keys = r.u16()
        recs = []
        for _ in range(keys):
            a = r.u16(); k = r.u16(); ln = r.u16()
            recs.append((a, k, ln, r.raw(ln * 2) if ln else b''))
        if expected == (r.o - start) + SIGSZ + 4:
            r.raw(SIGSZ)
        r.u32()
        return recs

    out = None
    for L, spl, apl in psd:
        if L:
            parse_ps(L)
    for L, spl, apl in psd:
        if spl:
            parse_ps(spl)
    for L, spl, apl in psd:
        if apl:
            out = parse_ps(apl)
    return out or []


def checksum13(words):
    """The checksum word 0 must satisfy, modulo 0x2000."""
    return sum(words[1:]) & 0x1FFF


def main(argv):
    path = argv[1]
    outjson = None
    if '--json' in argv:
        outjson = argv[argv.index('--json') + 1]

    blocks = {k: dat for a, k, ln, dat in app_ps_records(path)
              if 0x2258 <= k <= 0x2289 and ln}
    if outjson:
        with open(outjson, 'w') as f:
            json.dump({hex(k): v.hex() for k, v in blocks.items()}, f, indent=1)

    for k in sorted(blocks):
        b = blocks[k]
        w = [struct.unpack_from('<H', b, i)[0] for i in range(0, len(b), 2)]
        note = ''
        if len(w) >= 2:
            if (w[0] & 0x1FFF) == checksum13(w):
                note = '  checksum OK (13-bit)'
            elif w[0] == k:
                note = '  self-identifying: w0 = own PSKEY, w1 = next in chain'
        print('PSKEY_DSP%d (0x%04X)  %d words%s' % (k - 0x2258, k, len(w), note))
        for i in range(0, len(w), 8):
            print('   %2d: %s' % (i, ' '.join('%04X' % x for x in w[i:i + 8])))
        print()


main(sys.argv)
