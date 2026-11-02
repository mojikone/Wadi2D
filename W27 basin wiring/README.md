# W27 basin wiring (D6b)

[PRESERVE-CHECK]

KEEP, untouched in behaviour, numbers to the last digit for any job without `hydrology.basin_json`:
- The solver kernels on both backends, the steppers, the mesh, the tables. No kernel is edited.
- An HMS job: `_network`, `_check_routes`, the hand-back of `W25`, the base lumped run, `Forcing`, the balance, checkpoints.
  `plan_routes` keeps its cuts for an HMS basin; the new switch is off there.
- The dock's HMS route and plain rain-on-grid route: the same widgets, the same values, the same job. `merge_hms` untouched.
- `basin.json` as `W24` wrote it reads as before: a file without `routes` or `settings.lag_method` is the NRCS one.

CHANGE:
- Job contract: `hydrology.basin_json`, `hydrology.subbasins[].parameters` (an override per generated subbasin), `basin` (the
  `BasinSettings` of `W24`, now a part of the job, with `lag_method`, `handback_span` and `handback_min_cells`). `job_hash` leaves
  `basin` out: the run reads `basin.json`, whose bytes it hashes.
- The lag of a generated subbasin by `basin.lag_method`: `nrcs` (default) or `hms_kirpich`, 0.474 x Kirpich on the longest path
  and the 10-85 slope, the rule `W24` found under HMS's lags. Applied where the lag is derived (`refresh`), so `basin.json`
  records which method made its lags. `wadi2d basin` starts from the job's `basin` part; `--settings` and the flags override.
- `basin.json` gains a derived top-level `routes` list (the junction routes), written by `assemble`; readers that do not know it ignore it.
- New `wadi2d/basin/job.py`: a job on a generated basin resolves, before anything else, into the same contract an HMS job uses:
  every subbasin with its mode (incomplete ones to `2d`, with a warning naming what is missing), one `Inflow` at every junction
  whose route is `none` (its water enters the grid there), one `Handback` at every junction with a reach below that 2D water can
  reach, and the junction-to-junction links cut in the lumped engine. The resolved job is what `config.resolved.json` holds.
- `plan_routes` gains `cut` (links decided elsewhere) and `cut_entries` (False for a generated basin: the lumped water above a
  hand-back's junction stays in the network, because the routes already say what is on the grid).
- `_network` takes the lumped network from `basin.json` when the job names one; `_lumped_rain` no longer needs an HMS file; a
  depth grid on a generated basin is refused in words (not built).
- New `wadi2d/engine/rain_once.py`: a run stops, with the cell count and the names, when two lumped polygons share a cell or a
  2D subbasin's cells lie under a lumped polygon. Runs for every job with polygons; an HMS partition passes.
- New `wadi2d/engine/network_series.py`: the lumped network's inflow and outflow of every element go to `results.h5` and
  `series/network_<element>.csv` for every job with a lumped network, HMS or generated. New files beside old ones; no old
  number moves.
- `progress.jsonl` gains one `basin` event per run on a generated basin: every junction's route, what enters the grid where,
  the hand-back lines, the incomplete elements.
- `map_notes.water_note`: water from the hills is `inflow_m3 - reentry_m3`, as `W25` asked.
- Plugin: section 3 gains "Generate the basin from the DEM" (`sections/basin.py`, rows in `sections/basin_rows.py`), the
  junctions table, the hand-back line rows and the transmission loss row; `hydrology.py`, `job_builder.py`, `dock.py` and
  `protocol.py` get the smallest edits that hold them; `basin_layers.py` and three styles load `basin.gpkg`.

FILES:
- New: `wadi2d/basin/job.py`, `wadi2d/basin/geometry.py`, `wadi2d/engine/rain_once.py`, `wadi2d/engine/network_series.py`,
  `plugin/wadi2d_qgis/sections/basin.py`, `plugin/wadi2d_qgis/sections/basin_rows.py`, `plugin/wadi2d_qgis/basin_layers.py`,
  `tests/basin/test_job.py`, `tests/engine/test_basin_run.py`, `tests/engine/test_rain_once.py`, `tests/plugin/test_basin_rows.py`,
  this folder.
- Edited: `wadi2d/config/schema.py`, `wadi2d/run.py`, `wadi2d/forcing.py` (`load_polygons`, three lines), `wadi2d/basin/contract.py`,
  `wadi2d/basin/parameters.py`, `wadi2d/basin/build.py`, `wadi2d/engine/cli.py` (`_basin`), `wadi2d/hydrology/live_network.py`
  (`plan_routes` signature), `plugin/wadi2d_qgis/sections/hydrology.py`, `plugin/wadi2d_qgis/job_builder.py`,
  `plugin/wadi2d_qgis/dock.py`, `plugin/wadi2d_qgis/protocol.py`, `plugin/wadi2d_qgis/style.py`, `plugin/wadi2d_qgis/map_notes.py`,
  `tests/plugin/schema_sample.json`, `tests/plugin/test_contract.py`, `tests/basin/test_model.py` (one test flips),
  `tests/plugin/test_map_notes.py`.

[BROAD] by the rule: several modules, one existing function's signature extended. The owner said not to stop, so the proof is
`old_jobs_check.py` below, as `W23` and `W25` did it.

## State

Being built. Sections below are filled as each part lands.
