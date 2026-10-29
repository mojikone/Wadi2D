# Architecture seed for the design panels (2026-10-29)

Input to the design workflow, not a decision. It follows from the project CLAUDE.md (version-1 scope, decision 17; engineering rules;
decisions 2, 3, 4, 10, 16) and the toolchain gate (`toolchain_check.md`): CUDA C++ kernels compiled at run time by NVRTC through
CuPy, a CPU twin in Numba, Python orchestration, the engine as a separate process, a QGIS plugin as the version-1 UI. The panels
critique it, propose alternatives and fix the details; the design note records the outcome.

## 1. Repository layout (one package, kernels inside it so a wheel ships them)

```
pyproject.toml                 package "wadi2d"; extras: gpu (cupy-cuda12x + nvidia wheels), dev (pytest, ruff, mypy), qgis
LICENSE                        GPL-3.0-or-later
wadi2d/
  __init__.py                  __version__
  config/                      THE single source of truth for every parameter (engineering rule 2)
    schema.py                  pydantic v2 models: RunConfig and its parts, defaults, units, bounds, docs per field
    constants.py               physical constants only (g = 9.80665, rho); nothing tunable lives here
    resolve.py                 load job -> validate -> fill defaults -> resolved config; JSON Schema export
  grid/                        UniformGrid (origin, dx, nx, ny, CRS), tiles (32 x 32), domain mask, active-tile list, index maps
  terrain/                     DEM access (rasterio windows over the 27 GB raster), terrain objects (crest line, spillway, wall, burn line)
  tables/                      sub-grid table builder: cell volume-level, face width/area/conveyance-level, crest rasterisation, length factor
  solver/
    backend.py                 pick gpu (CuPy present and a device) or cpu; same API
    layout.py                  array names, dtypes, SoA layout, halo convention; shared by both backends and by the HDF5 writer
    gpu/loader.py              NVRTC compile of kernels/*.cu with the resolved numerics baked in as a generated header; cache
    gpu/kernels/*.cu           reconstruct_flux_update, friction, sources (rain, inflow, losses), boundaries, cfl_reduce, structures
    cpu/*.py                   Numba twins, one function per kernel, same arguments and the same arithmetic order where it matters
    stepper.py                 the time loop: dt, substeps, boundary and source application, output triggers, live-view triggers
  hydrology/                   lumped engine: cn.py, scs_uh.py, clark.py, muskingum_cunge.py, baseflow.py, network.py (topological order)
  hms/                         readers: basin.py, met.py, control.py, pdata.py, gage.py, run.py, dss.py (hecdss); one typed object model
  storm/                       frequency storm builder (point depths, pattern, position), ARF table, uniform hyetograph, GeoTIFF stack
  rain/                        rain-on-grid: rainfall onto cells, CN losses on cells, subbasin masks, hydrograph injection cells
  arf/                         storm-area set, one run per area, design-point lookup by drainage area, composite map
  io/                          HDF5 grid/tables/results files, GeoTIFF maps, CSV hydrographs, run folder, progress JSON lines
  engine/                      CLI (wadi2d run job.json; wadi2d build-grid; wadi2d tables; wadi2d hms-import), process protocol
  validation/                  analytic cases and comparators (lake at rest, Thacker, Stoker/Ritter, MacDonald), EA tests, metrics
tests/                         unit per module; analytic; cpu-gpu parity (skipped without a GPU); HMS replication on Block 2 (skipped
                               when the data folder is absent); marks: slow, gpu, data
plugin/wadi2d_qgis/            QGIS plugin: dock widget, QgsTask subprocess runner, live raster refresh, job builder from layers
docs/                          mkdocs: tutorial, method note, file formats, licence audit
W1 research and design note/   this folder (research, design note, benchmarks)
```

Registries (engineering rule 4): `hydrology.losses`, `hydrology.transforms`, `hydrology.routing`, `storm.sources`, `terrain.objects`,
`io.outputs`, `solver.backends`. Each is a dict from a name used in the config to a class with one interface; adding a method is a new
file plus a registration line.

## 2. Configuration (engineering rule 2)

One `RunConfig` (pydantic) with parts: `project` (name, CRS, units), `grid` (polygon or extent, dx, tile size), `terrain` (DEM path,
objects), `tables` (level step, maximum rows, sampling), `numerics` (CFL, limiter, wet depth, dry depth, velocity cap, friction
scheme, time integrator, max dt, min dt), `physics` (g, Manning source: raster, polygon layer, constant), `hydrology` (subbasins:
lumped or 2D, methods and parameters, or `hms_project` to import), `storm` (type and parameters, storm areas for ARF, ARF table),
`boundaries` (outflow lines and type), `outputs` (what, when, where), `run` (duration, output step, live-view step, backend,
precision). Every field has a default, a unit in its description and bounds. `wadi2d schema` exports JSON Schema for the plugin and
the docs. The resolved configuration is written to `run/config.resolved.json` before the first step; kernels receive numerics as
arguments or a generated `numerics.h`, never as literals in `.cu` files.

