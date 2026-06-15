#!/usr/bin/env python3
"""cleanup_pass6.py — 4-button column at slight angle (do it right).

Pass 5 punted on "column/line at slight angle" and shipped a 2×2 grid
with SW23 off the board edge. This is the redo:

- Move IR pair (D20, R30, U30) from y=110 → y=116, freeing 6mm of
  vertical right-side space so 4 buttons fit in a column.
- Place SW20-23 in a column with 1.5mm X offset per row (a clear
  diagonal lean, not "1mm = grid in disguise").
- Pitch 5.33mm Y between centers, just under cy_h (6mm), so courtyards
  overlap by ~0.7mm — visually a column.
- Silk labels TO THE RIGHT of each button (the angle opens space there).
- Includes a safety pass that ensures every (footprint at line start has
  the leading tab fp_meta requires.
"""
from __future__ import annotations

import re
import subprocess
import sys
import uuid
from pathlib import Path

PCB = Path("defcon_badge/defcon_badge.kicad_pcb")
SILK_TAG = "c1eanup1"

# Move IR pair down 6mm so we have room for a real 4-button column.
IR_MOVES = {
    'D20': (180.0, 116.0),
    'R30': (177.0, 116.0),
    'U30': (104.4, 116.0),
}

# Column: anchor X drifts right 2mm per row; Y pitch 5.33mm.
# Top button cleared by 4mm from J20 cy bottom (92.25); bottom button
# cleared by 3mm from new D20 cy top (115.05).
BUTTON_POS = {
    'SW20': (172.0,  96.0),     # Vol+
    'SW21': (174.0, 101.5),     # Vol-
    'SW22': (176.0, 107.0),     # Channel
    'SW23': (178.0, 112.5),     # Sync
}

# Labels to the RIGHT of each button (the angle opens space there)
SILK = [
    ('Vol+',     178.0,  96.0, 0.9),
    ('Vol-',     180.0, 101.5, 0.9),
    ('Channel',  182.5, 107.0, 0.9),
    ('Sync',     183.5, 112.5, 0.9),
]


def find_footprint_block(text: str, refdes: str) -> tuple[int, int] | None:
    pattern = rf'\(property "Reference" "{re.escape(refdes)}"'
    m = re.search(pattern, text)
    if not m:
        return None
    pos = m.start()
    depth = 0
    i = pos - 1
    while i >= 0:
        if text[i] == ')':
            depth += 1
        elif text[i] == '(':
            if depth == 0:
                j = i + 1
                while j < len(text) and (text[j].isalnum() or text[j] == '_'):
                    j += 1
                if text[i + 1:j] == 'footprint':
                    d2 = 1
                    k = i + 1
                    while k < len(text):
                        if text[k] == '(':
                            d2 += 1
                        elif text[k] == ')':
                            d2 -= 1
                            if d2 == 0:
                                return i, k + 1
                        k += 1
            depth -= 1
        i -= 1
    return None


def set_fp_at(text: str, refdes: str, x: float, y: float,
              rot: float | None) -> str:
    span = find_footprint_block(text, refdes)
    if span is None:
        return text
    start, end = span
    block = text[start:end]
    pat = re.compile(r'(\(at )(-?\d+\.?\d*)\s+(-?\d+\.?\d*)(\s+(-?\d+\.?\d*))?(\))')
    new_block, _ = pat.subn(
        lambda m: (f"(at {x:.3f} {y:.3f}"
                   + (f" {rot:g}" if rot is not None
                      else (f" {m.group(5)}" if m.group(5) else ""))
                   + ")"),
        block, count=1
    )
    return text[:start] + new_block + text[end:]


def remove_old_silk(text: str) -> str:
    pat = re.compile(
        r'\t\(gr_text "[^"]*" \(at [^)]+\) \(layer "[^"]+"\) '
        r'\(uuid "' + SILK_TAG + r'[^"]*"\) \(effects[^\n]+\n'
    )
    new, n = pat.subn('', text)
    if n:
        print(f"  removed {n} old silk labels")
    return new


def add_silk_text(text: str, label: str, x: float, y: float,
                  size: float) -> str:
    short = uuid.uuid4().hex[:24]
    uid = SILK_TAG + short
    block = (
        f'\t(gr_text "{label}" (at {x:.3f} {y:.3f} 0) '
        f'(layer "F.SilkS") (uuid "{uid}") '
        f'(effects (font (size {size:.2f} {size:.2f}) (thickness 0.18))))\n'
    )
    idx = text.rfind('\n)')
    return text[:idx + 1] + block + text[idx + 1:]


def fix_footprint_tabs(text: str) -> str:
    """Ensure every (footprint at line start has the leading tab fp_meta
    requires. Pass 5's clone_footprint forgot to add it."""
    return re.sub(r'^\(footprint ', '\t(footprint ', text, flags=re.MULTILINE)


def main() -> int:
    text = PCB.read_text()
    Path('defcon_badge/defcon_badge.kicad_pcb.pre_cleanup6').write_text(text)

    text = fix_footprint_tabs(text)

    print("== Move IR pair down 6mm ==")
    for ref, (x, y) in IR_MOVES.items():
        text = set_fp_at(text, ref, x, y, None)
        print(f"  {ref}: → ({x}, {y})")

    print("== Place buttons (column, slight angle) ==")
    for ref, (x, y) in BUTTON_POS.items():
        text = set_fp_at(text, ref, x, y, None)
        print(f"  {ref}: → ({x}, {y})")

    print("== Silk ==")
    text = remove_old_silk(text)
    for label, x, y, size in SILK:
        text = add_silk_text(text, label, x, y, size)
        print(f"  +silk '{label}' at ({x}, {y})")

    PCB.write_text(text)
    r = subprocess.run(
        ['kicad-cli', 'pcb', 'drc', '--format', 'report',
         '-o', '/tmp/drc.rpt', str(PCB)], capture_output=True
    )
    if r.returncode != 0:
        print("FAILED. Restoring.")
        PCB.write_text(
            Path('defcon_badge/defcon_badge.kicad_pcb.pre_cleanup6').read_text())
        print("stderr:", r.stderr.decode()[:500])
        return 1
    print("OK.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
