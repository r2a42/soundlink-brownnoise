#!/usr/bin/env python3
"""Smoke-test the probe13 engine cave in xapemu before flashing.

Paths (cave entry 0x3E21D, synthetic Y frame at 0x2000; incoming message
envelope pre-seeded at @(21,Y)=0x2015 / @(22,Y)=0x2016; mode bit = RAM
0x56b bit 11):
  press-ON : msg_lo=0, bit11=0 -> TONE, FEED_CTRL, FEED, re-arm timer
  timer    : msg_lo=sink, bit11=1 -> FEED only, re-arm (no TONE!)
  press-OFF: msg_lo=0, bit11=1 -> CancelFirst only, bit cleared
Injected trap returns: TONE->sink 0:0xB000, Claim->offset 2, Map->0xE000.
"""
import sys, json

sys.path.insert(0, "tools"); sys.path.insert(0, "tools/xapvm")
import xapvm
import xapemu

TONE_SENTINEL = 0xFFFE
CAVE, Y0 = 0x3E21D, 0x2000
SINK, MAPBASE, OFF = 0xB000, 0xE000, 0x0002
TICK = 250

w = xapvm.load_words("firmware/bose/extracted/internal_fs/vm.app")
code = w[0x18:]
for k, v in json.load(open("build/hook/probe13_words.json")).items():
    code[int(k, 16)] = v & 0xFFFF

_real_find_stubs = xapvm.find_stubs
def find_stubs_with_tone(code_arg):
    stubs, other = _real_find_stubs(code_arg)
    stubs = dict(stubs); stubs[0x4946] = TONE_SENTINEL
    return stubs, other
xapvm.find_stubs = find_stubs_with_tone

tt = xapvm.trap_table()
num = {name: n for n, name in tt.items()}
CLAIM_N, MAP_N, FLUSH_N = num["SinkClaim"], num["SinkMap"], num["SinkFlush"]
SEND_N, CANCEL_N = num["MessageSendLater"], num["MessageCancelFirst"]

def setword(emu, a, v):
    struct_pack(emu, a, v)

def struct_pack(emu, a, v):
    import struct
    struct.pack_into("<H", emu.ram, 2 * a, v & 0xFFFF)

def run(msg_lo, msg_hi, bit11):
    emu = xapemu.VM(w)
    emu.code = code
    emu.Y = Y0
    # cave's enterl -8 runs before the envelope read: dispatcher slot 13/14
    # (= msg lo/hi) appear at cave-frame offsets 21/22 => Y0+13 / Y0+14
    struct_pack(emu, Y0 + 13, msg_lo)
    struct_pack(emu, Y0 + 14, msg_hi)
    struct_pack(emu, 0x56b, 0x0800 if bit11 else 0)
    # SinkClaim advances the write pointer: successive claims return later
    # offsets (2, 5, 8, ...) like the real firmware would for our writes
    claim_state = [0]
    def claim_ret(trapnum, pair, a2):
        off = OFF + claim_state[0] * 3
        claim_state[0] += 1
        return (0, off)
    emu.STUB_RET = {
        TONE_SENTINEL: (0, SINK),
        CLAIM_N: claim_ret,
        MAP_N: (0, MAPBASE),
        FLUSH_N: (0, 0),
        SEND_N: (0, 0),
        CANCEL_N: (0, 0),
    }
    res = emu.run(CAVE, max_steps=100000)
    return emu, res

def seq(emu): return [t[0] for t in emu.traps]
def contract(emu):
    assert res[0] == "rts", res
    assert emu.X == 0xAED, hex(emu.X)
    assert emu.Y == Y0, hex(emu.Y)

# --- path 1: press ON ---
emu, res = run(0, 0, bit11=False)
contract(emu)
assert seq(emu) == [TONE_SENTINEL, CLAIM_N, MAP_N, FLUSH_N, CLAIM_N, MAP_N, FLUSH_N, SEND_N], \
    [hex(t) for t in seq(emu)]
# re-arm envelope: AH:AL = 0x4003:0x512, msg = sink, delay 250
t = emu.traps[-1]
exp_a2 = ((SINK & 0xFFFF) << 16) | (SINK >> 16)   # emulator packages slot0 as high word
assert t[0] == SEND_N and t[1] == (0x4003 << 16) | 0x512 and t[2] == exp_a2, (hex(t[1]), hex(t[2]))
assert emu.rd(Y0 - 8 - 4 + 2) == TICK, emu.rd(Y0 - 10)   # REARM frame slot 2
assert emu.rd(0x56b) & 0x0800, "mode bit should now be set"
# control words at map+2..4, notes at map+5..6 (claim advances the pointer)
assert [emu.rd(MAPBASE + OFF + i) for i in range(3)] == [0xA0FF, 0xB002, 0x90F0]
assert [emu.rd(MAPBASE + OFF + 3 + i) for i in range(2)] == [0x1408, 0x1A08]
print("path1 press-ON: OK  (beep, ctrl words, notes, timer armed, bit set)")

# --- path 2: timer fire ---
emu, res = run(SINK, 0, bit11=True)
contract(emu)
assert seq(emu) == [CLAIM_N, MAP_N, FLUSH_N, SEND_N], [hex(t) for t in seq(emu)]
assert emu.traps[-1][2] == ((SINK & 0xFFFF) << 16) | (SINK >> 16), "re-arm must carry the same sink"
assert emu.rd(MAPBASE + OFF) == 0x1408 and emu.rd(MAPBASE + OFF + 1) == 0x1A08
print("path2 timer fire: OK  (fed 2 notes, re-armed with same sink, no TONE)")

# --- path 3: press OFF ---
emu, res = run(0, 0, bit11=True)
contract(emu)
assert seq(emu) == [CANCEL_N], [hex(t) for t in seq(emu)]
assert emu.traps[0][1] == (0x4003 << 16) | 0x512
assert emu.rd(0x56b) & 0x0800 == 0, "mode bit should now be clear"
print("path3 press-OFF: OK  (timer cancelled, bit cleared, no feeding)")

print("SMOKE OK")
