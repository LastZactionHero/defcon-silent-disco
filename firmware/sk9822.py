"""
SK9822 (APA102 clone) addressable-LED driver -- bit-banged.

The badge's LED clock/data pins (GP24/GP25) are not on a hardware SPI block,
so we bit-bang.  This is fast enough for the 4-LED chain at ~30 fps and the
brief (~1 ms) blocking write does not disturb I2S DMA playback.

Protocol (per SK9822/APA102):
  start frame : 32 bits of 0
  per LED     : 0b111 + 5-bit global brightness, then Blue, Green, Red bytes
  end frame   : >= n/2 clocks; we send 64 bits of 0 (SK9822 wants zeros)
"""

import micropython
from machine import Pin


@micropython.viper
def _blast(buf: ptr8, n: int, clk_mask: int, dat_mask: int, dly: int):
    """Shift n bytes out MSB-first by banging the RP2040 SIO registers.

    Doing this a bit at a time through Pin.value() cost 3848 us per 28-byte
    frame -- 12.8% of the CPU at a 30 ms refresh, which was starving the audio
    refill and causing audible stutter.  Writing GPIO_OUT_SET/CLR directly
    (0xd0000014 / 0xd0000018) is ~40x faster.  `dly` pads each clock phase if a
    chain ever needs slowing down; 0 is fine for the badge's four LEDs.
    """
    SET = ptr32(0xd0000014)
    CLR = ptr32(0xd0000018)
    for i in range(n):
        b = int(buf[i])
        j = 7
        while j >= 0:
            if (b >> j) & 1:
                SET[0] = dat_mask
            else:
                CLR[0] = dat_mask
            for _ in range(dly):
                pass
            SET[0] = clk_mask
            for _ in range(dly):
                pass
            CLR[0] = clk_mask
            j -= 1


class SK9822:
    def __init__(self, clk_pin, dat_pin, n, brightness=8):
        self._clk = Pin(clk_pin, Pin.OUT, value=0)
        self._dat = Pin(dat_pin, Pin.OUT, value=0)
        self._clk_mask = 1 << clk_pin
        self._dat_mask = 1 << dat_pin
        self.delay = 0
        self.n = n
        self._bright = max(0, min(31, brightness))
        # frame buffer of (r, g, b) tuples
        self.buf = [(0, 0, 0)] * n
        # PER-LED 5-bit brightness.  On the SK9822 this field is an analog
        # constant-current setting, not a duty cycle (unlike the APA102, which
        # PWMs it at ~580 Hz).  Dimming here is therefore electrically quiet,
        # whereas dimming via mid-range colour values chops current at ~4.7 kHz
        # and is audible in the headphones -- see BADGE.md quirk 7.
        self.bright = [self._bright] * n
        # wire format: 4 start bytes + 4 per LED + 8 end bytes, built in place
        self._frame = bytearray(4 + 4 * n + 8)

    # -- low level ---------------------------------------------------------
    def write(self):
        """Flush the frame buffer to the LED chain."""
        f = self._frame
        bright = self.bright
        p = 4                      # leave the 4 start bytes at zero
        i = 0
        for (r, g, b) in self.buf:
            f[p] = 0xE0 | (bright[i] & 0x1F)
            f[p + 1] = b           # SK9822 order: Blue, Green, Red
            f[p + 2] = g
            f[p + 3] = r
            p += 4
            i += 1
        # trailing 8 bytes stay zero: the end frame
        _blast(f, len(f), self._clk_mask, self._dat_mask, self.delay)

    # -- convenience -------------------------------------------------------
    def set(self, i, rgb):
        if 0 <= i < self.n:
            self.buf[i] = rgb

    def fill(self, rgb):
        for i in range(self.n):
            self.buf[i] = rgb

    def set_brightness(self, b):
        """Set every LED's brightness (analog current scale, 0..31)."""
        self._bright = max(0, min(31, b))
        for i in range(self.n):
            self.bright[i] = self._bright

    def set_pixel_brightness(self, i, b):
        """Set ONE LED's brightness -- the quiet way to fade a single pixel."""
        if 0 <= i < self.n:
            self.bright[i] = max(0, min(31, b))

    @property
    def brightness(self):
        return self._bright

    def show(self, pixels=None, brightness=None):
        """Set all pixels (optional) and flush in one call."""
        if brightness is not None:
            self.set_brightness(brightness)
        if pixels is not None:
            for i in range(self.n):
                self.buf[i] = pixels[i] if i < len(pixels) else (0, 0, 0)
        self.write()

    def clear(self):
        self.fill((0, 0, 0))
        self.write()


# -------------------------------------------------------------------------
# Small color helpers (used by lights.py)
# -------------------------------------------------------------------------
def wheel(pos):
    """0..255 -> (r,g,b) around the color wheel."""
    pos &= 255
    if pos < 85:
        return (255 - pos * 3, pos * 3, 0)
    if pos < 170:
        pos -= 85
        return (0, 255 - pos * 3, pos * 3)
    pos -= 170
    return (pos * 3, 0, 255 - pos * 3)


def scale(rgb, num, den=255):
    """Scale a color's intensity by num/den (integer)."""
    r, g, b = rgb
    return (r * num // den, g * num // den, b * num // den)
