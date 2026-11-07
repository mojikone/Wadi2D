"""A run's result lines, for the plugin: the upfront ones as recorded, and any line read back from the saved frames.

Upfront lines and points were computed during the run, at every series step, from the discharge on the faces: those are
the numbers of record. A line read from saved frames sees only what a frame keeps, so it has the map interval. When
the run saved the face discharges with its maps (``outputs.face_discharge``), the line reads the same faces, signs and
sum an upfront line uses (``face_flow``): the number of record at the frame interval. When it did not, its flow is an
estimate from depth and speed: mean depth x speed x length, each sample of the line turned by the angle between the
line and the flow. A frame holds a speed and no direction, so the direction is read from the slope of the water surface
around the sample, and the estimate has a size and no sign. The answer says which it is.

Mean depth and not depth: a cell's depth is the level over its deepest point, which reads 1.5 to 8 x the flow of record.
A level is the depth over a cell's lowest point, and that lowest point comes from the run's own maps, ``max_level`` less
the deepest depth, so a wet cell needs neither the tables nor the DEM. A cell the water never reached has no level.

Only the blocks of a map the line passes through are read, so a line costs the same on 17 M cells as on 50,000.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np
import rasterio
from rasterio.windows import Window

from wadi2d.config.schema import RunConfig
from wadi2d.engine.design_lines import DESIGN_KIND
from wadi2d.engine.network_series import NETWORK_KIND
from wadi2d.grid.tiles import TileGrid
from wadi2d.products.face_flow import (
    FLOW_ESTIMATE,
    FLOW_FACES,
    X_FACES,
    Y_FACES,
    FaceCrossing,
    face_crossing,
    face_flow,
    frames_have_faces,
)
from wadi2d.products.frames import frame_names
from wadi2d.products.time_slider import frame_seconds, read_tiles
from wadi2d.solver.layout import TILE
from wadi2d.terrain import Ground, RasterBed, apply_objects
from wadi2d.terrain.sections import with_tables

MAX_LEVEL = Path("maps") / "max_level.tif"
SAMPLES_PER_CELL = 4
"""Samples along a line per cell of the run."""
MOST_SAMPLES = 2000
"""A longer line takes wider samples."""
BLOCK = 128
"""Cells of a map read at a time: the chunk of ``results.h5``."""
TIGHT_BLOCK = 64
"""Pixels of the DEM read at a time, along the line."""
AROUND = (-1, 0, 1)
STENCIL = 9
MIDDLE = 4
"""The sample itself among the nine."""
SOBEL = (1.0, 2.0, 1.0)
"""A wider reading of the slope than the two neighbours alone: it reads a cell's own bumps less."""
FLOW_FLOOR = 0.005
"""Below this a cell carries no flow, m. Far under the depth floor of the maps: a sheet that is dry on a map still runs,
and at the map's floor a rain-fed slope read 0.44 of its record, against 0.71 here. A line on a wadi moved by 3 % at most."""
DIGITS_LEVEL, DIGITS_FLOW = 3, 3
GROUND_DEM, GROUND_CELLS = "dem", "cells"


@dataclass
class Samples:
    """Points along a line, evenly spaced, with the raster cell of each and the way the line runs there."""

    station: np.ndarray
    x: np.ndarray
    y: np.ndarray
    east: np.ndarray
    north: np.ndarray
    spacing: float

    @property
    def count(self) -> int:
        return self.station.size


def sample_line(coordinates: list, spacing: float, most: int = MOST_SAMPLES) -> Samples:
    """Points at the middle of equal stretches of the line, about ``spacing`` apart and never more than ``most``."""
    points = np.asarray([p[:2] for p in coordinates], np.float64)
    if points.shape[0] < 2:
        raise ValueError("A result line needs at least two points.")
    steps = np.diff(points, axis=0)
    lengths = np.hypot(steps[:, 0], steps[:, 1])
    points, steps, lengths = points[np.r_[True, lengths > 0.0]], steps[lengths > 0.0], lengths[lengths > 0.0]
    if lengths.size == 0:
        raise ValueError("A result line needs a length.")
    along = np.concatenate(((0.0,), np.cumsum(lengths)))
    count = min(max(int(np.ceil(along[-1] / spacing)), 1), most)
    width = float(along[-1]) / count
    station = (np.arange(count) + 0.5) * width
    part = np.clip(np.searchsorted(along, station, side="right") - 1, 0, lengths.size - 1)
    return Samples(
        station,
        np.interp(station, along, points[:, 0]),
        np.interp(station, along, points[:, 1]),
        steps[part, 0] / lengths[part],
        steps[part, 1] / lengths[part],
        width,
    )


