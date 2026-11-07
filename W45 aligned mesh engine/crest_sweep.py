"""Road and dam detection through the Suggest command itself, on a small window of the full-extent ground across the
Batinah Highway, the one surveyed line he named (W5): his try-and-error of 2026-11-07 for the crest settings.

Each setting runs ``suggest`` on a 4 km by 4 km job at 20 m (the ground read at 5 m) and is scored as W5 scored the
top-hat: the share of the highway centre line within 30 m of a suggested crest, the crest length farther than that
from it (other roads, dykes, field bunds, noise, which no layer separates), and how many of the lines on the highway
are read as ``road``. The sweep is the crest height, the disc radius and the ground slope limit.

    .venv\\Scripts\\python "W45 aligned mesh engine\\crest_sweep.py" <out folder>
"""

from __future__ import annotations

import itertools
import json
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
import shapely  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "W45 aligned mesh engine"))
from bed_types import hillshade  # noqa: E402
from wadi2d.breaklines import suggest  # noqa: E402
from wadi2d.breaklines.settings import BANK  # noqa: E402
from wadi2d.config.schema import RunConfig  # noqa: E402

DEM = ROOT / "W2 full extent run" / "terrain" / "NSA5_COP30_blend.tif"
ROAD = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\SHP\Roads\Bathinah Highway CL.shp")
FRAME = shapely.box(410964, 2699707, 458976, 2742718)
HALF = 2000.0
REACH_M = 30.0
HEIGHTS = (0.3, 0.5, 1.0)
DISCS = (20.0, 40.0, 80.0)
SLOPES = (0.10, 0.15, 0.30)


def highway() -> shapely.LineString:
    import fiona
    from pyproj import Transformer

    with fiona.open(ROAD) as src:
        crs = src.crs
        parts = [shapely.geometry.shape(f["geometry"]) for f in src]
    road = shapely.union_all(parts)
    if crs and crs.to_epsg() != 32640:
        tf = Transformer.from_crs(crs, "EPSG:32640", always_xy=True)
        road = shapely.transform(road, lambda xy: np.column_stack(tf.transform(xy[:, 0], xy[:, 1])))
    road = shapely.line_merge(road.intersection(FRAME))
    return max(road.geoms, key=lambda g: g.length) if hasattr(road, "geoms") else road


def job(box: tuple[float, float, float, float], out: Path, settings: dict) -> RunConfig:
    return RunConfig.model_validate({
        "grid": {"dx": 20.0, "extent": list(box), "cache_dir": str(out / "cache")},
        "terrain": {"dem": str(DEM), "manning": 0.04},
        "mesh": {"analysis_pixel": 5.0},
        "breaklines": settings,
    })  # fmt: skip


def crests(path: str) -> list[tuple[shapely.LineString, dict]]:
    import fiona

    out = []
    with fiona.open(path, layer="breaklines") as src:
        for f in src:
            p = dict(f["properties"])
            if p.get("kind") == BANK:
                continue
            g = shapely.geometry.shape(f["geometry"])
            out.append((shapely.force_2d(g), p))
    return out


