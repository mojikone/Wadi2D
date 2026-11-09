"""The post-run step: the pixel maps of a finished run, and their smooth drawing.

Called by ``run_job`` at the end of a run and by ``wadi2d products`` on any run folder that holds its saved maps.
Everything lands in ``<run>/pixels/``. The 5 m rasters there are the numbers of record; the polygons and the depth
drawing are how they are shown.
"""

from __future__ import annotations

import gc
import json
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from wadi2d.config.constants import M2_PER_KM2
from wadi2d.config.schema import RunConfig
from wadi2d.io.geotiff import raster_profile, write_band
from wadi2d.products.frames import frame_names, read_frames, run_maxima
from wadi2d.products.ground import CellPixels, face_sills, read_cells
from wadi2d.products.hazard import DRY, class_names, classify
from wadi2d.products.mesh import MeshMaxima, MeshResult, classes_of, mesh_sills, read_parts, write_mesh_pixels
from wadi2d.products.mesh import spread as mesh_spread
from wadi2d.products.pixels import PixelMaxima, array_module
from wadi2d.tables import GridTables

PIXEL_DIR = "pixels"
DEPTH_FILE = "pixel_depth.tif"
HAZARD_FILE = "pixel_hazard.tif"
SPEED_FILE = "pixel_speed.tif"
DV_FILE = "pixel_dv.tif"
STATS_FILE = "pixels.json"
NO_DEPTH = -9999.0
STAGES = {"ground": (0.0, 5.0), "maps": (5.0, 80.0), "rasters": (80.0, 85.0), "smooth": (85.0, 100.0)}
"""Share of the step each stage runs through, percent, for the progress bar."""


class ProductsStopped(RuntimeError):
    """The stop file appeared."""


@dataclass
class Watch:
    """How the step reports and how it is stopped."""

    emit: Callable[..., None]
    stopped: Callable[[], bool]

    def check(self) -> None:
        if self.stopped():
            raise ProductsStopped

    def tick(self, stage: str, done: int, of: int) -> None:
        self.check()
        low, high = STAGES[stage]
        share = done / of if of else 1.0
        self.emit("products", stage=stage, done=done, of=of, percent=round(low + (high - low) * share, 1))


@dataclass
class PixelResult:
    cells: CellPixels
    classes: np.ndarray
    depth: np.ndarray
    speed: np.ndarray
    dv: np.ndarray
    maps: int


def _free_device(xp) -> None:
    gc.collect()
    if xp is not np:
        xp.get_default_memory_pool().free_all_blocks()


def pixel_maxima(cfg: RunConfig, tables: GridTables, out: Path, watch: Watch, xp) -> PixelResult:
    """Every saved map, then the run's own peaks, which do not depend on how often maps were saved."""
    rule = cfg.outputs.pixels
    results = out / "results.h5"
    peak = run_maxima(results)
    keep = peak["mean_depth"] > rule.cell_depth
    cells = read_cells(cfg, tables, keep, lambda a, b: watch.tick("ground", a, b))
    if cells.rows.size == 0:
        return PixelResult(cells, np.zeros((0, cells.k**2), np.uint8), *(np.zeros((0, cells.k**2)),) * 3, 0)
    zmin = (tables.zmin - cells.datum).astype(np.float32)
    sill_x, sill_y = face_sills(tables, cells.datum)
    maxima = PixelMaxima(xp, cells, zmin, sill_x, sill_y, keep, rule)
    names = frame_names(results)
    total = len(names) + 1
    with closing(read_frames(results, names)) as frames:
        for index, (depth, mean_depth, speed) in enumerate(frames):
            watch.tick("maps", index, total)
            maxima.add(depth, mean_depth, speed)
    maxima.add(peak["depth"], peak["mean_depth"], peak["speed"], moment=False)
    maxima.lift_dv(peak["hazard"])
    watch.tick("maps", total, total)
    depth, speed, dv = maxima.result()
    del maxima
    _free_device(xp)
    return PixelResult(cells, classify(depth, speed, dv, rule), depth, speed, dv, len(names))


