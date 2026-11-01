"""Losses, unit hydrographs and baseflow; no data folder needed."""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from wadi2d.hydrology import BASEFLOW_METHODS, LOSS_METHODS, TRANSFORM_METHODS
from wadi2d.hydrology.baseflow import NoBaseflow, RecessionBaseflow
from wadi2d.hydrology.constants import M3_PER_MM_KM2, SECONDS_PER_MINUTE
from wadi2d.hydrology.losses import NoLoss, ScsCurveNumber
from wadi2d.hydrology.transforms import ClarkUnitHydrograph, ScsUnitHydrograph, convolve

RAIN = np.array([1.0, 3.0, 12.0, 30.0, 12.0, 3.0, 1.0, 0.0])


def carried_mm(ordinates: np.ndarray, area_km2: float, dt_minutes: float) -> float:
    return float(ordinates.sum() * dt_minutes * SECONDS_PER_MINUTE / (area_km2 * M3_PER_MM_KM2))


@pytest.mark.parametrize("cn", [55.0, 70.0, 85.0, 95.0])
def test_excess_never_exceeds_rain_and_the_balance_closes(cn: float) -> None:
    excess = ScsCurveNumber(cn).excess(RAIN)
    assert np.all(excess >= 0.0)
    assert np.all(excess <= RAIN + 1e-12)


def test_excess_rises_with_curve_number() -> None:
    totals = [ScsCurveNumber(cn).excess(RAIN).sum() for cn in (60.0, 70.0, 80.0, 90.0, 98.0)]
    assert all(low < high for low, high in itertools.pairwise(totals))


def test_nothing_runs_off_before_the_initial_abstraction() -> None:
    loss = ScsCurveNumber(90.0, initial_abstraction_mm=10.0)
    assert loss.excess(np.array([3.0, 3.0, 3.0])).sum() == 0.0


def test_abstraction_defaults_to_a_fifth_of_the_retention() -> None:
    loss = ScsCurveNumber(90.0)
    assert loss.retention_mm == pytest.approx(25400.0 / 90.0 - 254.0)
    assert loss.abstraction_mm == pytest.approx(0.2 * loss.retention_mm)


def test_the_cumulative_form_does_not_depend_on_how_the_rain_is_split() -> None:
    loss = ScsCurveNumber(85.0, initial_abstraction_mm=7.0)
    assert loss.excess(np.full(40, 2.5)).sum() == pytest.approx(loss.excess(np.array([100.0])).sum())


def test_impervious_rain_runs_off_whole() -> None:
    assert ScsCurveNumber(60.0, percent_impervious=100.0).excess(RAIN) == pytest.approx(RAIN)


def test_no_loss_passes_the_rain() -> None:
    assert NoLoss().excess(RAIN) == pytest.approx(RAIN)
    assert isinstance(LOSS_METHODS.build("SCS", curve_number=80.0), ScsCurveNumber)


@pytest.mark.parametrize(("lag", "dt"), [(31.5, 5.0), (112.0, 5.0), (157.0, 5.0), (60.0, 15.0), (20.0, 1.0)])
def test_scs_unit_hydrograph_carries_one_millimetre(lag: float, dt: float) -> None:
    ordinates = ScsUnitHydrograph(lag).unit_hydrograph(59.078, dt)
    assert carried_mm(ordinates, 59.078, dt) == pytest.approx(1.0, abs=1e-12)
    assert np.all(ordinates >= 0.0)


def test_scs_unit_hydrograph_peaks_at_half_step_plus_lag() -> None:
    lag, dt = 112.0, 5.0
    ordinates = ScsUnitHydrograph(lag).unit_hydrograph(59.078, dt)
    assert dt * (int(np.argmax(ordinates)) + 1) == pytest.approx(lag + dt / 2.0, abs=dt)


def test_scs_peak_is_near_the_standard_peak_rate() -> None:
    area, lag, dt = 59.078, 112.0, 5.0
    ordinates = ScsUnitHydrograph(lag).unit_hydrograph(area, dt)
    standard = 0.75 * area * M3_PER_MM_KM2 / ((lag + dt / 2.0) * SECONDS_PER_MINUTE)
    assert ordinates.max() == pytest.approx(standard, rel=0.005)


@pytest.mark.parametrize(("tc", "storage"), [(120.0, 60.0), (60.0, 90.0), (240.0, 15.0)])
def test_clark_unit_hydrograph_carries_one_millimetre(tc: float, storage: float) -> None:
    ordinates = ClarkUnitHydrograph(tc, storage).unit_hydrograph(25.0, 5.0)
    assert carried_mm(ordinates, 25.0, 5.0) == pytest.approx(1.0, abs=1e-12)


def test_clark_refuses_a_step_of_twice_the_storage() -> None:
    with pytest.raises(ValueError, match="dt < 2 R"):
        ClarkUnitHydrograph(120.0, 2.0).unit_hydrograph(25.0, 5.0)


def test_clark_is_in_the_registry() -> None:
    method = TRANSFORM_METHODS.build(
        "Clark", time_of_concentration_minutes=60.0, storage_coefficient_minutes=30.0
    )
    assert isinstance(method, ClarkUnitHydrograph)


def test_convolution_starts_with_the_first_ordinate_at_the_end_of_the_excess_period() -> None:
    flow = convolve(np.array([2.0, 0.0, 0.0]), np.array([1.0, 3.0]), 5)
    assert flow == pytest.approx([0.0, 2.0, 6.0, 0.0, 0.0])


def test_convolution_conserves_volume_when_the_run_is_long_enough() -> None:
    area, dt = 12.0, 5.0
    ordinates = ScsUnitHydrograph(30.0).unit_hydrograph(area, dt)
    flow = convolve(RAIN, ordinates, 400)
    assert carried_mm(flow, area, dt) == pytest.approx(RAIN.sum())


def test_no_baseflow_is_the_direct_runoff() -> None:
    direct = np.array([0.0, 2.0, 1.0])
    assert NoBaseflow().total_flow(direct, 5.0, 10.0) is direct
    assert "Recession" in BASEFLOW_METHODS


def test_recession_decays_the_initial_flow_at_the_daily_constant() -> None:
    baseflow = RecessionBaseflow(recession_constant=0.5, initial_m3s_km2=0.1, threshold_ratio=0.1)
    total = baseflow.total_flow(np.zeros(25), 60.0, 10.0)
    assert total[0] == pytest.approx(1.0)
    assert total[24] == pytest.approx(0.5)


def test_recession_takes_over_below_the_threshold_of_the_peak() -> None:
    baseflow = RecessionBaseflow(recession_constant=0.5, initial_m3s_km2=0.0, threshold_ratio=0.5)
    direct = np.array([0.0, 100.0, 40.0, 0.0, 0.0])
    total = baseflow.total_flow(direct, 1440.0, 1.0)
    assert total == pytest.approx([0.0, 100.0, 40.0, 20.0, 10.0])
