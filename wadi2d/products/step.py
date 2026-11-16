"""The post-run step: the pixel maps of a finished run, and their smooth drawing.

Called by ``run_job`` at the end of a run and by ``wadi2d products`` on any run folder that holds its saved maps.
Everything lands in ``<run>/pixels/``. The 5 m rasters there are the numbers of record; the polygons and the depth
drawing are how they are shown, and are made only when asked for: with the run (``outputs.smooth.enabled``) or
after it (``wadi2d drawings``).
"""

from __future__ import annotations

import gc
import json
from collections.abc import Callable, Iterator
from contextlib import ExitStack, closing
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import rasterio

from wadi2d.config.constants import M2_PER_KM2
from wadi2d.config.schema import RunConfig
from wadi2d.demstore import cache_folder
from wadi2d.io.geopackage import write_geopackage
from wadi2d.io.geotiff import BLOCK, THREADS, BandWriter, float_record, raster_profile
from wadi2d.products.blocks import (
    BAND_GROUND_BYTES,
    HOST_RESULT_BYTES,
    SQUARE_HOST_BYTES,
    SQUARE_PIXEL_BYTES,
    STACK_BYTES,
    STACK_VALUE_BYTES,
    Block,
    Stack,
    device_budget,
    plan_bands,
    plan_blocks,
    read_square_stack,
    read_strip_stack,
    square_window_pixels,
)
from wadi2d.products.frames import frame_names, read_frames, run_maxima, strip_run_maxima
from wadi2d.products.ground import CellPixels, CellReader, face_sills
from wadi2d.products.hazard import DRY, class_names, classify, off_the_map
from wadi2d.products.mesh import MeshMaxima, MeshResult, classes_of, mesh_sills, read_parts, write_mesh_pixels
from wadi2d.products.pixels import BYTES, CELL_FILL, PixelMaxima, array_module, halo, kept_cells
from wadi2d.tables import GridTables

PIXEL_DIR = "pixels"
DEPTH_FILE = "pixel_depth.tif"
HAZARD_FILE = "pixel_hazard.tif"
SPEED_FILE = "pixel_speed.tif"
DV_FILE = "pixel_dv.tif"
LEVEL_FILE = "pixel_level.tif"
"""The highest water level at each pixel, m, the terrain's datum: its ground plus its highest depth (his question of
2026-11-16, the water surface map of RAS Mapper)."""
STATS_FILE = "pixels.json"
NO_DEPTH = -9999.0
STAGES = {"ground": (0.0, 5.0), "maps": (5.0, 80.0), "rasters": (80.0, 85.0), "smooth": (85.0, 100.0)}
"""Share of the step each stage runs through, percent, for the progress bar."""
STAGES_RECORD = {"ground": (0.0, 10.0), "maps": (10.0, 95.0), "rasters": (95.0, 100.0)}
"""The same for a step that makes the rasters of record alone (W50). On the lattice the ground of a block is read
and its windows are written with its maps, so ``maps`` is most of the step (W86)."""
STAGES_DRAWING = {"smooth": (0.0, 100.0)}
"""And for the polygons and the depth drawing made after the run."""
SQUEEZES = (1.0, 0.5, 0.25)
"""Shares of the card's room the blocks are cut to, tried in turn while a try runs out of device memory."""
WINDOW = 8 * BLOCK
"""Pixels along a window of the rasters of record as they are written: a whole number of their blocks."""


class ProductsStopped(RuntimeError):
    """The stop file appeared."""


@dataclass
class Watch:
    """How the step reports and how it is stopped."""

    emit: Callable[..., None]
    stopped: Callable[[], bool]
    stages: dict = field(default_factory=lambda: STAGES)

    def check(self) -> None:
        if self.stopped():
            raise ProductsStopped

    def tick(self, stage: str, done: int, of: int) -> None:
        self.check()
        low, high = self.stages[stage]
        share = done / of if of else 1.0
        self.emit("products", stage=stage, done=done, of=of, percent=round(low + (high - low) * share, 1))


def _free_device(xp) -> None:
    gc.collect()
    if xp is not np:
        xp.get_default_memory_pool().free_all_blocks()


def _box_of(rows: np.ndarray, cols: np.ndarray, k: int, extent=None) -> tuple[int, int, int, int]:
    """(top, left, height, width) in pixels of kept cells and, with ``extent``, of a strip's pixels from their first
    row to their last and their first column to their last."""
    boxes = []
    if rows.size:
        boxes.append((int(rows.min()) * k, int(cols.min()) * k, (int(rows.max()) + 1) * k, (int(cols.max()) + 1) * k))
    if extent is not None:
        boxes.append((extent[0], extent[2], extent[1] + 1, extent[3] + 1))
    top, left = min(b[0] for b in boxes), min(b[1] for b in boxes)
    bottom, right = max(b[2] for b in boxes), max(b[3] for b in boxes)
    return top, left, bottom - top, right - left