@dataclass
class LineCells:
    """Where a line's samples read a map: ``middle`` each sample's cell, ``stencil`` the nine around it, nine rows of samples."""

    middle: Picker
    stencil: Picker
    inside: np.ndarray
    on_raster: np.ndarray


class Picker:
    """Reads a set of cells from a large raster, one block at a time, in the order they were given."""

    def __init__(self, rows: np.ndarray, columns: np.ndarray, block: int = BLOCK) -> None:
        self.rows, self.columns = rows, columns
        self.block = block
        keys = rows // block * (1 << 32) + columns // block
        self.groups = [np.nonzero(keys == key)[0] for key in np.unique(keys)]

    def read(self, window: Callable[[int, int, int, int], np.ndarray]) -> np.ndarray:
        """``window(row, column, rows, columns)`` is one rectangle of the raster."""
        out = np.empty(self.rows.size, np.float32)
        for group in self.groups:
            row0 = int(self.rows[group].min())
            column0 = int(self.columns[group].min())
            row1 = int(self.rows[group].max()) + 1
            column1 = int(self.columns[group].max()) + 1
            data = window(row0, column0, row1 - row0, column1 - column0)
            out[group] = data[self.rows[group] - row0, self.columns[group] - column0]
        return out


def dataset_window(dataset: h5py.Dataset) -> Callable[[int, int, int, int], np.ndarray]:
    return lambda row, column, rows, columns: dataset[row : row + rows, column : column + columns]


def tif_window(src) -> Callable[[int, int, int, int], np.ndarray]:
    return lambda row, column, rows, columns: src.read(
        1, window=Window(column, row, columns, rows), masked=True
    ).filled(np.nan)


