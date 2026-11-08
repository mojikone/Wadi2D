"""The centre generator (W46, his rules of 2026-11-08): a breakline is a chain of faces with 4-sided cells either
side, rows repeat outward to the bank, small cells merge by losing a centre, the transition is polygons of at most
eight faces and no triangle, every join face is a lattice edge, the main stream keeps its rows through a junction
and the tributary stops short; and the floor rule that finds the bank: the scarp inside a step, the rise above the
bed, the slope cap."""

from __future__ import annotations

import numpy as np
import pytest
import shapely

from wadi2d.breaklines.window import Window
from wadi2d.grid.tiles import TileGrid
from wadi2d.strips.centres import SHORT_FACE, TURN_MAX, CentreSettings, Line, build_centre_mesh, stations_of, turns_of
from wadi2d.strips.floor import FloorRule, floor_distances, floor_of_line

DX = 30.0
PIXEL = 5.0
X0, Y0 = 400_000.0, 2_700_000.0
NX, NY = 60, 40  # 1,800 m by 1,200 m
YC = Y0 - 0.5 * NY * DX
YL = YC + 7.5
"""The test line's y: a quarter cell off the lattice's lines and centres, so its cells never coincide with squares."""


def wadi_window(bank_at: float = 70.0, scarp: float = 2.0, fan_slope: float = 0.0) -> Window:
    """A straight wadi along x: a flat bed, a scarp of ``scarp`` m over 10 m at ``bank_at`` from the axis, a plain
    climbing 1 % beyond; with ``fan_slope`` instead, no scarp and the ground climbing uniformly from the axis."""
    ny, nx = NY * int(DX / PIXEL), NX * int(DX / PIXEL)
    rows, cols = np.indices((ny, nx))
    x = X0 + (cols + 0.5) * PIXEL
    y = Y0 - (rows + 0.5) * PIXEL
    d = np.abs(y - YC)
    if fan_slope > 0.0:
        across = fan_slope * d
    else:
        across = scarp * np.clip((d - bank_at) / 10.0, 0.0, 1.0) + 0.01 * np.maximum(d - bank_at - 10.0, 0.0)
    z = 100.0 + 0.001 * (x - X0) + across
    return Window(z, np.ones_like(z, bool), X0, Y0, PIXEL, DX, "")


def grid() -> TileGrid:
    return TileGrid.from_mask(np.ones((NY, NX), bool), X0, Y0, DX)


def settings(**kw) -> CentreSettings:
    return CentreSettings(dx=DX, **kw)


def axis(x_from: float = 157.5, x_to: float = 1657.5) -> Line:
    """A line along x a quarter cell off the lattice's lines and centres, so its cells never coincide with squares."""
    return Line("wadi", np.array([[X0 + x_from, YL], [X0 + x_to, YL]]), rank=50.0)


def ring_sizes(mesh) -> np.ndarray:
    return np.diff(mesh.geometry.ring_start)


def shortest_face(mesh) -> float:
    """The shortest face of the mesh, m: the Voronoi diagram's near-degenerate edges must be gone (Faydh's leak)."""
    geo = mesh.geometry
    a, b = geo.face_node[:, 0], geo.face_node[:, 1]
    return float(np.hypot(geo.x[b] - geo.x[a], geo.y[b] - geo.y[a]).min())


def lattice_edge(mesh, grid_, f: int) -> bool:
    a, b = mesh.geometry.face_node[f]
    xa, ya, xb, yb = mesh.geometry.x[a], mesh.geometry.y[a], mesh.geometry.x[b], mesh.geometry.y[b]
    on = lambda v, o: abs((v - o) / DX - round((v - o) / DX)) < 1e-6  # noqa: E731
    return on(xa, grid_.x0) and on(xb, grid_.x0) and on(ya, grid_.y0) and on(yb, grid_.y0) and abs(np.hypot(xb - xa, yb - ya) - DX) < 1e-6


