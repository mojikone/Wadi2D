"""One job end to end. This is the only module that imports all the others.

``load_job`` validates and resolves a job file; ``prepare_grid`` gives the tables, from the cache when it can;
``run_job`` does the rest and always returns: its ``RunSummary.exit_code`` is the process exit code of design note
section 5, and a run folder records what happened whatever the outcome.
"""

from __future__ import annotations

import json
import time
import traceback
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import rasterio
import shapely
from pydantic import ValidationError
from rasterio import features
from rasterio.transform import Affine
from scipy import ndimage

from wadi2d.config.constants import M2_PER_KM2, G
from wadi2d.config.schema import RunConfig
from wadi2d.engine.monitor import Balance, Monitor, StopRequested
from wadi2d.forcing import Forcing, boundary_set, build_storm, initial_depth, load_polygons, manning_grid
from wadi2d.grid.tiles import TileGrid
from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
from wadi2d.io.cache import builder_identity, cache_key, cache_path, load_tables, save_tables
from wadi2d.io.checkpoint import checkpoint_job, load_checkpoint, save_checkpoint
from wadi2d.io.geotiff import write_map
from wadi2d.io.identity import file_identity
from wadi2d.io.progress import Progress
from wadi2d.io.results import Results, safe_name, write_series_csv
from wadi2d.solver.model import Model
from wadi2d.solver.stepper import NumericalFailure
from wadi2d.tables import GridTables, build_tables
from wadi2d.terrain import GridWindow, RasterBed, apply_objects
from wadi2d.terrain.crest import line_lengths
from wadi2d.terrain.vector import read_features

EXIT_DONE, EXIT_UNEXPECTED, EXIT_INVALID, EXIT_INPUT, EXIT_BACKEND = 0, 1, 2, 3, 4
EXIT_NUMERICAL, EXIT_STOPPED, EXIT_MEMORY = 5, 6, 7
EDGE_REACH = 2
"""Cells around a boundary that do not count as a closed edge."""


class JobError(Exception):
    """A failure the protocol names; ``code`` is the exit code."""

    code = EXIT_UNEXPECTED


class InvalidJob(JobError):
    code = EXIT_INVALID


class InputMissing(JobError):
    code = EXIT_INPUT


class BackendUnavailable(JobError):
    code = EXIT_BACKEND


PATH_FIELDS = (
    ("grid", "domain"),
    ("grid", "cache_dir"),
    ("terrain", "dem"),
    ("terrain", "manning_raster"),
    ("terrain", "cn_raster"),
    ("storm", "depth_grid"),
    ("hydrology", "hms_basin"),
    ("hydrology", "hms_project"),
    ("hydrology", "hms_sqlite"),
    ("hydrology", "polygons"),
    ("arf", "accumulation"),
)
"""Every path in a job; relative paths are relative to the job file."""
OPTIONAL_INPUT = {("grid", "cache_dir")}


def load_job(path: str | Path) -> RunConfig:
    """Parse and validate a job file; relative paths become absolute."""
    source = Path(path)
    if not source.is_file():
        raise InputMissing(f"job file not found: {source}")
    try:
        cfg = RunConfig.model_validate(json.loads(source.read_text(encoding="utf-8")))
    except (ValidationError, json.JSONDecodeError) as error:
        raise InvalidJob(str(error)) from error
    return resolve_paths(cfg, source.parent)


def resolve_paths(cfg: RunConfig, base: Path) -> RunConfig:
    """The same job with every path absolute."""
    updates: dict[str, dict[str, str]] = {}
    for part, name in PATH_FIELDS:
        value = getattr(getattr(cfg, part), name)
        if value is not None and not Path(value).is_absolute():
            updates.setdefault(part, {})[name] = str((base / value).resolve())
    return cfg.model_copy(update={p: getattr(cfg, p).model_copy(update=u) for p, u in updates.items()})


def check_inputs(cfg: RunConfig) -> None:
    """Every input file must exist before anything expensive starts."""
    if cfg.terrain.dem is None:
        raise InvalidJob("terrain.dem is required")
    if cfg.grid.extent is None and cfg.grid.domain is None:
        raise InvalidJob("grid.extent or grid.domain is required")
    for part, name in PATH_FIELDS:
        value = getattr(getattr(cfg, part), name)
        if value is not None and (part, name) not in OPTIONAL_INPUT and not Path(value).exists():
            raise InputMissing(f"{part}.{name} not found: {value}")


