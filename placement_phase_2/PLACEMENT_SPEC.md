# Placement-engine spec (committed BEFORE implementation — plan-before-build)

Tools: `placement_phase_2/tools/place.py` (constructive) + later a global optimizer.
Consumes: champion `placement_phase_2/floorplan.json`. Mutates: the target .kicad_pcb.
Status: spec frozen at C(5).

## Purpose
Move every movable part from the off-board staging grid onto the board into its assigned
zone, honoring zone topology and the locked fixed/edge constraints, then optimize component
positions to minimize ratsnest while satisfying every LOCKED Phase-C gate.

## Objective
Minimize `ratsnest_mm` (MST wirelength over signal nets, GND excluded) subject to HARD gates:
overlaps==0, offboard==0, unplaced==0, fp_unresolved==0, fixed_ok, decoupling_max_mm<=2.0,
dfm_spacing_violations==0, erc<=14. Target ratsnest <=2358 (>=20% vs baseline 2947) and
beat-and-lock the ~1339mm phase-1 reference.

## Pipeline (champion/challenger; keep the best by measured ratsnest with gates held)
1. **Constructive (place.py)** — deterministic first placement:
   - Pin fixed parts at floorplan.json `fixed` pos/rot (layer already correct; don't flip).
   - For each zone, lay its parts by `topology`:
     - `ring`   — anchor IC at zone center; decoupling caps to its power pins
       (pcb-placement `auto_decouple` / `arrange_around_ic`); support parts packed nearby.
     - `chain`  — parts in signal-flow order along the zone's `flow` direction.
     - `row`/`column` — evenly spaced line.
     - `cluster`— compact shelf-pack.
   - Courtyard-aware shelf-packing keeps within-zone overlaps at zero; stay inside the bbox.
2. **Legalize** — remove residual overlaps with pcb-placement `spread.py`, then
   `validate_placement.py` to pull any part back inside Edge.Cuts.
3. **Refine** — decoupling proximity (`auto_decouple`), then a GLOBAL optimizer
   (simulated annealing or force-directed per placement_research.md) minimizing ratsnest with
   a courtyard-overlap + off-board + fixed-displacement penalty. SA is the baseline; compare a
   second method; keep champion.

## Validation / measurement
`measure.py` every iteration → append metrics row. Render with pcb-views every few iters and
LOOK (wrong-facing connectors, off-edge, collisions). A change that raises ratsnest or breaks
a gate is reverted (git). Plateau (<2% over 5 iters) with all gates held => Phase C done.

## Constraints / notes
- Edge.Cuts FINAL. Mounting holes H1-4 locked. J11/J31 stay on B.Cu.
- Fixed pos/rot are starting points the optimizer may nudge slightly, but the EDGE/SIDE and
  layer are hard (J20 top-right plug-up; J10 bottom; SW1 bottom-left; U30 left y110 / D20
  right y110 mirror; J31 microSD B.Cu edge).
- Tools do the placing — no hand-editing the .kicad_pcb to fix a symptom.