def test_the_floor_rule_finds_the_scarp_and_falls_back_on_the_rise_on_a_fan() -> None:
    rule = FloorRule(rise_m=2.0, scarp_m=1.0, scarp_run_m=10.0, slope_cap=0.05, slope_run_m=40.0, reach_m=300.0, offset_m=DX)
    pts = np.column_stack((X0 + np.arange(300.0, 1500.0, 60.0), np.full(20, YC)))
    normals = np.tile([0.0, 1.0], (pts.shape[0], 1))
    left = floor_distances(wadi_window(70.0), pts, normals, rule, 1.0)
    right = floor_distances(wadi_window(70.0), pts, normals, rule, -1.0)
    assert np.all(np.abs(left - 70.0) <= 5.0) and np.all(np.abs(right - 70.0) <= 5.0), (left, right)
    # a 1.5 m scarp, under the 2 m rise, still ends the bed where it stands
    low = floor_distances(wadi_window(70.0, scarp=1.5), pts, normals, rule, 1.0)
    assert np.all(np.abs(low - 70.0) <= 5.0), low
    # a fan at 3 %: no scarp, no 5 % slope, the rise of 2 m at 67 m decides
    fan = floor_distances(wadi_window(fan_slope=0.03), pts, normals, rule, 1.0)
    assert np.all(np.abs(fan - 2.0 / 0.03) <= 5.0), fan
    # a plain climbing 0.5 %: nothing within 300 m, no bank
    plain = floor_distances(wadi_window(fan_slope=0.005), pts, normals, rule, 1.0)
    assert np.all(np.isnan(plain)), plain
    # the first cell is bed whatever the ground does: a wall at 10 m reads as the offset
    wall = floor_distances(wadi_window(10.0), pts, normals, rule, 1.0)
    assert np.all(wall == DX), wall


def test_a_straight_breakline_is_a_chain_of_faces_with_4_sided_cells_and_lattice_edges_at_the_join() -> None:
    g = grid()
    s = settings()
    line = axis()
    pts, _n, _w = stations_of(line, s)
    floors = [floor_of_line(wadi_window(70.0), pts, FloorRule(offset_m=DX))]
    mesh = build_centre_mesh(g, [line], floors, s)
    geo = mesh.geometry
    assert geo.check() == []
    sizes = ring_sizes(mesh)
    assert sizes.min() >= 4 and sizes.max() <= s.max_faces, (sizes.min(), sizes.max())
    assert shortest_face(mesh) >= SHORT_FACE * DX - 1e-6, shortest_face(mesh)
    # the line: one face per segment between two stations, the chain the polyline itself, between two 4-sided cells
    edges = mesh.breakline_edges["wadi:0"]
    assert len(edges) == pts.shape[0] - 1, (len(edges), pts.shape[0])
    for a, b in edges:
        assert abs(geo.y[a] - YL) < 1e-6 and abs(geo.y[b] - YL) < 1e-6
    pairs = np.nonzero((mesh.corridor == 0) & (mesh.row == 0))[0]
    assert pairs.size == 2 * (pts.shape[0] - 1)
    assert (sizes[pairs] == 4).sum() >= pairs.size - 4 and sizes[pairs].max() <= 5  # 4-sided along the line; its two ends meet the squares
    # two cells each side: the pair and one row, the bank at 70 m rounding to two cells
    assert set(np.unique(mesh.row[mesh.corridor == 0]).tolist()) == {0, 1}
    # areas: nothing under the minimum, the line's cells a square each on a straight reach
    area, cx, _cy = geo.areas_centroids()
    assert area.min() >= s.min_area_fraction * DX * DX
    on_line = (mesh.corridor == 0) & (cx > X0 + 157.5 + DX) & (cx < X0 + 1657.5 - DX)  # the end cells reach half a cell past the line
    assert np.allclose(area[on_line & (mesh.row == 0)], DX * DX, rtol=0.02)  # the cells on the line are squares
    assert np.all((area[on_line] > 0.8 * DX * DX) & (area[on_line] < 1.2 * DX * DX))  # the row beyond, 4-sided, meets the band's cells
    # every join face is a lattice edge, and the squares it replaces are what the cells cover
    boundary = np.nonzero(geo.face_cell[:, 1] < 0)[0]
    assert boundary.size and all(lattice_edge(mesh, g, f) for f in boundary)
    assert abs(area.sum() - mesh.masked[0].size * DX * DX) < 1e-6 * area.sum()
    # the band: polygons near the line, and exact squares wherever no relaxed centre is a neighbour
    from scipy.spatial import cKDTree

    from wadi2d.strips.centres import RELAX

    band = np.nonzero(mesh.corridor < 0)[0]
    outer = np.unique(geo.face_cell[boundary, 0])  # the cells on the join: exact squares, so the faces to the tiles are the lattice's
    assert outer.size and np.allclose(area[outer], DX * DX) and np.all(sizes[outer] == 4)
    _a, cxx, cyy = geo.areas_centroids()
    d, _k = cKDTree(np.column_stack((cxx[mesh.corridor == 0], cyy[mesh.corridor == 0]))).query(np.column_stack((cxx[band], cyy[band])))
    assert np.all(d[np.isin(band, outer)] > RELAX * DX)  # nothing on the join moved
    assert (sizes[band] > 4).any(), "the transition is polygons"