def _domain_polygon(path: str | None, crs: str) -> shapely.Geometry | None:
    if path is None:
        return None
    return shapely.union_all([shape for _properties, shape in read_features(path, crs)])


def _wkt(bed: RasterBed) -> str:
    return bed.crs.to_wkt() if bed.crs is not None else ""


def domain_mask(cfg: RunConfig, bed: RasterBed, window: GridWindow) -> np.ndarray:
    """Active cells: data under the centre pixel, inside the domain polygon if there is one."""
    mask = bed.active_mask(window, cfg.grid.dx)
    polygon = _domain_polygon(cfg.grid.domain, _wkt(bed))
    if polygon is not None:
        transform = Affine(cfg.grid.dx, 0.0, window.x0, 0.0, -cfg.grid.dx, window.y0)
        mask &= features.geometry_mask([polygon], out_shape=mask.shape, transform=transform, invert=True)
    return mask


def grid_window(cfg: RunConfig, bed: RasterBed) -> GridWindow:
    polygon = _domain_polygon(cfg.grid.domain, _wkt(bed))
    extent = cfg.grid.extent if polygon is None else polygon.bounds
    return bed.snap(extent, cfg.grid.dx)


def grid_key(cfg: RunConfig, bed: RasterBed, window: GridWindow) -> str:
    """Hash of everything the tables depend on."""
    limit = cfg.grid.content_hash_limit_mb
    extras = {
        key: file_identity(name, limit)
        for key, name in (("domain", cfg.grid.domain), ("manning", cfg.terrain.manning_raster))
        if name is not None
    }
    t = cfg.terrain
    return cache_key(
        {
            "builder": builder_identity(),
            "dem": bed.identity(limit),
            "window": [window.x0, window.y0, window.ny, window.nx],
            "dx": cfg.grid.dx,
            "objects": [o.model_dump() for o in t.objects],
            "object_settings": [t.join_cells, t.spillway_snap_cells, t.burn_pixels],
            "tables": cfg.tables.model_dump(),
            "manning": t.manning,
            "extras": extras,
        }
    )


def job_hash(cfg: RunConfig) -> str:
    """What a checkpoint must match: everything that changes the water, the input files included."""
    data = cfg.model_dump(mode="json")
    for part, name in (("run", "backend"), ("run", "checkpoint_every_s"), ("grid", "cache_dir")):
        data[part].pop(name)
    data.pop("project")
    limit = cfg.grid.content_hash_limit_mb
    files = {}
    for part, name in PATH_FIELDS:
        value = getattr(getattr(cfg, part), name)
        if value is not None and (part, name) not in OPTIONAL_INPUT:
            files[f"{part}.{name}"] = file_identity(value, limit)
    return cache_key({"job": data, "files": files})


def prepare_grid(cfg: RunConfig, cache_dir: Path, progress: Progress | None = None) -> tuple[GridTables, str]:
    """The tables and the CRS as WKT, from the cache when nothing changed."""
    emit = progress.emit if progress is not None else (lambda *_a, **_k: None)
    with RasterBed(cfg.terrain.dem, cfg.terrain.pixel_stride) as bed:
        crs = _wkt(bed)
        window = grid_window(cfg, bed)
        if cfg.mesh.enabled:
            return _mesh_tables(cfg, bed, window, crs), crs
        key = grid_key(cfg, bed, window)
        path = cache_path(cache_dir, key)
        hit = load_tables(path, key)
        if hit is not None:
            emit("output", kind="grid_cache_hit", path=str(path))
            return hit, crs
        mask = domain_mask(cfg, bed, window)
        if not mask.any():
            raise InvalidJob("the domain holds no active cell")
        grid = TileGrid.from_mask(mask, window.x0, window.y0, cfg.grid.dx)
        bed.bind(grid.x0, grid.y0)
        edits = apply_objects(grid, cfg.terrain.objects, bed.pixel, cfg.terrain)
        tables = build_tables(grid, bed, cfg.tables, manning_grid(cfg, grid, crs), edits.crest, edits.edit)
    save_tables(path, tables, key)
    emit("output", kind="grid_cache_saved", path=str(path))
    return tables, crs


