# Wadi2D: how fast and how accurate, as of 2026-11-08

**Fast, yes: tens of times HEC-RAS on the same ground. Accurate against other models and analytic cases, yes; against a
real flood it is barely tested, and the aligned mesh is not yet accurate at 20 m in narrow gorges.**

All on the RTX 5080 unless said. Numbers from the project record (`CLAUDE.md`, W1 to W48); the Faydh race rows are the
option A kernels (`feature/face-depth-carry`, not merged), which move every peak by 1 to 3 % from `main`.

## Speed

| Case | Cells | Simulated | Wall time | Note |
|---|---|---|---|---|
| Kernel throughput | | | 0.6 ns per cell-step, 2.2 to 2.9 G cell-updates/s | [Certain, measured] |
| A 3 x 3 km fan at 10 m, against HEC-RAS 6.6 on the same window | | | 13.5 s against 8 min 42 s | **39 x** [Certain] |
| Block 2, 599 km², 20 m | 2.0 M | 48 h | 8.9 min | [Certain] |
| Block 2, 10 m | 8.1 M | 36 h | 42 min; 26 min with the quadtree and local stepping (1.6 x) | [Certain] |
| The full project boundary, 15,398 km², 30 m | 17.1 M | 200-yr storm | 68 min | [Certain] |
| Faydh 01, 74 km², 16 h, 20 m squares | | 16 h | 13 s loop + 14 s tables | [Certain] |
| The same, 10 m / 5 m squares | | 16 h | 72 s / 490 s loop | [Certain] |
| The same, aligned centre mesh 20 m / 10 m | | 16 h | 35 s / 107 s loop, + 55 / 71 s to build the mesh | 2.6 x and 1.5 x the squares of the same size [Certain] |
| The same, W45 ring corridors 20 m | | 16 h | 59 s loop | [Certain] |
| CPU twin, no GPU (Faydh with corridors) | | 16 h | 22 min against 72 s on the GPU | about 18 x slower [Certain] |

[Certain] Mass closes to about 1e-8 of the volume in every run.

## Accuracy

| Test | Result | Rule | Standing |
|---|---|---|---|
| Still water on steep ground | exact by construction | | [Certain] |
| Ritter dam break, depth RMSE | 0.0085 m | 0.01 m | pass [Certain] |
| MacDonald subcritical / supercritical / jump, depth RMSE | 0.010 / 0.0105 / 0.032 m | 0.015 / 0.012 / 0.05 | pass [Certain] |
| Uniform flow on a 1 % slope, 20 m cells | 1.002 of normal depth (0.966 on `main`) | 1.5 % | pass on option A [Certain] |
| Straight channel, 3 cells wide, 0 / 45 degrees, squares | 1.004 / 1.039 of normal depth | 3 % | 45 degrees over the rule, not gated [Certain] |
| HEC-HMS replication, all lumped (Block 2) | within 0.002 % | | code check, not validation [Certain] |
| Hybrid, lumped hills and 2D plain, five dams | within 3 % of HMS | | [Certain] |
| Against HEC-RAS 2D, Bidah rain-on-grid at 10 m | 622.0 against 621.9 m³/s | | [Certain] two models agreeing |
| Against HEC-RAS 2D, Faydh 01 at 10 m | 1,873.8 against 1,872.2 m³/s | | [Certain] |
| Against HEC-RAS 2D, a fan window | water levels within 2.6 cm | | [Certain] |
| Cell-size convergence, Faydh dam axis, squares 20 / 10 m against 5 m | -4.3 / -1.5 % | 3 % | 10 m passes, 20 m does not [Certain] |
| The same, aligned centre mesh 20 / 10 m | +4.6 / +1.7 % | 3 % | 10 m passes, 20 m does not [Certain] |
| The same, W45 ring corridors 20 m | -0.6 % | 3 % | pass [Certain] |
| An observed flood: Cyclone Shaheen at Lihban, 197.5 km², volume imposed | 0.96 of the observed peak under a phi loss | | one event, nothing tuned [Certain] |
| A design flood against a gauge: Fizh, 100-yr | 2,582 against a report Q100 of 770 m³/s | | 3.4 x; the storm or the losses look too large for this ground, in HMS too (2.2 x) [Likely] |

## What this means

- [Certain] **The solver is right where an answer is known** (analytic cases, mass, uniform flow) and agrees with HEC-RAS
  to a fraction of a per cent on the same ground at 10 m.
- [Certain] **Cell size governs accuracy on steep wadis**: 10 m is within 2 % of the converged peak on Faydh for squares
  and aligned cells alike; 20 m is 4 to 5 % off either way.
- [Certain] **The aligned mesh at 20 m is not yet trustworthy in narrow gorges.** Where a gorge is narrower than two
  cells and bends, the strip has only two cells across at any size and stands about 0.2 to 0.3 m low; the hunt is in
  W48, a 5 m strip and a gentler bend running. Use it at 10 m until then.
- [Likely] **Accuracy against real floods is the open question**, and it is the inputs (storm, losses), not the solver,
  that the one design-flood comparison points at. Block 2 has no event with rain and flow together.
