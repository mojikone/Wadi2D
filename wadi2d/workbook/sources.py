"""Where the dam workbook's hydrographs come from: finished Wadi2D runs, or HEC-HMS depth-area DSS files.

Interface: :func:`parse_element`, :func:`from_runs`, :func:`from_hms_dss`.

A run gives an element by the first series it wrote of that name: ``series/network_<name>.csv`` (a lumped element:
inflow and outflow), ``design_<name>.csv`` (a design line, grid plus lumped water) or ``line_<name>.csv`` (a result
line, the size of its discharge). A network element routes when its outflow differs from its inflow; pool level and
storage are taken when the run wrote them (a column starting ``pool``, ``stage`` or ``elevation``, and one starting
``storage``: W59 writes ``pool_m`` and ``storage_m3``), and so is each structure's flow (W59's ``<kind>_<n>_m3s`` and
``evaporation_m3s``, W74); a run that wrote none of them leaves those columns out.

HMS gives an element at its own analysis point (the F part ends ``>name``): FLOW at a junction or any other element;
at a reservoir FLOW-COMBINE is the inflow, FLOW the outflow, ELEVATION the pool and STORAGE the storage.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import numpy as np

from wadi2d.workbook.model import Dam, Hydrograph

SECONDS_PER_HOUR = 3600.0
ROUTE_TOLERANCE = 1e-6
"""Outflow within this share of the peak inflow everywhere is the inflow passed on: no routing."""
STORAGE_TO_MM3 = {"m3": 1e-6, "1000m3": 1e-3, "thoum3": 1e-3, "mm3": 1.0, "mcm": 1.0}
FLOW_SUFFIX = "_m3s"
STRUCTURE_COLUMN = re.compile(r"^(?:[a-z][a-z_]*_\d+|evaporation)_m3s$")
"""W59's column of one structure's flow, ``<kind>_<n>_m3s``, or ``evaporation_m3s``; never inflow, outflow, branched."""


def parse_element(text: str) -> tuple[str, str]:
    """``R5A=R5`` -> (model name, sheet name); ``Bidah 03`` -> both the same."""
    name, _, label = text.partition("=")
    name, label = name.strip(), label.strip()
    return name, (label or name)


def _read_csv(path: Path) -> dict[str, np.ndarray]:
    with path.open(encoding="utf-8") as f:
        rows = list(csv.reader(f))
    data = np.array(rows[1:], dtype=np.float64).reshape(len(rows) - 1, len(rows[0]))
    return {name: data[:, k] for k, name in enumerate(rows[0])}


def _storage_factor(column: str) -> float:
    unit = column.lower().split("_", 1)[-1].replace(" ", "") if "_" in column else "m3"
    return STORAGE_TO_MM3.get(unit, 1e-6)


def _routes(inflow: np.ndarray, outflow: np.ndarray) -> bool:
    peak = float(np.max(np.abs(inflow))) if len(inflow) else 0.0
    return peak > 0.0 and float(np.max(np.abs(outflow - inflow))) > ROUTE_TOLERANCE * peak


def structure_columns(cols: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """W59's per-structure flows (``orifice_1_m3s``, ``rating_spillway_1_m3s``, ``gate_2_m3s`` ...) and the
    evaporation, by the column's stem, in the run's order."""
    return {k[: -len(FLOW_SUFFIX)]: v for k, v in cols.items() if STRUCTURE_COLUMN.match(k)}


def from_network_columns(cols: dict[str, np.ndarray]) -> Hydrograph:
    t_h = cols["t_s"] / SECONDS_PER_HOUR
    inflow, outflow = cols.get("inflow_m3s"), cols.get("outflow_m3s")
    if inflow is None or not np.any(inflow):
        return Hydrograph(t_h, outflow if outflow is not None else np.zeros_like(t_h))
    pool = next((v for k, v in cols.items() if k.lower().startswith(("pool", "stage", "elevation"))), None)
    storage_key = next((k for k in cols if k.lower().startswith("storage")), None)
    storage = None if storage_key is None else cols[storage_key] * _storage_factor(storage_key)
    structures = structure_columns(cols)
    if outflow is None or not (_routes(inflow, outflow) or pool is not None or storage is not None or structures):
        return Hydrograph(t_h, inflow)
    return Hydrograph(t_h, inflow, outflow, pool, storage, structures)


def run_series(run: Path, name: str) -> tuple[Hydrograph, str]:
    from wadi2d.io.results import safe_name

    folder, safe = run / "series", safe_name(name)
    network = folder / f"network_{safe}.csv"
    if network.is_file():
        return from_network_columns(_read_csv(network)), "Wadi2D network element"
    design = folder / f"design_{safe}.csv"
    if design.is_file():
        cols = _read_csv(design)
        return Hydrograph(cols["t_s"] / SECONDS_PER_HOUR, np.abs(cols["total_m3s"])), "Wadi2D design line"
    line = folder / f"line_{safe}.csv"
    if line.is_file():
        cols = _read_csv(line)
        return Hydrograph(cols["t_s"] / SECONDS_PER_HOUR, np.abs(cols["discharge_m3s"])), "Wadi2D result line"
    raise ValueError(f"run {run}: no network, design or line series named {name!r}")


def _step_s(t_h: np.ndarray) -> int:
    step = np.diff(t_h) * SECONDS_PER_HOUR
    if not len(step):
        raise ValueError("a series of one value has no step")
    return round(float(np.median(step)))


def from_runs(
    runs: dict[str, Path],
    elements: list[tuple[str, str]],
    areas: dict[str, float] | None = None,
    notes: list[str] | None = None,
) -> tuple[list[Dam], int]:
    """(dams, step in s) from one finished run, or one depth-area study folder (W74), per return period. ``areas``
    gives catchments in km2 by name; in a study they are also the area an element is read at. How each element of a
    study was read is appended to ``notes``, once per distinct reading."""
    from wadi2d.workbook.study import is_study, study_element

    areas = areas or {}
    dams, steps = [], set()
    for name, label in elements:
        dam = Dam(name, label, "", areas.get(name))
        for rp, run in runs.items():
            if is_study(run):
                hydrograph, kind, area, words = study_element(Path(run), name, areas.get(name))
                if dam.catchment_km2 is None:
                    dam.catchment_km2 = round(area, 2)
                if notes is not None and words not in notes:
                    notes.append(words)
            else:
                hydrograph, kind = run_series(Path(run), name)
            dam.series[rp], dam.element_kind = hydrograph, kind
            steps.add(_step_s(hydrograph.t_h))
        dams.append(dam)
    if len(steps) != 1:
        raise ValueError(f"the runs write their series on different steps: {sorted(steps)} s")
    return dams, steps.pop()


def _upstream_area_km2(basin, name: str) -> float:
    """Subbasin area draining through ``name``, itself included when it is a subbasin."""
    links = basin.connectivity()
    subbasins = basin.subbasins
    seen, todo, total = set(), [name], 0.0
    while todo:
        here = todo.pop()
        if here in seen:
            continue
        seen.add(here)
        if here in subbasins:
            total += float(subbasins[here].area or 0.0)
        todo.extend(links.upstream.get(here, []))
    return total


def _own(catalog, name: str) -> dict[str, object]:
    return {p.c: p for p in catalog if p.b == name and p.f.split(">")[-1] == name and ">" in p.f}


def _read(file, p) -> tuple[np.ndarray, np.ndarray, str]:
    """(hours from the first value, values, units) of one DSS record."""
    ts = file.read_timeseries(p.b, p.c, p.f, e=p.e)
    t = (ts.times - ts.times[0]).astype("timedelta64[s]").astype(float) / SECONDS_PER_HOUR
    return t, ts.values, ts.units


def from_hms_dss(
    dss: dict[str, Path], elements: list[tuple[str, str]], basin_file: Path | None = None
) -> tuple[list[Dam], int]:
    """(dams, step in s) from one HMS depth-area (or simulation) DSS file per return period."""
    from wadi2d.hms import basin as hms_basin
    from wadi2d.hms.dss import open_dss

    basin = hms_basin.load(basin_file) if basin_file is not None else None
    reservoirs = set(basin.reservoirs) if basin is not None else set()
    dams = []
    for name, label in elements:
        area = round(_upstream_area_km2(basin, name), 2) if basin is not None else None
        kind = (
            "HMS reservoir"
            if name in reservoirs
            else "HMS junction"
            if basin is None or name in basin.junctions
            else "HMS element"
        )
        dams.append(Dam(name, label, kind, area))
    steps = set()
    for rp, path in dss.items():
        with open_dss(path) as file:
            catalog = file.catalog()
            for dam in dams:
                own = _own(catalog, dam.name)
                if "FLOW" not in own:
                    raise ValueError(f"{path}: no FLOW at the own analysis point of {dam.name!r}")
                t_h, flow, _ = _read(file, own["FLOW"])
                steps.add(_step_s(t_h))
                if dam.name in reservoirs and "FLOW-COMBINE" in own:
                    inflow = _read(file, own["FLOW-COMBINE"])[1]
                    pool = _read(file, own["ELEVATION"])[1] if "ELEVATION" in own else None
                    storage = None
                    if "STORAGE" in own:
                        _, values, unit = _read(file, own["STORAGE"])
                        storage = values * STORAGE_TO_MM3.get(unit.lower().replace(" ", ""), 1e-6)
                    dam.series[rp] = Hydrograph(t_h, inflow, flow, pool, storage)
                else:
                    dam.series[rp] = Hydrograph(t_h, flow)
    if len(steps) != 1:
        raise ValueError(f"the DSS files hold different steps: {sorted(steps)} s")
    return dams, steps.pop()
