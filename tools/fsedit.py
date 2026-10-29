#!/usr/bin/env python3
"""fsedit: write custom content into the Bose SoundLink Micro's signed
filesystem, keeping Bose's RSA signature and digest valid.

Proven end to end 2026-09-27 (probe8: accepted, booted, persisted).

WHAT THIS EXPLOITS (docs/dfu-signature-scheme.md):
  1. The fs signature hash (8-chain MD5 variant) only READS bytes 0..33
     of each 64-byte content block — bytes 34..62 are blind: edits there
     leave Bose's signature mathematically valid.
  2. The fs 32-bit digest (the loader's other fs check) is dfubuild's
     GF(2)-linear checksum: f(x^e) = f(x) ^ L(e).  L is cancelled by a
     compensation set of blind flips (GF(2) solve), leaving the digest
     field byte-identical.
  3. The body 16-bit XOR must stay 0 (even total flip parity).

CONSTRAINTS on edits: each edited byte must lie in bytes 34..62 of its
64-byte content block (content = 4-byte digest field + body), and inside
file data (not table/names/trailer).  ~45% of every file qualifies.
Arbitrary chosen values are fine: the body XOR is rebalanced automatically
(flips at pool words) before the digest solve.

USAGE
  python tools/fsedit.py --edit AREA_BYTE_OFFSET=NEWHEX ... --out OUT.dfu
  python tools/fsedit.py --demo --out OUT.dfu     # marker + noise demo
  AREA_BYTE_OFFSET is the offset within the fs AREA (fsr_dfu1 = 0);
  the fs body starts at area byte 140 (0x8C).

Pipeline: edits -> blind check -> XOR balance (pool words) -> digest delta
via dfubuild oracle -> compensation solve (pool: build/sign/dfutest/L_pool.json)
-> full verify (digest byte-identical, RSA block invariant, XOR 0) -> csrpack
rebuild -> csrverify.  Flashing is a separate manual step (bose-dfu).
"""
import argparse, json, os, struct, subprocess, sys, glob

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# The CSR packing/verifying tools are IN-TREE at tools/csr, so this project
# is self-contained; there is no out-of-tree fallback.
NB = os.path.join(ROOT, "tools", "csr")
DFUBUILD = os.path.join(ROOT, "adk", "root", "tools", "bin", "dfubuild.exe")
SRC = os.path.join(ROOT, "firmware", "bose", "minnow_3.0.3",
                   "Minnow_3.0.3_stack_plus_app.dfu")
WORK = os.path.join(ROOT, "build", "fsedit")
POOL = os.path.join(ROOT, "build", "hook", "slack_pool.json")
# 2026-09-27: compensation moved here (body 0x35a5e+) after flipping
# data_us BODY corrupted the TTS prompt database (voice prompts died).
# 2026-09-29 CORRECTION - the "unclaimed inter-file slack" rationale was
# FALSE and is retained here as a warning. The fs table has NO gap: the
# data_us entry spans body 0x1cc..0x35b54 and NowSpeakTTS.kap starts at
# exactly 0x35b54. SLACK_RANGE is therefore the last 256 bytes OF data_us.
# It is safe empirically, not structurally: probes 11b/11c/15b/18b/22 all
# flipped bytes in this range and the owner confirmed prompts, pairing and
# BT still worked - the TTS chunk directory evidently does not reference
# the tail. Treat it as "tolerated", and re-test VOICE PROMPTS after any
# flash that lands compensation here.
# (The probe11c run log, 2026-09-28, found this; it never reached the code.)
# Original data_us pool: build/sign/dfutest/L_pool.json
DIGEST_OFFICIAL = 0xD38F3924

sys.path.insert(0, HERE)
from csrhash import fs_block


def die(msg):
    raise SystemExit(f"fsedit: {msg}")


def check(cond, msg):
    if not cond:
        die(msg)


def pdp(x):
    return ((x >> 16) & 0xFFFF) | ((x & 0xFFFF) << 16)


def load_body():
    """The official fs body as a bytearray (area byte 140 .. area end)."""
    d = open(SRC, "rb").read()
    ia = d.find(b"fsr_dfu1")
    check(ia >= 0, "no fs area in official image")
    siw = pdp(struct.unpack_from("<I", d, ia + 0x90)[0])
    area = d[ia:ia + 0x8C + siw * 2]
    return bytearray(area[140:])


def body_xor(body):
    x = 0
    for k in range(0, len(body), 2):
        x ^= struct.unpack_from("<H", body, k)[0]
    return x


def blind(area_byte_off):
    """Content offset = area byte - 136; blind = bytes 34..62 of its block."""
    c = area_byte_off - 136
    check(c >= 0, f"offset {area_byte_off:#x} is inside the header")
    return 34 <= (c % 64) <= 62


