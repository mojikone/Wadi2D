"""Full-screen drawings of Block 2 at 20 m on demand, timed: the whole block, a wadi, a 500 m window; GPU and CPU.

usage: python time_block2.py <run folder> <out json> [gpu|cpu ...]

The run is W49's local-radius Block 2 run (2.03 M cells, 7 saved maps), copied with its grid cache pointed inside the
worktree. Each view is drawn cold (its ground not read yet, waited for in full), again (all held), at the next saved map
(a slider step) and panned by a quarter of its width (a pan), at 1920 x 1080 and through the same renderer the plugin's
process uses. Other work may share the GPU: a timing that looks odd is drawn once more and both are kept.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import h5py
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wadi2d.products.pixels import to_host  # noqa: E402
from wadi2d.render.renderer import FrameRenderer  # noqa: E402
from wadi2d.render.run_source import open_run  # noqa: E402
from wadi2d.render.view import View  # noqa: E402

WIDTH, HEIGHT = 1920, 1080


def timed(renderer, t, view, field="depth"):
    start = time.perf_counter()
    drawn = renderer.draw(t, view, field, None)
    values = to_host(drawn.values)
    seconds = time.perf_counter() - start
    return seconds, drawn, values


def view_at(cx, cy, width_m):
    half_w, half_h = width_m / 2.0, width_m / 2.0 * HEIGHT / WIDTH
    return View.of((cx - half_w, cy - half_h, cx + half_w, cy + half_h), WIDTH, HEIGHT)


def deepest_wet(run: Path, frame_name: str, x0, y0, dx):
    with h5py.File(run / "results.h5", "r") as f:
        depth = f["maps"][frame_name]["mean_depth"][:]
    row, col = np.unravel_index(int(np.argmax(depth)), depth.shape)
    return x0 + (col + 0.5) * dx, y0 - (row + 0.5) * dx


def measure(run: Path, backend: str) -> dict:
    start = time.perf_counter()
    source = open_run(run, lambda text: print(f"  {text}", flush=True))
    opened = time.perf_counter() - start
    renderer = FrameRenderer(source, backend)
    found = {"backend": renderer.backend, "open_s": round(opened, 2), "detail": source.detail, "views": {}}
    print(f"{backend}: opened in {opened:.1f} s, detail {source.detail}, {len(source.names)} maps", flush=True)
    west, south, east, north = source.extent()
    middle = len(source.names) // 2
    t, t_next = float(source.times[middle]), float(source.times[middle + 1])
    cx, cy = deepest_wet(run, source.names[middle], source.x0, source.y0, source.dx)
    views = {
        "whole block": view_at((west + east) / 2.0, (south + north) / 2.0, max(east - west, (north - south) * WIDTH / HEIGHT)),
        "a wadi, 3 km": view_at(cx, cy, 3000.0),
        "500 m window": view_at(cx, cy, 500.0),
    }
    for name, view in views.items():
        row = {}
        seconds, drawn, values = timed(renderer, t, view)
        row["cold_s"] = round(seconds, 3)
        row["detail"], row["pixel_m"] = drawn.detail, drawn.pixel_m
        row["wet_pixels"] = int(np.count_nonzero(~np.isnan(values)))
        for label, args in (
            ("again_s", (t, view)),
            ("next_map_s", (t_next, view)),
            ("back_s", (t, view)),
        ):
            row[label] = round(timed(renderer, *args)[0], 3)
        shift = (view.xmax - view.xmin) / 4.0
        panned = View.of((view.xmin + shift, view.ymin, view.xmax + shift, view.ymax), WIDTH, HEIGHT)
        row["pan_cold_s"] = round(timed(renderer, t, panned)[0], 3)
        row["pan_again_s"] = round(timed(renderer, t, panned)[0], 3)
        row["hazard_s"] = round(timed(renderer, t, view, "hazard")[0], 3)
        steady = [row[k] for k in ("again_s", "next_map_s", "back_s", "pan_again_s")]
        if max(steady) > 3 * min(steady):  # shared card or a pause: once more, both kept
            row["again_rerun_s"] = round(timed(renderer, t, view)[0], 3)
        found["views"][name] = row
        print(f"  {name}: {row}", flush=True)
    if renderer.store is not None:
        found["ground_mb"] = round(renderer.store.held / 1024.0**2, 1)
        found["ground_tiles"] = len(renderer.store.tiles)
    renderer.close()
    return found


def main() -> None:
    run, out = Path(sys.argv[1]), Path(sys.argv[2])
    backends = sys.argv[3:] or ["gpu", "cpu"]
    results = [measure(run, backend) for backend in backends]
    out.write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
