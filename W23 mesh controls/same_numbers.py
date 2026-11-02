"""Existing jobs on the code before and after D3: every series and map, compared exactly.

usage: python same_numbers.py run TREE OUT      runs the cases on the wadi2d of TREE, one process, into OUT
       python same_numbers.py compare OLD NEW   exact comparison of two OUT folders; exit 1 on any difference

TREE is a checkout. The caller sets PYTHONPATH to it; this file checks that it got that tree. config.resolved.json differs by
design, by the new empty mesh.lines, so it is compared with that one key taken out. Timing files are not compared.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import h5py
import rasterio

JOB = Path(r"D:\Mojtaba\Renardet\Wadi2D\W1 research and design note\validation\ras_rain_on_grid\jobs\10m_n050_em.json")
SHORT_S = 7200.0
"""Short enough for the CPU."""
SHORT_STORM = {"kind": "uniform", "depth_mm": 60.0, "duration_min": 60.0}
"""Rain from the first minute, so that a short case carries water on every path."""
MESH = {"enabled": True, "coarse_dx": 40.0}
CASES = {
    "uniform_gpu": {"backend": "gpu"},
    "uniform_cpu": {"backend": "cpu", "duration": SHORT_S, "dx": 20.0},
    "mesh_gpu": {"backend": "gpu", "mesh": MESH},
    "mesh_gpu_local": {"backend": "gpu", "mesh": MESH, "local": True},
    "mesh_cpu": {"backend": "cpu", "duration": SHORT_S, "mesh": MESH},
    "mesh_zones_gpu": {
        "backend": "gpu", "duration": SHORT_S, "mesh": {**MESH, "stream_area_fine_km2": 1.0e6, "stream_area_mid_km2": 1.0e6},
        "zone": [(438000.0, 2726800.0), (439000.0, 2726800.0), (439000.0, 2727600.0), (438000.0, 2727600.0)],
    },
}  # fmt: skip
SKIP = {"progress.jsonl", "run.json", "summary.json", "cell_grid.gpkg", "config.resolved.json", "live.tif"}
BALANCE_NOTE = "the bookkeeping total on the card, compared apart: two runs of the same code differ by as much"


def config(spec: dict, cache: Path):
    from wadi2d.config.schema import RunConfig
    from wadi2d.run import load_job

    data = load_job(JOB).model_dump(mode="json")
    data["grid"]["cache_dir"] = str(cache)
    data["run"]["backend"] = spec["backend"]
    data["outputs"]["map_every_s"] = 3600.0
    data["outputs"]["series_every_s"] = 60.0
    if "duration" in spec:
        data["run"]["duration_s"] = spec["duration"]
        data["storm"] = SHORT_STORM  # the job's own storm is dry for its first hours: a short run of it proves nothing
    if "dx" in spec:
        data["grid"]["dx"] = spec["dx"]
    if "mesh" in spec:
        data["mesh"] = {**data["mesh"], **spec["mesh"]}
    if spec.get("local"):
        data["numerics"]["local_time_stepping"] = True
    if "zone" in spec:
        data["mesh"]["zones"] = [{"coordinates": spec["zone"], "dx": 20.0}]
    return RunConfig.model_validate(data)


def run(tree: str, out: str, only: list[str]) -> None:
    import wadi2d
    from wadi2d.engine.cli import main as cli
    from wadi2d.run import run_job

    assert Path(wadi2d.__file__).is_relative_to(Path(tree)), wadi2d.__file__
    print("engine", wadi2d.__file__, flush=True)
    root = Path(out)
    for name, spec in CASES.items():
        if only and name not in only:
            continue
        cfg = config(spec, root / "cache")
        summary = run_job(cfg, root / name)
        record = {
            "exit": summary.exit_code, "cells": summary.cells, "steps": summary.steps, "dt_min": summary.dt_min,
            "peaks": summary.peaks, "balance": repr(summary.balance), "wet": summary.wet_area_km2,
        }  # fmt: skip
        (root / name / "numbers.json").write_text(json.dumps(record, indent=1, default=repr), encoding="utf-8")
        print(name, summary.status, summary.cells, summary.steps, flush=True)
        if "mesh" in spec:
            job = root / name / "job_for_preview.json"
            job.write_text(cfg.model_dump_json(), encoding="utf-8")
            cli(["mesh", str(job), "--out", str(root / name / "preview")])


def h5_digest(path: Path) -> str:
    """Every dataset, name and value; the file's attributes hold the config and the balance, compared on their own."""
    out = hashlib.sha256()
    with h5py.File(path) as f:
        names: list[str] = []
        f.visit(names.append)
        for name in sorted(names):
            if isinstance(f[name], h5py.Dataset):
                out.update(name.encode())
                out.update(f[name][()].tobytes())
    return out.hexdigest()


