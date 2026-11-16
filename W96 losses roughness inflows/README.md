# W96 losses roughness inflows

Status (2026-11-15): built in the engine on `feature/losses-roughness` (off `main` = v0.4.0), not merged, nothing pushed.
Engine only: the dock comes with the W94 redesign. Requirements: `W94 dock redesign/README.md` (his words of 2026-11-15),
items Infiltration, Manning, external inflows, initial conditions and model types.

## What was built

Every new part is optional. A job that sets none of them runs, hashes and caches as before: the job hash of all 441
job files in the repository is unchanged, and the grid key, strip key and job hash of three synthetic jobs (plain, a
flow line, initial water with CN and Manning) are identical to v0.4.0's, computed by both code versions on one DEM.

| Item | Job field | What it does |
|---|---|---|
| Infiltration | `hydrology.cn_override` (`CurveOverride`) | `by: land_use` (a raster of class codes and a table of CN per class), `by: range` (every CN from `low` to `high`, both included, becomes one value; ranges may not overlap), `by: subbasin` (a CN by name). Applied to the rain-on-grid cells (after the CN grid, the job's and the subbasins' CN) and to the lumped subbasins alike: a lumped subbasin takes the mean of its class CN over the land-use pixels whose centres lie in its polygon (HMS's composite CN), its own CN through the range table, or its named CN. A class found and not listed stops the run, naming every code; a name that is no subbasin and has no polygon is refused; a lumped subbasin without a polygon is refused for `land_use`. The CN grid (`terrain.cn_raster`) stays as it was. |
| Manning | `terrain.roughness` (`Roughness`) | `form: uniform` (one `n`), `split` (`n` for the square cells, `n_aligned` for the strips' aligned cells; refused without `strips.enabled`), `grid` (a raster of n, read as `terrain.manning_raster` always was), `land_use` (a raster of class codes and a table of n per class, a missing class refused by code). Raster holes take `roughness.n`, else `terrain.manning`. With `roughness` set, `terrain.manning_raster` is refused (one source); without it both old fields hold. The tables' cache key carries the roughness and its raster's content only when it is set. |
| Inflow lines | `boundaries[].flow.step_s` | HEC-RAS's Flow Hydrograph entry: an interval and a list of flows, `flows[k]` at `k x step_s` from the run's start, in place of `times_s` (both refused together; two flows at least). `FlowHydrograph.table()` writes the times out, for the run and for the dock's chart. The energy slope (`slope`, `distribution: normal_depth`, W61), CSV and DSS records are unchanged. |
| Initial conditions | `initial_points` (`InitialPoint`: name, x, y, level) | The cells under the level joined to the point's cell through faces open at it start full, found as a dam's pool is (W34). A point behind a dam fills the same pool, to the cell, as the dam's own start at that level; an open boundary does not stop the fill (a point in the sea). Refused in words on dry ground (the cell's ground and the level named), off the domain, on a strip's aligned cell, on the quadtree. |
| Model type | `run.model_type` (`2d`, `lumped`, `hybrid_lumped`, `hybrid_2d`) | Sets what it implies where the job is silent (`lumped` sets `run.lumped_only`, `hybrid_lumped` sets `grid.exclude_lumped`) and is refused in words where the job does not fit: a lumped part (generated basin, lumped subbasins, inflows from elements, hand-backs) in a 2D model, catchments left out in a 2D or Hybrid 2D model, no network for a lumped model, no DEM or domain for a grid model, no lumped part for a hybrid one. A job without it runs as before; `wadi2d.config.model_type.model_type(cfg)` gives its type, inferred for old jobs. The type is not part of the job hash. |

## Schema classes touched

- New, in `wadi2d/config/land.py`: `Roughness`, `ManningClass`, `CurveOverride`, `CurveClass`, `CurveRange`, `SubbasinCurve`; the constants of the forms and of the four model types.
- New, in `wadi2d/config/schema.py`: `InitialPoint`.
- Changed in `wadi2d/config/schema.py`: `Terrain` (`roughness`, a validator refusing it beside `manning_raster`), `Hydrology` (`cn_override`), `FlowHydrograph` (`step_s`, the source validator, `table()`), `Run` (`model_type`), `RunConfig` (`initial_points`; validators for the type and for `split` without strips).
- Engine: `wadi2d/land.py` (the tables), `wadi2d/config/model_type.py` (inference and checks), `wadi2d/forcing.py` (`manning_grid` takes `aligned`, `curve_numbers` applies the override), `wadi2d/run.py` (hash pops, cache key, paths, the lumped basin's CN, the initial points), `wadi2d/dam_levels.py` (`point_pool_depth`), `wadi2d/engine/inflow_lines.py` (the table). Not touched: the storm schema and forcing of rain (`feature/rain-arf-v2`), the basin generator and the domain (`feature/domain-outline`).

## Tests

`tests/engine/test_land.py` (14), `test_inflow_step.py` (3), `test_initial_points.py` (4), `test_model_type.py` (10);
`tests/plugin/schema_sample.json` regenerated (only additions). CPU suite file by file under a 10 GB cap (W85's
`capped_pytest.py`), `-m "not gpu and not slow"`: see the line below.

Result: 2,742 passed, 10 skipped, the GPU and slow tests deselected; no failure left. Two found on the way: one of
mine (`test_hms_structures` builds the lumped basin from a stand-in job part without `cn_override`; fixed, `876687e`)
and one not (`test_barriers::test_a_burn_wins_where_it_crosses_a_wall`, WhiteboxTools filling nothing once while other
workers loaded the machine; it passes when run again, alone and in its file).

## Not done, and what to know

- The dock: every field above waits for the W94 redesign; nothing in `wadi2d_qgis` changed.
- A generated basin's reach Manning (`basin/elements.py`, the Muskingum-Cunge sections) still reads `terrain.manning` and `terrain.manning_raster`, not `terrain.roughness`: left alone, it is the basin worker's file. A job with `roughness` and a generated basin takes the reach n from `terrain.manning`.
- `by: range` maps a lumped subbasin's own CN as one value; it does not remap the CN grid under the polygon and average again. For a generated basin the two differ where the grid is mixed. [Certain, by construction]
- The breach's strip roughness fallback (`breach/strip.py`) still reads `terrain.manning`.
- Initial points fill square cells only; an aligned cell under the level starts dry and the run says so.
- Inflow from a point (`hydrology.inflows`) has no step form yet; only flow lines.
- No GPU run: the changes are in the tables, the loss classes and the initial depth, which both backends take from one source.
