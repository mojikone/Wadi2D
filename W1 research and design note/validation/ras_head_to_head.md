# HEC-RAS head-to-head, decision 12 (2026-11-01)

**Verdict: HEC-RAS 6.6 can be built and run from text with no GUI, and nothing is blocked. On a 3 x 3 km Block 2 fan window at 10 m, Wadi2D matches RAS SWE-EM to +2.6 cm on max level (rms 5.5 cm), F 0.94 on extent, 0.2 % on peak discharge and about 1 min on timing. The solve is about 33 x faster wall to wall than RAS's best core count. This is one easy case: confined, friction-driven, no structures. It does not close decision 12.**

Every figure names HEC-RAS 6.6 (September 2024). All Wadi2D numbers come from frozen commit `3f32ca6`. [Certain] applies to everything measured here; inference is tagged where it appears.

## What this does not prove

- **Peak discharge is weak evidence.** The flood loses about 2 % across the window in both models, so a match within 0.2 % is mostly conservation of the inflow. Level, extent and wave timing are the tests that discriminate.
- **Not tested:** crest lines and dam objects, overtopping, hydraulic jumps, rain on grid, deep ponding, any observed event. Only one hydrograph was run.
- **RAS is a reference here, not the truth.** Its own results move 5.6 cm in level between 20 m and 10 m.
- **The inlet is not independent.** Wadi2D's inflow shares along the west edge are copied from RAS's distribution, so the two models start from the same spread. Wadi2D also has no inflow momentum.
- **The outlets differ in type.** RAS uses normal depth on perimeter faces; Wadi2D uses prescribed-level boundary cells inside the edge. Level differences show near the east outlet.

## Driving RAS with no GUI: it works

| Step | Command or file | Result |
|---|---|---|
| Terrain | `RasProcess.exe CreateTerrain units=Meter stitch=false prj=... out=Terrain.hdf input.tif` | 10 s for 37 M pixels |
| Project | Text only: `.prj`, `.g01` (perimeter, seed points, BC lines, `Storage Area Mannings`), `.u01`, `.p01`, `.rasmap` naming the terrain | Written by `build_ras_project.py`; no `.g01.hdf` needed beforehand |
| Run | `Ras.exe -c Fan.prj Fan.p01` | Compiles the geometry, builds the mesh from the seeds, builds the tables, runs the preprocessor and solver |

Checks that this was not a false success: 22,500 and 90,000 cells, every one exactly 400 or 100 m2, faces exactly 20 or 10 m, centres on the lattice to under 1 mm, `Terrain Filename` recorded, inflow volume 2,763.06 against 2,763.00 thousand m3, `Unsteady Finished Successfully`. `run_all.py --dx 20 --equation 2` reproduced the 20 m comparison exactly: 25,180 steps, identical numbers apart from timing.

Grammar facts not in N03: `UNET D2 Equation` is 0 DWE, 1 SWE-ELM, 2 SWE-EM. `HDF Additional Output Variable=Face Flow` and `=Cell Velocity` add those outputs. Reference lines lying exactly on lattice faces report zero flow, so section flows here are summed from `Face Flow`. The plan and flow templates in `ras_common` were copied from a Majlas model and carry generic defaults only.

## The case

Window 436,999.99-439,999.99 E, 2,725,999.89-2,728,999.89 N, the braided wadi across the fan. Terrain is a 0.5 m clip of `GGC_2_MERGE_HDSM.tif`, used by both models. Manning 0.04 and square cells of 20 and 10 m on the same lattice. Bed slope is about 1.6 %. Inflow is 5 to 300 m3/s at 1.5 h and back to 5 at 5 h, on a 500 m line on the west edge, for 6 h. Normal depth (S 0.015) on the east and north edges; walls on the other two. RAS: Courant control on, maximum 1.0. Wadi2D: defaults, `tables.rows` 16.

## Sub-grid tables

| Residual | 20 m | 10 m |
|---|---|---|
| Wadi2D cell table minus the pixels, mean depth, mean (rms) | 0.14 (0.74) mm | 0.07 (0.35) mm |
| RAS cell volume minus Wadi2D, mean depth, mean (rms) | +7.3 (11.9) mm | +4.0 (6.7) mm |
| Same, relative, above 5 cm mean depth, mean (p5 to p95) | +3.2 % (0.6 to 8.1) | +2.8 % (0.6 to 6.8) |
| RAS cell minimum minus pixel minimum, mean (rms) | -30 (50) mm | -33 (53) mm |
| RAS face invert minus Wadi2D, mean (rms) | -33 (53) mm | -34 (54) mm |
| RAS face area minus Wadi2D, as mean depth, mean (rms) | +4.8 (14) mm | +6.3 (16) mm |
| Wadi2D K / RAS K, median, faces 1-2 m deep | 1.15 | 1.18 |

