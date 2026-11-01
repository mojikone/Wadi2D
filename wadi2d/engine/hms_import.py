"""``hms-import``: a job.json from an HMS project, self-contained: the storm goes in as numbers.

Every subbasin comes in lumped, entering at the icon of the junction it drains to, and the terrain and grid stay
for the user to fill. A grid-depth storm has no point depth in the met file: ``storm.depth_mm`` stays 0 and has to
be written by hand. The ARF table's nature is not in the project, so the job says so instead of guessing.
"""

from __future__ import annotations

from pathlib import Path

from wadi2d.config.schema import ArfTableConfig, Hydrology, Project, RunConfig, Storm, Subbasin
from wadi2d.hms import load_basin, load_control, load_met, load_pdata
from wadi2d.hydrology.from_hms import grid_from_hms, load_project_tables
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
    arf = None
    if storm.reduction_table_name in tables.area_reductions:
        table = tables.area_reductions[storm.reduction_table_name]
        arf = ArfTableConfig(
            areas_km2=[float(v) for v in table.areas_km2],
            factors=[float(v) for v in table.factors],
            table_type=ARF_TABLE_TYPE,
        )
    return Storm(
        kind="hypothetical",
        depth_mm=storm.storm_depth or 0.0,
        duration_min=storm.storm_duration * MINUTES_PER_HOUR,
        time_percent=[float(v) for v in pattern.time_percent],
        depth_percent=[float(v) for v in pattern.depth_percent],
        storm_area_km2=storm.storm_area,
        arf=arf,
    )


def build_job(hms_dir: Path, basin: str, met: str, control: str) -> RunConfig:
    """The job of a basin, met and control file of one project."""
    basin_path = hms_dir / basin
    model = load_basin(basin_path)
    subbasins = []
    for name, element in model.subbasins.items():
        target = model.junctions.get(element.downstream or "")
        outlet = None
        if target is not None and target.canvas_x is not None and target.canvas_y is not None:
            outlet = (target.canvas_x, target.canvas_y)
        subbasins.append(Subbasin(name=name, mode="lumped", outlet=outlet))
    sqlite = basin_path.with_suffix(SQLITE_SUFFIX)
    timing = grid_from_hms(load_control(hms_dir / control))
    return RunConfig(
        project=Project(name=f"{basin_path.stem}_{Path(met).stem}"),
        storm=_storm(hms_dir / met, hms_dir),
        hydrology=Hydrology(
            hms_basin=str(basin_path),
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
