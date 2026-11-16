"""Where the product step meets a run: after ``run_job``'s simulation, and alone through ``wadi2d products``.

A stop or a failure here does not undo a finished simulation: its maps and series are already written, so the run
keeps its exit code and the ``done`` event says what became of the pixel maps. Only ``wadi2d products`` itself exits
with the step's own outcome.
"""

from __future__ import annotations

import json
import traceback
from collections.abc import Iterable
from pathlib import Path

from wadi2d.config.schema import RunConfig
from wadi2d.io.progress import Progress
from wadi2d.products.frames import frame_names
from wadi2d.products.step import (
    DEPTH_FILE,
    HAZARD_FILE,
    PIXEL_DIR,
    STAGES,
    STAGES_DRAWING,
    STAGES_RECORD,
    STATS_FILE,
    ProductsStopped,
    Watch,
    make_products,
    read_record,
)

PRODUCTS_NONE, PRODUCTS_DONE, PRODUCTS_STOPPED, PRODUCTS_FAILED, PRODUCTS_SKIPPED = (
    "none", "finished", "stopped", "failed", "skipped",
)  # fmt: skip
PRODUCTS_LOG = "products.jsonl"
EXIT_OK, EXIT_FAILED, EXIT_INVALID, EXIT_STOPPED = 0, 1, 2, 6


def make_after_run(
    cfg: RunConfig, tables, crs, out: Path, backend: str | None, progress: Progress, stop_files: Iterable[Path], tags
) -> str:
    """The step for a finished run; what became of it, one of the ``PRODUCTS_`` words."""
    if not cfg.outputs.pixels.enabled:
        return PRODUCTS_NONE
    if not frame_names(out / "results.h5"):
        progress.emit("output", kind="pixels_skipped", reason="the run saved no maps")
        return PRODUCTS_SKIPPED
    stops = (out / "stop", *stop_files)
    stages = STAGES if cfg.outputs.smooth.enabled else STAGES_RECORD
    watch = Watch(progress.emit, lambda: any(path.exists() for path in stops), stages)
    try:
        make_products(cfg, tables, crs, out, watch, backend or cfg.run.backend, tags)
    except ProductsStopped:
        (out / "stop").unlink(missing_ok=True)
        progress.emit("warn", message="Pixel maps stopped on request. The run itself finished and its maps are written.")
        return PRODUCTS_STOPPED
    except Exception as error:  # the simulation is safe on disk: this must not turn into a failed run
        progress.emit(
            "warn",
            message=f"The pixel maps could not be made: {error}. The run itself finished and its maps are written.",
            trace=traceback.format_exc(),
        )
        return PRODUCTS_FAILED
    progress.emit("output", kind="pixels", path=str(out / PIXEL_DIR))
    return PRODUCTS_DONE


def _cell_maps(run: Path, tables, crs, progress: Progress) -> None:
    """A run on an aligned mesh made before its cell maps held the strip's cells (W86) gets them with a remake:
    seconds, and the wadis are no longer blank in ``maps/``. A failure here is not in the way of the pixel maps."""
    from wadi2d.products.cell_maps import remake_cell_maps

    try:
        filled = remake_cell_maps(run, tables, crs)
    except Exception as error:
        progress.emit("warn", message=f"The cell maps could not be written again with the strip's cells: {error}")
        return
    if filled:
        progress.emit("output", kind="cell_maps", path=str(run / "maps"), strip_squares=filled)


def remake(run: Path, backend: str | None = None, echo: bool = False) -> int:
    """The step again on a run folder, with this engine and that run's own configuration."""
    from wadi2d.run import InvalidJob, prepare_grid

    config = run / "config.resolved.json"
    with Progress(run / PRODUCTS_LOG, echo=echo) as progress:
        try:
            if not config.is_file() or not (run / "results.h5").is_file():
                raise InvalidJob(f"{run} holds no finished run")
            cfg = RunConfig.model_validate_json(config.read_text(encoding="utf-8"))
            asked = cfg.outputs.pixels.model_copy(update={"enabled": True})  # asking for them outranks the job
            cfg = cfg.model_copy(update={"outputs": cfg.outputs.model_copy(update={"pixels": asked})})
            cache = Path(cfg.grid.cache_dir) if cfg.grid.cache_dir else run / "cache"
            tables, crs = prepare_grid(cfg, cache, progress)
            _cell_maps(run, tables, crs, progress)
            outcome = make_after_run(cfg, tables, crs, run, backend, progress, (), None)
        except InvalidJob as error:
            progress.emit("error", code=EXIT_INVALID, message=str(error))
            return EXIT_INVALID
        code = {PRODUCTS_STOPPED: EXIT_STOPPED, PRODUCTS_FAILED: EXIT_FAILED}.get(outcome, EXIT_OK)
        progress.emit("done", status=outcome, code=code, products=outcome)
    return code


WINDOWS_DIR = "windows"
"""Under a run's ``pixels``: the rasters of drawn windows at the pixel asked for (W100)."""


def window_folder(run: Path, window: tuple[float, float, float, float], pixel_m: float) -> Path:
    """Where ``wadi2d window`` puts a window's rasters when it is not told: named by its corners and pixel."""
    xmin, ymin, xmax, ymax = (round(v) for v in window)
    return run / PIXEL_DIR / WINDOWS_DIR / f"window_{xmin}_{ymin}_{xmax}_{ymax}_{pixel_m:g}m"


