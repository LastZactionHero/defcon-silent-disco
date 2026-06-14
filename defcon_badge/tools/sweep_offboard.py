#!/usr/bin/env python3
"""sweep_offboard.py — move every footprint to a staging grid off-board.

Used before a fresh placement pass. Lays out all footprints in a tidy
grid below the board so we can verify the outline is correct and then
re-place each subsystem deliberately.

Preserves mounting hole positions (those are intentional, edge-bound).
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

PCB = Path("defcon_badge/defcon_badge.kicad_pcb")

STAGING_X0 = 50
STAGING_Y0 = 200
COL_PITCH = 10
ROW_PITCH = 8
COLS = 14


def main() -> int:
    text = PCB.read_text()
    shutil.copy2(PCB, PCB.with_suffix(PCB.suffix + ".pre_sweep_backup"))

    chunks = re.split(r"(\n\t\(footprint )", text)
    out = [chunks[0]]
    i = 1
    n = 0
    swept = []
    while i < len(chunks):
        body = chunks[i + 1] if i + 1 < len(chunks) else ""
        m_ref = re.search(r'\(property "Reference" "([^"]+)"', body)
        refdes = m_ref.group(1) if m_ref else None

        # Skip mounting holes — keep them where they are (corner-bound).
        if refdes and refdes.startswith("H"):
            out.append(chunks[i]); out.append(body); i += 2; continue
        # Skip non-component refdes (shouldn't happen)
        if not refdes:
            out.append(chunks[i]); out.append(body); i += 2; continue

        col = n % COLS
        row = n // COLS
        x = STAGING_X0 + col * COL_PITCH
        y = STAGING_Y0 + row * ROW_PITCH
        new_at = f"(at {x:.3f} {y:.3f} 0)"

        # Replace existing top-level (at ...)
        new_body, k = re.subn(
            r"\n\t\t\(at [\d.\-]+ [\d.\-]+(?: [\d.\-]+)?\)",
            f"\n\t\t{new_at}", body, count=1,
        )
        if k == 0:
            # Inject after first (layer "F.Cu" or "B.Cu")
            new_body, k = re.subn(
                r'(\(layer "[FB]\.Cu"\)\n)',
                rf"\1\t\t{new_at}\n", body, count=1,
            )
        if k:
            swept.append((refdes, x, y))
            n += 1
            out.append(chunks[i]); out.append(new_body)
        else:
            out.append(chunks[i]); out.append(body)
        i += 2

    PCB.write_text("".join(out))
    print(f"Swept {len(swept)} footprints to staging grid at "
          f"({STAGING_X0},{STAGING_Y0}), pitch=({COL_PITCH},{ROW_PITCH})")
    print(f"  refdes order: {', '.join(r for r,_,_ in swept[:15])}...")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
