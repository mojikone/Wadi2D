# W27 basin wiring (D6b)

[PRESERVE-CHECK]

KEEP, untouched in behaviour, numbers to the last digit for any job without `hydrology.basin_json`:
- The solver kernels on both backends, the steppers, the mesh, the tables. No kernel is edited.
- An HMS job: `_network`, `_check_routes`, the hand-back of `W25`, the base lumped run, `Forcing`, the balance, checkpoints.
  `plan_routes` keeps its cuts and its refusals for an HMS basin; the new switch is off there.
- The dock's HMS route and plain rain-on-grid route: the same widgets, the same values, the same job. `merge_hms` untouched.
- `basin.json` as `W24` wrote it reads as before: a file without `routes` or `settings.lag_method` is the NRCS one.

CHANGE:
- Job contract: `hydrology.basin_json`, `hydrology.subbasins[].parameters` (an override per generated subbasin), `basin` (the
  `BasinSettings` of `W24`, now a part of the job, with `lag_method`, `handback_span` and `handback_min_cells`),
  `hydrology.overlap_share`. `job_hash` leaves `basin` and `overlap_share` out: the run reads `basin.json`, whose bytes it hashes.
- The lag of a generated subbasin by `basin.lag_method`: `nrcs` (default) or `hms_kirpich`, 0.474 x Kirpich on the longest path
  and the 10-85 slope, the rule `W24` found under HMS's lags. Applied where the lag is derived (`refresh`), so `basin.json`
  records which method made its lags. `wadi2d basin` starts from the job's `basin` part; `--settings` and the flags override.
- `basin.json` gains a derived top-level `routes` list (the junction routes), written by `assemble`; readers that do not know it ignore it.
- `basin.gpkg`: the subbasin polygons are written pixel-exact, not simplified (why: below).
- New `wadi2d/basin/job.py`: a job on a generated basin resolves, before anything else, into the same contract an HMS job uses:
  every subbasin with its mode (incomplete ones to `2d`, with a warning naming what is missing), one `Inflow` at every junction
  whose route is `none` (its water enters the grid there), one `Handback` at every junction with a reach below that 2D water can
  reach, and the junction-to-junction links cut in the lumped engine. The resolved job is what `config.resolved.json` holds.
- `plan_routes` gains `cut` (links decided elsewhere) and `cut_entries` (False for a generated basin: the lumped water above a
  hand-back's junction stays in the network, because the routes already say what is on the grid; and a route may then reach the
  next entry, which is one more live element).
- `_network` takes the lumped network from `basin.json` when the job names one; `_lumped_rain` no longer needs an HMS file; a
  depth grid on a generated basin is refused in words (not built).
- New `wadi2d/engine/rain_once.py`: two subbasin polygons sharing more than `hydrology.overlap_share` (1 %) of the smaller stop
  the run, with the cell count and the names; less is a sliver along a digitised edge, warned and masked once. Runs for every
  job with polygons; Block 2's HMS polygons pass without a note at 40 m and 20 m.
- New `wadi2d/engine/network_series.py`: the lumped network's inflow and outflow of every element go to `results.h5` and
  `series/network_<element>.csv` for every job with a lumped network, HMS or generated. New files beside old ones; no old
  number moves.
- `progress.jsonl` gains one `basin` event per run on a generated basin: every junction's route, what enters the grid where,
  the hand-back lines, the incomplete elements.
- `map_notes.water_note`: water from the hills is `inflow_m3 - reentry_m3`, as `W25` asked.
- Plugin: section 3 gains "Generate the basin from the DEM" (`sections/basin.py`, rows in `sections/basin_rows.py`), the
  junctions table, the hand-back line rows and the transmission loss row; a structure layer's `name` field names the object
  (so a crest line names its reservoir); `hydrology.py`, `job_builder.py`, `dock.py` and `protocol.py` get the smallest edits
  that hold them; `basin_layers.py` and three styles load `basin.gpkg`.

FILES:
- New: `wadi2d/basin/job.py`, `wadi2d/basin/geometry.py`, `wadi2d/engine/rain_once.py`, `wadi2d/engine/network_series.py`,
  `plugin/wadi2d_qgis/sections/basin.py`, `plugin/wadi2d_qgis/sections/basin_rows.py`, `plugin/wadi2d_qgis/basin_layers.py`,
  `tests/basin/test_job.py`, `tests/engine/test_basin_run.py`, `tests/engine/test_rain_once.py`, `tests/plugin/test_basin_rows.py`,
  this folder.
