"""The local hydraulic radius face conveyance (W49, Spada et al. 2015, HESSD 12, 2607, eqs. 14 to 17).

Three properties: on a bed with no relief across the faces it is the strips sum to round-off; on W48's deep narrow
gorge the conveyance the x faces of one column carry together equals an independent, direct evaluation of Spada et
al.'s integrals on the same ground; and it is the same at 20, 10 and 5 m cells, where the strips sum is too but reads
the section shallow.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.optimize import brentq

from wadi2d.config.schema import Tables
from wadi2d.grid import TileGrid
from wadi2d.solver.cpu.kernels import face_lookup
from wadi2d.tables import ArrayBed, build_tables

PIXEL = 0.5
S, N, Q = 0.01, 0.05, 300.0
BETA = 9.0
NY_PIX, NX_PIX = 640, 160
"""320 m across the gorge, 80 m along it: the faces of one x-column read the whole section."""


def section(t: np.ndarray) -> np.ndarray:
    """W48's gorge: a 12 m bed, walls rising 7 m over 1.5 m, a 10 m ledge at 5 %, hills at 50 %."""
    a = np.abs(t)
    h = np.where(a < 6.0, 0.0, (a - 6.0) / 1.5 * 7.0)
    h = np.where(a >= 7.5, 7.0 + (a - 7.5) * 0.05, h)
    return np.where(a >= 17.5, 7.5 + (a - 17.5) * 0.5, h)


def gorge_bed() -> np.ndarray:
    """Pixels: rows across the gorge (y), columns along it (x), the bed falling S along x."""
    y = (np.arange(NY_PIX) + 0.5) * PIXEL - 0.5 * NY_PIX * PIXEL
    x = (np.arange(NX_PIX) + 0.5) * PIXEL
    return (100.0 - S * x[None, :] + section(y)[:, None]).astype(np.float32).astype(np.float64)


def column_conveyance(dx: float, mode: str, level_over_bed: float, z: np.ndarray | None = None) -> float:
    """The conveyance of the x faces of the grid's middle column at a level over the bed there, summed across."""
    k = round(dx / PIXEL)
    ny, nx = NY_PIX // k, NX_PIX // k
    tg = TileGrid.from_mask(np.ones((ny, nx), bool), 0.0, 0.0, dx)
    bed = gorge_bed() if z is None else z
    tables = build_tables(tg, ArrayBed(bed, PIXEL, row_offset=-k, col_offset=-k), Tables(face_conveyance=mode), N)
    i = nx // 2
    x_face = i * dx
    level = 100.0 - S * x_face + level_over_bed
    ftab = tg.from_tiles(tables.ftabx)
    ef = tg.from_tiles(tables.efx)
    fl = tg.from_tiles(tables.flx)
    rows = ftab.shape[-2]
    total = 0.0
    for j in range(ny):
        jj, ii = j + 1, i + 1  # the padded grid's first active row and column
        zf = fl[jj, ii] + tables.zmin[jj, ii - 1]
        e = level - zf
        if e <= 0.0:
            continue
        _a, t, _w = face_lookup(np.float32(e), np.float32(ef[jj, ii]), ftab[jj, ii].reshape(-1).astype(np.float32), rows)
        total += float(t) ** (5.0 / 3.0)
    return total