def in_file_data(body_off, body=None):
    """True if body byte offset is inside file DATA (not table/names/trailer)."""
    if body is None:
        body = load_body()
    siw = pdp(struct.unpack_from("<I", body, 4)[0])
    nfiles = struct.unpack_from("<H", body, 8)[0]
    p, ranges = 10, []
    for i in range(nfiles):
        fno, doff, sz = struct.unpack_from("<III", body, p)
        p += 12
        fno, doff, sz = pdp(fno), pdp(doff), pdp(sz)
        if not (fno >> 24) & 0x80:
            ranges.append((doff * 2, doff * 2 + sz))
    table_end = 10 + nfiles * 12
    first_data = min(r[0] for r in ranges)
    trailer = siw * 2 - 8
    if body_off < table_end:
        return False, "block table"
    if body_off < first_data:
        return False, "name pool"
    if body_off >= trailer:
        return False, "trailer"
    return True, "file data"


def oracle_digest(body):
    """dfubuild's digest of this body (the loader's check).
    dfubuild SILENTLY DROPS a filesystem whose body XOR != 0 (it calls the
    input 'redundant' and emits a 988-byte empty container) - never feed it
    an unbalanced body; build() balances before calling this."""
    check(body_xor(body) == 0, "oracle body XOR != 0 - dfubuild would drop it")
    os.makedirs(WORK, exist_ok=True)
    fs = os.path.join(WORK, "probe.fs")
    with open(fs, "w") as fh:
        for w in range(len(body) // 2):
            fh.write(f"@{w:06x}   {struct.unpack_from('<H', body, 2*w)[0]:04x}\n")
    out = os.path.join(WORK, "probe.dfu")
    r = subprocess.run([DFUBUILD, "-f", out, "-uv", "0x05A7", "-up", "0x4022",
                        "-i", "", "-h", fs], capture_output=True, timeout=600)
    check(b"successfully" in r.stdout, "dfubuild failed: " + r.stdout.decode(errors="replace"))
    d = open(out, "rb").read()
    i = d.find(b"fsr_dfu1")
    check(i >= 0, "dfubuild produced no fs area")
    return struct.unpack_from("<I", d, i + 0x88)[0]


SLACK_RANGE = (0x35A54, 0x35B54)   # data_us TAIL - tolerated, not unclaimed (see note above)

def blind_pool_words(pool, body, edit_bytes):
    """Pool words usable for balancing/compensation: bit0 byte blind, in file
    data or in the inter-file slack, and not a byte the user chose to edit."""
    out = []
    for k in pool["vals"]:
        p = int(k, 16)
        if p * 2 in edit_bytes:
            continue
        if not blind(p * 2 + 140):
            continue
        if SLACK_RANGE[0] <= p * 2 < SLACK_RANGE[1]:
            out.append(p)
            continue
        ok, _ = in_file_data(p * 2, body)
        if ok:
            out.append(p)
    return sorted(out)


def flips_for_value(V, words, body, edit_bytes):
    """One flip per set bit of V (a 16-bit body-XOR residue), at pool words,
    each at a blind byte that no chosen edit touches. Returns [(byte_off, mask)].
    These flips' own L-contribution rides along into the measured digest
    delta, so no per-bit L knowledge is required."""
    flips, used = [], set()
    for bit in range(16):
        if not (V >> bit) & 1:
            continue
        for p in words:
            o = p * 2 + bit // 8
            if p in used or o in edit_bytes or not blind(o + 140):
                continue
            ok, _ = in_file_data(o, body)
            if ok:
                used.add(p)
                flips.append((o, 1 << (bit % 8)))
                break
        else:
            die(f"no clean pool word to balance XOR bit {bit}")
    return flips


def solve_compensation(target, pool, words):
    """Find a subset of pool positions whose pair-delta XOR == target.
    Effective edit = subset (+ ref if odd cardinality) -> parity even."""
    ref = int(pool["ref"], 16)
    vals = {int(k, 16): int(v, 16) for k, v in pool["vals"].items()}
    items = words
    # augmented gaussian elimination: basis[pivot] = (vector, mask, value)
    basis = {}
    for idx, p in enumerate(items):
        v, m = vals[p], 1 << idx
        while v:
            b = v.bit_length() - 1
            if b in basis:
                bv, bm = basis[b]
                v ^= bv
                m ^= bm
            else:
                basis[b] = (v, m)
                v = 0
                break
    # solve for target
    acc, mask = target, 0
    while acc:
        b = acc.bit_length() - 1
        check(b in basis, "pool rank insufficient - measure more L vectors")
        bv, bm = basis[b]
        acc ^= bv
        mask ^= bm
    subset = [items[i] for i in range(len(items)) if (mask >> i) & 1]
    flips = list(subset)
    if len(subset) % 2:
        flips.append(ref)
    return flips


def build(edits, out_path, verbose=True):
    """edits: list of (area_byte_offset, new_byte_value)."""
    body = load_body()
    edit_bytes = set()                 # body byte offsets the user chose
    for off, val in edits:
        check(blind(off), f"edit at area {off:#x} is NOT in a blind window (bytes 34..62 of its block)")
        ok, where = in_file_data(off - 140, body)
        check(ok, f"edit at area {off:#x} lands in the {where}")
        body[off - 140] = val
        edit_bytes.add(off - 140)
    pool = json.load(open(POOL))
    words = blind_pool_words(pool, body, edit_bytes)
    # 1. Arbitrary chosen content has no reason to be XOR-even: balance it
    #    with one flip per set bit at pool words (dfubuild refuses odd XOR,
    #    and so would the loader).
    V = body_xor(body)
    bal = []
    if V:
        bal = flips_for_value(V, words, body, edit_bytes)
        for o, m in bal:
            body[o] ^= m
        if verbose:
            print(f"XOR balance: {len(bal)} flips at pool words (residue {V:04x})")
        # balance words are consumed: the compensation must not reuse them
        # (a second bit0 flip on the same word would cancel it out)
        used_words = {o // 2 for o, m in bal}
        words = [p for p in words if p not in used_words]
    # 2. digest delta of (edits + balance) vs official
    d_new = oracle_digest(body)
    delta = DIGEST_OFFICIAL ^ d_new
    if verbose:
        print(f"desired edits: {len(edits)} bytes; digest delta = {delta:08x}")
    if delta:
        comp = solve_compensation(delta, pool, words)
        if verbose:
            print(f"compensation: {len(comp)} one-bit flips in data_us")
        for p in comp:
            off = p * 2            # body word -> body byte (bit0 flips)
            check(blind(off + 140), f"comp word {p:#x} not blind?!")
            check(off not in edit_bytes, f"comp word {p:#x} collides with a chosen edit")
            body[off] ^= 1
    # ---- verify everything ----
    check(oracle_digest(body) == DIGEST_OFFICIAL, "final digest mismatch")
    official = load_body()
    dgbytes = struct.pack("<I", DIGEST_OFFICIAL)
    blk_new = fs_block(dgbytes + bytes(body))
    blk_old = fs_block(dgbytes + bytes(official))
    check(blk_new == blk_old, "RSA block changed")
    check(body_xor(body) == 0, "body XOR broken")
    # assemble the image
    os.makedirs(WORK, exist_ok=True)
    extract_dir = os.path.join(WORK, "x")
    if not os.path.exists(os.path.join(extract_dir, "manifest.json")):
        subprocess.run([sys.executable, os.path.join(NB, "csrpack.py"), "--extract",
                        SRC, extract_dir + "/"], capture_output=True, timeout=300)
    open(os.path.join(extract_dir, "04_fs0.bin"), "wb").write(
        b"fsr_dfu1" + _official_sig() + struct.pack("<I", DIGEST_OFFICIAL) + bytes(body))
    subprocess.run([sys.executable, os.path.join(NB, "csrpack.py"), "--rebuild", SRC,
                    extract_dir + "/", out_path], capture_output=True, timeout=300)
    r = subprocess.run([sys.executable, os.path.join(NB, "csrverify.py"), out_path],
                       capture_output=True, text=True, timeout=300)
    check("ALL CHECKSUMS REPRODUCE" in r.stdout, "csrverify failed:\n" + r.stdout)
    diffs = []
    a = open(SRC, "rb").read()
    b = open(out_path, "rb").read()
    if len(a) == len(b):
        diffs = [i for i in range(len(a)) if a[i] != b[i]]
    if verbose:
        print(f"OK: {out_path} ({len(diffs)} bytes differ from official)")
    return out_path


def _official_sig():
    d = open(SRC, "rb").read()
    i = d.find(b"fsr_dfu1")
    return d[i + 8:i + 0x88]


def demo_edits():
    """A recognizable marker written into data_us at blind byte offsets.
    Deep in the file (0x20000+): prompt audio data, so a corrupted byte is
    at worst a click in one prompt, nowhere near any index/header."""
    marker = b"ZCODE-OPEN-FW-2026"
    body = load_body()
    # choose blind byte offsets inside data_us (body 0x1cc..0x35b54)
    offs = []
    c = 0x20000
    while len(offs) < len(marker) and c < 0x30000:
        if blind(c + 140) and 0x1cc <= c < 0x35b54:
            offs.append(c + 140)
        c += 1
    check(len(offs) == len(marker), "not enough blind demo offsets")
    return [(o, marker[i]) for i, o in enumerate(offs)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edit", action="append", default=[],
                    help="AREA_BYTE_OFFSET=NEWHEX, e.g. 0x200=5a")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.demo:
        edits = demo_edits()
        print(f"demo: writing marker into data_us at {len(edits)} blind offsets")
    else:
        edits = []
        for e in args.edit:
            off, val = e.split("=")
            edits.append((int(off, 0), int(val, 0)))
    build(edits, args.out)


if __name__ == "__main__":
    main()
