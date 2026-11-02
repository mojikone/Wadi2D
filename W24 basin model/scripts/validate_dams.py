"""The generated reservoirs of Faydh 01 and Bidah 03 against the dam team's EAV curves and Modified Puls on them.

Reads Block 2 and the whole-catchment validation only. The terrain is NSA 5 m, the datum of the dam levels. Run from the
repository root with the worktree first on PYTHONPATH; writes `W24 basin model/results/dams.json`.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from wadi2d.basin import load_network
from wadi2d.basin.build import assemble
from wadi2d.basin.contract import value_of
from wadi2d.config.schema import BasinSettings
from wadi2d.hydrology.reservoir import ReservoirOutflowStructures, Spillway
from wadi2d.run import load_job

HERE = Path(__file__).resolve().parents[1]
FULL = HERE.parent / "W1 research and design note" / "validation" / "block2_full"
EAV = Path(r"D:\Mojtaba\Renardet\2224 WS11\Batinah\Block 2\Hydrology\SHP\Block 2 Dams\EAV")
DAMS = {
    "Faydh01": {"name": "Faydh 01", "fsl": 230.0, "crest": 235.0, "puls": 908.0, "level": 231.63},
    "Bidah03": {"name": "Bidah 03", "fsl": 100.0, "crest": 105.0, "puls": 220.0, "level": 101.28},
}
STEP_MINUTES = 5.0


def read_eav(name: str) -> dict[str, np.ndarray]:
    with open(EAV / f"{name} EAV.csv", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.reader(source))
    columns = np.array(rows[1:], dtype=np.float64)
    return {"area": columns[:, 0], "elevation": columns[:, 1], "volume": columns[:, 2]}


def read_inflow(key: str) -> np.ndarray:
    with open(FULL / f"inflow_{key}_100yr.csv", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    return np.array([float(row["q_m3s"]) for row in rows])


def routed(curve: ReservoirOutflowStructures, inflow: np.ndarray) -> float:
    return float(curve.branches(inflow, STEP_MINUTES)[0].max())


def compare(key: str, spec: dict) -> dict:
    cfg = load_job(HERE / "jobs" / f"dam_{key}.json")
    assembly = assemble(cfg, BasinSettings())
    model = assembly.model
    dam = next(e for e in model["elements"] if e["name"] == "Dam1")
    levels = np.array(value_of(dam, "elevation_m"))
    volumes = np.array(value_of(dam, "volume_m3"))
    areas = np.array(value_of(dam, "area_m2"))
    eav = read_eav(spec["name"])
    rating = value_of(dam, "spillways")
    curve = load_network(model, skip_incomplete=True).elements["Dam1"].routing
    storage = curve.storage_m3
    inflow = read_inflow(key)
    spillways = tuple(Spillway(**item) for item in rating)
    reference = ReservoirOutflowStructures(eav["elevation"], eav["area"], spillways, spec["fsl"])
    out: dict = {
        "notes": model["notes"],
        "drainage_km2": value_of(dam, "drainage_area_km2"),
        "spillways": rating,
        "peak_inflow": round(float(inflow.max()), 1),
        "generated_peak": round(routed(curve, inflow), 1),
        "eav_peak": round(routed(reference, inflow), 1),
        "w1_puls_peak": spec["puls"],
    }
    for label, level in (("fsl", spec["fsl"]), ("crest", spec["crest"])):
        out[label] = {
            "level": level,
            "eav_volume": round(float(np.interp(level, eav["elevation"], eav["volume"]))),
            "volume": round(float(np.interp(level, levels, volumes))),
            "engine_storage": round(float(np.interp(level, levels, storage))),
            "eav_area": round(float(np.interp(level, eav["elevation"], eav["area"]))),
            "area": round(float(np.interp(level, levels, areas))),
        }
    return out


def main() -> None:
    out = {key: compare(key, spec) for key, spec in DAMS.items()}
    (HERE / "results" / "dams.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
