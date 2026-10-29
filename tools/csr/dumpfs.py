#!/usr/bin/env python3
"""Dump the VM filesystem out of a CSR-dfu2 file (or a raw fsr_dfu1 blob)."""
import sys, struct, os, math, collections

def ent(b):
    if not b: return 0.0
    c = collections.Counter(b); n = len(b)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

def pdp(x): return ((x >> 16) & 0xFFFF) | ((x & 0xFFFF) << 16)

def parse_fs(d, area_start, outdir):
    assert d[area_start:area_start+8] == b'fsr_dfu1', d[area_start:area_start+8]
    magic_off = area_start + 8 + 128 + 4
    assert d[magic_off:magic_off+4] == b'iFel', d[magic_off:magic_off+4]
    siw = pdp(struct.unpack_from('<I', d, magic_off+4)[0])
    nfiles = struct.unpack_from('<H', d, magic_off+8)[0]
    base = magic_off + 10
    blocks = []
    for n in range(nfiles):
        fno, doff, sz = [pdp(x) for x in struct.unpack_from('<III', d, base + 12*n)]
        blocks.append((fno, doff, sz))
    def rd_name(noff):
        p = magic_off + noff*2
        ln = struct.unpack_from('<H', d, p)[0]
        return d[p+2:p+2+ln*2].decode('utf-16-le','replace')
    ents = []
    for n,(fno,doff,sz) in enumerate(blocks):
        noff = fno & 0xFFFFFF; flags = fno >> 24
        ents.append(dict(idx=n, flags=flags, isdir=bool(flags & 0x80),
                         name=rd_name(noff) if noff else '', doff=doff, size=sz,
                         noff=noff))
    os.makedirs(outdir, exist_ok=True)
    def walk(i, path):
        e = ents[i]
        if e['isdir']:
            p = os.path.join(path, e['name']) if e['name'] else path
            os.makedirs(p, exist_ok=True)
            first = e['doff'] - 1     # 1-based index of first child block
            for c in range(first, first + e['size']):
                walk(c, p)
        else:
            src = magic_off + e['doff']*2
            blob = d[src:src+e['size']]
            fp = os.path.join(path, e['name'])
            open(fp,'wb').write(blob)
            print(f"  wrote {fp}  {len(blob)} bytes  flags=0x{e['flags']:02X}  ent={ent(blob):.2f}")
    walk(0, outdir)
    return ents

if __name__ == '__main__':
    d = open(sys.argv[1],'rb').read()
    start = d.find(b'fsr_dfu1')
    print(f"fsr_dfu1 at 0x{start:X}")
    parse_fs(d, start, sys.argv[2])
