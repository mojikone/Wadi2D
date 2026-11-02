"""A Manning n per pixel on the faces, and nothing else moves when no object asks for one."""

from __future__ import annotations

import numpy as np
import pytest

from tests.terrain.helpers import flat_bed, grid_of, obj
from wadi2d.config.schema import Tables, Terrain
from wadi2d.tables import ArrayBed, build_tables
from wadi2d.terrain import Ground, apply_objects

SOUTH = [(160.0, 300.0), (160.0, 20.0)]
N_GROUND = 0.05


def tables_of(objects):
    grid = grid_of()
    bed = flat_bed()
    edits = apply_objects(grid, objects, 1.0, Terrain(), Ground(bed, grid.x0, grid.y0))
    return build_tables(grid, bed, Tables(), N_GROUND, edits.crest, edits.edit, edits.lining), grid


def channel(**fields):
    return obj(
        "channel",
        SOUTH,
        z_constant=98.0,
        section={"width": 40.0, "left_slope": 2.0, "right_slope": 2.0},
        **fields,
    )


def test_an_all_lined_face_conveys_the_ratio_of_the_two_n():
    # conveyance^(3/5) is stored, so the ratio shows as (n_ground / n_lined)^(3/5)
    plain, grid = tables_of([channel()])
    lined, _ = tables_of([channel(lining_n=0.0125)])
    j, i = 16 + 1, 16 + 1
    a = grid.to_tiles(np.arange(grid.shape[0] * grid.shape[1], dtype=np.float64).reshape(grid.shape))
    tile, row, col = (int(v[0]) for v in np.nonzero(a == j * grid.shape[1] + i))
    k_plain = plain.ftaby[tile, row, col, -1, 1]
    k_lined = lined.ftaby[tile, row, col, -1, 1]
    assert k_lined / k_plain == pytest.approx((N_GROUND / 0.0125) ** 0.6, rel=1e-5)


def test_lining_leaves_ground_outside_the_section_alone():
    plain, grid = tables_of([channel()])
    lined, _ = tables_of([channel(lining_n=0.0125)])
    far = np.zeros(grid.shape, bool)
    far[:, :6] = True
    a = grid.to_tiles(far.astype(np.float64)).astype(bool)
    assert np.array_equal(plain.ftabx[a], lined.ftabx[a])


def test_no_lining_gives_the_very_tables_of_no_lining_hook():
    grid = grid_of()
    bed = flat_bed()
    plain = build_tables(grid, bed, Tables(), N_GROUND)
    nan = build_tables(grid, bed, Tables(), N_GROUND, lining=lambda *_args: None)
    assert np.array_equal(plain.ftabx, nan.ftabx)
    assert np.array_equal(plain.ftaby, nan.ftaby)


def test_a_pixel_lining_on_bumpy_ground_changes_only_the_lined_share():
    grid = grid_of()
    z = flat_bed().z.copy() + 0.3 * np.sin(np.arange(flat_bed().z.shape[1]) / 3.0)
    bed = ArrayBed(z, 1.0)
    half = build_tables(grid, bed, Tables(), N_GROUND, lining=_half_lined)
    whole = build_tables(grid, bed, Tables(), N_GROUND, lining=_all_lined)
    none = build_tables(grid, bed, Tables(), N_GROUND)
    assert none.ftaby.sum() < half.ftaby.sum() < whole.ftaby.sum()


def _half_lined(_z, n, _row0, _col0):
    n[:, ::2] = 0.0125


def _all_lined(_z, n, _row0, _col0):
    n[:] = 0.0125
