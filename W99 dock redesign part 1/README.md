# W99 dock redesign part 1

**Status (2026-11-16): all four steps of the brief are built and tested through the real dock. Steps 1 and 2 (the model
saved; the model type first) are merged into `feature/fast-products` (`bd4b4dd`). Steps 3 (the look and section
status) and 4 (the Simulation section), and a guard round the engine's settings, are on branch `feature/dock-redesign`
on top of that merge, not merged, nothing pushed.**

The requirements, the to-do list and the mockup are in `W94 dock redesign/`. This folder is the record of the first
build: what the dock does now, what was tested, what was decided on the way and is his to overturn, and what the next
parts will need from this one.

## What the dock does now

### Step 1: the model is saved

- **Every section gives its state and takes it back** (`Section.state()` / `restore()`, `sections/common.py`). A
  section lists nothing: its input widgets are found by walking its attributes (`widget_state.py`), so a widget added
  later is saved without anyone remembering it. 187 inputs are found in the eleven sections today. A layer is saved by
  its id, with its source, name, provider and CRS; tables whose rows are dataclasses (boundaries, refinement lines, dam
  start levels, breaches, hand-backs, Muskingum reaches, both gauge tables) are named in `state_rows`; Hydrology adds
  the generated basin's file and the mode of each subbasin.
- **One versioned model document** (`model_doc.py`, format `wadi2d-model`, now version 2): refusals in words (not a
  model file, saved by a newer plugin), and a table of migrations, used for the first time by step 4.
- **Saved with the QGIS project** (`model_store.py`), as one entry of the project's own properties, and restored when
  the project opens, whether the dock was already open or is opened afterwards. A new project puts the dock back to
  its defaults. Why in the project and not in a `<project>.wadi2d.json` beside it: a layer choice is a layer id, which
  means something only inside that project; it is saved and renamed with the project in one go, so the two cannot part;
  and an unsaved project has no place for a file beside it. The copies anyone can read without QGIS are the next two.
- **In every run folder**: Run (and Start study) writes `model.wadi2d.json` beside `job.json`.
- **Open a run** (the Model box at the top of the sections, and the start page): a finished run's folder refills the
  dock from its saved model, adds the layers the project lacks from their files, and makes the run's results the ones
  Make map, the sliders and Result lines work on. A run from before this work has only `job.json`: the dock takes
  what the job can tell (`job_states.py`), then builds the job the refilled dock would write and compares it with the
  run's own; what differs is listed in words. The list comes from that comparison, not from a list kept in the code.
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
- **A model with no word on its type gets the one it runs as**, by the engine's own rule (`model_types.inferred`).

### Step 3: the look, and the status of each section

- **One style sheet module**, `look.py`: the mockup's palette and metrics as named constants (`LIGHT`), the same roles
  for a dark QGIS theme (`DARK`), and one `sheet()` set on the dock's own frame and matched by object name, so the
  QGIS widgets inside the sections keep the user's theme. Every text is held to a contrast of 4.5 on its fill, in both
  palettes, by a test.
- **Each section is a card** (`section_card.py`). The section itself is untouched: its title, its arrow and its form
  are its own, and older checks that open it or read its title still do. The card adds a frame, lays the status pill
  (Ready, Optional, Missing) over the right end of the title line, and shows one line of words under the title,
  whether the section is open or closed. A Missing card has a red border, a red pill and red words.
- **Each section says where it stands**: `standing(kind)` returns the state and the words (`section_status.py`, plain
  Python). It reads the section's own widgets and nothing else: no layer is read feature by feature, so it is asked
  every second while the model page shows. It is a guide; the whole check on the job is still made at Check and run.
  **Not named `status()` as the brief asked**: Run and the Depth-area study each have a label called `status`, which
  the dock and older scenarios write to.
- **The step strip** over the sections (as `Setup_2D.dc.html`): one step a section, four to a line, with a mark and a
  colour for its state and the state in words for a pointer and a screen reader; a click opens the section and brings
  it to the top.
