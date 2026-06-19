# The self-coding design philosophy

How this repo got Claude to write, critique, and improve its own PCB design
tools — totally unattended for ~50 commits across two days — and how to port
that same philosophy to a different project.

This is a description of a *method*, not of PCBs. The badge is just the proof
of concept. The reusable artifact is the loop.

---

## 1. What actually happened here

The user went to sleep and left an agent running. It woke itself up on a timer,
and on each wake-up it:

1. Looked at the current state of the work (literally — it rendered the board
   to a PNG and *read the image*).
2. Measured the work against objective checks (ERC, DRC, footprint resolution,
   courtyard overlaps, ratsnest length).
3. Picked the single highest-value fix it could finish in one sitting.
4. Made the change — usually by writing or editing a Python script that
   manipulates the KiCad files, not by hand-editing them.
5. Committed with a one-line message.
6. Updated a short state file.
7. Scheduled its own next wake-up and went back to sleep.

The output you can see in `git log`: `iter(0)` through `iter(42)`, then a
second phase of conventional-commit polishing. Along the way it did three
things that make this "self-coding" rather than just "automated":

- **It built its own tools.** `defcon_badge/tools/` holds ~40 Python scripts it
  authored: outline generators, net-sync utilities, placement engines, silk-art
  generators, a dozen `cleanup_pass*.py` scripts. Each was written because a
  task recurred often enough to deserve a tool.
- **It promoted tools into reusable skills.** When a tool was good enough to use
  on *any* PCB (not just this badge), it was lifted into
  `~/.claude/skills/pcb-placement` and `~/.claude/skills/pcb-views` with their
  own `SKILL.md` — `place_at.py`, `align.py`, `ratsnest.py`, `spread.py`
  (force-directed legalization), `check_courtyards.py`, `render_area.py`. The
  agent grew a standard library for the *domain*, then reused it.
- **It rewrote its own instructions.** `HARNESS.md` and `PROMPT.md` explicitly
  grant permission to edit `HARNESS.md` and `PROMPT.md`. The loop was allowed to
  improve the loop.

The headline isn't "Claude designed a PCB." It's "Claude was given a tight
feedback loop, a way to *see* its work, permission to build tooling, and a
single-fix-per-iteration discipline — and it compounded."

---

## 2. The five load-bearing ideas

These are the parts you actually need to copy. Everything else is decoration.

### 2.1 A closed perception→action loop

The agent never works blind. Every iteration begins with perception and ends
with a committed change. The critical and easily-skipped half is **perception**.
Here it took the form of `render_pcb.sh --quick` producing `assembly.png`, which
the agent then *read as an image*. HARNESS.md lists "skipping the render+read
step" as an explicit anti-pattern.

> The single most important rule in the harness is: **you MUST look at the
> board each time.** An agent that can't see the consequence of its last edit
> will drift.

### 2.2 Objective, machine-checkable scorers

Looking is subjective. To keep progress honest, the loop pairs the visual review
with hard metrics it can compute and trend:

| Signal | Tool | What it catches |
|---|---|---|
| ERC violations | `kicad-cli sch erc` | schematic wiring errors |
| DRC violations | `kicad-cli pcb drc` | physical rule violations |
| Footprint resolution | `check_footprints.py` | parts that won't build |
| Courtyard overlaps | `check_courtyards.py` | components colliding |
| Ratsnest length | `ratsnest.py` | placement quality (shorter = better) |

These turn "is it better?" into a number. `iter(39)` literally reads
"signal-flow optimization, ratsnest 1474→1395mm (-79mm)" — a quantified
improvement. The scorers are the difference between iterating and flailing.

### 2.3 One fix per iteration, committed

The harness forbids "big bang" rewrites (>50% of the board) and "multiple
unrelated fixes in one commit." Each iteration does exactly one thing and
commits it. This is what makes the run *recoverable* and *legible*: every step
is a small, reviewable diff, and `git log` becomes the agent's long-term memory.
When `iter(30)` went wrong, `iter(34)` could "reset to the iter-30 baseline"
because the history was clean.

### 2.4 Externalized, bounded memory

Context windows are finite, so durable state lives on disk, deliberately small:

- **`STATE.md`** — current focus, the *last 5 iterations only* (older context
  "lives in `git log`"), live ERC/DRC counts, and a TODO checklist. The cap is
  explicit: "Don't accumulate an essay."
- **`git log`** — the full, append-only history.
- **`HARNESS.md`** — the durable playbook and the definition of done.

The agent reloads `STATE.md` + `git log -20` at the start of every iteration.
That three-file pattern (playbook / rotating-state / history) is the whole
memory system.

### 2.5 Permission to build and to self-modify

The harness grants, in writing, the authority to:

- create new tools under `tools/`,
- promote them into reusable skills under `~/.claude/skills/`,
- and **edit the harness and prompt themselves** as it learns what works.

This is what converts a worker into a tool-builder. Without it, the agent
re-solves the same placement math by hand every time. With it, it writes
`place_at.py` once and calls it forever. The compounding comes from here.

### 2.6 A self-scheduling clock with a stop condition

The loop drives itself via `ScheduleWakeup`: 90–270s between active fixes (keeps
the prompt cache warm), 1200–1800s when it needs to "think about the next
phase." Crucially it has a **definition of done** and a **sanity cap** (~80
iterations). It knows when to stop — and it did, at iter 29, writing a wrap-up
commit rather than spinning. Autonomy without a terminal condition is just a way
to burn tokens.

---

## 3. The anatomy of one iteration (the template)

