#!/usr/bin/env python3
"""Sweep the generator's priming count for a SINGLE pass at NWORDS=126.

The nine priming 0x44 words lift the IMA step index; more priming = a bigger index =
louder output. probe128 was very quiet at prime=9. This finds the loudest prime that still
clips 0.00%, independently of the consult's figures.

Models nib_fill exactly as tools/noisespec.py does (which was proven byte-for-byte
identical to the real lifted XAP code in the probe128 cross-check), with the prime made a
parameter instead of hardcoded at 9.
"""
import sys

if sys.path and 'scratchpad' in sys.path[0]:
    sys.path.pop(0)

import os

import numpy as np

ROOT = __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import noisespec as ns

NWORDS = 126
RATE = 2000


def nib_fill(nwords, prime, state=0):
    """tools/noisespec.py's nib_fill with the priming count parameterised."""
    w = np.zeros(nwords, dtype=np.uint16)
    w[:prime] = 0x44
    reps = (nwords - prime) // 3
    w[prime:prime + 3 * reps] = np.tile(
        np.array([0x11, 0x41, 0x14], dtype=np.uint16), reps)
    x = 0xACE1 if state == 0 else state
    out = np.empty(nwords, dtype=np.uint16)
    for i in range(nwords):
        x = (x >> 1) ^ ((-(x & 1)) & 0xB400) & 0xFFFF
        x &= 0xFFFF
        out[i] = w[i] ^ (x & 0x88)
    return out, x


def nibbles(words, high_first=True):
    a = np.array([int(v) & 0xFF for v in words], dtype=np.int32)
    o = np.empty(a.size * 2, dtype=np.int32)
    if high_first:
        o[0::2], o[1::2] = a >> 4, a & 0xF
    else:
        o[0::2], o[1::2] = a & 0xF, a >> 4
    return o


print('SINGLE PASS, NWORDS=%d, %d samples = %.0f ms at %d Hz' %
      (NWORDS, 2 * NWORDS, 2000.0 * NWORDS / RATE, RATE))
print('%6s %10s %8s %9s %8s %18s %7s' %
      ('prime', '(nw-p)%3', 'dBFS', 'peak', 'clip%', 'idx min/mean/max', 'dB vs 9'))
base = None
rows = []
for prime in range(9, 19):
    if (NWORDS - prime) % 3:
        print('%6d %10d   skipped: template unrolls 3 words at a time'
              % (prime, (NWORDS - prime) % 3))
        continue
    words, _ = nib_fill(NWORDS, prime)
    pcm, idxs = ns.ima_decode(nibbles(words, True))
    x = pcm.astype(np.float64)
    dbfs = 20 * np.log10(np.sqrt((x ** 2).mean()) / 32768.0 + 1e-12)
    peak = int(np.max(np.abs(pcm)))
    clip = 100.0 * np.mean(np.abs(pcm) >= 32767)
    if base is None:
        base = dbfs
    rows.append((prime, dbfs, peak, clip, idxs))
    print('%6d %10d %8.1f %9d %8.2f %18s %+7.1f'
          % (prime, 0, dbfs, peak, clip,
             '%d/%.1f/%d' % (idxs.min(), idxs.mean(), idxs.max()), dbfs - base))

print()
clean = [r for r in rows if r[3] == 0.0]
if clean:
    best = max(clean, key=lambda r: r[1])
    print('LOUDEST prime with 0.00%% clipping: %d  -> %.1f dBFS, peak %d of 32768 '
          '(%.1f dB peak headroom), %+.1f dB vs probe128'
          % (best[0], best[1], best[2], 20 * np.log10(32768.0 / best[2]), best[1] - base))

# Robustness: the LFSR seed is fixed in the model, but confirm the choice is not a fluke of
# one seed. Re-run the winner across several seeds.
print('\nSeed robustness for the recommended prime (the device always starts from the same')
print('seed, but a result that only works for one seed would be fragile):')
for prime in (12, 15):
    if (NWORDS - prime) % 3:
        continue
    cl, db = [], []
    for seed in (0xACE1, 0x1234, 0xBEEF, 0x0001, 0x7FFF, 0xFFFF):
        words, _ = nib_fill(NWORDS, prime, seed)
        pcm, _i = ns.ima_decode(nibbles(words, True))
        xx = pcm.astype(np.float64)
        db.append(20 * np.log10(np.sqrt((xx ** 2).mean()) / 32768.0 + 1e-12))
        cl.append(100.0 * np.mean(np.abs(pcm) >= 32767))
    print('  prime %2d: dBFS %.1f..%.1f   clip%% %.2f..%.2f over %d seeds'
          % (prime, min(db), max(db), min(cl), max(cl), len(db)))
