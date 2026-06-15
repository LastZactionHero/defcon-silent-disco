# Floor-planner spec (committed BEFORE implementation — plan-before-build)

Tool: `placement_phase_2/tools/floorplan.py`
Artifact it emits: `placement_phase_2/floorplan.json`
Status: spec frozen at B(2). Implementation follows in B(3+).

## Purpose
Turn the netlist + design intent into a **floor plan**: a set of rectangular functional
zones tiled inside Edge.Cuts, every movable component assigned to exactly one zone, and the
fixed/edge-locked parts pinned at their required positions. The floor plan is the global
plan the Phase-C placement engine fills in. It exists so placement is *global and
signal-flow-aware* from the start, instead of greedy local nudging (the prior run's failure).

## Objective it optimizes
Primary: **minimize total estimated inter-zone ratsnest** (sum of MST wirelength using each
component's assigned zone centroid as its position proxy), subject to hard constraints:
- every component in exactly one zone; zones disjoint-enough and fully inside Edge.Cuts;
- fixed/edge parts at their locked positions;
- each subsystem's parts contiguous (one zone);
- signal-flow ordering respected (input→processing→output adjacency).
Secondary (tie-breakers): zone area utilization within capacity, shorter cross-board nets
(LED chain, I2S, QSPI, USB), audio/IR kept away from LED/switching noise.

## Inputs
- `defcon_badge/defcon_badge.kicad_pcb` (footprints, pads, nets, courtyard sizes via fp_meta).
- `badge_hw_design.md` (subsystem intent, signal flow, placement notes).
- Locked fixed constraints (below). Edge.Cuts AABB: x[100,188] y[80,134] (88×54mm).

## Output artifact (`floorplan.json`)
```json
{
  "board": {"x0":100,"y0":80,"x1":188,"y1":134},
  "zones": {
    "<name>": {"bbox":[x0,y0,x1,y1], "topology":"ring|chain|row|column|cluster|edge",
               "anchor":"<refdes|null>", "flow":"<dir>", "note":"..."}
  },
  "fixed": {"<refdes>": {"pos":[x,y], "rot":<deg>, "layer":"F.Cu|B.Cu", "why":"..."}},
  "assign": {"<refdes>":"<zone>"},          // every movable comp -> exactly one zone
  "score": {"approach":"...", "est_ratsnest_mm":<f>, "violations":[...]}
}
```

## Zone model
A zone is a rectangle + a topology rule the placement engine uses to lay its members out:
- `ring` — IC at center, decoupling/support caps ringed around its power pins (MCU, DAC).
- `chain` — parts in signal-flow order along a direction (power chain, audio chain, LED row).
- `row` / `column` — evenly spaced line (buttons, connector banks).
- `cluster` — loose group, packed compactly (misc passives of one subsystem).
- `edge` — pinned to a board edge at a given side/offset (connectors, IR pair).

## Subsystems → zones for THIS board (constructive starting point, derived from netlist)
- **mcu** (ring, anchor U3): U3 RP2040, U2 flash, Y1 xtal, C2/C3 (15p load), R5 (xtal 1k),
  R1/R2 (BOOTSEL/QSPI_SS), decoupling C5,C6,C7,C8,C9,C10,C11,C12,C14,C16,C23 (100n/1u on
  +3V3/+1V1), bulk C1,C4,C41,C71 (10u), R3/R4 (27Ω USB series). Center of board.
- **power** (chain, flow USB→LDO): U10 TP4056, U11 LDO, C20(1u VBUS), C21(10u BAT),
  C22(1u BAT_SW), R12(2.4k PROG), R13(100k CHRG), R14/R15(100k VBAT divider),
  R10/R11(5.1k CC). Bottom band near J10/J11.
- **audio** (chain, flow DAC→amp→jack, toward J20 top-right): U20 TM8211, U21 TDA1308,
  C42/C43(10u couple), C44(10u VGND), C40(100n), R20/R21(47k in), R22/R23(100k fb),
  R24/R25(10k vground), C45/C46(220u out). Upper-right, feeding J20.
- **leds** (row across top): LED20,LED21,LED22,LED23 + C60,C61,C62,C63(10n) + C70(100n)+C71(10u).
- **sao** (edge cluster): J30 + R40/R41(4.7k I2C pullups). A free edge (lower-left).
- **buttons** (row, bottom edge front): SW20,SW21,SW22,SW23 tactiles.
- IR + connectors handled as fixed/edge parts (below).

## Fixed / edge-locked constraints (LOCKED — from HARNESS Phase C gate; these win over the
design doc where they conflict, e.g. jack placement)
- **J20** audio jack — top-right, plug exits UP off the top edge.
- **J10** USB-C — bottom edge, plug down.
- **SW1** slide power switch — bottom-left corner.
- **U30** IR-RX — left edge, y=110.  **D20** IR-LED — right edge, y=110. Mirror-symmetric.
- **J31** microSD — on B.Cu, slot accessible from a board edge (back-center bottom).
- **J11** LiPo JST-PH — on B.Cu, near power zone, wire exit to an edge.
- **H1–H4** M2.5 mounting holes — already at the four corners; keep.

## Two approaches (the mission requires ≥2, scored, champion recorded)
- **A — constructive intent-driven** (B3): place fixed parts first; lay zones by the design
  intent + signal flow above (LEDs top, IR pair sides@110, audio upper-right→J20, power
  bottom→J10/J11, MCU center, buttons bottom, SAO free edge); pack each zone to fit its
  members' courtyard area + margin; emit artifact.
- **B — connectivity-driven partition** (B4): build the component graph weighted by shared
  nets (exclude GND/+3V3 power rails), run a balanced min-cut / spectral partition into the
  same number of zones, then assign each partition to a board region by matching its fixed
  anchors (the partition containing J10 → bottom, containing J20 → top-right, etc.).
  This lets connectivity, not just intuition, decide grouping.

## Scoring metric (how the champion is chosen)
For each emitted plan compute: (1) `est_ratsnest_mm` = MST over component zone-centroids
(GND excluded), lower is better; (2) hard-constraint violations (must be 0 to be eligible);
(3) zone capacity overflow (Σ member courtyard area vs zone area), lower better;
(4) signal-flow adjacency score (are chained subsystems in adjacent zones). Champion =
0 violations, then lowest est_ratsnest, then best capacity/adjacency. Record `CHAMPION:` in
LEDGER and write the winning plan to `floorplan.json`.

## Validation (Phase B exit gate — must all hold on the emitted plan)
- every movable component appears in exactly one zone (no missing, no double);
- all zone bboxes lie fully inside Edge.Cuts; zones don't overlap beyond a small slack;
- fixed/edge parts present at required positions/edges/layer;
- functional grouping matches the design-intent subsystems above;
- signal-flow ordering respected (power chain monotonic toward J10; audio toward J20).
- tool documented as a skill; ≥2 approaches scored; champion recorded.
