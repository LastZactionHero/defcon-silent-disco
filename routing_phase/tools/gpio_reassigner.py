#!/usr/bin/env python3
"""gpio_reassigner.py — R2 upstream lever (approval-gated). See NEXT_PASS_PLAN move 1.

The failed pass-1 nets leave the RP2040 on pins facing the WRONG side (SD on top of the QFN, card
slot below). The RP2040's IO is firmware-flexible (PIO=any GPIO; SPI/I2C have multiple instances), so
re-assigning each bus to a pin facing its destination dissolves crossings AT THE SOURCE.

STATUS: the crossing ANALYSIS (the R2 exit-gate deliverable — "report current vs best-achievable
QFN-escape crossing count") is IMPLEMENTED. The pinmux-legal re-assignment solver + schematic
write-back are scaffolded (they need the RP2040 mux table + KRT schematic_updater.py, and they EDIT
the frozen schematic -> require explicit user sign-off, so they are intentionally not auto-run).

R2 recipe:
  1. analyze_crossings(board): for each U3 signal net, native side (pad location) vs destination side
     (net far-endpoint direction) -> count mismatches = the escape-crossing cost. IMPLEMENTED.
  2. [TODO/run] solve: build the GPIO->QFN-pin->side table from the RP2040 datasheet mux; for each
     firmware-flexible bus, pick the instance whose pin faces its destination (Hungarian, as KRT
     target_swap.py); honor fixed pins (QSPI bank, ADC-only GPIO26-29, 2 instances each SPI/I2C/UART).
  3. [TODO/run, APPROVAL-GATED] write back via KRT schematic_updater.py + re-sync nets
     (sync_nets_pcbnew.py); route_db re-escapes only moved nets.
PRIMARY (R2): escape-crossing count. Output: a ranked remap proposal + the quantified reduction for
the USER to adjudicate BEFORE any escape copper.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "placement_phase_2" / "tools"))
import geom_route   # noqa: E402

NM = 1_000_000
PLANES = {"GND", "+3V3", "+1V1"}


def _side(dx, dy):
    return ("right" if dx > 0 else "left") if abs(dx) >= abs(dy) else ("bottom" if dy > 0 else "top")


def analyze_crossings(board_path, ref="U3"):
    """For each signal net on `ref`: native side (pad) vs destination side (far endpoint). A mismatch
    is an escape that must cross to the far side = the congestion cost pass 1 failed on."""
    import pcbnew
    with geom_route.safe_board(board_path) as b:
        fp = next(f for f in b.GetFootprints() if f.GetReference() == ref)
        c = fp.GetPosition()
        # net -> far endpoint centroid (non-ref pads)
        far = {}
        for f in b.GetFootprints():
            if f.GetReference() == ref:
                continue
            for p in f.Pads():
                n = p.GetNetname()
                if not n or n in PLANES:
                    continue
                pos = p.GetPosition()
                far.setdefault(n, []).append((pos.x, pos.y))
        rows = []
        for p in fp.Pads():
            n = p.GetNetname()
            if not n or n in PLANES or n not in far:
                continue
            pos = p.GetPosition()
            native = _side(pos.x - c.x, pos.y - c.y)
            fx = sum(x for x, _ in far[n]) / len(far[n])
            fy = sum(y for _, y in far[n]) / len(far[n])
            dest = _side(fx - c.x, fy - c.y)
            rows.append({"net": n, "pad": p.GetNumber(), "native": native, "dest": dest,
                         "mismatch": native != dest})
    return rows


def report(board_path, ref="U3"):
    rows = analyze_crossings(board_path, ref)
    mism = [r for r in rows if r["mismatch"]]
    print(f"{ref}: {len(rows)} signal nets analysed; {len(mism)} cross-side (escape mismatch):")
    for r in sorted(mism, key=lambda r: r["net"]):
        print(f"   {r['net']:28} pad on {r['native']:6} but dest is {r['dest']:6}  <-- remap candidate")
    print(f"\nCROSSING COST (current) = {len(mism)}. Best-achievable needs the pinmux solver (R2 TODO);"
          f" PIO/flexible nets (SD_*, LED_*, I2S_*) can move to the destination side -> target ~0.")
    return rows


if __name__ == "__main__":
    report(sys.argv[1] if len(sys.argv) > 1 else "defcon_badge/defcon_badge.kicad_pcb")