**Wadi2D's 16-row cell table holds its pixels to under a millimetre.** The differences from RAS are sampling rules, not errors:

- **N03 open issue 1 is closed for faces.** RAS reads the terrain by bilinear interpolation between pixel centres, at half-pixel spacing along the face. On 3,000 faces at 20 m this rule gives the invert with rms 0.00 mm, and on 2,500 faces the whole area table with rms 0.86 mm of mean depth, perimeter rms 0.30 m. Cell minima follow the same rule (98.9 % exact, rms 0.44 mm).
- **Wadi2D takes the higher of the two pixels along a face**, by design, so a one-pixel ridge counts. That is why its inverts sit 33 mm higher.
- **RAS rounds its terrain to 1/32 m** (rms 9 mm against the source).
- **RAS's cell volume is not fully explained.** It exceeds the pixel integral at almost every level (p1 0 mm at 20 m). No rule tried closes it; a one-sided integration across elevation bins is the likely cause [Guessing].
- **The K ratio is strip integration against RAS's single section.** A (A/W)^(2/3) / n reproduces RAS's K to a ratio of 0.999, so the gap is not wetted-perimeter length.

## Results

| Wadi2D against RAS | SWE-EM 20 m | SWE-ELM 20 m | SWE-EM 10 m | SWE-ELM 10 m |
|---|---|---|---|---|
| Max level, cells over 0.5 m: mean (rms), cm | +7.4 (11.4) | +5.5 (10.0) | **+2.6 (5.5)** | +1.2 (5.3) |
| Same, p5 to p95, cm | -2.8 to +21 | -4.3 to +19 | -2.8 to +7.9 | -4.7 to +6.5 |
| F, 0.5 m pixels, depth >= 0.1 m | 0.890 | 0.893 | **0.936** | 0.940 |
| F, cells, depth >= 0.1 / 0.3 / 1.0 m | 0.96 / 0.92 / 0.84 | 0.96 / 0.91 / 0.87 | 0.96 / 0.94 / 0.94 | 0.95 / 0.94 / 0.94 |
| Wet area, RAS and Wadi2D, km2 | 0.739, 0.810 | 0.738, 0.810 | 0.737, 0.772 | 0.736, 0.772 |
| Peak Q at the three sections, % | 0, -0.09, -0.31 | +0.12, +0.05, -0.07 | +0.20, -0.03, -0.06 | +0.28, +0.01, +0.07 |
| Half-rise time at the three sections, min late | 0.6, 1.6, 1.8 | 0.4, 1.3, 1.5 | 0.3, 0.9, 0.7 | 0.2, 0.5, 0.4 |
| Hydrograph NSE, lowest section | 0.992 | 0.994 | 0.996 | 0.997 |
| Arrival of 0.1 m: median (p5 to p95), min | +4.1 (-12 to +10) | +3.4 (-15 to +9) | +1.9 (-11 to +7) | +1.1 (-14 to +6) |
| Max speed, cells over 0.5 m: bias (rms), m/s | 0.00 (0.20) | +0.07 (0.20) | 0.00 (0.18) | +0.05 (0.18) |
| Mean max speed, RAS and Wadi2D, m/s | 1.98, 1.97 | 1.90, 1.97 | 2.10, 2.10 | 2.04, 2.09 |

Peak time agrees within 1 min at every section (RAS sampled at 5 min). Arrival is interpolated from RAS's 5 min output, and its wide tails sit in shallow side threads. Volume error: RAS 0.003-0.019 %, Wadi2D 0.00015 % and 0.00004 %. Figures: `ras_head_to_head\fig_10m_swe_em.png`, plus the same at 20 m and for SWE-ELM.

### How big is that difference?

| Pair, HEC-RAS 6.6 where RAS | Level change, mean (rms), cm | F |
|---|---|---|
| RAS 10 m, SWE-EM to SWE-ELM | +1.4 (3.4) | 0.977 |
| RAS 20 m, SWE-EM to SWE-ELM | +1.9 (4.2) | 0.972 |
| RAS 20 m SWE-EM, Courant step to fixed 1 s | 0.0 (under 0.1) | 1.000 |
| **RAS SWE-EM to Wadi2D, 10 m** | **+2.6 (5.5)** | **0.936** |
| RAS SWE-EM to Wadi2D, 20 m | +7.4 (11.4) | 0.890 |
| RAS SWE-EM, 20 m to 10 m | +5.6 (7.2) | 0.921 |
| Wadi2D, 20 m to 10 m | +1.0 (5.9) | 0.947 |

