#!/usr/bin/env python3
"""check_footprints.py — find footprint refs in the PCB and verify they resolve.

Resolution order (matches KiCad):
  1) Per-project fp-lib-table (defcon_badge/fp-lib-table)
  2) Global fp-lib-table (~/.config/kicad/10.0/fp-lib-table)
  3) Common system locations under /usr/share/kicad/footprints/

Exit code 0 if all resolve, 1 if any missing. JSON report to stdout.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PCB = REPO_ROOT / "defcon_badge" / "defcon_badge.kicad_pcb"

FP_TABLE_RE = re.compile(
    r'\(lib\s+\(name\s+"([^"]+)"\)\s*\(type\s+"[^"]+"\)\s*\(uri\s+"([^"]+)"\)'
)
KICAD_FOOTPRINTS = [
    Path("/usr/share/kicad/footprints"),
    Path("/usr/local/share/kicad/footprints"),
]


def parse_fp_table(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    text = path.read_text()
    libs = {}
    for m in FP_TABLE_RE.finditer(text):
        libs[m.group(1)] = expand(m.group(2))
    return libs


def expand(uri: str) -> str:
    uri = uri.replace("${KICAD10_FOOTPRINT_DIR}", "/usr/share/kicad/footprints")
    uri = uri.replace("${KICAD_FOOTPRINT_DIR}", "/usr/share/kicad/footprints")
    uri = uri.replace("${KIPRJMOD}", str(REPO_ROOT / "defcon_badge"))
    return os.path.expanduser(os.path.expandvars(uri))


def find_lib_dir(name: str, tables: list[dict[str, str]]) -> Path | None:
    for t in tables:
        if name in t:
            return Path(t[name])
    for base in KICAD_FOOTPRINTS:
        cand = base / f"{name}.pretty"
        if cand.is_dir():
            return cand
    return None


def main() -> int:
    project_table = parse_fp_table(REPO_ROOT / "defcon_badge" / "fp-lib-table")
    global_table = parse_fp_table(
        Path(os.path.expanduser("~/.config/kicad/10.0/fp-lib-table"))
    )
    tables = [project_table, global_table]

    pcb_text = PCB.read_text()
    refs = sorted(set(re.findall(r'\(footprint\s+"([^"]+)"', pcb_text)))

    report = {"total": len(refs), "missing": [], "resolved": []}
    for ref in refs:
        if ":" not in ref:
            report["missing"].append({"ref": ref, "reason": "no library prefix"})
            continue
        lib, name = ref.split(":", 1)
        lib_dir = find_lib_dir(lib, tables)
        if lib_dir is None:
            report["missing"].append({"ref": ref, "reason": f"library '{lib}' not found"})
            continue
        if not (lib_dir / f"{name}.kicad_mod").is_file():
            report["missing"].append(
                {"ref": ref, "reason": f"footprint not in {lib_dir}"}
            )
            continue
        report["resolved"].append(ref)

    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if not report["missing"] else 1


if __name__ == "__main__":
    sys.exit(main())
