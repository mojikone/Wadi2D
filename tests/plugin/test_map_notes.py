# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The words on a sheet come from the run folder, and the plugin's names match the engine's."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from wadi2d_qgis import map_notes, protocol

CONFIG = {
    "project": {"name": "demo"},
    "grid": {"dx": 20.0},
    "terrain": {"dem": "dem.tif", "manning": 0.04},
    "storm": {"depth_mm": 251.0, "storm_area_km2": 300.0},
    "run": {"duration_s": 172800.0},
    "boundaries": [{}, {}],
    "hydrology": {"subbasins": [{"name": "S1", "mode": "lumped"}, {"name": "S2", "mode": "2d"}]},
    "outputs": {"map_every_s": 900.0},
}
STATS = {
    "class_km2": {"H1": 2.0, "H2": 1.5},
    "limits": [[0.3, 0.3, 2.0]],
    "pixel_m": 5.0,
    "maps": 3,
}
BALANCE = {"inflow_m3": 2e6, "rain_m3": 1e6, "outflow_m3": 2.5e6, "relative_error": 1e-8}


def run_folder(tmp_path: Path) -> Path:
    (tmp_path / protocol.CONFIG_FILE).write_text(json.dumps(CONFIG), encoding="utf-8")
    (tmp_path / protocol.PIXEL_DIR).mkdir()
    (tmp_path / protocol.PIXEL_DIR / protocol.PIXEL_STATS).write_text(json.dumps(STATS), encoding="utf-8")
    (tmp_path / protocol.PROGRESS_FILE).write_text(
        json.dumps({"ev": "done", "balance": BALANCE}) + "\n", encoding="utf-8"
    )
    series = tmp_path / "series"
    series.mkdir()
    (series / "line_Dam_1.csv").write_text("t_s,discharge_m3s\n0,0\n3600,500\n7200,-700\n", encoding="utf-8")
    (series / "line_Dam_1_ring.csv").write_text("t_s,discharge_m3s\n0,9000\n", encoding="utf-8")
    return tmp_path


def test_facts_come_from_the_run(tmp_path: Path) -> None:
    facts = map_notes.read_facts(run_folder(tmp_path), leave_out="ring")
    assert facts.name == "demo"
    assert facts.lumped == ["S1"]
    assert facts.two_d == ["S2"]
    assert facts.peaks == [("Dam 1", 700.0, 2.0)]
    assert facts.duration_h == 48.0


def test_a_run_without_pixel_maps_still_has_facts(tmp_path: Path) -> None:
    folder = run_folder(tmp_path)
    (folder / protocol.PIXEL_DIR / protocol.PIXEL_STATS).unlink()
    assert map_notes.read_facts(folder).class_km2 == {}


def test_sheet_notes_say_it_in_words(tmp_path: Path) -> None:
    facts = map_notes.read_facts(run_folder(tmp_path), leave_out="ring")
    assert "1 subbasins" in map_notes.setup_notes(facts)
    assert "S2 and the plain" in map_notes.setup_notes(facts)
    assert "251 mm" in map_notes.setup_notes(facts)
    assert "Dam 1: 700 m3/s at hour 2.0" in map_notes.depth_notes(facts)
    assert "3.5 km2 in all" in map_notes.hazard_notes(facts)


def test_class_labels_follow_the_limits_of_the_run() -> None:
    labels = map_notes.class_labels([[0.3, 0.3, 2.0], [0.6, 0.5, 2.0]])
    assert len(labels) == 3
    assert "D x V 0.3" in labels[0]
    assert labels[2].startswith("H3")


def test_the_plugin_names_the_engine_s_files_and_layers() -> None:
    step = pytest.importorskip("wadi2d.products.step")
    smooth = pytest.importorskip("wadi2d.products.smooth")
    setup = pytest.importorskip("wadi2d.products.setup_layers")
    assert protocol.PIXEL_DIR == step.PIXEL_DIR
    assert protocol.PIXEL_STATS == step.STATS_FILE
    assert protocol.PIXEL_DEPTH == step.DEPTH_FILE
    assert protocol.PIXEL_HAZARD == step.HAZARD_FILE
    assert protocol.PIXEL_SPEED == step.SPEED_FILE
    assert protocol.PIXEL_DV == step.DV_FILE
    assert protocol.DEPTH_DRAWING == smooth.DRAWING_FILE
    assert protocol.LAYERS_FILE == smooth.LAYERS_FILE
    assert protocol.HAZARD_LAYER == smooth.CLASS_LAYER
    assert protocol.DOMAIN_LAYER == smooth.DOMAIN_LAYER
    assert protocol.SUBBASIN_LAYER == setup.SUBBASIN_LAYER
    assert protocol.INFLOW_LAYER == setup.INFLOW_LAYER
    assert protocol.BOUNDARY_LAYER == setup.BOUNDARY_LAYER
    assert protocol.LINE_LAYER == setup.LINE_LAYER
    assert protocol.REACH_LAYER == setup.REACH_LAYER
