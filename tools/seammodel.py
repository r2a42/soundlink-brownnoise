#!/usr/bin/env python3
"""seammodel: gap and splice at the chunk seam versus poll period P, lead L, rebuild latency
c and the tick phase of the chunk length D.   (offline task J-T3, 2026-10-12)

WHAT IT IS.  A small deterministic timing model of the polled rebuild loop (probes 179..181:
a chunk plays, the cave polls every P ms, the first poll that finds port 3 free rebuilds the
chunk).  It answers "how much silence (gap) and how much cut audio (splice) does a seam
cost, and what do P, L, c and D do to it", so 181p's POLL_MS and the payload length can be
chosen before a flash.  It is arithmetic, NOT a measurement of the speaker: L, h, s0 and the
handler times are assumptions until a press measures them (STRATEGY section 8, 181p).

USAGE (all offline, no device)
    python tools/seammodel.py seam   --size 10486 --rate 8000 --P 200 --L 64
        # one configuration: every seam of a 16-chunk run, the closed-form phase and drift
    python tools/seammodel.py table  --size 10486 --rate 8000
        # long-run gap/splice for P x L (the recommended-POLL_MS table of the T03 note)
    python tools/seammodel.py ladder --size 10486 --rate 8000 --P 200,100,50 --Lmax 260
        # for each P: the L intervals that give a gap, a splice or a clean joint (what the ear
        # says about L: the gap you hear at P is an equation in L, h, s0)
    python tools/seammodel.py sens   --size 10486 --rate 8000 --P 1000,200,100,50
        # robustness: worst/mean gap and clean share over L x h x s0 x a_busy grids
    python tools/seammodel.py align  --rate 8000 --P 200 --L 16:200
        # which payload lengths (28 N - 268 bytes, T07) keep the free edge inside the lead window
    python tools/seammodel.py check
        # self-check: the zero-latency corner against cavesim's numbers (378 / 514 ms at
        # P = 1000), the closed forms, and the 03-seamless-generator gap table
    python tools/seammodel.py dscan  --size 10486 --rate 8000 --P 200 --L 0,16,32,64,128 \
        --d-ms-list 2400:3200:50
        # (round 3, V01 D3) the long-run cell versus the chunk length D: every ladder rung and
        # every 'the heard gap reads c' statement is conditional on D, which is NOT measured
    options common to seam/table/ladder/sens/align:  --h MS  --h1072 MS  --s0 MS  --a-busy MS
        --a-build MS  --F MS  --purge always|never  --chunks N  --d-ms MS (overrides size/rate)
        --reengage MS (default 7)  --mixer-off MS (default 6)

ROUND 3 (V01, 2026-10-12) CHANGES, what each does to a number you may have read before:
    D       the ladder and the table assume D = bytes x 2 / rate (2621.5 ms for rphrases_us at
            8 kHz).  The owner heard about 14 percent more (verify.md V5).  The 'heard gap at
            P = 200 reads c' rule holds only for D near 2621.5 ms and a_busy of 1 to 2 ms: at
            D = 2990 the same ladder reads 30 ms for L 0..191 and has no 200 ms rung.  Every
            command that uses the default D now prints a line saying so; pass --d-ms from a
            stopwatch (the time of chunk 2) and rebuild the ladder before reading c.  `sens`
            now sweeps D and a_busy by default; `dscan` prints the dependence directly.
    reengage  the mixer re-engagement of a port that is EMPTY: the mix op releases after 4
            consecutive empty audio-out calls (6 ms at 1.5 ms per call, T02 E21), and
            re-engages after 4 calls with enough tone plus a 1 ms music ramp (about 7 ms).  A
            silence of 6 ms or more therefore lasts about 7 ms longer (default gap 20 -> 27 ms;
            with F = 16 ms 12.5 -> 19.5; the low-c bracket stays 3 ms, below the 6 ms
            threshold).  The T02 skeptic withdrew the wait/flip only for a port that still
            holds data.  The music also un-ducks during the gap (not modelled).  --reengage 0
            restores the pre-round-3 numbers.  HYPOTHESIS for the size (7 ms), proven text for
            the 4-call hysteresis.
    horizon  `longrun` used to report a slow periodic gap as 'b' when the horizon (60-160
            chunks) was shorter than the slide period.  It now extends the run (to 3,000
            chunks) when the first horizon is gap free and the closed-form drift is nonzero,
            and prints 'b>N' when even that is clean.

THE MODEL (ms; every symbol is a parameter)
    D          chunk length = bytes x 2 samples / rate.  Arithmetic: well-supported (2 samples
               per ADPCM byte); the owner heard about 3 s and 12 s for 2.62 s and 10.49 s
               (14 percent more: verify.md V5, cause unknown), so --d-ms can override.
    P          poll period = the assembler constant (POLL_MS).  PROVEN.
    tick       the cave re-arms MessageSendLater(P) from INSIDE the handler (assemble_probe181
               REARM), so the spacing is P + a: a_busy on a busy tick, a_build on a rebuild tick.
               The delivery jitter of the timer is not modelled (unknown on the 0x00e46 hook).
    h          handler time from tick delivery to TransformStart (gate, FileFind x2,
               StreamFileSource, TransformAdpcmDecode, TransformStart).      ASSUMED 5 ms.
    h1072      tick to the 0x1072 send (the GATE is the first thing a free tick does).
                                                                             ASSUMED 1 ms.
    s0         TransformStart to the first audible sample of a chain that finds the pipeline
               empty.  Default one DSP copy period (16 ms at 8 kHz mono, 64 ms at 2 kHz):
               the period is PROVEN by kalsim (T02 skeptic: 128e6/rate us), "the start waits one
               tick" is a HYPOTHESIS.
    a_busy,a_build  tick to re-arm call, busy path / rebuild path.  ASSUMED 1 ms / h + 1 ms.
    L          lead = audible end minus free edge: the time the old tail still plays after
               TransformFromSink reads 0.  L = L_DSP + L_BC.  L_DSP lower bound 16..32 ms at
               8 kHz and 64..128 ms at 2 kHz (T02: 256-sample tone buffer, usable 255, 128
               samples per copy tick; well-supported); L_BC (port buffer behind it) UNKNOWN.
               Swept, never assumed.
    F          audio the 0x1072 purge can remove = the DSP tone buffer fill, at most 255
               samples = 31.9 ms at 8 kHz, 127.5 ms at 2 kHz (T02 proven size, usable fill 255).
               Default = that maximum (an upper bound on the cut).
    purge      always (the probes: GATE sends 0x1072 before every rebuild) or never (skip-re-arm
               on caught-early rebuilds, J-C17).  The old "wait to the next tick plus mixer flip,
               12 ms mean" is WITHDRAWN (T02 skeptic): tone_copy_extra refills the DSP buffer
               from the port within 1.5 ms when the port holds data.  What is left is the empty
               port: the whole tail is cut and the silence runs until the new chunk is audible
               (a hypothesis only because L_BC is unknown).

THE SEAM, step by step
    chunk k is audible from A_k, its audible end is E_k = A_k + D, the transform frees port 3
    (free edge, TransformFromSink reads 0) at t_f = E_k - L.  The first tick T >= t_f rebuilds:
        0x1072 at T + h1072, TransformStart at T + h, new audio ready at A_new = T + h + s0.
        R = E_k - (T + h1072)  remaining old audio at the purge.
        purge: S = min(R, F) if R > 0 else 0;   the old tail now ends at E' = E_k - S
        no purge: S = 0, E' = E_k.
        gap G = max(0, A_new - E')            silence (ms)
        A_{k+1} = max(A_new, E')              new data queues BEHIND a tail that is still playing
    kinds: GAP (G > 0), SPLICE (G = 0, S > 0: the purge cut S ms and the audio continues from
    the port or the new chunk: a waveform jump), BUTT (G = 0, S = 0: new chunk back to back with
    the old tail, only the decoder restart step, benign for brown material: 03 section 4.5).
    Whether a splice or a restart is audible is a hypothesis (03 4.5, R10 screening heuristic).
    Note the purge can MAKE a gap: a tick that lands in the tail removes F ms of it (all of it
    when R <= F), and the silence then runs until the new chunk is audible:
        G_purge = max(0, (c - h1072) - max(0, R - F)),    c = h + s0,
    i.e. exactly c - h1072 (20 ms at the defaults, 3 ms if h = s0 = 2) for a full cut and less
    for a partial one, even though skipping the purge would butt-join. So the purge floor IS c:
    it is what 181p at P = 200 reads out. F is the tone-buffer FILL at the purge, between about
    16 and 32 ms at 8 kHz depending on the copy-timer phase; the default 31.9 ms is the ceiling
    (try --F 16 and --h 2 --s0 2 for the brackets).

TWO PHASE REGIMES (03 V7 refined here; the long-run numbers of `table`/`ladder`/`sens`/`align`
    average over BOTH)
    LOCKED (every seam a GAP): A_{k+1} = T + h + s0 whatever T was, so the free edge falls at
        the same distance from the tick grid every chunk:
            u = (a_build + P - (h + s0 + D - L)) mod (P + a_busy),  u in [0, P + a_busy)
        one image repeats ONE seam: the 03 gap table's uniform average describes a population of
        configurations, not the seams of one image (`check` reproduces that table).
    SLIDING (seams BUTT or SPLICE, the audio timeline stays anchored to the old tail): the
        free-edge phase moves against the tick grid by
            drift = (D - (a_build + P)) mod (P + a_busy)      per chunk
        (u falls by `drift`, or rises by P + a_busy - drift when that is smaller). The loop is
        clean for u/|drift| chunks, then ONE tick is missed and a gap of about P - L + c opens,
        which re-anchors the timeline and starts the slide again: a clean image is a
        periodic dropout of about one poll, unless drift is 0. drift moves by a_busy per busy
        tick (13 ticks per chunk at P = 200 for the 2.62 s stand-in), so zero drift needs a_busy
        known to a fraction of a millisecond: the tick-phase alignment lever of 03 M1 is
        D = a_build + P (mod P + a_busy), measured, not computed. `align` ranks payload lengths
        (28 bytes = 7.0 ms of D per staging period at 8 kHz; N must factor as OUTER x INNER with
        both <= 255, T07) by the long-run gap fraction; `seam` prints drift for one setting.

STATUS LABELS used in the output and in docs/deep/firmware-study-2026-10-12/T03-...md:
    PROVEN  arithmetic on a proven constant (P, copy period, buffer size, D from bytes)
    ASSUMED a parameter nobody has measured (h, h1072, s0, a_busy, a_build, L_BC)
Nothing here says the speaker cannot play brown noise (CLAUDE.md rule 11); it prices a seam.
"""
import argparse
import math
import sys

