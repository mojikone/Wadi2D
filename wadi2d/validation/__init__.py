"""Analytic validation cases: exact solutions, error metrics and the comparison a solver test runs."""

from wadi2d.validation.case import (
    Boundaries,
    Boundary,
    BoundaryKind,
    Case,
    Solution,
    State,
    Tolerance,
)
from wadi2d.validation.compare import Report, compare
from wadi2d.validation.grid import UniformGrid

__all__ = [
    "Boundaries",
    "Boundary",
    "BoundaryKind",
    "Case",
    "Report",
    "Solution",
    "State",
    "Tolerance",
    "UniformGrid",
    "compare",
]
