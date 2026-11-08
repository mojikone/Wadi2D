"""Why the centre generator reads higher at Faydh 01's dam axis than the squares and the ring corridors: the three
runs' maximum level and depth along the axis, the volume passing it, and a map of each strip at the axis window.

    .venv\\Scripts\\python "W46 centre-based mesh generator\\faydh_axis_check.py" [tag ...]

Reads W45's no-lines and ring runs and W46's centre runs (faydh20_centres_gpu, plus faydh20_centres_gpu_<tag> for
each tag given), writes ``race_faydh/axis_check.png`` and prints the numbers.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import fiona
import matplotlib
import numpy as np
import rasterio
import shapely

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
W45_RACE = ROOT / "W45 aligned mesh engine" / "race_faydh"
W46_RACE = ROOT / "W46 centre-based mesh generator" / "race_faydh"
PAD = 350.0


def series(folder: Path, name: str) -> tuple[np.ndarray, np.ndarray]:
    with (folder / "series" / f"line_{name}.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))[1:]
    t = np.array([float(r[0]) for r in rows])
    q = np.array([float(r[1]) for r in rows])
    return t, q


def sample(path: Path, pts: np.ndarray) -> np.ndarray:
    with rasterio.open(path) as src:
        vals = np.array([v[0] for v in src.sample(pts.tolist())], np.float64)
        if src.nodata is not None:
            vals[vals == src.nodata] = np.nan
    return vals


def strip_cells(folder: Path) -> tuple[list[np.ndarray], np.ndarray, np.ndarray]:
    path = folder / "maps" / "strip_mesh.gpkg"
    if not path.is_file():
        return [], np.zeros(0), np.zeros(0, bool)
    rings, depth, on_line = [], [], []
    with fiona.open(path, layer="strip_cells") as src:
        for f in src:
            g = shapely.geometry.shape(f["geometry"])
            for part in (g.geoms if hasattr(g, "geoms") else [g]):
                rings.append(shapely.get_coordinates(part.exterior))
                depth.append(float(f["properties"]["max_depth_m"]))
                on_line.append(f["properties"]["kind"] == "corridor")
    return rings, np.array(depth), np.array(on_line)


def main(tags: list[str]) -> None:
    runs = {"none": W45_RACE / "faydh20_none_gpu", "rings": W45_RACE / "faydh20_strips_gpu", "centres": W46_RACE / "faydh20_centres_gpu"}
    for tag in tags:
        runs[f"centres_{tag}"] = W46_RACE / f"faydh20_centres_gpu_{tag}"
    runs = {k: v for k, v in runs.items() if (v / "progress.jsonl").is_file()}
    job = json.loads((W46_RACE / "faydh20_centres_gpu.json").read_text(encoding="utf-8"))
    axis = shapely.LineString(next(l["coordinates"] for l in job["outputs"]["lines"] if l["name"] == "axis"))
    along = np.arange(0.0, axis.length, 5.0)
    pts = shapely.get_coordinates(shapely.line_interpolate_point(axis, along))
    print(f"axis {axis.length:.0f} m long")
    profiles = {}
    for name, folder in runs.items():
        t, q = series(folder, "axis")
        volume = float(np.trapezoid(np.abs(q), t))
        level = sample(folder / "maps" / "max_level.tif", pts)
        depth = sample(folder / "maps" / "max_depth.tif", pts)
        wet = np.isfinite(depth) & (depth > 0.05)
        profiles[name] = (level, depth, wet)
        print(
            f"{name:14s}: axis peak {np.abs(q).max():7.1f} m3/s, volume past the axis {volume / 1e6:.3f} Mm3, wet width on the axis"
            f" {5.0 * wet.sum():.0f} m, max level over the wet part mean {np.nanmean(level[wet]):.3f} m, max depth mean {np.nanmean(depth[wet]):.2f} m, deepest {np.nanmax(depth):.2f} m"
        )
    box = (pts[:, 0].min() - PAD, pts[:, 1].min() - PAD, pts[:, 0].max() + PAD, pts[:, 1].max() + PAD)
    n = len(runs)
    fig, axes = plt.subplots(2, n, figsize=(6 * n, 12), dpi=100, gridspec_kw={"height_ratios": [1.3, 1.0]})
    for k, (name, folder) in enumerate(runs.items()):
        ax = axes[0, k]
        with rasterio.open(folder / "maps" / "max_depth.tif") as src:
            win = rasterio.windows.from_bounds(*box, src.transform)
            d = src.read(1, window=win).astype(np.float64)
            if src.nodata is not None:
                d[d == src.nodata] = np.nan
            d[d <= 0.0] = np.nan
            b = rasterio.windows.bounds(win, src.transform)
        ax.imshow(d, extent=(b[0], b[2], b[1], b[3]), cmap="Blues", vmin=0, vmax=8)
        rings, depth, on_line = strip_cells(folder)
        if rings:
            inside = [k for k, r in enumerate(rings) if r[:, 0].min() < box[2] and r[:, 0].max() > box[0] and r[:, 1].min() < box[3] and r[:, 1].max() > box[1]]
            ax.add_collection(PolyCollection([rings[k] for k in inside], facecolors="none", edgecolors=np.where(on_line[inside], "#1b4f8a", "#c86400"), linewidths=0.4))
        ax.plot(*axis.xy, color="#d40000", linewidth=1.5)
        ax.set_xlim(box[0], box[2])
        ax.set_ylim(box[1], box[3])
        ax.set_aspect("equal")
        ax.set_title(f"{name}: max depth (blue), the strip's cells (dark blue on the line, orange around)", fontsize=9)
    ax = axes[1, 0]
    for name, (level, depth, wet) in profiles.items():
        ax.plot(along, np.where(wet, level, np.nan), label=f"{name} max level")
    ax.set_xlabel("along the axis, m")
    ax.set_ylabel("max level, m")
    ax.legend(fontsize=8)
    ax.set_title("maximum level along the axis where wet", fontsize=9)
    ax = axes[1, 1] if n > 1 else None
    if ax is not None:
        for name, (level, depth, wet) in profiles.items():
            ax.plot(along, np.where(wet, depth, np.nan), label=f"{name} max depth")
        ax.set_xlabel("along the axis, m")
        ax.set_ylabel("max depth, m")
        ax.legend(fontsize=8)
        ax.set_title("maximum depth along the axis", fontsize=9)
    for ax in axes[1, 2:]:
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(W46_RACE / "axis_check.png")
    print("wrote", W46_RACE / "axis_check.png")


if __name__ == "__main__":
    main(sys.argv[1:])
