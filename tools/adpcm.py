#!/usr/bin/env python3
"""IMA ADPCM, in the exact dialect the CSR ADK's voice_prompt_tool produces and
TransformAdpcmDecode consumes (see docs/deep/offline-2026-10-10/adpcm-format.md).

The format, in one paragraph: plain IMA/DVI ADPCM, 4 bits per sample, NO block headers,
NO framing, NO byte-count field; the decoder state (predictor, step index) starts at
(0, 0) and runs continuously over the whole byte stream; the FIRST sample of each byte is
in the HIGH nibble and the second in the LOW nibble; the standard 89-entry step table and
the standard index table; the quantiser is the CWI "adpcm_coder" (1992, Stichting
Mathematisch Centrum -- the same code as CPython's audioop.lin2adpcm), which the ADK tool
bundles as adpcm/ima_adpcm.py. Evidence grade: the encoder here reproduces the ADK tool's
output byte for byte (2,000/2,000 and 3,000/3,000 bytes on two test signals, 2026-10-10;
B1 re-check: a third signal, 5,001 samples, 2,501/2,501 codec bytes) AND the 16 vendor-made
.prm files in adk/4.3.1/app/apps/sink/*_prompts whose source WAV ships in
tools/bin/SampleAudioPrompts/8kHz_16bit (33,504/33,504 bytes). The textbook quantiser
delta = min(7, 4*|diff|/step) is NOT this dialect: it agrees with the vendor files on only
65% of bytes (B1). The decoder is the standard IMA reconstruction (= CWI adpcm_decoder:
high nibble first, step read before the index update, clamp to int16, index 0..88).

File-level detail (B1, measured on voice_prompt_tool.exe): a .prm is padded with ONE 0x00
byte when the codec byte count is odd, i.e. the file length is always even (5,002 samples ->
2,501 codec bytes -> 2,502-byte .prm; 4,999 / 5,003 samples -> 2,500 / 2,502 bytes, no pad);
the .idx size field records the padded length. encode() returns the bare codec bytes;
encode_prm() adds the tool's pad. A trailing 0x00 decodes as two "+step>>3, index-1"
samples: inaudible, and irrelevant to any even-sized payload.

API (all pure Python, no numpy needed):

    encode(pcm16, state=None)        -> bytes            (state: (valpred, index) or None = (0,0))
    encode_prm(pcm16)                -> bytes            (encode() + the tool's pad to an even length)
    encode_state(pcm16, state=None)  -> (bytes, state)   (state carried out for continuation)
    decode(data, state=None)         -> list of int16
    decode_state(data, state=None)   -> (list, state)
    decode_nibbles(nibbles, state)   -> (list, state)    (nibbles = ints 0..15, in play order)
    nibbles(data)                    -> list of 0..15    (high nibble first)
    pack(nibbles)                    -> bytes            (pads an odd count with a 0 nibble)
    step_one(state, nibble)          -> (sample, state)  (one decoder step)

CLI:
    python tools/adpcm.py --selftest
    python tools/adpcm.py encode in.pcm out.adpcm        (in.pcm = raw little-endian int16)
    python tools/adpcm.py encode in.pcm out.prm --prm    (padded to an even length like the tool)
    python tools/adpcm.py decode in.adpcm out.pcm
    python tools/adpcm.py decode in.adpcm out.wav --rate 8000
"""
import os
import struct
import sys

STEP = [
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
    50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230,
    253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963,
    1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024,
    3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493,
    10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623,
    27086, 29794, 32767,
]
INDEX_DELTA = [-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8]
INITIAL_STATE = (0, 0)      # (valpred, index): what a fresh TransformAdpcmDecode starts from


def _clamp16(v):
    return -32768 if v < -32768 else 32767 if v > 32767 else v


