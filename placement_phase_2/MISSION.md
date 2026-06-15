# MISSION — Self-Directed PCB Placement System

## What you are building
You are an autonomous engineering loop. Over many self-scheduled iterations, with no
human intervention, you will **design, implement, validate, and refine your OWN reusable
PCB tooling** — a floor-planner, a placement engine, and (stretch) a router — and use
that tooling to rebuild the DEF CON silent-disco badge layout from a depopulated board.

The board is the test case. **The tools are the deliverable.** When you are finished the
repo must contain a clean, documented, reusable placement *system* that (a) produces this
board to the locked quality bar in HARNESS.md and (b) generalizes to future boards — not
a pile of one-off scripts that happened to nudge this one layout into shape.

## Why this exists — read this, it is the whole point
A previous autonomous run on this board thrashed. It made greedy local edits, never
planned globally, rediscovered "floor planning" only after ~15 reactive fix-passes,
accumulated seven sequential `cleanup_pass` scripts, and could not tell it was going in
circles because its working memory held only the last 5 iterations. This mission is
engineered to make those specific failures impossible. **Every rule below maps to one of
them. Do not route around the rules — they are the lesson.**

## Operating philosophy (non-negotiable)
1. **Tools over edits.** Never hand-hack KiCad s-expressions to fix a symptom. If you are
   editing a `.kicad_pcb` by hand beyond a trivial one-liner, STOP and build/improve a
   tool. Every capability you need becomes a reusable, tested, documented tool.
2. **Plan before you build.** Every tool starts with a short committed spec (purpose,
   objective it optimizes, how it is validated) BEFORE implementation. Every phase starts
   with a committed plan.
3. **Measure everything.** You define quantitative metrics and append them to a durable,
   append-only log every iteration. You never fly blind; you never trust your eyes alone.
4. **Detect thrashing and escalate.** If a metric plateaus or oscillates you are
   FORBIDDEN from repeating the same move — switch approach or re-plan globally.
5. **Global rebuilds are encouraged.** Tearing the board down and re-placing from a floor
   plan is a first-class move, not an anti-pattern. (The prior run was wrongly forbidden
   this and suffered for it.)
6. **The quality bar is locked.** You may make the gates *stricter*. You may NEVER loosen
   them to declare yourself done.
7. **Use the research.** `docs/placement_rules.md` (read every iteration) and
   `docs/placement_research.md` (deep reference) are your knowledge base. Nothing in the
   research is off the table — simulated annealing, force-directed / analytical, CP-SAT
   no-overlap, RL on the GPU. Pick what the evidence supports; try more than one and keep
   the champion.

## Phases (in order; each has a locked exit gate in HARNESS.md)
- **Phase A — Reset & instrument.** Depopulate the board (sweep every movable footprint
  to an off-board staging grid), keep Edge.Cuts unchanged, delete prior thrash artifacts,
  and build `tools/measure.py` so every later iteration has objective metrics. Record the
  baseline.
- **Phase B — Floor-plan tool.** Build a reusable floor-planner that parses the netlist +
  design intent into functional zones, honors fixed/edge constraints, and emits a
  floor-plan artifact. Implement and compare at least two distinct approaches.
- **Phase C — Placement engine.** Build incremental + global placement tools and place the
  whole board from the floor plan. Optimize the objective until the locked quality gate
  passes and the metric plateaus. Champion/challenger across approaches.
- **Phase D — Routing (stretch).** Only after C is locked. Integrate/build a router
  (Freerouting via DSN/SES is the baseline; GPU/RL/custom are permitted). DRC-clean or
  documented best effort.

## What "satisfied" means
Done = all Phase C gates pass, the primary metric has plateaued at/above the bar
(improvement < 2% over the last 5 iterations while gates hold), every tool is documented
as a skill, and `LEDGER.md` has a final summary. Phase D is a bonus. If you exhaust every
approach for a phase and still cannot meet a gate, write a `BLOCKER:` entry in `LEDGER.md`
with everything you tried and keep attempting the most *different* method available — do
not lower the gate and do not quit.