DEFAULTS = dict(h=5.0, h1072=1.0, s0=None, a_busy=1.0, a_build=None, F=None, purge='always')
REENGAGE_MS = 7.0          # mixer re-engagement after an empty port (T02 E21: 4 calls x 1.5 ms + 1 ms ramp); HYPOTHESIS for the size
MIXER_OFF_MS = 6.0         # the mix op releases after 4 consecutive empty audio-out calls = 6 ms (T02 E21, proven text)
HORIZON_MAX = 3000         # longrun extends a clean-looking slide to this many chunks (V01 D5)
SAMPLES_BUF = 255          # usable fill of the 256-sample tone cbuffer (T02 skeptic: size - 1)
COPY_SAMPLES = 128         # samples moved per DSP copy tick (mono)
LONG = 160                 # chunks simulated for the long-run statistics
SKIP = 3                   # seams skipped as warm-up


def copy_period_ms(rate):
    """128e6/rate microseconds (T02 E9, proven by kalsim): 16 ms at 8 kHz, 64 ms at 2 kHz."""
    return 128e6 / rate / 1000.0


def buf_ms(rate):
    return SAMPLES_BUF * 1000.0 / rate


class Cfg:
    def __init__(self, D, P, L, rate=8000, h=5.0, h1072=1.0, s0=None, a_busy=1.0,
                 a_build=None, F=None, purge='always', reengage=REENGAGE_MS,
                 mixer_off=MIXER_OFF_MS):
        self.D, self.P, self.L, self.rate = float(D), float(P), float(L), rate
        self.reengage, self.mixer_off = float(reengage), float(mixer_off)
        self.h, self.h1072 = float(h), float(h1072)
        self.s0 = copy_period_ms(rate) if s0 is None else float(s0)
        self.a_busy = float(a_busy)
        self.a_build = self.h + 1.0 if a_build is None else float(a_build)
        self.F = buf_ms(rate) if F is None else float(F)
        self.purge = purge

    @property
    def c(self):
        return self.h + self.s0

    @property
    def Pb(self):
        return self.P + self.a_busy

    def describe(self):
        return ('D=%.1f ms  P=%g  L=%g  c=h+s0=%.1f+%.1f=%.1f  h1072=%g  a_busy=%g a_build=%.1f  '
                'F=%.1f  purge=%s  reengage=%g (silence >= %g ms)  (rate %d Hz)'
                % (self.D, self.P, self.L, self.h, self.s0, self.c, self.h1072, self.a_busy,
                   self.a_build, self.F, self.purge, self.reengage, self.mixer_off, self.rate))


