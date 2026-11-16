"""What a finished run holds for a drawing: its saved maps, its cells and, where it can be had, what the pixel rule needs.

The pixel rule needs each cell's lowest point and the ground of each face, which are in the tables, and the DEM. A run
whose tables are in its grid cache opens in seconds. One whose cache is gone has its tables built again, as
``wadi2d products`` does. A run on a mesh or with aligned cells, or one whose DEM has moved, is drawn by its cell values
alone, and says so.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import h5py
import numpy as np

from wadi2d.config.schema import RunConfig
from wadi2d.products.frames import frame_names
from wadi2d.products.time_slider import frame_seconds

PIXEL, CELLS = "pixel", "cells"
"""How fine a run can be drawn: at the terrain pixel, or one value a cell."""
FRAME_TOLERANCE_S = 0.5
"""A frame this far past a time still counts as at it: the plugin's own rule for the mesh layer and the result lines."""
FIELDS = ("depth", "mean_depth", "speed")
CHUNK = 128
"""Cells along a chunk of a saved map."""
MESH_NOTE = "This run is on a mesh of several cell sizes: it is drawn one value a cell, not at the terrain pixel."
STRIP_NOTE = (
    "This run has cells aligned with breaklines: the squares are drawn one value a cell, not at the terrain pixel, "
    "and the aligned cells are not drawn."
)


@dataclass
class PixelTables:
    """What the pixel rule reads besides the ground, on the grid of the saved maps, over ``datum``."""

    keep: np.ndarray
    zmin: np.ndarray
    sill_x: np.ndarray
    sill_y: np.ndarray
    datum: float
    grid: object
    """The run's ``TileGrid``: terrain objects are laid on it."""


