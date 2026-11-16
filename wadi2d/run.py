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
from datetime import datetime
from pathlib import Path

import numpy as np
import rasterio
import shapely
from pydantic import ValidationError
from rasterio import features
from rasterio.transform import Affine
from scipy import ndimage

from wadi2d.breach import build_breaches
from wadi2d.config.constants import M2_PER_KM2, G
from wadi2d.config.rain import PART_GRID, PART_LUMPED, absolute_store
from wadi2d.config.schema import (
    DEPTH_GRID_STORM,
    ENTRY_POINT,
    FILL_KIND,
    LUMPED_AT_OUTLETS,
    REACH_HMS,
    SHAPED_KINDS,
    RunConfig,
    Terrain,
    TerrainObject,
)
from wadi2d.dam_levels import grid_pool_depth, with_dam_starts
from wadi2d.demstore import cache_folder, open_bed
from wadi2d.edge_valleys import (
    crossing_notes,
    edge_pools,
    pool_notes,
    stream_crossings,
    write_crossings,
    write_pools,
)
from wadi2d.engine.design_lines import DESIGN_KIND, NETWORK, TOTAL
from wadi2d.engine.design_lines import plans as design_plans
from wadi2d.engine.design_lines import records as design_records
from wadi2d.engine.entries import place_entries, with_entries, with_snapped
from wadi2d.engine.gauge_job import (
    gauge_identity,
    missing_station_files,
    report_gauges,
    report_observed,
    resolve_station_paths,
)
from wadi2d.engine.handback import HandBackLink, line_labels, sink_lines
from wadi2d.engine.inflow_lines import flow_lines, line_injections, momentum_kick, momentum_lines, open_lines
from wadi2d.engine.left_out import LeftOut, cells_key, choose, snap_entries
from wadi2d.engine.line_checks import inflow_crossings
from wadi2d.engine.monitor import Balance, Monitor, StopRequested
from wadi2d.engine.pit_rebuild import fill_tiles, fills_follow, strip_base, strip_untouched
from wadi2d.engine.pit_step import resolve_pits
from wadi2d.engine.rain_once import check_rain_once
from wadi2d.engine.transmission import BedLoss
from wadi2d.forcing import (
    Forcing,
    boundary_notes,
    boundary_set,
    build_storm,
    initial_depth,
    load_polygons,
    manning_grid,
)
from wadi2d.grid.quad import lattice_view
from wadi2d.grid.tiles import TileGrid
from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
from wadi2d.hydrology.model import Reservoir
from wadi2d.io.cache import (
    builder_identity,
    cache_key,
    cache_path,
    load_mask,
    load_tables,
    mask_path,
    save_mask,
    save_tables,
)
from wadi2d.io.checkpoint import checkpoint_job, load_checkpoint, save_checkpoint
from wadi2d.io.identity import file_identity
from wadi2d.io.progress import Progress
from wadi2d.io.results import Results, safe_name, write_series_csv
from wadi2d.products.cell_grid import write_cell_grid
from wadi2d.products.runner import PRODUCTS_NONE, make_after_run
from wadi2d.solver.model import Model
from wadi2d.solver.stepper import NumericalFailure
from wadi2d.storm.gauges import GaugeStorm
from wadi2d.storm.gridded import GriddedStorm
from wadi2d.storm.split_arf import (
    at_study_area,
    grid_curve,
    lumped_curve,
    part_record,
    part_reduction,
    part_words,
    with_reduction,
)
from wadi2d.tables import GridTables, build_tables
from wadi2d.terrain import GridWindow, Ground, RasterBed, apply_objects
from wadi2d.terrain.checks import terrain_notes
from wadi2d.terrain.crest import line_lengths
from wadi2d.terrain.pits import is_pit_fill
from wadi2d.terrain.report import TerrainReport, survey
from wadi2d.terrain.sections import with_tables
from wadi2d.terrain.vector import read_features

EXIT_DONE, EXIT_UNEXPECTED, EXIT_INVALID, EXIT_INPUT, EXIT_BACKEND = 0, 1, 2, 3, 4
EXIT_NUMERICAL, EXIT_STOPPED, EXIT_MEMORY = 5, 6, 7
EDGE_REACH = 2
"""Cells around a boundary that do not count as a closed edge."""
TERRAIN_DIR = "terrain"
"""Folder of a run that holds what the terrain objects did."""
ENTRIES_FILE = "entries.json"
"""Where each 'wadi' entry of a run was asked for, where it entered, and why (W41)."""
PIXEL_KINDS = (*SHAPED_KINDS, "burn_line", FILL_KIND)
"""Terrain objects that change the ground, not only faces."""


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
    ("storm", "rain_file"),
    ("hydrology", "hms_basin"),
    ("hydrology", "hms_project"),
    ("hydrology", "hms_sqlite"),
    ("hydrology", "basin_json"),
    ("hydrology", "polygons"),
    ("transmission", "area"),
    ("arf", "accumulation"),
)
"""Every path in a job; relative paths are relative to the job file."""
OPTIONAL_INPUT = {("grid", "cache_dir")}
NOT_WATER = (
    ("run", "backend"),
    ("run", "checkpoint_every_s"),
    ("grid", "cache_dir"),
    ("outputs", "pixels"),
    ("outputs", "smooth"),
    ("outputs", "slider"),
    ("outputs", "frame_bytes_per_cell"),
    ("outputs", "face_discharge"),
    ("outputs", "observed"),
    ("outputs", "edge_check"),
    ("outputs", "step_limiter"),  # a reading of the step, not the water: an old job's checkpoint keeps its hash (W85)
    ("terrain", "pit_check"),  # the same: it names pits and changes nothing
    ("hydrology", "overlap_share"),
    ("arf", "bracket"),
    ("arf", "bracket_ratio"),
    ("arf", "bracket_max"),
    ("arf", "by_arf_step"),  # how a study picks its areas, and whether it maps: no run's water (W53)
    ("arf", "arf_step_max"),
    ("arf", "composite"),
)
"""Settings a checkpoint need not match: none of them changes the water."""
GIVEN_FACTOR = "given"
"""What a run with ``storm.arf_factor`` says its area reduction is: a factor given, read from no table (W83)."""


def load_job(path: str | Path) -> RunConfig:
    """Parse and validate a job file; relative paths become absolute."""
    source = Path(path)
    if not source.is_file():
        raise InputMissing(f"job file not found: {source}")
    try:
        cfg = RunConfig.model_validate(absolute_store(json.loads(source.read_text(encoding="utf-8")), source.parent))
    except (ValidationError, json.JSONDecodeError) as error:
        raise InvalidJob(str(error)) from error
    return resolve_paths(cfg, source.parent)


def resolve_paths(cfg: RunConfig, base: Path) -> RunConfig:
    """The same job with every path absolute."""
    updates: dict[str, dict] = {}
    for part, name in PATH_FIELDS:
        value = getattr(getattr(cfg, part), name)
        if value is not None and not Path(value).is_absolute():
            updates.setdefault(part, {})[name] = str((base / value).resolve())
    if any(_table(o) for o in cfg.terrain.objects):
        updates.setdefault("terrain", {})["objects"] = [_absolute_table(o, base) for o in cfg.terrain.objects]
    cfg = cfg.model_copy(update={p: getattr(cfg, p).model_copy(update=u) for p, u in updates.items()})
    return resolve_station_paths(cfg, base)


def _table(obj: TerrainObject) -> str | None:
    return obj.section.table if obj.section is not None else None


def _absolute_table(obj: TerrainObject, base: Path) -> TerrainObject:
    table = _table(obj)
    if table is None or Path(table).is_absolute():
        return obj
    section = obj.section.model_copy(update={"table": str((base / table).resolve())})
    return obj.model_copy(update={"section": section})


def check_inputs(cfg: RunConfig) -> None:
    """Every input file must exist before anything expensive starts; a lumped-only run needs no ground (W88)."""
    if cfg.terrain.dem is None and not cfg.run.lumped_only:
        raise InvalidJob("terrain.dem is required")
    if cfg.grid.extent is None and cfg.grid.domain is None and not cfg.run.lumped_only:
        raise InvalidJob("grid.extent or grid.domain is required")
    for part, name in PATH_FIELDS:
        value = getattr(getattr(cfg, part), name)
        if value is not None and (part, name) not in OPTIONAL_INPUT and not Path(value).exists():
            raise InputMissing(f"{part}.{name} not found: {value}")
    for obj in cfg.terrain.objects:
        table = _table(obj)
        if table is not None and not Path(table).exists():
            raise InputMissing(f"section table of {obj.name or obj.kind} not found: {table}")
    for missing in missing_station_files(cfg):
        raise InputMissing(missing)


def _domain_polygon(path: str | None, crs: str) -> shapely.Geometry | None:
    if path is None:
        return None
    return shapely.union_all([shape for _properties, shape in read_features(path, crs)])


def _wkt(bed: RasterBed) -> str:
    return bed.crs.to_wkt() if bed.crs is not None else ""


