#!/usr/bin/env python3
"""Parse a CSR-dfu2 container per ramikg/csr-dfu-parser CSRDFU.bt, and report
empirically on compression / filesystem layout."""
import sys, struct, zlib, math, collections

NAREAS = 16
SIGSZ = 128

def ent(b):
    if not b: return 0.0
    c = collections.Counter(b); n = len(b)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

def pdp(x):
    """PDP-endian u32: swap the two 16-bit halves."""
    return ((x >> 16) & 0xFFFF) | ((x & 0xFFFF) << 16)

class R:
    def __init__(s, d, o=0): s.d, s.o = d, o
    def u8(s):  v=s.d[s.o]; s.o+=1; return v
    def u16(s): v=struct.unpack_from('<H', s.d, s.o)[0]; s.o+=2; return v
    def u32(s): v=struct.unpack_from('<I', s.d, s.o)[0]; s.o+=4; return v
    def i64(s): v=struct.unpack_from('<q', s.d, s.o)[0]; s.o+=8; return v
    def u64(s): v=struct.unpack_from('<Q', s.d, s.o)[0]; s.o+=8; return v
    def raw(s,n): v=s.d[s.o:s.o+n]; s.o+=n; return v

def crc32inv(b):
    return zlib.crc32(b) ^ 0xFFFFFFFF

