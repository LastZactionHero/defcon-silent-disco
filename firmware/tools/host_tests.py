#!/usr/bin/env python3
"""Host regression suite for the badge firmware.

Runs the REAL firmware modules under tools/hostshim.py -- no hardware needed.
Every invariant that has ever caught a bug on this project lives here, plus a
full simulation of the IR receive ISR fed with the distortions we measured on
real hardware (TSOP AGC stretch, mark-length swings, 60 Hz ambient bursts).

    python3 tools/host_tests.py
"""
import json
import os
import random
import string
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hostshim import fw, clock, Pin  # noqa: E402

PASS = 0
FAIL = 0


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print("  %-58s %s %s" % (label, "ok" if ok else "FAIL", detail if not ok else ""))


# ---------------------------------------------------------------------------
print("== irsync: ISR + decoder against synthetic TSOP edges ==")
irsync = fw.irsync


class FakeRx:
    """Drives the REAL IrRx._edge/_decode/poll with scripted edge times.

    The TSOP output is active-low: a falling edge starts a mark, a rising
    edge ends it.  The ISR reads pin.value() AFTER the edge, which is how it
    tells a just-finished header MARK (pin now high) from a quiet gap.
    """

    def __init__(self):
        self.rx = irsync.IrRx.__new__(irsync.IrRx)
        self.rx._size = 400
        self.rx._buf = [0] * 400
        self.rx._n = 0
        self.rx._armed = True
        self.rx.attempts = 0
        self.rx.fails = 0
        self.rx.last_fail = None
        self.pin = Pin()
        self.rx._pin = self.pin
        self.level = 1                      # line idles high

    def edges(self, widths, start_us=1_000_000):
        """widths[0] is the first MARK; alternates mark/space."""
        t = start_us
        clock.us = t
        self.level = 0                      # falling edge: mark begins
        self.pin.value(0)
        self.rx._edge(self.pin)
        for w in widths:
            t += w
            clock.us = t
            self.level ^= 1
            self.pin.value(self.level)
            self.rx._edge(self.pin)

    def result(self):
        clock.us += 50_000                  # line quiet; poll may decode
        return self.rx.poll()


def frame_widths(tc, track, stretch=1.0, mark_scale=1.0):
    hi, lo, tr = (tc >> 8) & 0xFF, tc & 0xFF, track & 0xFF
    ck = (hi + lo + tr) & 0xFF
    bits = (hi << 24) | (lo << 16) | (tr << 8) | ck
    w = [int(irsync.HDR_MARK * stretch), int(irsync.HDR_SPACE * stretch)]
    for i in range(31, -1, -1):
        w.append(int(irsync.BIT_MARK * stretch * mark_scale))
        w.append(int((irsync.ONE_SPACE if (bits >> i) & 1 else irsync.ZERO_SPACE)
                     * stretch))
    w.append(int(irsync.STOP_MARK * stretch))
    return w


AMBIENT = [207, 152, 300, 82, 45, 60, 190, 70, 1860, 2920]  # measured 60 Hz hash

f = FakeRx(); f.edges(frame_widths(4242, 3))
check("clean frame decodes", f.result() == (4242, 3))

f = FakeRx(); f.edges(frame_widths(65535, 255))
check("max payload decodes", f.result() == (65535, 255))

f = FakeRx(); f.edges(frame_widths(999, 1, stretch=1.15))
check("TSOP +15% AGC stretch decodes", f.result() == (999, 1))

f = FakeRx(); f.edges(frame_widths(999, 1, stretch=0.9))
check("-10% squeeze decodes", f.result() == (999, 1))

f = FakeRx(); f.edges(frame_widths(777, 2, mark_scale=2.8))
check("wild mark lengths decode (data lives in the space)",
      f.result() == (777, 2))

