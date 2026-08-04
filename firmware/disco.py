"""
Silent disco badge.

    boot     -> mount SD -> resume where the badge last was (or channel 1)
    CHANNEL  (GP15)  tap = next track (wraps);  hold 10 s = hard reset
    SYNC     (GP12)  join a neighbour: playback pauses, the badge listens for
                     their broadcast, then adopts BOTH their channel and their
                     position.  Times out back to where you were.
    VOL+/-   (GP14/GP13)  louder / quieter, auto-repeat when held

A track that reaches its end REPLAYS ITSELF -- it never advances on its own.
Channel, position and volume persist to internal flash, so a brownout resumes
mid-set (rewound a few seconds).  Faults show as red binary on the LEDs
(codes below); the badge stays alive and resettable on every error path.

LEDs
----
Each track name hashes to a THEME (four colours), an ANIMATION and a
brightness -- independent slices of the hash, so a card mixes colour and
motion freely.  All animation is a pure function of the PLAYBACK clock
(pos_ms // SLOT_MS): badges synced to the same position flash at the same
moments and stay locked, and a re-sync snaps lights and music together.

Hard rules, learned on hardware and enforced by tools/host_tests.py:
  * Every channel value is 0 or 255 -- mid-range PWM couples audibly into the
    audio (config.py:29-33), so nothing ever crossfades; motion is WHICH LED
    shows WHICH colour.  Brightness "fades" use the SK9822 global current,
    which is analog and silent.
  * At most one white per theme (white glares and desaturates); contrast
    comes from black.  No naked-primary pairings (they read like a toy);
    the good looks are secondaries and adjacency blends -- R|Y reads orange,
    B|M reads purple, which is how the banned colours exist at all.
  * Full-field flashing stays under ~1.5 Hz (photosensitivity).

IR sync
-------
Every 7-13 s (randomised, so a room of badges cannot lockstep-collide) the
badge broadcasts (timecode, channel) over IR.  SYNC arms the receiver
instead: NEC-style frames, decoded by a hard-IRQ edge-capture that resyncs
on the 9 ms header mark (ambient light fires ~660 edges/s; see irsync.py).
Received timecodes are latency-compensated (IR_SEND_LATENCY_MS + a live
measurement of our own restart cost) -- measured residual ~+/-70 ms.

The two things that can stall the VM -- internal-flash state writes (XIP
freeze, up to ~100 ms) and the ~68 ms blocking IR send -- are deliberately
kept STALL_SPACING_MS apart so they cannot stack inside one I2S buffer.
The emit watchdog logs any gap over 150 ms with blame attribution.
"""

import gc
import os
import time
import json
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

# Crash resilience: channel, position and volume persist to INTERNAL flash
# (never the SD -- card writes are unproven on this board) and are restored on
# boot, so a brownout resumes mid-set instead of restarting it.
#
# Every internal-flash write SUSPENDS XIP: the whole VM freezes for the
# duration (up to ~100 ms when an erase is involved).  That is unavoidable --
# so the design minimises how often and how badly it can hurt:
#   * A/B slot files with a sequence number instead of write-temp-and-rename:
#     each checkpoint touches ONE small file (rename doubled the metadata
#     traffic).  Torn writes are survivable -- the loader takes the newest
#     slot that parses and checksums; the other slot is the fallback.
#   * Position checkpoints every ~30 s (a brownout rewinds up to that much,
#     which is fine at a party); channel/volume within 2 s of changing.
#   * Coordinated with the IR transmitter (see STALL_SPACING_MS): the ~68 ms
#     send and the flash freeze are each survivable alone, but stacked inside
#     one I2S buffer window they were the leading suspect for the "occasional
#     stutter" reports.  Now they keep their distance by construction.
PERSIST_SLOTS = ("/state_a.json", "/state_b.json")
PERSIST_LEGACY = "/disco_state.json"       # migrated from, then ignored
PERSIST_TICK_MS = 2000
PERSIST_POS_DELTA_MS = 30_000

# Minimum spacing between the two known VM-stallers (flash write, IR send).
STALL_SPACING_MS = 700

# How often to re-probe a missing/failed SD card.  Each probe blocks for up
# to ~1 s (5 init attempts), so this only runs when audio is already dead.
SD_RETRY_MS = 5_000


