"""The conserving Muskingum-Cunge (Todini 2007) beside the HMS path; no data folder needed."""

from __future__ import annotations

import numpy as np
import pytest

from tests.engine.test_handback import MC_REACH, SINK, write_basin
from wadi2d.config.schema import REACH_CONSERVING, REACH_HMS
from wadi2d.hms import load_basin
from wadi2d.hydrology import ROUTING_METHODS
from wadi2d.hydrology.from_hms import basin_from_hms
from wadi2d.hydrology.routing import (
    CONSERVING_FLOW_FLOOR,
    CONSERVING_MIN_VELOCITY,
    HMS_DEPTH_TOLERANCE,
    MUSKINGUM_CUNGE,
    MuskingumCunge,
)
from wadi2d.hydrology.routing_conserving import corrected_numbers, storage_weights

TEST_REACH = (3000.0, 0.01, 0.04, 10.0, 1.0, 2.0)
"""The hand-back test reach: 3 km, 1 %, n 0.04, 10 m wide, 1:1 banks, index celerity 2 m/s."""
BLOCK2_R1 = (26008.98, 0.01241, 0.1, 60.0, 0.7, 1.524)
BLOCK2_R6 = (4259.46, 0.01474, 0.1, 50.0, 1.0, 1.524)
IDENTITY = 1e-9
"""Round-off on the volume identity, as a share of the inflow volume."""
DRAINED = 1e-4
"""What out / in must reach once the tail has drained."""
DIP = 2e-4
"""The largest dip found, as a share of the peak: on the test reach when 800 m3/s fall to zero within two 5-minute
steps and C* reaches 2.5, the region where any Muskingum-Cunge weights the old outflow negatively (W29). Everywhere
else the floor of the outflow is round-off."""
TAIL_HOURS = 160.0
"""Long enough for R1 to drain its trickle: the velocity floor sets that time (W29)."""


def hms(reach: tuple = TEST_REACH) -> MuskingumCunge:
    return MuskingumCunge(*reach)


def conserving(reach: tuple = TEST_REACH) -> MuskingumCunge:
    return MuskingumCunge(*reach, scheme=REACH_CONSERVING)


def triangle(peak: float, dt_min: float, base_min: float = 20.0, tail_hours: float = TAIL_HOURS) -> np.ndarray:
    """A flood from zero to zero over ``base_min``, then a dry tail; the W25 short flood."""
    t = np.arange(int(tail_hours * 60.0 / dt_min) + 1) * dt_min
    return np.interp(t, [0.0, 0.5 * base_min, base_min], [0.0, peak, 0.0])


def volume(series: np.ndarray, dt_min: float) -> float:
    return float(np.trapezoid(series)) * dt_min * 60.0


@pytest.mark.parametrize("reach", [TEST_REACH, BLOCK2_R1, BLOCK2_R6], ids=["test", "R1", "R6"])
@pytest.mark.parametrize("peak", [8.0, 80.0, 800.0])
@pytest.mark.parametrize("dt_min", [1.0, 5.0])
def test_inflow_volume_equals_outflow_plus_storage_to_round_off_and_the_tail_drains(
    reach: tuple, peak: float, dt_min: float
) -> None:
    inflow = triangle(peak, dt_min)
    outflow, storage = conserving(reach).route_conserving(inflow, dt_min)
    entered = volume(inflow, dt_min)
    assert abs(entered - volume(outflow, dt_min) - storage) < IDENTITY * entered
    assert abs(volume(outflow, dt_min) / entered - 1.0) < DRAINED
    assert outflow.min() >= -DIP * inflow.max()


def test_the_hms_path_gains_or_loses_volume_on_the_short_flood_where_the_conserving_one_does_not() -> None:
    """The W25 finding, kept as the reason the option exists."""
    inflow = triangle(80.0, 5.0)
    gained = volume(hms(BLOCK2_R1).route(inflow, 5.0), 5.0) / volume(inflow, 5.0)
    assert gained > 1.5
    assert abs(volume(conserving(BLOCK2_R1).route(inflow, 5.0), 5.0) / volume(inflow, 5.0) - 1.0) < DRAINED


def test_steady_flow_passes_unchanged() -> None:
    inflow = np.full(100, 250.0)
    assert conserving().route(inflow, 5.0) == pytest.approx(inflow, rel=1e-9)


