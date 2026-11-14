# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The element chart's data, from what the engine wrote (W64): hand numbers, no Qt."""

from __future__ import annotations

import pytest
from wadi2d_qgis.element_view import (
    centroid_to_peak_s,
    element_view,
    facts_text,
    matching,
    overlay_curve,
    volume_m3,
    with_facts,
    with_overlays,
)
from wadi2d_qgis.line_view import (
    LUMPED,
    TEMPORARY,
    UPFRONT_LINE,
    UPFRONT_POINT,
    Entry,
    point_view,
    readout,
    record_view,
)

TIMES = [0.0, 600.0, 1200.0, 1800.0, 2400.0]
DAM = {
    "t_s": TIMES,
    "inflow_m3s": [0.0, 10.0, 30.0, 20.0, 0.0],
    "outflow_m3s": [0.0, 2.0, 8.0, 12.0, 6.0],
    "pool_m": [100.0, 100.5, 101.2, 101.6, 101.5],
    "rain_mm": [0.0, 6.0, 4.0, 0.0, 0.0],
    "excess_mm": [0.0, 2.0, 2.0, 0.0, 0.0],
    "element": {"kind": "reservoir", "drainage_area_km2": 74.31, "tc_minutes": 95.4, "lag_minutes": None},
}


def test_centroid_of_excess_to_peak_by_hand() -> None:
    # excess 2 mm in each of the steps ending at 600 and 1200 s: middles 300 and 900 s, centroid 600 s; peak at 1800 s
    assert centroid_to_peak_s(TIMES, DAM["excess_mm"], DAM["outflow_m3s"]) == pytest.approx(1200.0)
    assert centroid_to_peak_s(TIMES, [0.0] * 5, DAM["outflow_m3s"]) is None
    assert centroid_to_peak_s(TIMES, DAM["excess_mm"], [0.0] * 5) is None


def test_volume_by_hand() -> None:
    assert volume_m3([0.0, 3600.0, 7200.0], [0.0, 10.0, 0.0]) == pytest.approx(36_000.0)


def test_a_reservoir_has_the_rain_bar_its_pool_on_the_right_and_the_header() -> None:
    view = element_view(Entry(LUMPED, "Faydh 01", None, DAM), TIMES)
    assert view.heading == "Reservoir: Faydh 01."
    chart = view.charts[0]
    assert [c.label.split(",")[0] for c in chart.curves] == ["Outflow", "Inflow"]
    assert chart.right[0].values == DAM["pool_m"] and chart.right_unit == "m"
    bars = chart.bars
    assert bars.width_h == pytest.approx(600.0 / 3600.0)
    assert bars.times_h[1] == pytest.approx(600.0 / 3600.0)  # a bar ends at its own time
    assert bars.rain_mm == DAM["rain_mm"] and bars.excess_mm == DAM["excess_mm"]
    # outflow 0, 2, 8, 12, 6 m3/s every 600 s: 600 x (1 + 5 + 10 + 9) = 15,000 m3
    assert view.note == (
        "Drainage area 74.31 km2; tc 95 min (Kirpich, his HMS expression, on the longest path above); "
        "network: centroid of excess to peak 20 min; peak 12.0 m3/s at 30 min; volume 0.015 Mm3."
    )
    assert "pool 101.20 m" in readout(view, 2)


def test_a_subbasin_names_its_own_tc_and_lag() -> None:
    facts = {"kind": "subbasin", "drainage_area_km2": 12.5, "tc_minutes": 60.0, "lag_minutes": 36.0}
    assert facts_text(facts) == "drainage area 12.50 km2; tc 60 min (Kirpich on its own path), lag 36 min"
    view = element_view(Entry(LUMPED, "S1", None, {**DAM, "element": facts, "pool_m": []}), TIMES)
    assert view.heading == "Subbasin: S1." and view.charts[0].right == []


def test_an_hms_element_without_rain_says_so_and_keeps_its_flows() -> None:
    record = {key: DAM[key] for key in ("t_s", "inflow_m3s", "outflow_m3s")}
    view = element_view(Entry(LUMPED, "J4", None, record), TIMES)
    assert view.heading == "Lumped element: J4."
    assert view.charts[0].bars is None
    assert view.note.startswith("No rain in this run's series; peak 12.0 m3/s")


def test_a_design_point_gains_its_tc_under_the_heading() -> None:
    record = {"t_s": TIMES, "depth_m": [0.0] * 5, "level_m": [1.0] * 5, "element": DAM["element"]}
    entry = Entry(UPFRONT_POINT, "Faydh 01", None, record)
    view = with_facts(point_view(entry, TIMES), entry)
    assert view.note.startswith("Drainage area 74.31 km2; tc 95 min")
    bare = Entry(UPFRONT_POINT, "P", None, {"t_s": TIMES, "depth_m": [0.0] * 5, "level_m": [1.0] * 5})
    assert with_facts(point_view(bare, TIMES), bare).note == ""


def test_matching_keeps_the_order_of_the_features_and_each_entry_once() -> None:
    items = [Entry(LUMPED, name) for name in ("S1", "J1", "R1")]
    assert matching(items, ["J1", "S1", "J1", "unknown"]) == [1, 0]


