"""The dam-site Excel workbook: inflow (and, where a reservoir routes, outflow, pool and storage) at named dams or
picked elements over a set of return periods, in the layout he approved on 2026-11-14 (W58 section 7, W60).

Interface: :func:`make` (sources to a saved workbook, what ``wadi2d workbook`` calls), :mod:`.model`,
:mod:`.sources`, :mod:`.layout`.
"""

from __future__ import annotations

from pathlib import Path

from wadi2d.workbook.model import WorkbookInput, rp_sort_key

DEFAULT_TARGET = "200yr"


def make(
    out: str | Path,
    elements: list[tuple[str, str]],
    *,
    runs: dict[str, Path] | None = None,
    dss: dict[str, Path] | None = None,
    basin_file: Path | None = None,
    areas: dict[str, float] | None = None,
    target: str = DEFAULT_TARGET,
    project: str = "",
    method: str = "",
    tile_charts: bool = True,
) -> Path:
    """Read the series from runs or HMS DSS files (one per return period, keyed ``200yr``, ``PMP`` ...) and write."""
    from wadi2d.workbook import layout, sources

    if bool(runs) == bool(dss):
        raise ValueError("give either runs or DSS files, one per return period")
    if runs:
        dams, dt = sources.from_runs(runs, elements, areas)
        listed = "; ".join(f"{rp} = {Path(p).name}" for rp, p in runs.items())
        source, short = f"Wadi2D runs, one per return period: {listed}.", "Wadi2D"
    else:
        dams, dt = sources.from_hms_dss(dss, elements, basin_file)
        listed = ", ".join(Path(p).name for p in dss.values())
        where = f"; catchments from the basin file {Path(basin_file).name}" if basin_file else ""
        source, short = (
            f"HEC-HMS results, own analysis point of each element, DSS files {listed}{where}.",
            "HMS",
        )
        if areas:
            for dam in dams:
                dam.catchment_km2 = areas.get(dam.name, dam.catchment_km2)
    rps = sorted((runs or dss).keys(), key=rp_sort_key)
    wi = WorkbookInput(dams, rps, target, dt, source, short, method, project)
    return layout.write(wi, out, tile_charts)
