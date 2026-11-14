"""W70 study: a flow line's water entering at rest (W61) against entering with its momentum (W70), on the CPU.

Run from the repository root:  .venv\\Scripts\\python "W70 inflow line momentum\\study.py" <out folder>
Writes study.json beside this file. Cases:
  plane   W61's plane, 1 % east, 96 m wide, 20 m3/s across the west edge: the depth profile from the line.
  steep   the same plane at 3 % carrying 50 m3/s (Froude about 1.2): the bump against the wall behind the line.
  jet     a flat plain 400 x 400 m, 8 m3/s through a 16 m line on its west edge at Froude about 2.6: the jet.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.engine.conftest import X0, Y0, job, tilted_box, write_dem  # noqa: E402
from wadi2d.run import run_job  # noqa: E402

G = 9.81


def last_map(run_dir: Path) -> dict[str, np.ndarray]:
    with h5py.File(run_dir / "results.h5", "r") as f:
        maps = f["maps"]
        last = max(maps, key=lambda k: maps[k].attrs["t_s"])
        out = {k: maps[last][k][()] for k in ("depth", "mean_depth", "speed")}
        out["t_s"] = float(maps[last].attrs["t_s"])
        return out


def channel(tmp: Path, name: str, slope: float, q: float, width_cells: int, momentum: bool, duration: float) -> dict:
    nx, dx, n = 100, 4.0, 0.04
    dem = write_dem(tmp / f"{name}.tif", tilted_box(2 * nx, 2 * width_cells, 2.0, slope), 2.0)
    wide = width_cells * dx
    west = [(X0 + 2.0, Y0 - 1.0), (X0 + 2.0, Y0 - wide + 1.0)]
    line = {"kind": "flow", "coordinates": west, "flow": {"times_s": [0.0, 1e6], "flows": [q, q], "slope": slope,
                                                          "momentum": momentum}}  # fmt: skip
    outlet = {"kind": "free", "coordinates": [(X0 + nx * dx - 2.0, Y0 + 2.0), (X0 + nx * dx - 2.0, Y0 - wide - 2.0)]}
    cfg = job(
        dem, nx, width_cells, dx, terrain={"manning": n}, boundaries=[line, outlet],
        run={"duration_s": duration, "backend": "cpu", "source_every_s": 10.0},
        outputs={"map_every_s": duration / 4.0, "series_every_s": 60.0},
    )  # fmt: skip
    out = tmp / f"{name}_{'on' if momentum else 'off'}"
    run = run_job(cfg, out)
    assert run.exit_code == 0, run.message
    m = last_map(out)
    h = m["mean_depth"][:width_cells, :nx].mean(axis=0)  # across the channel, per column (the tiles pad the grid)
    normal = (q / wide * n / np.sqrt(slope)) ** 0.6
    first = int(np.argmax(h > 0.0))  # the line's column: the edge column is outside the domain
    far = float(h[62])
    return {
        "line_cell_over_far": round(float(h[first]) / far, 4),
        "worst_first_5_over_far": round(float(h[first : first + 5][np.argmax(np.abs(h[first : first + 5] - far))]) / far, 4),
        "normal_depth_m": normal,
        "froude": q / wide / normal / np.sqrt(G * normal),
        "depth_by_column_m": [round(float(v), 4) for v in h[:20]],
        "depth_at_250m": round(float(h[62]), 4),
        "bump_first_cell": round(float(h[0] / normal), 4),
        "max_over_normal_first_5": round(float(h[:5].max() / normal), 4),
        "inflow_m3": run.balance.inflow, "balance_relative": run.balance.relative,
    }  # fmt: skip


def jet(tmp: Path, momentum: bool, duration: float = 120.0, n: float = 0.01) -> dict:
    nx, dx, q, s = 100, 4.0, 8.0, 0.05
    dem = write_dem(tmp / "flat.tif", np.full((2 * nx, 2 * nx), 100.0), 2.0)
    mid = Y0 - 0.5 * nx * dx
    line = [(X0 + 2.0, mid + 8.0), (X0 + 2.0, mid - 8.0)]
    flow = {"times_s": [0.0, 1e6], "flows": [q, q], "slope": s, "momentum": momentum}
    cfg = job(
        dem, nx, nx, dx, terrain={"manning": n}, boundaries=[{"kind": "flow", "coordinates": line, "flow": flow}],
        run={"duration_s": duration, "backend": "cpu", "source_every_s": 5.0},
        outputs={"map_every_s": duration / 4.0, "series_every_s": 60.0},
    )  # fmt: skip
    out = tmp / f"jet_{'on' if momentum else 'off'}"
    run = run_job(cfg, out)
    assert run.exit_code == 0, run.message
    m = last_map(out)
    with h5py.File(out / "results.h5", "r") as f:
        last = max(f["maps"], key=lambda k: f["maps"][k].attrs["t_s"])
        qx = f["maps"][last]["qx"][()]
    h = m["mean_depth"]
    wet = h > 0.01
    jj, ii = np.nonzero(wet)
    yc = (jj + 0.5) * dx - 0.5 * nx * dx  # metres south of the line's centre
    xc = (ii + 0.5) * dx
    reach_east = float(xc.max())
    reach_side = float(np.abs(yc).max())
    hn = (q / 16.0 * n / np.sqrt(s)) ** 0.6
    u0 = q / 16.0 / hn
    rows = {}
    for x in (20.0, 40.0, 80.0):
        col = int(x / dx)
        prof = h[:, col]
        y = (np.arange(prof.size) + 0.5) * dx - 0.5 * nx * dx
        tot = prof.sum()
        east = qx[:, col]
        rows[f"{x:g}"] = {
            "east_discharge_over_q": round(float(east.sum()) / q, 3),
            "east_discharge_rms_half_width_m": round(
                float(np.sqrt((np.maximum(east, 0) * y * y).sum() / max(np.maximum(east, 0).sum(), 1e-9))), 2
            ),
            "estimate_half_width_m": round(8.0 + x * 2.0 / (u0 / np.sqrt(G * hn)), 1),
            "rms_half_width_m": round(float(np.sqrt((prof * y * y).sum() / tot)) if tot > 0 else 0.0, 2),
            "wet_half_width_m": round(float(np.abs(y[prof > 0.01]).max()) if (prof > 0.01).any() else 0.0, 1),
        }
    return {
        "normal_depth_m": round(hn, 4), "speed_m_s": round(u0, 3), "froude": round(u0 / np.sqrt(G * hn), 3),
        "map_t_s": m["t_s"], "reach_east_m": reach_east, "reach_side_m": reach_side, "east_over_side": round(reach_east / reach_side, 3),
        "columns": rows, "inflow_m3": run.balance.inflow, "balance_relative": run.balance.relative,
        "volume_cells_m3": float(h.sum() * dx * dx),
        "friction_decay_length_m": round(hn / (G * n * n / hn ** (1.0 / 3.0)), 1),
    }  # fmt: skip


def main(tmp: Path, cases: list[str]) -> None:
    """``cases`` from plane, steep, jet; none runs all three. Results merge into study.json."""
    tmp.mkdir(parents=True, exist_ok=True)
    path = Path(__file__).parent / "study.json"
    out = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    cases = cases or ["plane", "steep", "jet"]
    for mom in (False, True):
        key = "on" if mom else "off"
        if "plane" in cases:
            out[f"plane_{key}"] = channel(tmp, "plane", 0.01, 20.0, 24, mom, 2400.0)
        if "steep" in cases:
            out[f"steep_{key}"] = channel(tmp, "steep", 0.03, 50.0, 12, mom, 1800.0)
        if "jet" in cases:
            out[f"jet_{key}"] = jet(tmp, mom)
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2:])
