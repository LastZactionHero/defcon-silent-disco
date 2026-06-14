#!/usr/bin/env python3
"""silk_mecha.py — vector silk art for the DEFCON silent disco badge.

Theme: mecha Tokyo dance party. Bold filled chevrons, corner armor
brackets, radial sun-burst rays, dot grids, diagonal hash for "armor
panels", stenciled DC32 emblem, warning glyphs near connectors.

All shapes are emitted as KiCad gr_line / gr_arc / gr_poly on the
F.SilkS or B.SilkS layer. Strips the existing decorative silk first
(by uuid prefix tag) so re-runs are idempotent.

Usage: tools/silk_mecha.py [--side front|back|both]
"""
from __future__ import annotations

import argparse
import math
import re
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PCB = REPO / "defcon_badge" / "defcon_badge.kicad_pcb"

# Tag we put in every UUID we generate so we can strip them later
MECHA_TAG = "meca7a91"

# Width of normal silk strokes (KiCad default 0.12-0.15mm)
W_THIN = 0.12
W_BOLD = 0.25
W_HEAVY = 0.4


def U() -> str:
    """Tagged UUID we can find and strip later."""
    return f"{MECHA_TAG}-{uuid.uuid4().hex[:8]}-0000-0000-0000-{uuid.uuid4().hex[:12]}"


def gr_line(x1, y1, x2, y2, layer, w=W_THIN):
    return (f'\t(gr_line (start {x1:.3f} {y1:.3f}) (end {x2:.3f} {y2:.3f}) '
            f'(stroke (width {w}) (type default)) (layer "{layer}") '
            f'(uuid "{U()}"))\n')


def gr_arc(sx, sy, mx, my, ex, ey, layer, w=W_THIN):
    return (f'\t(gr_arc (start {sx:.3f} {sy:.3f}) (mid {mx:.3f} {my:.3f}) '
            f'(end {ex:.3f} {ey:.3f}) (stroke (width {w}) (type default)) '
            f'(layer "{layer}") (uuid "{U()}"))\n')


def gr_circle(cx, cy, r, layer, w=W_THIN, fill=False):
    return (f'\t(gr_circle (center {cx:.3f} {cy:.3f}) '
            f'(end {cx + r:.3f} {cy:.3f}) '
            f'(stroke (width {w}) (type default)) '
            f'(fill {"solid" if fill else "no"}) '
            f'(layer "{layer}") (uuid "{U()}"))\n')


def gr_poly(points, layer, fill=True, w=W_THIN):
    pts_s = "".join(f"\t\t\t(xy {x:.3f} {y:.3f})\n" for x, y in points)
    return (f'\t(gr_poly\n\t\t(pts\n{pts_s}\t\t)\n'
            f'\t\t(stroke (width {w}) (type default))\n'
            f'\t\t(fill {"solid" if fill else "no"})\n'
            f'\t\t(layer "{layer}")\n'
            f'\t\t(uuid "{U()}")\n\t)\n')


def gr_text(s, x, y, layer, size=2.0, bold=False, rot=0, mirror=False):
    thick = max(0.15, size * 0.15) if not bold else max(0.25, size * 0.18)
    bstr = ' (bold yes)' if bold else ''
    just = ' (justify mirror)' if mirror else ''
    return (f'\t(gr_text "{s}" (at {x:.2f} {y:.2f} {rot}) (layer "{layer}") '
            f'(uuid "{U()}") '
            f'(effects (font (size {size} {size}) (thickness {thick:.2f}){bstr}){just}))\n')


# ─────────────────────────────────────────────────────────────────────────
# Compound shapes
# ─────────────────────────────────────────────────────────────────────────

def chevron_filled(cx, cy, w, h, point: str, layer):
    """Filled triangle chevron. point ∈ {up,down,left,right}."""
    if point == "up":
        pts = [(cx, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2), (cx, cy - h / 2)]
    elif point == "down":
        pts = [(cx, cy + h / 2), (cx + w / 2, cy - h / 2), (cx - w / 2, cy - h / 2), (cx, cy + h / 2)]
    elif point == "right":
        pts = [(cx + w / 2, cy), (cx - w / 2, cy + h / 2), (cx - w / 2, cy - h / 2), (cx + w / 2, cy)]
    else:  # left
        pts = [(cx - w / 2, cy), (cx + w / 2, cy + h / 2), (cx + w / 2, cy - h / 2), (cx - w / 2, cy)]
    return gr_poly(pts, layer, fill=True)