```
wake →
  cat STATE.md                      # current focus, last 5 iters, TODO
  git log --oneline -20             # recent history
  render + READ the image           # PERCEIVE the current state
  run the scorers (ERC/DRC/...)     # MEASURE objectively
  →
  pick the SINGLE highest-value fix # one thing, finishable now
  make the change (prefer: write/edit a script, not hand-edits)
  →
  commit  "iter(N): <one line>"     # small, legible diff
  rotate STATE.md (drop oldest)     # bounded memory
  ScheduleWakeup(delay)             # self-clock
→ sleep
```

Stop when the definition of done is met, or the iteration cap is hit, with a
wrap-up commit.

---

## 4. Porting it to another project

The philosophy is domain-agnostic. To move it to project **X**, you instantiate
six things. The hard part is almost always #2 (perception) and #3 (scorers) —
if you nail those, the rest is boilerplate.

### Step 0 — Pick a project that fits

This loop shines when the work is:

- **Iterative** — improvable in small steps, not one monolithic decision.
- **Perceivable** — you can render/observe the current state cheaply.
- **Scorable** — at least one objective metric exists or can be built.
- **File-based** — the artifact lives in files an agent can edit and commit.

Good fits: codebases (tests = scorers, the app running = perception), data
pipelines, infra-as-code, generative/design work with a renderer, documents with
linters. Poor fits: tasks with no feedback signal, or where each step needs
human sign-off anyway.

### Step 1 — Write the harness (`HARNESS.md`)

This is the constitution. Copy the structure from this repo's `HARNESS.md` and
fill in:

- **Permissions** — state explicitly that the agent may edit the harness, build
  tools, and create skills. Spell out what it may *not* do (e.g. "don't push to
  remote," "no `sudo` unless necessary").
- **Goal + constraints** — concrete and checkable.
- **Per-iteration playbook** — the perceive → measure → pick-one → change →
  commit sequence, with the exact commands for *your* domain.
- **Anti-patterns** — name the failure modes ("big-bang rewrites," "skipping
  the perception step," "routing before placement is sane" → translate to your
  domain's equivalent of "don't optimize before the structure is right").
- **Definition of done** — per-iteration *and* overall.
- **Pacing** — wake intervals and an iteration cap.

### Step 2 — Build the perception tool (the "render")

The agent must be able to *see* the current state in one cheap command. Ask:
**"What is the PNG for my domain?"**

- Web/app → screenshot the running app (Playwright, etc.).
- CLI/library → run it on a representative input and capture output.
- Data → render a chart or a summary table.
- Docs → render to HTML/PDF.

For text-output domains the "render" can just be a structured summary the agent
reads — but if a *visual* is possible, prefer it. Reading a rendered image
caught aesthetic and spatial problems here that no linter would have.

### Step 3 — Build the scorers

Wire up every objective check you can, each as a one-shot command emitting a
number or a count:

- Code → test pass/fail count, type errors, lint count, coverage, benchmark ms.
- Data → row counts, schema-validation errors, accuracy metrics.
- Design → domain checks (the PCB's courtyard/ratsnest analogue).

Aim for at least one *quality gradient* (a number that should monotonically
improve, like ratsnest length), not just pass/fail gates. The gradient is what
lets the agent tell "better" from "merely legal."

### Step 4 — Set up bounded memory

Create the three-file memory system:

- `STATE.md` — current focus, last-N iterations (cap it!), live metric values,
  TODO checklist.
- Git history — one commit per iteration, prefixed (`iter(N): ...`).
- The harness — durable rules.

Tell the agent in the prompt to reload `STATE.md` + `git log` every iteration
and to rotate `STATE.md` (drop the oldest entry) rather than let it grow.

### Step 5 — Write the entry prompt (`PROMPT.md`)

A short prompt the loop re-runs verbatim each wake-up. It should: point at
`HARNESS.md` and `STATE.md` as required reading, restate the perceive→measure→
fix→commit→reschedule sequence, grant authority (edit harness, build skills,
refactor tools), list the hard "DO NOT"s (don't ask the sleeping user
questions; don't skip perception; don't do everything at once), and end with
`Begin.`

### Step 6 — Seed tooling, then let it grow

Don't pre-build everything. Give it the perception command, the scorers, and a
Makefile of common operations (this repo's `Makefile` wraps render/sync/fab/drc/
erc). Then let the agent author new tools as tasks recur, and **promote the
generalizable ones into skills**. Document each new skill back in `HARNESS.md`
under a "Skills authored" section — closing the loop on its own tool-building.

---

## 5. The porting checklist

```
[ ] Project is iterative, perceivable, scorable, file-based
[ ] HARNESS.md: permissions, goal+constraints, playbook, anti-patterns, DoD, pacing
[ ] One cheap "render" command the agent reads each iteration
[ ] One or more scorer commands → numbers (incl. ≥1 quality gradient)
[ ] STATE.md: focus + last-N (capped) + live metrics + TODO
[ ] Commit discipline: one fix per iteration, prefixed messages
[ ] PROMPT.md: required reading + loop steps + authority + DO-NOTs + "Begin."
[ ] Self-scheduling with a definition of done AND an iteration cap
[ ] Permission (in writing) to build tools, promote skills, edit the harness
[ ] A Makefile or task runner wrapping the common operations
```

---

## 6. Failure modes this design defends against

- **Drift / blind editing** → mandatory perception step every iteration.
- **Vibes-based "progress"** → objective scorers and a quality gradient.
- **Context exhaustion** → bounded `STATE.md` + history-as-memory.
- **Unrecoverable wrong turns** → one small commit per iteration; you can reset
  to any baseline (as iter 34 did).
- **Infinite spinning** → explicit definition of done + iteration cap +
  willingness to stop and write a wrap-up.
- **Re-solving the same problem** → permission and discipline to build tools and
  promote skills.

The badge is fab-ready-minus-routing because of these guardrails, not in spite
of them. Copy the guardrails, not the geometry.
