"""Reach routing; no data folder needed."""

from __future__ import annotations

import cmath
import math

import numpy as np
import pytest

from wadi2d.hydrology import ROUTING_METHODS
from wadi2d.hydrology.routing import HMS_LOW_FLOW, LagRouting, MuskingumCunge, NoRouting
from wadi2d.hydrology.routing_kernel import muskingum_coefficients

BLOCK2_INDEX_CELERITY = 1.524
BLOCK2_STEP_SECONDS = 300.0


def reach(length: float = 9000.0, width: float = 60.0) -> MuskingumCunge:
    return MuskingumCunge(
        length_m=length,
        slope=0.012,
        roughness=0.1,
        bottom_width_m=width,
        side_slope=1.5,
        index_celerity=BLOCK2_INDEX_CELERITY,
    )


def flood(n_times: int = 500, peak: float = 400.0, centre: float = 120.0, spread: float = 30.0) -> np.ndarray:
    return peak * np.exp(-(((np.arange(n_times) - centre) / spread) ** 2))


@pytest.mark.parametrize(
    ("length", "logged_dx"),
    [
        (26008.98, 456.2979),
        (9427.58, 448.9324),
        (4259.46, 425.9460),
        (659.62, 329.8100),
        (17006.85, 447.5487),
    ],
)
def test_cell_length_is_what_the_hms_log_prints(length: float, logged_dx: float) -> None:
    _cells, dx, substeps = reach(length).grid(BLOCK2_STEP_SECONDS)
    assert dx == pytest.approx(logged_dx, abs=1e-3)
    assert substeps == 1


def test_a_reach_shorter_than_a_step_of_wave_travel_divides_the_step() -> None:
    cells, dx, substeps = reach(200.0).grid(BLOCK2_STEP_SECONDS)
    assert (cells, dx, substeps) == (1, 200.0, 2)
    outflow = reach(200.0).route(flood(), 5.0)
    assert len(outflow) == len(flood())


def test_coefficients_sum_to_one_in_both_forms() -> None:
    for courant, reynolds in [(1.0, 0.1), (2.1, 0.26), (0.4, 0.03)]:
        assert sum(muskingum_coefficients(courant, reynolds)) == pytest.approx(1.0)


def test_constant_parameter_scheme_matches_the_exact_damped_sinusoid() -> None:
    """Advection-diffusion, Q(x, t) = Q0 + a exp(i (w t - k x)); Courant 1 on the third-order grid."""
    celerity, diffusivity, period = 2.0, 100.0, 21600.0
    omega = 2.0 * math.pi / period
    dx, dt = 500.0, 250.0
    courant, reynolds = celerity * dt / dx, 2.0 * diffusivity / (celerity * dx)
    weights = muskingum_coefficients(courant, reynolds)
    n_cells = 40
    base, amplitude = 100.0, 10.0
    times = np.arange(0.0, 8.0 * period, dt)
    upstream = base + amplitude * np.sin(omega * times)
    for _ in range(n_cells):
        outflow = np.empty_like(upstream)
        outflow[0] = upstream[0]
        for step in range(1, len(times)):
            outflow[step] = (
                weights[0] * upstream[step - 1] + weights[1] * upstream[step] + weights[2] * outflow[step - 1]
            )
        upstream = outflow
    root = cmath.sqrt(complex(-(celerity**2), -4.0 * omega * diffusivity))
    wavenumber = next(
        k for k in ((1j * celerity + s * root) / (2.0 * diffusivity) for s in (1, -1)) if k.imag < 0.0
    )
    distance = n_cells * dx
    exact = amplitude * cmath.exp(-1j * wavenumber * distance) * np.exp(1j * omega * times)
    tail = times > 4.0 * period
    assert np.max(np.abs(upstream[tail] - base - exact.imag[tail])) < 0.002 * amplitude


def test_steady_flow_passes_unchanged() -> None:
    inflow = np.full(100, 250.0)
    assert reach().route(inflow, 5.0) == pytest.approx(inflow, rel=1e-9)


def test_volume_is_conserved_and_the_flood_is_delayed_and_attenuated() -> None:
    inflow = flood()
    outflow = reach().route(inflow, 5.0)
    assert outflow.sum() == pytest.approx(inflow.sum(), rel=2e-3)
    assert outflow.max() < inflow.max()
    assert np.argmax(outflow) > np.argmax(inflow)


def test_outflow_is_never_negative_at_the_wave_front() -> None:
    assert reach().route(flood(spread=6.0), 5.0).min() >= 0.0


def test_below_the_low_flow_threshold_the_outflow_is_the_three_point_mean() -> None:
    """Six steps of R5 at the wave front of DA 100yr B1: inflow and outflow as HMS stored them."""
    hms_inflow = np.array([0.00000358, 0.00015945, 0.00083799, 0.00266495, 0.00649452, 0.01336460])
    hms_outflow = np.array([0.0, 0.00001865, 0.00014137, 0.00059222, 0.00178604, 0.00434918])
    assert hms_outflow.max() < HMS_LOW_FLOW
    channel = MuskingumCunge(659.62, 0.00945, 0.1, 100.0, 5.0, BLOCK2_INDEX_CELERITY)
    outflow = channel.route(np.r_[0.0, hms_inflow], 5.0)[1:]
    assert outflow == pytest.approx(hms_outflow, abs=5.0e-7)


def test_lag_shifts_the_inflow_and_interpolates_between_steps() -> None:
    inflow = np.array([0.0, 0.0, 10.0, 20.0, 10.0, 0.0, 0.0])
    assert LagRouting(10.0).route(inflow, 5.0) == pytest.approx([0.0, 0.0, 0.0, 0.0, 10.0, 20.0, 10.0])
    assert LagRouting(2.5).route(inflow, 5.0)[3] == pytest.approx(15.0)


def test_no_routing_and_the_registry() -> None:
    inflow = np.ones(3)
    assert NoRouting().route(inflow, 5.0) is inflow
    built = ROUTING_METHODS.build("Lag", lag_minutes=5.0)
    assert isinstance(built, LagRouting)
