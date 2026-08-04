#!/usr/bin/env bash
#
# record_mix.sh -- record whatever this Mac is PLAYING (loopback) to a file,
# for mixes made in an app that can play but not export.
#
# macOS has no built-in "record system output"; it needs a loopback device.
# We use BlackHole (free, open source).  ONE-TIME SETUP:
#
#   1. brew install blackhole-2ch        (asks for your password)
#   2. open "Audio MIDI Setup" (cmd-space, type it)
#        - click "+" bottom-left -> "Create Multi-Output Device"
#        - tick BOTH "BlackHole 2ch" AND your speakers/headphones
#   3. System Settings -> Sound -> Output -> "Multi-Output Device"
#      (audio now goes to your ears AND to BlackHole simultaneously)
#
# Then:
#   tools/record_mix.sh my_set            # record until you press q
#   DURATION=3600 tools/record_mix.sh my_set   # or a fixed length in seconds
#
# Produces my_set.wav (lossless master -- keep it!) and my_set.mp3 in the
# badge format via prepare_card.sh, so the badge encode always comes from
# lossless rather than a second lossy generation.
#
# Tip: if your mixing app can export/bounce to ANY file format at all, do
# that instead -- an export is sample-exact, a loopback recording is merely
# very good.
set -euo pipefail

cd "$(dirname "$0")"

NAME="${1:-mix_$(date +%Y%m%d_%H%M%S)}"
NAME="${NAME%.wav}"; NAME="${NAME%.mp3}"
WAV="$NAME.wav"

command -v ffmpeg >/dev/null 2>&1 || { echo "error: ffmpeg not found (brew install ffmpeg)" >&2; exit 1; }

# find BlackHole's avfoundation audio-device index.  RECDEV=N overrides, for
# any other loopback device you already have (e.g. a "Virtual Desktop
# Speakers" style device installed by remote-desktop tools -- if it appears
# as an OUTPUT in Sound settings, routing audio to it and recording its index
# here works the same way).
DEVLIST=$(ffmpeg -f avfoundation -list_devices true -i "" 2>&1 || true)
IDX="${RECDEV:-$(printf '%s\n' "$DEVLIST" | sed -n 's/.*\[\([0-9]*\)\] BlackHole.*/\1/p' | head -1)}"

if [ -z "$IDX" ]; then
  echo "BlackHole not found.  Audio input devices ffmpeg can see:" >&2
  printf '%s\n' "$DEVLIST" | sed -n '/audio devices/,$p' | sed 's/^/  /' >&2
  echo >&2
  echo "Install it:   brew install blackhole-2ch" >&2
  echo "Then do the one-time Multi-Output Device setup in this script's header." >&2
  exit 1
fi
echo "BlackHole is avfoundation audio device [$IDX]"

# sanity: warn if system output is not routed through BlackHole
OUT_NOW=$(system_profiler SPAudioDataType 2>/dev/null |
          awk '/Default Output Device: Yes/{found=1} found&&/^        [A-Za-z]/{print; exit}' || true)
echo
echo "RECORDING CHECKLIST:"
echo "  - System Settings -> Sound -> Output must be 'Multi-Output Device'"
echo "    (or 'BlackHole 2ch' if you do not need to hear it)"
echo "  - set your mix app playing AFTER recording starts; trim later"
echo

if [ -n "${DURATION:-}" ]; then
  echo "recording $DURATION s -> $WAV"
  ffmpeg -hide_banner -loglevel error -f avfoundation -i ":$IDX" \
         -ac 2 -ar 44100 -t "$DURATION" -y "$WAV"
else
  echo "recording -> $WAV    (press q to stop)"
  ffmpeg -hide_banner -loglevel error -f avfoundation -i ":$IDX" \
         -ac 2 -ar 44100 -y "$WAV"
fi

SZ=$(stat -f%z "$WAV" 2>/dev/null || echo 0)
[ "$SZ" -gt 100000 ] || { echo "error: recording is tiny ($SZ bytes) -- was audio routed to BlackHole?" >&2; exit 1; }
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$WAV" 2>/dev/null || echo "?")
echo "captured: $WAV  ($((SZ / 1048576)) MB, ${DUR%.*} s)"

echo
echo "encoding badge MP3 from the lossless master..."
./prepare_card.sh . "$WAV" >/dev/null
echo "done: $NAME.mp3  (badge-ready: 96k CBR joint stereo, loudness-normalised)"
echo "keep  $WAV as your lossless master; copy the .mp3 to the card."
