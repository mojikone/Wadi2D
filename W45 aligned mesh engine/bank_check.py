"""His check of 2026-11-07: the banks against the 2D depth results, since the flow runs inside the wadi course.

On the three Bidah windows the 100-yr run at 5 m (``conv_dx5_s1``) gives the flooded course; its margin at a depth
threshold is the physical bank. The terrain detectors (the rise of the ground over the bed) are scored against that
margin, station by station, and his strokes are placed beside both. His strokes are 10 to 12 m wide bands, so a
distance under about 6 m to them says nothing; the flood margin is a line.

    .venv\\Scripts\\python "W45 aligned mesh engine\\bank_check.py" <out folder>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "W45 aligned mesh engine"))
import bank_sweep as bs  # noqa: E402
from bed_types import hillshade  # noqa: E402
from wadi2d.strips.banks import read_layers  # noqa: E402

RISES = (1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 7.0)
DEPTHS = (0.2, 0.5)
STROKE_HALF_WIDTH_M = 6.0


def main(out: Path) -> None:
    gpkg, dem_path = bs.SITES["bidah"]
    _banks, thalwegs = read_layers(gpkg)
    windows = {}
    with rasterio.open(dem_path) as dem, rasterio.open(bs.DEPTH_MAP) as dm:
        for label, (area, half) in bs.SKETCHES.items():
            part = bs.thalweg_part(thalwegs, area)
            c = part.centroid
            box = (c.x - half, c.y - half, c.x + half, c.y + half)
            s, pts, normal = bs.sections(part)
            offsets, prof = bs.profiles(bs.Ground(dem, box), pts, normal)
            _o, depth = bs.profiles(bs.Ground(dm, box), pts, normal)
            if dm.nodata is not None:
                depth = np.where(depth == dm.nodata, 0.0, depth)
            flood = {d: bs.detect("flood", prof, offsets, depth, d=d) for d in DEPTHS}
            rise = {h: bs.detect("rise", prof, offsets, depth, h=h) for h in RISES}
            windows[label] = dict(part=part, box=box, pts=pts, normal=normal, flood=flood, rise=rise, trees=bs.strokes(out, label, box, part), prof=prof)
        # the table: each rise against each flood margin, where both found a bank
        table = {}
        print("rise bank against the flooded course margin: median |offset difference| m (rise minus flood, median signed), stations compared")
        for d in DEPTHS:
            for h in RISES:
                diffs, signed = [], []
                per = {}
                for label, w in windows.items():
                    f, r = w["flood"][d], w["rise"][h]
                    both = (f < bs.SECTION_HALF) & (r < bs.SECTION_HALF)
                    delta = (r - f)[both]
                    per[label] = (round(float(np.median(np.abs(delta))), 1), round(float(np.median(delta)), 1), int(both.sum()))
                    diffs.append(np.abs(delta))
                    signed.append(delta)
                allv = np.concatenate(diffs)
                table[f"rise {h} vs flood {d}"] = {"median_abs_m": round(float(np.median(allv)), 1), "median_signed_m": round(float(np.median(np.concatenate(signed))), 1), **per}
                print(f"  flood {d:.1f} m, rise {h:3.1f} m: all {np.median(allv):5.1f} m (signed {np.median(np.concatenate(signed)):+5.1f}); " + "; ".join(f"{k} {v[0]} ({v[1]:+}) n={v[2]}" for k, v in per.items()))
        widths = {}
        for label, w in windows.items():
            row = {}
            for d in DEPTHS:
                f = w["flood"][d]
                on = (f < bs.SECTION_HALF).all(axis=1)
                row[f"flood {d}"] = round(float(np.median((f[:, 0] + f[:, 1])[on])), 1) if on.any() else None
            for h in RISES:
                r = w["rise"][h]
                on = (r < bs.SECTION_HALF).all(axis=1)
                row[f"rise {h}"] = round(float(np.median((r[:, 0] + r[:, 1])[on])), 1) if on.any() else None
            widths[label] = row
            print(label, "widths m:", row)
        # his strokes against the flood margins: the share of stroke centre within the band
        strokes = {}
        for label, w in windows.items():
            for d in DEPTHS:
                f = w["flood"][d]
                dist = []
                for side, sign in enumerate((1.0, -1.0)):
                    on = f[:, side] < bs.SECTION_HALF
                    bank = w["pts"][on] + sign * w["normal"][on] * f[on, side][:, None]
                    dist.append(w["trees"][side].query(bank)[0])
                dist = np.concatenate(dist)
                strokes[f"{label} flood {d}"] = {"median_m": round(float(np.median(dist)), 1), "share_inside_stroke": round(float((dist < STROKE_HALF_WIDTH_M).mean()), 2)}
                print(f"{label}: flood {d} margin to his stroke: median {np.median(dist):.1f} m, {100 * (dist < STROKE_HALF_WIDTH_M).mean():.0f} % inside the stroke band")
        (out / "bank_check.json").write_text(json.dumps({"rise_vs_flood": table, "widths": widths, "strokes_vs_flood": strokes}, indent=1), encoding="utf-8")
        # the figure: his strokes, the two flood margins, the rise bank nearest the 0.2 m margin
        best = min(RISES, key=lambda h: table[f"rise {h} vs flood 0.2"]["median_abs_m"])
        fig, axes = plt.subplots(1, 3, figsize=(19, 6.6), dpi=130)
        for ax, (label, w) in zip(axes, windows.items(), strict=True):
            box = w["box"]
            shade, _z = hillshade(dem, box)
            ax.imshow(shade, extent=(box[0], box[2], box[1], box[3]), cmap="gray", vmin=0, vmax=1)
            for tree in w["trees"]:
                ax.scatter(tree.data[::12, 0], tree.data[::12, 1], s=1.5, color="#b070ff", alpha=0.5)
            for key, colour, lw in ((("flood", 0.2), "#00a0e0", 2.0), (("flood", 0.5), "#004c99", 1.2), (("rise", best), "#c00000", 1.6)):
                found = w[key[0]][key[1]]
                for side, sign in enumerate((1.0, -1.0)):
                    on = found[:, side] < bs.SECTION_HALF
                    bank = w["pts"][on] + sign * w["normal"][on] * found[on, side][:, None]
                    ax.plot(bank[:, 0], bank[:, 1], color=colour, lw=lw, label=f"{key[0]} {key[1]}" if side == 0 else None)
            tp = np.asarray(w["part"].coords)[:, :2]
            ax.plot(tp[:, 0], tp[:, 1], "--", color="#1f77b4", lw=0.9, label="thalweg")
            wd = widths[label]
            ax.set_title(f"{label}: widths m: his strokes see title of sketched_banks; flood 0.2 {wd['flood 0.2']}, flood 0.5 {wd['flood 0.5']}, rise {best} {wd[f'rise {best}']}", fontsize=7.5)
            ax.set_xlim(box[0], box[2])
            ax.set_ylim(box[1], box[3])
            ax.set_aspect("equal")
            ax.tick_params(labelsize=6)
            ax.ticklabel_format(useOffset=False, style="plain")
        axes[0].legend(fontsize=7, loc="lower right")
        fig.suptitle(f"Banks against the 100-yr flooded course (5 m run): purple his strokes, light blue the 0.2 m depth margin, dark blue 0.5 m, red the ground rise of {best} m, the terrain rule nearest the 0.2 m margin", fontsize=9)
        fig.savefig(out / "bank_check.png", bbox_inches="tight")
        print("best rise against the 0.2 m margin:", best)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