@dataclass
class RunSource:
    run: Path
    cfg: RunConfig
    x0: float
    y0: float
    dx: float
    mask: np.ndarray
    crs: str
    names: list[str]
    times: np.ndarray
    detail: str = CELLS
    note: str = ""
    tables: PixelTables | None = None
    _held: dict = field(default_factory=dict)

    @property
    def shape(self) -> tuple[int, int]:
        return self.mask.shape

    @property
    def results(self) -> Path:
        return self.run / "results.h5"

    def extent(self) -> tuple[float, float, float, float]:
        """(xmin, ymin, xmax, ymax) of the active cells."""
        rows, cols = np.nonzero(self.mask.any(axis=1))[0], np.nonzero(self.mask.any(axis=0))[0]
        if rows.size == 0:
            return self.x0, self.y0, self.x0, self.y0
        return (
            self.x0 + float(cols[0]) * self.dx,
            self.y0 - float(rows[-1] + 1) * self.dx,
            self.x0 + float(cols[-1] + 1) * self.dx,
            self.y0 - float(rows[0]) * self.dx,
        )

    def frame_at(self, t_s: float | None) -> int:
        """The saved frame shown at a time: the last one at or before it, and the last of all when no time is given."""
        if t_s is None:
            return len(self.names) - 1
        found = int(np.searchsorted(self.times, t_s + FRAME_TOLERANCE_S, side="right")) - 1
        return max(found, 0)

    def window(self, frame: int, rows: tuple[int, int], cols: tuple[int, int]) -> dict[str, np.ndarray]:
        """Depth, mean depth and speed of one frame over rows [a, b) and columns [a, b).

        Read by whole chunks and held, so a pan beside the last view and a drawing of the same frame cost nothing."""
        held = self._held.get(frame)
        if held is None or not (held[0][0] <= rows[0] and rows[1] <= held[0][1] and held[1][0] <= cols[0] and cols[1] <= held[1][1]):
            ny, nx = self.shape
            r = (rows[0] // CHUNK * CHUNK, min(-(-rows[1] // CHUNK) * CHUNK, ny))
            c = (cols[0] // CHUNK * CHUNK, min(-(-cols[1] // CHUNK) * CHUNK, nx))
            with h5py.File(self.results, "r") as f:
                group = f["maps"][self.names[frame]]
                data = {name: group[name][r[0] : r[1], c[0] : c[1]] for name in FIELDS}
            held = (r, c, data)
            self._held.pop(frame, None)
            self._held[frame] = held
            while len(self._held) > self.cfg.outputs.slider.frames_held:
                self._held.pop(next(iter(self._held)))
        (r0, _), (c0, _), data = held
        return {name: a[rows[0] - r0 : rows[1] - r0, cols[0] - c0 : cols[1] - c0] for name, a in data.items()}


def _config(run: Path) -> RunConfig:
    return RunConfig.model_validate_json((run / "config.resolved.json").read_text(encoding="utf-8"))


def _cached_tables(cfg: RunConfig, cache: Path):
    """The tables of a uniform grid straight from the cache, without the domain mask a fresh build needs first."""
    from wadi2d.io.cache import cache_path, load_tables
    from wadi2d.run import grid_key, grid_window
    from wadi2d.terrain import RasterBed
    from wadi2d.terrain.sections import with_tables

    full = with_tables(cfg)
    with RasterBed(full.terrain.dem, full.terrain.pixel_stride) as bed:
        key = grid_key(full, bed, grid_window(full, bed))
    return load_tables(cache_path(cache, key), key)


def _pixel_tables(source: RunSource, say: Callable[[str], None]) -> PixelTables:
    from wadi2d.products.ground import face_sills
    from wadi2d.products.pixels import kept_cells
    from wadi2d.run import prepare_grid

    cfg, run = source.cfg, source.run
    cache = Path(cfg.grid.cache_dir) if cfg.grid.cache_dir else run / "cache"
    tables = _cached_tables(cfg, cache)
    if tables is None:
        say("The tables of this run are not in its cache: building them again, which takes as long as it did before the run.")
        tables, _crs = prepare_grid(cfg, cache)
    grid = tables.grid
    same = grid.shape == source.shape and abs(grid.x0 - source.x0) < 1e-6 and abs(grid.y0 - source.y0) < 1e-6
    if not same or abs(grid.dx - source.dx) > 1e-9:
        raise ValueError("the tables built from this run's job do not lie on the grid of its saved maps")
    with h5py.File(source.results, "r") as f:
        keep = kept_cells(f["maxima"]["mean_depth"][:], cfg.outputs.pixels)
    datum = float(tables.zmin[keep].min()) if keep.any() else 0.0
    zmin = (tables.zmin - datum).astype(np.float32)
    sill_x, sill_y = face_sills(tables, datum)
    return PixelTables(keep, zmin, sill_x, sill_y, datum, grid)


def open_run(run: Path, say: Callable[[str], None] = lambda _text: None) -> RunSource:
    """A run folder ready to be drawn. ``say`` takes a sentence for whoever waits. Raises ValueError on no saved maps."""
    run = Path(run)
    results = run / "results.h5"
    if not results.is_file() or not (run / "config.resolved.json").is_file():
        raise ValueError(f"{run} holds no finished run")
    cfg = _config(run)
    names = frame_names(results)
    if not names:
        raise ValueError("This run saved no maps, so there is nothing to draw over time. Save maps, and run again.")
    with h5py.File(results, "r") as f:
        mask = f["mask"][:]
        x0, y0, dx = (float(f.attrs[name]) for name in ("x0", "y0", "dx"))
        crs = str(f.attrs.get("crs", ""))
    source = RunSource(run, cfg, x0, y0, dx, mask, crs, names, frame_seconds(names))
    if cfg.mesh.enabled:
        source.note = MESH_NOTE
    elif cfg.strips.enabled:
        source.note = STRIP_NOTE
    else:
        from wadi2d.run import JobError

        try:
            source.tables = _pixel_tables(source, say)
            source.detail = PIXEL
        except (OSError, ValueError, KeyError, JobError) as error:  # the DEM moved, the job no longer builds: cells still draw
            source.note = f"The terrain of this run could not be read ({error}), so it is drawn one value a cell."
    return source
