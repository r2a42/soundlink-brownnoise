#!/usr/bin/env python3
"""sbclib: an independent, minimal SBC toolkit for route C (written 2026-10-13, offline).

Written from the A2DP SBC format and from the ADK sources (adk/4.4/app/src/kalimba/sbc/*.asm) WITHOUT
using N03/N04's scratch code (sbcmodel.py, sbcexact.py).  It contains

  * the 80-tap (and 40-tap) prototype windows decoded from the ADK table (global_variables_encdec.asm)
  * CRC-8 (poly 0x1D, init 0x0F), exactly as sbc/crc_calc.asm
  * header parse and frame length exactly as the Bose frame_decode order (docs: N04 E1/E2, re-read by me
    in build/analysis/kalimba/sbc_decoder_pm.disasm.txt lines 8320-8410 and 0x25ea):
      sync scan byte by byte, header, corrupt bitpool -> resume at sync+3 (NO crc byte, NO scale factors),
      else join bits + scale factors, CRC compare, CRC fail -> resume after the last scale-factor bit
      (return-on-corrupt = 0: always retry), a header whose nsb differs from the previous header's nsb
      (even a corrupt one) zeroes the synthesis state (read_frame_header.asm: if NZ call silence_decoder)
  * bit allocation (loudness / SNR), sample dequantisation, analysis and synthesis filter banks
  * a stream decoder that returns events and PCM

No device access, no private data.  Run:  python -I sbclib.py   (self-test)
"""
import os
import re
import struct
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
ADK_SBC = os.path.join(ROOT, "adk", "4.4", "app", "src", "kalimba", "sbc")
DATA_US = os.path.join(ROOT, "firmware", "bose", "extracted", "internal_fs", "data_us")

SYNC = 0x9C


# ----------------------------------------------------------------------------------------------
# tables
# ----------------------------------------------------------------------------------------------
def load_proto(nsb):
    txt = open(os.path.join(ADK_SBC, "global_variables_encdec.asm")).read()
    m = re.search(r"win_coefs_m%d\[\d+\]\s*=\s*(.*?);" % nsb, txt, re.S)
    words = [int(w, 16) for w in re.findall(r"0x([0-9A-Fa-f]{4})", m.group(1))]
    b = b"".join(struct.pack(">H", w) for w in words)
    vals = [int.from_bytes(b[i:i + 3], "big", signed=True) / 2.0 ** 25 for i in range(0, len(b) - 2, 3)]
    assert len(vals) == 10 * nsb, len(vals)
    return np.array(vals)


PROTO = {8: load_proto(8), 4: load_proto(4)}

LOUD_OFFSET = {
    8: [[-2, 0, 0, 0, 0, 0, 0, 1], [-3, 0, 0, 0, 0, 0, 1, 2], [-4, 0, 0, 0, 0, 0, 1, 2], [-4, 0, 0, 0, 0, 0, 1, 2]],
    4: [[-1, 0, 0, 0], [-2, 0, 0, 1], [-2, 0, 0, 1], [-2, 0, 0, 1]],
}


def _mats(nsb):
    k = np.arange(nsb)
    i2 = np.arange(2 * nsb)
    # analysis matrix M[k][i] = cos((k+0.5)(i - nsb/2) pi/nsb)
    Ma = np.cos((k[:, None] + 0.5) * (i2[None, :] - nsb / 2.0) * np.pi / nsb)
    # synthesis matrix N[i][k] = cos((k+0.5)(i + nsb/2) pi/nsb)
    Ns = np.cos((k[None, :] + 0.5) * (i2[:, None] + nsb / 2.0) * np.pi / nsb)
    return Ma, Ns


MATS = {8: _mats(8), 4: _mats(4)}


# ----------------------------------------------------------------------------------------------
# CRC and bit helpers
# ----------------------------------------------------------------------------------------------
def crc8_bits(bits, crc=0x0F):
    for b in bits:
        top = (b ^ (crc >> 7)) & 1
        crc = (crc << 1) & 0xFF
        if top:
            crc ^= 0x1D
    return crc


def bits_of(v, n):
    return [(v >> (n - 1 - i)) & 1 for i in range(n)]


class BitReader:
    def __init__(self, buf, bytepos):
        self.buf = buf
        self.p = bytepos * 8

    def get(self, n):
        v = 0
        for _ in range(n):
            byte = self.buf[self.p >> 3] if (self.p >> 3) < len(self.buf) else 0
            v = (v << 1) | ((byte >> (7 - (self.p & 7))) & 1)
            self.p += 1
        return v


