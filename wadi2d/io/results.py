"""results.h5: maxima, map snapshots, series and the resolved configuration; CSV series beside it.

Layout (``format_version`` attribute at the root): ``maxima/<name>``; ``maps/t<seconds>/<name>``;
``series/points/<name>/<quantity>`` and ``series/lines/<name>/<quantity>``, each with its ``t_s``; the balance as
root attributes. Maps are (ny, nx) float32 with the grid origin in the root attributes.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import h5py
import numpy as np

from wadi2d.config.schema import FORMAT_VERSION
from wadi2d.grid.tiles import TileGrid

GZIP_LEVEL = 1
CHUNK = 128


def safe_name(name: str) -> str:
    """A name fit for a file: letters, digits, dot, dash and underscore."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "unnamed"


class Results:
    """An open results file; snapshots append, so a stopped run keeps what it wrote."""

    def __init__(
        self, path: str | Path, grid: TileGrid, crs_wkt: str, config_json: str, append: bool = False
    ) -> None:
        self.path = Path(path)
        self.f = h5py.File(self.path, "a" if append and self.path.exists() else "w")
        if "mask" in self.f:
            return
        a = self.f.attrs
        a["format_version"] = FORMAT_VERSION
        a["x0"], a["y0"], a["dx"] = grid.x0, grid.y0, grid.dx
        a["crs"] = crs_wkt
        a["config"] = config_json
        self.f.create_dataset("mask", data=grid.mask, compression="gzip", compression_opts=GZIP_LEVEL)

    def _map(self, group: h5py.Group, name: str, a: np.ndarray) -> None:
        chunks = (min(CHUNK, a.shape[0]), min(CHUNK, a.shape[1]))
        group.create_dataset(
            name, data=a.astype(np.float32), compression="gzip", compression_opts=GZIP_LEVEL, chunks=chunks
        )

    def snapshot(self, t: float, fields: dict[str, np.ndarray]) -> None:
        group = self.f.require_group("maps").require_group(f"t{round(t):09d}")
        group.attrs["t_s"] = t
        for name, a in fields.items():
            if name not in group:
                self._map(group, name, a)
        self.f.flush()

    def maxima(self, fields: dict[str, np.ndarray]) -> None:
        group = self.f.require_group("maxima")
        for name, a in fields.items():
            if name in group:
                del group[name]
            self._map(group, name, a)

    def series(self, kind: str, name: str, t: np.ndarray, columns: dict[str, np.ndarray]) -> None:
        group = self.f.require_group(f"series/{kind}").require_group(safe_name(name))
        group.attrs["name"] = name
        for key, a in {"t_s": t, **columns}.items():
            if key in group:
                del group[key]
            group.create_dataset(key, data=np.asarray(a, dtype=np.float64))

    def attributes(self, values: dict[str, float | str]) -> None:
        for key, value in values.items():
            self.f.attrs[key] = value

    def close(self) -> None:
        self.f.close()


def write_series_csv(path: str | Path, t: np.ndarray, columns: dict[str, np.ndarray]) -> Path:
    """t_s plus one column per quantity."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    names = list(columns)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["t_s", *names])
        rows = zip(t, *(columns[n] for n in names), strict=True)
        writer.writerows([f"{v:.6g}" if k else f"{v:.3f}" for k, v in enumerate(row)] for row in rows)
    return out
