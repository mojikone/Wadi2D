"""Overtopping at heads the crest coefficients were not fitted at: the sweep's box at 0.3 and 1.2 m as well as 0.6 m.

Writes crest_heads.csv beside this file. Q over critical flow at each head, the same crest over cell sizes and snaps.
"""

import csv
import tempfile
from pathlib import Path

import crest_sweep as sweep

HEADS = (0.3, 0.6, 1.2)
CASES = ((20, 5), (10, 5), (8, 6), (4, 6), (2, 4))
SLOPE = 2.0
SNAPS = (0.0, 0.5)


def main() -> None:
    rows = []
    with tempfile.TemporaryDirectory(prefix="wadi2d_heads_") as name:
        work = Path(name)
        for dx, width in CASES:
            for head in HEADS:
                sweep.HEAD = head
                values = [sweep.ratio(work, float(dx), snap, float(width), SLOPE) for snap in SNAPS]
                rows.append([dx, width, round(width / dx, 2), head, *(round(v, 3) for v in values)])
                print(rows[-1], flush=True)
    with (Path(__file__).resolve().parent / "crest_heads.csv").open("w", newline="", encoding="utf-8") as stream:
        table = csv.writer(stream)
        table.writerow(["dx_m", "crest_m", "crest_over_dx", "head_m", *(f"q_over_qcrit_snap_{s}" for s in SNAPS)])
        table.writerows(rows)


if __name__ == "__main__":
    main()
