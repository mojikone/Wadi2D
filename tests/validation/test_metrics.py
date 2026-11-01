"""Metrics on identical fields give no error, and on hand-made fields the hand-made numbers."""

from __future__ import annotations

import math

import numpy as np
import pytest

from wadi2d.validation.metrics import (
    f_statistic,
    l1,
    linf,
    mass_balance_error,
    peak_error,
    rmse,
    timing_error,
    wet_union,
)

FIELD = np.array([[0.0, 0.5, 1.0], [2.0, 0.0, 3.0]])


@pytest.mark.parametrize("norm", [rmse, l1, linf])
def test_identical_fields_have_no_error(norm) -> None:
    assert norm(FIELD, FIELD) == 0.0
    assert norm(FIELD, FIELD, FIELD > 0.0) == 0.0


def test_identical_extents_give_f_of_one() -> None:
    wet = FIELD > 0.0
    assert f_statistic(wet, wet) == 1.0


def test_two_empty_extents_give_f_of_one() -> None:
    dry = np.zeros((2, 2), dtype=bool)
    assert f_statistic(dry, dry) == 1.0


def test_f_counts_intersection_over_union() -> None:
    model = np.array([True, True, True, False, False])
    reference = np.array([False, True, True, True, False])
    assert f_statistic(model, reference) == pytest.approx(2.0 / 4.0)


def test_norms_on_a_known_error() -> None:
    value = np.array([1.0, 2.0, 5.0, 9.0])
    reference = np.array([1.0, 1.0, 3.0, 0.0])
    wet = np.array([True, True, True, False])
    assert rmse(value, reference, wet) == pytest.approx(math.sqrt(5.0 / 3.0))
    assert l1(value, reference, wet) == pytest.approx(1.0)
    assert linf(value, reference, wet) == pytest.approx(2.0)
    assert linf(value, reference) == pytest.approx(9.0)


@pytest.mark.parametrize("norm", [rmse, l1, linf])
def test_no_wet_cells_mean_no_error(norm) -> None:
    assert norm(FIELD, FIELD + 1.0, np.zeros_like(FIELD, dtype=bool)) == 0.0


def test_wet_union_counts_both_fields() -> None:
    model = np.array([0.0, 0.5, 0.0])
    reference = np.array([0.0, 0.0, 0.5])
    assert wet_union(model, reference, 0.1).tolist() == [False, True, True]


def test_mass_balance() -> None:
    assert mass_balance_error(FIELD, FIELD, 4.0) == 0.0
    assert mass_balance_error(FIELD * 1.1, FIELD, 4.0) == pytest.approx(0.1)
    total = float(FIELD.sum()) * 4.0
    assert mass_balance_error(FIELD * 2.0, FIELD, 4.0, net_inflow_volume=total) == pytest.approx(0.0)
    assert mass_balance_error(np.ones(4), np.zeros(4), 2.0) == 8.0


def test_peak_and_timing() -> None:
    t = np.array([0.0, 10.0, 20.0, 30.0])
    reference = np.array([0.0, 100.0, 50.0, 0.0])
    model = np.array([0.0, 40.0, 110.0, 0.0])
    assert peak_error(reference, reference) == 0.0
    assert peak_error(model, reference) == pytest.approx(0.1)
    assert timing_error(t, reference, t, reference) == 0.0
    assert timing_error(t, model, t, reference) == pytest.approx(10.0)
