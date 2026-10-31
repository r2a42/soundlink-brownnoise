#!/usr/bin/env python3
"""install_from_stock: install the brown-noise product on a speaker in stock state.

**The default (and recommended) route is ONE flash**: the DSP-generator product
(default probe427, see docs/dsp-generator-route.md). It needs no payload and no
writer image, because the noise is generated inside the speaker's own DSP rather
than played back from a stored file.

A second, OLDER route also exists (docs/ring-buffer-fix.md): a recorded, looped
ADPCM payload played through the stock tone path. It needs TWO images because a
signed DFU cannot write partition 2 directly, so a WRITER image stages the
payload and performs a runtime partition-2 erase-and-write on first boot, then a
PRODUCT image plays it. This runtime partition write is, by this project's own
risk assessment, the single highest-risk operation here -- its failure mode is
not a recoverable wedge but an unrecoverable brick (see docs/partition-route.md
"What makes it unsafe"). It is NOT the default; pass --two-image explicitly if
you specifically want this older route (e.g. to reproduce docs/ring-buffer-fix.md
yourself).

Every flash goes through tools/flash_probe.py, i.e. docs/FLASH-PROTOCOL.md steps 2-4 unchanged (foreground, polling, FLASHED updated, readback 0 differ). This
script only chains them and stops at the first problem.

Usage:  python tools/install_from_stock.py [probeNNN] [--dry-run]           # single flash, default probe427
        python tools/install_from_stock.py --two-image [--writer probeNNN] [--product probeNNN] [--dry-run] [--yes]
  --dry-run   print the plan and check the images exist; touch nothing
  --yes       (--two-image only) do not ask for the confirmation on the keyboard (the product image refuses to
              start when p2 does not hold the payload and says "adjust airbuds" (0x3B), so a missed write is
              audible, not harmful)
Single-flash steps: 1 flash the product; 2 start the noise (centre long press) as usual.
Two-image steps: 1 flash the writer; 2 switch the speaker on and leave it alone (USB may stay in): within about
10 to 60 s after the writer boots it speaks "switching call" (written) or "english" (already there); any other
phrase, or silence for two minutes, means STOP (do not flash the product); 3 flash the product; 4 start the
noise (centre long press) as usual.
"""
import os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


writer = arg('--writer', 'probe393')
product = arg('--product', 'probe428')
dry = '--dry-run' in sys.argv
yes = '--yes' in sys.argv
two_image = '--two-image' in sys.argv


def need(probe):
    for f in ('build/hook/%s_brown.dfu' % probe, 'build/hook/%s_words.json' % probe):
        if not os.path.exists(f):
            sys.exit('missing %s (build it: python build/hook/assemble_%s.py --build)' % (f, probe))


def ensure_flashed_file():
    if not os.path.exists('build/hook/FLASHED'):
        os.makedirs('build/hook', exist_ok=True)
        open('build/hook/FLASHED', 'w', encoding='utf-8').write(
            'status=none\n'
            'note=fresh checkout; no probe has been flashed yet on this install. '
            'Flash the official stock firmware first if you have not already (docs/FLASH-PROTOCOL.md).\n')


def run_flash(probe):
    ensure_flashed_file()
    print('=== flash %s (tools/flash_probe.py, foreground) ===' % probe, flush=True)
    r = subprocess.run([sys.executable, 'tools/flash_probe.py', probe])
    out = open('build/hook/FLASHED', encoding='utf-8').read()
    if r.returncode != 0 or 'verified=readback' not in out or probe not in out:
        sys.exit('STOP: flash of %s did not end verified; follow docs/FLASH-PROTOCOL.md recovery' % probe)


if two_image:
    need(writer); need(product)
    print('plan (two-image, OLDER route, highest risk operation in this project -- see docs/partition-route.md): writer %s -> switch the speaker on, press nothing else, wait for "switching call" (written) or "english" (already there) -> product %s' % (writer, product))
    if dry:
        print('dry run: images present, nothing flashed')
        sys.exit(0)
    run_flash(writer)
    print('\nSWITCH the speaker on with its power button if it is off (a flash cannot power it on). The stock boot says "battery 100%" - that is NOT the writer.')
    print('Press nothing else. Within about 10 to 60 s after the boot the writer speaks "switching call" (it wrote p2)')
    print('or the single word "english" (p2 already held the payload). Silence for two minutes, or any other phrase = failed (a refused state is silent and retried every 5 s).')
    if not yes and input('Type OK when you heard "switching call" or "english" (anything else stops): ').strip() != 'OK':
        sys.exit('STOP: the writer did not report success; the product is NOT flashed')
    run_flash(product)
    print('done. See docs/PROBE-CATALOG.md and docs/ring-buffer-fix.md for %s; the centre long press starts and stops the noise.' % product)
    sys.exit(0)

# Default: single flash, the DSP-generator product (docs/dsp-generator-route.md). Needs no payload and no writer.
single = next((a for a in sys.argv[1:] if not a.startswith('--')), 'probe427')
need(single)
print('plan (single flash, recommended): %s only; no writer, no payload partition write' % single)
if dry:
    print('dry run: image present, nothing flashed')
    sys.exit(0)
run_flash(single)
print('done. See docs/PROBE-CATALOG.md and docs/dsp-generator-route.md for %s; the centre long press starts and stops the noise.' % single)
