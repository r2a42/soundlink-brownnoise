#!/usr/bin/env python3
"""Brown-noise payloads for TransformAdpcmDecode -> Kalimba port 3 (tools/adpcm.py dialect).

What it does
  1. generates brown noise: white Gaussian noise through a LEAKY integrator (so it does not
     drift to DC), then an optional 2nd-order high-pass (keeps DC/sub-bass out and makes the
     loop seam clean), optionally made LOOPABLE by an equal-power crossfade of the tail into
     the head, then normalised to a chosen peak;
  2. encodes it with tools/adpcm.py from the decoder's initial state (0,0), exactly as a fresh
     TransformAdpcmDecode will decode it;
  3. writes (a) the payload bytes, (b) a .wav preview of the DECODED payload at the playback
     rate (what the speaker will reproduce, before the DSP's tone path), and prints a report
     (level, clipping, octave slope, round-trip SNR, loop-seam step, onset length);
  4. --interleave PATTERN: lays the payload out in a periodic byte pattern of OURS and STOCK
     bytes (the DFU blind-window shape is 64:34-62 = bytes 34..62 of every 64 are ours), fills
     the stock positions from --stock (random | zeros | file:PATH[:OFFSET]), and reports what
     the decoder makes of the result, two ways: NAIVE (our bytes encoded as if contiguous) and
     AWARE (the encoder runs the decoder through the stock bytes and continues from the state
     they leave). It writes the interleaved stream and a .wav of its decode too.

Usage
  python tools/brownnoise.py --rate 2000 --seconds 20 --out build/brownnoise/brown_2000.adpcm
  python tools/brownnoise.py --rate 8000 --seconds 20 --peak 0.7 --hp 30 --loop
  python tools/brownnoise.py --rate 2000 --seconds 10 --interleave 64:34-62 --stock random
  python tools/brownnoise.py --rate 2000 --seconds 10 --interleave 64:34-62 \
        --stock file:firmware/bose/extracted/internal_fs/data_us:4096
  python tools/brownnoise.py --selftest

  python tools/brownnoise.py --rate 8000 --bytes 219528 --loop --out build/noise/brown_8000_219528.bin
  python tools/brownnoise.py --seam-test build/noise/brown_8000_219528.bin --rate 8000

  # 2026-10-12 (J-T7): the FFT-shaped, exactly periodic generator (--gen) and its helpers
  python tools/brownnoise.py --rate 8000 --bytes 60100 --gen fft --loop --peak 0.985 --seed 63
  python tools/brownnoise.py --rate 8000 --bytes 60100 --gen fft --loop --peak 0.97 --seed 2 --crest-sigma 3
  python tools/brownnoise.py --ref-table reference.wav          # octave table of a reference wav

Options
  --rate HZ        playback (tone-port) rate the payload is meant for      [2000]
  --seconds S      duration                                                 [20]
  --bytes N        exact payload size in bytes (= 2N samples); overrides --seconds. Use it
                   to fill a file slot exactly (rphrases_us 10,486; soundClearWb.kap 65,242;
                   data_us 219,528)
  --seam-test PATH decode PATH twice concatenated (fresh transform = state reset at the
                   seam, and state carried) and report the seam discontinuity against the
                   material's own step distribution; no generation
  --peak F         normalise to F x full scale (0..1)                       [0.5]
  --leak HZ        leaky-integrator corner: the brown slope flattens below  [10; fft: 0]
  --hp HZ          2nd-order high-pass corner (0 = none)                    [20]
  --loop           crossfade the tail into the head (loopable payload)
  --xfade MS       crossfade length for --loop                              [50]
  --seed N         PRNG seed                                                [1]
  --gen G          integrator (default; the shipped probe184 recipe, byte-identical) | fft:
                   white Gaussian shaped in the FFT domain to amplitude 1/f x 2nd-order HP, so
                   the target is the ideal analog 1/f^2 in every octave and the signal is
                   EXACTLY periodic over the file (no crossfade; --loop only rotates it to a
                   restart point chosen by trial encodes). Needs numpy.
  fft only:        --lp HZ (2nd-order low-pass), --shelf-db DB and --shelf-hz HZ (first-order
                   low shelf), --tilt DB (extra dB per octave about 1 kHz), --crest-sigma K and
                   --crest-iters N [60] (crest-factor reduction: clip at K x rms, put the
                   magnitude spectrum back, repeat; the octave table stays on target while the
                   peak drops), --rot-cands N [12] (rotations tried by trial encode)
  --ref-table PATH print the octave table (against ideal 1/f^2, re its 160-320 Hz band) of a
                   16-bit PCM wav so a reference can be compared with the payload; no generation
  --out PATH       payload bytes          [build/brownnoise/brown_<rate>.adpcm]
  --wav PATH       decoded preview .wav   [<out>.wav]
  --also-rate HZ   write a second preview at another rate (a 2000-Hz payload is played at
                   8000 Hz by the FIRST chunk after a DSP load: hear what that does)
  --interleave P   period pattern: "64:34-62" (period:lo-hi[,lo-hi...] of OURS bytes) or a
                   string of o/s characters ("ooss...")
  --stock SPEC     random | zeros | file:PATH[:OFFSET]                      [random]
  --pattern-name N label for the report
"""
import hashlib
import math
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adpcm  # noqa: E402

