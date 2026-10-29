#!/usr/bin/env python3
"""transcribe_wav: speech-to-text for a recorded wav (offline model, no network after the first download).

Used to hear what the speaker said in a laptop-microphone recording (tools/mic_rec.ps1). Needs faster-whisper
(installed in a venv, not in the repo): <venv>/Scripts/python.exe tools/transcribe_wav.py file.wav [start_clock]
Prints segments with word times; with start_clock (HH:MM:SS.s, the REC_START time) also the wall-clock time."""
import sys
from faster_whisper import WhisperModel


def clock(base, t):
    if base is None:
        return ''
    h, m, s = base.split(':')
    tot = int(h) * 3600 + int(m) * 60 + float(s) + t
    return ' [%02d:%02d:%05.2f]' % (tot // 3600, (tot % 3600) // 60, tot % 60)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    base = sys.argv[2] if len(sys.argv) > 2 else None
    model = WhisperModel('small.en', device='cpu', compute_type='int8')
    segs, info = model.transcribe(sys.argv[1], language='en', word_timestamps=True, vad_filter=False,
                                  condition_on_previous_text=False, beam_size=5)
    n = 0
    for s in segs:
        n += 1
        print('%7.2f-%7.2f%s  %s' % (s.start, s.end, clock(base, s.start), s.text.strip()))
        for w in s.words or []:
            print('        %7.2f-%7.2f  %-14s p=%.2f' % (w.start, w.end, w.word.strip(), w.probability))
    print('segments:', n)


if __name__ == '__main__':
    main()
