# DEFCON Silent-Disco Badge — Hardware Notes & Quirks

Everything here was verified during hardware bring-up (MicroPython v1.28 on the
RP2040) against the KiCad schematic in `../defcon_badge/`. These are the facts
the firmware depends on. **Read this before changing pin assignments.**

## Pin map (all GPIO numbers)

| Subsystem | Signal | GPIO | Notes |
|-----------|--------|------|-------|
| **LEDs** (SK9822 ×4) | CLOCK | **GP24** (rev 2) | rev 1 boards: GP25 — swapped vs schematic (see below) |
| | DATA | **GP25** (rev 2) | rev 1 boards: GP24 |
| **Audio** (TM8211 I2S) | BCK / SCK | GP7 | |
| | WS / LRCK | GP8 | must be `SCK+1` on RP2040 |
| | DIN / SD | GP6 | |
| **Buttons** | SYNC | GP12 | active-low, needs pull-up |
| | VOL− | GP13 | |
| | VOL+ | GP14 | |
| | CH (→play/pause) | GP15 | |
| **microSD** (SPI0) | SCK | GP2 | |
| | MOSI | GP3 | |
| | MISO | GP4 | ⚠️ no board pull-up |
| | CS | GP5 | |
| **IR** | TX (LED) | GP9 | active-low, 38 kHz carrier |
| | RX (TSOP4838) | GP27 | active-low, idles high |

## Verified quirks (the important part)

### 1. LED clock/data are SWAPPED (rev 1 only — FIXED on rev 2)
On **rev 1**, the SK9822 footprint/silkscreen had DIN/CIN reversed, so the
assembled board needs **CLOCK on GP25 and DATA on GP24** — the opposite of the
schematic net names (`LED_SCK`, `LED_DAT`). With the schematic mapping the LEDs
stay dark; with the swap they work. **Rev 2 fixed the footprint** (verified
2026-07-24: schematic mapping works, swapped mapping is dark) — `config.py`
now ships with the schematic mapping; flip `LED_CLK`/`LED_DAT` for a rev 1 board. All four LEDs must also share the **same physical
orientation** or the daisy-chain breaks partway.
- GP24/GP25 are **not** on a hardware SPI block → the driver bit-bangs.
  ⚠️ Bit-banging this through `Pin.value()` cost **3848 µs per frame — 12.8% of
  the CPU** at a 30 ms refresh, enough to starve the MP3 refill and cause audible
  stutter. `sk9822.py` now shifts bits by writing the SIO `GPIO_OUT_SET`/`CLR`
  registers (`0xd0000014`/`0xd0000018`) from a viper function, which brings a
  full render down to 942 µs (3.1%). `SK9822.delay` pads the clock phases if a
  longer chain ever needs slowing down; 0 is right for four LEDs.
- Byte order after the brightness byte is **B, G, R** (standard SK9822).
- These run at 3.3 V. That's below the SK9822 datasheet min (3.7 V) but they
  work fine in practice.

### 2. Audio DAC = TM8211 (PT8211 clone), plain I2S
- No MCLK required, no mute/enable pin. Chain: DAC → TDA1308 headphone amp →
  3.5 mm jack (SJ1-3523N).
- 🚨 **The PT8211/TM8211 requires LSB-justified (LSBJ) framing, and this is not
  optional.** An earlier version of this document claimed "standard I2S produces
  clean audio in testing" — **that was wrong** and cost a long debugging session.
  See quirk 6 below.
- **No hardware volume** anywhere in the chain → volume is done in software by
  scaling PCM samples. The PT8211 has no gain register and the TDA1308's gain is
  fixed by its feedback resistors, so scaling samples in `dsp.pcm16_to_lsbj32()`
  is the only volume control that exists.
- Analog gain is **≈2.1×** (100 kΩ feedback / 47 kΩ input, per the schematic) and
  is perfectly healthy. If output seems wildly too loud, suspect the framing
  (quirk 6), not the amp.
