# DEFCON Silent-Disco Badge — Firmware

MicroPython + native-C firmware for the RP2040 badge: a **silent disco** —
each badge streams MP3 "channels" from its microSD to headphones, shows a
per-track LED theme + animation, and can **sync channel and playback position
to a neighbouring badge over IR**, so groups dance to the same beat.

> **Read [`BADGE.md`](BADGE.md) for the hardware story** — pin quirks, the
> patched SD driver, and the bring-up findings this code depends on.

## What it does

- Plays **MP3** (96 kbps CBR, the native Helix decoder) from the card root.
  Channel = file, ordered alphabetically. A track **loops**; it never
  auto-advances — changing channel is always a deliberate press.
- **CHANNEL** (GP15): tap = next channel. **Hold 10 s = hard reset** (the
  field escape hatch — no laptop needed).
- **VOL+ / VOL−** (GP14/GP13): 8 steps, 6 dB each, top step −6 dBFS, true
  mute at 0. Auto-repeat when held.
- **SYNC** (GP12): join a neighbour. Playback pauses, the badge listens
  ~25 s for another badge's IR broadcast, then adopts **their channel and
  position** (latency-compensated to ~±70 ms). Times out back to where you
  were. Every badge broadcasts its own (timecode, channel) every 7–13 s.
- **LEDs**: the track *name* hashes to one of 16 themes × 12 animations × 4
  brightness levels (768 looks). Animation phase is locked to the playback
  clock, so **synced badges flash in step and stay in step**.
- **Crash resilience**: channel/position/volume persist to internal flash;
  a brownout resumes mid-set, rewound a few seconds. Faults blink **red
  binary** on the LEDs (LED1 = LSB): 1 = no SD card, 2 = no playable tracks,
  3 = SD mount raised, 4 = playback failing. Every error path stays alive
  and keeps hold-to-reset working.

## Provision a badge (one command)

```sh
tools/flash_badge.sh          # one badge: BOOTSEL → flash → deploy → verify
tools/flash_badge.sh --loop   # the whole pile, badge after badge
```

Flashes `firmware-mp3-universal.uf2` — one image that boots **both** flash
vendors in the manufacturing run (Winbond and Macronix; the custom boot2
discriminates at boot) — then deploys the runtime and verifies imports on
the badge. macOS gotcha handled inside: a plain `cp` of a UF2 **silently
fails**; the script uses `dd` + `sync` and treats *the RPI-RP2 volume
disappearing* as the success signal.

## Prepare a card

```sh
tools/prepare_card.sh "/Volumes/CARD" set1.wav set2.flac set3.mp3
```

Encodes to the shipping format and prints a **preview of each track's LED
look** (the preview imports the real firmware code, so it cannot drift).
Two choices in the recipe are load-bearing — do not "improve" them:

- **CBR**: IR sync seeks by byte offset, which is only linear in time for
  constant bitrate. VBR = everyone syncs to the wrong bar.
- **44.1 kHz**: the DAC has no reconstruction filter; a lower sample rate
  folds ultrasonic images *down toward* the audible band.

Also: EBU R128 loudness normalisation (−16 LUFS) so channel-surfing between
DJs doesn't whiplash, metadata/art stripped, and a 128 MB budget check
(~2 h 54 m total at 96 k). **Track filename = channel order and LED look.**

Got a mix in an app that can play but not export? `tools/record_mix.sh`
captures the Mac's own audio output (loopback via BlackHole) to a lossless
WAV master and encodes the badge MP3 from that.

## Tests

```sh
python3 tools/host_tests.py
```

Runs the **real firmware modules** on the host: the IR ISR + decoder against
synthetic TSOP edges (AGC stretch, mark distortion, measured 60 Hz ambient
noise), CBR seek/wrap math, persistence-slot recovery incl. torn writes,
every LED invariant (no mid-range PWM, ≤1 white/theme, slot determinism,
flash-rate safety), and the volume ladder. Run it before deploying changes.

## Files

