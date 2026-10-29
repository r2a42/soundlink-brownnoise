import sys, wave, numpy as np
def run(p, t0, t1):
    w = wave.open(p); r = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768
    x = x[int(t0 * r):int(t1 * r)]
    n = int(0.01 * r)                       # 10 ms blocks
    m = len(x) // n
    e = []
    for i in range(m):
        seg = x[i * n:(i + 1) * n] * np.hanning(n)
        sp = np.abs(np.fft.rfft(seg)) ** 2
        fr = np.fft.rfftfreq(n, 1 / r)
        e.append(sp[(fr > 3000) & (fr < 12000)].sum())
    e = np.array(e)
    med = np.median(e)
    big = np.where(e > 8 * med)[0]
    big_t = sorted(set(int(i * 0.01) for i in big))
    return len(e), med, len(big), big_t[:15], e.max() / med
for p, t0, t1 in ((sys.argv[1], float(sys.argv[3]), float(sys.argv[4])), (sys.argv[2], float(sys.argv[3]), float(sys.argv[4]))):
    n, med, nb, bt, mx = run(p, t0, t1)
    print(p.split("\\")[-1], "blocks", n, "HF median %.3g" % med, "blocks > 8x median:", nb, "max/median %.1f" % mx, "at s:", bt)