def chevron_outline(cx, cy, size, thick, point: str, layer):
    """Outlined chevron > shape — two lines forming a V."""
    s = size / 2
    if point == "right":
        return (gr_line(cx - s, cy - s, cx + s, cy, layer, w=thick) +
                gr_line(cx + s, cy, cx - s, cy + s, layer, w=thick))
    if point == "left":
        return (gr_line(cx + s, cy - s, cx - s, cy, layer, w=thick) +
                gr_line(cx - s, cy, cx + s, cy + s, layer, w=thick))
    if point == "up":
        return (gr_line(cx - s, cy + s, cx, cy - s, layer, w=thick) +
                gr_line(cx, cy - s, cx + s, cy + s, layer, w=thick))
    return (gr_line(cx - s, cy - s, cx, cy + s, layer, w=thick) +
            gr_line(cx, cy + s, cx + s, cy - s, layer, w=thick))


def corner_bracket(cx, cy, size, orient: str, layer, w=W_BOLD):
    """L-shaped corner bracket. orient = tl, tr, bl, br."""
    s = size
    if orient == "tl":
        return (gr_line(cx, cy, cx + s, cy, layer, w=w) +
                gr_line(cx, cy, cx, cy + s, layer, w=w))
    if orient == "tr":
        return (gr_line(cx, cy, cx - s, cy, layer, w=w) +
                gr_line(cx, cy, cx, cy + s, layer, w=w))
    if orient == "bl":
        return (gr_line(cx, cy, cx + s, cy, layer, w=w) +
                gr_line(cx, cy, cx, cy - s, layer, w=w))
    return (gr_line(cx, cy, cx - s, cy, layer, w=w) +
            gr_line(cx, cy, cx, cy - s, layer, w=w))


def diag_hatch(x0, y0, x1, y1, pitch, layer, angle_deg=45, w=W_THIN):
    """Fill region [x0,y0]→[x1,y1] with diagonal lines at given angle."""
    out = ""
    # Step along the diagonal direction, drawing lines that span the box
    # For 45° hatch with pitch p, lines pass through offsets along the
    # normal direction. We sample x_offset along x-axis at uniform pitch.
    span = (x1 - x0) + (y1 - y0)
    for i in range(int(span / pitch) + 2):
        # Diagonal line family y = x + c, with c varying
        c = (i * pitch) - (y1 - y0)
        # Line: from x = x0+c (where y=x0+c-c = x0... not quite) actually:
        # parameterize as point on line and clip to box.
        # For y = x - x0 + (y0 + i*pitch - x0...) — easier just to draw segments
        # at angles. Let's compute endpoints crossing the box.
        # Pick direction vector
        dx = math.cos(math.radians(angle_deg))
        dy = math.sin(math.radians(angle_deg))
        # Start point: along the bottom or left edge.
        # We'll just draw a long line through (x_offset, y0) at the angle
        # and clip implicitly by drawing within sensible bounds.
        x_start = x0 + i * pitch - (y1 - y0)
        if x_start > x1: continue
        sx = max(x0, x_start)
        sy = y0 + (sx - x_start)
        ex = min(x1, x_start + (y1 - y0))
        ey = y0 + (ex - x_start)
        if sy > y1 or ey < y0: continue
        sy = max(y0, sy); ey = min(y1, ey)
        if ex - sx < 0.5: continue  # too short to bother
        out += gr_line(sx, sy, ex, ey, layer, w=w)
    return out


def dot_grid(x0, y0, x1, y1, pitch, dot_r, layer):
    """Filled-circle dots in a grid."""
    out = ""
    y = y0
    while y <= y1:
        x = x0
        while x <= x1:
            out += gr_circle(x, y, dot_r, layer, fill=True, w=0.1)
            x += pitch
        y += pitch
    return out


def radial_rays(cx, cy, n, r_inner, r_outer, layer, w=W_THIN):
    """N rays radiating from (cx, cy)."""
    out = ""
    for i in range(n):
        ang = 2 * math.pi * i / n
        sx = cx + r_inner * math.cos(ang)
        sy = cy + r_inner * math.sin(ang)
        ex = cx + r_outer * math.cos(ang)
        ey = cy + r_outer * math.sin(ang)
        out += gr_line(sx, sy, ex, ey, layer, w=w)
    return out


