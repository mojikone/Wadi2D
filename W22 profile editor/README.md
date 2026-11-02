# W22 profile editor

**Status (2026-11-02): done on QGIS 3.44.8, D7 of his work order.** A graphical editor per structure, as in HEC-RAS: drag points, type a table, undo, for bed, tops and elevations, with the engine's own preview under the plot. It writes what the engine already reads, and no file under `wadi2d/` changed. Base: `main` at `4ec2ac2`.

## [PRESERVE-CHECK]

The owner said not to stop, so this block stands in for the go-ahead. It is `[BROAD]` only in that it touches more than one file; nothing is removed or replaced.

**KEEP**, not touched and behaving as before:

- The engine: no file under `wadi2d/` changes. Job format, schema, `read_table`, `with_tables`, `build_profile` and the checks stay as they are.
- `job_builder.py` and `shaped.py`: no edit. `_shaped`, `shaped_object`, `_object`, `build_job` and `preview_job` keep their code.
- The field route: every field and number row in Structures, with a field winning over its number.
- The table route: the **Section table** picker and the **Section table field, per line**.
- Z on the vertices of the layer, `bed_start_z` with `bed_slope`, and freeboard with water depth.
- **Preview terrain**, **Sections and long profile...**, `ProfileDialog` and `ProfileCanvas`, used as they are.
- A layer with no saved profile gives the same `job.json` as before: same objects, same `inputs/` files, same properties. A test holds this.
- The user's layer and table files are never written to. Old jobs run as they ran.

**CHANGE**, all of it additions:

- Structures gets an **Edit profile...** button and a count of saved profiles, for every kind but walls, which have no level.
- `ShapedRows.features` and `StructuresSection.values` read features by id, so a line can find its saved profile. The id is taken back out before the feature leaves them, so what the job builder receives is unchanged.
- **An edit outranks the field and the table** for that one line, as in the boundary table (W18). **Drop saved profile** sets the line back.
- The dock opens the editor and passes its Preview through the existing `preview_terrain`.

**How a saved profile reaches the job, exactly:**

1. Save writes one CSV per line, in the columns the engine's `read_table` already reads: `station`, then `bed_z`, `crest_z`, `left_top_z`, `right_top_z`, then any other column the source table had, unchanged.
2. The file is `<layer folder>/<layer name>_profiles/<kind>_line_<feature id>.csv`, or wherever the editor's folder box points. The file is the record: a reopened project finds it by itself.
3. **Embankment, channel, channel with dykes:** `ShapedRows.features` puts that path in the feature's `table` property, the same property the Section table route fills. From there nothing is new: `_shaped` copies it to `inputs/<kind>_<n>_<file>.csv`, `shaped_object` names it in `section.table`, the engine reads it through `with_tables`, and its rows land in `config.resolved.json`.
4. **Crest line, spillway, burn line:** the engine takes no table for these, only `z` per vertex. `StructuresSection.values` reads the same CSV and gives the feature Z on its vertices, adding a vertex on the line at each profile station between two vertices, and takes `crest_z` out of its properties. `_object` then writes `coordinates` and `z` as it does for any layer with Z. The numbers reach the run folder in `job.json` and `inputs/<kind>.geojson`.

**A side effect of step 4, stated:** `staircase` snaps every vertex to its nearest cell corner, so a profile point between two vertices of a crest line or spillway forces the staircase through that corner. The faces can move by up to half a cell there, and only on a line with a saved profile. Points on the existing vertices move nothing. Measured on a diagonal line on 20 m cells, one vertex forced at 37 positions: the staircase strays up to 25.8 m from the true line against 21.4 m with none, which is 0.22 of a cell, and its total length does not change. `test_profile_route` holds the half-cell limit.

**FILES:**

- New: `plugin/wadi2d_qgis/profile_table.py` (the file, the seed, the store), `profile_model.py` (points and undo), `profile_canvas.py` (the drawing and the mouse), `profile_editor.py` (the dialog).
- Edited: `plugin/wadi2d_qgis/sections/shaped_rows.py`, `sections/structures.py`, `dock.py` (open the editor, pass its Preview), `plugin/wadi2d_qgis/README.md`. `boundary_rows.py` is only imported, for its line labels.
- New tests: `tests/plugin/test_profile_table.py`, `test_profile_model.py`, `test_profile_route.py`, `test_editor_qgis.py`, `editor_qgis.py`.
- New here: `dock_profile_editor.py`, `read_ground.py`, the log and the pictures.

