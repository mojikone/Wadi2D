"""A folder of GeoTIFFs, one frame each, in the order of their names; ``rain_2`` comes before ``rain_10``.

A GeoTIFF has no time of its own, so the job gives the period and the frames run from minute zero with no date.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import rasterio

from wadi2d.io.rain import GEOTIFF, RAIN_CHOICES, RAIN_READERS
from wadi2d.storm.rain_frames import RainFrames, RainSpec, depth_in_mm

SUFFIXES = (".tif", ".tiff")
DEFAULT_UNITS = "mm"
DIGITS = re.compile(r"(\d+)")


def _name_order(path: Path) -> list[object]:
    return [int(part) if part.isdigit() else part.lower() for part in DIGITS.split(path.name)]


def stack_files(folder: Path) -> list[Path]:
    found = [p for p in folder.iterdir() if p.suffix.lower() in SUFFIXES]
    if not found:
        raise ValueError(f"{folder.name}: no GeoTIFF in this folder")
    return sorted(found, key=_name_order)


@RAIN_READERS.register(GEOTIFF)
def read_stack(path: Path, spec: RainSpec) -> RainFrames:
    if spec.interval_min is None:
        raise ValueError(f"{path.name}: a folder of GeoTIFFs needs the length of each period")
    files = stack_files(path)
    bands = []
    with rasterio.open(files[0]) as first:
        transform, crs, shape = first.transform, first.crs, first.shape
    if transform.b != 0.0 or transform.d != 0.0 or transform.e >= 0.0:
        raise ValueError(f"{files[0].name}: rain must sit on a north-up grid")
    for file in files:
        with rasterio.open(file) as src:
            if src.transform != transform or src.shape != shape or src.crs != crs:
                raise ValueError(f"{file.name} is not on the same grid as {files[0].name}")
            bands.append(src.read(1, masked=True).astype(np.float64).filled(np.nan))
    period = np.full(len(files), spec.interval_min)
    depths = depth_in_mm(np.stack(bands), DEFAULT_UNITS, spec.units, period)
    starts = spec.interval_min * np.arange(len(files), dtype=np.float64)
    return RainFrames(
        depths, starts, starts + spec.interval_min, transform.c, transform.f, transform.a, -transform.e,
        crs.to_wkt() if crs is not None else "",
    )  # fmt: skip


def stack_choices(path: Path) -> list[str]:
    """A folder is one series."""
    return [path.name]


RAIN_CHOICES[GEOTIFF] = stack_choices
