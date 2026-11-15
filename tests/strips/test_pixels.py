"""Pixel depth over a strip's cells (W45, stage 7): a cell's pixels hold its water exactly under a surface that follows
the ground, two joined cells share one surface at their edge, and a job with a corridor paints the corridor's pixels
into the pixel maps beside the squares'."""

from __future__ import annotations

import json

import numpy as np
import pytest
import rasterio

from tests.engine.conftest import X0, Y0, tilted_dem  # noqa: F401
from tests.engine.test_strips_run import corridor, plane_job
from wadi2d.config.schema import Pixels as PixelRule
from wadi2d.run import run_job
from wadi2d.solver.poly.mesh import PolyMesh
from wadi2d.strips.geometry import MeshGeometry
from wadi2d.strips.pixels import StripMaxima, ground_from_pixels
from wadi2d.strips.tables import Pixels, build_poly_tables
from wadi2d.tables.builder import hbar_at_level

P = 1.0
"""Pixel, m."""


def two_quads(slope: float = 0.05) -> tuple[MeshGeometry, PolyMesh, np.ndarray, Pixels]:
    """Two 20 x 10 m quads side by side along x on a plane falling east at ``slope``, pixels of 1 m."""
    x = np.array([0.0, 20.0, 40.0, 0.0, 20.0, 40.0])
    y = np.array([0.0, 0.0, 0.0, 10.0, 10.0, 10.0])
    rings = [np.array([0, 1, 4, 3]), np.array([1, 2, 5, 4])]  # counter-clockwise
    geo = MeshGeometry.from_rings(x, y, rings)
    nx, ny = 48, 16
    xs = -4.0 + (np.arange(nx) + 0.5) * P
    z = np.tile(100.0 - slope * xs, (ny, 1))
    pix = Pixels(z, -4.0, 14.0, P)
    from wadi2d.config.schema import Tables

    mesh, kept = build_poly_tables(geo, pix, Tables(), 20.0, 0.03)
    return geo, mesh, kept, pix


def test_a_cell_holds_its_water_exactly_under_a_surface_that_follows_the_ground() -> None:
    geo, mesh, kept, pix = two_quads()
    ground = ground_from_pixels(geo, mesh, kept, pix, 0.0, 0.0, datum=99.0)
    assert ground.count == 2 * 200  # 20 x 10 pixels of 1 m each
    assert np.allclose(ground.weights.sum(axis=1), 1.0, atol=1e-5)
    rule = PixelRule()
    maxima = StripMaxima(np, ground, mesh, rule)
    level = 99.3 + 0.0 * mesh.zmin[:2]  # one still level over both cells: joined, one surface
    hb = hbar_at_level(level, mesh.zmin[:2], mesh.hc[:2], mesh.dtab[:2])
    d = level - mesh.zmin[:2]
    maxima.add(d, hb, np.zeros(2))
    depth, _speed, _dv = maxima.result()
    for c in range(2):
        on = ground.cell == c
        held = depth[on].sum() * P * P
        assert held == pytest.approx(hb[c] * mesh.area[c], rel=1e-3), (c, held, hb[c] * mesh.area[c])
        # deeper where the ground is lower: the pixel depth rises with falling ground
        order = np.argsort(ground.ground[on])
        assert np.all(np.diff(depth[on][order]) <= 1e-4)
    # a still level over joined cells is one flat surface: depth + ground is the level everywhere wet
    wet = depth > 0.0
    surface = depth[wet] + ground.ground[wet] + 99.0
    assert np.ptp(surface) < 2e-3, np.ptp(surface)


def test_a_dry_neighbour_keeps_its_own_surface_and_a_wet_one_its_water() -> None:
    geo, mesh, kept, pix = two_quads()
    ground = ground_from_pixels(geo, mesh, kept, pix, 0.0, 0.0, datum=99.0)
    maxima = StripMaxima(np, ground, mesh, PixelRule())
    hb = np.array([0.4, 0.0])
    from wadi2d.solver.state import level_of

    d = level_of(hb, mesh.hc[:2], mesh.dtab[:2])
    maxima.add(d, hb, np.array([1.5, 0.0]))
    depth, speed, dv = maxima.result()
    on = ground.cell == 0
    assert depth[on].sum() * P * P == pytest.approx(0.4 * mesh.area[0], rel=1e-3)
    assert not depth[~on].any()
    assert speed[on].max() == pytest.approx(1.5, abs=1e-5) and dv.max() > 0.0