## What it does

Every kind but a wall has an **Edit profile...** button in Structures. It opens one window per kind, a line at a time, and stays open beside the map.

- The ground is sampled from the DEM along the line, a pixel apart, up to 4,000 points. A notch on the top edge marks each vertex of the line.
- The points start from what the line has now, in the engine's own order: table, Z or constant, design rule. A line with no level starts on the ground and says so.
- **Drag** a point; Shift holds its station; a drag lands on 0.1 m and 0.01 m. **Double-click** adds a point to the nearest series. **Right-click** or Delete takes one away. The ends of the line keep their stations.
- **Type** the table, or **paste** from a spreadsheet, with or without a heading. A station typed in the last row adds a row at the levels already there, so nothing moves.
- **Undo** and redo, by button or Ctrl+Z and Ctrl+Y. One drag is one step, however many moves it made.
- **Both tops together** starts ticked when the two tops are the same, and moves the points they share.
- The wheel zooms along the line, Ctrl and the wheel zoom the levels, the middle button pans. A typed level outside the frame brings the frame with it, unless the view was zoomed on purpose.
- **Preview terrain** runs the same `wadi2d terrain` on the unsaved points. The result fills the lower half on `ProfileCanvas`, the same drawing code as the dock's sections dialog, the map shows the same two rasters, and the engine's checks come back in words. Taking a point turns the section to it. Editing after a preview says the preview is out of date; undoing the edit says it is good again.
- What the engine would refuse is met here: a top under the bed stops Save and Preview, in words, with its station. An adverse bed or a dyke with nothing to tie into is the engine's own sentence, after Preview.
- **Save** writes the file; **Drop saved profile** puts the line back and renames the file `.dropped`. Changing line or closing with unsaved edits asks. The editor closes when its layer goes.

## Results

`dock_profile_editor.py` through the real dock in QGIS 3.44.8, throwaway profile, Block 2 ground (`GGC_2_MERGE_HDSM_5.tif`), a 3.4 x 2 km box at 10 m: **120 of 120** (`log_dock_profile_editor.txt`). The plugin under test reports its file in this worktree. The check's `engine.py` puts this worktree first on the path, and `read_ground.py`, started the same way on the run's own job, reports `wadi2d.__file__` here.

**An edited profile changes the ground the engine used.** The same line, the same run, on its fields and then with one bed point at station 1,498.2 typed down to 118.5 m:

| At station 1,498.2 | On the fields | Edited | Asked |
|---|---|---|---|
| `terrain_modified.tif`, the pixel on the line | 120.65 | 118.50 | 118.5 |
| The solver's grid, `zmin` of the cell, read through the cache the run used | 120.65 | 118.50 | 118.5 |

Cut on that line went from 565,560 to 623,989 m3, the resolved job holds the edited row, the table in `inputs/` is the saved file to the byte, and mass closes at -1.8e-9. After **Drop**, the job's object equals the job of the fields to the last key, and the run takes the fields' cached grid again.

Also through the dock:

- The engine's bed in the preview is the bed in the plot, worst 0.5 mm over the line.
- The editor's ground against the engine's: median 4 cm, worst 1.27 m. Both read the raw DEM by nearest pixel; the editor's points stand a pixel apart and the check reads between them, so a steep face shows the gap. [Likely] that is all of it; the worst point was not isolated. This ground is drawn, not used.
- The Section table route and the field route run beside a saved profile. A section table opens in the editor, Save leaves the user's file untouched, and its `width` column stays with its stations.
- Embankment crest, crest line, spillway and burn line each edited, saved and run. The crest line's job has `z` per vertex with one vertex added on the line and its length unchanged. The spillway keeps its C and length. The ground took the burn at the edited invert, to 1 cm.
- A drawn layer with no file and no level: refused by the run as before, then given a bed by the editor alone, and run. A multi-part feature: each part a line, each its own file.

