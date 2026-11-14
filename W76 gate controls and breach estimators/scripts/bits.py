"""Old jobs bit for bit: every W59, W62 and W67 case routed, its series saved to one .npz, to compare the engine of
this branch with the one before it (``git archive`` of the base commit put first on PYTHONPATH).

Usage: ``python bits.py <out.npz>``, then ``python bits.py --compare <a.npz> <b.npz>``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
NEW = {"gate_percent_sluice", "gate_percent_radial", "gate_annual_sluice"}


def main() -> None:
    if sys.argv[1] == "--compare":
        a, b = np.load(sys.argv[2]), np.load(sys.argv[3])
        same = [k for k in a.files if np.array_equal(a[k], b[k], equal_nan=True)]
        differ = [k for k in a.files if k not in same]
        print(f"{len(same)} series identical, {len(differ)} differ: {differ}")
        return
    sys.path.append(str(ROOT))
    from tests.hydrology.test_hms_structures import DATA, STEP_MINUTES, load_case, reservoir_of

    out = {}
    for path in sorted(DATA.glob("*.basin")):
        case = path.stem
        if case in NEW or ("_tw_" in case and case.startswith("gate")):
            continue
        try:
            run = reservoir_of(case).run(load_case(case)["inflow"], STEP_MINUTES)
        except Exception as error:  # a case the old engine refuses stays out of the comparison
            print(case, "refused:", error)
            continue
        for name in ("main_m3s", "auxiliary_m3s", "evaporation_m3s", "pool_m", "storage_m3"):
            out[f"{case}.{name}"] = getattr(run, name)
        for name, flow in run.structures_m3s.items():
            out[f"{case}.{name}"] = flow
    np.savez(sys.argv[1], **out)
    print(len(out), "series from", len({k.split('.')[0] for k in out}), "cases")


if __name__ == "__main__":
    main()
