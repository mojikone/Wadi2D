# Architecture panel: the simplest version 1 that is correct and complete

Panel angle: fewest moving parts, every module justified by a version-1 feature (decision 17), an explicit list of what the seed
over-engineers. Inputs: the project `CLAUDE.md` (decisions 2, 3, 4, 10, 16, 17, 18; the engineering rules), `design_seed_architecture.md`,
`toolchain_check.md`. Written 2026-10-29. A proposal for the design note, not a decision.

**Verified on this machine today, before writing** (the proposal leans on each; all [Certain] unless tagged):

| Check | Result | Consequence |
|---|---|---|
| A numpy structured record (`np.void`) passed to a Numba `@njit` function, fields read by attribute | works (numba 0.65.1, 0.6 s compile) | the CPU twin takes the numerics as one record |
| The same record copied into a `__constant__ Params P` of a CuPy `RawModule` via `get_global("P").copy_from_host`; a kernel reports `sizeof` and field offsets | values read back; sizeof 24 and offsets 0,4,8,12,16,20 match numpy's | numerics reach the GPU kernels with no literal and no generated header of values; one struct definition generated from one dtype |
| NVRTC has no standard headers (`offsetof` undefined) | yes | kernels use no `<...>` includes; the few helpers we need are in `common.cuh` |
| HMS 4.12 text files (`.basin`, `.met`, `.control`, `.pdata`, `.hms`, `.run`) | one grammar: `Kind: Name` / indented `Key: Value` / `End:` | one parser, one mapper per file kind |
| `Basin_1.sqlite` of the Block 2 model | OGR SQLite, `geometry_format = WKB`, EPSG:32640; `subbasin2d` (18 polygons with `area_sqkm`), `outlet` (11 points), `reach2d` (20 lines); `shapely.wkb.loads` reads the blobs directly | subbasin polygons and outlets come from the HMS project with stdlib `sqlite3` + shapely; no user layer, no new dependency |
| `hecdss 0.1.29` on copies of the Block 2 DSS files | reads `PairedData` (ARF table: 12 areas 1-2000 km², factors 0.999-0.606; the percent-graph storm pattern) and `RegularTimeSeries` (FLOW, m³/s, 300 s, 577 values) | the ARF table and the pattern live in the project DSS, not in the `.met` text: the DSS reader is on the run path, not only in tests |
| The DSS library logs to the C-level stdout; Python's `redirect_stdout` captures none of it; an `os.dup2` of fd 1 silences it | confirmed | **stdout is not the progress protocol**; the progress file is |
| HMS results: `FM_*.dss` hold only PRECIP series; the depth-area runs `DA_<rp>_B1.dss` hold FLOW, PRECIP-EXCESS, PRECIP-LOSS ... per element, one series per analysis point: `//J1/FLOW/31Dec1999-02Jan2000/5Minute/DAA:DA 100yr B1>J1/` | 1151 condensed records per return period | the mode (a) oracle is the DAA file: the flow at point X in the run whose storm area is X's drainage area, exactly decision 9's lookup |
| `numba` in the project venv | importable, but from the **user** site-packages (`%APPDATA%\Python\Python312`), not from `.venv`; `python -I -c "import numba"` fails | the venv must own every dependency; a test enforces it |
| QGIS 3.44.8 LTR | `apps\Qt5`, `apps\Python312`; profile plugins at `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins` | PyQt5 through `qgis.PyQt`; the install path is known |
| `hecdss` opens files in "single-user advisory access mode" (read-write handle, 0 physical writes observed) | - | the reader opens a temporary copy, never his file |

## 0. The architecture in one paragraph

One Python package `wadi2d` in one venv, run as one process per job. Inside it: **one time loop** (`stepper.py`), **three kernels**
(`flux`, `update`, `dt_reduce`) written once in CUDA C++ and once in Numba, both reading the same arrays in the same layout and the same
`Params` record; **one expensive file** (`grid.h5`: grid, sub-grid tables, terrain objects already applied, Manning and CN per cell), built
once per terrain and shared by every run of a study; **one job file** (`job.json`, the whole configuration, validated by one pydantic
schema); **one results file** per run (`results.h5`) plus GeoTIFFs and CSVs exported from it; **one progress file** (`progress.jsonl`)
that the QGIS plugin tails. The solver knows nothing of storms, hydrology, HMS or GIS: it sees a rain-rate array, a list of inflow cells
and the face types. The plugin knows nothing of the engine's internals: it writes `job.json`, starts a process, tails a file, loads
rasters. Crest lines, walls and burn lines exist only in the table builder; the solver sees faces whose wet width is zero below a level.
Five registries with one mechanism give the extension points the engineering rules ask for. ARF is a folder of independent jobs.

## 1. What "simplest" means here, and what the seed over-engineers

Simplest means the fewest **concepts and contracts**: kernels, file formats, processes, threads, registries, code generators, options.
It does not mean the fewest files: a 2,000-line module is not simpler than six 300-line ones (engineering rule 1). Every module below
names the version-1 feature that justifies it; a module without one is out.

The seed over-engineers in these places (each is argued in "Changes to the seed", numbered C1-C16):

1. Eight kernels where three carry the same physics (C1).
2. Crest logic inside the solver, when the table builder can express a crest as a face that opens at a level (C2).
3. Numerics "baked in as a generated header" with a compile cache of our own (C3).
4. A third data file, `forcing.h5`, for data that is cheap to derive at run start (C4).
5. Boundaries stored in the grid file, which ties one grid to one set of what-ifs (C5).
6. Tile-major array storage, which buys nothing on the GPU and costs every raster library its direct access (C6).
7. Seven registries, two of them with one or two fixed entries and no planned third (C7).
8. Separate readers per HMS file kind, two of them (`.run`, `.gage`) unused in version 1 (C8).
9. A `QgsTask` to run a subprocess that is already off the main thread (C9).
10. A shipped `validation/` package and an mkdocs site, against the version-1 scope line "a GitHub release, one tutorial, a licence file" (C10).
11. Options that decisions already closed: a unit system, a precision switch (C11).
12. Three packages (`engine/`, `io/`, `arf/`) for what is five modules (C12).
13. stdout as the live protocol (C13, found today: a dependency writes to it).

And it under-specifies three things version 1 cannot do without: restart (C14), the elevation datum inside float32 kernels (C15), and
the table row layout and lookup rule (C16).

## 2. Repository and module map

```
pyproject.toml            package "wadi2d" (src layout not used: the package is at the root); extras: gpu, dev, docs; entry point "wadi2d"
uv.lock                   pinned environment (uv 0.10.9 is on the machine)
LICENSE                   GPL-3.0-or-later (decision 15, pending the design note)
LICENSES.md               the dependency audit (section 13), checked by a test
README.md, CLAUDE.md      live documents (existing)
examples/                 plane_rain.json, dam_break.json, block2_wadi.json (paths as placeholders)
wadi2d/
  __init__.py             __version__; nothing else
  registry.py             class Registry
  config/
    schema.py             RunConfig and its parts (pydantic v2); FORMAT_VERSION; every field: type, unit, default, bounds, description
    resolve.py            load(path) -> RunConfig; resolve(cfg, job_dir) -> RunConfig (defaults filled, paths absolute, HMS expanded); dump_resolved()
    migrate.py            migrate(dict) -> dict: pure functions per format version step
    provenance.py         provenance() -> dict: versions, GPU, driver, git commit, host, time, input hashes
  grid/
    geometry.py           GridGeometry: origin, dx, padded nx/ny, tiles, cell <-> xy, raster transform, rasterize(geom) -> mask
    build.py              build_grid(cfg) -> grid.h5 (the only function that touches DEM + objects + tables together)
  terrain/
    dem.py                DEM(path): read_window(bounds, stride) -> (float64 array, transform); pixel alignment checks
    objects.py            TERRAIN_OBJECT registry; CrestLine, Wall, BurnLine, Spillway: edit_dem(window) and/or mark_faces(face_lattice)
    crest.py              rasterize_line_to_faces(line, geometry) -> (face ids, z at crossing, length factor)
  tables/
    cells.py              cell_tables(dem_window, dx, rows) -> zmin, dz, hbar[rows]
    faces.py              face_tables(dem_window, geometry, rows, z_face_override) -> zf_l, zf_r, dzf, width[rows], area[rows]
  solver/
    layout.py             ARRAYS (name, dtype, shape rule, bytes/cell), PARAMS_DTYPE, FACE enum, LIMITER/INTEGRATOR codes, pad_to_tiles(), cell_index()
    params.py             params_record(numerics, physics, geometry) -> np.void of PARAMS_DTYPE; c_struct(PARAMS_DTYPE) -> str
    state.py              State: allocates every array of ARRAYS on a backend from a GridFile; active-tile list; to_host()
    backend.py            Backend protocol; select_backend("auto"|"gpu"|"cpu") -> Backend
    stepper.py            Stepper(state, params, backend): advance(t_end, rain_rate, inflows, callbacks) -> the only time loop
    gpu/
      loader.py           compile(sources) -> RawModule (CuPy's own disk cache); set_params(module, record)
      backend.py          GpuBackend: the three launches, scatter_add, reductions, download
      kernels/
        common.cuh        cell_index(), table lookup helpers, limiter(), hllc(), friction_implicit(): device functions only
        flux.cu           kernel flux(...)
        update.cu         kernel update(...)
        reduce.cu         kernel dt_reduce(...)
    cpu/
      backend.py          CpuBackend (Numba, prange over active tiles)
      kernels.py          flux(), update(), dt_reduce() as @njit functions mirroring the .cu files line for line; same helper names
  hydrology/
    model.py              Basin, Subbasin, Reach, Junction (pydantic); LossSpec, TransformSpec, RoutingSpec envelopes
    losses.py             LOSS registry: ScsCn
    transforms.py         TRANSFORM registry: ScsUnitHydrograph, Clark
    routing.py            ROUTING registry: MuskingumCunge, Lag
    network.py            LumpedEngine(basin, hyetographs, dt): topological order; step(t0, t1) -> {element: Q}; state for checkpoints
  hms/
    format.py             parse(text) -> [Block(kind, name, fields: dict[str, str])]
    project.py            .hms -> ProjectIndex (met files, dss file)
    basin.py              .basin -> Basin
    basin_gis.py          Basin_?.sqlite -> polygons, outlets, reach lines (sqlite3 + shapely, EPSG from spatial_ref_sys)
    met.py                .met -> FrequencyStormSpec (+ per-subbasin depth overrides)
    control.py            .control -> t_start, t_end, step_s
    pdata.py              .pdata -> {table name: (type, dss pathname)}
    dss.py                paired_data(path, pathname), time_series(path, pathname) via hecdss on a temp copy, fd 1 silenced
  storm/
    base.py               STORM registry; StormSource protocol: hyetograph(t0, t1) and rate_field(t0, t1, geometry) -> (ny, nx) m/s
    uniform.py            UniformHyetograph
    frequency.py          FrequencyStorm (HMS hypothetical storm, specified pattern, ARF at storm area)
    geotiff_stack.py      GeoTiffStack (bands or files with times, resampled to the grid)
    arf_table.py          ArfTable: factor(area_km2) (linear in log area)
  forcing.py              Forcing(cfg, grid): rain groups and masks, injection cells and weights, boundary faces, point/line probes
  io/
    grid_h5.py            write_grid(GridFile), read_grid(path) -> GridFile; stale check by hash
    results_h5.py         ResultsWriter (maps, maxima, series, hydrology, forcing, log), ResultsReader
    checkpoint.py         save(state, lumped, t, step), load()
    geotiff.py            write_tif(array, geometry, path, nodata, tags), atomic replace
    progress.py           ProgressEmitter: events to progress.jsonl (and a one-line human echo to stderr)
  run.py                  run_job(job, out, backend, resume) -> exit code; dry_run(job, out) -> estimate dict
  arf.py                  plan_areas(), write_jobs(), run_all(), design_point_table(), composite_map()
  export.py               results.h5 -> GeoTIFFs and CSVs (also the CLI "export")
  doctor.py               environment report and the per-cell-step benchmark used by dry-run estimates
  cli.py                  argparse: schema, build-grid, run, arf, export, hms-import, info, doctor, migrate
tests/                    section 11
plugin/wadi2d_qgis/       section 10
tools/                    install_plugin.py, package_plugin.py, bench_step.py (writes W1/benchmarks)
docs/                     tutorial.md, formats.md, method.md (plain markdown; no site build in version 1)
W1 research and design note/
```

