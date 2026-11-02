"""Overtopping of a raised crest against critical flow, on the committed code: crest over cell size, slope, snap.

Writes crest_sweep.csv beside this file. With ``gpu`` as an argument it also runs one case on both backends.
A box 120 m wide, a reservoir held 0.6 m over a crest at 102 m, a free fall behind it, 4 pixels per cell.
"""

import csv
import shutil
import sys
import tempfile
from pathlib import Path

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from tests.engine.conftest import X0, Y0, job, write_dem  # noqa: E402
from wadi2d.config.constants import CRITICAL_WEIR_COEFF as C  # noqa: E402
from wadi2d.run import run_job  # noqa: E402

CREST, HEAD, WIDTH = 102.0, 0.6, 120.0
CASES = (
    (20, 3),
    (20, 5),
    (12, 3),
    (10, 3),
    (10, 5),
    (8, 3),
    (8, 4),
    (8, 6),
    (6, 6),
    (6, 8),
    (4, 4),
    (4, 6),
    (4, 8),
    (2, 2),
    (2, 3),
    (2, 4),
    (2, 6),
)
SLOPES = (2.0, 3.0)
SNAPS = (0.0, 0.25, 0.5, 0.75)


def ratio(work: Path, dx: float, snap: float, width: float, slope: float, backend: str = "cpu") -> float:
    pixel = dx / 4.0
    nx, ny = round(320.0 / pixel), round(WIDTH / pixel)
    x = (np.arange(nx) + 0.5) * pixel
    z = np.where(x > 200.0, 95.0, 100.0)[None, :].repeat(ny, axis=0)
    dem = write_dem(work / "d.tif", z, pixel)
    line_x = 148.0 - (148.0 % dx) + snap * dx
    section = {"width": width, "left_slope": slope, "right_slope": slope}
    obj = {
        "kind": "embankment",
        "coordinates": [(X0 + line_x, Y0 - WIDTH), (X0 + line_x, Y0)],
        "z_constant": CREST,
        "section": section,
    }
    far = X0 - 50.0
    edge = X0 + line_x - 20.0
    ring = [(far, Y0 + 50.0), (edge, Y0 + 50.0), (edge, Y0 - WIDTH - 50.0), (far, Y0 - WIDTH - 50.0)]
    cfg = job(
        dem, round(320.0 / dx), round(WIDTH / dx), dx,
        terrain={"objects": [obj]},
        boundaries=[
            {"kind": "stage", "coordinates": [(X0 + dx / 2, Y0), (X0 + dx / 2, Y0 - WIDTH)], "stage": CREST + HEAD},
            {"kind": "free", "coordinates": [(X0 + 320.0 - dx / 2, Y0), (X0 + 320.0 - dx / 2, Y0 - WIDTH)]},
        ],
        initial_levels=[{"coordinates": ring, "level": CREST + HEAD}],
        run={"duration_s": 700.0, "source_every_s": 30.0, "backend": backend},
        outputs={"lines": [{"name": "o", "coordinates": [(X0 + 260.0, Y0), (X0 + 260.0, Y0 - WIDTH)]}], "series_every_s": 5.0},
    )  # fmt: skip
    out = work / "r"
    shutil.rmtree(out, ignore_errors=True)
    run = run_job(cfg, out)
    if run.exit_code:
        raise RuntimeError(run.message)
    with h5py.File(out / "results.h5", "r") as f:
        q = np.abs(f["series/lines/o/discharge_m3s"][()])[-30:].mean()
    return float(q / (C * WIDTH * HEAD**1.5))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="wadi2d_sweep_") as name:
        work = Path(name)
        if "gpu" in sys.argv:
            for dx, width, snap in ((8.0, 4.0, 0.5), (2.0, 4.0, 0.0), (4.0, 6.0, 0.25)):
                print(
                    dx,
                    width,
                    "cpu",
                    round(ratio(work, dx, snap, width, 2.0, "cpu"), 4),
                    "gpu",
                    round(ratio(work, dx, snap, width, 2.0, "gpu"), 4),
                    flush=True,
                )
            return
        rows = []
        for slope in SLOPES:
            for dx, width in CASES:
                values = [ratio(work, float(dx), snap, float(width), slope) for snap in SNAPS]
                rows.append([dx, width, round(width / dx, 2), slope, *(round(v, 3) for v in values)])
                print(rows[-1], flush=True)
    with (HERE / "crest_sweep.csv").open("w", newline="", encoding="utf-8") as stream:
        table = csv.writer(stream)
        table.writerow(
            ["dx_m", "crest_m", "crest_over_dx", "slope", *(f"q_over_qcrit_snap_{s}" for s in SNAPS)]
        )
        table.writerows(rows)


if __name__ == "__main__":
    main()
