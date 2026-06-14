# /loop entry prompt

You are iterating autonomously on the DEF CON badge PCB at
`/home/zach/dev/defcon_badge`. The user is asleep. Do NOT ask questions.
Use Bash, Read, Edit, Write, and any other tools as needed. Commit every
iteration.

**Read these first, every time:**
1. `/home/zach/dev/defcon_badge/HARNESS.md` — playbook + permissions.
2. `/home/zach/dev/defcon_badge/STATE.md` — current focus and TODO.
3. `git -C /home/zach/dev/defcon_badge log --oneline -20`

Then run ONE iteration per the playbook:
- Render: `cd /home/zach/dev/defcon_badge && ./defcon_badge/tools/render_pcb.sh --quick`
- Read `renders/assembly.png`. LOOK at it.
- Run ERC + DRC + footprint check (commands in HARNESS.md).
- Pick the single highest-value fix you can complete in this iteration.
- Make the change. Edit code/schematic/PCB. Be precise — KiCad files are
  s-expressions and order matters.
- `git add -A && git commit -m "iter(N): <one-line summary>"` where N is one
  greater than the last `iter(...)` commit (see git log).
- Update `STATE.md`: rotate the "Last 5 iterations" list (drop oldest, add this
  one); update ERC/DRC counts; tick anything off the TODO.
- ScheduleWakeup with this same prompt verbatim. Choose `delaySeconds`:
  - In active fix mode: 90–270s (keeps prompt cache warm).
  - When you hit a hard think-required moment: 1200–1800s.
  - Stop scheduling when Definition of Done is met, or you've done ~80 iterations.

You have full authority to:
- Rewrite HARNESS.md / PROMPT.md / STATE.md as you learn what works.
- Author new skills under `~/.claude/skills/` and document them in HARNESS.md.
- Refactor or replace any script under `defcon_badge/tools/`.
- Reshape the board outline, swap parts, restructure schematic sheets.

DO NOT:
- Ask the user questions. They are asleep.
- Skip the render+read step.
- Try to do everything in one iteration. Make steady, committed progress.
- Push to GitHub (the local commits are enough; remote push is the user's call).

Begin.
