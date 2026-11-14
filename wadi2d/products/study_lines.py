"""Lines read after a depth-area study, consistent with its area reduction (W53, his order of 2026-11-13).

A line drawn or picked after a study takes its own drainage area: a design line's own when the line is one, else the
largest drainage area of the model cells it crosses on the study's flow-accumulation raster (``arf.accumulation``).
Every series is read from the two storm-area runs that bracket that area and blended with the weights the study's own
maps use (:func:`wadi2d.arf.log_area_weights`, linear in ln A); the peak is the study's design-point reading of the two
runs' peaks (:func:`wadi2d.arf.interpolate_peak`). Outside the runs the end run holds, and the answer says so. A study
with no accumulation raster gives a line with no area of its own one run, the smallest storm area, named as such.

Both runs are read in one request, one process: a line costs two readings of :func:`read_line`, not two engines.
"""

from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import rasterio
from rasterio.windows import Window

from wadi2d.arf import interpolate_peak, log_area_weights, run_name
from wadi2d.config.constants import M2_PER_KM2
from wadi2d.config.schema import RunConfig
from wadi2d.products.result_lines import (
    DIGITS_FLOW,
    DIGITS_LEVEL,
    SAMPLES_PER_CELL,
    _rounded,
    catalogue,
    read_line,
    sample_line,
)

STUDY_FILE = "study.json"
RUNS_DIR = "runs"
FROM_DESIGN_LINE, FROM_ACCUMULATION = "design line", "flow accumulation"
SAME_POINT_M = 1e-6
"""Two lines are the same line when every vertex agrees to this."""
FRAME_SLACK = 0.1
"""Of the map interval: a frame lands on the first step past its time, so two runs' frames stand seconds apart and are
blended as the same frame; the answer gives the largest offset, at the smaller run's times."""
MOST_RASTER_SAMPLES = 20000
"""Points along a line read on the accumulation raster: half a pixel apart up to 10 km of 1 m pixels."""


def is_study(folder: Path) -> bool:
    return (Path(folder) / STUDY_FILE).is_file()


def study_runs(folder: Path) -> tuple[np.ndarray, list[Path]]:
    """The study's storm areas, rising, and the folder of each run."""
    saved = json.loads((Path(folder) / STUDY_FILE).read_text(encoding="utf-8"))
    areas = sorted(float(a) for a in saved["areas_km2"])
    runs = [Path(folder) / RUNS_DIR / run_name(a) for a in areas]
    missing = [run.name for run in runs if not (run / "results.h5").is_file()]
    if missing:
        raise ValueError(f"The study's runs {missing} are not in {Path(folder) / RUNS_DIR}.")
    return np.asarray(areas), runs


def _config(run: Path) -> RunConfig:
    return RunConfig.model_validate_json((run / "config.resolved.json").read_text(encoding="utf-8"))


def _same_line(a: list, b: list) -> bool:
    return len(a) == len(b) and all(abs(p[0] - q[0]) <= SAME_POINT_M and abs(p[1] - q[1]) <= SAME_POINT_M for p, q in zip(a, b, strict=True))


def line_drainage_area(run: Path, coordinates: list) -> tuple[float | None, str | None]:
    """The line's drainage area, km2, and where it came from: a design line's own, the accumulation raster's largest
    over the cells the line crosses, or (None, None) when the study has neither."""
    cfg = _config(run)
    for line in cfg.outputs.lines:
        if line.drainage_area_km2 is not None and _same_line([list(p) for p in line.coordinates], coordinates):
            return float(line.drainage_area_km2), FROM_DESIGN_LINE
    if not cfg.arf.accumulation or not Path(cfg.arf.accumulation).is_file():
        return None, None
    with h5py.File(run / "results.h5", "r") as f:
        mask = f["mask"][:]
        x0, y0, dx = (float(f.attrs[key]) for key in ("x0", "y0", "dx"))
    with rasterio.open(cfg.arf.accumulation) as src:
        res = abs(src.transform.a)
        samples = sample_line(coordinates, min(dx / SAMPLES_PER_CELL, res / 2.0), MOST_RASTER_SAMPLES)
        rows = np.floor((y0 - samples.y) / dx).astype(np.int64)
        columns = np.floor((samples.x - x0) / dx).astype(np.int64)
        inside = (rows >= 0) & (rows < mask.shape[0]) & (columns >= 0) & (columns < mask.shape[1])
        inside[inside] = mask[rows[inside], columns[inside]]
        if not inside.any():
            raise ValueError("This line does not cross the model.")
        inv = ~src.transform
        pixel_columns = np.floor(inv.a * samples.x[inside] + inv.b * samples.y[inside] + inv.c).astype(np.int64)
        pixel_rows = np.floor(inv.d * samples.x[inside] + inv.e * samples.y[inside] + inv.f).astype(np.int64)
        on = (pixel_rows >= 0) & (pixel_rows < src.height) & (pixel_columns >= 0) & (pixel_columns < src.width)
        if not on.any():
            return None, None
        r0, r1 = int(pixel_rows[on].min()), int(pixel_rows[on].max()) + 1
        c0, c1 = int(pixel_columns[on].min()), int(pixel_columns[on].max()) + 1
        block = src.read(1, window=Window(c0, r0, c1 - c0, r1 - r0), masked=True).filled(0.0).astype(np.float64)
    scale = res * res / M2_PER_KM2 if cfg.arf.accumulation_units == "cells" else 1.0
    area = float(block[pixel_rows[on] - r0, pixel_columns[on] - c0].max()) * scale
    return (area, FROM_ACCUMULATION) if area > 0.0 else (None, None)


