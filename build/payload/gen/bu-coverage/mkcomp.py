"""BX: playback-chain pre-compensated 24 kHz loop payloads (offline). Recipe of mkloops.py (circular periodic brown at the
stream rate, restart rotation, peak 0.985, seed 63, beam noise-shaper) with a smooth EQ applied in the circular frequency domain
BEFORE the rotation: a bass bell (centre 90 Hz, sigma 0.85 octave, +B dB) and a presence dip (centre 2.2 kHz, sigma 0.30 octave, C dB).
Usage: python -I mkcomp.py encode B_DB C_DB [NBYTES=58968]   -> audition3/COMP_24k_b<B>_c<C>_<N>B.adpcm (+ .json)
       python -I mkcomp.py predict                           -> audition3/predictions.json (needs the encodes + the three recordings)"""
import json, os, sys, time, hashlib, random
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import mkloops as ml
bn, adpcm, nsenc = ml.bn, ml.adpcm, ml.nsenc
OUT = os.path.join(HERE, 'audition3'); RATE = 24000
ROOT = ml.ROOT
SCRATCH = os.environ.get('PAYLOAD_SCRATCH', '')   # only read by optional analysis helpers, not by the payload build

def eq_db(f, B, C):
    f = np.maximum(f, 1e-3)
    return B * np.exp(-0.5 * (np.log2(f / 90.0) / 0.85) ** 2) + C * np.exp(-0.5 * (np.log2(f / 2200.0) / 0.30) ** 2)

def limit(x, g_db, knee):
    """gain g_db then a smooth memoryless soft limiter: identity below `knee` (of full scale 1.0), tanh knee above, asymptote 1.0."""
    y = np.asarray(x) * 10 ** (g_db / 20.0); a = np.abs(y)
    out = np.where(a <= knee, a, knee + (1 - knee) * np.tanh((a - knee) / (1 - knee)))
    return (np.sign(y) * out).tolist()

def pcm_comp(rate, nbytes, B, C, G=0.0, K=0.6):
    n = 2 * nbytes
    rnd = random.Random(ml.SEED)
    w = np.array([rnd.gauss(0.0, 1.0) for _ in range(n)])
    f = np.fft.rfftfreq(n, 1.0 / rate); fm = f[1:]
    h = np.zeros_like(f); h[1:] = 1.0 / fm * (1.0 / np.sqrt(1.0 + (ml.HP / fm) ** 4))
    h[1:] *= 10 ** (eq_db(fm, B, C) / 20.0)
    x = np.fft.irfft(np.fft.rfft(w) * h, n)
    x = (x / np.abs(x).max()).tolist()
    if G: x = limit(x, G, K)
    x = bn.restart_rotation(x, ml.PEAK, 12, fs=rate)
    return bn.to_pcm16(x, ml.PEAK)

def tagc(B, C, nb, G=0.0, K=0.6):
    t = tagc0(B, C, nb)
    return t + ('_g%gk%g' % (G, K * 100) if G else '')

def tagc0(B, C, nb): return 'COMP_24k_b%g_c%g_%dB' % (B, -C if C < 0 else C, nb) if C >= 0 else 'COMP_24k_b%g_cm%g_%dB' % (B, -C, nb)

def do_encode(B, C, nb, G=0.0, K=0.6):
    t0 = time.time(); rate = RATE
    pcm = pcm_comp(rate, nb, B, C, G, K)
    ph, tw = 0.33 * rate, 0.044 * rate
    W = nsenc.design_w(rate, ml.prof(ph, 24.0, tw), order=8)
    best = None
    for tl, tg in [(0, 0.0), (600, 4.0), (1500, 10.0), (3000, 40.0)]:
        d = nsenc.encode_ns(pcm, W=W, beam=32, tail=tl, tail_gain=tg)[0]
        dd = adpcm.decode(d); sm = abs(dd[0] - dd[-1])
        if best is None or sm < best[0]: best = (sm, d, (tl, tg))
    data = best[1]; assert len(data) == nb
    name = tagc(B, C, nb, G, K); os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, name + '.adpcm'), 'wb').write(data)
    dec = np.array(adpcm.decode(data), dtype=float); ref = np.array(pcm, dtype=float)
    m = {'B': B, 'C': C, 'G': G, 'K': K, 'bytes': nb, 'tail_variant': best[2], 'first4': data[:4].hex(), 'sha256': hashlib.sha256(data).hexdigest(),
         'md5': hashlib.md5(data).hexdigest(), 'snr_db': float(10 * np.log10(np.sum(ref ** 2) / np.sum((dec - ref) ** 2))),
         'clipped': int(np.sum((dec >= 32767) | (dec <= -32768))), 'seam_step': float(abs(dec[0] - dec[-1])),
         'p99_step': float(np.percentile(np.abs(np.diff(dec)), 99)), 'rms_dbfs': float(10 * np.log10(np.mean(dec ** 2) / 32768 ** 2)),
         'peak': float(np.abs(dec).max()), 'encode_s': time.time() - t0}
    json.dump(m, open(os.path.join(OUT, name + '.json'), 'w'), indent=1)
    print(name, json.dumps(m)); sys.stdout.flush()

