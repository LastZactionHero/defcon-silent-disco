# Iteration harness — DEF CON silent disco badge

You (Claude) are the iteration engine for this project. Every wake-up, you run
ONE iteration of the playbook below, commit, then schedule the next wake-up
via `ScheduleWakeup`. Run autonomously for many hours.

## Permissions (explicit)
- You may freely edit anything in this repo, including this HARNESS.md file
  and the iteration prompt at PROMPT.md. Improve them as you learn.
- You may create new skills under `~/.claude/skills/` (with `SKILL.md`
  frontmatter) when a recurring task deserves one. Document each new skill in
  HARNESS.md under "Skills authored".
- You may install system packages with `sudo` only if absolutely necessary —
  default is to do without. JRE is not installed; do not attempt freerouting
  unless you've verified `java -version` works.
- Every iteration MUST commit, even if the change is small. Use the message
  prefix `iter(<N>): <one-line summary>`. The next iteration reads `git log`.

## Goal
Functional, stylized, edgy DEF CON badge PCB ready for fab. Constraints:
- Roughly credit-card size (86 × 54mm baseline; you may grow up to ~100×62mm
  or pick a non-rectangular silhouette if it serves the aesthetic).
- USB-C connector for power+data (currently missing — add it).
- All footprints resolve from stock KiCad libs (use `tools/check_footprints.py`).
- DRC clean (or with documented exceptions).
- ERC clean.
- Schematic-parity clean.
- Aesthetic silkscreen / front-art that says "DEF CON" without being copyright-risky.
- Gerber + drill files exported under `fab/` on the final iteration.

## What's in the repo
- `defcon_badge/` — KiCad project (sheets: Audio, IO, LEDs_IR, MCU_Core, Power).
- `defcon_badge/tools/` — Python scripts that generated the schematic and PCB.
- `tools/` symlink (if created) and the helpers below.

## Per-iteration playbook
At the top of every iteration:
1. `cat STATE.md` to read the current focus, last-iteration notes, and TODO.
2. `git log --oneline -20` to see recent changes.
3. Run `defcon_badge/tools/render_pcb.sh --quick` then Read `renders/assembly.png`.
   Look at the board. Compare to STATE.md "current focus".
4. Run `kicad-cli sch erc --format json -o /tmp/erc.json defcon_badge/defcon_badge.kicad_sch`
   and `kicad-cli pcb drc --schematic-parity --format json -o /tmp/drc.json defcon_badge/defcon_badge.kicad_pcb`.
   Extract violation counts.
5. Run `python3 defcon_badge/tools/check_footprints.py > /tmp/fp.json`.

Then PICK THE SINGLE HIGHEST-VALUE FIX for this iteration. Examples of valid
single-iteration scope:
- Add USB-C connector to Power schematic + place it on the PCB edge.
- Re-cluster a subsystem (audio, charger, MCU) into a tight zone.
- Rewrite the board outline to a more interesting shape.
- Add silkscreen vector art (text logo, traces, glyphs).
- Resolve a class of ERC errors (e.g., add missing PWR_FLAG on +3V3).
- Move microSD to a board edge so it's accessible.
- Fix audio jack footprint/orientation (it's currently vertical through-hole;
  consider a horizontal SMD jack or relocate).
- Add ground pours on F.Cu and B.Cu.
- Trace fan-out for a chip (escape routes).
- Once placement is sane: hand-route the most critical net.

**Anti-patterns** (don't do these):
- "Big bang" rewrites that touch >50% of the PCB in one iteration.
- Multiple unrelated fixes in one commit — split them across iterations.
- Skipping the render+read step (you MUST look at the board each time).
- Reaching for routing while placement is still chaotic.

## Definition of done (per iteration)
- A render exists for the new state (commit `renders/assembly.png` periodically;
  every 5 iterations is fine, don't bloat git on every iter).
- ERC/DRC counts in STATE.md updated.
- A one-line commit on `main`.

## Definition of done (overall)
- ERC: 0 errors (warnings OK if documented).
- DRC: 0 errors after a routing pass (warnings OK if documented).
- Schematic parity: 0 issues.
- All footprints resolve.
- Board outline is intentional and credit-card-ish.
- Front silk has DEF-CON-appropriate art (not literal copyrighted logo).
- `fab/gerbers/` populated; `fab/README.md` documents the order details.
- A final commit `iter(final): fab-ready` is pushed.

## Pacing
Between iterations: `ScheduleWakeup` with `delaySeconds` in [60, 270] when
in active fix mode (cache stays warm). If you finish a hard problem and want
to think about the next phase, sleep 1200-1800s. Stop scheduling when DoD
is met, or after ~80 iterations (sanity cap — write a wrap-up commit).

## Skills authored
(Append entries here as you create new skills, with a one-line purpose.)

## Iteration log shorthand
STATE.md tracks the LAST 5 iterations only — older context lives in `git log`.
Don't accumulate an essay.
