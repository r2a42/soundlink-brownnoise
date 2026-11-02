"""BV: looped high-rate noise-shaped ADPCM payloads (encode) and 24 s 44.1 kHz audition renders + objective measures (render).
Offline only. Usage:
  python mkloops.py encode RATE_HZ NBYTES      -> audition2/LOOP_<r>k_<bytes>B.adpcm (+ .json)
  python mkloops.py render A_REF.wav           -> audition2/LOOP_*.wav + audition2/loop_measures.json (needs all .adpcm)
Recipe = product recipe of mkpayload.py (circular periodic brown at the stream rate, restart rotation, peak 0.985, seed 63)
with length 2*NBYTES samples, encoded by the beam noise-shaper with weight 'flat to 0.33 fs, +24 dB above' (the BU4 profile
scaled to the rate), best of four loop-seam tail weightings. The wavs are decode -> tile (decoder restarts at each loop) -> 24 s ->
resample_poly to 44.1 kHz -> equal 100-3500 Hz band rms as audition set A (A_fullband.wav)."""
import json, os, random, sys, time, wave
import numpy as np
from scipy import signal
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..')); sys.path.insert(0, os.path.join(ROOT, 'tools'))
import brownnoise as bn, adpcm, nsenc
OUT = os.path.join(HERE, 'audition2')
PEAK, SEED, HP, FS, SECS = 0.985, 63, 20.0, 44100, 24
CONFIGS = [(16000, 58968), (16000, 95660), (24000, 95660), (24000, 60100), (32000, 95660), (44100, 95660), (44100, 60100)]

def tag(rate, nb):
    r = ('%gk' % (rate / 1000.0))
    return 'LOOP_%s_%dB' % (r, nb)

def pcm_for(rate, nbytes):
    n = 2 * nbytes
    rnd = random.Random(SEED)
    w = np.array([rnd.gauss(0.0, 1.0) for _ in range(n)])
    f = np.fft.rfftfreq(n, 1.0 / rate); fm = f[1:]
    h = np.zeros_like(f); h[1:] = 1.0 / fm * (1.0 / np.sqrt(1.0 + (HP / fm) ** 4))
    x = np.fft.irfft(np.fft.rfft(w) * h, n)
    x = (x / np.abs(x).max()).tolist()
    x = bn.restart_rotation(x, PEAK, 12, fs=rate)
    return bn.to_pcm16(x, PEAK)

def prof(pass_hz, oob_db, tw):
    return lambda f: 0.0 if f < pass_hz else (oob_db if f > pass_hz + tw else oob_db * (f - pass_hz) / tw)

def do_encode(rate, nb):
    t0 = time.time()
    pcm = pcm_for(rate, nb)
    ph, tw = 0.33 * rate, 0.044 * rate
    W = nsenc.design_w(rate, prof(ph, 24.0, tw), order=8)
    best = None
    for tl, tg in [(0, 0.0), (600, 4.0), (1500, 10.0), (3000, 40.0)]:
        d = nsenc.encode_ns(pcm, W=W, beam=32, tail=tl, tail_gain=tg)[0]
        dd = adpcm.decode(d); sm = abs(dd[0] - dd[-1])
        if best is None or sm < best[0]:
            best = (sm, d, (tl, tg))
    data = best[1]; assert len(data) == nb
    name = tag(rate, nb); os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, name + '.adpcm'), 'wb').write(data)
    dec = np.array(adpcm.decode(data), dtype=float); ref = np.array(pcm, dtype=float)
    m = {'rate': rate, 'bytes': nb, 'loop_s': 2 * nb / rate, 'pass_hz': ph, 'boost_db': 24.0, 'tail_variant': best[2],
         'first4': data[:4].hex(), 'snr_db': float(10 * np.log10(np.sum(ref ** 2) / np.sum((dec - ref) ** 2))),
         'clipped': int(np.sum((dec >= 32767) | (dec <= -32768))), 'seam_step': float(abs(dec[0] - dec[-1])),
         'p99_step': float(np.percentile(np.abs(np.diff(dec)), 99)), 'rms_dbfs': float(10 * np.log10(np.mean(dec ** 2) / 32768 ** 2)),
         'encode_s': time.time() - t0}
    json.dump(m, open(os.path.join(OUT, name + '.json'), 'w'), indent=1)
    np.save(os.path.join(OUT, name + '_ref.npy'), ref.astype(np.int16))
    print(name, json.dumps(m)); sys.stdout.flush()