def pixel_box(cells: CellPixels, strip=None) -> tuple[int, int, int, int]:
    """(top, left, height, width) in pixels of the kept cells and, with a strip, its pixels too."""
    extent = None
    if strip is not None and strip.rows.size:
        extent = (int(strip.rows.min()), int(strip.rows.max()), int(strip.cols.min()), int(strip.cols.max()))
    return _box_of(cells.rows, cells.cols, cells.k, extent)


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


@dataclass
class Tally:
    """What the statistics count, block by block."""

    counts: np.ndarray = field(default_factory=lambda: np.zeros(np.iinfo(np.uint8).max + 1, np.int64))
    depth: float = 0.0
    speed: float = 0.0
    dv: float = 0.0
    strip_pixels: int = 0
    strip_depth: float = 0.0


@dataclass
class Lattice:
    """A run on the lattice while its pixel maps are made a block at a time (W86)."""

    xp: object
    rule: object
    watch: Watch
    reader: CellReader
    strips: object
    """A :class:`wadi2d.products.strip_pixels.StripReader`, or None on a run without a strip."""
    box: tuple[int, int, int, int]
    shape: tuple[int, int]
    """Cells of the grid, (rows, columns)."""
    zmin: np.ndarray
    sills: tuple[np.ndarray, np.ndarray]
    peak: tuple
    """The run's own peaks at the kept cells, in their order: depth, mean depth, speed, depth x speed."""
    strip_peak: dict | None
    maps: int
    blocks: int
    done: int = 0
    shown: int = -1
    """The count of maps last reported: many blocks would say the same one many times."""
    join: object = None
    """The :class:`wadi2d.products.strip_join.StripJoin` of a strip on the continuous surface (W100), or None."""
    join_stack: Stack | None = None
    """The saved maps of the strip cells the squares take as neighbours across the join."""
    strip_zmin: np.ndarray | None = None
    """The strip's cells' lowest ground over the datum."""
    join_record: tuple | None = None
    """The squares' surface at their join corners, map by map, from the last block's squares: (rows, columns, maps)."""

    def _join_ghosts(self, win_r, win_c, keep, zmin, sill_x, sill_y):
        """The replaced squares of a window as neighbours of its squares (W100), with the window's ground and face
        grounds made for them; None and the arrays as given when the window has none."""
        join = self.join
        if join is None:
            return None, zmin, sill_x, sill_y
        rows, cols, cells = join.ghosts_in(win_r, win_c, keep)
        if rows.size == 0:
            return None, zmin, sill_x, sill_y
        lr, lc = rows - win_r[0], cols - win_c[0]
        zmin, sill_x, sill_y = zmin.copy(), sill_x.copy(), sill_y.copy()
        zmin[lr, lc] = self.strip_zmin[cells]
        ghost = np.zeros(keep.shape, bool)
        ghost[lr, lc] = True
        ny, nx = keep.shape
        sill = join.sill[win_r[0] : win_r[1], win_c[0] : win_c[1]]
        # a face between a square and a replaced one: the square's own lowest join ground; between two replaced
        # ones, the higher of their lowest grounds, so the strip's water reads as one body
        for dj, di, faces, at in ((0, -1, sill_x, (0, 0)), (0, 1, sill_x, (0, 1)), (-1, 0, sill_y, (0, 0)), (1, 0, sill_y, (1, 0))):
            nr, nc = lr + dj, lc + di
            ok = (nr >= 0) & (nr < ny) & (nc >= 0) & (nc < nx)
            fr, fc = lr[ok] + at[0], lc[ok] + at[1]  # the face's own cell: west faces are a cell's, north ones too
            fine = (fr < ny) & (fc < nx)
            nr, nc, fr, fc, me = nr[ok][fine], nc[ok][fine], fr[fine], fc[fine], np.flatnonzero(ok)[fine]
            square = keep[nr, nc]
            faces[fr[square], fc[square]] = sill[nr[square], nc[square]]
            other = ghost[nr, nc]
            faces[fr[other], fc[other]] = np.maximum(zmin[nr[other], nc[other]], zmin[lr[me][other], lc[me][other]])
        return (lr, lc, cells), zmin, sill_x, sill_y

    def rect(self, block: Block) -> tuple[int, int, int, int]:
        """Pixel rows ``[p0, p1)`` and columns ``[q0, q1)`` of a block, on the grid's pixel frame."""
        top, left, height, width = self.box
        return (
            top + block.row0 * WINDOW, top + min(block.row1 * WINDOW, height),
            left + block.col0 * WINDOW, left + min(block.col1 * WINDOW, width),
        )  # fmt: skip

    strip_reach: int = 0
    """Cells past a block's own that the strip cells it works reach (W100): their join squares are worked that much
    further out, so the surface the strip takes from them is the whole run's."""

    def reach(self) -> int:
        """Cells a block's squares are worked with round its own: the halo, and the strip's reach on a join."""
        return halo(self.rule) + self.strip_reach

    def cell_rows(self, row0: int, row1: int) -> tuple[int, int]:
        """The run of kept cells that windows' rows ``[row0, row1)`` read: their own and the halo's."""
        top, _left, height, _width = self.box
        k, reach = self.reader.k, self.reach()
        first = (top + row0 * WINDOW) // k - reach
        last = -(-(top + min(row1 * WINDOW, height)) // k) + reach
        a, b = np.searchsorted(self.reader.rows, [first, last])
        return int(a), int(b)

    def tick(self, index: int, share: tuple[float, float]) -> None:
        """Map ``index`` of a block's ``maps + 1``, in the share of the block's time that part of it takes."""
        total = self.maps + 1
        units = (self.done + share[0]) * total + (share[1] - share[0]) * index  # maps done, over all blocks
        shown = int(units / self.blocks + 1e-9)
        if shown == self.shown:
            self.watch.check()
            return
        self.shown = shown
        self.watch.tick("maps", shown, total)

    def squares(self, block: Block, a: int, ground: np.ndarray, stack: Stack | None, share) -> tuple | None:
        """(rows, columns, depth, speed, depth x speed) of the kept cells that reach the block, each (cells, k * k);
        ``ground`` holds the kept cells from ``a`` on. The cells are worked with a halo round them, as a view of the
        time slider is, so their pixels are those of the whole domain."""
        xp, rule, reader = self.xp, self.rule, self.reader
        self.join_record = None
        if stack is None:
            return None
        k, reach = reader.k, self.reach()
        p0, p1, q0, q1 = self.rect(block)
        own_r, own_c = (p0 // k, -(-p1 // k)), (q0 // k, -(-q1 // k))
        win_r = (max(own_r[0] - reach, 0), min(own_r[1] + reach, self.shape[0]))
        win_c = (max(own_c[0] - reach, 0), min(own_c[1] + reach, self.shape[1]))
        b = a + ground.shape[0]
        r, c = reader.rows[a:b], reader.cols[a:b]
        pick = np.flatnonzero((r >= win_r[0]) & (r < win_r[1]) & (c >= win_c[0]) & (c < win_c[1]))
        r, c = r[pick], c[pick]
        own = (r >= own_r[0]) & (r < own_r[1]) & (c >= own_c[0]) & (c < own_c[1])
        if r.size == 0 or (not own.any() and self.join is None):
            return None  # with a join, a block of strip cells alone still needs the squares' surface beside it
        keep = np.zeros((win_r[1] - win_r[0], win_c[1] - win_c[0]), bool)
        keep[r - win_r[0], c - win_c[0]] = True
        cells = CellPixels(r - win_r[0], c - win_c[0], k, reader.pixel, reader.datum, ground[pick])
        window = (slice(*win_r), slice(*win_c))
        ghosts, zmin, sill_x, sill_y = self._join_ghosts(
            win_r, win_c, keep, self.zmin[window], self.sills[0][window], self.sills[1][window]
        )
        order = None if ghosts is None else (ghosts[0], ghosts[1])
        shaped = keep.copy()
        if ghosts is not None:
            shaped[ghosts[0], ghosts[1]] = True
        maxima = PixelMaxima(xp, cells, zmin, sill_x, sill_y, shaped, rule, ghosts=order)
        maxima.tidy = False
        if maxima.resident:  # its ground is on the card: the host's copy goes while the maps run (W93)
            cells.ground = None
        listed = a + pick
        at = stack.at(listed)
        extra, unknown, watched = None, None, None
        if ghosts is not None:  # the strip's water beside the squares, and the squares the strip will read
            extra = self.join_stack.at(ghosts[2])
            unknown = np.concatenate((np.zeros(r.size, np.float32), np.full(ghosts[2].size, np.nan, np.float32)))
            near = self.strip_reach  # the squares a block's strip cells can open onto, each worked with its own halo
            close = (r >= own_r[0] - near) & (r < own_r[1] + near) & (c >= own_c[0] - near) & (c < own_c[1] + near)
            watched = np.flatnonzero(np.isfinite(self.join.sill[r, c]) & close)
            maxima.watch(watched)

        def with_ghosts(values, more):
            return values if more is None else tuple(np.concatenate((v, m)) for v, m in zip(values, more, strict=True))

        for index in range(stack.maps):
            self.tick(index, share)
            more = None if extra is None else self.join_stack.of(index, extra)
            maxima.add_listed(*with_ghosts(stack.of(index, at), more), offsets=unknown)
        depth, mean_depth, speed, hazard = (v[listed] for v in self.peak)
        more = None
        if extra is not None:
            more = tuple(self.strip_peak[name][ghosts[2]] for name in ("depth", "mean_depth", "speed"))
        maxima.add_listed(*with_ghosts((depth, mean_depth, speed), more), moment=False, offsets=unknown)
        maxima.lift_listed(hazard if extra is None else np.concatenate((hazard, self.strip_peak["hazard"][ghosts[2]])))
        found = maxima.result()
        self.join_record = None
        if watched is not None and watched.size:
            self.join_record = (r[watched], c[watched], np.stack(maxima.record))
        del maxima
        _free_device(xp)
        if not own.any():
            return None
        return (r[own], c[own], *(v[own] for v in found), ground[pick][own])

    def _meet(self, maxima, part):
        """Hand the block's strip its join faces with the squares the last squares' block kept the surface of
        (W100); the squares' record, (maps + 1, 10, squares), or None."""
        join, held = self.join, self.join_record
        if join is None or held is None:
            return None
        rows, cols, record = held
        local = np.searchsorted(part.ids, join.face_cell)
        local = np.minimum(local, part.ids.size - 1)
        mine = part.ids[local] == join.face_cell
        width = self.shape[1]
        keys = rows.astype(np.int64) * width + cols
        order = np.argsort(keys)
        found = np.searchsorted(keys[order], join.face_row * width + join.face_col)
        found = np.minimum(found, keys.size - 1)
        known = keys[order][found] == join.face_row * width + join.face_col
        take = np.flatnonzero(mine & known)
        if take.size == 0:
            return None
        cell = local[take]
        square = order[found[take]]
        nodes = self.strips.cell_node[part.ids[cell]]  # each slot's node, as the block's incidences stand
        incs = []
        for k in range(2):
            slot = np.argmax(nodes == join.face_node[take, k][:, None], axis=1)
            incs.append(part.cell_inc[cell, slot])
        corner = join.face_corner[take]
        maxima.meet(cell, incs[0], incs[1], join.face_ground[take], square, corner[:, 0], corner[:, 1])
        return record

    def strip(self, block: Block, part, stack: Stack | None, share):
        """The strip's pixels in the block with their classes and maxima, or None. ``part`` is the block's
        :class:`wadi2d.products.strip_pixels.StripBlock`, read ahead (W93), or None."""
        from wadi2d.products.strip_pixels import BlockStripMaxima
        from wadi2d.strips.pixels import StripPixelResult

        if part is None:
            return None
        xp, rule = self.xp, self.rule
        maxima = BlockStripMaxima(xp, part, rule)
        record = self._meet(maxima, part)
        pixel_ground = part.ground  # kept on the host for the water level raster
        if xp is not np:  # on the card now: the host's copies of its pixels' ground and weights can go (W93)
            part.ground = part.weights = part.cell = None
        at = stack.at(part.ids)
        for index in range(stack.maps):
            self.tick(index * (self.maps + 1) // max(stack.maps, 1), share)
            maxima.join_map = None if record is None else record[index]
            maxima.add(*stack.of(index, at))
        peak = self.strip_peak
        maxima.join_map = None if record is None else record[stack.maps]
        maxima.add(peak["depth"][part.ids], peak["mean_depth"][part.ids], peak["speed"][part.ids], moment=False)
        maxima.lift_dv(peak["hazard"][part.ids])
        depth, speed, dv = maxima.result()
        del maxima
        _free_device(xp)
        p0, p1, q0, q1 = self.rect(block)
        inside = (part.rows >= p0) & (part.rows < p1) & (part.cols >= q0) & (part.cols < q1)
        depth, speed, dv = depth[inside], speed[inside], dv[inside]
        return StripPixelResult(
            part.rows[inside], part.cols[inside], classify(depth, speed, dv, rule), depth, speed, dv,
            None if pixel_ground is None else np.asarray(pixel_ground)[inside],
        )  # fmt: skip


class _Lane:
    """One thread beside the card's work, its jobs taken in the order given (W93): the next block's ground and
    strip pixels read while the card works on this one, the last block's windows written meanwhile. The same inputs
    and the same writes in the same order, so the same rasters; leaving waits for what is in hand."""

    def __init__(self) -> None:
        from concurrent.futures import ThreadPoolExecutor

        self.pool = ThreadPoolExecutor(1)
        self.last = None

    def submit(self, fn, *args):
        self.last = self.pool.submit(fn, *args)
        return self.last

    def wait(self) -> None:
        """Until the last job is done; its error, if any, raised here."""
        if self.last is not None:
            self.last.result()

    def __enter__(self) -> _Lane:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.pool.shutdown(wait=True, cancel_futures=True)


def _write_block(lattice: Lattice, block: Block, squares, strip, hazard, bands, tally: Tally) -> None:
    """The windows of one block into the rasters of record: kept cells, then the strip's pixels over them."""
    rule, k = lattice.rule, lattice.reader.k
    p0, p1, q0, q1 = lattice.rect(block)
    if squares is None:
        none = np.zeros(0, np.int64)
        squares = (none, none, *(np.zeros((0, k * k), np.float32),) * 4)
    rows, cols, depth, speed, dv, ground = squares
    datum = np.float32(lattice.reader.datum)
    level = depth + ground + datum  # the highest water level: the ground plus the highest depth
    strip_level = None
    if strip is not None and strip.ground is not None:
        strip_level = strip.depth + strip.ground + datum
    cells = CellPixels(rows, cols, k, lattice.reader.pixel, lattice.reader.datum, None)
    classes = classify(depth, speed, dv, rule)
    wet = classes > DRY
    on_strip = None if strip is None else strip.classes > DRY
    measures = (
        (depth, None if strip is None else strip.depth),
        (speed, None if strip is None else strip.speed),
        (dv, None if strip is None else strip.dv),
        (level, None if strip is None else strip_level),
    )
    top, left = lattice.box[0], lattice.box[1]
    parts = list(window_parts(cells, (p0, q0, p1 - p0, q1 - q0), strip, WINDOW))

    shown = off_the_map(classes, depth, rule)
    strip_shown = None if strip is None else off_the_map(strip.classes, strip.depth, rule)

    def classes_raster() -> np.ndarray:
        counts = np.zeros_like(tally.counts)
        for part in parts:
            tile = part.paint(shown[part.cells], None if strip is None else strip_shown[part.strip], DRY, np.uint8)
            hazard.write(tile, p0 - top + part.row, q0 - left + part.col)
            counts += np.bincount(tile.ravel(), minlength=counts.size)
        return counts

    def measure_raster(band, values, more) -> None:
        for part in parts:
            marked = np.where(wet[part.cells], values[part.cells], NO_DEPTH)
            dots = None if more is None else np.where(on_strip[part.strip], more[part.strip], NO_DEPTH)
            band.write(part.paint(marked, dots, NO_DEPTH, np.float32), p0 - top + part.row, q0 - left + part.col)

    # the four rasters side by side, each its own file and its windows in the same order (W93)
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(1 + len(bands)) as pool:
        counted = pool.submit(classes_raster)
        written = [
            pool.submit(measure_raster, band, *pair)
            for band, pair in zip(bands, measures, strict=True)
            if band is not None  # depth x speed is written only when asked for (W100)
        ]
        for done in written:
            done.result()
        tally.counts += counted.result()
    tally.depth = max(tally.depth, float(depth.max(initial=0.0)))
    tally.speed = max(tally.speed, float(speed.max(initial=0.0)))
    tally.dv = max(tally.dv, float(dv.max(initial=0.0)))
    if strip is not None:
        tally.strip_pixels += int(strip.rows.size)
        tally.strip_depth = max(tally.strip_depth, float(strip.depth.max(initial=0.0)))


MEASURE_FILES = (DEPTH_FILE, SPEED_FILE, DV_FILE, LEVEL_FILE)
OVERVIEW_MEASURES, OVERVIEW_CLASSES = "average", "mode"
"""How the reduced copies of the rasters of record are made (W100): depth and speed averaged over their wet pixels,
the class the most of them hold."""


def class_overviews(rule) -> str | None:
    return OVERVIEW_CLASSES if rule.overviews else None


def record_writers(stack: ExitStack, folder: Path, profile: dict, rule, tags) -> list:
    """The writers of depth, speed and depth x speed, None for depth x speed unless ``dv_raster`` asks for it (W100:
    the hazard classes hold it); float rasters within ``max_error_m``, with reduced copies unless ``overviews`` is off."""
    floats = float_record(profile, rule.max_error_m)
    resample = OVERVIEW_MEASURES if rule.overviews else None
    writers = []
    for name in MEASURE_FILES:
        if name == DV_FILE and not rule.dv_raster:
            (folder / name).unlink(missing_ok=True)  # a remake leaves no stale one behind
            writers.append(None)
            continue
        writers.append(stack.enter_context(BandWriter(folder / name, floats, np.float32, NO_DEPTH, tags, resample)))
    return writers


def _join_lattice(lattice: Lattice, tables: GridTables, keep: np.ndarray, results: Path, names: list[str]) -> None:
    """The strip's join with the squares on the continuous surface (W100): the replaced squares beside a kept square
    and the saved maps of their strip cells, read once."""
    from wadi2d.products.strip_join import strip_join

    datum = lattice.reader.datum
    join = strip_join(tables, datum)
    if join is None or join.rows.size == 0:
        return
    near = np.zeros(join.rows.size, bool)
    ny, nx = keep.shape
    for dj in (-1, 0, 1):
        for di in (-1, 0, 1):
            r, c = join.rows + dj, join.cols + di
            ok = (r >= 0) & (r < ny) & (c >= 0) & (c < nx)
            near[ok] |= keep[r[ok], c[ok]]
    join.rows, join.cols, join.cells = join.rows[near], join.cols[near], join.cells[near]
    lattice.join = join
    # how far past a block the strip cells it works can open onto a square: its rings of the widest strip cells
    from wadi2d.products.strip_pixels import rings

    strips = lattice.strips
    r0, r1, c0, c1 = strips.box
    widest = float(max(int((r1 - r0).max(initial=0)), int((c1 - c0).max(initial=0))) + 1) * strips.pixel
    lattice.strip_reach = int(np.ceil((rings(lattice.rule) + 1) * widest / tables.grid.dx)) + 1
    lattice.strip_zmin = (np.asarray(tables.strip.mesh.zmin[: tables.strip.mesh.real]) - datum).astype(np.float32)
    lattice.join_stack = read_strip_stack(results, names, np.unique(join.cells))


def window_cells(shape: tuple[int, int], x0: float, y0: float, dx: float, window, margin: int) -> np.ndarray:
    """The lattice cells of ``shape`` that reach ``window`` (xmin, ymin, xmax, ymax, m), and ``margin`` cells more
    round them: what a window of the maps reads (W100)."""
    xmin, ymin, xmax, ymax = window
    r0 = max(int(np.floor((y0 - ymax) / dx)) - margin, 0)
    r1 = min(int(np.ceil((y0 - ymin) / dx)) + margin, shape[0])
    c0 = max(int(np.floor((xmin - x0) / dx)) - margin, 0)
    c1 = min(int(np.ceil((xmax - x0) / dx)) + margin, shape[1])
    inside = np.zeros(shape, bool)
    if r1 > r0 and c1 > c0:
        inside[r0:r1, c0:c1] = True
    return inside


def window_box(box: tuple[int, int, int, int], x0: float, y0: float, pixel: float, window) -> tuple[int, int, int, int] | None:
    """``box`` (top, left, height, width) in pixels from the grid origin, cut to ``window``; None when they miss."""
    xmin, ymin, xmax, ymax = window
    top = max(box[0], int(np.floor((y0 - ymax) / pixel + 1e-9)))
    left = max(box[1], int(np.floor((xmin - x0) / pixel + 1e-9)))
    bottom = min(box[0] + box[2], int(np.ceil((y0 - ymin) / pixel - 1e-9)))
    right = min(box[1] + box[3], int(np.ceil((xmax - x0) / pixel - 1e-9)))
    if bottom <= top or right <= left:
        return None
    return top, left, bottom - top, right - left


def lattice_pixels(
    cfg: RunConfig,
    tables: GridTables,
    crs,
    out: Path,
    folder: Path,
    tags,
    watch: Watch,
    xp,
    squeeze: float = 1.0,
    window: tuple[float, float, float, float] | None = None,
) -> dict | None:
    """The rasters of record of a run on the lattice, its strip's pixels over the cells the strip replaced, made a
    block at a time (W86): every saved map, then the run's own peaks, which do not depend on how often maps were
    saved. Returns the statistics and the rasters' profile, or None when nothing was wet enough to map.
    ``squeeze`` is the share of the device's room the blocks are cut to, under 1 after a try that did not fit.
    ``window`` (xmin, ymin, xmax, ymax) makes the rasters of that window alone, each pixel what the whole run's
    rasters at that pixel size hold there (W100): the cells round it it reads, and the whole run's datum."""
    from wadi2d.products.strip_pixels import StripReader

    rule = cfg.outputs.pixels
    results = out / "results.h5"
    peak = run_maxima(results)
    keep = kept_cells(peak["mean_depth"], rule)
    datum = float(tables.zmin[keep].min()) if keep.any() else 0.0
    if window is not None:
        grid = tables.grid
        keep = keep & window_cells(keep.shape, grid.x0, grid.y0, grid.dx, window, halo(rule) + 1)
    names = frame_names(results)
    watch.tick("ground", 0, 1)
    with ExitStack() as held:
        cache = cache_folder(cfg, out)  # where the DEM's chunk store lies (W84)
        reader = held.enter_context(CellReader(cfg, tables, keep, datum=datum, cache=cache))
        rows, cols, k = reader.rows, reader.cols, reader.k
        strips, strip_peak, extent = None, None, None
        if getattr(tables, "strip", None) is not None:
            strip_peak = strip_run_maxima(results)
        if strip_peak is not None:
            strips = StripReader(cfg, tables, tables.strip, reader.datum, cache)
            held.callback(strips.close)
            extent = strips.extent()
            strips = None if extent is None else strips
        if rows.size == 0 and strips is None:
            return None
        box = _box_of(rows, cols, k, extent)
        if window is not None:
            box = window_box(box, tables.grid.x0, tables.grid.y0, reader.pixel, window)
            if box is None:
                return None
        grid = tables.grid
        x0, y0 = grid.x0 + box[1] * reader.pixel, grid.y0 - box[0] * reader.pixel
        profile = raster_profile(box[2:], reader.pixel, x0, y0, crs)
        # the blocks: bands of windows whose ground is read at once, cut into runs that fit the device
        shape = (-(-box[2] // WINDOW), -(-box[3] // WINDOW))
        square_pixels = square_window_pixels(rows, cols, k, WINDOW, box[0], box[1], shape)
        strip_pixels = np.zeros(shape) if strips is None else strips.window_pixels(WINDOW, box[0], box[1], shape)
        room, pool_cap = device_budget(xp, rule.batch_pixels, squeeze)
        on_card, on_host = (0, 0) if strips is None else (strips.pixel_bytes, strips.host_bytes)
        costs = [  # a block fits the device with its squares, then with its strip, and the host with both
            square_pixels * SQUARE_PIXEL_BYTES,
            strip_pixels * on_card,
            square_pixels * SQUARE_HOST_BYTES + strip_pixels * on_host,
        ]
        bands = [
            (band, plan_blocks(costs, [room, room, HOST_RESULT_BYTES], band))
            for band in plan_bands(square_pixels.sum(axis=1) * BYTES, BAND_GROUND_BYTES)
        ]
        lattice = Lattice(
            xp, rule, watch, reader, strips, box, keep.shape,
            (tables.zmin - reader.datum).astype(np.float32), face_sills(tables, reader.datum),
            tuple(peak[name][rows, cols] for name in ("depth", "mean_depth", "speed", "hazard")),
            strip_peak, len(names), sum(len(blocks) for _band, blocks in bands),
        )  # fmt: skip
        if strips is not None and rule.surface != CELL_FILL:
            _join_lattice(lattice, tables, keep, results, names)
        runs = [lattice.cell_rows(*band) for band, _blocks in bands]
        per_cell = STACK_VALUE_BYTES * max(len(names), 1)
        groups = plan_bands(np.array([(b - a) * per_cell for a, b in runs], float), STACK_BYTES)
        watch.emit(
            "output", kind="pixel_blocks", blocks=lattice.blocks, bands=len(bands), map_reads=len(groups),
            block_mb=round(room / 2**20), kept_pixels=int(rows.size) * k * k, strip_pixels=round(float(strip_pixels.sum())),
        )  # fmt: skip
        watch.check()
        tally = Tally()
        if xp is not np:
            pool = xp.get_default_memory_pool()
            held.callback(pool.set_limit, size=pool.get_limit())
            pool.set_limit(size=int(pool_cap))
        hazard = held.enter_context(BandWriter(folder / HAZARD_FILE, profile, np.uint8, DRY, tags, class_overviews(rule)))
        measures = record_writers(held, folder, profile, rule, tags)
        # beside the card's work: the next block's ground and strip pixels are read, the last block's windows written
        ahead = held.enter_context(_Lane())
        behind = held.enter_context(_Lane())
        for number, (first, last) in enumerate(groups):
            # the saved maps of this group of bands, held once: the squares' kept cells, the strip's cells
            a0, b0 = runs[first][0], runs[last - 1][1]
            jobs = [(n, block) for n in range(first, last) for block in bands[n][1]]
            grounds: dict = {}
            if jobs:  # the first band's ground read while the saved maps are (W93); the next once a band is done
                grounds[jobs[0][0]] = ahead.submit(reader.read, *runs[jobs[0][0]])
            tick = (lambda i, n: watch.tick("ground", i, n)) if number == 0 else (lambda _i, _n: watch.check())
            stack = read_square_stack(results, names, rows, cols, a0, b0, tick) if b0 > a0 else None
            sets, strip_stack = {}, None
            if strips is not None:
                listed = np.zeros(strips.n, bool)
                for _band, blocks in bands[first:last]:
                    for block in blocks:
                        own = strips.cells_in(*lattice.rect(block))
                        if own.any():
                            sets[block] = strips.sets(own, rule)
                            listed |= sets[block][1]
                strip_stack = read_strip_stack(results, names, np.flatnonzero(listed))
            def strip_ahead(j: int, jobs=jobs, sets=sets):
                """Job ``j``'s strip pixels, read on the lane ahead."""
                block = jobs[j][1]
                return ahead.submit(strips.block, *sets[block]) if block in sets else None

            coming = strip_ahead(0) if jobs else None
            for j, (n, block) in enumerate(jobs):
                watch.check()
                part_job = coming
                coming = strip_ahead(j + 1) if j + 1 < len(jobs) else None
                ground = grounds[n].result()
                both = block in sets
                squares = lattice.squares(block, runs[n][0], ground, stack, (0.0, 0.4 if both else 1.0))
                del ground
                if j + 1 == len(jobs) or jobs[j + 1][0] != n:
                    del grounds[n]  # the band's last block: its ground goes, and the next band's is read
                    if j + 1 < len(jobs):
                        grounds[jobs[j + 1][0]] = ahead.submit(reader.read, *runs[jobs[j + 1][0]])
                start = 0.4 if squares is not None else 0.0
                part = None if part_job is None else part_job.result()
                strip = lattice.strip(block, part, strip_stack, (start, 1.0))
                del part, part_job
                behind.wait()  # one block's windows in hand at most
                behind.submit(_write_block, lattice, block, squares, strip, hazard, measures, tally)
                del squares, strip
                lattice.done += 1
            behind.wait()
            grounds.clear()
            del stack, strip_stack, sets
        watch.tick("maps", lattice.maps + 1, lattice.maps + 1)
    km2 = reader.pixel**2 / M2_PER_KM2
    stats = {
        "class_km2": {name: round(float(tally.counts[n + 1]) * km2, 4) for n, name in enumerate(class_names(rule))},
        "maps": len(names),
        "kept_cells": int(rows.size),
        "pixel_m": reader.pixel,
        "surface": rule.surface,
        "limits": rule.hazard_limits,
        "depth_floor_m": rule.depth_floor,
        "depth_max_m": tally.depth,
        "speed_max_ms": tally.speed,
        "dv_max_m2s": tally.dv,
        "origin": [x0, y0],
    }
    if strips is not None:
        stats["strip_pixels"] = tally.strip_pixels
        stats["strip_depth_max_m"] = tally.strip_depth
    return {"stats": stats, "profile": profile}


def mesh_maxima(cfg: RunConfig, tables: GridTables, out: Path, watch: Watch, xp) -> MeshResult:
    """``pixel_maxima`` for a run on a mesh: the same maps through one pass per cell size."""
    rule = cfg.outputs.pixels
    results = out / "results.h5"
    peak = run_maxima(results)
    keep = kept_cells(peak["mean_depth"], rule)
    parts = read_parts(cfg, tables, keep, lambda a, b: watch.tick("ground", a, b), cache_folder(cfg, out))
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
    cfg: RunConfig,
    tables: GridTables,
    crs,
    out: Path,
    watch: Watch,
    backend: str,
    tags: dict | None = None,
    window: tuple[float, float, float, float] | None = None,
    folder: Path | None = None,
) -> dict:
    """The whole step; returns the statistics. ``ProductsStopped`` leaves nothing half-written behind.

    The rasters of record and the run's map layers always; the class polygons and the depth drawing when
    ``outputs.smooth.enabled`` asks for them, and later through :func:`wadi2d.products.runner.draw` when it did not.
    With ``window`` (xmin, ymin, xmax, ymax) the rasters of that window alone go into ``folder``, and nothing else
    (W100: the 0.5 m detail of a drawn window, the maps of record being coarser)."""
    from wadi2d.products.smooth import LAYERS_FILE, crs_text, make_drawings, run_layers

    on_mesh = getattr(tables.grid, "quad", False)
    if window is not None and on_mesh:
        raise ValueError("a window of the maps is made on the uniform grid and the aligned cells, not on a mesh of several sizes")
    xp = array_module(backend)
    _free_device(xp)
    folder = out / PIXEL_DIR if folder is None else Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    def record(xp, squeeze: float = 1.0):
        """The rasters of record made with ``xp``: their statistics and profile, or the count of the run's saved
        maps when nothing was wet enough to map."""
        if not on_mesh:
            written = lattice_pixels(cfg, tables, crs, out, folder, tags, watch, xp, squeeze, window=window)
            return written if written is not None else len(frame_names(out / "results.h5"))
        found = mesh_maxima(cfg, tables, out, watch, xp)
        if found.kept == 0:
            return found.maps
        watch.tick("rasters", 0, 1)
        files = {"hazard": HAZARD_FILE, "depth": DEPTH_FILE, "speed": SPEED_FILE, "dv": DV_FILE, "nodata": NO_DEPTH}
        return write_mesh_pixels(cfg, tables, crs, found, folder, tags, files)

    # on the lattice a try that does not fit the card is made again in smaller blocks before the CPU is asked
    for squeeze in SQUEEZES if xp is not np and not on_mesh else SQUEEZES[:1]:
        try:
            written = record(xp, squeeze)
            break
        except Exception as error:
            if xp is np or type(error).__name__ != "OutOfMemoryError":
                raise
            _free_device(xp)
    else:
        watch.emit("warn", message="The pixel maps did not fit on the GPU, so they run on the CPU, more slowly.")
        written = record(np)
    _free_device(xp)
    if not isinstance(written, dict):
        (folder / STATS_FILE).write_text(json.dumps({"class_km2": {}, "maps": written}), encoding="utf-8")
        return {"class_km2": {}}
    watch.tick("rasters", 0, 1)
    stats, profile = written["stats"], written["profile"]
    if window is not None:
        stats["window"] = list(window)
        (folder / STATS_FILE).write_text(json.dumps(stats, indent=1), encoding="utf-8")
        watch.tick("rasters", 1, 1)
        return stats
    layers = run_layers(cfg, tables, crs)
    if cfg.outputs.smooth.enabled:
        del written
        _free_device(xp)
        # from the files, as a drawing asked for later is made, so the two cannot differ; on a mesh this is new: the
        # picture there was drawn from every kept pixel's depth, now from the depth of record, dry under the floor
        classes, depth, _profile = read_record(folder)
        stats["smooth"] = make_drawings(cfg, classes, depth, profile, folder, crs, watch, xp, layers)
    else:
        write_geopackage(folder / LAYERS_FILE, layers, crs_text(crs))
        watch.tick("rasters", 1, 1)
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