def direct_lhrm(level_over_bed: float, beta: float = BETA) -> float:
    """Spada et al.'s eqs. 14 to 17 evaluated directly on the section at the pixel spacing, O(n^2), no prefix sums."""
    y = (np.arange(NY_PIX) + 0.5) * PIXEL - 0.5 * NY_PIX * PIXEL
    z = section(y)
    d = np.clip(level_over_bed - z, 0.0, None)
    wet = d > 0.0
    # the wetted length of the straight ground between two pixel centres, given to the wet end when one end is dry
    per = np.zeros(z.size)
    for t in range(z.size - 1):
        seg = float(np.hypot(PIXEL, z[t + 1] - z[t]))
        if wet[t] and wet[t + 1]:
            per[t] += 0.5 * seg
            per[t + 1] += 0.5 * seg
        elif wet[t] or wet[t + 1]:
            low = t if wet[t] else t + 1
            per[low] += min(d[low] / abs(z[t + 1] - z[t]), 1.0) * seg
    k_total = 0.0
    for i in np.nonzero(wet)[0]:
        lo = i
        while lo > 0 and wet[lo - 1]:
            lo -= 1
        hi = i
        while hi < z.size - 1 and wet[hi + 1]:
            hi += 1
        w = beta * d[i] / PIXEL
        j = np.arange(lo, hi + 1)
        nw = np.clip(1.0 - np.abs(j - i) / w, 0.0, None)
        radius = PIXEL * float(np.sum(d[j] * nw)) / float(np.sum(per[j] * nw))
        k_total += d[i] * radius ** (2.0 / 3.0) * PIXEL / N
    return k_total


def test_a_bed_with_no_relief_across_the_faces_gives_the_strips_sum() -> None:
    y = np.zeros(NY_PIX)
    flat = (100.0 - S * ((np.arange(NX_PIX) + 0.5) * PIXEL)[None, :] + y[:, None]).astype(np.float32).astype(np.float64)
    a = column_conveyance(20.0, "strips", 2.0, flat)
    b = column_conveyance(20.0, "local_radius", 2.0, flat)
    assert b == pytest.approx(a, rel=1e-5)


@pytest.mark.parametrize("dx", [20.0, 10.0, 5.0])
def test_the_gorge_conveyance_is_spada_et_al_s_at_every_cell_size(dx: float) -> None:
    for over in (2.0, 4.0, 5.3):
        assert column_conveyance(dx, "local_radius", over) == pytest.approx(direct_lhrm(over), rel=0.01)


def test_the_gorge_reads_deeper_than_the_strips_sum_and_alike_at_every_size() -> None:
    def depth(dx: float, mode: str) -> float:
        return brentq(lambda h: column_conveyance(dx, mode, h) * S**0.5 - Q, 1.0, 12.0, xtol=1e-3)

    strips = [depth(dx, "strips") for dx in (20.0, 5.0)]
    local = [depth(dx, "local_radius") for dx in (20.0, 5.0)]
    assert abs(strips[0] - strips[1]) < 0.02 and abs(local[0] - local[1]) < 0.03
    assert local[0] > 1.15 * strips[0], (strips, local)


def test_a_flat_face_in_a_channel_deeper_than_its_table_still_sees_the_walls() -> None:
    """A 12 m rectangular channel 11 m deep: the faces on its bed have no relief of their own, so their table top was
    face_depth_min (8 m) and above it the conveyance grew with the area, the strips law, reading the walls away; the
    top now reaches the window's relief (W49). The same at 20 m and 2.5 m cells, and well under the strips sum."""
    y = (np.arange(NY_PIX) + 0.5) * PIXEL - 0.5 * NY_PIX * PIXEL
    x = (np.arange(NX_PIX) + 0.5) * PIXEL
    z = (100.0 - S * x[None, :] + np.where(np.abs(y) < 6.0, 0.0, 20.0)[:, None]).astype(np.float32).astype(np.float64)
    coarse = column_conveyance(20.0, "local_radius", 11.0, z)
    fine = column_conveyance(2.5, "local_radius", 11.0, z)
    assert fine == pytest.approx(coarse, rel=0.005)
    assert fine < 0.8 * column_conveyance(2.5, "strips", 11.0, z)


