#!/usr/bin/env python3
"""Convert defcon_badge.kicad_pcb to 4-layer and place all 83 footprints in
sensible functional groups. Big board (100×80mm) — area optimization comes later.

Layer plan:
  F.Cu  → top signal + front-facing components (LEDs, buttons, jack, IR pair)
  In1.Cu → solid GND plane
  In2.Cu → +3V3 power plane
  B.Cu  → bottom signal + back-side components (RP2040, audio, power, connectors)

Layout zones (board origin at top-left = 50, 50; bottom-right = 150, 130):
  FRONT (y < 70 LED row, y > 110 bottom edge):
    LED20–23 across top, IR LED + TSOP centered, mounting holes at corners,
    3 tactile buttons + 3.5mm jack at bottom edge
  BACK (y 70..110, x 50..150):
    RP2040 + flash + crystal centered, audio chain bottom-left,
    power section bottom-right, microSD bottom-center, SAO right edge
"""
import re
import sys
from pathlib import Path

PROJECT = Path("/home/zach/dev/defcon_badge/defcon_badge")
PCB = PROJECT / "defcon_badge.kicad_pcb"

# -----------------------------------------------------------------------------
# Board geometry — 100×130mm PORTRAIT, wearable badge form factor.
#
# Layout intent (badge_hw_design.md):
#   Front face → 4 LEDs across top, IR LED+TSOP mirror-symmetric mid-height
#   (face-to-face tap aligns them automatically), 3 buttons across bottom edge
#   for thumb reach while wearing, 3.5mm jack on bottom-left edge so cable hangs
#   down. Art everywhere else.
#   Back face → RP2040 center, audio chain lower-left, USB/charge lower-right,
#   microSD center, SAO on right edge for plug-in access, slide switch on left
#   edge for thumb reach while wearing.
# -----------------------------------------------------------------------------
BOARD_X0, BOARD_Y0 = 50.0, 50.0
BOARD_X1, BOARD_Y1 = 150.0, 210.0      # 100 wide × 160 tall, portrait
BOARD_CX = (BOARD_X0 + BOARD_X1) / 2   # vertical centerline x=100
CORNER_INSET = 5.0

# -----------------------------------------------------------------------------
# Placement table: ref → (x, y, rotation, side)
# side: "F" = front (F.Cu), "B" = back (B.Cu)
# Positions are in mm, KiCad PCB origin (board origin defined above is just for
# visual reference; the (at) coordinates here are absolute PCB coords).
# -----------------------------------------------------------------------------

PLACEMENT: dict[str, tuple[float, float, float, str]] = {}


def add(ref, x, y, rot=0, side="B"):
    PLACEMENT[ref] = (x, y, rot, side)


# Board center x=100, y=115. Top edge y=50, bottom y=180, left x=50, right x=150.
# Lanyard attaches at top of board; user wears badge so top edge points up,
# buttons hang near bottom within thumb reach.

# ---- FRONT: 4× SK9822 LEDs evenly spread across top ----
# Spread between left/right mounting hole insets (x ~65..135), 4 LEDs at ~23mm pitch.
add("LED20",  68, 75, 0, "F")
add("LED21",  90, 75, 0, "F")
add("LED22", 112, 75, 0, "F")
add("LED23", 134, 75, 0, "F")

# ---- FRONT: IR LED + TSOP mirror-symmetric about board vertical centerline (x=100).
# Placed mid-upper-height so two badges held face-to-face naturally align the
# LED↔RX pair. 12mm pitch — wider than chip body to clear neighbor visibility.
add("D20",  94, 95, 0, "F")     # 940 nm IR LED at left-of-center
add("U30", 106, 95, 0, "F")     # TSOP4838 at right-of-center

# ---- FRONT: mounting holes at corners. Top-center area free for lanyard hole
# (drill or notch added in CAD later — not generated here).
add("H1",  60,  60, 0, "F")
add("H2", 140,  60, 0, "F")
add("H3",  60, 200, 0, "F")
add("H4", 140, 200, 0, "F")

# ---- FRONT: 3 tactile buttons across the bottom edge for thumb reach.
# CH, VOL+, VOL− left-to-right.
add("SW20",  78, 180, 0, "F")   # CH
add("SW21", 100, 180, 0, "F")   # VOL+
add("SW22", 122, 180, 0, "F")   # VOL-

