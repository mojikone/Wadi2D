"""Polygon tables from the DEM (W45, stage 2): a square lattice as polygons gives the lattice's tables to the digit,
and a triangle and a turned quad get the tables of their own pixels."""

from __future__ import annotations

import numpy as np
import pytest

from wadi2d.config.schema import Tables
from wadi2d.grid import TileGrid
from wadi2d.strips.geometry import MeshGeometry
from wadi2d.strips.tables import Pixels, build_poly_tables, face_profile
from wadi2d.tables import ArrayBed, build_tables
from wadi2d.tables.core import _cell_table

DX, K = 10.0, 10
P = DX / K
SIDE = 8


def bumpy(nr: int, nc: int, x0: float, y0: float) -> np.ndarray:
    """Ground with relief inside every cell and a 2 % fall east, rows south."""
    x = x0 + (np.arange(nc) + 0.5) * P
    y = y0 - (np.arange(nr) + 0.5) * P
    X, Y = np.meshgrid(x, y)
    return 100.0 - 0.02 * X + 0.8 * np.sin(X / 7.0) * np.cos(Y / 5.0)


def lattice_case():
    tg = TileGrid.from_mask(np.ones((SIDE, SIDE), bool), 0.0, 0.0, DX)
    ny, nx = tg.shape
    z = bumpy(ny * K, nx * K, tg.x0, tg.y0)
    tables = build_tables(tg, ArrayBed(z, P), Tables(), 0.03)
    jj, ii = np.nonzero(tg.mask)
    # nodes at the corners of the active cells, rings counter-clockwise: SW, SE, NE, NW
    corner = {}
    xs, ys, rings = [], [], []
    for j, i in zip(jj, ii, strict=True):
        ring = []
        for cj, ci in ((j + 1, i), (j + 1, i + 1), (j, i + 1), (j, i)):
            if (cj, ci) not in corner:
                corner[(cj, ci)] = len(xs)
                xs.append(tg.x0 + ci * DX)
                ys.append(tg.y0 - cj * DX)
            ring.append(corner[(cj, ci)])
        rings.append(np.array(ring))
    geo = MeshGeometry.from_rings(np.array(xs), np.array(ys), rings)
    return tg, tables, z, geo, jj, ii


def test_a_square_lattice_as_polygons_gives_the_lattice_tables_to_the_digit() -> None:
    tg, tables, z, geo, jj, ii = lattice_case()
    assert geo.check() == []
    mesh, _kept = build_poly_tables(geo, Pixels(z, tg.x0, tg.y0, P), Tables(), DX, 0.03)
    index = {(int(j), int(i)): c for c, (j, i) in enumerate(zip(jj, ii, strict=True))}
    np.testing.assert_allclose(mesh.zmin, tables.zmin[jj, ii], rtol=0, atol=1e-9)
    np.testing.assert_allclose(mesh.zbar, tables.zbar[jj, ii], rtol=1e-12)
    np.testing.assert_allclose(mesh.hc, tg.from_tiles(tables.hc)[jj, ii], rtol=2e-7)
    np.testing.assert_allclose(mesh.dtab, tg.from_tiles(tables.dtab)[jj, ii], rtol=2e-7, atol=1e-6)
    assert mesh.area == pytest.approx(DX * DX)
    flx, efx, ftabx = (tg.from_tiles(getattr(tables, n)) for n in ("flx", "efx", "ftabx"))
    fly, efy, ftaby = (tg.from_tiles(getattr(tables, n)) for n in ("fly", "efy", "ftaby"))
    matched = 0
    for k in range(mesh.nfaces):
        a, b = int(mesh.left[k]), int(mesh.right[k])
        ja, ia = jj[a], ii[a]
        jb, ib = jj[b], ii[b]
        if ja == jb:  # an x face between (j, i-1) and (j, i); the mesh may have them either way round
            i = max(ia, ib)
            want = (flx[ja, i] + tables.zmin[ja, i - 1], efx[ja, i], ftabx[ja, i])
        else:
            j = max(ja, jb)
            want = (fly[j, ia] + tables.zmin[j - 1, ia], efy[j, ia], ftaby[j, ia])
        assert mesh.zf[k] == pytest.approx(want[0], abs=1e-5)  # the tile tables hold faces as float32
        assert mesh.ef[k] == pytest.approx(want[1], rel=2e-7)
        np.testing.assert_allclose(mesh.ftab[k], want[2], rtol=2e-7, atol=1e-6)
        matched += 1
    assert matched == 2 * SIDE * (SIDE - 1)
    assert index  # every active cell is a polygon
    assert np.abs(mesh.skew_degrees()).max() < 1e-9


