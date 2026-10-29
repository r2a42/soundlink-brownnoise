#!/usr/bin/env python3
"""What does a .kap binary SOUND like through TransformAdpcmDecode?

The file-source route feeds arbitrary flash bytes to an IMA ADPCM decoder. Whether that is
a usable sleep sound is a question about the CONTENT, and it is answerable offline with the
project's own decoder -- before spending a press. Reuses tools/noisespec.py's ima_decode so
the model is the one already validated against hardware.
"""
import sys

# This script lives in the scratchpad, which contains a stale dis.py that shadows the
# stdlib module of the same name and breaks `import numpy`. Drop sys.path[0] first.
if sys.path and 'scratchpad' in sys.path[0]:
    sys.path.pop(0)

import os

import numpy as np

ROOT = __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import noisespec as ns

FS = 8000
FILES = [
    ('sbc_decoder.kap', 'firmware/bose/extracted/internal_fs/sbc_decoder.kap'),
    ('NowSpeakTTS.kap', 'build/fsedit/t/official/fs_000bff4c/NowSpeakTTS/NowSpeakTTS.kap'),
    ('soundClearWb.kap', 'build/fsedit/t/official/fs_000bff4c/soundClearWb/soundClearWb.kap'),
]


def nibbles_from_bytes(b, high_first=True):
    a = np.frombuffer(b, dtype=np.uint8).astype(np.int32)
    hi, lo = a >> 4, a & 0xF
    out = np.empty(a.size * 2, dtype=np.int32)
    if high_first:
        out[0::2], out[1::2] = hi, lo
    else:
        out[0::2], out[1::2] = lo, hi
    return out


def report(tag, pcm, idxs):
    x = pcm.astype(np.float64)
    peak = int(np.max(np.abs(pcm)))
    dbfs = 20 * np.log10(np.sqrt((x ** 2).mean()) / 32768.0 + 1e-12)
    clip = 100.0 * np.mean(np.abs(pcm) >= 32767)
    rail = 100.0 * np.mean(idxs >= 87)
    cent, lv, sl = ns.octave_slope(pcm, FS)
    print('  %-11s dBFS %6.1f  peak %6d  clipped %5.2f%%  idx mean %4.1f  railed %5.1f%%'
          % (tag, dbfs, peak, clip, idxs.mean(), rail))
    print('              octaves %s   slopes %s   mean %+.2f dB/oct'
          % (' '.join('%.0f' % v for v in lv),
             ' '.join('%+.2f' % s for s in sl),
             float(np.mean(sl))))


print('Brown noise = -6.00 dB/octave; the project generator measures ~-4.9.')
print('Decoder starts at predictor 0 / index 0, as a fresh transform would.')
print('"railed" = fraction of samples with the ADPCM step index pinned at max (harsh).\n')

for name, rel in FILES:
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        print('%s: ABSENT\n' % name)
        continue
    b = open(p, 'rb').read()
    print('%s  %d bytes -> %.1f s at 8 kHz' % (name, len(b), len(b) * 2 / FS))
    for hf in (True, False):
        nib = nibbles_from_bytes(b, hf)
        pcm, idxs = ns.ima_decode(nib)
        report('high-first' if hf else 'low-first', pcm, idxs)
    print()

# For the recommended file, also look at how uniform it is over time: a sleep sound must
# not lurch between loud and quiet. Report per-second RMS spread.
b = open(os.path.join(ROOT, FILES[0][1]), 'rb').read()
pcm, idxs = ns.ima_decode(nibbles_from_bytes(b, True))
sec = FS
n = len(pcm) // sec
r = np.array([np.sqrt((pcm[i * sec:(i + 1) * sec].astype(np.float64) ** 2).mean())
              for i in range(n)])
db = 20 * np.log10(r / 32768.0 + 1e-12)
print('sbc_decoder.kap per-second level over %d s:' % n)
print('  min %.1f dBFS  max %.1f dBFS  spread %.1f dB  (a steady sound wants a small spread)'
      % (db.min(), db.max(), db.max() - db.min()))
print('  first 10 s: %s' % ' '.join('%.0f' % v for v in db[:10]))
