# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The words on a map sheet, read from the run folder. No Qt, no QGIS."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

from .protocol import CONFIG_FILE, PIXEL_DIR, PIXEL_STATS, PROGRESS_FILE

MILLIONS = 1e6
SECONDS_PER_HOUR = 3600.0
BIGGEST_LINES = 6
"""Peak flows listed on the depth sheet."""


@dataclass
class RunFacts:
    """What the sheets say about a run."""

    name: str = ""
    crs: str = ""
    dem: str = ""
    dx: float = 0.0
    manning: float = 0.0
    storm_mm: float = 0.0
    storm_text: str = ""
    """What fell, where a depth alone would not say."""
    storm_area: float | None = None
    duration_h: float = 0.0
    lumped: list[str] = field(default_factory=list)
    two_d: list[str] = field(default_factory=list)
    boundaries: int = 0
    balance: dict = field(default_factory=dict)
    peaks: list[tuple[str, float, float]] = field(default_factory=list)
    class_km2: dict = field(default_factory=dict)
    limits: list = field(default_factory=list)
    pixel: float = 0.0
    maps: int = 0
    map_every_s: float = 0.0


def _peak_flows(run: Path, leave_out: str) -> list[tuple[str, float, float]]:
    """(line, peak m3/s, hour) of the biggest design lines."""
    peaks = []
    for path in sorted((run / "series").glob("line_*.csv")):
        name = path.stem[len("line_") :].replace("_", " ")
        if leave_out and leave_out.lower() in name.lower():
            continue
        with path.open(newline="", encoding="utf-8") as stream:
            rows = [(float(a), abs(float(b))) for a, b in list(csv.reader(stream))[1:]]
        if rows:
            hour, flow = max(rows, key=lambda row: row[1])
            peaks.append((name, flow, hour / SECONDS_PER_HOUR))
    return sorted(peaks, key=lambda row: -row[1])[:BIGGEST_LINES]


def _storm_text(storm: dict) -> str:
    if storm.get("kind") == "hyetograph":
        return f"{sum(storm['hyetograph_mm']):g} mm in a hyetograph"
    if storm.get("kind") == "gridded":
        return f"gridded rain from {Path(storm['rain_file']).name}"
    return ""


def _done_event(run: Path) -> dict:
    found: dict = {}
    for line in (run / PROGRESS_FILE).read_text(encoding="utf-8").splitlines():
        if '"done"' in line[:20]:
            found = json.loads(line)
    return found


def read_facts(run: Path | str, leave_out: str = "") -> RunFacts:
    """Everything the notes need. ``leave_out`` drops design lines with that word from the peak list."""
    folder = Path(run)
    cfg = json.loads((folder / CONFIG_FILE).read_text(encoding="utf-8"))
    stats_file = folder / PIXEL_DIR / PIXEL_STATS
    stats = json.loads(stats_file.read_text(encoding="utf-8")) if stats_file.is_file() else {}
    subs = cfg["hydrology"]["subbasins"]
    storm = cfg["storm"]
    return RunFacts(
        name=cfg["project"]["name"],
        dem=cfg["terrain"]["dem"] or "",
        dx=cfg["grid"]["dx"],
        manning=cfg["terrain"]["manning"],
        storm_mm=storm["depth_mm"],
        storm_text=_storm_text(storm),
        storm_area=storm.get("storm_area_km2"),
        duration_h=cfg["run"]["duration_s"] / SECONDS_PER_HOUR,
        lumped=[s["name"] for s in subs if s["mode"] == "lumped"],
        two_d=[s["name"] for s in subs if s["mode"] != "lumped"],
        boundaries=len(cfg["boundaries"]),
        balance=_done_event(folder).get("balance", {}) if (folder / PROGRESS_FILE).is_file() else {},
        peaks=_peak_flows(folder, leave_out),
        class_km2=stats.get("class_km2", {}),
        limits=stats.get("limits", []),
        pixel=stats.get("pixel_m", 0.0),
        maps=stats.get("maps", 0),
        map_every_s=cfg["outputs"]["map_every_s"],
    )


def water_note(facts: RunFacts) -> str:
    b = facts.balance
    if not b:
        return ""
    hills = f"{b['inflow_m3'] / MILLIONS:,.1f} Mm3 from the lumped hills, " if b["inflow_m3"] > 0.0 else ""
    return (
        f"Water: {hills}{b['rain_m3'] / MILLIONS:,.1f} Mm3 of "
        f"rain on the 2D area after losses, {b['outflow_m3'] / MILLIONS:,.1f} Mm3 out. "
        f"Mass error {abs(b['relative_error']):.0e}."
    )


def setup_notes(facts: RunFacts) -> str:
    parts = []
    if facts.lumped:
        parts.append(
            f"Hills: {len(facts.lumped)} subbasins run in the lumped engine. Their rain is masked out of the 2D "
            "model and each hydrograph enters at its magenta point."
        )
    two_d = f"{', '.join(facts.two_d)} and the plain" if facts.two_d else "The plain"
    parts.append(
        f"2D: {two_d}, rain on the grid, {facts.dx:g} m cells with terrain tables from the DEM, Manning n "
        f"{facts.manning:g}."
    )
    parts.append(f"Water leaves through {facts.boundaries} open boundaries. Every other edge is a closed wall.")
    area = f", storm area {facts.storm_area:g} km2" if facts.storm_area else ""
    parts.append(f"Storm: {facts.storm_text or f'{facts.storm_mm:g} mm'}{area}. Simulated {facts.duration_h:g} h.")
    if facts.balance:
        parts.append(water_note(facts))
    return "\n\n".join(parts)


def depth_notes(facts: RunFacts) -> str:
    parts = []
    if facts.peaks:
        lines = "\n".join(f"{name}: {flow:,.0f} m3/s at hour {hour:.1f}" for name, flow, hour in facts.peaks)
        parts.append(f"Peak flow at the design lines\n\n{lines}")
    if facts.balance:
        parts.append(water_note(facts))
    return "\n\n".join(parts)


def hazard_notes(facts: RunFacts) -> str:
    total = sum(facts.class_km2.values())
    areas = "\n".join(f"{name}: {km2:,.1f} km2" for name, km2 in facts.class_km2.items())
    return (
        f"Area by class, {total:,.1f} km2 in all\n\n{areas}\n\n"
        "A pixel takes the highest class any limit gives. The legend gives each class's upper limits: D x V in "
        "m2/s, D in m, V in m/s. Depth x speed at the same moment, from the saved maps, with the run's own peaks "
        "between them."
    )


def class_labels(limits: list) -> list[str]:
    """The legend of the hazard classes: each class's upper limits, m2/s, m, m/s, as the run used them."""
    labels = []
    for index, (dv, depth, speed) in enumerate(limits, start=1):
        labels.append(f"H{index}   D x V {dv:g}, D {depth:g}, V {speed:g}")
    labels.append(f"H{len(limits) + 1}   above H{len(limits)}")
    return labels
