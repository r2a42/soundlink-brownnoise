#!/usr/bin/env python3
"""decode_census_audio: read the spoken census (probe211b / probe213) from a microphone recording by CLUSTERING the prompts.

The speaker says every digit with one of ten fixed phrases ("battery 10%" = 0 ... "battery 100%" = 9) and a separator ("voice prompts off"), so the
same digit always sounds the same. Speech recognition on single prompts is error-prone (music, levels), so this tool
  1. cuts the recording into prompt events (energy bursts; a prompt is about 1 to 2 s, spacing 3.5 s or more),
  2. clusters the events by their spectral shape (onset-aligned log-mel, level removed),
  3. labels each cluster by a majority vote of per-event recognition (faster-whisper, biased with the phrase list),
  4. decodes words (digits, then a check digit = sum of the five digits mod 10, then a separator) and checks every check digit.
    <venv>/Scripts/python.exe tools/decode_census_audio.py file.wav [--thresh 0=auto] [--start 40] [--keep] [--labels A=0,B=1,...]
Prints the clusters (size and vote), the event sequence with times, and the decoded words with check-digit verdicts.
Needs numpy, scipy, faster-whisper (a venv outside the repo)."""
import os, re, sys, wave
import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.signal import stft

WORDS_BIAS = ('Battery 10%. Battery 20%. Battery 30%. Battery 40%. Battery 50%. Battery 60%. Battery 70%. Battery 80%. '
              'Battery 90%. Battery 100%. Voice prompts off. Voice prompts on.')
PHR = {r'\b10\b|ten': 0, r'\b20\b|twenty': 1, r'\b30\b|thirty': 2, r'\b40\b|forty': 3, r'\b50\b|fifty': 4, r'\b60\b|sixty': 5,
       r'\b70\b|seventy': 6, r'\b80\b|eighty': 7, r'\b90\b|ninety': 8, r'\b100\b|hundred': 9}


def args():
    a = sys.argv[1:]
    opt = {'thresh': 0.0, 'start': 0.0, 'keep': '--keep' in a, 'labels': None}
    if '--thresh' in a:
        opt['thresh'] = float(a[a.index('--thresh') + 1])
    if '--start' in a:
        opt['start'] = float(a[a.index('--start') + 1])
    if '--labels' in a:
        opt['labels'] = dict(kv.split('=') for kv in a[a.index('--labels') + 1].split(','))
    opt['path'] = a[0]
    return opt


def events(x, sr, thresh, start):
    N = int(0.05 * sr)
    m = len(x) // N
    rms = np.sqrt((x[:m * N].reshape(m, N) ** 2).mean(1))
    rms = np.convolve(rms, np.ones(5) / 5, 'same')          # 0.25 s smoothing: speech modulates a lot inside one prompt
    if thresh <= 0:
        thresh = max(100.0, 6.0 * float(np.median(rms)))   # automatic: 6 x the floor
    act = rms > thresh
    ev, i = [], 0
    while i < m:
        if act[i]:
            j = i
            last = i
            while j < m and j - last <= 6:      # 0.3 s of tolerated dip inside one prompt
                if act[j]:
                    last = j
                j += 1
            t0, t1 = i * 0.05, (last + 1) * 0.05
            if t1 - t0 >= 0.4 and t0 >= start:
                ev.append((t0, t1))
            i = last + 1
        else:
            i += 1
    return ev


def feat(x, sr, t0):
    a = max(0, int((t0 - 0.1) * sr))
    seg = x[a:a + int(2.4 * sr)]
    if len(seg) < int(2.4 * sr):
        seg = np.pad(seg, (0, int(2.4 * sr) - len(seg)))
    f, t, Z = stft(seg, sr, nperseg=400, noverlap=240)           # 25 ms window, 10 ms hop
    P = np.abs(Z) ** 2
    edges = np.geomspace(150, 7500, 25)
    bands = np.array([P[(f >= edges[k]) & (f < edges[k + 1])].sum(0) for k in range(24)])
    L = np.log(bands + 1e-3)
    L = L - L.mean()                                            # level removed
    return L[:, ::2]                                            # 20 ms frames x 24 bands


