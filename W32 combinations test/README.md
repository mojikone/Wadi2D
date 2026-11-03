# W32 combinations test

**Status (2026-11-02, `test/combinations` cut from local `main` at `a783afc`): 4 of 6 pass. Items 2, 3, 5 and 6 pass their rules. Item 1 passes on Bidah ground, where the CPU twin gives the GPU's numbers step for step, and fails on the Block 2 hybrid, where the two backends diverge deterministically (101,432 against 101,421 steps; Faydh 01 -2.5 % at the peak). Item 4 passes W25's 1e-3 and fails the brief's last-digit rule: a resumed run re-phases its series by 30 s. Nothing fixed, by the brief.**

The nine items of the work order were each tested alone through the real dock (`W28`); this folder runs the combinations nobody ran: the CPU twin through the new sections, and a generated basin (D6) with a gridded storm (D5), with the mesh (D3), with a resume, on the full extent, and the hand-back at a dam through crest faces. A testing iteration: no engine or plugin code changed; a fault is recorded with its evidence, not fixed. Every dock scenario ran in a throwaway QGIS 3.44.8 with a throwaway profile through `tests/dock/run_check.ps1`, the plugin and the engine from this checkout; every engine-side item ran `wadi2d` from this checkout on the project venv. **The card was shared with other agents throughout, so every time here is "took about" and none is a finding.** Read-only on his Block 2 files; the only thing written outside this worktree and the scratchpad is one grid-cache entry beside W12's (item 5).