def main(path):
    d = open(path,'rb').read()
    print(f"=== {path}  ({len(d)} bytes) ===")
    r = R(d)
    fid = r.raw(8).decode('ascii','replace')
    ver = r.u16(); flen = r.u32(); fhlen = r.u16()
    desc = r.raw(64)
    print(f"file_id={fid!r} version={ver} file_length=0x{flen:X} ({flen}) header_len=0x{fhlen:X} ({fhlen})")
    ss_len=r.u32(); as_len=r.u32(); ps_len=r.u32(); sps_len=r.u32(); aps_len=r.u32(); desc_len=r.u32()
    print(f"lengths: stack_sw=0x{ss_len:X} app_sw=0x{as_len:X} ps=0x{ps_len:X} sps=0x{sps_len:X} aps=0x{aps_len:X} desc=0x{desc_len:X}")

    ssd=[]; asd=[]; psd=[]; fsd=[]
    for _ in range(NAREAS):
        bc=r.u64(); fg=r.u64(); L=r.u32(); ssd.append((bc,fg,L))
    for _ in range(NAREAS):
        vm=r.u16(); s_=r.i64(); L=r.u32(); asd.append((vm,s_,L))
    for _ in range(NAREAS):
        bc=r.u64(); L=r.u32(); spl=r.u32(); apl=r.u32(); psd.append((bc,L,spl,apl))
    for _ in range(NAREAS):
        L=r.u32(); fs=r.u16(); vm=r.u16(); u1=r.u16(); u2=r.u16(); rl=r.u32(); fsd.append((L,fs,vm,u1,u2,rl))
    if desc_len:
        dsc = r.raw(desc_len).decode('utf-16-le','replace')
        print(f"description={dsc!r}")
    print(f"end of header at 0x{r.o:X} (declared {fhlen:#X})")
    for i,(bc,fg,L) in enumerate(ssd):
        if L: print(f"  ssd[{i}] bc={bc} fg={fg} len=0x{L:X}")
    for i,(vm,s_,L) in enumerate(asd):
        if L: print(f"  asd[{i}] vm={vm} s={s_} len=0x{L:X}")
    for i,(bc,L,spl,apl) in enumerate(psd):
        if L or spl or apl: print(f"  psd[{i}] bc={bc} len=0x{L:X} sps=0x{spl:X} aps=0x{apl:X}")
    for i,(L,fs,vm,u1,u2,rl) in enumerate(fsd):
        if rl: print(f"  fsd[{i}] len=0x{L:X} fs=0x{fs:X} vm=0x{vm:X} u1=0x{u1:X} u2=0x{u2:X} real_len=0x{rl:X} ({rl})")

    # ---- stack software areas ----
    for i,(bc,fg,L) in enumerate(ssd):
        if not L: continue
        start = r.o
        sid = r.raw(8).decode('ascii','replace')
        crc = r.u32(); pdl = r.u32(); cdl = r.u16(); sver = r.u16()
        print(f"\n--- StackSoftware[{i}] @0x{start:X} id={sid!r} ---")
        print(f"    crc=0x{crc:08X} program_data_length=0x{pdl:X} ({pdl})"
              f" constant_data_length=0x{cdl:X} ({cdl}) version={sver}")
        prog = r.raw(pdl); const = r.raw(cdl)
        calc = crc32inv(d[start+8+4 : r.o])
        print(f"    crc check: stored 0x{crc:08X} calc 0x{calc:08X} -> {'OK' if calc==crc else 'MISMATCH'}")
        print(f"    header bytes before program_data = {8+4+4+2+2} ; area total = {r.o-start} vs declared {L}")
        print(f"    program_data entropy  = {ent(prog):.4f} bits/byte")
        print(f"    constant_data entropy = {ent(const):.4f} bits/byte")
        open(f"out_stack{i}_program.bin","wb").write(prog)
        open(f"out_stack{i}_const.bin","wb").write(const)

    # ---- application software ----
    for i,(vm,s_,L) in enumerate(asd):
        if not L: continue
        start = r.o
        alen = r.u16(); app = r.raw(alen)
        print(f"\n--- ApplicationSoftware[{i}] @0x{start:X} app_len=0x{alen:X} ({alen}) entropy={ent(app):.4f}")
        print(f"    area total = {r.o-start} vs declared {L}")
        open(f"out_app{i}.bin","wb").write(app)

    # ---- persistent stores ----
    def parse_ps(name, expected):
        start = r.o
        clear = r.u16(); keys = r.u16()
        recs = []
        for _ in range(keys):
            action = r.u16(); key = r.u16(); ln = r.u16()
            data = r.raw(ln*2) if ln else b''
            recs.append((action,key,ln,data))
        if expected == (r.o - start) + SIGSZ + 4:
            sig = r.raw(SIGSZ)
        crc = r.u32()
        print(f"\n--- {name} @0x{start:X} clear={clear} keys={keys} total={r.o-start} declared={expected}")
        return recs
    for i,(bc,L,spl,apl) in enumerate(psd):
        if L: parse_ps(f"PersistentStore[{i}]", L)
    for i,(bc,L,spl,apl) in enumerate(psd):
        if spl: parse_ps(f"StackPersistentStore[{i}]", spl)
    for i,(bc,L,spl,apl) in enumerate(psd):
        if apl: parse_ps(f"AppPersistentStore[{i}]", apl)

    # ---- filesystems ----
    for i,(L,fs,vm,u1,u2,rl) in enumerate(fsd):
        if not rl: continue
        start = r.o
        fid2 = r.raw(8).decode('ascii','replace')
        sig = r.raw(SIGSZ)
        unk_ck = r.u32()
        magic_off = r.o
        magic = r.raw(4).decode('ascii','replace')
        siw = pdp(r.u32()); nfiles = r.u16()
        print(f"\n--- FileSystem[{i}] @0x{start:X} id={fid2!r} unknown_checksum=0x{unk_ck:08X}")
        print(f"    'File' magic at 0x{magic_off:X} (= area start + {magic_off-start}) reads {magic!r}")
        print(f"    size_in_words=0x{siw:X} ({siw}) -> {siw*2} bytes ; number_of_files={nfiles}")
        blocks=[]
        for n in range(nfiles):
            fno = pdp(r.u32()); doff = pdp(r.u32()); sz = pdp(r.u32())
            blocks.append((fno,doff,sz))
        print(f"    file blocks end at 0x{r.o:X}; block size = 12 bytes each")
        # names + data
        def rd_name(noff):
            p = magic_off + noff*2
            ln = struct.unpack_from('<H', d, p)[0]
            return d[p+2:p+2+ln*2].decode('utf-16-le','replace')
        entries=[]
        for n,(fno,doff,sz) in enumerate(blocks):
            noff = fno & 0xFFFFFF
            flags = fno >> 24
            isdir = bool(flags & 0x80)
            nm = rd_name(noff) if noff else ''
            entries.append((n,flags,isdir,nm,doff,sz,noff))
        # walk tree
        print(f"\n    {'idx':>4} {'flags':>5} {'type':<4} {'dataoff(w)':>11} {'size':>9}  name")
        for (n,flags,isdir,nm,doff,sz,noff) in entries:
            print(f"    {n:>4} 0x{flags:02X}  {'DIR' if isdir else 'file':<4} {doff:>11} {sz:>9}  {nm}")
        # dump file contents + sniff
        print(f"\n    --- file content sniff (first 16 bytes, entropy) ---")
        for (n,flags,isdir,nm,doff,sz,noff) in entries:
            if isdir: continue
            p = magic_off + doff*2
            blob = d[p:p+sz]
            sniff = blob[:16]
            print(f"    {n:>4} {nm:<28} sz={sz:>8} ent={ent(blob):5.2f}  {sniff.hex()}  {bytes(c if 32<=c<127 else 46 for c in sniff).decode()}")
        # trailer
        tp = magic_off + 2*siw - 8
        siwc = pdp(struct.unpack_from('<I', d, tp)[0])
        suffix = d[tp+4:tp+8].decode('ascii','replace')
        print(f"\n    trailer @0x{tp:X}: size_in_words_copy=0x{siwc:X} magic_suffix={suffix!r}")
        # xor checksum
        ck = 0
        for w in range(siw):
            ck ^= struct.unpack_from('<H', d, magic_off + 2*w)[0]
        print(f"    16-bit XOR checksum over {siw} words from 'File' magic = 0x{ck:04X} (expect 0)")
        r.o = start + rl
        print(f"    area declared real_length={rl}; consumed to 0x{r.o:X}")

    print(f"\nremaining after areas: 0x{r.o:X} of 0x{len(d):X} ({len(d)-r.o} bytes)")
    fcrc = struct.unpack_from('<I', d, r.o)[0]
    print(f"file_crc = 0x{fcrc:08X}  calc = 0x{crc32inv(d[:r.o]):08X}")
    suf = d[r.o+4:]
    print(f"dfu suffix ({len(suf)} bytes): {suf.hex()}")
    if len(suf) >= 16:
        bcdDev, idProd, idVend, bcdDfu = struct.unpack_from('<HHHH', suf, 0)
        sigb = suf[8:11]; slen = suf[11]; scrc = struct.unpack_from('<I', suf, 12)[0]
        print(f"  bcdDevice=0x{bcdDev:04X} idProduct=0x{idProd:04X} idVendor=0x{idVend:04X} "
              f"bcdDFU=0x{bcdDfu:04X} sig={sigb!r} len={slen} crc=0x{scrc:08X}")

main(sys.argv[1])
