# STATE (pointer only — durable history lives in LEDGER.md + metrics.jsonl)

Phase: **A — Reset & instrument**
Current approach: (none yet)
Next intended action:
  1. Delete thrash artifacts (cleanup_pass*.py, *.pre_cleanup*).
  2. Sweep every movable footprint to an off-board staging grid (keep Edge.Cuts).
  3. Build `tools/measure.py` emitting the full metric JSON (see HARNESS metrics schema).
  4. Record the baseline row in metrics.jsonl and seed LEDGER.md.

Exit gate (Phase A): board depopulated, Edge.Cuts unchanged, measure.py runs and baseline
logged, thrash artifacts removed. See HARNESS.md "Phase A" for the precise checklist.
