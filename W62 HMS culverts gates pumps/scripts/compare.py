"""Every W62 case through Wadi2D's reader and reservoir against HMS's own series; ``results/compare.json``.

Columns as W59's compare: outflow difference (of HMS's peak), peak, pool, storage; plus each pump's state agreement
(steps where ours is on and HMS's off or the reverse) and HMS's unbooked volume.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent / "tests" / "hydrology"))
from test_hms_structures import load_case, reservoir_of  # noqa: E402

STEP_MINUTES = 5.0
DT = STEP_MINUTES * 60.0
CASES = [
    "gate_sluice", "gate_radial", "gate_two", "pump", "pump_tw", "pump_closed", "pump_cycle", "pump_intake",
    "pump_times", "pump_rest", "pump_on_band", "pump_off_band",
]


def main() -> None:
    out = {}
    for case in sys.argv[1:] or CASES:
        hms = load_case(case)
        run = reservoir_of(case).run(hms["inflow"], STEP_MINUTES)
        peak = float(np.abs(hms["outflow"]).max())
        balance = np.diff(hms["storage_m3"]) - DT * 0.5 * (
            hms["inflow"][1:] + hms["inflow"][:-1] - hms["outflow"][1:] - hms["outflow"][:-1]
        )
        row = {
            "hms_outflow_peak_m3s": peak,
            "outflow_max_abs_diff_of_peak": float(np.abs(run.main_m3s - hms["outflow"]).max() / peak),
            "outflow_peak_rel_diff": float(run.main_m3s.max() / hms["outflow"].max() - 1.0),
            "pool_max_abs_diff_m": float(np.abs(run.pool_m - hms["elevation_m"]).max()),
            "storage_max_rel_diff": float(np.abs(run.storage_m3 - hms["storage_m3"]).max() / hms["storage_m3"].max()),
            "hms_unbooked_m3": float(balance.sum()),
        }
        if "pump_1" in hms:
            ours = run.structures_m3s["pump_1_m3s"] > 0
            theirs = hms["pump_1"] > 0
            row["pump_state_disagreements"] = int((ours != theirs).sum())
            row["pump_switches_hms"] = [int(k + 1) for k in np.flatnonzero(np.diff(theirs.astype(int)))]
            row["pump_switches_ours"] = [int(k + 1) for k in np.flatnonzero(np.diff(ours.astype(int)))]
        if "spill_1" in hms and any(k.startswith("gate") for k in run.structures_m3s):
            gates = sum(v for k, v in run.structures_m3s.items() if k.startswith("gate"))
            row["gate_flow_max_abs_diff_of_peak"] = float(np.abs(gates - hms["spill_1"]).max() / peak)
        out[case] = row
        print(case, {k: (f"{v:.2e}" if isinstance(v, float) else v) for k, v in row.items()})
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "compare.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
