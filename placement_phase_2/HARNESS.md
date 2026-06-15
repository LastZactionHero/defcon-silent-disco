# HARNESS — autonomous placement loop (operational core)

You are the iteration engine. Every wake-up you run ONE iteration of the procedure
below, commit, log, and schedule the next wake-up. Read MISSION.md for the why; this
file is the how. The rules here are tuned to prevent the prior run's thrashing — see
MISSION.md "Why this exists".

---

## Per-wake-up procedure (do these in order, every time)
   All paths below are relative to the repo root (`/home/zach/dev/defcon_badge`), which is
   your cwd. Mission-control files live in `placement_phase_2/`; the board is
   `defcon_badge/defcon_badge.kicad_pcb`.
1. **Read (mandatory, every iteration):** `placement_phase_2/MISSION.md`, this file,
   `placement_phase_2/placement_rules.md`, `badge_hw_design.md`. Consult
   `placement_phase_2/placement_research.md` on demand when choosing or building an
   algorithm. *(The prior run failed partly because the design doc was never on its read
   path. It is now.)*
2. **Load durable memory:** read the tail of `placement_phase_2/LEDGER.md` and the
   **entire** `placement_phase_2/metrics.jsonl` (it is small — read all of it; it is your
   trend signal). Read `placement_phase_2/STATE.md` for the phase pointer and your last
   intended action.
3. **Identify current phase** and its exit gate (below).
4. **Measure:** run `placement_phase_2/tools/measure.py defcon_badge/defcon_badge.kicad_pcb`;
   append exactly one JSON row to `placement_phase_2/metrics.jsonl` (measure.py does the
   append when given `--append`).
   (In Phase A, building `measure.py` *is* the work and the baseline row is the output.)
5. **Convergence check** over the last K=5 rows of the phase's primary metric:
   - **Improving** (>2% relative gain): continue the current approach with the single
     highest-leverage action.
   - **Plateaued / oscillating** (≤2% net over 5 rows) **and gate met**: advance to the
     next phase (update the STATE.md pointer; commit a phase-transition entry).
   - **Plateaued / oscillating and gate NOT met**: **ESCALATE.** You may not repeat the
     stalled move. Either (a) switch to an algorithmic approach you have not yet tried,
     (b) do a global re-plan / re-place from scratch, or (c) if you have exhausted
     approaches, write a `BLOCKER:` entry and implement the most *different* method
     available (including the SOTA/RL options in the research). Escalation is mandatory,
     not optional.
6. **Choose the single highest-leverage action for the current phase.** Valid actions
   include — and planning/tooling actions are FIRST-CLASS, an iteration need not move a
   component: write a phase plan; write a tool spec; implement or refactor a tool; run a
   comparison experiment between approaches; apply a tool and measure.
7. **Execute.** Prefer building/improving a tool over editing files directly. If you touch
   a `.kicad_pcb` by hand beyond a one-liner, that is a signal you owe a tool instead.
8. **Commit + log:** commit message ``<phase>(<iter>): <one-line summary>`` (e.g.
   `C(37): SA placer beats force-directed on ratsnest, set as champion`). Append one line
   to `LEDGER.md` (action | rationale | result | metric delta). Confirm this iteration's
   row is in `metrics.jsonl`.
9. **Schedule next wake-up:** `ScheduleWakeup` with the contents of `placement_phase_2/PROMPT.md`
   verbatim as the `prompt`. `delaySeconds`:
   90–270 in active build/fix mode (keeps cache warm); 1200–1800 when you launch a long
   experiment (RL training run, Freerouting pass) so you wake to results. Stop scheduling
   only when MISSION "satisfied" holds, or after a sanity cap of ~150 iterations (write a
   wrap-up entry and stop).

---

## Durable memory (append-only — NEVER rotate or truncate; all under `placement_phase_2/`)
- **`metrics.jsonl`** — one JSON object per iteration. Required keys:
  `ts, phase, iter, approach, commit` plus every metric:
  `overlaps, offboard, unplaced, fp_unresolved, ratsnest_mm, courtyard_violations,
  decoupling_max_mm, dfm_spacing_violations, fixed_ok, erc_errors, drc_errors`.
  This is the ONLY thing that lets you detect thrashing. Do not skip a row. Do not delete
  rows. The prior run's lossy "last 5 iterations" memory is why it circled blind.
- **`LEDGER.md`** — append-only decision log. Entry format:
  `[ISO-date] <phase>(<iter>) — action | rationale | result | Δmetric`.
  Prefixes: `BLOCKER:` (stuck, exhausted approaches), `REVIEW:` (you think a locked rule
  is wrong — log it and keep complying), `CHAMPION:` (new best approach for a phase).
- **`STATE.md`** — a *small pointer only*: current phase, current approach, next intended
  action, this phase's exit gate. Durable history lives in the ledger and metrics, not here.

---

## Phase exit gates

### Phase A — Reset & instrument  (exit when all true)
- Every movable footprint swept to an off-board staging grid (below the outline,
  y > board_max + margin). Edge.Cuts UNCHANGED.
- `tools/measure.py` exists, runs, and emits the full metric JSON; baseline row in
  `metrics.jsonl`.
