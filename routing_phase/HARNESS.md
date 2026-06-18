# HARNESS — autonomous routing loop (operational core)

You are the iteration engine. Every wake-up you run ONE iteration of the procedure below,
commit, log, and schedule the next wake-up. Read `MISSION.md` for the why; this is the how.
The rules are tuned to prevent the prior runs' failures (see placement_phase_2 — same lessons).

cwd is the repo root `/home/zach/dev/defcon_badge`. Mission-control lives in `routing_phase/`;
the board is `defcon_badge/defcon_badge.kicad_pcb` (project `.kicad_pro`, schematic `.kicad_sch`).

## LOCKED resolutions (do not route around these)
1. **Authoritative geometry + single writer, now for COPPER.** All board reads/writes go through
   pcbnew via `placement_phase_2/tools/geom.py` (extended in D0 with `load_tracks/load_vias/
   add_track/add_via/delete_routing`), never by regex/text-editing s-expressions. Every write
   calls `writer_lock.assert_writable()` FIRST (refuses while KiCad holds the board open). A
   router that adds tracks/vias obeys this exactly: create `pcbnew.PCB_TRACK`/`PCB_VIA`, set
   layer/net(by `FindNet(name)`)/width/start/end via the API, `b.Add()`, refill zones, `SaveBoard`.
   KRT writes `.kicad_pcb` natively — when KRT writes, the loop still owns the file: assert
   writable before invoking KRT, and treat KRT's output as a proposed write to be measured/gated.
2. **Completion truth = DRC, with a divergence guard.** The primary metric `unconnected` comes
   from pcbnew `GetConnectivity().GetUnconnectedCount(False)` AND is cross-checked against
   kicad-cli DRC `unconnected_items`. `measure_route.py` emits `unconnected_divergence`; if it is
   non-zero the cheap metric is lying — STOP and trust DRC (the routing analog of Resolution 1).
3. **DETERMINISM is an un-loosenable invariant.** A route step is only trusted if re-running it
   from the same input reproduces byte-identical copper. The determinism gate (route twice into
   two temp boards, compare sorted (net,layer,x0,y0,x1,y1,width)+via tuples) is a hard Phase-D
   gate. A non-zero diff is a router bug — fix the router, never the gate. Force KRT single-thread
   / fixed order; never introduce time/PID/RNG-seeded behavior.
4. **AESTHETIC gate, every phase exit.** "Render and LOOK" is enforced, not advice — autorouted
   spaghetti can be DRC-clean. At every phase exit run the aesthetic metrics (via_count,
   off_axis_segments==0, bus_pitch_variance, corner_count) AND render F.Cu+B.Cu+3D (pcb-views) and
   actually look. A phase does not exit while it looks machine-generated.
5. **Incremental from the start (route_db).** Every routed net is recorded in `route_db.json`
   keyed by its STABLE signature = hash(sorted pin-set of "REFDES-PADNUM"), NOT the (churning)
   net name. Unchanged nets are REPLAYED, never re-searched. This is built in D0 and used every
   time copper is laid, so re-runnability is structural, not bolted on later.
6. **Lock definitions, not just thresholds.** You may TIGHTEN a gate. You may not redefine what a
   metric means, nor delete a capability that broke, to pass. Either is a `REVIEW:` entry + human
   adjudication; keep complying meanwhile.

## Per-wake-up procedure (do these in order, every time)
0. **Single-writer preflight:** run `python3 placement_phase_2/tools/writer_lock.py
   defcon_badge/defcon_badge.kicad_pcb`. If LOCKED, KiCad is open — do read-only work
   (measure/render/plan) or reschedule; do not write this iteration.
1. **Read (every iteration):** `routing_phase/MISSION.md`, this file, `routing_phase/
   routing_rules.md`, `badge_hw_design.md`. Consult `routing_phase/ROUTING_SPEC.md` +
   `STACKUP_SPEC.md` and `placement_phase_2/placement_research.md` (Autorouters section) on demand.
2. **Load durable memory:** tail of `routing_phase/LEDGER.md` + the ENTIRE
   `routing_phase/metrics.jsonl` (small — read all of it; it is your anti-thrash trend signal).
   Read `routing_phase/STATE.md` for the phase pointer + last intended action.
3. **Identify current phase** and its exit gate (below).
4. **Measure:** run `python3 routing_phase/tools/measure_route.py defcon_badge/defcon_badge.kicad_pcb
   --phase D? --iter N --append routing_phase/metrics.jsonl`; confirm exactly one row landed.
   Check `unconnected_divergence` (Resolution 2) — if non-zero, trust DRC and fix the metric.
   *(In D0, building `measure_route.py` IS the work and the baseline row is its output.)*
   **CAUTION (learned 2026-06-17):** some `kicad-cli sch erc` / BOM-export invocations REWRITE the
   approved `.kicad_sch`/`.kicad_pro` (lib-symbol re-serialization, BOM-field injection). The
   schematic is FROZEN. Run ERC on a `/tmp` copy of the project (sch+pro+pcb together), or assert
   `git diff --quiet defcon_badge/*.kicad_sch defcon_badge/defcon_badge.kicad_pro` after measuring
   and revert any stray rewrite. Never let a measure mutate the frozen schematic. (DRC on the .pcb
   needs the sibling .kicad_pro present — copy it alongside any /tmp board copy.)
