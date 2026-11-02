"""Title and legend round the two full-size renders. Writes the two JPG maps."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Patch
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
HERE = Path(__file__).resolve().parent
T = HERE / "terrain"
STORM = "Block 2 200-yr storm over the whole boundary, 251 mm at storm area 300 km2. 30 m grid with sub-grid tables, NSA 5 m with Copernicus."


def frame(png: str, title: str, out: str, legend) -> None:
    img = Image.open(T / png).convert("RGB")
    x0, y0, x1, y1 = json.loads((T / (png + ".json")).read_text())
    w = 0.96
    width_px = img.width / w
    fig = plt.figure(figsize=(10, 11.8), dpi=width_px / 10, facecolor="white")
    ax = fig.add_axes([0.02, 0.08, w, 0.845])
    ax.imshow(img, extent=(x0, x1, y0, y1), interpolation="none")
    ax.set_axis_off()
    fig.text(0.02, 0.972, title, fontsize=15, fontweight="bold", va="center")
    fig.text(0.02, 0.950, STORM, fontsize=9.5, va="center")
    legend(fig)
    fig.savefig(HERE / out, dpi=width_px / 10, facecolor="white", pil_kwargs={"quality": 90})
    plt.close(fig)
    print(out, (HERE / out).stat().st_size / 1e6, "MB", img.size)


def depth_legend(fig) -> None:
    stops = [(0.0, "#f7fbff"), (0.5 / 3, "#a2cae5"), (1.0 / 3, "#73b2d8"), (1.5 / 3, "#2979b9"), (1.0, "#08306b")]
    cax = fig.add_axes([0.02, 0.045, 0.42, 0.013])
    bar = fig.colorbar(plt.cm.ScalarMappable(Normalize(0, 3), LinearSegmentedColormap.from_list("his", stops)), cax=cax,
                       orientation="horizontal", ticks=[0, 0.5, 1, 1.5, 3])  # fmt: skip
    bar.ax.set_xticklabels(["0", "0.5", "1", "1.5", "3+ m"], fontsize=9)
    bar.ax.tick_params(length=2)
    fig.text(0.47, 0.052, "Depth, style of Block2_Depth_200Year", fontsize=9, va="center")


def hazard_legend(fig) -> None:
    colours = ["#0000ff", "#0080ff", "#00ffff", "#00ff00", "#ffff00", "#ff0000"]
    handles = [Patch(facecolor=c, edgecolor="#555555", linewidth=0.3, label=f"H{i + 1}") for i, c in enumerate(colours)]
    fig.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.015, 0.02), ncol=6, frameon=False, fontsize=10, handlelength=1.6)
    fig.text(0.55, 0.046, "AIDR classes, colours of Block_2_Hazard_200y, shown opaque", fontsize=9, va="center")


if __name__ == "__main__":
    frame("render_depth.png", "Wadi2D rain-on-grid, full project extent: maximum depth", "Wadi2D_full_extent_MAX_DEPTH.jpg", depth_legend)
    frame("render_hazard.png", "Wadi2D rain-on-grid, full project extent: AIDR hazard H1 to H6", "Wadi2D_full_extent_HAZARD_H1-H6.jpg", hazard_legend)
