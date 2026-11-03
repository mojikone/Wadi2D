# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""What the result-line plot says, from what the engine wrote: no Qt, no QGIS.

Two kinds of line, and the plot must never let them be mistaken for each other. An upfront line or point was computed
during the run: a number of record. A temporary line is read back from the saved frames: the map interval, and a flow
that is either the discharge through the faces the run saved with its maps, the number of record at the frame interval,
or, on a run that saved none, an estimate from depth and speed. The engine's answer says which, and so does the plot.
An upfront line can be read from the frames as well, to see the two side by side.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

UPFRONT_LINE, UPFRONT_POINT, TEMPORARY = "upfront line", "upfront point", "temporary line"
SECONDS_PER_HOUR = 3600.0
SECONDS_PER_MINUTE = 60.0
FRAME_TOLERANCE_S = 0.5
"""Frame times are whole seconds in the frames file and the slider's are not."""
RECORD_COLOUR, FRAMES_COLOUR = "#1a5f9a", "#c8560a"
RECORD_LABEL = "Upfront, computed in the run: number of record"
FRAMES_LABEL = "Saved frames, {every}: estimated"
FACES_LABEL = "Saved frames, {every}: discharge through the faces, number of record at the frame interval"
FLOW_TITLE = "Flow, m3/s, size only"
UPFRONT, FRAMES = "upfront", "frames"
FLOW_FACES, FLOW_ESTIMATE = "faces", "estimate"
"""What the engine says a line's flow was read from; an answer without the word is an estimate."""
LIMIT = (
    "Saved frames, {every}: a peak between two frames is not seen. Flow is estimated from depth and speed, turned by the "
    "slope of the water: not a number of record. Across the flow it read 0.6 to 1.0 of upfront lines, lowest on coarse "
    "cells. A line along the flow reads far too high, and a line that crosses a wadi twice counts it twice."
)
FACES_LIMIT = (
    "Saved frames, {every}: a peak between two frames is not seen. Flow is the discharge through the faces the line "
    "crosses, summed as an upfront line is, with its sign: the number of record at the frame interval, drawn as a size. "
    "A line that crosses a wadi twice reads the net flow through both crossings."
)
LINE_NOTE = "Computed during the run, at every series step, from the discharge on the faces: the number of record."
POINT_NOTE = "Computed during the run, at every series step: the number of record."
NO_DEM = "The DEM is not where the run found it: the ground drawn is each cell's lowest point."
MOST_TICKS = 6
STEP_TOLERANCE = 1e-6
"""Of a step: a frame that starts a step exactly is on that step."""


@dataclass
class Entry:
    """One line or point on the list. Coordinates are in the run's CRS."""

    kind: str
    name: str
    coordinates: list | None = None
    record: dict = field(default_factory=dict)
    feature_id: int | None = None

    @property
    def label(self) -> str:
        words = {UPFRONT_LINE: "Upfront line", UPFRONT_POINT: "Upfront point", TEMPORARY: "Temporary line"}
        return f"{words[self.kind]}: {self.name}"


@dataclass
class Curve:
    label: str
    source: str
    colour: str
    times_h: list[float]
    values: list[float]
    markers: bool = False
    """A dot on every value: on saved frames it shows the interval the curve was read at."""


@dataclass
class Chart:
    title: str
    quantity: str
    unit: str
    curves: list[Curve]
    from_zero: bool = True


@dataclass
class Section:
    """The water surface with the terrain along a line; a gap is None."""

    title: str
    station_m: list[float]
    ground_m: list
    level_m: list[list]


@dataclass
class View:
    heading: str
    limit: str
    charts: list[Chart]
    section: Section | None
    frames_s: list[float]


def entries(listing: dict) -> list[Entry]:
    """The upfront lines, then the upfront points, of what ``wadi2d lines`` wrote."""
    lines = [Entry(UPFRONT_LINE, item["name"], item["coordinates"], item) for item in listing.get("lines", [])]
    points = [Entry(UPFRONT_POINT, item["name"], None, item) for item in listing.get("points", [])]
    return lines + points


def frame_at(times_s: list[float], t_s: float) -> int:
    """The saved frame shown at a time: the last one at or before it, the rule the mesh layer follows."""
    found = 0
    for index, time in enumerate(times_s):
        if time > t_s + FRAME_TOLERANCE_S:
            break
        found = index
    return found


def step_showing(frame_s: float, start_s: float, step_s: float, steps: int) -> int:
    """The controller's step that shows a frame: the first that starts at or after it, as a map shows the frame before."""
    if step_s <= 0.0 or steps < 1:
        return 0
    return min(max(math.ceil((frame_s - start_s) / step_s - STEP_TOLERANCE), 0), steps - 1)


def clock(seconds: float) -> str:
    """A time since the start of the run, in words a report would use."""
    minutes = round(seconds / SECONDS_PER_MINUTE)
    hours, rest = divmod(minutes, 60)
    return f"{hours} h {rest:02d} min" if hours else f"{rest} min"


