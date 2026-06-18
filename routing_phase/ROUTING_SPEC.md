# ROUTING_SPEC — Pass-2 architecture (escape-first, KRT-full-toolbox)

How the pass-2 system works. The big change vs pass 1: PLAN before ROUTE, and invoke KRT's
existing escape/bus/aesthetic capabilities instead of rebuilding them.

## Architecture
```
  geom_route (pcbnew authoritative copper) ──► measure_route (DRC-backed metrics) ──► gates
       │              ▲
       ▼              │
  route_db (incremental, stable pad-set signature)
       │
  PLAN (Workflow, run once) ───────────────────────────────► EXECUTE (loop)
    R2 gpio_reassigner  (crossing-min, schematic, approval)     R5 bulk singleton route + beautify
    R3 escape_planner   (qfn_fanout + B.Cu dogbones)            R6 plane fanout LAST + pour + verify
    R4 bus_topology_planner (chip_boundary/bus_detection)
       └─ emit escape_plan.json / bus_plan.json / gpio_remap.json (frozen artifacts)
                                          │
                                          ▼ (KRT = solver only; pcbnew = sole writer)
                          krt_bridge: KRT solves → extract (KRT kicad_parser) → re-apply via pcbnew
```

## KRT full-toolbox integration map (the pass-1 "missing tools" that already exist)
Run KRT via the venv; reach output ONLY through `krt_bridge` (KRT writes net NAMES, KiCad 10 needs
CODES). All KRT runs single-thread/deterministic.
- **Escape (R3):** `qfn_fanout.py --component U3 --layer F.Cu --width 0.15 --clearance 0.15 --nets
  "*" "!GND" "!+3V3" "!+1V1"` → 0-via on-layer escapes (PROVEN). escape_planner adds the B.Cu dogbone
  for the alternate pads (ESCAPE_SPEC).
- **Bus/topology (R4):** `bus_detection.py` (group nets into buses), `chip_boundary.py` (perimeter
  unroll → crossing-minimal order: two nets cross iff source/target orderings invert), and
  `route.py --bus --guide-corridor --guide-corridor-layer/-spacing` → constant-pitch bundles.
- **Aesthetics (R5):** the Rust `grid_router` knobs — `--turn-cost` (straighter), `--via-cost`/
  `--via-proximity-cost` (fewer/structured vias), `--track-proximity-*` (consistent spacing),
  cross-layer track attraction (stack traces on adjacent layers). Pass 1 ran defaults.
- **GPIO remap (R2):** `chip_boundary.py` to score crossings; Hungarian assignment (as in KRT
  `target_swap.py`); write back via KRT `schematic_updater.py` + `--swappable-nets`/`--schematic-dir`.
- **Bulk (R5):** `route.py` with the aesthetic knobs + `--rip-existing-nets PATTERN` (SMALL sets only;
  global rip-up is pathologically slow on this board). At 0.4mm-pitch QFN-local nets use
  `--grid-step 0.05 --clearance 0.05`.
- Do NOT use `route_planes.py`/`route.py` to place vias on pads (the pass-1 via-in-pad source) — and
  do NOT use KRT's writer.

## Pipeline (route_pipeline.py = a phase DAG, not the old flat chain)
R0 setup → R1 stackup → R2 gpio (opt) → **R3 escape** → **R4 bus** → R5 bulk singletons → R6 plane
fanout LAST + pour. Each stage: pcb_runner-isolated, records into route_db, independently re-runnable.
The old order (plane-fanout-then-bulk, no escape, bus lumped in bulk) is the structural flaw being
fixed — plane fanout MOVED TO LAST is the single most important change.

## Metric engine (measure_route.py — KEPT; fill the existing None placeholders)
Already emits: completion_pct (vs frozen baseline.json), unconnected + divergence guard, shorts,
drc_errors + drc_by_type, track/via counts + per-layer length, **via_in_pad** (HitTest), usb skew/
paired, acute_angles, off_axis_segments, zones_filled_ok. NEW tools fill the placeholders:
bus_pitch_var (R4), determinism_ok (route-twice). Per-phase PRIMARY metric declared in STATE.md
(R3: via_in_pad + escaped-pin count; R4: bus_pitch_var; R5: completion_pct).

## Incremental model (route_db.py — KEPT)
Nets keyed by stable pad-set signature (sorted REFDES-PADNUM, not the churning net name). A GPIO
remap (R2) changes the signature only for moved nets → only those re-escape/re-route. Determinism
gate = route-twice → identical fingerprint.

## Determinism + aesthetics are first-class
Route-twice gate wherever copper exists. Because escape (R3) and buses (R4) are PLANNED before bulk,
the structured-via + constant-pitch look is baked in — there is no "aesthetic pass at the end" to skip.
