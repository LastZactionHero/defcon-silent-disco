"""
Board configuration for the DEFCON silent-disco badge (RP2040).

Every value here was verified against the KiCad schematic AND confirmed by
bring-up testing on real hardware.  See BADGE.md for the story behind the
quirks (especially the swapped LED clock/data lines).

Pins are GPIO numbers (GPn), not physical package pins.
"""

# ---------------------------------------------------------------------------
# SK9822 addressable RGB LEDs  (x4, daisy-chained)   -- LED1..LED4
# ---------------------------------------------------------------------------
# Rev 2 boards fixed the SK9822 footprint, so clock/data match the schematic
# net names (verified 2026-07-24: schematic mapping lights the chain, the old
# swapped mapping does not).  Rev 1 boards had DIN/CIN reversed and need
# LED_CLK=25 / LED_DAT=24 -- flip these two values if running on a rev 1 board.
# All four LEDs must share the same physical orientation or the chain breaks.
# GP24/GP25 are NOT hardware-SPI capable on RP2040 -> the driver bit-bangs.
LED_CLK = 24
LED_DAT = 25
LED_COUNT = 4

# SK9822 global brightness, 0..31.  This is a CURRENT setting, not a duty cycle:
# unlike the APA102 (which PWMs this field at ~580 Hz), the SK9822 applies it as
# an analog current scale, so turning it down genuinely reduces the current the
# chain draws rather than just chopping it.
#
# Because this is an analog current scale rather than a duty cycle, turning it
# up is electrically QUIET -- the audible coupling comes from mid-range colour
# values (~4.7 kHz channel PWM), not from brightness.  Verified 2026-07-24 by
# holding average current constant and varying only duty: only the 50%-duty case
# was audible.  lights.py therefore uses saturated colours and dims with this
# field, so 12 is fine.  See BADGE.md quirk 7.
LED_BRIGHTNESS = 12

# Bitmask of which LEDs in the chain are allowed to illuminate; bit 0 == LED1
# (first in the daisy chain), bit 3 == LED4.  0b1111 is all of them.
# Every LED is still clocked every frame -- masked ones are just forced to black
# -- so this changes LED CURRENT without changing the bit-bang traffic.  That
# makes it a clean probe for how the chain couples into the audio: if only the
# LEDs nearest the DAC/amp cause hum it is radiated/capacitive, whereas if any
# LED does it equally it is the shared supply rail.
# All four: the proximity test came back negative (LED1, furthest from the jack
# and amp, was just as audible), which ruled out radiated/positional coupling.
LED_ACTIVE_MASK = 0b1111
# SK9822 byte order after the per-LED brightness byte is Blue, Green, Red.
# (Standard APA102/SK9822 ordering; adjust in sk9822.py if colors look wrong.)

# ---------------------------------------------------------------------------
# Audio DAC  (TM8211 == PT8211 clone)  over I2S  -> TDA1308 HP amp -> 3.5mm jack
# ---------------------------------------------------------------------------
# RP2040 constraint: the I2S word-select pin must be sck+1.  GP8 == GP7+1. OK.
# The DAC needs NO master clock (MCLK) and has no mute/enable pin.
I2S_ID = 0
I2S_SCK = 7   # bit clock  (BCK / SCK)
I2S_WS = 8    # word select (LRCK / WS)   -- must be I2S_SCK + 1
I2S_SD = 6    # serial data (DIN)

# ⚠️ The TM8211 needs LSB-JUSTIFIED framing (data ends at the WS edge), but
# MicroPython's I2S only emits standard/Philips framing (data delayed one BCK).
# With 16-bit frames that misalignment shifted every sample one bit and dropped
# the PREVIOUS sample's LSB into the DAC's SIGN bit, so the output sat near full
# scale regardless of amplitude and software volume did nothing.
# Workaround (verified on hardware 2026-07-24): use 32-BIT frames and place each
# 16-bit sample in bits 16..1, via dsp.pcm16_to_lsbj32().  The one-BCK delay then
# aligns our bits with the last 16 bits of the frame -- what an LSBJ DAC latches.
I2S_BITS = 32

# ---------------------------------------------------------------------------
# Buttons  (active-low; enable internal pull-ups; pressed == 0)
# ---------------------------------------------------------------------------
# Physical silk / net name  ->  GPIO  ->  player function
#   SYNC    GP12  -> "sync"       (cycles the LED light mode)
#   VOL-    GP13  -> "vol_down"
#   VOL+    GP14  -> "vol_up"
#   CH      GP15  -> "play_pause" (CH button repurposed)
BTN_SYNC = 12
BTN_VOL_DN = 13
BTN_VOL_UP = 14
BTN_PLAY = 15

