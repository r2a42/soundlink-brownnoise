# VM half plus the merged flash image. Run through build.sh.
OUTPUT=brown_noise
HARDWARE_INDEX=1
DEFS=$(EXTRA_DEFS)
DEBUGTRANSPORT=SPITRANS=USB SPIPORT=0
EXECUTION_MODE=hw_default
STACKSIZE=0
# Only used by the ADK's flash/keys targets, which are blocked below.
TRANSPORT=bcsp
FIRMWARE=unified
BUILD_MERGE=merge
FIRMWAREIMAGE=
LIBRARY_VERSION=
GENERATE_MAP=1

INPUTS=main.c

# The ADK's flash/keys targets burn the whole internal flash over SPI and
# can replace the speaker's own PS keys (trims, BDADDR, pairings). Program
# by hand instead, following README.md.
ifneq (,$(filter flash flash_internal keys,$(MAKECMDGOALS)))
$(error flash/keys targets are disabled for this project; see README.md)
endif

include $(BLUELAB)/Makefile.vm
