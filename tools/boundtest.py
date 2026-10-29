#!/usr/bin/env python3
"""Is the problem the RATE or the UNBOUNDED WALK?

My diagnosis was "the 2000 Hz rate killed the spectrum". The consult says no: the IMA
decoder is a pure accumulator with no leak, so a 252-sample free walk is dominated by its
own DC drift at ANY rate, and bounding the walk frees the rate again.

Tests the principle only, independent of any particular implementation:
  1. the current generator at 2000 and 8000 Hz
  2. the same template but with the SIGN chosen to pull the predictor back whenever
     |pred| > K -- i.e. a bounded walk

Reports the fraction of energy above 150 Hz, which is what this speaker radiates, and the
absolute in-band level, which is what the ear gets.
"""
import sys

if sys.path and 'scratchpad' in sys.path[0]:
    sys.path.pop(0)

import os

import numpy as np

ROOT = __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import noisespec as ns

STEP = ns.STEP
IDX = ns.IDX_DELTA
NW = 126


def lfsr_bits(n, seed=0xACE1):
    x, out = seed, []
    for _ in range(n):
        x = ((x >> 1) ^ ((-(x & 1)) & 0xB400)) & 0xFFFF
        out.append(x)
    return out


def template(nw, prime):
    w = np.zeros(nw, dtype=int)
    w[:prime] = 0x44
    reps = (nw - prime) // 3
    w[prime:prime + 3 * reps] = np.tile([0x11, 0x41, 0x14], reps)
    return w


def decode(nibs):
    pred, idx = 0, 0
    pcm = []
    for n in nibs:
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
        idx = max(0, min(88, idx + IDX[mag]))
        pcm.append(pred)
    return np.array(pcm, dtype=np.int32)


def free_walk(nw=NW, prime=12):
    """What the device does today: signs come straight from the LFSR."""
    w, xs = template(nw, prime), lfsr_bits(nw)
    nibs = []
    for i in range(nw):
        b = w[i] ^ (xs[i] & 0x88)
        nibs += [(b >> 4) & 0xF, b & 0xF]
    return decode(nibs)


def bounded_walk(nw=NW, prime=12, K=6000):
    """Same magnitudes, but the SIGN is forced toward zero when |pred| exceeds K.
    Tracks the real IMA predictor, so the bound is exact rather than approximate."""
    w, xs = template(nw, prime), lfsr_bits(nw)
    pred, idx = 0, 0
    nibs = []
    for i in range(nw):
        base = w[i]
        for half in (0, 1):
            mag = ((base >> 4) if half == 0 else base) & 0x7
            rnd = ((xs[i] >> (7 if half == 0 else 3)) & 1)
            step = STEP[idx]
            diff = step >> 3
            if mag & 4:
                diff += step
            if mag & 2:
                diff += step >> 1
            if mag & 1:
                diff += step >> 2
            if pred > K:
                neg = 1                      # pull down
            elif pred < -K:
                neg = 0                      # pull up
            else:
                neg = rnd                    # free
            pred = pred - diff if neg else pred + diff
            pred = max(-32768, min(32767, pred))
            idx = max(0, min(88, idx + IDX[mag]))
            nibs.append((neg << 3) | mag)
    return decode(nibs)


def band(pcm, fs, cut=150.0):
    x = pcm.astype(float) - pcm.mean()
    n = 1 << int(np.floor(np.log2(len(x))))
    psd = np.abs(np.fft.rfft(x[:n] * np.hanning(n))) ** 2
    f = np.fft.rfftfreq(n, 1.0 / fs)
    tot = psd.sum()
    frac = psd[f >= cut].sum() / tot if tot else 0.0
    rms = np.sqrt((x ** 2).mean())
    dbfs = 20 * np.log10(rms / 32768.0 + 1e-12)
    return frac * 100.0, dbfs, dbfs + 10 * np.log10(frac + 1e-12)


