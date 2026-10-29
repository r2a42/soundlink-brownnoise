#!/usr/bin/env python3
"""Dump every Persistent Store record from a CSR-dfu2 container, with real
PSKEY names from pskeys_gordon.json (extracted from the CSR8670 "gordon"
pskeys.html shipped in the ADK).

    python psdump.py Minnow_3.0.3.dfu

Read-only, offline. Never guess PSKEY numbers from memory -- they are all
in pskeys_gordon.json, and the ones I remembered were wrong.
"""
import sys, struct, json, os

NAREAS = 16
SIGSZ = 128

_here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_here, 'pskeys_gordon.json')) as f:
    NAMED = {int(k): v for k, v in json.load(f).items()}


class R:
    def __init__(s, d, o=0): s.d, s.o = d, o
    def u16(s): v = struct.unpack_from('<H', s.d, s.o)[0]; s.o += 2; return v
    def u32(s): v = struct.unpack_from('<I', s.d, s.o)[0]; s.o += 4; return v
    def i64(s): v = struct.unpack_from('<q', s.d, s.o)[0]; s.o += 8; return v
    def u64(s): v = struct.unpack_from('<Q', s.d, s.o)[0]; s.o += 8; return v
    def raw(s, n): v = s.d[s.o:s.o + n]; s.o += n; return v


def main(path):
    d = open(path, 'rb').read()
    r = R(d)
    r.raw(8)                      # file_id
    r.u16(); r.u32(); r.u16()     # version, file_length, header_len
    r.raw(64)                     # file_desc
    ss_len = r.u32(); as_len = r.u32(); ps_len = r.u32()
    sps_len = r.u32(); aps_len = r.u32(); desc_len = r.u32()

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

    for L in ssd:                 # skip stack software areas
        if not L:
            continue
        r.raw(8); r.u32()
        pdl = r.u32(); cdl = r.u16(); r.u16()
        r.raw(pdl); r.raw(cdl)
    for L in asd:                 # skip application software areas
        if not L:
            continue
        r.raw(r.u16())

    def parse_ps(name, expected):
        start = r.o
        clear = r.u16(); keys = r.u16()
        recs = []
        for _ in range(keys):
            action = r.u16(); key = r.u16(); ln = r.u16()
            recs.append((action, key, ln, r.raw(ln * 2) if ln else b''))
        sig = r.raw(SIGSZ) if expected == (r.o - start) + SIGSZ + 4 else None
        r.u32()                   # crc
        print('\n=== %s  clear=%d keys=%d  signature=%s ===' % (
            name, clear, keys, ('%d bytes' % len(sig)) if sig else 'NONE'))
        for action, key, ln, data in recs:
            allzero = data and not any(data)
            print('  action=%d key=0x%04X %-34s words=%-4d %s%s' % (
                action, key, NAMED.get(key, ''), ln, data[:24].hex(),
                '  <ALL ZERO>' if allzero else ('...' if ln * 2 > 24 else '')))
        return recs

    for i, (L, spl, apl) in enumerate(psd):
        if L:
            parse_ps('PersistentStore[%d]' % i, L)
    for i, (L, spl, apl) in enumerate(psd):
        if spl:
            parse_ps('StackPersistentStore[%d]' % i, spl)
    for i, (L, spl, apl) in enumerate(psd):
        if apl:
            parse_ps('AppPersistentStore[%d]' % i, apl)


main(sys.argv[1])
