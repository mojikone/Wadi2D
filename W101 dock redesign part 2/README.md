# W101 dock redesign part 2

**Status (2026-11-16): branch `feature/dock-redesign-2` off `feature/fast-products` (`75be51e`); not merged, nothing
pushed. Items 1 to 6 of the brief, his item 7 (the map controls and the one depth threshold), his two faults and his
job-import item are built, each committed alone and tested through the real dock (table below); what is not done is
under Not done.** Requirements: `W94 dock redesign/README.md`; part 1's record: `W99 dock redesign part 1/README.md`.

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

## Item 2: losses and roughness (built)

- **Manning given as** (Terrain), four forms (`land_rows.py`): one value; squares and aligned cells apart (a second n
  for the aligned cells, `terrain.roughness` form `split`, refused in words without the aligned cells); a grid of n;
  land-use classes (a raster of class codes and a table of code, n and name, form `land_use`; the value above is what
  a cell no class covers takes). Only the chosen form's fields show; a Lumped model shows none. **One value and a grid
  write `terrain.manning` and `terrain.manning_raster` as the dock always did**, so an older model writes its job; a
  model from before with a Manning raster opens as a grid (the raster's choice sets the form).
- **CN override** (Hydrology, `hydrology.cn_override`): none; by land-use class (a raster and a table of code, CN,
  name); by CN range (from, to, becomes; overlaps refused in words, as the engine refuses them); by subbasin (name,
  CN). The table's columns follow the choice; written only when one is chosen.
- Both come back from a job (`job_states`), both are in the sections' status words, and a missing table, a class
  twice, overlapping ranges or an unnamed subbasin is Missing in words.
- Tests: `tests/plugin/test_land_rows.py` 5 (each form's job taken by the engine's schema, one value and a grid the job
  of before, the refusals, a job read back); the dock bounds a CN range above 0 as the engine does.

## Item 3: boundaries (built)

- **A flow line's hydrograph typed at a step**, HEC-RAS's table (`flow.step_s` and `flow.flows`, W96): the box under
  the boundary table shows the flow line chosen there, "Hydrograph from" a file (the table's column, as before) or a
  table typed here, the step in minutes, the energy slope that shares the flow across the line (blank is the engine's
  0.005) and the chart of the flows against hours. Kept on the table's rows, so saved and brought back with the model;
  a job read back gives its typed table and slope to the row of its line. Fewer than two flows, a step of zero or a
  flow below zero is refused in words; a file stays the job it was.
- **Initial levels from points** (`initial_points`, W96) in Structures beside the start water: a point layer, its
  level and name fields; a point with no level is refused in words. An imported job's points go into its GeoPackage.
- Tests: `tests/plugin/test_inflow_tables.py` 5 (the table the engine's schema takes and writes out at the step, a
  file's job unchanged, the refusal, the points, the job read back). Through the dock `dock_inflows.py` 17 of 17, with
  **a real Bidah run whose engine read the typed table: 63,000 m3 entered, the table's own volume (0, 50, 20, 0 m3/s at
  15 min)**.

## Item 4: one Mesh section (built)

- **Mesh kind first** (`sections/mesh.py`, rules in `mesh_kinds.py`): Squares (Terrain's cell size everywhere), Quadtree
  (finest on the wadis, coarser on the hills), Aligned centre mesh (`strips.generator: centres`, cells along the
  streams, squares beyond). Each kind shows its own box: the quadtree its coarsest cell, the two wadi areas, zones and
  the refinement lines table; the aligned mesh Suggest's layer and its cells across, which are Terrain's cell size,
  repeated out to the floor's edge. **The kind is not saved**: it is read from the two ticks a model has always held
  (the quadtree's, the corridors'), kept hidden, so a model of the older dock opens on its own kind and writes the job
  it wrote. Choosing the aligned kind makes the cells from centres; local time stepping goes on and off with the
  quadtree.
- **Streams, banks and high ground** for every kind: the stream threshold (`mesh.stream_area_mid_km2`, which Suggest
  reads; written without the quadtree only off the engine's 1 km2), the floor rule (rise over the bed, a scarp within
  10 m `bank_scarp_m`, the slope cap `bank_slope` and its tick, written only off the engine's values) and Suggest
  breaklines. High ground drawn by hand stays in Structures, and the words say so.
- **Build mesh** (was "Preview tile sizes", quadtree only): on every kind it builds the cells a run would step and draws
  them under the model's Inputs > Mesh, the aligned cells over the cell grid by tile (and the quadtree's cell sizes),
  with the count, the smallest cell, the catchments left out and the mesher's notes in words; a refusal comes back in
  the engine's words in the section. It uses the run's own cache folder, so the DEM's store and the domain mask are
  read once for both.
- **Advanced** (a fold, closed): Suggest's bank and crest thresholds, the aligned cells' maker (rings or centres), the
  gorge rows (`strips.gorge_rows`, centres only, even, written when above 0), the rings' corridor sizes (rings only),
  local time stepping (shown with the quadtree, or wherever it is on).
- **Engine hook** (`wadi2d/mesh/preview.py`, commit `6f5e1e3`): `wadi2d mesh` drew the quadtree only; it now builds the
  cells of any job the way `prepare_grid` does (the same domain mask, catchments left out, strip builder) and writes
  `cell_grid.gpkg`, `strip_mesh.gpkg` and `mesh.json`; no table is built. `tests/engine/test_mesh_preview.py` 4: on the
  synthetic valley the aligned cells of the preview are the run's own, cell for cell in count and in area.
- Tests: `tests/plugin/test_mesh_kinds.py` 4 (the kind from the ticks, the new settings taken by the engine's schema and
  read back from a job, a job without them the job of before, the words). Through the dock `dock_mesh.py` 37 of 37,
  **on Bidah at 30 m a run's own cells equal Build mesh's: 23,431 squares, 8,160 aligned cells (2,809 quads and 5,351
  polygons in the run's words), 8,540 squares replaced**; the quadtree 15,856 cells against 31,971 squares.

## Item 5: the domain from an outline (built)

- **Domain from an outline**, a box in Terrain under Domain (hidden for a Lumped model): a rough outline (polygon
  layer), edges kept as drawn (a line layer, beside the Boundaries lines, which are always kept), catchments to align
  to (a polygon layer: the HMS subbasins or a generated basin's), and two buttons, **Complete upstream** and **Align to
  catchments**, each running `wadi2d domain` (W97; no engine change). The layers are written as GeoJSON in the DEM's
  CRS beside a job of the terrain, its objects and the boundary lines (`job_builder.domain_job`; the generated basin's
  stream threshold and walls when the model has one), in a folder beside the run folder, a new one each time
  (`domain_rows.py`). The result is loaded under Inputs > Terrain with what changed (added green, removed red), from
  the GeoPackage, which names its CRS (the GeoJSON beside it names none and read as degrees), chosen as Terrain's
  domain, and **the report's areas said in words** under the buttons; a refusal in the engine's words. The three
  layers are saved with the model.
- Tests: `tests/plugin/test_domain_rows.py` 4 (the folder, the command, the refusals, both reports in words, the job's
  boundary lines kept where they lie, a flow line with no hydrograph yet no obstacle). Through the dock
  `dock_domain.py` 23 of 23.
- Seen on Bidah: a rough outline 30 m inside Bidah's validation domain (27.82 km2) completes upstream to **36.72 km2**,
  9.08 km2 of ground draining in that the domain of W1 leaves out (the "five entering streams" W78 did not judge); the
  outline must come within 50 m of the boundary lines for them to stay kept edges, and with none near it the engine
  refuses ("no ground drains to the kept edges through the outline"), as it did when the first try drew it 60 m in.

## Item 6: the results page (built)

- **A third page of the dock** (`results_page.py`, `results_links.py`, rules in `results_rows.py`): the Run section's
  **Results ›** button (on after a run, or when a finished run is opened) and the start page's **Open run** lead to it;
  **‹ Model** goes back. The page is never saved: a model opens on its sections.
- **Maps and tools**: Make map, both time sliders, the window at the terrain's finest resolution, Result lines and the
  dam workbook are the Run section's own buttons laid out here, so every check that clicks them finds them; the map
  title, background and threshold stay in Run, with the model's settings.
- **Elements of record**, read by the engine (`wadi2d lines`, as the Result lines panel reads them): every upfront line
  and point and every lumped element, filed under design points and lines (a drainage area in the run's job, or a line
  pouring into the network), dams and reservoirs, junctions, reaches, subbasins, outlets, result lines and points,
  observed gauges (the elements a record was compared with), other elements; a kind filter, a search by name, and for
  each the peak (a dam's or reach's inflow), its time, the volume, the peak outflow beside a routed peak, a point's
  deepest water. **His default when nothing is pinned**: design points and lines, else dams, else outlets. **Pins**
  (the first column) come first whatever the filter and are saved in the project (`wadi2d` entry `pinned/<model>`, one
  list per model, its runs sharing their names). **A row opens the hydrograph chart** of W64 on that element and run.
- **Compare runs**: the runs beside the opened one (a model's numbered siblings) and any added by folder, ticked; one
  engine read per run; a table of peak, time to peak, volume and peak outflow per run side by side for the elements
  shown above (the filter and pins decide which); a row's flows of record of every run on one chart; **Export the table
  to Excel** with openpyxl, which QGIS 3.36 and 3.44 both ship (a CSV with words where it is missing). The dam
  workbook's code (W60) was not reused: it lays dams out by return period, not runs side by side.
- Tests: `tests/plugin/test_results_rows.py` 3 (each kind and its numbers, a dam's inflow and outflow, the default and
  the filter with pins, the comparison and its workbook). Through the dock `dock_results.py` 29 of 29.

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

6. **One depth threshold for the maps** (his addition): "Depth threshold for the maps" in Run with the other map
   controls, 0.1 m by default. It writes `outputs.pixels.depth_floor`, `hazard_depth_floor` and the new
   `cell_depth_floor` all to that value (the pixel depth, speed, level and hazard; the time slider and the on-demand
   renderer read `depth_floor` already) and sets the display cutoff of the depth layers in QGIS ("Draw depth from",
   0.05 m and separate before) to the same value: one place, screen and files alike, and it is now saved with the
   model. **Engine hook**: the cell maps (`maps/`) kept every cell ever wet; `outputs.pixels.cell_depth_floor`
   (None by default, so an old job writes the maps it wrote; outside the job hash, as all of `outputs.pixels`) leaves a
   cell whose largest depth stayed under it out of the depth, level, speed, hazard and mean-depth maps
   (`products/cell_maps.floored`, `run._write_outputs`); the arrival map keeps its own depth. A model from before
   (format 3, now 4) shows "The engine's own floors" and writes none: its job is the job it was. A job read back gives
   the threshold where its three floors agree.

At the defaults the map pixel and the raster write nothing; **the threshold writes its three floors in every new
model**, so a fresh dock's job now carries `outputs.pixels.depth_floor`, `hazard_depth_floor` and `cell_depth_floor`
of 0.1 (a named change: the hazard floor was 0.1 already, the pixel floor 0.05, the cell maps none). Seen on the way:
the headless smoke test's 20 mm sheet peaks at 6.5 cm, so at 0.1 m its maps hold nothing; that test now sets 0.05. The results page
(item 6) is not built, so the window button lives in Run beside the other map tools, which item 6 would move.
Tests: `tests/plugin/test_map_controls.py` 4 (the job at the defaults, both settings written and taken by the
engine's schema with the continuous surface, none without pixel maps, the window's command and folder).

## Tests through the real dock

| Scenario | What it proves | Passed |
|---|---|---|
| `dock_rain.py` | item 1: the sections in their places; Data tables (add, the next free name, a refused table Missing in words, rename, remove, both charts); six sources, the Steady rain's mm/h giving its job; SCS sets 24 h and refuses 6 h; a pattern by name carried into the job and filled in by the engine; a depth grid; the parts by model type; one area for both parts = the old form, parts that differ = `area_reduction`; the study's single-run area; **a real run on Bidah of a depth with a pattern of Data tables and the 2D part's own reduction, the engine's factor equal to the dock's**; saved and brought back to the same job; a format 2 model's steady rain and design storm moved, in words | 54 of 54 |
| `dock_losses.py` | item 2: four Manning forms, each showing its own fields; one value the job of before; a raster makes it a grid and one value drops it; split refused without aligned cells; land-use classes Missing until its table is filled, then the job's roughness; Lumped shows no Manning; the CN override's forms and columns, overlapping ranges Missing, the job's override; saved and brought back to the same job; **a real Bidah run whose `config.resolved.json` holds the land-use Manning and the CN by range** | 24 of 24 |
| `dock_inflows.py` | item 3: the hydrograph box shows the flow line chosen and hides for a normal-depth line; a file route first Missing in words; the typed table on the row, its chart a quarter-hour apart, the card Ready; the job's `flow.step_s`, `flows` and slope, taken by the engine's schema; one flow refused in words; initial points with their level and name, none without a level field; saved and brought back to the same job; **a real Bidah run that read the table** | 17 of 17 |
| `dock_mesh.py` | item 4: the kind the first input; three kinds, squares first, each with its box; the aligned kind makes centres and shows the gorge rows, rings the corridor sizes; local time stepping on and off with the quadtree; an older model's tick read as the quadtree; **Build mesh on squares (31,971 cells, the grid's tiles holding them), the quadtree (15,856, cell sizes and grid, the last build replaced) and the aligned mesh (8,160 aligned cells, one polygon a cell, over the grid)**; the engine's refusal of a line off the domain in its words; the stream threshold, scarp and gorge rows in the job and taken by the engine's schema, none written at the engine's values; saved and brought back; **a run stepping the same 23,431 squares, 8,160 aligned cells and 8,540 replaced**; one dark picture | 37 of 37 |
| `dock_domain.py` | item 5: the box under Terrain's domain, hidden for Lumped; no outline and no catchments refused in words; **Complete upstream on Bidah: 27.82 to 36.72 km2, the two boundary lines kept, the report in words, the domain and its changes under Inputs > Terrain, chosen as the domain, the job's domain the completed one by area**; a run on it; **Align to catchments: 28.59 km2 against the catchment's 28.77, a gap of 0.77 km2 added**, the completed layers replaced, a new folder with the first kept; the layers saved with the model | 23 of 23 |
| `dock_results.py` | item 6: the six map tools on the results page and none left in Run, Results off before a run; two Bidah runs (10 and 20 mm/h); the page of the second: Bidah 03, the one line with a drainage area, alone under design points and lines by his default, its peak 10.4 m3/s at 1 h in the table; every element (16), the search; a pin first under the filter and **in the saved project file**; a row opens the Result lines chart on Bidah 03 of that run; the runs beside offered; **compared: four numbers a run, the pinned and the design line, 10.36 against 1.55 m3/s, both hydrographs on one chart, the table in an Excel workbook**; the page as wide as the dock; ‹ Model back; Open run on the start page leads to the run's results; the page never saved | 29 of 29 |
| `dock_import_block2.py` | his item: the four W79 jobs imported; for each the 48 h, the ARF at 100 km2 with its factor shown, the outflow lines with their slopes, the crest lines and spillways, the result lines, the aligned centre mesh; saved as scenarios in W102; **the job the dock writes, compared field by field with the original through the engine's schema: identical but for what is listed, and the dock's own comparison lists the same** | 46 of 46 |
| `dock_fixes.py` | his two faults: in a project whose first raster is a run's depth map, the dock starts on the DEM the run was made on; with it gone, nothing, and Terrain Missing; a raster no run names is not taken; the DEM's own file under a results group taken for want of another; a project read with no saved model chooses again; the Storm stack as tall as the page shown (101 px for a fixed depth, 447 for the gauges) | 14 of 14 |
| `dock_maps.py` | item 7: Map pixel Automatic first, the depth x speed raster off, no surface choice shown, no pixel settings in the job at the defaults; the window button's name and its tooltip with this DEM's pixel; Lumped hides cell size, Manning and pit fill, 2D and no type show them; **a real Bidah run with a 10 m pixel and the raster: the maps of record at 10 m, `pixel_dv.tif` written; a window of 800 m mapped at the DEM's 5 m pixel, depth, speed and hazard loaded into the run's group, the run's maps untouched**; the one depth threshold: 0.1 m, beside the map controls, no second field, the display cutoff the same, one change moving both, a format 3 model keeping the engine's floors, and **after the run no pixel of the depth map and no cell of the cell maps under 0.1 m** | 31 of 31 |

## A job the dock did not write (his item of 2026-11-16; built)

His test: `job_reader.refill` on W79's run 1 came out with 1 h (the job says 48 h), no area reduction (the job reads
its table at 100 km2), no structures, boundaries or result lines (the job holds them inline), the corridors instead
of the aligned centre mesh, and Open a run refused the folder for want of a `job.json`. Now:

- **Open a run reads `job.json`, else the engine's `config.resolved.json`**; **Import a job...** in the Model box reads
  any job file, with the output folder the model's (`job_import.find_job`, `model_store.import_job`).
- **The lines and polygons a job holds inline** (boundaries, crest lines, walls, spillways, burn lines, result lines
  and points, initial water) go into `<job>_imported_inputs.gpkg` beside the model (the output folder; a run folder
  for Open a run) and are loaded as the sections' layers, with the fields they read (`job_import.inline_layers`,
  `job_layers.write_gpkg`). A vector file the job names is read in the DEM's CRS, as the engine reads it (W79's domain
  GeoJSON names none and landed in degrees).
- **Every field the dock has a control for is mapped**; new on the way: the mesh's **Cells made by** (rings, or the
  aligned centre mesh `strips.generator: centres`), the curve's table type carried through Data tables, the map pixel's
  0 (the DEM's own pixel, where -1 is Automatic), a resolved job's `null` keys read as unset. The HMS route's met and
  control files, which such a job does not name, are chosen (the only control file; the met file whose storm depth
  is the job's) and said in words.
- **A depth with a percent pattern to 100 % and one reduction for every part is written as the design storm**
  (`hypothetical`, `time_percent`, `depth_percent`, `storm.arf`), so such a job round-trips to itself: item 1's
  migrated design storms now write the job they wrote, and the words of the migration say so.
- **The comparison**: the job the refilled dock writes, as Run writes it (the HMS import included), against the
  original, defaults taken out of both by the engine's schema the dock holds, the terrain objects in the engine's
  order of application, lists what differs by section in the Model box ("Hydrology: the dock cannot hold yet ...").
- Fixed on the way: `widget_state` took two layers of one GeoPackage for one layer (the boundaries were found as the
  crest lines).

The four Block 2 jobs, imported, saved as scenarios and proved: `W102 Block 2 models in the dock` (README there, a copy
here as `W102_README.md`). `dock_import_block2.py` 46 of 46; `tests/plugin/test_job_import.py` 7.

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

**Again at item 2 (`e116cc0`, after the import, the threshold and the Manning forms)**, each from a frozen copy: the
same ten counts as the base, scenario for scenario (`old_scenarios/branch_e116cc0/`). The jobs now differ from the
base's by one named change only: every one of the 22 run jobs carries the threshold's three floors at 0.1 m
(`outputs.pixels.depth_floor`, `hazard_depth_floor`, `cell_depth_floor`), and with those taken out all 22 are
identical to the character (`old_scenarios/floors_only.py`); the 5 preview jobs differ the same way.

**And at the end (`b304c6e`, items 3 to 6 in)**: the same ten counts again, scenario for scenario, and the same jobs: 22
identical once the three floors are taken out (`old_scenarios/branch_b304c6e/`). W23's preview checks now run through
Build mesh and pass as before (the engine's numbers equal the table's, a raster of tile sizes); the map tools these
scenarios click now sit on the results page and are found there. The headless smoke test passes on QGIS 3.36.2 (2 of
2, the fake engine and the real one), the dock with every new section built there; all plugin tests that need no
QGIS window pass (695).

## Found on the way

1. The generated basin's reaches take their Manning n from Terrain's Manning (`wadi2d/basin/elements.py`
   `_manning`, read at Generate basin): a Lumped model that hides Manning in Terrain (his item 7, point 5) leaves the
   generated reaches on a value nobody sees. A reach-n field in the basin box would close it; not built.
2. `PairTable.set_rows` wrote six significant digits (`:g`), so a table of seven digits came back rounded from a saved
   model; now ten.
3. Older dock scenarios that drive the old Storm widgets (`W20`, `W37`, `W39`, `W53`, `W54`, `W77 dock_storm`) no longer
   find them: the sources changed by design. Not rewritten.
4. **The engine's run listing (`wadi2d lines`) does not carry a line's or point's drainage area**, so the results page
   names design points and lines from the run's own job; a listing that carried it would make the job's read
   unnecessary (not changed: no engine change was needed).
5. `wadi2d domain` writes `domain.geojson` with no CRS; QGIS reads such a file as degrees, so the dock loads the domain
   from `domain.gpkg`, which names it. A CRS in the GeoJSON (or the dock reading only the GeoPackage, as now) closes it.
6. The centre mesh on Bidah at 30 m gives one note per stream (13), two of them "no centres" for streams wholly inside a
   higher line's clearance; Build mesh says four and counts the rest.
7. On Bidah, Complete upstream adds 9.08 km2 that drains into W1's validation domain from outside it; the dock's runs
   on Bidah warn of the same entering streams (W78), which W78 left as the window's design.

## Not done

- **Mesh (item 4)**: no time-step estimate beside Build mesh's count (W94 asked for one); Build mesh shares the run's
  cache folder (the DEM's store, the domain mask) but not the aligned mesh itself, which the run builds again with its
  tables; no "slope over which hills coarsen" and no aligned streams inside quadtree hills (W82, not merged); the
  incision depth that makes a defined wadi for Suggest stays the engine's.
- **Domain (item 5)**: the keep distance (50 m) and the alignment tolerance (100 m) are the engine's, not in the dock;
  aligning to the model's own subbasins needs their layer chosen (the engine's `--align job` is not offered).
- **Results (item 6)**: the comparison offers the runs beside the opened one and any added by hand, not every run of
  the project; a depth-area study's folder is not a run of this page (its lines stay in the Study section); the Excel
  export is a plain sheet: the dam workbook (W60) lays out dams by return period and does not fit a run-by-run table;
  a lumped-only run (W88) goes through the same listing and was not opened on the page in a check.
- Older dock scenarios that drive the old Storm widgets (Found 3) are not rewritten; the new sections ran through the
  real dock on QGIS 3.44.8 only (on 3.36.2 the headless smoke test builds them and runs a job).
