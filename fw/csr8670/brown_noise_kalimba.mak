# Kalimba DSP half. Run through build.sh, which sets BLUELAB and HARDWARE.
OUTPUT=brown_noise_kalimba
DEFS=-DKALASM3
LIBS=core cbops
ASMS=brown_noise.asm
DEBUGTRANSPORT=SPITRANS=USB SPIPORT=0

include $(BLUELAB)/Makefile.dsp
