"""Suggested breaklines: lines the ground asks for, written for review, never used unread.

``suggest`` reads the job's ground at the mesher's analysis pixel, walks its streams, places a bank line either
side of every defined wadi, finds raised crests by the top-hat, and writes one editable line layer with a kind, a
height, a score and a plain reason per line, the ones that matter most first. Every vertex carries the ground
elevation at the line, so the user feeds the layer to the Structures section as crest lines as it is: a crest at
ground level only makes the faces under the line watertight, it raises nothing. The thalwegs go to a second layer
for reference; they are never breaklines (his rule of 2026-11-01).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import shapely
from scipy import ndimage

from wadi2d.breaklines.banks import Bank, all_banks
from wadi2d.breaklines.crests import Crest, crests_of
from wadi2d.breaklines.pixels import length_of
from wadi2d.breaklines.settings import (
    BANK,
    COLUMNS,
    DAM,
    FILE,
    LAYER,
    ROAD,
    THALWEG_COLUMNS,
    THALWEG_LAYER,
    Settings,
)
from wadi2d.breaklines.thalweg import Thalweg, thalwegs
from wadi2d.breaklines.window import Window, flow_fields, read_window
from wadi2d.config.schema import RunConfig
from wadi2d.io.geopackage import LINES, VectorLayer, write_geopackage

TOP_PIXELS = 3
"""A crest vertex reads the highest analysis pixel of this square around it: the ridge, not its flank."""
DEFAULTS = Settings()


def _why(kind: str, height: float, length: float, area: float, side: str, slope: float = 0.0) -> str:
    if kind == BANK:
        return f"{side} bank of a wadi draining {area:.1f} km2, {height:.1f} m below the ground around it"
    where = f"stands {height:.1f} m above its ground over {length:.0f} m, on ground at {100 * slope:.0f} %"
    if kind == DAM:
        return f"{where}, and crosses a wadi draining {area:.1f} km2: a dam, or a road with a culvert"
    if kind == ROAD:
        return f"{where}, straight: a road or a long dyke"
    return where


def _filled(z: np.ndarray) -> np.ndarray:
    valid = np.isfinite(z)
    if valid.all():
        return z
    nearest = ndimage.distance_transform_edt(~valid, return_distances=False, return_indices=True)
    return z[tuple(nearest)]


def _with_z(xy: np.ndarray, z: np.ndarray) -> shapely.LineString:
    return shapely.LineString(np.column_stack((xy[:, 0], xy[:, 1], z)))


def _rows(win: Window, banks: list[Bank], crests: list[Crest]) -> tuple[list[tuple], list[shapely.Geometry]]:
    ground = _filled(win.z)
    ridge = ndimage.maximum_filter(ground, TOP_PIXELS, mode="nearest")
    rows, shapes = [], []
    for bank in banks:
        length = length_of(bank.xy)
        rows.append((BANK, bank.side, bank.incised_m, length, bank.area_km2, 0.0, bank.incised_m * length,
                     _why(BANK, bank.incised_m, length, bank.area_km2, bank.side)))  # fmt: skip
        shapes.append(_with_z(bank.xy, win.sample(ground, bank.xy)))
    for crest in crests:
        length = length_of(crest.xy)
        rows.append((crest.kind, "", crest.height_m, length, crest.crossed_km2, crest.slope, crest.height_m * length,
                     _why(crest.kind, crest.height_m, length, crest.crossed_km2, "", crest.slope)))  # fmt: skip
        shapes.append(_with_z(crest.xy, win.sample(ridge, crest.xy, order=0)))
    order = sorted(range(len(rows)), key=lambda n: -rows[n][6])
    return [rows[n] for n in order], [shapes[n] for n in order]


def layers(win: Window, streams: list[Thalweg], banks: list[Bank], crests: list[Crest]) -> list[VectorLayer]:
    rows, shapes = _rows(win, banks, crests)
    lines = VectorLayer(LAYER, dict(COLUMNS), rows, shapes, LINES, has_z=True)
    ref = VectorLayer(
        THALWEG_LAYER,
        dict(THALWEG_COLUMNS),
        [(t.area_km2, t.incised_m, length_of(t.xy)) for t in streams],
        [shapely.LineString(t.xy) for t in streams],
        LINES,
    )
    return [lines, ref]


def suggest(cfg: RunConfig, out: str | Path, settings: Settings = DEFAULTS) -> dict:
    """Write ``suggested_breaklines.gpkg`` in ``out`` and return what it holds."""
    win = read_window(cfg)
    area, pointer = flow_fields(win)
    streams = thalwegs(
        win, area, pointer, cfg.mesh, settings.simplify_pixels * win.pixel, settings.smooth_vertices
    )
    banks = all_banks(win, streams, cfg.mesh, settings)
    crests = crests_of(win, streams, cfg.mesh.incision_depth, settings)
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    path = write_geopackage(folder / FILE, layers(win, streams, banks, crests), win.crs)
    kinds = {}
    for crest in crests:
        kinds[crest.kind] = kinds.get(crest.kind, 0) + 1
    return {
        "path": str(path),
        "layer": LAYER,
        "thalweg_layer": THALWEG_LAYER,
        "pixel_m": win.pixel,
        "banks": len(banks),
        "crests": len(crests),
        "crest_kinds": kinds,
        "thalwegs": len(streams),
        "bank_km": round(sum(length_of(b.xy) for b in banks) / 1000.0, 2),
        "crest_km": round(sum(length_of(c.xy) for c in crests) / 1000.0, 2),
        "thalweg_km": round(sum(length_of(t.xy) for t in streams) / 1000.0, 2),
    }


__all__ = ["FILE", "LAYER", "THALWEG_LAYER", "Settings", "layers", "suggest"]