**At 10 m, Wadi2D sits about 1.6 x RAS's own solver-to-solver spread in level rms, and its extent gap is about 2.8 x.** That is close but not inside the spread.

### The level bias

Wadi2D stands higher than RAS, and its wet area is 4.8 % larger at 10 m, 9.6 % at 20 m. I did not find the cause. What the runs show:

- **It shrinks with cell size, and mostly because RAS moves.** RAS rises 5.6 cm from 20 m to 10 m; Wadi2D rises 1.0 cm. The sum of cell maxima of mean depth tells the same story: RAS +5.5 %, Wadi2D -1.2 %. Wadi2D is the more grid-stable of the two on this case; I have not shown why.
- **Not flow direction.** Binned by angle off the grid axis the bias is flat: +6.6, +7.5, +7.6 cm at 20 m and +2.5, +2.7, +2.6 cm at 10 m. The known diagonal-channel limit is not what shows here.
- **Not conveyance form.** Wadi2D run with RAS's single-section K, by editing a cached table, moved level by +0.8 cm at 20 m and +0.4 cm at 10 m, and peaks by under 0.25 %. N03 recommendation 2 asked to decide by comparison: **on this case the choice hardly matters**, and the strip form is slightly closer to RAS. The 15-20 % K gap sits mostly at levels the flood never reached on smooth faces [Likely].
- **Scale.** Manning 0.048 instead of 0.04 raises level by 7.4 cm and cuts speed by 10 %. So the 10 m bias is worth about a 7 % error in n [Likely, scaled from the 20 m run].
- **Candidate not tested:** Wadi2D's higher face inverts and smaller face areas, at higher-of-two against bilinear [Guessing].

## Run time

| Solve, 6 h simulated, wall | 20 m, 22,500 cells | 10 m, 90,000 cells |
|---|---|---|
| RAS SWE-EM, 8 cores | 1:21 | **8:42** |
| RAS SWE-EM, 16 cores | 1:46 | 10:55 |
| RAS SWE-EM, 32 threads | 2:50 | not run |
| RAS SWE-ELM, 16 cores | 2:28 | 10:25 |
| Wadi2D RTX 5080, process, warm cache | 8.6 s | 13.5 s |
| Wadi2D RTX 5080, solver loop | 6.4 s | 11.1 s |
| Wadi2D CPU backend, solver loop | 46 s | 117 s |

- **The 10 m ratio is 39 x wall to wall with a warm cache, 33 x with a cold one (15.7 s), against RAS's best core count.** The bigger ratios of loop time against RAS total are not like for like.
- **Same hardware class:** Wadi2D's CPU backend is about 4.4 x faster than RAS on the CPU, wall to wall at 10 m.
- **RAS gets slower beyond 8 cores on this size.** The answers do not change: 16 and 8 cores differ by under 0.1 mm in level at 10 m.
- **The advantage grows with the model.** Four times the cells costs Wadi2D 1.6-1.7 x and RAS 6.4 x.
- **These are not clean benchmarks.** Other work was running on this machine throughout, and the GPU was already 28-62 % busy when Wadi2D started. Treat all times as upper bounds. On a quieter moment, a later working tree solved 10 m in 7.9 s.

## A defect found in the frozen commit

**A flow table was applied as the mean of each interval.** `Injection.mean_flow` in `3f32ca6` interpolates cumulative volume linearly, so the 15 min table cut the 300 m3/s peak to 289.5 and put steps in the hydrograph. I worked around it with a 1 min table in the job. The uncommitted working tree already integrates the flow properly, but that fix was not part of this test. It matters to any lumped hydrograph on a coarse step.

## Provenance

The solver changed during this work: `3f32ca6` touched the kernels at about 01:07. My first runs mixed two codes, so I set them aside in `ras_head_to_head\superseded_before_freeze\` and reran everything from `git archive 3f32ca6`. The 10 m results were unchanged and the 20 m level bias stayed within 0.2 cm. `wadi2d/` was not edited and nothing was committed. A later working tree gave 25,190 steps against 25,180 at 20 m; its results were not compared.

Rerun: `run_all.py --dx 10 --equation 2`, with `--code` pointing at a checkout of `3f32ca6`. The default is the repo as it stands. RAS runs are skipped when their folder already holds results.

## Next

1. **A case with a structure:** a road embankment or a dam crest overtopped, where the crest faces and the sampling rule differ most. This is the case that could actually fail.
2. **RAS at 5 m overnight:** about an hour or more [Guessing, from 8:42 at 10 m], to show whether RAS keeps rising toward Wadi2D.
3. **Test the invert rule:** tables built with RAS's bilinear rule, to see whether the level bias follows.
