# W68 layer groups and dock rows

**Live.** Branch `feature/dock-groups` off `feature/fast-products` at `c299429`; not merged, nothing pushed.

Three pieces of plugin work, 2026-11-14:

1. His new rule: the plugin makes one group per model in the QGIS layer tree, with a fixed pattern of subgroups, so inputs and
   results always sit in the same place.
2. Dock rows for what was built without them: the dam breach (`W63`) in Structures, and the dam workbook (`W60`) as a
   button and a small dialog.
3. Through the real dock: a reservoir with W59 structures read from an HMS file runs; W64's right-click chart under the pan
   tool on a real run.

## 1. The layer tree: one group per model

The pattern, in `plugin/wadi2d_qgis/layer_groups.py`. **Every name below is a constant at the top of that module: to rename
one, change it there and nothing else.**

```
Wadi2D – <model>                    the model: the Run section's output folder, by name
    Results – <run>                 one per run folder, newest on top
        Lines                       lines drawn after the run (Result lines)
        Time slider                 the frames as a mesh layer; the pixel slider layer
        Model setup                 what the run used: domain, open boundaries, inflows, design lines, reaches,
                                    subbasins, the cell grid, the corridors
        Flood maps                  the smooth hazard polygons and the depth drawing, when made
        Pixel rasters, the numbers of record
        Cell maps                   maps/*.tif, closed and switched off
    Inputs                          made whole the first time, so each kind always has its place
        Terrain                     Preview terrain: the change and the modified ground
        Boundaries                  (nothing of the plugin's yet; the place for his own layers)
        Structures                  (the same)
        Hydrology                   the basin generated from the DEM: subbasins, reaches, junctions
        Mesh                        the mesh preview; the suggested breaklines and thalwegs
```

| Constant | Name in the tree |
|---|---|
| `MODEL_PREFIX` | `Wadi2D – ` (an en dash) |
| `RESULTS_PREFIX` | `Results – ` |
| `INPUTS` | `Inputs` |
| `TERRAIN`, `BOUNDARIES`, `STRUCTURES`, `HYDROLOGY`, `MESH` | `Terrain`, `Boundaries`, `Structures`, `Hydrology`, `Mesh` |
| `LINES`, `TIME`, `SETUP`, `MAPS`, `RECORD`, `CELLS` | `Lines`, `Time slider`, `Model setup`, `Flood maps`, `Pixel rasters, the numbers of record`, `Cell maps` |
| `NO_MODEL` | `no output folder yet`, the model name before an output folder is chosen |

Rules, decided here (his to overturn):