# ---- FRONT: 3.5mm jack on bottom edge so the cable hangs DOWN. Pushed right
# of H3 mounting hole for clearance with the jack's wide body (~13mm).
add("J20",  82, 195, 0, "F")

# ---- BACK: RP2040 (7×7 QFN56) at board center (100, 115). 0.4mm pin pitch.
# Body extends ±3.5mm. Keep 0402 decoupling 6+mm from chip center.
add("U3", 100, 115, 0, "B")

# 14× RP2040 decoupling caps + +1V1 + bulk arranged around U3 in a ring just
# outside its courtyard. C8 next to pin 45 (VREG_VOUT) and C10 next to pin 44
# (VREG_VIN), per the RPi minimal-design silkscreen note.
# Top row (y=107):
add("C6",   91, 107, 0,  "B")
add("C7",   97, 107, 0,  "B")
add("C8",  103, 107, 0,  "B")   # close to pin 45 VREG_VOUT
add("C9",  109, 107, 0,  "B")
add("C10", 115, 107, 0,  "B")   # close to pin 44 VREG_VIN
# Right column (x=119):
add("C11", 119, 113, 90, "B")
add("C12", 119, 119, 90, "B")
# Bottom row (y=125):
# DROPPED: 
add("C13", 115, 125, 0,  "B")
add("C14", 109, 125, 0,  "B")
# DROPPED: 
add("C15", 103, 125, 0,  "B")
add("C16",  97, 125, 0,  "B")
add("C17",  91, 125, 0,  "B")
# Left column (x=85) — +1V1 cap and bulk
add("C1",   85, 119, 90, "B")   # +1V1 bulk (RP2040 internal regulator output)
add("C4",   85, 113, 90, "B")   # 3V3 bulk

# Crystal block immediately left of RP2040 — short stub to XIN/XOUT pins
add("Y1",   77, 115, 0,  "B")
add("C2",   72, 111, 0,  "B")   # 15p load
add("C3",   72, 119, 0,  "B")   # 15p load
add("R5",   82, 111, 90, "B")   # 1k crystal series

# W25Q16 flash immediately right of RP2040 — short QSPI stubs
add("U2",  130, 115, 0,  "B")
add("C5",  130, 109, 0,  "B")   # 100n flash decoupling
add("R1",  136, 113, 0,  "B")   # 1k QSPI_SS pullup
add("R2",  136, 117, 0,  "B")   # DNF pull

# USB D+/D− series 27Ω — between RP2040 USB pins (south edge) and USB-C zone
add("R3",  103, 102, 0,  "B")
add("R4",  108, 102, 0,  "B")

# J33 SWD/dev header — back, sitting above the RP2040 row, between RP2040 and
# top mounting hole H2. 5-pin 1x05 vertical pin header rotated horizontal.
add("J33", 130,  95, 0,  "B")

# ---- BACK: audio chain (lower-left, per spec "Audio lower left") ----
# Spec ordering: TM8211 DAC → coupling caps → TDA1308 amp → vground network → 220µF output caps
add("U20",  68, 145, 0,  "B")   # TM8211 DAC, SOIC-8
add("C40",  60, 140, 0,  "B")   # 100n DAC VDD
add("C41",  60, 145, 0,  "B")   # 10u DAC VDD bulk
add("C42",  75, 142, 0,  "B")   # 10u L coupling
add("C43",  75, 148, 0,  "B")   # 10u R coupling
add("R20",  80, 142, 90, "B")   # 47k L input
add("R21",  80, 148, 90, "B")   # 47k R input
add("U21",  85, 145, 0,  "B")   # TDA1308 amp
add("R22",  85, 138, 0,  "B")   # 100k L feedback
add("R23",  85, 152, 0,  "B")   # 100k R feedback
add("R24",  92, 142, 90, "B")   # 10k vground top
add("R25",  92, 148, 90, "B")   # 10k vground bottom
add("C44",  60, 152, 0,  "B")   # 10u vground bulk
add("C45",  68, 160, 0,  "B")   # 220u L output coupling (CP 6×5mm)
add("C46",  78, 160, 0,  "B")   # 220u R output coupling