try:
    import numpy as np
except ImportError:  # the generator and the report fall back to pure Python (slower)
    np = None


# The shipped probe184 payload (docs/deep/offline-2026-10-10/payload-184.md:45); the default recipe must never change.
SHIPPED_30000_SHA256 = 'f832c4d65dc7c5fee91c4c8c44c2f5664115020b122fe3338c9a4d0c30dba4dc'
# sha256 pin of the small fft recipe used by --selftest, valid for this Python/numpy pair only
# (a different numpy may round irfft differently; the statistical checks run regardless)
FFT_PIN_PYTHON = (3, 11)
FFT_PIN_NUMPY = '2.4.2'
FFT_PIN_SHA256 = 'a48c55a7b1d6f780abec7db4e9745316dcccf24034e95fe097d7b87652079a7f'

# ----------------------------------------------------------------------------- generation
def biquad_hp(x, fs, fc, q=0.7071):
    """2nd-order Butterworth high-pass (RBJ cookbook), in place on a list of floats."""
    if not fc:
        return x
    w0 = 2 * math.pi * fc / fs
    alpha = math.sin(w0) / (2 * q)
    cw = math.cos(w0)
    b0 = (1 + cw) / 2
    b1 = -(1 + cw)
    b2 = (1 + cw) / 2
    a0 = 1 + alpha
    a1 = -2 * cw
    a2 = 1 - alpha
    b0, b1, b2, a1, a2 = b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0
    y = [0.0] * len(x)
    x1 = x2 = y1 = y2 = 0.0
    for i, xi in enumerate(x):
        yi = b0 * xi + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, xi, y1, yi
        y[i] = yi
    return y


def brown(n, fs, leak_hz, hp_hz, seed, loop=False, xfade_ms=50.0):
    """Brown noise as floats, peak-normalised to 1.0. Leaky integrator then high-pass."""
    rnd = random.Random(seed)
    a = math.exp(-2 * math.pi * leak_hz / fs) if leak_hz else 1.0
    extra = int(fs * xfade_ms / 1000) if loop else 0
    total = n + extra + int(fs)        # one extra second of warm-up, discarded
    y = [0.0] * total
    acc = 0.0
    for i in range(total):
        acc = a * acc + rnd.gauss(0.0, 1.0)
        y[i] = acc
    y = y[int(fs):]                    # drop the warm-up
    y = biquad_hp(y, fs, hp_hz)
    if loop and extra:
        # equal-power crossfade: tail (last `extra`) fades out under the head fading in
        head = y[:extra]
        tail = y[n:n + extra]
        for i in range(extra):
            t = (i + 0.5) / extra
            g_in = math.sin(0.5 * math.pi * t)
            g_out = math.cos(0.5 * math.pi * t)
            y[i] = head[i] * g_in + tail[i] * g_out
        y = y[:n]
        # rotate the loop so it STARTS (and therefore ends) at a quiet zero crossing: every
        # chunk is a fresh transform whose decoder starts from predictor 0, so the seam step
        # equals |last sample|; starting at a zero crossing makes that step ~0
        best, best_i = None, 0
        for i in range(1, n - 1):
            m = abs(y[i]) + 0.5 * (abs(y[i + 1] - y[i]) + abs(y[i] - y[i - 1]))
            if best is None or m < best:
                best, best_i = m, i
        y = y[best_i:] + y[:best_i]
    else:
        y = y[:n]
    peak = max(abs(v) for v in y) or 1.0
    return [v / peak for v in y]


def to_pcm16(x, peak):
    lim = peak * 32767.0
    return [int(round(max(-32768, min(32767, v * lim)))) for v in x]


