# W101 dock redesign part 2

**Status (2026-11-16): branch `feature/dock-redesign-2` off `feature/fast-products` (`75be51e`); not merged, nothing
pushed. Built item by item under a usage ceiling (96 % of his 99 % when his item 7 was added): item 1 and item 7 (the
map controls, added mid-task) are built and tested; items 2 to 6 are not started.** Requirements: `W94 dock
redesign/README.md`; part 1's record: `W99 dock redesign part 1/README.md`.

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

## Tests through the real dock

| Scenario | What it proves | Passed |
|---|---|---|
| `dock_rain.py` | item 1: the sections in their places; Data tables (add, the next free name, a refused table Missing in words, rename, remove, both charts); six sources, the Steady rain's mm/h giving its job; SCS sets 24 h and refuses 6 h; a pattern by name carried into the job and filled in by the engine; a depth grid; the parts by model type; one area for both parts = the old form, parts that differ = `area_reduction`; the study's single-run area; **a real run on Bidah of a depth with a pattern of Data tables and the 2D part's own reduction, the engine's factor equal to the dock's**; saved and brought back to the same job; a format 2 model's steady rain and design storm moved, in words | 54 of 54 |

## Found on the way

1. The generated basin's reaches take their Manning n from Terrain's Manning (`wadi2d/basin/elements.py`
   `_manning`, read at Generate basin): a Lumped model that hides Manning in Terrain (his item 7, point 5) leaves the
   generated reaches on a value nobody sees. A reach-n field in the basin box would close it; not built.
2. `PairTable.set_rows` wrote six significant digits (`:g`), so a table of seven digits came back rounded from a saved
   model; now ten.
3. Older dock scenarios that drive the old Storm widgets (`W20`, `W37`, `W39`, `W53`, `W54`, `W77 dock_storm`) no longer
   find them: the sources changed by design. Not rewritten.

## Not done

Items 2 to 6 of the brief (losses and roughness, boundaries, the Mesh section, the domain from an outline, the results
view) are not started: the usage ceiling. What each needs from the engine is already there (W95 to W98); the part 1
record's "What the next parts need" still holds, and the new sections show the pattern (`sections/tables.py` for a
store shared by sections, `sections/reduction.py` for a section shown by model type, `table_rows.py` and
`reduction_rows.py` for the plain rules beside a `pytest` file).