# ----------------------------------------------------------------------------------------------
# bit allocation (A2DP SBC spec, 12.6.3.? / ADK calc_bit_allocation.asm)
# ----------------------------------------------------------------------------------------------
def bit_allocation(sf, nsb, ch_mode, method, bp, fsi):
    """sf: list per channel of nsb scale factors.  returns bits[ch][sb]."""
    nch = len(sf)
    bitneed = []
    for ch in range(nch):
        row = []
        for sb in range(nsb):
            if method == 1:  # SNR
                row.append(sf[ch][sb])
            else:
                if sf[ch][sb] == 0:
                    row.append(-5)
                else:
                    loud = sf[ch][sb] - LOUD_OFFSET[nsb][fsi][sb]
                    row.append(int(loud / 2) if loud > 0 else loud)  # C-style truncation
        bitneed.append(row)
    bits = [[0] * nsb for _ in range(nch)]
    groups = [[0]] if False else None
    if ch_mode in (0, 1):  # mono, dual: each channel on its own with the full bitpool
        chsets = [[c] for c in range(nch)]
    else:  # stereo, joint: common allocation over both channels
        chsets = [list(range(nch))]
    for cs in chsets:
        mx = max(bitneed[c][sb] for c in cs for sb in range(nsb))
        bitcount = 0
        slicecount = 0
        bitslice = mx + 1
        while True:
            bitslice -= 1
            bitcount += slicecount
            slicecount = 0
            for c in cs:
                for sb in range(nsb):
                    bn = bitneed[c][sb]
                    if bitslice + 1 < bn < bitslice + 16:
                        slicecount += 1
                    elif bn == bitslice + 1:
                        slicecount += 2
            if bitcount + slicecount >= bp:
                break
        if bitcount + slicecount == bp:
            bitcount += slicecount
            bitslice -= 1
        for c in cs:
            for sb in range(nsb):
                bn = bitneed[c][sb]
                if bn < bitslice + 2:
                    bits[c][sb] = 0
                else:
                    bits[c][sb] = min(bn - bitslice, 16)
        # distribute leftovers
        done = False
        for c in cs:
            if done:
                break
            for sb in range(nsb):
                if bitcount >= bp:
                    done = True
                    break
                if 2 <= bits[c][sb] < 16:
                    bits[c][sb] += 1
                    bitcount += 1
                elif bitneed[c][sb] == bitslice + 1 and bp > bitcount + 1:
                    bits[c][sb] = 2
                    bitcount += 2
        done = False
        for c in cs:
            if done:
                break
            for sb in range(nsb):
                if bitcount >= bp:
                    done = True
                    break
                if bits[c][sb] < 16:
                    bits[c][sb] += 1
                    bitcount += 1
    return bits


# ----------------------------------------------------------------------------------------------
# frame parse (Bose order)
# ----------------------------------------------------------------------------------------------
def parse_header(buf, i):
    """buf[i] == 0x9C.  Returns dict with kind in {'corrupt','crcfail','frame','short'} and 'next'
    (the read position the decoder resumes scanning from).  Bytes beyond len(buf) read as 0 and the
    result is flagged 'short' if the frame would extend past the end."""
    n = len(buf)
    if i + 3 > n:
        return dict(kind="short", i=i, next=n)
    b1 = buf[i + 1]
    bp = buf[i + 2]
    fsi = b1 >> 6
    blk = ((b1 >> 4) & 3) * 4 + 4
    mode = (b1 >> 2) & 3
    method = (b1 >> 1) & 1
    nsb = (b1 & 1) * 4 + 4
    nch = 2 if mode else 1
    ev = dict(i=i, fsi=fsi, blk=blk, mode=mode, method=method, nsb=nsb, nch=nch, bp=bp)
    lim = nsb * 16
    if mode >= 2:
        lim *= 2
    if lim > 250:
        lim = 250
    if lim < bp or bp < 2:
        ev.update(kind="corrupt", next=i + 3, rc=i + 3)
        return ev
    if i + 4 > n:
        ev.update(kind="short", next=n)
        return ev
    framecrc = buf[i + 3]
    crc = crc8_bits(bits_of(b1, 8) + bits_of(bp, 8))
    br = BitReader(buf, i + 4)
    join = []
    nbits = 0
    if mode == 3:
        for _ in range(nsb - 1):
            b = br.get(1)
            join.append(b)
            crc = crc8_bits([b], crc)
        join.append(0)
        b = br.get(1)  # RFA
        crc = crc8_bits([b], crc)
    sfs = [[0] * nsb for _ in range(nch)]
    for ch in range(nch):
        for sb in range(nsb):
            v = br.get(4)
            sfs[ch][sb] = v
            crc = crc8_bits(bits_of(v, 4), crc)
    t = blk * bp
    if mode >= 2:
        t += (mode - 2) * nsb
    else:
        t *= nch
    flen = ((nsb * nch) >> 1) + 5 + ((t - 1) >> 3)
    ev.update(flen=flen, sf=sfs, join=join)
    resume_crcfail = (br.p + 7) >> 3
    ev["rc"] = resume_crcfail
    if crc != framecrc:
        ev.update(kind="crcfail", next=resume_crcfail)
    else:
        if i + flen > n:
            ev.update(kind="short", next=n)
        else:
            ev.update(kind="frame", next=i + flen)
    return ev


