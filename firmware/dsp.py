"""
Audio DSP hot path (viper).  Operates on 16-bit signed PCM in place.

Verified against MicroPython v1.28 native emitter behaviour:
- ptr16 subscript is a zero-extended (unsigned) 16-bit load, but is tagged as a
  SIGNED machine int, so we sign-extend manually and all compares/shifts are
  signed.  NEVER cast anything here to uint() -- that would flip `>> 8` to a
  logical shift and corrupt negative samples.
- (s * vol) >> 15 with s in [-32768,32767] and vol in [0,32768] peaks at 2^30,
  well inside signed 32-bit, so no overflow and no clamping needed.

The scale is 15-bit (not 8-bit) because the badge has to run VERY quiet: the
rev-2 analog chain clips around -45 dBFS, so useful volumes live near vol=128
(-48 dBFS) and below.  An 8-bit scale bottoms out at 1/256 in a single step and
cannot express that range.  See BADGE.md.
"""

import micropython


@micropython.viper
def apply_vol(buf: ptr16, n: int, vol: int):
    """Scale n signed-int16 samples in `buf` in place by vol/32768 (vol 0..32768)."""
    for i in range(n):
        s = int(buf[i])
        if s >= 32768:
            s -= 65536
        s = (s * vol) >> 15
        buf[i] = s & 0xFFFF


@micropython.viper
def pcm16_to_lsbj32(src: ptr16, dst: ptr32, n: int, vol: int) -> int:
    """Scale n int16 samples by vol/32768, reframe for the TM8211, return peak.

    The DAC wants LSB-justified framing, but MicroPython's I2S only speaks
    standard (Philips) I2S, which delays data by one BCK.  Feeding it 16-bit
    frames put the PREVIOUS sample's LSB into the DAC's sign bit -- see BADGE.md.

    The fix is to send 32-bit frames with the sample sitting in bits 16..1.  The
    one-BCK delay then lines our 16 bits up exactly with the final 16 bits of
    the frame, which is the window an LSBJ DAC latches.

    The VU peak is computed in this same pass and returned: a separate peak()
    call over the same samples measured 770 us per frame on hardware, which is
    real money against a 26 ms realtime budget.
    """
    p = 0
    for i in range(n):
        s = int(src[i])
        if s >= 32768:
            s -= 65536
        s = (s * vol) >> 15
        dst[i] = (s & 0xFFFF) << 1
        if s < 0:
            s = -s
        if s > p:
            p = s
    return p


@micropython.viper
def peak(buf: ptr16, n: int) -> int:
    """Return the maximum absolute sample (0..32768) over n int16 samples."""
    p = 0
    for i in range(n):
        s = int(buf[i])
        if s >= 32768:
            s -= 65536
        if s < 0:
            s = -s
        if s > p:
            p = s
    return p
