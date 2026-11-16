# W101 dock redesign part 2

**Status (2026-11-16): branch `feature/dock-redesign-2` off `feature/fast-products` (`75be51e`); not merged, nothing
pushed. Built item by item under a usage ceiling (96 % of his 99 % when his item 7 was added): item 1 and item 7 (the
map controls, added mid-task) are built and tested; items 2 to 6 are not started.** Requirements: `W94 dock
redesign/README.md`; part 1's record: `W99 dock redesign part 1/README.md`.

## Item 1: rain and area reduction (built)

Three sections now hold what Storm held:

- **3b. Data tables** (`sections/tables.py`, plain rules in `table_rows.py`): the model's named rain patterns and
  area-reduction curves, as HEC-HMS keeps paired data. A pattern is time and depth, its time in percent or a fraction
  of the duration, or hours or minutes, its depth cumulative or incremental; a curve is area and factor, and what holds
  below its first area. New, Rename (in place, no dialog), Remove; each table has its chart (the share of the depth
  fallen; the factor on log area) and the engine's own checks in words under it. The store is the section's saved
  state; **a job carries only the tables its storm names**, so a store nothing reads changes no job.
- **4. Storm**, six sources: Fixed depth (uniform in time), Depth and pattern, Depth grid (a raster of mm) and pattern,
  Gridded rain (DSS, NetCDF or GeoTIFFs), Rain gauges, A hyetograph as received; and the HMS meteorologic file when a
  project is loaded. A pattern is Uniform, SCS type I, IA, II or III (HEC-HMS's own tables, W98; choosing one sets
  24 h, and another duration is refused in words), or a pattern of Data tables by name. **The Steady rain is retired**:
  a fixed depth writes the job it wrote (`uniform`, depth over duration), and an older check that sets its mm/h and
  hours gets that job to the last digit.
