"""The depth-area study: one run per storm area, each design point reading its own drainage area.

Design note section 7. Rain follows the job's ARF table at each storm area; a design line reads ln Q against
ln A between the two runs that bracket its drainage area, and the composite map does the same per cell from an
accumulation raster, so a map is consistent with the design flows at every point. The grid is built once and
shared; the runs are independent jobs, which is what a later job runner distributes. The table's type goes on
every output, because a storm-centred ratio is not a fixed-area curve.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import rasterio

from wadi2d.config.constants import M2_PER_KM2
from wadi2d.config.schema import RunConfig
from wadi2d.forcing import build_storm
from wadi2d.grid.tiles import TileGrid
from wadi2d.io.geotiff import NODATA, write_map
from wadi2d.io.progress import Progress
from wadi2d.run import (
    EXIT_DONE,
    EXIT_INVALID,
    EXIT_STOPPED,
    InvalidJob,
    JobError,
    RunSummary,
    check_inputs,
    prepare_grid,
    run_job,
)

COMPOSITE_MAPS = ("max_depth", "max_speed", "hazard")
UNLISTED_TYPE = "unspecified"


@dataclass
class StudySummary:
    exit_code: int = EXIT_DONE
    message: str = ""
    areas_km2: list[float] = field(default_factory=list)
    runs: list[RunSummary] = field(default_factory=list)
    table: list[dict[str, object]] = field(default_factory=list)
    composite: dict[str, Path] = field(default_factory=dict)


def table_type(cfg: RunConfig) -> str:
    return cfg.storm.arf.table_type if cfg.storm.arf is not None else UNLISTED_TYPE


def storm_areas(cfg: RunConfig) -> list[float]:
    """The explicit areas, or log-spaced ones, with the design points' own areas when asked."""
    a = cfg.arf
    base = list(a.areas_km2) or list(np.geomspace(a.area_min_km2, a.area_max_km2, a.n_areas))
    if a.exact_points:
        base += [p.drainage_area_km2 for p in cfg.outputs.lines if p.drainage_area_km2 is not None]
    return sorted({round(float(x), 4) for x in base})


def run_name(area: float) -> str:
    return f"A{area:010.3f}km2".replace(".", "p")


def interpolate_peak(areas: np.ndarray, peaks: np.ndarray, area: float) -> float:
    """ln Q linear in ln A; the end values hold outside the runs, and a dry run reads as zero."""
    usable = peaks > 0.0
    if not usable.any():
        return 0.0
    return float(np.exp(np.interp(np.log(area), np.log(areas[usable]), np.log(peaks[usable]))))


def design_table(cfg: RunConfig, areas: list[float], runs: list[RunSummary]) -> list[dict[str, object]]:
    """One row per design line with a drainage area."""
    grid_a = np.asarray(areas)
    kind = table_type(cfg)
    rows: list[dict[str, object]] = []
    for line in cfg.outputs.lines:
        if line.drainage_area_km2 is None:
            continue
        peaks = np.array([r.peaks.get(line.name, (0.0, 0.0))[0] for r in runs])
        times = np.array([r.peaks.get(line.name, (0.0, 0.0))[1] for r in runs])
        area = line.drainage_area_km2
        high = int(np.clip(np.searchsorted(grid_a, area), 0, grid_a.size - 1))
        low = max(high - 1, 0)
        nearest = low if abs(np.log(area / grid_a[low])) <= abs(np.log(area / grid_a[high])) else high
        rows.append(
            {
                "design_point": line.name,
                "drainage_area_km2": area,
                "storm_area_low_km2": float(grid_a[low]),
                "storm_area_high_km2": float(grid_a[high]),
                "peak_low_m3s": float(peaks[low]),
                "peak_high_m3s": float(peaks[high]),
                "design_peak_m3s": interpolate_peak(grid_a, peaks, area),
                "time_of_peak_s": float(times[nearest]),
                "arf_table_type": kind,
            }
        )
    return rows


def write_table(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        if not rows:
            f.write("design_point\n")
            return
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def accumulation_on_grid(path: str, units: str, grid: TileGrid) -> np.ndarray:
    """Drainage area per grid cell, km2: the largest value among the raster pixels inside the cell."""
    ny, nx = grid.shape
    out = np.zeros((ny, nx))
    with rasterio.open(path) as src:
        res = abs(src.transform.a)
        inv = ~src.transform
        c0 = max(int(np.floor(inv.a * grid.x0 + inv.c)), 0)
        r0 = max(int(np.floor(inv.e * grid.y0 + inv.f)), 0)
        c1 = min(int(np.ceil(inv.a * (grid.x0 + nx * grid.dx) + inv.c)), src.width)
        r1 = min(int(np.ceil(inv.e * (grid.y0 - ny * grid.dx) + inv.f)), src.height)
        window = rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)
        a = src.read(1, window=window, masked=True).filled(0.0).astype(np.float64)
        x = src.transform.c + (np.arange(c0, c1) + 0.5) * res
        y = src.transform.f - (np.arange(r0, r1) + 0.5) * res
    scale = res * res / M2_PER_KM2 if units == "cells" else 1.0
    jj = np.floor((grid.y0 - y) / grid.dx).astype(np.int64)
    ii = np.floor((x - grid.x0) / grid.dx).astype(np.int64)
    rkeep = (jj >= 0) & (jj < ny)
    ckeep = (ii >= 0) & (ii < nx)
    jg, ig = np.meshgrid(jj[rkeep], ii[ckeep], indexing="ij")
    np.maximum.at(out, (jg.ravel(), ig.ravel()), a[np.ix_(rkeep, ckeep)].ravel())
    return out * scale


