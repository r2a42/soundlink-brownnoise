#!/usr/bin/env python3
"""h1_delta.py: a quick DELTA REVIEW of two cave images (words.json files) of the same family (probe198c / probe203 builds with different parameters).
OFFLINE, read-only. Decodes both caves instruction by instruction (tools/xapvm decode over the stock vm.app with the cave words patched in), aligns the two
instruction streams (difflib) and prints only the blocks that differ, with the new image's addresses. A change of layout (an extra instruction pushing the
rest into the next band) shows up as a few inserted/removed instructions and, at most, changed branch/connector displacements.

    python build/hook/h1_delta.py build/hook/OLD_words.json build/hook/NEW_words.json
"""
import difflib
import json
import sys

sys.path.insert(0, 'tools')
sys.path.insert(0, 'tools/xapvm')
import xapvm  # noqa: E402


def stream(path, base):
    w = json.load(open(path))
    patched = list(base)
    cave = {int(k, 16): v for k, v in w.items()}
    for a, v in cave.items():
        patched[a] = v & 0xFFFF
    lo, hi = min(cave), max(cave)
    out = []
    for a, op, v, ln in xapvm.decode(patched, fold_zero=False):
        if a in cave:
            out.append((a, op, v, ln, tuple(patched[a:a + ln])))
    return out, len(cave)


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    base = xapvm.load_words('firmware/bose/extracted/internal_fs/vm.app')[0x18:]
    sa, na = stream(sys.argv[1], base)
    sb, nb = stream(sys.argv[2], base)
    ka = [x[4] for x in sa]
    kb = [x[4] for x in sb]
    sm = difflib.SequenceMatcher(None, ka, kb, autojunk=False)
    changed = 0
    print('old %s: %d words, %d instructions;  new %s: %d words, %d instructions' % (sys.argv[1], na, len(sa), sys.argv[2], nb, len(sb)))
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        changed += 1
        print('%s  old[%d:%d] new[%d:%d]' % (tag.upper(), i1, i2, j1, j2))
        for x in sa[i1:i2]:
            print('   - 0x%05x  %s' % (x[0], ' '.join('%04x' % t for t in x[4])))
        for x in sb[j1:j2]:
            print('   + 0x%05x  %s' % (x[0], ' '.join('%04x' % t for t in x[4])))
    print('%d differing block(s); %d of %d new instructions are identical to the old image' % (changed, sum(i2 - i1 for t, i1, i2, j1, j2 in sm.get_opcodes() if t == 'equal'), len(sb)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
