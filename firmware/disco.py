"""
Silent disco badge -- step 9: + IR receive and SYNC.

    boot     -> mount SD -> play the first track alphabetically, on a loop
    CHANNEL  (GP15)  tap = next track (wraps);  hold 10 s = hard reset
    SYNC     (GP12)  join a neighbour: playback pauses, the badge listens for
                     their broadcast, then adopts BOTH their channel and their
                     position.  Times out back to where you were.
    VOL+/-   (GP14/GP13)  louder / quieter, auto-repeat when held

A track that reaches its end REPLAYS ITSELF -- it never advances on its own.

LEDs
----
Each track name picks a THEME (four colours) and, from a DIFFERENT slice of the
same hash, an ANIMATION.  The two are independent, so a card gives you a mix of
colour/motion pairings rather than 12 fixed looks.

Two hard rules, both from the rev-2 audio noise work:

  * Every channel value is always 0 or 255.  Mid-range values are the one case
    config.py:29-33 found audible (~4.7 kHz PWM near 50% duty).  This is why
    NO animation crossfades between colours -- a fade would walk every channel
    straight through the bad range.  Motion comes from WHICH led shows WHICH
    colour instead.
  * Brightness animation uses the SK9822 global current field, which is an
    analog current scale rather than a duty cycle, so ramping it is quiet.
    That is the only "fade" available to us, and it is free.

Static themes still cost nothing: the chain is only written when the output
actually changes, so a STATIC animation produces zero bit-bang traffic after
the first frame, exactly as in step 4.

IR
--
Every 7-13 s (randomised) the badge broadcasts (timecode, channel) so a neighbour
can sync to it.  TRANSMIT ONLY at this step -- the receiver is not armed at
all, which keeps the two halves separable: an earlier build wedged the badge
because the transmitter left its PWM parked at ~38 kHz between sends, which the
TSOP4838 centimetres away read as a permanent carrier and turned into an
interrupt storm.  irsync.IrTx now builds the PWM per send and tears it down
afterwards, leaving the pin a plain GPIO high (the LED is active low).

A send blocks for ~35-60 ms.  The I2S buffer holds ~230 ms at the default
I2S_IBUF, so it should pass unheard -- if you hear a tick every 10 s, that is
the first thing to look at.

Next step: arm the receiver and implement SYNC (see disco_full.py).
"""

import time
import math
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

VOLUME_STEP = 4

# Animations advance on a fixed TIME GRID locked to the playback position:
# everything steps at multiples of SLOT_MS of *track time*, so two badges
# synced to the same position flash at the same moments -- the step boundary
# is a property of the track clock, not of whoever's scheduler woke up first.
# The loop polls every LED_POLL_MS (cheap: the chain is only written when the
# output actually changes), so an edge lands within one poll of its true spot.
SLOT_MS = 160
LED_POLL_MS = 25

# Broadcast interval, randomised per send.  With a room full of badges a fixed
# period drifts everyone into lockstep and every broadcast collides; jitter
# keeps collisions transient.  Mean ~10 s, so a listener's 25 s window still
# spans 2-3 broadcasts.
IR_TX_MIN_MS = 7_000
IR_TX_MAX_MS = 13_000

# Hold CHANNEL this long for a hard reset.  This is the field escape hatch: if
# a badge locks up mid-set nobody has a laptop, and the only other way back in
# is physical BOOTSEL.  Long enough that nobody triggers it by accident.
RESET_HOLD_MS = 10_000

# How long SYNC listens before giving up.  Must comfortably exceed the
# longest broadcast gap (IR_TX_MAX_MS) or we can time out between broadcasts.
SYNC_LISTEN_MS = 25_000

# TEST HOOK: if non-zero, start a sync automatically this often, so the link
# can be exercised over USB without a finger on the button.  Set to 0 for
# normal operation -- this is a debugging aid, not a feature.
AUTO_SYNC_MS = 0

# Sender-side latency baked into every received timecode: pos_ms is sampled
# before the ~68 ms blocking send, and the receiver only decodes ~7-27 ms after
# the last edge (quiet wait + poll cadence).  Receiver-side latency after the
# decode is measured live via Player.seek_ref, so only this fixed part needs a
# constant.
# 85 ms of that is the send itself; the rest is measured residual: with 85
# alone, a two-badge capture showed the receiver locking a consistent ~125 ms
# behind (file open + seek-probe SD reads happen after the compensation clock
# stops).  210 centres the offset near zero; remaining wobble is ~+/-70 ms,
# which is inaudible across separate headphones and under 2 LED frames.
IR_SEND_LATENCY_MS = 210