if __name__ == '__main__':
    if sys.argv[1] == 'encode':
        do_encode(float(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4]) if len(sys.argv) > 4 else 58968, float(sys.argv[5]) if len(sys.argv) > 5 else 0.0, float(sys.argv[6]) if len(sys.argv) > 6 else 0.6)

def band_db(dec, rate):
    """mean-per-bin power in dB for the xfer.py third-octave edges, exact periodic lines of the decoded loop."""
    import xfer
    X = np.abs(np.fft.rfft(dec - dec.mean())) ** 2; f = np.fft.rfftfreq(len(dec), 1.0 / rate)
    return np.array([10 * np.log10(X[(f >= lo) & (f < hi)].mean() + 1e-9) for lo, hi in xfer.EDG])

def wrap_click(dec):
    two = np.concatenate([dec, dec]); n = len(dec)
    st = np.abs(np.diff(two)); p99 = np.percentile(np.abs(np.diff(dec)), 99)
    return float(st[n - 1]), float(st[n - 17:n + 15].max()), float(p99)

def do_predict(extra_files):
    sys.path.append(SCRATCH)
    import xfer
    T = os.path.join(ROOT, 'build', 'payload', 'target')
    a, fs = xfer.load(os.path.join(T, 'q_stream_owner_phone_rec.wav'))
    c, _ = xfer.load(os.path.join(T, 'q_internal_probe305.wav'))
    A = xfer.bands(a, fs, 3, 30); C = xfer.bands(c, fs, 3, 18)
    ref = [i for i, (lo, hi) in enumerate(xfer.EDG) if lo >= 1000 and hi <= 2000]
    rel = lambda X: X - X[ref].mean()
    d305 = rel(C) - rel(A)
    p305 = np.array(adpcm.decode(open(os.path.join(ROOT, 'build', 'payload', 'g4', 'brown_24000_58968_ns.adpcm'), 'rb').read()), dtype=float)
    P305 = band_db(p305, RATE)
    res = {'edges': xfer.EDG, 'd305_measured': d305.tolist()}
    names = ['p305'] + extra_files
    mid = lambda dec: float(10 * np.log10(np.sum(np.abs(np.fft.rfft(dec - dec.mean())) ** 2 * ((np.fft.rfftfreq(len(dec), 1.0 / RATE) >= 315) & (np.fft.rfftfreq(len(dec), 1.0 / RATE) < 3150)))))
    base_mid = mid(p305)
    print('%-26s rms_dBFS peak  mid(315-3150)re305  wrap_step  wrap_win_max  p99' % 'payload')
    for nm in names:
        dec = p305 if nm == 'p305' else np.array(adpcm.decode(open(os.path.join(OUT, nm + '.adpcm'), 'rb').read()), dtype=float)
        P = band_db(dec, RATE)
        pred = d305 + (rel(P) - rel(P305))
        ws, ww, p99 = wrap_click(dec)
        res[nm] = {'rel_payload_db': rel(P).tolist(), 'pred_internal_minus_stream_db': pred.tolist(), 'rms_dbfs': float(10 * np.log10(np.mean(dec ** 2) / 32768 ** 2)),
                   'peak': float(np.abs(dec).max()), 'mid_re_305_db': mid(dec) - base_mid, 'wrap_step': ws, 'wrap_window_max_step': ww, 'p99_step': p99}
        print('%-26s %7.2f %6.0f %6.2f %10.0f %10.0f %8.0f' % (nm, res[nm]['rms_dbfs'], res[nm]['peak'], res[nm]['mid_re_305_db'], ws, ww, p99))
    print('\nband(Hz)      d305(meas) ' + ' '.join('%12s' % n[:12] for n in names[1:]) + '   [pred internal-stream dB, re 1-2k]')
    for i, (lo, hi) in enumerate(xfer.EDG):
        if hi > 4000: break
        print('%5d-%5d   %+6.1f      ' % (lo, hi, d305[i]) + ' '.join('%+12.1f' % res[n]['pred_internal_minus_stream_db'][i] for n in names[1:]))
    json.dump(res, open(os.path.join(OUT, 'predictions.json'), 'w'), indent=1)

if __name__ == '__main__' and sys.argv[1] == 'predict':
    do_predict(sys.argv[2:])
