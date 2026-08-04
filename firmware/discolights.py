"""
Light show for the MP3 player.  Audio-reactive, and it drives itself -- there is
no spare button to cycle modes, so it rotates through animations on its own.

⚠️ QUIET PALETTE RULE: every colour here uses only 0 or 255 per channel, and all
intensity comes from the SK9822's per-LED brightness field.  The chip dims a
colour channel by chopping it at ~4.7 kHz and that switching is audible in the
headphones; the brightness field is an analog current setting and is silent.
Never introduce a mid-range channel value (no wheel(), no scale()).
See BADGE.md quirk 7.
"""

import time
import math

import config as C

# saturated hues only -- see the module docstring before adding to this
RED = (255, 0, 0)
YELLOW = (255, 255, 0)
GREEN = (0, 255, 0)
CYAN = (0, 255, 255)
BLUE = (0, 0, 255)
MAGENTA = (255, 0, 255)
WHITE = (255, 255, 255)
OFF = (0, 0, 0)

HUES = (RED, YELLOW, GREEN, CYAN, BLUE, MAGENTA)
VU_COLORS = (GREEN, GREEN, YELLOW, RED)

# animations, rotated automatically while playing
VU, COMET, TWINKLE, WAVE, N_ANIM = 0, 1, 2, 3, 4
ANIM_SECS = 18          # how long each animation gets before rotating


class DiscoLights:
    def __init__(self, leds, brightness=None):
        self.leds = leds
        self.n = leds.n
        self.max_b = max(1, min(31, C.LED_BRIGHTNESS if brightness is None
                                else brightness))
        self._t = 0
        self._anim = VU
        self._anim_until = time.ticks_add(time.ticks_ms(), ANIM_SECS * 1000)
        self._overlay_until = 0
        self._overlay = None      # ('vol', frac) | ('track', direction)
        self._rng = 0x2545F491
        self._peak = 0            # decaying level, so the VU falls smoothly
        leds.set_brightness(self.max_b)

    # -- helpers -----------------------------------------------------------
    def _rand(self):
        """xorshift32 -- MicroPython's random isn't guaranteed on every port."""
        x = self._rng
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        self._rng = x & 0xFFFFFFFF
        return self._rng

    def _paint(self, i, colour, bright):
        self.leds.set(i, colour)
        self.leds.set_pixel_brightness(i, max(0, min(self.max_b, int(bright))))

    # -- transient overlays ------------------------------------------------
    def show_volume(self, step, steps, ms=900):
        self._overlay = ('vol', 0.0 if steps <= 0 else step / steps)
        self._overlay_until = time.ticks_add(time.ticks_ms(), ms)

    def show_track_change(self, direction, ms=500):
        """direction: +1 next, -1 previous -- a quick wipe that way."""
        self._overlay = ('track', direction)
        self._overlay_until = time.ticks_add(time.ticks_ms(), ms)

    # -- main --------------------------------------------------------------
    def render(self, level=0, paused=False):
        now = time.ticks_ms()
        self._t += 1

        # peak decays so the meter falls rather than snapping to zero
        if level > self._peak:
            self._peak = level
        else:
            self._peak -= (self._peak - level) >> 2

        if time.ticks_diff(self._overlay_until, now) > 0:
            kind, val = self._overlay
            if kind == 'vol':
                self._draw_volume(val)
            else:
                self._draw_track(val)
        elif paused:
            self._draw_paused()
        else:
            if time.ticks_diff(now, self._anim_until) >= 0:
                self._anim = (self._anim + 1) % N_ANIM
                self._anim_until = time.ticks_add(now, ANIM_SECS * 1000)
            if self._anim == VU:
                self._draw_vu()
            elif self._anim == COMET:
                self._draw_comet()
            elif self._anim == TWINKLE:
                self._draw_twinkle()
            else:
                self._draw_wave()
        self.leds.write()

    # -- animations --------------------------------------------------------
    def _draw_vu(self):
        frac = self._peak / 26000.0
        if frac > 1.0:
            frac = 1.0
        lit = int(frac * self.n + 0.5)
        for i in range(self.n):
            if i < lit:
                self._paint(i, VU_COLORS[i] if i < len(VU_COLORS) else RED,
                            self.max_b)
            else:
                self._paint(i, OFF, 0)

    def _draw_comet(self):
        head = (self._t // 3) % self.n
        hue = HUES[(self._t // (3 * self.n)) % len(HUES)]
        for i in range(self.n):
            dist = (head - i) % self.n
            self._paint(i, hue, self.max_b >> dist)

    def _draw_twinkle(self):
        # louder audio -> more frequent sparks
        thresh = 40 + (self._peak >> 9)
        for i in range(self.n):
            b = self.leds.bright[i]
            if (self._rand() & 0xFF) < thresh:
                self._paint(i, HUES[self._rand() % len(HUES)], self.max_b)
            elif b > 0:
                self._paint(i, self.leds.buf[i], b - 1)   # fade the spark out

    def _draw_wave(self):
        base = self._t // 5
        boost = self._peak / 32768.0
        for i in range(self.n):
            phase = (math.sin((self._t / 7.0) - i) + 1.0) * 0.5
            lvl = 1 + (self.max_b - 1) * (0.35 + 0.65 * boost) * phase
            self._paint(i, HUES[(base + i) % len(HUES)], lvl)

    # -- states / overlays -------------------------------------------------
    def _draw_paused(self):
        b = (math.sin(self._t / 12.0) + 1.0) * 0.5
        lvl = 1 + (self.max_b - 1) * b
        for i in range(self.n):
            self._paint(i, YELLOW, lvl)

    def _draw_volume(self, frac):
        lit = int(frac * self.n + 0.5)
        for i in range(self.n):
            self._paint(i, BLUE if i < lit else OFF,
                        self.max_b if i < lit else 0)

    def _draw_track(self, direction):
        step = (self._t // 2) % self.n
        head = step if direction > 0 else (self.n - 1 - step)
        for i in range(self.n):
            self._paint(i, WHITE if i == head else CYAN,
                        self.max_b if i == head else 1)