def test_the_flood_is_delayed_attenuated_and_never_negative() -> None:
    inflow = 400.0 * np.exp(-(((np.arange(500) - 120.0) / 30.0) ** 2))
    outflow = conserving().route(inflow, 5.0)
    assert outflow.max() < inflow.max()
    assert np.argmax(outflow) > np.argmax(inflow)
    assert outflow.min() >= -DIP * inflow.max()


def test_route_returns_the_conserving_outflow_only_and_route_conserving_the_storage_too() -> None:
    inflow = triangle(80.0, 1.0, tail_hours=1.0)
    outflow, storage = conserving().route_conserving(inflow, 1.0)
    np.testing.assert_array_equal(conserving().route(inflow, 1.0), outflow)
    assert storage > 0.0  # an hour in, the reach still holds some of the flood


def test_the_scheme_is_a_field_with_the_hms_default_and_the_registry_takes_it() -> None:
    assert hms().scheme == REACH_HMS
    length, slope, n, width, side, celerity = TEST_REACH
    built = ROUTING_METHODS.build(
        MUSKINGUM_CUNGE, length_m=length, slope=slope, roughness=n, bottom_width_m=width, side_slope=side,
        index_celerity=celerity, scheme=REACH_CONSERVING,
    )  # fmt: skip
    assert isinstance(built, MuskingumCunge) and built.scheme == REACH_CONSERVING
    with pytest.raises(ValueError, match="reach routing scheme"):
        MuskingumCunge(*TEST_REACH, scheme="todini")


def test_the_hms_path_does_not_read_the_scheme_field() -> None:
    """Bit for bit: the HMS kernel is called with the same arguments whatever the field is called."""
    inflow = triangle(80.0, 5.0, tail_hours=4.0)
    np.testing.assert_array_equal(hms().route(inflow, 5.0), MuskingumCunge(*TEST_REACH, scheme=REACH_HMS).route(inflow, 5.0))
    assert not np.array_equal(hms().route(inflow, 5.0), conserving().route(inflow, 5.0))


def test_the_diffusion_floor_keeps_the_new_inflow_weight_from_going_negative() -> None:
    dt = 300.0
    for courant, reynolds in [(0.02, 0.0), (0.3, 0.02), (0.9, 0.05), (1.4, 0.2)]:
        wedge, prism = storage_weights(courant, reynolds, dt)
        assert 2.0 * wedge <= dt * (1.0 + 1e-12)  # C1 = (dt - 2 [k e]) / (...) >= 0
        assert prism >= wedge
    # above C* + D* = 1 the numbers are Todini's own: k* (1 -+ D*) / 2 with k* = dt / C*
    wedge, prism = storage_weights(1.4, 0.2, dt)
    assert (wedge, prism) == pytest.approx((dt / 1.4 * 0.8 / 2.0, dt / 1.4 * 1.2 / 2.0))


def test_the_velocity_floor_bounds_the_travel_time_of_a_trickle_and_not_of_the_flood() -> None:
    _length, slope, n, width, side, _celerity = BLOCK2_R1
    dx, dt = 456.3, 300.0
    conveyance = slope**0.5 / n
    trickle = corrected_numbers(0.001, dt, dx, width, side, slope, conveyance, 1.0, 20, HMS_DEPTH_TOLERANCE,
                                CONSERVING_FLOW_FLOOR, CONSERVING_MIN_VELOCITY)  # fmt: skip
    assert trickle[0] == pytest.approx(CONSERVING_MIN_VELOCITY * dt / dx)
    flood = corrected_numbers(1000.0, dt, dx, width, side, slope, conveyance, 1.0, 20, HMS_DEPTH_TOLERANCE,
                              CONSERVING_FLOW_FLOOR, CONSERVING_MIN_VELOCITY)  # fmt: skip
    depth = flood[2]
    area = (width + side * depth) * depth
    assert flood[0] == pytest.approx(1000.0 / area * dt / dx)  # C* = v dt / dx, the parcel speed, not the celerity
    assert 0.0 < flood[1] < 1.0


def test_basin_from_hms_gives_every_reach_the_scheme_asked(tmp_path) -> None:
    basin = load_basin(write_basin(tmp_path, MC_REACH, SINK))
    assert basin_from_hms(basin).elements["R1"].routing.scheme == REACH_HMS
    assert basin_from_hms(basin, reach_routing=REACH_CONSERVING).elements["R1"].routing.scheme == REACH_CONSERVING
