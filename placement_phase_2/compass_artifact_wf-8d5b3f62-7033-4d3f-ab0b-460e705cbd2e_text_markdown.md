# A Comprehensive Guide to PCB Layout & Component Placement: From Fundamentals to AI-Driven Methods

## TL;DR
- **PCB placement is a formally NP-hard spatial-optimization problem** that practitioners solve with experience-based heuristics and that EDA tools attack with the same algorithm families used in VLSI (simulated annealing, force-directed/analytical, partitioning) plus, increasingly, reinforcement learning and LLM agents — but mature, fully-autonomous PCB placement remains an unsolved frontier as of mid-2026.
- For a **KiCad-based AI agent**, the realistic architecture is a hybrid: encode the deterministic beginner/expert rules as constraints (decoupling-cap proximity, connectors-at-edges, functional grouping, signal flow), use a wirelength+overlap+thermal objective optimized by simulated annealing or force-directed methods (both proven on PCBs), pre-place fixed/critical parts, and hand routing to an external engine (Freerouting) — mirroring what Quilter.ai, DeepPCB, and JITX already do commercially.
- The strongest transferable theory comes from **VLSI physical design** (Kahng et al.'s textbook; HPWL, legalization, floorplan representations) and **operations research** (the Quadratic Assignment Problem, 2D bin packing, constraint programming with no-overlap constraints) — all of which model PCB placement and all of which are intractable exactly, confirming that heuristic/metaheuristic/learning methods are the only practical path.

---

## Key Findings

1. **The canonical workflow is universal and encodable.** Every authoritative source (Altium, Cadence, Sierra Circuits, KiCad practice) describes the same pipeline: schematic capture → netlist → footprint assignment → board outline/stackup/design-rules → component placement → routing → DRC/ERC → fabrication outputs (Gerbers). Placement is repeatedly called "the most critical step" because it dictates routability, signal integrity, and EMI.

2. **Placement order is a strong, codifiable heuristic:** fixed/mechanical parts (connectors at edges) first → large/critical ICs and heat generators → then passives (decoupling caps adjacent to power pins) → group by functional block → arrange by signal flow (input→output, left→right). This is a near-deterministic recipe an agent can follow.

3. **The decoupling-cap "place it close" rule is context-dependent**, not absolute — a subtlety an expert agent must capture: with closely-spaced power/ground planes the exact location matters far less than loop inductance (Hubing et al.).

4. **The formal algorithm stack is mature and well-documented:** partitioning (Kernighan-Lin, Fiduccia-Mattheyses), simulated annealing (TimberWolf), force-directed/quadratic (Kraftwerk2), and modern electrostatics-based analytical placement (ePlace/RePlAce, GPU-accelerated as DREAMPlace). All minimize HPWL subject to density/overlap.

5. **AI-driven placement is real but contested.** Google's AlphaChip (Nature 2021) RL placer is used in production TPUs, but its claims are disputed (Cheng/Kahng "False Dawn" critique). For PCBs specifically, RL works in research (Vassallo thesis: 17-21% wirelength improvement over simulated annealing) and in commercial tools (Quilter.ai, DeepPCB, JITX).

6. **Adjacent fields supply directly-applicable theory:** the QAP is literally the textbook model of placing interconnected components on a PCB; 2D bin packing supplies no-overlap placement heuristics; constraint programming (OR-Tools CP-SAT `no_overlap_2d`) gives a practical no-overlap engine.

---

## Details

### AREA 1 — Beginner Hardware Designer Fundamentals

**The standard workflow.** The PCB design flow, as documented by Altium, Cadence, and Sierra Circuits, proceeds: (1) **Schematic capture** — draw the circuit with component symbols and nets; (2) **Netlist generation** — the list of all electrical connections that become traces; (3) **Footprint assignment** — link each schematic symbol to a physical land pattern (per IPC-7351); (4) **Board setup** — outline, layer stackup, and design rules (trace width, clearance, via sizes); (5) **Component placement**; (6) **Routing**; (7) **DRC/ERC** — automated design-rule and electrical-rule checks; (8) **Fabrication output** — Gerbers, drill files, pick-and-place. Professional teams start by considering the **enclosure**, which constrains board size, connector locations, and component heights.

**Floor-planning before placing.** Sierra Circuits: "The first step in PCB layout design is to have a floorplan. A floorplan is a rough sketch that allocates general areas where blocks of circuitry and connectors are to be placed on the board." Functional zoning (analog, digital, power, RF) should be done *before* placing any component; jumping straight to placement raises routing, debug, and EMI costs later.

**Component placement fundamentals (the codifiable recipe):**
- **Fixed/mechanical components first.** Connectors (USB, HDMI, Ethernet, power) go at board edges at predefined locations to meet enclosure/assembly requirements.
- **Then large/critical devices** — heat-generating parts, transformers, main ICs — which determine power-distribution paths and thermal structure.
- **Then passives** — resistors, capacitors, inductors.
- **Group by subsystem/functional block** to reduce signal crossings; keep related parts together.
- **Arrange by signal flow** — input processing near input connectors, output drivers near output connectors, to keep I/O traces short.
- **Consistent orientation** (components only vertical/horizontal, aligned) to facilitate automated assembly/wave soldering.
- **Keep sensitive high-speed devices away from board edges** (different impedance characteristics, higher EMI) — place near center.

**Decoupling/bypass capacitor placement.** The standard rule: place decoupling capacitors as close as possible to IC power pins to minimize loop inductance and the high-frequency current-path length. Ideal distance is within roughly 1-2 mm of the power pin for high-speed ICs. Use short, wide traces or direct connection to power/ground planes via vias; multiple vias per pad reduce series inductance. Use a combination of values (e.g., 1 µF, 0.1 µF, 0.01 µF) to cover a broad frequency range, with the smallest value closest to the pin. **Nuance for an expert agent:** Altium and Hubing et al. ("Power bus decoupling on multilayer printed circuit boards," IEEE Trans. EMC) show that with closely-spaced power/ground planes the planes provide the low-inductance path and exact cap location becomes much less sensitive — so the "place close" rule applies most strongly to leaded/QFP packages and 2-layer boards without solid planes.

**Crystal/oscillator placement.** Place close to the MCU with short traces; keep load capacitors close; use a ground guard ring / ground pour and keep noisy signals (e.g., switching caps) away. Microchip's app notes recommend separating sensitive traces like a 32 kHz crystal from decoupling caps by at least five times the trace width.

**Power-supply/regulator layout.** Keep high-current loops small; place input/output caps per datasheet; for switching regulators, manage the switch-node loop and feedback path (Rick Hartley emphasizes proper grounding of the switch node).

**Thermal considerations.** Place heat-generating components (regulators, power processors) where dissipation is favored (board edge, airflow), avoid clustering them, and keep them away from temperature-sensitive parts.

**Design rules and standards.** Trace width is set by current capacity; clearance by voltage (creepage/clearance). **IPC-2221** is the umbrella generic standard (electrical clearance, conductor spacing tables, via requirements; current revision IPC-2221C, Dec 2023), with **IPC-2222** for rigid boards, **IPC-2223** for flex, and **IPC-7351** for SMD land patterns/footprints (three density levels: Most/A, Nominal/B, Least/C; defines courtyard clearances and a standardized Zero Component Orientation for pick-and-place). Product reliability classes: Class 1 (consumer), Class 2 (industrial/instruments), Class 3 (high-reliability/aerospace/medical).

**Ground planes & return paths (the most important beginner concept that's actually advanced).** A classic 4-layer stackup is Signal-Ground-Power-Signal; placing signal layers adjacent to a solid reference plane gives a low-impedance return path. High-frequency return current flows directly beneath the signal trace (path of least inductance). Avoid splitting reference planes under high-speed traces.

**Common beginner mistakes:** ignoring the floorplan; placing decoupling caps too far / sharing one cap across pins; large signal/return loops; routing high-speed traces over plane splits; not considering the enclosure; using only 0.1 µF caps everywhere; placing sensitive parts at the board edge.

### AREA 2 — Expert Hardware Designer Techniques

**Signal integrity (SI).** The foundational mental model comes from **Eric Bogatin** (*Signal and Power Integrity — Simplified*): "Forget the word ground. Every signal has a return path." Every interconnect is a transmission line with a signal and return path; a signal sees an instantaneous impedance at each step, and signal quality is best when impedance is uniform (controlled impedance). Key techniques: controlled-impedance routing (commonly 50 Ω single-ended, ~100 Ω differential — Bogatin explains 50 Ω emerges as the manufacturability/crosstalk/thickness compromise), length matching for parallel buses, tightly-coupled differential pairs, and termination to manage reflections. Bogatin's "rules of thumb" (e.g., signal speed ≈ 6 in/ns, ~166 ps/inch; loop inductance ≈ 10-25 nH/inch) let an engineer "put in the numbers" quickly.

**Rick Hartley's grounding/field model.** Hartley (PCB West, Robert Feranec interviews): energy travels in the electromagnetic field between the trace and its reference plane, not in the copper. The real cause of SI/EMI problems is the field; control it with tight signal-to-plane spacing and proper plane assignment. "It's all about the space" (Dan Beeker). Hartley's controversial-but-influential position on the **analog/digital ground-split debate**: in most mixed-signal boards you should *not* split the ground plane; instead use one continuous ground plane and partition by component placement and routing, because splits break return paths. (Splits are justified only in specific cases like sensitive low-frequency audio or galvanic isolation.)

**Power integrity (PI).** Design the Power Distribution Network (PDN) to keep impedance below a target across frequency. Bogatin's PDN method: target impedance, capacitor loop inductance (ESL), the role of plane capacitance (closely-spaced planes ≈ 1 nF/in² of natural decoupling), and the Frequency-Domain Target Impedance Method (FDTIM) for choosing capacitor values/quantities. Steve Sandler (Picotest): the capacitor's ESR should be near the target impedance to keep a flat impedance profile; over-paralleling can cause anti-resonances.

**EMC/EMI mitigation.** Return-path management (keep loops small), stitching vias near layer transitions and along board edges, guard traces, and partitioning of analog/digital/RF sections. Henry Ott (*Electromagnetic Compatibility Engineering*) and Howard Johnson (*High-Speed Digital Design: A Handbook of Black Magic*) are the canonical references.

**High-speed design.** DDR routing requires byte-lane length matching and fly-by topology with termination; USB/Ethernet/PCIe require differential-pair impedance control, intra-pair skew matching, and careful reference-plane continuity. Howard Johnson's work covers transmission-line effects, ringing, and termination.

**RF layout.** Controlled-impedance feedlines, grounded coplanar waveguide, via fencing, keep-out zones, and component-orientation sensitivity.

**Stackup design.** Experts choose layer count and dielectric thicknesses to balance impedance targets, crosstalk, EMI (signal layers adjacent to solid planes), and cost. Hartley notes the trend (IoT/automotive) toward fewer layers (1-4) while maintaining SI by tight co-planar field containment.

**DFM/DFA heuristics.** Consistent orientation, adequate inter-component spacing (e.g., ~0.5 mm for hand/selective soldering, tighter for reflow), thermal reliefs on plane connections, fiducials, courtyard compliance (IPC-7351), and avoiding tall components shadowing pads in wave soldering.

**Expert floor-planning mental model.** Experts reason about tradeoffs holistically — Bogatin's "whack-a-mole" warning: changing one feature (e.g., narrowing a trace for density) degrades another (resistance). They build "virtual prototypes" (rules of thumb → approximations → field solvers) before committing to fabrication.

### AREA 3 — Standard Algorithms for Hardware Placement

The authoritative textbook references are **Sherwani, *Algorithms for VLSI Physical Design Automation*** and **Kahng, Lienig, Markov & Hu, *VLSI Physical Design: From Graph Partitioning to Timing Closure* (Springer, 2011)** — the latter's chapters map exactly to the pipeline: partitioning (Ch. 2), floorplanning/chip planning (Ch. 3), global & detailed placement (Ch. 4).

**Wirelength estimation models** (the objective function core):
- **Half-Perimeter Wirelength (HPWL):** half the perimeter of the bounding box of all pins on a net — the dominant, linear, cheap estimator. Sum over all nets.
- **Rectilinear Steiner Minimum Tree (RSMT):** more accurate routed-length estimate, more expensive.
- **Clique / star net models** for converting multi-pin nets to quadratic form.
- Quadratic placers minimize sum of *squared* wirelength (a convex QP solvable in polynomial time), then need a "linearization" (e.g., Bound2Bound net model in Kraftwerk2) to approximate HPWL.

**Partitioning-based / min-cut placement:**
- **Kernighan-Lin (KL, 1970):** iteratively swaps pairs of nodes between two partitions to minimize cut edges; locks swapped nodes.
- **Fiduccia-Mattheyses (FM, 1982):** moves single cells (not pairs), supports unbalanced partitions and hypergraphs, uses a gain-bucket data structure for linear time per pass. Together "KLFM" underpins recursive min-cut placement (the chip is bisected recursively; cells assigned to minimize cut).

**Simulated annealing (SA) placement:**
- **TimberWolf** (Sechen & Sangiovanni-Vincentelli, IEEE JSSC 1985) is the classic SA placer. SA accepts cost-increasing moves with probability e^(−ΔC/T) to escape local minima, with a cooling schedule (initial temperature, decay α, freeze condition). Moves: cell swaps and displacements. Cost = HPWL + overlap/penalty terms. Reported 15-62% area savings over prior tools. Pros: handles arbitrary objectives, high quality; Cons: slow for large designs.

**Force-directed / analytical placement:**
- Models nets as springs (Hooke's law); the quadratic wirelength objective yields a system Qx + d = 0 solved with conjugate gradient. **Kraftwerk2** (Spindler et al., IEEE TCAD 2008) separates the spreading force into a "hold force" and "move force" and uses the Bound2Bound net model to accurately represent HPWL; converges to overlap-free placement. **GORDIAN** (Kleinhans et al., 1991) combines quadratic programming with recursive slicing.
- **Modern nonlinear analytical (electrostatics-based):** **ePlace / RePlAce** (Lu, Chen et al., ACM TODAES 2015) model every cell as a positive charge and density cost as the potential energy of an electrostatic system, coupling potential/field to density via Poisson's equation solved by FFT spectral methods, and minimize with **Nesterov's method** (faster than conjugate gradient). This family is the state-of-the-art for standard-cell/mixed-size placement.
- **GPU acceleration:** **DREAMPlace** (Lin et al., DAC 2019, NVIDIA/UT Austin) casts analytical placement as "training a neural network" in PyTorch, achieving ~40× speedup over RePlAce with no quality loss — a key insight for any modern placement engine.

**Floorplanning representations** (for placing macros/blocks):
- **Slicing trees / normalized Polish expressions** (Wong & Liu, 1986) — represent slicing floorplans (recursive guillotine cuts); least flexible but simplest.
- **Sequence Pair (SP)** (Murata et al.) — two permutations encode relative positions; represents general (non-slicing) floorplans; O(n²) packing.
- **B*-tree** (Chang et al.) — binary tree for compacted floorplans; fast.
- **Corner Block List (CBL)** — mosaic floorplans.
- **Transitive Closure Graph (TCG), O-tree, BSG** — other general/compacted representations.
Flexibility order: general > compacted > mosaic > slicing. These matter for PCB agents placing large modules/connectors as rectangles.

**Legalization & detailed placement:** After global placement (where cells may overlap and be treated as points), legalization snaps cells to legal rows/sites without overlap (e.g., **Abacus**, **Tetris** algorithms), then detailed placement does local swaps/shifts to further reduce wirelength.

**Objective functions** beyond wirelength: routing congestion, timing (critical-path delay/slack), thermal, and power. Multi-objective weighted sums are common.

**ASIC vs PCB differences (critical for the agent):** ASIC placement involves millions of tiny, mostly uniform standard cells in fixed rows with abundant routing layers; PCB placement involves tens-to-hundreds of *heterogeneous*, large, fixed-shape components with rotation, strict mechanical/thermal/EMI constraints, double-sided placement, and far fewer routing layers. PCB placement is therefore closer to *floorplanning* (placing rectangles) than to standard-cell placement, and mechanical/electrical side constraints dominate.

### AREA 4 — State-of-the-Art AI-Driven Hardware Design

**Google AlphaChip (RL chip placement).** Mirhoseini, Goldie et al., "A graph placement methodology for fast chip design," *Nature* 594:207-212 (2021), building on the 2020 preprint "Chip Placement with Deep Reinforcement Learning." It poses macro placement as an RL problem: an agent places nodes of a netlist on a canvas; a graph-neural-network encoder produces embeddings enabling transfer learning across chips; the objective is PPA (power, performance, area) via a proxy reward (wirelength + congestion + density). Per Google DeepMind's 2024 retrospective ("How AlphaChip transformed computer chip design"): "For the TPU v5e, AlphaChip placed 10 blocks and achieved a 3.2% reduction in wirelength compared to human experts... in... Trillium, AlphaChip placed 25 blocks and achieved a 6.2% reduction in wirelength." It was open-sourced as **Circuit Training**, with pretrained weights released under the name **AlphaChip** (2024 Nature addendum).

**The controversy (must be flagged for honesty).** Cheng, Kahng et al., "The False Dawn: Reevaluating Google's Reinforcement Learning for Chip Macro Placement" (arXiv 2306.09633) and the "Stronger Baselines" paper (Bae et al.) argue the comparisons weren't apples-to-apples: the reported ~6-hour runtime excluded pre-training (RL trained on 20 blocks, evaluated on 5), used more compute than baselines, and in independent tests AlphaChip did not beat simulated annealing, RePlAce (academic), or Cadence's commercial placer. Google disputes these critiques. Net assessment: RL placement is genuinely deployed but its superiority over tuned classical methods is unproven and contested.

**GNN approaches.** Graph neural networks are used both as the encoder in RL placers and as standalone predictors — e.g., **RouteGNN/RoutePlacer** predict routability for differentiable optimization; **PL-GNN** generates cell-cluster placement guidance for commercial placers.

**LLMs and agents for hardware/EDA.** A 2025 ACM survey ("A Survey of Research in Large Language Models for Electronic Design Automation") catalogs LLM use across the flow. Notable: most work targets HDL/Verilog generation and **analog** layout constraints (**LLANA** combines LLM + Bayesian optimization; **LayoutCopilot** is a multi-agent LLM system for interactive analog layout). For PCB specifically: **PCBSchemaGen** (arXiv 2602.00510) is described as "the first training-free framework for PCB schematic design," using an LLM agent that reads an IC-datasheet-derived knowledge graph, generates **SKiDL** code, produces a KiCad schematic, then a KiCad PCB layout file ready for routing — directly relevant to a KiCad agent. **CircuitLM** (arXiv 2601.04505) is a multi-agent framework generating circuit schematics from natural language with a five-stage pipeline (NER → retrieval → chain-of-thought reasoning → CircuitJSON generation → force-directed SVG layout). **FanoutNet** uses deep RL for PCB fanout automation.

**OpenROAD.** A DARPA-funded (IDEA program, Andreas Olofsson), Google-sponsored open-source project providing an autonomous "no-human-in-the-loop, 24-hour RTL-to-GDSII flow" for ASICs above ~12 nm, used in 600+ tapeouts. Tools share the OpenDB data model and LEF/DEF, scriptable via Tcl/Python. It includes RePlAce-family global placement. Relevant because it is the open reference for autonomous physical design and hosts **SA-PCB**, an open-source C++ annealing-based *PCB* placement tool (HPWL cost, arbitrary-polygon overlap via Boost.Geometry, 45°/90°/free rotation, automatic initial-temperature computation).

**Autorouters.** **Freerouting** (originally by Alfons Wirtz; now actively maintained) is the dominant open-source autorouter, integrated with KiCad via the Specctra DSN/SES interface, with a CLI and a beta public API (Python SDK) — the obvious routing backend for a KiCad agent. It is a push-and-shove/rip-up-and-retry router and struggles on very dense boards. OrthoRoute author Brian Benchoff documented that on a backplane of "sixteen connectors, with 1,100 pins on each connector... 17,600 individual pads, and 8,192 airwires," "I tried FreeRouting, the KiCad autorouter plugin, and it routed 4% of the traces in seven hours." His GPU-accelerated alternative **OrthoRoute** (Manhattan lattice + PathFinder negotiation-based algorithm, KiCad IPC plugin) routed that same board to completion (44,233 blind/buried vias, 68,975 track segments) "Routed on an 80GB A100 GPU, rented on vast.io... Total time to route this board to completion was 41 hours." tscircuit develops its own CapacityMesh autorouter.

**Commercial AI EDA tools.** **Synopsys DSO.ai** (launched 2020, "industry's first autonomous AI application for chip design") uses reinforcement learning to optimize PPA across RTL-to-GDSII. Per Synopsys's Feb 7, 2023 press release announcing the first 100 commercial tape-outs, customers report "more than 3x productivity increases, up to 25% lower total power and significant reduction in die size" (SK hynix's Junhyun Chun cites "a 15% cell area reduction and a 5% die shrink"). **Cadence Cerebrus** is the direct competitor (RL design-flow automation); per AnandTech's launch coverage, "the Cerebrus tool helped a single engineer in 10 days achieve a 3.5 GHz mobile CPU while also saving leakage power, total power, and improving transistor density" (versus roughly a dozen engineers over months). **Cadence JedAI** is the data platform and the broader **Cadence.AI** offers "agentic AI workflows." These target ASIC, not PCB, but their RL-for-PPA paradigm is the template.

**PCB-specific commercial AI placement (most relevant).** **Quilter.ai** uses "physics-driven AI" / reinforcement learning to automate both placement and routing, reading the schematic to understand circuit relationships, generating parallel candidate layouts each with a "physics scorecard," and supporting a hybrid workflow (human pre-places ~20% of critical parts, Quilter does ~80%); it imports Altium, Cadence, Siemens, and KiCad. Published limits: <500 components, <2000 pins, <20% density, <10 layers, <6 GHz, <4 A. **DeepPCB** (InstaDeep, now part of BioNTech) is a cloud RL tool (self-play in a C++ simulation engine; DeepPCB Pro launched Sept 2024) handling up to ~1,000 components / 2,200 pins / 8 layers on a pay-per-minute model. **JITX** (UC Berkeley spinout, CEO Duncan Haldane) is a code-driven ("hardware-as-software," language Stanza) generator; per IEEE Spectrum's profile ("Startup JITX Uses AI to Automate Complex Circuit Board Design"): "On average, JITX produces circuit boards three times as fast and 25 percent cheaper than experienced humans working unassisted."

**What's realistic for a small-scale KiCad agent.** Evidence points to a hybrid: (1) deterministic rule engine for the codifiable heuristics (placement order, decoupling proximity, connectors at edges, functional grouping); (2) a metaheuristic optimizer — simulated annealing (proven in SA-PCB and Vassallo's baseline) or force-directed/analytical placement — minimizing HPWL + overlap + thermal + constraint penalties; (3) optional RL/GNN to learn placement quality; (4) LLM agent (à la PCBSchemaGen/CircuitLM) for the natural-language-to-netlist and constraint-extraction front end and for orchestration; (5) Freerouting as the routing backend. Full autonomy on dense, high-speed boards is not yet reliable; human-in-the-loop on critical nets is the state of the art.

### AREA 5 — Adjacent Concepts From Other Fields

**VLSI/ASIC physical design (the parent discipline).** Already covered — supplies HPWL, partitioning, SA, analytical placement, floorplan representations, and legalization. The single richest transfer source.

**Quadratic Assignment Problem (QAP) — operations research / facility layout.** Introduced by Koopmans & Beckmann (1957), the QAP assigns n facilities to n locations to minimize the sum over facility pairs of (flow × distance). Wikipedia states the QAP "is a mathematical model for the problem of placement of interconnected electronic components onto a printed circuit board or on a microchip" — i.e., PCB placement is *literally* a QAP (flow = number of connections between components, distance = inter-location distance). The QAP is NP-hard and NP-hard to approximate within any constant factor (TSP is a special case). It is solved in practice by tabu search, simulated annealing, genetic algorithms, GRASP, and ant colony optimization (facility-layout literature reports ~20% improvements over manual layouts). **Mapping:** an agent can treat components as facilities, candidate grid positions as locations, and netlist connectivity as flow, then run a QAP metaheuristic.

**Facility layout planning.** The broader OR discipline of placing machines/departments to minimize material-flow cost — same structure as minimizing wirelength. Heuristics (CRAFT, pairwise exchange) transfer directly.

**2D bin packing / rectangle packing / cutting stock.** The no-overlap rectangle-placement problem. Jukka Jylänki's practical survey ("A Thousand Ways to Pack the Bin") classifies heuristics into four families: **Shelf** (rows), **Guillotine** (recursive edge-to-edge cuts), **Maximal Rectangles / MAXRECTS** (track all maximal free rectangles; variants BL, Best-Short-Side-Fit, Best-Long-Side-Fit, Best-Area-Fit; best for offline), and **Skyline** (track the packing frontier as horizontal segments; fastest, best for online). Foundational heuristics: **Bottom-Left** (Baker, Coffman & Rivest, 1980) and **Bottom-Left-Fill** (Hopper & Turton, 2001; efficient O(n²) implementation by Chazelle, 1983). The cutting-stock LP column-generation origin is Gilmore & Gomory (1961). **Complexity:** 2D strip packing is strongly NP-hard (reduces from 1D bin packing) with no poly-time (3/2−ε)-approximation unless P=NP; for guillotine strip packing, Khan et al. (ICALP 2022 / ACM TALG 2025) give a matching (3/2+ε) polynomial and a (1+ε) pseudo-polynomial approximation. **Mapping:** these supply the no-overlap legalization and area-minimization layer of a PCB placer; component courtyards are the rectangles.

**Constraint programming / constraint satisfaction.** The **diffn** global constraint enforces k-dimensional no-overlap (for any pair of boxes, some dimension separates them). Google **OR-Tools CP-SAT** provides `add_no_overlap_2d` (over 2D interval variables) and `add_cumulative`, combining SAT clause-learning (CDCL) with integer reasoning (lead developer Laurent Perron). Layout-as-CSP uses AllDifferent over locations (assignment), NoOverlap2D (non-overlap), and reified constraints for adjacency/separation (cf. Rossi, van Beek & Walsh, *Handbook of Constraint Programming*, 2006). CP is excellent for expressing logical/disjunctive constraints and strong propagation but expensive for optimality proofs and sensitive to symmetry. A practical caveat: CP-SAT's `no_overlap_2d` does not natively support optional/enforcement literals, so multi-bin 2D packing is often modeled as one wide strip. **Mapping:** CP-SAT can directly enforce hard placement constraints (no overlap, keep-outs, alignment, "this cap within X mm of this pin") while a metaheuristic handles the soft wirelength objective.

**Force-directed graph drawing.** Network-visualization layout (Fruchterman-Reingold, Kamada-Kawai) uses attractive forces along edges and repulsive forces between nodes — the same physics as force-directed placement, and a source of intuition/algorithms for spreading connected components.

**Optimization methods (cross-cutting).** Gradient descent / Nesterov's method (analytical placement), simulated annealing (TimberWolf, SA-PCB), genetic algorithms (Jakobs 1996 GA+Bottom-Left hybrid; Hopper & Turton 2001 found SA beat GA on most packing instances; PCB-specific: Khoo & Ng 1998, and the Self-Organizing Genetic Algorithm in *Journal of Intelligent Manufacturing* optimizing temperature/area/power/critical-distance), and integer/linear/quadratic programming (MILP with Benders decomposition for exact placement; quadratic placement as convex QP). All are heuristic/approximate because the underlying problems are intractable.

**Robotics/path-planning & game-AI spatial reasoning.** Negotiation-based routing (PathFinder, used in OrthoRoute) comes from FPGA routing but resembles multi-agent path planning. A* / grid search, Monte Carlo Tree Search (the AlphaGo/AlphaZero lineage that inspired AlphaChip), and discretized free-space search ("component-centric" PCB RL) all transfer to spatial placement reasoning.

---

## Recommendations

**For building a KiCad-based AI placement agent, in stages:**

1. **Stage 1 — Encode the deterministic rule layer.** Implement the placement-order recipe (fixed/mechanical → critical ICs/heat → passives), connectors-at-edges, functional grouping (parse the schematic into subsystem blocks), signal-flow orientation, and decoupling-cap-adjacent-to-power-pin. Use IPC-7351 courtyards for spacing and IPC-2221 clearances. This alone produces reasonable placements for simple boards. **Benchmark to advance:** clean DRC and routable by Freerouting on 2-layer boards <50 components.

2. **Stage 2 — Add a metaheuristic optimizer.** Implement simulated annealing (follow SA-PCB: HPWL cost, polygon overlap penalty, 90°/45° rotation, automatic initial temperature) or force-directed/analytical placement (Kraftwerk2-style). Add thermal and constraint-penalty terms to the objective. Use CP-SAT `no_overlap_2d` for hard no-overlap/keep-out legalization. **Benchmark:** match or beat hand placement on wirelength for boards up to ~100 components; Vassallo's RL work shows ~17-21% wirelength gains over plain SA are achievable as a stretch target.

3. **Stage 3 — Add the LLM agent front end and orchestration.** Adopt the PCBSchemaGen pattern (LLM + datasheet knowledge graph → SKiDL → KiCad) for natural-language intent capture and constraint extraction, and use the LLM to set optimizer weights and identify special nets (differential pairs, impedance-controlled, bypass caps) — mirroring Quilter.ai's schematic-reading approach.

4. **Stage 4 — Consider RL/GNN only if data exists.** RL placement (DQN/PPO/TD3, GNN encoders) is promising but data-hungry and unproven beyond research; the AlphaChip controversy is a caution. Pursue only with a corpus of real boards; otherwise the SA/analytical + rules hybrid is more robust.

5. **Always keep human-in-the-loop for critical nets.** The commercial state of the art (Quilter, DeepPCB, JITX) all assume a human pre-places ~20% of critical/high-speed parts. Build for that workflow.

**Thresholds that change the approach:** Below ~50 components and 2 layers → rules + SA suffice. Above ~500 components, dense (>20% utilization), or >6 GHz/high-speed → current automation (even commercial) is unreliable; require human pre-placement and constraint-driven SI handling. If you have a large labeled board dataset → RL/GNN becomes worth the investment.

## Caveats

- **PCB placement is provably intractable to solve exactly** (NP-hard via QAP/bin-packing reductions; "at least NP-Complete" per Vassallo). Every method here is heuristic, metaheuristic, or approximate — there is no guaranteed-optimal placer.
- **The AlphaChip results are genuinely disputed.** Google reports production use and superhuman results; Cheng/Kahng et al. argue the evaluation was not apples-to-apples and that classical methods match it. Treat RL superiority claims as unproven.
- **PCB-specific automated *placement* research is sparse** compared to ASIC; much of the "PCB component placement" literature is actually pick-and-place *assembly sequencing* (a TSP-like machine-path problem, e.g., Ho & Ji 2005/2006), not spatial layout. The genuinely relevant PCB placement papers are few (Khoo & Ng 1998; the SOGA paper; Vassallo 2023; recent RL preprints).
- **Commercial-tool performance claims** (Quilter, DeepPCB, JITX, DSO.ai, Cerebrus) come largely from vendor press releases, marketing, and customer testimonials, not independent peer-reviewed benchmarks; treat specific percentages with appropriate caution.
- **Some sources are vendor blogs** (Sierra Circuits, Altium, Cadence, PCBWay); their engineering guidance is generally sound and corroborated across sources, but they are not peer-reviewed.
- **The decoupling "place close" rule and the ground-split debate are genuinely nuanced**; an agent that applies them as rigid universal rules will sometimes be wrong. Capture the context (stackup, package type, frequency).
- Several arXiv IDs cited (e.g., PCBSchemaGen 2602.00510, CircuitLM 2601.04505) carry 2026 listing numbers consistent with the current date; as preprints they are not yet peer-reviewed.