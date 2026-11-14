"""The dam workbook (W60): layout, formulas, charts, the run source and the command."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest
from openpyxl import load_workbook

from wadi2d.engine.cli import main
from wadi2d.workbook import layout, make, sources
from wadi2d.workbook.model import Dam, Hydrograph, WorkbookInput, rp_label, rp_sort_key, target_sheet_name

DT = 300
N = 10
RPS = ["2yr", "200yr", "PMP"]


def _wave(peak: float, n: int = N) -> np.ndarray:
    return peak * np.sin(np.linspace(0, np.pi, n))


def _t() -> np.ndarray:
    return np.arange(N) * DT / 3600.0


def _input(routed: bool = False) -> WorkbookInput:
    dams = []
    for k, name in enumerate(["Dam A", "Dam B"]):
        d = Dam(name, name, "HMS junction", 10.0 + k)
        for j, rp in enumerate(RPS):
            q = _wave(100.0 * (j + 1) + k)
            if routed and k == 0:
                d.series[rp] = Hydrograph(_t(), q, 0.5 * q, 100 + q / 100, q / 1000)
            else:
                d.series[rp] = Hydrograph(_t(), q)
        dams.append(d)
    return WorkbookInput(dams, RPS, "200yr", DT, "test", "HMS", "depth-area analyses", "Block 9")


def _all_text(wb) -> str:
    return "\n".join(
        str(c.value) for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.value is not None
    )


def test_return_period_names():
    assert sorted(["PMP", "200yr", "2yr", "10000yr"], key=rp_sort_key) == ["2yr", "200yr", "10000yr", "PMP"]
    assert rp_label("200yr") == "200-yr" and rp_label("PMP") == "PMP"
    assert target_sheet_name("200yr") == "200-year"


def test_sheets_formulas_and_no_status():
    wb = layout.build(_input())
    assert wb.sheetnames == [
        "Read me",
        "200-year",
        "Peak inflow",
        "Inflow volume",
        "Time to peak",
        "Dam A",
        "Dam B",
    ]
    assert "Status" not in _all_text(wb)
    ws = wb["Dam A"]
    # A time, B:D inflow per period, E empty, statistics from F
    assert [ws.cell(row=1, column=c).value for c in range(1, 5)] == [
        "Time (hrs)",
        "Inflow_2yr",
        "Inflow_200yr",
        "Inflow_PMP",
    ]
    assert ws["E1"].value is None and ws["F1"].value == "Return period"
    assert ws["F3"].value == "200-yr"
    assert ws["G3"].value == "=MAX(C$2:C$11)"
    assert ws["H3"].value == "=INDEX($A$2:$A$11,MATCH(G3,C$2:C$11,0))"
    assert ws["I3"].value == f"=SUM(C$2:C$11)*{DT}/1000000"
    assert (
        ws["F17"].value == "Dam"
        and ws["F18"].value == "HMS junction"
        and ws["F19"].value == "Catchment (km²)"
    )
    assert ws["G19"].value == 10.0
    assert ws["C3"].value == round(float(_wave(200.0)[1]), 3)
    # summaries point at the statistics block, catchment from the facts
    s = wb["Peak inflow"]
    assert [s.cell(row=3, column=c).value for c in range(1, 6)] == [
        "Dam",
        "Catchment (km²)",
        "2-yr",
        "200-yr",
        "PMP",
    ]
    assert s["B4"].value == "='Dam A'!$G$19" and s["D4"].value == "='Dam A'!$G$3"
    assert wb["Inflow volume"]["C5"].value == "='Dam B'!$I$2"
    assert wb["Time to peak"]["E4"].value == "='Dam A'!$H$4"
    t = wb["200-year"]
    assert t["B1"].value == "Dam A inflow 200-yr (m³/s)" and t["F1"].value == "Dam"
    assert t["H2"].value == "=MAX(B$2:B$11)" and t["J2"].value == f"=SUM(B$2:B$11)*{DT}/1000000"
    assert wb.calculation.fullCalcOnLoad


def test_charts_main_then_tiles_three_across():
    wb = layout.build(_input())
    charts = wb["Dam A"]._charts
    assert len(charts) == 1 + len(RPS)
    main_chart, tiles = charts[0], charts[1:]
    assert main_chart.anchor == "F23" and (main_chart.width, main_chart.height) == (30.0, 15.0)
    refs = [s.tx.strRef.f for s in main_chart.series[: len(RPS)]]
    assert refs == ["'Dam A'!$J$2", "'Dam A'!$J$3", "'Dam A'!$J$4"]
    rows = [t.anchor._from.row for t in tiles]
    assert rows[0] == rows[1] == rows[2] > 23
    assert tiles[0].anchor.ext.width == tiles[1].anchor.ext.width
    xs = [(t.anchor._from.col, t.anchor._from.colOff) for t in tiles]
    assert xs == sorted(xs) and len(set(xs)) == 3
    assert len(layout.build(_input(), tile_charts=False)["Dam A"]._charts) == 1
    assert len(wb["200-year"]._charts) == 1


def test_reservoir_columns_and_summaries():
    wb = layout.build(_input(routed=True))
    assert wb.sheetnames[5:8] == ["Peak outflow", "Attenuation", "Highest pool level"]
    ws = wb["Dam A"]
    heads = [ws.cell(row=1, column=c).value for c in range(1, 6)]
    assert heads == ["Time (hrs)", "Inflow_2yr", "Outflow_2yr", "Pool_2yr", "Storage_2yr"]
    st = 1 + 3 * 4 + 2  # column O
    assert ws.cell(row=1, column=st).value == "Return period"
    extra = [ws.cell(row=1, column=st + j).value for j in range(6, 10)]
    assert extra == ["Peak outflow (m³/s)", "Attenuation (-)", "Highest pool (m)", "Highest storage (Mm³)"]
    assert ws.cell(row=2, column=st + 6).value == "=MAX(C$2:C$11)"
    assert ws.cell(row=2, column=st + 7).value == '=IF(P2>0,1-U2/P2,"")'
    assert wb["Attenuation"]["C4"].value == "='Dam A'!$V$2"
    assert wb["Attenuation"].max_row == 4  # only the routed dam
    tile = ws._charts[1]
    assert [s.tx.strRef.f for s in tile.series] == ["'Dam A'!$B$1", "'Dam A'!$C$1"]
    t = wb["200-year"]
    assert [t.cell(row=1, column=c).value for c in range(2, 7)] == [
        "Dam A inflow 200-yr (m³/s)",
        "Dam A outflow 200-yr (m³/s)",
        "Dam A pool 200-yr (m)",
        "Dam A storage 200-yr (Mm³)",
        "Dam B inflow 200-yr (m³/s)",
    ]
    # Dam B is not routed: its sheet keeps the plain layout
    assert wb["Dam B"]["E1"].value is None and wb["Dam B"]["F1"].value == "Return period"


def test_refusals():
    wi = _input()
    wi.target = "500yr"
    with pytest.raises(ValueError, match="target"):
        layout.build(wi)
    wi = _input()
    del wi.dams[0].series["PMP"]
    with pytest.raises(ValueError, match="no series"):
        layout.build(wi)


def _write(path: Path, columns: dict[str, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(list(columns))
        w.writerows(zip(*columns.values(), strict=True))


def _runs(tmp_path: Path) -> dict[str, Path]:
    runs = {}
    t = np.arange(N) * float(DT)
    for j, rp in enumerate(RPS):
        run = tmp_path / rp
        q = _wave(50.0 * (j + 1))
        _write(
            run / "series" / "network_Res_1.csv",
            {"t_s": t, "inflow_m3s": q, "outflow_m3s": 0.4 * q, "pool_m": 90 + q / 50, "storage_m3": 1e4 * q},
        )
        _write(run / "series" / "network_J_2.csv", {"t_s": t, "inflow_m3s": q, "outflow_m3s": q})
        _write(run / "series" / "network_S3.csv", {"t_s": t, "inflow_m3s": 0 * q, "outflow_m3s": q})
        _write(run / "series" / "line_Axis.csv", {"t_s": t, "discharge_m3s": -q})
        runs[rp] = run
    return runs


def test_runs_source(tmp_path):
    runs = _runs(tmp_path)
    dams, dt = sources.from_runs(
        runs, [("Res 1", "R1"), ("J 2", "J2"), ("S3", "S3"), ("Axis", "Axis")], {"Res 1": 12.5}
    )
    assert dt == DT
    res, junction, subbasin, line = dams
    assert (
        res.routed
        and res.quantities() == ("inflow", "outflow", "pool", "storage")
        and res.catchment_km2 == 12.5
    )
    np.testing.assert_allclose(res.series["PMP"].storage, 1e-2 * _wave(150.0))
    assert not junction.routed and not subbasin.routed
    np.testing.assert_allclose(subbasin.series["2yr"].inflow, _wave(50.0))
    np.testing.assert_allclose(line.series["2yr"].inflow, _wave(50.0))
    assert line.element_kind == "Wadi2D result line"
    with pytest.raises(ValueError, match="no network"):
        sources.from_runs(runs, [("Nowhere", "Nowhere")])


def test_command(tmp_path, capsys):
    runs = _runs(tmp_path)
    out = tmp_path / "book.xlsx"
    args = ["workbook", "--out", str(out), "--element", "Res 1=R1", "--element", "J 2", "--area", "J 2=4"]
    for rp, run in runs.items():
        args += ["--run", f"{rp}={run}"]
    assert main(args) == 0
    wb = load_workbook(out)
    assert wb.sheetnames[:2] == ["Read me", "200-year"] and "R1" in wb.sheetnames and "J 2" in wb.sheetnames
    assert wb["J 2"].cell(row=19, column=7).value == 4.0
    assert main(["workbook", "--out", str(out), "--element", "Nowhere", "--run", f"2yr={runs['2yr']}"]) == 2
    assert main(["workbook", "--out", str(out), "--element", "J 2"]) == 2
    assert make is not None