Public interface per module, one line each (the declared interfaces of engineering rule 1):

| Module | One job | Public interface |
|---|---|---|
| `registry.py` | name -> class maps | `Registry(kind).register(name)`, `.get(name)`, `.names()` |
| `config/schema.py` | the single source of truth for every parameter | `RunConfig` and part models; `FORMAT_VERSION = "1.0"` |
| `config/resolve.py` | file -> validated, filled, absolute config | `load(path)`, `resolve(cfg, job_dir)`, `dump_resolved(cfg, path)`, `json_schema()` |
| `config/migrate.py` | old job dicts -> current | `migrate(d: dict) -> dict` |
| `config/provenance.py` | what produced a run | `provenance(inputs: list[Path]) -> dict` |
| `grid/geometry.py` | the grid's arithmetic | `GridGeometry(x_ul, y_ul, dx, ntx, nty, crs_wkt)`: `.nx .ny .transform .cell_of(x, y) .xy_of(j, i) .rasterize(geoms, all_touched)` |
| `grid/build.py` | DEM + objects + tables -> grid.h5 | `build_grid(cfg: RunConfig, out: Path, progress) -> Path` |
| `terrain/dem.py` | windowed DEM access | `DEM(path).read_window(bounds, stride=1) -> (z: float64[rows, cols], transform)`, `.pixel`, `.crs_wkt`, `.nodata` |
| `terrain/objects.py` | vector edits of terrain | `TerrainObject.edit_dem(z, transform) -> z`, `.mark_faces(lattice) -> None` |
| `terrain/crest.py` | line -> staircase of faces | `rasterize_line_to_faces(line, geometry) -> list[(axis, j, i, z_cross, length_factor)]` |
| `tables/cells.py` | cell storage curves | `cell_tables(z, dx_pixels, rows) -> (zmin, dz, hbar[rows])` |
| `tables/faces.py` | face conveyance curves | `face_tables(z, geometry, rows, z_face_override) -> (zf_l, zf_r, dzf, width[rows], area[rows])` |
| `solver/layout.py` | the array contract shared by both backends and the HDF5 writer | `ARRAYS`, `PARAMS_DTYPE`, `FACE`, `cell_index(tile, ty, tx, ntx)`, `pad_to_tiles(shape)` |
| `solver/params.py` | config -> kernel record | `params_record(cfg, geometry) -> np.void`, `c_struct(dtype) -> str` |
| `solver/state.py` | device arrays | `State.allocate(gridfile, backend)`, `.active_tiles`, `.rebuild_active()`, `.to_host(names)` |
| `solver/backend.py` | the compute interface | `Backend.flux(state, params, stage)`, `.update(...)`, `.dt(...) -> float`, `.scatter_add(arr, idx, w, value)`, `.download(arr)`, `.upload(arr, host)` |
| `solver/stepper.py` | the time loop | `Stepper.advance(t_end, rain_rate, inflows, on_step, on_output) -> t` |
| `solver/gpu/loader.py` | source -> module | `compile(sources: list[Path], defines) -> RawModule`, `set_params(module, record)` |
| `hydrology/model.py` | the basin as data | `Basin(subbasins, reaches, junctions)`, `.topological_order()` |
| `hydrology/network.py` | lumped runoff and routing | `LumpedEngine(basin, hyetographs, step_s).step(t0, t1) -> dict[str, float]`, `.state()`, `.restore(state)` |
| `hms/format.py` | the HMS grammar | `parse(text) -> list[Block]` |
| `hms/*.py` mappers | HMS file -> our objects | `read_basin(path) -> Basin`, `read_met(path) -> FrequencyStormSpec`, `read_control(path) -> Control`, `read_pdata(path) -> dict`, `read_basin_gis(path) -> BasinGis` |
| `hms/dss.py` | DSS access | `paired_data(path, pathname) -> (x, y)`, `time_series(path, pathname) -> (times, values, units)` |
| `storm/base.py` | rain as a function of time | `StormSource.hyetograph(t0, t1) -> float` (m), `.rate_field(t0, t1, geometry) -> ndarray` (m/s) |
| `forcing.py` | config + grid -> what the solver consumes | `Forcing(cfg, gridfile)`: `.rain_rate(t0, t1)`, `.inflow_targets`, `.face_types`, `.probes` |
| `io/grid_h5.py` | the grid contract | `write_grid(GridFile, path)`, `read_grid(path) -> GridFile`, `grid_hash(cfg) -> str` |
| `io/results_h5.py` | the results contract | `ResultsWriter(path, gridfile, cfg)`: `.map(t, arrays)`, `.series(t, values)`, `.maxima(arrays)`, `.log(record)`, `.close(status)` |
| `io/checkpoint.py` | restart | `save(path, state, lumped, t, step)`, `load(path) -> (host arrays, lumped state, t, step)` |
| `io/geotiff.py` | rasters out | `write_tif(array, geometry, path, nodata, tags, compress)` |
| `io/progress.py` | events out | `ProgressEmitter(path).emit(ev, **fields)` |
| `run.py` | wire everything for one job | `run_job(job, out, backend, resume) -> int`, `dry_run(job, out) -> dict` |
| `arf.py` | N jobs and the lookup | `plan_areas(cfg) -> list[float]`, `write_jobs(cfg, out) -> list[Path]`, `run_all(jobs)`, `design_point_table(out)`, `composite_map(out, accumulation)` |
| `cli.py` | the process protocol | `main(argv) -> int` |

Dependency direction (enforced by a test that imports each module in isolation): `config` <- everything; `solver` imports only
`config`, `io/grid_h5` types and numpy/cupy/numba; `hydrology` imports `config` only; `hms` imports `hydrology.model` and `storm` specs;
`forcing` imports `storm`, `hydrology`, `grid`; `run.py` is the only module that imports all of them. The plugin imports none.

## 3. Configuration schema

One `RunConfig` in `config/schema.py`, pydantic v2, `extra="forbid"` everywhere (a misspelt key is an error, not a silent default).
Units are SI throughout and fixed; a field's unit is in its name or its description, never a separate setting (C11). Every numeric
field carries `ge`/`le` bounds; every field a default except the ones marked required. JSON Schema is exported by `wadi2d schema`
and is what the plugin reads for defaults and tooltips.

### 3.1 Parts and fields

`project`

| Field | Type | Unit | Default | Bounds / note |
|---|---|---|---|---|
| `format_version` | str | - | "1.0" | must equal a version `migrate.py` knows |
| `name` | str | - | required | run name, used in output tags |
| `description` | str | - | "" | |

`grid`

| Field | Type | Unit | Default | Bounds / note |
|---|---|---|---|---|
| `domain` | path or GeoJSON Polygon | - | required | polygon file (GPKG, SHP, GeoJSON) or inline; any CRS, reprojected to the DEM CRS |
| `dx` | float | m | 10.0 | [0.5, 1000]; must be an integer multiple of the DEM pixel; the grid origin is snapped to DEM pixel corners |
| `tile` | int | cells | 32 | {32} in version 1 (the kernel launch geometry assumes it; 16 and 64 are a layout.py change) |
| `path` | path | - | "./grid.h5" | relative to the job file; built if missing or stale |

`terrain`

| Field | Type | Unit | Default | Bounds / note |
|---|---|---|---|---|
| `dem` | path | - | required | GeoTIFF; its CRS is the project CRS (no `project.crs` field) |
| `band` | int | - | 1 | >= 1 |
| `nodata` | enum | - | "inactive" | `inactive` (cells touching nodata are inactive) or `fill_nearest` |
| `objects` | list[TerrainObject] | - | [] | discriminated on `kind` |
| `manning.source` | enum | - | "constant" | `constant`, `raster`, `polygons` |
| `manning.value` | float | s m^-1/3 | 0.035 | [0.008, 0.5] |
| `manning.path`, `manning.field` | path, str | - | null | raster or polygon layer with a field |
| `cn.source` | enum | - | "none" | `none`, `constant`, `raster`, `polygons`; needed when any subbasin is `grid` with SCS losses |
| `cn.value` | float | - | 75 | [30, 100] |
| `cn.path`, `cn.field` | path, str | - | null | |

`TerrainObject` kinds (the `TERRAIN_OBJECT` registry; each class owns its parameter model):