def domain_mask(cfg: RunConfig, bed: RasterBed, window: GridWindow) -> np.ndarray:
    """Active cells: data under the centre pixel, inside the domain polygon if there is one."""
    polygon = _domain_polygon(cfg.grid.domain, _wkt(bed))
    if polygon is None:
        return bed.active_mask(window, cfg.grid.dx)
    transform = Affine(cfg.grid.dx, 0.0, window.x0, 0.0, -cfg.grid.dx, window.y0)
    inside = features.geometry_mask([polygon], out_shape=(window.ny, window.nx), transform=transform, invert=True)
    if hasattr(bed, "active_cells"):  # a bed on the chunk store reads the ground of the outline's cells alone (W84)
        return bed.active_cells(window, cfg.grid.dx, inside)
    return bed.active_mask(window, cfg.grid.dx) & inside


def kept_domain_mask(cfg: RunConfig, bed: RasterBed, window: GridWindow, cache_dir: Path) -> np.ndarray:
    """``domain_mask`` from the grid cache when the DEM, the window, the cell and the domain are the ones it was read
    for; made and kept there otherwise. On Block 2 the mask is half a minute of every start (W50)."""
    key = cache_key(
        {
            "mask": builder_identity(),
            "dem": bed.identity(cfg.grid.content_hash_limit_mb),
            "window": [window.x0, window.y0, window.ny, window.nx],
            "dx": cfg.grid.dx,
            "domain": None if cfg.grid.domain is None else file_identity(cfg.grid.domain, cfg.grid.content_hash_limit_mb),
        }
    )
    path = mask_path(cache_dir, key)
    mask = load_mask(path, key)
    if mask is None or mask.shape != (window.ny, window.nx):
        mask = domain_mask(cfg, bed, window)
        save_mask(path, mask, key)
    return mask


def grid_window(cfg: RunConfig, bed: RasterBed) -> GridWindow:
    polygon = _domain_polygon(cfg.grid.domain, _wkt(bed))
    extent = cfg.grid.extent if polygon is None else polygon.bounds
    return bed.snap(extent, cfg.grid.dx)


def grid_key(
    cfg: RunConfig,
    bed: RasterBed,
    window: GridWindow,
    replaced: tuple[np.ndarray, np.ndarray] | None = None,
    left_out: np.ndarray | None = None,
) -> str:
    """Hash of everything the tables depend on; ``replaced`` are the (j, i) of the lattice cells a strip takes out,
    and ``left_out`` the cells under the catchments left out of the mesh (W88): both shape the mask the tables are
    built on. A job that leaves nothing out keeps the key it had."""
    limit = cfg.grid.content_hash_limit_mb
    strip_cells = None
    if replaced is not None and replaced[0].size:
        import hashlib

        strip_cells = hashlib.sha1(np.ascontiguousarray(np.stack(replaced).astype(np.int64)).tobytes()).hexdigest()
    extras = {
        key: file_identity(name, limit)
        for key, name in (
            ("domain", cfg.grid.domain),
            ("manning", cfg.terrain.manning_raster),
            ("banks", cfg.strips.banks if cfg.strips.enabled else None),
        )
        if name is not None
    }
    t = cfg.terrain
    return cache_key(
        {
            "builder": builder_identity(),
            "dem": bed.identity(limit),
            "window": [window.x0, window.y0, window.ny, window.nx],
            "dx": cfg.grid.dx,
            "objects": [_object_key(o) for o in t.objects],
            "object_settings": [
                t.join_cells,
                t.spillway_snap_cells,
                t.burn_pixels,
                t.dyke_min_height,
                t.crest_thin_ratio,
                t.crest_eased_ratio,
                t.crest_resolved_ratio,
                t.crest_eased_coefficient,
            ],
            "tables": cfg.tables.model_dump(),
            "manning": t.manning,
            "extras": extras,
            **({"strips": cfg.strips.model_dump()} if cfg.strips.enabled else {}),
            **({"strip_cells": strip_cells} if strip_cells is not None else {}),
            **({"left_out": cells_key(left_out)} if left_out is not None else {}),
        }
    )


def _object_key(obj: TerrainObject) -> dict:
    """An object as the cache sees it: a section table's numbers, not where the file lies."""
    data = obj.model_dump()
    data.pop("delineate")  # the basin generator's, not the tables' (W73)
    if data["section"] is not None:
        data["section"]["table"] = None
    return data


def _drop_point_entries(hydrology: dict) -> None:
    """A job that asks for no 'wadi' entry hashes as it did before entries existed, so its checkpoint keeps."""
    items = [*hydrology["subbasins"], *hydrology["inflows"]]
    for item in items:
        if item.get("entry") == ENTRY_POINT:
            item.pop("entry")
    if not any("entry" in item for item in items):
        hydrology.pop("entry_erode_m")


def job_hash(cfg: RunConfig) -> str:
    """What a checkpoint must match: everything that changes the water, the input files included."""
    data = cfg.model_dump(mode="json")
    for part, name in NOT_WATER:
        data[part].pop(name)
    data.pop("project")
    data.pop("basin")  # how basin.json was made; the file's own bytes are hashed below
    # the pit fills are made from the three settings below and the ground, all hashed: the job as given and the job
    # as it runs (with its fills) are one job, and one without the fill keeps the hash it had before it (W85)
    data["terrain"]["objects"] = [
        obj for obj, kept in zip(data["terrain"]["objects"], cfg.terrain.objects, strict=True) if not is_pit_fill(kept)
    ]
    if not cfg.terrain.fill_pits:
        for name in ("fill_pits", "pit_max_cells", "pit_min_depth"):
            data["terrain"].pop(name)
    for obj in data["terrain"]["objects"]:
        obj.pop("delineate", None)  # the same: it shapes basin.json only (W73)
    if not cfg.hydrology.handbacks:
        data["hydrology"].pop("handbacks")
    if not cfg.transmission.enabled:
        data.pop("transmission")
    if cfg.hydrology.reach_routing == REACH_HMS:  # an old job's checkpoint keeps its hash
        data["hydrology"].pop("reach_routing")
    if not cfg.hydrology.muskingum:  # and the hash it had before Muskingum reaches existed (W89)
        data["hydrology"].pop("muskingum")
    if not cfg.dam_levels:
        data.pop("dam_levels")
    if not cfg.breaches:
        data.pop("breaches")  # a job without a breach keeps the hash it had before breaches existed (W63)
    for breach in data.get("breaches", []):  # and a W63 estimator the hash it had before W76's two fields
        estimator = breach.get("estimator") or {}
        if estimator.get("erodibility_class") == "medium" and estimator.get("dam_height_m") is None:
            estimator.pop("erodibility_class")
            estimator.pop("dam_height_m")
    if not cfg.strips.enabled:
        data.pop("strips")  # a job without strips keeps the hash it had before strips existed
    if cfg.storm.gauges is None:
        data["storm"].pop("gauges")  # and a job without gauges the one it had before them (W54)
    if cfg.storm.arf_factor is None:
        data["storm"].pop("arf_factor")  # and a job with no given factor the one it had before it (W83)
    for name in ("pattern", "area_reduction"):  # and a job of the old kinds the one it had before W95's sources
        if data["storm"][name] is None:
            data["storm"].pop(name)
    if data["storm"].get("pattern") is not None:  # a stored table's name is not water: its numbers, filled in, are
        data["storm"]["pattern"].pop("table")
    for part in (data["storm"].get("area_reduction") or {}).values():
        if part is not None:
            part.pop("curve")
    data.pop("data_tables")  # the tables a storm names are in the storm by now; the rest change no water (W95)
    if not cfg.grid.exclude_lumped and not cfg.grid.exclude_subbasins:  # and one that leaves no catchment out (W88)
        for name in ("exclude_lumped", "exclude_subbasins"):
            data["grid"].pop(name)
        data["hydrology"].pop("entry_snap_m")
    if cfg.hydrology.lumped_entry == LUMPED_AT_OUTLETS:  # and the lumped water at the outlets, as always (W88)
        data["hydrology"].pop("lumped_entry")
    if not cfg.hydrology.arf_by_element:
        data["hydrology"].pop("arf_by_element")
    if not cfg.run.lumped_only:
        data["run"].pop("lumped_only")
    for inflow in data["hydrology"]["inflows"]:
        if inflow.get("enters", True):
            inflow.pop("enters", None)
    for sub in data["hydrology"]["subbasins"]:
        if sub.get("storm_area_km2") is None:
            sub.pop("storm_area_km2", None)  # and a subbasin at the storm's own area the one it had before (W79)
    _drop_point_entries(data["hydrology"])
    for line in data["boundaries"]:  # a job without flow lines keeps the hash it had before them (W61)
        for key in ("name", "flow"):
            if line.get(key) is None:
                line.pop(key, None)
    limit = cfg.grid.content_hash_limit_mb
    files = {}
    for n, b in enumerate(cfg.boundaries):
        if b.flow is not None and b.flow.file is not None:
            files[f"boundaries.{n}.flow.file"] = file_identity(b.flow.file, limit)
    for part, name in PATH_FIELDS:
        value = getattr(getattr(cfg, part), name)
        if value is not None and (part, name) not in OPTIONAL_INPUT:
            files[f"{part}.{name}"] = file_identity(value, limit)
    files.update(gauge_identity(cfg, limit))
    return cache_key({"job": data, "files": files})


FIND = "find"
"""``prepare_grid`` works out what the job leaves out of the mesh itself; a run that already knows passes it."""


class NothingOnTheGrid(InvalidJob):
    """Every cell of the domain lies under a catchment left out of the mesh: the job is a lumped run (W88)."""