f = FakeRx()
f.edges(AMBIENT * 3, start_us=1_000_000)          # noise burst first
clock.us += 11_700                                 # the real inter-burst gap
f.level = 1
f.edges(frame_widths(1234, 5), start_us=clock.us)  # then our frame
check("frame after 60Hz ambient bursts decodes (ISR header resync)",
      f.result() == (1234, 5))

w = frame_widths(1234, 5)
# corrupt a SPACE (marks are deliberately not validated -- data is in spaces):
# a zero-space pushed past SPACE_SPLIT flips a bit, and the checksum must
# catch the flip
zi = next(i for i in range(3, len(w), 2) if w[i] == irsync.ZERO_SPACE)
w[zi] += 900
f = FakeRx(); f.edges(w)
check("flipped bit caught by checksum", f.result() is None)

f = FakeRx(); f.edges(frame_widths(1234, 5)[:30])
check("truncated frame rejected", f.result() is None)

f = FakeRx(); f.edges(AMBIENT * 6)
check("pure ambient noise rejected", f.result() is None)

# ---------------------------------------------------------------------------
print("== wavplayer: CBR seek math ==")
wp = fw.wavplayer


def synth_mp3(seconds=60, kbps=96):
    """Valid CBR frame headers with junk payloads."""
    out = bytearray()
    frame_len = (144 * kbps * 1000) // 44100
    n = int(seconds * 44100 / 1152)
    bri = {96: 0b0111, 128: 0b1001}[kbps]
    hdr = bytes([0xFF, 0xFB, (bri << 4) | 0b0000, 0x00])
    for _ in range(n):
        out += hdr + b"\x55" * (frame_len - 4)
    return bytes(out)


class FakeFile:
    def __init__(self, b):
        self.b = b
        self.p = 0

    def read(self, n=None):
        r = self.b[self.p:self.p + n] if n else self.b[self.p:]
        self.p += len(r)
        return r

    def seek(self, p, whence=0):
        self.p = p if whence == 0 else (len(self.b) + p if whence == 2 else self.p + p)

    def tell(self):
        return self.p


blob = synth_mp3(60)
ok = True
for want in (0, 1000, 30_000, 59_000):
    pl = wp.Player.__new__(wp.Player)
    pl._base_ms = want
    ff = FakeFile(blob)
    pl._seek_into(ff, 0)
    aligned = wp.mp3_frame_at(blob, ff.p) is not None or ff.p == 0
    err = abs(ff.p * 8000.0 / 96000 - want)
    ok &= aligned and (err < 60 or want == 0)
check("seek lands frame-aligned within 60 ms", ok)

pl = wp.Player.__new__(wp.Player)
pl._base_ms = 3_000_000                # 50 min into a 1 min track
ff = FakeFile(blob)
pl._seek_into(ff, 0)
check("timecode past EOF wraps into the track",
      0 <= ff.p < len(blob) and pl._base_ms < 60_000)

# ---------------------------------------------------------------------------
print("== disco: persistence slots ==")
disco = fw.disco

tmp = tempfile.mkdtemp()
A, B = os.path.join(tmp, "a.json"), os.path.join(tmp, "b.json")
disco.PERSIST_SLOTS = (A, B)
disco.PERSIST_LEGACY = os.path.join(tmp, "legacy.json")


def write_slot(path, seq, track="x.mp3", pos=1000, vol=4, good=True):
    st = {"seq": seq, "track": track, "pos": pos, "vol": vol}
    st["ck"] = disco._state_ck(st) if good else 0xDEAD
    with open(path, "w") as fh:
        json.dump(st, fh)


write_slot(A, 5, pos=5000)
write_slot(B, 6, pos=6000)
check("newest sequence wins", disco.load_state()["pos"] == 6000)

write_slot(B, 6, pos=6000, good=False)          # torn write in newest slot
check("torn slot falls back to older slot", disco.load_state()["pos"] == 5000)

os.remove(A); os.remove(B)
with open(disco.PERSIST_LEGACY, "w") as fh:
    json.dump({"track": "y.mp3", "pos": 777, "vol": 2}, fh)
