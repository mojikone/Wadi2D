"""W74: a depth-area study's folder as one return period of the dam workbook, each element read as the study reads it."""

from __future__ import annotations

import csv

import numpy as np
import pytest

from tests.engine.test_arf_network import MIDDLE, STORM
from tests.engine.test_handback import SINK, SUB, X0, box, flood, lag_reach, side_polygon, write_basin
from wadi2d.arf import arf_study
from wadi2d.workbook import make, sources
from wadi2d.workbook.model import Hydrograph
from wadi2d.workbook.study import blend, study_element


def _study(tmp_path):
    basin = write_basin(tmp_path, SUB.format(down="R1"), lag_reach(), SINK)
    back = {"name": "Back", "x": X0 + 340.0, "y": MIDDLE, "element": "R1"}
    cfg = box(
        tmp_path, basin, storm=STORM, inflows=[flood(), back], duration=3600.0,
        hydrology={"polygons": str(side_polygon(tmp_path)),
                   "subbasins": [{"name": "Side", "mode": "lumped", "outlet": (X0 + 300.0, MIDDLE)}]},
        arf={"areas_km2": [0.05, 0.2]},
    )  # fmt: skip
    out = tmp_path / "study"
    assert arf_study(cfg, out).exit_code == 0
    rows = {r["design_point"]: r for r in csv.DictReader((out / "design_points.csv").open(encoding="utf-8"))}
    return out, rows


def _columns(path):
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {k: np.array([float(r[k]) for r in rows]) for k in rows[0]}


def test_blend_is_linear_in_every_column_both_runs_wrote():
    t = np.arange(4) / 4.0
    a = Hydrograph(t, np.ones(4), 2 * np.ones(4), 10 * np.ones(4), None, {"orifice_1": np.ones(4)})
    b = Hydrograph(t, 3 * np.ones(4), 4 * np.ones(4), 20 * np.ones(4), np.ones(4), {"orifice_1": 3 * np.ones(4)})
    mixed = blend(a, b, 0.25)
    np.testing.assert_allclose(mixed.inflow, 1.5)
    np.testing.assert_allclose(mixed.pool, 12.5)
    np.testing.assert_allclose(mixed.structures["orifice_1"], 1.5)
    assert mixed.storage is None, "a column one run lacks is left out"
    with pytest.raises(ValueError, match="different times"):
        blend(a, Hydrograph(t + 0.1, np.ones(4)), 0.5)


def test_a_study_folder_reads_each_element_at_its_own_area_as_the_study_does(tmp_path):
    folder, rows = _study(tmp_path)
    # the lumped subbasin: rerun alone at its own area, the hydrograph whose peak the study tabled
    side, kind, area, words = study_element(folder, "Side")
    assert area == pytest.approx(0.1) and "rerun" in kind and "rerun lumped" in words
    assert float(side.inflow.max()) == pytest.approx(float(rows["Side"]["design_peak_m3s"]), rel=1e-9)
    # the hand-back reach: the two 2D runs either side, half and half at 0.1 km2 between 0.05 and 0.2
    fed, kind, area, words = study_element(folder, "R1")
    runs = sorted((folder / "runs").iterdir())
    low, high = (_columns(run / "series" / "network_R1.csv") for run in runs)
    np.testing.assert_allclose(fed.inflow, 0.5 * low["inflow_m3s"] + 0.5 * high["inflow_m3s"])
    assert "weight 0.500" in words and "tabled peak" in words
    assert float(rows["R1"]["peak_low_m3s"]) > 0.0
    with pytest.raises(ValueError, match="stays on the grid"):
        study_element(folder, "Out")
    with pytest.raises(ValueError, match="--area Nowhere=KM2"):
        study_element(folder, "Nowhere")
    # an element read at a given area rather than its own: blended at that area
    at_high = study_element(folder, "R1", 0.2)[0]
    np.testing.assert_allclose(at_high.inflow, high["inflow_m3s"])


def test_the_workbook_takes_a_study_folder_as_a_return_period(tmp_path):
    from openpyxl import load_workbook

    folder, _rows = _study(tmp_path)
    notes: list[str] = []
    dams, _dt = sources.from_runs({"200yr": folder}, [("Side", "Side"), ("R1", "R1")], None, notes)
    assert [d.catchment_km2 for d in dams] == [0.1, 0.1]
    assert len(notes) == 2
    out = make(tmp_path / "book.xlsx", [("Side", "Side sheet"), ("R1", "R1")], runs={"200yr": folder})
    wb = load_workbook(out)
    assert "Side sheet" in wb.sheetnames
    readme = " ".join(str(c.value) for c in wb["Read me"]["A"] if c.value)
    assert "depth-area study" in readme and "rerun lumped" in readme and "weight 0.500" in readme
