# Wadi2D QGIS plugin

One dock, one workflow from top to bottom: terrain, mesh, hydrology, structures, boundaries, results points, run. GPL-3.0-or-later.

The plugin never imports the engine. It writes `job.json`, starts a process, tails `progress.jsonl` and loads rasters
(design note section 5), so either side can change alone. Defaults, bounds and tooltips come from `wadi2d schema`.

## Install

From a release: unzip `Wadi2D-<version>-windows.zip` and double-click `install_wadi2d.bat`. It sets up the engine and copies
the plugin into the default QGIS profile. `wadi2d_qgis-<version>.zip` alone also works through Plugins > Install from ZIP,
for another profile; it finds the engine the installer recorded.

From the repository:

```
python tools/install_plugin.py          copy into the default QGIS profile; repeat freely
python tools/install_plugin.py --link   a directory junction, so edits in the repo are live
```

Then enable Wadi2D in Plugins > Manage and Install Plugins. The installer records the Python that ran it as the engine. If the engine is not found, press **Engine...** in the dock:
one field, the Python or `wadi2d` executable, checked with `wadi2d doctor`. The default is the engine the installer recorded.

## Use

1. **Terrain.** A DEM layer backed by a file, in a projected CRS. The cell size snaps to a multiple of the DEM pixel. The
   domain is a polygon layer, or the map extent kept inside the DEM. Manning is one value or a raster.
2. **Mesh.** Optional, off by default: off is the uniform grid, exactly as before. Ticked, the cell size above is the finest
   cell and tiles coarsen to the coarsest cell, by powers of two. Defined wadis stay fine by drainage area; barriers,
   boundaries and design lines always do. A polygon layer with a cell-size field adds zones. A line layer adds **refinement
   lines**, a table as in HEC-RAS: near cell, rows each side, far cell, with the actual sizes beside them, because the mesh only
   doubles a cell, so a size goes down to the finest cell times a power of two. Each doubling out to the far cell holds as
   many rows, so a band reaches rows x (2 far - near); up to 32 rows the 2:1 grading sets the sizes by itself and Far changes
   nothing. Fields `near_dx`, `rows` and `far_dx` in the layer fill the table. A line only refines: it blocks no flow. A band
   does not replace the wadi areas: on Bidah 8 rows on the main wadi alone read 7.8 % low, with the wadi areas on 4.1 %.
   **Preview tile sizes** puts a layer of cell sizes on the map and says how many cells it comes to and what each line got.
   Needs the `whitebox` package (`pip install wadi2d[mesh]`).
   Local time stepping sits here too: ticking the mesh turns it on, and it can be used without a mesh. It saves no time on a uniform
   grid and helps on a large mesh. A mesh saves time above about 1 M cells, and only memory below that.
3. **Hydrology.** Rain in mm/h and hours, or an HMS project folder: choose the basin, met and control files and set each
   subbasin to lumped or 2d. The storm and the simulated time then come from the project through `wadi2d hms-import`.
4. **Structures.** Line layers. Crest lines and spillways need an elevation: a field, or Z on the vertices.
   Embankments, channels and channels with dykes rebuild the ground along the line (section below). **Preview terrain**
   shows the result on the map in seconds, without a run.
5. **Boundaries.** One line layer holds them all. The table lists each line with its kind and value, editable, and needs no fields in the layer; a value starts from the default of its kind. Kind and Value above it set every line you have not touched. If the layer has fields named `kind` and `value`, each line starts from its own; a `name` field names the row. Click a row to flash its line on the map.
6. **Results points.** Points record depth and level; lines across the flow record discharge.
7. **Run.** Estimate gives cells, memory, time and the disk of the saved maps; on a mesh it counts the mesh, and its time is rough. **Save maps** is every 15 minutes for design
   work, or every 5 for an animation, three times the disk; peak depth and hazard hardly move between the two, because the
   run keeps its own peaks. A folder that already holds a run is never overwritten: the new run goes to `<folder>_2`, and
   all runs share `wadi2d_cache` beside them, so tables are built once.

During a run the depth appears as a blue layer. When the simulation ends the bar restarts for the pixel maps, unless the
box is unticked: depth at the DEM pixel, hazard H1 to H6, smooth class polygons, a depth drawing with a soft wet edge. At
the end the layers load into a group named after the run: **Model setup**, **Flood maps**, **Pixel rasters, the numbers of
record**, **Cell maps**. Model setup also holds the **Cell grid**, the cells the solver really stepped, coarse tiles coarse, on every run even with pixel maps off; it draws once you are near enough for a cell to reach 1 mm on screen, and its name says the scale. If the run fails, the message says why and a red cross marks the cell.

**Time slider** steps through the saved frames: it writes `frames.nc`, loads it as a mesh layer with depth, speed and hazard on the real cells, and sets up the Temporal Controller, one step per saved frame. The date on the slider is a stand-in: 1 January 2000, 00:00, is the start of the run. It switches the Flood maps group off, since the run's maximum under a rising flood would read as the flood; tick it back on. These are cell values and show how the flood moves; the pixel rasters stay the numbers of record. A large run takes minutes to read, and QGIS waits meanwhile. It needs two saved maps. Speed and hazard are in the layer's own styling panel.

**Make map** writes three A3 sheets to `pixels/<run>_maps.pdf`, setup, depth and hazard, over a hillshade of the DEM or
satellite imagery, and keeps the layout in the project to edit. It works on the last run, or on any finished run whose
folder is chosen above. The satellite background needs the internet, and its imagery has its own licence.