def export_window(
    run: Path,
    window: tuple[float, float, float, float],
    pixel_m: float = 0.0,
    out: Path | None = None,
    backend: str | None = None,
    echo: bool = False,
    surface: str | None = None,
) -> int:
    """``wadi2d window``: the rasters of record of one window of a finished run at another pixel, the DEM's own by
    default (W100). The maps of record are coarser; this is their detail where it is wanted, each pixel what the
    whole run at that pixel would hold there. Nothing of the run is touched but the new folder."""
    from wadi2d.run import InvalidJob, prepare_grid

    run = Path(run)
    xmin, ymin, xmax, ymax = window
    target = Path(out) if out is not None else window_folder(run, window, pixel_m)
    target.mkdir(parents=True, exist_ok=True)
    config = run / "config.resolved.json"
    with Progress(target / PRODUCTS_LOG, echo=echo) as progress:
        try:
            if not config.is_file() or not (run / "results.h5").is_file():
                raise InvalidJob(f"{run} holds no finished run")
            if xmax <= xmin or ymax <= ymin:
                raise InvalidJob("a window runs from its west and south edges to its east and north ones")
            cfg = RunConfig.model_validate_json(config.read_text(encoding="utf-8"))
            update = {"enabled": True, "pixel_m": pixel_m, **({"surface": surface} if surface else {})}
            asked = cfg.outputs.pixels.model_copy(update=update)
            asked = type(asked).model_validate(asked.model_dump())  # the settings checked as a job's would be
            cfg = cfg.model_copy(update={"outputs": cfg.outputs.model_copy(update={"pixels": asked})})
            cache = Path(cfg.grid.cache_dir) if cfg.grid.cache_dir else run / "cache"
            tables, crs = prepare_grid(cfg, cache, progress)
            stop = run / "stop"
            watch = Watch(progress.emit, stop.exists, STAGES_RECORD)
            make_products(cfg, tables, crs, run, watch, backend or cfg.run.backend, None, tuple(window), target)
        except InvalidJob as error:
            progress.emit("error", code=EXIT_INVALID, message=str(error))
            return EXIT_INVALID
        except ProductsStopped:
            (run / "stop").unlink(missing_ok=True)
            progress.emit("done", status=PRODUCTS_STOPPED, code=EXIT_STOPPED, products=PRODUCTS_STOPPED)
            return EXIT_STOPPED
        except (ValueError, OSError) as error:
            progress.emit("error", code=EXIT_FAILED, message=f"The window could not be made: {error}", trace=traceback.format_exc())
            return EXIT_FAILED
        progress.emit("output", kind="window", path=str(target))
        progress.emit("done", status=PRODUCTS_DONE, code=EXIT_OK, products=PRODUCTS_DONE)
    return EXIT_OK


def _draw(run: Path, backend: str | None, progress: Progress) -> None:
    """The polygons and the depth drawing from the rasters a run holds; the layers too when the run has none."""
    from wadi2d.io.geopackage import layer_names
    from wadi2d.products.pixels import array_module
    from wadi2d.products.smooth import DOMAIN_LAYER, LAYERS_FILE, make_drawings, run_layers
    from wadi2d.run import InvalidJob, prepare_grid

    config, folder = run / "config.resolved.json", run / PIXEL_DIR
    if not config.is_file() or not all((folder / name).is_file() for name in (HAZARD_FILE, DEPTH_FILE)):
        raise InvalidJob(f"{run} holds no pixel rasters to draw: wadi2d products makes them")
    cfg = RunConfig.model_validate_json(config.read_text(encoding="utf-8"))
    stop = run / "stop"
    watch = Watch(progress.emit, stop.exists, STAGES_DRAWING)
    watch.tick("smooth", 0, 1)
    classes, depth, profile = read_record(folder)
    layers = None
    if DOMAIN_LAYER not in layer_names(folder / LAYERS_FILE):  # a run made before every run kept its layers
        cache = Path(cfg.grid.cache_dir) if cfg.grid.cache_dir else run / "cache"
        tables, crs = prepare_grid(cfg, cache, progress)
        layers = run_layers(cfg, tables, crs)
    xp = array_module(backend or cfg.run.backend)
    accounts = make_drawings(cfg, classes, depth, profile, folder, profile["crs"], watch, xp, layers)
    stats_file = folder / STATS_FILE
    stats = json.loads(stats_file.read_text(encoding="utf-8")) if stats_file.is_file() else {}
    stats_file.write_text(json.dumps({**stats, "smooth": accounts}, indent=1), encoding="utf-8")


def draw(run: Path, backend: str | None = None, echo: bool = False) -> int:
    """``wadi2d drawings``: the smooth class polygons and the depth drawing of a finished run, made when they are
    wanted and not with every run (W50). They are drawn from the run's rasters of record, as the run draws them."""
    from wadi2d.run import InvalidJob

    with Progress(run / PRODUCTS_LOG, echo=echo) as progress:
        outcome = PRODUCTS_DONE
        try:
            _draw(run, backend, progress)
        except InvalidJob as error:
            progress.emit("error", code=EXIT_INVALID, message=str(error))
            return EXIT_INVALID
        except ProductsStopped:
            (run / "stop").unlink(missing_ok=True)
            progress.emit("warn", message="The drawing stopped on request. The run's rasters are as they were.")
            outcome = PRODUCTS_STOPPED
        except Exception as error:  # the protocol wants a code and an event, never a traceback alone
            progress.emit("error", code=EXIT_FAILED, message=f"The drawing could not be made: {error}", trace=traceback.format_exc())
            outcome = PRODUCTS_FAILED
        else:
            progress.emit("output", kind="drawings", path=str(run / PIXEL_DIR))
        code = {PRODUCTS_STOPPED: EXIT_STOPPED, PRODUCTS_FAILED: EXIT_FAILED}.get(outcome, EXIT_OK)
        progress.emit("done", status=outcome, code=code, products=outcome)
    return code
