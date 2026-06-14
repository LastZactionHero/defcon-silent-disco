#!/usr/bin/env python3
"""Delete orphan #PWR symbols in MCU_Core — power flags whose pin coords are
not touched by any wire or junction. These are the GND symbols left dangling
when the J3/J4 breakouts' wires were purged but the #PWR instances stayed."""
import re
import sys
from pathlib import Path

PROJECT = Path("/home/zach/dev/defcon_badge/defcon_badge")
SRC = PROJECT / "MCU_Core.kicad_sch"
TOL = 0.5  # mm tolerance for "wire endpoint touches pin"


def find_block_end(text: str, start: int) -> int:
    depth, j, in_str = 0, start, False
    while j < len(text):
        c = text[j]
        if c == '"' and (j == 0 or text[j - 1] != "\\"):
            in_str = not in_str
        elif not in_str:
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return j + 1
        j += 1
    raise ValueError


def main():
    text = SRC.read_text()

    # Collect every wire endpoint and junction coord.
    wire_endpoints: set[tuple[float, float]] = set()
    for m in re.finditer(
        r"\(wire[^)]*\(pts\s+\(xy\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\)\s+\(xy\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\)",
        text,
    ):
        for i in range(4):
            x, y = float(m.group(1 + (i // 2) * 2)), float(m.group(2 + (i // 2) * 2))
            wire_endpoints.add((round(x, 2), round(y, 2)))
    # Junctions
    for m in re.finditer(r"\(junction\s*\(at\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)", text):
        x, y = float(m.group(1)), float(m.group(2))
        wire_endpoints.add((round(x, 2), round(y, 2)))
    # Labels (a label position also counts as a "touched" coord since the symbol
    # could be on the same labeled net via name matching)
    for m in re.finditer(r'\(label[^)]*\(at\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)', text):
        x, y = float(m.group(1)), float(m.group(2))
        wire_endpoints.add((round(x, 2), round(y, 2)))
    # Hier_labels too
    for m in re.finditer(r'\(hierarchical_label[^)]*\(at\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)', text):
        x, y = float(m.group(1)), float(m.group(2))
        wire_endpoints.add((round(x, 2), round(y, 2)))

    def touched(x: float, y: float) -> bool:
        # Power symbol pin is at sym (0,0) so abs pin = instance position.
        for wx, wy in wire_endpoints:
            if abs(wx - x) < TOL and abs(wy - y) < TOL:
                return True
        return False

    # Walk top-level (symbol) instances. Drop power instances whose pin is
    # unreferenced.
    drop_ranges: list[tuple[int, int]] = []
    n_pwr_total = 0
    dropped_refs: list[str] = []
    for m in re.finditer(r"^\t\(symbol\n", text, re.MULTILINE):
        s = m.start()
        e = find_block_end(text, s)
        block = text[s:e]
        rm = re.search(r'\(property "Reference" "([^"]+)"', block)
        if not rm:
            continue
        ref = rm.group(1)
        if not ref.startswith("#PWR"):
            continue
        n_pwr_total += 1
        lm = re.search(r'\(lib_id "([^"]+)"', block)
        lib = lm.group(1) if lm else ""
        pm = re.search(r"\(at\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+\d+\)", block)
        if not pm:
            continue
        x, y = float(pm.group(1)), float(pm.group(2))
        if not touched(x, y):
            drop_ranges.append((s, e))
            dropped_refs.append(f"{ref} ({lib}) @ ({x:.2f}, {y:.2f})")

    print(f"  scanned {n_pwr_total} #PWR symbols", file=sys.stderr)
    print(f"  dropping {len(dropped_refs)} orphans:", file=sys.stderr)
    for r in dropped_refs:
        print(f"    - {r}", file=sys.stderr)

    if not drop_ranges:
        print("  nothing to drop", file=sys.stderr)
        return
    drop_ranges.sort(reverse=True)
    new_text = text
    for s, e in drop_ranges:
        end = e
        if end < len(new_text) and new_text[end] == "\n":
            end += 1
        new_text = new_text[:s] + new_text[end:]
    SRC.write_text(new_text)
    print(f"  wrote {SRC}", file=sys.stderr)


if __name__ == "__main__":
    main()
