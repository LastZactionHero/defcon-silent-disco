#!/usr/bin/env python3
"""cleanup_pass7.py — buttons on a downward arc + IR back to y=110.

Arc: a quarter-circle-ish curve sweeping from upper-right around the
right side and down to the lower-right. Center ~(170, 110), r ~12mm.

  SW20 (170,  98) — top of arc (apex)
  SW21 (180, 104) — upper-right
  SW22 (181, 116) — lower-right (passes D20 at y=110 on the outside)
  SW23 (170, 122) — bottom

IR pair returns to y=110 (the original pair-alignment line):
  D20  (180, 110)
  R30  (177, 110)
  U30  (104.4, 110)
"""
from __future__ import annotations
import re
import subprocess
import sys
import uuid
from pathlib import Path

PCB = Path("defcon_badge/defcon_badge.kicad_pcb")
SILK_TAG = "c1eanup1"

IR_MOVES = {
    'D20': (180.0, 110.0),
    'R30': (177.0, 110.0),
    'U30': (104.4, 110.0),
}

BUTTON_POS = {
    'SW20': (170.0,  98.0),   # Vol+    (apex)
    'SW21': (180.0, 104.0),   # Vol-    (upper-right)
    'SW22': (181.0, 116.0),   # Channel (lower-right)
    'SW23': (170.0, 122.0),   # Sync    (bottom)
}

SILK = [
    ('Vol+',    175.0,  93.5, 0.8),   # above SW20 (inside the J20 gap)
    ('Vol-',    185.0, 102.5, 0.7),
    ('Channel', 185.0, 117.5, 0.7),
    ('Sync',    175.0, 126.0, 0.8),   # below SW23
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


def main() -> int:
    text = PCB.read_text()
    Path('defcon_badge/defcon_badge.kicad_pcb.pre_cleanup7').write_text(text)

    print("== IR pair → y=110 ==")
    for ref, (x, y) in IR_MOVES.items():
        text = set_fp_at(text, ref, x, y, None)
        print(f"  {ref}: → ({x}, {y})")

    print("== Buttons → downward arc ==")
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
            Path('defcon_badge/defcon_badge.kicad_pcb.pre_cleanup7').read_text())
        return 1
    print("OK.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
