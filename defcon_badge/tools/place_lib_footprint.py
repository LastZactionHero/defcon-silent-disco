#!/usr/bin/env python3
"""place_lib_footprint.py — append a stdlib footprint to the PCB.

Reads `.kicad_mod` from /usr/share/kicad/footprints/<LIB>.pretty/<NAME>.kicad_mod,
rewrites its Reference property to the requested REFDES, sets the anchor
position to (X, Y) with optional ROT, generates fresh UUIDs for every
element (so KiCad doesn't see them as duplicates), and appends the result
to defcon_badge.kicad_pcb as a top-level (footprint ...) block.

Usage:
  tools/place_lib_footprint.py J10 Connector_USB USB_C_Receptacle_GCT_USB4085 134 125 0

Pads are NOT wired to any nets — they'll show up as unconnected and need
to be wired in a follow-up step or by hand in KiCad.
"""
from __future__ import annotations

import re
import shutil
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PCB = REPO_ROOT / "defcon_badge" / "defcon_badge.kicad_pcb"
LIBS = [Path("/usr/share/kicad/footprints"), Path("/usr/local/share/kicad/footprints")]


def find_mod(lib: str, name: str) -> Path:
    for base in LIBS:
        cand = base / f"{lib}.pretty" / f"{name}.kicad_mod"
        if cand.is_file():
            return cand
    raise FileNotFoundError(f"{lib}:{name} not found in {LIBS}")


def freshen_uuids(text: str) -> str:
    return re.sub(
        r'\(uuid "[0-9a-fA-F-]+"\)',
        lambda m: f'(uuid "{uuid.uuid4()}")',
        text,
    )


def set_reference(text: str, refdes: str) -> str:
    """Change (property "Reference" "REF**" to (property "Reference" "<refdes>"."""
    return re.sub(
        r'(\(property "Reference"\s+)"[^"]+"',
        rf'\1"{refdes}"',
        text,
        count=1,
    )


def set_anchor(text: str, x: float, y: float, rot: float) -> str:
    """Replace the footprint's top-level (at ...) line — the first one
    immediately after (descr) is the anchor. KiCad's .kicad_mod files don't
    have an (at) at the top level; we add one. The footprint body uses
    relative coordinates."""
    # The .kicad_mod top-level is "(footprint "NAME" ... (descr ...) (tags ...) (property "Reference" ...".
    # When embedded in a PCB, the footprint needs (layer "F.Cu") (uuid "...") (at X Y ROT) right after the name.
    # KiCad's stdlib .kicad_mod files already have (layer "F.Cu") at top — we just need to add (at ...) and (uuid).
    insert_after_descr = re.search(r'(\(descr "[^"]*"\))', text)
    if not insert_after_descr:
        # Add after (tags) or (layer)
        insert_after_descr = re.search(r'(\(tags "[^"]*"\))', text)
    if not insert_after_descr:
        insert_after_descr = re.search(r'(\(layer "[^"]+"\))', text)
    if not insert_after_descr:
        raise RuntimeError("Can't find insertion point in footprint")
    anchor = f'\n\t\t(uuid "{uuid.uuid4()}")\n\t\t(at {x:.3f} {y:.3f} {rot:.0f})'
    return text.replace(
        insert_after_descr.group(1),
        insert_after_descr.group(1) + anchor,
        1,
    )


def main() -> int:
    if len(sys.argv) not in (6, 7):
        print(__doc__, file=sys.stderr)
        return 2
    refdes = sys.argv[1]
    lib = sys.argv[2]
    name = sys.argv[3]
    x = float(sys.argv[4])
    y = float(sys.argv[5])
    rot = float(sys.argv[6]) if len(sys.argv) == 7 else 0.0

    mod_text = find_mod(lib, name).read_text()
    # KiCad .kicad_mod top-level wrapper is `(footprint "NAME" ... )`. We need
    # to keep that wrapper and indent it by one tab so it sits inside the PCB.
    mod_text = freshen_uuids(mod_text)
    mod_text = set_reference(mod_text, refdes)
    mod_text = set_anchor(mod_text, x, y, rot)

    # Replace footprint name with lib:name format (PCB format expects "LIB:NAME").
    mod_text = re.sub(
        r'^\(footprint "[^"]+"',
        f'(footprint "{lib}:{name}"',
        mod_text,
        count=1,
    )
    # Indent every line by one tab for proper PCB nesting.
    indented = "\n".join("\t" + ln if ln.strip() else ln for ln in mod_text.splitlines())

    pcb_text = PCB.read_text()
    shutil.copy2(PCB, PCB.with_suffix(PCB.suffix + ".pre_place_backup"))
    insert_at = pcb_text.rstrip().rfind(")")
    new_pcb = pcb_text[:insert_at] + "\n" + indented + "\n" + pcb_text[insert_at:]
    PCB.write_text(new_pcb)
    print(f"Placed {refdes} = {lib}:{name} at ({x}, {y}) rot {rot}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