def test_a_job_with_a_corridor_paints_the_corridor_pixels_into_the_pixel_maps(tilted_dem, tmp_path) -> None:  # noqa: F811
    cfg = plane_job(tilted_dem, corridor())
    heavy = cfg.storm.model_copy(update={"depth_mm": 400.0})  # enough for the squares to be kept too
    pixels = cfg.outputs.pixels.model_copy(update={"enabled": True})
    cfg = cfg.model_copy(update={"storm": heavy, "outputs": cfg.outputs.model_copy(update={"map_every_s": 300.0, "pixels": pixels})})
    out = tmp_path / "pixels"
    run = run_job(cfg, out)
    assert run.exit_code == 0, run.message
    stats = json.loads((out / "pixels" / "pixels.json").read_text(encoding="utf-8"))
    assert stats["kept_cells"] > 0, stats
    assert stats["strip_pixels"] > 0 and stats["strip_depth_max_m"] > 0.0
    with rasterio.open(out / "pixels" / "pixel_depth.tif") as src:
        depth = src.read(1)
        t = src.transform
        nodata = src.nodata
    # the corridor's middle, 100 m along, on its axis: painted, and varying inside the 4 m cells
    i = int((X0 + 100.0 - t.c) / t.a)
    j = int((t.f - (Y0 - 48.0)) / t.a)
    patch = depth[j - 6 : j + 6, i - 6 : i + 6]
    assert (patch != nodata).all() and patch.max() > 0.0
    assert np.ptp(patch) > 1e-4


def test_strip_ground_in_pieces_is_the_whole_windows_to_the_digit(monkeypatch) -> None:
    """W81: the strip's pixels are found a piece at a time and their weights a block at a time; on a corridor at 45
    degrees with its gap triangles, pieces of 2 cells and blocks of 1,000 pixels give what one window gave."""
    import wadi2d.strips.pixels as sp
    import wadi2d.strips.tables as st
    from tests.strips.test_mesher import DX as MDX
    from tests.strips.test_mesher import K as MK
    from tests.strips.test_mesher import _bed, strip_case
    from wadi2d.config.schema import Tables
    from wadi2d.strips.tables import _owners

    tg, _tables, _sc, _tc, strip = strip_case(45.0)
    z = _bed(45.0)[4]
    pix = Pixels(z, tg.x0, tg.y0, MDX / MK)
    geo = strip.geometry
    mesh, kept = build_poly_tables(geo, pix, Tables(), MDX, 0.03)
    monkeypatch.setattr(st, "PIECE_CELLS", 10_000)
    whole = ground_from_pixels(geo, mesh, kept, pix, tg.x0, tg.y0, datum=90.0)
    monkeypatch.setattr(st, "PIECE_CELLS", 2)
    monkeypatch.setattr(sp, "WEIGHT_BLOCK", 1000)
    pieces = ground_from_pixels(geo, mesh, kept, pix, tg.x0, tg.y0, datum=90.0)
    # the owners as the code before W81 found them, on the whole window at once
    n = mesh.real
    owner = _owners(geo.ring_start[: n + 1], geo.ring_node, geo.x, geo.y, pix.x0, pix.y0, pix.pixel, *z.shape)
    r, c = np.nonzero(owner >= 0)
    order = np.argsort(owner[r, c], kind="stable")
    assert pieces.count > 3000
    np.testing.assert_array_equal(pieces.rows, r[order])
    np.testing.assert_array_equal(pieces.cols, c[order])
    np.testing.assert_array_equal(pieces.cell, owner[r, c][order])
    for name in ("rows", "cols", "cell", "ground", "ptr", "weights", "incidence", "inc_cell", "inc_node", "pair_a", "pair_b"):
        np.testing.assert_array_equal(getattr(whole, name), getattr(pieces, name), err_msg=name)