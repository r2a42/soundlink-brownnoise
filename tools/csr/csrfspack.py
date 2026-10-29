#!/usr/bin/env python3
"""Clean-room packer for the CSR BlueCore filesystem ('iFel').

No public tool repacks a CSR filesystem -- csr-dfu-parser and friends only
extract. This writes one, from a format derived entirely from the shipped
images in hand.

    python csrfspack.py --roundtrip 04_fs0.bin
    python csrfspack.py --list      04_fs0.bin
    python csrfspack.py --replace   04_fs0.bin /vm.app new_vm.app out_fs.bin

Acceptance test is --roundtrip: parse and re-emit unchanged, byte-identical.

FORMAT (all 32-bit fields are PDP/middle-endian: the two 16-bit halves are
swapped; 16-bit fields are plain little-endian; names are UTF-16LE):

    'fsr_dfu1'                8 bytes   area id
    signature               128 bytes   RSA, vendor private key
    digest                    4 bytes   unidentified; not any CRC32/Adler/
                                        MD5/SHA variant tested. Passed
                                        through unchanged.
    'iFel'                    4 bytes   <- word 0 of the FS body
    size_in_words             4 bytes   PDP; covers 'iFel' .. trailer end
    nfiles                    2 bytes
    block table      nfiles * 12 bytes  (fno, data_off, size), all PDP
                                        fno: low 24 bits = name offset in
                                        words from 'iFel'; high 8 = flags
                                        (0x80 directory, 0x40 code, 0x00 data)
                                        directory: data_off = first child
                                        index + 1, size = number of children
    name pool                           per name: u16 length in WORDS, then
                                        UTF-16LE chars. Packed tight.
    file data                           each file padded to a multiple of
                                        2 words (dword alignment)
    slack                               padding; one word is chosen so the
                                        16-bit XOR over the whole body is 0
    trailer                   8 bytes   size_in_words copy (PDP) + 'iFel'

WHAT THIS CANNOT DO: regenerate the 128-byte signature. It copies it
through, and THE DEVICE CHECKS IT -- a modified filesystem built with this
tool was rejected with errFIRMWARE on 2026-09-20. Useful for analysis and
for SPI writes; useless for loading over USB. See CLAUDE.md, "THE
MODIFIED-IMAGE WRITE".
"""
import sys, os, struct


def pdp(x):
    return ((x >> 16) & 0xFFFF) | ((x & 0xFFFF) << 16)


def rd32(b, o):
    return pdp(struct.unpack_from('<I', b, o)[0])


def wr32(x):
    return struct.pack('<I', pdp(x))


