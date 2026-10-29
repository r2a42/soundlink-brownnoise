// *****************************************************************************
// Brown-noise generator for the CSR8670 (gordon) Kalimba DSP.
//
// A leaky integrator of white noise (the idea of ../src/noise.c, not its
// exact arithmetic), in 24-bit fractional arithmetic, then a one-pole
// high-pass to keep sub-bass off the small driver:
//    acc = acc - acc/512 + white/64,        |acc| clamped to 0.5
//    y   = y - y/64 + (acc - acc_prev),     |y|   clamped to 0.5
// white is a 24-bit LCG (multiplier and increment from $math.rand).
// The leak corner is about fs/(2*pi*512) = 15 Hz and the high-pass
// corner fs/(2*pi*64) = 119 Hz at 48 kHz, so the spectrum falls 6 dB per
// octave above ~120 Hz and is flat below it. The input is pre-scaled by
// 1/64 instead of the output so the integrator fits in 24 bits; both
// clamps keep every sum below 1.0, so nothing can wrap.
//
// Output: two MMU ports (DAC A/B, connected by the VM app), serviced by a
// 1.5 ms timer interrupt exactly as in the ADK my_first_dsp_app example.
// *****************************************************************************

#define $TMR_PERIOD_AUDIO_COPY         1500
#define $AUDIO_CBUFFER_SIZE            512
#define $BLOCK_SIZE                    ($AUDIO_CBUFFER_SIZE/2)
#define $LCG_MULT                      -4508331
#define $LCG_INC                       17
#define $LEAK_SHIFT                    -9
#define $INPUT_SHIFT                   -6
#define $HP_SHIFT                      -6
#define $ACC_LIMIT                     0.5

#include "core_library.h"
#include "cbops_library.h"

.MODULE $M.main;
   .CODESEGMENT PM;
   .DATASEGMENT DM;

   $main:

   .CONST  $AUDIO_LEFT_OUT_PORT    ($cbuffer.WRITE_PORT_MASK + 0);
   .CONST  $AUDIO_RIGHT_OUT_PORT   ($cbuffer.WRITE_PORT_MASK + 1);

   .VAR/DMCIRC $audio_out_left[$AUDIO_CBUFFER_SIZE];
   .VAR/DMCIRC $audio_out_right[$AUDIO_CBUFFER_SIZE];

   .VAR $audio_out_left_cbuffer_struc[$cbuffer.STRUC_SIZE] =
       LENGTH($audio_out_left), &$audio_out_left, &$audio_out_left;
   .VAR $audio_out_right_cbuffer_struc[$cbuffer.STRUC_SIZE] =
       LENGTH($audio_out_right), &$audio_out_right, &$audio_out_right;

   .VAR $audio_out_timer_struc[$timer.STRUC_SIZE];

   // cbuffers -> DAC ports: 24-bit samples shifted down to the 16-bit port
   .VAR $audio_out_copy_struc[] =
      &$audio_out_left_shift_op,
      2,
      &$audio_out_left_cbuffer_struc,
      &$audio_out_right_cbuffer_struc,
      2,
      $AUDIO_LEFT_OUT_PORT,
      $AUDIO_RIGHT_OUT_PORT;

   .BLOCK $audio_out_left_shift_op;
      .VAR $audio_out_left_shift_op.next = &$audio_out_right_shift_op;
      .VAR $audio_out_left_shift_op.func = &$cbops.shift;
      .VAR $audio_out_left_shift_op.param[$cbops.shift.STRUC_SIZE] =
         0,                            // Input index
         2,                            // Output index
         -8;                           // Shift amount
   .ENDBLOCK;

   .BLOCK $audio_out_right_shift_op;
      .VAR $audio_out_right_shift_op.next = $cbops.NO_MORE_OPERATORS;
      .VAR $audio_out_right_shift_op.func = &$cbops.shift;
      .VAR $audio_out_right_shift_op.param[$cbops.shift.STRUC_SIZE] =
         1,                            // Input index
         3,                            // Output index
         -8;                           // Shift amount
   .ENDBLOCK;

   call $stack.initialise;
   call $interrupt.initialise;
   call $message.initialise;
   call $cbuffer.initialise;

   call $message.send_ready_wait_for_go;

   // Start the output timer just after the DAC buffer wraps so left and
   // right stay in step (see my_first_dsp_app.asm for the reasoning).
   wait_for_dac_buffer_wraparound:
      r0 = $AUDIO_LEFT_OUT_PORT;
      call $cbuffer.calc_amount_space;
      Null = r0 - 32;
   if POS jump wait_for_dac_buffer_wraparound;

   r1 = &$audio_out_timer_struc;
   r2 = $TMR_PERIOD_AUDIO_COPY;
   r3 = &$audio_out_copy_handler;
   call $timer.schedule_event_in;

   fill_loop:
      call $brown_noise_fill;
      Null = r0;
      if Z call $timer.1ms_delay;
   jump fill_loop;

