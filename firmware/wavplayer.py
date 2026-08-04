"""
Asyncio audio player: streams 16-bit PCM to the I2S DAC with software volume,
play/pause, a live peak level (VU), and playlist auto-advance.

Plays .wav always, and .mp3 when the native `mp3` decoder module is built into
the firmware (see cmodules/mp3 + tools/build_firmware.sh).  On stock MicroPython
(no `mp3` module) it transparently falls back to WAV-only.

Both paths converge on _emit(): apply software volume, compute the VU peak, pick
I2S.MONO/STEREO from the channel count, and write with StreamWriter backpressure.
"""

import gc
import time
import asyncio
from machine import I2S, Pin

from wavparse import parse_wav, WavError
from dsp import pcm16_to_lsbj32
import config as C

try:
    import mp3
except ImportError:
    mp3 = None
HAVE_MP3 = mp3 is not None

# Set True to trace why a track started/stopped.  Prints once per track, never
# inside the decode loop, so it cannot itself cause an underrun.
DEBUG = False


# MPEG1 Layer III bitrate table, indexed by the header's 4-bit bitrate field.
_MP3_BR_V1L3 = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
_MP3_SR_V1 = (44100, 48000, 32000)


def mp3_frame_at(buf, i):
    """(bitrate_bps, sample_rate, frame_bytes) for an MPEG1-L3 header at buf[i].

    Returns None if buf[i] is not a plausible frame header.  Only MPEG1 Layer
    III is recognised, which is what the badge's content is; anything else is
    treated as "no frame here" and the caller falls back to a linear guess.
    """
    if i + 4 > len(buf):
        return None
    if buf[i] != 0xFF or (buf[i + 1] & 0xE0) != 0xE0:
        return None
    if ((buf[i + 1] >> 3) & 3) != 3:        # MPEG version must be 1
        return None
    if ((buf[i + 1] >> 1) & 3) != 1:        # layer must be III
        return None
    bri = (buf[i + 2] >> 4) & 15
    sri = (buf[i + 2] >> 2) & 3
    if bri == 0 or bri == 15 or sri == 3:
        return None
    br = _MP3_BR_V1L3[bri] * 1000
    sr = _MP3_SR_V1[sri]
    pad = (buf[i + 2] >> 1) & 1
    return br, sr, (144 * br) // sr + pad


