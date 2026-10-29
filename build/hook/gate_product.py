#!/usr/bin/env python3
"""Offline world-model gate for THE PRODUCT image (variant P of build/hook/ladder_ext.py; probe270 and later).
    python build/hook/gate_product.py probe270
Every scenario greps the cavesim report (a leading ! means: must NOT match). NO device. Written 2026-10-17 after the hands-free ladder
proved the pieces (docs/field-log.md probes 259-269); the real centre long press 0x4004 is simulated here."""
import os, re, subprocess, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
NAME = sys.argv[1] if len(sys.argv) > 1 else 'probe270'
WORDS = os.path.join(ROOT, 'build', 'hook', NAME + '_words.json')
BASE = ['--flag-id', '30', '--entry', '0x3E21D', '--mem', '59e=d', '--caller-frame', '23', '--world', '--music', 'playing', '--dsp', 'down',
        '--chunk-ms', os.environ.get('GATE_CHUNK_MS', '14742'), '--raw-p2', 'file:' + os.environ.get('GATE_P2', 'build/payload/r3/brown_8000_58968_s63.adpcm'), '--raw-pack', 'octet', '--raw-prime', '126',
        '--steps', '900000000']
BASE = BASE + (['--poll-floor', os.environ['GATE_POLL_FLOOR']] if os.environ.get('GATE_POLL_FLOOR') else [])   # probe309: the busy re-poll is 10 ms; rule R5's floor (default 50) is lowered for THIS image only and the value is stated in BY-smooth-loop.md
_wrap0 = ''
try: _wrap0 = open(os.path.join(ROOT, 'build', 'hook', 'assemble_' + NAME + '.py'), encoding='utf-8').read()
except OSError: pass
if 'PAYLOAD_BUSY_POLL = 6' in _wrap0 or 'PAYLOAD_BUSY_POLL = 8' in _wrap0 or 'PAYLOAD_BUSY_POLL = 9' in _wrap0:
    BASE = BASE + ['--events', '12000']      # probe311: a slow first chunk (14.7 s) is polled every 6 ms (~1,650 cave ticks); a model budget, not a rule: no R1-R6 check changes.
elif 'PAYLOAD_BUSY_POLL = 10' in _wrap0:
    BASE = BASE + ['--events', '6000']      # probe310: a slow first chunk (14.7 s) is polled every 10 ms (~990 cave ticks); cavesim's default event limit (400) would stop the run at ~11 s. A model budget, not a rule: no R1-R6 check changes.
if 'STALL = True' in _wrap0:
    BASE = BASE + ['--events', '60000']      # probe334: the 8-ms tick chain of the stall instrument (about 110 ticks per chunk); a model budget, not a rule
if 'CENSUS = True' in _wrap0:
    BASE = BASE + ['--ksink-after-unload', 'zero']      # probe288: the census gates on StreamKalimbaSink(3) != 0; the real stock returns 0 with no DSP (the default model returns a handle)
# chunks that ran in 30 s (stop / power-off / yield at 30 s): 2-3 with 14.7 s chunks, 4-7 with the 4.9 s chunks of the 24 kHz pair (6 with all chunks at 24 kHz, 4 with chunk 1 at the stock 8 kHz)
N23 = r'(?:1[0-4]|[5-9])' if 'PAYLOAD_RATE = 48000' in _wrap0 else r'[4-7]' if 'PAYLOAD_RATE = 24000' in _wrap0 else r'[23]'   # probe315: 2,457-ms chunks: about 12 chunks by a stop at 30 s (4 to 7 with 4,914-ms chunks, 2 or 3 with 14,742-ms chunks); the slow-first-chunk model gives about 7
NOWRITE = [r'!OverwriteSink', r'!SinkMap', r'!SinkClaim', r'!SinkFlush', r'!PartitionSetMessageDigest', r'!SinkClose']
RULES = [r'!R[1-5] t=']      # R6 (one chain) is waived for the whole product: the 10-s watchdog chain legitimately runs beside the poll chain
SC = []
def S(name, extra, rx, horizon): SC.append((name, BASE + ['--horizon', str(horizon), '--allow', 'R6'] + extra, rx))

S('1 cold press ON (no Bluetooth), OFF at 60 s, ON again at 100 s (warm), SLC disconnect at 135 s (self-healing): nothing spoken, the amp message each time',
  ['--press', '0:4004', '--press', '60000:4004', '--press', '100000:4004', '--press', '135000:4716', '--allow', 'R6'],
  [r'MessageKalimbaTask\(0xba3c\)', r'DSP loaded and booted', r'SETPLUGIN\(1\) accepted', r'LOADPARAMS', r'calls fn_1f04c', r'GO: DSP running',
   r'(?s)AH=0x7023.*AH=0x7023.*AH=0x7023', r'chunks started: (?:[8-9]|[1-9][0-9])', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes',
   r'!KalimbaSendLongMessage', r'!R[1-5] t='] + NOWRITE, 200000)   # R6 (one chain) is waived: after the disconnect the delayed hold release and ENSURE's 1-s retries legitimately overlap
S('2 a Bluetooth connect event alone does NOT start anything (the test emulation of the ladder is gone)',
  ['--press', '0:4753'],
  [r'chunks started: 0', r'(?m)spoken: \(nothing\)$', r'DSP: unloaded', r'!MessageKalimbaTask', r'cave messages still pending: 0'], 60000)
S('3 cold press, KalimbaLoad refused: 0x3E "bluetooth off" 2 s later (ENSURE 0.5 s + stage B 1.5 s), nothing loaded',
  ['--press', '0:4004', '--fail', 'KalimbaLoad'], [r'spoken: 0x3e@2000', r'DSP: unloaded', r'chunks started: 0'], 40000)
