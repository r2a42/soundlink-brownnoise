"""Bit-exact model of brown_noise.asm's inner loop, plus an octave-slope
check like ../tests/test_noise.c's (FFT band means here, 4.5-7.5 dB per
octave; the C test uses single-bin Goertzel, 4-8 dB).

  python model.py [wav_out]               model only
  python model.py --compare L.raw R.raw   check kalsim DAC captures (sim.sh)

Kalimba semantics modelled: 24-bit two's-complement registers, (int)
multiply keeps the low 24 bits, ASHIFT by a negative amount is an
arithmetic right shift, cbops.shift -8 drops the low 8 bits for the
16-bit DAC port."""
import sys
import wave

import numpy as np

LCG_MULT, LCG_INC = -4508331, 17
LIMIT = 1 << 22            # 0.5 in Q23
FS = 48000


def wrap24(x):
    x &= 0xFFFFFF
    return x - (1 << 24) if x & 0x800000 else x


def generate(n, state=21845):
    acc = y = prev = 0
    out = np.empty(n, dtype=np.int32)
    for i in range(n):
        state = wrap24(wrap24(state * LCG_MULT) + LCG_INC)
        acc = acc - (acc >> 9)
        acc = acc + (state >> 6)
        acc = min(max(acc, -LIMIT), LIMIT)
        y = y - (y >> 6) + (acc - prev)
        prev = acc
        y = min(max(y, -LIMIT), LIMIT)
        out[i] = y
    return out


def band_db(x, f):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    freqs = np.fft.rfftfreq(len(x), 1 / FS)
    sel = (freqs > f / 2 ** 0.25) & (freqs < f * 2 ** 0.25)
    return 10 * np.log10(spec[sel].mean())


def read_pcm(path):
    raw = open(path, "rb").read()
    if len(raw) % 2:
        print(f"{path}: odd length {len(raw)}, dropping the partial sample")
    return np.frombuffer(raw[:len(raw) & ~1], dtype="<i2")


def compare(left, right, n=None):
    """n=None checks every captured sample."""
    L, R = read_pcm(left), read_pcm(right)
    m = min(len(L), len(R))
    L, R = L[:m], R[:m]
    nz = np.flatnonzero(L)
    if len(nz) == 0:
        print(f"FAIL: {m} samples captured, none non-zero (did kalsim run?)")
        return False
    start = int(nz[0])
    n = m - start if n is None else n
    ref = (generate(n + 16) >> 8).astype(np.int16)
    ref = ref[np.flatnonzero(ref)[0]:]
    k = min(n, len(L) - start, len(ref))
    same_lr = np.array_equal(L, R)
    exact = np.array_equal(L[start:start + k], ref[:k])
    z = np.concatenate(([0], (L[start:] == 0).astype(np.int8), [0]))
    d = np.diff(z)
    longest = int((np.flatnonzero(d == -1) - np.flatnonzero(d == 1)).max(initial=0))
    print(f"{m} samples ({m / FS:.1f} s), first audio at {start}")
    print(f"left == right: {same_lr}; bit-exact vs model over {k}: {exact}; longest zero run {longest}")
    return same_lr and exact and longest < 4


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--compare":
        sys.exit(0 if compare(sys.argv[2], sys.argv[3]) else 1)
    q23 = generate(FS * 3)
    pcm = (q23 >> 8).astype(np.int16)
    clipped = np.mean(np.abs(q23) >= LIMIT)
    rms = np.sqrt(np.mean((q23 / (1 << 23)) ** 2))
    print(f"rms {20 * np.log10(rms):.1f} dBFS, at clamp {clipped:.4%}")
    levels = [band_db(pcm.astype(float), f) for f in (400, 800, 1600, 3200)]
    ok = True
    for (lo, hi), f in zip(zip(levels, levels[1:]), (400, 800, 1600)):
        drop = lo - hi
        good = 4.5 <= drop <= 7.5
        ok &= good
        print(f"{f:>5} -> {2 * f:<5} Hz: {drop:5.2f} dB {'ok' if good else 'FAIL'}")
    if len(sys.argv) > 1:
        with wave.open(sys.argv[1], "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(FS)
            w.writeframes(pcm.tobytes())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
