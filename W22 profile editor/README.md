# W22 profile editor

**Status (2026-11-02): in progress, D7 of his work order.** Base: `main` at `4ec2ac2`.

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

**A side effect of step 4, stated:** `staircase` snaps every vertex to its nearest cell corner, so a profile point between two vertices of a crest line or spillway forces the staircase through that corner. The faces can move by up to half a cell there, and only on a line with a saved profile. Points on the existing vertices move nothing.

**FILES:**

- New: `plugin/wadi2d_qgis/profile_table.py` (the file, the seed, the store), `profile_model.py` (points and undo), `profile_canvas.py` (the drawing and the mouse), `profile_editor.py` (the dialog).
- Edited: `plugin/wadi2d_qgis/sections/shaped_rows.py`, `sections/structures.py`, `dock.py` (open the editor, pass its Preview), `plugin/wadi2d_qgis/README.md`.
- New tests: `tests/plugin/test_profile_table.py`, `test_profile_model.py`, `test_profile_route.py`, `test_editor_qgis.py`, `editor_qgis.py`.
- New here: `dock_profile_editor.py` and its log.
