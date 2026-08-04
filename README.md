# DEF CON Silent Disco Badge

A wearable silent disco. Every badge plays DJ mixes from its own memory
card to your headphones, runs a light show that matches the music, and can
**sync to a friend's badge over infrared** — same song, same moment, lights
flashing together.

![Front](docs/hero_front.png)

## How to use it

1. Flip the **power switch**. Plug **headphones** into the top jack.
2. It starts playing where it last left off.

| Button | Does |
|---|---|
| **CHANNEL** | Next channel. Each channel is one DJ mix that loops forever. |
| **VOL + / −** | Volume, 8 steps. Hold to ramp. Bottom step is mute. |
| **SYNC** | Join a friend — see below. |
| **CHANNEL, held 10 s** | Reset the badge. |

**Syncing:** press SYNC — your music pauses and the badge listens for up to
~25 seconds. Touch your badge's jagged edge into your friend's (they
interlock — that's what the teeth are for) and it will pick up their
broadcast, jump to **their channel at their exact spot**, and both badges
shimmer to confirm. Every badge announces itself over IR every ~10 seconds,
so there's nothing to press on the other badge.

**The light show** is picked by the music: each track gets its own color
theme and animation, and every ~10 seconds the badge plays a short glitter
burst. Synced badges glitter at the same instant.

## If something's wrong

**Red blinking LEDs** are an error code — count which LEDs are lit
(leftmost = 1):

| Code | Meaning | Try |
|---|---|---|
| 1 | No SD card | Reseat the card, power cycle |
| 2 | Card is empty | Put MP3s on it (see below) |
| 3 | Card unreadable | Re-format / re-copy the card |
| 4 | Playback keeps failing | Power cycle; check the battery |

**Sounds distorted, buzzy, or "like a modem"? Swap the battery.** A dying
battery warps the audio and confuses the SD card before anything else —
it looks like a bug, and it never is.

## The SD card

Just MP3 files in the root of the card — nothing else needed:

```
/ElAndEu_Duis.mp3      ← channel 1
/InYourEyes.mp3        ← channel 2
/Sepultura.mp3         ← channel 3   (alphabetical order = channel order)
```

- Encode at **96 kbps CBR, 44.1 kHz stereo** — `firmware/tools/prepare_card.sh`
  does this for you (and matches loudness across mixes).
- The **filename chooses the light show** — rename a file, get new colors.
- A 128 MB card holds about **2 h 54 m** (~29 min × 6 channels).

![Back](docs/hero_back.png)

## Coming soon

- **Plain MP3-player firmware** — reflash the badge as a normal
  pocket music player (next/prev/pause instead of channels + sync). The
  code exists in this repo; a one-step installer is TODO.
- A **phone app that joins the disco by camera** — the glitter bursts
  encode the channel and timecode, so a phone can watch any badge and
  start playing along. Groundwork is shipped; app is TODO.

## Under the hood

RP2040 · MicroPython + native MP3 decoder · 4× addressable RGB LEDs ·
IR sync · sawtooth interlocking edges · USB-C. The full technical story —
firmware architecture, the test suite, build-your-own instructions, and
the bring-up war stories — lives in [`firmware/README.md`](firmware/README.md).
KiCad sources are in [`defcon_badge/`](defcon_badge/), fab files in
[`defcon_badge/fab_rev2.zip`](defcon_badge/fab_rev2.zip).

## Credits

Designed and built by [**Pikkolo Assembly**](https://pikkoloassembly.com/).
Demo mixes are Creative Commons (attribution in `CREDITS.txt` on each
card). MP3 decoding by the Helix decoder via
[picomp3lib](https://github.com/ikjordan/picomp3lib).

MIT licensed — see [LICENSE](LICENSE). Go make a dance floor.