def prepare_grid(
    cfg: RunConfig,
    cache_dir: Path,
    progress: Progress | None = None,
    left_out: LeftOut | str | None = FIND,
    base: GridTables | None = None,
) -> tuple[GridTables, str]:
    """The tables and the CRS as WKT, from the cache when nothing changed. The tables carry ``left_out``, the
    catchments the job leaves out of the mesh (None for none).

    ``base`` is the tables of this same job before its pit fills (``resolve_pits``, W85): the strip's mesh is taken
    from it, only the tiles the fills reach are built again, and the strip's tables are its own when no fill lies near
    the strip (W91), each the whole build's to the digit."""
    emit = progress.emit if progress is not None else (lambda *_a, **_k: None)
    cfg = with_tables(cfg)
    with open_bed(cfg, cache_dir) as bed:  # the DEM decoded once into the cache folder, then read raw (W84)
        crs = _wkt(bed)
        window = grid_window(cfg, bed)
        left = left_out_of(cfg, crs) if isinstance(left_out, str) else left_out
        if cfg.mesh.enabled:
            if cfg.strips.enabled:
                raise InvalidJob("corridors run on the uniform grid in this version: untick the mesh refinement or the corridors")
            tables = _mesh_tables(cfg, bed, window, crs, left)
            tables.left_out = left
            return tables, crs
        mask = kept_domain_mask(cfg, bed, window, cache_dir)
        if not mask.any():
            raise InvalidJob("the domain holds no active cell")
        domain = mask
        """The domain's active cells before any catchment is left out: the strip's floor rule reads them (W92)."""
        gone = None
        """The domain's cells under the left-out catchments, or None when the job leaves none out."""
        if left is not None and left.names:
            gone = left.cells(window.x0, window.y0, cfg.grid.dx, mask.shape) & mask
            mask = mask & ~gone
            left.cells_out = int(gone.sum())
            if not mask.any():
                raise NothingOnTheGrid(_NOTHING_ON_THE_GRID)
        strip = None
        made = None
        """The strip's mesh and tables from the cache, or None: built below and saved (W81)."""
        if cfg.strips.enabled:
            from wadi2d.io.cache import load_strip, strip_path

            spath = strip_path(cache_dir, strip_key(cfg, bed, window, mask))
            held = load_strip(spath, spath.stem.removeprefix("strip_"))
            if held is not None:
                emit("output", kind="strip_cache_hit", path=str(spath))
                mask, made = held
                strip = made.strip
        held_mesh = getattr(base, "strip_mesh", None)
        if cfg.strips.enabled and strip is None and held_mesh is not None:
            mask, strip = held_mesh  # a pit fill shapes no strip mesh: its lines, banks and floors are the job's (W91)
        if cfg.strips.enabled and strip is None:
            from wadi2d.strips.build import mask_for_strips

            polygon = _domain_polygon(cfg.grid.domain, crs)
            if polygon is None:
                polygon = shapely.box(window.x0, window.y0 - mask.shape[0] * cfg.grid.dx, window.x0 + mask.shape[1] * cfg.grid.dx, window.y0)
            if gone is not None:  # corridors built from a banks file end a cell clear of the left-out catchments
                polygon = polygon.difference(left.area.buffer(cfg.grid.dx))
            try:
                mask, strip = mask_for_strips(cfg, mask, window.x0, window.y0, polygon, domain, str(cache_dir))
            except (ValueError, OSError) as error:
                raise InvalidJob(str(error)) from error
        # the strip's cells are part of the key: the tables are built on the mask the strip leaves, and a mesher that
        # draws the strip differently (a code change, with the job unchanged) must not meet the old tables; a cached
        # lattice masked where the new strip is not left a wall between them and ponded 20 m deep at Faydh's outlet
        # across four reruns (2026-11-08)
        key = grid_key(cfg, bed, window, replaced=strip.masked if strip is not None else None, left_out=gone)
        path = cache_path(cache_dir, key)
        hit = load_tables(path, key)
        if hit is not None:
            emit("output", kind="grid_cache_hit", path=str(path))
            tables = hit
        else:
            grid = TileGrid.from_mask(mask, window.x0, window.y0, cfg.grid.dx)
            bed.bind(grid.x0, grid.y0)
            ground = Ground(bed, grid.x0, grid.y0)
            edits = apply_objects(grid, cfg.terrain.objects, bed.pixel, cfg.terrain, ground)
            n = manning_grid(cfg, grid, crs)
            only = fill_tiles(cfg, base, grid, bed)
            tables = build_tables(
                grid, bed, cfg.tables, n, edits.crest, edits.edit, edits.lining, base=base if only is not None else None,
                only=only, keep_raw=fills_follow(cfg),
            )  # fmt: skip
            save_tables(path, tables, key)
            emit("output", kind="grid_cache_saved", path=str(path))
        if cfg.strips.enabled:
            tables.strip_mesh = (mask, strip)  # for the build with the pit fills, if one follows (W91)
        if made is not None:
            tables.strip = made
        elif strip is not None:  # cached with its key since W81: minutes on Block 2, on every start and products remake
            from wadi2d.io.cache import save_strip
            from wadi2d.strips.build import strip_squares, strip_tables

            if strip_untouched(cfg, base, strip):
                tables.strip = base.strip
            else:
                bed.bind(tables.grid.x0, tables.grid.y0)
                jj, ii = np.nonzero(tables.grid.mask)
                sj, si = strip_squares(strip.geometry, tables.grid)  # the squares under the strip left the mask
                cells = (np.concatenate((jj, sj)), np.concatenate((ii, si)))
                n = manning_grid(cfg, tables.grid, crs, cells)
                held, changed = strip_base(cfg, base, strip)  # only the pieces the pit fills reach (W91)
                tables.strip = strip_tables(cfg, tables, bed, strip, n, held, changed, keep_raw=fills_follow(cfg))
                tables.strip_raw = tables.strip.mesh.__dict__.pop("raw", None)  # kept off the cached strip
            save_strip(spath, spath.stem.removeprefix("strip_"), mask, tables.strip)
            emit("output", kind="strip_cache_saved", path=str(spath))
    tables.left_out = left
    return tables, crs


_NOTHING_ON_THE_GRID = (
    "every cell of the domain lies under a catchment left out of the mesh: nothing is left for the 2D model"
)


def _entering(h) -> list[tuple[str, tuple[float, float] | None, str]]:
    """Every (name, point, element) of the lumped network whose outflow enters the grid."""
    wanted = [(i.name, (i.x, i.y), i.element) for i in h.inflows if i.element is not None]
    wanted += [(s.name, s.outlet, s.name) for s in h.subbasins if s.mode == "lumped" and s.outlet is not None]
    return wanted


def carried_subbasins(cfg: RunConfig, crs: str = "") -> dict[str, str]:
    """The carried lumped subbasins of a resolved job, each with the entry that brings its water to the grid (W88):
    lumped, with no outlet of its own, above an inflow's element or the end of a hand-back's route on links the grid
    does not carry. Empty for a job with no lumped network; what a run would refuse is refused there, not here."""
    h = cfg.hydrology
    wanted = _entering(h)
    generated = h.basin_json is not None
    if (not wanted and not h.handbacks and not generated) or (h.hms_basin is None and not generated):
        return {}
    basin, _hms_basin, decided = _lumped_basin(cfg, crs)
    routes = None
    if h.handbacks or generated:
        from wadi2d.hydrology.live_network import plan_routes

        entries = [line.element for line in h.handbacks]
        routes = plan_routes(basin, entries, [e for _n, _p, e in wanted], decided, cut_entries=not generated)
    alone = {s.name for s in h.subbasins if s.mode == "lumped" and s.outlet is None}
    return {sub: entry for sub, entry in _carried(h, basin, wanted, routes).items() if sub in alone}


def left_out_of(cfg: RunConfig, crs: str = "") -> LeftOut | None:
    """What a job leaves out of its mesh, or None when it asks for nothing (:mod:`wadi2d.engine.left_out`)."""
    g = cfg.grid
    if not g.exclude_lumped and not g.exclude_subbasins:
        return None
    cfg = _resolved(cfg, crs)[0]
    try:
        carried = carried_subbasins(cfg, crs) if g.exclude_lumped else {}
        return choose(cfg, carried, load_polygons(cfg.hydrology, crs))
    except ValueError as error:
        raise InvalidJob(str(error)) from error


def strip_key(cfg: RunConfig, bed: RasterBed, window: GridWindow, mask: np.ndarray) -> str:
    """Hash of everything a strip's mesh and tables depend on (W81): the grid's own key without the strip's cells,
    the domain's active cells it is built on, the job's terrain, grid, breakline and boundary settings (the bank
    rule, the cells kept clear round boundary lines) and the code of the strip builder."""
    import hashlib

    from wadi2d.io.cache import STRIP_FORMAT, STRIP_SOURCES, source_identity

    terrain = cfg.terrain.model_dump(mode="json")
    terrain["objects"] = [_object_key(o) for o in cfg.terrain.objects]
    # the pit settings shape no strip: the check changes nothing, and a fill reaches the strip as its objects (W85)
    for name in ("pit_check", "fill_pits", "pit_max_cells", "pit_min_depth"):
        terrain.pop(name, None)
    grid = cfg.grid.model_dump(mode="json")
    grid.pop("cache_dir", None)  # where the cache lies is not what is in it
    for name in ("exclude_lumped", "exclude_subbasins"):  # what they take out is in the mask below (W88)
        grid.pop(name, None)
    return cache_key(
        {
            "strip_format": STRIP_FORMAT,
            "grid_key": grid_key(cfg, bed, window),
            "mask": hashlib.sha1(np.ascontiguousarray(mask, bool).tobytes()).hexdigest() + str(mask.shape),
            "terrain": terrain,
            "grid": grid,
            "breaklines": cfg.breaklines.model_dump(mode="json"),
            "boundaries": [b.model_dump(mode="json") for b in cfg.boundaries],
            "code": source_identity(STRIP_SOURCES),
        }
    )


