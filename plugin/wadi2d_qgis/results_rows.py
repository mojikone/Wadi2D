# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The results page's elements of record and the comparison of runs (W101 item 6), without Qt.

A run's elements of record are what ``wadi2d lines`` lists (W21, W38, W64): its upfront lines and points and every
lumped element's series. Each row is filed under one kind by what the run knows of it, and carries the numbers a
designer reads first from its series of record: the peak flow and its time, the volume, and, where an element routes,
its peak outflow beside its peak inflow; a point carries its deepest water. Comparing runs puts those numbers side by
side for the elements the runs share, and the flows of record on one time axis.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

from .line_view import LUMPED, UPFRONT_LINE, UPFRONT_POINT, Entry, entries

DESIGN, DAMS, JUNCTIONS, REACHES, SUBBASINS, OUTLETS, LINES, OBSERVED, OTHER, ALL = (
    "design", "dams", "junctions", "reaches", "subbasins", "outlets", "lines", "observed", "other", "all",
)  # fmt: skip
KIND_WORDS = {
    ALL: "Every element",
    DESIGN: "Design points and lines",
    DAMS: "Dams and reservoirs",
    JUNCTIONS: "Junctions",
    REACHES: "Reaches",
    SUBBASINS: "Subbasins",
    OUTLETS: "Outlets",
    LINES: "Result lines and points",
    OBSERVED: "Observed gauges",
    OTHER: "Other elements",
}
ELEMENT_KINDS = {
    "reservoir": DAMS, "junction": JUNCTIONS, "reach": REACHES, "subbasin": SUBBASINS, "sink": OUTLETS,
    "diversion": OTHER, "source": OTHER,
}  # fmt: skip
"""A lumped element's kind (the basin model's word, W64 and W74) to the page's."""
DEFAULT_ORDER = (DESIGN, DAMS, OUTLETS)
"""His rule for the page's first view when nothing is pinned: design points and lines, else dams, else outlets."""
COLUMNS = ("Element", "Kind", "Peak, m3/s", "Time to peak, h", "Volume, Mm3", "Peak outflow, m3/s", "Deepest, m")
COMPARED = ("Peak, m3/s", "Time to peak, h", "Volume, Mm3", "Peak outflow, m3/s")
SECONDS_PER_HOUR = 3600.0


@dataclass
class Row:
    key: str
    """The element across runs: its listing kind and name."""
    name: str
    kind: str
    entry: Entry
    peak: float | None = None
    time_h: float | None = None
    volume_mm3: float | None = None
    outflow: float | None = None
    deepest: float | None = None
    observed: bool = False
    times_h: list[float] = field(default_factory=list)
    flow: list[float] = field(default_factory=list)
    """The flow of record, for the hydrographs of a comparison."""

    def cells(self) -> list[str]:
        return [self.name, KIND_WORDS[self.kind], *(_text(v, d) for v, d in self.numbers_with_digits())]

    def numbers(self) -> tuple:
        return (self.peak, self.time_h, self.volume_mm3, self.outflow)

    def numbers_with_digits(self) -> list[tuple]:
        return [(self.peak, 1), (self.time_h, 2), (self.volume_mm3, 3), (self.outflow, 1), (self.deepest, 2)]


def _text(value: float | None, digits: int) -> str:
    return "" if value is None else f"{value:,.{digits}f}"


def _peak(times_s: list[float], flow: list[float]) -> tuple[float | None, float | None]:
    if not flow or len(flow) != len(times_s):
        return None, None
    index = max(range(len(flow)), key=lambda i: abs(flow[i]))
    return abs(flow[index]), times_s[index] / SECONDS_PER_HOUR


def _volume(times_s: list[float], flow: list[float]) -> float | None:
    """Mm3, by the trapezoid rule on the series' own times, as the chart's header reads it (W64)."""
    if len(flow) < 2 or len(flow) != len(times_s):
        return None
    total = sum(0.5 * (abs(a) + abs(b)) * (t1 - t0) for a, b, t0, t1 in zip(flow, flow[1:], times_s, times_s[1:], strict=False))
    return total / 1e6


