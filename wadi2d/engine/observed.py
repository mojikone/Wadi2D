"""Observed records beside a finished run's series. Interface: :func:`compare_run`, :func:`load_observed`,
:data:`OBSERVED_DIR`.

Each record of ``outputs.observed`` is read (:mod:`wadi2d.io.series`), put on the run's clock, and compared with the
series the run wrote for its target: a result line's discharge (its design record, grid plus lumped water, where the
run wrote one), a result point's level or depth, or a lumped element's outflow or inflow. A line's discharge carries
the sign of its direction; it is compared as a size, as the plot draws it. Written in ``observed/`` of the run folder:
``<name>.csv`` with both series on the common time base, and ``statistics.json`` with every record's numbers and the
formulas they come from (:mod:`wadi2d.engine.agreement`). Nothing here reruns the model, so a new observed file is
compared with an old run in seconds.

The clock. A record that counts minutes from the start of the run needs nothing. A record with dates needs the date of
the run's start: the record's own ``start``, else the job's ``storm.rain_start``, else the start of a gauge storm's rain
as the run wrote it in ``rain_gauges.json``.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from wadi2d.config.gauges import COMPARE_ELEMENT, COMPARE_LINE, COMPARE_POINT, DEPTH, FLOW, Observed
from wadi2d.config.schema import RunConfig
from wadi2d.engine.agreement import FORMULAS, agreement
from wadi2d.io.results import safe_name
from wadi2d.io.series import FLOW as WANT_FLOW
from wadi2d.io.series import INSTANT, PERIOD_MEAN, SECONDS_PER_MINUTE, read_record
from wadi2d.io.series import LEVEL as WANT_LEVEL

OBSERVED_DIR = "observed"
STATISTICS = "statistics.json"
GAUGE_FILE = "rain_gauges.json"
"""Written by a run on a gauge storm: the date of its minute zero among other things."""
CONFIG = "config.resolved.json"
UNITS = {FLOW: "m3/s", "level": "m", DEPTH: "m"}
COLUMN = {"level": "level_m", DEPTH: "depth_m"}
CFS = 0.3048**3
TO_SI = {
    FLOW: {"m3/s": 1.0, "cms": 1.0, "m3s": 1.0, "cumecs": 1.0, "cfs": CFS, "ft3/s": CFS},
    "level": {
        "m": 1.0,
        "meter": 1.0,
        "meters": 1.0,
        "metre": 1.0,
        "metres": 1.0,
        "ft": 0.3048,
        "feet": 0.3048,
    },
}
"""Units a DSS flow or stage record may carry, to m3/s and m."""
KINDS_READ = ("", INSTANT, PERIOD_MEAN)
"""A flow or a stage is a value at an instant, or a mean over a period stamped at its end; a total is refused."""


def _origin(item: Observed, cfg: RunConfig, run: Path) -> np.datetime64 | None:
    if item.start is not None:
        return np.datetime64(item.start, "s")
    if cfg.storm.rain_start is not None:
        return np.datetime64(cfg.storm.rain_start, "s")
    written = run / GAUGE_FILE
    if written.is_file():
        start = json.loads(written.read_text(encoding="utf-8")).get("start")
        if start:
            return np.datetime64(start, "s")
    return None


def _read_csv(path: Path) -> dict[str, np.ndarray]:
    """A series the run wrote; empty when it wrote none of that name."""
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if len(rows) < 2:
        return {}
    data = np.array(rows[1:], dtype=np.float64)
    return {name: data[:, k] for k, name in enumerate(rows[0])}


def simulated(run: Path, item: Observed) -> tuple[np.ndarray, np.ndarray, str]:
    """(t_s, values, what was read) of the run's series the record is compared with."""
    folder = run / "series"
    name = safe_name(item.target)
    if item.compare == COMPARE_LINE:
        design = _read_csv(folder / f"design_{name}.csv")
        if "total_m3s" in design:
            return (
                design["t_s"],
                np.abs(design["total_m3s"]),
                f"result line {item.target}, grid plus lumped water",
            )
        found = _read_csv(folder / f"line_{name}.csv")
        if "discharge_m3s" in found:
            return (
                found["t_s"],
                np.abs(found["discharge_m3s"]),
                f"result line {item.target}, size of the discharge",
            )
        raise ValueError(f"observed {item.name}: the run wrote no series for result line {item.target}")
    if item.compare == COMPARE_POINT:
        found = _read_csv(folder / f"point_{name}.csv")
        column = COLUMN[item.quantity]
        if column in found:
            return found["t_s"], found[column], f"result point {item.target}, {item.quantity}"
        raise ValueError(f"observed {item.name}: the run wrote no series for result point {item.target}")
    found = _read_csv(folder / f"network_{name}.csv")
    column = f"{item.series}_m3s"
    if column in found:
        return found["t_s"], found[column], f"lumped element {item.target}, {item.series}"
    raise ValueError(
        f"observed {item.name}: the run wrote no {item.series} for lumped element {item.target}; a run writes the "
        "series of the elements whose water reached the grid"
    )


