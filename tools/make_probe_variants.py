#!/usr/bin/env python3
"""Build the FS/PS probe variants: official Bose 3.0.3 DFU with one minimal,
checksum-consistent edit per area, to map where the speaker's loader checks.

Usage:
  python tools/make_probe_variants.py [--out-dir DIR] [--force]

Writes (default firmware/bose/probe/, which .gitignore covers):

  probe2_fs_pad.dfu      two bit flips in dword padding between FS files,
                         canceled against each other so the FS body XOR stays
                         0. RSA signature stale. Asks: does the signature cover
                         padding, or only file data?
  probe3_fs_xorfix.dfu   one byte changed inside /tts/rphrases_us, filesystem
                         repacked with csrfspack so the body XOR is 0 again.
                         RSA signature stale. The 2026-09-20 probe changed
                         data with the XOR stale and got errFIRMWARE; this one
                         separates the XOR check from the signature check.
  probe4_ps_unsigned.dfu one inert, unnamed key (0x2290, one zero word)
                         appended to the official file's EMPTY, UNSIGNED
                         ps[0] area, CRC fixed. Asks: does the loader enforce
                         the signature on non-empty PS areas, given it already
                         accepts an unsigned empty one?

Each build: extract the official container (csrpack), edit the area bytes,
re-emit with csrpack --rebuild (recomputes PS CRCs, file_crc, suffix CRC and
refreshes the length tables), then self-verify: csrverify must pass and the
diff against the official file must match the expected byte set.

The 2026-09-20 probe (rphrases data byte, XOR stale -> errFIRMWARE) and the
2026-09-24 probe (stack const gap, CRCs fixed -> errFILE) are documented in
the top-level README. probe1 is built by tools/make_stack_probe.py.

This script only reads and writes files. It never opens the USB device.
Downloading any of these to the speaker is a separate, manual step that
needs the owner's go-ahead (README, "Ground rules").
"""
import argparse, hashlib, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# Reason: the readback tool dfu_upload.py lives in this same directory, and on 2026-10-04 I
# failed to find it at a guessed path, concluded no readback tool existed, and flashed seven
# times without verification -- which cost the first unit. An in-tree copy makes that
# failure mode impossible. See docs/POST-MORTEM-2026-10-04.md.
NB = os.path.join(ROOT, "tools", "csr")
SRC = os.path.join(ROOT, "firmware", "bose", "minnow_3.0.3",
                   "Minnow_3.0.3_stack_plus_app.dfu")
SRC_SHA256 = "5ae3bc9655af1b80eb78ebe3610eb58473edd715c885f8cdffc3f1b66be4659e"
OUT_DIR = os.path.join(ROOT, "firmware", "bose", "probe")
WORK = os.path.join(ROOT, "build", "probe_variants")

# FS-body offsets inside the fs area (== offsets in csrpack's 04_fs0.bin).
FS_PAD_FLIPS = (0x04B032, 0x06C07A)   # bit0 of each; flips cancel in the XOR
RPHRASE_OFF = 4096                    # byte inside /tts/rphrases_us to change
PS_KEY_ID = 0x2290                    # unnamed in pskeys_gordon.json
PS_KEY_WORDS = (0x0000,)


def check(cond, msg):
    if not cond:
        raise SystemExit(f"make_probe_variants: {msg}")


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    check(r.returncode == 0,
          f"{' '.join(os.path.basename(c) for c in cmd)} failed:\n{r.stdout}\n{r.stderr}")
    return r.stdout


def fs_xor(fs):
    """16-bit XOR over the FS body from the 'iFel' magic (csrpack's rule)."""
    off = fs.find(b"iFel")
    check(off >= 0, "no iFel magic in filesystem area")
    siw = struct_unpack_pdp_u32(fs, off + 4)
    x = 0
    for w in range(siw):
        x ^= int.from_bytes(fs[off + 2 * w:off + 2 * w + 2], "little")
    return x


def struct_unpack_pdp_u32(b, o):
    import struct as _s
    v, = _s.unpack_from("<I", b, o)
    return ((v >> 16) & 0xFFFF) | ((v & 0xFFFF) << 16)


def extract(tag):
    """csrpack --extract the official file into a fresh work dir; return its dir."""
    d = os.path.join(WORK, tag)
    run([sys.executable, os.path.join(NB, "csrpack.py"), "--extract", SRC, d + "/"])
    return d


def rebuild(tag, out_path):
    """csrpack --rebuild: official file + edited areas -> new container."""
    run([sys.executable, os.path.join(NB, "csrpack.py"), "--rebuild", SRC,
        os.path.join(WORK, tag) + "/", out_path])


def diff_bytes(new_path):
    a = open(SRC, "rb").read()
    b = open(new_path, "rb").read()
    check(len(a) == len(b),
          f"{os.path.basename(new_path)}: length {len(b)} != official {len(a)}")
    return [i for i in range(len(a)) if a[i] != b[i]]