def _mesh_tables(cfg: RunConfig, bed: RasterBed, window: GridWindow, crs: str) -> GridTables:
    """Tables of a quadtree. Not cached yet: the mesher's rules are the first thing a user changes."""
    from wadi2d.mesh.build import build_grid, lines_on_coarse_tiles
    from wadi2d.tables.quad import build_quad_tables

    if cfg.grid.dx < cfg.mesh.min_dx:
        raise InvalidJob(f"grid.dx {cfg.grid.dx} m is below mesh.min_dx {cfg.mesh.min_dx} m")
    mask = domain_mask(cfg, bed, window)
    if not mask.any():
        raise InvalidJob("the domain holds no active cell")
    grid = build_grid(cfg, mask, window.x0, window.y0, crs)
    stray = lines_on_coarse_tiles(cfg, grid)
    if stray:
        raise InvalidJob(
            f"{stray} barrier, boundary or design lines reach coarse tiles, where their faces cannot be read: "
            "keep mesh.refine_lines on, or add a refinement zone along them"
        )
    bed.bind(grid.x0, grid.y0)
    edits = apply_objects(grid, cfg.terrain.objects, bed.pixel, cfg.terrain)
    return build_quad_tables(grid, bed, cfg.tables, manning_grid(cfg, grid, crs), edits.crest, edits.edit)


def _project_tables(h, hms_basin):
    """The paired tables, when a reservoir or a diversion needs them; a basin without one needs no DSS read."""
    from wadi2d.hms import load_pdata
    from wadi2d.hydrology.from_hms import load_project_tables

    if not hms_basin.reservoirs and not hms_basin.diversions:
        return None
    folder = Path(h.hms_basin).parent
    found = [Path(h.hms_project)] if h.hms_project else sorted(folder.glob("*.hms"))
    if not found:
        raise InvalidJob(f"{Path(h.hms_basin).name} has reservoirs or diversions: set hydrology.hms_project")
    stem = found[0].with_suffix("")
    return load_project_tables(load_pdata(stem.with_suffix(".pdata")), stem.with_suffix(".dss"))


def _lumped_rain(cfg: RunConfig, storm, basin, hms_basin, crs: str):
    """What falls on the lumped network: the storm, or the depth grid averaged over each subbasin."""
    if cfg.storm.depth_grid is None:
        return storm
    from wadi2d.hydrology.from_hms import grid_storm
    from wadi2d.storm.grid_depth import DepthGrid

    h = cfg.hydrology
    if h.hms_sqlite is None:
        raise InvalidJob("a depth grid on a lumped network needs hydrology.hms_sqlite for the polygons")
    system = hms_basin.spatial.coordinate_system if hms_basin.spatial is not None else None
    try:
        rain = grid_storm(
            storm, DepthGrid.load(cfg.storm.depth_grid, system or crs or None), basin, h.hms_sqlite, True
        )
    except KeyError as error:
        raise InvalidJob(f"no polygon for subbasin {error} in hydrology.hms_sqlite") from error
    return rain("", cfg.storm.storm_area_km2)


def _check_routes(h, basin, wanted) -> None:
    """Every lumped subbasin's water enters once: dropped water and doubled water both end in exit 0."""
    lumped = {s.name: s for s in h.subbasins if s.mode == "lumped"}
    known = set(basin.subbasins) if basin is not None else set()
    carried: dict[str, str] = {}
    for name, _point, element in wanted:
        if basin is None or element not in basin.elements:
            raise InvalidJob(f"inflow {name}: element {element} is not in the basin")
        if element in lumped and lumped[element].outlet is not None and name == element:
            continue
        for sub in basin.upstream_of(element) & known:
            carried[sub] = name
    tabled = {i.name for i in h.inflows if i.element is None}
    for name, sub in lumped.items():
        if name in carried and sub.outlet is not None:
            raise InvalidJob(f"subbasin {name} enters twice: at its outlet and in inflow {carried[name]}")
        if name not in carried and sub.outlet is None and name not in tabled:
            raise InvalidJob(
                f"lumped subbasin {name} has no way in: its rain is masked and its hydrograph would be dropped; "
                "give it an outlet, an inflow from an element below it, or a table inflow of the same name"
            )
    for sub, inflow in carried.items():
        if sub not in lumped:
            raise InvalidJob(
                f"inflow {inflow} carries subbasin {sub}: list it as lumped, or its rain falls twice"
            )


