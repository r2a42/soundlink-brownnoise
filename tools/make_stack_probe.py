#!/usr/bin/env python3
"""Build the Route A2 probe: the official Bose 3.0.3 DFU with a harmless change
in the unsigned stack area and every checksum recomputed.

Usage:
  python tools/make_stack_probe.py [--out PATH] [--force]

An existing output file is never overwritten unless --force is given.

This script only reads and writes files. It never opens the USB device.
Downloading the result to the speaker is a separate, manual step that needs
the owner's go-ahead (see README, Route A2).

The patch goes in the const area's gap. CSR's reference gordon stack
(repo/firmware/assisted/unified/gordon/stack_unsigned.xdv) places word 0x4000,
then jumps to 0x4080. The DFU fills const words 1..127 with FFFF, and nothing
is linked there. Four words in that gap become FFFE 0000 0000 FFFE. That keeps
the 16-bit word sum and XOR of the area unchanged, in case the stack
self-checks with either. Only the stack CRC-32, file CRC and suffix CRC are
recomputed. The signed PS keys and filesystem are left untouched.
"""
import argparse, hashlib, os, struct, sys, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from csrdfu import parse_header

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "firmware/bose/minnow_3.0.3/Minnow_3.0.3_stack_plus_app.dfu")
SRC_SHA256 = "5ae3bc9655af1b80eb78ebe3610eb58473edd715c885f8cdffc3f1b66be4659e"
OUT = os.path.join(ROOT, "firmware/bose/probe/Minnow_3.0.3_stack_probe1.dfu")

GAP = range(1, 128)            # const words that are gap fill in the source image
PATCH_AT = 0x40                # first patched word, mid-gap
PATCH = (0xFFFE, 0x0000, 0x0000, 0xFFFE)

def check(cond, msg):
    """Safety check that also runs under python -O (unlike assert)."""
    if not cond:
        raise SystemExit(f"make_stack_probe: {msg}")

def crc(data):
    return (zlib.crc32(data) ^ 0xFFFFFFFF) & 0xFFFFFFFF

def layout(d):
    """Offsets of the stack area and the three CRC fields; checks every CRC is valid."""
    h = parse_header(d)
    stacks = [ln for *_, ln in h["ssd"] if ln]
    check(len(stacks) == 1, "expected one stack area")
    st = h["header_length"] + h["desc_len"]
    check(d[st:st + 8] == b"CSRbcfw1", f"stack id is {d[st:st + 8]!r}")
    pdl, = struct.unpack_from("<I", d, st + 12)
    cdl, = struct.unpack_from("<H", d, st + 16)
    end = st + 20 + pdl + cdl
    check(end <= st + stacks[0], "stack data longer than its area")
    fcrc = h["file_length"] - 4
    check(len(d) == h["file_length"] + 16 and d[-8:-5] == b"UFD" and d[-5] == 16, "DFU suffix")
    L = dict(stack=st, const=st + 20 + pdl, cdl=cdl, stack_crc=st + 8, stack_end=end,
             file_crc=fcrc, suffix_crc=len(d) - 4)
    check(crc(d[st + 12:end]) == struct.unpack_from("<I", d, st + 8)[0], "stack CRC")
    check(crc(d[:fcrc]) == struct.unpack_from("<I", d, fcrc)[0], "file CRC")
    check(crc(d[:-4]) == struct.unpack_from("<I", d, len(d) - 4)[0], "suffix CRC")
    return L

def words(d, off, n):
    return list(struct.unpack_from(f"<{n}H", d, off))

def relpath(f):
    try:
        return os.path.relpath(f, ROOT)
    except ValueError:          # another drive on Windows
        return os.path.abspath(f)

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--force", action="store_true", help="overwrite an existing output file")
    a = ap.parse_args()
    txt = os.path.splitext(a.out)[0] + ".txt"
    for f in (a.out, txt):
        check(a.force or not os.path.exists(f), f"{f} exists; pass --force to overwrite it")

    src = open(SRC, "rb").read()
    got = hashlib.sha256(src).hexdigest()
    check(got == SRC_SHA256, f"source DFU is not the official 3.0.3 file ({got})")
    L = layout(src)
    check(words(src, L["const"], 1) == [0], "const word 0 changed")
    gap = words(src, L["const"] + 2 * GAP.start, len(GAP))
    check(all(w == 0xFFFF for w in gap), "const gap is not FFFF fill")

    d = bytearray(src)
    p = L["const"] + 2 * PATCH_AT
    struct.pack_into(f"<{len(PATCH)}H", d, p, *PATCH)
    old = words(src, p, len(PATCH))
    check(sum(old) & 0xFFFF == sum(PATCH) & 0xFFFF, "patch changes the 16-bit word sum")
    check(old[0] ^ old[1] ^ old[2] ^ old[3] == PATCH[0] ^ PATCH[1] ^ PATCH[2] ^ PATCH[3], "patch changes the word XOR")

    struct.pack_into("<I", d, L["stack_crc"], crc(d[L["stack"] + 12:L["stack_end"]]))
    struct.pack_into("<I", d, L["file_crc"], crc(d[:L["file_crc"]]))
    struct.pack_into("<I", d, L["suffix_crc"], crc(d[:-4]))
    d = bytes(d)

    # Self-check: every CRC valid, and the only changed bytes are the patch and the three CRCs.
    check(layout(d) == L, "layout changed after patching")
    allowed = set(range(p, p + 2 * len(PATCH)))
    for k in ("stack_crc", "file_crc", "suffix_crc"):
        allowed |= set(range(L[k], L[k] + 4))
    changed = {i for i in range(len(d)) if d[i] != src[i]}
    check(changed and changed <= allowed, f"unexpected changed bytes: {sorted(changed - allowed)[:16]}")

    sha = hashlib.sha256(d).hexdigest()
    rel = lambda o: f"file {o:#09x}"
    report = [
        f"source   {relpath(SRC)}  sha256 {SRC_SHA256}",
        f"output   {relpath(a.out)}  sha256 {sha}",
        f"patch    const words {PATCH_AT:#x}..{PATCH_AT + len(PATCH) - 1:#x} ({rel(p)}): "
        + " ".join(f"{w:04X}" for w in old) + " -> " + " ".join(f"{w:04X}" for w in PATCH),
    ]
    for k in ("stack_crc", "file_crc", "suffix_crc"):
        o = L[k]
        report.append(f"{k:11s}{rel(o)}: {src[o:o+4][::-1].hex()} -> {d[o:o+4][::-1].hex()}")
    report.append(f"bytes changed: {len(changed)}; all CRCs verified; PS keys and filesystem untouched")
    text = "\n".join(report) + "\n"
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    open(a.out, "wb").write(d)
    open(txt, "w").write(text)
    print(text, end="")

if __name__ == "__main__":
    main()
