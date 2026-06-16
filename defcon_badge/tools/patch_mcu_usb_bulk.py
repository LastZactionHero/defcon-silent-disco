#!/usr/bin/env python3
"""patch_mcu_usb_bulk.py — repair the connectivity breaks the schematic review
found on MCU_Core.kicad_sch:

  * R3.1 / R4.1 (USB D+/D- 27R series-resistor connector side) were dangling —
    the RP2040's USB lines never reached the USB-C connector. Add USB_DP /
    USB_DM labels so they merge with the cross-sheet hierarchical nets.
  * C1 (10u) had pin 1 floating; C17 (10u) had BOTH pins floating. Per the
    review these are the RP2040 +3V3 bulk caps (doc: "1uF bulk x2"). Wire them
    to +3V3 / GND with cloned power symbols and correct the value to 1u.

Idempotent-ish: run once on the as-generated MCU_Core. Verifies nothing; the
caller re-runs analyze_schematic.py to confirm the nets merged.
"""
from __future__ import annotations
import re
import sys
import uuid
from pathlib import Path

SRC = Path(__file__).parent.parent / "MCU_Core.kicad_sch"
INST_PATH = "/8c0b3d8b-46d3-4173-ab1e-a61765f77d61/614c6d9e-c93d-4105-a0eb-565eebb554cc"


def u() -> str:
    return str(uuid.uuid4())


def label(name: str, x: float, y: float) -> str:
    return (f'\t(label "{name}"\n\t\t(at {x:.2f} {y:.2f} 0)\n'
            f'\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n'
            f'\t\t\t(justify left bottom)\n\t\t)\n\t\t(uuid "{u()}")\n\t)')


def wire(x1: float, y1: float, x2: float, y2: float) -> str:
    return (f'\t(wire\n\t\t(pts\n\t\t\t(xy {x1:.2f} {y1:.2f}) (xy {x2:.2f} {y2:.2f})\n\t\t)\n'
            f'\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n\t\t(uuid "{u()}")\n\t)')


def power(rail: str, ref: str, x: float, y: float) -> str:
    """Clone of an existing MCU_Core power symbol, pin sits exactly at (x,y)."""
    if rail == "+3V3":
        vx, vy, rx, ry = x + 0.381, y - 4.394, x, y + 3.81
    elif rail == "GND":
        vx, vy, rx, ry = x - 3.81, y + 1.27, x, y + 6.35
    else:
        raise ValueError(rail)
    def prop(name, val, px, py, hide):
        h = "\n\t\t\t(hide yes)" if hide else ""
        return (f'\t\t(property "{name}" "{val}"\n\t\t\t(at {px:.3f} {py:.3f} 0){h}\n'
                f'\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n\t\t\t(effects\n'
                f'\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t)\n\t\t)')
    return (
        f'\t(symbol\n\t\t(lib_id "power:{rail}")\n\t\t(at {x:.2f} {y:.2f} 0)\n'
        f'\t\t(unit 1)\n\t\t(body_style 1)\n\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n'
        f'\t\t(on_board yes)\n\t\t(in_pos_files yes)\n\t\t(dnp no)\n\t\t(uuid "{u()}")\n'
        + prop("Reference", ref, rx, ry, True) + "\n"
        + prop("Value", rail, vx, vy, False) + "\n"
        + prop("Footprint", "", x, y, True) + "\n"
        + prop("Datasheet", "", x, y, True) + "\n"
        + prop("Description", "", x, y, False) + "\n"
        + f'\t\t(pin "1"\n\t\t\t(uuid "{u()}")\n\t\t)\n'
        + f'\t\t(instances\n\t\t\t(project "defcon_badge"\n\t\t\t\t(path "{INST_PATH}"\n'
        + f'\t\t\t\t\t(reference "{ref}")\n\t\t\t\t\t(unit 1)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)'
    )


def set_value(text: str, ref: str, newval: str) -> str:
    """Change the Value property of the symbol whose Reference is `ref`."""
    # Find the symbol block by its Reference property, then its Value property.
    m = re.search(r'\(property "Reference" "' + re.escape(ref) + r'"', text)
    if not m:
        raise SystemExit(f"ref {ref} not found")
    seg = text[m.start():m.start() + 2000]
    seg2 = re.sub(r'(\(property "Value" ")[^"]*(")', r'\g<1>' + newval + r'\g<2>', seg, count=1)
    return text[:m.start()] + seg2 + text[m.start() + 2000:]


def main():
    t = SRC.read_text()

    frags = []
    # --- USB D+/D- : connector-side series-resistor pins → cross-sheet nets ---
    # R3.1 (248.92,96.52) right pin; R4.1 (248.92,104.14) right pin. Stub right.
    frags.append(wire(248.92, 96.52, 251.46, 96.52))
    frags.append(label("USB_DP", 251.46, 96.52))
    frags.append(wire(248.92, 104.14, 251.46, 104.14))
    frags.append(label("USB_DM", 251.46, 104.14))

    # --- C1 +3V3 bulk: pin1 top (58.42,45.72) → +3V3 (pin2 already GND) ---
    frags.append(wire(58.42, 45.72, 58.42, 43.18))
    frags.append(power("+3V3", "#PWR_C1V", 58.42, 43.18))
    # --- C17 +3V3 bulk: pin1 top (351.79,189.23) → +3V3 ; pin2 (196.85) → GND ---
    frags.append(wire(351.79, 189.23, 351.79, 186.69))
    frags.append(power("+3V3", "#PWR_C17V", 351.79, 186.69))
    frags.append(wire(351.79, 196.85, 351.79, 199.39))
    frags.append(power("GND", "#PWR_C17G", 351.79, 199.39))

    # Insert before the final top-level closing paren.
    idx = t.rstrip().rfind(")")
    t = t[:idx] + "\n".join(frags) + "\n" + t[idx:]

    # Correct bulk-cap values 10u → 1u (per design doc "1uF bulk x2").
    t = set_value(t, "C1", "1u")
    t = set_value(t, "C17", "1u")

    SRC.write_text(t)
    print(f"patched {SRC}")


if __name__ == "__main__":
    main()
