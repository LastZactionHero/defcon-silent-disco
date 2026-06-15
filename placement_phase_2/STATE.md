# STATE (pointer only — durable history lives in LEDGER.md + metrics.jsonl)

Phase: **C — Placement engine**
Current approach: constructive placement landed (place.py); refining toward gates.
Last completed: C(5) — PLACEMENT_SPEC + tools/place.py; all 75 parts on-board, grouped.
  ratsnest 2947 → 1604.55mm (−45%). offboard 4, overlaps 2, decoupling_max 29.1, erc 14.
  Rendered + looked (renders/views/area_100_80_188_134.png). Commit pending this iter.

Next intended action (Phase C):
  1. C(6): legalize — pcb-placement spread.py to clear the 2 courtyard overlaps; pull the 4
     off-edge parts inside via validate_placement. Nudge J20→top-right corner (y~84) and
     SW1→bottom-left corner (y~130) in floorplan.py FIXED config so fixed_ok passes; set
     connector orientations (J20 plug up, J10 plug down). Re-place, re-measure, re-render.
  2. C(7): auto_decouple U3 (and U20/U21) to drive decoupling_max_mm 29→≤2.0 (caps to IC
     power pins). Build/extend a tool; don't hand-edit.
  3. C(8+): global optimizer — simulated annealing (baseline) minimizing ratsnest with
     courtyard-overlap + off-board + fixed-displacement penalties; compare a 2nd method
     (force-directed); keep champion. Target ratsnest <1339 and plateau with ALL gates held.
  4. Render + LOOK every few iters; escalate (switch method / global re-place) if ratsnest
     plateaus short of gate — never repeat a stalled move.

LOCKED Phase C exit gates (ALL must hold; tighten only):
  overlaps==0; offboard==0; unplaced==0; fp_unresolved==0; fixed_ok==true
  (J20 top-right plug-up; J10 USB-C bottom; SW1 bottom-left; U30 left y=110 & D20 right y=110;
   J31 microSD B.Cu edge; 4× M2.5 holes corners);
  decoupling_max_mm<=2.0; dfm_spacing_violations==0;
  ratsnest_mm >= 20% better than baseline 2947 (i.e. <=2358) AND non-regressing — beat & lock
  the ~1339mm phase-1 reference; erc_errors<=14 (no regression).
  Placement produced BY TOOLS, not hand-placing parts. Then plateau (<2% over 5 iters) to finish.

Board: 88×54mm, x[100,188] y[80,134]. Staging grid currently holds 75 movable parts below y=134.