def design_names(job: dict | None) -> set[str]:
    """The run's design points and lines: those its job gives a drainage area (the Points section's area field, the
    depth-area study's design points); the engine's listing does not carry the area."""
    outputs = (job or {}).get("outputs") or {}
    return {
        item["name"] for item in (outputs.get("lines") or []) + (outputs.get("points") or [])
        if item.get("drainage_area_km2") is not None
    }  # fmt: skip


def _kind(entry: Entry, design: set[str]) -> str:
    record = entry.record
    if entry.kind == LUMPED:
        return ELEMENT_KINDS.get((record.get("element") or {}).get("kind", ""), OTHER)
    pours = bool(record.get("design")) or bool(record.get("element"))  # into a generated basin's network (W41, W64)
    return DESIGN if entry.name in design or pours else LINES


def _flow(entry: Entry) -> tuple[list[float], list[float]]:
    """The series' times and its flow of record: a design line's total (W41), a line's faces, an element's outflow."""
    record = entry.record
    if entry.kind == LUMPED:
        return record.get("t_s", []), record.get("outflow_m3s", [])
    design = record.get("design") or {}
    if "total_m3s" in design:
        return design.get("t_s", []), design["total_m3s"]
    return record.get("t_s", []), record.get("discharge_m3s", [])


DAM_SUFFIXES = (" reservoir", " dam")
POOL_PREFIX = "pool_"
POOL_WORDS = "2D pool: inflow by the pool's balance, outflow over its crest"


def _safe(name: str) -> str:
    """The engine's file name of a series (``wadi2d.io.results.safe_name``)."""
    import re

    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "unnamed"


def dam_key(name: str) -> str:
    """One key for a dam across model types (W106, gap 8 of W104): a lumped reservoir and the 2D pool of the same dam,
    an HMS reservoir's trailing "Reservoir" or "Dam" set aside, so Compare runs puts them on one row."""
    base = name.strip()
    for suffix in DAM_SUFFIXES:
        if base.lower().endswith(suffix):
            base = base[: -len(suffix)].strip()
    return f"dam:{base.lower()}"


def pool_rows(run: Path | str | None) -> list[Row]:
    """A run's 2D pools as dams of record, from ``series/pool_<dam>.csv`` (the engine's pool balance, W106): peak
    inflow, its time and volume, and the peak outflow; the row's chart is the dam line's."""
    if run is None:
        return []
    found = []
    folder = Path(run) / "series"
    known = {}
    pools = Path(run) / "pools.json"
    if pools.is_file():
        import json

        try:
            known = {item["dam"]: item for item in json.loads(pools.read_text(encoding="utf-8")).get("dams", [])}
        except (ValueError, KeyError, TypeError):
            known = {}
    for path in sorted(folder.glob(f"{POOL_PREFIX}*.csv")) if folder.is_dir() else []:
        safe = path.stem[len(POOL_PREFIX) :]
        name = next((dam for dam in known if _safe(dam) == safe), safe.replace("_", " "))
        with path.open(encoding="utf-8") as f:
            data = [line for line in csv.reader(f)]
        head, values = data[0], [[float(v) for v in line] for line in data[1:] if line]
        if not values:
            continue
        times = [v[0] for v in values]
        inflow = [v[head.index("inflow_m3s")] for v in values]
        outflow = [v[head.index("outflow_m3s")] for v in values]
        row = Row(dam_key(name), name, DAMS, Entry(UPFRONT_LINE, name, record={"pool": True}))
        row.peak, row.time_h = _peak(times, inflow)
        row.volume_mm3 = _volume(times, [max(q, 0.0) for q in inflow])
        held = (known.get(name) or {}).get("peak_outflow_m3s")  # the dam line's own peak, at the series step
        row.outflow = float(held) if held is not None else (max(outflow) if any(outflow) else 0.0)
        row.times_h = [t / SECONDS_PER_HOUR for t in times]
        row.flow = [abs(q) for q in outflow]
        found.append(row)
    return found


