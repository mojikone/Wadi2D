"""Before against after, to the digit: the tables and the strip each run built, its pits, its survey, its job.

    python s03_compare.py <before label> <after label>

Reads the two s01 runs: the grid and strip caches each saved (in the order its log names them: the job as given,
then the job with its pit fills), ``terrain_checks.gpkg``, ``terrain/volumes*.csv``, ``config.resolved.json``. The
cache keys differ (the builder's code is hashed into them), so files are paired by their place in the log. Writes
``runs/compare_<before>_<after>.json`` and prints it.
"""

from __future__ import annotations

import json
import pickle
import sqlite3
import sys
from dataclasses import fields
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RUNS = HERE.parent / "runs"
sys.path.insert(0, str(HERE.parents[1]))


def saved(label: str, kind: str) -> list[Path]:
    out = []
    for line in (RUNS / f"{label}.log").read_text(encoding="utf-8").splitlines():
        text = line[10:]
        if text.startswith("{"):
            ev = json.loads(text)
            if ev.get("ev") == "output" and ev.get("kind") in (f"{kind}_cache_saved", f"{kind}_cache_hit"):
                out.append(Path(ev["path"]))
    return out


def grids_equal(a: Path, b: Path) -> dict:
    import h5py

    from wadi2d.tables import GridTables

    names = ["mask"] + [f.name for f in fields(GridTables) if f.name != "grid"]
    bad = []
    with h5py.File(a, "r") as fa, h5py.File(b, "r") as fb:
        for attr in ("x0", "y0", "dx"):
            if fa.attrs[attr] != fb.attrs[attr]:
                bad.append(attr)
        for name in names:
            if not np.array_equal(fa[name][()], fb[name][()], equal_nan=True):
                bad.append(name)
    return {"arrays": len(names), "different": bad}


def _walk(x, y, path: str, bad: list[str]) -> None:
    if isinstance(x, np.ndarray) or isinstance(y, np.ndarray):
        if not (isinstance(x, np.ndarray) and isinstance(y, np.ndarray) and x.shape == y.shape
                and np.array_equal(x, y, equal_nan=x.dtype.kind in "fc")):  # fmt: skip
            bad.append(path)
        return
    if isinstance(x, dict):
        if not isinstance(y, dict) or set(x) != set(y):
            bad.append(path)
            return
        for k in x:
            _walk(x[k], y[k], f"{path}.{k}", bad)
        return
    if isinstance(x, (list, tuple)):
        if not isinstance(y, (list, tuple)) or len(x) != len(y):
            bad.append(path)
            return
        for n, (p, q) in enumerate(zip(x, y, strict=True)):
            _walk(p, q, f"{path}[{n}]", bad)
        return
    if hasattr(x, "__dict__"):
        if type(x) is not type(y):
            bad.append(path)
            return
        _walk(vars(x), vars(y), path, bad)
        return
    if isinstance(x, float) and isinstance(y, float) and np.isnan(x) and np.isnan(y):
        return
    if x != y:
        bad.append(path)


def strips_equal(a: Path, b: Path) -> dict:
    with open(a, "rb") as f:
        x = pickle.load(f)
    with open(b, "rb") as f:
        y = pickle.load(f)
    bad: list[str] = []
    _walk(x["mask"], y["mask"], "mask", bad)
    _walk(x["strip"], y["strip"], "strip", bad)
    return {"different": bad[:20], "count": len(bad)}


def pits(label: str) -> list:
    path = RUNS / label / "terrain_checks.gpkg"
    with sqlite3.connect(path) as db:
        cols = [r[1] for r in db.execute('PRAGMA table_info("pits")')]
        keep = [c for c in cols if c not in ("fid",)]
        return db.execute(f'SELECT {", ".join(chr(34) + c + chr(34) for c in keep)} FROM "pits" ORDER BY fid').fetchall()


def text(label: str, name: str) -> str:
    return (RUNS / label / name).read_text(encoding="utf-8")


def main() -> None:
    before, after = sys.argv[1], sys.argv[2]
    out = {"before": before, "after": after}
    gb, ga = saved(before, "grid"), saved(after, "grid")
    sb, sa = saved(before, "strip"), saved(after, "strip")
    out["grid_files"] = [len(gb), len(ga)]
    out["grid"] = [grids_equal(p, q) for p, q in zip(gb, ga, strict=True)]
    out["strip"] = [strips_equal(p, q) for p, q in zip(sb, sa, strict=True)]
    pb, pa = pits(before), pits(after)
    out["pits"] = {"before": len(pb), "after": len(pa), "same": pb == pa}
    for name in ("terrain/volumes.csv", "terrain/volumes_by_station.csv"):
        out[name] = text(before, name) == text(after, name)
    jb = json.loads(text(before, "config.resolved.json"))
    ja = json.loads(text(after, "config.resolved.json"))
    for j in (jb, ja):
        j["grid"].pop("cache_dir", None)
        j["project"].pop("description", None)  # W79's session reworded run 3's between the two runs (11:12)
    out["config.resolved.json"] = jb == ja
    path = RUNS / f"compare_{before}_{after}.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
