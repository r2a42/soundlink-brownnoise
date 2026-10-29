#!/usr/bin/env python3
"""Smoke-test the probe12 cave in xapemu before flashing.

Runs the cave standalone (entry 0x3E21D, synthetic Y frame) with trap stubs
record-and-return, injecting plausible return values:
  TONE (0x4946, pseudo-stub)  -> AH:AL = 0:0xB000  (feed sink handle)
  SinkClaim                   -> AL = offset (2 words; 0xFFFF on fail path)
  SinkMap                     -> AH:AL = 0:0xE000 (buffer ptr, outside const)
  SinkFlush                   -> 0
Asserts control flow, trap sequence, the 16 note words at map+offset, and
the X=0xaed / Y-restored exit contract on three paths.
"""
import sys, json

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm
import xapemu

TONE_SENTINEL = 0xFFFE
CAVE = 0x3E21D
SINK, MAPBASE, OFF = 0xB000, 0xE000, 0x0002
NOTES = [0x1088, 0x1208, 0x1408, 0x1688] * 4

w = xapvm.load_words("firmware/bose/extracted/internal_fs/vm.app")
code = w[0x18:]
for k, v in json.load(open("build/hook/probe12_words.json")).items():
    code[int(k, 16)] = v & 0xFFFF

# find_stubs is called inside VM.run: wrap to add the TONE pseudo-stub
_real_find_stubs = xapvm.find_stubs
def find_stubs_with_tone(code_arg):
    stubs, other = _real_find_stubs(code_arg)
    stubs = dict(stubs); stubs[TONE_SENTINEL] = None
    stubs[0x4946] = TONE_SENTINEL
    return stubs, other
xapvm.find_stubs = find_stubs_with_tone

tt = xapvm.trap_table()                       # trapnum -> name
num = {name: n for n, name in tt.items()}
CLAIM_N, MAP_N, FLUSH_N = num["SinkClaim"], num["SinkMap"], num["SinkFlush"]

def run(claim_ret, map_ret):
    emu = xapemu.VM(w)
    emu.code = code
    emu.const = xapemu.VM(w).const            # const window from clean image
    emu.Y = 0x2000
    emu.STUB_RET = {
        TONE_SENTINEL: (0, SINK),
        CLAIM_N: claim_ret,
        MAP_N: map_ret,
        FLUSH_N: (0, 0),
    }
    res = emu.run(CAVE, max_steps=50000)
    return emu, res

def word(emu, a):
    return emu.rd(a)

# --- path 1: success ---
emu, res = run((0, OFF), (0, MAPBASE))
assert res[0] == "rts", res
assert emu.X == 0xAED, hex(emu.X)
assert emu.Y == 0x2000, hex(emu.Y)
seq = [t[0] for t in emu.traps]
assert seq == [TONE_SENTINEL, CLAIM_N, MAP_N, FLUSH_N], [hex(t) for t in seq]
got = [word(emu, MAPBASE + OFF + i) for i in range(16)]
assert got == NOTES, [hex(g) for g in got]
assert word(emu, 0x1FF8 + 4) == OFF          # frame slot 4 = claim offset
print("path1 claim/map/write/flush: OK  (16 note words at map+off, X=0xaed, Y restored)")

# --- path 2: claim fails -> 2nd beep telemetry, still clean exit ---
emu, res = run((0, 0xFFFF), (0, MAPBASE))
assert res[0] == "rts", res
assert emu.X == 0xAED, hex(emu.X)
seq = [t[0] for t in emu.traps]
assert seq == [TONE_SENTINEL, CLAIM_N, TONE_SENTINEL], [hex(t) for t in seq]
print("path2 claim-fail: OK  (second TONE call, clean exit)")

# --- path 3: null map -> straight to exit ---
emu, res = run((0, OFF), (0, 0))
assert res[0] == "rts", res
assert emu.X == 0xAED, hex(emu.X)
seq = [t[0] for t in emu.traps]
assert seq == [TONE_SENTINEL, CLAIM_N, MAP_N], [hex(t) for t in seq]
print("path3 null-map: OK  (no writes, clean exit)")

print("SMOKE OK")
