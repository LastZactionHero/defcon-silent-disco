#!/usr/bin/env bash
#
# prepare_card.sh -- convert audio files into badge-playable WAV and copy them
# to the microSD card (or any directory).
#
# The badge plays 16-bit PCM WAV streamed from the SD card to the I2S DAC.
# It CANNOT decode MP3 in real time (MicroPython has no MP3 decoder and the
# RP2040 is too slow for pure-Python decode), so we pre-decode to WAV here.
#
# SD read throughput on this board is ~45-51 KB/s at the conservative 1 MHz
# SPI clock (no MISO pull-up).  Byte rate of the chosen format must stay under
# that with margin:
#     mono 16-bit @ 16000 Hz = 32 KB/s   <- default (safe, good margin)
#     mono 16-bit @ 22050 Hz = 44 KB/s   <- borderline; use only if reads solid
# The player up-mixes mono to stereo on the fly, so keep the files MONO to
# halve the SD load.
#
# Usage:
#   tools/prepare_card.sh <dest_dir> <input1> [input2 ...]
#   RATE=22050 tools/prepare_card.sh /Volumes/BADGE song1.mp3 song2.flac
#
# Requires: ffmpeg
set -euo pipefail

RATE="${RATE:-16000}"      # override with RATE=22050 for higher quality (riskier)
CHANNELS=1                 # mono keeps SD bandwidth low; badge up-mixes to stereo

if [ "$#" -lt 2 ]; then
  echo "usage: RATE=$RATE $0 <dest_dir> <input1> [input2 ...]" >&2
  exit 2
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "error: ffmpeg not found (brew install ffmpeg)" >&2
  exit 1
fi

DEST="$1"; shift
mkdir -p "$DEST"

i=1
for src in "$@"; do
  if [ ! -f "$src" ]; then
    echo "skip (not found): $src" >&2
    continue
  fi
  base="$(basename "${src%.*}")"
  # sanitize: keep it short + FAT-friendly; number so playback order is stable
  safe="$(printf '%s' "$base" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-24)"
  out="$(printf '%s/%02d_%s.wav' "$DEST" "$i" "$safe")"
  echo "-> $out  (${RATE} Hz, ${CHANNELS}ch, 16-bit)"
  ffmpeg -y -v error -i "$src" \
    -f wav -acodec pcm_s16le -ac "$CHANNELS" -ar "$RATE" \
    "$out"
  i=$((i + 1))
done

echo "done. copied $((i - 1)) file(s) to $DEST"
echo "eject the card safely, insert into the badge, and it will play them in order."