def simulate(cfg, n_chunks=12):
    """The polled loop.  Returns a list of seam dicts, one per rebuild (the press is chunk 1)."""
    seams = []
    A = cfg.h + cfg.s0                      # chunk 1: press at t=0 builds at once
    E = A + cfg.D
    t_f = E - cfg.L
    T = cfg.a_build + cfg.P                 # the press handler arms the first poll
    Pb = cfg.Pb
    for k in range(2, n_chunks + 1):
        m = 0
        if T < t_f - 1e-9:                  # busy ticks, jumped arithmetically
            m = int(math.ceil((t_f - 1e-9 - T) / Pb))
            T += m * Pb
            if T < t_f - 1e-9:
                T += Pb
                m += 1
        tau = T + cfg.h1072
        A_new = T + cfg.h + cfg.s0
        R = E - tau
        S = min(R, cfg.F) if (cfg.purge == 'always' and R > 0) else 0.0
        E1 = E - S
        G = max(0.0, A_new - E1)
        A = max(A_new, E1)
        # V01 D4: a silence of mixer_off ms or more lets the mix op release (4 empty audio-out
        # calls) and the new chunk pays the re-engagement (4 calls + a ramp) before it is heard
        re = cfg.reengage if (G >= cfg.mixer_off - 1e-9 and G > 1e-9) else 0.0
        G += re
        A += re
        kind = 'GAP' if G > 1e-9 else ('SPLICE' if S > 1e-9 else 'BUTT')
        seams.append(dict(k=k, tick=T, t_f_prev=t_f, u=T - t_f, gap=G, cut=S, kind=kind,
                          A=A, E_prev=E, ticks_busy=m, reeng=re, A_new=A_new))
        E = A + cfg.D
        t_f = E - cfg.L
        T += cfg.a_build + cfg.P
    return seams


def longrun(cfg, n_chunks=LONG, skip=SKIP, extend=True):
    """Statistics over the seams after warm-up: the honest 'steady state' (a sliding phase is a
    periodic gap, not a clean seam).  V01 D5: when the first horizon shows no gap but the closed
    form says the free edge slides, the run is extended to the slide period (at most HORIZON_MAX
    chunks); a still-clean run is labelled 'b>N' (clean for at least N chunks), never plain 'b'."""
    s = simulate(cfg, n_chunks)[skip:]
    clean_for = None
    if extend and all(x['gap'] <= 1e-9 for x in s):
        d = abs(drift_per_chunk(cfg))
        if d > 1e-6:
            need = int(math.ceil(cfg.Pb / d)) + skip + 2
            if need > n_chunks:
                n2 = min(need, HORIZON_MAX)
                s = simulate(cfg, n2)[skip:]
                if all(x['gap'] <= 1e-9 for x in s):
                    clean_for = n2 - skip
    gaps = [x['gap'] for x in s]
    cuts = [x['cut'] for x in s]
    ng = sum(1 for g in gaps if g > 1e-9)
    n = len(s)
    out = dict(n=n, n_gap=ng, frac_gap=ng / n, gap_max=max(gaps), gap_mean=sum(gaps) / n,
               cut_max=max(cuts), last=s[-1])
    out['period'] = (n / ng) if ng else None
    if ng == n:
        out['cell'] = '%d' % round(out['gap_max'])
    elif ng == 0:
        out['cell'] = ('s%d' % round(out['cut_max'])) if out['cut_max'] > 1e-9 else (
            'b>%d' % clean_for if clean_for else 'b')
        out['clean_for'] = clean_for
    else:
        out['cell'] = 'g%d/%d' % (round(out['gap_max']), max(2, round(n / ng)))
    return out