def _depths(read: dict) -> np.ndarray:
    """Water depth along the line per frame, 0 where dry."""
    ground = np.array([np.nan if v is None else v for v in read["ground_m"]], np.float64)
    levels = np.array([[np.nan if v is None else v for v in frame] for frame in read["level_m"]], np.float64)
    return np.nan_to_num(np.maximum(levels - ground, 0.0))


def _speeds(read: dict) -> np.ndarray:
    return np.nan_to_num(np.array([[np.nan if v is None else v for v in frame] for frame in read["speed_m_s"]], np.float64))


def blend_reads(low: dict, high: dict, w: float) -> dict:
    """Two readings of one line, ``(1 - w) * low + w * high`` at every frame and station. Depth and speed are blended
    with dry as zero, and the level is the ground plus the blended depth, so a cell wet in one run only is half wet."""
    same_frames = len(low["t_s"]) == len(high["t_s"]) and all(
        abs(a - b) <= FRAME_SLACK * low["interval_s"] for a, b in zip(low["t_s"], high["t_s"], strict=True)
    )
    if not same_frames or low["station_m"] != high["station_m"]:
        raise ValueError("The two runs saved different frames or read the line differently: they cannot be blended.")
    out = dict(low)
    out["frame_offset_s"] = max((abs(a - b) for a, b in zip(low["t_s"], high["t_s"], strict=True)), default=0.0)
    out["flow_m3s"] = [round((1.0 - w) * a + w * b, DIGITS_FLOW) for a, b in zip(low["flow_m3s"], high["flow_m3s"], strict=True)]
    depth = (1.0 - w) * _depths(low) + w * _depths(high)
    ground = np.array([np.nan if v is None else v for v in low["ground_m"]], np.float64)
    out["deepest_m"] = [round(float(d.max()), DIGITS_LEVEL) if d.size else 0.0 for d in depth]
    out["level_m"] = [_rounded(np.where(d > 0.0, ground + d, np.nan), DIGITS_LEVEL) for d in depth]
    speed = (1.0 - w) * _speeds(low) + w * _speeds(high)
    out["speed_m_s"] = [_rounded(np.where(d > 0.0, s, np.nan), DIGITS_LEVEL) for d, s in zip(depth, speed, strict=True)]
    return out


def _peak(read: dict) -> float:
    return max((abs(q) for q in read["flow_m3s"]), default=0.0)


def _words(area: float | None, source: str | None, low: float, high: float, w: float, clamp: str | None) -> str:
    if area is None:
        return (
            f"The study has no flow accumulation raster and this is no design line, so the line has no drainage area of "
            f"its own: read from the run at the storm area of {low:g} km2 alone, the smallest of the study."
        )
    where = "its design line's" if source == FROM_DESIGN_LINE else "flow accumulation, the largest where it crosses"
    said = f"The line drains {area:.4g} km2 ({where}). "
    if clamp == "below":
        return said + f"That is below the smallest storm area of the study: read from the run at {low:g} km2 alone."
    if clamp == "above":
        return said + f"That is above the largest storm area of the study: read from the run at {high:g} km2 alone."
    if low == high:
        return said + f"Read from the run at that storm area, {low:g} km2."
    return said + f"Read from the runs at {low:g} km2, weight {1.0 - w:.3f}, and {high:g} km2, weight {w:.3f}, linear in log area."


def read_study_line(folder: Path, coordinates: list, name: str = "") -> dict:
    """A line after a study: its area, the two runs either side, every series blended; see the module's note."""
    areas, runs = study_runs(folder)
    area, source = line_drainage_area(runs[0], coordinates)
    low = high = 0
    w = 0.0
    clamp = None
    if area is not None:
        clamp = "below" if area < areas[0] else ("above" if area > areas[-1] else None)
        if areas.size > 1:
            found_low, found_high, found_w = log_area_weights(areas, area)
            low, high, w = int(found_low), int(found_high), float(found_w)
            if w <= 0.0:  # on a run, or below the smallest: that run alone
                high, w = low, 0.0
            elif w >= 1.0:  # on a run, or above the largest
                low, w = high, 0.0
    first = read_line(runs[low], coordinates, name)
    if high == low:
        found, design = first, _peak(first)
    else:
        second = read_line(runs[high], coordinates, name)
        found = blend_reads(first, second, w)
        design = interpolate_peak(areas[[low, high]], np.array([_peak(first), _peak(second)]), area)
    found["study"] = {
        "drainage_area_km2": area,
        "area_source": source,
        "low_km2": float(areas[low]),
        "high_km2": float(areas[high]),
        "weight_low": round(1.0 - w, 6) if high != low else 1.0,
        "weight_high": round(w, 6) if high != low else 0.0,
        "clamped": clamp,
        "design_peak_m3s": round(float(design), DIGITS_FLOW),
        "words": _words(area, source, float(areas[low]), float(areas[high]), w, clamp),
    }
    return found


def study_catalogue(folder: Path) -> dict:
    """What the plugin lists for a study: the frames and the design lines of its runs, to be read through the study.
    The runs' own recorded series are each one storm area's, so none is offered as the line's record."""
    areas, runs = study_runs(folder)
    listing = catalogue(runs[0])
    for line in listing["lines"]:
        for key in list(line):
            if key not in ("name", "coordinates"):
                del line[key]
    cfg = _config(runs[0])
    has_raster = bool(cfg.arf.accumulation) and Path(cfg.arf.accumulation).is_file()
    listing.update(points=[], lumped=[], study={"areas_km2": areas.tolist(), "accumulation": has_raster})
    return listing
