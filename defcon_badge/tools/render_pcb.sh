#!/usr/bin/env bash
# render_pcb.sh — Generate annotated PCB views for visual inspection.
#
# Usage:
#   tools/render_pcb.sh              # default views
#   tools/render_pcb.sh --quick      # just the assembly view
#   tools/render_pcb.sh --routing    # adds copper-only views (F.Cu, B.Cu)
#
# Outputs to renders/ at repo root:
#   renders/top.svg       — Edge.Cuts + F.Cu + F.Silk + F.Mask + F.Fab
#   renders/bottom.svg    — Edge.Cuts + B.Cu + B.Silk + B.Mask (mirrored)
#   renders/assembly.svg  — F.Fab + F.Silk + Edge.Cuts (placement view)
#   renders/all.svg       — Everything
#   renders/top.png       — PNG raster of top.svg (1600px wide)
#   renders/assembly.png  — PNG raster of assembly.svg
#
# The PNGs are what the iteration loop reads.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PCB="${REPO_ROOT}/defcon_badge/defcon_badge.kicad_pcb"
OUT="${REPO_ROOT}/renders"

if [[ ! -f "$PCB" ]]; then
  echo "PCB not found: $PCB" >&2
  exit 1
fi

mkdir -p "$OUT"

QUICK=0
ROUTING=0
for arg in "$@"; do
  case "$arg" in
    --quick) QUICK=1 ;;
    --routing) ROUTING=1 ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

plot() {
  local name="$1"; shift
  local layers="$1"; shift
  local extra=("$@")
  kicad-cli pcb export svg \
    --output "$OUT/$name.svg" \
    --layers "$layers" \
    --page-size-mode 2 \
    --exclude-drawing-sheet \
    --mode-single \
    "${extra[@]}" \
    "$PCB" >/dev/null
}

png() {
  local base="$1"
  if command -v rsvg-convert >/dev/null 2>&1; then
    rsvg-convert -w 1600 "$OUT/$base.svg" -o "$OUT/$base.png"
  elif command -v inkscape >/dev/null 2>&1; then
    inkscape "$OUT/$base.svg" --export-type=png --export-width=1600 \
      --export-filename="$OUT/$base.png" >/dev/null 2>&1
  else
    echo "WARN: neither rsvg-convert nor inkscape found; skipping PNG for $base" >&2
  fi
}

echo "Rendering assembly view..."
plot assembly "Edge.Cuts,F.Silkscreen,F.Fab" --sketch-pads-on-fab-layers
png assembly

if [[ "$QUICK" -eq 1 ]]; then
  echo "Done (quick): $OUT/assembly.svg"
  exit 0
fi

echo "Rendering top view..."
plot top "Edge.Cuts,F.Cu,F.Silkscreen,F.Mask,F.Paste,F.Fab"
png top

echo "Rendering bottom view..."
plot bottom "Edge.Cuts,B.Cu,B.Silkscreen,B.Mask,B.Fab" --mirror
png bottom

if [[ "$ROUTING" -eq 1 ]]; then
  echo "Rendering copper-only views..."
  plot copper_top "Edge.Cuts,F.Cu"
  plot copper_bot "Edge.Cuts,B.Cu" --mirror
  png copper_top
  png copper_bot
fi

echo "Rendering all-layers view..."
plot all "Edge.Cuts,F.Cu,B.Cu,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,F.Fab,B.Fab,F.Paste,B.Paste,User.Comments,User.Drawings"
png all

echo "Done. Renders in: $OUT"
ls -1 "$OUT"
