"""A long dry valley for the sleeping-tile tests and W90's timing: squares, or squares with a strip on the axis.

The bed falls along x and rises either side of the axis, so water put in at the head runs down a narrow course and
the hills stay dry. With ``strip`` a band of the axis's squares is masked out of the tiles and carried by a strip
of the same squares, its ghosts the squares either side: the hybrid as a run with aligned cells has it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wadi2d.config.schema import Numerics, Tables
from wadi2d.grid import TileGrid
from wadi2d.solver.backend import BoundaryCells
from wadi2d.solver.model import Model
from wadi2d.strips.geometry import MeshGeometry
from wadi2d.strips.hybrid import Hybrid, ghosts_for, make_hybrid
from wadi2d.strips.tables import Pixels, build_poly_tables
from wadi2d.tables import ArrayBed, build_tables

DX, K = 20.0, 2
SLOPE, SIDE_SLOPE, MANNING = 0.01, 0.02, 0.035
HALF_WIDTH = 1
"""The strip is the axis row and this many rows either side."""
STATE = ("h", "d", "u", "v", "mx", "my", "qx", "qy", "res")
STRIP_STATE = ("h", "d", "u", "m", "q", "res")


@dataclass
class Valley:
    grid: TileGrid
    model: Model
    hybrid: Hybrid | None
    axis: int
    """The grid row of the valley's axis."""
    strip_cells: tuple[np.ndarray, np.ndarray] | None
    """Grid (j, i) of the strip's cells, in cell order."""

    def advance(self, t: float) -> None:
        (self.hybrid or self.model).advance(t)

    def head(self, discharge: float, column: int = 8) -> np.ndarray:
        """A source rate grid, m/s, that puts ``discharge`` into two squares beside the axis at ``column``."""
        rate = np.zeros(self.grid.shape)
        rows = [self.axis - HALF_WIDTH - 1, self.axis + HALF_WIDTH + 1]
        rate[rows, column] = discharge / (len(rows) * DX * DX)
        return rate

    def open_end(self) -> None:
        """A free outflow on the last active column."""
        g = self.grid
        cols = np.nonzero(g.mask.any(axis=0))[0]
        j = np.nonzero(g.mask[:, cols[-1]])[0]
        cells = np.array([self.model.cell_state_index(int(a), int(cols[-1])) for a in j], np.int32)
        zero = np.zeros(cells.size, np.int32)
        f = np.zeros(cells.size, np.float32)
        self.model.set_boundary(BoundaryCells(cells, zero, np.ones(cells.size, np.int32), f, f.copy()))

    def awake(self) -> int:
        return int(self.model.backend.nact)

    def fields(self) -> dict[str, np.ndarray]:
        """Every state array, own cells only; and the strip's."""
        out = {name: self.model.field(name) for name in STATE}
        if self.hybrid is not None:
            n = self.hybrid.nreal
            for name in STRIP_STATE:
                a = np.asarray(self.hybrid.strip_host(name))
                out[f"strip_{name}"] = a[:n].copy() if name in ("h", "d", "res") else a.copy()
        return out


def bed(tg: TileGrid, axis: int) -> np.ndarray:
    """Pixels of the padded grid: a fall along x, a rise either side of the axis row."""
    ny, nx = tg.shape
    p = DX / K
    x = (np.arange(nx * K) + 0.5) * p
    y = (np.arange(ny * K) + 0.5) * p
    xx, yy = np.meshgrid(x, y)
    return (200.0 - SLOPE * xx + SIDE_SLOPE * np.abs(yy - (axis + 0.5) * DX)).astype(np.float32).astype(np.float64)


def squares_of(tg: TileGrid, patch: np.ndarray) -> tuple[MeshGeometry, np.ndarray, np.ndarray]:
    """The cells of ``patch`` (padded grid) as a polygon mesh of squares, and their (j, i) in cell order."""
    jj, ii = np.nonzero(patch)
    corner: dict[tuple[int, int], int] = {}
    xs, ys, rings = [], [], []
    for j, i in zip(jj.tolist(), ii.tolist(), strict=True):
        ring = []
        for cj, ci in ((j + 1, i), (j + 1, i + 1), (j, i + 1), (j, i)):  # counter-clockwise from the south-west
            if (cj, ci) not in corner:
                corner[(cj, ci)] = len(xs)
                xs.append(tg.x0 + ci * tg.dx)
                ys.append(tg.y0 - cj * tg.dx)
            ring.append(corner[(cj, ci)])
        rings.append(np.array(ring))
    return MeshGeometry.from_rings(np.array(xs), np.array(ys), rings), jj, ii