| Kind | Fields | Unit | Default | Bounds / note |
|---|---|---|---|---|
| `crest_line` | `geometry` (LineString, Z or 2D), `z` (`"geometry"`, `"constant"`, `"field"`), `z_value`, `length_factor` (`"auto"` or float) | m | z "geometry"; length_factor "auto" | float factor in [0.5, 1.0]; auto = segment length / staircase length per crossed face |
| `wall` | `geometry` | - | - | a crest at +infinity: every crossed face stays closed |
| `burn_line` | `geometry`, `depth` or `z` profile, `width` | m | width = 2 DEM pixels | depth [0, 30]; width [1 pixel, 100 m] |
| `spillway` | `geometry` (short line across the faces), `z_crest`, `coefficient`, `length`, `submergence` | m, -, m | coefficient 2.1, submergence "villemonte" | coefficient [1.4, 2.3] SI; length [0.1, 2000]; `none` or `villemonte` |

`tables`

| Field | Type | Unit | Default | Bounds / note |
|---|---|---|---|---|
| `rows` | int | - | 16 | [4, 64]; 16 rows x 4 B = one 64 B line per cell or face table |
| `dem_stride` | int | pixels | 1 | [1, 8]; subsample the DEM for quick tests (stride 4 on a 0.5 m DEM = 2 m) |
| `min_dz` | float | m | 0.01 | [0.001, 1]; row spacing floor for flat cells |

`numerics` (every field here is a `Params` field, section 3.2)

| Field | Type | Unit | Default | Bounds / note |
|---|---|---|---|---|
| `cfl` | float | - | 0.5 | [0.05, 0.95] |
| `limiter` | enum | - | "minmod" | `none`, `minmod`, `vanleer`, `vanalbada` (numerics panel sets the default) |
| `integrator` | enum | - | "rk2" | `euler`, `rk2` (SSP-RK2 reuses the two kernels; MUSCL-Hancock would add a predictor kernel, deferred) |
| `h_wet` | float | m | 1e-3 | [1e-6, 0.1]; below it a cell exchanges no momentum flux |
| `h_cfl` | float | m | 1e-2 | [h_wet, 1.0]; cells below it are excluded from the time-step search (decision 18 c) |
| `u_max` | float | m/s | 20 | [1, 100]; velocity cap, counted and reported |
| `dt_max` | float | s | 60 | [1e-3, 3600] |
| `dt_min` | float | s | 1e-4 | [1e-6, 1]; below it the run stops with exit code 5 and the offending cell's coordinates |
| `active_margin` | int | tiles | 1 | [0, 3] |
| `active_rebuild` | int | steps | 10 | [1, 1000]; also the stop-file polling period |
| `mass_warn` | float | - | 1e-3 | [0, 1]; relative mass error that raises a warning event |
| `fast_math` | bool | - | false | GPU only; parity tests run with false |

`physics`

| Field | Type | Unit | Default | Bounds / note |
|---|---|---|---|---|
| `g` | float | m/s² | 9.80665 | [9.7, 9.9] |
| `ia_ratio` | float | - | 0.2 | [0, 0.5]; initial abstraction ratio for grid CN losses (lumped subbasins carry their own HMS value) |

`hydrology`

