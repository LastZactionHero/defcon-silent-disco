# ROUTING_SPEC — the routing system architecture (committed BEFORE implementation)

How the badge-routing system works: the engine integration, the routing pipeline, the metric
engine, the incremental model, and the aesthetic model. Build the tools to this spec; plan-before-
build means refine this doc before coding a tool, then implement.

## Architecture (mirrors placement_phase_2: authoritative geometry + instrument + optimizer)
```
  geom (pcbnew)  ──►  measure_route.py (DRC-backed metrics)  ──►  metrics.jsonl + gates
       │                                                              ▲
       ▼                                                              │
  route_db.json (incremental)  ──►  pipeline: fanout→bus→maze→cleanup→pour  ──► board
                                          │
                                          ▼  (low-level pathfinding)
                                   KiCadRoutingTools (deterministic A*, diff-pairs, planes, rip-up)
```

## ENGINE integration — KRT is the pathfinder; WE own structure, order, aesthetics, incrementality
Run KRT via `~/.local/share/defcon-badge-krt/venv/bin/python <KRT>/route.py` (and `route_diff.py`,
`route_planes.py`). Always **single-thread / fixed order** for determinism. Flag map:
- **Incremental / locality:** `--nets <names>` route only these; `--rip-existing-nets <patterns>`
  rip only these; KRT never rips pre-existing tracks → unchanged copper is preserved. This is how
  `route_db` drives net-by-net routing and re-routes only the dirty set.
- **Bus aesthetics (our seam):** `--guide-corridor[-layer/-spacing]` — our `bus_plan.py` draws a
  polyline on a User layer; selected nets follow it as waypoints (topology imposed by us, no added
  vias). Plus `--bus --bus-attraction-radius/-bonus --bus-min-nets` for KRT's own bundling.
- **Aesthetic cost-shaping:** `--turn-cost` (straighter), `--via-cost` + `--via-proximity-cost`
  (fewer/structured vias), `--track-proximity-distance/-cost` (consistent spacing),
  `--direction-preference-cost` (per-layer H/V bias).
- **Electrical:** `--impedance`/`--track-width`/`--clearance`/`--via-size`/`--via-drill`,
  `--power-nets --power-nets-widths` (+ neckdown), `--ordering mps` (or our explicit order).
- **Diff pairs:** `route_diff.py` (pose A* + Dubins, GND return vias, polarity) for USB.
- **Planes:** `route_planes.py` (Voronoi multi-net stitching, plane-resistance/IPC-2152 report,
  disconnected-region repair) for the GND/+3V3 plane fanout + stitching.

If KRT cannot produce an acceptable result for a given net even with our guide corridors and
cost-shaping, the escalation (per HARNESS) is to build the missing piece of OUR router (the bus
router is the highest-aesthetic-value bespoke piece; a cost-shaped maze for leftovers is next) —
KRT is the baseline engine, not a hard dependency.

## PIPELINE (deterministic, PVISA — every stage emits a snapshot; gate-and-revert via git)
0. **PLANE FANOUT** (`route_planes.py` driver): for every GND (89) and +3V3 (47) pad, drop a via
   to its plane (thermal-relief/direct). Removes ~136 connections from the 2D problem; tidy via
   dots, not wandering copper. Record stitching vias for the D5 return-path metric.
1. **BUS EXTRACTION** (`bus_plan.py`): group the ~62 signal nets into declared buses from their
   names + endpoints: QSPI 6 (SCLK/SD0..3/SS, U3↔U2), SD/SPI0 4 (U3↔J31), I2S 3 (GP6/7/8, U3↔U20),
   SPI1/LED 2 + daisy-chain (U3↔LED20→21→22→23), I2C/SAO 2 (U3↔J30), USB diff 2, audio chain; plus
   ~30 loose singletons. Emit a `bus_plan.json` (per-bus trunk axis + member ordering) — the
   routing analog of placement's frozen `structured` groups.
2. **BUS ROUTE** (criticality order: QSPI, crystal, USB first, on empty copper): for each bus,
   compute pin-escape order at both endpoints, untwist (match orderings by perpendicular
   projection), choose a trunk centerline, emit a guide corridor, route members as constant-pitch
   parallel bundles via KRT. USB as a length-matched constant-gap diff pair (`route_diff.py`).
   Freeze each routed bus (record in route_db) as obstacle for the next.
3. **MAZE / SINGLETONS** (`krt_route.py` with aesthetic flags, fixed net order): route the loose
   nets with strong via/turn penalties, track-proximity spacing, channel preference (empty B.Cu).
