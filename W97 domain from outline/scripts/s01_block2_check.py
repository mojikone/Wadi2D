"""W97 check on Block 2: the domain completed from a rough outline and aligned to Basin 3, CPU only.

    python s01_block2_check.py [pixel_m] [sea|all]

``sea`` (the default): W79's sea line is the one kept line. ``all``: the four boundary lines of W79's job, the sea and
the three side outflow lines its edge check opened (Wadi HAT's north line, Wadi Fizh's branch, the 1 km2 north
stream), and the rough outline's move fades to nothing near each of them as near the coast strip.

1. A rough outline: Basin 3's 104 polygons joined, its edge moved 1 to 3 km in or out (out and in alternating along the
   edge, every 1 km a vertex), the move fading to nothing within 3 km of W79's coast strip; the coast strip and the sea
   edge exactly W79's (``inputs/domain_no_rim.geojson``).
2. ``complete_outline`` on it with W79's sea line as the one kept line, at the job's stream threshold (10 km2), on the
   W79 rerun2 job's DEM (GGC 0.5 m read at the analysis pixel).
3. ``align_outline`` of the completed domain to Basin 3's polygons, tolerance 100 m.
4. ``align_outline`` of W79's first domain (polygons + 40 m, ``inputs/domain.geojson``) to Basin 3: W79's own test,
   13 cells outside every polygon away from the coast strip with its hand-made domain, 17,420 with the rim.

Counts are W79's (``s16_domain_no_rim.py``): 20 m cells on the lattice of W79's first domain, centre inside the domain,
outside every polygon, more than 66 m from the coast strip. Writes ``runs/`` (out of git) and ``block2_check.json``.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import shapely
from affine import Affine
from rasterio import features
from shapely.geometry import mapping, shape

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parent
W79 = REPO / "W79 Block 2 four ways"
JOB = W79 / "jobs" / "rerun2_run3_hybrid_aligned.json"
RIM_DOMAIN = W79 / "inputs" / "domain.geojson"
NO_RIM_DOMAIN = W79 / "inputs" / "domain_no_rim.geojson"
RUNS = HERE / "runs"
DX = 20.0
CRS_WKT = __import__("rasterio.crs", fromlist=["CRS"]).CRS.from_epsg(32640).to_wkt()
RIM_M, JOIN_M = 40.0, 46.0
MOVE_MIN, MOVE_SPAN = 1000.0, 2000.0
WAVE_SIZE_M, WAVE_SIGN_M = 7000.0, 20000.0
VERTEX_M, FADE_M = 1000.0, 3000.0

sys.path.insert(0, str(REPO))
from wadi2d.config.schema import BasinSettings, DomainSettings  # noqa: E402
from wadi2d.domain.align import align_outline  # noqa: E402
from wadi2d.domain.files import write_domain  # noqa: E402
from wadi2d.domain.outline import complete_outline  # noqa: E402
from wadi2d.forcing import load_polygons  # noqa: E402
from wadi2d.run import load_job  # noqa: E402


def _geojson(path: Path) -> shapely.Geometry:
    return shape(json.loads(path.read_text(encoding="utf-8"))["features"][0]["geometry"])


def _save(path: Path, geometry: shapely.Geometry) -> None:
    feature = {"type": "Feature", "properties": {}, "geometry": mapping(geometry)}
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}), encoding="utf-8")


def strip_of(old: shapely.Geometry, land: shapely.Geometry) -> shapely.Geometry:
    """W79's coast strip: the domain beyond the polygons + 41 m, its largest piece (s16)."""
    beyond = old.difference(land.buffer(RIM_M + 1.0))
    return max(getattr(beyond, "geoms", [beyond]), key=lambda g: g.area)


def rough_outline(land: shapely.Polygon, strip: shapely.Geometry, coast: shapely.Geometry) -> shapely.Polygon:
    """Basin 3's edge moved 1 to 3 km, in and out in turn, a hand's outline; exact at the coast strip."""
    ring = land.exterior.simplify(200.0).segmentize(VERTEX_M)
    xy = np.asarray(ring.coords)[:-1]
    s = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
    ahead, behind = np.roll(xy, -1, axis=0), np.roll(xy, 1, axis=0)
    t = ahead - behind
    normal = np.column_stack([t[:, 1], -t[:, 0]]) / np.maximum(np.hypot(t[:, 0], t[:, 1]), 1e-9)[:, None]
    if shapely.Polygon(xy + 10.0 * normal).area < land.area:  # point the normals out
        normal = -normal
    size = MOVE_MIN + MOVE_SPAN * np.abs(np.sin(2 * np.pi * s / WAVE_SIZE_M))
    sign = np.where(np.sin(2 * np.pi * s / WAVE_SIGN_M) >= 0.0, 1.0, -1.0)
    near = shapely.distance(coast, shapely.points(xy))
    fade = np.clip(near / FADE_M, 0.0, 1.0)
    moved = shapely.make_valid(shapely.Polygon(xy + (size * sign * fade)[:, None] * normal)).buffer(0)
    moved = max(getattr(moved, "geoms", [moved]), key=lambda g: g.area)
    return shapely.Polygon(shapely.union_all([moved, strip.buffer(JOIN_M)]).exterior)