def test_a_triangle_takes_the_tables_of_its_own_pixels() -> None:
    z = bumpy(40, 40, 0.0, 0.0)
    pix = Pixels(z, 0.0, 0.0, P)
    # a square a third of a pixel off the pixel grid, so no pixel centre lies exactly on an edge
    x = np.array([0.3, 30.3, 0.3, 30.3])
    y = np.array([-0.3, -0.3, -30.3, -30.3])
    # two triangles from a square, split on the diagonal SW to NE: ring 0 is the south-east one
    geo = MeshGeometry.from_rings(x, y, [np.array([2, 3, 1]), np.array([2, 1, 0])])
    mesh, _kept = build_poly_tables(geo, pix, Tables(), DX, 0.03)
    assert mesh.nfaces == 1  # the diagonal; the outer edges are walls
    assert mesh.area == pytest.approx([450.0, 450.0])
    X, Y = np.meshgrid((np.arange(40) + 0.5) * P, -(np.arange(40) + 0.5) * P)
    south_east = (X > 0.3) & (X < 30.3) & (Y > -30.3) & (Y < X - 30.6)  # below the diagonal from SW to NE
    tab = np.zeros(Tables().rows)
    zm, _rel, hc = _cell_table(np.sort(z[south_east]), Tables().rows, tab)
    assert mesh.zmin[0] == pytest.approx(zm) and mesh.hc[0] == pytest.approx(hc)
    np.testing.assert_allclose(mesh.dtab[0], tab)
    assert south_east.sum() * P * P == pytest.approx(450.0, rel=0.02)


def test_a_turned_quad_on_a_plane_holds_the_planes_volume() -> None:
    nc = 60
    x = (np.arange(nc) + 0.5) * P
    X, _Y = np.meshgrid(x, x)
    z = 100.0 - 0.05 * X  # a plane falling east
    pix = Pixels(z, 0.0, 0.0, P)
    th = np.radians(30.0)
    c, s = np.cos(th), np.sin(th)
    local = np.array([[-15.0, -5.0], [15.0, -5.0], [15.0, 5.0], [-15.0, 5.0]])
    xs = 30.0 + local[:, 0] * c - local[:, 1] * s
    ys = -30.0 + local[:, 0] * s + local[:, 1] * c
    geo = MeshGeometry.from_rings(xs, ys, [np.array([0, 1, 2, 3])])
    mesh, _kept = build_poly_tables(geo, pix, Tables(), DX, 0.03)
    assert mesh.area[0] == pytest.approx(300.0)
    # full to the brim (mean depth hc) the surface stands at the highest pixel; the mean bed is the plane's at the centroid
    from wadi2d.solver.state import level_of

    level = level_of(np.array([mesh.hc[0]]), mesh.hc, mesh.dtab)
    zmax = 100.0 - 0.05 * (30.0 - 15.0 * c - 5.0 * s)
    assert float(level[0]) + mesh.zmin[0] == pytest.approx(zmax, abs=0.1)
    assert mesh.zbar[0] == pytest.approx(100.0 - 0.05 * 30.0, abs=0.05)
    assert mesh.zmin[0] == pytest.approx(100.0 - 0.05 * (30.0 + 15.0 * c + 5.0 * s), abs=0.1)


def test_a_face_profile_reads_the_higher_pixel_either_side() -> None:
    z = np.zeros((20, 20))
    z[:, 10] = 2.0  # a ridge one pixel wide at x = 10 to 11
    pix = Pixels(z, 0.0, 0.0, P)
    prof, spacing = face_profile(pix, 10.0, -2.0, 10.0, -12.0)  # along the ridge's west edge
    assert spacing == pytest.approx(P)
    assert prof.size == 10 and np.all(prof == 2.0)
    prof, _ = face_profile(pix, 2.0, -5.0, 8.0, -5.0)  # across the plain, short of the ridge
    assert np.all(prof == 0.0)