def valley(
    tiles_y: int = 2, tiles_x: int = 8, strip: bool = True, backend: str = "cpu", sleeping: bool = True,
    num: Numerics | None = None, strip_ends: tuple[int, int] = (4, 12), dry_strips: tuple[int, ...] = (),
) -> Valley:  # fmt: skip
    """``tiles_y`` x ``tiles_x`` tiles of 32 cells. ``sleeping`` off steps every tile at every step: the reference.
    ``strip_ends`` are the columns the strip stops short of the west and east edges; ``dry_strips`` the rows, from
    the axis, of more bands of aligned cells on the hillsides, which no water reaches: streams that stay dry."""
    ny, nx = tiles_y * 32 - 2, tiles_x * 32 - 2
    mask = np.ones((ny, nx), bool)
    whole = TileGrid.from_mask(mask, 0.0, 0.0, DX)
    axis = whole.shape[0] // 2
    z = bed(whole, axis)
    patch = np.zeros(whole.shape, bool)
    if strip:
        for row in (0, *dry_strips):
            rows = slice(axis + row - HALF_WIDTH, axis + row + HALF_WIDTH + 1)
            patch[rows, 1 + strip_ends[0] : whole.shape[1] - 1 - strip_ends[1]] = True
    tg = TileGrid.from_mask(mask & ~patch[1 : 1 + ny, 1 : 1 + nx], 0.0, 0.0, DX)
    assert tg.shape == whole.shape
    tables = build_tables(tg, ArrayBed(z, DX / K), Tables(), MANNING)
    model = Model(tables, num or Numerics(), backend)
    model.stepper.adaptive_active = sleeping
    hybrid, cells = None, None
    if strip:
        geo, jj, ii = squares_of(tg, patch)
        ghosts = ghosts_for(geo, model, tables)
        mesh, _kept = build_poly_tables(geo, Pixels(z, tg.x0, tg.y0, DX / K), Tables(), DX, MANNING, ghosts=ghosts)
        hybrid = make_hybrid(model, mesh)
        cells = (jj, ii)
    model.set_depth(np.zeros(tg.shape))
    return Valley(tg, model, hybrid, axis, cells)


# ---- the comparison the sleeping-tile tests make (W90)
def pair(**kwargs) -> tuple[Valley, Valley]:
    """The same valley twice: tiles that sleep, and every tile stepped at every step."""
    return valley(sleeping=True, **kwargs), valley(sleeping=False, **kwargs)


def both(a: Valley, b: Valley, act) -> None:
    for v in (a, b):
        act(v)


def assert_same(a: Valley, b: Valley, where: str = "") -> None:
    """Every state array, the strip's too, the step count, the time and the time step: equal to the last bit."""
    sa, sb = a.model.stepper, b.model.stepper
    assert (sa.nsteps, sa.t, sa.dt) == (sb.nsteps, sb.t, sb.dt), where
    fa, fb = a.fields(), b.fields()
    for name in fa:
        differ = int(np.sum(fa[name] != fb[name]))
        assert differ == 0, f"{where}: {name} differs in {differ} entries, by up to {np.abs(fa[name] - fb[name]).max():.3e}"


def run_same(a: Valley, b: Valley, times, floor: int | None = None) -> list[int]:
    """Advance both through ``times``, equal at each; the sleeping run's awake tiles at each time."""
    awake = []
    for t in times:
        both(a, b, lambda v, t=t: v.advance(t))
        assert_same(a, b, f"t = {t:g} s")
        awake.append(a.awake())
    assert b.awake() == b.grid.ntiles - 1  # the reference never sleeps
    if floor is not None:
        assert min(awake) <= floor, awake
    return awake
