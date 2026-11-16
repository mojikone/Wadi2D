# W99 dock redesign part 1

**Status (2026-11-16): steps 1 and 2 of the four are built and tested through the real dock, on branch
`feature/dock-redesign` off `feature/fast-products`; not merged, nothing pushed. Steps 3 (the look and the status of each
section) and 4 (the simulation panel) are not built: the brief's four-hour rule stopped the work at the end of step 2.**

The requirements, the to-do list and the mockup are in `W94 dock redesign/`. This folder is the record of the first
build: what the dock does now, what was tested, what was decided on the way and is his to overturn, and what the next
parts will need from this one.

## What the dock does now

### Step 1: the model is saved

- **Every section gives its state and takes it back** (`Section.state()` / `restore()`, `sections/common.py`). A
  section lists nothing: its input widgets are found by walking its attributes (`widget_state.py`), so a widget added
  later is saved without anyone remembering it. 182 inputs are found in the ten sections today. A layer is saved by its
  id, with its source, name, provider and CRS; tables whose rows are dataclasses (boundaries, refinement lines, dam
  start levels, breaches, hand-backs, Muskingum reaches, both gauge tables) are named in `state_rows`; Hydrology adds
  the generated basin's file and the mode of each subbasin.
- **One versioned model document** (`model_doc.py`, format `wadi2d-model`, version 1): refusals in words (not a model
  file, saved by a newer plugin), a table of migrations for later formats.
- **Saved with the QGIS project** (`model_store.py`), as one entry of the project's own properties, and restored when
  the project opens, whether the dock was already open or is opened afterwards. A new project puts the dock back to
  its defaults. Why in the project and not in a `<project>.wadi2d.json` beside it: a layer choice is a layer id, which
  means something only inside that project; it is saved and renamed with the project in one go, so the two cannot part;
  and an unsaved project has no place for a file beside it. The copies anyone can read without QGIS are the next two.
- **In every run folder**: Run (and Start study) writes `model.wadi2d.json` beside `job.json`.
- **Open a run** (the Model box at the top of the sections, and the start page): a finished run's folder refills the
  dock from its saved model, adds the layers the project lacks from their files, and makes the run's results the ones
  Make map, the sliders and Result lines work on. A run from before this work has only `job.json`: the dock takes
  what the job can tell (`job_states.py`: the DEM, the input files the job builder wrote into `inputs/`, the numbers),
  then builds the job the refilled dock would write and compares it with the run's own; what differs is listed in
  words. The list comes from that comparison, not from a list kept in the code.
- **Save as scenario / Open scenario**: a named copy of the document in `scenarios/` inside the output folder.

### Step 2: the model type first

- **A start page** as `Main.dc.html` draws it: a card each for 2D, Lumped, Hybrid Lumped and Hybrid 2D with its
  one-line meaning and what in it is lumped and what is 2D, a finished run to open, and `All sections, no model type`,
  which is the dock as it was.
- **The choice writes `run.model_type`** into the job (only when a type is chosen, and only when the engine has the
  field), shows as a badge and in words in the header over the sections, with `Types` as the way back and a
  `Show all sections` switch where the type hides any.
- **Which sections show**: Lumped hides Mesh, Boundaries and the Depth-area study; the other three hide none. In
  Hydrology a 2D model shows only the transmission loss and the curve number.
- **The three ticks the type sets** show only where a choice is left:

  | | The HMS way only | Leave the catchments out of the mesh | Lumped water enters the 2D model |
  |---|---|---|---|
  | 2D | not shown (no lumped part) | not shown | not shown |
  | Lumped | on, not shown | not shown | not shown; "each element at its own area" stays a choice |
  | Hybrid Lumped | off, not shown | on, not shown | **a choice**: at the outlets, or down the HMS reaches |
  | Hybrid 2D | off, not shown | off, not shown | at the outlets, not shown |
  | no type | shown | shown | shown |

- **The type's own values are laid over the dock's** when a job is built (`model_types.apply_type`); no widget is
  emptied. A 2D model with an HMS project still chosen leaves it out of the job, and the header says so.
- **A model with no word on its type gets the one it runs as**, by the engine's own rule (`model_types.inferred`): a
  document saved without one, and a run opened from its job alone.

## Tests

Through the real dock (`tests/dock/run_check.ps1`, QGIS 3.44.8, a throwaway profile each), logs in `logs/`:

