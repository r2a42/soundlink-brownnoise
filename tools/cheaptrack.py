#!/usr/bin/env python3
"""Can the bound be enforced with a CHEAP tracker instead of exact predictor tracking?

The consult's design tracks the IMA predictor exactly, which needs a 6-entry table of
per-position diffs and costs ~131 lifted words against a 262-word cave. Cave space is the
binding constraint, so this asks whether a cheaper approximation gets most of the in-band
gain:

  (a) EXACT      - diff recomputed from the real step table each nibble (the consult's)
  (b) CONSTANT   - the tracker assumes one fixed step, so no table and no per-position math
  (c) SIGN-ONLY  - no tracker at all: alternate the sign every nibble, LFSR picks when to
                   hold instead of alternate. Bounded by construction, nothing to track.

All three are measured by decoding with the REAL IMA decoder, so the comparison is honest
regardless of what the generator believes.
"""
import sys

if sys.path and 'scratchpad' in sys.path[0]:
    sys.path.pop(0)

import os

import numpy as np

ROOT = __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import noisespec as ns

STEP, IDX = ns.STEP, ns.IDX_DELTA
NW = 126


def lfsr(n, seed=0xACE1):
    x, o = seed, []
    for _ in range(n):
        x = ((x >> 1) ^ ((-(x & 1)) & 0xB400)) & 0xFFFF
        o.append(x)
    return o


def diff_of(step, mag):
    d = step >> 3
    if mag & 4:
        d += step
    if mag & 2:
        d += step >> 1
    if mag & 1:
        d += step >> 2
    return d


def decode(nibs):
    pred, idx, out = 0, 0, []
    for n in nibs:
        d = diff_of(STEP[idx], n & 7)
        pred = pred - d if (n & 8) else pred + d
        pred = max(-32768, min(32767, pred))
        idx = max(0, min(88, idx + IDX[n & 7]))
        out.append(pred)
    return np.array(out, dtype=np.int32)


def build(mode, K=3000, nw=NW, seed=0xACE1):
    xs = lfsr(nw, seed)
    nibs = []
    pred = idx = 0
    track = 0                      # the generator's own belief about the predictor
    CONST = 9000                   # a single assumed step for mode (b)
    pw = 0
    while idx < 76 and pw < nw:    # prime the index high with magnitude 7
        for _ in range(2):
            d = diff_of(STEP[idx], 7)
            neg = 1 if pred > 0 else 0
            pred = max(-32768, min(32767, pred - d if neg else pred + d))
            idx = max(0, min(88, idx + IDX[7]))
            nibs.append((neg << 3) | 7)
        pw += 1
    tmpl = np.tile([0x11, 0x41, 0x14], (nw - pw) // 3)
    alt = 0
    for i, base in enumerate(tmpl):
        for half in (0, 1):
            mag = ((base >> 4) if half == 0 else base) & 7
            rnd = (xs[pw + i] >> (7 if half == 0 else 3)) & 1
            d = diff_of(STEP[idx], mag)
            if mode == 'exact':
                ref = pred
            elif mode == 'const':
                ref = track
            else:
                ref = None
            if mode == 'signonly':
                # alternate unless the LFSR says hold; no tracker at all
                alt ^= 1 if rnd else 0
                alt ^= 1
                neg = alt
            else:
                if ref > K:
                    neg = 1
                elif ref < -K:
                    neg = 0
                else:
                    neg = rnd
            if mode == 'const':
                track = track - CONST if neg else track + CONST
                track = max(-32768, min(32767, track))
            pred = max(-32768, min(32767, pred - d if neg else pred + d))
            idx = max(0, min(88, idx + IDX[mag]))
            nibs.append((neg << 3) | mag)
    return decode(nibs)


def band(pcm, fs, cut=150.0):
    x = pcm.astype(float) - pcm.mean()
    n = 1 << int(np.floor(np.log2(len(x))))
    psd = np.abs(np.fft.rfft(x[:n] * np.hanning(n))) ** 2
    f = np.fft.rfftfreq(n, 1.0 / fs)
    tot = psd.sum()
    fr = psd[f >= cut].sum() / tot if tot else 0.0
    db = 20 * np.log10(np.sqrt((x ** 2).mean()) / 32768.0 + 1e-12)
    return fr * 100, db, db + 10 * np.log10(fr + 1e-12)


BASE = -41.9        # probe129's in-band level at 2000 Hz
print('baseline: probe129 in-band -41.9 dBFS at 2000 Hz\n')
print('%-12s %6s %8s %9s %11s %7s %8s %9s' %
      ('tracker', 'rate', 'dBFS', '>150Hz', 'in-band', 'clip%', 'peak', 'vs p129'))
for mode in ('exact', 'const', 'signonly'):
    for fs in (2000, 8000):
        pcm = build(mode)
        fr, db, ib = band(pcm, fs)
        cl = 100.0 * np.mean(np.abs(pcm) >= 32767)
        print('%-12s %6d %8.1f %8.1f%% %11.1f %7.2f %8d %+9.1f'
              % (mode, fs, db, fr, ib, cl, int(np.max(np.abs(pcm))), ib - BASE))

print('\nseed robustness at 2000 Hz (8 seeds), in-band dBFS and worst clip%:')
for mode in ('exact', 'const', 'signonly'):
    ibs, cls = [], []
    for sd in (0xACE1, 0x1234, 0xBEEF, 0x0001, 0x7FFF, 0xFFFF, 0x5A5A, 0x0F0F):
        pcm = build(mode, seed=sd)
        _, _, ib = band(pcm, 2000)
        ibs.append(ib)
        cls.append(100.0 * np.mean(np.abs(pcm) >= 32767))
    print('  %-10s in-band %.1f..%.1f dBFS   worst clip %.2f%%'
          % (mode, min(ibs), max(ibs), max(cls)))