| Field | Type | Unit | Default | Bounds / note |
|---|---|---|---|---|
| `hms` | object or null | - | null | `{folder, basin, met, control}`; expanded by `resolve()` into the fields below; the resolved file carries no HMS reference |
| `basin` | Basin | - | empty | subbasins, reaches, junctions (section 8) |
| `subbasin_layer`, `name_field` | path, str | - | null, "name" | optional override of the polygons from the HMS sqlite |
| `step_s` | float | s | 60 | [1, 3600]; the lumped engine's step, the coupling interval and the series output step |
| `inflows` | list | - | [] | `{name, xy, series: [[t_s, m3_s]] or csv path, spread_radius}`; user hydrographs (the dam team's, for instance) |
| `spread_radius` | float | m | 2 dx | [0, 500]; radius over which an injected hydrograph is spread, weighted by wet area at 1 m depth |

`storm`

| Field | Type | Unit | Default | Bounds / note |
|---|---|---|---|---|
| `kind` | enum | - | required | `uniform`, `frequency`, `geotiff_stack` (the `STORM` registry) |
| uniform: `table` | list[[t_s, mm_h]] | - | required | step function |
| frequency: `depth_mm` | float | mm | required | [1, 2000]; point depth |
| frequency: `duration_h` | float | h | 24 | [1, 96] |
| frequency: `pattern` | list[[pct_time, pct_depth]] or `{dss, pathname}` | % | required | HMS percent graph; the Block 2 one comes from `.pdata` + DSS |
| frequency: `step_min` | int | min | 5 | [1, 60] |
| geotiff_stack: `files` or `folder`, `times`, `units` | - | - | required | `mm_h` or `mm_per_step` |
| `arf.table` | list[[area_km2, factor]] or `{dss, pathname}` | - | null | null = no reduction |
| `arf.storm_area_km2` | float or null | km² | null | [0.1, 1e5]; null = factor 1; `wadi2d arf` sets it per job |
| `arf.n_areas` | int | - | 6 | [2, 12]; for `wadi2d arf` when `areas_km2` is absent |
| `arf.areas_km2` | list[float] | km² | null | explicit set |
| `arf.accumulation_raster` | path or null | cells or km² (attr) | null | for the composite map; produced by QGIS processing |
| `t_start` | ISO datetime or 0 | - | 0 | storm clock = run clock |

`boundaries`: list of `{name, geometry (LineString), kind: closed|free|stage, stage_m or stage_series [[t_s, m]]}`; default: every domain
edge is `closed`. Lines are rasterised onto boundary faces at run start (C5).

`outputs`

| Field | Type | Unit | Default | Bounds / note |
|---|---|---|---|---|
| `map_every_s` | float | s | 900 | [0, 86400]; 0 = no time maps |
| `map_variables` | list[enum] | - | ["depth"] | subset of `depth`, `qx`, `qy` (speed and level derived at export) |
| `maxima` | bool | - | true | depth, speed, hazard, arrival time |
| `hazard` | enum | - | "dv" | `dv` (depth x speed), `defra` (classes) |
| `points` | list | - | [] | `{name, xy, drainage_area_km2?}`: depth, level, speed series |
| `lines` | list | - | [] | `{name, geometry, drainage_area_km2?}`: discharge series through the crossed faces (the design points) |
| `series_every_s` | float | s | 60 | [1, 3600] |
| `live_every_steps` | int | steps | 200 | [0, 10000]; 0 = off |
| `live_stride` | int | cells | 4 | [1, 16] |
| `geotiffs` | list[enum] | - | all four maxima | written at the end; `wadi2d export` regenerates them |

`run`

| Field | Type | Unit | Default | Bounds / note |
|---|---|---|---|---|
| `duration_s` | float | s | required | [1, 2.6e6] |
| `backend` | enum | - | "auto" | `auto` (GPU if CuPy sees a device), `gpu`, `cpu` |
| `gpu_device` | int | - | 0 | >= 0 |
| `cpu_threads` | int | - | 0 | 0 = all cores |
| `checkpoint_every_s` | float | wall s | 300 | [0, 86400]; 0 = none |
| `progress_every_s` | float | wall s | 1.0 | [0.1, 60]; step events are throttled to this |
| `estimate.depth_m`, `estimate.speed_m_s`, `estimate.wet_fraction` | float | m, m/s, - | 1.0, 2.0, 0.2 | dry-run guesses; bounds [0.01, 50], [0, 20], [0.01, 1] |

A job for the Block 2 wadi in mode (b), abbreviated:

```json
{
  "project": {"format_version": "1.0", "name": "block2_wadi_100yr"},
  "grid": {"domain": "inputs/domain.gpkg", "dx": 10.0, "path": "../grid_10m.h5"},
  "terrain": {"dem": "D:/.../GGC_2_MERGE_HDSM.tif",
              "objects": [{"kind": "crest_line", "geometry": "inputs/dam_crest.gpkg", "z": "field", "z_field": "crest_z"},
                          {"kind": "spillway", "geometry": "inputs/spillway.gpkg", "z_crest": 212.5, "coefficient": 2.1, "length": 40}],
              "manning": {"source": "polygons", "path": "inputs/landuse.gpkg", "field": "n"},
              "cn": {"source": "raster", "path": "inputs/cn.tif"}},
  "hydrology": {"hms": {"folder": "D:/.../HEC_HMS_Block_02", "basin": "Basin_1.basin", "met": "FM_100yr.met", "control": "Control_1.control"},
                "subbasin_modes": {"S12": "grid", "S14": "grid"}},
  "storm": {"kind": "frequency", "arf": {"storm_area_km2": 120}},
  "boundaries": [{"name": "sea", "geometry": "inputs/coast.gpkg", "kind": "stage", "stage_m": 0.0}],
  "outputs": {"lines": [{"name": "Bidah 03", "geometry": "inputs/bidah03_xs.gpkg", "drainage_area_km2": 118.4}]},
  "run": {"duration_s": 172800}
}
```

`resolve()` turns `hydrology.hms` into the full `basin`, the `storm.frequency` block (depth 205.4 mm, 24 h, the pattern as numbers,
the ARF table as numbers) and `run.duration_s` from the control file, so `config.resolved.json` is self-contained.

### 3.2 How numerics reach the kernels without literals

- `solver/layout.py` defines `PARAMS_DTYPE`, a numpy structured dtype with `align=True`, whose field names are the `numerics` and
  `physics` field names plus the grid integers (`nx`, `ny`, `ntx`, `nty`, `tile`, `rows`, `dx`). Enums become `int32` codes defined
  once in `layout.py` (`LIMITER = {"none": 0, "minmod": 1, ...}`).
- `solver/params.py` builds the record from the resolved config and generates the C `struct Params` text from the dtype. The GPU loader
  prepends that text to every kernel source and fills `__constant__ Params P` with `module.get_global("P").copy_from_host(...)` once per
  run. The CPU backend passes the same record as the first argument of each Numba function. Verified today (table at the top).
- A test launches a one-thread kernel that writes `sizeof(Params)` and every field offset and compares them with numpy's; a second test
  greps `kernels/*.cu` and `cpu/kernels.py` for numeric literals other than `0`, `1`, `2`, `0.5` and powers used in the arithmetic and
  fails on any other constant (the engineering rule 2 gate, mechanical).
- Nothing is compiled per configuration: one module per (source hash, architecture, `fast_math`), cached by CuPy itself in
  `~/.cupy/kernel_cache` (verified path on this machine). No cache code of our own (C3).

### 3.3 How the resolved configuration is recorded

Before the first step, `run.py` writes `<out>/config.resolved.json`: the full `RunConfig.model_dump()` with every default present,
every path absolute, the HMS parts expanded, plus a `provenance` object: `wadi2d_version`, `git_commit` (if the package runs from a
checkout), `python`, `numpy`, `numba`, `cupy`, `cuda_runtime`, `driver`, `gpu_name`, `hostname`, `started`, `grid_hash` (the hash of
`grid.h5`'s identity attributes), `inputs` (path, size, mtime, and sha256 for files under 1 GB; the 27.8 GB DEM is identified by path,
size and mtime). The same JSON string is stored as an attribute of `results.h5`, so a results file alone names its configuration. A
run is reproducible from the folder: `wadi2d run config.resolved.json --out other_folder` must give the same numbers (a test does it).

## 4. Data contracts

Every file carries `format` (a name) and `format_version` ("major.minor"). A reader accepts its own major and any minor not above its
own; a minor adds optional datasets or fields and never changes meaning; a major changes meaning and bumps the name of the folder in
the tests. `job.json` is the only file with migration code in version 1 (`config/migrate.py`, applied by `load()` before validation,
and by `wadi2d migrate`); `grid.h5` is rebuilt rather than migrated (minutes), and an old `results.h5` is read by the release that wrote
it (the version is in its attributes; releases are tagged). GeoTIFF has no version: it is a standard.

### 4.1 `grid.h5` (producer `wadi2d build-grid`; consumers the solver, `forcing.py`, the plugin for display)

Root attributes: `format="wadi2d-grid"`, `format_version="1.0"`, `wadi2d_version`, `created`, `crs_wkt`, `x_ul`, `y_ul` (upper-left
corner of the padded grid, m), `dx`, `tile=32`, `ntx`, `nty`, `nx=ntx*32`, `ny=nty*32`, `rows`, `dem_path`, `dem_size`, `dem_mtime`,
`dem_pixel`, `grid_hash` (sha256 of the JSON of the `grid`, `terrain` and `tables` parts plus the DEM identity and the object
geometry files' hashes: the stale check), `objects_json` (the terrain objects as applied, GeoJSON with their parameters).

Row index `j` increases southward and column `i` eastward, as in a raster; the arrays are the padded grid with one inactive tile ring
on every side, so every active cell has four faces inside the arrays. Datasets (chunks `(32, 32)` for 2-D, `(32, 32, rows)` for 3-D;
gzip level 1 with the shuffle filter; float32 unless stated):

| Dataset | dtype, shape | Unit | Meaning |
|---|---|---|---|
| `/cells/mask` | uint8 (ny, nx) | - | 1 active |
| `/cells/zmin` | float32 (ny, nx) | m | lowest DEM sample in the cell (host use only: display, initial conditions) |
| `/cells/dz` | float32 (ny, nx) | m | row spacing of the cell table = max(min_dz, (zmax − zmin) / (rows − 1)) |
| `/cells/hbar` | float32 (ny, nx, rows) | m | stored volume per cell plan area at level zmin + k dz; above the last row volume grows linearly |
| `/cells/manning` | float32 (ny, nx) | s m^-1/3 | |
| `/cells/cn` | float32 (ny, nx) | - | optional; 0 where none |
| `/faces_x/zf_l`, `/faces_x/zf_r` | float32 (ny, nx) | m | face opening level minus `zmin` of the west cell and of the east cell (no absolute elevation reaches a kernel, C15) |
| `/faces_x/dzf` | float32 (ny, nx) | m | row spacing of the face tables |
| `/faces_x/width` | float32 (ny, nx, rows) | m | wet length of the face at level z_face + k dzf, times the crest length factor where a crest crosses |
| `/faces_x/area` | float32 (ny, nx, rows) | m² | flow area at that level |
| `/faces_x/type` | uint8 (ny, nx) | - | `FACE.OPEN=0, CLOSED=1, SPILLWAY=4` (2 and 3 are set at run time from `boundaries`) |
| `/faces_x/aux` | int32 (ny, nx) | - | index into `/structures` for spillways, −1 otherwise |
| `/faces_y/*` | same | | `fy[j, i]` is the north face of cell (j, i); `fx[j, i]` its west face |
| `/structures` | compound (n,): `kind u1, z_crest f4, coefficient f4, length f4, submergence u1, name vlen str` | | spillways in version 1 |
| `/tiles/has_active` | uint8 (nty, ntx) | - | the solver's initial active list |

Sizes: static data ≈ 375 B per cell (cells 85, faces 2 x 145); 2 M cells ≈ 0.75 GB on disk before compression, 6 M ≈ 2.3 GB.

### 4.2 `results.h5` (producer the engine; consumers `export.py`, the plugin, post-processing)

Root attributes: `format="wadi2d-results"`, `format_version`, `wadi2d_version`, `run_id` (uuid), `config_resolved` (the JSON string),
`grid_path`, `grid_hash`, `status` (`running`, `ok`, `stopped`, `error`), `started`, `finished`, `t_start` (ISO), `backend`, `device`.

| Group / dataset | dtype, shape, chunks | Meaning |
|---|---|---|
| `/time` | float64 (nt,) | seconds since `t_start` for the maps |
| `/maps/depth`, `/maps/qx`, `/maps/qy` | float32 (nt, ny, nx), chunks (1, 128, 128), gzip 1 + shuffle, resizable in t | the state at output times; dry cells 0 |
| `/maxima/depth`, `/maxima/speed`, `/maxima/hazard`, `/maxima/arrival_s` | float32 (ny, nx), chunks (128, 128) | arrival = first time depth > h_wet; −1 never |
| `/series/time` | float64 (ns,) | `series_every_s` clock |
| `/series/points/<name>/depth`, `/level`, `/speed` | float32 (ns,) | attrs `x`, `y`, `cell_j`, `cell_i`, `drainage_area_km2` |
| `/series/lines/<name>/discharge` | float32 (ns,) | m³/s through the line's faces (sign: left to right along the line); attrs geometry WKT, `drainage_area_km2` |
| `/hydrology/<element>/outflow`, `/precip`, `/excess`, `/loss` | float32 (ns,) | the lumped engine, every element, m³/s and mm per step |
| `/forcing/hyetographs/<name>` | float32 (nr,) + `/forcing/rain_time` | the rain applied, m/s per interval, per rain group; attrs `arf_factor`, `storm_area_km2` |
| `/forcing/rain_group` | int16 (ny, nx) | which hyetograph fed each cell; −1 masked by a lumped polygon |
| `/forcing/inflows/<name>` | float32 (ns,) + attrs cells, weights | injected hydrographs as applied |
| `/log/mass` | compound (nm,): `t f8, step i8, dt f4, volume f8, rain f8, inflow f8, outflow f8, infiltration f8, error f8` | one record per `progress_every_s` |
| `/log/events` | vlen str (ne,) | copy of `progress.jsonl` |

The time maps are the only large part: 2 M cells x 3 variables x 4 B = 24 MB per output time uncompressed; mostly-dry fields compress
5-20x [Likely]. The writer flushes after every map so a killed process leaves a readable file.

### 4.3 `checkpoint.h5` (engine to itself)

`/state/{h, qx, qy, pcum}` float32 (ny, nx), `/maxima/*`, `/active_tiles` int32, `/lumped/<element>` (the unit-hydrograph convolution
buffer and the Muskingum-Cunge sub-reach flows, float64), attrs `t`, `step`, `config_hash` (numerics + grid + hydrology parts),
`format_version`. Written to `checkpoint.tmp.h5` then `os.replace`d; one file, overwritten.

### 4.4 JSON files

| File | Producer -> consumer | Content |
|---|---|---|
| `job.json` | plugin or user -> engine | `RunConfig`, unresolved; relative paths relative to the file |
| `config.resolved.json` | engine -> everyone | section 3.3 |
| `estimate.json` | `run --dry-run` -> plugin | `cells_total, cells_active, tiles_active, bytes_device, bytes_host, dt_est_s, steps_est, cost_ns_per_cell_step, wall_est_s, source` (`"doctor"` or `"default"`) |
| `~/.wadi2d/doctor.json` | `wadi2d doctor` -> dry-run | the environment report and the measured cost per cell-step on this machine, per backend |
| `arf/plan.json` | `wadi2d arf` -> itself and the plugin | the storm areas, the job folders, their status |
| `arf/design_points.csv` | `wadi2d arf` -> user | point, drainage area, bracketing areas, interpolated peak and time to peak, path to the series |

### 4.5 GeoTIFF conventions

All rasters: GTiff, float32, `nodata=-9999`, tiled 256 x 256, `compress=DEFLATE`, `predictor=3`, CRS = the DEM's, transform from
`GridGeometry` (north-up), band description = variable and unit, TIFF tags `WADI2D_VERSION`, `RUN_ID`, `VARIABLE`, `UNITS`, `T_S`
(for time slices), `STORM_AREA_KM2`. Only the active extent is written (the padding ring is cropped). Files: `maps/max_depth.tif`,
`max_speed.tif`, `hazard.tif` (float dv, or uint8 classes with a colour table for `defra`), `arrival_h.tif`, optional
`depth_<HHHHMM>.tif`. The live raster `live/depth.tif` is uncompressed, strided by `live_stride`, written to `live/depth.tmp.tif` and
renamed with `os.replace` so the plugin never reads a half file.

### 4.6 Progress events (`progress.jsonl`, one JSON object per line, UTF-8, `\n`)

Common fields: `ev`, `seq` (monotonic int), `wall` (ISO time). Event kinds:

| `ev` | Fields | When |
|---|---|---|
| `start` | `protocol:"1.0"`, `run_id`, `out`, `backend`, `device`, `cells`, `cells_active`, `tiles_active`, `t_end`, `wall_est_s` | first line |
| `phase` | `name` (`validate`, `build_grid`, `load_grid`, `forcing`, `run`, `export`), `progress` 0-1 | phase changes and long preprocessing |
| `step` | `t`, `step`, `dt`, `wet_cells`, `tiles`, `mass_err`, `u_capped`, `wall_s`, `eta_s`, `rate_cells_per_s` | throttled to `progress_every_s` |
| `output` | `kind` (`map`, `live`, `maxima`, `series`, `checkpoint`), `t`, `path` | each write |
| `warn` | `code` (`DT_SMALL`, `MASS_ERROR`, `U_CAPPED`, `NODATA_IN_DOMAIN`, `GRID_REBUILT`), `msg`, `t`, `j`, `i`, `x`, `y` | as they happen |
| `error` | `code`, `msg`, `traceback` | before a non-zero exit |
| `done` | `status` (`ok`, `stopped`, `error`), `exit_code`, `wall_s`, `outputs` (list of paths) | last line |

The plugin reads the file from its last offset every 500 ms. stdout carries nothing the plugin parses (C13); stderr carries one human
line per `phase` and `warn` plus Python logging. A remote job runner (version 2) ships the same file.

## 5. Engine process protocol

```
wadi2d schema      [--out schema.json]                       JSON Schema of job.json; exit 0
wadi2d doctor      [--bench] [--json]                        environment report; --bench times the two kernels per backend on a 1 M-cell synthetic grid
wadi2d build-grid  job.json [--force] [--out grid.h5]        builds or refreshes grid.h5 (skips when grid_hash matches, unless --force)
wadi2d run         job.json --out DIR [--backend auto|gpu|cpu] [--dry-run] [--resume] [--no-build] [--quiet]
wadi2d arf         job.json --out DIR [--areas 10,30,100] [--only-plan] [--parallel N]   N > 1 only makes sense for CPU runs or several GPUs
wadi2d export      RUN_DIR [--what max_depth,max_speed,hazard,arrival,series,hydrology] [--t 3600,7200]
wadi2d hms-import  HMS_DIR --basin F --met F --control F --out job.json [--mode lumped|grid|auto]
wadi2d info        FILE.h5                                    attributes, datasets, sizes; exit 0
wadi2d migrate     job.json [--in-place]                      brings a job file to the current format version
```

Exit codes (one table in `cli.py`, imported by the plugin's copy as a constant list in `engine_process.py`; a test keeps them equal):

| Code | Meaning | `done.status` |
|---|---|---|
| 0 | finished | `ok` |
| 1 | unexpected exception (traceback in the `error` event) | `error` |
| 2 | invalid job (validation errors as JSON on stderr and in the `error` event) | `error` |
| 3 | input missing or unreadable (DEM, HMS file, grid) | `error` |
| 4 | backend unavailable (`--backend gpu` without CuPy or a device; compile failure) | `error` |
| 5 | numerical failure (`dt < dt_min`, NaN) with the cell's coordinates | `error` |
| 6 | stopped on request, outputs flushed, checkpoint written | `stopped` |
| 7 | out of memory (device or host), with the estimate it would have needed | `error` |
| 8 | resume refused (checkpoint's `config_hash` differs) | `error` |

Stop: the plugin (or a user) creates the empty file `<out>/stop`; the loop polls it every `active_rebuild` steps, flushes maps and
series, writes the checkpoint and the `done` event, exits 6. `SIGINT`/`CTRL_BREAK` do the same. The plugin kills the process only if no
`done` arrives within 30 s. Restart: `wadi2d run job.json --out DIR --resume` loads `checkpoint.h5`, verifies `config_hash`, reopens
`results.h5` in append mode, continues from `t`; without a checkpoint `--resume` starts from zero with a warning. A crash loses at most
`checkpoint_every_s` of wall time.

Dry run: validates, resolves, reads `grid.h5`'s attributes (or, when it does not exist yet, rasterises the domain polygon at `dx` to
count cells), computes `bytes_device = cells x 435` and `bytes_host`, `dt_est = cfl dx / (speed + sqrt(g depth))` from
`run.estimate`, `steps_est = duration / dt_est`, `wall_est = steps_est x cells_active x cost_ns_per_cell_step` with the cost from
`~/.wadi2d/doctor.json` for the chosen backend (defaults 1.5 ns GPU, 60 ns CPU [Guessing] when `doctor --bench` has not run), writes
`estimate.json`, prints it, exits 0 or 7 (estimate above device memory).

## 6. Registries and adding a method

One class, five instances, no plugin discovery, no entry points:

```python
LOSS = Registry("hydrology.loss")            # scs_cn                      v2: green_ampt, initial_constant, deficit_constant
TRANSFORM = Registry("hydrology.transform")  # scs_uh, clark               v2: snyder, modclark
ROUTING = Registry("hydrology.routing")      # muskingum_cunge, lag        v2: kinematic_wave, muskingum
STORM = Registry("storm")                    # uniform, frequency, geotiff_stack   v2: netcdf, grib2, dss_grid
TERRAIN_OBJECT = Registry("terrain.object")  # crest_line, wall, burn_line, spillway   v2: channel_template
```

Each registered class carries a nested pydantic `Params` model and implements one small protocol (`Loss.excess(rain_m, state)`,
`Transform.convolve(excess, dt)`, `Routing.route(inflow, dt)`, `StormSource.rate_field(...)`, `TerrainObject.edit_dem/mark_faces`). The
config envelope is `{method: str, params: dict}`; `schema.py` validates the envelope and `resolve()` asks the registry class to
validate `params` with its own model. `wadi2d schema` merges every registered `Params` into an `anyOf` so the plugin sees the fields.
Adding a method is one new file in the package, one `@LOSS.register("green_ampt")` line, and one test file; no edit of `schema.py`,
`network.py` or the plugin. A test asserts the registered names equal the version-1 list above, so a method cannot slip in without
the design note being updated (the scope gate of decision 17).

Not registries (C7): the backend (`select_backend` is a two-way choice, one interface, rule 4 satisfied), the outputs (a fixed set
driven by flags), the HMS readers (one per file kind, exhaustive).

## 7. Solver array layout, tile convention, kernels, backends, parity

### 7.1 Layout (`solver/layout.py`, the contract both backends and the HDF5 writer import)

- Plain row-major arrays of the padded grid `(ny, nx)`, `ny = nty x 32`, `nx = ntx x 32`, one inactive tile ring around the domain.
  Tile `(tj, ti)` covers rows `32 tj .. 32 tj + 31` and columns `32 ti .. 32 ti + 31`; tile id `tj x ntx + ti`. The active list is an
  `int32[nact]` of tile ids rebuilt every `active_rebuild` steps from a per-tile wet flag with `active_margin` tiles of margin.
- Kernels never write `j * nx + i`; they call `cell_index(tile, ty, tx)` from `common.cuh` (and its Numba twin). A tile-major or
  compacted storage (version 2's quadtree, decision 16 b's domain split) changes that one function and the writer (C6).
- 3-D tables are `(ny, nx, rows)`: a cell's 16 rows are one contiguous 64 B line, read whole by the first lookup; a warp reading 32
  neighbouring cells pulls 2 KB, every byte of it used.
- Face convention: `fx[j, i]` is the west face of cell `(j, i)`, `fy[j, i]` its north face; the east face is `fx[j, i + 1]` and the
  south face `fy[j + 1, i]`, which exist for every active cell because of the ring.
- Elevations: kernels see depths and differences only. State `h` is the mean depth over the cell plan area (volume / dx², float32,
  decision 3); the level above `zmin` comes from the cell table; faces carry `zf_l` and `zf_r` (section 4.1), so the hydrostatic
  reconstruction computes `max(0, d_L − zf_l)` and `max(0, d_R − zf_r)` with no 1,500 m magnitude in the arithmetic (C15). The table
  builder does this bookkeeping in float64 once.
- Launch geometry (GPU): one block per active tile, `blockDim = (32, 8)`, each thread handles four rows. A 1,024-thread block would
  cap registers at 64 per thread and the flux kernel, with MUSCL and two table lookups, needs more than that [Likely]. The tile stays
  32 x 32; the launch shape is a backend detail.

Arrays (`ARRAYS` in `layout.py`, with the HDF5 name where it is persisted):

| Name | dtype, shape | Bytes/cell | Role |
|---|---|---|---|
| `h`, `qx`, `qy` | f4 (ny, nx) | 12 | state; `q` = unit discharge, m²/s |
| `pcum` | f4 (ny, nx) | 4 | cumulative rain for the CN method, m |
| `mask`, `manning`, `cn_s`, `ia` | u1, f4, f4, f4 | 13 | static per cell (`cn_s`, `ia` derived from `cn` at load, m) |
| `dz`, `hbar` | f4, f4 (.., rows) | 68 | cell table |
| `zf_l`, `zf_r`, `dzf`, `width`, `area`, `ftype`, `faux` x 2 axes | f4 x 3, f4 (.., rows) x 2, u1, i4 | 290 | face tables and types |
| `flux_x`, `flux_y` | f4 (3, ny, nx) each | 24 | face fluxes (mass, two momenta) |
| `rain_rate` | f4 (ny, nx) | 4 | m/s, host-updated per rain interval |
| `hmax`, `vmax`, `hazmax`, `tarr` | f4 (ny, nx) | 16 | maxima |
| `tile_wave`, `tile_wet` | f4, u1 (nty x ntx) | ~0 | reductions |
| total | | ≈ 435 | 2 M cells ≈ 0.9 GB device; 6 M ≈ 2.6 GB; the 16 GB card holds ≈ 30 M cells |

### 7.2 Kernels (three, each with one job; the numerics panel fixes the formulas, not the split)

| Kernel | Reads | Writes | Job |
|---|---|---|---|
| `flux` | `h, qx, qy` of 4 cells per face, `hbar/dz` of 2 cells, face tables, `ftype/faux`, `P` | `flux_x, flux_y`, `tile_wave` | MUSCL reconstruction of level-above-face and velocity, hydrostatic reconstruction against `zf`, HLLC in the face-normal frame scaled by the face wet area and width, per `ftype`: closed = zero flux, free = outgoing characteristic, stage = Riemann against the given level, spillway = `Q = C L H^1.5` with Villemonte submergence as a mass-only flux; records the max wave speed per tile (only cells with `h > h_cfl`) |
| `update` | `flux_x, flux_y` of 4 faces, `h, qx, qy, pcum, cn_s, ia, manning, rain_rate, hbar/dz`, `P` | `h, qx, qy, pcum, hmax, vmax, hazmax, tarr, tile_wet` | flux divergence, bed-slope source consistent with the reconstruction, rain and CN excess, point-implicit Manning friction with the sub-grid effective depth, velocity cap (counted), maxima, wet flag |
| `dt_reduce` | `tile_wave` over the active list | one float | the global step `cfl dx / max wave`, clamped to `[dt_min, dt_max]` (the clamp at `dt_min` is detected on the host and ends the run with exit 5 and the tile's worst cell) |

Everything else is a CuPy or NumPy call in `stepper.py`: inflow injection is `scatter_add(h, cells, weights, Q dt / dx²)`, the
rain field upload is one `upload`, the live view is `download(h[::s, ::s])`, line discharges are one gather of the line's face fluxes
and one `bincount`. SSP-RK2 is two `flux` + `update` passes with the stage flag in the argument list. The seed's `friction`,
`sources`, `boundaries`, `structures`, `maxima` and `liveview_downsample` kernels are folded into these (C1): each would have cost a
further pass over the state arrays, and each would have needed its own parity test.

Per-step cost estimate [Guessing, arithmetic from the measured 827 GB/s]: `flux` touches ≈ 300 B per active cell (face tables dominate:
two faces x 128 B), `update` ≈ 150 B; RK2 doubles it: ≈ 1 KB per active cell per step ≈ 1.2 ns. 2 M cells all active, 48 h at a 2 s
step: 86,400 steps x 2.4 ms ≈ 3.5 min; with 20 % of tiles wet ≈ 1 min. Table traffic is the lever if it is slower: caching the
bracketing row per cell halves it (version 2, behind `common.cuh`).

### 7.3 Backends

`Backend` is a protocol with seven methods (`upload`, `download`, `flux`, `update`, `dt`, `scatter_add`, `synchronize`). `GpuBackend`
holds the `RawModule` and the `__constant__` record; `CpuBackend` holds the Numba functions compiled on first use (`cache=True` in
`__pycache__`), parallel over active tiles with `prange`, `cpu_threads` through `numba.set_num_threads`. `select_backend("auto")`
tries `import cupy` and `cupy.cuda.runtime.getDeviceCount() > 0`, then falls back with a `warn` event; `--backend gpu` fails with exit 4
instead. The CPU twin exists for machines without NVIDIA, for CI, and as the reference in parity tests; it is not a performance path
(tens of times slower, decision 16 c).

### 7.4 Parity

The `.cu` and the `.py` kernels are written side by side with the same helper names, the same statement order and the same
accumulation order of the four face fluxes. Tests (`tests/parity/`, mark `gpu`): (1) a single `flux` + `update` on a random wet state
over a synthetic tilted-bowl grid with crest faces and a spillway: `max |Δh| < 1e-6 m`, `max |Δq| < 1e-5 m²/s`; (2) 200 steps of the
Thacker case: `max |Δh| < 1e-4 m` and identical step counts; (3) the `dt_reduce` value within 1e-6 relative; (4) every analytic case of
section 11 runs on both backends with the same tolerance. Float32 on both sides, `fast_math` off; the FP64 CPU reference used to
measure the float32 error is a dtype parameter of `CpuBackend`, not a configuration option (C11).

## 8. Hydrology object model and the HMS readers

`hydrology/model.py`:

```
Basin(name, subbasins: list[Subbasin], reaches: list[Reach], junctions: list[Junction])
Subbasin(name, area_km2, downstream, mode: "lumped"|"grid", polygon: Polygon|None, outlet: (x, y)|None,
         loss: LossSpec, transform: TransformSpec, impervious_pct)
Reach(name, downstream, routing: RoutingSpec)         # version 1: MuskingumCunge(length_m, slope, n, shape: trapezoid|eight_point, bottom_width_m, side_slope, section, subreaches) or Lag(lag_min)
Junction(name, downstream: str|None)                  # None = basin outlet (Block 2's outlet junctions have no Downstream line)
LossSpec = {method: "scs_cn", params: {cn, ia_mm}}; TransformSpec = {method: "scs_uh", params: {lag_min}} | {method: "clark", params: {tc_h, r_h}}
```

Sinks, reservoirs, diversions and sources are version 2 (none in Block 2; `read_basin` raises a clear error when it meets one).

The `Basin` is the source of truth of a run. The HMS readers are one-way mappers into it and are used once, by `resolve()` (when
`hydrology.hms` is given) or by `wadi2d hms-import`; after that the resolved job carries everything inline, and the HMS folder is not
needed to rerun. Mapping, all fields present in the Block 2 files:

| HMS file | Reader | Produces |
|---|---|---|
| `Basin_1.basin` | `hms/basin.py` | `Subbasin` from `Area`, `Downstream`, `LossRate: SCS` (`Curve Number`, `Initial Abstraction`, `Percent Impervious Area`), `Transform: SCS` (`Lag`); `Reach` from `Route: Muskingum Cunge` (`Length`, `Energy Slope`, `Mannings n`, `Channel: Trapezoid`, `Bottom Width`, `Side Slope`, `Number Subreaches`, `Index Celerity`); `Junction` from `Downstream`; `Unit System: Metric` checked (US customary is converted at read) |
| `Basin_1.sqlite` | `hms/basin_gis.py` | `subbasin2d` polygons (WKB) by `name`, `outlet` points, `reach2d` lines; CRS from `spatial_ref_sys` (EPSG:32640 here) |
| `FM_100yr.met` | `hms/met.py` | `FrequencyStormSpec(depth_mm=205.4, duration_h=24, pattern_name="FM 10-1000yr", storm_area_km2=300, arf_table_name="ARF FM", uniform=True)` and per-subbasin `Depth` overrides when present |
| `HEC_HMS_Block_02.pdata` + project DSS | `hms/pdata.py`, `hms/dss.py` | the pattern (percent graph) and the ARF table as number lists; `Elev-Dis` tables ignored in version 1 |
| `Control_1.control` | `hms/control.py` | `t_start`, `t_end`, `step_s` (HMS's `24:00` is the next day's `00:00`) |
| `HEC_HMS_Block_02.hms` | `hms/project.py` | the met file list and the project DSS name, for the plugin's drop-down |

The lumped engine (`network.py`) walks the basin in topological order every `hydrology.step_s`: subbasin excess (`LOSS`), unit
hydrograph convolution (`TRANSFORM`), junction sums, reach routing (`ROUTING`), and returns the flow at every element. `run.py`
advances the solver in coupling intervals of `step_s` with the lumped outflows held constant inside the interval: a subbasin whose
`downstream` is a 2D-domain element (or whose outlet lies inside the domain) is injected at its outlet cells; a lumped subbasin's polygon
sets `rain_group = −1` on the 2D cells it covers (no double rainfall, decision 5); a `grid` subbasin's polygon defines a rain group
fed by its hyetograph with CN losses per cell. Mode (a) is a job with no 2D domain (`grid` absent): `run.py` skips the solver and
writes `/hydrology` only.

The oracle relation: the HMS depth-area DSS (`DA_100yr_B1.dss`) gives, for every element and every analysis point, the series of the
run whose storm area is that point's drainage area; `tests/oracle/test_hms_block2.py` reproduces each analysis point's run with
`storm.arf.storm_area_km2` set to that area and compares element by element. Two cheaper oracles come first: the storm builder against
HMS's own `PRECIP-INC` series per subbasin (exact to rounding), and the losses against `PRECIP-LOSS` and `PRECIP-EXCESS`.

## 9. ARF orchestration as independent jobs

`wadi2d arf job.json --out DIR`:

1. `plan_areas`: the storm areas = `storm.arf.areas_km2` if given, else `n_areas` log-spaced values between the smallest and the largest
   `drainage_area_km2` among `outputs.points` and `outputs.lines` (rounded to two significant figures). Decision 9: 6-8 values cover
   10-600 km² with ≈ 2 % ARF steps.
2. `write_jobs`: `DIR/area_<A>km2/job.json`, identical to the input except `storm.arf.storm_area_km2 = A` and `project.name`; all point at
   the one `grid.h5`. `DIR/plan.json` lists them.
3. `run_all`: runs them with the same `run_job()` in this process (sequential by default: one GPU); `--parallel N` uses N subprocesses for
   CPU runs. Each folder is a complete, restartable run with its own `progress.jsonl`; a job runner on another PC (version 2) executes
   the same folders.
4. `design_point_table`: for each point or line, the two runs bracketing its drainage area, the peak and the time to peak interpolated
   linearly in `log(area)` (error below 1 % by decision 9's arithmetic), the series at the nearer area; `design_points.csv`.
5. `composite_map` (when `storm.arf.accumulation_raster` is set): per cell, the drainage area from the raster (resampled to the grid with
   nearest neighbour), the two bracketing runs, the maxima interpolated in `log(area)`; `composite_max_depth.tif`, `composite_max_speed.tif`,
   `composite_hazard.tif`. Cells with area below the smallest run read the smallest run.

Nothing in the solver, the forcing or the hydrology knows about ARF beyond the single factor `ArfTable.factor(storm_area_km2)` applied
to the storm depth in `storm/frequency.py`; that is what keeps it "cheap orchestration".

## 10. QGIS plugin

```
plugin/wadi2d_qgis/
  metadata.txt          name=Wadi2D, qgisMinimumVersion=3.34, supportsQt6=False in version 1, version from the engine tag, license GPL-3.0-or-later
  __init__.py           classFactory(iface) -> Wadi2DPlugin
  plugin.py             toolbar action, creates the dock, unload
  dock.py               QgsDockWidget with one vertical workflow in QgsCollapsibleGroupBox sections: Terrain, Grid, Hydrology, Storm, Boundaries, Outputs, Run
  job_builder.py        widgets + layers -> job.json and inputs/*.geojson (reprojected to the DEM CRS with QgsCoordinateTransform)
  engine_process.py     QProcess wrapper: start/stop/resume, exit-code table, argument building, stdout/stderr to the log view
  progress_tail.py      QTimer(500 ms): reads new lines of progress.jsonl, parses events, emits Qt signals (step, output, warn, done)
  live_view.py          on each `output: live` event, reloads live/depth.tif (dataProvider().reloadData() + triggerRepaint()); on done loads maps with the QML styles
  results_loader.py     adds maxima GeoTIFFs, series CSVs (as delimited-text layers) and the ARF composite to a layer group named after the run
  schema_cache.py       runs `wadi2d schema` once per engine path, caches the JSON Schema, supplies defaults and tooltips to the widgets
  settings.py           QgsSettings: engine python path, last folders, default dx; the settings page shows `wadi2d doctor --json`
  styles/depth.qml, speed.qml, hazard.qml, arrival.qml
  engine_default.json   written by tools/install_plugin.py: {"python": "<repo>/.venv/Scripts/python.exe"}; read when no setting exists
```

Widgets, all from `qgis.gui` (no `.ui` files, no `pyuic` step; the dock is built in code):

| Section | Widgets | Writes |
|---|---|---|
| Terrain | `QgsMapLayerComboBox` (raster) for the DEM; `QgsMapLayerComboBox` (line) x 4 for crest lines, walls, burn lines, spillways with a field picker (`QgsFieldComboBox`) for crest z; Manning and CN sources (constant spin box, raster combo or polygon combo + field) | `terrain` |
| Grid | `QgsMapLayerComboBox` (polygon) for the domain, `QgsDoubleSpinBox` dx (snapped to multiples of the DEM pixel), a "Build grid" button that runs `wadi2d build-grid` as a QProcess with the same progress tail; a label with the dry-run cell count and memory from `estimate.json` | `grid` |
| Hydrology | `QgsFileWidget` for the HMS folder, combos for basin/met/control (listed from the `.hms` file by the engine's `hms-import --list`), a table of subbasins with a `lumped|grid` column, an inflow table (point layer + CSV) | `hydrology` |
| Storm | kind combo; frequency: depth, duration, pattern from HMS or a CSV; ARF: storm area, areas list for `arf`, accumulation raster combo | `storm` |
| Boundaries, Outputs | line layer + kind; points and lines layers with name and drainage-area fields | `boundaries`, `outputs` |
| Run | duration, backend, output folder (`QgsFileWidget`), **Dry run**, **Run**, **Run ARF**, **Stop**, **Resume**; a `QProgressBar` (t / t_end), labels for dt, wet cells, ETA, a `QPlainTextEdit` log; a "Live view" check box | `run`; starts the process |

Flow of a run: the job builder writes `<out>/job.json` and `<out>/inputs/*.geojson` (selected features of each chosen layer,
reprojected; `job.json` references them), `engine_process.start(["-m", "wadi2d", "run", job, "--out", out])`; `progress_tail` starts;
every `output: live` reloads the live layer (added on the first one, styled, placed on top); `warn` lines go to the log in orange;
`done` loads the results and re-enables the buttons; a non-zero exit shows the `error` event's message. Stop writes the `stop` file and
arms a 30 s kill timer. Resume starts the same command with `--resume`. There is no `QgsTask` and no thread in the plugin (C9): the
engine is already another process, `QProcess` signals arrive on the GUI thread, and a 500 ms file poll is cheap.

Install next to the engine venv: `tools/install_plugin.py [--profile default] [--copy]` creates a directory junction
(`%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\wadi2d_qgis -> <repo>\plugin\wadi2d_qgis`; `mklink /J`, no admin rights) or a
copy, and writes `engine_default.json` with the venv's `python.exe`. Development uses QGIS's Plugin Reloader; a release ships
`wadi2d_qgis.zip` (from `tools/package_plugin.py`) for "Install from ZIP" plus a one-line engine install (`uv sync --extra gpu` in the
repo, or `pip install wadi2d[gpu]`), both in `docs/tutorial.md`. The plugin never imports `wadi2d`, `cupy`, `numba`, `h5py`: QGIS's
Python has none of them and must not need them.

## 11. Testing layers and CI

Marks: `unit` (default, no data, CPU, seconds), `analytic`, `parity` (needs a GPU), `oracle` (needs the Block 2 data folder, path in
`WADI2D_DATA`), `slow`, `qgis` (runs under QGIS's Python). `pytest` with no mark selection runs `unit` and `analytic` on the CPU.

| Layer | Folder | What | Pass criterion |
|---|---|---|---|
| Environment | `tests/unit/test_env.py` | every dependency imports under `python -I` from the venv; registered names equal the version-1 list; module import graph obeys section 2 | exact |
| Config | `tests/unit/test_config.py` | defaults, bounds, `extra=forbid`, round trip through JSON Schema, `migrate`, resolved dump reproduces a run | exact |
| Layout | `test_layout.py` | `Params` sizeof/offsets GPU vs numpy (gpu mark) and the no-literal grep of the kernels | exact |
| Geometry and tables | `test_grid_geometry.py`, `test_tables_*.py`, `test_crest.py` | tilted plane (hbar exact), parabolic bowl (volume integral within 0.1 %), a 45° crest closes a staircase with factor 1/√2, a wall closes, a burn lowers | tolerances stated per test |
| Table oracle | `tests/oracle/test_ras_tables.py` | HEC-RAS geometry HDF (same square cells, same terrain, read with `rashdf`) vs ours on a 2 km Block 2 clip | cell volume within 2 % at every level; face area within 5 % |
| HMS readers | `tests/unit/test_hms_*.py` | parse every Block 2 file; `Basin` has 18/8/14 elements with the values quoted in section 8; sqlite polygons sum to the `Area` fields within 0.5 % | exact / stated |
| Storm | `tests/oracle/test_storm_block2.py` | frequency storm vs HMS `PRECIP-INC` per subbasin, per return period | max abs difference 0.01 mm per step |
| Hydrology | `tests/oracle/test_hms_block2.py` | each method vs the DAA DSS per element: `PRECIP-LOSS`, `FLOW` at subbasins, reaches, junctions, for 3 return periods | peak within 2 %, volume within 1 %, time to peak within one step |
| Analytic | `tests/analytic/` | lake at rest on the bowl with a 1,500 m datum, Ritter and Stoker dam breaks, Thacker oscillation, MacDonald steady friction, rain on a plane (kinematic rising limb) | lake: `max |u| < 1e-6 m/s` after 1 h; others: tolerances fixed by the numerics panel, recorded in the test |
| Parity | `tests/parity/` | section 7.4 | stated there |
| Mass | inside every solver test | closed-domain mass error | `< 1e-6` relative |
| End to end | `tests/e2e/` | Block 2 wadi, mode (b), 10 m, 6 h; `arf` with 3 areas; stop + resume gives the same numbers as an uninterrupted run | runs, exit 0, bit-identical resume |
| Plugin | `tests/plugin/test_job_builder.py` | under QGIS's Python: a fixture project -> `job.json` validates against the schema | exact |
| Benchmarks | `tools/bench_step.py` | ms per step at 1 M and 4 M cells, written to `W1 research and design note/benchmarks/` | recorded, not asserted |

CI (`.github/workflows/ci.yml`, active only once he pushes): matrix `windows-latest` and `ubuntu-latest`, Python 3.12, `uv sync
--extra dev`, `ruff check`, `ruff format --check`, `clang-format --dry-run -Werror wadi2d/solver/gpu/kernels/*`, `mypy wadi2d`,
`pytest -m "not gpu and not oracle and not slow and not qgis"`, `pip-licenses` compared with `LICENSES.md`. The GPU, oracle and slow
marks run on his machine by hand before a tag (`tools/pre_release.ps1`), and on a self-hosted runner later if he wants one. Pre-commit
runs ruff and clang-format.

## 12. Build order and "done" per stage

| Stage | Builds | Done when |
|---|---|---|
| 1 Skeleton | package, `schema.py` with every field of section 3, `registry.py`, `layout.py` + `params.py`, `grid_h5`/`results_h5`/`checkpoint` round trips, `progress.py`, `cli.py` with the exit-code table, `run --dry-run` on `examples/plane_rain.json`, `doctor`, `test_env` | `pytest` green on Windows and Linux from a clean `uv sync`; `wadi2d schema` validates the three examples; the `Params` GPU offset test passes on the RTX 5080 |
| 2 Grid and tables | `geometry`, `dem`, `objects`, `crest`, `tables`, `build-grid` | table unit tests and the RAS oracle pass on the 2 km clip; the full Block 2 plain at 10 m builds in under 30 min [Guessing] and its time is recorded |
| 3 Solver | the three kernels twice, `state`, `stepper`, backends, flat bed first then tables | lake at rest, Ritter, Stoker, Thacker, MacDonald within tolerance on both backends; parity green; mass error `< 1e-6`; `bench_step` numbers in W1 |
| 4 HMS and lumped | `hms/*`, `hydrology/*`, mode (a) through `wadi2d run` | storm oracle exact; hydrology oracle within 2 % / 1 % at every element for three return periods; the full Block 2 mode (a) job runs from the CLI |
| 5 Forcing | `storm/*`, `forcing.py`, rain-on-grid, masks, injection, boundaries, spillway, live view, export | rain-on-a-plane and reservoir-spillway tests pass; one Block 2 wadi runs in mode (b) at 10 m with outputs that load in QGIS; stop + resume identical |
| 6 ARF | `arf.py` | `test_arf_small` passes; the design-point table at an exact area equals a direct run; the composite map is produced from a GRASS `r.watershed` accumulation raster |
| 7 Plugin | everything in section 10 | he builds the job, runs, watches the live layer, stops, resumes and loads the results for a Block 2 wadi without touching the CLI |
| 8 Release | Block 2 comparison (modes a and b at the five dam sites against the W1 peaks), the HEC-RAS head to head on one wadi (depth, extent, run time), `docs/`, `LICENSES.md`, tag `v1.0.0` | the comparison numbers are in W1 with their explanation; the licence test passes; the release is built from a clean checkout; pushing waits for his word |

Each stage's tests stay green through the next (engineering rule 5); a stage that needs an interface change in an earlier module
records it in the design note before the edit.

## 13. Licence audit list (engine and plugin GPL-3.0-or-later, decision 15 pending)

| Component | Role | Licence | Fit with GPL-3.0 | Note |
|---|---|---|---|---|
| numpy 2.4, scipy 1.18 | arrays, interpolation | BSD-3 | yes | |
| numba 0.65, llvmlite 0.47 | CPU twin | BSD-2 | yes | must be installed in the venv, not the user site |
| cupy-cuda12x 14.2 | GPU runtime, NVRTC, kernel cache | MIT | yes | |
| nvidia-cuda-nvrtc-cu12 12.9, nvidia-cuda-runtime-cu12 12.9 (and the other `nvidia-*` wheels CuPy pulls) | CUDA runtime | NVIDIA EULA (proprietary, redistributable) | not bundled: installed by the user from PyPI; documented as a system component | the GPL system-library reading is arguable [Likely]; the mitigation is to never redistribute them (a frozen installer in version 2 must leave them out and install them at first run); Apache-2.0 would face the same question |
| h5py 3.16 + HDF5 | files | BSD-3; HDF5 BSD-style | yes | |
| rasterio 1.5 + GDAL, PROJ, GEOS (wheels) | rasters, rasterise | BSD-3; GDAL MIT; PROJ MIT; GEOS LGPL-2.1 | yes | |
| shapely 2.1, pyproj 3.7, affine 2.4 | vectors, CRS | BSD-3, MIT, BSD-3 | yes | |
| pydantic 2.13 | schema | MIT | yes | |
| hecdss 0.1.29 (HEC) | DSS read | MIT [Likely]; the native heclib is a US Government work [Guessing] | audit in stage 4 | fallback: DSSVue CSV exports for the oracle tests |
| rashdf | RAS geometry HDF oracle | MIT [Likely] | test dependency only | |
| pytest 9, ruff, mypy, clang-format wheel, pip-licenses | development | MIT / MIT / MIT / Apache-2.0 with LLVM exception / MIT | yes | not shipped |
| QGIS 3.44 (PyQGIS), PyQt5 | plugin host | GPL-2.0-or-later; GPL-3.0 (or commercial) | yes, and the reason the plugin must be GPL | |
| argparse, json, sqlite3, logging (stdlib) | CLI, JSON, HMS sqlite | PSF | yes | `typer` is in the venv but not used: eight subcommands do not need a dependency |
| EA 2D benchmark data | tests | Open Government Licence [Likely] | yes, with attribution | |
| Block 2 terrain, HMS model, shapefiles | oracle tests | the client's | **not in the repository**; tests skip without `WADI2D_DATA`; synthetic fixtures for CI | a 2 km clip in the repo needs the owner's consent first |

`LICENSES.md` lists each entry with its version; `tests/unit/test_licences.py` compares the installed set (`pip-licenses --format=json`)
with the file and fails on a new or changed entry.

## Changes to the seed

- **C1. Three kernels, not eight.** `flux`, `update`, `dt_reduce`; boundaries and structures are face types inside `flux`; friction,
  rain, losses, injection and maxima are inside `update`; the live view and the line discharges are CuPy calls. Reason: every extra
  kernel is another pass over the state arrays (memory-bound, so another 10-20 % of the step) and another parity test; a face type is one
  branch, not a kernel.
- **C2. Crest lines, walls and burn lines live in the table builder only.** A crest raises the face's opening level and zeroes the
  width rows below it; a wall is a permanently closed face; a burn edits the DEM window before the tables. The solver has no crest
  concept. Reason: "wall until overtopped" is exactly what the hydrostatic reconstruction against a high face level does; one mechanism,
  tested once by the lake-at-rest and the crest tests. The spillway keeps its explicit formula because he wants his coefficient visible.
- **C3. Numerics as a `__constant__` struct from one numpy dtype, no generated header of values, no compile cache of our own.** Verified
  on the machine today. Reason: no code generation path to maintain, one compile per source version instead of one per configuration,
  the same record drives the CPU twin, and CuPy already caches compiled modules on disk.
- **C4. No `forcing.h5`.** Rain groups, masks, injection weights and boundary faces are derived at run start (seconds) and recorded in
  `results.h5:/forcing`; the solver receives a rain-rate field per rain interval. Reason: one file contract fewer; the only expensive
  artefact, `grid.h5`, is the only shared one; the kernel interface for rain becomes a single array.
- **C5. Boundaries move from `grid.h5` to `job.json`.** Reason: a grid then depends on terrain, objects and cell size alone and serves
  every what-if on the same ground; outflow lines are rasterised onto faces at start.
- **C6. Row-major padded arrays with an active-tile index list, not tile-major storage.** Reason: a warp reading one 32-cell row is
  fully coalesced either way, so tile-major buys nothing on the GPU [Likely], while row-major lets h5py, rasterio and numpy address the
  grid directly; the single `cell_index()` function is where a tile-major layout would go in version 2.
- **C7. Five registries with one mechanism; backends and outputs are not registries.** Reason: a registry with one or two fixed entries
  and no planned third is ceremony; rule 4 asks for one interface per extension point, which `select_backend` and the output flags are.
- **C8. One HMS grammar parser with per-file mappers; `.run` and `.gage` readers deferred; a sqlite reader added.** Reason: all HMS
  text files share one block grammar (seen today); the job names basin, met and control explicitly so `.run` adds nothing; frequency
  storms use no gages; the basin sqlite gives polygons and outlets with stdlib `sqlite3` + shapely, which removes the user-supplied
  subbasin layer from the version-1 workflow.
- **C9. `QProcess` + `QTimer`, no `QgsTask`, no `.ui` files, no engine import in the plugin.** Reason: the engine is already a separate
  process; a `QgsTask` would add a thread and cancellation semantics for nothing; widgets built in code avoid the `pyuic` step; the
  plugin reads defaults from `wadi2d schema` so the single source of truth survives the process boundary.
- **C10. `validation/` becomes `tests/analytic/`; `docs/` is three markdown files.** Reason: the version-1 scope line is "a GitHub
  release, one tutorial, a licence file"; nothing shipped that the user does not run.
- **C11. No `project.units`, no `project.crs`, no `run.precision`.** Reason: SI only, the CRS is the DEM's, float32 is decision 3; the
  FP64 CPU reference is a test parameter.
- **C12. `engine/`, `io/` (partly) and `arf/` become `cli.py`, `run.py`, `arf.py`, `export.py`, `doctor.py`.** Reason: each is one
  module with one job; a package for one file hides nothing.
- **C13. The progress protocol is the file, not stdout.** Reason: found today: the DSS library writes its log to the C-level stdout past
  Python's redirection; any other native dependency may; a file with a sequence number is also what a remote runner ships back.
- **C14. Add restart: `checkpoint.h5`, `--resume`, exit code 8, and `wadi2d doctor` with a measured cost for the dry-run estimate.**
  Reason: an hour-long run that cannot be resumed after a stop or a crash is not usable from a GUI; the estimate needs a number from
  this machine, not a constant.
- **C15. No absolute elevation in a kernel: faces carry `zf_l`, `zf_r` relative to each cell's `zmin`.** Reason: decision 3's
  arithmetic applies to the reconstruction too; a 1,500 m level in float32 would put 0.1 mm of noise into every face difference, which
  the lake-at-rest test at a high datum would expose.
- **C16. Tables at uniform level spacing per cell and per face, fixed row count, `(ny, nx, rows)` layout, linear growth above the last
  row.** Reason: the seed left the lookup rule open; uniform spacing makes the level-to-volume lookup O(1), the inverse a four-step
  search within one 64 B line, and the layout the same for both backends and the HDF5 writer. The row count is a config field.

## Risks

- **The well-balanced property with per-face tables.** HLLC with hydrostatic reconstruction is well balanced on a bed step; with
  per-face area and width tables and per-cell storage tables the still-water proof is not textbook, and a leak would show as drift on
  steep ground. Mitigation: stage 3 builds the solver on a plain bed first (tables degenerate to flat cells), then adds tables with the
  lake-at-rest test as the gate; the numerics panel owns the formulation; the fallback is the TUFLOW-like face level `max(z_L, z_R)` with
  cell tables only, which loses some face conveyance detail but keeps every crest feature (crests are face levels).
- **Memory traffic of the tables.** About 0.5 KB per active cell per stage is read from tables; if the real step is 2-3x the estimate,
  the full Block 2 at 10 m is an hour, not twenty minutes. Mitigation: active tiles only; 16-row tables in one cache line; measured
  early by `bench_step` in stage 3; the per-cell cached row index is a contained change in `common.cuh`.
- **Register pressure and launch shape.** The fused `flux` kernel may spill registers at 256 threads per block. Mitigation: the launch
  shape is a backend constant, not a contract; `blockDim (32, 4)` with eight rows per thread is the next step down; `nvcc --resource-usage`
  is not available without a toolkit, but NVRTC's `--ptxas-options=-v` log is readable through CuPy.
- **Two implementations of every formula.** The Numba twin can drift from the CUDA source. Mitigation: side-by-side files with the same
  helper names, the single-step parity test at 1e-6, the analytic suite on both; if drift keeps happening, generating both from one
  template is a later option behind the same tests.
- **Dependency pinning on Blackwell.** `cupy-cuda12x 14.2` with the CUDA 12.9 wheels compiles for sm_120 today; a wheel or driver update
  may not. Mitigation: `uv.lock` pins everything, `wadi2d doctor` reports the chain, the CPU twin is the always-working path, and the
  kernels are plain CUDA C++ that nvcc compiles into a DLL if the NVRTC path ever fails.
- **The user-site trap.** numba is importable today only through the user site-packages; another PC will not have it. Mitigation:
  `test_env` under `python -I`, and the venv owns every dependency.
- **HMS replication within a few per cent may fail for reasons inside HMS** (unit-hydrograph discretisation, Muskingum-Cunge sub-reach
  and step rules, the pattern interpolation). Mitigation: the oracle is element by element, so the first element that disagrees names
  the method; the storm and loss oracles come before any routing; documented deviations are acceptable if explained, since mode (a)'s
  purpose is to know why before a reviewer asks.
- **`hecdss` on other machines and its licence.** The native library ships in the wheel for Windows and Linux [Likely]; its licence is
  not confirmed. Mitigation: audit in stage 4; the ARF table and the pattern can be typed into the job or exported from DSSVue, so the
  run path survives without it; tests fall back to CSV exports.
- **The GPL and the NVIDIA wheels.** Mitigation as in section 13: never redistribute them; state it in `LICENSES.md`; the question is the
  same under any open licence and does not block version 1.
- **Windows process control.** Signals to a child process are unreliable from Qt. Mitigation: the stop file is the primary mechanism and
  the checkpoint bounds the loss; the kill timer is the last resort.
- **A single global time step** stays the version-1 design (decision 18 d defers tile-level local stepping); one thin cell with a
  spurious velocity could still throttle a run. Mitigation: `h_cfl` excludes thin cells from the search, friction is point-implicit,
  the cap is counted and reported, and a `dt_min` stop names the cell so the terrain object or table that caused it can be fixed.
- **Scope creep through the registries and the config.** Mitigation: `test_env` pins the registered names to the version-1 list and
  `extra="forbid"` rejects unknown fields; a new method or field changes the design note first.
- **The plugin and QGIS versions.** Qt6 builds of QGIS exist; `qgis.PyQt` keeps the code portable, but `supportsQt6` is false until
  tested. Mitigation: version 1 targets the 3.44 LTR on his machine; the plugin has no compiled part and no Qt-version-specific module.
