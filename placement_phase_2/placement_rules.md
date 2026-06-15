# Placement rules — codified checklist (READ EVERY ITERATION)

Condensed from `docs/placement_research.md` (Areas 1–2). These are the heuristics
your tools should *encode* and your placements should *satisfy*. Distances are
starting points; this board's design intent (`badge_hw_design.md`) and the IPC
tables win wherever they conflict.

## Order of placement
1. **Fixed / mechanical first** — connectors at board edges, mounting holes at
   corners, anything with an enclosure or edge constraint.
2. **Large / critical ICs and heat sources next** — they define the power and
   thermal structure of the board.
3. **Passives last, attached to their owner** — decoupling caps to IC power pins,
   load caps to the crystal, feedback resistors to the amp.

## Grouping & signal flow
- Group by functional subsystem; keep a subsystem's parts in one contiguous zone.
- Arrange zones by signal flow: input near input connectors, output near output
  connectors, keep I/O traces short.
- Consistent component orientation (axis-aligned) for assembly.
- Keep sensitive / high-speed parts away from board edges (bias toward center).

## Decoupling / bypass
- One bypass cap per IC power pin, placed adjacent, smallest value closest to pin.
- Minimize the cap→pin→via loop; short wide connections or direct via-to-plane.
- Nuance: with tightly-spaced power/ground planes the exact cap location matters
  far less — loop inductance is the real target, not raw distance.

## Crystal / oscillator
- Adjacent to the MCU, short symmetric traces, load caps close, ground guard/pour,
  keep switching/noisy nets at least ~5× trace width away.

## Power / thermal
- Keep high-current loops small; place input/output caps per datasheet; keep the
  switch-node loop tight.
- Spread heat sources; keep them off temperature-sensitive parts; favor edges/airflow.

## Ground / return path (placement implications)
- Assume a solid reference plane; do not create placements that force routing over
  a plane split.
- Mixed-signal: prefer one continuous ground, partition by *placement* (analog /
  digital / RF zones), not by splitting the plane.

## Spacing / DFM
- Honor IPC-7351 courtyards (zero overlaps) and IPC-2221 clearances.
- Leave assembly clearance; fiducials present; no tall parts shadowing pads.

## THIS BOARD'S FIXED CONSTRAINTS (do not violate; pull details from badge_hw_design.md)
- **Edge.Cuts**: ~86×54mm sawtooth-edge outline (origin roughly x 100–188, y 80–134).
  **DO NOT change the outline** — it is considered final.
- **J20** audio jack: top-right, plug exits up off the top edge.
- **J10** USB-C: bottom edge, plug down.
- **SW1** power switch: bottom-left corner.
- **U30** IR-RX: left edge at y=110.  **D20** IR-LED: right edge at y=110.
  Mirror-symmetric for board-to-board pairing — keep both at y=110.
- **J31** microSD: on B.Cu, slot accessible from a board edge.
- **4× M2.5** mounting holes at the corners.
- Subsystems: MCU (U3) + flash (U2) + 12MHz xtal (Y1) + decoupling ring;
  Power chain USB-C→TP4056 (U10)→LiPo (J11)→switch (SW1)→LDO (U11)→+3V3;
  4× SK9822 LEDs across the top; Audio TM8211 (U20)→FDA1308 (U21)→coupling→J20;
  IR (U30/D20); 3× buttons; SAO / Dev-SWD / UART connectors.
