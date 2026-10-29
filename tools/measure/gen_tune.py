import sys, numpy as np
FS = 48000
MULT, INC = -4508331, 17
def w24(v):
    v &= 0xFFFFFF
    return v - (1 << 24) if v & 0x800000 else v
def gen(n, leak=9, ins=7, sa=6, sb=7, g=4, S=6, seed=21845):
    st = seed; acc = la = lb = 0; out = np.empty(n)
    for i in range(n):
        st = w24(w24(st * MULT) + INC)
        acc = w24(acc - (acc >> leak)); acc = w24(acc + (st >> ins))
        la = w24(la + ((acc - la) >> sa)); lb = w24(lb + ((acc - lb) >> sb))
        v = w24(acc + (la - lb) * g); out[i] = (v >> S)
    return out
def bands(x):
    n = FS; acc = None; k = 0
    for i in range(0, len(x) - n, n // 2):
        sp = np.abs(np.fft.rfft(x[i:i + n] * np.hanning(n))) ** 2
        acc = sp if acc is None else acc + sp; k += 1
    fr = np.fft.rfftfreq(n, 1 / FS)
    return np.array([10 * np.log10((acc[(fr > f / 2 ** .5) & (fr < f * 2 ** .5)].mean()) / k) for f in (30, 60, 120, 250, 500, 1000, 2000, 4000, 8000)])
tgt = np.array([-4.9, -5.7, -4.4, 0.2, 1.1, 0.0, 1.9, 0.0, -0.3])      # measured A - B (generator minus payload, mic, relative 1k): we want to ADD -tgt
base = bands(gen(48000 * 20, g=4)); base -= base[5]
print("g=4 model rel 1k:", np.round(base, 1))
best = []
for g in (4, 6, 8, 10, 12, 16):
    for sa, sb in ((6, 7), (5, 7), (6, 8), (5, 6)):
        b = bands(gen(48000 * 20, g=g, sa=sa, sb=sb)); b -= b[5]
        delta = b - base            # change vs the flashed image
        err = np.sqrt(np.mean((delta + tgt) ** 2))
        best.append((err, g, sa, sb, np.round(delta, 1)))
best.sort(key=lambda t: t[0])
for e, g, sa, sb, d in best[:5]: print("err %.2f g %d sa %d sb %d delta vs flashed" % (e, g, sa, sb), d)
