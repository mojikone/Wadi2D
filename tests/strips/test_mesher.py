"""The strip mesher (W45, stage 4): a corridor of aligned cells inside the lattice, its breakline rows on the lines,
every interface face a lattice edge; and the first race, W3's channel with a corridor along its axis."""

from __future__ import annotations

import numpy as np
import pytest
import shapely

from tests.solver.test_poly import BANK, DX, SIDE, T_END, B, K, Q, S, channel, normal_depth, run_channel
from wadi2d.config.schema import Numerics, Tables
from wadi2d.solver.backend import BoundaryCells
from wadi2d.solver.model import Model
from wadi2d.solver.state import level_of
from wadi2d.strips.hybrid import HybridCpu, ghosts_for
from wadi2d.strips.mesher import (
    Corridor,
    breakline_faces,
    build_strip_mesh,
    corridor_cells,
    corridor_nodes,
    fold_free_pieces,
    folds,
)
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


def test_a_corridor_past_the_active_cells_is_refused_in_words() -> None:
    grid = _grid()
    x1 = grid.x0 + grid.mask.shape[1] * DX  # the east edge of the lattice
    past = shapely.LineString([(x1 - 300.0, grid.y0 - 500.0), (x1 + 100.0, grid.y0 - 500.0)])
    with pytest.raises(ValueError, match="corridor past reaches outside the active cells near"):
        build_strip_mesh(grid, [Corridor("past", past, OFFSETS, DX)])


def test_the_fold_free_pieces_of_a_hairpin_are_its_two_legs_and_a_straight_corridor_is_whole() -> None:
    straight = axis_corridor(0.0)
    whole, is_whole = fold_free_pieces(straight)
    assert is_whole and len(whole) == 1 and whole[0].shape[0] == round(2 * HALF / DX) + 1
    hairpin = shapely.LineString([(0.0, 0.0), (600.0, 0.0), (600.0, 20.0), (0.0, 20.0)])
    assert fold_free_pieces(Corridor("hairpin", hairpin, OFFSETS, DX, {})) == ([], False)  # its legs overlap each other
    square = shapely.LineString([(0.0, 0.0), (600.0, 0.0), (600.0, 400.0), (0.0, 400.0)])
    pieces, is_whole = fold_free_pieces(Corridor("corners", square, OFFSETS, DX, {}))
    assert not is_whole and len(pieces) == 3  # two legs and the cross, cut clear of the two corners
    for k, piece in enumerate(pieces):
        length = np.hypot(*np.diff(piece, axis=0).T).sum()
        assert (400.0 < length < 600.0) if k != 1 else (200.0 < length < 400.0), (k, length)
        assert folds(*corridor_nodes(Corridor("leg", shapely.LineString(piece), OFFSETS, DX, {}))) == []
    wall = shapely.box(250.0, -100.0, 350.0, 100.0)  # something to keep out of, across the straight corridor
    straight_pieces, is_whole = fold_free_pieces(Corridor("kept", shapely.LineString([(0.0, 0.0), (600.0, 0.0)]), OFFSETS, DX, {}), keep_out=wall)
    assert not is_whole and len(straight_pieces) == 2
    assert all(not shapely.LineString(p).intersects(wall) for p in straight_pieces)


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


def run_strip_channel(theta: float, substeps: int = 1) -> tuple[float, float, int]:
    """Depth at the axis over normal depth with the corridor, the largest skew in degrees, and the steps."""
    tg, tables, sc, tc, strip = strip_case(theta)
    _tg, _t, _sc, _tc, z = _bed(theta)
    model = Model(tables, Numerics(), "cpu")
    ghosts = ghosts_for(strip.geometry, model, tables)
    mesh, _kept = build_poly_tables(strip.geometry, Pixels(z, tg.x0, tg.y0, DX / K), Tables(), DX, 0.03, ghosts=ghosts)
    hybrid = HybridCpu(model, mesh, substeps)
    yn = normal_depth(B, BANK, Q)
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


