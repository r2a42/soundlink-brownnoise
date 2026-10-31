// noisegen425.asm: OPTION-2 generator for probe425 (tools/eq_tune.py): acc -> bass SVF1 -> bass SVF2 (on lp1) + white band-pass SVF3 (on w); Q15 coefficients through the one-word fractional multiply
// (kalsim-proven round-half-even, as probe402). Coefficients (Q15 integers): leak=32456 f11=1694 f21=243 f12=1376 f22=146 f3=3000 q3=26000 gw=-16 ga=11800 gb=16360 gc=18327
// Per sample (w = st >> 11):
//   st  = st * 27145 + 17 ;  acc = acc * leak/32768 + w
//   lp1 += bp1 * f11 ; hp1 = acc - lp1 - bp1 ; bp1 += hp1 * f21               (SVF1 on acc)
//   lp2 += bp2 * f12 ; hp2 = lp1 - lp2 - bp2 ; bp2 += hp2 * f22               (SVF2 on lp1)
//   lp3 += bp3 * f3  ; hp3 = w - lp3 - bp3 * q3 ; bp3 += hp3 * f3             (white band-pass)
//   v = lp2 + w * gw + acc * ga - bp1 * gb + bp3 * gc ;  ring[wr] = v << M[0x29e6]   (shift and wr read from memory in the loop: r0 and r4 hold lp3 and bp3)
// State: DM[0x300] st, [0x301] acc, [0x302] lp1, [0x303] lp3, [0x304] bp1, [0x305] bp3, [0x306] lp2, [0x307] bp2 (two NEW cells beyond 0x305).
// Registers: r0 lp3, r1 lp1, r2 lp2, r3 acc, r4 bp3, r5 st, r6 w then the mix, r7 bp1, r8 bp2, r9 temp, r10 loop count.
.MODULE $M.noisegen425;
   .CODESEGMENT PM;
   .DATASEGMENT DM;

   $reset:
   gen_entry:
   push rLink;
   r0 = 0x2a73;
   call 0x1a27;                 // r0 = free space in the ring
   r10 = r0;                    // sets N/Z
   if LE jump skip_fill;
   r5 = M[0x300];               // st
   r3 = M[0x301];               // acc
   r1 = M[0x302];               // lp1
   r0 = M[0x303];               // lp3
   r7 = M[0x304];               // bp1
   r4 = M[0x305];               // bp3
   r2 = M[0x306];               // lp2
   r8 = M[0x307];               // bp2
   do fill_loop;
      r5 = r5 * 27145 (int);
      r5 = r5 + 17;
      r3 = r3 * 0.990478515625 (frac);      // acc leak
      r6 = r5 ASHIFT -11;                     // w
      r3 = r3 + r6;                           // acc
      r9 = r7 * 0.05169677734375 (frac);     // f11
      r1 = r1 + r9;                           // lp1
      r9 = r3 - r1;
      r9 = r9 - r7;                           // hp1
      r9 = r9 * 0.007415771484375 (frac);     // f21
      r7 = r7 + r9;                           // bp1
      r9 = r8 * 0.0419921875 (frac);     // f12
      r2 = r2 + r9;                           // lp2
      r9 = r1 - r2;
      r9 = r9 - r8;                           // hp2
      r9 = r9 * 0.00445556640625 (frac);     // f22
      r8 = r8 + r9;                           // bp2
      r9 = r4 * 0.091552734375 (frac);     // f3
      r0 = r0 + r9;                           // lp3
      r9 = r4 * 0.79345703125 (frac);     // q3
      r9 = r9 + r0;
      r9 = r6 - r9;                           // hp3
      r9 = r9 * 0.091552734375 (frac);     // f3
      r4 = r4 + r9;                           // bp3
      r9 = r6 * -0.00048828125 (frac);      // gw
      r6 = r2 + r9;                           // lp2 + gw w
      r9 = r3 * 0.360107421875 (frac);      // ga
      r6 = r6 + r9;
      r9 = r7 * 0.499267578125 (frac);      // gb
      r6 = r6 - r9;
      r9 = r4 * 0.559295654296875 (frac);      // gc
      r6 = r6 + r9;
      r9 = M[0x29e6];             // the tone chain's shift (the cave's level ladder pokes it)
      r6 = r6 ASHIFT r9;
      r9 = M[0x2a75];             // wr
      M[r9 + 0] = r6;
      r9 = r9 + 1;
      r9 = r9 AND 0xff;
      r9 = r9 OR 0x100;
      M[0x2a75] = r9;
   fill_loop:
   M[0x300] = r5;
   M[0x301] = r3;
   M[0x302] = r1;
   M[0x303] = r0;
   M[0x304] = r7;
   M[0x305] = r4;
   M[0x306] = r2;
   M[0x307] = r8;
   skip_fill:
   r1 = -31899;                 // 0xFF8365: the timer struct
   r2 = M[0x2aac];
   r3 = 0x2a00;                 // this routine
   call 0x1a8d;
   jump 0x1a9b;
.ENDMODULE;
