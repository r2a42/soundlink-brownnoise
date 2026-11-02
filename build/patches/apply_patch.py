#!/usr/bin/env python3
"""apply_patch: turn the official stock firmware into a built probe image, with no DSP
toolchain and no filesystem-signing tool needed.

What this is, and why it's safe. A .patch.json file in this directory is a sparse,
run-length list of (offset, length, new bytes) -- the literal, already-computed
difference between one official Bose firmware file and one probe image this project
actually built, flashed, and read back from its own speaker (docs/PROBE-CATALOG.md,
docs/CURRENT-STATE.md). It contains none of Bose's own firmware content at all: only
this project's own new byte values and where they go, never the original bytes they
replace (the whole-file sha256 check below is what guarantees the input is byte-exact
before any edit runs, so no per-edit copy of the original content is needed or stored).
You still have to supply the whole stock file yourself. Applying a patch does not
recompute anything: the signed-filesystem edits, and the digest/XOR compensation that
keeps Bose's own original signature valid over them (docs/dfu-signature-scheme.md),
were already solved once, by the project's own tools, against this exact stock file;
this script only replays that fixed, already-verified result byte for byte. It cannot
produce any image other than the one the .patch.json already describes, and it will
refuse to run against a stock file that doesn't match byte-for-byte.

This is the SIMPLE path: no ADK, no vendor tools, pure Python standard library. The
FULL path -- rebuilding the DSP generator and the signed edit list from source, which
*can* produce a different image if you change the source -- is docs/clean-room-rebuild.md
and needs the CSR/Qualcomm ADK (docs/toolchain.md). Both paths produce the identical,
independently verifiable output; use this one if you just want the result, the other if
you want to understand, verify, or modify how it was built.

Usage:
    python build/patches/apply_patch.py build/patches/probe427_product_from_stock_3.0.3.6546.patch.json STOCK.dfu OUT.dfu
"""
import hashlib
import json
import sys


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main(argv):
    if len(argv) != 4:
        sys.stderr.write(__doc__)
        return 2
    patch_path, stock_path, out_path = argv[1], argv[2], argv[3]

    with open(patch_path, encoding='utf-8') as f:
        patch = json.load(f)
    with open(stock_path, 'rb') as f:
        data = bytearray(f.read())

    if len(data) != patch['source_size']:
        sys.exit('refusing to patch: %s is %d bytes, expected %d (wrong file?)'
                  % (stock_path, len(data), patch['source_size']))
    got = sha256(data)
    if got != patch['source_sha256']:
        sys.exit('refusing to patch: %s sha256 is\n  %s\nexpected\n  %s\n'
                  'This is not byte-identical to the stock firmware this patch was built '
                  'against -- a different firmware version will not work. Re-download from '
                  'Bose and check the hash again before retrying.' % (stock_path, got, patch['source_sha256']))

    for edit in patch['edits']:
        off = edit['offset']
        new = bytes.fromhex(edit['new'])
        if edit.get('length', len(new)) != len(new):
            sys.exit('malformed patch: edit at offset 0x%X has length %d but %d new bytes'
                      % (off, edit['length'], len(new)))
        data[off:off + len(new)] = new

    out = sha256(data)
    if out != patch['output_sha256']:
        sys.exit('patch applied but the result does not match: got\n  %s\nexpected\n  %s\n'
                  'Do not flash this file.' % (out, patch['output_sha256']))

    with open(out_path, 'wb') as f:
        f.write(data)
    print('wrote %s (%d bytes, sha256 %s) -- matches the recorded, verified %s image exactly.'
          % (out_path, len(data), out, patch.get('name', 'target')))
    print('Next: docs/FLASH-PROTOCOL.md, in full, before flashing anything.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
