#!/usr/bin/env python3
"""Delete the inherited RP2040-minimal connectors + LDO from MCU_Core.kicad_sch.

Targets refs: J1 (USB-Micro), J2 (1×2 power), J3, J4 (36-pin breakouts), U1 (NCP1117).
Also drops the no_connect markers, junctions, and wires whose endpoints overlap the
deleted symbols' approximate bounding boxes — best-effort, not exhaustive. The user
will clean up any leftover floating wires in the KiCad GUI.

Operates by paren-balanced block deletion on the s-expression text. No reformat.
"""
import re
import sys
from pathlib import Path

PROJECT = Path("/home/zach/dev/defcon_badge/defcon_badge")
SRC = PROJECT / "MCU_Core.kicad_sch"
DROP_REFS = {"J1", "J2", "J3", "J4", "U1"}


def find_block_end(text: str, start: int) -> int:
    """Given start index pointing at an opening '(' line, return index just past
    the matching ')'. Honors quoted strings."""
    depth = 0
    i = start
    in_str = False
    while i < len(text):
        c = text[i]
        if c == '"' and (i == 0 or text[i - 1] != "\\"):
            in_str = not in_str
        elif not in_str:
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return i + 1
        i += 1
    raise ValueError(f"Unbalanced at offset {start}")


def find_instance_blocks(text: str):
    """Yield (start, end, ref) for every top-level (symbol …) instance."""
    # Top-level instances begin with "\t(symbol\n" (literal newline) — distinct
    # from the lib_symbols entries which begin with "\t\t(symbol \"…\"".
    for m in re.finditer(r"^\t\(symbol\n", text, re.MULTILINE):
        start = m.start()
        end = find_block_end(text, start)
        block = text[start:end]
        rm = re.search(r'\(property "Reference" "([^"]+)"', block)
        ref = rm.group(1) if rm else None
        yield start, end, ref


def get_instance_position(block: str) -> tuple[float, float] | None:
    m = re.search(r"\(at\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+\d+\)", block)
    if m:
        return (float(m.group(1)), float(m.group(2)))
    return None


# Approximate bounding-box span (mm) per legacy component type for sweeping
# nearby orphans. Generous on purpose — false positives just delete some
# decoration wires that the user can re-add if needed.
BBOX_RADIUS = {
    "J1": 18,   # USB-Micro is wide
    "J2": 6,
    "J3": 60,   # 2×18 header is tall
    "J4": 60,
    "U1": 12,
}


def main():
    text = SRC.read_text()
    drop_ranges: list[tuple[int, int]] = []
    drop_positions: list[tuple[float, float, str]] = []
    kept_refs = []

    for start, end, ref in find_instance_blocks(text):
        if ref in DROP_REFS:
            pos = get_instance_position(text[start:end])
            print(f"  drop instance: {ref} at {pos}", file=sys.stderr)
            drop_ranges.append((start, end))
            if pos:
                drop_positions.append((pos[0], pos[1], ref))
        else:
            kept_refs.append(ref)

    if not drop_ranges:
        print("Nothing to drop. Already clean?", file=sys.stderr)
        return

    # Sort by descending start so we can splice without offset shifts.
    drop_ranges.sort(reverse=True)
    new_text = text
    for s, e in drop_ranges:
        # Also eat the trailing newline so we don't leave blank lines piling up.
        end = e
        while end < len(new_text) and new_text[end] == "\n":
            end += 1
            break
        new_text = new_text[:s] + new_text[end:]

    # Best-effort: drop wires / junctions / labels / no_connects whose endpoints
    # fall inside the deleted components' bounding boxes.
    def in_drop_bbox(x: float, y: float) -> str | None:
        for dx, dy, ref in drop_positions:
            r = BBOX_RADIUS.get(ref, 10)
            if abs(x - dx) <= r and abs(y - dy) <= r:
                return ref
        return None

    def strip_blocks(text: str, head_regex: str, get_point) -> tuple[str, int]:
        """Walk top-level blocks matching head_regex; drop any whose extracted
        (x, y) falls inside any drop bbox. Returns (new_text, n_dropped)."""
        drops = []
        for m in re.finditer(head_regex, text, re.MULTILINE):
            s = m.start()
            e = find_block_end(text, s)
            block = text[s:e]
            pt = get_point(block)
            if pt is None:
                continue
            x, y = pt
            hit = in_drop_bbox(x, y)
            if hit:
                drops.append((s, e, hit))
        drops.sort(reverse=True)
        new = text
        for s, e, _ in drops:
            end = e
            if end < len(new) and new[end] == "\n":
                end += 1
            new = new[:s] + new[end:]
        return new, len(drops)

    # Wire: (wire (pts (xy X1 Y1) (xy X2 Y2)) …) — drop if EITHER endpoint inside.
    def wire_pt(block: str):
        m = re.search(r"\(pts\s+\(xy\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\)\s+\(xy\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\)", block)
        if not m:
            return None
        x1, y1, x2, y2 = (float(m.group(i)) for i in (1, 2, 3, 4))
        # Return whichever endpoint falls inside a bbox first
        for x, y in ((x1, y1), (x2, y2)):
            if in_drop_bbox(x, y):
                return (x, y)
        return None

    new_text, n_wires = strip_blocks(new_text, r"^\t\(wire\b", wire_pt)
    print(f"  dropped {n_wires} wires touching legacy bbox", file=sys.stderr)

    def at_pt(block: str):
        m = re.search(r"\(at\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)", block)
        if m:
            return (float(m.group(1)), float(m.group(2)))
        return None

    new_text, n_jct = strip_blocks(new_text, r"^\t\(junction\b", at_pt)
    print(f"  dropped {n_jct} junctions touching legacy bbox", file=sys.stderr)
    new_text, n_lbl = strip_blocks(new_text, r'^\t\(label\b', at_pt)
    print(f"  dropped {n_lbl} labels touching legacy bbox", file=sys.stderr)
    new_text, n_nc = strip_blocks(new_text, r'^\t\(no_connect\b', at_pt)
    print(f"  dropped {n_nc} no_connects touching legacy bbox", file=sys.stderr)

    SRC.write_text(new_text)
    print(f"wrote {SRC}", file=sys.stderr)
    print(f"kept {len(kept_refs)} other instances", file=sys.stderr)


if __name__ == "__main__":
    main()
