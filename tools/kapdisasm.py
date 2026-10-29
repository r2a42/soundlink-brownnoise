#!/usr/bin/env python3
"""kapdisasm: disassemble a Kalimba .kap with the ADK's own binutils.

`docs/firmware-map.md` called the four shipped `.kap` images "the largest single
unknown that bears on this project" -- every claim about Kalimba port 3 rested on an
analogy with the ADK's equivalent DSP source rather than on Bose's actual binary. The
analogy was mostly right and in one place **wrong** (the tone gain shift), which is
exactly the kind of thing an analogy gets wrong.

It turns out a Kalimba disassembler has been in the tree all along:
`adk/root/tools/bin/kobjdump.exe` lists `gordon` and `csr8670` among its supported
architectures, alongside `kmapper`, `kreadelf`, `knm`, `kobjcopy`, `ksize`, `kstrings`
and `kaddr2line`. All four images disassemble with **zero unknown opcodes** -- a far
better result than the XAP decoder manages on `vm.app`.

## The container format (verified)

A `.kap` is a flat array of **16-bit little-endian words**; `elf2kap` writes them as
ASCII `@%06X   %04X` records and the filesystem stores the identical values as binary.

    words 0..199     the 208-word `elf2kap -b` gordon bootstrap, identical in all five
                     images this project has (four shipped + one we built)
    word 200..       a RECORD stream (corrected 2026-10-08, see records()): each record
                     is [tag, len] + len words; for 0x0100 PM / 0x0200 DM / 0x0300 DATA
                     the first two payload words are the address (high, low).
                     word 200 = 0x0300 at address 0 wraps the RAM image: word 204 =
                     0x0100 PM, **word 205 = PM length INCLUDING the 2 address words**,
                     PM data from word 208, each 32-bit instruction **two 16-bit words,
                     HIGH half first**; then the 0x0200 DM records; 0x0500 ends it.
    then             top-level 0x0300 FLASH records, each addressed by a DM pointer slot;
                     the first is the PM-flash overlay at 0x3000, stored LOW half first;
                     then 0x0600 (len 2, a trailer) and 0x0500.

Verified on `sbc_decoder.kap`: word 205 = 0x5360 = 21,344 words, 21,342 of them PM
= 10,671 instructions (an earlier count of 10,672 included the next record's header),
and the first two decode as `Null = Null + Null` (reset) then `jump 0xf2d` -- the
`pre_main` entry. Round-tripping the locally built brown-noise image reproduces its
ELF disassembly instruction for instruction.

## Why the ELF wrapper step matters

`kobjdump -d` on a *raw binary* gets opcodes, registers, immediates and absolute
memory operands right, but mis-computes **branch and call targets**: it counts in
bytes where Kalimba PC-relative offsets are in words. Wrapping the PM in an ELF with
`kobjcopy` makes addressing word-based, after which targets resolve correctly -- which
is what let the registered-handler table be read at all.

Usage:
    python tools/kapdisasm.py                      # all four shipped images
    python tools/kapdisasm.py sbc_decoder          # one
    python tools/kapdisasm.py --out DIR
"""
import argparse
import os
import struct
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, 'adk', 'root', 'tools', 'bin')
FS = os.path.join(ROOT, 'firmware', 'bose', 'extracted', 'internal_fs')
IMAGES = ('sbc_decoder', 'NowSpeakTTS', 'soundClearNb', 'soundClearWb')
PM_TAG_WORD, PM_LEN_WORD, PM_START = 204, 205, 208
PMFLASH_BASE = 0x3000       # gordon.link PMFLASH_REGION


