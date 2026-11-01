"""The grid cache: tables are the only expensive artefact, so they are kept by a hash of what made them.

The key hashes DEM identity, extent, cell size, terrain objects, table settings and Manning. It is stored inside
the file too, so a renamed or truncated file is a miss, never a wrong grid.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from wadi2d.config.schema import FORMAT_VERSION
from wadi2d.grid.tiles import TileGrid
from wadi2d.tables.builder import GridTables

CACHE_FORMAT = "1"
GZIP_LEVEL = 1


def cache_key(parts: dict[str, Any]) -> str:
    """Stable hash of a JSON-serialisable description of the grid."""
    text = json.dumps({"format": FORMAT_VERSION, "cache": CACHE_FORMAT, **parts}, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def cache_path(folder: str | Path, key: str) -> Path:
    return Path(folder) / f"grid_{key}.h5"


def save_tables(path: str | Path, tables: GridTables, key: str) -> Path:
    """Write through a temporary name, so an interrupted build leaves no file that looks finished."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    grid = tables.grid
    with h5py.File(tmp, "w") as f:
        f.attrs["key"] = key
        f.attrs["cache_format"] = CACHE_FORMAT
        f.attrs["x0"] = grid.x0
        f.attrs["y0"] = grid.y0
        f.attrs["dx"] = grid.dx
        f.create_dataset("mask", data=grid.mask, compression="gzip", compression_opts=GZIP_LEVEL)
        for field in fields(GridTables):
            if field.name == "grid":
                continue
            a = getattr(tables, field.name)
            f.create_dataset(
                field.name, data=a, compression="gzip", compression_opts=GZIP_LEVEL, shuffle=True
            )
    tmp.replace(out)
    return out


def load_tables(path: str | Path, key: str) -> GridTables | None:
    """The tables, or None when the file is missing, unreadable or was built from something else."""
    source = Path(path)
    if not source.is_file():
        return None
    try:
        with h5py.File(source, "r") as f:
            if f.attrs.get("key") != key or f.attrs.get("cache_format") != CACHE_FORMAT:
                return None
            grid = TileGrid(float(f.attrs["x0"]), float(f.attrs["y0"]), float(f.attrs["dx"]), f["mask"][()])
            arrays = {
                field.name: np.asarray(f[field.name][()])
                for field in fields(GridTables)
                if field.name != "grid"
            }
    except (OSError, KeyError):
        return None
    return GridTables(grid=grid, **arrays)