def octagon(cx, cy, r, layer, w=W_BOLD, fill=False):
    """Octagonal outline or fill."""
    pts = []
    for i in range(8):
        ang = math.pi / 8 + i * math.pi / 4  # rotate so flat sides are top/bottom
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    pts.append(pts[0])
    if fill:
        return gr_poly(pts, layer, fill=True)
    out = ""
    for i in range(8):
        out += gr_line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1], layer, w=w)
    return out


def hex_outline(cx, cy, r, layer, w=W_BOLD):
    """Hexagonal outline."""
    pts = [(cx + r * math.cos(math.pi / 6 + i * math.pi / 3),
            cy + r * math.sin(math.pi / 6 + i * math.pi / 3)) for i in range(6)]
    out = ""
    for i in range(6):
        j = (i + 1) % 6
        out += gr_line(pts[i][0], pts[i][1], pts[j][0], pts[j][1], layer, w=w)
    return out


# ─────────────────────────────────────────────────────────────────────────
# Composition — the actual design
# ─────────────────────────────────────────────────────────────────────────

def back_side_art() -> str:
    """Design for B.SilkS — mecha Tokyo dance party hero panel."""
    art = ""
    L = "B.SilkS"

    # Board outline reference: x=100..186, y=80..134
    cx_board = 143; cy_board = 107

    # ── Corner armor brackets ── 4 L-shapes at the 4 board corners
    art += corner_bracket(102, 82, 5, "tl", L, w=W_HEAVY)
    art += corner_bracket(184, 82, 5, "tr", L, w=W_HEAVY)
    art += corner_bracket(102, 132, 5, "bl", L, w=W_HEAVY)
    art += corner_bracket(184, 132, 5, "br", L, w=W_HEAVY)

    # ── Top frame stripe with chevrons ──
    # Horizontal heavy line under the corner brackets
    art += gr_line(108, 84, 178, 84, L, w=W_BOLD)
    # 3 chevrons pointing right of the line, 3 pointing left (mirrored ~)
    for i in range(5):
        x = 112 + i * 4
        art += chevron_filled(x, 86, 3, 2.5, "right", L)
    for i in range(5):
        x = 174 - i * 4
        art += chevron_filled(x, 86, 3, 2.5, "left", L)

    # ── Bottom frame stripe ──
    art += gr_line(108, 130, 178, 130, L, w=W_BOLD)
    for i in range(5):
        x = 112 + i * 4
        art += chevron_filled(x, 128, 3, 2.5, "right", L)
    for i in range(5):
        x = 174 - i * 4
        art += chevron_filled(x, 128, 3, 2.5, "left", L)

    # ── Left/right vertical accent stripes (mecha armor scale lines) ──
    for y in range(90, 126, 4):
        art += gr_line(103, y, 105, y, L, w=W_BOLD)
        art += gr_line(181, y, 183, y, L, w=W_BOLD)

    # ── Diagonal hash blocks in the corners (mecha shading) ──
    # Top-left and bottom-right diagonal hatch
    art += diag_hatch(108, 88, 116, 96, 1.2, L, angle_deg=45, w=W_THIN)
    art += diag_hatch(170, 118, 178, 126, 1.2, L, angle_deg=45, w=W_THIN)
    # Top-right and bottom-left counter-hash
    art += diag_hatch(170, 88, 178, 96, 1.2, L, angle_deg=135, w=W_THIN)
    art += diag_hatch(108, 118, 116, 126, 1.2, L, angle_deg=135, w=W_THIN)

    # ── Radial sunburst behind the DEFCON wordmark center ──
    art += radial_rays(cx_board, 96, 24, 14, 25, L, w=W_THIN)

    # ── BIG DEFCON wordmark (mirrored for back) ──
    art += gr_text("DEFCON", cx_board, 96, L, size=4.5, bold=True, mirror=True)

    # ── Tagline ──
    art += gr_text("// SILENT DISCO //", cx_board - 14, 102, L, size=1.3, mirror=True)

    # ── Octagonal DC32 emblem ──
    em_x, em_y = cx_board, 115
    art += octagon(em_x, em_y, 6, L, w=W_BOLD, fill=False)
    art += octagon(em_x, em_y, 5, L, w=W_THIN, fill=False)
    art += gr_text("DC32", em_x - 4, em_y + 1, L, size=2.0, bold=True, mirror=True)

    # ── Small mecha tech accents to either side of the emblem ──
    # Left: hex with a dot
    art += hex_outline(em_x - 16, em_y, 3, L, w=W_THIN)
    art += gr_circle(em_x - 16, em_y, 0.5, L, fill=True)
    # Right: hex with a dot
    art += hex_outline(em_x + 16, em_y, 3, L, w=W_THIN)
    art += gr_circle(em_x + 16, em_y, 0.5, L, fill=True)

    # ── github URL bottom ──
    art += gr_text("github.com/LastZactionHero/defcon-silent-disco",
                   cx_board - 17, 124, L, size=0.85, mirror=True)

    # ── 0xC0FFEE / @LZH flavor in corners ──
    art += gr_text("0xC0FFEE", 113, 88, L, size=0.7, mirror=True)
    art += gr_text("@LZH", 170, 88, L, size=0.7, mirror=True)

    # ── Dotted "rain" / LED party array — small pixel grid below corners ──
    art += dot_grid(112, 122, 124, 126, 1.6, 0.4, L)
    art += dot_grid(162, 122, 174, 126, 1.6, 0.4, L)

    return art


