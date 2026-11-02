"""BU: noise-shaped (beam / trellis) IMA ADPCM encoder against the TRUE decoder of tools/adpcm.py.

The decoder is fixed (TransformAdpcmDecode = CWI/IMA, high nibble first, state (0,0)); only the code
sequence is free. The ADK/CWI encoder picks, per sample, the code whose decoded value is closest to the
input (white error). Here the code sequence is chosen by a beam search that minimises the energy of the
WEIGHTED error  w[n] = e[n] - a*e[n-1]  (e = decoded - input). Minimising sum w^2 puts the error spectrum
at 1/|1 - a z^-1|^2 : a = 0 is the CWI white error, a -> 1 is a brown-shaped error (constant SNR across
frequency, like the signal), values between trade LF error against HF error.

Offline only. Usage as a module: encode_ns(pcm_int, a, beam) -> (bytes, nibbles).
"""
import os
import sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..', '..', '..', 'tools')))
import adpcm  # noqa: E402

STEP = np.array(adpcm.STEP, dtype=np.int64)
# signed reconstruction difference and next index, [index, code]
DT = np.zeros((89, 16), dtype=np.int64)
NI = np.zeros((89, 16), dtype=np.int64)
for _i in range(89):
    for _c in range(16):
        s = int(STEP[_i])
        d = s >> 3
        if _c & 4:
            d += s
        if _c & 2:
            d += s >> 1
        if _c & 1:
            d += s >> 2
        DT[_i, _c] = -d if _c & 8 else d
        NI[_i, _c] = min(88, max(0, _i + adpcm.INDEX_DELTA[_c]))


def encode_ns(x, a=0.9, beam=32, a2=0.0, W=None, tail=0, tail_gain=4.0):
    """x: int array (target samples). Weighted error w = e - a*e1 - a2*e2, or, when W is given,
    w = sum_k W[k] * e[n-k] (W[0] = 1, any order). Returns (bytes, codes)."""
    if W is not None:
        return _encode_w(x, np.asarray(W, dtype=float), beam, tail, tail_gain)
    x = np.asarray(x, dtype=np.int64)
    n_samp = len(x)
    B = beam
    vp = np.zeros(1, dtype=np.int64)
    ix = np.zeros(1, dtype=np.int64)
    cost = np.zeros(1)
    e1 = np.zeros(1)
    e2 = np.zeros(1)
    par = np.zeros((n_samp, B), dtype=np.int32)
    cod = np.zeros((n_samp, B), dtype=np.uint8)
    codes16 = np.arange(16)
    for n in range(n_samp):
        nvp = np.clip(vp[:, None] + DT[ix], -32768, 32767)            # (b,16)
        e = nvp - x[n]
        w = e - a * e1[:, None] - a2 * e2[:, None]
        nc = cost[:, None] + w * w
        flat = nc.ravel()
        k = min(len(flat), 3 * B)
        if len(flat) > k:
            sel = np.argpartition(flat, k - 1)[:k]
        else:
            sel = np.arange(len(flat))
        sel = sel[np.argsort(flat[sel])]
        pi = sel // 16
        ci = sel % 16
        nvp_s = nvp.ravel()[sel]
        nix_s = NI[ix[pi], ci]
        key = nvp_s * 128 + nix_s
        _, first = np.unique(key, return_index=True)
        first.sort()
        first = first[:B]
        pi = pi[first]
        ci = ci[first]
        m = len(first)
        par[n, :m] = pi
        cod[n, :m] = ci
        e2 = e1[pi]
        e1 = e.ravel()[sel[first]].astype(float)
        cost = flat[sel[first]]
        vp = nvp_s[first]
        ix = nix_s[first]
    best = int(np.argmin(cost))
    out = np.zeros(n_samp, dtype=np.uint8)
    b = best
    for n in range(n_samp - 1, -1, -1):
        out[n] = cod[n, b]
        b = par[n, b]
    return adpcm.pack([int(c) for c in out]), out


