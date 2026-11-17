# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""W101 item 6: the results page's elements of record, filed by kind with their numbers, filtered with the pinned ones
first, the default view by his rule, and runs compared into a table and Excel."""

from __future__ import annotations

import pytest
from wadi2d_qgis.results_rows import (
    ALL,
    DAMS,
    DESIGN,
    JUNCTIONS,
    LINES,
    OBSERVED,
    OUTLETS,
    compare,
    default_kind,
    filtered,
    rows_of,
    write_table,
)

T = [0.0, 3600.0, 7200.0]
JOB = {"outputs": {"lines": [{"name": "Dam line", "drainage_area_km2": 20.0}, {"name": "Across"}], "points": []}}
"""The run's job names the design line by its drainage area; the engine's listing does not carry it."""


def listing(scale: float = 1.0) -> dict:
    return {
        "lines": [
            {"name": "Dam line", "coordinates": [[0, 0], [1, 1]], "t_s": T,
             "discharge_m3s": [0.0, -100.0 * scale, 50.0]},
            {"name": "Across", "coordinates": [[0, 0], [1, 1]], "t_s": T, "discharge_m3s": [0.0, 10.0, 5.0]},
        ],
        "points": [{"name": "Gauge point", "x": 0.0, "y": 0.0, "t_s": T, "depth_m": [0.0, 1.5, 0.7]}],
        "lumped": [
            {"name": "R1", "t_s": T, "inflow_m3s": [0.0, 300.0 * scale, 100.0], "outflow_m3s": [0.0, 80.0, 90.0],
             "element": {"kind": "reservoir"}},
            {"name": "J1", "t_s": T, "outflow_m3s": [0.0, 40.0, 20.0], "element": {"kind": "junction"}},
            {"name": "Sea", "t_s": T, "outflow_m3s": [0.0, 30.0, 25.0], "element": {"kind": "sink"}},
        ],
        "observed": [{"compare": "element", "target": "J1", "quantity": "flow"}],
    }  # fmt: skip


def test_each_element_filed_with_its_numbers() -> None:
    rows = {row.name: row for row in rows_of(listing(), JOB)}
    assert [rows[n].kind for n in ("Dam line", "Across", "Gauge point", "R1", "J1", "Sea")] == [
        DESIGN, LINES, LINES, DAMS, JUNCTIONS, OUTLETS,
    ]  # fmt: skip
    dam = rows["Dam line"]
    assert (dam.peak, dam.time_h) == (100.0, 1.0), "the flow's size, at its time"
    assert dam.volume_mm3 == pytest.approx((0.5 * 100.0 * 3600.0 + 0.5 * 150.0 * 3600.0) / 1e6)
    reservoir = rows["R1"]
    assert (reservoir.peak, reservoir.outflow) == (300.0, 90.0), "a dam: peak inflow, and its peak outflow beside it"
    assert rows["Gauge point"].deepest == 1.5 and rows["Gauge point"].peak is None
    assert rows["J1"].observed and not rows["Sea"].observed


def test_the_default_view_and_the_filter() -> None:
    rows = rows_of(listing(), JOB)
    assert default_kind(rows) == DESIGN
    assert default_kind([r for r in rows if r.kind != DESIGN]) == DAMS
    assert default_kind([r for r in rows if r.kind not in (DESIGN, DAMS)]) == OUTLETS
    assert [r.name for r in filtered(rows, DAMS, "", [])] == ["R1"]
    assert [r.name for r in filtered(rows, OBSERVED, "", [])] == ["J1"]
    assert [r.name for r in filtered(rows, DAMS, "", ["lumped element:Sea"])] == ["Sea", "R1"], "pinned first, any kind"
    assert [r.name for r in filtered(rows, ALL, "dam", [])] == ["Dam line"], "the search, by name"


def test_runs_compared_and_written(tmp_path) -> None:
    pytest.importorskip("openpyxl")
    first, second = rows_of(listing(), JOB), rows_of(listing(2.0), JOB)
    keys = [r.key for r in filtered(first, ALL, "", []) if r.name in ("Dam line", "R1")]
    comparison = compare({"base": first, "doubled": second}, keys)
    assert comparison.header()[:3] == ["Element", "Kind", "base: Peak, m3/s"]
    table = comparison.table()
    assert [line[0] for line in table] == ["Dam line", "R1"]
    assert table[0][2] == 100.0 and table[0][6] == 200.0, "the same element, run by run"
    written = write_table(tmp_path / "compare.xlsx", comparison)
    from openpyxl import load_workbook

    sheet = load_workbook(written).active
    assert sheet.cell(1, 3).value == "base: Peak, m3/s" and sheet.cell(2, 7).value == 200.0


def test_a_dam_lines_up_across_model_types(tmp_path) -> None:
    """W106 gap 8: a 2D pool's inflow by balance and outflow over its crest, from the engine's pool series, on the same
    row as a lumped reservoir of the same dam (an HMS name's "Reservoir" set aside)."""
    import json

    from wadi2d_qgis.results_rows import dam_key, pool_rows

    run = tmp_path / "2D"
    (run / "series").mkdir(parents=True)
    (run / "series" / "pool_Bidah_03.csv").write_text(
        "t_s,inflow_m3s,outflow_m3s,storage_m3\n900,10,0,9000\n1800,580,0,531000\n2700,300,12,800000\n", encoding="utf-8"
    )
    (run / "pools.json").write_text(json.dumps({"dams": [{"dam": "Bidah 03"}]}), encoding="utf-8")
    (pool,) = pool_rows(run)
    assert pool.key == dam_key("Bidah 03") == dam_key("Bidah 03 Reservoir") == "dam:bidah 03"
    assert (pool.name, pool.kind, pool.peak, pool.time_h, pool.outflow) == ("Bidah 03", DAMS, 580.0, 0.5, 12.0)
    lumped = {"lines": [], "points": [], "lumped": [
        {"name": "Bidah 03 Reservoir", "t_s": T, "inflow_m3s": [0.0, 455.0, 100.0], "outflow_m3s": [0.0, 0.0, 0.0],
         "element": {"kind": "reservoir"}},
    ]}  # fmt: skip
    table = compare({"Lumped": rows_of(lumped, {}), "2D": rows_of({"lines": [], "points": [], "lumped": []}, {}, run)})
    (line,) = table.table()
    assert line[0] == "Bidah 03 Reservoir" and line[2] == 455.0 and line[6] == 580.0  # one row, both runs' inflow
    assert pool_rows(None) == [] and pool_rows(tmp_path / "none") == []
