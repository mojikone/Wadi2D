"""The pit check of a run, and the fill when the job asks for it (W85).

Runs once the tables are there: ``terrain.pit_check`` names the pits in the run's warnings and in
``terrain_checks.gpkg``; ``terrain.fill_pits`` adds a ``fill`` terrain object for every cell of every pit and builds the
tables again on that ground. The job that comes back holds those objects, so ``config.resolved.json``, the pixel maps
and every later reading of the run take the same ground as the solver did.

A job that already holds pit fills was resolved before (a study's runs share one grid; a resolved job run again): it
is left as it is, and its tables are taken as given.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from wadi2d.config.schema import RunConfig
from wadi2d.io.progress import Progress
from wadi2d.tables.builder import GridTables
from wadi2d.terrain.pits import Pit, fill_objects, find_pits, is_pit_fill, pit_notes, write_pits


def resolve_pits(
    cfg: RunConfig,
    tables: GridTables,
    crs: str,
    out: Path,
    progress: Progress,
    rebuild: Callable[[RunConfig, GridTables], GridTables] | None,
) -> tuple[RunConfig, GridTables, list[Pit]]:
    """(the job as it runs, its tables, the pits found). ``rebuild(job, before)`` gives the tables of a job, ``before``
    the tables of the same job without its fills (W91: it builds again only what the fills reach); None says the
    tables in hand cannot be replaced, and a fill asked for is then refused in a warning."""
    cfg, tables, pits = _resolve(cfg, tables, crs, out, progress, rebuild)
    tables.raw = None  # what a build kept for the rebuild (W91): five arrays of the grid's size, not needed again
    tables.strip_raw = None  # and the strip's piece tables
    return cfg, tables, pits


def _resolve(cfg, tables, crs, out, progress, rebuild):
    terrain = cfg.terrain
    if not (terrain.pit_check or terrain.fill_pits) or any(is_pit_fill(o) for o in terrain.objects):
        return cfg, tables, []
    if getattr(tables.grid, "quad", False):
        if terrain.fill_pits:
            progress.emit(
                "warn",
                message="pits are not filled on a refined mesh in this version: terrain.fill_pits is left out",
            )
        return cfg, tables, []
    pits = find_pits(tables, terrain)
    filled = bool(pits) and terrain.fill_pits and rebuild is not None
    if pits and terrain.fill_pits and rebuild is None:
        progress.emit("warn", message="the pits are not filled: this run was given its tables ready made")
    if filled:
        objects = [*terrain.objects, *fill_objects(pits, tables)]
        cfg = cfg.model_copy(update={"terrain": terrain.model_copy(update={"objects": objects})})
        tables = rebuild(cfg, tables)
        left = find_pits(tables, terrain)
        if left:
            deepest = left[0]
            progress.emit(
                "warn",
                message=f"{len(left)} pits are left after the fill, the deepest {deepest.depth_m:.1f} m at "
                f"({deepest.x:.0f}, {deepest.y:.0f}): run again to fill them, or look at the ground there",
            )
    for note in pit_notes(pits, filled, tables.grid.dx):
        progress.emit("warn", message=note)
    path = write_pits(out, pits, crs, filled)
    if path is not None:
        progress.emit(
            "output", kind="terrain_pits", path=str(path), pits=len(pits), filled=filled,
            volume_m3=round(sum(p.volume_m3 for p in pits), 1),
        )  # fmt: skip
    return cfg, tables, pits
