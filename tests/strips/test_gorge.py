"""Rows across a narrow channel (W52): where a deep channel is narrower than the pair of cells on its line, the pair
is cut into narrower 4-sided rows between the walls and one cell beyond each wall; the line stays a chain of faces,
no triangle appears, the strip's outline and area do not change, and a mesh with no gorge (or the setting off) comes
back exactly as it was."""

from __future__ import annotations

import numpy as np
import pytest

from tests.strips.test_centres import DX, X0, YL, axis, grid, ring_sizes, settings
from wadi2d.config.schema import Strips
from wadi2d.strips.centres import build_centre_mesh, stations_of
from wadi2d.strips.gorge import GorgeRule, split_gorge_rows

PIXEL = 0.5


def gorge_ground(bed_half: float = 9.0, wall_run: float = 2.0, wall_h: float = 8.0, x_from: float = -1e9, x_to: float = 1e9):
    """A gorge along the test line: a flat bed, walls rising ``wall_h`` over ``wall_run``, a plain at 2 % beyond;
    between ``x_from`` and ``x_to`` (from the grid's west edge) only, flat ground elsewhere."""

    def ground(xy: np.ndarray) -> np.ndarray:
        xy = np.asarray(xy, np.float64).reshape(-1, 2)
        d = np.abs(xy[:, 1] - YL)
        across = np.clip((d - bed_half) / wall_run, 0.0, 1.0) * wall_h + 0.02 * np.maximum(d - bed_half - wall_run, 0.0)
        inside = (xy[:, 0] >= X0 + x_from) & (xy[:, 0] <= X0 + x_to)
        return 100.0 - 0.001 * (xy[:, 0] - X0) + np.where(inside, across, 0.0)

    return ground


def pair_mesh():
    s = settings()
    line = axis()
    pts, _n, _w = stations_of(line, s)
    narrow = np.full(pts.shape[0], DX)  # the floor at one cell: the pair alone on the line
    return build_centre_mesh(grid(), [line], [(narrow, narrow)], s), pts


def outline(mesh) -> set[tuple[float, float, float, float]]:
    geo = mesh.geometry
    out = set()
    for f in np.nonzero(geo.face_cell[:, 1] < 0)[0]:
        a, b = geo.face_node[f]
        p, q = (round(geo.x[a], 6), round(geo.y[a], 6)), (round(geo.x[b], 6), round(geo.y[b], 6))
        out.add((*min(p, q), *max(p, q)))
    return out


def widths_across(mesh, x: float) -> list[float]:
    """The cells of the strip a north-south line at ``x`` crosses, by their extent in y, south to north."""
    geo = mesh.geometry
    found = []
    for c in range(geo.ncells):
        r = geo.ring(c)
        xs, ys = geo.x[r], geo.y[r]
        if xs.min() < x < xs.max() and mesh.corridor[c] >= 0:
            found.append((ys.min(), ys.max()))
    return [hi - lo for lo, hi in sorted(found)]


def test_the_pair_is_cut_into_rows_between_the_walls() -> None:
    mesh, _pts = pair_mesh()
    rule = GorgeRule(rows=4, wall_m=3.0, cell_min_m=2.0, pixel=PIXEL)
    cut = split_gorge_rows(mesh, gorge_ground(), rule)
    geo = cut.geometry
    assert geo.check() == []
    sizes = ring_sizes(cut)
    assert sizes.min() >= 4, "no triangle"
    area0, area1 = mesh.geometry.areas_centroids()[0], geo.areas_centroids()[0]
    assert abs(area1.sum() - area0.sum()) < 1e-6 * area0.sum()
    assert outline(cut) == outline(mesh), "the strip's outline and the join to the squares are as they were"
    # the line is still a chain of faces
    faces = {(int(min(a, b)), int(max(a, b))) for a, b in geo.face_node}
    assert set(cut.breakline_edges["wadi:0"]) <= faces
    # in the reach: two rows each side between the line and the wall, then the cell beyond the wall
    rows_ = cut.gorge
    assert (rows_ == 1).sum() == (rows_ == 2).sum() == (rows_ == -1).sum() > 0
    assert np.all(sizes[rows_ > 0] == 4), "every row cell has four sides"
    wall = 9.0 + 2.0 * 3.0 / 8.0  # where the ground first stands 3 m over the bed
    w = widths_across(cut, X0 + 900.0)
    assert len(w) == 6, w
    assert np.allclose(w[1:5], wall / 2, atol=PIXEL), w
    assert min(w[0], w[5]) > DX - wall - PIXEL, w  # the rest of the pair's cell, out to where the pair reached
    assert cut.corridor.size == geo.ncells and cut.row.size == geo.ncells


@pytest.mark.parametrize("rows, expect", [(2, 1), (6, 3), (12, 3)])
def test_the_rows_never_go_under_the_floor_on_their_width(rows: int, expect: int) -> None:
    mesh, _pts = pair_mesh()
    cut = split_gorge_rows(mesh, gorge_ground(bed_half=6.0), GorgeRule(rows=rows, wall_m=3.0, cell_min_m=2.0, pixel=PIXEL))
    wall = 6.0 + 2.0 * 3.0 / 8.0  # 6.75 m: three rows of 2.25 m at most
    assert int(cut.gorge.max()) == expect
    w = widths_across(cut, X0 + 900.0)
    assert len(w) == 2 * (expect + 1), w
    assert min(w[1:-1]) >= 2.0 - 1e-9 and np.allclose(w[1:-1], wall / expect, atol=PIXEL), w


def test_a_reach_ends_on_a_cell_that_carries_the_cut_nodes_and_no_triangle() -> None:
    mesh, _pts = pair_mesh()
    cut = split_gorge_rows(mesh, gorge_ground(x_from=600.0, x_to=1200.0), GorgeRule(rows=4, wall_m=3.0, cell_min_m=2.0, pixel=PIXEL))
    geo = cut.geometry
    assert geo.check() == []
    sizes = ring_sizes(cut)
    assert sizes.min() >= 4
    assert (cut.gorge > 0).any()
    # the cells across the reach's ends keep their place and take the cut face's nodes on their rings
    _a, cx, _cy = geo.areas_centroids()
    rows_x = cx[cut.gorge != 0]
    assert rows_x.min() > X0 + 600.0 - DX and rows_x.max() < X0 + 1200.0 + DX
    hanging = (cut.gorge == 0) & (cut.corridor >= 0) & (sizes > 4)
    assert hanging.sum() >= 4, "one at each end, each side"
    assert len(widths_across(cut, X0 + 300.0)) == 2 and len(widths_across(cut, X0 + 900.0)) == 6
    assert abs(geo.areas_centroids()[0].sum() - mesh.geometry.areas_centroids()[0].sum()) < 1e-6 * geo.areas_centroids()[0].sum()


def test_no_wall_inside_the_pair_leaves_the_mesh_exactly_as_it_was() -> None:
    mesh, _pts = pair_mesh()
    for ground in (gorge_ground(x_from=1e8, x_to=1e8 + 1), gorge_ground(bed_half=40.0)):  # flat; a channel wider than the pair
        out = split_gorge_rows(mesh, ground, GorgeRule(rows=4, wall_m=3.0, cell_min_m=2.0, pixel=PIXEL))
        assert out.geometry is mesh.geometry and not out.gorge.any()


def test_the_setting_is_off_by_default_and_even() -> None:
    assert Strips().gorge_rows == 0
    assert Strips(gorge_rows=4).gorge_rows == 4
    with pytest.raises(ValueError, match="even"):
        Strips(gorge_rows=3)