- **4b. Area reduction** (`sections/reduction.py`, rules in `reduction_rows.py`), a lumped part and a 2D part, each:
  none, a coefficient, at one storm area read on a curve (its factor shown, and marked on the curve's chart), or the
  curve itself. The lumped curve says what it does: each lumped subbasin read at the drainage area of the element where
  its water enters the grid (W98), each element at its own area in a Lumped model, each run's storm area in a study. The
  2D part's fourth choice is **By the depth-area study** (section 9), with the area a single Run reads it at. A 2D model
  shows only the 2D part, a Lumped model only the lumped part. Observed rain (a hyetograph, gauges) takes none, and the
  section says so; the HMS storm keeps its own, with the HMS depth-area tick (each element at its own area) here.
  Hydrology's "Each element at its own drainage area" tick is gone: it is the lumped part's curve.

**What the job holds.** Where every part the model has is the same coefficient or the same fixed area, the storm
keeps the single-storm form the engine always read (`storm.arf_factor`, or `storm.storm_area_km2` with `storm.arf`),
which applies one factor to the lumped subbasins and the 2D cells alike: **a model of the old dock writes the job it
wrote**. Anything else, and every `depth` and `depth_grid` storm, writes `storm.area_reduction` with the curves by
name and the job's `data_tables` with those curves. The HMS project's table can still be read at one area for both
parts (the import fills it in); a split on it is refused in words.

**The saved model is format 3** (`model_doc._to_3`). A format 2 model opens with, in words: its Steady rain as a fixed
depth (the same job); its design storm as a Depth and pattern, the pattern put into Data tables as "Design pattern" and
the reduction table as the curve "Area reduction" (**the job changes form**: kind `depth` with a named pattern and
`storm.area_reduction`, which W95 holds equal to the design storm to the digit); one storm area or a given factor as
both parts alike (the same job); the old "By the depth-area study" as the lumped curve and the 2D study at the old
area (**a single Run's lumped subbasins are then read at their entry areas, no longer at that area**; a study is as
before); Hydrology's by-element tick as the lumped curve (the HMS storm: the tick in 4b). A run with only its job is
read back the same way (`job_states`).

Tests. `tests/plugin/test_reduction_rows.py` 19 (every encoding against the engine's schema, the factor against the
engine's `ArfTable` to 1e-12, each pattern refused where `PatternTable` refuses it, the migration). `smoke_qgis.py`
rewritten for the new sources (fake and real engine, both pass: the fixed depth reduced at 505 km2 reads 0.75 in the
engine's preview, the coefficient 0.7, the 2D part's own reduction on a depth 0.75 while the lumped part is 0.6).
Rerun and passing: `test_storm_rows.py` 29, `test_job_builder.py` 47, `test_study_rows.py` 24, `test_model_doc.py` 8,
`test_section_status.py` 13, `test_model_types.py` 11, `test_job_states.py` 5 (two of its checks rewritten: the old
widget names are gone). Through the real dock: `dock_rain.py`, see the table below.

## Item 7: the map controls (his, added mid-task; built)

His words of 2026-11-16, applied (`sections/run.py`, `window_links.py`, `window_rows.py`, `sections/terrain.py`):

1. **Map pixel** in Run, under the pixel-map tick: Automatic (empty, the engine's rule of W100) or a pixel in m
   (`outputs.pixels.pixel_m`).
2. **Map a window at the terrain's finest resolution**, beside the time sliders: a rectangle dragged on the map,
   `wadi2d window` on it at the DEM's own pixel (`--pixel 0`), and its depth, speed and hazard rasters loaded into the
   run's group under "Window at the DEM pixel, ...". Named for the terrain, not "0.5 m": the tooltip gives this DEM's
   pixel. The run's own maps are not touched.
3. **No choice of surface**: the dock writes none, so the pixel maps are the continuous surface (the engine's default);
   the cell maps stay one value a cell; `corners` and `cell_fill` stay loadable in the engine for old jobs.
4. **Depth x speed raster**, a tick, off by default (`outputs.pixels.dv_raster`).
5. **A Lumped model's Terrain** hides the cell size, Manning and the pit fill (their values kept for the day the type
   has a 2D part again). See Found 1: a generated basin still reads Manning for its reaches.

At the defaults the job holds no `outputs.pixels` at all, so an older model writes the job it wrote. The results page
(item 6) is not built, so the window button lives in Run beside the other map tools, which item 6 would move.
Tests: `tests/plugin/test_map_controls.py` 4 (the job at the defaults, both settings written and taken by the
engine's schema with the continuous surface, none without pixel maps, the window's command and folder).

## Tests through the real dock

| Scenario | What it proves | Passed |
|---|---|---|
| `dock_rain.py` | item 1: the sections in their places; Data tables (add, the next free name, a refused table Missing in words, rename, remove, both charts); six sources, the Steady rain's mm/h giving its job; SCS sets 24 h and refuses 6 h; a pattern by name carried into the job and filled in by the engine; a depth grid; the parts by model type; one area for both parts = the old form, parts that differ = `area_reduction`; the study's single-run area; **a real run on Bidah of a depth with a pattern of Data tables and the 2D part's own reduction, the engine's factor equal to the dock's**; saved and brought back to the same job; a format 2 model's steady rain and design storm moved, in words | 54 of 54 |
| `dock_fixes.py` | his two faults: in a project whose first raster is a run's depth map, the dock starts on the DEM the run was made on; with it gone, nothing, and Terrain Missing; a raster no run names is not taken; the DEM's own file under a results group taken for want of another; a project read with no saved model chooses again; the Storm stack as tall as the page shown (101 px for a fixed depth, 447 for the gauges) | 14 of 14 |
| `dock_maps.py` | item 7: Map pixel Automatic first, the depth x speed raster off, no surface choice shown, no pixel settings in the job at the defaults; the window button's name and its tooltip with this DEM's pixel; Lumped hides cell size, Manning and pit fill, 2D and no type show them; **a real Bidah run with a 10 m pixel and the raster: the maps of record at 10 m, `pixel_dv.tif` written; a window of 800 m mapped at the DEM's 5 m pixel, depth, speed and hazard loaded into the run's group, the run's maps untouched** | 23 of 23 |

## His two faults of 2026-11-16 (fixed)

1. **The DEM picker took the first raster of the project**, which in his W100 project of results was a depth map.
   Terrain now starts on the DEM a run in the project was made on (the `job.json` of the run folder a layer's file lies
   in), never on a run's own raster (a file in a run folder's `pixels`, `maps`, `windows` or `composite`, or a layer
   under a "Results – ..." group, unless it is that DEM's own file and no other copy exists); with none, the picker is
   empty and Terrain says Missing (`dem_choice.py`). Chosen when the dock is made and when a project with no saved
   model is read.
2. **Storm's short pages stood over a gap** the height of the tallest page (a `QStackedWidget` is as tall as its
   tallest page). The pages now lie in a column with all but the shown one hidden (`sections/page_stack.py`, the same
   calls): a fixed depth's stack is 101 px where it was 447.

`dock_fixes.py` 14 of 14 (below). The headless smoke test set the DEM by hand where it had relied on the first raster.

## Older dock scenarios: the same counts and the same jobs

The ten W99 used, on the base (`75be51e`) and on this branch at item 7 (`2b92b41`), each batch from its own copy:

| Scenario | Base | Branch |
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

**Every job they wrote is the same**: 22 of the runs' `job.json` identical to the character once each batch's folder
is taken out (W99's `compare_jobs.py`), and the 5 profile-editor preview jobs on each side pair up, 3 identical and 2
differing only in their random scratch names (W99's `compare_previews.py`), as in W99. The four that do not pass stop
at the same check on the base. These run the Steady rain's mm/h through the new fixed depth, so they are also the
proof that it writes the old job. Logs in `old_scenarios/`. The faults' fix came after this batch; it changes no job.

## Found on the way

1. The generated basin's reaches take their Manning n from Terrain's Manning (`wadi2d/basin/elements.py`
   `_manning`, read at Generate basin): a Lumped model that hides Manning in Terrain (his item 7, point 5) leaves the
   generated reaches on a value nobody sees. A reach-n field in the basin box would close it; not built.
2. `PairTable.set_rows` wrote six significant digits (`:g`), so a table of seven digits came back rounded from a saved
   model; now ten.
3. Older dock scenarios that drive the old Storm widgets (`W20`, `W37`, `W39`, `W53`, `W54`, `W77 dock_storm`) no longer
   find them: the sources changed by design. Not rewritten.

## Not done

Items 2 to 6 of the brief (losses and roughness, boundaries, the Mesh section, the domain from an outline, the results
view) are not started: the usage ceiling. What each needs from the engine is already there (W95 to W98); the part 1
record's "What the next parts need" still holds, and the new sections show the pattern (`sections/tables.py` for a
store shared by sections, `sections/reduction.py` for a section shown by model type, `table_rows.py` and
`reduction_rows.py` for the plain rules beside a `pytest` file).
