"""
DEFCON silent-disco badge -- main firmware.

Boots into a WAV player streamed from the microSD card to the I2S DAC, with the
four buttons controlling volume, play/pause, and the LED light mode.  With no
card / no audio it still runs as a light toy (buttons + animations keep working).

Buttons:
    VOL+  (GP14)  volume up      (auto-repeats when held)
    VOL-  (GP13)  volume down    (auto-repeats when held)
    CH    (GP15)  play / pause
    SYNC  (GP12)  cycle LED light mode  (local-only for now)

Recovery: hold the CH (play/pause) button while powering on to SKIP autostart
and drop to the REPL.  Or interrupt over serial (Ctrl-C) to stop the asyncio loop.
"""

import time
import asyncio
import machine
from machine import Pin, SPI

import config as C
from sk9822 import SK9822
from lights import Lights
from buttons import Buttons
from wavplayer import Player, HAVE_MP3


# --------------------------------------------------------------------------
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
    import os
    try:
        files = os.listdir(C.SD_MOUNT)
    except Exception:
        return []
    exts = (".wav", ".mp3") if HAVE_MP3 else (".wav",)
    # NOTE: MicroPython's str.endswith() does NOT accept a tuple (unlike CPython),
    # so check each extension individually.
    tracks = sorted(f for f in files
                    if not f.startswith(".") and any(f.lower().endswith(e) for e in exts))
    return [C.SD_MOUNT + "/" + f for f in tracks]


# --------------------------------------------------------------------------
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
            elif ev == "sync":
                lights.next_mode()
        await asyncio.sleep_ms(20)


async def led_task(player, lights):
    while True:
        lights.render(level=player.level, paused=player.paused)
        await asyncio.sleep_ms(30)


# --------------------------------------------------------------------------
async def main():
    # Overclock BEFORE any peripheral init (SPI/I2S dividers are computed from
    # the system clock at construction time).  Required for 44.1 kHz stereo MP3.
    machine.freq(C.CPU_FREQ)

    leds = SK9822(C.LED_CLK, C.LED_DAT, C.LED_COUNT)
    lights = Lights(leds)

    # boot flash: each LED a color, so you can see it's alive
    for i in range(C.LED_COUNT):
        leds.fill((0, 0, 0))
        leds.set(i, (0, 60, 120))
        leds.write()
        time.sleep_ms(120)
    leds.clear()

    btns = Buttons({
        "sync": C.BTN_SYNC,
        "vol_down": C.BTN_VOL_DN,
        "vol_up": C.BTN_VOL_UP,
        "play_pause": C.BTN_PLAY,
    })
    btns.repeat = {"vol_up", "vol_down"}

    player = Player(C.I2S_ID, C.I2S_SCK, C.I2S_WS, C.I2S_SD, C.I2S_IBUF, C.AUDIO_CHUNK)

    print("audio formats:", "WAV + MP3 (native decoder)" if HAVE_MP3 else "WAV only")
    try:
        if mount_sd():
            player.playlist = find_tracks()
            print("tracks:", player.playlist)
    except Exception as e:
        print("SD mount failed:", e)
    if not player.playlist:
        print("no tracks found -- running as light toy (buttons still work)")
        player.status = "no_files"

    try:
        await asyncio.gather(
            player.run(),
            input_task(player, lights, btns),
            led_task(player, lights),
        )
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


if _autostart_blocked():
    print("autostart skipped (CH held) -- at REPL. Run: import main; asyncio.run(main.main())")
else:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("stopped")
    finally:
        asyncio.new_event_loop()   # reset loop so the REPL is clean afterward