def hydrographs(
    cfg: RunConfig, storm, crs: str = ""
) -> list[tuple[str, tuple[float, float], np.ndarray, np.ndarray]]:
    """Every (name, point, times, flows) that enters the 2D domain; the lumped engine runs here if needed."""
    h = cfg.hydrology
    table = [
        (i.name, (i.x, i.y), np.asarray(i.times_s, np.float64), np.asarray(i.flows, np.float64))
        for i in h.inflows
        if i.element is None
    ]
    wanted = [(i.name, (i.x, i.y), i.element) for i in h.inflows if i.element is not None]
    wanted += [(s.name, s.outlet, s.name) for s in h.subbasins if s.mode == "lumped" and s.outlet is not None]
    if not wanted:
        _check_routes(h, None, [])
        return table
    if h.hms_basin is None:
        raise InvalidJob("a lumped inflow needs hydrology.hms_basin")
    if storm is None:
        raise InvalidJob("a lumped inflow needs a storm")
    from wadi2d.hms import load_basin
    from wadi2d.hydrology.from_hms import basin_from_hms
    from wadi2d.hydrology.model import TimeGrid
    from wadi2d.hydrology.network import LumpedEngine

    hms_basin = load_basin(h.hms_basin)
    basin = basin_from_hms(hms_basin, _project_tables(h, hms_basin))
    _check_routes(h, basin, wanted)
    steps = int(np.ceil(cfg.run.duration_s / SECONDS_PER_MINUTE / h.time_step_min))
    grid = TimeGrid(h.time_step_min, steps)
    run = LumpedEngine(basin).run(_lumped_rain(cfg, storm, basin, hms_basin, crs), grid)
    times = grid.minutes * SECONDS_PER_MINUTE
    for name, point, element in wanted:
        table.append((name, point, times, run.outflow[element]))
    return table


@dataclass
class RunSummary:
    """What a run reports to its caller."""

    exit_code: int = EXIT_UNEXPECTED
    status: str = "failed"
    message: str = ""
    t_end: float = 0.0
    steps: int = 0
    tables_s: float = 0.0
    loop_s: float = 0.0
    wet_area_km2: float = 0.0
    dt_min: float = 0.0
    balance: Balance = field(default_factory=Balance)
    peaks: dict[str, tuple[float, float]] = field(default_factory=dict)
    backend: str = ""
    cells: int = 0


def _failed_cell(model: Model) -> dict[str, float]:
    """Where it broke: the first non-finite cell, else the fastest wave."""
    grid = model.grid
    h, d = model.field("h"), model.field("d")
    u, v = model.field("u"), model.field("v")
    speed = np.nan_to_num(np.hypot(u, v), nan=np.inf) + np.sqrt(G * np.maximum(np.nan_to_num(d), 0.0))
    bad = ~(np.isfinite(h) & np.isfinite(u) & np.isfinite(v))
    if bad.any():
        j, i = (int(a) for a in np.argwhere(bad)[0])
    else:
        j, i = (int(a) for a in np.unravel_index(np.argmax(np.where(grid.mask, speed, 0.0)), speed.shape))
    x, y = grid.xy_of(np.array(j), np.array(i))
    return {"j": j, "i": i, "x": float(x), "y": float(y), "wave": float(speed[j, i])}


def arf_tags(cfg: RunConfig) -> dict[str, str]:
    """What every output of an area-reduced run says about its rain."""
    arf = cfg.storm.arf
    if arf is None or cfg.storm.storm_area_km2 is None:
        return {}
    return {"arf_table_type": arf.table_type, "storm_area_km2": str(cfg.storm.storm_area_km2)}