# Playlist index to start on at boot.  0 for shipping; useful in testing to
# make two badges boot on different channels (e.g. to exercise channel-adopt).
START_CHANNEL = 0

BLACK = (0, 0, 0)
R = (255, 0, 0)
Y = (255, 255, 0)
G = (0, 255, 0)
Cy = (0, 255, 255)
B = (0, 0, 255)
M = (255, 0, 255)
W = (255, 255, 255)

# Themes: four colours across LED1..LED4.
#   1-6   analogous sweeps -- a four-wide window slid around the hue wheel
#   7-9   white-accented pairs -- legible at distance, looks deliberate
#   10-12 complementary alternation -- highest contrast
THEMES = (
    (R, Y, G, Cy),      # sunrise
    (Y, G, Cy, B),      # meadow
    (G, Cy, B, M),      # lagoon
    (Cy, B, M, R),      # twilight
    (B, M, R, Y),       # ember
    (M, R, Y, G),       # bloom
    (R, W, M, W),       # neon rose
    (B, W, Cy, W),      # glacier
    (G, W, Y, W),       # citrus
    (R, Cy, R, Cy),     # flame/ice
    (G, M, G, M),       # clover
    (B, Y, B, Y),       # voltage
)
THEME_NAMES = ("sunrise", "meadow", "lagoon", "twilight", "ember", "bloom",
               "neon rose", "glacier", "citrus", "flame/ice", "clover", "voltage")

BRIGHT_STEPS = (5, 10, 16, 24)

# --- error codes ------------------------------------------------------------
# Shown as RED BINARY across the four LEDs, LED1 = least significant bit, so a
# badge can report a fault with nobody holding a laptop.  The pattern holds,
# then blanks briefly, so repeats are countable and it never reads as "normal".
# Four LEDs gives codes 1..15; 0 means no error.
ERR_NO_CARD = 1      # 0001  SD did not initialise
ERR_NO_TRACKS = 2    # 0010  card mounted, but nothing playable on it
ERR_SD_EXC = 3       # 0011  mount raised an exception
ERR_PLAYBACK = 4     # 0100  playback failed repeatedly
ERR_NAMES = {
    ERR_NO_CARD: "no SD card",
    ERR_NO_TRACKS: "no playable tracks on card",
    ERR_SD_EXC: "SD mount raised",
    ERR_PLAYBACK: "playback failing",
}
ERR_COLOR = R
ERR_BRIGHT = 12
# Pattern lit 1.2 s, blank 0.4 s -- countable, and never mistakable for a theme.
ERR_ON_MS = 1200
ERR_CYCLE_MS = 1600


def _tri(x, period):
    """Triangle wave: 0 .. period/2 .. 0.  Integer, no float, no allocation."""
    h = period >> 1
    p = x % period
    return p if p < h else period - p


# --- animations -------------------------------------------------------------
# Signature: fn(slot, theme, out, n, base_b) -> brightness
# `slot` is track-time // SLOT_MS, so every step below is an absolute position
# in the track: synced badges compute identical output at identical moments.
# Fills `out` (a preallocated list) with `n` colours and returns the global
# brightness to use.  Never produces a channel value other than 0 or 255.

def an_static(slot, theme, out, n, base_b):
    for i in range(n):
        out[i] = theme[i & 3]
    return base_b


def an_rotate(slot, theme, out, n, base_b):
    """Theme colours march around the ring.  One step per 320 ms."""
    s = (slot >> 1) & 3
    for i in range(n):
        out[i] = theme[(i + s) & 3]
    return base_b


def an_chase(slot, theme, out, n, base_b):
    """One lit LED runs around; the rest are dark.  160 ms per step."""
    pos = slot % n
    for i in range(n):
        out[i] = theme[i & 3] if i == pos else BLACK
    return base_b


def an_pingpong(slot, theme, out, n, base_b):
    """Lit LED bounces back and forth instead of wrapping.  160 ms per step."""
    span = (n - 1) * 2 if n > 1 else 1
    p = slot % span
    pos = p if p < n else span - p
    for i in range(n):
        out[i] = theme[i & 3] if i == pos else BLACK
    return base_b