# ---- BACK: power section (lower-right, per spec "USB/charge lower right") ----
# Slide switch SW1 on the LEFT edge so the user can flick it with their thumb
# while the badge hangs on a lanyard.
add("SW1",  55, 130, 0,  "B")   # SS-12D00 on left edge

# Battery cell connector on the right edge
add("J11", 145, 140, 90, "B")   # JST-PH 2P on right edge near power section

# TP4056 + bypass + PROG/CHRG resistors — top of the power column
add("U10", 125, 140, 0,  "B")   # TP4056 SOP-8
add("C20", 118, 135, 0,  "B")   # 1u TP4056 VCC bypass
add("C21", 132, 135, 0,  "B")   # 10u TP4056 BAT bulk
add("R12", 122, 146, 0,  "B")   # 2.4k PROG
add("R13", 128, 146, 0,  "B")   # 100k CHRG pullup

# ME6211 LDO + bypass + VBAT divider — bottom of the power column
add("U11", 125, 155, 0,  "B")   # ME6211 LDO SOT-23-5
add("C22", 118, 152, 0,  "B")   # 1u LDO VIN bypass
add("C23", 132, 152, 0,  "B")   # 1u LDO VOUT bypass
add("R14", 138, 152, 0,  "B")   # 100k VBAT div top
add("R15", 138, 156, 0,  "B")   # 100k VBAT div bottom

# ---- BACK: microSD center back (per spec "SD back center") ----
# Push socket is ~15×17mm. Place between RP2040 row (above) and bottom controls.
add("J31", 100, 165, 0,  "B")

# ---- BACK: SAO 2×3 on RIGHT edge for plug-in access ----
add("J30", 142, 175, 0,  "B")   # SAO header, right edge
add("R40", 138, 168, 0,  "B")   # 4.7k SAO_SDA pullup
add("R41", 138, 171, 0,  "B")   # 4.7k SAO_SCL pullup

# ---- BACK: UART debug header (DNP, bring-up only) ----
add("J32",  62, 175, 0,  "B")   # bottom-left back, away from audio chain

# ---- BACK: IR LED driver close to D20 (FRONT, mirrored x) ----
# DROPPED: 
add("Q20",  93, 102, 0,  "B")   # S8050 NPN
add("R30",  89, 102, 0,  "B")   # 68 Ω current limit
# DROPPED: 
add("R31",  89, 105, 0,  "B")   # 1k base

# ---- BACK: SK9822 bypass caps just below each LED (offset 5mm so projected
# courtyards don't overlap the LED footprint).
add("C60",  68, 82, 0,   "B")
add("C61",  90, 82, 0,   "B")
add("C62", 112, 82, 0,   "B")
add("C63", 134, 82, 0,   "B")

# ---- BACK: TSOP4838 supply decoupling close to U30 (FRONT) ----
add("C70", 110, 102, 0,  "B")   # 100n
add("C71", 113, 102, 0,  "B")   # 10u

# ---- USB-C CC pulldowns — staged near where J10 will land later (bottom-right
# edge). When you Update PCB from Schematic and J10 appears, move it into the
# bottom-right edge cutout; these pulldown resistors are already adjacent.
add("R10", 115, 195, 0,  "B")
add("R11", 119, 195, 0,  "B")


# -----------------------------------------------------------------------------
# PCB file surgery
# -----------------------------------------------------------------------------
def find_block_end(text: str, start: int) -> int:
    depth, j, in_str = 0, start, False
    while j < len(text):
        c = text[j]
        if c == '"' and (j == 0 or text[j - 1] != "\\"):
            in_str = not in_str
        elif not in_str:
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return j + 1
        j += 1
    raise ValueError("unbalanced")


