# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""W101 item 5: the domain from an outline, its folder, its command, its refusals, its words, and the job it reads."""

from __future__ import annotations

from wadi2d_qgis.domain_rows import (
    ALIGN,
    COMPLETE,
    DOMAIN_FILE,
    domain_args,
    domain_problems,
    domain_words,
    output_folder,
)
from wadi2d_qgis.job_builder import Feature, domain_job

from wadi2d.config.schema import RunConfig


def test_a_new_folder_beside_the_run_each_time(tmp_path) -> None:
    first = output_folder(str(tmp_path / "run"))
    assert first == tmp_path / "run_domain"
    first.mkdir()
    (first / DOMAIN_FILE).write_text("{}", encoding="utf-8")
    assert output_folder(str(tmp_path / "run")) == tmp_path / "run_domain_2", "never written over"
    assert output_folder("").is_dir(), "a temporary one with no output folder"


def test_the_command_and_its_refusals() -> None:
    assert domain_args("j.json", "out", "o.geojson", None, None) == ["domain", "j.json", "--out", "out", "--outline", "o.geojson"]
    assert domain_args("j", "o", "a", "k", "c")[-4:] == ["--keep", "k", "--align", "c"]
    assert domain_problems(COMPLETE, True, True, False) == []
    assert any("catchments to align to" in p for p in domain_problems(ALIGN, True, True, False))
    assert any("rough outline" in p for p in domain_problems(COMPLETE, True, False, False))


def test_the_report_in_words() -> None:
    complete = {
        "mode": COMPLETE, "outline_km2": 18.2, "domain_km2": 20.97, "added_km2": 2.9, "removed_km2": 0.13,
        "not_added_km2": 0.4, "catchments_added": [{"km2": 2.5}, {"km2": 0.3}], "slivers_added_km2": 0.1,
        "catchments_removed": [], "slivers_removed_km2": 0.13, "catchments_not_added": [{"km2": 0.4}],
        "kept_lines": 3, "stream_threshold_km2": 1.0, "pixel_m": 10.0, "notes": ["2 holes inside the domain filled, 0.010 km2"],
    }  # fmt: skip
    text = domain_words(complete)
    assert text.startswith(
        "Domain 20.97 km2, the outline of 18.20 km2 completed upstream: 2.90 km2 added, draining in (2 catchments with a "
        "stream over 1 km2, 0.10 km2 in smaller pieces)"
    )
    assert "across kept edges: 0.40 km2 (1 catchment with a stream over 1 km2)." in text
    assert "holes inside the domain filled" in text
    align = {
        "mode": ALIGN, "outline_km2": 20.0, "domain_km2": 20.5, "catchments": 1, "rim_removed_km2": 0.1,
        "gap_added_km2": 0.6, "tolerance_m": 100.0, "cell_m": 30.0, "cells_outside_catchments": 0,
        "outside_catchments_km2": 0.0, "cells_outside_catchments_before": 120, "notes": [],
    }  # fmt: skip
    text = domain_words(align)
    assert "aligned to 1 catchment: a rim of 0.10 km2" in text and "(were 120)" in text


def test_the_job_keeps_the_boundary_lines_where_they_lie(tmp_path) -> None:
    dem = tmp_path / "dem.tif"
    dem.write_bytes(b"x")
    flow = Feature("LineString", [[0.0, 0.0], [0.0, 100.0]], {"kind": "flow", "file": None})
    values = {
        "dem": str(dem), "crs": "EPSG:32640", "dx": 10.0, "manning": 0.04, "duration_h": 1.0, "output": str(tmp_path),
        "extent": (0.0, 0.0, 100.0, 100.0), "rain_mm_h": 10.0, "rain_hours": 1.0, "boundaries": [flow],
        "basin": {"json": None, "settings": {"stream_threshold_km2": 2.0, "lag_method": "hms_kirpich"}},
    }  # fmt: skip
    job = domain_job(values, tmp_path / "d")
    assert job["boundaries"] == [{"kind": "free", "coordinates": [[0.0, 0.0], [0.0, 100.0]]}], "a flow line with no hydrograph yet"
    cfg = RunConfig.model_validate(job)
    assert cfg.basin.stream_threshold_km2 == 2.0, "the basin's own streams"
    assert "hydrology" not in job or not job["hydrology"].get("basin_json"), "no basin of its own"


def test_align_aligns_terrains_domain_before_the_rough_outline() -> None:
    """W106 gap 4: after Complete upstream the domain is the completed layer, and Align reads it, saying which."""
    from wadi2d_qgis.domain_rows import align_source

    which, words = align_source("Domain completed upstream, 1,399.36 km2", "rough outline")
    assert which == "domain" and "Domain completed upstream" in words
    which, words = align_source(None, "rough outline")
    assert which == "outline" and "rough outline" in words and "no domain yet" in words
    assert align_source(None, None) is None
    assert domain_problems(ALIGN, True, False, True, True) == []  # the domain alone is enough to align
    assert any("Terrain's domain or the rough outline" in p for p in domain_problems(ALIGN, True, False, True, False))
