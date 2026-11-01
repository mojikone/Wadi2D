# Architecture panel, operational angle: Wadi2D version 1 as run every day from QGIS on a 27 GB terrain

Panel proposal, 2026-10-29. One of three architecture proposals; the design note arbitrates. Scope: the project CLAUDE.md (decision 17 and
the Version 1 scope; the engineering rules 1-7; decisions 2, 3, 4, 10, 16, 18), the seed `design_seed_architecture.md` and
`toolchain_check.md`. Angle: the engineer who opens QGIS in the morning, binds a few layers, presses Run, watches, stops, resumes,
exports, and must be able to reproduce any figure from the run folder a year later. Confidence tags as in the project rules:
[Certain] verified today or arithmetic, [Likely] strong inference, [Guessing] estimate.

## 0. Facts verified today that the seed did not have

| Fact | Value | Consequence for the architecture |
|---|---|---|
| The 0.5 m terrain `GGC_2_MERGE_HDSM.tif` [Certain] | 131,136 x 128,660 px, float32, LZW, **tiled 128 x 128, no overviews**, nodata 3.4e38, EPSG:32640, 65.6 x 64.3 km, 27.8 GB on disk (67.5 GB raw) | Windowed reads only, never a copy; QGIS draws it slowly (no overviews) and we cannot add a sidecar to his read-only folder; the grid must be tile-compacted because the bounding box at 10 m is 42 M cells |
| QGIS 3.44.8 Python [Certain] | 3.12.13 with GDAL 3.12.2, numpy 2.4.2, rasterio 1.5.0, numba 0.65.1, pydantic 2.12.5, scipy, pandas; **no h5py**, no netCDF4; `venv` and pip 26 present | The plugin cannot read HDF5 through h5py. Everything the plugin consumes must be GeoTIFF, CSV, GeoJSON or JSON written by the engine |
| GDAL HDF5 driver inside QGIS [Certain] | loaded as a plugin DLL when QGIS sets `GDAL_DRIVER_PATH` (absent when gdalinfo is run bare) | Even so, a tile-major `[time, tile, 32, 32]` dataset is not a raster; the plugin never opens `results.h5` |
| Engine venv [Certain] | Python 3.12.10, numpy 2.4.6, numba 0.65.1, h5py 3.16 on **HDF5 2.0.0**, rasterio 1.5 on GDAL 3.12.1 with HDF5, netCDF, GPKG, GeoJSON, COG drivers, cupy 14.2, pydantic 2.13, hecdss 0.1.29 (licence field empty in its metadata) | Write HDF5 with `libver=("earliest","v110")` so HDFView, MATLAB, rashdf and HEC tools open our files; hecdss licence must be checked by hand |
| GPU memory [Certain] | 15.59 GB free of 17.09 GB (decimal) at idle with QGIS closed; 64 MB L2; 48 KB shared per block | Budget 14 GB for the engine on his card; a laptop card is 4-8 GB |
| Windows TDR on his PC [Certain] | `TdrLevel=0` (detection off), `TdrDelay=10` | His machine tolerates long kernels; a colleague's default is 2 s with recovery on. Every kernel launch stays under 100 ms by design; `wadi2d doctor` reads these keys |
| `LongPathsEnabled=0` [Certain] | 260-character limit in force | Short run-folder names; the engine warns above 200 characters |
| Host | 125.6 GB RAM, D: 6.39 TB free, uv 0.10.9 on PATH [Certain] | The table builder may use tens of GB here but is budgeted for a 16 GB laptop |

## 1. The engineer's day: data flow and run folder

### 1.1 The loop

1. **Open QGIS**, the project has the DEM (the 5 m raster for display, the 0.5 m file bound as "terrain for tables"), a domain polygon, crest
   lines, a subbasin layer from the HMS model, design points, outflow lines. The Wadi2D dock reads the bindings from the project file.
2. **Grid page**: cell size (10 or 20 m), the domain polygon. "Estimate" runs `wadi2d run --dry-run`: cells, tiles, GPU bytes, disk bytes,
   step and time estimates, and whether the grid is already in the cache. Nothing is built yet.
3. **Build grid** (once per terrain + domain + dx + objects; cached by content hash): 1-4 min on Block 2 [Guessing], progress in the dock.
   The result `grid.h5` is self-contained: later runs never touch the 27 GB file again.
4. **Hydrology page**: point at the HMS project (`.hms`), pick basin and met; the import report lists every subbasin and reach with its
   methods and marks anything unsupported. Choose lumped or 2D per subbasin (mode a, b or c in one click).
5. **Storm page**: return period from the met file, storm area (single run) or "ARF study" (set of areas).
6. **Run**: a run folder appears; the dock shows step, dt, wet cells, mass error, ETA, the limiting cell; a live depth raster refreshes every
   2 s; maxima rasters exist from the first minute. Stop is a file; resume is a button.
7. **Results**: maxima loaded with styles; time slider over exported fields; design-point table; "downscaled depth" export at 0.5 m for a
   clipped extent for the report figure.
8. **A year later**: the run folder has `config.resolved.json`, the kernel sources used, the manifest with every input hash and software
   version; `wadi2d run --resume` or a fresh `wadi2d run job.json` reproduces it bitwise on the same backend and GPU class.

### 1.2 Study folder layout (one per QGIS project; the plugin and the CLI agree on it)

```
<study>/
  wadi2d.project.json              bindings (layer roles -> files), engine path used, defaults chosen; format_version
  inputs/                          exported by the plugin at job build, GeoJSON in the DEM CRS, one file per role
    domain.geojson  crest_lines.geojson  spillways.geojson  walls.geojson  burn_lines.geojson
    subbasins.geojson  injection_points.geojson  design_points.geojson  flux_lines.geojson  boundaries.geojson  manning.geojson
    hms/                           a verbatim copy of the HMS text files used (.hms .basin .met .control .run .pdata .gage), DSS by path only
  cache/
    grids/<grid_hash>/grid.h5      content-addressed; shared by every run and every ARF job with the same inputs
    grids/<grid_hash>/build.log, build.json (timing, DEM identity)
    terrain/<dem_hash>/dem.vrt, dem.vrt.ovr   optional overviews for display, built on a VRT so his file is never touched
  runs/
    <run_id>/                      run_id = YYYYMMDD-HHMM_<name>  (name ASCII, <= 24 chars; the folder is the identity)
      job.json                     as submitted (unresolved)
      config.resolved.json         every field filled; provenance block
      manifest.json                status, attempts, input hashes, software, device, contract versions, achieved cell-steps/s
      basin.json                   the hydrology object model actually used (after HMS import and overrides)
      forcing.h5                   storm, ARF-scaled rain, lumped hydrographs, boundary stages
      results.h5                   fields, maxima, series, mass balance, time-step log (engine-exclusive while running)
      checkpoint.h5, checkpoint.prev.h5
      maps/   max_depth.tif max_velocity.tif max_wse.tif hazard.tif arrival_time.tif  (exist from the first minute; COG at the end)
      live/   depth.tif  latest.json         (downsampled, updated in place)
      series/ hydrographs.csv points.csv lines.csv mass_balance.csv
      kernels/ numerics.h, *.cu as compiled, compile.json (nvrtc version, arch, options, source hash)
      progress.jsonl  log.txt  pid.json  stop (control file, created by the user or the plugin)
  arf/<study_id>/
      study.json                   the study definition and the expanded run list with status
      runs/ -> run ids under runs/ (same run folders; nothing duplicated)
      design_points.csv  composite/ max_depth_composite.tif ...
```

Rule: the run folder is **self-contained after `forcing`**: `grid.h5` is copied or hard-linked in (hard link on NTFS when on the same volume;
copy otherwise; `manifest.json` records which), so a run can be zipped and sent to a reviewer, and the cache can be purged.

## 2. Repository and module map

Package `wadi2d` (engine, GPL-3.0-or-later as in `LICENSE`), plugin `plugin/wadi2d_qgis`, nothing imports across that line. Every file:
its one job and its public interface in one line. Files stay under ~400 lines (rule 1); a module that grows splits.

