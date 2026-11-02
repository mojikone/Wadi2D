"""Rain files as :class:`~wadi2d.storm.rain_frames.RainFrames`. Interface: :func:`read_rain`, :func:`rain_format`, :func:`rain_choices`.

A format is one new file holding a reader registered in :data:`RAIN_READERS` and a listing in :data:`RAIN_CHOICES`, so
radar and satellite products arrive without touching the storm, the cells or the dock.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np

from wadi2d.storm.rain_frames import RainFrames, RainSpec
from wadi2d.storm.registry import Registry

NETCDF, DSS, GEOTIFF = "netcdf", "dss", "geotiff"
NETCDF_SUFFIXES = (".nc", ".nc4", ".cdf", ".netcdf")
DSS_SUFFIX = ".dss"

RAIN_READERS: Registry[RainFrames] = Registry("rain file")
"""Readers by format: ``reader(path=..., spec=...)``."""
RAIN_CHOICES: dict[str, Callable[[Path], list[str]]] = {}
"""What a file offers for ``RainSpec.variable``, by format."""


def rain_format(path: str | Path) -> str:
    """The format of a rain source, from what it is."""
    source = Path(path)
    if source.is_dir():
        return GEOTIFF
    if source.suffix.lower() in NETCDF_SUFFIXES:
        return NETCDF
    if source.suffix.lower() == DSS_SUFFIX:
        return DSS
    raise ValueError(f"{source.name}: rain comes as a NetCDF file, a DSS file, or a folder of GeoTIFFs")


def rain_choices(path: str | Path) -> list[str]:
    """The rain a file offers; more than one means the job has to say which."""
    return RAIN_CHOICES[rain_format(path)](Path(path))


def read_rain(path: str | Path, spec: RainSpec, start: str | None = None) -> RainFrames:
    """The frames of a rain source; ``start`` is the date the run starts at, else the start of the first period."""
    frames = RAIN_READERS.build(rain_format(path), path=Path(path), spec=spec)
    return frames if start is None else frames.since(np.datetime64(start, "s"))


from wadi2d.io.rain import dss_grid, geotiff_stack, netcdf  # noqa: E402  registers the formats

__all__ = [
    "DSS",
    "GEOTIFF",
    "NETCDF",
    "RAIN_CHOICES",
    "RAIN_READERS",
    "dss_grid",
    "geotiff_stack",
    "netcdf",
    "rain_choices",
    "rain_format",
    "read_rain",
]
