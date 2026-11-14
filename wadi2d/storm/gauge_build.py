"""A job's rain gauges as a :class:`~wadi2d.storm.gauges.GaugeStorm`. Interface: :func:`build_gauge_storm`, :func:`gauge_files`.

The steps, in order: the gauges of the job, or of the HMS project's ``.gage`` file where the job names one; their
records; one clock for all of them, whose zero is ``storm.rain_start`` or else the start of the earliest period; every
record cut into the same stretches of time; then the job's rule for a gauge with no value where another has one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from wadi2d.config.gauges import GAPS_ERROR, GAPS_NEIGHBOURS, Gauge, GaugeRain
from wadi2d.config.schema import RunConfig
from wadi2d.hms import gage as hms_gage
from wadi2d.io.series import PRECIPITATION, SECONDS_PER_MINUTE, StationRecord, read_record
from wadi2d.storm.gauge_series import GaugePeriods, on_edges, periods_of, shifted, since_start
from wadi2d.storm.gauges import GaugeStorm, fill_gaps, place_weights

WGS84 = "EPSG:4326"
"""HEC-HMS names no datum for a gage's latitude and longitude; they are read as WGS 84."""


@dataclass(frozen=True)
class Station:
    """A gauge with everything resolved: where it stands and which record is its own."""

    name: str
    x: float
    y: float
    file: Path
    record: str | None
    gauge: Gauge


def _hms_gages(cfg: RunConfig) -> tuple[Path | None, list[hms_gage.HmsGage]]:
    path = hms_gage.beside(cfg.hydrology.hms_project, cfg.hydrology.hms_basin)
    return path, ([g for g in hms_gage.load(path) if g.is_rain] if path is not None else [])


def _dem_xy(cfg: RunConfig, longitude: float, latitude: float) -> tuple[float, float]:
    import pyproj
    import rasterio

    with rasterio.open(cfg.terrain.dem) as dem:
        if dem.crs is None:
            raise ValueError(
                "the DEM names no coordinate system, so an HMS gage's latitude and longitude cannot be placed on it"
            )
        x, y = pyproj.Transformer.from_crs(WGS84, dem.crs.to_wkt(), always_xy=True).transform(
            longitude, latitude
        )
    return float(x), float(y)


def _from_hms(cfg: RunConfig, gauge: Gauge, found: hms_gage.HmsGage) -> Station:
    if found.dss_file is None or found.pathname is None:
        raise ValueError(f"HMS gage {found.name} names no DSS record")
    if gauge.x is not None and gauge.y is not None:
        x, y = gauge.x, gauge.y
    elif found.latitude is not None and found.longitude is not None:
        x, y = _dem_xy(cfg, found.longitude, found.latitude)
    else:
        raise ValueError(
            f"HMS gage {found.name} has no position in the project: give rain gauge {gauge.name} its x and y"
        )
    return Station(gauge.name, x, y, found.dss_file, found.pathname, gauge)


def stations(cfg: RunConfig) -> list[Station]:
    """The job's gauges with their files, the HMS project's standing in where the job says so."""
    spec: GaugeRain = cfg.storm.gauges
    listed = list(spec.gauges)
    path, hms = (None, [])
    if not listed or any(g.hms_gage is not None for g in listed):
        path, hms = _hms_gages(cfg)
    if not listed:
        placed = [g for g in hms if g.latitude is not None and g.longitude is not None]
        if not placed:
            where = (
                f"the HMS project's {path.name} holds no precipitation gage with a position"
                if path
                else "no HMS project is named"
            )
            raise ValueError(f"storm.gauges lists no rain gauge, and {where}: list the gauges in the job")
        listed = [Gauge(name=g.name, hms_gage=g.name) for g in placed]
    by_name = {g.name.casefold(): g for g in hms}
    out = []
    for gauge in listed:
        if gauge.hms_gage is None:
            out.append(Station(gauge.name, gauge.x, gauge.y, Path(gauge.file), gauge.record, gauge))
            continue
        found = by_name.get(gauge.hms_gage.casefold())
        if found is None:
            have = sorted(g.name for g in hms) or "none"
            where = path.name if path else "no HMS project is named, so no .gage file"
            raise ValueError(
                f"rain gauge {gauge.name}: no precipitation gage {gauge.hms_gage!r} in {where}; it holds: {have}"
            )
        out.append(_from_hms(cfg, gauge, found))
    return out


def gauge_files(cfg: RunConfig) -> list[Path]:
    """Every file the job's gauges are read from, for the run's identity; none when the job has no gauges storm."""
    if cfg.storm.kind != "gauges" or cfg.storm.gauges is None:
        return []
    found = [station.file for station in stations(cfg)]
    listed = cfg.storm.gauges.gauges
    path = hms_gage.beside(cfg.hydrology.hms_project, cfg.hydrology.hms_basin)
    if path is not None and (not listed or any(g.hms_gage is not None for g in listed)):
        found.append(path)
    return sorted(set(found))


def _when(minutes: float, origin: np.datetime64 | None) -> str:
    if origin is None:
        return f"minute {minutes:g}"
    return str(origin + np.timedelta64(round(minutes * SECONDS_PER_MINUTE), "s")).replace("T", " ")


