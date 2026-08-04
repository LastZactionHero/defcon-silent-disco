"""
IR timecode sync for the silent disco badge.

Badges broadcast where they are in their track; press SYNC on a badge and it
listens instead, adopting whatever it hears.  That lets you walk up to a friend
and land on the same spot in the same mix.

Wire-level (verified against the schematic netlist):
    IR_TX  GP9  -> R22 -> D1 -> +3V3     ACTIVE LOW: pin low = LED lit
    IR_RX  GP27 <- U7.1 (TSOP4838)       ACTIVE LOW: idles high, low = carrier

Because the LED is active low, "no carrier" means driving the pin HIGH, i.e.
duty 65535 -- NOT duty 0, which would sit the LED on continuously and blind
every receiver in the room.

Frame (NEC-like pulse-distance, 38 kHz carrier):
    header   9000us mark, 4500us space          (NEC standard)
    32 bits  MSB first, each 560us mark + 560us space (0) / 1690us space (1)
    stop     560us mark
    payload  [timecode_hi][timecode_lo][track][checksum]
             timecode is in 100 ms units (16 bits -> 6553 s ~= 109 min)
             checksum is (hi + lo + track) & 0xFF

Sending blocks for ~35-60 ms depending on bit pattern.  That is deliberate: at
the default I2S_IBUF the DMA holds ~230 ms of audio, so a send fits comfortably
inside the buffer without an underrun.  Receiving does NOT block -- edges are
captured in a pin IRQ and decoded later.
"""

import time
import array
from machine import Pin, PWM, mem32

import config as C

CARRIER_HZ = 38000

# RP2040 pad control.  GPIOs come up at 4 mA drive, but the IR LED wants
# (3V3 - Vf)/R22 = (3.3 - 1.3)/150 ~= 13 mA, so at the default the pin cannot
# sink anywhere near the design current and the emitter runs at roughly a
# third of it.  Raising the pad to 12 mA lets the LED actually reach its
# design point -- worth a lot of range on a link this marginal.
#
# For reference, a TV remote drives its emitter at hundreds of mA through a
# transistor.  13 mA direct from a GPIO is a SHORT-RANGE link by construction;
# this only recovers the current the schematic already intended.
_PADS_BANK0 = 0x4001C000
DRIVE_2MA, DRIVE_4MA, DRIVE_8MA, DRIVE_12MA = 0, 1, 2, 3


def set_drive(gpio, level=DRIVE_12MA):
    """Set a pad's drive strength (survives the pin being handed to PWM)."""
    addr = _PADS_BANK0 + 0x04 + (gpio * 4)
    mem32[addr] = (mem32[addr] & ~(3 << 4)) | (level << 4)


def get_drive(gpio):
    return (mem32[_PADS_BANK0 + 0x04 + (gpio * 4)] >> 4) & 3

# NEC-standard timings.  Switched from a homebrew 4500/400/1200 scheme because
# the link proved marginal: at 20 cm the TSOP returned a 2477/3491 header
# (~40% short) with marks stretched and spaces squashed -- classic weak-signal
# AGC strain.  Every TSOP4838 is characterised against NEC, and its longer
# bursts put ~40% more energy per bit into the detector, which is exactly what
# a weak emitter needs.  Frame time goes ~35-60 ms -> ~68 ms, still well inside
# the 181 ms I2S buffer.
HDR_MARK = 9000
HDR_SPACE = 4500
BIT_MARK = 560
ZERO_SPACE = 560
ONE_SPACE = 1690
STOP_MARK = 560

_DUTY_CARRIER = 32768      # ~50% at 38 kHz
_DUTY_OFF = 65535          # pin held high -> LED dark (active low)

# Edges needed for a whole frame: 2 header + 32*2 bits + 1 closing the stop mark
_FRAME_EDGES = 2 + 64 + 1

# Pulse matching tolerance.  Generous because TSOP AGC stretches and shortens
# bursts, especially the first one after a quiet period.
_TOL = 0.35
_TOL_FLOOR = 180           # us, so the 400us pulses still have room

# Bit-decision limits.  Wide on purpose -- see IrRx._bits().  The gap between
# a zero space (~465 measured) and a one space (~1258 measured) is enormous, so
# a midpoint split is far more robust than matching either one closely.
# Mark length is NOT validated tightly on purpose.  In pulse-distance encoding
# the data is carried entirely by the SPACE; the mark is just a delimiter.
# Measured marks swing from ~290 to ~1762 us depending on the preceding space
# (TSOP AGC recovery), so a tight window rejects otherwise perfect frames -- we
# lost a 31-of-32-correct frame to exactly that.  Only sanity-check it.
MARK_MIN = 150
MARK_MAX = 2600
ZERO_SPACE_MIN = 200
SPACE_SPLIT = 1100         # midpoint between 560 and 1690
ONE_SPACE_MAX = 3000