| File | Purpose |
|------|---------|
| `config.py` | **Pin map + tunables** (single source of truth, with history) |
| `main.py` | Entry point — boots `disco`; alternates commented inside |
| `disco.py` | The silent-disco program (channels, LEDs, sync, persistence) |
| `irsync.py` | IR timecode protocol: NEC-style TX + hard-IRQ RX |
| `wavplayer.py` | Async player engine (MP3+WAV, seek, stall watchdog) |
| `mp3player.py` | Plain player (also: `mount_sd`/`find_tracks` used by disco) |
| `linktest.py` | IR link bring-up tools: `beacon()` / `scope()` / `raw()` |
| `dsp.py` | Viper DSP hot path (volume + LSBJ reframe + peak) |
| `sk9822.py` | Bit-banged SK9822 LED driver (viper/SIO fast path) |
| `buttons.py` | Debounced buttons: auto-repeat + tap/hold semantics |
| `sdcard.py` | **Patched** SD-SPI driver (CMD8-glitch workaround) |
| `audiolab.py` | Audio diagnostics (tone/sweep/ZEROS/CLKOFF/FREQ modes) |
| `jukebox.py`, `lights.py`, `selftest.py` | Earlier player + LED modes + HW test |
| `tools/flash_badge.sh` | One-command badge provisioning (`--loop` for batches) |
| `tools/prepare_card.sh` | Mix → badge-format MP3 + look preview + budget check |
| `tools/record_mix.sh` | Record the Mac's audio output to badge format |
| `tools/host_tests.py` | Host regression suite (real modules, no hardware) |
| `tools/card_preview.py` | LED look preview for a set of filenames |
| `tools/build_firmware.sh` | Rebuild the firmware UF2 (MP3 module + boot2) |
| `boot2/` | Custom second-stage bootloaders (universal + Macronix) |
| `cmodules/mp3/` | Native MP3 decoder C module (Helix / picomp3lib) |

## Recovery / field notes

- **Sounds like a modem / horrible hum, or the card stops reading?  Fresh
  battery first.**  A sagging AAA amplitude-modulates the DAC (its output is
  ratiometric to the rail) and breaks SD init -- both look exactly like
  firmware bugs.  USB power masks it, so a badge that "tests fine on the
  laptop" can still be a dead battery.  Pack spares.
- **Hold CHANNEL at power-on** → skip autostart, drop to the REPL.
- **Hold CHANNEL 10 s while running** → hard reset (works on error screens too).
- Red binary blink = error code (see above). Code 1: reseat the SD card.
- `mpremote` cannot take the REPL while audio is decoding — send **one**
  Ctrl-C over raw serial first, or power-cycle, then deploy. (Spamming
  Ctrl-C mid-playback has wedged boards.)
- Rebuilding the UF2 needs the **xPack** ARM toolchain on PATH first —
  Homebrew's `arm-none-eabi-gcc` has no newlib and fails at boot2 link:
  `export PATH="$HOME/dev/xpack-arm-none-eabi-gcc-14.2.1-1.1/bin:$PATH"`

## Known limitations / respin notes

- **Writes to SD are unproven** — state persists to *internal* flash instead;
  treat the card as read-only in the field.
- **No MISO pull-up** fitted: the schematic's R8/R9/R23 pull-ups terminate on
  a mis-named power net (`+3.3V` vs `+3V3`) with no source. One symbol rename
  fixes it next spin; until then SD SPI stays at the verified 4 MHz.
- **No DAC reconstruction filter** → the supply-buzz floor, and the reason
  encoding stays at 44.1 kHz. Next spin: series R + shunt C on each DAC
  output, and a local bypass at the TDA1308 (it has none).
- **IR range is short by construction**: the emitter is ~13 mA straight off a
  GPIO (12 mA pad drive recovers the design current). A transistor driver at
  100 mA+ next spin would give real range. Badges sync reliably at
  face-to-face distances; the jagged board edges interlock to align
  emitter↔receiver.
- **276 MHz overclock** (RP2040 is rated 133 MHz) is load-bearing for MP3
  decode *and* chosen for audio-noise pitch; verified stable on the bench
  units. `250_000_000` is the tested fallback if a unit is flaky.
- The VM freezes during internal-flash writes (XIP suspend) and the ~68 ms
  IR send — the firmware spaces them apart and the emit watchdog logs any
  >150 ms gap with blame, so a stutter report is diagnosable from the console.
