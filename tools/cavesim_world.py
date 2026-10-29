#!/usr/bin/env python3
"""cavesim_world: the clocked "world" model behind cavesim's --world / --loop / --press flags.

Added by offline workflow B2 (2026-10-10) for the loop / stop / material probes of
docs/deep/offline-2026-10-10/DESIGN.md (probes 179..186).  Everything here is OPT-IN: cavesim
imports this module only when one of the new flags is given, and every pre-existing flag
keeps its exact output (tools/cavesim_regress.py diffs the battery).

WHAT IS MODELLED  (every line is a MODEL, not a measurement; the status of each assumption
is tabulated in docs/deep/offline-2026-10-10/cavesim-changes.md)

  * a virtual clock in milliseconds and an event queue: button presses delivered to the cave
    entry (AL = the event, the 0x00e46 hook), MessageSendLater messages delivered to the
    cave's TaskData handler (AL = task, AH = MessageId) at now + delay, DSP messages
    (MESSAGE_FROM_KALIMBA) delivered to the handler when the cave owns the Kalimba mailbox;
  * MessageCancelFirst (TRUE iff a matching message is pending; removes it) and
    MessageFlushTask (returns how many it removed);
  * port 3 and the ADPCM transform on it: a chunk is created by TransformAdpcmDecode, started
    by TransformStart, plays for (file bytes x 2 samples/byte / rate), reaches source EOF,
    reaches its audible end `--tail-ms` later, and is freed by firmware at one of those two
    edges (`--free-edge`).  TransformFromSink reads nonzero from creation until the free edge.
    The DSP sends 0x1080 `--tone-end-ms` after the audible end; with the music PAUSED the DSP
    is unloaded `--unload-ms` after that (KalimbaSendMessage then returns FALSE);
  * the hidden rate latch (probe177: the first chunk after the stock's last tone plays at
    the stock's 8 kHz, a sent 0x1072 rate is honoured from the next chunk: `--latch late`) and
    the level word (0x1072 word b: bit 1 set -> cbops.shift 4, clear -> 7, honoured at once);
  * the file system: FileFind by name over a small tree (the real internal files plus
    `--fs-add`), including files that exist only on partition 2 and become visible according
    to `--p2-automount` / PartitionMountFilesystem(1, 2); StreamFileSource / SourceSize /
    SourceMap / SourceDrop / SourceClose with a configurable window (`--src-window`);
  * partition 2 census keys and the overwrite-sink write bookkeeping;
  * the port-3 RULES, checked at every trap and reported at the end:
        R1  KalimbaSendMessage(0x1072) while port 3 is audible/busy        (probe173)
        R2  TransformStop / TransformDisconnect / StreamDisconnect on a RUNNING port-3
            transform                                                       (probes 174/175)
        R3  SPEAK (prompt engine) while port 3 is ours                      (probe173)
        R4  a second TransformAdpcmDecode / TransformStart on a busy port   (probe173)
        R5  MessageSendLater to the cave below the poll floor (`--poll-floor`, default 50 ms)
        R6  two or more cave messages pending at once (a duplicate chain)
    plus warnings (SourceDrop past SourceSize, SourceMap beyond the model's RAM window, a
    transform created and never started, file sources never closed).

FAILURE WORLDS (J-T3, 2026-10-12; docs/deep/firmware-study-2026-10-12/T03-cavesim-and-seam-model.md;
every one opt-in and absent from every legacy run):

  --cancel never|always     MessageCancelFirst returns FALSE (never finds the message) / TRUE
                            (nothing removed): the two STOP failure worlds of 02-loop-forever
  --ksink-after-unload zero StreamKalimbaSink(3) returns 0 while no DSP is loaded (the
                            counterfactual to the n=1 observation of a nonzero return)
  --wrong-dsp MS:DUR        a TTS prompt or call DSP replaces sbc_decoder for DUR ms (T04's DSP
                            swap): the chain is cut, the gate still reads TRUE, rule W1 fires if
                            the cave sends 0x1072 or builds into it
  --mid-chunk-1072 MS[:b]   the STOCK sends 0x1072(8000, b) at MS (T04: fn_31a7c, via a stock
                            tone): purge cut, level switch (b=0 is +18 dB over b=2), a stale
                            ksink task; it does NOT go through the cave, so R1 stays silent
  --foreign-tone MS:DUR     a stock tone (fn_1c17f) disposes our chain at MS and holds port 3
                            for DUR ms (differs from --stock-prompt, which is only a busy window)
  --mem-at MS:ADDR=VAL      a timed RAM write (a sinkState change, ADDR 59e, ADK sink_states.h)
  --voice-field             the stock's centre-long (0x4004) arm toggles an assistant "field" and
                            sends a voice-recognition enable (odd) / disable (even) request EVEN
                            WHEN THE CAVE SWALLOWS THE EVENT; while the field is set a centre SHORT
                            press (--short-id, default 0x4045) is converted by the stock to 0x4004
                            (T04 E4/E7/C10: decode proven, runtime values unobserved: hypothesis)
  --field-at MS:0|1         an HFP status message sets/clears the field (T04 M4)

WHAT IT CANNOT TELL YOU: whether the firmware agrees.  The rules encode what hardware has
shown to be harmful (docs/deep/offline-2026-10-10/verify.md V1..V11); the free edge, the
unload latency, the latch and the window size are parameters precisely because they are not
known offline.
"""
import heapq
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERNAL = os.path.join(ROOT, 'firmware/bose/extracted/internal_fs')

# the internal file system as `tools/csrdfu.py extract` shows it (docs/deep brief): path -> size
DEFAULT_FS = {
    'NowSpeakTTS/data_us': 219528,
    'NowSpeakTTS/NowSpeakTTS.kap': 31076,
    'tts/rphrases_us': 10486,
    'sbc_decoder/sbc_decoder.kap': 69994,
}
SRC_MAP_BASE = 0x4000          # where SourceMap puts the words (below the const window)
SRC_MAP_CAP = 0x7400 - 0x4000  # 13,312 words fit between SRC_MAP_BASE and the const window
SRC_HANDLE0 = 0x5FC0           # the first StreamFileSource handle (cavesim's legacy value)
TF_HANDLE0 = 0x5EC0            # the first TransformAdpcmDecode handle (legacy value)
FOREIGN_TF = 0x7001            # TransformFromSink's answer while a STOCK prompt holds port 3
STOCK_RATE = 8000
FN_REPLAY = 0x189FB            # the stock call the hook replays for every event but 0x4004


def _basename(p):
    return p.rsplit('/', 1)[-1]


class Chunk:
    """One ADPCM chunk on port 3 (created -> started -> eof -> audible end)."""
    def __init__(self, k, handle, src, ksink, now):
        self.k, self.handle, self.src, self.ksink = k, handle, src, ksink
        self.created = now
        self.start = self.eof = self.end = self.freed = None
        self.rate = self.b = self.dur = None
        self.ended = False
        self.cut = None            # 'bt-teardown' if ended early
        self.gen = 0               # J-T3: bumped when eof/end are rescheduled (stale events drop)
        self.b_now = None          # J-T3: the level word now in force (a stock 0x1072 may change it)
        self.level_log = []        # (t, old_b, new_b)
        self.splices = []          # (t, ms of tail cut by a purge)

    def holds(self, now):
        """TransformFromSink would read nonzero."""
        return self.freed is None or now < self.freed

    def audible(self, now):
        return self.start is not None and (self.end is None or self.start <= now < self.end)


