"""HX3: the 48 kHz compensated payload with a LOW-FREQUENCY-AWARE loop join (offline).
Same recipe as mk48_head.py (bell +11 dB at 90 Hz, dip -4 dB at 2.2 kHz, +3 dB tanh limiter knee 0.55, peak 0.985, seed 63, beam noise shaper) but the circular
signal is rotated so that the wrap point is where a time slip of the join (the 3-16 ms gap the DSP covers with held or stale samples) costs least in the bass:
for each eligible start k (a zero crossing, level within 1.5 dB before and after) the metric is the rms, over slips g = 3, 6, 9, 12 ms, of LP(x)[k+g] - LP(x)[k]
(LP = 25-300 Hz band of the circular signal) plus the same for the full band at a smaller weight; the best candidates (also subject to the decoder-onset
criteria of tools/brownnoise.restart_rotation) are encoded in full and scored by the decoded seam step as before. Also a head offset so the first four bytes cost
at most 5 compare words (a byte < 0x80 costs 1, >= 0x80 costs 2; the product's layout does not converge with more).
Usage: python -I mk48_lf.py RATE [NBYTES]  -> build/payload/g8/brown_<RATE>_<NBYTES>_lf.adpcm (+ .json) ; prints the modelled join click against the shipped g7 payload."""
import sys, os, json, time, hashlib, random, math, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, '..', 'bu-coverage'))
import mkcomp as mc
ml = mc.ml; adpcm, nsenc, bn = ml.adpcm, ml.nsenc, ml.bn
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
rate = int(sys.argv[1]); nb = int(sys.argv[2]) if len(sys.argv) > 2 else 58968
B, C, G, K = 11.0, -4.0, 3.0, 0.55
n = 2 * nb
SLIPS_MS = (3, 6, 9, 12)

def circ_signal():
    rnd = random.Random(ml.SEED)
    w = np.array([rnd.gauss(0.0, 1.0) for _ in range(n)])
    f = np.fft.rfftfreq(n, 1.0 / rate); fm = f[1:]
    h = np.zeros_like(f); h[1:] = 1.0 / fm * (1.0 / np.sqrt(1.0 + (ml.HP / fm) ** 4)); h[1:] *= 10 ** (mc.eq_db(fm, B, C) / 20.0)
    x = np.fft.irfft(np.fft.rfft(w) * h, n); x = x / np.abs(x).max()
    return np.array(mc.limit(x.tolist(), G, K))