def _state_ck(st):
    """Tiny integrity checksum -- catches torn flash writes, not attackers."""
    return (st.get("seq", 0) + st.get("pos", 0) + st.get("vol", 0)
            + len(st.get("track", ""))) & 0xFFFF


def batt_low(volts, was_low):
    """Low-battery decision with hysteresis (pure, host-tested)."""
    if was_low:
        return volts < C.BATT_LOW_V + C.BATT_HYST_V
    return volts < C.BATT_LOW_V


def should_persist(last, st):
    """Write only when something meaningful changed (pure, host-tested)."""
    return not (st["track"] == last.get("track")
                and st["vol"] == last.get("vol")
                and abs(st["pos"] - last.get("pos", -1 << 30))
                < PERSIST_POS_DELTA_MS)


def load_state():
    """Newest valid slot wins; falls back to the legacy single file."""
    best = None
    for path in PERSIST_SLOTS + (PERSIST_LEGACY,):
        try:
            with open(path) as f:
                st = json.load(f)
            if path != PERSIST_LEGACY and st.get("ck") != _state_ck(st):
                continue                     # torn write: use the other slot
            if best is None or st.get("seq", 0) > best.get("seq", 0):
                best = st
        except Exception:
            pass
    return best

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

K = BLACK   # an off LED is a design element: electrically perfect, and it buys
            # coals, voids and asymmetry the 7 pure colours cannot.

# Themes: four colours across LED1..LED4, curated as VIBES rather than swept
# hue windows.  Three lessons shape them, the third learned on hardware:
#   * adjacent-LED blending -- the eye mixes neighbours at arm's length, so
#     R next to Y reads as orange (fire, sunset) and M next to B reads as
#     purple (synthwave, defcon): the two banned colours, recovered optically.
#   * black as a colour -- gaps and asymmetry read as texture, especially
#     under rotate/pulse (fire flickers over dark coals, matrix has a void).
#   * WHITE DESATURATES.  A white LED is ~3x the luminance of any pure colour
#     and reads as glare that washes out everything beside it -- the original
#     glacier (two whites of four) looked dull in practice.  Rule: at most ONE
#     white per theme, used as a glint; contrast comes from black instead.
# Fourth lesson, also from eyeballing hardware: NAKED PRIMARIES READ CHEAP.
# Pure R/G/B pairings look like a toy; the looks that pop are secondaries
# (Cy, M, Y) and adjacency blends (B|M purple, G|Cy teal, R|M crimson).  So
# themes lean on blends, the set skews cool (blues/greens/purples, per taste),
# and no theme pairs two naked primaries for its identity -- sirens excepted,
# because sirens is a bit, not an aesthetic.
THEMES = (
    (Cy, B, Cy, M),     # glacier    ice blues with a violet depth
    (G, Cy, M, B),      # aurora     green -> cyan -> magenta -> blue sweep
    (M, B, Cy, M),      # synthwave  neon sunset; M|B edge reads purple
    (B, M, B, K),       # twilight   deep purple night over a dark gap
    (Cy, G, Cy, B),     # lagoon     tropical teal via the G|Cy blend
    (M, R, Y, R),       # sunset     magenta -> red -> gold gradient
    (R, Y, R, K),       # fire       flames over a dark coal
    (G, K, G, G),       # matrix     terminal green with a void (iconic; keep)
    (G, Y, G, K),       # toxic      radioactive lime
    (Cy, M, Cy, M),     # miami      hard neon alternation, all secondaries
    (M, B, M, B),       # defcon     reads purple at distance
    (R, B, R, B),       # sirens     you know exactly what this is
    (B, Cy, K, B),      # ocean      deep water over a dark trench
    (M, Cy, M, W),      # candy      bubblegum + mint, one sparkle
    (M, R, M, R),       # neon rose  hot pink via the M|R blend
    (R, K, R, M),       # vampire    crimson with a violet undertone
)
THEME_NAMES = ("glacier", "aurora", "synthwave", "twilight", "lagoon",
               "sunset", "fire", "matrix", "toxic", "miami", "defcon",
               "sirens", "ocean", "candy", "neon rose", "vampire")