def test_gap_slivers_are_joined_into_convex_quads_and_nothing_wider() -> None:
    from wadi2d.strips.mesher import MERGE_DN, merge_slivers

    # a thin sliver pair: two triangles on a 20 m edge with apexes 1 m either side of it, and a fat pair to keep
    xy = np.array([[0.0, 0.0], [20.0, 0.0], [10.0, 1.0], [10.0, -1.0], [40.0, 0.0], [60.0, 0.0], [50.0, 15.0], [50.0, -15.0]])
    thin = [np.array([0, 1, 2]), np.array([0, 3, 1])]
    fat = [np.array([4, 5, 6]), np.array([4, 7, 5])]
    out = merge_slivers(xy, thin + fat, MERGE_DN * 20.0)
    assert len(out) == 3 and sorted(r.size for r in out) == [3, 3, 4]
    quad = next(r for r in out if r.size == 4)
    assert set(quad.tolist()) == {0, 1, 2, 3}
    p = xy[quad]
    d = np.roll(p, -1, axis=0) - p
    assert (d[:, 0] * np.roll(d, -1, axis=0)[:, 1] - d[:, 1] * np.roll(d, -1, axis=0)[:, 0] > 0).all()  # counter-clockwise, convex


def _close_gap_faces(mesh, limit: float) -> int:
    geo = mesh.geometry
    _area, cx, cy = geo.areas_centroids()
    _length, nfx, nfy, _xf, _yf = geo.faces(cx, cy)
    inner = geo.face_cell[:, 1] >= 0
    L, R = geo.face_cell[inner, 0], geo.face_cell[inner, 1]
    gap = (mesh.corridor[L] < 0) & (mesh.corridor[R] < 0)
    dn = (cx[R] - cx[L]) * nfx[inner] + (cy[R] - cy[L]) * nfy[inner]
    return int((dn[gap] < limit).sum())


def test_joining_slivers_removes_most_of_the_close_gap_faces_and_leaves_quads_at_most() -> None:
    from wadi2d.strips.mesher import MERGE_DN

    grid = _grid()
    raw = build_strip_mesh(grid, [axis_corridor(30.0)], merge=0.0)
    joined = build_strip_mesh(grid, [axis_corridor(30.0)])
    before, after = _close_gap_faces(raw, MERGE_DN * DX), _close_gap_faces(joined, MERGE_DN * DX)
    assert before > 0 and after <= 0.25 * before, (before, after)
    assert np.diff(joined.geometry.ring_start).max() <= 4  # triangles and quads only
    assert (joined.corridor < 0).sum() < (raw.corridor < 0).sum()


def test_the_strip_sub_cycling_inside_the_squares_step_keeps_the_channel_and_saves_the_squares_steps() -> None:
    """Eight strip steps may share one step of the squares: the squares step at their own rule, the corridor at its
    10 m rows' rule inside it; the depth stays the same to half a point and the squares take fewer steps."""
    together, _skew, steps_together = run_strip_channel(45.0, 1)
    nested, _skew2, steps_nested = run_strip_channel(45.0, 8)
    yn_rule = 0.03
    assert abs(together - 1.0) < yn_rule and abs(nested - 1.0) < yn_rule, (together, nested)
    assert nested == pytest.approx(together, abs=0.005), (nested, together)
    assert steps_nested < 0.8 * steps_together, (steps_nested, steps_together)


def test_a_ragged_corridor_keeps_its_inner_side_to_what_a_bend_allows() -> None:
    """On a wide floor a ragged corridor would fold at any bend; its inner side drops cells to the bend's radius
    instead and the corridor stays whole (Block 2's biggest wadi lost its confluence reach to this, 2026-11-07)."""
    theta = np.linspace(0.0, np.pi / 2, 31)
    arc = np.column_stack((300.0 + 100.0 * np.sin(theta), 100.0 - 100.0 * np.cos(theta)))  # a 90 degree bend, radius 100 m
    centre = shapely.LineString(np.vstack(([[0.0, 0.0]], arc, [[400.0, 400.0]])))
    far = shapely.LineString([(-50.0, 250.0), (150.0, 250.0), (150.0, 450.0)]).buffer(0.1).exterior  # the inner (left) edge, far away
    outer = centre.parallel_offset(250.0, "right") if hasattr(centre, "parallel_offset") else centre.offset_curve(-250.0)
    c = Corridor("bend", centre, np.zeros(0), 20.0, {}, edges={"left": far, "right": outer}, cell=30.0)
    pieces, whole = fold_free_pieces(c, smooth=0)
    assert whole, "the inner side thins at the bend instead of folding"
    x, y, valid = corridor_cells(c, smooth=0)
    from wadi2d.strips.mesher import _frame, ragged_counts

    centre_pts, _n = _frame(c, 0)
    left, right = ragged_counts(centre_pts, c.edges, 30.0, 12, 20.0)
    assert left.min() <= 3 and left[0] >= 6  # the straight approach fills the wide floor; the bend cuts the inner side
    assert folds(x, y, valid) == []


