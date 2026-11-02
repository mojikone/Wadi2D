"""The whole step on the full-extent run, without writing there: a folder of its own holds a hard link to results.h5.

Usage: s07_full_step.py <run folder> <work folder> <table cache>. The work folder must be on the same drive as the run.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

from wadi2d.config.schema import RunConfig
from wadi2d.products.step import Watch, make_products
from wadi2d.run import prepare_grid

RUN, WORK, CACHE = (Path(a) for a in sys.argv[1:4])
WORK.mkdir(parents=True, exist_ok=True)
link = WORK / "results.h5"
if not link.exists():
    os.link(RUN / "results.h5", link)
shutil.copy(RUN / "config.resolved.json", WORK)
cfg = RunConfig.model_validate_json((WORK / "config.resolved.json").read_text(encoding="utf-8"))
t0 = time.time()
tables, crs = prepare_grid(cfg, CACHE)
print(f"tables {time.time() - t0:.0f} s", flush=True)
last = [None]


def emit(event, **fields):
    tag = (event, fields.get("stage"))
    if tag != last[0] or fields.get("done", 1) % 40 == 0:
        print(f"{time.time() - t0:7.0f} {event} {fields}", flush=True)
        last[0] = tag


stats = make_products(cfg, tables, crs, WORK, Watch(emit, lambda: False), "auto")
stats["step_s"] = round(time.time() - t0)
print(json.dumps(stats, indent=1), flush=True)
