"""
Interactive audio diagnostic lab -- driven entirely by the badge's buttons.

Built during rev-2 bring-up to chase a loud broadband "static" that sits on top
of the music.  Runs standalone (USB power is enough, no laptop needed) so the
listener can move through tests at their own pace.

    SYNC  (GP12)  next mode
    CH    (GP15)  start / stop output
    VOL+  (GP14)  level up    (6 dB per step, auto-repeats)
    VOL-  (GP13)  level down  (6 dB per step, auto-repeats)

LEDs: all four show the current MODE COLOR.  Their brightness pattern spells the
LEVEL in binary with LED1 as the least-significant bit (bright = 1, dim = 0), so
level 0 is all-dim and level 15 is all-bright.  The whole chain is dim when
stopped and bright when running.

Modes (in cycle order):
    TONE    red     441 Hz sine at the selected level
    SWEEP   yellow  441 Hz sine ramping 1 -> 32767 over 20 s, repeating
                    (ignores the level; tests whether loudness tracks amplitude)
    MUSIC   green   MP3 streamed from the SD card, scaled to the selected level
    ZEROS   blue    I2S running, all-zero samples -- noise floor WITH clocks
    CLKOFF  white   I2S torn down, BCK/WS/DIN driven low -- noise floor with NO
                    clocks.  ZEROS vs CLKOFF is the key comparison: if both are
                    equally noisy the noise is not coming from the I2S side.

Safety: boots stopped, at level 0 (amplitude 1 == -90 dBFS), so nothing plays
until CH is pressed.

Restore the normal player with:  mpremote connect PORT fs cp main.py :
"""

import time
import math
import gc
from machine import Pin, SPI, I2S

import config as C
from sk9822 import SK9822, scale
from buttons import Buttons
from dsp import pcm16_to_lsbj32

try:
    import mp3
except ImportError:
    mp3 = None

# -- modes -------------------------------------------------------------------
TONE, SWEEP, MUSIC, ZEROS, CLKOFF = range(5)
MODE_NAMES = ("TONE", "SWEEP", "MUSIC", "ZEROS", "CLKOFF")
MODE_COLORS = (
    (255, 0, 0),      # TONE    red
    (255, 170, 0),    # SWEEP   yellow
    (0, 255, 0),      # MUSIC   green
    (0, 80, 255),     # ZEROS   blue
    (255, 255, 255),  # CLKOFF  white
)
N_MODES = 5

MAX_LEVEL = 15
SWEEP_SECS = 20.0

# A smaller I2S buffer than the player uses: ~90 ms, so start/stop feels prompt.
# (32-bit frames double the wire rate, hence 32000 rather than 16000.)
IBUF = 32000

TONE_PERIODS = 5           # 441 Hz periods per write (5 * 100 frames = 2000 B)
TONE_FRAMES = TONE_PERIODS * 100


def level_to_amp(level):
    """Level 0..15 -> peak amplitude 1..32767, 6 dB per step."""
    return min(32767, 1 << level)


class Mp3Stream:
    """Minimal looping MP3 reader: next() returns one decoded frame."""

    def __init__(self, path):
        self.path = path
        self.dec = None
        self.f = None
        self.IN = bytearray(8192)
        self.mv = memoryview(self.IN)
        self.OUT = bytearray(mp3.MAX_FRAME_BYTES)
        self.mvOUT = memoryview(self.OUT)
        self._open()

    def _open(self):
        self.close()
        self.f = open(self.path, "rb")
        head = self.f.read(10)
        if len(head) == 10 and head[0:3] == b"ID3":
            sz = ((head[6] & 0x7F) << 21) | ((head[7] & 0x7F) << 14) | \
                 ((head[8] & 0x7F) << 7) | (head[9] & 0x7F)
            self.f.seek(10 + sz)
        else:
            self.f.seek(0)
        self.dec = mp3.Decoder()
        self.pos = 0
        self.have = 0
        self.eof = False

    def next(self):
        """-> (memoryview_pcm, nbytes, rate, channels); loops at end of file."""
        cap = len(self.IN)
        for _ in range(64):                      # bounded: never spin forever
            avail = self.have - self.pos
            if avail < 2048 and not self.eof:
                if self.have > cap - 512 and self.pos > 0:
                    self.IN[0:avail] = self.IN[self.pos:self.have]
                    self.pos = 0
                    self.have = avail
                n = self.f.readinto(self.mv[self.have:])
                if n:
                    self.have += n
                else:
                    self.eof = True
                avail = self.have - self.pos
            if avail <= 0 and self.eof:
                self._open()                     # loop the track
                continue
            consumed, produced, rate, ch = self.dec.decode(
                self.mv[self.pos:self.have], self.OUT)
            self.pos += consumed
            if produced > 0:
                return self.mvOUT, produced, rate, ch
            if consumed == 0:
                if self.eof:
                    self._open()
                    continue
                if self.pos == 0 and self.have == cap:
                    self._open()                 # undecodable: start over
                    continue
        return None, 0, 0, 0

    def close(self):
        if self.dec is not None:
            try:
                self.dec.deinit()
            except Exception:
                pass
            self.dec = None
        if self.f is not None:
            try:
                self.f.close()
            except Exception:
                pass
            self.f = None


