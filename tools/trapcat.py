#!/usr/bin/env python3
"""trapcat: the stack's VM trap catalogue, its argument forms and its stream-object class table, re-derived.

Read-only and offline.  Reads three files and nothing else; touches no device, writes no file:

    build/analysis/stack-disasm.txt             the Bluetooth stack disassembly (WORD INDICES, not vm.app addresses)
    firmware/bose/extracted/stack_const.bin     the extracted constant pool of the official stack (little-endian words)
    tools/traps-bluelab73.json                  trap names (BlueLab 7.3 numbering; the app is VM 19.0)

What it prints (default: everything; every figure is computed, none is typed in):

 1. the trap catalogue, slots 0x00..0xE2: name, form, bank, shim address, shim head.  The table is a list of
    (M, A) word pairs: A = const word 0x103e + 2n, M = const word 0x103d + 2n; bank = (M & 0xff) - 1,
    shim = (bank << 16) + A - 10, form = M >> 8.  (T01 corrected the old pairing, which read M one slot late.)
 2. the argument forms: the dispatcher 0x01ef66 jumps through a table of 21 two-word `bra` entries at
    0x01ef8b + 2*form (brxl: target = next word + X, X = 2*form).  Form 0 is the FAULT entry (the ten
    unimplemented (0,0) slots land there); forms 1..20 are the twenty real argument forms.  For each form the
    code is traced from its entry to the indirect call and the epilogue: which VM argument slots it reads
    (AL, AH, v3..v6 = the VM frame words 3..6 via `ld X,@(-1,Y)`), whether it packs a 32-bit value
    (`asl #0x10`), and the return class (R16 = AL zero-extended, R32 = AH:AL, R0 = void, result 0).
 3. the stream-object classes: every caller of the single allocator 0x9c32 (18 sites) with its class
    constant, the class words that matter (w0:w1 destroy hook, w4 sink-op table, w7 source-op table,
    w8:w9 post-drop hook, w11 kind/side), the creator function and the traps that reach it (call-graph walk).
 4. the checks, among them the 210/7/10 split of T01 (210 shims that start at an `enterl`, 7 that do not,
    10 unimplemented) next to the refined split (a shim that starts `sub Y,#1 ; enterl` is an enterl shim).

Usage:
    python tools/trapcat.py                   # everything
    python tools/trapcat.py --catalogue       # section 1 only
    python tools/trapcat.py --forms           # section 2 only
    python tools/trapcat.py --classes         # section 3 only
    python tools/trapcat.py --checks          # section 4 only
    python tools/trapcat.py --trap 0xD3       # one slot in full
    python tools/trapcat.py --selftest        # asserts the pinned facts; exit 0 if all hold

Marks: the table words, the shim heads, the form tracer and the class words are read from the files (proven as
text).  The role labels in the class table are the project's own readings (see docs/deep/round3-2026-10-12/
R02-raw-source-0xd3-and-trap-catalogue.md); the `conf` column says how far each is trusted.
"""
import json
import os
import re
import struct
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
DISASM = os.path.join(ROOT, 'build', 'analysis', 'stack-disasm.txt')
CONST = os.path.join(ROOT, 'firmware', 'bose', 'extracted', 'stack_const.bin')
TRAPS = os.path.join(ROOT, 'tools', 'traps-bluelab73.json')

LAST_TRAP = 0xE2              # dispatcher bound: cmp X,#0xe2 at 0x01ef70
TABLE_M = 0x103d              # const word of M for slot 0; A is at 0x103e
DISPATCH = 0x01ef66           # vm trap dispatcher
FORM_TABLE = 0x01ef8b         # brxl base: entry for form f at FORM_TABLE + 2*f
ALLOC = 0x9c32                # the single stream-object allocator
RET16, RET32, RET0 = 0x1f093, 0x1f0a0, 0x1f09e
FAULT = 0x1f099

