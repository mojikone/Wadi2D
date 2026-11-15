"""Sleeping tiles (W90): a tile that neither holds water nor can be reached by any before the next check is not
stepped, and the run is the run that steps every tile, to the last digit: every state array, the step count and the
time step. Squares alone here; ``tests/strips/test_sleeping.py`` has the same with a strip of aligned cells.

The reference steps every tile at every step (``adaptive_active`` off). A sleeping tile holds no water, so nothing
may differ; a difference of one bit anywhere fails.
"""

from __future__ import annotations

import numpy as np
import pytest

from tests.strips.valley import DX, Valley, both, pair, run_same
from wadi2d.solver.layout import STRIDE2


# ---- squares alone
def test_still_water_in_one_corner_leaves_the_rest_asleep() -> None:
    a, b = pair(tiles_y=3, tiles_x=4, strip=False)

    def lake(v: Valley) -> None:
        h = np.zeros(v.grid.shape)
        h[v.axis - 6 : v.axis + 7, 100:125] = 0.6  # a pond across the valley's axis in the last tile column
        v.model.set_depth(h * v.grid.mask)

    both(a, b, lake)
    assert a.awake() < b.awake() == 12
    awake = run_same(a, b, [30.0, 120.0, 400.0])
    assert max(awake) < 12
    assert a.model.volume() == pytest.approx(0.6 * 13 * 25 * DX * DX, rel=1e-6)


def test_a_front_that_crosses_tile_borders_in_every_direction() -> None:
    a, b = pair(tiles_y=5, tiles_x=5, strip=False)

    def columns(v: Valley) -> None:
        h = np.zeros(v.grid.shape)
        h[8:24, 70:90] = 2.0  # on the north hillside: it runs south across two rows of tiles
        h[136:152, 70:90] = 2.0  # on the south hillside: north across two
        h[72:88, 70:90] = 3.0  # on the axis: it backs up west and runs east
        v.model.set_depth(h * v.grid.mask)

    both(a, b, columns)
    first = a.awake()
    assert first == 15  # the three wet tiles and their neighbours, of 25
    awake = run_same(a, b, [20.0, 60.0, 150.0, 400.0, 900.0])
    wet = a.model.field("h") > 0.0
    assert wet[32:64, :].any() and wet[96:128, :].any() and wet[:, :64].any() and wet[:, 96:].any()
    assert awake[-1] > first


def test_rain_that_starts_later_on_a_sleeping_tile() -> None:
    a, b = pair(tiles_y=2, tiles_x=8, strip=False)
    both(a, b, lambda v: v.model.set_source(v.head(30.0)))
    run_same(a, b, [200.0])
    asleep = a.awake()
    assert asleep < 16

    def rain(v: Valley) -> None:
        rate = v.head(30.0)
        rate[5:25, 200:230] = 60.0 / 3.6e6  # 60 mm/h on a hillside six tiles down the valley, dry and asleep
        v.model.set_source(rate * v.grid.mask)

    far = a.model.cell_state_index(10, 210) // STRIDE2
    assert far not in set(a.model.backend.active_tiles.tolist())
    both(a, b, rain)
    assert far in set(a.model.backend.active_tiles.tolist())
    run_same(a, b, [260.0, 500.0, 900.0])
    assert a.model.field("h")[5:25, 200:230].min() > 0.0


def test_an_inflow_at_the_head_and_an_open_end() -> None:
    a, b = pair(tiles_y=2, tiles_x=8, strip=False)
    both(a, b, Valley.open_end)
    both(a, b, lambda v: v.model.set_source(v.head(40.0)))
    awake = run_same(a, b, [60.0, 300.0, 900.0, 1800.0, 3600.0], floor=8)
    assert awake[0] < awake[-1] == 16  # the flood reaches the end, and wakes the valley as it goes
    assert a.model.field("h")[a.axis, -20:].max() > 0.0


def test_a_tile_that_dries_sleeps_again_and_wakes_again() -> None:
    a, b = pair(tiles_y=2, tiles_x=8, strip=False)

    def source(v: Valley, mm_h: float, everywhere: bool = False) -> None:
        rate = np.zeros(v.grid.shape)
        rate[8:20, 200:215] = mm_h / 3.6e6
        if everywhere:
            rate[:] = mm_h / 3.6e6
        v.model.set_source(rate * v.grid.mask)

    both(a, b, lambda v: source(v, 40.0))
    assert a.awake() == 6  # the rained tile and its neighbours
    run_same(a, b, [120.0])
    assert a.model.volume() > 0.0
    both(a, b, lambda v: source(v, -4000.0, everywhere=True))  # a loss that takes every drop, wherever it ran to
    run_same(a, b, [600.0])
    assert a.model.volume() == 0.0
    both(a, b, lambda v: source(v, 0.0))
    assert a.awake() == 16  # a change of source drops no tile: only a check does
    run_same(a, b, [700.0, 1200.0])
    assert a.awake() == 0  # dry at two checks in a row, every tile left the list
    both(a, b, lambda v: source(v, 40.0))
    assert a.awake() == 6  # and the rained tile and its neighbours wake at once
    run_same(a, b, [1300.0, 1800.0])
    assert a.model.volume() > 0.0


# ---- the same on the GPU
@pytest.mark.gpu
def test_the_gpu_sleeps_and_gives_the_all_tiles_run() -> None:
    a, b = pair(tiles_y=2, tiles_x=8, strip=False, backend="gpu")
    both(a, b, Valley.open_end)
    both(a, b, lambda v: v.model.set_source(v.head(40.0)))
    awake = run_same(a, b, [30.0, 300.0, 1200.0, 3600.0], floor=8)
    assert awake[0] < awake[-1]
