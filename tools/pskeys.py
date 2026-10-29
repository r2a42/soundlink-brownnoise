#!/usr/bin/env python3
"""List the PS keys inside a CSR-dfu2 file with names from a firmware
pskeys.txt (e.g. adk/root/firmware/assisted/unified/gordon/pskeys.txt).

Usage: python pskeys.py <file.dfu> <pskeys.txt>
"""
import re
import struct
import sys

import csrdfu


def load_names(path):
    text = open(path, encoding="latin-1").read()
    names = {}
    for m in re.finditer(r"NAME\s*\n\s*(PSKEY_\w+)\s*\((0x[0-9a-fA-F]+)\)\s*\n\s*\nSUMMARY\s*\n\s*([^\n]*)", text):
        names[int(m.group(2), 16)] = (m.group(1), m.group(3).strip())
    return names


def ps_areas(d):
    h = csrdfu.parse_header(d)
    o = h["header_length"] + h["desc_len"]
    for _, _, ln in h["ssd"]:
        o += ln
    for _, _, ln in h["asd"]:
        o += ln
    for label, idx in (("PS", 1), ("STACK-PS", 2), ("APP-PS", 3)):
        for rec in h["psd"]:
            ln = rec[idx]
            if ln:
                _, recs, _ = csrdfu.parse_ps(d, o, ln)
                yield label, recs
                o += ln


def main():
    d = open(sys.argv[1], "rb").read()
    names = load_names(sys.argv[2])
    for label, recs in ps_areas(d):
        print(f"== {label} ({len(recs)} keys)")
        for _, key, data in recs:
            words = struct.unpack(f"<{len(data) // 2}H", data)
            name, summary = names.get(key, ("?", ""))
            val = " ".join(f"{w:04x}" for w in words[:10]) + (" ..." if len(words) > 10 else "")
            print(f"0x{key:04x} {name:40s} [{len(words):3d}] {val}")
            if summary:
                print(f"{'':7s}{summary}")


if __name__ == "__main__":
    main()