def every(seconds: float) -> str:
    """The map interval; a frame falls on the first step past its time, so the spacing runs a second or so over."""
    return f"every {round(seconds / SECONDS_PER_MINUTE, 1):g} min"


def ticks(low: float, high: float, most: int = MOST_TICKS) -> list[float]:
    """Round values between two limits, at most ``most``."""
    span = high - low
    if span <= 0.0:
        return [low]
    rough = span / max(most - 1, 1)
    power = 10.0 ** math.floor(math.log10(rough))
    step = next((m * power for m in (1.0, 2.0, 5.0, 10.0) if m * power >= rough), 10.0 * power)
    first = math.ceil(low / step - 1e-9)
    last = math.floor(high / step + 1e-9)
    return [round(n * step, 10) for n in range(first, last + 1)]


def _hours(times_s: list[float]) -> list[float]:
    return [t / SECONDS_PER_HOUR for t in times_s]


def _record_curve(entry: Entry) -> Curve | None:
    record = entry.record
    if "discharge_m3s" not in record:
        return None
    return Curve(RECORD_LABEL, UPFRONT, RECORD_COLOUR, _hours(record["t_s"]), [abs(q) for q in record["discharge_m3s"]])


def point_view(entry: Entry, frames_s: list[float]) -> View:
    """A point: depth and level as recorded. There is no flow at a point, and nothing along it."""
    record = entry.record
    times = _hours(record.get("t_s", []))
    depth = Curve(RECORD_LABEL, UPFRONT, RECORD_COLOUR, times, record.get("depth_m", []))
    level = Curve(RECORD_LABEL, UPFRONT, RECORD_COLOUR, times, record.get("level_m", []))
    charts = [
        Chart("Depth at the point, m", "depth", "m", [depth]),
        Chart("Water level at the point, m", "level", "m", [level], from_zero=False),
    ]
    return View(f"Upfront point: {entry.name}.", POINT_NOTE, charts, None, frames_s)


def record_view(entry: Entry, frames_s: list[float]) -> View:
    """An upfront line that cannot be read from frames: its record alone."""
    curve = _record_curve(entry)
    charts = [Chart(FLOW_TITLE, "flow", "m3/s", [curve] if curve else [])]
    return View(f"Upfront line: {entry.name}.", LINE_NOTE, charts, None, frames_s)


def line_view(entry: Entry, read: dict) -> View:
    """A line read from the saved frames, with its record beside it when it has one."""
    interval = every(read["interval_s"])
    times = _hours(read["t_s"])
    of_record = read.get("flow_source") == FLOW_FACES
    label = (FACES_LABEL if of_record else FRAMES_LABEL).format(every=interval)
    flows = [abs(q) for q in read["flow_m3s"]]
    frames = Curve(label, FRAMES, FRAMES_COLOUR, times, flows, markers=True)
    deepest = Curve(f"Saved frames, {interval}", FRAMES, FRAMES_COLOUR, times, read["deepest_m"], markers=True)
    record = _record_curve(entry)
    flow = [record, frames] if record else [frames]
    charts = [Chart(FLOW_TITLE, "flow", "m3/s", flow), Chart("Deepest water on the line, m", "deepest", "m", [deepest])]
    title = "Water surface and terrain along the line, m"
    if read["ground_source"] != "dem":
        title = f"{title}. {NO_DEM}"
    section = Section(title, read["station_m"], read["ground_m"], read["level_m"])
    if entry.kind == TEMPORARY:
        heading = f"Temporary line: {entry.name}. Read from saved frames."
    else:
        heading = f"Upfront line: {entry.name}. Flow computed during the run; depth and water surface read from saved frames."
    limit = (FACES_LIMIT if of_record else LIMIT).format(every=interval)
    return View(heading, limit, charts, section, read["t_s"])


def value_at(curve: Curve, hours: float) -> float | None:
    """A curve's value at a time, straight between its points; None outside them."""
    times, values = curve.times_h, curve.values
    if not times or hours < times[0] or hours > times[-1]:
        return None
    for index in range(1, len(times)):
        if hours <= times[index]:
            span = times[index] - times[index - 1]
            share = (hours - times[index - 1]) / span if span > 0.0 else 0.0
            return values[index - 1] + share * (values[index] - values[index - 1])
    return values[-1]


def readout(view: View, frame: int) -> str:
    """The numbers at the current frame, each named for what it is."""
    if not view.frames_s:
        return ""
    t_s = view.frames_s[min(frame, len(view.frames_s) - 1)]
    words = [f"{clock(t_s)} from the start of the run"]
    for chart in view.charts:
        for curve in chart.curves:
            found = value_at(curve, t_s / SECONDS_PER_HOUR)
            if found is not None:
                words.append(f"{chart.quantity} {found:,.2f} {chart.unit} ({curve.source})")
    return "; ".join(words)
