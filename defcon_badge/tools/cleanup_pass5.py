#!/usr/bin/env python3
"""cleanup_pass5.py — 4-button silent-disco layout.

- Add SW23 by cloning SW22's footprint block (new UUIDs, new refdes).
- Place SW20-23 in a 2×2 grid with a slight angle for visual interest.
- Replace PREV/NEXT/PLAY silk with Vol+/Vol-/Sync/Channel.
- Run spread.py at the end to legalize any cy overlap.

Button function mapping (silent disco UX):
  SW20 = Vol +      top-left
  SW21 = Vol -      top-right
  SW22 = Channel    bottom-left
  SW23 = Sync       bottom-right
"""
from __future__ import annotations

import re
import subprocess
import sys
import uuid
from pathlib import Path

PCB = Path("defcon_badge/defcon_badge.kicad_pcb")
SILK_TAG = "c1eanup1"  # reuse so prior labels are removed

# 2x2 grid with a 1mm downward tilt to the right ("slight angle")
BUTTON_POS = {
    'SW20': (171.0,  96.5),  # Vol+   (top-left); +1.5mm right to clear C46
    'SW21': (181.5,  97.5),  # Vol-   (top-right, 1mm lower for slight angle)
    'SW22': (172.5, 105.0),  # Channel (bottom-left)
    'SW23': (183.0, 106.0),  # Sync   (bottom-right)
}

SILK = [
    ('Vol+',     171.0,  93.0, 0.9),
    ('Vol-',     181.5,  94.0, 0.9),
    ('Channel',  172.5, 108.5, 0.9),
    ('Sync',     183.0, 109.5, 0.9),
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


def clone_footprint(text: str, src_ref: str, new_ref: str,
                    new_x: float, new_y: float) -> str:
    """Copy SW22's footprint block, change refdes + UUIDs + position."""
    span = find_footprint_block(text, src_ref)
    if span is None:
        raise RuntimeError(f"source {src_ref} not found")
    start, end = span
    src = text[start:end]

    # Re-UUID every uuid field so the clone doesn't collide.
    clone = re.sub(
        r'\(uuid "[0-9a-f-]+"\)',
        lambda m: f'(uuid "{uuid.uuid4()}")',
        src
    )
    # Update Reference property
    clone = re.sub(
        rf'\(property "Reference" "{re.escape(src_ref)}"',
        f'(property "Reference" "{new_ref}"',
        clone, count=1
    )
    # Update position
    clone = re.sub(
        r'(\(at )(-?\d+\.?\d*)\s+(-?\d+\.?\d*)(\s+-?\d+\.?\d*)?(\))',
        lambda m: f"(at {new_x:.3f} {new_y:.3f}"
                  + (m.group(4) or '') + ')',
        clone, count=1
    )

    # Insert clone right after the source block.
    # Need leading tab to match the file's indent style for footprints.
    insertion = "\n\t" + clone if not clone.startswith("\n") else clone
    # The src includes the (footprint ... ) starting with \t. Use same.
    insert_text = clone
    return text[:end] + "\n" + insert_text + text[end:]


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


def main() -> int:
    text = PCB.read_text()
    Path('defcon_badge/defcon_badge.kicad_pcb.pre_cleanup5').write_text(text)

    # Step 1: clone SW22 → SW23 if SW23 doesn't exist yet
    if find_footprint_block(text, 'SW23') is None:
        print("Cloning SW22 → SW23...")
        text = clone_footprint(text, 'SW22', 'SW23', *BUTTON_POS['SW23'])
    else:
        print("SW23 already exists; updating position")

    # Step 2: set all 4 button positions
    for ref, (x, y) in BUTTON_POS.items():
        text = set_fp_at(text, ref, x, y, None)
        print(f"  {ref}: → ({x}, {y})")

    # Step 3: replace silk
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
            Path('defcon_badge/defcon_badge.kicad_pcb.pre_cleanup5').read_text())
        print("stderr:", r.stderr.decode()[:500])
        return 1
    print("OK.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