def composite_map(maps: list[np.ndarray], areas: np.ndarray, cell_area: np.ndarray) -> np.ndarray:
    """Per cell, the runs that bracket its drainage area, linear in ln A; outside them, the end run."""
    if areas.size == 1:
        return np.array(maps[0], dtype=np.float64)
    ln_a = np.log(areas)
    ln_c = np.log(np.clip(cell_area, areas[0], areas[-1]))
    high = np.clip(np.searchsorted(ln_a, ln_c), 1, ln_a.size - 1)
    low = high - 1
    w = (ln_c - ln_a[low]) / (ln_a[high] - ln_a[low])
    stack = np.stack(maps)
    rows, cols = np.indices(cell_area.shape, sparse=True)
    return (1.0 - w) * stack[low, rows, cols] + w * stack[high, rows, cols]


def composite_maps(
    cfg: RunConfig, tables, crs: str, out: Path, areas: list[float], folders: list[Path]
) -> dict[str, Path]:
    """One composite per quantity, tagged with the ARF table's type."""
    grid = tables.grid
    cell_area = accumulation_on_grid(cfg.arf.accumulation, cfg.arf.accumulation_units, grid)
    result: dict[str, Path] = {}
    for name in COMPOSITE_MAPS:
        maps = []
        for folder in folders:
            with rasterio.open(folder / "maps" / f"{name}.tif") as src:
                band = src.read(1)
                maps.append(np.where(band == NODATA, 0.0, band))
        data = composite_map(maps, np.asarray(areas), cell_area)
        tags = {"arf_table_type": table_type(cfg), "method": "depth-area analysis"}
        result[name] = write_map(out / "composite" / f"{name}.tif", data, grid, crs, tags=tags)
    return result


def check_study(cfg: RunConfig, areas: list[float]) -> None:
    """A study needs rain and a table that tells its runs apart: identical runs under exit 0 would mean nothing."""
    if cfg.storm.kind == "none":
        raise InvalidJob("a depth-area study needs a storm")
    if cfg.storm.arf is None:
        raise InvalidJob("a depth-area study needs storm.arf: without a table every run is the same run")
    storm = build_storm(cfg)
    depths = {round(storm.at_area(area).total_depth, 9) for area in areas}
    if len(areas) > 1 and len(depths) == 1:
        raise InvalidJob(
            f"storm.arf gives one factor at all the storm areas {areas}: the runs would be identical"
        )


def _stopped(summary: StudySummary, progress: Progress, stop: Path) -> None:
    summary.exit_code = EXIT_STOPPED
    stop.unlink(missing_ok=True)
    progress.emit("done", status="stopped", code=EXIT_STOPPED, partial=True, runs=len(summary.runs))


def _study(cfg, folder: Path, backend, progress: Progress, summary: StudySummary) -> None:
    check_inputs(cfg)
    summary.areas_km2 = storm_areas(cfg)
    check_study(cfg, summary.areas_km2)
    stop = folder / "stop"
    cache = Path(cfg.grid.cache_dir) if cfg.grid.cache_dir else folder / "cache"
    tables, crs = prepare_grid(cfg, cache, progress)
    kind = table_type(cfg)
    progress.emit("start", areas_km2=summary.areas_km2, arf_table_type=kind)
    folders = []
    for area in summary.areas_km2:
        if stop.exists():
            _stopped(summary, progress, stop)
            return
        storm = cfg.storm.model_copy(update={"storm_area_km2": area})
        one = cfg.model_copy(update={"storm": storm})
        run_dir = folder / "runs" / run_name(area)
        folders.append(run_dir)
        result = run_job(one, run_dir, backend, tables=(tables, crs), stop_files=(stop,))
        summary.runs.append(result)
        progress.emit("output", kind="run", area_km2=area, code=result.exit_code, peaks=result.peaks)
        if result.exit_code == EXIT_STOPPED:
            _stopped(summary, progress, stop)
            return
        if result.exit_code != EXIT_DONE:
            summary.exit_code = result.exit_code
            summary.message = result.message
            progress.emit("error", code=result.exit_code, message=result.message, area_km2=area)
            return
    summary.table = design_table(cfg, summary.areas_km2, summary.runs)
    write_table(folder / "design_points.csv", summary.table)
    if cfg.arf.accumulation is not None:
        summary.composite = composite_maps(cfg, tables, crs, folder, summary.areas_km2, folders)
    (folder / "study.json").write_text(
        json.dumps(
            {"areas_km2": summary.areas_km2, "arf_table_type": kind, "table": summary.table}, indent=2
        ),
        encoding="utf-8",
    )
    progress.emit("done", status="finished", code=EXIT_DONE, rows=len(summary.table))


def arf_study(
    cfg: RunConfig, out: str | Path, backend: str | None = None, echo: bool = False
) -> StudySummary:
    """Run the study into ``out``: ``runs/<area>/`` per storm area, ``design_points.csv``, ``composite/``.

    ``out/stop`` stops it, and each run's own folder still stops that run. A stopped or failed study writes no table.
    """
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    summary = StudySummary()
    with Progress(folder / "progress.jsonl", echo=echo) as progress:
        try:
            _study(cfg, folder, backend, progress, summary)
        except JobError as error:
            summary.exit_code, summary.message = error.code, str(error)
            progress.emit("error", code=error.code, message=str(error))
        except ValueError as error:
            summary.exit_code, summary.message = EXIT_INVALID, str(error)
            progress.emit("error", code=EXIT_INVALID, message=str(error))
    return summary
