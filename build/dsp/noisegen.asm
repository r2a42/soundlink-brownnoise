// noisegen.asm: DSP-side brown-noise generator for the Bose SoundLink Micro tone path (CSR8670 / gordon Kalimba).
// It replaces the stock tone-copy timer handler (0x16c3) of the sbc_decoder DSP application: the VM writes this code into
// free DSP program memory through the PM window (POKE 0x7AB3, enable M[0xFFFE65] := 1), then makes the next tick run it by
// ONE write of M[0xFF8367] := its address (field log 2026-10-28, probes 374-377).
//
// Per tick it fills the tone ring {size 0x100, rd, wr} at DM[0x2A73] (ring storage DM[0x100..0x1FF]) with brown noise:
//   st  = st * -4508331 + 17                       (24-bit LCG, the same constants as fw/csr8670/brown_noise.asm)
//   acc = acc - (acc >> 9) + (st >> 7)             (leaky integrator, corner about 15 Hz at 48 kHz)
//   la += (acc - la) >> 6 ; lb += (acc - lb) >> 8  (one-pole low-passes about 120 Hz and 30 Hz)  [lb 7 -> 8: hardware p380a showed the bass 5 dB lighter than the payload]
//   v   = (acc + ((la - lb) << 2)) >> 6            (a bass bump near 120 Hz as the approved ADPCM payload has; no 0.85 multiply: +1.4 dB, 2 PM words less)
//   ring[wr] = v << M[0x29e6]; wr = ((wr + 1) & 0xFF) | 0x100   (no clamp: the ring words are 24-bit, peaks reach about 3.6 sigma = 42k at rms 11.7k; the stock watchdog 0x17ab is not called)
// then it reschedules itself (the stock tail) and returns.
// State: DM[0x300] st, [0x301] acc, [0x302] la, [0x303] lb (a zero block at start; nothing else uses DM 0x300..0x3FF here).
// Bit-exact model: build/dsp/gen_model.py. Linked at PM 0x2A00 with build/dsp/gen.link (PM_REGION narrowed).
.MODULE $M.noisegen;
   .CODESEGMENT PM;
   .DATASEGMENT DM;

   $reset:
   gen_entry:
   push rLink;
   r0 = 0x2a73;
   call 0x1a27;                 // r0 = free space in the ring = (rd - wr - 1) mod size
   r10 = r0;
   Null = r10 + Null;
   if LE jump skip_fill;
   r4 = M[0x2a75];              // wr
   r5 = M[0x300];
   r3 = M[0x301];
   r1 = M[0x302];
   r2 = M[0x303];
   r0 = M[0x29e6];             // the tone chain's shift (ring word = 16-bit sample << M[0x29e6]; the cave's level ladder pokes it)
   do fill_loop;
      r5 = r5 * -4508331 (int);
      r5 = r5 + 17;
      r6 = r3 ASHIFT -9;
      r3 = r3 - r6;
      r6 = r5 ASHIFT -7;
      r3 = r3 + r6;
      r6 = r3 - r1;
      r6 = r6 ASHIFT -6;
      r1 = r1 + r6;
      r6 = r3 - r2;
      r6 = r6 ASHIFT -8;
      r2 = r2 + r6;
      r6 = r1 - r2;
      r6 = r6 ASHIFT 2;
      r6 = r6 + r3;
      r6 = r6 ASHIFT -6;
      r6 = r6 ASHIFT r0;
      M[r4 + 0] = r6;
      r4 = r4 + 1;
      r4 = r4 AND 0xff;
      r4 = r4 OR 0x100;
   fill_loop:
   M[0x2a75] = r4;
   M[0x300] = r5;
   M[0x301] = r3;
   M[0x302] = r1;
   M[0x303] = r2;
   skip_fill:
   r1 = -31899;                 // 0xFF8365: the timer struct (16-bit sign-extended form)
   r2 = M[0x2aac];
   r3 = 0x2a00;                 // this routine
   call 0x1a8d;
   jump 0x1a9b;
.ENDMODULE;