def closed_form_u(cfg, reeng=0.0):
    """Locked tick phase after a GAP seam:  u = (a_build + P - (c + reeng + D - L)) mod
    (P + a_busy), reeng = the mixer re-engagement paid by the PREVIOUS seam (0 or cfg.reengage)."""
    return (cfg.a_build + cfg.P - (cfg.c + reeng + cfg.D - cfg.L)) % cfg.Pb


def d_assumption_note(a):
    """One line printed by every command that uses the default D (V01 D3)."""
    if getattr(a, 'd_ms', None):
        return ''
    return ('NOTE D = %.1f ms is an ASSUMPTION (bytes x 2 / rate). The owner heard about 14 percent '
            'more (verify.md V5). Every rung below is conditional on it: pass --d-ms from a '
            'stopwatch (time of chunk 2) and rebuild before reading c; `dscan` shows the '
            'dependence.' % (a.size * 2 * 1000.0 / a.rate))


def drift_per_chunk(cfg):
    """Sliding regime: u moves by -drift per clean chunk (drift in (-Pb/2, Pb/2])."""
    d = (cfg.D - (cfg.a_build + cfg.P)) % cfg.Pb
    return d - cfg.Pb if d > cfg.Pb / 2.0 else d


def uniform_stats(P, c, L, n=100000):
    """03 section 4.4: u uniform in [0, P), G = max(0, u + c - L): mean, max, share with gap."""
    tot = mx = cnt = 0.0
    for i in range(n):
        g = max(0.0, (i + 0.5) * P / n + c - L)
        tot += g
        mx = max(mx, g)
        cnt += g > 0
    return tot / n, mx, 100.0 * cnt / n


def fmt_seam(s):
    return '%-6s G=%7.1f ms  cut=%5.1f ms  u=%7.1f  tick at %9.1f' % (
        s['kind'], s['gap'], s['cut'], s['u'], s['tick'])


