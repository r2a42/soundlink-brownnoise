#!/usr/bin/env python3
"""click_detect: gain-independent glitch finder for a laptop-microphone recording of the looped brown noise.

Why a new detector (field-log 2026-10-27): the microphone chain changes level between sessions (a session that starts in
silence reads 5x louder than one that starts with the noise running), and the earlier z-score "jerk" detector fired on
phase-locked artefacts of the low-gain sessions. This tool aligns every loop to the known payload (a straight line through the
lags of 0.3 s windows gives each loop's start and time scale), builds the EMPIRICAL template of the same recording (the median of
all loops, so the speaker, the room and the capture chain are part of the template) and reports, per loop:
  SEAM    next loop start minus this loop's end (ms): the rebuild gap or overlap, every loop
  STEP    a persistent timeline step inside a loop (stream time inserted or dropped: a replay or an underrun), size in ms
  BURST   extra high-frequency energy at a phase where the other loops are quiet (a click), strength in sigmas
Usage:  python -I tools/click_detect.py rec.wav [--payload FILE.adpcm] [--skip SECONDS] [--json out.json]
Method rule: start every recording in SILENCE and start the noise during the recording (tools/csr/virtual_press.py), so the
capture gain is in its high state; do not compare counts between sessions of the two kinds. Use --skip to ignore the stock
prompts at the start. Needs numpy and scipy; the recording must be 16 kHz mono (tools/mic_rec.ps1)."""
import argparse
import json
import os
import wave

import numpy as np
from scipy.signal import butter, resample_poly, sosfiltfilt

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PAYLOAD = os.path.join(HERE, "..", "build", "payload", "g9", "brown_48000_58968_periodic96.adpcm")
NOMINAL = 117936 / 48000.0          # seconds per loop of the 48 kHz payload (analyse() uses len(payload) / rate)

_ST = [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
       130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166,
       1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845,
       8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767]
_IX = [-1, -1, -1, -1, 2, 4, 6, 8]


def decode_adpcm(path):
    p = 0
    i = 0
    out = []
    for b in open(path, "rb").read():
        for n in (b >> 4, b & 15):
            s = _ST[i]
            df = s >> 3
            if n & 1:
                df += s >> 2
            if n & 2:
                df += s >> 1
            if n & 4:
                df += s
            p = max(-32768, min(32767, p - df if n & 8 else p + df))
            i = max(0, min(88, i + _IX[n & 7]))
            out.append(p)
    return np.array(out, float)


def load(path):
    w = wave.open(path)
    fs = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(float)
    return fs, x


def _xc(a, b):
    """Lag (samples, sub-sample) of b inside a (len(a) >= len(b)) and the normalised peak."""
    n = len(a) + len(b)
    c = np.fft.irfft(np.fft.rfft(a, n) * np.conj(np.fft.rfft(b, n)), n)[:len(a) - len(b) + 1]
    m = int(np.argmax(c))
    e = np.sqrt(np.convolve(a * a, np.ones(len(b)), "valid")[m] * np.dot(b, b)) + 1e-9
    d = 0.0
    if 0 < m < len(c) - 1:
        y0, y1, y2 = c[m - 1], c[m], c[m + 1]
        d = 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2 + 1e-12)
    return m + d, c[m] / e