def test_an_hms_reservoir_and_diversion_are_named_by_kind_and_the_tc_said_not_available() -> None:
    """W74: on the HMS route the listing now carries each element's kind; HMS holds no path to a reservoir."""
    facts = {"kind": "reservoir", "drainage_area_km2": 19.3, "tc_minutes": None,
             "tc_note": "HMS holds no flow path to an element's outlet"}  # fmt: skip
    view = element_view(Entry(LUMPED, "Bidah 03 Reservoir", None, {**DAM, "element": facts}), TIMES)
    assert view.heading == "Reservoir: Bidah 03 Reservoir."
    assert view.note.startswith("Drainage area 19.30 km2; tc not available: HMS holds no flow path")
    sub = {"kind": "subbasin", "drainage_area_km2": 5.0, "tc_minutes": None, "lag_minutes": 42.0,
           "tc_note": "the HMS basin's .sqlite holds no flow path for it"}  # fmt: skip
    assert facts_text(sub).endswith("holds no flow path for it; lag 42 min")


def test_a_diversion_draws_what_it_passes_on_and_what_it_diverts() -> None:
    """W74: W72's passed_m3s and diverted_m3s on the chart."""
    record = {"t_s": TIMES, "inflow_m3s": [0.0, 10.0, 30.0, 20.0, 0.0], "outflow_m3s": [0.0, 10.0, 20.0, 18.0, 0.0],
              "passed_m3s": [0.0, 10.0, 20.0, 18.0, 0.0], "diverted_m3s": [0.0, 0.0, 10.0, 2.0, 0.0],
              "element": {"kind": "diversion", "drainage_area_km2": 3.0, "tc_minutes": None}}  # fmt: skip
    view = element_view(Entry(LUMPED, "D1", None, record), TIMES)
    assert view.heading == "Diversion: D1."
    labels = [c.label for c in view.charts[0].curves]
    assert labels[:2] == ["Passed on (outflow), lumped network: number of record", "Diverted, lumped network: number of record"]
    assert view.charts[0].curves[1].values == record["diverted_m3s"]
    # diverted 0, 0, 10, 2, 0 every 600 s: 600 x (0 + 5 + 6 + 1) = 7,200 m3
    assert "passed on, peak 20.0 m3/s" in view.note and "diverted, peak 10.0 m3/s at 20 min; volume 0.007 Mm3" in view.note


def test_a_design_line_carries_the_rain_bar_of_the_subbasins_above_it() -> None:
    record = {"t_s": TIMES, "discharge_m3s": [0.0, 1.0, 3.0, 2.0, 0.0],
              "rain": {"t_s": TIMES, "rain_mm": DAM["rain_mm"], "excess_mm": DAM["excess_mm"]},
              "element": DAM["element"]}  # fmt: skip
    entry = Entry(UPFRONT_LINE, "Dam line", [[0, 0], [1, 0]], record)
    view = with_facts(record_view(entry, TIMES), entry)
    assert view.charts[0].bars is not None and view.charts[0].bars.rain_mm == DAM["rain_mm"]
    assert with_facts(record_view(Entry(UPFRONT_LINE, "x", None, {"t_s": TIMES, "discharge_m3s": [0.0] * 5}), TIMES),
                      Entry(UPFRONT_LINE, "x", None, {})).charts[0].bars is None  # fmt: skip


def test_add_to_chart_draws_a_second_element_over_the_first_in_its_own_colour() -> None:
    first = Entry(LUMPED, "Faydh 01", None, DAM)
    second = Entry(LUMPED, "S1", None, {"t_s": TIMES, "outflow_m3s": [0.0, 5.0, 9.0, 4.0, 1.0]})
    line = Entry(UPFRONT_LINE, "Axis", [[0, 0], [1, 0]], {"t_s": TIMES, "discharge_m3s": [0.0, -1.0, -3.0, -2.0, 0.0]})
    added = [(e, overlay_curve(e)) for e in (second, line)]
    view = with_overlays(element_view(first, TIMES), added)
    curves = view.charts[0].curves
    assert [c.label for c in curves[-2:]] == ["Lumped element: S1: outflow of record", "Upfront line: Axis: number of record"]
    assert curves[-2].values == [0.0, 5.0, 9.0, 4.0, 1.0] and curves[-1].values == [0.0, 1.0, 3.0, 2.0, 0.0]
    assert len({c.colour for c in curves}) == len(curves), "each curve its own colour"
    assert view.heading == "Reservoir: Faydh 01. Added: S1, Axis."
    assert "flow 9.00 m3/s" in readout(view, 2)
    assert overlay_curve(Entry(UPFRONT_POINT, "P", None, {"t_s": TIMES})) is None
    drawn = Entry(TEMPORARY, "Line 1", [[0, 0], [1, 0]])
    assert overlay_curve(drawn) is None
    read = {"t_s": TIMES, "flow_m3s": [0.0, -2.0, -4.0, -1.0, 0.0]}
    assert overlay_curve(drawn, read).values == [0.0, 2.0, 4.0, 1.0, 0.0]
    assert with_overlays(element_view(first, TIMES), []).heading == "Reservoir: Faydh 01."
