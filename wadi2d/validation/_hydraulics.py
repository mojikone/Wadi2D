"""One-dimensional open-channel relations shared by the case modules (Chow 1959; Henderson 1966)."""

from __future__ import annotations

import math

import numpy as np
from scipy.optimize import brentq

from wadi2d.validation._constants import STEADY_SPINUP_TRAVERSALS, G
from wadi2d.validation.grid import FloatArray

type Depth = float | FloatArray


def friction_slope(q: float, h: Depth, n: float) -> Depth:
    """Manning friction slope of a wide channel, ``n^2 q^2 / h^(10/3)``."""
    return n * n * q * q / h ** (10.0 / 3.0)


def critical_depth(q: float) -> float:
    """Critical depth for unit discharge ``q``."""
    return (q * q / G) ** (1.0 / 3.0)


def froude(q: float, h: Depth) -> Depth:
    """Froude number of unit discharge ``q`` at depth ``h``."""
    return q / (h * np.sqrt(G * h))


def specific_energy(q: float, h: Depth) -> Depth:
    """Specific energy ``h + q^2 / (2 g h^2)``, m."""
    return h + q * q / (2.0 * G * h * h)


def specific_force(q: float, h: Depth) -> Depth:
    """Momentum function ``q^2 / h + g h^2 / 2`` per unit width and density, m3/s2."""
    return q * q / h + 0.5 * G * h * h


def sequent_depth(q: float, h: float) -> float:
    """Depth conjugate to ``h`` across a hydraulic jump (Belanger)."""
    return 0.5 * h * (math.sqrt(1.0 + 8.0 * float(froude(q, h)) ** 2) - 1.0)


def depth_from_energy(q: float, energy: float, *, subcritical: bool) -> float:
    """The depth carrying ``q`` at specific energy ``energy``, on the chosen side of critical."""
    hc = critical_depth(q)
    if energy < specific_energy(q, hc):
        raise ValueError(f"energy {energy} m is below the minimum for q = {q} m2/s")
    if subcritical:
        return float(brentq(lambda h: specific_energy(q, h) - energy, hc, energy))
    jet_depth = q / math.sqrt(2.0 * G * energy)
    return float(brentq(lambda h: specific_energy(q, h) - energy, jet_depth, hc))


def spinup_time(length: float, depth: float) -> float:
    """Time for a steady case to settle: repeated traversals of ``length`` by a long wave of ``depth``."""
    return STEADY_SPINUP_TRAVERSALS * length / math.sqrt(G * depth)