def test_a_bend_keeps_the_chain_whole_and_merges_its_small_inner_cells_into_polygons() -> None:
    g = grid()
    s = settings()
    theta = np.linspace(0.0, np.pi / 2, 31)
    xc, yc, r = X0 + 600.0, Y0 - 900.0, 60.0 * 2  # a 120 m radius, four cells
    arc = np.column_stack((xc + r * np.sin(theta), yc + r * (1 - np.cos(theta))))
    line = Line("bend", np.vstack(([[xc - 300.0, yc]], arc, [[xc + r, yc + r + 300.0]])), rank=20.0)
    pts, _n, _w = stations_of(line, s)
    wide = np.full(pts.shape[0], 150.0)  # five cells each side, the inner rows squeezed by the bend
    mesh = build_centre_mesh(g, [line], [(wide, wide)], s)
    geo = mesh.geometry
    assert geo.check() == []
    area, _cx, _cy = geo.areas_centroids()
    sizes = ring_sizes(mesh)
    assert area.min() >= s.min_area_fraction * DX * DX, area.min()
    assert 4 <= sizes.min() and sizes.max() <= s.max_faces, (sizes.min(), sizes.max())
    assert shortest_face(mesh) >= SHORT_FACE * DX - 1e-6, shortest_face(mesh)
    assert len(mesh.breakline_edges["bend:0"]) == pts.shape[0] - 1  # the chain is whole through the bend
    pairs = (mesh.corridor == 0) & (mesh.row == 0)
    assert pairs.sum() == 2 * (pts.shape[0] - 1)
    # the chain is the polyline itself: every face on the line has both ends on it, no jog at a bend (his circle)
    polyline = shapely.LineString(pts)
    for a, b in mesh.breakline_edges["bend:0"]:  # to a centimetre: four nearly cocircular centres place a vertex to millimetres
        assert polyline.distance(shapely.Point(geo.x[a], geo.y[a])) < 1e-2 and polyline.distance(shapely.Point(geo.x[b], geo.y[b])) < 1e-2
    inner = (mesh.corridor == 0) & (mesh.row >= 1)
    assert (sizes[inner] > 4).any(), "the inner rows merged into polygons somewhere on the bend"
    assert all(lattice_edge(mesh, g, f) for f in np.nonzero(geo.face_cell[:, 1] < 0)[0])


