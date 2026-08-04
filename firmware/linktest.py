"""
Standalone IR link test -- no audio, no LEDs, no SD.

Built because debugging the link through the full disco program was slow and
fragile: a 10 s broadcast period, a 25 s sync window, and every diagnostic
competing with the decoder for CPU.  This strips everything else away.

Two roles:

    beacon()   transmit a frame every second, forever.  Set a badge's main.py
               to call this and it beacons from power-on with no host attached
               -- which is the robust way to do it, since driving a beacon over
               the REPL kept wedging the board.

    scope()    listen and report what each capture looks like, so you can move
               the badges and watch link quality change live.

Typical use: one badge booting into beacon(), the other running scope() over
USB while you vary the distance.
"""

import time
import irsync


def beacon(period_ms=1000, quiet=False):
    """Transmit forever.  Never returns."""
    tx = irsync.IrTx()
    print("beacon: carrier=%d timings=%d/%d/%d/%d drive=%d"
          % (irsync.CARRIER_HZ, irsync.HDR_MARK, irsync.BIT_MARK,
             irsync.ZERO_SPACE, irsync.ONE_SPACE, irsync.get_drive(9)))
    n = 0
    while True:
        try:
            tx.send(1000 + (n % 100), 0)
            n += 1
            if not quiet and (n % 10) == 0:
                print("beacon: %d frames sent" % n)
        except Exception as e:
            print("beacon: send failed:", e)
        time.sleep_ms(period_ms)


def _hdr_of(dump):
    """Pull the first two pulse widths out of a dump string."""
    try:
        nums = dump.split("=[")[1].rstrip("]").split(", ")
        return int(nums[0]), int(nums[1])
    except Exception:
        return None, None


def scope(secs=90):
    """Listen and classify every capture.  Returns (decoded, failed)."""
    rx = irsync.IrRx()
    rx.start()
    print("scope: listening %ds  (expecting hdr ~%d/%d)"
          % (secs, irsync.HDR_MARK, irsync.HDR_SPACE))
    ok = 0
    last_fail = 0
    t0 = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t0) < secs * 1000:
        got = rx.poll()
        if got:
            ok += 1
            print("  DECODED %s   <-- LINK GOOD" % (got,))
        elif rx.fails != last_fail:
            last_fail = rx.fails
            h1, h2 = _hdr_of(rx.last_fail or "")
            if h1 is None:
                print("  fail #%d (no widths)" % rx.fails)
            else:
                # Is the header even close?  That separates "our frame arrived
                # but is distorted" from "this is just ambient noise".
                near = (irsync.HDR_MARK * 0.6 < h1 < irsync.HDR_MARK * 1.4 and
                        irsync.HDR_SPACE * 0.6 < h2 < irsync.HDR_SPACE * 1.4)
                print("  fail #%d hdr=%d/%d %s"
                      % (rx.fails, h1, h2, "OUR FRAME (distorted)" if near
                         else "noise/not ours"))
        time.sleep_ms(25)
    rx.stop()
    print("scope: %d decoded, %d failed" % (ok, rx.fails))
    return ok, rx.fails


def raw(secs=20):
    """Dump full pulse widths of the next few captures, for tuning."""
    rx = irsync.IrRx()
    rx.start()
    print("raw: %ds" % secs)
    seen = 0
    last = 0
    t0 = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t0) < secs * 1000 and seen < 4:
        got = rx.poll()
        if got:
            print("  DECODED", got)
            seen += 1
        elif rx.fails != last:
            last = rx.fails
            print(" ", rx.last_fail)
            seen += 1
        time.sleep_ms(25)
    rx.stop()