## 3. Data contracts (engineering rule 3; all versioned with a `format_version` attribute)

| File | Producer -> consumer | Content |
|---|---|---|
| `job.json` | plugin or user -> engine | RunConfig (unresolved) |
| `grid.h5` | `wadi2d build-grid` -> solver, plugin | grid definition, CRS, domain mask, tile list, bed statistics, per-cell volume table, per-face width and conveyance tables, crest faces with crest elevation and length factor, Manning per cell or face, inflow cells per subbasin, boundary faces |
| `forcing.h5` | storm and hydrology -> solver | rainfall per cell group and time, hydrographs per injection point, boundary stages |
| `results.h5` | solver -> plugin, post-processing | per output time: depth and velocity (float32, chunked by tile); maxima; hydrographs at points; mass balance log |
| `maps/*.tif` | solver -> QGIS | max depth, max velocity, hazard, arrival time, and the live-view depth raster |
| `progress.jsonl` | engine -> plugin | one JSON object per event: step, time, dt, wet cells, mass error, output written, warnings |
| `config.resolved.json` | engine -> everyone | the exact configuration the run used |

## 4. Engine process protocol

`wadi2d run job.json --out <folder>`: validates, builds or loads `grid.h5`, builds `forcing.h5`, runs, writes outputs; prints
progress as JSON lines on stdout and to `progress.jsonl`; exit code 0 on success; `--dry-run` validates and estimates cells, memory
and time; `SIGINT` or a `stop` file in the folder stops cleanly with outputs flushed. The plugin never imports the engine; a job
runner on another PC later speaks the same protocol (decision 16).

## 5. Solver data layout and kernels (for the panel to fix)

State per cell, float32, structure of arrays: depth `h`, unit discharges `qx`, `qy`; derived per step: free surface where needed.
Per cell constants: bed minimum `zmin`, volume table (level breakpoints and volumes, fixed row count, packed), Manning `n`, mask.
Per face (x faces and y faces as separate arrays): width table and conveyance table (fixed rows), crest elevation (or minus
infinity), crest length factor, wall flag. Tiles of 32 x 32 cells; arrays stored tile-major so a tile's cells are contiguous; an
active-tile list rebuilt every K steps from a wet flag per tile with a one-tile margin; kernels launch over active tiles only.

Kernels per step (names, not final): `cfl_reduce` (per-tile minimum, then a second pass), `reconstruct_flux_update` (fused: MUSCL
on free surface and discharge, hydrostatic or table-based reconstruction, HLLC in x and y, source terms, provisional update),
`friction_implicit`, `sources` (rain, losses, injected inflow), `boundaries`, `structures` (crest and spillway faces), `maxima`,
`liveview_downsample`. Time integration: MUSCL-Hancock or SSP-RK2 (panel decides from the research and the benchmark).

## 6. Hydrology and rain-on-grid

A `Basin` object model read from HMS files or built in the plugin: subbasins, reaches, junctions, sinks, with methods from the
registries. The lumped engine solves in topological order on the simulation step, producing hydrographs; a lumped subbasin's
hydrograph enters the 2D domain at its injection cells (the delineated outlet or a user point, spread over the sub-grid channel
width of the receiving cells); its polygon masks rainfall on the 2D cells beneath it. 2D subbasins receive rainfall per cell with CN
losses per cell. Mode (a) runs no 2D at all; mode (b) both; mode (c) all 2D.

## 7. ARF orchestration

`wadi2d arf job.json`: a set of storm areas (default 6-8 log-spaced between the smallest and largest design-point drainage areas),
one run per area with rain scaled by the ARF table, outputs per area, a design-point table that reads each point's run by its
drainage area (from the HMS basin file or a user value), and an optional composite map from an accumulation grid supplied as a
raster (produced by QGIS processing). Runs are independent jobs, which is what a later job runner distributes.

## 8. Testing layers (engineering rule 5)

Unit tests per module; table builder against HEC-RAS geometry tables (same square cells, same terrain); hydrology methods against
HMS numbers from Block 2 DSS results; analytic cases as regression tests for the solver on both backends; CPU-GPU parity to a
tolerance; an end-to-end Block 2 job; benchmarks recorded in W1. CI runs the CPU tests on Windows and Linux.

## 9. Build order and "done" per stage

1. Skeleton, config schema, data contracts, run folder, CLI stub: `wadi2d schema` and `wadi2d run --dry-run` work; tests pass.
2. Table builder from a DEM window with crest lines: tables match a hand computation and the RAS oracle on a small case.
3. Solver CPU twin and GPU kernels on a plain bed, then with tables: lake at rest exact, Thacker and dam-break within tolerance,
   parity within float32 noise; benchmark recorded.
4. HMS readers and lumped engine: Block 2 mode (a) peaks within a few per cent of HMS at every junction.
5. Rain-on-grid, masks, injection, boundaries, structures: a Block 2 wadi runs in mode (b) and looks right in QGIS.
6. ARF orchestration and design-point table; composite map.
7. QGIS plugin: build job from layers, run, watch, load results.
8. Documentation, licence audit, release.
