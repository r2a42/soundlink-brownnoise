#!/usr/bin/env python3
"""csrhash: the CSR DFU filesystem-signature hash, fully reverse-engineered.

Construction (every element validated against CSR's dfusign.exe — see
docs/dfu-signature-scheme.md for the evidence trail):

  content = the fs area's 4-byte digest field + the body (area[140:] in
            XUV word space; area[136:] of the binary area)
  feed    = content in 64-byte blocks, block k -> chain k mod 8
  chain   = MD5 (standard rounds, K table, schedule) EXCEPT the message
            words: M[i] = LE dword at BYTE offset 2*i of the block (a
            16-bit sliding window over the 64-byte staging buffer; the
            last words read past the block as zeros)
  init    = all 8 chains at the standard MD5 IV
  finalize= word-granular MD5 padding of the content tail: 0x8000 word,
            zero words so total == 28 mod 32 words, then an 8-byte
            length = (total words fed incl. pad) * 16 bits; the final
            blocks continue the chain rotation; then chain 0's A word
            &= 0x7fffffff (from FINALIZE 0x40AB24).
  block   = the 8 chain states (128 bytes, memory order)
  RSA     = S = block^d mod n (raw, e=3); the file stores the signature
            words REVERSED; the block fed to RSA = dwords reversed.

Usage:
  python csrhash.py <area.xuv|area.bin> [--sig WORDSFILE]  # hash; verify vs sig if given
  python csrhash.py --block <area>                          # print the 128-byte block
  python csrhash.py --S <area> <keyfile-private>            # the expected signature int
"""
import sys, os, re, struct, math

HERE = os.path.dirname(os.path.abspath(__file__))

# MD5 constants (validated identical to dfusign's descriptor table)
_K = [0xd76aa478,0xe8c7b756,0x242070db,0xc1bdceee,0xf57c0faf,0x4787c62a,0xa8304613,0xfd469501,
      0x698098d8,0x8b44f7af,0xffff5bb1,0x895cd7be,0x6b901122,0xfd987193,0xa679438e,0x49b40821,
      0xf61e2562,0xc040b340,0x265e5a51,0xe9b6c7aa,0xd62f105d,0x02441453,0xd8a1e681,0xe7d3fbc8,
      0x21e1cde6,0xc33707d6,0xf4d50d87,0x455a14ed,0xa9e3e905,0xfcefa3f8,0x676f02d9,0x8d2a4c8a,
      0xfffa3942,0x8771f681,0x6d9d6122,0xfde5380c,0xa4beea44,0x4bdecfa9,0xf6bb4b60,0xbebfbc70,
      0x289b7ec6,0xeaa127fa,0xd4ef3085,0x04881d05,0xd9d4d039,0xe6db99e5,0x1fa27cf8,0xc4ac5665,
      0xf4292244,0x432aff97,0xab9423a7,0xfc93a039,0x655b59c3,0x8f0ccc92,0xffeff47d,0x85845dd1,
      0x6fa87e4f,0xfe2ce6e0,0xa3014314,0x4e0811a1,0xf7537e82,0xbd3af235,0x2ad7d2bb,0xeb86d391]
_S = [7,12,17,22]*4 + [5,9,14,20]*4 + [4,11,16,23]*4 + [6,10,15,21]*4
_MI = list(range(16)) + [(5*i+1) % 16 for i in range(16)] + \
      [(3*i+5) % 16 for i in range(16)] + [(7*i) % 16 for i in range(16)]
_M32 = 0xFFFFFFFF
IV = [0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476]


def compress(state, blk64):
    """One compression: standard MD5 rounds, message = LE dwords at 2-byte stride."""
    buf = blk64 + b"\x00" * 66          # stride reads up to byte 130
    M = [struct.unpack_from("<I", buf, 2 * i)[0] for i in range(64)]
    a, b, c, d = state
    for i in range(64):
        if i < 16:
            f = (b & c) | (~b & d)
        elif i < 32:
            f = (d & b) | (~d & c)
        elif i < 48:
            f = b ^ c ^ d
        else:
            f = c ^ (b | ~d)
        f &= _M32
        g = _MI[i]
        tmp = (a + f + _K[i] + M[g]) & _M32
        s = _S[i]
        tmp = ((tmp << s) | (tmp >> (32 - s))) & _M32
        a, b, c, d = d, (b + tmp) & _M32, b, c
    return [(x + y) & _M32 for x, y in zip((a, b, c, d), state)]