```
pyproject.toml              package wadi2d; console script `wadi2d = wadi2d.engine.cli:main`; extras gpu (cupy-cuda12x, nvidia-* wheels), dev, docs
uv.lock + requirements/*.txt  locked, hashed installs for the engine venv (engine-gpu.txt, engine-cpu.txt)
wadi2d/
  __init__.py               __version__ (single source: read by pyproject via hatch/setuptools-scm or a static string; one place)
  contracts.py              FORMAT_VERSIONS = {job, grid, forcing, results, checkpoint, progress, manifest, basin, study, project}; is_compatible(name, found)
  config/
    schema.py               RunConfig and parts (pydantic v2, frozen): defaults, units, bounds, doc per field; model_json_schema()
    constants.py            G = 9.80665, RHO_WATER, DEM pixel 0.5 is NOT here (it is read from the DEM)
    resolve.py              resolve(job_path | dict) -> ResolvedConfig; fills defaults, relative paths, registry-validated method specs
    migrate.py              job.json format_version upgrades (a list of pure functions old->new dict)
    estimate.py             Estimate(cfg, grid_summary, bench) -> cells, bytes_gpu, bytes_host, bytes_disk, dt_est, steps, seconds (range)
  grid/
    uniform.py              UniformGrid(x0, y1, dx, nx, ny, crs, geotransform): cell<->xy, polygon->mask, DEM alignment rule
    tiles.py                TileIndex(mask, T=32): compact ids, origins, neighbours, padding rule, active-tile list helpers
    rasterize.py            lines and polygons -> cell mask / face lattice staircase with per-face crossing elevation and length factor
  terrain/
    dem.py                  Dem(path): windowed float32 reads (rasterio), nodata policy, identity (size, mtime, sampled sha256), overviews-on-VRT
    objects.py              TerrainObject registry base: CrestLine, Wall, BurnLine, Spillway; each: geometry + params -> face/cell edits
  tables/
    cell_tables.py          volume table per cell from the DEM pixels under it (sorted-pixel method), dz_cell, zmin/zmax/zmean
    face_tables.py          width, area, conveyance tables per face from the DEM profile along the face, zf_min, dz_face
    builder.py              build(cfg, grid, dem, objects) -> writes grid.h5 band by band (tile rows), parallel workers, progress events
    oracle_ras.py           read HEC-RAS geometry HDF cell/face tables (rashdf) for the test comparison
  solver/
    layout.py               ArrayLayout: names, dtypes, shapes [n_tiles,32,32(,K)], face ownership, index helpers; used by both backends and io
    params.py               KernelParams (frozen, from ResolvedConfig) -> numerics.h text + CPU namedtuple; the ONLY path from config to kernels
    backend.py              select(cfg) -> Backend ('gpu'|'cpu'); Backend protocol: alloc, upload, step(dt), reduce_cfl, download, maxima
    state.py                SolverState: the arrays (device or host) + output cursors + checkpoint read/write
    stepper.py              run loop: dt control, sources, boundaries, outputs, live view, checkpoints, stop file, NaN guard, progress
    gpu/loader.py           NVRTC compile via cupy.RawModule of kernels/*.cu with numerics.h; cache keyed by sha256(sources+header+nvrtc+arch)
    gpu/kernels/            cfl_reduce.cu reconstruct_flux_update.cu friction.cu sources.cu boundaries.cu structures.cu maxima.cu liveview.cu common.cuh
    gpu/backend_gpu.py      Backend implementation on CuPy arrays, one block per active tile
    cpu/                    one Numba file per kernel, same names, same section numbering, same argument order; backend_cpu.py
    tables_lookup.py        the depth<->level and face-table interpolation written once as device-function text + Numba twin (shared by kernels)
  hydrology/
    model.py                Basin, Subbasin, Reach, Junction, Sink, Source, Met, Control, Run (pydantic); network validation; drainage_area()
    losses/  __init__.py (registry) scs_cn.py (lumped + per-cell CUDA text + Numba) none.py        [green_ampt.py, deficit_constant.py later]
    transforms/ scs_uh.py clark.py none.py
    routing/ muskingum_cunge.py lag.py none.py
    baseflow/ none.py recession.py
    engine.py               simulate(basin, met, control, storm_area, arf) -> Hydrographs (topological order, one-way, before the 2D run)
    injection.py            injection cells per lumped subbasin (outlet point -> receiving cells and weights over the sub-grid channel width)
  hms/
    parse.py                HMS block text parser ("Key: value", "End:") -> dicts; encodings; line numbers for error messages
    basin.py met.py control.py run.py pdata.py gage.py   each: dict -> wadi2d.hydrology.model objects, unit conversion, unsupported -> errors
    dss.py                  hecdss wrapper: paired data (ARF, patterns), time series (results for tests); DSS files opened read-only
  storm/
    __init__.py (registry)  sources: uniform.py frequency.py geotiff_stack.py; each -> RainSeries per rain group or per forcing pixel
    arf.py                  ArfTable (duration x area), log-linear interpolation, scaling of a frequency storm to a storm area
    pattern.py              HMS specified pattern, SCS types; intensity position
  rain/
    groups.py               rain groups: cells -> group id (uniform: one; subbasin-masked: one per 2D subbasin; stack: pixel ids)
    forcing.py              writes forcing.h5 from storm + hydrographs + boundary stages
  arf/
    study.py                Study model (pydantic), expansion to jobs, status, resume; run_one(); design-point table; composite map
  io/
    h5grid.py h5forcing.py h5results.py h5checkpoint.py   open/create with libver, chunking, attrs, resize-on-resume; schema check
    geotiff.py              write/update GeoTIFF (in place during the run; COG at the end), nodata, tags, styles sidecar
    geojson.py              read GeoJSON (json + shapely) with our crs member; write for exports
    csv_out.py              hydrographs, points, lines, mass balance
    progress.py             ProgressWriter (stdout + progress.jsonl, seq, ts, rate limiting); ProgressReader (tail, used by tests and plugin copy)
    manifest.py             manifest.json create/update; provenance collection (versions, device, hashes)
    runfolder.py            RunFolder: paths, creation, pid.json, stop file, hard link of grid.h5, short-path checks
    migrations/             <file>_<from>_<to>.py for MAJOR bumps
  engine/
    cli.py                  argparse; subcommands import lazily (version/doctor/schema/validate start < 0.5 s)
    commands/ version.py doctor.py schema.py validate.py build_grid.py forcing.py run.py stop.py export.py arf.py bench.py hms_import.py ras_tables.py
    exitcodes.py            the table in section 6.2 (one source)
    process.py              signal handling (SIGINT, CTRL_BREAK), keep-awake flag, environment setup (CUDA_PATH, HDF5 locking, GDAL cache)
  validation/
    cases/ lake_at_rest.py thacker.py ritter.py stoker.py macdonald.py   each: build a job programmatically + exact solution + metric
    ea_tests/               EA 2D benchmark test builders (1, 2, 4, 5, 8A at least) + comparison
    metrics.py              L1/L2/Linf, mass error, arrival-time agreement
tests/                      see section 15 (marks: gpu, data, slow, plugin)
plugin/wadi2d_qgis/         see section 11
docs/                       mkdocs: tutorial (Block 2), file formats (generated from contracts), method note, licence audit (generated)
scripts/                    dev_link_plugin.ps1, install_engine.cmd, make_release.ps1, check_licences.py
W1 research and design note/
```

Registries (rule 4): `hydrology.losses`, `hydrology.transforms`, `hydrology.routing`, `hydrology.baseflow`, `storm.sources`,
`terrain.objects`, `solver.backends`, `io.exporters`. One `wadi2d/registry.py` class, section 7.

## 3. Configuration schema

One `RunConfig` in `config/schema.py`. Every field: type, unit in the description, default, bounds; `wadi2d schema` exports JSON Schema
(the plugin builds its forms from it; the docs page is generated from it; a test fails if a field lacks unit or bounds). Paths are relative
to the job file's folder. Units SI everywhere inside; HMS US units converted at import.

### 3.1 `project`

| Field | Type | Unit | Default | Bounds / note |
|---|---|---|---|---|
| format_version | str | - | "1.0" | must be compatible with `contracts.job` |
| name | str | - | required | ASCII, <= 24 chars (folder names) |
| crs | str | - | from DEM | EPSG code or WKT; must equal the DEM's; projected, metres |
| description, tags | str, list[str] | - | "" , [] | free |

### 3.2 `grid`

| Field | Type | Unit | Default | Bounds / note |
|---|---|---|---|---|
| domain | FeatureRef {path, layer?, where?} | - | required | polygon(s) in the DEM CRS; GeoJSON |
| dx | float | m | 10 | > 0; integer multiple of the DEM pixel; 2..100 |
| tile | int | cells | 32 | fixed set {32} in v1 (16 allowed for tests); extension point for the quadtree |
| align | enum | - | "dem" | "dem": origin on the DEM pixel lattice (decision 4) |
| max_cells | int | cells | 30,000,000 | hard guard; > this the job is refused before allocation |
| pad_inactive_ring | int | tiles | 1 | the padded grid ends with inactive cells (face ownership, section 8) |

### 3.3 `terrain`

| Field | Type | Unit | Default | Bounds / note |
|---|---|---|---|---|
| dem | path | - | required | GeoTIFF (or any GDAL raster), projected, metres; read windowed |
| dem_identity | enum | - | "sampled" | "sampled" (header + 64 spread blocks, seconds) or "full" sha256 (14 s on NVMe for 27.8 GB [Likely]) |
| nodata_policy | enum | - | "inactive" | "inactive": a cell with > `nodata_max_fraction` nodata pixels is inactive, remaining nodata pixels filled by nearest; "error" |
| nodata_max_fraction | float | - | 0.5 | 0..1 |
| gdal_cache_mb | int | MB | 2048 | 256..32768; `GDAL_CACHEMAX` for the engine process |
| band_rows_in_flight | int | tile rows | 2 | 1..8; host memory of the builder (section 12) |
| objects | list[TerrainObjectSpec] | - | [] | discriminated by `kind`: crest_line, wall, burn_line, spillway (section 3.4) |

### 3.4 `terrain.objects[]` (registry `terrain.objects`)

| kind | Fields (type, unit, default, bounds) |
|---|---|
| crest_line | geometry FeatureRef (lines); elevation: {mode: "vertex_z" \| "attribute" \| "constant" \| "dem_plus", field?, value? m, plus? m default 0}; length_factor_mode enum {"staircase"} default; name |
| wall | geometry (lines); height m (default: infinite, i.e. closed face); name |
| burn_line | geometry (lines); depth m (> 0) or elevation attribute; width m (default dx); applies to the cell and face tables under the line |
| spillway | geometry (point or short line on a crest face); crest_z m; length m (> 0); coefficient (m^0.5/s, default 2.1, 1.0..2.5); name; the face it sits on becomes a weir face |

### 3.5 `tables`

| Field | Type | Unit | Default | Bounds / note |
|---|---|---|---|---|
| cell_levels (K) | int | rows | 16 | 8..64; memory 4K B per cell |
| face_levels (K_f) | int | rows | 12 | 8..64; memory 12 K_f B per face |
| min_range | float | m | 0.5 | 0.05..10; minimum zmax-zmin spanned by a table (flat cells) |
| max_level_step | float | m | 2.0 | 0.1..20; if (zmax-zmin)/(K-1) exceeds it the table stops at K rows and the kernel extrapolates linearly |
| face_sample_step | float | m | DEM pixel | 0.25..dx; sampling step along a face |
| conveyance_exponent | float | - | 2/3 | fixed in v1 (Manning); field exists so Chezy can be added |
| method | enum | - | "sorted_pixels" | registry hook for a later TIN method |
| cache | bool | - | true | reuse `cache/grids/<hash>` |

### 3.6 `numerics` (the panel on numerics owns the values; the schema owns where they live)

| Field | Type | Unit | Default | Bounds / note |
|---|---|---|---|---|
| cfl | float | - | 0.5 | 0.1..0.95 |
| riemann | enum | - | "hllc" | "hllc", "roe" (registry of flux functions in the kernel text) |
| reconstruction | enum | - | "muscl_minmod" | "first_order", "muscl_minmod", "muscl_vanleer" |
| time_integrator | enum | - | "ssp_rk2" | "euler", "ssp_rk2", "muscl_hancock" |
| h_dry | float | m | 1e-4 | 1e-6..1e-2; below: cell is dry, momentum zeroed |
| h_wet | float | m | 1e-3 | > h_dry; above: fluxes computed |
| h_cfl_min | float | m | 1e-3 | cells shallower are excluded from the CFL search (decision 18 c) |
| velocity_cap | float | m/s | 20 | 5..50; diagnostic cap, counted in warnings |
| desingularise_eps | float | m | 1e-3 | Kurganov-Petrova type velocity in thin cells |
| friction | enum | - | "point_implicit" | registry hook |
| dt_max, dt_min, dt_init | float | s | 30, 1e-3, 0.1 | dt_min < dt_init < dt_max; dt < dt_min for `dt_min_patience` steps -> exit 5 |
| dt_min_patience | int | steps | 200 | 10..10000 |
| nan_check_every | int | steps | 50 | 1..1000 |
| active_rebuild_every | int | steps | 20 | 1..1000; active-tile list refresh |
| active_margin | int | tiles | 1 | 1..2 |

### 3.7 `physics`

