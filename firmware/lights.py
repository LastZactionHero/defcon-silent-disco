"""
LED light modes for the badge.

A Lights object owns the SK9822 chain and renders one of several modes each
frame.  The SYNC button cycles the mode.  A transient "volume overlay" is drawn
for a short window whenever the volume changes.

render() is cheap and non-blocking apart from the SK9822 bit-bang flush.
"""

import time
import math
import config as C
# NOTE: sk9822.wheel()/scale() are deliberately NOT used here -- both produce
# mid-range channel values, which is exactly the PWM duty that couples into the
# audio. Intensity comes from per-LED brightness instead.

# mode ids
VU = 0
RAINBOW = 1
PULSE = 2
SOLID = 3
OFF = 4          # fully dark AND electrically quiet -- see render()
N_MODES = 5

# ---------------------------------------------------------------------------
# QUIET PALETTE
# ---------------------------------------------------------------------------
# Every colour here uses only 0 or 255 per channel.  The SK9822 dims a channel
# by chopping it at ~4.7 kHz, and that switching couples into the audio rail --
# it is audible in the headphones, loudest around 50% duty.  Values of 0 and 255
# do not switch at all, so all brightness control is done with the per-LED
# global-brightness field instead, which is an analog current setting.
# Verified 2026-07-24: equal average current, 100% vs 50% duty, and only the
# 50%-duty case is audible.  Do NOT reintroduce mid-range colour values here.
_HUES = ((255, 0, 0),      # red
         (255, 255, 0),    # yellow
         (0, 255, 0),      # green
         (0, 255, 255),    # cyan
         (0, 0, 255),      # blue
         (255, 0, 255))    # magenta

_THEME = (0, 255, 255)   # base color for PULSE/SOLID (a disco cyan)
_AMBER = (255, 255, 0)   # paused indicator (yellow: both channels saturated)
_OFF = (0, 0, 0)


class Lights:
    def __init__(self, leds, brightness=None):
        if brightness is None:
            brightness = C.LED_BRIGHTNESS
        self.leds = leds
        self.n = leds.n
        self.mode = RAINBOW
        self._max_b = max(1, min(31, brightness))
        self.leds.set_brightness(brightness)
        self._t = 0
        self._vol_until = 0      # ticks_ms; while >now, draw volume overlay
        self._vol_frac = 0.0     # 0..1
        self._blanked = False    # True once OFF mode has flushed a dark frame

    # -- control ----------------------------------------------------------
    def next_mode(self):
        self.mode = (self.mode + 1) % N_MODES
        return self.mode

    def show_volume(self, step, steps, ms=900):
        self._vol_frac = 0.0 if steps <= 0 else step / steps
        self._vol_until = time.ticks_add(time.ticks_ms(), ms)

    # -- render -----------------------------------------------------------
    def render(self, level=0, paused=False):
        """level: recent audio peak 0..32767.  Draw one frame and flush."""
        # OFF is a genuine quiet mode, not just black pixels: after one dark
        # frame it stops touching the chain entirely.  Both the LED current
        # draw and the periodic bit-bang burst couple into the audio rail --
        # with music muted you can still HEAR the brightness animation -- so
        # continuing to clock out black frames would not actually silence it.
        # It also drops this task's allocations, which were provoking GC ticks.
        if self.mode == OFF:
            if not self._blanked:
                self.leds.clear()
                self._blanked = True
            return
        self._blanked = False

        now = time.ticks_ms()
        self._t = (self._t + 1) & 0x7FFFFFFF

        if time.ticks_diff(self._vol_until, now) > 0:
            self._draw_volume()
        elif paused:
            self._draw_paused()
        elif self.mode == VU:
            self._draw_vu(level)
        elif self.mode == RAINBOW:
            self._draw_rainbow()
        elif self.mode == PULSE:
            self._draw_pulse()
        else:
            self._draw_solid()
        # Force masked-out LEDs dark.  They are still clocked, so this varies
        # LED current without varying bit-bang traffic (see LED_ACTIVE_MASK).
        mask = C.LED_ACTIVE_MASK
        if mask != (1 << self.n) - 1:
            for i in range(self.n):
                if not (mask >> i) & 1:
                    self.leds.set(i, (0, 0, 0))
        self.leds.write()

    # -- modes ------------------------------------------------------------
    # NOTE: every _draw_* below sets colours from the saturated palette only and
    # expresses intensity through set_pixel_brightness().  See _HUES.
    def _paint(self, i, colour, bright):
        self.leds.set(i, colour)
        self.leds.set_pixel_brightness(i, max(0, min(self._max_b, bright)))

    def _draw_volume(self):
        lit = int(round(self._vol_frac * self.n))
        for i in range(self.n):
            self._paint(i, (0, 0, 255) if i < lit else _OFF,
                        self._max_b if i < lit else 1)

    def _draw_paused(self):
        # slow amber breathing so it's obviously "paused"
        b = (math.sin(self._t / 12.0) + 1.0) * 0.5   # 0..1
        lvl = int(1 + (self._max_b - 1) * b)
        for i in range(self.n):
            self._paint(i, _AMBER, lvl)

    def _draw_vu(self, level):
        # map peak (0..32767) to 0..n lit, green->yellow->red gradient
        frac = min(1.0, level / 26000.0)
        lit = int(round(frac * self.n))
        palette = ((0, 255, 0), (0, 255, 0), (255, 255, 0), (255, 0, 0))
        for i in range(self.n):
            if i < lit:
                self._paint(i, palette[i] if i < len(palette) else (255, 0, 0),
                            self._max_b)
            else:
                self._paint(i, _OFF, 0)

    def _draw_rainbow(self):
        # Hues step discretely (saturated only); the travelling brightness wave
        # is what makes it read as smooth motion, and it is electrically quiet.
        base = self._t // 5
        for i in range(self.n):
            phase = (math.sin((self._t / 7.0) - i) + 1.0) * 0.5
            self._paint(i, _HUES[(base + i) % len(_HUES)],
                        int(1 + (self._max_b - 1) * phase))

    def _draw_pulse(self):
        b = (math.sin(self._t / 8.0) + 1.0) * 0.5     # 0..1
        lvl = int(1 + (self._max_b - 1) * b)
        for i in range(self.n):
            self._paint(i, _THEME, lvl)

    def _draw_solid(self):
        for i in range(self.n):
            self._paint(i, _THEME, self._max_b)