def verify(new_path):
    out = run([sys.executable, os.path.join(NB, "csrverify.py"), new_path])
    check("ALL CHECKSUMS REPRODUCE" in out, f"{new_path}: csrverify did not pass:\n{out}")


def read_area(tag, name):
    return open(os.path.join(WORK, tag, name), "rb").read()


def write_area(tag, name, data):
    open(os.path.join(WORK, tag, name), "wb").write(data)


def report(path, lines):
    txt = os.path.splitext(path)[0] + ".txt"
    open(txt, "w").write("\n".join(lines) + "\n")
    print("\n".join(lines) + "\n")


def sha256(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def build_probe2(force):
    out = os.path.join(OUT_DIR, "probe2_fs_pad.dfu")
    if not force and os.path.exists(out):
        return f"skip {out} (exists)"
    tag = "probe2"
    d = extract(tag)
    fs = bytearray(read_area(tag, "04_fs0.bin"))
    before = bytes(fs)
    for off in FS_PAD_FLIPS:
        fs[off] ^= 0x01                # bit0 of the low pad byte
    check(fs_xor(bytes(fs)) == 0, "probe2: pad flips did not cancel in the FS XOR")
    write_area(tag, "04_fs0.bin", bytes(fs))
    rebuild(tag, out)
    verify(out)
    changed = diff_bytes(out)
    fs_file_off = 0x0BFF4C            # fs area start in the container (region map)
    expected = ({fs_file_off + o for o in FS_PAD_FLIPS}
                | set(range(0x1AE08C, 0x1AE090))    # file_crc
                | set(range(0x1AE0A0 - 4, 0x1AE0A0)))  # suffix dwCRC
    check(set(changed) <= expected,
          f"probe2: unexpected changed bytes {[hex(c) for c in sorted(set(changed) - expected)]}")
    report(out, [
        f"probe2_fs_pad: bit flips in FS dword padding at FS offsets "
        f"{[hex(o) for o in FS_PAD_FLIPS]} (cancel in the body XOR).",
        f"signature: stale (copied).  fs XOR after edit: 0 (verified).",
        f"source  {SRC}  sha256 {SRC_SHA256}",
        f"output  {out}  sha256 {sha256(out)}",
        f"container bytes changed: {len(changed)} at {[hex(c) for c in changed]}",
        f"csrverify: ALL CHECKSUMS REPRODUCE",
    ])


def build_probe3(force):
    out = os.path.join(OUT_DIR, "probe3_fs_xorfix.dfu")
    if not force and os.path.exists(out):
        return f"skip {out} (exists)"
    tag = "probe3"
    d = extract(tag)
    fs_before = read_area(tag, "04_fs0.bin")
    # dump the FS tree, flip one byte of rphrases_us
    fdir = os.path.join(WORK, tag + "_files")
    run([sys.executable, os.path.join(NB, "dumpfs.py"),
         os.path.join(WORK, tag, "04_fs0.bin"), fdir + "/"])
    rp = None
    for base, _, files in os.walk(fdir):
        for f in files:
            if f == "rphrases_us":
                rp = os.path.join(base, f)
    check(rp, "rphrases_us not found in the filesystem dump")
    rdata = bytearray(open(rp, "rb").read())
    check(len(rdata) == 10486, f"rphrases_us is {len(rdata)} bytes, expected 10486")
    old = rdata[RPHRASE_OFF]
    rdata[RPHRASE_OFF] ^= 0xFF
    open(rp, "wb").write(bytes(rdata))
    # repack the filesystem (recomputes the body XOR; signature copied stale)
    fs_new_path = os.path.join(WORK, tag + "_fs.bin")
    run([sys.executable, os.path.join(NB, "csrfspack.py"), "--replace",
         os.path.join(WORK, tag, "04_fs0.bin"), "/tts/rphrases_us", rp, fs_new_path])
    fs_new = open(fs_new_path, "rb").read()
    check(len(fs_new) == len(fs_before),
          f"probe3: repacked FS is {len(fs_new)} bytes, official area is {len(fs_before)}")
    check(fs_xor(fs_new) == 0, "probe3: repacked FS body XOR is not 0")
    check(fs_new[8:136] == fs_before[8:136], "probe3: RSA signature block changed")
    # sanity: the repack of the UNCHANGED area is byte-identical (roundtrip
    # already proven), so the only intended deltas are the byte + its XOR fixup
    write_area(tag, "04_fs0.bin", fs_new)
    rebuild(tag, out)
    verify(out)
    changed = diff_bytes(out)
    fs_file_off = 0x0BFF4C
    in_fs = [c - fs_file_off for c in changed if fs_file_off <= c < fs_file_off + len(fs_new)]
    outside = [c for c in changed if not (fs_file_off <= c < fs_file_off + len(fs_new))]
    expected_outside = set(range(0x1AE08C, 0x1AE090)) | set(range(0x1AE09C, 0x1AE0A0))
    check(set(outside) <= expected_outside,
          f"probe3: changes outside the FS area: {[hex(c) for c in outside]}")
    report(out, [
        f"probe3_fs_xorfix: one byte of /tts/rphrases_us (FS offset {hex(in_fs[0]) if in_fs else '?'}) "
        f"changed {old:02x} -> {old ^ 0xFF:02x}; filesystem repacked with csrfspack "
        f"(body XOR 0, RSA signature stale).",
        f"changed bytes inside the FS area: {len(in_fs)} at FS offsets "
        f"{[hex(o) for o in in_fs]}",
        f"changed bytes outside the FS area (container CRCs): "
        f"{[hex(c) for c in outside]}",
        f"source  {SRC}  sha256 {SRC_SHA256}",
        f"output  {out}  sha256 {sha256(out)}",
        f"csrverify: ALL CHECKSUMS REPRODUCE",
    ])


def build_probe4(force):
    out = os.path.join(OUT_DIR, "probe4_ps_unsigned.dfu")
    if not force and os.path.exists(out):
        return f"skip {out} (exists)"
    tag = "probe4"
    d = extract(tag)
    import struct
    ps_old = read_area(tag, "01_ps0.bin")
    check(ps_old == bytes.fromhex("00000000") + struct.pack("<I", 0xDEBB20E3),
          f"probe4: official ps[0] is not the expected empty area: {ps_old.hex()}")
    rec = (struct.pack("<HHH", 2, PS_KEY_ID, len(PS_KEY_WORDS))
           + struct.pack(f"<{len(PS_KEY_WORDS)}H", *PS_KEY_WORDS))
    body = struct.pack("<HH", 0, 1) + rec
    crc = __import__("zlib").crc32(body) ^ 0xFFFFFFFF
    write_area(tag, "01_ps0.bin", body + struct.pack("<I", crc))
    rebuild(tag, out)
    verify(out)
    a = open(SRC, "rb").read()
    b = open(out, "rb").read()
    check(len(b) == len(a) + len(rec),
          f"probe4: output is {len(b)} bytes, expected official + {len(rec)}")
    shift = len(rec)                  # everything from the FS area on moves by this
    ps_file_off, fs_file_off = 0x0BF004, 0x0BFF4C
    # regions that must match: before the ps area (byte-for-byte), and from the
    # fs area on (byte-for-byte at +shift) -- header bookkeeping and file_crc
    # are the expected exceptions
    pre = [i for i in range(ps_file_off) if a[i] != b[i]]
    # official file_crc (0x1AE08C..0x1AE08F) legitimately differs; new file_crc
    # sits at the same offset+shift with the new value
    post = [i for i in range(fs_file_off, len(a) - 4)
            if fs_file_off <= i < len(a) - 4
            and not (0x1AE08C <= i < 0x1AE090)
            and a[i] != b[i + shift]]
    expected_pre = {0xA, 0xB, 0xC, 0xD}   # file_length field (u32 @ 0xA)
    # psd[0].ps length entry lives in the header descriptor table; find it by
    # allowing any header offset in 0x1a8..0x2a8 (the psd table region)
    bad_pre = [i for i in pre if i not in expected_pre and not (0x100 <= i < 0x300)]
    check(not bad_pre, f"probe4: unexpected header changes at {[hex(i) for i in bad_pre]}")
    check(not post, f"probe4: FS area changed beyond the shift: {[hex(i) for i in post[:8]]}")
    report(out, [
        f"probe4_ps_unsigned: empty unsigned ps[0] area gains one key: "
        f"action=2 key=0x{PS_KEY_ID:04x} words={len(PS_KEY_WORDS)} "
        f"value={(' '.join('%04x' % w for w in PS_KEY_WORDS))}. CRC fixed; "
        f"no signature exists on this area in the official file either.",
        f"official ps[0] was 8 bytes (zero keys); probe area is "
        f"{8 + len(rec)} bytes; FS area and container tail shift by {shift} bytes "
        f"and are otherwise byte-identical (verified).",
        f"header changes: file_length + ps[0] length descriptor only "
        f"({len(pre)} bytes at {[hex(i) for i in pre]})",
        f"source  {SRC}  sha256 {SRC_SHA256}",
        f"output  {out}  sha256 {sha256(out)}",
        f"csrverify: ALL CHECKSUMS REPRODUCE",
    ])


def main():
    global OUT_DIR, WORK
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out-dir", default=OUT_DIR)
    ap.add_argument("--force", action="store_true",
                    help="overwrite existing outputs and work dirs")
    a = ap.parse_args()
    OUT_DIR, WORK = a.out_dir, os.path.join(WORK, "run")
    if a.force and os.path.exists(WORK):
        import shutil
        shutil.rmtree(WORK)
    src = open(SRC, "rb").read()
    check(hashlib.sha256(src).hexdigest() == SRC_SHA256,
          "source DFU is not the official 3.0.3 file")
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)
    print(build_probe2(a.force))
    print(build_probe3(a.force))
    print(build_probe4(a.force))


if __name__ == "__main__":
    main()
