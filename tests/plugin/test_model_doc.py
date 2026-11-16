# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The saved model document (W99): its format, its refusals in words, its files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from wadi2d_qgis import model_doc

SECTIONS = {"terrain": {"widgets": {"dx": 20.0}, "rows": {}}}


def test_a_document_goes_to_text_and_back() -> None:
    doc = model_doc.new_doc(SECTIONS, "0.4.0", model_type="2d")
    again = model_doc.loads(model_doc.dumps(doc))
    assert again == doc
    assert (again["format"], again["version"], again["model_type"]) == (
        "wadi2d-model",
        model_doc.VERSION,
        "2d",
    )


def test_the_same_model_whatever_the_stamp_and_the_plugin() -> None:
    first = model_doc.new_doc(SECTIONS, "0.4.0")
    later = {**model_doc.new_doc(SECTIONS, "0.5.0"), "saved": "2030-01-01T00:00:00"}
    assert model_doc.fingerprint(first) == model_doc.fingerprint(later)
    moved = model_doc.new_doc({"terrain": {"widgets": {"dx": 30.0}, "rows": {}}}, "0.4.0")
    assert model_doc.fingerprint(first) != model_doc.fingerprint(moved)
    assert model_doc.fingerprint(first) != model_doc.fingerprint(
        model_doc.new_doc(SECTIONS, model_type="lumped")
    )


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ("not json", "not a Wadi2D model file"),
        ('{"format": "other", "version": 1, "sections": {}}', "not a Wadi2D model file"),
        ('{"format": "wadi2d-model", "sections": {}}', "no format version"),
        ('{"format": "wadi2d-model", "version": 99, "sections": {}}', "newer Wadi2D"),
    ],
)
def test_what_cannot_be_read_is_refused_in_words(text: str, words: str) -> None:
    with pytest.raises(ValueError, match=words):
        model_doc.loads(text)


def test_an_older_format_is_brought_up(monkeypatch) -> None:
    monkeypatch.setattr(model_doc, "VERSION", 2)
    monkeypatch.setattr(model_doc, "MIGRATIONS", {1: lambda doc: {**doc, "model_type": "2d"}})
    old = json.dumps({"format": "wadi2d-model", "version": 1, "sections": {}})
    assert model_doc.loads(old) == {
        "format": "wadi2d-model",
        "version": 2,
        "sections": {},
        "model_type": "2d",
    }


def test_scenarios_live_in_the_models_folder(tmp_path: Path) -> None:
    assert model_doc.list_scenarios(tmp_path) == []
    assert model_doc.list_scenarios("") == []
    path = model_doc.write_doc(
        model_doc.scenario_path(tmp_path, "200-yr: dams full?"), model_doc.new_doc(SECTIONS)
    )
    assert path == tmp_path / "scenarios" / "200-yr_ dams full_.wadi2d.json"
    assert model_doc.list_scenarios(tmp_path) == [("200-yr_ dams full_", path)]
    assert model_doc.read_doc(path)["sections"] == SECTIONS