def mesh_grid(cfg: RunConfig, bed: RasterBed, window: GridWindow, crs: str, left_out: LeftOut | None = None):
    """The quadtree of a job, and every refusal a mesh can give before its tables; ``left_out`` takes the cells
    under its catchments out of the domain first (W88)."""
    from wadi2d.mesh.build import build_grid, lines_on_coarse_tiles

    if cfg.grid.dx < cfg.mesh.min_dx:
        raise InvalidJob(f"grid.dx {cfg.grid.dx} m is below mesh.min_dx {cfg.mesh.min_dx} m")
    mask = domain_mask(cfg, bed, window)
    if not mask.any():
        raise InvalidJob("the domain holds no active cell")
    if left_out is not None and left_out.names:
        gone = left_out.cells(window.x0, window.y0, cfg.grid.dx, mask.shape) & mask
        mask = mask & ~gone
        left_out.cells_out = int(gone.sum())
        if not mask.any():
            raise NothingOnTheGrid(_NOTHING_ON_THE_GRID)
    bed.bind(window.x0, window.y0)
    grid = build_grid(cfg, mask, window.x0, window.y0, crs, Ground(bed, window.x0, window.y0))
    bed.bind(grid.x0, grid.y0)
    stray = lines_on_coarse_tiles(cfg, grid, Ground(bed, grid.x0, grid.y0))
    if stray:
        raise InvalidJob(
            f"{stray} barrier, crest, boundary or design lines reach coarse tiles, where their faces cannot be "
            "read and water would pass them: keep mesh.refine_lines on, or add a refinement zone along them"
        )
    return grid


def _mesh_tables(
    cfg: RunConfig, bed: RasterBed, window: GridWindow, crs: str, left_out: LeftOut | None = None
) -> GridTables:
    """Tables of a quadtree. Not cached yet: the mesher's rules are the first thing a user changes."""
    from wadi2d.tables.quad import build_quad_tables

    grid = mesh_grid(cfg, bed, window, crs, left_out)
    ground = Ground(bed, grid.x0, grid.y0)
    edits = apply_objects(grid, cfg.terrain.objects, bed.pixel, cfg.terrain, ground)
    n = manning_grid(cfg, grid, crs)
    return build_quad_tables(grid, bed, cfg.tables, n, edits.crest, edits.edit, edits.lining)


def check_terrain(cfg: RunConfig) -> list[str]:
    """What the shaped objects look like against the ground, in plain words; no table is built."""
    if not any(o.kind in SHAPED_KINDS for o in cfg.terrain.objects):
        return []
    with RasterBed(cfg.terrain.dem, cfg.terrain.pixel_stride) as bed:
        window = grid_window(cfg, bed)
        bed.bind(window.x0, window.y0)
        dx = cfg.grid.dx
        bounds = (window.x0, window.y0 - window.ny * dx, window.x0 + window.nx * dx, window.y0)
        ground = Ground(bed, window.x0, window.y0)
        return terrain_notes(cfg.terrain.objects, ground, dx, bed.pixel, cfg.terrain, bounds)


def survey_terrain(
    cfg: RunConfig, grid: TileGrid, folder: Path, maps: bool, whole: bool, cache_dir: Path | None = None
) -> TerrainReport:
    """Cut and fill of every object, and the modified terrain if ``maps``; ``whole`` writes every tile of it. The
    ground is read through the DEM's chunk store under ``cache_dir`` when there is one, as the tables read it (W91:
    the same pixels, minutes faster on a 0.5 m terrain)."""
    with open_bed(cfg, cache_dir) as bed:
        bed.bind(grid.x0, grid.y0)
        ground = Ground(bed, grid.x0, grid.y0)
        edits = apply_objects(grid, cfg.terrain.objects, bed.pixel, cfg.terrain, ground)
        view = lattice_view(grid) if getattr(grid, "quad", False) else grid
        return survey(cfg.terrain, view, bed, edits, folder, bed.crs, whole, maps)


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
    gages = stem.with_suffix(".gage") if hms_basin.diversions else None  # a Specified Flow diversion reads one (W72)
    return load_project_tables(
        load_pdata(stem.with_suffix(".pdata")), stem.with_suffix(".dss"), gages if gages and gages.is_file() else None
    )


def _lumped_rain(cfg: RunConfig, storm, basin, hms_basin, crs: str):
    """What falls on the lumped network: the storm, or a grid averaged over each subbasin; a subbasin with a storm area
    of its own reads the area reduction there. With ``storm.area_reduction`` the network takes the lumped part's
    reduction, and a lumped curve in a run with a 2D part reads each subbasin at its own storm area, else at its own
    area (W95)."""
    if cfg.storm.area_reduction is not None:
        storm = with_reduction(storm, part_reduction(cfg.storm, PART_LUMPED))
    rain = _network_rain(cfg, storm, basin, hms_basin, crs)
    own = {s.name: s.storm_area_km2 for s in cfg.hydrology.subbasins if s.storm_area_km2 is not None}
    if lumped_curve(cfg.storm) and not cfg.run.lumped_only:  # a lumped-only run reads every element by itself
        own = {name: own.get(name, subbasin.area_km2) for name, subbasin in basin.subbasins.items()} | own
    if not own:
        return rain
    from wadi2d.storm.own_area import OwnAreas

    missing = sorted(set(own) - set(basin.subbasins))
    if missing:
        raise InvalidJob(f"subbasins {', '.join(missing)} have a storm area of their own but are not in the basin")
    return OwnAreas(rain, own)


def _network_rain(cfg: RunConfig, storm, basin, hms_basin, crs: str):
    """The storm, or a grid averaged over each subbasin, as the job's storm area gives it."""
    h = cfg.hydrology
    spatial = hms_basin.spatial if hms_basin is not None else None
    system = spatial.coordinate_system if spatial is not None else None
    if isinstance(storm, GriddedStorm):
        return storm.bind(load_polygons(h, crs), system or crs)
    if isinstance(storm, GaugeStorm):
        return storm.bind(load_polygons(h, crs), system or crs, crs)
    if cfg.storm.depth_grid is None:
        return storm
    if cfg.storm.kind == DEPTH_GRID_STORM:  # a source of its own: any polygons the job has, an HMS basin's or not (W95)
        from wadi2d.storm.by_subbasin import StormBySubbasin
        from wadi2d.storm.grid_depth import DepthGrid, subbasin_means

        polygons = load_polygons(h, crs)
        missing = sorted(set(basin.subbasins) - set(polygons))
        if missing:
            raise InvalidJob(f"a depth grid on the lumped network needs a polygon for every subbasin; none for {missing}")
        grid = DepthGrid.load(cfg.storm.depth_grid, system or crs or None)
        return StormBySubbasin(storm, subbasin_means(grid, polygons, basin.subbasins)).at_area(storm.storm_area_km2)
    from wadi2d.hydrology.from_hms import grid_storm
    from wadi2d.storm.grid_depth import DepthGrid

    if h.hms_sqlite is None:
        why = "; a generated basin cannot take one yet" if h.basin_json is not None else ""
        raise InvalidJob(f"a depth grid on a lumped network needs hydrology.hms_sqlite for the polygons{why}")
    try:
        rain = grid_storm(
            storm, DepthGrid.load(cfg.storm.depth_grid, system or crs or None), basin, h.hms_sqlite, True
        )
    except KeyError as error:
        raise InvalidJob(f"no polygon for subbasin {error} in hydrology.hms_sqlite") from error
    return rain("", cfg.storm.storm_area_km2)


def _above(basin, element: str, cut) -> set[str]:
    """What sends an element water; a cut link sends none, because the grid carries that water instead."""
    if not cut:
        return basin.upstream_of(element)
    links = {name: [p for p in parents if (p, name) not in cut] for name, parents in basin.upstream.items()}
    return basin._walk(links, element)


def _carried(h, basin, wanted, routes=None) -> dict[str, str]:
    """The subbasins of the basin whose water an entry brings in from above it, each with that entry's name; a
    subbasin that enters at its own outlet under its own name is not carried."""
    lumped = {s.name: s for s in h.subbasins if s.mode == "lumped"}
    known = set(basin.subbasins) if basin is not None else set()
    carried: dict[str, str] = {}
    cut = routes.cut if routes is not None else ()
    ends = [(f"the route to {name}", None, name) for name, _second in routes.ends] if routes else []
    for name, _point, element in [*wanted, *ends]:
        if basin is None or element not in basin.elements:
            raise InvalidJob(f"inflow {name}: element {element} is not in the basin")
        if element in lumped and lumped[element].outlet is not None and name == element:
            continue
        for sub in _above(basin, element, cut) & known:
            carried[sub] = name
    return carried


