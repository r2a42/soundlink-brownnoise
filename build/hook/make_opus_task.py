#!/usr/bin/env python3
"""Assemble the single-file Opus consult package: opus_task/ANALYSIS_TASK.md"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HEADER = """# TASK: Bose SoundLink Micro firmware — audio engine analysis consult

You are analyzing DISASSEMBLY of the VM application (XAP2 bytecode, CSR8670
chip) from a Bose SoundLink Micro speaker (stock 3.0.3). We reverse-
engineer it to add a "hold button = brown noise" feature, loaded via USB
DFU only (no hardware access). Answer the three questions at the end using
the listings below. Be concrete: cite addresses.

## Background (proven on hardware)

- We can edit the vm.app inside the RSA-signed filesystem only inside
  "blind windows" (bytes 34..62 of each 64-byte content block) — small
  code caves are placed in zero-padding regions. We CANNOT add files or
  grow flash regions; we CAN blind-edit ~45% of the bytes of certain
  existing files.
- Messages: MessageSendLater(task=AL, id=AH, msg=@(0,Y):@(1,Y),
  delay=@(2,Y)); tasks are TaskData pointers in globals (0x50b timer
  task, 0x512 main UI task).
- Sounds play through an audio request API: 0xdf7f(request_id) ->
  0xdf01 (gate: global 0x570 bit13; logs id to global 0x503; builds a
  10-slot message; arms a 2s watchdog message 0x4757) -> engine
  0x2f8f8 -> 0x2fda8 -> orchestrator 0x2fde2 -> stage functions.
- The engine loads Kalimba DSP apps (.kap) with KalimbaLoad, opens
  StreamKalimbaSink(port), connects streams (StreamConnect), and plays
  content FROM FILESYSTEM FILES (StreamFileSource in 0x30008).
- Filesystem: internal fs has vm.app, data_us (219,528 B of raw 16-bit
  PCM = voice prompts, 13.7s @ 8kHz), rphrases_us (10,486 B directory
  of 16-bit values, interpreted as (offset,length) chunks into
  data_us), and 4 .kap DSP apps (NowSpeakTTS.kap, sbc_decoder.kap,
  soundClearNb/Wb.kap). External flash = second signed fs with 12 more
  language packs (data_XX + rphrases_XX; file numbers: data +8/lang,
  rphrases +12/lang).
- Qualcomm's ADK reference (csr_voice_prompts_plugin) for this chip
  family: prompt playback sends the prompt INDEX to the DSP via
  KalimbaSendMessage(KALIMBA_MSG_FILE_INDEX...), and raw PCM prompts
  connect to StreamKalimbaSink(3) (TONE_VP_MIXING_DSP_PORT).

## Field results (all verified on the device)

1. Stock: long-press center = voice-assistant start. A chirp plays via
   the request API with id 0x35 (the case at 0xace calls 0xdf7f(0x35)
   at 0xae4 and sets LED bits). Pressing again within ~5s = cancel (LED
   only). After ~5s the session times out; next long-press = fresh
   start (guards: 0x9157 count and 0x565 bit7 gate the case body).
2. Our cave (hooked at the 0xae0 call site, proven running) requested
   ids 0x35, 0x36, then a sweep 0x00, 0x01, 0x02, ... through the
   request API: EVERY id plays what sounds like the SAME short chirp.
   No id produced speech, tones, or silence so far.
3. The tone-generator route (StreamRingtoneSource + StreamConfigure
   0x30b + feeding note words into the returned sink) WORKS but at a
   fixed, barely-audible level; volume control words have no effect —
   it bypasses the DSP engine.
4. StreamAudioSink(AUDIO_HARDWARE_CODEC) + direct PCM writes = totally
   silent. The Bose DSP owns the codec output stage.
5. Volume buttons control anything routed through the engine (proven
   with prompts). Hard requirement for the final feature.

## ISA cheat sheet (XAP2; word = operand<<8 | opcode)

- Prefix chaining: words with low byte 0x00 are prefixes; value folds
  v = (v + sext8(operand)) << 8 per prefix. 0x0000 is a standalone NOP.
- ld/st: 0x1n/0x2n, mode: 0=#imm 1=@abs16 2=@(n,X) 3=@(n,Y); reg
  field: 0=AL 1=AH 2=X 3=Y. @(0xffe0..e4) = special regs AH,AL,?,X,Y.
- Arithmetic: add 0x3n, sub 0x5n, cmp 0x8n (C=1 iff a<b), or 0xBn,
  and 0xCn, xor 0xDn; asl/asr #n (0xA0/0xA4) on the 32-bit AH:AL pair.
- bsr = 0x9C (1-3 words; multiword target = last word + operand,
  1-word target = branch addr + operand). rts/leavel pop an INTERNAL
  return stack (X is NOT the return address).
