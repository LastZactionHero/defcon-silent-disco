# A Comprehensive Guide to PCB Layout & Component Placement: From Fundamentals to AI-Driven Methods

> Knowledge base for the autonomous placement loop. `placement_rules.md` is the
> cheap every-iteration distillation of Areas 1–2; this is the deep reference for
> when you are choosing or building an algorithm. Consult on demand.

## TL;DR
- PCB placement is a formally NP-hard spatial-optimization problem solved in practice
  by experience-based heuristics, by the same algorithm families as VLSI (simulated
  annealing, force-directed/analytical, partitioning), and increasingly by RL and LLM
  agents — but fully-autonomous PCB placement remains a frontier.
- For a KiCad agent the realistic architecture is a hybrid: encode the deterministic
  rules as constraints, optimize a wirelength+overlap+thermal objective with simulated
  annealing or force-directed methods, pre-place fixed/critical parts, and hand routing
  to an external engine (Freerouting) — mirroring Quilter.ai, DeepPCB, JITX.
- The strongest transferable theory is VLSI physical design (HPWL, legalization,
  floorplan representations) and operations research (QAP, 2D bin packing, constraint
  programming with no-overlap). All are intractable exactly → heuristic/metaheuristic/
  learning methods are the only practical path.

## AREA 1 — Beginner fundamentals
**Workflow:** schematic capture → netlist → footprint assignment (IPC-7351) → board
setup (outline, stackup, design rules) → placement → routing → DRC/ERC → fab output
(Gerbers, drill, pick-and-place). Start from the enclosure (it constrains size,
connector locations, heights).

**Floor-plan before placing:** a floorplan is a rough sketch allocating areas to
blocks of circuitry and connectors. Do functional zoning (analog/digital/power/RF)
*before* placing any component.

**Placement recipe (codifiable):** fixed/mechanical first (connectors at edges) →
large/critical ICs + heat sources → passives. Group by subsystem; arrange by signal
flow (input→output, left→right); consistent orientation; keep sensitive/high-speed
parts off the edges.

**Decoupling caps:** place close to IC power pins (≈1–2mm for high-speed), short/wide
or via-to-plane, mix of values (smallest closest). Nuance (Hubing et al.): with
closely-spaced planes, exact location matters far less — loop inductance dominates.

**Crystal:** close to MCU, short traces, load caps close, guard ring; keep noisy nets
≥5× trace width away (Microchip app notes).

**Power/regulator:** small high-current loops, datasheet caps, tight switch-node loop.

**Thermal:** place heat sources for dissipation (edge/airflow), don't cluster, keep off
sensitive parts.

**Rules & standards:** trace width←current, clearance←voltage. IPC-2221(C) generic;
IPC-2222 rigid; IPC-2223 flex; IPC-7351 land patterns (density levels Most/Nominal/Least,
courtyards, zero-orientation). Reliability Class 1/2/3.

**Ground/return:** classic 4-layer Sig-Gnd-Pwr-Sig; signal layers adjacent to a solid
plane; HF return flows under the trace; don't split planes under high-speed traces.

**Common beginner mistakes:** no floorplan; caps too far/shared; large loops; routing
over plane splits; ignoring enclosure; only 0.1µF everywhere; sensitive parts at edges.

## AREA 2 — Expert techniques
**Signal integrity (Bogatin):** "every signal has a return path"; every interconnect
is a transmission line; uniform impedance = good SI (controlled impedance ~50Ω single,
~100Ω diff). Length matching, tight diff pairs, termination. Rules of thumb: ~166ps/in,
loop L ≈ 10–25nH/in.

**Grounding/field model (Hartley, Beeker):** energy is in the field between trace and
plane, not the copper; control the field with tight signal-to-plane spacing. The
mixed-signal ground-split debate: usually DON'T split the ground plane — one continuous
plane, partition by placement/routing. Splits only for specific cases (low-freq audio,
galvanic isolation).

**Power integrity:** design PDN to keep impedance below target across frequency
(Bogatin FDTIM; plane capacitance ≈1nF/in²; cap ESR near target impedance; beware
anti-resonance from over-paralleling — Sandler).

**EMC/EMI (Ott, Johnson):** small return loops, stitching vias at layer transitions and
board edges, guard traces, analog/digital/RF partitioning.

**High-speed:** DDR byte-lane match + fly-by + termination; USB/Ethernet/PCIe diff
impedance + intra-pair skew + reference continuity.

**Stackup:** balance impedance, crosstalk, EMI (signal next to solid plane), cost.