- WS pin must equal SCK+1 on RP2040: GP8 = GP7+1. ✔
- ⚠️ **Rev 1 builds had the TDA1308 unpopulated** (wrong package was ordered).
  Listening directly off the DAC into headphones (32 Ω) overloads the PT8211's
  line-level output → heavy "clipped" distortion at any real amplitude. The
  digital chain was exhaustively verified clean (decode bit-perfect vs ffmpeg,
  DSP exact, I2S transport clean) — the distortion is purely the missing
  buffer. On an amp-less board: feed a **line-level input** (powered
  speakers/AUX), keep digital level ≤ ~5–10 %, and set `VOL_DEFAULT_STEP = 1`.
  **Rev 2 has the TDA1308 populated** — headphone output is usable and the
  default volume step in `config.py` is raised accordingly.

### 3. microSD reads work; it's a read-mostly device here
- The card's **CMD8 response glitches its R1 byte on bus turnaround** on this
  board. The stock `sdcard.py` rejects the card ("couldn't determine SD card
  version"); the patched `sdcard.py` in this dir detects a v2/SDHC card from
  the CMD8 voltage echo (`0x01AA`) instead. It also drains the bus on a read
  timeout (so a marginal read doesn't wedge the card) and retries block reads.
- There is **no MISO pull-up** on the board. Keep SPI at ≤1 MHz. Measured read
  throughput at 1 MHz: **~45–51 KB/s**, byte-perfect and repeatable on a
  settled board (10/10 verified reads of an 8 KB file; a 269 KB file read clean
  at 51 KB/s).
- **Writes are unproven** and occasionally wedged the card during testing (partly
  confounded by live-soldering). Treat the card as read-only in the field; load
  content offline with a card reader.
- **Respin TODO:** add a MISO→3V3 pull-up (10–47 kΩ), ideally on MOSI/CS too,
  plus series resistors on SCK — then higher SPI clocks and reliable writes
  become possible.

### 4. Buttons
Active-low, no external pull resistors → enable the RP2040 internal pull-ups.
`value()==0` means pressed. All four verified idle-high and responsive.

### 5. IR (send + receive both work)
- TX: IR LED driven **active-low** through a resistor from GP9. Modulate a
  **38 kHz** carrier (the TSOP4838 only demodulates ~38 kHz). GP9 low = LED on.
- RX: TSOP4838 output on GP27, **active-low**, idles high, pulls low when it
  sees the carrier (with ~160 µs turn-on latency).
- Self-loopback works on the bench with no reflector (enough on-board optical
  coupling). Intended use is device-to-device timing sync — not wired up in the
  player yet (the SYNC button is a local no-op that just changes the lights).

### 6. I2S framing: the DAC needs LSBJ, MicroPython only speaks standard I2S
This was the root cause of the rev-2 "everything is painfully loud and music is
pure static" bug. Diagnosed and fixed 2026-07-24.

The schematic says it outright: *"DAC needs LSBJ-format I2S (WS shifted by one
BCK vs standard I2S)."* LSB-justified framing means the sample's last bit lands
on the WS edge. Standard (Philips) I2S delays data by one BCK instead. With
**16-bit frames** that one-bit slip is catastrophic, because the DAC latches the
16 bits ending at the WS edge:

| DAC bit | gets | should be |
|---------|------|-----------|
| 15 (**sign**) | the **previous** sample's LSB | sample bit 15 |
| 14..0 | sample bits 15..1 | sample bits 14..0 |

So the **sign bit is driven by a bit with no relationship to the signal**. Any
sample whose LSB is set slams the next output to roughly −32768. Consequences,
all of which we observed:
- Output sits near full scale no matter how small the samples are, so it is
  deafening even at 1 LSB (−90 dBFS), and **software volume cannot work at all**.
- *Music* becomes broadband static, because its LSBs toggle pseudo-randomly.
- *Pure tones* still sound crisp and pitched — the LSB of a low-amplitude sine
  toggles periodically, so the garbage is a periodic (square-ish) wave at the
  right frequency. This is why every tone test wrongly looked fine, and why the
  bug survived rev-1 bring-up.

**Fix (no PIO needed):** send **32-bit frames** with the 16-bit sample in bits
**16..1** — `dsp.pcm16_to_lsbj32()`, enabled by `I2S_BITS = 32` in `config.py`.
The one-BCK delay then aligns those bits exactly with the final 16 bits of the
frame. Costs one extra pass over the samples (fused with the volume multiply)
and doubles the wire rate and `I2S_IBUF`.

Debugging tip that isolated it in one test: play a square wave toggling `0/1`
against one toggling `0/2`. They differ by a single bit, but under this fault
the `0/1` one is dramatically **louder** — amplitude and loudness inverted.
Nothing but a sign-bit misalignment does that.

### 7. The LEDs are audible in the headphones
Reported and localised 2026-07-24: with playback **digitally muted** (volume
step 0) there is still a high-pitched whine, plus a periodic tick. It tracks the
LED animation — during the amber "paused" breathing you can literally hear the
brightness rise and fall. So it is not in the audio data; the LED chain is
coupling into the audio, most likely through the shared 3V3 rail as SK9822
current draw changes with PWM duty, with the periodic bit-bang burst adding the
tick.

**The mechanism is PWM duty cycle, not brightness or data traffic.** Narrowed
down by ear on 2026-07-24:
- Not data: the frame is re-clocked every 30 ms whether or not anything changed,
  so bit-bang traffic is constant and cannot explain noise that comes and goes.
- Not position: with only LED1 lit — the one furthest from the jack and amp —
  it was just as audible, ruling out radiated/capacitive coupling.
- **It is duty.** The SK9822 dims each channel by chopping it at ~4.7 kHz, right
  in the audible band. Switching energy peaks near 50% duty and vanishes at both
  0% and 255. Decisive test: two phases at *equal average current*
  (value 255 @ brightness 8 vs value 128 @ brightness 16) but 100% vs 50% duty —
  the noise cleanly alternated with duty. This also explains why a rainbow is
  loudest *mid-transition* (mixed, mid-range channels) and quiet at its
  brightest points (saturated hues).

Firmware fixes, both in place:
1. **A quiet palette.** `lights.py` now uses only saturated channel values
   (0 or 255) and expresses all intensity through the SK9822's **per-LED**
   global-brightness field, which is an analog constant-current setting rather
   than a duty cycle. ⚠️ Do not reintroduce `wheel()`/`scale()` or any
   mid-range colour value into the light modes — that is precisely the fault.
2. **An OFF mode** (cycle to it with SYNC). A real quiet state, not black
   pixels — after one dark frame it stops touching the chain entirely, since
   clocking out black would leave the switching noise in place.

`LED_ACTIVE_MASK` in `config.py` restricts which LEDs illuminate while still
clocking all of them, which is how the position test above was run.

**Respin fixes to consider:** separate/filtered supply for the LEDs, bulk plus
HF decoupling at the LED chain, keeping LED traces away from the DAC and its
coupling caps, and a star ground so LED return current does not share a path
with the audio ground.

## Audio formats

**WAV — works on stock MicroPython.** 16-bit PCM streamed SD → I2S. Convert songs
with `tools/prepare_card.sh` (ffmpeg). Keep files **mono, 16000 Hz** (32 KB/s,
safe) — 22050 Hz mono (44 KB/s) is borderline against the SD read ceiling. The
badge up-mixes mono to stereo via `I2S.MONO`.

**MP3 — needs the custom firmware.** MicroPython has no built-in MP3 decoder and
pure-Python decode is too slow, but the RP2040 decodes MP3 in fixed-point **C**.
⚠️ Measured on hardware (2026-07-24): decode of 44.1 kHz stereo costs **~94% of a
core at stock 125 MHz** (an earlier ~34% estimate was wrong) — with DSP + SD on
top the player underruns constantly. The firmware therefore **overclocks to
250 MHz** at boot (`CPU_FREQ` in `config.py`), verified stable and >1× realtime
with the full task load. The
`cmodules/mp3` native module (Helix / [picomp3lib](https://github.com/ikjordan/picomp3lib))
exposes a `mp3.Decoder` callable from Python; build with `tools/build_firmware.sh`.
MP3 also **reduces** SD load (128 kbps ≈ 16 KB/s vs 32 KB/s for the WAV above) and
shrinks files ~10×. The player uses MP3 automatically when the module is present
and `.mp3` files are on the card; it falls back to WAV-only on stock firmware.

Key M0+ detail: the RP2040 (ARMv6-M) has no 64-bit multiply (`SMULL`); picomp3lib's
`assembly.h` gates the `SMULL` path on `__ARM_ARCH >= 7`, so it uses a C multiply
fallback — don't swap in an unpatched decoder.

*(CircuitPython also has a native `audiomp3` decoder, but its built-in SD driver
would re-trip the CMD8 glitch our MicroPython driver works around, and it needs a
full app rewrite — so the C-module route is preferred.)*
