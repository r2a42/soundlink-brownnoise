#!/usr/bin/env python3
"""Survey EVERY file in both filesystems for how it decodes through TransformAdpcmDecode.

The file-source route's whole viability is a content question. sbc_decoder.kap clips 41% of
samples, so it is unusable as a sleep sound. This asks whether ANY file on the device
decodes to something gentle: low clipping, a step index that is not railed, and a slope
near brown (-6 dB/oct).

Also scans ext_flash.bin in windows, since 2 MB of it has never been examined.
"""
import sys

if sys.path and 'scratchpad' in sys.path[0]:
    sys.path.pop(0)

import glob
import os

import numpy as np

ROOT = __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import noisespec as ns

FS = 8000
MAXB = 120000      # cap per file for speed; 120 kB = 30 s, plenty to characterise


def nib(b):
    a = np.frombuffer(b, dtype=np.uint8).astype(np.int32)
    out = np.empty(a.size * 2, dtype=np.int32)
    out[0::2], out[1::2] = a >> 4, a & 0xF
    return out


def score(b):
    pcm, idxs = ns.ima_decode(nib(b[:MAXB]))
    x = pcm.astype(np.float64)
    dbfs = 20 * np.log10(np.sqrt((x ** 2).mean()) / 32768.0 + 1e-12)
    clip = 100.0 * np.mean(np.abs(pcm) >= 32767)
    _, lv, sl = ns.octave_slope(pcm, FS)
    return dbfs, clip, float(idxs.mean()), float(np.mean(sl))


rows = []
for d in ('firmware/bose/extracted/internal_fs', 'firmware/bose/extracted/ext_fs'):
    for p in sorted(glob.glob(os.path.join(ROOT, d, '*'))):
        if not os.path.isfile(p):
            continue
        b = open(p, 'rb').read()
        if len(b) < 16000:        # < 2 s of audio is not a sustain candidate
            continue
        dbfs, clip, idx, slope = score(b)
        rows.append((clip, os.path.basename(p), len(b), len(b) * 2 / FS, dbfs, idx, slope))

print('EVERY filesystem file >= 16 kB, decoded as IMA ADPCM, sorted by clipping')
print('%-16s %9s %7s %8s %7s %7s %9s' % ('file', 'bytes', 'secs', 'dBFS', 'clip%', 'idx', 'dB/oct'))
for clip, name, n, secs, dbfs, idx, slope in sorted(rows):
    print('%-16s %9d %7.1f %8.1f %7.2f %7.1f %+9.2f' % (name, n, secs, dbfs, clip, idx, slope))

print('\nReference: project generator  -15.5 dBFS   0.00 clip%   idx 36   -4.9 dB/oct')
print('A usable sleep sound needs clip% near 0 and an index well below 88.')

# --- ext_flash.bin, never examined: scan in 60 kB windows for a quiet region ---
p = os.path.join(ROOT, 'firmware/bose/extracted/ext_flash.bin')
if os.path.exists(p):
    b = open(p, 'rb').read()
    print('\next_flash.bin: %d bytes (%.0f kB). Scanning 60 kB windows.' % (len(b), len(b) / 1024))
    W = 60000
    best = []
    for off in range(0, len(b) - W, W):
        w = b[off:off + W]
        if len(set(w[:4000])) < 8:      # skip erased/constant regions
            continue
        dbfs, clip, idx, slope = score(w)
        best.append((clip, off, dbfs, idx, slope))
    best.sort()
    print('  %d non-constant windows; the 8 with least clipping:' % len(best))
    for clip, off, dbfs, idx, slope in best[:8]:
        print('    off 0x%06x  dBFS %6.1f  clip %6.2f%%  idx %5.1f  %+.2f dB/oct'
              % (off, dbfs, clip, idx, slope))
