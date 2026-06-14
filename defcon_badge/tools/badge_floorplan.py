#!/usr/bin/env python3
"""badge_floorplan.py — complete floorplan for the DEFCON badge.

Defines functional zones and signal topology, then dispatches to the
floorplan skill to lay out every component.

Board: 86 × 54mm (x: 100-188, y: 80-134)

Zone layout:

   100        125         145         165         188
80 ┌──────────────────────────────────┬──────────┐
   │  LED STRIP (LED20-23)            │ J20 JACK │
90 ├──┬────────────────────────────────┴──────────┤
   │J30│                                 │ BUTTONS│
   │SAO│   AUDIO CHAIN                   │ SW20-22│
100│   │   U20 → U21 → C45 → C46 → J20   │        │
   ├───┤                                 │        │
   │U30│                                 │        │
110│IR │   MCU CLUSTER (U3 + ring)       │ D20+R30│
   │ R │                                 │ (IR TX)│
   │ X │   Y1 crystal + load caps below  │        │
120├───┴──────────────────┬──────────────┼────────┤
   │ POWER CHAIN          │   USB-C J10  │  open  │
130│ SW1 → U10 → U11 → battery (back)    │        │
   │                      │              │microSD │
   │  R10-R15, C20-C23    │              │(back)  │
   └──────────────────────┴──────────────┴────────┘
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

PCB = Path("defcon_badge/defcon_badge.kicad_pcb")

# Edge-locked positions (constraints we can't move)
FIXED_POSITIONS = {
    'J20':  [170.0, 85.0, 180],   # audio jack — top-right corner, plug up
    'J10':  [140.0, 128.0, 0],    # USB-C — bottom edge, plug down
    'SW1':  [112.2, 132.4, 0],    # power switch — bottom-left corner
    'U30':  [104.4, 110.0, 0],    # IR RX — left edge at y=110 for pairing
    'D20':  [184.0, 110.0, 0],    # IR LED — right edge at y=110 for pairing
    'R30':  [180.5, 110.0, 0],    # IR LED series R
}

# All zones in the floor plan.
ZONES = {
    # ─── TOP STRIP ────────────────────────────────────────────
    'led_strip': {
        # Shrink right end so LED23 doesn't crash into J20 (J20 cy left=164.25)
        'bbox': [110, 84, 158, 86],
        'topology': 'row',
        'parts': ['LED20', 'LED21', 'LED22', 'LED23'],
    },
    'led_decoupling': {
        'bbox': [110, 89, 158, 91],
        'topology': 'row',
        'parts': ['C60', 'C61', 'C62', 'C63'],
    },
    # ─── UPPER LEFT ───────────────────────────────────────────
    'sao': {
        'bbox': [108, 93, 113, 100],
        'topology': 'fixed',
        'positions': {'J30': [110.0, 95.0]},
    },
    # ─── AUDIO CHAIN: U20 → U21 → C45 → C46 → J20 ─────────────
    'audio_chain': {
        # U20 + U21 SOIC-8 ICs (3.9×4.9mm). Spacing 7mm allows ~3mm gap.
        'bbox': [135, 99, 144, 101],
        'topology': 'chain',
        'direction': 'right',
        'parts': ['U20', 'U21'],
    },
    'audio_caps_big': {
        # C45/C46 electrolytics (6.6×6.6mm). Need >9mm anchor spacing.
        # C45 at x=151 — gap of ~5mm to U21 (4mm right edge clears).
        'bbox': [151, 99, 164, 101],
        'topology': 'fixed',
        'positions': {
            'C45': [151.0, 100.0],
            'C46': [161.0, 100.0],
        },
    },
    'audio_jack_position': {
        'bbox': [165, 80, 175, 92],
        'topology': 'fixed',
        'positions': {'J20': FIXED_POSITIONS['J20']},
    },
    # All audio support passives (R20-R25, C40, C42-C44) in one row ABOVE
    # the chain, between the LED decoupling caps (y=90) and the chain
    # (y=99). Avoids overlap with U20/U21/U2.
    'audio_support_row': {
        'bbox': [135, 94, 162, 95],
        'topology': 'row',
        'parts': ['R20', 'R21', 'R22', 'R23', 'R24', 'R25',
                  'C40', 'C42', 'C43', 'C44'],
    },
    # ─── MCU CLUSTER ──────────────────────────────────────────
    'mcu_ring': {
        # U3 RP2040 at center; the ring tool will run AFTER this on caps
        'bbox': [130, 107, 144, 117],
        'topology': 'ring',
        'center_part': 'U3',
        'ring_parts': ['C5', 'C6', 'C7', 'C9', 'C11', 'C12', 'C14', 'C16'],
        'gap': 0.6,
    },
    'mcu_flash': {
        # U2 W25Q16 flash — to the LEFT of U3, not above it (above is
        # claimed by audio chain). Short QSPI lines to U3 left edge.
        'bbox': [125, 109, 128, 113],
        'topology': 'fixed',
        'positions': {'U2': [126.5, 111.0]},
    },
    'mcu_flash_support': {
        # R3, R4, R5 — flash pullups, near U2
        'bbox': [123, 113, 129, 114],
        'topology': 'row',
        'parts': ['R3', 'R4', 'R5'],
    },
    'mcu_crystal': {
        # Y1 below the U3 ring (ring extends to ~y=117). Y1 at y=121.
        'bbox': [135, 121, 142, 122],
        'topology': 'fixed',
        'positions': {'Y1': [137.0, 121.0]},
    },
    'mcu_crystal_caps': {
        # C2, C3 — flank Y1
        'bbox': [134, 123, 142, 124],
        'topology': 'row',
        'parts': ['C2', 'C3'],
    },
    'mcu_bulk_caps': {
        # C1 (10u), C8 (1u +1V1), C10 (1u +3V3), C17 (10u) — to the LEFT
        # of the U3 ring (clear of the y=116 ring bottom)
        'bbox': [120, 110, 128, 113],
        'topology': 'row',
        'parts': ['C1', 'C8', 'C10', 'C17'],
    },
    # ─── BUTTONS — right side, triangle ───────────────────────
    'buttons': {
        'bbox': [170, 94, 187, 108],
        'topology': 'triangle',
        'point': 'down',
        'parts': ['SW20', 'SW21', 'SW22'],
    },
    # ─── IR pair LEDs ─────────────────────────────────────────
    'ir_edges': {
        'bbox': [100, 109, 188, 111],
        'topology': 'fixed',
        'positions': {
            'U30': FIXED_POSITIONS['U30'],
            'D20': FIXED_POSITIONS['D20'],
            'R30': FIXED_POSITIONS['R30'],
        },
    },
    # ─── POWER CHAIN: USB-C → charger → battery → switch → LDO ─
    'power_switch': {
        'bbox': [108, 130, 118, 134],
        'topology': 'fixed',
        'positions': {'SW1': FIXED_POSITIONS['SW1']},
    },
    'power_usb': {
        'bbox': [136, 126, 148, 137],
        'topology': 'fixed',
        'positions': {'J10': FIXED_POSITIONS['J10']},
    },
    'power_chain': {
        # U10 TP4056 (charger), U11 LDO. End at x=132 so U11 clears the
        # MCU crystal at x=135.
        'bbox': [120, 124, 132, 125],
        'topology': 'row',
        'parts': ['U10', 'U11'],
    },
    'power_caps': {
        'bbox': [118, 121, 132, 122],
        'topology': 'row',
        'parts': ['C20', 'C22', 'C23'],
    },
    'power_resistors_top': {
        'bbox': [118, 127, 132, 128],
        'topology': 'row',
        'parts': ['R12', 'R13', 'R14', 'R15'],
    },
    'usb_cc_pulldowns': {
        # R10, R11 — 5.1k CC pulldowns next to USB-C
        'bbox': [148, 132, 152, 134],
        'topology': 'row',
        'parts': ['R10', 'R11'],
    },
    # ─── BACK SIDE: battery + microSD ─────────────────────────
    'back_battery': {
        # J11 JST-PH on B.Cu, near SW1's position (battery wire short)
        'bbox': [110, 121, 120, 128],
        'topology': 'fixed',
        'positions': {'J11': [115.0, 124.0, 0]},
    },
    'back_sd': {
        # J31 microSD on B.Cu, right-bottom
        'bbox': [155, 120, 175, 132],
        'topology': 'fixed',
        'positions': {'J31': [165.0, 125.0, 0]},
    },
    # ─── MISC ──────────────────────────────────────────────────
    'misc_caps_top': {
        # C9 (close to U3 — let ring handle), C41, C42, C70 etc. — keep
        # these off in their own row to avoid clutter
        'bbox': [120, 100, 132, 102],
        'topology': 'row',
        'parts': ['C41', 'C70', 'C50', 'C51'],
    },
}


def main() -> int:
    plan = {'zones': ZONES}
    plan_path = Path('/tmp/badge_plan.json')
    plan_path.write_text(json.dumps(plan, indent=2))
    print(f"Plan written to {plan_path}")
    print(f"Plan contains {len(ZONES)} zones")
    print("Running floorplan tool...")
    r = subprocess.run(
        ['python3',
         str(Path.home() / '.claude/skills/pcb-placement/scripts/floorplan.py'),
         str(PCB), '--plan', str(plan_path)],
        check=False
    )
    return r.returncode


if __name__ == '__main__':
    sys.exit(main())
