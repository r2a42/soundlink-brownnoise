#!/usr/bin/env python3
"""Static analyzer for Bose SoundLink Micro vm.app (XAP2 VM bytecode).

Produces a function-level disassembly with:
  - function discovery: targets of bsr calls + the 0x291-thunk entries,
    bodies bounded by enterl/leavel balance (linear sweep with jump targets
    as instruction starts, shared with xapvm.decode)
  - trap-stub annotation (find_stubs + traps.json): every call site named
  - call graph + reverse xrefs per function
  - branch targets resolved, intra-function labels emitted
  - string candidates (ASCII and UTF-16LE) in const + tail regions
Outputs to build/analysis/:
  functions/<addr>.lst   per-function listing
  all_functions.txt      one index line per function (addr, size, calls out, called by)
  callgraph.txt          caller -> callee edges
  xrefs_<addr>.txt       reverse refs for one function (with -fn ADDR)
  strings.txt            string candidates
  globals.txt            words of the globals region with per-global xref counts
"""
import sys, os, json, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xapvm

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VM = os.path.join(ROOT, "firmware", "bose", "extracted", "internal_fs", "vm.app")
OUT = os.path.join(ROOT, "build", "analysis")

sext8 = lambda b: b - 0x100 if b & 0x80 else b


def load():
    w = xapvm.load_words(VM)
    return w


