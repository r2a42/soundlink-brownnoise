/* VM application for the brown-noise DSP app on CSR8670.

   Loads brown_noise_kalimba.kap from the filesystem, connects Kalimba
   output ports 0/1 to DAC channels A/B at 48 kHz, and starts the DSP.
   Structure follows the ADK 4.4 my_first_dsp_app example. */

#include <kalimba.h>
#include <kalimba_standard_messages.h>
#include <message.h>
#include <file.h>
#include <string.h>
#include <panic.h>
#include <sink.h>
#include <source.h>
#include <stream.h>
#include <pio.h>
#include <app/audio/audio_if.h>

/* PIO5 is held high from reset by Bose's boot PS key and by its app,
   even across the reboot into the loader. On the chip it is a plain PIO
   (the CSR8670 keeps its own regulators latched internally), so it
   drives something on Bose's board whose role is unknown
   (../../firmware/bose/vm_app_notes.md). brown_noise.psr sets the same
   boot state; the app drives it high again first thing and never lets
   it go low. */
#define HOLD_HIGH_PIO 5

/* PIO that enables the speaker amplifier. Unknown for the SoundLink
   Micro: build with -DAMP_ENABLE_PIO=<n> once it is identified (see
   README.md). Left undefined, no PIO is driven. */
#if defined(AMP_ENABLE_PIO) && AMP_ENABLE_PIO == HOLD_HIGH_PIO
#error "AMP_ENABLE_PIO must not be PIO5, which Bose holds high"
#endif

/* DAC gain, 0..CODEC_OUTPUT_GAIN_RANGE (codec gain table index). */
#ifndef DAC_GAIN
#define DAC_GAIN 10
#endif
#if DAC_GAIN < 0 || DAC_GAIN > CODEC_OUTPUT_GAIN_RANGE
#error "DAC_GAIN out of range"
#endif

#define SAMPLE_RATE 48000

static const char kap[] = "brown_noise_kalimba/brown_noise_kalimba.kap";

static uint32 pio_drive_high(uint32 mask);
static void start_kalimba(void);
static void connect_streams(void);

int main(void)
{
    /* No Panic here: a panic resets the chip, and PIO5 would fall with
       its weak pull-down until the boot PS key takes effect again. */
    (void)pio_drive_high(1UL << HOLD_HIGH_PIO);
    start_kalimba();
    connect_streams();
    PanicFalse(KalimbaSendMessage(KALIMBA_MSG_GO, 0, 0, 0, 0));
    MessageLoop();
    return 0;
}

/* Level before direction, so the pin never drives low on the way to
   high. Both traps return the pins they could not change (and change
   none of them in that case); so does this. */
static uint32 pio_drive_high(uint32 mask)
{
    uint32 failed = PioSet32(mask, mask);
    return failed ? failed : PioSetDir32(mask, mask);
}

static void start_kalimba(void)
{
    FILE_INDEX index = FileFind(FILE_ROOT, kap, strlen(kap));
    PanicFalse(index != FILE_NONE);
    PanicFalse(KalimbaLoad(index));
}

static void connect_streams(void)
{
    Sink dac_a = StreamAudioSink(AUDIO_HARDWARE_CODEC, AUDIO_INSTANCE_0, AUDIO_CHANNEL_A);
    Sink dac_b = StreamAudioSink(AUDIO_HARDWARE_CODEC, AUDIO_INSTANCE_0, AUDIO_CHANNEL_B);

    PanicFalse(SinkConfigure(dac_a, STREAM_CODEC_OUTPUT_RATE, SAMPLE_RATE));
    PanicFalse(SinkConfigure(dac_b, STREAM_CODEC_OUTPUT_RATE, SAMPLE_RATE));
    PanicFalse(SinkSynchronise(dac_a, dac_b));

#ifdef AMP_ENABLE_PIO
    PanicFalse(pio_drive_high(1UL << AMP_ENABLE_PIO) == 0);
#endif

    PanicFalse(SinkConfigure(dac_a, STREAM_CODEC_OUTPUT_GAIN, DAC_GAIN));
    PanicFalse(SinkConfigure(dac_b, STREAM_CODEC_OUTPUT_GAIN, DAC_GAIN));

    PanicFalse(StreamConnect(StreamKalimbaSource(0), dac_a));
    PanicFalse(StreamConnect(StreamKalimbaSource(1), dac_b));
}
