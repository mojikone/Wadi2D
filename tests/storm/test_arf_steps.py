"""Storm areas placed by the change of the area-reduction factor between neighbouring runs (W53, his order of
2026-11-13): as few runs as keep every step within the limit, equal steps, no run a hair below the end."""

from __future__ import annotations

import math

import numpy as np
import pytest

from wadi2d.storm.arf import ArfTable

ARF_FM = ArfTable(
    np.array([1.0, 5.0, 10.0, 20.0, 30.0, 40.0, 50.0, 100.0, 200.0, 500.0, 1000.0, 2000.0]),
    np.array([0.999, 0.994, 0.987, 0.976, 0.965, 0.956, 0.948, 0.913, 0.864, 0.776, 0.694, 0.606]),
    reduces_below_table=False,
)
"""Block 2's ``ARF FM`` as the HMS project holds it."""


def steps(table: ArfTable, areas: list[float]) -> np.ndarray:
    return np.abs(np.diff([table.factor(a) for a in areas]))


@pytest.mark.parametrize(("limit", "runs"), [(0.05, 9), (0.02, 21), (0.01, 40)])
def test_every_neighbouring_pair_changes_the_factor_by_at_most_the_limit(limit, runs) -> None:
    areas = ARF_FM.step_areas(10.0, 2000.0, limit)
    assert len(areas) == runs == math.ceil((0.987 - 0.606) / limit) + 1
    assert areas[0] == 10.0 and areas[-1] == 2000.0
    assert np.all(np.diff(areas) > 0.0)
    found = steps(ARF_FM, areas)
    assert found.max() <= limit * (1.0 + 1e-12)
    assert found == pytest.approx(np.full(runs - 1, (0.987 - 0.606) / (runs - 1)), rel=1e-9), "equal steps"


def test_one_run_fewer_would_break_the_limit() -> None:
    """The fewest runs: the total change over the span cannot be covered in fewer steps of the limit."""
    for limit in (0.05, 0.02, 0.013):
        areas = ARF_FM.step_areas(10.0, 2000.0, limit)
        assert (0.987 - 0.606) / (len(areas) - 2) > limit


def test_no_run_sits_a_hair_below_the_end() -> None:
    """A greedy walk at 2 % places its last run at about 1,990 km2 before 2,000; equal steps never crowd an end."""
    areas = ARF_FM.step_areas(10.0, 2000.0, 0.02)
    assert areas[-1] / areas[-2] > 1.08
    assert areas[1] / areas[0] > 1.08


def test_the_factor_is_read_as_the_runs_read_it() -> None:
    """Linear in area, the reading that reproduces HMS's own log (0.974932 at 20.971 km2), so the bound holds on the
    factors the runs apply."""
    assert ARF_FM.factor(20.971) == pytest.approx(200.251 / 205.4, abs=5e-7)
    areas = ARF_FM.step_areas(10.0, 2000.0, 0.05)
    assert [round(a) for a in areas] == [10, 62, 143, 268, 430, 665, 956, 1459, 2000]
    assert ARF_FM.factor(areas[1]) == pytest.approx(0.987 - (0.987 - 0.606) / 8.0, abs=1e-12)


def test_todays_six_log_spaced_runs_step_the_factor_unevenly() -> None:
    """Why the rule: 6 log-spaced areas from 10 to 2,000 km2 step the factor by 2.1 % to 13.8 %."""
    found = steps(ARF_FM, list(np.geomspace(10.0, 2000.0, 6)))
    assert found.min() == pytest.approx(0.0207, abs=5e-4) and found.max() == pytest.approx(0.1383, abs=5e-4)


def test_one_area_or_a_flat_table_gives_one_or_two_runs() -> None:
    assert ARF_FM.step_areas(20.971, 20.971, 0.05) == [20.971]
    flat = ArfTable(np.array([1.0, 100.0]), np.array([0.9, 0.9]))
    assert flat.step_areas(10.0, 50.0, 0.05) == [10.0, 50.0]


def test_a_factor_that_rises_again_is_bounded_too() -> None:
    odd = ArfTable(np.array([1.0, 10.0, 100.0, 1000.0]), np.array([1.0, 0.8, 0.9, 0.5]))
    areas = odd.step_areas(1.0, 1000.0, 0.05)
    assert steps(odd, areas).max() <= 0.05 * (1.0 + 1e-12)
    assert len(areas) == math.ceil((0.2 + 0.1 + 0.4) / 0.05) + 1


def test_below_the_table_the_whole_depth_jumps_to_the_first_factor() -> None:
    """HMS leaves the depth whole below the first area: the jump of 0.001 at 1 km2 counts in the path."""
    areas = ARF_FM.step_areas(0.5, 50.0, 0.01)
    assert steps(ARF_FM, areas).max() <= 0.01 * (1.0 + 1e-12)
    assert ARF_FM.factor(areas[0]) == 1.0 and all(isinstance(a, float) for a in areas)


def test_a_limit_of_zero_is_refused() -> None:
    with pytest.raises(ValueError, match="above zero"):
        ARF_FM.step_areas(10.0, 2000.0, 0.0)