def w79_count(geom: shapely.Geometry, polys: list, strip: shapely.Geometry, old: shapely.Geometry) -> int:
    """s16's count: 20 m cells inside, outside every polygon, more than 66 m from the coast strip."""
    lattice = shapely.union(old, geom).bounds
    x0, y1 = np.floor(lattice[0] / DX) * DX, np.ceil(lattice[3] / DX) * DX
    shp = (int(np.ceil((y1 - lattice[1]) / DX)), int(np.ceil((lattice[2] - x0) / DX)))
    t = Affine(DX, 0, x0, 0, -DX, y1)
    labels = features.rasterize([(p, 1) for p in polys], out_shape=shp, transform=t, fill=0, dtype="uint8")
    mask = features.geometry_mask([geom], out_shape=shp, transform=t, invert=True)
    jj, ii = np.nonzero(mask & (labels == 0))
    far = shapely.distance(strip, shapely.points(x0 + (ii + 0.5) * DX, y1 - (jj + 0.5) * DX)) > JOIN_M + DX
    return int(far.sum())


def main() -> None:
    pixel = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
    variant = sys.argv[2] if len(sys.argv) > 2 else "sea"
    tag = f"{pixel:g}m" if variant == "sea" else f"{pixel:g}m_{variant}"
    RUNS.mkdir(parents=True, exist_ok=True)
    cfg = load_job(JOB)
    started = time.perf_counter()
    polys = [shapely.make_valid(p).buffer(0) for p in load_polygons(cfg.hydrology).values()]
    joined = shapely.union_all([p.buffer(1.0) for p in polys]).buffer(-1.0)
    land = shapely.Polygon(max(getattr(joined, "geoms", [joined]), key=lambda g: g.area).exterior)
    old, no_rim = _geojson(RIM_DOMAIN), _geojson(NO_RIM_DOMAIN)
    strip = strip_of(old, land)
    sea = shapely.LineString(cfg.boundaries[0].coordinates)
    kept = [sea] if variant == "sea" else [shapely.LineString(b.coordinates) for b in cfg.boundaries]
    rough = rough_outline(land, strip, shapely.union_all(kept))
    _save(RUNS / f"rough_outline_{variant}.geojson", rough)
    edge = shapely.points(np.asarray(rough.exterior.segmentize(100.0).coords))
    off = shapely.distance(land.exterior, edge)
    far = shapely.distance(strip, edge) > FADE_M
    setup_s = time.perf_counter() - started
    out: dict = {
        "pixel_m": pixel,
        "kept": variant,
        "setup_s": round(setup_s, 1),
        "basin3_km2": round(land.area / 1e6, 3),
        "w79_no_rim_km2": round(no_rim.area / 1e6, 3),
        "rough": {
            "km2": round(rough.area / 1e6, 3),
            "edge_off_basin3_m": {
                q: round(float(np.percentile(off[far], p)), 0)
                for q, p in (("p5", 5), ("median", 50), ("p95", 95), ("max", 100))
            },
            "outside_basin3_km2": round(
                rough.difference(land).difference(strip.buffer(JOIN_M)).area / 1e6, 3
            ),
            "basin3_outside_km2": round(land.difference(rough).area / 1e6, 3),
            "cells_outside_every_polygon": w79_count(rough, polys, strip, old),
        },
    }
    basin = cfg.basin.model_copy(update={"analysis_pixel": pixel})
    done = complete_outline(
        cfg, rough, kept, BasinSettings.model_validate(basin.model_dump()), DomainSettings()
    )
    changes = [(c.kind, c.geometry, c.km2, c.catchment, c.x, c.y) for c in done.changes]
    write_domain(RUNS / f"completed_{tag}", done.polygon, "completed", CRS_WKT, done.report, changes)
    dom = done.polygon
    out["completed"] = {
        **{k: v for k, v in done.report.items() if k not in ("catchments_added", "catchments_removed")},
        "catchments_added": len(done.report["catchments_added"]),
        "catchments_removed": len(done.report["catchments_removed"]),
        "against_basin3": {
            "domain_outside_basin3_km2": round(
                dom.difference(land).difference(strip.buffer(JOIN_M)).area / 1e6, 3
            ),
            "basin3_outside_domain_km2": round(land.difference(dom).area / 1e6, 3),
            "against_w79_no_rim_symdiff_km2": round(dom.symmetric_difference(no_rim).area / 1e6, 3),
            "cells_outside_every_polygon": w79_count(dom, polys, strip, old),
        },
    }
    aligned = align_outline(dom, polys, DomainSettings(), kept, DX)
    write_domain(RUNS / f"completed_aligned_{tag}", aligned.polygon, "completed and aligned", CRS_WKT,
                 aligned.report, [])  # fmt: skip
    a = aligned.polygon
    out["completed_aligned"] = {
        **aligned.report,
        "basin3_outside_domain_km2": round(land.difference(a).area / 1e6, 3),
        "against_w79_no_rim_symdiff_km2": round(a.symmetric_difference(no_rim).area / 1e6, 3),
        "cells_outside_every_polygon": w79_count(a, polys, strip, old),
    }
    if variant == "sea":
        w79 = align_outline(old, polys, DomainSettings(), [sea], DX)
        _save(RUNS / "w79_domain_aligned.geojson", w79.polygon)
        out["w79_rim_domain_aligned"] = {
            **w79.report,
            "cells_outside_every_polygon_before": w79_count(old, polys, strip, old),
            "cells_outside_every_polygon": w79_count(w79.polygon, polys, strip, old),
            "w79_by_hand": w79_count(no_rim, polys, strip, old),
            "against_w79_no_rim_symdiff_km2": round(w79.polygon.symmetric_difference(no_rim).area / 1e6, 3),
        }
    out["total_s"] = round(time.perf_counter() - started, 1)
    (HERE / f"block2_check_{tag}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
