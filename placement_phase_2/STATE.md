# STATE (pointer only — durable history lives in LEDGER.md + metrics.jsonl)

Phase: **C — Placement engine**
Current approach: (none yet — Phase C just opened). Champion floor plan: floorplan.json (A).
Last completed: B(4) — Phase B gate MET. Floor-planner (spec + floorplan.py Approach A
  champion @892mm proxy + floorplan_partition.py Approach B challenger) documented as the
  `badge-placement` skill. Commit pending this iter.

Next intended action (Phase C):
  1. C(5): write a short PLACEMENT_SPEC (purpose, objective=ratsnest s.t. locked gates,
     how validated) — plan-before-build — then build tools/place.py: a CONSTRUCTIVE per-zone
     placer that reads floorplan.json and lays each zone's parts by its topology
     (ring=decoupling around anchor IC pins via the auto_decouple primitive; chain=signal-flow
     line; row/column=evenly spaced; cluster=compact pack), pins fixed/edge parts at their
     locked positions/rotations, keeps everything inside Edge.Cuts. Emit + measure.
  2. C(6+): legalize overlaps (pcb-placement spread.py / check_courtyards) and pull parts to
     real pin proximity; drive ratsnest down. Then add a global optimizer (simulated annealing
     or force-directed, per placement_research.md) as champion/challenger vs the constructive
     placement; keep the champion. Re-measure every iteration; escalate if the metric plateaus
     short of the gate (no repeating a stalled move).
  3. Render and LOOK every few iterations (pcb-views render_all.sh / render_area.py) — catch
     wrong-facing connectors, off-edge parts, collisions the metrics miss.

LOCKED Phase C exit gates (ALL must hold; tighten only):
  overlaps==0; offboard==0; unplaced==0; fp_unresolved==0; fixed_ok==true
  (J20 top-right plug-up; J10 USB-C bottom; SW1 bottom-left; U30 left y=110 & D20 right y=110;
   J31 microSD B.Cu edge; 4× M2.5 holes corners);
  decoupling_max_mm<=2.0; dfm_spacing_violations==0;
  ratsnest_mm >= 20% better than baseline 2947 (i.e. <=2358) AND non-regressing — beat & lock
  the ~1339mm phase-1 reference; erc_errors<=14 (no regression).
  Placement produced BY TOOLS, not hand-placing parts. Then plateau (<2% over 5 iters) to finish.

Board: 88×54mm, x[100,188] y[80,134]. Staging grid currently holds 75 movable parts below y=134.