| Field | Type | Unit | Default | Bounds / note |
|---|---|---|---|---|
| manning | {source: "constant" \| "raster" \| "polygons", value?, path?, field?} | s/m^(1/3) | constant 0.035 | 0.008..0.3; per cell; face n = mean of the two cells |
| manning_min_depth | float | m | 0.01 | depth below which n is not increased further (thin-film treatment, numerics panel) |
| gravity | - | - | constants.G | not configurable (rule 2: a constant, not a parameter) |

### 3.8 `hydrology`

| Field | Type | Unit | Default | Bounds / note |
|---|---|---|---|---|
| mode | enum | - | "b" | "a" lumped only (no 2D), "b" hybrid, "c" all 2D |
| hms | {project: path, basin: str, met: str, control: str?, run: str?} | - | null | import source; everything imported is written to basin.json |
| basin | path | - | null | alternative: a basin.json built by the plugin |
| subbasin_overrides | list[{name, kind: "lumped"\|"2d", loss?, transform?, baseflow?, injection?}] | - | [] | per subbasin; `injection: {mode: "outlet"\|"point"\|"feature", xy?, spread: "channel_width"\|"single", radius_m?}` |
| default_2d_loss | LossSpec | - | scs_cn from the basin | losses on 2D cells; registry-discriminated |
| time_step_min | float | min | 1 | 0.1..60; lumped engine step; hydrographs are interpolated by the solver |
| cn_raster | path | - | null | optional per-cell CN; else the subbasin's CN on its cells |

### 3.9 `storm` (registry `storm.sources`, discriminated by `kind`)

| kind | Fields |
|---|---|
| uniform | depth mm (0..2000), duration h (0.1..240), pattern {name: "scs_type_ii" \| "hms_specified", path?, series?}, start datetime |
| frequency | depths {duration_min: depth_mm} (as the HMS met file), pattern as above, intensity_position % (default 50; 0..100), storm_area_km2 (> 0), arf {table: path \| inline {durations_min[], areas_km2[], factors[][]} \| "none"}, return_period label, from_hms met name? |
| geotiff_stack | folder, glob, time_step_min, units "mm" \| "mm_h", start, resample "nearest" \| "bilinear" |
| common | time_step_min (default 1; 0.1..60), total_depth_check bool (default true: refuse if pattern does not integrate to 1 +- 1e-3) |

### 3.10 `boundaries[]`

| Field | Type | Default | Note |
|---|---|---|---|
| name | str | required | |
| kind | enum | "outflow_normal" | "outflow_normal" (normal-depth outflow using the face conveyance), "stage" (series), "closed" |
| geometry | FeatureRef (lines) | required | snapped to the nearest active-inactive faces |
| stage | {series: path \| inline, datum "msl"} | null | for "stage" |
| slope | float | from the DEM | 1e-5..1 for outflow_normal |

### 3.11 `outputs`

| Field | Type | Unit | Default | Bounds / note |
|---|---|---|---|---|
| fields | list[enum] | - | ["depth"] | any of depth, qx, qy, velocity, wse |
| field_step | float | min | 15 | 0.5..1440 |
| keep_transient_fields | bool | - | true (false for ARF runs) | |
| maxima | list[enum] | - | all | depth, velocity, wse, hazard, arrival_time, time_of_max |
| hazard | enum | - | "dv" | "dv" (depth x velocity), "defra_2006", "arr_2019" (registry) |
| arrival_depth | float | m | 0.05 | 0.01..1 |
| points | FeatureRef (points) | - | null | depth, wse per point every `series_step` |
| lines | FeatureRef (lines) | - | null | discharge through the faces crossed, signed by line direction |
| series_step | float | min | 1 | 0.1..60 |
| mass_balance_step | float | min | 5 | 1..60 |
| live_view | {enabled bool true, every_seconds 2.0 (0.5..60), field "depth", downsample 4 (1..16), extent "domain" \| "viewport"} | | | section 11.5 |
| geotiff | {compression "deflate", level 6, predictor 3, cog true, nodata -9999.0, overviews true} | | | section 5.5 |
| checkpoints | {every_minutes 10 (1..120), keep 2 (1..5), at_outputs false} | wall min | | |
| h5 | {compression "gzip" \| "lzf" \| "none", level 1, shuffle true, chunk_tiles 64} | | | section 5.3 |

### 3.12 `run`

| Field | Type | Unit | Default | Bounds / note |
|---|---|---|---|---|
| start | datetime | - | from control or storm | ISO 8601 |
| duration | float | h | required | 0.01..480 |
| backend | enum | - | "auto" | "auto" (gpu if a device and cupy, else cpu), "gpu", "cpu" |
| device | int | - | 0 | >= 0 |
| precision | enum | - | "float32" | the only value in v1; the field exists so mixed precision is a config change |
| threads | int | - | physical cores | 1..256 (cpu) |
| deterministic | bool | - | true | no atomics in state, fixed-order sums; false allows faster non-deterministic sums (never in v1 kernels) |
| keep_awake | bool | - | true | `SetThreadExecutionState` while running (laptops) |
| stop_poll_every | int | steps | 50 | 1..1000 |
| estimate | {h_ref 2.0 m, u_ref 3.0 m/s, active_fraction 0.5} | | | dry-run inputs, overwritten by calibration from `bench.json` and past runs |

### 3.13 `arf` (used by `wadi2d arf`; `study.json` embeds a RunConfig plus this)

| Field | Type | Unit | Default | Bounds / note |
|---|---|---|---|---|
| storm_areas | list[float] \| {"auto": {n 7, min?, max?}} | km² | auto | 2..20 areas; auto = log-spaced between the smallest and largest design-point drainage areas |
| return_periods | list[str] | - | all in the met files | HMS met names or labels |
| design_points | {features: FeatureRef, area_source: "hms_element" \| "field" \| "accumulation", field?, element_field?} | | required | |
| interpolation | enum | - | "loglinear" | "nearest", "loglinear" in area |
| composite | {enabled false, accumulation_raster path, cell_area_m2 from raster} | | | |
| per_run_outputs | partial `outputs` | - | maxima + series, no transient fields | |
| max_parallel | int | - | 1 | 1..8; > 1 only for cpu or several devices |

### 3.14 How numerics reach the kernels (no literal in a `.cu` file)

`solver/params.py` derives a frozen `KernelParams` from `ResolvedConfig` (the subset the kernels need: T, K, K_f, cfl, h_dry, h_wet,
h_cfl_min, desingularise_eps, velocity_cap, G, conveyance exponent, riemann and reconstruction choices, loss method, hazard method). From
that one object:

- `numerics.h` is rendered (`constexpr float H_DRY = 1.0e-4f;`, `#define WADI2D_T 32`, `#define FLUX_FN flux_hllc`, `#define LOSS_FN
  loss_scs_cn`) and `#include`d by every `.cu`; the file is written into `runs/<id>/kernels/` next to the exact `.cu` sources used.
- The Numba twins receive the same `KernelParams` as a namedtuple argument (Numba specialises on it), so one object feeds both backends.
- Per-step values (dt, t, rain index and weights, output flags) travel in a `StepParams` struct passed by value to each launch.
- `tests/test_no_literals.py` scans `gpu/kernels/*.cu` and `cpu/*.py` with a regex and fails on any numeric literal other than
  0, 1, 2, 0.5, 0.25 and loop bounds derived from `WADI2D_T`. Mechanical, not a convention.

### 3.15 The resolved configuration record

`config.resolved.json` = the full `RunConfig` with every default filled, every path made absolute, every method spec expanded, plus a
`_provenance` block: engine version and git describe, contract versions, python, numpy, numba, cupy, nvrtc, cuda runtime, driver, GPU name
and compute capability, backend chosen, host name, user, start time, `grid_sha256`, `dem_identity`, hashes of every input file. It is
written before the first step and never modified; `manifest.json` carries the mutable status. A run is reproducible from the folder alone
(rule 2): `wadi2d run runs/<id>/config.resolved.json --out <new>` is a valid invocation.

## 4. Data contracts: files and their schemas

All HDF5 files: created with `h5py.File(path, "w", libver=("earliest", "v110"))`, root attrs `format_version` (string "MAJOR.MINOR"),
`producer` ("wadi2d 1.0.0"), `created` (ISO), `contract` (name). Arrays over cells are **tile-major** `[n_tiles, 32, 32]` (section 8), chunked
`(chunk_tiles, 32, 32)` with `chunk_tiles = 64` (256 KB float32 chunks), gzip level 1 + shuffle by default (dry tiles are zeros and vanish).
Row index inside a tile increases southward (GDAL convention) so no array is ever flipped between the DEM, the solver and a GeoTIFF.

### 4.1 `grid.h5` (producer `wadi2d build-grid`; consumers solver, forcing, export, plugin via export only)

```
/                       attrs: format_version "1.0", crs_wkt, crs_epsg, geotransform[6] (GDAL), dx, nx, ny (padded), ntx, nty, T=32,
                        n_tiles (compact), n_cells_active, dem_path, dem_identity (json), objects_json, tables_json, builder_version,
                        grid_hash (sha256 of the inputs that define it), build_seconds
/tiles/index            int32 [nty, ntx]        compact id or -1
/tiles/origin           int32 [n_tiles, 2]      (tj, ti)
/tiles/neighbors        int32 [n_tiles, 4]      compact ids W, E, N, S or -1
/tiles/n_active         uint16 [n_tiles]
/tiles/bbox             float64 [n_tiles, 4]    xmin, ymin, xmax, ymax (export clipping without reading cells)
/cells/mask             uint8  [n_tiles,32,32]  bit0 active, bit1 touches boundary face, bit2 has crest face, bit3 injection cell
/cells/zmin zmax zmean  float32 [n_tiles,32,32] m
/cells/dz_cell          float32 [n_tiles,32,32] m   table spacing (section 8.3)
/cells/vol_table        float32 [n_tiles,32,32,K]   storage depth s_k (m) at level zmin + k dz_cell; s_0 = 0; monotone
/cells/manning          float32 [n_tiles,32,32] s m^-1/3
/cells/rain_group       int16  [n_tiles,32,32]  -1 none (lumped-masked), else group id into forcing /rain
/cells/subbasin         int16  [n_tiles,32,32]  index into /subbasins or -1
/cells/loss/<method>/<param>   float32 [n_tiles,32,32]   e.g. /cells/loss/scs_cn/cn
/faces_x/ and /faces_y/ (west face and north face of each cell, section 8.2)
   zf_min dz_face       float32 [n_tiles,32,32] m
   width area conv      float32 [n_tiles,32,32,K_f]  wet-width fraction (-), area (m2), A R^(2/3) (m^(8/3)) at depth k dz_face over zf_min
   crest                float32 [n_tiles,32,32] m; NaN = none
   length_factor        float32 [n_tiles,32,32] (-), 1 where no crest
   flags                uint8  [n_tiles,32,32]  bit0 wall(closed) bit1 crest bit2 weir(spillway) bit3 boundary bit4 outside(unstored twin)
/structures/spillways   compound [n]: name S32, tile i j side(0 x,1 y) int32, crest_z length coef float32
/boundaries/faces       compound [n]: tile i j side int32, boundary_id int16
/boundaries/defs        attrs: json list (name, kind, params)
/subbasins/             attrs: json list (name, kind, area_km2, injection); /subbasins/injection compound [m]: subbasin_id tile i j weight
/provenance/            attrs: dem statistics (min, max, nodata fraction), per-stage timing, worker count, host
```