def test_the_main_stream_keeps_its_rows_through_a_junction_and_the_tributary_stops_short() -> None:
    g = grid()
    s = settings()
    main = axis()
    trib = Line("trib", np.array([[X0 + 900.0, YL - 500.0], [X0 + 900.0, YL]]), rank=5.0)
    pts_m, _n, _w = stations_of(main, s)
    pts_t, _n, _w = stations_of(trib, s)
    three = lambda n: (np.full(n, 95.0), np.full(n, 95.0))  # noqa: E731  three cells each side
    mesh = build_centre_mesh(g, [trib, main], [three(pts_t.shape[0]), three(pts_m.shape[0])], s)
    geo = mesh.geometry
    assert geo.check() == []
    assert len(mesh.breakline_edges["wadi:0"]) == pts_m.shape[0] - 1, "the main's chain runs whole through the junction"
    area, cx, cy = geo.areas_centroids()
    sizes = ring_sizes(mesh)
    assert sizes.max() <= s.max_faces and area.min() >= s.min_area_fraction * DX * DX
    assert shortest_face(mesh) >= SHORT_FACE * DX - 1e-6, shortest_face(mesh)
    main_cells = mesh.corridor == 1
    trib_cells = mesh.corridor == 0
    assert trib_cells.any()
    # the tributary's cells stay clear of the main's rows: no tributary centroid within the main's three rows (95 m)
    assert np.all(np.abs(cy[trib_cells] - YL) > 3 * DX - 1e-6)
    # and its chain ends short of the main's outer row by about a cell
    top = cy[trib_cells & (mesh.row == 0)].max()
    assert YL - 5 * DX <= top <= YL - 3 * DX, (top - YL) / DX
    assert any("trib" in n and "stations given up" in n for n in mesh.notes), mesh.notes
    assert main_cells.sum() >= 6 * (pts_m.shape[0] - 1)  # three rows each side along its whole length
    assert all(lattice_edge(mesh, g, f) for f in np.nonzero(geo.face_cell[:, 1] < 0)[0])


def test_a_hard_line_outranks_a_stream_and_its_faces_lie_on_it() -> None:
    g = grid()
    s = settings()
    wadi = axis()
    road = Line("road", np.array([[X0 + 900.0, YC - 400.0], [X0 + 900.0, YC + 400.0]]), rank=np.inf, hard=True)
    pts_w, _n, _w = stations_of(wadi, s)
    pts_r, _n, _w = stations_of(road, s)
    two = lambda n: (np.full(n, 65.0), np.full(n, 65.0))  # noqa: E731
    mesh = build_centre_mesh(g, [wadi, road], [two(pts_w.shape[0]), None], s)
    geo = mesh.geometry
    assert geo.check() == []
    assert len(mesh.breakline_edges["road:0"]) == pts_r.shape[0] - 1, "the road's chain is whole, the wadi gave way"
    for a, b in mesh.breakline_edges["road:0"]:
        assert abs(geo.x[a] - (X0 + 900.0)) < 1e-6 and abs(geo.x[b] - (X0 + 900.0)) < 1e-6
    assert len(mesh.breakline_edges["wadi:0"]) < pts_w.shape[0]  # the wadi's chain is cut at the road
    assert any("wadi" in n and "given up" in n for n in mesh.notes), mesh.notes


def test_a_guide_line_is_smoothed_at_a_corner_and_a_hard_line_is_reported() -> None:
    s = settings()
    corner = np.array([[X0 + 300.0, YC], [X0 + 900.0, YC], [X0 + 900.0, YC + 600.0]])
    pts, _n, notes = stations_of(Line("guide", corner, 10.0), s)
    assert not notes and np.abs(turns_of(pts)).max() <= TURN_MAX + 1e-9
    _pts, _n, notes = stations_of(Line("dyke", corner, np.inf, hard=True), s)
    assert len(notes) == 1 and "turns 90 degrees" in notes[0], notes


