#!/usr/bin/env python3
"""dead_end_detector.py — the ESCALATE rule as CODE (Pass-2 anti-thrash).

Pass 1's worst process miss: I knew the "don't repeat a stalled move" rule and violated it, chasing
the dead-end via-fixer through 4 variants of ONE approach family. This makes the rule enforceable:
a preflight that REFUSES to schedule another iteration under a stalled/banned approach family.

Model:
  - metrics.jsonl rows carry `phase` and `approach` (the FAMILY tag, coarse — e.g. 'posthoc-via-move',
    'qfn-multilayer', 'krt-default-route'). Cosmetic re-skins of a dead approach share a family tag, so
    they are caught (the 4 via-fixer variants were one family).
  - approaches.json: {"(phase|family)": {first_iter,last_iter,best,first,status,reason}}.
  - A family with >=3 rows in a phase whose PRIMARY metric improved <2% (relative, in the goal
    direction) from its first to its best row is BANNED. Banned families cannot be re-selected; the
    loop must take the next escalation-ladder rung.
  - A "finding-only"/"refactor" iteration is allowed but does NOT reset the counter (don't tag it with
    the working family; tag it 'finding' so it doesn't mask a stall).

Usage:
  dead_end_detector.py --phase R5 --primary completion_pct --proposed krt-route-aesthetic-knobs
     -> evaluates metrics.jsonl, updates approaches.json (auto-bans stalled families), and exits
        0 (proposed family ALLOWED) or 3 (BANNED — take the next ladder rung). Prints the verdict.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
METRICS = HERE / "metrics.jsonl"
APPROACHES = HERE / "approaches.json"
THRESH = 0.02
MIN_ROWS = 3

# goal direction per primary metric (does a BIGGER number mean progress?)
HIGHER_BETTER = {"completion_pct"}
# everything else we gate on is lower-better (via_in_pad, bus_pitch_var, drc_errors, unconnected,
# acute_angles, off_axis_segments, shorts)


def _rel_improvement(first, best, higher_better):
    if first is None or best is None:
        return 1.0
    if higher_better:
        denom = abs(first) or 1.0
        return (best - first) / denom
    denom = abs(first) or 1.0
    return (first - best) / denom


def evaluate(phase: str, primary: str) -> dict:
    rows = [json.loads(l) for l in METRICS.read_text().splitlines() if l.strip()] if METRICS.exists() else []
    appr = json.loads(APPROACHES.read_text()) if APPROACHES.exists() else {}
    higher = primary in HIGHER_BETTER
    by_fam: dict[str, list] = {}
    for r in rows:
        if r.get("phase") != phase:
            continue
        fam = r.get("approach") or "?"
        if fam in ("finding", "refactor", ""):
            continue
        v = r.get(primary)
        if v is None or v == -1:
            continue
        by_fam.setdefault(fam, []).append(v)
    for fam, vals in by_fam.items():
        best = max(vals) if higher else min(vals)
        first = vals[0]
        key = f"{phase}|{fam}"
        rec = appr.get(key, {"status": "active", "reason": ""})
        rec.update({"count": len(vals), "first": first, "best": best,
                    "improvement": round(_rel_improvement(first, best, higher), 4)})
        if rec["status"] != "champion" and len(vals) >= MIN_ROWS and rec["improvement"] < THRESH:
            rec["status"] = "banned"
            rec["reason"] = f"{len(vals)} iters, {primary} improved {rec['improvement']:.1%} (<{THRESH:.0%}) — dead end"
        appr[key] = rec
    APPROACHES.write_text(json.dumps(appr, indent=1, sort_keys=True))
    return appr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True)
    ap.add_argument("--primary", required=True)
    ap.add_argument("--proposed", required=True, help="the approach family you intend to run")
    args = ap.parse_args()
    appr = evaluate(args.phase, args.primary)
    key = f"{args.phase}|{args.proposed}"
    rec = appr.get(key)
    banned = bool(rec) and rec.get("status") == "banned"
    print(f"phase={args.phase} primary={args.primary} proposed={args.proposed!r}")
    for k, v in sorted(appr.items()):
        if k.startswith(args.phase + "|"):
            print(f"  {v.get('status','?'):8} {k.split('|',1)[1]:28} count={v.get('count','-')} "
                  f"best={v.get('best','-')} improv={v.get('improvement','-')}")
    if banned:
        print(f"VERDICT: BANNED — {rec.get('reason','')}. Take the next escalation-ladder rung (STATE.md).")
        return 3
    print("VERDICT: ALLOWED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
