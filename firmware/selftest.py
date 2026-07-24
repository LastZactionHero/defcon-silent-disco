"""
Standalone hardware self-test for the badge.  Run after (re)assembly/soldering
to confirm every subsystem still works, independent of the player firmware.

    import selftest; selftest.all()          # run everything
    selftest.leds(); selftest.audio(); ...   # or one at a time

Uses only blocking/synchronous APIs (the same patterns validated during
bring-up), so it's easy to reason about when something is wrong.
"""

import time
import math
import struct
from machine import Pin, I2S, PWM, SPI

import config as C


# --------------------------------------------------------------------------
def leds():
    print("[LEDs] chase LED1..LED%d then R/G/B/W hold" % C.LED_COUNT)
    from sk9822 import SK9822
    strip = SK9822(C.LED_CLK, C.LED_DAT, C.LED_COUNT, brightness=12)
    cols = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]
    for _ in range(2):
        for i in range(C.LED_COUNT):
            strip.fill((0, 0, 0))
            strip.set(i, cols[i % len(cols)])
            strip.write()
            time.sleep_ms(250)
    strip.show(cols[:C.LED_COUNT])
    time.sleep(2)
    strip.clear()
    print("       -> did each LED light in turn, then R/G/B/W?")


# --------------------------------------------------------------------------
def audio(freq=441, secs=3):
    print("[Audio] %d Hz tone for %ds on the I2S DAC" % (freq, secs))
    rate = 44100
    spc = rate // freq
    n = spc * 20
    buf = bytearray(n * 4)          # stereo 16-bit
    for i in range(n):
        v = int(12000 * math.sin(2 * math.pi * (i % spc) / spc))
        struct.pack_into("<hh", buf, i * 4, v, v)
    a = I2S(C.I2S_ID, sck=Pin(C.I2S_SCK), ws=Pin(C.I2S_WS), sd=Pin(C.I2S_SD),
            mode=I2S.TX, bits=16, format=I2S.STEREO, rate=rate, ibuf=20000)
    t0 = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t0) < secs * 1000:
        a.write(buf)
    a.deinit()
    print("       -> did you hear a steady tone on the jack?")


# --------------------------------------------------------------------------
def buttons(secs=8):
    print("[Buttons] press each button within %ds..." % secs)
    pins = {
        "SYNC": Pin(C.BTN_SYNC, Pin.IN, Pin.PULL_UP),
        "VOL-": Pin(C.BTN_VOL_DN, Pin.IN, Pin.PULL_UP),
        "VOL+": Pin(C.BTN_VOL_UP, Pin.IN, Pin.PULL_UP),
        "CH":   Pin(C.BTN_PLAY, Pin.IN, Pin.PULL_UP),
    }
    seen = set()
    last = {k: 1 for k in pins}
    t0 = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t0) < secs * 1000:
        for name, p in pins.items():
            v = p.value()
            if v == 0 and last[name] == 1:
                print("       %s pressed" % name)
                seen.add(name)
            last[name] = v
        time.sleep_ms(15)
    print("       -> saw: %s" % (", ".join(sorted(seen)) or "NONE"))


# --------------------------------------------------------------------------
def ir():
    print("[IR] 38 kHz loopback (TX GP%d -> RX GP%d)" % (C.IR_TX, C.IR_RX))
    rx = Pin(C.IR_RX, Pin.IN, Pin.PULL_UP)
    Pin(C.IR_TX, Pin.OUT, value=1)          # LED off (active-low)
    print("       RX idle (expect 1):", rx.value())
    hits = 0
    for _ in range(10):
        p = PWM(Pin(C.IR_TX))
        p.freq(38000)
        p.duty_u16(32768)
        t0 = time.ticks_us()
        low = 0
        while time.ticks_diff(time.ticks_us(), t0) < 3000:
            if rx.value() == 0:
                low += 1
        p.deinit()
        Pin(C.IR_TX, Pin.OUT, value=1)
        if low > 0:
            hits += 1
        time.sleep_ms(15)
    print("       -> %d/10 bursts detected (want 10/10)" % hits)


# --------------------------------------------------------------------------
def sd():
    print("[SD] mount + read test")
    import os
    import sdcard
    spi = SPI(C.SD_SPI_ID, baudrate=C.SD_BAUD_INIT, polarity=0, phase=0,
              sck=Pin(C.SD_SCK), mosi=Pin(C.SD_MOSI), miso=Pin(C.SD_MISO))
    cs = Pin(C.SD_CS, Pin.OUT, value=1)
    # bus recovery in case a prior run left the card mid-transfer
    for _ in range(3):
        cs.value(0)
        for _ in range(600):
            spi.write(b"\xff")
        cs.value(1)
        for _ in range(32):
            spi.write(b"\xff")
        time.sleep_ms(20)
    card = None
    for a in range(5):
        try:
            card = sdcard.SDCard(spi, cs, baudrate=C.SD_BAUD_DATA)
            break
        except Exception as e:
            print("       init try %d: %s" % (a + 1, e))
            time.sleep_ms(150)
    if card is None:
        print("       -> SD init FAILED")
        return
    print("       card OK: %d sectors (~%d MB)" % (card.sectors, card.sectors // 2048))
    os.mount(os.VfsFat(card), C.SD_MOUNT)
    files = os.listdir(C.SD_MOUNT)
    print("       files:", files)
    wavs = [f for f in files if f.lower().endswith(".wav")]
    if wavs:
        path = C.SD_MOUNT + "/" + wavs[0]
        t0 = time.ticks_ms()
        total = 0
        with open(path, "rb") as f:
            while True:
                b = f.read(2048)
                if not b:
                    break
                total += len(b)
        dt = time.ticks_diff(time.ticks_ms(), t0)
        print("       read %s: %d bytes in %d ms (%.1f KB/s)"
              % (wavs[0], total, dt, (total / dt) if dt else 0))
    os.umount(C.SD_MOUNT)
    print("       -> SD read OK")


# --------------------------------------------------------------------------
def all():
    for name, fn in (("LEDs", leds), ("Audio", audio), ("IR", ir),
                     ("SD", sd), ("Buttons", buttons)):
        print("=" * 48)
        try:
            fn()
        except Exception as e:
            print("[%s] ERROR: %s" % (name, e))
    print("=" * 48)
    print("self-test complete")