class Fs:
    def __init__(self, area):
        self.area = area
        assert area[:8] == b'fsr_dfu1', area[:8]
        self.signature = area[8:0x88]
        self.digest = area[0x88:0x8C]
        m = 0x8C
        assert area[m:m + 4] == b'iFel', area[m:m + 4]
        self.m = m
        self.siw = rd32(area, m + 4)
        nf = struct.unpack_from('<H', area, m + 8)[0]
        self.entries = []
        p = m + 10
        for i in range(nf):
            fno = rd32(area, p); doff = rd32(area, p + 4); sz = rd32(area, p + 8)
            p += 12
            noff = fno & 0xFFFFFF
            flags = fno >> 24
            name = ''
            if noff:
                np = m + noff * 2
                ln = struct.unpack_from('<H', area, np)[0]
                name = area[np + 2:np + 2 + ln * 2].decode('utf-16-le')
            self.entries.append(dict(i=i, flags=flags, noff=noff, name=name,
                                     doff=doff, size=sz,
                                     isdir=bool(flags & 0x80)))
        for e in self.entries:
            if not e['isdir']:
                p = m + e['doff'] * 2
                e['data'] = area[p:p + e['size']]

        # The slack between the last file and the trailer is not zeroed in
        # Bose's images -- packfile leaves ~7 words of whatever was there.
        # Keep it so an unmodified repack is byte-identical; the XOR fix-up
        # below lands on the same value it already holds.
        last = max((e for e in self.entries if not e['isdir']),
                   key=lambda e: e['doff'])
        end_w = last['doff'] + (last['size'] + 1) // 2
        self.orig_slack = area[m + end_w * 2: m + (self.siw - 4) * 2]

    # ---- tree helpers ----

    def paths(self):
        out = {}

        def walk(idx, prefix):
            e = self.entries[idx]
            if e['isdir']:
                d = prefix + (e['name'] + '/' if e['name'] else '')
                first = e['doff'] - 1
                for c in range(first, first + e['size']):
                    walk(c, d)
            else:
                out[prefix + e['name']] = e
        walk(0, '/')
        return out

    # ---- emit ----

    def build(self):
        m = self.m
        nf = len(self.entries)
        blocks_words = 5 + nf * 6          # 'iFel'(2) + siw(2) + nfiles(1) + 6/entry

        # name pool, in the original offset order so a round-trip is exact
        named = [e for e in self.entries if e['noff']]
        named.sort(key=lambda e: e['noff'])
        noff = {}
        pool = bytearray()
        w = blocks_words
        for e in named:
            noff[e['i']] = w
            nb = e['name'].encode('utf-16-le')
            pool += struct.pack('<H', len(nb) // 2) + nb
            w += 1 + len(nb) // 2

        # file data, in the original offset order, dword aligned
        files = [e for e in self.entries if not e['isdir']]
        files.sort(key=lambda e: e['doff'])
        doff = {}
        data = bytearray()
        dstart = w
        for e in files:
            if w % 2:                       # align to a dword boundary
                data += b'\x00\x00'
                w += 1
            doff[e['i']] = w
            data += e['data']
            nw = (len(e['data']) + 1) // 2
            if len(e['data']) % 2:
                data += b'\x00'
            w += nw
        assert dstart + len(data) // 2 == w, (dstart, len(data), w)

        # block table
        blocks = bytearray()
        blocks += b'iFel'
        siw_off = len(blocks)
        blocks += wr32(0)                   # size_in_words, patched below
        blocks += struct.pack('<H', nf)
        for e in self.entries:
            fno = (e['flags'] << 24) | noff.get(e['i'], 0)
            d = e['doff'] if e['isdir'] else doff[e['i']]
            blocks += wr32(fno) + wr32(d) + wr32(e['size'])
        assert len(blocks) // 2 == blocks_words, (len(blocks) // 2, blocks_words)

        body = bytearray(blocks) + pool + data
        # pad out to the original trailer position if we still fit, else to
        # the next dword boundary plus the 6-word slack the packer leaves
        cur = len(body) // 2
        target = self.siw - 4               # trailer occupies the last 4 words
        if cur > target:
            target = cur + (6 - (cur + 4) % 2) % 2 + 6
        slack = bytes(self.orig_slack)
        if len(slack) != (target - cur) * 2:
            slack = b'\x00\x00' * (target - cur)
        body += slack
        body += wr32(self.siw if target == self.siw - 4 else target + 4)
        body += b'iFel'
        siw_final = len(body) // 2
        struct.pack_into('<I', body, siw_off, pdp(siw_final))
        struct.pack_into('<I', body, len(body) - 8, pdp(siw_final))

        # choose the slack word so the 16-bit XOR over the body is 0
        slack_at = (target - 1) * 2
        struct.pack_into('<H', body, slack_at, 0)
        x = 0
        for i in range(0, len(body), 2):
            x ^= struct.unpack_from('<H', body, i)[0]
        struct.pack_into('<H', body, slack_at, x)
        chk = 0
        for i in range(0, len(body), 2):
            chk ^= struct.unpack_from('<H', body, i)[0]
        assert chk == 0, hex(chk)

        return b'fsr_dfu1' + self.signature + self.digest + bytes(body)


def cmd_list(path):
    fs = Fs(open(path, 'rb').read())
    print('signature %d bytes, digest %s, size_in_words %d, %d entries'
          % (len(fs.signature), fs.digest.hex(), fs.siw, len(fs.entries)))
    for p, e in sorted(fs.paths().items()):
        print('  %9d  flags=%02X  %s' % (e['size'], e['flags'], p))
    return 0


def cmd_roundtrip(path):
    d = open(path, 'rb').read()
    out = Fs(d).build()
    print('%s\n  in  %d bytes\n  out %d bytes' % (path, len(d), len(out)))
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


def cmd_replace(path, fspath, localfile, outpath):
    fs = Fs(open(path, 'rb').read())
    tbl = fs.paths()
    if fspath not in tbl:
        print('no such file in image: %s' % fspath)
        print('available: %s' % ', '.join(sorted(tbl)))
        return 1
    new = open(localfile, 'rb').read()
    e = tbl[fspath]
    print('  %s: %d -> %d bytes' % (fspath, e['size'], len(new)))
    e['data'] = new
    e['size'] = len(new)
    out = fs.build()
    open(outpath, 'wb').write(out)
    print('  wrote %s (%d bytes)' % (outpath, len(out)))
    x = 0
    for i in range(0x8C, len(out), 2):
        x ^= struct.unpack_from('<H', out, i)[0]
    print('  16-bit XOR over body = 0x%04X %s' % (x, '(OK)' if x == 0 else '*** BAD'))
    return 0


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    if argv[1] == '--list':
        return cmd_list(argv[2])
    if argv[1] == '--roundtrip':
        return cmd_roundtrip(argv[2])
    if argv[1] == '--replace':
        return cmd_replace(argv[2], argv[3], argv[4], argv[5])
    print(__doc__)
    return 2


sys.exit(main(sys.argv))
