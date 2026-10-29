"""Parse a CSR BlueCore DFU container (AN093) and list/extract its File System area.
Structure taken from ramikg/csr-dfu-parser CSRDFU.bt.
Also handles a bare FS area blob (starting with 'fsr_dfu1' or the 'iFel' magic).
"""
import struct, sys, os

def pdp(x):
    return ((x >> 16) & 0xFFFF) | ((x & 0xFFFF) << 16)

class R:
    def __init__(self, b, o=0):
        self.b = b; self.o = o
    def u8(self):  v=self.b[self.o]; self.o+=1; return v
    def u16(self): v=struct.unpack_from('<H', self.b, self.o)[0]; self.o+=2; return v
    def u32(self): v=struct.unpack_from('<I', self.b, self.o)[0]; self.o+=4; return v
    def u64(self): v=struct.unpack_from('<Q', self.b, self.o)[0]; self.o+=8; return v
    def raw(self,n): v=self.b[self.o:self.o+n]; self.o+=n; return v

def parse_header(r):
    h = {}
    h['file_id'] = r.raw(8)
    h['file_version'] = r.u16()
    h['file_length'] = r.u32()
    h['file_header_length'] = r.u16()
    h['file_description'] = r.raw(64)
    h['ss_len'] = r.u32(); h['as_len'] = r.u32(); h['ps_len'] = r.u32()
    h['sps_len'] = r.u32(); h['aps_len'] = r.u32(); h['desc_len'] = r.u32()
    h['ssd'] = [dict(bc=r.u64(), fg=r.u64(), len=r.u32()) for _ in range(16)]
    h['asd'] = [dict(vm=r.u16(), s=r.u64(), len=r.u32()) for _ in range(16)]
    h['psd'] = [dict(bc=r.u64(), len=r.u32(), sps_len=r.u32(), aps_len=r.u32()) for _ in range(16)]
    h['fsd'] = [dict(len=r.u32(), fs=r.u16(), vm=r.u16(), u1=r.u16(), u2=r.u16(), real_length=r.u32())
                for _ in range(16)]
    if h['desc_len']:
        h['description'] = r.raw(h['desc_len']).decode('utf-16-le', 'replace')
    return h

def parse_fs(b, base, outdir=None, label='fs'):
    """base points at the 'fsr_dfu1' id (or directly at 'iFel')."""
    off = base
    sig_present = b[base:base+8] == b'fsr_dfu1'
    if sig_present:
        off = base + 8 + 128 + 4   # id + 128-byte signature + unknown checksum
    magic = b[off:off+4]
    if magic != b'iFel':
        # scan forward a little for the magic
        idx = b.find(b'iFel', base, base+1024)
        if idx < 0:
            print('  !! no iFel magic found near', hex(base)); return None
        off = idx
    mstart = off
    size_in_words = pdp(struct.unpack_from('<I', b, off+4)[0])
    nfiles = struct.unpack_from('<H', b, off+8)[0]
    print(f'  FS at 0x{base:x}: signed={sig_present} magic_at=0x{mstart:x} '
          f'size_words={size_in_words} (={size_in_words*2} bytes) files={nfiles}')
    blocks = []
    p = off + 10
    for i in range(nfiles):
        fno = pdp(struct.unpack_from('<I', b, p)[0]); p += 4
        doff = pdp(struct.unpack_from('<I', b, p)[0]); p += 4
        size = pdp(struct.unpack_from('<I', b, p)[0]); p += 4
        name_off = fno & 0xFFFFFF
        flags = fno >> 24
        name = ''
        if name_off:
            np = mstart + name_off*2
            ln = struct.unpack_from('<H', b, np)[0]
            name = b[np+2:np+2+ln*2].decode('utf-16-le', 'replace')
        blocks.append(dict(i=i, flags=flags, isdir=bool(flags & 0x80),
                           name=name, data_off=doff, size=size))
    # walk
    results = []
    def walk(idx, path):
        blk = blocks[idx]
        if blk['isdir']:
            d = path + blk['name'] + '/'
            first = blk['data_off'] - 1
            for c in range(first, first + blk['size']):
                if 0 <= c < len(blocks):
                    walk(c, d)
        else:
            fp = path + blk['name']
            data = b[mstart + blk['data_off']*2: mstart + blk['data_off']*2 + blk['size']]
            results.append((fp, blk['size'], data))
    walk(0, '')
    for fp, size, data in results:
        head = data[:16].hex()
        print(f'    {size:9d}  {fp:50s} {head}')
        if outdir:
            op = os.path.join(outdir, fp.lstrip('/').replace('/', os.sep))
            os.makedirs(os.path.dirname(op) or '.', exist_ok=True)
            open(op, 'wb').write(data)
    return results

def main(path, outdir=None):
    b = open(path, 'rb').read()
    print(f'{path}: {len(b)} bytes')
    if b[:7] == b'CSR-dfu':
        r = R(b)
        h = parse_header(r)
        print(' id=%r ver=%d len=0x%x hdrlen=0x%x' % (h['file_id'], h['file_version'],
                                                      h['file_length'], h['file_header_length']))
        print(' desc=%r' % h['file_description'].split(b'\x00')[0])
        if 'description' in h:
            print(' description=%r' % h['description'])
        print(' lengths: ss=0x%x as=0x%x ps=0x%x sps=0x%x aps=0x%x desc=%d' %
              (h['ss_len'], h['as_len'], h['ps_len'], h['sps_len'], h['aps_len'], h['desc_len']))
        for k in ('ssd','asd','psd','fsd'):
            for i, d in enumerate(h[k]):
                if any(v for kk, v in d.items() if kk.endswith('len') or kk == 'len' or kk=='real_length'):
                    print('  %s[%d] = %s' % (k, i, d))
        off = r.o
        print(' after header off=0x%x' % off)
        # Stack software areas
        for d in h['ssd']:
            if d['len']:
                print('  SS area at 0x%x id=%r len=0x%x' % (off, b[off:off+8], d['len']))
                off += d['len']
        for d in h['asd']:
            if d['len']:
                print('  AS area at 0x%x len=0x%x' % (off, d['len']))
                off += d['len']
        for key in ('len','sps_len','aps_len'):
            for d in h['psd']:
                if d[key]:
                    print('  PS(%s) area at 0x%x len=0x%x' % (key, off, d[key]))
                    off += d[key]
        for d in h['fsd']:
            if d['real_length']:
                print('  FS area at 0x%x len=0x%x real=0x%x' % (off, d['len'], d['real_length']))
                parse_fs(b, off, outdir)
                off += d['real_length']
        print(' trailing at 0x%x .. %d bytes left' % (off, len(b)-off))
    else:
        # bare blob: find fsr_dfu1 / iFel
        i = b.find(b'fsr_dfu1')
        if i < 0:
            i = b.find(b'iFel')
        if i < 0:
            print(' no FS magic found'); return
        parse_fs(b, i, outdir)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
