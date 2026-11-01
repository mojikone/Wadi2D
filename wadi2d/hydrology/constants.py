"""Unit conversions of the lumped engine, each set once (engineering rule 2)."""

from __future__ import annotations

from wadi2d.storm.base import PERCENT

__all__ = ["M3_PER_MM_KM2", "MM_PER_INCH", "PERCENT", "SECONDS_PER_DAY", "SECONDS_PER_MINUTE"]

SECONDS_PER_MINUTE = 60.0
SECONDS_PER_DAY = 86400.0
M3_PER_MM_KM2 = 1000.0
"""1 mm over 1 km2 is 1000 m3."""
MM_PER_INCH = 25.4