def pixel_box(cells: CellPixels, strip=None) -> tuple[int, int, int, int]:
    """(top, left, height, width) in pixels of the kept cells and, with a strip, its pixels too."""
    k = cells.k
    boxes = []
    if cells.rows.size:
        boxes.append((int(cells.rows.min()) * k, int(cells.cols.min()) * k, (int(cells.rows.max()) + 1) * k, (int(cells.cols.max()) + 1) * k))
    if strip is not None and strip.rows.size:
        boxes.append((int(strip.rows.min()), int(strip.cols.min()), int(strip.rows.max()) + 1, int(strip.cols.max()) + 1))
    top, left = min(b[0] for b in boxes), min(b[1] for b in boxes)
    bottom, right = max(b[2] for b in boxes), max(b[3] for b in boxes)
    return top, left, bottom - top, right - left


def spread(cells: CellPixels, values: np.ndarray, fill: float, dtype, box=None, strip=None, strip_values=None) -> np.ndarray:
    """(cells, k * k) values as one raster over the kept cells' bounding box; a strip's pixels painted after them."""
    k = cells.k
    top, left, height, width = pixel_box(cells, strip) if box is None else box
    out = np.full((height, width), fill, dtype)
    if cells.rows.size:
        down, across = np.meshgrid(np.arange(k), np.arange(k), indexing="ij")
        rows = (cells.rows * k - top)[:, None] + down.ravel()[None, :]
        cols = (cells.cols * k - left)[:, None] + across.ravel()[None, :]
        out[rows, cols] = values
    if strip is not None and strip_values is not None and strip.rows.size:
        out[strip.rows - top, strip.cols - left] = strip_values
    return out


def write_pixels(cfg: RunConfig, tables: GridTables, crs, found: PixelResult, folder: Path, tags, strip=None) -> dict:
    """The rasters of record and the statistics; the class raster and the depth come back for the smoothing.
    ``strip`` is a :class:`wadi2d.strips.pixels.StripPixelResult`: its pixels fill the cells the strip replaced."""
    rule = cfg.outputs.pixels
    cells = found.cells
    grid = tables.grid
    box = pixel_box(cells, strip)
    x0 = grid.x0 + box[1] * cells.pixel
    y0 = grid.y0 - box[0] * cells.pixel
    classes = spread(cells, found.classes, DRY, np.uint8, box, strip, None if strip is None else strip.classes)
    profile = raster_profile(classes.shape, cells.pixel, x0, y0, crs)
    write_band(folder / HAZARD_FILE, classes, profile, DRY, tags)
    wet = found.classes > DRY
    depth_band = None
    for name, values, more in (
        (DEPTH_FILE, found.depth, None if strip is None else strip.depth),
        (SPEED_FILE, found.speed, None if strip is None else strip.speed),
        (DV_FILE, found.dv, None if strip is None else strip.dv),
    ):
        on_strip = None if more is None else np.where(strip.classes > DRY, more, NO_DEPTH)
        band = spread(cells, np.where(wet, values, NO_DEPTH), NO_DEPTH, np.float32, box, strip, on_strip)
        write_band(folder / name, band, profile, NO_DEPTH, tags)
        if name == DEPTH_FILE:
            depth_band = np.where(band == NO_DEPTH, 0.0, band).astype(np.float32)
    km2 = cells.pixel**2 / M2_PER_KM2
    names = class_names(rule)
    stats = {
        "class_km2": {name: round(float((classes == k + 1).sum()) * km2, 4) for k, name in enumerate(names)},
        "maps": found.maps,
        "kept_cells": int(cells.rows.size),
        "pixel_m": cells.pixel,
        "limits": rule.hazard_limits,
        "depth_floor_m": rule.depth_floor,
        "depth_max_m": float(found.depth.max(initial=0.0)),
        "speed_max_ms": float(found.speed.max(initial=0.0)),
        "dv_max_m2s": float(found.dv.max(initial=0.0)),
        "origin": [x0, y0],
    }
    if strip is not None:
        stats["strip_pixels"] = int(strip.rows.size)
        stats["strip_depth_max_m"] = float(strip.depth.max(initial=0.0))
    return {"stats": stats, "classes": classes, "profile": profile, "depth": depth_band}


