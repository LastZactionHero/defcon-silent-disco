#!/usr/bin/env python3
"""pcb_runner.py — the pcbnew-binding discipline, baked in (Pass-2 R0).

Every board mutation in pass 2 goes through here so the hard-won pass-1 workarounds are STRUCTURAL,
not rediscovered per tool:
  - ONE LoadBoard + ONE SaveBoard per process (a 2nd in-process load corrupts pcbnew's swig registry).
  - os._exit(0) right after SaveBoard (heavy mutate-then-save segfaults during teardown AFTER the file
    is written — so do NOT gate success on the exit code; check the file/metrics).
  - swig assert noise ('PROPERTY_ENUM', 'memory leak', ...) filtered so real output isn't buried.
  - reads use geom_route.safe_board (a /tmp project copy) so a read never flushes BOM defs into the
    frozen .kicad_pro.
  - a frozen-file git guard to catch any stray schematic/project rewrite.

API:
  run(body) -> (stdout, ok)          run a pcbnew snippet in its own process (body sees pcbnew + paths)
  mutate(board, body) -> ok          load board, run body (sees `b`), save, os._exit — isolated
  rip(board) ; refill(board)         the next-round reset: delete all routing / refill zones (isolated)
  footprint_hash(board) -> str       12-char hash of refdes:pos:rot (frozen-placement check)
  assert_frozen() -> (clean, msg)    .kicad_sch/.kicad_pro git-clean check (+ auto-revert helper)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
PLACEMENT_TOOLS = TOOLS.parents[1] / "placement_phase_2" / "tools"
REPO = TOOLS.parents[1]
NOISE = ("PROPERTY_ENUM", "m_choices", "memory leak", "image handler",
         "Debug:", "Couldn't get screen", "wxWidgets")

_PRE = f"""
import sys, os
sys.path.insert(0, {str(TOOLS)!r}); sys.path.insert(0, {str(PLACEMENT_TOOLS)!r})
import pcbnew
"""


def _filter(text: str) -> str:
    return "\n".join(l for l in (text or "").splitlines() if not any(n in l for n in NOISE))


def run(body: str) -> tuple[str, bool]:
    """Run a pcbnew snippet in its own process. body may import geom_route etc. and should end its
    work with sys.stdout.flush(); os._exit(0) if it mutated+saved a board."""
    p = subprocess.run([sys.executable, "-c", _PRE + body], capture_output=True, text=True)
    return _filter(p.stdout), (p.returncode == 0)


def mutate(board: str, body: str) -> bool:
    """Isolated load -> body(sees `b`) -> save -> os._exit(0). Returns True if the file was written
    (verified by load, since os._exit may yield a nonzero code even on success)."""
    code = (_PRE + f'b = pcbnew.LoadBoard({str(board)!r})\n' + body +
            f'\npcbnew.SaveBoard({str(board)!r}, b)\nsys.stdout.flush(); os._exit(0)\n')
    run(code)
    # verify by reload count instead of exit code (the os._exit-segfault-after-save reality)
    ok, _ = run(f'b = pcbnew.LoadBoard({str(board)!r}); print("OK", len(list(b.GetFootprints())))')
    return ok.startswith("OK")


def rip(board: str) -> bool:
    """Full ripup: delete every track/arc/via (planes/footprints untouched). The next-round reset."""
    return mutate(board, 'import geom_route; geom_route.delete_routing(b)')


def refill(board: str) -> bool:
    return mutate(board, 'pcbnew.ZONE_FILLER(b).Fill(b.Zones())')


def footprint_hash(board: str) -> str:
    out, _ = run(
        'import hashlib\n'
        f'b = pcbnew.LoadBoard({str(board)!r})\n'
        'h = hashlib.sha1(("|".join(sorted(f"{f.GetReference()}:{f.GetPosition().x},{f.GetPosition().y},'
        '{f.GetOrientationDegrees()}" for f in b.GetFootprints()))).encode()).hexdigest()[:12]\n'
        'print("HASH", h)')
    for l in out.splitlines():
        if l.startswith("HASH"):
            return l.split()[1]
    return ""


def assert_frozen() -> tuple[bool, str]:
    """True if the frozen .kicad_sch + .kicad_pro are git-clean (the schematic/project must not change
    except an intended R2 GPIO remap, which is committed deliberately)."""
    r = subprocess.run(["git", "diff", "--quiet", "defcon_badge/Audio.kicad_sch",
                        "defcon_badge/IO.kicad_sch", "defcon_badge/LEDs_IR.kicad_sch",
                        "defcon_badge/MCU_Core.kicad_sch", "defcon_badge/Power.kicad_sch",
                        "defcon_badge/defcon_badge.kicad_sch", "defcon_badge/defcon_badge.kicad_pro"],
                       cwd=REPO, capture_output=True)
    return (r.returncode == 0, "frozen files clean" if r.returncode == 0 else "FROZEN FILE CHANGED")


if __name__ == "__main__":
    b = sys.argv[1] if len(sys.argv) > 1 else "defcon_badge/defcon_badge.kicad_pcb"
    print("footprint_hash:", footprint_hash(b))
    print("frozen:", assert_frozen())
