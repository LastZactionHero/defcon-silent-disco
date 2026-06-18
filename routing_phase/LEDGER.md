# LEDGER — routing loop decision log (append-only; NEVER rotate/truncate)

Format: `[ISO-date] D?(N) — action | rationale | result | Δmetric`.
Prefixes: `BLOCKER:` (stuck, exhausted approaches) · `REVIEW:` (a locked rule may be wrong — log +
keep complying) · `CHAMPION:` (new best approach) · `MANUAL(user...)` (user-directed out-of-band edit).

---

[2026-06-17] D0(0) — SETUP/AUTHORING (by the mission-author session, not a loop iteration).
  ACTION: stood up the routing phase. (1) Two deep research workflows: routing-phase bearings
  (harness reuse, headless DSN path, router survey, net plan, metric/gate spec) + routing-engine
  architecture (aesthetic routing, determinism/ECO, Freerouting fork-vs-build, KRT assessment,
  4-layer stackup rework). (2) ENGINE DECISION: REJECT Freerouting (110kloc legacy Java, structural
  ugliness, Java 25, non-deterministic, no incremental — forking buys the property we don't want);
  BUILD ON KiCadRoutingTools (MIT, KiCad-10-native, deterministic, diff-pairs/planes/rip-up; default
  aesthetics are griddy → OUR layer owns aesthetics). (3) Vetted KRT firsthand: cloned, viewed demo
  renders (confirmed default output is autorouted-looking on DENSE boards; our badge is sparse),
  confirmed MIT + KiCad 9/10 + the CLI seams (--guide-corridor, --bus, --turn/via/track-proximity
  cost, --nets/--rip-existing-nets for incrementality). (4) Installed the engine env: KRT pinned at
  ce5cb2d (v0.15.13) under ~/.local/share/defcon-badge-krt/, isolated venv with cp314
  numpy/scipy/shapely wheels, prebuilt rust grid_router kernel — smoke-tested OK. (5) Authored
  mission-control: MISSION/HARNESS/PROMPT/STATE/ROUTING_SPEC/STACKUP_SPEC/routing_rules + setup.sh.
  RATIONALE: user chose to build (not click Freerouting); the spec is aesthetic + deterministic +
  re-runnable + ours. Mirror the placement_phase_2 harness (authoritative geometry + DRC-backed
  instrument + locked gates + append-only memory + anti-thrash convergence rule).
  RESULT: env ready; board still unrouted (0 tracks/vias); 4-layer stackup is a porting artifact to
  be reworked in D1. No metrics row yet (D0's first loop iteration builds measure_route.py + baseline).
  USER DECISIONS recorded: 4-layer (rework the ported zones), fully-autonomous loop (run free,
  minimal interruption, all tooling on the table), engine = my call (chose build-on-KRT), re-runnable
  is a real goal. Δmetric: n/a (baseline pending).
  NOTE: a one-time host prerequisite remains optional — none blocking (KRT env already installed in
  the venv; no sudo/JRE needed). The loop owns the board file; placement is frozen.
