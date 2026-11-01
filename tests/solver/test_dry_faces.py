"""A dry or closed neighbour face must not be advected as a real zero velocity: the 45-degree channel it deepens."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.optimize import brentq

from wadi2d.config.schema import Numerics, Tables
from wadi2d.grid import TileGrid
from wadi2d.solver.backend import BoundaryCells
from wadi2d.solver.model import Model
from wadi2d.tables import ArrayBed, build_tables
from wadi2d.tables.builder import hbar_at_level


def channel_error(mirror: bool, offset: float = 5.0) -> float:
    """Depth error against Manning, in per cent, of a channel 3 cells wide at 45 degrees with vertical walls."""
    dx, k, slope, n, b, q, side = 20.0, 20, 0.002, 0.03, 60.0, 60.0, 128
    tg = TileGrid.from_mask(np.ones((side, side), bool), 0.0, 0.0, dx)
    ny, nx = tg.shape
    p = dx / k
    ca = sa = np.sqrt(0.5)
    x = (np.arange(nx * k + 2) - 1 + 0.5) * p - 0.5 * nx * dx
    y = (np.arange(ny * k + 2) - 1 + 0.5) * p - 0.5 * ny * dx
    grid_x, grid_y = np.meshgrid(x, y)
    along = grid_x * ca + grid_y * sa
    across = -grid_x * sa + grid_y * ca - offset
    z = -along * slope + 5.0 * (np.abs(across) >= b / 2)
    normal = brentq(lambda y_: (b * y_) * (b * y_ / (b + 2 * y_)) ** (2 / 3) * slope**0.5 / n - q, 0.01, 20)
    tables = build_tables(tg, ArrayBed(z, p, 1, 1), Tables(), n)
    model = Model(tables, Numerics(mirror_dry_faces=mirror), "cpu")
    xc = (np.arange(nx) + 0.5) * dx - 0.5 * nx * dx
    yc = (np.arange(ny) + 0.5) * dx - 0.5 * ny * dx
    cell_x, cell_y = np.meshgrid(xc, yc)
    s_c = cell_x * ca + cell_y * sa
    t_c = -cell_x * sa + cell_y * ca - offset
    level = -s_c * slope + normal
    h0 = hbar_at_level(level, tables.zmin, tg.from_tiles(tables.hc), tg.from_tiles(tables.dtab))
    h0 = np.where(np.abs(t_c) < b / 2 + 2 * dx, h0, 0.0)
    model.set_depth(h0)
    reach = 0.45 * side * dx
    source = (s_c > -reach) & (s_c < -reach + 120) & (np.abs(t_c) < b / 2 + dx)
    rate = np.zeros(tg.shape)
    rate[source] = q / (source.sum() * dx * dx)
    model.set_source(rate)
    out = (s_c > reach - 120) & (s_c < reach) & (np.abs(t_c) < b + 3 * dx)
    cells = np.array([model.cell_state_index(int(j), int(i)) for j, i in zip(*np.nonzero(out), strict=True)], np.int32)
    count = cells.size
    fixed = np.maximum((level - tables.zmin)[out], 0).astype(np.float32)
    model.set_boundary(BoundaryCells(cells, np.zeros(count, np.int32), np.zeros(count, np.int32), fixed, h0[out].astype(np.float32)))
    model.advance(4000.0)
    middle = (np.abs(s_c) < 0.15 * side * dx) & (np.abs(t_c) < 0.71 * dx)
    return float(np.mean((tables.zmin + model.field("d") + s_c * slope)[middle]) / normal - 1.0) * 100.0


@pytest.mark.parametrize(("mirror", "low", "high"), [(False, 5.0, 12.0), (True, -3.0, 3.0)])
def test_the_45_degree_channel(mirror: bool, low: float, high: float) -> None:
    assert low < channel_error(mirror) < high