| Scenario | What it proves | Passed |
|---|---|---|
| `dock_model_saved_a.py` | every section has a state; an untouched dock changes no project; a dock filled in every section; the project saved at once | 15 of 15 |
| `dock_model_saved_b.py` | **a QGIS started afresh opens that project and the dock builds the same job, to the character, and every input file the same**; the same with the dock open first; a scenario saved and opened; five other kinds of input saved and brought back (rain gauges, hyetograph and a flow line, gridded rain, corridors with an embankment and a breach, an HMS project with modes and Muskingum numbers); a finished run opened into an empty project builds the run's own job; a run with only its job comes back whole, coordinates to the millimetre | 66 of 66 |
| `dock_model_type.py` | the start page; each type's sections, Hydrology rows and job; a real run of the 2D type; the type saved and read back; a model with no type inferred four ways; All sections; Open a run from the start page; Engine answering again keeps every field; a model file edited by hand | 71 of 71 |

Run `dock_model_saved_a.py` before `dock_model_saved_b.py`, into the same throwaway folder: the second opens the
project the first saved. All three run on the CPU engine, on Bidah at 30 m. The harness looks for `.venv` in the
checkout; a worktree has none, so link it to the main one (`mklink /J .venv <main checkout>\.venv`) and take the link
off before the worktree is removed.

`pytest`, without QGIS: `tests/plugin/test_model_doc.py` 8, `test_job_states.py` 4, `test_model_types.py` 11 (two of
them against the engine: the type names are the engine's, and it reads an untyped job as the dock does).
Rerun and unchanged: `test_contract.py` 97, `test_job_builder.py` 47, `test_build_release.py` 14,
`test_install_plugin.py` 6, `test_smoke_qgis.py` 2, `test_groups_qgis.py` 1, `test_chart_qgis.py` 1. The full suite
was not run.

A fault of this work found by its own scenario, and fixed: a saved choice was put into any empty list, to wait for the
engine's answer. That is right for the series of a rain file and wrong for the HMS file lists: a model whose HMS folder
was gone left a basin file's name with no folder behind it, and the next answer of the engine (Engine..., OK) then
stopped the dock halfway through. The saved choice now waits only where a section names the list (`state_hold`).

## What stayed as it was, and how that was checked

Fifteen dock scenarios written before this work were run on the base commit and on this branch, each batch from a
clean copy of its commit, and **every `job.json` they wrote was compared**:

| Scenario | On the base commit (`cf872e7`) | On this branch (`7372fa8`, the end of step 2) |
|---|---|---|
| `dock_cell_grid.py` (W17) | 3 passed, 1 failed, stopped by an exception | 3 passed, 1 failed, stopped by an exception |
| `dock_boundary_table.py` (W18) | 34 passed, 0 failed | 34 passed, 0 failed |
| `dock_time_slider.py` (W19) | 8 passed, 0 failed, stopped by an exception | 8 passed, 0 failed, stopped by an exception |
| `dock_result_lines.py` (W21) | 42 passed, 4 failed, stopped by an exception | 42 passed, 4 failed, stopped by an exception |
| `dock_profile_editor.py` (W22) | 120 passed, 0 failed | 120 passed, 0 failed |
| `dock_mesh_controls.py` (W23) | 44 passed, 1 failed, stopped by an exception | 44 passed, 1 failed, stopped by an exception |
| `dock_suggest.py` (W26) | 32 passed, 0 failed | 32 passed, 0 failed |
| `dock_basin_bidah.py` (W27) | 47 passed, 5 failed | 47 passed, 5 failed |
| `dock_dam_start.py` (W34) | 23 passed, 0 failed | 23 passed, 0 failed |
| `dock_backend_arf.py` (W37) | 7 passed, 0 failed, stopped by an exception | 7 passed, 0 failed, stopped by an exception |
| `dock_flow_line.py` (W61) | 13 passed, 1 failed | 13 passed, 1 failed |
| `dock_breach.py` (W68) | 14 passed, 0 failed | 14 passed, 0 failed |
| `dock_basin_points.py` (W73) | 36 passed, 0 failed | 36 passed, 0 failed |
| `dock_wiring_gaps.py` (W75) | 33 passed, 1 failed, stopped by an exception | 33 passed, 1 failed, stopped by an exception |
| `dock_gauges.py` (W77) | 42 passed, 1 failed | 42 passed, 1 failed |

**The counts are the same in all fifteen, and so is every job.** The scenarios wrote 38 `job.json` files on each side: the
33 of runs are identical to the character once each batch's own folder is taken out of the paths; the 5 of the
profile editor's terrain previews are identical once their two random scratch names (the preview folder, the editor's
draft file) are taken out as well.

