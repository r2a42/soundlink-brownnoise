#!/usr/bin/env python3
"""Measure the brown-noise generator's spectrum for a given NWORDS.

Reproduces offline what `build/noiseprobe/noise.c:nib_fill` produces on the device, so a
change to NWORDS can be checked before it is built into a probe. The original measurement
scripts lived in session scratchpads and were lost; this is the reproducible version.

The chain modelled, in the order the hardware sees it:

  1. `nib_fill(p, st)` writes NWORDS 16-bit words: a magnitude template laid down on the
     first call (nine 0x44 priming words, then 0x11/0x41/0x14 repeating, whose index
     deltas sum to zero), with the two sign bits (0x88) XOR-toggled from an LFSR on every
     call.
  2. `StreamRegionSource` delivers **one byte per 16-bit word** -- the low 8 bits. That
     byte is two IMA ADPCM nibbles.
  3. `TransformAdpcmDecode` runs standard IMA ADPCM.

Usage:  python tools/noisespec.py [NWORDS ...]      (default: 639 636)
"""
import sys

import numpy as np

STEP = [
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
    50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230,
    253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963,
    1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024,
    3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493,
    10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623,
    27086, 29794, 32767,
]
IDX_DELTA = [-1, -1, -1, -1, 2, 4, 6, 8]


def nib_fill(nwords, state, first):
    """One refill. Returns (words, new_state). `first` lays the template."""
    x = state
    w = np.zeros(nwords, dtype=np.uint16)
    if first:
        w[:9] = 0x44
        tmpl = np.tile(np.array([0x11, 0x41, 0x14], dtype=np.uint16),
                       (nwords - 9) // 3)
        w[9:] = tmpl
        x = 0xACE1
    else:
        # a later refill re-XORs the signs onto the template already in memory
        w[:9] = 0x44
        w[9:] = np.tile(np.array([0x11, 0x41, 0x14], dtype=np.uint16),
                        (nwords - 9) // 3)
    out = np.empty(nwords, dtype=np.uint16)
    for i in range(nwords):
        x = (x >> 1) ^ ((-(x & 1)) & 0xB400) & 0xFFFF
        x &= 0xFFFF
        out[i] = w[i] ^ (x & 0x88)
    return out, x


def ima_decode(nibbles):
    pred, idx = 0, 0
    pcm = np.empty(len(nibbles), dtype=np.int32)
    idxs = np.empty(len(nibbles), dtype=np.int32)
    for i, n in enumerate(nibbles):
        step = STEP[idx]
        mag = n & 7
        diff = step >> 3
        if mag & 4:
            diff += step
        if mag & 2:
            diff += step >> 1
        if mag & 1:
            diff += step >> 2
        pred = pred - diff if (n & 8) else pred + diff
        pred = max(-32768, min(32767, pred))
        idx = max(0, min(88, idx + IDX_DELTA[mag]))
        pcm[i] = pred
        idxs[i] = idx
    return pcm, idxs


def octave_slope(pcm, fs=8000):
    x = pcm.astype(np.float64)
    x -= x.mean()
    n = 1 << int(np.floor(np.log2(len(x))))
    x = x[:n] * np.hanning(n)
    psd = np.abs(np.rfft(x) if hasattr(np, 'rfft') else np.fft.rfft(x)) ** 2
    freq = np.fft.rfftfreq(n, 1.0 / fs)

    def band(f0):
        lo, hi = f0 / 2 ** 0.5, f0 * 2 ** 0.5
        m = (freq >= lo) & (freq < hi)
        return 10 * np.log10(psd[m].mean()) if m.any() else float('nan')

    centres = [400, 800, 1600, 3200]
    lv = [band(f) for f in centres]
    return centres, lv, [lv[i + 1] - lv[i] for i in range(len(lv) - 1)]


# Each refill builds a NEW TransformAdpcmDecode, so the IMA decoder's index and
# predictor RESET to zero at every refill boundary. That is why the template re-primes:
# the nine 0x44 words lift the index 0 -> ~36 again on each pass. Carrying the decoder
# state across boundaries instead makes the index climb +36 per refill and rail at 88
# after three -- which is what a first version of this script did, and it is a modelling
# error, not a defect in the generator.
def run(nwords, refills=3, lo_first=True):
    st, first, words = 0, True, []
    for _ in range(refills):
        w, st = nib_fill(nwords, st, first)
        first = False
        words.append(w)
    b = np.concatenate(words) & 0xFF
    if lo_first:
        nib = np.empty(b.size * 2, dtype=np.uint8)
        nib[0::2] = b & 0x0F
        nib[1::2] = b >> 4
    else:
        nib = np.empty(b.size * 2, dtype=np.uint8)
        nib[0::2] = b >> 4
        nib[1::2] = b & 0x0F
    per = nib.size // refills
    pcm = np.concatenate([ima_decode(nib[k*per:(k+1)*per])[0] for k in range(refills)])
    idxs = np.concatenate([ima_decode(nib[k*per:(k+1)*per])[1] for k in range(refills)])
    centres, lv, slopes = octave_slope(pcm)
    peak = int(np.abs(pcm).max())
    rms = float(np.sqrt((pcm.astype(np.float64) ** 2).mean()))
    clipped = 100.0 * np.mean((pcm >= 32767) | (pcm <= -32768))
    print('NWORDS=%d  nibble order=%s  refills=%d  samples=%d'
          % (nwords, 'low-first' if lo_first else 'high-first', refills, pcm.size))
    print('  dBFS %.1f   peak %d   clipped %.2f%%   index min/max/final %d/%d/%d'
          % (20 * np.log10(rms / 32768.0), peak, clipped,
             idxs.min(), idxs.max(), idxs[-1]))
    print('  octave slope %s  ->  %s'
          % (' '.join('%dHz' % f for f in centres),
             ' '.join('%+.2f' % s for s in slopes)))
    print('  mean slope %+.2f dB/octave   (brown = -6.00)'
          % (sum(slopes) / len(slopes)))
    return sum(slopes) / len(slopes), clipped, peak


if __name__ == '__main__':
    sizes = [int(a) for a in sys.argv[1:]] or [639, 636]
    for nw in sizes:
        if (nw - 9) % 3:
            print('NWORDS=%d rejected: (NWORDS-9) must be divisible by 3 '
                  '(the template unrolls three words at a time)' % nw)
            continue
        for lo in (True, False):
            run(nw, lo_first=lo)
        print()
