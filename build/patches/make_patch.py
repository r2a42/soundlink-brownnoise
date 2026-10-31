#!/usr/bin/env python3
"""make_patch: build a .patch.json (the format apply_patch.py replays) from the official stock firmware and a built image.

The patch holds only the new byte values and where they go, never the stock bytes they replace. Run it
yourself if you have rebuilt an image (docs/clean-room-rebuild.md) and want to share it without sharing
Bose's file. It refuses unless both files have the same size, then checks its own output by applying it.

Usage:
    python build/patches/make_patch.py NAME "one-line description" STOCK.dfu IMAGE.dfu OUT.patch.json
"""
import hashlib, json, sys


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    name, desc, stock_path, image_path, out_path = sys.argv[1:6]
    stock = open(stock_path, 'rb').read()
    image = open(image_path, 'rb').read()
    if len(stock) != len(image):
        sys.exit('size differs: stock %d, image %d' % (len(stock), len(image)))
    edits, i, n = [], 0, len(stock)
    while i < n:
        if stock[i] != image[i]:
            j = i
            while j < n and stock[j] != image[j]:
                j += 1
            edits.append({'offset': i, 'length': j - i, 'new': image[i:j].hex()})
            i = j
        else:
            i += 1
    patch = {'name': name, 'description': desc, 'source_file': stock_path.replace('\\', '/').split('/')[-1],
             'source_size': len(stock), 'source_sha256': sha(stock), 'output_size': len(image),
             'output_sha256': sha(image), 'edit_count': len(edits),
             'edit_bytes': sum(e['length'] for e in edits), 'edits': edits}
    # self-check: replay the edits on the stock bytes and compare with the image hash
    out = bytearray(stock)
    for e in edits:
        out[e['offset']:e['offset'] + e['length']] = bytes.fromhex(e['new'])
    if sha(bytes(out)) != patch['output_sha256']:
        sys.exit('self-check failed')
    json.dump(patch, open(out_path, 'w'), indent=1)
    print('%s: %d edits, %d bytes, output sha256 %s' % (name, len(edits), patch['edit_bytes'], patch['output_sha256']))


main()
