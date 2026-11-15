"""Sleeping tiles beside a strip of aligned cells (W90): a tile that holds squares the strip touches is no longer
stepped whatever the water does. It sleeps until water, the strip's or the squares', can reach it before the next
check, and the run is the run that steps every tile, to the last digit: every state array, the strip's too, the
step count and the time step. ``tests/solver/test_sleeping.py`` has the same on squares alone.
"""

from __future__ import annotations

import numpy as np
import pytest

from tests.strips.valley import HALF_WIDTH, Valley, both, pair, run_same, valley
from wadi2d.solver.layout import STRIDE2
from wadi2d.strips.watch import MARGIN, home_flags


def test_a_dry_strip_holds_no_tile_awake() -> None:
    a = valley(tiles_y=2, tiles_x=8)
    ghost_tiles = np.unique(a.hybrid.ghost // STRIDE2)
    assert ghost_tiles.size == 16  # every tile holds squares the strip touches
    assert a.awake() == 0
    a.advance(100.0)
    assert a.awake() == 0 and a.model.stepper.nsteps > 16


def test_a_flood_down_a_strip_wakes_the_tiles_ahead_of_it() -> None:
    a, b = pair(tiles_y=2, tiles_x=8)
    both(a, b, Valley.open_end)
    both(a, b, lambda v: v.model.set_source(v.head(40.0)))
    assert a.awake() < 16
    awake = run_same(a, b, [30.0, 120.0, 300.0, 600.0, 1200.0, 2400.0, 3600.0], floor=8)
    assert awake[0] < awake[-1] == 16
    assert float(np.abs(a.hybrid.strip_host("q")).max()) > 1.0  # the strip carried it
    assert a.model.field("h")[a.axis - HALF_WIDTH - 1, -20:].max() > 0.0  # and it reached the open end


def test_strips_that_stay_dry_hold_no_tile_awake_beside_a_flood_in_another() -> None:
    """Block 2's case: streams cross almost every tile and most stay dry. Before W90 every tile was stepped here."""
    kwargs = {"tiles_y": 6, "tiles_x": 4, "dry_strips": (-64, 64)}
    a, b = pair(**kwargs)
    ghost_tiles = np.unique(a.hybrid.ghost // STRIDE2)
    assert ghost_tiles.size == 24  # all of them hold squares a strip touches
    both(a, b, Valley.open_end)
    both(a, b, lambda v: v.model.set_source(v.head(40.0)))
    awake = run_same(a, b, [60.0, 300.0, 900.0, 1800.0])
    assert max(awake) == 20 < 24  # the flood's two rows of tiles and their neighbours, and the open end's columns
    assert float(np.abs(a.hybrid.strip_host("q")).max()) > 1.0


def test_still_water_across_the_join_and_dry_tiles_beyond() -> None:
    a, b = pair(tiles_y=2, tiles_x=8)

    def pond(v: Valley) -> None:
        h = np.zeros(v.grid.shape)
        h[v.axis - 8 : v.axis + 9, 215:240] = 0.8
        v.model.set_depth(h * v.grid.mask)
        _jj, ii = v.strip_cells
        v.hybrid.set_strip_depth(np.where((ii >= 215) & (ii < 240), 0.8, 0.0))

    both(a, b, pond)
    assert 0 < a.awake() < 16
    run_same(a, b, [30.0, 200.0, 600.0], floor=12)


ENDS = (4, 76)
"""A strip that ends in the sixth of eight tile columns, two short of the open end, whose tiles are always awake."""


def strip_rain(v: Valley) -> None:
    _jj, ii = v.strip_cells
    v.hybrid.set_strip_source(np.where((ii >= 60) & (ii < 80), 3000.0 / 3.6e6, 0.0))


def test_rain_on_a_sleeping_strip_runs_down_it_and_leaves_its_end_into_squares_that_slept() -> None:
    """The water never touches a square until the strip's end: only the strip's own wake rule can wake the tile
    there in time. Without it the end's squares take nothing and 400 m3 are missing (W90, ``mutations.py``)."""
    a, b = pair(tiles_y=2, tiles_x=8, strip_ends=ENDS)
    both(a, b, Valley.open_end)
    run_same(a, b, [50.0])
    quiet = a.awake()
    assert quiet == 4  # the open end's tiles and their neighbours
    both(a, b, strip_rain)
    assert quiet < a.awake() < 16
    awake = run_same(a, b, [80.0, 300.0, 900.0, 1800.0, 2700.0, 3600.0])
    end = a.grid.shape[1] - 1 - ENDS[1]
    assert a.model.field("h")[:, end:].max() > 0.0  # squares beyond the strip's end took its water
    assert awake[-1] > awake[0]
    assert a.hybrid.volume() == b.hybrid.volume()


def test_water_from_the_squares_runs_down_the_strip_to_sleeping_tiles() -> None:
    a, b = pair(tiles_y=2, tiles_x=8)

    def lake(v: Valley) -> None:
        h = np.zeros(v.grid.shape)
        h[6:26, 20:50] = 2.0  # on the hillside of the first tiles: it runs down to the axis and into the strip
        v.model.set_depth(h * v.grid.mask)

    both(a, b, lake)
    first = a.awake()
    assert first < 16
    awake = run_same(a, b, [20.0, 100.0, 300.0, 900.0, 1800.0])
    assert float(a.hybrid.strip_host("h")[: a.hybrid.nreal].max()) > 0.0
    assert awake[-1] > first


def test_the_watch_counts_reach_on_the_models_own_cells() -> None:
    a = valley(tiles_y=2, tiles_x=8)
    w = a.hybrid.watch
    assert w.reach == a.model.num.active_every + MARGIN
    nt = a.grid.ntiles
    # a strip cell wet in the fifth tile column wakes the tiles of that column and the columns beside it, no more
    _jj, ii = a.strip_cells
    h = np.where(ii == 4 * 32 + 16, 0.1, 0.0).astype(np.float32)
    flags = home_flags(np, h, np.zeros_like(h), w.home, nt)
    woken = w.tiles_to_wake(np.zeros(nt, bool), flags)
    columns = sorted({int(a.grid.tiles[t, 1]) for t in np.nonzero(woken)[0]})
    assert 4 in columns and min(columns) >= 3 and max(columns) <= 5
    # the reach is the count of cells: a wet strip cell further than the reach from a tile does not wake it
    for t in np.nonzero(woken)[0]:
        ti = int(a.grid.tiles[t, 1])
        gap = max(ti * 32 - (4 * 32 + 16), (4 * 32 + 16) - (ti * 32 + 31), 0)
        assert gap <= w.reach


# ---- the same on the GPU
@pytest.mark.gpu
def test_the_gpu_flood_down_a_strip_gives_the_all_tiles_run() -> None:
    a, b = pair(tiles_y=2, tiles_x=8, backend="gpu")
    both(a, b, Valley.open_end)
    both(a, b, lambda v: v.model.set_source(v.head(40.0)))
    awake = run_same(a, b, [30.0, 300.0, 1200.0, 3600.0], floor=8)
    assert awake[0] < awake[-1]


@pytest.mark.gpu
def test_the_gpu_rain_on_a_sleeping_strip_leaves_its_end_into_squares_that_slept() -> None:
    a, b = pair(tiles_y=2, tiles_x=8, strip_ends=ENDS, backend="gpu")
    both(a, b, Valley.open_end)
    run_same(a, b, [50.0])
    both(a, b, strip_rain)
    run_same(a, b, [80.0, 900.0, 1800.0, 2700.0, 3600.0])
    end = a.grid.shape[1] - 1 - ENDS[1]
    assert a.model.field("h")[:, end:].max() > 0.0