After the last commit (`894048c`, the restore made safe at its edges), four of them were run once more from the
branch itself: `dock_boundary_table.py` 34 of 34, `dock_dam_start.py` 23 of 23, `dock_breach.py` 14 of 14,
`dock_basin_points.py` 36 of 36, their 8 `job.json` files identical to the base commit's.

Nine of the fifteen do not pass on the base commit itself: they were written for an earlier dock and nobody has kept
them up. By their own messages, not chased further: a layer group they look for is not there, `composite_box` is no
longer a name in the study section, words in the Result lines plot and the lag method differ, his HMS project lost a
file. They are here as they are: each stops at the same check with the same numbers before and after this work.

**What that leaves unproven.** A scenario that stops early says nothing about what comes after the stop. So the time
slider (W19 stops at its 8th check), the later Result lines checks (W21), the depth-area study (W37 stops at its 7th)
and the cell grid layer were not exercised by an old scenario on either side. For those the evidence is weaker and of
another kind: none of their files is touched (`result_lines.py`, `line_view.py`, `slider_layer.py`, `time_layer.py`,
`map_sheets.py`, `workbook_dialog.py`, `element_view.py`, `layer_groups.py`, `sections/study.py` but for its key), and
the new scenarios open Result lines' button on a finished run. Make map, the workbook and the right-click chart were
not run here.

The logs of both sides and the three scripts that made the table and compared the jobs are in `old_scenarios/`.

The harness now leaves the start page by `All sections, no model type` before an older scenario starts: that is the dock
those were written for.

## Decisions taken here that are his to overturn

1. **The model lives in the QGIS project**, not in a file beside it (reasons above).
2. **The project's copy is kept by a 2 s timer** that compares the dock with what was last written, and by the
   project's own "writing" signal. A change in the dock marks the project as modified, so QGIS asks to save on closing.
3. **A new project empties the dock** and returns it to the start page.
4. **Pressing OK in Engine... no longer resets every field** (it did: the schema was applied again over the user's
   values). The fields are held and put back.
5. **Open a run adds missing layers to the project** from their files, and says which. Opening a project never does.
6. **Open a run and Open scenario start from the defaults**, so a setting newer than the file takes its default, not
   what the dock happened to hold.
7. **Scenarios are files in `scenarios/` inside the output folder**, as the generated basin's folder is.
8. **`All sections, no model type`** is not in the mockup. It keeps the old dock reachable from the start page and is
   what a job without `run.model_type` needs.
9. **Hybrid 2D enters at the outlets**, set by the type; the engine would also take the HMS reaches there. The task's
   own definition ("their water routed on the 2D mesh") decided it.
10. **Lumped hides Mesh, Boundaries and the Depth-area study**, and keeps Terrain and Structures: Generate basin reads
    both, and the dock's job needs the DEM. The mode of each subbasin stays the table's under every type.
11. **The depth cutoff for drawing is not in the model**: it is a display setting kept with QGIS, as before.
12. **Which page shows is saved but does not mark the project as changed**: looking at the start page is not an edit.

## Not done

- **Step 3, the look and section status**: no cards with status pills, no `status()` per section, no step strip, no
  sticky footer with Check and run. Only the start page and the header carry the mockup's look.
- **Step 4, the simulation panel**: nothing. The three "Run starts at" fields, the engine choice and the intervals are
  where they were.
- A run the dock follows after QGIS restarts is brought to the model page (`attach_if_live`): written, not tested.
- Not tested through the dock: a generated basin saved and restored (the file is read back by `BasinBox.take`; no
  scenario generates one), the depth-area study's own run copy, a project with a layer removed since it was saved (the
  words are tested only for a hand-edited file), the dark QGIS theme, QGIS 3.36.
- The recent runs list of the mockup's start page; the mockup's "New model / Open results" tabs (the results view is
  a later part).
- No human hand has clicked a card yet.

## What the next parts need from this one

- **Any new section** (the split ARF, the simulation panel, Data tables): a `Section` subclass with a `key`, added
  to `dock.sections` and to `model_types.ALL_SECTIONS` (a dock check holds the two together); its inputs are saved
  with no further code, its row tables through `state_rows`. Hidden for a type through `ModelType.hidden`; rows that
  depend on the type through its own `set_model_type(kind)`, which `TypeLinks.refresh` already calls on every section.