class Lab:
    def __init__(self):
        self.leds = SK9822(C.LED_CLK, C.LED_DAT, C.LED_COUNT)
        self.btns = Buttons({
            "sync": C.BTN_SYNC,
            "vol_down": C.BTN_VOL_DN,
            "vol_up": C.BTN_VOL_UP,
            "play_pause": C.BTN_PLAY,
        })
        self.btns.repeat = {"vol_up", "vol_down"}

        self.mode = TONE
        self.level = 0
        self.playing = False

        self.audio = None
        self.stream = None
        self.sweep_t0 = None
        self._clk_pins = None

        # All output is LSBJ-reframed to 32-bit words -> 4 bytes per sample,
        # i.e. 8 bytes per stereo frame.  See dsp.pcm16_to_lsbj32 / BADGE.md.
        self.tone = bytearray(TONE_FRAMES * 8)
        self.tone_amp = None
        self.zeros = bytearray(4000)
        self.scratch = bytearray(mp3.MAX_FRAME_BYTES * 2) if mp3 else None
        self.sweep_step = 0

        self.have_music = False
        self.track = None
        self._mount_sd()
        self._apply_mode()

    # -- setup ---------------------------------------------------------------
    def _mount_sd(self):
        if mp3 is None:
            return
        import os
        import sdcard
        try:
            try:
                os.umount(C.SD_MOUNT)
            except Exception:
                pass
            spi = SPI(C.SD_SPI_ID, baudrate=C.SD_BAUD_INIT, polarity=0, phase=0,
                      sck=Pin(C.SD_SCK), mosi=Pin(C.SD_MOSI), miso=Pin(C.SD_MISO))
            cs = Pin(C.SD_CS, Pin.OUT, value=1)
            for _ in range(3):
                cs.value(0)
                for _ in range(600):
                    spi.write(b"\xff")
                cs.value(1)
                for _ in range(32):
                    spi.write(b"\xff")
                time.sleep_ms(20)
            card = sdcard.SDCard(spi, cs, baudrate=C.SD_BAUD_DATA)
            os.mount(os.VfsFat(card), C.SD_MOUNT)
            names = sorted(f for f in os.listdir(C.SD_MOUNT)
                           if f.lower().endswith(".mp3") and not f.startswith("."))
            if names:
                self.track = C.SD_MOUNT + "/" + names[0]
                self.have_music = True
                print("music:", self.track)
        except Exception as e:
            print("no SD/music:", e)

    # -- audio plumbing ------------------------------------------------------
    def _i2s_up(self):
        if self.audio is not None:
            return
        self._clk_pins = None
        self.audio = I2S(C.I2S_ID, sck=Pin(C.I2S_SCK), ws=Pin(C.I2S_WS),
                         sd=Pin(C.I2S_SD), mode=I2S.TX, bits=C.I2S_BITS,
                         format=I2S.STEREO, rate=44100, ibuf=IBUF)

    def _i2s_down(self):
        if self.audio is not None:
            try:
                self.audio.deinit()
            except Exception:
                pass
            self.audio = None

    def _clocks_low(self):
        """Tear down I2S and hold all three audio pins at 0."""
        self._i2s_down()
        self._clk_pins = [Pin(C.I2S_SCK, Pin.OUT, value=0),
                          Pin(C.I2S_WS, Pin.OUT, value=0),
                          Pin(C.I2S_SD, Pin.OUT, value=0)]

    def _apply_mode(self):
        if self.stream is not None:
            self.stream.close()
            self.stream = None
        gc.collect()
        if self.mode == CLKOFF:
            self._clocks_low()
        else:
            self._i2s_up()
        if self.mode == MUSIC and self.have_music:
            try:
                self.stream = Mp3Stream(self.track)
            except Exception as e:
                print("music open failed:", e)
                self.stream = None
        if self.mode == SWEEP:
            self.sweep_t0 = time.ticks_ms()
        self.tone_amp = None       # force a rebuild

    # -- signal generation ---------------------------------------------------
    def _fill_tone(self, amp):
        """Build one LSBJ-reframed 441 Hz period and tile it across the buffer."""
        if amp == self.tone_amp:
            return
        self.tone_amp = amp
        b = self.tone
        for i in range(100):
            s = int(amp * math.sin(2 * math.pi * i / 100))
            w = (s & 0xFFFF) << 1          # sample into bits 16..1
            b0 = w & 0xFF
            b1 = (w >> 8) & 0xFF
            b2 = (w >> 16) & 0xFF
            for p in range(TONE_PERIODS):
                j = ((p * 100) + i) * 8
                b[j] = b0                   # left channel, little-endian u32
                b[j + 1] = b1
                b[j + 2] = b2
                b[j + 3] = 0
                b[j + 4] = b0               # right channel
                b[j + 5] = b1
                b[j + 6] = b2
                b[j + 7] = 0

    def _sweep_amp(self):
        el = time.ticks_diff(time.ticks_ms(), self.sweep_t0) / 1000.0
        if el >= SWEEP_SECS:
            self.sweep_t0 = time.ticks_ms()
            el = 0.0
        self.sweep_step = int(el / SWEEP_SECS * 15.0)
        return max(1, min(32767, 1 << self.sweep_step))

    # -- one slice of output -------------------------------------------------
    def _pump(self):
        if self.mode == CLKOFF or self.audio is None:
            time.sleep_ms(20)
            return
        if self.mode == ZEROS:
            self.audio.write(self.zeros)
        elif self.mode == TONE:
            self._fill_tone(level_to_amp(self.level))
            self.audio.write(self.tone)
        elif self.mode == SWEEP:
            self._fill_tone(self._sweep_amp())
            self.audio.write(self.tone)
        elif self.mode == MUSIC:
            if self.stream is None:
                time.sleep_ms(20)
                return
            pcm, n, rate, ch = self.stream.next()
            if n <= 0:
                time.sleep_ms(5)
                return
            # Music is mastered near full scale, so scaling by amp/32768 puts
            # its peak at roughly the same amplitude the TONE mode would use.
            vol = level_to_amp(self.level)
            nsamp = n >> 1
            pcm16_to_lsbj32(pcm, self.scratch, nsamp, vol)
            self.audio.write(memoryview(self.scratch)[:nsamp << 2])

    # -- LEDs ----------------------------------------------------------------
    def _render(self):
        col = MODE_COLORS[self.mode]
        dim = scale(col, 10)
        # SWEEP drives its own amplitude, so show the live ramp position there
        # rather than the (unused) level -- the LEDs visibly count up.
        shown = self.sweep_step if (self.mode == SWEEP and self.playing) else self.level
        for i in range(C.LED_COUNT):
            self.leds.set(i, col if (shown >> i) & 1 else dim)
        # Kept low: LED current couples into the audio rail (BADGE.md quirk 7).
        self.leds.set_brightness(C.LED_BRIGHTNESS if self.playing
                                 else max(1, C.LED_BRIGHTNESS // 3))
        self.leds.write()

    def _announce(self):
        print("mode %-6s level %2d (amp %5d)  %s"
              % (MODE_NAMES[self.mode], self.level,
                 level_to_amp(self.level), "RUNNING" if self.playing else "stopped"))

    # -- main loop -----------------------------------------------------------
    def run(self):
        print("audio lab ready -- SYNC=mode  CH=start/stop  VOL+/-=level")
        self._announce()
        self._render()
        next_render = time.ticks_add(time.ticks_ms(), 120)
        while True:
            for ev in self.btns.poll():
                if ev == "sync":
                    self.mode = (self.mode + 1) % N_MODES
                    self._apply_mode()
                    self._announce()
                elif ev == "play_pause":
                    self.playing = not self.playing
                    if self.mode == SWEEP and self.playing:
                        self.sweep_t0 = time.ticks_ms()
                    self._announce()
                elif ev == "vol_up":
                    if self.level < MAX_LEVEL:
                        self.level += 1
                        self._announce()
                elif ev == "vol_down":
                    if self.level > 0:
                        self.level -= 1
                        self._announce()

            if self.playing:
                self._pump()
            else:
                time.sleep_ms(20)

            now = time.ticks_ms()
            if time.ticks_diff(now, next_render) >= 0:
                self._render()
                next_render = time.ticks_add(now, 120)


def run():
    import machine
    machine.freq(C.CPU_FREQ)
    lab = Lab()
    try:
        lab.run()
    finally:
        lab._i2s_down()
        try:
            lab.leds.clear()
        except Exception:
            pass
