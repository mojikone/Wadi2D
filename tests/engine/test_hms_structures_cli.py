"""W75: ``wadi2d hms-structures`` lists each reservoir's structures and gives the engine's refusal in its own words."""

from __future__ import annotations

import json
import shutil

from tests.hydrology.test_hms_structures import DATA, _tables
from wadi2d.engine import hms_structures
from wadi2d.engine.cli import main


def test_a_culvert_reservoir_routes_and_a_bad_one_is_refused_in_the_run_s_words(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(hms_structures, "_tables", lambda *_: _tables())
    good = tmp_path / "culvert.basin"
    shutil.copy(DATA / "culvert_box_ic.basin", good)
    found = hms_structures.reservoir_structures(good)
    (row,) = found["reservoirs"]
    assert row["refused"] is None
    assert any(s.startswith("Conduit: Culvert") and "culvert shape Box" in s for s in row["structures"])

    bad = tmp_path / "bad.basin"
    bad.write_text(good.read_text(encoding="utf-8").replace("Culvert Shape: Box", "Culvert Shape: Arch"), encoding="utf-8")
    (row,) = hms_structures.reservoir_structures(bad)["reservoirs"]
    assert row["refused"] and "Arch" in row["refused"]

    out = tmp_path / "structures.json"
    assert main(["hms-structures", str(good), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["reservoirs"][0]["name"] == row["name"]


def test_a_basin_with_no_project_beside_it_says_so(tmp_path) -> None:
    good = tmp_path / "culvert.basin"
    shutil.copy(DATA / "culvert_box_ic.basin", good)
    found = hms_structures.reservoir_structures(good)
    assert "no .hms project" in found["tables"]
    assert found["reservoirs"][0]["refused"]  # the run refuses it too: no tables, no pool
