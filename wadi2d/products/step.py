"""The post-run step: the pixel maps of a finished run, and their smooth drawing.

Called by ``run_job`` at the end of a run and by ``wadi2d products`` on any run folder that holds its saved maps.
Everything lands in ``<run>/pixels/``. The 5 m rasters there are the numbers of record; the polygons and the depth
drawing are how they are shown.
"""

from __future__ import annotations

import gc
import json
from collections.abc import Callable, Iterator
from contextlib import ExitStack, closing
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio

from wadi2d.config.constants import M2_PER_KM2
from wadi2d.config.schema import RunConfig
from wadi2d.io.geotiff import BLOCK, THREADS, BandWriter, raster_profile
from wadi2d.products.frames import frame_names, read_frames, run_maxima
from wadi2d.products.ground import CellPixels, face_sills, read_cells
from wadi2d.products.hazard import DRY, class_names, classify
from wadi2d.products.mesh import MeshMaxima, MeshResult, classes_of, mesh_sills, read_parts, write_mesh_pixels
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
WINDOW = 8 * BLOCK
"""Pixels along a window of the rasters of record as they are written: a whole number of their blocks."""


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


@dataclass
class WindowPart:
    """One window of the rasters and where its pixels come from: kept cells, then the strip's pixels over them."""

    row: int
    col: int
    shape: tuple[int, int]
    cells: np.ndarray
    """The kept cells that reach into the window."""
    inside: np.ndarray | None
    """Which of their pixels fall in it, (cells, k * k); None when all do."""
    at: np.ndarray
    """Where those pixels go in the window, flat."""
    strip: np.ndarray
    """The strip's pixels in the window."""
    strip_at: np.ndarray

    def paint(self, values: np.ndarray, strip_values, fill: float, dtype) -> np.ndarray:
        """The window of one raster: ``fill``, then the values of ``cells``, (cells, k * k), then those of ``strip``."""
        out = np.full(self.shape, fill, dtype)
        if self.cells.size:
            out.put(self.at, values if self.inside is None else values[self.inside])
        if strip_values is not None and self.strip.size:
            out.put(self.strip_at, strip_values)
        return out