def words_of(path):
    b = open(path, 'rb').read()
    return list(struct.unpack('<%dH' % (len(b) // 2), b[:len(b) // 2 * 2]))


def records(w):
    """Walk the record stream from word 200. A record is [tag, len] + len words; for
    0x0100 (PM), 0x0200 (DM) and 0x0300 (DATA) the first two payload words are the
    address (high, low). The first 0x0300 record (address 0) wraps the RAM image's
    0x0100/0x0200 records; later top-level 0x0300 records are flash data addressed by
    a DM pointer slot. 0x0500 ends a level, 0x0600 (len 2) is a trailer.
    Yields (depth, word_offset, tag, address_or_None, data_words)."""
    out = []

    def walk(a, end, depth):
        while a + 2 <= end:
            tag, ln = w[a], w[a + 1]
            addr = ((w[a + 2] << 16) | w[a + 3]) if ln >= 2 else None
            data = w[a + 4:a + 2 + ln] if ln >= 2 else []
            out.append((depth, a, tag, addr, data))
            if tag == 0x0300 and addr == 0 and depth == 0:
                walk(a + 4, a + 2 + ln, 1)
            a += 2 + ln
        if a != end:
            raise SystemExit('record walk ends at word %d, expected %d' % (a, end))

    walk(200, len(w), 0)
    return out


def pack(words, high_first):
    out = bytearray()
    for i in range(0, len(words) - 1, 2):
        hi, lo = (words[i], words[i + 1]) if high_first else (words[i + 1], words[i])
        out += struct.pack('>I', (hi << 16) | lo)
    return bytes(out)


def extract_pm(w):
    """RAM PM (the 0x0100 record) as big-endian 32-bit bytes. Stored HIGH half first.
    Its length word counts the 2 address words, so the data is len - 2 words (the old
    reader took len words from 208 and decoded the next record's header as a final
    instruction)."""
    if w[PM_TAG_WORD] != 0x0100:
        raise SystemExit('word %d is %#06x, expected the 0x0100 PM tag'
                         % (PM_TAG_WORD, w[PM_TAG_WORD]))
    n = w[PM_LEN_WORD] - 2
    pm = w[PM_START:PM_START + n]
    return pack(pm, True), n, n // 2


def objdump(pm, base, stem, outdir):
    """Disassemble big-endian PM bytes loaded at word address `base`. Returns
    (listing path, instruction count, unrecognised count)."""
    raw = os.path.join(outdir, stem + '.bin')
    elf = os.path.join(outdir, stem + '.elf')
    lst = os.path.join(outdir, stem + '.disasm.txt')
    open(raw, 'wb').write(pm)
    subprocess.run([os.path.join(BIN, 'kobjcopy.exe'),
                    '-I', 'binary', '-O', 'elf32-kalimba', '-B', 'gordon',
                    '--rename-section', '.data=PM_REGION,code,readonly,contents',
                    '--change-section-address', '.data=%#x' % (0x80000000 + base),
                    raw, elf],
                   check=True, capture_output=True)
    r = subprocess.run([os.path.join(BIN, 'kobjdump.exe'), '-d', '-m', 'gordon', elf],
                       check=True, capture_output=True, text=True)
    open(lst, 'w', encoding='utf-8', newline='\n').write(r.stdout)
    unknown = sum(1 for ln in r.stdout.splitlines() if '.word' in ln or 'bad' in ln.lower())
    return lst, len(pm) // 4, unknown


def disasm(name, outdir):
    kap = os.path.join(FS, name + '.kap')
    if not os.path.exists(kap):
        print('  %s: not found' % kap, file=sys.stderr)
        return None
    w = words_of(kap)
    recs = records(w)
    with open(os.path.join(outdir, name + '.records.txt'), 'w', newline='\n') as f:
        for depth, at, tag, addr, data in recs:
            f.write('%s@%-6d tag %04x  %6d data words  addr %s\n'
                    % ('  ' * depth, at, tag, len(data),
                       '%#x' % addr if addr is not None else '-'))
    pm, nwords, ninstr = extract_pm(w)
    lst, _, unknown = objdump(pm, 0, name + '_pm', outdir)
    print('%-14s %6d words, %d records; RAM PM %5d words = %5d instructions, '
          '%d unrecognised -> %s'
          % (name, len(w), len(recs), nwords, ninstr, unknown, os.path.basename(lst)))
    # Top-level DATA records after the RAM image: flash-resident. The first one in
    # sbc_decoder is the PM-flash overlay (gordon.link PMFLASH_REGION 0x003000), stored
    # LOW half first (verified: 0x34a7 push rLink / 0x34a9 r2 = 0x7000 / call 0x349c).
    # Which of the OTHER flash records are code is not known from the container. Each is
    # decoded anyway, but kobjdump decodes almost any bit pattern (every record measures
    # 0 unrecognised), so the count below does NOT distinguish code from data. Only the
    # FIRST flash record gets the 0x3000 base; the others are listed at base 0.
    flash = [r for r in recs if r[0] == 0 and r[2] == 0x0300 and r[3]]
    for k, (_, at, _, slot, data) in enumerate(flash):
        base = PMFLASH_BASE if k == 0 else 0
        lst, n, bad = objdump(pack(data, False), base,
                              '%s_flash%d_slot%04x' % (name, k, slot), outdir)
        print('  flash record %d @%d  slot %#06x  %5d words = %4d instr, base %#x, '
              '%4d unrecognised (%.0f%%; not a code test) -> %s'
              % (k, at, slot, len(data), n, base, bad, 100.0 * bad / max(n, 1),
                 os.path.basename(lst)))
    return lst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('image', nargs='?', help='one of %s' % ', '.join(IMAGES))
    ap.add_argument('--out', default=os.path.join(ROOT, 'build', 'analysis', 'kalimba'))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    for name in ([args.image] if args.image else IMAGES):
        disasm(name, args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