def gpkg_digest(path: Path) -> str:
    """Every row of every layer; the file also stamps the time it was written."""
    out = hashlib.sha256()
    with sqlite3.connect(path) as db:
        for (table,) in db.execute("select table_name from gpkg_contents order by table_name").fetchall():
            for row in db.execute(f'select * from "{table}" order by 1'):
                out.update(repr(row).encode())
    return out.hexdigest()


def digest(path: Path) -> str:
    if path.suffix == ".tif":
        with rasterio.open(path) as src:
            return hashlib.sha256(src.read().tobytes()).hexdigest()
    if path.suffix == ".h5":
        return h5_digest(path)
    if path.suffix == ".gpkg":
        return gpkg_digest(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def balance_of(folder: Path) -> tuple[float, float]:
    """(rain, outflow and storage as text): rain is a sum run on the card, see BALANCE_NOTE."""
    text = json.loads((folder / "numbers.json").read_text(encoding="utf-8"))["balance"]
    fields = dict(part.split("=") for part in text[len("Balance("):-1].split(", "))
    return float(fields["rain"]), f"{fields['outflow']} {fields['storage']}"


def numbers_of(folder: Path) -> dict:
    """numbers.json with the balance taken out."""
    data = json.loads((folder / "numbers.json").read_text(encoding="utf-8"))
    data.pop("balance")
    return data


def files(folder: Path) -> dict[str, str]:
    return {
        str(p.relative_to(folder)): digest(p)
        for p in sorted(folder.rglob("*"))
        if p.is_file() and p.name not in SKIP and p.parent.name != "cache" and not p.name.startswith("job_for_preview")
    }


def resolved(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["mesh"].pop("lines", None)
    return data


def compare(old: str, new: str) -> int:
    bad = 0
    worst_rain = 0.0
    for name in CASES:
        a, b = Path(old) / name, Path(new) / name
        fa, fb = files(a), files(b)
        names = set(fa) | set(fb)
        missing = sorted(n for n in names if n not in fa or n not in fb)
        moved = sorted(n for n in names - set(missing) if fa[n] != fb[n])
        moved = [n for n in moved if n not in (str(Path("preview") / "mesh.json"), "numbers.json")]
        if numbers_of(a) != numbers_of(b):
            moved.append("numbers.json")
        rain_a, rest_a = balance_of(a)
        rain_b, rest_b = balance_of(b)
        if rest_a != rest_b:
            moved.append("balance")
        if rain_a <= 0.0:
            moved.append("a case with no rain proves nothing")
        rain_gap = abs(rain_a - rain_b) / max(rain_a, 1.0)
        worst_rain = max(worst_rain, rain_gap)
        ra, rb = resolved(a / "config.resolved.json"), resolved(b / "config.resolved.json")
        for part in (ra, rb):
            part["grid"]["cache_dir"] = ""
        same_config = ra == rb
        if (a / "preview" / "mesh.json").exists():
            pa = json.loads((a / "preview" / "mesh.json").read_text(encoding="utf-8"))
            pb = json.loads((b / "preview" / "mesh.json").read_text(encoding="utf-8"))
            pb.pop("lines", None)
            if pa != pb:
                moved.append("preview/mesh.json")
        verdict = "identical" if not (missing or moved) and same_config else "DIFFERENT"
        print(
            f"{name}: {len(names)} files, {verdict}, rain total off by {rain_gap:.1e}",
            "" if verdict == "identical" else (missing, moved, same_config),
        )
        bad += verdict != "identical"
    print(f"largest gap in the rain total {worst_rain:.1e}; {BALANCE_NOTE}")
    return int(bad > 0)


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(sys.argv[2], sys.argv[3], sys.argv[4:])
    else:
        raise SystemExit(compare(sys.argv[2], sys.argv[3]))