def window_parts(cells: CellPixels, box: tuple[int, int, int, int], strip=None, size: int = WINDOW) -> Iterator[WindowPart]:
    """The windows of ``size`` pixels of the raster over ``box`` that hold a kept cell or a strip pixel, row by row.

    Together they paint what :func:`spread` paints and nothing else: a window with nothing in it is not made, so the
    work and the file follow the flood, not its bounding box (W50)."""
    k = cells.k
    top, left, height, width = box
    pr = cells.rows.astype(np.int64) * k - top
    pc = cells.cols.astype(np.int64) * k - left
    down, across = (a.ravel() for a in np.meshgrid(np.arange(k), np.arange(k), indexing="ij"))
    none = np.zeros(0, np.int64)
    across_windows = -(-width // size)
    s_order, s_key, sr, sc = none, none, none, none
    if strip is not None and strip.rows.size:
        sr, sc = strip.rows.astype(np.int64) - top, strip.cols.astype(np.int64) - left
        key = (sr // size) * across_windows + sc // size
        s_order = np.argsort(key, kind="stable")
        s_key = key[s_order]
    for r0 in range(0, height, size):
        band = np.nonzero((pr < r0 + size) & (pr + k > r0))[0]
        first, last = pc[band] // size, (pc[band] + k - 1) // size
        for w in range(across_windows):
            c0 = w * size
            own = band[(first <= w) & (last >= w)]
            a, b = np.searchsorted(s_key, [(r0 // size) * across_windows + w, (r0 // size) * across_windows + w + 1])
            dots = s_order[a:b]
            if own.size == 0 and dots.size == 0:
                continue
            shape = (min(size, height - r0), min(size, width - c0))
            rr = (pr[own] - r0)[:, None] + down[None, :]
            cc = (pc[own] - c0)[:, None] + across[None, :]
            inside = (rr >= 0) & (rr < shape[0]) & (cc >= 0) & (cc < shape[1])
            at = rr * shape[1] + cc
            whole = bool(inside.all())
            yield WindowPart(
                r0, c0, shape, own, None if whole else inside, at if whole else at[inside],
                dots, (sr[dots] - r0) * shape[1] + (sc[dots] - c0),
            )  # fmt: skip


def write_pixels(cfg: RunConfig, tables: GridTables, crs, found: PixelResult, folder: Path, tags, strip=None, watch=None) -> dict:
    """The rasters of record and the statistics, window by window over the wet ground (W50).
    ``strip`` is a :class:`wadi2d.strips.pixels.StripPixelResult`: its pixels fill the cells the strip replaced."""
    rule = cfg.outputs.pixels
    cells = found.cells
    grid = tables.grid
    box = pixel_box(cells, strip)
    x0 = grid.x0 + box[1] * cells.pixel
    y0 = grid.y0 - box[0] * cells.pixel
    profile = raster_profile(box[2:], cells.pixel, x0, y0, crs)
    wet = found.classes > DRY
    on_strip = None if strip is None else strip.classes > DRY
    measures = (
        (DEPTH_FILE, found.depth, None if strip is None else strip.depth),
        (SPEED_FILE, found.speed, None if strip is None else strip.speed),
        (DV_FILE, found.dv, None if strip is None else strip.dv),
    )
    counts = np.zeros(np.iinfo(np.uint8).max + 1, np.int64)
    rows, row = -(-box[2] // WINDOW), -1
    with ExitStack() as files:
        hazard = files.enter_context(BandWriter(folder / HAZARD_FILE, profile, np.uint8, DRY, tags))
        bands = [files.enter_context(BandWriter(folder / name, profile, np.float32, NO_DEPTH, tags)) for name, *_ in measures]
        for part in window_parts(cells, box, strip):
            if watch is not None and part.row != row:
                row = part.row
                watch.tick("rasters", row // WINDOW, rows)
            tile = part.paint(found.classes[part.cells], None if strip is None else strip.classes[part.strip], DRY, np.uint8)
            hazard.write(tile, part.row, part.col)
            counts += np.bincount(tile.ravel(), minlength=counts.size)
            for band, (_name, values, more) in zip(bands, measures, strict=True):
                marked = np.where(wet[part.cells], values[part.cells], NO_DEPTH)
                dots = None if more is None else np.where(on_strip[part.strip], more[part.strip], NO_DEPTH)
                band.write(part.paint(marked, dots, NO_DEPTH, np.float32), part.row, part.col)
    km2 = cells.pixel**2 / M2_PER_KM2
    names = class_names(rule)
    stats = {
        "class_km2": {name: round(float(counts[k + 1]) * km2, 4) for k, name in enumerate(names)},
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
    return {"stats": stats, "profile": profile}


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
    from wadi2d.products.smooth import make_drawings, run_layers

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
        written = write_pixels(cfg, tables, crs, found, folder, tags, strip, watch)
    stats, profile = written["stats"], written["profile"]
    if cfg.outputs.smooth.enabled:
        layers = run_layers(cfg, tables, crs)
        del found, written
        _free_device(xp)
        # the rasters are written window by window and not held, so the drawing reads them back; on a mesh this is
        # new: the picture there was drawn from every kept pixel's depth, now from the depth of record, dry under
        # the floor, as on the uniform grid
        classes, depth, _profile = read_record(folder)
        stats["smooth"] = make_drawings(cfg, classes, depth, profile, folder, crs, watch, xp, layers)
    (folder / STATS_FILE).write_text(json.dumps(stats, indent=1), encoding="utf-8")
    return stats


def read_record(folder: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    """The class raster, the depth with 0 where dry, and the profile of a run's rasters of record: what the drawing
    is made from, in the run and after it."""
    with rasterio.Env(GDAL_NUM_THREADS=THREADS):
        with rasterio.open(folder / HAZARD_FILE) as src:
            classes = src.read(1)
            t = src.transform
            profile = raster_profile(src.shape, t.a, t.c, t.f, src.crs)
        with rasterio.open(folder / DEPTH_FILE) as src:
            depth = src.read(1)
    depth[depth == NO_DEPTH] = 0.0
    return classes, depth, profile
