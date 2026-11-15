"""W81: tables built on threads are the one-thread build's to the digit, on the uniform grid and the quadtree."""

from __future__ import annotations

import numpy as np
import pytest

from wadi2d.config.schema import Tables
from wadi2d.grid import TileGrid
from wadi2d.tables import ArrayBed, build_tables
from wadi2d.tables.parallel import ThreadBeds, run_all, table_workers

DX, K = 10.0, 5
P = DX / K


def bumpy(nr: int, nc: int) -> np.ndarray:
    x = (np.arange(nc) + 0.5) * P
    y = -(np.arange(nr) + 0.5) * P
    X, Y = np.meshgrid(x, y)
    return 100.0 - 0.02 * X + 1.5 * np.sin(X / 13.0) * np.cos(Y / 9.0) + 0.3 * np.sin(X * Y / 400.0)


def arrays(tables) -> dict[str, np.ndarray]:
    return {k: v for k, v in vars(tables).items() if isinstance(v, np.ndarray)}


@pytest.mark.parametrize("conveyance", ["strips", "local_radius"])
def test_tiles_on_threads_give_the_one_thread_tables(conveyance) -> None:
    mask = np.ones((80, 75), bool)
    mask[:10, :20] = False  # a ragged domain: some tiles partly inactive
    grid = TileGrid.from_mask(mask, 0.0, 0.0, DX)
    ny, nx = grid.shape
    bed = ArrayBed(bumpy(ny * K + 40, nx * K + 40), P, 20, 20)
    cfg = Tables(face_conveyance=conveyance, face_depth_max=4.0)
    calls = []

    def edit(z, row0, col0):  # a burn on every window, as terrain objects do: called from the threads
        calls.append((row0, col0))
        z[:, (np.arange(z.shape[1]) + col0) % 37 == 0] -= 0.5

    one = arrays(build_tables(grid, bed, cfg, 0.03, edit=edit, workers=1))
    many = arrays(build_tables(grid, bed, cfg, 0.03, edit=edit, workers=4))
    assert len(calls) == 2 * (grid.ntiles - 1)
    for name, value in one.items():
        np.testing.assert_array_equal(value, many[name], err_msg=name)


def test_the_quadtree_on_threads_gives_the_one_thread_tables() -> None:
    from scipy.ndimage import gaussian_filter

    from tests.solver.test_quad import DX as QDX
    from tests.solver.test_quad import column_levels, grids
    from wadi2d.tables.quad import build_quad_tables

    q, _u = grids(column_levels(4, 6), 64, 320)  # fine, coarse and the interface faces between them
    z = gaussian_filter(np.random.default_rng(1).normal(0, 1.0, (64 * 2 + 8, 320 * 2 + 8)), 4) * 20 + 300.0
    bed = ArrayBed(z, QDX / 2, 4, 4)
    one = arrays(build_quad_tables(q, bed, Tables(), 0.03, workers=1))
    many = arrays(build_quad_tables(q, bed, Tables(), 0.03, workers=4))
    for name, value in one.items():
        np.testing.assert_array_equal(value, many[name], err_msg=name)


def test_workers_come_from_the_argument_then_the_environment(monkeypatch) -> None:
    monkeypatch.delenv("WADI2D_TABLE_WORKERS", raising=False)
    assert table_workers(3) == 3 and table_workers(0) == 1
    monkeypatch.setenv("WADI2D_TABLE_WORKERS", "2")
    assert table_workers() == 2


def test_a_raster_bed_is_reopened_on_each_worker_thread_and_closed() -> None:
    opened = []

    class Bed:
        def reopen(self):
            other = Bed()
            opened.append(other)
            return other

        def close(self):
            opened.remove(self)

    bed = Bed()
    beds = ThreadBeds(bed)
    seen = set()
    run_all(range(16), lambda _i: seen.add(id(beds.get())), 4)
    assert beds.get() is bed  # the calling thread keeps its own
    assert 1 <= len(opened) <= 4 and bed not in opened
    beds.close()
    assert opened == []
