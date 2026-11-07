"""The strip mesher (W45, stage 4): a corridor of aligned cells inside the lattice, its breakline rows on the lines,
every interface face a lattice edge; and the first race, W3's channel with a corridor along its axis."""

from __future__ import annotations

import numpy as np
import pytest
import shapely

from tests.solver.test_poly import BANK, DX, SIDE, T_END, B, K, Q, S, channel, normal_depth_wide, run_channel
from wadi2d.config.schema import Numerics, Tables
from wadi2d.solver.backend import BoundaryCells
from wadi2d.solver.model import Model
from wadi2d.solver.state import level_of
from wadi2d.strips.hybrid import HybridCpu, ghosts_for
from wadi2d.strips.mesher import Corridor, breakline_faces, build_strip_mesh, corridor_nodes, folds
from wadi2d.strips.tables import Pixels, build_poly_tables
from wadi2d.tables.builder import hbar_at_level

OFFSETS = np.arange(-50.0, 50.1, 10.0)
"""Ten rows of 10 m across the channel: the toes at +-30 m carry the breaklines."""
TOE = int(np.argmin(np.abs(OFFSETS + B / 2))), int(np.argmin(np.abs(OFFSETS - B / 2)))
HALF = 0.3 * SIDE * DX
"""The corridor runs this far either side of the channel's middle; the inflow and the outlet stay on tiles."""


def axis_corridor(theta: float, name: str = "axis") -> Corridor:
    th = np.radians(theta)
    ca, sa = np.cos(th), np.sin(th)
    xm, ym = 0.5 * SIDE * DX, -0.5 * SIDE * DX
    centre = shapely.LineString([(xm - HALF * ca, ym - HALF * sa), (xm + HALF * ca, ym + HALF * sa)])
    toes = {}
    for j in TOE:
        off = OFFSETS[j]
        nx, ny = -sa, ca  # the left normal of the direction of travel
        toes[j] = shapely.LineString(
            [(xm - 2 * HALF * ca + off * nx, ym - 2 * HALF * sa + off * ny), (xm + 2 * HALF * ca + off * nx, ym + 2 * HALF * sa + off * ny)]
        )
    return Corridor(name, centre, OFFSETS, DX, toes)


def test_a_straight_corridor_has_its_rows_on_the_offsets_and_no_fold() -> None:
    c = axis_corridor(30.0)
    x, y = corridor_nodes(c)
    assert x.shape == (round(2 * HALF / DX) + 1, OFFSETS.size)
    assert folds(x, y) == []
    for j in TOE:
        line = c.snap[j]
        assert max(line.distance(shapely.Point(p)) for p in zip(x[:, j], y[:, j], strict=True)) < 1e-6


def test_a_corridor_too_bent_for_its_width_is_refused_by_name() -> None:
    bend = shapely.LineString([(0.0, 0.0), (200.0, 0.0), (200.0, 20.0), (0.0, 20.0)])
    with pytest.raises(ValueError, match="corridor hairpin folds at stations"):
        build_strip_mesh(_grid(), [Corridor("hairpin", bend, OFFSETS, DX)])


def _grid():
    tg, _tables, _sc, _tc = channel(0.0)
    return tg


def strip_case(theta: float):
    tg_full, _tables_full, sc, tc = channel(theta)
    strip = build_strip_mesh(tg_full, [axis_corridor(theta)])
    jj, ii = strip.masked
    mask = np.ones((SIDE, SIDE), bool)
    mask[jj - 1, ii - 1] = False  # the full grid pads one cell on the north and west
    tg, tables, sc, tc = channel(theta, mask)
    assert tg.shape == tg_full.shape and tg.x0 == tg_full.x0
    return tg, tables, sc, tc, strip


def test_every_interface_face_is_a_lattice_edge_with_a_tile_cell_across() -> None:
    _tg, tables, _sc, _tc, strip = strip_case(45.0)
    geo = strip.geometry
    assert geo.check() == []
    model = Model(tables, Numerics(), "cpu")
    ghosts = ghosts_for(geo, model, tables)
    boundary = geo.face_cell[:, 1] < 0
    opened = ghosts.face_slot >= 0
    assert opened.sum() == boundary.sum()  # every boundary face opens onto an active tile cell: none is a wall
    area, cx, cy = geo.areas_centroids()
    _length, nfx, nfy, _xf, _yf = geo.faces(cx, cy)
    axis_aligned = (np.abs(nfx) > 0.999) | (np.abs(nfy) > 0.999)
    assert axis_aligned[boundary].all()
    assert (strip.corridor >= 0).sum() == (OFFSETS.size - 1) * round(2 * HALF / DX)
    assert (strip.corridor < 0).sum() > 100  # gap triangles round the corridor
    assert area.min() > 0.0
    faces = breakline_faces(strip)
    assert sorted(faces) == ["axis:2", "axis:8"] and all(v.size == round(2 * HALF / DX) for v in faces.values())


