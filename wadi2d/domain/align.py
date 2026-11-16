"""A domain's edge aligned to catchment polygons (W97): generated ones, the user's own or an HMS basin's.

Where the outline runs close outside the catchments' outer edge, the band between them is rain-on-grid ground in a
hybrid run, the rim W79 found. Where it runs close inside, a strip of catchment lies off the domain. Both are thin:

- the **rim**, the parts of the outline outside every catchment narrower than twice the tolerance and within that of
  the catchments, is removed;
- the **gap**, the parts of the catchments outside the outline as narrow and within twice the tolerance of it, is added.

Thin is read by an opening (shrink by the tolerance, grow back): a wide piece outside the catchments, the coast strip
between them and the sea, stays with the band that joins it to them. An edge within ``keep_m`` of a kept line stays as
drawn. So the edge lies on the catchments' own outer edge wherever the two met, and on the outline elsewhere.

Interface: :class:`Aligned`, :func:`align_outline`, :func:`outside_cells`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import shapely
from rasterio import features
from rasterio.transform import Affine

from wadi2d.config.schema import DomainSettings

RIM, GAP = "rim removed", "gap added"


@dataclass
class Aligned:
    polygon: shapely.Polygon
    rim: shapely.Geometry
    gap: shapely.Geometry
    report: dict = field(default_factory=dict)


def _joined(catchments: list[shapely.Geometry], join_m: float) -> shapely.Geometry:
    valid = [shapely.make_valid(c).buffer(0) for c in catchments]
    whole = shapely.union_all([c.buffer(join_m) for c in valid]) if join_m > 0.0 else shapely.union_all(valid)
    return whole.buffer(-join_m) if join_m > 0.0 else whole


def _thin(region: shapely.Geometry, tolerance: float) -> shapely.Geometry:
    """What an opening by ``tolerance`` takes away: the parts narrower than twice it."""
    if region.is_empty:
        return region
    return region.difference(region.buffer(-tolerance).buffer(tolerance * 1.001))


def _polygonal(geometry: shapely.Geometry) -> shapely.Geometry:
    parts = [g for g in getattr(geometry, "geoms", [geometry]) if g.geom_type in ("Polygon", "MultiPolygon")]
    return shapely.union_all(parts) if parts else shapely.Polygon()


def outside_cells(
    polygon: shapely.Geometry, catchments: shapely.Geometry, cell_m: float, bounds: tuple | None = None
) -> int:
    """Cells of ``cell_m`` on the lattice through the origin whose centre lies in the polygon and outside every
    catchment: what a hybrid run with every catchment lumped would rain on. ``bounds`` widens the lattice."""
    b = polygon.bounds if bounds is None else bounds
    x0, y0 = np.floor(b[0] / cell_m) * cell_m, np.ceil(b[3] / cell_m) * cell_m
    shape = (int(np.ceil((y0 - b[1]) / cell_m)), int(np.ceil((b[2] - x0) / cell_m)))
    t = Affine(cell_m, 0.0, x0, 0.0, -cell_m, y0)
    inside = features.geometry_mask([polygon], out_shape=shape, transform=t, invert=True)
    under = features.geometry_mask([catchments], out_shape=shape, transform=t, invert=True)
    return int((inside & ~under).sum())


def align_outline(
    outline: shapely.Geometry,
    catchments: list[shapely.Geometry],
    settings: DomainSettings,
    kept: list[shapely.Geometry] | None = None,
    cell_m: float | None = None,
) -> Aligned:
    """The outline with its edge on the catchments' outer edge where the two run within the tolerance."""
    if not catchments:
        raise ValueError("no catchment polygon to align to")
    started = time.perf_counter()
    tol = settings.align_tolerance_m
    whole = _joined(catchments, settings.join_m)
    outline = shapely.make_valid(outline)
    rim = _polygonal(_thin(outline.difference(whole), tol).intersection(whole.buffer(2.0 * tol)))
    gap = _polygonal(_thin(whole.difference(outline), tol).intersection(outline.buffer(2.0 * tol)))
    if kept:
        zone = shapely.union_all(kept).buffer(settings.keep_m)
        rim, gap = rim.difference(zone), gap.difference(zone)
    shaped = shapely.make_valid(outline.difference(rim).union(gap))
    parts = sorted((g for g in getattr(shaped, "geoms", [shaped]) if g.geom_type == "Polygon"),
                   key=lambda g: g.area, reverse=True)  # fmt: skip
    if not parts:
        raise ValueError("nothing of the outline is left after the alignment")
    domain = parts[0]
    filled = shapely.set_precision(shapely.Polygon(domain.exterior), 0.01)
    notes: list[str] = []
    apart = sum(p.area for p in parts[1:]) / 1e6
    if apart > 0.0:
        notes.append(f"{len(parts) - 1} pieces apart from the domain left out, {apart:.4f} km2")
    if domain.interiors:
        notes.append(
            f"{len(domain.interiors)} holes inside the domain filled, {(filled.area - domain.area) / 1e6:.4f} km2"
        )
    beyond = filled.difference(whole)
    report = {
        "tolerance_m": tol,
        "catchments": len(catchments),
        "outline_km2": round(outline.area / 1e6, 4),
        "domain_km2": round(filled.area / 1e6, 4),
        "rim_removed_km2": round(rim.area / 1e6, 4),
        "gap_added_km2": round(gap.area / 1e6, 4),
        "outside_catchments_km2": round(beyond.area / 1e6, 4),
        "outside_catchments_thin_km2": round(
            _thin(beyond, tol).intersection(whole.buffer(2.0 * tol)).area / 1e6, 4
        ),
        "catchments_outside_km2": round(whole.difference(filled).area / 1e6, 4),
        "notes": notes,
    }
    if cell_m is not None:
        report["cell_m"] = cell_m
        both = shapely.union(outline, filled).bounds
        report["cells_outside_catchments_before"] = outside_cells(outline, whole, cell_m, both)
        report["cells_outside_catchments"] = outside_cells(filled, whole, cell_m, both)
    report["seconds"] = round(time.perf_counter() - started, 1)
    return Aligned(filled, rim, gap, report)