class Player:
    def __init__(self, i2s_id, sck, ws, sd, ibuf, chunk):
        self._id = i2s_id
        self._sck = sck
        self._ws = ws
        self._sd = sd
        self._ibuf = ibuf
        self._chunk = chunk

        self.audio = None
        self._swriter = None
        self._cur_rate = None
        self._cur_fmt = None
        # Allocation ORDER matters more than total free memory here.  The GC is
        # mark-and-sweep and does NOT compact, so once the heap is carved up no
        # contiguous 80 KB run exists no matter how much is free -- we saw the
        # I2S buffer fail with ~155 KB available.  So: claim the biggest block
        # first, while the heap is still clean, then the smaller one.
        gc.collect()
        try:
            self._ensure_i2s(44100, I2S.STEREO)     # 80 KB, the hard one
        except Exception as e:
            print("I2S pre-init failed:", e)        # _emit will retry later

        need = 0
        if mp3 is not None:
            need = (mp3.MAX_FRAME_BYTES >> 1) << 2
        need = max(need, (chunk >> 1) << 2)
        self._out32 = bytearray(need)
        self._mv32 = memoryview(self._out32)

        self.volume = 128        # 0..VOL_UNITY (32768 == unity); 128 == -48 dBFS
        self.level = 0           # recent output peak 0..32767 (for VU lights)
        self.playlist = []
        self.index = 0
        self.status = "idle"     # idle | playing | paused | no_files | error
        self.errors = 0          # consecutive failed track attempts

        self._run = asyncio.Event()
        self._run.set()          # playing by default
        self._skip = False
        self._stop = False
        self._jump = None        # where to go after the current track ends

        # Silent-disco additions.  All default to the old behaviour so the
        # plain player is unaffected.
        self.repeat_track = False   # True: a track ending replays itself
        self.seek_ms = 0            # ONE-SHOT: where the next track start begins
        self.seek_ref = None        # ticks_ms when seek_ms was CORRECT; the
                                    # elapsed time until the seek actually runs
                                    # is added, so restart latency (skip, file
                                    # open, SD reads) does not become sync lag
        self._base_ms = 0           # offset the current playback started at
        self._played_ms = 0.0       # decoded audio time since that start

    # -- state for the input/led tasks ------------------------------------
    @property
    def paused(self):
        return not self._run.is_set()

    @property
    def pos_ms(self):
        """Playback position in the current track, in ms.

        Counted from decoded audio, so it does NOT include the I2S buffer
        latency (~230 ms at the default I2S_IBUF) -- what you hear lags this by
        roughly that much.  Good enough for IR sync between badges, since every
        badge has the same lag.
        """
        return self._base_ms + int(self._played_ms)

    def toggle_pause(self):
        if self._run.is_set():
            self._run.clear()
            self.status = "paused"
        else:
            self._run.set()
            self.status = "playing"

    def set_volume_step(self, step, steps):
        """Map a button step to a volume, logarithmically.

        Loudness is perceived in dB, so the old linear map (step/steps * unity)
        crowded every step into the top 18 dB and felt like the buttons did
        nothing.  Each step here is VOL_STEP_DB (6 dB == one halving), with the
        top step held VOL_TOP_ATTEN_DB below full scale to stay under the
        analog clipping ceiling.
        """
        if steps <= 0 or step <= 0:
            self.volume = 0
            return
        shift = (C.VOL_TOP_ATTEN_DB // C.VOL_STEP_DB) + (steps - step)
        self.volume = max(1, C.VOL_UNITY >> shift)

    def next_track(self):
        self._jump = 1
        self._skip = True
        self._run.set()          # unpause so the loop notices the skip

    def prev_track(self):
        self._jump = -1
        self._skip = True
        self._run.set()

    def goto_track(self, i):
        """Jump to absolute playlist index i, interrupting the current track."""
        if self.playlist:
            self._jump = i - (self.index % len(self.playlist))
        self._skip = True
        self._run.set()

    def restart_track(self):
        self._jump = 0
        self._skip = True
        self._run.set()

    def stop(self):
        self._stop = True
        self._run.set()

    # -- I2S lifecycle -----------------------------------------------------
    def _ensure_i2s(self, rate, fmt):
        if self.audio is not None and self._cur_rate == rate and self._cur_fmt == fmt:
            return
        if self.audio is not None:
            self.audio.deinit()
        gc.collect()            # 80 KB wants a contiguous block; compact first
        self.audio = I2S(
            self._id,
            sck=Pin(self._sck), ws=Pin(self._ws), sd=Pin(self._sd),
            mode=I2S.TX, bits=C.I2S_BITS, format=fmt, rate=rate, ibuf=self._ibuf,
        )
        self._swriter = asyncio.StreamWriter(self.audio)
        self._cur_rate = rate
        self._cur_fmt = fmt

    def deinit(self):
        if self.audio is not None:
            try:
                self.audio.deinit()
            except Exception:
                pass
            self.audio = None
            self._swriter = None
            self._cur_rate = None
            self._cur_fmt = None

    # -- shared PCM -> I2S emit -------------------------------------------
    def _ensure_out32(self, nsamp):
        """Output buffer holding nsamp LSBJ-reframed 32-bit words."""
        need = nsamp << 2
        if self._out32 is None or len(self._out32) < need:
            self._out32 = bytearray(need)
            self._mv32 = memoryview(self._out32)
        return self._mv32

    async def _emit(self, buf, nbytes, rate, ch):
        """Volume-scale + reframe `nbytes` of PCM in `buf`, then stream it.
        Returns False if playback of the current track should stop."""
        await self._run.wait()                 # blocks (0% CPU) while paused
        if self._stop or self._skip:
            return False
        fmt = I2S.MONO if ch == 1 else I2S.STEREO
        self._ensure_i2s(rate, fmt)
        nsamp = nbytes >> 1
        mv = self._ensure_out32(nsamp)
        # Volume, LSBJ reframing and the VU peak all happen in one pass.
        self.level = pcm16_to_lsbj32(buf, self._out32, nsamp, self.volume)
        self._played_ms += (nsamp // ch) * 1000.0 / rate
        self._swriter.write(mv[:nsamp << 2])
        await self._swriter.drain()            # backpressure; yields to other tasks
        return True

    # -- WAV path ----------------------------------------------------------
    async def _play_wav_file(self, path):
        info = parse_wav(path)
        ch = info["num_channels"]
        block = info["block_align"]
        rate = info["sample_rate"]
        chunk_bytes = self._chunk - (self._chunk % block)
        if chunk_bytes <= 0:
            chunk_bytes = block
        buf = bytearray(chunk_bytes)
        mv = memoryview(buf)

        self.status = "playing"
        with open(path, "rb") as f:
            f.seek(info["data_offset"])
            remaining = info["data_size"]
            while remaining > 0 and not self._stop:
                to_read = chunk_bytes if remaining >= chunk_bytes else remaining
                to_read -= to_read % block
                if to_read <= 0:
                    break
                nread = f.readinto(mv[:to_read])
                if not nread:
                    break
                remaining -= nread
                nread -= nread % block          # drop any partial trailing frame
                if nread == 0:
                    break
                if not await self._emit(buf, nread, rate, ch):
                    break
        self.level = 0

    def _seek_into(self, f, audio_start):
        """Position `f` at roughly self._base_ms into the MP3, frame-aligned.

        Assumes CONSTANT BITRATE, which is what byte-offset seeking needs: the
        offset is just time x bitrate.  A VBR file would land in the wrong
        place (harmless -- it still plays, just from the wrong spot), so keep
        the card CBR.  After the linear guess we scan forward for a real frame
        header; the decoder can resync on its own, but landing mid-frame makes
        an audible splat.
        """
        want_ms = self._base_ms
        if want_ms <= 0:
            return
        probe = f.read(4096)
        info = None
        for k in range(len(probe) - 4):
            info = mp3_frame_at(probe, k)
            if info:
                break
        if not info:
            f.seek(audio_start)          # unrecognised: just play from the top
            self._base_ms = 0
            return
        br = info[0]
        # Wrap into this track's length rather than seeking off the end.  A
        # neighbour 40 min into a 60 min mix will hand us a timecode past the
        # end of a 9 min one; without this we would seek past EOF, hit
        # immediate end-of-track, and loop-restart forever.
        f.seek(0, 2)
        span = f.tell() - audio_start
        dur_ms = int(span * 8000.0 / br)
        if dur_ms > 0:
            want_ms %= dur_ms
            self._base_ms = want_ms
        if want_ms <= 0:
            f.seek(audio_start)
            return
        target = audio_start + int(want_ms * br / 8000.0)
        f.seek(target)
        win = f.read(4096)
        for k in range(len(win) - 4):
            if mp3_frame_at(win, k):
                f.seek(target + k)
                return
        f.seek(target)                   # no header found; let the decoder resync

    # -- MP3 path (native decoder) ----------------------------------------
    async def _play_mp3_file(self, path):
        if mp3 is None:
            raise WavError("mp3 decoder not built into firmware")
        dec = mp3.Decoder()
        IN = bytearray(8192)
        mvIN = memoryview(IN)
        cap = len(IN)
        OUT = bytearray(mp3.MAX_FRAME_BYTES)
        pos = 0        # start of unconsumed data in IN
        have = 0       # end of valid data in IN
        eof = False
        # The decoder occasionally false-syncs and returns a frame with a bogus
        # (rate, ch).  Reconfiguring I2S on every such frame dumps the DMA
        # buffer and glitches badly, so lock the format to the first value seen
        # on two consecutive frames and DROP any frame that disagrees.
        fmt_lock = None   # (rate, ch) once locked
        fmt_prev = None   # previous frame's (rate, ch) before locking

        self.status = "playing"
        n_emit = 0
        n_dec = 0
        why = "?"
        audio_start = 0      # bound before the try so the finally cannot NameError
        try:
            with open(path, "rb") as f:
                # skip an ID3v2 tag if present (syncsafe size in header bytes 6..9)
                head = f.read(10)
                if len(head) == 10 and head[0:3] == b"ID3":
                    audio_start = 10 + (((head[6] & 0x7F) << 21) |
                                        ((head[7] & 0x7F) << 14) |
                                        ((head[8] & 0x7F) << 7) |
                                        (head[9] & 0x7F))
                else:
                    audio_start = 0
                f.seek(audio_start)
                self._seek_into(f, audio_start)

                # Test _skip here, not only inside _emit().  _emit is the only
                # other place it was checked, and it is not reached on every
                # iteration: frames dropped by the format-lock guard `continue`
                # straight past it, and a decode that yields produced==0 with
                # consumed>0 loops without ever calling it.  In those states a
                # next-track press was silently ignored until something else
                # happened to nudge the loop.  _play_track() clears _skip before
                # we get here, so this cannot exit on a stale flag.
                while not (self._stop or self._skip):
                    avail = have - pos
                    if avail < 2048 and not eof:
                        # make room at the end if we're near the top (rare copy)
                        if have > cap - 512 and pos > 0:
                            IN[0:avail] = IN[pos:have]
                            pos = 0
                            have = avail
                        n = f.readinto(mvIN[have:])
                        if n:
                            have += n
                        else:
                            eof = True
                        avail = have - pos
                    if avail <= 0 and eof:
                        why = "eof"
                        break

                    consumed, produced, rate, ch = dec.decode(mvIN[pos:have], OUT)
                    n_dec += 1
                    pos += consumed
                    if produced > 0:
                        if fmt_lock is None:
                            if fmt_prev == (rate, ch):
                                fmt_lock = (rate, ch)
                            else:
                                fmt_prev = (rate, ch)
                                continue     # don't emit until format is stable
                        elif (rate, ch) != fmt_lock:
                            continue         # false-sync frame: drop it
                        if not await self._emit(OUT, produced, rate, ch):
                            why = "skip" if self._skip else "stop"
                            break
                        n_emit += 1
                    elif consumed == 0:
                        # no progress: need more data, else give up
                        if eof:
                            why = "no-progress-eof"
                            break
                        if pos == 0 and have == cap:
                            why = "full-buffer-no-frame"
                            break
                else:
                    why = "skip-loop" if self._skip else "stopped"
        finally:
            dec.deinit()
            if DEBUG:
                print("[mp3] %s base=%dms start=%d decodes=%d emits=%d lock=%s -> %s"
                      % (path.rsplit("/", 1)[-1], self._base_ms, audio_start,
                         n_dec, n_emit, fmt_lock, why))
        self.level = 0

    async def _play_track(self, path):
        self._skip = False
        # seek_ms is one-shot: consume it here so a natural loop (or the next
        # track) starts from the top rather than repeating the seek forever.
        # If seek_ref is set, seek_ms was correct at that instant -- add the
        # wall time spent getting here (track teardown, file open, SD traffic),
        # which measured in the hundreds of ms and was audible as sync lag.
        base = self.seek_ms
        if base > 0 and self.seek_ref is not None:
            base += time.ticks_diff(time.ticks_ms(), self.seek_ref)
        self._base_ms = base
        self.seek_ms = 0
        self.seek_ref = None
        self._played_ms = 0.0
        if path.lower().endswith(".mp3"):
            await self._play_mp3_file(path)
        else:
            await self._play_wav_file(path)

    async def run(self):
        """Main playback loop: play the playlist in order, forever."""
        while not self._stop:
            if not self.playlist:
                self.status = "no_files"
                await asyncio.sleep_ms(250)
                continue
            path = self.playlist[self.index % len(self.playlist)]
            try:
                await self._play_track(path)
                self.errors = 0          # a clean run clears the failure streak
            except WavError as e:
                print("skip (bad file)", path, "-", e)
                await asyncio.sleep_ms(50)
            except OSError as e:
                print("io error", path, "-", e)
                self.status = "error"
                await asyncio.sleep_ms(150)
            except Exception as e:
                print("play error", path, "-", e)
                self.errors += 1
                # Back off as failures repeat.  The old flat 150 ms retry
                # spammed the console hundreds of times a second and made the
                # real first error impossible to find.
                await asyncio.sleep_ms(min(2000, 150 * self.errors))
            # A track ending naturally advances by one -- or replays itself when
            # repeat_track is set (silent disco: the channel stays put).
            # next/prev/restart_track override that for this transition only.
            natural = 0 if self.repeat_track else 1
            jump = natural if self._jump is None else self._jump
            self._jump = None
            self.index = (self.index + jump) % len(self.playlist)
        self.deinit()