# role labels: (label, confidence).  Everything in this dict is interpretation, not text.
CLASS_LABEL = {
    0x03dc: ('Kalimba port (trap 0x87 StreamKalimbaSink)', 'proven'),
    0x03f9: ('duplex connection stream, two MMU buffers (created in a message handler)', 'hypothesis'),
    0x0408: ('audio source/sink (traps 0x6b, 0x6c)', 'well-supported'),
    0x0d93: ('UART sink (trap 0x68)', 'well-supported'),
    0x0da7: ('single-buffer stream made by 0x18516 (reached from TestPerform_ 0x97 and a task table)', 'unknown'),
    0x18ba: ('USB interface (trap 0x9b)', 'well-supported'),
    0x18c6: ('USB endpoints (trap 0x9c)', 'well-supported'),
    0x18d5: ('two-buffer stream made by 0x30264 (task-table handler)', 'unknown'),
    0x196a: ('host sink (trap 0x67)', 'well-supported'),
    0x1f97: ('internal MMU buffer (intermediate buffer of the transforms); never handed to the VM', 'well-supported'),
    0x24c0: ('two-buffer stream made by 0x50e6d (task-table handler)', 'unknown'),
    0x25d6: ('PARTITION SINK (StreamPartitionOverwriteSink 0xCB / ResumeSink 0xDC): flash writer', 'well-supported'),
    0x2634: ('hardware-backed duplex stream made by 0x54ef0 (task-table handler)', 'unknown'),
    0x2648: ('single-buffer stream made by 0x550f8 (message handler 0x55137)', 'unknown'),
    0x267c: ('region source (trap 0x5f)', 'well-supported'),
    0x2694: ('ringtone source (trap 0x6a)', 'well-supported'),
    0x26af: ('file source (trap 0x86)', 'proven'),
    0x26f5: ('RAW SERIAL / SPIFLASH SOURCE (traps 0xd3 PartitionGetRawSerialSource, 0xb9 StreamSpiflashSource)', 'proven'),
}


# ----------------------------------------------------------------------------- loading