S('4 press ON and OFF within 1 s (the DSP loads after the OFF): nothing is brought up',
  ['--press', '0:4004', '--press', '800:4004'], [r'!GO: DSP running', r'chunks started: 0', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: no'], 60000)
S('5 ON, OFF at 60 s, ON again at 62 s while the last chunk plays: no 0x1072 while port 3 is busy (rule R1)',
  ['--press', '0:4004', '--press', '60000:4004', '--press', '62000:4004'], [r'chunks started: (?:[4-9]|[1-9][0-9])', r'(?m)spoken: \(nothing\)$'] + RULES, 120000)
S('6 other events (0x4742, 0x4715, 0x4743) start nothing and are replayed',
  ['--press', '0:4742', '--press', '100:4715', '--press', '200:4743'], [r'(?m)spoken: \(nothing\)$', r'presses: 0 swallowed, 3 replayed', r'cave messages still pending: 0'], 30000)
S('7 a loaded DSP (the Bluetooth/warm case): the press starts the noise without loading a DSP, with the amp message',
  ['--dsp', 'up', '--press', '0:4004'], [r'!MessageKalimbaTask', r'AH=0x7023', r'chunks started: (?:[1-9])', r'(?m)spoken: \(nothing\)$'] + RULES, 60000)

S('8 the stock UNLOADS the DSP at 90 s while the noise plays (seen on the unit ~13.7 min after the link went away): no "call ended" prompt, the cold bring-up runs again, the noise resumes',
  ['--press', '0:4004', '--unload-at', '90000', '--allow', 'R6'],
  [r'(?s)DSP loaded and booted.*DSP loaded and booted', r'(?m)spoken: \(nothing\)$', r'chunks started: (?:[7-9]|[1-9][0-9])', r'mode flag \(id 0x30\) pending: yes', r'!R[1-5] t='], 200000)

# probe277 (NEWFEAT: power-off OFF, mute, yield): run with an image built from assemble_probe277.py
S('9 cold press, then the stock power-off event 0x4002 at 30 s: the mode goes OFF (flag gone), the running chunk is the last, 0x4002 is replayed to the stock, nothing spoken',
  ['--press', '0:4004', '--press', '30000:4002'],
  [r'mode flag \(id 0x30\) pending: no', r'chunks started: ' + N23 + ',', r'event 0x4002: REPLAYED', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 120000)
S('10 cold press (the DSP is OURS), then a phone starts streaming (0x4758) at 30 s: YIELD, the mode goes OFF, the stock can load its decoder',
  ['--press', '0:4004', '--press', '30000:4758'],
  [r'mode flag \(id 0x30\) pending: no', r'chunks started: ' + N23 + ',', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 120000)
S('11 a loaded DSP (the warm case, not ours): a stream start at 20 s does NOT stop the noise',
  ['--dsp', 'up', '--press', '0:4004', '--press', '20000:4758'],
  [r'mode flag \(id 0x30\) pending: yes', r'chunks started: (?:[2-9]|[1-9][0-9])'] + RULES, 60000)
S('12 (L1a F1a) warm: a stream start (0x4758) arms the auto-start, an OFF 2 s later: nothing is left pending, the loop does not survive the OFF',
  ['--dsp', 'up', '--press', '0:4004', '--press', '3000:4758', '--press', '5000:4004'],
  [r'mode flag \(id 0x30\) pending: no', r'cave messages still pending: 0', r'chunks started: [1-3],'] + RULES, 60000)
S('13 (L1a F1b) cold ON then the power-off event 1 s later: no DSP is loaded after the OFF',
  ['--press', '0:4004', '--press', '1000:4002'],
  [r'mode flag \(id 0x30\) pending: no', r'!KalimbaLoad +AL', r'cave messages still pending: 0', r'chunks started: 0'] + RULES, 60000)
S('14 (L1a F4) cold ON with a refused KalimbaLoad: ONE "bluetooth off" prompt, the mode goes OFF, no endless retries',
  ['--press', '0:4004', '--fail', 'KalimbaLoad'],
  [r'(?m)^spoken: 0x3e@\d+$', r'mode flag \(id 0x30\) pending: no', r'cave messages still pending: 0'] + RULES, 60000)
_wrap = ''
try: _wrap = open(os.path.join(ROOT, 'build', 'hook', 'assemble_' + NAME + '.py'), encoding='utf-8').read()
except OSError: pass
if 'DACREL = True' in _wrap:
    S('15 (probe279) cold ON then a phone streams (0x4758): our DAC connection is undone ONCE with fn_1f12b so the stock connect can claim the DAC',
      ['--press', '0:4004', '--press', '30000:4758'],
      [r'(?s)calls fn_1f12b.*', r'mode flag \(id 0x30\) pending: no', r'cave messages still pending: 0'] + RULES, 60000)
    S('16 (probe279) warm (a stock DSP is loaded): an OFF does NOT touch the DAC',
      ['--dsp', 'up', '--press', '0:4004', '--press', '20000:4004'],
      [r'!calls fn_1f12b', r'mode flag \(id 0x30\) pending: no'] + RULES, 40000)
if 'DACREL3 = True' in _wrap:
    S('19 (probe287) cold ON, press-OFF at 30 s: our DAC connection is undone ONCE, by the delayed hold release (id 0x13 at 46 s), never at the OFF itself',
      ['--press', '0:4004', '--press', '30000:4004'],
      [r'(?s)timer message, MessageId 0x0013(?:(?!\n== t=).)*?calls fn_1f12b', r'(?s)\A(?!.*calls fn_1f12b.*calls fn_1f12b)', r'(?s)\A(?!.*t= 3[0-9]{4}[^\n]*\n  calls fn_1f12b)', r'mode flag \(id 0x30\) pending: no'] + RULES, 60000)
    S('20 (probe287) cold ON then a phone streams (0x4758) at 30 s: the same single release-time DAC undo (yield)',
      ['--press', '0:4004', '--press', '30000:4758'],
      [r'(?s)timer message, MessageId 0x0013(?:(?!\n== t=).)*?calls fn_1f12b', r'(?s)\A(?!.*calls fn_1f12b.*calls fn_1f12b)', r'mode flag \(id 0x30\) pending: no'] + RULES, 60000)
    S('21 (probe287) warm (a stock DSP is loaded): an OFF and its release do NOT touch the DAC',
      ['--dsp', 'up', '--press', '0:4004', '--press', '20000:4004'],
      [r'!calls fn_1f12b', r'mode flag \(id 0x30\) pending: no'] + RULES, 60000)
if 'IDGUARD = True' in _wrap:
    S('18 (probe285) cold ON, power-off event at 30 s, then the stock message 0x7008 reaches the cave task at 31 s: the noise does NOT restart (no new poll, no new chunk after the last one)',
      ['--press', '0:4004', '--press', '30000:4002', '--msg-at', '31000:7008', '--msg-at', '32000:7001'],
      [r'mode flag \(id 0x30\) pending: no', r'cave messages still pending: 0'] + RULES, 80000)
if 'DSPGUARD = True' in _wrap:
    S('17 (probe284) cold ON, OFF at 30 s, then STOCK DSP messages 0x1015 and 0x1000 at 31 s (its beep / power-off tone on our DSP): the bring-up does NOT run again (one SETPLUGIN, one GO)',
      ['--press', '0:4004', '--press', '30000:4004', '--dspmsg-at', '31000:1015', '--dspmsg-at', '31500:1000'],
      [r'(?s)\A(?!.*SETPLUGIN\(1\) accepted.*SETPLUGIN\(1\) accepted)', r'(?s)\A(?!.*GO: DSP running.*GO: DSP running)', r'mode flag \(id 0x30\) pending: no'] + RULES, 60000)

if 'CLEARDAC = True' in _wrap:
    # probe295 (docs/deep/material-2026-10-19/AJ-probe295-fix.md). --dac-guard models the real fn_1f04c guard on @0x6d1 bit 15 (refuse while set, set on success; fn_1f12b clears it).
    S('27 (probe295 F2) cold ON, OFF at 30 s, a stock sentence at 50 s (the DSP is gone, @0x6d1 bit 15 stays set), ON at 100 s: the DAC connect is NOT refused, the noise starts again',
      ['--dac-guard', '--press', '0:4004', '--press', '30000:4004', '--unload-at', '50000', '--mem-at', '50000:6d1=8000', '--press', '100000:4004'],
      [r'(?s)GO: DSP running.*GO: DSP running', r'(?s)calls fn_1f04c.*calls fn_1f04c', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes', r'chunks started: (?:[5-9]|[1-9][0-9])'] + RULES, 160000)
    S('28 (probe295 F2) the stale flag is cleared ONLY on a cold load: a warm press (a loaded DSP, nothing to connect) never calls fn_1f04c or fn_1f12b',
      ['--dac-guard', '--dsp', 'up', '--press', '0:4004'],
      [r'!calls fn_1f04c', r'!calls fn_1f12b', r'chunks started: (?:[1-9])'] + RULES, 60000)
if 'CONSUME = True' in _wrap:
    FR = ['--frame', '13=1', '--frame', '14=0', '--show', '90d:2']       # the stock caller fn_00846: (13,Y) indicate = 1, (14,Y) flag word = 0; the cave's slots 21/22
    S('29 (probe295 F1) the START press (0x4004) clears the caller indicate flag (13,Y) and sets the consume bit 15 of (14,Y): the stock arm, beep and park never run',
      FR + ['--press', '0:4004'], [r'data @0x090D\.\.\+2: 0000 8000', r'presses: 1 swallowed, 0 replayed'] + RULES, 30000)
    S('30 (probe295 F1) the STOP press does the same (the frame is put back to indicate 1 / flag 0 at 29 s, so only the stop press can have written it)',
      FR + ['--press', '0:4004', '--mem-at', '29000:90d=1', '--mem-at', '29000:90e=0', '--press', '30000:4004'],
      [r'data @0x090D\.\.\+2: 0000 8000', r'presses: 2 swallowed, 0 replayed', r'mode flag \(id 0x30\) pending: no'] + RULES, 60000)
    S('31 (probe295 F1) every OTHER event (0x4742, 0x4715, 0x4743) leaves the stock frame alone and is replayed',
      FR + ['--press', '0:4742', '--press', '100:4715', '--press', '200:4743'],
      [r'data @0x090D\.\.\+2: 0001 0000', r'presses: 0 swallowed, 3 replayed'] + RULES, 30000)
if 'FAILOFF = True' in _wrap:
    S('32 (probe295 F3) the DAC connect (fn_1f04c) is refused: the mode goes OFF, 0x3d "noise cancellation only" is spoken once, nothing plays, nothing is left pending',
      ['--press', '0:4004', '--fail', 'fn_1f04c'],
      [r'(?m)^spoken: 0x3d@\d+$', r'mode flag \(id 0x30\) pending: no', r'chunks started: 0', r'!GO: DSP running'] + RULES, 60000)
    S('33 (probe295 F3) the 0x1072 gate is refused after the DAC connect (the GO branch): the mode goes OFF, 0x3c "adjust left airbud" is spoken once, no GO',
      ['--press', '0:4004', '--dsp-refuse', '1072'],
      [r'(?m)^spoken: 0x3c@\d+$', r'mode flag \(id 0x30\) pending: no', r'chunks started: 0', r'!GO: DSP running'] + RULES, 60000)
    S('34 (probe295 F3) a failure does not leave the mode stale-ON (the AH "presses do nothing" symptom): with the DAC connect refused every press is a START that fails audibly, so two presses speak 0x3d twice (a stale ON would make the second press a silent OFF)',
      ['--press', '0:4004', '--press', '40000:4004', '--fail', 'fn_1f04c', '--unload-at', '20000'],      # the unload models the speak path: the TTS powers the DSP off
      [r'(?m)^spoken: 0x3d@\d+, 0x3d@\d+$', r'mode flag \(id 0x30\) pending: no', r'chunks started: 0'] + RULES, 80000)
if 'CANCELALL = True' in _wrap:
    S('35 (probe295 F4) two duplicate restart checks (id 0x2C) are pending, cold ON, OFF at 30 s: the OFF cancels BOTH, and the cold flag 0x2E, the watchdog 0x2D, stage B 0x26 and the auto-start 0x20 (only the delayed hold release 0x13 stays); probe285 (single cancels) leaves one 0x2C, probe287/288 (OFFLOOP with the ld AH,@(4,X) defect) leave all',
      ['--press', '0:4004', '--pending', '2c@45000', '--pending', '2c@46000', '--press', '30000:4004'],
      [r'mode flag \(id 0x30\) pending: no', r'!cave messages still pending:[^\n]*id 0x2[cde]', r'!cave messages still pending:[^\n]*id 0x26', r'!cave messages still pending:[^\n]*id 0x20', r'cave messages still pending: 1 \(id 0x13 due'] + RULES, 40000)
if 'PROBE_RATIO_EVEN = 0x0F' in _wrap:
    _m = re.search(r'(?m)^PROBE_DEFLEV = (\d+)', _wrap)
    _RHI = '0x0015' if (_m and int(_m.group(1)) % 2) else '0x000f'
    if 'PROBE_FINE = True' in _wrap: _RHI = '0x%04x' % (int(re.search(r'(?m)^PROBE_FINE_R0 = (\d+)', _wrap).group(1)) + 7 * (int(_m.group(1)) % 4))      # probe326/327: the fine ladder's ratio byte of the default level
    # probe296 (docs/deep/material-2026-10-19/AV-probe296-level.md): the AT section 6 level match. fn_22a89 / fn_1f5bf are recorded by the opt-in cavesim WATCH ("watched" lines); the POKE ratio is value hi (stack slot 2) of the 0x28f6 message.
    S('36 (probe296) cold press: the bring-up sends DAC gain index 15 (fn_22a89(15), fn_1f5bf(0, gain 0)), never 12, and the tone mix ratio byte is 0x0F (even level), never 0x2D',
      ['--press', '0:4004'],
      [r'watched fn_22a89  AL=0x000f', r'watched fn_1f5bf  AL=0x0000 AH=0x0000  \(gain 0/60 dB\)', r'!watched fn_22a89  AL=0x000c', r'!gain -540', r'POKE message: addr 0x28f6, value hi \(stack slot 2\) = ' + _RHI, r'!POKE message: addr 0x28f6, value hi \(stack slot 2\) = 0x002d', r'GO: DSP running', r'(?m)spoken: \(nothing\)$'] + RULES, 20000)
    S('37 (probe296) warm press (a loaded DSP): no DAC gain is written at all (the warm DAC is the stock one), the ratio byte is 0x0F',
      ['--dsp', 'up', '--press', '0:4004'],
      [r'!watched fn_1f5bf', r'!watched fn_22a89', r'POKE message: addr 0x28f6, value hi \(stack slot 2\) = ' + _RHI, r'!POKE message: addr 0x28f6, value hi \(stack slot 2\) = 0x002d', r'AH=0x7023', r'(?m)spoken: \(nothing\)$'] + RULES, 30000)
if 'BTDROP = True' in _wrap:
    # probe328: Bluetooth off while the noise plays. cavesim models: fn_09157 (devices connected: 1 when @0x59e >= 3), fn_09445 (recorded 'calls fn_09445 AL=0x0001'; afterwards sink state 1 and page scan on, as the stock's disconnect tail), the four scan wrappers (calls fn_0c80e / fn_0c86d off, fn_0c7f2 / fn_0c82a on; @0x564 bit 10 page, bit 11 inquiry)
    BT = ['--mem', '564=0c00']
    S('BT1 (probe328) ON press with a device connected (state 3, both scans on): the stock drop-everything helper once with AL=1, then page scan off and inquiry scan off, in that order, in the press itself',
      BT + ['--mem', '59e=3', '--press', '0:4004'],
      [r'(?s)t=\s+0\s+press 0x4004.*?calls fn_09157.*?calls fn_09445  AL=0x0001.*?calls fn_0c80e.*?calls fn_0c86d.*?== t=\s+500', r'!calls fn_0c7f2', r'!calls fn_0c82a'] + RULES, 3000)
    S('BT2 (probe328) ON press with nothing connected (state 1, both scans on): no drop, the two scans go off',
      BT + ['--mem', '59e=1', '--press', '0:4004'],
      [r'calls fn_09157', r'!calls fn_09445', r'(?s)calls fn_0c80e.*?calls fn_0c86d', r'!calls fn_0c7f2'] + RULES, 3000)
    S('BT3 (probe328) ON press with nothing connected and both scans already off (@0x564 bits clear): nothing is sent at all',
      ['--mem', '564=0000', '--mem', '59e=1', '--press', '0:4004'],
      [r'calls fn_09157', r'!calls fn_09445', r'!calls fn_0c80e', r'!calls fn_0c86d', r'!calls fn_0c7f2', r'!calls fn_0c82a'] + RULES, 3000)
    S('BT4 (probe328) ON at 0 s from state 3, OFF at 20 s (nothing connected by then): the scans come back on (page scan on, inquiry scan on) and the drop happened once',
      BT + ['--mem', '59e=3', '--press', '0:4004', '--press', '20000:4004'],
      [r'(?s)calls fn_09445  AL=0x0001', r'!(?s)calls fn_09445.*calls fn_09445', r'(?s)calls fn_0c7f2.*?calls fn_0c82a'] + RULES, 30000)
    S('BT5 (probe328) a device connects again at 10 s (state 3): the watchdog drops it again (a second fn_09445), scans off again; the loop goes on',
      BT + ['--mem', '59e=3', '--mem-at', '10000:59e=3', '--mem-at', '10000:564=0c00', '--press', '0:4004'],
      [r'(?s)calls fn_09445.*calls fn_09445', r'!(?s)calls fn_09445.*calls fn_09445.*calls fn_09445', r'mode flag \(id 0x30\) pending: yes'] + RULES, 16000)
    S('BT6 (probe328) OFF at 21 s while a device is connected (state 3, connected at 20.5 s between two watchdog ticks): the scans are NOT touched (the stock keeps them off in the connected states)',
      BT + ['--mem', '59e=1', '--press', '0:4004', '--mem-at', '20500:59e=3', '--mem-at', '20500:564=0000', '--press', '21000:4004'],
      [r'!calls fn_0c7f2', r'!calls fn_0c82a'] + RULES, 30000)
if 'CANCEL670B = True' in _wrap:
    # probe333: the stock 0x670b "ready to connect" reminder (task 0x512) is cancelled by every SCANOFF: the press ON and each 4-s watchdog tick (cancel of a task/id the cave does not own; the cave's own messages are untouched)
    S('CN1 (probe333) ON press: MessageCancelFirst(0x0512, 0x670b) at the press and again on the 4-s watchdog ticks; the loop and the flag are unharmed',
      ['--mem', '564=0c00', '--mem', '59e=1', '--press', '0:4004'],
      [r'(?s)MessageCancelFirst\s+AL=0x0512 AH=0x670b.*MessageCancelFirst\s+AL=0x0512 AH=0x670b.*MessageCancelFirst\s+AL=0x0512 AH=0x670b', r'mode flag \(id 0x30\) pending: yes'] + RULES, 14000)
    S('CN2 (probe333) with a device connected (state 3): the drop is followed by the reminder cancel; OFF at 20 s: still no harm',
      ['--mem', '564=0c00', '--mem', '59e=3', '--press', '0:4004', '--press', '20000:4004'],
      [r'(?s)calls fn_09445  AL=0x0001.*MessageCancelFirst\s+AL=0x0512 AH=0x670b'] + RULES, 30000)
if 'EVGUARD = True' in _wrap:
    # probe298 (docs/deep/material-2026-10-19/BC-probe298-evguard.md): EVGUARD at the top of EVTX. Models: --dac-guard (@0x6d1 bit 15), --ksink-after-unload zero (no DSP -> StreamKalimbaSink(3) = 0),
    # --audio-busy (the stock audio-busy word; --mem-at MS:fffe=VAL sets it), --mem-at MS:72f=VAL / 72e=VAL (the A2DP / call plugin instance pointers), --show 6d1:1 prints the flag at the end.
    # The simulator has no TTS: "the TTS ran" is --unload-at (DSP gone) plus --mem-at T:6d1=8000 (the flag left set), the model of scenario 27.
    CH = 'EVGCHAIN = True' in _wrap       # probe299 (BH): the stack-true chain model replaces the --ksink-after-unload counterfactual (BG 12)
    EG = ['--dac-guard', '--chain-model', '--audio-busy', '--show', '6d1:1'] if CH else ['--dac-guard', '--ksink-after-unload', 'zero', '--audio-busy', '--show', '6d1:1']
    STALE = ['--press', '0:4004', '--press', '30000:4004', '--unload-at', '50000', '--mem-at', '50000:6d1=8000']      # cold ON, OFF at 30 s, a TTS at 50 s: DSP gone, flag stale
    F_SET, F_CLR = r'data @0x06D1\.\.\+1: 8000', r'data @0x06D1\.\.\+1: 0000'
    S('38 (probe298 EVGUARD) the stale flag after a DSP unload is cleared by the NEXT event (a volume press 0x400D at 60 s); the event is replayed to the stock',
      EG + STALE + ['--press', '60000:400D'], [F_CLR, r'presses: 2 swallowed, 1 replayed', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 80000)
    S('38b (control) the same without the volume press: the flag is still stale at the end (the clear above is EVGUARD, nothing else)',
      EG + STALE, [F_SET, r'(?m)spoken: \(nothing\)$'] + RULES, 80000)
    S('39 (probe298) NOT cleared while OUR DSP is resident (the lie window E2): no unload, the flag is valid, a volume press at 60 s',
      EG + ['--press', '0:4004', '--press', '30000:4004', '--press', '60000:400D'], [F_SET, r'presses: 2 swallowed, 1 replayed'] + RULES, 80000)
    S('40 (probe298) NOT cleared while a stock owner holds the audio-busy word (a stock sound is in flight): busy := 0xb195 at 55 s, event at 60 s',
      EG + STALE + ['--mem-at', '55000:fffe=b195', '--press', '60000:400D'], [F_SET, r'presses: 2 swallowed, 1 replayed'] + RULES, 80000)
    S('41 (probe298) NOT cleared while an A2DP plugin instance exists (@0x72f != 0): set at 55 s, event at 60 s',
      EG + STALE + ['--mem-at', '55000:72f=5', '--press', '60000:400D'], [F_SET, r'presses: 2 swallowed, 1 replayed'] + RULES, 80000)
    S('41b (probe298) NOT cleared while the call/CVC plugin instance exists (@0x72e != 0): set at 55 s, event at 60 s',
      EG + STALE + ['--mem-at', '55000:72e=5', '--press', '60000:400D'], [F_SET, r'presses: 2 swallowed, 1 replayed'] + RULES, 80000)
    S('42 (probe298) NOT cleared during a mode-ON session: events 0x400D, 0x4715, 0x400E arrive while the noise plays; the noise continues, the flag stays set',
      EG + ['--press', '0:4004', '--press', '20000:400D', '--press', '25000:4715', '--press', '30000:400E'],
      [F_SET, r'presses: 1 swallowed, 3 replayed', r'chunks started: (?:[2-9]|[1-9][0-9])', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 60000)
    S('43 (probe298) NOT cleared in the warm case (a stock DSP is loaded, the stock set the flag): event at 20 s',
      EG + ['--dsp', 'up', '--mem-at', '0:6d1=8000', '--press', '20000:400D'], [F_SET, r'presses: 0 swallowed, 1 replayed'] + RULES, 40000)
    S('44 (probe298) after the repair a following START press still starts the noise (the F2 path is unharmed): cold ON, OFF, stale, volume press (cleared), ON at 100 s',
      EG + STALE + ['--press', '60000:400D', '--press', '100000:4004'],
      [r'(?s)GO: DSP running.*GO: DSP running', r'(?s)calls fn_1f04c.*calls fn_1f04c', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes', r'chunks started: (?:[5-9]|[1-9][0-9])', F_SET] + RULES, 160000)
    S('45 (probe298) a clear with the flag already clear is harmless and the event is still replayed with the right id: no DSP, no press history, 0x400D at 1 s',
      EG + ['--press', '1000:400D'], [F_CLR, r'presses: 0 swallowed, 1 replayed', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 20000)
if 'EVGCHAIN = True' in _wrap:
    # probe299 (docs/deep/material-2026-10-19/BH-probe299-evguard-fixed.md): scenarios 38-45 above run under --chain-model; these add the chain-specific cases.
    TFS0, TFS1 = r'TransformFromSource -> 0 \(--chain-model: the DAC link chain is gone\)', r'TransformFromSource -> handle \(--chain-model: the DAC link chain is alive\)'
    S('46 (probe299) the clear is decided by the chain test: after the stale flag (DSP unloaded) the event reads TransformFromSource = 0 (chain gone) and clears',
      EG + STALE + ['--press', '60000:400D'], [F_CLR, TFS0, r'presses: 2 swallowed, 1 replayed'] + RULES, 80000)
    S('47 (probe299) NOT cleared while the chain is alive although nothing else holds: our own cold run, stopped, hold released, DSP and DAC link still up (the lie window), volume press at 60 s',
      EG + ['--press', '0:4004', '--press', '30000:4004', '--press', '60000:400D'], [F_SET, TFS1, r'presses: 2 swallowed, 1 replayed'] + RULES, 80000)
    S('48 (probe299) a stock chain alive on a stale-looking state (--chain-at 55000:1 after the unload): the flag is valid, NOT cleared',
      EG + STALE + ['--chain-at', '55000:1', '--press', '60000:400D'], [F_SET, TFS1, r'presses: 2 swallowed, 1 replayed'] + RULES, 80000)
    S('49 (probe299) the cave never asks for port 3 any more in the guard: StreamKalimbaSink is called with port 5 by the guard (a trap at the event), the answer is nonzero in every state',
      EG + STALE + ['--press', '60000:400D'], [F_CLR, r'StreamKalimbaSink +AL=0x0005'] + RULES, 80000)
if 'G5DIAG = True' in _wrap:
    # probe300 (docs/deep/material-2026-10-19/BN-probe300-g5-diag.md): ONE read-only digit D = blk[24] + 5*ready, spoken 36 s after the yield (0x4758 while the noise runs), as id 0x27+D. The stock plugin state is not
    # modelled: the words it would write are set with --mem-at (73e = the BDSP shadow word, bit 6 = ready = 0x40; 72b = the audio-manager block, set to 0x1000 so blk[24] is the word at 0x1018).
    YP = ['--press', '0:4004', '--press', '30000:4758']
    BLKP = lambda v: ['--mem-at', '31000:72b=1000', '--mem-at', '31000:1018=%x' % v]
    S('50 (probe300) yield, the stock chain complete (ready, blk[24] = 3): D = 8, id 0x2f is spoken once, 36 s after the stream start; the yield itself is unchanged (mode OFF, chunk 3 never starts)',
      EG + YP + ['--mem-at', '31000:73e=40'] + BLKP(3), [r'(?m)^spoken: 0x2f@66000$', r'mode flag \(id 0x30\) pending: no', r'chunks started: ' + N23 + ',', r'cave messages still pending: 0', r'presses: 1 swallowed, 1 replayed'] + RULES, 120000)
    S('51 (probe300) yield, connected but "ready" never ran (the muted-graph case): D = 3, id 0x2a',
      EG + YP + ['--mem-at', '31000:73e=10'] + BLKP(3), [r'(?m)^spoken: 0x2a@66000$', r'mode flag \(id 0x30\) pending: no', r'cave messages still pending: 0'] + RULES, 120000)
    S('52 (probe300) yield, nothing of the stock plugin exists (RAM zero): D = 0, id 0x27',
      EG + YP, [r'(?m)^spoken: 0x27@66000$', r'cave messages still pending: 0'] + RULES, 120000)
    S('53 (probe300) yield, "ready" ran and blk[24] = 4 (refused): D = 9, id 0x30',
      EG + YP + ['--mem-at', '31000:73e=40'] + BLKP(4), [r'(?m)^spoken: 0x30@66000$'] + RULES, 120000)
    S('54 (probe300) NO yield: cold ON, OFF at 30 s, the plugin words set: nothing is ever spoken (the report is armed only by a stream start)',
      EG + ['--press', '0:4004', '--press', '30000:4004', '--mem-at', '5000:73e=40'] + ['--mem-at', '5000:72b=1000', '--mem-at', '5000:1018=3'], [r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 120000)
    S('55 (probe300) a stock stream start with the noise OFF (plain music, nothing of ours running): not armed, nothing spoken',
      EG + ['--press', '30000:4758'] + ['--mem-at', '5000:73e=40'], [r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 120000)
    S('56 (probe300, rule 4) yield, then the owner starts the noise again at 50 s (mode ON when the report is due at 66 s): the report is NOT spoken',
      EG + YP + ['--mem-at', '31000:73e=40'] + BLKP(3) + ['--press', '50000:4004'], [r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 100000)
    S('57 (probe300) warm case (a stock DSP is loaded, the noise continues through the stream start): armed, but the mode is ON at 56 s: nothing spoken, the noise plays on',
      ['--dsp', 'up', '--press', '0:4004', '--press', '20000:4758'], [r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes', r'chunks started: (?:[2-9]|[1-9][0-9])'] + RULES, 70000)
    S('58 (probe300, documented corner) warm case, then the noise is stopped by a press at 40 s: the report (armed by the stream start) is spoken at 56 s although it was not a yield',
      ['--dsp', 'up', '--press', '0:4004', '--press', '20000:4758', '--press', '40000:4004', '--mem-at', '5000:73e=40'], [r'(?m)^spoken: 0x2c@56000$', r'mode flag \(id 0x30\) pending: no'] + RULES, 80000)
if 'G5ZAP = True' in _wrap:
    # probe302 (docs/deep/material-2026-10-19/BS-probe302-g5zap.md): at the stream start (0x4758) with the mode ON and @0x72f == 0 the stale DAC flag @0x6d1 bit 15 is cleared by EVGZAP; the yield is otherwise unchanged.
    ZP = ['--dac-guard', '--chain-model', '--audio-busy', '--show', '6d1:1']
    YPZ = ['--press', '0:4004', '--mem-at', '20000:6d1=8000', '--press', '30000:4758']
    S('60 (probe302) cold ON (flag stale 8000 set at 20 s), stream start at 30 s, @0x72f == 0: the flag reads 0000 afterwards; the yield is unchanged (mode OFF, nothing spoken)',
      ZP + YPZ, [F_CLR, r'mode flag \(id 0x30\) pending: no', r'chunks started: ' + N23 + ',', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0', r'presses: 1 swallowed, 1 replayed'] + RULES, 120000)
    S('61 (probe302) the same but a stock A2DP instance exists (@0x72f = 5 from 25 s): the bit is left alone (8000)',
      ZP + YPZ + ['--mem-at', '25000:72f=5'], [F_SET, r'mode flag \(id 0x30\) pending: no', r'cave messages still pending: 0'] + RULES, 120000)
    S('62 (probe302) the stream start with the noise OFF (cold ON, OFF at 25 s, flag stale 8000 at 20 s, stream start at 30 s): not the yield path, EVGZAP not called by EVGY (the flag is left as set by the stock path)',
      ZP + ['--press', '0:4004', '--press', '25000:4004', '--mem-at', '27000:6d1=8000', '--press', '30000:4758'], [F_SET, r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 120000)
    S('63 (probe302) a different event (volume 0x400D) with the noise ON and the flag stale: EVGY does nothing (EVGCHK skips on busy): the flag stays 8000',
      ZP + ['--press', '0:4004', '--mem-at', '20000:6d1=8000', '--press', '30000:400D'], [F_SET, r'mode flag \(id 0x30\) pending: yes'] + RULES, 80000)
if 'CENSUS = True' in _wrap:
    # probe288 (read-only census, docs/deep/material-2026-10-19/AA-probe288-census.md). Digit d is spoken as id 0x27 + d ("battery (d+1)*10 percent"), d1 at +1.5 s, d2 at +6 s after the press.
    NOCHUNK_LATE = r'!#\d+ start +(?:[89]\d{4}|\d{6}) ms'       # no chunk starts at or after 80 s
    S('22 (probe288) CLEAN cold press (nothing resident): no census, the normal cold start (nothing spoken, noise starts)',
      ['--press', '0:4004'],
      [r'GO: DSP running', r'chunks started: (?:[2-9]|[1-9][0-9])', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 40000)
    S('23 (probe288) ON, OFF at 60 s, an IDLE press at 100 s (the DSP is resident): the census is spoken (d1 = 1 sink, d2 = 0), NOTHING else happens: no toggle, no start, no second DSP load',
      ['--press', '0:4004', '--press', '60000:4004', '--press', '100000:4004'],
      [r'(?m)^spoken: 0x28@101500, 0x27@106000$', r'mode flag \(id 0x30\) pending: no', r'cave messages still pending: 0', NOCHUNK_LATE, r'(?s)\A(?!.*DSP loaded and booted.*DSP loaded and booted)', r'presses: 3 swallowed, 0 replayed'] + RULES, 140000)
    S('24 (probe288) the same with the DAC link flag @0x6d1 bit 15 set at 70 s: d2 = 2',
      ['--press', '0:4004', '--press', '60000:4004', '--mem-at', '70000:6d1=8000', '--press', '100000:4004'],
      [r'(?m)^spoken: 0x28@101500, 0x29@106000$', r'mode flag \(id 0x30\) pending: no', NOCHUNK_LATE] + RULES, 140000)
    S('25 (probe288) a STOP press while the noise runs is never turned into a census (mode ON = the normal path): nothing spoken, the mode goes OFF',
      ['--press', '0:4004', '--press', '30000:4004'],
      [r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: no', r'cave messages still pending: 0'] + RULES, 60000)
    S('26 (probe288) a stale mode flag (the stock unloads the DSP at 20 s while ON): the press at 20.5 s is the normal OFF, silent (a stale ON is cleared by one press; the census is never spoken with the mode ON)',
      ['--press', '0:4004', '--unload-at', '20000', '--press', '20500:4004'],
      [r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: no'], 60000)

if 'PAYLOAD_RATE = 24000' in _wrap:
    # probe305 (docs/deep/material-2026-10-19/BW-24k-pair.md): the 24 kHz payload (58,968 B = 4,914 ms per chunk). These scenarios pin their own chunk model (--chunk-ms is appended last and wins over BASE):
    # 4914 = every chunk at 24 kHz; 14742,4914 = the pessimistic reading of FACTS Q007 (chunk 1 plays at the stock 8 kHz, later chunks at 24 kHz). Timeline of the 4914 model: chunk 1 built at 2,550 ms (EOF 7,464),
    # chunk 2 at 7,500 (EOF 12,414), chunk 3 at 12,450 ...; the start gap is 4,950 ms (36 ms between EOF and the next build).
    C24 = ['--chunk-ms', '4914']
    # probe309 (BY-smooth-loop.md): FIRST_POLL 4850 and a 10-ms busy re-poll: chunk 1 built at 2,550 -> first poll 7,400 (busy), then every 10 ms: free at 7,470 (EOF 7,464): chunk 2 at 7,470 and every start gap 4,920 ms; the old images keep 7,500 / 4,950
    BP6 = 'PAYLOAD_BUSY_POLL = 6' in _wrap       # probe311 (CK-fast-poll-probe311.md): FIRST_POLL 4905 and a 6-ms busy re-poll: polls at 2,550 + 4,905 + 6 k = 7,455, 7,461, 7,467 ...; EOF 7,464: chunk 2 at 7,467, start gap 4,917 ms
    BP_FINE = BP6 or 'PAYLOAD_BUSY_POLL = 10' in _wrap
    BP_2, BP_GAP = (7467, 4917) if BP6 else (7470, 4920) if BP_FINE else (7500, 4950)
    BP_STOP1 = 7465 if BP6 else 7466 if BP_FINE else 7480     # a STOP after EOF 7,464 and before the rebuild tick
    BP_STOP2 = 7487 if BP6 else 7490 if BP_FINE else 7520     # a STOP 20 ms after chunk 2 was built
    CW = ['--chunk-ms', '14742,4914'] + (['--events', '12000' if BP6 else '6000'] if BP_FINE else [])   # probe310: the slow first chunk is polled every 10 ms (~990 ticks); the model's default event limit (400) would stop the run at ~11 s, so the limit is raised (a model budget, not a rule)
    S('64 (probe305) the 5-s chunk re-arm sequence: cold ON, 60 s: twelve chunks, chunk 2+ at 24000 Hz, every start gap 4,950 ms (a 36-ms seam), nothing spoken, port-3 rules OK',
      C24 + ['--press', '0:4004'],
      [r'chunks started: 12,', r'(?m)#2 start +%d ms .* 24000 Hz' % BP_2, r'(?m)chunk-to-chunk start gaps \(ms\): %d(?:, %d){10}$' % (BP_GAP, BP_GAP), r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 60000)
    S('65 (probe305) STOP press mid-chunk (10 s, inside chunk 2): the chunk in flight plays out (EOF 12,414), no chunk 3, the hold release is armed 16 s after the press (26,000 ms), nothing spoken, nothing left pending',
      C24 + ['--press', '0:4004', '--press', '10000:4004'],
      [r'chunks started: 2, ended: 2', r'MessageSendLater\(cave, id 0x13\) due at t=26000 ms', r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 60000)
    S('66 (probe305) STOP press 16 ms after chunk 1 ended and 20 ms before the rebuild tick (7,480 ms): the poll is cancelled, no chunk 2',
      C24 + ['--press', '0:4004', '--press', '%d:4004' % BP_STOP1],
      [r'chunks started: 1, ended: 1', r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 60000)
    S('67 (probe305) STOP press 20 ms after chunk 2 was built (7,520 ms): chunk 2 plays out, no chunk 3',
      C24 + ['--press', '0:4004', '--press', '%d:4004' % BP_STOP2],
      [r'chunks started: 2, ended: 2', r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 60000)
    S('68 (probe305) YIELD at 0x4758 mid-chunk (10 s, inside chunk 2): the mode goes OFF, chunk 2 is the last, the release is armed for 26,000 ms, nothing spoken',
      C24 + ['--press', '0:4004', '--press', '10000:4758'],
      [r'chunks started: 2, ended: 2', r'MessageSendLater\(cave, id 0x13\) due at t=26000 ms', r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 80000)
    S('69 (probe305) SLC disconnect (0x4716) mid-chunk at 10 s with the mode ON: ENSURE waits for the chunk in flight (no 0x1072 / SPEAK while it plays, R1/R3) and the loop goes on (>= 9 chunks by 50 s)',
      C24 + ['--press', '0:4004', '--press', '10000:4716'],
      [r'chunks started: (?:9|1[0-9]),', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 50000)
    S('70 (probe305, worst case Q007) chunk 1 at the stock 8 kHz (14,742 ms: EOF 17,292), later chunks 4,914 ms: the first poll (4,600 after the build) finds it busy and waits in 50-ms polls (rules R1-R5 hold); the loop then runs at the 5-s rhythm',
      CW + ['--press', '0:4004'],
      [r'chunks started: (?:1[0-9]),', r'(?m)#1 start +2550 ms .* 8000 Hz', r'(?m)#2 start +17\d\d\d ms .* 24000 Hz', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 60000)
    S('71 (probe305, worst case Q007) STOP at 2,560 ms, 10 ms after the slow chunk 1 was built: the chunk plays on to 17,292 ms and the hold release (2,560 + 16,000 = 18,560 ms) comes AFTER its end',
      CW + ['--press', '0:4004', '--press', '2560:4004'],
      [r'chunks started: 1, ended: 1', r'(?m)#1 start +2550 ms .* 17292', r'MessageSendLater\(cave, id 0x13\) due at t=18560 ms', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 60000)
    S('72 (probe305, worst case Q007) YIELD at 10 s in the slow chunk 1: mode OFF, chunk 1 is the last, the release is armed for 26,000 ms (after EOF 17,292), nothing spoken',
      CW + ['--press', '0:4004', '--press', '10000:4758'],
      [r'chunks started: 1, ended: 1', r'MessageSendLater\(cave, id 0x13\) due at t=26000 ms', r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 80000)

if 'PAYLOAD_RATE = 24000' in _wrap:
    S('73 (probe305, pair rule) the OLD 8 kHz payload (first four bytes 77 7f 77 c6) is in p2 (writer not run): NO chunk ever starts (the payload check refuses; the cold bring-up and the 1.5-s retries go on, nothing is spoken in 12 s), port-3 rules OK',
      C24 + ['--raw-p2', 'file:build/payload/r3/brown_8000_58968_s63.adpcm', '--press', '0:4004'],
      [r'chunks started: 0, ended: 0', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 12000)

if 'PAYLOAD_RATE = 24000' in _wrap and 'PAYLOAD_BUSY_POLL = 10' in _wrap and 'PAYLOAD_FIRST_POLL = 4880' in _wrap:
    # probe310 (docs/deep/material-2026-10-19/BZ-fast-poll-probe310.md): windowed fast poll, FIRST_POLL 4880 and a 10-ms busy re-poll. Chunk 1 is built at 2,550 ms, so the polls fall at 7,430, 7,440, ... (2,550 + 4,880 + 10 k).
    # The unknown free edge is modelled through --chunk-ms (port 3 reads free at the chunk's EOF = build + the value); the real edge was between about 4,900 and 4,950 ms after the build (period 4,953 ms with a 50-ms grid).
    FE = lambda ms: ['--chunk-ms', str(ms)]
    S('74 (probe310) free edge at 4,903 ms after the build (EOF 7,453): polls 7,430 .. 7,450 busy, 7,460 free: chunk 2 at 7,460, nothing before or after on the 10-ms grid, port-3 rules OK',
      FE(4903) + ['--press', '0:4004'],
      [r'(?m)#2 start +7460 ms', r'(?s)t=7430 ms.*t=7440 ms.*t=7450 ms.*t=7460 ms', r'!t=7420 ms', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 14000)
    S('75 (probe310) free edge at 4,925 ms (EOF 7,475): chunk 2 at the first poll after it, 7,480',
      FE(4925) + ['--press', '0:4004'],
      [r'(?m)#2 start +7480 ms', r'(?m)spoken: \(nothing\)$'] + RULES, 14000)
    S('76 (probe310) free edge at 4,950 ms (EOF 7,500): chunk 2 at 7,500 (the old 50-ms grid sat exactly here)',
      FE(4950) + ['--press', '0:4004'],
      [r'(?m)#2 start +750\d ms', r'(?m)spoken: \(nothing\)$'] + RULES, 14000)
    S('77 (probe310) STOP press at 7,445 ms, INSIDE the fast window (polls at 7,440 and 7,450, EOF 7,464): the pending poll is cancelled, chunk 1 plays out, no chunk 2, the hold release is armed 16 s later (23,445 ms), nothing spoken, nothing left pending',
      C24 + ['--press', '0:4004', '--press', '7445:4004'],
      [r'chunks started: 1, ended: 1', r'MessageSendLater\(cave, id 0x13\) due at t=23445 ms', r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 60000)
    S('78 (probe310) YIELD (0x4758) at 7,445 ms inside the fast window: the mode goes OFF, chunk 1 is the last, the release is armed for 23,445 ms, nothing spoken',
      C24 + ['--press', '0:4004', '--press', '7445:4758'],
      [r'chunks started: 1, ended: 1', r'MessageSendLater\(cave, id 0x13\) due at t=23445 ms', r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 80000)
    S('79 (probe310) SLC disconnect (0x4716) at 7,445 ms inside the fast window with the mode ON: the loop goes on (>= 9 chunks by 50 s), nothing spoken, rules R1-R5 hold',
      C24 + ['--press', '0:4004', '--press', '7445:4716'],
      [r'chunks started: (?:9|1[0-9]),', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 50000)
    S('80 (probe310, worst case Q007) chunk 1 at the stock 8 kHz (14,742 ms, EOF 17,292): the first poll (4,880 after the build) finds it busy and the 10-ms polls run to 17,290 (busy) and 17,300 (free): chunk 2 at 17,300, later chunks at the 5-s rhythm, rules R1-R5 hold at the 10-ms floor',
      CW + ['--press', '0:4004'],
      [r'(?m)#2 start +17300 ms .* 24000 Hz', r'chunks started: (?:1[0-9]),', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 60000)
    S('81 (probe310, worst case Q007) STOP at 14,000 ms inside the 10-ms poll window of the slow chunk 1: the poll is cancelled, the chunk plays on to 17,292 ms, no chunk 2, the release is armed for 30,000 ms (after the end), nothing left pending',
      CW + ['--press', '0:4004', '--press', '14000:4004'],
      [r'chunks started: 1, ended: 1', r'MessageSendLater\(cave, id 0x13\) due at t=30000 ms', r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 60000)
    S('82 (probe310, worst case Q007) YIELD (0x4758) at 14,000 ms inside the slow chunk 1 poll window: mode OFF, chunk 1 is the last, release armed for 30,000 ms, nothing spoken',
      CW + ['--press', '0:4004', '--press', '14000:4758'],
      [r'chunks started: 1, ended: 1', r'MessageSendLater\(cave, id 0x13\) due at t=30000 ms', r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 80000)

if 'PAYLOAD_RATE = 24000' in _wrap and 'PAYLOAD_BUSY_POLL = 6' in _wrap and 'PAYLOAD_FIRST_POLL = 4905' in _wrap:
    # probe311 (docs/deep/material-2026-10-19/CK-fast-poll-probe311.md): FIRST_POLL 4905 and a 6-ms busy re-poll. Chunk 1 is built at 2,550 ms, so the polls fall at 7,455, 7,461, 7,467, ... (2,550 + 4,905 + 6 k).
    # The unknown free edge is modelled through --chunk-ms (port 3 reads free at the chunk's EOF = build + the value); the real edge was between about 4,913 and 4,933 ms after the build (probe310 recording: periods 4.9215-4.9230 s and 4.9305-4.9321 s).
    FE = lambda ms: ['--chunk-ms', str(ms)]
    S('74 (probe311) free edge at 4,903 ms after the build (EOF 7,453): the first poll (7,455) already finds it free: chunk 2 at 7,455, port-3 rules OK',
      FE(4903) + ['--press', '0:4004'],
      [r'(?m)#2 start +7455 ms', r'!t=7449 ms', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 14000)
    S('75 (probe311) free edge at 4,913 ms (EOF 7,463): polls 7,455 and 7,461 busy, 7,467 free: chunk 2 at 7,467',
      FE(4913) + ['--press', '0:4004'],
      [r'(?m)#2 start +7467 ms', r'(?s)t=7455 ms.*t=7461 ms.*t=7467 ms', r'(?m)spoken: \(nothing\)$'] + RULES, 14000)
    S('76 (probe311) free edge at 4,925 ms (EOF 7,475): chunk 2 at the first poll after it, 7,479',
      FE(4925) + ['--press', '0:4004'],
      [r'(?m)#2 start +7479 ms', r'(?m)spoken: \(nothing\)$'] + RULES, 14000)
    S('77 (probe311) free edge at 4,933 ms (EOF 7,483): chunk 2 at 7,485',
      FE(4933) + ['--press', '0:4004'],
      [r'(?m)#2 start +7485 ms', r'(?m)spoken: \(nothing\)$'] + RULES, 14000)
    S('78 (probe311) free edge at 4,950 ms (EOF 7,500): chunk 2 at 7,503 (the old 50-ms grid sat at 7,500)',
      FE(4950) + ['--press', '0:4004'],
      [r'(?m)#2 start +7503 ms', r'(?m)spoken: \(nothing\)$'] + RULES, 14000)
    S('79 (probe311) STOP press at 7,458 ms, INSIDE the fast window (polls at 7,455 and 7,461, EOF 7,464): the pending poll is cancelled, chunk 1 plays out, no chunk 2, the hold release is armed 16 s later (23,458 ms), nothing spoken, nothing left pending',
      C24 + ['--press', '0:4004', '--press', '7458:4004'],
      [r'chunks started: 1, ended: 1', r'MessageSendLater\(cave, id 0x13\) due at t=23458 ms', r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 60000)
    S('80 (probe311) YIELD (0x4758) at 7,458 ms inside the fast window: the mode goes OFF, chunk 1 is the last, the release is armed for 23,458 ms, nothing spoken',
      C24 + ['--press', '0:4004', '--press', '7458:4758'],
      [r'chunks started: 1, ended: 1', r'MessageSendLater\(cave, id 0x13\) due at t=23458 ms', r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 80000)
    S('81 (probe311) SLC disconnect (0x4716) at 7,458 ms inside the fast window with the mode ON: the loop goes on (>= 9 chunks by 50 s), nothing spoken, rules R1-R5 hold',
      C24 + ['--press', '0:4004', '--press', '7458:4716'],
      [r'chunks started: (?:9|1[0-9]),', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 50000)
    S('82 (probe311, worst case Q007) chunk 1 at the stock 8 kHz (14,742 ms, EOF 17,292): the first poll (4,905 after the build) finds it busy and the 6-ms polls run to 17,289 (busy) and 17,295 (free): chunk 2 at 17,295, later chunks at the 5-s rhythm, rules R1-R5 hold at the 6-ms floor',
      CW + ['--press', '0:4004'],
      [r'(?m)#2 start +17295 ms .* 24000 Hz', r'chunks started: (?:1[0-9]),', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 60000)
    S('83 (probe311, worst case Q007) STOP at 14,000 ms inside the 6-ms poll window of the slow chunk 1: the poll is cancelled, the chunk plays on to 17,292 ms, no chunk 2, the release is armed for 30,000 ms (after the end), nothing left pending',
      CW + ['--press', '0:4004', '--press', '14000:4004'],
      [r'chunks started: 1, ended: 1', r'MessageSendLater\(cave, id 0x13\) due at t=30000 ms', r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 60000)
    S('84 (probe311, worst case Q007) YIELD (0x4758) at 14,000 ms inside the slow chunk 1 poll window: mode OFF, chunk 1 is the last, release armed for 30,000 ms, nothing spoken',
      CW + ['--press', '0:4004', '--press', '14000:4758'],
      [r'chunks started: 1, ended: 1', r'MessageSendLater\(cave, id 0x13\) due at t=30000 ms', r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 80000)

if 'PAYLOAD_RATE = 24000' in _wrap and 'NOPURGE = True' in _wrap:
    # probe312 (docs/deep/material-2026-10-19/CN-no-purge-probe312.md; CL-fable-review.md R1): the rebuild after a chunk end sends NO 0x1072 while the audio-busy word is still the cave task (the full gate's HOLD); the full gate (0x1072 + poke + hold)
    # runs when the word is not ours (first chunk, after the release 16 s after an OFF, after a stock owner took or cleared it). T = a 0x1072 the DSP accepted; probe310 sent one per chunk (14 in 60 s), probe312 sends the bring-up gate and the first-chunk gate only.
    T = r'KalimbaSendMessage\(0x1072, [^\n]*-> TRUE'
    def NT(n): return [r'(?s)(?:%s.*){%d}' % (T, n), r'!(?s)(?:%s.*){%d}' % (T, n + 1)]      # exactly n accepted 0x1072 in the run
    S('83 (probe312) cold ON, 60 s: exactly TWO accepted 0x1072 (the bring-up gate and the first-chunk gate), none for the eleven later rebuilds (probe310: 14); twelve chunks, every start gap 4,920 ms, nothing spoken, rules R1-R5 hold',
      C24 + ['--press', '0:4004'],
      NT(2) + [r'chunks started: 12,', r'(?m)chunk-to-chunk start gaps \(ms\): 4920(?:, 4920){10}$', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes', r'!word b=0x0'] + RULES, 60000)
    S('84 (probe312) warm ON (a DSP is resident, --dsp up), 60 s: exactly ONE accepted 0x1072 (the first chunk full gate: the busy word is 0), thirteen chunks, nothing spoken',
      C24 + ['--dsp', 'up', '--press', '0:4004'],
      NT(1) + [r'chunks started: 13,', r'(?m)spoken: \(nothing\)$'] + RULES, 60000)
    S('85 (probe312) ON, OFF at 20 s, ON again at 25 s (inside the 16-s hold release): the restart goes through ENSURE (its own full gate): exactly THREE accepted 0x1072 in all, the later rebuilds are light, nothing spoken',
      C24 + ['--press', '0:4004', '--press', '20000:4004', '--press', '25000:4004'],
      NT(3) + [r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 70000)
    S('86 (probe312) ON, OFF at 20 s, ON again at 60 s (after the release at 36 s): exactly THREE accepted 0x1072 (the restart gate heals nothing it should not), nothing spoken',
      C24 + ['--press', '0:4004', '--press', '20000:4004', '--press', '60000:4004'],
      NT(3) + [r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 100000)
    S('87 (probe312, the heal path) the audio-busy word is cleared at 30 s (a stock owner took and released it): the next rebuild sends the FULL gate once (exactly THREE accepted in all), the ones after are light again, twelve chunks, nothing spoken',
      C24 + ['--audio-busy', '--press', '0:4004', '--mem-at', '30000:fffe=0'],
      NT(3) + [r'chunks started: 12,', r'(?m)spoken: \(nothing\)$'] + RULES, 60000)
    S('88 (probe312) a stock tone is requested at 20 s: it is PARKED behind the cave hold (no stock 0x1072, no purge): exactly TWO accepted 0x1072, the level word stays b=0x2, twelve chunks, no reboot',
      C24 + ['--tone-at', '20000', '--press', '0:4004'],
      NT(2) + [r'chunks started: 12,', r'!word b=0x0', r'!STOPPED', r'(?m)spoken: \(nothing\)$'] + RULES, 60000)
    S('89 (probe312, KNOWN LIMITATION pinned so that a change is noticed) a stock 0x1072 (b=0, +18 dB) reaches the DSP mid-chunk at 20 s although the hold is on (the model forces it; the real stock senders are parked by the hold): probe310 healed it with its next rebuild gate; probe312 does NOT (the busy word is still ours): the later chunks stay at b=0x0 until an OFF/ON (a stop press and a new start send the full gate)',
      C24 + ['--mid-chunk-1072', '20000:0', '--press', '0:4004'],
      NT(2) + [r'word b=0x0', r'word b=0x2', r'chunks started: 12,', r'(?m)spoken: \(nothing\)$'], 60000)
    S('90 (probe312, no change from the volume buttons) volume up (0x400D) and down (0x400E) at 10 s and 15 s: the level moves with the existing VOL path, no accepted 0x1072 (exactly TWO in all), twelve chunks, nothing spoken, rules R1-R5 hold',
      C24 + ['--press', '0:4004', '--press', '10000:400d', '--press', '15000:400e'],
      NT(2) + [r'chunks started: 12,', r'(?m)spoken: \(nothing\)$'] + RULES, 60000)
    S('91 (probe312, warm music start at 24 kHz) the noise runs warm (--dsp up) and a phone starts streaming (0x4758) at 20 s: the existing warm path (auto-start debounce, the noise goes on), exactly ONE accepted 0x1072, thirteen chunks, nothing spoken',
      C24 + ['--dsp', 'up', '--press', '0:4004', '--press', '20000:4758'],
      NT(1) + [r'chunks started: 13,', r'(?m)spoken: \(nothing\)$'] + RULES, 60000)
    S('92 (probe312) SLC disconnect (0x4716) at 20 s with the mode ON: ENSURE restarts the loop (its own gate, then the auto-start): four accepted 0x1072 in all, twelve chunks, the loop goes on, nothing spoken',
      C24 + ['--press', '0:4004', '--press', '20000:4716'],
      NT(4) + [r'chunks started: 12,', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 60000)
    S('93 (probe312) STOP press at 20 s (inside chunk 4): the chunk in flight plays out, no chunk 5, exactly TWO accepted 0x1072, the hold release is armed, nothing spoken, nothing left pending',
      C24 + ['--press', '0:4004', '--press', '20000:4004'],
      NT(2) + [r'chunks started: 4, ended: 4', r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 60000)
    S('94 (probe312, the DSP-gone test of the light gate) the stock UNLOADS the DSP at 30 s while the noise plays: the light rebuild POKE returns FALSE, the refused-transform restart runs the cold bring-up again (two bring-ups = four accepted 0x1072 in all), nothing spoken, the noise resumes (>= 17 chunks by 100 s)',
      C24 + ['--press', '0:4004', '--unload-at', '30000'],
      NT(4) + [r'(?s)DSP loaded and booted.*DSP loaded and booted', r'chunks started: (?:1[7-9]|[2-9][0-9]),', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 100000)
    S('95 (probe312, as 94 with the real-stock reading that StreamKalimbaSink(3) returns 0 without a DSP) the same: the NOSINK 0x10 "and" path is gone (the refused-transform restart replaces it), nothing spoken, the noise resumes',
      C24 + ['--press', '0:4004', '--unload-at', '30000', '--ksink-after-unload', 'zero'],
      NT(4) + [r'(?s)DSP loaded and booted.*DSP loaded and booted', r'chunks started: (?:1[7-9]|[2-9][0-9]),', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 100000)

if 'PAYLOAD_RATE = 48000' in _wrap and 'NOPURGE = True' in _wrap:
    # probe315 (the 48 kHz pair; owner order 2026-10-22): the 24 kHz rows 64-95 re-derived for 58,968 B at 48 kHz = a 2,457 ms chunk. Timeline of the all-48-kHz model (--chunk-ms 2457): chunk 1 is built at 2,550 ms (EOF 5,007); FIRST_POLL 2423 puts the
    # first poll at 4,973 ms, then every 10 ms (4,983, 4,993, 5,003 busy; 5,013 free): chunk 2 at 5,013 ms, and every start gap 2,463 ms (2,423 + 4 x 10 ms): starts at 2,550 + 2,463 k. In 60 s: k = 0 .. 23 = 24 chunks; a warm start (--dsp up) starts 2,000 ms earlier: 25.
    C48 = ['--chunk-ms', '2457']
    # probe316 (the same pair at a 6-ms busy poll): FIRST_POLL 2448 and a 6-ms re-poll: polls at 2,550 + 2,448 + 6 k = 4,998, 5,004, 5,010 (EOF 5,007): chunk 2 at 5,010, start gap 2,460 ms; probe315 (10 ms): FIRST_POLL 2423, polls 4,973 .. 5,013, gap 2,463 ms
    BP6 = 'PAYLOAD_BUSY_POLL = 6' in _wrap
    _mb = re.search(r'(?m)^PAYLOAD_BUSY_POLL = (\d+)', _wrap); _mf = re.search(r'(?m)^PAYLOAD_FIRST_POLL = (\d+)', _wrap)
    _FP, _BPD = (int(_mf.group(1)), int(_mb.group(1))) if (_mb and _mf) else ((2448, 6) if BP6 else (2423, 10))      # probe330: read the pair from the wrapper (8 ms: 2451)
    def FP1(e):    # the first poll at or after the EOF of a chunk built at 2,550 ms with chunk length e ms
        t = 2550 + _FP
        while t < 2550 + e: t += _BPD
        return t
    T2 = FP1(2457); G48 = T2 - 2550
    STOPIN = 2550 + _FP + _BPD // 2 if (_mb and _mf and _BPD not in (6, 10)) else (5000 if BP6 else 4985)       # between two polls inside the fast window (polls 4,998 / 5,004 or 4,983 / 4,993; 8 ms: 5,001 / 5,009)
    CW48 = ['--chunk-ms', '14742,2457', '--events', '12000' if _BPD <= 9 else '6000']
    T = r'KalimbaSendMessage\(0x1072, [^\n]*-> TRUE'
    def NT(n): return [r'(?s)(?:%s.*){%d}' % (T, n), r'!(?s)(?:%s.*){%d}' % (T, n + 1)]      # exactly n accepted 0x1072 in the run
    FE48 = lambda ms: ['--chunk-ms', str(ms)]
    S('64 (probe315) the 2.5-s chunk re-arm sequence: cold ON, 60 s: 24 chunks, chunk 2+ at 48000 Hz, every start gap 2,463 ms (a 6-ms seam), nothing spoken, port-3 rules OK',
      C48 + ['--press', '0:4004'],
      [r'chunks started: 24,', r'(?m)#2 start +%d ms .* 48000 Hz' % T2, r'(?m)chunk-to-chunk start gaps \(ms\): %d(?:, %d){22}$' % (G48, G48), r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 60000)
    S('65 (probe315) STOP press mid-chunk (10 s, inside chunk 4: built 9,939, EOF 12,396): the chunk in flight plays out, no chunk 5, the hold release is armed 16 s after the press (26,000 ms), nothing spoken, nothing left pending',
      C48 + ['--press', '0:4004', '--press', '10000:4004'],
      [r'chunks started: 4, ended: 4', r'MessageSendLater\(cave, id 0x13\) due at t=26000 ms', r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 60000)
    S('66 (probe315) STOP press at 5,008 ms: 1 ms after chunk 1 ended (EOF 5,007) and 5 ms before the rebuild poll (5,013): the poll is cancelled, no chunk 2',
      C48 + ['--press', '0:4004', '--press', '%d:4004' % (5008 if T2 > 5008 else T2 - 1)],      # probe331 (9 ms): the rebuild poll is AT the EOF (5,007), so the STOP goes 1 ms before it
      [r'chunks started: 1, ended: 1', r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 60000)
    S('67 (probe315) STOP press 20 ms after chunk 2 was built (5,033 ms): chunk 2 plays out, no chunk 3',
      C48 + ['--press', '0:4004', '--press', '%d:4004' % (T2 + 20)],
      [r'chunks started: 2, ended: 2', r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 60000)
    S('68 (probe315) YIELD at 0x4758 mid-chunk (10 s, inside chunk 4): the mode goes OFF, chunk 4 is the last, the release is armed for 26,000 ms, nothing spoken',
      C48 + ['--press', '0:4004', '--press', '10000:4758'],
      [r'chunks started: 4, ended: 4', r'MessageSendLater\(cave, id 0x13\) due at t=26000 ms', r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 80000)
    S('69 (probe315) SLC disconnect (0x4716) mid-chunk at 10 s with the mode ON: ENSURE waits for the chunk in flight (no 0x1072 / SPEAK while it plays, R1/R3) and the loop goes on (>= 19 chunks by 50 s)',
      C48 + ['--press', '0:4004', '--press', '10000:4716'],
      [r'chunks started: (?:19|2[0-9]),', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 50000)
    S('70 (probe315, worst case Q007) chunk 1 at the stock 8 kHz (14,742 ms: EOF 17,292), later chunks 2,457 ms: the first poll (4,973) finds it busy and the 10-ms polls run on; they fall at 4,973 + 10 k, the first at or after 17,292 is 17,293: chunk 2 at 17,293, then the 2.5-s rhythm, rules R1-R5 hold',
      CW48 + ['--press', '0:4004'],
      [r'chunks started: (?:1[5-9]|2[0-9]),', r'(?m)#1 start +2550 ms .* 8000 Hz', r'(?m)#2 start +1729\d ms .* 48000 Hz', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 60000)
    S('71 (probe315, worst case Q007) STOP at 2,560 ms, 10 ms after the slow chunk 1 was built: the chunk plays on to 17,292 ms and the hold release (2,560 + 16,000 = 18,560 ms) comes AFTER its end',
      CW48 + ['--press', '0:4004', '--press', '2560:4004'],
      [r'chunks started: 1, ended: 1', r'(?m)#1 start +2550 ms .* 17292', r'MessageSendLater\(cave, id 0x13\) due at t=18560 ms', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 60000)
    S('72 (probe315, worst case Q007) YIELD at 10 s in the slow chunk 1: mode OFF, chunk 1 is the last, the release is armed for 26,000 ms (after EOF 17,292), nothing spoken',
      CW48 + ['--press', '0:4004', '--press', '10000:4758'],
      [r'chunks started: 1, ended: 1', r'MessageSendLater\(cave, id 0x13\) due at t=26000 ms', r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 80000)
    S('73 (probe315, pair rule) the OLD 8 kHz payload (first four bytes 77 7f 77 c6) is in p2 (writer not run): NO chunk ever starts (the payload check refuses; the cold bring-up and the 1.5-s retries go on, nothing is spoken in 12 s), port-3 rules OK',
      C48 + ['--raw-p2', 'file:build/payload/r3/brown_8000_58968_s63.adpcm', '--press', '0:4004'],
      [r'chunks started: 0, ended: 0', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 12000)
    S('74 (probe315) free edge at 2,440 ms after the build (EOF 4,990): polls 4,973 and 4,983 busy, 4,993 free: chunk 2 at 4,993, nothing before it on the 10-ms grid, port-3 rules OK',
      FE48(2440) + ['--press', '0:4004'],
      [r'(?m)#2 start +%d ms' % FP1(2440), r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 9000)
    S('75 (probe315) free edge at 2,455 ms (EOF 5,005): polls to 5,003 busy, chunk 2 at the first poll after it, 5,013',
      FE48(2455) + ['--press', '0:4004'],
      [r'(?m)#2 start +%d ms' % FP1(2455), r'(?m)spoken: \(nothing\)$'] + RULES, 9000)
    S('76 (probe315) free edge at 2,470 ms (EOF 5,020): chunk 2 at the first poll after it, 5,023',
      FE48(2470) + ['--press', '0:4004'],
      [r'(?m)#2 start +%d ms' % FP1(2470), r'(?m)spoken: \(nothing\)$'] + RULES, 9000)
    S('77 (probe315) STOP press at 4,985 ms, INSIDE the fast window (polls at 4,983 and 4,993, EOF 5,007): the pending poll is cancelled, chunk 1 plays out, no chunk 2, the hold release is armed 16 s later (20,985 ms), nothing spoken, nothing left pending',
      C48 + ['--press', '0:4004', '--press', '%d:4004' % STOPIN],
      [r'chunks started: 1, ended: 1', r'MessageSendLater\(cave, id 0x13\) due at t=%d ms' % (STOPIN + 16000), r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 60000)
    S('78 (probe315) YIELD (0x4758) at 4,985 ms inside the fast window: the mode goes OFF, chunk 1 is the last, the release is armed for 20,985 ms, nothing spoken',
      C48 + ['--press', '0:4004', '--press', '%d:4758' % STOPIN],
      [r'chunks started: 1, ended: 1', r'MessageSendLater\(cave, id 0x13\) due at t=%d ms' % (STOPIN + 16000), r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 80000)
    S('79 (probe315) SLC disconnect (0x4716) at 4,985 ms inside the fast window with the mode ON: the loop goes on (>= 17 chunks by 50 s: the ENSURE restart costs about 4 s, as at 24 kHz; the model gives 18 with one 6,485 ms gap), nothing spoken, rules R1-R5 hold',
      C48 + ['--press', '0:4004', '--press', '%d:4716' % STOPIN],
      [r'chunks started: (?:1[7-9]|2[0-9]),', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 50000)
    S('80 (probe315, worst case Q007) STOP at 14,000 ms inside the 10-ms poll window of the slow chunk 1: the poll is cancelled, the chunk plays on to 17,292 ms, no chunk 2, the release is armed for 30,000 ms (after the end), nothing left pending',
      CW48 + ['--press', '0:4004', '--press', '14000:4004'],
      [r'chunks started: 1, ended: 1', r'MessageSendLater\(cave, id 0x13\) due at t=30000 ms', r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 60000)
    S('81 (probe315, worst case Q007) YIELD (0x4758) at 14,000 ms inside the slow chunk 1 poll window: mode OFF, chunk 1 is the last, release armed for 30,000 ms, nothing spoken',
      CW48 + ['--press', '0:4004', '--press', '14000:4758'],
      [r'chunks started: 1, ended: 1', r'MessageSendLater\(cave, id 0x13\) due at t=30000 ms', r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 80000)
    S('83 (probe315) cold ON, 60 s: exactly TWO accepted 0x1072 (the bring-up gate and the first-chunk gate), none for the 22 later rebuilds; 24 chunks, every start gap 2,463 ms, nothing spoken, rules R1-R5 hold',
      C48 + ['--press', '0:4004'],
      NT(2) + [r'chunks started: 24,', r'(?m)chunk-to-chunk start gaps \(ms\): %d(?:, %d){22}$' % (G48, G48), r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes', r'!word b=0x0'] + RULES, 60000)
    S('84 (probe315) warm ON (a DSP is resident, --dsp up), 60 s: exactly ONE accepted 0x1072 (the first chunk full gate: the busy word is 0), 25 chunks, nothing spoken',
      C48 + ['--dsp', 'up', '--press', '0:4004'],
      NT(1) + [r'chunks started: 25,', r'(?m)spoken: \(nothing\)$'] + RULES, 60000)
    S('85 (probe315) ON, OFF at 20 s, ON again at 25 s (inside the 16-s hold release): the restart goes through ENSURE (its own full gate): exactly THREE accepted 0x1072 in all, the later rebuilds are light, nothing spoken',
      C48 + ['--press', '0:4004', '--press', '20000:4004', '--press', '25000:4004'],
      NT(3) + [r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 70000)
    S('86 (probe315) ON, OFF at 20 s, ON again at 60 s (after the release at 36 s): exactly THREE accepted 0x1072, nothing spoken',
      C48 + ['--press', '0:4004', '--press', '20000:4004', '--press', '60000:4004'],
      NT(3) + [r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 100000)
    S('87 (probe315, the heal path) the audio-busy word is cleared at 30 s (a stock owner took and released it): the next rebuild sends the FULL gate once (exactly THREE accepted in all), the ones after are light again, 24 chunks, nothing spoken',
      C48 + ['--audio-busy', '--press', '0:4004', '--mem-at', '30000:fffe=0'],
      NT(3) + [r'chunks started: 24,', r'(?m)spoken: \(nothing\)$'] + RULES, 60000)
    S('88 (probe315) a stock tone is requested at 20 s: it is PARKED behind the cave hold (no stock 0x1072, no purge): exactly TWO accepted 0x1072, the level word stays b=0x2, 24 chunks, no reboot',
      C48 + ['--tone-at', '20000', '--press', '0:4004'],
      NT(2) + [r'chunks started: 24,', r'!word b=0x0', r'!STOPPED', r'(?m)spoken: \(nothing\)$'] + RULES, 60000)
    S('89 (probe315, KNOWN LIMITATION pinned so that a change is noticed) a stock 0x1072 (b=0, +18 dB) reaches the DSP mid-chunk at 20 s although the hold is on: the later chunks stay at b=0x0 until an OFF/ON',
      C48 + ['--mid-chunk-1072', '20000:0', '--press', '0:4004'],
      NT(2) + [r'word b=0x0', r'word b=0x2', r'chunks started: 24,', r'(?m)spoken: \(nothing\)$'], 60000)
    S('90 (probe315) volume up (0x400D) and down (0x400E) at 10 s and 15 s: the level moves with the existing VOL path, no accepted 0x1072 (exactly TWO in all), 24 chunks, nothing spoken, rules R1-R5 hold',
      C48 + ['--press', '0:4004', '--press', '10000:400d', '--press', '15000:400e'],
      NT(2) + [r'chunks started: 24,', r'(?m)spoken: \(nothing\)$'] + RULES, 60000)
    S('91 (probe315, warm music start at 48 kHz) the noise runs warm (--dsp up) and a phone starts streaming (0x4758) at 20 s: the existing warm path, exactly ONE accepted 0x1072, 25 chunks, nothing spoken',
      C48 + ['--dsp', 'up', '--press', '0:4004', '--press', '20000:4758'],
      NT(1) + [r'chunks started: 25,', r'(?m)spoken: \(nothing\)$'] + RULES, 60000)
    S('92 (probe315) SLC disconnect (0x4716) at 20 s with the mode ON: ENSURE restarts the loop (its own gate, then the auto-start): four accepted 0x1072 in all, the loop goes on, nothing spoken',
      C48 + ['--press', '0:4004', '--press', '20000:4716'],
      NT(4) + [r'chunks started: (?:2[2-4]),', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 60000)
    S('93 (probe315) STOP press at 20 s (inside chunk 8: built 19,791, EOF 22,248): the chunk in flight plays out, no chunk 9, exactly TWO accepted 0x1072, the hold release is armed, nothing spoken, nothing left pending',
      C48 + ['--press', '0:4004', '--press', '20000:4004'],
      NT(2) + [r'chunks started: 8, ended: 8', r'mode flag \(id 0x30\) pending: no', r'(?m)spoken: \(nothing\)$', r'cave messages still pending: 0'] + RULES, 60000)
    S('94 (probe315, the DSP-gone test of the light gate) the stock UNLOADS the DSP at 30 s while the noise plays: the light rebuild POKE returns FALSE, the refused-transform restart runs the cold bring-up again (four accepted 0x1072 in all), nothing spoken, the noise resumes (>= 34 chunks by 100 s)',
      C48 + ['--press', '0:4004', '--unload-at', '30000'],
      NT(4) + [r'(?s)DSP loaded and booted.*DSP loaded and booted', r'chunks started: (?:3[4-9]|[4-9][0-9]),', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 100000)
    S('95 (probe315, as 94 with the real-stock reading that StreamKalimbaSink(3) returns 0 without a DSP) the same: nothing spoken, the noise resumes',
      C48 + ['--press', '0:4004', '--unload-at', '30000', '--ksink-after-unload', 'zero'],
      NT(4) + [r'(?s)DSP loaded and booted.*DSP loaded and booted', r'chunks started: (?:3[4-9]|[4-9][0-9]),', r'(?m)spoken: \(nothing\)$', r'mode flag \(id 0x30\) pending: yes'] + RULES, 100000)


fails = 0
# probe288 (CENSUS): scenarios that probe285 passes and probe288 fails BY DESIGN or by the dropped features; each reason is the explanation required by the gate rule. '10' is not run (the yield is dropped: the stream start is not modelled to an end and the run does not terminate in useful time).
XFAIL = {}
if 'CENSUS = True' in _wrap:
    XFAIL = {'1': 'the third press (100 s, warm: the DSP is resident, mode OFF, chunk ended) is the CENSUS press, not a warm start: expected',
             '5': 'the press at 62 s comes after the last chunk ended in the model (61.5 s): an idle press with a resident DSP = the census is spoken: expected',
             '7': 'a resident DSP (--dsp up) with the mode OFF: the press is the census, not a warm start: expected',
             '11': 'warm start by press: the press is the census: expected',
             '12': 'warm start by press: the press is the census: expected',
             '10': 'SKIP: yield dropped (NOYIELD) to make room'}
if 'G5DIAG = True' in _wrap:
    XFAIL['10'] = 'by design: the yield now speaks the read-only report digit (D = 0 with RAM zero, id 0x27 at 66 s); scenarios 50-53 pin it'
ONLY = [x for x in os.environ.get('GATE_ONLY', '').split(',') if x]      # e.g. GATE_ONLY=22,23 runs only those scenarios
_SH = os.environ.get('GATE_SHARD')      # 'i/n': run scenario k of the list when k % n == i (parallel runs on a many-core machine)
for _k, (name, args, rx) in enumerate(SC):
    if ONLY and name.split()[0] not in ONLY: continue
    if _SH and _k % int(_SH.split('/')[1]) != int(_SH.split('/')[0]): continue
    if XFAIL.get(name.split()[0], '').startswith('SKIP'):
        print('skip ' + name); print('      -> ' + XFAIL[name.split()[0]]); continue
    r = subprocess.run([sys.executable, 'tools/cavesim.py', WORDS] + args, cwd=ROOT, capture_output=True, text=True, timeout=int(os.environ.get('GATE_TIMEOUT', '3600')))   # probe311: the 6-ms worst-case rows need >1 h on a loaded machine; GATE_TIMEOUT (s) raises the per-scenario limit, default unchanged
    out = r.stdout + r.stderr
    bad = []
    for p in rx:
        neg = p.startswith('!')
        pat = p[1:] if neg else p
        found = re.search(pat, out) is not None
        if found == neg: bad.append(('present: ' if neg else 'missing: ') + pat)
    if 'STOPPED' in out: bad.append('STOPPED in the simulator')
    _xf = XFAIL.get(name.split()[0])
    print(('xfail ' if (bad and _xf) else 'FAIL ' if bad else 'ok   ') + name)
    for b in bad: print('      -> ' + b)
    if bad and _xf: print('      => expected: ' + _xf)
    fails += bool(bad) and not _xf
print('%d scenario(s), %d failed' % (len(SC), fails))
sys.exit(1 if fails else 0)
