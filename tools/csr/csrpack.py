#!/usr/bin/env python3
"""Clean-room writer for CSR-dfu2 containers.

Splits a .dfu into its areas, lets callers replace an area's contents, and
re-emits a structurally valid container with every checksum recomputed:
stack-software CRC, the three persistent-store CRCs, the filesystem's
16-bit XOR, file_crc, and the DFU suffix dwCRC.

    python csrpack.py --roundtrip Minnow_3.0.3.dfu
    python csrpack.py --extract  Minnow_3.0.3.dfu outdir/
    python csrpack.py --rebuild  Minnow_3.0.3.dfu outdir/ new.dfu

Acceptance test is --roundtrip: parse and re-emit with no changes and the
output must be byte-identical to the input. Nothing built on this tool is
trustworthy until that passes.

WHAT THIS CANNOT DO: regenerate the 128-byte RSA signature carried by each
persistent-store area and by the filesystem area. Those are made with
Bose's private key. This tool copies them through unchanged, which is
correct for any edit the signature does not cover and useless for any edit
it does. THE DEVICE DOES VERIFY THEM: a 6-byte modified image was rejected
with errFIRMWARE on 2026-09-20. Anything this tool changes inside a signed
area will NOT load over USB. See CLAUDE.md, "THE MODIFIED-IMAGE WRITE".
"""
import sys, os, struct, zlib, json

NAREAS, SIGSZ = 16, 128


def crc32inv(b):
    return zlib.crc32(b) ^ 0xFFFFFFFF


def pdp(x):
    return ((x >> 16) & 0xFFFF) | ((x & 0xFFFF) << 16)


class R:
    def __init__(s, d, o=0): s.d, s.o = d, o
    def u16(s): v = struct.unpack_from('<H', s.d, s.o)[0]; s.o += 2; return v
    def u32(s): v = struct.unpack_from('<I', s.d, s.o)[0]; s.o += 4; return v
    def i64(s): v = struct.unpack_from('<q', s.d, s.o)[0]; s.o += 8; return v
    def u64(s): v = struct.unpack_from('<Q', s.d, s.o)[0]; s.o += 8; return v
    def raw(s, n): v = s.d[s.o:s.o + n]; s.o += n; return v


class Dfu:
    """A parsed CSR-dfu2 container held as header bytes + a list of areas."""

    def __init__(self, data):
        self.data = data
        self._parse()

    def _parse(self):
        d = self.data
        r = R(d)
        self.file_id = r.raw(8)
        self.file_version = r.u16()
        self.file_length = r.u32()
        self.file_header_length = r.u16()
        self.file_description = r.raw(64)
        self.ss_len = r.u32(); self.as_len = r.u32(); self.ps_len = r.u32()
        self.sps_len = r.u32(); self.aps_len = r.u32(); self.desc_len = r.u32()
        self.ssd, self.asd, self.psd, self.fsd = [], [], [], []
        for _ in range(NAREAS):
            self.ssd.append([r.u64(), r.u64(), r.u32()])
        for _ in range(NAREAS):
            self.asd.append([r.u16(), r.i64(), r.u32()])
        for _ in range(NAREAS):
            self.psd.append([r.u64(), r.u32(), r.u32(), r.u32()])
        for _ in range(NAREAS):
            self.fsd.append([r.u32(), r.u16(), r.u16(), r.u16(), r.u16(), r.u32()])
        self.description = r.raw(self.desc_len) if self.desc_len else b''
        self.header_end = r.o

        # areas, in the order the boot loader consumes them
        self.areas = []          # list of (kind, index, raw bytes)
        for i, e in enumerate(self.ssd):
            if e[2]:
                self.areas.append(['ss', i, r.raw(e[2])])
        for i, e in enumerate(self.asd):
            if e[2]:
                start = r.o
                alen = r.u16(); r.raw(alen)
                self.areas.append(['as', i, d[start:r.o]])
        for i, e in enumerate(self.psd):
            if e[1]:
                self.areas.append(['ps', i, r.raw(e[1])])
        for i, e in enumerate(self.psd):
            if e[2]:
                self.areas.append(['sps', i, r.raw(e[2])])
        for i, e in enumerate(self.psd):
            if e[3]:
                self.areas.append(['aps', i, r.raw(e[3])])
        for i, e in enumerate(self.fsd):
            if e[5]:
                self.areas.append(['fs', i, r.raw(e[5])])
        self.body_end = r.o
        self.file_crc = r.u32()
        self.suffix = r.raw(16)

    # ---- checksum fixers, applied to an area's bytes in place ----

    @staticmethod
    def fix_ss(b):
        """Stack software: crc32 over everything after id(8)+crc(4)."""
        return b[:8] + struct.pack('<I', crc32inv(b[12:])) + b[12:]

    @staticmethod
    def fix_ps(b):
        """Persistent store: trailing crc32 over the whole area body."""
        return b[:-4] + struct.pack('<I', crc32inv(b[:-4]))

    @staticmethod
    def fs_xor(b):
        """16-bit XOR over the filesystem body from the 'iFel' magic."""
        off = b.find(b'iFel')
        if off < 0:
            return None, None
        siw = pdp(struct.unpack_from('<I', b, off + 4)[0])
        x = 0
        for w in range(siw):
            x ^= struct.unpack_from('<H', b, off + 2 * w)[0]
        return x, off

    def build(self):
        """Re-emit the container with every checksum recomputed."""
        areas = []
        for kind, i, b in self.areas:
            if kind == 'ss':
                b = self.fix_ss(b)
            elif kind in ('ps', 'sps', 'aps'):
                b = self.fix_ps(b)
            areas.append([kind, i, b])

        # refresh the per-area length tables from the actual bytes
        for e in self.ssd:
            e[2] = 0
        for e in self.asd:
            e[2] = 0
        for e in self.psd:
            e[1] = e[2] = e[3] = 0
        for e in self.fsd:
            e[0] = e[5] = 0
        for kind, i, b in areas:
            if kind == 'ss':
                self.ssd[i][2] = len(b)
            elif kind == 'as':
                self.asd[i][2] = len(b)
            elif kind == 'ps':
                self.psd[i][1] = len(b)
            elif kind == 'sps':
                self.psd[i][2] = len(b)
            elif kind == 'aps':
                self.psd[i][3] = len(b)
            elif kind == 'fs':
                self.fsd[i][5] = len(b)
                self.fsd[i][0] = self._fs_len_field.get(i, len(b))

        body = b''.join(b for _, _, b in areas)

        h = bytearray()
        h += self.file_id
        h += struct.pack('<H', self.file_version)
        file_length_off = len(h)
        h += struct.pack('<I', 0)          # patched below
        h += struct.pack('<H', self.file_header_length)
        h += self.file_description
        h += struct.pack('<IIIIII', self.ss_len, self.as_len, self.ps_len,
                         self.sps_len, self.aps_len, self.desc_len)
        for e in self.ssd:
            h += struct.pack('<QQI', e[0], e[1], e[2])
        for e in self.asd:
            h += struct.pack('<HqI', e[0], e[1], e[2])
        for e in self.psd:
            h += struct.pack('<QIII', e[0], e[1], e[2], e[3])
        for e in self.fsd:
            h += struct.pack('<IHHHHI', e[0], e[1], e[2], e[3], e[4], e[5])
        h += self.description

        out = bytes(h) + body
        # file_length counts everything up to and including the file_crc
        struct.pack_into('<I', h, file_length_off, len(h) + len(body) + 4)
        out = bytes(h) + body
        out += struct.pack('<I', crc32inv(out))
        out += self.suffix[:12] + struct.pack('<I', 0)
        out = out[:-4] + struct.pack('<I', crc32inv(out[:-4]))
        return out

    _fs_len_field = {}


