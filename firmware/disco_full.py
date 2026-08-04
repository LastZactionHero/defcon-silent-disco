"""
Silent disco badge -- V1.

    CHANNEL (GP15)  next track, alphabetical, wraps
    VOL+    (GP14)  louder      VOL- (GP13)  quieter   (both auto-repeat)
    SYNC    (GP12)  jump to 0, stop transmitting, listen for a neighbour's
                    timecode, then jump to it

A track plays through and then repeats itself -- it does NOT advance to the
next one.  Changing channel is always a deliberate button press.

LEDs show a constant colour picked from the track name.  Two deliberate choices
come out of the rev-2 audio noise work:

  * Only fully saturated colours are used (every channel is 0 or 255).  The
    SK9822's per-channel PWM couples into the audio at MID-RANGE duty -- see
    config.py:29-33, where only the 50%-duty case was audible.  0/255 has no
    switching to couple.
  * The chain is written ONLY when something changes, never on a timer.  There
    is no LED task, so during playback there is zero bit-bang traffic on
    GP24/GP25.

Brightness is the SK9822 global field, which is an analog current scale rather
than a duty cycle, so varying it is electrically quiet and gives us more
distinct looks than 7 colours alone.

IR sync assumes CONSTANT BITRATE MP3s: seeking is done by byte offset, which is
only linear in time for CBR.  Keep the card CBR (tools/prepare_card.sh).
"""

import time
import random
import asyncio
import machine
from machine import Pin

import config as C
from sk9822 import SK9822
from buttons import Buttons
from wavplayer import Player, HAVE_MP3
from mp3player import mount_sd, find_tracks
import irsync

# Every channel is 0 or 255 -- nothing in between.  A mid-range channel value
# is the one case config.py:29-33 found audible (~4.7 kHz PWM at ~50% duty), so
# tempting colours like amber (255,90,0) are deliberately NOT here: 90/255 is
# ~35% duty on green, right in the bad band.  Seven colours is the whole set
# available under that constraint.
PALETTE = (
    (255, 0, 0),      # red
    (255, 255, 0),    # yellow
    (0, 255, 0),      # green
    (0, 255, 255),    # cyan
    (0, 0, 255),      # blue
    (255, 0, 255),    # magenta
    (255, 255, 255),  # white
)

# SK9822 global current, 0..31.  This is an ANALOG current scale, not a duty
# cycle, so it is electrically quiet at any value -- which is why the variety
# comes from here rather than from more colours.  7 x 4 = 28 distinct looks.
BRIGHT_STEPS = (5, 10, 16, 24)

# Colour shown while listening for a neighbour.
SYNC_COLOR = (255, 255, 255)
SYNC_BRIGHT = 4

# Broadcast interval.  Randomised so a room full of badges does not settle into
# lockstep and talk over each other every time.
IR_TX_MIN_MS = 7000
IR_TX_MAX_MS = 13000

# How long SYNC listens before giving up and going back to normal.
SYNC_LISTEN_MS = 20000


def name_hash(name):
    """FNV-1a over the track name.

    Plain letter-summing collides badly on real filenames (anagram-ish names
    and shared prefixes land on the same value), and the whole point is that
    two different mixes look different.  FNV-1a is barely more code.
    """
    h = 2166136261
    for ch in name:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    # Avalanche the result before anyone takes it modulo a small number.
    # FNV-1a's LOW bits are weakly mixed -- without this, `h % 7` clustered
    # badly on real filenames (8 of 25 test names landed on one colour).
    h ^= h >> 16
    h = (h * 0x7FEB352D) & 0xFFFFFFFF
    h ^= h >> 15
    h = (h * 0x846CA68B) & 0xFFFFFFFF
    h ^= h >> 16
    return h


def track_look(name):
    """(rgb, brightness) for a track name -- stable across reboots."""
    h = name_hash(name)
    return (PALETTE[h % len(PALETTE)],
            BRIGHT_STEPS[(h >> 13) % len(BRIGHT_STEPS)])