.ENDMODULE;

// *****************************************************************************
// MODULE:
//    $audio_out_copy_handler
//
// DESCRIPTION:
//    Timer interrupt: copy the internal cbuffers to the DAC MMU ports.
// *****************************************************************************
.MODULE $M.audio_out_copy_handler;
   .CODESEGMENT PM;
   .DATASEGMENT DM;

   $audio_out_copy_handler:

   $push_rLink_macro;

   r8 = &$audio_out_copy_struc;
   call $cbops.copy;

   r1 = &$audio_out_timer_struc;
   r2 = $TMR_PERIOD_AUDIO_COPY;
   r3 = &$audio_out_copy_handler;
   call $timer.schedule_event_in;

   jump $pop_rLink_and_rts;

.ENDMODULE;

// *****************************************************************************
// MODULE:
//    $brown_noise_fill
//
// DESCRIPTION:
//    If both output cbuffers have room for a block, write $BLOCK_SIZE brown
//    noise samples (same sample to left and right).
//
// OUTPUTS:
//    r0 = 1 if a block was written, 0 if there was no room
//
// TRASHED REGISTERS:
//    r0-r7, r10, I0, L0, I4, L4
// *****************************************************************************
.MODULE $M.brown_noise_fill;
   .CODESEGMENT PM;
   .DATASEGMENT DM;

   .VAR lcg_state = 21845;
   .VAR acc = 0;
   .VAR hp_y = 0;
   .VAR hp_prev = 0;

   $brown_noise_fill:

   $push_rLink_macro;

   r0 = &$audio_out_left_cbuffer_struc;
   call $cbuffer.calc_amount_space;
   Null = r0 - $BLOCK_SIZE;
   if NEG jump no_room;
   r0 = &$audio_out_right_cbuffer_struc;
   call $cbuffer.calc_amount_space;
   Null = r0 - $BLOCK_SIZE;
   if NEG jump no_room;

   call $interrupt.block;

   r0 = &$audio_out_left_cbuffer_struc;
   call $cbuffer.get_write_address_and_size;
   I0 = r0;
   L0 = r1;
   r0 = &$audio_out_right_cbuffer_struc;
   call $cbuffer.get_write_address_and_size;
   I4 = r0;
   L4 = r1;

   r5 = M[lcg_state];
   r3 = M[acc];
   r1 = M[hp_y];
   r2 = M[hp_prev];
   r6 = $ACC_LIMIT;
   r7 = -$ACC_LIMIT;

   r10 = $BLOCK_SIZE;
   do gen_loop;
      // white: 24-bit LCG
      r5 = r5 * $LCG_MULT (int);
      r5 = r5 + $LCG_INC;
      // leak: acc -= acc/512
      r4 = r3 ASHIFT $LEAK_SHIFT;
      r3 = r3 - r4;
      // integrate: acc += white/64
      r4 = r5 ASHIFT $INPUT_SHIFT;
      r3 = r3 + r4;
      // clamp to +/-0.5
      Null = r3 - r6;
      if GT r3 = r6;
      Null = r3 - r7;
      if LT r3 = r7;
      // high-pass: y += (acc - acc_prev) - y/64
      r4 = r1 ASHIFT $HP_SHIFT;
      r1 = r1 - r4;
      r4 = r3 - r2;
      r1 = r1 + r4;
      r2 = r3;
      // clamp to +/-0.5
      Null = r1 - r6;
      if GT r1 = r6;
      Null = r1 - r7;
      if LT r1 = r7;
      M[I0,1] = r1;
      M[I4,1] = r1;
   gen_loop:

   M[lcg_state] = r5;
   M[acc] = r3;
   M[hp_y] = r1;
   M[hp_prev] = r2;

   r0 = &$audio_out_left_cbuffer_struc;
   r1 = I0;
   call $cbuffer.set_write_address;
   r0 = &$audio_out_right_cbuffer_struc;
   r1 = I4;
   call $cbuffer.set_write_address;
   L0 = 0;
   L4 = 0;

   call $interrupt.unblock;

   r0 = 1;
   jump $pop_rLink_and_rts;

   no_room:
   r0 = 0;
   jump $pop_rLink_and_rts;

.ENDMODULE;