def load():
    """-> (code, W, names): code = {addr: (words, text)}, W = const words, names = {n: name}."""
    rx = re.compile(r'^\s+0x([0-9a-f]+): ((?:[0-9a-f]{4} )+)\s*(.*)$')
    code = {}
    with open(DISASM, encoding='utf-8', errors='replace') as f:
        for ln in f:
            m = rx.match(ln)
            if m:
                code[int(m.group(1), 16)] = (tuple(m.group(2).split()), m.group(3).strip())
    with open(CONST, 'rb') as f:
        raw = f.read()
    W = struct.unpack('<%dH' % (len(raw) // 2), raw[:len(raw) // 2 * 2])
    with open(TRAPS) as f:
        by_name = json.load(f)
    names = {v: k for k, v in by_name.items()}
    return code, W, names


class World:
    def __init__(self):
        self.code, self.W, self.names = load()
        self.addrs = sorted(self.code)
        self.callers = {}
        for a, (w, t) in self.code.items():
            if t.startswith('bsr '):
                tg = self.target(a)
                if tg is not None:
                    self.callers.setdefault(tg, []).append(a)
        self._fs = {}

    # branch/call target: addr + nwords - 1 + operand (the rule of tools/disasm.py:109)
    def target(self, a):
        w, t = self.code[a]
        m = re.match(r'(?:bsr|bra|b[a-z?0-9]+) ([+-]\d+)$', t)
        if not m:
            return None
        return a + len(w) - 1 + int(m.group(1))

    def text(self, a):
        return self.code[a][1] if a in self.code else '?'

    def fstart(self, a):
        """start of the function containing a: nearest enterl at or below a (or the `sub Y,#n` just before it)."""
        if a in self._fs:
            return self._fs[a]
        k = a
        while k >= 0 and a - k < 4096:
            if k in self.code and self.code[k][1].startswith('enterl'):
                if (k - 1) in self.code and self.code[k - 1][1].startswith('sub Y,#'):
                    k -= 1
                self._fs[a] = k
                return k
            k -= 1
        self._fs[a] = None
        return None

    def codeptr(self, hi, lo):
        """const-pool code pointer (hi, lo) -> stack word index, or None for the null pair."""
        if hi == 0:
            return None
        return ((hi - 1) << 16) + lo - 10

    # ------------------------------------------------------------------ trap table
    def slot(self, n):
        M = self.W[TABLE_M + 2 * n]
        A = self.W[TABLE_M + 1 + 2 * n]
        low = M & 0xff
        shim = (((low - 1) << 16) + A - 10) if low else None
        return {'n': n, 'M': M, 'A': A, 'bank': (low - 1) if low else None, 'form': M >> 8, 'shim': shim,
                'name': self.names.get(n, '?')}

    def shim_kind(self, shim):
        """('enterl', N) | ('sub+enterl', N) | ('leaf', ninstr) | ('body', ninstr)"""
        if shim is None:
            return ('none', 0)
        t = self.text(shim)
        if t.startswith('enterl'):
            return ('enterl', int(t.split()[1]))
        if t.startswith('sub Y,#') and self.text(shim + 1).startswith('enterl'):
            return ('sub+enterl', int(self.text(shim + 1).split()[1]))
        # frameless body: count instructions to the first rts, note branches and calls
        n, branchy = 0, False
        for a in self.addrs[self.addrs.index(shim):self.addrs.index(shim) + 64]:
            n += 1
            tx = self.text(a)
            if tx.startswith(('b', 'tst')) and not tx.startswith('bsr') and tx.split()[0] in (
                    'beq', 'bne', 'bcc', 'bcs', 'bcz', 'bgt', 'bge', 'ble', 'bra') or tx.startswith('b?'):
                branchy = True
            if tx.startswith('bsr'):
                branchy = True
            if tx.startswith('rts'):
                break
        return ('body' if branchy else 'leaf', n)

    # ------------------------------------------------------------------ forms
    def form_entries(self):
        """{form: code entry address} from the 21 two-word bra entries at FORM_TABLE."""
        out = {}
        for f in range(21):
            a = FORM_TABLE + 2 * f
            tg = self.target(a)
            out[f] = tg
        return out

    def trace_form(self, entry):
        """Follow straight-line code from a form entry (taking unconditional bra's) to the epilogue.
        -> dict(reads=sorted list, pack32=bool, ret='R16'|'R32'|'R0'|'FAULT', calls=1)"""
        reads, pack32, a, steps, called, ret = set(), False, entry, 0, False, None
        vm = False                                  # X holds the VM frame pointer after ld X,@(-1,Y)
        while steps < 200:
            steps += 1
            if a not in self.code:
                a += 1
                continue
            if a in (RET16, RET0, RET32) and called:
                # fell into an epilogue label: 0x1f093 = ld AH,#0 ; bra 0x1f0a0 (R16), 0x1f09e = AH=AL=0 (R0), 0x1f0a0 = leavel (R32)
                ret = {RET16: 'R16', RET0: 'R0', RET32: 'R32'}[a]
                break
            t = self.text(a)
            if t.startswith('ld X,@(-1,Y)'):
                vm = True
            elif t.startswith('ld ') and re.match(r'ld [A-Z]+,@\((\d+),X\)$', t) and vm:
                k = int(re.search(r'\((\d+),X\)', t).group(1))
                if 3 <= k <= 6:
                    reads.add('v%d' % k)
            elif t.startswith('ld X,@(') and ',X)' in t and vm:
                k = int(re.search(r'\((\d+),X\)', t).group(1))
                if 3 <= k <= 6:
                    reads.add('v%d' % k)
            if t == 'ld AL,@(6,Y)':
                reads.add('AL')
            if t == 'ld AH,@(7,Y)':
                reads.add('AH')
            if t == 'ld AL,@(7,Y)':
                reads.add('AH')                     # the saved AH used as a 32-bit pack source
            if t.startswith('asl #0x10'):
                pack32 = True
            if t.startswith('?0e 4'):
                called = True                       # the indirect call is `?0e 4 ; bsr +5` (far call via @(4,Y),@(5,Y))
            if t.startswith('bra '):
                tg = self.target(a)
                if tg in (RET16, RET0, RET32):
                    # 0x1f093 = ld AH,#0 ; bra 0x1f0a0 -> R16;  0x1f09e = AH=AL=0 -> R0;  0x1f0a0 = leavel -> R32
                    ret = {RET16: 'R16', RET0: 'R0', RET32: 'R32'}[tg]
                    break
                if tg == FAULT:
                    ret = 'FAULT'
                    break
                a = tg
                continue
            a += 1
        return {'reads': sorted(reads, key=lambda s: ('AL', 'AH', 'v3', 'v4', 'v5', 'v6').index(s)),
                'pack32': pack32, 'ret': ret, 'called': called}

    # ------------------------------------------------------------------ classes
    def class_sites(self):
        """[(call_site, class_constant)] for every `bsr` to the allocator: the class constant is the
        `ld AL,#imm` (2-word form) closest before the call."""
        out = []
        for c in sorted(self.callers.get(ALLOC, [])):
            k = c
            cls = None
            for _ in range(14):
                k -= 1
                while k not in self.code and k > c - 40:
                    k -= 1
                if k in self.code and self.code[k][1].startswith('ld AL,#') and len(self.code[k][0]) == 2:
                    cls = int(self.code[k][1].split('#')[1], 16)
                    break
            out.append((c, cls))
        return out

    def reach(self, f, depth=10):
        """traps whose shim reaches function f within `depth` caller hops -> sorted [(n, name, hops)]"""
        shimrev = {}
        for n in range(LAST_TRAP + 1):
            s = self.slot(n)['shim']
            if s is not None:
                shimrev.setdefault(s, []).append(n)
        seen = {f: 0}
        front = [f]
        found = {}
        for d in range(depth + 1):
            nxt = []
            for g in front:
                for n in shimrev.get(g, []):
                    found.setdefault(n, d)
                for c in self.callers.get(g, []):
                    h = self.fstart(c)
                    if h is not None and h not in seen:
                        seen[h] = d + 1
                        nxt.append(h)
            front = nxt
        return sorted((n, self.names.get(n, '?'), d) for n, d in found.items())


# ----------------------------------------------------------------------------- reports

def catalogue(w, out):
    out.append('== 1. TRAP CATALOGUE (slots 0x00..0x%02X; shim = stack word index) ==' % LAST_TRAP)
    out.append('slot  name                                 form bank shim      kind        head')
    for n in range(LAST_TRAP + 1):
        s = w.slot(n)
        if s['shim'] is None:
            out.append('0x%02x  %-36s %4d  -    UNIMPLEMENTED (M = A = 0)' % (n, s['name'], s['form']))
            continue
        kind = w.shim_kind(s['shim'])
        head = w.text(s['shim'])
        out.append('0x%02x  %-36s %4d %4d 0x%06x  %-10s  %s' % (
            n, s['name'], s['form'], s['bank'], s['shim'],
            ('%s %d' % kind) if kind[0] in ('enterl', 'sub+enterl') else '%s/%d' % kind, head))


def forms(w, out):
    ent = w.form_entries()
    hist = {}
    for n in range(LAST_TRAP + 1):
        hist.setdefault(w.slot(n)['form'], []).append(n)
    out.append('== 2. ARGUMENT FORMS (dispatcher 0x%06x; table of %d bra entries at 0x%06x + 2*form) ==' % (
        DISPATCH, len(ent), FORM_TABLE))
    out.append('form entry     traps reads(VM args)            pack32 ret    example traps')
    for f in range(21):
        tg = ent[f]
        if f == 0:
            tr = {'reads': [], 'pack32': False, 'ret': 'FAULT'}
        else:
            tr = w.trace_form(tg)
        ex = ', '.join('%s' % w.names.get(n, '?') for n in hist.get(f, [])[:3])
        out.append('%4d 0x%06x %5d %-28s %-6s %-6s %s' % (
            f, tg, len(hist.get(f, [])), ','.join(tr['reads']) or '-', 'yes' if tr['pack32'] else '-', tr['ret'], ex))
    out.append('(AL, AH = the VM registers at the trap; v3..v6 = VM frame words 3..6, the 3rd..6th C arguments;')
    out.append(' pack32 = a uint32 is assembled from two words with asl #0x10; R16/R32/R0 = return class)')


def classes(w, out):
    sites = w.class_sites()
    out.append('== 3. STREAM-OBJECT CLASSES (callers of the allocator 0x%04x: %d sites) ==' % (ALLOC, len(sites)))
    out.append('class  site      creator   w11    kind side destroy   sink-ops source-ops post-drop  traps (call hops, <=6) label [conf]')
    for c, cls in sites:
        W = w.W
        w11 = W[cls + 11]
        kind, side = (w11 >> 10) & 7, w11 >> 13

        def cp(i):
            p = w.codeptr(W[cls + i], W[cls + i + 1])
            return '0x%06x' % p if p is not None else '-'
        tr = sorted(w.reach(w.fstart(c), 6), key=lambda x: (x[2], x[0]))
        trs = ','.join('0x%02x(%d)' % (n, d) for n, nm, d in tr[:4]) or '-'
        if len(tr) > 4:
            trs += '+%d' % (len(tr) - 4)
        lab = CLASS_LABEL.get(cls, ('?', 'unknown'))
        out.append('0x%04x 0x%06x 0x%06x 0x%04x %4d %4d %-9s 0x%04x   0x%04x     %-9s  %-18s %s [%s]' % (
            cls, c, w.fstart(c), w11, kind, side, cp(0), W[cls + 4], W[cls + 7], cp(8), trs, lab[0], lab[1]))
    out.append('(traps = shims that reach the creator by bsr within 6 caller hops; a static over-approximation, "-" = created')
    out.append(' only through a request queue or a task table, i.e. no bsr path from any trap shim)')
    out.append('(w0:w1 = destroy hook called by the close routine 0x9b73; w4/w7 = sink-side/source-side op tables;')
    out.append(' w8:w9 = post-drop hook called by 0x9bdc/0x9a34; kind = (w11>>10)&7 source role, side = w11>>13 sink role)')
    # op tables of the classes of interest
    out.append('op tables (entry -> code): ')
    for t, nm in ((0xfb2, 'Kalimba sink-side'), (0xfba, 'Kalimba source-side'), (0xfce, 'MMU sink-side'),
                  (0xfd6, 'MMU source-side'), (0xfe2, 'raw-serial source-side'), (0x392a, 'source-only classes, sink side'),
                  (0x26bb, 'file source-side'), (0x2688, 'region source-side'), (0x26a0, 'ringtone source-side')):
        es = []
        for i in range(4):
            p = w.codeptr(w.W[t + 2 * i], w.W[t + 2 * i + 1])
            es.append('0x%06x' % p if p is not None else '-')
        out.append('  0x%04x %-34s %s' % (t, nm, ' '.join(es)))


def splits(w):
    legacy = {'enterl_at_shim': 0, 'other': [], 'unimplemented': 0}
    refined = {'enterl_family': 0, 'leaf': [], 'body': [], 'unimplemented': 0}
    shims = []
    banks = {}
    for n in range(LAST_TRAP + 1):
        s = w.slot(n)
        if s['shim'] is None:
            legacy['unimplemented'] += 1
            refined['unimplemented'] += 1
            continue
        shims.append(s['shim'])
        banks[s['bank']] = banks.get(s['bank'], 0) + 1
        k = w.shim_kind(s['shim'])
        if k[0] == 'enterl':
            legacy['enterl_at_shim'] += 1
            refined['enterl_family'] += 1
        else:
            legacy['other'].append(n)
            if k[0] == 'sub+enterl':
                refined['enterl_family'] += 1
            elif k[0] == 'leaf':
                refined['leaf'].append(n)
            else:
                refined['body'].append(n)
    return legacy, refined, shims, banks


def checks(w, out):
    legacy, refined, shims, banks = splits(w)
    res = []

    def chk(name, ok, detail):
        res.append(ok)
        out.append('  [%s] %s: %s' % ('OK' if ok else 'FAIL', name, detail))
    out.append('== 4. CHECKS ==')
    chk('bound', w.text(0x01ef70) == 'cmp X,#0xe2' and w.text(0x01ef72).startswith('bcz') and w.target(0x01ef73) == FAULT,
        '0x01ef70 "%s", 0x01ef72 "%s", 0x01ef73 "%s" -> 0x%x' % (
            w.text(0x01ef70), w.text(0x01ef72), w.text(0x01ef73), w.target(0x01ef73) or 0))
    chk('slots', LAST_TRAP + 1 == 227, '%d slots 0x00..0x%02X' % (LAST_TRAP + 1, LAST_TRAP))
    chk('210/7/10 (T01 split)', (legacy['enterl_at_shim'], len(legacy['other']), legacy['unimplemented']) == (210, 7, 10),
        '%d shims start at an enterl, %d do not (%s), %d unimplemented' % (
            legacy['enterl_at_shim'], len(legacy['other']), ' '.join('0x%02x' % n for n in legacy['other']),
            legacy['unimplemented']))
    chk('refined split', (refined['enterl_family'], len(refined['leaf']), len(refined['body']), refined['unimplemented'])
        == (211, 5, 1, 10),
        '%d enterl-family (incl. "sub Y,#1 ; enterl"), %d leaf (%s), %d frameless body (%s), %d unimplemented' % (
            refined['enterl_family'], len(refined['leaf']), ' '.join('0x%02x' % n for n in refined['leaf']),
            len(refined['body']), ' '.join('0x%02x' % n for n in refined['body']), refined['unimplemented']))
    chk('distinct shims', len(shims) == 217 and len(set(shims)) == 217, '%d implemented, %d distinct' % (len(shims), len(set(shims))))
    chk('banks', banks == {3: 214, 1: 3}, 'bank counts %s' % dict(sorted(banks.items())))
    unimpl = [n for n in range(LAST_TRAP + 1) if w.slot(n)['shim'] is None]
    chk('unimplemented list', unimpl == [0x2c, 0x2f, 0x96, 0xaf, 0xc0, 0xc1, 0xca, 0xd9, 0xda, 0xdb],
        ' '.join('0x%02x' % n for n in unimpl))
    fz = [w.slot(n)['form'] for n in range(LAST_TRAP + 1)]
    ok = all(f == 0 for n, f in zip(range(LAST_TRAP + 1), fz) if w.slot(n)['shim'] is None) and \
        all(1 <= f <= 20 for n, f in zip(range(LAST_TRAP + 1), fz) if w.slot(n)['shim'] is not None)
    chk('forms', ok, 'unimplemented slots are form 0 (the fault entry); implemented slots use forms %d..%d' % (
        min(f for n, f in zip(range(LAST_TRAP + 1), fz) if w.slot(n)['shim'] is not None), max(fz)))
    ent = w.form_entries()
    chk('form table', ent[0] == FAULT and all(ent[f] is not None and ent[f] > FORM_TABLE + 40 for f in range(1, 21)),
        'form 0 -> 0x%x (fault); forms 1..20 -> %s' % (ent[0], ' '.join('%x' % ent[f] for f in range(1, 21))))
    nxt = w.slot(LAST_TRAP + 1)
    chk('table end', nxt['M'] == 0 and nxt['A'] == 0, 'slot 0xE3 reads (M, A) = (0x%x, 0x%x)' % (nxt['M'], nxt['A']))
    sites = w.class_sites()
    cl = sorted(set(c for _, c in sites))
    chk('classes', len(sites) == 18 and len(cl) == 18 and None not in cl,
        '%d allocator sites, %d distinct classes: %s' % (len(sites), len(cl), ' '.join('0x%x' % c for c in cl)))
    chk('no pipe class', not any('pipe' in CLASS_LABEL.get(c, ('', ''))[0].lower() for c in cl), 'no class is a pipe')
    s = w.slot(0xD3)
    chk('0xD3', s['name'] == 'PartitionGetRawSerialSource' and s['shim'] == 0x3ab04 and s['form'] == 3 and
        w.text(0x3ab04) == 'enterl -2', 'name %s shim 0x%x form %d head "%s"' % (s['name'], s['shim'], s['form'], w.text(0x3ab04)))
    out.append('  checks: %s' % ('ALL OK' if all(res) else 'FAILURES'))
    return all(res)


def one_trap(w, n, out):
    s = w.slot(n)
    out.append('trap 0x%02x %s' % (n, s['name']))
    out.append('  table pair: M = 0x%04x (bank byte 0x%02x, form %d), A = 0x%04x' % (s['M'], s['M'] & 0xff, s['form'], s['A']))
    if s['shim'] is None:
        out.append('  unimplemented: (0, 0); the dispatcher takes form 0 = the fault path')
        return
    out.append('  shim: stack word 0x%06x  (%s)' % (s['shim'], w.text(s['shim'])))
    ent = w.form_entries()
    tr = w.trace_form(ent[s['form']])
    out.append('  form %d at 0x%06x: reads %s, pack32 %s, return %s' % (
        s['form'], ent[s['form']], ','.join(tr['reads']) or '-', tr['pack32'], tr['ret']))
    a = s['shim']
    out.append('  first instructions of the shim:')
    i = w.addrs.index(a)
    for k in w.addrs[i:i + 12]:
        tg = w.target(k) if w.text(k).startswith('bsr') else None
        out.append('    0x%06x: %-14s %s%s' % (k, ' '.join(w.code[k][0]), w.text(k), ('  -> 0x%x' % tg) if tg else ''))


def report(w, sections):
    out = []
    if 'catalogue' in sections:
        catalogue(w, out)
        out.append('')
    if 'forms' in sections:
        forms(w, out)
        out.append('')
    if 'classes' in sections:
        classes(w, out)
        out.append('')
    ok = True
    if 'checks' in sections:
        ok = checks(w, out)
    return out, ok


def selftest():
    w = World()
    fails = []

    def need(name, cond):
        if not cond:
            fails.append(name)
    out1, ok1 = report(w, ('catalogue', 'forms', 'classes', 'checks'))
    out2, ok2 = report(w, ('catalogue', 'forms', 'classes', 'checks'))
    need('all checks hold', ok1 and ok2)
    need('deterministic output', out1 == out2)
    need('catalogue has 227 rows', sum(1 for l in out1 if re.match(r'^0x[0-9a-f]{2}  ', l)) == 227)
    # pinned facts (each is read from the files, here only asserted)
    s = w.slot(0xD3)
    need('0xD3 shim', s['shim'] == 0x3ab04 and s['form'] == 3)
    need('0x62 TransformAdpcmDecode shim', w.slot(0x62)['shim'] == 0x3a03e and w.slot(0x62)['form'] == 3)
    need('0xB9 StreamSpiflashSource form 18', w.slot(0xB9)['form'] == 18 and w.slot(0xB9)['shim'] == 0x3a9fc)
    need('0xCC PartitionMountFilesystem form 4', w.slot(0xCC)['form'] == 4 and w.slot(0xCC)['shim'] == 0x3ab68)
    need('0xD8 starts with sub Y,#1 ; enterl', w.shim_kind(w.slot(0xD8)['shim'])[0] == 'sub+enterl')
    ent = w.form_entries()
    need('form 3 entry', ent[3] == 0x1efbf)
    tr3 = w.trace_form(ent[3])
    need('form 3 = (AL, AH) -> R16', tr3['reads'] == ['AL', 'AH'] and tr3['ret'] == 'R16' and not tr3['pack32'])
    tr9 = w.trace_form(ent[9])
    need('form 9 packs a uint32 from v4, v5 and returns void', 'v4' in tr9['reads'] and 'v5' in tr9['reads'] and
         tr9['pack32'] and tr9['ret'] == 'R0')
    need('form 20 returns R32', w.trace_form(ent[20])['ret'] == 'R32')
    sites = dict((cls, c) for c, cls in w.class_sites())
    need('raw serial class creator 0x5620a', 0x26f5 in sites and w.fstart(sites[0x26f5]) == 0x5620a)
    W = w.W
    need('raw serial class words', w.codeptr(W[0x26f5], W[0x26f5 + 1]) == 0x561f2 and
         w.codeptr(W[0x26f5 + 8], W[0x26f5 + 9]) == 0x561bc and W[0x26f5 + 7] == 0x0fe2 and W[0x26f5 + 11] == 0x2400)
    need('0xD3 reaches class 0x26f5', 0xd3 in [n for n, nm, d in w.reach(w.fstart(sites[0x26f5]), 10)])
    need('partition sink creator has no bsr path from a shim', w.reach(w.fstart(sites[0x25d6]), 6) == [])
    need('partition sink close hook writes the DATA magic', w.codeptr(W[0x25d6], W[0x25d6 + 1]) == 0x54042 and
         w.text(0x0540da) == 'ld AH,#0x4441' and w.text(0x0540dd) == 'ld AL,#0x5441')
    need('mount requires partition type 1', w.text(0x01130d) == 'ld AL,#0x1' and w.target(0x01130e) == 0x2d146)
    need('raw source requires partition type 3', w.text(0x02d162) == 'ld AL,#0x3' and w.target(0x02d164) == 0x2d146)
    need('type test compares the table type with the key', w.text(0x02d155) == 'cmp AL,@(3,Y)')
    for f in fails:
        print('FAIL: ' + f)
    print('trapcat selftest: %s (%d checks failed)' % ('OK' if not fails else 'FAIL', len(fails)))
    return not fails


def main(argv):
    if argv and argv[0] == '--selftest':
        return 0 if selftest() else 1
    w = World()
    if argv and argv[0] == '--trap':
        out = []
        one_trap(w, int(argv[1], 0), out)
        print('\n'.join(out))
        return 0
    sel = {'--catalogue': 'catalogue', '--forms': 'forms', '--classes': 'classes', '--checks': 'checks'}
    sections = [sel[a] for a in argv if a in sel] or ['catalogue', 'forms', 'classes', 'checks']
    bad = [a for a in argv if a not in sel]
    if bad:
        print(__doc__.split('Usage:')[1].split('Marks:')[0])
        return 2
    out, ok = report(w, sections)
    print('\n'.join(out))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
