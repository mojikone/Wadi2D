"""``hms-import``: a job.json from an HMS project, self-contained: the storm goes in as numbers.

Every subbasin comes in lumped, with ``entry: wadi``: the run puts its hydrograph at the wadi outlet of its polygon on
the grid, clear above every result line (W41). HMS icons are schematic, and at all five Block 2 dams the dam junction's
icon lies 0.4 to 87 m below the dam line, so a hydrograph entered there passes under the line. The icon of the element
it drains to (junction, sink, reservoir or the head of a reach) stays as the outlet, for a subbasin without a polygon.
The terrain and grid stay for the user to fill. A subbasin that drains to nothing keeps no outlet, and the run refuses
it by name. A grid-depth storm carries its raster; a storm that gives no depth at all
is refused here. The ARF table's nature is not in the project, so the job says so instead of guessing.
"""

from __future__ import annotations

from pathlib import Path

from wadi2d.config.schema import ENTRY_WADI, ArfTableConfig, Hydrology, Project, RunConfig, Storm, Subbasin
from wadi2d.hms import load_basin, load_control, load_met, load_pdata
from wadi2d.hms.basin import Basin, Element, Reach
from wadi2d.hydrology.from_hms import find_grid_file, grid_from_hms, load_project_tables
from wadi2d.hydrology.replication import GRID_METHOD, GRID_SUFFIX
from wadi2d.storm.hypothetical import MINUTES_PER_HOUR

SQLITE_SUFFIX = ".sqlite"
ARF_TABLE_TYPE = "as supplied in the HMS project; check whether it is fixed-area or storm-centred"


def _storm(met_path: Path, hms_dir: Path) -> Storm:
    """The met model's hypothetical storm with its pattern and ARF table as numbers."""
    storm = load_met(met_path).storm
    if storm is None:
        raise ValueError(f"{met_path.name} has no hypothetical storm")
    projects = sorted(hms_dir.glob("*.hms"))
    if not projects:
        raise FileNotFoundError(f"no .hms file in {hms_dir}")
    stem = projects[0].with_suffix("")
    tables = load_project_tables(load_pdata(stem.with_suffix(".pdata")), stem.with_suffix(".dss"))
    pattern = tables.patterns[storm.pattern_name]
    grid = None
    if storm.precipitation_method == GRID_METHOD:
        if storm.precip_freq_grid_name is None:
            raise ValueError(f"{met_path.name} names no precipitation grid")
        grid = str(
            find_grid_file(
                stem.with_suffix(GRID_SUFFIX), storm.precip_freq_grid_name, (hms_dir, hms_dir.parent)
            )
        )
    elif storm.storm_depth is None:
        raise ValueError(f"{met_path.name}: a depth for each subbasin cannot go into a job yet")
    arf = None
    if storm.reduction_table_name in tables.area_reductions:
        table = tables.area_reductions[storm.reduction_table_name]
        arf = ArfTableConfig(
            areas_km2=[float(v) for v in table.areas_km2],
            factors=[float(v) for v in table.factors],
            table_type=ARF_TABLE_TYPE,
            reduces_below_table=table.reduces_below_table,
        )
    return Storm(
        kind="hypothetical",
        depth_mm=storm.storm_depth or 0.0,
        depth_grid=grid,
        duration_min=storm.storm_duration * MINUTES_PER_HOUR,
        time_percent=[float(v) for v in pattern.time_percent],
        depth_percent=[float(v) for v in pattern.depth_percent],
        storm_area_km2=storm.storm_area,
        arf=arf,
    )


def _outlet(model: Basin, element: Element) -> tuple[float, float] | None:
    """Where a subbasin's water leaves it: the icon of what it drains to, the upstream end of a reach."""
    target = next((e for e in model.elements if e.name == element.downstream), None)
    if target is None:
        return None
    if isinstance(target, Reach) and target.from_canvas_x is not None and target.from_canvas_y is not None:
        return target.from_canvas_x, target.from_canvas_y
    if target.canvas_x is None or target.canvas_y is None:
        return None
    return target.canvas_x, target.canvas_y


def build_job(hms_dir: Path, basin: str, met: str, control: str) -> RunConfig:
    """The job of a basin, met and control file of one project."""
    basin_path = hms_dir / basin
    model = load_basin(basin_path)
    subbasins = [
        Subbasin(name=name, mode="lumped", outlet=_outlet(model, element), entry=ENTRY_WADI)
        for name, element in model.subbasins.items()
    ]
    sqlite = basin_path.with_suffix(SQLITE_SUFFIX)
    timing = grid_from_hms(load_control(hms_dir / control))
    return RunConfig(
        project=Project(name=f"{basin_path.stem}_{Path(met).stem}"),
        storm=_storm(hms_dir / met, hms_dir),
        hydrology=Hydrology(
            hms_basin=str(basin_path),
            hms_project=str(next(iter(sorted(hms_dir.glob("*.hms"))), "")) or None,
            hms_sqlite=str(sqlite) if sqlite.is_file() else None,
            time_step_min=timing.dt_minutes,
            subbasins=subbasins,
        ),
        run={"duration_s": timing.n_intervals * timing.dt_seconds},
    )


def write_job(hms_dir: Path, basin: str, met: str, control: str, out: Path) -> Path:
    """Write the job file."""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_job(hms_dir, basin, met, control).model_dump_json(indent=2), encoding="utf-8")
    return out