- **The footer** under the sections, always in sight: how many sections need the user, by name ("2 sections need you
  before running: Storm, Run"), and **Check and run**, which is Run's own check and start, with the Run section
  opened so the answer shows.
- **Never colour alone**: a pill carries its word, a step its mark and name, the footer its count and names, a card
  its words.
- **A dark QGIS theme** takes the dark palette when the dock is made (`shots/dark_start_page.png`,
  `shots/dark_model_page.png`, on Night Mapping).

### Step 4: the Simulation section

A section of its own before Run (`sections/simulation.py`, `simulation_rows.py`), heading `7c. Simulation`:

- **Run starts at**: one field for the whole run. It replaces the three "Run starts at" fields of the gridded rain,
  the rain gauges and the observed gauges, which now read this one. A start that is not a date stops the run in words.
- **Simulated time**, moved from Run.
- **2D time step**. Automatic: the Courant number, the largest and the smallest step, each written into the job only
  when moved off the engine's default. Fixed (advanced): one step. The engine has no fixed step of its own, so the
  dock holds one by setting the engine's largest and smallest step alike; the field's bounds are the engine's own
  (0.001 to 1 s, because its smallest step may be at most 1 s), said in words under the field, with what the engine
  does when the flow needs a shorter step: it stops the run and names the cell.
- **Lumped step** (`hydrology.time_step_min`), shown only for a model with a lumped part. With an HMS project, a step
  typed here replaces the control file's, and Run says so.
- **Save maps** (moved from Run) and **Save series every** (`outputs.series_every_s`).
- **Engine**: the one engine choice, moved from Run. The `Engine...` button for the engine's path stays at the top.
- A Lumped model shows neither the 2D step nor the maps.
- **At the defaults the job holds nothing new**: no `numerics`, no `time_step_min`, no `series_every_s`, no start.
- **A model saved by steps 1 and 2 still opens** (document format 1 to 2, `model_doc._to_2`): Run's three fields move
  to Simulation as they are, and the three starts become one, the rain's before the observed records'. What that
  moves or drops is said in words in the Model box ("The run has one start now, in the Simulation section: it took
  ... from the observed gauges"); a start that differed and is dropped, and a start typed for a rain source that was
  not in use, are each named.

### The guard round the engine's settings

`dock._schema_read` applied the engine's schema section by section with no guard: an error in one stopped the rest
and the restore of the model, while the dock looked ready. Each section is now applied on its own; one that fails is
named beside "Engine ready" with the error's own words, and its traceback goes to the Wadi2D log. Its own commit
(`38d9cf9`).

## Tests

Through the real dock (`tests/dock/run_check.ps1`, QGIS 3.44.8, a throwaway profile each), logs in `logs/`:

| Scenario | What it proves | Passed |
|---|---|---|
| `dock_model_saved_a.py` | every section has a state; an untouched dock changes no project; a dock filled in every section; the project saved at once | 16 of 16 |
| `dock_model_saved_b.py` | **a QGIS started afresh opens that project and the dock builds the same job, to the character, and every input file the same**; the same with the dock open first; a scenario saved and opened; five other kinds of input saved and brought back; a finished run opened into an empty project builds the run's own job; a run with only its job comes back whole, coordinates to the millimetre | 66 of 66 |
| `dock_model_type.py` | the start page; each type's sections, Hydrology rows and job; a real run of the 2D type; the type saved and read back; a model with no type inferred four ways; All sections; Open a run from the start page; Engine answering again keeps every field; a model file edited by hand | 71 of 71 |
| `dock_status.py` | step 3: every section in a card with a pill and words; the step strip and the footer; the status following the widgets through ten cases (a flow line with no file, a design storm with no pattern, crest lines with no elevation, the mesh and the corridors together, a gauge with no record ...); the type's say (Lumped with no network); a step opening its section; **Check and run refusing in words, then starting a real run that finishes**; a section that cannot take the engine's settings named, the model kept | 53 of 53 |
| `dock_dark.py` | step 3 on Night Mapping: the dark palette is taken, a Missing section and the footer still say so in words; the two screenshots | 7 of 7 |
| `dock_simulation.py` | step 4: the section before Run, one "Run starts at" in the whole dock; nothing new in the job at the defaults; the one start reaching a gridded rain, rain gauges and an observed record; the 2D step automatic and fixed, its bounds the engine's; **a real run at a fixed step of 0.25 s taking 1,440 steps in 0.1 h**; **a real run refused by the engine in its own words when the fixed step is longer than the flow allows**; the lumped step by model type; saved and brought back; maps and engine held while a run goes | 54 of 54 |
| `dock_model_migrated.py` | step 4: **the QGIS project saved by the plugin of steps 1 and 2 (document format 1) opens in the new dock and builds that plugin's job, to the character, and every input file**; the two rain-gauge runs that plugin wrote, each with a format 1 model, opened into an empty project build the jobs those runs wrote; what moved is said in words | 18 of 18 |

Run `dock_model_saved_a.py` before `dock_model_saved_b.py`, into the same throwaway folder: the second opens the
project the first saved. `dock_model_migrated.py` is run into the folder where the plugin of `bd4b4dd` ran
`dock_model_saved_a.py` and W77's `dock_gauges.py`. All run on the CPU engine, on Bidah at 30 m. The harness looks for
`.venv` in the checkout; a worktree has none, so link it to the main one (`mklink /J .venv <main checkout>\.venv`) and
take the link off before the worktree is removed.

`pytest`, without QGIS: `tests/plugin/test_model_doc.py` 8, `test_job_states.py` 5, `test_model_types.py` 11,
`test_section_status.py` 13 (the states and words of every section, the footer, both palettes' contrast),
`test_simulation_rows.py` 16 (the job at the defaults to the character, the fixed step validated by the engine's own
schema and one over its bound refused by it, the observed start, format 1 brought up seven ways). Rerun and unchanged:
`test_contract.py` 97, `test_job_builder.py` 47, `test_gauge_rows.py` 12, `test_storm_rows.py` 29,
`test_smoke_qgis.py` 2, `test_groups_qgis.py` 1. Every file of `tests/plugin`, one at a time: 651 passed in 43 files
(621 at the merge of steps 1 and 2). The engine's part of the suite was not run: no file of the engine is touched.

Three faults of this work found by tests, and fixed.

- In steps 1 and 2, found by `dock_model_type.py`: a saved choice was put into any empty list to wait for the engine's
  answer, which is right for the series of a rain file and wrong for the HMS file lists (a model whose HMS folder was
  gone left a file name with no folder, and the next answer of the engine stopped the dock halfway). It now waits
  only where a section names the list (`state_hold`).
- In step 3, found by `test_smoke_qgis.py`: the Structures status read an elevation field of a wall layer, which has
  none; outside QGIS proper an error in a timer's slot ends the process. A status that fails is now logged and shown
  as unknown, and never stops the dock.
- **In step 1, and so in the merge of steps 1 and 2, found by the older `dock_suggest.py` (W26) on the step 4 commit:**
  Suggest breaklines leaves a helper on the Mesh section that points back at the dock, and the walk that finds a
  section's inputs followed it through the whole dock. From step 1 on that put other sections' widgets into the Mesh
  section's saved state once Suggest had been pressed (no scenario saw it: the job was not affected). With step 3's
  cards in the dock the walk met an object it could not read and failed, every two seconds and, worse, on the copy of
  the model written at Run, **so a run after Suggest breaklines never started**. The walk now takes only widgets laid
  out inside the section, and neither keeping the model nor writing a run's copy can stop anything (`ed1b2cf`).
  This is why the older scenarios are run on the last commit and not only read as "untouched".

## What stayed as it was, and how that was checked

### Steps 3 and 4 (this round)

Ten dock scenarios written before this work were run on the merge of steps 1 and 2 and on the last code commit of
this branch, each batch from a clean copy of its commit, and **every `job.json` they wrote was compared**:

| Scenario | On the merge of steps 1 and 2 (`bd4b4dd`) | On this branch (`ed1b2cf`, the last code commit) |
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

**The counts are the same in all ten, and so is every job.** The scenarios wrote 27 `job.json` files on each side: the
22 of runs are identical to the character once each batch's own folder is taken out of the paths; the 5 of the
profile editor's terrain previews are identical once their two random scratch names are taken out as well. Among
them are the two runs of `dock_gauges.py`, which type a start into the rain gauges' field and the observed gauges'
field: the same job from the one field. The four that do not pass stop on the base commit at the same check.

The batch was first run on the step 4 commit (`92d97b2`), and there `dock_suggest.py` did not finish: the fault in
the walk described under Tests. It was fixed and the whole batch run again on the fix; the table is that run.
Logs of both sides in `old_scenarios_2/`; the comparing scripts are those of `old_scenarios/`.

### Steps 1 and 2 (the first round)

Fifteen older scenarios, on `cf872e7` (before this work) and `7372fa8` (the end of step 2): the same counts in all
fifteen, and all 38 `job.json` files the same (33 to the character, the 5 terrain-preview jobs once their random
scratch names are taken out). Four were run once more after the last commit of that round, their 8 jobs identical.
Logs and the three scripts in `old_scenarios/`.

### What that leaves unproven

Several older scenarios no longer pass on the base commit itself: they were written for an earlier dock and nobody has
kept them up. By their own messages, not chased further: a layer group they look for is not there, `composite_box` is
no longer a name in the study section, words in the Result lines plot and the lag method differ, his HMS project lost
a file. Each stops at the same check with the same numbers before and after this work, and says nothing about what
comes after its stop. So the time slider, the later Result lines checks, the depth-area study and the cell grid layer
were not exercised by an old scenario on either side. For those the evidence is of another kind: none of their files
is touched (`result_lines.py`, `line_view.py`, `slider_layer.py`, `time_layer.py`, `map_sheets.py`,
`workbook_dialog.py`, `element_view.py`, `layer_groups.py`), and the new scenarios find Result lines offered on a
finished run. Make map, the workbook and the right-click chart were not run here. The harness leaves the start page by
`All sections, no model type` before an older scenario starts: that is the dock those were written for.

## Decisions taken here that are his to overturn

From steps 1 and 2:

1. **The model lives in the QGIS project**, not in a file beside it (reasons above).
2. **The project's copy is kept by a 2 s timer** that compares the dock with what was last written, and by the
   project's own "writing" signal. A change in the dock marks the project as modified, so QGIS asks to save on closing.
3. **A new project empties the dock** and returns it to the start page.
4. **Pressing OK in Engine... no longer resets every field**. The fields are held and put back.
5. **Open a run adds missing layers to the project** from their files, and says which. Opening a project never does.
6. **Open a run and Open scenario start from the defaults**, so a setting newer than the file takes its default.
7. **Scenarios are files in `scenarios/` inside the output folder**, as the generated basin's folder is.
8. **`All sections, no model type`** is not in the mockup. It keeps the old dock reachable from the start page.
9. **Hybrid 2D enters at the outlets**, set by the type; the engine would also take the HMS reaches there.
10. **Lumped hides Mesh, Boundaries and the Depth-area study**, and keeps Terrain and Structures. The mode of each
    subbasin stays the table's under every type.
11. **The depth cutoff for drawing is not in the model**: a display setting kept with QGIS, as before.
12. **Which page shows is saved but does not mark the project as changed**.

From steps 3 and 4:

13. **The sections keep their numbered titles**, and the new one is `7c. Simulation`. Older scenarios hold the titles
    ("8. Run", "6. Boundaries", "7b. Gauges (optional)"), so dropping or renumbering them, which the review of
    2026-11-16 asked for, would break those checks; it is one edit a title when he says so.
14. **The status is a quick guide, not the check.** It reads widgets only. What needs the features of a layer (a
    crest line whose elevation is missing on one line, an initial water polygon with no level, a gauge that names a
    line that is not there) is still found by Check and run, in Run's words. The alternative, the whole job check every
    second, reads every layer every second.
15. **Check and run starts the run**; there is no Check page as in `Check.dc.html` (not in this part). It opens Run,
    where the refusal or the progress shows.
16. **The steps lie four to a line**, in two or three lines, so the longer names are whole at the width of a dock.
    The mockup has five steps on one line; this dock has up to eleven.
17. **Optional, for a section with nothing set and nothing needed**: Mesh off, no structures, no boundary lines (every
    edge a wall: allowed, and said), no result points, no gauges, the depth-area study, and Hydrology of a 2D model
    with no curve number ("no losses: all the rain on the grid runs off").
18. **A fixed step is the engine's two bounds set alike**, 0.001 to 1 s. The engine has no other way, and it does not
    shorten such a step: it stops. A fixed step above 1 s needs the engine's bound on its smallest step lifted.
19. **The one start: the rain's wins over the observed records'** when an older model held both and they differed.
    With a gridded rain the observed records carry no start of their own in the job, as before: the engine reads them
    from the rain's.
20. **The start is checked as an ISO date and time** (`2021-10-04 00:00`) before a run; it was not checked before, and
    the engine read whatever was typed.
21. **The dark palette is mine**, the mockup has none: the same roles, each text at a contrast of 4.5 or more on its
    fill. It is chosen once, when the dock is made; QGIS itself asks for a restart to change its theme.
22. **The model document is format 2.** A plugin of steps 1 and 2 refuses a format 2 file in words ("saved by a newer
    Wadi2D"); it does not misread it.
23. **Save maps stays the two choices it was** (every 15 minutes for design work, every 5 for an animation), moved as
    it is. A free interval is one number box more; older scenarios pick the second choice by its place.

## Not done

- No Check page, no results view, no recent runs on the start page, no "New model / Open results" tabs: later parts.
- The frames window, resume from a checkpoint and the checkpoint interval, which the review listed with the
  Simulation panel, are not in it: the brief of this part did not name them.
- "Name the cell that sets the time step" is still in Run; the review calls it a diagnostic for Advanced.
- Not tested through the dock: a generated basin saved and restored, a project with a layer removed since it was
  saved, Blend of Gray (the other dark theme), QGIS 3.36, a run the dock follows after QGIS restarts being brought to
  the model page, the lumped step replacing an HMS control file's in a real hybrid run.
- The status of a section does not see what only the features of a layer can tell (decision 14).
- A dock narrower than about 450 px scrolls sideways when Hydrology is open, as before the cards: its basin box
  needs 436 px. The pills of the cards then lie outside the view; their words do not.
- No human hand has clicked a card, a step or Check and run yet.

## What the next parts need from this one

- **Any new section** (the split ARF, Data tables): a `Section` subclass with a `key`, added to `dock.sections` and
  to `model_types.ALL_SECTIONS` (a dock check holds the two together), a name in `section_status.STEP_NAMES`, and a
  `standing()`; `sections/simulation.py` is the example. Its inputs are saved with no further code, its row tables
  through `state_rows`; it gets its card, its step and its place in the footer's count by being in `dock.sections`.
  Hidden for a type through `ModelType.hidden`; rows that depend on the type through its own `set_model_type(kind)`.
- **New widgets in existing sections** (rain options, CN override, Manning forms, inflow tables, initial-level
  points, mesh kinds, domain from an outline): saved by the walk. An old document simply lacks them, and Open starts
  from the defaults. A value that is not a widget goes through `extra_state()` / `restore_extra()`. What they can
  miss goes into the section's `standing()` and its function in `section_status.py`.
- **A widget that moves between sections, or changes meaning**: a function in `model_doc.MIGRATIONS` and a version
  up, as `_to_2` does; its words go under `MIGRATED` and reach the user through the Model box.
- **A value the type owns** in the job: `model_types.apply_type`, with its test in `test_model_types.py`.
- **Data tables shared by sections** (patterns, ARF curves): a part of the document beside `sections`, through
  `dock.model_parts()` / `set_model_parts()`, and named in `model_doc.MATTERS` so a change marks the project.
- **The Check page**: `StatusLinks.check_and_run` is where the footer's button lands; the statuses are in
  `StatusLinks.statuses`, the whole check is `job_builder.problems`, the estimate is the dock's `estimate()`.
- **The results view**: a third page of `dock.pages`; `dock.show_run(folder)` is the one way a run becomes the dock's
  results; pinned elements are a part of the document.
- **Scenarios with inheritance and the batch queue**: a scenario is a whole document today. `ModelLinks.collect()` and
  `apply()` are the only two doors; a scenario that stores its differences from a base is a format 3 of `model_doc`
  with a migration, and a batch is `collect()`, change, `build_job`, repeated.
- **Anything drawn in the dock's own frame**: a colour or a size is a constant of `look.py`, in both palettes; the
  contrast test takes a new pair of text and fill in one line.

## Found wrong in the current dock on the way

1. **Engine... reset the whole dock** on OK. Fixed in step 1.
2. **An error in any section's `apply_schema` stopped the dock halfway**, with no word. Guarded now (`38d9cf9`).
3. **`W68 .../hms_copy.py` no longer runs**: it copies `HEC_HMS_Block_02.gage`, which his HMS project no longer has.
   `dock_hms_structures.py` (W68) and the HMS part of `dock_wiring_gaps.py` (W75) fail on the base commit too. Not
   fixed: his project is the source, and the scenario's owner should say which file replaces it.
4. **Older dock scenarios are not kept up**: of fifteen run on the commit before this work, nine do not pass there
   (the table in `old_scenarios/`). Nobody runs them after a change to the dock, so they stop proving anything.
5. **A job cannot be rebuilt to the last digit from its own `inputs/` folder**: the job keeps its result lines and
   boundaries at full precision, the GeoJSON beside it is rounded to the millimetre. Harmless (0.5 mm).
6. **The rain refusal reads "Set the rain, or choose an HMS project"** under a 2D type, where an HMS project is no
   answer. Left for the rain part of the redesign.
7. **`dock.py` (1,082 lines) and `job_builder.py` (840) are far over the project's own rule** of a few
   hundred lines. This work put everything it could in new modules; the dock's own file still grew by the wiring.
8. `shaped_rows.py` uses `zip(strict=)`, so the plugin already needs Python 3.10: fine on QGIS 3.36 for Windows
   (Python 3.12), not on a 3.9 build.
9. **Run and the Depth-area study each have a widget named `status`**, so no section can have a method of that name
   (decision in step 3 above).
10. **Outside QGIS proper, an error in any slot ends the process without a word** (PyQt's rule; QGIS installs its own
    handler). The headless smoke test dies with an exit code and no traceback; a hook that prints the error first would
    save the next person an hour.
11. **Hydrology's basin box needs 436 px**, wider than a dock of the mockup's 420 px.
12. **The start of a run was free text with no check** in three places; a typing error reached the engine.
13. The logs kept in the W folders, these included, hold local paths. The repository is public.

## Files

New in `plugin/wadi2d_qgis/`. Steps 1 and 2: `widget_state.py`, `model_doc.py`, `model_store.py`, `model_bar.py`,
`job_states.py`, `job_reader.py`, `model_types.py`, `type_links.py`, `start_page.py`, `look.py`. Step 3:
`section_status.py` (states and words, plain Python), `section_card.py`, `status_bars.py` (the strip and the footer),
`status_links.py` (what fills them). Step 4: `simulation_rows.py` (plain Python), `sections/simulation.py`.
Changed: every `sections/*.py` (a key, row tables, `standing()`; Run lost three fields, Storm and Gauges their starts),
`dock.py`, `job_builder.py` (`run.model_type`, the type's and the simulation's refusals, the three new job parts),
`gauge_rows.py` (the observed start under a gridded rain), `tests/dock/harness.py` (`open_dock(all_sections=True)`).

Here: the seven scenarios, `model_fill.py` and `model_variants.py` which they load, `logs/`, `shots/`,
`old_scenarios/` (round one) and `old_scenarios_2/` (this round).
