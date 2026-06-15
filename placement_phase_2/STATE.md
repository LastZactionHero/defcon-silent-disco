# STATE (pointer only — durable history lives in LEDGER.md + metrics.jsonl)

Phase: **B — Floor-plan tool**
Current approach: Approach A (constructive) DONE & valid; Approach B next.
Last completed: B(3) — tools/floorplan.py + floorplan.json (Approach A). Valid: 79 parts
  placed (68 zoned + 11 fixed), est_ratsnest proxy 892mm. Commit pending this iter.

Next intended action (Phase B):
  1. [done B2] Committed floor-planner SPEC — see placement_phase_2/FLOORPLAN_SPEC.md.
  2. [done B3] Approach A (constructive) — tools/floorplan.py, floorplan.json, valid,
     est_ratsnest proxy 892mm.
  3. B(4): implement Approach B (connectivity-driven min-cut partition) as
     tools/floorplan_partition.py, reusing floorplan.py classify/validate/score; build the
     component graph weighted by shared non-power nets, partition into the same zones, map
     partitions to regions via their fixed anchors; score both; record CHAMPION: in LEDGER;
     keep the winning floorplan.json.
  4. Document the floor-planner as a skill; list under HARNESS "Skills authored".
  5. When Phase B gate holds (>=2 approaches scored + champion + plan validates), advance
     STATE to Phase C (placement engine) — build the tool that moves staged parts onto the
     board per the champion floor plan, then optimize to the locked gates.

Exit gate (Phase B): floor-planner tool WITH committed spec exists; emitted plan validates
(one zone per component, zones fit Edge.Cuts, fixed/edge parts at required spots, grouping
matches design subsystems, signal-flow ordering respected); ≥2 approaches scored, champion
recorded; tool documented as a skill. See HARNESS.md "Phase B".

Fixed constraints (must hold by Phase C): J20 top-right plug-up; J10 USB-C bottom edge;
SW1 bottom-left; U30 IR-RX left edge y=110 & D20 IR-LED right edge y=110 (mirror);
J31 microSD on B.Cu edge-accessible; 4× M2.5 holes at corners. Board 88×54mm, x[100,188] y[80,134].
