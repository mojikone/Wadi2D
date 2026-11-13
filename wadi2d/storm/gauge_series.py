"""One rain gauge's record as periods of rain. Interface: :class:`GaugePeriods`, :func:`periods_of`, :func:`since_start`,
:func:`shifted`, :func:`on_edges`.

A period is a stretch of time and the depth that fell in it, at a constant rate; a period the record says nothing about
is a gap, depth NaN. How a record becomes periods:

* **incremental** (a DSS ``PER-CUM`` record, or a CSV said to be): each value is the depth of one period. With a known
  interval the period is that long and closes at the stamp (a DSS record always; a CSV unless ``stamp`` is ``start``),
  and a spacing of stamps longer than the interval leaves a gap between them. With no interval a period runs from the
  stamp before to this one, the first being as long as the second: a missing row then cannot be told from a long
  period, and only a missing value is a gap.
* **cumulative** (a DSS ``INST-CUM`` record, or a CSV said to be): each value is the depth since the record began, at an
  instant. A period runs between two neighbouring values and holds their difference; a fall is refused, it is a counter
  reset and not rain. Rows with no value between two that have one are bridged: the difference is known, its timing is
  not, and the period is marked so the job's ``gaps`` rule can refuse it.

Minutes count from the start of the run. :func:`since_start` drops a period that ends before it, and one cut by it
keeps its share.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wadi2d.io.series import CUMULATIVE, PERIOD_TOTAL, StationRecord
from wadi2d.storm.base import FloatArray
from wadi2d.storm.rain_frames import MM_PER

INCREMENTAL = "incremental"
STAMP_END = "end"
RATIO_TOLERANCE = 1.0e-6
"""Of an interval: stamps this close to one interval apart are one interval apart."""
FALL_TOLERANCE_MM = 1.0e-6
RAIN_KINDS = {PERIOD_TOTAL: INCREMENTAL, CUMULATIVE: "cumulative"}


@dataclass(frozen=True)
class GaugePeriods:
    """``depths`` in mm between ``starts`` and ``ends``, minutes from the start of the run; NaN where there is no value."""

    name: str
    starts: FloatArray
    ends: FloatArray
    depths: FloatArray
    bridged: np.ndarray
    """True for a period of a cumulative record that spans rows with no value."""

    @property
    def total(self) -> float:
        return float(np.nansum(self.depths))


def _factor(name: str, units: str) -> float:
    key = "".join(units.lower().split())
    if key not in MM_PER:
        raise ValueError(f"rain gauge {name}: the units {units!r} are not a depth this can read (mm, cm, m, in)")
    return MM_PER[key]


def _incremental(name: str, t: FloatArray, v: FloatArray, interval: float | None, stamp: str):
    if interval is None:
        if t.size < 2:  # noqa: PLR2004
            raise ValueError(f"rain gauge {name}: one value and no interval; give interval_min")
        steps = np.diff(t)
        if stamp == STAMP_END:
            starts, ends = np.concatenate(([t[0] - steps[0]], t[:-1])), t
        else:
            starts, ends = t, np.concatenate((t[1:], [t[-1] + steps[-1]]))
        return starts, ends, v
    steps = np.diff(t)
    short = steps < interval * (1.0 - RATIO_TOLERANCE)
    if short.any():
        at = int(np.argmax(short)) + 1
        raise ValueError(
            f"rain gauge {name}: value {at + 1} comes {steps[at - 1]:g} min after the one before, less than its "
            f"interval of {interval:g} min: the periods would overlap"
        )
    starts, ends = (t - interval, t) if stamp == STAMP_END else (t, t + interval)
    holes = np.nonzero(steps > interval * (1.0 + RATIO_TOLERANCE))[0]
    if holes.size:
        starts = np.concatenate((starts, ends[holes]))
        ends = np.concatenate((ends, starts[holes + 1]))
        v = np.concatenate((v, np.full(holes.size, np.nan)))
        order = np.argsort(starts, kind="stable")
        starts, ends, v = starts[order], ends[order], v[order]
    return starts, ends, v


def _cumulative(name: str, t: FloatArray, v: FloatArray, interval: float | None):
    known = np.isfinite(v)
    if np.count_nonzero(known) < 2:  # noqa: PLR2004
        raise ValueError(f"rain gauge {name}: a cumulative record needs two values at least")
    at = np.nonzero(known)[0]
    depths = np.diff(v[at])
    if np.any(depths < -FALL_TOLERANCE_MM):
        where = at[int(np.argmax(depths < -FALL_TOLERANCE_MM)) + 1]
        raise ValueError(
            f"rain gauge {name}: the cumulative depth falls at value {where + 1}: a counter that was reset is not rain; "
            "split the record there or give it as incremental depths"
        )
    starts, ends = t[at[:-1]], t[at[1:]]
    bridged = np.diff(at) > 1
    if interval is not None:
        bridged |= (ends - starts) > interval * (1.0 + RATIO_TOLERANCE)
    return starts, ends, np.maximum(depths, 0.0), bridged


def periods_of(
    name: str,
    record: StationRecord,
    origin: np.datetime64 | None,
    values: str = INCREMENTAL,
    units: str = "mm",
    interval_min: float | None = None,
    stamp: str = STAMP_END,
) -> GaugePeriods:
    """The periods of one record; ``values``, ``units``, ``interval_min`` and ``stamp`` speak where the file does not."""
    if record.kind and record.kind not in RAIN_KINDS:
        raise ValueError(
            f"rain gauge {name}: {record.source} is a {record.kind} record, not a rain depth (PER-CUM or INST-CUM)"
        )
    kind = RAIN_KINDS.get(record.kind, values)
    factor = _factor(name, record.units or units)
    interval = record.interval_min or interval_min
    t = np.asarray(record.minutes_from(origin), np.float64)
    v = np.asarray(record.values, np.float64) * factor
    if np.any(v < 0.0):
        at = int(np.argmax(v < 0.0))
        raise ValueError(f"rain gauge {name}: value {at + 1} is a negative depth, {v[at]:g} mm")
    if kind == INCREMENTAL:
        starts, ends, depths = _incremental(name, t, v, interval, STAMP_END if record.kind else stamp)
        bridged = np.zeros(depths.size, bool)
    else:
        starts, ends, depths, bridged = _cumulative(name, t, v, interval)
    return GaugePeriods(name, starts, ends, depths, bridged)


def since_start(periods: GaugePeriods) -> GaugePeriods:
    """Only what falls from minute zero on; a period cut by it keeps its share of the rain."""
    keep = periods.ends > 0.0
    starts, ends = periods.starts[keep].copy(), periods.ends[keep]
    depths, bridged = periods.depths[keep].copy(), periods.bridged[keep]
    cut = starts < 0.0
    depths[cut] *= ends[cut] / (ends[cut] - starts[cut])
    starts[cut] = 0.0
    return GaugePeriods(periods.name, starts, ends, depths, bridged)


def shifted(periods: GaugePeriods, minutes: float) -> GaugePeriods:
    """The same periods with the clock moved ``minutes`` back, so that ``minutes`` becomes zero."""
    return GaugePeriods(periods.name, periods.starts - minutes, periods.ends - minutes, periods.depths, periods.bridged)


def on_edges(periods: GaugePeriods, edges: FloatArray) -> FloatArray:
    """The depth in each stretch between ``edges``, which must hold every start and end of ``periods``: a period's depth
    split by time, NaN where the record has no value or does not reach."""
    out = np.full(edges.size - 1, np.nan)
    first = np.searchsorted(edges, periods.starts)
    last = np.searchsorted(edges, periods.ends)
    for a, b, start, end, depth in zip(first, last, periods.starts, periods.ends, periods.depths, strict=True):
        out[a:b] = depth * np.diff(edges[a : b + 1]) / (end - start)
    return out
