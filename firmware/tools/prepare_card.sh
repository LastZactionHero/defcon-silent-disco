#!/usr/bin/env bash
#
# prepare_card.sh -- encode DJ mixes for the badge and copy them to the card.
#
# Output format (matches what the firmware and the IR sync REQUIRE):
#     MP3, 96 kbps CBR, joint stereo, 44.1 kHz, no ID3/artwork
#
#   * CBR is load-bearing: IR sync seeks by byte offset, which is only linear
#     in time for constant bitrate.  VBR would make everyone sync to the wrong
#     bar.  Do not "upgrade" this to VBR.
#   * 44.1 kHz is load-bearing too: the DAC has no reconstruction filter, so a
#     lower sample rate folds ultrasonic images DOWN toward the audible band.
#   * Loudness-normalised (EBU R128, -16 LUFS) so channel-surfing between two
#     different DJs does not whiplash between quiet and loud.  TWO-PASS
#     (measure, then apply linearly): single-pass loudnorm adjusts gain
#     dynamically and audibly "pumps" on dynamic material -- exactly wrong
#     for a DJ mix.  Two-pass applies one constant gain.
#   * Metadata/artwork stripped -- a display-less badge has no use for 500 KB
#     of embedded cover art (the first test file wasted 5.6% on exactly that).
#
# Capacity: a "128 MB" card holds ~125 MB usable = ~2 h 54 m at 96 kbps.
# Channel order on the badge is ALPHABETICAL by filename, and the filename
# hash picks the LED theme + animation -- renaming a file changes its look.
#
# Usage:
#   tools/prepare_card.sh <dest_dir> <input1> [input2 ...]
#   tools/prepare_card.sh "/Volumes/NO NAME" set1.wav set2.flac set3.mp3
#
# Requires: ffmpeg
set -euo pipefail

BITRATE="${BITRATE:-96k}"

if [ "$#" -lt 2 ]; then
  echo "usage: $0 <dest_dir> <input1> [input2 ...]" >&2
  exit 2
fi
command -v ffmpeg >/dev/null 2>&1 || { echo "error: ffmpeg not found (brew install ffmpeg)" >&2; exit 1; }

DEST="$1"; shift
mkdir -p "$DEST"

total=0
for src in "$@"; do
  if [ ! -f "$src" ]; then
    echo "skip (not found): $src" >&2
    continue
  fi
  base="$(basename "${src%.*}")"
  safe="$(printf '%s' "$base" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-40)"
  out="$DEST/$safe.mp3"
  echo "-> $out"

  # pass 1: measure loudness (writes nothing)
  MEAS=$(ffmpeg -hide_banner -nostats -i "$src"           -af loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json -f null - 2>&1 |
         python3 -c '
import json, sys
txt = sys.stdin.read()
try:
    j = json.loads(txt[txt.rindex("{"):txt.rindex("}") + 1])
    print(":".join("measured_%s=%s" % (k, j["input_" + k.lower()])
                   for k in ("I", "TP", "LRA", "thresh"))
          + ":offset=%s" % j["target_offset"])
except Exception:
    pass')

  if [ -n "$MEAS" ]; then
    NORM="loudnorm=I=-16:TP=-1.5:LRA=11:$MEAS:linear=true"
  else
    echo "   (measurement failed -- falling back to single-pass loudnorm)" >&2
    NORM="loudnorm=I=-16:TP=-1.5:LRA=11"
  fi

  # pass 2: one constant gain, then encode
  ffmpeg -y -v error -i "$src"     -vn -codec:a libmp3lame -b:a "$BITRATE" -joint_stereo 1 -ar 44100 -ac 2     -af "$NORM"     -map_metadata -1 -id3v2_version 0 -write_id3v1 0     "$out"
  sz=$(stat -f%z "$out" 2>/dev/null || stat -c%s "$out")
  total=$((total + sz))
  echo "   $((sz / 1048576)) MB"
done

sync
echo
echo "total: $((total / 1048576)) MB  (budget: ~119 MB usable on a 128 MB card)"
if [ "$total" -gt 124000000 ]; then
  echo "WARNING: over the 128 MB card budget -- trim a set or drop a channel" >&2
fi
echo "channel order = alphabetical.  Eject the card SAFELY (data may be cached)."
# show what each track will look like on the badge (uses the real firmware code)
if command -v python3 >/dev/null 2>&1; then
  echo
  python3 "$(dirname "$0")/card_preview.py" "$DEST"/*.mp3 2>/dev/null || true
fi