- Edited: `wadi2d/config/schema.py`, `wadi2d/run.py`, `wadi2d/forcing.py` (`load_polygons`, four lines), `wadi2d/basin/contract.py`,
  `wadi2d/basin/parameters.py`, `wadi2d/basin/build.py`, `wadi2d/basin/layers.py`, `wadi2d/engine/cli.py` (`_basin`),
  `wadi2d/hydrology/live_network.py` (`plan_routes`), `plugin/wadi2d_qgis/sections/hydrology.py`, `.../sections/structures.py`
  (`_parts`), `plugin/wadi2d_qgis/job_builder.py`, `plugin/wadi2d_qgis/dock.py`, `plugin/wadi2d_qgis/protocol.py`,
  `plugin/wadi2d_qgis/style.py`, `plugin/wadi2d_qgis/map_notes.py`, `plugin/wadi2d_qgis/README.md`, `tests/plugin/schema_sample.json`,
  `tests/plugin/test_contract.py`, `tests/plugin/test_map_notes.py`, `tests/basin/test_model.py` (one test flips),
  `tests/hydrology/test_live_network.py`.

[BROAD] by the rule: several modules, one existing function's signature extended, one output file format extended. The owner
said not to stop, so the proof is `old_jobs_check.py` below, as `W23` and `W25` did it.

## State (2026-11-02, branch `feature/basin-wiring`, cut from local `main` at `e756f7c`; not merged, not pushed)

**D6b is in the plugin and run through the real dock: a basin generated from the DEM runs lumped by default, any subbasin switches
to rain-on-grid, an element lacking a parameter is refused into rain-on-grid by name, the junctions route HMS style where a reach
exists and feed the grid where none does, and 2D flow reaching a junction with a reach below leaves the grid at a hand-back line
built from the routes, with the books closed. Bidah, 52 of 52 through the dock; Block 2, 26 of 26, generated against the HMS project under the same storm (table
below). The full suite: 1,680 passed, exit 0; ruff clean. Old jobs give their numbers to the last digit (table below).**

Live. Supersedes nothing: `W24` holds the terrain side and the lag finding, `W25` the hand-back's own proof.

## The design as built

The rule of the brief is that the user never types an inflow for a generated basin. So a job that names `hydrology.basin_json`
is **resolved** before anything else (`wadi2d/basin/job.py`), into the contract an HMS job already uses:

| From `basin.json` and the job | What the run gets |
|---|---|
| A subbasin with its parameters complete | `mode` as the job says, `lumped` by default; its polygon masks the rain |
| A subbasin lacking a parameter (`missing` not empty) | `mode: 2d`, whatever the job asked, and a `warn` event naming it and what it lacks; a `parameters` override in the job can complete it (source `job`; an override of a lag input re-derives a derived lag) |
| A junction or reservoir whose route is `none` (no reach, a reach lacking a parameter, or the outlet) | an `Inflow` at its outlet, element itself: its network outflow enters the grid there and runs over the ground to the next junction; the link below it is cut in the lumped engine |
| A junction with a complete reach below, and 2D water able to reach it (a 2D subbasin draining to it, or a junction above whose water is on the grid) | a `Handback` line there, element the junction (or the reservoir), square to the reach below, `handback_span` x the valley width at `section_depth_m` long, at least `handback_min_cells` cells; one cell down the reach at a junction, three cells up the axis at a dam |
| Everything else | stays in the lumped network: a reach-routed hydrograph never touches the grid until the junction where the routes say it leaves |

`plan_routes` on a generated basin keeps the links into a hand-back's junction (`cut_entries=False`): the lumped water above it
is the live network's lateral inflow, known before the run, and only the 2D water crosses the line. That is why the all-lumped
generated run carries no hand-back delay at any junction, and why a chain of lines down a wadi is allowed (each entry is the
next live element). The resolved job is `config.resolved.json`; every inflow and line the run built is written there.

**Why the override is a job field and not an edited copy.** `basin.json` stays the record of what the terrain gave; a scenario
is a job, and the run folder reproduces itself from `config.resolved.json` and the basin file's bytes (hashed for checkpoints).
An edited copy of `basin.json` still works (the contract marks a filled value `user`); the dock does not write one.

