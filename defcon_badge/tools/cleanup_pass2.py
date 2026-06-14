#!/usr/bin/env python3
"""cleanup_pass2.py — second review-feedback pass.

- Shift U3 RP2040 cluster (U3 + all decoupling caps within 7mm) left by
  5mm to give breathing room around the audio caps.
- Special-case C44 to its proper home next to U21 (audio AC coupling).
- Pull D20 IR LED + R30 series resistor further from the right sawtooth.
- Rearrange SW20-22 buttons into a diagonal line (top-left → bottom-right)
  with PREV / PLAY / NEXT silk labels.
- Move J30 SAO header next to SW1 in the bottom-left, off the IC cluster.
"""
from __future__ import annotations
import math
import re
import subprocess
import sys
import uuid
from pathlib import Path

PCB = Path("defcon_badge/defcon_badge.kicad_pcb")
SILK_TAG = "c1eanup1"  # reuse so prior labels are replaced

# Current U3 anchor; everything within RADIUS mm of this point gets
# shifted by SHIFT.
U3_CENTER = (141.9, 109.6)
RADIUS = 7.0
SHIFT = (-5.0, 0.0)

# Components excluded from the cluster shift (move them individually).
EXCLUDED = {'C44'}

# Absolute target positions: refdes -> (x, y, rot or None)
INDIVIDUAL_MOVES = {
    'C44':  (139.0, 100.5, None),   # next to U21 audio amp
    'D20':  (180.0, 110.0, None),   # was 185 (still close to sawtooth)
    'R30':  (177.0, 110.0, None),   # series with D20
    'SW20': (172.0, 92.0, None),    # diagonal: top-left
    'SW21': (177.5, 99.0, None),    # diagonal: middle
    'SW22': (183.0, 106.0, None),   # diagonal: bottom-right
    'J30':  (123.0, 121.0, None),   # near SW1, off the IC cluster
}

# (text, x, y, size)
SILK = [
    ('PREV',  172.0,  88.0, 1.0),   # above SW20 (top of diagonal)
    ('PLAY',  177.5,  95.0, 1.0),   # above SW21 (middle of diagonal)
    ('NEXT',  183.0, 110.5, 1.0),   # below SW22 (bottom of diagonal)
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


def fp_at(text: str, refdes: str) -> tuple[float, float, float | None]:
    span = find_footprint_block(text, refdes)
    if span is None:
        raise KeyError(refdes)
    block = text[span[0]:span[1]]
    m = re.search(r'\(at (-?\d+\.?\d*)\s+(-?\d+\.?\d*)(?:\s+(-?\d+\.?\d*))?\)',
                  block)
    if not m:
        raise ValueError(f"no (at ...) in {refdes}")
    return float(m.group(1)), float(m.group(2)), \
        (float(m.group(3)) if m.group(3) else None)


def set_fp_at(text: str, refdes: str, x: float, y: float,
              rot: float | None) -> str:
    span = find_footprint_block(text, refdes)
    if span is None:
        print(f"  {refdes}: not found")
        return text
    start, end = span
    block = text[start:end]
    pat = re.compile(r'(\(at )(-?\d+\.?\d*)\s+(-?\d+\.?\d*)(\s+(-?\d+\.?\d*))?(\))')
    new_block, n = pat.subn(
        lambda m: (f"(at {x:.3f} {y:.3f}"
                   + (f" {rot}" if rot is not None
                      else (f" {m.group(5)}" if m.group(5) else ""))
                   + ")"),
        block, count=1
    )
    if n == 0:
        print(f"  {refdes}: no (at ...) found")
        return text
    return text[:start] + new_block + text[end:]


def list_refdes(text: str) -> list[str]:
    """All refdes in the PCB."""
    return list(set(re.findall(r'\(property "Reference" "([^"]+)"', text)))


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
    Path('defcon_badge/defcon_badge.kicad_pcb.pre_cleanup2').write_text(text)

    print("== Identify U3 cluster ==")
    all_refs = list_refdes(text)
    cluster = []
    for ref in all_refs:
        if ref in EXCLUDED:
            continue
        if ref in INDIVIDUAL_MOVES:
            continue
        try:
            x, y, _ = fp_at(text, ref)
        except (KeyError, ValueError):
            continue
        if math.hypot(x - U3_CENTER[0], y - U3_CENTER[1]) <= RADIUS:
            cluster.append(ref)
    cluster.sort()
    print(f"  cluster ({len(cluster)} parts): {cluster}")

    print(f"== Shift cluster by {SHIFT} ==")
    for ref in cluster:
        x, y, rot = fp_at(text, ref)
        nx, ny = x + SHIFT[0], y + SHIFT[1]
        text = set_fp_at(text, ref, nx, ny, None)
        print(f"  {ref}: ({x:.2f}, {y:.2f}) → ({nx:.2f}, {ny:.2f})")

    print("== Individual moves ==")
    for ref, (x, y, rot) in INDIVIDUAL_MOVES.items():
        text = set_fp_at(text, ref, x, y, rot)
        print(f"  {ref}: → ({x}, {y})")

    print("== Silk labels ==")
    text = remove_old_silk(text)
    for label, x, y, size in SILK:
        text = add_silk_text(text, label, x, y, size)
        print(f"  +silk '{label}' at ({x}, {y})")

    PCB.write_text(text)
    print("Wrote PCB. Verifying loads…")
    r = subprocess.run(
        ['kicad-cli', 'pcb', 'drc', '--format', 'report',
         '-o', '/tmp/drc.rpt', str(PCB)],
        capture_output=True
    )
    if r.returncode != 0:
        print("FAILED. Restoring backup.")
        PCB.write_text(
            Path('defcon_badge/defcon_badge.kicad_pcb.pre_cleanup2').read_text()
        )
        print("stderr:", r.stderr.decode()[:500])
        return 1
    print("OK.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