Consistency checks written by the builder and verified by `wadi2d validate --grid`: a stored face and its unstored twin never both border
active cells; every injection weight set sums to 1; tables monotone; `grid_hash` recomputed equals the attr.

### 4.2 `forcing.h5` (producer `wadi2d forcing`; consumer the solver; per run because ARF scaling is per run)

```
/                       attrs: format_version "1.0", start (ISO), dt_s, n_steps, grid_hash, storm_json, arf_json (storm area, factors by duration)
/time                   float64 [nt] seconds since start
/rain/rate              float32 [nt, n_groups] mm/h      (uniform: n_groups = 1)
/rain/groups            compound [n_groups]: id, name, subbasin_id, area_km2
/rain/pixels            (geotiff_stack only) float32 [nt, rows, cols] mm/h + attrs geotransform; /rain/cell_pixel int32 [n_tiles,32,32]
/hydrographs/flow       float32 [nt, n_points] m3/s
/hydrographs/points     compound: name, subbasin_id, injection ref
/hydrographs/components/<subbasin>/{precip, excess, baseflow, direct}  float32 [nt] (the mode (a) record; CSV mirror in series/)
/boundaries/stage       float32 [nt, n_stage]
```

### 4.3 `results.h5` (producer the solver; exclusive to the engine while running; consumers `wadi2d export`, tests)

```
/                       attrs: format_version "1.0", run_id, grid_hash, completed bool, end_reason, t_end_s, resumed_from (json list)
/time/fields            float64 [nt_out]  (maxshape None; truncated on resume)
/fields/<name>          float32 [nt_out, n_tiles, 32, 32]  chunks (1, 64, 32, 32); gzip 1 + shuffle; attrs units
/maxima/<name>          float32 [n_tiles, 32, 32]; /maxima/time_of_max float32 (s)
/series/time            float64 [nt_s]; /series/points/{depth,wse} float32 [nt_s, n_pts]; /series/lines/discharge float32 [nt_s, n_lines]
/series/defs            attrs json (names, xy, cells)
/mass/                  time, stored, cum_rain, cum_infiltration, cum_inflow, cum_outflow, error_rel  float64 [nt_m]
/steps/                 t, dt float32 [n_steps]; limiting_cell int32 [n_steps, 3]; n_active_tiles int32; wall_ms float32  (appendable)
/warnings/              compound [n]: step, code S16, tile i j, value float32
```

### 4.4 `checkpoint.h5`

`/state/{h, qx, qy}`, `/state/loss/<param>`, `/maxima/*`, attrs `t, step, output_index, series_index, mass_totals (json), config_sha256,
grid_hash, engine_version, format_version`. Written to `checkpoint.tmp.h5` then rotated (`prev` <- current <- tmp) so a crash during a
write never loses the last good one. Resume refuses a checkpoint whose `config_sha256` or `grid_hash` differ (exit 7).

### 4.5 JSON files (all with `format_version`)

| File | Shape (top level) |
|---|---|
| `job.json` | RunConfig unresolved (section 3) |
| `config.resolved.json` | RunConfig resolved + `_provenance` (3.15) |
| `manifest.json` | run_id, status (created\|running\|done\|stopped\|failed), attempts[] {start, end, pid, host, exit_code, engine_version, achieved_cell_steps_per_s}, inputs {dem {path,size,mtime,identity}, files {path: sha256}}, grid {path, hash, linked\|copied}, software {...}, contracts {...} |
| `basin.json` | the hydrology object model (section 9) |
| `study.json` | arf study (section 10) |
| `wadi2d.project.json` | bindings {role: {path, layer, field map}}, engine {exe, version}, defaults, last_run_ids |
| `pid.json` | pid, host, started, engine exe (plugin attaches by folder, 11.3) |
| `live/latest.json` | path of the live raster, t, step, downsample, extent, seq |
| `cache/grids/<hash>/build.json` | inputs, timing, builder version |

### 4.6 GeoJSON inputs

FeatureCollections written by the plugin (or by hand) in the DEM's projected CRS with a top-level `"crs": {"type": "name", "properties":
{"name": "EPSG:32640"}}` member (the pre-RFC form GDAL and QGIS still honour), coordinates with 3 decimals, one file per role, properties
per role documented in the schema (`crest_z`, `length`, `coef`, `name`, `subbasin`, `kind`, `n`, `area_km2`). The engine reads them with
`json` + shapely; no OGR dependency in the engine. Z on vertices is honoured for crest profiles (`elevation.mode = "vertex_z"`).

### 4.7 GeoTIFF conventions

Float32, nodata -9999, CRS and geotransform from the grid, tiled 256 x 256. **During the run**: uncompressed, preallocated, updated in
place (`live/depth.tif` and `maps/max_*.tif`); on Windows GDAL opens with share-all, so QGIS reading while the engine writes is allowed
[Likely]; a torn frame is acceptable in the live view. **At the end** (or on `wadi2d export`): rewritten as COG, DEFLATE 6, predictor 3,
overviews (average), band description = field, GDAL metadata `WADI2D_RUN_ID`, `WADI2D_FIELD`, `WADI2D_TIME_S`, `WADI2D_UNITS`,
`WADI2D_FORMAT_VERSION`. Fixed names (`max_depth.tif`, ...). A `.qml` style sidecar per field ships with the plugin and is applied on load.
Downscaled sub-grid depth (depth at DEM pixels = max(0, wse_cell - z_px)) only through `wadi2d export --downscale --clip`, COG, with the
0.5 m DEM read windowed over the clip.

### 4.8 Progress events (stdout and `progress.jsonl`, one JSON object per line)

Every event: `seq` (int, monotone), `ts` (ISO, local with offset), `ev` (string), `run_id`. Rate limit: `step` at most once per second of
wall time and at least every 1,000 steps.

```
{"ev":"start","pid":1234,"host":"...","backend":"gpu","device":"NVIDIA GeForce RTX 5080","n_cells":1497120,"n_tiles":1480,"t_end":172800,"engine":"1.0.0","contracts":{...}}
{"ev":"phase","name":"build-grid","pct":12.5,"msg":"tile row 13/104","eta_s":95}
{"ev":"step","step":12345,"t":3600.5,"dt":1.82,"wet_cells":123456,"active_tiles":812,"mass_err":1.2e-6,"wall_s":55.1,"eta_s":410,"cell_steps_per_s":1.4e9,"lim":[812,5,17],"lim_xy":[412345.5,2701234.5]}
{"ev":"output","kind":"field|maxima|series|checkpoint","t":3600.0,"path":"results.h5","index":4}
{"ev":"liveview","path":"live/depth.tif","t":3600.0,"seq":17}
{"ev":"warn","code":"W_DT_SMALL|W_VEL_CAP|W_MASS|W_NODATA|W_LONGPATH|W_TDR","msg":"...","cell":[812,5,17],"xy":[...],"value":0.02}
{"ev":"resume","from_t":7200.0,"checkpoint":"checkpoint.h5","attempt":2}
{"ev":"end","status":"ok|stopped|failed","exit_code":0,"reason":"","wall_s":612.3,"summary":{"max_depth":4.2,"mass_err":3e-5,"steps":92345}}
```

The file is the durable, primary channel; stdout is a mirror for liveness and for the CLI user. The plugin tails the file (11.3).

### 4.9 Format versioning and migration

`wadi2d/contracts.py` holds every contract version in one dict; the plugin's `contract.py` carries a copy of the same dict and a repo test
asserts equality. A reader accepts the same MAJOR and any MINOR <= its own; MINOR adds datasets, attrs or fields with defaults; MAJOR is
breaking and needs `wadi2d migrate <file>` (functions in `io/migrations/`, each `(from, to)`, pure, tested on fixtures). `job.json` migrates
on load through `config/migrate.py` (renames, splits) before validation. Every file names its `format_version`; the plugin refuses to build
a job or to open a run whose MAJOR differs and tells the user which side to update.

## 5. Engine process protocol

### 5.1 Commands

```
wadi2d version [--json]                       engine, contracts, python; no heavy imports (< 0.5 s)
wadi2d doctor [--json] [--bench]              python, cupy, nvrtc, cuda runtime, driver, GPU and free memory, numba threads, GDAL, h5py/HDF5,
                                              free disk, TDR keys, LongPathsEnabled, engine home, kernel cache; --bench runs `bench`
wadi2d schema [--part grid|...] [--out f]     JSON Schema (draft 2020-12) of RunConfig or a part
wadi2d validate job.json [--grid grid.h5]     exit 0, or 2 with a JSON list of {loc, msg, hint}
wadi2d build-grid job.json --out <study> [--force] [--workers N]      -> cache/grids/<hash>/grid.h5 (reused on hit)
wadi2d forcing job.json --out <run> [--mode a|b|c]                    -> forcing.h5, basin.json, series/hydrographs.csv  (mode a ends here)
wadi2d run job.json --out <run> [--dry-run] [--resume] [--backend auto|gpu|cpu] [--device N] [--progress file|stdout|both] [--quiet]
                                              build-grid (cache) + forcing + solve + maps; --dry-run prints the estimate JSON and exits 0
