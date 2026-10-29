#!/usr/bin/env python3
"""Parse and extract CSR BlueCore DFU files (CSR-dfu2) and fsr_dfu1 filesystem images.

Usage:
  python csrdfu.py info    <file.dfu>
  python csrdfu.py extract <file.dfu|ext.xuv|ext.bin> <outdir>

info prints ok/BAD for every check and exits 1 if anything is BAD.
extract keeps the filesystem's directory tree under fs_<offset>/.

Format reference: tools/csr-dfu-parser-ref/CSRDFU.bt (BlueCore01 DFU File Format Spec, AN093).
"""
import os, re, struct, sys, zlib

SIG_SIZE = 128
N_AREAS = 16
HDR_MIN = 8 + 2 + 4 + 2 + 64 + 24 + 20 * N_AREAS + 14 * N_AREAS + 20 * N_AREAS + 16 * N_AREAS
SUFFIX_LEN = 16

def pdp(x):
    return ((x >> 16) & 0xFFFF) | ((x & 0xFFFF) << 16)

def crc(data):
    return (zlib.crc32(data) ^ 0xFFFFFFFF) & 0xFFFFFFFF

def load_xuv(path):
    """Words of a .xuv file placed at their @addresses (from 0). Gaps are filled
    with FFFF (erased flash) and reported on stderr; a repeated address is an error."""
    mem = {}
    for line in open(path, "r", errors="replace"):
        m = re.match(r"@([0-9A-Fa-f]+)\s+([0-9A-Fa-f]{4})", line)
        if m:
            a = int(m.group(1), 16)
            if a in mem:
                raise SystemExit(f"{path}: address {a:#x} appears twice")
            mem[a] = int(m.group(2), 16)
    if not mem:
        raise SystemExit(f"{path}: no @address lines")
    n = max(mem) + 1
    if len(mem) != n:
        print(f"warning: {path}: {n - len(mem)} of {n} words missing, filled with FFFF", file=sys.stderr)
    return b"".join(struct.pack("<H", mem.get(a, 0xFFFF)) for a in range(n))

def parse_header(d):
    if len(d) < HDR_MIN:
        raise SystemExit(f"file too short for a CSR-dfu2 header ({len(d)} < {HDR_MIN} bytes)")
    h = {}
    o = 0
    h["file_id"] = d[0:8]; o = 8
    h["file_version"], = struct.unpack_from("<H", d, o); o += 2
    h["file_length"], = struct.unpack_from("<I", d, o); o += 4
    h["header_length"], = struct.unpack_from("<H", d, o); o += 2
    h["description"] = d[o:o + 64].rstrip(b"\0 "); o += 64
    (h["ss_len"], h["as_len"], h["ps_len"], h["sps_len"], h["aps_len"], h["desc_len"]) = struct.unpack_from("<6I", d, o); o += 24
    h["ssd"] = [struct.unpack_from("<QQI", d, o + 20 * i) for i in range(N_AREAS)]; o += 20 * N_AREAS
    h["asd"] = [struct.unpack_from("<HqI", d, o + 14 * i) for i in range(N_AREAS)]; o += 14 * N_AREAS
    h["psd"] = [struct.unpack_from("<QIII", d, o + 20 * i) for i in range(N_AREAS)]; o += 20 * N_AREAS
    h["fsd"] = [struct.unpack_from("<IHHHHI", d, o + 16 * i) for i in range(N_AREAS)]; o += 16 * N_AREAS
    if h["desc_len"]:
        h["long_description"] = d[o:o + h["desc_len"]].decode("utf-16le", "replace")
    return h

def parse_ps(d, o, ln):
    st = o
    if ln < 8 or st + ln > len(d):
        raise SystemExit(f"PS area at {st:#x} (len {ln}) does not fit the file")
    clear, keys = struct.unpack_from("<HH", d, o); o += 4
    recs = []
    for _ in range(keys):
        if o + 6 > st + ln:
            raise SystemExit(f"PS area at {st:#x}: key table overruns the area")
        act, key, l = struct.unpack_from("<HHH", d, o); o += 6
        recs.append((act, key, d[o:o + 2 * l])); o += 2 * l
    rest = st + ln - o
    if rest < 0:
        raise SystemExit(f"PS area at {st:#x}: key data overruns the area")
    signed = rest == SIG_SIZE + 4
    return clear, recs, signed

def ps_crc_ok(d, o, ln):
    return crc(d[o:o + ln - 4]) == struct.unpack_from("<I", d, o + ln - 4)[0]