def rd(p):
    w = wave.open(p); return np.frombuffer(w.readframes(w.getnframes()), '<i2').astype(float)

def bandrms(y, lo=100, hi=3500):
    Y = np.fft.rfft(y); f = np.fft.rfftfreq(len(y), 1.0 / FS); m = (f >= lo) & (f < hi)
    return np.sqrt(np.sum(np.abs(Y[m]) ** 2)) / len(y)

def third_levels(y, centres):
    f, P = signal.welch(y, FS, nperseg=16384)
    return np.array([P[(f >= c / 2 ** (1 / 6)) & (f < c * 2 ** (1 / 6))].sum() for c in centres])

def env_ac(y, lag_s):
    sos = signal.butter(4, [1000, 3000], 'bandpass', fs=FS, output='sos')
    e = np.abs(signal.hilbert(signal.sosfiltfilt(sos, y)))
    e = signal.sosfiltfilt(signal.butter(2, 8, 'low', fs=FS, output='sos'), e)     # ~125 ms smoothing
    e = e[::221]; r = FS / 221.0                                                   # 200 Hz
    e = e - e.mean(); n = len(e)
    F = np.fft.rfft(e, 2 * n); ac = np.fft.irfft(np.abs(F) ** 2)[:n]
    ac = ac / (n - np.arange(n)) ; ac = ac / ac[0]                                 # unbiased, normalised
    n = n // 2; ac = ac[:n]                                                        # lags up to half the record only (>= 12 s overlap)
    k = int(round(lag_s * r)); pk = ac[max(0, k - 2):k + 3].max()
    mask = np.ones(n, bool)
    for j in range(0, n, max(1, int(round(lag_s * r)))):
        mask[max(0, j - int(0.3 * r)):j + int(0.3 * r) + 1] = False
    mask[:int(0.5 * r)] = False
    bg = ac[mask]
    return float(pk), float(np.sqrt(np.mean(bg ** 2))), float(np.max(np.abs(bg))), float(e.std() / max(1e-9, np.mean(np.abs(e)) + 1e-9))

def seam_excess(y, lag_s, nseam):
    hp = signal.sosfiltfilt(signal.butter(4, 1000, 'high', fs=FS, output='sos'), y)
    w = int(0.003 * FS); a = np.abs(hp)
    def wmax(c): return a[max(0, c - w):c + w].max()
    seams = [wmax(int(round(k * lag_s * FS))) for k in range(1, nseam + 1) if int(round(k * lag_s * FS)) + w < len(y)]
    rng = np.random.default_rng(5); rnd = [wmax(int(c)) for c in rng.integers(w, len(y) - w, 400)]
    rng2 = np.random.default_rng(6); rnd = np.array([wmax(int(c)) for c in rng2.integers(w, len(y) - w, 3000)])
    pct = lambda v: float(100.0 * np.mean(rnd <= v))
    return pct(np.max(seams)), pct(np.median(seams))