- **New widgets in existing sections** (rain options, CN override, Manning forms, inflow tables, initial-level
  points, mesh kinds, domain from an outline): saved by the walk. An old document simply lacks them, and Open starts
  from the defaults. A value that is not a widget goes through `extra_state()` / `restore_extra()`.
- **A value the type owns** in the job: `model_types.apply_type`, with its test in `test_model_types.py`.
- **Data tables shared by sections** (patterns, ARF curves): a part of the document beside `sections`, through
  `dock.model_parts()` / `set_model_parts()`, and named in `model_doc.MATTERS` so a change marks the project.
- **Step 3**: `look.py` already names the status colours, the pill, the step and the footer and has their rules,
  unused so far. A section's `status()` sits beside its `state()`; the strip goes between `dock.header` and the scroll
  area, the footer under it, both inside the model page built in `dock.py`.
- **Step 4**: a section before Run. The three start fields are `storm.start`, `storm.gauge_start` and `gauges.start`
  in a saved model; a migration in `model_doc.MIGRATIONS` moves an old document's value into the one field.
- **The results view**: a third page of `dock.pages`; `dock.show_run(folder)` is the one way a run becomes the dock's
  results; pinned elements are a part of the document.
- **Scenarios with inheritance and the batch queue**: a scenario is a whole document today. `ModelLinks.collect()` and
  `apply()` are the only two doors; a scenario that stores its differences from a base is a format 2 of `model_doc`
  with a migration, and a batch is `collect()`, change, `build_job`, repeated.

## Found wrong in the current dock on the way

1. **Engine... reset the whole dock** on OK. Fixed here (decision 4).
2. **`W68 .../hms_copy.py` no longer runs**: it copies `HEC_HMS_Block_02.gage`, which his HMS project no longer has.
   `dock_hms_structures.py` (W68) and the HMS part of `dock_wiring_gaps.py` (W75) therefore fail on the base commit
   too (W75: 33 passed, then the exception). Not fixed: his project is the source, and the scenario's owner should say
   which file replaces it.
3. **`dock_cell_grid.py` (W17) and `dock_mesh_controls.py` (W23) fail on the base commit**: they look for the cell
   grid layer where it was before W68's layer groups. Not fixed.
4. **A job cannot be rebuilt to the last digit from its own `inputs/` folder**: the job keeps its result lines and
   boundaries at full precision, the GeoJSON beside it is rounded to the millimetre. Harmless (0.5 mm), but it is why
   an old run is compared to the millimetre.
5. **The rain refusal reads "Set the rain, or choose an HMS project"** under a 2D type, where an HMS project is no
   answer. Left for the rain part of the redesign.
6. **`dock.py` (1,042 lines) and `job_builder.py` (827) are far over the project's own rule** of a few hundred lines.
   This work added 67 lines of wiring to the first and 4 to the second, and put everything else in new modules.
7. `shaped_rows.py` uses `zip(strict=)`, so the plugin already needs Python 3.10: fine on QGIS 3.36 for Windows
   (Python 3.12), not on a 3.9 build.
8. **An error in any section's `apply_schema` stops the dock halfway**, with no word to the user: `dock._schema_read`
   has set the schema by then, so the dock looks ready. Hydrology's reads the chosen HMS basin file with no check that
   it is still there. It cannot happen from the widgets alone today (the list comes from the folder); it is the door
   the fault above came through. Not changed.
9. The logs kept in the W folders, these included, hold local paths. The repository is public (item 5 of his list
   under Next steps).

## Files

New in `plugin/wadi2d_qgis/`: `widget_state.py` (a widget's value out and in, the walk), `model_doc.py` (the
document), `model_store.py` (project, run folder, scenarios), `model_bar.py` (the Model box), `job_states.py` and
`job_reader.py` (a run with only its job), `model_types.py` (the four types), `type_links.py` (what a type does in the
dock), `start_page.py` (the cards and the header), `look.py` (palette and metrics). Changed: `sections/*.py` (a key
each, row tables named; Hydrology's lumped rows in one box and `set_model_type`), `dock.py` (two pages, the wiring),
`job_builder.py` (`run.model_type`, the type's refusal), `tests/dock/harness.py` (`open_dock(all_sections=True)`).

Here: the three scenarios, `model_fill.py` and `model_variants.py` which they load, `logs/`, `shots/`.
