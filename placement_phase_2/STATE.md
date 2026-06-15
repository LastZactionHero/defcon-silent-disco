# STATE (pointer only — durable history lives in LEDGER.md + metrics.jsonl)

Phase: **C — Placement engine**
Current approach: constructive placement legalized; 4/8 hard gates pass. Refining.
Last completed: C(6) — overlaps 0, offboard 0, unplaced 0, fixed_ok TRUE. ratsnest 1580mm.
  place.py now has row topology + board-clamp + flip-to-back; BOOTSEL on B.Cu. Commit pending.

GATE STATUS: overlaps 0 ✓ | offboard 0 ✓ | unplaced 0 ✓ | fp_unresolved 0 ✓ | fixed_ok ✓ |
  erc 14 ✓ (<=14) | ratsnest 1580 (<=2358 ✓; target <1339) | decoupling_max 26.3 ✗ (need <=2.0)
  | dfm_spacing 190 ✗ (need 0; mostly silk_overlap + copper/edge clearance, unrouted board).

Next intended action (Phase C):
  1. C(7): auto_decouple — use pcb-placement auto_decouple.py / arrange_around_ic.py to move
     each decoupling cap adjacent to its IC power pin (U3 first: +3V3/+1V1 caps; then U20/U21).
     Wrap it as a place.py "ring" step driven by floorplan so it's reproducible. Target
     decoupling_max_mm <= 2.0. Re-measure (watch overlaps stay 0); re-render.
  2. C(8+): global optimizer — simulated annealing (baseline) minimizing ratsnest with
     overlap + off-board + fixed-displacement + decoupling penalties; compare force-directed;
     keep champion. Target ratsnest <1339, plateau with ALL gates held.
  3. dfm_spacing: most are silk_overlap/silk_over_copper (cosmetic, fixable by silk regen) +
     copper_edge_clearance/clearance (placement). Separate the placement-driven clearance
     violations (must be 0) from silk (handle via a silk pass) — don't conflate. Re-measure.
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
