#!/usr/bin/env python3
"""flip_footprint.py REFDES X Y [ROT] — flip a footprint to the back side.

KiCad's "Flip" command does three things:
  1. Change the footprint's top-level (layer) from F.Cu to B.Cu.
  2. Swap every internal F.* layer reference to its B.* counterpart
     (F.SilkS↔B.SilkS, F.Mask↔B.Mask, F.Paste↔B.Paste, F.Fab↔B.Fab,
     F.CrtYd↔B.CrtYd, and pad layer lists).
  3. Set a new anchor position with the desired rotation.

KiCad mirrors the rendering on B.Cu — internal sub-element coordinates
stay the same; mirroring is implicit because the part is "viewed from
the back".

Usage: tools/flip_footprint.py J31 143 120 180
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PCB = REPO / "defcon_badge" / "defcon_badge.kicad_pcb"

# Order matters — swap must use placeholder to avoid double-swapping.
SWAPS = [
    ("F.Cu", "B.Cu"),
    ("F.SilkS", "B.SilkS"),
    ("F.Mask", "B.Mask"),
    ("F.Paste", "B.Paste"),
    ("F.Fab", "B.Fab"),
    ("F.CrtYd", "B.CrtYd"),
    ("F.Adhes", "B.Adhes"),
]


def swap_layers(text: str) -> str:
    """Bidirectional F.*↔B.* swap. Use unique placeholders to avoid clobber."""
    for f, b in SWAPS:
        text = text.replace(f, f"__FLIP_{f}__")
    for f, b in SWAPS:
        text = text.replace(b, f)
    for f, b in SWAPS:
        text = text.replace(f"__FLIP_{f}__", b)
    return text


def main() -> int:
    if len(sys.argv) not in (4, 5):
        print(__doc__, file=sys.stderr)
        return 2
    refdes = sys.argv[1]
    x = float(sys.argv[2])
    y = float(sys.argv[3])
    rot = float(sys.argv[4]) if len(sys.argv) == 5 else 0.0

    text = PCB.read_text()
    shutil.copy2(PCB, PCB.with_suffix(PCB.suffix + ".pre_flip_backup"))

    chunks = re.split(r"(\n\t\(footprint )", text)
    out = [chunks[0]]
    flipped = False
    i = 1
    while i < len(chunks):
        body = chunks[i + 1] if i + 1 < len(chunks) else ""
        if f'(property "Reference" "{refdes}"' in body:
            body = swap_layers(body)
            # Update anchor position
            body = re.sub(
                r"\n\t\t\(at [\d.\-]+ [\d.\-]+(?: [\d.\-]+)?\)",
                f"\n\t\t(at {x:.3f} {y:.3f} {rot:.0f})",
                body,
                count=1,
            )
            flipped = True
        out.append(chunks[i])
        out.append(body)
        i += 2

    PCB.write_text("".join(out))
    if not flipped:
        print(f"FAIL: refdes {refdes} not found", file=sys.stderr)
        return 1
    print(f"Flipped {refdes} to B.Cu at ({x}, {y}) rot {rot}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