def parse_fs(d, i):
    """Return (files, base, sig, size_words) for an fsr_dfu1 filesystem starting at offset i."""
    o = i + 8
    sig = d[o:o + SIG_SIZE]; o += SIG_SIZE
    o += 4  # checksum
    base = o
    magic = d[o:o + 4]; o += 4
    if magic != b"iFel":
        raise SystemExit(f"fsr_dfu1 at {i:#x}: bad magic {magic!r} (expected b'iFel')")
    size_words = pdp(struct.unpack_from("<I", d, o)[0]); o += 4
    if base + 2 * size_words > len(d):
        raise SystemExit(f"fsr_dfu1 at {i:#x}: size {size_words:#x} words runs past end of file")
    nfiles, = struct.unpack_from("<H", d, o); o += 2
    if o + 12 * nfiles > base + 2 * size_words:
        raise SystemExit(f"fsr_dfu1 at {i:#x}: file table ({nfiles} entries) runs past the filesystem")
    files = []
    for n in range(nfiles):
        fno, doff, size = (pdp(x) for x in struct.unpack_from("<III", d, o)); o += 12
        name_off, flags = fno & 0xFFFFFF, fno >> 24
        name = ""
        if name_off:
            p = base + name_off * 2
            if p + 2 > len(d):
                raise SystemExit(f"fsr_dfu1 at {i:#x}: entry {n} name offset out of range")
            ln, = struct.unpack_from("<H", d, p)
            name = d[p + 2:p + 2 + ln * 2].decode("utf-16le", "replace")
        files.append(dict(n=n, name=name, isdir=bool(flags & 0x80), flags=flags, off=doff, size=size))
    return files, base, sig, size_words

def fs_checks(d, base, sw):
    """(xor_ok, tail_ok): body words XOR to zero; body ends with the size copy and 'iFel'."""
    x = 0
    for w in struct.unpack_from(f"<{sw}H", d, base):
        x ^= w
    end = base + 2 * sw
    tail_ok = sw >= 6 and pdp(struct.unpack_from("<I", d, end - 8)[0]) == sw and d[end - 4:end] == b"iFel"
    return x == 0, tail_ok

def info(path):
    """Print the layout and every check; return the list of failed checks."""
    d = open(path, "rb").read()
    bad = []
    def ok(label, good):
        if not good:
            bad.append(label)
        return "ok" if good else "BAD"
    h = parse_header(d)
    fl = h["file_length"]
    print("file_id", h["file_id"], ok("file_id", h["file_id"] == b"CSR-dfu2"),
          "version", h["file_version"], "len", hex(fl), "hdr", hex(h["header_length"]))
    if bad:
        return bad
    extra = len(d) - fl
    print(f"file_length {fl:#x} actual {len(d):#x}",
          ok("file_length", extra in (0, SUFFIX_LEN)), "(suffix)" if extra == SUFFIX_LEN else "")
    print("description", h["description"], h.get("long_description", ""))
    o = h["header_length"] + h["desc_len"]
    for bc, fg, ln in h["ssd"]:
        if ln:
            sid = d[o:o + 8]; c, pdl = struct.unpack_from("<II", d, o + 8); cdl, ver = struct.unpack_from("<HH", d, o + 16)
            good = crc(d[o + 12:o + 20 + pdl + cdl]) == c and 20 + pdl + cdl <= ln
            print(f"STACK  id={sid} prog={pdl} const={cdl} ver={ver} crc={ok('stack crc', good)} (no signature field in format)")
            o += ln
    for vm, s, ln in h["asd"]:
        if ln:
            print(f"APP    vm={vm} len={ln}"); o += ln
    for label, idx in (("PS", 1), ("STACK-PS", 2), ("APP-PS", 3)):
        for rec in h["psd"]:
            ln = rec[idx]
            if ln:
                clear, recs, signed = parse_ps(d, o, ln)
                print(f"{label:9s} keys={len(recs)} clear={clear} signed={signed}")
                print(f"{label:9s} crc={ok(label + ' crc', ps_crc_ok(d, o, ln))}")
                for act, key, data in recs:
                    print(f"    0x{key:04x} act={act} len={len(data)//2:3d} {data[:32].hex()}")
                o += ln
    for rec in h["fsd"]:
        rl = rec[5]
        if rl:
            if d[o:o + 8] != b"fsr_dfu1":
                print("FS     id", d[o:o + 8], ok("fs id", False))
                o += rl
                continue
            files, base, sig, sw = parse_fs(d, o)
            print(f"FS     size_words={hex(sw)} files={len(files)} signature={'present' if any(sig) else 'absent'}")
            xo, to = fs_checks(d, base, sw)
            print(f"FS     xor={ok('fs xor', xo)} size_copy+iFel={ok('fs tail', to)} "
                  f"length={ok('fs length', base + 2 * sw == o + rl)}")
            for f in files:
                print(f"    {'DIR ' if f['isdir'] else 'file'} {f['name']!r:24s} size={f['size']}")
            o += rl
    if not ok("layout", o == fl - 4 and o + 4 <= len(d)):
        print(f"areas end at {o:#x}, expected file crc at {fl - 4:#x} BAD")
        return bad
    fcrc, = struct.unpack_from("<I", d, o)
    print("file crc", ok("file crc", crc(d[:o]) == fcrc))
    if extra <= 0:
        print("suffix absent"); return bad
    bcd, pid, vid, bcddfu = struct.unpack_from("<HHHH", d, o + 4)
    print(f"suffix bcdDevice={bcd:#06x} usb={vid:04x}:{pid:04x} bcdDFU={bcddfu:#06x}")
    print("suffix signature", ok("suffix signature", d[-8:-5] == b"UFD" and d[-5] == SUFFIX_LEN),
          "crc", ok("suffix crc", crc(d[:-4]) == struct.unpack_from("<I", d, len(d) - 4)[0]))
    return bad