def _encode_w(x, W, beam, tail=0, tail_gain=4.0):
    x = np.asarray(x, dtype=np.int64)
    n_samp = len(x)
    B = beam
    P = len(W) - 1
    vp = np.zeros(1, dtype=np.int64)
    ix = np.zeros(1, dtype=np.int64)
    cost = np.zeros(1)
    eh = np.zeros((1, max(P, 1)))          # eh[:, k-1] = e[n-k]
    par = np.zeros((n_samp, B), dtype=np.int32)
    cod = np.zeros((n_samp, B), dtype=np.uint8)
    Wh = W[1:]
    for n in range(n_samp):
        nvp = np.clip(vp[:, None] + DT[ix], -32768, 32767)            # (b,16)
        e = nvp - x[n]
        hist = (eh[:, :P] @ Wh) if P else np.zeros(len(vp))           # (b,)
        w = e * W[0] + hist[:, None]
        gn = 1.0 if (not tail or n < n_samp - tail) else 1.0 + (tail_gain - 1.0) * ((n - (n_samp - tail)) / tail) ** 2
        te = 0.0 if (not tail or n < n_samp - tail) else tail_gain * ((n - (n_samp - tail)) / tail) ** 2
        nc = cost[:, None] + gn * w * w + te * e * e
        flat = nc.ravel()
        k = min(len(flat), 3 * B)
        sel = np.argpartition(flat, k - 1)[:k] if len(flat) > k else np.arange(len(flat))
        sel = sel[np.argsort(flat[sel])]
        pi = sel // 16
        ci = sel % 16
        nvp_s = nvp.ravel()[sel]
        nix_s = NI[ix[pi], ci]
        key = nvp_s * 128 + nix_s
        _, first = np.unique(key, return_index=True)
        first.sort()
        first = first[:B]
        pi = pi[first]
        ci = ci[first]
        m = len(first)
        par[n, :m] = pi
        cod[n, :m] = ci
        newe = e.ravel()[sel[first]].astype(float)
        if P:
            eh = np.concatenate([newe[:, None], eh[pi][:, :P - 1]], axis=1)
        cost = flat[sel[first]]
        vp = nvp_s[first]
        ix = nix_s[first]
    best = int(np.argmin(cost))
    out = np.zeros(n_samp, dtype=np.uint8)
    b = best
    for n in range(n_samp - 1, -1, -1):
        out[n] = cod[n, b]
        b = par[n, b]
    return adpcm.pack([int(c) for c in out]), out


def design_w(rate, nsr_db, order=8, f0=20.0):
    """Weighting FIR W (W[0]=1) whose inverse has the noise PSD  N(f) = S(f) * 10^(nsr_db(f)/10),
    S(f) = 1/(f^2+f0^2) (brown). nsr_db: callable f_hz -> dB (negative). LPC (Levinson) of N(f)."""
    nf = 8192
    f = np.linspace(0, rate / 2, nf + 1)
    Nf = (1.0 / (f ** 2 + f0 ** 2)) * 10 ** (np.array([nsr_db(v) for v in f]) / 10.0)
    r = np.fft.irfft(Nf)[:order + 1]                                  # autocorrelation of the target noise
    # Levinson-Durbin
    a = np.zeros(order + 1)
    a[0] = 1.0
    err = r[0]
    for i in range(1, order + 1):
        acc = r[i] + np.dot(a[1:i], r[i - 1:0:-1])
        k = -acc / err
        a[1:i + 1] = a[1:i + 1] + k * np.concatenate([a[i - 1:0:-1], [1.0]])
        err *= (1 - k * k)
    return a


def cwi(x):
    return adpcm.encode([int(v) for v in x])


if __name__ == '__main__':
    rng = np.random.default_rng(1)
    t = np.cumsum(rng.normal(0, 300, 4000)).clip(-20000, 20000).astype(np.int64)
    b0 = cwi(t)
    b1, c1 = encode_ns(t, a=0.0, beam=1)
    print('beam=1 a=0 equals CWI:', b0 == b1)
    dec = np.array(adpcm.decode(b1))
    print('decoder reproduces beam path, rms err', np.sqrt(np.mean((dec - t) ** 2)))
