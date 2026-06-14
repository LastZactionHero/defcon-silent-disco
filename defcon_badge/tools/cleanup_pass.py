#!/usr/bin/env python3
"""cleanup_pass.py — one-shot board cleanup addressing user review feedback.

- Drops J32 (UART) + J33 (SWD) — USB-C bootsel covers programming.
- Bumps Y1 below U3 (was 1.9mm gap, body intrusion in render).
- Moves D20 IR LED inward from x=187.9 (off-edge) to x=185.
- Moves C44 away from C45 (was 0.5mm gap to electrolytic).
- Relocates R24+R25 (audio VGND bias divider) next to U21.
- Moves SW20-22 to right-side triangle formation (free space below J20).
- Adds PREV/PLAY/NEXT silk labels for the buttons.

Idempotent: each move sets absolute coords; silk labels are tagged with
a known UUID prefix so re-running replaces them.
"""
from __future__ import annotations
import re
import subprocess
import sys
import uuid
from pathlib import Path

PCB = Path("defcon_badge/defcon_badge.kicad_pcb")
SILK_TAG = "c1eanup1"  # uuid prefix for our cleanup silk

# Absolute target positions: refdes -> (x, y, rot or None for keep)
MOVES = {
    'Y1':  (141.5, 118.5, None),   # was 115; below U3 (U3 bottom y=113.1)
    'D20': (185.0, 110.0, None),   # was 187.9 (off-edge)
    'C44': (137.0, 110.0, None),   # was 146.5 (overlapping C45); move near U21 input
    'R24': (143.5, 100.5, None),   # VGND divider — next to U21
    'R25': (145.5, 100.5, None),
    'SW20': (174.0, 95.0, None),   # right-side triangle: top-left
    'SW21': (181.0, 95.0, None),   #                       top-right
    'SW22': (177.5, 104.0, None),  #                       bottom-center
}

# Silk labels: (text, x, y, size)
SILK = [
    ('PREV',   174.0, 100.5, 1.0),
    ('NEXT',   181.0, 100.5, 1.0),
    ('PLAY',   177.5, 108.5, 1.0),
]


def delete_footprint(text: str, refdes: str) -> tuple[str, bool]:
    pattern = rf'\(property "Reference" "{re.escape(refdes)}"'
    m = re.search(pattern, text)
    if not m:
        return text, False
    pos = m.start()
    depth = 0
    i = pos - 1
    while i >= 0:
        ch = text[i]
        if ch == ')':
            depth += 1
        elif ch == '(':
            if depth == 0:
                j = i + 1
                while j < len(text) and (text[j].isalnum() or text[j] == '_'):
                    j += 1
                token = text[i + 1:j]
                if token == 'footprint':
                    d2 = 1
                    k = i + 1
                    end = i + 1
                    while k < len(text):
                        if text[k] == '(':
                            d2 += 1
                        elif text[k] == ')':
                            d2 -= 1
                            if d2 == 0:
                                end = k + 1
                                break
                        k += 1
                    while end < len(text) and text[end] in '\t\n':
                        end += 1
                    start = i
                    while start > 0 and text[start - 1] == '\t':
                        start -= 1
                    return text[:start] + text[end:], True
            depth -= 1
        i -= 1
    return text, False


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


def move_footprint(text: str, refdes: str, x: float, y: float,
                   rot: float | None) -> str:
    """Set absolute (at X Y [R]) inside the footprint block."""
    span = find_footprint_block(text, refdes)
    if span is None:
        print(f"  {refdes}: not found")
        return text
    start, end = span
    block = text[start:end]
    # The footprint-level (at X Y [R]) is the first (at ...) line after
    # the `(layer ".Cu")` declaration. Match the first occurrence inside
    # block.
    pat = re.compile(r'(\(at )(-?\d+\.?\d*)\s+(-?\d+\.?\d*)(\s+(-?\d+\.?\d*))?(\))')
    # We want only the first match (footprint-level at).
    new_block, n = pat.subn(
        lambda m: (f"(at {x:.3f} {y:.3f}"
                   + (f" {rot}" if rot is not None
                      else (f" {m.group(5)}" if m.group(5) else ""))
                   + ")"),
        block, count=1
    )
    if n == 0:
        print(f"  {refdes}: no (at ...) found inside block")
        return text
    print(f"  {refdes}: moved to ({x}, {y})"
          + (f" rot={rot}" if rot is not None else ""))
    return text[:start] + new_block + text[end:]


def remove_old_silk(text: str) -> str:
    """Remove any gr_text whose uuid starts with our SILK_TAG (single-line)."""
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
    # Insert immediately before the final closing paren line
    idx = text.rfind('\n)')
    if idx < 0:
        idx = text.rfind(')')
        return text[:idx] + block + text[idx:]
    return text[:idx + 1] + block + text[idx + 1:]


def main() -> int:
    text = PCB.read_text()
    Path('defcon_badge/defcon_badge.kicad_pcb.pre_cleanup').write_text(text)

    print("== Delete debug headers ==")
    for ref in ('J32', 'J33'):
        text, ok = delete_footprint(text, ref)
        print(f"  delete {ref}: {'OK' if ok else 'NOT FOUND'}")

    print("== Move footprints ==")
    for ref, (x, y, rot) in MOVES.items():
        text = move_footprint(text, ref, x, y, rot)

    print("== Silk labels ==")
    text = remove_old_silk(text)
    for label, x, y, size in SILK:
        text = add_silk_text(text, label, x, y, size)
        print(f"  +silk '{label}' at ({x}, {y})")

    PCB.write_text(text)
    print("Wrote PCB. Verifying it still loads…")
    r = subprocess.run(
        ['kicad-cli', 'pcb', 'drc', '--format', 'report',
         '-o', '/tmp/drc.rpt', str(PCB)],
        capture_output=True
    )
    if r.returncode != 0:
        print("FAILED. Leaving modified PCB on disk for inspection.")
        print("stderr:", r.stderr.decode()[:1000])
        print("stdout:", r.stdout.decode()[:1000])
        return 1
    print("OK.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
