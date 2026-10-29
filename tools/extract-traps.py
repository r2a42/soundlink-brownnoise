#!/usr/bin/env python3
"""Extract the trap-number table from an ADK `vmbuilder.exe`.

vmbuilder holds a flat array of pointers to trap-name strings, indexed by
trap number. Trap numbers are NOT stable between BlueLab versions, so the
table must be taken from the version that matches the image being read --
see docs/trap-numbering.md.

    python tools/extract-traps.py <vmbuilder.exe> [out.json]
"""
import json
import re
import struct
import sys


def sections(d):
    pe = struct.unpack_from('<I', d, 0x3C)[0]
    nsec = struct.unpack_from('<H', d, pe + 6)[0]
    optsz = struct.unpack_from('<H', d, pe + 20)[0]
    base = struct.unpack_from('<I', d, pe + 24 + 28)[0]
    out = []
    for i in range(nsec):
        o = pe + 24 + optsz + 40 * i
        vsz, va, rsz, ro = struct.unpack_from('<IIII', d, o + 8)
        out.append((va, vsz, ro, rsz))
    return base, out


def extract(path):
    d = open(path, 'rb').read()
    base, secs = sections(d)

    def off2va(off):
        for va, vsz, ro, rsz in secs:
            if ro <= off < ro + rsz:
                return base + va + (off - ro)

    def va2off(va):
        r = va - base
        for va_, vsz, ro, rsz in secs:
            if va_ <= r < va_ + vsz:
                return ro + (r - va_)

    def cstr(va):
        o = va2off(va)
        if o is None or not 0 < o < len(d):
            return None
        s = d[o:o + 64].split(b'\0')[0]
        if not s or not re.match(rb'^[A-Za-z_][A-Za-z0-9_]*$', s):
            return None
        return s.decode('ascii')

    m = re.search(br'\x00malloc\x00', d)          # trap 0 anchors the array
    target = off2va(m.start() + 1)
    starts = [i for i in range(0, len(d) - 4, 4)
              if struct.unpack_from('<I', d, i)[0] == target]
    for start in starts:
        table, i = {}, 0
        while True:
            va = struct.unpack_from('<I', d, start + 4 * i)[0]
            name = cstr(va)
            if name is None:
                break
            table[name] = i
            i += 1
        if len(table) > 100:
            return table
    raise SystemExit('trap table not found in %s' % path)


if __name__ == '__main__':
    t = extract(sys.argv[1])
    print('%d traps' % len(t))
    if len(sys.argv) > 2:
        json.dump(t, open(sys.argv[2], 'w'), indent=1, sort_keys=True)