def cmd_roundtrip(path):
    d = open(path, 'rb').read()
    f = Dfu(d)
    f._fs_len_field = {i: e[0] for i, e in enumerate(f.fsd) if e[5]}
    out = f.build()
    print('%s' % path)
    print('  in  %d bytes' % len(d))
    print('  out %d bytes' % len(out))
    if out == d:
        print('  BYTE-IDENTICAL -- round-trip OK')
        return 0
    n = min(len(out), len(d))
    diffs = [i for i in range(n) if out[i] != d[i]]
    print('  *** %d differing bytes%s' % (
        len(diffs), '' if len(out) == len(d) else ', and lengths differ'))
    for i in diffs[:16]:
        print('     @0x%06X  in=%02X out=%02X' % (i, d[i], out[i]))
    return 1


def cmd_extract(path, outdir):
    d = open(path, 'rb').read()
    f = Dfu(d)
    os.makedirs(outdir, exist_ok=True)
    man = []
    for n, (kind, i, b) in enumerate(f.areas):
        name = '%02d_%s%d.bin' % (n, kind, i)
        open(os.path.join(outdir, name), 'wb').write(b)
        man.append({'n': n, 'kind': kind, 'index': i, 'file': name, 'len': len(b)})
        print('  %-16s %9d bytes' % (name, len(b)))
    json.dump(man, open(os.path.join(outdir, 'manifest.json'), 'w'), indent=1)
    return 0


def cmd_rebuild(path, indir, outpath):
    d = open(path, 'rb').read()
    f = Dfu(d)
    f._fs_len_field = {i: e[0] for i, e in enumerate(f.fsd) if e[5]}
    man = json.load(open(os.path.join(indir, 'manifest.json')))
    for m in man:
        b = open(os.path.join(indir, m['file']), 'rb').read()
        if len(b) != f.areas[m['n']][2].__len__():
            print('  note: %s changed size %d -> %d'
                  % (m['file'], len(f.areas[m['n']][2]), len(b)))
        f.areas[m['n']][2] = b
    out = f.build()
    open(outpath, 'wb').write(out)
    print('  wrote %s (%d bytes)' % (outpath, len(out)))
    return 0


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    if argv[1] == '--roundtrip':
        return cmd_roundtrip(argv[2])
    if argv[1] == '--extract':
        return cmd_extract(argv[2], argv[3])
    if argv[1] == '--rebuild':
        return cmd_rebuild(argv[2], argv[3], argv[4])
    print(__doc__)
    return 2


sys.exit(main(sys.argv))