wadi2d stop <run>                             creates <run>/stop (idempotent)
wadi2d export <run> --what maxima|field|series [--time T|--index i] [--format gtiff|csv] [--downscale F] [--clip geojson] [--out dir]
wadi2d arf study.json --out <study> [--list] [--only RUN_ID] [--resume] [--max-parallel N]
wadi2d arf-table <study> [--out csv]          design-point table (peaks, hydrographs by area interpolation)
wadi2d composite <study> --accumulation acc.tif [--what max_depth,...]
wadi2d hms-import project.hms --basin B --met M [--out basin.json] [--report]    import diagnostics
wadi2d ras-tables geometry.hdf --out tables.h5                                     oracle for the table tests
wadi2d bench [--backend auto|gpu|cpu] [--cells 1000000] [--steps 200]             -> engine home bench.json (cell-steps/s; the estimate's basis)
wadi2d migrate <file> [--to X.Y]
```

Global flags: `--log-level`, `--engine-home` (default `%LOCALAPPDATA%\Wadi2D`), `--no-color`. All paths are passed as argument lists, never
through a shell (spaces and Arabic in his folder names are routine). The process sets for itself: `HDF5_USE_FILE_LOCKING=FALSE`,
`GDAL_CACHEMAX` from config, `CUDA_PATH` to the nvidia wheel folder (silences CuPy), `NUMBA_NUM_THREADS` from `run.threads`,
`CUPY_CACHE_DIR` under the engine home.

### 5.2 Exit codes (`engine/exitcodes.py`, the single table)

| Code | Meaning | What the engineer sees in the dock |
|---|---|---|
| 0 | success | results loaded |
| 1 | unexpected exception (traceback in `log.txt`) | "engine error, see log" with the last 20 lines |
| 2 | invalid job or config (list of loc, msg, hint) | the offending page highlighted |
| 3 | input file problem: missing, unreadable, CRS mismatch, unsupported HMS feature | file name and the fix |
| 4 | resources: GPU or host memory, disk space, max_cells exceeded | the numbers needed vs available, and the dry-run advice (coarser dx, smaller domain, cpu) |
| 5 | numerical failure: NaN, dt < dt_min for dt_min_patience steps | the cell coordinates; "Zoom to cell" button; last checkpoint kept |
| 6 | stopped by the user (stop file or SIGINT), outputs flushed | "stopped at t = ..., resume available" |
| 7 | contract or version mismatch (resume of another version, incompatible grid.h5) | which side to update |
| 8 | backend unavailable (gpu requested, none usable) | "run on cpu?" |
| 9 | another engine holds this run folder (`pid.json` alive) | attach instead |

### 5.3 Stop, restart, resume

- **Stop**: the `stop` file (polled every `stop_poll_every` steps) is primary because it works for a user without a terminal, for the plugin,
  and later for a job runner on another PC. SIGINT / `CTRL_BREAK_EVENT` (the plugin starts the process with `CREATE_NEW_PROCESS_GROUP`) is
  the same path. On stop: finish the step, write the checkpoint, flush results, write the maxima COGs, `end` event with `status: stopped`,
  exit 6. Grace: the plugin waits 60 s then kills; a killed run still has its last checkpoint.
- **Resume**: `wadi2d run job.json --out <run> --resume` loads `checkpoint.h5` (falls back to `checkpoint.prev.h5`), checks config and
  grid hashes, truncates `results.h5` time axes to the checkpoint indices, appends an attempt to `manifest.json`, emits `resume`. Bitwise
  identical to the uninterrupted run on the same backend (section 13), which is a test.
- **Crash or power cut**: nothing to do beyond `--resume`; at most `checkpoints.every_minutes` of compute lost; HDF5 datasets are flushed
  at every output so the file is readable up to the last output even without the checkpoint.
- **A run folder with a live `pid.json`** (pid alive and command line matches): a second `run` refuses (exit 9); the plugin attaches.

### 5.4 Dry-run estimates

`--dry-run` resolves the config, builds or loads only the grid *summary* (tile index and counts; from the cache when present, otherwise a
fast pass over the domain polygon at tile resolution without reading the DEM) and prints:

```
{"cells_active":1497120,"tiles":1480,"bytes_gpu":687000000,"bytes_host":450000000,"bytes_disk":{"results":900000000,"maps":36000000,"checkpoints":72000000},
 "dt_est_s":2.1,"steps_est":82000,"seconds_est":[45,180],"cell_steps_per_s_assumed":2.0e9,"basis":"bench.json 2026-10-29 gpu","grid_cached":true,
 "warnings":["no bench.json for cpu backend; estimate x10 uncertainty"]}
```

`dt_est = cfl dx / (sqrt(g h_ref) + u_ref)` with `run.estimate`; `seconds = steps x cells x active_fraction / rate`, rate from `bench.json`
(or the median of the last three runs' achieved rates recorded in their manifests, if any), reported as a range x0.5..x2. The dock shows
the range and refuses to start when `bytes_gpu` exceeds 90% of free device memory or the disk estimate exceeds free space.

## 6. Registries and adding a method

`wadi2d/registry.py`:

```python
class Registry(Generic[T]):
    def __init__(self, name: str, interface: type[T]): ...
    def register(self, key: str) -> Callable[[type[T]], type[T]]   # decorator; refuses duplicates; checks the interface
    def get(self, key: str) -> type[T]
    def keys(self) -> list[str]
    def config_union(self) -> type   # Annotated[Union[params models], Field(discriminator="method")] for the schema
```

Each registered class declares: `key`, `Params` (pydantic model with units and bounds), `format_version`, and the interface methods. For a
**loss method** (`hydrology.losses`): `initial_state(params, n) -> dict[str, ndarray]`, `step_lumped(rain_mm, state, params, dt) ->
excess_mm`, and for 2D use `cuda_source: str` (a `__device__ float loss_<key>(...)` text with the same signature for every method) and
`cpu_fn` (a Numba `njit` function with the same arguments). The sources kernel calls `LOSS_FN(...)`; `params.py` writes `#define LOSS_FN
loss_<key>` and `loader.py` prepends the registered device-function text to the module source. Transform and routing methods are
lumped-only in v1 (NumPy). Storm sources return `RainSeries` per group or per pixel. Terrain objects expose `apply(grid, builder_ctx)`.
Backends expose the `Backend` protocol. Exporters map a name to a writer.

**Adding a method** = one new file (`hydrology/losses/green_ampt.py`) with the `Params` model, the lumped step, the CUDA text and the
Numba twin, plus its tests against a reference (HMS numbers or a hand computation), plus one import line in the package `__init__.py`
(explicit list in v1; `importlib.metadata` entry points `wadi2d.losses` are the extension door for third-party packages). The config schema,
the JSON Schema for the plugin's forms and the docs page update themselves because they are generated from the registry.

## 7. Solver array layout and tile convention (shared by GPU and CPU)

### 7.1 Arrays

Structure of arrays, float32 state, every per-cell array `[n_tiles, T, T]` with T = 32, tile-major, compact over domain tiles (never the
bounding box; the 42 M-cell bounding box of Block 2 at 10 m is why). `layout.py` is the one description of names, dtypes, shapes, face
ownership and the `(tile, j, i)` index convention; the HDF5 writers and both backends import it. Index: `idx = tile*T*T + j*T + i`, `i`
east, `j` south (row 0 is the northern row, as in the DEM and the GeoTIFFs). Cell centre: `x = x0 + (ti*T + i + 0.5) dx`, `y = y1 - (tj*T + j +
0.5) dx`.

### 7.2 Faces and ownership

Cell `(tile, j, i)` owns its **west** x-face and its **north** y-face. Its east face is the west face of `(i+1)` or of column 0 of the E
neighbour tile; its south face is the north face of `(j+1)` or of row 0 of the S neighbour tile. The padded grid ends in an inactive column
and row (`grid.pad_inactive_ring`), so the unstored east and south faces of the last tiles never border an active cell (asserted by the
builder, flag bit4 marks them). Boundary faces are listed explicitly in `/boundaries/faces`; any active-inactive face not listed is a wall.

### 7.3 Tables and precision

The state `h` is volume per cell area (decision 3). Level from depth: `vol_table` is monotone in `k`; the kernel finds `k` by a 4-step
binary search over K = 16 (shared memory per tile) and interpolates; beyond the table the slope is 1 (fully wet). Face tables are indexed by
depth over `zf_min` with spacing `dz_face`. Free-surface differences across a face are computed as `(zmin_i - zmin_j) + (lev_i - lev_j)`
in that order: the first term is exact in float32 whenever the two elevations are within a factor of two (Sterbenz) [Certain, IEEE], the
second carries full float32 resolution at depth scale; no per-face bed-difference array is needed.

### 7.4 Halos and launch

One thread block per **active** tile; the block gathers its 32 x 32 cells plus a 2-cell halo (36 x 36) for h, qx, qy, zmin, dz_cell from the
neighbour tiles through `/tiles/neighbors` (gather, no stored halo); 5 fields x 36 x 36 x 4 B = 26 KB shared, under the 48 KB per block
[Certain]. Block size 16 x 16 threads, 2 x 2 cells per thread (register pressure). Active-tile list: wet flag per tile reduced every
`active_rebuild_every` steps, dilated by `active_margin`; a tile with an injection cell or a stage boundary is always active. Every launch
finishes in milliseconds; no persistent kernel (TDR on display GPUs, section 0). The CPU twin runs the same loop: `numba.prange` over active
tiles, the same gather, the same section order inside the kernel function.

### 7.5 Determinism

No atomics touch the state: injection weights are per cell; line discharges are summed on the host in fixed order from per-face values;
the CFL reduction is a min (order-free); mass-balance sums use a fixed pairwise tree. Same job + same engine version + same backend + same
GPU architecture = bitwise identical `results.h5` (a test, section 13). CPU and GPU agree to a tolerance, not bitwise.

### 7.6 Parity testing

(1) Single-step parity: random wet-dry state over 20 tiles with random tables, one step on both backends, `max|diff| < 32 eps_32 x
max|value|`. (2) Case parity: the analytic suite on both backends, errors against the exact solution within the same tolerance band and
`|CPU - GPU|` below 1e-5 relative after 1,000 steps. (3) Goldens: per backend, stored checksums of `results.h5` fields for three small cases,
updated only by an explicit `--update-goldens` with the reason in the commit. (4) Structural: each `.cu` kernel and its Numba twin carry
the same numbered sections (`// [3] face flux`), and a test checks the section lists match. Drift between two hand-written implementations
is the standing risk; section 19 names the alternative to benchmark.

## 8. Hydrology object model and the HMS readers

`hydrology/model.py` (pydantic, serialised as `basin.json`, format_version):

```
Basin      name, unit_system_source ("SI"|"US"), elements: list[Subbasin|Reach|Junction|Sink|Source|Reservoir|Diversion] (discriminator "type"),
           validators: unique names, downstream links resolve, acyclic, every tree ends in a Sink; drainage_area(name) -> km2
Subbasin   name, area_km2, downstream, kind ("lumped"|"2d"), loss: LossSpec, transform: TransformSpec, baseflow: BaseflowSpec,
           geometry: FeatureRef|None, injection: InjectionSpec (mode outlet|point|feature, xy, spread channel_width|single, radius_m)
Reach      name, downstream, routing: RoutingSpec (muskingum_cunge {length_m, slope, n, section: trapezoid{bottom_width_m, side_slope} |
           eight_point{stations_m[8], elevations_m[8], n_left, n_main, n_right}, space_time "auto"} | lag {lag_min} | none)
Junction   name, downstream;   Sink name;   Source name, downstream, series;   Reservoir, Diversion: parsed, refused in v1 with a message
Met        name, kind frequency_storm {depths {dur_min: mm}, pattern, intensity_position, storm_area_km2, arf: ArfTable|None} |
           specified_hyetograph {gage: series}
Control    start, end, time_step_min
Run        name, basin, met, control, dss_path
Hydrographs  time_s[], flows {element: m3/s[]}, components {subbasin: {precip, loss, excess, baseflow}}, meta (storm area, arf applied)
```

Readers are adapters: `hms/parse.py` turns the HMS block format into dicts with line numbers; `hms/basin.py` etc. map dicts to the model,
converting US units at the boundary (the basin file's `Unit System`), collecting every unsupported method into one `HmsImportReport`
(element, method, line) that `wadi2d hms-import --report` prints and `forcing` turns into exit 3. `hms/pdata.py` resolves paired-data
tables (ARF, patterns) to DSS records read through `hecdss` (read-only). The engine never reads HMS files at solve time: `forcing` writes
`basin.json` and `forcing.h5`, and the run depends on those alone. The plugin can also build a `basin.json` from layers (subbasin polygons
with CN and lag fields) without HMS. The lumped engine (`hydrology/engine.py`) runs **before** the 2D run, one-way, on
`hydrology.time_step_min`; the solver interpolates the hydrographs in time at injection cells. Mode (a) is `wadi2d forcing --mode a`
(no solver), which is also how the HMS replication test runs on CI without a GPU.

## 9. ARF orchestration as independent jobs

`study.json` = a base RunConfig + the `arf` part. `wadi2d arf study.json --out <study>` expands return periods x storm areas into run
folders `runs/<study>_T<rp>_A<area>` each with a complete `job.json` (storm area set, rain scaled by the ARF table for every duration,
`outputs` = maxima + series, transient fields off), all pointing at one cached `grid.h5` (hard-linked in). `study.json` carries the expanded
list with status per run; `--resume` skips `done`, re-runs `failed`, attaches to `running`; `--only` runs one; `--max-parallel` > 1 only for
cpu runs or several devices (one GPU runs them serially; the plugin runs the study as one QgsTask that spawns one engine process at a time).
Each run is an ordinary job: restartable alone, movable to another PC by copying its folder, and exactly what a later job runner (decision
16) distributes. `wadi2d arf-table` reads each design point's drainage area (HMS element cumulative area, a layer field, or the
accumulation raster at the point), picks the bracketing storm areas and interpolates peak and hydrograph log-linearly in area
(`arf.interpolation`), and writes `design_points.csv` (point, area, areas used, peak, time to peak, run ids). `wadi2d composite` resamples
the accumulation raster to the grid, maps every cell to its bracketing runs and interpolates the maxima into `composite/*.tif`, with a
`provenance.json` naming the runs used. Disk per study on Block 2 at 10 m [Guessing]: 100 runs x (36 MB maxima + 5 MB series) ~ 4 GB.

## 10. QGIS plugin

### 10.1 Files

```
plugin/wadi2d_qgis/
  metadata.txt               name, qgisMinimumVersion=3.34, version (plugin), engine_contract_major
  __init__.py                classFactory
  plugin.py                  menu, toolbar, dock registration, processing provider registration, settings
  contract.py                copy of FORMAT_VERSIONS, exit codes, event names, file names (tested equal to the engine's)
  engine/locator.py          find the engine exe: QGIS setting -> %LOCALAPPDATA%\Wadi2D\engine\current.json -> PATH; `version --json` handshake
  engine/client.py           EngineProcess: Popen(args list, CREATE_NEW_PROCESS_GROUP|CREATE_NO_WINDOW, stdout pipe); stop(); kill(); doctor(); schema()
  engine/events.py           ProgressTailer: reads progress.jsonl incrementally (seek), parses, emits Qt signals on the GUI thread
  job/builder.py             JobBuilder(project_state, pages) -> job.json + inputs/*.geojson + hms copies; CRS check and reprojection to the DEM CRS
  job/schema_forms.py        builds QWidgets for a schema part (number fields with unit and bounds, enums as combos) from `wadi2d schema`
  job/project_state.py       read/write wadi2d.project.json and QgsProject custom properties (layer ids by role, study folder)
  tasks/engine_task.py       QgsTask: runs an EngineProcess for one command, forwards events, cancel -> stop file -> grace -> kill
  tasks/study_task.py        runs an ARF study one engine process at a time; per-run progress; resumable
  tasks/export_task.py       export maps, downscale, load results
  ui/dock.py (+ .ui)         the single dock: a stepper of pages in order Terrain, Grid, Objects, Hydrology, Storm, Boundaries, Outputs, Run, Results
  ui/pages/*.py              one page per step: layer pickers by role, schema forms, validation badge
  ui/run_panel.py            progress bar, dt and mass-error sparkline, ETA, limiting cell with "zoom to", log tail, Stop, Resume, Open folder
  ui/results_panel.py        run list (from runs/*/manifest.json), load maxima, time slider (calls export per index, cached), design-point table
  ui/liveview.py             LiveView: adds live/depth.tif once with the depth style, auto-refresh (ReloadData) every live_view.every_seconds
  layers/styles/*.qml        depth, velocity, wse, hazard, arrival time; crest line, spillway, injection, design point symbology
  layers/loader.py           add run rasters under a group named by run_id with styles; never duplicates on reload
  processing/provider.py     algorithms: Build grid, Run job, Export, ARF study, HMS import (wrap the CLI; enable Model Designer and batch)
  resources/                 icons
  tests/                     pytest-qgis: job builder, tailer, contract equality, page validation
```

### 10.2 Building a job from layers

Roles (DEM for tables, display DEM, domain, crest lines, spillways, walls, burn lines, subbasins, injection points, design points, flux
lines, boundaries, Manning polygons, CN raster) are bound to layers in the Terrain/Objects/Hydrology pages and stored in the project. On
"Validate" or "Run" the builder: checks every vector layer's CRS and reprojects to the DEM CRS on export; writes `inputs/<role>.geojson`
(selected features only if the user ticks "selection"); requires file-backed rasters (a VRT or in-memory raster is exported first); copies
the HMS text files into `inputs/hms/`; fills the schema parts from the forms; writes `job.json`; runs `wadi2d validate`; shows errors on
the page they belong to. Defaults come from the engine's JSON Schema, never from the plugin (rule 2); the plugin stores only the user's
deviations.

### 10.3 The task that runs the subprocess, and attaching by folder

`EngineTask(QgsTask)` starts `wadi2d run job.json --out <run> --progress file` with `CREATE_NEW_PROCESS_GROUP` and no console window. The
task does not parse stdout for progress; the `ProgressTailer` (a QTimer on the GUI thread, 500 ms, incremental reads of `progress.jsonl`)
is the single source of events, so the same code attaches to a run that is already running (QGIS was restarted, or the run was started from
the CLI or on another PC on a shared folder) by opening its folder and reading `pid.json`. Cancel writes `stop`, waits up to 60 s for
`end`, then `kill()`. `finished()` loads results according to the exit code table. Stdout is kept only for the last lines on exit 1.

### 10.4 Installing next to the engine venv

- Plugin: zip from the GitHub release installed with the QGIS plugin manager into the profile's `python/plugins/wadi2d_qgis`. Dev: a
  junction created by `scripts/dev_link_plugin.ps1` and the Plugin Reloader.
- Engine: `%LOCALAPPDATA%\Wadi2D\engine\<version>\.venv` created by `scripts\install_engine.cmd` (shipped in the release): `uv venv --python
  3.12` (uv fetches a python-build-standalone interpreter when none is installed) then `uv pip install --require-hashes -r
  requirements\engine-gpu.txt` (or `engine-cpu.txt` on a machine without an NVIDIA GPU); writes `engine\current.json`. Downloads happen in
  a visible console, never silently from inside QGIS. The plugin's Engine page shows `doctor` output and offers "Create engine..." which
  opens that console; "Use existing" accepts any `wadi2d.exe`. Rejected: running the engine inside QGIS's Python (a kernel fault would take
  QGIS down, the GIL and GPU memory would be shared with the canvas) and a venv on QGIS's bundled interpreter (breaks on every QGIS upgrade).
