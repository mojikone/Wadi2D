"""W85: the tables before and after the local-radius margin is capped at the bed's own extent.

    python s08_builder_margin.py save <folder>       with the builder as it was
    python s08_builder_margin.py compare <folder>    with the builder as it is
    python s08_builder_margin.py window <job.json> <old cache folder> <new cache folder>
    python s08_builder_margin.py save_quad <folder>, compare_quad <folder>      the same on a quadtree

Three beds in memory, none needing more than a few MB under either builder: `long` (320 m, the margin of 144 m fits
inside it: nothing may change), `short_flat` (40 m, flat: the local radius is the strips sum whatever the window, so
nothing may change) and `short_slope` (40 m, a V valley on a slope: the rows of the face tables whose window reaches
past the bed's own length read fewer repeats of its edge pixel). `compare` prints, per bed and array, whether it is
equal to the digit and, where a face table is not, the shallowest depth at which a row differs.
"""

from __future__ import annotations

import sys
from dataclasses import fields
from pathlib import Path

import numpy as np

from wadi2d.config.schema import Tables
from wadi2d.grid import TileGrid
from wadi2d.tables import ArrayBed, build_tables
from wadi2d.tables.builder import GridTables


def beds() -> dict[str, tuple[TileGrid, ArrayBed]]:
    out = {}
    for name, dx, k in (("long", 10.0, 10), ("short_flat", 1.25, 5), ("short_slope", 1.25, 5)):
        grid = TileGrid.from_mask(np.ones((30, 30), bool), 0.0, 0.0, dx)
        ny, nx = grid.shape
        pixel = dx / k
        y, x = np.mgrid[0 : ny * k, 0 : nx * k] * pixel
        if name == "short_flat":
            z = np.full(x.shape, 50.0)
        else:
            width = nx * dx
            z = 50.0 - 0.02 * x + 0.3 * np.abs(y - 0.5 * width) + 0.5 * np.sin(x / (0.05 * width))
        out[name] = (grid, ArrayBed(z, pixel))
    return out


def quad_beds() -> dict[str, tuple]:
    """The same three grounds on a quadtree of two cell sizes (the east half one step coarser)."""
    from wadi2d.grid.quad import QuadGrid

    out = {}
    for name, dx, k in (("quad_long", 10.0, 10), ("quad_short_flat", 0.625, 5), ("quad_short_slope", 0.625, 5)):
        mask = np.zeros((64, 128), bool)
        mask[2:-2, 2:-2] = True
        level = np.zeros((2, 4), np.int32)
        level[:, 2:] = 1
        grid = QuadGrid.from_levels(mask, 0.0, 0.0, dx, level)
        ny, nx = grid.shape
        pixel = dx / k
        y, x = np.mgrid[0 : ny * k, 0 : nx * k] * pixel
        if name.endswith("flat"):
            z = np.full(x.shape, 50.0)
        else:
            width = ny * dx
            z = 50.0 - 0.02 * x + 0.3 * np.abs(y - 0.5 * width) + 0.5 * np.sin(x / (0.05 * width))
        out[name] = (grid, ArrayBed(z, pixel))
    return out


def arrays(t: GridTables) -> dict[str, np.ndarray]:
    return {f.name: np.asarray(getattr(t, f.name)) for f in fields(GridTables) if f.name != "grid"}


def window(job: Path, old: Path, new: Path) -> None:
    """A real DEM through ``prepare_grid`` with the builder as it is, against the cache files the old builder left."""
    import h5py

    from wadi2d.config.schema import RunConfig
    from wadi2d.run import prepare_grid

    cfg = RunConfig.model_validate_json(
        job.read_text(encoding="utf-8")
    )  # its paths are as the window script wrote them
    cfg = cfg.model_copy(update={"grid": cfg.grid.model_copy(update={"cache_dir": str(new)})})
    tables, _crs = prepare_grid(cfg, new)
    now = arrays(tables)
    print(f"{job.name}: {tables.grid.shape} cells of {tables.grid.dx} m built into {new.name}")
    for path in sorted(old.glob("grid_*.h5")):
        with h5py.File(path, "r") as f:
            same = [
                key for key, a in now.items() if key in f and np.array_equal(a, f[key][()], equal_nan=True)
            ]
            mask = np.array_equal(tables.grid.mask, f["mask"][()])
        verdict = (
            "EQUAL TO THE DIGIT in all" if len(same) == len(now) and mask else f"equal in {len(same)} of"
        )
        print(
            f"   against {path.name} (old builder): {verdict} {len(now)} arrays, mask {'equal' if mask else 'differs'}"
        )


def main() -> None:
    if sys.argv[1] == "window":
        window(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
        return
    mode, folder = sys.argv[1], Path(sys.argv[2])
    folder.mkdir(parents=True, exist_ok=True)
    cfg = Tables()
    quad = mode.endswith("_quad")
    mode = mode.removesuffix("_quad")
    for name, (grid, bed) in (quad_beds() if quad else beds()).items():
        span = max(bed.z.shape)
        margin = int(np.ceil(cfg.local_radius_beta * cfg.face_depth_max / bed.pixel))
        if quad:
            from wadi2d.tables.quad import build_quad_tables

            now = arrays(build_quad_tables(grid, bed, cfg, 0.03, workers=2))
        else:
            now = arrays(build_tables(grid, bed, cfg, 0.03, workers=2))
        path = folder / f"tables_{name}.npz"
        if mode == "save":
            np.savez_compressed(path, **now)
            print(f"{name}: saved; bed {span} px at {bed.pixel} m, margin asked {margin} px")
            continue
        was = np.load(path)
        print(f"{name}: bed {span} px at {bed.pixel} m ({span * bed.pixel:.0f} m), margin asked {margin} px")
        for key, a in now.items():
            b = was[key]
            if np.array_equal(a, b, equal_nan=True):
                print(f"   {key:6s} equal to the digit")
                continue
            line = f"   {key:6s} DIFFERS at {int((a != b).sum())} of {a.size} values, largest relative {float(np.nanmax(np.abs(a - b) / np.maximum(np.abs(b), 1e-12))):.2e}"
            if key.startswith("ftab"):
                rows = a.shape[-2]
                top = now["ef" + key[-1]].astype(np.float64)[: a.shape[0]]
                differs = (a != b).any(axis=-1)  # (ntiles, TILE, TILE, rows)
                depth = (np.arange(rows) / (rows - 1)) ** 2 * top[..., None]
                line += f"; shallowest row that differs is {float(depth[differs].min()):.2f} m above its face invert"
                line += f" (the bed's length over beta is {span * bed.pixel / cfg.local_radius_beta:.2f} m)"
            print(line)


if __name__ == "__main__":
    main()