4. **CLEANUP / BEAUTIFY** (`beautify.py`): pull-tight/straighten, via-minimize, push-to-grid
   (0.05mm) + 45°-quantize, bus-pitch normalize, teardrops + corner fillets (KiCad built-ins).
   Each pass idempotent and DRC-rechecked; revert any pass that breaks a gate.
5. **POUR & STITCH**: refill all zones; place structured GND stitching vias near fast-edge clusters
   (USB, crystal, I2S, LED clock) and along the edge. Final full-gate + determinism + render.

## METRIC ENGINE (`measure_route.py`) — reuse measure.py's DRC plumbing; ADD routing metrics
Reuse AS-IS: `run_kicad_cli`/`collect_violations`/`sev`/`_item_ref`, the `--append`/row harness,
`POWER_RE`/`GROUND`, `geom.load_pcb`/`board_outline`, the erc carry-over.
- `completion_pct` = 100*(1 - unconnected_now/unconnected_baseline). PRIMARY. Baseline = the
  unrouted board's `GetUnconnectedCount(False)` measured AFTER the D1 zone-fill (so GND/+3V3 plane
  pads don't inflate it). Freeze the baseline as a constant once D1 fills zones.
- `unconnected` = pcbnew `GetConnectivity().GetUnconnectedCount(False)`; `unconnected_divergence`
  = |that − len(drc unconnected_items)| (Resolution-2 guard).
- `shorts` = DRC `shorting_items` count (+ pcbnew net-cluster cross-check). HARD 0.
- `drc_errors` + `drc_by_type` (Counter over error-sev types): clearance/track_dangling/
  via_dangling/copper_edge_clearance/track_width/annular_width/hole_clearance.
- `track_count`, `via_count`, `track_len_mm`, `track_len_by_layer` (inner planes should show ~0
  signal track), `layer_balance`.
- `usb_diff_paired` (both USB nets resolve to USB_DIFF_90) + `usb_diff_skew_mm` (|len(DP)−len(DM)|).
- `power_min_width_ok` (every power-net segment ≥0.30mm), `acute_angles`, `off_axis_segments`
  (segments not in {0,45,90,135}°), `bus_pitch_var` (variance of adjacent-trace pitch within a bus).
- `zones_filled_ok`, `determinism_ok` (route-twice identical), `erc_errors`.
Locked thresholds live as module-top constants (POWER_MIN_WIDTH_MM=0.30, USB_SKEW_MAX_MM=2.5,
VIA_BUDGET=<set in D3>) — changing a DEFINITION needs a REVIEW (Resolution 6).

## INCREMENTAL MODEL (`route_db.py`) — built in D0, used whenever copper is laid
- **Stable signature** `net_sig = hash(sorted pin_set)`, pin_set = sorted "REFDES-PADNUM" on the
  net. NOT the net name (KiCad auto-names churn). A part swap that keeps a net's pads → same sig →
  net unchanged → copper replayed.
- **Record** per net: `{net_sig, net_name, pin_set, pad_xy(quantized nm), input_hash(pins+xy+
  netclass+rules), route:[segments/vias], router_version}`.
- **Diff** the live net set vs route_db: NEW (route it) / CHANGED (input_hash differs → rip+reroute)
  / DELETED (rip its copper, drop record) / UNCHANGED (input_hash equal → REPLAY stored route
  verbatim, never re-search).
- **Stamp** the board: clear routing, emit UNCHANGED from DB + freshly-routed CHANGED/NEW, in the
  stable net order. **Stable order** key = (netclass_rank, −pin_count, round(bbox_half_perimeter),
  net_sig) — all intrinsic, so adding/removing a net doesn't reshuffle survivors.
- **Locality** on re-run: freeze UNCHANGED routes as fixed obstacles; route only the dirty set
  walking around them; only on failure expand a bounded rip-up bucket of the specific blockers.
- **Determinism gate** = route the whole board twice from clean → assert identical route_db.

## AESTHETIC MODEL — what "hand-designed" means here, made measurable
Visual tells of autorouting, each with a metric + a fix:
- excess/scattered vias → `via_count` budget + via-minimize pass.
- staircase/off-axis jogs → `off_axis_segments==0` + push-to-grid/45-quantize + `bend`/turn penalty.
- ragged bus spacing → `bus_pitch_var`≈0 + bus-pitch-normalize + constant-pitch bundle routing.
- sharp 90° corners → corner count + teardrops/fillets.
- detours on random nets → criticality net order (important nets straight on empty copper).
Aesthetics is partly subjective → the render-in-the-loop gate (pcb-views F.Cu/B.Cu/3D, look at it)
is mandatory at every phase exit; metrics catch regressions, the render catches the rest.
