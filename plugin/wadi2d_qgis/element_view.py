# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The hydrograph chart of one element, after HMS's layout (W64): no Qt, no QGIS.

A thin rain bar hangs from the top, rain light and excess dark over it, so the losses are the difference. The flow sits
below: outflow of record and inflow; a reservoir's pool level on a right-hand axis when its series has one. The header
names the drainage area, Kirpich's tc, the network's own time from the centroid of excess to the peak, the peak, its
time and the volume. Kirpich was fitted on small farm basins, so on a large junction its tc is a figure outside its
range: both numbers are shown, labelled, and neither sets a lag.

Interface: :func:`element_view`, :func:`facts_text`, :func:`centroid_to_peak_s`, :func:`volume_m3`, :func:`with_facts`,
:func:`matching`.
"""

from __future__ import annotations

from .line_view import (
    FLOW_TITLE,
    INFLOW_COLOUR,
    LUMPED_NOTE,
    RECORD_COLOUR,
    SECONDS_PER_HOUR,
    SECONDS_PER_MINUTE,
    UPFRONT,
    Bars,
    Chart,
    Curve,
    Entry,
    View,
    _agreement,
    clock,
    observed_curves,
)

POOL_COLOUR = "#2e7d32"
POOL_COLUMNS = ("pool_m", "stage_m", "elevation_m")
"""A reservoir's level column, the first found; W59 writes ``pool_m``."""
KIND_WORDS = {
    "subbasin": "Subbasin",
    "reach": "Reach",
    "junction": "Junction",
    "reservoir": "Reservoir",
}
TC_WORDS = "tc {tc:,.0f} min (Kirpich, his HMS expression, on the longest path above)"
SUBBASIN_TC_WORDS = "tc {tc:,.0f} min (Kirpich on its own path), lag {lag:,.0f} min"
NETWORK_WORDS = "network: centroid of excess to peak {minutes:,.0f} min"
NO_RAIN_WORDS = "no rain in this run's series"


def centroid_to_peak_s(times_s: list[float], excess_mm: list[float], flow: list[float]) -> float | None:
    """The time from the centroid of the excess to the peak of the flow, s; None with no excess or no flow.

    Each depth is the step ending at its time, so it counts at the middle of that step.
    """
    if len(times_s) < 2 or not flow or max(abs(q) for q in flow) <= 0.0:
        return None
    total = sum(excess_mm[1:])
    if total <= 0.0:
        return None
    middle = [0.5 * (times_s[i - 1] + times_s[i]) for i in range(1, len(times_s))]
    centroid = sum(d * t for d, t in zip(excess_mm[1:], middle, strict=True)) / total
    peak = max(range(len(flow)), key=lambda i: abs(flow[i]))
    return times_s[peak] - centroid


def volume_m3(times_s: list[float], flow: list[float]) -> float:
    """The volume under a hydrograph, trapezoids, m3."""
    return sum(0.5 * (abs(flow[i - 1]) + abs(flow[i])) * (times_s[i] - times_s[i - 1]) for i in range(1, len(times_s)))


def facts_text(facts: dict | None) -> str:
    """Drainage area and tc of an element of a generated basin; empty on an HMS basin, which has no terrain path."""
    if not facts:
        return ""
    words = []
    if facts.get("drainage_area_km2") is not None:
        words.append(f"drainage area {facts['drainage_area_km2']:,.2f} km2")
    tc, lag = facts.get("tc_minutes"), facts.get("lag_minutes")
    if tc is not None and lag is not None:
        words.append(SUBBASIN_TC_WORDS.format(tc=tc, lag=lag))
    elif tc is not None:
        words.append(TC_WORDS.format(tc=tc))
    return "; ".join(words)


def _bars(times_s: list[float], record: dict) -> Bars | None:
    rain, excess = record.get("rain_mm"), record.get("excess_mm")
    if not rain or len(times_s) < 2 or max(rain) <= 0.0:
        return None
    step_h = (times_s[1] - times_s[0]) / SECONDS_PER_HOUR
    return Bars([t / SECONDS_PER_HOUR for t in times_s], step_h, list(rain), list(excess or [0.0] * len(rain)))


def _pool(record: dict) -> list[float] | None:
    return next((record[key] for key in POOL_COLUMNS if record.get(key)), None)


def element_view(entry: Entry, frames_s: list[float]) -> View:
    """One lumped element's chart: rain bar, outflow and inflow, pool level when it has one, and the header."""
    record = entry.record
    times_s = record.get("t_s", [])
    times = [t / SECONDS_PER_HOUR for t in times_s]
    outflow = record.get("outflow_m3s", [])
    curves = [Curve("Outflow, lumped network: number of record", UPFRONT, RECORD_COLOUR, times, outflow)]
    inflow = record.get("inflow_m3s")
    if inflow and any(inflow):
        curves.append(Curve("Inflow, lumped network", UPFRONT, INFLOW_COLOUR, times, inflow))
    curves += observed_curves(entry, "flow")
    pool = _pool(record)
    right = [Curve("Pool level, m", UPFRONT, POOL_COLOUR, times, pool)] if pool else []
    bars = _bars(times_s, record)
    chart = Chart(FLOW_TITLE, "flow", "m3/s", curves, right=right, right_quantity="pool", right_unit="m", bars=bars)
    facts = record.get("element") or {}
    kind = KIND_WORDS.get(facts.get("kind", ""), "Lumped element")
    words = [w for w in (facts_text(facts),) if w]
    if bars is None:
        words.append(NO_RAIN_WORDS)
    else:
        lag = centroid_to_peak_s(times_s, bars.excess_mm, outflow)
        if lag is not None:
            words.append(NETWORK_WORDS.format(minutes=lag / SECONDS_PER_MINUTE))
    if outflow and len(times_s) > 1:
        peak = max(range(len(outflow)), key=lambda i: abs(outflow[i]))
        words.append(f"peak {abs(outflow[peak]):,.1f} m3/s at {clock(times_s[peak])}")
        words.append(f"volume {volume_m3(times_s, outflow) / 1e6:,.3f} Mm3")
    note = "; ".join(words)
    note = note[0].upper() + note[1:] + "." if note else ""
    return View(f"{kind}: {entry.name}.", LUMPED_NOTE, [chart], None, frames_s, _agreement(entry, ("flow",)), note)


def with_facts(view: View, entry: Entry) -> View:
    """A design point's or line's drainage area and tc added under the heading, when the basin model has them."""
    text = facts_text(entry.record.get("element"))
    if text:
        view.note = f"{view.note} {text[0].upper()}{text[1:]}.".strip()
    return view


def matching(entries: list[Entry], names: list[str]) -> list[int]:
    """The entries named by features under a right-click, in the order the features came, each once."""
    found: list[int] = []
    for name in names:
        for index, entry in enumerate(entries):
            if entry.name == name and index not in found:
                found.append(index)
    return found