- Branches (1-2 words, target = FIRST word address + operand):
  bra E0, bne F0, beq F4, bcc F8, bcs FC, bgt 20, bge 24, ble 28,
  bls 2C, blt E4.
- enterl -N (0x0B, signed operand) allocates a frame; leavel (0x0F)
  returns. Frame slots are @(n,Y).
- Trap stubs: short sequences ending in a jump to dispatcher 0x291.

## Trap stubs referenced in the listings

0x2a free, 0x42 PanicNull, 0x4a PanicUnlessMalloc, 0x62
MessageSendLater, 0x6a MessageSendConditionally, 0x86 SinkClose,
0x106 StreamConnect, 0x10a StreamConnectDispose, 0x10e
StreamDisconnect, 0x11a StreamConfigure, 0x11e SourceConfigure, 0x122
StreamSourceFromSink, 0x126 SinkAlias, 0x136 SinkSynchronise, 0x15e
StreamUartConfigure, 0x162 StreamRingtoneSource, 0x166
StreamAudioSource, 0x16a StreamAudioSink, 0x182 (unknown), 0x1a2
InquirySetPriority, 0x1b4 FileParent, 0x1b9 StreamFileSource, 0x1be
StreamKalimbaSink, 0x1c3 KalimbaLoad, 0x1cd KalimbaSendMessage, 0x1d2
KalimbaSendLongMessage, 0x1d7 MessageKalimbaTask, 0x283
OperatorResetMultiple.

## Known globals

0x503 last request id (written by 0xdf01); 0x50b/0x512 task ptrs;
0x515, 0x517 ptrs (0x517 dereffed for engine msg slot 8); 0x536
written into engine msg slot 5; 0x56f bit12 selects a banked table
(read via X=0x56f>>12 then @(-21376,X) = per-bank config word);
0x565 bit7 + the count from 0x9157 gate the 0x4003 case; 0x570 bit13 =
request gate; 0x56b bit11 = LED bookkeeping; 0x72e = engine context
ptr (heap block): field @(12,X) bit-packed — low nibble = source kind
(compared to 4), bits 12/13 mode flags, &0xfff0 passed to
StreamKalimbaSink at one site; @(13,X) similar; @(10,X) = nested ptr.

## QUESTIONS (answer with references into the listings)

Q1. Trace the request id from 0xdf01 (stored @(11,Y) there; msg slot 0)
    through 0x2f8f8/0x2fda8/0x2fde2 into the stage functions. Where
    does the id FIRST influence what is played (file choice, chunk
    index, DSP message argument)? Given that ALL ids 0x00..0x3F sound
    like the same chirp, where does the id->content mapping actually
    live (VM vs the NowSpeakTTS.kap DSP app), and which VM-side input
    (if any) changes content?

Q2. We want LOUD, LONG, low-frequency noise with working volume
    buttons. Constraints: blind-window edits only; caves in zero
    padding; can blind-edit ~45% of rphrases_us bytes; data_us PCM
    exists and is engine-played. Rank these routes and say what to try
    first: (a) open StreamKalimbaSink(port) from a cave and write PCM
    directly (which port? what handshake does the engine do first via
    KalimbaSendMessage 0x8024/0x8026?); (b) blind-edit rphrases_us
    entries to repoint (offset,length) pairs at long low-frequency
    data_us ranges (60 Hz energy exists at ~3.65-3.70s, 4.70s, 13.65s);
    (c) keep sweeping request ids beyond 0x3F (the 0x3e9-0x3f2 phrase
    family); (d) anything in the listings we have missed entirely.

Q3. The engine only runs during an active VA session (~5s window after
    each long-press). For indefinite noise we need the engine resident.
    From the listings, what keeps the engine alive (the 0x4757
    watchdog? engine-side timers? the DSP app itself?), and what is
    the cheapest VM-side way to keep it resident (re-request cadence,
    a message to 0x72e's task, faking an engine callback id like
    0x4740/0x474f/0x4753)?

## LISTINGS (static disassembly, decoder-validated)
"""

files = ["df7f", "df01", "2f8f8", "2fda8", "2fde2", "30075", "3011e",
         "30008", "30294", "2ffbe", "2ffd6", "2ff95"]

parts = [HEADER]
for f in files:
    p = os.path.join(ROOT, "build", "analysis", "functions", f + ".lst")
    if os.path.exists(p):
        parts.append("\n----- function listing: %s.lst -----\n" % f)
        parts.append(open(p, encoding="utf-8").read())
    else:
        parts.append("\n----- MISSING: %s -----\n" % f)

out = "".join(parts)
dst = os.path.join(ROOT, "opus_task", "ANALYSIS_TASK.md")
os.makedirs(os.path.dirname(dst), exist_ok=True)
open(dst, "w", encoding="utf-8").write(out)
print("written:", dst, len(out), "chars,", out.count("\n"), "lines")
