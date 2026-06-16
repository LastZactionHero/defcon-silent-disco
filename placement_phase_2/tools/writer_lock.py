#!/usr/bin/env python3
"""writer_lock.py — single-writer discipline for the placement loop (Resolution 5).

The loop and an interactively-open KiCad are two writers fighting for one
`.kicad_pcb`. During run 2 the user had KiCad open; it saved over the loop's
writes ("were changes overwritten?"). The fix is a discipline, enforced here:
**the loop owns the board file. Review it via renders or a read-only KiCad.**

KiCad signals "I have this project open" two ways, both in the board's directory:
  - `~<project>.kicad_pro.lck`   — the editor's project lock (JSON: host/user)
  - `_autosave-<board>.kicad_pcb` — an in-progress editor session with unsaved work

If either is present, a tool that writes the board would race the editor. So the
single authoritative writer (geom.apply) calls `assert_writable()` first and
refuses unless the human explicitly overrides with ALLOW_WRITE_LOCKED=1.

This module has NO dependency on pcbnew so it is safe to import everywhere.

Usage (also runnable as a preflight in run_pipeline.sh):
  writer_lock.py defcon_badge/defcon_badge.kicad_pcb        # exit 0 free / 3 locked
  writer_lock.py PCB --quiet
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


class BoardLocked(RuntimeError):
    """Raised when a writer tool would race an open KiCad on the same board."""


def lock_files(pcb) -> list[Path]:
    """Editor-presence markers in the board's directory, if any exist."""
    pcb = Path(pcb)
    d = pcb.parent
    # project lock: KiCad names it ~<project-stem>.kicad_pro.lck
    markers = [
        d / f"~{pcb.stem}.kicad_pro.lck",
        d / f"_autosave-{pcb.name}",
    ]
    # also catch a board-level lock if a future KiCad writes one
    markers.append(d / f"~{pcb.name}.lck")
    return [m for m in markers if m.exists()]


def who_holds(markers) -> str:
    """Best-effort 'host/user' string from a .lck marker, for the error message."""
    for m in markers:
        if m.suffix == ".lck":
            try:
                d = json.loads(m.read_text())
                return f"{d.get('username', '?')}@{d.get('hostname', '?')}"
            except Exception:
                pass
    return "an open KiCad editor"


def is_locked(pcb) -> bool:
    return bool(lock_files(pcb))


def assert_writable(pcb) -> None:
    """Refuse to write a board that an interactive KiCad holds open.

    Override for a deliberate, supervised write with ALLOW_WRITE_LOCKED=1 (the
    human takes responsibility for closing KiCad / discarding its copy first)."""
    if os.environ.get("ALLOW_WRITE_LOCKED") == "1":
        return
    markers = lock_files(pcb)
    if markers:
        names = ", ".join(m.name for m in markers)
        raise BoardLocked(
            f"REFUSING to write {Path(pcb).name}: it is open in KiCad "
            f"({who_holds(markers)}; markers: {names}).\n"
            f"Single-writer rule: the loop owns the board file — close KiCad and "
            f"review via renders or a read-only viewer. To override (you accept the "
            f"race and will discard KiCad's copy), set ALLOW_WRITE_LOCKED=1."
        )


def main() -> int:
    quiet = "--quiet" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("usage: writer_lock.py PCB [--quiet]", file=sys.stderr)
        return 2
    markers = lock_files(args[0])
    if markers:
        if not quiet:
            print(f"LOCKED: {Path(args[0]).name} is open in KiCad "
                  f"({who_holds(markers)}). Writers will refuse.")
            for m in markers:
                print(f"  marker: {m.name}")
        return 3
    if not quiet:
        print(f"writable: {Path(args[0]).name} (no editor lock)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