def an_alternate(slot, theme, out, n, base_b):
    """Odd/even LEDs swap between two theme colours every 320 ms."""
    s = (slot >> 1) & 1
    for i in range(n):
        out[i] = theme[((i + s) & 1) * 2 + ((i >> 1) & 1)]
    return base_b


def an_pulse(slot, theme, out, n, base_b):
    """Brightness ramp over ~1.3 s -- ANALOG current, electrically silent."""
    for i in range(n):
        out[i] = theme[i & 3]
    lo = 1 + (base_b >> 2)
    return lo + ((base_b - lo) * _tri(slot, 8)) // 4


def an_breathe(slot, theme, out, n, base_b):
    """Same idea as pulse over ~3.8 s."""
    for i in range(n):
        out[i] = theme[i & 3]
    lo = 1 + (base_b >> 3)
    return lo + ((base_b - lo) * _tri(slot, 24)) // 12


def an_strobe(slot, theme, out, n, base_b):
    """All on / all off: 320 ms dark in every 1.28 s.  Kept deliberately
    slow -- fast strobing is both unpleasant and a seizure risk in a dark
    room."""
    on = ((slot >> 1) & 3) != 0
    for i in range(n):
        out[i] = theme[i & 3] if on else BLACK
    return base_b


ANIMS = (an_static, an_rotate, an_chase, an_pingpong,
         an_alternate, an_pulse, an_breathe, an_strobe)
ANIM_NAMES = ("static", "rotate", "chase", "pingpong",
              "alternate", "pulse", "breathe", "strobe")


def name_hash(name):
    """FNV-1a plus an avalanche finalizer.

    The finalizer matters: FNV-1a's LOW bits are weakly mixed and everything
    here takes the result modulo a small number.  Without it, real filenames
    clustered badly.
    """
    h = 2166136261
    for ch in name:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    h ^= h >> 16
    h = (h * 0x7FEB352D) & 0xFFFFFFFF
    h ^= h >> 15
    h = (h * 0x846CA68B) & 0xFFFFFFFF
    h ^= h >> 16
    return h


