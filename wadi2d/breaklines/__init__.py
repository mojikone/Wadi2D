"""Suggested breaklines: lines the ground asks for, written for review, never used unread.

``suggest`` reads the job's ground at the mesher's analysis pixel, walks its streams, places a bank line either
side of every defined wadi, finds raised crests by the top-hat, and writes one editable line layer with a kind, a
height, a score and a plain reason per line, the ones that matter most first. Every vertex carries the ground
elevation at the line, so the user feeds the layer to the Structures section as crest lines as it is. A crest face
is not free: it passes at most critical flow and sets the time step, so a line the flood crosses along its length
costs the peak (W26: Bidah 7 to 15 %). The thalwegs go to a second layer for reference; they are never breaklines
(his rule of 2026-11-01).
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
    DEPTH_MAP,
    FILE,
    GROUND,
    LAYER,
    ROAD,
    THALWEG_COLUMNS,
    THALWEG_LAYER,
    Settings,
)
from wadi2d.breaklines.thalweg import Thalweg, thalwegs
from wadi2d.breaklines.window import Window, flow_fields, read_field, read_window
from wadi2d.config.schema import RefineLine, RunConfig
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


def _rows(
    win: Window, banks: list[Bank], crests: list[Crest], band: tuple[float, int, float]
) -> tuple[list[tuple], list[shapely.Geometry]]:
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
    counts: dict[str, int] = {}
    named = []
    for n in order:
        kind = rows[n][0]
        counts[kind] = counts.get(kind, 0) + 1
        named.append((f"{kind} {counts[kind]}", *rows[n], *band))
    return named, [shapes[n] for n in order]


def band_of(cfg: RunConfig) -> tuple[float, int, float]:
    """What the Mesh table reads from the layer: the finest cell beside the line, the schema's rows, the coarsest cell."""
    return cfg.grid.dx, int(RefineLine.model_fields["rows"].default), cfg.mesh.coarse_dx


def layers(
    win: Window,
    streams: list[Thalweg],
    banks: list[Bank],
    crests: list[Crest],
    band: tuple[float, int, float],
) -> list[VectorLayer]:
    rows, shapes = _rows(win, banks, crests, band)
    lines = VectorLayer(LAYER, dict(COLUMNS), rows, shapes, LINES, has_z=True)
    ref = VectorLayer(
        THALWEG_LAYER,
        dict(THALWEG_COLUMNS),
        [(t.area_km2, t.incised_m, length_of(t.xy)) for t in streams],
        [shapely.LineString(t.xy) for t in streams],
        LINES,
    )
    return [lines, ref]


def bank_rule(settings: Settings, from_depth: bool) -> str:
    """The rule that placed the banks, in words for the layer's reader."""
    if from_depth:
        return f"edge of the flooded course of {settings.bank_depth_map}, deeper than {settings.bank_depth_m:g} m"
    if settings.bank_method == "slope":
        return (
            f"edge of the floodplain, where the ground climbs over {100 * settings.bank_slope:g} % for {settings.bank_run_m:g} m"
            f" and stands {settings.bank_rise_m:g} m over the bed"
        )
    return f"ground {settings.bank_rise_m:g} m over the bed of the wadi"


def suggest(cfg: RunConfig, out: str | Path, settings: Settings | None = None) -> dict:
    """Write ``suggested_breaklines.gpkg`` in ``out`` and return what it holds; the settings are the job's
    ``breaklines`` section unless given."""
    settings = cfg.breaklines if settings is None else settings
    win = read_window(cfg)
    depth = None
    if settings.bank_depth_map:
        if not Path(settings.bank_depth_map).is_file():
            raise ValueError(f"the depth map for the banks is not a file: {settings.bank_depth_map}")
        depth = read_field(win, settings.bank_depth_map)
    area, pointer = flow_fields(win)
    streams = thalwegs(
        win, area, pointer, cfg.mesh, settings.simplify_pixels * win.pixel, settings.smooth_vertices
    )
    banks = all_banks(win, streams, cfg.mesh, settings, depth)
    crests = crests_of(win, streams, cfg.mesh.incision_depth, settings)
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    path = write_geopackage(folder / FILE, layers(win, streams, banks, crests, band_of(cfg)), win.crs)
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
        "banks_from": DEPTH_MAP if depth is not None else GROUND,
        "bank_rule": bank_rule(settings, depth is not None),
        "bank_km": round(sum(length_of(b.xy) for b in banks) / 1000.0, 2),
        "crest_km": round(sum(length_of(c.xy) for c in crests) / 1000.0, 2),
        "thalweg_km": round(sum(length_of(t.xy) for t in streams) / 1000.0, 2),
    }


__all__ = ["DEFAULTS", "FILE", "LAYER", "THALWEG_LAYER", "Settings", "bank_rule", "layers", "suggest"]