def status_tags(summary: RunSummary, t: float, cfg: RunConfig) -> dict[str, str]:
    """A map says how it was made: a stopped run's maxima are maxima so far, not the event's."""
    return {
        "run_status": summary.status,
        "partial": str(summary.status != "finished").lower(),
        "t_end_s": f"{t:.3f}",
        "duration_s": f"{cfg.run.duration_s:.3f}",
    }


def edge_ponding(grid: TileGrid, depth: np.ndarray, open_cells: np.ndarray) -> tuple[float, float, float]:
    """Deepest water on the domain edge away from any boundary: (depth, x, y).

    An edge is a wall. Water deep against one is a domain drawn too tight or a gap between polygons, and the
    balance closes all the same, so nothing else would tell.
    """
    edge = grid.mask & ~ndimage.binary_erosion(grid.mask, border_value=0)
    closed = edge & ~ndimage.binary_dilation(open_cells, iterations=EDGE_REACH)
    if not closed.any():
        return 0.0, 0.0, 0.0
    j, i = (int(a) for a in np.unravel_index(np.argmax(np.where(closed, depth, -1.0)), depth.shape))
    x, y = grid.xy_of(j, i)
    return float(depth[j, i]), float(x), float(y)


def _write_outputs(cfg, tables, monitor: Monitor, results: Results, out: Path, crs, progress, tags) -> None:
    fields_ = monitor.maxima.fields()
    grid = tables.grid
    arrived = fields_["arrival"] >= 0.0
    level = tables.zmin + fields_["depth"]
    maps = {
        "max_depth": (fields_["depth"], None),
        "max_level": (level, fields_["depth"] > 0.0),
        "max_speed": (fields_["speed"], None),
        "hazard": (fields_["hazard"], None),
        "arrival": (fields_["arrival"], arrived),
        "max_mean_depth": (fields_["mean_depth"], None),
    }
    for name, (data, valid) in maps.items():
        write_map(out / "maps" / f"{name}.tif", data, grid, crs, valid, tags)
    results.maxima(fields_)
    deep, x, y = edge_ponding(grid, fields_["depth"], monitor.boundary.mask)
    if deep > cfg.outputs.edge_depth:
        progress.emit(
            "warn",
            message=f"water stood {deep:.1f} m deep against the domain edge at ({x:.0f}, {y:.0f}): "
            "an edge is a wall, so check the domain polygon there",
        )
    t = np.asarray(monitor.times)
    for s in monitor.series + monitor.line_series:
        columns = {k: np.asarray(v) for k, v in s.columns.items()}
        results.series(s.kind, s.name, t, columns)
        write_series_csv(out / "series" / f"{s.kind[:-1]}_{safe_name(s.name)}.csv", t, columns)
    progress.emit("output", kind="maps", path=str(out / "maps"))


def preflight(cfg: RunConfig, crs: str):
    """Everything that can refuse a job without a grid; it comes before the tables, which can take minutes."""
    storm = build_storm(cfg)
    polygons = load_polygons(cfg.hydrology, crs)
    return storm, polygons, hydrographs(cfg, storm, crs)


def spillway_notes(cfg: RunConfig) -> list[str]:
    """A spillway far longer than its line passes less than its rating: the cells beside it starve it."""
    notes = []
    for obj in cfg.terrain.objects:
        if obj.kind == "spillway" and obj.length is not None:
            drawn = float(line_lengths(obj.coordinates)[-1])
            if obj.length > cfg.terrain.spillway_stretch * drawn:
                notes.append(
                    f"spillway of {obj.length:g} m drawn on {drawn:g} m: it will pass less than C L H^1.5; "
                    "draw its true length"
                )
    return notes


def _check_resume(cfg: RunConfig, checkpoint: Path, resume: bool, progress: Progress) -> bool:
    """Whether this run continues a checkpoint; a checkpoint of another job is refused, before anything is written."""
    if not resume:
        return False
    if not checkpoint.exists():
        progress.emit("warn", message="no checkpoint in this folder: the run starts from the beginning")
        return False
    saved = checkpoint_job(checkpoint)
    if saved is None:
        raise InvalidJob(f"{checkpoint.name} is damaged or too old to resume: run without --resume")
    if saved != job_hash(cfg):
        raise InvalidJob(
            f"{checkpoint.name} was made by another job or other input files: resuming would give a result that "
            "belongs to neither; run without --resume in a new folder"
        )
    return True


