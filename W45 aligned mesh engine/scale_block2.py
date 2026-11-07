"""How the corridor builder scales: Block 2 at 30 m with every stream over 0.1 km2 as a bank pair.

The dock's Block 2 hybrid job (W33) at 30 m; the Suggest (``wadi2d breaklines``) with ``stream_area_mid_km2`` 0.1;
the corridors from its banks; the strip mesh and its tables. Each phase timed, so the slow ones are known before the
full domain is tried.

    .venv\\Scripts\\python "W45 aligned mesh engine\\scale_block2.py" <work folder>
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import shapely

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wadi2d.config.schema import RunConfig  # noqa: E402
from wadi2d.strips.banks import corridor_specs, pair_banks, read_layers  # noqa: E402
from wadi2d.terrain.vector import read_features  # noqa: E402

SOURCE = ROOT / "W33 backend parity" / "dock_hms_job.json"
THRESHOLD_KM2 = 0.1
DX = 30.0


def main(work: Path) -> None:
    work.mkdir(parents=True, exist_ok=True)
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    data["grid"]["dx"] = DX
    data["grid"]["cache_dir"] = str(work / "cache")
    data.setdefault("mesh", {})["stream_area_mid_km2"] = THRESHOLD_KM2
    data["mesh"]["enabled"] = False
    data["outputs"]["map_every_s"] = 0.0
    data["outputs"]["live_every_s"] = 0.0
    data["outputs"]["pixels"] = {"enabled": False}
    data["run"]["backend"] = "gpu"
    job = work / "block2_30m.json"
    job.write_text(json.dumps(data, indent=1), encoding="utf-8")
    report: dict = {"dx": DX, "threshold_km2": THRESHOLD_KM2}
    exe = ROOT / ".venv" / "Scripts" / "wadi2d.exe"

    t0 = time.perf_counter()
    done = subprocess.run([str(exe), "breaklines", str(job), "--out", str(work / "suggest")], capture_output=True, text=True)
    report["suggest_s"] = round(time.perf_counter() - t0, 1)
    (work / "suggest.log").write_text(done.stdout + "\n" + done.stderr, encoding="utf-8")
    event = None
    for line in reversed(done.stdout.strip().splitlines()):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict) and e.get("ev") == "breaklines":
            event = e
            break
    if event is None:
        print("suggest failed:", done.returncode, done.stderr[-800:])
        return
    gpkg = Path(event["path"])
    report["banks"], report["thalwegs"], report["crests"] = event["banks"], event["thalwegs"], event["crests"]
    print(f"suggest: {report['suggest_s']} s, {event['banks']} banks on {event['thalwegs']} thalwegs, {event['crests']} crests")

    t0 = time.perf_counter()
    banks, thalwegs = read_layers(gpkg)
    pairs = pair_banks(banks, thalwegs)
    report["pairs"], report["pair_s"] = len(pairs), round(time.perf_counter() - t0, 1)
    print(f"pairs: {len(pairs)} in {report['pair_s']} s from {len(banks)} bank parts")
    cfg = RunConfig.model_validate(data)
    domain = shapely.union_all([shape for _p, shape in read_features(cfg.grid.domain, "")])
    t0 = time.perf_counter()
    specs, cut = corridor_specs(pairs, domain, 10.0, 3, DX)
    report["corridors"], report["cut"], report["corridor_s"] = len(specs), len(cut), round(time.perf_counter() - t0, 1)
    km = sum(float(np.hypot(*np.diff(np.asarray(s["centre"]), axis=0).T).sum()) for s in specs) / 1000.0
    report["corridor_km"] = round(km, 1)
    print(f"corridors: {len(specs)} along {km:.1f} km in {report['corridor_s']} s, {len(cut)} cut")

    data["strips"] = {"enabled": True, "banks": str(gpkg)}
    strips_job = work / "block2_30m_strips.json"
    strips_job.write_text(json.dumps(data, indent=1), encoding="utf-8")
    from wadi2d.run import prepare_grid

    t0 = time.perf_counter()
    plain, _ = prepare_grid(RunConfig.model_validate({**data, "strips": {"enabled": False}}), work / "cache")
    report["lattice_tables_s"] = round(time.perf_counter() - t0, 1)
    report["lattice_cells"] = int(plain.grid.mask.sum())
    print(f"lattice tables: {report['lattice_cells']} cells in {report['lattice_tables_s']} s (cached from here on)")
    t0 = time.perf_counter()
    tables, _ = prepare_grid(RunConfig.model_validate(data), work / "cache")
    report["strip_build_s"] = round(time.perf_counter() - t0, 1)
    st = tables.strip
    report["strip_cells"] = int(st.mesh.real)
    report["corridor_cells"] = int((st.strip.corridor >= 0).sum())
    report["triangles"] = int((st.strip.corridor < 0).sum())
    report["faces"] = int(st.mesh.nfaces)
    report["replaced"] = int(st.strip.masked[0].size)
    report["dn_min"] = float(st.mesh.dn.min())
    print(
        f"strip: {report['corridor_cells']} corridor cells, {report['triangles']} triangles, {report['faces']} faces, "
        f"{report['replaced']} squares replaced, built with its tables in {report['strip_build_s']} s (lattice cached)"
    )
    (work / "scale.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
