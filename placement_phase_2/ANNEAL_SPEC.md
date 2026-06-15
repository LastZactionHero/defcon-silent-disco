# Global optimizer spec — simulated annealing (committed BEFORE implementation)

Tool: `placement_phase_2/tools/anneal.py`. Status: spec frozen at C(7).
Why: the constructive placer + greedy decouple+spread plateaus — it can hit 6/8 gates but
can't jointly satisfy decoupling_max<=2.0 AND overlaps==0 AND push ratsnest <1339, because
those objectives are coupled (cramming caps to pins creates overlaps; resolving overlaps
pushes caps away). A global optimizer that scores all objectives in one cost function and
explores moves stochastically is the textbook fix (TimberWolf-style SA; see placement_research.md).

## State
Each movable part has (x, y, rot, side). Fixed parts (J20,J10,SW1,U30,D20,J31,J11,SW23,H*)
are frozen — never proposed for moves. Start state = current constructive placement (warm
start) optionally pre-decoupled by decouple.py.

## Cost function (minimize)
  cost = w_rat * ratsnest_mm
       + w_ovl * sum(courtyard_overlap_area)        # ->0
       + w_off * num_offboard                        # centroid outside Edge.Cuts
       + w_edge* sum(edge_intrusion for non-edge parts)   # courtyard past outline
       + w_dec * sum(max(0, deco_dist_i - 2.0))      # decoupling proximity penalty
weights staged so hard constraints dominate (e.g. w_ovl,w_off,w_edge >> w_rat; w_dec mid).
ratsnest via the MST metric (GND excluded), incrementally where possible.

## Moves (proposal distribution)
- translate a part by a gaussian step (annealed magnitude);
- swap two same-zone parts;
- rotate a part by 90°;
- (rare) jump a part to a random spot in its floorplan zone.
Accept by Metropolis: ΔE<0 always; else exp(-ΔE/T). Geometric cooling T*=alpha each epoch.
Constrain translations to keep a part within its floorplan zone (soft) / board (hard).

## Schedule / scale
Warm start from constructive placement (already ~1580mm), so few thousand iterations suffice.
numpy for vectorised distance/overlap. Target wall-clock < a couple minutes per run. If SA
underperforms, the challenger is force-directed/analytical (also in research) — keep champion.

## Validation
After SA: run measure.py. Accept the result ONLY if every previously-passing gate still holds
and the objective improved; else revert (git). Render + LOOK. Compare ratsnest vs constructive
champion; keep the better. Re-run with different seeds/weights; keep best with all gates held.

## Gates this must achieve (with constructive's already met)
overlaps==0, offboard==0, decoupling_max_mm<=2.0, dfm copper/edge clearance==0, ratsnest
minimized (target <1339) and plateaued. Silk-only dfm handled separately by a silk pass.

## Reuse / reproducibility
Deterministic given a --seed. Reads/writes the .kicad_pcb via the same anchor/flip helpers as
place.py. decouple.py may seed cap positions first. Document in the badge-placement skill.