def _run(cfg, out: Path, backend, tables, resume, progress, summary: RunSummary, stop_files) -> None:
    check_inputs(cfg)
    checkpoint = out / "checkpoint.h5"
    continuing = _check_resume(cfg, checkpoint, resume, progress)
    (out / "config.resolved.json").write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
    t0 = time.monotonic()
    if tables is not None:
        tables, crs = tables
    else:
        with rasterio.open(cfg.terrain.dem) as dem:
            crs = dem.crs.to_wkt() if dem.crs is not None else ""
    storm, polygons, flows = preflight(cfg, crs)
    still = storm is None and not flows and not cfg.initial_levels
    if still and not any(b.kind == "stage" for b in cfg.boundaries):
        progress.emit("warn", message="no rain, no inflow and no stage boundary: nothing will happen")
    if cfg.storm.depth_grid is not None:
        progress.emit(
            "warn",
            message="depth grid: 2D cells take the raster's own depth, lumped subbasins their polygon mean; "
            "HMS with Uniform Depth: Yes uses the mean above each analysis point instead",
        )
    for note in spillway_notes(cfg):
        progress.emit("warn", message=note)
    if tables is None:
        cache = Path(cfg.grid.cache_dir) if cfg.grid.cache_dir else out / "cache"
        tables, crs = prepare_grid(cfg, cache, progress)
    summary.tables_s = time.monotonic() - t0
    grid = tables.grid
    summary.cells = grid.cell_count if getattr(grid, "quad", False) else int(grid.mask.sum())
    name = backend or cfg.run.backend
    try:
        model = Model(tables, cfg.numerics, name)
    except (RuntimeError, ImportError, OSError) as error:
        raise BackendUnavailable(str(error)) from error
    summary.backend = model.backend.name
    bset = boundary_set(cfg.boundaries, tables, cfg.grid.line_samples)
    model.set_depth(initial_depth(cfg.initial_levels, tables))
    if bset.size:
        model.set_boundary(bset.cells)
    forcing = Forcing(cfg, tables, model, bset, storm, polygons, flows, crs)

    results = Results(out / "results.h5", grid, crs, cfg.model_dump_json(), append=continuing)
    if results.salvaged:
        progress.emit(
            "warn", message="results.h5 was left unreadable by a kill: snapshots before it are lost"
        )
    monitor = Monitor(cfg, tables, model, bset, results, progress, out, crs, stop_files)
    monitor.balance.storage0 = monitor.storage()
    if continuing:
        load_checkpoint(checkpoint, model, monitor)
    key = job_hash(cfg)
    progress.emit(
        "start", backend=summary.backend, cells=summary.cells, tiles=grid.ntiles - 1, dx=grid.dx,
        duration_s=cfg.run.duration_s, tables_s=round(summary.tables_s, 2), t=model.stepper.t,
    )  # fmt: skip

    t1 = time.monotonic()
    t = model.stepper.t
    end = cfg.run.duration_s
    dry = False
    try:
        if monitor.stop_requested():
            raise StopRequested
        while t < end - 1e-9:
            t_next = min(t + cfg.run.source_every_s, end)
            rate, rain, inflow = forcing.rate(t, t_next)
            if rain + inflow > 0.0 or not dry:
                model.set_source_cells(forcing.state, rate)
            dry = rain + inflow <= 0.0
            monitor.open_window(t, t_next, rain, inflow)
            model.advance(t_next, monitor.on_step)
            monitor.settle(t_next)
            t = t_next
            if monitor.checkpoint_due:
                monitor.checkpoint_due = False
                save_checkpoint(checkpoint, model, monitor, key)
        summary.exit_code, summary.status = EXIT_DONE, "finished"
    except StopRequested:
        monitor.settle(model.stepper.t)
        save_checkpoint(checkpoint, model, monitor, key)
        summary.exit_code, summary.status = EXIT_STOPPED, "stopped"
    except NumericalFailure as error:
        summary.loop_s = time.monotonic() - t1
        where = _failed_cell(model)
        summary.exit_code, summary.status = EXIT_NUMERICAL, "numerical failure"
        summary.message = f"{error} at cell {where}"
        progress.emit("error", code=EXIT_NUMERICAL, message=str(error), cell=where)
        _finish(cfg, tables, model, monitor, results, out, crs, progress, summary, t1)
        return
    _finish(cfg, tables, model, monitor, results, out, crs, progress, summary, t1)


