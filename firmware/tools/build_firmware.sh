#!/usr/bin/env bash
#
# build_firmware.sh -- build a custom MicroPython v1.28 firmware for the badge
# with the native MP3 decoder (picomp3lib / Helix) compiled in as a C module.
#
# Run this on a computer with the ARM toolchain (NOT on the badge). It clones
# MicroPython + picomp3lib + pico-sdk, builds, and drops firmware-mp3.uf2 in the
# firmware/ dir. Flash it by holding BOOTSEL, plugging in, and copying the .uf2
# onto the RPI-RP2 drive.
#
# Requires: git, cmake, make, python3, arm-none-eabi-gcc
#   macOS:  brew install cmake arm-none-eabi-gcc   (+ Xcode Command Line Tools)
#   Debian: sudo apt install cmake gcc-arm-none-eabi build-essential git python3
#
# Env overrides: BUILD_DIR, MPY_REF (default v1.28.0), BOARD (default RPI_PICO), JOBS
set -euo pipefail

FW_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$FW_DIR/.build}"
MPY_REF="${MPY_REF:-v1.28.0}"
BOARD="${BOARD:-RPI_PICO}"
JOBS="${JOBS:-4}"

echo "firmware dir : $FW_DIR"
echo "build dir    : $BUILD_DIR"
echo "micropython  : $MPY_REF    board: $BOARD    jobs: $JOBS"
echo

# --- tool checks ----------------------------------------------------------
missing=0
for t in git cmake make python3 arm-none-eabi-gcc; do
  if ! command -v "$t" >/dev/null 2>&1; then echo "MISSING tool: $t"; missing=1; fi
done
[ "$missing" = 0 ] || { echo; echo "Install the missing tool(s) and re-run."; exit 1; }

mkdir -p "$BUILD_DIR"

# --- vendor picomp3lib next to the C module (the cmake expects it here) ----
PICO_MP3="$FW_DIR/cmodules/mp3/picomp3lib"
if [ ! -d "$PICO_MP3/src" ]; then
  echo ">> cloning picomp3lib..."
  git clone --depth 1 https://github.com/ikjordan/picomp3lib "$PICO_MP3"
else
  echo ">> picomp3lib already present"
fi

# CRITICAL PATCH: Helix's static decoder buffers are 'char' arrays (alignment 1)
# cast to structs.  The linker can place them at odd addresses; on Cortex-M0+
# any word access through them is a HARD FAULT (verified on hardware: deinit and
# real decoding crashed the badge until this).  Force 4-byte alignment.
if ! grep -q "aligned(4)" "$PICO_MP3/src/buffers.c"; then
  echo ">> patching picomp3lib buffers.c: 4-byte-align static decoder buffers"
  sed -i.bak -E 's/static char ([A-Za-z_0-9]+)\[sizeof\(([A-Za-z_0-9]+)\)\];/static char \1[sizeof(\2)] __attribute__((aligned(4)));/' \
    "$PICO_MP3/src/buffers.c"
  rm -f "$PICO_MP3/src/buffers.c.bak"
fi

# --- MicroPython source ---------------------------------------------------
MPY="$BUILD_DIR/micropython"
if [ ! -d "$MPY/.git" ]; then
  echo ">> cloning MicroPython $MPY_REF..."
  git clone -b "$MPY_REF" --depth 1 https://github.com/micropython/micropython "$MPY"
else
  echo ">> MicroPython already cloned"
fi

echo ">> building mpy-cross..."
make -C "$MPY/mpy-cross" -j"$JOBS"

echo ">> fetching rp2 submodules (pico-sdk etc.) -- may take a while..."
make -C "$MPY/ports/rp2" BOARD="$BOARD" submodules

echo ">> building firmware with the mp3 user C module..."
make -C "$MPY/ports/rp2" BOARD="$BOARD" -j"$JOBS" \
  USER_C_MODULES="$FW_DIR/cmodules/micropython.cmake"

UF2="$MPY/ports/rp2/build-$BOARD/firmware.uf2"
if [ -f "$UF2" ]; then
  cp "$UF2" "$FW_DIR/firmware-mp3.uf2"
  echo
  echo "SUCCESS -> $FW_DIR/firmware-mp3.uf2"
  echo "Flash: hold BOOTSEL, plug the badge in, copy firmware-mp3.uf2 onto RPI-RP2."
  echo "Then re-deploy the .py files and put .mp3 files on the SD card."
else
  echo "Build finished but $UF2 was not produced -- check the output above."
  exit 1
fi