# SK9822 global current, 0..31, ANALOG so quiet at any value.  Shifted well
# DOWN from the first pass (5/10/16/24): at high current the LEDs bloom and
# perceived saturation collapses -- dimmer genuinely reads more vibrant, which
# was confirmed by eye on hardware.  Bonus: less LED current on the shared
# rail, and longer battery life.
BRIGHT_STEPS = (3, 5, 8, 12)

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
# Randomness comes from _shash(slot) -- a hash of the slot, so "random" looks
# are still pure functions of track time and match across badges.
# Never a channel value other than 0/255; brightness is the SK9822 analog
# current field (silent).  Full-field flashing stays at or under ~1.5 Hz.

def _shash(x):
    """Cheap deterministic slot hash (Knuth multiplicative + xor fold)."""
    x = (x * 2654435761) & 0xFFFFFFFF
    return x ^ (x >> 13)


def an_static(slot, theme, out, n, base_b):
    for i in range(n):
        out[i] = theme[i & 3]
    return base_b


def an_spin(slot, theme, out, n, base_b):
    """Theme colours whip around the ring, one step per slot (160 ms)."""
    s = slot & 3
    for i in range(n):
        out[i] = theme[(i + s) & 3]
    return base_b


def an_comet(slot, theme, out, n, base_b):
    """A head runs the ring with a contrasting tail one step behind."""
    head = slot % n
    tail = (head - 1) % n
    for i in range(n):
        if i == head:
            out[i] = theme[head & 3]
        elif i == tail:
            out[i] = theme[(head + 2) & 3]
        else:
            out[i] = BLACK
    return base_b


def an_scanner(slot, theme, out, n, base_b):
    """Two adjacent LEDs sweep back and forth -- wider, meaner pingpong."""
    span = (n - 2) * 2 if n > 2 else 1
    p = slot % span
    pos = p if p < (n - 1) else span - p
    for i in range(n):
        out[i] = theme[i & 3] if i in (pos, pos + 1) else BLACK
    return base_b


def an_alternate(slot, theme, out, n, base_b):
    """Odd/even LEDs swap between two theme colours every 320 ms."""
    s = (slot >> 1) & 1
    for i in range(n):
        out[i] = theme[((i + s) & 1) * 2 + ((i >> 1) & 1)]
    return base_b


def an_thump(slot, theme, out, n, base_b):
    """Brightness KICK every 4 slots (~94 BPM): slam bright, decay, repeat.
    Colour never changes -- all the motion is the analog current, so it is
    electrically silent and reads exactly like a beat."""
    for i in range(n):
        out[i] = theme[i & 3]
    m = (8, 4, 3, 2)[slot & 3]          # 2x, 1x, .75x, .5x of base
    return max(1, min(31, (base_b * m) >> 2))


def an_pulse(slot, theme, out, n, base_b):
    """Brightness ramp over ~1.3 s -- ANALOG current, electrically silent."""
    for i in range(n):
        out[i] = theme[i & 3]
    lo = 1 + (base_b >> 2)
    return lo + ((base_b - lo) * _tri(slot, 8)) // 4


def an_breathe(slot, theme, out, n, base_b):
    """Same idea as pulse over ~3.8 s -- the one calm option in the set."""
    for i in range(n):
        out[i] = theme[i & 3]
    lo = 1 + (base_b >> 3)
    return lo + ((base_b - lo) * _tri(slot, 24)) // 12


def an_sparkle(slot, theme, out, n, base_b):
    """Deterministic glitter: a hashed subset of LEDs lights each slot.
    Sparse per-LED twinkle, never a full-field flash."""
    bits = _shash(slot) & 0xF
    if not bits & ((1 << n) - 1):
        bits = 0b0101                    # never fully dark
    for i in range(n):
        out[i] = theme[i & 3] if (bits >> i) & 1 else BLACK
    return base_b


def an_wave(slot, theme, out, n, base_b):
    """Spin and pulse at once -- colours orbit while brightness rolls."""
    s = (slot >> 1) & 3
    for i in range(n):
        out[i] = theme[(i + s) & 3]
    lo = 1 + (base_b >> 2)
    return lo + ((base_b - lo) * _tri(slot, 8)) // 4


def an_flash(slot, theme, out, n, base_b):
    """All on / all off: 320 ms dark in every 1.28 s.  Kept deliberately
    slow -- fast full-field strobing is a seizure risk in a dark room."""
    on = ((slot >> 1) & 3) != 0
    for i in range(n):
        out[i] = theme[i & 3] if on else BLACK
    return base_b


