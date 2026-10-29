#!/usr/bin/env python3
"""h1_mutants.py: MUTATION CHECK of the probe203 / probe198c template builds (OFFLINE; no device tool).
    python build/hook/h1_mutants.py probe203|probe198c [--run]
Writes mutated copies of build/hook/<probe>_words.json into build/hook/mut_h1/<probe>/ (scratch, one changed instruction or constant each) and, with --run,
runs `gate_<probe>.py --first --words COPY` on each with 6 workers: every mutant must FAIL the gate ("survivors: []"). The mutation sites are found by
instruction pattern, so the list adapts to a changed parameter block (a site that no longer exists is reported and skipped)."""
import json, os, sys
sys.path.insert(0, 'tools')
import caveasm as ca
probe = sys.argv[1]
OUT = 'build/hook/mut_h1/%s/' % probe
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    os.unlink(OUT + f)
W = json.load(open('build/hook/%s_words.json' % probe))
A = sorted(int(k, 16) for k in W)
val = {a: W['0x%x' % a] for a in A}
names = []


def occ(seq):
    return [a for a in A if all(val.get(a + i) == w for i, w in enumerate(seq))]


def mut(name, edits):
    d = dict(W)
    for a, n in edits:
        assert hex(a) in d, hex(a)
        d[hex(a)] = n
    json.dump(d, open(OUT + name + '.json', 'w'), indent=0)
    names.append(name)
    print('wrote %-9s %s' % (name, [(hex(a), '%04x' % val[a], '%04x' % n) for a, n in edits][:3]))


def sub(name, old, new):
    o = occ(list(old))
    print(name, 'sites', [hex(x) for x in o])
    if not o:
        print('   (no site: skipped)')
        return
    for k, a in enumerate(o):
        mut('%s_%d' % (name, k), [(a + i, new[i]) for i in range(len(old)) if new[i] != old[i]])


cmpi = lambda v: list(ca.imm_words(v, 0x84))
ldi = lambda v: list(ca.imm_words(v, 0x14))
sub('g13', cmpi(13), cmpi(14))
sub('g3', cmpi(3), cmpi(2))
sub('lev', [(21 << 8) | 0x27], [(29 << 8) | 0x27])
if probe == 'probe203':
    LBL = json.load(open('build/hook/probe203_labels.json'))
    sub('id1', ldi(0x30), ldi(0x31))
    sub('id0', ldi(0x3B), ldi(0x3C))
    sub('c4', cmpi(4), cmpi(3))
    sub('add4', [0xFC34], [0xFD34])
    sub('c1', cmpi(1), cmpi(2))
    sub('c2', cmpi(2), cmpi(3))
    sub('c100', cmpi(100), cmpi(99))
    sub('d64', [0x4010], [0x3F10])
    sub('ptadd', [(4 << 8) | 0x37], [(3 << 8) | 0x37])
    sub('cls1', [0x0114], [0x0214])
    sub('cls2', [0x0214], [0x0314])
    sub('cls3', [0x0314], [0x0414])
    sub('cls4', [0x0414], [0x0514])
    sub('and4', [0x04C4], [0x08C4])
    sub('and2', [0x02C4], [0x04C4])
    sub('and1', [0x01C4], [0x02C4])
    sub('subs', [(8 << 8) | 0x57], [(9 << 8) | 0x57])
    sub('cmpe1', [(1 << 8) | 0x86], [0x0086])
    sub('cmp3', cmpi(3), cmpi(4))
    sub('cK', cmpi(14), cmpi(13))
    sub('cLast', cmpi(0x12 + 14), cmpi(0x12 + 13))
    # the window items: every word changed in turn (the drop count by -1, the pair bytes by xor 1), and the pointer table entries
    for i in range(3):
        a0 = LBL['WIN%d' % i]
        for k in range(7):
            new = val[a0 + k] - 1 if k == 0 else val[a0 + k] ^ (0x80 if k >= 5 else 1)      # the third pair: a flipped HIGH bit (a flipped low bit can still occur elsewhere in the stock file)
            mut('win%d_%d' % (i, k), [(a0 + k, new)])
    p0 = LBL['PT']
    mut('pt1', [(p0 + 1, val[p0 + 0])])
    mut('pt2', [(p0 + 2, val[p0 + 1])])
    e = [a for a in A if val[a] == 0xF00B]; l = [a for a in A if val[a] == 0xF00F]
    print('TICK -16', [hex(x) for x in e], [hex(x) for x in l])
    mut('fr16', [(a, 0xF40B) for a in e] + [(a, 0xF40F) for a in l])
    e = [a for a in A if val[a] == 0xF60B]; l = [a for a in A if val[a] == 0xF60F]
    mut('fr10', [(a, 0xFA0B) for a in e] + [(a, 0xFA0F) for a in l])
else:   # probe198c
    sub('id30', ldi(0x30), ldi(0x31))
    sub('c21', cmpi(21), cmpi(22))
    sub('c64', cmpi(64), cmpi(63))
    sub('d64', [0x4010], [0x3F10])
    sub('x14', [0x0E10], [0x0D10])
    sub('look0', [(5 << 8) | 0x16], [(6 << 8) | 0x16])
    sub('look3', [(8 << 8) | 0x16], [(9 << 8) | 0x16])
    sub('addm', [(5 << 8) | 0x34], [(6 << 8) | 0x34])
    sub('c77', cmpi(0x77), cmpi(0x78))
    sub('c1320', ldi(1320), ldi(1319))
    sub('per', ldi(2106), ldi(2105))
    sub('cab', cmpi(15000), cmpi(15001))
    sub('c100', cmpi(2006), cmpi(2007))
    sub('c1000', cmpi(1000), cmpi(1001))
    e = [a for a in A if val[a] == 0xF60B]; l = [a for a in A if val[a] == 0xF60F]
    print('GLOOP -10', [hex(x) for x in e], [hex(x) for x in l])
    mut('fr10', [(a, 0xFA0B) for a in e] + [(a, 0xFA0F) for a in l])
open(OUT + 'names.txt', 'w').write('\n'.join(names))
print(len(names), 'mutants')

if '--run' in sys.argv:
    import concurrent.futures as cf
    import subprocess

    def run(n):
        r = subprocess.run([sys.executable, 'build/hook/gate_%s.py' % probe, '--first', '--words', OUT + n + '.json'], capture_output=True, text=True)
        fl = [l for l in r.stdout.splitlines() if l.startswith('FAIL')]
        return n, r.returncode, (fl[0][:100] if fl else 'NO FAIL')
    with cf.ThreadPoolExecutor(6) as ex:
        res = list(ex.map(run, names))
    for n, rc, l in res:
        print('%-10s rc=%d %s' % (n, rc, l))
    print('survivors:', [x[0] for x in res if x[1] == 0])