def load_observed(item: Observed, origin: np.datetime64 | None) -> tuple[np.ndarray, np.ndarray, str]:
    """(t_s from the start of the run, values with the offset added, the source) of one observed record."""
    want = WANT_FLOW if item.quantity == FLOW else WANT_LEVEL
    record = read_record(item.file, item.record, item.time_unit, item.time_format, want=want)
    if record.kind not in KINDS_READ:
        raise ValueError(
            f"observed {item.name}: {record.source} is a {record.kind} record, not a flow or a level"
        )
    if record.dated and origin is None:
        raise ValueError(
            f"observed {item.name}: the record has dates and the run's start has none: give the record's start, the "
            "date and time of the run's minute zero"
        )
    t = np.asarray(record.minutes_from(origin), np.float64) * SECONDS_PER_MINUTE
    return t, np.asarray(record.values, np.float64) * _factor(item, record.units) + item.offset, record.source


def _factor(item: Observed, units: str) -> float:
    """To m3/s or m from what a DSS record says it holds; a CSV says nothing and is read as m3/s or m."""
    key = "".join(units.lower().split())
    known = TO_SI[FLOW if item.quantity == FLOW else "level"]
    if not key or key in known:
        return known.get(key, 1.0)
    raise ValueError(
        f"observed {item.name}: units {units!r} are not a {item.quantity} this can read ({sorted(known)})"
    )


def _write_pair(
    path: Path, t: np.ndarray, obs: np.ndarray, sim: np.ndarray, origin: np.datetime64 | None
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["t_s", "date", "observed", "simulated"])
        for when, o, s in zip(t, obs, sim, strict=True):
            date = "" if origin is None else str(origin + np.timedelta64(round(when), "s")).replace("T", " ")
            writer.writerow([f"{when:.3f}", date, f"{o:.6g}", f"{s:.6g}"])


def compare_one(run: Path, cfg: RunConfig, item: Observed) -> dict:
    """The record of one comparison, written beside the others."""
    origin = _origin(item, cfg, run)
    t_obs, obs, source = load_observed(item, origin)
    t_sim, sim, read = simulated(run, item)
    stats = agreement(t_obs, obs, t_sim, sim, volumes=item.quantity == FLOW)
    keep = np.isfinite(obs) & (t_obs >= t_sim[0]) & (t_obs <= t_sim[-1])
    _write_pair(
        run / OBSERVED_DIR / f"{safe_name(item.name)}.csv",
        t_obs[keep],
        obs[keep],
        np.interp(t_obs[keep], t_sim, sim),
        origin,
    )
    left = int(np.count_nonzero(np.isfinite(obs))) - stats.points
    return {
        "name": item.name, "quantity": item.quantity, "unit": UNITS[item.quantity], "compare": item.compare,
        "target": item.target, "series": item.series if item.compare == COMPARE_ELEMENT else None,
        "observed_source": source, "simulated_source": read, "start": None if origin is None else str(origin),
        "outside_run": left, "file": f"{safe_name(item.name)}.csv", **stats.as_dict(),
    }  # fmt: skip


def compare_run(run: str | Path, observed: list[Observed] | None = None) -> dict:
    """Compare every record with the run in folder ``run``; ``observed`` replaces the job's own list.

    One record that cannot be compared is reported with its reason and the others go on.
    """
    folder = Path(run)
    cfg = RunConfig.model_validate_json((folder / CONFIG).read_text(encoding="utf-8"))
    items = cfg.outputs.observed if observed is None else observed
    done, failed = [], []
    for item in items:
        try:
            done.append(compare_one(folder, cfg, item))
        except (ValueError, OSError, KeyError) as error:
            failed.append({"name": item.name, "reason": str(error)})
    report = {"formulas": FORMULAS, "records": done, "failed": failed}
    if items:
        path = folder / OBSERVED_DIR / STATISTICS
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


__all__ = [
    "COMPARE_LINE",
    "COMPARE_POINT",
    "OBSERVED_DIR",
    "STATISTICS",
    "compare_one",
    "compare_run",
    "load_observed",
]