Tests: 104 in `tests/plugin`: `test_profile_table` 54, `test_profile_model` 35, `test_profile_route` 14, `test_editor_qgis` 1, the last a long script of its own. The one to read is `test_opening_and_saving_a_line_gives_the_engine_the_same_profile`: 14 ways of giving a level, each opened and saved, against the engine's own `build_profile`. `editor_qgis.py` drives the editor offscreen on QGIS's Python with real mouse, wheel and key events, the right-click menus and the folder box included.

**Looked at, not only checked:** the dock section, the editor opened, after a drag, previewed on a channel with dykes and on an embankment, a crest line, a line starting on the ground, a table route, and the preview's change raster and the run's change raster on the map. `editor_*.png` here are from the real dock.

## What the pictures found that the checks did not

- **The Edit button squeezed to "dit profile.." with its count cut to "1 saved: it".** The check read the label's text and passed. The count is now short, the explanation is a tooltip, and two checks hold the widths.
- The empty preview pane took half the window before any preview. It now appears with the first one.
- The end points were half cut by the frame, and they are the points most often taken.
- A typed level above the view sat on the frame edge, half hidden.
- The readout kept the value of a point after that step was undone.

## What the dock and the tests found

- **A spurious vertex.** Stations are rounded to the millimetre and a line's length is not, so a crest line's last point fell 0.3 mm inside its end and became a new vertex. Harmless to the numbers, wrong in the job. Found only by the run.
- **Save on the wrong line,** found on rereading the dialog, before any run. Choosing another line with unsaved edits and pressing Save in the question would have written the edits to the line just chosen, because the box had already changed. The editor now follows the line in the plot, and a test holds it.
- **A frozen list of lines.** The window stays open, so a table chosen in the dock meanwhile went unseen. It now reads the lines each time one loads.
- **A point 0.01 m from the end of the line counted as pinned** and could not be dragged back.

## Found, not fixed: teeth in a section on the end of a line

A preview section at exactly station 0 draws as a saw. Sample points on the end line fall 7e-11 m past it by round-off, about half of them count as beyond the line, and those take no cut. One metre along the same section is clean, and the plain sections dialog shows the same teeth. [Likely] it touches only the drawn section, because pixel centres do not fall exactly on an end. I read the numbers for one object and did not check the pixels. The engine was out of scope, so it stands: the editor's pane opens on a middle section instead.

## Limits

- **A crest line or spillway alone has no Preview.** They close faces and change no pixel, so `preview_problems` says so in its words, and the long profile above is all there is to judge them by. With a ground object in the job, Preview runs and shows that object.
- **A feature id names the file.** On a shapefile, deleting a line and packing renumbers the lines after it, and a profile then sits on the wrong line. The engine's note about a table's length catches it only if the lengths differ by over a metre. A GeoPackage keeps its ids.
- **A layer's edits follow its stations.** Moving a vertex keeps the levels at their stations, not at their places on the ground.
- A profile of a layer with no file goes to the temporary folder and dies with that layer.
- The default folder sits beside the layer, so on a shared or read-only folder Save says it could not write, and the folder box takes another. A layer's chosen folder is kept in the QGIS project; unsaved, it must be chosen again.
- The editor edits bed, tops and elevations. Width and slopes stay fields or table columns, and a table's other columns stay as they are but are not shown.

## Not tested

- QGIS other than 3.44.8; the laptop has 3.40.14.
- A human hand: every drag was real Qt events sent to the widget, not an OS mouse.
- Screens under 900 px high. The window shrinks to fit; with a preview open its minimum may not.
- A long line near the 4,000-sample cap, and how the plot feels on it.
- A shapefile or a GeoPackage layer: the check used GeoJSON and memory layers.
- The CPU backend through the dock.
- `ruff` is clean on everything here. `ruff check tests` still gives one import-order finding, in `tests/plugin/test_contract.py`, already there on `main` at `4ec2ac2` and left alone as out of scope.

## Rerun

```
powershell -File tests\dock\run_check.ps1 "W22 profile editor\dock_profile_editor.py" <throwaway folder> -Copy "W22 profile editor"
```

`read_ground.py` is started by the check, on the engine's Python: it reads the solver's grid at a point through a run's own job and cache.
