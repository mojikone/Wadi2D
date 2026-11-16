# W95 rain sources and split ARF

**Live.** Branch `feature/rain-arf-v2`, off `main` at `69473b1` (v0.4.0); not merged, nothing pushed. Engine only: the
dock's Hydrology and Data tables sections are another worker's, later. Requirements: `W94 dock redesign/README.md`
(his words of 2026-11-15, Hydrology: ARF and Rainfall; Data tables).

## What was built

**1. The area reduction split by part, `storm.area_reduction`.** Two parts, `lumped` (rain on the lumped subbasins)
and `grid` (rain on the 2D cells); a part left out is not reduced. Each part takes one of three forms:

| Form | Fields | Lumped part | 2D part |
|---|---|---|---|
| `coefficient` | `coefficient` (0 < c <= 1) | every lumped subbasin times c | every cell times c |
| `area` | `curve` (a stored name) or `table`, and `area_km2` | the curve's factor at that area | the same |
| `curve` | `curve` or `table` | per element: in a lumped-only run every element at its own drainage area (W88's `arf_by_element`, to 1e-12 of it); in a run with a 2D part each lumped subbasin at its `storm_area_km2` (`38dc74e`), **else at its own area** | only inside a depth-area study, at each run's storm area |

Refused in words: `area_reduction` beside `storm.arf`, `storm.storm_area_km2` or `storm.arf_factor`; on a hyetograph,
gauges or no storm; a 2D curve in a single run ("the 2D cells of a single run have no area of their own"); a study
whose 2D part is a coefficient, a fixed area or nothing ("every run would be the same run"); a study beside subbasins
with their own areas; `hydrology.arf_by_element` or a subbasin's `storm_area_km2` unless the lumped part is a curve;
a lumped curve in a lumped-only run beside subbasins with their own areas ("choose one"); every malformed part (a
coefficient with an area, an area with no curve, a curve with an area, neither part).

A study (`wadi2d arf`) turns every `curve` part into `area` at each run's storm area (`split_arf.at_study_area`), so a
lumped curve in a study behaves as the old storm area did; a fixed lumped part stays fixed across the runs. The run's
record: one `area_reduction` output event per part (`part`, `form`, `factor`, `storm_area_km2`, `curve`,
`arf_table_type`) and a warning line in words; `arf_tags` gives `arf_lumped` and `arf_grid` to the outputs.

My call, his to overturn: **a lumped curve in a hybrid run with no subbasin area reads each subbasin at its own area**
(the HMS depth-area answer at the subbasin's outlet: less reduction than at a dam's area, so the safe side). The
alternative was to refuse until every subbasin has an area.

**2. Rain sources, one shape.** Two new kinds beside the old ones (which stay, to the digit):

- `kind: depth`: `depth_mm` over `duration_min`, spread by `storm.pattern`;
- `kind: depth_grid`: the raster `depth_grid` (mm per cell, 2D cells read the pixel under their centre, each lumped
  subbasin the mean of the pixel centres in its polygon, HMS's `Uniform Depth: No`), spread by `storm.pattern`. It is
  now a source of its own and takes the polygons of any basin (an HMS basin with a polygons file, `basin.json`), where
  the old depth-grid path needs `hydrology.hms_sqlite`;
- `kind: gridded` (DSS, NetCDF, GeoTIFF stack) as before, now with `area_reduction` too.

`storm.pattern`: `uniform` (the constant-rate storm, to the digit of the old `uniform`), `scs` with `scs_type` I, IA,
II or III (needs `duration_min` 1440), or `table` by name from the store or given as `values`. A pattern table holds
`time` and `depth`, `time_units` percent or fraction of the duration (ending at 100 or 1) or hours or minutes (ending
at the duration), `form` cumulative (any unit, read as a share of the last; from 0, 0) or incremental (each period's
share, read as a share of the sum). A table pattern runs as the old hypothetical storm to the digit. The HMS met file
still imports to a `hypothetical` storm (`wadi2d/engine/hms_import.py`, untouched).

[Likely] The SCS curves are the abbreviated TR-20 tables at 23 times written from the published table as I know it;
I could not check them here against NEH 630 chapter 4 (its tables are images in the copy reached) or HEC-HMS's SCS
Storm. Check before a design number rests on them.

**3. The table store, `data_tables`.** Named `patterns` and `arf_curves` in the job, or in a JSON file beside it
(`data_tables.file`, relative to the job, keys `patterns` and `arf_curves` only). A storm refers to them by name
(`storm.pattern.table`, `storm.area_reduction.<part>.curve`); every name is filled in when the job is validated
(`config.rain.resolve_tables`, a before-validator of `RunConfig`), so the run, `config.resolved.json` and the hash hold
the numbers. Refused in words: a name the store does not hold (with the names it does hold), a name and other numbers
beside it, a name in the job and the file with other numbers, other keys in the file.

## Old jobs

The hash drops `storm.pattern` and `storm.area_reduction` when None, the whole `data_tables`, and the names of stored
tables: an old job keeps its hash, a store of tables nothing names changes no hash, a named table hashes as the same
numbers given inline. `config.resolved.json` of an old job gains `"pattern": null`, `"area_reduction": null` and an
empty `data_tables`. The old kinds, `storm.arf`, `storm.arf_factor`, `storm_area_km2` and `arf_by_element` keep their
paths: a job without `area_reduction` reads the same reduction from `split_arf.part_reduction` for both parts as before.

## Schema classes touched

`wadi2d/config/schema.py`: `Storm` (two kinds, `pattern`, `area_reduction`, the `_sources` validator), `RunConfig`
(`data_tables`, the `_stored_tables` before-validator, `_by_element` and `_own_storm_areas` accept a lumped curve).
`ArfTableConfig` moved to the new `wadi2d/config/rain.py` (still importable from `schema`), which also holds
`PatternTable`, `StormPattern`, `ArfPart`, `AreaReduction`, `DataTables`. No other section of the schema changed.

Engine: `wadi2d/storm/patterns.py` and `wadi2d/storm/split_arf.py` (new), `forcing.build_storm` and `arf_table`,
`run._lumped_rain`, `_network_rain`, `lumped_rain_at`, `job_hash`, `load_job`, `arf_tags`, `_run`'s refusal and
records, `engine/lumped_run.py` (a lumped curve is by element), `arf.py` (the study's checks and per-run storm),
`storm/grid_depth.subbasin_means`.

## Tests (CPU, one file at a time under the 10 GB cap)

- `tests/storm/test_rain_sources.py`, 27 of 27: depth with no pattern and with a table equal to the old uniform and
  hypothetical storms to the digit; four spellings of one pattern each hold the whole depth to 1e-12; the four SCS
  types monotone, whole, read exactly at their 23 times, Type II's burst at 11:45 to 12:00, refused off 24 h; the depth
  grid as a unit storm; ten refusals of sources and six of pattern tables; the store by name equal to inline, read back
  from the dump, the three refusals, the sidecar file through `load_job` and its two refusals; old hashes.
- `tests/engine/test_rain_sources_split_arf.py`, 10 of 10: every 2D cell takes the intended depth to 1e-12 (depth,
  depth with a pattern and coefficient, SCS with a fixed area, the depth grid pixel by pixel with its pattern), the
  volume to 1e-9 in float64 and to 1e-6 as the solver's float32 source carries it; a gridded series times the 2D
  part's factor cell by cell; each lumped subbasin's depth (depth, split, the depth grid's polygon mean) to 1e-12; a
  lumped curve at the subbasin's own area and at its `storm_area_km2`; **the hybrid run: 2D rain 0.75 of the
  unreduced run (the curve at 505 km2), lumped inflow 0.6 (the coefficient), each to 1e-6**, events and words; a lumped
  curve in a lumped-only run equal to `arf_by_element` on every element to 1e-12; the refusals.
- Existing files rerun one at a time, all passing unchanged: `tests/storm/*` (arf_steps 11, gauges 29, rain_dss 37,
  rain_files 18, rain_frames 39, storm 13), `tests/engine/test_forcing.py` 12, `test_rain_run.py` 15,
  `test_given_factor.py` 8, `test_subbasin_storm_area.py` 5, `test_lumped_network.py` 8, `test_arf_cli.py` 14,
  `test_arf_network.py` 8, `test_rain_preview.py` 7, `test_review.py` 48, `test_mesh_paths.py` 21, `tests/hydrology/test_network.py` 18,
  `tests/plugin/test_storm_rows.py` 29, `tests/plugin/test_contract.py` 97 after the frozen JSON schema sample
  (`tests/plugin/schema_sample.json`) was rewritten from the engine, as every schema change does.

## Not done

- The dock (another worker); the plugin's JSON-schema forms will show the new fields.
- `wadi2d rain-preview` reads the split through the same pieces but has no test of its own for it.
- SCS curves against HMS's SCS Storm; the full suite.