# Quiet gap that marks a frame boundary.  Longer than any intra-frame space
# (1690 us) and than the header mark (9000 us) is NOT -- the header is a MARK,
# so the gap test never splits a frame mid-flight.
GAP_US = 12000
# Header-mark window.  A LOW of about HDR_MARK that has just ended is
# unambiguously the start of our frame -- ambient bursts are far shorter, and a
# quiet gap is HIGH, not LOW, so reading the pin tells the two apart.
HDR_LO_US = 7000
HDR_HI_US = 11500
# How long the line must be idle before we try to decode.  Ambient bursts
# arrive every ~16.7 ms, so this has to be comfortably under that or we would
# never get a quiet window at all.
QUIET_US = 7000


def _match(actual, expect):
    return abs(actual - expect) <= max(_TOL_FLOOR, int(expect * _TOL))


class IrTx:
    """Carrier generator.

    The PWM only exists for the duration of a send.  Between sends the pin is a
    plain GPIO driven HIGH (LED dark, since the LED is active low).

    That is deliberate.  Leaving a 38 kHz PWM parked at duty 65535 is NOT
    reliably a constant high -- a one-cycle glitch per period is still a 38 kHz
    pulse train, and 38 kHz is precisely what the TSOP4838 sitting centimetres
    away is tuned to demodulate.  It would see a permanent carrier, hold its
    output active, and machine-gun the receive IRQ forever.
    """

    def __init__(self, pin=None):
        self._pin_no = C.IR_TX if pin is None else pin
        self._pwm = None
        self.idle()

    def idle(self):
        if self._pwm is not None:
            try:
                self._pwm.deinit()
            except Exception:
                pass
            self._pwm = None
        Pin(self._pin_no, Pin.OUT, value=1)     # active low -> 1 = LED dark

    def deinit(self):
        self.idle()

    def send(self, timecode_100ms, track):
        """Blocking send of one frame (~35-60 ms)."""
        hi = (timecode_100ms >> 8) & 0xFF
        lo = timecode_100ms & 0xFF
        tr = track & 0xFF
        ck = (hi + lo + tr) & 0xFF
        bits = (hi << 24) | (lo << 16) | (tr << 8) | ck

        p = PWM(Pin(self._pin_no))
        p.freq(CARRIER_HZ)
        set_drive(self._pin_no, DRIVE_12MA)   # AFTER PWM claims the pin
        self._pwm = p
        try:
            sleep = time.sleep_us
            p.duty_u16(_DUTY_CARRIER); sleep(HDR_MARK)
            p.duty_u16(_DUTY_OFF);     sleep(HDR_SPACE)
            for i in range(31, -1, -1):
                p.duty_u16(_DUTY_CARRIER); sleep(BIT_MARK)
                p.duty_u16(_DUTY_OFF)
                sleep(ONE_SPACE if (bits >> i) & 1 else ZERO_SPACE)
            p.duty_u16(_DUTY_CARRIER); sleep(STOP_MARK)
        finally:
            self.idle()                          # tears the PWM back down


