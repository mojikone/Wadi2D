"""W85 step 4, from the saved frames: the step of a finished run with some cells taken out of the step rule.

    python s04_steps_without.py <run folder> <grid cache .h5> <out csv> [every] [pit cells .npz]

With the cells of ``s09_block2_pits.py`` as a fifth argument a further scenario, ``dt_fill_pits``, takes the faces of
every pit ``terrain.fill_pits`` would fill out of the rule.

For every saved frame (or every ``every``-th) the wave speed of every face is read as in ``s01_frame_waves.py`` and the
step it gives is taken four ways: all faces; without the faces of the pit's cells; without those and the three single
cells next in line; and all faces with ``plan_min`` at 0.05, 0.10 and 0.25 in place of 0.02. The run's own step at
that time comes from its progress file; a scenario's step is the run's step times the frame's ratio, and its steps over
the run the sum over the frames. CPU only.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import h5py
import numpy as np

from wadi2d.config.schema import Numerics
from wadi2d.io.cache import load_tables
from wadi2d.solver.model import Model
from wadi2d.solver.state import plan_field

sys.path.insert(0, str(Path(__file__).parent))
from s01_frame_waves import waves_of

PIT = (414791.0, 2722485.0, 45.0)
"""The pit's centre and the radius, m, within which a cell counts as the pit's."""
SINGLES = ((438521.0, 2739036.0, 25.0), (432961.0, 2740036.0, 25.0), (451501.0, 2721316.0, 25.0))
"""The three single cells next in line at the end of the run."""
PLAN_MINS = (0.05, 0.10, 0.25)


def near(grid, spots) -> np.ndarray:
    """Cells within the radius of any spot, and their east and south neighbours' faces with them."""
    ny, nx = grid.shape
    x, y = grid.xy_of(*np.mgrid[0:ny, 0:nx])
    out = np.zeros(grid.shape, bool)
    for sx, sy, r in spots:
        out |= np.hypot(x - sx, y - sy) <= r
    return out


