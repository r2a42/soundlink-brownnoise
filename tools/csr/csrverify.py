#!/usr/bin/env python3
"""Verify every checksum in a CSR-dfu2 container against its stored value.

This is the prerequisite for writing a repacker: each CRC/checksum below
must reproduce exactly on the stock image before any writer can be trusted.

    python csrverify.py Minnow_3.0.3.dfu
"""
import sys, struct, zlib

NAREAS, SIGSZ = 16, 128


def crc32inv(b):
    """ANSI X3.66 / USB-DFU CRC as CSR uses it: init 0xFFFFFFFF, not final-xored."""
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


def main(path):
    d = open(path, 'rb').read()
    print('%s  (%d bytes)' % (path, len(d)))
    ok = True

    def check(label, got, want):
        nonlocal ok
        good = got == want
        ok = ok and good
        print('  %-44s got 0x%08X  stored 0x%08X  %s'
              % (label, got, want, 'OK' if good else '*** MISMATCH ***'))

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
    fsd = []
    for _ in range(NAREAS):
        L = r.u32(); r.u16(); r.u16(); r.u16(); r.u16(); rl = r.u32()
        fsd.append((L, rl))
    if desc_len:
        r.raw(desc_len)

    # ---- stack software: crc32 over program+constant data ----
    for i, L in enumerate(ssd):
        if not L:
            continue
        start = r.o
        r.raw(8)
        stored = r.u32()
        pdl = r.u32(); cdl = r.u16(); r.u16()
        r.raw(pdl); r.raw(cdl)
        check('StackSoftware[%d] crc' % i, crc32inv(d[start + 12:r.o]), stored)

    for i, L in enumerate(asd):
        if not L:
            continue
        r.raw(r.u16())

    # ---- persistent stores: trailing crc32 over the area body ----
    def check_ps(name, expected):
        start = r.o
        r.u16(); keys = r.u16()
        for _ in range(keys):
            r.u16(); r.u16(); ln = r.u16()
            if ln:
                r.raw(ln * 2)
        if expected == (r.o - start) + SIGSZ + 4:
            r.raw(SIGSZ)
        body_end = r.o
        stored = r.u32()
        check('%s crc' % name, crc32inv(d[start:body_end]), stored)

    for i, (L, spl, apl) in enumerate(psd):
        if L:
            check_ps('PersistentStore[%d]' % i, L)
    for i, (L, spl, apl) in enumerate(psd):
        if spl:
            check_ps('StackPersistentStore[%d]' % i, spl)
    for i, (L, spl, apl) in enumerate(psd):
        if apl:
            check_ps('AppPersistentStore[%d]' % i, apl)

    # ---- filesystems: 16-bit XOR over the FS body must be 0 ----
    for i, (L, rl) in enumerate(fsd):
        if not rl:
            continue
        start = r.o
        r.raw(8); r.raw(SIGSZ); r.u32()
        magic_off = r.o
        assert d[magic_off:magic_off + 4] == b'iFel', d[magic_off:magic_off + 4]
        siw = pdp(struct.unpack_from('<I', d, magic_off + 4)[0])
        x = 0
        for w in range(siw):
            x ^= struct.unpack_from('<H', d, magic_off + 2 * w)[0]
        print('  %-44s got 0x%04X      expect 0x0000  %s'
              % ('FileSystem[%d] 16-bit XOR' % i, x, 'OK' if x == 0 else '*** MISMATCH ***'))
        ok = ok and x == 0
        r.o = start + rl

    # ---- file footer crc + DFU suffix ----
    body_end = r.o
    stored_file_crc = struct.unpack_from('<I', d, body_end)[0]
    check('file_crc', crc32inv(d[:body_end]), stored_file_crc)

    suf = d[body_end + 4:]
    stored_suffix_crc = struct.unpack_from('<I', suf, 12)[0]
    check('dfu suffix dwCRC', crc32inv(d[:len(d) - 4]), stored_suffix_crc)
    # NB: plain zlib.crc32 here, NOT the inverted form -- the suffix CRC is
    # chosen so that a plain CRC over the whole file lands on 0xFFFFFFFF.
    whole = zlib.crc32(d)
    print('  %-44s got 0x%08X  expect 0xFFFFFFFF  %s'
          % ('crc32(whole file)', whole, 'OK' if whole == 0xFFFFFFFF else '*** MISMATCH ***'))
    ok = ok and whole == 0xFFFFFFFF

    print()
    print('ALL CHECKSUMS REPRODUCE' if ok else 'SOME CHECKSUMS DO NOT REPRODUCE')
    return 0 if ok else 1


sys.exit(main(sys.argv[1]))
