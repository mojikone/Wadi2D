# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Suggest breaklines button's plain parts, without QGIS; the dock itself is checked through the harness."""

from __future__ import annotations

import json
from pathlib import Path

from wadi2d_qgis.suggest_lines import (
    FILE,
    FOLDER_SUFFIX,
    KINDS,
    TEMP_PREFIX,
    breaklines_args,
    layer_title,
    output_folder,
    parse_breaklines,
    summary_text,
)

EVENT = {
    "ev": "breaklines",
    "path": "D:/runs/one_breaklines/suggested_breaklines.gpkg",
    "layer": "breaklines",
    "thalweg_layer": "thalwegs",
    "pixel_m": 5.0,
    "banks": 4,
    "crests": 3,
    "crest_kinds": {"road": 1, "other crest": 2},
    "thalwegs": 2,
}


def test_the_arguments_are_the_commands():
    assert breaklines_args(Path("j.json"), "out") == ["breaklines", "j.json", "--out", "out"]


def test_the_event_is_the_last_line_that_says_so():
    noise = "warning\n" + json.dumps({"ev": "other"}) + "\n" + json.dumps(EVENT) + "\nbye\n"
    assert parse_breaklines(noise) == EVENT
    assert parse_breaklines("nothing\n") is None
    assert parse_breaklines(json.dumps({"ev": "error", "message": "x"})) is None


def test_the_file_goes_beside_the_run_folder_or_to_a_temporary_one(tmp_path):
    run = tmp_path / "one"
    first = output_folder(str(run))
    assert first == tmp_path / ("one" + FOLDER_SUFFIX)
    first.mkdir()
    (first / FILE).write_bytes(b"")
    assert output_folder(str(run)) == tmp_path / ("one" + FOLDER_SUFFIX + "_2")
    temp = output_folder("")
    assert temp.is_dir() and temp.name.startswith(TEMP_PREFIX)
    temp.rmdir()


def test_the_title_and_the_message_say_what_was_found():
    assert layer_title(EVENT) == "Suggested breaklines: 4 banks, 3 crests"
    text = summary_text(EVENT)
    assert "4 bank lines along 2 thalwegs" in text
    assert "3 crests (1 road, 2 other crest)" in text
    assert "delete what is wrong" in text and EVENT["path"] in text
    assert "bank lines as Refinement lines in the Mesh section" in text  # banks refine, they are never barriers
    assert "never load them as Crest lines" in text and "road, dam and dyke crests as Crest lines" in text
    assert "no crests" in summary_text({**EVENT, "crests": 0, "crest_kinds": {}})


def test_every_kind_the_engine_writes_has_a_colour_and_the_file_name_is_the_engines():
    from wadi2d_qgis.mesh_rows import LINE_FIELDS

    from wadi2d.breaklines import settings as engine

    assert {kind for kind, _colour, _legend in KINDS} == {engine.BANK, engine.DAM, engine.OTHER, engine.ROAD}
    assert FILE == engine.FILE
    assert LINE_FIELDS == engine.LINE_FIELDS
