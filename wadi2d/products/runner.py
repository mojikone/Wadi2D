"""Where the product step meets a run: after ``run_job``'s simulation, and alone through ``wadi2d products``.

A stop or a failure here does not undo a finished simulation: its maps and series are already written, so the run
keeps its exit code and the ``done`` event says what became of the pixel maps. Only ``wadi2d products`` itself exits
with the step's own outcome.
"""

from __future__ import annotations

import traceback
from collections.abc import Iterable
from pathlib import Path

from wadi2d.config.schema import RunConfig
from wadi2d.io.progress import Progress
from wadi2d.products.frames import frame_names
from wadi2d.products.step import PIXEL_DIR, ProductsStopped, Watch, make_products

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
    watch = Watch(progress.emit, lambda: any(path.exists() for path in stops))
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
            outcome = make_after_run(cfg, tables, crs, run, backend, progress, (), None)
        except InvalidJob as error:
            progress.emit("error", code=EXIT_INVALID, message=str(error))
            return EXIT_INVALID
        code = {PRODUCTS_STOPPED: EXIT_STOPPED, PRODUCTS_FAILED: EXIT_FAILED}.get(outcome, EXIT_OK)
        progress.emit("done", status=outcome, code=code, products=outcome)
    return code
