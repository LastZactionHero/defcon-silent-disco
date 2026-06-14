#!/usr/bin/env python3
"""cleanup_pass3.py — fix overlaps revealed by check_courtyards.

- SW20 was overlapping J20 audio jack body — slide button cluster down
  4mm so SW20 clears J20 bottom edge.
- C1 was inside U3 body (shift-left moved U3 over it).
- C8 was overlapping Y1 crystal.
- R3+R4 were 0.4mm apart from each other — separate them.
- Move U2 up by 2mm so the U3 top-edge cap ring clears its body.
- R5, R3, R4, C40 follow U2.
- R23 overlapping U21 — slide down off the amp.
- C23 overlapping U11 LDO — slide right.
- Update silk labels to follow new button positions (now to right of each
  button instead of below).
"""
from __future__ import annotations
import re
import subprocess
import sys
import uuid
from pathlib import Path

PCB = Path("defcon_badge/defcon_badge.kicad_pcb")
SILK_TAG = "c1eanup1"

# Move U2 + companions up so they clear the U3 top-edge cap ring.
INDIVIDUAL_MOVES = {
    'U2':   (135.4, 101.5, None),   # up 2.3mm
    'R5':   (132.0, 101.5, None),   # left of U2
    'R3':   (137.5, 103.5, None),   # spread from R4
    'R4':   (139.5, 103.5, None),   # spread from R3
    'C40':  (135.5, 103.5, None),   # follow U2
    'C1':   (130.0, 113.0, None),   # was inside U3 body
    'C8':   (137.5, 121.5, None),   # was over Y1
    # Audio
    'R23':  (144.5, 102.0, None),   # below U21, clear of R24/R25
    'R24':  (143.0, 100.5, None),   # nudge left for C45 clearance
    'R25':  (144.5, 100.5, None),
    # Charger area
    'C23':  (170.5, 121.5, None),   # right of U11
    'C20':  (152.5, 121.5, None),   # nudge left for U10 clearance
    'C17':  (133.0, 119.0, None),   # below Y1, clear courtyard
    # Buttons — triangle. D20 is locked at y=110 for IR pair alignment.
    # Spacing 11mm between top row to clear courtyards (TS-1187A
    # courtyard extends 2.1mm beyond body so 8.5mm min anchor spacing).
    'SW20': (170.0,  97.0, None),   # top-left — x≥170 to clear C46 audio cap
    'SW21': (179.0,  97.0, None),   # top-right (9mm spacing clears courtyards)
    'SW22': (174.5, 105.0, None),   # bottom-center (downward triangle)
}

SILK = [
    ('PREV',  170.0,  92.7, 0.9),
    ('NEXT',  179.0,  92.7, 0.9),
    ('PLAY',  174.5, 100.7, 0.9),
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
    Path('defcon_badge/defcon_badge.kicad_pcb.pre_cleanup3').write_text(text)

    print("== Move parts ==")
    for ref, (x, y, rot) in INDIVIDUAL_MOVES.items():
        text = set_fp_at(text, ref, x, y, rot)
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
            Path('defcon_badge/defcon_badge.kicad_pcb.pre_cleanup3').read_text())
        return 1
    print("OK.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
