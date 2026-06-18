# MISSION — Self-Directed PCB Routing System (Phase D)

## What you are building
You are an autonomous engineering loop. Over many self-scheduled iterations, with no human
intervention, you will **design, implement, validate, and refine your OWN reusable PCB
*routing* system** — a bus-aware, aesthetic, deterministic, incrementally-re-runnable router —
and use it to route the DEF CON silent-disco badge from its frozen, user-approved placement.

The board is the test case. **The routing system is the deliverable.** This is the direct
sequel to `placement_phase_2/`, which built its own floor-planner + simulated-annealing placer
behind an authoritative pcbnew geometry layer. You will mirror that architecture for routing.

## The four goals that define "good" here (optimize for ALL of them, not just "100% routed")
The user chose to build this rather than click the Freerouting button. That choice IS the spec:

1. **Aesthetic — it must look HAND-DESIGNED, not autorouted.** Clean constant-pitch buses,
   straight runs, minimal & structured vias, tidy 45°s, symmetric diff pairs. The user
   explicitly rejects the Freerouting "machine filled the gaps" look. This is a first-class,
   gated goal — judged by aesthetic metrics AND by rendering the board and LOOKING at it.
2. **Deterministic** — same inputs → byte-identical copper. No threads/seeds/wall-clock
   deciding the result. Determinism is an un-loosenable invariant (the routing analog of the
   placement loop's `overlaps_divergence==0`): route twice, assert identical, or it's a bug.
3. **Re-runnable / incremental** — when a part goes out of stock and gets swapped (schematic +
   placement re-sync), re-routing must touch ONLY the changed nets and replay everything else
   byte-for-byte. Cost proportional to the change, not the board. Architect for this from day 1.
4. **Ours** — a system we fully control and can explain, built on an authoritative geometry
   layer, not a black box.

## The engine decision (made 2026-06-17 after a deep fork-vs-build study — see ENGINE in ROUTING_SPEC.md)
- **Freerouting: REJECTED.** ~110 kloc of 20-yr-old Java; its ugliness is *structural* (per-net
  greedy, free-space rooms not a pitch grid, single-corner staircasing, a local-only optimizer
  with no bus concept); needs Java 25; non-deterministic by default; **no incremental mode**.
  Forking it buys the one engine property we don't want. Not used, not installed.
- **KiCadRoutingTools (KRT) is the FOUNDATION ENGINE — we build ON it, not reinvent it.**
  MIT, KiCad-10-native (writes `.kicad_pcb` directly, no DSN/SES round-trip), **deterministic**
  (integer cost, counter tie-break, no RNG), with mature pose-based **diff-pair** routing
  (Dubins), **Voronoi plane-stitching**, and rip-up that **never touches pre-existing tracks**
  (our incremental-locality primitive). Pinned at commit in `KRT_PINNED_COMMIT.txt`; runnable
  via the venv (see `setup.sh`). Its weakness is *default aesthetics* (griddy/autorouted) — which
  is exactly the part WE own.
- **What WE build (where goals 1/3/4 live):** the bus planner (route QSPI/I2S/SPI/USB as
  constant-pitch bundles via KRT's `--guide-corridor` seam) + criticality net ordering +
  aesthetic cost-shaping (`--turn-cost`/`--via-cost`/`--track-proximity-cost`) + a beautification
  pass + the incremental `route_db` (stable-pin-set-signature keyed) + the authoritative
  geometry/metric/gate harness. KRT is the low-level pathfinder; the design judgment is ours.

## Operating philosophy (non-negotiable — inherited from placement_phase_2, they are the lesson)
1. **Tools over edits.** Never hand-hack the `.kicad_pcb` to fix a symptom. Build/improve a tool.
2. **Plan before you build.** Every tool gets a short committed spec before implementation.
3. **Measure everything.** Append one row to `metrics.jsonl` every iteration. Never fly blind.
4. **Detect thrashing and escalate.** A plateaued/oscillating metric FORBIDS repeating the move.
5. **Authoritative geometry + single writer.** All board reads/writes via pcbnew (extend
   `placement_phase_2/tools/geom.py`), guarded by `writer_lock.py`. Never text-edit s-exprs for
   geometry. A router writes TRACKS and VIAS — it owes the same discipline (see HARNESS Rule 1).
6. **The quality bar is LOCKED.** You may make gates stricter. You may NEVER loosen them, redefine
   a metric's meaning, or delete a capability to declare yourself done.
7. **Placement is FROZEN.** Routing adds copper only — never move a footprint. (Exception: the D1
   stackup/zone rework, which changes the layer stack + zones, NOT footprint positions.)

## Phases (in order; each has a locked exit gate in HARNESS.md)
- **D0 — Setup & instrument.** Build `measure_route.py` (the routing metric engine) + extend geom
  for track/via read/write/rip-up + the `route_db` skeleton. Baseline row (0% routed). KRT env
  verified. *(Building the instrument IS the D0 work; the baseline row is its output.)*
- **D1 — Stackup & rules rework.** Execute `STACKUP_SPEC.md`: real JLC 1.6mm 4-layer stack, In1
  solid GND / In2 +3V3-dominant mixed, F.Cu/B.Cu GND pours; delete the ported artifact zones;
  fix board thickness 1.0→1.6mm; fix the USB_DIFF_90 netclass (pattern + 0.8→0.17mm width). DRC
  clean on the unrouted board.
- **D2 — Plane fanout + critical pre-route.** Via-stitch every GND/+3V3 pad to its plane; then
  bus-route + LOCK the critical nets (USB diff pair, crystal, QSPI, I2S) first on empty copper.
- **D3 — Bus + bulk route.** Bus planner → guide corridors → KRT routes buses as bundles, then
  singletons in criticality order, to 100% completion. Incremental `route_db` records every net.
- **D4 — Cleanup & DRC.** Beautification passes (pull-tight, via-min, push-to-grid, teardrops,
  corner smoothing); DRC → 0; aesthetic metrics within budget.
- **D5 — Pour, stitch & verify.** Refill all zones, structured GND stitching vias near fast
  edges; full-gate re-check + determinism gate + human-eyes render.

## What "satisfied" means
Done = all locked Phase-D gates pass (100% routed, 0 DRC, 0 shorts, USB pair correct, aesthetic
budget met, zones filled+stitched), the **determinism gate** passes (route twice → identical),
the **incremental path** is demonstrated (a synthetic 1-net change re-routes only that net), a
human-eyes render confirms it looks hand-designed, every tool is documented as/in a skill, and
`LEDGER.md` has a final summary. If you exhaust every approach and cannot meet a gate, write a
`BLOCKER:` entry with everything tried and keep attempting the most *different* method — never
lower the gate, never quit.