def row_of(entry: Entry, design: set[str] | None = None) -> Row:
    record = entry.record
    kind = _kind(entry, design or set())
    key = dam_key(entry.name) if entry.kind == LUMPED and kind == DAMS else f"{entry.kind}:{entry.name}"
    row = Row(key, entry.name, kind, entry, observed=bool(record.get("observed")))
    if entry.kind == UPFRONT_POINT:
        depth = record.get("depth_m") or []
        row.deepest = max(depth) if depth else None
        return row
    times_s, flow = _flow(entry)
    inflow = record.get("inflow_m3s") if entry.kind == LUMPED else None
    routed = bool(inflow) and any(inflow) and row.kind in (DAMS, REACHES)
    row.peak, row.time_h = _peak(times_s, inflow if routed else flow)
    row.volume_mm3 = _volume(times_s, inflow if routed else flow)
    if routed:
        row.outflow = _peak(times_s, flow)[0]
    row.times_h = [t / SECONDS_PER_HOUR for t in times_s]
    row.flow = [abs(q) for q in flow]
    return row


def rows_of(listing: dict, job: dict | None = None, run: Path | str | None = None) -> list[Row]:
    """The run's elements of record, in the listing's order: lines, points, then the lumped elements, then the 2D
    pools of ``run``'s folder (W106); ``job`` the run's own, which names the design points and lines."""
    design = design_names(job)
    rows = [row_of(entry, design) for entry in entries(listing)]
    lumped = {row.key for row in rows if row.kind == DAMS}
    return rows + [row for row in pool_rows(run) if row.key not in lumped]


def default_kind(rows: list[Row]) -> str:
    present = {row.kind for row in rows}
    return next((kind for kind in DEFAULT_ORDER if kind in present), ALL)


def filtered(rows: list[Row], kind: str, text: str, pinned: list[str]) -> list[Row]:
    """The rows shown: pinned ones first, whatever the filter, then those of the kind whose name holds the text."""
    words = text.strip().lower()

    def wanted(row: Row) -> bool:
        if words and words not in row.name.lower():
            return False
        if kind == ALL:
            return True
        return row.observed if kind == OBSERVED else row.kind == kind

    first = [row for key in pinned for row in rows if row.key == key and (not words or words in row.name.lower())]
    return first + [row for row in rows if row.key not in pinned and wanted(row)]


@dataclass
class Comparison:
    runs: list[str]
    keys: list[str]
    names: dict[str, str]
    kinds: dict[str, str]
    values: dict[tuple[str, str], tuple]
    """(run, key) to the four numbers."""

    def header(self) -> list[str]:
        return ["Element", "Kind", *(f"{run}: {column}" for run in self.runs for column in COMPARED)]

    def table(self) -> list[list]:
        out = []
        for key in self.keys:
            line: list = [self.names[key], KIND_WORDS[self.kinds[key]]]
            for run in self.runs:
                numbers = self.values.get((run, key))
                line += list(numbers) if numbers is not None else [None] * len(COMPARED)
            out.append(line)
        return out


def compare(runs: dict[str, list[Row]], keys: list[str] | None = None) -> Comparison:
    """The four numbers of every element the runs hold, run by run; ``keys`` limits and orders the elements (the page's
    filter); an element a run lacks reads empty there."""
    order: list[str] = []
    names: dict[str, str] = {}
    kinds: dict[str, str] = {}
    values: dict[tuple[str, str], tuple] = {}
    for run, rows in runs.items():
        for row in rows:
            if row.key not in names:
                order.append(row.key)
                names[row.key], kinds[row.key] = row.name, row.kind
            values[(run, row.key)] = row.numbers()
    chosen = [key for key in keys if key in names] if keys is not None else order
    return Comparison(list(runs), chosen, names, kinds, values)


def rounded(value):
    return None if value is None or (isinstance(value, float) and math.isnan(value)) else value


def write_table(path: Path, comparison: Comparison) -> Path:
    """The comparison as an Excel workbook (openpyxl, which QGIS ships), else as CSV beside it; the path written."""
    path = Path(path)
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
    except ImportError:
        target = path.with_suffix(".csv")
        with target.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(comparison.header())
            writer.writerows([[("" if v is None else v) for v in line] for line in comparison.table()])
        return target
    book = Workbook()
    sheet = book.active
    sheet.title = "Compare runs"
    sheet.append(comparison.header())
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for line in comparison.table():
        sheet.append([rounded(v) for v in line])
    sheet.freeze_panes = "C2"
    sheet.column_dimensions["A"].width = 28
    sheet.column_dimensions["B"].width = 22
    book.save(path)
    return path


__all__ = [
    "ALL", "COLUMNS", "KIND_WORDS", "Comparison", "Row", "compare", "default_kind", "filtered", "rows_of", "write_table",
]  # fmt: skip
