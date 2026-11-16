"""The tables of a finished run, as ``wadi2d products`` would build them, with the cache in this iteration's folder.

    python s02_tables.py RUN CACHE

Says whether the grid and strip caches were hit and how long it took; the tables are then in CACHE for the remakes.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from wadi2d.config.schema import RunConfig
from wadi2d.io.progress import Progress
from wadi2d.run import prepare_grid


def config_of(run: Path, cache: Path) -> RunConfig:
    cfg = RunConfig.model_validate_json((run / "config.resolved.json").read_text(encoding="utf-8"))
    grid = cfg.grid.model_copy(update={"cache_dir": str(cache.resolve())})
    return cfg.model_copy(update={"grid": grid})


def main() -> None:
    run, cache = Path(sys.argv[1]), Path(sys.argv[2])
    cfg = config_of(run, cache)
    start = time.time()
    log = cache / f"tables_{run.name}.jsonl"
    with Progress(log, echo=True) as progress:
        tables, _crs = prepare_grid(cfg, cache, progress)
    print(f"tables of {run.name}: {time.time() - start:.1f} s; strip: {getattr(tables, 'strip', None) is not None}")


if __name__ == "__main__":
    main()