def update_layers(text: str) -> str:
    """Replace the (layers …) block with a 4-layer stackup."""
    m = re.search(r"^\t\(layers\n", text, re.MULTILINE)
    if not m:
        raise RuntimeError("no (layers block")
    s = m.start()
    e = find_block_end(text, s)
    new_block = """\t(layers
\t\t(0 "F.Cu" signal)
\t\t(4 "In1.Cu" power "GND")
\t\t(6 "In2.Cu" power "+3V3")
\t\t(2 "B.Cu" signal)
\t\t(9 "F.Adhes" user "F.Adhesive")
\t\t(11 "B.Adhes" user "B.Adhesive")
\t\t(13 "F.Paste" user)
\t\t(15 "B.Paste" user)
\t\t(5 "F.SilkS" user "F.Silkscreen")
\t\t(7 "B.SilkS" user "B.Silkscreen")
\t\t(1 "F.Mask" user)
\t\t(3 "B.Mask" user)
\t\t(17 "Dwgs.User" user "User.Drawings")
\t\t(19 "Cmts.User" user "User.Comments")
\t\t(21 "Eco1.User" user "User.Eco1")
\t\t(23 "Eco2.User" user "User.Eco2")
\t\t(25 "Edge.Cuts" user)
\t\t(27 "Margin" user)
\t\t(31 "F.CrtYd" user "F.Courtyard")
\t\t(29 "B.CrtYd" user "B.Courtyard")
\t\t(35 "F.Fab" user)
\t\t(33 "B.Fab" user)
\t)"""
    return text[:s] + new_block + text[e:]


def update_footprint(block: str, ref: str, x: float, y: float, rot: float, side: str) -> str:
    """Update a single footprint block: set (at X Y rot) and (layer "F.Cu"|"B.Cu")."""
    layer = "F.Cu" if side == "F" else "B.Cu"
    # Update the FIRST (layer "...") near the top of the block
    block = re.sub(r'\(layer "(?:F\.Cu|B\.Cu)"', f'(layer "{layer}"', block, count=1)
    # Update the FIRST (at X Y [rot]) — the footprint's own position
    rot_str = f" {rot:g}" if rot != 0 else ""
    block = re.sub(
        r"\(at\s+-?\d+\.?\d*\s+-?\d+\.?\d*(?:\s+-?\d+\.?\d*)?\)",
        f"(at {x:g} {y:g}{rot_str})",
        block,
        count=1,
    )
    return block


def place_footprints(text: str) -> tuple[str, list[str]]:
    """For each (footprint …) block, look up its Reference and apply placement."""
    unmatched: list[str] = []
    placed: list[str] = []
    out: list[str] = []
    i = 0
    # Walk top-level footprint blocks. Each starts at "\t(footprint \"..." at column 0+tab.
    pattern = re.compile(r'^\t\(footprint "', re.MULTILINE)
    last = 0
    for m in pattern.finditer(text):
        s = m.start()
        e = find_block_end(text, s)
        out.append(text[last:s])
        block = text[s:e]
        rm = re.search(r'\(property "Reference" "([^"]+)"', block)
        if rm:
            ref = rm.group(1)
            if ref in PLACEMENT:
                x, y, rot, side = PLACEMENT[ref]
                block = update_footprint(block, ref, x, y, rot, side)
                placed.append(ref)
            else:
                unmatched.append(ref)
        out.append(block)
        last = e
    out.append(text[last:])
    print(f"  placed {len(placed)} footprints", file=sys.stderr)
    if unmatched:
        print(f"  unmatched (no placement): {unmatched}", file=sys.stderr)
    return "".join(out), unmatched


def add_edge_cuts(text: str) -> str:
    """Add a rectangular board outline on Edge.Cuts, inserted just before the
    closing ) of the kicad_pcb root. Uses gr_rect."""
    edge_block = (
        f'\n\t(gr_rect (start {BOARD_X0:g} {BOARD_Y0:g}) (end {BOARD_X1:g} {BOARD_Y1:g})'
        f' (stroke (width 0.1) (type solid)) (fill no) (layer "Edge.Cuts"))\n'
    )
    # Insert right before final closing paren of kicad_pcb root. Find last ')'.
    last_close = text.rstrip().rfind(")")
    return text[:last_close] + edge_block + text[last_close:]


def main():
    text = PCB.read_text()
    text = update_layers(text)
    text, unmatched = place_footprints(text)
    text = add_edge_cuts(text)
    PCB.write_text(text)
    print(f"  wrote {PCB} ({len(text)} bytes)", file=sys.stderr)


if __name__ == "__main__":
    main()