**DFM/DFA:** consistent orientation, spacing, thermal reliefs, fiducials, courtyard
compliance, no shadowing in wave solder.

## AREA 3 — Standard placement algorithms
References: Sherwani, *Algorithms for VLSI Physical Design Automation*; Kahng, Lienig,
Markov & Hu, *VLSI Physical Design: From Graph Partitioning to Timing Closure* (2011).

**Wirelength models:** HPWL (half-perimeter of net bounding box — the cheap dominant
estimator; sum over nets); RSMT (Steiner, accurate, costly); clique/star for quadratic
form. Quadratic placers minimize squared wirelength (convex QP) then linearize
(Bound2Bound) toward HPWL.

**Partitioning / min-cut:** Kernighan-Lin (pairwise swaps), Fiduccia-Mattheyses
(single-cell moves, hypergraphs, gain buckets, linear/pass). Recursive bisection →
min-cut placement.

**Simulated annealing:** TimberWolf (Sechen & Sangiovanni-Vincentelli, 1985). Accept
worse moves w.p. e^(−ΔC/T); cooling schedule; cost = HPWL + overlap penalty. High
quality, slow. **This is the proven workhorse for PCB-scale problems.**

**Force-directed / analytical:** nets as springs (Hooke), solve Qx+d=0 by conjugate
gradient. Kraftwerk2 (hold/move force split, Bound2Bound). GORDIAN (QP + recursive
slicing). Modern nonlinear: ePlace/RePlAce (every cell a charge, density = electrostatic
potential via Poisson/FFT, Nesterov optimization) — SOTA for cells. GPU: DREAMPlace
(analytical placement as "NN training" in PyTorch, ~40× speedup).

**Floorplan representations (for placing macros/rectangles):** slicing trees /
normalized Polish (Wong-Liu); sequence pair; B*-tree; corner block list; TCG/O-tree/BSG.
Flexibility: general > compacted > mosaic > slicing. Relevant for placing connectors/
modules as rectangles.

**Legalization & detailed placement:** Abacus / Tetris snap to legal sites without
overlap; then local swaps reduce wirelength.

**Objectives beyond wirelength:** congestion, timing/slack, thermal, power (weighted sum).

**ASIC vs PCB:** ASIC = millions of tiny uniform cells, fixed rows, many routing layers.
PCB = tens–hundreds of heterogeneous fixed-shape parts with rotation, mechanical/thermal/
EMI constraints, double-sided, few layers → PCB placement ≈ floorplanning + side
constraints, NOT standard-cell placement.

## AREA 4 — State-of-the-art AI-driven design
**Google AlphaChip:** Mirhoseini/Goldie et al., Nature 2021; macro placement as RL,
GNN encoder for transfer, proxy reward (wirelength+congestion+density). Open-sourced as
Circuit Training. **Controversy:** Cheng/Kahng "The False Dawn" (arXiv 2306.09633) +
"Stronger Baselines" argue the comparison wasn't apples-to-apples (pre-training excluded
from runtime, more compute, didn't beat SA/RePlAce/commercial in independent tests).
Google disputes. → Treat RL superiority over tuned classical methods as unproven.

**GNNs:** encoders in RL placers; routability predictors (RoutePlacer); cell-cluster
guidance (PL-GNN).

**LLMs/agents for EDA:** mostly HDL/Verilog and analog layout (LLANA, LayoutCopilot).
PCB-specific: **PCBSchemaGen** — training-free LLM agent, datasheet knowledge graph →
SKiDL → KiCad schematic → KiCad PCB ready for routing (directly relevant to a KiCad
agent). **CircuitLM** — multi-agent NL→schematic, force-directed SVG layout. FanoutNet —
deep RL for PCB fanout.

**OpenROAD:** open autonomous RTL-GDSII flow (ASIC); hosts **SA-PCB**, an open C++
annealing PCB placer (HPWL cost, polygon overlap via Boost.Geometry, 45°/90°/free
rotation, auto initial temperature). **Closest open prior art to what we are building —
study it.**

**Autorouters:** **Freerouting** (Specctra DSN/SES, KiCad integration, CLI + beta Python
API) — the obvious routing backend, but weak on very dense boards (one anecdote: 4% of a
17.6k-pad backplane in 7h). GPU alternative OrthoRoute (Manhattan lattice + PathFinder,
A100). tscircuit CapacityMesh.