class World:
    def __init__(self, ctx, vm, trapnums, names, args, state, dsp):
        self.ctx, self.vm, self.trapnums, self.names = ctx, vm, trapnums, names
        self.args, self.state, self.dsp = args, state, dsp
        self.fail = set(args.fail)
        self.now = 0
        self.seq = 0
        self.queue = []                 # heap of (t, prio, seq, ev)
        self.chunks = []
        self.violations = []
        self.waived = []
        self.warnings = []
        self.spoken = []                # (t, id)
        self.notes = []                 # lines printed after the current run's trap list
        self.sources = {}               # handle -> dict(path,size,pos,closed,chunk)
        self.n_src = 0
        self.transforms = {}            # handle -> Chunk
        self.ksink = None
        self.rate_sent = None           # last 0x1072 word a
        self.rate_active = args.stock_rate
        self.level_b = 0                # the stock sends b = 0 for its own tones
        self.sent_1072 = []             # (t, a, b)
        self.foreign = [tuple(int(x) for x in s.split(':')) for s in args.stock_prompt]
        self.replayed = False
        self.swallowed = 0
        self.replays = 0
        self.p2 = {'mounted': args.p2_mounted == 1 if args.p2_mounted is not None else None,
                   'open': False, 'closed': False, 'bytes': 0, 'flushes': 0, 'claims': 0,
                   'digest': None, 'sink': None, 'erased': False, 'mounted_by_cave': False}
        self.fs = {}
        for path, size in DEFAULT_FS.items():
            self.fs[path] = {'size': size, 'vis': 'root', 'src': None}
        for spec in args.fs_add:
            name, _, rest = spec.partition('=')
            val, _, vis = rest.partition(':')
            src = None
            if val.startswith('@'):
                src = val[1:]
                size = os.path.getsize(src)
            else:
                size = int(val, 0)
            self.fs[name] = {'size': size, 'vis': vis or 'root', 'src': src}
        self.handles = {}               # path -> dir/file handle
        self.paths = {1: ''}            # handle -> path ('' = root)
        self.pinfo = {}
        for spec in args.pinfo:         # PART:KEY=VAL
            pk, _, v = spec.partition('=')
            p, _, k = pk.partition(':')
            self.pinfo[(int(p), int(k))] = int(v, 0)
        self.chunk_ms = ([int(x) for x in args.chunk_ms.split(',')]
                         if args.chunk_ms and args.chunk_ms != 'auto' else None)
        self.task = None                # the cave's TaskData data address (set by cavesim)
        self.press_event = 0x4004
        self.loop_stop_reason = None
        self.started_after_cap = False
        # ---- J-T3 failure worlds (all opt-in; the defaults leave every legacy run untouched)
        self.cancel_mode = args.cancel                  # None | 'never' | 'always'
        self.wrong_windows = [self._ms_dur(s) for s in args.wrong_dsp]
        self.foreign_tones = [self._ms_dur(s) for s in args.foreign_tone]
        self.foreign.extend(self.foreign_tones)         # the busy window; the chain cut is an event
        self.audio_busy = 0                      # probe210: the stock audio-busy word (--audio-busy)
        self.busy_log = []                       # (t, value) of every SetAudioBusy
        self.pending_disc = False                # a disconnect parked on the busy word
        self.mid1072 = []
        for s in args.mid_chunk_1072:
            t, _, b = s.partition(':')
            self.mid1072.append((int(t), int(b, 0) if b else 0))
        self.msg_at = []
        for s_ in getattr(args, 'msg_at', []):
            t_, _, m_ = s_.partition(':')
            self.msg_at.append((int(t_), int(m_, 16)))
        self.dspmsg_at = []
        for s_ in getattr(args, 'dspmsg_at', []):
            t_, _, m_ = s_.partition(':')
            self.dspmsg_at.append((int(t_), int(m_, 16)))
        # ---- BF (2026-10-19): opt-in stock-world model (--tone-at / --tts-at); see docs/deep/material-2026-10-19/BF-stock-world-model.md
        self.tone_at = [int(x) for x in getattr(args, 'tone_at', [])]
        self.tts_at = [int(x) for x in getattr(args, 'tts_at', [])]
        self.stock_world = bool(self.tone_at or self.tts_at)
        self.stock_queue = []                    # parked stock sounds ('tone' / 'tts', t requested), served in creation order when audio-busy is 0
        self.stock_log = []                      # (t, text)
        self.rebooted = None                     # t of the modelled VM fault (PanicNull at 0x230be), or None
        self.mem_at = []
        for s in args.mem_at:
            t, _, rest = s.partition(':')
            ad, _, v = rest.partition('=')
            self.mem_at.append((int(t), int(ad, 16), int(v, 16) & 0xFFFF))
        self.field = 0                  # the stock voice-recognition field (T04), --voice-field
        self.short_id = int(args.short_id, 16)
        self.converted = 0
        self.requests = []              # (t, 'enable'|'disable'): predicted stock requests
        self.field_at = []
        for s in args.field_at:
            t, _, v = s.partition(':')
            self.field_at.append((int(t), int(v)))
        self.wrong_now = False
        self.wrong_since = None
        self.stale_sink_task = False
        self.hazard_notes = []          # (t, text): hearing / state hazards of the failure worlds
        # ---- round 3 (T08 follow-up 1, the 184 rehearsal without a monkeypatch); all opt-in
        self.size_calls = 0             # SourceSize trap calls so far (--size-dries-after)
        self.p2_capture = []            # bytes flushed to the p2 sink, one entry per flush (--p2-capture)
        self.last_map = 0               # SinkMap(p2 sink) return (the claim buffer base) and
        self.last_claim = 0             # SinkClaim(p2 sink) return (its offset), for the capture
        # ---- R1 / probe196 (2026-10-13): the raw partition source (trap 0xD3), all opt-in
        self.raw_sources = {}           # handle -> dict(data,pos,closed,drops,maps)
        self.raw_calls = []             # (device, partition) of every PartitionGetRawSerialSource call
        self.raw_drops = 0
        self.getinfo_n = 0              # PartitionGetInfo calls so far (--getinfo-fail-at)
        self.synth_calls = {}           # trap number -> calls through a cave-SYNTHESISED stub
        self.raw_exhausted = 0          # R2: raw sources that closed themselves by being drained
        self.claim_n = 0                # R2: SinkClaim / SinkFlush call counters, the VmGetClock offset, digest result
        self.flush_n = 0
        self.clock_extra = 0
        self.digest_ok = True

    @staticmethod
    def _ms_dur(spec):
        a, _, d = spec.partition(':')
        return int(a), int(d)

    # ------------------------------------------------------------------ small helpers
    def say(self, msg):
        self.notes.append(msg)

    def violate(self, rule, msg):
        if rule in self.args.allow:
            self.waived.append((self.now, rule, msg))
            self.notes.append('waived %s (--allow): %s' % (rule, msg))
            return
        self.violations.append((self.now, rule, msg))
        self.notes.append('!! %s: %s' % (rule, msg))

    def warn(self, msg):
        self.warnings.append((self.now, msg))
        self.notes.append('warn: %s' % msg)

    def push(self, t, prio, ev):
        self.seq += 1
        ev['t'], ev['seq'] = t, self.seq
        heapq.heappush(self.queue, (t, prio, self.seq, ev))

    def pending(self, task=None):
        return [e for (_t, _p, _s, e) in self.queue
                if e['kind'] == 'msg' and not e.get('dead') and (task is None or e['task'] == task)]

    def rd_data(self, a):
        """A data word, const addresses read from the PATCHED code image (vm.const is the
        unpatched copy; a carried string lives in the patched window)."""
        c = self.ctx
        a &= 0xFFFF
        if a >= c.CONST_DATA_BASE and c.CODE_WORDS + (a - c.CONST_DATA_BASE) < len(self.vm.code):
            return self.vm.code[c.CODE_WORDS + (a - c.CONST_DATA_BASE)] & 0xFFFF
        return self.vm.rd(a)

    def call_base(self, base, trap, ahal, a2):
        if base is None:
            return self.vm.AH, self.vm.AL
        return base(trap, ahal, a2) if callable(base) else base

    # ------------------------------------------------------------------ port-3 state
    def foreign_busy(self, t):
        return any(a <= t < a + d for a, d in self.foreign)

    # ------------------------------------------------------------------ BF: the stock world (opt-in: --tone-at, --tts-at)
    def stock_request(self, what):
        """A stock sound is requested. Parked (conditional on the audio-busy word) while it is non-zero, served at once otherwise."""
        if self.audio_busy != 0:
            self.stock_queue.append(what)
            self.stock_log.append((self.now, '%s requested, PARKED (audio-busy %#06x)' % (what, self.audio_busy)))
            self.say_line('t=%6d  STOCK %s requested: PARKED on the audio-busy word (%#06x)' % (self.now, what.upper(), self.audio_busy))
        else:
            self.stock_start(what)

    def stock_serve(self):
        while self.stock_queue and self.audio_busy == 0 and self.rebooted is None:
            self.stock_start(self.stock_queue.pop(0))

    def stock_start(self, what):
        a, vm = self.args, self.vm
        if what == 'tone':
            if vm.rd(0x6D1) & 0x8000:
                self.rebooted = self.now
                self.stock_log.append((self.now, 'tone served: @0x6d1 bit 15 SET -> REBOOT'))
                self.say_line('t=%6d  STOCK TONE served (AQ 4.4): fn_1f0a4 refuses, @0x6d1 bit 15 is SET -> fn_23016 PanicNull at 0x230be: MODELLED REBOOT (chip reset)' % self.now)
                return
            self.audio_busy = 0xBD4E                 # fn_23016 0x23027: SetAudioBusy(0xBD4E)
            self.busy_log.append((self.now, 0xBD4E))
            vm.wr(0x6D1, vm.rd(0x6D1) | 0x8000)      # the tone's own fn_1f0a4 connect sets the flag
            self.stock_log.append((self.now, 'tone served: bit 15 clear -> connects'))
            self.say_line('t=%6d  STOCK TONE served (AQ 4.4): @0x6d1 bit 15 clear -> connects, audio-busy := 0xbd4e for %d ms' % (self.now, a.tone_ms))
            self.push(self.now + a.tone_ms, 0, {'kind': 'stock_end', 'what': 'tone'})
        else:
            self.audio_busy = 0xB195                 # fn_1dbdc: the TTS word engine owns the busy word (AC 3)
            self.busy_log.append((self.now, 0xB195))
            n = self.cut_chunks('stock TTS prompt (--tts-at)')
            self.dsp.update(loaded=False, plugin=None, go=False)
            self.vm.chain_alive = False            # BH: the stock KalimbaLoad(NowSpeakTTS) disposes every chain (BG 0.1 item 3)
            self.rate_active, self.rate_sent = a.stock_rate, None
            self.stock_log.append((self.now, 'tts served: DSP and codec sinks torn down, bit 15 left as it was'))
            self.say_line('t=%6d  STOCK TTS served (AC 6.3, 8.4): our DSP is replaced (%d chain(s) cut), codec sinks closed, StreamKalimbaSink(3) -> 0, @0x6d1 bit 15 UNTOUCHED (%#06x), for %d ms'
                          % (self.now, n, self.vm.rd(0x6D1), a.tts_ms))
            self.push(self.now + a.tts_ms, 0, {'kind': 'stock_end', 'what': 'tts'})

    def stock_finish(self, what):
        vm = self.vm
        if what == 'tone':
            vm.wr(0x6D1, vm.rd(0x6D1) & 0x7FFF)      # fn_231b3 -> fn_1f12b clears bit 15 (the tone's own connect set it)
            if self.dsp['loaded']:
                self.say_line('t=%6d  STOCK TONE ends: KalimbaPowerOff on the loaded DSP (fn_231b3; hypothesis: probe241 stall class, NOT modelled)' % self.now)
        self.audio_busy = 0
        self.busy_log.append((self.now, 0))
        self.say_line('t=%6d  STOCK %s ends: audio-busy := 0, @0x6d1 = %#06x' % (self.now, what.upper(), vm.rd(0x6D1)))
        self.stock_serve()

    def release_parked(self, why):
        if self.stock_world and self.rebooted is None:
            self.stock_serve()
        if self.pending_disc and self.audio_busy == 0:
            self.pending_disc = False
            self.say_line('t=%6d  the parked plugin disconnect is delivered (%s): the DSP will unload' % (self.now, why))
            self.push(self.now + self.args.unload_ms, 0, {'kind': 'unload', 'why': 'parked disconnect'})

    def busy_audible(self, t=None):
        t = self.now if t is None else t
        return self.foreign_busy(t) or any(c.audible(t) for c in self.chunks)

    def reads_busy(self, t=None):
        t = self.now if t is None else t
        return self.foreign_busy(t) or any(c.holds(t) for c in self.chunks)

    def running_chunk(self):
        for c in reversed(self.chunks):
            if c.audible(self.now):
                return c
        return None

    # ------------------------------------------------------------------ file system
    def _visible(self, rec):
        v = rec['vis']
        if v == 'root':
            return True
        if v == 'never':
            return False
        if v == 'p2':
            written = (self.p2['closed'] and self.p2['digest'] == 3) or self.args.p2_preloaded
            if not written:
                return False
            return bool(self.args.p2_automount or self.p2['mounted_by_cave'])
        return False

    def find(self, dirh, name):
        base = self.paths.get(dirh)
        if base is None:
            return 0
        full = (base + '/' + name) if base else name
        if full in self.fs and self._visible(self.fs[full]):
            return self._handle(full)
        prefix = full + '/'
        if any(p.startswith(prefix) and self._visible(r) for p, r in self.fs.items()):
            return self._handle(full)
        return 0

    def _handle(self, path):
        if path not in self.handles:
            h = 0x5D00 + len(self.handles) + 1
            self.handles[path] = h
            self.paths[h] = path
        return self.handles[path]

    def file_bytes(self, path):
        rec = self.fs[path]
        src = rec['src']
        for cand in ([src] if src else []) + [os.path.join(INTERNAL, _basename(path))]:
            if cand and os.path.exists(cand):
                with open(cand, 'rb') as f:
                    return f.read()
        return bytes(rec['size'])

    # ------------------------------------------------------------------ sources
    def src_size(self, s):
        rem = s['size'] - s['pos']
        w = self.args.src_window
        n = min(rem, w) if w else rem
        return max(0, min(n, 0xFFFF))

    def src_map(self, s):
        self.last_mapped = s                          # E1 (--map-live): the source whose map is the live window
        n = self.src_size(s)
        start = s['pos']
        sh = getattr(self.args, 'map_shift_from', None)
        if sh:                                        # D1: from POS on the map presents position + SHIFT
            p0, sv = sh.split(':')
            if s['pos'] >= int(p0, 0):
                start = max(0, s['pos'] + int(sv, 0))
        data = s['data'][start:start + n]
        if self.args.src_unpacked:
            # ONE BYTE PER 16-BIT ELEMENT (T08 UNIT RULE: fn_1edf9 0x1ee1b reads (p[0]&0xff)<<8 |
            # (p[1]&0xff); fn_185c3 tests p[0] == 3; StreamRegionSource was seen delivering a byte
            # per word, FACTS N012). The window semantics (SourceSize/SourceDrop) are unchanged.
            cap = self.args.src_cap
            if len(data) > cap and not getattr(self, '_capwarned', False):
                self._capwarned = True
                self.warn('SourceMap: %d mapped elements but --src-cap maps only the first %d; a '
                          'cave indexing beyond reads stale words' % (len(data), cap))
            junk = 0x5A00 if getattr(self.args, 'src_hijunk', False) else 0
            hib = getattr(self.args, 'src_hibyte', False)
            lead = getattr(self.args, 'map_lead', 0) or 0
            for _r in getattr(self.args, 'map_lead_rule', []) or []:      # F1: alignment-dependent lead
                _m, _rm, _n = (int(x, 0) for x in _r.split(':'))
                if s['pos'] % _m == _rm:
                    lead = _n
                    break
            for _r in getattr(self.args, 'map_lead_last', []) or []:      # G1: the last drop's size
                _sz, _n = (int(x, 0) for x in _r.split(':'))
                if s.get('lastdrop') == _sz:
                    lead = _n
                    break
            for _r in getattr(self.args, 'map_lead_ndrop', []) or []:     # G1: the number of drop calls so far
                _c, _n = (int(x, 0) for x in _r.split(':'))
                if s.get('ndrop', 0) >= _c:
                    lead = _n
                    break
            els = [0xDD] * lead + [(b << 8) if hib else (b | junk) for b in data]
            if lead and getattr(self.args, 'map_trunc', False):
                els = els[:n]                          # R3b: SourceSize elements in all
            for i, v in enumerate(els[:cap]):
                self.vm.wr(SRC_MAP_BASE + i, v)
            return SRC_MAP_BASE
        le = self.args.src_endian == 'le'
        words = []
        for i in range(0, len(data), 2):
            b0 = data[i]
            b1 = data[i + 1] if i + 1 < len(data) else 0
            words.append((b0 | (b1 << 8)) if le else ((b0 << 8) | b1))
        if len(words) > SRC_MAP_CAP:
            if not getattr(self, '_capwarned', False):
                self._capwarned = True
                self.warn('SourceMap: %d mapped words but the model maps only the first %d '
                          '(RAM below the const window); a cave indexing beyond reads zeros'
                          % (len(words), SRC_MAP_CAP))
            words = words[:SRC_MAP_CAP]
        for i, v in enumerate(words):
            self.vm.wr(SRC_MAP_BASE + i, v)
        return SRC_MAP_BASE

    # ------------------------------------------------------------------ installing the traps
    def install(self):
        vm, tn, w = self.vm, self.trapnums, self
        a = self.args

        def wrap(name, fn):
            t = tn.get(name)
            if t is None:
                return
            base = vm.STUB_RET.get(t)

            def inner(trap, ahal, a2, base=base, fn=fn):
                return fn(trap, ahal, a2, lambda: w.call_base(base, trap, ahal, a2))
            vm.STUB_RET[t] = inner

        def AL(x): return x & 0xFFFF
        def AH(x): return (x >> 16) & 0xFFFF
        def s0(a2): return (a2 >> 16) & 0xFFFF
        def s1(a2): return a2 & 0xFFFF

        # ---- port 3 ---------------------------------------------------------------
        def streamkalimbasink(trap, ahal, a2, base):
            if (a.ksink_after_unload == 'zero' or w.stock_world) and not getattr(a, 'chain_model', False) and AL(ahal) == 3 and not w.dsp['loaded']:
                w.say('StreamKalimbaSink(3) -> 0 (--ksink-after-unload zero: no DSP is loaded)')
                return (0, 0)
            r = base()
            if AL(ahal) == 3 and (r[1] & 0xFFFF):
                w.ksink = r[1] & 0xFFFF
            return r
        wrap('StreamKalimbaSink', streamkalimbasink)

        def transformfromsource(trap, ahal, a2, base):
            # BH --chain-model: the stack's TransformFromSource(source of Kalimba port p) is nonzero iff a node with that source exists (BG 3.3, harness BH section 2)
            if not getattr(a, 'chain_model', False): return base()
            alive = bool(getattr(vm, 'chain_alive', False))
            w.say('TransformFromSource -> %s (--chain-model: the DAC link chain %s)' % ('handle' if alive else '0', 'is alive' if alive else 'is gone'))
            return (0, 0x1C19) if alive else (0, 0)
        wrap('TransformFromSource', transformfromsource)

        def transformfromsink(trap, ahal, a2, base):
            r = base()
            if (r[1] & 0xFFFF) == 0:
                w.say('TransformFromSink -> 0 (forced free: --fail / --fail-after)')
                return (0, 0)
            if w.foreign_busy(w.now):
                return (0, FOREIGN_TF)
            for c in reversed(w.chunks):
                if c.holds(w.now):
                    return (0, c.handle)
            return (0, 0)
        wrap('TransformFromSink', transformfromsink)

        def adpcm(trap, ahal, a2, base):
            r = base()
            if (r[1] & 0xFFFF) == 0:
                return r
            src, sink = AL(ahal), AH(ahal)
            if w.wrong_now:
                w.violate('W1', 'TransformAdpcmDecode on port 3 of a DSP that is not sbc_decoder '
                                '(--wrong-dsp window: a prompt or call DSP is resident)')
            if w.busy_audible() or any(c.holds(w.now) and c.start is not None
                                       for c in w.chunks):
                w.violate('R4', 'TransformAdpcmDecode on port 3 while a transform still holds it '
                                '(a second transform on a held sink, the probe173 condition)')
            h = TF_HANDLE0 + len(w.chunks)
            c = Chunk(len(w.chunks) + 1, h, src, sink, w.now)
            w.chunks.append(c)
            w.transforms[h] = c
            if src in w.sources:
                w.sources[src]['chunk'] = c
            return (0, h)
        wrap('TransformAdpcmDecode', adpcm)

        def tstart(trap, ahal, a2, base):
            r = base()
            if (r[1] & 0xFFFF) == 0:
                return r
            c = w.transforms.get(AL(ahal))
            if c is None:
                w.warn('TransformStart(%#06x): not a transform this run created' % AL(ahal))
                return r
            if c.start is not None:
                w.violate('R4', 'TransformStart on a transform that is already running')
                return r
            w.start_chunk(c)
            return r
        wrap('TransformStart', tstart)

        def tstop(trap, ahal, a2, base):
            c = w.transforms.get(AL(ahal))
            if c is not None and c.audible(w.now):
                w.violate('R2', 'TransformStop on a RUNNING port-3 transform (probes 174/175 '
                                'restarted the speaker doing this)')
            elif c is not None:
                w.say('TransformStop on a finished transform (model: tolerated; probe151 did '
                      'the trio on an inactive transform for ~55 ticks)')
            return base()
        wrap('TransformStop', tstop)

        def tdisc(trap, ahal, a2, base):
            c = w.transforms.get(AL(ahal))
            if c is not None and c.audible(w.now):
                w.violate('R2', 'TransformDisconnect on a RUNNING port-3 transform')
            elif c is not None:
                w.say('TransformDisconnect on a finished transform (model: tolerated)')
            return base()
        wrap('TransformDisconnect', tdisc)

        def sdisc(trap, ahal, a2, base):
            src, sink = AL(ahal), AH(ahal)
            hit = (sink == w.ksink and w.busy_audible()) or (
                src in w.sources and w.sources[src].get('chunk') is not None
                and w.sources[src]['chunk'].audible(w.now))
            if hit:
                w.violate('R2', 'StreamDisconnect(%#06x, %#06x) on a RUNNING port-3 stream '
                                '(probe173 runaway / 174-175 restart)' % (src, sink))
            return base()
        wrap('StreamDisconnect', sdisc)

        # ---- the DSP: 0x1072 ---------------------------------------------------------
        def ksend(trap, ahal, a2, base):
            mid, arg = AL(ahal), AH(ahal)
            if mid == 0x1072 and w.wrong_now:
                w.violate('W1', 'KalimbaSendMessage(0x1072) into a DSP that is not sbc_decoder '
                                '(--wrong-dsp window; the send returns TRUE, the DSP ignores it)')
            if mid == 0x1072 and w.busy_audible():
                w.violate('R1', 'KalimbaSendMessage(0x1072) while port 3 is busy/audible '
                                '(design rule: its handler purges the tone cbuffers, PM 0x1782-'
                                '0x1785; probe173 re-sent it mid-chunk inside a bundle that ran '
                                'away; DESIGN E4 waives it on purpose: --allow R1)')
            r = base()
            if mid == 0x1072 and (r[1] & 0xFFFF):
                w.rate_sent, w.level_b = arg, s0(a2)
                w.sent_1072.append((w.now, arg, s0(a2)))
            return r
        wrap('KalimbaSendMessage', ksend)

        # ---- messages ---------------------------------------------------------------
        def sendlater(trap, ahal, a2, base):
            task, mid = AL(ahal), AH(ahal)
            delay = (s1(a2) << 16) | vm.rd((vm.Y + 2) & 0xFFFF)
            if task == w.task:
                if delay < a.poll_floor:
                    w.violate('R5', 'MessageSendLater to the cave with %d ms < the %d ms floor'
                              % (delay, a.poll_floor))
                _flag = getattr(a, 'flag_id', None)
                _fid = int(_flag, 16) if _flag else None
                _others = [e for e in w.pending(w.task) if e['id'] != _fid]
                if _others and mid != _fid:   # the flag renewing itself is not a second chain
                    w.violate('R6', 'a cave message is already pending (%s): this one starts a '
                                    'second chain' % ', '.join('%#x' % e['id'] for e in _others))
                w.push(w.now + delay, 1, {'kind': 'msg', 'task': task, 'id': mid})
                w.say('MessageSendLater(cave, id %#x) due at t=%d ms' % (mid, w.now + delay))
            else:
                w.say('MessageSendLater(task %#06x, id %#x, %d ms): not the cave\'s task; '
                      'not simulated' % (task, mid, delay))
            return base()
        wrap('MessageSendLater', sendlater)

        def sinktask(trap, ahal, a2, base):
            # probe337: MessageSinkTask(sink = AL, task = AH): remember the task registered on the Kalimba sink; the stock clearing it (fn_31ab7) is not modelled
            if w.ksink is not None and AL(ahal) == w.ksink:
                w.sink_task = AH(ahal)
                w.say('MessageSinkTask(ksink, %#06x) -> registered%s' % (AH(ahal), ' (the cave task)' if AH(ahal) == w.task else ''))
            return base()
        wrap('MessageSinkTask', sinktask)

        def pollpoll(trap, ahal, a2, base):
            # probe340: TransformPollTraffic is TRUE (data moved) unless TRAFFIC_GAP=start:len (ms) says the pipeline stood still then
            g = __import__('os').environ.get('TRAFFIC_GAP')
            if g:
                st, ln = (int(x) for x in g.split(':'))
                if st <= w.now < st + ln:
                    w.say('TransformPollTraffic -> FALSE (TRAFFIC_GAP %s)' % g)
                    return (0, 0)
            return base()
        wrap('TransformPollTraffic', pollpoll)

        def cancelfirst(trap, ahal, a2, base):
            task, mid = AL(ahal), AH(ahal)
            if w.cancel_mode == 'never':
                w.say('MessageCancelFirst(%#06x, %#x) -> FALSE (--cancel never: the trap never '
                      'finds the message)' % (task, mid))
                return (0, 0)
            if w.cancel_mode == 'always':
                w.say('MessageCancelFirst(%#06x, %#x) -> TRUE (--cancel always: nothing removed)'
                      % (task, mid))
                return (0, 1)
            cands = sorted((e for e in w.pending(task) if e['id'] == mid),
                           key=lambda e: (e['t'], e['seq']))
            if cands:
                cands[0]['dead'] = True
                w.say('MessageCancelFirst(%#06x, %#x) -> TRUE (removed the message due at %d ms)'
                      % (task, mid, cands[0]['t']))
                return (0, 1)
            w.say('MessageCancelFirst(%#06x, %#x) -> FALSE (nothing pending)' % (task, mid))
            return (0, 0)
        wrap('MessageCancelFirst', cancelfirst)

        def flushtask(trap, ahal, a2, base):
            task = AL(ahal)
            ps = w.pending(task)
            for e in ps:
                e['dead'] = True
            w.say('MessageFlushTask(%#06x) -> %d' % (task, len(ps)))
            return (0, len(ps))
        wrap('MessageFlushTask', flushtask)

        # ---- the file system -------------------------------------------------------
        def filefind(trap, ahal, a2, base):
            r = base()
            if (r[1] & 0xFFFF) == 0:
                w.say('FileFind -> 0 (forced: --fail / --fail-after)')
                return (0, 0)
            n = s0(a2)
            name = ''.join(chr(w.rd_data(AH(ahal) + k) & 0xFF) for k in range(n))
            h = w.find(AL(ahal), name)
            w.say('FileFind(dir %#06x, %r, %d) -> %s' % (AL(ahal), name, n,
                                                       '%#06x' % h if h else 'FILE_NONE'))
            return (0, h)
        wrap('FileFind', filefind)

        def filesource(trap, ahal, a2, base):
            r = base()
            if (r[1] & 0xFFFF) == 0:
                return r
            path = w.paths.get(AL(ahal))
            if path is None or path not in w.fs:
                w.say('StreamFileSource(%#06x): not a file handle -> 0' % AL(ahal))
                return (0, 0)
            h = SRC_HANDLE0 + w.n_src
            w.n_src += 1
            w.sources[h] = {'path': path, 'size': w.fs[path]['size'], 'pos': 0, 'closed': False,
                            'chunk': None, 'data': w.file_bytes(path)}
            return (0, h)
        wrap('StreamFileSource', filesource)

        def srcsize(trap, ahal, a2, base):
            s = w.sources.get(AL(ahal))
            if s is None:
                w.warn('SourceSize on an unknown source %#06x' % AL(ahal))
                return base()
            n = w.src_size(s)
            w.size_calls += 1
            if a.size_dries_after is not None and w.size_calls > a.size_dries_after:
                w.say('SourceSize(%s) -> 0 (forced: --size-dries-after %d, call %d; the window really '
                      'holds %d)' % (s['path'], a.size_dries_after, w.size_calls, n))
                return (0, 0)
            for _r in getattr(a, 'size_value_at', []) or []:        # H1: one forced answer at the Nth call
                _c, _v = (int(x, 0) for x in _r.split(':'))
                if w.size_calls == _c:
                    w.say('SourceSize(%s) -> %d (forced: --size-value-at %d:%d; the window really holds %d)' % (s['path'], _v, _c, _v, n))
                    return (0, _v)
            w.say('SourceSize(%s) -> %d' % (s['path'], n))
            return (0, n)
        wrap('SourceSize', srcsize)

        # --p2-capture: the payload the cave hands the p2 sink. Captured at SinkFlush (what is
        # COMMITTED, in order): SinkMap's last return + SinkClaim's last return is the claim buffer,
        # read in the model's RAM at the flush. A cave that fills the buffer by memmove (184) and one
        # that stores into it directly (probe140's pattern) are both seen byte for byte; the gate
        # script used to wrap memmove, which saw only the first kind.
        def sinkmap_track(trap, ahal, a2, base):
            r = base()
            if AL(ahal) == w.p2['sink']:
                w.last_map = r[1] & 0xFFFF
            return r
        wrap('SinkMap', sinkmap_track)

        def srcmap(trap, ahal, a2, base):
            r = base()
            if (r[1] & 0xFFFF) == 0:
                return r
            s = w.sources.get(AL(ahal))
            if s is None:
                return r
            fp = getattr(a, 'map_fail_pos', None)
            if fp is not None and s['pos'] >= fp:
                w.say('SourceMap(%s) -> 0 (forced: --map-fail-pos %d, position %d)' % (s['path'], fp, s['pos']))
                return (0, 0)
            return (0, w.src_map(s))
        wrap('SourceMap', srcmap)

        def srcdrop(trap, ahal, a2, base):
            s = w.sources.get(AL(ahal))
            if s is None:
                w.warn('SourceDrop on an unknown source %#06x' % AL(ahal))
                return (AH(ahal), AL(ahal))
            n, size = AH(ahal), w.src_size(s)
            if n > size:
                w.warn('SourceDrop(%d) is more than SourceSize (%d): real behaviour unknown'
                       % (n, size))
                n = size
            if getattr(a, 'drop_adv', None) is not None:
                n = a.drop_adv                         # D1: the drop advances by this many bytes whatever was asked
            s['ndrop'] = s.get('ndrop', 0) + 1               # G1: the history flags
            s['lastdrop'] = AH(ahal)
            s['pos'] = min(s['pos'] + n, s['size'])
            if getattr(a, 'map_live', False) and getattr(w, 'last_mapped', None) is s:
                w.src_map(s)                           # E1: a live window follows the position
            w.say('SourceDrop(%s, %d): %d bytes left in the file, window now %d'
                  % (s['path'], n, s['size'] - s['pos'], w.src_size(s)))
            return (AH(ahal), AL(ahal))
        wrap('SourceDrop', srcdrop)

        def srcclose(trap, ahal, a2, base):
            s = w.sources.get(AL(ahal))
            if s is not None:
                s['closed'] = True
            return base()
        wrap('SourceClose', srcclose)

        # ---- partitions ----------------------------------------------------------------
        def getinfo(trap, ahal, a2, base):
            r = base()
            part, key, ptr = AH(ahal), s0(a2), s1(a2)
            val = w.pinfo.get((part, key))
            if val is None and part == 2 and key == 0 and w.p2['mounted'] is not None:
                val = 1 if (w.p2['mounted'] or w.p2['mounted_by_cave']) else 0
            if val is None and part == 2 and key == 3 and w.p2['open'] and not w.p2['closed']:
                val = 1                              # INCOMPLETE until the sink is closed
            if val is None:
                return r
            vm.wr(ptr, (val >> 16) & 0xFFFF)
            vm.wr((ptr + 1) & 0xFFFF, val & 0xFFFF)
            return (0, 1)
        wrap('PartitionGetInfo', getinfo)

        def mount(trap, ahal, a2, base):
            r = base()
            dev, part = AL(ahal), AH(ahal)
            if (r[1] & 0xFFFF) and dev == 1 and part == 2:
                w.p2['mounted_by_cave'] = True
                w.say('PartitionMountFilesystem(1, 2): mounted (model)')
            elif (r[1] & 0xFFFF) == 0:
                w.say('PartitionMountFilesystem(%d, %d) -> FALSE' % (dev, part))
            return r
        wrap('PartitionMountFilesystem', mount)

        def overwrite(trap, ahal, a2, base):
            r = base()
            if (r[1] & 0xFFFF) and AH(ahal) == 2:
                w.p2.update(open=True, closed=False, sink=r[1] & 0xFFFF, erased=True)
                w.say('StreamPartitionOverwriteSink(%d, 2): the p2 ERASE is issued' % AL(ahal))
            return r
        wrap('StreamPartitionOverwriteSink', overwrite)

        def sinkclaim(trap, ahal, a2, base):
            r = base()
            if AL(ahal) == w.p2['sink']:
                w.p2['claims'] += 1
                w.last_claim = r[1] & 0xFFFF
            return r
        wrap('SinkClaim', sinkclaim)

        def sinkflush(trap, ahal, a2, base):
            if AL(ahal) == w.p2['sink']:
                w.p2['flushes'] += 1
                w.p2['bytes'] += AH(ahal)
                if (a.p2_capture or a.raw_from_sink) and w.p2['open'] and not w.p2['closed']:
                    start = (w.last_map + w.last_claim) & 0xFFFF
                    w.p2_capture.append(bytes(vm.rd((start + k) & 0xFFFF) & 0xFF
                                              for k in range(AH(ahal))))
            return base()
        wrap('SinkFlush', sinkflush)

        def digest(trap, ahal, a2, base):
            if AL(ahal) == w.p2['sink']:
                w.p2['digest'] = AH(ahal)
            return base()
        wrap('PartitionSetMessageDigest', digest)

        def sinkclose(trap, ahal, a2, base):
            if AL(ahal) == w.p2['sink'] and w.p2['open']:
                w.p2['closed'] = True
                w.say('SinkClose(p2 sink): %d flushes, %d bytes, digest type %s -> %s'
                      % (w.p2['flushes'], w.p2['bytes'], w.p2['digest'],
                         'VALID' if w.p2['digest'] == 3 else 'digest not SKIP'))
            return base()
        wrap('SinkClose', sinkclose)

        # ---- the prompt engine and the stock call the hook replays -------------------------
        def speak(pc, pair, _):
            sid = pair & 0xFFFF
            w.spoken.append((w.now, sid))
            if w.busy_audible():
                w.violate('R3', 'SPEAK %#04x while port 3 is ours (every prompt on a live '
                                'sbc_decoder is mixed through port 3: silent at best)' % sid)
            return (0, 0)
        vm.FUNC_RET[self.ctx.SPEAK_ADDR] = speak

        def replay(pc, pair, _):
            w.replayed = True
            return (0, 0)
        vm.FUNC_RET[FN_REPLAY] = replay
        if getattr(a, 'audio_busy', False):                      # probe210: the stock SetAudioBusy / GetAudioBusy
            if getattr(a, 'busy_init', None):
                w.audio_busy = int(a.busy_init, 16)
            def getbusy(pc, pair, _):
                return (0, w.audio_busy & 0xFFFF)
            def setbusy(pc, pair, _):
                new = pair & 0xFFFF
                w.busy_log.append((w.now, new))
                w.audio_busy = new
                if new == 0:
                    w.release_parked('SetAudioBusy(0)')
                return (0, 0)
            vm.FUNC_RET[0x2F9F2] = getbusy
            vm.FUNC_RET[0x2F9FB] = setbusy
        self.install_raw()

    # ------------------------------------------------------------------ R1 / probe196: the raw source world
    def raw_payload(self, spec):
        """--raw-p2 SPEC -> bytes, or None for 'none'. Never opens a .bin or a readback."""
        kind, _, rest = spec.partition(':')
        if kind == 'none':
            return None
        if kind == 'zero':
            return bytes(int(rest))
        if kind == 'incr':
            return bytes(i & 0xFF for i in range(int(rest)))
        if kind == 'hex':
            return bytes.fromhex(rest)
        if kind == 'file':                          # probe209 (2026-10-15): a payload file under build/payload/ (never a .bin, a .dfu or a readback)
            rel = rest.replace(chr(92), '/')
            if not rel.startswith('build/payload/') or rel.endswith(('.bin', '.dfu')) or 'readback' in rel or '..' in rel:
                raise SystemExit('--raw-p2 file: only build/payload/* payload files are allowed')
            return open(os.path.join(ROOT, rel), 'rb').read()
        if kind == 'staged141':
            sw = json.load(open(os.path.join(ROOT, 'build/payload/staged_words.json')))
            out = bytearray()
            for v in sw[2:]:                       # probe141 gathered ROFS words 2.. (payload-184.md 4b)
                out += bytes((v & 0xFF, (v >> 8) & 0xFF))
            return bytes(out[:4096])
        raise SystemExit('--raw-p2: unknown spec %r' % spec)

    def raw_window(self, s):
        return max(0, min(len(s['data']) - s['pos'], self.args.raw_prime))

    def raw_elements(self, s):
        """the SourceMap elements for the current window, per --raw-pack"""
        d = s['data'][s['pos']:s['pos'] + self.raw_window(s)]
        mode = self.args.raw_pack
        if mode == 'octet':
            return list(d)
        out = []
        for i in range(0, len(d), 2):
            b0, b1 = d[i], (d[i + 1] if i + 1 < len(d) else 0)
            out.append((b0 | (b1 << 8)) if mode == 'le' else ((b0 << 8) | b1))
        return out

    def install_raw(self):
        """Wrappers added AFTER the legacy ones (so they are outermost): handles they do not know fall through
        to the legacy behaviour untouched. M1-graw.md D3 is the contract: the builder returns a handle for
        (device 1, partition 2) only; SourceSize after creation = min(prime, length); SourceMap shows the
        window; SourceDrop is FORBIDDEN in R1 (rule R7); SourceClose closes."""
        vm, tn, w, a = self.vm, self.trapnums, self, self.args

        def wrap(name, fn):
            t = tn.get(name)
            if t is None:
                return
            base = vm.STUB_RET.get(t)

            def inner(trap, ahal, a2, base=base, fn=fn):
                return fn(trap, ahal, a2, lambda: w.call_base(base, trap, ahal, a2))
            vm.STUB_RET[t] = inner

        def AL(x): return x & 0xFFFF
        def AH(x): return (x >> 16) & 0xFFFF

        # SinkSlack: --slack N for BOTH the stock and the synthesised stub (they share the model)
        if a.slack is not None:
            wrap('SinkSlack', lambda trap, ahal, a2, base: (0, a.slack & 0xFFFF))

        # PartitionGetInfo: count calls, --getinfo-fail-at N -> FALSE (the legacy/world answer is not consulted)
        def getinfo_count(trap, ahal, a2, base):
            w.getinfo_n += 1
            if w.getinfo_n in a.getinfo_fail_at:
                w.say('PartitionGetInfo call %d -> FALSE (--getinfo-fail-at)' % w.getinfo_n)
                return (0, 0)
            return base()
        wrap('PartitionGetInfo', getinfo_count)

        # the synthesised stubs: count the calls; --synth-skew adds N to the synthesised SinkSlack result
        for addr, (n_, _kind, _ln) in (w.state.get('synth') or {}).items():
            old = vm.FUNC_RET[addr]

            def synth(pc, pair, _, old=old, n_=n_):
                if a.synth_noop:
                    w.synth_calls[n_] = w.synth_calls.get(n_, 0) + 1
                    w.say('synthesised stub for trap %#x returned WITHOUT running the trap (--synth-noop)' % n_)
                    return (vm.AH, vm.AL)
                r = old(pc, pair, _)
                w.synth_calls[n_] = w.synth_calls.get(n_, 0) + 1
                if n_ == 0xCE and a.synth_skew:
                    ptr = vm.rd((vm.Y + 1) & 0xFFFF)          # the caller's @(1,Y): where TYPE was written
                    vm.wr((ptr + 1) & 0xFFFF, (vm.rd((ptr + 1) & 0xFFFF) + a.synth_skew) & 0xFFFF)
                    w.say('synthesised PartitionGetInfo stub: written value skewed by %+d (--synth-skew)' % a.synth_skew)
                if n_ == 0x3F and a.synth_skew:
                    w.say('synthesised SinkSlack stub: result skewed by %+d (--synth-skew)' % a.synth_skew)
                    return (r[0], (r[1] + a.synth_skew) & 0xFFFF)
                return r
            vm.FUNC_RET[addr] = synth

        # ---- R2 / probe197 wrappers (outermost): SinkClaim / SinkFlush failure injection, the clock, the digest result
        r2on = bool(a.raw_from_sink or a.claim_fail_at or a.flush_fail_at or a.erase_ms or a.flush_ms
                    or a.claim_offset is not None
                    or a.clock_base != 5000 or a.clock_jump)
        def claim_fail(trap, ahal, a2, base):
            w.claim_n += 1
            if w.claim_n in a.claim_fail_at and AL(ahal) == w.p2['sink']:
                w.say('SinkClaim call %d -> 0xFFFF (--claim-fail-at)' % w.claim_n)
                return (0, 0xFFFF)
            r = base()
            if a.claim_offset is not None and AL(ahal) == w.p2['sink']:
                w.last_claim = a.claim_offset & 0xFFFF         # the capture reads at map + offset
                return (0, a.claim_offset & 0xFFFF)
            return r
        if a.claim_fail_at or a.claim_offset is not None:
            wrap('SinkClaim', claim_fail)

        def flush_fail(trap, ahal, a2, base):
            if AL(ahal) == w.p2['sink']:
                w.flush_n += 1
                if w.flush_n in a.flush_fail_at:
                    w.say('SinkFlush call %d -> 0, nothing committed (--flush-fail-at)' % w.flush_n)
                    return (0, 0)
                w.clock_extra += a.flush_ms
            return base()
        if r2on:
            wrap('SinkFlush', flush_fail)

        def open_clock(trap, ahal, a2, base):
            r = base()
            if (r[1] & 0xFFFF) and AH(ahal) == 2:
                w.clock_extra += a.erase_ms
                w.p2_capture.clear()            # the open erases ALL of p2: what an earlier run committed is gone
                w.digest_ok, w.p2['digest'] = True, None
            return r
        if r2on:
            wrap('StreamPartitionOverwriteSink', open_clock)

        def digest_res(trap, ahal, a2, base):
            r = base()
            if AL(ahal) == w.p2['sink']:
                w.digest_ok = bool(r[1] & 0xFFFF)
            return r
        if r2on:
            wrap('PartitionSetMessageDigest', digest_res)

        def getclock(trap, ahal, a2, base):
            _jx = sum(int(j.split(':')[1]) for j in a.clock_jump if w.now >= int(j.split(':')[0]))
            v = (a.clock_base + w.now + w.clock_extra + _jx) & 0xFFFFFFFF
            return ((v >> 16) & 0xFFFF, v & 0xFFFF)          # AH:AL, as the stock callers read it
        if r2on:
            wrap('VmGetClock', getclock)

        if a.raw_p2 is None and not a.raw_from_sink:
            return
        payload = self.raw_payload(a.raw_p2) if a.raw_p2 is not None else None

        def sink_stream():
            """--raw-from-sink: the bytes the p2 sink committed, or None (the builder refuses: magic missing)."""
            if a.raw_refuse or not (w.p2['closed'] and w.digest_ok and w.p2['digest'] == 3):
                return None
            blob = bytearray(b''.join(w.p2_capture))
            if not blob:
                return None
            if a.raw_truncate is not None:
                del blob[a.raw_truncate:]
            if a.raw_wrapbug is not None:
                orig = bytes(blob)
                for p in range(126, len(blob)):
                    if p - a.raw_wrapbug >= 0:
                        blob[p] = orig[p - a.raw_wrapbug]
            if a.raw_corrupt:
                pos, _, x = a.raw_corrupt.partition(':')
                if int(pos) < len(blob):
                    blob[int(pos)] ^= int(x, 0) if x else 0x55
            return bytes(blob)

        def rawsrc(trap, ahal, a2, base):
            dev, part = AL(ahal), AH(ahal)
            w.raw_calls.append((dev, part))
            r = base()                                   # honours --fail PartitionGetRawSerialSource
            if (r[1] & 0xFFFF) == 0:
                w.say('PartitionGetRawSerialSource(%d, %d) -> 0 (forced: --fail)' % (dev, part))
                return r
            data = sink_stream() if a.raw_from_sink else payload
            if dev != 1 or part != 2 or not data:
                w.say('PartitionGetRawSerialSource(%d, %d) -> 0 (device != 1, partition != 2 or no valid payload)'
                      % (dev, part))
                return (0, 0)
            h = 0x62C0 + len(w.raw_sources)
            w.raw_sources[h] = {'data': data, 'pos': 0, 'closed': False, 'drops': 0, 'maps': 0, 'dead': False}
            w.say('PartitionGetRawSerialSource(1, 2) -> %#06x (payload %d bytes, window %d)'
                  % (h, len(data), a.raw_prime))
            return (0, h)
        wrap('PartitionGetRawSerialSource', rawsrc)

        def dead_call(s, what, h):
            w.violate('R8', '%s on the raw source %#06x AFTER it closed itself (exhausted): the handle is dead' % (what, h))

        def rsize(trap, ahal, a2, base):
            s = w.raw_sources.get(AL(ahal))
            if s is None:
                return base()
            if s['dead']:
                dead_call(s, 'SourceSize', AL(ahal))
                return (0, 0)
            n = w.raw_window(s)
            w.say('SourceSize(raw %#06x) -> %d' % (AL(ahal), n))
            return (0, n)
        wrap('SourceSize', rsize)

        def rmap(trap, ahal, a2, base):
            s = w.raw_sources.get(AL(ahal))
            if s is None:
                return base()
            if s['dead']:
                dead_call(s, 'SourceMap', AL(ahal))
                return (0, 0)
            if s['closed']:
                w.warn('SourceMap on a CLOSED raw source %#06x' % AL(ahal))
            s['maps'] += 1
            if a.raw_map_zero:
                w.say('SourceMap(raw) -> 0 (--raw-map-zero)')
                return (0, 0)
            els = w.raw_elements(s)
            for i, v in enumerate(els):
                vm.wr(SRC_MAP_BASE + i, v)
            w.say('SourceMap(raw) -> %#06x, %d elements (%s)' % (SRC_MAP_BASE, len(els), a.raw_pack))
            return (0, SRC_MAP_BASE)
        wrap('SourceMap', rmap)

        def rdrop(trap, ahal, a2, base):
            s = w.raw_sources.get(AL(ahal))
            if s is None:
                return base()
            if s['dead']:
                dead_call(s, 'SourceDrop', AL(ahal))
                return (AH(ahal), AL(ahal))
            s['drops'] += 1
            w.raw_drops += 1
            if not a.raw_from_sink:
                w.violate('R7', 'SourceDrop on the raw source: R1 forbids it (the first refill can cross the ring '
                                'end, M1-graw B5)')
            n = min(AH(ahal), w.raw_window(s))
            if AH(ahal) > n:
                w.warn('SourceDrop(%d) is more than SourceSize (%d)' % (AH(ahal), n))
            s['pos'] += n
            w.say('SourceDrop(raw, %d): %d bytes left' % (n, len(s['data']) - s['pos']))
            if s['pos'] >= len(s['data']):
                s['dead'] = s['closed'] = True            # M1-graw B4: the object closes itself when exhausted
                w.raw_exhausted += 1
                w.say('raw source exhausted: closed itself')
            return (AH(ahal), AL(ahal))
        wrap('SourceDrop', rdrop)

        def rclose(trap, ahal, a2, base):
            s = w.raw_sources.get(AL(ahal))
            if s is None:
                return base()
            if s['dead']:
                dead_call(s, 'SourceClose', AL(ahal))
                return (0, 0)
            if s['closed']:
                w.warn('SourceClose on an already closed raw source %#06x' % AL(ahal))
            s['closed'] = True
            return (0, 1)
        wrap('SourceClose', rclose)

    # ------------------------------------------------------------------ the chunk life cycle
    def start_chunk(self, c):
        a = self.args
        s = self.sources.get(c.src)
        size = s['size'] if s else 10486
        path = s['path'] if s else '?'
        c.path = path
        c.size = size
        if a.latch == 'late':
            c.rate = self.rate_active
            why = ("the stock's rate: no sent rate has been applied yet"
                   if c.rate == a.stock_rate and self.rate_sent != c.rate
                   else 'applied late from an earlier 0x1072')
            if self.rate_sent is not None:
                self.rate_active = self.rate_sent
        else:
            c.rate = self.rate_sent if self.rate_sent is not None else a.stock_rate
            why = 'immediate'
        c.b = self.level_b
        c.b_now = c.b
        c.wrong = self.wrong_now          # J-T3: built while a non-sbc DSP was resident
        if self.chunk_ms:
            c.dur = self.chunk_ms[min(c.k - 1, len(self.chunk_ms) - 1)]
        else:
            c.dur = int(round(size * 2 * 1000.0 / c.rate))
        c.start = self.now
        c.end = c.start + c.dur
        c.eof = max(c.start, c.end - a.tail_ms)
        c.freed = c.eof if a.free_edge == 'eof' else c.end
        self.push(c.eof, 0, {'kind': 'eof', 'chunk': c})
        self.push(c.end, 0, {'kind': 'end', 'chunk': c})
        self.say('chunk %d starts: %s, %d bytes, rate %d Hz (%s), word b=%#x (%s), %d ms; '
                 'source EOF at %d, audible end at %d, port reads free from %d'
                 % (c.k, path, size, c.rate, why,
                    c.b, 'shift 4, quiet' if c.b & 2 else 'shift 7, loud', c.dur,
                    c.eof, c.end, c.freed))
        if a.loop and len([x for x in self.chunks if x.start is not None]) > a.loop:
            self.started_after_cap = True

    def end_chunk(self, c):
        c.ended = True
        a = self.args
        self.push(self.now + a.tone_end_ms, 0, {'kind': 'toneend', 'chunk': c})

    # ------------------------------------------------------------------ the session
    def deliver_kalimba(self, mid):
        d = self.dsp
        if d['task'] is not None and d['task'] == self.task and d['loaded']:
            d['queue'].append(('dsp', mid))
            return True
        return False

    def run(self, cave, entry_event, handler):
        """Drive the world until the queue drains, the --loop cap is met and settled, or a
        limit is hit.  `handler` is the cave handler's code address (None: no TaskData)."""
        vm, a = self.vm, self.args
        presses = []
        for spec in a.press:
            t, _, ev = spec.partition(':')
            presses.append((int(t), int(ev or '4004', 16)))
        if not presses and (a.loop or a.press_gap or not a.pending):
            presses.append((0, entry_event))
        self.press_event = presses[0][1] if presses else entry_event
        for t, ev in presses:
            self.push(t, 2, {'kind': 'press', 'event': ev})
        for spec in a.pending:
            ident, _, when = spec.partition('@')
            self.push(int(when or 1000), 1, {'kind': 'msg', 'task': self.task,
                                             'id': int(ident, 16)})
        for t, d in self.wrong_windows:
            self.push(t, 0, {'kind': 'wrong_on', 'dur': d})
            self.push(t + d, 0, {'kind': 'wrong_off'})
        for t, d in self.foreign_tones:
            self.push(t, 0, {'kind': 'foreign_cut', 'dur': d})
        for t, b in self.mid1072:
            self.push(t, 0, {'kind': 'mid1072', 'b': b})
        for t, m_ in self.msg_at:
            self.push(t, 1, {'kind': 'msg', 'task': self.task, 'id': m_})
        for t, m_ in self.dspmsg_at:
            self.push(t, 0, {'kind': 'dspmsg', 'mid': m_})
        for t, ad, v in self.mem_at:
            self.push(t, 0, {'kind': 'mem', 'addr': ad, 'val': v})
        for s_ in getattr(self.args, 'chain_at', []):          # BH: --chain-at MS:0|1 (needs --chain-model)
            t_, _, v_ = s_.partition(':')
            self.push(int(t_), 0, {'kind': 'chain_set', 'val': int(v_)})
        for t in self.tone_at:
            self.push(t, 0, {'kind': 'stock_req', 'what': 'tone'})
        for t in self.tts_at:
            self.push(t, 0, {'kind': 'stock_req', 'what': 'tts'})
        for t, v in self.field_at:
            self.push(t, 0, {'kind': 'field', 'val': v})
        if a.bt_teardown_at is not None:
            self.push(a.bt_teardown_at, 0, {'kind': 'bt'})
        if a.unload_at is not None:
            self.push(a.unload_at, 0, {'kind': 'unload'})
        if getattr(a, 'pause_at', None) is not None:
            self.push(a.pause_at, 0, {'kind': 'pause'})
        if a.music_resume_at is not None:
            self.push(a.music_resume_at, 0, {'kind': 'resume'})
        horizon = 0 if a.once else a.horizon
        n_run, settle_deadline = 0, None
        while True:
            if self.rebooted is not None:
                self.loop_stop_reason = 'REBOOT (modelled VM fault, chip reset) at %d ms' % self.rebooted
                break
            while self.queue and self.queue[0][3].get('dead'):
                heapq.heappop(self.queue)
            if not self.queue:
                self.loop_stop_reason = 'queue empty (nothing more will happen)'
                break
            t, _prio, _seq, ev = self.queue[0]
            if t > horizon:
                self.loop_stop_reason = 'horizon (%d ms) reached with %d event(s) still queued' % (
                    horizon, len([e for (_a, _b, _c, e) in self.queue if not e.get('dead')]))
                break
            if settle_deadline is not None and t > settle_deadline:
                self.loop_stop_reason = ('settle window (%d ms after chunk %d ended) over with '
                                         'cave events still queued' % (a.settle_ms, a.loop))
                break
            if n_run >= a.events:
                self.loop_stop_reason = 'event limit (%d) reached' % a.events
                break
            heapq.heappop(self.queue)
            self.now = t
            kind = ev['kind']
            if kind in ('press', 'msg'):
                if kind == 'press':
                    ev_id, title_x = ev['event'], ''
                    if a.voice_field and ev_id == self.short_id and self.field == 1:
                        title_x = ' (centre SHORT %#06x converted by the stock fn_07d5d)' % ev_id
                        ev_id = 0x4004
                        self.converted += 1
                    ev['event_in'] = ev_id
                    vm.AH, vm.AL = (int(a.ah, 16) if a.ah else 0), ev_id
                    entry, title = cave, 'press %#06x%s' % (ev_id, title_x)
                    self.replayed = False
                else:
                    if handler is None:
                        self.say('message for a cave with no TaskData handler')
                        continue
                    vm.AH, vm.AL = ev['id'], ev['task']
                    entry, title = handler, 'timer message, MessageId %#06x' % ev['id']
                n_run += 1
                if self.run_cave(entry, title):
                    return 1
                if kind == 'press':
                    if self.replayed:
                        self.replays += 1
                    else:
                        self.swallowed += 1
                    if a.voice_field and ev['event_in'] == 0x4004:
                        self.field ^= 1
                        self.requests.append((self.now, 'enable' if self.field else 'disable'))
                        print('  stock 0x4004 arm (runs whatever the cave did): voice-recognition '
                              '%s request, field now %d [T04 C10, static prediction, never seen]'
                              % (self.requests[-1][1], self.field))
                    print('  event %#06x: %s' % (
                        ev['event_in'], 'REPLAYED to the stock fn_189fb' if self.replayed
                        else 'SWALLOWED (fn_189fb not replayed; on hardware '
                        'fn_01749 case-3 arm 0x0194C still runs after: not modelled)'))
            else:
                self.internal(ev)
            if self.flush_dsp_events(handler):
                n_run += 1
            if self.started_after_cap:
                self.loop_stop_reason = ('chunk %d started after the --loop %d cap: the cave '
                                         'keeps looping (no end of its own seen)'
                                         % (len(self.chunks), a.loop))
                break
            settle_deadline = self.update_settle(settle_deadline)
        return 0

    def ended_count(self):
        return len([c for c in self.chunks if c.ended])

    def update_settle(self, deadline):
        a = self.args
        if a.loop and deadline is None and self.ended_count() >= a.loop:
            return self.now + a.settle_ms
        return deadline

    def internal(self, ev):
        k, a = ev['kind'], self.args
        if k in ('eof', 'end') and ev['chunk'].gen != ev.get('gen', 0):
            return                          # J-T3: rescheduled by a purge or a rate change
        if k == 'eof':
            c = ev['chunk']
            if c.cut:
                return
            self.say_line('t=%6d  chunk %d: source EOF%s' % (
                self.now, c.k, ' -> firmware frees port 3' if a.free_edge == 'eof' else ''))
            if a.free_edge == 'eof' and getattr(self, 'sink_task', None) == self.task and not __import__('os').environ.get('NO_FREE_MSG'):   # NO_FREE_MSG=1: the message never comes (watchdog test)
                # probe337: the stack's dispose posts MESSAGE_STREAM_DISCONNECT (0x8026) to the task registered on the Kalimba sink (stack-transform.md section 4)
                self.push(self.now, 1, {'kind': 'msg', 'task': self.task, 'id': 0x8026})
                self.say_line('t=%6d  MESSAGE_STREAM_DISCONNECT (0x8026) posted to the cave task' % self.now)
        elif k == 'end':
            c = ev['chunk']
            if c.cut or c.ended:
                return
            self.say_line('t=%6d  chunk %d: audible end%s' % (
                self.now, c.k, ' -> firmware frees port 3' if a.free_edge == 'audible' else ''))
            self.end_chunk(c)
            if (a.press_gap and not self.pending(self.task)
                    and not (a.loop and self.ended_count() >= a.loop)):
                self.push(self.now + a.press_gap, 2, {'kind': 'press', 'event': self.press_event})
        elif k == 'pause':
            if self.audio_busy == 0:
                self.say_line('t=%6d  music PAUSED: the stock disconnects the plugin (audio-busy is zero)' % self.now)
                self.push(self.now + a.unload_ms, 0, {'kind': 'unload', 'why': 'music paused'})
            else:
                self.pending_disc = True
                self.say_line('t=%6d  music PAUSED: the plugin disconnect is PARKED on the audio-busy word (%#06x)' % (self.now, self.audio_busy))
        elif k == 'toneend':
            c = ev['chunk']
            if getattr(c, 'wrong', False):
                self.say_line('t=%6d  chunk %d: no 0x1080 (it was built into a DSP that is not '
                              'sbc_decoder: unknown what, if anything, was heard)' % (self.now, c.k))
                return
            if getattr(a, 'audio_busy', False) and any(o is not c and o.audible(self.now) for o in self.chunks):
                self.say_line('t=%6d  chunk %d: no 0x1080 (another chunk is already running: the tone buffer was refilled)' % (self.now, c.k))
                return
            sent = self.deliver_kalimba(0x1080)
            self.stale_sink_task = False      # fn_31ab7 clears MessageSinkTask(ksink)
            if getattr(a, 'audio_busy', False) and not (self.stock_world and sent):      # BF: with the stock world on, a 0x1080 the CAVE handled never ran fn_31ab7: the cave's hold stays (AQ 7.1)
                self.audio_busy = 0               # fn_31ab7 -> SetAudioBusy(NULL)
                self.busy_log.append((self.now, 0))
                self.release_parked('0x1080 end-of-tone')
            self.say_line('t=%6d  chunk %d: DSP end-of-tone 0x1080 -> %s' % (
                self.now, c.k, 'the CAVE handler' if sent else
                'the stock task (fn_31ab7: no teardown trap; the cave is not told)'))
            if a.music == 'paused' and self.dsp['loaded']:
                self.push(self.now + a.unload_ms, 0, {'kind': 'unload', 'why': 'paused'})
        elif k == 'dspmsg':
            self.dsp['queue'].append(('stock', ev['mid']))
            self.say_line('t=%6d  a DSP message %#06x arrives (--dspmsg-at)' % (self.now, ev['mid']))
        elif k == 'unload':
            if self.dsp['loaded']:
                self.dsp.update(loaded=False, plugin=None, go=False)
                self.vm.chain_alive = False        # BH: a stock unload (KalimbaPowerOff) disposes the chains
                self.rate_active, self.rate_sent = a.stock_rate, None
                self.say_line('t=%6d  DSP UNLOADED (%s): KalimbaSendMessage now returns FALSE'
                              % (self.now, ev.get('why', '--unload-at')))
        elif k == 'resume':
            self.dsp.update(loaded=True, plugin=None, go=False)
            self.vm.chain_alive = True             # BH: the stock reloads its DSP and rebuilds its chain
            self.rate_active, self.rate_sent = a.stock_rate, None
            self.say_line('t=%6d  music resumes: stock reloads the DSP (rate back to the '
                          'stock\'s %d Hz)' % (self.now, a.stock_rate))
        elif k == 'wrong_on':
            n = self.cut_chunks('dsp-swap (--wrong-dsp)')
            self.wrong_now, self.wrong_since = True, self.now
            self.rate_active, self.rate_sent = a.stock_rate, None
            self.say_line('t=%6d  WRONG DSP resident for %d ms (a prompt or call DSP replaced '
                          'sbc_decoder): %d chain(s) cut, TransformFromSink reads 0, the gate '
                          'still reads TRUE, StreamKalimbaSink(3) stays nonzero'
                          % (self.now, ev['dur'], n))
        elif k == 'wrong_off':
            n = self.cut_chunks('lost when the stock reloaded sbc_decoder', since=self.wrong_since)
            self.wrong_now = False
            self.rate_active, self.rate_sent = a.stock_rate, None
            self.say_line('t=%6d  sbc_decoder reloaded by the stock (%d chain(s) built into the '
                          'wrong DSP are gone; rate latch reset)' % (self.now, n))
        elif k == 'foreign_cut':
            n = self.cut_chunks('stock tone pre-emption (--foreign-tone)')
            self.say_line('t=%6d  STOCK TONE (fn_1c17f) disposes our chain (StreamDisconnect on its '
                          'sink pair, %d chain(s) cut) and holds port 3 for %d ms: '
                          'TransformFromSink reads a foreign handle' % (self.now, n, ev['dur']))
        elif k == 'mid1072':
            self.stock_1072(ev['b'])
        elif k == 'field':
            self.field = ev['val']
            self.say_line('t=%6d  HFP status message %s the voice-recognition field (T04 M4)'
                          % (self.now, 'SETS' if self.field else 'CLEARS'))
        elif k == 'stock_req':
            self.stock_request(ev['what'])
        elif k == 'stock_end':
            self.stock_finish(ev['what'])
        elif k == 'mem' and ev['addr'] == 0xFFFE and getattr(a, 'audio_busy', False):      # probe298 (opt-in): --mem-at MS:fffe=VAL sets the MODELLED audio-busy word (a stock sound takes / frees it); needs --audio-busy
            self.audio_busy = ev['val'] & 0xFFFF
            if self.audio_busy == 0 and self.stock_world and self.rebooted is None:
                self.stock_serve()
            self.say_line('t=%6d  audio-busy word := %#06x (--mem-at fffe=, a stock owner)' % (self.now, self.audio_busy))
        elif k == 'chain_set':
            self.vm.chain_alive = bool(ev['val'])
            self.say_line('t=%6d  the DAC link chain is set %s (--chain-at)' % (self.now, 'ALIVE' if ev['val'] else 'DEAD'))
        elif k == 'mem':
            self.vm.wr(ev['addr'], ev['val'])
            self.say_line('t=%6d  RAM @%#06x := %#06x (--mem-at; for 0x59e this is a sinkState '
                          'change)' % (self.now, ev['addr'], ev['val']))
        elif k == 'bt':
            run = self.running_chunk()
            self.say_line('t=%6d  BLUETOOTH LONG PRESS (fn_0d500 teardown)%s' % (
                self.now, ': chunk %d ended cleanly, DSP unloaded; pending cave messages '
                'are NOT flushed (model)' % run.k if run else ': nothing running; DSP unloaded'))
            if run:
                run.cut = 'bt-teardown'
                run.end = run.eof = run.freed = self.now
                run.ended = True
            self.dsp.update(loaded=False, plugin=None, go=False)
            self.vm.chain_alive = False            # BH
            self.rate_active, self.rate_sent = a.stock_rate, None

    def cut_chunks(self, why, since=None):
        """J-T3: dispose every chain that still holds port 3 (cleanly, like the Bluetooth long
        press): its remaining audio is lost, the port reads free, no 0x1080 reaches the cave."""
        n = 0
        for c in self.chunks:
            if c.start is None or c.cut:
                continue
            if since is not None and c.start < since:
                continue
            if c.audible(self.now) or c.holds(self.now):
                c.cut = why
                c.gen += 1
                c.end = c.eof = c.freed = self.now
                c.ended = True
                n += 1
        return n

    def reschedule(self, c, new_end, new_eof):
        """Move a running chunk's source-EOF and audible end (a purge cut or a rate change)."""
        was_eof_free = (c.freed == c.eof)
        c.gen += 1
        c.end, c.eof = int(round(new_end)), int(round(max(self.now, min(new_eof, new_end))))
        c.freed = c.eof if was_eof_free else c.end
        self.push(c.eof, 0, {'kind': 'eof', 'chunk': c, 'gen': c.gen})
        self.push(c.end, 0, {'kind': 'end', 'chunk': c, 'gen': c.gen})

    def stock_1072(self, b):
        """--mid-chunk-1072: the stock A2DP-time tone starter (fn_31a7c, T04) sends
        0x1072(8000, b) straight to the DSP. Not a cave call: R1 does not apply."""
        a = self.args
        run = self.running_chunk()
        rate = STOCK_RATE
        self.sent_1072.append((self.now, rate, b))
        self.rate_sent, self.level_b = rate, b
        self.stale_sink_task = True
        if run is None:
            self.say_line('t=%6d  STOCK 0x1072(%d, b=%#x) with nothing playing: rate/level word '
                          'now %d Hz / b=%#x until the next sender' % (self.now, rate, b, rate, b))
            return
        rem = run.end - self.now
        buf_ms = 255 * 1000.0 / run.rate
        cut = min(rem, buf_ms) if rem > 0 else 0
        run.splices.append((self.now, cut))
        new_end, new_eof = run.end - cut, run.eof - cut
        if a.latch == 'immediate' and run.rate != rate:
            scale = float(rate) / run.rate           # remaining samples play at the new rate
            new_end = self.now + (new_end - self.now) / scale
            new_eof = self.now + max(0.0, new_eof - self.now) / scale
            run.rate = rate
        self.reschedule(run, new_end, new_eof)
        old_b = run.b_now
        run.b_now = b
        run.level_log.append((self.now, old_b, b))
        self.say_line('t=%6d  STOCK 0x1072(%d, b=%#x) mid-chunk (not through the cave): purge cuts '
                      'up to %.1f ms of tail (cut %.1f ms), level b %#x -> %#x, the ksink task is '
                      'left on the stock plug-in until the next 0x1080'
                      % (self.now, rate, b, buf_ms, cut, old_b, b))
        if (old_b & 2) and not (b & 2):
            self.hazard_notes.append((self.now,
                'HEARING HAZARD: chunk %d goes from quiet (b&2, shift 4) to loud (shift 7), '
                '+18 dB, at %d ms and stays there for %d ms until the cave next resends b'
                % (run.k, self.now, run.end - self.now)))

    def say_line(self, s):
        print('\n== ' + s if not s.startswith('==') else s)

    def flush_dsp_events(self, handler):
        """Run the cave handler for DSP messages queued by the model."""
        n = 0
        while self.dsp['queue'] and handler is not None:
            kind, mid = self.dsp['queue'].pop(0)
            c = self.ctx
            self.vm.AH, self.vm.AL = c.DSP_MSG, self.task
            for k, v in enumerate((mid, 0, 0, 0, 0)):
                self.vm.wr(c.MSGBUF + k, v)
            self.run_cave(handler, "MESSAGE_FROM_KALIMBA msg[0]=%#06x" % mid)
            n += 1
        return n

    def run_cave(self, entry, title):
        c, vm = self.ctx, self.vm
        vm.Y = c.FRAME
        vm.wr(c.FRAME, c.MSGBUF)
        try:
            why, pc = vm.run(entry, max_steps=self.args.steps)
        except RuntimeError as e:
            print('STOPPED in %s: %s' % (title, e))
            return 1
        if self.args.brief:
            traps = [self.names.get(t, 'trap_%02x' % t) for t, _a, _b in vm.traps]
            spoke = ['SPEAK %#04x' % (v & 0xFFFF) for a_, v in vm.calls_seen
                     if a_ == c.SPEAK_ADDR]
            print('t=%6d  %s -> %s' % (self.now, title, ' '.join(
                [t.replace('Stream', 'S.').replace('Transform', 'T.').replace('Kalimba', 'K.')
                 for t in traps] + spoke)))
            for line in self.notes:
                if line.startswith(('!!', 'chunk', 'warn', 'MessageCancel', 'MessageFlush',
                                    'StreamPartition', 'SinkClose', 'Partition')):
                    print('    model: %s' % line)
        else:
            c.run_report(vm, self.names, 't=%6d  %s -> %s 0x%05X, ended %s at 0x%05X'
                         % (self.now, title, 'entry' if 'press' in title else 'handler', entry,
                            why, pc))
            for line in self.notes:
                print('    model: %s' % line)
        if not self.args.brief:
            for line in self.dsp['log']:
                print('    dsp: %s' % line)
        self.dsp['log'] = []
        self.notes = []
        return 0

    # ------------------------------------------------------------------ the report
    def level_name(self, b):
        return 'quiet (b&2: shift 4, -18 dB at the cbops)' if b & 2 else 'loud (shift 7)'

    def summary(self):
        a = self.args
        print('\n== world summary (MODEL; see docs/deep/offline-2026-10-10/cavesim-changes.md)')
        print('stopped: %s' % (self.loop_stop_reason or 'n/a'))
        print('chunks started: %d, ended: %d' % (len([c for c in self.chunks if c.start is not None]),
                                                 self.ended_count()))
        for c in self.chunks:
            if c.start is None:
                print('  #%d created at %d ms, NEVER STARTED' % (c.k, c.created))
                continue
            print('  #%d start %6d ms  %-28s %5d Hz  b=%#x %-6s  %6d ms  EOF %6d  end %6d%s'
                  % (c.k, c.start, c.path, c.rate, c.b, 'quiet' if c.b & 2 else 'loud', c.dur,
                     c.eof, c.end, '  (cut: %s)' % c.cut if c.cut else ''))
        starts = [c.start for c in self.chunks if c.start is not None]
        if len(starts) > 1:
            print('  chunk-to-chunk start gaps (ms): %s' % ', '.join(
                str(b - x) for x, b in zip(starts, starts[1:])))
            gaps = [self.chunks[i + 1].start - self.chunks[i].end
                    for i in range(len(self.chunks) - 1)
                    if self.chunks[i].start is not None and self.chunks[i + 1].start is not None]
            print('  silence between chunks (ms, audible end -> next start): %s'
                  % ', '.join(str(g) for g in gaps))
        print('spoken: %s' % (', '.join('%#04x@%d' % (i, t) for t, i in self.spoken) or '(nothing)'))
        if getattr(self.args, 'audio_busy', False):
            print('audio busy: now %#06x; SetAudioBusy calls: %s%s' % (self.audio_busy, ', '.join('%d@%d' % (v, t) for t, v in self.busy_log) or 'none', '; a disconnect is still PARKED' if self.pending_disc else ''))
        if self.stock_world:
            print('stock world: outcome %s; parked at the end: %s; log: %s' % (
                'REBOOT at %d ms' % self.rebooted if self.rebooted is not None else 'no reboot',
                ', '.join(self.stock_queue) or 'none', '; '.join('%d ms %s' % (t, x) for t, x in self.stock_log) or 'none'))
        print('presses: %d swallowed, %d replayed to the stock' % (self.swallowed, self.replays))
        _flag = getattr(self.args, 'flag_id', None)
        _fid = int(_flag, 16) if _flag else None
        if _fid is not None:
            print('mode flag (id %#x) pending: %s' % (_fid, 'yes' if any(e['id'] == _fid for e in self.pending(self.task)) else 'no'))
        left = [e for e in self.pending(self.task) if e['id'] != _fid]
        print('cave messages still pending: %d%s' % (
            len(left), (' (' + ', '.join('id %#x due %d ms' % (e['id'], e['t']) for e in left) + ')')
            if left else ''))
        print('DSP: %s' % ('loaded' if self.dsp['loaded'] else 'unloaded'))
        if self.sources:
            leaked = [s for s in self.sources.values() if not s['closed']]
            print('file sources: %d opened, %d never closed (the stock closes only its own)'
                  % (len(self.sources), len(leaked)))
        if self.raw_sources or self.raw_calls:
            leaked = [h for h, s in self.raw_sources.items() if not s['closed']]
            print('raw partition sources (trap 0xD3): %d call(s), %d handle(s), %d never closed, %d SourceDrop '
                  'call(s), synthesised-stub calls %s' % (len(self.raw_calls), len(self.raw_sources), len(leaked),
                                                          self.raw_drops, dict(sorted(self.synth_calls.items()))))
            for h in leaked:
                self.warnings.append((self.now, 'raw source %#06x never closed (its MMU buffer would leak)' % h))
        if self.p2['erased']:
            print('partition 2: erase issued; %d claims, %d flushes, %d bytes; digest %s; closed=%s'
                  % (self.p2['claims'], self.p2['flushes'], self.p2['bytes'], self.p2['digest'],
                     self.p2['closed']))
        if a.p2_capture:
            import hashlib
            blob = b''.join(self.p2_capture)
            with open(a.p2_capture, 'wb') as f:
                f.write(blob)
            print('p2 capture: %d flushes, %d bytes -> %s (sha256 %s)'
                  % (len(self.p2_capture), len(blob), a.p2_capture,
                     hashlib.sha256(blob).hexdigest()))
        for c in self.chunks:
            if c.start is None:
                self.warnings.append((c.created, 'transform %#06x created and never started '
                                                 '(the sink stays held)' % c.handle))
        for c in self.chunks:
            for t, o, n in c.level_log:
                print('  chunk %d level word b %#x -> %#x at %d ms (stock 0x1072)' % (c.k, o, n, t))
            for t, cut in c.splices:
                print('  chunk %d purged by the stock 0x1072 at %d ms: up to %.1f ms of tail cut'
                      % (c.k, t, cut))
        if a.voice_field:
            print('stock voice-recognition requests (predicted, T04): %s; centre short presses '
                  'converted to 0x4004: %d; field now %d'
                  % (', '.join('%s@%d' % (k_, t_) for t_, k_ in self.requests) or 'none',
                     self.converted, self.field))
        for t, m in self.hazard_notes:
            print('!! t=%d ms: %s' % (t, m))
        if self.stale_sink_task:
            print('note: the stock 0x1072 left MessageSinkTask(ksink) on the stock plug-in task '
                  '(T04: fn_31a7c sets it before the connect); cleared by the next 0x1080')
        for t, m in self.warnings:
            print('warning t=%d: %s' % (t, m))
        for t, r, m in self.waived:
            print('waived %s t=%d ms (--allow): %s' % (r, t, m))
        if self.violations:
            print('port-3 rules: %d VIOLATION(S)' % len(self.violations))
            for t, r, m in self.violations:
                print('  %s t=%d ms: %s' % (r, t, m))
        else:
            print('port-3 rules: OK (R1 no 0x1072 while busy, R2 no teardown of a running '
                  'transform, R3 no SPEAK while port 3 is ours, R4 no stacked transform, '
                  'R5 poll >= %d ms, R6 one chain%s)' % (
                      a.poll_floor, ', W1 nothing into a non-sbc DSP' if self.wrong_windows
                      else ''))

    def check_expect(self):
        """--expect KEY=VAL; returns 0 if all hold."""
        bad = 0
        left = self.pending(self.task)
        have = {
            'chunks': str(len([c for c in self.chunks if c.start is not None])),
            'ended': str(self.ended_count()),
            'spoken': ','.join('%x' % i for _t, i in self.spoken),
            'violations': str(len(self.violations)),
            'rules': ','.join(sorted({r for _t, r, _m in self.violations})),
            'pending': str(len(left)),
            'swallowed': str(self.swallowed),
            'replayed': str(self.replays),
            'dsp': 'loaded' if self.dsp['loaded'] else 'unloaded',
            'looping': 'yes' if self.started_after_cap else 'no',
            'converted': str(self.converted),
            'field': str(self.field),
            'hazards': str(len(self.hazard_notes)),
            'cut': str(len([c for c in self.chunks if c.cut])),
            'rawopen': str(len(self.raw_sources)),
            'rawclosed': str(len([1 for s in self.raw_sources.values() if s['closed']])),
            'rawdrops': str(self.raw_drops),
            'rawmaps': str(sum(s['maps'] for s in self.raw_sources.values())),
            'rawcalls': str(len(self.raw_calls)),
            'rawexhausted': str(self.raw_exhausted),
            'flushes': str(self.p2['flushes']),
            'p2closed': str(self.p2['closed']),
            'getinfo': str(self.getinfo_n),
        }
        for spec in self.args.expect:
            k, _, v = spec.partition('=')
            ok = have.get(k) == v
            print('expect %-10s = %-14s %s%s' % (k, v, 'PASS' if ok else 'FAIL',
                                                 '' if ok else ' (have %r)' % have.get(k)))
            bad += 0 if ok else 1
        return 1 if bad else 0