def dist(F1, F2):
    best = 1e9
    for s in range(-4, 5):
        a, b = (F1[:, max(0, s):], F2[:, max(0, -s):]) if s >= 0 else (F1[:, :s], F2[:, -s:])
        n = min(a.shape[1], b.shape[1])
        d = np.sqrt(((a[:, :n] - b[:, :n]) ** 2).mean())
        best = min(best, d)
    return best


def main():
    o = args()
    w = wave.open(o['path'])
    sr = w.getframerate()
    x = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(float)
    w.close()
    ev = events(x, sr, o['thresh'], o['start'])
    print('events:', len(ev))
    F = [feat(x, sr, t0) for t0, _ in ev]
    n = len(F)
    D = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            D[i, j] = D[j, i] = dist(F[i], F[j])
    iu = np.triu_indices(n, 1)
    Z = linkage(D[iu], 'average')
    lab = fcluster(Z, t=12, criterion='maxclust')
    # per-event recognition for the vote
    from faster_whisper import WhisperModel
    model = WhisperModel('small.en', device='cpu', compute_type='int8')
    votes = {}
    txt = []
    for k, (t0, t1) in enumerate(ev):
        a, b = max(0, int((t0 - 0.3) * sr)), int((t1 + 0.5) * sr)
        seg = x[a:b].astype(np.float32)
        seg = np.concatenate([np.zeros(sr // 2, np.float32), seg / max(1.0, np.abs(seg).max()) * 0.9, np.zeros(sr // 2, np.float32)])
        segs, _ = model.transcribe(seg, language='en', initial_prompt=WORDS_BIAS, condition_on_previous_text=False, beam_size=5,
                                   temperature=0.0, no_speech_threshold=0.95, log_prob_threshold=-3.0)
        t = ' '.join(s.text.strip() for s in segs).lower()
        txt.append(t)
        d = None
        if re.search(r'voice|prompt|off|on\b', t):
            d = 'S'
        else:
            for rx, v in PHR.items():
                if re.search(rx, t):
                    d = str(v)
                    break
        votes.setdefault(lab[k], []).append(d)
    names = {}
    print('--- clusters (size, votes)')
    for c in sorted(votes):
        vs = [v for v in votes[c] if v is not None]
        cnt = {v: vs.count(v) for v in set(vs)}
        top = max(cnt, key=cnt.get) if cnt else '?'
        names[c] = top
        print('  cluster %2d size %3d  vote %s   %s' % (c, len(votes[c]), top, dict(sorted(cnt.items(), key=lambda kv: -kv[1]))))
    if o['labels']:
        for c, v in o['labels'].items():
            names[int(c)] = v
    print('--- sequence (time, cluster, label, recognised text)')
    seq = []
    for k, (t0, t1) in enumerate(ev):
        seq.append(names.get(lab[k], '?'))
        print('  %7.1f s  c%-2d %s   %s' % (t0, lab[k], names.get(lab[k], '?'), txt[k]))
    s = ''.join(seq)
    print('--- decoded (S = separator)')
    print(s)
    words = [w_ for w_ in s.split('S') if w_]
    for w_ in words:
        if all(ch.isdigit() for ch in w_) and len(w_) >= 2:
            digs = [int(ch) for ch in w_[:-1]]
            chk = int(w_[-1])
            ok = (sum(digs) % 10) == chk
            print('  word %-8s value %-6s check %d %s' % (w_, ''.join(map(str, digs)).lstrip('0') or '0', chk, 'ok' if ok else 'MISMATCH (expected %d)' % (sum(digs) % 10)))
        else:
            print('  word %-8s (not decodable)' % w_)
    if not o['keep']:
        os.remove(o['path'])


if __name__ == '__main__':
    main()
