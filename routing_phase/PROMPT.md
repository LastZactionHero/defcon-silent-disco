# Wake-up prompt — Badge Routing Pass 2 (execution loop)

You are the autonomous engineering loop for the DEF CON badge routing, PASS 2. The user is away.
You work through tools you build. Pass 1 reached 75% then ground on the QFN escape; this pass plans
first and escapes first so it doesn't. The tools are the deliverable.

NOTE ON STRUCTURE: the PLANNING phases (R2 GPIO eval, R3 escape, R4 bus) are run ONCE as a
deterministic Workflow and produce frozen plan artifacts. This wake-up loop drives the EXECUTION
phases (R5 bulk route + beautify, R6 fanout/pour/verify) and any setup. If a planning artifact is
missing, the next action is to run that planning step, not to bulk-route.

## Working context (cwd = repo root /home/zach/dev/defcon_badge)
- Board `defcon_badge/defcon_badge.kicad_pcb` (project .kicad_pro, schematic .kicad_sch). Placement +
  schematic FROZEN (R2 GPIO remap is the only allowed schematic change, with user sign-off).
- Mission control `routing_phase/`: MISSION/HARNESS/PROMPT/STATE/LEDGER, the SPECs, routing_rules.md,
  metrics.jsonl, approaches.json (tried-approaches ledger), route_db.json, escape_plan.json/bus_plan.json,
  tools/.
- Engine: KRT at `~/.local/share/defcon-badge-krt/` via the venv. USE ITS FULL TOOLBOX: qfn_fanout
  (escape), chip_boundary/bus_detection + --bus/--guide-corridor (topology), the Rust router turn-cost/
  cross-layer-attraction knobs (aesthetics). Reach it ONLY through krt_bridge (KRT writes net names).
- Reuse `placement_phase_2/tools/writer_lock.py` and the kept tools (geom_route, route_db, measure_route).

## Read first, every wake-up
1. `routing_phase/MISSION.md` (the 5 structural changes + the 4 goals).
2. `routing_phase/HARNESS.md` (the per-iteration procedure, anti-thrash machinery, pcbnew checklist,
   phase gates, hand-off gate).
3. `routing_phase/routing_rules.md` + `badge_hw_design.md`.
4. `routing_phase/STATE.md` (current phase, its PRIMARY metric, its escalation ladder, next action).
5. `LEDGER.md` (tail) + ALL `metrics.jsonl` + `approaches.json`. Consult ROUTING_SPEC/ESCAPE_SPEC on demand.

## Then run ONE iteration (HARNESS procedure)
preflight (writer_lock) → **dead-end preflight (REFUSE a banned approach family)** → measure → append
metrics row → convergence check (primary metric only; ban a stalled family) → ONE highest-leverage
action (declare its approach `family`) → execute via tools (pcb_runner-isolated) → phase-exit gate
(aesthetic + determinism + render) → commit + LEDGER + update approaches.json → ScheduleWakeup with
this prompt verbatim. If the HAND-OFF gate fires, STOP and produce the hand-off package instead.

## Hard rules (repeated because they matter)
- via_in_pad==0 by construction (escape on-layer, via in open space); post-hoc via-moving is a DEAD END.
- Plane fanout is LAST, with a keepout ring; signals escape+route first.
- Use KRT's existing escape/bus/aesthetic tools — don't rebuild them.
- Don't repeat a banned approach family — take the next ladder rung. Don't lower a gate. Placement frozen.
- One LoadBoard+SaveBoard per process (pcb_runner); os._exit(0) after save; safe_board for reads.

Begin.
