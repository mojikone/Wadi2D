"""W85 step 4: a Block 2 window round the pit through the real engine on the CPU, with and without the pit.

    python s05_window.py <W79 run folder> <out folder> [variant ...]

The window is 1.2 km square on the cells of the W79 run, 60 by 60 cells of 20 m, the pit at its centre, every edge a
free outfall, the run's own storm, losses and roughness, 48 h. Variants:

    base        the DEM as it is
    filled      the pit filled to its spill level in a copy of the DEM (nothing else changed)
    plan10      the DEM as it is, numerics.plan_min 0.10
    plan25      the DEM as it is, numerics.plan_min 0.25
    plan100     the DEM as it is, numerics.plan_min 1.0: the wet share out of the step rule altogether
    lts         the DEM as it is, local time stepping on
    bank        the DEM as it is, an embankment object over the pit with its top at the spill level

Each run writes its folder with ``outputs.step_limiter: layer``; ``window_summary.json`` holds steps, loop time, the
smallest step, the balance and the water in the pit's cells at the end.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import from_bounds
from skimage.morphology import reconstruction

from wadi2d.config.schema import RunConfig
from wadi2d.run import run_job

DX = 20.0
PIT_X, PIT_Y = 414791.0, 2722486.0
"""A cell corner of the W79 lattice beside the pit: the face the pit lies across runs through it."""
HALF = 600.0
MARGIN = 100.0
"""DEM kept round the window, so a face table reads the ground past the window's edge as it does in the full run."""
PATCH = 60.0
"""Half side of the square in which sinks are filled, m: the two pits and nothing else."""
EXTENT = (PIT_X - HALF, PIT_Y - HALF, PIT_X + HALF, PIT_Y + HALF)
BANK = {
    "kind": "embankment",
    "name": "pit fill",
    "coordinates": [[414789.75, 2722471.0], [414789.75, 2722508.0]],
    "z_constant": 1187.84,
    "section": {"width": 16.0, "left_slope": 0.0, "right_slope": 0.0},
}
"""The pit mended with a tool the dock has: an embankment over the sink, its top at the sink's spill level."""
VARIANTS = {
    "base": ("dem.tif", {}),
    "filled": ("dem_filled.tif", {}),
    "plan10": ("dem.tif", {"numerics": {"plan_min": 0.10}}),
    "plan25": ("dem.tif", {"numerics": {"plan_min": 0.25}}),
    "plan100": ("dem.tif", {"numerics": {"plan_min": 1.0}}),
    "lts": ("dem.tif", {"numerics": {"local_time_stepping": True}}),
    "bank": ("dem.tif", {"terrain": {"objects": [BANK]}}),
}


def crop_dems(source: str, out: Path) -> dict:
    """The window of the DEM as it is and with the sinks of the pit's patch filled; what the fill moved."""
    out.mkdir(parents=True, exist_ok=True)
    with rasterio.open(source) as src:
        b = (EXTENT[0] - MARGIN, EXTENT[1] - MARGIN, EXTENT[2] + MARGIN, EXTENT[3] + MARGIN)
        win = from_bounds(*b, src.transform).round_offsets().round_lengths()
        z = src.read(1, window=win)
        profile = src.profile | {
            "height": z.shape[0], "width": z.shape[1], "transform": src.window_transform(win), "compress": "deflate",
            "tiled": True, "blockxsize": 256, "blockysize": 256,
        }  # fmt: skip
        pixel = src.res[0]
    with rasterio.open(out / "dem.tif", "w", **profile) as dst:
        dst.write(z, 1)
    tr = profile["transform"]
    c0, c1 = (round((PIT_X + s * PATCH - tr.c) / pixel) for s in (-1, 1))
    r0, r1 = (round((tr.f - (PIT_Y - s * PATCH)) / pixel) for s in (-1, 1))
    patch = z[r0:r1, c0:c1].astype(np.float64)
    seed = np.full_like(patch, patch.max())
    seed[0, :], seed[-1, :], seed[:, 0], seed[:, -1] = patch[0, :], patch[-1, :], patch[:, 0], patch[:, -1]
    filled = reconstruction(seed, patch, method="erosion")
    rise = filled - patch
    done = z.copy()
    done[r0:r1, c0:c1] = filled.astype(z.dtype)
    with rasterio.open(out / "dem_filled.tif", "w", **profile) as dst:
        dst.write(done, 1)
    report = {
        "pixel_m": pixel,
        "filled_pixels": int((rise > 0.01).sum()),
        "filled_area_m2": float((rise > 0.01).sum() * pixel * pixel),
        "filled_volume_m3": float(rise.sum() * pixel * pixel),
        "deepest_fill_m": float(rise.max()),
        "lowest_before_m": float(patch.min()),
        "lowest_after_m": float(filled.min()),
    }
    (out / "fill_report.json").write_text(json.dumps(report, indent=1))
    return report


