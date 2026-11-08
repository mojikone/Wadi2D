"""The banks as the engine now draws them (ground 2 m over the bed, W45), on the three Bidah windows he sketched, with
the corridor cells the width rule built on them, and over the whole of Faydh 01.

    .venv\\Scripts\\python "W45 aligned mesh engine\\bank_maps.py" <out folder>
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
import shapely  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "W45 aligned mesh engine"))
from bed_types import SITES, hillshade  # noqa: E402
from digitise_sketch import SKETCHES, thalweg_part  # noqa: E402
from wadi2d.strips.banks import read_layers  # noqa: E402

W45 = ROOT / "W45 aligned mesh engine"
BIDAH_BANKS = W45 / "suggested" / "bidah" / "suggested_breaklines.gpkg"
FAYDH_BANKS = W45 / "suggested" / "faydh" / "suggested_breaklines.gpkg"
BIDAH_STRIP = W45 / "race_bidah_hybrid" / "corridors_w2" / "maps" / "strip_mesh.gpkg"
FAYDH_DEM = SITES["faydh"][1]
BIDAH_DEM = SITES["bidah"][1]


def polygons(path: Path, layer: str) -> list[np.ndarray]:
    import fiona

    out = []
    if not path.is_file():
        return out
    with fiona.open(path, layer=layer) as src:
        for f in src:
            g = shapely.geometry.shape(f["geometry"])
            for part in shapely.get_parts(g):
                if part.geom_type == "Polygon":
                    out.append(np.asarray(part.exterior.coords)[:, :2])
    return out


def strokes(out: Path, label: str, box, part) -> np.ndarray:
    import bank_sweep as bs

    trees = bs.strokes(out / "bed_types", label, box, part)
    return np.vstack([t.data for t in trees])


def draw_banks(ax, banks: list[dict], box, colour: str, lw: float) -> int:
    window = shapely.box(*box)
    n = 0
    for b in banks:
        line = b["line"]
        if not line.intersects(window):
            continue
        xy = np.asarray(line.coords)
        ax.plot(xy[:, 0], xy[:, 1], color=colour, lw=lw)
        n += 1
    return n


def main(out: Path) -> None:
    banks, thalwegs = read_layers(BIDAH_BANKS)
    _old_banks, old_thalwegs = read_layers(SITES["bidah"][0])  # the windows he sketched were cut on W26's thalwegs
    cells = polygons(BIDAH_STRIP, "strip_cells")
    fig, axes = plt.subplots(1, 3, figsize=(19, 6.8), dpi=130)
    with rasterio.open(BIDAH_DEM) as dem:
        for ax, (label, (area, half)) in zip(axes, SKETCHES.items(), strict=True):
            part = thalweg_part(old_thalwegs, area)
            c = part.centroid
            box = (c.x - half, c.y - half, c.x + half, c.y + half)
            shade, _z = hillshade(dem, box)
            ax.imshow(shade, extent=(box[0], box[2], box[1], box[3]), cmap="gray", vmin=0, vmax=1)
            window = shapely.box(*box)
            inside = [p for p in cells if shapely.Polygon(p).intersects(window)]
            if inside:
                ax.add_collection(PolyCollection(inside, facecolors="#2a7fd420", edgecolors="#2a7fd4", linewidths=0.4))
            try:
                pts = strokes(out, label, box, part)
                ax.scatter(pts[::10, 0], pts[::10, 1], s=1.0, color="#b070ff", alpha=0.35)
            except Exception:
                pass
            for line in thalwegs.values():
                if line.intersects(window):
                    xy = np.asarray(line.coords)
                    ax.plot(xy[:, 0], xy[:, 1], "--", color="#1f77b4", lw=0.8)
            n = draw_banks(ax, banks, box, "#c00000", 1.6)
            ax.set_title(f"{label}: wadi of {area:.1f} km2, {n} bank lines in view, {len(inside)} corridor cells", fontsize=9)
            ax.set_xlim(box[0], box[2])
            ax.set_ylim(box[1], box[3])
            ax.set_aspect("equal")
            ax.tick_params(labelsize=6)
            ax.ticklabel_format(useOffset=False, style="plain")
    fig.suptitle("Bidah: the banks the engine now draws (red, ground 2 m over the bed), the corridor cells built on them (blue), the thalwegs (dashed), your strokes (purple)", fontsize=9)
    fig.savefig(out / "bank_maps_bidah.png", bbox_inches="tight")
    print("wrote", out / "bank_maps_bidah.png")

    fbanks, fthalwegs = read_layers(FAYDH_BANKS)
    union = shapely.union_all([b["line"] for b in fbanks])
    x0, y0, x1, y1 = union.bounds
    pad = 300.0
    box = (x0 - pad, y0 - pad, x1 + pad, y1 + pad)
    side = max(box[2] - box[0], box[3] - box[1])
    cx, cy = 0.5 * (box[0] + box[2]), 0.5 * (box[1] + box[3])
    box = (cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2)
    fig, axes = plt.subplots(1, 2, figsize=(19, 9.4), dpi=120)
    with rasterio.open(FAYDH_DEM) as dem:
        shade, _z = hillshade(dem, box)
        axes[0].imshow(shade, extent=(box[0], box[2], box[1], box[3]), cmap="gray", vmin=0, vmax=1)
        for line in fthalwegs.values():
            xy = np.asarray(line.coords)
            axes[0].plot(xy[:, 0], xy[:, 1], "--", color="#1f77b4", lw=0.5)
        n = draw_banks(axes[0], fbanks, box, "#c00000", 0.8)
        axes[0].set_title(f"Faydh 01: {n} bank lines over {sum(b['line'].length for b in fbanks) / 1000:.0f} km on {len(fthalwegs)} thalwegs", fontsize=9)
        axes[0].set_xlim(box[0], box[2])
        axes[0].set_ylim(box[1], box[3])
        # a close window on the biggest wadi, half way down
        big = fthalwegs[max(fthalwegs)]
        mid = big.interpolate(0.55, normalized=True)
        zoom = (mid.x - 600.0, mid.y - 600.0, mid.x + 600.0, mid.y + 600.0)
        shade, _z = hillshade(dem, zoom)
        axes[1].imshow(shade, extent=(zoom[0], zoom[2], zoom[1], zoom[3]), cmap="gray", vmin=0, vmax=1)
        for line in fthalwegs.values():
            if line.intersects(shapely.box(*zoom)):
                xy = np.asarray(line.coords)
                axes[1].plot(xy[:, 0], xy[:, 1], "--", color="#1f77b4", lw=0.9)
        n = draw_banks(axes[1], fbanks, zoom, "#c00000", 1.6)
        axes[1].set_title(f"Faydh 01, the main wadi half way down: {n} bank lines in view", fontsize=9)
        axes[1].set_xlim(zoom[0], zoom[2])
        axes[1].set_ylim(zoom[1], zoom[3])
        axes[0].add_patch(plt.Rectangle((zoom[0], zoom[1]), zoom[2] - zoom[0], zoom[3] - zoom[1], fill=False, edgecolor="#ffa500", lw=1.2))
    for ax in axes:
        ax.set_aspect("equal")
        ax.tick_params(labelsize=6)
        ax.ticklabel_format(useOffset=False, style="plain")
    fig.suptitle("Faydh 01: the banks the engine now draws (red, ground 2 m over the bed) and the thalwegs (dashed); orange box: the close view", fontsize=9)
    fig.savefig(out / "bank_maps_faydh.png", bbox_inches="tight")
    print("wrote", out / "bank_maps_faydh.png")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
