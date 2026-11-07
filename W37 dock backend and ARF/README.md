# W37 dock backend and ARF

**Status (2026-11-07): done on QGIS 3.44.8, branch `feature/dock-backend-arf`, not merged, not pushed. 55 of 55 through
the real dock on Bidah at 40 m (`log_dock_backend_arf.txt`); the full suite, 1,830 tests, passes on the branch.** The Run section has an Engine choice (Automatic, GPU only,
CPU only), written into the job only when it is not Automatic. A new section, **9. Depth-area study**, runs the study from
the dock with storm areas that bracket the drainage areas by default, shows which run of how many and how many are left,
stops on request, and ends with a table of design flows and the file it is in. Folded in his amendment of 2026-11-07:
lumped elements get design flows too, an element with no 2D water above it from a lumped rerun at its own area.
**Measured: Bidah 03 read between the 10 and 30 km2 runs is 0.39 % below the run at its own 20.971 km2.**

## [PRESERVE-CHECK]

- **KEEP:** every existing job and its hash: the engine choice and a line's drainage area enter the job only when set, a
  run's job never carries an `arf` block, and the three new `arf` fields are out of `job_hash`, so old checkpoints resume.
  `wadi2d arf` on an old job gives the same areas, runs and line rows as before; its rows gain one column, `read_as`, at
  the end. The Run section, its buttons, the estimate and every other section behave as they did. The composite code is
  the existing one, untouched. The Structures section (another agent's) is not touched.
- **CHANGE:**
  1. Run section: an **Engine** choice, the schema's `run.backend` enum and default; only a choice other than Automatic is
     written. The crash message points at it.
  2. A new section **9. Depth-area study**: storm areas, an experimental composite tick, Start and Stop, progress with
     the runs left, the table and its file. Results points gain a **Drainage area field**.
  3. Engine, his amendment of 2026-11-07: the study names each run before it starts (`run` event); `arf.bracket`
     (with `bracket_ratio` 2, `bracket_max` 6) spans the storm areas over the drainage areas the table needs; lumped
     elements get rows of their own: no 2D water above, rerun lumped at their own area; fed by a hand-back, read from
     the 2D runs; otherwise listed as on the grid, with no row.
- **FILES:** `plugin/wadi2d_qgis/sections/run.py`, `job_builder.py` (constants, two `if`s), `protocol.py` (names, two
  helpers, the crash words), `engine_process.py` (two hooks in `EngineRun.start`, the new `StudyRun`), `dock.py` (the
  study's wiring; `_checked_values`, `_prepare`, `_safely` take who speaks), `live_layer.py` (`load_maps` takes a
  folder), `sections/points.py`, new `sections/study.py`, `study_rows.py`, `study_state.py`, the plugin README;
  `wadi2d/arf.py`, new `wadi2d/arf_network.py`, `wadi2d/run.py` (`LumpedView`, `lumped_view`, `lumped_rain_at`, three
  `NOT_WATER` entries), `wadi2d/config/schema.py` (three `ArfStudy` fields); tests in `tests/plugin` and `tests/engine`,
  the fake engine, the QGIS smoke test, the frozen schema sample.

## What was built

**Engine choice.** A combo in Run, filled from `run.backend`'s enum, starting on its default. Automatic leaves the job
byte for byte as before; GPU only or CPU only adds `run.backend`. The estimate, the run, the pixel maps and a study all
read it from the job. Held while a run or a study goes.

**The study, its own section.** A section rather than rows in Run, because it has its own inputs (storm areas, the
composite tick), its own two buttons and its own result, a table; Run's rows stay as they were. It uses everything above
it, Run's output folder and Run's engine, and writes to `<folder>_arf` beside the output folder (`_arf_2` when one
exists), so it shares `wadi2d_cache` with the runs. One engine process runs the whole study (`wadi2d arf`); the dock
follows the study's `progress.jsonl` and, from the new `run` event, the progress file of the run in progress:
`Run 2 of 3, storm area 30 km2; 1 run left after it. 11 h 00 min of 48 h 00 min | step 1.93 s | ...`. **Stop study**
writes the stop file; the run in progress finishes its step and writes its maps, and the study ends with no table, as
the engine always did; the dock says `Stopped after 1 of 3 runs`. A study is not re-attached after QGIS restarts, as a
run is.

**His amendment, item by item:**

| Item | Built |
|---|---|
| One 2D run per storm area, log-spaced; by default the bins bracket the design points' drainage areas, 5 to 6 at most | **Yes.** `arf.bracket`: from the smallest to the largest drainage area of the design lines and of the lumped elements a hand-back feeds, log-spaced, neighbours at most 2 x apart, at most 6; one area when all are equal. The dock's default; the engine's own default stays off, so `wadi2d arf` on an old job is unchanged. Log-spaced between two areas and listed areas remain. |
| Rain x ARF(area) on lumped and 2D alike in each run | **Already so** (each run is the job with `storm_area_km2` set; W20 showed lumped and 2D take the same rain). Checked: every run read 205.4 mm x ARF of its own area to 1e-9. |
| Every design point and every lumped element reads the two runs bracketing its drainage area, on log area; one table per point | **Yes**, for design lines and for lumped elements a hand-back feeds. Points carry no flow and get no row; the dock says so. One table, `design_points.csv`, with a `read_as` column. |
| A lumped element with no 2D water above it: exact-area lumped-only rerun, no interpolation | **Yes.** It is rerun alone, its upstream only, with the storm at its own drainage area; equal to HMS's depth-area algorithm (`analyse_point`) to 1e-9 in `tests/engine/test_arf_network.py`. An element whose upstream water runs on the grid and never comes back has no network flow of its own: it gets no row and the dock names it. |
| 2D runs = area bins, never HMS elements | **Yes**: Study B, 17 rows from 2 runs. |
| Composite map behind a tick, experimental, off by default | **Yes**, wired to the existing code: a flow accumulation raster and its units; the three rasters load as `<study> composite`. |
| Per-point exact-area tick | **Not built**, as he said. The engine's old `arf.exact_points` stays for the command line; the dock does not offer it. |

## Results through the real dock

`dock_backend_arf.py`, Bidah 03's domain at 40 m, Block 2's HMS project, 55 of 55. Run times are not findings: the GPU
was shared with another agent's runs.

**Study A**, the HMS storm (FM_100yr, 205.4 mm, its ARF FM table), all 18 HMS subbasins rain-on-grid, no CN raster so
each HMS subbasin's own losses apply, 48 h from the control file, storm areas 10, 20.971 and 30 km2, Automatic engine:

| Storm area, km2 | ARF | Depth read by the run, mm | Bidah 03 line peak, m3/s |
|---|---|---|---|
| 10 | 0.987 | 202.730 | 628.785 |
| 20.971 | 0.97493 | 200.251 | 618.793 |
| 30 | 0.965 | 198.211 | 610.500 |

- [Certain] Each run started on the GPU, its job has no `run.backend`, its storm area is its own.
- [Certain] The table's row reads the runs either side, 10 and 20.971, with their series peaks to 1e-5, and its design
  peak is the 20.971 run's, since that is its own area. The dock's table, `study.json` and `design_points.csv` agree.
- **[Certain] Interpolation against an exact-area run: from the 10 and 30 km2 runs, ln Q on ln A, Bidah 03 at 20.971 km2
  reads 616.400 m3/s against 618.793 from the run at its own area, -0.39 %.** One point, one storm, a factor-3 bracket;
  the default bracket is at most a factor 2.
- [Certain] The composite map, on a constant 20.971 km2 accumulation raster, equals the 20.971 run's depth map exactly.
- The design line `axis` has no area field value: no row, and the dock says so.

**Study C**, the same with 10, 30 and 90 km2, stopped 11 h into its second run: the engine's `done` is `stopped`, code 6;
the second run stopped too; the third never started; no `design_points.csv`, no stop file left; Start study is back.

**Study B**, a basin generated from the DEM (threshold 2 km2: 8 subbasins, 4 reaches, 5 junctions), S2 switched to
rain-on-grid so a hand-back is built at junction Bidah 03, a design storm of 100 mm in 2 h with the HMS pattern and ARF
table, 4 h, bracketing storm areas, **CPU only**:

- [Certain] The job says `backend: cpu`; both runs' `start` events say `cpu`; the plain run after it too, and its job has
  no `arf` block.
- [Certain] Storm areas 19.3071 and 22.3541 km2: from the smallest to the largest of the line (20.971) and the three fed
  elements (Bidah 03 and R1 at 19.3071, J1 at 22.3541); 2 runs for 17 rows.
- 13 elements with no 2D water above them read their own exact lumped reruns; 3 fed elements read the 2D runs, their
  peaks equal to their network series in those runs. None was on the grid. Table in `design_points_study_b.csv`.
- **[Certain] What the shortcut saves: had these 13 elements read the 2D runs, they would sit below the smallest bin and
  take its peak, -0.24 % (J2, 17.75 km2) to -3.16 % (S5, 0.25 km2) against their exact reruns.**

## Found on the way, for him

1. **A design line at a hand-back junction reads only the water on the grid.** Study B: the line at the dam reads
   42.6 m3/s, the junction Bidah 03 308.5, because on a generated basin the lumped water above a hand-back junction stays
   in the network and only what is on the grid crosses the line, S2's rain and the ground no subbasin covers [Likely,
   from the routes the run reported; not traced cell by cell]. The table
   carries both rows; nothing in the dock warns about the line.
