# STATE (pointer only — durable history lives in LEDGER.md + metrics.jsonl)

Phase: **C — Placement engine**
Current approach: ESCALATED to global SA optimizer (greedy decouple+spread plateaus).
Last completed: C(7) — built decouple.py (load-balanced cap→owner) + ANNEAL_SPEC.md. Greedy
  decouple+spread got decoupling 26→9.7 but stalls + adds overlaps; reverted to clean C(6)
  state (0 overlaps, 1580mm, decoupling 26). Board unchanged. Commit pending this iter.

GATE STATUS: overlaps 0 ✓ | offboard 0 ✓ | unplaced 0 ✓ | fp_unresolved 0 ✓ | fixed_ok ✓ |
  erc 14 ✓ (<=14) | ratsnest 1580 (<=2358 ✓; target <1339) | decoupling_max 26.3 ✗ (need <=2.0)
  | dfm_spacing 190 ✗ (need 0; mostly silk_overlap + copper/edge clearance, unrouted board).

Next intended action (Phase C):
  1. C(8): implement tools/anneal.py per ANNEAL_SPEC.md — SA over (ratsnest + overlap +
     offboard + edge + decoupling) cost, fixed parts frozen, warm-started from the current
     constructive placement (optionally decouple.py-seeded). numpy. --seed for determinism.
     Accept the result only if every passing gate still holds AND objective improved, else
     revert. Render + LOOK. Keep champion vs constructive (1580mm).
  2. C(9+): tune SA weights/schedule + multiple seeds; target ratsnest <1339, decoupling<=2.0,
     overlaps 0, offboard 0, all held. If SA underperforms, challenger = force-directed/analytical.
  3. dfm_spacing: separate placement-driven copper/edge clearance (must be 0, SA edge term
     handles) from silk_overlap/silk_over_copper (cosmetic — handle via a silk-regen pass, not
     placement). Don't conflate. Re-measure.
  4. Render + LOOK every few iters; escalate (switch method / global re-place) if a metric
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