**Stop** creates `DIR/stop`; the engine finishes the step, writes its maps and exits, and is killed after 30 s if it does
not. Stop during the pixel maps leaves the run finished, with no half-written pixel file; `wadi2d products <folder>` makes
them later. Close QGIS and the engine keeps running: on the next start the dock opens and follows it from its progress
file.

## Embankments and channels

Station 0 is the first vertex; left and right are looking along the line, so draw channels downstream.

- **Embankment.** Raised ground for a dam or dyke: crest, crest width, a slope each side. Where it stands above the
  ground it also runs as a line of crest faces, so it holds water on cells far coarser than it.
- **Channel.** A trapezoid burned into the ground, daylighting to it.
- **Channel with dykes.** The one HEC-RAS does not have. One line, and at every section each bank settles itself: where
  the ground is above the bank's top the channel is cut and daylights; where it is below, a dyke is built at the top
  level with its outer slope down to the ground. One bank can be in cut and the other in dyke, changing along the line.

Give a section three ways, and mix them:

1. **On the feature.** Each number in the dock is the value for every line of the layer; choose a field next to it and
   the field wins wherever it holds a value. Bed and top are fields, or Z on the vertices for the bed.
2. **A section table.** A CSV chosen in the dock for the layer, or named per line in a field. Columns: `station`, then any
   of `bed_z`, `width`, `crest_z` (both banks), `left_top_z`, `right_top_z`, `left_slope`, `right_slope`,
   `left_crest_width`, `right_crest_width`, `left_outer_slope`, `right_outer_slope`, `water_z`. Values read linearly
   between stations, so two sections join with no step; an empty cell reads between its neighbours; a missing column
   takes the number in the dock. A table is copied into `inputs/` with the run.
3. **A design rule.** Bed from a start level and a slope, top as freeboard above a water depth, or above a `water_z`
   column in the table.

**Openings** are text in a field, station ranges with an optional bank: `120-180 left; 600-650`. The raised part is left out
and ends in a slope either side. **Lining** is a Manning n on the pixels of the channel section, not on whole cells.
**Ends**: open stops a cut square, closed wraps the section round the end, taper fades it to the ground. A raised part
always ends in a slope. A spillway drawn on an embankment takes the fill out of its pixels and keeps its own law.

**Preview terrain** writes the job, runs `wadi2d terrain`, and loads `terrain change` (blue cut, brown fill) and `terrain
modified` into a group. It also says cut and fill per object and everything the checks found, and **Sections and long
profile** draws ground, bed and tops along the line with what each bank is at each station, and any section. Nothing
here needs rain, boundaries or an output folder.

A run writes `terrain/volumes.csv` and `terrain/volumes_by_station.csv`, gives the volumes in its final message, and with
**Write the modified terrain** also `terrain/terrain_modified.tif` and `terrain_change.tif`, whole domain. A preview's rasters
hold only the tiles the objects reach.

## In a run folder, written by the plugin

The engine writes `cell_grid.gpkg` at the start of a run, one line feature per tile with `cell_m`, `level` and `cells`.

`job.json`, `inputs/*.geojson` (every vector layer, in the DEM CRS, as sent), `plugin_run.json` (pid, CRS, end time, for a
later session), `engine.out`, `engine.err`. The schema carries structures, boundaries and design points inline in
`job.json`; the GeoJSON files are the record of them, and only the domain is read from its file.

## Modules

| File | Job | Needs QGIS |
|---|---|---|
| `protocol.py` | commands, file names, exit codes, the clean environment | no |
| `progress.py` | progress tail, run state, where the live raster is | no |
| `boundary_rows.py` | the rows of the Boundaries table: who set what | no |
| `mesh_rows.py` | the rows of the mesh lines table: what each size becomes, who set what | no |
| `job_builder.py` | values to a job dict; layers to features at the end of the file | adapters only |
| `shaped.py` | embankments and channels to job entries, their problems, the volumes sentence | no |
| `preview.py`, `profile_view.py` | Preview terrain and its sections dialog | yes |
| `engine_process.py` | `QProcess` wrappers: short commands and runs, start, attach, stop | yes |
| `live_layer.py`, `result_layers.py`, `style.py` | layers on the map, grouped and styled | yes |
| `time_layer.py` | the frames file as a mesh layer, and the Temporal Controller | yes |
| `map_notes.py` | the words on a sheet, from the run folder | no |
| `map_sheets.py` | the A3 layout and its PDF; also runs on QGIS's Python alone | `qgis.core` only |
| `dock.py`, `sections/*.py`, `settings.py`, `plugin.py` | the interface | yes |

`clean_env` in `protocol.py` matters more than it looks: QGIS sets `PYTHONHOME`, `GDAL_DATA` and `PROJ_DATA` for its own
interpreter, and a child that inherits them loads QGIS's standard library instead of its own.

The depth and hazard colours are display choices and live in `style.py`; the hazard limits of the pixel maps are the
engine's, in the schema, and the legend reads them from `pixels/pixels.json`. The only other number near a
default is `PREFERRED_DX` (20 m), the dock's first cell size; the engine's own default is finer.

## Tests

```
.venv\Scripts\python.exe -m pytest tests\plugin
```

`test_job_builder`, `test_progress`, `test_protocol`, `test_fake_engine` and `test_install_plugin` need no QGIS.
`test_contract` holds the plugin against the real schema and validates its jobs with `RunConfig`. `test_smoke_qgis` starts
`smoke_qgis.py` on QGIS's Python with `QT_QPA_PLATFORM=offscreen`: the real dock and process wrapper, once on the fake engine
in `fake_engine.py` and once on the real CLI. `test_sheets_qgis` makes a real run, then its layers and PDF on QGIS's Python,
without offscreen, whose fonts draw every letter as a box. When the schema changes, `test_contract` fails until `schema_sample.json` is
dumped again.
