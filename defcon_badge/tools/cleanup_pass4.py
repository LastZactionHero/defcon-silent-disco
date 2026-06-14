#!/usr/bin/env python3
"""cleanup_pass4.py — power consolidation on left + button spread on right.

User feedback:
- Move J11 battery JST-PH to B.Cu so the battery mounts on the back.
- Put J11 near SW1 to consolidate power lines.
- Move U10 TP4056 charger + U11 LDO + their R/C parts to the left
  (currently right side, crowding).
- Move J31 microSD elsewhere on B.Cu (was overlapping J30 SAO area).
- Move J30 SAO to upper-left (off the power zone, off the microSD).
- Spread SW20-22 wider on the right side now that the right is clear.
"""
from __future__ import annotations
import re
import subprocess
import sys
import uuid
from pathlib import Path

PCB = Path("defcon_badge/defcon_badge.kicad_pcb")
SILK_TAG = "c1eanup1"

# Layer-preserving moves (set anchor to absolute coords)
MOVES = {
    # SAO header — upper-left, out of power zone
    'J30':  (110.0,  95.0, None),
    # microSD moves on B.Cu — right-back, out of the J11/SW1 corner
    'J31':  (160.0, 125.0, None),
    # Power cluster on left (between SW1 and J10 USB-C)
    'U10':  (135.0, 123.0, None),   # TP4056
    'U11':  (143.0, 123.0, None),   # LDO
    'C20':  (130.5, 123.0, None),   # bulk on U10 input
    'C22':  (139.5, 123.0, None),   # between U10 and U11
    'C23':  (146.5, 123.0, None),   # bulk on U11 output
    'R12':  (135.0, 120.0, None),   # PROG (2.4k) above U10
    'R13':  (142.0, 120.0, None),   # 100k above U11
    'R14':  (144.0, 120.0, None),
    'R15':  (146.0, 120.0, None),
    'R10':  (148.5, 132.0, None),   # USB-C CC1 pulldown, near J10
    'R11':  (150.5, 132.0, None),   # USB-C CC2 pulldown
    # C8 bulk for +1V1 (was where U10 is going)
    'C8':   (143.0, 116.0, None),
    # Buttons — wider triangle now (12mm SW20↔SW21)
    'SW20': (170.0,  96.0, None),
    'SW21': (182.0,  96.0, None),
    'SW22': (176.0, 104.0, None),
}

# Silk labels for buttons (follow new triangle)
SILK = [
    ('PREV',  170.0,  92.7, 0.9),
    ('NEXT',  182.0,  92.7, 0.9),
    ('PLAY',  176.0, 100.0, 0.9),
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
        print(f"  {refdes}: not found")
        return text
    start, end = span
    block = text[start:end]
    pat = re.compile(r'(\(at )(-?\d+\.?\d*)\s+(-?\d+\.?\d*)(\s+(-?\d+\.?\d*))?(\))')
    new_block, _ = pat.subn(
        lambda m: (f"(at {x:.3f} {y:.3f}"
                   + (f" {rot}" if rot is not None
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
        print(f"  removed {n} old cleanup silk labels")
    return new


def add_silk_text(text: str, label: str, x: float, y: float,
                  size: float) -> str:
    short = uuid.uuid4().hex[:24]
    uid = SILK_TAG + short
    block = (
        f'\t(gr_text "{label}" (at {x:.3f} {y:.3f} 0) '
        f'(layer "F.SilkS") (uuid "{uid}") '
        f'(effects (font (size {size:.2f} {size:.2f}) (thickness 0.2))))\n'
    )
    idx = text.rfind('\n)')
    return text[:idx + 1] + block + text[idx + 1:]


def main() -> int:
    text = PCB.read_text()
    Path('defcon_badge/defcon_badge.kicad_pcb.pre_cleanup4').write_text(text)

    print("== Move parts ==")
    for ref, (x, y, rot) in MOVES.items():
        text = set_fp_at(text, ref, x, y, rot)
        print(f"  {ref}: → ({x}, {y})")

    print("== Silk ==")
    text = remove_old_silk(text)
    for label, x, y, size in SILK:
        text = add_silk_text(text, label, x, y, size)

    PCB.write_text(text)
    r = subprocess.run(
        ['kicad-cli', 'pcb', 'drc', '--format', 'report',
         '-o', '/tmp/drc.rpt', str(PCB)], capture_output=True
    )
    if r.returncode != 0:
        print("FAILED. Restoring.")
        PCB.write_text(
            Path('defcon_badge/defcon_badge.kicad_pcb.pre_cleanup4').read_text())
        return 1
    print("OK.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