def _check_routes(h, basin, wanted, routes=None) -> None:
    """Every lumped subbasin's water enters once: dropped water and doubled water both end in exit 0."""
    lumped = {s.name: s for s in h.subbasins if s.mode == "lumped"}
    carried = _carried(h, basin, wanted, routes)
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


def _live_reentries(routes, wanted) -> dict[str, str]:
    """The inflows a hand-back's route ends at, by name; two on one element would send the same water twice."""
    live = {name: element for name, _point, element in wanted if element in routes.live}
    twice = {element for element in live.values() if list(live.values()).count(element) > 1}
    if twice:
        raise InvalidJob(f"two inflows take the outflow of {sorted(twice)}: the same water would enter twice")
    return live


def hydrographs(
    cfg: RunConfig, storm, crs: str = ""
) -> list[tuple[str, tuple[float, float], np.ndarray, np.ndarray]]:
    """Every (name, point, times, flows) that enters the 2D domain; the lumped engine runs here if needed."""
    return _network(cfg, storm, crs)[0]


def _lumped_basin(cfg: RunConfig, crs: str):
    """The engine's basin from the job's network file, the HMS model when there is one, and the cuts the routes decided."""
    h = cfg.hydrology
    if h.basin_json is not None:
        from wadi2d.basin.job import engine_basin, generated_basin

        gen = generated_basin(cfg, crs)
        basin = engine_basin(gen.model, gen.modes, h.reach_routing)
        with_dam_starts(basin, cfg.dam_levels)
        return basin, None, gen.cut
    from wadi2d.hms import load_basin
    from wadi2d.hydrology.from_hms import basin_from_hms

    hms_basin = load_basin(h.hms_basin)
    basin = basin_from_hms(
        hms_basin, _project_tables(h, hms_basin), h.reach_routing, run_calendar(cfg), {m.reach: m for m in h.muskingum}
    )
    with_dam_starts(basin, cfg.dam_levels)
    return basin, hms_basin, ()


def run_calendar(cfg: RunConfig) -> datetime | None:
    """The date and time of the run's minute zero, ``storm.rain_start``; None when the job gives none.

    The lumped network's first step is the run's minute zero, so a reservoir with monthly evaporation reads its
    months from here; without a date it refuses to route.
    """
    start = cfg.storm.rain_start
    return None if start is None else datetime.fromisoformat(start)


def _taken_starts(cfg: RunConfig, lumped) -> dict[str, float]:
    """The dams of ``dam_levels`` a reservoir of the run's lumped network took, with the level it starts at."""
    if lumped is None or not cfg.dam_levels:
        return {}
    named = {item.name for item in cfg.dam_levels}
    return {
        name: float(element.routing.initial_elevation_m)
        for name, element in lumped.basin.elements.items()
        if name in named and isinstance(element, Reservoir)
    }


def _network(cfg: RunConfig, storm, crs: str = ""):
    """``hydrographs``, the live network of a job with hand-backs (None otherwise), and the base run's series."""
    h = cfg.hydrology
    table = [
        (i.name, (i.x, i.y), np.asarray(i.times_s, np.float64), np.asarray(i.flows, np.float64))
        for i in h.inflows
        if i.element is None
    ]
    wanted = _entering(h)
    generated = h.basin_json is not None
    if not wanted and not h.handbacks and not generated:
        _check_routes(h, None, [])
        return table, None, None
    if h.hms_basin is None and not generated:
        raise InvalidJob(f"a {'hand-back' if h.handbacks else 'lumped inflow'} needs hydrology.hms_basin")
    if storm is None and not h.handbacks:
        raise InvalidJob("a lumped inflow needs a storm")
    from wadi2d.engine.network_series import NetworkSeries
    from wadi2d.hydrology.live_network import LiveNetwork, NoRain, plan_routes
    from wadi2d.hydrology.model import TimeGrid
    from wadi2d.hydrology.network import LumpedEngine

    basin, hms_basin, decided = _lumped_basin(cfg, crs)
    routes = None
    if h.handbacks or generated:
        leaving = [element for _name, _point, element in wanted]
        entries = [line.element for line in h.handbacks]
        routes = plan_routes(basin, entries, leaving, decided, cut_entries=not generated)
    _check_routes(h, basin, wanted, routes)
    steps = int(np.ceil(cfg.run.duration_s / SECONDS_PER_MINUTE / h.time_step_min))
    grid = TimeGrid(h.time_step_min, steps)
    rain = NoRain() if storm is None else _lumped_rain(cfg, storm, basin, hms_basin, crs)
    run = LumpedEngine(basin).run(rain, grid, cut=routes.cut if routes is not None else ())
    times = grid.minutes * SECONDS_PER_MINUTE
    leaving = {i.name for i in h.inflows if not i.enters}  # water that leaves the model there, as at an HMS sink (W88)
    for name, point, element in wanted:
        if name not in leaving:
            table.append((name, point, times, run.outflow[element]))
    keep = None if generated else _ran(basin, wanted, routes)
    if routes is None or not routes.live:
        return table, None, NetworkSeries(basin, run, keep=keep)
    live = LiveNetwork(basin, routes, run, _live_reentries(routes, wanted))
    return table, live, NetworkSeries(basin, run, routes.live, keep=keep)


def _ran(basin, wanted, routes) -> set[str]:
    """The elements of an HMS network whose water this run put on the grid: each entering element and what feeds it.

    The rest of the network is computed whole, as HMS would route it, and never reaches the grid: a subbasin switched
    to rain-on-grid, and the junctions and reaches below the lumped subbasins, whose water the grid routes instead. Their
    series would look like design flows and are not (W39: Z4C read 9,130 m3/s that the run never carried), so none
    is written.
    """
    cut = routes.cut if routes is not None else ()
    found: set[str] = set()
    for _name, _point, element in wanted:
        found |= _above(basin, element, cut) | {element}
    return found


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
    terrain: Terrain | None = None
    """The terrain as the run took it: the job's, with the pit fills when ``terrain.fill_pits`` made any (W85)."""
    cells: int = 0
    products: str = PRODUCTS_NONE
    done: dict = field(default_factory=dict)


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
    """What every output of an area-reduced run says about its rain; with ``storm.area_reduction``, each part's."""
    if cfg.storm.area_reduction is not None:
        tags = {}
        for part in (PART_LUMPED, PART_GRID):
            record = part_record(cfg.storm, part)
            if record is not None:
                tags[f"arf_{part}"] = part_words(record).split(": ", 1)[1]
        return tags
    if cfg.storm.arf_factor is not None:
        return {"arf_table_type": GIVEN_FACTOR, "arf_factor": f"{cfg.storm.arf_factor:g}"}
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


def domain_cells(tables: GridTables) -> np.ndarray:
    """The lattice cells inside the domain's outline: the active ones and the squares an aligned strip replaced, which
    are inactive on the lattice but still the domain (W80: their joins counted as edges, 338 false pools on Block 2)."""
    grid = tables.grid
    strip = getattr(tables, "strip", None)
    if strip is None or not strip.strip.masked[0].size:
        return grid.mask
    inside = grid.mask.copy()
    inside[strip.strip.masked[0], strip.strip.masked[1]] = True
    return inside


def edge_ponding(
    grid: TileGrid, depth: np.ndarray, open_cells: np.ndarray, domain: np.ndarray | None = None
) -> tuple[float, float, float]:
    """Deepest water on the domain edge away from any boundary: (depth, x, y).

    An edge is a wall. Water deep against one is a domain drawn too tight or a gap between polygons, and the
    balance closes all the same, so nothing else would tell. ``domain`` as in :func:`domain_cells`.
    """
    edge = grid.mask & ~ndimage.binary_erosion(grid.mask if domain is None else domain, border_value=0)
    closed = edge & ~ndimage.binary_dilation(open_cells, iterations=EDGE_REACH)
    if not closed.any():
        return 0.0, 0.0, 0.0
    j, i = (int(a) for a in np.unravel_index(np.argmax(np.where(closed, depth, -1.0)), depth.shape))
    x, y = grid.xy_of(j, i)
    return float(depth[j, i]), float(x), float(y)


def _edge_streams(cfg: RunConfig, crs: str, out: Path, progress, left: LeftOut | None = None) -> list[str]:
    """Streams across closed edges before the run (W78): the warnings, the points in ``edge_checks.gpkg``. A check
    that fails costs a warning, never the run. The outline along a catchment left out of the mesh is no edge of
    the model: a stream across it there is not named (W88)."""
    if not cfg.outputs.edge_check.enabled:
        return []
    try:
        cache = Path(cfg.grid.cache_dir) if cfg.grid.cache_dir else out / "cache"
        found = stream_crossings(cfg, crs, cache, left.area if left is not None and left.names else None)
        path = write_crossings(out, found, crs)
    except Exception as error:  # the ground, the DEM or WhiteboxTools: the run goes on without the check
        return [f"the check for streams across the domain edge could not run: {error}"]
    if path is not None:
        progress.emit("output", kind="edge_checks", path=str(path), streams=len(found))
    return crossing_notes(found, cfg.outputs.edge_check)


