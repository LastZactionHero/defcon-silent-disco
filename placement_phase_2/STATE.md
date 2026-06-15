# STATE (pointer only — durable history lives in LEDGER.md + metrics.jsonl)

Phase: **B — Floor-plan tool**
Current approach: (none yet — Phase B just opened)
Last completed: A(1) — board depopulated, measure.py + depopulate.py built, baseline logged
  (ratsnest 2947mm, overlaps 0, offboard 75, erc 14). Commit f4d1c94.

Next intended action (Phase B):
  1. Write a committed floor-planner SPEC in placement_phase_2/ (purpose, the objective it
     optimizes, the zone model, how it is validated) BEFORE implementing — plan-before-build.
  2. Derive functional zones from badge_hw_design.md + the netlist (MCU+flash+xtal+decoupling;
     power chain USB-C→TP4056→switch→LDO→3V3; 4× SK9822 across top; audio TM8211→TDA1308→J20;
     IR U30/D20 mirror at y=110; 3 buttons; SAO/UART/SWD). Re-derive — do NOT resurrect
     defcon_badge/tools/badge_floorplan.py blindly (HARNESS: reference but re-derive).
  3. Build tools/floorplan.py emitting a floor-plan artifact (zones w/ bboxes inside
     Edge.Cuts; every component in exactly one zone; fixed/edge constraints recorded).
  4. Implement a SECOND distinct approach (e.g. partitioning/min-cut vs. constructive
     intent-driven, or force-directed seed) and score both on a documented metric; record
     CHAMPION: in LEDGER.
  5. Document the floor-planner as a skill and list it under HARNESS "Skills authored".

Exit gate (Phase B): floor-planner tool WITH committed spec exists; emitted plan validates
(one zone per component, zones fit Edge.Cuts, fixed/edge parts at required spots, grouping
matches design subsystems, signal-flow ordering respected); ≥2 approaches scored, champion
recorded; tool documented as a skill. See HARNESS.md "Phase B".

Fixed constraints (must hold by Phase C): J20 top-right plug-up; J10 USB-C bottom edge;
SW1 bottom-left; U30 IR-RX left edge y=110 & D20 IR-LED right edge y=110 (mirror);
J31 microSD on B.Cu edge-accessible; 4× M2.5 holes at corners. Board 88×54mm, x[100,188] y[80,134].
