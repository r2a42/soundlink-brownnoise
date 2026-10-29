#!/usr/bin/env python3
"""recan.py -- offline analysis of a speaker recording (16-bit mono WAV, any rate).

Usage:  python -I tools/recan.py FILE.wav [--from S] [--to S] [--win 2] [--floor F] [--period 14.74]

Prints: per-window rms table with a bar, the noise floor, bursts (events above the floor),
a stationarity verdict for a window range (brown noise = broadband, steady, low spectral
slope variation; speech/prompts = bursty), the spectral tilt (dB per octave; brown noise
is about -6) and, with --period, the autocorrelation of the 50 ms rms envelope at that
period (a chunk cadence shows as a peak).
Offline only; reads one file given on the command line, never opens private/.
"""
import argparse, sys, wave
import numpy as np


def load(path):
    w = wave.open(path)
    n, ch, sw, fs = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
    if sw != 2:
        sys.exit('only 16-bit WAV')
    x = np.frombuffer(w.readframes(n), dtype='<i2').astype(float)
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, fs


def env(x, fs, step=0.05):
    k = int(fs * step)
    m = len(x) // k
    return np.sqrt((x[:m * k].reshape(m, k) ** 2).mean(axis=1)), step


def tilt(seg, fs):
    """spectral slope in dB/octave over 100 Hz..4 kHz (Welch-like average)."""
    n = 4096
    if len(seg) < n * 2:
        return float('nan')
    sp = np.zeros(n // 2 + 1)
    cnt = 0
    win = np.hanning(n)
    for i in range(0, len(seg) - n, n // 2):
        sp += np.abs(np.fft.rfft(seg[i:i + n] * win)) ** 2
        cnt += 1
    f = np.fft.rfftfreq(n, 1 / fs)
    sel = (f >= 100) & (f <= min(4000, fs / 2 - 100))
    p = 10 * np.log10(sp[sel] / cnt + 1e-9)
    a = np.polyfit(np.log2(f[sel]), p, 1)[0]
    return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('wav')
    ap.add_argument('--from', dest='t0', type=float, default=0.0)
    ap.add_argument('--to', dest='t1', type=float, default=None)
    ap.add_argument('--win', type=float, default=2.0)
    ap.add_argument('--floor', type=float, default=None)
    ap.add_argument('--period', type=float, default=None)
    a = ap.parse_args()
    x, fs = load(a.wav)
    dur = len(x) / fs
    t1 = a.t1 if a.t1 is not None else dur
    e, st = env(x, fs)
    floor = a.floor if a.floor is not None else float(np.percentile(e, 10))
    print('file %.1f s, %d Hz, floor(rms, 10th pct of 50 ms) %.1f' % (dur, fs, floor))
    t = a.t0
    while t < t1:
        seg = x[int(t * fs):int((t + a.win) * fs)]
        if len(seg) == 0:
            break
        r = np.sqrt((seg ** 2).mean())
        s = e[int(t / st):int((t + a.win) / st)]
        cv = s.std() / (s.mean() + 1e-9)
        print('%6.1f-%6.1f rms %7.1f  cv(50ms) %4.2f  tilt %5.1f dB/oct  %s' % (
            t, t + a.win, r, cv, tilt(seg, fs), '#' * min(60, int(r / max(floor, 1) / 2))))
        t += a.win
    thr = floor * 3
    on = e > thr
    print('--- bursts above %.1f (merged within 0.3 s)' % thr)
    i = 0
    while i < len(on):
        if on[i]:
            j = i
            gap = 0
            k = i
            while k < len(on) and gap < 6:
                gap = 0 if on[k] else gap + 1
                if on[k]:
                    j = k
                k += 1
            print('  %7.2f-%7.2f s  peak %.0f  mean %.0f' % (i * st, (j + 1) * st, e[i:j + 1].max(), e[i:j + 1].mean()))
            i = j + 1
        else:
            i += 1
    seg = e[int(a.t0 / st):int(t1 / st)]
    cv = seg.std() / (seg.mean() + 1e-9)
    verdict = 'STEADY (noise-like)' if (seg.mean() > thr and cv < 0.35) else 'BURSTY or quiet'
    print('--- range %.1f-%.1f s: mean %.1f cv %.2f -> %s' % (a.t0, t1, seg.mean(), cv, verdict))
    if a.period:
        d = seg - seg.mean()
        lag = int(round(a.period / st))
        if len(d) > lag * 2:
            ac = (d[:-lag] * d[lag:]).mean() / (d.var() + 1e-9)
            print('--- envelope autocorrelation at %.2f s: %.2f (>0.3 suggests the chunk cadence)' % (a.period, ac))


if __name__ == '__main__':
    main()
