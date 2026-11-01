"""Compare the lumped engine with a computed HMS project, and write the table.

Interface: :func:`replicate`, :func:`render`, :class:`Replication`, :class:`Comparison`. Reads the project's own
depth-area analyses and their results files, reruns each analysis here, and compares the peak at every analysis
point. Nothing is written to the project.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from wadi2d.hms import (
    AnalysisResults,
    load_basin,
    load_met,
    load_nals,
    load_pdata,
    load_project,
    load_results,
)
from wadi2d.hydrology.constants import PERCENT, SECONDS_PER_MINUTE
from wadi2d.hydrology.depth_area import StormAtPoint, analyse, point_storm
from wadi2d.hydrology.from_hms import (
    ProjectTables,
    basin_from_hms,
    find_grid_file,
    grid_from_hms,
    grid_storm,
    load_project_tables,
    storm_from_hms,
)
from wadi2d.hydrology.model import Basin, TimeGrid
from wadi2d.hydrology.network import LumpedEngine
from wadi2d.storm.grid_depth import DepthGrid

RESULTS_FOLDER = "results"
RESULTS_PREFIX = "DAA_"
RESULTS_SUFFIX = ".results"
GRID_METHOD = "Precipitation-Frequency Grid"
DSS_SUFFIX = ".dss"
PAIRED_SUFFIX = ".pdata"
GRID_SUFFIX = ".grid"
NALS_SUFFIX = ".nals"
SQLITE_SUFFIX = ".sqlite"


@dataclass(frozen=True)
class Comparison:
    """One analysis point of one analysis."""

    analysis: str
    point: str
    hms_peak: float
    peak: float
    hms_minutes: float
    minutes: float
    dt_minutes: float

    @property
    def error_percent(self) -> float:
        """Peak error against HMS, %."""
        return PERCENT * (self.peak / self.hms_peak - 1.0)

    @property
    def time_steps(self) -> int:
        """Time-of-peak error, control steps."""
        return round((self.minutes - self.hms_minutes) / self.dt_minutes)


@dataclass(frozen=True)
class Replication:
    """All comparisons, in project order, and any analysis left out with the reason."""

    comparisons: list[Comparison] = field(default_factory=list)
    left_out: dict[str, str] = field(default_factory=dict)

    @property
    def analyses(self) -> list[str]:
        """The analyses compared, in order."""
        return list(dict.fromkeys(c.analysis for c in self.comparisons))

    @property
    def points(self) -> list[str]:
        """The analysis points, in order."""
        return list(dict.fromkeys(c.point for c in self.comparisons))

    def of(self, analysis: str | None = None, points: Iterable[str] | None = None) -> list[Comparison]:
        """The comparisons of one analysis and of some points; everything when a filter is None."""
        chosen = None if points is None else set(points)
        return [
            c
            for c in self.comparisons
            if (analysis is None or c.analysis == analysis) and (chosen is None or c.point in chosen)
        ]

    def worst(self, points: Iterable[str] | None = None) -> Comparison:
        """The largest absolute peak error."""
        return max(self.of(points=points), key=lambda c: abs(c.error_percent))


def _compare(
    name: str,
    results: AnalysisResults,
    engine: LumpedEngine,
    storm: StormAtPoint,
    grid: TimeGrid,
    points: list[str],
) -> list[Comparison]:
    computed = analyse(engine, storm, grid, points)
    rows: list[Comparison] = []
    for point, result in computed.items():
        reference = results.element(point)
        if reference.outflow_max is None or reference.outflow_max_time is None or results.start is None:
            raise ValueError(f"no HMS peak for {point} in {name}")
        minutes = (reference.outflow_max_time - results.start).total_seconds() / SECONDS_PER_MINUTE
        rows.append(
            Comparison(
                name, point, reference.outflow_max, result.peak, minutes, result.peak_minutes, grid.dt_minutes
            )
        )
    return rows


def _point_storm(
    met_path: Path, tables: ProjectTables, basin: Basin, basin_path: Path, stem: str
) -> StormAtPoint:
    """The storm of a met model; a grid storm reads its raster, which raises when it cannot be found."""
    met = load_met(met_path)
    if met.storm is None:
        raise ValueError(f"{met_path} has no Hypothetical Storm")
    if met.storm.precipitation_method != GRID_METHOD:
        return point_storm(storm_from_hms(met.storm, tables))
    if met.storm.precip_freq_grid_name is None:
        raise ValueError(f"{met_path} names no grid")
    folder = basin_path.parent
    raster = find_grid_file(
        folder / f"{stem}{GRID_SUFFIX}", met.storm.precip_freq_grid_name, (folder, folder.parent)
    )
    storm = storm_from_hms(met.storm, tables, depth_mm=0.0)
    return grid_storm(storm, DepthGrid.load(raster), basin, basin_path.with_suffix(SQLITE_SUFFIX))


def replicate(project_file: str | Path) -> Replication:
    """Rerun every depth-area analysis of a project; an analysis whose grid cannot be read is left out."""
    source = Path(project_file)
    folder = source.parent
    project = load_project(source)
    pdata = load_pdata(folder / f"{source.stem}{PAIRED_SUFFIX}")
    tables = load_project_tables(pdata, folder / f"{source.stem}{DSS_SUFFIX}")
    engines: dict[str, LumpedEngine] = {}
    comparisons: list[Comparison] = []
    left_out: dict[str, str] = {}
    for analysis in load_nals(folder / f"{source.stem}{NALS_SUFFIX}").analyses:
        if analysis.met_model_name is None or analysis.basin_model_name is None:
            left_out[analysis.name] = "no met or basin model"
            continue
        basin_path = project.path_of(project.basins[analysis.basin_model_name])
        if analysis.basin_model_name not in engines:
            engines[analysis.basin_model_name] = LumpedEngine(basin_from_hms(load_basin(basin_path)))
        engine = engines[analysis.basin_model_name]
        met_path = project.path_of(project.mets[analysis.met_model_name])
        try:
            storm = _point_storm(met_path, tables, engine.basin, basin_path, source.stem)
        except (OSError, KeyError) as error:
            left_out[analysis.name] = f"grid not readable: {error}"
            continue
        results_name = f"{RESULTS_PREFIX}{analysis.name.replace(' ', '_')}{RESULTS_SUFFIX}"
        results = load_results(folder / RESULTS_FOLDER / results_name)
        grid = grid_from_hms(analysis)
        comparisons += _compare(analysis.name, results, engine, storm, grid, list(analysis.points))
    return Replication(comparisons, left_out)


def _summary_row(replication: Replication, analysis: str, dams: list[str]) -> str:
    rows = replication.of(analysis)
    worst = max(rows, key=lambda c: abs(c.error_percent))
    dam_worst = max(replication.of(analysis, dams), key=lambda c: abs(c.error_percent))
    slip = max(abs(c.time_steps) for c in rows)
    return (
        f"| {analysis} | {worst.error_percent:+.3f} | {worst.point} | {dam_worst.error_percent:+.3f} "
        f"| {dam_worst.point} | {slip} |"
    )


def render(replication: Replication, dams: list[str], reference_analysis: str, preamble: str) -> str:
    """The Markdown report: summary per analysis, the dam sites, every error."""
    analyses = replication.analyses
    lines = [preamble.rstrip(), "", "## Summary per analysis", ""]
    lines += ["| Analysis | Worst peak error % | At | Worst dam-site error % | At | Max time error, steps |"]
    lines += ["|---|---|---|---|---|---|"]
    lines += [_summary_row(replication, analysis, dams) for analysis in analyses]
    lines += ["", f"## Dam sites, {reference_analysis}", ""]
    lines += ["| Dam site | HMS m3/s | Wadi2D m3/s | Error % | Time error, steps |", "|---|---|---|---|---|"]
    for row in replication.of(reference_analysis, dams):
        lines.append(
            f"| {row.point} | {row.hms_peak:.2f} | {row.peak:.2f} | {row.error_percent:+.4f} | {row.time_steps} |"
        )
    lines += ["", "## Peak error at every analysis point, %", ""]
    short = [analysis.split()[1] for analysis in analyses]
    lines += ["| Point | " + " | ".join(short) + " |", "|---|" + "---|" * len(short)]
    for point in replication.points:
        cells = [f"{replication.of(a, [point])[0].error_percent:+.3f}" for a in analyses]
        lines.append(f"| {point} | " + " | ".join(cells) + " |")
    if replication.left_out:
        lines += ["", "## Left out", ""]
        lines += [f"- {name}: {reason}" for name, reason in replication.left_out.items()]
    return "\n".join(lines) + "\n"
