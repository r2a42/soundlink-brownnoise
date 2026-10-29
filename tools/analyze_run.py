#!/usr/bin/env python3
"""analyze_run: one-call analysis of a laptop-microphone recording from tools/mic_rec.ps1.

    <venv>/Scripts/python.exe tools/analyze_run.py file.wav HH:MM:SS [--keep]

Prints (1) the recognised phrases with wall-clock times, (2) every loud event (rms over 3x the floor) with its clock time,
(3) the digital-silence gaps (rms < 3 for 50 ms or more, the capture dropouts). The wav is deleted afterwards unless --keep.
Needs numpy and faster-whisper (a venv outside the repo). Phrases from the recogniser on noise ("Thank you.", "You",
"Thanks for watching!") are artefacts: accept only phrases that match what the speaker is expected to say."""
import os, sys, wave
import numpy as np


def clock(base, t):
    h, m, s = base.split(':')
    tot = int(h) * 3600 + int(m) * 60 + float(s) + t
    return '%02d:%02d:%05.2f' % (tot // 3600, (tot % 3600) // 60, tot % 60)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    path, base = sys.argv[1], sys.argv[2][:8]
    w = wave.open(path)
    sr = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(float)
    print('file %.1f s, start clock %s' % (len(x) / sr, base))
    w.close()
    from faster_whisper import WhisperModel
    model = WhisperModel('small.en', device='cpu', compute_type='int8')
    segs, _ = model.transcribe(path, language='en', condition_on_previous_text=False, beam_size=5)
    print('--- phrases')
    for s in segs:
        print('  %s  (%6.2f-%6.2f s)  %s' % (clock(base, s.start), s.start, s.end, s.text.strip()))
    N = int(0.1 * sr)
    m = len(x) // N
    rms = np.sqrt((x[:m * N].reshape(m, N) ** 2).mean(1))
    fl = np.median(rms)
    act = rms > max(fl * 3, fl + 25)
    print('--- loud events (floor %.1f)' % fl)
    i = 0
    while i < m:
        if act[i]:
            j = i
            last = i
            while j < m and j - last <= 8:
                if act[j]:
                    last = j
                j += 1
            print('  %s  %6.1f-%6.1f s  peak rms %5d' % (clock(base, i * 0.1), i * 0.1, (last + 1) * 0.1, rms[i:last + 1].max()))
            i = last + 1
        else:
            i += 1
    n = int(0.05 * sr)
    ds = [t for t in np.arange(0, len(x) / sr - 0.05, 0.05) if np.sqrt((x[int(t * sr):int(t * sr) + n] ** 2).mean()) < 3]
    print('--- digital-silence gaps (rms < 3), excluding the first 0.4 s warm-up')
    gaps = []
    for t in ds:
        if t < 0.4:
            continue
        if gaps and t - gaps[-1][1] < 0.075:
            gaps[-1][1] = t
        else:
            gaps.append([t, t])
    for a, b in gaps:
        print('  %s  %6.2f-%6.2f s  (%.2f s)' % (clock(base, a), a, b + 0.05, b + 0.05 - a))
    print('  none' if not gaps else '  %d gap(s)' % len(gaps))
    w.close()
    if '--keep' not in sys.argv:
        os.remove(path)
        print('(wav deleted)')


if __name__ == '__main__':
    main()