class _EdgeCheckBeside:
    """``_edge_streams`` on a thread of its own while the tables are built (W91): on a domain outline the cache has
    not seen it reads the whole DEM under the outline at the coarse pixel and runs D8, 225 s on Block 2's run 3,
    and needs nothing the tables make. Its events are held and written in their own order by ``report``, so the
    run's progress file carries the same lines; ``report`` without ``start`` runs the check where it stands."""

    def __init__(self, cfg: RunConfig, crs: str, out: Path, left: LeftOut | None) -> None:
        self.args = (cfg, crs, out)
        self.left = left
        self.events: list[tuple[str, dict]] = []
        self.pool = None
        self.future = None

    def emit(self, ev: str, **fields) -> None:
        self.events.append((ev, fields))

    def start(self) -> None:
        from concurrent.futures import ThreadPoolExecutor

        self.pool = ThreadPoolExecutor(1, thread_name_prefix="edge-check")
        self.future = self.pool.submit(_edge_streams, *self.args, self, self.left)

    def report(self, progress) -> None:
        if self.future is None:
            notes = _edge_streams(*self.args, self, self.left)
        else:
            try:
                notes = self.future.result()
            finally:
                self.pool.shutdown()
        for ev, fields in self.events:
            progress.emit(ev, **fields)
        for note in notes:
            progress.emit("warn", message=note)


def _edge_pools(cfg, tables, depth, open_cells, out: Path, crs, progress) -> list[str] | None:
    """Deep water against closed edges after the run (W78), or None when the check is off or fails: the single
    deepest-cell warning then stands, as before."""
    check = cfg.outputs.edge_check
    if not check.enabled or getattr(tables.grid, "quad", False):
        return None
    try:
        pools = edge_pools(
            tables.grid, depth, tables.zmin, open_cells, EDGE_REACH, cfg.outputs.edge_depth, check, domain_cells(tables)
        )
        path = write_pools(out, pools, crs)
    except Exception:  # the old warning stands in for it
        return None
    if path is not None:
        progress.emit("output", kind="edge_checks", path=str(path), pools=len(pools))
    return pool_notes(pools, check)


def _write_outputs(cfg, tables, monitor: Monitor, results: Results, out: Path, crs, progress, tags) -> None:
    from wadi2d.products.cell_maps import lattice_maps, paint_strip, strip_on_lattice, write_cell_maps

    fields_ = monitor.maxima.fields()
    grid = tables.grid
    maps = lattice_maps(fields_, tables.zmin)
    more = [make() for make in monitor.extra_maxima]
    strip_maxima = {name: a for held in more for name, a in held.items()}
    where, also = strip_on_lattice(tables), None
    if where is not None and where[0].size and "strip_depth" in strip_maxima:
        # the squares a strip replaced read the strip cell at their centre: the wadis are not blank (W86)
        also = paint_strip(maps, strip_maxima, where, tables.strip.mesh.zmin)
    write_cell_maps(out / "maps", maps, grid, crs, tags, also)
    for make in monitor.extra_products:
        kind, path = make(out / "maps", crs)
        progress.emit("output", kind=kind, path=str(path))
    results.maxima(fields_)
    for held in more:
        results.maxima(held)
    open_cells = monitor.boundary.mask
    left = getattr(tables, "left_out", None)
    if left is not None and left.entries:  # water running in beside a left-out catchment is no pool (W88)
        open_cells = open_cells | left.entry_cells(grid)
    pooled = _edge_pools(cfg, tables, fields_["depth"], open_cells, out, crs, progress)
    deep, x, y = edge_ponding(grid, fields_["depth"], open_cells, domain_cells(tables))
    if pooled is not None:
        for note in pooled:
            progress.emit("warn", message=note)
    elif deep > cfg.outputs.edge_depth:
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
    if monitor.limiter is not None:
        for note in monitor.limiter.notes():
            progress.emit("warn", message=note)
        path = monitor.limiter.write(out, crs) if cfg.outputs.step_limiter == "layer" else None
        if path is not None:
            progress.emit("output", kind="step_limiter", path=str(path), cells=len(monitor.limiter.cells))
    progress.emit("output", kind="maps", path=str(out / "maps"))


def _preflight(cfg: RunConfig, crs: str):
    storm = build_storm(cfg)
    polygons = load_polygons(cfg.hydrology, crs)
    return (storm, polygons, *_network(cfg, storm, crs))


def _resolved(cfg: RunConfig, crs: str):
    """A job on a generated basin as the engine runs it, and the basin; an HMS job with its lumped water kept on the
    network down to the grid when it asks for that (W88); any other job as it is."""
    if cfg.hydrology.basin_json is None:
        if cfg.hydrology.lumped_entry == LUMPED_AT_OUTLETS or cfg.hydrology.hms_basin is None:
            return cfg, None
        from wadi2d.engine.network_entries import hms_icons, route_on_network

        basin, hms_basin, _cut = _lumped_basin(cfg, crs)
        try:
            return route_on_network(cfg, basin, hms_icons(hms_basin)), None
        except ValueError as error:
            raise InvalidJob(str(error)) from error
    from wadi2d.basin.job import resolve

    return resolve(cfg, crs)


def preflight(cfg: RunConfig, crs: str):
    """Everything that can refuse a job without a grid; it comes before the tables, which can take minutes."""
    return _preflight(_resolved(cfg, crs)[0], crs)[:3]


@dataclass(frozen=True)
class LumpedView:
    """A job's lumped network as its runs see it, for the depth-area study (:mod:`wadi2d.arf_network`)."""

    cfg: RunConfig
    """The job resolved: on a generated basin every subbasin with its mode."""
    basin: object
    """The lumped engine's basin; on a generated basin its 2D subbasins are left out."""
    hms_basin: object | None
    live: frozenset[str]
    """Elements a hand-back carries 2D water into, and everything below them on its route."""
    cut: frozenset[tuple[str, str]]
    """Links that carry no water, because the grid carries it instead."""
    generated: object | None


def lumped_view(cfg: RunConfig, crs: str) -> LumpedView | None:
    """The network the runs of ``cfg`` route, or None when it has none; it refuses what a run would refuse."""
    resolved, generated = _resolved(cfg, crs)
    _storm, _polygons, _table, network, series = _preflight(resolved, crs)
    if series is None:
        return None
    basin, hms_basin, decided = _lumped_basin(resolved, crs)
    cut = network.routes.cut if network is not None else frozenset(decided)
    return LumpedView(resolved, basin, hms_basin, frozenset(series.live), frozenset(cut), generated)


def lumped_rain_at(view: LumpedView, area_km2: float, crs: str):
    """The rain of the lumped network with the storm read at ``area_km2``, as a run at that storm area takes it."""
    cfg = view.cfg.model_copy(update={"storm": at_study_area(view.cfg.storm, area_km2)})
    return _lumped_rain(cfg, build_storm(cfg), view.basin, view.hms_basin, crs)


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


def _placed_entries(cfg, tables, polygons, flows, crs, out: Path, progress):
    """The hydrographs with every 'wadi' entry placed on the grid (W41), and every entry that lies in a catchment
    left out of the mesh moved to the wadi just outside it first (W88); entries.json says where and why."""
    try:
        snapped = snap_entries(cfg, tables, flows, getattr(tables, "left_out", None))
    except ValueError as error:
        raise InvalidJob(str(error)) from error
    for s in snapped:
        progress.emit("warn", message=f"inflow {s.name} at ({s.asked[0]:.0f}, {s.asked[1]:.0f}) {s.note}")
    moved = {s.name: s.point for s in snapped}
    flows = [(name, moved.get(name, point), times, q) for name, point, times, q in flows]
    placed = place_entries(cfg, tables, polygons, crs, moved, {name for name, *_rest in flows})
    placed = with_snapped(placed, snapped)
    if not placed:
        return flows
    records = [p.record() for p in placed]
    (out / ENTRIES_FILE).write_text(json.dumps(records, indent=2), encoding="utf-8")
    progress.emit("entries", placed=records)
    for p in placed:
        if not p.clear:
            progress.emit("warn", message=f"lumped {p.kind} {p.name} {p.note}")
    return with_entries(flows, placed)


def _lumped(cfg: RunConfig, out: Path, crs: str, progress, summary: RunSummary, left=None, why: str = "") -> None:
    """A lumped-only run into ``out`` (:mod:`wadi2d.engine.lumped_run`); None: there are no tables for a step after it."""
    from wadi2d.engine.lumped_run import run_lumped

    (out / "config.resolved.json").write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
    try:
        run_lumped(cfg, out, crs, progress, summary, left, why)
    except ValueError as error:
        raise InvalidJob(str(error)) from error


def _say_left_out(left: LeftOut, progress) -> None:
    """What the mesh leaves out, on the record of the run (W88)."""
    if not left.names:
        progress.emit(
            "warn",
            message="grid.exclude_lumped: the lumped network carries no subbasin to an entry elsewhere, so no cell "
            "is left out of the mesh",
        )
        return
    progress.emit(
        "left_out", subbasins=list(left.names), cells=left.cells_out, area_km2=round(left.area_km2, 4),
        owners=dict(left.owner),
    )  # fmt: skip
    progress.emit(
        "warn",
        message=f"the 2D mesh leaves out {len(left.names)} lumped subbasins, {left.area_km2:.2f} km2 and "
        f"{left.cells_out} cells of the domain: the lumped network carries their water, and their edge is a closed wall",
    )


