#!/usr/bin/env python3
"""fix_pad_nets.py — rewrite pad-level `(net "name")` to `(net code "name")`.

KiCad pads use `(net code "name")`. Footprints emitted from kicad_mod
files often have only `(net "name")` (no code). Zones also use `(net "name")`
but in a DIFFERENT syntactic position — rewriting zone nets to include a
code breaks the file.

This script:
  1. Builds {name: code} from top-level `(net code "name")` decls.
  2. Walks the file and for every `(net "name")` match, checks the
     enclosing block. If inside `(pad ...)`, rewrite to `(net code "name")`.
     If inside `(zone ...)` or other context, leave alone.
  3. Verifies the resulting file still loads via `kicad-cli pcb drc`.

Usage: tools/fix_pad_nets.py PCB_PATH
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def find_enclosing_block_head(text: str, pos: int) -> str | None:
    """Walk backward from pos looking for the innermost enclosing
    `(name ...` token. Returns the name (e.g. "pad", "zone", "footprint")
    or None."""
    depth = 0
    i = pos - 1
    while i >= 0:
        ch = text[i]
        if ch == ")":
            depth += 1
        elif ch == "(":
            if depth == 0:
                # Found the opening paren of our enclosing block. Read the
                # word that follows it.
                j = i + 1
                while j < len(text) and text[j].isalnum() or text[j] == "_":
                    j += 1
                return text[i + 1: j] if j > i + 1 else None
            depth -= 1
        i -= 1
    return None


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: fix_pad_nets.py PCB_PATH", file=sys.stderr)
        return 2
    pcb = Path(sys.argv[1])
    text = pcb.read_text()

    # Backup
    backup = pcb.with_suffix(pcb.suffix + ".pre_padnet_fix")
    backup.write_text(text)

    name_to_code = {n: int(c) for c, n in
                    re.findall(r'^\t\(net (\d+) "([^"]*)"\)', text, re.MULTILINE)}
    print(f"net decls loaded: {len(name_to_code)}")

    matches = list(re.finditer(r'\(net "([^"]*)"\)', text))
    print(f"name-only (net ...) occurrences: {len(matches)}")

    # Walk back to front so positions stay valid as we splice
    rewritten = 0
    skipped_by_block = {}
    new_text = text
    for m in reversed(matches):
        name = m.group(1)
        if name not in name_to_code:
            continue
        head = find_enclosing_block_head(text, m.start())
        if head != "pad":
            skipped_by_block[head] = skipped_by_block.get(head, 0) + 1
            continue
        new = f'(net {name_to_code[name]} "{name}")'
        new_text = new_text[:m.start()] + new + new_text[m.end():]
        rewritten += 1

    pcb.write_text(new_text)
    print(f"rewrote: {rewritten} pad nets")
    print(f"skipped (not in a pad): {skipped_by_block}")

    # Verify
    r = subprocess.run(["kicad-cli", "pcb", "drc", "--format", "report",
                        "-o", "/tmp/drc.rpt", str(pcb)],
                       capture_output=True)
    if r.returncode != 0:
        print("ERROR: PCB no longer loads. Restoring backup.", file=sys.stderr)
        pcb.write_text(backup.read_text())
        return 1
    print("PCB loads OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
