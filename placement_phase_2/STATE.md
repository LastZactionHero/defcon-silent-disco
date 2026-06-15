# STATE (pointer only — durable history lives in LEDGER.md + metrics.jsonl)

Phase: **B — Floor-plan tool**
Current approach: spec frozen (FLOORPLAN_SPEC.md); implementing approaches next.
Last completed: B(2) — committed FLOORPLAN_SPEC.md (zone model, per-subsystem assignment,
  2 approaches, scoring metric, validation gate). Board unchanged. Commit pending this iter.

Next intended action (Phase B):
  1. [done B2] Committed floor-planner SPEC — see placement_phase_2/FLOORPLAN_SPEC.md.
  2. B(3): implement Approach A (constructive intent-driven) in tools/floorplan.py per the
     spec: pin fixed parts, lay zones (LEDs top, IR pair sides@y110, audio upper-right→J20,
     power bottom→J10/J11, MCU center ring, buttons bottom, SAO free edge), pack to courtyard
     area, emit placement_phase_2/floorplan.json, validate, score (est_ratsnest + violations).
  3. B(4): implement Approach B (connectivity-driven min-cut partition); score both; record
     CHAMPION: in LEDGER; keep the winning floorplan.json.
  4. Document the floor-planner as a skill; list under HARNESS "Skills authored".
  5. When Phase B gate holds, advance STATE to Phase C (placement engine).

Exit gate (Phase B): floor-planner tool WITH committed spec exists; emitted plan validates
(one zone per component, zones fit Edge.Cuts, fixed/edge parts at required spots, grouping
matches design subsystems, signal-flow ordering respected); ≥2 approaches scored, champion
recorded; tool documented as a skill. See HARNESS.md "Phase B".

Fixed constraints (must hold by Phase C): J20 top-right plug-up; J10 USB-C bottom edge;
SW1 bottom-left; U30 IR-RX left edge y=110 & D20 IR-LED right edge y=110 (mirror);
J31 microSD on B.Cu edge-accessible; 4× M2.5 holes at corners. Board 88×54mm, x[100,188] y[80,134].
