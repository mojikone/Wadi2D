"""Suggested breaklines on Faydh 01 (W11's 20 m domain) and Bidah 03 (W41's PMP job) with the engine's own bank rule,
through the ``breaklines`` command the dock runs: the banks files the corridor races and the cell-size trials take.

    .venv\\Scripts\\python "W45 aligned mesh engine\\suggest_banks.py" <out folder> [--rise <m>] [--depth-map <tif> <m>]

Writes ``<out>/faydh/suggested_breaklines.gpkg`` and ``<out>/bidah/...`` with the job each came from beside it.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
W11 = ROOT / "W11 validation round two" / "t2_faydh"
W41 = ROOT / "W41 hybrid design lines" / "jobs" / "pmp_hybrid_s13_above.json"


def jobs(out: Path) -> dict[str, dict]:
    faydh = json.loads((W11 / "jobs" / "10m_n050_em.json").read_text(encoding="utf-8"))
    faydh["grid"]["dx"] = 20.0
    faydh["grid"]["domain"] = str(W11 / "domain_wadi_20m.geojson")
    faydh["grid"]["cache_dir"] = str(out / "cache")
    bidah = json.loads(W41.read_text(encoding="utf-8"))
    bidah["grid"]["cache_dir"] = str(out / "cache")
    bidah.setdefault("mesh", {})["enabled"] = False
    return {"faydh": faydh, "bidah": bidah}


def main(argv: list[str]) -> None:
    out = Path(argv[1])
    settings: dict = {}
    if "--rise" in argv:
        settings["bank_rise_m"] = float(argv[argv.index("--rise") + 1])
    if "--depth-map" in argv:
        k = argv.index("--depth-map")
        settings["bank_depth_map"] = argv[k + 1]
        settings["bank_depth_m"] = float(argv[k + 2])
    exe = ROOT / ".venv" / "Scripts" / "wadi2d.exe"
    for site, data in jobs(out).items():
        folder = out / site
        folder.mkdir(parents=True, exist_ok=True)
        if settings:
            data["breaklines"] = settings
        job = folder / "suggest_job.json"
        job.write_text(json.dumps(data, indent=1), encoding="utf-8")
        t0 = time.perf_counter()
        done = subprocess.run([str(exe), "breaklines", str(job), "--out", str(folder)], capture_output=True, text=True)
        (folder / "suggest.log").write_text(done.stdout + "\n" + done.stderr, encoding="utf-8")
        event = next((json.loads(s) for s in reversed(done.stdout.strip().splitlines()) if s.startswith("{")), None)
        print(f"{site}: exit {done.returncode} in {time.perf_counter() - t0:.0f} s: "
              + (f"{event['banks']} banks over {event['bank_km']} km on {event['thalwegs']} thalwegs, {event['crests']} crests; {event['bank_rule']}" if event else done.stderr[-400:]))
        if event:
            (folder / "summary.json").write_text(json.dumps(event, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv)
