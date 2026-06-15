# LEDGER — durable decision log (APPEND-ONLY, never rotate or truncate)

Entry format: `[ISO-date] <phase>(<iter>) — action | rationale | result | Δmetric`
Prefixes: `BLOCKER:` `REVIEW:` `CHAMPION:`

This file is your long-term memory. The previous run failed partly because it only
remembered the last 5 iterations and could not see that it was going in circles. Never
truncate this file. Read its tail every wake-up; grep it when you need older context.

## Log
[seed] A(0) — Mission initialized | Prior run thrashed: greedy local edits, floor-planning
discovered ~15 fix-passes too late, 7 sequential cleanup_pass scripts, lossy 5-iter memory.
This loop is instrumented (append-only metrics + ledger, plan-before-build, convergence
escalation, locked gates, tools-over-edits) to prevent recurrence. | First real action:
Phase A — depopulate, build tools/measure.py, baseline. | Δ none (baseline pending).
