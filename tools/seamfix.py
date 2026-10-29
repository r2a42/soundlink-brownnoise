#!/usr/bin/env python3
"""seamfix: make the loop boundary of an IMA-ADPCM noise payload survive the speaker's early chunk cut.

Finding (field-log 2026-10-27, tools/click_detect.py): on the speaker every chunk is cut about 160 samples (3.33 ms) before its end
by the rebuild, so the loop boundary joins sample N-160 of the old chunk to sample 0 of the new one, whose decoder starts from state
(0,0). The earlier tail fix (end state (0,0) at sample N) never reaches that state. Here the last part of the audible payload fades to
zero BEFORE the cut point and everything after it is zero, so a cut anywhere in the last CUT samples joins zero to the zero start.
  python tools/seamfix.py IN.adpcm OUT.adpcm [--cut 160] [--fade 480]
The output has exactly the input's length (the first bytes, so the product's first-four-bytes check, are unchanged)."""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adpcm  # noqa: E402


def seamfix(data, cut=160, fade=480):
    nib = adpcm.nibbles(data)
    n = len(nib)
    m = n - cut                                                   # the audible end: the cut point
    orig, _ = adpcm.decode_state(data)
    orig = np.array(orig, float)
    _, st = adpcm.decode_nibbles(nib[:m - fade])
    w = 0.5 * (1 + np.cos(np.pi * np.arange(1, fade + 1) / fade))   # 1 -> 0 raised cosine
    target = np.round(orig[m - fade:m] * w).astype(int).tolist()
    tail, st2 = adpcm.encode_state(target, st)
    tn = adpcm.nibbles(tail)[:fade]
    out_nib = nib[:m - fade] + tn + [0] * cut
    assert len(out_nib) == n
    out = adpcm.pack(out_nib)
    return out, orig, st, st2


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inp")
    ap.add_argument("out")
    ap.add_argument("--cut", type=int, default=160)
    ap.add_argument("--fade", type=int, default=480)
    a = ap.parse_args()
    data = open(a.inp, "rb").read()
    out, orig, st, st2 = seamfix(data, a.cut, a.fade)
    new = np.array(adpcm.decode_state(out)[0], float)
    n = len(new)
    m = n - a.cut
    print("in %d bytes, out %d bytes; fade starts at sample %d with decoder state %s" % (len(data), len(out), m - a.fade, st))
    print("tail before the fade: orig rms %.0f; fade region new rms %.0f (orig %.0f); value at the cut point %.0f; |value| in the last %d samples max %.0f" %
          (np.sqrt((orig[m - a.fade - 480:m - a.fade] ** 2).mean()), np.sqrt((new[m - a.fade:m] ** 2).mean()), np.sqrt((orig[m - a.fade:m] ** 2).mean()), new[m - 1], a.cut, np.abs(new[m:]).max()))
    print("start of the loop: first samples", new[:6].astype(int).tolist(), "; samples at the cut point -3..+3:", new[m - 3:m + 3].astype(int).tolist())
    assert np.array_equal(new[:m - a.fade], orig[:m - a.fade]), "the audible start must be untouched"
    open(a.out, "wb").write(out)


if __name__ == "__main__":
    main()
