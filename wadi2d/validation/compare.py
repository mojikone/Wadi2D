"""Compare a modelled state with a case and report the numbers and a pass or fail."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wadi2d.validation.case import Case, State, Tolerance
from wadi2d.validation.grid import FloatArray
from wadi2d.validation.metrics import f_statistic, l1, linf, mass_balance_error, rmse, wet_union


@dataclass(frozen=True)
class Report:
    """The numbers of one comparison; ``failures`` names every limit the state missed."""

    case: str
    t: float
    depth_rmse: float
    depth_l1: float
    depth_linf: float
    discharge_rmse: float
    discharge_l1: float
    discharge_linf: float
    surface_rmse: float
    f_statistic: float
    volume_error: float
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """True when the state is within every limit of the case tolerance."""
        return not self.failures


def _failures(numbers: dict[str, float], tolerance: Tolerance) -> tuple[str, ...]:
    """The tolerance checks, as messages. Error limits bound the magnitude; F is a lower bound."""
    failures = []
    for name in ("depth_rmse", "depth_linf", "discharge_rmse", "discharge_linf", "surface_rmse"):
        limit = getattr(tolerance, name)
        if limit is not None and numbers[name] > limit:
            failures.append(f"{name} {numbers[name]:.4g} > {limit:.4g}")
    if tolerance.volume is not None and abs(numbers["volume_error"]) > tolerance.volume:
        failures.append(f"volume_error {numbers['volume_error']:.4g} beyond {tolerance.volume:.4g}")
    if tolerance.f_statistic is not None and numbers["f_statistic"] < tolerance.f_statistic:
        failures.append(f"f_statistic {numbers['f_statistic']:.4f} < {tolerance.f_statistic:.4f}")
    return tuple(failures)


def compare(state: State, case: Case, t: float, *, surface: FloatArray | None = None) -> Report:
    """Measure ``state`` against the exact state of ``case`` at time ``t``.

    Norms run over the cells wet in either field. The volume is checked against the initial volume when the
    domain is closed and against the exact volume otherwise. ``surface`` is the modelled water surface; give
    it when depth plus bed at the cell centre is not that surface, as in a sub-grid run.
    """
    exact = case.exact(t)
    if state.h.shape != exact.h.shape:
        raise ValueError(f"state shape {state.h.shape} does not match the case grid {exact.h.shape}")
    threshold = case.tolerance.wet_depth
    wet = wet_union(state.h, exact.h, threshold)
    discharge_error = np.hypot(state.qx - exact.qx, state.qy - exact.qy)
    no_error = np.zeros_like(discharge_error)
    modelled_surface = state.h + case.bed() if surface is None else surface
    volume_reference = case.initial().h if case.boundaries.is_closed else exact.h
    numbers = {
        "depth_rmse": rmse(state.h, exact.h, wet),
        "depth_l1": l1(state.h, exact.h, wet),
        "depth_linf": linf(state.h, exact.h, wet),
        "discharge_rmse": rmse(discharge_error, no_error, wet),
        "discharge_l1": l1(discharge_error, no_error, wet),
        "discharge_linf": linf(discharge_error, no_error, wet),
        "surface_rmse": rmse(modelled_surface, case.surface(t), wet),
        "f_statistic": f_statistic(state.h > threshold, exact.h > threshold),
        "volume_error": mass_balance_error(state.h, volume_reference, case.grid.cell_area),
    }
    return Report(case=case.name, t=t, failures=_failures(numbers, case.tolerance), **numbers)