def mesh_maxima(cfg: RunConfig, tables: GridTables, out: Path, watch: Watch, xp) -> MeshResult:
    """``pixel_maxima`` for a run on a mesh: the same maps through one pass per cell size."""
    rule = cfg.outputs.pixels
    results = out / "results.h5"
    peak = run_maxima(results)
    keep = peak["mean_depth"] > rule.cell_depth
    parts = read_parts(cfg, tables, keep, lambda a, b: watch.tick("ground", a, b))
    if not parts:
        return MeshResult({}, {}, {}, {}, {}, 0)
    datum = next(iter(parts.values())).datum
    zmin = (tables.zmin - datum).astype(np.float32)
    maxima = MeshMaxima(xp, tables.grid, parts, keep, zmin, mesh_sills(tables, datum), rule)
    names = frame_names(results)
    total = len(names) + 1
    with closing(read_frames(results, names)) as frames:
        for index, (depth, mean_depth, speed) in enumerate(frames):
            watch.tick("maps", index, total)
            maxima.add(depth, mean_depth, speed)
    maxima.add(peak["depth"], peak["mean_depth"], peak["speed"], moment=False)
    maxima.lift_dv(peak["hazard"])
    watch.tick("maps", total, total)
    held = maxima.result()
    del maxima
    _free_device(xp)
    depth, speed, dv = ({s: v[n] for s, v in held.items()} for n in range(3))
    return MeshResult(parts, classes_of(depth, speed, dv, rule), depth, speed, dv, len(names))


def make_products(
    cfg: RunConfig, tables: GridTables, crs, out: Path, watch: Watch, backend: str, tags: dict | None = None
) -> dict:
    """The whole step; returns the statistics. ``ProductsStopped`` leaves nothing half-written behind."""
    from wadi2d.products.smooth import make_drawings

    on_mesh = getattr(tables.grid, "quad", False)
    maxima_of = mesh_maxima if on_mesh else pixel_maxima
    xp = array_module(backend)
    _free_device(xp)
    try:
        found = maxima_of(cfg, tables, out, watch, xp)
    except Exception as error:
        if xp is np or type(error).__name__ != "OutOfMemoryError":
            raise
        watch.emit("warn", message="The pixel maps did not fit on the GPU, so they run on the CPU, more slowly.")
        _free_device(xp)
        found = maxima_of(cfg, tables, out, watch, np)
    folder = out / PIXEL_DIR
    folder.mkdir(parents=True, exist_ok=True)
    strip = None
    if not on_mesh and getattr(tables, "strip", None) is not None:
        from wadi2d.strips.pixels import strip_pixel_maxima

        strip = strip_pixel_maxima(cfg, tables, tables.strip, out, watch, xp, found.cells.datum)
        _free_device(xp)
    nothing = (found.kept if on_mesh else found.cells.rows.size) == 0 and (strip is None or strip.rows.size == 0)
    if nothing:
        (folder / STATS_FILE).write_text(json.dumps({"class_km2": {}, "maps": found.maps}), encoding="utf-8")
        return {"class_km2": {}}
    watch.tick("rasters", 0, 1)
    if on_mesh:
        files = {"hazard": HAZARD_FILE, "depth": DEPTH_FILE, "speed": SPEED_FILE, "dv": DV_FILE, "nodata": NO_DEPTH}
        written = write_mesh_pixels(cfg, tables, crs, found, folder, tags, files)
    else:
        written = write_pixels(cfg, tables, crs, found, folder, tags, strip)
    stats = written["stats"]
    if cfg.outputs.smooth.enabled:
        if on_mesh:
            depth = mesh_spread(found.cells, found.depth, 0.0, np.float32)
        else:
            depth = written["depth"]
        del found
        _free_device(xp)
        stats["smooth"] = make_drawings(cfg, tables, written, depth, folder, crs, watch, xp)
    (folder / STATS_FILE).write_text(json.dumps(stats, indent=1), encoding="utf-8")
    return stats