def assign_looks(names):
    """Per-track looks with collisions resolved.

    A raw hash collides more than you would guess: with 28 combinations and
    only SIX tracks the birthday odds of a clash are already ~40%, and two
    channels that look identical defeat the whole point of colouring them.
    On a clash we probe to the next free combination, so a track keeps its
    hashed look unless it actually collides with an earlier one.

    Order matters and is the sorted playlist, so the result is stable for a
    given card.  Adding a track can shift the colour of a later one that had
    been pushed off its first choice -- acceptable, and far better than two
    channels being indistinguishable.
    """
    combos = [(c, b) for c in PALETTE for b in BRIGHT_STEPS]
    n = len(combos)
    used = set()
    out = []
    for nm in names:
        if len(used) >= n:       # more tracks than looks: start reusing
            used.clear()
        i = name_hash(nm) % n
        cand = combos[i]
        for k in range(n):
            cand = combos[(i + k) % n]
            if cand not in used:
                break
        used.add(cand)
        out.append(cand)
    return out


class Disco:
    def __init__(self):
        machine.freq(C.CPU_FREQ)

        self.leds = None
        if getattr(C, "LED_ENABLE", True):
            self.leds = SK9822(C.LED_CLK, C.LED_DAT, C.LED_COUNT)
        else:
            # Park the pins so a disabled chain cannot emit edges all night.
            Pin(C.LED_CLK, Pin.OUT, value=0)
            Pin(C.LED_DAT, Pin.OUT, value=0)

        self.btns = Buttons({
            "channel": C.BTN_PLAY,      # silk says CH; this is the CHANNEL key
            "vol_down": C.BTN_VOL_DN,
            "vol_up": C.BTN_VOL_UP,
            "sync": C.BTN_SYNC,
        })
        self.btns.repeat = {"vol_up", "vol_down"}

        self.player = Player(C.I2S_ID, C.I2S_SCK, C.I2S_WS, C.I2S_SD,
                             C.I2S_IBUF, C.AUDIO_CHUNK)
        self.player.repeat_track = True          # loop the channel, never advance

        self.vol_step = C.VOL_DEFAULT_STEP
        self.player.set_volume_step(self.vol_step, C.VOL_STEPS)

        self.tx = irsync.IrTx()
        self.rx = irsync.IrRx()
        self.listening = False
        self.listen_until = 0
        self._next_tx = time.ticks_add(time.ticks_ms(), IR_TX_MIN_MS)
        self._shown = None                       # what the LEDs currently show
        self.looks = []                          # per-track (rgb, bright)

    # -- tracks ------------------------------------------------------------
    @property
    def track_name(self):
        pl = self.player.playlist
        if not pl:
            return "(no tracks)"
        return pl[self.player.index % len(pl)].rsplit("/", 1)[-1]

    def load_tracks(self):
        try:
            if mount_sd():
                self.player.playlist = find_tracks()
        except Exception as e:
            print("SD mount failed:", e)
        pl = self.player.playlist
        if pl:
            names = [p.rsplit("/", 1)[-1] for p in pl]
            self.looks = assign_looks(names)
            print("%d channel(s):" % len(pl))
            for i, nm in enumerate(names):
                rgb, br = self.looks[i]
                print("  %2d. %-34s rgb%s b%d" % (i + 1, nm[:34], rgb, br))
        else:
            print("no tracks on the card -- buttons still work")
            self.player.status = "no_files"

    # -- LEDs (written only on change) -------------------------------------
    def _paint(self, rgb, bright):
        if self.leds is None or self._shown == (rgb, bright):
            return
        self._shown = (rgb, bright)
        self.leds.set_brightness(bright)
        for i in range(C.LED_COUNT):
            self.leds.set(i, rgb)
        self.leds.write()

    def show_track(self):
        if self.looks:
            rgb, bright = self.looks[self.player.index % len(self.looks)]
        else:
            rgb, bright = track_look(self.track_name)
        self._paint(rgb, bright)

    def show_listening(self):
        self._paint(SYNC_COLOR, SYNC_BRIGHT)

    # -- sync --------------------------------------------------------------
    def _schedule_tx(self):
        self._next_tx = time.ticks_add(
            time.ticks_ms(), random.randint(IR_TX_MIN_MS, IR_TX_MAX_MS))

    def start_sync(self):
        """Reset to 0, go quiet, and listen for a neighbour."""
        self.listening = True
        self.listen_until = time.ticks_add(time.ticks_ms(), SYNC_LISTEN_MS)
        self.tx.idle()
        self.rx.start()          # arm the capture IRQ only while listening
        self.player.seek_ms = 0
        self.player.restart_track()
        self.show_listening()
        print("sync: listening (reset to 0)")

    def _end_sync(self, why):
        self.listening = False
        self.rx.stop()           # disarm: no IRQ load during playback
        self._schedule_tx()
        self.show_track()
        print("sync:", why)

    def apply_sync(self, tc100, track):
        ms = tc100 * 100
        note = ""
        if track != (self.player.index % max(1, len(self.player.playlist))):
            # Different channel: still adopt the timecode, per the V1 spec.
            # Flip this to `return` if same-channel-only turns out to be better
            # in a crowded room.
            note = " (from channel %d -- different from ours)" % (track + 1)
        self.player.seek_ms = ms
        self.player.restart_track()
        self._end_sync("locked to %d.%01d s%s" % (ms // 1000, (ms % 1000) // 100,
                                                  note))

    # -- tasks -------------------------------------------------------------
    async def input_task(self):
        while True:
            for ev in self.btns.poll():
                if ev == "channel":
                    self.player.seek_ms = 0
                    self.player.next_track()
                    if self.listening:
                        self._end_sync("cancelled (channel changed)")
                    # index only moves once the loop picks it up
                    await asyncio.sleep_ms(30)
                    self.show_track()
                    print("channel %d/%d: %s"
                          % (self.player.index + 1, len(self.player.playlist),
                             self.track_name))
                elif ev == "vol_up":
                    self.vol_step = min(C.VOL_STEPS, self.vol_step + 1)
                    self.player.set_volume_step(self.vol_step, C.VOL_STEPS)
                    print("vol %d/%d" % (self.vol_step, C.VOL_STEPS))
                elif ev == "vol_down":
                    self.vol_step = max(0, self.vol_step - 1)
                    self.player.set_volume_step(self.vol_step, C.VOL_STEPS)
                    print("vol %d/%d" % (self.vol_step, C.VOL_STEPS))
                elif ev == "sync":
                    if not self.listening:
                        self.start_sync()
            await asyncio.sleep_ms(20)

    async def ir_task(self):
        while True:
            if self.listening:
                got = self.rx.poll()
                if got:
                    self.apply_sync(got[0], got[1])
                elif time.ticks_diff(time.ticks_ms(), self.listen_until) >= 0:
                    self._end_sync("timed out, nothing heard")
                await asyncio.sleep_ms(20)
            else:
                if (self.player.playlist and
                        time.ticks_diff(time.ticks_ms(), self._next_tx) >= 0):
                    idx = self.player.index % len(self.player.playlist)
                    # Blocks ~35-60 ms; the I2S buffer covers it.
                    self.tx.send(self.player.pos_ms // 100, idx)
                    self._schedule_tx()
                await asyncio.sleep_ms(50)

    async def main(self):
        print("audio:", "MP3 + WAV" if HAVE_MP3 else "WAV only (no mp3 module)")
        self.load_tracks()
        self.show_track()
        print("CHANNEL=next  VOL+/-  SYNC=listen for a neighbour")
        try:
            await asyncio.gather(
                self.player.run(),
                self.input_task(),
                self.ir_task(),
            )
        finally:
            self.player.deinit()
            self.tx.deinit()
            self.rx.stop()
            if self.leds is not None:
                try:
                    self.leds.clear()
                except Exception:
                    pass


def _autostart_blocked():
    """Hold CHANNEL at boot to skip autostart and reach the REPL."""
    hold = Pin(C.BTN_PLAY, Pin.IN, Pin.PULL_UP)
    time.sleep_ms(20)
    return hold.value() == 0


def run():
    if _autostart_blocked():
        print("autostart skipped (CHANNEL held) -- REPL. "
              "Run: import disco, asyncio; asyncio.run(disco.Disco().main())")
        return
    asyncio.run(Disco().main())