def scan(buf, start=0, stop=None):
    """Yield the events the Bose decoder produces walking buf from byte `start` (read pointer)."""
    n = len(buf)
    stop = n if stop is None else stop
    pos = start
    while True:
        try:
            i = buf.index(SYNC, pos, n)
        except ValueError:
            return
        if i >= stop:
            return
        ev = parse_header(buf, i)
        yield ev
        if ev["kind"] == "short":
            return
        pos = ev["next"]


# ----------------------------------------------------------------------------------------------
# audio: dequantisation, synthesis
# ----------------------------------------------------------------------------------------------
def read_samples(buf, ev):
    """Return subband samples array (blk, nch, nsb) float, following bits order blk -> ch -> sb."""
    nsb, nch, blk, bp = ev["nsb"], ev["nch"], ev["blk"], ev["bp"]
    bits = bit_allocation(ev["sf"], nsb, ev["mode"], ev["method"], bp, ev["fsi"])
    # position of audio: after 4 header bytes + join/sf bits
    nbits_pre = (nsb if ev["mode"] == 3 else 0) + nch * nsb * 4
    br = BitReader(buf, ev["i"] + 4)
    br.p += nbits_pre
    out = np.zeros((blk, nch, nsb))
    for b in range(blk):
        for ch in range(nch):
            for sb in range(nsb):
                nb = bits[ch][sb]
                if nb:
                    code = br.get(nb)
                    lv = (1 << nb) - 1
                    out[b, ch, sb] = (2.0 ** (ev["sf"][ch][sb] + 1)) * ((2.0 * code + 1.0) / lv - 1.0)
    if ev["mode"] == 3:
        for sb in range(nsb):
            if ev["join"][sb]:
                m = out[:, 0, sb].copy()
                s = out[:, 1, sb].copy()
                out[:, 0, sb] = m + s
                out[:, 1, sb] = m - s
    return out


class Synth:
    """Polyphase synthesis, one channel (mono output = channel 0, stereo summed to mono for monitoring)."""

    def __init__(self, gain=1.0):
        self.nsb = 0
        self.V = None
        self.gain = gain

    def reset(self, nsb=None):
        if nsb is not None:
            self.nsb = nsb
        self.V = np.zeros(20 * self.nsb)

    def blocks(self, sb_blocks):
        """sb_blocks (nblk, nsb) -> pcm (nblk*nsb)"""
        nsb = self.nsb
        Ma, Ns = MATS[nsb]
        D = -PROTO[nsb] * nsb * self.gain   # sign: analysis->synthesis identity (checked: corr +1.0000, delay 73)
        out = np.zeros(len(sb_blocks) * nsb)
        V = self.V
        # U gather index
        idx = np.zeros(10 * nsb, dtype=int)
        for i in range(5):
            for j in range(nsb):
                idx[i * 2 * nsb + j] = i * 4 * nsb + j
                idx[i * 2 * nsb + nsb + j] = i * 4 * nsb + 3 * nsb + j
        for n, s in enumerate(sb_blocks):
            V[2 * nsb:] = V[:-2 * nsb].copy()
            V[:2 * nsb] = Ns @ s
            W = V[idx] * D
            out[n * nsb:(n + 1) * nsb] = W.reshape(10, nsb).sum(axis=0)
        return out


def analysis(x, nsb=8):
    """x: 1-D float, length multiple of nsb; returns (nblk, nsb)."""
    Ma, Ns = MATS[nsb]
    C = PROTO[nsb]
    nblk = len(x) // nsb
    X = np.zeros(10 * nsb)
    S = np.zeros((nblk, nsb))
    for n in range(nblk):
        X[nsb:] = X[:-nsb].copy()
        X[:nsb] = x[n * nsb:(n + 1) * nsb][::-1]
        Z = X * C
        Y = Z.reshape(5, 2 * nsb).sum(axis=0)
        S[n] = Ma @ Y
    return S