def _run(cfg, out: Path, backend, tables, resume, progress, summary: RunSummary, stop_files):
    """The simulation. Returns (tables, CRS WKT) for the step after it; the model is gone by then, GPU memory too."""
    check_inputs(cfg)
    cfg = with_tables(cfg)
    if tables is not None:
        tables, crs = tables
    elif cfg.terrain.dem is not None:
        with rasterio.open(cfg.terrain.dem) as dem:
            crs = dem.crs.to_wkt() if dem.crs is not None else ""
    else:
        crs = ""
    cfg, generated = _resolved(cfg, crs)
    if cfg.run.lumped_only:
        return _lumped(cfg, out, crs, progress, summary)
    if grid_curve(cfg.storm):
        raise InvalidJob(
            "storm.area_reduction.grid reads its curve at each storm area of a depth-area study, and the 2D cells of "
            "a single run have no area of their own: give the 2D part a fixed area or a coefficient, or run the study"
        )
    design = design_plans(cfg, generated)
    checkpoint = out / "checkpoint.h5"
    continuing = _check_resume(cfg, checkpoint, resume, progress)
    if continuing and cfg.breaches:
        raise InvalidJob("a run with a breach cannot be resumed in this version: start it again")
    (out / "config.resolved.json").write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
    t0 = time.monotonic()
    storm, polygons, flows, network, lumped = _preflight(cfg, crs)
    if generated is not None:
        for note in generated.notes:
            progress.emit("warn", message=note)
        progress.emit("basin", path=str(generated.path), **generated.report())
    if lumped is not None:  # a Muskingum reach outside its stable range routes as given, as in HMS, and says so (W89)
        from wadi2d.hydrology.muskingum import reach_notes

        for note in reach_notes(lumped.basin, cfg.hydrology.time_step_min):
            progress.emit("warn", message=note)
    still = storm is None and not flows and not cfg.initial_levels and not cfg.dam_levels and not flow_lines(cfg.boundaries)
    if still and not any(b.kind == "stage" for b in cfg.boundaries):
        progress.emit("warn", message="no rain, no inflow and no stage boundary: nothing will happen")
    if cfg.storm.depth_grid is not None:
        progress.emit(
            "warn",
            message="depth grid: 2D cells take the raster's own depth, lumped subbasins their polygon mean; "
            "HMS with Uniform Depth: Yes uses the mean above each analysis point instead",
        )
    if cfg.storm.arf_factor is not None:  # a given factor, on the record of the run whatever the storm (W83)
        progress.emit(
            "output", kind="area_reduction", factor=cfg.storm.arf_factor, storm_area_km2=None,
            arf_table_type=GIVEN_FACTOR,
        )  # fmt: skip
        progress.emit(
            "warn",
            message=f"rain: every depth is multiplied by {cfg.storm.arf_factor:.4f}, the given area-reduction factor, "
            "over the whole event",
        )
    for part in (PART_LUMPED, PART_GRID):  # each part's reduction, on the record of the run (W95)
        record = part_record(cfg.storm, part)
        if record is not None:
            progress.emit("output", kind="area_reduction", **record)
            progress.emit("warn", message=part_words(record))
    own = {s.name: s.storm_area_km2 for s in cfg.hydrology.subbasins if s.storm_area_km2 is not None}
    if own and cfg.storm.arf is not None:  # the subbasins that read the table at an area of their own (W79)
        progress.emit("output", kind="subbasin_storm_areas", areas_km2=own, arf_table_type=cfg.storm.arf.table_type)
        said = ", ".join(f"{name} {area:g}" for name, area in own.items())
        progress.emit(
            "warn",
            message=f"rain: {len(own)} lumped subbasins read the area-reduction table at their own storm area, km2: "
            f"{said}; the rest of the model at the storm's own area",
        )
    if isinstance(storm, GriddedStorm):
        for note in storm.notes(cfg.run.duration_s / SECONDS_PER_MINUTE):
            progress.emit("warn", message=f"rain: {note}")
        if storm.arf is not None and cfg.storm.arf_factor is None:  # which factor the rain was multiplied by, on the record of the run
            progress.emit(
                "output", kind="area_reduction", factor=storm.area_factor, storm_area_km2=storm.storm_area_km2,
                arf_table_type=cfg.storm.arf.table_type,
            )  # fmt: skip
            if storm.storm_area_km2 is None:
                said = "an area-reduction table without a storm area leaves the rain whole"
            else:
                said = (
                    f"every frame is multiplied by {storm.area_factor:.4f}, the area-reduction table at "
                    f"{storm.storm_area_km2:g} km2, over the whole event"
                )
            progress.emit("warn", message=f"rain: {said}")
    for note in spillway_notes(cfg) + check_terrain(cfg):
        progress.emit("warn", message=note)
    left = getattr(tables, "left_out", None) if tables is not None else left_out_of(cfg, crs)
    edges = _EdgeCheckBeside(cfg, crs, out, left)  # beside the tables when they are built here (W91)
    if tables is not None:
        edges.report(progress)
    if cfg.mesh.enabled and cfg.mesh.lines:
        from wadi2d.mesh.build import rounding_notes

        for note in rounding_notes(cfg):
            progress.emit("warn", message=note)
    rebuild = None
    if tables is None:
        cache = Path(cfg.grid.cache_dir) if cfg.grid.cache_dir else out / "cache"
        edges.start()
        try:
            try:
                tables, crs = prepare_grid(cfg, cache, progress, left)
            finally:
                edges.report(progress)
        except NothingOnTheGrid as error:  # every cell is left out: the job is the lumped network alone (W88)
            cfg = cfg.model_copy(update={"run": cfg.run.model_copy(update={"lumped_only": True})})
            why = f"{error}: the run is the lumped network alone, the HMS way"
            return _lumped(cfg, out, crs, progress, summary, left, why)

        def rebuild(job: RunConfig, before: GridTables) -> GridTables:
            return prepare_grid(job, cache, progress, left, base=before)[0]

    if cfg.hydrology.arf_by_element:
        raise InvalidJob(
            "hydrology.arf_by_element is for a lumped-only run: with a 2D part one rain falls on the grid, and the "
            "elements that feed it cannot each read their own area; give lumped subbasins storm_area_km2 instead"
        )

    plain = cfg
    cfg, tables, _pits = resolve_pits(cfg, tables, crs, out, progress, rebuild)
    if cfg is not plain:  # the pit fills are terrain objects of the job as it runs: the saved job and the maps take them
        (out / "config.resolved.json").write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
    summary.terrain = cfg.terrain
    summary.tables_s = time.monotonic() - t0
    grid = tables.grid
    summary.cells = grid.cell_count if getattr(grid, "quad", False) else int(grid.mask.sum())
    if left is not None:
        _say_left_out(left, progress)
    try:
        write_cell_grid(grid, crs, out)
    except Exception as error:  # a drawing of the grid must not cost a run
        progress.emit("warn", message=f"The cell grid layer could not be written: {error}")
    if any(o.kind in PIXEL_KINDS for o in cfg.terrain.objects):
        wanted = cfg.outputs.terrain_map
        report = survey_terrain(cfg, grid, out / TERRAIN_DIR, wanted, wanted, cache_folder(cfg, out))
        progress.emit("terrain", volumes=report.volumes, files=report.files)
    flows = _placed_entries(cfg, tables, polygons, flows, crs, out, progress)
    subs = cfg.hydrology.subbasins
    lumped_names = [s.name for s in subs if s.mode == "lumped"]
    two_d_names = [s.name for s in subs if s.mode == "2d"]
    for note in check_rain_once(grid, polygons, lumped_names, two_d_names, cfg.hydrology.overlap_share):
        progress.emit("warn", message=note)
    name = backend or cfg.run.backend
    strip = getattr(tables, "strip", None)
    try:
        model = Model(tables, cfg.numerics, name)
    except (RuntimeError, ImportError, OSError) as error:
        raise BackendUnavailable(str(error)) from error
    summary.backend = model.backend.name
    lines = [*open_lines(cfg.boundaries), *sink_lines(cfg.hydrology.handbacks)]
    bset = boundary_set(lines, tables, cfg.grid.line_samples)
    for note in boundary_notes(lines, bset, grid.dx, line_labels(cfg)):
        progress.emit("warn", message=note)
    taken = _taken_starts(cfg, lumped)
    try:
        pools, notes = grid_pool_depth(cfg, tables, bset.mask, taken)
    except ValueError as error:
        raise InvalidJob(str(error)) from error
    for note in notes:
        progress.emit("warn", message=note)
    hybrid = None
    wet_in_strip = None
    if strip is not None:
        from wadi2d.strips.hybrid import make_hybrid

        hybrid = make_hybrid(model, strip.mesh, cfg.strips.substeps)
        strip_start, wet_in_strip = hybrid.strip_initial_depth(cfg.initial_levels)
        progress.emit(
            "strips", corridors=len(strip.strip.polygons), cells=int((strip.strip.corridor >= 0).sum()),
            triangles=int((strip.strip.corridor < 0).sum()), replaced=int(strip.strip.masked[0].size), cut=strip.strip.notes,
            rules=strip.strip.rules,
        )  # fmt: skip
    model.set_depth(np.maximum(initial_depth(cfg.initial_levels, tables, wet_in_strip), pools))
    if bset.size:
        model.set_boundary(bset.cells)
    if hybrid is not None:
        hybrid.set_strip_depth(strip_start)
    forcing = Forcing(cfg, tables, model, bset, storm, polygons, flows, crs, None if hybrid is None else hybrid.forcing_cells())
    if hybrid is not None:
        forcing.strip_depth = hybrid.strip_depth_real
    carried: list = []  # flow lines whose water brings its momentum (W70)
    if flow_lines(cfg.boundaries):
        try:
            injected, notes = line_injections(cfg, tables, forcing, crs)
            moving, more = momentum_lines(cfg, model.kicks_faces())
        except (ValueError, FileNotFoundError) as error:
            raise InvalidJob(f"flow line: {error}") from error
        forcing.injections += injected
        if moving:
            carried = [inj for inj in injected if inj.east is not None]
        for note in notes + more:
            progress.emit("warn", message=note)
    if isinstance(storm, GaugeStorm):
        report_gauges(storm, forcing, cfg, progress, out)
    if forcing.injections and not getattr(grid, "quad", False):
        entering = {
            inj.name: set(zip(forcing.jj[inj.cells].tolist(), forcing.ii[inj.cells].tolist(), strict=True))
            for inj in forcing.injections
        }
        for note in inflow_crossings(cfg.outputs.lines, entering, grid):
            progress.emit("warn", message=note)

    results = Results(out / "results.h5", grid, crs, cfg.model_dump_json(), append=continuing)
    if results.salvaged:
        progress.emit(
            "warn", message="results.h5 was left unreadable by a kill: snapshots before it are lost"
        )
    monitor = Monitor(cfg, tables, model, bset, results, progress, out, crs, stop_files)
    if hybrid is not None:
        hybrid.attach(monitor, strip, cfg.outputs.lines)
    monitor.balance.storage0 = monitor.storage()
    link = HandBackLink(cfg, tables, model, bset, forcing, network, monitor) if network is not None else None
    if lumped is not None:
        monitor.parts.append(lumped)
    bed = BedLoss(cfg, tables, model, forcing, crs, monitor) if cfg.transmission.enabled else None
    for part in (link, bed):
        for note in part.notes() if part is not None else ():
            progress.emit("warn", message=note)
    try:
        breaches = build_breaches(cfg, tables, model, forcing, crs, progress)
    except ValueError as error:
        raise InvalidJob(str(error)) from error
    on_step = monitor.on_step
    if breaches is not None:

        def on_step(stepper, _m=monitor.on_step, _b=breaches.on_step):
            _m(stepper)
            _b(stepper)

    if continuing:
        load_checkpoint(checkpoint, model, monitor)
    if breaches is not None:
        breaches.on_step(model.stepper)  # the triggers read the water the run starts with
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
            if link is not None:
                link.exchange(t)
                t_next = link.window_end(t, t_next)
            if breaches is not None:
                t_next = breaches.window_end(t, t_next)
            rate, rain, inflow = forcing.rate(t, t_next)
            if breaches is not None:
                rate = breaches.add_rates(rate)
            loss = bed.apply(rate, t, t_next) if bed is not None else 0.0
            if rain + inflow + loss > 0.0 or not dry or (breaches is not None and breaches.piping):
                model.set_source_cells(forcing.state, rate[: forcing.n_lattice])
                if hybrid is not None:
                    hybrid.set_strip_source(rate[forcing.n_lattice :])
            if carried:
                model.set_momentum(momentum_kick(carried, grid.dx, cfg.numerics.u_max))
            dry = rain + inflow + loss <= 0.0
            back = link.reentry_volume() if link is not None else 0.0
            monitor.open_window(t, t_next, rain, inflow, back, loss)
            model.advance(t_next, on_step)
            monitor.settle(t_next)
            t = t_next
            if monitor.checkpoint_due:
                monitor.checkpoint_due = False
                save_checkpoint(checkpoint, model, monitor, key)
            if monitor.stop_due and t < end - 1e-9:
                raise StopRequested  # at a window's end, so a resume carries on the unbroken run's windows
        summary.exit_code, summary.status = EXIT_DONE, "finished"
        if breaches is not None:
            breaches.write(out)
    except StopRequested:
        monitor.settle(model.stepper.t)
        if breaches is not None:
            breaches.write(out)
        save_checkpoint(checkpoint, model, monitor, key)
        summary.exit_code, summary.status = EXIT_STOPPED, "stopped"
    except NumericalFailure as error:
        summary.loop_s = time.monotonic() - t1
        where = _failed_cell(model)
        summary.exit_code, summary.status = EXIT_NUMERICAL, "numerical failure"
        summary.message = f"{error} at cell {where}"
        progress.emit("error", code=EXIT_NUMERICAL, message=str(error), cell=where)
        _finish(cfg, tables, model, monitor, results, out, crs, progress, summary, t1, design)
        return tables, crs
    _finish(cfg, tables, model, monitor, results, out, crs, progress, summary, t1, design)
    return tables, crs


