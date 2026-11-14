"""Every W76 case routed by the engine against HEC-HMS 4.12: worst outflow difference of the peak, peak, pool, and the
law at HMS's own levels. Writes ``results/compare.json``.

Usage: ``python compare.py`` from the repository root (needs ``tests`` importable).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.hydrology.test_hms_gate_controls import ALL_CASES, law_at_hms_levels, routed  # noqa: E402
from tests.hydrology.test_hms_structures import STEP_MINUTES, load_case  # noqa: E402


def main() -> None:
    out = {}
    for case in ALL_CASES:
        hms = load_case(case)
        run = routed(case)
        peak = float(np.abs(hms["outflow"]).max())
        out[case] = {
            "hms_peak_m3s": peak,
            "max_outflow_difference_of_peak": float(np.abs(run.main_m3s - hms["outflow"]).max() / peak),
            "peak_difference_of_peak": float((run.main_m3s.max() - peak) / peak),
            "max_pool_difference_m": float(np.abs(run.pool_m - hms["elevation_m"]).max()),
            "law_at_hms_levels_of_peak": float(np.abs(law_at_hms_levels(case) - hms["spill_1"]).max() / peak),
            "step_minutes": STEP_MINUTES,
        }
        print(case, {k: f"{v:.3g}" for k, v in out[case].items()})
    target = Path(__file__).resolve().parents[1] / "results" / "compare.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
