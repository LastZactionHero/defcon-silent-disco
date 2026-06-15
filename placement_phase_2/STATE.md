# STATE (pointer only — durable history lives in LEDGER.md + metrics.jsonl)

Phase: **C — Placement engine**
Current approach: SA + decoupling term + snap finisher. decoupling 0.09mm short → back-side caps.
Last completed: C(9) — added decoupling cost term (distinct-pin) + coordinate-descent snap to
  anneal.py; decouple.py owner map now capacity/sheet-aware. decoupling 18→2.09, overlaps 0,
  ratsnest 941. Commit pending this iter.

GATE STATUS: overlaps 0 ✓ | offboard 0 ✓ | unplaced 0 ✓ | fp_unresolved 0 ✓ | fixed_ok ✓ |
  erc 14 ✓ | ratsnest 941.6 ✓ (<<1339 reference — beat & locked) |
  decoupling_max 2.09 ✗ (need <=2.0; 0.09 short — U3 front-ring density limit → back-side caps) |
  dfm_spacing ~194 ✗ (need 0; mostly silk_overlap/silk_over_copper cosmetic + some clearance).
  → 7 of 9 gate lines pass. Remaining: decoupling (0.09mm, C10 back-side), dfm/silk (C11).

Next intended action (Phase C):
  1. C(10): BACK-SIDE decoupling to close the last 0.09mm. The U3 front ring (9 caps + bulk) is
     too dense for all ≤2.0 with 0 overlaps. Move the 2-3 tightest U3 caps (e.g. C16, C11, C7)
     to B.Cu directly under their power pins (place.py flip-to-back + the snap finisher adapted
     for B.Cu; pad-distance metric is layer-agnostic so a back cap under the pin is ≤2.0).
     Verify front overlaps drop to 0 and decoupling_max ≤2.0. Re-measure + render front & back.
  2. C(11): dfm_spacing — separate placement-driven copper/edge clearance (must be 0; nudge via
     SA edge term) from silk_overlap/silk_over_copper (cosmetic — handle with a silk-regen pass
     tool, NOT placement). Target dfm copper/edge clearance 0; track silk separately. Re-measure.
  3. When ALL Phase C gates hold and ratsnest plateaus (<2% over 5 iters), advance to Phase D
     (routing via Freerouting DSN/SES or alternative). Update STATE pointer.
  4. Render + LOOK every few iters; escalate if a metric plateaus short of gate.

LOCKED Phase C exit gates (ALL must hold; tighten only):
  overlaps==0; offboard==0; unplaced==0; fp_unresolved==0; fixed_ok==true
  (J20 top-right plug-up; J10 USB-C bottom; SW1 bottom-left; U30 left y=110 & D20 right y=110;
   J31 microSD B.Cu edge; 4× M2.5 holes corners);
  decoupling_max_mm<=2.0; dfm_spacing_violations==0;
  ratsnest_mm >= 20% better than baseline 2947 (i.e. <=2358) AND non-regressing — beat & lock
  the ~1339mm phase-1 reference; erc_errors<=14 (no regression).
  Placement produced BY TOOLS, not hand-placing parts. Then plateau (<2% over 5 iters) to finish.

Board: 88×54mm, x[100,188] y[80,134]. Staging grid currently holds 75 movable parts below y=134.