def surface_way(level: np.ndarray, wet: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The way down the water surface, east and north, from (3, 3, n) levels and wet flags, row 0 to the north.

    Only differences between two wet cells count, so a bank does not turn the flow. Where nothing can be read both are
    zero, and the caller counts the sample as crossing square.
    """
    east = np.zeros(level.shape[2])
    north = np.zeros(level.shape[2])
    for k, weight in enumerate(SOBEL):
        for a, b in ((0, 1), (1, 2)):
            east += weight * np.where(wet[k, a] & wet[k, b], level[k, b] - level[k, a], 0.0)
            north += weight * np.where(wet[a, k] & wet[b, k], level[a, k] - level[b, k], 0.0)
    size = np.hypot(east, north)
    seen = size > 0.0
    return (
        np.where(seen, -east / np.where(seen, size, 1.0), 0.0),
        np.where(seen, -north / np.where(seen, size, 1.0), 0.0),
    )


def crossing(samples: Samples, level: np.ndarray, wet: np.ndarray) -> np.ndarray:
    """The share of the flow that crosses the line at each sample, 0 to 1; 1 where no direction can be read."""
    east, north = surface_way(level, wet)
    across = np.abs(east * samples.north - north * samples.east)
    return np.where((east == 0.0) & (north == 0.0), 1.0, across)


def line_flow(samples: Samples, mean_depth: np.ndarray, speed: np.ndarray, share: np.ndarray, wet: np.ndarray) -> float:
    """Estimated flow through the line at one frame, m3/s."""
    return float(np.sum(np.where(wet, mean_depth * speed * share, 0.0)) * samples.spacing)


def cell_sizes(run: Path, cfg: RunConfig, shape: tuple[int, int]) -> np.ndarray:
    """Finest cells along a cell, per tile of finest cells; 1 everywhere on a uniform grid."""
    tiles = np.ones((shape[0] // TILE + 1, shape[1] // TILE + 1), np.int64)
    if cfg.mesh.enabled:
        for row, column, level in read_tiles(run):
            size = 1 << level
            tiles[row : row + size, column : column + size] = size
    return tiles


def ground_along(cfg: RunConfig, samples: Samples, mask: np.ndarray, x0: float, y0: float, dx: float) -> np.ndarray:
    """The terrain at the samples, with the run's terrain objects applied, as the tables saw it; NaN off the DEM."""
    with RasterBed(cfg.terrain.dem, cfg.terrain.pixel_stride) as bed:
        bed.bind(x0, y0)
        edit = None
        if cfg.terrain.objects:
            objects = with_tables(cfg).terrain.objects
            edit = apply_objects(TileGrid(x0, y0, dx, mask), objects, bed.pixel, cfg.terrain, Ground(bed, x0, y0)).edit
        rows = np.floor((y0 - samples.y) / bed.pixel).astype(np.int64)
        columns = np.floor((samples.x - x0) / bed.pixel).astype(np.int64)

        def window(row: int, column: int, height: int, width: int) -> np.ndarray:
            z = bed.read(row, column, height, width)
            if edit is not None:
                edit(z, row, column)
            return z

        ground = Picker(rows, columns, TIGHT_BLOCK).read(window).astype(np.float64)
        east, south = bed.left + bed.src.width * bed.native, bed.top - bed.src.height * bed.native
        on_dem = (samples.x > bed.left) & (samples.x < east) & (samples.y < bed.top) & (samples.y > south)
    return np.where(on_dem, ground, np.nan)


def _rounded(values: np.ndarray, digits: int) -> list:
    return [None if not np.isfinite(v) else round(float(v), digits) for v in values]


def _read_config(run: Path) -> RunConfig:
    return RunConfig.model_validate_json((run / "config.resolved.json").read_text(encoding="utf-8"))


def _line_cells(samples: Samples, mask: np.ndarray, x0: float, y0: float, dx: float, tiles: np.ndarray) -> LineCells:
    ny, nx = mask.shape
    rows = np.floor((y0 - samples.y) / dx).astype(np.int64)
    columns = np.floor((samples.x - x0) / dx).astype(np.int64)
    inside = (rows >= 0) & (rows < ny) & (columns >= 0) & (columns < nx)
    rows, columns = np.clip(rows, 0, ny - 1), np.clip(columns, 0, nx - 1)
    inside &= mask[rows, columns]
    if not inside.any():
        raise ValueError("This line does not cross the model.")
    sizes = tiles[rows // TILE, columns // TILE]
    near_rows = np.concatenate([rows + a * sizes for a in AROUND for _ in AROUND])
    near_columns = np.concatenate([columns + b * sizes for _ in AROUND for b in AROUND])
    on_raster = (near_rows >= 0) & (near_rows < ny) & (near_columns >= 0) & (near_columns < nx)
    stencil = Picker(np.clip(near_rows, 0, ny - 1), np.clip(near_columns, 0, nx - 1))
    return LineCells(Picker(rows, columns), stencil, inside, on_raster)


class FacePickers:
    """A line's face crossing with its cells grouped for reading, once for every frame."""

    def __init__(self, crossing: FaceCrossing) -> None:
        self.crossing = crossing
        self.x = Picker(crossing.x_rows, crossing.x_columns)
        self.y = Picker(crossing.y_rows, crossing.y_columns)

    def flow(self, group: h5py.Group) -> float:
        qx = self.x.read(dataset_window(group[X_FACES]))
        qy = self.y.read(dataset_window(group[Y_FACES]))
        return face_flow(qx, qy, self.crossing)


def _estimated_flow(samples: Samples, cells: LineCells, group: h5py.Group, running: np.ndarray, share: np.ndarray) -> float:
    mean_depth = cells.middle.read(dataset_window(group["mean_depth"]))
    speed = cells.middle.read(dataset_window(group["speed"]))
    return line_flow(samples, mean_depth, speed, share, running[1, 1] & cells.inside)


def read_line(run: Path, coordinates: list, name: str = "") -> dict:
    """Flow, deepest water and the water surface along a line, at every saved frame; see the module's note."""
    results = run / "results.h5"
    names = frame_names(results)
    if len(names) < 2:
        raise ValueError(f"This run saved {len(names)} map(s), and a line needs two. Save maps more often, or run longer.")
    cfg = _read_config(run)
    floor = cfg.outputs.pixels.depth_floor
    with h5py.File(results, "r") as f, rasterio.open(run / MAX_LEVEL) as peak_level:
        mask = f["mask"][:]
        x0, y0, dx = (float(f.attrs[key]) for key in ("x0", "y0", "dx"))
        samples = sample_line(coordinates, dx / SAMPLES_PER_CELL)
        count = samples.count
        tiles = cell_sizes(run, cfg, mask.shape)
        cells = _line_cells(samples, mask, x0, y0, dx, tiles)
        low = cells.stencil.read(tif_window(peak_level)) - cells.stencil.read(dataset_window(f["maxima"]["depth"]))
        low = low.astype(np.float64)
        ground, source = _terrain(cfg, samples, mask, x0, y0, dx, low.reshape(STENCIL, count)[MIDDLE])
        faces = FacePickers(face_crossing(mask, x0, y0, dx, coordinates, tiles)) if frames_have_faces(f, names) else None
        flows, deepest, levels = [], [], []
        for frame in names:
            group = f["maps"][frame]
            depth = cells.stencil.read(dataset_window(group["depth"])).astype(np.float64)
            known = np.isfinite(low) & cells.on_raster
            level = (low + depth).reshape(3, 3, count)
            running = (known & (depth >= FLOW_FLOOR)).reshape(3, 3, count)
            if faces is not None:
                flows.append(faces.flow(group))
            else:
                flows.append(_estimated_flow(samples, cells, group, running, crossing(samples, level, running)))
            shown = (known & (depth >= floor)).reshape(3, 3, count)[1, 1] & cells.inside
            surface = np.where(shown, level[1, 1], np.nan)
            water = surface - ground
            deep = np.where(np.isfinite(water) & (water > 0.0), water, 0.0)
            deepest.append(float(deep.max()))
            levels.append(np.where(deep > 0.0, surface, np.nan))
    times = frame_seconds(names)
    return {
        "name": name,
        "t_s": times.tolist(),
        "interval_s": float(np.median(np.diff(times))),
        "length_m": round(float(count * samples.spacing), 2),
        "flow_source": FLOW_FACES if faces is not None else FLOW_ESTIMATE,
        "flow_m3s": [round(q, DIGITS_FLOW) for q in flows],
        "deepest_m": [round(d, DIGITS_LEVEL) for d in deepest],
        "station_m": _rounded(samples.station, DIGITS_LEVEL),
        "ground_m": _rounded(ground, DIGITS_LEVEL),
        "ground_source": source,
        "level_m": [_rounded(level, DIGITS_LEVEL) for level in levels],
    }


def _terrain(cfg, samples: Samples, mask, x0: float, y0: float, dx: float, low: np.ndarray) -> tuple[np.ndarray, str]:
    """The terrain, or each cell's lowest point when the DEM is no longer where the run found it."""
    try:
        return ground_along(cfg, samples, mask, x0, y0, dx), GROUND_DEM
    except (OSError, ValueError):
        return low, GROUND_CELLS


def _series(f: h5py.File, kind: str, name: str) -> dict:
    """A recorded series by the name the job gave it; empty when the run did not reach it."""
    if f"series/{kind}" not in f:
        return {}
    for group in f["series"][kind].values():
        if group.attrs.get("name") == name:
            return {key: [round(float(v), DIGITS_FLOW) for v in group[key][:]] for key in group}
    return {}


def catalogue(run: Path) -> dict:
    """What a run holds: its saved frames, its upfront lines and points, and its lumped elements, with their series."""
    results = run / "results.h5"
    cfg = _read_config(run)
    names = frame_names(results)
    times = frame_seconds(names) if names else np.zeros(0)
    with h5py.File(results, "r") as f:
        crs = str(f.attrs.get("crs", ""))
        lines = [
            {"name": line.name, "coordinates": [list(p) for p in line.coordinates], **_series(f, "lines", line.name)}
            for line in cfg.outputs.lines
        ]
        for line in lines:
            design = _series(f, DESIGN_KIND, line["name"])
            if design:
                line["design"] = design
        points = [{"name": p.name, "x": p.x, "y": p.y, **_series(f, "points", p.name)} for p in cfg.outputs.points]
        lumped = [
            {"name": str(group.attrs.get("name", key)), **_series(f, NETWORK_KIND, str(group.attrs.get("name", key)))}
            for key, group in (f["series"][NETWORK_KIND].items() if f"series/{NETWORK_KIND}" in f else ())
        ]
    return {
        "crs": crs,
        "frames_s": times.tolist(),
        "interval_s": float(np.median(np.diff(times))) if times.size > 1 else 0.0,
        "lines": lines,
        "points": points,
        "lumped": lumped,
    }
