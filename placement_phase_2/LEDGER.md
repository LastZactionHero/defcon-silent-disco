# LEDGER — durable decision log (APPEND-ONLY, never rotate or truncate)

Entry format: `[ISO-date] <phase>(<iter>) — action | rationale | result | Δmetric`
Prefixes: `BLOCKER:` `REVIEW:` `CHAMPION:`

This file is your long-term memory. The previous run failed partly because it only
remembered the last 5 iterations and could not see that it was going in circles. Never
truncate this file. Read its tail every wake-up; grep it when you need older context.

## Log
[seed] A(0) — Mission initialized | Prior run thrashed: greedy local edits, floor-planning
discovered ~15 fix-passes too late, 7 sequential cleanup_pass scripts, lossy 5-iter memory.
This loop is instrumented (append-only metrics + ledger, plan-before-build, convergence
escalation, locked gates, tools-over-edits) to prevent recurrence. | First real action:
Phase A — depopulate, build tools/measure.py, baseline. | Δ none (baseline pending).

[2026-06-15] A(1) — Reset & instrument complete | Wired harness to real paths + target
board (defcon_badge/defcon_badge.kicad_pcb); discarded phase-1 root harness; deleted
thrash artifacts; built tools/measure.py (locked-schema metric engine) + tools/depopulate.py
(adaptive shelf-pack sweep). Depopulated board: 75 movable parts → off-board staging grid,
Edge.Cuts untouched, mounting holes H1-H4 kept at corners. |
  RESULT — Phase A exit gate MET: depopulated ✓, Edge.Cuts unchanged ✓, measure.py runs &
  baseline logged ✓, thrash removed ✓, ledger+state seeded ✓.
  BASELINE (depopulated, commit f4d1c94): ratsnest=2947.16mm  overlaps=0  offboard=75
  unplaced=0  fp_unresolved=0  decoupling_max=61.96mm  dfm_spacing=3  erc=14  drc=31  fixed_ok=false.
  REFERENCE (phase-1 final placed board, for context not as a gate): ratsnest≈1339mm —
  that is the number to *beat & lock*, not just the 20%-of-2947 floor (≤2358mm).
  Phase C gate targets: ratsnest ≤2358mm (≥20% vs baseline) AND ideally <1339; overlaps=0;
  offboard=0; unplaced=0; fp_unresolved=0; decoupling_max≤2.0; dfm_spacing=0; fixed_ok=true;
  erc≤14 (no regression). | Δ baseline established (no prior row to diff).
  NOTE: measure.py fixed_detail edge-checks tightened post-baseline (a part swept below the
  outline no longer false-counts as "on bottom edge"); fixed_ok was already correctly false,
  so the baseline row's gate metrics stand. Append-only: baseline row left as recorded.
  NEXT: Phase B — write a floor-planner spec, then build a floorplan tool that partitions
  the netlist + design intent into zones; implement ≥2 approaches and score them.
