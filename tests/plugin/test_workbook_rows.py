"""The dam workbook dialog without Qt (W60 in the dock, W68): the runs, the elements, and the command it starts."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from wadi2d_qgis.workbook_rows import (
    common_elements,
    period_key,
    run_elements,
    workbook_args,
    workbook_problems,
    workbook_reply,
)

from wadi2d.engine.cli import main


def _run(tmp_path: Path, name: str, peak: float, extra: str = "") -> Path:
    run = tmp_path / name
    (run / "series").mkdir(parents=True)
    t = np.arange(0.0, 7200.0 + 1, 600.0)
    q = peak * np.sin(np.pi * t / 7200.0)
    rows = ["t_s,inflow_m3s,outflow_m3s", *(f"{a},{b},{0.5 * b}" for a, b in zip(t, q, strict=True))]
    (run / "series" / "network_Dam_A.csv").write_text("\n".join(rows), encoding="utf-8")
    lines = ["t_s,total_m3s", *(f"{a},{b}" for a, b in zip(t, q, strict=True))]
    (run / "series" / "design_Axis.csv").write_text("\n".join(lines), encoding="utf-8")
    if extra:
        (run / "series" / f"line_{extra}.csv").write_text("t_s,discharge_m3s\n0,0\n", encoding="utf-8")
    return run


def test_periods_are_named_as_the_engine_names_them() -> None:
    assert [period_key(t) for t in ("200", " 200 yr", "200-year", "pmp", "PMP", "odd")] == [
        "200yr", "200yr", "200yr", "PMP", "PMP", "odd",
    ]  # fmt: skip


def test_elements_every_run_has_lumped_first_and_the_args_sorted_by_years(tmp_path: Path) -> None:
    a, b = _run(tmp_path, "rp200", 300.0, extra="only_here"), _run(tmp_path, "rp50", 150.0)
    assert run_elements(a) == ["Dam_A", "Axis", "only_here"]
    assert common_elements([a, b]) == ["Dam_A", "Axis"]
    rows = [("PMP", str(a)), ("200", str(a)), ("50 yr", str(b))]
    args = workbook_args(rows, ["Dam_A"], "200", "out.xlsx", "Block 02")
    assert args == [
        "workbook", "--out", "out.xlsx", "--element", "Dam_A",
        "--run", f"50yr={b}", "--run", f"200yr={a}", "--run", f"PMP={a}",
        "--target", "200yr", "--project", "Block 02",
    ]  # fmt: skip
    assert workbook_reply('noise\n{"ev": "workbook", "path": "D:/x.xlsx"}') == "D:/x.xlsx"
    assert workbook_reply("") is None


def test_what_is_missing_is_said_before_the_engine_starts(tmp_path: Path) -> None:
    a = _run(tmp_path, "rp200", 300.0)
    assert workbook_problems([], [], "200yr", "") == [
        "Add a finished run for each return period.",
        "Tick at least one element: a dam, a reservoir or a design line.",
        "The target period 200yr has no run.",
        "Choose where the workbook goes.",
    ]
    found = workbook_problems([("200", str(a)), ("200yr", str(tmp_path / "nothing"))], ["Dam_A"], "200yr", "o.xlsx")
    assert found == [
        "The run of 200yr is not a finished run folder with series.",
        "One run per return period: 200yr is given twice.",
    ]
    assert workbook_problems([("200", str(a))], ["Dam_A"], "200", "o.xlsx") == []


def test_the_engine_writes_the_workbook_the_dialog_asks_for(tmp_path: Path, capsys) -> None:
    a, b = _run(tmp_path, "rp200", 300.0), _run(tmp_path, "rp50", 150.0)
    out = tmp_path / "book.xlsx"
    args = workbook_args([("200", str(a)), ("50", str(b))], ["Dam_A", "Axis"], "200", str(out))
    assert main(args) == 0
    assert workbook_reply(capsys.readouterr().out) == str(out) and out.is_file()
    from openpyxl import load_workbook

    names = load_workbook(out).sheetnames
    assert "200-year" in names and any("Dam_A" in n for n in names) and any("Axis" in n for n in names), names