def analyze():
    w = load()
    code = w[0x18:]
    ins = list(xapvm.decode(code))
    start = {a: i for i, (a, op, v, ln) in enumerate(ins)}
    stubs, _ = xapvm.find_stubs(code)
    tt = xapvm.trap_table()
    stub_name = {a: tt.get(n, f"trap{n}") for a, n in stubs.items()}

    # ---- collect bsr sites and targets ----
    bsrs = []          # (site, target)
    branches = []      # (site, target, op)
    for a, op, v, ln in ins:
        if op == 0x9C:
            bsrs.append((a, (a + ln - 1 + v) & 0x3FFFF))
        elif op in (0xE0, 0xF0, 0xF4, 0xF8, 0xFC, 0x20, 0x24, 0x28, 0x2C, 0xE4):
            branches.append((a, (a + v) & 0x3FFFF, op))

    # ---- function discovery: bsr targets (+ entry-region helper 0x8a etc.) ----
    fentries = set(t for _, t in bsrs)
    # VM runtime entries referenced from the low region are included naturally
    fentries.discard(0x291)          # common trap dispatcher, not a function
    # add the 0x4003-dispatcher entry: discover separately by scan (it is
    # reached by the task mechanism, not bsr) - caller supplies extras
    funcs = sorted(fentries)

    # ---- bound functions: from entry, walk until an unconditional return
    # (leavel / rts) that no branch re-enters past; use the next entry or a
    # branch-target gap as the size bound. This is a heuristic used only for
    # listing; the decoder is the authority for instruction boundaries.
    btarget = set(t for _, t, _ in branches)
    bounds = {}
    for i, f in enumerate(funcs):
        if f not in start:
            continue                     # target lands mid-instruction (data or alias)
        nxt = funcs[i + 1] if i + 1 < len(funcs) else len(code)
        end = nxt
        # shrink to the last leavel/rts before any gap of unclaimed flow:
        j = start[f]
        lastret = None
        while j < len(ins) and ins[j][0] < end:
            a, op, v, ln = ins[j]
            if op in (0x0F, 0xE2) and (a + ln) >= end - 0:
                lastret = a + ln
            if a != f and a in btarget and a in fentries:
                end = a
                break
            j += 1
        bounds[f] = lastret or end

    os.makedirs(OUT, exist_ok=True)
    fdir = os.path.join(OUT, "functions")
    os.makedirs(fdir, exist_ok=True)

    calls_out = collections.defaultdict(set)
    called_by = collections.defaultdict(set)
    for site, tgt in bsrs:
        # which function contains site
        cont = None
        for f in funcs:
            if f <= site < bounds.get(f, f):
                cont = f
                break
        if cont is not None:
            calls_out[cont].add(tgt)
            called_by[tgt].add(cont)

    names = {}
    for a, n in stub_name.items():
        names[a] = n

    index_lines = []
    for f in funcs:
        if f not in start:
            index_lines.append(f"{f:#07x}  <not an instruction start in linear decode - data or alias>")
            continue
        lo, hi = f, min(bounds.get(f, f), len(code))
        lines = [f"function {f:#x} .. {hi:#x}  ({hi - f} words)"]
        if called_by[f]:
            lines.append("called by: " + ", ".join(f"{c:#x}" for c in sorted(called_by[f])))
        for a, op, v, ln in ins:
            if not (f <= a < hi):
                continue
            m = xapvm.mnemonic(op, v)
            ann = ""
            if op == 0x9C:
                tgt = (a + ln - 1 + v) & 0x3FFFF
                m += f"  -> {tgt:#x}"
                if tgt in names:
                    ann = f"   ; {names[tgt]}"
            elif op in (0xE0, 0xF0, 0xF4, 0xF8, 0xFC, 0x20, 0x24, 0x28, 0x2C, 0xE4):
                m += f"  -> {(a + v) & 0x3FFFF:#x}"
            elif a in names:
                ann = f"   ; TRAP {names[a]}"
            words = " ".join(f"{code[i]:04x}" for i in range(a, a + ln))
            lines.append(f"  {a:#07x}: {words:<12} {m}{ann}")
        open(os.path.join(fdir, f"{f:x}.lst"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
        outs = ", ".join(f"{t:#x}" + (f"({names[t]})" if t in names else "") for t in sorted(calls_out[f]))
        index_lines.append(f"{f:#07x}  size={hi - f:<6} callers={len(called_by[f]):<3} calls: {outs}")

    open(os.path.join(OUT, "all_functions.txt"), "w", encoding="utf-8").write("\n".join(index_lines) + "\n")
    with open(os.path.join(OUT, "callgraph.txt"), "w", encoding="utf-8") as fh:
        for f in sorted(calls_out):
            for t in sorted(calls_out[f]):
                fh.write(f"{f:#x} -> {t:#x}" + (f"  ({names[t]})" if t in names else "") + "\n")

    # ---- strings ----
    def ascii_strs(words, lo, hi):
        out, cur, cur_a = [], [], None
        for a in range(lo, min(hi, len(words))):
            cw = words[a]
            for b in (cw >> 8, cw & 0xFF):
                if 0x20 <= b < 0x7F:
                    if cur_a is None:
                        cur_a = a
                    cur.append(chr(b))
                else:
                    if len(cur) >= 5:
                        out.append((cur_a, "".join(cur)))
                    cur, cur_a = [], None
        if len(cur) >= 5:
            out.append((cur_a, "".join(cur)))
        return out

    def utf16_strs(words, lo, hi):
        out, cur, cur_a = [], [], None
        for a in range(lo, min(hi, len(words))):
            cw = words[a]
            ch = cw & 0xFF
            ok = (cw >> 8) == 0 and 0x20 <= ch < 0x7F
            if ok:
                if cur_a is None:
                    cur_a = a
                cur.append(chr(ch))
            else:
                if len(cur) >= 4:
                    out.append((cur_a, "".join(cur)))
                cur, cur_a = [], None
        if len(cur) >= 4:
            out.append((cur_a, "".join(cur)))
        return out

    const_start = 0x18 + w[6]
    str_out = ["-- ASCII in code+tail --"]
    str_out += [f"{a:#x}: {s}" for a, s in ascii_strs(code, 0, len(code))]
    str_out.append("-- UTF-16LE in code+tail --")
    str_out += [f"{a:#x}: {s}" for a, s in utf16_strs(code, 0, len(code))]
    open(os.path.join(OUT, "strings.txt"), "w", encoding="utf-8").write("\n".join(str_out) + "\n")

    # ---- globals: xref counts of @abs references ----
    gref = collections.Counter()
    for a, op, v, ln in ins:
        mode = op & 3
        if mode == 1 and 0x400 <= v < 0x740:
            gref[v] += 1
    with open(os.path.join(OUT, "globals.txt"), "w", encoding="utf-8") as fh:
        for g in sorted(gref):
            fh.write(f"{g:#05x}  refs={gref[g]}\n")

    # machine-readable dump
    json.dump({
        "functions": {hex(f): {"end": hex(bounds.get(f, f)), "callers": [hex(c) for c in sorted(called_by[f])],
                               "calls": [hex(t) for t in sorted(calls_out[f])]} for f in funcs},
        "stubs": {hex(a): n for a, n in stub_name.items()},
        "bsr_sites": {hex(s): hex(t) for s, t in bsrs},
        "branch_sites": {hex(s): [hex(t), op] for s, t, op in branches},
    }, open(os.path.join(OUT, "analysis.json"), "w"), indent=1)

    print(f"functions: {len(funcs)}; bsr sites: {len(bsrs)}; stubs: {len(stubs)}")
    print(f"output in {OUT}")


def xref(addr):
    w = load()
    code = w[0x18:]
    ins = list(xapvm.decode(code))
    stubs, _ = xapvm.find_stubs(code)
    tt = xapvm.trap_table()
    addr = int(addr, 0)
    print(f"== references to {addr:#x} ==")
    for a, op, v, ln in ins:
        if op == 0x9C and (a + ln - 1 + v) & 0x3FFFF == addr:
            print(f"  bsr from {a:#x}")
        elif op in (0xE0, 0xF0, 0xF4, 0xF8, 0xFC, 0x20, 0x24, 0x28, 0x2C, 0xE4) and (a + v) & 0x3FFFF == addr:
            print(f"  {xapvm.mnemonic(op, v).split()[0]} from {a:#x}")
        elif a == addr and a in stubs:
            print(f"  trap stub here: {tt.get(stubs[a])}")
        elif mode_ref(op, v, addr):
            print(f"  data ref from {a:#x}: {xapvm.mnemonic(op, v)}")


def mode_ref(op, v, addr):
    return (op & 3) == 1 and v == addr


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "-fn":
        xref(sys.argv[2])
    else:
        analyze()