def _clock(records: list[StationRecord], names: list[str], start: str | None) -> np.datetime64 | None:
    """The provisional date of minute zero: the job's start, else the earliest stamp; None for records with no dates."""
    dated = [r.dated for r in records]
    if any(dated) and not all(dated):
        mixed = ", ".join(
            f"{n} ({'dates' if d else 'counts from the start'})" for n, d in zip(names, dated, strict=True)
        )
        raise ValueError(
            f"rain gauges must share one clock, all with dates or all counting from the run's start: {mixed}"
        )
    if not any(dated):
        if start is not None:
            raise ValueError(
                "storm.rain_start means nothing here: the gauge records count from the start of the run"
            )
        return None
    return np.datetime64(start, "s") if start is not None else min(r.dates[0] for r in records)


def _first_gap(periods: GaugePeriods, depths: np.ndarray, edges: np.ndarray) -> tuple[float, float] | None:
    """The first stretch a gauge says nothing about, or the first bridged period of a cumulative record."""
    missing = np.isnan(depths)
    spans = []
    if missing.any():
        first = int(np.argmax(missing))
        last = first
        while last + 1 < missing.size and missing[last + 1]:
            last += 1
        spans.append((float(edges[first]), float(edges[last + 1])))
    if periods.bridged.any():
        at = int(np.argmax(periods.bridged))
        spans.append((float(periods.starts[at]), float(periods.ends[at])))
    return min(spans) if spans else None


def _filled_notes(
    names: list[str], before: np.ndarray, after: np.ndarray, edges: np.ndarray, rule: str
) -> list[str]:
    notes = []
    lengths = np.diff(edges)
    for g, name in enumerate(names):
        missing = np.isnan(before[:, g])
        if not missing.any():
            continue
        minutes = float(lengths[missing].sum())
        if rule == GAPS_NEIGHBOURS:
            notes.append(
                f"gauge {name} had no value for {minutes:g} min and was given {after[missing, g].sum():.1f} mm from the other gauges"
            )
        else:
            notes.append(f"gauge {name} had no value for {minutes:g} min, counted as no rain")
    return notes


def build_gauge_storm(cfg: RunConfig) -> GaugeStorm:
    """The storm of a job whose ``storm.kind`` is ``gauges``."""
    spec: GaugeRain = cfg.storm.gauges
    placed = stations(cfg)
    names = [s.name for s in placed]
    records = [
        read_record(s.file, s.record, s.gauge.time_unit, s.gauge.time_format, want=PRECIPITATION)
        for s in placed
    ]
    origin = _clock(records, names, cfg.storm.rain_start)
    periods = [
        periods_of(
            s.name, r, origin, s.gauge.values, s.gauge.units, s.gauge.interval_min, cfg.storm.rain_stamp
        )
        for s, r in zip(placed, records, strict=True)
    ]
    if origin is not None and cfg.storm.rain_start is None:
        early = min(float(p.starts.min()) for p in periods)
        periods = [shifted(p, early) for p in periods]
        origin = origin + np.timedelta64(round(early * SECONDS_PER_MINUTE), "s")
    periods = [since_start(p) for p in periods]
    for p in periods:
        if p.starts.size == 0:
            raise ValueError(f"rain gauge {p.name} ends before the run's start, {_when(0.0, origin)}")
    edges = np.unique(np.concatenate([np.concatenate((p.starts, p.ends)) for p in periods]))
    depths = np.column_stack([on_edges(p, edges) for p in periods])
    if spec.gaps == GAPS_ERROR:
        for p, column in zip(periods, depths.T, strict=True):
            gap = _first_gap(p, column, edges)
            if gap is not None:
                raise ValueError(
                    f"rain gauge {p.name} has no value from {_when(gap[0], origin)} to {_when(gap[1], origin)}, while the "
                    "gauges' rain runs from "
                    f"{_when(float(edges[0]), origin)} to {_when(float(edges[-1]), origin)}: complete the record, or set "
                    "storm.gauges.gaps to 'zero' or 'neighbours'"
                )
    xy = np.array([[s.x, s.y] for s in placed], np.float64)

    def weigh(x: np.ndarray, y: np.ndarray, gauges: np.ndarray) -> np.ndarray:
        return place_weights(x, y, gauges, spec.method, spec.power, spec.search_radius_m, spec.quadrants)[0]

    whole = fill_gaps(depths, xy, spec.gaps, weigh)
    if float(whole.sum()) <= 0.0:
        raise ValueError(
            "the rain gauges hold no rain in the run's time: check storm.rain_start and the records"
        )
    return GaugeStorm(
        names=tuple(names), xy=xy, edges=edges, cumulative=np.vstack((np.zeros(len(names)), np.cumsum(whole, axis=0))),
        method=spec.method, power=spec.power, search_radius_m=spec.search_radius_m, quadrants=spec.quadrants,
        samples=spec.samples, gauge_weights=spec.weights or {}, origin=origin,
        filled=tuple(_filled_notes(names, depths, whole, edges, spec.gaps)),
    )  # fmt: skip