def safe_relpath(p):
    """Validate a '/'-separated filesystem path and return it as a local relative path."""
    parts = p.split("/")
    for s in parts:
        if s in ("", ".", "..") or "\\" in s or ":" in s or "\0" in s:
            raise SystemExit(f"refusing unsafe filesystem name {p!r}")
    return os.path.join(*parts)

def fs_paths(files):
    """Map file index -> '/'-joined path. A directory entry's off is the 1-based
    index of its first child and size is its child count; entry 0 is the root."""
    paths = {0: ""} if files and files[0]["isdir"] else {}
    for f in files:
        if f["isdir"] and f["n"] in paths:
            parent = paths[f["n"]]
            for c in range(f["off"] - 1, f["off"] - 1 + f["size"]):
                if f["n"] < c < len(files) and c not in paths:
                    nm = files[c]["name"] or f"file{c}"
                    paths[c] = f"{parent}/{nm}" if parent else nm
    for f in files:
        if f["n"] not in paths and not f["isdir"]:
            print(f"warning: entry {f['n']} {f['name']!r} has no parent directory; extracted at top level", file=sys.stderr)
            paths[f["n"]] = f["name"] or f"file{f['n']}"
    return paths

def extract(path, outdir):
    if path.lower().endswith(".xuv"):
        d = load_xuv(path)
        os.makedirs(outdir, exist_ok=True)
        open(os.path.join(outdir, "image.bin"), "wb").write(d)
    else:
        d = open(path, "rb").read()
        os.makedirs(outdir, exist_ok=True)
    found = False
    if d[:8] == b"CSR-dfu2":
        h = parse_header(d)
        o = h["header_length"] + h["desc_len"]
        k = 0
        for bc, fg, ln in h["ssd"]:
            if ln:
                pdl, = struct.unpack_from("<I", d, o + 12); cdl, = struct.unpack_from("<H", d, o + 16)
                pre = "stack" if k == 0 else f"stack{k}"
                open(os.path.join(outdir, f"{pre}_prog.bin"), "wb").write(d[o + 20:o + 20 + pdl])
                open(os.path.join(outdir, f"{pre}_const.bin"), "wb").write(d[o + 20 + pdl:o + 20 + pdl + cdl])
                print(f"wrote {pre}_prog.bin / {pre}_const.bin")
                o += ln; k += 1; found = True
    root = os.path.realpath(outdir)
    i = d.find(b"fsr_dfu1")
    while i >= 0:
        files, base, sig, sw = parse_fs(d, i)
        fsdir = os.path.join(outdir, f"fs_{i:08x}")
        os.makedirs(fsdir, exist_ok=True)
        paths = fs_paths(files)
        for f in files:
            if f["isdir"]:
                continue
            data = d[base + f["off"] * 2: base + f["off"] * 2 + f["size"]]
            fn = os.path.join(fsdir, safe_relpath(paths[f["n"]]))
            if not os.path.realpath(fn).startswith(root + os.sep):
                raise SystemExit(f"refusing to write outside {outdir}: {fn}")
            os.makedirs(os.path.dirname(fn), exist_ok=True)
            open(fn, "wb").write(data)
            print(f"wrote {fn} ({len(data)} bytes)")
        found = True
        i = d.find(b"fsr_dfu1", base + sw * 2)
    if not found:
        print("nothing to extract (no stack area, no fsr_dfu1 filesystem)", file=sys.stderr)

def main(argv):
    nargs = {"info": 1, "extract": 2}
    if len(argv) < 2 or argv[1] not in nargs or len(argv) != 2 + nargs[argv[1]]:
        sys.stderr.write(__doc__)
        return 2
    try:
        if argv[1] == "info":
            bad = info(argv[2])
            if bad:
                print("BAD:", ", ".join(bad))
            return 1 if bad else 0
        extract(argv[2], argv[3])
    except OSError as e:
        raise SystemExit(f"error: {e}")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