def score(lines: list[tuple[shapely.LineString, dict]], road: shapely.LineString) -> dict:
    if not lines:
        return {"recall": 0.0, "km_elsewhere": 0.0, "km_on": 0.0, "road_kind_on": 0, "lines": 0}
    union = shapely.union_all([g for g, _p in lines])
    near = road.buffer(REACH_M)
    found = road.intersection(union.buffer(REACH_M)).length
    on = sum(g.intersection(near).length for g, _p in lines)
    off = sum(g.difference(near).length for g, _p in lines)
    on_lines = [g for g, _p in lines if g.intersection(near).length > 0.5 * g.length]
    road_kind = sum(1 for g, p in lines if p.get("kind") == "road" and g.intersection(near).length > 0.5 * g.length)
    lengths = [g.length for g in on_lines]
    straight = [shapely.Point(g.coords[0]).distance(shapely.Point(g.coords[-1])) / g.length for g in (shapely.get_parts(shapely.line_merge(g))[0] if g.geom_type != "LineString" else g for g in on_lines) if g.length > 0]
    return {
        "recall": round(found / road.length, 3), "km_elsewhere": round(off / 1000.0, 2), "km_on": round(on / 1000.0, 2),
        "road_kind_on": road_kind, "lines": len(lines), "pieces_on": len(on_lines),
        "on_length_median_m": round(float(np.median(lengths)), 0) if lengths else None,
        "on_length_max_m": round(float(np.max(lengths)), 0) if lengths else None,
        "on_straightness_median": round(float(np.median(straight)), 3) if straight else None,
    }


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    road = highway()
    p = road.interpolate(0.4, normalized=True)
    box = (p.x - HALF, p.y - HALF, p.x + HALF, p.y + HALF)
    piece = road.intersection(shapely.box(*box))
    print(f"window {box}, highway inside {piece.length / 1000:.2f} km")
    settings = [{"crest_height_m": h, "disc_radius_m": d, "ground_slope_max": 0.15} for h, d in itertools.product(HEIGHTS, DISCS)]
    settings += [{"crest_height_m": 0.5, "disc_radius_m": 40.0, "ground_slope_max": s} for s in SLOPES if s != 0.15]
    table = []
    kept = {}
    for n, s in enumerate(settings):
        folder = out / f"s{n:02d}"
        t0 = time.perf_counter()
        summary = suggest(job(box, out, s), folder)
        lines = crests(summary["path"])
        row = {**s, **score(lines, piece), "seconds": round(time.perf_counter() - t0, 1), "banks": summary["banks"]}
        table.append(row)
        kept[n] = lines
        print(f"  height {s['crest_height_m']:.1f} disc {s['disc_radius_m']:.0f} slope {s['ground_slope_max']:.2f}: recall {row['recall']:.2f}, {row['km_on']} km on in {row['pieces_on']} pieces (median {row['on_length_median_m']} m, longest {row['on_length_max_m']} m, straightness {row['on_straightness_median']}), {row['km_elsewhere']} km elsewhere, {row['road_kind_on']} read as road, {row['lines']} crests, {row['seconds']} s")
    (out / "crest_sweep.json").write_text(json.dumps({"box": box, "highway_km": piece.length / 1000.0, "rows": table}, indent=1), encoding="utf-8")
    # the figure: the three settings with the most highway found per km elsewhere, among those finding over 70 %
    # the three corners worth seeing: W26's setting, the lowest height on the widest disc, the highest height on it
    shown = [(0.5, 40.0), (0.3, 80.0), (1.0, 80.0)]
    best = [next(n for n, r in enumerate(table) if (r["crest_height_m"], r["disc_radius_m"]) == pair and r["ground_slope_max"] == 0.15) for pair in shown]
    fig, axes = plt.subplots(1, 3, figsize=(19, 6.6), dpi=120)
    with rasterio.open(DEM) as dem:
        shade, _z = hillshade(dem, box)
    for ax, n in zip(axes, best, strict=False):
        ax.imshow(shade, extent=(box[0], box[2], box[1], box[3]), cmap="gray", vmin=0, vmax=1)
        for part in getattr(piece, "geoms", [piece]):  # the highway under the crests, so a crest on it shows
            xy = np.asarray(part.coords)
            ax.plot(xy[:, 0], xy[:, 1], color="#9fd8f5", lw=4.0, alpha=0.8)
        for g, prop in kept[n]:
            colour = {"road": "#303030", "dam": "#d40000"}.get(prop.get("kind"), "#e07b00")
            for part in shapely.get_parts(g):
                xy = np.asarray(part.coords)
                ax.plot(xy[:, 0], xy[:, 1], color=colour, lw=1.0)
        r = table[n]
        ax.set_title(f"height {r['crest_height_m']} m, disc {r['disc_radius_m']:.0f} m, slope {r['ground_slope_max']}: highway {r['recall']:.0%} found, {r['km_elsewhere']} km elsewhere, {r['road_kind_on']} read as road", fontsize=7.5)
        ax.set_xlim(box[0], box[2])
        ax.set_ylim(box[1], box[3])
        ax.set_aspect("equal")
        ax.tick_params(labelsize=6)
        ax.ticklabel_format(useOffset=False, style="plain")
    fig.suptitle("Crests suggested across the Batinah Highway (the wide light-blue band): grey read as road, red as dam, orange other; W26's setting against the lowest and the highest height on the widest disc", fontsize=9)
    fig.savefig(out / "crest_sweep.png", bbox_inches="tight")
    print("best:", [table[n] for n in best])


if __name__ == "__main__":
    main(Path(sys.argv[1]))
