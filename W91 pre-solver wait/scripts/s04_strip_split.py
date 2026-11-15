"""Where a whole strip build's time goes, outside and inside its pieces: ``strip_tables`` once under cProfile on a
finished s01 run's job, grid tables and strip mesh (read from its cache), then the strip cache's own save.

    python s04_strip_split.py <s01 label>

Writes ``runs/<label>.strip_split.txt``: the profile's top functions by cumulative time, and the save's seconds.
"""

from __future__ import annotations

import cProfile
import io
import json
import pstats
import sys
import time
from pathlib import Path

RUNS = Path(__file__).resolve().parents[1] / "runs"


def saved(label: str, kind: str) -> list[Path]:
    out = []
    for line in (RUNS / f"{label}.log").read_text(encoding="utf-8").splitlines():
        text = line[10:]
        if text.startswith("{"):
            ev = json.loads(text)
            if ev.get("kind") == f"{kind}_cache_saved":
                out.append(Path(ev["path"]))
    return out


def main() -> None:
    import h5py
    import numpy as np

    from wadi2d.demstore import open_bed
    from wadi2d.io.cache import load_strip, load_tables, save_strip
    from wadi2d.run import _wkt, load_job, manning_grid, with_tables
    from wadi2d.strips.build import strip_squares, strip_tables

    label = sys.argv[1]
    cfg = with_tables(load_job(RUNS / label / "config.resolved.json"))
    grid_file, strip_file = saved(label, "grid")[-1], saved(label, "strip")[-1]
    with h5py.File(grid_file, "r") as f:
        key = f.attrs["key"]
    tables = load_tables(grid_file, key)
    mask, made = load_strip(strip_file, strip_file.stem.removeprefix("strip_"))
    strip = made.strip
    with open_bed(cfg, Path(cfg.grid.cache_dir)) as bed:
        crs = _wkt(bed)
        bed.bind(tables.grid.x0, tables.grid.y0)
        jj, ii = np.nonzero(tables.grid.mask)
        sj, si = strip_squares(strip.geometry, tables.grid)
        cells = (np.concatenate((jj, sj)), np.concatenate((ii, si)))
        t0 = time.perf_counter()
        n = manning_grid(cfg, tables.grid, crs, cells)
        manning_s = time.perf_counter() - t0
        prof = cProfile.Profile()
        t0 = time.perf_counter()
        prof.enable()
        built = strip_tables(cfg, tables, bed, strip, n)
        prof.disable()
        whole_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    scratch = RUNS / f"{label}.strip_split.pkl"
    save_strip(scratch, "scratch", mask, built)
    save_s = time.perf_counter() - t0
    scratch.unlink()
    text = io.StringIO()
    pstats.Stats(prof, stream=text).sort_stats("cumulative").print_stats(30)
    head = f"manning {manning_s:.1f} s, strip_tables {whole_s:.1f} s, save_strip {save_s:.1f} s\n\n"
    (RUNS / f"{label}.strip_split.txt").write_text(head + text.getvalue(), encoding="utf-8")
    print(head)


if __name__ == "__main__":
    main()
