# Wadi2D QGIS plugin tests. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Puts the plugin package on the path; none of these fixtures needs QGIS."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugin"))
sys.path.insert(0, str(ROOT / "tools"))

FAKE_ENGINE = Path(__file__).with_name("fake_engine.py")


@pytest.fixture
def schema():
    """The frozen dump of the engine's JSON Schema, wrapped for the plugin."""
    from wadi2d_qgis.job_builder import SchemaView

    return SchemaView(json.loads(Path(__file__).with_name("schema_sample.json").read_text(encoding="utf-8")))


@pytest.fixture
def fake_engine() -> Path:
    return FAKE_ENGINE