def brown_fft(n, fs, leak_hz, hp_hz, seed, lp_hz=0.0, shelf_db=0.0, shelf_hz=150.0,
              tilt_db=0.0, crest_sigma=0.0, crest_iters=60):
    """FFT-shaped brown noise: n samples (a circular, exactly periodic signal), as floats
    peak-normalised to 1.0. White Gaussian (random.Random(seed).gauss, stable across Python
    versions) -> rfft -> amplitude 1/sqrt(f^2+leak^2) x 2nd-order HP x optional LP, shelf and
    tilt -> irfft. crest_sigma > 0 reduces the crest factor by alternating projection: clip the
    time signal at crest_sigma x rms, then put the original magnitude spectrum back (the phases
    are kept), repeat. Needs numpy."""
    if np is None:
        raise SystemExit('--gen fft needs numpy')
    rnd = random.Random(seed)
    w = np.array([rnd.gauss(0.0, 1.0) for _ in range(n)])
    f = np.fft.rfftfreq(n, 1.0 / fs)
    fm = f[1:]
    h = np.zeros_like(f)
    h[1:] = 1.0 / np.sqrt(fm ** 2 + leak_hz ** 2)
    if hp_hz:
        h[1:] *= 1.0 / np.sqrt(1.0 + (hp_hz / fm) ** 4)
    if lp_hz:
        h[1:] *= 1.0 / np.sqrt(1.0 + (fm / lp_hz) ** 4)
    if shelf_db:
        g = 10.0 ** (shelf_db / 20.0)
        h[1:] *= np.abs(1.0 + (g - 1.0) / (1.0 + 1j * fm / shelf_hz))
    if tilt_db:
        h[1:] *= (fm / 1000.0) ** (tilt_db / 6.0206)
    spec = np.fft.rfft(w) * h
    x = np.fft.irfft(spec, n)
    if crest_sigma > 0:
        mag = np.abs(spec)
        sigma = math.sqrt(float(np.mean(x ** 2)))
        for _ in range(int(crest_iters)):
            c = np.clip(x, -crest_sigma * sigma, crest_sigma * sigma)
            cs = np.fft.rfft(c)
            x = np.fft.irfft(mag * cs / np.maximum(np.abs(cs), 1e-300), n)
    return (x / np.abs(x).max()).tolist()


