"""Banks as the valley margins, from the DEM: the slope break at the foot of the hillslope, not a rise over the thalweg.

His sketches on the first maps (2026-11-07) put the banks on the margins of the valley floor: 70 m apart on the
Bidah 7.9 km2 wadi, about 100 m on the 7.2 km2 one, 350 m on the 20 km2 fan belt, where the 1.5 m rise found 27, 42 and
a wandering 276. Here a section across the thalweg walks outward and stops where the hillslope starts: the running
slope over ``RUN`` metres exceeds ``s_bank`` and the ground stands at least ``h_min`` above the bed. Two settings are
drawn side by side for his choice.

    .venv\\Scripts\\python "W45 aligned mesh engine\\bank_detection.py" <out folder>
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
from matplotlib.collections import LineCollection  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "W45 aligned mesh engine"))
from bed_types import SITES, hillshade, sample  # noqa: E402
from wadi2d.strips.banks import read_layers  # noqa: E402

SECTION_HALF = 300.0
STATION = 10.0
RUN = 20.0
"""The slope is read over this run outward, m."""
SETTINGS = {"gentle: slope over 6 %, 1 m up": (0.06, 1.0), "firm: slope over 12 %, 2 m up": (0.12, 2.0)}
WINDOWS = {
    "bidah": [(7.9, "narrow", 300.0), (7.2, "medium", 320.0), (20.0, "fan", 450.0)],
    "faydh": [(74.4, "gorge", 300.0), (69.8, "medium", 320.0)],
}


def margins(dem, thalweg: shapely.LineString, s_bank: float, h_min: float):
    """Left and right margin lines and half-widths per station."""
    s = np.arange(STATION, thalweg.length - STATION, STATION)
    pts = np.array([thalweg.interpolate(v).coords[0] for v in s])[:, :2]
    ahead = np.array([thalweg.interpolate(min(v + STATION, thalweg.length)).coords[0] for v in s])[:, :2]
    t = ahead - pts
    t /= np.maximum(np.hypot(t[:, 0], t[:, 1]), 1e-9)[:, None]
    normal = np.column_stack((-t[:, 1], t[:, 0]))
    offsets = np.arange(0.0, SECTION_HALF + 0.5, 1.0)
    run = int(RUN)
    half = {"left": np.zeros(s.size), "right": np.zeros(s.size)}
    for k, (p, n) in enumerate(zip(pts, normal, strict=True)):
        for side, sign in (("left", 1.0), ("right", -1.0)):
            xs, ys = p[0] + sign * offsets * n[0], p[1] + sign * offsets * n[1]
            z = sample(dem, xs, ys)
            bed = np.nanmin(z[:16])
            found = SECTION_HALF
            for d in range(run, offsets.size - run):
                slope = (z[d + run] - z[d]) / RUN
                if slope > s_bank and z[d] - bed > h_min:
                    found = float(d)
                    break
            half[side][k] = found

    def smooth(a):
        out = a.copy()
        for k in range(a.size):
            out[k] = np.median(a[max(0, k - 2) : k + 3])
        return out

    left, right = smooth(half["left"]), smooth(half["right"])
    found = (left < SECTION_HALF) & (right < SECTION_HALF)
    lb = shapely.LineString(pts + normal * left[:, None])
    rb = shapely.LineString(pts - normal * right[:, None])
    return lb, rb, left, right, found


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    made = []
    for site, (gpkg, dem_path) in SITES.items():
        _banks, thalwegs = read_layers(gpkg)
        with rasterio.open(dem_path) as dem:
            for area, label, half_window in WINDOWS[site]:
                line = next((l for a, l in thalwegs.items() if abs(a - area) < 0.05), None)
                if line is None:
                    continue
                mid = line.interpolate(0.5, normalized=True)
                window = shapely.box(mid.x - half_window, mid.y - half_window, mid.x + half_window, mid.y + half_window)
                part = line.intersection(window)
                part = max(part.geoms, key=lambda g: g.length) if hasattr(part, "geoms") else part
                box = (mid.x - half_window, mid.y - half_window, mid.x + half_window, mid.y + half_window)
                fig, axes = plt.subplots(1, 2, figsize=(13, 6.6), dpi=150)
                for ax, (name, (s_bank, h_min)) in zip(axes, SETTINGS.items(), strict=True):
                    lb, rb, left, right, found = margins(dem, part, s_bank, h_min)
                    shade, z = hillshade(dem, box)
                    ax.imshow(shade, extent=(box[0], box[2], box[1], box[3]), cmap="gray", vmin=0.0, vmax=1.0)
                    ax.contour(np.linspace(box[0], box[2], z.shape[1]), np.linspace(box[3], box[1], z.shape[0]), z, levels=14, colors="#6b4e00", linewidths=0.3, alpha=0.6)
                    ax.add_collection(LineCollection([np.asarray(lb.coords)[:, :2], np.asarray(rb.coords)[:, :2]], colors="#c00000", linewidths=1.6))
                    tp = np.asarray(part.coords)[:, :2]
                    ax.plot(tp[:, 0], tp[:, 1], color="#1f77b4", lw=1.0, ls="--")
                    widths = (left + right)[found]
                    text = f"width median {np.median(widths):.0f} m, 10-90 % {np.percentile(widths, 10):.0f} to {np.percentile(widths, 90):.0f} m, margin found on {found.mean() * 100:.0f} % of stations" if widths.size else "no margin found within 300 m: no defined wadi here"
                    ax.set_title(f"{name}\n{text}", fontsize=9)
                    ax.set_xlim(box[0], box[2])
                    ax.set_ylim(box[1], box[3])
                    ax.set_aspect("equal")
                    ax.tick_params(labelsize=6)
                    ax.ticklabel_format(useOffset=False, style="plain")
                fig.suptitle(f"{site.title()}, {label}: wadi of {area:.1f} km2. Red: the valley margins found as the start of the hillslope (slope over {RUN:g} m); blue: thalweg.", fontsize=9)
                path = out / f"banks_{site}_{label}.png"
                fig.savefig(path, bbox_inches="tight")
                plt.close(fig)
                made.append(path)
                print("wrote", path)
    print("done", len(made))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
