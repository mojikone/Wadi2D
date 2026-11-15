"""How a run's pixel maps would be cut into blocks, and how long the step takes to get there, without making them.

    python s06_plan.py RUN [--memory-mb N] [--backend cpu|gpu]

The product step itself is run on RUN (read only) up to its plan and stopped there: the readers opened, the strip's
extent found, the blocks cut. Nothing is written to RUN; the step's temporary rasters go to ``runs/_plan`` and are
removed by the stop. With ``--backend cpu`` nothing touches the card and the block is the host's 4 GB, or the cap.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from contextlib import suppress
from pathlib import Path

from wadi2d.config.schema import RunConfig
from wadi2d.products.pixels import array_module
from wadi2d.products.step import ProductsStopped, Watch, lattice_pixels
from wadi2d.run import prepare_grid

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("--memory-mb", type=int, default=0)
    parser.add_argument("--backend", default="cpu")
    args = parser.parse_args()
    if args.memory_mb:
        os.environ["WADI2D_PIXEL_MEMORY_MB"] = str(args.memory_mb)
    cfg = RunConfig.model_validate_json((args.run / "config.resolved.json").read_text(encoding="utf-8"))
    start = time.perf_counter()
    tables, crs = prepare_grid(cfg, Path(cfg.grid.cache_dir))
    loaded = time.perf_counter()
    plan: dict = {}

    def emit(_ev: str, **event) -> None:
        if event.get("kind") == "pixel_blocks":
            plan.update(event)

    folder = HERE / "runs" / "_plan"
    folder.mkdir(parents=True, exist_ok=True)
    with suppress(ProductsStopped):
        lattice_pixels(cfg, tables, crs, args.run, folder, None, Watch(emit, lambda: bool(plan)), array_module(args.backend))
    plan.update(grid_and_strip_load_s=round(loaded - start, 1), to_plan_s=round(time.perf_counter() - loaded, 1))
    print(json.dumps(plan, indent=1))


if __name__ == "__main__":
    main()
