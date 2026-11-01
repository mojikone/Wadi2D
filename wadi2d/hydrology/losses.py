"""Rainfall losses. Interface: :class:`LossMethod`, :data:`LOSS_METHODS`.

A loss method turns period-ending precipitation (mm per step) into period-ending excess. The SCS method keeps
the cumulative-difference form of HMS (research note H01, algorithm A): an infiltration-rate form does not
replicate it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from wadi2d.hydrology.constants import MM_PER_INCH, PERCENT
from wadi2d.storm.base import FloatArray
from wadi2d.storm.registry import Registry

SCS_CN = "SCS"
NO_LOSS = "None"
CN_NUMERATOR = 1000.0
CN_OFFSET = 10.0
DEFAULT_IA_RATIO = 0.2


class LossMethod(Protocol):
    """A loss model of one subbasin."""

    def excess(self, precipitation_mm: FloatArray) -> FloatArray:
        """The excess of each step, mm."""
        ...


LOSS_METHODS: Registry[LossMethod] = Registry("loss")


@LOSS_METHODS.register(NO_LOSS)
@dataclass(frozen=True)
class NoLoss:
    """All rainfall is excess."""

    def excess(self, precipitation_mm: FloatArray) -> FloatArray:
        """The excess of each step, mm."""
        return precipitation_mm.copy()


@LOSS_METHODS.register(SCS_CN)
@dataclass(frozen=True)
class ScsCurveNumber:
    """SCS curve number. ``initial_abstraction_mm`` is a depth, as stored in the ``.basin``; None means 0.2 S."""

    curve_number: float
    initial_abstraction_mm: float | None = None
    percent_impervious: float = 0.0

    @property
    def retention_mm(self) -> float:
        """Potential maximum retention S, mm."""
        return (CN_NUMERATOR / self.curve_number - CN_OFFSET) * MM_PER_INCH

    @property
    def abstraction_mm(self) -> float:
        """Initial abstraction Ia, mm."""
        if self.initial_abstraction_mm is None:
            return DEFAULT_IA_RATIO * self.retention_mm
        return self.initial_abstraction_mm

    def cumulative_excess(self, cumulative_mm: FloatArray) -> FloatArray:
        """Pervious excess Pe(P) = (P - Ia)^2 / (P - Ia + S), zero up to Ia."""
        effective = np.maximum(cumulative_mm - self.abstraction_mm, 0.0)
        return effective**2 / (effective + self.retention_mm)

    def excess(self, precipitation_mm: FloatArray) -> FloatArray:
        """The excess of each step: the difference of cumulative excess, impervious rain passing whole."""
        pervious = np.diff(self.cumulative_excess(np.cumsum(precipitation_mm)), prepend=0.0)
        impervious = self.percent_impervious / PERCENT
        return (1.0 - impervious) * pervious + impervious * precipitation_mm
