#!/usr/bin/env bash
#
# flash_badge.sh -- provision one badge, start to finish, then loop for the
# next one.  Built for the "flash 18 boards the night before DEFCON" workflow.
#
#   1. waits for a badge in BOOTSEL (RPI-RP2 volume)
#   2. flashes firmware-mp3-universal.uf2 -- works on BOTH flash vendors in
#      the run (the boot2 discriminates Winbond/Macronix at boot)
#   3. waits for MicroPython to enumerate
#   4. deploys the runtime .py set
#   5. verifies the imports actually resolve on the badge
#   6. resets it into the disco program
#
# Hard-won details encoded here so nobody re-learns them at 1 AM:
#   * plain `cp` of a UF2 SILENTLY FAILS on macOS -- data sits in the buffer
#     cache and never reaches the bootloader.  dd + sync works.
#   * success = the RPI-RP2 volume DISAPPEARING (bootloader accepted the image
#     and rebooted).  Volume still mounted = the write did not land.
#   * first boot on a virgin chip formats littlefs: CDC can take ~20 s.
#   * a FRESH flash has an empty filesystem, so there is no main.py to fight
#     mpremote for the REPL -- deploy just works.  (Re-provisioning a badge
#     that is already running disco is different: power-cycle it first.)
#
# Usage:
#   tools/flash_badge.sh          # one badge
#   tools/flash_badge.sh --loop   # badge after badge until ctrl-C
set -euo pipefail

cd "$(dirname "$0")/.."

UF2=firmware-mp3-universal.uf2
RUNTIME="config.py sk9822.py buttons.py dsp.py wavparse.py sdcard.py
         wavplayer.py discolights.py mp3player.py irsync.py linktest.py
         disco.py main.py"

[ -f "$UF2" ] || { echo "error: $UF2 not found (run from the repo)" >&2; exit 1; }
for f in $RUNTIME; do [ -f "$f" ] || { echo "error: missing $f" >&2; exit 1; }; done
python3 -m mpremote version >/dev/null 2>&1 || { echo "error: mpremote not available" >&2; exit 1; }

flash_one() {
  local n="$1"

  # One badge at a time: with two CDC devices attached the port detection
  # below grabs whichever enumerates first and deploys to the WRONG badge.
  if [ "$(ls /dev/cu.usbmodem* 2>/dev/null | wc -l)" -gt 0 ]; then
    echo "[$n] NOTE: a running badge is already on USB -- unplug it first" >&2
    while ls /dev/cu.usbmodem* >/dev/null 2>&1; do sleep 1; done
  fi

  echo "[$n] waiting for a badge in BOOTSEL (hold BOOTSEL / fit jumper, plug in)..."
  until [ -d /Volumes/RPI-RP2 ]; do sleep 1; done
  echo "[$n] BOOTSEL detected -- flashing $UF2"

  dd if="$UF2" of=/Volumes/RPI-RP2/fw.uf2 bs=1m 2>/dev/null
  sync
  local t=0
  while [ -d /Volumes/RPI-RP2 ]; do
    sleep 1; t=$((t + 1))
    if [ "$t" -ge 20 ]; then
      echo "[$n] ERROR: RPI-RP2 still mounted after 20 s -- the write did not land." >&2
      return 1
    fi
  done
  echo "[$n] bootloader accepted the image (volume unmounted)"

  echo "[$n] waiting for MicroPython CDC (first boot formats the fs, ~20 s)..."
  local port="" i=0
  while [ -z "$port" ]; do
    port=$(ls /dev/cu.usbmodem* 2>/dev/null | head -1 || true)
    [ -n "$port" ] && break
    sleep 1; i=$((i + 1))
    if [ "$i" -ge 60 ]; then
      echo "[$n] ERROR: no serial port after 60 s" >&2
      return 1
    fi
  done
  echo "[$n] serial: $port"
  sleep 2

  echo "[$n] deploying runtime..."
  # shellcheck disable=SC2086
  python3 -m mpremote connect "$port" fs cp $RUNTIME : >/dev/null

  echo "[$n] verifying..."
  python3 -m mpremote connect "$port" exec "
import os, config, disco, irsync, wavplayer
assert hasattr(irsync, 'set_drive'), 'stale irsync'
print('  files=%d themes=%d anims=%d cpu=%d ibuf=%d' % (
    len(os.listdir('/')), len(disco.THEMES), len(disco.ANIMS),
    config.CPU_FREQ, config.I2S_IBUF))
"
  python3 -m mpremote connect "$port" reset >/dev/null 2>&1 || true
  echo "[$n] DONE -- badge is booting disco.  Unplug it."

  # wait for THIS badge to leave the bus so --loop does not re-flash it
  while ls /dev/cu.usbmodem* >/dev/null 2>&1; do sleep 1; done
}

if [ "${1:-}" = "--loop" ]; then
  n=1
  while true; do
    flash_one "$n" || echo "[$n] failed -- fix and reinsert"
    n=$((n + 1))
  done
else
  flash_one 1
fi