def analyse(path, payload=DEFAULT_PAYLOAD, skip=0.0, verbose=True, debug=False, preemph=False, rate=48000):
    fs, x = load(path)
    x = x[int(skip * fs):]
    if fs != 16000:
        raise SystemExit("expected a 16 kHz recording (tools/mic_rec.ps1)")
    pay48 = decode_adpcm(payload)
    if preemph:                                                 # validation signals are differentiated so that a laptop loudspeaker can play them
        pay48 = np.diff(pay48, prepend=pay48[-1])
    pay = resample_poly(pay48, 1, rate // 16000) if rate % 16000 == 0 else resample_poly(pay48, 16000 // np.gcd(16000, rate), rate // np.gcd(16000, rate))      # 16 kHz, one loop (the payload played at RATE)
    nominal = len(pay48) / float(rate)
    L = len(pay)
    band = butter(4, [120, 2500], "band", fs=fs, output="sos")
    xb = sosfiltfilt(band, x)
    pb = sosfiltfilt(band, pay)
    # 1. coarse loop period (the laptop-time length of one loop) and offset by folding
    best = None
    for P in np.arange(nominal * 0.9932, nominal * 1.0094, nominal * 0.00004):
        N = int(round(P * fs))
        k = len(xb) // N
        if k < 3:
            continue
        fo = xb[:k * N].reshape(k, N).mean(0)
        pp = np.interp(np.arange(N), np.arange(L) * N / L, pb)
        c = np.fft.irfft(np.fft.rfft(fo) * np.conj(np.fft.rfft(pp)))
        m = int(np.argmax(c))
        v = c[m] / np.sqrt((fo ** 2).sum() * (pp ** 2).sum())
        if best is None or v > best[0]:
            best = (v, P, m)
    if best is None:
        raise SystemExit("recording too short (need at least 3 loops)")
    v, P0, m0 = best
    N0 = int(round(P0 * fs))
    payS = np.interp(np.arange(N0), np.arange(L) * N0 / L, pb)        # the payload stretched to the laptop-time loop length
    # 2. per-loop alignment: lags of 0.3 s windows against the stretched payload; a straight line through them gives the loop's
    #    start (offset) and its time scale (slope); the next loop is predicted from this loop's end
    WIN0 = int(0.3 * fs)
    MARG0 = int(0.04 * fs)
    nw0 = N0 // WIN0 + 1
    wst = np.linspace(0, N0 - WIN0, nw0).astype(int)        # window starts, the last one ends at the loop end
    loops_t = []                   # (start sample, slope, quality, window-lag residuals, window correlations)
    base = float(m0)
    while base + N0 + MARG0 < len(xb):
        if base - MARG0 < 0:
            base += N0
            continue
        lags = np.full(nw0, np.nan)
        cs_ = np.zeros(nw0)
        for j in range(nw0):
            a0 = int(round(base)) + wst[j] - MARG0
            seg = xb[a0:a0 + WIN0 + 2 * MARG0]
            if len(seg) < WIN0 + 2 * MARG0:
                break
            lg, c = _xc(seg, payS[wst[j]:wst[j] + WIN0])
            lags[j] = lg - MARG0
            cs_[j] = c
        good = np.isfinite(lags) & (cs_ > 0.25)
        if good.sum() >= 5:
            jj = wst[good]
            sl = float(np.median(np.diff(lags[good]) / np.diff(jj)))
            off = float(np.median(lags[good] - sl * jj))
            res = lags - (off + sl * wst)
            start = int(round(base)) + off
            loops_t.append((start, sl, float(np.median(cs_[good])), res, cs_))
            base = start + N0 * (1 + sl)
        else:
            loops_t.append((float("nan"), 0.0, 0.0, np.full(nw0, np.nan), cs_))
            base += N0
    if len(loops_t) < 4:
        raise SystemExit("too few loops")
    st = np.array([l[0] for l in loops_t])
    sl = np.array([l[1] for l in loops_t])
    cq = np.array([l[2] for l in loops_t])
    good_l = np.isfinite(st) & (cq > 0.25)
    if good_l.sum() < 4:
        raise SystemExit("too few aligned loops (%d of %d)" % (good_l.sum(), len(st)))
    eps = float(np.median(sl[good_l]))                   # time scale: laptop samples per payload-grid sample minus 1
    gaps = []                                            # seam: next start minus this loop's end (start + stretched length)
    for i in range(len(st) - 1):
        if good_l[i] and good_l[i + 1]:
            gaps.append((st[i + 1] - (st[i] + N0 * (1 + sl[i]))) / fs * 1000.0)
    gaps = np.array(gaps)
    # 3. resample each good loop onto the payload grid with its own start and slope (first pass)
    def resample(maps):
        out = []
        for i, mp in zip(idx, maps):
            t = st[i] + np.arange(L) * (N0 / L) * (1 + sl[i]) + mp
            out.append(np.interp(t, np.arange(len(x)), x))
        return np.array(out, dtype=np.float32)
    idx = [i for i in range(len(st)) if good_l[i] and st[i] + N0 * (1 + sl[i]) + 4 < len(x)]
    K = len(idx)
    if K < 4:
        raise SystemExit("too few usable loops: %d" % K)
    loops = resample([0.0] * K)
    # 4. STEP findings: lags of 0.2 s windows of every loop against the empirical template (the median loop); a persistent change of
    #    the lag between the windows before and after a point is stream time inserted or dropped. The lags also give a piecewise-linear
    #    time warp so that the burst residual below is not polluted by a slow timing wander.
    E = np.median(loops, axis=0)
    Eb = sosfiltfilt(band, E)
    W2 = int(0.2 * fs)
    M2 = int(0.03 * fs)
    w2 = np.linspace(0, L - W2, int(L / W2) + 1).astype(int)
    lag2 = np.full((K, len(w2)), np.nan)
    cor2 = np.zeros((K, len(w2)))
    for k in range(K):
        lb = sosfiltfilt(band, loops[k])
        for j, s0 in enumerate(w2):
            a0 = max(s0 - M2, 0)
            seg = lb[a0:s0 + W2 + M2]
            if len(seg) < W2 + 2 * M2 and a0 == 0:
                continue
            lg, c = _xc(seg, Eb[s0:s0 + W2])
            lag2[k, j] = (lg - (s0 - a0)) * (N0 / L) * (1 + sl[idx[k]])
            cor2[k, j] = c
    merged = []
    for k in range(K):
        r = lag2[k]
        c = cor2[k]
        for j in range(2, len(w2) - 2):
            before, after = r[max(j - 3, 0):j], r[j + 1:j + 4]
            cb, ca = c[max(j - 3, 0):j], c[j + 1:j + 4]
            vb, va = np.isfinite(before) & (cb > 0.3), np.isfinite(after) & (ca > 0.3)
            if vb.sum() < 2 or va.sum() < 2:
                continue            # the window j itself may straddle the step and is left out on purpose; at least two good windows on each side
            before, after = before[vb], after[va]
            d = (np.median(after) - np.median(before)) / fs * 1000.0
            if abs(d) > 1.2:
                f = {"loop": k, "t_s": round(float(st[idx[k]]) / fs + w2[j] / fs + skip, 2), "phase_s": round(w2[j] / fs, 2), "step_ms": round(d, 2)}
                if merged and merged[-1]["loop"] == k and abs(f["phase_s"] - merged[-1]["phase_s"]) < 0.7:
                    if abs(f["step_ms"]) > abs(merged[-1]["step_ms"]):
                        merged[-1] = f
                else:
                    merged.append(f)
    # warp: the raw window lags interpolated to every sample (a step is followed, not smoothed away); the windows around a step are masked below
    maps = []
    cen = w2 + W2 / 2.0
    for k in range(K):
        r = lag2[k].copy()
        okw = np.isfinite(r) & (cor2[k] > 0.3)
        if okw.sum() >= 4:
            maps.append(np.interp(np.arange(L), cen[okw], r[okw]))
        else:
            maps.append(0.0)
    del loops
    loops2 = resample(maps)
    stepmask = np.zeros((K, L // int(0.002 * fs) + 1), bool)
    for f in merged:
        kk = f["loop"]
        c0 = int(f["phase_s"] * fs / int(0.002 * fs))
        stepmask[kk, max(c0 - 100, 0):c0 + 200] = True       # +-0.2 s around the window that holds the step
    # 5. BURST findings: HF residual energy per 2 ms against the same phase in the other loops (warped loops)
    E2 = np.median(loops2, axis=0)
    hp = butter(4, 800, "high", fs=fs, output="sos")
    H = np.array([sosfiltfilt(hp, l) for l in loops2], dtype=np.float32)
    del loops2
    He = sosfiltfilt(hp, E2)
    R = H                                    # the residual is formed in place (memory)
    blk = int(0.5 * fs)
    for k in range(K):
        for b in range(0, L, blk):
            e = He[b:b + blk]
            g = np.dot(H[k, b:b + blk], e) / (np.dot(e, e) + 1e-9)
            H[k, b:b + blk] -= (g * e).astype(np.float32)
    bin_ = int(0.002 * fs)
    nb = L // bin_
    en = np.sqrt((R[:, :nb * bin_].reshape(K, nb, bin_) ** 2).mean(2))
    med = np.median(en, axis=0)
    mad = np.median(np.abs(en - med[None, :]), axis=0) + 1e-6
    z = (en - med[None, :]) / (1.4826 * mad[None, :])
    z[stepmask[:, :nb]] = 0.0
    floor = np.median(en)
    mb = []
    for k, b in sorted(zip(*np.where((z > 9) & (en > 2.5 * floor)))):
        f = {"loop": int(k), "phase_s": round(b * bin_ / fs, 3), "sigma": round(float(z[k, b]), 1), "energy_x_floor": round(float(en[k, b] / floor), 1),
             "t_s": round(float(st[idx[k]]) / fs + b * bin_ / fs + skip, 2)}
        if mb and mb[-1]["loop"] == f["loop"] and f["phase_s"] - mb[-1]["last_phase_s"] < 0.06:      # bins within 60 ms are one event
            mb[-1]["last_phase_s"] = f["phase_s"]
            mb[-1]["bins"] += 1
            if f["sigma"] > mb[-1]["sigma"]:
                mb[-1].update({k_: v_ for k_, v_ in f.items() if k_ not in ("last_phase_s", "bins")})
        else:
            f["last_phase_s"] = f["phase_s"]
            f["bins"] = 1
            mb.append(f)
    # events whose phase recurs in 3 or more loops are deterministic (a property of the signal or the capture chain), not clicks
    ph = np.array([b["phase_s"] for b in mb]) if mb else np.array([])
    keep = []
    for b in mb:
        same = int(np.sum(np.abs(ph - b["phase_s"]) < 0.02))
        b["recurs_in_loops"] = same
        if same < 3:
            keep.append(b)
    dropped = len(mb) - len(keep)
    rec = {}
    for b in mb:
        if b["recurs_in_loops"] >= 3:
            key = round(b["phase_s"] / 0.02) * 0.02
            rec.setdefault(round(key, 2), []).append(b["sigma"])
    recurrent = sorted(([ph_, len(v_), round(float(np.median(v_)), 1)] for ph_, v_ in rec.items()), key=lambda r: -r[1])[:8]
    mb = keep
    # SEAM ENERGY: high-frequency energy of the median loop (800 Hz high-pass, 1 ms bins) within +-15 ms of the loop boundary against the median level elsewhere;
    # about 1 for an unbroken playback, large when every loop boundary is a splice
    he_env = np.sqrt(np.convolve(He ** 2, np.ones(16) / 16, "same"))
    bn = int(0.001 * fs)
    nbb = L // bn
    envb = np.sqrt((He[:nbb * bn].reshape(nbb, bn) ** 2).mean(1))
    typ = float(np.median(envb))
    seam_zone = np.r_[envb[:15], envb[-15:]]
    seam_ratio = float(seam_zone.max() / (typ + 1e-9))
    seam_where = int(np.argmax(np.r_[envb[:15], envb[-15:]]))
    dur = len(x) / fs
    res = {
        "file": os.path.basename(path), "duration_s": round(dur, 1), "loops_used": int(K), "align_quality_median": round(float(np.median(cq[good_l])), 2),
        "loop_time_scale_ppm": round(eps * 1e6, 0), "laptop_loop_s": round(N0 * (1 + eps) / fs, 5),
        "seam_ms_median": round(float(np.median(gaps)), 2) if len(gaps) else None,
        "seam_gaps_ms": [round(float(g), 2) for g in gaps], "seam_ms_p5_p95": [round(float(np.percentile(gaps, 5)), 2), round(float(np.percentile(gaps, 95)), 2)] if len(gaps) else None,
        "steps": merged, "bursts": mb, "bursts_dropped_recurrent": dropped, "recurrent_phases": recurrent,
        "seam_hf_ratio": round(seam_ratio, 1), "seam_hf_peak_bin": seam_where, "loop_start_s": [round(float(st[i]) / fs + skip, 4) for i in idx],
        "steps_per_min": round(len(merged) / (dur / 60), 2), "bursts_per_min": round(len(mb) / (dur / 60), 2),
    }
    if verbose:
        print("%s: %.0f s, %d loops used, alignment quality %.2f, one loop = %.5f s on the laptop clock (payload %.5f s), time scale %+.0f ppm" %
              (res["file"], dur, K, res["align_quality_median"], res["laptop_loop_s"], nominal, res["loop_time_scale_ppm"]))
        if len(gaps):
            print("  SEAM gap (next loop start minus this loop end): median %.2f ms, 5-95%% %.2f..%.2f ms" % (res["seam_ms_median"], res["seam_ms_p5_p95"][0], res["seam_ms_p5_p95"][1]))
        print("  STEP findings (> 1.2 ms persistent timeline step inside a loop): %d (%.2f/min)" % (len(merged), res["steps_per_min"]))
        for s_ in merged[:30]:
            print("     t=%.1f s loop %d phase %.2f s step %+.2f ms" % (s_["t_s"], s_["loop"], s_["phase_s"], s_["step_ms"]))
        print("  SEAM HF energy: peak %.1fx the typical level within 15 ms of the loop boundary (1 = no splice)" % seam_ratio)
        print("  recurrent (deterministic) high-frequency features [phase s, loops, median sigma]: %s" % recurrent)
        print("  BURST findings (HF energy > 9 sigma over the same phase of the other loops): %d (%.2f/min), %d recurrent-phase events dropped" % (len(mb), res["bursts_per_min"], dropped))
        for b_ in mb[:30]:
            print("     t=%.1f s loop %d phase %.3f s  %.1f sigma, %.1fx floor, %d bins" % (b_["t_s"], b_["loop"], b_["phase_s"], b_["sigma"], b_["energy_x_floor"], b_["bins"]))
    if debug:
        return res, locals()
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wav")
    ap.add_argument("--payload", default=DEFAULT_PAYLOAD)
    ap.add_argument("--skip", type=float, default=0.0, help="seconds to ignore at the start (prompts, start-up)")
    ap.add_argument("--json")
    ap.add_argument("--rate", type=int, default=48000, help="the DSP rate the payload is played at (32000 for probe350)")
    ap.add_argument("--preemph", action="store_true", help="the played signal is the first difference of the payload (validation files)")
    a = ap.parse_args()
    res = analyse(a.wav, a.payload, a.skip, preemph=a.preemph, rate=a.rate)
    if a.json:
        json.dump(res, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
