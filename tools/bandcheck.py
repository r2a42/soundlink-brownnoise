#!/usr/bin/env python3
"""Why did PRIME 12 sound LOWER but not LOUDER?

A bigger IMA step index makes the random-walk integrator take bigger strides per sample,
which piles energy at the BOTTOM of the spectrum. On a tiny speaker that energy is not
radiated, so RMS dBFS rises while perceived loudness does not.

This measures energy IN BANDS, and the fraction of it that lands above a small driver's
usable limit, for PRIME 9 vs 12 at the 2000 Hz rate probe128/129 used and at 8000 Hz.
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


def fill(nw, prime, seed=0xACE1):
    w = np.zeros(nw, dtype=np.uint16)
    w[:prime] = 0x44
    reps = (nw - prime) // 3
    w[prime:prime + 3 * reps] = np.tile(np.array([0x11, 0x41, 0x14], dtype=np.uint16), reps)
    x, o = seed, np.empty(nw, dtype=np.uint16)
    for i in range(nw):
        x = (x >> 1) ^ ((-(x & 1)) & 0xB400) & 0xFFFF
        x &= 0xFFFF
        o[i] = w[i] ^ (x & 0x88)
    return o


def pcm_of(prime):
    w = fill(NWORDS, prime)
    a = np.array([int(v) & 0xFF for v in w], dtype=np.int32)
    nib = np.empty(a.size * 2, dtype=np.int32)
    nib[0::2], nib[1::2] = a >> 4, a & 0xF
    pcm, idxs = ns.ima_decode(nib)
    return pcm, idxs


def spectrum(pcm, fs):
    x = pcm.astype(np.float64)
    x -= x.mean()
    n = 1 << int(np.floor(np.log2(len(x))))
    xw = x[:n] * np.hanning(n)
    psd = np.abs(np.fft.rfft(xw)) ** 2
    f = np.fft.rfftfreq(n, 1.0 / fs)
    return f, psd


def energy_above(pcm, fs, cut):
    f, psd = spectrum(pcm, fs)
    tot = psd.sum()
    return 100.0 * psd[f >= cut].sum() / tot if tot else 0.0


print('A SoundLink Micro is a small passive-radiator driver; energy below roughly')
print('100-150 Hz is essentially not radiated. "Loudness" is what survives that.\n')

for fs in (2000, 8000):
    print('=== playback rate %d Hz  (%.0f ms for %d samples, Nyquist %d Hz) ==='
          % (fs, 2000.0 * NWORDS / fs, 2 * NWORDS, fs // 2))
    print('%6s %9s %9s  %s' % ('prime', 'dBFS', 'peak', 'energy above:  100Hz   150Hz   300Hz'))
    for prime in (9, 12):
        pcm, idxs = pcm_of(prime)
        x = pcm.astype(np.float64)
        dbfs = 20 * np.log10(np.sqrt((x ** 2).mean()) / 32768.0 + 1e-12)
        print('%6d %9.1f %9d   %21.1f%% %7.1f%% %7.1f%%'
              % (prime, dbfs, int(np.max(np.abs(pcm))),
                 energy_above(pcm, fs, 100), energy_above(pcm, fs, 150),
                 energy_above(pcm, fs, 300)))
    # octave levels in bands that exist at this rate
    print('   octave band levels (dB, relative):')
    for prime in (9, 12):
        pcm, _ = pcm_of(prime)
        f, psd = spectrum(pcm, fs)
        cs = [c for c in (62.5, 125, 250, 500, 1000, 2000) if c * 1.42 < fs / 2]
        lv = []
        for c in cs:
            m = (f >= c / 2 ** 0.5) & (f < c * 2 ** 0.5)
            lv.append(10 * np.log10(psd[m].mean()) if m.any() else float('nan'))
        print('     prime %2d: %s' % (prime, '  '.join('%.0fHz %.0f' % (c, v)
                                                       for c, v in zip(cs, lv))))
    print()

# The decisive comparison: audible-band energy, which is what the ear gets.
print('DECISIVE: absolute energy above 150 Hz, normalised to prime 9 at 2000 Hz')
ref = None
for fs in (2000, 8000):
    for prime in (9, 12):
        pcm, _ = pcm_of(prime)
        f, psd = spectrum(pcm, fs)
        e = psd[f >= 150].sum() / len(pcm)        # per-sample, so rates compare
        if ref is None:
            ref = e
        print('  %4d Hz  prime %2d -> %+6.1f dB of audible-band energy vs the baseline'
              % (fs, prime, 10 * np.log10(e / ref)))