def _network_layers(cfg: RunConfig, tables, monitor, out: Path, crs: str, progress) -> None:
    """The lumped network of a run with a 2D part as map layers (W88): the catchments that ran the HMS way, with
    their peaks and whether the mesh left them out. A failure costs a warning, never the run."""
    from wadi2d.engine.network_layers import element_rows, write_network
    from wadi2d.engine.network_series import NetworkSeries, element_columns

    found = [part for part in monitor.parts if isinstance(part, NetworkSeries)]
    if not found:
        return
    part = found[0]
    left = getattr(tables, "left_out", None)
    own = {s.name: "its own outlet" for s in cfg.hydrology.subbasins if s.mode == "lumped" and s.outlet is not None}
    try:
        enters = {**own, **carried_subbasins(cfg, crs)}
        t = part.run.grid.minutes * SECONDS_PER_MINUTE
        series = {name: element_columns(part.basin, part.run, name) for name in part.written()}
        rows = element_rows(part.basin, series, t)
        path = write_network(out, cfg, part.basin, rows, crs, set(left.names) if left is not None else set(), enters)
    except Exception as error:
        progress.emit("warn", message=f"the lumped network's map layers could not be written: {error}")
        return
    if path is not None:
        progress.emit("output", kind="network_layers", path=str(path))


def _design_records(design, monitor, results, out: Path, progress) -> dict:
    """The record of every design line a reach carries lumped water past (W41), written beside its line series."""
    if not design:
        return {}
    t = np.asarray(monitor.times)
    grid_flow = {s.name: np.asarray(s.columns["discharge_m3s"]) for s in monitor.line_series}
    made, notes = design_records(design, out, t, grid_flow)
    for note in notes:
        progress.emit("warn", message=note)
    for name, columns in made.items():
        results.series(DESIGN_KIND, name, t, columns)
        write_series_csv(out / "series" / f"{DESIGN_KIND}_{safe_name(name)}.csv", t, columns)
        total, network = np.abs(columns[TOTAL]), np.abs(columns[NETWORK])
        progress.emit(
            "design", line=name, peak_m3s=float(total.max()) if total.size else 0.0,
            network_peak_m3s=float(network.max()) if network.size else 0.0,
            elements=[p.element for plan in design if plan.line == name for p in plan.parts],
        )  # fmt: skip
    return made


def _finish(cfg, tables, model, monitor, results, out, crs, progress, summary, t1, design=()) -> None:
    st = model.stepper
    monitor.finish(st.t)
    monitor.stop_file.unlink(missing_ok=True)
    for part in monitor.parts:
        part.finish(st.t, monitor.balance)
        part.write(results, out)
    _network_layers(cfg, tables, monitor, out, crs, progress)
    tags = {**arf_tags(cfg), **status_tags(summary, st.t, cfg)}
    _write_outputs(cfg, tables, monitor, results, out, crs, progress, tags)
    made = _design_records(design, monitor, results, out, progress)
    report_observed(cfg, out, progress)
    summary.loop_s = time.monotonic() - t1
    summary.t_end, summary.steps, summary.balance = st.t, st.nsteps, monitor.balance
    summary.dt_min = monitor.dt_min
    mean_depth = monitor.maxima.fields()["mean_depth"]
    wet = int(np.count_nonzero(mean_depth >= cfg.outputs.wet_depth))
    summary.wet_area_km2 = wet * tables.grid.dx**2 / M2_PER_KM2
    t = np.asarray(monitor.times)
    for s in monitor.line_series:
        q = np.abs(made[s.name][TOTAL] if s.name in made else np.asarray(s.columns["discharge_m3s"]))
        if q.size:
            summary.peaks[s.name] = (float(q.max()), float(t[int(np.argmax(q))]))
    b = monitor.balance
    balance = {
        "rain_m3": b.rain, "inflow_m3": b.inflow, "outflow_m3": b.outflow, "storage_start_m3": b.storage0,
        "storage_end_m3": b.storage, "error_m3": b.error, "relative_error": b.relative,
    }  # fmt: skip
    for part in monitor.parts:
        balance.update(part.figures(b))
    results.attributes({"status": summary.status, "t_end_s": st.t, "steps": st.nsteps, **balance, **tags})
    results.close()
    summary.done = dict(
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
            made = _run(cfg, folder, backend, tables, resume, progress, summary, tuple(stop_files))
            if summary.status == "finished" and made is not None:
                tags = {**arf_tags(cfg), **status_tags(summary, summary.t_end, cfg)}
                ran = cfg if summary.terrain is None else cfg.model_copy(update={"terrain": summary.terrain})
                summary.products = make_after_run(ran, *made, folder, backend, progress, stop_files, tags)
            progress.emit("done", **summary.done, products=summary.products)
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
    "check_terrain",
    "load_job",
    "preflight",
    "prepare_grid",
    "resolve_paths",
    "run_job",
]