def an_jump(slot, theme, out, n, base_b):
    """The whole colour arrangement teleports to a hashed rotation every
    320 ms -- jump-cut dancing instead of smooth motion."""
    s = _shash(slot >> 1) & 3
    for i in range(n):
        out[i] = theme[(i + s) & 3]
    return base_b


ANIMS = (an_static, an_spin, an_comet, an_scanner, an_alternate, an_thump,
         an_pulse, an_breathe, an_sparkle, an_wave, an_flash, an_jump)
ANIM_NAMES = ("static", "spin", "comet", "scanner", "alternate", "thump",
              "pulse", "breathe", "sparkle", "wave", "flash", "jump")


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
    player.blame = {}               # stall attribution for the emit watchdog

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

    # Mount the card -- and if it is missing/empty, KEEP TRYING while
    # blinking the error code.  Inserting a card must bring the badge to
    # life without a reset: it will be handed to people who have never
    # heard of BOOTSEL.
    tracks = []
    err = 0
    hold_t0 = None
    last_try = -60_000
    while True:
        if time.ticks_diff(time.ticks_ms(), last_try) >= SD_RETRY_MS:
            last_try = time.ticks_ms()
            err = 0
            try:
                os.umount(C.SD_MOUNT)          # clean slate for the retry
            except Exception:
                pass
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
            if not err:
                break
            print("ERROR %d: %s -- will keep retrying; insert a card"
                  % (err, ERR_NAMES.get(err, "?")))
        lights.error(time.ticks_ms(), err or ERR_NO_CARD)
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

    # --- restore persisted state (channel by NAME, position, volume) -------
    vol = VOLUME_STEP
    names = [_name(p) for p in tracks]
    try:
        st = load_state() or {}
        if st.get("track") in names:
            player.index = names.index(st["track"])
        pos = st.get("pos")
        if isinstance(pos, int) and pos > 0:
            player.seek_ms = pos        # CBR byte seek; wraps if past track end
        v = st.get("vol")
        if isinstance(v, int) and 0 <= v <= C.VOL_STEPS:
            vol = v
        if st:
            print("restored: %s @ %ds, vol %d/%d"
                  % (st.get("track"), (pos or 0) // 1000, vol, C.VOL_STEPS))
    except Exception as e:
        print("state restore failed:", e)

    if START_CHANNEL:
        player.index = START_CHANNEL % len(tracks)

    player.set_volume_step(vol, C.VOL_STEPS)
    print("volume:", _describe(vol))
    print("CHANNEL tap = next  |  hold %ds = reset  |  VOL+/- = volume"
          % (RESET_HOLD_MS // 1000))

    listening = False
    listen_until = 0
    celebrate_until = 0

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
                # while listening, so track time is frozen here.  Looked up by
                # NAME -- a hardcoded index already broke once when the theme
                # list was reordered.
                lights.render(time.ticks_ms() // SLOT_MS,
                              THEME_NAMES.index("glacier"), 10,
                              ANIM_NAMES.index("breathe"))
            elif time.ticks_diff(celebrate_until, time.ticks_ms()) > 0:
                # sync-lock celebration: a bright fast shimmer in the NEW
                # channel's theme, so both people SEE the join land.  Colour
                # swap only -- never a dark field, so no flash-rate concern.
                t, b, a = looks[cur]
                lights.render(time.ticks_ms() // 80, t, 16,
                              ANIM_NAMES.index("alternate"))
            else:
                t, b, a = looks[cur]
                lights.render(player.pos_ms // SLOT_MS, t, b, a)
            await asyncio.sleep_ms(LED_POLL_MS)

    async def persist_task():
        """Checkpoint (track, position, volume) to internal flash.

        Also hosts the housekeeping GC: collecting on OUR schedule keeps the
        automatic collector from firing at a random moment inside the audio
        path, and keeps fragmentation down for track-change allocations.
        """
        last = {}
        seq = 0
        slot = 0
        while True:
            await asyncio.sleep_ms(PERSIST_TICK_MS)
            gc.collect()
            if not player.playlist:
                continue
            st = {"track": _name(player.playlist[player.index %
                                                 len(player.playlist)]),
                  "pos": player.pos_ms,
                  "vol": vol}
            if not should_persist(last, st):
                continue
            # keep the flash freeze away from a fresh IR send
            if (player.blame and "ir" in player.blame and
                    time.ticks_diff(time.ticks_ms(),
                                    player.blame["ir"]) < STALL_SPACING_MS):
                continue                     # retry on the next 2 s tick
            seq += 1
            st["seq"] = seq
            st["ck"] = _state_ck(st)
            try:
                with open(PERSIST_SLOTS[slot], "w") as f:
                    json.dump(st, f)
                slot ^= 1
                st.pop("seq"); st.pop("ck")
                last = st
                if player.blame is not None:
                    player.blame["persist"] = time.ticks_ms()
            except Exception as e:
                print("persist failed:", e)

    async def battery_task():
        """Warn about a dying battery BEFORE it wrecks the audio and the SD.

        Inert unless the SAO divider bodge is fitted (config.BATT_ADC_GPIO).
        Warning is deliberately subtle: LED1 winks red between animation
        frames every few seconds -- visible to the wearer, not a light show.
        """
        if getattr(C, "BATT_ADC_GPIO", None) is None:
            return
        from machine import ADC
        adc = ADC(C.BATT_ADC_GPIO)
        low = False
        while True:
            await asyncio.sleep_ms(5000)
            v = adc.read_u16() * 3.3 * C.BATT_DIVIDER / 65535
            now_low = batt_low(v, low)
            if now_low and not low:
                print("BATTERY LOW: %.2f V -- swap the AAA soon" % v)
            low = now_low
            if low and lights.leds is not None:
                # brief red wink on LED1 only; render() repaints the theme
                # on its next change so this never sticks
                lights.leds.set_brightness(8)
                lights.leds.set(0, (255, 0, 0))
                lights.leds.write()
                await asyncio.sleep_ms(180)
                lights._cur_b = None          # force theme repaint

    async def sd_recovery_task():
        """If playback keeps failing (yanked/flaky card), try a full remount.

        Only runs once audio is already dead (player.errors gate), because a
        probe of an absent card blocks up to ~1 s.  On success the playlist
        AND the per-track looks are rebuilt -- the card that comes back may
        not be the card that left.
        """
        nonlocal looks
        while True:
            await asyncio.sleep_ms(SD_RETRY_MS)
            if player.errors < 4:
                continue
            print("sd: attempting recovery...")
            try:
                os.umount(C.SD_MOUNT)
            except Exception:
                pass
            try:
                if mount_sd():
                    nt = find_tracks()
                    if nt:
                        player.playlist = nt
                        looks = assign_looks([_name(x) for x in nt])
                        player.errors = 0
                        player.seek_ms = 0
                        player.restart_track()
                        print("sd: recovered, %d track(s)" % len(nt))
            except Exception as e:
                print("sd: recovery failed:", e)

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
            nonlocal celebrate_until
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
                    celebrate_until = time.ticks_add(time.ticks_ms(), 1400)
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
                    # keep the ~68 ms blocking send away from a fresh flash
                    # write -- stacked, the two stalls can outrun the I2S
                    # buffer; spaced, each hides inside it comfortably
                    if (player.blame and "persist" in player.blame and
                            time.ticks_diff(time.ticks_ms(),
                                            player.blame["persist"])
                            < STALL_SPACING_MS):
                        await asyncio.sleep_ms(STALL_SPACING_MS)
                    ch = player.index % len(player.playlist)
                    pos = player.pos_ms
                    try:
                        tx.send(pos // 100, ch)      # blocks ~68 ms
                        player.blame["ir"] = time.ticks_ms()
                        print("ir tx: ch %d  t=%d.%01ds" % (ch + 1, pos // 1000,
                                                            (pos % 1000) // 100))
                    except Exception as e:
                        print("ir tx failed:", e)
                    next_tx = time.ticks_add(time.ticks_ms(), random.randint(IR_TX_MIN_MS, IR_TX_MAX_MS))
                await asyncio.sleep_ms(50)

    try:
        await asyncio.gather(player.run(), input_task(), led_task(), ir_task(),
                             auto_sync_task(), persist_task(),
                             sd_recovery_task(), battery_task())
    finally:
        player.deinit()
        lights.off()
        if tx is not None:
            tx.deinit()
        if rx is not None:
            rx.stop()


def run():
    asyncio.run(main())
