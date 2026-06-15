# STATE (pointer only — durable history lives in LEDGER.md + metrics.jsonl)

Phase: **C — Placement engine**
Current approach: SA optimizer is CHAMPION (ratsnest 928mm). Adding decoupling term next.
Last completed: C(8) — built tools/anneal.py (zone-constrained SA); ratsnest 1580→928mm, all
  previously-passing gates held. Applied seed 1. Commit pending this iter.

GATE STATUS: overlaps 0 ✓ | offboard 0 ✓ | unplaced 0 ✓ | fp_unresolved 0 ✓ | fixed_ok ✓ |
  erc 14 ✓ | ratsnest 928 ✓ (<=2358 AND <1339 reference — beat & locked) |
  decoupling_max 18.1 ✗ (need <=2.0; SA has no decoupling term yet) |
  dfm_spacing 191 ✗ (need 0; mostly silk_overlap/silk_over_copper cosmetic + some clearance).
  → 7 of 9 gate lines pass. Remaining: decoupling (C9), dfm (silk pass + clearance).

Next intended action (Phase C):
  1. C(9): add a DECOUPLING term to anneal.py cost — w_dec * sum max(0, dist(cap_pwr_pad,
     owner_pwr_pad) − 2.0), owner map from decouple.py's load-balanced logic (import it).
     Re-run SA (warm start from current 928mm board, or from constructive). Goal: decoupling_max
     <= 2.0 while keeping overlaps 0, offboard 0, ratsnest low (<~1100 acceptable trade). Tune
     w_dec. Accept only if gates hold + decoupling improves; render + LOOK; keep champion.
  2. C(10): dfm_spacing — separate placement-driven copper/edge clearance (SA edge term / nudge)
     from silk_overlap/silk_over_copper (cosmetic). Handle silk via a silk-regen pass tool (not
     placement). Target dfm copper/edge clearance 0; track silk separately. Re-measure.
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