def job(base: dict, out: Path, dem: str, more: dict) -> RunConfig:
    data = json.loads(json.dumps(base))
    x0, y0, x1, y1 = EXTENT
    inset = 0.5 * DX
    edges = (
        [(x0 + inset, y0 + inset), (x0 + inset, y1 - inset)],
        [(x1 - inset, y0 + inset), (x1 - inset, y1 - inset)],
        [(x0 + inset, y0 + inset), (x1 - inset, y0 + inset)],
        [(x0 + inset, y1 - inset), (x1 - inset, y1 - inset)],
    )
    data["project"]["name"] = "w85_window"
    data["project"]["description"] = "W85: a Block 2 window round the pit that sets the time step"
    data["grid"].update(domain=None, extent=list(EXTENT), cache_dir=str(out / "cache"))
    data["terrain"].update(dem=str(out / "dem" / dem), objects=[])
    data["boundaries"] = [{"kind": "free", "coordinates": [list(p) for p in edge]} for edge in edges]
    data["run"].update(backend="cpu", duration_s=3600.0 * float(os.environ.get("W85_HOURS", "48")))
    data["outputs"].update(
        lines=[], observed=[], map_every_s=3600.0, series_every_s=10.0, step_limiter="layer",
        points=[
            {"name": "pit east", "x": PIT_X + 0.5 * DX, "y": PIT_Y - 0.5 * DX},
            {"name": "pit west", "x": PIT_X - 0.5 * DX, "y": PIT_Y - 0.5 * DX},
        ],
    )  # fmt: skip
    data["outputs"]["pixels"]["enabled"] = False
    data["outputs"]["edge_check"]["enabled"] = False
    for part, values in more.items():
        data[part].update(values)
    return RunConfig.model_validate(data)


def main() -> None:
    run, out = Path(sys.argv[1]), Path(sys.argv[2])
    names = sys.argv[3:] or list(VARIANTS)
    base = json.loads((run / "config.resolved.json").read_text())
    if not (out / "dem" / "dem_filled.tif").is_file():
        print("fill:", crop_dems(base["terrain"]["dem"], out / "dem"))
    summary_file = out / os.environ.get("W85_SUMMARY", "window_summary.json")
    summary = json.loads(summary_file.read_text()) if summary_file.is_file() else {}
    for name in names:
        dem, more = VARIANTS[name]
        cfg = job(base, out, dem, more)
        folder = out / name
        (out / f"job_{name}.json").write_text(cfg.model_dump_json(indent=1))
        s = run_job(cfg, folder)
        done = s.done
        ends = {}
        for point in ("pit_east", "pit_west"):
            rows = (folder / "series" / f"point_{point}.csv").read_text().splitlines()
            head, last = rows[0].split(","), rows[-1].split(",")
            ends[point] = dict(zip(head, (float(v) for v in last), strict=True))
        summary[name] = {
            "exit": s.exit_code, "status": s.status, "steps": done.get("steps"), "loop_s": done.get("loop_s"),
            "dt_min": done.get("dt_min"), "tile_steps": done.get("tile_steps"), "balance": done.get("balance"),
            "pit_cells_end": ends,
        }  # fmt: skip
        summary_file.write_text(json.dumps(summary, indent=1))
        print(name, json.dumps({k: v for k, v in summary[name].items() if k != "balance"}), flush=True)


if __name__ == "__main__":
    main()