**Commercial AI EDA:** Synopsys DSO.ai, Cadence Cerebrus/JedAI (ASIC, RL-for-PPA).
**PCB-specific (most relevant):** Quilter.ai (physics-driven RL placement+routing, reads
schematic, parallel candidates with physics scorecard, hybrid: human pre-places ~20%;
limits <500 comps / <2000 pins / <20% density / <10 layers / <6GHz / <4A); DeepPCB
(cloud RL, ~1000 comps/2200 pins/8 layers); JITX (code-driven generator, "3× faster,
25% cheaper").

**Realistic for a small KiCad agent (us):** hybrid — (1) deterministic rule engine for
codifiable heuristics; (2) metaheuristic optimizer (SA proven in SA-PCB / force-directed
/ analytical) minimizing HPWL+overlap+thermal+constraint penalties; (3) optional RL/GNN
if data exists; (4) LLM agent for NL→netlist + orchestration; (5) Freerouting backend.
Full autonomy on dense/high-speed is not yet reliable; human-in-loop on critical nets is
SOTA. **For <100 heterogeneous components, SA or force-directed is the highest-expected-
value first approach; RL is a challenger to try only if those plateau below the gate.**

## AREA 5 — Adjacent fields that transfer
**VLSI physical design** — the parent; supplies everything in Area 3.

**Quadratic Assignment Problem (QAP)** — Koopmans-Beckmann 1957; assign n facilities to
n locations minimizing Σ flow×distance. The QAP is *literally the textbook model of
placing interconnected components on a PCB* (flow = connections, distance = inter-location
distance). NP-hard, inapproximable; solved by tabu/SA/GA/GRASP/ant-colony. → treat
components as facilities, grid positions as locations, netlist as flow.

**Facility layout planning** — place departments to minimize material flow = minimize
wirelength. CRAFT, pairwise exchange transfer directly.

**2D bin packing / rectangle packing** — the no-overlap rectangle problem. Jylänki
families: Shelf, Guillotine, Maximal-Rectangles (MAXRECTS: BL/BSSF/BLSF/BAF), Skyline.
Bottom-Left / Bottom-Left-Fill. Strongly NP-hard; guillotine has (3/2+ε) poly /
(1+ε) pseudo-poly approximations. → the no-overlap legalization + area layer; courtyards
are the rectangles.

**Constraint programming** — diffn / no-overlap-2D; OR-Tools **CP-SAT**
`add_no_overlap_2d` + `add_cumulative` (CDCL + integer reasoning). Great for hard logical
constraints (keep-outs, alignment, "cap within X mm of pin"), expensive for optimality.
Caveat: CP-SAT no_overlap_2d lacks enforcement literals → model multi-region as one strip.
→ use CP-SAT to enforce hard placement constraints while a metaheuristic handles the soft
wirelength objective.

**Force-directed graph drawing** — Fruchterman-Reingold, Kamada-Kawai; same physics as
force-directed placement.

**Optimization toolkit** — gradient/Nesterov (analytical), SA (TimberWolf/SA-PCB), GA
(Jakobs GA+BL; SA often beats GA on packing), MILP/QP (exact but small only).

**Path-planning / game AI** — negotiation-based routing (PathFinder), A*, MCTS (the
AlphaZero lineage behind AlphaChip), discretized free-space search.

## Recommended build path (for THIS loop)
- **Stage rules first** (placement order, connectors-at-edges, grouping, signal flow,
  decoupling proximity, IPC spacing) → reasonable placements for simple boards.
- **Add a metaheuristic** (SA per SA-PCB: HPWL cost, polygon overlap penalty, 90°/45°
  rotation, auto initial temperature) OR force-directed/analytical. CP-SAT for hard
  no-overlap legalization.
- **Compare ≥2 approaches** on the same board, keep the champion (target: beat naive
  HPWL by ≥20%; the prior hand-thrash run reached ~1395mm ratsnest — beat it).
- **RL/GNN only if simple methods plateau below the gate** and a board corpus exists;
  remember the AlphaChip caveat.
- **Keep human-in-loop affordance for critical nets** even if the run is autonomous.

## Caveats
- Provably intractable to solve exactly (QAP / bin-packing reductions). Every method is
  heuristic/approximate; there is no guaranteed-optimal placer.
- AlphaChip RL superiority is disputed — don't assume RL > tuned SA.
- PCB-specific *placement* literature is sparse (much "PCB placement" work is assembly
  pick-and-place sequencing, a different TSP-like problem). Real refs: Khoo & Ng 1998,
  the SOGA paper, Vassallo 2023 (RL, ~17–21% wirelength over SA), SA-PCB.
- Vendor performance numbers are marketing, not peer-reviewed — treat percentages with
  caution.
- The decoupling "place close" rule and the ground-split debate are genuinely nuanced;
  encode the context (stackup, package, frequency), don't apply as rigid universals.