# --- the consult's actual design: prime the INDEX high (huge steps) AND bound the walk ---
def hi_bounded(nw=NW, K=6000, idx_target=84):
    """Prime with large-magnitude nibbles to drive the step index high, then hold it with
    the zero-sum cycle while forcing the sign toward zero past +/-K. Big steps give large,
    rapidly alternating excursions = high-frequency energy at high level."""
    xs = lfsr_bits(nw)
    pred, idx = 0, 0
    nibs = []
    # priming: magnitude 7 raises the index by 8 per nibble
    prime_words = 0
    while idx < idx_target - 8 and prime_words < nw:
        for mag in (7, 7):
            step = STEP[idx]
            diff = step >> 3
            if mag & 4: diff += step
            if mag & 2: diff += step >> 1
            if mag & 1: diff += step >> 2
            neg = 1 if pred > 0 else 0
            pred = pred - diff if neg else pred + diff
            pred = max(-32768, min(32767, pred))
            idx = max(0, min(88, idx + IDX[mag]))
            nibs.append((neg << 3) | mag)
        prime_words += 1
    tmpl = np.tile([0x11, 0x41, 0x14], (nw - prime_words) // 3)
    for i, base in enumerate(tmpl):
        for half in (0, 1):
            mag = ((base >> 4) if half == 0 else base) & 0x7
            rnd = (xs[prime_words + i] >> (7 if half == 0 else 3)) & 1
            step = STEP[idx]
            diff = step >> 3
            if mag & 4: diff += step
            if mag & 2: diff += step >> 1
            if mag & 1: diff += step >> 2
            if pred > K: neg = 1
            elif pred < -K: neg = 0
            else: neg = rnd
            pred = pred - diff if neg else pred + diff
            pred = max(-32768, min(32767, pred))
            idx = max(0, min(88, idx + IDX[mag]))
            nibs.append((neg << 3) | mag)
    return decode(nibs), prime_words, idx

print('%-34s %6s %8s %9s %11s %7s' %
      ('generator', 'rate', 'dBFS', '>150Hz', 'in-band dBFS', 'clip%'))
rows = []
for tag, pcm in (('free walk, PRIME 9  (probe128)', free_walk(prime=9)),
                 ('free walk, PRIME 12 (probe129)', free_walk(prime=12))):
    for fs in (2000, 8000):
        fr, db, ib = band(pcm, fs)
        cl = 100.0 * np.mean(np.abs(pcm) >= 32767)
        print('%-34s %6d %8.1f %8.1f%% %11.1f %7.2f' % (tag, fs, db, fr, ib, cl))
        rows.append((tag, fs, ib))
print()
for K in (3000, 6000, 10000):
    pcm = bounded_walk(prime=12, K=K)
    for fs in (2000, 8000):
        fr, db, ib = band(pcm, fs)
        cl = 100.0 * np.mean(np.abs(pcm) >= 32767)
        print('%-34s %6d %8.1f %8.1f%% %11.1f %7.2f'
              % ('BOUNDED walk, K=%d' % K, fs, db, fr, ib, cl))

base = [r for r in rows if 'PRIME 12' in r[0] and r[1] == 2000][0][2]
print('\nbaseline in-band level (probe129 @2000) = %.1f dBFS' % base)
for K in (3000, 6000, 10000):
    pcm = bounded_walk(prime=12, K=K)
    for fs in (2000, 8000):
        _, _, ib = band(pcm, fs)
        print('  bounded K=%-6d @%4d Hz -> in-band %+6.1f dB vs probe129' % (K, fs, ib - base))


print()
print('=== the consult design: HIGH index + bounded walk ===')
for K in (3000, 6000, 10000, 16000):
    pcm, pw, idxf = hi_bounded(K=K)
    for fs in (2000, 8000):
        fr, db, ib = band(pcm, fs)
        cl = 100.0 * np.mean(np.abs(pcm) >= 32767)
        print('  K=%-6d @%4d Hz  dBFS %6.1f  >150Hz %5.1f%%  in-band %6.1f  clip %5.2f%%  '
              'peak %5d  (%d prime words, final idx %d)  -> %+5.1f dB vs probe129'
              % (K, fs, db, fr, ib, cl, int(np.max(np.abs(pcm))), pw, idxf, ib - base))
