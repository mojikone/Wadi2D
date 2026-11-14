# W65 rain source

**Live.** Branch `feature/rain-source`, off `feature/fast-products` at `f6d59c0`; not merged, nothing pushed.

His words, 2026-11-14: rain gauges exist (W54), so a received hyetograph applies directly; "manage it more
professionally, as adding all options would be confusing": one Rain source choice, only that choice's fields, and a
preview of each subbasin's depth and hyetograph before the run. Spec: `W58 HMS elements and dam workbook/README.md`
section 8.

## What was built

**The Storm section (`plugin/wadi2d_qgis/sections/storm.py`): one Rain source combo, stacked pages.**

| Rain source | Fields shown | Job written (unchanged meaning) |
|---|---|---|
| As in the HMS project (only with one loaded) | a note | the HMS import's storm, as before |
| Design storm with area reduction | point depth, duration, pattern, then the area reduction block | `hypothetical`, as before |
| Gridded file with area reduction | file or folder, series, units, period, stamp, run start, the rain file's summary, then the area reduction block | `gridded`, as before |
| Rain gauges | what the Gauges section lists (names, spreading method) and a button that opens it | `gauges`, as before |
| Single hyetograph | Constant rain (mm/h, hours) or A table of periods | `uniform` or `hyetograph`, as Steady rain and Hyetograph table wrote |

Steady rain and the hyetograph table, two choices for one thing, are now one source with two forms. The default with
no HMS project stays constant rain, so every existing check that sets the rain still reads the same job.

**The area reduction is one block**, shown only under a design storm and a gridded file: None; At one storm area (area
and table; on a grid with an HMS project an empty table takes the project's); By the depth-area study, which shows the
study's storm areas read only from section 9 and keeps the area of a single Run. A reduction chosen with no table is
refused before the run ("Fill the area reduction table, or choose no area reduction."); before, an empty table meant
no reduction without a word, which is now the None choice.

**Preview rain**, a button under the section: the dock writes the job a run would write (through the HMS import when
there is one) in a scratch folder, and `wadi2d rain-preview` answers with each lumped subbasin's and the 2D area's
area, depth after the reduction, peak intensity and hyetograph on the lumped engine's step. The dock shows a table and
a small bar chart of the row picked. The engine computes everything (`wadi2d/engine/rain_preview.py`): the storm the
run builds, the rain the lumped network takes (`run._lumped_rain`), and the same binding for the 2D area, which is the
domain less the lumped subbasins' polygons. The 2D depth is an area-weighted mean over the rain pixels; the cells read
the pixel under their centre, so on a coarse rain grid the two can part by a fraction of a per cent at the edge.

Files: `wadi2d/engine/rain_preview.py`, `wadi2d/engine/cli.py` (`rain-preview`), `plugin/wadi2d_qgis/sections/storm.py`,
`rain_chart.py`, `rain_query.py` (the section's links to the dock, the Gauges and Study sections and the engine),
`storm_rows.py`, `gauge_rows.py` (`gauges_text`), `study_rows.py` (two refusal texts name the new choices), `dock.py`
(two lines).

## Tests

- `tests/engine/test_rain_preview.py`, 3 of 3: a gridded storm with an area reduction on a closed box, the preview's 2D
  depth times the area equal to the run's rain volume to 1e-5 (the engine's own forcing); an HMS hybrid where the
  lumped subbasin's hyetograph equals the network's own increments to 1e-4 mm, the 2D subbasin counted in the 2D area,
  not as a lumped row; the command writes its file and refuses a job without rain.
- `tests/plugin/test_storm_rows.py`, 5 new: per kind, the job of the new values equals the job of the old section's
  values; the refusal; the preview's line; the gauges summary.
- `tests/plugin/smoke_qgis.py` on QGIS 3.44.8, the real dock:
  - with the fake engine, for each source the job the new section writes equals what the old one wrote for the same
    choice (constant rain, table, design storm without and with a reduction, by the study, observed grid, grid of point
    depths, gauges); the reduction refused without its table; the gauges button opens the Gauges section;
  - with the real engine, Preview rain: 100 mm/h for 0.2 h on the 4 km2 plane reads 20 mm at 100 mm/h; a design storm
    of 80 mm at 505 km2 on a table 1.0 to 0.5 reads 60 mm, factor 0.7500; a reduction with no table refused in words.
  - The real-engine smoke now starts this checkout's engine through a launcher file, where it ran `-m wadi2d.engine.cli`
    from the venv's install: in a worktree that was the main checkout's engine.
- `tests/plugin` whole: 528 of 528. CPU only. The full suite was not run.

## Not done

- **The gauge table was not moved into the Storm section** (spec section 8 says moved, 7b keeping only flow gauges).
  The Gauges section holds rain, flow and level gauges in one table with one layer and one set of reading rules;
  splitting it is a change of the W54 section and its dock checks. The Storm page shows the rain gauges it lists and
  opens that section. His call whether to split it.
- No temporary map layer colouring the subbasins by depth, and no total-depth raster on gridded and gauge rain.
- The HMS page has no read-only summary of its storm and no "Copy into the form"; Preview rain gives its numbers.
- No "fill the table with constant rain" button: constant rain is its own form, so its job stays `uniform`.
- Not driven through the real dock with a person's clicks or a dock scenario on Block 2; the W20 and W54 dock scenarios
  address the old widgets (`kind` data `uniform`, `grid_arf_on`) and are records of their iterations, not rerun.