def bandpass(x, lo, hi):
    X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1.0 / rate)
    X[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(X, len(x))

DIP_DB, DIP_HALF_MS = float(os.environ.get('DIP_DB', '-10')), float(os.environ.get('DIP_HALF_MS', '40'))
def apply_dip(sig, k):
    """Scale ONLY the 25-300 Hz band by a raised-cosine bump of depth DIP_DB and half-width DIP_HALF_MS centred on the wrap k (circular): a smooth bass calm around the join."""
    nn = len(sig); lf = bandpass(sig, 25, 300)
    d = np.arange(nn) - k; d = (d + nn // 2) % nn - nn // 2
    H = DIP_HALF_MS * rate / 1000.0
    w = np.where(np.abs(d) <= H, 0.5 * (1 + np.cos(np.pi * d / H)), 0.0)
    g = 10 ** (DIP_DB / 20.0)
    return sig - (1 - g) * w * lf

def win_metric(sig, k_all, before_ms=10, after_ms=25):
    """rms of `sig` over the window [k - before, k + after) around each candidate wrap k (circular), the region the join hole (about 10 ms) and its neighbours occupy."""
    nn = len(sig); wb = int(before_ms * rate / 1000.0); wa = int(after_ms * rate / 1000.0)
    c = np.concatenate([[0.0], np.cumsum(np.concatenate([sig * sig] * 3))])
    k3 = k_all + nn
    return np.sqrt((c[k3 + wa] - c[k3 - wb]) / (wa + wb))

def choose_rotation(x):
    a = np.asarray(x); sig = float(a.std())
    w = max(64, min(int(0.1 * rate), n // 8))
    e = np.concatenate([a * a] * 3); cs = np.concatenate([[0.0], np.cumsum(e)])
    idx = np.arange(n) + n
    before = (cs[idx] - cs[idx - w]) / w; after = (cs[idx + w] - cs[idx]) / w
    g0 = float(np.mean(a * a))
    dev = np.maximum(np.abs(10 * np.log10(before / g0 + 1e-12)), np.abs(10 * np.log10(after / g0 + 1e-12)))
    elig = np.where(np.abs(a) <= 0.05 * sig)[0]
    ok = elig[dev[elig] <= 3.0]
    lf = bandpass(a, 25, 300); fb = a
    m_lf = win_metric(lf, ok) / lf.std(); m_fb = win_metric(fb, ok) / sig
    metric = m_lf + 0.15 * m_fb
    head = 256
    def onset(k):
        seg = a[(np.arange(head) + k) % n]
        pcm = bn.to_pcm16(seg.tolist(), ml.PEAK)
        dec = adpcm.decode(adpcm.encode(pcm))
        err = np.asarray(dec[:32], float) - np.asarray(pcm[:32], float)
        return math.sqrt(float(np.mean(err ** 2)))
    order = np.argsort(metric)
    picks = []
    for j in order[:400]:
        k = int(ok[j])
        if all(min(abs(k - q), n - abs(k - q)) >= 400 for q, _ in picks):
            picks.append((k, float(metric[j])))
        if len(picks) >= 12: break
    best = None
    ranked = []
    ons = {k: onset(k) for k, _ in picks}
    omin = min(ons.values())
    for k, mval in picks:
        pcm = bn.to_pcm16(np.roll(a, -k).tolist(), ml.PEAK)
        dec = adpcm.decode(adpcm.encode(pcm)); seam = abs(dec[0] - dec[-1])
        winv = max(abs(dec[j + 1] - dec[j]) for j in list(range(0, 16)) + list(range(n - 17, n - 1)))
        sc = mval * 1000.0 + 0.5 * (seam + winv) + 2.0 * ons[k] + 30.0 * float(dev[k])
        ranked.append((sc, k, mval, ons[k], float(dev[k]), seam))
        if best is None or sc < best[0]: best = (sc, k, mval, ons[k], float(dev[k]), seam)
    ranked.sort()
    # the metric of the whole population for comparison
    return a, ranked, dict(pop_median=float(np.median(metric)), pop_min=float(metric.min()))

def join_click(pcm, gap_ms, mode):
    """Model of the join: decoded payload tiled with a gap of gap_ms filled by 'hold' (the last sample repeated) or 'zero'; returns the rms of the low-passed (<300 Hz) and full-band first difference-free residual
    x_model - x_ideal around the join, where x_ideal is the circular continuation (what the signal would have been with no gap)."""
    dec = np.array(adpcm.decode(adpcm.encode(pcm)), float) if False else np.array(pcm, float)
    N = len(dec); gs = int(round(gap_ms * rate / 1000.0))
    ideal = np.concatenate([dec, dec, dec])
    fill = np.full(gs, dec[-1] if mode == 'hold' else 0.0)
    model = np.concatenate([dec, fill, dec, fill, dec])
    # ideal continuation including the gap duration as if the signal were periodic with period N + gs: not available; compare to the signal with the gap removed (time-slipped), i.e. the error is the slip
    # residual = model(t) - ideal(t) for t in the second chunk, ideal(t) = dec[(t - gs) mod N]... the slip: the second chunk starts gs samples late relative to a period-N repeat
    seg = np.arange(N + gs, N + gs + int(0.1 * rate))     # 100 ms after the join
    res = model[seg] - ideal[seg - gs]
    return float(np.sqrt(np.mean(res ** 2)))

def choose_local(x, centres, win_ms=4.0):
    """For each dip centre c: apply the bass dip centred on c, then pick the wrap k within +-win_ms of c at a zero crossing of the DIPPED signal with the best decoder onset and seam (the same criteria as tools/brownnoise.restart_rotation, local). Returns (best dict, dipped signal)."""
    best = None
    wn = int(win_ms * rate / 1000.0)
    for c in centres:
        xd = apply_dip(x, c) if DIP_DB < 0 else x
        sig = float(xd.std())
        ks = [(c + j) % n for j in range(-wn, wn + 1)]
        el = [k for k in ks if abs(xd[k]) <= 0.05 * sig]
        for k in el:
            seg = xd[(np.arange(256) + k) % n]
            pcm_h = bn.to_pcm16(seg.tolist(), ml.PEAK)
            dec_h = adpcm.decode(adpcm.encode(pcm_h))
            ons = math.sqrt(float(np.mean((np.asarray(dec_h[:32], float) - np.asarray(pcm_h[:32], float)) ** 2)))
            pcm_f = bn.to_pcm16(np.roll(xd, -k).tolist(), ml.PEAK)
            dec = adpcm.decode(adpcm.encode(pcm_f)); seam = abs(dec[0] - dec[-1])
            winv = max(abs(dec[j + 1] - dec[j]) for j in list(range(0, 16)) + list(range(n - 17, n - 1)))
            sc = seam + winv + 2.0 * ons
            if best is None or sc < best[0]: best = (sc, k, c, ons, seam, winv, xd)
    return best

def cost(b4): return sum(1 if b < 0x80 else 2 for b in b4)
def ok4(b4): return cost(b4) <= 5 and b4[0] != b4[1] and b4[2] != b4[3]

if __name__ == '__main__':
    t0 = time.time()
    x = circ_signal()
    if os.environ.get('ROT', 'lf') == 'local':
        a0, ranked0, popinfo0 = choose_rotation(x)
        centres = [k for sc_, k, *_ in ranked0[:6]]
        bl = choose_local(x, centres)
        sc_, k_, c_, ons_, seam_, winv_, xd_ = bl
        print('local wrap: centre %d wrap %d score %.0f onset %.0f seam %.0f edge step %.0f' % (c_, k_, sc_, ons_, seam_, winv_)); sys.stdout.flush()
        a_sig = xd_; DIP_DB = 0.0      # the dip is already applied: do not apply it again in the candidate loop
        ranked = [(sc_, k_, 0.0, ons_, 0.0, seam_)]
        popinfo = {'rotation': 'local', 'centre': c_}
    elif os.environ.get('ROT', 'lf') == 'orig':
        # the original wrap choice of tools/brownnoise.restart_rotation (zero crossing, level match, best decoder tracking and seam), then only the bass calm is added around it
        r0 = np.array(bn.restart_rotation(x.tolist(), ml.PEAK, 12, fs=rate))
        k0 = int(np.argmin(np.abs(x - r0[0])))
        assert np.allclose(np.roll(x, -k0)[:64], r0[:64]), 'could not locate the original wrap'
        a_sig = x
        ranked = [(0.0, k0, 0.0, 0.0, 0.0, 0.0)]
        popinfo = {'rotation': 'orig', 'k0': k0}
    else:
        a_sig, ranked, popinfo = choose_rotation(x)
    ph, tw = 0.33 * rate, 0.044 * rate
    W = nsenc.design_w(rate, ml.prof(ph, 24.0, tw), order=8)
    found = None; info = None
    for sc, k, mval, ons_k, dev_k, seam_k in ranked:
        a_mod = apply_dip(a_sig, k) if DIP_DB < 0 else a_sig
        rot = np.roll(a_mod, -k)
        pcm0 = bn.to_pcm16(rot.tolist(), ml.PEAK)
        rnd = random.Random(5)
        for trial in range(120):
            off = [rnd.choice([-1, 1]) * rnd.randint(0, 150) for _ in range(8)]
            p = list(pcm0[:1024])
            for i, o in enumerate(off): p[i] = max(-32768, min(32767, p[i] + o))
            d = nsenc.encode_ns(p, W=W, beam=32, tail=0, tail_gain=0.0)[0]
            if ok4(d[:4]): found = off; break
        print('candidate k=%d metric %.3f onset %.0f seam %.0f dev %.2f dB score %.0f -> %s' % (k, mval, ons_k, seam_k, dev_k, sc, 'head offset found' if found else 'no head offset')); sys.stdout.flush()
        if found:
            info = dict(k=k, metric=mval, onset=ons_k, dev_db=dev_k, seam=seam_k, **popinfo); break
    assert found, 'no candidate rotation admits a cheap head'
    print('rotation', json.dumps(info))
    pcm = list(pcm0)
    for i, o in enumerate(found): pcm[i] = max(-32768, min(32767, pcm[i] + o))
    best = None
    VARS = [(0, 0.0), (300, 2.0), (600, 4.0), (900, 6.0), (1500, 10.0), (2200, 20.0), (3000, 40.0), (4000, 80.0), (6000, 160.0), (800, 3.0), (1200, 8.0), (2000, 14.0)]
    for tl, tg in VARS:
        d = nsenc.encode_ns(pcm, W=W, beam=32, tail=tl, tail_gain=tg)[0]
        dd = adpcm.decode(d); sm = abs(dd[0] - dd[-1]) + 0.5 * (abs(dd[0]) + abs(dd[-1]))     # the join steps: hold fill sees |first - last|, zero fill sees |first| and |last|
        if best is None or sm < best[0]: best = (sm, d, (tl, tg))
    data = best[1]; assert len(data) == nb and ok4(data[:4]), data[:4].hex()
    out = os.path.join(ROOT, 'build', 'payload', 'g8'); os.makedirs(out, exist_ok=True)
    name = 'brown_%d_%d_lf%s%s' % (rate, nb, ('d%g' % -float(os.environ.get('DIP_DB', '-10'))) if float(os.environ.get('DIP_DB', '-10')) < 0 else '', {'orig': 'o', 'local': 'L'}.get(os.environ.get('ROT', 'lf'), ''))
    open(os.path.join(out, name + '.adpcm'), 'wb').write(data)
    dec = np.array(adpcm.decode(data), float)
    g7 = os.path.join(ROOT, 'build', 'payload', 'g7', 'brown_%d_%d_comp.adpcm' % (rate, nb))
    if not os.path.exists(g7):      # public export: the payload file above is already written; the comparison with the older g7 payload is skipped
        print(json.dumps({'sha256': hashlib.sha256(data).hexdigest(), 'file': name + '.adpcm'})); sys.exit(0)
    old = np.array(adpcm.decode(open(os.path.join(ROOT, 'build', 'payload', 'g7', 'brown_%d_%d_comp.adpcm' % (rate, nb)), 'rb').read()), float)
    def lfwin(d):
        lf = bandpass(d, 25, 300); nn = len(d); wb = int(0.010 * rate); wa = int(0.025 * rate)
        seg = np.concatenate([lf[-wb:], lf[:wa]])
        return float(np.sqrt(np.mean(seg ** 2))), float(lf.std())
    (lo, ls), (ln, ln_s) = lfwin(old), lfwin(dec)
    print('LF (25-300 Hz) rms in the 35 ms around the wrap [-10, +25 ms]: old payload %.0f (%.2f of the loop LF rms), new payload %.0f (%.2f): %.1f dB' % (lo, lo / ls, ln, ln / ln_s, 20 * np.log10(ln / lo)))
    clicks_old, clicks_new = lo, ln
    m = {'rate': rate, 'bytes': nb, 'loop_s': 2 * nb / rate, 'rotation': info, 'head_offset': found, 'tail_variant': best[2], 'first4': data[:4].hex(), 'first4_cost': cost(data[:4]),
         'sha256': hashlib.sha256(data).hexdigest(), 'md5': hashlib.md5(data).hexdigest(), 'clipped': int(np.sum((dec >= 32767) | (dec <= -32768))), 'seam_step': float(abs(dec[0] - dec[-1])),
         'rms_dbfs': float(10 * np.log10(np.mean(dec ** 2) / 32768 ** 2)), 'peak': float(np.abs(dec).max()), 'lf_wrap_rms_old': clicks_old, 'lf_wrap_rms_new': clicks_new, 'encode_s': time.time() - t0}
    json.dump(m, open(os.path.join(out, name + '.json'), 'w'), indent=1)
    print(json.dumps(m, indent=1))