check("legacy single-file state migrates", disco.load_state()["pos"] == 777)

os.remove(disco.PERSIST_LEGACY)
check("no state at all -> None", disco.load_state() is None)

# ---------------------------------------------------------------------------
print("== disco: themes / animations invariants ==")
N = 4
W = (255, 255, 255)
viol = set()
for fn in disco.ANIMS:
    for th in disco.THEMES:
        for base in disco.BRIGHT_STEPS:
            out = [None] * N
            for slot in range(400):
                b = fn(slot, th, out, N, base)
                if not (1 <= b <= 31):
                    viol.add((fn.__name__, "bright"))
                for c in out:
                    if c is None or any(v not in (0, 255) for v in c):
                        viol.add((fn.__name__, "midrange"))
check("no mid-range channel values, brightness 1..31 (noise rule)",
      not viol, str(viol))

check("at most one white LED per theme (desaturation rule)",
      max(sum(1 for c in t if c == W) for t in disco.THEMES) <= 1)

det = True
for fn in disco.ANIMS:
    o1, o2 = [None] * N, [None] * N
    for h in [random.randrange(99999) for _ in range(30)]:
        fn(h, disco.THEMES[1], o1, N, 8)
    det &= (fn(777, disco.THEMES[1], o1, N, 8) ==
            fn(777, disco.THEMES[1], o2, N, 8)) and o1 == o2
check("animations are pure functions of slot (badge lockstep)", det)

out = [None] * N
prev = None
trans = 0
for slot in range(int(60_000 / disco.SLOT_MS)):
    disco.an_flash(slot, disco.THEMES[9], out, N, 8)
    dk = all(c == (0, 0, 0) for c in out)
    if prev is not None and dk != prev:
        trans += 1
    prev = dk
check("full-field flash rate under 1.5 Hz (photosensitivity)",
      trans / 2 / 60.0 < 1.5, "%.2f/s" % (trans / 2 / 60.0))

spark_ok = True
for slot in range(3000):
    disco.an_sparkle(slot, disco.THEMES[9], out, N, 8)
    spark_ok &= any(c != (0, 0, 0) for c in out)
check("sparkle never fully dark", spark_ok)

random.seed(11)
dup = 0
for _ in range(300):
    k = random.randint(2, 40)
    nm = sorted("".join(random.choice(string.ascii_letters) for _ in range(9))
                + ".mp3" for _ in range(k))
    looks = disco.assign_looks(nm)
    if len(set(looks)) != len(nm):
        dup += 1
check("no duplicate looks across 300 random cards", dup == 0)

check("listening indicator resolves by name",
      disco.THEME_NAMES.index("glacier") >= 0 and
      disco.ANIM_NAMES.index("breathe") >= 0)

# ---------------------------------------------------------------------------
print("== buttons: debounce / repeat / tap-vs-hold ==")
bt = fw.buttons
clock.ms = 1000


def press(b, name, down=True):
    b._pins[name].value(0 if down else 1)


b = bt.Buttons({"x": 1})
press(b, "x"); b.poll()                 # raw edge recorded
clock.ms += 5
check("bounce shorter than debounce ignored", b.poll() == [])
clock.ms += 30
check("stable press fires the event", b.poll() == ["x"])
press(b, "x", down=False); b.poll(); clock.ms += 30; b.poll()

b = bt.Buttons({"v": 2}); b.repeat = {"v"}
press(b, "v"); b.poll(); clock.ms += 30
first = b.poll()
clock.ms += b.repeat_after_ms + b.repeat_ms
evs = []
for _ in range(3):
    evs += b.poll()
    clock.ms += b.repeat_ms
check("auto-repeat fires while held", first == ["v"] and evs.count("v") >= 3)