5. **Convergence check** over the last K=5 rows of the phase's primary metric:
   - **Improving** (>2% relative gain on completion, or the active sub-metric): continue with the
     single highest-leverage action.
   - **Plateaued/oscillating AND gate met:** advance phase (update STATE pointer; commit a
     phase-transition entry).
   - **Plateaued/oscillating AND gate NOT met:** **ESCALATE.** You may not repeat the stalled
     move. Switch approach (different KRT flags / net order / bus strategy / build the missing
     piece of our own router), or write a `BLOCKER:` and implement the most *different* method.
6. **Choose the single highest-leverage action.** Planning/tool-building is FIRST-CLASS — an
   iteration need not lay copper (writing a spec or a tool counts).
7. **Execute via tools.** Prefer building/improving a tool over editing files. All board writes
   via geom/pcbnew or KRT, guarded by the writer lock. After any copper write, update `route_db`.
7b. **Phase-exit gate (MANDATORY at every phase exit and any iteration that changed copper):**
   run the aesthetic metrics + the determinism gate (where copper exists) AND render+LOOK
   (pcb-views F.Cu/B.Cu/3D). A phase does not exit while a gate is red or the render shows junk.
8. **Commit + log:** message `D?(N): <one-line summary>`. Append one `LEDGER.md` line
   (action | rationale | result | Δmetric). Confirm this iteration's `metrics.jsonl` row exists.
9. **Schedule next wake-up:** `ScheduleWakeup` with `routing_phase/PROMPT.md` contents verbatim.
   `delaySeconds`: 90–270 in active build/route mode (cache warm); 1200–1800 when launching a
   long route/experiment so you wake to results. Stop only when MISSION "satisfied" holds, or
   after a ~150-iteration sanity cap (write a wrap-up entry and stop).

## Durable memory (append-only — NEVER rotate/truncate; all under `routing_phase/`)
- **`metrics.jsonl`** — one JSON row per iteration. Required keys: `ts, phase, iter, approach,
  commit` + every metric: `completion_pct, unconnected, unconnected_divergence, shorts,
  drc_errors, drc_by_type, track_count, via_count, via_in_pad, track_len_mm, track_len_by_layer,
  usb_diff_paired, usb_diff_skew_mm, power_min_width_ok, acute_angles, off_axis_segments,
  bus_pitch_var, zones_filled_ok, determinism_ok, erc_errors`. Never skip or delete a row.
- **`LEDGER.md`** — append-only decision log: `[ISO-date] D?(N) — action | rationale | result |
  Δmetric`. Prefixes: `BLOCKER:` `REVIEW:` `CHAMPION:`.