def restart_rotation(x, peak, cands=12, fs=8000):
    """Rotate the circular signal x (floats) so that a FRESH decoder (state (0,0), step index 0)
    can start it, the end meets the start, and the level does not dip there.
    Eligible start points are zero crossings (|x| <= 0.05 sigma) whose 100 ms before and after
    match the whole-file rms within 0.5 dB. Each is ranked by how well the decoder tracks the
    first 32 samples from state (0,0) (the encoder is causal, so a trial encode of the first 256
    samples is exactly what the full file will do); the `cands` best, spaced at least 400 samples
    apart, are encoded in full and scored by the decoded seam step + the largest sample step among
    the first and last 16 samples + 2 x the onset error + 500 per dB of level mismatch.
    Returns the best rotation (floats)."""
    a = np.asarray(x)
    n = len(a)
    sig = float(a.std())
    w = max(64, min(int(0.1 * fs), n // 8))
    e = np.concatenate([a * a] * 3)
    cs = np.concatenate([[0.0], np.cumsum(e)])
    idx = np.arange(n) + n
    before = (cs[idx] - cs[idx - w]) / w
    after = (cs[idx + w] - cs[idx]) / w
    g = float(np.mean(a * a))
    dev = np.maximum(np.abs(10 * np.log10(before / g + 1e-12)), np.abs(10 * np.log10(after / g + 1e-12)))
    elig = np.where(np.abs(a) <= 0.05 * sig)[0]
    ok = elig[dev[elig] <= 0.5]
    if len(ok) < 20:
        ok = elig[np.argsort(dev[elig], kind='stable')[:200]] if len(elig) else np.array([int(np.argmin(np.abs(a)))])
    if len(ok) > 800:
        ok = ok[::len(ok) // 800 + 1]
    head = min(256, n)

    def onset(k):
        seg = a[(np.arange(head) + k) % n]
        pcm = to_pcm16(seg.tolist(), peak)
        dec = adpcm.decode(adpcm.encode(pcm))
        err = np.asarray(dec[:32], dtype=float) - np.asarray(pcm[:32], dtype=float)
        return math.sqrt(float(np.mean(err ** 2)))

    ons = {int(k): onset(int(k)) for k in ok}
    picks = []
    for k in sorted(ons, key=lambda q: (ons[q] + 200.0 * dev[q], q)):
        if all(min(abs(k - j), n - abs(k - j)) >= 400 for j in picks):
            picks.append(k)
        if len(picks) >= cands:
            break
    best = None
    for k in picks:
        dec = adpcm.decode(adpcm.encode(to_pcm16(np.roll(a, -k).tolist(), peak)))
        seam = abs(dec[0] - dec[-1])
        win = max(abs(dec[j + 1] - dec[j]) for j in list(range(0, 16)) + list(range(n - 17, n - 1)))
        sc = seam + win + 2.0 * ons[k] + 500.0 * float(dev[k])
        if best is None or sc < best[0]:
            best = (sc, k)
    return np.roll(a, -best[1]).tolist()


def octave_vs_ideal(pcm, fs, hp=20.0):
    """Octave-band level of `pcm` against the ideal analog 1/f^2 (2nd-order HP at `hp`), in dB,
    after removing the offset of the 160-320 Hz band. One Hann periodogram of the whole signal;
    bands 20-40, 40-80, ... up to Nyquist (the top band is cut at 0.999 x Nyquist). Returns
    [(lo, hi, dB)], or None without numpy or for a very short signal."""
    if np is None or len(pcm) < 4096:
        return None
    x = np.asarray(pcm, dtype=np.float64)
    x = x - x.mean()
    n = len(x)
    p = np.abs(np.fft.rfft(x * np.hanning(n))) ** 2
    f = np.fft.rfftfreq(n, 1.0 / fs)
    fz = np.maximum(f, 1e-9)
    ideal = 1.0 / fz ** 2
    if hp:
        ideal = ideal / (1.0 + (hp / fz) ** 4)
    nyq = 0.999 * fs / 2.0
    rows = []
    lo = 20.0
    while lo < nyq:
        hi = min(2 * lo, nyq)
        if hi - lo >= 0.25 * lo:
            m = (f >= lo) & (f < hi)
            if m.sum() > 2:
                rows.append((lo, hi, 10 * math.log10(p[m].mean() / ideal[m].mean())))
        lo *= 2
    if not rows:
        return None
    ref = next((r[2] for r in rows if abs(r[0] - 160.0) < 1e-6), rows[-1][2])
    return [(a, b, v - ref) for a, b, v in rows]


def read_wav_mono(path):
    import wave
    w = wave.open(path, 'rb')
    if w.getsampwidth() != 2:
        raise SystemExit('%s: only 16-bit PCM wav is supported' % path)
    ch, fs = w.getnchannels(), w.getframerate()
    raw = struct.unpack('<%dh' % (w.getnframes() * ch), w.readframes(w.getnframes()))
    w.close()
    if ch > 1:
        raw = [sum(raw[i:i + ch]) / ch for i in range(0, len(raw), ch)]
    return list(raw), fs


def ref_table(path):
    pcm, fs = read_wav_mono(path)
    rows = octave_vs_ideal(pcm, fs, 20.0)
    print('== reference table %s: %d samples = %.1f s at %d Hz, %.1f dBFS rms'
          % (path, len(pcm), len(pcm) / fs, fs, dbfs(pcm)))
    if not rows:
        print('   too short for a table')
        return
    print('   octave Hz : ' + ' '.join('%g-%g' % (a, b) for a, b, _ in rows))
    print('   vs ideal 1/f^2 (HP 20), re 160-320 Hz: ' + ' '.join('%+.1f' % v for _, _, v in rows))
    sl = [rows[i + 1][2] - rows[i][2] for i in range(len(rows) - 1)]
    print('   step between neighbouring rows: ' + ' '.join('%+.1f' % v for v in sl)
          + '  (0 = on the ideal brown slope; negative = steeper, positive = shallower)')


# ----------------------------------------------------------------------------- analysis
def dbfs(pcm):
    if not pcm:
        return float('-inf')
    rms = math.sqrt(sum(float(v) * v for v in pcm) / len(pcm))
    return 20 * math.log10(rms / 32768.0) if rms > 0 else float('-inf')


def octave_report(pcm, fs):
    """Octave-band levels (dB, relative to the band at 125 Hz or the lowest available) and
    the mean slope in dB/octave over the bands that fit below Nyquist."""
    if np is None or len(pcm) < 1024:
        return None
    x = np.asarray(pcm, dtype=np.float64)
    x -= x.mean()
    n = 1 << int(math.floor(math.log2(len(x))))
    seg = x[:n] * np.hanning(n)
    psd = np.abs(np.fft.rfft(seg)) ** 2
    freq = np.fft.rfftfreq(n, 1.0 / fs)
    centres = [31.25, 62.5, 125, 250, 500, 1000, 2000, 4000]
    out = []
    for f0 in centres:
        lo, hi = f0 / 2 ** 0.5, f0 * 2 ** 0.5
        if hi > fs / 2:
            break
        m = (freq >= lo) & (freq < hi)
        if m.sum() < 2:
            continue
        out.append((f0, 10 * math.log10(psd[m].mean() + 1e-30)))
    if len(out) < 2:
        return None
    ref = out[0][1]
    slopes = [out[i + 1][1] - out[i][1] for i in range(len(out) - 1)]
    return [(f, lv - ref) for f, lv in out], sum(slopes) / len(slopes)


def clip_pct(pcm):
    return 100.0 * sum(1 for v in pcm if v >= 32767 or v <= -32768) / max(1, len(pcm))


def snr_db(target, got):
    n = min(len(target), len(got))
    if n == 0:
        return float('nan')
    sig = sum(float(t) * t for t in target[:n])
    err = sum((float(t) - g) ** 2 for t, g in zip(target[:n], got[:n]))
    return 10 * math.log10(sig / err) if err > 0 else float('inf')


def report_payload(name, target, data, fs, loop):
    dec, end_state = adpcm.decode_state(data)
    print('== %s' % name)
    print('   %d bytes = %d samples = %.2f s at %d Hz (%.2f s if played at 8000 Hz)'
          % (len(data), len(dec), len(dec) / fs, fs, len(dec) / 8000.0))
    print('   target: %.1f dBFS rms, peak %d;  decoded: %.1f dBFS rms, peak %d, clipped %.2f%%'
          % (dbfs(target), max(abs(v) for v in target), dbfs(dec), max(abs(v) for v in dec), clip_pct(dec)))
    print('   round-trip SNR %.1f dB; decoder end state (pred %d, index %d)'
          % (snr_db(target, dec), end_state[0], end_state[1]))
    # onset: samples until the decoder is within 10% of the peak of the target
    thr = 0.1 * max(abs(v) for v in target)
    onset = next((i for i in range(len(dec)) if abs(dec[i] - target[i]) < thr), len(dec))
    print('   onset from state (0,0): decoder within 10%% of the target after %d samples (%.1f ms)'
          % (onset, 1000.0 * onset / fs))
    oc = octave_report(dec, fs)
    if oc:
        bands, slope = oc
        print('   octave bands (dB re lowest): ' + ' '.join('%g:%+.1f' % (f, lv) for f, lv in bands))
        print('   mean slope %+.2f dB/octave (brown = -6.0, pink = -3.0, white = 0)' % slope)
    iv = octave_vs_ideal(dec, fs)
    if iv:
        print('   vs ideal analog 1/f^2 (HP 20), octaves %s Hz, dB re 160-320 Hz: %s'
              % ('/'.join('%g' % a for a, _, _ in iv), ' '.join('%+.2f' % v for _, _, v in iv)))
    # the seam: chunk after chunk = a FRESH transform each time (state reset) -- what the
    # start-only cycle does; and a carried state (if one transform ever looped the bytes)
    twice_reset = dec + adpcm.decode(data)
    twice_carry = dec + adpcm.decode(data, end_state)
    n = len(dec)
    steps = sorted(abs(dec[i + 1] - dec[i]) for i in range(n - 1))
    p99 = steps[int(0.99 * (n - 2))]
    seam_reset = abs(twice_reset[n] - twice_reset[n - 1])
    seam_carry = abs(twice_carry[n] - twice_carry[n - 1])
    print('   seam step: %d (fresh transform, state reset) / %d (state carried); '
          'typical 99th-percentile step %d; loop crossfade %s'
          % (seam_reset, seam_carry, p99, loop if isinstance(loop, str) else 'on' if loop else 'off'))
    print('   end-of-payload predictor %d (a non-zero value is the DC step the NEXT chunk starts from)'
          % end_state[0])
    return dec


def seam_test(path, fs):
    """Decode the payload twice, concatenated, both ways a chunk boundary can happen:
    RESET = each chunk is a fresh TransformAdpcmDecode (state (0,0) at the seam: the
    start-only cycle on the speaker), CARRY = one transform reading the bytes twice (state
    carried). Reports the seam step against the material's own step distribution."""
    data = open(path, 'rb').read()
    one, end_state = adpcm.decode_state(data)
    n = len(one)
    reset = one + adpcm.decode(data)
    carry = one + adpcm.decode(data, end_state)
    steps = sorted(abs(one[i + 1] - one[i]) for i in range(n - 1))
    p99 = steps[int(0.99 * (n - 2))]
    p999 = steps[int(0.999 * (n - 2))]
    mx = steps[-1]
    seam_reset = abs(reset[n] - reset[n - 1])
    seam_carry = abs(carry[n] - carry[n - 1])
    # the largest step anywhere in a +-16-sample window around the seam, both ways
    win_reset = max(abs(reset[i + 1] - reset[i]) for i in range(n - 16, n + 16))
    win_carry = max(abs(carry[i + 1] - carry[i]) for i in range(n - 16, n + 16))
    print('== seam test %s: %d bytes = %d samples = %.2f s at %d Hz' % (path, len(data), n, n / fs, fs))
    print('   material steps: 99th pct %d, 99.9th pct %d, max %d; last sample %d, end state (pred %d, index %d)'
          % (p99, p999, mx, one[-1], end_state[0], end_state[1]))
    print('   seam step, fresh transform (state reset): %d  [%.2f x p99]  window max %d'
          % (seam_reset, seam_reset / max(1, p99), win_reset))
    print('   seam step, state carried              : %d  [%.2f x p99]  window max %d'
          % (seam_carry, seam_carry / max(1, p99), win_carry))
    verdict = 'inaudible in principle (below the 99th-percentile step)' if max(seam_reset, seam_carry) <= p99 \
        else 'within the material (below its max step)' if max(seam_reset, seam_carry) <= mx \
        else 'LARGER THAN ANY STEP IN THE MATERIAL: a click'
    print('   verdict: %s' % verdict)
    return seam_reset, seam_carry, p99, mx


# ----------------------------------------------------------------------------- interleave
def parse_pattern(spec):
    """-> (period, set of OURS positions)."""
    if ':' in spec:
        period, ranges = spec.split(':', 1)
        period = int(period)
        ours = set()
        for r in ranges.split(','):
            lo, hi = (r.split('-') + [None])[:2]
            lo = int(lo)
            hi = int(hi) if hi is not None else lo
            ours.update(range(lo, hi + 1))
        return period, {p for p in ours if 0 <= p < period}
    period = len(spec)
    return period, {i for i, c in enumerate(spec) if c.lower() == 'o'}


def stock_bytes(spec, n, seed):
    if spec == 'random':
        rnd = random.Random(seed + 1000)
        return bytes(rnd.randrange(256) for _ in range(n))
    if spec == 'zeros':
        return bytes(n)
    if spec.startswith('file:'):
        parts = spec[5:].rsplit(':', 1)
        path = parts[0]
        off = int(parts[1], 0) if len(parts) > 1 else 0
        b = open(path, 'rb').read()
        if off + n > len(b):
            raise SystemExit('stock file %s too short for offset %d + %d bytes' % (path, off, n))
        return b[off:off + n]
    raise SystemExit('unknown --stock %r' % spec)


def interleave(target, period, ours, stock, aware):
    """Build the interleaved stream for `target` samples. Our bytes fill the OURS positions
    period after period; stock bytes fill the rest. aware=True: the encoder's state is the
    DECODER's real state (it runs the decoder through the stock bytes); aware=False: the
    encoder pretends our bytes are contiguous."""
    n_ours = len(ours)
    out = bytearray()
    state = adpcm.INITIAL_STATE
    enc_state = adpcm.INITIAL_STATE
    si = 0                                   # sample index into target
    stock_i = 0
    while si < len(target):
        for p in range(period):
            if p in ours:
                pair = target[si:si + 2]
                if not pair:
                    break
                if aware:
                    b, enc_state = adpcm.encode_state(pair, state)
                else:
                    b, enc_state = adpcm.encode_state(pair, enc_state)
                out += b
                _, state = adpcm.decode_state(b, state)
                si += 2
            else:
                sb = stock[stock_i % len(stock)]
                stock_i += 1
                out.append(sb)
                _, state = adpcm.decode_state(bytes([sb]), state)
        if n_ours == 0:
            break
    return bytes(out)


def report_interleave(label, target, data, period, ours, fs):
    dec = adpcm.decode(data)
    # classify each decoded sample as ours / stock by its byte position
    ours_s, stock_s, tgt_ours = [], [], []
    si = 0
    idx_at_band_start, idx_at_band_end = [], []
    state = adpcm.INITIAL_STATE
    nib = adpcm.nibbles(data)
    k = 0
    for bi, b in enumerate(data):
        p = bi % period
        is_ours = p in ours
        if is_ours and (bi == 0 or (bi - 1) % period not in ours):
            idx_at_band_start.append(state[1])
        for _ in range(2):
            s, state = adpcm.step_one(state, nib[k])
            k += 1
            if is_ours:
                ours_s.append(s)
                if si < len(target):
                    tgt_ours.append(target[si])
                si += 1
            else:
                stock_s.append(s)
        if is_ours and (bi + 1) % period not in ours:
            idx_at_band_end.append(state[1])
    print('== interleave %s: period %d, %d OURS bytes (%.0f%% of the time), gating rate %.1f Hz'
          % (label, period, len(ours), 100.0 * len(ours) / period, fs / (2.0 * period)))
    print('   whole decode : %.1f dBFS, peak %d, clipped %.2f%%'
          % (dbfs(dec), max(abs(v) for v in dec), clip_pct(dec)))
    print('   OURS samples : %.1f dBFS, clipped %.2f%%, SNR vs target %.1f dB'
          % (dbfs(ours_s), clip_pct(ours_s), snr_db(tgt_ours, ours_s)))
    print('   STOCK samples: %.1f dBFS, clipped %.2f%%' % (dbfs(stock_s), clip_pct(stock_s)))
    if idx_at_band_start:
        print('   step index at our band starts: mean %.1f (min %d, max %d); at band ends: mean %.1f'
              % (sum(idx_at_band_start) / len(idx_at_band_start), min(idx_at_band_start),
                 max(idx_at_band_start), sum(idx_at_band_end) / len(idx_at_band_end)))
    oc = octave_report(dec, fs)
    if oc:
        bands, slope = oc
        print('   octave bands (dB re lowest): ' + ' '.join('%g:%+.1f' % (f, lv) for f, lv in bands)
              + '   slope %+.2f dB/oct' % slope)
    return dec


# ----------------------------------------------------------------------------- main
def selftest():
    ok = adpcm.selftest(verbose=False)
    x = brown(4000, 2000, 10, 20, 1)
    pcm = to_pcm16(x, 0.5)
    data = adpcm.encode(pcm)
    dec = adpcm.decode(data)
    s = snr_db(pcm, dec)
    if s < 15:
        ok = False
    per, ours = parse_pattern('64:34-62')
    if per != 64 or len(ours) != 29 or 33 in ours or 63 in ours:
        ok = False
    per2, ours2 = parse_pattern('oss')
    if per2 != 3 or ours2 != {0}:
        ok = False
    st = stock_bytes('zeros', 100, 1)
    il = interleave(pcm[:2000], 64, ours, st, aware=True)
    if len(il) < 2000 // 2 // 29 * 64:
        ok = False
    # 2026-10-12 additions: the shipped recipe must stay byte-identical (probe184 payload, payload-184.md:45);
    # the fft generator must be deterministic, periodic, on the ideal octave levels and crest-reducible
    x = brown(60000, 8000, 10, 20, 1, True, 50.0)
    sha = hashlib.sha256(adpcm.encode(to_pcm16(x, 0.5))).hexdigest()
    if sha != SHIPPED_30000_SHA256:
        print('  FAIL: shipped recipe (integrator, 30000 B, peak 0.5, seed 1) sha256 %s, expected %s'
              % (sha, SHIPPED_30000_SHA256))
        ok = False
    if np is not None:
        a = brown_fft(40000, 8000, 0, 20, 1)
        b = brown_fft(40000, 8000, 0, 20, 1)
        if a != b:
            print('  FAIL: brown_fft is not deterministic')
            ok = False
        steps = sorted(abs(a[i + 1] - a[i]) for i in range(len(a) - 1))
        if abs(a[0] - a[-1]) > 4 * steps[len(steps) // 2]:
            print('  FAIL: brown_fft is not periodic (wrap step %.4f, median step %.4f)'
                  % (abs(a[0] - a[-1]), steps[len(steps) // 2]))
            ok = False
        rows = octave_vs_ideal([v * 30000 for v in a], 8000)
        worst = max(abs(v) for lo, hi, v in rows if lo >= 160)
        if worst > 0.6:
            print('  FAIL: fft octave levels >= 160 Hz are %.2f dB off the ideal (limit 0.6)' % worst)
            ok = False
        c = np.asarray(brown_fft(40000, 8000, 0, 20, 1, crest_sigma=3.0))
        crest = float(np.abs(c).max() / c.std())
        if crest > 3.05:
            print('  FAIL: crest reduction left crest %.2f (target 3.0)' % crest)
            ok = False
        if sys.version_info[:2] == FFT_PIN_PYTHON and np.__version__ == FFT_PIN_NUMPY:
            r = restart_rotation(brown_fft(8000, 8000, 0, 20, 1), 0.9, 4)
            h = hashlib.sha256(adpcm.encode(to_pcm16(r, 0.9))).hexdigest()
            if h != FFT_PIN_SHA256:
                print('  FAIL: fft recipe (4000 B, peak 0.9, seed 1, 4 rotation candidates) sha256 %s, '
                      'expected %s' % (h, FFT_PIN_SHA256))
                ok = False
        else:
            print('  note: fft sha256 pin recorded for Python %d.%d / numpy %s only; here %d.%d / numpy %s, '
                  'statistical checks only' % (FFT_PIN_PYTHON + (FFT_PIN_NUMPY,) + sys.version_info[:2]
                                               + (np.__version__,)))
    print('brownnoise selftest: %s (brown round-trip SNR %.1f dB)' % ('OK' if ok else 'FAIL', s))
    return ok


def main(argv):
    args = {'--rate': '2000', '--seconds': '20', '--peak': '0.5', '--leak': None, '--hp': '20',
            '--xfade': '50', '--seed': '1', '--out': None, '--wav': None, '--also-rate': None,
            '--interleave': None, '--stock': 'random', '--pattern-name': None,
            '--bytes': None, '--seam-test': None, '--gen': 'integrator', '--lp': '0',
            '--shelf-db': '0', '--shelf-hz': '150', '--tilt': '0', '--crest-sigma': '0',
            '--crest-iters': '60', '--rot-cands': '12', '--ref-table': None}
    flags = {'--loop': False, '--selftest': False, '-h': False, '--help': False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in flags:
            flags[a] = True
            i += 1
        elif a in args:
            args[a] = argv[i + 1]
            i += 2
        else:
            raise SystemExit('unknown option %r (see --help)' % a)
    if flags['-h'] or flags['--help']:
        print(__doc__)
        return 0
    if flags['--selftest']:
        return 0 if selftest() else 1
    if args['--ref-table']:
        ref_table(args['--ref-table'])
        return 0
    fs = int(args['--rate'])
    gen = args['--gen']
    if gen not in ('integrator', 'fft'):
        raise SystemExit('--gen must be integrator or fft')
    if args['--leak'] is None:
        args['--leak'] = '10' if gen == 'integrator' else '0'
    if args['--seam-test']:
        seam_test(args['--seam-test'], fs)
        return 0
    if args['--bytes']:
        n = 2 * int(args['--bytes'])          # exactly N bytes: 2 samples per byte
    else:
        n = int(round(fs * float(args['--seconds'])))
        if n % 2:
            n += 1
    out = args['--out'] or os.path.join('build', 'brownnoise', 'brown_%d.adpcm' % fs)
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    wav = args['--wav'] or out + '.wav'
    loop = flags['--loop']
    if gen == 'fft':
        x = brown_fft(n, fs, float(args['--leak']), float(args['--hp']), int(args['--seed']),
                      float(args['--lp']), float(args['--shelf-db']), float(args['--shelf-hz']),
                      float(args['--tilt']), float(args['--crest-sigma']),
                      int(args['--crest-iters']))
        if loop:
            x = restart_rotation(x, float(args['--peak']), int(args['--rot-cands']))
    else:
        x = brown(n, fs, float(args['--leak']), float(args['--hp']), int(args['--seed']), loop,
                  float(args['--xfade']))
    pcm = to_pcm16(x, float(args['--peak']))
    data = adpcm.encode(pcm)
    if args['--bytes'] and len(data) != int(args['--bytes']):
        raise SystemExit('internal: %d bytes written, %s requested' % (len(data), args['--bytes']))
    open(out, 'wb').write(data)
    if gen == 'fft':
        print('generator: fft-shaped brown, exactly periodic (leak %s Hz, high-pass %s Hz, low-pass %s, '
              'shelf %s dB below %s Hz, tilt %s dB/oct, crest-sigma %s x %s, peak %s, seed %s, '
              'rotated to a restart point %s)'
              % (args['--leak'], args['--hp'], args['--lp'], args['--shelf-db'], args['--shelf-hz'],
                 args['--tilt'], args['--crest-sigma'], args['--crest-iters'], args['--peak'],
                 args['--seed'], loop))
    else:
        print('generator: brown (leak %s Hz, high-pass %s Hz, peak %s, seed %s, loop %s)'
              % (args['--leak'], args['--hp'], args['--peak'], args['--seed'], loop))
    print('   sha256 %s' % hashlib.sha256(data).hexdigest())
    dec = report_payload(out, pcm, data, fs,
                         ('off (periodic signal, rotated to a restart point)' if loop else 'off') if gen == 'fft' else loop)
    adpcm.write_wav(wav, dec, fs)
    print('   wrote %s and preview %s' % (out, wav))
    if args['--also-rate']:
        r2 = int(args['--also-rate'])
        w2 = os.path.splitext(wav)[0] + '_at%d.wav' % r2
        adpcm.write_wav(w2, dec, r2)
        print('   also %s (the same bytes played at %d Hz: %.2f s)' % (w2, r2, len(dec) / r2))
    if args['--interleave']:
        period, ours = parse_pattern(args['--interleave'])
        n_stock = (len(data) // max(1, len(ours)) + 2) * (period - len(ours))
        stock = stock_bytes(args['--stock'], max(n_stock, 1), int(args['--seed']))
        label = args['--pattern-name'] or ('%s, stock=%s' % (args['--interleave'], args['--stock']))
        for aware in (False, True):
            il = interleave(pcm, period, ours, stock, aware)
            tag = 'AWARE' if aware else 'NAIVE'
            d = report_interleave('%s [%s encoder]' % (label, tag), pcm, il, period, ours, fs)
            base = os.path.splitext(out)[0]
            p_il = '%s_interleaved_%s.bin' % (base, tag.lower())
            open(p_il, 'wb').write(il)
            adpcm.write_wav(p_il + '.wav', d, fs)
            print('   wrote %s and %s' % (p_il, p_il + '.wav'))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
