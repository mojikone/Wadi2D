"""Write the Wadi2D job of the same case. The inflow shares along the west edge are read from the RAS run.

usage: build_wadi_job.py RAS_FOLDER JOB.json --dx 10 [--n 0.04]

RAS spreads a flow hydrograph along the boundary line by conveyance. Wadi2D injects at points, so each RAS boundary
face with more than a trace of the flow becomes one point in its boundary cell, carrying that face's share of the
volume over the event. This removes the placement of the inflow as a difference between the models.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import h5py
import numpy as np

import case

BC = "Results/Unsteady/Output/Output Blocks/Base Output/Unsteady Time Series/Boundary Conditions"


def shares(ras_folder: Path, dx: float) -> list[tuple[float, float]]:
    """(northing of the cell centre, share of the flow) per boundary face that carries more than a trace."""
    with h5py.File(ras_folder / "Fan.p01.hdf", "r") as f:
        d = f[BC]["Inflow - Flow per Face"]
        q = d[:]
        ids = d.attrs["Faces"]
        m = f["Geometry/2D Flow Areas/Fan"]
        ends = m["Faces FacePoint Indexes"][:][ids]
        xy = m["FacePoints Coordinate"][:]
    q = np.maximum(q, 0.0).sum(axis=0)
    s = q / q.sum()
    y = 0.5 * (xy[ends[:, 0], 1] + xy[ends[:, 1], 1])
    # snap to the row of cell centres; the end faces of the line are half cells long in RAS's stationing
    rows = np.floor((case.Y0 - y) / dx)
    y = case.Y0 - (rows + 0.5) * dx
    keep = s > 0.002
    return [(float(a), float(b)) for a, b in zip(y[keep], s[keep] / s[keep].sum())]


def job(ras_folder: Path, dx: float, manning: float, backend: str) -> dict:
    x0, y0, side = case.X0, case.Y0, case.SIDE
    t, q = case.hydrograph()
    # Wadi2D applies a table as the mean flow of each interval, RAS reads it linearly, so a 15 min table would
    # cut the 300 m3/s peak to the mean of its interval, 289.5. The job gets RAS's reading at 1 min.
    tf = np.arange(0.0, t[-1] + 1.0, 60.0)
    t, q = tf, np.interp(tf, t, q)
    x1, y1 = x0 + side, y0 - side
    inflows = [
        {
            "name": f"in{n:02d}",
            "x": x0 + 0.5 * dx,
            "y": y,
            "times_s": t.tolist(),
            "flows": (q * share).tolist(),
        }
        for n, (y, share) in enumerate(shares(ras_folder, dx))
    ]
    edge = 0.5 * dx
    lines = []
    for name, (off, a, b) in case.SECTIONS.items():
        xl = x0 + off
        lines.append({"name": name, "coordinates": [[xl, y0 - b], [xl, y0 - a]]})  # heading north: east is positive
    return {
        "project": {"name": f"ras_head_to_head_{dx:g}m", "description": "Same case as the HEC-RAS 6.6 project"},
        "grid": {"dx": dx, "extent": [x0, y1, x1, y0], "cache_dir": "cache"},
        "terrain": {"dem": str(case.DEM), "pixel_stride": 1, "manning": manning},
        "hydrology": {"inflows": inflows, "inject_radius": 0.6 * dx, "inject_min_depth": 0.1},
        "boundaries": [
            {
                "kind": "normal",
                "slope": case.SLOPE_OUT,
                "coordinates": [[x1 - edge, y0], [x1 - edge, y1]],
            },
            {
                "kind": "normal",
                "slope": case.SLOPE_OUT,
                "coordinates": [[x0, y0 - edge], [x1, y0 - edge]],
            },
        ],
        "outputs": {"map_every_s": 300.0, "series_every_s": 60.0, "live_every_s": 0.0, "lines": lines},
        "run": {"duration_s": case.DURATION_H * 3600.0, "backend": backend, "source_every_s": 30.0},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ras_folder")
    ap.add_argument("job")
    ap.add_argument("--dx", type=float, default=10.0)
    ap.add_argument("--n", type=float, default=case.MANNING)
    ap.add_argument("--backend", default="gpu")
    a = ap.parse_args()
    data = job(Path(a.ras_folder), a.dx, a.n, a.backend)
    Path(a.job).write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(a.job, len(data["hydrology"]["inflows"]), "inflow points")


if __name__ == "__main__":
    main()