- **`STATE.md`** — a small pointer only (phase, approach, next action, this phase's exit gate).
- **`route_db.json`** — per-net routed geometry keyed by stable signature (Resolution 5).

## Phase exit gates

### D0 — Setup & instrument (exit when all true)
- `routing_phase/tools/measure_route.py` exists, runs, emits the full metric schema, appends a
  baseline row (completion_pct≈0 on the unrouted board, unconnected=baseline, determinism_ok n/a).
- geom extended with track/via read + `add_track/add_via/delete_routing` (writer-lock-guarded);
  `route_db.json` skeleton exists (load/save, net-signature, diff NEW/CHANGED/DELETED/UNCHANGED).
- KRT verified runnable (`setup.sh` reproduces the env; a trivial KRT invocation works).

### D1 — Stackup & rules rework (exit when all true)
- Stackup reworked per `STACKUP_SPEC.md`: thickness 1.6mm; real dielectric block; In1 solid GND
  plane; In2 +3V3-dominant pour (+ optional GND); F.Cu & B.Cu GND pours; the 3 ported artifact
  zones deleted and recreated. Zones fill clean.
- USB_DIFF_90 netclass fixed: pattern matches the real nets (`/MCU_Core/USB_DP`, `USB_DM`, and the
  connector-side `Net-(U3-USB_DP/DM)`); `diff_pair_width` 0.8→0.17mm, gap 0.13–0.15mm.
- `kicad-cli pcb drc` (project file present) on the unrouted board is clean of NEW stackup/zone
  errors (pre-existing silk/courtyard/lib types are out of scope, like placement's dfm scoping).
- Baseline measure row written; `unconnected_divergence==0`.

### D2 — Plane fanout + critical pre-route (exit when all true)
- Every GND and +3V3 pad stitched to its plane with a via (deterministic fanout); planes connected.
- Critical nets routed AND locked: USB diff pair (coupled, length-matched, over solid In1 GND, no
  plane split under it), crystal XIN/XOUT loop (tight, guard), QSPI flash bus, I2S GP6/7/8 bus —
  each as clean structured copper, recorded in `route_db`. `completion_pct` rising; `shorts==0`;
  no NEW drc_errors on the routed subset; `usb_diff_paired==true`, `usb_diff_skew_mm<=2.5`.

### D3 — Bus + bulk route (exit when all true)
- `completion_pct==100` (`unconnected==0`, `unconnected_divergence==0`) OR a documented `BLOCKER:`
  listing the unrouted nets and every approach tried. `shorts==0`. `via_in_pad==0`. Critical
  pre-routes from D2 preserved (route_db replayed them, not re-searched).

### D4 — Cleanup & DRC (exit when all true)
- `drc_errors==0` (routing types: clearance/track_dangling/via_dangling/copper_edge_clearance/
  track_width/annular_width/hole_clearance), `shorts==0`, `acute_angles==0`,
  `off_axis_segments==0`, `power_min_width_ok` (power nets ≥0.30mm), `completion_pct==100`,
  `via_in_pad==0` (USER DIRECTIVE — see below), `via_count` within the aesthetic budget,
  `bus_pitch_var` near 0. Track length not regressed.

**`via_in_pad==0` — USER DIRECTIVE (locked, 2026-06-17): NO via-in-pad.** Vias may not land on
pad copper (needs filled/plated vias = cost; pointless at this density). A proper fanout/stitch via
is OFFSET from the pad with a short stub. Enforce on the KRT plane fanout with
`--same-net-pad-clearance 0.2` (default −1 allows via-in-pad; ≥0.2 forces offset vias + stubs →
`via_in_pad` 95→0, verified). Gated from D2 onward (any iteration that places vias). This is a hard
gate; do not weaken it.

### D5 — Pour, stitch & verify (exit when all true)
- All zones filled & connected (`zones_filled_ok`); structured GND stitching vias near each
  fast-edge cluster (USB, crystal, I2S, LED clock). A FULL re-run of all hard gates still passes
  AFTER fill. **`determinism_ok==true`** (route-twice identical). A synthetic 1-net incremental
  re-route touches only that net (re-runnability demonstrated). `erc_errors` not worse than the
  routing-start baseline. **Human-eyes render** (F.Cu, B.Cu, 3D) confirms hand-designed look.

## LOCKED — you may not weaken these
- The Phase-D quality gates (tighten only). Metric DEFINITIONS (Resolution 6). Authoritative
  geometry + single writer (Resolution 1). Completion=DRC truth + divergence guard (Resolution 2).
  The determinism gate (Resolution 3). The aesthetic render gate every phase exit (Resolution 4).
  The route_db/incremental discipline (Resolution 5). Measure-every-iteration. Plan-before-build.
  Convergence-escalation (no repeating a stalled move). Tools-over-edits. Placement is frozen
  (footprints never move).
If you believe a locked rule is genuinely wrong, write a `REVIEW:` entry and keep complying.

## Anti-patterns (do the opposite)
- Hand-editing the board to fix a symptom → build/improve a tool.
- Repeating a non-improving move → escalate / switch approach.
- Declaring done by lowering/redefining a gate → forbidden.
- Accepting DRC-clean spaghetti → it must also pass the aesthetic + render gate.
- Letting KRT run multi-threaded / nondeterministic → force single-thread, fixed order; gate on
  determinism.
- Re-routing the whole board for a 1-net change → replay unchanged nets from route_db.
- Trusting `completion_pct` when `unconnected_divergence>0` → trust DRC, fix the metric.
- Writing the board while KiCad has it open → read-only that iteration.

## Existing assets (reuse, don't reinvent)
- **REUSE AS-IS:** `placement_phase_2/tools/writer_lock.py` (single-writer); `placement_phase_2/
  tools/measure.py` DRC plumbing (`run_kicad_cli`/`collect_violations`/`sev`/`_item_ref`, the
  `--append`/metrics-row harness, `POWER_RE`/`GROUND`); `placement_phase_2/tools/geom.py`
  `load_pcb`/`board_outline`; the `pcb-views` skill (render F.Cu/B.Cu/3D) for the render gate;
  the `Makefile`. `defcon_badge/tools/sync_nets_pcbnew.py` to re-sync nets after any board edit.
- **ENGINE:** KRT at `~/.local/share/defcon-badge-krt/KiCadRoutingTools` (pinned commit in
  `KRT_PINNED_COMMIT.txt`), run via `~/.local/share/defcon-badge-krt/venv/bin/python`. Key flags:
  `--nets`/`--rip-existing-nets` (incremental), `--guide-corridor[-layer/-spacing]` (bus seam),
  `--bus`/`--bus-attraction-*`, `--turn-cost`/`--via-cost`/`--track-proximity-cost` (aesthetics),
  `--power-nets[-widths]`, `--impedance`/`--track-width`/`--clearance`, `--ordering mps`.
- **BUILD (per their specs):** `measure_route.py`, geom track/via extension, `route_db.py`,
  `bus_plan.py` (emit guide corridors), `krt_route.py` (wrapper), `beautify.py`, `route_pipeline.sh`.

## Skills authored
(Append one line per new skill: name — purpose.)
- (pending) badge-routing — reusable aesthetic/deterministic/incremental routing system on KRT.