def _finish(cfg, tables, model, monitor, results, out, crs, progress, summary, t1) -> None:
    st = model.stepper
    monitor.finish(st.t)
    monitor.stop_file.unlink(missing_ok=True)
    tags = {**arf_tags(cfg), **status_tags(summary, st.t, cfg)}
    _write_outputs(cfg, tables, monitor, results, out, crs, progress, tags)
    summary.loop_s = time.monotonic() - t1
    summary.t_end, summary.steps, summary.balance = st.t, st.nsteps, monitor.balance
    summary.dt_min = monitor.dt_min
    mean_depth = monitor.maxima.fields()["mean_depth"]
    wet = int(np.count_nonzero(mean_depth >= cfg.outputs.wet_depth))
    summary.wet_area_km2 = wet * tables.grid.dx**2 / M2_PER_KM2
    t = np.asarray(monitor.times)
    for s in monitor.line_series:
        q = np.abs(np.asarray(s.columns["discharge_m3s"]))
        if q.size:
            summary.peaks[s.name] = (float(q.max()), float(t[int(np.argmax(q))]))
    b = monitor.balance
    balance = {
        "rain_m3": b.rain, "inflow_m3": b.inflow, "outflow_m3": b.outflow, "storage_start_m3": b.storage0,
        "storage_end_m3": b.storage, "error_m3": b.error, "relative_error": b.relative,
    }  # fmt: skip
    results.attributes({"status": summary.status, "t_end_s": st.t, "steps": st.nsteps, **balance, **tags})
    results.close()
    progress.emit(
        "done",
        status=summary.status, code=summary.exit_code, partial=summary.status != "finished", t=st.t,
        duration_s=cfg.run.duration_s, steps=st.nsteps, loop_s=round(summary.loop_s, 2),
        tables_s=round(summary.tables_s, 2), wet_area_km2=round(summary.wet_area_km2, 4),
        dt_min=summary.dt_min, balance=balance, tile_steps=getattr(st, "tile_steps", None),
    )  # fmt: skip


def run_job(
    cfg: RunConfig,
    out: str | Path,
    backend: str | None = None,
    tables: tuple[GridTables, str] | None = None,
    resume: bool = False,
    echo: bool = False,
    stop_files: Iterable[Path] = (),
) -> RunSummary:
    """Run one job into folder ``out``. ``tables`` reuses a grid already in memory: (tables, CRS WKT).

    ``out/stop`` stops the run, and so does any of ``stop_files``; a stop that was there first stops it at once.
    """
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    summary = RunSummary()
    with Progress(folder / "progress.jsonl", echo=echo, append=resume) as progress:
        try:
            _run(cfg, folder, backend, tables, resume, progress, summary, tuple(stop_files))
        except JobError as error:
            summary.exit_code, summary.message = error.code, str(error)
            progress.emit("error", code=error.code, message=str(error))
        except (FileNotFoundError, rasterio.errors.RasterioIOError) as error:
            summary.exit_code, summary.message = EXIT_INPUT, str(error)
            progress.emit("error", code=EXIT_INPUT, message=str(error))
        except ValueError as error:
            summary.exit_code, summary.message = EXIT_INVALID, str(error)
            progress.emit("error", code=EXIT_INVALID, message=str(error))
        except Exception as error:  # the protocol wants a code and an event, never a traceback alone
            memory = isinstance(error, MemoryError) or type(error).__name__ == "OutOfMemoryError"
            summary.exit_code = EXIT_MEMORY if memory else EXIT_UNEXPECTED
            summary.message = str(error)
            progress.emit("error", code=summary.exit_code, message=str(error), trace=traceback.format_exc())
    return summary


__all__ = [
    "InputMissing",
    "InvalidJob",
    "JobError",
    "RunSummary",
    "load_job",
    "preflight",
    "prepare_grid",
    "resolve_paths",
    "run_job",
]
