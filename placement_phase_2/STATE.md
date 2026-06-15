# STATE (pointer only — durable history lives in LEDGER.md + metrics.jsonl)

Phase: **C — Placement engine**
Current approach: placement essentially done (8/9 gates). Only dfm/silk remains.
Last completed: C(10) — backside_decouple.py moved C16 + 3 bulk caps to B.Cu under their pins;
  decoupling 2.09→1.72 (GATE MET), overlaps 0, ratsnest 941, all placement gates pass. Commit pending.

GATE STATUS: overlaps 0 ✓ | offboard 0 ✓ | unplaced 0 ✓ | fp_unresolved 0 ✓ | fixed_ok ✓ |
  erc 14 ✓ | ratsnest 940.95 ✓ (<<1339 reference — beat & locked) | decoupling_max 1.72 ✓ |
  dfm_spacing ~198 ✗ (need 0; mostly silk_overlap/silk_over_copper cosmetic + some clearance).
  → 8 of 9 gate lines PASS. Only dfm_spacing remains.

Next intended action (Phase C):
  1. C(11): dfm_spacing — run kicad-cli DRC, BREAK DOWN the ~198 by type. The copper-spacing set
     (clearance/copper_edge_clearance/hole_clearance) is what the gate counts; many are likely
     silk (silk_overlap/silk_over_copper/silk_edge) which measure.py already EXCLUDES from
     dfm_spacing — so recheck what dfm_spacing actually is now (=198? verify the type breakdown).
     If real copper/edge-clearance violations exist, nudge the offending parts (tool/anneal edge
     term) to clear them. If they are unrouted-net artifacts, note that DRC clearance on an
     unrouted board is dominated by pad-to-pad of unconnected nets — decide the honest gate
     reading (placement clearance vs routing). Silk is cosmetic → optional silk-declutter tool.
  2. When ALL Phase C gates hold and ratsnest plateaus (<2% over 5 iters — already stable ~940),
     advance STATE to Phase D (routing via Freerouting DSN/SES or alternative).
  3. Render + LOOK; escalate if a metric plateaus short of gate.

LOCKED Phase C exit gates (ALL must hold; tighten only):
  overlaps==0; offboard==0; unplaced==0; fp_unresolved==0; fixed_ok==true
  (J20 top-right plug-up; J10 USB-C bottom; SW1 bottom-left; U30 left y=110 & D20 right y=110;
   J31 microSD B.Cu edge; 4× M2.5 holes corners);
  decoupling_max_mm<=2.0; dfm_spacing_violations==0;
  ratsnest_mm >= 20% better than baseline 2947 (i.e. <=2358) AND non-regressing — beat & lock
  the ~1339mm phase-1 reference; erc_errors<=14 (no regression).
  Placement produced BY TOOLS, not hand-placing parts. Then plateau (<2% over 5 iters) to finish.

Board: 88×54mm, x[100,188] y[80,134]. Staging grid currently holds 75 movable parts below y=134.
