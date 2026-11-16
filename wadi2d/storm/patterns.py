"""A storm pattern of the job as the storm builders take it. Interface: :func:`percent_pattern`, :data:`SCS_CURVES`.

A pattern becomes a :class:`~wadi2d.storm.hypothetical.PercentPattern`, percent of the duration against percent of the
depth, which a :class:`~wadi2d.storm.hypothetical.HypotheticalStorm` interpolates linearly; a uniform pattern is None,
and the builder takes the constant-rate storm instead.

The NRCS 24-hour distributions are the abbreviated TR-20 tables at 23 times, as reproduced in TR-55-era manuals
[Likely: written from that published table; not yet checked against NEH 630 chapter 4's finer 0.1 h tables or against
HEC-HMS's SCS Storm, which interpolates its own tables]. Between the times the curve is linear.
"""

from __future__ import annotations

import numpy as np

from wadi2d.config.rain import PATTERN_SCS, PATTERN_UNIFORM, PatternTable, StormPattern
from wadi2d.storm.base import PERCENT
from wadi2d.storm.hypothetical import PercentPattern

SCS_HOURS = (0, 2, 4, 6, 7, 8, 8.5, 9, 9.5, 9.75, 10, 10.5, 11, 11.5, 11.75, 12, 12.5, 13, 13.5, 14, 16, 20, 24)
SCS_CURVES = {
    "I": (0, .035, .076, .125, .156, .194, .219, .254, .303, .362, .515, .583, .624, .654, .669, .682, .706, .727,
          .748, .767, .830, .926, 1.0),
    "IA": (0, .050, .116, .206, .268, .425, .480, .520, .550, .564, .577, .601, .624, .645, .655, .664, .683, .701,
           .719, .736, .800, .906, 1.0),
    "II": (0, .022, .048, .080, .098, .120, .133, .147, .163, .172, .181, .204, .235, .283, .357, .663, .735, .772,
           .799, .820, .880, .952, 1.0),
    "III": (0, .020, .043, .072, .089, .115, .130, .148, .167, .178, .189, .216, .250, .298, .339, .500, .702, .751,
            .785, .811, .886, .957, 1.0),
}  # fmt: skip
"""Fraction of the 24-hour depth fallen by each of :data:`SCS_HOURS`."""
SCS_SPAN_H = 24.0
MINUTES_PER_HOUR = 60.0
TIME_SCALE_PERCENT = {"percent": 1.0, "fraction": PERCENT}
"""What turns a relative time into percent of the duration."""


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
        hours = np.asarray(SCS_HOURS, np.float64)
        return PercentPattern(hours / SCS_SPAN_H * PERCENT, np.asarray(SCS_CURVES[pattern.scs_type]) * PERCENT)
    if pattern.values is None:
        raise ValueError(f"storm.pattern names {pattern.table!r} but holds no numbers: read the job through load_job")
    return table_pattern(pattern.values, duration_min)