def faces_of(cells: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """West faces and north faces that touch any of ``cells``."""
    return cells | np.roll(cells, 1, axis=1), cells | np.roll(cells, 1, axis=0)


def used_plan(om, d, fl, fr, axis, h_cfl) -> np.ndarray:
    """The wet share the kernel reads at each face of water at rest: the upwind cell's, or the smaller when both are wet."""
    om_l, d_l = np.roll(om, 1, axis=axis), np.roll(d, 1, axis=axis)
    from_left = (d_l - fl) >= (d - fr)
    plan = np.where(from_left, om_l, om)
    other = np.where(from_left, d, d_l)
    return np.where(other > h_cfl, np.minimum(om_l, om), plan)


def run_steps(run: Path) -> tuple[np.ndarray, np.ndarray]:
    t, dt = [], []
    for line in (run / "progress.jsonl").read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        if e["ev"] == "step":
            t.append(e["t"])
            dt.append(e["dt"])
    return np.array(t), np.array(dt)


def main() -> None:
    run, cache, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    every = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    cfg = json.loads((run / "config.resolved.json").read_text())
    num = Numerics(**cfg["numerics"])
    tables = load_tables(cache, cache.stem.removeprefix("grid_"))
    grid = tables.grid
    model = Model(tables, num, backend="cpu")
    dx = grid.dx
    pit_x, pit_y = faces_of(near(grid, (PIT,)))
    four_x, four_y = faces_of(near(grid, (PIT, *SINGLES)))
    pits_x = pits_y = None
    if len(sys.argv) > 5:
        held = np.load(sys.argv[5])
        cells = np.zeros(grid.shape, bool)
        cells[held["j"], held["i"]] = True
        pits_x, pits_y = faces_of(cells)
    flx, frx = grid.from_tiles(tables.flx), grid.from_tiles(tables.frx)
    fly, fry = grid.from_tiles(tables.fly), grid.from_tiles(tables.fry)
    t_run, dt_run = run_steps(run)
    rows = []
    with h5py.File(run / "results.h5", "r") as f:
        maps = f["maps"]
        names = sorted(maps)[::every]
        for name in names:
            t = float(maps[name].attrs["t_s"])
            d = maps[name]["depth"][()].astype(np.float64)
            h = maps[name]["mean_depth"][()].astype(np.float64)
            speed = maps[name]["speed"][()].astype(np.float64)
            b = model.backend
            om = plan_field(tables, h)
            b.set_field("h", model.host.to_state(h))
            b.set_field("d", model.host.to_state(d))
            b.set_field("om", model.host.to_state(om))
            for a in ("u", "v", "mx", "my", "qx", "qy"):
                getattr(b, a)[:] = 0.0
            wx, wy = (a.astype(np.float64) for a in waves_of(model, 1e-3))
            sx = np.maximum(
                speed, np.roll(speed, 1, axis=1)
            )  # the saved cell speed stands in for the face's |u|
            sy = np.maximum(speed, np.roll(speed, 1, axis=0))

            def step(ax, ay, sx=sx, sy=sy):
                w = max(float((ax + sx * (ax > 0)).max()), float((ay + sy * (ay > 0)).max()))
                return num.cfl * dx / max(w, num.wave_floor)

            def lead(ax, ay, sx=sx, sy=sy, d=d, om=om):
                a = np.maximum(ax + sx * (ax > 0), ay + sy * (ay > 0))
                j, i = np.unravel_index(int(np.argmax(a)), a.shape)
                x, y = grid.xy_of(j, i)
                return float(x), float(y), float(d[j, i]), float(om[j, i])

            px = used_plan(om, d, flx, frx, 1, num.h_cfl)
            py = used_plan(om, d, fly, fry, 0, num.h_cfl)
            row = {"t_s": round(t, 1), "dt_run": float(np.interp(t, t_run, dt_run)) if t_run.size else np.nan}
            row["dt_all"] = step(wx, wy)
            row["dt_no_pit"] = step(np.where(pit_x, 0.0, wx), np.where(pit_y, 0.0, wy))
            row["dt_no_four"] = step(np.where(four_x, 0.0, wx), np.where(four_y, 0.0, wy))
            if pits_x is not None:
                row["dt_fill_pits"] = step(np.where(pits_x, 0.0, wx), np.where(pits_y, 0.0, wy))
            for pm in PLAN_MINS:
                fx = np.sqrt(np.maximum(px, num.plan_min) / np.maximum(px, pm))
                fy = np.sqrt(np.maximum(py, num.plan_min) / np.maximum(py, pm))
                row[f"dt_plan_min_{pm:.2f}"] = step(wx * fx, wy * fy)
            for key, (ax, ay) in {
                "all": (wx, wy),
                "no_pit": (np.where(pit_x, 0.0, wx), np.where(pit_y, 0.0, wy)),
                "no_four": (np.where(four_x, 0.0, wx), np.where(four_y, 0.0, wy)),
            }.items():
                x, y, depth, plan = lead(ax, ay)
                row[f"{key}_x"], row[f"{key}_y"], row[f"{key}_depth"], row[f"{key}_plan"] = (
                    x,
                    y,
                    round(depth, 2),
                    round(plan, 4),
                )
            rows.append(row)
            print(
                f"t {t / 3600.0:6.2f} h  run {row['dt_run']:.4f}  frame {row['dt_all']:.4f}  no pit {row['dt_no_pit']:.4f}"
                f"  no four {row['dt_no_four']:.4f}  plan_min .05/.10/.25 "
                + " ".join(f"{row[f'dt_plan_min_{pm:.2f}']:.4f}" for pm in PLAN_MINS),
                flush=True,
            )
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    t = np.array([r["t_s"] for r in rows])
    span = np.gradient(t) if t.size > 1 else np.ones(1)
    span *= float(cfg["run"]["duration_s"]) / span.sum()
    base = np.array([r["dt_run"] for r in rows])
    frame = np.array([r["dt_all"] for r in rows])
    print(f"\nsteps of the run by its own step at the frames: {int((span / base).sum()):,}")
    more = ("dt_fill_pits",) if pits_x is not None else ()
    for key in ("dt_all", "dt_no_pit", "dt_no_four", *more, *(f"dt_plan_min_{pm:.2f}" for pm in PLAN_MINS)):
        ratio = np.array([r[key] for r in rows]) / frame
        steps = (span / np.minimum(base * ratio, num.dt_max)).sum()
        print(f"   {key:18s} steps {int(steps):>9,}  ({steps / (span / base).sum():.3f} of the run's)")


if __name__ == "__main__":
    main()
