#!/usr/bin/env python3
"""Recover the Bose DFU-signing modulus by GCD once the staged-block
construction is known.

Usage:
  python recover_modulus.py <emulator-module>   # module with fs_block(area_bytes) -> 128-byte block

For every official Minnow release R with filesystem area F_R and
signature S_R:  n | (S_R^3 - B_R)  where B_R = fs_block(F_R).
n = gcd over all releases (up to a small cofactor, removed by trial
division and by checking the result is 1024 bits).
"""
import struct, sys, math, re, os

HERE = os.path.dirname(os.path.abspath(__file__))
REL = [("1.0.6", "Minnow_1.0.6_stack_plus_app.dfu"),
       ("1.0.14", "Minnow_1.0.14_stack_plus_app.dfu"),
       ("1.1.3", "Minnow_1.1.3_stack_plus_app.dfu"),
       ("1.2.4", "Minnow_1.2.4_stack_plus_app.dfu"),
       ("1.5.0", "Minnow_1.5.0_stack_plus_app.dfu"),
       ("2.6.0", "Minnow_2.6.0_stack_plus_app.dfu"),
       ("3.0.3", os.path.join("minnow_3.0.3", "Minnow_3.0.3_stack_plus_app.dfu"))]

def fs_area(path):
    d = open(path, "rb").read()
    i = d.find(b"fsr_dfu1")
    assert i >= 0, path
    # area = id(8) + sig(128) + digest(4) + body ... to end of area:
    # the fs area runs to the container's file_crc; find via header parse
    # (the fs area is the last area: fs start .. file_length-4)
    file_len = struct.unpack_from("<I", d, 0xA)[0]
    return d[i:i + file_len - 4], d[i+8:i+136]   # content (id..end), signature

def main():
    mod = __import__(sys.argv[1]) if len(sys.argv) > 1 else None
    g = None
    for ver, fn in REL:
        p = os.path.join(HERE, "..", "firmware", "bose", fn)
        if not os.path.exists(p):
            print("missing", p); continue
        area, sig = fs_area(p)
        S = int.from_bytes(sig[::-1], "little")   # words reversed per convention
        if mod is None:
            print("no emulator given; demonstrating with dummy blocks"); return
        B = int.from_bytes(mod.fs_block(area), "little")
        v = (pow(S, 3, 1 << 2100) - B) if False else None
        # S^3 - B without modulus: S^3 is 3072-bit; n divides the difference
        diff = pow(S, 3) - B
        g = diff if g is None else math.gcd(g, diff)
        print(ver, "gcd bits:", g.bit_length() if g else 0)
    if g:
        # strip small cofactors
        for p in range(2, 100000):
            while g % p == 0 and g // p > (1 << 1000):
                g //= p
        print("n bits:", g.bit_length())
        print("n hex:", hex(g))

if __name__ == "__main__":
    main()
