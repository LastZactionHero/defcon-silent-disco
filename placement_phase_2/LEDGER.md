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

[2026-06-15] B(2) — Floor-planner SPEC committed (plan-before-build) | Extracted full
component/net inventory (79 fps) and mapped every part to a subsystem from real nets, not
guesswork. Wrote placement_phase_2/FLOORPLAN_SPEC.md: purpose, objective (min est. inter-zone
ratsnest s.t. hard constraints), zone model (ring/chain/row/column/cluster/edge), concrete
per-subsystem zone assignment for THIS board (mcu/power/audio/leds/sao/buttons + IR/connectors
as fixed-edge), the locked fixed-constraint table, TWO approaches (A constructive intent-driven,
B connectivity-driven min-cut partition), the scoring metric, and the Phase-B validation gate.
Resolved the design-doc vs HARNESS jack conflict in favor of HARNESS (J20 top-right, locked). |
RESULT: spec frozen; board unchanged so metrics row B(2) == baseline (ratsnest 2947, overlaps 0,
offboard 75, erc 14) — expected during a planning iteration. | Δ none (planning iteration).
NEXT: B(3) — implement Approach A (constructive) in tools/floorplan.py, emit + validate
floorplan.json, score it.

[2026-06-15] B(3) — Approach A (constructive floor-planner) implemented | Built
tools/floorplan.py: generic engine (classify each part by its schematic SHEET = ground-truth
subsystem, with net/refdes fallbacks; assign to a zone; pin fixed/edge parts; emit + validate
+ score) with board geometry as config. Sheet membership parsed from defcon_badge/*.kicad_sch
(definitive — 58/79 had it via nets, the rest resolved by sheet). 7 zones: leds(top),
mcu(center ring), audio(right→J20), power(bottom→J10/J11), buttons(bottom-right), sao(left),
ir(near D20). |
RESULT: floorplan.json emitted, validation OK (all 79 parts placed: 68 zoned + 11 fixed incl.
H1-4; every zone inside Edge.Cuts; no capacity overflow, max util 0.67 buttons). Approach-A
score est_ratsnest=892.4mm (centroid proxy) — well below the 1339mm reference, grouping looks
strong. Board itself unchanged (floor plan is a plan, not a placement) so metrics row B(3) ==
baseline. | Δ floorplan quality: first scored plan (892mm proxy).
NEXT: B(4) — implement Approach B (connectivity-driven min-cut partition) reusing floorplan.py's
classify/validate/score; compare est_ratsnest + capacity vs A; record CHAMPION:.