def run_centre_channel(theta: float, floor_m: float = 70.0, substeps: int = 1) -> tuple[float, float, int, int]:
    """W3's channel through cells from centres: depth at the axis over normal depth, the largest skew, the steps,
    and the strip's cell count. The same harness as the ring corridor's (tests.strips.test_mesher)."""
    from tests.solver.test_poly import BANK, DX as CDX, SIDE, T_END, B, K, Q, S, channel, normal_depth_wide
    from tests.strips.test_mesher import HALF, _bed
    from wadi2d.config.schema import Numerics, Tables
    from wadi2d.solver.backend import BoundaryCells
    from wadi2d.solver.model import Model
    from wadi2d.solver.state import level_of
    from wadi2d.strips.hybrid import HybridCpu, ghosts_for
    from wadi2d.strips.tables import Pixels, build_poly_tables
    from wadi2d.tables.builder import hbar_at_level

    th = np.radians(theta)
    ca, sa = np.cos(th), np.sin(th)
    xm, ym = 0.5 * SIDE * CDX, -0.5 * SIDE * CDX
    tg_full, _tables_full, _sc, _tc = channel(theta)
    line = Line("axis", np.array([[xm - HALF * ca, ym - HALF * sa], [xm + HALF * ca, ym + HALF * sa]]), rank=50.0)
    s = CentreSettings(dx=CDX)
    pts, _n, _w = stations_of(line, s)
    strip = build_centre_mesh(tg_full, [line], [(np.full(pts.shape[0], floor_m), np.full(pts.shape[0], floor_m))], s)
    jj, ii = strip.masked
    mask = np.ones((SIDE, SIDE), bool)
    mask[jj - 1, ii - 1] = False
    tg, tables, sc, tc = channel(theta, mask)
    _tg, _t, _sc, _tc, z = _bed(theta)
    model = Model(tables, Numerics(), "cpu")
    ghosts = ghosts_for(strip.geometry, model, tables)
    mesh, _kept = build_poly_tables(strip.geometry, Pixels(z, tg.x0, tg.y0, CDX / K), Tables(), CDX, 0.03, ghosts=ghosts)
    hybrid = HybridCpu(model, mesh, substeps)
    yn = normal_depth_wide(B, BANK, Q)
    hc, dtab = tg.from_tiles(tables.hc), tg.from_tiles(tables.dtab)
    level = 100.0 - sc * S + yn
    wet = (np.abs(tc) < B / 2 + BANK * yn + 2 * CDX) & tg.mask
    hb = np.where(wet, hbar_at_level(level, tables.zmin, hc, dtab), 0.0)
    model.set_depth(hb)
    n = hybrid.nreal
    s_cell = (mesh.cx[:n] - xm) * ca + (mesh.cy[:n] - ym) * sa
    t_cell = -(mesh.cx[:n] - xm) * sa + (mesh.cy[:n] - ym) * ca
    strip_level = 100.0 - s_cell * S + yn
    strip_wet = np.abs(t_cell) < B / 2 + BANK * yn + 2 * CDX
    hybrid.set_strip_depth(np.where(strip_wet, hybrid.strip_hbar_at_level(strip_level), 0.0))
    lim = 0.45 * SIDE * CDX
    up = (sc > -lim) & (sc < -lim + 6 * CDX) & (np.abs(tc) < B / 2 + CDX) & tg.mask
    model.set_source(np.where(up, Q / (up.sum() * CDX * CDX), 0.0))
    down = (sc > lim - 6 * CDX) & (sc < lim) & (np.abs(tc) < B + 3 * CDX) & tg.mask
    dj, di = np.nonzero(down)
    d0 = level_of(hb[down], hc[down], dtab[down])
    held = np.array([model.cell_state_index(int(j), int(i)) for j, i in zip(dj, di, strict=True)], np.int32)
    zero = np.zeros(held.size, np.int32)
    model.set_boundary(BoundaryCells(held, zero, zero.copy(), d0.astype(np.float32), hb[down].astype(np.float32)))
    hybrid.advance(T_END)
    middle = (np.abs(s_cell) < 0.15 * SIDE * CDX) & (np.abs(t_cell) < 0.51 * CDX)  # the pair cells either side of the axis
    depth = float(np.mean((mesh.zmin[:n] + hybrid.state.d[:n] + s_cell * S - 100.0)[middle]))
    return depth / yn, float(mesh.skew_degrees().max()), model.stepper.nsteps, n


@pytest.mark.parametrize("theta", [0.0, 45.0])
def test_the_channel_through_cells_from_centres_holds_the_rule(theta: float) -> None:
    """W3's rule, 3 % of the normal depth at the axis, on the centre generator's cells: the physics gate before any
    race on real ground."""
    ratio, skew, steps, n = run_centre_channel(theta)
    assert ratio == pytest.approx(1.0, abs=0.03), (ratio, skew, steps, n)


