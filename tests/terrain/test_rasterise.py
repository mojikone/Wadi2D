"""GDAL's rasterise on the table threads (W85): the masks are the single-thread ones, and no two calls run at once."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import shapely
from rasterio import features
from rasterio.transform import Affine

from wadi2d.config.schema import Section, Tables, Terrain, TerrainObject
from wadi2d.grid import TileGrid
from wadi2d.tables import ArrayBed, build_tables
from wadi2d.terrain import Ground, apply_objects, rasterise

THREADS = 16
SHAPE = (257, 257)
PIXEL = 0.5


def strips(n: int) -> list:
    """(strip, transform) of n calls: buffered lines at every angle through windows spread over 20 km, each window
    with its own transform, as a burn line's pixel edit asks for them tile by tile."""
    rng = np.random.default_rng(85)
    out = []
    for _ in range(n):
        west, north = 400000.0 + rng.integers(0, 40000) * PIXEL, 2700000.0 - rng.integers(0, 40000) * PIXEL
        cx, cy = west + 0.5 * SHAPE[1] * PIXEL, north - 0.5 * SHAPE[0] * PIXEL
        a, half = rng.uniform(0.0, np.pi), rng.uniform(20.0, 150.0)
        dx, dy = half * np.cos(a), half * np.sin(a)
        line = shapely.LineString([(cx - dx, cy - dy), (cx + dx, cy + dy)])
        out.append(
            (
                line.buffer(rng.uniform(0.5, 8.0), cap_style="flat"),
                Affine(PIXEL, 0.0, west, 0.0, -PIXEL, north),
            )
        )
    return out


def burn(job) -> np.ndarray:
    strip, transform = job
    return rasterise.rasterize(
        [(strip, 1)], out_shape=SHAPE, transform=transform, all_touched=True, dtype="uint8"
    )


def test_many_strips_from_16_threads_give_the_single_thread_masks():
    work = strips(1200)
    alone = [burn(job) for job in work]
    assert sum(int(mask.sum()) for mask in alone) > 1_000_000  # the strips do land in their windows
    with ThreadPoolExecutor(THREADS) as pool:
        together = list(pool.map(burn, work))
    differing = [n for n, (a, b) in enumerate(zip(alone, together, strict=True)) if not np.array_equal(a, b)]
    assert differing == []


def test_no_two_rasterise_calls_run_at_once(monkeypatch):
    """The lock is the fix: with it off the table threads ran these calls together, and rasterio warned on a third
    of them that its in-memory dataset had no geotransform."""
    real = features.rasterize
    running, most = [0], [0]
    guard = threading.Lock()

    def watched(*args, **kwargs):
        with guard:
            running[0] += 1
            most[0] = max(most[0], running[0])
        time.sleep(0.001)  # long enough for another thread to walk in, were the door open
        try:
            return real(*args, **kwargs)
        finally:
            with guard:
                running[0] -= 1

    monkeypatch.setattr(rasterise.features, "rasterize", watched)
    with ThreadPoolExecutor(THREADS) as pool:
        list(pool.map(burn, strips(200)))
    assert most[0] == 1


def bumpy(nr: int, nc: int, pixel: float) -> np.ndarray:
    y, x = np.mgrid[0:nr, 0:nc] * pixel
    return (100.0 - 0.02 * x + 1.5 * np.sin(x / 13.0) * np.cos(y / 9.0)).astype(np.float32).astype(np.float64)


def test_tables_with_burn_lines_and_embankments_are_the_same_on_one_thread_and_on_16():
    """The real edits through the real builder: twelve burn lines and two embankments across nine tiles."""
    dx, k = 10.0, 5
    grid = TileGrid.from_mask(np.ones((90, 90), bool), 0.0, 0.0, dx)
    ny, nx = grid.shape
    bed = ArrayBed(bumpy(ny * k, nx * k, dx / k), dx / k)
    rng = np.random.default_rng(7)
    objects = []
    for n in range(12):
        (x0, y0), (x1, y1) = rng.uniform(40.0, 860.0, (2, 2))
        objects.append(
            TerrainObject(
                kind="burn_line", name=f"burn {n}", coordinates=[(x0, -y0), (x1, -y1)], depth=1.0, width=4.0
            )
        )
    for n, y in enumerate((-300.0, -620.0)):
        line = [(60.0, y), (840.0, y + 90.0)]
        shape = Section(width=6.0, left_slope=2.0, right_slope=2.0)
        objects.append(
            TerrainObject(
                kind="embankment", name=f"bank {n}", coordinates=line, z_constant=101.5, section=shape
            )
        )
    edits = apply_objects(grid, objects, bed.pixel, Terrain(), Ground(bed, grid.x0, grid.y0))
    cfg = Tables(face_depth_max=4.0)
    built = [
        build_tables(grid, bed, cfg, 0.03, edits.crest, edits.edit, edits.lining, workers=workers)
        for workers in (1, THREADS)
    ]
    one, many = (
        {key: value for key, value in vars(t).items() if isinstance(value, np.ndarray)} for t in built
    )
    assert not np.array_equal(
        one["zmin"], build_tables(grid, bed, cfg, 0.03, workers=1).zmin
    )  # the edits do bite
    for name, value in one.items():
        np.testing.assert_array_equal(value, many[name], err_msg=name)