- **The model is the Run section's output folder, by name.** A run in `bidah_2` or a study in `bidah_arf` belongs to `bidah`
  when `bidah` sits beside it (the dock numbers a rerun's folder that way). A folder `solo_7` with no `solo` beside it is its
  own model.
- **Results above Inputs**, newest run on top: QGIS draws the top of the tree over the rest, and a flood map drawn under
  the terrain preview would be hidden. His example listed Inputs first; the order is one line in `results_group`.
- **A rerun replaces only its own results group.** Loading a run again (its maps at the end, the same folder reopened)
  replaces `Results – <run>` at the place it stood; other runs' groups stay. A rerun into a new numbered folder is a new
  group above the last.
- **The user's layers are never deleted.** Every layer the plugin adds carries a custom property (`wadi2d/slot`) naming what
  made it; a later preview, basin or suggestion removes only its own slot's layers that are still inside the model's group.
  A layer the user moved out of the group stays where it is. A layer or group of the user's inside a results group being
  replaced is moved up into the model's group.
- **Groups are found by a custom property, not by name** (`wadi2d/role`, `wadi2d/key`), so the model's group is found where
  the user moved it (inside a group of his own, say) and a rename by the user does not make a second one.
- Not in the tree, as before: the map sheets' layers (they live in the layout only), and a scratch line layer drawn with no
  run open (top of the tree).

Where each layer now goes, by module: `live_layer.load_maps` and the live depth layer (results group), `result_layers`
(Model setup, Flood maps, the record, the cell grid, the corridors), `time_layer` and `slider_layer` (Time slider),
`line_tool.scratch_layer` (Lines), `preview.load_terrain` (Terrain), `basin_layers` (Hydrology), `live_layer.show_mesh` and
`suggest_lines` (Mesh).

## 2. The dock rows

**Dam breach** (Structures, under the dam start table): a table of breaches, Add and Remove. A row: the dam (a named crest
line or embankment of the layers), mode (overtopping or piping), final bottom, bottom width, side slope (both sides),
formation time (min), growth (linear or sine), the trigger (pool level, level held, run time), its value (level in m or
time in h), how long held (min), the pipe's centre (m). It writes the job's `breaches` in the engine's units. Left to the
engine's defaults, a job by hand still sets them: the breach centre (the lowest ground under the line), the weir and
orifice coefficients, the collapse ratio, the update interval, the estimators (Froehlich 2008 and the others). **Refused
before the run, in the engine's words:** the mesh, the corridors, local time stepping. Rows logic without Qt:
`breach_rows.py`; the widget: `sections/breach_table.py`.

**Dam workbook** (Run section, `Dam workbook...`): a dialog with one finished run per return period (the last run fills the
first row; `Add run...` the rest), the elements every run has a series of (lumped elements, then design lines, then result
lines) as ticks, the target period (200yr by default), a project name and the file. It starts `wadi2d workbook --run
RP=DIR ...` and says where it wrote. Periods typed `200`, `200 yr` or `200-year` go to the engine as `200yr`, `pmp` as
`PMP`. Rows logic without Qt: `workbook_rows.py`; the dialog: `workbook_dialog.py`. **The element names offered are the
series files' names** (`Bidah_03_Reservoir`, underscores for spaces), so the sheets are named that way; the engine takes
`NAME=SHEET`, the dialog does not offer it yet. HMS DSS files as the source are command-line only.

## 3. Tests

`.venv\Scripts\python -m pytest -o addopts="" tests/plugin`, CPU: **545 passed** (538 after the groups alone; new:
`test_groups_qgis.py`, `test_breach_rows.py` 3, `test_workbook_rows.py` 4, the last writing a real workbook through
`wadi2d workbook` from two runs' series). The full suite of the repository was not run. On QGIS 3.44.8's
own Python, headless: `tests/plugin/groups_qgis.py` (the pattern made whole; results on top of inputs; a rerun replaces at
its place and moves the user's layer up; a layer moved out stays; a slot clears only its own; the model group found inside
a group of the user's; a second model a second group), and the existing smoke and sheet scripts, now on the new groups.

Through the real dock (`tests/dock/run_check.ps1`, a throwaway QGIS 3.44.8 profile, CPU engine):

| Check | Result |
|---|---|
| `dock_breach.py`: Bidah's own dam (W34's three crest pieces at 105 m, spillway at 100 m), pool full to the spillway (3,832,907 m3 on the grid), a breach added in the table, 20 m cells, 1 h | **14 of 14** |
| the row lists the named dam; held and pipe greyed for a level-started overtopping; an empty row stopped in words | pass |
| the mesh ticked: refused in the engine's words; ticking the mesh also ticks local time stepping, which stays refused when the mesh is unticked, until it is unticked too | pass |
| the run: job `breaches` in the engine's units (trigger 0.05 h = 180 s, formation 10 min = 600 s), events `start` at 180 s and `formed` at 780 s, `series/breach_Bidah dam.csv` | pass |
| `dock_hms_structures.py`: Bidah 03 at 30 m, 200-yr frequency storm from `hms_copy.py`'s project, every subbasin rain-on-grid, a hand-back line 60 m above the dam into the reservoir; the HMS control's 48 h | **21 of 21** |
| the reservoir routes by its structures: series with `orifice_1_m3s`, `rating_spillway_1_m3s`, `dam_top_1_m3s`, pool and storage; peak in 703.7, out 25.4 m3/s, pool 84.70 to 96.15 m | pass |
| the tree: `Wadi2D – structures_hms` > `Results – structures_hms`, `Inputs` with its five; the user's hand-back layer left at the root | pass |
| W64 under the pan tool: a right-click on the hand-back line offers Bidah 03, Bidah 03 ring and the reservoir; the reservoir's entry opens its chart in the Result lines panel | pass |
| the workbook dialog opens on the run, offers its 18 series, writes Read me, 200-year, the six summaries and the reservoir's sheet | pass |

Found on the way:

- **[Certain] W64's chart heading on the HMS route reads "Lumped element: Bidah 03 Reservoir.", not "Reservoir: ...":** the
  listing of an HMS network carries no element kind, so the heading and the tc note that W64 draws for a generated basin
  are not there. The chart itself opens on the right-click as on a generated basin.
- The run's flood reached the reservoir at 703.7 m3/s (no curve number in this check: the rain runs off with no losses);
  the pool rose from 84.70 to 96.15 m, below the 100 m spillway table's flow, so the orifice carried all of the 25.4 m3/s
  out, as 0.6 x 3 m2 x (2 g x 10 m)^0.5 gives by hand.
- The engine refused the first attempt in words: with every subbasin on the grid, the reach below the reservoir carried
  rain-on-grid subbasins ("list it as lumped, or its rain falls twice"); the copy now sends the reservoir to a sink of its own.

## Files

- `hms_copy.py`: a copy of Block 2's HMS project (his files read-only) whose Bidah 03 reservoir routes by an orifice
  (2 x 1.5 m2 at 86 m), the project's own `Elev-Dis Bidah 03` table as a rating-curve spillway, and a level dam top
  (300 m at 104 m, C 1.7) in place of its Modified Puls curve; every key as W59's HMS-saved test basins write it.
- `dock_hms_structures.py`, `dock_breach.py`: the dock scenarios.
- `logs/`: the dock logs and the pictures they took.