def test_the_strip_ends_clear_of_the_squares_kept_for_a_boundary() -> None:
    """Faydh's outlet, 2026-11-08: the centre mesh covered the squares of the outflow boundary, whose faces on the
    domain's edge are walls, and ponded 23 m deep. The squares a boundary line touches stay squares and the strip
    ends BAND cells before them."""
    from wadi2d.strips.centres import BAND

    g = grid()
    s = settings()
    line = axis()
    pts, _n, _w = stations_of(line, s)
    two = (np.full(pts.shape[0], 65.0), np.full(pts.shape[0], 65.0))
    keep = np.zeros(g.shape, bool)
    keep[:, g.shape[1] - 8 : g.shape[1] - 6] = True  # a boundary two squares wide near the east edge, across the line
    mesh = build_centre_mesh(g, [line], [two], s, keep_out=keep)
    masked = set(zip(mesh.masked[0].tolist(), mesh.masked[1].tolist(), strict=True))
    assert not any((j, i) in masked for j, i in zip(*np.nonzero(keep), strict=True)), "a kept square was replaced"
    _area, cx, _cy = mesh.geometry.areas_centroids()
    edge = g.x0 + (g.shape[1] - 8) * DX
    assert cx[mesh.corridor == 0].max() < edge - BAND * DX + DX, "the line's cells end BAND cells before the kept squares"
    assert len(mesh.breakline_edges["wadi:0"]) < pts.shape[0]
    assert all(lattice_edge(mesh, g, f) for f in np.nonzero(mesh.geometry.face_cell[:, 1] < 0)[0])


def test_a_line_ends_at_the_domains_edge_and_a_line_wholly_outside_is_refused_in_words() -> None:
    mask = np.ones((NY, NX), bool)
    mask[:, NX // 2 :] = False  # the east half inactive
    g = TileGrid.from_mask(mask, X0, Y0, DX)
    s = settings()
    line = axis()
    pts, _n, _w = stations_of(line, s)
    two = (np.full(pts.shape[0], 65.0), np.full(pts.shape[0], 65.0))
    mesh = build_centre_mesh(g, [line], [two], s)
    _area, cx, _cy = mesh.geometry.areas_centroids()
    edge = X0 + (NX // 2) * DX  # the mask's east half starts here; the grid itself pads a cell west
    assert cx[mesh.corridor == 0].max() < edge and len(mesh.breakline_edges["wadi:0"]) < pts.shape[0]
    assert any("wadi" in n and "domain's edge" in n for n in mesh.notes), mesh.notes
    # the join: a boundary face with an active square beyond it is that square's lattice edge; one against the
    # inactive ground is a wall, cut along a lattice line, whatever its length
    geo = mesh.geometry
    _a, cxx, cyy = geo.areas_centroids()
    _len, nfx, nfy, xf, yf = geo.faces(cxx, cyy)
    for f in np.nonzero(geo.face_cell[:, 1] < 0)[0]:
        px, py = xf[f] + 0.5 * DX * nfx[f], yf[f] + 0.5 * DX * nfy[f]
        j, i = int(np.floor((g.y0 - py) / DX)), int(np.floor((px - g.x0) / DX))
        beyond_active = 0 <= j < g.shape[0] and 0 <= i < g.shape[1] and bool(g.mask[j, i])
        a, b = geo.face_node[f]
        on_x = abs((geo.x[a] - g.x0) / DX - round((geo.x[a] - g.x0) / DX)) < 1e-6 and abs(geo.x[a] - geo.x[b]) < 1e-6
        on_y = abs((geo.y[a] - g.y0) / DX - round((geo.y[a] - g.y0) / DX)) < 1e-6 and abs(geo.y[a] - geo.y[b]) < 1e-6
        assert lattice_edge(mesh, g, f) if beyond_active else (on_x or on_y), f
    east = Line("east", np.array([[edge + 300.0, YC], [edge + 1200.0, YC]]), rank=5.0)
    pts_e, _n, _w = stations_of(east, s)
    with pytest.raises(ValueError, match="no line gave a centre"):
        build_centre_mesh(g, [east], [(np.full(pts_e.shape[0], 65.0), np.full(pts_e.shape[0], 65.0))], s)