**Why the polygons are exact.** The rain-once check caught, on its first run, the generated polygons of `W24` overlapping along
shared edges: each was simplified on its own, and 50 of 60,000 cells of the test valley lay under two lumped polygons. Simplified
as a coverage the edges still moved up to a pixel and cells along them changed owner, 0.2 % of the water. Unsimplified, the
polygons are exactly the pixels the areas count: the 2D twin of a subbasin rains on 1.4902 km2 against 1.4902 km2 lumped.

**Why the check measures overlap and not ties.** With 20 m cells on 5 m pixels a cell centre sits on a shared edge and the
rasteriser burns it for both polygons; the forcing masks it once, so nothing is counted twice. Block 2's own HMS polygons
"overlapped" 442 cells at 40 m that way and share no area. The check intersects the polygons (made valid first: the HMS ones
self-touch at one spot), counts the cells of the domain under the shared area, and stops over `overlap_share` of the smaller.

## Proof through `run_job` (`tests/engine/test_basin_run.py`, the synthetic valley, CPU)

The valley of `tests/basin/conftest.py`: two arms join at the fork J2, the reach R1 runs to the outlet J1, every pixel drains
to J1; three subbasins. CN 85 everywhere, 60 mm in an hour: 27.17 mm of excess by the SCS formula by hand, on every cell and in
every lumped twin alike. Six hours, so the lumped hydrographs end.

| Case | What is checked | Result |
|---|---|---|
| Lumped by default | no rain on the grid; the outlet's inflow is the whole excess of 6.0 km2; one inflow, at J1; no line; `basin` event; no warning | rain 0; inflow within 0.2 % of 163,027 m3; grid error under 1e-6 |
| One arm in 2D | the grid's rain is that arm's excess; the lateral is the other two; a line at J2 square to R1; what crossed is 0.9 of the rain and more; the whole closes to the Muskingum-Cunge defect | rain 40,490 = 27.17 mm on 1.4902 km2; line 254 m = 1.5 x the 169 m width the fit gives at 4 m; the series of the arm is not in the network, the line's is |
| Incomplete subbasin, asked lumped | runs, as rain-on-grid, the warning names it and `curve_number`, `not lumped as asked` | yes |
| The same with `parameters: {curve_number: 85}` | runs lumped, no warning, the override in the resolved job | yes |
| Two overlapping lumped polygons (plain route) | stopped with the count and the names; the 2D-under-lumped case too | `5000 cells lie under both lumped subbasins West and East (50.00 % of the smaller...` |
| No reach anywhere (`min_reach_m` 5,000) | an inflow at every junction, the link below the fork cut (the outlet's network inflow is the valley subbasin's alone), the fork's water reaches a line 4 cells above the outlet over 1.5 km of ground | the line carries 80,909 m3 against 80,969 of the two arms by hand, 0.07 % |
| `preflight` and the dry-run estimate | take a generated job | yes |

`tests/basin/test_job.py` holds the resolution alone: modes, overrides, the line's geometry, the cuts, idempotence, the report.
`tests/hydrology/test_live_network.py` holds the chain of entries with the links kept.

## Through the real dock: Bidah (`checks/dock_basin_bidah.py`, `log_dock_basin_bidah.txt`, 52 of 52)

Block 2's ground around Bidah at 20 m, the dam's three crest pieces (one named Bidah 03, two saddles) and its spillway as
structure layers, the project CN raster, 60 mm/h for an hour, 3 h. Generated at 2 km2: 8 subbasins, 4 reaches, 4 junctions, 1
reservoir (the named crest line, rating complete), 6.43 km2 of ground that reaches the domain edge without meeting a stream.
Picture: `basin_bidah.png`; the section: `hydrology_section.png`.

| Step | Checked | Numbers |
|---|---|---|
| Lumped by default | the table shows 8 rows lumped; the junctions table 5 rows; the run's `basin` event; network series for all 17 elements; the only rain on the grid is the unassigned ground's | rain 185,520 m3, inflow 405,428, error 1.9e-8 |
| S2 to rain-on-grid | a line built at Bidah 03 (a reservoir: three cells up the axis), `two_d_sources` S2; the same water for S2: its lumped hydrograph against the rain the grid gained; what crossed plus what is still on the grid is that rain | 65,944 lumped against 65,921 on the grid; crossed 58,386 + 7,585 still on the grid = 65,971; whole error -2.3e-4, the Muskingum-Cunge defect of R1 |
| No CN anywhere | every row 2d and locked, tooltip and summary name `curve_number`; the run warns by name; a line at every reach junction, chained to the outlet | lines at Bidah 03, J2, J3, J4 |
| Hand-back rows | a line layer gives one row per line with the generated elements as choices; the job carries name and element | |
| Transmission row | off by default; on at 25 mm/h the job has `transmission.enabled`; off leaves it out | |
| HMS switch | an HMS folder unticks and disables the box and shows the 18 HMS subbasins; clearing it brings the generated 8 back | |

