"""Fixtures of the HMS reader tests."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parents[1] / "data" / "hms"


@pytest.fixture(scope="session")
def fixtures() -> Path:
    """The folder of synthetic HMS files, which exercise every parser without the Block 2 data."""
    return FIXTURE_DIR
