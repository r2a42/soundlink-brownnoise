# The DSP-generator route: noise made inside the Kalimba DSP (how it works, how it was found, what to reuse)

Purpose: a technical write-up of the route that finally worked (probes 361-380, 2026-10-28), written so that another project on a CSR8670 / BlueCore "gordon" speaker can reuse the findings without re-deriving them.
Status / last verified: 2026-10-28. Everything marked **proven** was observed on the real speaker (unit 2, firmware 3.0.3.6546) through spoken or recorded read-backs; addresses are DSP data-memory (DM) or program-memory (PM) word addresses of the `sbc_decoder` application.
Note: this page describes the first 45-word generator (probe380); the shipped, ear-tuned 67-word generator is described in `docs/ear-tuned-eq.md`.
Read next: `docs/CURRENT-STATE.md`, `docs/topics/audio-path-and-dsp.md`, `docs/topics/probing-method.md`.

## 1. The idea

The VM (the application CPU) can send small messages to the Kalimba DSP. The stock `sbc_decoder` DSP application answers two of them for debugging: a PEEK (read two DM words at any address) and a POKE (write one DM word at any address). Through POKE the VM can also write the DSP's own **program memory**, because the DSP's PM RAM is mapped into DM address space by a window that one register enables. So the VM can put a small program into the running DSP and redirect the DSP's audio timer to it: the DSP then generates the noise itself.

## 2. The message interface (proven)

`KalimbaSendMessage(id, w1, w2, w3, w4)` from the cave: AL = id, AH = w1, stack slots 0, 1, 2 = w2, w3, w4.
- PEEK id 0x7AB2: address = (w2 << 16) + w1. The DSP replies with a MESSAGE_FROM_KALIMBA (0x8024) whose words 1-4 are M[a] low, M[a] high, M[a+1] low, M[a+1] high (16-bit words). The VM receives it as message pointer in AL; reload X from your own frame (see the lessons).
- POKE id 0x7AB3: address as above, value = w3 | (w4 << 16) (24-bit).
- Addresses at or above 0x10000 read as 0 through the handler in the forms we tried with a nonzero high word, EXCEPT the PM windows (below). DM2 and the memory-mapped registers are reached by their 16-bit sign-extended form with high word 0: the cell the code calls 0xFF8367 is read as 0x8367; the register 0xFFFE65 as 0xFE65.

## 3. Memory map facts (proven unless marked)

- PM RAM is 0x0000-0x2BFF (the flash-overlay code cache is 0x2C00-0x2FFF, not free). The resident program of `sbc_decoder` ends below 0x2400; PM 0x2400-0x2BFF reads 0 and is free.
- PM window: write 1 to the register at 0xFE65 (= PM_WIN_ENABLE, 0xFFFE65), after which PM address a is visible at DM 0x030000 + a (LO 16 bits of the 32-bit instruction word) and DM 0x020000 + a (HI 16 bits); a 24-bit view sits at 0x040000. The enable register reads back 0. Proven by reading the DSP's own instruction at PM 0x06C4 (LO half 0x0010) and writing and reading back an unused word. The window must be enabled again in every DSP session; a DSP reload (every noise start) resets it.
- The tone ring (the buffer the mixer reads) is a structure {size, read pointer, write pointer} at DM 0x2A73-0x2A75: size 0x100, ring storage 0x100-0x1FF; a second (unused, mono) ring structure at 0x2A76. Ring words are the 16-bit sample shifted left by M[0x29E6] (the tone chain's shift); the mixer multiplies by M[0x28F6] (the gain). The cave's volume ladder pokes both.
- The tone-copy timer: struct {next, time, handler, id} at DM2 0xFF8365 (read as 0x8365); the handler pointer at 0x8367 holds 0x16C3 while the stock handler runs, and the stock handler reschedules itself, so a single POKE of 0x8367 redirects the next tick. The copy period M[0x2AAC] = 4000 us at 32 kHz (128e6 / rate).
- Free DM: 0x200-0x3FF read 0 and no code references them (ring 1 sits in 0x200-0x2FF but is unused in mono).

## 4. The generator (proven)

`build/dsp/noisegen.asm`, per timer tick, fills the free space of the tone ring: a 24-bit LCG (multiplier -4508331, increment 17) feeds a leaky integrator (acc -= acc >> 9; acc += state >> 7), a bass shelf (two one-pole low-passes, shifts 6 and 8, gain 4) matches the approved recorded noise within about 2 dB, the result is shifted by M[0x29E6] and stored; write pointer wraps inside 0x100-0x1FF; state in DM 0x300-0x303; the routine reschedules itself with the stock tail. 45 PM words after `build/dsp/compact.py` turns five two-word absolute branches into the stock one-word relative forms. Bit-exact Python model: the tuning scripts used 24-bit semantics (wrap, floor shifts).

## 5. Delivery from the VM (proven)

The program is carried as a data table in seven whole 14-word bands of the VM cave's const window (the VM reads its own window words as data), written into `out` by `ladder_core.py` under the `GEN` flag. At every noise start the cave (`ladder_ext.py`, blocks GLDM/GLRUN/GLDPUT/HOOKP): unhooks (POKE 0x8367 := 0x16C3) and enables the PM window; writes 7 words per message, 50 ms apart (LO half to window 3, HI half to window 2); hooks (POKE 0x8367 := 0x2A00) twice. Hook is written last, unhook first, so a half-written instruction never executes. At OFF the cave mutes and unhooks.

## 6. How the findings were obtained (method)

A read-only census speaks one DSP word per console event as seven battery-percent prompts (digit d = (d+1)*10 percent), recorded by the laptop microphone and decoded slot by slot with a speech recogniser; the seventh digit is a check digit. Console events are injected over USB (`tools/csr/virtual_press.py`, `ev <decimal>` after the unit-keyed unlock). Each probe is a normal gated flash (`docs/FLASH-PROTOCOL.md`).

## 7. Lessons that cost time (reuse these)

1. A stock event id is NOT inert because you never saw it used: console `ev 16417` (0x4021) is `BootSetMode(7)` and made the speaker enumerate as the bare CSR identity 05A7:4005 (only a USB replug cured it); 0x4022 enters the loader. Use ids in the default arm of the stock event switch (`tools/switchtab.py 0x1749`; case = id - 0x4001).
2. A reply handler that is entered with the message pointer in AL must reload X from its frame; reading through a stale X returned the same wrong word for every address.
3. Sending 14 delayed messages in one reply handler reset the speaker; 7 were fine (the message pool is small).
4. After any ev, check the USB node's LastArrivalDate: a silent reset does not show in `bose-dfu list`.
5. A zero read is not proof of free memory (a cold-loaded DSP reads 0 everywhere); check the linker script (`adk/.../gordon.link`) and the stock disassembly.
6. Offline simulators do not model DSP memory; the hardware read-back is the proof.

## 8. Reuse for other projects

The same two messages give a read/write window into the stock DSP of any speaker that ships the `sbc_decoder` application; the PM window plus the tone-copy timer hook is a general way to run custom DSP code (a tone, a filter, a noise source) without touching the signed filesystem.

## 9. Update 2026-10-31: the v0.2.0 generator

The 45-word generator of section 3 was replaced by a 67-word state-variable-filter chain (`build/dsp/noisegen425.asm`) tuned by ear to a direct recording of the source; the delivery method (PM window write plus the tone-copy timer hook) is unchanged. How it was tuned, the volume cap and the power-off fix: `docs/ear-tuned-eq.md`.
