#!/usr/bin/env python3
"""stackdepth: how much VM stack is already in use where a cave is installed.

probe91 used `enterl -24` -- eight words more than any cave before it -- and left
the VM application non-responsive: Bluetooth up, every button dead, HID timing
out, DFU entry refused. The stack was the suspect, and `docs/roadmap.md` rule 0
now forbids raising a cave's frame without measuring the headroom first. This
measures it.

**The stack size is in the `vm.app` header, word [09].** Verified by building the
same app twice: `STACKSIZE=0` (auto) gave header[09] = 16 for a linker-reported
15, and `STACKSIZE=40` gave exactly 40. Bose's image declares **316 words**.

The depth *at the hook* is the sum of the `enterl` frames along the deepest call
path that reaches it. This walks the call graph backwards from a target address,
accumulating frame sizes, and reports the worst path -- so a cave's own frame can
be checked against what is left.

    python tools/stackdepth.py 0xAE0          # the hook site
    python tools/stackdepth.py 0xAE0 --frame 24

Caveats worth stating rather than hiding:

  * It follows **direct `bsr` edges only.** The firmware dispatches through
    switch tables and message handlers (`docs/switchtab.py`, `MessageLoop` at
    0x395F8), so a real path may be deeper than any static `bsr` chain.
  * Recursion is cut at the first repeat, so a recursive path is under-counted.
  * `enterl` operands are read from the decode; a function reached by `bra` into
    the middle of another has no frame of its own and is attributed to its host.

So treat the number as a **lower bound on depth**, i.e. an **upper bound on
headroom**. That is the conservative direction for deciding a frame size.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'xapvm'))
import xapvm                                                   # noqa: E402

APP = os.path.join(ROOT, 'firmware/bose/extracted/internal_fs/vm.app')
HDR_STACK = 0x09          # verified: header word [09] is the stack size in words


def load():
    words = xapvm.load_words(APP)
    return words, words[0x18:]


def build_graph(code):
    """(frame_of_function, callers_of_function, function_containing_address)."""
    ins = list(xapvm.decode(code))
    frame, owner, cur = {}, {}, None
    for a, op, v, ln in ins:
        if op == 0x0B:                            # enterl
            cur = a
            frame[a] = -v if v < 0 else v
        owner[a] = cur
    callers = {}
    for a, op, v, ln in ins:
        if op == 0x9C:                            # bsr
            t = (a + ln - 1 + v) & 0x3FFFF
            if t in frame:
                callers.setdefault(t, set()).add(owner.get(a))
    return frame, callers, owner


def deepest(fn, frame, callers, seen=None):
    """Deepest total frame size on any bsr path that reaches `fn`, with path."""
    if seen is None:
        seen = frozenset()
    if fn in seen or fn is None:
        return 0, []
    seen = seen | {fn}
    best, best_path = 0, []
    for c in callers.get(fn, ()):
        if c is None or c in seen:
            continue
        d, p = deepest(c, frame, callers, seen)
        if d >= best:
            best, best_path = d, p
    return frame.get(fn, 0) + best, [fn] + best_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('addr', help='code address the cave is installed at, e.g. 0xAE0')
    ap.add_argument('--frame', type=int, default=None,
                    help='proposed cave frame size, to check against the headroom')
    args = ap.parse_args()
    target = int(args.addr, 0)

    words, code = load()
    stack = words[HDR_STACK]
    frame, callers, owner = build_graph(code)
    sys.setrecursionlimit(10000)

    host = owner.get(target)
    if host is None:
        raise SystemExit('stackdepth: %#x is not inside a function with an enterl'
                         % target)
    depth, path = deepest(host, frame, callers)
    print('vm.app declares a stack of %d words (header[09])' % stack)
    print('%#x is inside the function at %#x (enterl -%d)'
          % (target, host, frame.get(host, 0)))
    print('deepest static bsr path reaching it: %d words over %d frames'
          % (depth, len(path)))
    for fn in path:
        print('    %#07x  enterl -%d' % (fn, frame.get(fn, 0)))
    head = stack - depth
    print('\nheadroom at that point: %d - %d = **%d words**' % (stack, depth, head))
    if args.frame is not None:
        verdict = 'FITS' if args.frame < head else 'DOES NOT FIT'
        print('a cave frame of %d words: %s (%d words would remain)'
              % (args.frame, verdict, head - args.frame))
    print('\nThis is a LOWER bound on depth: only direct bsr edges are followed,'
          '\nso the real path through the message loop and switch tables may be'
          '\ndeeper. Treat the headroom as an upper bound.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
