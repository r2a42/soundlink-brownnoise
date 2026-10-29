import sys, wave, numpy as np
def load(p, t0, t1):
    w = wave.open(p); r = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768
    return x[int(t0 * r):int(t1 * r)], r
def bands(x, r):
    # Welch-style: average spectra of 1 s hann blocks
    n = r
    acc = None; k = 0
    for i in range(0, len(x) - n, n // 2):
        seg = x[i:i + n] * np.hanning(n)
        sp = np.abs(np.fft.rfft(seg)) ** 2
        acc = sp if acc is None else acc + sp; k += 1
    fr = np.fft.rfftfreq(n, 1 / r)
    out = []
    for f in (30, 60, 120, 250, 500, 1000, 2000, 4000, 8000, 16000):
        sel = (fr > f / 2 ** 0.5) & (fr < f * 2 ** 0.5)
        out.append(10 * np.log10(acc[sel].mean() / k + 1e-18))
    return np.array(out)
a, ra = load(sys.argv[1], float(sys.argv[3]), float(sys.argv[4]))
b, rb = load(sys.argv[2], float(sys.argv[3]), float(sys.argv[4]))
ba, bb = bands(a, ra), bands(b, rb)
print("rms A %.4f  B %.4f  (A/B %.1f dB)" % (a.std(), b.std(), 20 * np.log10(a.std() / b.std())))
print("A rel 1k:", np.round(ba - ba[5], 1))
print("B rel 1k:", np.round(bb - bb[5], 1))
print("A-B     :", np.round((ba - ba[5]) - (bb - bb[5]), 1))