2. **The composite needs an accumulation raster finer than the cells.** The existing code takes the largest pixel whose
   centre falls in a cell, and a cell with none reads the smallest run, without a word. My first check used 100 m pixels
   on 40 m cells and failed by 0.08 m for that reason [Certain, from the code and the rerun at 10 m].
3. The generated basin gives the junction Bidah 03 19.31 km2, against 20.971 on the validation job's dam line; the study
   takes each as given.
4. On the Bidah domain the runs pond 6 to 12 m against the western edge, as W27 already found; the warning is in every
   run of the log.

## Not tested

- A study re-attached after QGIS restarts (not built), a study on a mesh, a gridded or DSS storm (refused: no ARF), the
  HMS storm on a hybrid HMS job with hand-backs, an element `on the grid` in the real dock (only in the engine test).
- The composite map on a real flow accumulation raster, and loaded maps looked at by a person.
- A study at Block 2 scale (W1's took 7.2 h): only that Stop works mid-run, and the `run` event lists the runs left.
- The GPU only choice on a PC without a GPU.

## How to rerun

```
powershell -File tests\dock\run_check.ps1 "<full Windows path>\W37 dock backend and ARF\dock_backend_arf.py" <throwaway folder> -Copy "<full Windows path>\W37 dock backend and ARF"
```

In a worktree, `.venv` must be a junction to the main checkout's, as the harness looks for the engine there. Tests:
`.venv\Scripts\python -m pytest tests\plugin tests\engine\test_arf_cli.py tests\engine\test_arf_network.py`.

## Files

`dock_backend_arf.py` the scenario; `log_dock_backend_arf.txt` its log; `design_points_study_a.csv` and
`design_points_study_b.csv` the two tables as written; `widget_study_before.png`, `widget_study_a_table.png`,
`widget_study_b_table.png` the section as drawn.
