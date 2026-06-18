# STATE (pointer only — durable history in LEDGER.md + metrics.jsonl + approaches.json)

Pass: **2** (plan-first, escape-first). Pass-1 history preserved in RETROSPECTIVE.md / NEXT_PASS_PLAN.md
and git. The board is to be FULL-RIPPED at the start of pass 2 (delete all tracks/vias, refill zones)
back to the placed + planes state; pass-2 tooling is being built now, board not yet ripped/routed.

Phase: **R0 — Setup & bake-in** (pass-2 tooling build in progress)

Tooling status (this build — what's BUILT+TESTED vs SCAFFOLDED):
  KEEP (verified good): geom_route.py, route_db.py, measure_route.py, writer_lock.py.
  BUILT + TESTED: pcb_runner.py (isolated load-mutate-save; footprint-hash + frozen guard verified),
    dead_end_detector.py (anti-thrash, escalate-as-code), escape_planner.py (R3 LINCHPIN — multi-layer,
    PROVEN via_in_pad==0 by construction on U3; residual DRC = R3 tuning target, see below),
    route_pipeline.py (restructured to the phase DAG: rip→escape→bus→bulk→fanout-LAST).
  BUILT, analysis-tested (routing parts run in R2/R4 of the loop): gpio_reassigner.py (crossing
    analysis WORKS — quantified 19/33 cross-side mismatches), bus_topology_planner.py (grouping WORKS:
    QSPI6/SD5/I2S3/SAO2/LED2 + 44 singletons; corridor-route is the R4 loop step).
  SCAFFOLDED (run on routed copper, not testable until copper exists): beautifier.py.
  KEEP-AS-IS (works; kicad_parser-extractor rebuild is an R0 refinement, not blocking): krt_bridge.py.
  DROPPED: fix_signal_vias.py (confirmed dead end — git-removed).

DE-RISKING RESULTS:
  - ESCAPE (the linchpin): KRT qfn_fanout escapes U3's 43 signal pads via-in-pad-free (0 vias, F.Cu)
    BUT 0.4mm pitch → single-layer stubs 0.283mm apart → 54 clearance errs. escape_planner's multi-layer
    (alternate F.Cu-direct / B.Cu-dogbone, collision-validated) achieves **via_in_pad==0** + cut DRC
    78→39 (residual = escape-stub clearances at 0.4mm pitch). R3 ladder finishes it: finer grid /
    more-B.Cu / GPIO remap. The KEY guarantee (no via-in-pad, by construction) is proven.
  - GPIO LEVER (R2): 19 of 33 U3 signal nets are cross-side mismatches (I2S/SAO/LED/USB/SD_CD) — the
    quantified congestion cost. Strong support for the (approval-gated) GPIO remap; could close most
    of the unrouted set at the source.

Per-phase PRIMARY metric + escalation ladder (anti-thrash):
  R3 escape  — PRIMARY: via_in_pad (==0) + escaped-pin count. Ladder: qfn_fanout-multilayer →
    manual-escape-corridor-seed → R2-gpio-remap → hand-off.
  R4 bus     — PRIMARY: bus_pitch_var (≈0). Ladder: guide-corridor-bundle → krt-bus-mode →
    manual-corridor → singleton-route-the-bus.
  R5 bulk    — PRIMARY: completion_pct. Ladder: krt-route-aesthetic-knobs → small-set-ripup →
    per-net-guide-corridor → hand-off.

Next intended action:
  1. **R0:** finish the substrate — pcb_runner used by geom_route/krt_bridge; verify qfn_fanout +
     --guide-corridor runnable on a /tmp copy; emit a baseline measure row on the (to-be) ripped board.
  2. **R1:** rework_stackup (parameterized) — real 1.6mm 4-layer, In1 GND/In2 +3V3/F+B GND pours, USB
     netclass fix (these worked in pass 1; keep).
  3. **R2 (approval-gated):** run gpio_reassigner eval → report crossing reduction → USER decides remap.
  4. **R3:** escape_planner on U3 (+ J31 if needed) → escape_plan.json, via_in_pad==0, DRC-clean.
  5. **R4→R6** per HARNESS.

LOCKED gates: see HARNESS. via_in_pad==0 (route-time/by-construction); plane fanout LAST + keepout
ring; determinism + aesthetic render gate per phase exit; placement+schematic frozen (R2 remap = only
schematic change, with sign-off); anti-thrash families machine-enforced; hand-off gate defined.
