#!/usr/bin/env python3
"""Add wire stubs + matching flat-labels to each hierarchical_label in MCU_Core
so they're no longer dangling. Decides stub direction based on which sheet edge
the hier_label sits on (left edge → stub right, right edge → stub left)."""
import re
import sys
import uuid
from pathlib import Path

PROJECT = Path("/home/zach/dev/defcon_badge/defcon_badge")
SRC = PROJECT / "MCU_Core.kicad_sch"
STUB = 2.54


def new_uuid() -> str:
    return str(uuid.uuid4())


def main():
    text = SRC.read_text()

    # Find all hierarchical_labels and capture (name, x, y, end_offset).
    pattern = re.compile(
        r'^\t\(hierarchical_label\s+"([^"]+)"[\s\S]*?\(at\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+(\d+)\)',
        re.MULTILINE,
    )
    hier_labels = []
    for m in pattern.finditer(text):
        name = m.group(1)
        x = float(m.group(2))
        y = float(m.group(3))
        rot = int(m.group(4))
        hier_labels.append((name, x, y, rot))
    print(f"  found {len(hier_labels)} hierarchical_labels", file=sys.stderr)

    # A3 sheet is 420 wide. Anything x < 60 is "left edge"; anything x > 360 is "right edge".
    inject_lines: list[str] = []
    for name, x, y, rot in hier_labels:
        if x < 60:
            ex, ey = x + STUB, y
        elif x > 360:
            ex, ey = x - STUB, y
        else:
            # middle — pick by rotation (text direction)
            ex, ey = (x + STUB, y) if rot == 0 else (x - STUB, y)
        # Wire from (x, y) to (ex, ey)
        inject_lines.append(
            f'\t(wire (pts (xy {x:.2f} {y:.2f}) (xy {ex:.2f} {ey:.2f}))'
            f' (stroke (width 0) (type default)) (uuid "{new_uuid()}"))'
        )
        # Flat label of same name at stub end
        inject_lines.append(
            f'\t(label "{name}" (at {ex:.2f} {ey:.2f} {rot})'
            f' (effects (font (size 1.27 1.27)) (justify left bottom))'
            f' (uuid "{new_uuid()}"))'
        )

    if not inject_lines:
        print("  nothing to add", file=sys.stderr)
        return

    injection = "\n".join(inject_lines) + "\n"
    marker = "\t(sheet_instances"
    idx = text.find(marker)
    if idx < 0:
        raise RuntimeError("no (sheet_instances")
    new_text = text[:idx] + injection + text[idx:]
    SRC.write_text(new_text)
    print(f"  injected {len(inject_lines)} lines (1 wire + 1 label per hier_label)",
          file=sys.stderr)


if __name__ == "__main__":
    main()
