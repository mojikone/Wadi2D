# W106 Block 2 from the dock, gaps fixed

**Live (2026-11-16), branch `feature/dock-gaps-w106` off `feature/fast-products` (`903fc77`); not merged, nothing
pushed.** His question: "Did you test the dock to create and run all 4 types? All issues are fixed?" This folder is
the answer: the nine gaps W104 found fixed, each its own commit with a test, and Block 2's four models built and run
again from his raw inputs through the dock alone, in throwaway QGIS 3.44.8 windows (`tests/dock/run_check.ps1`), with
no step in QGIS's own tools, no job file and no command line. Superseded: nothing; W104 stays as the record of the dock
before these fixes.

## The answer in short

- [Certain] **All nine gaps are fixed and the four models were built and run from the ground up through the dock with
  no way round**: 22, 14, 15, 15 and 11 checks of the five sessions passed, none failed (after two faults the real dock
  found and that were fixed on the way, below). His raw CN grid with its holes, 88 typed beside it; the reach n at its
  0.1; HAT-J4 a clicked junction ticked as a last point; the lumped ARF the curve, the 2D part at 100 km2.
- [Certain] **2D** equals W104's to 0.1 % and W79's run 1 within 0.7 % at every dam, in and out.
- [Certain] **Lumped and Hybrid Lumped** are now within 1.2 to 5.4 % of W79 (HMS's Basin 3) at Bidah 03, Faydh 01, R5A
  and Z4C, where W104 read 42 to 57 % over at R5A, R2A and Z4C: the reach n (0.1 against Terrain's 0.04) was most of it.
  R2A stays 27 % over, the generated basin's own: 14 subbasins above it with lags of 19 to 101 min against HMS's few.
- [Certain] **Hybrid 2D** is the model his rule describes, with no workaround: 67 lumped subbasins, each at its own
  outlet, routed in 2D, the dams as pools, each read at its dam's area: the lumped water entering is 161.5 Mm3 against
  W79's 161.6 (W104 178.3, the own-area rule). Its peaks differ from W79's run 4 by -2.9 % (Bidah 03) to +42 % (R2A),
  the generated basin's finer subbasins entering the grid, and -18.5 % at Faydh 01 (below).
- Times, Run to maps loaded: **2D 46.1 min, Hybrid Lumped 20.2 min, Hybrid 2D 39.7 min, Lumped 10 s** (W104: 48.8,
  20.3, 38.2 min, 12.5 s).

## The steps a user does (the scenarios `s1` to `s5`, sharing `w106_help.py`)

His layers dragged in: the 0.5 m DEM, his CN grid as it is, W79's Manning grid, the rough outline, the four outflow
lines, the crest lines and spillways, the dam lines (copied from W104's `inputs/`; the outflow lines worked on as a copy
under `runs/inputs/`, since the dock's outflow button writes into the Boundaries layer). Every number typed into the
dock's own widgets: 20 m, Manning grid with 0.04 elsewhere, Fill pits, the four lines normal depth at 0.003, 0.0057,
0.005, 0.005, the storm (251 mm in 24 h on his FM 10-1000yr pattern, typed into Data tables), ARF FM.

1. **Session 1, the domain, the basin, Lumped (22 of 22).** The **Lumped card first**; its Terrain shows Domain from an
   outline (gap 5). Rough outline, edges kept along the outflow lines, **Complete upstream** (124 s): 1,399.36 km2, and
   "2 streams leave this domain through a closed edge ... 269.87 km2 at (452352, 2715540); 0.30 km2 ..." with the button
   **Add 2 outflow lines there** (gap 9), pressed: "Outflow 269.9 km2, Outflow 0.3 km2" in the Boundaries table, typed
   0.005. Hydrology: his CN grid, **88 beside it** (gap 1). **Generate basin** at 7.5 km2 (53 s): 111 subbasins, none
   lacking a CN, "14 subbasins take CN 88 where the CN raster has none, weighted by area" (gap 2), every reach at n
   0.1, the job's (gap 7). **Align to catchments** (230 s): "Aligning Terrain's domain "Domain completed upstream,
   1,399.36 km2" to the catchments..." to 1,398.25 km2 (gap 4; W104 had to load the completed layer again). After it
   the dock offered the button again for 35.7, 0.84 and 0.64 km2 (the North stream's line, which opens only part of its
   valley): not pressed in this session, see Still not done. **Generate basin** on the aligned domain (64 s): 109
   subbasins, 5 reservoirs (Bidah 03 20.03, Faydh 01 74.42, R5A 117.12, R2A 175.94, Z4C 211.56 km2; Basin 3 20.97,
   74.30, 117.10, 175.87, 211.09). Storm, area reduction (lumped curve), simulation 48 h; **Run** (10 s). Saved.
2. **Session 2, 2D (14 of 14).** The project reopened: the aligned domain and the CN 88 beside the grid restored. 2D
   card; Mesh: aligned centre mesh, **Suggest breaklines** (232 s), **Build mesh** (135 s): 3,461,233 cells (536,278
   aligned). Area reduction 2D at 100 km2 (0.9130). Then **the CN box emptied and Run**: "The CN grid gives no value on
   15,687 cells of 20 m where rain falls on the grid (6.27 km2): they would run off with no losses, and the engine
   refuses that. Give a CN where the grid has none (Hydrology, Curve number), or extend the grid." in 10 s, no engine
   started (gap 1). 88 again; **Run**. Its `pools.json` holds the five dams' pools (gap 8). Saved.
3. **Session 3, Hybrid Lumped (15 of 15).** Hybrid Lumped card. **New layer**, Junction, **Click on the map** at the
   HAT-S7 / HAT-S8 confluence: "Junction 1 lies 0 m from reach R7 of the last generated basin, which drains 294.23 km2
   at its lower end: Generate basin snaps it and says the drainage area there" (gap 6); renamed HAT-J4, the layer
   saved. **Generate basin** (64 s): "Basin points: ... HAT-J4 moved 0 m to the stream there, draining 260.36 km2" (the click was on the Lumped basin's junction; the five dams 0 m too) and
   the moves drawn on the map (gap 6). Last points: the five dams ticked, **Add a junction** HAT-J4. Hydrology: "the
   lumped model ends at 5 dams + HAT-J4 · 67 of 108 subbasins lie above the last points and run lumped; the rest rain
   on the grid". The job: `generated_entry: last_points` (gap 3), `exclude_lumped`. **Run**: 67 subbasins, 859.42 km2
   and 2,148,920 cells left out (W79 860.30 km2, 2,149,911), each last point entering on the edge of the catchments it
   brings in (Bidah 03 77 m from its node, Faydh 01 34, R5A 24, R2A 831, Z4C 21, HAT-J4 45 m). Saved.
4. **Session 4, Hybrid 2D (15 of 15).** Hybrid 2D card, the HAT-J4 layer, Generate basin, the same last points; the
   job: `generated_entry: outlets` (gap 3). **Run**: "Hybrid 2D: 67 lumped subbasins enter the grid at their own
   outlets; no reach or reservoir is routed lumped, the grid routes their water"; every one read at its last point's
   area (`lumped_entry_areas.json`: 67 at a last point, no rerun). The window was closed by hand before it saved its
   scenario; session 5 saved it.
5. **Session 5, the project (11 of 11).** Each run opened with Open a run, its results page drawn; **Compare runs** on
   the four: one row per dam, the four runs' inflow and outflow on it (gap 8), the table in `compare_runs.xlsx`. The
   project written back: **`Block2_from_the_dock_W106.qgz`**, one group per model in the plugin's pattern.

## Times from pressing Run to the maps loaded (GPU, RTX 5080)

| Stage, s | 2D | Hybrid Lumped | Hybrid 2D | W104 2D / HL / H2D |
|---|---|---|---|---|
| Before the solver (job, CN check, tables from the DEM store, strips, pits, entries) | 323 (tables 304) | 160 (tables 146) | 369 (tables 299) | 397 / 157 / 338 |
| Solver loop, 48 h | 2,191 (407,815 steps) | 948 (519,536 steps) | 1,863 (396,511 steps) | 2,292 / 950 / 1,744 |
| Products (ground, 193 maps, rasters, the pools) | 223 | 82 | 130 | 213 / 84 / 207 |
| Layers loaded into the project | 27 | 24 | 18 | 26 / 25 / - |
| **Run to maps loaded** | **2,764 (46.1 min)** | **1,215 (20.2 min)** | **2,380 (39.7 min)** | 2,929 / 1,216 / 2,289 |
| Mass error | 6.8e-9 | -8.8e-9 | 5.9e-8 | 3.7e-9 / -2.4e-8 / 4.7e-8 |
| Water, Mm3: rain / lumped inflow / out | 271.0 / 0 / 214.9 | 101.3 / 112.2 / 207.6 | 101.3 / 161.5 / 207.0 | 271.0 / 0 / 214.9; 101.2 / 112.4 / 207.6; 103.7 / 178.3 / 226.4 |

Lumped: 10 s. Before a run: Complete upstream 124 s (with the edge check; the DEM store was built by the first try's
session), Generate basin 53 to 64 s, Align 230 s, Suggest breaklines 232 s, Build mesh 135 s. The pools of a run take
26 s of its products on Block 2.

## Dam peaks against W79 and W104 (`dam_peaks.csv`, `scripts/s05_compare.py`; m3/s)

Read as W79 and W104 read theirs: a lumped reservoir's inflow and outflow series; a 2D pool's inflow by the balance of
W79's pool polygons and its outflow on the dam line. The engine's own pool record (gap 8) is beside it in the CSV and
equals it within 0.15 % (Z4C 3,221.7 against 3,225.7); the dock's Compare shows the engine's.

| Dam | 2D in / out (W79; W104) | Lumped = Hybrid Lumped in / out (W79; W104) | Hybrid 2D in / out (W79; W104) |
|---|---|---|---|
| Bidah 03 | 584 / 0 (581 / 0; 584 / 0) | 463 / 0 (455 / 0; 479 / 0) | 431 / 0 (444 / 0; 463 / 0) |
| Faydh 01 | 2,305 / 0 (2,314 / 0; 2,304 / 0) | 1,173 / 0 (1,240 / 0; 1,198 / 0) | 995 / 0 (1,221 / 0; 1,214 / 0) |
| R5A | 2,056 / 612 (2,071 / 608; 2,056 / 612) | 1,205 / 891 (1,144 / 754; 1,673 / 927) | 1,381 / 599 (1,115 / 671; 1,538 / 839) |
| R2A | 3,931 / 1,145 (3,958 / 1,151; 3,929 / 1,153) | 2,198 / 925 (1,736 / 818; 2,732 / 979) | 2,156 / 934 (1,516 / 857; 2,684 / 1,369) |
| Z4C | 3,226 / 3,434 (3,240 / 3,455; 3,226 / 3,434) | 2,126 / 2,027 (2,101 / 2,025; 2,978 / 2,743) | 2,065 / 2,110 (1,941 / 2,018; 2,801 / 2,958) |

Inflow volumes, Mm3, 2D / Lumped / Hybrid 2D: Bidah 03 3.82 / 4.14 / 4.15, Faydh 01 14.88 / 15.25 / 15.25, R5A 22.80 /
22.87 / 22.79, R2A 34.31 / 32.96 / 32.86, Z4C 41.66 / 39.25 / 39.18 (W79's Lumped 4.3, 15.2, 22.9, 32.9, 39.2). HAT-J4,
Hybrid Lumped's entry: 3,142 m3/s at 14.08 h, 46.92 Mm3 (W79 2,472 at 15.75 h, 47.07; W104 4,136 at 13.25 h).

What each difference comes from:

- **2D** [Certain]: the same model as W104's and W79's run 1; the two outflow lines the dock added lie 11 km and more
  below the dams.
- **Lumped and Hybrid Lumped against W104** [Certain]: the reach n, 0.1 against 0.04, takes 20 to 29 % off R5A, R2A
  and Z4C and 2 to 3 % off Bidah 03 and Faydh 01 (one 1.8 km and two 4.2 km of reach above them); the CN by area
  against W104's 88-filled grid gives the same volumes (within 0.05 Mm3). Hybrid Lumped equals Lumped at the dams to
  the digit, as W79's run 3 equals its run 2: the lumped water stops at the dams, each at its own area.
- **Lumped against W79 (HMS's Basin 3)** [Likely]: volumes agree within 0.16 Mm3, Bidah 03 the most (its generated polygon 4.5 % smaller); the peaks are within 5.4 % at four dams, R2A +27 %: 14 generated subbasins above it (lags 19 to 101 min,
  33.7 km of reach) against Basin 3's few, so more of the catchment answers early. The generated basin, not the
  dock's rules: Basin 3's own subbasins would give W79's numbers (W105 showed the rules give them to 0.005 m3/s).
- **Hybrid 2D against W79's run 4** [Likely]: the ARF is now his rule (each subbasin at its dam's area): the volumes
  equal Lumped's within 0.1 Mm3 and the lumped inflow 161.5 against run 4's 161.6 Mm3, where W104 had +10 %. The peaks
  are the generated subbasins entering the grid at 67 outlets against Basin 3's 26: +24 % at R5A and +42 % at R2A, where
  the lumped peaks were already +5 and +27 %, and the 2D routing between the outlets and the pool shapes the rest.
  **Faydh 01 reads -18.5 %** (995 against 1,221): its five subbasins enter at their own outlets up its branches and the grid
  routes them through the gorge; W79's run 4 entered HMS's polygons' wadi outlets. [Guessing]
  The attenuation of those reaches on the grid; not looked into here.

## Still not done, or not from the dock

1. **The North stream's line**: after Align the dock offered outflow lines for 35.7, 0.84 and 0.64 km2 leaving the
   aligned domain (the North stream line opens 0.4 of its 0.7 km, W104's gap 15); this session did not press the button
   the second time, so the three runs carry those closed crossings and their pools against the edge (no dam is near).
2. **Delineation on the coastal flats is not repeatable**: the same inputs gave 109, 108 and 111 subbasins and 34.15,
   34.07 and 31.51 km2 reaching the edge in the three model folders; every dam's and HAT-J4's area identical to the
   digit. [Likely] ties in the flat-resolution of the plain.
3. **R2A's Hybrid Lumped entry lies 831 m from its reservoir node**: the lowest cell on the edge of its 14 catchments
   (W105's `edge` rule); W105 put it 35 m from the main chute on HMS's polygons. Not looked into.
4. **A placement check is the last basin's**: a click names the reach of the last generated basin and its area at the
   reach's lower end; the exact snap and area come with Generate basin. A snap before any basin needs a cached
   delineation, not built.
5. **Pools need names**: a dam is a named crest line or embankment (its "part N" pieces one dam); its outflow is the
   result line of the same name, else none, said in `pools.json`.
6. **W104's other gaps not in this brief**: 31 to 34 km2 of the domain reach the edge without a stream in a Lumped
   model, said and not run; Suggest's 13,725 crests to review; the Lumped card still shows the 2D part of the area
   reduction.
7. **The harness**: the throwaway QGIS windows of these long sessions stayed open after their last check (closed by
   hand, each one; session 4's before it saved its scenario, which session 5 saved). W104's session 1 window (process
   37376, its own worktree) was still open when this work started; left as it was, not this work's.
8. The Hybrid 2D card on an **HMS** project is W105's (`lumped_entry`), unchanged.

## Found and fixed on the way (the real dock)

- `8e1b2e4`: the first Generate basin of a model did not take the reach n (only a basin already generated did): the
  first session's first try read 0.04 on every reach.
- `efd2801`: the CN check let GDAL free the raster under its band and fell to its "skipped" branch, so the first try of
  session 2 started an engine run with no CN for the holes; stopped by hand, the folder deleted.
- `9ea94fd`: a pool's peak outflow is the dam line's own peak, not its 15-minute mean.

- `636d0bf`: a pool record was searched behind every named crest line, its window widening to 96 km, so W26's older
  scenario of Suggest's crests ran minutes past its one-minute run; now only a dam (a spillway on it or a result line
  of its name), the window held within 24 km.

## Tests

- Plugin tests that need no QGIS window, every file of `tests/plugin` alone: **755 passed of 755** (55 files;
  `logs/plugin_tests.txt`); new: `test_cn_holes.py` 5, `test_reach_n.py` 3, and tests added to
  `test_model_types.py`, `test_domain_rows.py` (2), `test_basin_point_rows.py`, `test_results_rows.py`; the format
  number in three files moved to 7.
- Engine tests the changes reach, each file alone on the CPU (`CUDA_VISIBLE_DEVICES=-1`): **269 passed, 2 skipped**
  in 22 files (`logs/engine_tests.txt`): `tests/basin` all 8 files, `test_run`, `test_lumped_network`, `test_left_out`,
  `test_model_type`, `test_entry_area`, `test_last_points`, `test_basin_run`, `test_design_lines`, `test_edge_valleys`,
  `test_forcing`, `test_rain_once`, `tests/domain` both, `tests/products/test_pools.py` (new, 3). The full suite was
  not run (left to the merge).
- Real dock, Block 2: sessions 1 to 5, **77 of 77** (22, 14, 15, 15, 11; `logs/log_s*.txt`; the first tries kept as
  `log_s1_first.txt`, `log_s2_first.txt`).

## The older dock scenarios: the same counts and the same jobs

The ten W99, W101 and W103 used (`scripts/run_old_batch.ps1`), each in its own throwaway QGIS 3.44.8, on a frozen copy
of the base (`903fc77`, `git archive`) and of this branch (`636d0bf`); logs in `old_scenarios/base` and `branch`:

| Scenario | Base `903fc77` | Branch `636d0bf` |
|---|---|---|
| `dock_cell_grid.py` (W17) | 3 passed, 1 failed, stopped by an exception | 3 passed, 1 failed, stopped by an exception |
| `dock_boundary_table.py` (W18) | 34 passed, 0 failed | 34 passed, 0 failed |
| `dock_profile_editor.py` (W22) | 120 passed, 0 failed | 120 passed, 0 failed |
| `dock_mesh_controls.py` (W23) | 44 passed, 1 failed, stopped by an exception | 44 passed, 1 failed, stopped by an exception |
| `dock_suggest.py` (W26) | 32 passed, 0 failed | 32 passed, 0 failed |
| `dock_dam_start.py` (W34) | 23 passed, 0 failed | 23 passed, 0 failed |
| `dock_flow_line.py` (W61) | 13 passed, 1 failed | 13 passed, 1 failed |
| `dock_breach.py` (W68) | 14 passed, 0 failed | 14 passed, 0 failed |
| `dock_basin_points.py` (W73) | 36 passed, 0 failed | 36 passed, 0 failed |
| `dock_gauges.py` (W77) | 42 passed, 1 failed | 42 passed, 1 failed |

The same counts as W101 and W103, scenario for scenario; the four that do not pass stop at the same check on the base.
**The jobs** (W99's `compare_jobs.py` and `compare_previews.py`): of the 22 run jobs, **21 identical to the character**
once each batch's folder is taken out; the one that differs is W73's Generate basin job, by `hydrology.reach_manning_n:
0.1` alone, the named change of gap 7 (a new model's reach n). The 5 profile-editor preview jobs on each side pair up,
3 identical and 2 differing only in their random scratch names, as in W99, W101 and W103. Both batches wrote no pixel
maps in their Bidah runs: the CUDA headers do not compile under the frozen copies' long folder name, the same on the
base; the Block 2 runs above, from the worktree, made theirs.

## Files

`s1_setup_lumped.py` to `s5_project.py` and `w106_help.py`: the dock scenarios (from W104's, run with
`tests/dock/run_check.ps1`). `scripts/s05_compare.py`: the dam table (W104's, with W104's columns and the engine's
pool record beside); `scripts/run_old_batch.ps1` (W103's). `inputs/`: his drawn layers and typed numbers (W104's),
`basin_points_hat_j4.gpkg` the clicked junction. `logs/`: each session's log and steps, the engine stages, the test
logs, `s5_compare.json`. `shots/`: the dock and the maps. `dam_peaks.csv`, `dam_peaks.json`, `compare_runs.xlsx` (the
dock's own Compare runs), **`Block2_from_the_dock_W106.qgz`** (the four models in the plugin's groups; it reads the
runs under `runs/`). `runs/` (out of git): the four run folders, their domain, breaklines and basin folders, the DEM's
store (30 GB, `wadi2d_cache`), the first tries, the older batches and their frozen copies, the throwaway QGIS folders.

## The gaps and what the dock does now

| # | W104's gap | What the dock does now | Commit | Proved by |
|---|---|---|---|---|
| 1 | No CN value beside a CN grid; the engine refused runs on the grid's holes after the tables | The value box stays open beside a CN grid, empty by default ("None where the grid has none"), and writes `hydrology.curve_number`, the CN of the grid's holes. With no value, Run counts the holes on cells of the run's size over the domain (less the generated subbasins run lumped) and stops before the engine, with the count | `a2417da`, `efd2801` | `test_cn_holes.py`; session 2: "The CN grid gives no value on 15,687 cells of 20 m where rain falls on the grid (6.27 km2) ..." in 10 s, no engine started |
| 2 | A generated subbasin the CN grid covers under 90 % got no CN, and the dock told the user to edit basin.json | Beside a CN grid the job's CN is the CN of its holes on a generated subbasin too: the area-weighted mean of grid and value; with no value the subbasin's tip sends the user to the CN box and Generate basin, never to basin.json | `368dd76` | `test_model.py::test_the_cn_of_the_job_fills_the_raster_holes_by_area`; session 1: 109 subbasins, none lacking a CN (W104: S36, S37) |
| 3 | The Hybrid 2D card changed nothing on a generated basin; Hybrid Lumped needed hand-placed outfalls | `hydrology.generated_entry`, set by the two hybrid cards on a generated basin. Hybrid Lumped (`last_points`): only the subbasins at or above a last point are lumped, routed by the file's reaches and reservoirs down to the lowest last point on their way, whose outflow enters on the edge of the catchments left out; nothing below a last point lumped. Hybrid 2D (`outlets`): the same subbasins lumped, each entering at its own outlet inside its own polygon (a dam's own subbasin in the pool above the crest), no reach or reservoir routed lumped, the dams 2D pools, a lumped curve read at each subbasin's first last point's area. Hydrology says how many subbasins the last points leave lumped | `57ee0fc` | `test_job.py` (4 new), `test_model_types.py`; sessions 3 and 4 |
| 4 | Align to catchments aligned the rough outline, losing the completion | Align aligns Terrain's domain (the completed one) and says which; the rough outline only when Terrain has none | `0739d17` | `test_domain_rows.py`; session 1: "Aligning Terrain's domain "Domain completed upstream, 1,399.36 km2" ...", 1,398.25 km2 |
| 5 | The Lumped card hid Domain from an outline | Shown under every card | `e97ac84` | session 1, its first check |
| 6 | A basin point on the wrong stream was not seen before the run | On a click, with a basin already generated, the dock names the reach the point lies on and its drainage area; after Generate basin it lists every point's move to its node and the area there, the far moves (over 50 m) named, and draws each move on the map labelled with the area ("Basin points: where each snapped") | `5d63a31` | `test_basin_point_rows.py`; session 3 |
| 7 | No reach Manning n for generated reaches (they took Terrain's 0.04) | Hydrology's Reach Manning n, 0.1 by default ("the n the owner's HEC-HMS model of Block 2 routes its reaches at (W1)"), and a table by reach; written to the job (`hydrology.reach_manning_n`, `reach_manning`) and used at generation and at run time. A saved model of before keeps Terrain's n, with words | `662de94`, `8e1b2e4` | `test_job.py` (3 new), `test_reach_n.py`; session 1: every generated reach `{"value": 0.1, "source": "job"}` |
| 8 | Compare runs could not line a dam up across model types | Every run writes each named dam's 2D pool as an element of record (`series/pool_<dam>.csv`, `pools.json`: W79's pool at the crest + 0.3 m, widened 60 m; inflow by the pool's balance; outflow on the dam line); the results page lists it as a dam and keys dams by name, so a 2D pool and a lumped reservoir of the same dam are one row | `23a0220`, `9ea94fd`, `636d0bf` | `test_pools.py`, `test_results_rows.py`; session 5 |
| 9 | Streams left the completed domain through closed edges unseen (the Fizh branch, 270 km2) | `wadi2d domain` runs the edge check on the domain it makes and gives a line along the edge at each stream leaving it; the dock names them and offers "Add N outflow lines there", normal depth, their slope the table's to check | `5a01de0`, `7d19f37` | `test_edge_valleys.py`, `test_outline.py`, `test_domain_rows.py`; session 1: "Outflow 269.9 km2, Outflow 0.3 km2" added |

## [PRESERVE-CHECK]

- **KEEP**: every job a dock of before wrote (the ten older scenarios below); the engine's results for every job that
  sets none of the new fields (`generated_entry` 'routes', no reach n, no CN beside a raster on a generated basin); the
  job hash of every such job; an HMS basin's routing; W105's rules on HMS basins; the results page's other rows.
- **CHANGE**: new fields `hydrology.generated_entry`, `reach_manning_n`, `reach_manning`; the CN beside a CN raster now
  also fills a generated subbasin's holes by area (before: a subbasin under 90 % lacked its CN); the edge check reads
  the DEM through the chunk store; every run writes `pools.json` and `series/pool_<dam>.csv` where it has named dams on
  the grid; the dock's CN box open beside a grid, Reach Manning n (0.1 for a new model), the domain box under Lumped,
  Align on Terrain's domain, the outflow button, the snapped points, dams keyed by name on the results page (a pin on
  a lumped reservoir made before reads as unpinned); model format 7.
- **FILES**: `wadi2d/basin/job.py`, `elements.py`; `wadi2d/config/schema.py`; `wadi2d/run.py`; `wadi2d/edge_valleys.py`;
  `wadi2d/engine/cli.py`; `wadi2d/products/pools.py` (new); `plugin/wadi2d_qgis/`: `cn_holes.py` (new), `dock.py`,
  `sections/common.py`, `sections/hydrology.py`, `sections/terrain.py`, `sections/basin_rows.py`, `section_status.py`,
  `model_doc.py`, `model_types.py`, `job_builder.py`, `domain_rows.py`, `domain_links.py`, `basin_point_rows.py`,
  `basin_points.py`, `results_rows.py`, `results_links.py`; tests as listed.