The one warning of every run, water 5.3 m deep against the domain edge, is the test domain's western edge, where rain on the
unassigned ground ponds against the wall; `W15` had the same domain.

## Through the real dock: Block 2 generated against the HMS project (`checks/dock_basin_block2.py`, `block2_peaks.json`)

The whole Block 2 domain of `W1` (810 km2) at 40 m, the five dam axes of `W24/jobs/block2.json` as a named crest-line layer, the
project CN raster, Manning 0.1 (HMS's own reach n, as `W24` used it), the W1 outlets as normal boundaries. The storm is the HMS
100-yr storm on the dock's design page: 205.4 mm in 24 h, the FM pattern, the `ARF FM` table, **storm area 74.3 km2 for every
site** (what the HMS import gives the HMS route; `W24` ran each site at its own area, so its numbers are not these). Three runs
through the dock, nothing tuned:

1. Generated at 10 km2 with the NRCS lag (41 subbasins, 18 reaches, 21 junctions, 5 reservoirs; the five dams lack a spillway, so
   they pass their inflow on as junctions and the run says so), all lumped, 30 h.
2. The same generated again with the HMS-style lag (`basin.json` records `hms_kirpich`), all lumped, 30 h.
3. The HMS project through the dock's own HMS route, all 18 subbasins lumped, 48 h from the control file.

The five dam peaks are the lumped network's inflow at each dam element (`series/network_<dam>.csv`, new in this iteration), which
on the HMS route is the HMS replication of `W1` and is untouched by the grid. Picture of the generated basin: `basin_block2.png`.

| Dam | HMS, m3/s at h | Generated, NRCS lag | / HMS | Generated, HMS-style lag | / HMS |
|---|---|---|---|---|---|
| Faydh 01 | 993.5 at 13.25 | 1,443.4 at 12.67 | 1.453 | 988.5 at 13.08 | 0.995 |
| Bidah 03 | 343.6 at 12.75 | 361.9 at 12.58 | 1.053 | 330.6 at 12.75 | 0.962 |
| R5A | 921.5 at 14.75 | 1,333.9 at 13.33 | 1.448 | 810.0 at 14.75 | 0.879 |
| R2A | 1,464.0 at 14.25 | 2,329.2 at 13.25 | 1.591 | 1,849.8 at 13.67 | 1.264 |
| Z4C | 1,826.0 at 15.50 | 2,158.5 at 15.17 | 1.182 | 1,751.8 at 15.58 | 0.959 |

- [Certain, measured] The NRCS row is `W24`'s threshold-10 row to the second digit (1.45, 1.05, 1.46, 1.58, 1.18): the dock
  reproduces the engine-only finding. Faydh 01 on the HMS route, 993.5, is `W24`'s 994 at the same area.
- [Certain, measured] The HMS-style lag reads closer to HMS than NRCS at every dam, 0.88 to 1.26. R2A at 1.26 is new: `W24`'s
  diagnosis row (0.98 there) was on the aligned 18-subbasin model; at the 10 km2 threshold R2A's catchment is subdivided and the
  lag rule is not additive over subbasins, as `W24` found for NRCS (up to 0.18 x HMS from the threshold alone). Which lag and
  which threshold is his call; the dock now switches both.
- The scenario ran twice (the first time a check compared the storm area to three decimals the dock's spin box does not hold):
  four dams repeated their peaks to the digit, R2A moved 0.03 % (2,329.8 then 2,329.2 with NRCS, 1,849.9 then 1,849.8) between
  two generations of the same ground. [Guessing] WhiteboxTools' breaching breaks a tie differently from run to run and a pixel
  or two of R2A's 176 km2 changes side. Not chased.
- Rain on the grid in the generated runs is the 80.4 km2 of ground that reaches the domain edge without meeting a stream: 11.9
  Mm3 against 115.7 Mm3 of inflow at the junctions. Grid error 2.2e-8.
- The HMS route's one warning, water 21.1 m deep against the domain edge, is the `W1` domain's own; the generated runs have none
  beyond the five reservoirs lacking a spillway.

## Old jobs give their numbers to the last digit (`old_jobs_check.py`)

`W25`'s script, with one change in `compare`: an item the branch writes and the base did not is listed as added, not as a
difference, and a base item that moved or vanished still fails. The base is local `main` at `e756f7c`, exported with
`git archive` to the scratchpad so it could not move, run with its own `wadi2d` first on the path (`PYTHONPATH`; the script's
folder is first on `sys.path` otherwise and `import wadi2d` falls through to the editable install, which is how the first
attempt measured the main checkout against itself). Every dataset and numeric attribute of `results.h5`, every GeoTIFF band,
every series CSV and the numbers of the done event, hashed one by one; run times left out.

| Job | Backend | What it uses | Base items | Identical | Added on the branch |
|---|---|---|---|---|---|
| Valley, uniform storm, CN, free boundary, points and lines, pixel maps | CPU | rain-on-grid, the products after the run | 65 | **65** | 0 |
| The same | GPU | | 65 | **65** | 0 |
| The same with a hyetograph and local time stepping | GPU | D5's storm, the level stepper | 65 | 59, the 6 others the base does not repeat itself | 0 |
| Plane, table inflow, stage boundary, initial level | CPU | injection, fixed level, initial water | 40 | **40** | 0 |
| Mesh, HMS basin, lumped subbasin at its outlet | CPU | quadtree, lumped network before the run | 40 | **40** | 8: the network series of its 4 elements |
| Block 2 hybrid, all 18 subbasins lumped, 40 m, 6 h | GPU | the real HMS basin, CN raster, ARF storm, 3 boundaries, 5 dams' lines | 96 | **96** | 160: the network series of its 40 elements |

**365 of 371 base items identical to the last bit; the 6 others are the last digits of `rain_m3`, `error_m3` and the relative
error of the local-time-stepping job**, which a second run of the base code moves by itself (`old_jobs_base_again.json`; the
monitor credits a window's rain at progress ticks that the wall clock times, as `W25` read in `Monitor.settle`). `compare`
exits 0 (`old_jobs_compare.txt`). The 168 added items are the new `series/network/*` datasets and CSVs; no old file changed.

On the way the check found two faults of this branch on the Block 2 hybrid, both fixed and tested: the rain-once check
stopping the job on rasteriser ties (442 cells at 40 m), and GEOS refusing to intersect the HMS polygons, which self-touch at
one spot.

## What was not tested, and what is weak

- **The hand-back at a dam is placed, not validated.** The line sits three cells up the axis; on Bidah it took S2's water into
  the pool and the books closed, but no case compares a 2D flood entering a lumped pool against the same flood routed on the
  grid through the crest faces. `W25` did that for a reach, not for a reservoir.
- **The line's length is the fitted width at `section_depth_m` times 1.5.** `W24` said the fitted section reads a narrow
  low-flow channel in a wide bed. A line shorter than the flood may be passed round its end; the open-share warning and the
  drawing are the only tell (`W25`'s weak point stands). Not seen on Bidah or the valley.
- **A hand-back's 2D water is caught only where the routes say 2D water can come.** Rain on the unassigned ground and on gaps
  between polygons (none now, the polygons are exact) runs down the corridor of a lumped reach in 2D and rejoins at the next
  junction where the network re-enters: not lost, not doubled, not routed HMS style either.
- **The lag choice and the threshold move the dam peaks by up to 0.6 x HMS between them** (table above). No gauge says which is
  right (decision 20); the dock gives him both switches and the numbers.
- **Not run:** a depth-grid storm on a generated basin (refused in words); a gridded storm on one (the code path exists,
  untested); a generated basin with a mesh (`mesh.enabled`); a resume of a generated-basin run (the hand-back's own resume is
  `W25`'s); a 2D subbasin draining to a reservoir with a complete rating and its outflow re-entering the grid below (Bidah's
  reservoir route continues through R1 to J1); the full 15,398 km2 extent; a PC without an NVIDIA card.
- **The hand-back rows of the dock were not run through a job:** the rows, the choices and the values are checked; a run with a
  user-drawn line on a generated basin is not (the built lines are).
- **The double-rain check is engine-side only through the dock:** the dock has no way to make overlapping polygons; the stop is
  proven through `run_job` on the plain polygon route.
- **Network series are written for HMS jobs too.** New files beside the old ones: the lumped hydrographs of mode (b) were only
  visible as injections before. If that is unwanted it is one line in `_network`.
- **ruff clean; `ruff format --check` lists 37 files that predate this branch**, so black is not this repository's gate.