b = bt.Buttons({"c": 3}); b.hold = {"c"}; b.hold_ms = 500
press(b, "c"); b.poll(); clock.ms += 30
check("hold-capable button silent on press", b.poll() == [])
clock.ms += 100
press(b, "c", down=False); b.poll(); clock.ms += 30
check("short tap fires on RELEASE", b.poll() == ["c"])

b = bt.Buttons({"c": 3}); b.hold = {"c"}; b.hold_ms = 500
press(b, "c"); b.poll(); clock.ms += 30; b.poll()
clock.ms += 520
check("long press fires <name>_hold at threshold", b.poll() == ["c_hold"])
press(b, "c", down=False); b.poll(); clock.ms += 30
check("hold suppresses the release tap (reset != channel change)",
      b.poll() == [])

# ---------------------------------------------------------------------------
print("== mp3player: track discovery ==")
mp3p = fw.mp3player
config = fw.config
import os as real_os  # noqa: E402

_orig_listdir = real_os.listdir
_orig_have = mp3p.HAVE_MP3
_orig_max = config.MAX_TRACKS
real_os.listdir = lambda p: ["b.mp3", "A.mp3", ".hidden.mp3", "._junk.mp3",
                             "notes.txt", "c.MP3", "d.wav", "e.mp4"]
mp3p.HAVE_MP3 = True
got = mp3p.find_tracks()
names = [p.rsplit("/", 1)[-1] for p in got]
check("filters junk, keeps mp3/wav, skips dotfiles, sorts",
      names == ["A.mp3", "b.mp3", "c.MP3", "d.wav"], str(names))
config.MAX_TRACKS = 2
names2 = [p.rsplit("/", 1)[-1] for p in mp3p.find_tracks()]
check("MAX_TRACKS caps the playlist", len(names2) == 2)
real_os.listdir = _orig_listdir
mp3p.HAVE_MP3 = _orig_have
config.MAX_TRACKS = _orig_max

# ---------------------------------------------------------------------------
print("== disco: checkpoint decision ==")
base = {"track": "a.mp3", "pos": 10_000, "vol": 4}
check("no change -> no write", not disco.should_persist(base, dict(base)))
check("volume change -> write",
      disco.should_persist(base, {**base, "vol": 5}))
check("channel change -> write",
      disco.should_persist(base, {**base, "track": "b.mp3"}))
check("small position drift -> no write",
      not disco.should_persist(base, {**base, "pos": 10_000 + 5_000}))
check("position drift past threshold -> write",
      disco.should_persist(
          base, {**base, "pos": 10_000 + disco.PERSIST_POS_DELTA_MS + 1}))
check("first write always happens", disco.should_persist({}, base))

# ---------------------------------------------------------------------------
print("== disco: battery hysteresis ==")
check("healthy voltage -> not low", not disco.batt_low(3.9, False))
check("below threshold -> low", disco.batt_low(3.4, False))
check("recovers only past hysteresis band",
      disco.batt_low(3.6, True) and not disco.batt_low(3.75, True))
check("sag near threshold does not flap",
      not disco.batt_low(3.6, False) and disco.batt_low(3.6, True))

# ---------------------------------------------------------------------------
print("== config: volume ladder ==")
config = fw.config
import math  # noqa: E402

tops = []
for s in range(1, config.VOL_STEPS + 1):
    shift = (config.VOL_TOP_ATTEN_DB // config.VOL_STEP_DB) + (config.VOL_STEPS - s)
    tops.append(max(1, config.VOL_UNITY >> shift))
check("ladder is strictly increasing", all(a < b for a, b in zip(tops, tops[1:])))
top_db = 20 * math.log10(tops[-1] / config.VOL_UNITY)
check("max step is -6 dBFS (earbud bump, clip guard)",
      abs(top_db + config.VOL_TOP_ATTEN_DB) < 0.2, "%.1f" % top_db)
check("I2S buffer floor configured", config.I2S_IBUF_MIN <= config.I2S_IBUF)

# ---------------------------------------------------------------------------
print()
print("%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