# ----------------------------------------------------------------------------------------------
# whole-stream decoder with the Bose control flow
# ----------------------------------------------------------------------------------------------
def decode_stream(buf, start=0, gain=1.0, return_events=True):
    """Run the byte stream through the Bose-order decoder.  Returns (pcm float array mono, events).
    The synthesis state is zeroed whenever a header (even a corrupt one) has a different nsb than the previous
    header; a stereo frame is summed to mono (monitoring only)."""
    syn = Synth(gain)
    syn.reset(8)
    prev_nsb = 8
    pcm = []
    events = []
    for ev in scan(buf, start):
        if ev["nsb"] != prev_nsb:
            ev["reset"] = True
            prev_nsb = ev["nsb"]
            syn.reset(ev["nsb"])
        else:
            ev["reset"] = False
        if ev["kind"] == "frame":
            sbs = read_samples(buf, ev)
            if ev["nch"] == 2:
                sbs = sbs.sum(axis=1)
            else:
                sbs = sbs[:, 0, :]
            ev["pcm_at"] = sum(len(p) for p in pcm)
            pcm.append(syn.blocks(sbs))
        events.append(ev)
    return (np.concatenate(pcm) if pcm else np.zeros(0)), events


# ----------------------------------------------------------------------------------------------
# frame builders
# ----------------------------------------------------------------------------------------------
def build_frame(sf_list, codes, bp, nsb=8, blk=16, fsi=2, method=0, mode=0):
    """Mono frame.  sf_list: nsb scale factors; codes: list of (blk) codes for subbands that have bits, in the
    order the decoder reads them; here codes[b] is a list per block of codes for each subband with bits>0."""
    ev = dict(nsb=nsb, nch=1, blk=blk, bp=bp, sf=[list(sf_list)], mode=mode, method=method, fsi=fsi)
    bits = bit_allocation(ev["sf"], nsb, mode, method, bp, fsi)[0]
    b1 = (fsi << 6) | (((blk - 4) // 4) << 4) | (mode << 2) | (method << 1) | (1 if nsb == 8 else 0)
    crc = crc8_bits(bits_of(b1, 8) + bits_of(bp, 8))
    sfbits = []
    for v in sf_list:
        sfbits += bits_of(v, 4)
    crc = crc8_bits(sfbits, crc)
    body = list(sfbits)
    for b in range(blk):
        k = 0
        for sb in range(nsb):
            if bits[sb]:
                body += bits_of(codes[b][k], bits[sb])
                k += 1
    while len(body) % 8:
        body.append(0)
    by = bytearray([SYNC, b1, bp, crc])
    for i in range(0, len(body), 8):
        v = 0
        for bt in body[i:i + 8]:
            v = (v << 1) | bt
        by.append(v)
    return bytes(by), bits


def flen_mono(nsb, blk, bp):
    return ((nsb) >> 1) + 5 + ((blk * bp - 1) >> 3)


def build_cover(clen, nsb=8, fsi=2):
    """Silent 4-block mono frame of exact length clen (>=9, <=72): bp = 2*(clen-8), scale factors 0, codes 0."""
    bp = 2 * (clen - 8)
    blk = 4
    b1 = (fsi << 6) | (0 << 4) | (0 << 2) | (0 << 1) | 1
    crc = crc8_bits(bits_of(b1, 8) + bits_of(bp, 8))
    crc = crc8_bits([0] * (nsb * 4), crc)
    by = bytearray([SYNC, b1, bp, crc]) + bytearray(clen - 4)
    return bytes(by)


def selftest():
    # CRC: A2DP test vector from the spec is not at hand; check internal consistency by parse
    sf = [10, 0, 0, 0, 0, 0, 0, 0]
    codes = [[(b * 5) % 64] for b in range(16)]
    fr, bits = build_frame(sf, codes, 6)
    assert len(fr) == 20, len(fr)
    assert bits == [6, 0, 0, 0, 0, 0, 0, 0], bits
    ev = parse_header(fr + bytes(30), 0)
    assert ev["kind"] == "frame" and ev["next"] == 20, ev
    for s in range(16):
        bits = bit_allocation([[s] + [0] * 7], 8, 0, 0, 6, 2)[0]
        # sf 0 -> all subbands -5
        if s == 0:
            assert sum(bits) == 6
        else:
            assert bits[0] == 6 and sum(bits) == 6, (s, bits)
    # round trip of the filter bank
    rng = np.random.default_rng(1)
    x = np.cumsum(rng.standard_normal(8 * 400)) * 0.0 + np.sin(2 * np.pi * 300 * np.arange(8 * 400) / 44100.0) * 10000
    S = analysis(x)
    syn = Synth(1.0)
    syn.reset(8)
    y = syn.blocks(S)
    best = None
    for d in range(60, 90):
        a = y[d + 200:d + 2400]
        b = x[200:2400]
        e = np.sqrt(np.mean((a - b) ** 2))
        if best is None or e < best[0]:
            best = (e, d)
    print("filterbank round trip: best delay", best[1], "rms err", best[0], "vs signal rms", np.sqrt(np.mean(x[200:2400] ** 2)))
    # sb0 gain: sine 300 Hz amplitude 10000 -> sb0 amplitude
    print("sb0 amplitude of a 300 Hz sine of 10000:", np.abs(S[50:300, 0]).max())
    print("selftest ok")


if __name__ == "__main__":
    selftest()
