"""Compare the lumped engine with a computed HMS project, and write the table.

Interface: :func:`replicate`, :func:`render`, :class:`Replication`, :class:`Comparison`. Reads the project's own
depth-area analyses and their results files, reruns each analysis here, and compares the peak at every analysis
point. Nothing is written to the project. Whatever cannot be compared is left out with its reason, never guessed
at: an analysis with no results file or with an element the engine does not implement, a point the results do
not hold.
"""

from __future__ import annotations

import math
import re
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
from wadi2d.hms import Basin as HmsBasin
from wadi2d.hms.nals import Analysis
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
NOT_IN_A_RESULTS_NAME = re.compile(r"[^0-9A-Za-z]")
GRID_METHOD = "Precipitation-Frequency Grid"
DSS_SUFFIX = ".dss"
PAIRED_SUFFIX = ".pdata"
GRID_SUFFIX = ".grid"
NALS_SUFFIX = ".nals"
SQLITE_SUFFIX = ".sqlite"
NO_UNIFORM_DEPTH = "No"


def results_file_name(analysis: str) -> str:
    """HMS replaces every character that is not a letter or a digit: `DA 10yr 1D DAM - All`."""
    return f"{RESULTS_PREFIX}{NOT_IN_A_RESULTS_NAME.sub('_', analysis)}{RESULTS_SUFFIX}"


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
        """Peak error against HMS, %; a dam that spills nothing has a peak of zero."""
        if self.hms_peak == 0.0:
            return 0.0 if self.peak == 0.0 else math.inf
        return PERCENT * (self.peak / self.hms_peak - 1.0)

    @property
    def time_steps(self) -> int:
        """Time-of-peak error, control steps."""
        return round((self.minutes - self.hms_minutes) / self.dt_minutes)


@dataclass(frozen=True)
class Replication:
    """All comparisons in project order, any analysis left out with the reason, any point the results lack."""

    comparisons: list[Comparison] = field(default_factory=list)
    left_out: dict[str, str] = field(default_factory=dict)
    points_without_results: dict[str, list[str]] = field(default_factory=dict)

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
    computed = analyse(engine, storm, grid, [point for point in points if point in results.points])
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
    met_path: Path, tables: ProjectTables, hms_basin: HmsBasin, basin: Basin, basin_path: Path, stem: str
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
    crs = hms_basin.spatial.coordinate_system if hms_basin.spatial is not None else None
    return grid_storm(
        storm,
        DepthGrid.load(raster, crs),
        basin,
        basin_path.with_suffix(SQLITE_SUFFIX),
        by_subbasin=met.storm.uniform_depth == NO_UNIFORM_DEPTH,
    )


class _Project:
    """One project during a replication: its files, its tables, and one engine per basin model."""

    def __init__(self, source: Path) -> None:
        self.source = source
        self.folder = source.parent
        self.project = load_project(source)
        pdata = load_pdata(self.folder / f"{source.stem}{PAIRED_SUFFIX}")
        self.tables = load_project_tables(pdata, self.folder / f"{source.stem}{DSS_SUFFIX}")
        self._models: dict[str, tuple[HmsBasin, LumpedEngine] | ValueError] = {}

    def model(self, basin_name: str) -> tuple[HmsBasin, LumpedEngine]:
        """The basin model and its engine; a model the engine cannot build raises the same error each time."""
        if basin_name not in self._models:
            try:
                hms_basin = load_basin(self.project.path_of(self.project.basins[basin_name]))
                engine = LumpedEngine(basin_from_hms(hms_basin, self.tables))
                self._models[basin_name] = (hms_basin, engine)
            except ValueError as error:
                self._models[basin_name] = error
        found = self._models[basin_name]
        if isinstance(found, ValueError):
            raise found
        return found


def _run_analysis(project: _Project, analysis: Analysis) -> tuple[list[Comparison], list[str]]:
    """The comparisons of one analysis, and the points its results lack; what stops it raises."""
    if analysis.met_model_name is None or analysis.basin_model_name is None:
        raise ValueError("no met or basin model")
    results_path = project.folder / RESULTS_FOLDER / results_file_name(analysis.name)
    if not results_path.is_file():
        raise FileNotFoundError(f"no results file {results_path.name}")
    hms_basin, engine = project.model(analysis.basin_model_name)
    basin_path = project.project.path_of(project.project.basins[analysis.basin_model_name])
    met_path = project.project.path_of(project.project.mets[analysis.met_model_name])
    storm = _point_storm(met_path, project.tables, hms_basin, engine.basin, basin_path, project.source.stem)
    results = load_results(results_path)
    points = list(analysis.points)
    rows = _compare(analysis.name, results, engine, storm, grid_from_hms(analysis), points)
    return rows, [point for point in points if point not in results.points]


def replicate(project_file: str | Path, analyses: Iterable[str] | None = None) -> Replication:
    """Rerun the depth-area analyses of a project, all or the named ones; what cannot run is left out."""
    source = Path(project_file)
    project = _Project(source)
    wanted = None if analyses is None else set(analyses)
    replication = Replication()
    for analysis in load_nals(source.with_suffix(NALS_SUFFIX)).analyses:
        if wanted is not None and analysis.name not in wanted:
            continue
        try:
            rows, lacking = _run_analysis(project, analysis)
        except (OSError, KeyError, ValueError) as error:
            replication.left_out[analysis.name] = f"{type(error).__name__}: {error}"
            continue
        replication.comparisons.extend(rows)
        if lacking:
            replication.points_without_results[analysis.name] = lacking
    return replication


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