def step_one(state, nibble):
    """One IMA decoder step. Returns (sample, new_state). Standard reconstruction:
    diff = step/8 + (b2 ? step) + (b1 ? step/2) + (b0 ? step/4), signed by bit 3."""
    valpred, index = state
    step = STEP[index]
    diff = step >> 3
    if nibble & 4:
        diff += step
    if nibble & 2:
        diff += step >> 1
    if nibble & 1:
        diff += step >> 2
    valpred = _clamp16(valpred - diff if nibble & 8 else valpred + diff)
    index += INDEX_DELTA[nibble]
    index = 0 if index < 0 else 88 if index > 88 else index
    return valpred, (valpred, index)


def encode_state(pcm16, state=None):
    """CWI adpcm_coder quantiser (= audioop.lin2adpcm = the ADK tool). Returns (bytes, state).
    An odd sample count leaves the last byte's low nibble 0 (as the ADK tool does)."""
    valpred, index = state if state is not None else INITIAL_STATE
    out = bytearray()
    hi = None
    for val in pcm16:
        step = STEP[index]
        diff = val - valpred
        sign = 8 if diff < 0 else 0
        if sign:
            diff = -diff
        delta = 0
        vpdiff = step >> 3
        if diff >= step:
            delta = 4
            diff -= step
            vpdiff += step
        step >>= 1
        if diff >= step:
            delta |= 2
            diff -= step
            vpdiff += step
        step >>= 1
        if diff >= step:
            delta |= 1
            vpdiff += step
        valpred = _clamp16(valpred - vpdiff if sign else valpred + vpdiff)
        delta |= sign
        index += INDEX_DELTA[delta]
        index = 0 if index < 0 else 88 if index > 88 else index
        if hi is None:
            hi = delta
        else:
            out.append((hi << 4) | delta)
            hi = None
    if hi is not None:
        out.append(hi << 4)
    return bytes(out), (valpred, index)


def encode(pcm16, state=None):
    return encode_state(pcm16, state)[0]


def encode_prm(pcm16):
    """Exactly what voice_prompt_tool.exe writes to prompts/N.prm: the codec bytes from state
    (0,0), plus one 0x00 byte if that count is odd (the file length is always even)."""
    b = encode(pcm16)
    return b + b'\x00' if len(b) % 2 else b


def nibbles(data):
    """The nibble stream in play order: high nibble of each byte first."""
    out = []
    for b in data:
        out.append(b >> 4)
        out.append(b & 15)
    return out


def pack(nibs):
    out = bytearray()
    for i in range(0, len(nibs), 2):
        lo = nibs[i + 1] if i + 1 < len(nibs) else 0
        out.append(((nibs[i] & 15) << 4) | (lo & 15))
    return bytes(out)


def decode_nibbles(nibs, state=None):
    st = state if state is not None else INITIAL_STATE
    out = []
    for n in nibs:
        s, st = step_one(st, n)
        out.append(s)
    return out, st


def decode_state(data, state=None):
    return decode_nibbles(nibbles(data), state)


def decode(data, state=None):
    return decode_state(data, state)[0]


# --------------------------------------------------------------------------- helpers
def write_wav(path, pcm16, rate):
    import wave
    w = wave.open(path, 'wb')
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(rate)
    w.writeframes(struct.pack('<%dh' % len(pcm16), *[_clamp16(int(v)) for v in pcm16]))
    w.close()