def run_strip_channel(theta: float) -> tuple[float, float, int]:
    """Depth at the axis over normal depth with the corridor, the largest skew in degrees, and the steps."""
    tg, tables, sc, tc, strip = strip_case(theta)
    _tg, _t, _sc, _tc, z = _bed(theta)
    model = Model(tables, Numerics(), "cpu")
    ghosts = ghosts_for(strip.geometry, model, tables)
    mesh, _kept = build_poly_tables(strip.geometry, Pixels(z, tg.x0, tg.y0, DX / K), Tables(), DX, 0.03, ghosts=ghosts)
    hybrid = HybridCpu(model, mesh)
    yn = normal_depth_wide(B, BANK, Q)
    hc, dtab = tg.from_tiles(tables.hc), tg.from_tiles(tables.dtab)
    level = 100.0 - sc * S + yn
    wet = (np.abs(tc) < B / 2 + BANK * yn + 2 * DX) & tg.mask
    hb = np.where(wet, hbar_at_level(level, tables.zmin, hc, dtab), 0.0)
    model.set_depth(hb)
    n = hybrid.nreal
    th = np.radians(theta)
    xm, ym = 0.5 * SIDE * DX, -0.5 * SIDE * DX
    s_cell = (mesh.cx[:n] - xm) * np.cos(th) + (mesh.cy[:n] - ym) * np.sin(th)
    t_cell = -(mesh.cx[:n] - xm) * np.sin(th) + (mesh.cy[:n] - ym) * np.cos(th)
    strip_level = 100.0 - s_cell * S + yn
    strip_wet = np.abs(t_cell) < B / 2 + BANK * yn + 2 * DX
    hybrid.set_strip_depth(np.where(strip_wet, hybrid.strip_hbar_at_level(strip_level), 0.0))
    lim = 0.45 * SIDE * DX
    up = (sc > -lim) & (sc < -lim + 6 * DX) & (np.abs(tc) < B / 2 + DX) & tg.mask
    model.set_source(np.where(up, Q / (up.sum() * DX * DX), 0.0))
    down = (sc > lim - 6 * DX) & (sc < lim) & (np.abs(tc) < B + 3 * DX) & tg.mask
    dj, di = np.nonzero(down)
    d0 = level_of(hb[down], hc[down], dtab[down])
    held = np.array([model.cell_state_index(int(j), int(i)) for j, i in zip(dj, di, strict=True)], np.int32)
    zero = np.zeros(held.size, np.int32)
    model.set_boundary(BoundaryCells(held, zero, zero.copy(), d0.astype(np.float32), hb[down].astype(np.float32)))
    hybrid.advance(T_END)
    # the depth at the axis over the corridor's middle: the row cells straddling the centre line
    middle = (np.abs(s_cell) < 0.15 * SIDE * DX) & (np.abs(t_cell) < 0.51 * 10.0)
    depth = float(np.mean((mesh.zmin[:n] + hybrid.state.d[:n] + s_cell * S - 100.0)[middle]))
    return depth / yn, float(mesh.skew_degrees().max()), model.stepper.nsteps


def _bed(theta: float):
    from tests.strips.test_hybrid import _bed as bed

    return bed(theta)


@pytest.mark.parametrize("theta", [0.0, 45.0])
def test_the_channel_through_an_aligned_corridor_holds_the_rule(theta: float) -> None:
    ratio, skew, steps = run_strip_channel(theta)
    assert ratio == pytest.approx(1.0, abs=0.03), (ratio, skew, steps)


def test_the_race_at_45_degrees_the_corridor_against_the_staircase() -> None:
    corridor, skew, steps = run_strip_channel(45.0)
    tiles, _ = run_channel(45.0, "tiles")
    # the record, not a rule: the corridor's error against the tiles' +2.5 %
    assert abs(corridor - 1.0) < abs(tiles - 1.0) + 0.005, (corridor, tiles, skew, steps)
