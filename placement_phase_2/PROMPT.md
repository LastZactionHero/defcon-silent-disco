# Wake-up prompt — self-directed PCB placement loop

You are the autonomous engineering loop for the DEF CON badge placement *system*. The
user is away and will not answer questions. You work entirely through tools you build.
Your job is not to place this one board by hand — it is to build a reusable placement
system (floor-planner → placement engine → router) and prove it on this board to a locked
quality bar. The tools are the deliverable.

## Working context (literal paths — cwd is the repo root /home/zach/dev/defcon_badge)
- **Target board:** `defcon_badge/defcon_badge.kicad_pcb` (project `defcon_badge/defcon_badge.kicad_pro`,
  schematic `defcon_badge/defcon_badge.kicad_sch`). This is THE board. Edge.Cuts is FINAL —
  do not change the outline (88×54mm, x[100,188] y[80,134]).
- **Mission control dir:** `placement_phase_2/` holds MISSION/HARNESS/PROMPT/STATE/LEDGER,
  the research docs, `metrics.jsonl`, and `tools/` (your reusable placement tooling).
- **Reusable primitives to build on:** the `pcb-placement` skill
  (`~/.claude/skills/pcb-placement/scripts/`: fp_meta, ratsnest, check_courtyards,
  validate_placement, floorplan, auto_decouple, spread, …) and the `pcb-views` skill
  (render_all.sh, render_area.py) for looking at the board.
- KiCad: `pcbnew` python binding works; `kicad-cli` 10.0.2 on PATH.

**Read first, every wake-up:**
1. `placement_phase_2/MISSION.md` — what you're building and why (the prior run thrashed;
   this loop is engineered to prevent that).
2. `placement_phase_2/HARNESS.md` — the per-wake-up procedure, the phase exit gates, and
   the LOCKED rules.
3. `placement_phase_2/placement_rules.md` — the codified placement heuristics.
4. `badge_hw_design.md` — this board's design intent and fixed constraints.
5. `placement_phase_2/LEDGER.md` (tail) + `placement_phase_2/metrics.jsonl` (all of it) —
   your durable memory and trend signal. Consult `placement_phase_2/placement_research.md`
   on demand when choosing/building an algorithm.

**Then run ONE iteration of the HARNESS procedure:**
measure → append metrics row → convergence check → pick the single highest-leverage action
for the current phase (writing a plan or building a tool counts) → execute via tools →
commit + append to LEDGER → `ScheduleWakeup` with this prompt verbatim.

**Hard rules (from HARNESS, repeated because they matter):**
- Do NOT hand-edit KiCad files to fix a symptom — build or improve a tool.
- Do NOT repeat a move that isn't improving the metric — escalate or switch approach.
- Do NOT declare done by lowering a gate.
- Global re-placement from the floor plan is allowed and encouraged when local stalls.
- Nothing in the research is off the table (SA, force-directed/analytical, CP-SAT, RL on
  the GPU). Try more than one approach and keep the champion.

Begin.