def test_on_the_quadtree_the_fine_faces_and_the_interface_faces_are_the_uniform_grid_s() -> None:
    """A mesh of 10 m tiles with two columns of 20 m tiles, on rough ground with a trench: every face of a 10 m tile,
    the interface faces on its east side included, carries the same local-radius table as the uniform 10 m grid."""
    from scipy.ndimage import gaussian_filter

    from wadi2d.grid.quad import QuadGrid
    from wadi2d.solver.layout import TILE
    from wadi2d.tables.quad import build_quad_tables

    dx, k = 10.0, 4
    mask = np.zeros((64, 320), bool)
    mask[2:-2, 2:-2] = True
    level = np.zeros((2, 10), np.int32)
    level[:, 4:6] = 1
    q = QuadGrid.from_levels(mask, 0.0, 0.0, dx, level)
    u = TileGrid(0.0, 0.0, dx, q.mask.copy())
    z = gaussian_filter(np.random.default_rng(1).normal(0, 1.0, (64 * k + 8, 320 * k + 8)), 6) * 15 + 300.0
    z[100:112, :] -= 6.0  # a trench 6 m deep and 15 m wide along x, walls the windows reach
    bed = ArrayBed(z, dx / k, 4, 4)
    cfg = Tables(face_conveyance="local_radius")
    tq, tu = build_quad_tables(q, bed, cfg, 0.03), build_tables(u, bed, cfg, 0.03)
    ref = Tables(face_conveyance="strips")
    tq_s = build_quad_tables(q, bed, ref, 0.03)
    fu = tu.grid.from_tiles(tu.ftabx)
    row = q.interfaces[q.interfaces[:, 1] == 2][0]
    t, base = int(row[0]), int(row[5])
    j0, i0 = int(q.tiles[t, 0]) * TILE, int(q.tiles[t, 1]) * TILE
    pt, rw = base // (TILE * TILE), (base % (TILE * TILE)) // TILE
    moved = 0
    for jq in range(TILE):
        own_q, own_u = tq.ftabx[t, jq, 5], fu[j0 + jq, i0 + 5]
        np.testing.assert_allclose(own_q, own_u, rtol=1e-5, atol=1e-6)
        side_q, side_u = tq.ftabx[pt, rw, jq], fu[j0 + jq, i0 + TILE]
        np.testing.assert_allclose(side_q, side_u, rtol=1e-5, atol=1e-6)
        moved += not np.allclose(side_q, tq_s.ftabx[pt, rw, jq], rtol=1e-4)
    assert moved > 0, "the interface faces should see the trench's walls"


class Watched(ArrayBed):
    """An array bed that remembers the largest window it was asked for, in pixels a side."""

    largest = 0

    def read(self, row0: int, col0: int, nrows: int, ncols: int) -> np.ndarray:
        type(self).largest = max(type(self).largest, nrows, ncols)
        return super().read(row0, col0, nrows, ncols)


def test_a_bed_of_fine_pixels_is_read_no_further_than_it_is_long() -> None:
    """The reach is 144 m whatever the pixel (W85): on 5 mm pixels a tile's window was 57,729 px a side, 24.8 GiB,
    for a bed 1.28 m long. No face's line now reaches further past its ends than the bed is long."""
    from wadi2d.solver.layout import TILE

    k, dx = 4, 0.02
    grid = TileGrid.from_mask(np.ones((30, 62), bool), 0.0, 0.0, dx)
    ny, nx = grid.shape
    y, x = np.mgrid[0 : ny * k, 0 : nx * k] * (dx / k)
    Watched.largest = 0
    bed = Watched(0.05 * x + 0.5 * np.abs(y - 0.5 * ny * dx), dx / k)
    asked = int(np.ceil(BETA * Tables().face_depth_max / bed.pixel))
    tables = build_tables(grid, bed, Tables(), 0.03, workers=1)
    assert bed.span == nx * k < asked
    assert Watched.largest == TILE * k + 1 + 2 * bed.span
    assert np.isfinite(tables.ftabx).all() and np.isfinite(tables.ftaby).all()


def test_a_bed_longer_than_the_reach_is_read_as_before() -> None:
    from wadi2d.solver.layout import TILE

    grid = TileGrid.from_mask(np.ones((30, 30), bool), 0.0, 0.0, 10.0)
    ny, nx = grid.shape
    Watched.largest = 0
    bed = Watched(np.zeros((ny * 10, nx * 10)), 1.0)
    build_tables(grid, bed, Tables(), 0.03, workers=1)
    asked = int(np.ceil(BETA * Tables().face_depth_max / bed.pixel))
    assert asked < bed.span and Watched.largest == TILE * 10 + 1 + 2 * asked
