"""The rasters of record of windows of a finished run, by each surface rule, at the pixel asked for.

    python s03_windows.py RUN CACHE OUT --window NAME XMIN YMIN XMAX YMAX [--window ...] [--rules a,b] [--pixel M]
                          [--backend cpu|gpu]

The run is read, never written: its tables come from CACHE (``s01_cache_folder.py``), the rasters go to
``OUT/<rule>/<window>/``, with the seconds each took in ``OUT/<rule>/<window>/timing.json``.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from wadi2d.config.schema import RunConfig
from wadi2d.io.progress import Progress
from wadi2d.products.step import STAGES_RECORD, Watch, make_products
from wadi2d.run import prepare_grid


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("cache", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--window", nargs=5, action="append", metavar=("NAME", "XMIN", "YMIN", "XMAX", "YMAX"))
    parser.add_argument("--rules", default="cell_fill,corners,continuous")
    parser.add_argument("--pixel", type=float, default=0.5)
    parser.add_argument("--backend", default="gpu")
    args = parser.parse_args()
    cfg = RunConfig.model_validate_json((args.run / "config.resolved.json").read_text(encoding="utf-8"))
    cfg = cfg.model_copy(update={"grid": cfg.grid.model_copy(update={"cache_dir": str(args.cache.resolve())})})
    start = time.time()
    tables, crs = prepare_grid(cfg, args.cache)
    print(f"tables {time.time() - start:.1f} s", flush=True)
    quiet = Watch(lambda *_a, **_k: None, lambda: False, STAGES_RECORD)
    for rule in args.rules.split(","):
        pixels = cfg.outputs.pixels.model_copy(update={"surface": rule, "pixel_m": args.pixel})
        job = cfg.model_copy(update={"outputs": cfg.outputs.model_copy(update={"pixels": pixels})})
        for name, *box in args.window:
            folder = args.out / rule / name
            folder.mkdir(parents=True, exist_ok=True)
            began = time.time()
            with Progress(folder / "products.jsonl", echo=False):
                stats = make_products(job, tables, crs, args.run, quiet, args.backend, None, tuple(float(v) for v in box), folder)
            seconds = time.time() - began
            (folder / "timing.json").write_text(json.dumps({"seconds": round(seconds, 1), "window": box}), encoding="utf-8")
            print(f"{rule} {name}: {seconds:.1f} s, classes {stats.get('class_km2')}", flush=True)


if __name__ == "__main__":
    main()