def assign_looks(names):
    """Per-track (theme, brightness, animation), collisions resolved.

    Theme, brightness and animation come from DIFFERENT slices of the hash, so
    colour and motion are independent -- two tracks can share a palette and
    still look clearly different, which is the point.

    12 x 4 x 8 = 384 combinations, but collisions are still worth handling:
    two channels that look identical defeat the purpose.  On a clash we probe
    the animation first, then brightness, then theme -- so a colliding track
    keeps its colours and changes its motion where possible.
    """
    nt, nb, na = len(THEMES), len(BRIGHT_STEPS), len(ANIMS)
    total = nt * nb * na
    used = set()
    out = []
    for nm in names:
        if len(used) >= total:
            used.clear()
        h = name_hash(nm)
        t0, b0, a0 = h % nt, (h >> 13) % nb, (h >> 21) % na
        cand = (t0, BRIGHT_STEPS[b0], a0)
        if cand in used:
            for k in range(1, total + 1):
                a = (a0 + k) % na
                b = (b0 + (k // na)) % nb
                t = (t0 + (k // (na * nb))) % nt
                cand = (t, BRIGHT_STEPS[b], a)
                if cand not in used:
                    break
        used.add(cand)
        out.append(cand)
    return out


def _describe(step):
    if step <= 0:
        return "step 0/%d  volume 0  (MUTED)" % C.VOL_STEPS
    shift = (C.VOL_TOP_ATTEN_DB // C.VOL_STEP_DB) + (C.VOL_STEPS - step)
    vol = max(1, C.VOL_UNITY >> shift)
    db = 20.0 * math.log(vol / C.VOL_UNITY) / math.log(10)
    tag = "  (MAX)" if step >= C.VOL_STEPS else ""
    return "step %d/%d  volume %5d  %.1f dBFS%s" % (step, C.VOL_STEPS, vol, db, tag)


def _name(path):
    return path.rsplit("/", 1)[-1]


class Lights:
    """Renders animations, writing the chain only when the output changes.

    The change check is what keeps STATIC free: it produces identical output
    every frame, so after the first write there is no further traffic on
    GP24/GP25 at all.
    """

    def __init__(self):
        self.leds = None
        self.n = C.LED_COUNT
        self._buf = [BLACK] * self.n
        self._cur = [None] * self.n
        self._cur_b = None
        if getattr(C, "LED_ENABLE", True):
            self.leds = SK9822(C.LED_CLK, C.LED_DAT, C.LED_COUNT)
        else:
            Pin(C.LED_CLK, Pin.OUT, value=0)
            Pin(C.LED_DAT, Pin.OUT, value=0)

    def render(self, slot, theme_idx, bright, anim_idx):
        if self.leds is None:
            return
        b = ANIMS[anim_idx](slot, THEMES[theme_idx], self._buf, self.n, bright)
        if b == self._cur_b and self._buf == self._cur:
            return                              # nothing changed: stay silent
        self._cur_b = b
        self._cur = list(self._buf)
        self.leds.set_brightness(b)
        for i in range(self.n):
            self.leds.set(i, self._buf[i])
        self.leds.write()

    def error(self, now_ms, code):
        """Blink `code` in red binary.  LED1 is the least significant bit."""
        if self.leds is None:
            return
        lit_phase = (now_ms % ERR_CYCLE_MS) < ERR_ON_MS
        for i in range(self.n):
            on = lit_phase and ((code >> i) & 1)
            self._buf[i] = ERR_COLOR if on else BLACK
        if ERR_BRIGHT == self._cur_b and self._buf == self._cur:
            return
        self._cur_b = ERR_BRIGHT
        self._cur = list(self._buf)
        self.leds.set_brightness(ERR_BRIGHT)
        for i in range(self.n):
            self.leds.set(i, self._buf[i])
        self.leds.write()

    def off(self):
        if self.leds is not None:
            try:
                self.leds.clear()
            except Exception:
                pass


async def main():
    machine.freq(C.CPU_FREQ)
    print("cpu   :", machine.freq())
    print("audio :", "MP3 + WAV" if HAVE_MP3 else "WAV only (no mp3 module)")

    lights = Lights()

    # Guarded: a hang or exception in the IR path must never take the whole
    # badge with it.  An earlier build wedged before USB enumerated, which left
    # no way back in short of replacing the chip.
    tx = None
    rx = None
    try:
        tx = irsync.IrTx()
        rx = irsync.IrRx()
    except Exception as e:
        print("IR disabled:", e)

    player = Player(C.I2S_ID, C.I2S_SCK, C.I2S_WS, C.I2S_SD,
                    C.I2S_IBUF, C.AUDIO_CHUNK)
    player.repeat_track = True

    btns = Buttons({
        "channel": C.BTN_PLAY,
        "vol_up": C.BTN_VOL_UP,
        "vol_down": C.BTN_VOL_DN,
        "sync": C.BTN_SYNC,
    })
    btns.repeat = {"vol_up", "vol_down"}
    # Tap-on-release + long-press semantics for CHANNEL.  Buttons already
    # implements exactly this: a tap emits "channel" when released, and a hold
    # past hold_ms emits "channel_hold" once and then suppresses the tap -- so
    # holding to reset does NOT also change channel on the way past.
    btns.hold = {"channel"}
    btns.hold_ms = RESET_HOLD_MS

    tracks = []
    err = 0
    try:
        if mount_sd():
            tracks = find_tracks()
            if not tracks:
                err = ERR_NO_TRACKS
        else:
            err = ERR_NO_CARD
    except Exception as e:
        print("SD mount raised:", e)
        err = ERR_SD_EXC

    if err:
        # Do NOT return.  Bailing out left the badge totally inert -- no
        # buttons, and no hold-to-reset either, which is precisely the state
        # the escape hatch exists for.  Stay alive, blink the code, keep the
        # reset available.
        print("ERROR %d: %s" % (err, ERR_NAMES.get(err, "unknown")))
        print("LEDs show the code in red binary (LED1 = LSB)")
        print("buttons still live: hold CHANNEL %ds to reset"
              % (RESET_HOLD_MS // 1000))
        hold_t0 = None
        while True:
            lights.error(time.ticks_ms(), err)   # dedups internally
            if btns.pressed("channel"):
                if hold_t0 is None:
                    hold_t0 = time.ticks_ms()
            else:
                hold_t0 = None
            for ev in btns.poll():
                if ev == "channel_hold":
                    print("CHANNEL held -- hard reset")
                    time.sleep_ms(60)
                    machine.reset()
            await asyncio.sleep_ms(20)

    player.playlist = tracks
    looks = assign_looks([_name(p) for p in tracks])
    print("%d channel(s):" % len(tracks))
    for i, p in enumerate(tracks):
        t, b, a = looks[i]
        print("  %2d. %-28s %-10s %-10s b%d"
              % (i + 1, _name(p)[:28], THEME_NAMES[t], ANIM_NAMES[a], b))

    if START_CHANNEL:
        player.index = START_CHANNEL % len(tracks)

    vol = VOLUME_STEP
    player.set_volume_step(vol, C.VOL_STEPS)
    print("volume:", _describe(vol))
    print("CHANNEL tap = next  |  hold %ds = reset  |  VOL+/- = volume"
          % (RESET_HOLD_MS // 1000))

    listening = False
    listen_until = 0

    def start_sync():
        """Pause playback, go quiet, and listen for a neighbour."""
        nonlocal listening, listen_until
        if rx is None:
            print("sync: IR unavailable")
            return
        listening = True
        listen_until = time.ticks_add(time.ticks_ms(), SYNC_LISTEN_MS)
        if tx is not None:
            tx.idle()               # stop transmitting so we do not hear ourselves
        rx.start()                  # arm the capture IRQ only while listening
        if not player.paused:
            player.toggle_pause()   # silence while listening (I2S drains ~180ms)
        print("sync: listening %ds (playback paused)" % (SYNC_LISTEN_MS // 1000))

    def end_sync(why, resume=True):
        """resume=False when the caller has already restarted playback (a
        successful lock un-pauses via the skip machinery)."""
        nonlocal listening
        listening = False
        if rx is not None:
            rx.stop()               # disarm: no IRQ load during playback
        if resume and player.paused:
            player.toggle_pause()   # timeout/cancel: pick up where we left off
        print("sync:", why)

    async def input_task():
        nonlocal vol
        hold_t0 = None
        said = -1
        while True:
            # Countdown on the console so a long hold is visibly doing
            # something -- 10 s of silence feels like a dead button.
            if btns.pressed("channel"):
                if hold_t0 is None:
                    hold_t0 = time.ticks_ms()
                    said = -1
                else:
                    left = RESET_HOLD_MS - time.ticks_diff(time.ticks_ms(), hold_t0)
                    secs = left // 1000
                    if 0 <= secs < 5 and secs != said:
                        said = secs
                        print("reset in %d..." % (secs + 1))
            else:
                hold_t0 = None

            for ev in btns.poll():
                if ev == "channel":
                    if listening:
                        end_sync("cancelled (channel pressed)")
                    player.next_track()
                elif ev == "sync":
                    if not listening:
                        start_sync()
                elif ev == "channel_hold":
                    print("CHANNEL held %ds -- hard reset" % (RESET_HOLD_MS // 1000))
                    time.sleep_ms(60)          # let the print flush over USB
                    machine.reset()
                elif ev == "vol_up":
                    if vol >= C.VOL_STEPS:
                        continue
                    vol += 1
                    player.set_volume_step(vol, C.VOL_STEPS)
                    print("volume:", _describe(vol))
                elif ev == "vol_down":
                    if vol <= 0:
                        continue
                    vol -= 1
                    player.set_volume_step(vol, C.VOL_STEPS)
                    print("volume:", _describe(vol))
            await asyncio.sleep_ms(20)

    async def led_task():
        """Drives LEDs from the player's own index and CLOCK.

        Animation phase is the playback position quantised to SLOT_MS, not a
        local counter: a counter ticked by sleep_ms runs percent-level slow
        under decode load and differently per badge, which is exactly the
        "lights drift apart" that was visible by eye.  Position-derived slots
        mean badges locked to the same track time flash at the same track
        time, always -- and a re-sync snaps the lights together with the
        audio.  The chain is only written when the computed output changes,
        so polling fast costs no LED traffic.
        """
        last = None
        while True:
            cur = player.index % len(player.playlist)
            if cur != last:
                last = cur
                t, b, a = looks[cur]
                print("channel %d/%d: %-28s %s + %s"
                      % (cur + 1, len(player.playlist),
                         _name(player.playlist[cur])[:28],
                         THEME_NAMES[t], ANIM_NAMES[a]))
            if player.errors >= 3:
                # Repeated failures are worth showing on the badge, not just
                # on a console nobody is watching.
                lights.error(time.ticks_ms(), ERR_PLAYBACK)
            elif listening:
                # glacier + breathe on the WALL clock: playback is paused
                # while listening, so track time is frozen here.
                lights.render(time.ticks_ms() // SLOT_MS, 7, 20, 6)
            else:
                t, b, a = looks[cur]
                lights.render(player.pos_ms // SLOT_MS, t, b, a)
            await asyncio.sleep_ms(LED_POLL_MS)

    async def auto_sync_task():
        """Fire SYNC on a timer.  Test hook only; disabled when AUTO_SYNC_MS=0."""
        if not AUTO_SYNC_MS:
            return
        print("AUTO-SYNC test hook: every %ds" % (AUTO_SYNC_MS // 1000))
        while True:
            await asyncio.sleep_ms(AUTO_SYNC_MS)
            if not listening:
                start_sync()
                return          # fire ONCE -- so a scripted drift measurement
                                # is not re-corrected every cycle

    async def ir_task():
        """Broadcast (timecode, channel) periodically; listen instead on SYNC.

        Timecode is the decoded-audio position, so it excludes the ~230 ms I2S
        buffer latency -- fine between badges, since every badge has the same
        lag.
        """
        if tx is None:
            return
        next_tx = time.ticks_add(time.ticks_ms(), random.randint(IR_TX_MIN_MS, IR_TX_MAX_MS))
        while True:
            if listening:
                got = rx.poll()
                if got:
                    tc100, ch = got
                    # Timestamp NOW: everything that happens between here and
                    # the actual file seek is measured and added back by the
                    # player, so track-switch/SD latency cannot become lag.
                    player.seek_ref = time.ticks_ms()
                    player.seek_ms = tc100 * 100 + IR_SEND_LATENCY_MS
                    ntr = len(player.playlist)
                    ch %= ntr
                    note = ""
                    if ch != (player.index % ntr):
                        player.goto_track(ch)      # join their channel too
                        note = " joined ch %d" % (ch + 1)
                    else:
                        player.restart_track()
                    end_sync("locked to ch %d @ %d.%01ds%s"
                             % (ch + 1, player.seek_ms // 1000,
                                (player.seek_ms % 1000) // 100, note),
                             resume=False)
                    next_tx = time.ticks_add(time.ticks_ms(), random.randint(IR_TX_MIN_MS, IR_TX_MAX_MS))
                elif time.ticks_diff(time.ticks_ms(), listen_until) >= 0:
                    # Say WHY it failed.  "edges=0" means nothing reached the
                    # receiver at all; a list of widths means a frame arrived
                    # but did not decode, which is a timing-constant problem.
                    print("sync: frames seen=%d failed=%d" % (rx.attempts, rx.fails))
                    if rx.last_fail:
                        print("sync: last failed frame:", rx.last_fail)
                    else:
                        print("sync: live buffer:", rx.dump())
                    end_sync("timed out, nothing decoded")
                    next_tx = time.ticks_add(time.ticks_ms(), random.randint(IR_TX_MIN_MS, IR_TX_MAX_MS))
                await asyncio.sleep_ms(20)
            else:
                if time.ticks_diff(time.ticks_ms(), next_tx) >= 0:
                    ch = player.index % len(player.playlist)
                    pos = player.pos_ms
                    try:
                        tx.send(pos // 100, ch)      # blocks ~35-60 ms
                        print("ir tx: ch %d  t=%d.%01ds" % (ch + 1, pos // 1000,
                                                            (pos % 1000) // 100))
                    except Exception as e:
                        print("ir tx failed:", e)
                    next_tx = time.ticks_add(time.ticks_ms(), random.randint(IR_TX_MIN_MS, IR_TX_MAX_MS))
                await asyncio.sleep_ms(50)

    try:
        await asyncio.gather(player.run(), input_task(), led_task(), ir_task(),
                             auto_sync_task())
    finally:
        player.deinit()
        lights.off()
        if tx is not None:
            tx.deinit()
        if rx is not None:
            rx.stop()


def run():
    asyncio.run(main())