def do_render(aref):
    import firresp
    A = rd(aref) / 32768.0; ref_band = bandrms(A)
    cent = [1000 * 2 ** (k / 3.0) for k in range(-10, 14)]
    cent = [c for c in cent if c < 21000]
    PA = third_levels(A, cent)
    # control: envelope AC of A itself at each loop lag (A is 16 s, so lags <= 8 s only)
    xs = np.linspace(0.2, 0.5, 301); fr = 20 * np.log10(firresp.resp(xs)); xdev = float(np.interp(-3.0, fr[::-1], xs[::-1]))
    res = {}
    for rate, nb in CONFIGS:
        name = tag(rate, nb)
        data = open(os.path.join(OUT, name + '.adpcm'), 'rb').read()
        dec = np.array(adpcm.decode(data), dtype=float) / 32768.0
        ref = np.load(os.path.join(OUT, name + '_ref.npy')).astype(float) / 32768.0
        N = len(dec); L = N / rate
        reps = int(np.ceil((SECS + 1) * rate / N))
        tiled = np.tile(dec, reps)
        y = tiled if rate == FS else signal.resample_poly(tiled, FS, rate)
        y = y[:FS * SECS]
        y = y * (ref_band / bandrms(y))
        pcm = np.round(np.clip(y, -1, 32767 / 32768) * 32767).astype(np.int16)
        pk = int(np.abs(pcm.astype(int)).max())
        wv = wave.open(os.path.join(OUT, name + '.wav'), 'wb'); wv.setnchannels(1); wv.setsampwidth(2); wv.setframerate(FS); wv.writeframes(pcm.tobytes()); wv.close()
        yq = pcm.astype(float) / 32768.0
        # bandwidth: third-octave level re A, first centre above 1 kHz where it is below -3 dB (linear interpolation)
        PY = third_levels(yq, cent); rel = 10 * np.log10(PY / PA)
        bw = None
        for i in range(1, len(cent)):
            if cent[i] > 1000 and rel[i] < -3.0 <= rel[i - 1]:
                bw = float(cent[i - 1] + (cent[i] - cent[i - 1]) * (rel[i - 1] + 3.0) / (rel[i - 1] - rel[i])); break
        # NSR per octave at the stream rate (exact periodic lines)
        Xr = np.fft.rfft(ref); Xe = np.fft.rfft(dec - ref); f = np.fft.rfftfreq(N, 1.0 / rate)
        nsr = {}; lo = 31.25
        while lo < rate / 2:
            hi = min(lo * 2, rate / 2 + 1)
            m = (f >= lo) & (f < hi)
            if m.sum() >= 3:
                nsr['%g-%g' % (lo, min(hi, round(rate / 2)))] = float(10 * np.log10(np.sum(np.abs(Xe[m]) ** 2) / np.sum(np.abs(Xr[m]) ** 2)))
            lo *= 2
        pkac, bgrms, bgmax, _ = env_ac(yq, L)
        sx_max, sx_med = seam_excess(yq, L, int(SECS // L))
        # control: envelope AC of independent noise (set A) at the same lag, when A is long enough
        ctrl = None
        if L < 7.5:
            ctrl = float(env_ac(A, L)[0])
        res[name] = {'rate': rate, 'bytes': nb, 'samples': N, 'loop_s': L, 'repeats_in_24s': SECS / L, 'bw_minus3dB_hz': bw,
                     'bw_device_fir_minus3dB_hz': xdev * rate, 'nsr_octave_db': nsr, 'env_ac_at_loop_lag': pkac, 'env_ac_background_rms': bgrms,
                     'env_ac_background_max': bgmax, 'env_ac_control_independent_noise': ctrl, 'seam_pct_max': sx_max, 'seam_pct_median': sx_med,
                     'peak_int16': pk, 'rms_dbfs': float(10 * np.log10(np.mean(yq ** 2))),
                     'third_oct_re_A_db': {('%d' % c): float(r) for c, r in zip(cent, rel) if c >= 1000}}
        print(name, json.dumps({k: v for k, v in res[name].items() if k != 'third_oct_re_A_db'})); sys.stdout.flush()
    json.dump(res, open(os.path.join(OUT, 'loop_measures.json'), 'w'), indent=1)

if __name__ == '__main__':
    if sys.argv[1] == 'encode':
        do_encode(int(sys.argv[2]), int(sys.argv[3]))
    else:
        do_render(sys.argv[2])
