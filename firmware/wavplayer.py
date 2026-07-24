"""
Asyncio audio player: streams 16-bit PCM to the I2S DAC with software volume,
play/pause, a live peak level (VU), and playlist auto-advance.

Plays .wav always, and .mp3 when the native `mp3` decoder module is built into
the firmware (see cmodules/mp3 + tools/build_firmware.sh).  On stock MicroPython
(no `mp3` module) it transparently falls back to WAV-only.

Both paths converge on _emit(): apply software volume, compute the VU peak, pick
I2S.MONO/STEREO from the channel count, and write with StreamWriter backpressure.
"""

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
        self._out32 = None       # LSBJ-reframed output, 4 bytes per sample
        self._mv32 = None

        self.volume = 128        # 0..VOL_UNITY (32768 == unity); 128 == -48 dBFS
        self.level = 0           # recent output peak 0..32767 (for VU lights)
        self.playlist = []
        self.index = 0
        self.status = "idle"     # idle | playing | paused | no_files | error

        self._run = asyncio.Event()
        self._run.set()          # playing by default
        self._skip = False
        self._stop = False

    # -- state for the input/led tasks ------------------------------------
    @property
    def paused(self):
        return not self._run.is_set()

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
        self._skip = True
        self._run.set()          # unpause so the loop notices the skip

    def stop(self):
        self._stop = True
        self._run.set()

    # -- I2S lifecycle -----------------------------------------------------
    def _ensure_i2s(self, rate, fmt):
        if self.audio is not None and self._cur_rate == rate and self._cur_fmt == fmt:
            return
        if self.audio is not None:
            self.audio.deinit()
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
        try:
            with open(path, "rb") as f:
                # skip an ID3v2 tag if present (syncsafe size in header bytes 6..9)
                head = f.read(10)
                if len(head) == 10 and head[0:3] == b"ID3":
                    sz = ((head[6] & 0x7F) << 21) | ((head[7] & 0x7F) << 14) | \
                         ((head[8] & 0x7F) << 7) | (head[9] & 0x7F)
                    f.seek(10 + sz)
                else:
                    f.seek(0)

                while not self._stop:
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
                        break

                    consumed, produced, rate, ch = dec.decode(mvIN[pos:have], OUT)
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
                            break
                    elif consumed == 0:
                        # no progress: need more data, else give up
                        if eof:
                            break
                        if pos == 0 and have == cap:
                            break                # full buffer, no decodable frame
        finally:
            dec.deinit()
        self.level = 0

    async def _play_track(self, path):
        self._skip = False
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
            except WavError as e:
                print("skip (bad file)", path, "-", e)
                await asyncio.sleep_ms(50)
            except OSError as e:
                print("io error", path, "-", e)
                self.status = "error"
                await asyncio.sleep_ms(150)
            except Exception as e:
                print("play error", path, "-", e)
                await asyncio.sleep_ms(150)
            self.index = (self.index + 1) % len(self.playlist)
        self.deinit()