# ---------------------------------------------------------------------------
# microSD card  over SPI0
# ---------------------------------------------------------------------------
# Uses the patched sdcard.py in this directory.  The card's CMD8 response
# glitches its R1 byte on bus turnaround on this board; the driver detects a
# v2 card from the voltage echo instead.  There is NO MISO pull-up on the
# board, so keep the clock conservative.  Measured read throughput ~45-51 KB/s
# at 1 MHz -> pick audio formats that fit (see BADGE.md / tools/prepare_card.sh).
SD_SPI_ID = 0
SD_SCK = 2
SD_MOSI = 3
SD_MISO = 4
SD_CS = 5
SD_BAUD_INIT = 400_000     # low speed for card init
# Data phase: 4 MHz verified byte-perfect on this board (512 KB sha256-matched
# host copy at 188.7 KB/s, 2026-07-01) despite the missing MISO pull-up.
# 1 MHz (~45 KB/s) starves 44.1 kHz stereo MP3 playback into constant underrun.
SD_BAUD_DATA = 4_000_000
SD_MOUNT = "/sd"

# ---------------------------------------------------------------------------
# IR  (not used by the player yet; documented for a future real sync channel)
# ---------------------------------------------------------------------------
# TX: IR LED driven active-LOW through a resistor; modulate a 38 kHz carrier.
# RX: TSOP4838 demodulator, output active-LOW (idles high, low = carrier seen).
IR_TX = 9
IR_RX = 27

# ---------------------------------------------------------------------------
# CPU clock
# ---------------------------------------------------------------------------
# MP3 decode of 44.1 kHz stereo measured ~94% of a core at the stock 125 MHz
# (the old "~34%" estimate was wrong) -- with DSP + SD reads on top, playback
# ran at ~0.57x realtime = constant underrun stutter.  250 MHz gives ~2x
# headroom and was verified stable on hardware (2026-07-24: 20.2 s audio in
# 20.1 s wall, worst stall 51 ms vs the 230 ms I2S buffer).  Drop to
# 200_000_000 if a particular chip proves flaky at 250.
CPU_FREQ = 250_000_000

# ---------------------------------------------------------------------------
# Audio / player tunables
# ---------------------------------------------------------------------------
# I2S DMA buffer.  Larger = more tolerance for SD read latency spikes (fewer
# dropouts) but a longer pause/stop latency (the buffered audio plays out before
# it goes quiet).  Doubled from 40 KB when the output moved to 32-bit frames
# (I2S_BITS above), which doubles the on-the-wire byte rate: 80 KB is again
# ~0.23 s of 44.1 kHz stereo, comfortably over the worst measured refill stall
# (51 ms on hardware).
I2S_IBUF = 80_000
# PCM read chunk (bytes).  Multiple of 4 so it divides both mono(2) and stereo(4)
# frame sizes.  ~64 ms of audio per read at 16 kHz mono.
AUDIO_CHUNK = 2048

# ---------------------------------------------------------------------------
# Software volume
# ---------------------------------------------------------------------------
# There is NO hardware volume control anywhere in the chain -- the PT8211 has no
# gain register and the TDA1308's gain is fixed by its feedback resistors.  The
# only thing "volume" can mean here is scaling the PCM samples before they reach
# the DAC, which dsp.pcm16_to_lsbj32() does as (sample * volume) >> 15 while it
# reframes for the DAC.
VOL_UNITY = 32768      # volume value meaning unity gain (0 dBFS, no attenuation)

VOL_STEPS = 8          # number of discrete volume steps the buttons cycle
VOL_STEP_DB = 6        # dB per step (6 dB == one bit == a factor of 2)

# Attenuation of the LOUDEST step, in dB below full scale.  0 == unity.
# (An earlier revision pinned this to 48 dB believing the analog chain clipped
# around -45 dBFS.  That was a misdiagnosis: the analog gain is only ~2.1x and
# is fine -- the real fault was the I2S framing mismatch described above, which
# made every level sound equally blown out.  With I2S_BITS = 32 the chain is
# linear again and normal volumes work.)
#
# Set to 12 dB from listening tests on headphones (2026-07-24): 0 dBFS and
# -6 dBFS were "too loud, uncomfortable, clipping", while -12 dBFS was "about as
# loud as comfortable".  Holding the top step there also moves the whole ladder
# down, which fixes the other complaint -- that even the quietest step was too
# loud.  The range is now -54 dBFS (step 1) .. -12 dBFS (step 8), plus a true
# digital mute at step 0.
VOL_TOP_ATTEN_DB = 12
VOL_DEFAULT_STEP = 3   # -42 dBFS