- Handshake: on dock open `wadi2d version --json`; MAJOR contract mismatch disables Run with the message naming which side to update.

### 10.5 Live raster refresh

The engine updates `live/depth.tif` in place (uncompressed, downsampled by `live_view.downsample`, every `every_seconds` of wall time
after a device-to-host copy of one field) and writes `live/latest.json`. The plugin adds the layer once and sets
`setAutoRefreshMode(ReloadData)` with the same interval [Likely available in 3.34+; fallback: a QTimer calling
`dataProvider().reloadData()` and `triggerRepaint()`]. If an in-place update ever fails on a machine (file lock), the engine falls back to
numbered files `live/depth_<seq>.tif` named in `latest.json` and the plugin swaps the data source. The maxima rasters are updated in place
at every field output, so "max so far" is a layer the engineer can add during the run.

## 11. Memory, disk and time budgets

### 11.1 Device and host memory per cell (float32, K = 16, K_f = 12) [Certain, arithmetic]

| Array | Bytes/cell |
|---|---|
| h, qx, qy, two buffers (SSP-RK2 or Hancock) | 24 |
| zmin, dz_cell, manning | 12 |
| mask, rain_group, subbasin | 5 |
| loss state (two fields) | 8 |
| cell volume table (K) | 64 |
| two faces x (3 tables x K_f + zf_min + dz_face + crest + length factor + flags) | 2 x 161 = 322 |
| maxima (6 fields) | 24 |
| **Total** | **~459** |

| Case | Cells | Device | Host (run) | Host (table build, 2 bands in flight at 20 m) |
|---|---|---|---|---|
| Block 2 plain, mode (b), 10 m | 2 M | 0.9 GB | < 0.5 GB | ~1.5 GB |
| Block 2 full, 20 m | 1.5 M | 0.7 GB | < 0.5 GB | ~1.5 GB |
| Block 2 full, 10 m | 6 M | 2.8 GB | ~1 GB | ~1.5 GB (bands are half the height) |
| Ceiling on the RTX 5080 (14 GB usable) | ~28 M | 13 GB | | |
| Laptop, 6 GB card | ~11 M | | | |
| Laptop, CPU only, 16 GB RAM | ~20 M (host arrays replace device) | | | |

K = 8 and K_f = 8 (laptop profile) cut the per-cell cost to ~300 B. A uint16-normalised table option (v1.1) would halve the tables again
without a layout change (dtype lives in `layout.py`).

### 11.2 Disk

| Item | Formula | Block 2 full 20 m, 48 h | Block 2 full 10 m |
|---|---|---|---|
| Transient fields | cells x 4 B x fields x outputs x compression (~0.3 with dry tiles) [Guessing] | 1 field, 192 outputs: ~0.35 GB | ~1.4 GB |
| Maxima maps (COG) | cells x 4 B x 6 x ~0.5 | 18 MB | 72 MB |
| Checkpoints | 2 x cells x 36 B | 108 MB | 430 MB |
| Steps log | steps x 24 B | ~2 MB | ~4 MB |
| ARF study, maxima only | runs x cells x 24 B | 7 areas x 13 RPs: 3.3 GB | 13 GB |
| Downscaled depth at 0.5 m, whole block | 2.4 G px x 4 B (deflate ~0.4) | ~4 GB, only by explicit export with a clip | |

