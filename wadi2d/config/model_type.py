"""The four kinds of run as a saved setting, ``run.model_type`` (W96): what each needs of the rest of the job.

Interface: :func:`model_type` (the job's, or inferred for a job that gives none), :func:`model_type_problems` (why a
given type does not fit the job, in words), :func:`implied_by_type` (what a type sets when the job leaves it unsaid).

- ``2d``: one 2D model, rain on the grid; no lumped part.
- ``lumped``: the lumped network alone, the HMS way (``run.lumped_only``); a basin file is needed, no grid.
- ``hybrid_lumped``: lumped catchments left out of the mesh (``grid.exclude_lumped``), 2D below them.
- ``hybrid_2d``: lumped catchments whose cells stay in the mesh, only the wet ones active (W90's sleeping tiles).

The functions read the job's attributes and import no schema, so the schema's validator calls them.
"""

from __future__ import annotations

from typing import Any

from wadi2d.config.land import MODEL_2D, MODEL_HYBRID_2D, MODEL_HYBRID_LUMPED, MODEL_LUMPED

IMPLIED = {MODEL_LUMPED: ("run", "lumped_only", True), MODEL_HYBRID_LUMPED: ("grid", "exclude_lumped", True)}
"""What a type sets when the job does not say: (part, field, value)."""


def lumped_part(cfg: Any) -> list[str]:
    """What in the job is a lumped part, in words; empty for a job wholly on the grid."""
    h = cfg.hydrology
    found = []
    if h.basin_json is not None:
        found.append("hydrology.basin_json")
    lumped = [s.name for s in h.subbasins if s.mode == "lumped"]
    if lumped:
        found.append(f"lumped subbasins {lumped}")
    elements = [i.name for i in h.inflows if i.element is not None]
    if elements:
        found.append(f"inflows from lumped elements {elements}")
    if h.handbacks:
        found.append(f"hand-backs {[b.name for b in h.handbacks]}")
    return found


def _left_out(cfg: Any) -> bool:
    return bool(cfg.grid.exclude_lumped or cfg.grid.exclude_subbasins)


def inferred_type(cfg: Any) -> str:
    """The type a job that gives none runs as: lumped alone, hybrid with catchments left out or kept, else 2D."""
    if cfg.run.lumped_only:
        return MODEL_LUMPED
    if lumped_part(cfg):
        return MODEL_HYBRID_LUMPED if _left_out(cfg) else MODEL_HYBRID_2D
    return MODEL_2D


def model_type(cfg: Any) -> str:
    """The job's own type, or the one it runs as when it gives none (every job before W96)."""
    return cfg.run.model_type or inferred_type(cfg)


def _needs_grid(cfg: Any, kind: str) -> list[str]:
    out = []
    if cfg.terrain.dem is None:
        out.append(f"a {kind} model needs terrain.dem")
    if cfg.grid.domain is None and cfg.grid.extent is None:
        out.append(f"a {kind} model needs a domain: grid.domain or grid.extent")
    if cfg.run.lumped_only:
        out.append(f"a {kind} model runs on the grid, and run.lumped_only is on")
    return out


def model_type_problems(cfg: Any) -> list[str]:
    """Why the job's ``run.model_type`` does not fit the rest of it; empty when it does, or when the job gives none."""
    kind = cfg.run.model_type
    if kind is None:
        return []
    found = lumped_part(cfg)
    h, g = cfg.hydrology, cfg.grid
    if kind == MODEL_LUMPED:
        out = []
        if not cfg.run.lumped_only:
            out.append("a lumped model is the lumped network alone: run.lumped_only must be on")
        if h.hms_basin is None and h.basin_json is None:
            out.append("a lumped model needs a lumped network: hydrology.hms_basin or hydrology.basin_json")
        return out
    out = _needs_grid(cfg, {MODEL_2D: "2D", MODEL_HYBRID_LUMPED: "Hybrid Lumped", MODEL_HYBRID_2D: "Hybrid 2D"}[kind])
    if kind == MODEL_2D:
        if found:
            out.append(f"a 2D model has no lumped part, and the job has {', '.join(found)}: choose a hybrid type")
        if _left_out(cfg):
            out.append("a 2D model leaves no catchment out of the mesh: grid.exclude_lumped and grid.exclude_subbasins must be off")
        return out
    if not found and h.hms_basin is None:
        out.append(
            "a hybrid model needs a lumped part: a basin file (hydrology.hms_basin or hydrology.basin_json) with lumped "
            "subbasins, or lumped subbasins in hydrology.subbasins"
        )
    if kind == MODEL_HYBRID_LUMPED and not g.exclude_lumped:
        out.append("a Hybrid Lumped model leaves its lumped catchments out of the mesh: grid.exclude_lumped must be on")
    if kind == MODEL_HYBRID_2D and _left_out(cfg):
        out.append(
            "a Hybrid 2D model keeps its lumped catchments' cells in the mesh, only the wet ones active: "
            "grid.exclude_lumped and grid.exclude_subbasins must be off, or choose Hybrid Lumped"
        )
    return out


def implied_by_type(data: Any) -> Any:
    """A job as given (a dict, before validation) with what its type implies set where the job leaves it unsaid."""
    if not isinstance(data, dict):
        return data
    run = data.get("run")
    kind = run.get("model_type") if isinstance(run, dict) else getattr(run, "model_type", None)
    if kind not in IMPLIED:
        return data
    part, name, value = IMPLIED[kind]
    section = data.get(part, {})
    if not isinstance(section, dict) or name in section:
        return data
    return {**data, part: {**section, name: value}}
