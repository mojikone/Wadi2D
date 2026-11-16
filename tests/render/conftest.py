"""A small real run with saved maps, and what the product step makes of it: the yardstick of the drawing on demand."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np
import pytest
import rasterio

from tests.engine.conftest import X0, Y0, job, write_dem
from wadi2d.config.schema import RunConfig
from wadi2d.products import step
from wadi2d.products.frames import frame_names
from wadi2d.products.ground import face_sills, read_cells
from wadi2d.products.hazard import classify, off_the_map
from wadi2d.products.pixels import PixelMaxima, kept_cells
from wadi2d.products.step import PIXEL_DIR, Watch, make_products, pixel_box, spread
from wadi2d.run import prepare_grid, run_job

PIXEL, CELL = 2.5, 20.0
NX, NY = 48, 24
"""Cells of the job; a cell holds 8 x 8 pixels, so a drawing can take one pixel in every 2, 4 or 8."""
MAP_EVERY_S = 300.0


def ground(nx: int, ny: int, pixel: float) -> np.ndarray:
    """A wadi falling east at 2 % between banks, with ripples, so no two cells hold the same ground."""
    x = (np.arange(nx) + 0.5) * pixel
    y = (np.arange(ny) + 0.5) * pixel
    xx, yy = np.meshgrid(x, y)
    bank = np.clip(np.abs(yy - ny * pixel / 2.0 - 25.0 * np.sin(xx / 150.0)) - 40.0, 0.0, 8.0) * 0.4
    return 200.0 - 0.02 * xx + bank + 0.25 * np.sin(xx / 7.0) * np.cos(yy / 5.0)


def wadi_job(folder: Path, **outputs) -> RunConfig:
    dem = write_dem(folder / "wadi.tif", ground(int(NX * CELL / PIXEL), int(NY * CELL / PIXEL), PIXEL), PIXEL)
    return job(
        dem,
        NX,
        NY,
        CELL,
        terrain={"manning": 0.04},
        storm={"kind": "uniform", "depth_mm": 150.0, "duration_min": 30.0},
        boundaries=[{"kind": "free", "coordinates": [(X0 + NX * CELL - 10.0, Y0), (X0 + NX * CELL - 10.0, Y0 - NY * CELL)]}],
        run={"duration_s": 2400.0, "backend": "cpu", "source_every_s": 30.0},
        # the record compared with the drawing to 2e-4 m: every digit kept, not the bounded error of the default (W100)
        outputs={"map_every_s": MAP_EVERY_S, "smooth": {"enabled": False}, "pixels": {"max_error_m": 0.0}, **outputs},
    )


@dataclass
class Finished:
    cfg: RunConfig
    run: Path
    tables: object
    crs: str


@pytest.fixture(scope="session")
def finished(tmp_path_factory) -> Finished:
    """A finished run, its pixel maps of record made on the CPU."""
    folder = tmp_path_factory.mktemp("render_wadi")
    cfg = wadi_job(folder)
    summary = run_job(cfg, folder / "run")
    assert summary.exit_code == 0, summary.message
    cfg = RunConfig.model_validate_json((folder / "run" / "config.resolved.json").read_text(encoding="utf-8"))
    tables, crs = prepare_grid(cfg, folder / "run" / "cache")
    return Finished(cfg, folder / "run", tables, crs)


@dataclass
class Yardstick:
    """One frame laid over the whole domain by the product step's own object, as rasters over the kept cells' box."""

    depth: np.ndarray
    speed: np.ndarray
    hazard: np.ndarray
    extent: tuple[float, float, float, float]
    pixel: float

    def window(self, extent: tuple[float, float, float, float]) -> tuple[slice, slice]:
        """Rows and columns of an extent that lies on whole pixels inside the box."""
        col0 = round((extent[0] - self.extent[0]) / self.pixel)
        col1 = round((extent[2] - self.extent[0]) / self.pixel)
        row0 = round((self.extent[3] - extent[3]) / self.pixel)
        row1 = round((self.extent[3] - extent[1]) / self.pixel)
        return slice(row0, row1), slice(col0, col1)


def whole_domain(found: Finished, frame: int, xp=np) -> Yardstick:
    """What ``pixel_maxima`` holds after one saved map, without the run's own peaks."""
    cfg, tables = found.cfg, found.tables
    rule = cfg.outputs.pixels
    results = found.run / "results.h5"
    with h5py.File(results, "r") as f:
        keep = kept_cells(f["maxima"]["mean_depth"][:], rule)  # the cells the rule keeps (W100: every one ever wet)
        group = f["maps"][frame_names(results)[frame]]
        fields = [group[name][:] for name in ("depth", "mean_depth", "speed")]
    cells = read_cells(cfg, tables, keep)
    zmin = (tables.zmin - cells.datum).astype(np.float32)
    maxima = PixelMaxima(xp, cells, zmin, *face_sills(tables, cells.datum), keep, rule)
    maxima.add(*fields)
    depth, speed, dv = maxima.result()
    classes = classify(depth, speed, dv, rule)
    box = pixel_box(cells)
    grid = tables.grid
    west, north = grid.x0 + box[1] * cells.pixel, grid.y0 - box[0] * cells.pixel
    extent = (west, north - box[2] * cells.pixel, west + box[3] * cells.pixel, north)
    wet = classes > 0
    return Yardstick(
        spread(cells, np.where(wet, depth, np.nan), np.nan, np.float32, box),
        spread(cells, np.where(wet, speed, np.nan), np.nan, np.float32, box),
        spread(cells, off_the_map(classes, depth, rule), 0, np.uint8, box),  # the hazard map leaves thin water out
        extent,
        cells.pixel,
    )


@pytest.fixture(scope="session")
def peak_from_a_frame(finished: Finished, tmp_path_factory) -> tuple[Path, int]:
    """A copy of the run whose own peaks are one of its saved maps, with the rasters of record made from it.

    In it the record's peak comes from a saved frame at every pixel, so the highest of the frames drawn must be the
    record. Returns the folder and the frame that was made the peak."""
    folder = tmp_path_factory.mktemp("render_peak")
    shutil.copy(finished.run / "results.h5", folder / "results.h5")
    config = json.loads((finished.run / "config.resolved.json").read_text(encoding="utf-8"))
    config["grid"]["cache_dir"] = str(finished.run / "cache")
    (folder / "config.resolved.json").write_text(json.dumps(config), encoding="utf-8")
    with h5py.File(folder / "results.h5", "r+") as f:
        names = sorted(f["maps"])
        volume = [float(f["maps"][name]["mean_depth"][:].sum()) for name in names]
        peak = int(np.argmax(volume))
        group = f["maps"][names[peak]]
        for name in ("depth", "mean_depth", "speed"):
            f["maxima"][name][...] = group[name][:]
        f["maxima"]["hazard"][...] = group["depth"][:] * group["speed"][:]
    cfg = RunConfig.model_validate(config)
    quiet = Watch(lambda *_a, **_k: None, lambda: False)
    make_products(cfg, finished.tables, finished.crs, folder, quiet, "cpu")
    return folder, peak


def read_record(folder: Path, name: str) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """A raster of record, NaN where it holds nothing, and its extent."""
    with rasterio.open(folder / PIXEL_DIR / name) as src:
        band = src.read(1).astype(np.float32)
        bounds = src.bounds
    band[band == step.NO_DEPTH] = np.nan
    return band, (bounds.left, bounds.bottom, bounds.right, bounds.top)