def read_pcm(path):
    b = open(path, 'rb').read()
    return list(struct.unpack('<%dh' % (len(b) // 2), b[:len(b) // 2 * 2]))


# --------------------------------------------------------------------------- self-test
def selftest(verbose=True):
    import math
    import random
    rnd = random.Random(12345)
    fails = []

    # 1. the ADK tool's own output, reproduced here as a fixture: the first 32 bytes of
    #    prompts/0.prm for the 4,000-sample test signal of 2026-10-10 (sin 440 Hz at 12000
    #    + gauss(0, 2500), seed 1, clamped). The signal is regenerated from the same seed.
    r = random.Random(1)
    sig = []
    for i in range(4000):
        v = int(12000 * math.sin(2 * math.pi * 440 * i / 8000) + r.gauss(0, 2500))
        sig.append(_clamp16(v))
    tool_head = bytes.fromhex('777777741fce88a40581301908bdc8a0928350416a08bc1c0c021a25210928db')
    got = encode(sig)
    if got[:len(tool_head)] != tool_head:
        fails.append('ADK-tool fixture: first %d bytes differ: %s vs %s'
                     % (len(tool_head), got[:len(tool_head)].hex(), tool_head.hex()))
    if len(got) != 2000:
        fails.append('ADK-tool fixture: length %d != 2000' % len(got))

    # 2. decode of the encoder's output tracks the input (IMA is lossy; the quantiser's
    #    reconstruction is exactly what the decoder produces, so the encoder-side valpred
    #    must equal the decoder output sample for sample)
    dec = decode(got)
    # recompute encoder-side predictions
    _, st = encode_state(sig)
    dec2, st2 = decode_state(got)
    if st != st2:
        fails.append('encoder/decoder end state differ: %r vs %r' % (st, st2))
    err = math.sqrt(sum((a - b) ** 2 for a, b in zip(sig, dec)) / len(sig))
    sig_rms = math.sqrt(sum(float(a) * a for a in sig) / len(sig))
    snr = 20 * math.log10(sig_rms / err) if err else 99.0
    if snr < 15:
        fails.append('round-trip SNR %.1f dB too low (RMS error %.0f)' % (snr, err))

    # 3. nibble order and packing
    if nibbles(b'\x7a\x05') != [7, 10, 0, 5]:
        fails.append('nibbles(): order wrong')
    if pack([7, 10, 0, 5]) != b'\x7a\x05' or pack([7]) != b'\x70':
        fails.append('pack(): wrong')

    # 4. state continuation: encoding in two halves with carried state == one pass
    a1, s1 = encode_state(sig[:1001])          # odd count: a dangling nibble is padded...
    a2, _ = encode_state(sig[1001:], s1)       # ...and so is this one (2999 samples)
    one = encode(sig)
    nib_split = nibbles(a1)[:1001] + nibbles(a2)[:2999]
    if pack(nib_split) != one:
        fails.append('state continuation differs from a single pass')

    # 5. silence from (0,0) stays silent: 0x00 bytes decode to all zeros (step 7 >> 3 = 0)
    if any(decode(b'\x00' * 64)):
        fails.append('zero bytes from state (0,0) are not silent')

    # 6. random bytes rail the decoder (the field-log 2026-10-04 table reproduces)
    rb = bytes(rnd.randrange(256) for _ in range(4000))
    d = decode(rb)
    railed = sum(1 for v in d if v in (-32768, 32767)) / len(d)
    _, (_, idx) = decode_state(rb)
    if railed < 0.2 or idx < 60:
        fails.append('random bytes: railed %.0f%%, final index %d (expected railed, high index)'
                     % (100 * railed, idx))

    # 7. (B1, 2026-10-10) second ADK-tool fixture, ODD sample count: 5,001 samples of a
    #    100->2000 Hz chirp + gauss(0,1500) (seed 7) with a +32767 impulse at 1000..1003,
    #    a -20000 shelf at 2000..2499 and -32768 at 3000..3001. The tool wrote 2,502 bytes:
    #    2,501 codec bytes (last = 0xb0, the dangling nibble padded low) + one 0x00 pad.
    r7 = random.Random(7)
    n7 = 5001
    sig7 = []
    for i in range(n7):
        f = 100 + 1900 * i / n7
        v = 9000 * math.sin(2 * math.pi * f * i / 8000) + r7.gauss(0, 1500)
        if 1000 <= i < 1004:
            v = 32767
        if 2000 <= i < 2500:
            v += -20000
        if 3000 <= i < 3002:
            v = -32768
        sig7.append(_clamp16(int(v)))
    tool7_head = bytes.fromhex('f77777771810c508b011180c28d4a0d9')
    got7 = encode_prm(sig7)
    if got7[:16] != tool7_head or len(got7) != 2502 or got7[-2:] != b'\xb0\x00':
        fails.append('ADK-tool fixture 2 (odd count): head %s len %d tail %s'
                     % (got7[:16].hex(), len(got7), got7[-2:].hex()))

    # 8. (B1) vendor-made .prm files in the ADK tree, when present: encode(source WAV) must
    #    equal the shipped file, and the textbook quantiser must NOT (it is a different
    #    dialect: ~65% byte agreement on speech)
    vendor = 'skipped (ADK 4.3.1 prompt pack not present)'
    here = os.path.dirname(os.path.abspath(__file__))
    adk = os.path.join(here, '..', 'adk', '4.3.1', 'app')
    prm = os.path.join(adk, 'apps', 'sink', 'headset_prompts', '0.prm')
    wav = os.path.join(adk, 'tools', 'bin', 'SampleAudioPrompts', '8kHz_16bit',
                       '460_Prompts_Power_On_8k.wav')
    if os.path.exists(prm) and os.path.exists(wav):
        import wave
        w = wave.open(wav, 'rb')
        raw = w.readframes(w.getnframes())
        w.close()
        pcm = list(struct.unpack('<%dh' % (len(raw) // 2), raw))
        vb = open(prm, 'rb').read()
        ours = encode_prm(pcm)
        # textbook quantiser, for the negative
        vp, ix, nib = 0, 0, []
        for val in pcm:
            st_ = STEP[ix]
            df = val - vp
            sg = 8 if df < 0 else 0
            df = -df if sg else df
            dl = min(7, (df * 4) // st_)
            vd = st_ >> 3
            if dl & 4:
                vd += st_
            if dl & 2:
                vd += st_ >> 1
            if dl & 1:
                vd += st_ >> 2
            vp = _clamp16(vp - vd if sg else vp + vd)
            dl |= sg
            ix = max(0, min(88, ix + INDEX_DELTA[dl]))
            nib.append(dl)
        tb = pack(nib)
        agree_tb = sum(1 for a, b in zip(tb, vb) if a == b)
        if ours != vb:
            fails.append('vendor headset_prompts/0.prm != encode_prm(460_Prompts_Power_On_8k.wav)')
        if agree_tb > 0.9 * len(vb):
            fails.append('textbook quantiser agrees with the vendor file on %d/%d bytes: '
                         'the dialect is not pinned' % (agree_tb, len(vb)))
        vendor = ('%s (%d bytes); textbook quantiser %d/%d'
                  % ('match' if ours == vb else 'DIFFERS', len(vb), agree_tb, len(vb)))

    if verbose:
        print('adpcm selftest: %s' % ('OK' if not fails else 'FAIL'))
        print('  tool fixture      : %s' % ('match' if not any('fixture:' in f for f in fails) else 'DIFFERS'))
        print('  tool fixture 2    : %s (odd count, %d bytes, tail %s)'
              % ('match' if not any('fixture 2' in f for f in fails) else 'DIFFERS', len(got7), got7[-2:].hex()))
        print('  vendor .prm       : %s' % vendor)
        print('  round-trip SNR    : %.1f dB (RMS error %.0f on a noisy full-scale signal)' % (snr, err))
        print('  random-byte decode: %.0f%% railed, final index %d' % (100 * railed, idx))
        for f in fails:
            print('  FAIL:', f)
    return not fails


def main(argv):
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return 0
    if argv[0] == '--selftest':
        return 0 if selftest() else 1
    if argv[0] == 'encode':
        pcm = read_pcm(argv[1])
        data = encode_prm(pcm) if '--prm' in argv else encode(pcm)
        open(argv[2], 'wb').write(data)
        print('%d samples -> %d bytes%s' % (len(pcm), len(data),
                                            ' (padded to even like the ADK tool)' if '--prm' in argv else ''))
        return 0
    if argv[0] == 'decode':
        data = open(argv[1], 'rb').read()
        pcm = decode(data)
        rate = 8000
        if '--rate' in argv:
            rate = int(argv[argv.index('--rate') + 1])
        if argv[2].lower().endswith('.wav'):
            write_wav(argv[2], pcm, rate)
        else:
            open(argv[2], 'wb').write(struct.pack('<%dh' % len(pcm), *pcm))
        print('%d bytes -> %d samples (%.2f s at %d Hz)' % (len(data), len(pcm), len(pcm) / rate, rate))
        return 0
    print('unknown command %r' % argv[0])
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
