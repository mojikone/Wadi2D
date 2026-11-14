# W53 gridded storms with ARF

**Live.** The owner's new design rain grids of Block 2 (12 NetCDF files and their 12 DSS twins made in HEC-HMS) run in
the engine and the dock, and a gridded storm can now take the area reduction a frequency storm takes, off unless the job
asks. Two additions of his the same day: a depth-area study can place its storm areas by the change of the
area-reduction factor, and a line drawn or picked after a study reads the runs either side of its own drainage area.
Branch `feature/gridded-arf`, not merged, nothing pushed.

His words: "I have added new netCDF and converted DSS files from them using HEC-HMS in the Block 02 folder. I need the
model to be able to run them and apply the ARF too."

Files here: `inventory.py` (the 24 files), `run_engine.py` (the Bidah 03 runs), `summarise.py` (their tables),
`same_numbers.py` (old jobs against the base commit), `study_lines_bidah.py` (the accumulation raster, a study and the
wait for a line), `dock_gridded_arf.py` (the real dock); numbers in `results/`. Run folders are in `_throwaway_w53/`,
outside git.

## What was built

- **Engine.** A gridded storm (NetCDF, DSS, GeoTIFF folder) takes `storm.arf` and `storm.storm_area_km2`, as the design
  storm does. With both set, every frame is multiplied by the table's factor at the storm area, before the losses, on the
  rain-on-grid cells (each cell's SCS excess is of the reduced rain) and under every lumped subbasin's polygon alike.
  Without them the factor is 1 and the rain is not touched, so an existing gridded job gives its numbers to the digit
  (checked below). A hyetograph still refuses a table.
- **On the record.** A run with a table writes `{"ev": "output", "kind": "area_reduction", "factor", "storm_area_km2",
  "arf_table_type"}` to `progress.jsonl`, and a warning in words the dock shows: "rain: every frame is multiplied by
  0.9749, the area-reduction table at 20.971 km2, over the whole event". A table with no storm area says it leaves the
  rain whole.
- **Depth-area study.** `python -m wadi2d.engine.cli arf` takes a gridded storm with a table: one 2D run per storm area,
  each reduced at its own area, each design line read between the bracketing runs on log area, and each lumped element
  with no 2D water above it rerun lumped at its own area, exactly as for the design storm. The rain file is read once per
  process and kept while it is unchanged (a DSS file of 144 frames takes 6 to 7 s to read; a study builds its storm once
  per run and per lumped element).
- **Dock.** Storm, Gridded rain: a tick **Reduce by area: the grids hold point depths**, off by default; ticked, it shows
  **Storm area, km2** and a reduction table (type or paste). Left empty while an HMS project is loaded, the table is the
  HMS project's (ARF FM on Block 2), and the run says so; with no HMS table the run is refused in words. The depth-area
  study accepts gridded rain with the tick on.

The first worker's untested commit (`8697c5a`, stopped at the usage ceiling) was read before anything was built on it
and kept: the reduction sits in the storm (`GriddedStorm.area_factor`, `reduced`, `at_area`), so the cells, the lumped
polygons and the study's reruns all take it from one place, and a factor of 1 touches nothing. Changed: its no-ARF test
compared the booked rain to the last digit, which a parallel sum does not repeat (below); the factor is now also said
in words; the table builder is shared with the step rule. It was squashed into the commits of this work.

## Which duration the table is read at, and why

The table is read once, at the storm area, and the one factor multiplies the whole 24 h event, every 10-minute frame
alike. [Certain] That is what HMS does with this table: ARF FM is a single area-factor table attached to a 24 h
specified-pattern hypothetical storm, and HMS multiplies the storm's total depth by its factor and keeps the pattern; its
own depth-area log for Bidah 03 reads "Area-reduced hypothetical storm depth: 200.251 mm" of 205.4 mm, a factor of
0.974932, the factor this engine reports at 20.971 km2 to six digits. The grids span the same 24 h. A duration-dependent
reduction (a larger cut of the short-duration bursts, as TP-40 curves or HMS's Frequency Storm method do) needs one table
per duration, which the project does not have, and it would reshape the grid's own time pattern; it was not built.

## The 24 files

All 24 read. 144 frames of 10 min, 24 h from 2000-01-01 00:00, no gaps, no missing data, no negative depths, depths in mm
per period. NetCDF: 494 x 605 pixels of 2 km, WGS 84 / UTM 40N. DSS: 606 x 528 pixels of 2 km on HEC's SHG Albers grid
(EPSG 5070), the NetCDF resampled; read in 6 to 7 s against under 2 s. Depth of the event, area-weighted over the
polygon as the engine reads a lumped subbasin (`inventory.py`, `results/inventory.json`):

| Storm | NetCDF over S13, mm | DSS over S13, mm | DSS against NetCDF, S13 | over the Bidah 03 domain | worst of 18 subbasins |
|---|---|---|---|---|---|
| RP5 | 50.51 | 50.56 | +0.10 % | +0.09 % | 0.32 % |
| RP10 | 67.73 | 67.82 | +0.12 % | +0.11 % | 0.31 % |
| RP25 | 91.91 | 92.06 | +0.17 % | +0.15 % | 0.28 % |
| RP50 | 111.89 | 112.13 | +0.21 % | +0.19 % | 0.27 % |
| RP100 | 133.52 | 133.86 | +0.26 % | +0.23 % | 0.31 % |
| RP200 | 157.14 | 157.62 | +0.30 % | +0.27 % | 0.36 % |
| RP500 | 191.54 | 192.24 | +0.36 % | +0.32 % | 0.43 % |
| RP1000 | 219.89 | 220.81 | +0.42 % | +0.37 % | 0.50 % |
| RP2000 | 250.97 | 252.15 | +0.47 % | +0.41 % | 0.57 % |
| RP5000 | 296.84 | 298.44 | +0.54 % | +0.47 % | 0.66 % |
| RP10000 | 335.20 | 337.21 | +0.60 % | +0.52 % | 0.72 % |
| PMP | 502.81 | 505.81 | +0.60 % | +0.52 % | 0.72 % |

Found on the way, for his reading:

- **The DSS twins hold 0.1 to 0.6 % more rain than their NetCDF over Bidah 03,** growing with the return period; W39 saw
  +0.265 % on RP200 alone. It is the resampling onto the SHG grid, not the reader.
- **These grids are not the frequency storms of his HMS project.** Over S13 the grid's RP100 holds 133.5 mm where
  `FM_100yr.met` holds a point depth of 205.4 mm (0.65 x), RP200 157.1 against 251.0 (0.63 x), RP10000 335.2 against
  685.1 (0.49 x).
- **The PMP grid is 1.5 x the RP10000 grid** to 1e-7 on 15 of 18 subbasins, capped at 1,500 mm (S1, S2, S5 and S14 lie
  under the cap and read 1.455 to 1.4997 x); its frames are not 1.5 x the RP10000 frames (largest 10-min depth 88.0
  against 81.7 mm), so only the totals scale. [Likely] It was made as 1.5 x the 10,000-yr totals with a 1,500 mm cap.
  It is a different file from the PMP raster W39 tested (`Clip_PMP_823mm...`, about 1,405 mm over S13).

## Bidah 03 at 30 m

W39's job: Bidah 03's domain, 30 m cells, the 5 m DEM, the project CN grid, two `normal` outlets at slope 0.01, the
`Bidah 03` dam line, 30 h; pixel products off (`run_engine.py`). Full 2D unless named. Every run finished with a mass
error under 1e-6 (`results/runs.json`).

All 24 files through the engine, full 2D on the project CN grid, GPU, no area reduction; the Bidah 03 dam line:

| Storm | NetCDF peak, m3/s | DSS peak, m3/s | DSS against NetCDF, peak | water booked after losses | peak at, h |
|---|---|---|---|---|---|
| RP5 | 95.2 | 95.4 | +0.20 % | +0.15 % | 12.97 |
| RP10 | 175.3 | 175.5 | +0.16 % | +0.17 % | 12.78 |
| RP25 | 302.4 | 303.5 | +0.37 % | +0.21 % | 12.64 |
| RP50 | 415.7 | 417.0 | +0.30 % | +0.25 % | 12.56 |
| RP100 | 528.9 | 531.0 | +0.40 % | +0.30 % | 12.51 |
| RP200 | 637.6 | 639.7 | +0.32 % | +0.33 % | 12.46 |
| RP500 | 757.9 | 759.9 | +0.27 % | +0.38 % | 12.43 |
| RP1000 | 825.3 | 827.4 | +0.25 % | +0.43 % | 12.41 |
| RP2000 | 885.9 | 888.4 | +0.28 % | +0.48 % | 12.41 |
| RP5000 | 1,007.8 | 1,014.6 | +0.67 % | +0.54 % | 12.38 |
| RP10000 | 1,168.7 | 1,177.7 | +0.77 % | +0.59 % | 12.36 |
| PMP | 1,666.9 | 1,672.8 | +0.36 % | +0.57 % | 12.32 |

With the area reduction at S13's own 20.971 km2 (ARF FM, factor 0.974932 reported by every run):

| Run | peak, no ARF | peak, ARF | ratio | water booked after losses, ratio |
|---|---|---|---|---|
| full 2D RP10 NetCDF / DSS | 175.3 / 175.5 | 166.9 / 167.2 | 0.952 / 0.952 | 0.962 |
| full 2D RP100 NetCDF / DSS | 528.9 / 531.0 | 509.4 / 511.1 | 0.963 / 0.962 | 0.968 |
| full 2D RP10000 NetCDF / DSS | 1,168.7 / 1,177.7 | 1,132.5 / 1,141.2 | 0.969 / 0.969 | 0.972 |
| full 2D PMP NetCDF / DSS | 1,666.9 / 1,672.8 | 1,618.8 / 1,624.2 | 0.971 / 0.971 | 0.973 |
| HMS route, S13 lumped, RP100 NetCDF / DSS (48 h) | 311.4 / 312.3 | 301.5 / 302.4 | 0.968 / 0.968 | 0.967 |
| HMS route, S13 lumped, PMP NetCDF | 886.0 | 863.1 | 0.974 | 0.973 |

- [Certain] The factor scales the rain exactly: on CN 100 (no losses) through the dock the rain booked with the
  reduction is 0.974931898 of the rain without, against the factor 0.974931900. The engine's unit tests hold the cells,
  the lumped polygons and a study to the factor to 1e-6 and better.
- The peaks fall by more than the rain, 2.6 to 4.8 %, because the SCS loss takes its initial abstraction first: the cut
  falls on the runoff. The rarer the storm, the nearer the peak ratio comes to the factor.
- CPU twin: RP100 NetCDF 528.87 against 528.88 m3/s on the GPU (-0.002 %, 169 s), PMP DSS 1,672.85 against 1,672.80
  (+0.003 %, 341 s), the HMS route with ARF 301.50 against 301.47 (+0.012 %, 23 min).
- The HMS route's S13 is lumped (SCS lag), so its 311 m3/s against full 2D's 529 is the method gap W39 and decision 20
  already record, not this work.
- Every run warns that water stands 7.5 to 8.8 m deep against the domain's edge at (434861, 2723525) or
  (432611, 2727275): the Bidah 03 domain polygon of W39 cuts a pond there. Not looked into; it is W39's domain.
- **Existing jobs give the same numbers** (`same_numbers.py`, `results/same_numbers.json`): RP200 NetCDF, RP200 DSS and
  the HMS-route RP100 job run by the base commit `8128178` and by this branch: every series file byte for byte, every
  cell map value for value, the same steps, the same job hash (a checkpoint resumes across the two). The booked rain
  differs in its sixteenth digit (2.7e-16 relative): the booked rain and inflow are parallel sums, and the base commit
  rerun on the same jobs differs from itself the same way (1.3e-16 and 2.3e-16), as one job run twice on the CPU does
  (W53's unit test now allows 1e-13 there); the water does not.

## Storm areas by the change of the area reduction (his addition)

`arf.by_arf_step` with `arf.arf_step_max` (0.05 by default), off unless chosen; in the dock, Storm areas **By the
change of area reduction** with **Largest ARF change between runs**. The runs span the smallest to the largest drainage
area of the design lines and of the lumped elements a hand-back feeds, as bracketing does, and the factor changes by at
most the limit between neighbours.

- **Equal steps, not a greedy walk.** The table's whole change over the span is cut into the fewest equal steps within
  the limit. A greedy walk from the small end gives the same count and leaves a run a hair below the end at 2 %
  (1,984 then 2,000 km2); merging that run into the end would break the limit (0.021), so equal steps are the form that
  keeps both of his conditions. A factor that rises again is counted along its whole path.
- **Read as the runs read it.** [Certain] The engine reads ARF FM linear in area, as HMS does: HMS's own depth-area log
  gives 200.251 of 205.4 mm at 20.971 km2, a factor of 0.974932, and the engine's is 0.974932. His reference list
  (10, 62, 144, 265, 446, 695, 1057, 1567, 2000) is the greedy walk on log area; read on log area the engine's run at 20.971
  km2 would get 0.974714, which is not the factor it applies. The step rule therefore reads the table the way the runs
  do, so the limit holds on the factors actually applied. On ARF FM, 10 to 2,000 km2: **0.05 gives 9 runs** (10, 62,
  143, 268, 430, 665, 956, 1,459, 2,000 km2, each step 0.0476); **0.02 gives 21**; 0.01 gives 40. Today's 6 log-spaced
  runs step the factor by 2.1 to 13.8 % (13.1 % on log area, his figure).
- One table serves the whole event, so there is no duration to choose (as above).
- The dock lists the runs before the study from the design lines' drainage areas and the table it holds (a design
  storm's, or gridded rain's own); with the HMS project's table it lists them once the job is written, before the first
  run. A contract test holds the dock's sum to the engine's on six cases.
- Existing study settings give the same areas (the engine's and the dock's tests of the listed, log-spaced and
  bracketing rules pass unchanged), and the new settings stay out of the job hash, as `bracket` does.

## Lines after a depth-area study (his addition)

The study's own **Result lines** button (under its table) opens the line panel on the study folder; the engine command
`lines` given a study's folder answers for the study (`wadi2d/products/study_lines.py`).

- **The line's drainage area.** A design line keeps its own (`drainage_area_km2`); any other line takes the largest value
  of the study's flow accumulation raster (`arf.accumulation`, in its `accumulation_units`) over the pixels it crosses
  inside the model. The raster now goes into the study's job whenever one is chosen; the composite map stays its own
  tick (`arf.composite`, True by default, so a job with a raster still writes its maps as before; the dock writes False
  when the map is unticked). This is a change to the dock: before, the raster went into the job only with the composite
  map.
- **Two runs, one request.** The engine finds the two runs either side of the area with `wadi2d.arf.log_area_weights`,
  the weights the composite map uses (the composite map now calls the same function; its numbers do not move), reads
  the line from both and blends every series frame by frame: flow, deepest water, depth and level along the line
  (dry counted as no depth, so a cell wet in one run only is half wet), and speed along the line (new in every line's
  answer). The two runs' frames stand seconds apart (a frame lands on the first step past its time) and are blended as
  the same frame, at the smaller run's times. The peak given is the study's own reading of the two runs' peaks
  (`interpolate_peak`, ln Q on ln A), what the design table does.
- **Outside the runs** the end run is read alone and the plot says so; **no raster**: a design line still takes its
  own area, any other line reads the smallest run alone, and the plot says which storm area that is.
- **The plot** keeps its heading and puts under it, over two lines, the line's area, where it came from, the two runs
  and their weights in words, and the peak as the study reads a design point.
- **Wait.** On Bidah 03 at 30 m (`study_lines_bidah.py`, a D8 accumulation raster of 30 m from the 5 m DEM, a study on
  RP100 NetCDF with ARF FM at 5, 10, 20.971 and 40 km2), two sessions of three requests each, the PC shared with other
  work: a line across a wadi of 8.2 km2, read from two runs, took 1.86 to 2.38 s against 1.39 to 1.94 s for the same
  line on one run, so the second run adds 0.1 to 0.9 s to a wait that is mostly the process starting; a line on a run's
  own area (Bidah 03 itself, one run) took 1.52 to 2.02 s. The 8.2 km2 line read 0.292 of the 5 km2 run and 0.708 of
  the 10 km2 run; the line on Bidah 03 gave 509.58 m3/s from the frames every 15 minutes against the study's design
  peak of 509.44 m3/s from the series of record (+0.03 %).

## His HEC-HMS project

[Certain] Nothing in it is like for like with these runs. It has no meteorologic model on the new grids (the `.grid` file
holds only the PMP raster and the CN grid). The depth-area analyses `DA_*_B2` and `DA_*_B3` of 2026-11-11 run Basin 2
and Basin 3 on the point-depth frequency storms `FM_*.met` (205.4 mm at 100 yr), with the specified 24 h pattern and
ARF FM, so their rain over S13 is 1.5 to 2 times the grid's and differently shaped in time. What does compare is the
area reduction itself: HMS reduces Bidah 03's storm at 20.97 km2 by 200.251 / 205.4 = 0.974932, the engine's factor to
six digits. Nothing was tuned.

## Through the real dock

`dock_gridded_arf.py` in QGIS 3.44.8 with a throwaway profile inside the worktree (`tests/dock/run_check.ps1`), Bidah
03 at 30 m, RP100 NetCDF, full 2D: **48 of 48** (`results/log_w53.txt`, `results/dock.json`, three widget pictures).
Two earlier rounds: 46 of 47, the panel's study note overwritten by the first line's answer; then 47 of 47, but the
picture showed the weights running off the end of the one-line plot heading, so they moved to a wrapped note under it,
and the line's position became a check of its own.

- Gridded rain: **Reduce by area** is off by default with its area and table hidden; unticked, the job carries no
  reduction and the run reports no factor.
- Ticked, 20.971 km2 and ARF FM typed: the job carries both, every run reports 0.9749319 and the dock shows it in words;
  on CN 100 the rain is the factor times the unreduced run's to 2e-9; on the CN grid the dam line reads 509.44 m3/s
  against 528.88 unreduced.
- The HMS project loaded and the table left empty: the dock says the project's table is used, the job carries ARF FM
  with HMS's own below-the-table rule, the same factor and the same 509.44 m3/s, over the control file's 48 h.
- Depth-area study on the gridded storm at 10, 20.971 and 30 km2: three runs, each reduced at its own area (0.987,
  0.9749319, 0.965); the 20.971 km2 run is the single reduced run to the digit and the design peak is its peak
  (509.44); 518.84 > 509.44 > 501.90 m3/s with storm area. The flow accumulation raster went into the study job with
  the composite map off, and no map was written.
- **By the change of area reduction** is offered at 0.05, and the dock lists the run(s) before the study.
- Result lines on the study: the panel says it is a study and how its lines read; the design line is listed as a design
  line and reads its own 20.971 km2 run; a 300 m line drawn through the real map tool across the wadi above Bidah 03
  (where it was clicked, within two 5 m pixels) read 19.48 km2 on the raster and was drawn from the 10 km2 run at
  weight 0.100 and the 20.971 km2 run at 0.900, peak 442.7 m3/s, its words under the heading, on the plot 1.9 s after
  the last click. A first round drew the line with the map zoomed out to the whole domain, where a click lands on a
  pixel tens of metres wide; it read 20.06 km2 on a line four times too long, so the check now zooms to the line.

## Tests

- New: `tests/storm/test_arf_steps.py` (the step rule: counts 9, 21, 40, every step within the limit, equal steps, no
  run a hair below the end, a table that rises again, the whole depth below HMS's first area), ARF on gridded rain in
  `tests/storm/test_rain_frames.py`, `tests/engine/test_rain_run.py` (cells, losses after the reduction, the no-ARF job
  unchanged, the factor in words), `tests/engine/test_arf_cli.py` and `test_arf_network.py` (a study on gridded rain
  gives the design storm's design flows; lumped elements rerun at their own area; the step rule through `storm_areas`),
  `tests/engine/test_study_lines.py` (a synthetic two-run study: the blend equals the hand-weighted runs, a line on the
  design line gives the study's design-point answer within 2 %, the clamp both ways, no raster, the command in one
  request, the composite switch, the job hash), and the plugin's rows, contract (the dock's step areas are the
  engine's) and line-view tests.
- `tests/storm tests/hydrology tests/engine tests/plugin tests/dock tests/products`: **1,371 passed, 1 failed** on the
  code before the last plot-note change, then the folders touched since (`tests/plugin`, the study, ARF and
  result-line tests) **553 of 553**. The one failure is `tests/hydrology/test_block2_replication.py`, which reads his
  HMS project live and fails the same way on the base commit since he added Basin 2 and 3 (below).

## Not done, or his call

- **The grids are not the frequency storms.** Over S13 the RP100 grid holds 0.65 x FM_100yr's point depth, RP10000
  0.49 x. Which rainfall governs the design is his call; W39 asked the same of RP200.
- **The PMP grid is 1.5 x the 10,000-yr grid capped at 1,500 mm**, a different file from W39's PMP raster: which PMP
  is meant is his call.
- **The DSS twins carry 0.1 to 0.6 % more rain than the NetCDF** over Bidah 03, from the resampling to SHG; the NetCDF is
  the source file.
- **The step rule reads the table linear in area**, as the runs and HMS do, so its areas differ from his log-area
  reference list beyond about 100 km2 with the same count (9 at 0.05). If he wants the log reading, the factors the
  runs apply would have to change with it.
- **Lines after a study:** a line blends the two runs; its frames are the smaller run's times, at most seconds apart
  from the other's. Not built: points after a study (a point has no flow; it would need the same blend of depth), and
  the lumped elements' series in a study's list (each run's is one storm area's).
- **Dock change to note:** the flow accumulation raster now goes into a study's job whenever one is chosen, with
  `arf.composite` False when the map is unticked; before, it went in only with the composite map.
- The Bidah 03 domain of W39 leaves a pond 7.5 to 8.8 m deep against its edge in every run; not looked into.
- The owner's HMS project changed on 2026-11-11 (Basin 2, Basin 3, `DA_*_B2`, `DA_*_B3`): the existing test
  `tests/hydrology/test_block2_replication.py`, which reads that project live, now fails on the base commit as on this
  branch (`DA PMP B2`, `DA PMP B3`: "no grid cell is centred in these polygons", then an IndexError in the report). Not
  this work's; it needs the test or the replication updated to the new analyses.