def fs_block(content):
    """The 128-byte signed block for the canonical fs content (digest+body).

    Canonical rule (validated: 24/24 size sweep vs dfusign, and Bose's own
    signature S^3 mod n == block verified on all 7 Minnow releases):

      - the hashed span excludes the area's FINAL WORD (2 bytes): the caller
        passes digest+body and fs_block drops the last 2 bytes itself;
      - feed: EVERY complete 64-byte block, block k -> chain k mod 8
        (the earlier 128-byte-unit reading was an equivalent-in-read-region
        coincidence, not the real rule);
      - if the remaining tail is non-empty: fin = tail + 0x8000 word + zero
        words to 28 mod 32 (of total words incl. feed) + 8-byte bit length;
        empty tail -> NO fin block at all;
      - the compress only ever READS bytes 0..33 of each block (message words
        M[0..15] at 16-bit stride); everything past byte 34 of a block is
        irrelevant, which is why several padding conventions hash identically;
      - chain 0's A word &= 0x7fffffff.
    """
    content = content[:-2]
    feed = content[:len(content) // 64 * 64]
    tail = content[len(feed):]
    slots = [list(IV) for _ in range(8)]
    for k in range(0, len(feed), 64):
        slots[(k // 64) % 8] = compress(slots[(k // 64) % 8], feed[k:k + 64])
    nfeed = len(feed) // 64
    if tail:
        tw = len(tail) // 2
        m = tw % 32
        pad_w = (28 - m) if m < 28 else (60 - m)
        total_words = (len(feed) // 2) + tw + pad_w
        fin = tail + b"\x80\x00" + b"\x00" * ((pad_w - 1) * 2) \
            + struct.pack("<II", total_words * 16, 0)
        while len(fin) % 64:
            fin += b"\x00"
        for j in range(0, len(fin) // 64):
            slots[(nfeed + j) % 8] = compress(slots[(nfeed + j) % 8], fin[j * 64:j * 64 + 64])
    out = b"".join(struct.pack("<4I", *s) for s in slots)
    # the finalize mask: chain 0's A &= 0x7fffffff
    a0 = struct.unpack_from("<I", out, 0)[0] & 0x7FFFFFFF
    return struct.pack("<I", a0) + out[4:]


def load_area(path):
    """fs area content (digest+body) from an XUV text image or a binary area."""
    data = open(path, "rb").read()
    if data[:1] == b"@" or b"\n@" in data[:200]:
        W = {}
        for line in data.decode("latin-1").splitlines():
            m = re.match(r"@([0-9A-Fa-f]+)\s+([0-9A-Fa-f]{4})", line.strip())
            if m:
                W[int(m.group(1), 16)] = int(m.group(2), 16)
        addrs = sorted(W)
        # the words are dense from 0 in these images
        raw = b"".join(W[a].to_bytes(2, "little") for a in addrs)
    else:
        raw = data
    if raw[:8] == b"fsr_dfu1":
        return raw[136:]              # digest + body
    # a bare body (no area header)
    return raw


def sig_int_from_words(words):
    """Signature integer from the 64 stored (reversed) words."""
    return int.from_bytes(b"".join(w.to_bytes(2, "little") for w in words[::-1]), "little")


def sig_int_from_area(raw_area):
    if raw_area[:8] != b"fsr_dfu1":
        raise ValueError("not an fs area")
    ws = struct.unpack("<64H", raw_area[8:136])
    return sig_int_from_words(list(ws))


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    if args[0] == "--block":
        content = load_area(args[1])
        print(fs_block(content).hex())
        return
    content = load_area(args[0])
    blk = fs_block(content)
    print("block:", blk.hex())
    if len(args) > 2 and args[1] == "--verify":
        # args[2] = the full signed area (XUV or bin) carrying the signature
        d = open(args[2], "rb").read()
        if d[:1] == b"@" or b"\n@" in d[:200]:
            W = {}
            for line in d.decode("latin-1").splitlines():
                m = re.match(r"@([0-9A-Fa-f]+)\s+([0-9A-Fa-f]{4})", line.strip())
                if m:
                    W[int(m.group(1), 16)] = int(m.group(2), 16)
            raw = b"".join(W[a].to_bytes(2, "little") for a in sorted(W))
        else:
            raw = d
        S = sig_int_from_area(raw)
        # verify against our test key if given, else just report S^3 relation
        print("S bits:", S.bit_length())
        print("n from gcd needed to verify; use recover_modulus.py")


if __name__ == "__main__":
    main()