# ---------------------------------------------------------------- staging grid (T07)
def staging_ok(n):
    """N staging periods must factor as OUTER x INNER, both 1..255 (imm8 pair)."""
    return any(n % a == 0 and 1 <= n // a <= 255 for a in range(1, 256))


def payload_bytes(n):
    return 28 * n - 268


# ---------------------------------------------------------------- commands
def parse_list(s, cast=float):
    out = []
    for part in s.split(','):
        if ':' in part:
            bits = part.split(':')
            lo, hi = cast(bits[0]), cast(bits[1])
            step = cast(bits[2]) if len(bits) > 2 else (1 if cast is int else 8)
            v = lo
            while v <= hi + 1e-9:
                out.append(v)
                v += step
        elif part:
            out.append(cast(part))
    return out


def d_ms(a):
    return a.d_ms if a.d_ms else a.size * 2 * 1000.0 / a.rate


def mk(a, P, L, D=None):
    return Cfg(D if D is not None else d_ms(a), P, L, a.rate, a.h, a.h1072, a.s0, a.a_busy,
               a.a_build, a.F, a.purge, a.reengage, a.mixer_off)


def cmd_seam(a):
    cfg = mk(a, a.P, a.L)
    print(cfg.describe())
    if d_assumption_note(a):
        print(d_assumption_note(a))
    d = drift_per_chunk(cfg)
    nb = int(cfg.D // cfg.P)
    print('closed form: after a GAP seam the free edge sits u = %.1f ms into a %.1f ms tick '
          'spacing; after a clean seam u moves by %+.2f ms per chunk (%d busy ticks per chunk: '
          'each ms of a_busy error moves it %d ms)' % (closed_form_u(cfg, cfg.reengage), cfg.Pb, -d, nb, nb))
    for s in simulate(cfg, a.chunks):
        print('  seam into chunk %2d: %s' % (s['k'], fmt_seam(s)))
    lr = longrun(cfg)
    print('long run (%d seams): %s   gaps in %d of them, max %.1f ms, mean %.1f ms, max cut %.1f ms'
          % (lr['n'], lr['cell'], lr['n_gap'], lr['gap_max'], lr['gap_mean'], lr['cut_max']))
    return 0


def l_grid(a, default_list):
    """The L values (ms) of a command: --L-samples (R03: L = (F + U) / rate with F and U in tone-buffer
    samples; floor 127, ceiling 511 samples, the 255/383 points are ILLUSTRATIVE grid points, not
    bounds - V-check of R03) converted with --rate, else the --L-list."""
    if getattr(a, 'L_samples', None):
        return [round(s * 1000.0 / a.rate, 3) for s in parse_list(a.L_samples)]
    return parse_list(default_list)


def cmd_table(a):
    Ps = parse_list(a.P_list)
    Ls = l_grid(a, a.L_list)
    D = d_ms(a)
    c0 = mk(a, 1, 1)
    print('long-run seam of one image, D = %.1f ms, rate %d Hz' % (D, a.rate))
    if d_assumption_note(a):
        print(d_assumption_note(a))
    print('[h=%g h1072=%g s0=%.1f a_busy=%g a_build=%.1f F=%.1f purge=%s reengage=%g]'
          % (a.h, a.h1072, c0.s0, a.a_busy, c0.a_build, c0.F, a.purge, a.reengage))
    print('cell: N = gap of N ms at EVERY seam (locked) | gN/K = a gap of N ms at one seam in K '
          '(sliding phase) | sN = splice, N ms cut, never silent | b>N = clean butt joint for at '
          'least N chunks (the slide period is longer than the run)')
    print('%-9s' % 'P \\ L' + ''.join('%8g' % L for L in Ls))
    for P in Ps:
        print('%-9g' % P + ''.join('%8s' % longrun(mk(a, P, L))['cell'] for L in Ls))
    print('\nlong-run statistics over the L grid (seams with any silence / worst gap / mean gap):')
    for P in Ps:
        lrs = [longrun(mk(a, P, L)) for L in Ls]
        print('  P=%-6g seams with a gap %5.1f %%   worst gap %7.1f ms   mean gap %7.1f ms   '
              '%d busy ticks per chunk, %d ticks per hour'
              % (P, 100.0 * sum(x['n_gap'] for x in lrs) / sum(x['n'] for x in lrs),
                 max(x['gap_max'] for x in lrs), sum(x['gap_mean'] for x in lrs) / len(lrs),
                 int(D // P), int(3600000.0 // P)))
    return 0


def cmd_ladder(a):
    D = d_ms(a)
    print('L intervals (ms) by long-run outcome, D = %.1f ms, rate %d Hz, purge=%s; gap/cut '
          'rounded to 5 ms' % (D, a.rate, a.purge))
    if d_assumption_note(a):
        print(d_assumption_note(a))
    for P in parse_list(a.P):
        runs, prev, lo = [], None, 0.0
        L = 0.0
        while L <= a.Lmax + 1e-9:
            lr = longrun(mk(a, P, L), 60, 2)
            c = lr['cell']
            if c[0].isdigit():
                c = 'GAP %d' % (5 * round(int(c) / 5.0))
            elif c[0] == 'g':
                g, _, k = c[1:].partition('/')
                c = 'GAP %d every %s chunks' % (5 * round(int(g) / 5.0), k)
            elif c[0] == 's':
                c = 'SPLICE %d' % (5 * round(int(c[1:]) / 5.0))
            elif c.startswith('b>'):
                c = 'BUTT (clean for at least %s chunks)' % c[2:]
            else:
                c = 'BUTT (clean)'
            if c != prev:
                if prev is not None:
                    runs.append((lo, L - a.step, prev))
                prev, lo = c, L
            L += a.step
        runs.append((lo, a.Lmax, prev))
        print('P=%g (%d busy ticks per chunk, drift %+.1f ms/chunk when clean):'
              % (P, int(D // P), -drift_per_chunk(mk(a, P, 0))))
        for lo, hi, c in runs:
            print('    L %6.1f .. %6.1f   %s' % (lo, hi, c))
    return 0


def d_grid(a):
    """The D values `sens` sweeps: --d-list if given, else 0.92..1.22 x the nominal D in 2 percent
    steps (the owner heard ~14 percent more than bytes x 2 / rate, verify.md V5), plus the nominal."""
    D0 = d_ms(a)
    if a.d_list:
        return parse_list(a.d_list)
    return sorted({round(D0 * (0.92 + 0.02 * i), 3) for i in range(16)} | {round(D0, 3)})


def cmd_sens(a):
    D0 = d_ms(a)
    Ds = d_grid(a)
    Ls = parse_list(a.L_list)
    print('robustness over L %g..%g (step %g), h in %s, s0 in %s ms, a_busy in %s ms, D in %.0f..%.0f '
          'ms (%d values; nominal %.1f), rate %d Hz, purge=%s, reengage=%g'
          % (Ls[0], Ls[-1], Ls[1] - Ls[0], a.h_list, a.s0_list, a.a_list, Ds[0], Ds[-1], len(Ds),
             D0, a.rate, a.purge, a.reengage))
    print('(V01 D3: D and a_busy are swept, not fixed; the old single-D table is --d-list %g '
          '--a-list 0,1,3)' % D0)
    print('%-8s %-14s %-10s %-10s %-16s %-16s %-16s' % ('P', 'gap-free runs %', 'worst gap',
                                                     'mean gap', 'max gap<=20 ms %',
                                                     'max gap<=25 ms %', 'max gap>100 ms %'))
    for P in parse_list(a.P):
        lrs = []
        for D in Ds:
            for h in parse_list(a.h_list):
                for s0 in parse_list(a.s0_list):
                    for ab in parse_list(a.a_list):
                        for L in Ls:
                            cfg = Cfg(D, P, L, a.rate, h, a.h1072, s0, ab, None, a.F, a.purge,
                                      a.reengage, a.mixer_off)
                            lrs.append(longrun(cfg, 80, 2))
        n = len(lrs)
        print('%-8g %-14.1f %-10.1f %-10.1f %-16.1f %-16.1f %-16.1f' % (
            P, 100.0 * sum(x['n_gap'] == 0 for x in lrs) / n, max(x['gap_max'] for x in lrs),
            sum(x['gap_mean'] for x in lrs) / n,
            100.0 * sum(x['gap_max'] <= 20.0 for x in lrs) / n,
            100.0 * sum(x['gap_max'] <= 25.0 for x in lrs) / n,
            100.0 * sum(x['gap_max'] > 100.0 for x in lrs) / n))
    return 0


def cmd_dscan(a):
    """The long-run cell versus D (V01 D3): one row per D, one column per L."""
    Ls = parse_list(a.L)
    Ds = parse_list(a.d_ms_list)
    print('long-run cell versus D, rate %d Hz, P=%g, purge=%s, reengage=%g, h=%g h1072=%g a_busy=%g'
          % (a.rate, a.P, a.purge, a.reengage, a.h, a.h1072, a.a_busy))
    print('nominal D (bytes x 2 / rate) = %.1f ms; cell as in `table`' % d_ms(a))
    print('%-9s' % 'D \ L' + ''.join('%8g' % L for L in Ls))
    for D in Ds:
        print('%-9.1f' % D + ''.join('%8s' % longrun(mk(a, a.P, L, D))['cell'] for L in Ls))
    return 0


def cmd_align(a):
    Ls = parse_list(a.L)
    lo, hi = a.d_lo * 1000.0, a.d_hi * 1000.0
    rows = []
    for n in range(2, 4000):
        if not staging_ok(n):
            continue
        by = payload_bytes(n)
        if by <= 0:                      # 28 N - 268 is always a multiple of 4 (V01 D6)
            continue
        D = by * 2 * 1000.0 / a.rate
        if not (lo <= D <= hi):
            continue
        lrs = [longrun(mk(a, a.P, L, D), 60, 2) for L in Ls]
        ok = [x['n_gap'] == 0 for x in lrs]
        best = cur = 0
        for v in ok:
            cur = cur + 1 if v else 0
            best = max(best, cur)
        drift = drift_per_chunk(mk(a, a.P, 0, D))
        rows.append((best, n, by, D, 100.0 * sum(ok) / len(ok),
                     sum(x['frac_gap'] for x in lrs) / len(lrs) * 100.0, drift))
    rows.sort(key=lambda r: (-r[0], abs(r[6]), r[1]))
    step = (Ls[1] - Ls[0]) if len(Ls) > 1 else 0
    print('payload = 28 N - 268 bytes (T07), N = OUTER x INNER (both <= 255); P=%g, rate %d Hz, '
          'purge=%s; L grid %g..%g step %g ms' % (a.P, a.rate, a.purge, Ls[0], Ls[-1], step))
    print('%-6s %-9s %-10s %-12s %-16s %-12s %s' % ('N', 'bytes', 'D (ms)', 'gap-free L%',
                                                   'widest gap-free', 'seams w/gap %',
                                                   'drift ms/chunk'))
    for best, n, by, D, share, fg, drift in rows[:a.top]:
        print('%-6d %-9d %-10.1f %-12.1f %-16s %-12.1f %+.2f'
              % (n, by, D, share, '%g ms of L' % (best * step), fg, -drift))
    busy = int(rows[0][3] // a.P) if rows else 0
    print('%d lengths in range; neighbouring lengths differ by one staging period = %.1f ms of D; '
          'drift = how far the free edge slides against the tick grid per clean chunk (0 = a '
          'stable clean seam; it moves by about %d ms per ms of a_busy error). Use the ranking to '
          'compare lengths, not as a promise: h, s0, a_busy are assumptions.'
          % (len(rows), 28 * 2 * 1000.0 / a.rate, busy))
    return 0


def cmd_check(a):
    bad = 0

    def ok(name, cond, extra=''):
        nonlocal bad
        print('%-4s %s %s' % ('PASS' if cond else 'FAIL', name, extra))
        bad += 0 if cond else 1
    # 1: zero-latency corner = cavesim (cavesim-changes.md section 6: 378 ms after 2,622 ms and
    #    514 ms after 10,486 ms at P = 1000, "silence between chunks").  cavesim rounds D to ms.
    for D, want in ((2622, 378), (10486, 514)):
        cfg = Cfg(D, 1000, 0, 8000, h=0, h1072=0, s0=0, a_busy=0, a_build=0, F=0, reengage=0)
        s = simulate(cfg, 10)[-1]
        ok('zero-latency corner D=%d P=1000: silence %d ms (cavesim %d)' % (D, round(s['gap']),
                                                                         want),
           round(s['gap']) == want)
    # 2: closed form u (GAP seams that follow a GAP seam) against the simulation, over a grid
    worst = 0.0
    n_checked = 0
    for P in (25, 50, 100, 200, 1000):
        for L in (0, 16, 32, 64, 128, 200):
            for D in (2621.5, 2622, 7500, 10486):
                cfg = Cfg(D, P, L)
                sm = simulate(cfg, 20)
                for prev, s in zip(sm, sm[1:]):
                    if prev['kind'] == 'GAP' and s['kind'] == 'GAP':
                        worst = max(worst, abs(s['u'] - closed_form_u(cfg, prev['reeng'])))
                        n_checked += 1
    ok('locked-phase closed form equals the simulation on %d GAP-after-GAP seams (max error '
       '%.6f ms)' % (n_checked, worst), worst < 1e-6 and n_checked > 50)
    # 3: sliding drift closed form: u moves by -drift per BUTT-after-BUTT seam
    worst, n_checked = 0.0, 0
    for P in (50, 100, 200):
        for L in (56, 57, 64, 96, 128):
            cfg = Cfg(2621.5, P, L, purge='never')
            sm = simulate(cfg, 30)
            for prev, s in zip(sm, sm[1:]):
                if prev['kind'] == 'BUTT' and s['kind'] == 'BUTT':
                    du = ((s['u'] - prev['u'] + cfg.Pb / 2) % cfg.Pb) - cfg.Pb / 2
                    worst = max(worst, abs(du + drift_per_chunk(cfg)))
                    n_checked += 1
    ok('sliding-phase drift closed form equals the simulation on %d BUTT-after-BUTT seams (max '
       'error %.6f ms)' % (n_checked, worst), worst < 1e-6 and n_checked > 30)
    # 4: the uniform-phase table of 03 section 4.4 (c = 30), spot values
    for P, L, want in ((1000, 0, (530, 1030, 100)), (200, 64, (69, 166, 83)),
                       (100, 64, (22, 66, 66)), (50, 64, (3, 16, 32)), (25, 64, (0, 0, 0))):
        m, mx, sh = uniform_stats(P, 30.0, L)
        ok('03 table P=%d L=%d: mean/max/share = %.0f/%.0f/%.0f (03: %s)' % (P, L, m, mx, sh,
                                                                          '/'.join(map(str, want))),
           abs(m - want[0]) <= 1 and abs(mx - want[1]) <= 1 and abs(sh - want[2]) <= 1)
    # 5: the staging grid: 60,100 B and 90,004 B are valid, 60,000 B is not (T07)
    ok('staging grid: 60,100 B (N=2156) and 90,004 B (N=3224) valid; N=2153 (asks for 60,016 B, a '
       'prime, no OUTER x INNER pair) not',
       staging_ok(2156) and staging_ok(3224) and not staging_ok(2153)
       and payload_bytes(2156) == 60100 and payload_bytes(3224) == 90004)
    # 6: proven constants
    ok('copy period 16 ms at 8 kHz, 64 ms at 2 kHz (T02, kalsim)',
       abs(copy_period_ms(8000) - 16.0) < 1e-9 and abs(copy_period_ms(2000) - 64.0) < 1e-9)
    ok('tone buffer 255 usable samples = 31.9 ms at 8 kHz, 127.5 ms at 2 kHz',
       abs(buf_ms(8000) - 31.875) < 1e-9 and abs(buf_ms(2000) - 127.5) < 1e-9)
    # 7: a poll no longer than L - c is gap free (and the purge does not make a gap at P=25, L=100)
    cfg = Cfg(2622, 25, 100)
    ok('P=25, L=100, c=21: every seam of a 60-chunk run is gap free',
       all(s['gap'] < 1e-9 for s in simulate(cfg, 60)))
    # 8: the purge makes a gap that skipping it does not (the 20 ms of P=200, L=64)
    lp0 = longrun(Cfg(2621.5, 200, 64, reengage=0), 60, 2)
    lp = longrun(Cfg(2621.5, 200, 64), 60, 2)
    ln = longrun(Cfg(2621.5, 200, 64, purge='never'), 60, 2)
    ok('purge-made gap: P=200, L=64 gaps %.1f ms (%.1f with --reengage 0) at %d of %d seams with the '
       'purge; without it the seam slides and only %d of %d seams gap (one per ~%d chunks)'
       % (lp['gap_max'], lp0['gap_max'], lp['n_gap'], lp['n'], ln['n_gap'], ln['n'],
          round(ln['period'] or 0)),
       abs(lp0['gap_max'] - 20.0) < 1e-6 and abs(lp['gap_max'] - 27.0) < 1e-6
       and lp['n_gap'] == lp['n'] and 0 < ln['n_gap'] < ln['n'])
    # 9: the purge-made silence formula G = max(0, (c - h1072) - max(0, R - F)) for a tick in the tail
    worst, n_checked = 0.0, 0
    for P in (25, 50, 100, 200, 1000):
        for L in (0, 16, 32, 64, 128, 200):
            for h, s0, F in ((5, 16, 31.875), (2, 2, 31.875), (5, 16, 16), (2, 2, 16)):
                cfg = Cfg(2621.5, P, L, 8000, h=h, s0=s0, F=F)
                for s in simulate(cfg, 30):
                    R = s['E_prev'] - (s['tick'] + cfg.h1072)
                    if R > 0:
                        base = max(0.0, (cfg.c - cfg.h1072) - max(0.0, R - cfg.F))
                        want = base + (cfg.reengage if base >= cfg.mixer_off - 1e-9 and base > 0
                                       else 0.0)
                        worst = max(worst, abs(s['gap'] - want))
                        n_checked += 1
    ok('purge-made silence G = base + reengage*(base >= 6 ms), base = max(0, (c - h1072) - max(0, '
       'R - F)), equals the simulation on %d in-tail ticks (max error %.6f ms)'
       % (n_checked, worst), worst < 1e-6 and n_checked > 100)
    # 10: the re-engagement (V01 D4): the default gap is 27 ms, F=16 gives 19.5, the low-c bracket stays 3
    g = lambda **k: simulate(Cfg(2621.5, 200, 64, **k), 10)[-1]['gap']
    ok('re-engagement: P=200 L=64 default gap %.1f (20 + 7), F=16 %.1f, low-c bracket (h=s0=2) %.1f '
       '(below the 6 ms mixer-off threshold, no addition)' % (g(), g(F=16), g(h=2, s0=2)),
       abs(g() - 27.0) < 1e-6 and abs(g(F=16) - 19.5) < 1e-6 and abs(g(h=2, s0=2) - 3.0) < 1e-6)
    # 11: D matters (V01 D3): the P=200 ladder rung at the nominal D is not the rung at D=2990
    c1 = longrun(Cfg(2621.5, 200, 100), 60, 2)['cell']
    c2 = longrun(Cfg(2990.0, 200, 100), 60, 2)['cell']
    ok('D-dependence: P=200 L=100 reads %s at D=2621.5 and %s at D=2990 (the heard gap reads c only '
       'for the nominal D)' % (c1, c2), c1 != c2)
    # 12: a slow slide is not reported clean (V01 D5): purge never, tiny drift
    lr = longrun(Cfg(2621.5 + 0.25, 200, 100, a_busy=0.0, purge='never'), 60, 2)
    ok('long-run horizon: a 0.25 ms/chunk slide shows a gap (cell %s), not a clean "b"' % lr['cell'],
       lr['cell'] != 'b')
    print('NOTE: these checks are CONSTRUCTION checks (the code against its own closed forms and '
          'identities); they prove the algebra, not the speaker. The evidence about the loop images is '
          'the word scan and the two --mem loops of T03, not this list (V01 D9).')
    print('seammodel self-check: %s' % ('OK' if not bad else '%d FAILED' % bad))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)

    def common(p):
        p.add_argument('--size', type=int, default=10486, help='chunk file bytes (default '
                       'rphrases_us 10,486)')
        p.add_argument('--rate', type=int, default=8000)
        p.add_argument('--d-ms', type=float, help='chunk length override, ms')
        p.add_argument('--h', type=float, default=DEFAULTS['h'])
        p.add_argument('--h1072', type=float, default=DEFAULTS['h1072'])
        p.add_argument('--s0', type=float, default=None, help='default: one copy period')
        p.add_argument('--a-busy', type=float, default=DEFAULTS['a_busy'])
        p.add_argument('--a-build', type=float, default=None, help='default: h + 1')
        p.add_argument('--F', type=float, default=None, help='purge cut ceiling, default 255 '
                       'samples in ms')
        p.add_argument('--purge', choices=('always', 'never'), default='always')
        p.add_argument('--chunks', type=int, default=16)
        p.add_argument('--reengage', type=float, default=REENGAGE_MS,
                       help='mixer re-engagement added to a silence of --mixer-off ms or more '
                            '(default %g; 0 restores the pre-round-3 numbers)' % REENGAGE_MS)
        p.add_argument('--mixer-off', type=float, default=MIXER_OFF_MS,
                       help='empty-port time after which the mix op releases (default %g)'
                            % MIXER_OFF_MS)
    s = sub.add_parser('seam')
    common(s)
    s.add_argument('--P', type=float, required=True)
    s.add_argument('--L', type=float, required=True)
    s = sub.add_parser('table')
    common(s)
    s.add_argument('--P-list', default='1000,500,200,100,50,25')
    s.add_argument('--L-list', default='0,16,32,48,64,96,128,200')
    s.add_argument('--L-samples', default=None,
                   help='L in tone-buffer samples (converted with --rate), e.g. 127,255,383,511 '
                        '(R03: floor 127, ceiling 511 are derived and conditional; 255 and 383 are '
                        'illustrative grid points, not bounds). Overrides --L-list.')
    s = sub.add_parser('align')
    common(s)
    s.add_argument('--P', type=float, required=True)
    s.add_argument('--L', default='0:200:8', help='L grid lo:hi:step or a list')
    s.add_argument('--d-lo', type=float, default=14.0, help='shortest D, s')
    s.add_argument('--d-hi', type=float, default=24.0, help='longest D, s')
    s.add_argument('--top', type=int, default=12)
    s = sub.add_parser('ladder')
    common(s)
    s.add_argument('--P', default='200,100,50')
    s.add_argument('--Lmax', type=float, default=260.0)
    s.add_argument('--step', type=float, default=0.5)
    s = sub.add_parser('sens')
    common(s)
    s.add_argument('--P', default='1000,200,100,50')
    s.add_argument('--L-list', default='0:260:4')
    s.add_argument('--h-list', default='2,5,10,20,40')
    s.add_argument('--s0-list', default='0,16,32')
    s.add_argument('--a-list', default='0,1,3,5', help='a_busy values, ms')
    s.add_argument('--d-list', default=None, help='D values, ms (default: 0.92..1.22 x nominal, '
                    '16 values; V01 D3)')
    s = sub.add_parser('dscan')
    common(s)
    s.add_argument('--P', type=float, required=True)
    s.add_argument('--L', default='0,16,32,64,128')
    s.add_argument('--d-ms-list', default='2400:3200:50', help='D grid lo:hi:step, ms')
    sub.add_parser('check')
    a = ap.parse_args()
    return {'seam': cmd_seam, 'table': cmd_table, 'align': cmd_align, 'ladder': cmd_ladder,
            'sens': cmd_sens, 'dscan': cmd_dscan, 'check': cmd_check}[a.cmd](a)


if __name__ == '__main__':
    sys.exit(main())
