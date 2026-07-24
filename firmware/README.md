# DEFCON Silent-Disco Badge — Firmware

MicroPython firmware for the RP2040 badge: a WAV player streamed from microSD to
the I2S DAC, with the four buttons driving volume / play-pause / LED modes.

> **Read [`BADGE.md`](BADGE.md) first** — it documents the hardware quirks this
> code depends on (notably the **swapped LED clock/data pins** and the **patched
> SD driver**), all verified on real hardware during bring-up.

## What it does

- Plays 16-bit PCM **WAV** files from the SD card, in order, looping.
- **VOL+ / VOL−** (GP14 / GP13): software volume, 8 steps, auto-repeat when held.
- **CH** (GP15): play / pause.
- **SYNC** (GP12): cycle the LED light mode (VU meter → rainbow → pulse → solid).
  *(Local-only for now — the IR sync channel isn't wired in yet.)*
- LEDs react to the audio (VU mode) and show a volume overlay when you change it.
- With **no card / no files** it still runs as a light toy — buttons keep working.

## Audio: WAV out of the box, MP3 with a custom firmware

**WAV (stock MicroPython).** Pre-decode songs to 16-bit PCM WAV on a computer.
Keep files **mono, 16 kHz** (32 KB/s — under the ~45–51 KB/s SD read ceiling); the
badge up-mixes to stereo via `I2S.MONO`.

**MP3 (native, optional).** The RP2040 decodes MP3 in fixed-point C, but 44.1 kHz
stereo needs the badge's 250 MHz overclock (`CPU_FREQ` in `config.py` — decode
alone is ~94% of a core at stock 125 MHz). The
`cmodules/mp3` module (Helix/picomp3lib) adds a real decoder; build it into a
custom firmware with `tools/build_firmware.sh` (see [Native MP3](#native-mp3-optional)).
MP3 *lowers* SD load (128 kbps ≈ 16 KB/s) and shrinks files ~10×. The player picks
MP3 automatically when the module is present and `.mp3` files are on the card.
See [`BADGE.md`](BADGE.md) for the full rationale.

## Prepare a card

```sh
# from this dir; needs ffmpeg
tools/prepare_card.sh /Volumes/YOUR_SD  song1.mp3 song2.flac
# higher quality (riskier vs the SD read ceiling):
RATE=22050 tools/prepare_card.sh /Volumes/YOUR_SD song.mp3
```

Files are written as `NN_name.wav` so playback order is stable. A ready-made
`audio/01_tones.wav` (16 kHz mono) is included for a first test — copy it to the
card root.

## Deploy to the badge

Uses [`mpremote`](https://docs.micropython.org/en/latest/reference/mpremote.html).
The board must already have MicroPython v1.28 flashed.

```sh
PORT=$(ls /dev/cu.usbmodem*)        # macOS
mpremote connect $PORT fs cp \
    config.py sk9822.py buttons.py lights.py dsp.py \
    wavparse.py wavplayer.py sdcard.py selftest.py main.py :
mpremote connect $PORT reset        # main.py auto-runs on boot
```

## Files

| File | Purpose |
|------|---------|
| `config.py` | **Pin map + tunables** (single source of truth) |
| `main.py` | Entry point: mount SD, build playlist, run async tasks |
| `wavplayer.py` | Async I2S streaming player (volume, pause, VU level) |
| `wavparse.py` | Robust RIFF/WAVE PCM-16 parser |
| `dsp.py` | Viper DSP hot path (volume + peak) |
| `sk9822.py` | Bit-banged SK9822 LED driver (viper/SIO fast path) |
| `audiolab.py` | Button-driven audio diagnostic lab (tone/sweep/music/silence) |
| `lights.py` | LED light modes (VU / rainbow / pulse / solid) |
| `buttons.py` | Debounced button reader with auto-repeat |
| `sdcard.py` | **Patched** SD-SPI driver (CMD8-glitch workaround) |
| `selftest.py` | Standalone per-subsystem hardware test |
| `tools/prepare_card.sh` | Host-side audio → badge-WAV converter |
| `cmodules/mp3/` | Native MP3 decoder C module (Helix / picomp3lib) |
| `tools/build_firmware.sh` | Build custom firmware with the MP3 module |
| `BADGE.md` | Hardware pin map + verified quirks |

## Controls / recovery

- **Hold CH at power-on** → skips autostart, drops to the REPL (recovery).
- **Ctrl-C** over serial stops the asyncio loop cleanly.
- Run one subsystem test: `import selftest; selftest.audio()` (or `.all()`).

## Native MP3 (optional)

Adds real-time MP3 playback by compiling the Helix decoder into a custom
MicroPython firmware as a C user-module. Everything else (SD driver, I2S, LEDs,
buttons, IR, the player) is unchanged — the player just gains an MP3 path.

Build on a computer with the ARM toolchain (not on the badge):

```sh
cd firmware
tools/build_firmware.sh          # clones MicroPython + picomp3lib + pico-sdk
# -> firmware-mp3.uf2
```
Requires `arm-none-eabi-gcc`, `cmake`, `make`, `git`, `python3`
(`brew install cmake arm-none-eabi-gcc`). Then flash `firmware-mp3.uf2` (hold
BOOTSEL, copy to RPI-RP2), re-deploy the `.py` files, and drop `.mp3` files on the
card. Details in [`cmodules/mp3/README.md`](cmodules/mp3/README.md).

Not built it yet? Everything still runs as a **WAV** player on stock MicroPython —
the MP3 path activates only when the `mp3` module is present.

## Known limitations / respin notes

- **Writes to SD are unproven** — treat the card as read-only in the field.
- **No MISO pull-up** on the board → SPI kept at 1 MHz. Adding a 10–47 kΩ
  MISO→3V3 pull-up (and series R on SCK) would allow faster SPI, higher-quality
  audio, and reliable writes.
- **Pause latency** ≈ the I2S buffer (~0.23 s) — the buffered audio finishes
  before it goes quiet. Tune `I2S_IBUF` in `config.py` (smaller = snappier pause,
  larger = more dropout immunity).
- **Realtime margin is not huge.** 44.1 kHz stereo MP3 measured 1.002× realtime
  with the full task load (decode + volume/reframe + LEDs + buttons + SD). If you
  add work to the audio or LED path, re-measure — at 0.95× the stutter is
  immediately audible. The 250 MHz overclock and the viper LED driver are both
  load-bearing.
- SYNC is a **local light toggle**; real device-to-device timing sync over IR
  (GP9 TX / GP27 RX, 38 kHz) is a future addition — the hardware is verified.
- **Native MP3** is provided via the `cmodules/mp3` C module (see above); it needs
  a one-time custom firmware build. Validated on hardware 2026-07-24 (rev 2 board):
  44.1 kHz stereo plays continuously at the 250 MHz overclock with the full task
  load; at stock 125 MHz it underruns (~0.57× realtime) — don't remove the
  `machine.freq(C.CPU_FREQ)` call in `main.py`.
