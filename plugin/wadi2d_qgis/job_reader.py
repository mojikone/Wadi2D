# Wadi2D QGIS plugin. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A job without its model opened into the dock: a run from before the model was saved (W99), or a job the dock did not
write, as a script's or the engine's ``config.resolved.json`` (W101).

:mod:`job_states` says what the job tells, the sections restore it as they restore a saved model, and the lines and
polygons the job holds inline go into a GeoPackage beside the model, loaded as the dock's layers. Then the job the
refilled dock writes, through the HMS import where it has one, as Run writes it, is compared with the original field by
field, defaults taken out of both, and what the dock cannot hold yet is said section by section
(:mod:`job_import`).
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from .job_builder import LayerError
from .job_import import GPKG_NAME, held_words, inline_layers, not_held, strip_defaults
from .job_states import job_states
from .model_store import labelled
from .widget_state import inputs

SAME = "The job the dock writes now is the job's own, field by field."
NOT_BUILT = "the job of the refilled dock could not be built to compare it: {problem}"


def _crs_wkt(job: dict) -> str:
    from osgeo import gdal

    dem = (job.get("terrain") or {}).get("dem")
    source = gdal.Open(str(dem)) if dem and Path(dem).is_file() else None
    return source.GetProjection() if source is not None else ""


def write_inline(job: dict, folder: Path | str) -> Path | None:
    """The job's inline lines, points and polygons into a GeoPackage in ``folder``; None when it holds none. A file
    that a layer of the project holds open is not replaced: the next free name is taken."""
    from .job_layers import write_gpkg

    layers = inline_layers(job)
    if not layers:
        return None
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    stem = str((job.get("project") or {}).get("name") or "job")
    path = folder / f"{stem}_{GPKG_NAME}"
    number = 1
    while path.exists():
        try:
            path.unlink()
        except OSError:
            number += 1
            path = folder / f"{stem}_{number}_{GPKG_NAME}"
            continue
    write_gpkg(path, layers, _crs_wkt(job))
    return path


def _in_dem_crs(states: dict, job: dict) -> None:
    """Every vector file a job names is read in the DEM's CRS, as the engine reads it: a GeoJSON that names no CRS
    would otherwise land in degrees (W79's domain)."""
    from qgis.core import QgsCoordinateReferenceSystem

    wkt = _crs_wkt(job)
    crs = QgsCoordinateReferenceSystem.fromWkt(wkt) if wkt else None
    if crs is None or not crs.isValid():
        return
    definition = crs.authid() or crs.toWkt()
    for state in states.values():
        for value in (state.get("widgets") or {}).values():
            if isinstance(value, dict) and value.get("provider") == "ogr" and not value.get("crs"):
                value["crs"] = definition


def refill(links, job: dict, run_folder: Path, inline_folder: Path | str | None = None) -> list[str]:
    """Fill the dock from a job; what could not be restored, in words. ``inline_folder`` takes the GeoPackage of the
    job's inline geometry (the run folder when not given); the comparison follows when the job is built."""
    dock = links.dock
    links.reset()
    words = []
    gpkg = None
    try:
        gpkg = write_inline(job, inline_folder or run_folder)
    except (OSError, RuntimeError, ValueError) as problem:
        words.append(f"the job's lines and polygons could not be written beside the model: {problem}")
    states = job_states(job, run_folder, gpkg)
    _in_dem_crs(states, job)
    for section in dock.sections:
        state = states.get(section.key)
        if state is None:
            continue
        known = {path for path, _widget in inputs(section, section.state_skip)}
        unknown = sorted(set(state.get("widgets", {})) - known)
        if unknown:  # this module names an input the section no longer has: say so, do not pass over it
            words.append(f"{section.heading}, inputs the dock no longer has: {', '.join(unknown)}")
        words += labelled(section, section.restore(state, add_missing=True))
    words += [f"3. Hydrology, {text}" for text in (states.get("hydrology", {}).get("extra") or {}).get("hms_words", [])]
    dock.model_applied((job.get("run") or {}).get("model_type"), infer=True)
    return words


def comparable(job: dict, schema) -> dict:
    """A job as the comparison reads it: defaults out, the domain's polygon in place of its file's path."""
    out = strip_defaults(json.loads(json.dumps(job)), schema)
    domain = (out.get("grid") or {}).get("domain")
    if domain and str(domain).lower().endswith((".geojson", ".json")) and Path(domain).is_file():
        features = json.loads(Path(domain).read_text(encoding="utf-8")).get("features", [])
        out["grid"]["domain"] = [f.get("geometry", {}).get("coordinates") for f in features]
    return out


def compare(links, job: dict, done) -> None:
    """Build the job the refilled dock writes, as Run writes it (the HMS import included), and call ``done(words,
    found)``: the words, and what differs by section."""
    dock = links.dock
    scratch = Path(tempfile.mkdtemp(prefix="wadi2d_open_job_"))
    said: list[str] = []

    def failed(text: str) -> None:
        shutil.rmtree(scratch, ignore_errors=True)
        done([NOT_BUILT.format(problem=text)], None)

    def built(path: Path) -> None:
        try:
            rebuilt = json.loads(Path(path).read_text(encoding="utf-8"))
            found = not_held(comparable(job, dock.schema), comparable(rebuilt, dock.schema))
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        done(held_words(found) or [SAME], found)

    try:
        values = dock._collect()
    except LayerError as problem:
        failed(str(problem))
        return
    values["output"] = str(scratch)
    try:
        dock._prepare(values, scratch, built, failed, lambda text, _tone="info": said.append(text))
    except (KeyError, ValueError, OSError) as problem:
        failed(str(problem))
