"""What a run needs to know about a job's station files, and what it says about its gauges. Interface:
:func:`resolve_station_paths`, :func:`missing_station_files`, :func:`gauge_identity`, :func:`report_gauges`.

Kept apart from :mod:`wadi2d.run` so that the run's own code grows by a line per call.
"""

from __future__ import annotations

import json
from pathlib import Path

from wadi2d.config.schema import GAUGE_STORM, RunConfig
from wadi2d.hydrology.constants import SECONDS_PER_MINUTE
from wadi2d.io.identity import file_identity

GAUGE_FILE = "rain_gauges.json"


def _absolute(path: str | None, base: Path) -> str | None:
    if path is None or Path(path).is_absolute():
        return path
    return str((base / path).resolve())


def resolve_station_paths(cfg: RunConfig, base: Path) -> RunConfig:
    """The same job with every gauge file and observed file absolute; relative ones are relative to the job file."""
    storm, outputs = cfg.storm, cfg.outputs
    if storm.gauges is not None and storm.gauges.gauges:
        gauges = [g.model_copy(update={"file": _absolute(g.file, base)}) for g in storm.gauges.gauges]
        storm = storm.model_copy(update={"gauges": storm.gauges.model_copy(update={"gauges": gauges})})
    if outputs.observed:
        observed = [o.model_copy(update={"file": _absolute(o.file, base)}) for o in outputs.observed]
        outputs = outputs.model_copy(update={"observed": observed})
    if storm is cfg.storm and outputs is cfg.outputs:
        return cfg
    return cfg.model_copy(update={"storm": storm, "outputs": outputs})


def missing_station_files(cfg: RunConfig) -> list[str]:
    """A message per station file that is not there. An observed record is checked too: it is compared after the run,
    and a run of hours should not end on a mistyped name."""
    found = []
    gauges = cfg.storm.gauges.gauges if cfg.storm.kind == GAUGE_STORM and cfg.storm.gauges is not None else []
    for gauge in gauges:
        if gauge.file is not None and not Path(gauge.file).is_file():
            found.append(f"record of rain gauge {gauge.name} not found: {gauge.file}")
    for item in cfg.outputs.observed:
        if not Path(item.file).is_file():
            found.append(f"observed record {item.name} not found: {item.file}")
    return found


def gauge_identity(cfg: RunConfig, limit_mb: float) -> dict[str, object]:
    """The identity of every file the gauges are read from: a changed record refuses a resume, as a changed rain file does."""
    from wadi2d.storm.gauge_build import gauge_files

    return {
        f"storm.gauges.{path.name}.{n}": file_identity(path, limit_mb)
        for n, path in enumerate(gauge_files(cfg))
    }


def report_gauges(storm, forcing, cfg: RunConfig, progress, out: Path) -> None:
    """The run's notes on its gauge rain, one ``gauges`` event holding who carries what, and the same in
    ``rain_gauges.json``, where a later comparison finds the date of the run's minute zero."""
    cells = forcing.gridded
    for note in [*storm.notes(cfg.run.duration_s / SECONDS_PER_MINUTE), *cells.notes()]:
        progress.emit("warn", message=f"rain: {note}")
    areas = forcing.area if forcing.areas is None else forcing.areas
    report = {
        "method": storm.method,
        "gauges": {
            name: round(float(total), 3) for name, total in zip(storm.names, storm.totals, strict=True)
        },
        "positions": {name: [float(x), float(y)] for name, (x, y) in zip(storm.names, storm.xy, strict=True)},
        "start": None if storm.origin is None else str(storm.origin),
        "rain_ends_min": float(storm.edges[-1]),
        "cell_shares": cells.cell_shares(forcing.rained, areas),
        "subbasin_shares": storm.subbasin_shares(),
    }
    (out / GAUGE_FILE).write_text(json.dumps(report, indent=2), encoding="utf-8")
    progress.emit("gauges", **report)


def report_observed(cfg: RunConfig, out: Path, progress) -> None:
    """Every observed record beside its simulated series, once the run has written them; a record that cannot be
    compared costs a warning, never the run."""
    if not cfg.outputs.observed:
        return
    from wadi2d.engine.observed import OBSERVED_DIR, STATISTICS, compare_run

    try:
        report = compare_run(out)
    except (ValueError, OSError) as error:
        progress.emit("warn", message=f"observed records were not compared: {error}")
        return
    for failed in report["failed"]:
        progress.emit("warn", message=f"observed {failed['name']} was not compared: {failed['reason']}")
    for record in report["records"]:
        progress.emit(
            "observed", name=record["name"], target=record["target"], nse=record["nse"],
            pbias_percent=record["pbias_percent"], peak_ratio=record["peak_ratio"],
        )  # fmt: skip
    progress.emit("output", kind="observed", path=str(out / OBSERVED_DIR / STATISTICS))
