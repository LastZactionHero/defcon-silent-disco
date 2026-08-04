"""
DEFCON silent-disco badge -- plain MP3 player.

Plays every track on the card, in order, forever.  The playlist is a FLAT
listing of the card root sorted alphabetically (no subdirectory walking),
capped at config.MAX_TRACKS.

Buttons:
    CH    (GP15)  play / pause
    VOL+  (GP14)  volume up        (auto-repeats when held)
    VOL-  (GP13)  volume down      (auto-repeats when held)
    SYNC  (GP12)  TAP = next track, HOLD = previous track

Lights run themselves -- there is no spare button to cycle them -- rotating
through audio-reactive animations and flashing acknowledgements for volume and
track changes.  See discolights.py.

Recovery: hold CH while powering on to skip autostart and land in the REPL.
"""

import time
import asyncio
import machine
from machine import Pin, SPI

import config as C
from sk9822 import SK9822
from discolights import DiscoLights
from buttons import Buttons
from wavplayer import Player, HAVE_MP3

EXTS = (".mp3", ".wav")


def mount_sd():
    """Init + mount the SD card. Returns True on success."""
    import os
    import sdcard
    spi = SPI(C.SD_SPI_ID, baudrate=C.SD_BAUD_INIT, polarity=0, phase=0,
              sck=Pin(C.SD_SCK), mosi=Pin(C.SD_MOSI), miso=Pin(C.SD_MISO))
    cs = Pin(C.SD_CS, Pin.OUT, value=1)
    # drain the bus in case a prior run left the card mid-transfer
    for _ in range(3):
        cs.value(0)
        for _ in range(600):
            spi.write(b"\xff")
        cs.value(1)
        for _ in range(32):
            spi.write(b"\xff")
        time.sleep_ms(20)
    card = None
    for attempt in range(5):
        try:
            card = sdcard.SDCard(spi, cs, baudrate=C.SD_BAUD_DATA)
            break
        except Exception as e:
            print("sd init attempt %d: %s" % (attempt + 1, e))
            time.sleep_ms(150)
    if card is None:
        return False
    os.mount(os.VfsFat(card), C.SD_MOUNT)
    print("SD mounted: %d sectors (~%d MB)" % (card.sectors, card.sectors // 2048))
    return True


def find_tracks():
    """Flat, alphabetical listing of playable files in the card root."""
    import os
    try:
        files = os.listdir(C.SD_MOUNT)
    except Exception:
        return []
    exts = EXTS if HAVE_MP3 else (".wav",)
    # MicroPython's str.endswith() takes no tuple, so test each extension.
    names = []
    for f in files:
        if f.startswith("."):           # skips ._AppleDouble junk too
            continue
        low = f.lower()
        for e in exts:
            if low.endswith(e):
                names.append(f)
                break
    names.sort()
    if len(names) > C.MAX_TRACKS:
        print("note: %d files found, using the first %d"
              % (len(names), C.MAX_TRACKS))
        names = names[:C.MAX_TRACKS]
    return [C.SD_MOUNT + "/" + f for f in names]


def now_playing(player):
    if not player.playlist:
        return "(no tracks)"
    path = player.playlist[player.index % len(player.playlist)]
    return path.rsplit("/", 1)[-1]


async def input_task(player, lights, btns):
    step = C.VOL_DEFAULT_STEP
    player.set_volume_step(step, C.VOL_STEPS)
    while True:
        for ev in btns.poll():
            if ev == "vol_up":
                step = min(C.VOL_STEPS, step + 1)
                player.set_volume_step(step, C.VOL_STEPS)
                lights.show_volume(step, C.VOL_STEPS)
            elif ev == "vol_down":
                step = max(0, step - 1)
                player.set_volume_step(step, C.VOL_STEPS)
                lights.show_volume(step, C.VOL_STEPS)
            elif ev == "play_pause":
                player.toggle_pause()
                print("paused" if player.paused else "playing:", now_playing(player))
            elif ev == "track":              # tap
                player.next_track()
                lights.show_track_change(1)
            elif ev == "track_hold":         # hold
                player.prev_track()
                lights.show_track_change(-1)
        await asyncio.sleep_ms(20)


async def led_task(player, lights):
    while True:
        lights.render(level=player.level, paused=player.paused)
        await asyncio.sleep_ms(30)


class NullLights:
    """Stand-in for DiscoLights when C.LED_ENABLE is False.

    Swallows the UI calls input_task makes so the buttons still work with the
    LED path completely inert.  No render() -- led_task is not started at all.
    """

    def show_volume(self, *a, **k):
        pass

    def show_track_change(self, *a, **k):
        pass

    def render(self, *a, **k):
        pass


def _silence_leds():
    """Blank the chain, then park the bit-bang pins so they stop switching.

    One clear frame is unavoidable (the LEDs latch their last state), but it
    happens before playback starts.  After this the pins are static outputs and
    emit no edges for the rest of the session.
    """
    leds = SK9822(C.LED_CLK, C.LED_DAT, C.LED_COUNT)
    try:
        leds.clear()
    except Exception as e:
        print("LED clear failed:", e)
    Pin(C.LED_CLK, Pin.OUT, value=0)
    Pin(C.LED_DAT, Pin.OUT, value=0)
    return leds


async def announce_task(player):
    """Print the track name whenever it changes."""
    last = None
    while True:
        cur = player.index
        if cur != last and player.playlist:
            last = cur
            print("track %d/%d: %s"
                  % (cur + 1, len(player.playlist), now_playing(player)))
        await asyncio.sleep_ms(200)


async def main():
    machine.freq(C.CPU_FREQ)          # before any peripheral init

    leds_on = getattr(C, "LED_ENABLE", True)
    if leds_on:
        leds = SK9822(C.LED_CLK, C.LED_DAT, C.LED_COUNT)
        lights = DiscoLights(leds)
    else:
        leds = _silence_leds()
        lights = NullLights()
        print("LEDs DISABLED (C.LED_ENABLE=False): chain blanked, "
              "GP%d/GP%d parked, no bit-bang traffic" % (C.LED_CLK, C.LED_DAT))

    btns = Buttons({
        "track": C.BTN_SYNC,
        "vol_down": C.BTN_VOL_DN,
        "vol_up": C.BTN_VOL_UP,
        "play_pause": C.BTN_PLAY,
    })
    btns.repeat = {"vol_up", "vol_down"}
    btns.hold = {"track"}             # tap = next, hold = previous

    player = Player(C.I2S_ID, C.I2S_SCK, C.I2S_WS, C.I2S_SD,
                    C.I2S_IBUF, C.AUDIO_CHUNK)

    print("audio:", "MP3 + WAV" if HAVE_MP3 else "WAV only")
    try:
        if mount_sd():
            player.playlist = find_tracks()
    except Exception as e:
        print("SD mount failed:", e)
    if player.playlist:
        print("%d track(s):" % len(player.playlist))
        for i, p in enumerate(player.playlist):
            print("  %2d. %s" % (i + 1, p.rsplit("/", 1)[-1]))
    else:
        print("no tracks -- running as a light toy (buttons still work)")
        player.status = "no_files"

    print("CH=play/pause  VOL+/-  SYNC: tap=next, hold=previous")
    try:
        tasks = [
            player.run(),
            input_task(player, lights, btns),
            announce_task(player),
        ]
        if leds_on:
            tasks.insert(2, led_task(player, lights))
        await asyncio.gather(*tasks)
    finally:
        player.deinit()
        try:
            leds.clear()
        except Exception:
            pass


def _autostart_blocked():
    """Hold CH/play-pause at boot to skip autostart and reach the REPL."""
    hold = Pin(C.BTN_PLAY, Pin.IN, Pin.PULL_UP)
    time.sleep_ms(20)
    return hold.value() == 0


def run():
    if _autostart_blocked():
        print("autostart skipped (CH held) -- REPL. "
              "Run: import mp3player; import asyncio; asyncio.run(mp3player.main())")
        return
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("stopped")
    finally:
        asyncio.new_event_loop()      # leave the REPL usable