| Item | What was combined | Result |
|---|---|---|
| 1 | CPU engine through the Storm, Mesh controls, Result lines and generated-basin sections of the dock | **Pass on Bidah, fail on the Block 2 hybrid.** 253 of 253 checks on the CPU across the four scenarios (storm 51 of 52 on both backends, the one failure the scenario's own 80 m rule); on Bidah ground every run matches the GPU step for step and peak for peak at six digits; on the Block 2 hybrid at 80 m the backends diverge: 101,421 against 101,432 steps, Faydh 01 493.7 against 506.6 m3/s, rings up to 23 %, each backend repeating itself to the digit |
| 2 | Generated basin with a gridded storm (288 GeoTIFF frames), Bidah | **Pass**, 24 of 24: hills 3,600,902.79 against 3,600,902.79 m3, grid 996,681.19 against 996,681.19 m3, reservoir inflow peak 463.3 m3/s in both; rain-once silent |
| 3 | Generated basin with the quadtree mesh, 10 to 40 m | **Pass at the dam** on the 2.4 % rule: `above` line -0.26 %, reservoir outflow -1.1 %; the hand-back crossings at J2 to J4 read 2.7 to 3.1 % low, W23's known behaviour on sections |
| 4 | Generated basin with a stop and a resume | **Fails the last-digit rule, passes W25's**: every balance field within 1e-3 (hand-back 3,251,468.13 against 3,251,467.84 m3), but the line and point series re-phase by 30 s after the checkpoint and the network series differ by up to 0.0024 m3/s |
| 5 | Generated basin on the full extent, 15,398 km2 at 30 m | **Pass**: refused at 5 m and 10 m in words (the guard counts the bounding box, 1.85 G and 463 M pixels against 400 M); at 15 m 844 subbasins, 381 reaches, 467 junctions in about 167 s, 9 subbasins refused into rain-on-grid by name; the run on 17,108,508 cells started, reached 11.3 h of 36 in the 10 min allowed, books closing (grid 1.4e-8, whole -3.6e-4) |
| 6 | Hand-back at the dam against the same flood through the crest faces | **Pass**, second attempt 15 of 15: rated lumped pool 262.6 m3/s at 12.92 h, crest faces on the grid 258.7 at 12.91 h (-1.5 %), W8 embankment 255.4 (-2.7 %); spilled 3.25, 3.14, 3.24 Mm3; every book closes. The first attempt exposed two things the owner should know (below) |

## 1. The CPU engine through the new sections

**How the CPU was forced.** The dock has no backend choice: `run.backend` stays `auto` and `select_backend` takes the GPU whenever CuPy sees a device (`wadi2d/solver/backend.py`). W16 forced the CPU by installing an engine without CuPy. Here `scripts/run_dock.ps1` sets `CUDA_VISIBLE_DEVICES=-1` in the environment that starts the throwaway QGIS; the plugin's `engine_environment()` hands it to the engine, CuPy's `getDeviceCount()` raises `cudaErrorNoDevice`, and `auto` falls to the Numba twin. Each scenario checks the backend the engine wrote in its own `start` event after every run (`W32 <run>: ran on the cpu`), and writes every series peak of every run, unrounded, to `w32_numbers.json`; the same scenario then ran on the GPU and `scripts/compare_backends.py` set the two side by side (`results/item1_backends.json`).

**What changed against the original scenarios** (`scripts/dock_*_w32.py` are W20, W23, W21 and W27's scenarios with these edits, made by a patch script, and nothing else): the helper import and the backend check; harness limits raised to 100 min; and the Block 2 part of the storm scenario at **80 m, not 40 m**, because the CPU twin is about 31 x slower on this ground (`results/speed_probe.json`: loop 21.7 s against 0.69 s on 71,934 cells, 3,793 steps, both backends the same peak 0.681818 m3/s) and the HMS control file fixes 48 h for those two runs.

| Scenario | GPU checks | CPU checks | Runs | Cells, steps (same on both) | Loop, GPU / CPU, about | Peaks GPU against CPU | Balance volumes |
|---|---|---|---|---|---|---|---|
| `dock_basin_bidah_w32` (W27, D6) | 55 of 55 | 55 of 55 | 3 | 71,934; 8,124 / 8,124 / 3,143 | 2.5 / 30.6 s; 3.1 / 31.0; 1.2 / 22.5 | equal at every series' six digits (36 peaks) | equal to the ninth digit: hand-back 58,385.78717 against 58,385.78591 m3, storage 98,863.5202 against 98,863.5200 |
| `dock_mesh_controls_w32` (W23, D3) | 70 of 70 | 70 of 70 | 3 | 119,628 / 43,995 / 71,934; 1,385 / 1,105 / 182 | 2.1 / 30.7; 0.9 / 24.0; 0.2 / 13.3 s | equal | rain equal; outflow 9,003.5147 against 9,003.5140 m3 |
| `dock_result_lines_w32` (W21, D9) | 77 of 77 | 77 of 77 | 4 | 71,934 (three), 106,864 on the mesh; 6,687 / 2,986 / 65 / 9,449 | 2.9 / 36.5; 1.0 / 22.9; 0.2 / 12.8; 8.5 / 97.6 s | equal: Across 316.36, Axis 326.03, Oblique 324.405 m3/s on both; frame ratios 0.936 / 1.004 / 0.937 on the CPU, 0.94 / 1.01 / 0.94 in W21 | outflow 1,242,390.87 against 1,242,390.79 m3 |
| `dock_storm_w32` (W20, D5) | 51 of 52 | 51 of 52 | 11 | Bidah at 40 m, every run the same steps on both; Block 2 at 80 m: 126,531 cells, **101,432 steps on the GPU, 101,421 on the CPU** (frames run 101,440 against 101,433) | Bidah runs about 0.2 to 2 s against 10 to 30 s; Block 2 56 / 508 s and 63 / 529 s | Bidah runs equal; **Block 2 differs: Faydh_01 506.6 against 493.7 m3/s (-2.5 %), Z4C 1,674.2 against 1,673.1, R2A 1,118.5 against 1,118.4, R5A 788.7 against 790.3; the rings Bidah_03_ring 55.6 against 42.7, S6_ring 7.9 against 9.5** | hills 84,501,544.013 m3 on both backends and both storms; plain 35,462,131.42 against 35,462,131.35 m3 |

[Certain, measured] The CPU twin gives the GPU's numbers through every new section: the same step count in every run, every peak equal at the six significant digits the series CSVs hold, the balance volumes apart only in the ninth digit, which is the threaded sum W23 and W25 recorded. The pixel products, the mesh, the hand-back lines, the lumped network and the result-lines reader all ran on the CPU path through the dock.

**The one failed check is the scenario's own 80 m, not the combination.** On the GPU, "every steady line as the HMS storm" reads 1.16 % worst (Faydh_01 506.6 against 500.7 m3/s, Z4C 1,674.2 against 1,663.1) against W20's 0.5 % rule, which W20 and W28 passed at 40 m with 0.34 %. The two runs took the same water to the digit (hills 84,501,544.013 m3 both; plain the same), so the rain reaches the lumped and the 2D parts alike from the frames; the raw peaks move because at 80 m the inflow of a lumped hydrograph is split among fewer, larger cells at each refresh, the flicker W20 named. On the CPU the same check reads 0.74 % worst and fails the same way.

**The twins diverge on the Block 2 hybrid, and not by chance (`scripts/repeat_hybrid.py`, `results/repeat_hybrid.json`).** The dock's HMS-storm job at 80 m, run again twice on the GPU and once on the CPU by the command line: the two GPU runs are equal to the last digit of every peak and to the dock's own run (101,432 steps, Faydh_01 506.601); the CPU run repeats the dock's CPU run to the digit too (101,421 steps, Faydh_01 493.718). So each backend is repeatable and they differ from each other, by -2.5 % at Faydh 01, under 0.3 % at the other four dams, and up to -23 % on `Bidah_03_ring` (55.6 against 42.7 m3/s, 38 min apart). On Bidah ground, rain-on-grid with a generated basin and its hand-backs, mesh included, the two backends took the same number of steps in all 13 runs and gave the same six digits. [Guessing] What the hybrid has that Bidah does not is HMS inflows entering at wadi mouths through `inject_radius` and `inject_min_depth`: a cell on the threshold of "wet" is counted by one backend and not the other at some refresh, the inflow's split among its cells changes, and from there the step sequences part; the ring that moves most sits round a lumped inflow, which is where W20 saw the raw peak flicker. Not chased, by the brief. [Certain] It is a reproducibility fault of the hybrid across backends, not a CPU-path fault: the CPU gives the GPU's digits wherever the GPU gives its own.

## 2. A generated basin with a gridded storm (`scripts/item2_gridded.py`, `results/item2_gridded.json`)

Bidah ground at 20 m (GGC 5 m terrain, the project CN raster, W27's outlets and dam objects), the basin generated at 2 km2 as W27 did: 8 subbasins, 4 reaches, 4 junctions, 1 reservoir (Bidah 03, rating complete), in about 2 s. The storm is Block 2's 100-yr design storm of the W1 jobs read at the Bidah area, 20.971 km2 (200.3 mm after the ARF table), 30 h. Then the same storm written out as 288 five-minute GeoTIFF frames by W20's method (`build_storm` on the resolved job, one 2 x 2 pixel raster per period) and run as `storm.kind: gridded`. Twice each: all lumped by default, and S2, the subbasin draining straight to the dam, in 2D.

| Run | Rain on the grid, m3 | Inflow from the hills, m3 | Reservoir inflow peak, m3/s at h | Hand-back built | Grid error | Whole error |
|---|---|---|---|---|---|---|
| Design storm, all lumped | 996,681.192 | 3,600,902.790 | 463.334 at 12.42 | none | -2.0e-8 | |
| Frames, all lumped | 996,681.193 | 3,600,902.787 | 463.334 at 12.42 | none | -2.0e-8 | |
| Design storm, S2 in 2D | 1,354,145.837 | 3,599,606.999 | 456.924 at 12.42 | Bidah 03 | -1.9e-8 | -2.8e-4 (the Muskingum-Cunge defect, -1,284 m3) |
| Frames, S2 in 2D | 1,354,145.838 | 3,599,606.992 | 456.934 at 12.42 | Bidah 03 | -2.0e-8 | -2.8e-4 |

[Certain, measured] The lumped subbasins and the 2D ground take the same water from the frames as from the design storm, to 1e-9 of the volume; the `above` line 65.34 against 65.32 m3/s; the hand-back crossing 362,769.4 m3 in both. The rain-once check ran on every job and said nothing (the one warning of every run is the test domain's western edge, as in W15 and W27). This is the code path W27 listed as "exists, untested".

## 3. A generated basin with the mesh (`scripts/item3_mesh.py`, `results/item3_mesh.json`)

The same basin and storm at 10 m, every subbasin above the dam in 2D, the rest lumped; uniform 10 m against the mesh 10 to 40 m with the default stream rules, local time stepping off and on. Rule set before the run: the dam-side peaks within the mesh's known 2.4 %.

| Case | Cells | `above` line, m3/s | Reservoir outflow, m3/s at h | Crossing at Bidah 03 | at J2 | at J3 | at J4 | Grid error | Whole error |
|---|---|---|---|---|---|---|---|---|---|
| Uniform 10 m | 287,578 | 64.67 | 277.79 at 12.75 | 68.74 | 326.26 | 88.47 | 182.05 | | |
| Mesh 10 to 40 m | 131,425 | 64.51 (-0.26 %) | 274.71 at 12.83 (-1.1 %) | 68.59 (-0.22 %) | 317.36 (-2.73 %) | 85.86 (-2.95 %) | 176.46 (-3.07 %) | -2.1e-8 | -7.7e-4 |
| Mesh, local time stepping | 131,425 | 64.60 (-0.12 %) | 274.94 (-1.0 %) | 68.71 (-0.05 %) | 317.93 (-2.55 %) | 85.85 (-2.96 %) | 176.63 (-2.98 %) | -2.1e-8 | -7.8e-4 |

[Certain, measured] At the dam the mesh holds the rule, and the volumes crossing every line are within 0.7 %. The crossings at the three upstream junctions read 2.5 to 3.1 % low, which is what W23 measured for the stream rules alone on a section across a wadi (-3.1 to -5.1 %): the mesh, not the basin. The resolver built lines at J2, J3 and J4 as well as at the reservoir, because each has a 2D subbasin above it and a reach below (W27's rule); my script expected one line and flagged it, which is the script's mistake, and its crossing checks did not run through a key mismatch (`Bidah_03` against `Bidah 03`), so the crossings above are read from the run's own series and not from a check. The mesh with a hand-back, the quadtree refining along the built lines, had not been run before; it closes.

## 4. A generated basin with a resume (`scripts/item4_resume.py`, `results/item4_resume.json`)

The item-3 job at 20 m, 30 h, a checkpoint every 15 wall seconds: one straight run; one run stopped through `out/stop` at 12.09 h, inside the rising flood (exit 6, `checkpoint.h5` with its `handback` group), then `--resume` to 30 h (exit 0). The first attempt of this script never stopped the run (it looked for a `t_s` field the `step` events do not have); the second did.

| | Straight | Resumed | |
|---|---|---|---|
| Rain, m3 | 4,254,615.4766 | 4,254,615.4863 | 2.3e-9 |
| Hand-back crossed, m3 | 3,251,468.1293 | 3,251,467.8424 | 8.8e-8 |
| Network storage at the end, m3 | 58,481.2117 | 58,480.8152 | 6.8e-6 |
| Grid storage at the end, m3 | 389,067.3921 | 389,067.7213 | 8.5e-7 |
| Outflow, m3 | 7,438,336.7369 | 7,438,336.5286 | 2.8e-8 |
| Grid error | -2.13e-8 | -2.15e-8 | |
| Whole error | -7.7655e-4 | -7.7655e-4 | the routing defect, -3,595.9 m3, both |
| `above` line peak | 62.8699 m3/s at 12.04 h | 62.8699 at 12.04 h | |

**Fails the rule the brief set, equal to the last digit: 1 of 19 series files identical.** [Certain, read in the files] The four line series and the pool point have 993 of 1,800 rows different: the straight run samples at 30 + 60 k s throughout (48,450, 48,510, ...), the resumed run samples at 60 k s after the checkpoint (48,450 then 50,460, 50,520, ...): the series clock re-phases at the checkpoint time 48,465.5 s instead of keeping the run's phase, so every later value is the same hydrograph read 30 s away (-5.49355 against -5.46977 m3/s at the peak's tail). The lumped network and hand-back series differ in the 20 rows after the stop by up to 0.0024 m3/s (R2 at 48,600 s): the period that holds the stop is tallied again on the resume. Both are inside W25's 1e-3, which is why its resume test passes; neither is bit-for-bit. [Likely] the series phase is the `Monitor`'s next-sample time, reset on load; not chased, by the brief.

## 5. A generated basin on the full extent (`scripts/item5_full_extent.py`, `results/item5_full_extent.json`)

W12's job (the actual project boundary at 30 m on the NSA 5 m and Copernicus 30 m blend, Block 2's 200-yr storm at 300 km2, CN raster, the two coast lines as normal boundaries, W12's 19 lines) with the HMS network taken out and `basin.stream_threshold_km2` 10, the default of the schema.

| Step | What happened | Numbers |
|---|---|---|
| `wadi2d basin` at the default 5 m pixel | refused in words, exit 2, in 2 s | "the delineation would take 1,852,454,016 pixels of 5.0 m, above max_pixels 400,000,000: use a coarser analysis pixel" |
| at 10 m | refused the same way | 463,113,504 pixels: [Certain, arithmetic] the guard counts the domain's bounding box, 46,311 km2, three times the 15,398 km2 polygon |
| at 15 m | **generated, about 167 s** | 844 subbasins, 381 reaches, 467 junctions, 0 reservoirs (the job has no crest line), no generation notes; 9 subbasins lack `curve_number` and `lag_minutes` (the CN raster does not cover them to `min_raster_share`) |
| `wadi2d run`, all lumped by default | started: 17,108,508 cells, 17,243 tiles, tables about 209 s (a new cache entry, the basin changes the key) | the resolver: 381 junctions route by reach, 86 feed the grid, 2 hand-back lines (the 9 rain-on-grid subbasins above a reach), 835 lumped; 9 warnings naming each incomplete subbasin and what it lacks, plus W12's own edge-water warning |
| stopped by the stop file after 10 min of loop | exit 6, checkpoint written | t = 40,650 s (11.3 h of 36), 32,099 steps, smallest step 0.69 s; rain on the grid 14.46 Mm3, inflow 43.20 Mm3, crossed the lines 8.46 Mm3, in the network 17.77 Mm3; grid error 1.4e-8, whole -3.6e-4 (routing defect -24,274 m3) |

[Certain, measured] The generated basin runs on the full extent: generation is minutes, the run starts and its books close through the first 11 h. [Likely] A full run would take about the same loop time as W12's, 68 min on an idle card, plus the lumped network's reruns at each of the 432 lumped steps; the 10 min here reached 11.3 h at 32,099 steps, which extrapolates to about 32 min of loop for 36 h on the shared card. Not run to the end: the card was in use by other work (13 % at the time), and the brief said not to in that case. [Guessing] The two things the owner will meet first on a real full-extent basin: the bounding-box guard, which asks for 15 m on a domain whose polygon would allow 10 m, and the 9 subbasins at the edge of the CN raster, which run as rain-on-grid without being asked.

## 6. The hand-back at a dam through crest faces (`scripts/item6_dam_handback.py`, `item6b_dam_handback_filled.py`)

W27 placed the line three cells up the axis and never compared a 2D flood entering the lumped pool with the same flood routed on the grid through the crest faces. Two runs of the 100-yr flood at 20 m, 36 h, nothing tuned: the lumped pool on W27's basin (its rating is the spillway object, Q = 2.1 x 72 x H^1.5 at 100 m, the pool table from the DEM behind the 105 m crest), and the grid pool on a basin generated with no reaches (`min_reach_m` 5,000: every junction's route is `none`, no line is built), so the pool fills on the grid and the flood passes the spillway face and the crest faces, read on a line 150 m downstream of the crest. A third run replaces the main crest line by a W8 `embankment` on the same alignment (crest 105 m, 8 m wide, 2:1 faces), so the barrier is the eased crest faces of the shaped objects. [Certain, read in `wadi2d/basin/pour.py`] the generator takes `crest_line` only as a dam, so an embankment alone makes no reservoir: the generation keeps the crest line, the run swaps the object.

**First attempt (`results/item6_dam_handback.json`), every subbasin above the dam in 2D: not like for like, and two things to know.**

| | Lumped pool | Grid pool, crest lines | Grid pool, embankment |
|---|---|---|---|
| Reservoir inflow peak (network), m3/s | 589.4 at 12.33 h | | |
| Pool outflow peak, m3/s | 274.0 at 12.83 h | 0.06 | 0.11 |
| Spilled, Mm3 | 3.236 | 0.0003 | 0.0007 |
| Pool level at the end | | 99.2 m at 33.6 h, still rising | 99.4 m |
| Grid storage at the end, Mm3 | 0.38 | 3.65 | 3.65 |

- [Certain, read in `basin.json`] **The generated reservoir starts at its spillway crest**: `initial_elevation_m` is derived as the lowest spillway level, 100.0 m, while the pool table runs from 86.96 m; the grid pool starts dry. On Bidah that is 3.6 Mm3 of dead storage, and the 100-yr flood (4.25 Mm3 of rain on the catchment) nearly fits in it: the lumped pool spilled 3.24 Mm3 while the grid pool never reached the spillway. Starting a flood routing at the spillway crest is HMS's usual conservative assumption and nothing is wrong with it; but a hybrid run holds the two pools to different starts unless the user fills the grid pool with `initial_levels`, and the dock has no row for that. His call.
- [Certain, measured] With every subbasin above the dam in 2D the resolver builds lines at J2, J3 and J4 too (each has a 2D subbasin above and a reach below), so the upper water reaches the pool through the lumped reaches R2 to R4 and only S2 crosses the grid line at the dam: the "2D flood into the pool" is 589 m3/s of reach outflow plus 66 m3/s over the grid. That is W27's rule working as written, and it means a 2D catchment above a dam is lumped again at the first junction with a reach.
- A user-drawn hand-back line below the crest into R1, on the same job, ran (exit 0): the engine accepted it beside the built lines and it caught 574 m3, what passed the crest. No refusal, no double count, and no use either.

**Second attempt (`results/item6b_dam_handback_filled.json`), like for like, 15 of 15:** only S2 in 2D, S3 to S8 lumped in every run (so the upper water routes alike, reaches in one basin, inflows at J2 to J4 running over the ground in the other), and the grid pool filled to the reservoir's own 100.0 m through `initial_levels` on a polygon bounded by the dam line and reaching 3 km up the valley.

| | Lumped pool, rating | Grid pool, crest lines | Grid pool, W8 embankment |
|---|---|---|---|
| Pool at the start, Mm3 | at 100.0 m | 3.740 | 3.658 |
| S2 crossing the built line, m3/s | 67.8 at 12.08 h (364,872 m3) | | |
| Reservoir inflow peak (network), m3/s | 456.9 at 12.42 h | | |
| **Outflow peak, m3/s at h** | **262.6 at 12.92** | **258.7 at 12.91 (-1.5 %)** | **255.4 at 12.91 (-2.7 %)** |
| Spilled over 36 h, Mm3 | 3.249 | 3.140 (-3.4 %) | 3.242 (-0.2 %) |
| Pool level at the peak | | 101.43 m at 12.86 h | 101.48 m at 12.89 h |
| Grid error | -1.7e-8 | -8.6e-9 | -1.0e-8 |
| Whole error | -2.8e-4, the routing defect of R1 (-1,284 m3) | | |

[Certain, measured] The rated lumped pool and the crest faces on the grid give the same dam outflow within 1.5 % at the peak and 2 min in time, the embankment within 2.7 %, with the spillway head 1.43 to 1.48 m; the books of all three close. [Likely] the 1.5 % is the inflow, not the dam: the lumped run's pool takes the upper water through Muskingum-Cunge reaches and the grid run over the ground, the method difference W25 measured on R1. One artefact to know when reading the grid runs: a burst of 495 m3/s across the dam line at t = 0, the initial-level polygon (its downstream edge 10 m up from the line) filling a few cells on the downstream side of the crest staircase, which drain at once; it is 0.08 Mm3 of the start and does not touch the 12.9 h comparison.

## Failures and what the owner must decide

1. **Resume is not bit-for-bit (item 4).** The series clock re-phases at the checkpoint and the hand-back period holding the stop is re-tallied; both under 1e-3. Decide whether a resumed run must reproduce a straight one to the digit (then the sampling phase and the period tally belong in the checkpoint), or whether W25's 1e-3 is the rule and the brief's "last digit" is withdrawn.
2. **The lumped pool starts at the spillway crest, the grid pool starts dry (item 6).** Decide the convention for the generated reservoir's initial level, and whether the dock should fill the grid pool to it (`initial_levels` has no row).
3. **A 2D catchment above a dam is lumped again at the first junction with a reach (item 6, first attempt).** By W27's rule. If the owner wants the 2D flood to reach the pool over the ground, the resolver needs a switch per junction, or the reaches above the dam must be dropped at generation (`min_reach_m`), which drops every reach.
4. **The dock has no backend choice (item 1).** The CPU twin is proven through every new section, but a user with a card who wants the CPU, or a machine where CuPy half-works, has only an environment variable. A row or a setting is one field.
5. **The two backends diverge on the Block 2 hybrid (item 1).** Each repeats itself to the digit; they differ from each other by 2.5 % at Faydh 01 and 23 % on a ring round a lumped inflow, after 101,421 against 101,432 steps. Decide whether a run must give the same digits on both backends (then the inflow injection's wet-cell test is the first place to look) or whether the backends are allowed to differ inside the flicker the raw peaks already carry, and the record says which backend made a number.
6. **The full-extent generator's size guard counts the bounding box (item 5)**: a 15,398 km2 polygon in a 46,311 km2 box is refused at 10 m. Decide whether the guard should count the polygon, or `max_pixels` should rise; and whether a subbasin at the edge of the CN raster should fall to rain-on-grid silently in the dock as it does on the command line (the warning names it, nothing stops).
7. **The storm scenario's Block 2 part at 80 m reads 1.16 % apart between the HMS storm and the frames (item 1)**: not a defect, the raw-peak flicker W20 named, but it says the 0.5 % rule is a 40 m rule.

## What was not run, and why

- The CPU twin on the full extent, or on Block 2 at 40 m: at 31 x the GPU's time, hours per run; the 80 m runs stand in.
- A full 68-min run of the generated full-extent basin: the card was in use by other work, so the brief's rule gave the 10-min probe; `--full` runs it.
- A generated basin with a gridded storm on the mesh, or with a resume on the mesh: each pair was run once, not every triple.
- The hand-back at the dam through the dock: items 2 to 6 ran the engine by `wadi2d run` on jobs the dock would write (the job fields are W27's); the dock itself was run on the CPU twin only (item 1).
- The profile editor, the cell grid layer, the boundary table and the time slider on the CPU twin: not new sections of the engine; the result-lines scenario covers the time slider's frames.

## Files, and what was deleted

- `scripts/`: `common.py` (paths, the Bidah job, running the engine, reading a run), `jobs.py` (generation, the subbasins above the dam, the lines), `w32dock.py` (the dock helper), `run_dock.ps1` and `run_item1.ps1` (item 1), `compare_backends.py`, `speed_probe.py`, `item2_gridded.py`, `item3_mesh.py`, `item4_resume.py`, `item5_full_extent.py`, `item6_dam_handback.py`, `item6b_dam_handback_filled.py`, the four `dock_*_w32.py` scenarios and `wadi_line.geojson` (W23's stem, which the mesh scenario reads beside itself).
- `dock/`: the harness log of each scenario on each backend (`log_<scenario>_<backend>.txt`), the series peaks (`numbers_<scenario>_<backend>.json`), the renders and widget shots the scenarios make.
- `results/`: one JSON per item with every number above, `item1_backends.json`, `speed_probe.json`, and the console output of each item script (`item*.txt`).
- `jobs/`: every job the items ran, as written (paths point at the session scratchpad; the basin files are regenerated by the scripts in about 2 s).
- **Deleted:** every run folder, grid cache and generated basin in the session scratchpad (`w32/`, 2.9 GB at the end, the 17 M-cell run's results the largest of it), the 288 rain frames, the eight throwaway QGIS profiles, and the one grid-cache entry item 5 wrote beside W12's two (`W12 full extent rerun/cache/grid_8356f40d...h5`, 4.3 GB, removed; W12's own two entries untouched). Nothing kept is over 6 MB.

## Rerun

From this worktree with `.venv` beside it (a junction to the main checkout's works):

```
powershell -File "W32 combinations test\scripts\run_item1.ps1" cpu      # then gpu; then python scripts\compare_backends.py
.venv\Scripts\python.exe "W32 combinations test\scripts\item2_gridded.py" <scratch>     # first: the others reuse its basin
.venv\Scripts\python.exe "W32 combinations test\scripts\item3_mesh.py" <scratch>
.venv\Scripts\python.exe "W32 combinations test\scripts\item4_resume.py" <scratch>
.venv\Scripts\python.exe "W32 combinations test\scripts\item6_dam_handback.py" <scratch>   # then item6b_dam_handback_filled.py
.venv\Scripts\python.exe "W32 combinations test\scripts\item5_full_extent.py" <scratch> --minutes 10 --pixel 15   # --full for the whole run
```