def test_a_bend_tighter_than_a_cell_leaves_the_inner_side_empty_and_two_cells_sharing_ground_are_a_fold() -> None:
    """Block 2's t284, 2026-11-07: a 73 degree turn in one 30 m station on a one-cell floor. The bend cap floored at
    one cell let the inner cells of two neighbouring stations overlap by 2.5 m2, which no fold test saw (overlaps
    were tested between non-neighbours only), and the corridor's outline gained a vertex off the nodes, refused by
    the mesher. The inner side of a bend tighter than a cell holds no cell, the outer side carries the corridor on;
    and two cells sharing ground are a fold, neighbours or not."""
    from scipy.spatial import cKDTree

    from wadi2d.strips.mesher import _frame, _quad, bend_caps, corridor_polygon

    headings = np.radians([0.0, 0.0, 0.0, 10.0, 30.0, 110.0, 140.0, 150.0, 150.0, 150.0, 150.0, 150.0])  # 80 degrees in one station
    steps = 30.0 * np.column_stack((np.cos(headings), np.sin(headings)))
    centre = shapely.LineString(np.vstack(([[0.0, 0.0]], np.cumsum(steps, axis=0))))
    floor = centre.buffer(30.0).exterior  # one cell either side, everywhere
    c = Corridor("hairpin", centre, np.zeros(0), 30.0, {}, edges={"left": floor, "right": floor}, cell=30.0)
    centre_pts, normal = _frame(c, 0)
    cap_left, cap_right = bend_caps(centre_pts, 30.0, 30.0)
    assert cap_left.min() == 0 and cap_right.min() >= 1, "the 80 degree turn's inner side, 23 m to the meeting cross lines, holds no 30 m cell"
    # the fold test itself, on the rows the floored cap used to give: one cell each side at every station
    off = np.array([-30.0, 0.0, 30.0])
    x = centre_pts[:, 0][:, None] + off[None, :] * normal[:, 0][:, None]
    y = centre_pts[:, 1][:, None] + off[None, :] * normal[:, 1][:, None]
    quads = {(i, j): shapely.Polygon(_quad(x, y, i, j)) for i in range(x.shape[0] - 1) for j in range(2)}
    sharing = [(a, b) for a in quads for b in quads if a < b and quads[a].intersection(quads[b]).area > 1e-6]
    assert any(abs(a[0] - b[0]) == 1 and a[1] == b[1] == 1 for a, b in sharing), sharing  # inner neighbours among them
    bad = set(folds(x, y))
    assert all(a in bad and b in bad for a, b in sharing), (sharing, bad)
    # the corridor as built: no two cells share ground, the outline's vertices are nodes, the outer side carries it on
    x, y, valid = corridor_cells(c, smooth=0)
    cells = [tuple(int(v) for v in ij) for ij in np.argwhere(valid)]
    built = {ij: shapely.Polygon(_quad(x, y, *ij)) for ij in cells}
    assert not [(a, b) for a in cells for b in cells if a < b and built[a].intersection(built[b]).area > 1e-6]
    assert folds(x, y, valid) == []
    nodes = np.column_stack((x.ravel(), y.ravel()))
    d, _ = cKDTree(nodes).query(shapely.get_coordinates(corridor_polygon(x, y, valid)))
    assert d.max() < 1e-6, d.max()
    assert valid.any(axis=1).all() and fold_free_pieces(c, smooth=0)[1], "the outer side carries the corridor through the bend"
    assert (~valid[:, -1]).sum() >= 3, "the inner row is empty through the bend"