- Thrash artifacts removed: `defcon_badge/tools/cleanup_pass*.py`, `*.pre_cleanup*`, and
  any other reactive one-offs. (Keep the good primitives — see "Existing assets".)
- `LEDGER.md` and `STATE.md` seeded.

### Phase B — Floor-plan tool  (exit when all true)
- A floor-planner tool exists (e.g. `tools/floorplan.py`) WITH a committed spec, that
  reads the netlist + `badge_hw_design.md`, partitions components into functional zones,
  and emits a floor-plan artifact (zones with bounding boxes + every component assigned to
  exactly one zone + fixed/edge constraints recorded).
- The emitted floor plan validates: every component in exactly one zone; zones fit inside
  Edge.Cuts; fixed/edge-locked parts at required positions (per `placement_rules.md`);
  functional grouping matches the design-intent subsystems; signal-flow ordering respected.
- At least TWO distinct floor-planning approaches were implemented and scored on a
  documented metric; the champion is recorded (`CHAMPION:` in ledger).
- The tool is documented as a skill (`~/.claude/skills/...`) and listed under "Skills
  authored" below.

### Phase C — Placement engine  (LOCKED quality bar; exit when ALL true)
- `overlaps == 0` (courtyard)
- `offboard == 0` (every placed part inside Edge.Cuts; staging emptied)
- `unplaced == 0`  and  `fp_unresolved == 0`
- `fixed_ok` true: J20 top-right plug-up; J10 USB-C bottom edge; SW1 bottom-left;
  U30 IR-RX left edge y=110 and D20 IR-LED right edge y=110 (mirror); J31 microSD on B.Cu
  edge-accessible; 4× M2.5 holes at corners.
- `decoupling_max_mm <= 2.0` (every decoupling cap adjacent to its IC power pin; one 100n
  per U3 power pin).
- `dfm_spacing_violations == 0` (IPC nominal).
- `ratsnest_mm` improved **>= 20%** vs the Phase A naive baseline, AND non-regressing once
  achieved. (Prior hand-thrash run bottomed near ~1395mm — beat it and lock it.)
- Placement produced by your tools, not by hand-placing individual parts as the primary
  mechanism.
- `erc_errors` not worse than baseline (schematic ERC fixes are out of scope per design
  intent; do not regress them).

### Phase D — Routing (stretch; exit when)
- Routing attempted via a real engine (Freerouting through DSN/SES is the baseline; GPU /
  RL / custom permitted). DRC clean OR a documented best effort listing unrouted nets and
  why, in `LEDGER.md`.

---

## Permissions
You have full authority to:
- Create/refactor any tool or skill; rewrite `MISSION.md`, this file, `PROMPT.md`,
  `STATE.md`, `LEDGER.md` to improve them.
- Install packages (incl. a JRE for Freerouting, and CUDA/PyTorch for GPU RL — the host
  `g4` has an RTX 3060 / 12 GB; respect that VRAM budget). Use `sudo` only if necessary.
- Run long experiments. Cost/time is approved.

## LOCKED — you may not weaken these to make the job easier
- The **Phase C quality gates** (tighten only, never loosen).
- The requirement to **measure every iteration** and append to `metrics.jsonl`.
- The **plan-before-build** rule.
- The **convergence-escalation** rule (no repeating a stalled move).
- The **tools-over-edits** rule.
If you believe a locked rule is genuinely wrong, write a `REVIEW:` entry in `LEDGER.md`
and keep complying. A human adjudicates locked rules; you do not.

## Anti-patterns (these are the prior run's mistakes — do the opposite)
- Hand-editing `.kicad_pcb` to fix a symptom  →  build/improve a tool.
- Repeating a move that isn't improving the metric  →  escalate / switch approach.
- Accumulating one-off `cleanup_pass`-style scripts  →  consolidate into spec'd tools.
- Lossy memory  →  ledger + metrics are append-only; never rotate.
- Declaring done by lowering a gate  →  forbidden.
- Treating a global re-place as forbidden  →  it is encouraged when local placement stalls.
- Doing everything by eyeballing one render  →  measure, then look.

## Existing assets (audit, don't blindly inherit — they were built during the thrash)
- **KEEP and build on** (good primitives): the `pcb-placement` skill — `fp_meta.py`,
  `place_at.py`, `align.py`, `ratsnest.py`, `whats_near.py`, `check_courtyards.py`,
  `check_edge_components.py`, `rotate.py`; the `pcb-views` skill — `render_all.sh`,
  `render_area.py`; `render_pcb.sh`; the `Makefile` (render/fab/drc/erc targets).
- **Reference but re-derive**: `defcon_badge/tools/badge_floorplan.py` has a good zone
  diagram but was authored mid-thrash. Re-derive the floor plan from a proper spec in
  Phase B; don't just resurrect it.
- **DELETE in Phase A**: `cleanup_pass*.py`, `*.pre_cleanup*`, and other reactive one-offs.

## Skills authored
(Append one line per new skill: name — purpose.)
- badge-placement (~/.claude/skills/badge-placement) — reusable floor-planning + placement
  system: measure.py (metrics), depopulate.py (reset), floorplan.py (Approach A, champion),
  floorplan_partition.py (Approach B). Grows with the Phase-C placement engine.
