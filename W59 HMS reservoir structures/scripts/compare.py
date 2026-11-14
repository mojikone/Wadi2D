"""Every W59 case through Wadi2D's reader and reservoir, against HMS's own series: outflow, pool, storage, structures.

HMS's inflow of record (FLOW-COMBINE) is routed by the reservoir the reader builds from HMS's own basin file and the
tables of the test project; the differences are written to ``results/compare.json`` and printed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parent / "tests" / "hydrology"))
from test_hms_structures import CASES, EVAPORATION_ONLY, load_case, reservoir_of  # noqa: E402

STEP_MINUTES = 5.0


def main() -> None:
    out = {}
    for case in [*CASES, EVAPORATION_ONLY]:
        hms = load_case(case)
        routing = reservoir_of(case)
        run = routing.run(hms["inflow"], STEP_MINUTES)
        peak = float(np.abs(hms["outflow"]).max())
        row = {
            "hms_outflow_peak_m3s": peak,
            "outflow_max_abs_diff_m3s": float(np.abs(run.main_m3s - hms["outflow"]).max()),
            "outflow_peak_rel_diff": float(run.main_m3s.max() / hms["outflow"].max() - 1.0),
            "pool_max_abs_diff_m": float(np.abs(run.pool_m - hms["elevation_m"]).max()),
            "storage_max_rel_diff": float(np.abs(run.storage_m3 - hms["storage_m3"]).max() / hms["storage_m3"].max()),
            "hms_pool_max_m": float(hms["elevation_m"].max()),
        }
        if "evaporation_m3" in hms:
            volume = 0.5 * (run.evaporation_m3s[1:] + run.evaporation_m3s[:-1]) * STEP_MINUTES * 60.0
            row["evaporation_volume_rel_diff"] = float(volume.sum() / hms["evaporation_m3"].sum() - 1.0)
        out[case] = row
        print(f"{case:14s} peak {peak:8.3f} | dQ {row['outflow_max_abs_diff_m3s']:.2e} ({row['outflow_max_abs_diff_m3s'] / peak:.1e} "
              f"of peak) peak {row['outflow_peak_rel_diff']:+.1e} | dz {row['pool_max_abs_diff_m']:.1e} | dS "
              f"{row['storage_max_rel_diff']:.1e}" + (f" | evap {row['evaporation_volume_rel_diff']:+.1e}" if "evaporation_volume_rel_diff" in row else ""))
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "compare.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
