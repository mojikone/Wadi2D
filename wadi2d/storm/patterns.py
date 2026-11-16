"""A storm pattern of the job as the storm builders take it. Interface: :func:`percent_pattern`, :func:`scs_curve`.

A pattern becomes a :class:`~wadi2d.storm.hypothetical.PercentPattern`, percent of the duration against percent of the
depth, which a :class:`~wadi2d.storm.hypothetical.HypotheticalStorm` interpolates linearly; a uniform pattern is None,
and the builder takes the constant-rate storm instead.

The NRCS 24-hour distributions are HEC-HMS 4.12's own tables (:mod:`wadi2d.storm.scs_tables`): the NRCS ordinates at
every 0.1 hour, carried to every minute on a natural cubic spline through them, which is how HMS's SCS Storm holds them
(its 1441 ordinates a minute to 5e-5, W98). Between the minutes the curve is linear. The 23 ordinates W95 typed from
memory were up to 0.0285 off and are gone.
"""

from __future__ import annotations

from functools import cache

import numpy as np

from wadi2d.config.rain import PATTERN_SCS, PATTERN_UNIFORM, PatternTable, StormPattern
from wadi2d.storm.base import PERCENT
from wadi2d.storm.hypothetical import PercentPattern
from wadi2d.storm.scs_tables import SCS_KNOT_HOURS, SCS_KNOTS

SCS_SPAN_H = 24.0
MINUTES_PER_HOUR = 60.0
SCS_STEP_MIN = 1.0
"""The curve is read every minute, as HMS holds it."""
TIME_SCALE_PERCENT = {"percent": 1.0, "fraction": PERCENT}
"""What turns a relative time into percent of the duration."""


@cache
def scs_curve(scs_type: str) -> tuple[np.ndarray, np.ndarray]:
    """Minutes from 0 to 1440 and the fraction of the 24-hour depth fallen by each, for one NRCS type: a natural
    cubic spline through the 0.1-hour ordinates, as HEC-HMS 4.12 holds the curve."""
    from scipy.interpolate import CubicSpline

    knots = np.asarray(SCS_KNOTS[scs_type], np.float64)
    at = np.arange(knots.size) * SCS_KNOT_HOURS * MINUTES_PER_HOUR
    minutes = np.arange(0.0, SCS_SPAN_H * MINUTES_PER_HOUR + SCS_STEP_MIN / 2.0, SCS_STEP_MIN)
    fraction = CubicSpline(at, knots, bc_type="natural")(minutes)
    fraction[:: round(SCS_KNOT_HOURS * MINUTES_PER_HOUR / SCS_STEP_MIN)] = knots  # the table itself, to the digit
    fraction.setflags(write=False)
    minutes.setflags(write=False)
    return minutes, fraction


def table_pattern(table: PatternTable, duration_min: float) -> PercentPattern:
    """A stored or given table as percent of the duration against percent of the depth."""
    time = np.asarray(table.time, np.float64)
    depth = np.asarray(table.depth, np.float64)
    if table.time_units in TIME_SCALE_PERCENT:
        time = time * TIME_SCALE_PERCENT[table.time_units]
    else:
        minutes = time * (MINUTES_PER_HOUR if table.time_units == "hours" else 1.0)
        time = minutes / duration_min * PERCENT
    if table.form == "incremental":
        time = np.concatenate(([0.0], time))
        depth = np.concatenate(([0.0], np.cumsum(depth)))
    return PercentPattern(time, depth / depth[-1] * PERCENT)


def percent_pattern(pattern: StormPattern | None, duration_min: float) -> PercentPattern | None:
    """The pattern a storm builder takes; None for a uniform rate."""
    if pattern is None or pattern.kind == PATTERN_UNIFORM:
        return None
    if pattern.kind == PATTERN_SCS:
        minutes, fraction = scs_curve(pattern.scs_type)
        return PercentPattern(minutes / (SCS_SPAN_H * MINUTES_PER_HOUR) * PERCENT, fraction * PERCENT)
    if pattern.values is None:
        raise ValueError(f"storm.pattern names {pattern.table!r} but holds no numbers: read the job through load_job")
    return table_pattern(pattern.values, duration_min)