def front_side_art() -> str:
    """Design for F.SilkS — armor panel lines around components, accent
    chevrons near connectors, tech accents in empty zones. Subtle — the
    front is busy with refdes silk already, so we keep accents tasteful."""
    art = ""
    L = "F.SilkS"

    # ── Tiny corner brackets (no overlap with mounting holes) ──
    art += corner_bracket(108, 88, 3, "tl", L, w=W_THIN)
    art += corner_bracket(178, 88, 3, "tr", L, w=W_THIN)
    art += corner_bracket(108, 126, 3, "bl", L, w=W_THIN)
    art += corner_bracket(178, 126, 3, "br", L, w=W_THIN)

    # ── Chevron arrows pointing DOWN toward USB-C J10 at bottom ──
    # (data flow visual)
    for i, y in enumerate([100, 102, 104]):
        art += chevron_outline(124, y, 1.6, W_BOLD, "down", L)

    # ── Chevron arrows pointing UP toward audio jack at top-right ──
    for i, y in enumerate([100, 102, 104]):
        art += chevron_outline(178, y, 1.6, W_BOLD, "up", L)

    # ── Tiny "▶" chevron near power switch direction (next to SW1) ──
    art += chevron_outline(118, 128, 1.6, W_BOLD, "right", L)

    # ── Power flow chevron near battery JST-PH ──
    art += chevron_outline(167, 128, 1.6, W_BOLD, "left", L)

    # ── Decorative hex glyphs in empty zones ──
    art += hex_outline(108, 102, 2, L, w=W_THIN)
    art += gr_circle(108, 102, 0.4, L, fill=True)
    art += hex_outline(178, 116, 2, L, w=W_THIN)
    art += gr_circle(178, 116, 0.4, L, fill=True)

    # ── Subtle armor panel divider — horizontal line between audio block
    # and MCU zone (around y=108, x=110..156) ──
    art += gr_line(108, 109, 124, 109, L, w=W_THIN)
    art += gr_line(168, 109, 178, 109, L, w=W_THIN)
    # Same for between MCU and bottom row
    art += gr_line(108, 124, 116, 124, L, w=W_THIN)
    art += gr_line(170, 124, 178, 124, L, w=W_THIN)

    return art


# ─────────────────────────────────────────────────────────────────────────
# Strip + insert
# ─────────────────────────────────────────────────────────────────────────

def strip_old_mecha(text: str) -> str:
    """Drop every gr_* element whose UUID begins with our tag."""
    pattern = re.compile(
        rf'\n\t\(gr_(?:line|arc|rect|circle|poly|curve|text)\b[^)]*?'
        rf'\(uuid "{MECHA_TAG}-[^"]+"\).*?\)',
        re.DOTALL,
    )
    return pattern.sub("", text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--side", choices=("front", "back", "both"), default="both")
    args = ap.parse_args()

    text = PCB.read_text()
    text = strip_old_mecha(text)

    art = ""
    if args.side in ("back", "both"):
        art += back_side_art()
    if args.side in ("front", "both"):
        art += front_side_art()

    insert_at = text.rstrip().rfind(")")
    text = text[:insert_at] + art + text[insert_at:]
    PCB.write_text(text)

    # Count what we added
    counts = {
        "lines": art.count("(gr_line"),
        "arcs": art.count("(gr_arc"),
        "circles": art.count("(gr_circle"),
        "polys": art.count("(gr_poly"),
        "texts": art.count("(gr_text"),
    }
    print("Mecha silk applied:")
    for k, v in counts.items():
        print(f"  {v:4} {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