def test_a_corridor_pinched_to_a_node_between_two_bends_is_cut_there() -> None:
    """A left bend then a right bend, each tighter than a cell, six stations apart on a one-cell floor: the cells of
    one station lie right of the centre, the next station's left, and they share a node and no face. Five Block 2
    corridors did this (2026-11-07): their outline was two polygons touching at a point, which the layer writer
    dropped and the map refused. A pinch is a fold: the mesher refuses it by name and the fold-free pieces end
    either side of it."""
    from wadi2d.strips.mesher import corridor_polygon

    headings = np.radians([0.0] * 5 + [80.0] * 6 + [0.0] * 5)  # +80 degrees at station 5, -80 at station 11
    steps = 30.0 * np.column_stack((np.cos(headings), np.sin(headings)))
    centre = shapely.LineString(np.vstack(([[0.0, 0.0]], np.cumsum(steps, axis=0))))
    floor = centre.buffer(30.0).exterior
    c = Corridor("ess", centre, np.zeros(0), 30.0, {}, edges={"left": floor, "right": floor}, cell=30.0)
    x, y, valid = corridor_cells(c, smooth=0)
    pinched = np.nonzero(~(valid[:-1] & valid[1:]).any(axis=1))[0]
    assert pinched.size == 1, pinched  # the geometry pinches once, between the bends
    assert corridor_polygon(x, y, valid).geom_type == "MultiPolygon"  # what the pinch does to the outline
    bad = folds(x, y, valid)
    assert {i for i, _j in bad} >= {int(pinched[0]), int(pinched[0]) + 1}, bad
    pieces, whole = fold_free_pieces(c, smooth=0)
    assert not whole and len(pieces) == 2, (whole, len(pieces))
    for piece in pieces:
        leg = Corridor("leg", shapely.LineString(piece), np.zeros(0), 30.0, {}, edges=c.edges, cell=30.0)
        xl, yl, vl = corridor_cells(leg, smooth=0)
        assert folds(xl, yl, vl) == [] and corridor_polygon(xl, yl, vl).geom_type == "Polygon"


def test_cross_lines_meeting_inside_a_corridor_count_as_a_fold() -> None:
    """At a sharp bend the cross lines of two stations can meet inside the corridor while every cell keeps a
    positive area: the cells between them overlap, and the union of the cells gained vertices off the nodes (found
    on Block 2, 2026-11-07). The fold test now sees it, and the fold-free pieces cut it out."""
    bend = shapely.LineString([(0.0, 0.0), (300.0, 0.0), (330.0, 30.0), (360.0, 0.0), (660.0, 0.0)])
    wide = Corridor("kink", bend, np.array([-90.0, -60.0, -30.0, 0.0, 30.0, 60.0, 90.0]), 30.0)
    x, y = corridor_nodes(wide, smooth=0)
    bad = folds(x, y)
    assert bad, "the kink's cross lines meet within 90 m of the centre"
    pieces, whole = fold_free_pieces(wide, smooth=0)
    assert not whole and len(pieces) == 2
    straight = Corridor("straight", shapely.LineString([(0.0, 0.0), (660.0, 0.0)]), wide.offsets, 30.0)
    assert folds(*corridor_nodes(straight, smooth=0)) == []


def test_the_rows_between_two_snapped_rows_share_their_width_and_the_centre_need_not_be_a_row() -> None:
    """A wadi's inner rows follow both banks in the proportion of their offsets; a snapped row finds its line out
    from the station's centre, so a corridor of one cell across, with no row at offset zero, still snaps."""
    centre = shapely.LineString([(0.0, 0.0), (600.0, 0.0)])
    north = shapely.LineString([(-50.0, 6.0), (650.0, 6.0)])
    south = shapely.LineString([(-50.0, -12.0), (650.0, -12.0)])
    even = Corridor("even", centre, np.array([-20.0, -10.0, 0.0, 10.0, 20.0]), 20.0, {3: north, 1: south})
    x, y = corridor_nodes(even, smooth=0)
    assert np.allclose(y[:, 3], 6.0) and np.allclose(y[:, 1], -12.0)
    assert np.allclose(y[:, 2], -3.0)  # midway between the banks, off the centre line
    assert np.allclose(y[:, 4], 16.0) and np.allclose(y[:, 0], -22.0)  # the outer rows carried with their banks
    assert folds(x, y) == []
    odd = Corridor("odd", centre, np.array([-15.0, -5.0, 5.0, 15.0]), 20.0, {2: north, 1: south})
    x, y = corridor_nodes(odd, smooth=0)
    assert np.allclose(y[:, 2], 6.0) and np.allclose(y[:, 1], -12.0)
    assert np.allclose(y[:, 3], 16.0) and np.allclose(y[:, 0], -22.0)
    assert folds(x, y) == []
