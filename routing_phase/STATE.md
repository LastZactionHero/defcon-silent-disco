# STATE (pointer only — durable history in LEDGER.md + metrics.jsonl + approaches.json)

Pass: **2** (plan-first, escape-first). Pass-1 history preserved in RETROSPECTIVE.md / NEXT_PASS_PLAN.md
and git. R0 (2026-06-18): board FULL-RIPPED back to placed+planes (0 tracks/arcs/vias; 5 zones refilled;
2 `(vias not_allowed)` keepout areas are rule-areas, not copper). HEAD still holds the pass-1 75.5%
routed board as the archival reference — pass-2 clean base lives uncommitted in the working tree until
this R0 commit.

Phase: **R2 — GPIO re-assignment eval (approval-gated)** — R0 DONE + R1 carried-over-verified.

R0 RESULTS (2026-06-18, clean base):
  - Env verified: KRT venv (numpy 2.4.6/scipy 1.17.1/shapely 2.1.2), host pcbnew 10.0.2, qfn_fanout
    end-to-end on /tmp (86 tracks, 43 stubs×2, "No endpoint collisions", reproduced the 0.4mm-pitch
    residual warning), route.py --guide-corridor end-to-end on /tmp (8 waypoints, layer-costs applied).
  - Clean base: rip+refill via route_pipeline (pcb_runner-isolated); footprint hash dcb44305490d
    UNCHANGED, frozen .kicad_sch/.kicad_pro git-clean.
  - Baseline measure row (R0(0)): completion 2.72%, unconnected 143 (baseline 147, divergence 0),
    via_in_pad 0, drc 0, shorts 0, usb_diff_paired TRUE, zones_filled_ok TRUE, n_footprints 83.
  - R1 (stackup/netclass) carried over from D1 through the rip — 1.6mm 4-layer, In1 GND/In2 +3V3,
    F/B GND pours filled, USB_DIFF_90 fixed. Re-verified clean; no new R1 work needed.
  - KRT invocation note: route.py takes OUTPUT + net-patterns as POSITIONALS (not --output/--nets);
    qfn_fanout DOES take --output. route.py default clearance 0.25mm. Net names are hierarchical
    (e.g. /Audio/I2S_BCK) — R4 corridor calls must use the real net names, not bare bus labels.

R2 EVAL RESULT (2026-06-18, read-only, frozen pin map): U3 = 33 signal nets, **19 cross-side**.
  - 15 firmware-MOVABLE (PIO/any-GPIO or instance-flexible): I2S_BCK/DIN/LRCK (move as a 3-contiguous
    block — PIO side-set), BTN_SYNC, SAO_GPIO1/2, SAO_SCL/SDA, IR_RX, IR_TX, LED_DAT, LED_SCK, ~CHRG,
    SD_CD, VBAT_SENSE (within ADC bank GP26-29).
  - 4 FIXED-but-benign (dedicated silicon pins): QSPI_SS (adjacent to flash), RUN (pullup stub),
    USB_DM/DP (dedicated USB pins; pass 1 routed USB 4/4 fine).
  - Remap could take 19 -> ~4, residual all non-problematic. AWAITING USER DECISION on the remap fork
    (schematic+firmware edit, approval-gated). gpio_reassigner's pinmux-legal SOLVER is still TODO —
    a trustworthy concrete proposal needs it built (RP2040 QFN pad->GPIO map + function table +
    I2S-contiguity/ADC-bank constraints).

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
  1. ~~**R0:** substrate + baseline~~ DONE (see R0 RESULTS).
  2. ~~**R1:** stackup/netclass~~ carried-over-verified from D1.
  3. **R2 (approval-gated) — AWAITING USER DECISION:** crossing eval done (19 cross-side, 15 movable).
     Fork presented to user: (a) build pinmux-legal solver -> concrete remap proposal -> apply (schematic
     edit, needs final sign-off); (b) route the frozen map as-is, lean on the R3 multi-layer escape
     ladder. The remap APPLY is the only schematic change allowed and is the one hard pause in the run.
  4. **R3:** escape_planner on U3 (+ J31 if needed) → escape_plan.json, via_in_pad==0, DRC-clean.
     Run on whichever pin map R2 settles on.
  5. **R4→R6** per HARNESS.

LOCKED gates: see HARNESS. via_in_pad==0 (route-time/by-construction); plane fanout LAST + keepout
ring; determinism + aesthetic render gate per phase exit; placement+schematic frozen (R2 remap = only
schematic change, with sign-off); anti-thrash families machine-enforced; hand-off gate defined.