### 11.3 Time [Guessing, to be replaced by `bench` after stage 3]

From the measured ceiling (70 G cell-updates/s for a 5-point stencil, 827 GB/s), a full SWE step with table lookups moves ~100-150 B per
cell: 1-3 G cell-steps/s realistic on the RTX 5080. Block 2 full at 20 m: 1.5 M cells x 86,400 steps (dt ~2 s) ~ 1.3e11 cell-steps -> 1-2
min with half the tiles active. At 10 m: 6 M x 172,800 ~ 1e12 -> 6-15 min. CPU twin on 8 laptop cores: ~30-60 M cell-steps/s -> 40-70 min
for the 20 m case, 5-9 h for 10 m; the dock says so before Run. Table build on Block 2: 2.4 G DEM pixels decoded (LZW, 128 x 128 blocks)
with 8-16 workers, plus sorting 1,600 pixels per cell: 1-4 min; cache hit < 2 s.

## 12. Failure modes and restartability (what happens, what he sees, what he does)

| Failure | Detection | Exit | Engineer sees | Recovery |
|---|---|---|---|---|
| GPU out of memory | dry-run estimate; `cupy` allocation failure at start | 4 | bytes needed vs free | coarser dx, smaller domain, K = 8, cpu |
| Host out of memory in the table builder | `band_rows_in_flight` x band size estimate before starting | 4 | | lower `band_rows_in_flight` or workers |
| Disk full | free-space check at start and at every output (`shutil.disk_usage`) | 4 | | free space, `--resume` |
| NaN or dt collapse | `nan_check_every` reduction; `dt_min_patience` | 5 | the cell, its x,y, the dt history, "zoom to cell" | inspect the terrain there (a nodata hole, a vertical crest profile, a 1-pixel pit); fix the object or `tables.min_range`; rerun |
| Power cut, QGIS crash, kill | `pid.json` stale on next open | - | "run interrupted at t = ..." | Resume button (`--resume`) |
| User stop | stop file | 6 | partial maxima flagged `completed=false` | Resume |
| DEM moved or changed | manifest identity vs file | 3 (build) | | the run itself does not need the DEM (grid.h5 is linked in); rebuild if re-gridding |
| Unsupported HMS element or method | import report | 3 | element, method, line number | override it or model it in 2D |
| CRS mismatch | builder (plugin) and `validate` (engine) | 2/3 | the layer named | reproject (the plugin does it on export) |
| Plugin and engine versions drift | `version --json` handshake | 7 | which side to update | update |
| Path too long or non-ASCII trouble | `runfolder.py` checks; `doctor` reads `LongPathsEnabled` | warn / 3 | | shorter study path |
| TDR on a colleague's PC | `doctor` reads `TdrLevel/TdrDelay`; every launch < 100 ms by design | warn | | none needed; the design respects it |
| Laptop sleeps mid-run | `keep_awake` | - | | checkpoints |
| Two engines on one folder | `pid.json` alive | 9 | | attach |
| Mass error grows | `W_MASS` above 0.5% | warn | | report; the run continues |

## 13. Reproducibility

- A run folder contains everything that produced it: `config.resolved.json` with provenance, `kernels/` with the exact sources and
  `numerics.h` compiled, `basin.json`, `forcing.h5`, the linked `grid.h5`, `manifest.json` with input hashes and versions.
- Same folder, same engine version, same backend and GPU architecture: bitwise identical `results.h5` (section 7.5; a test runs a small case
  twice and compares checksums; resume-vs-uninterrupted is the second test).
- Across GPU architectures and between CPU and GPU: within tolerance (NVRTC codegen differs); the manifest names the architecture so a
  reviewer knows what to expect. The kernel cache key includes the NVRTC version and `sm_XX`.
- The engine venv is locked with hashes (`uv.lock`, `requirements/*.txt`); `doctor --json` is saved into the run folder as
  `environment.json` at start.
- The Block 2 inputs are client data and stay out of the repository; tests that need them read `WADI2D_BLOCK2` and skip otherwise.

## 14. Testing layers and CI

| Layer | What | Where it runs |
|---|---|---|
| Static | ruff (format + lint), mypy on `wadi2d/` and the plugin, `test_no_literals`, `test_schema_doc` (every field has unit, bounds, description), `test_contracts_equal` (engine vs plugin copy), `check_licences.py` (section 17) | CI, every push |
| Unit | config resolve and migrate; grid alignment and tiling; rasteriser (diagonal crest line: staircase watertight, length factor 1.41 at 45 degrees); cell and face tables on synthetic DEMs (plane, V-channel, step: analytic volumes and widths); HMS parser on committed hand-written fixtures; lumped methods on small references; storm builder; ARF interpolation; progress writer/reader; run folder; exit codes via subprocess | CI (cpu) |
| Solver analytic | lake at rest on random steep terrain (exact to 1e-6 m over 1,000 steps), Thacker (order of convergence), Ritter and Stoker dam-break, MacDonald steady friction; mass error < 1e-8 relative; on both backends | CI (cpu); local (gpu mark) |
| Parity and determinism | section 7.6; run-twice bitwise; resume bitwise | local (gpu); cpu part on CI |
| Oracle | table builder vs HEC-RAS geometry HDF tables on a shared square-cell test area (`ras-tables`), volume within 1%, conveyance within 2% | local (data mark) |
| Integration | Block 2 mode (a) vs HMS DSS peaks (3 RPs, 14 points, within 3%); a Block 2 wadi mode (b) at 40 m, 2 h, exit 0, files per contract, georeferencing of maps checked against the DEM; ARF study of 3 areas with resume after a kill | local (data, slow); nightly on a self-hosted runner if one exists |
| Plugin | pytest-qgis headless: job builder from memory layers (CRS reprojection, GeoJSON properties), tailer, contract equality, pages validate; manual checklist for the dock, live view and the time slider, filled before a release | CI (plugin mark, QGIS from conda or the OSGeo docker image on Linux); manual on Windows |
| Performance | `wadi2d bench` on the RTX 5080 recorded in `W1/benchmarks` and in each release note; a regression over 20% blocks the release | local |
| EA 2D benchmark tests | test 1, 2, 4, 5, 8A with published comparisons | local (slow) |

CI: GitHub Actions on `windows-latest` and `ubuntu-latest`, `uv sync --extra dev`, `pytest -m "not gpu and not data and not slow"`, plus a
weekly `slow` job on Linux. The GPU and data tests are run locally before a merge, and the PR template requires the pasted summary line of
`pytest -m "gpu or data"`. Pre-commit: ruff and the no-literals test.

## 15. Build order with the "done" criterion per stage

| Stage | Builds | Done when |
|---|---|---|
| 0 Skeleton | repo, pyproject, locked envs, CI, `contracts.py`, config schema with docs, empty-but-valid HDF5 writers/readers, run folder, progress, exit codes, CLI `version/doctor/schema/validate/run --dry-run`, the plugin skeleton with locator and handshake | `wadi2d run --dry-run` on a Block 2 job prints the estimate; CI green on both OSes; the dock opens in QGIS 3.44 and shows `doctor` |
| 1 Grid and tables | uniform grid, tiles, DEM access, cell and face tables, crest staircase, cache, `build-grid`, `ras-tables` | synthetic-DEM tables exact; crest watertight test; RAS oracle within tolerance; Block 2 full domain at 20 m builds in < 5 min with < 8 GB host memory; cache hit < 2 s |
| 2 Solver | layout, params, CPU twin, GPU kernels, stepper, checkpoints, stop/resume, maxima, live view, `run` | analytic suite on both backends; parity; run-twice and resume bitwise; NaN produces exit 5 with the cell; `bench` >= 1 G cell-steps/s on a 1 M-cell wet case [target]; stop and resume from the CLI |
| 3 Hydrology | HMS readers, object model, lumped engine, storm and ARF table, `forcing`, `hms-import` | Block 2 mode (a) within 3% of HMS at 14 points for 3 RPs; import report lists every element; `forcing.h5` per contract |
| 4 Rain-on-grid and coupling | rain groups, masks, injection, CN on cells, boundaries, spillway faces, series and lines | a Block 2 wadi at 10 m runs mode (b) end to end from the CLI, mass error < 0.1%, maps open in QGIS in the right place, live view refreshes |
| 5 Plugin | pages, job builder, tasks, tailer, results panel, styles, processing provider, installer script | he builds, runs, stops, resumes and loads a Block 2 run from QGIS without editing JSON; installed from the zip plus `install_engine.cmd` on the laptop (cpu backend) by following the README |
| 6 ARF | study expansion, serial runner, resume, design-point table, composite | 7 areas x 1 RP on Block 2 at 20 m; the design-point peaks equal the single-run peaks at matching areas; study resumes after a kill; composite map written with provenance |
| 7 Validation and release | EA tests, HEC-RAS head-to-head on one wadi, tutorial, licence audit, release v1.0.0 (plugin zip, wheel, lock files, install script) | a colleague installs from the release notes alone; the audit file lists every dependency with its licence; the W1 README records the benchmarks |

## 16. Licence audit list (against GPL-3.0-or-later, the licence in `LICENSE`)

| Component | Licence | Compatible | Action |
|---|---|---|---|
| numpy, scipy, h5py, rasterio, shapely | BSD-3 | yes | - |
| numba, llvmlite | BSD-2 | yes | - |
| HDF5 library (in the h5py wheel) | BSD-style (HDF Group) | yes | - |
| GDAL (in the rasterio wheel), PROJ, pyproj | MIT | yes | - |
| GEOS (in the shapely wheel) | LGPL-2.1 | yes (dynamic) | - |
| pydantic, pydantic-core | MIT | yes | - |
| CuPy, fastrlock | MIT | yes | - |
| NVIDIA wheels (cuda-runtime, nvrtc, nvjitlink, cublas, ...) and the driver | NVIDIA EULA, proprietary | not GPL; we never redistribute them: the user's `uv pip install` fetches them from PyPI; the `.cu` sources are compiled on the user's machine | **decide in the design note**: GPL-3.0 plus an explicit additional permission for linking with the CUDA runtime and NVRTC (the usual "GPL linking exception" wording), so no installer can ever be accused of distributing a combined work; never bundle the wheels |
| hecdss (HEC) | **not stated in the package metadata** [Certain, checked today]; HEC-DSS is a US Government work with its own terms [Likely] | to verify | read the repository licence file; if unclear, isolate behind `hms/dss.py` so it can be swapped for a DSS reader of our own or made an optional extra |
| rashdf (HEC/FEMA) | MIT [Likely] | yes | verify on adoption; test-only dependency |
| QGIS, PyQGIS | GPL-2.0-or-later | yes (the plugin is GPL-3.0-or-later; the combination is GPL-3) | the plugin repository requires a GPL-compatible licence; met |
| PyQt5 / Qt | GPL-3 (PyQt) / LGPL-3 (Qt) | yes | - |
| uv, ruff, mypy, pytest, pytest-qgis, mkdocs, mkdocs-material | MIT / Apache-2.0 / BSD | tooling only | - |
| GRASS, SAGA (called through QGIS processing for the accumulation grid) | GPL-2+ / GPL-2+ and LGPL | yes, separate processes | - |
| QGIS icons, our icons | GPL / ours | yes | - |
| Block 2 terrain, HMS model, shapefiles | client data, not ours | no | never in the repository; `.gitignore` already blocks rasters and DSS; add the HMS text files (`*.basin *.met *.control *.run *.pdata *.gage *.hms`) under a `data/` ignore rule and keep synthetic fixtures |
| HEC-RAS example projects (geometry HDF) | US Government work | yes | test fixtures only, cited |
| Published methods (SCS, Clark, Muskingum-Cunge, HLLC, Kurganov-Petrova, EA tests) | citations, not licences | - | the method note cites them |
| Contributions | - | - | DCO sign-off (`Signed-off-by`) rather than a CLA, unless a dual licence is ever sold |

