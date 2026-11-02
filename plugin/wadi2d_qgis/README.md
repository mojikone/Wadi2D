# Wadi2D QGIS plugin

One dock, one workflow from top to bottom: terrain, hydrology, structures, boundaries, results points, run. GPL-3.0-or-later.

The plugin never imports the engine. It writes `job.json`, starts a process, tails `progress.jsonl` and loads rasters
(design note section 5), so either side can change alone. Defaults, bounds and tooltips come from `wadi2d schema`.

## Install

```
python tools/install_plugin.py          copy into the default QGIS profile; repeat freely
python tools/install_plugin.py --link   a directory junction, so edits in the repo are live
```

Then enable Wadi2D in Plugins > Manage and Install Plugins. The installer records the Python that ran it as the engine. If the engine is not found, press **Engine...** in the dock:
one field, the Python or `wadi2d` executable, checked with `wadi2d doctor`. The default is the project venv.

## Use

1. **Terrain.** A DEM layer backed by a file, in a projected CRS. The cell size snaps to a multiple of the DEM pixel. The
   domain is a polygon layer, or the map extent kept inside the DEM. Manning is one value or a raster.
2. **Hydrology.** Rain in mm/h and hours, or an HMS project folder: choose the basin, met and control files and set each
   subbasin to lumped or 2d. The storm and the simulated time then come from the project through `wadi2d hms-import`.
3. **Structures.** Line layers. Crest lines and spillways need an elevation: a field, or Z on the vertices.
4. **Boundaries.** A line layer with one kind and value. If it has fields named `kind` and `value`, each line uses its own.
5. **Results points.** Points record depth and level; lines across the flow record discharge.
6. **Run.** Estimate gives cells, memory, time and the disk of the saved maps. **Save maps** is every 15 minutes for design
   work, or every 5 for an animation, three times the disk; peak depth and hazard hardly move between the two, because the
   run keeps its own peaks. A folder that already holds a run is never overwritten: the new run goes to `<folder>_2`, and
   all runs share `wadi2d_cache` beside them, so tables are built once.

During a run the depth appears as a blue layer. When the simulation ends the bar restarts for the pixel maps, unless the
box is unticked: depth at the DEM pixel, hazard H1 to H6, smooth class polygons, a depth drawing with a soft wet edge. At
the end the layers load into a group named after the run: **Model setup**, **Flood maps**, **Pixel rasters, the numbers of
record**, **Cell maps**. If the run fails, the message says why and a red cross marks the cell.

**Make map** writes three A3 sheets to `pixels/<run>_maps.pdf`, setup, depth and hazard, over a hillshade of the DEM or
satellite imagery, and keeps the layout in the project to edit. It works on the last run, or on any finished run whose
folder is chosen above. The satellite background needs the internet, and its imagery has its own licence.

**Stop** creates `DIR/stop`; the engine finishes the step, writes its maps and exits, and is killed after 30 s if it does
not. Stop during the pixel maps leaves the run finished, with no half-written pixel file; `wadi2d products <folder>` makes
them later. Close QGIS and the engine keeps running: on the next start the dock opens and follows it from its progress
file.

## In a run folder, written by the plugin

`job.json`, `inputs/*.geojson` (every vector layer, in the DEM CRS, as sent), `plugin_run.json` (pid, CRS, end time, for a
later session), `engine.out`, `engine.err`. The schema carries structures, boundaries and design points inline in
`job.json`; the GeoJSON files are the record of them, and only the domain is read from its file.

## Modules

| File | Job | Needs QGIS |
|---|---|---|
| `protocol.py` | commands, file names, exit codes, the clean environment | no |
| `progress.py` | progress tail, run state, where the live raster is | no |
| `job_builder.py` | values to a job dict; layers to features at the end of the file | adapters only |
| `engine_process.py` | `QProcess` wrappers: short commands and runs, start, attach, stop | yes |
| `live_layer.py`, `result_layers.py`, `style.py` | layers on the map, grouped and styled | yes |
| `map_notes.py` | the words on a sheet, from the run folder | no |
| `map_sheets.py` | the A3 layout and its PDF; also runs on QGIS's Python alone | `qgis.core` only |
| `dock.py`, `sections/*.py`, `settings.py`, `plugin.py` | the interface | yes |

`clean_env` in `protocol.py` matters more than it looks: QGIS sets `PYTHONHOME`, `GDAL_DATA` and `PROJ_DATA` for its own
interpreter, and a child that inherits them loads QGIS's standard library instead of its own.

The depth and hazard colours are display choices and live in `style.py`; the hazard limits of the pixel maps are the
engine's, in the schema, and the legend reads them from `pixels/pixels.json`. The only other number near a
default is `PREFERRED_DX` (20 m), the dock's first cell size, which he asked for; the engine's own default is finer.

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
