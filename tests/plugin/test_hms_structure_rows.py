"""W75: the read-only reservoir table takes the engine's answer as it comes (``wadi2d hms-structures``)."""

from __future__ import annotations

import shutil

from wadi2d_qgis.hms_structure_rows import ROUTES, reservoir_rows, structures_args, structures_note

from tests.hydrology.test_hms_structures import DATA, _tables
from wadi2d.engine import hms_structures


def test_the_engine_s_answer_becomes_rows(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(hms_structures, "_tables", lambda *_: _tables())
    good, bad = tmp_path / "good.basin", tmp_path / "bad.basin"
    shutil.copy(DATA / "culvert_box_tw_part.basin", good)
    bad.write_text(good.read_text(encoding="utf-8").replace("Culvert Shape: Box", "Culvert Shape: Arch"), encoding="utf-8")
    (ok,) = reservoir_rows(hms_structures.reservoir_structures(good))
    assert ok.word == ROUTES and not ok.refused and "Conduit: Culvert" in ok.structures
    assert "main tailwater Fixed Stage 101.5 m" in ok.structures
    answer = hms_structures.reservoir_structures(bad)
    (no,) = reservoir_rows(answer)
    assert no.refused and no.word.startswith("refused: ") and "Arch" in no.word
    assert structures_note(answer).startswith("0 of 1 reservoirs route")
    assert structures_note({"reservoirs": []}) == "The basin has no reservoir."
    assert structures_args("b.basin", "o.json") == ["hms-structures", "b.basin", "--out", "o.json"]