`scripts/check_licences.py` reads the lock file and `pip-licenses`-style metadata, fails CI on an unknown or incompatible licence, and writes
`docs/licences.md`.

## 17. Where the seed will hurt in daily use

1. **`grid.h5` built per run.** The seed says "builds or loads grid.h5"; without a content-addressed cache every ARF run and every re-run
   pays 1-4 min on the 27 GB DEM. Section 1.2 fixes it.
2. **HDF5 as the plugin's data path.** The seed's table lists `results.h5 -> plugin`; QGIS's Python has no h5py [Certain] and a tile-major
   dataset is not a raster. The plugin reads GeoTIFF, CSV, JSON only; the engine exports.
3. **Dense arrays over the bounding box.** A loosely drawn domain on Block 2 at 10 m is 42 M cells; compaction over domain tiles is
   required, not an optimisation.
4. **The lumped engine inside the time loop.** Coupling is one-way; running it on the simulation step complicates resume, mode (a) tests
   and the forcing record for nothing. Precompute.
5. **Stdout as the progress channel.** A plugin that owns the pipe cannot re-attach after a QGIS restart and a job runner cannot share the
   protocol. The file is primary; stdout mirrors.
6. **Live view at full resolution with file replacement.** `os.replace` over a file QGIS holds open fails on Windows; in-place updates of a
   preallocated, downsampled, uncompressed GeoTIFF work and cost nothing.
7. **Persistent-kernel temptations.** Not on a display GPU with TDR on (a colleague's default 2 s). Every launch short; `doctor` reads the
   keys.
8. **Vector inputs unspecified.** GeoJSON in the DEM CRS keeps OGR out of the engine and makes the run folder self-contained.
9. **No dry-run basis.** An estimate needs a measured rate per machine (`bench`) and calibration from past runs; otherwise the dock cannot
   tell a laptop user that a 10 m run is nine hours.
10. **Long and non-ASCII paths** (his folder names have spaces; `LongPathsEnabled=0` [Certain]): argument lists everywhere, short run ids,
    an explicit check.

## Changes to the seed

1. **Content-addressed grid cache** (`cache/grids/<hash>/grid.h5`, hard-linked into runs) instead of build-or-load per run. Reason: 1-4
   min per run on the 27 GB DEM, paid once instead of 100 times per ARF study; the run folder stays self-contained.
2. **The plugin consumes GeoTIFF, CSV, GeoJSON and JSON only; `results.h5` is engine-exclusive and reached through `wadi2d export`.**
   Reason: QGIS's Python has no h5py [Certain]; the GDAL HDF5 driver cannot interpret tile-major arrays; file locking while the engine writes.
3. **Arrays allocated over domain tiles (compact index), never over the bounding box; the active-wet list is a subset for launching.**
   Reason: 42 M-cell bounding box on Block 2 at 10 m; also the shape the quadtree and domain splitting need.
4. **Lumped hydrology runs before the 2D solve (`wadi2d forcing`), one-way; mode (a) is `forcing --mode a`.** Reason: no feedback exists;
   simpler stepper, trivial resume, mode (a) testable on CI without a GPU, and `forcing.h5` becomes the complete forcing record.
5. **`progress.jsonl` is the primary channel; the plugin tails the file and attaches to runs by folder (`pid.json`); stdout mirrors.**
   Reason: re-attach after a QGIS restart, runs started from the CLI or on another PC, and the job-runner door of decision 16.
6. **Live view and maxima rasters are preallocated, downsampled (live) GeoTIFFs updated in place; QGIS auto-refresh with ReloadData.**
   Reason: `os.replace` fails on a file QGIS holds open on Windows; in-place updates work and are cheap.
7. **Vector inputs are GeoJSON in the DEM CRS inside `inputs/`, read with json + shapely; no OGR in the engine.** Reason: the seed is
   silent; this keeps the engine's dependency list to wheels with known licences and makes the run folder portable.
8. **Face ownership convention (west and north faces per cell) with an inactive padding ring; GDAL row direction everywhere.** Reason: the
   seed's "x faces and y faces as separate arrays" leaves ownership open; a fixed convention prevents the duplicated-face bugs and the
   array flips between DEM, solver and GeoTIFF.
9. **Per-cell uniform table spacing (`dz_cell`, `dz_face`) with implicit breakpoints instead of stored level breakpoints.** Reason: half
   the table memory (322 vs ~450 B per cell for faces) and a 4-step binary search in shared memory; the dtype and K live in `layout.py` so a
   uint16 option is a config change.
10. **`numerics.h` generated from a frozen `KernelParams` that also feeds the Numba twins; a no-literal test on the kernel sources.**
    Reason: rule 2 enforced mechanically, one object for both backends.
11. **A dry-run with a measured basis**: `wadi2d bench` per machine and backend, calibration from past manifests, a range not a number,
    and a hard refusal above 90% of free device memory or free disk. Reason: the laptop user must be told before, not after.
12. **Checkpoints and resume as a first-class part of the protocol** (rotating checkpoint files, bitwise resume as a test, exit 6/7/9
    semantics). Reason: 10-60 min runs on a shared workstation get interrupted; the seed only mentions a clean stop.
13. **Exit code table extended** (2 invalid, 3 input, 4 resource, 5 numerical with the cell, 6 stopped, 7 contract, 8 backend, 9 folder busy).
    Reason: the dock reacts per code; the engineer gets a cell coordinate instead of a traceback.
14. **Installation story**: engine venv under `%LOCALAPPDATA%\Wadi2D\engine\<version>` built by `uv` with hashed lock files; plugin from
    the QGIS plugin manager; handshake on contract MAJOR. Reason: the seed has no install path; a colleague's laptop is the test.
15. **ARF study as a `study.json` with per-run status, serial on one GPU, resumable, hard-linked grid.** Reason: 100 independent jobs
    need a manifest, not a loop.
16. **Licence note on the NVIDIA runtime**: never bundle the wheels; propose a GPL linking exception in the design note; verify hecdss.
    Reason: the audit found the one component that is not GPL-compatible and the one with no stated licence.
17. **Engine CLI startup split**: light commands (`version`, `doctor`, `schema`, `validate`) import nothing heavy. Reason: the dock calls
    them on every open and every validate; a 1 s cupy import on each would make the UI feel broken.

## Risks

1. **Two hand-written kernel sets (CUDA C++ and Numba) drift** and a bug fixed in one is not fixed in the other. Mitigation: the
   section-numbering test, single-step parity on random states in CI (cpu side) and locally (gpu), goldens per backend, and a stage-2
   benchmark of a **single-source alternative**: `numba.cuda` kernels (NVIDIA's `numba-cuda` compiles through NVRTC without a toolkit
   [Likely]) written once and run on both backends. If within 20% of the NVRTC/CuPy version, switch; the layout and the params object are
   the same either way, so the switch is contained in `solver/gpu`.
2. **The table builder on the 27 GB LZW file is slower than estimated** (single-threaded LZW decode, 128 x 128 blocks, no overviews).
   Mitigation: band-parallel workers, `GDAL_CACHEMAX`, the content cache, and a documented one-off conversion of the DEM to a ZSTD-tiled
   COG in our cache folder if decode dominates (never in his folder).
3. **Float32 table interpolation on steep cells produces spurious free-surface gradients** (well-balancing with sub-grid is the numerics
   panel's problem, but the layout decides what precision the kernel can reach). Mitigation: the Sterbenz ordering in 7.3, the lake-at-rest
   test on random steep terrain at 1,500 m, and the option of float64 only inside the table lookup (register-local, rare) if the test fails.
4. **GPU memory on 6-8 GB laptops or shared workstations** refuses the 10 m full-catchment case. Mitigation: dry-run refusal with advice,
   the K = 8 laptop profile, `max_cells`, and the tile layout that makes host-device streaming of tiles a version-2 option.
5. **In-place GeoTIFF updates while QGIS reads them** behave differently on some machines (antivirus, network drives). Mitigation: the
   numbered-file fallback in 10.5, selected automatically on the first failure.
6. **HMS file dialects** (4.x versions, US units, methods we do not implement, DSS paired data quirks) stop the import on real projects.
   Mitigation: the import report lists everything instead of failing on the first; overrides per element; fixtures from Block 2 and from
   HMS example projects; `hms/parse.py` keeps line numbers.
7. **hecdss licence or Windows binary trouble** (its native DLL, HDF5 2.0 in the same process). Mitigation: isolate behind `hms/dss.py`,
   optional extra, paired data also accepted as CSV/JSON exported from HEC-DSSVue.
8. **Reproducibility promises break across NVRTC or driver updates.** Mitigation: the manifest records them; the claim is scoped to "same
   engine, backend and architecture"; goldens are tolerance-based across versions.
9. **The plugin grows into the engine** (logic in pages, defaults duplicated). Mitigation: the plugin has no numbers (forms from the
   schema, defaults from the engine), the contract-equality test, and `validate` as the only judge.
10. **QGIS API changes** (auto-refresh mode, task manager behaviour) between 3.34 LTR and 3.44. Mitigation: `qgisMinimumVersion=3.34`,
    the QTimer fallback, the plugin tests on CI against the LTR image.
11. **Windows process handling** (CTRL_BREAK, no console window, child outliving QGIS) misbehaves on a colleague's machine. Mitigation: the
    stop file is the primary mechanism and does not depend on signals; `pid.json` plus attach-by-folder means an orphaned engine is a
    feature, not a leak.
12. **Scope creep through the registries** (every method "a new file") before the solver is validated. Mitigation: stage gates in section
    15; no method beyond SCS CN, SCS UH, Clark, Muskingum-Cunge, lag, recession until stage 7 is done.