class IrRx:
    """Edge-capture receiver.  Never blocks; call poll() from a task.

    The IRQ is only installed while we are actually listening.  Ambient IR --
    sunlight, fluorescent lighting, other badges, and above all our OWN
    transmitter a couple of centimetres away -- generates edges constantly, and
    there is no reason to take an interrupt for any of it during normal
    playback when nothing ever reads the buffer.
    """

    def __init__(self, pin=None, size=256):
        self._size = size
        self._buf = array.array("i", [0] * size)
        self._n = 0
        self._armed = False
        # Diagnostics.  poll() clears the capture buffer on EVERY decode
        # attempt, including failures -- so without stashing a copy here, a
        # frame that arrives and fails to decode is indistinguishable from no
        # frame at all.  That cost us a long detour chasing aiming and then the
        # transmitter, when reception had been working all along.
        self.attempts = 0          # complete frames seen and tried
        self.fails = 0             # ...of which did not decode
        self.last_fail = None      # pulse widths of the most recent failure
        self._pin = Pin(C.IR_RX if pin is None else pin, Pin.IN, Pin.PULL_UP)

    # Kept allocation-free: writes into a preallocated array and an int.
    def _edge(self, pin):
        t = time.ticks_us()
        n = self._n
        if n:
            gap = time.ticks_diff(t, self._buf[n - 1])
            # Hard sync on the header MARK.  If a ~9 ms LOW just ended (pin is
            # high now, so the gap we just measured was low), that was our
            # header -- restart the capture from it and drop everything before.
            # Ambient IR bursts are much shorter, and the quiet BETWEEN bursts
            # is high rather than low, so neither can be mistaken for it.
            #
            # Without this the receiver never locked: room lighting fires ~660
            # edges/sec in bursts every 16.7 ms, leaving only ~11.7 ms of quiet,
            # so a plain gap threshold cannot be set below the 9 ms header mark
            # without also splitting frames in half.
            if n < _FRAME_EDGES and HDR_LO_US < gap < HDR_HI_US and pin.value():
                self._buf[0] = self._buf[n - 1]
                self._buf[1] = t
                self._n = 2
                return
            if n < _FRAME_EDGES and gap > GAP_US:
                n = 0
        if n < self._size:
            self._buf[n] = t
            self._n = n + 1

    def start(self):
        """Arm the capture IRQ and drop anything stale."""
        self._n = 0
        self.attempts = 0
        self.fails = 0
        self.last_fail = None
        if not self._armed:
            # hard=True is essential, not an optimisation.  MicroPython
            # defaults to a SOFT irq, which is merely scheduled to run between
            # bytecodes -- fine on an idle board, useless under load.  With MP3
            # decode, I2S DMA and LED bit-banging running, scheduling slipped
            # far enough to miss edges outright and mistime the rest: the same
            # receiver decoded 5/5 frames with audio stopped and 0 with it
            # playing.  The handler is allocation-free, so a real ISR is safe.
            self._pin.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING,
                          handler=self._edge, hard=True)
            self._armed = True

    def reset(self):
        self._n = 0

    def stop(self):
        if self._armed:
            try:
                self._pin.irq(handler=None)
            except Exception:
                pass
            self._armed = False
        self._n = 0

    def poll(self):
        """Return (timecode_100ms, track) once a complete frame has landed.

        Waits for the line to go quiet before decoding, so we never try to
        parse a frame that is still arriving.
        """
        n = self._n
        if n < _FRAME_EDGES:
            if n >= self._size:          # buffer full of noise -- start over
                self._n = 0
            return None
        if (time.ticks_diff(time.ticks_us(), self._buf[n - 1]) < QUIET_US
                and n < self._size):
            return None                  # still receiving
        self.attempts += 1
        res = self._decode(n)
        if res is None:
            self.fails += 1
            self.last_fail = self.dump(40)   # snapshot BEFORE we clear
        self._n = 0
        return res

    def dump(self, limit=24):
        """Captured pulse widths, for diagnosing a receive that will not decode.

        The decoder has only ever been proven against synthetic frames; real
        TSOP4838 output is AGC-shaped and the burst lengths come back stretched
        or squeezed.  Seeing the actual microseconds is the only way to tell
        "nothing arrived" from "arrived but the constants are wrong".
        """
        n = self._n
        if n < 2:
            return "edges=%d (nothing captured)" % n
        d = []
        for i in range(min(n - 1, limit)):
            d.append(time.ticks_diff(self._buf[i + 1], self._buf[i]))
        return "edges=%d first widths(us)=%s" % (n, d)

    def _decode(self, n):
        b = self._buf
        # Scan for the header rather than assuming edge 0 is the frame start --
        # ambient IR (sunlight, other badges, fluorescent lighting) routinely
        # puts junk edges in front of the real thing.
        last_start = n - _FRAME_EDGES
        for s in range(last_start + 1):
            if not _match(time.ticks_diff(b[s + 1], b[s]), HDR_MARK):
                continue
            if not _match(time.ticks_diff(b[s + 2], b[s + 1]), HDR_SPACE):
                continue
            val = self._bits(b, s + 2)
            if val is None:
                continue
            hi = (val >> 24) & 0xFF
            lo = (val >> 16) & 0xFF
            tr = (val >> 8) & 0xFF
            ck = val & 0xFF
            if ((hi + lo + tr) & 0xFF) != ck:
                continue
            return ((hi << 8) | lo, tr)
        return None

    def _bits(self, b, idx):
        """Decode 32 pulse-distance bits.

        Deliberately threshold-based rather than template-matching.  Measured
        TSOP4838 output comes back ~15% long (400us marks arrive as ~455,
        1200us spaces as ~1258) and the AGC distorts individual pulses further
        at close range.  Matching both the mark and the space against fixed
        templates rejected real frames.  Instead: accept any plausible mark,
        and split zero from one at the midpoint, which is what the encoding
        actually needs.
        """
        val = 0
        for _ in range(32):
            mark = time.ticks_diff(b[idx + 1], b[idx])
            space = time.ticks_diff(b[idx + 2], b[idx + 1])
            if mark < MARK_MIN or mark > MARK_MAX:
                return None
            if space > SPACE_SPLIT:
                if space > ONE_SPACE_MAX:
                    return None
                val = (val << 1) | 1
            elif space >= ZERO_SPACE_MIN:
                val = val << 1
            else:
                return None
            idx += 2
        return val
